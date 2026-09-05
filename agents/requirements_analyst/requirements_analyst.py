"""Requirements Analyst — derives the requirements, then judges against them.

Merges the topology-5 **User Input Inspector** and **DC Output Inspector**
into one agent.  It owns the requirements at BOTH ends: it reads whatever the
user supplied and writes ``extracted_inputs.txt``, and it later compares the
generated renders against that same material.

It is deliberately NOT named for vision.  Seeing images is one input modality,
not the agent's identity — it could equally read plain text and turn it into a
list of requirements without ever looking at a render.

Its two jobs happen in SEPARATE invocations — the Planner sends it new user
material, the Design Engineer sends it a render to judge — which is why its
step budget is the MAX of its parents' (``MAX_REQUIREMENTS_ANALYST_STEPS``,
40 = max(UII 40, DCOI 40)) rather than their sum.  The Design Engineer is the
mirror case and takes the sum.

Tool set — the union of both parents:

* from the UII: ``read_user_inputs`` + ``write_extraction``;
* from the DCOI: ``read_extracted_inputs``, ``read_attempts``, ``calculate``;
* from both: the image tools (``view_images``, and ``reread_text_regions``
  when OCR is on for this agent).

``calculate`` comes from the DCOI half alone — the UII deliberately does not
bind it, because it records what the user said and resolves nothing.  Under
the union rule the merged agent has it, since one parent did.

The ``@tool`` stubs below are LOCAL copies rather than imports of the
parents'.  Their docstrings ARE the descriptions the model reads, so importing
would mean a topology-3 wording edit silently moving topologies 5 and 7.
"""

import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

from agents.shared.agent_activity import generic_tool
from agents.shared.attempts_tool import read_attempts
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.dba_tools import dba_tools_for
from agents.shared.dc_primer import dc_primer_messages
from agents.shared.file_utils import (
    ai_text,
    flush_pending_image_blocks,
    strip_image_blocks_from_messages,
)
from agents.shared.llm_provider import (
    history_cache_control,
    make_system_message,
)
from agents.shared.llm_retry import invoke_with_retry
from agents.shared.prompts import _build_template, routing_instructions
from agents.shared.retrieve_tool_dispatcher import dispatch_retrieve_tool
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
from agents.shared.stop_signal import check_stop_or_raise
from agents.shared.topology import hub_key as _hub_key
from agents.shared.user_inputs_tool import (
    build_read_user_inputs,
    build_user_inputs_tools,
    dispatch_user_inputs_tool,
    read_inputs_doc,
    read_user_inputs_summary,
)
from agents.shared import token_usage
from agents.step_caps import MAX_REQUIREMENTS_ANALYST_STEPS
from config import USER_INPUTS_DIR
from tools.calculate.calculate import calculate
from workflow_settings import settings as workflow_settings

logger = logging.getLogger("propeller_agent")


# Carried verbatim from the DC Output Inspector: which of the two blocks the
# prompt's {image_persistence_block} slot receives depends on the session's
# KEEP IMAGES IN CONTEXT setting.
_IMAGE_PERSISTENCE_ON = """\
Render images loaded in earlier cycles remain in
your message history as full image blocks AND paired
``Loaded image (path: …):`` text blocks (the path block sits
immediately before each image block).  Those images describe PAST
designs, not the current one."""

_IMAGE_PERSISTENCE_OFF = """\
Render images loaded in earlier cycles have their
image bytes stripped from your history at every operation hand-off;
only the paired ``Loaded image (path: …):`` text blocks survive as a
path-only record of which images you had loaded.  To see those earlier
renders again you must explicitly re-load them from those paths via
``view_images``."""


