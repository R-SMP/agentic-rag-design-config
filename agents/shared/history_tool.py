"""Shared ``read_agent_history`` tool.

Lets an agent (currently the Receptionist and the Planner) inspect
another agent's live ``self.messages`` list and answer questions about
prior pipeline runs without re-running anything.

Each calling agent gets its own copy of the tool built via
:func:`build_read_agent_history_tool`, bound to
``Orchestrator.get_agent_messages`` (the history provider).
"""

from typing import Callable, Optional

from langchain_core.tools import StructuredTool


_TOOL_DESCRIPTION = (
    "Read another agent's message history to answer questions from "
    "prior pipeline runs without re-running anything.\n\n"
    "Parameters:\n"
    "  agent_name (str): Which agent's history to read.  Accepts "
    "human-readable names ('DC Output Inspector', 'Tool Caller') or "
    "snake_case keys ('dc_output_inspector', 'tool_caller').  Valid "
    "agents: planner, user_input_inspector, dc_input_creator, "
    "dc_input_inspector, dc_output_inspector, tool_caller, "
    "orchestrator, receptionist.\n"
    "  last_n (int, optional): Return only the last N messages.  Omit "
    "for the full history.\n\n"
    "Returns a formatted transcript (tool calls, tool results, message "
    "content) or an error string if the name is unknown / no history "
    "has been recorded yet."
)


def build_read_agent_history_tool(
    history_provider: Callable[[str, Optional[int]], str],
) -> StructuredTool:
    """Build a ``read_agent_history`` StructuredTool bound to *history_provider*."""

    def _invoke(agent_name: str, last_n: Optional[int] = None) -> str:
        try:
            return history_provider(agent_name, last_n)
        except Exception as exc:
            return f"Error reading history for '{agent_name}': {exc}"

    return StructuredTool.from_function(
        func=_invoke,
        name="read_agent_history",
        description=_TOOL_DESCRIPTION,
    )
