"""Orchestrator agent — horizontal coordinator in the agent pipeline.

The Orchestrator is a regular agent like any other.  It exposes a
``run(message) -> AgentHop`` method and its LLM is bound to a set of
``call_<agent>`` routing tools.  When its LLM invokes one of those
tools, the intended next hop is recorded on the Orchestrator's
instance and its run loop exits — just like every other chain agent.
No run loop is ever nested inside another.

The Orchestrator also owns :meth:`dispatch`, the top-level driver.
``dispatch(kickoff_message)`` enters the Orchestrator once, receives
its hop, invokes the chosen agent, receives ITS hop, invokes the next,
and so on — a flat horizontal loop.  When any agent hops to
``receptionist`` (or to any target that returns a ``DONE`` hop) the
dispatcher terminates and returns the user-facing text.  When an
agent hops to ``orchestrator``, the dispatcher simply re-enters the
Orchestrator's persistent run loop with a fresh ``HumanMessage``; the
Python call stack never grows.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage

from agents.database_handler import DatabaseHandler
from agents.dc_input_creator import DCInputCreator
from agents.dc_input_inspector import DCInputInspector
from agents.dc_output_inspector import DCOutputInspector
from agents.planner import Planner
from agents.receptionist import Receptionist
from agents.shared.attempts_tool import list_attempts, new_attempt, read_attempt
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.context_pruner import ContextPruner
from agents.shared.file_utils import ai_text
from agents.shared.history_tool import build_read_agent_history_tool
from agents.shared.llm_provider import make_system_message
from agents.shared.llm_retry import invoke_with_retry
from agents.shared.prompts import _build_template, PLANNER_FIRST
from agents.shared.stop_signal import is_stop_requested
from agents.shared.routing_tools import (
    AGENT_DISPLAY,
    AgentHop,
    DONE,
    ROUTING_TOOL_NAMES,
    build_routing_tool,
    log_tool_call,
)
from agents.shared.session import AgentState, Session
from agents.shared import standing_directives
from agents.shared.trace import trace as _trace
from agents.step_caps import (
    MAX_DISPATCH_HOPS,
    MAX_ORCH_INNER_STEPS,
    MAX_ORCHESTRATOR_STEPS,
)
from agents.shared.retrieve_tool_dispatcher import dispatch_retrieve_tool
from agents.shared.stop_signal import check_stop_or_raise
from agents.tool_caller import ToolCaller
from agents.user_input_inspector import UserInputInspector
from tools.calculate.calculate import calculate
from tools.database_search.database_search import make_database_search_tool
from tools.retrieve_attempt.retrieve_attempt import make_retrieve_attempt_tool
from tools.retrieve_user_inputs.retrieve_user_inputs import (
    make_retrieve_user_inputs_tool,
)
from workflow_settings import database_access

logger = logging.getLogger("propeller_agent")


# Component C — the chain agents that must carry a standing directive forward
# (everyone a Planner directive is meant to reach).  Excludes the Orchestrator +
# Receptionist (mediators / user-facing) and the User; the Orchestrator re-stamps
# on its OUTGOING hop, so a block dropped on the way INTO it is not lost.
_DIRECTIVE_CARRIERS = frozenset({
    "user_input_inspector", "planner", "dc_input_creator",
    "dc_input_inspector", "tool_caller", "dc_output_inspector",
})


_ROLE4_INSTRUCTIONS_PATH = Path(__file__).parent / "role4_feedback_instructions.md"


def _load_role4_instructions() -> str:
    """Role-4 (end-of-session feedback distribution) instructions.

    Held in a sibling ``.md`` and injected into the feedback-round trigger
    message ONLY when that pass runs (see ``run_feedback_round``) — so the
    ~100-line block no longer ships in the Orchestrator's live-pipeline
    system prompt on every turn.
    """
    return _ROLE4_INSTRUCTIONS_PATH.read_text(encoding="utf-8")


_CHAIN_ACCESS_ON = """\
## Inter-agent communication visibility (ENABLED)
Whenever control returns to you (a new incoming message from the
dispatcher), the message is prefixed with every inter-agent exchange
that took place while you were waiting, under a clearly labelled
``--- Inter-agent messages recorded while you were waiting ---``
block, followed by the actual hand-off content.  Use this chain-log
block to understand the reasoning path the sub-agents took.  Do NOT
repeat it back verbatim to other agents or to the Receptionist; it is
for your own situational awareness."""

_CHAIN_ACCESS_OFF = """\
## Inter-agent communication visibility (DISABLED)
You only see the hand-off message the dispatcher hands back to you;
messages exchanged between other agents while you were waiting are not
surfaced to you.  If you need more detail about what happened inside
the chain, escalate to the Planner with the evidence you do have."""


class Orchestrator(BaseChainAgent):
    """Central orchestrator, wired up as a regular chain agent.

    Subclasses ``BaseChainAgent`` so it shares the (state, session,
    *, llm_cache) construction signature, the snapshot/restore
    plumbing, and the LLM-cache lookup with every other chain agent.
    The dispatch loop (``dispatch``) and chain-agent registry
    (``_agents_by_key``) are Orchestrator-specific.
    """

    AGENT_KEY = "orchestrator"

    def __init__(
        self,
        state: AgentState | None = None,
        session: Session | None = None,
        *,
        llm_cache=None,
    ):
        if session is None:
            raise TypeError(
                "Orchestrator now requires a Session.  Construct one "
                "via Session(...) or Session.create_for_v3(...) and "
                "pass it in."
            )
        if state is None:
            state = session.agent_states.setdefault(
                "orchestrator", AgentState(agent_key="orchestrator"),
            )
        super().__init__(state=state, session=session, llm_cache=llm_cache)

        # Orchestrator-specific config flags read from session.  Held
        # on self so existing call sites that read self.* keep working
        # without touching session.* directly.
        self.rag_enabled = session.rag_enabled
        self.dc_inspector_enabled = session.dc_inspector_enabled
        self.mesh_checks = session.mesh_checks
        self.dcoi_comparison_mode = session.dcoi_comparison_mode
        self.chain_access = session.chain_access

        # The chain log lives on session.chain_log_exchanges (per
        # v3 Phase 1 Q1 — session-scoped, not per-turn).  Routing
        # tools and dispatch read/write it directly via self.session.

        # Build every chain agent via the (state, session) path.
        # Each one's per-agent state is materialised into
        # session.agent_states under its own agent_key so subsequent
        # turns can rebuild the live agent from the snapshot.
        def _state_for(agent_key: str) -> AgentState:
            return session.agent_states.setdefault(
                agent_key, AgentState(agent_key=agent_key),
            )

        self.planner = Planner(
            state=_state_for("planner"), session=session,
        )
        self.receptionist = Receptionist(
            state=_state_for("receptionist"), session=session,
        )
        self.user_input_inspector = UserInputInspector(
            state=_state_for("user_input_inspector"), session=session,
        )
        self.dc_input_creator = DCInputCreator(
            state=_state_for("dc_input_creator"), session=session,
        )
        self.dc_input_inspector = DCInputInspector(
            state=_state_for("dc_input_inspector"), session=session,
        )
        self.dc_output_inspector = DCOutputInspector(
            state=_state_for("dc_output_inspector"), session=session,
        )
        self.tool_caller = ToolCaller(
            state=_state_for("tool_caller"), session=session,
        )
        # Context Pruner shares the Orchestrator's LLM (cheaper than
        # spinning up a 9th provider build).  Exposed on the Session so
        # every chain agent's
        # ``BaseChainAgent.prune_history_if_needed`` can reach it via
        # ``self.session.context_pruner`` without needing a back-
        # reference to the Orchestrator.  Pre-invoke pruning is gated
        # by ``workflow_settings.CONTEXT_PRUNER_ENABLED``.
        self.context_pruner = ContextPruner(self.base_llm)
        setattr(session, "context_pruner", self.context_pruner)
        # Database Handler — runs ONLY post-session, after the user
        # types ``quit`` and confirms saving.  Not part of the
        # dispatch loop, has no routing tools, never speaks to the
        # user.  Held here so the loader can reach it via the
        # Orchestrator instance.  As of v3 Phase 1 commit 6, the DH
        # is a BaseChainAgent like every other agent, takes
        # (state, session), and reads from session.agent_states.
        self.database_handler = DatabaseHandler(
            state=_state_for("database_handler"), session=session,
        )

        # Orchestrator-specific extras (BaseChainAgent already set
        # self.messages / self._pending_hop / self.llm / self.base_llm).
        self._tools_by_name: dict = {}
        chain_access_block = (
            _CHAIN_ACCESS_ON if session.chain_access else _CHAIN_ACCESS_OFF
        )
        # Built fresh at construction time so live edits to .md
        # fragments via the System Prompts UI take effect on the
        # NEXT session without a Python restart.
        self.system_prompt = _build_template("orchestrator").format(
            chain_access_block=chain_access_block,
        )

        # Registry for the dispatch driver
        self._agents_by_key: dict = {
            "orchestrator":         self,
            "planner":              self.planner,
            "user_input_inspector": self.user_input_inspector,
            "dc_input_creator":     self.dc_input_creator,
            "dc_input_inspector":   self.dc_input_inspector,
            "tool_caller":          self.tool_caller,
            "dc_output_inspector":  self.dc_output_inspector,
            "receptionist":         self.receptionist,
        }

        # Wire every agent's routing tools (including the Orchestrator's own)
        self._wire_routing()

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def _wire_routing(self) -> None:
        """Build per-agent tool sets and bind them.

        Each agent gets ONLY the routing tools it is allowed to use.
        ``build_routing_tool`` binds each tool to its CALLER: invoking
        the tool records an ``AgentHop`` on the caller's
        ``_pending_hop`` attribute; the dispatcher reads that hop once
        the caller's run loop exits.

        The tool table adapts to whether the DC Input Inspector is
        enabled: when it is, DCIC → DCII → TC; when it is not, DCIC →
        TC directly (and TC's ``prev`` becomes the DCIC).
        """
        # build_routing_tool now closes over the Session so it can
        # append exchanges directly to session.chain_log_exchanges
        # (per v3 Phase 1 commit 5; chain log is session-scoped).
        cl = self.session

        # Shared history-reading tool — bound to this Orchestrator's live
        # history provider.
        history_tool = build_read_agent_history_tool(self.get_agent_messages)

        # Planner — FORWARD target depends on PLANNER_FIRST.
        #   PF_ON:  FORWARD → UII, RETURN → Orchestrator
        #   PF_OFF: FORWARD → DCIC, CLARIFY → UII, RETURN → Orchestrator
        if PLANNER_FIRST:
            planner_tools = [
                build_routing_tool("planner", "user_input_inspector",
                                   self.planner, cl),
                build_routing_tool("planner", "orchestrator",
                                   self.planner, cl),
            ]
        else:
            planner_tools = [
                build_routing_tool("planner", "dc_input_creator",
                                   self.planner, cl),
                build_routing_tool("planner", "user_input_inspector",
                                   self.planner, cl),
                build_routing_tool("planner", "orchestrator",
                                   self.planner, cl),
            ]
        self.planner.set_routing_tools(
            tools=planner_tools,
            history_tool=history_tool,
        )

        # Receptionist — bound to read_agent_history (for answering
        # simple questions alone) and to call_orchestrator (so it can
        # forward a new user message into the pipeline by invoking the
        # tool, instead of relying on code-word parsing of its reply).
        self.receptionist.set_tools([
            history_tool,
            build_routing_tool(
                "receptionist", "orchestrator", self.receptionist, cl,
            ),
        ])

        # UII — neighbours depend on PLANNER_FIRST.
        #   PF_ON:  FORWARD → DCIC, CLARIFY → Planner, ESCALATE → Orchestrator
        #   PF_OFF: FORWARD → Planner,                 ESCALATE → Orchestrator
        if PLANNER_FIRST:
            uii_tools = [
                build_routing_tool("user_input_inspector", "dc_input_creator",
                                   self.user_input_inspector, cl),
                build_routing_tool("user_input_inspector", "planner",
                                   self.user_input_inspector, cl),
                build_routing_tool("user_input_inspector", "orchestrator",
                                   self.user_input_inspector, cl),
            ]
            uii_next_agent = "DC Input Creator"
        else:
            uii_tools = [
                build_routing_tool("user_input_inspector", "planner",
                                   self.user_input_inspector, cl),
                build_routing_tool("user_input_inspector", "orchestrator",
                                   self.user_input_inspector, cl),
            ]
            uii_next_agent = "Planner"
        self.user_input_inspector.set_routing_tools(
            tools=uii_tools,
            next_agent=uii_next_agent,
        )

        # DCIC — FORWARD target depends on whether DCII is enabled;
        # CLARIFY-back target depends on PLANNER_FIRST.
        if self.dc_inspector_enabled:
            dcic_forward_tool = build_routing_tool(
                "dc_input_creator", "dc_input_inspector",
                self.dc_input_creator, cl,
            )
            dcic_next_agent = "DC Input Inspector"
        else:
            dcic_forward_tool = build_routing_tool(
                "dc_input_creator", "tool_caller",
                self.dc_input_creator, cl,
            )
            dcic_next_agent = "Tool Caller"

        if PLANNER_FIRST:
            dcic_clarify_tool = build_routing_tool(
                "dc_input_creator", "user_input_inspector",
                self.dc_input_creator, cl,
            )
        else:
            dcic_clarify_tool = build_routing_tool(
                "dc_input_creator", "planner",
                self.dc_input_creator, cl,
            )

        self.dc_input_creator.set_routing_tools(
            tools=[
                dcic_forward_tool,
                dcic_clarify_tool,
                build_routing_tool("dc_input_creator", "orchestrator",
                                   self.dc_input_creator, cl),
            ],
            next_agent=dcic_next_agent,
        )

        # DCII — always wired (its tools are unused when it is not called)
        self.dc_input_inspector.set_routing_tools([
            build_routing_tool("dc_input_inspector", "tool_caller",
                               self.dc_input_inspector, cl),
            build_routing_tool("dc_input_inspector", "dc_input_creator",
                               self.dc_input_inspector, cl),
            build_routing_tool("dc_input_inspector", "orchestrator",
                               self.dc_input_inspector, cl),
        ])

        # Tool Caller — prev depends on whether DCII is enabled
        if self.dc_inspector_enabled:
            tc_prev_tool_obj = build_routing_tool(
                "tool_caller", "dc_input_inspector",
                self.tool_caller, cl,
            )
            tc_prev_agent = "DC Input Inspector"
        else:
            tc_prev_tool_obj = build_routing_tool(
                "tool_caller", "dc_input_creator",
                self.tool_caller, cl,
            )
            tc_prev_agent = "DC Input Creator"

        self.tool_caller.set_routing_tools(
            tools=[
                build_routing_tool("tool_caller", "dc_output_inspector",
                                   self.tool_caller, cl),
                tc_prev_tool_obj,
                build_routing_tool("tool_caller", "orchestrator",
                                   self.tool_caller, cl),
            ],
            prev_agent=tc_prev_agent,
        )

        # DC Output Inspector — CLARIFY to TC, RETURN/ESCALATE to Orchestrator
        self.dc_output_inspector.set_routing_tools([
            build_routing_tool("dc_output_inspector", "tool_caller",
                               self.dc_output_inspector, cl),
            build_routing_tool("dc_output_inspector", "orchestrator",
                               self.dc_output_inspector, cl),
        ])

        # Orchestrator — can call every chain agent plus the Receptionist
        orch_tools = [
            build_routing_tool("orchestrator", "planner", self, cl),
            build_routing_tool("orchestrator", "user_input_inspector",
                               self, cl),
            build_routing_tool("orchestrator", "dc_input_creator", self, cl),
            build_routing_tool("orchestrator", "tool_caller", self, cl),
            build_routing_tool("orchestrator", "dc_output_inspector",
                               self, cl),
            build_routing_tool("orchestrator", "receptionist", self, cl),
            calculate,
            list_attempts,
            read_attempt,
            new_attempt,
        ]
        if database_access.is_enabled_for("orchestrator"):
            orch_tools.append(make_database_search_tool("orchestrator"))
            orch_tools.append(make_retrieve_user_inputs_tool("orchestrator"))
            orch_tools.append(make_retrieve_attempt_tool("orchestrator"))
        if self.dc_inspector_enabled:
            orch_tools.insert(
                4,
                build_routing_tool("orchestrator", "dc_input_inspector",
                                   self, cl),
            )
        self._tools_by_name = {t.name: t for t in orch_tools}
        self.llm = self.base_llm.bind_tools(orch_tools)

    # ------------------------------------------------------------------
    # Run loop — terminal on every routing tool (horizontal dispatch)
    # ------------------------------------------------------------------

    def run(self, message: str) -> AgentHop:
        """Process one incoming message and return the chosen hop."""
        self._pending_hop = None
        self.messages.append(HumanMessage(content=message))

        for _ in range(MAX_ORCH_INNER_STEPS):
            check_stop_or_raise()
            self.prune_history_if_needed()
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + self.messages,
                "Orchestrator",
            )
            self.messages.append(response)

            rendered_content = ai_text(response.content)
            if rendered_content:
                logger.info(f"[ORCHESTRATOR]  {rendered_content}")

            if not response.tool_calls:
                final = rendered_content
                if not final or not final.strip():
                    final = (
                        "The Orchestrator produced no user-facing text "
                        "this turn (empty response from the model).  "
                        "This is likely a coordination bug; please "
                        "re-send your last request."
                    )
                return AgentHop(DONE, final)

            routed = False
            for tc in response.tool_calls:
                check_stop_or_raise()
                name = tc["name"]
                # Phase 5E: retrieve_* tools are dispatcher-handled
                # (their @tool stubs return "" — the dispatcher does
                # the real R2 work and appends the ToolMessage +
                # image content blocks).  Catch them before the
                # _tools_by_name lookup so the stub never runs.
                if dispatch_retrieve_tool(self, tc, "orchestrator"):
                    continue
                tool_fn = self._tools_by_name.get(name)
                if tool_fn is None:
                    result = f"Error: unknown tool '{name}'"
                else:
                    try:
                        result = tool_fn.invoke(tc["args"])
                    except Exception as exc:
                        result = f"Error calling {name}: {exc}"
                        logger.error(f"[ORCH TOOL ERROR] {name}: {exc}")

                if name not in ROUTING_TOOL_NAMES:
                    log_tool_call(
                        "orchestrator", name, tc.get("args"), result,
                    )

                self.messages.append(ToolMessage(
                    content=str(result),
                    tool_call_id=tc["id"],
                    name=name,
                ))
                if name in ROUTING_TOOL_NAMES and self._pending_hop is not None:
                    routed = True
                    break

            if routed:
                return self._pending_hop

        # The inner loop exhausted its budget without routing or
        # producing plain text.  Bail out as DONE so the dispatcher
        # does not loop indefinitely.
        return AgentHop(
            DONE,
            "Orchestrator produced no routing decision this turn.",
        )

    # ------------------------------------------------------------------
    # Dispatcher — the top-level horizontal driver
    # ------------------------------------------------------------------

    def dispatch(self, kickoff_message: str,
                 start_agent_key: str = "orchestrator") -> str:
        """Run the horizontal dispatch loop and return the user-facing text."""
        current = start_agent_key
        message = kickoff_message
        # Component C: a standing directive is issued fresh each user turn
        # (the Planner re-derives it from the extraction when still relevant),
        # so a stale directive from a prior turn is never forced onto — or
        # leaked by — an unrelated later turn.  Within-turn persistence is
        # unaffected: capture happens later in THIS dispatch and the field is
        # session-scoped for the rest of the loop.
        self.session.standing_directives = ""
        # Cursor into the SESSION-scoped chain log.  Initialised to the
        # log's current length so the per-turn chain-access view shows
        # only exchanges produced during THIS dispatch call, not prior
        # turns' exchanges (per v3 Phase 1 Q1: chain_log is session-
        # scoped, but the Orchestrator's "what happened while I was
        # waiting" feature stays per-turn).
        orch_chain_log_cursor = len(self.session.chain_log_exchanges)
        orch_visits = 0
        first_orch_entry = True

        for _ in range(MAX_DISPATCH_HOPS):
            # Cooperative-stop check: the web UI's Stop button sets
            # the shared flag, and we honour it at each hop boundary
            # (the currently-running step has already finished by the
            # time we get back here).  We surface a clear message to
            # the user and return — the next /api/turn auto-clears
            # the flag so subsequent turns proceed normally.
            if is_stop_requested():
                logger.warning(
                    "[DISPATCH] Stop requested by user — halting pipeline "
                    f"at hop into '{current}'"
                )
                _trace(current, "User", "stopped by user")
                return (
                    "(Session interrupted by Stop button — the pipeline "
                    "halted after the last completed step.  Send a new "
                    "message to continue.)"
                )

            agent = self._agents_by_key.get(current)
            if agent is None:
                return f"Dispatch error: unknown agent key '{current}'."

            if current == "orchestrator":
                if self.chain_access and not first_orch_entry:
                    new_exchanges = self.session.chain_log_exchanges[
                        orch_chain_log_cursor:
                    ]
                    if new_exchanges:
                        block_lines = [
                            "--- Inter-agent messages recorded while you "
                            "were waiting ---"
                        ]
                        for ex in new_exchanges:
                            block_lines.append(
                                f"\n[FROM {ex['from_agent']}, "
                                f"TO {ex['to_agent']}]:\n{ex['message']}"
                            )
                        block_lines.append(
                            "\n--- End of inter-agent messages; hand-off "
                            "below ---"
                        )
                        message = (
                            "\n".join(block_lines) + "\n\n" + message
                        )
                first_orch_entry = False
                orch_visits += 1
                if orch_visits > MAX_ORCHESTRATOR_STEPS:
                    logger.warning("[DISPATCH] Max orchestrator steps reached")
                    return self._surface_limit_to_user(
                        "max Orchestrator visits"
                    )

            hop = agent.run(message)

            # Operation-end hook (Change #2).  An "operation" ends when
            # an agent's run() returns — i.e. the LLM invoked a routing
            # tool (or otherwise handed off).  Utility tool calls
            # inside run() do NOT trigger this since run() doesn't
            # return until the LLM routes.  Image-consuming agents use
            # this to strip image bytes from history when KEEP IMAGES
            # IN CONTEXT is OFF, leaving paired path-text blocks
            # behind.  Non-image agents (and image agents in KEEP=ON
            # mode) just no-op.
            on_op_end = getattr(agent, "on_operation_end", None)
            if callable(on_op_end):
                try:
                    on_op_end()
                except Exception as exc:  # pragma: no cover
                    logger.warning(
                        f"[DISPATCH] on_operation_end failed for "
                        f"{current}: {exc}"
                    )

            if current == "orchestrator":
                orch_chain_log_cursor = len(self.session.chain_log_exchanges)

            if not isinstance(hop, AgentHop):
                # Defensive guard — every agent must return AgentHop.
                return str(hop)

            # [AGENT MSG] is normally emitted by the routing tool when the
            # LLM invokes it.  When an agent's run loop returns an
            # orchestrator-bound hop WITHOUT having invoked the tool
            # (error fall-through, step-limit exhaustion, empty
            # tool_calls), the routing-tool logger never fires.  Emit the
            # log line here so mid-chain resumes are still visible in the
            # session log.
            if (
                hop.target == "orchestrator"
                and current != "orchestrator"
                and getattr(agent, "_pending_hop", None) is None
            ):
                source_display = AGENT_DISPLAY.get(current, current)
                logger.info(
                    f"[AGENT MSG]  {source_display} -> Orchestrator\n"
                    f"{hop.message}"
                )
                _trace(source_display, "Error, Escalated to Orchestrator")

            if hop.target == DONE:
                return hop.message

            # Component C: capture a Planner-issued standing directive, then
            # re-stamp it onto any forward hand-off that dropped it (the loss
            # backstop).  The directive is verbose text carried IN the messages,
            # not a flag; only the Planner may set one.  ensure_present is a
            # no-op when nothing is active or the block is still intact — so it
            # re-stamps ONLY on detected loss.
            if current == "planner":
                _issued = standing_directives.extract_directive(hop.message)
                if _issued:
                    self.session.standing_directives = _issued
            if hop.target in _DIRECTIVE_CARRIERS:
                hop.message = standing_directives.ensure_present(
                    hop.message, self.session.standing_directives
                )

            current = hop.target
            message = hop.message

        logger.warning("[DISPATCH] Max dispatch hops reached")
        return self._surface_limit_to_user("max dispatch hops")

    # ------------------------------------------------------------------
    # Surfacing step-limit termination to the user
    # ------------------------------------------------------------------

    def _surface_limit_to_user(self, reason_label: str) -> str:
        """Build a technical summary and let the Receptionist relay it."""
        summary_lines: list[str] = [
            "The design workflow was halted before completion.",
            f"Reason: {reason_label} reached.",
            "",
        ]

        exchanges = self.session.chain_log_exchanges
        if exchanges:
            summary_lines.append("Route taken (compact):")
            for ex in exchanges[-20:]:
                snippet = _first_line(ex["message"], limit=180)
                summary_lines.append(
                    f"  - {ex['from_agent']} -> {ex['to_agent']}: {snippet}"
                )
            summary_lines.append("")

        dcoi_msg = _last_text_message(self.dc_output_inspector)
        if dcoi_msg:
            summary_lines.append("Last DC Output Inspector verdict:")
            summary_lines.append(_truncate(dcoi_msg, 800))
            summary_lines.append("")

        tc_msg = _last_text_message(self.tool_caller)
        if tc_msg:
            summary_lines.append("Last Tool Caller report:")
            summary_lines.append(_truncate(tc_msg, 800))
            summary_lines.append("")

        plan = getattr(self.planner, "current_plan", "")
        if plan:
            summary_lines.append("Latest Planner plan:")
            summary_lines.append(_truncate(plan, 600))
            summary_lines.append("")

        summary = "\n".join(summary_lines).rstrip()
        last_attempted = ""
        if exchanges:
            fa, ta, msg = exchanges[-1]
            last_attempted = f"{fa} -> {ta}: {_first_line(msg, limit=160)}"

        fallback = (
            f"The Orchestrator could not settle a plan within its step "
            f"budget ({reason_label}); this is likely a coordination bug."
        )
        if last_attempted:
            fallback += f"  Last attempted action: {last_attempted}"

        try:
            composed = self.receptionist.run(summary).message
        except Exception as exc:
            logger.error(f"[DISPATCH SURFACE ERROR] {exc}")
            composed = ""

        if not composed or not composed.strip():
            return fallback
        return composed

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def reset_turn(self) -> None:
        """Reset per-turn state (call at the start of each user turn).

        Vestigial in v3: the chain log is session-scoped (per Phase 1
        Q1) and the per-turn "what happened while I was waiting" view
        is reconstructed via a cursor inside ``dispatch`` rather than
        by clearing anything.  Kept as a no-op so the loader's call
        site stays stable; remove together with the loader call when
        the v3 loader rewrite lands.
        """
        return None

    def reset(self) -> None:
        """Clear all agent histories for a fresh start."""
        self.messages.clear()
        self.session.chain_log_exchanges.clear()
        self.session.standing_directives = ""
        self.planner.reset()
        self.receptionist.reset()
        self.user_input_inspector.reset()
        self.dc_input_creator.reset()
        self.dc_input_inspector.reset()
        self.dc_output_inspector.reset()
        self.tool_caller.reset()

    # ------------------------------------------------------------------
    # Live agent-history access (used by the read_agent_history tool)
    # ------------------------------------------------------------------

    _AGENT_KEY_ALIASES: dict = {
        "planner": "planner",
        "user input inspector": "user_input_inspector",
        "user_input_inspector": "user_input_inspector",
        "uii": "user_input_inspector",
        "dc input creator": "dc_input_creator",
        "dc_input_creator": "dc_input_creator",
        "dcic": "dc_input_creator",
        "dc input inspector": "dc_input_inspector",
        "dc_input_inspector": "dc_input_inspector",
        "dcii": "dc_input_inspector",
        "dc output inspector": "dc_output_inspector",
        "dc_output_inspector": "dc_output_inspector",
        "dcoi": "dc_output_inspector",
        "tool caller": "tool_caller",
        "tool_caller": "tool_caller",
        "tc": "tool_caller",
        "receptionist": "receptionist",
        "orchestrator": "orchestrator",
    }

    def get_agent_messages(
        self,
        agent_name: str,
        last_n: int | None = None,
    ) -> str:
        """Return a formatted dump of *agent_name*'s message history."""
        if not isinstance(agent_name, str):
            return "Error: 'agent_name' must be a string."
        key = self._AGENT_KEY_ALIASES.get(agent_name.strip().lower())
        if key is None:
            valid = sorted(self._agents_by_key)
            return (
                f"Error: unknown agent '{agent_name}'.  Valid names: "
                f"{', '.join(valid)}."
            )
        agent = self._agents_by_key.get(key)
        messages = getattr(agent, "messages", None)
        if not messages:
            return f"No history recorded for agent '{key}' yet."
        if isinstance(last_n, int) and last_n > 0:
            messages = messages[-last_n:]
        return _format_agent_history(key, messages, sys_prompt=None)

    # ------------------------------------------------------------------
    # End-of-session feedback distribution (Role 4)
    # ------------------------------------------------------------------

    def run_feedback_round(
        self,
        *,
        satisfaction: str,
        what_went_well: str,
        what_went_wrong: str,
    ) -> dict:
        """Drive the Orchestrator through ONE forced ``submit_feedback_dispatch``
        tool call that decides, per chain agent, whether the user's
        end-of-session feedback contains material worth forwarding to
        that agent — and if so, what exact text to forward.

        Side effect on success: for every dispatch with ``send=True``,
        appends a ``HumanMessage(content=message, name="orchestrator")``
        to the target's LIVE ``self.messages`` AND mirrors the agent's
        new ``snapshot_state()`` into ``self.session.agent_states[<key>]``.
        The Database Handler reads from the session's ``agent_states``
        when interviewing each agent post-session, so the feedback
        becomes part of that interview's context.

        This method DOES NOT mutate the Orchestrator's own
        ``self.messages`` — the feedback round is a separate
        post-session pass, NOT part of the live design pipeline.  The
        tool is bound for ONE turn only (W18 / W20 force-tool pattern)
        and discarded immediately afterwards; the permanent ``orch_tools``
        binding installed by ``_wire_routing`` is untouched.

        Args:
            satisfaction:    "yes" / "partially" / "no" — the y/p/n
                             toggle the user picked in the End Session
                             modal.
            what_went_well:  Free-text field, may be empty when the
                             user didn't elaborate.
            what_went_wrong: Free-text field, may be empty.

        Returns:
            ``{"ok": bool, "decisions": [{"agent_key", "send", "message"}, ...],
               "error": str | None}``.  When the LLM call or tool-call
            parsing fails, ``ok`` is False and ``decisions`` is empty.
        """
        from agents.orchestrator.feedback_tool import (
            submit_feedback_dispatch,
            SUBMIT_FEEDBACK_DISPATCH_TOOL_NAME,
        )

        # Target set: every chain agent in the registry except the
        # Orchestrator itself (the Orchestrator collects/dispatches,
        # never receives feedback).  Adapts to ``dc_inspector_enabled``
        # automatically because DCII is only inserted into
        # ``_agents_by_key`` when enabled... actually DCII is ALWAYS in
        # the registry (orchestrator.py:188-197) but its routing tools
        # are only wired when enabled — so we explicitly drop it from
        # the feedback target set when disabled to avoid forwarding
        # feedback to a dormant agent.
        target_keys: list[str] = []
        for k in self._agents_by_key.keys():
            if k == "orchestrator":
                continue
            if k == "dc_input_inspector" and not self.dc_inspector_enabled:
                continue
            target_keys.append(k)

        # Build the per-turn forced-tool LLM binding.  This is a LOCAL
        # binding — it does NOT mutate self.llm (which is the
        # permanently-tool-bound design-pipeline LLM).  W20 mirrors
        # the DH's W18 invariant: this tool is never on self.llm.
        try:
            feedback_llm = self.base_llm.bind_tools(
                [submit_feedback_dispatch],
                tool_choice=SUBMIT_FEEDBACK_DISPATCH_TOOL_NAME,
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                f"[ORCHESTRATOR-FEEDBACK]  could not bind "
                f"submit_feedback_dispatch: {type(exc).__name__}: "
                f"{exc}; treating as empty dispatch list."
            )
            return {"ok": False, "decisions": [], "error": str(exc)}

        # Compose the instruction message.  This is a TRANSIENT message
        # list (we do NOT append to self.messages) so the design
        # pipeline's history stays clean.  The Role-4 instructions live in
        # a sibling .md (injected here by CONCATENATION — not str.format —
        # so its literal JSON braces survive) rather than in the live
        # system prompt; prepend them, then add the user's three fields
        # plus the live target list.
        ww = (what_went_well or "").strip() or "(no text supplied)"
        ww_wrong = (what_went_wrong or "").strip() or "(no text supplied)"
        targets_md = ", ".join(target_keys)

        live_data = (
            "--- THIS SESSION'S FEEDBACK ---\n\n"
            f"Satisfaction (y/partial/n): {(satisfaction or '').strip() or '(unset)'}\n"
            f"What worked well: {ww}\n"
            f"What did NOT work: {ww_wrong}\n\n"
            "Target agents (emit exactly one dispatch each, any order): "
            f"{targets_md}\n\n"
            "Emit the submit_feedback_dispatch call now."
        )
        instruction = HumanMessage(
            content=_load_role4_instructions() + "\n\n" + live_data
        )

        try:
            response = invoke_with_retry(
                feedback_llm,
                [make_system_message(self.system_prompt, self.provider)]
                + [instruction],
                "Orchestrator-feedback-dispatch",
            )
        except Exception as exc:
            logger.warning(
                f"[ORCHESTRATOR-FEEDBACK]  LLM call raised "
                f"{type(exc).__name__}: {exc}; treating as empty "
                f"dispatch list."
            )
            return {"ok": False, "decisions": [], "error": str(exc)}

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            logger.warning(
                "[ORCHESTRATOR-FEEDBACK]  response carried no tool_calls "
                "despite tool_choice=submit_feedback_dispatch; "
                "treating as empty dispatch list."
            )
            return {"ok": False, "decisions": [], "error": "no_tool_call"}

        tc = tool_calls[0]
        args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
        dispatches = (args or {}).get("dispatches") or []
        if not isinstance(dispatches, list):
            logger.warning(
                f"[ORCHESTRATOR-FEEDBACK]  expected `dispatches` to be "
                f"a list; got {type(dispatches).__name__!r}."
            )
            dispatches = []

        applied: list[dict] = []
        seen_keys: set[str] = set()
        for d in dispatches:
            if not isinstance(d, dict):
                continue
            ak  = str(d.get("agent_key") or "").strip()
            snd = bool(d.get("send", False))
            msg = str(d.get("message") or "").strip()
            if ak not in target_keys:
                logger.warning(
                    f"[ORCHESTRATOR-FEEDBACK]  dispatch agent_key "
                    f"{ak!r} not in target set; skipping."
                )
                continue
            if ak in seen_keys:
                logger.warning(
                    f"[ORCHESTRATOR-FEEDBACK]  duplicate dispatch for "
                    f"{ak!r}; keeping the first one."
                )
                continue
            seen_keys.add(ak)
            if not snd or not msg:
                applied.append({"agent_key": ak, "send": False, "message": ""})
                continue

            # Append to the LIVE agent so dump_histories sees it, then
            # mirror via snapshot_state() into session.agent_states so
            # the DH's per-agent interview sees it too (the DH reads
            # session.agent_states[<key>].messages, NOT the live agent
            # instances).
            target = self._agents_by_key.get(ak)
            if target is None:  # pragma: no cover — defensive
                continue
            try:
                target.messages.append(
                    HumanMessage(content=msg, name="orchestrator")
                )
                self.session.agent_states[ak] = target.snapshot_state()
            except Exception as exc:
                logger.warning(
                    f"[ORCHESTRATOR-FEEDBACK]  could not append "
                    f"feedback to {ak!r}: {type(exc).__name__}: {exc}"
                )
                applied.append({"agent_key": ak, "send": False, "message": ""})
                continue
            applied.append({"agent_key": ak, "send": True, "message": msg})

        # Surface a summary in the session log so the operator can see
        # which agents received feedback at a glance.
        sent = [d["agent_key"] for d in applied if d.get("send")]
        skipped = [d["agent_key"] for d in applied if not d.get("send")]
        logger.info(
            f"[ORCHESTRATOR-FEEDBACK]  round complete — "
            f"sent={sent or '[]'}  skipped={skipped or '[]'}"
        )
        return {"ok": True, "decisions": applied, "error": None}

    # ------------------------------------------------------------------
    # Per-agent history dump
    # ------------------------------------------------------------------

    def dump_histories(self, output_dir) -> list:
        """Write each agent's message history to its own text file."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        agents = [
            ("orchestrator",         self,                       self.system_prompt),
            ("planner",              self.planner,               getattr(self.planner, "system_prompt", None)),
            ("receptionist",         self.receptionist,          getattr(self.receptionist, "system_prompt", None)),
            ("user_input_inspector", self.user_input_inspector,  getattr(self.user_input_inspector, "system_prompt", None)),
            ("dc_input_creator",     self.dc_input_creator,      getattr(self.dc_input_creator, "system_prompt", None)),
            ("dc_input_inspector",   self.dc_input_inspector,    getattr(self.dc_input_inspector, "system_prompt", None)),
            ("dc_output_inspector",  self.dc_output_inspector,   getattr(self.dc_output_inspector, "system_prompt", None)),
            ("tool_caller",          self.tool_caller,           getattr(self.tool_caller, "system_prompt", None)),
        ]

        written: list = []
        for name, agent, sys_prompt in agents:
            messages = getattr(agent, "messages", None)
            if messages is None:
                continue
            path = output_dir / f"history_{name}.txt"
            path.write_text(
                _format_agent_history(name, messages, sys_prompt),
                encoding="utf-8",
            )
            written.append(path)
        return written


# ---------------------------------------------------------------------------
# Limit-surfacing helpers
# ---------------------------------------------------------------------------

def _first_line(text: str, limit: int = 180) -> str:
    """Return the first non-empty line of *text*, truncated to *limit*."""
    if not isinstance(text, str):
        text = str(text)
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:limit] + ("..." if len(line) > limit else "")
    return ""


def _truncate(text: str, limit: int) -> str:
    if not isinstance(text, str):
        text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]"


def _last_text_message(agent) -> str:
    """Return the most recent textual content produced by *agent*."""
    messages = getattr(agent, "messages", None) or []
    for msg in reversed(messages):
        content = getattr(msg, "content", "")
        rendered = _format_message_content(content).strip()
        if rendered:
            return rendered
    return ""


# ---------------------------------------------------------------------------
# History-dump helpers
# ---------------------------------------------------------------------------

def _format_message_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        rendered = []
        for block in content:
            if isinstance(block, dict):
                btype = block.get("type", "?")
                if btype == "text":
                    rendered.append(block.get("text", ""))
                elif btype in {"image", "image_url"}:
                    rendered.append(f"<{btype} block omitted>")
                else:
                    rendered.append(f"<{btype} block: {list(block.keys())}>")
            else:
                rendered.append(str(block))
        return "\n".join(rendered)
    return str(content)


def _format_agent_history(agent_name: str, messages: list, sys_prompt) -> str:
    lines: list = []
    lines.append(f"=== History for agent: {agent_name} ===")
    lines.append(f"Dumped at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Message count: {len(messages)}")
    lines.append("")

    if sys_prompt:
        lines.append("--- System Prompt ---")
        lines.append(str(sys_prompt))
        lines.append("")

    for i, msg in enumerate(messages, start=1):
        msg_type = type(msg).__name__
        lines.append(f"=== Message {i} : {msg_type} ===")
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                tc_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "?")
                tc_args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                lines.append(f"[tool_call] {tc_name}  args={tc_args}")
        tm_name = getattr(msg, "name", None)
        tm_id = getattr(msg, "tool_call_id", None)
        # Disambiguate the label based on the message type:
        #   * ToolMessage (has tool_call_id) → "[tool_result] name=... id=..."
        #   * Any other message with name= set (e.g. a HumanMessage
        #     appended by the Orchestrator at end-of-session feedback
        #     round) → "[from <name>]" — NOT "[tool_result]", which
        #     was misleading.
        if tm_id:
            lines.append(f"[tool_result] name={tm_name}  id={tm_id}")
        elif tm_name:
            lines.append(f"[from {tm_name}]")

        content = _format_message_content(getattr(msg, "content", ""))
        if content:
            lines.append(content)
        lines.append("")

    return "\n".join(lines)
