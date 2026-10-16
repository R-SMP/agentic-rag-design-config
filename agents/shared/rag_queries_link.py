"""Give every ``rag_queries`` row the id of the session that made the call.

A live session has no database id yet: its ``IDNNN_<date>_<time>`` name is
minted only when the session is first NAMED -- a log snapshot (the Save LOG
button, or the end of a Sessions Queue run), a Database Handler save, or End
Session.  So each RAG call still inserts its row straight away (a crash loses
nothing) and the row's id is remembered here; every naming event then stamps
the remembered rows that do not carry the name yet.  The name never changes
within a session (it is cached on the Session), so a snapshot followed by a
save stamps the same id, and only the rows added in between are new.

Two columns, two meanings (schema v9):

* ``run_session_id`` -- no foreign key.  The session's name, for EVERY
  session, saved or not.  Set by :func:`stamp`.
* ``session_id`` -- foreign key to ``sessions``.  Set only when the session is
  saved, by :func:`link_saved`, once the ``sessions`` row exists.

One process serves one session at a time (W13), so the module-level list IS
the current session's list; :func:`reset` empties it when a session starts or
ends.  Everything here is best-effort: a failure is logged and never breaks
the RAG call, the snapshot or the save that triggered it.
"""

from __future__ import annotations

import logging
import threading

from agents.shared import postgres_pool

logger = logging.getLogger("mas_agent")

_LOCK = threading.Lock()
_ROW_IDS: list[int] = []


def remember(row_id) -> None:
    """Record the id of a ``rag_queries`` row the current session inserted."""
    if row_id is None:
        return
    with _LOCK:
        _ROW_IDS.append(int(row_id))


def has_rows() -> bool:
    """True when the current session has logged at least one RAG call."""
    with _LOCK:
        return bool(_ROW_IDS)


def reset() -> None:
    """Forget the remembered rows (call when a session starts or ends)."""
    with _LOCK:
        _ROW_IDS.clear()


def stamp(session_name: str | None) -> int:
    """Set ``run_session_id`` on this session's rows that do not have it yet.

    Returns the number of rows stamped (0 on any failure).
    """
    with _LOCK:
        ids = list(_ROW_IDS)
    if not ids or not session_name or not postgres_pool.is_enabled():
        return 0
    try:
        with postgres_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE rag_queries SET run_session_id = %s "
                    "WHERE id = ANY(%s) AND run_session_id IS NULL",
                    (session_name, ids),
                )
                stamped = cur.rowcount
    except Exception as exc:  # noqa: BLE001 — best-effort by contract
        logger.warning(
            f"[rag_queries] stamping run_session_id={session_name} failed "
            f"(best-effort): {type(exc).__name__}: {exc}"
        )
        return 0
    logger.info(
        f"[rag_queries] stamped {stamped} of {len(ids)} row(s) "
        f"with run_session_id={session_name}"
    )
    return stamped


def link_saved(session_name: str | None) -> int:
    """Fill the ``session_id`` foreign key on the rows stamped with *session_name*.

    Call only after the ``sessions`` row exists (the Database Handler's
    ``upsert_session``).  Returns the number of rows linked (0 on failure).
    """
    if not session_name or not postgres_pool.is_enabled():
        return 0
    try:
        with postgres_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE rag_queries SET session_id = %s "
                    "WHERE run_session_id = %s AND session_id IS NULL",
                    (session_name, session_name),
                )
                linked = cur.rowcount
    except Exception as exc:  # noqa: BLE001 — best-effort by contract
        logger.warning(
            f"[rag_queries] linking session_id={session_name} failed "
            f"(best-effort): {type(exc).__name__}: {exc}"
        )
        return 0
    logger.info(f"[rag_queries] linked {linked} row(s) to saved session {session_name}")
    return linked
