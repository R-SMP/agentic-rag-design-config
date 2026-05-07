"""Context Pruner agent — reduces accumulated message history.

Stateless agent: receives a serialised message history and returns a
pruned version that preserves essential information while removing
redundant or superseded content.

NOTE: this agent is built but is NOT currently invoked by the
Orchestrator's dispatch loop.  Wiring it up is tracked as a known
future task (DCOI image accumulation can blow the TPM budget on long
recovery sessions).
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
