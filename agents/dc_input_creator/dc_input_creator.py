"""DC Input Creator agent — builds the complete parameter set.

Stateful agent.  Receives a short hand-off message from the User Input
Inspector that carries the extracted-inputs file path.  The DCIC then
calls TWO utility tools:

1. ``read_extracted_inputs(path)`` loads the structured extraction
   written by the UII.
2. ``new_attempt_parameters(parameters, slug, description)`` opens the
   attempt folder and writes the full parameter JSON into it, in one call.

Next in the natural pipeline is either the DC Input Inspector (when
enabled) or the Tool Caller (when DCII is skipped).  The wiring is
decided at setup time via ``set_routing_tools``.
"""

import json
import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

from agents.shared.agent_activity import generic_tool
from agents.shared.attempts_tool import create_attempt, read_attempts
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.file_utils import (
    ai_text,
    flush_pending_image_blocks,
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
    PARAMETER_NAMES,
    PLANNER_FIRST,
    _build_template,
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
from agents.shared.session import AgentState, Session
from agents.shared.retrieve_tool_dispatcher import dispatch_retrieve_tool
from agents.shared.stop_signal import check_stop_or_raise
from agents.step_caps import MAX_DCIC_STEPS
from tools.calculate.calculate import calculate
from agents.shared.dba_tools import dba_tools_for

logger = logging.getLogger("propeller_agent")


# ---------------------------------------------------------------------------
# Utility tool schemas (actual I/O handled by DCInputCreator)
# ---------------------------------------------------------------------------

# The extraction's final section, ``USEFUL INPUT IMAGES``, records which
# reference images matter and the crop regions identified on them.  It
# exists for agents that can SEE images (the DC Input Inspector, the DC
# Output Inspector); this agent binds no image tools, so the section is
# stripped before the text reaches it — image navigation it cannot act on
# is noise it would have to reason past.  The section is written LAST, so
# removing it is a truncate; absent (older extraction, or a run with no
# images), this is a no-op.
_IMAGES_SECTION_HEADER = "USEFUL INPUT IMAGES:"


def _strip_images_section(content: str) -> str:
    """Return *content* without its trailing ``USEFUL INPUT IMAGES``
    section."""
    head, sep, _tail = content.partition(_IMAGES_SECTION_HEADER)
    return head.rstrip() + "\n" if sep else content


@tool
def read_extracted_inputs(path: str) -> str:
    """Read the structured user-input extraction from a file.

    Pass the absolute path supplied by the User Input Inspector under
    the ``Extracted inputs file:`` label.  Returns the extraction's
    parameter-relevant sections as text.  Do NOT call this tool with a
    guessed path."""
    return ""  # Actual read is performed by _handle_read_tool.


@tool
def new_attempt_parameters(parameters: dict,
                           slug: str = "attempt",
                           description: str = "") -> str:
    """Open a NEW attempt folder and write the complete parameter set into it.

    One call does both, in this order: the parameter set is validated,
    then the attempt folder is created (timestamp + sequence number +
    ``slug``), then ``description.txt`` is recorded when a description is
    given, and finally the values are written to ``parameters.json``
    inside that same folder.

    There is no path argument — the folder this tool creates is the folder
    it writes into, so the two can never disagree.  Because validation
    happens first, a rejected call creates nothing and leaves no empty
    attempt behind.

    Args:
      parameters:  dict carrying ALL the design parameters listed in your
                   prompt, each mapped to a number.
      slug:        short, filename-safe label that appears in the folder
                   name after the timestamp + sequence number (e.g.
                   ``'4blades_thick_ring'``).  Optional.
      description: optional one-paragraph note explaining what this
                   attempt is for; written to ``description.txt``.

    Returns the new attempt's NUMBER and absolute folder path on success —
    put both on the ``Current attempt <N>:`` line of your hand-off — or an
    error naming the missing / unexpected / non-numeric fields, in which
    case nothing was created and nothing was written."""
    return ""  # Actual work is performed by _handle_write_tool.


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
        self._write_tool = new_attempt_parameters
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
            read_attempts.name: read_attempts,
            calculate.name: calculate,
        }
        # Which of the three database tools this agent holds is a
        # per-(profile, agent, tool) decision; dba_tools_for owns it.
        for _dba_tool in dba_tools_for("dc_input_creator"):
            self._extra_utility_tools_by_name[_dba_tool.name] = _dba_tool
        all_tools = (
            [self._read_tool, self._write_tool]
            + list(self._extra_utility_tools_by_name.values())
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
        # Built fresh at construction time so live edits to .md
        # fragments on disk take effect on the
        # NEXT session without a Python restart.
        self.system_prompt = _build_template("dc_input_creator").format(
            routing_instructions=routing_block,
        )

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    def run(self, message: str) -> AgentHop:
        """Process one hand-off message and return the chosen hop."""
        token_usage.begin_turn("DCIC")
        self._pending_hop = None
        self._routing_retry_used = False
        text = f"Hand-off from User Input Inspector:\n{message}"
        self.messages.append(HumanMessage(content=text))

        seen_sigs: set[tuple[str, str]] = set()

        for _ in range(MAX_DCIC_STEPS):
            check_stop_or_raise()
            self.prune_history_if_needed()
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + dc_primer_messages(self.provider, self.AGENT_KEY)
                + self.messages,
                "DCIC",
                cache_control=history_cache_control(self.provider),
            )
            self.messages.append(response)

            if not response.tool_calls:
                raw = ai_text(response.content)
                if begin_routing_retry(self, raw, "DCIC"):
                    continue
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
                check_stop_or_raise()
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
                if name == "new_attempt_parameters":
                    self._handle_write_tool(tc)
                    continue
                if dispatch_retrieve_tool(self, tc, "dc_input_creator"):
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
                finish_routing_retry(self)
                return self._pending_hop

        return AgentHop(
            "orchestrator",
            "Error: DC Input Creator reached step limit without routing.",
        )

    # ------------------------------------------------------------------
    # read_extracted_inputs handler
    # ------------------------------------------------------------------

    @generic_tool("Read extracted inputs")
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
                    content = _strip_images_section(
                        path.read_text(encoding="utf-8"))
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
    # new_attempt_parameters handler
    # ------------------------------------------------------------------

    @generic_tool("Open attempt + write parameters")
    def _handle_write_tool(self, tc: dict) -> None:
        """Validate the parameter set, then create the attempt folder and
        write ``parameters.json`` into it.

        Validation runs FIRST so a rejected call never leaves an empty
        attempt folder behind.  There is no target-folder argument: this
        tool always writes into the folder it just created, so the
        append-only guarantee holds by construction.
        """
        args = tc.get("args", {}) or {}
        params = args.get("parameters")
        slug = args.get("slug") or "attempt"
        description = args.get("description") or ""
        # Names the LLM actually passed in this call - quoted back in
        # error messages so the LLM cannot mistake a missing-argument
        # error for a tool-schema mismatch and externalise blame.
        provided_arg_names = sorted(args.keys())

        if not isinstance(params, dict):
            summary = (
                f"Error: YOUR call to new_attempt_parameters omitted the "
                f"'parameters' argument (you passed only "
                f"{provided_arg_names}).  This is NOT a tool-schema "
                f"problem - 'parameters' is REQUIRED; 'slug' and "
                f"'description' are optional.  RE-ISSUE the call with "
                f"'parameters' set to a dict containing exactly these "
                f"{len(PARAMETER_NAMES)} keys, each mapped to a "
                f"numeric value: {list(PARAMETER_NAMES)}.  Do NOT "
                f"report this as a tool-interface bug; the omission "
                f"is in your previous call's arguments."
            )
        elif not isinstance(slug, str) or not isinstance(description, str):
            summary = (
                "Error: 'slug' and 'description' must be strings when "
                "given.  Nothing was created."
            )
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
                parts = [
                    "Error: no attempt was created and no parameters.json "
                    "was written."
                ]
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
                try:
                    attempt_n, dest = create_attempt(slug, description)
                except OSError as exc:
                    summary = f"Error creating attempt folder: {exc}"
                    logger.warning(f"[DCIC] {summary}")
                else:
                    path = dest / "parameters.json"
                    try:
                        path.write_text(
                            json.dumps(ordered, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        summary = (
                            f"Created attempt {attempt_n} at "
                            f"{dest.resolve()} and wrote parameters.json "
                            f"({len(ordered)} fields) into it.  Hand this "
                            f"on as: Current attempt {attempt_n}: "
                            f"{dest.resolve()}"
                        )
                        logger.info(f"[DCIC] {summary}")
                    except OSError as exc:
                        summary = (
                            f"Attempt {attempt_n} was created at "
                            f"{dest.resolve()} but parameters.json could "
                            f"not be written: {exc}"
                        )
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

        The DCIC no longer loads user images (it works from
        ``extracted_inputs.txt``), so there are normally no image blocks
        to strip — this remains a no-op safety net that, with
        ``keep_images_in_context=False``, would strip any stray image
        content block from history (leaving paired ``Loaded image
        (path: …):`` text behind).  No-op when
        ``keep_images_in_context=True``.
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
