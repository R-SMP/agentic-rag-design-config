"""Live smoke test for the ``database_search`` tool — Phase 4D.

Seeds three synthetic sessions on the Railway Postgres, exercises
the Phase 4B/4C search pipeline through a series of scenarios, and
cleans up.  Designed to be invoked manually as a standalone script::

    python extra_utilities/db_design/smoke_test_database_search.py

Requirements (any of which missing → script exits early):

* ``DATABASE_PUBLIC_URL`` or ``DATABASE_URL`` set
* ``OPENAI_API_KEY`` set (used by ``db_writer`` during chunk
  seeding for stitch + embed)

Exit codes:

* ``0`` — all seeded data created/destroyed cleanly AND every
  assertion the run executed passed.
* ``1`` — anything failed (seed, scenario, assertion, cleanup).

Cleanup runs in a ``finally:`` block so a failed scenario still
leaves the database untouched at the end.

Status (Phase 4D-1)
-------------------
4D-1 lands the skeleton + seed + cleanup ONLY.  Scenarios 1-4 land
in 4D-2; scenarios 5-8 land in 4D-3.  Running this file as it
stands seeds the dataset, prints "Scenarios skipped", and tears
down.  Useful for verifying the seed + cleanup framework in
isolation before scenario logic enters.

Test-data conventions
---------------------
Every row this script creates carries the per-run prefix
``_RUN_PREFIX`` so cleanup can reliably match by ``LIKE`` without
risking other smoke tests' rows.  Sessions are deleted by
``session_id LIKE prefix%`` (CASCADE handles chunks + dc_attempts).
``rag_queries`` rows are identified via ``query_text LIKE prefix%``
— scenarios MUST prefix their query strings with ``run.prefix`` so
cleanup catches them.
"""

from __future__ import annotations

import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# sys.path + .env bootstrap (must run BEFORE the project imports
# so this script can be invoked from anywhere — typically the repo
# root — without needing PYTHONPATH set first).  Matches
# smoke_test_db_writer.py's pattern.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Load the repo-root .env so DATABASE_PUBLIC_URL / DATABASE_URL /
# OPENAI_API_KEY are available to the modules imported below.
try:
    from dotenv import load_dotenv as _load_dotenv  # type: ignore
    _load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass  # dotenv not installed → expect env vars to be set externally

from agents.shared import postgres_pool
from agents.database_handler import db_writer
from tools.database_search.database_search import _database_search_impl
from workflow_settings import settings as workflow_settings


# ============================================================
# Run-wide constants
# ============================================================

_RUN_TS_UTC = datetime.now(tz=timezone.utc)
_RUN_TS_HMS = _RUN_TS_UTC.strftime("%Y%m%d_%H%M%S")
_RUN_PREFIX = f"_smoke_test_dbsearch_{_RUN_TS_HMS}_"
_DC_NAME    = "propeller"


# ============================================================
# Run context
# ============================================================

@dataclass
class SmokeRun:
    """Carries per-run state — the prefix that tags every row, the
    list of seeded session_ids (for explicit reference in
    scenarios), the BIGSERIAL attempt_ids returned by upsert_attempt
    (keyed by their session_id), and assertion counters.
    """
    prefix:             str
    seeded_session_ids: list[str]      = field(default_factory=list)
    seeded_attempt_ids: dict[str, int] = field(default_factory=dict)
    assertions_passed:  int            = 0
    assertions_failed:  int            = 0
    failures:           list[str]      = field(default_factory=list)


def _assert(run: SmokeRun, condition: bool, label: str, detail: str = "") -> None:
    """Mark one assertion.  Does NOT raise on failure — the
    remaining scenarios still run so the operator sees the full
    picture per smoke-test invocation.
    """
    if condition:
        run.assertions_passed += 1
        print(f"[assert] OK    — {label}")
    else:
        run.assertions_failed += 1
        msg = f"{label}" + (f"  ({detail})" if detail else "")
        run.failures.append(msg)
        print(f"[assert] FAIL  — {msg}")


