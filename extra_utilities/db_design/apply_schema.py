"""Apply a SQL schema file to a configurator's SECTION of the database
pointed at by DATABASE_URL.

Usage (from anywhere; absolute or relative paths both work):
    python extra_utilities/db_design/apply_schema.py extra_utilities/db_design/database_PostgreSQL_schema_v10.sql
    python extra_utilities/db_design/apply_schema.py <file.sql> --section vacuum_hose_adapter
    python extra_utilities/db_design/apply_schema.py <file.sql> --shared

A section is a PostgreSQL schema named after the configurator's folder
(``engine/db_sections.py``); the app reads and writes the loaded
configurator's section only.  By default the file runs in the section of
the configurator ``config.py`` loads (``DC_PACK_DIR``, else the one loaded
last, else the propeller); ``--section`` names another.  The full schema
file makes the section (refused when it is there); any other file -- a
migration -- runs with the section first on the ``search_path``.
``--shared`` runs the file as it is, in ``public``: a database made before
sections (TODO F129).

Reads DATABASE_URL from the repo-root .env via the same load_dotenv()
pattern as config.py. The whole .sql file is executed inside one
connection so CREATE EXTENSION + multiple CREATE TABLE + CREATE INDEX
statements all land in a single round-trip.

WARNING: this is not a migration tool — it just runs whatever SQL
you point it at.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(REPO_ROOT))

from engine import db_sections  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("schema", help="the .sql file")
    where = ap.add_mutually_exclusive_group()
    where.add_argument("--section", help="the section (default: the configurator config.py loads)")
    where.add_argument("--shared", action="store_true", help="run the file as it is, in public")
    args = ap.parse_args()

    schema_path = Path(args.schema).resolve()
    if not schema_path.exists():
        print(f"Schema file not found: {schema_path}", file=sys.stderr)
        return 2

    # Prefer DATABASE_PUBLIC_URL (works from a developer laptop via the
    # Railway TCP proxy). Fall back to DATABASE_URL (the in-cluster
    # internal hostname, the only one available when this script runs
    # inside Railway). Both are set side-by-side in .env for local dev.
    url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    url_source = (
        "DATABASE_PUBLIC_URL"
        if os.environ.get("DATABASE_PUBLIC_URL")
        else "DATABASE_URL"
    )
    if not url:
        print(
            f"Neither DATABASE_PUBLIC_URL nor DATABASE_URL is set in environment. "
            f"Expected to find at least one in {REPO_ROOT / '.env'}",
            file=sys.stderr,
        )
        return 2
    print(f"Using connection URL from {url_source}.")

    # Mask the password for the connection banner — only print host/db.
    try:
        host_db = url.split("@", 1)[1]
    except IndexError:
        host_db = "<unparseable url>"

    if args.shared:
        section = db_sections.SHARED
    elif args.section:
        section = db_sections.section_of(args.section)
    else:
        import config  # noqa: F401 -- DC_PACK_DIR: the configurator it loads
        section = db_sections.name()
    print(f"Applying {schema_path.name} to {host_db}, "
          + ("in public (--shared)..." if args.shared else f"section {section}..."))
    sql = schema_path.read_text(encoding="utf-8")

    with psycopg.connect(url) as conn:
        if args.shared:
            with conn.cursor() as cur:
                cur.execute(sql)
        elif schema_path == db_sections.SCHEMA_SQL.resolve():
            try:
                db_sections.create(conn, section)
            except db_sections.SectionError as exc:
                print(f"Refused: {exc}.", file=sys.stderr)
                return 1
        else:
            if not db_sections.ready(conn, section):
                print(f"Refused: the database has no section {section!r} to run "
                      f"{schema_path.name} in (make it with the schema file).", file=sys.stderr)
                return 1
            with conn.cursor() as cur:
                cur.execute(db_sections.search_path(section))
                cur.execute(sql)
        conn.commit()
    print("Schema applied.\n")

    # Verification round-trip.
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT extname, extversion FROM pg_extension "
                "WHERE extname = 'vector';"
            )
            ext_row = cur.fetchone()
            if ext_row:
                print(f"Extension vector: version {ext_row[1]} active")
            else:
                print("WARNING: pgvector extension is not active")

            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s "
                "ORDER BY table_name;", (section,)
            )
            tables = [row[0] for row in cur.fetchall()]
            print(f"\nTables in {section} ({len(tables)}):")
            for name in tables:
                print(f"  - {name}")

            cur.execute(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = %s "
                "ORDER BY indexname;", (section,)
            )
            indexes = [row[0] for row in cur.fetchall()]
            print(f"\nIndexes in {section} ({len(indexes)}):")
            for name in indexes:
                print(f"  - {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
