"""Context Pruner agent — reduces accumulated message history.

Stateless agent: receives a serialised message history and returns a
pruned version that preserves essential information while removing
redundant or superseded content.

How it's wired (v9 onwards)
---------------------------
Every chain agent calls ``self.prune_history_if_needed()`` at the top
of its invoke loop (see ``agents/shared/base_chain_agent.py``).  When
the agent's accumulated ``self.messages`` crosses
``workflow_settings.CONTEXT_PRUNER_THRESHOLD_TOKENS`` (cl100k_base),
the pruner runs a THREE-TIER ESCALATION:

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

from langchain_core.messages import HumanMessage, SystemMessage

# Tier 1 — broad-strokes summary of the older portion of the history.
# The latest N messages survive verbatim, so this summary can afford
# to be aggressive: it covers everything BEFORE the most-recent
# window, and the LLM will see the verbatim window right after it.
COARSE_SUMMARY_PROMPT = """\
You are the Context Pruner for a propeller design configurator system.

## Your Role
When an agent's message history grows too long, prune it to keep only
the essential information.  Your output replaces the agent's history.

## What to REMOVE
- Old image render descriptions that have been superseded by newer ones.
- User messages referring to requests that are no longer being pursued.
- Verbose tool-call arguments and raw tool outputs (keep only key findings).
- Redundant back-and-forth that has been resolved.
- Repetitive error messages from the same root cause.

## What to KEEP
- The current design requirements and parameters.
- Important decisions and their reasoning.
- The most recent error messages and lessons learned.
- The current state of the design (latest parameters, latest assessment).
- Any unresolved issues or pending questions.

## What to SUMMARISE (replace verbose content with a brief summary)
- Multiple attempts at fixing a design → "Attempted N fixes; main issue
  was X; resolution was Y."
- Old visual-render descriptions → one-line summary of findings.
- Long tool outputs → key metrics and warnings only.

## Output Format
Return a condensed version of the conversation as a numbered list of
concise messages.  Each entry should state:
  <role>: <condensed content>

Preserve chronological order.  The result must be self-contained —
someone reading only your output should understand the full context.
"""

# Tier 2 — fine summary of the MOST RECENT window.  Fires only when
# Tier 1 was not enough.  Because this window is small (the last
# ``CONTEXT_PRUNER_KEEP_LAST_MESSAGES`` messages) and immediately
# precedes the next agent decision, the summary should be more
# PRECISE than the coarse one — keep specific values, attempt
# numbers, last decisions, last errors verbatim where possible.
# Condense only the verbose framing (handshakes, restated
# instructions, tool-call boilerplate).
FINE_SUMMARY_PROMPT = """\
You are the Context Pruner for a propeller design configurator system.

## Your Role (TIER 2 — fine summary)
You are being called as a SECOND PASS, after a coarse summary already
condensed the older portion of the conversation.  Your input is the
MOST RECENT window of the conversation only.  Your output replaces
those latest messages with a precise summary — the reader will see
this immediately before producing the next agent turn, so the
window's contents drive the imminent decision.

## What to PRESERVE VERBATIM
- Specific numeric values, attempt numbers (e.g. "attempt 003"),
  parameter names and their values.
- The LAST decision the conversation reached.
- The LAST reported error / failure / unresolved issue.
- Any unresolved tool-call result that the next turn must act on.
- The most recent user / orchestrator instruction (it almost
  certainly drives the next reply).

## What to CONDENSE (but do NOT drop)
- Handshakes, restated instructions, courteous boilerplate.
- Tool-call ARGUMENT echoes that have already been answered.
- Repeated framing the agent has already acknowledged.

## What you may DROP
- Restated old context that the coarse summary already covered.
- Polite acknowledgements with no informational content.

## Output Format
Return a numbered list of concise messages preserving chronological
order.  Each entry should state:
  <role>: <condensed content>

Be MORE PRECISE than a coarse summary: when in doubt about whether
to keep a specific value or attempt id, KEEP IT.
"""

# Tier 3 — ultra-compact super-summary.  Fires only when Tiers 1+2
# together still left the history above threshold.  Input is the
# concatenation of the two prior summaries (coarse + fine).  Output
# is ONE merged summary, terse, keeping only the absolute essentials.
ULTRA_COMPACT_SUMMARY_PROMPT = """\
You are the Context Pruner for a propeller design configurator system.

## Your Role (TIER 3 — ultra-compact super-summary)
You are being called as a THIRD AND FINAL PASS.  Two prior summaries
of the same conversation have already condensed it once at a coarse
level and once at a fine level.  Both together STILL exceeded the
agent's context budget.  Your input is those two summaries
concatenated.  Produce ONE merged ultra-compact summary that
replaces both.

## What to KEEP (and ONLY these)
1. Current design state — latest parameter set, latest mesh /
   render, latest assessment.
2. The current task or pending question that the next agent turn
   must answer.
3. The single most-critical decision made during the session.
4. The single most-recent unresolved issue or error.

## What to DROP
Everything else.  This includes earlier design attempts, prior
errors that have been resolved, intermediate decisions that have
been superseded, and any narrative or framing.

## Output Format
Terse paragraphs or a short numbered list.  The reader has very
little context budget left — this summary must be brief but
self-contained: someone reading only your output should still be
able to make the next correct agent decision for the current task.
"""


# Public alias retained for any external caller that imported the
# previous single-prompt name.  Equivalent to the coarse prompt.
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
        return response.content
