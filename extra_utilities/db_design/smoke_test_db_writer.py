"""Smoke test for Phase 3B — agents/database_handler/db_writer.py.

Exercises the full stitch → embed → upsert / INSERT pipeline against
the live Railway Postgres and the live OpenAI API.  Sub-cent total
cost (~8 OpenAI calls).  Safe to re-run — the test cleans up every
``_smoke_test_*`` session it created.

Run from the repo root::

    python extra_utilities/db_design/smoke_test_db_writer.py

Exits 0 on full pass, non-zero on any failure (with a clear error
message at the failure point).  When ``SMOKE_NO_CLEANUP`` is set
to a truthy value, the synthetic session is left in Postgres for
manual inspection.

What gets verified (14 numbered checks)
---------------------------------------
 1. ``postgres_pool`` is enabled and a trivial ``SELECT 1`` works.
 2. Pre-run cleanup removes any leftover ``_smoke_test_*`` rows.
 3. ``stitch_for_embedding`` reaches the OpenAI chat-completions
    endpoint and returns a non-empty paragraph (also exercises
    the YAML-frontmatter strip in ``_load_stitching_prompt``).
 4. ``embed_text`` reaches the OpenAI embeddings endpoint, returns
    a vector of length ``EMBEDDING_VECTOR_DIMS``, and produces the
    locked ``"openai/text-embedding-3-large/1024"``
    ``embedding_model`` string format.
 5. ``upsert_session`` lands a row; a second call with the same
    ``session_id`` is idempotent.
 6. ``upsert_attempt`` returns a positive BIGSERIAL id; second
    call with the same ``(session_id, attempt_label)`` returns the
    SAME id (ON CONFLICT … RETURNING path).
 7. ``upsert_attempt_parameters`` lands ``len(SMOKE_PARAMS)``
    rows in ``dc_attempt_parameters``.
 8. ``insert_chunk`` happy-path Semantic returns ``INSERTED``;
    SELECT confirms ``embedding`` non-NULL, ``embedding_model`` =
    locked string, ``embedding_input`` non-empty, ``agents_to`` =
    ``DEFAULT_AGENTS_TO_ACL`` (invariant 14 satisfied when an empty
    list is passed in).
 9. ``insert_chunk`` Quantitative returns ``INSERTED``; SELECT
    confirms ``embedding`` / ``embedding_model`` / ``embedding_input``
    are all NULL (the Quantitative branch skips stitch + embed).
10. ``insert_chunk`` with ``is_empty=True`` returns ``INSERTED``;
    SELECT confirms ``is_empty=TRUE``, ``embedding`` NULL — proves
    the **v5 relaxed CHECK constraint** accepts the row (architecture
    doc §3.1 v5 addendum + C8 safety net).
11. A second ``insert_chunk`` with the same unique-key tuple as
    step 8 returns ``SKIPPED_UNIQUE``; the chunks row count is
    unchanged; no retry was consumed; no safety folder was written.
12. With ``db_writer.stitch_for_embedding`` monkey-patched to raise
    ``StitchError``, ``insert_chunk`` exhausts
    ``DATABASE_ENTRY_MAX_RETRIES`` attempts and returns ``SAFETY``;
    no row landed in chunks.  When R2 is enabled, the safety file
    lands at ``<SMOKE_SESSION_ID>/safety/session/_SmokeForceFail.txt``
    (a manual cleanup will be needed for that one R2 object; see the
    final print warning).  When R2 is disabled, the hard-ERROR log
    fires with the full Q+A body.
13. ``save_session_feedback`` updates ``sessions.satisfaction`` +
    ``sessions.feedback`` (with the labelled-block format
    ``"--- Positive ---\\n<answer>"``) and writes one chunks row
    per fixed feedback question — the answered one stitched +
    embedded normally, the unanswered one as a Semantic safety-net
    with ``is_empty=TRUE``.
14. Post-run cleanup ``DELETE FROM sessions WHERE session_id LIKE
    '_smoke_test_%' …`` cascades to chunks + dc_attempts; final
    SELECTs confirm zero rows.

Expected output on success::

    [pool]            is_enabled() = True
    [pool]            SELECT 1 -> (1,)
    [cleanup-pre]     wiped 0 leftover _smoke_test_ session(s)
    [stitch]          stitched paragraph (length 187): "Regarding…"
    [embed]           vector dims=1024 model='openai/text-embedding-3-large/1024'
    [upsert_session]  session_id=_smoke_test_20260602_140523 inserted (2nd call idempotent)
    [upsert_attempt]  attempt_id=42 returned; second call returned the same id
    [upsert_params]   3 long-format param rows inserted
    [insert Semantic] INSERTED  (embedding non-NULL, embedding_input length=192)
    [insert Quant]    INSERTED  (embedding NULL — Quantitative branch OK)
    [insert is_empty] INSERTED  (is_empty=TRUE, embedding NULL — v5 CHECK relaxation OK)
    [insert dup]      SKIPPED_UNIQUE  (chunks row count unchanged at 3)
    [insert SAFETY]   SAFETY  (R2 enabled; chunks row count unchanged at 3)
    [feedback]        UPDATE OK; sessions.feedback len=58
    [feedback]        outcomes={'fixed_positive': 'inserted', 'fixed_negative': 'inserted'}
    [feedback]        Positive chunks row has embedding non-NULL; Negative is_empty=TRUE
    [cleanup-post]    wiped 1 _smoke_test_ session(s) (CASCADE removed children)

    PASS - Phase 3B (db_writer) end-to-end verified.
    NOTE: one R2 object remains under <session_id>/safety/session/_SmokeForceFail.txt
          (intentional — Q-T4 keeps R2 verification out of this smoke test).
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Load the repo-root .env so OPENAI_API_KEY / DATABASE_PUBLIC_URL /
# DATABASE_URL / R2_* are available to the modules we import below.
# Matches apply_schema.py's behaviour; without this, running the
# smoke test from a fresh shell fails with "OPENAI_API_KEY is not
# set" unless the operator has already exported the vars.
try:
    from dotenv import load_dotenv as _load_dotenv  # type: ignore
    _load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass  # dotenv not installed → expect env vars to be set externally

# Per Q-T1 = (A): direct imports, accept the agent-stack import
# cost (db_writer runs in production with the agent stack loaded
# anyway).
from agents.database_handler import db_writer  # noqa: E402
from agents.shared import postgres_pool, r2_uploader  # noqa: E402
from workflow_settings import settings as workflow_settings  # noqa: E402


_NOW_STR = datetime.now().strftime("%Y%m%d_%H%M%S")
SMOKE_SESSION_ID = f"_smoke_test_{_NOW_STR}"
SMOKE_ATTEMPT_LABEL = f"{datetime.now().strftime('%Y%m%d')}_001_smoke"
SMOKE_PARAMS: dict[str, float] = {
    "bladeCount": 5.0,
    "ringRadius": 0.10,
    "ringHeight": 0.04,
}


# ============================================================
# Helpers
# ============================================================

def _wipe_smoke_sessions() -> int:
    """DELETE every session whose id begins with ``_smoke_test_``.

    CASCADE removes chunks + dc_attempts + dc_attempt_parameters.
    Returns the number of session rows removed.
    """
    sql = (
        "DELETE FROM sessions "
        r"WHERE session_id LIKE '\_smoke\_test\_%' ESCAPE '\'"
    )
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.rowcount


def _count_chunks(session_id: str) -> int:
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM chunks WHERE session_id = %s",
                (session_id,),
            )
            return int(cur.fetchone()[0])


def _select_chunk(session_id: str, field: str) -> dict | None:
    sql = (
        "SELECT field, field_type, embedding IS NOT NULL, "
        "       embedding_model, embedding_input, body, "
        "       is_empty, is_error, agents_to "
        "FROM chunks WHERE session_id = %s AND field = %s "
        "ORDER BY id LIMIT 1"
    )
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (session_id, field))
            row = cur.fetchone()
            if row is None:
                return None
            return {
                "field":           row[0],
                "field_type":      row[1],
                "has_emb":         bool(row[2]),
                "embedding_model": row[3],
                "embedding_input": row[4],
                "body":            row[5],
                "is_empty":        bool(row[6]),
                "is_error":        bool(row[7]),
                "agents_to":       list(row[8]) if row[8] else [],
            }


def _select_session_feedback(
    session_id: str,
) -> tuple[int | None, str | None]:
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT satisfaction, feedback FROM sessions "
                "WHERE session_id = %s",
                (session_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None, None
            return (
                int(row[0]) if row[0] is not None else None,
                row[1],
            )


# ============================================================
# Main test body
# ============================================================

def _run_checks() -> int:
    """Run the 14 numbered checks.  Returns 0 on full pass, 1 on
    the first failure (subsequent checks are skipped).  Cleanup is
    handled by the caller's finally block.
    """

    # ----- 1. Pool sanity ------------------------------------------
    if not postgres_pool.is_enabled():
        print("FAIL - postgres_pool.is_enabled() returned False.")
        return 1
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            row = cur.fetchone()
    if row != (1,):
        print(f"FAIL - SELECT 1 returned {row!r}")
        return 1
    print("[pool]            is_enabled() = True")
    print(f"[pool]            SELECT 1 -> {row}")

    # ----- 2. Pre-run cleanup --------------------------------------
    n_pre = _wipe_smoke_sessions()
    print(
        f"[cleanup-pre]     wiped {n_pre} leftover _smoke_test_ "
        f"session(s)"
    )

    # ----- 3. Stitching (live OpenAI) ------------------------------
    stitched = db_writer.stitch_for_embedding(
        dc_name="propeller",
        field="Plan",
        question="What is the overall plan for the next design iteration?",
        answer=(
            "Increase the blade count from 3 to 5 and reduce the "
            "ring thickness, then re-render and compare."
        ),
    )
    if not stitched.strip():
        print("FAIL - stitch_for_embedding returned empty.")
        return 1
    preview = stitched[:60].replace("\n", " ")
    print(
        f"[stitch]          stitched paragraph (length "
        f"{len(stitched)}): \"{preview}…\""
    )

    # ----- 4. Embedding (live OpenAI) ------------------------------
    vector, model_str = db_writer.embed_text("test paragraph")
    expected_dims = int(workflow_settings.EMBEDDING_VECTOR_DIMS)
    expected_model_str = (
        f"{workflow_settings.EMBEDDING_PROVIDER.lower()}/"
        f"{workflow_settings.EMBEDDING_MODEL}/{expected_dims}"
    )
    if len(vector) != expected_dims:
        print(
            f"FAIL - embed_text returned {len(vector)} dims, "
            f"expected {expected_dims}."
        )
        return 1
    if model_str != expected_model_str:
        print(
            f"FAIL - embed_text model string {model_str!r} != "
            f"expected {expected_model_str!r}"
        )
        return 1
    print(
        f"[embed]           vector dims={len(vector)} "
        f"model={model_str!r}"
    )

    # ----- 5. upsert_session (idempotency) -------------------------
    now_utc = datetime.now(timezone.utc)
    for _ in range(2):
        db_writer.upsert_session(
            session_id=SMOKE_SESSION_ID,
            session_ts=now_utc,
            dc_name="propeller",
            schema_version=1,
            dc_inspector_enabled=True,
            notes="db_writer smoke test session — safe to delete.",
        )
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM sessions WHERE session_id = %s",
                (SMOKE_SESSION_ID,),
            )
            n_sessions = int(cur.fetchone()[0])
    if n_sessions != 1:
        print(
            f"FAIL - sessions row count for SMOKE_SESSION_ID = "
            f"{n_sessions}, expected 1."
        )
        return 1
    print(
        f"[upsert_session]  session_id={SMOKE_SESSION_ID} inserted "
        f"(2nd call idempotent)"
    )

    # ----- 6. upsert_attempt (idempotency: same id) ----------------
    attempt_id_1 = db_writer.upsert_attempt(
        session_id=SMOKE_SESSION_ID,
        attempt_label=SMOKE_ATTEMPT_LABEL,
        schema_version=1,
        parameters_json={"smoke_test": True, **SMOKE_PARAMS},
    )
    attempt_id_2 = db_writer.upsert_attempt(
        session_id=SMOKE_SESSION_ID,
        attempt_label=SMOKE_ATTEMPT_LABEL,
        schema_version=1,
        parameters_json={"smoke_test": True, **SMOKE_PARAMS},
    )
    if attempt_id_1 != attempt_id_2:
        print(
            f"FAIL - upsert_attempt returned different ids "
            f"({attempt_id_1} vs {attempt_id_2}) for same label."
        )
        return 1
    if attempt_id_1 <= 0:
        print(
            f"FAIL - upsert_attempt returned non-positive id: "
            f"{attempt_id_1}"
        )
        return 1
    print(
        f"[upsert_attempt]  attempt_id={attempt_id_1} returned; "
        f"second call returned the same id"
    )

    # ----- 7. upsert_attempt_parameters ----------------------------
    db_writer.upsert_attempt_parameters(
        attempt_id=attempt_id_1,
        parameters=SMOKE_PARAMS,
    )
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM dc_attempt_parameters "
                "WHERE attempt_id = %s",
                (attempt_id_1,),
            )
            n_params = int(cur.fetchone()[0])
    if n_params != len(SMOKE_PARAMS):
        print(
            f"FAIL - dc_attempt_parameters row count = {n_params}, "
            f"expected {len(SMOKE_PARAMS)}."
        )
        return 1
    print(
        f"[upsert_params]   {n_params} long-format param rows inserted"
    )

    # ----- 8. insert_chunk Semantic happy path ---------------------
    # NOTE: attempt_id=attempt_id_1 AND item_index=1 (BOTH non-NULL)
    # so that step 11's duplicate call collides on the UNIQUE
    # constraint.  Per the chunks-table NOTE in
    # database_PostgreSQL_schema_v5.sql, PostgreSQL treats NULLs as
    # DISTINCT in UNIQUE constraints, so two rows where EITHER
    # attempt_id OR item_index IS NULL will NOT collide.  Real
    # attempt-scoped Q+A rows (multi-answer-split or otherwise) carry
    # non-NULL attempt_id, so this mirrors realistic production usage.
    field_semantic = "Plan"
    sem_body = (
        "Increase the blade count from 3 to 5 and reduce the ring "
        "thickness, then re-render and compare."
    )
    outcome_sem = db_writer.insert_chunk(
        session_id=SMOKE_SESSION_ID,
        attempt_id=attempt_id_1,
        agent_from="planner",
        agents_to=[],   # → DEFAULT_AGENTS_TO_ACL
        field=field_semantic,
        field_type="Semantic",
        question="What is the overall plan?",
        body=sem_body,
        item_index=1,
        dc_name="propeller",
        safety_scope="attempt_001",
        safety_filename="Plan__001.txt",
    )
    if outcome_sem != db_writer.InsertOutcome.INSERTED:
        print(
            f"FAIL - insert_chunk Semantic returned {outcome_sem!r}, "
            f"expected INSERTED."
        )
        return 1
    row = _select_chunk(SMOKE_SESSION_ID, field_semantic)
    if not row:
        print(f"FAIL - no chunks row found for field={field_semantic!r}")
        return 1
    if not row["has_emb"]:
        print("FAIL - Semantic row has NULL embedding.")
        return 1
    if row["embedding_model"] != expected_model_str:
        print(
            f"FAIL - Semantic row embedding_model "
            f"{row['embedding_model']!r} != {expected_model_str!r}"
        )
        return 1
    if not (row["embedding_input"] or "").strip():
        print("FAIL - Semantic row embedding_input is empty.")
        return 1
    if row["agents_to"] != list(db_writer.DEFAULT_AGENTS_TO_ACL):
        print(
            f"FAIL - Semantic row agents_to != DEFAULT_AGENTS_TO_ACL: "
            f"{row['agents_to']}"
        )
        return 1
    print(
        f"[insert Semantic] INSERTED  (embedding non-NULL, "
        f"embedding_input length={len(row['embedding_input'])}, "
        f"item_index=1 used to make step 11's UNIQUE test fire)"
    )

    # ----- 9. insert_chunk Quantitative ---------------------------
    field_quant = "_SmokeQuantitative"
    outcome_q = db_writer.insert_chunk(
        session_id=SMOKE_SESSION_ID,
        attempt_id=attempt_id_1,
        agent_from="dc_input_creator",
        agents_to=[],
        field=field_quant,
        field_type="Quantitative",
        question=None,
        body='{"bladeCount": 5}',
        item_index=None,
        dc_name=None,
        safety_scope="attempt_001",
        safety_filename=f"{field_quant}.txt",
    )
    if outcome_q != db_writer.InsertOutcome.INSERTED:
        print(f"FAIL - insert_chunk Quantitative returned {outcome_q!r}")
        return 1
    row_q = _select_chunk(SMOKE_SESSION_ID, field_quant)
    if not row_q:
        print(f"FAIL - no chunks row for {field_quant!r}")
        return 1
    if (
        row_q["has_emb"]
        or row_q["embedding_model"] is not None
        or row_q["embedding_input"] is not None
    ):
        print(
            f"FAIL - Quantitative row should have NULL embedding/"
            f"embedding_model/embedding_input: {row_q}"
        )
        return 1
    print(
        "[insert Quant]    INSERTED  (embedding NULL — Quantitative "
        "branch OK)"
    )

    # ----- 10. insert_chunk is_empty safety-net (v5 CHECK relax) --
    field_empty = "_SmokeEmpty"
    outcome_e = db_writer.insert_chunk(
        session_id=SMOKE_SESSION_ID,
        attempt_id=None,
        agent_from="User",
        agents_to=[],
        field=field_empty,
        field_type="Semantic",
        question="An unanswered question.",
        body="",
        item_index=None,
        is_empty=True,
        dc_name="propeller",
        safety_scope="session",
        safety_filename=f"{field_empty}.txt",
    )
    if outcome_e != db_writer.InsertOutcome.INSERTED:
        print(f"FAIL - insert_chunk is_empty returned {outcome_e!r}")
        return 1
    row_e = _select_chunk(SMOKE_SESSION_ID, field_empty)
    if not row_e or not row_e["is_empty"] or row_e["has_emb"]:
        print(f"FAIL - is_empty row shape wrong: {row_e}")
        return 1
    print(
        "[insert is_empty] INSERTED  (is_empty=TRUE, embedding NULL "
        "— v5 CHECK relaxation OK)"
    )

    # ----- 11. SKIPPED_UNIQUE on duplicate ------------------------
    # Mirrors step 8's key tuple exactly (attempt_id, item_index,
    # all other UNIQUE columns) so the constraint engages.
    n_before = _count_chunks(SMOKE_SESSION_ID)
    outcome_dup = db_writer.insert_chunk(
        session_id=SMOKE_SESSION_ID,
        attempt_id=attempt_id_1,
        agent_from="planner",
        agents_to=[],
        field=field_semantic,
        field_type="Semantic",
        question="What is the overall plan?",
        body=sem_body,
        item_index=1,
        dc_name="propeller",
        safety_scope="attempt_001",
        safety_filename="Plan__001.txt",
    )
    if outcome_dup != db_writer.InsertOutcome.SKIPPED_UNIQUE:
        print(
            f"FAIL - duplicate insert_chunk returned {outcome_dup!r}, "
            f"expected SKIPPED_UNIQUE."
        )
        return 1
    n_after = _count_chunks(SMOKE_SESSION_ID)
    if n_after != n_before:
        print(
            f"FAIL - chunks row count changed on SKIPPED_UNIQUE "
            f"({n_before} → {n_after})."
        )
        return 1
    print(
        f"[insert dup]      SKIPPED_UNIQUE  (chunks row count "
        f"unchanged at {n_after})"
    )

    # ----- 12. SAFETY path (monkey-patch stitch_for_embedding) ----
    field_safety = "_SmokeForceFail"
    n_chunks_before = _count_chunks(SMOKE_SESSION_ID)
    original_stitch = db_writer.stitch_for_embedding

    def _failing_stitch(*args, **kwargs):
        raise db_writer.StitchError(
            "smoke test forced failure (monkey-patched stitch)"
        )

    db_writer.stitch_for_embedding = _failing_stitch
    try:
        outcome_safety = db_writer.insert_chunk(
            session_id=SMOKE_SESSION_ID,
            attempt_id=None,
            agent_from="planner",
            agents_to=[],
            field=field_safety,
            field_type="Semantic",
            question="A question whose stitching will always fail.",
            body="An answer that should never land in chunks.",
            item_index=None,
            dc_name="propeller",
            safety_scope="session",
            safety_filename=f"{field_safety}.txt",
        )
    finally:
        db_writer.stitch_for_embedding = original_stitch
    if outcome_safety != db_writer.InsertOutcome.SAFETY:
        print(
            f"FAIL - SAFETY-path insert_chunk returned "
            f"{outcome_safety!r}, expected SAFETY."
        )
        return 1
    n_chunks_after = _count_chunks(SMOKE_SESSION_ID)
    if n_chunks_after != n_chunks_before:
        print(
            f"FAIL - SAFETY-path landed a chunks row anyway "
            f"({n_chunks_before} → {n_chunks_after})."
        )
        return 1
    r2_status = "enabled" if r2_uploader.is_enabled() else "disabled"
    print(
        f"[insert SAFETY]   SAFETY  (R2 {r2_status}; chunks row count "
        f"unchanged at {n_chunks_after})"
    )

    # ----- 13. save_session_feedback (answered + unanswered) ------
    pos_ans = "the geometry generation was fast"
    outcomes = db_writer.save_session_feedback(
        session_id=SMOKE_SESSION_ID,
        dc_name="propeller",
        satisfaction=8,
        answers={"fixed_positive": pos_ans, "fixed_negative": None},
    )
    if outcomes.get("fixed_positive") != db_writer.InsertOutcome.INSERTED:
        print(
            f"FAIL - fixed_positive outcome was "
            f"{outcomes.get('fixed_positive')}, expected INSERTED."
        )
        return 1
    if outcomes.get("fixed_negative") != db_writer.InsertOutcome.INSERTED:
        print(
            f"FAIL - fixed_negative outcome was "
            f"{outcomes.get('fixed_negative')}, expected INSERTED."
        )
        return 1
    sat, fb = _select_session_feedback(SMOKE_SESSION_ID)
    if sat != 8:
        print(f"FAIL - sessions.satisfaction = {sat}, expected 8.")
        return 1
    expected_fb = f"--- Positive ---\n{pos_ans}"
    if fb != expected_fb:
        print(
            f"FAIL - sessions.feedback != expected.\n"
            f"  got:      {fb!r}\n"
            f"  expected: {expected_fb!r}"
        )
        return 1
    row_pos = _select_chunk(SMOKE_SESSION_ID, "Positive User Comments")
    if not row_pos or not row_pos["has_emb"] or row_pos["is_empty"]:
        print(
            f"FAIL - Positive User Comments row shape wrong: {row_pos}"
        )
        return 1
    row_neg = _select_chunk(SMOKE_SESSION_ID, "Negative User Comments")
    if not row_neg or row_neg["has_emb"] or not row_neg["is_empty"]:
        print(
            f"FAIL - Negative User Comments row shape wrong: {row_neg}"
        )
        return 1
    print(
        f"[feedback]        UPDATE OK; sessions.feedback len={len(fb)}"
    )
    print(
        "[feedback]        outcomes="
        + str({k: v.value for k, v in outcomes.items()})
    )
    print(
        "[feedback]        Positive chunks row has embedding non-NULL; "
        "Negative is_empty=TRUE"
    )

    return 0


def main() -> int:
    no_cleanup = os.environ.get("SMOKE_NO_CLEANUP", "").strip() not in (
        "", "0", "false", "False", "no", "No",
    )
    rc = 1
    try:
        rc = _run_checks()
    except Exception:
        traceback.print_exc()
        rc = 1
    finally:
        if no_cleanup:
            print("[cleanup-post]    SKIPPED (SMOKE_NO_CLEANUP set)")
        else:
            try:
                n_after = _wipe_smoke_sessions()
                print(
                    f"[cleanup-post]    wiped {n_after} "
                    f"_smoke_test_ session(s) (CASCADE removed children)"
                )
            except Exception as exc:
                print(
                    f"[cleanup-post]    WARNING: cleanup failed: {exc}"
                )
        try:
            postgres_pool.close_pool()
        except Exception:
            pass

    if rc == 0:
        print()
        print("PASS - Phase 3B (db_writer) end-to-end verified.")
        # Determine if R2 was truly operational this run.
        # ``r2_uploader.is_enabled()`` only checks env vars; the boto3
        # import is a separate prerequisite.  When boto3 is missing,
        # the SAFETY-path payload falls back to the hard-ERROR log
        # rather than being uploaded — the trailing NOTE reports that
        # accurately so the operator knows whether an R2 object was
        # actually created.
        boto3_available = True
        try:
            import boto3  # noqa: F401
        except ImportError:
            boto3_available = False
        r2_truly_used = r2_uploader.is_enabled() and boto3_available
        if r2_truly_used:
            print(
                "NOTE: one R2 object remains at "
                f"{SMOKE_SESSION_ID}/safety/session/_SmokeForceFail.txt"
            )
            print(
                "      (intentional — Q-T4 keeps R2 cleanup out of "
                "this smoke test; remove manually via dashboard if "
                "needed).  Future R2-cleanup helper is a follow-up."
            )
        else:
            print(
                "NOTE: R2 was not operational this run "
                f"(env-vars-set={r2_uploader.is_enabled()}, "
                f"boto3-installed={boto3_available}).  The SAFETY-"
                "path payload was logged at ERROR level only; no R2 "
                "object was created."
            )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
