"""Tool Caller agent — executes design tools as instructed.

Stateful agent with TWO kinds of tools bound to its LLM:

- **Utility tools** (``generate_and_render_propeller`` — builds the
  mesh AND renders/checks it in one call — ``calculate``,
  ``read_attempts``) — these do actual work and the
  run loop keeps going after them, letting the LLM call more tools
  before finally producing a response + routing call.
- **Routing tools** (``call_dc_output_inspector``,
  ``call_dc_input_creator`` when DCII is skipped, otherwise
  ``call_dc_input_inspector``, ``call_orchestrator``) — these are
  terminal: when the LLM invokes one, the run loop returns
  immediately with the recorded hop.

The Tool Caller does NOT auto-load parameters.json — the path is
supplied by the previous agent (DCII when enabled, otherwise DCIC) in
its FORWARD message under a ``Parameters file:`` label.
"""

import logging

from langchain_core.messages import HumanMessage, ToolMessage

from agents.shared.attempts_tool import read_attempts
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.file_utils import ai_text
from agents.shared.llm_provider import (
    history_cache_control,
    make_system_message,
)
from agents.shared.llm_retry import invoke_with_retry
from agents.shared import token_usage
from agents.shared.prompts import (
    _build_template,
    read_pack_fragment,
    routing_instructions,
)
from agents.shared.routing_tools import (
    AgentHop,
    ROUTING_TOOL_NAMES,
    begin_routing_retry,
    finalize_unanswered_tool_calls,
    finish_routing_retry,
    log_tool_call,
    stuck_escalation,
    tool_call_signature,
)
from agents.shared.retrieve_tool_dispatcher import dispatch_retrieve_tool
from agents.shared.stop_signal import check_stop_or_raise
from agents.shared.topology import hub_key as _hub_key
from agents.shared.session import AgentState, Session
from agents.step_caps import MAX_TC_STEPS
from tools.calculate.calculate import calculate
from agents.shared.dba_tools import dba_tools_for
from agents.shared.dc_params_tool import param_tools_for
from engine import pack_tools

logger = logging.getLogger("mas_agent")


# ---------------------------------------------------------------------------
# Read tool schema (actual read handled by ToolCaller)
# ---------------------------------------------------------------------------

