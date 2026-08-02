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
from agents.shared import topology as _topology

# ---------------------------------------------------------------------------
# Natural-pipeline string
#
# Built conditionally on the DC_INSPECTOR_ENABLED setting so the
# inter-agent flow string never names DCII when DCII is off.
# ---------------------------------------------------------------------------

# Topologies whose flow is FIXED — no PLANNER_FIRST ordering to choose and
# no separable DC Input Inspector to switch off, because both were merged
# into other agents.
#
# Note the 5-agent string includes the Receptionist while the 7-agent one
# does not.  That is not an oversight either way: the 7-agent Receptionist
# hands to the Orchestrator rather than into the chain, so the string
# starts and ends at the hub; the 5-agent Receptionist routes straight to
# the UII, so it IS the UII's natural previous and belongs in the flow.
_PIPELINE_BY_TOPOLOGY = {
    5: (
        "Receptionist → User Input Inspector → Conductor → Creator → "
        "Tool Caller → DC Output Inspector → Conductor"
    ),
}


def _authorisation_sources(hub: str) -> str:
    """Who can grant an authorisation, for the active topology.

    The ONE place in the routing boilerplate that is not a rename: the
    7-agent system has the Planner as a grantor distinct from the hub,
    but the 5-agent Conductor absorbs the Planner, so the list collapses
    from three sources to two.
    """
    if _topology.topology() == 7:
        return (
            "authorisations come from the user "
            f"(relayed by the Receptionist → {hub}), from the Planner "
            f"(relayed by the {hub}), or from the {hub} itself."
        )
    return (
        "authorisations come from the user "
        f"(relayed by the Receptionist → {hub}), or from the {hub} itself."
    )


def natural_pipeline() -> str:
    """The canonical inter-agent flow string for the active topology.

    A function rather than a constant: it depends on ``SYSTEM_TOPOLOGY``,
    which the Sessions Queue switches between runs inside one process, and
    in the 7-agent case also on ``PLANNER_FIRST`` and
    ``DC_INSPECTOR_ENABLED``.
    """
    fixed = _PIPELINE_BY_TOPOLOGY.get(_topology.topology())
    if fixed is not None:
        return fixed
    head = (
        "Orchestrator → Planner → User Input Inspector → "
        if _workflow_settings.PLANNER_FIRST
        else "Orchestrator → User Input Inspector → Planner → "
    )
    middle = (
        "DC Input Creator → DC Input Inspector → "
        if _workflow_settings.DC_INSPECTOR_ENABLED
        else "DC Input Creator → "
    )
    return head + middle + "Tool Caller → DC Output Inspector → Orchestrator"


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

    The active topology's override is preferred when one exists, so the
    5-agent chain loads ``routing_creator_5agents.md`` while a fragment
    with no topology-specific copy comes from the shared directory.
    ``_topology_override`` is imported lazily, alongside
    ``apply_flag_filters``, because ``prompts`` imports THIS module at its
    own import time — a module-level import here would be circular.
    """
    from agents.shared.prompts import _topology_override, apply_flag_filters

    # PLANNER_FIRST splits some of these fragments into a
    # ``*_planner_first.md`` / ``*_uii_first.md`` pair.  That axis exists
    # ONLY in the 7-agent system: a topology whose hub IS the planner has
    # no Planner/UII ordering to choose, so it ships ONE fragment per
    # agent and its override cannot match the branched name the caller
    # passes.  Try the exact name first — a topology CAN still branch if
    # it ever needs to — then the name with the branch suffix removed.
    candidates = [fragment_name]
    stem, suffix = Path(fragment_name).stem, Path(fragment_name).suffix
    for branch in ("_planner_first", "_uii_first"):
        if stem.endswith(branch):
            candidates.append(f"{stem[: -len(branch)]}{suffix}")
            break

    path = None
    for name in candidates:
        path = _topology_override(f"prompt_fragments/{name}")
        if path is not None:
            break
    # The shared fallback always uses the ORIGINAL name, never the
    # collapsed one, so topology 7 reads exactly what it always read.
    if path is None:
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
    # Whoever the active topology's hub is — Orchestrator (7-agent) or
    # Conductor (5-agent).  Every "route back / escalate to …" below names
    # it, so it is resolved once here rather than hard-coded per sentence.
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
        "- If you cannot do your job because the upstream message is "
        "ambiguous, missing data, or contains an error that the previous "
        "agent can fix, route to the previous agent with a clear "
        "clarification request (CLARIFY).",
        "- If something is fundamentally wrong and no agent in the chain "
        f"can fix it, route to the {hub} (ESCALATE).",
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
