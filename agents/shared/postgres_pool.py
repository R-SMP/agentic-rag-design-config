"""PostgreSQL connection pool for the Railway Postgres backend.

The pool is **lazy** and **optional**:

* It opens on the first call to ``get_pool()``.
* If neither ``DATABASE_PUBLIC_URL`` nor ``DATABASE_URL`` is set,
  ``get_pool()`` returns ``None`` and ``connection()`` raises
  :class:`PostgresDisabledError`.  Callers that should degrade
  gracefully (e.g. dev sessions on a checkout without Postgres
  configured) check :func:`is_enabled` first.

URL resolution order:

1. ``DATABASE_PUBLIC_URL`` — preferred for local development.
   Points at the Railway TCP proxy (e.g. ``zephyr.proxy.rlwy.net``)
   which resolves from a developer laptop.
2. ``DATABASE_URL`` — Railway's auto-injected reference variable
   inside the cluster.  Points at the internal hostname
   ``postgres.railway.internal`` which does NOT resolve from outside.

Both are read from :mod:`config`, which loads them from the repo-root
``.env`` (local dev) or from Railway-injected env vars (production).

Per-connection setup: pgvector's ``register_vector`` adapter is
installed on every new connection so ``vector(1024)`` columns marshal
to/from Python lists / numpy arrays transparently.

One database, one SECTION per configurator (``engine/db_sections.py``): a
PostgreSQL schema named after the loaded configurator's folder.  There is
one pool per section, and each of its connections has ``search_path`` =
the section, then ``public`` (the shared session counter and pgvector), so
every query reads and writes the loaded configurator's tables only.  A
configurator whose section is missing has no database (:func:`is_enabled`
is False, :func:`disabled_reason` says why) until it is made
(:func:`create_section`, the Database view's button).

Usage::

    from agents.shared.postgres_pool import connection, is_enabled

    if is_enabled():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                print(cur.fetchone())

When the pool is owned by a long-running process (FastAPI),
call :func:`close_pool` at shutdown to release sockets cleanly.  In
short-lived scripts the OS reclaims them on exit and you can skip it.
"""

from __future__ import annotations

import functools
import logging
import threading
import time
from contextlib import contextmanager
from typing import Iterator, Optional

import psycopg
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

import config
from engine import db_sections

logger = logging.getLogger(__name__)


class PostgresDisabledError(RuntimeError):
    """Raised by :func:`connection` when neither DATABASE_PUBLIC_URL
    nor DATABASE_URL is configured."""


# Conservative defaults for Railway Hobby Postgres (which caps at
# ~20 simultaneous connections per database).  A single web service
# with this pool leaves ~15 connections free for psql sessions,
# helper scripts, and other replicas.  Adjust if we move to a Pro
# tier with higher caps.
_DEFAULT_MIN_SIZE = 1
_DEFAULT_MAX_SIZE = 4
_DEFAULT_TIMEOUT_SEC = 10.0

# section -> its pool
_pools: dict[str, ConnectionPool] = {}
_pool_lock = threading.Lock()
# section -> (has its tables, when checked).  A section found is remembered
# for the process; a missing one is asked again after
# _MISSING_RECHECK_SEC (made meanwhile by a script, or by the Database
# view's button in another process).
_ready: dict[str, tuple[bool, float]] = {}
_MISSING_RECHECK_SEC = 30.0
# Whether the database still keeps its tables in public, from before
# sections (seen when a section is found missing): its configurators' tables
# are moved there, not made (engine/db_sections.move_shared_into).
_shared_tables = False


def _resolve_url() -> str:
    """Return the connection URL the pool should use, or ``""``
    if Postgres is disabled -- no URL, or the active setup may not use
    the database (``database: true`` in its pack.yaml, ``engine/pack.py``).

    Prefers DATABASE_PUBLIC_URL when set (local dev / admin scripts),
    falls back to DATABASE_URL (Railway-internal in production).
    """
    url = (config.DATABASE_PUBLIC_URL or config.DATABASE_URL) or ""
    if url:
        from engine import pack
        if not pack.uses_database():
            return ""
    return url


