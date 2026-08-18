"""Tool Caller agent — executes design tools as instructed.

Stateful agent with THREE kinds of tools bound to its LLM:

- **Read tool** (``read_parameters``) — loads the parameter JSON
  from the path supplied in the incoming hand-off.  Non-terminal.
- **Utility tools** (``generate_and_render_propeller`` — builds the
  mesh AND renders/checks it in one call — ``calculate``,
  ``list_attempts``, ``read_attempt``) — these do actual work and the
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
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

from agents.shared.agent_activity import generic_tool
from agents.shared.attempts_tool import list_attempts, read_attempt
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.file_utils import ai_text
from agents.shared.llm_provider import (
    history_cache_control,
    make_system_message,
)
from agents.shared.llm_retry import invoke_with_retry
from agents.shared import token_usage
from agents.shared.prompts import (
    RENDER_CHECK_LIBRARY_PYVISTA,
    RENDER_CHECK_LIBRARY_OFF,
    RENDER_CHECK_LIBRARY_TRIMESH,
    _build_template,
    routing_instructions,
)
from agents.shared.routing_tools import (
    AgentHop,
    ROUTING_TOOL_NAMES,
    finalize_unanswered_tool_calls,
    log_tool_call,
    stuck_escalation,
    tool_call_signature,
)
from agents.shared.retrieve_tool_dispatcher import dispatch_retrieve_tool
from agents.shared.stop_signal import check_stop_or_raise
from agents.shared.session import AgentState, Session
from agents.step_caps import MAX_TC_STEPS
from tools import get_render_library, get_tools
from tools.database_search.database_search import make_database_search_tool
from tools.retrieve_attempt.retrieve_attempt import make_retrieve_attempt_tool
from tools.retrieve_user_inputs.retrieve_user_inputs import (
    make_retrieve_user_inputs_tool,
)
from tools.render_blade_sections.render_blade_sections import render_blade_sections
from workflow_settings import blade_sections_access, database_access

logger = logging.getLogger("propeller_agent")


# ---------------------------------------------------------------------------
# Read tool schema (actual read handled by ToolCaller)
# ---------------------------------------------------------------------------

@tool
def read_parameters(path: str) -> str:
    """Read the parameter JSON.

    Pass the absolute path supplied by the previous agent under the
    ``Parameters file:`` label.  Returns the file content as text.  Do
    NOT call this tool with a guessed path."""
    return ""  # Actual read is performed by _handle_read_parameters_tool.


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
        self._read_tool = read_parameters
        # Utility tools span the design generators (the active render
        # library is picked by ``set_render_library`` before this agent
        # is built) and the session-scoped attempt-inspection helpers;
        # both are dispatched the same way so they share one map.
        utility_tools = list(get_tools()) + [list_attempts, read_attempt]
        if database_access.is_enabled_for("tool_caller"):
            utility_tools.append(make_database_search_tool("tool_caller"))
            utility_tools.append(make_retrieve_user_inputs_tool("tool_caller"))
            utility_tools.append(make_retrieve_attempt_tool("tool_caller"))
        # Blade-sections visualizer (global toggle, Tool Caller only).  Read
        # fresh so a Workflow-Settings edit takes effect next session.
        if blade_sections_access.is_enabled():
            utility_tools.append(render_blade_sections)
        self._extra_utility_tools_by_name = {t.name: t for t in utility_tools}
        self.mesh_checks = session.mesh_checks
        self.render_library = get_render_library()
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
        """Bind read + utility + routing tools and build the system prompt."""
        all_tools = (
            [self._read_tool]
            + list(self._extra_utility_tools_by_name.values())
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
        # Mesh checks OFF => the render step emits no metrics at all
        # (render_mesh.py:281 guards the findings, :329 the summary), so a
        # backend's metric semantics would describe a report this agent
        # never receives.  Gated HERE rather than with <<MESH_ON>> markers
        # because .format() runs AFTER apply_flag_filters — a marker inside
        # the injected fragment would never be filtered.
        render_check_block = (
            (
                RENDER_CHECK_LIBRARY_PYVISTA
                if self.render_library == "pyvista"
                else RENDER_CHECK_LIBRARY_TRIMESH
            )
            if self.mesh_checks
            else RENDER_CHECK_LIBRARY_OFF
        )
        # Built fresh at construction time so live edits to .md
        # fragments via the System Prompts UI take effect on the
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
                return AgentHop(
                    "orchestrator",
                    "Error: Tool Caller produced a response with no routing "
                    "tool call — it wrote prose but did not invoke "
                    "call_dc_output_inspector / call_orchestrator, so the "
                    "pipeline would otherwise halt silently.  Its raw text "
                    f"was:\n\n{final}",
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
                if name == "read_parameters":
                    self._handle_read_parameters_tool(tc)
                    continue

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
                return self._pending_hop

        return AgentHop(
            "orchestrator",
            "Error: Tool Caller reached maximum steps without completing.",
        )

    # ------------------------------------------------------------------
    # read_parameters handler
    # ------------------------------------------------------------------

    @generic_tool("Read parameters")
    def _handle_read_parameters_tool(self, tc: dict) -> None:
        """Read parameters.json at the supplied path."""
        raw_path = tc.get("args", {}).get("path")

        if not isinstance(raw_path, str) or not raw_path.strip():
            summary = (
                "Error: missing or non-string 'path' argument.  Call "
                "this tool with the absolute path supplied by the "
                "previous agent under the 'Parameters file:' label."
            )
        else:
            path = Path(raw_path)
            if not path.is_file():
                summary = (
                    f"Error: '{raw_path}' is not an existing file.  Do "
                    f"not retry with a guessed path; ESCALATE if no "
                    f"valid path was supplied."
                )
            else:
                try:
                    content = path.read_text(encoding="utf-8")
                except OSError as exc:
                    summary = f"Error reading '{raw_path}': {exc}"
                else:
                    if not content.strip():
                        summary = (
                            f"Warning: '{raw_path}' exists but is empty.  "
                            f"ESCALATE."
                        )
                    else:
                        summary = (
                            f"Loaded parameters from {path.resolve()} "
                            f"({len(content)} chars).\n\n"
                            f"--- DC Parameters ---\n{content}"
                        )

        log_tool_call(
            "tool_caller", tc["name"], tc.get("args"), summary,
        )
        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    def reset(self) -> None:
        self.messages.clear()
