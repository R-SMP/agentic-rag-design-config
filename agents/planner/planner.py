"""Planner agent — pipeline kickoff and problem-solving reasoning.

The Planner has TWO roles:

1. Standard kickoff: called first for a new request.  If the request is
   straightforward, it hands control straight to the User Input Inspector
   with a minimal forward message — no detailed plan needed.

2. Problem-solver: called by the Orchestrator when something has gone
   wrong.  It produces a concise Problem / Solution / Sequence plan and
   routes back to the Orchestrator, which then executes the
   non-standard sequence by calling the individual agents.

It does NOT analyse design values, does NOT invent mechanisms or file
schemas, and does NOT produce plans for simple standard cases.
"""

import logging
from datetime import datetime

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
    PLANNER_FIRST,
    PLANNER_TEMPLATE,
    routing_instructions,
)
from agents.shared.routing_tools import (
    AgentHop,
    ROUTING_TOOL_NAMES,
    finalize_unanswered_tool_calls,
    log_tool_call,
)
from agents.shared.session import AgentState, Session
from agents.shared.user_inputs_tool import (
    USER_INPUTS_TOOLS,
    USER_INPUTS_TOOL_NAMES,
    dispatch_user_inputs_tool,
)
from agents.step_caps import MAX_PLANNER_STEPS
from config import INPUT_IMAGES_SUBDIR, LOGS_DIR, USER_INPUTS_DIR
from tools.calculate.calculate import calculate

logger = logging.getLogger("propeller_agent")

_RAG_INSTRUCTIONS_ON = """
## RAG Retrieval (enabled)
If producing a problem-solving plan, note per agent whether to retrieve
from the database (Design Intent, Failure Log, etc.).  One line per agent.
RAG execution is not yet implemented.
"""

_RAG_INSTRUCTIONS_OFF = """
## RAG Retrieval (disabled)
Do not include retrieval steps.
"""

# ---------------------------------------------------------------------------
# Utility tool — read user_query.txt entries
# ---------------------------------------------------------------------------

_QUERY_HEADER_PREFIX = "--- ["


def _parse_user_query_entries(text: str) -> list[str]:
    """Split ``user_query.txt`` content into individual entries."""
    entries: list[str] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if line.startswith(_QUERY_HEADER_PREFIX):
            if current is not None:
                entries.append("\n".join(current).strip())
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        entries.append("\n".join(current).strip())
    return [e for e in entries if e]


@tool
def read_extracted_inputs(path: str) -> str:
    """Read the User Input Inspector's structured extraction.

    Pass the absolute path that the UII (or the Orchestrator)
    supplied under the ``Extracted inputs file:`` label.  Returns
    the full extraction as text.  Returns a short error string if
    the file does not exist or cannot be read.

    Use this whenever ``extracted_inputs.txt`` is present in the
    pipeline state.  In UII-first mode (PLANNER_FIRST=False) the
    Planner ALWAYS reads the extraction first and only consults the
    raw user inputs (texts + notes) afterwards if more context is
    needed."""
    from pathlib import Path
    try:
        p = Path(path)
        if not p.exists():
            return f"extracted_inputs.txt not found at {p.resolve()}."
        return p.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Error reading extracted_inputs.txt: {exc}"


@tool
def read_user_queries(n: int = 1, from_start: bool = False) -> str:
    """Return selected entries from user_query.txt.

    ``n`` (int, ≥ 1): number of entries to return.
    ``from_start`` (bool, default False): when False return the latest
    ``n`` entries; when True return the first ``n`` (oldest) entries.

    Entries are returned in chronological order, each preceded by its
    original ``--- [timestamp] ---`` header.  Returns a short message
    if the file does not exist, is empty, or has no parsable entries.
    """
    try:
        n_int = int(n)
    except (TypeError, ValueError):
        return "Error: 'n' must be an integer >= 1."
    if n_int < 1:
        return "Error: 'n' must be >= 1."

    path = USER_INPUTS_DIR / "user_query.txt"
    if not path.exists():
        return f"user_query.txt not found at {path.resolve()}."
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Error reading user_query.txt: {exc}"

    entries = _parse_user_query_entries(content)
    if not entries:
        return "user_query.txt contains no parsable entries."

    selected = entries[:n_int] if from_start else entries[-n_int:]
    label = "first" if from_start else "latest"
    header = (
        f"Showing {len(selected)} of {len(entries)} entries "
        f"({label} {n_int} requested):"
    )
    return header + "\n\n" + "\n\n".join(selected)