def section() -> str:
    """The loaded configurator's database section (``engine/db_sections.py``)."""
    return db_sections.name()


def section_ready(refresh: bool = False) -> Optional[bool]:
    """Whether the loaded configurator's section holds its tables: True or
    False; None when there is no database to ask (no URL, or the setup does
    not use it) or asking failed -- an unreachable database is then
    reported by the caller's own connection, as before sections."""
    url = _resolve_url()
    if not url:
        return None
    try:
        name = section()
    except db_sections.SectionError:
        return False
    now = time.monotonic()
    seen = _ready.get(name)
    if seen and not refresh and (seen[0] or now - seen[1] < _MISSING_RECHECK_SEC):
        return seen[0]
    global _shared_tables
    try:
        with psycopg.connect(url, connect_timeout=int(_DEFAULT_TIMEOUT_SEC), autocommit=True) as conn:
            ok = db_sections.ready(conn, name)
            if not ok:
                _shared_tables = bool(db_sections.tables_in(conn, db_sections.SHARED))
    except Exception as exc:
        logger.warning("Could not check the database section %r on %s: %s",
                       name, _safe_host(url), exc)
        return None
    if not ok and (seen is None or seen[0]):
        logger.warning(
            "The database has no section %r: this configurator runs without the "
            "database until it is made (the Database view, or "
            "extra_utilities/db_design/apply_schema.py).", name)
    _ready[name] = (ok, now)
    return ok


def is_enabled() -> bool:
    """True when the loaded configurator has a database: a URL, ``database:
    true`` in its pack.yaml, and its section made.  Does NOT open the pool;
    asks the database once per section (a missing one again after
    :data:`_MISSING_RECHECK_SEC`)."""
    return bool(_resolve_url()) and section_ready() is not False


def tables_still_shared() -> bool:
    """Whether the database, when a section was last found missing, kept
    its tables in ``public`` (made before sections): they are moved into
    the section, not made anew."""
    return _shared_tables


def disabled_reason() -> str:
    """Why the loaded configurator has no database; "" when it has one."""
    if not (config.DATABASE_PUBLIC_URL or config.DATABASE_URL):
        return ("No database is configured on this deploy (DATABASE_URL / "
                "DATABASE_PUBLIC_URL are not set).")
    if not _resolve_url():
        return ("This configurator does not use the database (no "
                "database: true in its pack.yaml).")
    try:
        name = section()
    except db_sections.SectionError as exc:
        return f"This configurator cannot have a database section: {exc}."
    if section_ready() is False:
        if _shared_tables:
            return (f"The database has no section for this configurator ({name}) "
                    f"yet, so it runs without the database.  It keeps its "
                    f"tables in public, from before sections: move them into "
                    f"the section (extra_utilities/db_design/"
                    f"move_tables_to_section.py {name}).")
        return (f"The database has no section for this configurator ({name}) "
                f"yet, so it runs without the database.  Make it in the "
                f"Database view (side menu).")
    return ""


def create_section() -> dict:
    """Make the loaded configurator's section on the database
    (``engine/db_sections.create``): ``{"section", "tables"}``.  Raises
    :class:`PostgresDisabledError` when there is no database to make it
    in, ``db_sections.SectionError`` when it is there already."""
    url = _resolve_url()
    if not url:
        raise PostgresDisabledError(disabled_reason())
    name = section()
    with psycopg.connect(url, connect_timeout=int(_DEFAULT_TIMEOUT_SEC)) as conn:
        made = db_sections.create(conn, name)
        conn.commit()
    _ready[name] = (True, time.monotonic())
    logger.warning("[db] made the database section %r (%d tables) on %s",
                   name, len(made), _safe_host(url))
    return {"section": name, "tables": made}


def _configure_connection(conn: psycopg.Connection, section: Optional[str] = None) -> None:
    """Per-connection setup hook for the pool.

    Registers the pgvector type adapter so ``vector(1024)`` columns
    in the ``chunks`` table marshal to/from Python lists / numpy
    arrays transparently, and points the connection at its *section*
    (``search_path`` = the section, public).  Commits, so the connection
    goes back to the pool idle with that path kept.
    """
    register_vector(conn)
    if section:
        conn.execute(db_sections.search_path(section))
    conn.commit()