# ============================================================
# Seeding helpers
# ============================================================

def _set_satisfaction(session_id: str, value: int) -> None:
    """Direct ``UPDATE`` on ``sessions.satisfaction`` for test
    seeding.  Bypasses :func:`db_writer.save_session_feedback`
    because that helper would also write feedback ``chunks`` rows
    we don't need for the smoke-test fixture.
    """
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sessions SET satisfaction = %s WHERE session_id = %s",
                (value, session_id),
            )
            conn.commit()


def _seed_chunk_or_die(run: SmokeRun, **kwargs: Any) -> None:
    """Wrap :func:`db_writer.insert_chunk` for the seed path.

    Fails loudly on ``InsertOutcome.SAFETY`` — that would mean the
    DB INSERT failed and the test data leaked to the R2 safety
    folder, which is never expected during smoke-test seeding.
    ``SKIPPED_UNIQUE`` is tolerated (means the smoke test was
    re-run within the same second; the row already exists).
    """
    outcome = db_writer.insert_chunk(**kwargs)
    if outcome == db_writer.InsertOutcome.SAFETY:
        raise RuntimeError(
            f"[seed] insert_chunk returned SAFETY for "
            f"{kwargs.get('field')!r} on session "
            f"{kwargs.get('session_id')!r}: test data leaked to R2!"
        )
    print(f"[seed]   chunk {kwargs.get('field')!r:36}  -> {outcome.value}")


# ============================================================
# Seeding — 3 sessions, predictable content
# ============================================================

