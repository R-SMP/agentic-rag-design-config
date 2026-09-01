"""Per-agent default LLM choices shown to a first-time user.

These defaults populate the Workflow Settings LLM-routing chart
when no ``.env`` files exist (fresh deploy, or a user who has
never touched the chart).  Once the user saves any value via the
UI, that value is written to ``agents/<agent>/.env`` or
``agents/.env`` and overrides the per-agent default here.

Why this lives in code, not in ``.env`` files: the ``.env`` files
are gitignored (they hold API keys by convention).  So a fresh
checkout or a fresh Railway container has no .env files and
would otherwise fall back to a SINGLE shared default for every
agent.  This module provides per-agent defaults that both the UI
chart (``workflow_settings.llm_routing``) and the runtime
resolver (``agents.shared.llm_provider``) consult as the LAST
fallback.

To change a default permanently in the codebase (e.g. when a
better model ships), edit the dict below; users with their own
.env overrides are NOT affected.
"""

from __future__ import annotations

from workflow_settings import settings as _settings


DEFAULT_PROVIDER: str = "openai"


# Per-agent baked-in defaults.  Each entry is the model string
# passed verbatim to the provider's client (OpenAI's API accepts
# arbitrary model identifiers; an unknown one surfaces as a 404
# at session start, not at config time).
#
# Keys must match the agent slugs in
# ``workflow_settings.llm_routing.AGENT_SPEC`` and
# ``workflow_settings.database_access.DEFAULT_AGENTS``.
DEFAULT_PER_AGENT_MODELS: dict[str, str] = {
    "receptionist":         "gpt-5.4",
    "orchestrator":         "gpt-5.4-mini",
    "user_input_inspector": "gpt-5.4",
    "planner":              "gpt-5-mini",
    "dc_input_creator":     "gpt-5.4-mini",
    "dc_input_inspector":   "gpt-5.5",
    "dc_output_inspector":  "gpt-5.4",
    "tool_caller":          "gpt-5.4-mini",
    "database_handler":     "gpt-5-mini",
    "context_pruner":       "gpt-5.4",
    # 3-agent topology.  The Architect takes the STRONGER of its three
    # parents' defaults: it perceives (vision), plans and routes in one
    # agent, which is the cognitive-load confound the design doc flags
    # as W1 — under-modelling it would confound "fewer agents" with
    # "one overloaded agent".  The Designer takes the DCIC's default;
    # it creates AND executes, but has no validation stage to carry.
    "architect":            "gpt-5.4",
    "designer":             "gpt-5.4-mini",
}


# Per-TOPOLOGY overlay.  Consulted BEFORE the shared dict above and
# fully populated, so topology 5 owns every one of its agents' defaults
# outright: changing a model here can never move topology 7, and changing
# one above can never move topology 5.  Same override-then-fallback shape
# the prompt layer uses for agents/5agent/ and the tool layer uses for
# agents/topology5/.
#
# The one value that is NOT a copy is the Planner's.  In topology 7 the
# Planner only plans and is the weakest tier in the table; in topology 5
# it is the HUB, running the dispatch loop on every hop.  It therefore
# takes the figure the retired Conductor used for exactly that merged
# role -- gpt-5.4-mini -- rather than the chain Planner's gpt-5-mini.
DEFAULT_PER_AGENT_MODELS_BY_TOPOLOGY: dict[int, dict[str, str]] = {
    5: {
        "receptionist":         "gpt-5.4",
        "user_input_inspector": "gpt-5.4",
        "planner":              "gpt-5.4-mini",   # HUB here, not a chain agent
        "dc_input_creator":     "gpt-5.4-mini",
        "dc_output_inspector":  "gpt-5.4",
        "tool_caller":          "gpt-5.4-mini",
        "database_handler":     "gpt-5-mini",
        "context_pruner":       "gpt-5.4",
    },
}

# Last-resort fallback for any agent not in the dict above.  Kept
# in sync with the historical ``_DEFAULT_MODEL`` in
# ``agents/shared/llm_provider.py`` and
# ``workflow_settings/llm_routing.py``.
FALLBACK_MODEL: str = "gpt-5-mini"


def model_for(agent_key: str) -> str:
    """Return the baked-in default model for ``agent_key``.

    The ACTIVE topology's overlay wins; then
    :data:`DEFAULT_PER_AGENT_MODELS`; then :data:`FALLBACK_MODEL`.

    ``SYSTEM_TOPOLOGY`` is read FRESH on every call, never captured at
    import: the Sessions Queue switches topology between runs inside one
    process, and ``web_app._build_session`` reloads the settings module in
    place without reloading its importers (see ``agents/shared/topology.py``
    for the same reasoning).  A module-level constant here would pin the
    overlay to whatever topology the process started with and silently
    mis-resolve the 2nd..Nth run of a mixed-topology queue.

    Read off ``workflow_settings.settings`` directly rather than through
    ``agents.shared.topology`` so this module does not import from
    ``agents`` -- that would invert the package dependency direction.
    """
    topo = int(getattr(_settings, "SYSTEM_TOPOLOGY", 7))
    overlay = DEFAULT_PER_AGENT_MODELS_BY_TOPOLOGY.get(topo)
    if overlay and agent_key in overlay:
        return overlay[agent_key]
    return DEFAULT_PER_AGENT_MODELS.get(agent_key, FALLBACK_MODEL)


