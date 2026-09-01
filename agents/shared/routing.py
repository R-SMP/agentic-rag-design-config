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
# Both strings start and end at the hub, because in both topologies the
# Receptionist hands to the hub rather than into the chain.  The 5-agent
# string is the 7-agent PF_OFF one with the Orchestrator replaced by the
# Planner and the two removed agents dropped; the Planner appears twice
# because it is both the origin and the terminus there.
_PIPELINE_BY_TOPOLOGY = {
    5: (
        "Planner → User Input Inspector → Planner → DC Input Creator → "
        "Tool Caller → DC Output Inspector → Planner"
    ),
    # 3-agent (strip-down).  Starts and ends at the hub, like the
    # 7-agent string and unlike the 5-agent one: there is no UII here,
    # so the Receptionist hands to the HUB rather than into the chain.
    3: "Architect → Designer → DC Output Inspector → Architect",
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

# Which routing sections each agent's prompt gets.  The 2026-08-22 prompt
# reduction (extra_utilities/prompt_reduction_4agents_changes.md §A2) cut
# most of the shared boilerplate for the Planner and the UII; every agent
# NOT listed here keeps the full historic set, byte-identical.
#
# ⚠ Keyed by the ``agent_name`` DISPLAY string, which is NOT unique across
# configurations: the 5-agent topology builds its UII from the same class
# with the same display name.  The reduction is therefore gated by
# :func:`_reduced_sections_apply` to the ONE configuration it was reviewed
# in — 7-agent, UII-first.  That gate is load-bearing, not defensive: the
# text these sections carry was MOVED into
# ``routing_user_input_inspector_uii_first.md``, and no other
# configuration's fragment absorbed it, so suppressing the sections
# anywhere else deletes rules with nothing standing in for them.
#
# Section names:
#   header         ``## Routing`` + natural-flow string + position bullets
#   decide         ``### How to decide where to route`` (all four bullets)
#   fragment       the per-agent routing-tool markdown fragment (round 2
#                  folded the decision bullets into its tool bullets and
#                  dropped the "Available routing tools" heading)
#   loop           ``### Do not loop — ESCALATE when stuck``
#   permission     ``### Permission / authorisation issues → hub``
#   mandatory      ``### Routing is a tool call — MANDATORY`` (all three
#                  paragraphs)
#   mandatory_tail just the "Do NOT describe or announce…" paragraph,
#                  without the heading and without the closing
#                  keep-it-terse sentence
_ROUTING_SECTIONS_DEFAULT: tuple[str, ...] = (
    "header", "decide", "fragment", "loop", "permission", "mandatory",
)
_ROUTING_SECTIONS_BY_AGENT: dict[str, tuple[str, ...]] = {
    # The Planner carries the roster + pipeline flow at the top of its own
    # prompt; its fragment supplies the tool list, and only the
    # don't-announce paragraph survives from the mandate section.
    "Planner": ("fragment", "mandatory_tail"),
    # The UII's fragment (routing_user_input_inspector_uii_first.md)
    # absorbed the surviving CLARIFY sentence, the forwarding rules and the
    # mandate remains, so the fragment IS the whole routing section.
    "User Input Inspector": ("fragment",),
    # Round 2 (prompt_reduction_3agents_changes.md §A2) folded the four
    # decision bullets into the tool bullets they describe, inside each of
    # these fragments, and dropped every remaining sub-section.
    "DC Input Creator": ("fragment", "mandatory_tail"),
    "DC Input Inspector": ("fragment", "mandatory_tail"),
    "Tool Caller": ("fragment", "mandatory_tail"),
    "DC Output Inspector": ("fragment", "mandatory_tail"),
}

# Agents whose reduction is safe ONLY under PLANNER_FIRST=False.  Round 1
# moved their suppressed text into the ``*_uii_first`` fragments alone, so
# the ``*_planner_first`` variants would lose rules with nothing standing in
# for them.  Round 2 folded the decision bullets into BOTH DC Input Creator
# variants and into the single DCII / TC / DCOI fragments, so those four are
# safe under either ordering.
_PF_SENSITIVE_AGENTS = frozenset({"Planner", "User Input Inspector"})

# The closing paragraph of the mandate section, split so the reduced
# emission ("mandatory_tail") and the full section stay byte-identical to
# what they always said.
_MANDATORY_TAIL = (
    "Do NOT describe or announce which tool you intend to call.  Do "
    "NOT wait for the next turn to invoke it.  Do NOT substitute the "
    "tool call with free-form prose that says \"routing to X\".  In "
    "the same response where you finish your work, invoke the tool.  "
    "Any ordinary response text you produce is for your own brief "
    "reasoning only — it is NOT delivered to the recipient; only the "
    "tool's ``message`` argument is."
)


# The reduced path's single mandate paragraph.  Until 2026-08-25 this was
# TWO adjacent paragraphs -- a "_MANDATORY_LINE_REDUCED" restored on
# 2026-08-23 plus _MANDATORY_TAIL -- which said the same thing twice, on
# top of the generic constraints' "DON'T communicate in plain prose"
# bullet.  The ID252-262 runs settled it: all three routing failures
# (254 DCII+DCOI, 261 DCII, all gpt-5.4-mini) happened to agents carrying
# the mandate THREE times, and the ROUTING_RETRY_ENABLED nudge is what
# recovered every one.  Merged to one statement; the generic DON'T stays.
# The full-mandate path keeps _MANDATORY_TAIL unchanged.
_MANDATORY_TAIL_REDUCED = (
    "Every turn MUST end by invoking exactly one of the routing tools "
    "above, in the same response where you finish your work.  Do NOT "
    "announce which tool you intend to call, and do NOT substitute "
    "prose saying \"routing to X\".  Ordinary response text is your own "
    "brief reasoning; only the tool's ``message`` argument reaches the "
    "recipient."
)


def _sections_for(agent_name: str) -> tuple[str, ...]:
    """Which routing sections *agent_name* gets in the ACTIVE configuration.

    The reduction applies only to the 7-agent, UII-first system — the one
    the prompts were reviewed in, and the only one whose per-agent routing
    fragments were rewritten to carry the text the suppressed sections
    used to state.  Every other topology, and the PLANNER_FIRST=True
    ordering (which selects a different, un-rewritten fragment), keeps the
    full historic set.

    ⚠ PLANNER_FIRST is read from ``prompts``, NOT from ``workflow_settings``
    — deliberately.  ``prompts.PLANNER_FIRST`` is captured at import, and it
    is the value each agent's ``set_routing_tools`` uses to pick WHICH
    fragment to load.  Reading the settings module fresh here would let the
    two disagree after ``web_app._build_session`` reloads
    ``workflow_settings`` in place: the agent would load a
    ``*_planner_first.md`` fragment (which never absorbed the moved text)
    while this gate suppressed the sections, deleting rules with nothing
    standing in for them.  Same source = they cannot disagree.
    """
    from agents.shared.prompts import PLANNER_FIRST

    topo = _topology.topology()
    if topo not in (7, 5):
        return _ROUTING_SECTIONS_DEFAULT
    # PLANNER_FIRST is a 7-agent-only axis.  Topology 5 always ships the
    # branch-COLLAPSED fragments, which carry the uii_first text -- i.e.
    # the text that absorbed what the reduction removed -- so the
    # PF gate must not fire there.
    if topo == 7 and PLANNER_FIRST and agent_name in _PF_SENSITIVE_AGENTS:
        return _ROUTING_SECTIONS_DEFAULT
    return _ROUTING_SECTIONS_BY_AGENT.get(
        agent_name, _ROUTING_SECTIONS_DEFAULT,
    )


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
    call" mandate — are shared boilerplate built inline below, emitted
    per the agent's allow-list in ``_ROUTING_SECTIONS_BY_AGENT``.
    """
    # Whoever the active topology's hub is — Orchestrator (7-agent) or
    # Conductor (5-agent).  Every "route back / escalate to …" below names
    # it, so it is resolved once here rather than hard-coded per sentence.
    hub = _topology.hub_display()
    sections = _sections_for(agent_name)

    lines: list[str] = []

    if "header" in sections:
        lines += [
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
            lines.append(
                f"- Your natural previous in line is: **{prev_agent}**."
            )
        else:
            lines.append(
                "- You are the first agent in the natural flow; if you need "
                f"to go 'back', that means handing control to the {hub}."
            )

    # "Previous" means whoever handed you this work, so the CLARIFY bullet
    # below names its own target instead of leaving the per-agent fragment
    # to patch it (F84).
    #
    # ONLY when there IS a previous agent.  A first-in-pipeline agent is
    # already told where a "back" goes by the position bullet above (same
    # ``else`` branch), and naming the hub again here once produced a
    # statement that CONTRADICTED the agent's own routing fragment (F84):
    # this said "route back ... for you that is the Orchestrator" while the
    # fragment said "there is no 'previous' agent in the chain for you to
    # CLARIFY back to" — same destination, opposite claim about whether
    # CLARIFY applies at all.  Leaving the clause empty keeps the fragment
    # the sole authority for the first-agent case.  (The 2026-08-22 prompt
    # reduction cut that fragment sentence for the 7-agent UII, which now
    # emits the CLARIFY rule from the fragment itself; the empty clause is
    # still what keeps the two from contradicting each other.)
    if prev_agent:
        clarify_clause = f" — normally the **{prev_agent}** — "
    else:
        clarify_clause = " "

    if "decide" in sections:
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

    if "fragment" in sections:
        # The per-agent "Available routing tools" subsection comes from the
        # markdown fragment.  The fragment supplies its own ``###`` heading.
        if "header" not in sections:
            # The reduction drops the header block, but the fragment's
            # ``###`` subsections still need a ``##`` parent — without one
            # they render as part of whichever section the prompt happened
            # to end on (the Planner's "Attempt folders", the UII's "Hard
            # constraints — tool-specific").  Emit the bare title only: what
            # the markup removed as duplicated is the flow string and the
            # position bullets, now carried at the top of those prompts.
            # Round 2 §A2 titles the merged section ``## ROUTING``.
            lines += ["## ROUTING", ""]
        lines.append(_load_routing_fragment(fragment_name))

    if "loop" in sections:
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
        ]

    if "permission" in sections:
        lines += [
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
        ]

    if "mandatory" in sections:
        lines += [
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
            _MANDATORY_TAIL + "  Keep that reasoning terse "
            "(one or two lines is plenty).",
        ]
    elif "mandatory_tail" in sections:
        lines += ["", _MANDATORY_TAIL_REDUCED]

    return "\n".join(lines)
