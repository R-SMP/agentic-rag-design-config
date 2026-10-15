"""The parameter schema in the database: table ``dc_parameter_schemas``.

Every saved session and attempt records a ``schema_version`` -- WHICH
parameter set its values belong to.  A version is a numbered set of rows
(name, min, max, unit, description), one per parameter, written once and
never changed.  The numbers are assigned here, automatically: nobody types
a version.

    the setup         dc_pack/parameters.json   (engine/parameters.py)
    the database      every version ever uploaded

A version MATCHES the setup when its rows are exactly the setup's rows (same
names, ranges, units and descriptions).  Saving needs a matching version;
the highest one is used.  When none matches, the save stops and asks for an
upload -- uploading is never automatic, only the "Upload parameter schema"
button in Workflow Settings (or ``populate_dc_parameter_schemas.py``)
does it.

An upload adds the setup as the next version (1 in an empty table) unless
the LATEST version already matches it, and marks retired the latest
version's parameters the new one no longer has.  The latest version is the
one ``database_search`` normalises against (``tools/database_search/
param_rank.py``), so an upload also makes the setup the active one.

Takes a DB-API connection (psycopg's); never opens one, never commits --
the caller's ``with`` block does.  Tested with a stand-in connection
(``extra_utilities/tests/smoke_test_parameters.py``), never the live
database.
"""

from __future__ import annotations

from engine import parameters as _parameters

TABLE = "dc_parameter_schemas"

# Shown when a save finds no matching version (web page, DH log, REPL,
# manual entry): where to click, not what went wrong inside.
UPLOAD_FIRST_MESSAGE = (
    "Upload the parameter schema first (Workflow Settings › Database)")

_SELECT_ALL_SQL = (
    f"SELECT schema_version, param_name, min_value, max_value, unit,"
    f" description, introduced_at, retired_at FROM {TABLE}"
    f" ORDER BY schema_version, param_name")
# Two uploads at once must not both take the same next number.  This mode
# conflicts with itself and with every write, but not with plain reads.
_LOCK_SQL = f"LOCK TABLE {TABLE} IN SHARE ROW EXCLUSIVE MODE"
_INSERT_SQL = (
    f"INSERT INTO {TABLE} (schema_version, param_name, min_value, max_value,"
    f" unit, description) VALUES (%s, %s, %s, %s, %s, %s)")
_RETIRE_SQL = (
    f"UPDATE {TABLE} SET retired_at = NOW() WHERE schema_version = %s"
    f" AND param_name = ANY(%s) AND retired_at IS NULL")


# ---------------------------------------------------------------------------
# Comparing
# ---------------------------------------------------------------------------

def setup_rows(spec: dict | None = None) -> list[dict]:
    """The setup's rows, in the parameters' canonical order."""
    return _parameters.db_rows(spec)


def _row_key(row: dict) -> tuple:
    # The database stores ranges as DOUBLE PRECISION and may hold NULL text.
    return (row["param_name"], float(row["min_value"]), float(row["max_value"]),
            row.get("unit") or "", row.get("description") or "")


def same_rows(a: list[dict], b: list[dict]) -> bool:
    return sorted(map(_row_key, a)) == sorted(map(_row_key, b))


def read_versions(conn) -> dict[int, list[dict]]:
    """Every version in the table: ``{version: [row, ...]}``, oldest first."""
    versions: dict[int, list[dict]] = {}
    with conn.cursor() as cur:
        cur.execute(_SELECT_ALL_SQL)
        for v, name, lo, hi, unit, desc, introduced, retired in cur.fetchall():
            versions.setdefault(int(v), []).append({
                "param_name": name, "min_value": lo, "max_value": hi,
                "unit": unit, "description": desc,
                "introduced_at": introduced, "retired_at": retired})
    return dict(sorted(versions.items()))


def matching_in(versions: dict[int, list[dict]], rows: list[dict]) -> int | None:
    """The highest version whose rows are exactly *rows*, or None."""
    found = [v for v, vr in versions.items() if same_rows(vr, rows)]
    return max(found) if found else None


