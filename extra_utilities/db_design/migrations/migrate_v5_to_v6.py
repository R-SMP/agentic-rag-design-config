"""Migrate Postgres from schema v5 to v6 (Phase 3E).

Adds the ``session_counter`` SEQUENCE (architecture doc §9.10) and
seeds its current value to MAX(existing IDNNN) from the sessions
table, so the next ``nextval('session_counter')`` returns max+1
and no slug collisions occur.

Idempotent — safe to re-run.  ``CREATE SEQUENCE IF NOT EXISTS``
is a no-op when the sequence already exists; the setval re-seeds
based on the CURRENT state of the sessions table every invocation.

Run from repo root::

    python extra_utilities/db_design/migrations/migrate_v5_to_v6.py

Exits 0 on success, non-zero on failure.

When to use this script
-----------------------
- **Existing v5 deployment with live sessions** (e.g. the Railway
  DB at the time of this migration's introduction, which had 41+
  IDNNN_* sessions): RUN THIS SCRIPT.  It adds the SEQUENCE and
  seeds the counter so the next saved session starts at
  ``ID{max+1:03d}_...``.
- **Fresh deployment with empty DB**: do NOT need this script —
  applying ``database_PostgreSQL_schema_v6.sql`` directly via
  ``apply_schema.py`` includes the SEQUENCE (start = 1) by
  default.  Running this script anyway is harmless (idempotent).
"""

from __future__ import annotations

import re
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


# Matches the IDNNN_ prefix used by _resolve_session_name's
# happy-path output.  Timestamp-fallback slugs (ID_YYYY...) do
# NOT match — those carry no counter and contribute nothing to
# the SEQUENCE's seed value.
_ID_NNN_RE = re.compile(r"^ID(\d+)_")


def main() -> int:
    if not postgres_pool.is_enabled():
        print(
            "FAIL - postgres_pool not enabled.  Set "
            "DATABASE_PUBLIC_URL (local dev) or DATABASE_URL "
            "(Railway internal) in .env before re-running."
        )
        return 1

    print("[migrate-v5-v6]  starting migration...")

    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            # 1. Create the sequence (idempotent).
            cur.execute(
                "CREATE SEQUENCE IF NOT EXISTS session_counter "
                "INCREMENT 1 START 1 MINVALUE 1 "
                "NO MAXVALUE NO CYCLE"
            )
            print("[migrate-v5-v6]  CREATE SEQUENCE OK (or already existed)")

            # 2. Find MAX existing IDNNN.  Slugs not matching the
            # IDNNN_ pattern (timestamp-fallback ones, or any
            # pre-Phase-3E variants) are ignored — they don't
            # participate in the counter.
            cur.execute(
                "SELECT session_id FROM sessions "
                "WHERE session_id ~ '^ID[0-9]+_'"
            )
            max_nnn = 0
            n_scanned = 0
            for (sid,) in cur.fetchall():
                n_scanned += 1
                m = _ID_NNN_RE.match(sid)
                if m:
                    max_nnn = max(max_nnn, int(m.group(1)))
            print(
                f"[migrate-v5-v6]  scanned {n_scanned} existing "
                f"session(s); max IDNNN = {max_nnn}"
            )

            # 3. Seed the SEQUENCE.
            #    setval(name, n, is_called=true)  → next nextval returns n+1
            #    setval(name, n, is_called=false) → next nextval returns n
            if max_nnn == 0:
                cur.execute(
                    "SELECT setval('session_counter', 1, false)"
                )
                print(
                    "[migrate-v5-v6]  session_counter seeded; "
                    "next nextval will return 1"
                )
            else:
                cur.execute(
                    "SELECT setval('session_counter', %s, true)",
                    (max_nnn,),
                )
                print(
                    f"[migrate-v5-v6]  session_counter seeded to "
                    f"{max_nnn}; next nextval will return "
                    f"{max_nnn + 1}"
                )

            # 4. Verification round-trip: peek at currval AFTER
            # setval (Postgres allows currval() only after at
            # least one nextval/setval has been issued in the
            # session — which we just did).
            cur.execute("SELECT currval('session_counter')")
            (current,) = cur.fetchone()
            print(
                f"[migrate-v5-v6]  currval('session_counter') "
                f"reports {current}"
            )

    try:
        postgres_pool.close_pool()
    except Exception:
        pass

    print()
    print("PASS - migration v5 → v6 complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
