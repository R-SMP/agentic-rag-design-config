"""Per-(profile, agent, tool) database-access flags ("DBa" toggles).

Persistent storage for the per-agent DBa buttons in the Workflow
Settings LLM-routing chart.  Three tools are gated independently:

* ``search``       — ``database_search``
* ``user_inputs``  — ``retrieve_user_inputs``
* ``attempt``      — ``retrieve_attempt``

A flag being ``True`` means that tool is bound at session start AND
its ``$..._tool`` fragment is present in the agent's system prompt;
``False`` means neither.  An agent with all three ``False`` also has
its ``<<HAS_DBA>>...<</HAS_DBA>>`` prompt region stripped, since that
region asks "does this agent hold ANY database tool".

A global master switch ``workflow_settings.settings.RAG_ENABLED``
takes precedence over everything here.  When it is ``False``, every
answer is ``False`` — see :func:`is_enabled_for`.

The 9th primary agent — ``database_handler`` — is intentionally
excluded from :data:`DEFAULT_AGENTS` per Q-4A-13 (the DH is
write-only post-session and never invokes ``database_search``).

Profiles
--------
Different agent systems want different distributions: the 7-agent
REDUCED system deliberately gives the Planner search only, the DCIC
search + attempt, the Receptionist nothing at all.  So the store is
keyed by SETTINGS PROFILE first:

    { "<profile>": { "<agent_slug>": { "<tool>": <bool> } } }

The profile key is the topology for the standard prompts (``"7"``,
``"5"``, ``"3"``) and ``"<topology>-<variant>"`` otherwise — today
that means ``"7-reduced"``.  See :func:`profile_key`.

ONLY PROFILES SOMEBODY ACTUALLY DECIDED ARE IN THE FILE.  ``"5"`` and
``"3"`` are deliberately absent: a missing profile (or agent, or tool)
falls back to :data:`_DEFAULT_VALUE`, which is ``True``, which is
exactly how those systems behaved before this dimension existed.
Writing rows for them would record an inherited DEFAULT as though it
were a DECISION, and later nobody could tell the two apart.  Adding a
row when their distribution IS decided is the whole change — no
migration, no code.  See F88 in extra_utilities/TODO_known_issues.md.

A typo'd profile key does NOT raise — it silently resolves to the
all-``True`` default, which looks like "the setting did nothing".  If a
distribution appears to be ignored, check the key spelling first.

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
codebase).  Mid-session toggles do not affect the currently-running
agents because the per-agent templates were built once at session
construction and tool binding happened at agent construction.
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

# The three independently-gated database tools.
TOOLS: tuple[str, ...] = ("search", "user_inputs", "attempt")

# Canonical list of the chain agents (lowercase_snake slugs) eligible
# for a DBa toggle.  Matches Q-4A-13 binding decisions locked in
# extra_utilities/db_design/database_and_RAG_architecture.md §9.11.
# When chain agents are added or removed, edit BOTH this tuple AND
# ``agents.database_handler.db_writer.DEFAULT_AGENTS_TO_ACL``.
DEFAULT_AGENTS: tuple[str, ...] = (
    "receptionist",
    "orchestrator",
    "planner",
    "user_input_inspector",
    "dc_input_creator",
    "dc_input_inspector",
    "dc_output_inspector",
    "tool_caller",
    # 5-agent topology (superset across topologies)
    "conductor",
    "creator",
    # 3-agent topology
    "architect",
    "designer",
)

# Default value for any (profile, agent, tool) the JSON file does not
# mention — ``True``, so an undecided system keeps the behaviour it had
# before profiles existed.
_DEFAULT_VALUE: bool = True

# Profile key used when a LEGACY flat file is found on disk.  A flat
# ``{agent: bool}`` file predates profiles and can only have described
# the standard 7-agent system.
_LEGACY_PROFILE: str = "7"


# ---------------------------------------------------------------------------
# Profile resolution
# ---------------------------------------------------------------------------

def profile_key() -> str:
    """The active settings profile, e.g. ``"7"`` or ``"7-reduced"``.

    Reads ``SYSTEM_TOPOLOGY`` / ``PROMPT_VARIANT`` off the settings module
    DIRECTLY rather than importing ``agents.shared.topology``: this package
    sits below ``agents`` in the layering, and these are two ``getattr``
    calls.  They are read FRESH per call for the same reason
    ``topology.topology()`` reads them fresh — ``web_app._build_session``
    reloads the settings module in place, and the Sessions Queue switches
    settings between runs inside one process.
    """
    topo = int(getattr(_workflow_settings, "SYSTEM_TOPOLOGY", 7))
    variant = str(
        getattr(_workflow_settings, "PROMPT_VARIANT", "standard")
    ).strip()
    if variant in ("", "standard"):
        return str(topo)
    return f"{topo}-{variant}"


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def _coerce_tools(raw: object) -> dict[str, bool] | None:
    """Normalise one agent's stored entry into a full three-tool dict.

    Accepts the per-tool mapping, and also a bare bool (a legacy flat
    file's value) meaning "the same for all three".  Returns None when the
    entry is unusable, so the caller falls back to defaults.
    """
    if isinstance(raw, bool):
        return {t: raw for t in TOOLS}
    if isinstance(raw, dict):
        return {t: bool(raw.get(t, _DEFAULT_VALUE)) for t in TOOLS}
    return None


def _read_raw() -> dict[str, dict[str, dict[str, bool]]]:
    """Read the JSON file into ``{profile: {agent: {tool: bool}}}``.

    Returns an empty dict on ANY failure (missing file, parse error, wrong
    type) so callers cleanly fall back to defaults — the DH save path must
    not break just because this config file is malformed.

    A legacy FLAT ``{agent: bool}`` file is interpreted as describing
    :data:`_LEGACY_PROFILE` only; every other profile then falls back to
    defaults.  This is a safety net for a stale deployment, not the
    migration path — the migration is the committed JSON itself.
    """
    try:
        if not _PATH.is_file():
            return {}
        data = json.loads(_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        # Legacy flat file: every value is a bare bool.
        if data and all(isinstance(v, bool) for v in data.values()):
            legacy = {
                k: {t: bool(v) for t in TOOLS}
                for k, v in data.items() if isinstance(k, str)
            }
            return {_LEGACY_PROFILE: legacy}
        out: dict[str, dict[str, dict[str, bool]]] = {}
        for prof, agents in data.items():
            if not isinstance(prof, str) or not isinstance(agents, dict):
                continue
            entry: dict[str, dict[str, bool]] = {}
            for agent, tools in agents.items():
                if not isinstance(agent, str):
                    continue
                coerced = _coerce_tools(tools)
                if coerced is not None:
                    entry[agent] = coerced
            out[prof] = entry
        return out
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return {}


def get_all_tools(profile: str | None = None) -> dict[str, dict[str, bool]]:
    """Full per-tool state for *profile* (default: the active one).

    Always returns every slug in :data:`DEFAULT_AGENTS` with all three
    tools present, filling in :data:`_DEFAULT_VALUE` for anything the file
    does not mention.  Does NOT consult ``RAG_ENABLED`` — pure stored state.
    """
    prof = profile or profile_key()
    stored = _read_raw().get(prof, {})
    return {
        slug: {
            t: bool(stored.get(slug, {}).get(t, _DEFAULT_VALUE))
            for t in TOOLS
        }
        for slug in DEFAULT_AGENTS
    }


def get_tools(agent: str, profile: str | None = None) -> dict[str, bool]:
    """One agent's three flags.  Unknown agents get all-``False``."""
    if agent not in DEFAULT_AGENTS:
        return {t: False for t in TOOLS}
    return get_all_tools(profile)[agent]


def get_all(profile: str | None = None) -> dict[str, bool]:
    """``{agent: bool}`` where the bool is "holds ANY database tool".

    Shape deliberately UNCHANGED from before per-tool flags existed: the
    session-config banner and the admin chart's per-agent button both want
    exactly this collapsed view.  Use :func:`get_all_tools` for the
    per-tool detail.  Does NOT consult ``RAG_ENABLED``.
    """
    return {
        slug: any(tools.values())
        for slug, tools in get_all_tools(profile).items()
    }


def get(agent: str, tool: str | None = None,
        profile: str | None = None) -> bool:
    """Stored flag, WITHOUT consulting ``RAG_ENABLED``.

    ``tool=None`` collapses to "holds any database tool".  Unknown agents
    and unknown tool names return ``False``.
    """
    if agent not in DEFAULT_AGENTS:
        return False
    tools = get_tools(agent, profile)
    if tool is None:
        return any(tools.values())
    if tool not in TOOLS:
        return False
    return tools[tool]


def is_enabled_for(agent: str, tool: str | None = None) -> bool:
    """True iff *agent* should hold *tool* for the NEXT session.

    Combines the global ``RAG_ENABLED`` master switch with the stored
    per-(profile, agent, tool) flag, AND semantics:

    * ``RAG_ENABLED=False``  →  ``False``, whatever is stored
    * ``RAG_ENABLED=True``   →  the stored flag

    ``tool=None`` asks "does this agent hold ANY database tool", which is
    exactly the question the ``<<HAS_DBA>>`` prompt region answers.
    """
    if not bool(getattr(_workflow_settings, "RAG_ENABLED", False)):
        return False
    return get(agent, tool)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def _atomic_write(payload: dict) -> None:
    """Tmp-file + rename for crash-safe writes.  Caller holds
    :data:`_LOCK`."""
    tmp = _PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(_PATH)


def _validate(agent: str, tool: str) -> None:
    if agent not in DEFAULT_AGENTS:
        raise ValueError(
            f"Unknown agent {agent!r}; expected one of {DEFAULT_AGENTS}"
        )
    if tool not in TOOLS:
        raise ValueError(
            f"Unknown tool {tool!r}; expected one of {TOOLS}"
        )


def set_one(agent: str, tool: str, enabled: bool,
            profile: str | None = None) -> dict[str, dict[str, bool]]:
    """Set ONE (agent, tool) flag in *profile* and persist.

    Returns the profile's full post-write per-tool dict.  Only the targeted
    cell changes: every other agent, tool and profile is written back
    exactly as read.
    """
    _validate(agent, tool)
    prof = profile or profile_key()
    with _LOCK:
        current = _read_raw()
        prof_entry = current.setdefault(prof, {})
        agent_entry = prof_entry.setdefault(
            agent, {t: _DEFAULT_VALUE for t in TOOLS}
        )
        agent_entry[tool] = bool(enabled)
        _atomic_write(current)
    return get_all_tools(prof)


def set_many(flags: dict[str, dict[str, bool]],
             profile: str | None = None) -> dict[str, dict[str, bool]]:
    """Set several ``{agent: {tool: bool}}`` flags in one atomic write.

    Unknown agents or tools are rejected with ``ValueError``.  Anything not
    named keeps its current on-disk value.
    """
    for agent, tools in flags.items():
        if not isinstance(tools, dict):
            raise ValueError(
                f"flags[{agent!r}] must be a {{tool: bool}} mapping"
            )
        for tool in tools:
            _validate(agent, tool)
    prof = profile or profile_key()
    with _LOCK:
        current = _read_raw()
        prof_entry = current.setdefault(prof, {})
        for agent, tools in flags.items():
            agent_entry = prof_entry.setdefault(
                agent, {t: _DEFAULT_VALUE for t in TOOLS}
            )
            for tool, enabled in tools.items():
                agent_entry[tool] = bool(enabled)
        _atomic_write(current)
    return get_all_tools(prof)
