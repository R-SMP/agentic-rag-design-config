"""``dc_params_list`` — the design-parameter list as an on-demand tool.

The Planner and the Orchestrator no longer carry the ``$parameter_list``
fragment inline in their system prompts (2026-08-22 prompt reduction,
extra_utilities/prompt_reduction_4agents_changes.md §B2): they retrieve
it only when they explicitly need it, via this tool.  The Receptionist
and the UII keep the inline fragment and do NOT bind this tool.

The tool returns exactly what the ``$parameter_list`` slot renders —
``DC_prompt_fragments/dc_config/parameters.md`` (honouring any active
topology override), read fresh from disk on every call.
"""

from langchain_core.tools import tool

from agents.shared.agent_activity import generic_tool


@tool
@generic_tool("List DC parameters")
def dc_params_list() -> str:
    """Return the full list of the design parameters — the ONLY parameters
    that exist — with each one's name (exact spelling), type, unit and
    allowed range, plus notes on how they interact.

    Call this when you need to see which parameters exist and what they
    represent (e.g. before judging a directive that names one, or when
    wording a parameter-level plan).  Takes NO arguments.
    """
    # Local import: ``prompts`` imports the routing module at its own
    # import time; reading through its fragment loader here keeps one
    # source of truth (including topology overrides) without widening
    # this module's import-time dependencies.
    from agents.shared.prompts import _read_dc_fragment

    return _read_dc_fragment("dc_config/parameters.md")
