"""``dc_params_list`` — the design-parameter list as an on-demand tool.

The Planner and the Orchestrator do not carry the ``$parameter_list``
fragment inline in their system prompts (2026-08-22 prompt reduction,
extra_utilities/prompt_reduction_4agents_changes.md §B2), and the
Receptionist stopped carrying it in round 5
(extra_utilities/prompt_reduction_round5_changes.md, "The Receptionist
loses its static parameter list").  All three retrieve it only when they
explicitly need it, via this tool.

The UII does NOT bind it: its inline fragment is gated by
``UII_PARAMETER_LIST_ENABLED`` (default False) precisely so the UII works
in the user's vocabulary rather than the configurator's, and handing it a
retrieval path would defeat that.

The tool returns exactly what the ``$parameter_list`` slot renders —
``DC_prompt_fragments/dc_config/parameters.md`` (honouring any active
topology override), read fresh from disk on every call.  Note this is the
SHARED file: a per-agent scoped copy (``parameters_<agent>.md``) changes
that agent's PROMPT but not what this tool returns.

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
    # The Planner directs in words and never picks values, so it rarely needs
    # this at all — and the printed ranges are exactly what tempted it to pick
    # from them (runs ID278 / ID279).
    "planner": (
        "Reference only: which parameters exist and what each one means.  You "
        "rarely need it — describe the change you want in plain words and let "
        "the DC Input Creator pick the parameter and the value.  Takes NO "
        "arguments."
    ),
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
        from agents.shared.prompts import _read_dc_fragment

        return _read_dc_fragment("dc_config/parameters.md")

    # ``generic_tool`` is a ``functools.wraps`` wrapper, so this lands on the
    # object ``tool()`` reads the description from.
    _impl.__doc__ = _BASE_DOC + _use_clause(agent_key)
    return tool("dc_params_list")(_impl)


# Default-wording instance, kept as a module-level name because the Planner
# and the Orchestrator bind it by import.
dc_params_list = build_dc_params_list()
