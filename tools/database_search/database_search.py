"""Database Search tool — Phase 4 of the RAG layer.

Wraps the locked-design semantic search over the Postgres ``chunks``
table (architecture doc §4 + §9.11) as an LLM-facing langchain
``@tool`` that any chain agent can invoke during a live session.

Public surface
--------------
``make_database_search_tool(caller_agent: str)``
    Factory.  Returns a fresh ``@tool``-decorated function with the
    caller's agent identifier baked into a closure.  The LLM-facing
    schema has NO ``caller_agent`` parameter, so the LLM cannot spoof
    its identity.  Phase 4C calls this once per chain agent in their
    ``set_tools()`` methods.

Behaviour locked by the architecture doc
----------------------------------------
* §4.2 — ``$caller_agent = ANY(agents_to)`` pre-filter on every query.
* §4.3 — ``N`` counts ANCHORS (distinct sessions or attempts), not
  chunks.  Dedup via ``ROW_NUMBER() PARTITION BY anchor`` over a
  ``DATABASE_SEARCH_CANDIDATE_POOL_MAGNIFIER × N`` candidate pool.
* §4.5 — token cap = ``DATABASE_SEARCH_MAX_RESPONSE_TOKENS``; trim
  lowest-ranked anchors first; never partial-anchor truncation.
* §4.6 — every response opens with ``<search_meta .../>``.
* §4.7 — locked no-results wording (two variants).
* §4.9 — embedding-model mismatch is silent-skip; count reported in
  ``<search_meta>``.
* §8 invariant 8 — every vector query MUST include the prefix
  ``WHERE NOT is_error AND NOT is_empty AND field_type = 'Semantic'``.
  Enforced once in a single helper here.
* §8 invariant 11 — every call is logged to ``rag_queries``, success
  or error.

This module is incomplete: phase 4B step 2 lands only the package
skeleton + public API stub.  SQL, XML emission, trim loop, error
handling, and ``rag_queries`` logging land in subsequent steps.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Annotated, Any
from xml.sax.saxutils import escape, quoteattr

import psycopg
import tiktoken
from psycopg.types.json import Json
from langchain_core.tools import tool

from agents.shared import postgres_pool
from agents.shared.agent_activity import generic_tool
from agents.database_handler import db_writer
from workflow_settings import settings as workflow_settings

logger = logging.getLogger("propeller_agent")


# ============================================================
# Module-local references to the settings.py knobs
# ============================================================
# Re-bound at module-import time.  ``settings.py`` is the single
# source of truth; these are read-only aliases for readability at
# the call sites below.  A workflow-settings edit takes effect on
# the NEXT process start (same lifecycle as every other settings
# constant — see agents/loader.py's settings-load behaviour).

_MAX_RESPONSE_TOKENS = int(workflow_settings.DATABASE_SEARCH_MAX_RESPONSE_TOKENS)
_CANDIDATE_POOL_MAGNIFIER = int(workflow_settings.DATABASE_SEARCH_CANDIDATE_POOL_MAGNIFIER)


# ============================================================
# Section 2.  SQL layer (Phase 4B step 3)
# ============================================================
# Three queries against the Postgres ``chunks`` table:
#
#   1. _run_candidate_query     — window-function dedup over a
#      magnifier × N candidate pool; returns up to N ANCHOR hits
#      ranked by their best-matching chunk (Q-4A-4 + §4.3).
#   2. _run_expansion_query     — for the chosen anchors, fetch
#      every Q+A pair the caller can see, respecting ACL +
#      embedding-model filter (§4.4).
#   3. _run_mismatch_count_query — second cheap COUNT query for
#      the <search_meta skipped_due_to_model_mismatch=N/> field
#      (§4.6 + §4.9).
#
# All three SQL build sites go through ``_invariant_8_where_fragment()``
# so the partial HNSW index (schema v6) actually engages — §8
# invariant 8.  This is the SINGLE PLACE the locked prefix is
# spelled out; grep for it before adding any new vector query.


# ----- Single source of truth for §8 invariant 8 ------------

def _invariant_8_where_fragment() -> str:
    """Return the locked WHERE prefix every vector query against
    ``chunks`` MUST include.  See architecture doc §8 invariant 8
    and schema v6 ``idx_chunks_embedding`` partial-index definition.

    Forgetting any predicate causes Postgres to fall back to a
    sequential scan over the full chunks table — correct but
    ~1000× slower with no warning.
    """
    return "NOT is_error AND NOT is_empty AND field_type = 'Semantic'"


# ----- Typed return shapes ----------------------------------

@dataclass(frozen=True)
class AnchorHit:
    """One row from the candidate-pool window-function query.

    Represents a distinct anchor (session or attempt) with its
    best-matching chunk's distance, used to rank anchors.  Q+A
    text is fetched separately by :func:`_run_expansion_query`.
    """
    session_id:    str
    attempt_id:    int | None     # NULL = session-scoped anchor
    attempt_label: str | None     # human-readable 'NNN' slug; NULL when attempt_id is NULL
    dist:          float          # cosine distance to query (lower = closer)
    best_chunk_id: int            # id of the rank-1 chunk for this anchor


@dataclass(frozen=True)
class ExpandedChunk:
    """One Q+A pair returned by the expansion query.

    ``dist`` is populated only for the anchor's best-matching
    chunk (the one that came from the candidate query); siblings
    fetched by the expansion get ``dist=None``.  The caller
    stamps the rank-1 chunk's distance from the matching
    :class:`AnchorHit` before emitting XML.
    """
    chunk_id:      int                # chunks.id — lets the emitter match against AnchorHit.best_chunk_id
    session_id:    str
    attempt_id:    int | None
    attempt_label: str | None         # human-readable 'NNN' slug; NULL for session-scoped chunks
    agent_from:    str
    field:         str
    field_type:    str                # "Semantic" | "Quantitative"
    question:      str | None
    body:          str
    item_index:    int | None
    dist:          float | None


# ----- Query 1.  Candidate pool + window-function dedup -----

def _run_candidate_query(
    conn,
    *,
    query_vec:           list[float],
    caller_agent:        str,
    embedding_model:     str,
    n:                   int,
    attempt_specific:    bool,
    metafilter_where:    str,
    metafilter_params:   dict[str, Any],
    candidate_pool_size: int,
) -> list[AnchorHit]:
    """Run the locked candidate-pool window-function query and
    return up to ``n`` distinct anchors ranked by their
    best-matching chunk's distance.

    Implements §4.3 (anchor semantics) + Q-4A-4 (window-function
    dedup over a ``DATABASE_SEARCH_CANDIDATE_POOL_MAGNIFIER × N``
    candidate pool) + §8 invariant 8 (locked WHERE prefix).

    Parameters
    ----------
    conn:
        A psycopg connection from
        :func:`agents.shared.postgres_pool.connection`.
    query_vec:
        The embedded query vector (``EMBEDDING_VECTOR_DIMS`` floats).
    caller_agent:
        The calling agent's slug (one of
        :data:`agents.database_handler.db_writer.DEFAULT_AGENTS_TO_ACL`).
    embedding_model:
        The ``chunks.embedding_model`` value to match (e.g.
        ``"openai/text-embedding-3-large/1024"``).
    n:
        Number of anchors to return (§4.3 — counts anchors, not
        chunks).
    attempt_specific:
        When ``True``, the PARTITION key is ``attempt_id`` and
        ``attempt_id IS NULL`` chunks are excluded (§4.4).  When
        ``False``, the PARTITION key is ``session_id``.
    metafilter_where:
        SQL fragment already built by the metafilter parser
        (Step 4).  May be the empty string.
    metafilter_params:
        Named-placeholder params keyed by the names that appear
        in ``metafilter_where``.  Merged with the fixed params
        below.
    candidate_pool_size:
        Number of candidate chunks to fetch before dedup.
        Typically ``_CANDIDATE_POOL_MAGNIFIER * n``.

    Returns
    -------
    Up to ``n`` :class:`AnchorHit` instances, ordered by ascending
    distance (closest first).  Empty list when no chunks match the
    filters.  When dedup leaves fewer than ``n`` anchors (heavy
    clustering), returns what it found — the caller logs the
    shortfall to ``rag_queries.n_returned``.
    """
    # PARTITION key differs by attempt_specific flag (§4.4).
    # NOTE: partition_expr is used inside the ``ranked`` CTE whose
    # FROM is the ``candidates`` CTE — the chunks alias ``c`` is
    # NOT in scope there.  Reference the column names bare.
    # attempt_clause, by contrast, IS inside the ``candidates`` CTE
    # so it correctly keeps the ``c.`` prefix.
    if attempt_specific:
        partition_expr = "attempt_id::text"
        attempt_clause = "AND c.attempt_id IS NOT NULL"
    else:
        partition_expr = "session_id"
        attempt_clause = ""

    extra_where = f" AND {metafilter_where}" if metafilter_where else ""

    sql = f"""
        WITH candidates AS (
            SELECT
                c.id            AS chunk_id,
                c.session_id    AS session_id,
                c.attempt_id    AS attempt_id,
                a.attempt_label AS attempt_label,
                c.embedding <=> %(query_vec)s::vector AS dist
            FROM chunks c
            JOIN sessions s         ON s.session_id = c.session_id
            LEFT JOIN dc_attempts a ON a.attempt_id = c.attempt_id
            WHERE {_invariant_8_where_fragment()}
              AND %(caller_agent)s = ANY(c.agents_to)
              AND c.embedding_model = %(embedding_model)s
              {attempt_clause}
              {extra_where}
            ORDER BY c.embedding <=> %(query_vec)s::vector
            LIMIT %(candidate_pool_size)s
        ),
        ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY {partition_expr}
                       ORDER BY dist
                   ) AS rn
            FROM candidates
        )
        SELECT chunk_id, session_id, attempt_id, attempt_label, dist
        FROM ranked
        WHERE rn = 1
        ORDER BY dist
        LIMIT %(n)s;
    """
    params: dict[str, Any] = {
        "query_vec":           query_vec,
        "caller_agent":        caller_agent,
        "embedding_model":     embedding_model,
        "candidate_pool_size": candidate_pool_size,
        "n":                   n,
        **metafilter_params,
    }
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [
            AnchorHit(
                session_id    = row[1],
                attempt_id    = row[2],
                attempt_label = row[3],
                dist          = float(row[4]),
                best_chunk_id = int(row[0]),
            )
            for row in cur.fetchall()
        ]


# ----- Query 2.  Anchor expansion (all Q/A per anchor) ------

def _run_expansion_query(
    conn,
    *,
    anchors:          list[AnchorHit],
    caller_agent:     str,
    embedding_model:  str,
    attempt_specific: bool,
) -> list[ExpandedChunk]:
    """Fetch every Q+A pair the caller can see within the anchor
    set, respecting ACL + embedding-model filter.  Per §4.4:

      * ``attempt_specific=False`` → every chunk in each anchor
        SESSION (siblings + the rank-1 chunk).
      * ``attempt_specific=True``  → only chunks within each
        anchor ATTEMPT.

    The expansion query does NOT compute distances — sibling
    chunks of the rank-1 chunk get ``dist=None``; the caller
    (XML emitter, Step 5) stamps the rank-1 chunk's distance
    from the matching :class:`AnchorHit`.

    Parameters
    ----------
    conn:
        A psycopg connection.
    anchors:
        Output of :func:`_run_candidate_query`.  Empty input is
        allowed and returns an empty list without hitting the
        database.
    caller_agent, embedding_model:
        Same as in :func:`_run_candidate_query` — the ACL +
        model-mismatch filter must match the candidate query
        so the expansion never reveals chunks the caller could
        not have seen ranked.
    attempt_specific:
        Must match the value passed to the candidate query for
        this search.  Determines whether the anchor key is
        ``attempt_id`` (when ``True``) or ``session_id``.

    Returns
    -------
    Unsorted list of :class:`ExpandedChunk` covering every Q+A
    pair within the anchor set the caller can see.  The XML
    emitter groups by anchor downstream.
    """
    if not anchors:
        return []

    if attempt_specific:
        anchor_keys: list[Any] = [a.attempt_id for a in anchors]
        anchor_filter          = "c.attempt_id = ANY(%(anchor_keys)s)"
    else:
        anchor_keys            = [a.session_id for a in anchors]
        anchor_filter          = "c.session_id = ANY(%(anchor_keys)s)"

    sql = f"""
        SELECT
            c.id            AS chunk_id,
            c.session_id,
            c.attempt_id,
            a.attempt_label,
            c.agent_from,
            c.field,
            c.field_type,
            c.question,
            c.body,
            c.item_index
        FROM chunks c
        LEFT JOIN dc_attempts a ON a.attempt_id = c.attempt_id
        WHERE {_invariant_8_where_fragment()}
          AND %(caller_agent)s = ANY(c.agents_to)
          AND c.embedding_model = %(embedding_model)s
          AND {anchor_filter}
    """
    params: dict[str, Any] = {
        "caller_agent":    caller_agent,
        "embedding_model": embedding_model,
        "anchor_keys":     anchor_keys,
    }
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [
            ExpandedChunk(
                chunk_id      = int(row[0]),
                session_id    = row[1],
                attempt_id    = row[2],
                attempt_label = row[3],
                agent_from    = row[4],
                field         = row[5],
                field_type    = row[6],
                question      = row[7],
                body          = row[8],
                item_index    = row[9],
                dist          = None,
            )
            for row in cur.fetchall()
        ]


# ----- Query 3.  Embedding-model mismatch COUNT -------------

def _run_mismatch_count_query(
    conn,
    *,
    caller_agent:      str,
    embedding_model:   str,
    metafilter_where:  str,
    metafilter_params: dict[str, Any],
) -> int:
    """Return the number of chunks the caller could otherwise see
    (same ACL + metafilters + invariant-8 prefix) whose
    ``embedding_model`` does NOT match the query's model.

    Populates ``<search_meta skipped_due_to_model_mismatch="N"/>``
    per §4.6 + §4.9.  Cheap indexed COUNT — no vector op, no
    HNSW scan.  Almost always returns 0 today since only one
    embedding model is in use; matters after an EMBEDDING_MODEL
    change in workflow_settings.
    """
    extra_where = f" AND {metafilter_where}" if metafilter_where else ""
    sql = f"""
        SELECT COUNT(*)
        FROM chunks c
        JOIN sessions s         ON s.session_id = c.session_id
        LEFT JOIN dc_attempts a ON a.attempt_id = c.attempt_id
        WHERE {_invariant_8_where_fragment()}
          AND %(caller_agent)s = ANY(c.agents_to)
          AND c.embedding_model <> %(embedding_model)s
          {extra_where};
    """
    params: dict[str, Any] = {
        "caller_agent":    caller_agent,
        "embedding_model": embedding_model,
        **metafilter_params,
    }
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return int(cur.fetchone()[0])


# ----- Query 4.  Available attempts per session (Phase 5D) ---

# attempt_label format is <YYYYMMDD>_<HHMMSS>_<NNN>_<slug>; this regex
# captures the 3+ digit NNN.  Same convention as the parser in
# tools/retrieve_attempt/retrieve_attempt.py.
_ATTEMPT_LABEL_NNN_RE = re.compile(r"^\d+_\d+_(\d+)_")


def _run_available_attempts_query(
    conn,
    *,
    session_ids: list[str],
) -> dict[str, list[tuple[int, str]]]:
    """Fetch all attempts saved for each of *session_ids*.

    Returns a dict mapping each session_id to a list of
    ``(global_attempt_id, nnn)`` tuples sorted by global_id ascending.
    Sessions with no saved attempts (or session_ids not in the
    sessions table) map to an empty list — never absent from the dict
    so the caller never has to guard against missing keys.

    Powers the per-session ``<available_attempts>`` block added to
    every database_search response in Phase 5D.  The block enables
    agents to discover the global attempt ids they can pass to the
    ``retrieve_attempt`` tool, including attempts that didn't match
    the semantic search.

    NNN is extracted from ``attempt_label`` via the
    ``<TS>_<NNN>_<slug>`` regex; labels that don't match (defensive)
    are silently skipped.
    """
    out: dict[str, list[tuple[int, str]]] = {sid: [] for sid in session_ids}
    if not session_ids:
        return out
    sql = """
        SELECT session_id, attempt_id, attempt_label
        FROM dc_attempts
        WHERE session_id = ANY(%(session_ids)s)
        ORDER BY attempt_id
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"session_ids": session_ids})
        for sid, gid, label in cur.fetchall():
            m = _ATTEMPT_LABEL_NNN_RE.match(label or "")
            if not m:
                continue
            out.setdefault(sid, []).append((int(gid), m.group(1)))
    return out