# Comparison-source blocks — one per startup choice (1 / 2 / 3), filled into
# the prompt's {comparison_mode_block} slot.  Carried verbatim from the DCOI.
#
# ⚠ Mode 2 and mode 3 tell this agent to compare against
# ``extracted_inputs.txt`` — a file that, in topology 3, IT WROTE ITSELF.  In
# topology 5 that file came from a different agent, which is what made "if the
# extraction is wrong, that is an upstream problem to surface" sensible; here
# there is no upstream.  Tracked as open item O2 in the rebuild plan and
# resolved with the owner's prompt edits, not here.
_COMPARISON_MODE_1 = """\
Compare the generated design DIRECTLY against the USER INPUTS —
the user's typed prompt (``user_query.txt``), the user-supplied
reference image(s), and their paired ``_note.txt`` description(s).
Your own ``extracted_inputs.txt`` is NOT your comparison source in
this mode; you compare against the user's own material.

  * ``read_user_inputs()`` — the typed prompt for this design, plus
    what each reference image depicts and where the images are.
  * ``view_images([...])`` — load the relevant user reference
    image(s) so you can compare them against the renders.

The comparison source(s) in scope this session: ``user_query.txt``
plus any paired image+note in ``inputs/input_images/``.  Do NOT
read ``extracted_inputs.txt`` in this mode — it is your own
interpretation, not the user's own input."""

_COMPARISON_MODE_2 = """\
Compare the generated design against the STRUCTURED EXTRACTION at
``extracted_inputs.txt``.  The user's own inputs (``user_query.txt``,
the input image(s), their paired note(s)) are NOT in scope for
comparison in this mode; the extraction IS the comparison source.

  * ``read_extracted_inputs(path={extracted_inputs_path})`` — read
    the extraction.  Use its ``QUANTITATIVE INPUTS``, ``QUALITATIVE
    DESCRIPTIONS`` and ``DESIGN INTENT AND FUNCTIONAL REQUIREMENTS``
    sections as your comparison source.  Its ``USEFUL INPUT IMAGES``
    section is not a comparison source — it is navigation: when a
    precision directive sends you to a user image, that section names
    the crop region to pass as ``crop_regions`` so you compare
    against the right part of it.

Do NOT load the user's own inputs in this mode."""

_COMPARISON_MODE_3 = """\
Compare the generated design PRIMARILY against the STRUCTURED
EXTRACTION (``extracted_inputs.txt``), AND SECONDARILY against the
user's inputs (``user_query.txt``, image(s) and their paired
note(s)) when you judge it necessary OR when the extraction's
``DESIGN INTENT AND FUNCTIONAL REQUIREMENTS`` explicitly calls for
it.

  * ``read_extracted_inputs(path={extracted_inputs_path})`` — read
    the extraction.  Use its ``QUANTITATIVE INPUTS``, ``QUALITATIVE
    DESCRIPTIONS`` and ``DESIGN INTENT AND FUNCTIONAL REQUIREMENTS``
    sections as your comparison source, and ``USEFUL INPUT IMAGES``
    as navigation — it names which reference images carry what, and
    the crop region to pass as ``crop_regions`` when you load one.
  * ``read_user_inputs()`` and ``view_images()`` — the user's own
    material, when you need it."""


# ---------------------------------------------------------------------------
# Utility tool schemas (actual I/O handled by RequirementsAnalyst)
# ---------------------------------------------------------------------------

@tool
def write_extraction(
    path: str, quantitative: str, qualitative: str, intent: str,
    images: str,
) -> str:
    """Persist the structured user-input extraction to a file.

    Pass the absolute file path supplied in your hand-off under the
    ``Extraction output file:`` label, plus four strings (one per
    section).  Use "None specified." for any section with no content.
    The tool formats the file with canonical section headers and writes
    it to disk.

    ``images`` is the USEFUL INPUT IMAGES section: one block per
    reference image that actually contributed something, giving what the
    image shows, why it matters to this design, and every crop region
    you identified on it as ``- <label>: [x0, y0, x1, y1]``.  The Design
    Engineer cannot see the images at all, and you will want these boxes
    yourself when you come back to judge a render against them."""
    return ""  # Actual write is performed by _handle_write_extraction_tool.