def seed_dataset(run: SmokeRun) -> None:
    """Seed the 3-session fixture used by scenarios 1-8.

    * Session A: 'thin blades, satisfaction=8', 3 chunks
      (session-generic, attempt-scoped, planner-only ACL).
    * Session B: 'thick blades, satisfaction=3', 1 chunk.
    * Session C: 'mismatched embedding_model', 1 chunk via direct
      SQL INSERT (bypasses :func:`db_writer.insert_chunk` so we
      can plant a non-current ``embedding_model`` string that the
      search will skip — exercises scenario #5).
    """
    print(f"[seed] Run prefix: {run.prefix}")

    # ---------------------------------------------------------
    # Session A — 'thin blades, satisfaction=8'
    # ---------------------------------------------------------
    session_a = f"{run.prefix}propeller_A"
    db_writer.upsert_session(
        session_id           = session_a,
        session_ts           = _RUN_TS_UTC,
        dc_name              = _DC_NAME,
        schema_version       = 1,
        dc_inspector_enabled = True,
    )
    _set_satisfaction(session_a, 8)
    attempt_a = db_writer.upsert_attempt(
        session_id      = session_a,
        attempt_label   = f"{run.prefix}A_001",
        schema_version  = 1,
        parameters_json = {"bladeCount": 5, "innerThickness": 2.0},
        has_geometry    = True,
        has_renders     = True,
    )
    run.seeded_attempt_ids[session_a] = attempt_a

    # Session-generic chunk: visible to all primary agents.
    _seed_chunk_or_die(
        run,
        session_id      = session_a,
        attempt_id      = None,
        agent_from      = "database_handler",
        agents_to       = list(db_writer.DEFAULT_AGENTS_TO_ACL),
        field           = "Plan",
        field_type      = "Semantic",
        question        = "What was the design plan?",
        body            = ("A thin five-blade propeller optimised for "
                           "low-drag airflow.  The user prioritised "
                           "minimal radial thickness."),
        dc_name         = _DC_NAME,
        safety_scope    = "session",
        safety_filename = "Plan.txt",
    )
    # Attempt-scoped chunk: exercises scenario #6 (attempt_specific).
    _seed_chunk_or_die(
        run,
        session_id      = session_a,
        attempt_id      = attempt_a,
        agent_from      = "dc_input_inspector",
        agents_to       = list(db_writer.DEFAULT_AGENTS_TO_ACL),
        field           = "Parameter Review",
        field_type      = "Semantic",
        question        = "Did the parameters meet the thin-blade brief?",
        body            = ("Yes.  The bladeCount=5 plus inner-thickness "
                           "of 2.0 mm produced a satisfying thin profile."),
        item_index      = 1,
        dc_name         = _DC_NAME,
        safety_scope    = "attempt_001",
        safety_filename = "Parameter Review__001.txt",
    )
    # ACL-restricted chunk: only the Planner can see it.
    # Exercises scenario #2 (ACL filter).
    _seed_chunk_or_die(
        run,
        session_id      = session_a,
        attempt_id      = None,
        agent_from      = "database_handler",
        agents_to       = ["planner"],
        field           = "Planner-only secret",
        field_type      = "Semantic",
        question        = "Internal planning notes?",
        body            = ("Confidential design strategy.  This chunk is "
                           "visible to the planner only and must NOT be "
                           "returned to other agents."),
        dc_name         = _DC_NAME,
        safety_scope    = "session",
        safety_filename = "Planner-only secret.txt",
    )
    run.seeded_session_ids.append(session_a)
    print(f"[seed] Session A ({session_a}) + attempt {attempt_a}: 3 chunks\n")

    # ---------------------------------------------------------
    # Session B — 'thick blades, satisfaction=3'
    # ---------------------------------------------------------
    session_b = f"{run.prefix}propeller_B"
    db_writer.upsert_session(
        session_id           = session_b,
        session_ts           = _RUN_TS_UTC,
        dc_name              = _DC_NAME,
        schema_version       = 1,
        dc_inspector_enabled = True,
    )
    _set_satisfaction(session_b, 3)
    attempt_b = db_writer.upsert_attempt(
        session_id      = session_b,
        attempt_label   = f"{run.prefix}B_001",
        schema_version  = 1,
        parameters_json = {"bladeCount": 3, "innerThickness": 8.0},
        has_geometry    = False,
        has_renders     = False,
    )
    run.seeded_attempt_ids[session_b] = attempt_b

    _seed_chunk_or_die(
        run,
        session_id      = session_b,
        attempt_id      = None,
        agent_from      = "database_handler",
        agents_to       = list(db_writer.DEFAULT_AGENTS_TO_ACL),
        field           = "Plan",
        field_type      = "Semantic",
        question        = "What was the design plan?",
        body            = ("A thick three-blade propeller.  The design "
                           "produced poor airflow characteristics and "
                           "did not satisfy the user."),
        dc_name         = _DC_NAME,
        safety_scope    = "session",
        safety_filename = "Plan.txt",
    )
    run.seeded_session_ids.append(session_b)
    print(f"[seed] Session B ({session_b}) + attempt {attempt_b}: 1 chunk\n")

    # ---------------------------------------------------------
    # Session C — 'mismatched embedding_model'
    # ---------------------------------------------------------
    # Direct SQL INSERT so we can plant a non-current
    # embedding_model that the search will reject (scenario #5).
    # The vector is dummy data — we never expect a real search to
    # rank this row; the only thing we check is the COUNT in
    # <search_meta skipped_due_to_model_mismatch=...>.
    session_c = f"{run.prefix}propeller_C"
    db_writer.upsert_session(
        session_id           = session_c,
        session_ts           = _RUN_TS_UTC,
        dc_name              = _DC_NAME,
        schema_version       = 1,
        dc_inspector_enabled = True,
    )
    fake_model = "old-provider/old-model/512"
    fake_vec   = [0.1] * int(workflow_settings.EMBEDDING_VECTOR_DIMS)
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chunks (
                    session_id, attempt_id, agent_from, agents_to,
                    field, field_type, question, body, item_index,
                    embedding, embedding_model, embedding_input,
                    is_error, is_empty
                )
                VALUES (
                    %(session_id)s, NULL, %(agent_from)s, %(agents_to)s,
                    %(field)s, 'Semantic', %(question)s, %(body)s, NULL,
                    %(fake_vec)s, %(fake_model)s, %(stitched)s,
                    FALSE, FALSE
                )
                """,
                {
                    "session_id":  session_c,
                    "agent_from":  "database_handler",
                    "agents_to":   list(db_writer.DEFAULT_AGENTS_TO_ACL),
                    "field":       "Plan",
                    "question":    "Plan for the mismatched-model session?",
                    "body":        ("Thin blade propeller (content similar "
                                    "to session A) but indexed with an "
                                    "older embedding model."),
                    "fake_vec":    fake_vec,
                    "fake_model":  fake_model,
                    "stitched":    "Mismatched-embedding smoke-test row.",
                },
            )
            conn.commit()
    run.seeded_session_ids.append(session_c)
    print(f"[seed] Session C ({session_c}): 1 chunk with "
          f"embedding_model={fake_model!r}\n")


# ============================================================
# Cleanup
# ============================================================

def cleanup(run: SmokeRun) -> None:
    """Delete every row this run created.  Runs from ``main()``'s
    ``finally:`` so a scenario failure mid-run still leaves no
    residue.

    ``sessions`` DELETE CASCADEs to ``chunks`` + ``dc_attempts``
    via FK.  ``rag_queries.session_id`` is set to NULL in v1
    (see Step 7 sub-decision 7-α) so we match those rows on
    ``query_text LIKE prefix%``.  Scenarios MUST prefix their
    queries with ``run.prefix`` for this to be reliable.
    """
    print(f"[cleanup] Deleting rows tagged with prefix {run.prefix}")
    try:
        with postgres_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM sessions WHERE session_id LIKE %s",
                    (f"{run.prefix}%",),
                )
                deleted_sessions = cur.rowcount
                cur.execute(
                    "DELETE FROM rag_queries WHERE query_text LIKE %s",
                    (f"{run.prefix}%",),
                )
                deleted_rag = cur.rowcount
                conn.commit()
        print(f"[cleanup] Deleted {deleted_sessions} session(s) "
              f"(CASCADE → chunks + dc_attempts) and "
              f"{deleted_rag} rag_queries row(s)")
    except Exception as exc:
        print(f"[cleanup] FAILED: {type(exc).__name__}: {exc}")


# ============================================================
# Scenarios (Phase 4D-2)
# ============================================================
# Each scenario takes the SmokeRun and registers 3-5 assertions
# via _assert(run, ...).  Failure does NOT abort the suite — the
# next scenario still runs so a single invocation surfaces every
# broken contract point.
#
# Every scenario's query string starts with run.prefix so the
# rag_queries cleanup matches via WHERE query_text LIKE prefix%.


def _preview(text: str, n: int = 200) -> str:
    """Truncate a long XML string for readable debug output."""
    if len(text) <= n:
        return text
    return text[:n] + f" ... [{len(text)} chars total]"


def scenario_1_happy_path(run: SmokeRun) -> None:
    """Query that matches Session A's thin-blade content; verify
    Session A appears in the response with the expected XML shape
    + score + best_match attribute.
    """
    print("\n--- Scenario 1: Happy path ---")
    query = f"{run.prefix}thin propeller with five blades"
    response = _database_search_impl(
        caller_agent          = "planner",
        query                 = query,
        n                     = 5,
        attempt_specific_flag = False,
        metafilters           = None,
    )
    print(f"[scenario 1] response: {_preview(response)}")

    session_a_id = f"{run.prefix}propeller_A"
    _assert(run, "<search_meta" in response,
            "Scenario 1: search_meta header present")
    _assert(run, f'<session id="{session_a_id}"' in response,
            "Scenario 1: session A appears",
            detail=f"expected session_id={session_a_id}")
    _assert(run, 'best_match="true"' in response,
            "Scenario 1: best_match attribute present")
    _assert(run, "<no_results" not in response,
            "Scenario 1: no <no_results> tag")
    _assert(run, "error=" not in response.split("\n", 1)[0],
            "Scenario 1: search_meta has no error attribute")


def scenario_2_acl_filter(run: SmokeRun) -> None:
    """Same query run twice — as ``planner`` (positive control;
    MUST see the restricted chunk) and as ``receptionist`` (ACL
    test; MUST NOT see it).  Tests §4.2 ACL pre-filter.
    """
    print("\n--- Scenario 2: ACL filter ---")
    query = f"{run.prefix}confidential planner notes design strategy"

    response_planner = _database_search_impl(
        caller_agent          = "planner",
        query                 = query,
        n                     = 5,
        attempt_specific_flag = False,
        metafilters           = None,
    )
    print(f"[scenario 2 — planner]      response: {_preview(response_planner)}")
    _assert(run, "Planner-only secret" in response_planner,
            "Scenario 2 positive: planner sees the restricted field")

    response_recep = _database_search_impl(
        caller_agent          = "receptionist",
        query                 = query,
        n                     = 5,
        attempt_specific_flag = False,
        metafilters           = None,
    )
    print(f"[scenario 2 — receptionist] response: {_preview(response_recep)}")
    _assert(run, "Planner-only secret" not in response_recep,
            "Scenario 2 ACL: receptionist does NOT see the restricted field",
            detail="ACL regression: receptionist returned planner-only content")


def scenario_3_empty_results_metafilters(run: SmokeRun) -> None:
    """Metafilter ``{"satisfaction": ">=99"}`` cannot match any row
    in the entire ``sessions`` table — the schema CHECK constraint
    enforces ``satisfaction BETWEEN 0 AND 10`` so >=99 is
    semantically impossible regardless of pre-existing data in the
    Railway DB.  Expect ``<no_results>`` with the locked §4.7
    metafilter-relax hint.
    """
    print("\n--- Scenario 3: Empty results with metafilters ---")
    query = f"{run.prefix}anything at all"
    response = _database_search_impl(
        caller_agent          = "planner",
        query                 = query,
        n                     = 5,
        attempt_specific_flag = False,
        metafilters           = {"satisfaction": ">=99"},
    )
    print(f"[scenario 3] response: {_preview(response)}")

    _assert(run, 'n_returned="0"' in response,
            "Scenario 3: n_returned=0")
    _assert(run, "<no_results" in response,
            "Scenario 3: <no_results> tag present")
    _assert(run, "may be related to the metafilters applied" in response,
            "Scenario 3: locked §4.7 metafilter-relax hint present")
    # Confirm the metafilters attribute on search_meta is non-empty
    # (proves the dict was passed through to the SQL layer).
    meta_attr_nonempty = False
    if 'metafilters="' in response:
        try:
            value = response.split('metafilters="', 1)[1].split('"', 1)[0]
            meta_attr_nonempty = value not in ("", "{}")
        except IndexError:
            pass
    _assert(run, meta_attr_nonempty,
            "Scenario 3: metafilters attribute on search_meta is non-empty")


def scenario_4_token_cap_trim(run: SmokeRun) -> None:
    """Force aggressive trim by passing ``token_cap=200``.  Expect a
    ``<truncated reason="token_limit" omitted_anchors=K>`` footer
    with K>=1.  Tests §4.5 + invariant 3.
    """
    print("\n--- Scenario 4: Token-cap trim ---")
    query = f"{run.prefix}thin propeller"
    response = _database_search_impl(
        caller_agent          = "planner",
        query                 = query,
        n                     = 5,
        attempt_specific_flag = False,
        metafilters           = None,
        token_cap             = 200,
    )
    print(f"[scenario 4] response: {_preview(response)}")

    _assert(run, '<truncated reason="token_limit"' in response,
            "Scenario 4: truncated footer present")
    # Pull omitted_anchors out of the footer.
    omitted: int | None = None
    if 'omitted_anchors="' in response:
        try:
            tail = response.split('omitted_anchors="', 1)[1]
            omitted = int(tail.split('"', 1)[0])
        except (ValueError, IndexError):
            pass
    _assert(run, omitted is not None and omitted >= 1,
            "Scenario 4: omitted_anchors >= 1",
            detail=f"got omitted={omitted}")
    _assert(run, 'token_cap="200"' in response,
            "Scenario 4: token_cap attribute matches the value passed")
    _assert(run, "<search_meta" in response,
            "Scenario 4: response still has a search_meta header")


def scenario_5_model_mismatch_skip(run: SmokeRun) -> None:
    """Unconstrained query — assert ``skipped_due_to_model_mismatch``
    is >=1 in the response, proving the second COUNT query is firing
    correctly (Session C's mismatched-model row contributes at least 1).
    """
    print("\n--- Scenario 5: Model-mismatch skip ---")
    query = f"{run.prefix}propeller design"
    response = _database_search_impl(
        caller_agent          = "planner",
        query                 = query,
        n                     = 3,
        attempt_specific_flag = False,
        metafilters           = None,
    )
    print(f"[scenario 5] response: {_preview(response)}")

    skipped: int | None = None
    if 'skipped_due_to_model_mismatch="' in response:
        try:
            tail = response.split('skipped_due_to_model_mismatch="', 1)[1]
            skipped = int(tail.split('"', 1)[0])
        except (ValueError, IndexError):
            pass
    _assert(run, skipped is not None and skipped >= 1,
            "Scenario 5: skipped_due_to_model_mismatch >= 1",
            detail=f"got skipped={skipped} — Session C's mismatched row "
                   "should be counted")


def scenario_6_attempt_specific(run: SmokeRun) -> None:
    """Run with ``attempt_specific=True``; the anchor is now an
    attempt, not a session.  Verify the ``<attempt id=...>`` element
    shape + no ``<session_generic>`` block (excluded per §4.4 when
    attempt_specific=True).
    """
    print("\n--- Scenario 6: attempt_specific=True ---")
    query = f"{run.prefix}parameter review thin blade satisfying"
    response = _database_search_impl(
        caller_agent          = "planner",
        query                 = query,
        n                     = 3,
        attempt_specific_flag = True,
        metafilters           = None,
    )
    print(f"[scenario 6] response: {_preview(response)}")

    _assert(run, 'attempt_specific="true"' in response,
            "Scenario 6: search_meta attempt_specific=true")
    # The XML emitter wraps each anchor as
    # <session id="..."><attempt id="NNN" score="..."> chunks
    # </attempt></session>.  Confirm the score lives on <attempt>.
    _assert(run, "<attempt id=" in response and " score=" in response,
            "Scenario 6: response has <attempt id=...> with score")
    _assert(run, "<session_generic>" not in response,
            "Scenario 6: no <session_generic> blocks "
            "(excluded when attempt_specific=true)")


def scenario_7_invalid_metafilter_error(run: SmokeRun) -> None:
    """Force the ``InvalidMetafilterError`` → error-XML path.  Verify
    the structured error envelope per Q-4A-10.
    """
    print("\n--- Scenario 7: Invalid metafilter error ---")
    query = f"{run.prefix}anything"
    response = _database_search_impl(
        caller_agent          = "planner",
        query                 = query,
        n                     = 3,
        attempt_specific_flag = False,
        metafilters           = {"unknown_key": 1},
    )
    print(f"[scenario 7] response: {_preview(response)}")

    _assert(run, '<search_meta error="invalid_metafilter"' in response,
            'Scenario 7: search_meta error="invalid_metafilter"')
    _assert(run, "<error>" in response and "</error>" in response,
            "Scenario 7: <error>...</error> element present")
    _assert(run, "Unknown metafilter key" in response,
            "Scenario 7: error message mentions 'Unknown metafilter key'")


def scenario_8_rag_queries_logging(run: SmokeRun) -> None:
    """SELECT ``rag_queries`` rows tagged with ``run.prefix``; verify
    count + column population + at least one error row from scenario 7
    (§8 invariant 11: every call logged, success and error alike).
    """
    print("\n--- Scenario 8: rag_queries logging ---")
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT caller_agent, n_returned, error_message,
                       embedding_model, query_text
                FROM rag_queries
                WHERE query_text LIKE %s
                ORDER BY ts DESC
                """,
                (f"{run.prefix}%",),
            )
            rows = cur.fetchall()

    total_rows   = len(rows)
    success_rows = [r for r in rows if r[2] is None]
    error_rows   = [r for r in rows if r[2] is not None]
    print(f"[scenario 8] total={total_rows}  success={len(success_rows)}  "
          f"error={len(error_rows)}")

    _assert(run, total_rows >= 6,
            "Scenario 8: at least 6 rag_queries rows logged for this run",
            detail=f"got {total_rows}")
    _assert(run, len(success_rows) >= 1,
            "Scenario 8: at least one successful call's row logged")
    _assert(run, len(error_rows) >= 1,
            "Scenario 8: at least one error row logged",
            detail="scenario 7's invalid_metafilter call should have "
                   "logged with error_message populated")
    # Spot-check column population on the first (most recent) row.
    if rows:
        agent, n_ret, err, emb_model, qt = rows[0]
        known_slugs = set(db_writer.DEFAULT_AGENTS_TO_ACL)
        _assert(run, agent in known_slugs,
                "Scenario 8: sampled row's caller_agent is a known slug",
                detail=f"got caller_agent={agent!r}")


