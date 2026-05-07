"""Routing tools and shared state for horizontal agent-to-agent hand-offs.

Each chain agent is bound to a subset of per-target tools named
``call_<target>``.  When an agent's LLM invokes one of these tools:

  1. The exchange (caller, target, message) is appended to a shared
     ``ChainLog`` and to the agent-flow trace.
  2. The intended next hop is recorded on the caller agent's instance
     (``caller._pending_hop``).
  3. The tool returns a brief acknowledgement string so the caller's
     LLM has a valid ``ToolMessage`` to append before the loop exits.

Crucially, routing tools do NOT synchronously invoke the target
agent's ``run()``.  Each agent's run loop is terminal on a routing
tool call: it returns the recorded hop to its caller (the top-level
``dispatch()`` driver), which then invokes the next agent.  The Python
call stack stays flat; every hand-off is a horizontal step driven by
the dispatcher, not a nested recursion.

``call_orchestrator`` is not special in the mechanism — it just records
``target_key="orchestrator"`` like any other target.  The dispatcher
re-enters the Orchestrator's persistent run loop, appending a fresh
``HumanMessage`` for the new turn.
"""

import json
import logging
from dataclasses import dataclass

from langchain_core.tools import StructuredTool

from agents.shared.trace import trace as _trace

logger = logging.getLogger("propeller_agent")


# ---------------------------------------------------------------------------
# Hop signalling
# ---------------------------------------------------------------------------

DONE = "_done_"  # sentinel: dispatch terminates, hop.message is the final text


@dataclass
class AgentHop:
    """The return value of every agent's ``run(message)``.

    ``target`` is either another agent key (see ``AGENT_DISPLAY``) or
    ``DONE`` to signal that dispatch should end and ``message`` is the
    final user-facing (or error) text.
    """
    target: str
    message: str


def _log_inter_agent_message(caller: str, target: str, message: str) -> None:
    """Record an inter-agent message to the session log.

    Always called, regardless of whether the Orchestrator has visibility
    into the chain.  The session .log must contain every exchange
    between any two agents.
    """
    logger.info(f"[AGENT MSG]  {caller} -> {target}\n{message}")


# ---------------------------------------------------------------------------
# Utility-tool observability
# ---------------------------------------------------------------------------

_TOOL_CALL_ARG_TRUNC = 800
_TOOL_CALL_RESULT_TRUNC = 800


def _format(obj) -> str:
    """Render *obj* as a readable string for logs."""
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, default=repr, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(obj)


def _truncate(obj, limit: int) -> str:
    text = _format(obj)
    if len(text) <= limit:
        return text
    return text[:limit] + f"... <truncated, {len(text) - limit} more chars>"


def log_tool_call(caller_key: str, tool_name: str, args, result) -> None:
    """Record a utility tool invocation to the session log and trace."""
    caller_display = AGENT_DISPLAY.get(caller_key, caller_key)
    _trace(caller_display, tool_name)
    args_str = _truncate(args, _TOOL_CALL_ARG_TRUNC)
    result_str = _truncate(result, _TOOL_CALL_RESULT_TRUNC)
    logger.info(
        f"[TOOL CALL]  {caller_display} -> {tool_name}\n"
        f"  args:   {args_str}\n"
        f"  result: {result_str}"
    )


# ---------------------------------------------------------------------------
# Identity table
# ---------------------------------------------------------------------------

AGENT_DISPLAY: dict[str, str] = {
    "planner":              "Planner",
    "user_input_inspector": "User Input Inspector",
    "dc_input_creator":     "DC Input Creator",
    "dc_input_inspector":   "DC Input Inspector",
    "tool_caller":          "Tool Caller",
    "dc_output_inspector":  "DC Output Inspector",
    "orchestrator":         "Orchestrator",
    "receptionist":         "Receptionist",
}

ROUTING_TOOL_NAMES: set[str] = {f"call_{k}" for k in AGENT_DISPLAY}


# ---------------------------------------------------------------------------
# Shared chain log
# ---------------------------------------------------------------------------

class ChainLog:
    """In-memory buffer of inter-agent exchanges for the current user turn."""

    def __init__(self) -> None:
        self.exchanges: list[tuple[str, str, str]] = []

    def append(self, from_agent: str, to_agent: str, message: str) -> None:
        self.exchanges.append((from_agent, to_agent, message))

    def reset(self) -> None:
        self.exchanges.clear()

    def format(self) -> str:
        if not self.exchanges:
            return ""
        blocks = [
            f"[FROM {a}, TO {b}]:\n{m}" for a, b, m in self.exchanges
        ]
        return "\n\n---\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Tool factory
