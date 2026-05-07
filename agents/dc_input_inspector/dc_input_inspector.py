"""DC Input Inspector agent — validates DC parameters against requirements.

Stateful agent.  Receives a hand-off from the DC Input Creator that
carries two absolute paths (the parameters file and the extracted-
inputs file).  The DCII then calls TWO utility tools:

1. ``read_parameters(path)`` loads the parameter JSON written by the
   DC Input Creator.
2. ``read_extracted_inputs(path)`` loads the structured extraction
   written by the User Input Inspector (relayed through the DCIC's
   hand-off).

This agent is optional and can be skipped at setup time.  When it is
enabled, it sits between DC Input Creator and Tool Caller in the
natural pipeline.
"""

import json
import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

from agents.shared.attempts_tool import list_attempts, read_attempt
from agents.shared.file_utils import (
    ai_text,
    flush_pending_image_blocks,
    strip_image_blocks_from_messages,
)
from agents.shared.llm_provider import build_llm, make_system_message
from agents.shared.llm_retry import invoke_with_retry
from agents.shared.prompts import DCII_TEMPLATE, routing_instructions
from agents.shared.routing_tools import (
    AgentHop,
    ROUTING_TOOL_NAMES,
    finalize_unanswered_tool_calls,
    log_tool_call,
    stuck_escalation,
    tool_call_signature,
)
from agents.shared.user_inputs_tool import (
    USER_INPUTS_TOOLS,
    dispatch_user_inputs_tool,
)
from agents.step_caps import MAX_DCII_STEPS
from tools.calculate.calculate import calculate

AGENT_KEY = "dc_input_inspector"

logger = logging.getLogger("propeller_agent")


# ---------------------------------------------------------------------------
# Utility tool schemas (actual I/O handled by DCInputInspector)
# ---------------------------------------------------------------------------

@tool
def read_parameters(path: str) -> str:
    """Read the parameter JSON written by the DC Input Creator.

    Pass the absolute path supplied by the DCIC under the
    ``Parameters file:`` label.  Returns the file content as text (the
    JSON is not parsed — you read it directly).  Do NOT call this tool
    with a guessed path."""
    return ""  # Actual read is performed by _handle_read_parameters_tool.


@tool
def read_extracted_inputs(path: str) -> str:
    """Read the structured user-input extraction.

    Pass the absolute path supplied by the DCIC under the
    ``Extracted inputs file:`` label (originally written by the UII).
    Returns the full three-section extraction as text.  Do NOT call
    this tool with a guessed path."""
    return ""  # Actual read is performed by _handle_read_extraction_tool.


