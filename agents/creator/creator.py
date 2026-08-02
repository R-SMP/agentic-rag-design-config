"""Creator agent (5-agent topology) — authors the parameter set AND
self-validates it before writing.

Merges the 7-agent DC Input Creator and DC Input Inspector into one
agent.  Where the 7-agent chain was DCIC -> DCII -> Tool Caller, the
Creator does both halves in a single turn and forwards straight to the
Tool Caller.

The turn has THREE phases (see ``agents/creator/prompt.md``):

1. DRAFT          translate the extraction into the full parameter set.
2. SELF-VALIDATE  check the draft — always the per-parameter range
                  check, the hard-blocker feasibility check and the
                  authorisation check; scale the deeper comparisons to
                  the size of the change.
3. WRITE          only once the draft passes: ``new_attempt`` ONCE,
                  then ``write_parameters`` ONCE, then hand off.

The ordering matters and is why this agent differs structurally from
the DCIC: attempt folders are append-only, so a correction discovered
after the write has nowhere legal to go.  Validating the DRAFT means
the file on disk is correct by construction.

Tools are the union of both parents:
  * from the DCIC — ``read_extracted_inputs``, ``write_parameters``,
    ``new_attempt`` (it remains the ONLY holder of attempt creation),
    ``list_attempts``, ``read_attempt``, ``calculate``;
  * from the DCII — the user-input IMAGE tools.  The DCIC bound
    ``build_user_inputs_tools(..., include_image_tools=False)``; the
    Creator does NOT pass that flag, so it inherits the DCII's ability
    to look at the user's sketches when the extraction is in doubt.

There is no ``read_parameters``: the Creator validates the draft before
anything is written, so there is nothing on disk to re-read.
``list_attempts`` / ``read_attempt`` still cover inspecting PRIOR
cycles.

NOT YET WIRED.  Nothing constructs this class: ``SYSTEM_TOPOLOGY``
defaults to 7 and no dispatcher branch builds the 5-agent set yet.  Two
resolution steps are also still outstanding, so a prompt built today
would splice the 7-agent fragments and leave ``$routing_creator``
unresolved:
  * ``prompts._build_slots`` is not topology-aware, so the 5-agent
    fragment overrides under ``agents/5agent/fragments/`` are not yet
    reachable;
  * ``routing._load_routing_fragment`` only looks in
    ``agents/shared/prompt_fragments/``.
Both are part of the topology-aware resolution step.
"""

import json
import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

