"""Upload the parameter schema from the command line -- the FALLBACK for the
"Upload parameter schema" button (Workflow Settings > Database).

Both run the same code, ``engine/parameter_schema.py``, on the same data,
``setups/<setup>/parameters.json``; nothing is hard-coded here.  The upload adds the
setup's parameters to table ``dc_parameter_schemas`` as the next version
(1 in an empty table), or does nothing when the latest version already
matches, and marks retired the latest version's parameters the new one no
longer has.  Rows are never changed or deleted.  Version numbers are
assigned automatically.

Usage (from the repo root):
    py -3.13 extra_utilities/db_design/populate_dc_parameter_schemas.py
    py -3.13 extra_utilities/db_design/populate_dc_parameter_schemas.py --dry-run

``--dry-run`` reports what an upload would do and writes nothing.

The upload goes to the configurator's SECTION of the database
(``engine/db_sections.py``): the one ``config.py`` loads (``DC_PACK_DIR``,
else the one loaded last, else the propeller).  A missing section is
refused -- make it first (``apply_schema.py`` or the Database view).

Reads DATABASE_PUBLIC_URL (preferred for local dev) or DATABASE_URL, which
``config.py`` loads from the repo-root .env.

The versions already in a database stay as they are: the live database keeps
version 1 (17 parameters, ``impellerHeight`` retired) and version 2 (16
parameters), which this script once seeded by hand.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import psycopg  # noqa: E402

import config  # noqa: E402
from engine import db_sections, parameter_schema, parameters  # noqa: E402


def _print_version(version: int, rows: list[dict]) -> None:
    print(f"Version {version}:")
    print(f"  {'param_name':22s} {'min':>8s}   {'max':>8s}   {'unit':<22s} description")
    print(f"  {'-' * 22} {'-' * 8}   {'-' * 8}   {'-' * 22} {'-' * 40}")
    for r in rows:
        marker = "  (retired)" if r["retired_at"] else ""
        print(f"  {r['param_name']:22s} {r['min_value']:>8}   {r['max_value']:>8}   "
              f"{r['unit']:22s} {r['description'][:40]}{marker}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="report what an upload would do; write nothing")
    args = ap.parse_args()

    url = config.DATABASE_PUBLIC_URL or config.DATABASE_URL
    source = "DATABASE_PUBLIC_URL" if config.DATABASE_PUBLIC_URL else "DATABASE_URL"
    if not url:
        print(f"Neither DATABASE_PUBLIC_URL nor DATABASE_URL is set; expected "
              f"at least one in {REPO_ROOT / '.env'}", file=sys.stderr)
        return 2
    try:
        spec = parameters.load()
    except parameters.ParameterSpecError as exc:
        print(exc, file=sys.stderr)
        return 2
    rows = parameter_schema.setup_rows(spec)
    host_db = url.split("@", 1)[1] if "@" in url else "<unparseable url>"
    section = db_sections.name()
    print(f"Using connection URL from {source}: {host_db}, section {section}")
    print(f"Setup: {len(rows)} parameters from {parameters.spec_path()}")

    with psycopg.connect(url) as conn:
        if not db_sections.ready(conn, section):
            print(f"The database has no section {section!r}: make it first "
                  f"(apply_schema.py, or the Database view).", file=sys.stderr)
            return 1
        conn.execute(db_sections.search_path(section))
        conn.commit()                 # kept by the dry run's rollback below
        if args.dry_run:
            plan = parameter_schema.plan_upload(
                parameter_schema.read_versions(conn, parameter_schema.typed(rows)), rows)
            conn.rollback()
        else:
            plan = parameter_schema.upload(conn, rows)
            conn.commit()
        state = parameter_schema.status(conn, spec)

    verb = "would" if args.dry_run else "did"
    if plan["action"] == "none":
        print(f"Nothing to upload: version {plan['version']} already matches.")
    else:
        print(f"Upload {verb} add version {plan['version']}; retired from "
              f"version {plan['previous']}: {', '.join(plan['retire']) or 'none'}.")
    print(f"State: {state['state']} (latest version {state['latest_version']}, "
          f"matching version {state['matching_version']})")
    print()
    for v in state["versions"]:
        _print_version(v["version"], v["rows"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