def get_pool() -> Optional[ConnectionPool]:
    """Return the loaded configurator's section's pool, opening it on
    first use.

    Returns ``None`` when the configurator has no database (no URL, no
    ``database: true``, no section).  Callers can treat this as "Postgres
    is disabled" and skip the DB write path rather than fail.
    """
    # The active setup may have been loaded in place since a pool opened
    # (engine/switch.py): one that may not use the database gets none, and
    # another one gets its own section's pool.
    if not is_enabled():
        return None
    name = section()
    pool = _pools.get(name)
    if pool is not None:
        return pool

    # Double-checked init.  ConnectionPool.__init__ + open() is not
    # cheap; serialise the first call across threads.
    with _pool_lock:
        pool = _pools.get(name)
        if pool is not None:
            return pool

        url = _resolve_url()
        if not url:
            logger.info(
                "Postgres pool not initialised: neither "
                "DATABASE_PUBLIC_URL nor DATABASE_URL is set."
            )
            return None

        try:
            pool = ConnectionPool(
                conninfo=url,
                min_size=_DEFAULT_MIN_SIZE,
                max_size=_DEFAULT_MAX_SIZE,
                open=False,
                timeout=_DEFAULT_TIMEOUT_SEC,
                kwargs={"autocommit": False},
                configure=functools.partial(_configure_connection, section=name),
                # Verify the connection is ALIVE before handing it out.
                # psycopg_pool's default is NO check, so a connection the
                # server has since closed -- Railway drops idle ones, and a
                # design session can leave the pool untouched for many
                # minutes -- is handed to the caller dead, and its FIRST
                # query fails with "consuming input failed: SSL error:
                # unexpected eof while reading".  That is what pushed
                # session 378 into the W31 timestamp fallback on
                # 2026-08-27: nextval('session_counter') was that first
                # query.  max_idle does not help, because it only trims
                # connections ABOVE min_size and min_size is 1.
                #
                # check_connection sends an EMPTY query: one round-trip, no
                # parsing.  On failure psycopg_pool discards the dead
                # connection and loops for another
                # (ConnectionPool._getconn_with_check_loop), so callers
                # never see it.
                check=ConnectionPool.check_connection,
            )
            pool.open(wait=True, timeout=_DEFAULT_TIMEOUT_SEC)
        except Exception as exc:
            logger.error(
                "Failed to open Postgres pool against %s: %s",
                _safe_host(url), exc,
            )
            raise

        _pools[name] = pool
        logger.info(
            "Postgres pool opened (min=%d, max=%d) against %s, section %s",
            _DEFAULT_MIN_SIZE, _DEFAULT_MAX_SIZE, _safe_host(url), name,
        )
        return pool


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    """Borrow a connection from the pool for the duration of the
    ``with`` block.

    The connection is returned to the pool automatically when the
    block exits (whether by success or exception).  Transactions
    auto-rollback on exception and auto-commit on clean exit
    (standard psycopg ``ConnectionPool.connection()`` behaviour).

    Raises :class:`PostgresDisabledError` when the loaded configurator
    has no database (:func:`disabled_reason`).
    """
    pool = get_pool()
    if pool is None:
        raise PostgresDisabledError(disabled_reason() or "No database.")
    with pool.connection() as conn:
        yield conn


def close_pool() -> None:
    """Close every section's pool at process shutdown.  Safe to call when
    none was opened — it is a no-op in that case."""
    with _pool_lock:
        pools = list(_pools.items())
        _pools.clear()
        _ready.clear()
        for name, pool in pools:
            try:
                pool.close()
            except Exception:                                       # noqa: BLE001
                logger.exception("Closing the pool of section %s failed", name)
        if pools:
            logger.info("Postgres pool(s) closed: %s", ", ".join(n for n, _p in pools))


def _safe_host(url: str) -> str:
    """Return ``host:port/db`` from a connection URL, hiding the
    password.  Used only for log lines so credentials never appear
    in logs / tracebacks."""
    try:
        return url.split("@", 1)[1]
    except IndexError:
        return "<unparseable url>"