# ============================================================
# Section 3.  Metafilter parser (Phase 4B step 4)
# ============================================================
# Turn the LLM-supplied metafilters dict into a (where_sql, params)
# pair that Section 2's queries accept verbatim.
#
# Syntax (Q-4A-6, hybrid string-prefix):
#   {"k": V}           equality          (V is a primitive)
#   {"k": ">=N"}       comparison        (string starting with op)
#   {"k": [...]}       IN-list           (Python list)
#
# Supported operators in comparison strings: =, >=, <=, >, <.
#
# v1 covers only the 11 §2.2 metafilters on sessions / dc_attempts /
# chunks columns.  Parameter-value filters (e.g. bladeCount>=5) are
# deferred to T1 — the dc_attempt_parameters JOIN is not built.


@dataclass(frozen=True)
class _MetafilterSpec:
    """How one metafilter key maps to SQL + what values are allowed."""
    sql_expr:            str                # e.g. "s.dc_name"
    py_type:             type                # str / int / bool
    supports_comparison: bool
    supports_in:         bool


_METAFILTER_SPEC: dict[str, _MetafilterSpec] = {
    # sessions.*
    "dc_name":              _MetafilterSpec("s.dc_name",              str,  False, True),
    "satisfaction":         _MetafilterSpec("s.satisfaction",         int,  True,  False),
    "session_ts":           _MetafilterSpec("s.session_ts",           str,  True,  False),
    "schema_version":       _MetafilterSpec("s.schema_version",       int,  True,  True),
    "dc_inspector_enabled": _MetafilterSpec("s.dc_inspector_enabled", bool, False, False),
    "user_id":              _MetafilterSpec("s.user_id",              str,  False, True),
    "user_provided_images": _MetafilterSpec("s.user_provided_images", bool, False, False),
    # dc_attempts.*
    "has_geometry":         _MetafilterSpec("a.has_geometry",         bool, False, False),
    "has_renders":          _MetafilterSpec("a.has_renders",          bool, False, False),
    # chunks.*
    "agent_from":           _MetafilterSpec("c.agent_from",           str,  False, True),
    "field":                _MetafilterSpec("c.field",                str,  False, True),
}

