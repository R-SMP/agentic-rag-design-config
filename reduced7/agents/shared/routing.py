"""Reduced-variant routing block.

FORKED FROM: agents/shared/routing.py @ e31acc0
FORKS:       routing_instructions()  — only this function
IMPORTS UNCHANGED: natural_pipeline, _authorisation_sources,
                   _load_routing_fragment, _PIPELINE_BY_TOPOLOGY

Only ``routing_instructions`` is re-implemented, because only its TEXT differs.
``_authorisation_sources`` in particular MUST NOT be copied: it drops the
Planner from the grantor list when the topology is not 7, and a stale duplicate
would name an agent that does not exist in the 5- and 3-agent systems (F61).

WHAT DIFFERS FROM THE ORIGINAL — one change, see F59:

The original guards only the POSITION line on ``prev_agent`` (origin lines
190-196) and then appends the "How to decide where to route" block
unconditionally, including "route to the previous agent with a clear
clarification request (CLARIFY)".  For an agent with ``prev_agent=None`` that
bullet points at nobody, so every first-agent fragment has to carry a paragraph
patching it afterwards — see
``agents/shared/prompt_fragments/routing_user_input_inspector_uii_first.md``,
whose closing paragraph exists solely to say "anything that would otherwise be a
'back' routes to the Orchestrator instead".

This is NOT a contradiction in the original: "previous agent" legitimately means
*whoever handed you this work*, and a first-in-pipeline agent still has a
caller.  The defect is that the generator already knows ``prev_agent is None``
and could say so itself instead of making each fragment correct it.

So here the CLARIFY bullet names its own target, defining "previous" as the
sender rather than a pipeline position.  The fragment's patch paragraph then
becomes redundant, which is what makes the proposal's UII-44 cut safe.
"""

from agents.shared import topology as _topology
from agents.shared.routing import (  # noqa: F401  (re-exported for callers)
    _authorisation_sources,
    _load_routing_fragment,
    natural_pipeline,
)


def routing_instructions(
    agent_name: str,
    next_agent: str | None,
    prev_agent: str | None,
    fragment_name: str,
) -> str:
    """Build the routing section for an agent's system prompt.

    Same contract and same call signature as the original — callers are
    unchanged; ``agents/shared/prompts.py`` selects between the two.
    """
    hub = _topology.hub_display()

    lines: list[str] = [
        "## Routing",
        "",
        "You are one agent in a decentralised pipeline.  The natural "
        "flow is:",
        f"  {natural_pipeline()}",
        "",
        f"Your position: **{agent_name}**.",
    ]
    if next_agent:
        lines.append(f"- Your natural next in line is: **{next_agent}**.")
    else:
        lines.append(
            "- You are the last agent in the natural flow; completing "
            f"normally means handing control back to the {hub}."
        )
    if prev_agent:
        lines.append(f"- Your natural previous in line is: **{prev_agent}**.")
    else:
        lines.append(
            "- You are the first agent in the natural flow; if you need "
            f"to go 'back', that means handing control to the {hub}."
        )

    # THE ONE CHANGE (F59).  "Previous" means whoever handed you this work, so
    # the bullet names its own target instead of leaving the per-agent fragment
    # to patch it.  A first-in-pipeline agent still has a caller — it is the
    # hub — so CLARIFY stays available to it rather than pointing at nobody.
    if prev_agent:
        clarify_target = f"normally the **{prev_agent}**"
    else:
        clarify_target = f"for you that is the {hub}"

    lines += [
        "",
        "### How to decide where to route",
        f"- If the {hub}'s instruction in your incoming message told "
        "you to *continue the pipeline* (explicitly or by default, since "
        "no instruction to report back means continue), and your own "
        "work succeeded, route FORWARD to the next agent.",
        f"- If the {hub}'s instruction told you to *report back* or "
        f"to *do X and return*, route to the {hub} once your work "
        "is done.",
        "- If you cannot do your job because the incoming hand-off is "
        "ambiguous, missing data, or contains an error the sender can fix, "
        "route back to the agent that handed you this work — "
        f"{clarify_target} — with a clear clarification request (CLARIFY).",
        "- If something is fundamentally wrong and no agent in the chain "
        f"can fix it, route to the {hub} (ESCALATE).",
        "",
    ]

    lines.append(_load_routing_fragment(fragment_name))

    lines += [
        "",
        "### Do not loop — ESCALATE when stuck",
        "If you find yourself about to call the same tool with the same "
        "arguments you already called earlier in this turn, STOP.  Calling "
        "the same read tool twice on unchanged input, or re-thinking the "
        "same decision in a loop, will not give you new information.  "
        f"Instead, ESCALATE to the {hub} with a short note describing "
        "what is ambiguous or missing and what you would need to proceed.  "
        f"The {hub} can then re-dispatch you with new instructions, "
        "consult another agent, or ask the user.  Never silently loop.",
        "",
        f"### Permission / authorisation issues → {hub} (not "
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
        f"to the {hub}.  The previous agent in the chain typically "
        "CANNOT grant permission — " + _authorisation_sources(hub) + "  "
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