# ---------------------------------------------------------------------
# Proposed-workflow presets — surfaced as buttons in the Workflow
# Settings LLM-routing chart's Global LLM row.  Click populates every
# per-agent override field with the listed (provider, model) pair so
# the user can swap whole workflows in one click instead of editing
# 10 rows.  Click does NOT trigger a save — the user reviews the
# chart and hits the existing "Save LLM routing" button to commit.
# DBa toggles are NOT touched by these presets.
#
# Adding a third preset: append a new dict to the list.  The frontend
# renders one button per entry from the /api/llm-routing response, no
# JS / HTML change needed.
#
# These two presets ARE Test 1 "Experiment Subject 5" — the per-agent
# LLM mix (see extra_utilities/docs/reference/benchmark_suite.md, Part B).  The tier of
# each agent is chosen by REASONING demand (context window is not a
# binding constraint: every tier is >= 200k and observed peak usage was
# ~30k).  The SAME tier assignment is instantiated for both providers, so
# the two presets are the two benchmark runs of Subject 5.
#
#   Agent                 Tier    | OpenAI tier map      Anthropic tier map
#   -------------------- -------- | -----------------    ------------------
#   user_input_inspector  HIGH    | HIGH   gpt-5.5       HIGH   claude-opus-4-8
#   dc_input_creator      MEDIUM  | MEDIUM gpt-5.4       MEDIUM claude-sonnet-4-6
#   dc_input_inspector    HIGH    | LOW    gpt-5.4-mini  LOW    claude-haiku-4-5
#   dc_output_inspector   HIGH    |
#   planner               MEDIUM  |  Why these tiers:
#   receptionist          MEDIUM  |  - HIGH: perceive (UII), validate (DCII),
#   orchestrator          LOW     |    critique (DCOI) — the judgement that
#   tool_caller           LOW     |    determines correctness.
#   database_handler      LOW     |  - MEDIUM: create (DCIC), plan (Planner),
#   context_pruner        HIGH    |    interface (Receptionist).
#                                 |  - LOW: route (Orchestrator), execute
#                                 |    (Tool Caller), post-session (DH).
#   The Context Pruner now builds its OWN LLM from this assignment (see
#   orchestrator.py) instead of sharing the Orchestrator's, so HIGH takes
#   effect on the summarisation call (fired only when a long history crosses
#   the pruning threshold — rare).  The DH does not run during a scored
#   Test-1 session, so its tier is cost-only.
# ---------------------------------------------------------------------

PROPOSED_WORKFLOWS: list[dict] = [
    {
        "id":       "openai",
        "label":    "Proposed OpenAI Workflow (Test 1 · Subj 5)",
        "provider": "openai",
        "models": {
            "receptionist":         "gpt-5.4",       # MEDIUM
            "orchestrator":         "gpt-5.4-mini",  # LOW
            "user_input_inspector": "gpt-5.5",       # HIGH
            "planner":              "gpt-5.4",       # MEDIUM
            "dc_input_creator":     "gpt-5.4",       # MEDIUM
            "dc_input_inspector":   "gpt-5.5",       # HIGH
            "dc_output_inspector":  "gpt-5.5",       # HIGH
            "tool_caller":          "gpt-5.4-mini",  # LOW
            "database_handler":     "gpt-5.4-mini",  # LOW
            "context_pruner":       "gpt-5.5",       # HIGH
        },
    },
    {
        "id":       "anthropic",
        "label":    "Proposed Anthropic Workflow (Test 1 · Subj 5)",
        "provider": "anthropic",
        "models": {
            "receptionist":         "claude-sonnet-4-6",  # MEDIUM
            "orchestrator":         "claude-haiku-4-5",   # LOW
            "user_input_inspector": "claude-opus-4-8",    # HIGH
            "planner":              "claude-sonnet-4-6",  # MEDIUM
            "dc_input_creator":     "claude-sonnet-4-6",  # MEDIUM
            "dc_input_inspector":   "claude-opus-4-8",    # HIGH
            "dc_output_inspector":  "claude-opus-4-8",    # HIGH
            "tool_caller":          "claude-haiku-4-5",   # LOW
            "database_handler":     "claude-haiku-4-5",   # LOW
            "context_pruner":       "claude-opus-4-8",    # HIGH
        },
    },
]
