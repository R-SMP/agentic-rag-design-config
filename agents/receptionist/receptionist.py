"""Receptionist agent — user-facing communication and input validation.

The Receptionist is the bridge between the user and the rest of the system.
It:
1. Reads user input files from a given directory path.
2. Reasons about the user's message and either forwards into the
   pipeline (by invoking its ``call_orchestrator`` routing tool) or
   replies to the user directly (by producing plain text with no tool
   call).
3. Formats outgoing messages from the system to the user.

The Receptionist owns two routing-relevant tools:
  * ``read_agent_history`` — inspects what other agents did in prior
    runs, so simple user questions can be answered without re-running
    the pipeline.
  * ``call_orchestrator`` — forwards control into the pipeline.
"""

import logging
import time
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage

from agents.shared.attempts_tool import list_attempts, read_attempt
from agents.step_caps import MAX_RECEPTIONIST_STEPS
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.file_utils import (
    ai_text,
    load_user_inputs_bundle,
    strip_image_blocks_from_messages,
)
from agents.shared.llm_provider import make_system_message
from agents.shared.llm_retry import invoke_with_retry
from agents.shared.prompts import RECEPTIONIST_TEMPLATE
from agents.shared.routing_tools import (
    AgentHop,
    DONE,
    ROUTING_TOOL_NAMES,
    finalize_unanswered_tool_calls,
)
from agents.shared.session import AgentState, Session
from agents.shared.user_inputs_tool import (
    dispatch_user_inputs_tool,
    list_input_files,
    read_image_notes,
    read_input_text,
)
from config import ATTEMPTS_DIR
from tools.calculate.calculate import calculate
from tools.visualize_model.visualize_model import visualize_3d_model

logger = logging.getLogger("propeller_agent")


