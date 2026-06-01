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

Usage::

    from agents.shared.postgres_pool import connection, is_enabled

    if is_enabled():
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                print(cur.fetchone())

When the pool is owned by a long-running process (FastAPI, Streamlit),
call :func:`close_pool` at shutdown to release sockets cleanly.  In
short-lived scripts the OS reclaims them on exit and you can skip it.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Iterator, Optional

import psycopg
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

import config

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

_pool: Optional[ConnectionPool] = None
_pool_lock = threading.Lock()


def _resolve_url() -> str:
    """Return the connection URL the pool should use, or ``""``
    if Postgres is disabled.

    Prefers DATABASE_PUBLIC_URL when set (local dev / admin scripts),
    falls back to DATABASE_URL (Railway-internal in production).
    """
    return (config.DATABASE_PUBLIC_URL or config.DATABASE_URL) or ""


def is_enabled() -> bool:
    """True iff a Postgres URL is configured.  Cheap; does NOT open
    the pool."""
    return bool(_resolve_url())


def _configure_connection(conn: psycopg.Connection) -> None:
    """Per-connection setup hook for the pool.

    Registers the pgvector type adapter so ``vector(1024)`` columns
    in the ``chunks`` table marshal to/from Python lists / numpy
    arrays transparently.
    """
    register_vector(conn)


def get_pool() -> Optional[ConnectionPool]:
    """Return the process-wide pool, opening it on first use.

    Returns ``None`` when no Postgres URL is configured.  Callers can
    treat this as "Postgres is disabled" and skip the DB write path
    rather than fail.
    """
    global _pool
    if _pool is not None:
        return _pool

    # Double-checked init.  ConnectionPool.__init__ + open() is not
    # cheap; serialise the first call across threads.
    with _pool_lock:
        if _pool is not None:
            return _pool

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
                configure=_configure_connection,
            )
            pool.open(wait=True, timeout=_DEFAULT_TIMEOUT_SEC)
        except Exception as exc:
            logger.error(
                "Failed to open Postgres pool against %s: %s",
                _safe_host(url), exc,
            )
            raise

        _pool = pool
        logger.info(
            "Postgres pool opened (min=%d, max=%d) against %s",
            _DEFAULT_MIN_SIZE, _DEFAULT_MAX_SIZE, _safe_host(url),
        )
        return _pool


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    """Borrow a connection from the pool for the duration of the
    ``with`` block.

    The connection is returned to the pool automatically when the
    block exits (whether by success or exception).  Transactions
    auto-rollback on exception and auto-commit on clean exit
    (standard psycopg ``ConnectionPool.connection()`` behaviour).

    Raises :class:`PostgresDisabledError` when Postgres is not
    configured.
    """
    pool = get_pool()
    if pool is None:
        raise PostgresDisabledError(
            "No Postgres URL configured.  Set DATABASE_PUBLIC_URL "
            "(local dev) or DATABASE_URL (Railway internal) in .env."
        )
    with pool.connection() as conn:
        yield conn


def close_pool() -> None:
    """Close the pool at process shutdown.  Safe to call when the
    pool was never opened — it is a no-op in that case."""
    global _pool
    with _pool_lock:
        if _pool is None:
            return
        try:
            _pool.close()
        finally:
            _pool = None
        logger.info("Postgres pool closed.")


def _safe_host(url: str) -> str:
    """Return ``host:port/db`` from a connection URL, hiding the
    password.  Used only for log lines so credentials never appear
    in logs / tracebacks."""
    try:
        return url.split("@", 1)[1]
    except IndexError:
        return "<unparseable url>"
