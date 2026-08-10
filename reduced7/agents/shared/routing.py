"""Reduced-variant routing block.

FORKED FROM: agents/shared/routing.py
FORKS:       routing_instructions()  — only this function
IMPORTS UNCHANGED: natural_pipeline, _authorisation_sources,
                   _load_routing_fragment, _PIPELINE_BY_TOPOLOGY

The COMMIT this was forked at lives in extra_utilities/fork_manifest.json, not
here — one recorded version, checked by smoke_test_fork_drift.py.  A SHA in
this docstring as well would be a second copy to keep in sync, and the one
that goes stale is always the one nobody runs a test against.

Only ``routing_instructions`` is re-implemented, because only its TEXT differs.
``_authorisation_sources`` in particular MUST NOT be copied: it drops the
Planner from the grantor list when the topology is not 7, and a stale duplicate
would name an agent that does not exist in the 5- and 3-agent systems (F61).

WHAT DIFFERS FROM THE ORIGINAL — still exactly one change (F59).  Verified by
diffing the EMITTED text against the original for both a first-in-pipeline and a
mid-chain agent: one bullet differs, nothing else.

The original appends the "How to decide where to route" block unconditionally,
including "route to the previous agent with a clear clarification request
(CLARIFY)" — naming no target.  Here that bullet names its own, defining
"previous" as *whoever handed you this work* rather than a pipeline position.

BUT ONLY WHERE THERE IS ONE (C6, 2026-08-10).  An earlier version of this fork
also named the hub when ``prev_agent is None``.  That was the THIRD statement of
the same thing for a first agent — the position bullet a few lines above already
says "You are the first agent in the natural flow; if you need to go 'back',
that means handing control to the {hub}" under the identical condition — and it
was worded so as to CONTRADICT the agent's own routing fragment, which says
"there is no 'previous' agent in the chain for you to CLARIFY back to"
(``agents/shared/prompt_fragments/routing_user_input_inspector_uii_first.md``).
Same destination, opposite claim about whether CLARIFY applies at all.

That fragment paragraph is the SOLE authority for the first-agent case and must
not be cut.  The proposal's UII-44 assumes this fork made it redundant.  It did
not, and that cut is unsafe as written.

WHAT DEPENDS ON THIS BLOCK — read before deleting any string below.

Deleting this fork wholesale is safe: the original emits the same rules, and all
that is lost is the F59 wording.  EDITING these strings is NOT safe.  Under
PROMPT_VARIANT=reduced, ``generic_constraints_7agents_reduced.md`` deliberately
no longer states FORWARD-is-default, ESCALATE-when-blocked or permissions->hub.
That cut was sound precisely BECAUSE this block states all three to exactly the
same audience: ``<<CHAIN_ONLY>>``'s audience is identical to this function's,
since ``_NON_CHAIN_AGENTS`` (prompts.py:228-230) is precisely the set of agents
that never call it — see the four hub files, incl. the explicit comments at
conductor.py:230 and architect.py:301.  So for the reduced variant those three
rules now have exactly ONE delivery each, and it is the "How to decide where to
route" and "Permission / authorisation issues" sections below.
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
    # to patch it.
    #
    # ONLY when there IS a previous agent.  A first-in-pipeline agent is
    # already told where a "back" goes twice — by the bullet above (same
    # ``else`` branch as this one) and by its own routing fragment.  Naming
    # the hub a third time here produced a statement that CONTRADICTED the
    # fragment: this said "route back ... for you that is the Orchestrator",
    # while e.g. routing_user_input_inspector_uii_first.md says "there is no
    # 'previous' agent in the chain for you to CLARIFY back to".  Same
    # destination, opposite claim about whether CLARIFY applies at all.
    if prev_agent:
        clarify_clause = f" — normally the **{prev_agent}** — "
    else:
        clarify_clause = " "

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
        "route back to the agent that handed you this work"
        f"{clarify_clause}with a clear clarification request (CLARIFY).",
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
