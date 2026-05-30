"""BaseChainAgent — shared lifecycle plumbing for the 7 chain agents.

Subclasses (Receptionist, Planner, UII, DCIC, DCII, ToolCaller, DCOI)
inherit:

  * LLM lookup via ``llm_client_cache`` (replaces the per-agent
    ``build_llm(AGENT_KEY)`` call in each subclass's ``__init__``).
  * Common state restore: ``messages``, ``_pending_hop``, image
    buffers, plus the optional Receptionist (``cycle_start_ts``) and
    Planner (``current_plan``) fields are restored uniformly.
  * Symmetric ``snapshot_state()`` that captures everything back into
    a fresh ``AgentState`` ready for storage.
  * Session-config flag forwarding (``keep_images_in_context``).

Subclasses MUST set the class attribute ``AGENT_KEY`` and provide
their own:
  * ``system_prompt`` assembly (each agent's prompt template differs
    and may include session-config-derived blocks).
  * ``set_routing_tools()`` / ``set_tools()`` (signatures differ per
    agent — some take a ``next_agent`` arg, some ``prev_agent``,
    Receptionist takes neither).
  * ``_run_llm_loop()`` (tool dispatch logic is agent-specific —
    Planner has image loaders, Tool Caller has mesh tools, DCOI has
    render loaders, ...).

This module does NOT touch the dispatch / routing pipeline.  Which
agent calls which is determined by the routing tools each agent gets
bound to and by the Orchestrator's ``dispatch`` loop, neither of
which this base class affects.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agents.shared import llm_client_cache as _default_llm_cache
from agents.shared.routing_tools import AgentHop
from agents.shared.session import AgentState, Session

logger = logging.getLogger("propeller_agent")


class BaseChainAgent:
    """Common scaffolding for chain agents — see module docstring."""

    AGENT_KEY: ClassVar[str]  # subclasses must set

    def __init__(
        self,
        state: AgentState,
        session: Session,
        llm_cache=None,
    ):
        if not getattr(self, "AGENT_KEY", None):
            raise TypeError(
                f"{type(self).__name__} must define class attribute "
                f"AGENT_KEY before subclassing BaseChainAgent."
            )
        if state.agent_key != self.AGENT_KEY:
            raise ValueError(
                f"AgentState.agent_key={state.agent_key!r} does not "
                f"match this class's AGENT_KEY={self.AGENT_KEY!r}."
            )

        cache = llm_cache if llm_cache is not None else _default_llm_cache
        self.base_llm, self.provider, self.model = cache.get_for_agent(
            self.AGENT_KEY
        )
        # Most subclasses re-bind ``self.llm`` in ``set_routing_tools``
        # / ``set_tools`` to the tool-bound version.
        self.llm = self.base_llm

        self.session = session
        # Session-config flags forwarded onto self for backwards
        # compatibility with v4 code that reads ``self.keep_images_in_
        # context`` directly.  Other flags (rag_enabled, etc.) are
        # subclass-specific and stay in subclass __init__.
        self.keep_images_in_context = session.keep_images_in_context

        # Restore plain-data state.  Lists are shallow-copied so
        # mutating this agent's fields does not retroactively edit
        # the snapshot the agent was built from.
        self.messages = list(state.messages)
        self._pending_hop = (
            None if state.pending_hop is None
            else AgentHop(**state.pending_hop)
        )
        self._pending_image_blocks = list(state.pending_image_blocks)
        self._pending_image_paths = list(state.pending_image_paths)

        # Optional agent-specific fields, restored uniformly so every
        # subclass has a well-defined attribute.  ``cycle_start_ts``
        # is only meaningful for Receptionist; ``current_plan`` only
        # for Planner.  Other agents carry the defaults harmlessly.
        self.cycle_start_ts = state.cycle_start_ts
        self.current_plan = state.current_plan

    def snapshot_state(self) -> AgentState:
        """Return a fresh ``AgentState`` with this agent's current state.

        All optional fields are captured uniformly via getattr-with-
        default so subclasses do not need to override.  Receptionist
        will have ``cycle_start_ts`` populated; Planner will have
        ``current_plan``; other agents will have both at the default
        (None / "").
        """
        hop_dict = None
        if self._pending_hop is not None:
            hop_dict = {
                "target":  self._pending_hop.target,
                "message": self._pending_hop.message,
            }
        return AgentState(
            agent_key=self.AGENT_KEY,
            messages=list(self.messages),
            pending_hop=hop_dict,
            pending_image_blocks=list(
                getattr(self, "_pending_image_blocks", [])
            ),
            pending_image_paths=list(
                getattr(self, "_pending_image_paths", [])
            ),
            cycle_start_ts=getattr(self, "cycle_start_ts", None),
            current_plan=getattr(self, "current_plan", ""),
        )

    def reset(self) -> None:
        """Clear conversation history.  Subclasses may override."""
        self.messages.clear()

    # ------------------------------------------------------------------
    # Context Pruner integration (F7)
    # ------------------------------------------------------------------
    # Display label used for the ``agent_active`` events the LOG-and-
    # Status chart consumes.  Maps the AGENT_KEY back to the
    # human-readable name the frontend's ``FLOW_BOX_BY_NAME`` keys on.
    _PRUNE_DISPLAY_NAMES: ClassVar[dict] = {
        "receptionist":         "Receptionist",
        "orchestrator":         "Orchestrator",
        "user_input_inspector": "User Input Inspector",
        "planner":              "Planner",
        "dc_input_creator":     "DC Input Creator",
        "dc_input_inspector":   "DC Input Inspector",
        "dc_output_inspector":  "DC Output Inspector",
        "tool_caller":          "Tool Caller",
    }

    def prune_history_if_needed(self) -> None:
        """Pre-invoke check: if ``self.messages`` has grown past the
        configured token threshold, summarise the older portion via
        the session's Context Pruner and replace it with a single
        SystemMessage block, keeping the last N messages verbatim.

        Idempotent and exception-safe — any failure (settings missing,
        pruner absent, tokeniser error, LLM error) logs a warning and
        leaves ``self.messages`` untouched so the live invoke still
        runs against the original history.

        Hooked from each chain agent's ``_run_llm_loop`` right before
        ``invoke_with_retry``.  The Database Handler intentionally
        does NOT call this — it iterates ~28 schedule entries in one
        save and relies on the accumulated state.
        """
        try:
            from workflow_settings import settings as _ws
            if not getattr(_ws, "CONTEXT_PRUNER_ENABLED", False):
                return
            threshold = int(getattr(_ws, "CONTEXT_PRUNER_THRESHOLD_TOKENS", 80000))
            keep_n = int(getattr(_ws, "CONTEXT_PRUNER_KEEP_LAST_MESSAGES", 6))
        except Exception:
            return

        pruner = getattr(self.session, "context_pruner", None)
        if pruner is None:
            return

        if not self.messages or len(self.messages) <= keep_n:
            return

        try:
            from agents.database_handler.token_utils import count_tokens
        except Exception:
            return  # token util missing — fail open

        try:
            serialised_full = _serialise_messages(self.messages)
            n_before = count_tokens(serialised_full)
        except Exception as exc:
            logger.warning(
                f"[CP]  token count failed for {self.AGENT_KEY}: {exc}"
            )
            return

        if n_before <= threshold:
            return

        # Pick the cut point: keep the last keep_n messages, then walk
        # forward (toward the tail) until we land on a "safe" boundary
        # that doesn't orphan an AIMessage(tool_calls) from its matching
        # ToolMessage(s).
        cut = max(0, len(self.messages) - keep_n)
        cut = _safe_cut_point(self.messages, cut)
        if cut <= 0 or cut >= len(self.messages):
            return  # nothing to prune (or whole history would go)

        prefix = self.messages[:cut]
        tail = self.messages[cut:]
        prefix_text = _serialise_messages(prefix)

        display = self._PRUNE_DISPLAY_NAMES.get(
            self.AGENT_KEY, self.AGENT_KEY
        )

        # Publish the entry handoff so the LOG-and-Status chart lights
        # up the Context Pruner box alongside the calling agent's box
        # (matches the tool_active pattern used by the DC tools).  No
        # ``generic_tool`` event is published: the calling agent's box
        # already lights up CP visually, and routing a caption to all
        # active boxes would write "Pruning X" under the caller too,
        # which is redundant.
        _publish_cp_active(display, "Context Pruner")

        try:
            summary = pruner.run(prefix_text) or ""
        except Exception as exc:
            logger.warning(
                f"[CP]  pruner.run failed for {self.AGENT_KEY}: {exc}; "
                f"skipping prune."
            )
            _publish_cp_active("Context Pruner", display)
            return
        finally:
            # Tool exit handoff is published regardless — even on the
            # error path so the chart doesn't leave CP highlighted.
            pass

        summary = summary.strip()
        if not summary:
            logger.warning(
                f"[CP]  empty summary returned for {self.AGENT_KEY}; "
                f"skipping prune."
            )
            _publish_cp_active("Context Pruner", display)
            return

        new_history = [
            SystemMessage(
                content=(
                    f"SUMMARY OF EARLIER CONVERSATION (pruned by the "
                    f"Context Pruner; {len(prefix)} older messages "
                    f"condensed into this block):\n\n{summary}"
                )
            ),
        ] + tail
        self.messages = new_history

        try:
            n_after = count_tokens(_serialise_messages(self.messages))
        except Exception:
            n_after = -1

        logger.info(
            f"[CP]  {self.AGENT_KEY}: pruned history "
            f"{len(prefix) + len(tail)} -> {len(self.messages)} "
            f"messages, ~{n_before} -> ~{n_after} tokens"
        )
        _publish_cp_active("Context Pruner", display)


# ---------------------------------------------------------------------------
# Helpers — exposed at module level so they can be unit-tested without
# instantiating an agent.
# ---------------------------------------------------------------------------


def _serialise_messages(messages) -> str:
    """Render a list of langchain BaseMessages to plain text.

    Used by both the token estimator and the Pruner's input.  Image
    content blocks are replaced with a brief ``[image: ...]``
    placeholder so they don't waste pruning tokens on encoded bytes.
    """
    out: list[str] = []
    for i, m in enumerate(messages):
        role = _role_of(m)
        body = _body_text_of(m)
        out.append(f"{i + 1}. {role}: {body}")
    return "\n".join(out)


def _role_of(m) -> str:
    if isinstance(m, SystemMessage):
        return "SYSTEM"
    if isinstance(m, HumanMessage):
        return "USER"
    if isinstance(m, AIMessage):
        return "ASSISTANT"
    if isinstance(m, ToolMessage):
        return "TOOL_RESULT"
    return m.__class__.__name__.upper()


def _body_text_of(m) -> str:
    content = getattr(m, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Mixed-content message (langchain blocks): text + images.
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                parts.append(str(block))
                continue
            btype = block.get("type")
            if btype == "text":
                parts.append(str(block.get("text", "")))
            elif btype in ("image", "image_url"):
                parts.append("[image: redacted for pruning]")
            elif btype == "tool_use":
                parts.append(
                    f"[tool_use: {block.get('name', '?')}]"
                )
            else:
                parts.append(f"[{btype}: ...]")
        return " ".join(parts)
    return str(content)


def _safe_cut_point(messages, desired_cut: int) -> int:
    """Adjust *desired_cut* forward (toward the tail) so the prefix
    being pruned does NOT contain an ``AIMessage`` with ``tool_calls``
    whose matching ``ToolMessage`` would otherwise survive into the
    kept tail.

    Concretely: if ``messages[desired_cut - 1]`` is a ``ToolMessage``
    that pairs with an ``AIMessage(tool_calls=...)`` further back, the
    cut is fine (both sides are in the prefix).  If
    ``messages[desired_cut - 1]`` is an ``AIMessage`` with tool_calls
    AND any of those tool_call_ids show up as a ``ToolMessage`` at
    ``messages[desired_cut:]``, advance ``desired_cut`` forward past
    those ToolMessages.

    Walks forward at most ``len(messages)`` steps; never returns a
    cut greater than ``len(messages)``.
    """
    if desired_cut <= 0 or desired_cut >= len(messages):
        return desired_cut

    # Collect pending tool_call ids from the prefix that haven't been
    # answered by a ToolMessage yet (in the prefix).
    pending: set[str] = set()
    for m in messages[:desired_cut]:
        if isinstance(m, AIMessage):
            for tc in (getattr(m, "tool_calls", None) or []):
                tcid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if tcid:
                    pending.add(str(tcid))
        elif isinstance(m, ToolMessage):
            tcid = getattr(m, "tool_call_id", None)
            if tcid in pending:
                pending.discard(tcid)
    if not pending:
        return desired_cut

    # Advance forward, absorbing any ToolMessage that closes a pending
    # tool_call from the prefix.  Stop when no pending ids remain.
    new_cut = desired_cut
    while new_cut < len(messages) and pending:
        m = messages[new_cut]
        if isinstance(m, ToolMessage):
            tcid = getattr(m, "tool_call_id", None)
            if tcid in pending:
                pending.discard(tcid)
                new_cut += 1
                continue
        # A non-ToolMessage before the pending ids are closed is a
        # malformed history — bail to the original cut and let the
        # invoke proceed (worst case the LLM sees an orphaned
        # AIMessage; not our problem to fix here).
        return desired_cut
    return new_cut


def _publish_cp_active(from_name: str, to_name: str) -> None:
    """Publish an ``agent_active`` event on the viz bus so the LOG-
    and-Status chart can highlight the Context Pruner box (and keep
    the caller's box highlighted alongside it via the existing
    multi-active rule the frontend applies to known tool names)."""
    try:
        from agents.shared.viz_bus import publish as _publish
        _publish({
            "type": "agent_active",
            "from": from_name,
            "to":   to_name,
            "note": "context-prune",
        })
    except Exception:
        pass