class ToolCaller(BaseChainAgent):
    """Stateful agent with read + utility + routing tools."""

    AGENT_KEY = "tool_caller"

    def __init__(
        self,
        state: AgentState | None = None,
        session: Session | None = None,
        *,
        llm_cache=None,
    ):
        if session is None:
            raise TypeError(
                "ToolCaller now requires a Session.  Construct one "
                "via Session(...) or Session.create_for_v3(...) and "
                "pass it in."
            )
        if state is None:
            state = AgentState(agent_key=self.AGENT_KEY)
        super().__init__(state=state, session=session, llm_cache=llm_cache)
        # Utility tools span the pack's generators (bound by role: this
        # agent is the tool runner -- engine/pack_tools.py), the calculator
        # and the session-scoped attempt-inspection helpers; all are
        # dispatched the same way so they share one map.
        utility_tools = (pack_tools.agent_tools(self.AGENT_KEY, ("generator",))
                         + [calculate, read_attempts])
        # Which of the three database tools this agent holds is a
        # per-(profile, agent, tool) decision; dba_tools_for owns it.
        utility_tools.extend(dba_tools_for("tool_caller"))
        # The pack's other tools for this role (the blade-sections
        # visualizer), each only while its Workflow Settings switch is on.
        utility_tools.extend(pack_tools.agent_tools(self.AGENT_KEY, ("helper",)))
        # dc_params_list, when this agent's parameter-access cell says
        # "tool" (engine/parameter_access.py).
        utility_tools.extend(param_tools_for(self.AGENT_KEY))
        self._extra_utility_tools_by_name = {t.name: t for t in utility_tools}
        self._routing_tools_by_name: dict = {}
        self.system_prompt: str = ""

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def set_routing_tools(
        self,
        tools: list,
        prev_agent: str,
    ) -> None:
        """Bind the utility + routing tools and build the system prompt."""
        all_tools = (
            list(self._extra_utility_tools_by_name.values())
            + list(tools)
        )
        self.llm = self.base_llm.bind_tools(all_tools)
        self._routing_tools_by_name = {t.name: t for t in tools}
        routing_block = routing_instructions(
            agent_name="Tool Caller",
            next_agent="DC Output Inspector",
            prev_agent=prev_agent,
            fragment_name="routing_tool_caller.md",
        )
        # The tool that declares this placeholder (runtime_blocks in its
        # tool.yaml) says which of its slots fills it, from the settings the
        # session started with.  Filled HERE rather than with markers because
        # ``.format()`` runs AFTER apply_flag_filters -- a marker inside the
        # injected fragment would never be filtered -- and read here, per
        # session, because the Sessions Queue switches topology between runs
        # inside one process.
        render_check_block = read_pack_fragment(
            pack_tools.runtime_block_slot(
                "render_check_library_block", self.session.tool_settings))
        # Built fresh at construction time so live edits to .md
        # fragments on disk take effect on the
        # NEXT session without a Python restart.
        self.system_prompt = _build_template("tool_caller").format(
            routing_instructions=routing_block,
            render_check_library_block=render_check_block,
        )

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    def run(self, message: str) -> AgentHop:
        """Process one hand-off message."""
        token_usage.begin_turn("ToolCaller")
        self._pending_hop = None
        self._routing_retry_used = False
        text = f"Hand-off from previous agent:\n{message}"
        self.messages.append(HumanMessage(content=text))

        seen_sigs: set[tuple[str, str]] = set()

        for _ in range(MAX_TC_STEPS):
            check_stop_or_raise()
            self.prune_history_if_needed()
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + self.messages,
                "Tool Caller",
                cache_control=history_cache_control(self.provider),
            )
            self.messages.append(response)

            if not response.tool_calls:
                final = ai_text(response.content)
                if begin_routing_retry(self, final, "ToolCaller"):
                    continue
                bound = " / ".join(sorted(self._routing_tools_by_name)) \
                    or "any routing tool"
                return AgentHop(
                    _hub_key(),
                    "Error: Tool Caller produced a response with no routing "
                    "tool call — it wrote prose but did not invoke "
                    f"{bound}, so the pipeline would otherwise halt "
                    f"silently.  Its raw text was:\n\n{final}",
                )

            routed = False
            for i, tc in enumerate(response.tool_calls):
                check_stop_or_raise()
                name = tc["name"]
                if name not in self._routing_tools_by_name:
                    sig = tool_call_signature(tc)
                    if sig in seen_sigs:
                        finalize_unanswered_tool_calls(
                            self.messages, response.tool_calls, i,
                        )
                        return stuck_escalation("Tool Caller", name)
                    seen_sigs.add(sig)
                # Phase 5E: retrieve_* tools are dispatcher-handled
                # (their @tool stubs return "" — the dispatcher does
                # the real R2 work and appends the ToolMessage +
                # image content blocks).  Catch them before the
                # routing/utility lookups so the stub never runs.
                if dispatch_retrieve_tool(self, tc, "tool_caller"):
                    continue

                if name in self._routing_tools_by_name:
                    tool_fn = self._routing_tools_by_name[name]
                elif name in self._extra_utility_tools_by_name:
                    tool_fn = self._extra_utility_tools_by_name[name]
                else:
                    tool_fn = None

                if tool_fn is None:
                    result = f"Error: Unknown tool '{name}'"
                else:
                    try:
                        result = tool_fn.invoke(tc["args"])
                    except Exception as exc:
                        result = f"Error calling {name}: {exc}"
                        logger.error(f"[TC TOOL ERROR] {name}: {exc}")

                if name in self._extra_utility_tools_by_name:
                    log_tool_call("tool_caller", name, tc.get("args"), result)

                self.messages.append(ToolMessage(
                    content=str(result),
                    tool_call_id=tc["id"],
                    name=name,
                ))
                if name in ROUTING_TOOL_NAMES and self._pending_hop is not None:
                    routed = True
                    finalize_unanswered_tool_calls(
                        self.messages, response.tool_calls, i + 1,
                    )
                    break

            if routed:
                finish_routing_retry(self)
                return self._pending_hop

        return AgentHop(
            _hub_key(),
            "Error: Tool Caller reached maximum steps without completing.",
        )


    def reset(self) -> None:
        self.messages.clear()
