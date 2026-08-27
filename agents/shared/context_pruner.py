"""Context Pruner agent — reduces accumulated message history.

Stateless agent: receives a serialised message history and returns a
pruned version that preserves essential information while removing
redundant or superseded content.

How it's wired (v9 onwards)
---------------------------
Every chain agent calls ``self.prune_history_if_needed()`` at the top
of its invoke loop (see ``agents/shared/base_chain_agent.py``).  When the
agent's accumulated ``self.messages`` PLUS its system prompt crosses a
per-agent threshold — derived from the context window of the model that
agent runs on, as ``max(MIN, min(WINDOW_FRACTION x window, MAX))``; see
``agents/shared/model_windows.py`` — the pruner runs a THREE-TIER
ESCALATION:

  * **Tier 1 (coarse).**  Summarise the older portion (everything
    BEFORE the last ``CONTEXT_PRUNER_KEEP_LAST_MESSAGES`` messages)
    via ``COARSE_SUMMARY_PROMPT``.  Replace with a single
    ``SystemMessage`` at the head of the history; the latest N
    messages survive verbatim.  Cut point is auto-extended forward so
    an ``AIMessage(tool_calls)`` is never split from its matching
    ``ToolMessage``.

  * **Tier 2 (fine).**  If after Tier 1 the history is STILL above
    threshold, summarise the still-verbatim tail (the latest N
    messages) via ``FINE_SUMMARY_PROMPT`` — a more PRECISE prompt
    that asks the LLM to retain specific names, values, attempt
    numbers, last decisions, last errors verbatim.  Replace
    ``self.messages`` with exactly two ``SystemMessage``s (the
    coarse summary + the fine summary); no verbatim messages remain.

  * **Tier 3 (ultra-compact).**  If after Tier 2 it is STILL above
    threshold, merge the two summaries into ONE super-summary via
    ``ULTRA_COMPACT_SUMMARY_PROMPT``.  Keeps only the current design
    state, current task, single most-critical decision, single
    most-recent unresolved issue.  Replace ``self.messages`` with a
    single ``SystemMessage``.

The agent's ORIGINAL system prompt lives in ``self.system_prompt``
(NOT in ``self.messages``) and is rebuilt fresh at every invoke,
so pruning leaves the agent's role / rules intact — the LLM sees
the original system prompt followed by the Pruner's summary
``SystemMessage`` (or two, or one, depending on which tiers fired).

The Database Handler is intentionally NOT pruned: it iterates ~28
schedule entries in one save and relies on accumulated state to
ask coherent follow-ups.  All other chain agents are pruned.
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agents.shared import token_usage
from agents.shared.file_utils import ai_text

logger = logging.getLogger("propeller_agent")

# ---------------------------------------------------------------------------
# Pruning prompts — a shared base + a short per-tier delta.  Only ONE tier
# fires per prune (they are never concatenated), so composing them from one
# base keeps the keep/drop philosophy DRY.
# ---------------------------------------------------------------------------

_PRUNER_BASE = """\
You are the Context Pruner for a propeller design configurator system.
Your output REPLACES the history you are given, so it must be self-
contained: a reader seeing only it must be able to make the next correct
agent decision.

KEEP the signal — current design state (latest parameters, mesh / render,
assessment), specific values + attempt ids, key decisions and their
reasoning, the most recent error / unresolved issue, and the pending
instruction driving the next turn.  DROP or CONDENSE the noise —
boilerplate and restated instructions, verbose tool arguments / raw
outputs (keep only key metrics + warnings), file paths, superseded
attempts, and resolved exchanges.

Output: keep chronological order; a numbered list of
``<role>: <condensed content>`` works well."""

# Tier 1 — broad-strokes summary of the older portion; the latest window
# survives verbatim, so this pass can be aggressive.
COARSE_SUMMARY_PROMPT = _PRUNER_BASE + """

## This pass — COARSE (tier 1)
Summarise the OLDER portion — everything before the most-recent window,
which the reader sees verbatim right after you.  Be aggressive; broad
strokes are fine (e.g. "attempted N fixes; the issue was X; resolution Y")."""

# Tier 2 — fine summary of the most-recent window; fires when tier 1 was
# not enough.  This window drives the imminent decision, so stay precise.
FINE_SUMMARY_PROMPT = _PRUNER_BASE + """

