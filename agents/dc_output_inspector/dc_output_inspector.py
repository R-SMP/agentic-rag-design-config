"""DC Output Inspector agent — analyses generated geometry and renders.

Stateful agent.  Owns a ``load_render_images`` utility tool (to load
rendered PNGs from disk into the LLM's view) and a set of routing
tools.  It is the last agent in the natural pipeline: its FORWARD
target is the Orchestrator.
"""

import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

from agents.shared.attempts_tool import list_attempts, read_attempt
from agents.shared.file_utils import (
    ai_text,
    append_pending_images,
    flush_pending_image_blocks,
    strip_image_blocks_from_messages,
)
from agents.shared.llm_provider import (
    build_llm,
    encode_image,
    make_image_block,
    make_system_message,
)
from agents.shared.llm_retry import invoke_with_retry
from agents.shared.prompts import DCOI_TEMPLATE, routing_instructions
from agents.shared.routing_tools import (
    AgentHop,
    ROUTING_TOOL_NAMES,
    finalize_unanswered_tool_calls,
    log_tool_call,
)
from agents.shared.user_inputs_tool import (
    USER_INPUTS_TOOLS,
    dispatch_user_inputs_tool,
)
from agents.step_caps import MAX_DCOI_STEPS
from config import USER_INPUTS_DIR
from tools.calculate.calculate import calculate

AGENT_KEY = "dc_output_inspector"
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}

logger = logging.getLogger("propeller_agent")


_IMAGE_PERSISTENCE_ON = """\
You are STATEFUL: render images loaded in earlier cycles remain in
your message history as full image blocks AND paired
``Loaded image (path: …):`` text blocks (the path block sits
immediately before each image block).  Those images describe PAST
designs, not the current one.  Mode: KEEP IMAGES IN CONTEXT (ON)."""

_IMAGE_PERSISTENCE_OFF = """\
You are STATEFUL: render images loaded in earlier cycles have their
image bytes stripped from your history at every operation hand-off;
only the paired ``Loaded image (path: …):`` text blocks survive as a
path-only record of which images you had loaded.  To see those earlier
renders again you must explicitly re-load them from those paths via
``load_render_images``.  Mode: KEEP IMAGES IN CONTEXT (OFF)."""


# Comparison-source blocks — one per startup choice (1 / 2 / 3).
# Filled into the {comparison_mode_block} placeholder of DCOI_TEMPLATE.

_COMPARISON_MODE_1 = """\
This session is configured to compare the generated design DIRECTLY
against the USER INPUTS — the user's typed prompt
(``user_query.txt``), the user-supplied reference image(s), and
their paired ``_note.txt`` description(s).  The UII's
``extracted_inputs.txt`` is NOT your comparison source in this
mode; you compare against the user's raw materials.

**Recommended order each cycle:**
  1. ``load_render_images([...])`` — load this cycle's renders FIRST,
     and form your visual judgement of the rendered design on its
     own terms (counts, presence/absence of features, proportions)
     before reading any user material.  This ordering matters:
     loading the user material first anchors the model on the
     user's stated features, after which it tends to confabulate
     agreement on the render rather than actually counting /
     observing what the render shows.  Render-first forces an
     independent reading.
  2. ``read_input_text(path={user_query_path})`` — read the user's
     typed prompt for this design.
  3. ``read_image_notes()`` — when reference images are present,
     learn what each one depicts.
  4. ``load_input_images([...])`` — load the relevant user reference
     image(s) so you can compare them against the renders.

The comparison source(s) in scope this session: ``user_query.txt``
plus any paired image+note in ``inputs/input_images/``.  Do NOT
read ``extracted_inputs.txt`` in this mode — it is the UII's
interpretation, not the user's raw input."""

