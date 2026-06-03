"""Migrate Postgres from schema v6 to v7 (Phase 5B).

Generalises the ``rag_queries`` table from a database_search-only
log to a logging surface that also records ``retrieve_user_inputs``
and ``retrieve_attempt`` tool calls (architecture doc §3.4 + the
Phase 5B notes).

Three idempotent column-level changes plus one index:

  * ``ADD COLUMN tool_name TEXT NOT NULL DEFAULT 'database_search'``
    — identifies which RAG tool produced the row.  The DEFAULT
    backfills existing rows to ``'database_search'`` so the
    historical interpretation is preserved.
  * ``ADD COLUMN images_flag BOOLEAN`` (nullable) — the retrieve_*
    images_flag argument.  NULL for database_search rows.
  * ``ALTER COLUMN attempt_specific DROP NOT NULL`` — retrieve_*
    tools have no attempt_specific concept and pass NULL.
    database_search still always supplies a value.
  * ``CREATE INDEX idx_rag_queries_tool_name`` — supports
    per-tool analytics queries.

All four statements are written with ``IF NOT EXISTS`` (or the
ALTER's natural idempotence) so re-running this script is a no-op.

Run from repo root::

    python extra_utilities/db_design/migrations/migrate_v6_to_v7.py

Exits 0 on success, non-zero on failure.

When to use this script
-----------------------
- **Existing v6 deployment**: RUN THIS SCRIPT.  It adds the three
  new ``rag_queries`` columns + the index without touching any
  existing rows.
- **Fresh deployment with empty DB**: do NOT need this script —
  applying ``database_PostgreSQL_schema_v7.sql`` directly via
  ``apply_schema.py`` already includes the new columns and index.
  Running this script anyway is harmless (idempotent).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Force stdout/stderr to UTF-8 with replace-on-error so the
# migration script runs cleanly on Windows consoles (cp1252
# default).  Otherwise an arrow character in a status message
# would UnicodeEncodeError.
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

from agents.shared import postgres_pool  # noqa: E402


def main() -> int:
    if not postgres_pool.is_enabled():
        print(
            "FAIL - postgres_pool not enabled.  Set "
            "DATABASE_PUBLIC_URL (local dev) or DATABASE_URL "
            "(Railway internal) in .env before re-running."
        )
        return 1

    print("[migrate-v6-v7]  starting migration...")

    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            # 1. tool_name column.  Idempotent via IF NOT EXISTS;
            #    DEFAULT 'database_search' backfills existing rows.
            cur.execute(
                "ALTER TABLE rag_queries "
                "ADD COLUMN IF NOT EXISTS tool_name TEXT NOT NULL "
                "DEFAULT 'database_search'"
            )
            print("[migrate-v6-v7]  ADD COLUMN tool_name OK")

            # 2. images_flag column.  Nullable; NULL on every
            #    existing row (no DEFAULT needed).
            cur.execute(
                "ALTER TABLE rag_queries "
                "ADD COLUMN IF NOT EXISTS images_flag BOOLEAN"
            )
            print("[migrate-v6-v7]  ADD COLUMN images_flag OK")

            # 3. attempt_specific → nullable.  ALTER ... DROP NOT
            #    NULL is naturally idempotent (running on an already-
            #    nullable column is a no-op).
            cur.execute(
                "ALTER TABLE rag_queries "
                "ALTER COLUMN attempt_specific DROP NOT NULL"
            )
            print("[migrate-v6-v7]  DROP NOT NULL on attempt_specific OK")

            # 4. Index on tool_name for per-tool analytics.
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_rag_queries_tool_name "
                "ON rag_queries (tool_name)"
            )
            print("[migrate-v6-v7]  CREATE INDEX idx_rag_queries_tool_name OK")

            # 5. Verification: confirm the four expected columns exist
            #    with the expected nullability via information_schema.
            cur.execute(
                "SELECT column_name, is_nullable, data_type "
                "FROM information_schema.columns "
                "WHERE table_name = 'rag_queries' "
                "  AND column_name IN ('tool_name', 'images_flag', "
                "                      'attempt_specific') "
                "ORDER BY column_name"
            )
            rows = cur.fetchall()
            print("[migrate-v6-v7]  verification — column states:")
            for name, is_nullable, data_type in rows:
                print(
                    f"[migrate-v6-v7]    {name:<20} "
                    f"is_nullable={is_nullable:<3}  type={data_type}"
                )

    try:
        postgres_pool.close_pool()
    except Exception:
        pass

    print()
    print("PASS - migration v6 → v7 complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
