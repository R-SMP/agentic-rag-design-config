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

from agents.shared import topology as _topology
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

# Tools whose payload goes to the log IN FULL when
# ``LOG_FULL_TOOL_PAYLOADS`` is on.  The rule: a file's content is logged
# ONCE, where it is created — never again where it is read back.
#
# So the WRITERS get their ARGS.  A writer's result is a one-line receipt
# ("Wrote extracted_inputs.txt (7628 chars)") while the content it wrote
# sits in its args, so uncapping a writer's result would achieve nothing.
# Every reader stays capped: ``read_attempts``, ``read_extracted_inputs``
# and ``read_user_inputs`` all re-read text the log already holds in full.
#
# The two image tools are the exception, because their result is not a
# re-read of anything — OCR text and the record of what an agent was
# actually shown exist nowhere else.
_FULL_RESULT_TOOLS: frozenset[str] = frozenset({
    "view_images",
    "reread_text_regions",
})
# ``write_parameters`` is the 5-/3-agent name for ``new_attempt_parameters``.
_FULL_ARG_TOOLS: frozenset[str] = frozenset({
    "write_extraction",
    "new_attempt_parameters",
    "write_parameters",
})


def _log_full_payloads() -> bool:
    """True iff the operator wants uncut payloads for the tools above.

    Read fresh on every call so flipping the setting takes effect without
    a restart, and import-guarded so a settings problem can never break a
    tool call.
    """
    try:
        from workflow_settings import settings as workflow_settings
        return bool(getattr(workflow_settings, "LOG_FULL_TOOL_PAYLOADS", True))
    except Exception:  # noqa: BLE001 — never break a tool over settings
        return True


def _format(obj) -> str:
    """Render *obj* as a readable string for logs."""
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, default=repr, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(obj)


def _truncate(obj, limit: int) -> str:
    """Render *obj* for the log, cut to *limit* chars; ``limit <= 0`` = uncut."""
    text = _format(obj)
    if limit <= 0 or len(text) <= limit:
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
    full = _log_full_payloads()
    args_str = _truncate(
        args,
        0 if full and tool_name in _FULL_ARG_TOOLS else _TOOL_CALL_ARG_TRUNC,
    )
    result_str = _truncate(
        result,
        0 if full and tool_name in _FULL_RESULT_TOOLS else _TOOL_CALL_RESULT_TRUNC,
    )
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
    # NOTE this table is the identity registry: ``ROUTING_TOOL_NAMES`` below
    # and ``session.KNOWN_AGENT_KEYS`` both derive from it, and
    # ``AgentState`` validates against it.  Nothing iterates it to BUILD
    # agents, so a topology that does not use a key simply never constructs
    # it.  The 5-agent Conductor and Creator were removed on 2026-08-31 when
    # topology 5 was rebuilt around the Planner and the DC Input Creator;
    # ``session.RETIRED_AGENT_KEYS`` still tolerates them in archived
    # snapshots.
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
    # A topology that ships an overlay owns this table outright -- the same
    # override-then-REPLACE contract the prompt tree uses, not a merge.  The
    # generic fallback below still covers a tool the active table omits.
    descriptions = _topology.overlay_value(
        "TOOL_DESCRIPTIONS", _TOOL_DESCRIPTIONS)
    description = descriptions.get(
        tool_name, f"Call the {target_display} with a short hand-off message."
    )

    def _invoke(message: str) -> str:
        message = _carry_over_prose(caller_agent, message, caller_display)
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


# ---------------------------------------------------------------------------
# Routing retry — one second chance after a prose-only turn
#
# The six CHAIN agents must end every turn with a routing tool call; prose
# alone is discarded.  Historically the first prose reply aborted the turn
# with an error hop and the agent was never told.  These three helpers give
# it ONE nudge instead, and are called EXPLICITLY from each agent's run
# loop rather than from BaseChainAgent, so the behaviour stays visible and
# tunable per agent.  The Receptionist and the Orchestrator do not use them:
# for those two a prose reply IS the user-facing answer.
# ---------------------------------------------------------------------------

