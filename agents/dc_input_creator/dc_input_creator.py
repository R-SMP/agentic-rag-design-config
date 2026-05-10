"""DC Input Creator agent — builds the complete parameter set.

Stateful agent.  Receives a short hand-off message from the User Input
Inspector that carries the extracted-inputs file path.  The DCIC then
calls TWO utility tools:

1. ``read_extracted_inputs(path)`` loads the structured extraction
   written by the UII.
2. ``write_parameters(parameters, attempt_dir)`` persists the full
   parameter JSON to ``parameters.json`` inside the attempt folder.

Next in the natural pipeline is either the DC Input Inspector (when
enabled) or the Tool Caller (when DCII is skipped).  The wiring is
decided at setup time via ``set_routing_tools``.
"""

import json
import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

from agents.shared.attempts_tool import list_attempts, new_attempt, read_attempt
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.file_utils import (
    ai_text,
    flush_pending_image_blocks,
    strip_image_blocks_from_messages,
)
from agents.shared.llm_provider import make_system_message
from agents.shared.llm_retry import invoke_with_retry
from agents.shared.prompts import (
    DCIC_TEMPLATE,
    PARAMETER_NAMES,
    PLANNER_FIRST,
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
from agents.shared.session import AgentState, Session
from agents.shared.user_inputs_tool import (
    USER_INPUTS_TOOLS,
    dispatch_user_inputs_tool,
)
from agents.step_caps import MAX_DCIC_STEPS
from config import ATTEMPTS_DIR
from tools.calculate.calculate import calculate

logger = logging.getLogger("propeller_agent")


# ---------------------------------------------------------------------------
# Utility tool schemas (actual I/O handled by DCInputCreator)
# ---------------------------------------------------------------------------

@tool
def read_extracted_inputs(path: str) -> str:
    """Read the structured user-input extraction from a file.

    Pass the absolute path supplied by the User Input Inspector under
    the ``Extracted inputs file:`` label.  Returns the full three-
    section extraction as text.  Do NOT call this tool with a guessed
    path."""
    return ""  # Actual read is performed by _handle_read_tool.


@tool
def write_parameters(parameters: dict, attempt_dir: str) -> str:
    """Persist the complete parameter set to
    ``<attempt_dir>/parameters.json``.

    Both arguments are REQUIRED.

    - ``parameters``: a dict containing all design-configurator keys
      nested inside it (see the call shape below).
    - ``attempt_dir``: absolute path of the attempt folder this
      parameter set belongs to.  This is either the path the
      hand-off carries under ``Current attempt:`` (when the
      Orchestrator / Planner created the folder for you), or the
      path you obtained by calling ``new_attempt`` yourself when no
      attempt was assigned.  The folder must already exist; the
      write refuses if it already contains a ``parameters.json``
      (attempt folders are append-only — start a new attempt if
      this set of parameters needs to differ from the existing one).

    Returns a short confirmation (file path + field count) on success
    or an error describing missing / extra / non-numeric fields, or a
    bad / already-occupied attempt folder."""
    return ""  # Actual write is performed by _handle_write_tool.


class DCInputCreator(BaseChainAgent):
    """Stateful agent that creates the complete DC parameter set."""

    AGENT_KEY = "dc_input_creator"

    def __init__(
        self,
        state: AgentState | None = None,
        session: Session | None = None,
        *,
        llm_cache=None,
    ):
        if session is None:
            raise TypeError(
                "DCInputCreator now requires a Session.  Construct "
                "one via Session(...) or Session.create_for_v3(...) "
                "and pass it in."
            )
        if state is None:
            state = AgentState(agent_key=self.AGENT_KEY)
        super().__init__(state=state, session=session, llm_cache=llm_cache)
        self._read_tool = read_extracted_inputs
        self._write_tool = write_parameters
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
        """Bind the DC Input Creator's allowed routing tools."""
        self._extra_utility_tools_by_name = {
            list_attempts.name: list_attempts,
            read_attempt.name: read_attempt,
            new_attempt.name: new_attempt,
            calculate.name: calculate,
        }
        all_tools = (
            [self._read_tool, self._write_tool]
            + list(self._extra_utility_tools_by_name.values())
            + list(USER_INPUTS_TOOLS)
            + list(tools)
        )
        self.llm = self.base_llm.bind_tools(all_tools)
        self._routing_tools_by_name = {t.name: t for t in tools}
        if PLANNER_FIRST:
            routing_block = routing_instructions(
                agent_name="DC Input Creator",
                next_agent=next_agent,
                prev_agent="User Input Inspector",
                fragment_name=
                    "routing_dc_input_creator_planner_first.md",
            )
        else:
            routing_block = routing_instructions(
                agent_name="DC Input Creator",
                next_agent=next_agent,
                prev_agent="Planner",
                fragment_name=
                    "routing_dc_input_creator_uii_first.md",
            )
        self.system_prompt = DCIC_TEMPLATE.format(
            routing_instructions=routing_block,
        )

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    def run(self, message: str) -> AgentHop:
        """Process one hand-off message and return the chosen hop."""
        self._pending_hop = None
        text = f"Hand-off from User Input Inspector:\n{message}"
        self.messages.append(HumanMessage(content=text))

        seen_sigs: set[tuple[str, str]] = set()

        for _ in range(MAX_DCIC_STEPS):
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + self.messages,
                "DCIC",
            )
            self.messages.append(response)

            if not response.tool_calls:
                raw = ai_text(response.content)
                return AgentHop(
                    "orchestrator",
                    "Error: DC Input Creator produced a response with no "
                    "routing tool call — it wrote prose but did not invoke "
                    "call_dc_input_inspector / call_orchestrator / etc., so "
                    "the pipeline would otherwise halt silently.  Its raw "
                    f"text was:\n\n{raw}",
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
                        return stuck_escalation("DC Input Creator", name)
                    seen_sigs.add(sig)
                if name == "read_extracted_inputs":
                    self._handle_read_tool(tc)
                    continue
                if name == "write_parameters":
                    self._handle_write_tool(tc)
                    continue
                if dispatch_user_inputs_tool(self, tc, "dc_input_creator"):
                    continue
                if name in self._extra_utility_tools_by_name:
                    tool_fn = self._extra_utility_tools_by_name[name]
                    try:
                        result = tool_fn.invoke(tc["args"])
                    except Exception as exc:
                        result = f"Error calling {name}: {exc}"
                        logger.error(f"[DCIC TOOL ERROR] {name}: {exc}")
                    log_tool_call(
                        "dc_input_creator", name, tc.get("args"), result,
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
                        logger.error(f"[DCIC TOOL ERROR] {name}: {exc}")
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
            "Error: DC Input Creator reached step limit without routing.",
        )

    # ------------------------------------------------------------------
    # read_extracted_inputs handler
    # ------------------------------------------------------------------

    def _handle_read_tool(self, tc: dict) -> None:
        """Read the extraction file the UII pointed us at."""
        raw_path = tc.get("args", {}).get("path")

        if not isinstance(raw_path, str) or not raw_path.strip():
            summary = (
                "Error: missing or non-string 'path' argument.  Call "
                "this tool with the absolute path supplied by the User "
                "Input Inspector under the 'Extracted inputs file:' "
                "label."
            )
        else:
            path = Path(raw_path)
            if not path.is_file():
                summary = (
                    f"Error: '{raw_path}' is not an existing file.  Do "
                    f"not retry with a guessed path; ESCALATE if the UII "
                    f"did not supply a valid path."
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
                            f"ESCALATE — the UII did not produce an "
                            f"extraction."
                        )
                    else:
                        summary = (
                            f"Loaded extraction from {path.resolve()} "
                            f"({len(content)} chars).\n\n"
                            f"--- Extracted Inputs ---\n{content}"
                        )

        log_tool_call(
            "dc_input_creator", tc["name"], tc.get("args"), summary,
        )

        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    # ------------------------------------------------------------------
    # write_parameters handler
    # ------------------------------------------------------------------

    def _handle_write_tool(self, tc: dict) -> None:
        """Validate and persist the parameter set to
        ``<attempt_dir>/parameters.json``.

        Refuses when ``parameters.json`` already exists in the target
        folder — attempt folders are append-only.
        """
        args = tc.get("args", {}) or {}
        params = args.get("parameters")
        raw_attempt_dir = args.get("attempt_dir")
        # Names the LLM actually passed in this call — quoted back in
        # error messages so the LLM cannot mistake a missing-argument
        # error for a tool-schema mismatch and externalise blame.
        provided_arg_names = sorted(args.keys())

        attempt_dir_err: str | None = None
        attempt_path: Path | None = None
        if not isinstance(raw_attempt_dir, str) or not raw_attempt_dir.strip():
            attempt_dir_err = (
                f"Error: YOUR call to write_parameters omitted the "
                f"'attempt_dir' argument (you passed only "
                f"{provided_arg_names}).  This is NOT a tool-schema "
                f"problem — write_parameters accepts BOTH "
                f"'parameters' and 'attempt_dir', and BOTH are "
                f"REQUIRED.  RE-ISSUE the call with 'attempt_dir' "
                f"set to the absolute path the hand-off carries "
                f"under ``Current attempt:``, or call "
                f"``new_attempt`` first and pass its returned path. "
                f"Do NOT report this as a tool-interface bug; the "
                f"omission is in your previous call's arguments."
            )
        else:
            attempt_path = Path(raw_attempt_dir).resolve()
            try:
                attempts_root = ATTEMPTS_DIR.resolve()
            except OSError:
                attempts_root = ATTEMPTS_DIR
            if not attempt_path.is_dir():
                attempt_dir_err = (
                    f"Error: '{raw_attempt_dir}' is not an existing "
                    f"directory.  Create the attempt folder first via "
                    f"``new_attempt`` and pass its absolute path."
                )
            elif (
                attempts_root not in attempt_path.parents
                and attempt_path != attempts_root
            ):
                attempt_dir_err = (
                    f"Error: '{attempt_path}' is not an attempt folder "
                    f"under {attempts_root}.  ``write_parameters`` only "
                    f"writes inside an attempt folder."
                )
            elif (attempt_path / "parameters.json").exists():
                attempt_dir_err = (
                    f"Error: '{attempt_path}/parameters.json' already "
                    f"exists.  Attempt folders are append-only — call "
                    f"``new_attempt`` to create a fresh folder for a "
                    f"new parameter set."
                )

        if not isinstance(params, dict):
            # Hardened error message: name the omitted arg explicitly,
            # list the keys that the new dict must contain, and
            # explicitly forbid the LLM from blaming the tool.  The
            # original ``'parameters' must be a dict with all named
            # keys`` was ambiguous enough that the DCIC's LLM in
            # session ID003 hallucinated a "tool-schema mismatch"
            # rather than recognising it had simply forgotten to pass
            # the dict.  See extra_utilities/warnings_developer.md
            # (W13) and the corresponding TODO entry.
            summary = (
                f"Error: YOUR call to write_parameters omitted the "
                f"'parameters' argument (you passed only "
                f"{provided_arg_names}).  This is NOT a tool-schema "
                f"problem — write_parameters accepts BOTH "
                f"'parameters' and 'attempt_dir', and BOTH are "
                f"REQUIRED.  RE-ISSUE the call with 'parameters' "
                f"set to a dict containing exactly these "
                f"{len(PARAMETER_NAMES)} keys, each mapped to a "
                f"numeric value: {list(PARAMETER_NAMES)}.  Do NOT "
                f"report this as a tool-interface bug; the omission "
                f"is in your previous call's arguments."
            )
        elif attempt_dir_err is not None:
            summary = attempt_dir_err
        else:
            provided = set(params.keys())
            expected = set(PARAMETER_NAMES)
            missing = sorted(expected - provided)
            extra = sorted(provided - expected)
            non_numeric = [
                k for k in PARAMETER_NAMES
                if k in params and not isinstance(params[k], (int, float))
                or isinstance(params.get(k), bool)
            ]

            if missing or extra or non_numeric:
                parts = ["Error: parameters.json not written."]
                if missing:
                    parts.append(f"Missing keys: {missing}")
                if extra:
                    parts.append(f"Unexpected keys (remove them): {extra}")
                if non_numeric:
                    parts.append(
                        f"Non-numeric values (must be int or float): "
                        f"{non_numeric}"
                    )
                summary = "  ".join(parts)
            else:
                ordered = {k: params[k] for k in PARAMETER_NAMES}
                path = attempt_path / "parameters.json"
                try:
                    path.write_text(
                        json.dumps(ordered, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    summary = (
                        f"Wrote parameters.json ({len(ordered)} fields) "
                        f"to {path.resolve()}.  Attempt folder: "
                        f"{attempt_path.resolve()}."
                    )
                    logger.info(f"[DCIC] {summary}")
                except OSError as exc:
                    summary = f"Error writing parameters.json: {exc}"
                    logger.warning(f"[DCIC] {summary}")

        log_tool_call(
            "dc_input_creator", tc["name"], tc.get("args"), summary,
        )

        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    def on_operation_end(self) -> None:
        """End-of-operation hook called by the dispatcher.

        With ``keep_images_in_context=False`` strip every image content
        block from this agent's history (the DCIC may load user input
        images via ``load_input_images`` to inform parameter
        creation), leaving the paired ``Loaded image (path: …):``
        text blocks behind.  No-op when ``keep_images_in_context=True``.
        """
        if self.keep_images_in_context:
            return
        removed = strip_image_blocks_from_messages(self.messages)
        if removed:
            logger.info(
                f"[DCIC]  on_operation_end stripped {removed} image "
                f"block(s); paired path-text blocks retained."
            )

    def reset(self) -> None:
        self.messages.clear()
