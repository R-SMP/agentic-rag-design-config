"""Masked-RMSE ranking of saved attempts by design parameters (T1).

The long-deferred half of the RAG search layer.  ``database_search``
ranks by what past agents *said*; this ranks by what they *built*.

Architecture-neutral ON PURPOSE.  Nothing here knows whether it is
reached through a new argument on ``database_search``, a separate
``parameter_search`` tool, or a JSON sniffed out of the query string.
It takes a parameter dict, returns ranked attempts, and offers an
adapter onto the existing ``AnchorHit`` pipeline.  Pick the surface
later; this layer does not move.

What the record already locks
-----------------------------
* architecture doc T1 (:1034) -- "RMSE against dc_attempt_parameters,
  normalised per schema_version's min/max".
* design notes D7  -- norm = (raw - min) / (max - min), computed at
  query time by JOIN, NEVER stored.
* design notes D8.1 -- a parameter retired between versions is not in
  the mask and contributes nothing.
* design notes D8.2 -- effective mask = chosen ^ candidate_has_it, and
  "the result-set must always carry 'matched dims = k'".  Mandatory,
  not decorative: without it a k=1 and a k=16 RMSE look alike.
* design notes D8.3 -- a stored value outside the CURRENT range gives
  norm < 0 or > 1.  Intentional.  MUST NOT be clipped.
* design notes D13 -- never rank in Python.  Masked-RMSE is the one
  named exception and even it says the scan stays inside Postgres.
* TODO F2 -- equal weights for every dimension.  Per-parameter weights
  are a separate item, blocked on a sensitivity analysis.  Do not ship
  weights here.
* F46(c) -- impellerHeight is DERIVED and not comparable across
  schema versions; "never a match / ranking signal".

Three traps, each paid for once
-------------------------------
1. ``retired_at IS NULL`` DOES NOT SELECT ONE ROW PER PARAMETER.
   D7 says to join "the most recent active" schema entry, but the v1
   rows were never marked retired -- so on the live database all 16
   parameters have TWO active rows (v1 and v2).  Joining on
   ``retired_at IS NULL`` alone multiplies every attempt's rows and
   DOUBLES ``matched_keys`` (measured: 32/16, 4/2, 2/1).  The RMSE
   itself survived only because v1 and v2 happen to carry identical
   ranges today; the moment one range changes, the average silently
   blends two normalisation bases and nothing looks wrong.  Hence
   ``_ACTIVE_SCHEMA_SQL`` pins MAX(schema_version) as well.

2. Pinning the newest version is also what retires impellerHeight.
   It exists only in v1, with retired_at still NULL, so every
   "active" filter keeps it.  Pinning the newest version drops it,
   which is what D8.1 and F46(c) both ask for.

3. The mask is the JOIN, not an ``if``.  An attempt missing one of
   the queried keys simply contributes no row for it, so k falls out
   of COUNT(*) and an attempt sharing NOTHING with the query produces
   no group at all -- excluded, with no divide-by-zero to guard.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("propeller_agent")

# Ranking is scale-free because every difference is divided by that
# parameter's legal span, so each term is <= 1 and the RMSE lands in
# [0, 1] for in-range data.  Calibrated on the live corpus (95
# attempts, 4465 pairs): identical 0.000, same design re-iterated
# ~0.134, two unrelated designs ~0.440, furthest pair 0.851.
_CLOSENESS_DP = 3

# ----- Topology-3 role equivalence --------------------------
#
# chunks.agents_to names SEVEN-agent roles.  Topology 3 merges those
# roles into two agents, so a literal `design_engineer = ANY(agents_to)`
# matches almost nothing: measured on the live corpus, the DE and the
# RA are each named in 88 of 1464 chunks and in ZERO of the 342
# attempt-level chunks.  Gating a parameter ranking on the literal
# name would hand both of them a permanently empty result.
#
# The merge is already recorded in prose -- agents/shared/topology.py:
# "DC Input Creator + Tool Caller become the Design Engineer; User
# Input Inspector + DC Output Inspector become the Requirements
# Analyst" -- and prompts.PROMPT_MD_RUNTIME_SLOTS gives each merged
# agent "the UNION of its two parents' slots".  This is the same union,
# applied to the ACL instead of to prompt slots.  The DE also absorbs
# the DC Input Inspector, which exists in topology 7 only.
#
# Measured consequence: attempts invisible to the DE goes 95/95 -> 0/95,
# and to the RA 95/95 -> 0/95.  Chunk reach goes 88 -> 975 for the DE
# and 88 -> 863 for the RA.  The DE's 975 is EXACTLY what the DC Input
# Inspector alone already sees, so the expansion grants no topology-3
# agent sight of anything no topology-7 agent already holds.  It is a
# re-labelling, not an escalation -- which is the whole argument for
# doing it here rather than widening agents_to at write time.
_ROLE_EQUIVALENCE: dict[str, tuple[str, ...]] = {
    "design_engineer":      ("dc_input_creator", "dc_input_inspector",
                             "tool_caller"),
    "requirements_analyst": ("user_input_inspector", "dc_output_inspector"),
}


def acl_identities(caller_agent: str) -> list[str]:
    """Every seven-agent role *caller_agent* inherits, itself included.

    An agent with no merge returns just its own slug, so topologies 7
    and 5 are untouched by construction.
    """
    return sorted({caller_agent, *_ROLE_EQUIVALENCE.get(caller_agent, ())})


class ParameterQueryError(ValueError):
    """The parameter dict is unusable: empty, an unknown key, a
    non-numeric value, or a value outside the parameter's legal range.

    Raised BEFORE any SQL runs.  The caller turns it into the same
    kind of structured error envelope ``InvalidMetafilterError`` gets,
    so a mistake comes back as something the agent can correct rather
    than as an empty result it would read as "nothing similar exists".
    """


# ============================================================
# Section 1.  The active parameter schema
# ============================================================

_ACTIVE_SCHEMA_SQL = """
    SELECT param_name, min_value, max_value
      FROM dc_parameter_schemas
     WHERE schema_version = (SELECT MAX(schema_version)
                               FROM dc_parameter_schemas)
       AND retired_at IS NULL
       AND max_value > min_value
