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
# Orchestrator; the 5-agent hub is the Conductor, which merges the
# Planner and the Orchestrator into one agent.
#
# The display names must agree with ``routing_tools.AGENT_DISPLAY``.
# They are duplicated here rather than imported from it because that
# module pulls in ``langchain_core``, and this one must stay importable
# without it.  ``smoke_test_topology_fragments.py`` asserts the two
# tables agree, so they cannot drift silently.
_HUB_BY_TOPOLOGY = {
    7: ("orchestrator", "Orchestrator"),
    5: ("conductor", "Conductor"),
}

# Fallback for an unrecognised SYSTEM_TOPOLOGY: behave as the 7-agent
# system, which is the historic behaviour and the one whose files always
# exist.
_DEFAULT_HUB = _HUB_BY_TOPOLOGY[7]


def topology() -> int:
    """The active agent topology (7 or 5)."""
    return int(getattr(_workflow_settings, "SYSTEM_TOPOLOGY", 7))


def hub_key() -> str:
    """Agent key of the active topology's hub, e.g. ``"conductor"``."""
    return _HUB_BY_TOPOLOGY.get(topology(), _DEFAULT_HUB)[0]


def hub_display() -> str:
    """Display name of the active topology's hub, e.g. ``"Conductor"``."""
    return _HUB_BY_TOPOLOGY.get(topology(), _DEFAULT_HUB)[1]