## This pass — FINE (tier 2)
The older history is already coarsely summarised; you get only the MOST
RECENT window, which drives the imminent decision.  Be PRECISE — keep
specific values, attempt ids, the last decision, and the last error
VERBATIM; condense only boilerplate.  When unsure about a value, KEEP it."""

# Tier 3 — ultra-compact super-summary; fires when tiers 1+2 together
# still overflow.  Input is the two prior summaries concatenated.
ULTRA_COMPACT_SUMMARY_PROMPT = _PRUNER_BASE + """

## This pass — ULTRA-COMPACT (tier 3, final)
Two prior summaries (coarse + fine) together STILL overflow; your input is
both concatenated.  Merge them into ONE ultra-compact summary keeping
ONLY: (1) current design state, (2) the pending task / question, (3) the
single most-critical decision, (4) the single most-recent unresolved
issue.  Drop everything else — earlier attempts, resolved errors,
superseded decisions, all narrative.  Output terse short paragraphs (your
input is summaries, not a role-tagged transcript)."""


# Public alias retained for any external caller that imported the previous
# single-prompt name.  Equivalent to the coarse prompt.
SYSTEM_PROMPT = COARSE_SUMMARY_PROMPT


class ContextPruner:
    """Stateless agent that prunes message histories.

    Three tiers selected by the ``tier`` kwarg on :meth:`run`:

    * ``tier=1`` (default) — coarse summary of the older portion.
    * ``tier=2`` — fine, more-precise summary of the latest window.
    * ``tier=3`` — ultra-compact super-summary merging two prior
      summaries.

    The driver (``BaseChainAgent.prune_history_if_needed``) escalates
    tier by tier when the running token count refuses to drop below
    the threshold.
    """

    def __init__(self, llm):
        self.llm = llm

    def run(self, messages_text: str, *, tier: int = 1) -> str:
        if tier == 2:
            system_prompt = FINE_SUMMARY_PROMPT
            user_content = (
                "Summarise the following MOST RECENT window of the "
                "conversation (the rest has already been coarsely "
                "summarised separately).  Be precise — retain "
                "specific values, attempt numbers, last decisions, "
                "and last errors verbatim where possible:\n\n"
                f"{messages_text}"
            )
        elif tier == 3:
            system_prompt = ULTRA_COMPACT_SUMMARY_PROMPT
            user_content = (
                "The two summaries below cover the same conversation "
                "at different granularities.  Merge them into ONE "
                "ultra-compact super-summary; keep only the four "
                "items listed in your system prompt and drop "
                "everything else:\n\n"
                f"{messages_text}"
            )
        else:
            system_prompt = COARSE_SUMMARY_PROMPT
            user_content = (
                f"Prune the following message history:\n\n{messages_text}"
            )

        response = self.llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ])
        # The ONE LLM call in the system that does not go through
        # ``invoke_with_retry``, so it records its own usage or it would
        # be invisible — and a pruning pass reads a long history, so its
        # input cost is far from negligible.  Deliberately NOT folded
        # into the calling agent's turn total: the pruner gets its own
        # line in the per-agent breakdown.
        try:
            token_usage.record("ContextPruner", response)
        except Exception:
            logger.warning(
                "[ContextPruner]  token accounting failed; continuing",
                exc_info=True,
            )
        # ``ai_text`` and not ``response.content``: this method is
        # declared ``-> str`` and its callers rely on it — the tier-1
        # path calls ``.strip()`` on the result
        # (base_chain_agent.py:320) and tier 3 f-strings two summaries
        # together (:477).  Anthropic already returns a BLOCK LIST when
        # a turn mixes text with tool_use, and since 2026-08-27 so does
        # OpenAI on every turn when OPENAI_API_STYLE="responses" (the
        # default) — the Responses API wraps even a plain text reply as
        # ``[{"type": "text", "text": ...}]``.  Returning that raw made
        # the first prune of an OpenAI session die on
        # ``AttributeError: 'list' object has no attribute 'strip'``.
        return ai_text(response.content)
