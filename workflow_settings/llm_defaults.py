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
}


# Last-resort fallback for any agent not in the dict above.  Kept
# in sync with the historical ``_DEFAULT_MODEL`` in
# ``agents/shared/llm_provider.py`` and
# ``workflow_settings/llm_routing.py``.
FALLBACK_MODEL: str = "gpt-5-mini"


def model_for(agent_key: str) -> str:
    """Return the baked-in default model for ``agent_key``.

    Agents not in :data:`DEFAULT_PER_AGENT_MODELS` get
    :data:`FALLBACK_MODEL`.
    """
    return DEFAULT_PER_AGENT_MODELS.get(agent_key, FALLBACK_MODEL)