_COMPARISON_MODE_2 = """\
This session is configured to compare the generated design against
the UII's STRUCTURED EXTRACTION at ``extracted_inputs.txt`` —
specifically its ``QUANTITATIVE INPUTS`` and ``DESIGN INTENT``
sections.  The user's raw inputs (``user_query.txt``, the input
image(s), their paired note(s)) are NOT in scope for comparison
in this mode; the extraction IS the comparison source.

Path to read: ``{extracted_inputs_path}``.

**Recommended order each cycle:**
  1. ``load_render_images([...])`` — load this cycle's renders FIRST,
     and form your visual judgement of the rendered design on its
     own terms before reading the extraction.  This ordering
     matters: loading the extraction first anchors the model on
     the extraction's stated values, after which it tends to
     confabulate agreement on the render rather than actually
     counting / observing what the render shows.  Render-first
     forces an independent reading.
  2. ``read_input_text(path={extracted_inputs_path})`` — read the
     extraction.  Use the ``QUANTITATIVE INPUTS`` section
     (lock-annotated user-supplied numerics) and the
     ``DESIGN INTENT`` section (the user's goals and
     functional requirements) as your comparison source.

Do NOT load the user's raw inputs (``user_query.txt``, the input
image(s), the paired notes) in this mode.  Your comparison
source is the extraction — if the extraction is wrong, that is
an upstream UII problem to surface via the override-authority
section below, not something for you to verify against the raw
materials."""

_COMPARISON_MODE_3 = """\
This session is configured to compare the generated design
PRIMARILY against the UII's STRUCTURED EXTRACTION
(``extracted_inputs.txt`` — focusing on its
``QUANTITATIVE INPUTS`` and ``DESIGN INTENT`` sections), AND
SECONDARILY against the user's raw inputs (``user_query.txt``,
paired image+note) when you judge it necessary OR when the
extraction's ``DESIGN INTENT`` explicitly calls for it.

Path to the extraction: ``{extracted_inputs_path}``.

**Recommended order each cycle:**
  1. ``load_render_images([...])`` — load this cycle's renders FIRST,
     and form your visual judgement of the rendered design on its
     own terms before reading any comparison source.  This
     ordering matters: loading a comparison source first anchors
     the model on its stated features, after which it tends to
     confabulate agreement on the render rather than actually
     counting / observing what the render shows.  Render-first
     forces an independent reading.
  2. ``read_input_text(path={extracted_inputs_path})`` — always
     read the extraction.  Use ``QUANTITATIVE INPUTS`` and
     ``DESIGN INTENT`` as your primary comparison source.
  3. **When ANY of the following is true, ALSO consult the user's
     raw inputs**:
       - ``DESIGN INTENT`` in the extraction explicitly references
         a visual / structural feature most reliably resolvable
         from the reference image (e.g. an instruction to match
         a sketch's silhouette, layout, or proportions closely).
       - ``QUANTITATIVE INPUTS`` contains a real-world-quantity
         entry whose unit / framing seems ambiguous and the
         paired note might disambiguate.
       - You suspect the extraction may have misread something
         the user supplied (a count discrepancy, a value that
         disagrees with what is plainly visible in the
         reference image, etc.).
     Use the user-input tools as needed:
     ``list_input_files()``, ``read_input_text(path of
     {user_query_path} or a paired _note.txt)``, ``read_image_notes()``,
     ``load_input_images([...])``.
  4. **Otherwise, the extraction alone is sufficient.**  Don't
     burn LLM turns loading user inputs you don't need to consult.

The comparison source(s) in scope this session: extraction
ALWAYS, plus the user's raw inputs WHEN your judgement says they
are needed."""


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


# ---------------------------------------------------------------------------
# Utility tool schema (actual loading handled by DCOutputInspector)
# ---------------------------------------------------------------------------

@tool
def load_render_images(paths: list[str]) -> str:
    """Load one or more rendered images (PNG/JPG) from disk so you can see
    them.  Pass the full file paths that were explicitly listed in the
    incoming message (under a "Render images:" label).  Without valid
    paths, no image can be loaded — do not call this tool with guessed or
    fabricated paths.  The loaded images will be attached in the
    following user message; this tool's text output is only a loading
    summary."""
    return ""  # Actual loading is performed by _handle_load_tool.


