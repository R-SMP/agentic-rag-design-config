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
from datetime import datetime
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage

from agents.database_handler import DatabaseHandler
from agents.dc_input_creator import DCInputCreator
from agents.dc_input_inspector import DCInputInspector
from agents.dc_output_inspector import DCOutputInspector
from agents.planner import Planner
from agents.receptionist import Receptionist
from agents.shared.attempts_tool import list_attempts, new_attempt, read_attempt
from agents.shared.context_pruner import ContextPruner
from agents.shared.file_utils import ai_text
from agents.shared.history_tool import build_read_agent_history_tool
from agents.shared.llm_provider import build_llm, make_system_message
from agents.shared.llm_retry import invoke_with_retry
from agents.shared.prompts import ORCHESTRATOR_TEMPLATE, PLANNER_FIRST
from agents.shared.routing_tools import (
    AGENT_DISPLAY,
    AgentHop,
    ChainLog,
    DONE,
    ROUTING_TOOL_NAMES,
    build_routing_tool,
    log_tool_call,
)
from agents.shared.trace import trace as _trace
from agents.step_caps import (
    MAX_DISPATCH_HOPS,
    MAX_ORCH_INNER_STEPS,
    MAX_ORCHESTRATOR_STEPS,
)
from agents.tool_caller import ToolCaller
from agents.user_input_inspector import UserInputInspector
from tools.calculate.calculate import calculate

AGENT_KEY = "orchestrator"

logger = logging.getLogger("propeller_agent")


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


class Orchestrator:
    """Central orchestrator, wired up as a regular chain agent.

    Each agent (including the Orchestrator) builds its own LLM via
    ``build_llm(<agent_key>)``.  This means a per-agent ``.env`` file
    can override which provider / model that one agent uses, without
    affecting the others (see ``agents/shared/llm_provider.py``).
    """

    def __init__(
        self,
        mesh_checks: bool,
        rag_enabled: bool,
        dc_inspector_enabled: bool = True,
        chain_access: bool = False,
        keep_images_in_context: bool = False,
        dcoi_comparison_mode: int = 3,
    ):
        self.rag_enabled = rag_enabled
        self.dc_inspector_enabled = dc_inspector_enabled
        self.mesh_checks = mesh_checks
        # DCOI comparison source(s) for this session — see
        # _DCOI_COMPARISON_MODE_* blocks in dc_output_inspector.py.
        self.dcoi_comparison_mode = dcoi_comparison_mode
        # When True, inter-agent messages exchanged while the
        # Orchestrator was waiting are prepended to its next incoming
        # message so it can see what the sub-agents said to each other.
        # When False, the Orchestrator only sees the hand-off text.
        # The session .log records every exchange in either case.
        self.chain_access = chain_access
        # When True, image content blocks loaded by an agent persist in
        # that agent's history across hand-offs (alongside paired
        # ``Loaded image (path: …):`` text blocks).  When False, image
        # blocks are stripped at every operation hand-off and only the
        # paired path-text blocks survive.  Forwarded into the
        # image-loading sub-agents (DCOI, UII, Receptionist).
        self.keep_images_in_context = keep_images_in_context

        # Shared chain log — reset at the start of every user turn
        self.chain_log = ChainLog()

        # The Orchestrator's own LLM
        self.base_llm, self.provider, self.model = build_llm(AGENT_KEY)

        # Build every sub-agent (each builds its own LLM via build_llm).
        # All chain agents that can load images (Receptionist, Planner,
        # UII, DCIC, DCII, DCOI) receive the keep_images_in_context
        # flag so their on_operation_end hooks know whether to strip
        # image bytes after each operation.  Receptionist has no image
        # bytes to strip in practice (it is only ever fed text + paired
        # notes via load_user_inputs_bundle(include_image_bytes=False)),
        # but it owns the hook for symmetry with the bypass path.
        self.planner = Planner(
            rag_enabled,
            keep_images_in_context=keep_images_in_context,
        )
        self.receptionist = Receptionist(
            keep_images_in_context=keep_images_in_context,
        )
        self.user_input_inspector = UserInputInspector(
            keep_images_in_context=keep_images_in_context,
        )
        self.dc_input_creator = DCInputCreator(
            keep_images_in_context=keep_images_in_context,
        )
        self.dc_input_inspector = DCInputInspector(
            keep_images_in_context=keep_images_in_context,
        )
        self.dc_output_inspector = DCOutputInspector(
            keep_images_in_context=keep_images_in_context,
            dcoi_comparison_mode=dcoi_comparison_mode,
        )
        self.tool_caller = ToolCaller(mesh_checks)
        # Context Pruner shares the Orchestrator's LLM (cheaper than
        # spinning up a 9th provider build).  Currently constructed but
        # not invoked by the dispatcher — see KNOWN_ISSUES.
        self.context_pruner = ContextPruner(self.base_llm)
        # Database Handler — runs ONLY post-session, after the user
        # types ``quit`` and confirms saving.  Not part of the
        # dispatch loop, has no routing tools, never speaks to the
        # user.  Held here so the loader can reach it via the
        # Orchestrator instance.
        self.database_handler = DatabaseHandler()

        # Orchestrator's own state
        self.messages: list = []
        self._tools_by_name: dict = {}
        self._pending_hop: AgentHop | None = None
        chain_access_block = (
            _CHAIN_ACCESS_ON if chain_access else _CHAIN_ACCESS_OFF
        )
        self.system_prompt = ORCHESTRATOR_TEMPLATE.format(
            chain_access_block=chain_access_block,
        )
        self.llm = self.base_llm  # re-bound in _wire_routing

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
        cl = self.chain_log

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
                name = tc["name"]
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
        orch_chain_log_cursor = 0
        orch_visits = 0
        first_orch_entry = True

        for _ in range(MAX_DISPATCH_HOPS):
            agent = self._agents_by_key.get(current)
            if agent is None:
                return f"Dispatch error: unknown agent key '{current}'."

            if current == "orchestrator":
                if self.chain_access and not first_orch_entry:
                    new_exchanges = self.chain_log.exchanges[
                        orch_chain_log_cursor:
                    ]
                    if new_exchanges:
                        block_lines = [
                            "--- Inter-agent messages recorded while you "
                            "were waiting ---"
                        ]
                        for fa, ta, msg in new_exchanges:
                            block_lines.append(
                                f"\n[FROM {fa}, TO {ta}]:\n{msg}"
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
                orch_chain_log_cursor = len(self.chain_log.exchanges)

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

        exchanges = self.chain_log.exchanges
        if exchanges:
            summary_lines.append("Route taken (compact):")
            for fa, ta, msg in exchanges[-20:]:
                snippet = _first_line(msg, limit=180)
                summary_lines.append(f"  - {fa} -> {ta}: {snippet}")
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
        """Reset per-turn state (call at the start of each user turn)."""
        self.chain_log.reset()

    def reset(self) -> None:
        """Clear all agent histories for a fresh start."""
        self.messages.clear()
        self.chain_log.reset()
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
        if tm_name or tm_id:
            lines.append(f"[tool_result] name={tm_name}  id={tm_id}")

        content = _format_message_content(getattr(msg, "content", ""))
        if content:
            lines.append(content)
        lines.append("")

    return "\n".join(lines)
