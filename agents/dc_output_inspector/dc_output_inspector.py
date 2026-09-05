"""DC Output Inspector agent — analyses generated geometry and renders.

Stateful agent.  Uses the shared ``view_images`` tool (to load renders /
user images — optionally cropped and/or side-by-side — into the LLM's view)
and a set of routing tools.  Its readers are:

1. ``read_extracted_inputs(path)`` — the structured extraction written by
   the User Input Inspector.  Comparing the render against it is the whole
   job, so the DCOI reads it directly rather than through a generic
   text-file reader.
2. ``read_user_inputs(path)`` — the raw user inputs (every text file at
   once, plus the list of image paths) when the extraction is not enough.
3. ``read_attempts(n)`` — an earlier cycle's renders and parameters.

It is the last agent in the natural pipeline: its FORWARD target is the
Orchestrator.
"""

import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

from agents.shared.agent_activity import generic_tool
from agents.shared.attempts_tool import read_attempts
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
from agents.shared.dc_primer import primed_history
from agents.shared.llm_retry import invoke_with_retry
from agents.shared import token_usage
from agents.shared.prompts import _build_template, routing_instructions
from agents.shared.routing_tools import (
    AgentHop,
    ROUTING_TOOL_NAMES,
    begin_routing_retry,
    finalize_unanswered_tool_calls,
    finish_routing_retry,
    log_tool_call,
)
from agents.shared.topology import hub_key as _hub_key
from agents.shared.topology import topology as _topology
from agents.shared.session import AgentState, Session
from agents.shared.user_inputs_tool import (
    read_inputs_doc,
    build_read_user_inputs,
    build_user_inputs_tools,
    dispatch_user_inputs_tool,
    read_user_inputs_summary,
)
from agents.shared.retrieve_tool_dispatcher import dispatch_retrieve_tool
from agents.shared.stop_signal import check_stop_or_raise
from agents.step_caps import MAX_DCOI_STEPS
from config import USER_INPUTS_DIR
from tools.calculate.calculate import calculate
from agents.shared.dba_tools import dba_tools_for

logger = logging.getLogger("propeller_agent")


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


# Comparison-source blocks — one per startup choice (1 / 2 / 3).
# Filled into the {comparison_mode_block} placeholder of DCOI_TEMPLATE.

_COMPARISON_MODE_1 = """\
Compare the generated design DIRECTLY against the USER INPUTS —
the user's typed prompt (``user_query.txt``), the user-supplied
reference image(s), and their paired ``_note.txt`` description(s).
The UII's ``extracted_inputs.txt`` is NOT your comparison source in
this mode; you compare against the user's own material.

  * ``read_user_inputs()`` — the typed prompt for this design, plus
    what each reference image depicts and where the images are.
  * ``view_images([...])`` — load the relevant user reference
    image(s) so you can compare them against the renders.

The comparison source(s) in scope this session: ``user_query.txt``
plus any paired image+note in ``inputs/input_images/``.  Do NOT
read ``extracted_inputs.txt`` in this mode — it is the UII's
interpretation, not the user's own input."""

_COMPARISON_MODE_2 = """\
Compare the generated design against the UII's STRUCTURED
EXTRACTION at ``extracted_inputs.txt``.  The user's own inputs
(``user_query.txt``, the input image(s), their paired note(s)) are
NOT in scope for comparison in this mode; the extraction IS the
comparison source.

  * ``read_extracted_inputs(path={extracted_inputs_path})`` — read
    the extraction.  Use its ``QUANTITATIVE INPUTS``, ``QUALITATIVE
    DESCRIPTIONS`` and ``DESIGN INTENT AND FUNCTIONAL REQUIREMENTS``
    sections as your comparison source.  Its ``USEFUL INPUT IMAGES``
    section is not a comparison source — it is navigation: when a
    precision directive sends you to a user image, that section names
    the crop region to pass as ``crop_regions`` so you compare
    against the right part of it.

Do NOT load the user's own inputs in this mode.  Your comparison
source is the extraction — if the extraction is wrong, that is
an upstream UII problem to surface via the override-authority
section below, not something for you to verify against the user's
material."""