class DCOutputInspector:
    """Stateful agent with an image-loading tool + routing tools."""

    def __init__(
        self,
        keep_images_in_context: bool = False,
        dcoi_comparison_mode: int = 3,
    ):
        self.base_llm, self.provider, self.model = build_llm(AGENT_KEY)
        self.keep_images_in_context = keep_images_in_context
        if dcoi_comparison_mode not in {1, 2, 3}:
            raise ValueError(
                f"dcoi_comparison_mode must be 1, 2, or 3 (got "
                f"{dcoi_comparison_mode!r})"
            )
        self.dcoi_comparison_mode = dcoi_comparison_mode
        self._load_tool = load_render_images
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
        """Bind routing tools (plus the utility image-loading tool)."""
        self._extra_utility_tools_by_name = {
            list_attempts.name: list_attempts,
            read_attempt.name: read_attempt,
            calculate.name: calculate,
        }
        all_tools = (
            [self._load_tool]
            + list(self._extra_utility_tools_by_name.values())
            + list(USER_INPUTS_TOOLS)
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
        self.system_prompt = DCOI_TEMPLATE.format(
            routing_instructions=routing_block,
            image_persistence_block=image_persistence_block,
            comparison_mode_block=comparison_mode_block,
        )

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    def run(self, message: str) -> AgentHop:
        """Process one hand-off message."""
        self._pending_hop = None
        text = f"Hand-off from Tool Caller:\n{message}"
        self.messages.append(HumanMessage(content=text))

        for _ in range(MAX_DCOI_STEPS):
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + self.messages,
                "DCOI",
            )
            self.messages.append(response)

            if not response.tool_calls:
                final = ai_text(response.content)
                return AgentHop(
                    "orchestrator",
                    "Error: DC Output Inspector produced a response with no "
                    "routing tool call — it wrote prose but did not invoke "
                    "call_tool_caller / call_orchestrator, so the pipeline "
                    "would otherwise halt silently.  Its raw text was:\n\n"
                    f"{final}",
                )

            routed = False
            for i, tc in enumerate(response.tool_calls):
                name = tc["name"]
                if name == "load_render_images":
                    self._handle_load_tool(tc)
                    continue
                if dispatch_user_inputs_tool(self, tc, "dc_output_inspector"):
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
                return self._pending_hop

        return AgentHop(
            "orchestrator",
            "Error: DC Output Inspector reached the step limit without routing.",
        )

    # ------------------------------------------------------------------
    # load_render_images handler
    # ------------------------------------------------------------------

    def _handle_load_tool(self, tc: dict) -> None:
        """Load the requested images and make them visible to the LLM."""
        paths = tc.get("args", {}).get("paths") or []
        if isinstance(paths, str):
            paths = [paths]

        loaded: list[str] = []
        missing: list[str] = []
        image_blocks: list[dict] = []
        image_paths: list[str] = []

        for p in paths:
            try:
                path = Path(p)
            except TypeError:
                missing.append(str(p))
                continue
            if (
                path.exists()
                and path.is_file()
                and path.suffix.lower() in ALLOWED_IMAGE_SUFFIXES
            ):
                try:
                    b64 = encode_image(path)
                    image_blocks.append(make_image_block(b64, self.provider))
                    image_paths.append(str(path.resolve()))
                    loaded.append(str(path))
                except OSError as exc:
                    missing.append(f"{path} (read error: {exc})")
            else:
                missing.append(str(p))

        parts = [f"Loaded {len(loaded)} image(s)."]
        if loaded:
            parts.append("Loaded paths:\n  " + "\n  ".join(loaded))
        if missing:
            parts.append("Missing / invalid paths:\n  " + "\n  ".join(missing))
        if image_blocks:
            parts.append(
                "The loaded images are attached in the next user message, "
                "each preceded by its absolute path so the path remains in "
                "history even if image bytes are later stripped."
            )
        else:
            parts.append(
                "No images were loaded.  Do not retry with guessed paths."
            )
        summary = "\n".join(parts)

        log_tool_call(
            "dc_output_inspector", tc["name"], tc.get("args"), summary,
        )

        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))
        if image_blocks:
            # Buffer instead of appending HumanMessage immediately, so that
            # if the LLM batched another tool_call alongside this one
            # (e.g. read_input_text), the contiguity rule is preserved.
            # The run loop flushes after the tool_calls iteration
            # completes — see file_utils.flush_pending_image_blocks.
            append_pending_images(self, image_blocks, image_paths)

    def on_operation_end(self) -> None:
        """End-of-operation hook called by the dispatcher.

        With ``keep_images_in_context=True`` this is a no-op — images
        and their paired path-text blocks both persist across
        hand-offs.

        With ``keep_images_in_context=False`` every image content
        block in this agent's history is stripped, leaving the paired
        ``Loaded image (path: …):`` text blocks behind as a path-only
        record.  Re-loading the same images later requires another
        explicit ``load_render_images`` call.
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
