"""User Input Inspector agent — extracts design information from user input
files.

Stateful agent.  Receives a short hand-off message from the Planner that
carries the input directory path.  The UII then calls TWO utility tools:

1. ``read_user_inputs(path)`` loads the text / JSON / images from the
   supplied directory.
2. ``write_extraction(quantitative, qualitative, intent)`` persists the
   structured extraction to ``extracted_inputs.txt``.

After the extraction has been written it routes via one of its bound
routing tools (FORWARD to DC Input Creator, CLARIFY back to Planner,
or ESCALATE to the Orchestrator).
"""

import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

from agents.shared.agent_activity import generic_tool
from agents.shared.attempts_tool import list_attempts, read_attempt
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.file_utils import (
    ai_text,
    flush_pending_image_blocks,
    load_user_inputs_bundle,
    strip_image_blocks_from_messages,
)
from agents.shared.llm_provider import (
    history_cache_control,
    make_system_message,
)
from agents.shared.dc_primer import dc_primer_messages
from agents.shared.llm_retry import invoke_with_retry
from agents.shared import token_usage
from agents.shared.prompts import (
    PLANNER_FIRST,
    _build_template,
    routing_instructions,
)
from agents.shared.dba_tools import dba_tools_for
from workflow_settings import settings as workflow_settings
from agents.shared.routing_tools import (
    AgentHop,
    ROUTING_TOOL_NAMES,
    finalize_unanswered_tool_calls,
    log_tool_call,
    stuck_escalation,
    tool_call_signature,
)
from agents.shared.session import AgentState, Session
from agents.shared.user_inputs_tool import (
    build_user_inputs_tools,
    dispatch_user_inputs_tool,
)
from agents.shared.retrieve_tool_dispatcher import dispatch_retrieve_tool
from agents.shared.stop_signal import check_stop_or_raise
from agents.step_caps import MAX_UII_STEPS
from tools.calculate.calculate import calculate

logger = logging.getLogger("propeller_agent")


# ---------------------------------------------------------------------------
# Utility tool schemas (actual I/O handled by UserInputInspector)
# ---------------------------------------------------------------------------

_READ_INPUTS_DOC = (
    "Read a user-inputs directory: TEXT plus a LIST of its images (it does "
    "NOT load the images themselves).\n\n"
    "Pass the absolute path of the inputs directory supplied in your hand-off "
    "under the ``Input directory:`` label (do NOT guess).  The output is a "
    "summary plus the concatenated contents of all text/JSON files — "
    "including every image's ``_note.txt`` — followed by a list of the "
    "reference images present with their paths.  To actually SEE an image "
    "(and get its OCR-recognised text: dimension callouts, labels), call "
    "``view_images`` with the path(s) you need."
)


def _build_read_user_inputs():
    """Build the ``read_user_inputs`` tool.

    Returns text + an image LIST only; the real work happens in
    ``_handle_read_inputs_tool``.  Images (and their OCR) are loaded on
    demand via ``view_images``.
    """
    def _impl(path: str) -> str:
        return ""  # handled by _handle_read_inputs_tool
    _impl.__doc__ = _READ_INPUTS_DOC
    return tool("read_user_inputs")(_impl)


@tool
def write_extraction(
    path: str, quantitative: str, qualitative: str, intent: str,
) -> str:
    """Persist the structured user-input extraction to a file.

    Pass the absolute file path supplied in your hand-off under the
    ``Extraction output file:`` label, plus three strings (one per
    section).  Use "None specified." for any section with no content.
    The tool formats the file with canonical section headers and writes
    it to disk."""
    return ""  # Actual write is performed by _handle_write_extraction_tool.


