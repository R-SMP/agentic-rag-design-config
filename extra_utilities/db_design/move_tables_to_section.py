"""Move a database's tables from ``public`` into a configurator's section.

A database made before sections (``engine/db_sections.py``) keeps the
seven tables in ``public``; the app now reads and writes a section named
after the loaded configurator's folder, so such a database looks empty to
it until its tables are moved.  This moves them -- rows, indexes and the
tables' own sequences -- into the section, in one transaction.  The shared
``session_counter`` stays in ``public``, so session IDs carry on.

Usage (from the repo root):
    py -3.13 extra_utilities/db_design/move_tables_to_section.py propeller --dry-run
    py -3.13 extra_utilities/db_design/move_tables_to_section.py propeller

Refused unless ``public`` holds all seven tables and the section none.
Reads DATABASE_PUBLIC_URL (preferred) or DATABASE_URL, as ``config.py``
loads them.  Never deletes a row.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

import config  # noqa: E402
from engine import db_sections  # noqa: E402


def _counts(conn, schema: str) -> dict[str, int]:
    out = {}
    with conn.cursor() as cur:
        for t in db_sections.tables_in(conn, schema):
            cur.execute(sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier(schema), sql.Identifier(t)))
            out[t] = cur.fetchone()[0]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("section", help="the configurator's section, e.g. propeller")
    ap.add_argument("--dry-run", action="store_true", help="say what would move; move nothing")
    args = ap.parse_args()

    url = config.DATABASE_PUBLIC_URL or config.DATABASE_URL
    if not url:
        print("Neither DATABASE_PUBLIC_URL nor DATABASE_URL is set.", file=sys.stderr)
        return 2
    section = db_sections.section_of(args.section)
    host_db = url.split("@", 1)[1] if "@" in url else "<unparseable url>"
    print(f"Database {host_db}: public -> section {section}")

    with psycopg.connect(url) as conn:
        before = _counts(conn, db_sections.SHARED)
        print(f"public holds: {before or 'none of the tables'}")
        print(f"{section} holds: {db_sections.tables_in(conn, section) or 'none of the tables'}")
        if args.dry_run:
            conn.rollback()
            return 0
        try:
            moved = db_sections.move_shared_into(conn, section)
        except db_sections.SectionError as exc:
            conn.rollback()
            print(f"Refused: {exc}.", file=sys.stderr)
            return 1
        after = _counts(conn, section)
        if after != before:
            conn.rollback()
            print(f"Refused: the rows moved do not match ({after} after, {before} before); "
                  f"nothing was moved.", file=sys.stderr)
            return 1
        conn.commit()
    print(f"Moved {len(moved)} tables into {section}, rows unchanged: {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