ROUTING_RETRY_NUDGE = (
    "Your last response contained no routing tool call, so it was NOT "
    "delivered to anyone.  End this turn by invoking one of your routing "
    "tools."
)


def routing_retry_enabled() -> bool:
    """Whether the one-shot routing retry is on, read disk-fresh.

    Read through ``getattr`` with a default so an older settings.py that
    predates the flag still imports.
    """
    from workflow_settings import settings as _ws

    return bool(getattr(_ws, "ROUTING_RETRY_ENABLED", True))


def begin_routing_retry(agent, prose: str, agent_label: str) -> bool:
    """Start the ONE permitted retry after a prose-only turn.

    Appends the nudge to *agent*'s history and stashes *prose* so the next
    routing call can fall back to it (see :func:`_carry_over_prose`).

    Returns True when the caller should ``continue`` its run loop, and
    False when it should fall through to its existing error hop — because
    the flag is off, or the single retry is already spent this turn.
    """
    if not routing_retry_enabled():
        return False
    if getattr(agent, "_routing_retry_used", False):
        return False
    agent._routing_retry_used = True
    # Index of the prose AIMessage the caller appended just before its
    # no-tool-call check; the nudge lands directly after it.  Both are
    # removed again by ``finish_routing_retry`` once the retry routes.
    agent._routing_retry_mark = len(agent.messages) - 1
    agent._routing_retry_prose = prose
    # Imported here, not at module scope: this module is imported by
    # langchain-free consumers (extra_utilities/smoke_test_topology_
    # fragments.py stubs only ``langchain_core.tools``), and a second
    # top-level langchain_core import would break them.
    from langchain_core.messages import HumanMessage

    agent.messages.append(HumanMessage(content=ROUTING_RETRY_NUDGE))
    logger.warning(
        f"[{agent_label}]  no routing tool call — nudging once and "
        f"re-invoking (ROUTING_RETRY_ENABLED)."
    )
    return True


def finish_routing_retry(agent) -> None:
    """Drop the prose turn and the nudge once the retry has routed.

    Identity-checked rather than index-trusted: the run loop may prune
    history or flush image blocks between the nudge and the retry, and
    deleting the wrong two messages would corrupt the tool_call /
    tool_result pairing.  When the check fails the messages are simply
    left in place — a slightly longer history is harmless, a broken one
    is not.

    A no-op for the overwhelming majority of turns, where no retry ran.
    """
    mark = getattr(agent, "_routing_retry_mark", None)
    agent._routing_retry_mark = None
    agent._routing_retry_prose = None
    if mark is None or mark < 0 or mark + 1 >= len(agent.messages):
        return
    if getattr(agent.messages[mark + 1], "content", None) != ROUTING_RETRY_NUDGE:
        return
    del agent.messages[mark:mark + 2]


def _carry_over_prose(agent, message: str, caller_display: str) -> str:
    """Substitute a retried agent's own prose for a thinner hand-off.

    After a prose-only turn the agent is nudged and re-invoked.  It may
    then route with a ``message`` far thinner than the reasoning it wrote
    a moment earlier, silently dropping it.  When the new hand-off is
    shorter than that prose, send the prose instead: the routing tool the
    agent chose still decides WHERE the hand-off goes, so only the thin
    sentence is discarded.

    Called at the TOP of the routing tool, before the chain log, the
    session log and the trace are written, so all three and the recipient
    agree on what was actually sent.  One-shot, and inert for every agent
    that did not retry.
    """
    prose = getattr(agent, "_routing_retry_prose", None)
    if not prose:
        return message
    agent._routing_retry_prose = None
    if len(message.strip()) >= len(prose.strip()):
        return message
    logger.info(
        f"[{caller_display}]  retried hand-off ({len(message.strip())} chars) "
        f"was thinner than the prose it retried from "
        f"({len(prose.strip())} chars) — sending the prose instead."
    )
    return prose


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
