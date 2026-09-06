"""Requirements Analyst — derives the requirements, then judges against them.

Merges the topology-5 **User Input Inspector** and **DC Output Inspector**
into one agent.  It owns the requirements at BOTH ends: it reads whatever the
user supplied and STATES what it found, and it later compares the generated
renders against that same material.

**Nothing writes ``extracted_inputs.txt`` in topology 3, so the file does not
exist and nothing may read it.**  This agent communicates everything it
extracts VERBALLY, in its hand-off — free-form prose, not a structured block
standing in for the old file.  Hence neither ``write_extraction`` nor
``read_extracted_inputs`` is bound.

It is deliberately NOT named for vision.  Seeing images is one input modality,
not the agent's identity — it could equally read plain text and turn it into a
list of requirements without ever looking at a render.

Its two jobs happen in SEPARATE invocations — the Planner sends it new user
material, the Design Engineer sends it a render to judge — which is why its
step budget is the MAX of its parents' (``MAX_REQUIREMENTS_ANALYST_STEPS``,
40 = max(UII 40, DCOI 40)) rather than their sum.  The Design Engineer is the
mirror case and takes the sum.

Tool set — the union of both parents:

* from the UII: ``read_user_inputs``;
* from the DCOI: ``read_attempts``, ``calculate``;
* from both: the image tools (``view_images``, and ``reread_text_regions``
  when OCR is on for this agent).

``calculate`` comes from the DCOI half alone — the UII deliberately does not
bind it, because it records what the user said and resolves nothing.  Under
the union rule the merged agent has it, since one parent did.
"""

import logging

from langchain_core.messages import HumanMessage, ToolMessage

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
from tools.calculate.calculate import calculate

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


# The comparison-source block filled into the prompt's
# {comparison_mode_block} slot.
#
# ⚠ ONLY MODE 1 EXISTS HERE, and that is a topology decision rather than a
# tidy-up.  Modes 2 and 3 told the agent to compare against
# ``extracted_inputs.txt``; in topology 3 nothing writes that file, so both
# would name a file that can never exist.  ``DCOI_COMPARISON_MODE`` is
# therefore inert under topology 3 -- visible in the settings UI showing its
# real value, greyed out, a write refused -- by the same mechanism as
# PLANNER_FIRST and DC_INSPECTOR_ENABLED.  This agent compares against the
# user's own material, always.  (Closes the rebuild plan's open item O2: the
# question was what to do about grading an extraction it wrote itself, and
# the answer is that there is no extraction.)
_COMPARISON_MODE_1 = """\
Compare the generated design DIRECTLY against the USER INPUTS —
the user's typed prompt (``user_query.txt``), the user-supplied
reference image(s), and their paired ``_note.txt`` description(s).

  * ``read_user_inputs()`` — the typed prompt for this design, plus
    what each reference image depicts and where the images are.
  * ``view_images([...])`` — load the relevant user reference
    image(s) so you can compare them against the renders.

The comparison source(s) in scope this session: ``user_query.txt``
plus any paired image+note in ``inputs/input_images/``."""

# ---------------------------------------------------------------------------
# Utility tool schemas (actual I/O handled by RequirementsAnalyst)
# ---------------------------------------------------------------------------

def _build_comparison_mode_block(mode: int) -> str:
    """Return the runtime-filled comparison-source block."""
    # *mode* is accepted and IGNORED.  ``DCOI_COMPARISON_MODE`` is inert
    # under topology 3 (settings editor), because modes 2 and 3 compare
    # against ``extracted_inputs.txt`` and nothing writes that file here.
    # The argument stays in the signature so the call site, the runtime
    # slot and the snapshot harness all keep their shape.
    del mode
    return _COMPARISON_MODE_1


class RequirementsAnalyst(BaseChainAgent):
    """Stateful agent that states the requirements AND judges renders."""

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
        # Validated but not obeyed: the setting is inert under topology 3
        # (see _build_comparison_mode_block).  Kept so a session carrying a
        # 2 or a 3 from another topology still constructs.
        if session.dcoi_comparison_mode not in {1, 2, 3}:
            raise ValueError(
                f"session.dcoi_comparison_mode must be 1, 2, or 3 "
                f"(got {session.dcoi_comparison_mode!r})"
            )
        self.dcoi_comparison_mode = session.dcoi_comparison_mode
        # Schema-only stub: this agent's run loop handles the call itself.
        self._read_inputs_tool = build_read_user_inputs(
            doc=read_inputs_doc(self.AGENT_KEY))
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
            [self._read_inputs_tool]
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
        comparison_mode_block = _build_comparison_mode_block(
            self.dcoi_comparison_mode)
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

        summary = read_user_inputs_summary(
            raw_path,
            self.provider,
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
