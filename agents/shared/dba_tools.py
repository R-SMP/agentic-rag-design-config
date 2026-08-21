"""One place that decides which database tools an agent holds.

Every agent used to carry its own four-line block:

    if database_access.is_enabled_for("<agent>"):
        <list>.append(make_database_search_tool("<agent>"))
        <list>.append(make_retrieve_user_inputs_tool("<agent>"))
        <list>.append(make_retrieve_attempt_tool("<agent>"))

which hard-wired "all three or none" into twelve files.  The three tools
are now gated independently per (profile, agent, tool), so the decision
lives here instead and each agent asks one question:

    all_tools.extend(dba_tools_for("planner"))

Same shape as ``prompts.routing_instructions``: one selector reaches every
agent, and no agent file needs to know that profiles or variants exist.

The factories are imported HERE and nowhere else, so adding or retiring a
database tool touches this module rather than the whole fleet.
"""

from __future__ import annotations

from tools.database_search.database_search import make_database_search_tool
from tools.retrieve_attempt.retrieve_attempt import make_retrieve_attempt_tool
from tools.retrieve_user_inputs.retrieve_user_inputs import (
    make_retrieve_user_inputs_tool,
)
from workflow_settings import database_access


# Tool key -> factory.  Order is the order agents see them in their tool
# list, and is deliberately stable: search first because it is what finds
# the ids the other two consume.
_FACTORIES = (
    ("search",      make_database_search_tool),
    ("user_inputs", make_retrieve_user_inputs_tool),
    ("attempt",     make_retrieve_attempt_tool),
)


def dba_tools_for(agent_key: str) -> list:
    """Bound database tools for *agent_key*, for THIS session.

    Returns ``[]`` when the agent holds none — because the master switch
    ``RAG_ENABLED`` is off, because the active profile gives it nothing, or
    because the agent is not DBa-eligible at all.  The caller appends or
    indexes the result; it never has to branch.

    Read fresh at bind time, like every other setting in this codebase: the
    profile depends on ``SYSTEM_TOPOLOGY``, which the Sessions Queue changes
    between runs inside one process.
    """
    return [
        factory(agent_key)
        for tool_key, factory in _FACTORIES
        if database_access.is_enabled_for(agent_key, tool_key)
    ]