@tool
def read_extracted_inputs(path: str) -> str:
    """Read the structured user-input extraction.

    Pass the absolute path named in your comparison-source
    instructions above (or under an ``Extracted inputs file:`` label
    when the hand-off carries one).  Returns the full four-section
    extraction as text: QUANTITATIVE INPUTS, QUALITATIVE
    DESCRIPTIONS, DESIGN INTENT AND FUNCTIONAL REQUIREMENTS, and
    USEFUL INPUT IMAGES — the last naming the reference images that
    matter and the crop regions identified on each, which you can
    pass straight to ``view_images`` as ``crop_regions``.  Do NOT
    call this tool with a guessed path."""
    return ""  # Actual read is performed by _handle_read_extraction_tool.


def _build_comparison_mode_block(
    mode: int,
    extracted_inputs_path: str,
    user_query_path: str,
) -> str:
    """Return the runtime-filled comparison-source block."""
    template = {
        1: _COMPARISON_MODE_1,
        2: _COMPARISON_MODE_2,
        3: _COMPARISON_MODE_3,
    }.get(mode)
    if template is None:
        raise ValueError(
            f"Unknown comparison mode: {mode!r}.  Expected 1, 2, or 3."
        )
    return template.format(
        extracted_inputs_path=extracted_inputs_path,
        user_query_path=user_query_path,
    )