def matching_version(conn, rows: list[dict] | None = None) -> int | None:
    """The version a save of the current setup records, or None (upload first)."""
    return matching_in(read_versions(conn), rows or setup_rows())


# ---------------------------------------------------------------------------
# Uploading
# ---------------------------------------------------------------------------

def plan_upload(versions: dict[int, list[dict]], rows: list[dict]) -> dict:
    """What an upload of *rows* would do to a table holding *versions*.

    ``{"action": "none", "version": latest}`` when the latest version already
    matches; otherwise ``{"action": "insert", "version": next, "previous":
    latest or None, "retire": [names of latest's rows the new one drops]}``.
    """
    latest = max(versions) if versions else None
    if latest is not None and same_rows(versions[latest], rows):
        return {"action": "none", "version": latest}
    new_names = {r["param_name"] for r in rows}
    retire = sorted(r["param_name"] for r in versions.get(latest, [])
                    if r["param_name"] not in new_names and r["retired_at"] is None)
    return {"action": "insert", "version": (latest or 0) + 1,
            "previous": latest, "retire": retire}


def upload(conn, rows: list[dict] | None = None) -> dict:
    """Upload the setup (or *rows*) as described in :func:`plan_upload`.

    Locks the table for the rest of the caller's transaction, so the version
    number read here is still the latest when the rows go in.  Returns the
    plan that was carried out.
    """
    rows = rows or setup_rows()
    with conn.cursor() as cur:
        cur.execute(_LOCK_SQL)
    plan = plan_upload(read_versions(conn), rows)
    if plan["action"] == "insert":
        with conn.cursor() as cur:
            cur.executemany(_INSERT_SQL, [
                (plan["version"], r["param_name"], r["min_value"], r["max_value"],
                 r["unit"], r["description"]) for r in rows])
            if plan["retire"]:
                cur.execute(_RETIRE_SQL, (plan["previous"], plan["retire"]))
    return plan


# ---------------------------------------------------------------------------
# What the web page shows
# ---------------------------------------------------------------------------

def status(conn, spec: dict | None = None) -> dict:
    """The setup against the database, for the Workflow Settings panel and the
    Database schema view.

    ``state`` is ``current`` (the latest version matches: nothing to do),
    ``older`` (an older version matches: saving works, but search still
    uses the latest version's ranges -- upload to make the setup current),
    or ``missing`` (no version matches: saving stops until an upload).
    """
    spec = spec or _parameters.load()
    rows = setup_rows(spec)
    versions = read_versions(conn)
    latest = max(versions) if versions else None
    match = matching_in(versions, rows)
    state = ("current" if match is not None and match == latest
             else "older" if match is not None else "missing")
    order = {n: i for i, n in enumerate(_parameters.names(spec))}
    return {
        "state": state, "latest_version": latest, "matching_version": match,
        "next_upload": plan_upload(versions, rows),
        "setup": shown_rows(rows),
        "versions": [{"version": v, "rows": shown_rows(sorted(vr, key=lambda r: (
            order.get(r["param_name"], len(order)), r["param_name"])))}
            for v, vr in sorted(versions.items(), reverse=True)],
    }


def shown_rows(rows: list[dict]) -> list[dict]:
    """*rows* as the web page gets them: JSON-safe, text never null."""
    return [{"param_name": r["param_name"], "min_value": r["min_value"],
             "max_value": r["max_value"], "unit": r.get("unit") or "",
             "description": r.get("description") or "",
             "introduced_at": _iso(r.get("introduced_at")),
             "retired_at": _iso(r.get("retired_at"))} for r in rows]


def _iso(ts) -> str | None:
    return ts.isoformat() if hasattr(ts, "isoformat") else ts


# ---------------------------------------------------------------------------
# The app's shortcut
# ---------------------------------------------------------------------------

def resolve_version() -> int | None:
    """``matching_version`` through the app's connection pool.

    Raises ``PostgresDisabledError`` when no database is configured; the
    callers check ``postgres_pool.is_enabled()`` first.  Imported lazily:
    the engine itself does not depend on the app's database layer.
    """
    from agents.shared import postgres_pool
    with postgres_pool.connection() as conn:
        return matching_version(conn)
