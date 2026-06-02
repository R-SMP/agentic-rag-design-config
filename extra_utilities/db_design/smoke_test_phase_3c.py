"""Smoke test for Phase 3C — populate_database integration helper.

Exercises ``DatabaseHandler._phase_3c_persist_chunk`` directly
against the live Railway Postgres + OpenAI API.  The helper is the
single seam at which Phase 3C's per-Q+A integration lands chunks
rows (via ``db_writer.insert_chunk``) or routes to the cascade
fast-path (via ``db_writer.save_to_safety_folder``).

Why not drive the full ``populate_database``?  That would require
mocking every chain agent's LLM + the orchestrator's routing — far
out of scope for an integration smoke test.  Hitting the helper
directly with a minimal mock ``self`` (the helper only reads
``self.session.dc_name``) covers all six new branches at a
fraction of the complexity.

Run from the repo root::

    python extra_utilities/db_design/smoke_test_phase_3c.py

Exits 0 on full pass, non-zero on any failure (with a clear error
message at the failure point).  When ``SMOKE_NO_CLEANUP`` is set
to a truthy value, the synthetic session is left in Postgres for
manual inspection.

Sub-cent OpenAI cost — only tests 1 + 2 trigger a stitch + embed
round-trip; tests 3, 4, 5, 6 are cascade / no-op / forced-failure
paths that never reach the LLM.

What gets verified (6 numbered checks)
---------------------------------------
 1. Session-scoped Semantic row (``nnn=None``, ``item_index=None``)
    → INSERT happens; chunks row's ``item_index`` is NULL (no
    forcing applied to session-scoped rows per W28).
 2. Attempt-scoped Semantic row (``nnn="001"``,
    ``item_index=None``) → INSERT happens; chunks row's
    ``item_index`` is 1 (W28 forcing — needed for the chunks
    UNIQUE constraint to engage on attempt-scoped rows).
 3. Attempt-scoped row with ``"001"`` already in
    ``cascaded_attempt_nnns`` → cascade fast-path: NO chunks row,
    safety file written to R2 (or hard-ERROR log when R2 disabled).
 4. Attempt-scoped row with NNN that is NOT in
    ``attempt_id_by_nnn`` (e.g. ``"999"``) → cascade fast-path:
    NO chunks row.
 5. ``db_writer_available=False`` → helper is a no-op: NO chunks
    row, no exception.
 6. SAFETY outcome on an identifying-Q row (monkey-patch
    ``db_writer.stitch_for_embedding`` to raise) → the helper adds
    the NNN to ``cascaded_attempt_nnns`` so subsequent sub-rows
    will fast-path on the next call.

Expected output on success::

    [pool]            is_enabled() = True
    [cleanup-pre]     wiped 0 leftover _smoke_phase3c_ sessions
    [setup]           sessions row + attempt 001 (BIGSERIAL=N) created
    [test 1]          PASS — session-scoped, item_index=NULL
    [test 2]          PASS — attempt-scoped, item_index=1 (W28 forcing)
    [test 3]          PASS — cascade fast-path, chunks count unchanged
    [test 4]          PASS — unknown NNN fast-path, chunks count unchanged
    [test 5]          PASS — db_writer_available=False is a no-op
    [test 6]          PASS — SAFETY → '002' added to cascaded_attempt_nnns
    [cleanup-post]    wiped 1 _smoke_phase3c_ sessions

    PASS - Phase 3C (_phase_3c_persist_chunk integration) verified.
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Force stdout/stderr to UTF-8 with replace-on-error so the test
# runs cleanly on Windows consoles (cp1252 default) — the `→` and
# `—` characters used in PASS/FAIL messages would otherwise raise
# UnicodeEncodeError mid-test.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass

try:
    from dotenv import load_dotenv as _load_dotenv  # type: ignore
    _load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

from agents.database_handler import db_writer  # noqa: E402
from agents.database_handler.database_handler import DatabaseHandler  # noqa: E402
from agents.shared import postgres_pool, r2_uploader  # noqa: E402


_NOW_STR = datetime.now().strftime("%Y%m%d_%H%M%S")
SMOKE_SESSION_ID = f"_smoke_phase3c_{_NOW_STR}"
SMOKE_ATTEMPT_LABEL_1 = f"{datetime.now().strftime('%Y%m%d')}_001_smoke3c"
SMOKE_ATTEMPT_LABEL_2 = f"{datetime.now().strftime('%Y%m%d')}_002_smoke3c"


class _MockDhSelf:
    """Minimal stand-in for the DH instance.

    ``_phase_3c_persist_chunk`` only reads ``self.session.dc_name``;
    no other DH machinery is touched.  Building the real DH would
    pull in the orchestrator + every chain agent's LLM client —
    overkill for this isolated helper test.
    """

    def __init__(self, dc_name: str):
        self.session = SimpleNamespace(dc_name=dc_name)


def _wipe_smoke() -> int:
    sql = (
        "DELETE FROM sessions "
        r"WHERE session_id LIKE '\_smoke\_phase3c\_%' ESCAPE '\'"
    )
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.rowcount


def _count_chunks(session_id: str, field: str | None = None) -> int:
    sql = "SELECT COUNT(*) FROM chunks WHERE session_id = %s"
    params: list = [session_id]
    if field is not None:
        sql += " AND field = %s"
        params.append(field)
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return int(cur.fetchone()[0])


def _select_chunk_item_index(session_id: str, field: str) -> int | None:
    sql = (
        "SELECT item_index FROM chunks "
        "WHERE session_id = %s AND field = %s "
        "ORDER BY id LIMIT 1"
    )
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (session_id, field))
            row = cur.fetchone()
            return row[0] if row else None


def _run_checks() -> int:
    mock_self = _MockDhSelf("propeller")

    # ----- Pool sanity --------------------------------------------
    if not postgres_pool.is_enabled():
        print("FAIL - postgres_pool.is_enabled() returned False")
        return 1
    print("[pool]            is_enabled() = True")

    # ----- Pre-cleanup --------------------------------------------
    n_pre = _wipe_smoke()
    print(
        f"[cleanup-pre]     wiped {n_pre} leftover _smoke_phase3c_ sessions"
    )

    # ----- Setup: sessions row + attempt 001 (BIGSERIAL cached) ---
    db_writer.upsert_session(
        session_id=SMOKE_SESSION_ID,
        session_ts=datetime.now(timezone.utc),
        dc_name="propeller",
        schema_version=1,
        dc_inspector_enabled=True,
        notes="Phase 3C smoke test — safe to delete",
    )
    attempt_001_pk = db_writer.upsert_attempt(
        session_id=SMOKE_SESSION_ID,
        attempt_label=SMOKE_ATTEMPT_LABEL_1,
        schema_version=1,
        parameters_json={"smoke_test": True, "bladeCount": 5.0},
    )
    print(
        f"[setup]           sessions row + attempt 001 "
        f"(BIGSERIAL={attempt_001_pk}) created"
    )

    attempt_id_by_nnn: dict[str, int] = {"001": attempt_001_pk}
    cascaded_attempt_nnns: set[str] = set()

    # ----- 1. session-scoped Semantic, item_index=None ------------
    DatabaseHandler._phase_3c_persist_chunk(
        mock_self,
        session_id=SMOKE_SESSION_ID,
        nnn=None,
        agent_key="planner",
        agents_to=[],
        field="_Smoke3C_SessionScope",
        field_type="Semantic",
        question="A session-scoped question.",
        body="An answer with substance for embedding into the chunks table.",
        item_index=None,
        is_error=False,
        is_identifying=False,
        safety_filename="_Smoke3C_SessionScope.txt",
        attempt_id_by_nnn=attempt_id_by_nnn,
        cascaded_attempt_nnns=cascaded_attempt_nnns,
        db_writer_available=True,
    )
    if _count_chunks(SMOKE_SESSION_ID, "_Smoke3C_SessionScope") != 1:
        print("FAIL - test 1: session-scoped row did not land")
        return 1
    if _select_chunk_item_index(
        SMOKE_SESSION_ID, "_Smoke3C_SessionScope"
    ) is not None:
        print("FAIL - test 1: session-scoped item_index should be NULL")
        return 1
    print(
        "[test 1]          PASS — session-scoped row landed, "
        "item_index=NULL (no forcing)"
    )

    # ----- 2. attempt-scoped Semantic, item_index forcing ---------
    DatabaseHandler._phase_3c_persist_chunk(
        mock_self,
        session_id=SMOKE_SESSION_ID,
        nnn="001",
        agent_key="planner",
        agents_to=[],
        field="_Smoke3C_AttemptScope",
        field_type="Semantic",
        question="An attempt-scoped question.",
        body="An attempt-specific answer for embedding.",
        item_index=None,  # → helper promotes to 1
        is_error=False,
        is_identifying=False,
        safety_filename="_Smoke3C_AttemptScope__001.txt",
        attempt_id_by_nnn=attempt_id_by_nnn,
        cascaded_attempt_nnns=cascaded_attempt_nnns,
        db_writer_available=True,
    )
    if _count_chunks(SMOKE_SESSION_ID, "_Smoke3C_AttemptScope") != 1:
        print("FAIL - test 2: attempt-scoped row did not land")
        return 1
    actual_idx = _select_chunk_item_index(
        SMOKE_SESSION_ID, "_Smoke3C_AttemptScope"
    )
    if actual_idx != 1:
        print(
            f"FAIL - test 2: attempt-scoped item_index should be 1 "
            f"(W28 forcing), got {actual_idx}"
        )
        return 1
    print(
        "[test 2]          PASS — attempt-scoped row landed, "
        "item_index=1 (W28 forcing applied)"
    )

    # ----- 3. NNN in cascaded set → fast-path ---------------------
    cascaded_attempt_nnns.add("001")
    n_before = _count_chunks(SMOKE_SESSION_ID)
    DatabaseHandler._phase_3c_persist_chunk(
        mock_self,
        session_id=SMOKE_SESSION_ID,
        nnn="001",
        agent_key="planner",
        agents_to=[],
        field="_Smoke3C_CascadeFastPath",
        field_type="Semantic",
        question="A cascaded question.",
        body="An answer that should NEVER reach Postgres.",
        item_index=None,
        is_error=False,
        is_identifying=False,
        safety_filename="_Smoke3C_CascadeFastPath__001.txt",
        attempt_id_by_nnn=attempt_id_by_nnn,
        cascaded_attempt_nnns=cascaded_attempt_nnns,
        db_writer_available=True,
    )
    n_after = _count_chunks(SMOKE_SESSION_ID)
    if n_after != n_before:
        print(
            f"FAIL - test 3: cascade fast-path inserted a chunks row "
            f"anyway ({n_before} → {n_after})"
        )
        return 1
    print(
        f"[test 3]          PASS — cascade fast-path: no chunks "
        f"row inserted (count unchanged at {n_after})"
    )
    cascaded_attempt_nnns.discard("001")

    # ----- 4. unknown NNN (not in cache) → fast-path --------------
    n_before = _count_chunks(SMOKE_SESSION_ID)
    DatabaseHandler._phase_3c_persist_chunk(
        mock_self,
        session_id=SMOKE_SESSION_ID,
        nnn="999",  # not in attempt_id_by_nnn
        agent_key="planner",
        agents_to=[],
        field="_Smoke3C_UnknownNNN",
        field_type="Semantic",
        question="A question about an attempt we never upserted.",
        body="An answer that should NEVER reach Postgres.",
        item_index=None,
        is_error=False,
        is_identifying=False,
        safety_filename="_Smoke3C_UnknownNNN__999.txt",
        attempt_id_by_nnn=attempt_id_by_nnn,
        cascaded_attempt_nnns=cascaded_attempt_nnns,
        db_writer_available=True,
    )
    n_after = _count_chunks(SMOKE_SESSION_ID)
    if n_after != n_before:
        print(
            f"FAIL - test 4: unknown-NNN fast-path inserted a "
            f"chunks row anyway ({n_before} → {n_after})"
        )
        return 1
    print(
        f"[test 4]          PASS — unknown NNN fast-path: no "
        f"chunks row inserted (count unchanged at {n_after})"
    )

    # ----- 5. db_writer_available=False → no-op -------------------
    n_before = _count_chunks(SMOKE_SESSION_ID)
    DatabaseHandler._phase_3c_persist_chunk(
        mock_self,
        session_id=SMOKE_SESSION_ID,
        nnn=None,
        agent_key="planner",
        agents_to=[],
        field="_Smoke3C_DbDisabled",
        field_type="Semantic",
        question="Q",
        body="A",
        item_index=None,
        is_error=False,
        is_identifying=False,
        safety_filename="_Smoke3C_DbDisabled.txt",
        attempt_id_by_nnn=attempt_id_by_nnn,
        cascaded_attempt_nnns=cascaded_attempt_nnns,
        db_writer_available=False,  # ← disabled
    )
    n_after = _count_chunks(SMOKE_SESSION_ID)
    if n_after != n_before:
        print(
            f"FAIL - test 5: db_writer_available=False still "
            f"wrote ({n_before} → {n_after})"
        )
        return 1
    print(
        "[test 5]          PASS — no-op when db_writer_available=False"
    )

    # ----- 6. SAFETY on identifying-Q → cascade set updated -------
    # Set up attempt 002 (so insert_chunk reaches the stitch step).
    attempt_002_pk = db_writer.upsert_attempt(
        session_id=SMOKE_SESSION_ID,
        attempt_label=SMOKE_ATTEMPT_LABEL_2,
        schema_version=1,
        parameters_json={"smoke_test": True},
    )
    attempt_id_by_nnn["002"] = attempt_002_pk

    original_stitch = db_writer.stitch_for_embedding

    def _failing_stitch(*args, **kwargs):
        raise db_writer.StitchError("smoke3c forced fail")

    db_writer.stitch_for_embedding = _failing_stitch
    try:
        DatabaseHandler._phase_3c_persist_chunk(
            mock_self,
            session_id=SMOKE_SESSION_ID,
            nnn="002",
            agent_key="planner",
            agents_to=[],
            field="_Smoke3C_IdentifyingQ_Fails",
            field_type="Semantic",
            question="An identifying-Q.",
            body="An answer that the helper will try to embed.",
            item_index=None,
            is_error=False,
            is_identifying=True,  # ← identifying
            safety_filename="_Smoke3C_IdentifyingQ_Fails__002.txt",
            attempt_id_by_nnn=attempt_id_by_nnn,
            cascaded_attempt_nnns=cascaded_attempt_nnns,
            db_writer_available=True,
        )
    finally:
        db_writer.stitch_for_embedding = original_stitch

    if "002" not in cascaded_attempt_nnns:
        print(
            "FAIL - test 6: SAFETY return on identifying-Q did NOT "
            "add '002' to cascaded_attempt_nnns"
        )
        return 1
    print(
        "[test 6]          PASS — SAFETY → '002' added to "
        "cascaded_attempt_nnns"
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
                n_after = _wipe_smoke()
                print(
                    f"[cleanup-post]    wiped {n_after} "
                    f"_smoke_phase3c_ sessions"
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
        print(
            "PASS - Phase 3C (_phase_3c_persist_chunk integration) "
            "verified."
        )
        if r2_uploader.is_enabled():
            print(
                "NOTE: test 3 + test 6 each upload one R2 safety "
                f"object under {SMOKE_SESSION_ID}/safety/... "
                "(intentional; remove manually if needed)."
            )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