# Longest prefix first so the greedy match picks ``>=`` before ``>``.
_COMPARISON_OPS = ("<=", ">=", "<", ">")


class InvalidMetafilterError(ValueError):
    """Raised when the metafilters dict has an unknown key, a
    wrong-type value, an unsupported operator, or a comma-string
    where a list is expected.

    Surfaces in Step 7 as ``<search_meta error="invalid_metafilter"/>``.
    """


def _is_strict_type(value: Any, expected: type) -> bool:
    """Strict type check that does NOT treat ``bool`` as ``int``.

    Required because Python evaluates ``isinstance(True, int)`` as
    ``True`` (bool is a subclass of int).  Without this guard,
    ``{"satisfaction": True}`` would be accepted as a valid int
    filter — silently misleading.
    """
    if expected is int:
        return type(value) is int       # excludes bool
    if expected is bool:
        return type(value) is bool
    return isinstance(value, expected)


def _parse_metafilters(
    metafilters: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """Turn the LLM-supplied metafilters dict into ``(where_sql, params)``.

    Empty / ``None`` input returns ``("", {})``.  The caller stitches
    the where_sql into the main query with an
    ``f" AND {where}" if where else ""`` pattern — see
    :func:`_run_candidate_query` for the live call site.

    Param keys are prefixed ``mf_<key>`` so they cannot collide with
    the fixed params (``query_vec``, ``caller_agent``,
    ``embedding_model``, ``n``, ``candidate_pool_size``,
    ``anchor_keys``) Section 2 uses.

    Raises
    ------
    InvalidMetafilterError
        On unknown key, wrong-type value, unsupported operator, or
        comma-separated string where a real list is expected.
    """
    if not metafilters:
        return "", {}

    clauses: list[str] = []
    params:  dict[str, Any] = {}

    for key, raw_value in metafilters.items():
        if key not in _METAFILTER_SPEC:
            raise InvalidMetafilterError(
                f"Unknown metafilter key {key!r}.  Supported keys: "
                f"{sorted(_METAFILTER_SPEC)}."
            )
        spec       = _METAFILTER_SPEC[key]
        param_name = f"mf_{key}"

        # ----- list → IN ------------------------------------
        if isinstance(raw_value, list):
            if not spec.supports_in:
                raise InvalidMetafilterError(
                    f"Metafilter {key!r} does not support list (IN) syntax."
                )
            for v in raw_value:
                if not _is_strict_type(v, spec.py_type):
                    raise InvalidMetafilterError(
                        f"Metafilter {key!r} list element {v!r} is "
                        f"not of expected type {spec.py_type.__name__}."
                    )
            clauses.append(f"{spec.sql_expr} = ANY(%({param_name})s)")
            params[param_name] = list(raw_value)
            continue

        # ----- string starting with operator → comparison ---
        if isinstance(raw_value, str):
            matched_op: str | None = None
            for op in _COMPARISON_OPS:
                if raw_value.startswith(op):
                    matched_op = op
                    break
            if matched_op is not None:
                if not spec.supports_comparison:
                    raise InvalidMetafilterError(
                        f"Metafilter {key!r} does not support "
                        f"comparison operators."
                    )
                operand_str = raw_value[len(matched_op):].strip()
                operand: Any
                try:
                    if spec.py_type is int:
                        operand = int(operand_str)
                    elif spec.py_type is float:
                        operand = float(operand_str)
                    else:
                        operand = operand_str  # str (e.g. ISO 8601)
                except ValueError as exc:
                    raise InvalidMetafilterError(
                        f"Metafilter {key!r} operand {operand_str!r} "
                        f"could not be coerced to {spec.py_type.__name__}."
                    ) from exc
                clauses.append(
                    f"{spec.sql_expr} {matched_op} %({param_name})s"
                )
                params[param_name] = operand
                continue
            # plain string falls through to equality

            # Reject comma-separated lists masquerading as strings,
            # but only for keys that DO support lists — otherwise
            # a legitimate string like "foo,bar" gets falsely
            # rejected.
            if "," in raw_value and spec.supports_in:
                raise InvalidMetafilterError(
                    f"Metafilter {key!r} got a comma-separated string "
                    f"{raw_value!r} — pass a real list instead, e.g. "
                    f"{key!r}: {raw_value.split(',')!r}."
                )

        # ----- primitive → equality -------------------------
        if not _is_strict_type(raw_value, spec.py_type):
            raise InvalidMetafilterError(
                f"Metafilter {key!r} value {raw_value!r} is not of "
                f"expected type {spec.py_type.__name__}."
            )
        clauses.append(f"{spec.sql_expr} = %({param_name})s")
        params[param_name] = raw_value

    return " AND ".join(clauses), params


# ============================================================
# Section 4.  XML emission + token-cap trim (Phase 4B step 5)
# ============================================================
# Turn the Step-3 query outputs (AnchorHit + ExpandedChunk lists)
# into the locked §5 XML response string.  Apply the §4.5 token
# cap via the naive O(N²) drop-lowest-rebuild loop (Q-4A-12).
#
# Layout per anchor:
#
#   attempt_specific=False  →  <session id="..." score="X">
#                                <session_generic>... <qa/> ...</session_generic>
#                                <attempt id="NNN"> ... <qa/> ... </attempt>
#                                <attempt id="MMM"> ... <qa/> ... </attempt>
#                              </session>
#
#   attempt_specific=True   →  <session id="...">
#                                <attempt id="NNN" score="X"> ... <qa/> ... </attempt>
#                              </session>
#
# The rank-1 chunk per anchor (matched on chunks.id == AnchorHit
# .best_chunk_id) gets best_match="true"; siblings have no marker.
# Per §4.8 the score lives on the anchor element (rank-1 chunk's
# similarity), NOT on individual <qa> — siblings' distances are
# unknown so attaching scores there would lie.


@dataclass(frozen=True)
class SearchMeta:
    """Inputs to the <search_meta/> opener.  Built fresh each iteration
    of the trim loop because ``n_returned`` shrinks when anchors drop.
    """
    n_requested:                   int
    n_returned:                    int    # FINAL count after trim
    attempt_specific:              bool
    metafilters_repr:              str    # raw repr() of the dict; escaped at emit time
    embedding_model:               str
    skipped_due_to_model_mismatch: int


# Lazy module-level tiktoken encoding cache.  cl100k_base matches
# the Context Pruner family (settings.py §13-§15) so token budgets
# across the system stay comparable.
_TIKTOKEN_ENC: Any = None


def _get_tiktoken():
    global _TIKTOKEN_ENC
    if _TIKTOKEN_ENC is None:
        _TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")
    return _TIKTOKEN_ENC


def _count_tokens(text: str) -> int:
    """cl100k_base token count for ``text``.  Used by the trim loop."""
    return len(_get_tiktoken().encode(text))


def _similarity_score(dist: float) -> float:
    """Convert pgvector cosine distance to cosine similarity (3 d.p.).

    pgvector's ``<=>`` returns ``1 - cos_sim`` for normalised vectors;
    OpenAI ``text-embedding-3-large`` outputs are normalised so this
    is well-defined and bounded to [0.0, 1.0] for non-pathological
    inputs.  Three decimals is enough for the LLM to distinguish
    "this matched well" (0.85+) from "this was a stretch" (0.4-).
    """
    return round(1.0 - float(dist), 3)


# ----- Per-<qa> emission ------------------------------------

def _emit_qa(chunk: ExpandedChunk, *, best_match: bool) -> str:
    """Emit one ``<qa>...</qa>`` block.  Text fields escaped via
    ``saxutils.escape``; attribute values via ``saxutils.quoteattr``.
    """
    attrs = (
        f"agent={quoteattr(chunk.agent_from)} "
        f"field={quoteattr(chunk.field)} "
        f"type={quoteattr(chunk.field_type)}"
    )
    if best_match:
        attrs += ' best_match="true"'
    q = escape(chunk.question or "")
    a = escape(chunk.body)
    return (
        f"    <qa {attrs}>\n"
        f"      <question>{q}</question>\n"
        f"      <answer>{a}</answer>\n"
        f"    </qa>"
    )


# ----- Per-anchor emission ----------------------------------

def _sort_chunks_for_emission(
    anchor: AnchorHit,
    chunks: list[ExpandedChunk],
) -> list[ExpandedChunk]:
    """Rank-1 chunk first (matched on best_chunk_id), then siblings
    by item_index (NULL-as-zero) then chunk_id for determinism.
    """
    return sorted(
        chunks,
        key=lambda c: (
            c.chunk_id != anchor.best_chunk_id,    # False (0) sorts before True (1)
            c.item_index if c.item_index is not None else 0,
            c.chunk_id,
        ),
    )


def _emit_anchor_block(
    anchor:             AnchorHit,
    chunks:             list[ExpandedChunk],
    attempt_specific:   bool,
    available_attempts: list[tuple[int, str]],
) -> str:
    """Emit one anchor's ``<session>...</session>`` block.

    Always wraps in ``<session>`` even in attempt-specific mode — the
    session_id provides context (which session this attempt belongs
    to) and matches §5.2's layout.  When attempt_specific=True the
    score lives on the inner ``<attempt>`` element (the actual
    anchor); when False it lives on ``<session>`` directly.

    *available_attempts* (Phase 5D) is the list of
    ``(global_id, nnn)`` pairs for this session, sorted by global_id
    ascending.  Always emitted as a ``<available_attempts>`` child of
    ``<session>``; self-closing when empty so the agent never has to
    interpret absence.  Matched ``<attempt>`` elements ALSO carry
    their ``global_id`` attribute (also Phase 5D), so the agent can
    feed it directly into ``retrieve_attempt``.
    """
    score    = _similarity_score(anchor.dist)
    sid_attr = quoteattr(anchor.session_id)

    # Phase 5D: <available_attempts> block (always emitted)
    if available_attempts:
        avail_lines = ["  <available_attempts>"]
        for gid, nnn in available_attempts:
            avail_lines.append(
                f'    <attempt global_id="{gid}" nnn={quoteattr(nnn)}/>'
            )
        avail_lines.append("  </available_attempts>")
        avail_block = "\n".join(avail_lines)
    else:
        avail_block = "  <available_attempts/>"

    if attempt_specific:
        att_label = anchor.attempt_label or str(anchor.attempt_id or "")
        sorted_chunks = _sort_chunks_for_emission(anchor, chunks)
        qa_lines = "\n".join(
            _emit_qa(c, best_match=(c.chunk_id == anchor.best_chunk_id))
            for c in sorted_chunks
        )
        global_id_attr = (
            f' global_id="{anchor.attempt_id}"'
            if anchor.attempt_id is not None
            else ""
        )
        return (
            f"<session id={sid_attr}>\n"
            f"{avail_block}\n"
            f'  <attempt id={quoteattr(att_label)}{global_id_attr} score="{score}">\n'
            f"{qa_lines}\n"
            f"  </attempt>\n"
            f"</session>"
        )

    # attempt_specific=False — split chunks by session-generic vs per-attempt.
    generic_chunks: list[ExpandedChunk] = []
    attempt_groups: dict[str, list[ExpandedChunk]] = {}
    for c in chunks:
        if c.attempt_id is None:
            generic_chunks.append(c)
        else:
            key = c.attempt_label or str(c.attempt_id)
            attempt_groups.setdefault(key, []).append(c)

    parts: list[str] = [f'<session id={sid_attr} score="{score}">']
    parts.append(avail_block)

    if generic_chunks:
        parts.append("  <session_generic>")
        for c in _sort_chunks_for_emission(anchor, generic_chunks):
            qa_text = _emit_qa(c, best_match=(c.chunk_id == anchor.best_chunk_id))
            # Indent the whole <qa> block by 2 extra spaces so it
            # nests under <session_generic>.
            parts.append("\n".join("  " + ln for ln in qa_text.splitlines()))
        parts.append("  </session_generic>")

    for att_label in sorted(attempt_groups):
        group_chunks = attempt_groups[att_label]
        # Phase 5D: pick global_id from first chunk in the group (all
        # share the same attempt_id since they're grouped by it).
        global_id_attr = (
            f' global_id="{group_chunks[0].attempt_id}"'
            if group_chunks and group_chunks[0].attempt_id is not None
            else ""
        )
        parts.append(f"  <attempt id={quoteattr(att_label)}{global_id_attr}>")
        for c in _sort_chunks_for_emission(anchor, group_chunks):
            qa_text = _emit_qa(c, best_match=(c.chunk_id == anchor.best_chunk_id))
            parts.append("\n".join("  " + ln for ln in qa_text.splitlines()))
        parts.append("  </attempt>")

    parts.append("</session>")
    return "\n".join(parts)


# ----- Top-level header / footer / no-results ---------------

def _emit_search_meta(meta: SearchMeta) -> str:
    """The ``<search_meta .../>`` opener.  Always present per §4.6."""
    return (
        f'<search_meta '
        f'n_requested="{meta.n_requested}" '
        f'n_returned="{meta.n_returned}" '
        f'attempt_specific={quoteattr("true" if meta.attempt_specific else "false")} '
        f'metafilters={quoteattr(meta.metafilters_repr)} '
        f'embedding_model={quoteattr(meta.embedding_model)} '
        f'skipped_due_to_model_mismatch="{meta.skipped_due_to_model_mismatch}"'
        f'/>'
    )


def _emit_no_results(metafilters_applied: bool) -> str:
    """Locked §4.7 wording — two variants by metafilter presence."""
    if metafilters_applied:
        msg = (
            "No results found. This may be related to the metafilters "
            "applied — consider relaxing them."
        )
    else:
        msg = "No results found."
    return f"<no_results>{escape(msg)}</no_results>"


def _emit_truncated_footer(omitted: int, token_cap: int) -> str:
    """§4.5 footer — emitted only when at least one anchor was dropped."""
    return (
        f'<truncated reason="token_limit" '
        f'omitted_anchors="{omitted}" '
        f'token_cap="{token_cap}"/>'
    )


# ----- Full-response assembly + trim loop -------------------

def _build_response_full(
    *,
    meta:                          SearchMeta,
    anchors:                       list[AnchorHit],
    chunks_by_anchor:              dict[Any, list[ExpandedChunk]],
    attempt_specific:              bool,
    metafilters_applied:           bool,
    omitted:                       int,
    token_cap:                     int,
    available_attempts_by_session: dict[str, list[tuple[int, str]]],
) -> str:
    """Assemble the full response string from its parts.  Pure;
    no token counting — the trim loop calls this then counts."""
    parts = [_emit_search_meta(meta)]
    if not anchors:
        parts.append(_emit_no_results(metafilters_applied))
    for a in anchors:
        key = a.attempt_id if attempt_specific else a.session_id
        parts.append(
            _emit_anchor_block(
                a, chunks_by_anchor.get(key, []), attempt_specific,
                available_attempts_by_session.get(a.session_id, []),
            )
        )
    if omitted > 0:
        parts.append(_emit_truncated_footer(omitted, token_cap))
    return "\n".join(parts)


def _trim_to_token_cap(
    *,
    anchors:                       list[AnchorHit],
    chunks_by_anchor:              dict[Any, list[ExpandedChunk]],
    attempt_specific:              bool,
    metafilters_applied:           bool,
    n_requested:                   int,
    embedding_model:               str,
    metafilters_repr:              str,
    skipped_due_to_mm:             int,
    token_cap:                     int,
    available_attempts_by_session: dict[str, list[tuple[int, str]]],
) -> tuple[str, int]:
    """Naive O(N²) drop-lowest-rebuild trim loop (Q-4A-12).

    Builds the response with all anchors, counts tokens, drops the
    lowest-ranked anchor if over cap, rebuilds and recounts, repeats
    until it fits or all anchors are dropped.

    Returns ``(response_xml, omitted_anchors)`` — the second is for
    ``rag_queries.truncated_anchors`` logging.
    """
    omitted = 0
    kept    = list(anchors)         # local copy; never mutate the caller's list
    while True:
        meta = SearchMeta(
            n_requested                   = n_requested,
            n_returned                    = len(kept),
            attempt_specific              = attempt_specific,
            metafilters_repr              = metafilters_repr,
            embedding_model               = embedding_model,
            skipped_due_to_model_mismatch = skipped_due_to_mm,
        )
        xml = _build_response_full(
            meta                          = meta,
            anchors                       = kept,
            chunks_by_anchor              = chunks_by_anchor,
            attempt_specific              = attempt_specific,
            metafilters_applied           = metafilters_applied,
            omitted                       = omitted,
            token_cap                     = token_cap,
            available_attempts_by_session = available_attempts_by_session,
        )
        if _count_tokens(xml) <= token_cap or not kept:
            return xml, omitted
        kept.pop()                  # drop lowest-ranked (last in score-desc list)
        omitted += 1


# ============================================================
# Section 5.  Pure search pipeline (Phase 4B step 6)
# ============================================================
# The pipeline that wires Sections 2-4 together.  Returns a
# :class:`_SearchOutcome` carrying both the XML response (consumed
# by the @tool caller via the Section 6 wrapper) AND the metrics
# needed for rag_queries logging.
#
# Pipeline:
#   1. Parse metafilters → SQL fragment + params.
#   2. Embed query via db_writer.embed_text.
#   3. Open one pool connection covering steps 4-6.
#   4. Candidate query → AnchorHit list.
#   5. (skipped when 4 returned 0) Expansion query → ExpandedChunk list.
#   6. Mismatch-count query → int.
#   7. Group expanded chunks by anchor key.
#   8. Trim to token cap and assemble XML.
#
# This function deliberately propagates exceptions; Section 6's
# wrapper (:func:`_database_search_impl`) adds the error-XML
# envelope + rag_queries logging on top.


@dataclass(frozen=True)
class _SearchOutcome:
    """Return value of :func:`_run_search_pipeline`.

    Carries both the XML response (consumed by the @tool caller via
    the Section 6 wrapper) AND the metrics needed for ``rag_queries``
    logging (consumed by :func:`_database_search_impl`).
    """
    xml:                           str
    n_returned:                    int             # after trim
    skipped_due_to_model_mismatch: int
    truncated_anchors:             int             # K dropped by trim
    returned_anchor_ids:           list[dict[str, Any]]
                                                   # [{session_id, attempt_id, score}, ...]
    embedding_model:               str             # the model used to embed the query


def _run_search_pipeline(
    *,
    caller_agent:          str,
    query:                 str,
    n:                     int,
    attempt_specific_flag: bool,
    metafilters:           dict[str, Any] | None,
    token_cap:             int = _MAX_RESPONSE_TOKENS,
) -> _SearchOutcome:
    """Run the full search pipeline and return a :class:`_SearchOutcome`.

    Internal helper — not LLM-facing.  Exposes a private
    ``token_cap`` kwarg for smoke tests (Q-4A-3 second sub-question);
    the @tool wrapper does not surface it to the LLM.

    All 3 SQL queries run inside a single
    :func:`postgres_pool.connection` checkout so pool churn stays
    at one borrow/return per tool call.  When the candidate query
    returns 0 anchors the expansion query is skipped (no anchor
    keys to expand) but the mismatch-count query still runs — the
    skipped count is part of the response header regardless of
    whether anchors landed.

    Raises any exception from
    :func:`agents.database_handler.db_writer.embed_text`, the SQL
    helpers, or :class:`InvalidMetafilterError` from
    :func:`_parse_metafilters`.  :func:`_database_search_impl`
    catches these and translates them into
    ``<search_meta error="..."/>`` + ``<error>...</error>`` XML.
    """
    # 1. Parse metafilters (fast-fail on bad input).
    metafilter_where, metafilter_params = _parse_metafilters(metafilters)
    metafilters_applied = bool(metafilter_where)
    metafilters_repr    = repr(metafilters or {})

    # 2. Embed query.
    query_vec, embedding_model = db_writer.embed_text(query)

    # 3-6. Open one connection, run the three queries.
    candidate_pool_size = _CANDIDATE_POOL_MAGNIFIER * n
    with postgres_pool.connection() as conn:
        anchors = _run_candidate_query(
            conn,
            query_vec           = query_vec,
            caller_agent        = caller_agent,
            embedding_model     = embedding_model,
            n                   = n,
            attempt_specific    = attempt_specific_flag,
            metafilter_where    = metafilter_where,
            metafilter_params   = metafilter_params,
            candidate_pool_size = candidate_pool_size,
        )
        if anchors:
            chunks = _run_expansion_query(
                conn,
                anchors          = anchors,
                caller_agent     = caller_agent,
                embedding_model  = embedding_model,
                attempt_specific = attempt_specific_flag,
            )
        else:
            chunks = []
        skipped_count = _run_mismatch_count_query(
            conn,
            caller_agent      = caller_agent,
            embedding_model   = embedding_model,
            metafilter_where  = metafilter_where,
            metafilter_params = metafilter_params,
        )
        # Phase 5D: list ALL attempts saved for each returned session
        # so each <session> block can advertise the full directory
        # (input for the retrieve_attempt tool).  Empty dict when no
        # anchors landed (the no-results path emits no <session>
        # blocks anyway).
        if anchors:
            available_attempts_by_session = _run_available_attempts_query(
                conn,
                session_ids = list({a.session_id for a in anchors}),
            )
        else:
            available_attempts_by_session = {}

    # 7. Group expanded chunks by anchor key.
    chunks_by_anchor: dict[Any, list[ExpandedChunk]] = {}
    for c in chunks:
        key = c.attempt_id if attempt_specific_flag else c.session_id
        chunks_by_anchor.setdefault(key, []).append(c)

    # 8. Trim + assemble.
    xml, omitted = _trim_to_token_cap(
        anchors                       = anchors,
        chunks_by_anchor              = chunks_by_anchor,
        attempt_specific              = attempt_specific_flag,
        metafilters_applied           = metafilters_applied,
        n_requested                   = n,
        embedding_model               = embedding_model,
        metafilters_repr              = metafilters_repr,
        skipped_due_to_mm             = skipped_count,
        token_cap                     = token_cap,
        available_attempts_by_session = available_attempts_by_session,
    )

    # Build returned_anchor_ids for rag_queries logging.  Trim drops
    # from the tail (lowest-ranked), so the anchors that survived are
    # the first ``len(anchors) - omitted``.
    kept_anchors = anchors[: len(anchors) - omitted] if omitted else anchors
    returned_anchor_ids: list[dict[str, Any]] = [
        {
            "session_id": a.session_id,
            "attempt_id": a.attempt_id,
            "score":      _similarity_score(a.dist),
        }
        for a in kept_anchors
    ]

    return _SearchOutcome(
        xml                           = xml,
        n_returned                    = len(kept_anchors),
        skipped_due_to_model_mismatch = skipped_count,
        truncated_anchors             = omitted,
        returned_anchor_ids           = returned_anchor_ids,
        embedding_model               = embedding_model,
    )


# ============================================================
# Section 6.  Error envelope + rag_queries logging (Phase 4B step 7)
# ============================================================
# Wraps :func:`_run_search_pipeline` with:
#   * Q-4A-10 structured error responses
#     (<search_meta error="<category>"/> + <error>...</error>)
#   * Invariant 11 — every call logged to rag_queries (success +
#     error paths) on a best-effort basis.
#
# Error category vocabulary (Q-4A-10b):
#   invalid_metafilter — :class:`InvalidMetafilterError`
#   db_unreachable    — :class:`postgres_pool.PostgresDisabledError`,
#                       :class:`psycopg.OperationalError`,
#                       :class:`psycopg.InterfaceError`
#   embedding_failed  — :class:`db_writer.StitchError`,
#                       :class:`db_writer.EmbedError`
#   timeout           — :class:`TimeoutError`
#   internal          — anything else (also ``logger.exception(...)``)


def _emit_error_response(*, error_category: str, error_message: str) -> str:
    """Build the structured error XML per Q-4A-10.

    Minimal shape — no n_requested/n_returned attrs because some are
    undefined on the error path (e.g. embedding_model is unknown
    when embed_text raised before resolution).
    """
    return (
        f"<search_meta error={quoteattr(error_category)}/>\n"
        f"<error>{escape(error_message)}</error>"
    )


def _log_rag_query(
    *,
    caller_agent:        str,
    query_text:          str,
    n_requested:         int,
    attempt_specific:    bool,
    metafilters:         dict[str, Any] | None,
    embedding_model:     str | None,
    n_returned:          int,
    returned_anchor_ids: list[dict[str, Any]],
    skipped_count:       int,
    truncated_anchors:   int,
    latency_ms:          int,
    error_message:       str | None,
) -> None:
    """Best-effort INSERT into ``rag_queries`` (invariant 11).

    Called by :func:`_database_search_impl` on both success and
    error paths.  Failures here log a WARNING but DO NOT propagate
    — logging must never break the user-facing tool response.

    ``rag_queries.session_id`` is set to NULL in v1.  Linking to
    the live session row is deferred (the session row doesn't
    exist in Postgres until End Session, so the FK would fail
    mid-session).  See Step 7 sub-decision 7-α.
    """
    try:
        with postgres_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO rag_queries (
                        session_id, caller_agent, query_text, query_params,
                        n_requested, attempt_specific, metafilters,
                        embedding_model, n_returned, returned_anchor_ids,
                        skipped_count, truncated_anchors, latency_ms,
                        error_message
                    ) VALUES (
                        NULL, %(caller_agent)s, %(query_text)s, NULL,
                        %(n_requested)s, %(attempt_specific)s, %(metafilters)s,
                        %(embedding_model)s, %(n_returned)s,
                        %(returned_anchor_ids)s, %(skipped_count)s,
                        %(truncated_anchors)s, %(latency_ms)s,
                        %(error_message)s
                    )
                    """,
                    {
                        "caller_agent":        caller_agent,
                        "query_text":          query_text,
                        "n_requested":         n_requested,
                        "attempt_specific":    attempt_specific,
                        "metafilters":         Json(metafilters) if metafilters is not None else None,
                        "embedding_model":     embedding_model,
                        "n_returned":          n_returned,
                        "returned_anchor_ids": Json(returned_anchor_ids),
                        "skipped_count":       skipped_count,
                        "truncated_anchors":   truncated_anchors,
                        "latency_ms":          latency_ms,
                        "error_message":       error_message,
                    },
                )
    except Exception as exc:
        logger.warning(
            "[database_search] rag_queries log failed (best-effort): "
            "%s: %s",
            type(exc).__name__, exc,
        )


def _database_search_impl(
    *,
    caller_agent:          str,
    query:                 str,
    n:                     int,
    attempt_specific_flag: bool,
    metafilters:           dict[str, Any] | None,
    token_cap:             int = _MAX_RESPONSE_TOKENS,
) -> str:
    """Public-facing implementation: error envelope +
    invariant-11 ``rag_queries`` logging on top of
    :func:`_run_search_pipeline`.

    Catches the documented error categories (Q-4A-10b),
    translates each into ``<search_meta error=.../>`` +
    ``<error>...</error>`` XML, and ALWAYS logs to ``rag_queries``
    (success + error paths) per invariant 11.

    Returns the assembled XML string.  Never raises — even
    catastrophic failures land as ``error="internal"`` XML so the
    calling agent always sees a tool result it can reason about.
    """
    start = time.monotonic()
    outcome: _SearchOutcome | None = None
    error_category: str | None     = None
    error_message:  str | None     = None
    xml: str = ""

    try:
        outcome = _run_search_pipeline(
            caller_agent          = caller_agent,
            query                 = query,
            n                     = n,
            attempt_specific_flag = attempt_specific_flag,
            metafilters           = metafilters,
            token_cap             = token_cap,
        )
        xml = outcome.xml
    except InvalidMetafilterError as exc:
        error_category = "invalid_metafilter"
        error_message  = str(exc)
        xml = _emit_error_response(
            error_category=error_category, error_message=error_message,
        )
    except postgres_pool.PostgresDisabledError as exc:
        error_category = "db_unreachable"
        error_message  = str(exc)
        xml = _emit_error_response(
            error_category=error_category, error_message=error_message,
        )
    except (db_writer.StitchError, db_writer.EmbedError) as exc:
        error_category = "embedding_failed"
        error_message  = f"{type(exc).__name__}: {exc}"
        xml = _emit_error_response(
            error_category=error_category, error_message=error_message,
        )
    except TimeoutError as exc:
        error_category = "timeout"
        error_message  = str(exc)
        xml = _emit_error_response(
            error_category=error_category, error_message=error_message,
        )
    except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
        error_category = "db_unreachable"
        error_message  = f"{type(exc).__name__}: {exc}"
        xml = _emit_error_response(
            error_category=error_category, error_message=error_message,
        )
    except Exception as exc:
        error_category = "internal"
        error_message  = f"{type(exc).__name__}: {exc}"
        logger.exception(
            "[database_search] unexpected internal error: caller_agent=%s",
            caller_agent,
        )
        xml = _emit_error_response(
            error_category=error_category, error_message=error_message,
        )

    latency_ms = int((time.monotonic() - start) * 1000)

    _log_rag_query(
        caller_agent        = caller_agent,
        query_text          = query,
        n_requested         = n,
        attempt_specific    = attempt_specific_flag,
        metafilters         = metafilters,
        embedding_model     = outcome.embedding_model     if outcome else None,
        n_returned          = outcome.n_returned          if outcome else 0,
        returned_anchor_ids = outcome.returned_anchor_ids if outcome else [],
        skipped_count       = outcome.skipped_due_to_model_mismatch if outcome else 0,
        truncated_anchors   = outcome.truncated_anchors   if outcome else 0,
        latency_ms          = latency_ms,
        error_message       = error_message,
    )

    return xml


# ============================================================
# Section 7.  Public surface — closure factory (Phase 4B step 6)
# ============================================================
# Per-agent ``@tool`` binding with ``caller_agent`` baked into a
# closure (Q-4A-2).  The LLM-facing tool schema has no caller_agent
# parameter, so the SQL ACL pre-filter can never be spoofed.


def make_database_search_tool(caller_agent: str):
    """Return a fresh langchain ``@tool``-decorated ``database_search``
    function with ``caller_agent`` baked into a Python closure.

    Each of the 8 chain agents calls this factory once at startup
    (in its ``set_tools()`` method) with its own slug from
    ``agents.database_handler.db_writer.DEFAULT_AGENTS_TO_ACL``
    (``"receptionist"``, ``"planner"``, …).

    The LLM-facing tool schema has NO ``caller_agent`` parameter.
    The closure captures it so the SQL ACL pre-filter
    (``WHERE $caller_agent = ANY(agents_to)``) can never be spoofed
    by the LLM.

    Parameters
    ----------
    caller_agent:
        The calling agent's lowercase_snake slug (one of the 9 in
        ``DEFAULT_AGENTS_TO_ACL``).  Validated here so a typo at
        binding time fails loudly rather than silently producing
        rows that fail every ACL check.

    Returns
    -------
    A langchain ``Tool`` object suitable for inclusion in the
    agent's ``bind_tools(...)`` call.

    Raises
    ------
    ValueError
        When ``caller_agent`` is not one of the known slugs.  No
        tool object is returned in that case.
    """
    # Validate the agent slug eagerly — typo at binding time should
    # fail loudly, not silently produce rows whose ACL never matches.
    valid_slugs = set(db_writer.DEFAULT_AGENTS_TO_ACL)
    if caller_agent not in valid_slugs:
        raise ValueError(
            f"make_database_search_tool: caller_agent={caller_agent!r} "
            f"is not one of the {len(valid_slugs)} known agent slugs "
            f"({sorted(valid_slugs)}).  Spelling matters — the SQL ACL "
            f"pre-filter compares verbatim against chunks.agents_to."
        )

    @tool
    @generic_tool("Database Search")
    def database_search(
        query: Annotated[
            str,
            "Natural-language search query.  Describe what past Q+A "
            "you're looking for — e.g. 'thin propeller designs that "
            "worked well', 'failure cases for blade counts above 8'.  "
            "Embedded with the same model the corpus was indexed with "
            "(see <search_meta embedding_model=.../> in the response).",
        ],
        n: Annotated[
            int,
            "Number of distinct ANCHORS to return.  N counts SESSIONS "
            "by default, or ATTEMPTS when attempt_specific_flag=true.  "
            "Each returned anchor is expanded to all Q+A within it "
            "that you're allowed to see.  Typical value: 3-10.",
        ],
        attempt_specific_flag: Annotated[
            bool,
            "When false (default), the search ranks SESSIONS and each "
            "returned <session> is expanded to all Q+A within it.  "
            "When true, the search ranks ATTEMPTS only (session-"
            "generic chunks are excluded) and each returned <attempt> "
            "is expanded only to Q+A within that attempt.  Use true "
            "when you want narrow, per-iteration context (e.g. "
            "'parameters used for the best attempt in similar past "
            "sessions').",
        ] = False,
        metafilters: Annotated[
            dict | None,
            "Optional hard filters narrowing the candidate pool.  "
            "Pass None or {} to skip.  Hybrid string-prefix syntax: "
            '{"k": V} = equality (primitive value), '
            '{"k": ">=N"} = comparison (string with op prefix; '
            "supported ops: =, >=, <=, >, <), "
            '{"k": [...]} = IN-list (Python list).  Supported keys: '
            "dc_name, satisfaction, session_ts (ISO 8601), "
            "schema_version, dc_inspector_enabled, user_id, "
            "user_provided_images, has_geometry, has_renders, "
            "agent_from, field.  Combine freely: "
            '{"has_renders": true, "satisfaction": ">=7"}.',
        ] = None,
    ) -> str:
        """Semantic search over the saved-sessions RAG corpus.

        Returns XML with a <search_meta/> header followed by one
        <session>...</session> block per anchor.  Each block carries
        a similarity ``score`` (cosine similarity, 0-1, 3 d.p.) and
        nests one or more <qa> elements; the closest-matching <qa>
        in each anchor is marked ``best_match="true"``.

        When zero anchors match, returns
        <search_meta n_returned="0"/> + <no_results>...</no_results>
        (the wording hints at metafilter relaxation when filters
        were applied).

        When the assembled response would exceed the token cap,
        the lowest-ranked anchors are dropped and a
        <truncated omitted_anchors="K"/> footer is appended.

        Returns TEXT ONLY.  No images.  After reading a text
        response, a future artefact-fetch tool will let you
        request specific anchors' user-input images / attempt
        renders if needed.
        """
        return _database_search_impl(
            caller_agent          = caller_agent,
            query                 = query,
            n                     = n,
            attempt_specific_flag = attempt_specific_flag,
            metafilters           = metafilters,
        )

    return database_search
