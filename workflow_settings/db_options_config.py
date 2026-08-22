"""Persisted state for the "Database options" panel.

Stores the 3-way database-mode toggle (Text-only / single-vector
multimodal / late-interaction multimodal).  ``database_search`` reads it
to route READS — see ``_resolve_search_backend``, which maps
``single-vector-multimodal`` to the Voyage ``chunks_mm`` table and every
other mode to the text ``chunks`` table.  WRITES are unaffected:
``chunks_mm`` is dual-written on every save whatever the mode
(architecture doc §6.3), so flipping the toggle never leaves the other
table stale.

Mirrors the read/write shape of ``workflow_settings/database_access.py``
and ``db_search_ignore_list.py``: a small JSON file + atomic writes +
a module lock, with public ``get_mode`` / ``set_mode`` helpers and
dedicated ``/api/db_options`` endpoints in ``web_app.py``.

The per-option embedding PARAMETERS (model, 2048 dims, 1536 px max
side, fusion, …) are NOT stored here — they are locked in code
(``agents/shared/voyage_mm.py`` + W38) and surfaced read-only in the
panel.  Only the mode toggle persists.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

_PATH = Path(__file__).parent / "db_options.json"
_LOCK = threading.Lock()

# The three modes the toggle offers.  "late-interaction-multimodal" is
# reserved — not implemented yet — but selectable so the choice is
# recorded for when it ships.
MODE_TEXT_ONLY = "text-only"
MODE_SINGLE_VECTOR = "single-vector-multimodal"
MODE_LATE_INTERACTION = "late-interaction-multimodal"
VALID_MODES: tuple[str, ...] = (
    MODE_TEXT_ONLY,
    MODE_SINGLE_VECTOR,
    MODE_LATE_INTERACTION,
)
DEFAULT_MODE = MODE_SINGLE_VECTOR


def _read_raw() -> dict:
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write(payload: dict) -> None:
    tmp = _PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(_PATH)


def get_mode() -> str:
    """Return the persisted mode, falling back to the default."""
    mode = str(_read_raw().get("mode", DEFAULT_MODE))
    return mode if mode in VALID_MODES else DEFAULT_MODE


def set_mode(mode: str) -> str:
    """Validate and persist the mode.  Returns the stored value.

    Raises ``ValueError`` for an unknown mode.
    """
    if mode not in VALID_MODES:
        raise ValueError(
            f"Unknown database mode {mode!r}; expected one of {VALID_MODES}"
        )
    with _LOCK:
        current = _read_raw()
        current["mode"] = mode
        _atomic_write(current)
    return mode