"""


def active_schema(conn) -> dict[str, tuple[float, float]]:
    """Return ``{param_name: (min_value, max_value)}`` for the current
    parameter set -- the query vocabulary AND the normalisation basis.

    Pins MAX(schema_version) as well as ``retired_at IS NULL``; trap 1
    in the module docstring says why the second filter alone is not
    enough.  ``max_value > min_value`` guards a zero-width range,
    which would otherwise divide by zero inside the ranking SQL.
    """
    with conn.cursor() as cur:
        cur.execute(_ACTIVE_SCHEMA_SQL)
        schema = {name: (float(lo), float(hi))
                  for name, lo, hi in cur.fetchall()}
    if not schema:
        raise ParameterQueryError(
            "No active parameter schema found in dc_parameter_schemas; "
            "a parameter search cannot be normalised without one.")
    return schema


# ============================================================
# Section 2.  Validation
# ============================================================

def validate_query(
    params: dict,
    schema: dict[str, tuple[float, float]],
) -> dict[str, float]:
    """Check the agent-supplied dict against *schema*; return it
    coerced to floats.

    Key order is irrelevant -- the mask is a set intersection computed
    by a JOIN, so ``{"a": 1, "b": 2}`` and ``{"b": 2, "a": 1}`` are the
    same query.

    Out-of-range values are REJECTED rather than ranked.  If an agent
    asks for bladeCount=20 where the legal band is 3..6, every stored
    attempt is equally far away and the ranking is noise; returning
    the "closest" would be a confidently wrong answer, whereas naming
    the band lets the agent fix it on the next turn.  Note this is a
    deliberate asymmetry with D8.3, which forbids clipping a STORED
    value that falls outside the current range -- that one is real
    history and its out-of-range norm is a true signal.  A QUERY value
    is not history; it is a typo.
    """
    if not isinstance(params, dict) or not params:
        raise ParameterQueryError(
            "Supply at least one design parameter, as a JSON object of "
            "parameter name -> numeric value, e.g. "
            '{"bladeCount": 5, "impellerRadius": 70}.')

    clean: dict[str, float] = {}
    for key, raw in params.items():
        if key not in schema:
            raise ParameterQueryError(
                f"Unknown design parameter {key!r}.  Searchable "
                f"parameters are: {', '.join(sorted(schema))}.")
        # bool is a subclass of int, so isinstance(True, int) is True.
        # The same trap _is_strict_type() guards in the metafilter
        # parser -- {"bladeCount": True} must not read as 1.
        if isinstance(raw, bool):
            raise ParameterQueryError(
                f"Parameter {key!r} got a boolean; it needs a number.")
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ParameterQueryError(
                f"Parameter {key!r} value {raw!r} is not numeric.") from exc
        lo, hi = schema[key]
        if not (lo <= value <= hi):
            raise ParameterQueryError(
                f"Parameter {key!r} value {value:g} is outside its legal "
                f"range {lo:g}..{hi:g}.  Search within the range.")
        clean[key] = value
    return clean


# ============================================================
# Section 3.  The ranking
# ============================================================

@dataclass(frozen=True)
class ParamHit:
    """One ranked attempt.

    ``matched_keys`` is D8.2's mandatory "matched dims = k": how many
    of the queried parameters this attempt actually carries.  Two hits
    with the same rmse and different k are NOT equally comparable, and
    the consumer can only know that if k travels with the number.
    """
    attempt_id:    int
    session_id:    str
    attempt_label: str | None
    rmse:          float          # masked, range-normalised; lower = closer
    matched_keys:  int            # k = |query keys ^ attempt keys|
    n_queried:     int            # |query keys|, so k/n reads as coverage

    @property
    def closeness(self) -> float:
        """``1 - rmse``: bounded 0-1 for in-range data, higher = closer.

        Deliberately NOT clamped.  A stored value outside the current
        legal range (D8.3 -- kept, never clipped) can push rmse above
        1 and closeness below 0.  That is a true signal about the data
        and hiding it would defeat the point of not clipping.
        """
        return round(1.0 - self.rmse, _CLOSENESS_DP)


# The mask, the normalisation, the ACL and the ranking are ONE
# statement, run inside Postgres (D13).  Reading 95 attempts into
# Python and sorting there would be easier and is explicitly forbidden.
#
# `q` is the query vector, passed as two parallel arrays rather than
# interpolated, so parameter names can never reach the SQL as text.
# JOINing `q` to the stored rows IS the mask (trap 3).
#
# The EXISTS clause is invariant 1 -- agents_to is the only ACL, and it
# pre-filters the ranking rather than filtering the display, so the
# ranking never considers an attempt the caller cannot see.  It reads
# ONLY attempt-level chunks (c.attempt_id = p.attempt_id), not the
# whole session: "you may rank this attempt because you may see
# something about THIS attempt" is the tighter and more defensible
# rule, and the measurement shows it costs nothing (0/95 invisible for
# every target agent once the role equivalence is applied).
_MASKED_RMSE_SQL = """
WITH q(param_name, q_value) AS (
    SELECT * FROM unnest(%(keys)s::text[], %(vals)s::float8[])
),
sch AS (
    SELECT param_name, min_value, max_value
      FROM dc_parameter_schemas
     WHERE schema_version = (SELECT MAX(schema_version)
                               FROM dc_parameter_schemas)
       AND retired_at IS NULL
       AND max_value > min_value
),
scored AS (
    SELECT p.attempt_id,
           COUNT(*) AS matched_keys,
           sqrt(AVG(POWER((p.raw_value - q.q_value)
                          / (s.max_value - s.min_value), 2))) AS rmse
      FROM dc_attempt_parameters p
      JOIN q     ON q.param_name = p.param_name
      JOIN sch s ON s.param_name = p.param_name
     WHERE EXISTS (SELECT 1 FROM chunks c
                    WHERE c.attempt_id = p.attempt_id
                      AND c.agents_to && %(acl)s)
     GROUP BY p.attempt_id
)
SELECT sc.attempt_id, a.session_id, a.attempt_label,
       sc.rmse, sc.matched_keys
  FROM scored sc
  JOIN dc_attempts a ON a.attempt_id = sc.attempt_id
 ORDER BY sc.rmse ASC, sc.matched_keys DESC, a.attempt_id ASC
 LIMIT %(n)s
