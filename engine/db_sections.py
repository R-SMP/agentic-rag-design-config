"""One database, one section per configurator.

A *section* is a PostgreSQL schema named after the configurator's folder
(``setups/propeller`` -> ``propeller``, ``setups/vacuum_hose_adapter`` ->
``vacuum_hose_adapter``) holding the seven tables of the v10 layout
(:data:`SCHEMA_SQL`).  The app's connections read and write the loaded
configurator's section only (``agents/shared/postgres_pool.py``): each
one's ``search_path`` is the section, then ``public``, where the two
things every section shares live -- the ``session_counter`` sequence (one
for all configurators: a session's ID names its folder in the bucket, so
two configurators must never both have an ``ID5``) and pgvector.

A configurator whose section is missing has no database, as a deploy
with none: nothing falls back to another section, nor to tables left in
``public`` (PostgreSQL itself would skip a missing schema of the
``search_path`` and read ``public.sessions``).  A section is made on
purpose -- the Database view's button, ``apply_schema.py``,
``move_tables_to_section.py`` -- never when a configurator loads.

The owner (2026-10-22): a momentary solution, to be revisited.

Takes DB-API connections (psycopg's); never opens one and never commits --
the caller's ``with`` block does.
"""

from __future__ import annotations

import re
from pathlib import Path

from psycopg import sql

SHARED = "public"
# The v10 layout's tables, parents first (the order they are created and moved in).
TABLES = ("dc_parameter_schemas", "sessions", "dc_attempts", "chunks",
          "dc_attempt_parameters", "rag_queries", "chunks_mm")
SCHEMA_SQL = (Path(__file__).resolve().parents[1] / "extra_utilities" / "db_design"
              / "database_PostgreSQL_schema_v10.sql")
_NOT_A_SECTION = re.compile(r"public|information_schema|pg_.*")


class SectionError(ValueError):
    """A section that cannot be named, made or moved into."""


def section_of(setup_dir: "Path | str") -> str:
    """The section of the configurator in *setup_dir*: its folder's name,
    lower case, with any character other than a letter, a digit or ``_``
    as ``_`` (a PostgreSQL name: at most 63 characters, not starting with a
    digit)."""
    raw = Path(setup_dir).name.lower()
    name = re.sub(r"[^a-z0-9_]", "_", raw)[:63]
    if not name or name[0].isdigit():
        name = ("s_" + name)[:63]
    if _NOT_A_SECTION.fullmatch(name):
        raise SectionError(f"a configurator folder named {raw!r} cannot have a database section "
                           f"({name!r} is PostgreSQL's own)")
    return name


def name() -> str:
    """The loaded configurator's section (``config.DC_PACK_DIR``)."""
    from engine import pack
    return section_of(pack.pack_dir())


def search_path(section: str) -> sql.Composed:
    """``SET search_path TO "<section>", public``."""
    return sql.SQL("SET search_path TO {}, {}").format(sql.Identifier(section), sql.Identifier(SHARED))


def tables_in(conn, schema: str) -> list[str]:
    """Which of the v10 tables *schema* holds, in :data:`TABLES` order."""
    with conn.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_type = 'BASE TABLE'", (schema,))
        have = {r[0] for r in cur.fetchall()}
    return [t for t in TABLES if t in have]


def ready(conn, section: str) -> bool:
    """True when *section* holds every table of the layout."""
    return len(tables_in(conn, section)) == len(TABLES)


def create(conn, section: str) -> list[str]:
    """Make *section*: the schema and the v10 tables in it (the shared
    counter and pgvector made in ``public`` when missing).  Refused when the
    schema already holds any of the tables, and on a database made before
    sections -- its tables still in ``public`` -- where an empty section
    would hide them: those are moved (:func:`move_shared_into`).  Leaves the
    connection's ``search_path`` on the section.  Returns the tables made."""
    section_of(section)                               # a name a folder could have
    have = tables_in(conn, section)
    if have:
        raise SectionError(f"the database already has a section {section!r} "
                           f"({len(have)} of its {len(TABLES)} tables)")
    if tables_in(conn, SHARED):
        raise SectionError(f"this database still keeps its tables in public, from before "
                           f"sections: move them into the section instead "
                           f"(extra_utilities/db_design/move_tables_to_section.py {section})")
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(section)))
        cur.execute(search_path(section))
        cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    made = tables_in(conn, section)
    if made != list(TABLES):
        raise SectionError(f"making the section {section!r} left {made}, not {list(TABLES)}")
    return made


def move_shared_into(conn, section: str) -> list[str]:
    """Move the layout's tables from ``public`` into *section* (a database
    made before sections: the tables, their rows, indexes and own sequences
    go; ``session_counter`` stays shared).  Refused unless ``public`` holds
    all seven and *section* none.  Returns the tables moved."""
    section_of(section)
    shared, there = tables_in(conn, SHARED), tables_in(conn, section)
    if there:
        raise SectionError(f"the section {section!r} already holds {there}")
    if shared != list(TABLES):
        missing = [t for t in TABLES if t not in shared]
        raise SectionError(f"public does not hold the whole layout (missing {missing})")
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(section)))
        for t in TABLES:
            cur.execute(sql.SQL("ALTER TABLE {}.{} SET SCHEMA {}").format(
                sql.Identifier(SHARED), sql.Identifier(t), sql.Identifier(section)))
    return list(TABLES)
