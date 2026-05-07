"""Routing-related prompt fragments shared across agent templates.

Two pieces live here because both are PROMPT content (text the LLM
reads), not runtime mechanism (which lives in
``agents/shared/routing_tools.py``):

- ``NATURAL_PIPELINE`` — the canonical inter-agent flow string,
  embedded into the Orchestrator's system prompt and into every
  agent's per-routing block.
- ``routing_instructions(...)`` — builds the per-agent ``## Routing``
  section (FORWARD / CLARIFY / ESCALATE rules + the per-agent
  "Available routing tools" subsection) inserted into each chain
  agent's system prompt at wiring time.  The "Available routing
  tools" subsection is itself authored as a per-agent markdown
  fragment under ``agents/shared/prompt_fragments/`` and loaded here
  rather than constructed inline — this keeps the per-agent call
  roster in plain markdown that's easy to inspect and edit.
"""

from pathlib import Path

from workflow_settings import settings as _workflow_settings

# ---------------------------------------------------------------------------
# Natural-pipeline string
#
# Built conditionally on the DC_INSPECTOR_ENABLED setting so the
# inter-agent flow string never names DCII when DCII is off.
# ---------------------------------------------------------------------------

_HEAD = (
    "Orchestrator → Planner → User Input Inspector → " if _workflow_settings.PLANNER_FIRST
    else "Orchestrator → User Input Inspector → Planner → "
)
_MIDDLE = (
    "DC Input Creator → DC Input Inspector → " if _workflow_settings.DC_INSPECTOR_ENABLED
    else "DC Input Creator → "
)
NATURAL_PIPELINE = _HEAD + _MIDDLE + "Tool Caller → DC Output Inspector → Orchestrator"


# ---------------------------------------------------------------------------
# Per-agent routing-fragment loading
# ---------------------------------------------------------------------------

_FRAGMENTS_DIR = Path(__file__).resolve().parent / "prompt_fragments"


def _load_routing_fragment(fragment_name: str) -> str:
    """Load a per-agent ``routing_<agent>.md`` fragment from disk.

    The file is the source of truth for the agent's "Available routing
    tools" subsection — the list of bound ``call_<agent>`` tools and
    their FORWARD / CLARIFY / ESCALATE semantics.

    DCII conditional regions (``<<DCII_ONLY>>`` / ``<<DCII_OFF>>``)
    and PLANNER_FIRST conditional regions (``<<PF_ON>>`` /
    ``<<PF_OFF>>``) are resolved here.
    """
    from agents.shared.prompts import apply_flag_filters

    path = _FRAGMENTS_DIR / fragment_name
    return apply_flag_filters(path.read_text(encoding="utf-8").rstrip())


# ---------------------------------------------------------------------------
# Routing-section builder
# ---------------------------------------------------------------------------