class DCInputInspector:
    """Stateful agent that validates DC parameters."""

    def __init__(self, keep_images_in_context: bool = False):
        self.base_llm, self.provider, self.model = build_llm(AGENT_KEY)
        self.keep_images_in_context = keep_images_in_context
        self._read_params_tool = read_parameters
        self._read_extraction_tool = read_extracted_inputs
        self.llm = self.base_llm
        self.messages: list = []
        self._routing_tools_by_name: dict = {}
        self._extra_utility_tools_by_name: dict = {}
        self.system_prompt: str = ""
        self._pending_hop: AgentHop | None = None

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def set_routing_tools(self, tools: list) -> None:
        """Bind the DC Input Inspector's utility + routing tools."""
        self._extra_utility_tools_by_name = {
            calculate.name: calculate,
            list_attempts.name: list_attempts,
            read_attempt.name: read_attempt,
        }
        all_tools = (
            [self._read_params_tool, self._read_extraction_tool]
            + list(self._extra_utility_tools_by_name.values())
            + list(USER_INPUTS_TOOLS)
            + list(tools)
        )
        self.llm = self.base_llm.bind_tools(all_tools)
        self._routing_tools_by_name = {t.name: t for t in tools}
        routing_block = routing_instructions(
            agent_name="DC Input Inspector",
            next_agent="Tool Caller",
            prev_agent="DC Input Creator",
            fragment_name="routing_dc_input_inspector.md",
        )
        self.system_prompt = DCII_TEMPLATE.format(
            routing_instructions=routing_block,
        )

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    def run(self, message: str) -> AgentHop:
        """Process one hand-off message and return the chosen hop."""
        self._pending_hop = None
        text = f"Hand-off from DC Input Creator:\n{message}"
        self.messages.append(HumanMessage(content=text))

        seen_sigs: set[tuple[str, str]] = set()

        for _ in range(MAX_DCII_STEPS):
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + self.messages,
                "DCII",
            )
            self.messages.append(response)

            if not response.tool_calls:
                final = ai_text(response.content)
                return AgentHop(
                    "orchestrator",
                    "Error: DC Input Inspector produced a response with no "
                    "routing tool call — it wrote prose but did not invoke "
                    "call_tool_caller / call_dc_input_creator / "
                    "call_orchestrator, so the pipeline would otherwise halt "
                    f"silently.  Its raw text was:\n\n{final}",
                )

            routed = False
            for i, tc in enumerate(response.tool_calls):
                name = tc["name"]
                if name not in self._routing_tools_by_name:
                    sig = tool_call_signature(tc)
                    if sig in seen_sigs:
                        finalize_unanswered_tool_calls(
                            self.messages, response.tool_calls, i,
                        )
                        return stuck_escalation("DC Input Inspector", name)
                    seen_sigs.add(sig)
                if name == "read_parameters":
                    self._handle_read_parameters_tool(tc)
                    continue
                if name == "read_extracted_inputs":
                    self._handle_read_extraction_tool(tc)
                    continue
                if dispatch_user_inputs_tool(self, tc, "dc_input_inspector"):
                    continue
                if name in self._extra_utility_tools_by_name:
                    tool_fn = self._extra_utility_tools_by_name[name]
                    try:
                        result = tool_fn.invoke(tc["args"])
                    except Exception as exc:
                        result = f"Error calling {name}: {exc}"
                        logger.error(f"[DCII TOOL ERROR] {name}: {exc}")
                    log_tool_call(
                        "dc_input_inspector", name, tc.get("args"), result,
                    )
                    self.messages.append(ToolMessage(
                        content=str(result),
                        tool_call_id=tc["id"],
                        name=name,
                    ))
                    continue
                if name in self._routing_tools_by_name:
                    tool_fn = self._routing_tools_by_name[name]
                    try:
                        result = tool_fn.invoke(tc["args"])
                    except Exception as exc:
                        result = f"Error calling {name}: {exc}"
                        logger.error(f"[DCII TOOL ERROR] {name}: {exc}")
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
                else:
                    self.messages.append(ToolMessage(
                        content=f"Error: unknown tool '{name}'",
                        tool_call_id=tc["id"],
                        name=name,
                    ))

            # Flush any pending image content blocks as a single
            # trailing HumanMessage AFTER all ToolMessages for this
            # AIMessage are appended.  Preserves the tool_use →
            # tool_result contiguity rule on Anthropic / OpenAI.
            flush_pending_image_blocks(self)

            if routed:
                return self._pending_hop

        return AgentHop(
            "orchestrator",
            "Error: DC Input Inspector reached step limit without routing.",
        )

    # ------------------------------------------------------------------
    # Read handlers
    # ------------------------------------------------------------------

    def _handle_read_parameters_tool(self, tc: dict) -> None:
        """Read parameters.json at the supplied path and feed it to the LLM."""
        summary = _read_file_at_path(
            tc.get("args", {}).get("path"),
            missing_label="Parameters file",
            content_label="DC Parameters",
            validate_json=True,
        )
        log_tool_call(
            "dc_input_inspector", tc["name"], tc.get("args"), summary,
        )
        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    def _handle_read_extraction_tool(self, tc: dict) -> None:
        """Read extracted_inputs.txt at the supplied path."""
        summary = _read_file_at_path(
            tc.get("args", {}).get("path"),
            missing_label="Extracted inputs file",
            content_label="Extracted Inputs",
            validate_json=False,
        )
        log_tool_call(
            "dc_input_inspector", tc["name"], tc.get("args"), summary,
        )
        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    def on_operation_end(self) -> None:
        """End-of-operation hook called by the dispatcher.

        With ``keep_images_in_context=False`` strip every image content
        block from this agent's history (the DCII may load user input
        images via ``load_input_images`` to inform parameter
        validation), leaving the paired ``Loaded image (path: …):``
        text blocks behind.  No-op when ``keep_images_in_context=True``.
        """
        if self.keep_images_in_context:
            return
        removed = strip_image_blocks_from_messages(self.messages)
        if removed:
            logger.info(
                f"[DCII]  on_operation_end stripped {removed} image "
                f"block(s); paired path-text blocks retained."
            )

    def reset(self) -> None:
        self.messages.clear()


# ---------------------------------------------------------------------------
# Shared read helper
# ---------------------------------------------------------------------------

def _read_file_at_path(
    raw_path,
    missing_label: str,
    content_label: str,
    validate_json: bool,
) -> str:
    """Read *raw_path* and return a ToolMessage-ready summary."""
    if not isinstance(raw_path, str) or not raw_path.strip():
        return (
            f"Error: missing or non-string 'path' argument.  Call this "
            f"tool with the absolute path supplied under the "
            f"'{missing_label}:' label."
        )
    path = Path(raw_path)
    if not path.is_file():
        return (
            f"Error: '{raw_path}' is not an existing file.  Do not "
            f"retry with a guessed path; ESCALATE if no valid path was "
            f"supplied."
        )
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Error reading '{raw_path}': {exc}"
    if not content.strip():
        return (
            f"Warning: '{raw_path}' exists but is empty.  ESCALATE."
        )
    if validate_json:
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            return (
                f"Error: '{raw_path}' is not valid JSON ({exc}).  "
                f"ESCALATE."
            )
    return (
        f"Loaded {content_label} from {path.resolve()} "
        f"({len(content)} chars).\n\n"
        f"--- {content_label} ---\n{content}"
    )