# ---------------------------------------------------------------------------

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "call_planner": (
        "Call the Planner.  The ``message`` argument IS the hand-off "
        "text the Planner will see — write it as free-form prose."
    ),
    "call_user_input_inspector": (
        "Call the User Input Inspector.  The ``message`` argument IS "
        "the hand-off text the UII will see — write it as free-form "
        "prose."
    ),
    "call_dc_input_creator": (
        "Call the DC Input Creator.  The ``message`` argument IS the "
        "hand-off text the DCIC will see — write it as free-form prose."
    ),
    "call_dc_input_inspector": (
        "Call the DC Input Inspector.  The ``message`` argument IS the "
        "hand-off text the DCII will see — write it as free-form prose."
    ),
    "call_tool_caller": (
        "Call the Tool Caller.  The ``message`` argument IS the hand-"
        "off text the Tool Caller will see — write it as free-form "
        "prose."
    ),
    "call_dc_output_inspector": (
        "Call the DC Output Inspector.  The ``message`` argument IS "
        "the hand-off text the DC Output Inspector will see.  Include "
        "the full paths of any rendered images that the Inspector "
        "should analyse, under a 'Render images:' label."
    ),
    "call_orchestrator": (
        "Return control to the Orchestrator.  The ``message`` argument "
        "IS the hand-off text the Orchestrator will see — write it as "
        "free-form prose.  Use this when the natural pipeline has "
        "completed, when you cannot proceed, or when the Orchestrator's "
        "incoming instruction told you to report back."
    ),
    "call_receptionist": (
        "Hand a user-facing result to the Receptionist, which composes "
        "and delivers the final message to the user.  Pass a technical "
        "summary — the Receptionist composes the actual wording."
    ),
}


def build_routing_tool(
    caller_key: str,
    target_key: str,
    caller_agent,
    chain_log: ChainLog,
):
    """Build a ``call_<target_key>`` tool for the agent named ``caller_key``."""
    caller_display = AGENT_DISPLAY.get(caller_key, caller_key)
    target_display = AGENT_DISPLAY.get(target_key, target_key)
    tool_name = f"call_{target_key}"
    description = _TOOL_DESCRIPTIONS.get(
        tool_name, f"Call the {target_display} with a short hand-off message."
    )

    def _invoke(message: str) -> str:
        if target_key != "orchestrator":
            chain_log.append(caller_display, target_display, message)
        _log_inter_agent_message(caller_display, target_display, message)
        # The Receptionist -> Orchestrator hop is traced by the loader
        # with a richer "forwarded" note; skip the routing-tool trace
        # here to avoid a duplicate entry.
        if not (caller_key == "receptionist" and target_key == "orchestrator"):
            _trace(caller_display, target_display)
        # Label the hand-off with its sender so the target agent can
        # never mis-attribute the content (e.g. mistake a Planner plan
        # for a user request).  Session log and chain-log use unlabeled
        # copies — they already carry their own sender header.
        labeled_message = f"[Incoming from: {caller_display}]\n\n{message}"
        caller_agent._pending_hop = AgentHop(
            target=target_key, message=labeled_message,
        )
        return (
            f"Hand-off recorded: message delivered to {target_display}. "
            f"Control will pass horizontally once your turn ends."
        )

    return StructuredTool.from_function(
        func=_invoke,
        name=tool_name,
        description=description,
    )


# ---------------------------------------------------------------------------
# Shared run loop helper
# ---------------------------------------------------------------------------

def is_routing_tool(name: str) -> bool:
    """Return True if *name* is one of the terminal routing tools."""
    return name in ROUTING_TOOL_NAMES


# ---------------------------------------------------------------------------
# Stuck-loop detection
# ---------------------------------------------------------------------------

def tool_call_signature(tc: dict) -> tuple[str, str]:
    """Canonical (name, args) signature for duplicate-call detection."""
    args = tc.get("args") or {}
    try:
        args_str = json.dumps(
            args, sort_keys=True, default=repr, ensure_ascii=False,
        )
    except (TypeError, ValueError):
        args_str = repr(args)
    return tc.get("name", ""), args_str


def stuck_escalation(agent_label: str, tool_name: str) -> AgentHop:
    """Build the AgentHop used when a stuck loop is detected."""
    return AgentHop(
        "orchestrator",
        (
            f"Error: {agent_label} detected a stuck loop — it was about to "
            f"call '{tool_name}' with the same arguments it already used "
            f"this turn, without new information to act on.  Escalating "
            f"instead of looping; please provide fresh instructions or "
            f"consult another agent."
        ),
    )


def finalize_unanswered_tool_calls(
    messages: list,
    response_tool_calls: list,
    start_index: int,
    reason: str = (
        "Tool call dropped — the agent returned control before executing "
        "this call.  No result is available."
    ),
) -> None:
    """Append a synthetic ToolMessage for every tool_call from
    ``start_index`` onward in ``response_tool_calls``.

    Required because OpenAI's chat completions API rejects any payload
    where an assistant message with ``tool_calls`` is not immediately
    followed by a ToolMessage for each ``tool_call_id`` (error
    ``"tool_calls must be followed by tool messages…"``).  When an
    agent's run loop returns or breaks early — for example via
    ``stuck_escalation`` (the current tc was rejected before its
    handler ran) or via the routed-tool ``break`` (the routing tc
    was answered but later sibling tcs were not) — any unprocessed
    tool_call from the same response would otherwise be left
    dangling in the agent's persistent ``self.messages`` and the
    next ``llm.invoke`` would 400.

    Importing module-locally to avoid a circular import on
    ``langchain_core``.
    """
    from langchain_core.messages import ToolMessage  # local import — see docstring
    for tc in response_tool_calls[start_index:]:
        messages.append(ToolMessage(
            content=reason,
            tool_call_id=tc["id"],
            name=tc.get("name", ""),
        ))
