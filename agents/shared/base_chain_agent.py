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
        # 5-agent topology
        "conductor":            "Conductor",
        # 3-agent topology
        "architect":            "Architect",
        "designer":             "Designer",
        "creator":              "Creator",
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
            fraction = float(getattr(_ws, "CONTEXT_PRUNER_WINDOW_FRACTION", 0.60))
            cap_tok = int(getattr(_ws, "CONTEXT_PRUNER_MAX_THRESHOLD_TOKENS", 150000))
            floor_tok = int(getattr(_ws, "CONTEXT_PRUNER_MIN_THRESHOLD_TOKENS", 20000))
            keep_n = int(getattr(_ws, "CONTEXT_PRUNER_KEEP_LAST_MESSAGES", 6))
        except Exception:
            return

        # Threshold = a share of THIS agent's model window, but never above an
        # absolute cap.  Current windows are 200k-1.05M, so on the big models
        # the CAP governs: 60% of 1M would let an agent accumulate ~600k tokens
        # of history, which costs far more in re-sent context than pruning
        # saves long before it is ever unsafe.  The fraction still binds on
        # small-window models (200k Haiku -> 120k), which is where it matters.
        try:
            from agents.shared.model_windows import context_window_for
            window = context_window_for(getattr(self, "model", "") or "")
        except Exception:
            window = 200_000
        threshold = max(floor_tok, min(int(window * fraction), cap_tok))

        pruner = getattr(self.session, "context_pruner", None)
        if pruner is None:
            return

        if not self.messages or len(self.messages) <= keep_n:
            return

        try:
            from agents.database_handler.token_utils import count_tokens
        except Exception:
            return  # token util missing — fail open

        # ------------------------------------------------------------------
        # Pre-scan — replace any single oversized message in-place with a
        # placeholder.  Runs BEFORE the threshold check so a giant
        # ToolMessage (e.g. an inline .obj mesh dump that slipped past
        # the source-side cap in agents/shared/attempts_tool.py) can't
        # poison the Pruner's own LLM call later in tier 2.  No-op when
        # no message exceeds the per-message cap.
        # ------------------------------------------------------------------
        try:
            cap_per_msg = int(getattr(
                _ws, "CONTEXT_PRUNER_MAX_INDIVIDUAL_MESSAGE_TOKENS", 30000
            ))
        except Exception:
            cap_per_msg = 30000
        if cap_per_msg > 0:
            try:
                new_msgs, n_truncated, _, _ = _truncate_oversized_messages(
                    self.messages, cap_per_msg, count_tokens
                )
                if n_truncated > 0:
                    self.messages = new_msgs
                    logger.info(
                        f"[CP]  {self.AGENT_KEY} pre-scan: truncated "
                        f"{n_truncated} oversized message(s) "
                        f"(per-message cap = {cap_per_msg} tokens)"
                    )
            except Exception as exc:
                logger.warning(
                    f"[CP]  pre-scan failed for {self.AGENT_KEY}: "
                    f"{exc}; continuing with un-scanned history."
                )

        try:
            serialised_full = _serialise_messages(self.messages)
            n_before = count_tokens(serialised_full)
            # Count the system prompt too: it is re-sent on EVERY turn and is
            # up to ~30k tokens (Planner), so leaving it out made the same
            # nominal threshold mean very different real context per agent.
            _sys_prompt = getattr(self, "system_prompt", "") or ""
            if _sys_prompt:
                n_before += count_tokens(_sys_prompt)
        except Exception as exc:
            logger.warning(
                f"[CP]  token count failed for {self.AGENT_KEY}: {exc}"
            )
            return

        if n_before <= threshold:
            return

        try:
            from agents.shared.model_windows import source_for
            _src = source_for(getattr(self, "model", "") or "")
        except Exception:
            _src = "unknown"
        logger.info(
            f"[CP]  {self.AGENT_KEY} over budget: {n_before:,} tok "
            f"(history + system prompt) > {threshold:,} threshold "
            f"[model {getattr(self, 'model', '?')}, window {window:,} "
            f"via {_src}]"
        )

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

        coarse_block = SystemMessage(
            content=(
                f"SUMMARY OF EARLIER CONVERSATION (Context Pruner tier 1; "
                f"{len(prefix)} older messages condensed into this "
                f"block):\n\n{summary}"
            )
        )
        new_history = [coarse_block] + tail
        self.messages = new_history

        try:
            n_after = count_tokens(_serialise_messages(self.messages))
        except Exception:
            n_after = -1

        logger.info(
            f"[CP]  {self.AGENT_KEY} tier 1: pruned "
            f"{len(prefix) + len(tail)} -> {len(self.messages)} "
            f"messages, ~{n_before} -> ~{n_after} tokens"
        )

        # ------------------------------------------------------------------
        # Tier 2 — if the history is STILL over threshold after tier 1,
        # summarise the still-verbatim tail too via FINE_SUMMARY_PROMPT.
        # Replaces self.messages with TWO SystemMessages (coarse + fine);
        # no verbatim tail remains.  Tool-call pairing is vacuous after
        # this because there is no AIMessage / ToolMessage left.
        # ------------------------------------------------------------------
        fine_block = None  # set below if tier 2 succeeds; used by tier 3
        if (
            n_after is not None
            and n_after > threshold
            and len(tail) > 0
        ):
            try:
                tail_text = _serialise_messages(tail)
                n_tail_before = count_tokens(tail_text)
            except Exception as exc:
                logger.warning(
                    f"[CP]  tier-2 tail serialisation/token-count "
                    f"failed for {self.AGENT_KEY}: {exc}; staying at "
                    f"tier 1."
                )
                tail_text = None
                n_tail_before = -1

            if tail_text is not None and n_tail_before > 0:
                # Hard-cap the LLM input.  Most providers reject a
                # single request whose input exceeds 100k–200k tokens
                # regardless of the model's overall context window
                # (TPM limit).  This cap protects tier 2 from hitting
                # an upstream 429 just because the pre-scan placeholder
                # plus a few "normal" messages still add up to more
                # than one call can carry.  Truncates by character
                # ratio (count_tokens is consulted to size it).
                try:
                    cap_tier2 = int(getattr(
                        _ws, "CONTEXT_PRUNER_TIER2_INPUT_CAP_TOKENS", 60000
                    ))
                except Exception:
                    cap_tier2 = 60000
                if cap_tier2 > 0 and n_tail_before > cap_tier2:
                    target_chars = max(
                        2000,
                        int(len(tail_text) * cap_tier2 / n_tail_before),
                    )
                    tail_text = (
                        tail_text[:target_chars]
                        + "\n\n...[tail truncated to honour Context "
                          "Pruner tier-2 LLM input cap]"
                    )
                    try:
                        n_tail_capped = count_tokens(tail_text)
                    except Exception:
                        n_tail_capped = -1
                    logger.info(
                        f"[CP]  {self.AGENT_KEY} tier-2 input cap: "
                        f"tail ~{n_tail_before} -> ~{n_tail_capped} "
                        f"tokens (cap = {cap_tier2})"
                    )

                try:
                    summary2 = (pruner.run(tail_text, tier=2) or "").strip()
                except Exception as exc:
                    logger.warning(
                        f"[CP]  tier-2 pruner.run failed for "
                        f"{self.AGENT_KEY}: {exc}; staying at tier 1."
                    )
                    summary2 = ""

                if summary2:
                    try:
                        n_summary2 = count_tokens(summary2)
                    except Exception:
                        n_summary2 = -1
                    # Reject the tier-2 replacement if the summary is
                    # bigger than the input it would replace — happens
                    # when the LLM expands instead of condensing.  Stay
                    # at tier 1 in that case so we never increase token
                    # count.
                    if 0 < n_summary2 < n_tail_before:
                        fine_block = SystemMessage(
                            content=(
                                f"FINE SUMMARY OF RECENT TURNS (Context "
                                f"Pruner tier 2; {len(tail)} most-recent "
                                f"messages condensed into this block):\n\n"
                                f"{summary2}"
                            )
                        )
                        self.messages = [coarse_block, fine_block]
                        try:
                            n_after_tier2 = count_tokens(
                                _serialise_messages(self.messages)
                            )
                        except Exception:
                            n_after_tier2 = -1
                        logger.info(
                            f"[CP]  {self.AGENT_KEY} tier 2: tail "
                            f"summarised, ~{n_after} -> ~{n_after_tier2} "
                            f"tokens"
                        )
                        n_after = n_after_tier2
                    else:
                        logger.warning(
                            f"[CP]  tier-2 summary REJECTED for "
                            f"{self.AGENT_KEY} (n_summary2={n_summary2} >= "
                            f"n_tail={n_tail_before}); staying at tier 1."
                        )
                else:
                    logger.warning(
                        f"[CP]  tier-2 empty summary for "
                        f"{self.AGENT_KEY}; staying at tier 1."
                    )

        # ------------------------------------------------------------------
        # Tier 3 — merge tier-1 + tier-2 summaries into ONE ultra-compact
        # super-summary via ULTRA_COMPACT_SUMMARY_PROMPT.  Only fires when
        # tier 2 actually succeeded (we have two summaries to merge);
        # otherwise compressing a single coarse summary further would
        # mostly destroy information without buying much.
        # ------------------------------------------------------------------
        if (
            n_after is not None
            and n_after > threshold
            and fine_block is not None
        ):
            combined = (
                f"{coarse_block.content}\n\n---\n\n{fine_block.content}"
            )
            try:
                n_combined = count_tokens(combined)
            except Exception:
                n_combined = -1

            try:
                super_summary = (pruner.run(combined, tier=3) or "").strip()
            except Exception as exc:
                logger.warning(
                    f"[CP]  tier-3 pruner.run failed for "
                    f"{self.AGENT_KEY}: {exc}; staying at tier 2."
                )
                super_summary = ""

            if super_summary:
                try:
                    n_super = count_tokens(super_summary)
                except Exception:
                    n_super = -1
                if 0 < n_super < (n_combined if n_combined > 0 else n_after):
                    self.messages = [
                        SystemMessage(
                            content=(
                                f"ULTRA-COMPACT SESSION SUMMARY "
                                f"(Context Pruner tier 3; tier-1 + "
                                f"tier-2 summaries merged into one):\n\n"
                                f"{super_summary}"
                            )
                        ),
                    ]
                    try:
                        n_after_tier3 = count_tokens(
                            _serialise_messages(self.messages)
                        )
                    except Exception:
                        n_after_tier3 = -1
                    logger.info(
                        f"[CP]  {self.AGENT_KEY} tier 3: merged "
                        f"summaries, ~{n_after} -> ~{n_after_tier3} "
                        f"tokens"
                    )
                    n_after = n_after_tier3
                else:
                    logger.warning(
                        f"[CP]  tier-3 summary REJECTED for "
                        f"{self.AGENT_KEY} (n_super={n_super} >= "
                        f"n_combined={n_combined}); staying at tier 2."
                    )
            else:
                logger.warning(
                    f"[CP]  tier-3 empty summary for "
                    f"{self.AGENT_KEY}; staying at tier 2."
                )

        if n_after is not None and n_after > threshold:
            logger.warning(
                f"[CP]  {self.AGENT_KEY}: ALL three tiers exhausted and "
                f"history is still ~{n_after} tokens (threshold "
                f"{threshold}).  Proceeding with invoke regardless; the "
                f"upstream LLM call may rate-limit or context-overflow."
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


def _truncate_oversized_messages(
    messages,
    max_per_message_tokens: int,
    count_tokens_fn,
    *,
    head_chars: int = 2000,
):
    """Replace any single message whose serialised content exceeds
    *max_per_message_tokens* with a placeholder of the same message
    type, preserving ``tool_call_id`` / ``tool_calls`` / ``name``
    fields so the agent's protocol contract is not broken.

    Returns ``(new_messages, n_truncated, original_tokens_total,
    new_tokens_total)``.  Caller decides whether to log / proceed.

    Why this exists: one ToolMessage carrying e.g. a 1 MB ``.obj``
    mesh dump (~333k tokens) is enough to push the Context Pruner's
    OWN tier-2 LLM call over the provider's per-request token limit,
    which 429s the whole prune chain and leaves the calling agent
    with its original oversized history.  Truncating to a bounded
    placeholder BEFORE any summarisation pass is the only thing that
    can save us from that.

    Tool-call pairing: a ``ToolMessage`` placeholder still carries
    its ``tool_call_id``, so a matching ``AIMessage(tool_calls=…)``
    still closes correctly when the LLM sees the (now compact) pair.
    """
    new: list = []
    n_truncated = 0
    original_total = 0
    new_total = 0
    for m in messages:
        body = _body_text_of(m)
        try:
            n = count_tokens_fn(body)
        except Exception:
            n = -1
        original_total += max(n, 0)

        if n > max_per_message_tokens:
            head = body[:head_chars]
            placeholder_content = (
                f"[content auto-truncated by Context Pruner pre-scan: "
                f"original was {len(body)} chars (~{n} tokens), too "
                f"large for the Pruner's own LLM to summarise in one "
                f"shot.  First {min(len(body), head_chars)} chars "
                f"shown:]\n\n{head}\n...[truncated]"
            )

            # Preserve message type + structured fields.
            try:
                if isinstance(m, ToolMessage):
                    nm = ToolMessage(
                        content=placeholder_content,
                        tool_call_id=getattr(m, "tool_call_id", ""),
                    )
                    name = getattr(m, "name", None)
                    if name:
                        nm.name = name
                elif isinstance(m, AIMessage):
                    kwargs: dict = {"content": placeholder_content}
                    if getattr(m, "tool_calls", None):
                        kwargs["tool_calls"] = m.tool_calls
                    nm = AIMessage(**kwargs)
                    name = getattr(m, "name", None)
                    if name:
                        nm.name = name
                elif isinstance(m, HumanMessage):
                    nm = HumanMessage(content=placeholder_content)
                    name = getattr(m, "name", None)
                    if name:
                        nm.name = name
                elif isinstance(m, SystemMessage):
                    nm = SystemMessage(content=placeholder_content)
                else:
                    # Unknown subclass — leave it intact rather than
                    # risk a broken constructor.
                    new.append(m)
                    new_total += max(n, 0)
                    continue
            except Exception:
                # If the replacement constructor blows up for any
                # reason, keep the original so we don't lose data.
                new.append(m)
                new_total += max(n, 0)
                continue

            new.append(nm)
            try:
                n_new = count_tokens_fn(_body_text_of(nm))
            except Exception:
                n_new = -1
            new_total += max(n_new, 0)
            n_truncated += 1
        else:
            new.append(m)
            new_total += max(n, 0)
    return new, n_truncated, original_total, new_total


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


