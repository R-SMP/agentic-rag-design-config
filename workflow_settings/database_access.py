"""Per-agent ``database_search`` access flags ("DBa" toggle).

Persistent storage for the per-agent DBa button in the Workflow
Settings LLM-routing chart.  Each of the 8 chain agents gets one
boolean:

* ``True``  — that agent has ``database_search`` bound at session
  start AND has the ``$database_search_tool`` fragment included in
  its system prompt;
* ``False`` — neither.  The tool is not in the agent's
  ``bind_tools(...)`` list and the
  ``<<HAS_DBA>>...<</HAS_DBA>>`` region in its prompt.md is
  stripped at template-build time.

A global master switch ``workflow_settings.settings.RAG_ENABLED``
takes precedence.  When ``RAG_ENABLED`` is ``False``, every
agent's effective access is ``False`` regardless of the per-agent
flag — see :func:`is_enabled_for`.

The 9th primary agent — ``database_handler`` — is intentionally
excluded from :data:`DEFAULT_AGENTS` per Q-4A-13 (the DH is
write-only post-session and never invokes ``database_search``).

Persistence
-----------
A single JSON file ``database_access.json`` lives alongside
``dh_schedule.json`` in this package.  Writes are atomic via
tmp-file + ``rename``; a single in-process lock serialises
concurrent writes.

Lifecycle
---------
Changes take effect on the NEXT session (matches the existing
"settings are read fresh at each session build" pattern in this
codebase).  Mid-session toggles do not affect the currently-
running agents because the per-agent templates were built once at
process / module-load time using the JSON file's state at that
moment, and tool binding happened at agent construction.

File shape
----------
A flat ``{ "<agent_slug>": <bool> }`` mapping, alphabetical by
key for deterministic diffs.  Missing keys default to
:data:`_DEFAULT_VALUE` (currently ``True`` — system ships
database access enabled for every chain agent, consistent with
the ``RAG_ENABLED=True`` default).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from workflow_settings import settings as _workflow_settings


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PATH = Path(__file__).parent / "database_access.json"
_LOCK = threading.Lock()

# Canonical list of the 8 chain agents (lowercase_snake slugs)
# eligible for the DBa toggle.  Matches Q-4A-13 binding decisions
# locked in extra_utilities/db_design/database_and_RAG_architecture.md
# §9.11.  When chain agents are added or removed, edit BOTH this
# tuple AND ``agents.database_handler.db_writer.DEFAULT_AGENTS_TO_ACL``.
DEFAULT_AGENTS: tuple[str, ...] = (
    "receptionist",
    "orchestrator",
    "planner",
    "user_input_inspector",
    "dc_input_creator",
    "dc_input_inspector",
    "dc_output_inspector",
    "tool_caller",
)

# Default per-agent value when the JSON file is missing or doesn't
# include a given agent — ``True`` (system ships with database
# access enabled, consistent with the RAG_ENABLED=True default).
_DEFAULT_VALUE: bool = True


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def _read_raw() -> dict[str, bool]:
    """Read the JSON file from disk.  Returns an empty dict on any
    failure (missing file, parse error, wrong type) so callers can
    cleanly fall back to defaults — the DH save path must not break
    just because this config file is malformed.
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

    Always returns exactly the 8 keys in :data:`DEFAULT_AGENTS`,
    filling in :data:`_DEFAULT_VALUE` for any agent the JSON file
    doesn't currently include.  Does NOT consult the global
    ``RAG_ENABLED`` master switch — pure per-agent state.
    """
    raw = _read_raw()
    return {
        slug: bool(raw.get(slug, _DEFAULT_VALUE))
        for slug in DEFAULT_AGENTS
    }


def get(agent: str) -> bool:
    """Per-agent flag, without consulting ``RAG_ENABLED``.  Unknown
    agents return ``False``.  See :func:`is_enabled_for` for the
    master-switch-gated version that callers in agents/ use.
    """
    if agent not in DEFAULT_AGENTS:
        return False
    return get_all()[agent]


def is_enabled_for(agent: str) -> bool:
    """True iff ``agent`` should have ``database_search`` bound AND
    the ``$database_search_tool`` fragment in its prompt for the
    NEXT session.

    Combines the global ``RAG_ENABLED`` master switch and the
    per-agent flag with AND semantics:

    * ``RAG_ENABLED=False``  →  ``False`` (regardless of per-agent)
    * ``RAG_ENABLED=True``   →  per-agent flag
    """
    if not bool(getattr(_workflow_settings, "RAG_ENABLED", False)):
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
    """Update one agent's flag and persist to disk.  Returns the
    full post-write dict (with defaults filled in for any missing
    agents)."""
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

    Unknown agents in ``flags`` are rejected with
    ``ValueError``.  Agents NOT in ``flags`` keep their current
    on-disk value.  Returns the full post-write dict (with defaults
    filled in)."""
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
