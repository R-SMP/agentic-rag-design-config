"""Per-agent OCR access flags ("OCR" toggle).

Persistent storage for the per-agent OCR button in the Workflow
Settings LLM-routing chart.  Mirrors ``database_access.py`` (the DBa
toggle).  Each eligible agent gets one boolean:

* ``True``  — when OCR is globally enabled, that agent's image tools
  (``view_images`` / ``read_user_inputs`` / ``retrieve_user_inputs``)
  carry the ``extract_text`` flag and the ``ocr_regions`` tool, and run
  OCR on loaded images;
* ``False`` — that agent's image tools behave as if OCR were off (no
  ``extract_text`` flag, no ``ocr_regions`` tool, no OCR pass) even when
  the global switch is on.

A global master switch ``workflow_settings.settings.OCR_ENABLED``
takes precedence.  When ``OCR_ENABLED`` is ``False``, every agent's
effective access is ``False`` regardless of the per-agent flag — see
:func:`is_enabled_for`.

Eligible agents
---------------
Only the 5 chain agents that bind the image tools
(``build_user_inputs_tools`` / ``read_user_inputs`` /
``retrieve_user_inputs``) are eligible — the other roles have no
images to OCR.  See :data:`DEFAULT_AGENTS`.

Persistence
-----------
A single JSON file ``ocr_access.json`` lives alongside
``database_access.json`` in this package.  Writes are atomic via
tmp-file + ``rename``; a single in-process lock serialises
concurrent writes.

Lifecycle
---------
Changes take effect on the NEXT session (matches the existing
"settings are read fresh at each session build" pattern): the
per-agent tool builders read these flags at agent construction.

File shape
----------
A flat ``{ "<agent_slug>": <bool> }`` mapping, alphabetical by key
for deterministic diffs.  Missing keys default to
:data:`_DEFAULT_VALUE` (currently ``True`` — OCR is enabled for every
eligible agent, consistent with the ``OCR_ENABLED=True`` default).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from workflow_settings import settings as _workflow_settings


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PATH = Path(__file__).parent / "ocr_access.json"
_LOCK = threading.Lock()

# The chain agents that bind the image tools (lowercase_snake slugs) —
# the only ones for which OCR is meaningful.  When the set of
# image-tool-binding agents changes, edit this tuple.  Superset across
# topologies: a topology that never constructs an agent simply never
# consults its entry.
DEFAULT_AGENTS: tuple[str, ...] = (
    "user_input_inspector",
    "planner",
    "dc_input_creator",
    "dc_input_inspector",
    "dc_output_inspector",
    # 5-agent topology: the Creator inherits the DCIC's + DCII's image
    # tools; the Conductor inherits the Planner's ``view_images``.
    "conductor",
    "creator",
    # 3-agent topology.  The Architect PERCEIVES — it absorbs the UII,
    # so it binds the image tools and needs OCR text with them.
    "architect",
    "designer",
)

# Default per-agent value when the JSON file is missing or doesn't
# include a given agent — ``True`` (OCR enabled for every eligible
# agent, consistent with the OCR_ENABLED=True default).
_DEFAULT_VALUE: bool = True


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def _read_raw() -> dict[str, bool]:
    """Read the JSON file from disk.  Returns an empty dict on any
    failure (missing file, parse error, wrong type) so callers cleanly
    fall back to defaults — tool binding must not break just because
    this config file is malformed.
    """
    try:
        if not _PATH.is_file():
            return {}
        data = json.loads(_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {
            k: bool(v) for k, v in data.items()
            if isinstance(k, str)
        }
    except (OSError, json.JSONDecodeError):
        return {}


def get_all() -> dict[str, bool]:
    """Return the current per-agent access dict.

    Always returns exactly the keys in :data:`DEFAULT_AGENTS`, filling
    in :data:`_DEFAULT_VALUE` for any agent the JSON file doesn't
    currently include.  Does NOT consult the global ``OCR_ENABLED``
    master switch — pure per-agent state.
    """
    raw = _read_raw()
    return {
        slug: bool(raw.get(slug, _DEFAULT_VALUE))
        for slug in DEFAULT_AGENTS
    }


def get(agent: str) -> bool:
    """Per-agent flag, without consulting ``OCR_ENABLED``.  Unknown
    agents return ``False``.  See :func:`is_enabled_for` for the
    master-switch-gated version that the tool builders use.
    """
    if agent not in DEFAULT_AGENTS:
        return False
    return get_all()[agent]


def is_enabled_for(agent: str) -> bool:
    """True iff *agent* should get OCR (the ``extract_text`` flag +
    ``ocr_regions`` tool + the OCR pass) for the NEXT session.

    Combines the global ``OCR_ENABLED`` master switch and the
    per-agent flag with AND semantics:

    * ``OCR_ENABLED=False``  →  ``False`` (regardless of per-agent)
    * ``OCR_ENABLED=True``   →  per-agent flag
    """
    if not bool(getattr(_workflow_settings, "OCR_ENABLED", False)):
        return False
    return get(agent)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def _atomic_write(payload: dict[str, bool]) -> None:
    """Tmp-file + rename for crash-safe writes.  Caller holds
    :data:`_LOCK`."""
    tmp = _PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(_PATH)


def set_one(agent: str, enabled: bool) -> dict[str, bool]:
    """Update one agent's flag and persist to disk.  Returns the full
    post-write dict (with defaults filled in for any missing agents)."""
    if agent not in DEFAULT_AGENTS:
        raise ValueError(
            f"Unknown agent {agent!r}; expected one of {DEFAULT_AGENTS}"
        )
    with _LOCK:
        current = _read_raw()
        current[agent] = bool(enabled)
        _atomic_write(current)
    return get_all()


def set_many(flags: dict[str, bool]) -> dict[str, bool]:
    """Update multiple agents' flags in one atomic write.

    Unknown agents in *flags* are rejected with ``ValueError``.  Agents
    NOT in *flags* keep their current on-disk value.  Returns the full
    post-write dict (with defaults filled in)."""
    unknown = set(flags) - set(DEFAULT_AGENTS)
    if unknown:
        raise ValueError(
            f"Unknown agent(s) {sorted(unknown)}; "
            f"expected subset of {list(DEFAULT_AGENTS)}"
        )
    with _LOCK:
        current = _read_raw()
        for agent, enabled in flags.items():
            current[agent] = bool(enabled)
        _atomic_write(current)
    return get_all()