class Receptionist(BaseChainAgent):
    """Stateful agent that manages user communication."""

    AGENT_KEY = "receptionist"

    def __init__(
        self,
        state: AgentState | None = None,
        session: Session | None = None,
        *,
        llm_cache=None,
    ):
        if session is None:
            raise TypeError(
                "Receptionist now requires a Session.  Construct one "
                "via Session(...) or Session.create_for_v3(...) and "
                "pass it in."
            )
        if state is None:
            state = AgentState(agent_key=self.AGENT_KEY)
        super().__init__(state=state, session=session, llm_cache=llm_cache)
        self.system_prompt: str = RECEPTIONIST_TEMPLATE
        self._tools_by_name: dict = {}
        # Receptionist resets cycle_start_ts at the start of every
        # validate_input call.  When restoring from a fresh AgentState
        # (cycle_start_ts is None), seed it to "now" so a
        # format_outgoing call before any validate_input still has a
        # well-defined starting point for the freshness filter.
        # Otherwise honour the snapshot value.
        if self.cycle_start_ts is None:
            self.cycle_start_ts = time.time()

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def set_tools(self, tools: list) -> None:
        """Bind ``read_agent_history``, ``calculate``, ``list_attempts``,
        ``read_attempt``, the user-inputs inspection tools (listing,
        reading text, reading image notes — but NOT loading image
        bytes; the Receptionist does not analyse images itself),
        ``visualize_3d_model`` (push a generated mesh to the web
        viewer), plus the ``call_orchestrator`` routing tool."""
        all_tools = list(tools) + [
            calculate,
            list_attempts,
            read_attempt,
            list_input_files,
            read_input_text,
            read_image_notes,
            visualize_3d_model,
        ]
        self._tools_by_name = {t.name: t for t in all_tools}
        self.llm = self.base_llm.bind_tools(all_tools)

    # ------------------------------------------------------------------
    # Helper — run the LLM loop with optional tool-calling
    # ------------------------------------------------------------------

    def _run_llm_loop(self) -> str:
        """Invoke the LLM and resolve any tool calls iteratively.

        Terminates when the LLM produces a plain-text response with no
        tool call OR when it invokes a routing tool (in which case
        ``self._pending_hop`` is already set and the loop exits).
        Returns the final assistant text; when the loop exited on a
        routing-tool invocation the text may be empty — the caller
        should prefer ``self._pending_hop.message`` in that case.
        """
        for _ in range(MAX_RECEPTIONIST_STEPS):
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + self.messages,
                "Receptionist",
            )
            self.messages.append(response)

            if not getattr(response, "tool_calls", None):
                return ai_text(response.content)

            routed = False
            for i, tc in enumerate(response.tool_calls):
                name = tc["name"]
                if dispatch_user_inputs_tool(self, tc, "receptionist"):
                    continue
                tool_fn = self._tools_by_name.get(name)
                if tool_fn is None:
                    result = f"Error: unknown tool '{name}'"
                else:
                    try:
                        result = tool_fn.invoke(tc["args"])
                    except Exception as exc:
                        result = f"Error calling {name}: {exc}"
                        logger.error(
                            f"[RECEPTIONIST TOOL ERROR] {name}: {exc}"
                        )
                self.messages.append(ToolMessage(
                    content=str(result),
                    tool_call_id=tc["id"],
                    name=name,
                ))
                if (
                    name in ROUTING_TOOL_NAMES
                    and self._pending_hop is not None
                ):
                    routed = True
                    finalize_unanswered_tool_calls(
                        self.messages, response.tool_calls, i + 1,
                    )
                    break

            if routed:
                return ""

        return (
            "I'm sorry — I wasn't able to finish preparing a response "
            "this turn.  Please try again."
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_input(self, input_dir: str | Path) -> dict:
        """Read the user's input files and let the LLM decide what to do.

        Returns
        -------
        dict with keys:
            forward    : bool  — True if the LLM invoked
                                 ``call_orchestrator`` to forward into
                                 the pipeline; False if it chose to
                                 reply to the user directly.
            message    : str   — the Orchestrator-bound prose when
                                 ``forward`` is True, or the user-facing
                                 reply when it is False.
            input_dir  : str   — resolved directory path.
            file_types : list  — categories of files found (populated
                                 only when forwarding).
        """
        # Mark the start of a new user cycle.  format_outgoing() will
        # filter render / parameter artifacts against this timestamp so
        # stale files from previous runs are not reported as current.
        self.cycle_start_ts = time.time()
        self._pending_hop = None

        input_path = Path(input_dir)
        # The Receptionist does NOT analyse images itself, so the
        # bundle is loaded with image bytes EXCLUDED.  Image filenames
        # + every <name>_note.txt's content are still surfaced (so the
        # LLM can decide whether each image's described purpose fits
        # the design workflow), and the pairing report flags any
        # orphan image / note that the user must fix before forwarding.
        loaded = load_user_inputs_bundle(
            input_path, self.provider, include_image_bytes=False,
        )
        pairing = loaded["pairing"]
        pairing_banner = (
            "Image+note pairing: OK"
            if pairing["ok"]
            else "Image+note pairing: INVALID — see pairing report below"
        )

        text = (
            f"[Incoming from: User]\n\n"
            f"User input files from: {input_path.resolve()}\n"
            f"Files found: {loaded['summary']}\n"
            f"{pairing_banner}\n\n"
            f"{loaded['text_content']}"
        )
        if not loaded["text_content"]:
            text += "\n(No readable content found in the input directory.)"

        self.messages.append(HumanMessage(content=text))

        reply = self._run_llm_loop().strip()

        # Receptionist bypasses the dispatcher's per-hop hook, so it
        # invokes its own on_operation_end after every operation
        # boundary (forwarding to the Orchestrator and replying
        # directly to the user both count).
        self.on_operation_end()

        if (
            self._pending_hop is not None
            and self._pending_hop.target == "orchestrator"
        ):
            categories = list({f["category"] for f in loaded["root_files"]})
            if loaded["image_paths"]:
                categories.append("image")
            return {
                "forward": True,
                "message": self._pending_hop.message.strip(),
                "input_dir": str(input_path.resolve()),
                "file_types": categories,
            }

        return {
            "forward": False,
            "message": reply,
            "input_dir": str(input_path.resolve()),
            "file_types": [],
        }

    def format_outgoing(self, system_result: str) -> str:
        """Compose a user-facing response from the system's technical result.

        The Orchestrator's hand-off now names the attempt folder(s)
        this cycle and which to show the user; the Receptionist pulls
        each one's parameters / render paths itself via its
        ``read_attempt`` / ``list_attempts`` tools (see prompt).  Only
        when the hand-off carries NO attempt-folder reference do we
        fall back to the legacy behaviour of auto-attaching the single
        most-recently-touched attempt's fresh artifacts, so a summary
        that never references an attempt path still works.
        """
        self._pending_hop = None
        text = f"System message to relay to the user:\n{system_result}"

        if not self._handoff_names_attempt(system_result):
            def _is_fresh(path: Path) -> bool:
                try:
                    return (
                        path.exists()
                        and path.stat().st_mtime >= self.cycle_start_ts
                    )
                except OSError:
                    return False

            latest_attempt = self._latest_active_attempt()
            if latest_attempt is not None:
                params_path = latest_attempt / "parameters.json"
                if _is_fresh(params_path):
                    text += (
                        f"\n\nDC parameters written this cycle (attempt "
                        f"folder: {latest_attempt.resolve()}; use these "
                        f"exact values if listing parameters — do not "
                        f"invent names or values):\n"
                        f"{params_path.read_text(encoding='utf-8')}"
                    )

                render_names = (
                    "render_isometric.png", "render_top.png",
                    "render_side.png",
                )
                render_files = [
                    str((latest_attempt / n).resolve())
                    for n in render_names
                    if _is_fresh(latest_attempt / n)
                ]
                if render_files:
                    text += (
                        "\n\nConfirmed render files produced this cycle "
                        "(attempt folder: "
                        f"{latest_attempt.resolve()}):\n"
                        + "\n".join(render_files)
                    )

        self.messages.append(HumanMessage(content=text))
        composed = self._run_llm_loop()

        if self._pending_hop is not None:
            logger.warning(
                "[RECEPTIONIST]  LLM invoked a routing tool in Situation B "
                "(user-facing composition); ignoring the hop and returning "
                "whatever text was produced."
            )

        # format_outgoing also bypasses the dispatcher; invoke the
        # operation-end hook here.  format_outgoing itself does not
        # load images, but a previous validate_input on this same
        # session may have, and they should also be pruned now if
        # KEEP IMAGES IN CONTEXT is OFF.
        self.on_operation_end()

        return composed

    @staticmethod
    def _latest_active_attempt() -> Path | None:
        """Return the most recently-modified attempt folder, or None."""
        if not ATTEMPTS_DIR.exists():
            return None
        candidates: list[tuple[float, Path]] = []
        try:
            for child in ATTEMPTS_DIR.iterdir():
                if child.is_dir():
                    try:
                        candidates.append((child.stat().st_mtime, child))
                    except OSError:
                        continue
        except OSError:
            return None
        if not candidates:
            return None
        return max(candidates, key=lambda x: x[0])[1]

    @staticmethod
    def _handoff_names_attempt(system_result: str) -> bool:
        """True if the Orchestrator's hand-off references an attempt
        folder path.  When so, the Receptionist pulls each attempt's
        details via its ``read_attempt`` / ``list_attempts`` tools per
        the prompt, and the legacy single-newest-attempt auto-attach
        in ``format_outgoing`` is skipped.  Detected by the
        ATTEMPTS_DIR path appearing in the summary — robust to wording
        because every absolute attempt path contains the attempts
        root."""
        if not system_result:
            return False
        try:
            root = str(ATTEMPTS_DIR.resolve())
        except OSError:
            root = str(ATTEMPTS_DIR)
        return (
            root.replace("\\", "/").lower()
            in system_result.replace("\\", "/").lower()
        )

    def run(self, message: str) -> AgentHop:
        """Compose a user-facing message and return a terminal hop."""
        return AgentHop(DONE, self.format_outgoing(message))

    def on_operation_end(self) -> None:
        """End-of-operation hook.

        With ``keep_images_in_context=False`` strip every image content
        block from this agent's history, leaving the paired
        ``Loaded image (path: …):`` text blocks behind.  No-op when
        ``keep_images_in_context=True``.

        Unlike DCOI / UII (which the dispatcher invokes after every
        ``run()``), the Receptionist's two entry points
        (``validate_input`` / ``format_outgoing``) bypass the
        dispatcher and call this hook themselves.
        """
        if self.keep_images_in_context:
            return
        removed = strip_image_blocks_from_messages(self.messages)
        if removed:
            logger.info(
                f"[RECEPTIONIST]  on_operation_end stripped {removed} "
                f"image block(s); paired path-text blocks retained."
            )

