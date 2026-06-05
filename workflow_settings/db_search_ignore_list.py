"""Sessions to IGNORE during database searches and retrievals.

Persistent ignore list consulted by:

* ``tools.database_search`` — adds ``AND session_id <> ALL(%(_ignore_list)s)``
  to the WHERE clause of both the vector-query and the
  session-query, so ignored sessions never appear in
  ``<search_meta/>`` results.
* ``tools.retrieve_user_inputs`` — when a requested
  ``session_id`` is on the list, returns
  ``<session id="..." status="ignored"/>`` (skips the R2 fetch
  entirely).
* ``tools.retrieve_attempt`` — when a requested attempt belongs
  to an ignored session, returns
  ``<attempt id="..." status="ignored"/>`` (skips R2 + Postgres
  parameter fetch entirely).

The file is a flat JSON array of session_id strings.  Mutated
via the Database admin view in the web UI (the existing
password-gated panel — see
``web_app:_check_db_password`` and the ``/api/db_admin/...``
endpoints).  Single-user (W13/O9) — no per-user state.

Storage: ``db_search_ignore_list.json`` alongside other
``workflow_settings/`` JSON.  Writes are atomic (tmp-file +
rename) with a process-level lock to serialise concurrent
writes.  Reads are fresh on every call — changes take effect
immediately on the next retrieval call, no session restart
needed.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path


_PATH = Path(__file__).parent / "db_search_ignore_list.json"
_LOCK = threading.Lock()


# Canonical session-ID shape used by ``agents.loader._resolve_session_name``
# on the Postgres-SEQUENCE happy path.  The Database admin view's
# write endpoint validates incoming session_ids against this regex
# (see web_app.api_db_admin_ignore_write).  Fallback-shaped IDs are
# NOT accepted by the strict-validation path — relax this regex
# (or add a permissive alternative) if you ever need to ignore a
# fallback-shape session.
SESSION_ID_PATTERN = re.compile(r"^ID\d+_\d{8}_\d{6}$")


def get_ignore_list() -> list[str]:
    """Return the current ignore list (sorted, de-duplicated).

    Returns an empty list on any failure (missing file, parse
    error, wrong type) so callers fall back to "no filter" cleanly
    — a malformed ignore-list file must never break a
    ``database_search`` call.
    """
    try:
        if not _PATH.is_file():
            return []
        data = json.loads(_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return sorted({
        str(x).strip()
        for x in data
        if isinstance(x, str) and x.strip()
    })


def is_ignored(session_id: str) -> bool:
    """Convenience: True iff ``session_id`` is on the ignore list."""
    return str(session_id or "").strip() in set(get_ignore_list())


def _atomic_write(payload: list[str]) -> None:
    """Tmp-file + rename for crash-safe writes.  Caller holds
    :data:`_LOCK`."""
    tmp = _PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(_PATH)


def set_ignore_list(session_ids: list[str]) -> list[str]:
    """Replace the ignore list with ``session_ids``.  Returns the
    post-write list (sorted, de-duplicated, validated)."""
    cleaned = sorted({
        str(x).strip()
        for x in (session_ids or [])
        if isinstance(x, str) and x.strip()
    })
    with _LOCK:
        _atomic_write(cleaned)
    return cleaned
