"""Per-agent OCR-region CROP-attachment flags ("Crops" toggle).

Persistent storage for the per-agent "Crops" button in the Workflow
Settings LLM-routing chart, sitting next to each agent's OCR button.
Controls ONE thing: whether that agent's ``reread_text_regions`` tool ATTACHES
the zoomed crop image(s) it re-reads, or returns the higher-resolution
re-read **text only**.

* ``True``  — ``reread_text_regions`` attaches one zoomed crop image
  per region
  (as the tool originally always did), in addition to the re-read text;
* ``False`` — ``reread_text_regions`` still crops + upscales + re-OCRs each
  region (so the re-read TEXT is still higher-resolution), but attaches
  **no images** — cheaper on vision tokens.  This is the default.

Sub-feature of OCR
------------------
Crops only make sense where the ``reread_text_regions`` tool exists, i.e. where
OCR is enabled for the agent.  So :func:`is_enabled_for` ANDs this
per-agent flag with :func:`workflow_settings.ocr_access.is_enabled_for`
— there is no separate master switch; ``OCR_ENABLED`` already gates it.

Eligible agents
---------------
Only the 3 chain agents that actually bind ``reread_text_regions`` (via
``build_user_inputs_tools`` WITH image tools + OCR on).  The other
OCR-eligible roles (planner, dc_input_creator) never receive the tool,
so a crop flag for them would be inert.  See :data:`DEFAULT_AGENTS`.

Persistence & lifecycle
-----------------------
A single JSON file ``ocr_region_crops_access.json`` lives in this
package, alongside ``ocr_access.json``.  Writes are atomic (tmp-file +
``rename``); a process lock serialises concurrent writes.  Changes take
effect on the NEXT session (the tool dispatcher reads the flag when it
handles the call).  Flat ``{ "<agent_slug>": <bool> }``, alphabetical.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from workflow_settings import ocr_access as _ocr_access


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PATH = Path(__file__).parent / "ocr_region_crops_access.json"
_LOCK = threading.Lock()

# The 3 chain agents that actually bind the ``reread_text_regions`` tool
# (lowercase_snake slugs).  When the set of agents that bind it changes,
# edit this tuple.  Must stay a subset of ocr_access.DEFAULT_AGENTS.
DEFAULT_AGENTS: tuple[str, ...] = (
    "user_input_inspector",
    "dc_input_inspector",
    "dc_output_inspector",
)

# Default per-agent value when the JSON file is missing or omits an
# agent — ``False`` (crops OFF: text-only re-read by default, per the
# design decision to keep vision-token cost down).
_DEFAULT_VALUE: bool = False


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def _read_raw() -> dict[str, bool]:
    """Read the JSON file from disk.  Returns an empty dict on any
    failure (missing file, parse error, wrong type) so callers cleanly
    fall back to defaults — tool dispatch must not break just because
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
    """Return the current per-agent crop-attachment dict.

    Always returns exactly the keys in :data:`DEFAULT_AGENTS`, filling
    in :data:`_DEFAULT_VALUE` for any agent the JSON file doesn't
    include.  Does NOT consult OCR access — pure per-agent state.
    """
    raw = _read_raw()
    return {
        slug: bool(raw.get(slug, _DEFAULT_VALUE))
        for slug in DEFAULT_AGENTS
    }


def get(agent: str) -> bool:
    """Per-agent crop flag, without consulting OCR access.  Unknown
    agents return ``False``.  See :func:`is_enabled_for` for the
    OCR-gated version the tool dispatcher uses.
    """
    if agent not in DEFAULT_AGENTS:
        return False
    return get_all()[agent]


def is_enabled_for(agent: str) -> bool:
    """True iff *agent*'s ``reread_text_regions`` should ATTACH zoomed crops.

    ANDs the per-agent crop flag with the agent's effective OCR access
    (:func:`workflow_settings.ocr_access.is_enabled_for`, itself gated
    by the global ``OCR_ENABLED``):

    * OCR off for the agent  →  ``False`` (there's no tool to attach to)
    * OCR on for the agent   →  the per-agent crop flag
    """
    if not _ocr_access.is_enabled_for(agent):
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
    """Update one agent's crop flag and persist to disk.  Returns the
    full post-write dict (with defaults filled in)."""
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
    """Update multiple agents' crop flags in one atomic write.

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
