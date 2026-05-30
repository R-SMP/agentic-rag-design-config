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
the older portion is fed to this Pruner's ``run()`` and replaced
with a single ``SystemMessage`` summary at the front of the new
history; the most recent ``CONTEXT_PRUNER_KEEP_LAST_MESSAGES``
messages survive verbatim, with the cut point automatically
extended forward so an ``AIMessage(tool_calls)`` is never split
from its matching ``ToolMessage``.

The agent's ORIGINAL system prompt lives in ``self.system_prompt``
(NOT in ``self.messages``) and is rebuilt fresh at every invoke,
so pruning leaves the agent's role / rules intact — the LLM sees
the original system prompt followed by the Pruner's summary
``SystemMessage``.

The Database Handler is intentionally NOT pruned: it iterates ~28
schedule entries in one save and relies on accumulated state to
ask coherent follow-ups.  All other chain agents are pruned.
"""

from langchain_core.messages import HumanMessage, SystemMessage

SYSTEM_PROMPT = """\
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


class ContextPruner:
    """Stateless agent that prunes message histories."""

    def __init__(self, llm):
        self.llm = llm

    def run(self, messages_text: str) -> str:
        response = self.llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=f"Prune the following message history:\n\n{messages_text}"
            ),
        ])
        return response.content
