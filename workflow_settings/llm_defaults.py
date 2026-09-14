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
    "receptionist":         "gpt-5.6-terra",
    "orchestrator":         "gpt-5.6-luna",
    "user_input_inspector": "gpt-5.6-terra",
    "planner":              "gpt-5.6-terra",
    "dc_input_creator":     "gpt-5.6-terra",
    "dc_input_inspector":   "gpt-5.6-luna",
    "dc_output_inspector":  "gpt-5.6-terra",
    "tool_caller":          "gpt-5.6-luna",
    "database_handler":     "gpt-5.6-terra",
    "context_pruner":       "gpt-5.6-sol",
    # 3-agent topology.  These two keys exist ONLY under topology 3, so a
    # base entry here cannot move topology 7 or 5 -- it simply keeps
    # every consumer that iterates ALL agent keys (llm_routing, the
    # loader's startup banner) off FALLBACK_MODEL.  Their RUNTIME values
    # come from the topology-3 overlay below, which lists both in full;
    # these mirror it so the settings chart and the runtime agree.
    "design_engineer":      "gpt-5.4-mini",
    "requirements_analyst": "gpt-5.4",
}


# Per-TOPOLOGY overlay.  Consulted BEFORE the shared dict above and
# fully populated, so topology 5 owns every one of its agents' defaults
# outright: changing a model here can never move topology 7, and changing
# one above can never move topology 5.  Same override-then-fallback shape
# the prompt layer uses for agents/5agent/ and the tool layer uses for
# agents/topology5/.
#
# Topology 5's values are a SNAPSHOT of the gpt-5.4-era table: they were
# copied when the overlay was written and deliberately left alone when
# topology 7 moved to the gpt-5.6 family, because the overlay exists so
# that exactly this kind of edit cannot move topology 5 by accident.
# Re-tier them deliberately when topology 5 is next benchmarked.  Note
# that topology 5's Planner is the HUB, running the dispatch loop on
# every hop, not the chain Planner topology 7 has.
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
    # 3-agent topology.  Listed in FULL, like topology 5's, so the table
    # is the whole truth for this topology rather than a diff a reader has
    # to compute.  Exactly ONE entry differs from the shared defaults --
    # ``planner`` gpt-5-mini -> gpt-5.4-mini, the same lift topology 5
    # gives the same merged-hub role.  The two merged agents inherit
    # their parents' figure, which in both cases the two parents share.
    3: {
        "receptionist":         "gpt-5.4",
        "planner":              "gpt-5.4-mini",   # HUB here
        "requirements_analyst": "gpt-5.4",
        "design_engineer":      "gpt-5.4-mini",
        "database_handler":     "gpt-5-mini",
        "context_pruner":       "gpt-5.4",
    },
}

# Last-resort fallback for any agent not in the dict above.  Kept
# in sync with the historical ``_DEFAULT_MODEL`` in
# ``agents/shared/llm_provider.py`` and
# ``workflow_settings/llm_routing.py``.
FALLBACK_MODEL: str = "gpt-5.6-terra"


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
# The OPENAI preset is the gpt-5.6 workflow, and is kept identical to
# ``DEFAULT_PER_AGENT_MODELS`` above (topology 7's baked-in defaults) so
# that a fresh deploy and a click on the button produce the SAME chart.
# Change one, change the other.
#
#   gpt-5.6-terra   receptionist, user_input_inspector, planner,
#                   dc_input_creator, dc_output_inspector, database_handler
#   gpt-5.6-luna    orchestrator, dc_input_inspector, tool_caller
#   gpt-5.6-sol     context_pruner — the only agent on sol
#
# The ANTHROPIC preset is still Test 1 "Experiment Subject 5" (see
# extra_utilities/docs/reference/benchmark_suite.md, Part B): a tier chosen
# per agent by REASONING demand — HIGH claude-opus-4-8 to perceive (UII),
# validate (DCII) and critique (DCOI); MEDIUM claude-sonnet-4-6 to create
# (DCIC), plan (Planner) and interface (Receptionist); LOW claude-haiku-4-5
# to route (Orchestrator), execute (Tool Caller) and save (DH).  Context
# window is not a binding constraint on either side: every tier is >= 200k
# and observed peak usage was ~30k.
#
# The two presets are therefore NO LONGER one tier assignment instantiated
# twice.  The OpenAI side was re-pointed at the 5.6 family on 2026-09-14
# and does not follow that map: the DCII drops from the top tier to the
# middle, the DH rises from the bottom to the top, and the Context Pruner
# sits alone on sol.  A like-for-like Subject-5 comparison needs the
# Anthropic preset against the PRE-2026-09-14 OpenAI mix, which is in git
# history at this file.
#
# The Context Pruner builds its OWN LLM from this assignment (see
# orchestrator.py) rather than sharing the Orchestrator's, so its entry
# takes effect on the summarisation call — fired only when a long history
# crosses the pruning threshold.  The DH does not run during a scored
# Test-1 session, so its entry is cost-only.
# ---------------------------------------------------------------------

PROPOSED_WORKFLOWS: list[dict] = [
    {
        "id":       "openai",
        "label":    "Proposed OpenAI Workflow (Test 1 · Subj 5)",
        "provider": "openai",
        "models": {
            "receptionist":         "gpt-5.6-terra",
            "orchestrator":         "gpt-5.6-luna",
            "user_input_inspector": "gpt-5.6-terra",
            "planner":              "gpt-5.6-terra",
            "dc_input_creator":     "gpt-5.6-terra",
            "dc_input_inspector":   "gpt-5.6-luna",
            "dc_output_inspector":  "gpt-5.6-terra",
            "tool_caller":          "gpt-5.6-luna",
            "database_handler":     "gpt-5.6-terra",
            "context_pruner":       "gpt-5.6-sol",
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