SCENARIOS = [
    scenario_1_happy_path,
    scenario_2_acl_filter,
    scenario_3_empty_results_metafilters,
    scenario_4_token_cap_trim,
    scenario_5_model_mismatch_skip,
    scenario_6_attempt_specific,
    scenario_7_invalid_metafilter_error,
    scenario_8_rag_queries_logging,
]


# ============================================================
# Driver
# ============================================================

def main() -> int:
    print("=== database_search smoke test ===")
    print(f"Run prefix: {_RUN_PREFIX}")
    print()

    if not postgres_pool.is_enabled():
        print("ERROR: Postgres pool not enabled "
              "(DATABASE_URL / DATABASE_PUBLIC_URL not set in env / config)")
        return 1

    run = SmokeRun(prefix=_RUN_PREFIX)

    try:
        print("--- Seeding test dataset ---")
        seed_dataset(run)

        # ---------------------------------------------------------
        # Scenarios (4D-2 lands 1-4; 4D-3 will extend with 5-8).
        # Each scenario fires database_search calls and registers
        # assertions via _assert(run, ...).  Failure inside a
        # scenario does NOT abort — the next one still runs.
        # ---------------------------------------------------------
        print("--- Running scenarios ---")
        for fn in SCENARIOS:
            try:
                fn(run)
            except Exception as exc:
                msg = (f"{fn.__name__}: uncaught "
                       f"{type(exc).__name__}: {exc}")
                print(f"[scenario] FATAL — {msg}")
                run.assertions_failed += 1
                run.failures.append(msg)
        print()

        print("--- Summary ---")
        print(f"  Assertions passed: {run.assertions_passed}")
        print(f"  Assertions failed: {run.assertions_failed}")
        if run.failures:
            print("  Failures:")
            for f in run.failures:
                print(f"    - {f}")
        return 0 if run.assertions_failed == 0 else 1

    except Exception:
        print("\nFATAL during setup or run:")
        traceback.print_exc()
        return 1
    finally:
        print("\n--- Cleanup ---")
        cleanup(run)
        # Close the pool so background worker threads stop cleanly
        # at process exit (matches the other smoke_test_*.py files;
        # otherwise psycopg_pool prints "couldn't stop thread" hints).
        postgres_pool.close_pool()


if __name__ == "__main__":
    sys.exit(main())