from agents.shared.agent_activity import generic_tool
from agents.shared.attempts_tool import list_attempts, new_attempt, read_attempt
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.file_utils import (
    ai_text,
    flush_pending_image_blocks,
    strip_image_blocks_from_messages,
)
from agents.shared.llm_provider import make_system_message
from agents.shared.llm_retry import invoke_with_retry
from agents.shared import token_usage
from agents.shared.prompts import (
    PARAMETER_NAMES,
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
from agents.shared.session import AgentState, Session
from agents.shared.user_inputs_tool import (
    build_user_inputs_tools,
    dispatch_user_inputs_tool,
)
from agents.shared.retrieve_tool_dispatcher import dispatch_retrieve_tool
from agents.shared.stop_signal import check_stop_or_raise
from agents.step_caps import MAX_CREATOR_STEPS
from config import ATTEMPTS_DIR
from tools.calculate.calculate import calculate
from tools.database_search.database_search import make_database_search_tool
from tools.retrieve_attempt.retrieve_attempt import make_retrieve_attempt_tool
from tools.retrieve_user_inputs.retrieve_user_inputs import (
    make_retrieve_user_inputs_tool,
)
from workflow_settings import database_access

logger = logging.getLogger("propeller_agent")


# ---------------------------------------------------------------------------
# Utility tool schemas (actual I/O handled by Creator)
# ---------------------------------------------------------------------------

@tool
def read_extracted_inputs(path: str) -> str:
    """Read the structured user-input extraction from a file.

    Pass the absolute path supplied under the ``Extracted inputs file:``
    label.  Returns the full three-section extraction as text.  Do NOT
    call this tool with a guessed path."""
    return ""  # Actual read is performed by _handle_read_tool.


@tool
def write_parameters(parameters: dict, attempt_dir: str) -> str:
    """Persist the complete parameter set to
    ``<attempt_dir>/parameters.json``.

    Call this ONLY after your self-validation has passed — the draft is
    checked BEFORE it is written, so the file on disk is correct by
    construction.

    Both arguments are REQUIRED.

    - ``parameters``: a dict containing all design-configurator keys
      nested inside it (see the call shape below).
    - ``attempt_dir``: absolute path of the attempt folder this
      parameter set belongs to — the path returned by your own
      ``new_attempt`` call, which you make only once the draft passes.
      The folder must already exist; the write refuses if it already
      contains a ``parameters.json`` (attempt folders are append-only,
      so a later correction is a NEW generation: open a fresh attempt).

    Returns a short confirmation (file path + field count) on success
    or an error describing missing / extra / non-numeric fields, or a
    bad / already-occupied attempt folder.  A REJECTED call writes no
    file, so fixing what it names and re-calling on the SAME folder is
    not a second write."""
    return ""  # Actual write is performed by _handle_write_tool.


class Creator(BaseChainAgent):
    """Stateful agent that authors AND self-validates the DC parameter
    set (5-agent topology)."""

    AGENT_KEY = "creator"

    def __init__(
        self,
        state: AgentState | None = None,
        session: Session | None = None,
        *,
        llm_cache=None,
    ):
        if session is None:
            raise TypeError(
                "Creator requires a Session.  Construct one via "
                "Session(...) or Session.create_for_v3(...) and pass "
                "it in."
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

    def set_routing_tools(self, tools: list) -> None:
        """Bind the Creator's utility + routing tools.

        Unlike the DCIC there is no ``next_agent`` parameter: the
        Creator's forward target is always the Tool Caller, and both
        CLARIFY and ESCALATE go to the Conductor via the same tool.
        """
        self._extra_utility_tools_by_name = {
            list_attempts.name: list_attempts,
            read_attempt.name: read_attempt,
            new_attempt.name: new_attempt,
            calculate.name: calculate,
        }
        if database_access.is_enabled_for(self.AGENT_KEY):
            _database_search = make_database_search_tool(self.AGENT_KEY)
            self._extra_utility_tools_by_name[_database_search.name] = _database_search
            _retrieve_user_inputs = make_retrieve_user_inputs_tool(self.AGENT_KEY)
            self._extra_utility_tools_by_name[_retrieve_user_inputs.name] = _retrieve_user_inputs
            _retrieve_attempt = make_retrieve_attempt_tool(self.AGENT_KEY)
            self._extra_utility_tools_by_name[_retrieve_attempt.name] = _retrieve_attempt
        all_tools = (
            [self._read_tool, self._write_tool]
            + list(self._extra_utility_tools_by_name.values())
            # NO include_image_tools=False here: the Creator inherits the
            # DC Input Inspector's image access so it can check the
            # extraction against the user's own sketches.
            + build_user_inputs_tools(self.AGENT_KEY)
            + list(tools)
        )
        self.llm = self.base_llm.bind_tools(all_tools)
        self._routing_tools_by_name = {t.name: t for t in tools}
        routing_block = routing_instructions(
            agent_name="Creator",
            next_agent="Tool Caller",
            prev_agent="Conductor",
            fragment_name="routing_creator.md",
        )
        # Built fresh at construction time so live edits to .md
        # fragments via the System Prompts UI take effect on the
        # NEXT session without a Python restart.
        self.system_prompt = _build_template("creator").format(
            routing_instructions=routing_block,
        )

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    def run(self, message: str) -> AgentHop:
        """Process one hand-off message and return the chosen hop."""
        token_usage.begin_turn("Creator")
        self._pending_hop = None
        text = f"Hand-off from Conductor:\n{message}"
        self.messages.append(HumanMessage(content=text))

        seen_sigs: set[tuple[str, str]] = set()

        for _ in range(MAX_CREATOR_STEPS):
            check_stop_or_raise()
            self.prune_history_if_needed()
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + self.messages,
                "Creator",
            )
            self.messages.append(response)

            if not response.tool_calls:
                raw = ai_text(response.content)
                return AgentHop(
                    "conductor",
                    "Error: Creator produced a response with no routing "
                    "tool call — it wrote prose but did not invoke "
                    "call_tool_caller / call_conductor, so the pipeline "
                    "would otherwise halt silently.  Its raw text "
                    f"was:\n\n{raw}",
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
                        return stuck_escalation("Creator", name)
                    seen_sigs.add(sig)
                if name == "read_extracted_inputs":
                    self._handle_read_tool(tc)
                    continue
                if name == "write_parameters":
                    self._handle_write_tool(tc)
                    continue
                if dispatch_user_inputs_tool(self, tc, self.AGENT_KEY):
                    continue
                if dispatch_retrieve_tool(self, tc, self.AGENT_KEY):
                    continue
                if name in self._extra_utility_tools_by_name:
                    tool_fn = self._extra_utility_tools_by_name[name]
                    try:
                        result = tool_fn.invoke(tc["args"])
                    except Exception as exc:
                        result = f"Error calling {name}: {exc}"
                        logger.error(f"[CREATOR TOOL ERROR] {name}: {exc}")
                    log_tool_call(
                        self.AGENT_KEY, name, tc.get("args"), result,
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
                        logger.error(f"[CREATOR TOOL ERROR] {name}: {exc}")
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
            # AIMessage are appended.  Preserves the tool_use ->
            # tool_result contiguity rule on Anthropic / OpenAI.
            flush_pending_image_blocks(self)

            if routed:
                return self._pending_hop

        return AgentHop(
            "conductor",
            "Error: Creator reached step limit without routing.",
        )

    # ------------------------------------------------------------------
    # read_extracted_inputs handler
    # ------------------------------------------------------------------

    @generic_tool("Read extracted inputs")
    def _handle_read_tool(self, tc: dict) -> None:
        """Read the extraction file the hand-off pointed us at."""
        raw_path = tc.get("args", {}).get("path")

        if not isinstance(raw_path, str) or not raw_path.strip():
            summary = (
                "Error: missing or non-string 'path' argument.  Call "
                "this tool with the absolute path the hand-off carries "
                "under the 'Extracted inputs file:' label."
            )
        else:
            path = Path(raw_path)
            if not path.is_file():
                summary = (
                    f"Error: '{raw_path}' is not an existing file.  Do "
                    f"not retry with a guessed path; ESCALATE if the "
                    f"hand-off did not supply a valid path."
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

        log_tool_call(self.AGENT_KEY, tc["name"], tc.get("args"), summary)

        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    # ------------------------------------------------------------------
    # write_parameters handler
    # ------------------------------------------------------------------

    @generic_tool("Write parameters")
    def _handle_write_tool(self, tc: dict) -> None:
        """Validate and persist the parameter set to
        ``<attempt_dir>/parameters.json``.

        Refuses when ``parameters.json`` already exists in the target
        folder — attempt folders are append-only.  Validation runs
        BEFORE any write, so a rejected call leaves no file behind and
        may be re-called on the same folder.
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
                f"REQUIRED.  RE-ISSUE the call with 'attempt_dir' set "
                f"to the absolute path ``new_attempt`` returned.  Do "
                f"NOT report this as a tool-interface bug; the "
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
            summary = (
                f"Error: YOUR call to write_parameters omitted the "
                f"'parameters' argument (you passed only "
                f"{provided_arg_names}).  This is NOT a tool-schema "
                f"problem — write_parameters accepts BOTH "
                f"'parameters' and 'attempt_dir', and BOTH are "
                f"REQUIRED.  RE-ISSUE the call with 'parameters' set "
                f"to a dict containing exactly these "
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
                    logger.info(f"[CREATOR] {summary}")
                except OSError as exc:
                    summary = f"Error writing parameters.json: {exc}"
                    logger.warning(f"[CREATOR] {summary}")

        log_tool_call(self.AGENT_KEY, tc["name"], tc.get("args"), summary)

        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    def on_operation_end(self) -> None:
        """End-of-operation hook called by the dispatcher.

        Unlike the DCIC, the Creator DOES load user images (it inherited
        the DC Input Inspector's image tools), so this hook does real
        work: with ``keep_images_in_context=False`` it strips image
        content blocks from history, leaving the paired ``Loaded image
        (path: ...):`` text behind.  No-op when
        ``keep_images_in_context=True``.
        """
        if self.keep_images_in_context:
            return
        removed = strip_image_blocks_from_messages(self.messages)
        if removed:
            logger.info(
                f"[CREATOR]  on_operation_end stripped {removed} image "
                f"block(s); paired path-text blocks retained."
            )

    def reset(self) -> None:
        self.messages.clear()