def routing_instructions(
    agent_name: str,
    next_agent: str | None,
    prev_agent: str | None,
    fragment_name: str,
) -> str:
    """Build the routing section for an agent's system prompt.

    The "Available routing tools" subsection is loaded from the
    per-agent markdown fragment named ``fragment_name`` (under
    ``agents/shared/prompt_fragments/``).  All other subsections —
    natural-flow position, decide-where-to-route rules, do-not-loop
    guidance, permission-question routing rule, "routing is a tool
    call" mandate — are shared boilerplate built inline below.
    """
    lines: list[str] = [
        "## Routing",
        "",
        "You are one agent in a decentralised pipeline.  The natural "
        "flow is:",
        f"  {NATURAL_PIPELINE}",
        "",
        f"Your position: **{agent_name}**.",
    ]
    if next_agent:
        lines.append(f"- Your natural next in line is: **{next_agent}**.")
    else:
        lines.append(
            "- You are the last agent in the natural flow; completing "
            "normally means handing control back to the Orchestrator."
        )
    if prev_agent:
        lines.append(f"- Your natural previous in line is: **{prev_agent}**.")
    else:
        lines.append(
            "- You are the first agent in the natural flow; if you need "
            "to go 'back', that means handing control to the Orchestrator."
        )

    lines += [
        "",
        "### How to decide where to route",
        "- If the Orchestrator's instruction in your incoming message told "
        "you to *continue the pipeline* (explicitly or by default, since "
        "no instruction to report back means continue), and your own "
        "work succeeded, route FORWARD to the next agent.",
        "- If the Orchestrator's instruction told you to *report back* or "
        "to *do X and return*, route to the Orchestrator once your work "
        "is done.",
        "- If you cannot do your job because the upstream message is "
        "ambiguous, missing data, or contains an error that the previous "
        "agent can fix, route to the previous agent with a clear "
        "clarification request (CLARIFY).",
        "- If something is fundamentally wrong and no agent in the chain "
        "can fix it, route to the Orchestrator (ESCALATE).",
        "",
    ]

    # The per-agent "Available routing tools" subsection comes from the
    # markdown fragment.  The fragment supplies its own ``###`` heading.
    lines.append(_load_routing_fragment(fragment_name))

    lines += [
        "",
        "### Do not loop — ESCALATE when stuck",
        "If you find yourself about to call the same tool with the same "
        "arguments you already called earlier in this turn, STOP.  Calling "
        "the same read tool twice on unchanged input, or re-thinking the "
        "same decision in a loop, will not give you new information.  "
        "Instead, ESCALATE to the Orchestrator with a short note describing "
        "what is ambiguous or missing and what you would need to proceed.  "
        "The Orchestrator can then re-dispatch you with new instructions, "
        "consult another agent, or ask the user.  Never silently loop.",
        "",
        "### Permission / authorisation issues → Orchestrator (not "
        "the previous agent)",
        "If a rule in your system prompt blocks an action unless some "
        "authorisation is present, READ THE INCOMING HAND-OFF (and any "
        "upstream file the hand-off points to, e.g. extracted_inputs.txt) "
        "ONCE MORE before escalating.  If the hand-off already names an "
        "authorisation that plausibly covers the action — even if the "
        "wording differs from a template you expected — act on it.  Do "
        "NOT bounce back to the previous agent in the chain for a ritual "
        "re-confirmation of something the hand-off already carries; that "
        "is a wasted round-trip.",
        "",
        "When an authorisation is truly missing or ambiguous, ESCALATE "
        "to the Orchestrator.  The previous agent in the chain typically "
        "CANNOT grant permission — authorisations come from the user "
        "(relayed by the Receptionist → Orchestrator), from the Planner "
        "(relayed by the Orchestrator), or from the Orchestrator itself.  "
        "CLARIFY back to the previous agent is appropriate for data / "
        "wording / format issues the previous agent can actually fix, "
        "NOT for permission questions.",
        "",
        "### Routing is a tool call — MANDATORY",
        "Every response that ends your turn MUST invoke exactly one of "
        "the routing tools listed above.  The tool's ``message`` argument "
        "IS the complete hand-off text the recipient will see — there "
        "is NO separate audit block to emit.  Do NOT write a "
        "``---ROUTING---`` / ``---MESSAGE---`` / ``---END---`` template; "
        "that format has been retired.  The tool call is the routing "
        "decision; its ``message`` argument is the hand-off.",
        "",
        "Write the ``message`` argument as free-form prose: no fixed "
        "template, no enumerated option menus, no placeholder phrasings.  "
        "Include everything the recipient genuinely needs (paths the "
        "recipient's tools require, context about what changed and why, "
        "authorship of any non-user-authored values) and nothing they do "
        "not.  Your verbose work product stays in your own history and "
        "(where applicable) on disk — do not duplicate it inside the "
        "``message`` argument.",
        "",
        "Do NOT describe or announce which tool you intend to call.  Do "
        "NOT wait for the next turn to invoke it.  Do NOT substitute the "
        "tool call with free-form prose that says \"routing to X\".  In "
        "the same response where you finish your work, invoke the tool.  "
        "Any ordinary response text you produce is for your own brief "
        "reasoning only — it is NOT delivered to the recipient; only the "
        "tool's ``message`` argument is.  Keep that reasoning terse "
        "(one or two lines is plenty).",
    ]
    return "\n".join(lines)