_COMPARISON_MODE_3 = """\
Compare the generated design PRIMARILY against the UII's STRUCTURED
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
    """Return the runtime-filled comparison-source block for the DCOI."""
    template = {
        1: _COMPARISON_MODE_1,
        2: _COMPARISON_MODE_2,
        3: _COMPARISON_MODE_3,
    }.get(mode)
    if template is None:
        raise ValueError(
            f"Unknown DCOI comparison mode: {mode!r}.  Expected 1, 2, or 3."
        )
    return template.format(
        extracted_inputs_path=extracted_inputs_path,
        user_query_path=user_query_path,
    )


class DCOutputInspector(BaseChainAgent):
    """Stateful agent with an image-loading tool + routing tools."""

    AGENT_KEY = "dc_output_inspector"

    def __init__(
        self,
        state: AgentState | None = None,
        session: Session | None = None,
        *,
        llm_cache=None,
    ):
        if session is None:
            raise TypeError(
                "DCOutputInspector now requires a Session.  Construct "
                "one via Session(...) or Session.create_for_v3(...) "
                "and pass it in."
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
        self._read_inputs_tool = build_read_user_inputs(
            doc=read_inputs_doc(self.AGENT_KEY))
        self._read_extraction_tool = read_extracted_inputs
        self._routing_tools_by_name: dict = {}
        self._extra_utility_tools_by_name: dict = {}
        self.system_prompt: str = ""

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def set_routing_tools(self, tools: list) -> None:
        """Bind routing tools, the two readers and the utility tools."""
        self._extra_utility_tools_by_name = {
            read_attempts.name: read_attempts,
            calculate.name: calculate,
        }
        # Which of the three database tools this agent holds is a
        # per-(profile, agent, tool) decision; dba_tools_for owns it.
        for _dba_tool in dba_tools_for("dc_output_inspector"):
            self._extra_utility_tools_by_name[_dba_tool.name] = _dba_tool
        all_tools = (
            [self._read_extraction_tool, self._read_inputs_tool]
            + list(self._extra_utility_tools_by_name.values())
            + build_user_inputs_tools(self.AGENT_KEY,
                                      include_text_tools=False)
            + list(tools)
        )
        self.llm = self.base_llm.bind_tools(all_tools)
        self._routing_tools_by_name = {t.name: t for t in tools}
        routing_block = routing_instructions(
            agent_name="DC Output Inspector",
            next_agent=None,
            prev_agent="Tool Caller",
            fragment_name="routing_dc_output_inspector.md",
        )
        image_persistence_block = (
            _IMAGE_PERSISTENCE_ON
            if self.keep_images_in_context
            else _IMAGE_PERSISTENCE_OFF
        )
        extracted_inputs_path = str(
            (USER_INPUTS_DIR / "extracted_inputs.txt").resolve()
        )
        user_query_path = str(
            (USER_INPUTS_DIR / "user_query.txt").resolve()
        )
        comparison_mode_block = _build_comparison_mode_block(
            self.dcoi_comparison_mode,
            extracted_inputs_path,
            user_query_path,
        )
        # Built fresh at construction time so live edits to .md
        # fragments on disk take effect on the
        # NEXT session without a Python restart.
        self.system_prompt = _build_template("dc_output_inspector").format(
            routing_instructions=routing_block,
            image_persistence_block=image_persistence_block,
            comparison_mode_block=comparison_mode_block,
        )

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    def run(self, message: str) -> AgentHop:
        """Process one hand-off message."""
        token_usage.begin_turn("DCOI")
        self._pending_hop = None
        self._routing_retry_used = False
        # Under topology 5 the Planner can call the DCOI directly, so the
        # sender is not always the Tool Caller.  Topology 7's wording is
        # unchanged.
        sender = "Tool Caller" if _topology() == 7 else "previous agent"
        text = f"Hand-off from {sender}:\n{message}"
        self.messages.append(HumanMessage(content=text))

        for _ in range(MAX_DCOI_STEPS):
            check_stop_or_raise()
            self.prune_history_if_needed()
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + primed_history(self.provider, self.AGENT_KEY,
                                 self.messages),
                "DCOI",
                cache_control=history_cache_control(self.provider),
            )
            self.messages.append(response)

            if not response.tool_calls:
                final = ai_text(response.content)
                if begin_routing_retry(self, final, "DCOI"):
                    continue
                bound = " / ".join(sorted(self._routing_tools_by_name)) \
                    or "any routing tool"
                return AgentHop(
                    _hub_key(),
                    "Error: DC Output Inspector produced a response with no "
                    "routing tool call — it wrote prose but did not invoke "
                    f"{bound}, so the pipeline would otherwise halt "
                    f"silently.  Its raw text was:\n\n{final}",
                )

            routed = False
            for i, tc in enumerate(response.tool_calls):
                check_stop_or_raise()
                name = tc["name"]
                if name == "read_extracted_inputs":
                    self._handle_read_extraction_tool(tc)
                    continue
                if name == "read_user_inputs":
                    self._handle_read_inputs_tool(tc)
                    continue
                if dispatch_user_inputs_tool(self, tc, "dc_output_inspector"):
                    continue
                if dispatch_retrieve_tool(self, tc, "dc_output_inspector"):
                    continue
                if name in self._extra_utility_tools_by_name:
                    tool_fn = self._extra_utility_tools_by_name[name]
                    try:
                        result = tool_fn.invoke(tc["args"])
                    except Exception as exc:
                        result = f"Error calling {name}: {exc}"
                        logger.error(f"[DCOI TOOL ERROR] {name}: {exc}")
                    log_tool_call(
                        "dc_output_inspector", name, tc.get("args"), result,
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
                        logger.error(f"[DCOI TOOL ERROR] {name}: {exc}")
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

            # All ToolMessages for this AIMessage are now appended.
            # Flush any image content blocks that the load handlers
            # buffered, as a single trailing HumanMessage — preserving
            # the tool_use → tool_result contiguity rule on both
            # Anthropic and OpenAI.
            flush_pending_image_blocks(self)

            if routed:
                finish_routing_retry(self)
                return self._pending_hop

        return AgentHop(
            _hub_key(),
            "Error: DC Output Inspector reached the step limit without routing.",
        )

    # ------------------------------------------------------------------
    # Reader handlers
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
                    f"retry with a guessed path; ESCALATE if no valid path "
                    f"was supplied."
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
                            f"Loaded Extracted Inputs from {path.resolve()} "
                            f"({len(content)} chars).\n\n"
                            f"--- Extracted Inputs ---\n{content}"
                        )
        log_tool_call(
            "dc_output_inspector", tc["name"], tc.get("args"), summary,
        )
        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    def _handle_read_inputs_tool(self, tc: dict) -> None:
        """Read the whole user-inputs directory (text + image list)."""
        summary = read_user_inputs_summary(
            tc.get("args", {}).get("path"),
            getattr(self, "provider", "openai"),
            can_view_images=True,
            agent_key=self.AGENT_KEY,
        )
        log_tool_call(
            "dc_output_inspector", tc["name"], tc.get("args"), summary,
        )
        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    def on_operation_end(self) -> None:
        """End-of-operation hook called by the dispatcher.

        With ``keep_images_in_context=True`` this is a no-op — images
        and their paired path-text blocks both persist across
        hand-offs.

        With ``keep_images_in_context=False`` every image content
        block in this agent's history is stripped, leaving the paired
        ``Loaded image (path: …):`` text blocks behind as a path-only
        record.  Re-loading the same images later requires another
        explicit ``view_images`` call.
        """
        if self.keep_images_in_context:
            return
        removed = strip_image_blocks_from_messages(self.messages)
        if removed:
            logger.info(
                f"[DCOI]  on_operation_end stripped {removed} image "
                f"block(s); paired path-text blocks retained."
            )

    def reset(self) -> None:
        self.messages.clear()