class RequirementsAnalyst(BaseChainAgent):
    """Stateful agent that writes the extraction AND judges renders."""

    AGENT_KEY = "requirements_analyst"

    def __init__(
        self,
        state: AgentState | None = None,
        session: Session | None = None,
        *,
        llm_cache=None,
    ):
        if session is None:
            raise TypeError(
                "RequirementsAnalyst requires a Session.  Construct one via "
                "Session(...) or Session.create_for_v3(...) and pass it in."
            )
        if state is None:
            state = AgentState(agent_key=self.AGENT_KEY)
        super().__init__(state=state, session=session, llm_cache=llm_cache)
        if session.dcoi_comparison_mode not in {1, 2, 3}:
            raise ValueError(
                f"session.dcoi_comparison_mode must be 1, 2, or 3 "
                f"(got {session.dcoi_comparison_mode!r})"
            )
        self.dcoi_comparison_mode = session.dcoi_comparison_mode
        # Schema-only stub: this agent's run loop handles the call itself.
        self._read_inputs_tool = build_read_user_inputs(
            doc=read_inputs_doc(self.AGENT_KEY))
        self._read_extraction_tool = read_extracted_inputs
        self._write_tool = write_extraction
        self._routing_tools_by_name: dict = {}
        self._extra_utility_tools_by_name: dict = {}
        self.system_prompt: str = ""

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def set_routing_tools(self, tools: list) -> None:
        """Bind the Requirements Analyst's utility + routing tools.

        One positional argument: this class exists only under topology 3,
        whose edge set is fixed, so the neighbours are stated here rather than
        threaded in from the hub.
        """
        self._extra_utility_tools_by_name = {
            read_attempts.name: read_attempts,
            calculate.name: calculate,
        }
        # Which of the three database tools this agent holds is a
        # per-(profile, agent, tool) decision; dba_tools_for owns it.
        for _dba_tool in dba_tools_for(self.AGENT_KEY):
            self._extra_utility_tools_by_name[_dba_tool.name] = _dba_tool

        all_tools = (
            [self._read_inputs_tool, self._write_tool,
             self._read_extraction_tool]
            + list(self._extra_utility_tools_by_name.values())
            # No text-file tools: ``read_user_inputs`` already reads every
            # text file at once (image notes included) and lists the image
            # paths, so only ``view_images`` (+ ``reread_text_regions`` when
            # OCR is on) come from the shared builder.
            + build_user_inputs_tools(self.AGENT_KEY, include_text_tools=False)
            + list(tools)
        )
        self.llm = self.base_llm.bind_tools(all_tools)
        self._routing_tools_by_name = {t.name: t for t in tools}

        routing_block = routing_instructions(
            agent_name="Requirements Analyst",
            # Last in the natural flow: completing normally means handing
            # back to the hub.  Mirrors the DC Output Inspector.
            next_agent=None,
            prev_agent="Design Engineer",
            fragment_name="routing_requirements_analyst.md",
        )
        image_persistence_block = (
            _IMAGE_PERSISTENCE_ON
            if self.keep_images_in_context
            else _IMAGE_PERSISTENCE_OFF
        )
        extracted_inputs_path = str(
            (USER_INPUTS_DIR / "extracted_inputs.txt").resolve()
        )
        user_query_path = str((USER_INPUTS_DIR / "user_query.txt").resolve())
        comparison_mode_block = _build_comparison_mode_block(
            self.dcoi_comparison_mode,
            extracted_inputs_path,
            user_query_path,
        )
        # Built fresh at construction time so live edits to .md fragments on
        # disk take effect on the NEXT session without a Python restart.
        self.system_prompt = _build_template(self.AGENT_KEY).format(
            routing_instructions=routing_block,
            image_persistence_block=image_persistence_block,
            comparison_mode_block=comparison_mode_block,
        )

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    def run(self, message: str) -> AgentHop:
        """Process one hand-off message and return the chosen hop."""
        token_usage.begin_turn("RA")
        self._pending_hop = None
        self._routing_retry_used = False
        # Agnostic wording: this agent is called by the Planner AND by the
        # Design Engineer, and the routing tool already prefixes
        # "[Incoming from: ...]", so naming a sender here could only
        # contradict it.
        text = f"Hand-off from previous agent:\n{message}"
        self.messages.append(HumanMessage(content=text))

        seen_sigs: set[tuple[str, str]] = set()

        for _ in range(MAX_REQUIREMENTS_ANALYST_STEPS):
            check_stop_or_raise()
            self.prune_history_if_needed()
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + dc_primer_messages(self.provider, self.AGENT_KEY)
                + self.messages,
                "RA",
                cache_control=history_cache_control(self.provider),
            )
            self.messages.append(response)

            if not response.tool_calls:
                final = ai_text(response.content)
                if begin_routing_retry(self, final, "RA"):
                    continue
                bound = " / ".join(sorted(self._routing_tools_by_name)) \
                    or "any routing tool"
                return AgentHop(
                    _hub_key(),
                    "Error: Requirements Analyst produced a response with no "
                    "routing tool call — it wrote prose but did not invoke "
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
                        return stuck_escalation("Requirements Analyst", name)
                    seen_sigs.add(sig)
                if name == "read_user_inputs":
                    self._handle_read_inputs_tool(tc)
                    continue
                if name == "write_extraction":
                    self._handle_write_extraction_tool(tc)
                    continue
                if name == "read_extracted_inputs":
                    self._handle_read_extraction_tool(tc)
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
                        logger.error(f"[RA TOOL ERROR] {name}: {exc}")
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
                        logger.error(f"[RA TOOL ERROR] {name}: {exc}")
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

            # Flush any pending image content blocks as a single trailing
            # HumanMessage AFTER all ToolMessages for this AIMessage are
            # appended.  Preserves the tool_use -> tool_result contiguity rule
            # on both Anthropic and OpenAI.
            flush_pending_image_blocks(self)

            if routed:
                finish_routing_retry(self)
                return self._pending_hop

        return AgentHop(
            _hub_key(),
            "Error: Requirements Analyst reached step limit without routing.",
        )

    # ------------------------------------------------------------------
    # read_user_inputs handler  (from the UII half)
    # ------------------------------------------------------------------

    @generic_tool("Read user inputs")
    def _handle_read_inputs_tool(self, tc: dict) -> None:
        """Load everything in the requested directory and feed it to the LLM."""
        raw_path = tc.get("args", {}).get("path")

        # Workflow setting (block #18) lets the developer filter the prior
        # extracted_inputs.txt out of the bundle when they suspect the agent
        # is carrying stale state forward despite the prompt's "do not copy
        # forward" rule.  Read disk-fresh per the standard pattern.
        exclude_root: tuple[str, ...] = ()
        if not workflow_settings.UII_MAY_READ_PREVIOUS_EXTRACTION:
            exclude_root = ("extracted_inputs.txt",)
        summary = read_user_inputs_summary(
            raw_path,
            self.provider,
            exclude_root_files=exclude_root,
            can_view_images=True,
            strip_timestamps=True,
            agent_key=self.AGENT_KEY,
        )
        if not raw_path or not isinstance(raw_path, str):
            summary = (
                "Error: no directory path provided.  Call this tool with "
                "the absolute path supplied in your hand-off under the "
                "'Input directory:' label."
            )

        log_tool_call(self.AGENT_KEY, tc["name"], tc.get("args"), summary)

        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    # ------------------------------------------------------------------
    # write_extraction handler  (from the UII half)
    # ------------------------------------------------------------------

    @generic_tool("Write extracted inputs")
    def _handle_write_extraction_tool(self, tc: dict) -> None:
        """Write the four-section extraction to the path the LLM supplied."""
        args = tc.get("args", {}) or {}
        raw_path = args.get("path")
        quantitative = args.get("quantitative")
        qualitative = args.get("qualitative")
        intent = args.get("intent")
        images = args.get("images")

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
                    ("images", images),
                ) if not isinstance(val, str)
            ]
            if missing:
                summary = (
                    f"Error: the following arguments are missing or not "
                    f"strings: {missing}.  File not written."
                )
            else:
                q, ql, it, im = (
                    quantitative.strip(),
                    qualitative.strip(),
                    intent.strip(),
                    images.strip(),
                )
                if not (q or ql or it or im):
                    summary = (
                        "Error: all four sections are empty.  Provide "
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
                        f"{it or 'None specified.'}\n\n"
                        f"USEFUL INPUT IMAGES:\n"
                        f"{im or 'None specified.'}"
                    )
                    out_path = Path(raw_path)
                    try:
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_text(extraction, encoding="utf-8")
                        summary = (
                            f"Wrote {out_path.name} ({len(extraction)} chars) "
                            f"to {out_path.resolve()}."
                        )
                        logger.info(f"[RA] {summary}")
                    except OSError as exc:
                        summary = f"Error writing to '{raw_path}': {exc}"
                        logger.warning(f"[RA] {summary}")

        log_tool_call(self.AGENT_KEY, tc["name"], tc.get("args"), summary)

        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    # ------------------------------------------------------------------
    # read_extracted_inputs handler  (from the DCOI half)
    # ------------------------------------------------------------------

    @generic_tool("Read extracted inputs")
    def _handle_read_extraction_tool(self, tc: dict) -> None:
        """Read extracted_inputs.txt at the supplied path."""
        raw_path = tc.get("args", {}).get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            summary = (
                "Error: missing or non-string 'path' argument.  Call this "
                "tool with the absolute extraction path named in your "
                "comparison-source instructions."
            )
        else:
            path = Path(raw_path)
            if not path.is_file():
                summary = (
                    f"Error: '{raw_path}' is not an existing file.  Do not "
                    f"retry with a guessed path; hand back to the Planner if "
                    f"no valid path was supplied."
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
                            f"Hand back to the Planner."
                        )
                    else:
                        summary = (
                            f"Loaded Extracted Inputs from {path.resolve()} "
                            f"({len(content)} chars).\n\n"
                            f"--- Extracted Inputs ---\n{content}"
                        )
        log_tool_call(self.AGENT_KEY, tc["name"], tc.get("args"), summary)
        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    def on_operation_end(self) -> None:
        """End-of-operation hook called by the dispatcher.

        With ``keep_images_in_context=False`` every image content block in
        this agent's history is stripped, leaving the paired ``Loaded image
        (path: …):`` text blocks behind as a path-only record.  Re-loading the
        same images later requires another explicit ``view_images`` call.
        No-op when ``keep_images_in_context=True``.
        """
        if self.keep_images_in_context:
            return
        removed = strip_image_blocks_from_messages(self.messages)
        if removed:
            logger.info(
                f"[RA]  on_operation_end stripped {removed} image "
                f"block(s); paired path-text blocks retained."
            )

    def reset(self) -> None:
        self.messages.clear()
