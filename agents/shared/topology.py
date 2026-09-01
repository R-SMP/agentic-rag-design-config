"""Which agent topology is active, and who its hub is.

Deliberately dependency-free — it imports ``workflow_settings`` and
nothing else — because all three layers need these facts: prompt
assembly (``prompts.py``), the routing-section builder (``routing.py``)
and the routing-tool factory (``routing_tools.py``).  Homing them in any
one of those would make the other two depend on it; here,
``routing_tools`` stays a leaf and ``routing`` stays importable without
``langchain_core``.

Every value is read FRESH on each call and never captured at import:
``web_app._build_session`` reloads the settings module in place but does
not reload its importers, and the Sessions Queue switches topology
between runs inside a single process.  A module constant here would pin
the topology to whatever was on disk when the process started.
"""

from workflow_settings import settings as _workflow_settings

# Agent key -> display name, per topology.  The 7-agent hub is the
# Orchestrator; the 5-agent hub is the PLANNER, which absorbs the
# Orchestrator's dispatch role (the 5-agent system is the 7-agent one
# minus the Orchestrator and minus the DC Input Inspector).
#
# The display names must agree with ``routing_tools.AGENT_DISPLAY``.
# They are duplicated here rather than imported from it because that
# module pulls in ``langchain_core``, and this one must stay importable
# without it.  ``smoke_test_topology_fragments.py`` asserts the two
# tables agree, so they cannot drift silently.
_HUB_BY_TOPOLOGY = {
    7: ("orchestrator", "Orchestrator"),
    5: ("planner", "Planner"),
    # 3-agent topology (strip-down).  The Architect merges the UII into
    # the hub: perceive + plan + route + approve.
    3: ("architect", "Architect"),
}

# Fallback for an unrecognised SYSTEM_TOPOLOGY: behave as the 7-agent
# system, which is the historic behaviour and the one whose files always
# exist.
_DEFAULT_HUB = _HUB_BY_TOPOLOGY[7]


def topology() -> int:
    """The active agent topology (7 or 5)."""
    return int(getattr(_workflow_settings, "SYSTEM_TOPOLOGY", 7))


def hub_key() -> str:
    """Agent key of the active topology's hub, e.g. ``"planner"``."""
    return _HUB_BY_TOPOLOGY.get(topology(), _DEFAULT_HUB)[0]


def hub_display() -> str:
    """Display name of the active topology's hub, e.g. ``"Planner"``."""
    return _HUB_BY_TOPOLOGY.get(topology(), _DEFAULT_HUB)[1]

# ---------------------------------------------------------------------------
# Per-topology CODE overlays
#
# The prompt layer gets its topology dimension from files:
# ``prompts._topology_override`` resolves
# ``agents/<N>agent/.../<name>_<N>agents.md`` and falls back to the shared
# original.  The TOOL layer had no such dimension at all -- every per-agent
# tailoring table (``_VIEW_IMAGES_PATHS_BY_AGENT``, ``_USE_BY_AGENT``,
# ``_TEXT_PATH_BY_AGENT``, ...) was keyed on ``agent_key`` alone, so the
# 5-agent DCOI / UII / Tool Caller reused their 7-agent twins' tool
# descriptions and any edit to one moved both.
#
# ``overlay_value`` is the same override-then-fallback shape, one level up:
# a topology that ships an overlay module owns the value outright; one that
# does not takes the shared value unchanged.  There is no merging -- the
# overlay tables are FULLY populated so a topology's table is the whole
# truth for that topology, which is what makes the two independent.
#
# Topology 7 ships no overlay module, so every lookup misses and the
# expression reduces to exactly the code that was there before.
# ---------------------------------------------------------------------------

_OVERLAY_MODULE_BY_TOPOLOGY = {
    5: "agents.topology5.tool_text",
}


def overlay_value(name: str, shared):
    """The active topology's version of *name*, or *shared*.

    *name* is the attribute to look for in this topology's overlay module.
    Import is lazy and per call: the module cache makes it cheap, and the
    TOPOLOGY must be re-read every time because the Sessions Queue switches
    it between runs inside one process.

    A missing overlay module, or a module that does not define *name*,
    yields *shared* -- so a half-written overlay is safe, exactly as a
    half-written ``agents/<N>agent/`` tree is.
    """
    module_name = _OVERLAY_MODULE_BY_TOPOLOGY.get(topology())
    if module_name is None:
        return shared
    import importlib

    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return shared
    return getattr(module, name, shared)