class UserInputInspector(BaseChainAgent):
    """Stateful agent that analyses user input files."""

    AGENT_KEY = "user_input_inspector"

    def __init__(
        self,
        state: AgentState | None = None,
        session: Session | None = None,
        *,
        llm_cache=None,
    ):
        if session is None:
            raise TypeError(
                "UserInputInspector now requires a Session.  Construct "
                "one via Session(...) or Session.create_for_v3(...) "
                "and pass it in."
            )
        if state is None:
            state = AgentState(agent_key=self.AGENT_KEY)
        super().__init__(state=state, session=session, llm_cache=llm_cache)
        self._read_tool = _build_read_user_inputs()
        self._write_tool = write_extraction
        self._routing_tools_by_name: dict = {}
        self._extra_utility_tools_by_name: dict = {}
        self.system_prompt: str = ""

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def set_routing_tools(
        self,
        tools: list,
        next_agent: str,
    ) -> None:
        """Bind the UII's utility + routing tools."""
        self._extra_utility_tools_by_name = {
            calculate.name: calculate,
            list_attempts.name: list_attempts,
            read_attempt.name: read_attempt,
        }
        # Which of the three database tools this agent holds is a
        # per-(profile, agent, tool) decision; dba_tools_for owns it.
        for _dba_tool in dba_tools_for("user_input_inspector"):
            self._extra_utility_tools_by_name[_dba_tool.name] = _dba_tool
        all_tools = (
            [self._read_tool, self._write_tool]
            + list(self._extra_utility_tools_by_name.values())
            + build_user_inputs_tools(self.AGENT_KEY)
            + list(tools)
        )
        self.llm = self.base_llm.bind_tools(all_tools)
        self._routing_tools_by_name = {t.name: t for t in tools}
        if PLANNER_FIRST:
            routing_block = routing_instructions(
                agent_name="User Input Inspector",
                next_agent=next_agent,
                prev_agent="Planner",
                fragment_name=
                    "routing_user_input_inspector_planner_first.md",
            )
        else:
            routing_block = routing_instructions(
                agent_name="User Input Inspector",
                next_agent=next_agent,
                prev_agent=None,
                fragment_name=
                    "routing_user_input_inspector_uii_first.md",
            )
        # Built fresh at construction time so live edits to .md
        # fragments on disk take effect on the
        # NEXT session without a Python restart.
        self.system_prompt = _build_template("user_input_inspector").format(
            routing_instructions=routing_block,
        )

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    def run(self, message: str) -> AgentHop:
        """Process one hand-off message and return the chosen hop."""
        token_usage.begin_turn("UII")
        self._pending_hop = None
        # The routing tool already prefixes "[Incoming from: <sender>]"
        # (routing_tools.py:311), so naming a sender here can only
        # contradict it — under PLANNER_FIRST=False the UII is called by
        # the Orchestrator, not the Planner.  Same agnostic form as
        # tool_caller.py:168, the one agent that already gets this right.
        text = f"Hand-off from previous agent:\n{message}"
        self.messages.append(HumanMessage(content=text))

        seen_sigs: set[tuple[str, str]] = set()

        for _ in range(MAX_UII_STEPS):
            check_stop_or_raise()
            self.prune_history_if_needed()
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + dc_primer_messages(self.provider)
                + self.messages,
                "UII",
                cache_control=history_cache_control(self.provider),
            )
            self.messages.append(response)

            if not response.tool_calls:
                final = ai_text(response.content)
                return AgentHop(
                    "orchestrator",
                    "Error: User Input Inspector produced a response with no "
                    "routing tool call — it wrote prose but did not invoke "
                    "call_dc_input_creator / call_planner / call_orchestrator, "
                    "so the pipeline would otherwise halt silently.  Its raw "
                    f"text was:\n\n{final}",
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
                        return stuck_escalation("User Input Inspector", name)
                    seen_sigs.add(sig)
                if name == "read_user_inputs":
                    self._handle_read_inputs_tool(tc)
                    continue
                if name == "write_extraction":
                    self._handle_write_extraction_tool(tc)
                    continue
                if dispatch_user_inputs_tool(self, tc, "user_input_inspector"):
                    continue
                if dispatch_retrieve_tool(self, tc, "user_input_inspector"):
                    continue
                if name in self._extra_utility_tools_by_name:
                    tool_fn = self._extra_utility_tools_by_name[name]
                    try:
                        result = tool_fn.invoke(tc["args"])
                    except Exception as exc:
                        result = f"Error calling {name}: {exc}"
                        logger.error(f"[UII TOOL ERROR] {name}: {exc}")
                    log_tool_call(
                        "user_input_inspector", name, tc.get("args"), result,
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
                        logger.error(f"[UII TOOL ERROR] {name}: {exc}")
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
            # tool_result contiguity rule on both Anthropic and OpenAI.
            flush_pending_image_blocks(self)

            if routed:
                return self._pending_hop

        return AgentHop(
            "orchestrator",
            "Error: User Input Inspector reached step limit without routing.",
        )

    # ------------------------------------------------------------------
    # read_user_inputs handler
    # ------------------------------------------------------------------

    @generic_tool("Read user inputs")
    def _handle_read_inputs_tool(self, tc: dict) -> None:
        """Load everything in the requested directory and feed it to the LLM."""
        raw_path = tc.get("args", {}).get("path")
        summary_parts: list[str] = []
        image_paths: list[str] = []

        if not raw_path or not isinstance(raw_path, str):
            summary = (
                "Error: no directory path provided.  Call this tool with "
                "the absolute path supplied in your hand-off under the "
                "'Input directory:' label."
            )
        else:
            directory = Path(raw_path)
            if not directory.is_dir():
                summary = (
                    f"Error: '{raw_path}' is not an existing directory.  "
                    f"Do not retry with a guessed path."
                )
            else:
                # Workflow setting (block #18) lets the developer
                # filter the prior extracted_inputs.txt out of the
                # bundle when they suspect the UII is carrying stale
                # state forward despite the prompt's "do not copy
                # forward" rule.  Read disk-fresh per the standard
                # workflow_settings pattern.
                exclude_root: tuple[str, ...] = ()
                if not workflow_settings.UII_MAY_READ_PREVIOUS_EXTRACTION:
                    exclude_root = ("extracted_inputs.txt",)
                # Images are NOT loaded here — the UII loads the specific
                # image(s) it needs on demand via view_images (which
                # also runs OCR per image).  read_user_inputs stays cheap:
                # text + notes + a list of the images present.
                loaded = load_user_inputs_bundle(
                    directory,
                    self.provider,
                    include_image_bytes=False,
                    exclude_root_files=exclude_root,
                )
                image_paths = loaded["image_paths"]
                pairing = loaded["pairing"]
                summary_parts.append(
                    f"Loaded inputs from {directory.resolve()}."
                )
                summary_parts.append(f"Files: {loaded['summary']}")
                if not pairing["ok"]:
                    summary_parts.append(
                        "WARNING: image+note pairing is INVALID.  "
                        "The Receptionist should have caught this — "
                        "ESCALATE so the user can be asked to fix the "
                        "uploads.  Pairing report:\n" + pairing["report"]
                    )
                if loaded["text_content"]:
                    summary_parts.append(
                        "--- File contents ---\n" + loaded["text_content"]
                    )
                else:
                    summary_parts.append("(no text or JSON files found)")
                if image_paths:
                    listing = "\n".join(
                        f"  - {Path(p).name}   (path: {p})"
                        for p in image_paths
                    )
                    summary_parts.append(
                        f"{len(image_paths)} reference image(s) are available "
                        f"but NOT loaded here (their notes are in the file "
                        f"contents above).  To SEE an image and get its OCR "
                        f"text, call view_images with the path(s) you "
                        f"need:\n" + listing
                    )
                summary = "\n\n".join(summary_parts)

        log_tool_call(
            "user_input_inspector", tc["name"], tc.get("args"), summary,
        )

        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    # ------------------------------------------------------------------
    # write_extraction handler
    # ------------------------------------------------------------------

    @generic_tool("Write extracted inputs")
    def _handle_write_extraction_tool(self, tc: dict) -> None:
        """Write the three-section extraction to the path the LLM supplied."""
        args = tc.get("args", {}) or {}
        raw_path = args.get("path")
        quantitative = args.get("quantitative")
        qualitative = args.get("qualitative")
        intent = args.get("intent")

        if not isinstance(raw_path, str) or not raw_path.strip():
            summary = (
                "Error: missing or non-string 'path' argument.  Call this "
                "tool with the absolute path supplied in your hand-off under "
                "the 'Extraction output file:' label."
            )
        else:
            missing = [
                name for name, val in (
                    ("quantitative", quantitative),
                    ("qualitative", qualitative),
                    ("intent", intent),
                ) if not isinstance(val, str)
            ]
            if missing:
                summary = (
                    f"Error: the following arguments are missing or not "
                    f"strings: {missing}.  File not written."
                )
            else:
                q, ql, it = (
                    quantitative.strip(),
                    qualitative.strip(),
                    intent.strip(),
                )
                if not (q or ql or it):
                    summary = (
                        "Error: all three sections are empty.  Provide "
                        "at least one non-empty section (use 'None "
                        "specified.' only for truly empty sections when "
                        "at least one other section has content).  File "
                        "not written."
                    )
                else:
                    extraction = (
                        f"QUANTITATIVE INPUTS:\n{q or 'None specified.'}\n\n"
                        f"QUALITATIVE DESCRIPTIONS:\n{ql or 'None specified.'}\n\n"
                        f"DESIGN INTENT AND FUNCTIONAL REQUIREMENTS:\n"
                        f"{it or 'None specified.'}"
                    )
                    out_path = Path(raw_path)
                    try:
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_text(extraction, encoding="utf-8")
                        summary = (
                            f"Wrote {out_path.name} ({len(extraction)} chars) "
                            f"to {out_path.resolve()}."
                        )
                        logger.info(f"[UII] {summary}")
                    except OSError as exc:
                        summary = (
                            f"Error writing to '{raw_path}': {exc}"
                        )
                        logger.warning(f"[UII] {summary}")

        log_tool_call(
            "user_input_inspector", tc["name"], tc.get("args"), summary,
        )

        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    def on_operation_end(self) -> None:
        """End-of-operation hook called by the dispatcher.

        With ``keep_images_in_context=False`` strip every image
        content block from this agent's history, leaving the paired
        ``Loaded image (path: …):`` text blocks behind.  No-op when
        ``keep_images_in_context=True``.
        """
        if self.keep_images_in_context:
            return
        removed = strip_image_blocks_from_messages(self.messages)
        if removed:
            logger.info(
                f"[UII]  on_operation_end stripped {removed} image "
                f"block(s); paired path-text blocks retained."
            )

    def reset(self) -> None:
        self.messages.clear()
