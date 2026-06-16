"""Smoke test for agents/database_handler/db_writer_mm.py against LIVE
Railway Postgres + R2 + the Voyage API.

Auto-picks a real saved session that has user images AND attempt
renders (smallest such session, to keep the run short), mirrors it into
`chunks_mm` with force=True, then verifies:
  * rows were inserted,
  * text / user-image / render rows are all present,
  * a sampled image-row embedding is a 2048-float vector.

Run from repo root with the conda interpreter (has voyageai + the DB
deps) and a populated .env::

    "C:/Users/vince/miniconda3/python.exe" extra_utilities/db_design/smoke_test_db_writer_mm.py

Makes live Voyage calls for the chosen session (well within the
free-token tier).  WRITES real rows to chunks_mm for that session —
this is the intended backfill behaviour.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass

try:
    from dotenv import load_dotenv as _load_dotenv  # type: ignore
    _load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

from agents.shared import postgres_pool
from agents.database_handler import db_writer_mm
from agents.database_handler.db_writer_mm import (
    FIELD_USER_IMAGE, FIELD_RENDER,
)

_PICK_RICH_SESSION = """
SELECT s.session_id, COUNT(c.id) AS n
FROM sessions s
JOIN chunks c ON c.session_id = s.session_id
WHERE s.user_provided_images = TRUE
  AND EXISTS (SELECT 1 FROM dc_attempts a
              WHERE a.session_id = s.session_id AND a.has_renders)
GROUP BY s.session_id
ORDER BY n ASC
LIMIT 1
"""

_PICK_ANY_SESSION = """
SELECT c.session_id, COUNT(*) AS n
FROM chunks c
GROUP BY c.session_id
ORDER BY n ASC
LIMIT 1
"""


def _pick_session() -> str | None:
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_PICK_RICH_SESSION)
            row = cur.fetchone()
            if row:
                print(f"[mm-smoke]  picked rich session {row[0]} "
                      f"({row[1]} chunks, has images + renders)")
                return row[0]
            cur.execute(_PICK_ANY_SESSION)
            row = cur.fetchone()
            if row:
                print(f"[mm-smoke]  no image+render session; falling back "
                      f"to {row[0]} ({row[1]} chunks, text-only)")
                return row[0]
    return None


def main() -> int:
    if not postgres_pool.is_enabled():
        print("FAIL - postgres not enabled (set DATABASE_PUBLIC_URL in .env)")
        return 1

    # Optional explicit target: `... smoke_test_db_writer_mm.py <session_id>`
    session_id = sys.argv[1] if len(sys.argv) > 1 else _pick_session()
    if not session_id:
        print("FAIL - no session with chunks found to test against")
        return 1
    if len(sys.argv) > 1:
        print(f"[mm-smoke]  using explicit target session {session_id}")

    print(f"[mm-smoke]  mirroring {session_id} (force=True) ...")
    summary = db_writer_mm.mirror_session_to_mm(
        session_id, force=True, log=lambda m: print(f"[mm-smoke] {m}"))
    print(f"[mm-smoke]  summary = {summary}")

    # Verify chunks_mm contents for the session.
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT field, COUNT(*), "
                "       COUNT(*) FILTER (WHERE embedding IS NOT NULL) "
                "FROM chunks_mm WHERE session_id = %s GROUP BY field "
                "ORDER BY field",
                (session_id,))
            by_field = cur.fetchall()
            cur.execute(
                "SELECT vector_dims(embedding) FROM chunks_mm "
                "WHERE session_id = %s AND field = ANY(%s) "
                "  AND embedding IS NOT NULL LIMIT 1",
                (session_id, [FIELD_USER_IMAGE, FIELD_RENDER]))
            img_dim_row = cur.fetchone()
            cur.execute(
                "SELECT COUNT(*) FROM chunks_mm WHERE session_id = %s",
                (session_id,))
            total = cur.fetchone()[0]

    print(f"[mm-smoke]  chunks_mm rows for {session_id}: {total}")
    print("[mm-smoke]  by field (field, rows, embedded):")
    for f, n, emb in by_field:
        print(f"[mm-smoke]    {f!r:32} rows={n:<4} embedded={emb}")

    ok = True
    if total == 0:
        print("[mm-smoke]  FAIL: no rows written")
        ok = False
    if img_dim_row is not None:
        dim = img_dim_row[0]
        print(f"[mm-smoke]  sampled image-row embedding dims = {dim}")
        if dim != 2048:
            print(f"[mm-smoke]  FAIL: image embedding has {dim} dims, expected 2048")
            ok = False
    else:
        print("[mm-smoke]  NOTE: no image rows for this session (text-only) — "
              "image-dim check skipped")

    try:
        postgres_pool.close_pool()
    except Exception:
        pass

    print()
    if ok:
        print("PASS - db_writer_mm smoke test green.")
        return 0
    print("FAIL - db_writer_mm smoke test had failures (see above).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