class Planner(BaseChainAgent):
    """Stateful planning agent with persistent message history."""

    AGENT_KEY = "planner"

    def __init__(
        self,
        state: AgentState | None = None,
        session: Session | None = None,
        *,
        llm_cache=None,
    ):
        if session is None:
            raise TypeError(
                "Planner now requires a Session.  Construct one via "
                "Session(...) or Session.create_for_v3(...) and pass "
                "it in."
            )
        if state is None:
            state = AgentState(agent_key=self.AGENT_KEY)
        super().__init__(state=state, session=session, llm_cache=llm_cache)
        self.rag_enabled = session.rag_enabled
        # current_plan is restored by BaseChainAgent from
        # state.current_plan (default "").
        self._tools_by_name: dict = {}
        self.system_prompt: str = ""

    # ------------------------------------------------------------------
    # Wiring (called once after all agents are constructed)
    # ------------------------------------------------------------------

    def set_routing_tools(
        self,
        tools: list,
        history_tool=None,
    ) -> None:
        """Bind this Planner's utility + routing tools."""
        extra_utility = [history_tool] if history_tool is not None else []
        attempts_utility = [list_attempts, read_attempt, new_attempt]
        all_tools = (
            [read_user_queries, read_extracted_inputs, calculate]
            + extra_utility
            + attempts_utility
            + list(USER_INPUTS_TOOLS)
            + list(tools)
        )
        self.llm = self.base_llm.bind_tools(all_tools)
        self._tools_by_name = {t.name: t for t in all_tools}
        rag_block = (
            _RAG_INSTRUCTIONS_ON if self.rag_enabled else _RAG_INSTRUCTIONS_OFF
        )
        if PLANNER_FIRST:
            routing_block = routing_instructions(
                agent_name="Planner",
                next_agent="User Input Inspector",
                prev_agent=None,
                fragment_name="routing_planner_planner_first.md",
            )
        else:
            routing_block = routing_instructions(
                agent_name="Planner",
                next_agent="DC Input Creator",
                prev_agent="User Input Inspector",
                fragment_name="routing_planner_uii_first.md",
            )
        self.system_prompt = PLANNER_TEMPLATE.format(
            rag_instructions=rag_block,
            routing_instructions=routing_block,
            user_inputs_dir=str(USER_INPUTS_DIR.resolve()),
            input_images_subdir=INPUT_IMAGES_SUBDIR,
            extraction_output_file=str(
                (USER_INPUTS_DIR / "extracted_inputs.txt").resolve()
            ),
        )

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    def run(self, message: str) -> AgentHop:
        """Process one hand-off message and return the chosen hop."""
        self._pending_hop = None
        self.messages.append(HumanMessage(content=message))

        for _ in range(MAX_PLANNER_STEPS):
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + self.messages,
                "Planner",
            )
            self.messages.append(response)

            if not response.tool_calls:
                final = ai_text(response.content)
                self._persist_plan(response, pending_hop=None)
                return AgentHop(
                    "orchestrator",
                    "Error: Planner produced a response with no routing tool "
                    "call — it wrote prose but did not invoke "
                    "call_user_input_inspector or call_orchestrator, so the "
                    "pipeline would otherwise halt silently.  Its raw text "
                    f"was:\n\n{final}",
                )

            routed = False
            for i, tc in enumerate(response.tool_calls):
                name = tc["name"]
                if name in USER_INPUTS_TOOL_NAMES:
                    dispatch_user_inputs_tool(self, tc, "planner")
                    continue
                tool_fn = self._tools_by_name.get(name)
                if tool_fn is None:
                    result = f"Error: unknown tool '{name}'"
                else:
                    try:
                        result = tool_fn.invoke(tc["args"])
                    except Exception as exc:
                        result = f"Error calling {name}: {exc}"
                        logger.error(f"[PLANNER TOOL ERROR] {name}: {exc}")
                if name not in ROUTING_TOOL_NAMES:
                    log_tool_call("planner", name, tc.get("args"), result)
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

            # Flush any image content blocks buffered by load_input_images
            # as a single trailing HumanMessage AFTER all ToolMessages
            # for this AIMessage are appended.  Preserves the
            # tool_use → tool_result contiguity rule on Anthropic / OpenAI.
            flush_pending_image_blocks(self)

            self._persist_plan(response, pending_hop=self._pending_hop)

            if routed:
                return self._pending_hop

        return AgentHop(
            "orchestrator",
            "Error: Planner reached step limit without routing.",
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_plan(self, response, pending_hop) -> None:
        """Capture the long and short parts of this turn's plan and
        write them to ``current_plan.txt``."""
        long_plan = ai_text(getattr(response, "content", "")).strip()
        short_plan = (
            pending_hop.message.strip()
            if pending_hop is not None
            and getattr(pending_hop, "message", "")
            else ""
        )
        if not long_plan and not short_plan:
            return

        sections: list[str] = []
        if long_plan:
            sections.append(
                "--- Full plan (Planner's reasoning; Part 1, response "
                "content) ---\n" + long_plan
            )
        else:
            sections.append(
                "--- Full plan (Planner's reasoning; Part 1, response "
                "content) ---\n"
                "(Not produced as natural-language content this turn — "
                "the LLM placed everything in the routing tool's "
                "message argument; see the short version below.)"
            )
        if short_plan:
            sections.append(
                "--- Short actionable message (Part 2, routing tool's "
                "message argument) ---\n" + short_plan
            )
        else:
            sections.append(
                "--- Short actionable message (Part 2, routing tool's "
                "message argument) ---\n"
                "(None recorded — the LLM did not invoke a routing "
                "tool this turn.)"
            )

        self.current_plan = "\n\n".join(sections)
        self._save_plan_to_file()

    def _save_plan_to_file(self) -> None:
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            plan_path = LOGS_DIR / "current_plan.txt"
            plan_path.write_text(
                f"Plan updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                f"\n\n{self.current_plan}\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    def on_operation_end(self) -> None:
        """End-of-operation hook called by the dispatcher.

        With ``keep_images_in_context=False`` strip every image content
        block from this agent's history (the Planner can load user
        input images via ``load_input_images`` for special reasoning),
        leaving the paired ``Loaded image (path: …):`` text blocks
        behind.  No-op when ``keep_images_in_context=True``.
        """
        if self.keep_images_in_context:
            return
        removed = strip_image_blocks_from_messages(self.messages)
        if removed:
            logger.info(
                f"[PLANNER]  on_operation_end stripped {removed} image "
                f"block(s); paired path-text blocks retained."
            )

    def reset(self) -> None:
        self.messages.clear()
        self.current_plan = ""
