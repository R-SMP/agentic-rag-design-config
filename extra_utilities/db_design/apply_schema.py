"""Apply a SQL schema file to the database pointed at by DATABASE_URL.

Usage (from anywhere; absolute or relative paths both work):
    python extra_utilities/db_design/apply_schema.py extra_utilities/db_design/database_PostgreSQL_schema_v4.sql

Reads DATABASE_URL from the repo-root .env via the same load_dotenv()
pattern as config.py. The whole .sql file is executed inside one
autocommit connection so CREATE EXTENSION + multiple CREATE TABLE +
CREATE INDEX statements all land in a single round-trip.

WARNING: this is not a migration tool — it just runs whatever SQL
you point it at. Re-running with the same v4.sql will fail with
"relation already exists" because CREATE TABLE is not idempotent.
For a clean re-apply on a test DB, DROP TABLE CASCADE first.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(REPO_ROOT / ".env")


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path/to/schema.sql>", file=sys.stderr)
        return 2

    schema_path = Path(sys.argv[1]).resolve()
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

    print(f"Applying {schema_path.name} to {host_db}...")
    sql = schema_path.read_text(encoding="utf-8")

    with psycopg.connect(url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
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
                "WHERE table_schema = 'public' "
                "ORDER BY table_name;"
            )
            tables = [row[0] for row in cur.fetchall()]
            print(f"\nTables in public schema ({len(tables)}):")
            for name in tables:
                print(f"  - {name}")

            cur.execute(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' "
                "ORDER BY indexname;"
            )
            indexes = [row[0] for row in cur.fetchall()]
            print(f"\nIndexes in public schema ({len(indexes)}):")
            for name in indexes:
                print(f"  - {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
