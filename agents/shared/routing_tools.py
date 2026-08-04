"""Routing tools and shared state for horizontal agent-to-agent hand-offs.

Each chain agent is bound to a subset of per-target tools named
``call_<target>``.  When an agent's LLM invokes one of these tools:

  1. The exchange (caller, target, message, ts) is appended to the
     session-scoped ``session.chain_log_exchanges`` and to the
     agent-flow trace.
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
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from langchain_core.tools import StructuredTool

from agents.shared.topology import hub_key as _hub_key
from agents.shared.trace import trace as _trace

if TYPE_CHECKING:
    from agents.shared.session import Session

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
    # File-only trace line: ``tool_name`` is a langchain tool function
    # name (snake_case), NOT a real agent.  Publishing this to viz_bus
    # would inject a bogus ``agent_active`` event into the flowchart —
    # the frontend would clear every real agent's highlight trying to
    # activate the unknown id.  See trace() docstring for the contract.
    _trace(caller_display, tool_name, publish=False)
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
    # 5-agent topology: the Conductor merges Planner + Orchestrator, the
    # Creator merges DC Input Creator + DC Input Inspector.  Listed here for
    # EVERY topology because this table is the identity registry
    # (``ROUTING_TOOL_NAMES`` below and ``session.KNOWN_AGENT_KEYS`` derive
    # from it).  Nothing iterates it to BUILD agents, so a topology that does
    # not use them simply never constructs them.
    "conductor":            "Conductor",
    "creator":              "Creator",
    # 3-agent topology.  The Architect merges UII + Planner +
    # Orchestrator; the Designer merges DC Input Creator + Tool Caller
    # with NO validation stage.  The critic stays the DC Output
    # Inspector, unrenamed, exactly as the 5-agent survivors did.
    "architect":            "Architect",
    "designer":             "Designer",
}

ROUTING_TOOL_NAMES: set[str] = {f"call_{k}" for k in AGENT_DISPLAY}


# ---------------------------------------------------------------------------
# Chain-log helpers
# ---------------------------------------------------------------------------
#
# The chain log lives on Session as ``session.chain_log_exchanges`` —
# a session-scoped list of plain dicts, one per inter-agent hand-off.
# (Per Q1 of v3 Phase 1's design pass the chain log accumulates across
# the WHOLE session; the per-turn-only "just exchanges since I last
# saw" view is reconstructed in Orchestrator.dispatch via a cursor
# tracked per-dispatch-call rather than by resetting the log.)
#
# Each exchange dict has four keys:
#   - ``from_agent``: caller's display name (e.g. "Planner")
#   - ``to_agent``:   target's display name (e.g. "Tool Caller")
#   - ``message``:    the unlabelled hand-off prose
#   - ``ts``:         ISO-8601 with timezone, recorded at append time

def format_chain_exchanges(exchanges: list[dict]) -> str:
    """Render a list of chain-log exchanges as the prose block agents see.

    Same shape as the previous ``ChainLog.format()`` output (which the
    Orchestrator-with-chain-access prepends to its incoming message),
    but reads dicts instead of tuples.
    """
    if not exchanges:
        return ""
    blocks = [
        f"[FROM {ex['from_agent']}, TO {ex['to_agent']}]:\n{ex['message']}"
        for ex in exchanges
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
    "call_conductor": (
        "Return control to the Conductor — the hub that plans, routes and "
        "approves.  The ``message`` argument IS the hand-off text it will "
        "see — write it as free-form prose.  Use this when the natural "
        "pipeline has completed, to CLARIFY when its directive was "
        "ambiguous or could not be expressed in concrete parameter "
        "values, or to ESCALATE when you are stuck; the Conductor is the "
        "single point the chain returns to on any failure."
    ),
    "call_architect": (
        "Return control to the Architect — the brain that reads the "
        "user's inputs, plans, routes and approves.  The ``message`` "
        "argument IS the hand-off text it will see — write it as "
        "free-form prose.  Use this when your step is complete, to "
        "CLARIFY when its directive was ambiguous, or to ESCALATE when "
        "you are stuck; it is the single point the chain returns to."
    ),
    "call_designer": (
        "Call the Designer.  The ``message`` argument IS the hand-off "
        "text the Designer will see — write it as free-form prose.  It "
        "authors the complete parameter set AND runs the generation / "
        "render tools itself, so state the qualitative direction you "
        "want (\"increase <param X>\") rather than concrete numbers."
    ),
    "call_creator": (
        "Call the Creator.  The ``message`` argument IS the hand-off text "
        "the Creator will see — write it as free-form prose.  It authors "
        "the complete parameter set AND self-validates it before writing, "
        "so state the qualitative direction you want (\"increase <param "
        "X>\") rather than concrete numbers."
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
    session: "Session",
):
    """Build a ``call_<target_key>`` tool for the agent named ``caller_key``.

    The tool closes over ``session`` so that invoking it appends an
    exchange dict directly to ``session.chain_log_exchanges`` — same
    uniform pattern every other piece of agent state uses (no extra
    wrapper class).  Closing over ``caller_agent`` lets the tool
    record the next-hop on that exact agent instance, even when agents
    are rebuilt per turn (the Orchestrator re-runs ``_wire_routing``
    each construction so each new agent gets fresh closures).
    """
    caller_display = AGENT_DISPLAY.get(caller_key, caller_key)
    target_display = AGENT_DISPLAY.get(target_key, target_key)
    tool_name = f"call_{target_key}"
    description = _TOOL_DESCRIPTIONS.get(
        tool_name, f"Call the {target_display} with a short hand-off message."
    )

    def _invoke(message: str) -> str:
        # Returning to the hub is not a chain exchange, so it is not
        # recorded in the chain log.  Resolved per call rather than per
        # build so a topology switch cannot leave a stale hub captured in
        # the closure.
        if target_key != _hub_key():
            session.chain_log_exchanges.append({
                "from_agent": caller_display,
                "to_agent": target_display,
                "message": message,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        _log_inter_agent_message(caller_display, target_display, message)
        # The Receptionist -> hub hop is traced by ``dispatch.py`` with a
        # richer "forwarded" note; skip the routing-tool trace here to
        # avoid a duplicate entry.
        #
        # Hub-aware ONLY because ``dispatch_turn`` is topology-neutral and
        # emits ``_trace("Receptionist", hub_display(), "forwarded")`` for
        # whichever hub is active.  These two must move together: making
        # this hub-aware without that emitter would silently DELETE the
        # Receptionist -> Conductor trace rather than de-duplicate it.
        if not (caller_key == "receptionist" and target_key == _hub_key()):
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
    """Build the AgentHop used when a stuck loop is detected.

    Targets the ACTIVE topology's hub.  Hard-coding ``"orchestrator"``
    sent the 5-agent chain's failure path to an agent that topology never
    builds — and the callers (Creator, Tool Caller, User Input Inspector)
    all run there, so the escalation route was broken exactly when it was
    needed.
    """
    return AgentHop(
        _hub_key(),
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
