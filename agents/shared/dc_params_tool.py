"""``dc_params_list`` — the design-parameter list as an on-demand tool.

Which agents hold it is the parameter-access table
(``engine/parameter_access.py``; default in ``dc_pack/pack.yaml``): an agent
whose cell says ``tool`` in the running topology gets it, through
:func:`param_tools_for`, and nobody else does.  By default that is the
Receptionist, the Planner and the Orchestrator, which do not carry the
``$parameter_list`` fragment inline (2026-08-22 prompt reduction, round 5;
see extra_utilities/extra_info.md §7.1 and §8) and retrieve it only when
they need it.

The tool returns exactly what the ``$parameter_list`` slot renders —
``dc_pack/fragments/dc/parameter_list.md`` (or the active topology's
``parameter_list.t<N>.md``), read fresh from disk on every call.  Note this
is the SHARED text: an agent's own copy (``parameter_list@<agent>.md``)
changes that agent's PROMPT but not what this tool returns.

WHY A FACTORY.  The schema is identical for every binder but the
"when to call it" sentence is not — the Receptionist reaches for it to
answer the user, the Planner and Orchestrator to check their own wording.
Same reasoning, and the same shape, as ``_build_view_images`` in
``agents/shared/user_inputs_tool.py``.
"""

from langchain_core.tools import tool

from agents.shared import topology as _topology
from agents.shared.agent_activity import generic_tool

_BASE_DOC = (
    "Return the full list of the design parameters — the ONLY parameters "
    "that exist — with each one's name (exact spelling), type, unit and "
    "allowed range, plus notes on how they interact.\n\n"
)

_USE_DEFAULT = (
    "Call this when you need to see which parameters exist and what they "
    "represent (e.g. before judging a directive that names one, or when "
    "wording a parameter-level plan).  Takes NO arguments."
)

_USE_BY_AGENT = {
    # No "planner" entry: the 7-agent Planner has always been given the
    # default wording (it bound the default instance before the access table
    # existed).  The 5- and 3-agent Planners have their own wording in
    # agents/topology5/tool_text.py and agents/topology3/tool_text.py.
    #
    # The Receptionist never validates numbers; it answers and clarifies.
    "receptionist": (
        "Call this to answer a user question about what the system accepts "
        "as input — which parameters exist, what they mean, what values are "
        "allowed — or to clarify a value the user gave.  Takes NO arguments."
    ),
}


def _use_clause(agent_key: str) -> str:
    # The active topology owns this table outright when it ships one; see
    # agents/topology5/tool_text.py.  Topology 7 misses and takes the shared
    # values unchanged.
    table = _topology.overlay_value("USE_BY_AGENT", _USE_BY_AGENT)
    default = _topology.overlay_value("USE_DEFAULT", _USE_DEFAULT)
    return table.get(agent_key or "", default)


def build_dc_params_list(agent_key: str = ""):
    """The ``dc_params_list`` tool, with *agent_key*'s when-to-call clause."""

    @generic_tool("List DC parameters")
    def _impl() -> str:
        # Local import: ``prompts`` imports the routing module at its own
        # import time; reading through its fragment loader here keeps one
        # source of truth (including topology overrides) without widening
        # this module's import-time dependencies.
        from agents.shared.prompts import read_pack_fragment

        return read_pack_fragment("parameter_list")

    # ``generic_tool`` is a ``functools.wraps`` wrapper, so this lands on the
    # object ``tool()`` reads the description from.
    _impl.__doc__ = _BASE_DOC + _use_clause(agent_key)
    return tool("dc_params_list")(_impl)


def param_tools_for(agent_key: str) -> list:
    """``[dc_params_list]`` when *agent_key*'s cell in the parameter-access
    table says ``tool`` in the running topology, else ``[]``.

    Every agent class binds the tool through this, at the place in its tool
    list where it has always sat, so the list's order does not move.
    """
    from engine import parameter_access

    if parameter_access.state(agent_key, _topology.topology()) == "tool":
        return [build_dc_params_list(agent_key)]
    return []