"""


def rank_attempts(
    conn,
    *,
    caller_agent: str,
    params: dict[str, float],
    n: int,
) -> list[ParamHit]:
    """Rank saved attempts by masked, range-normalised RMSE.

    *params* must already have been through :func:`validate_query`.
    *n* counts ATTEMPTS, matching 4.3's rule that N counts anchors
    rather than rows.  *caller_agent* is expanded through
    :func:`acl_identities` and pre-filters the ranking; like every
    other RAG tool it is closure-captured by the factory, never an
    argument the model can set.

    Ordering is ``rmse ASC, matched_keys DESC, attempt_id ASC``.  The
    second key only fires on an exact tie, which is not hypothetical:
    the live corpus holds 95 attempts but only 84 distinct parameter
    vectors, so ties are routine.  On a tie, prefer the attempt that
    matched MORE of what was asked for.  The third key just makes the
    order deterministic; note attempt_id is NOT chronological (the
    lowest ids carry the highest label numbers), so it is a stable
    tiebreak and nothing more.

    NOT sorted by coverage overall, by decision: an attempt storing
    only one of two queried keys, exactly, still outranks one storing
    both with a small error.  k travels with every hit so the consumer
    can discount a thin match itself.
    """
    if not params:
        return []
    with conn.cursor() as cur:
        cur.execute(_MASKED_RMSE_SQL, {
            "keys": list(params),
            "vals": [float(v) for v in params.values()],
            "acl":  acl_identities(caller_agent),
            "n":    int(n),
        })
        rows = cur.fetchall()
    return [
        ParamHit(attempt_id=int(aid), session_id=sid, attempt_label=label,
                 rmse=float(rmse), matched_keys=int(k), n_queried=len(params))
        for aid, sid, label, rmse, k in rows
    ]


# ============================================================
# Section 4.  Adapter onto the existing pipeline
# ============================================================

def to_anchor_hits(hits: list[ParamHit]):
    """Re-shape :class:`ParamHit` rows as ``AnchorHit`` rows.

    The seam that makes this feature small.  Everything downstream of
    the candidate query in ``database_search`` -- the Q+A expansion,
    the per-anchor grouping, the token-cap trim, the XML emitter --
    consumes ``AnchorHit`` and nothing else.  Hand it AnchorHits and
    the whole tail works unchanged, ACL included, so a parameter
    search reuses the response machinery instead of copying it.

    Two fields need care:

    ``dist``  <- the masked RMSE.  Not a cosine distance, but the same
    direction (lower = closer) and the same bounds, so the existing
    ``_similarity_score(dist)`` already computes ``1 - rmse``, which
    IS the closeness.  Nothing to convert.

    ``best_chunk_id`` <- ``-1``.  A parameter match has no
    best-matching chunk: it matched NUMBERS, not text.  -1 never
    equals a real ``chunks.id``, so the emitter marks no <qa> with
    ``best_match="true"`` and the response does not invent a claim
    about which past answer was relevant.  A plausible-looking
    best_match here would be a lie the agent cannot detect.
    """
    from tools.database_search.database_search import AnchorHit
    return [
        AnchorHit(session_id=h.session_id, attempt_id=h.attempt_id,
                  attempt_label=h.attempt_label, dist=h.rmse,
                  best_chunk_id=-1, matched_keys=h.matched_keys,
                  n_queried=h.n_queried)
        for h in hits
    ]
