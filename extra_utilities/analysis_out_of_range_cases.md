# Out-of-range values — full case matrix + coherence audit

> ## ✅ FIXES APPLIED 2026-08-01 (owner-approved, one at a time)
>
> The matrix below describes the state BEFORE these fixes.  Eight landed:
>
> 1. **Tool Caller now range-checks before generating** — both topologies.
>    `$parameter_list` added (+396 tok); refuse-and-route-back, never clip.
>    Owner's call: ranges only, not hard blockers; and *"if implemented then it
>    must also be implemented in the original 7-agent system for consistency"*.
>    **This restores the 5-agent's independent numeric check** (lost when
>    DCIC+DCII merged) and closes all three previously-unchecked paths:
>    precision refine rounds, `DCII_OFF` sessions, and a double miss.
> 2. **[U-a] resolved in the live DCIC** — the three-way collision (hard FAIL
>    vs write-verbatim vs restore-the-user's-value) now has an explicit
>    resolution, ported back from the Creator.  Plus the "What you CAN fix"
>    list un-scoped and its write mechanics corrected: the owner spotted that
>    *"call `write_parameters` again"* would be **REFUSED** post-write
>    (append-only).  Code-verified: validation runs before `write_text`, so a
>    REJECTED call wrote no file and may be re-called on the same folder; a
>    SUCCEEDED write closes the folder and a later correction needs a fresh
>    `new_attempt`.
> 3. **Planner escalation now carries the numbers** — *"Do NOT paste their
>    current values (the Orchestrator / Receptionist splice those)"* was false;
>    neither does.  The permission question could reach the user with no
>    parameter, value or range in it.
> 4. **Planner's DCII block corrected** — *"the only gate"* was triply false,
>    and *"do not skip it"* contradicted the DCIC's tight precision loop.  Now
>    scoped to Planner-authored Sequences, with the real justification (the
>    only INDEPENDENT audit) and the precision-loop exception stated.
> 5. **[U-g] the UII now flags out-of-range values** on the QUANTITATIVE
>    INPUTS line, with a rule-D carve-out.  Scoped to unit-matching values —
>    a real-world quantity needing conversion is not the UII's to judge (G6).
>    This is the ONLY guard on an extraction-only request, where DCIC / DCII /
>    TC / DCOI never run.
> 6. **[U-c] disclosure** — the Planner/Conductor now carries any user value
>    not honoured into its APPROVE hand-off, and the Receptionist relays it.
>    Modelled on the existing precision-fidelity honesty rule.  Closes G2, G3,
>    G5 and G6 at once, not just the out-of-range case.
> 7. **Stale cross-agent attributions** — the DCOI no longer credits the DCII
>    (which may not run); it names the terminal check instead.  Roster drift
>    fixed: the Creator validates the draft BEFORE writing, not "what it wrote".
> 8. **[U-d] G7 deadlock closed** — a "keep fixed" directive whose value is
>    itself out of range no longer orders a restore; it escalates so the
>    Planner/Conductor can revise the directive.
>
> **Still open, deliberately:** **[U-b]** (how far into range an authorised
> move should land — left as agent discretion; the goal governs for soft
> targets and the DCII already checks "as needed" vs "freely" overshoot), and
> **G8 / G9** — the no-ask-back + degrade feature, specified in
> `design_no_ask_back_and_range_degrade.md` and not yet built.
>
> **Not verified:** none of this is import-tested (py3.8 worktree), and no
> live run has exercised it.

**Produced 2026-08-01** by extracting every range-related rule from all 8 live
7-agent prompts, all 6 5-agent drafts, the 5-agent fragments, `$value_states`,
`dc_input_creator.py` and `web/app.js`.  Every cell is grounded in quoted
prompt text; cells the prompts do NOT define are marked **UNDEFINED** rather
than guessed.

## Three facts established from CODE, not prompts

1. **`write_parameters` validates key-set + numeric-ness only** — no range
   comparison (`agents/dc_input_creator/dc_input_creator.py`).
2. **No range table exists in executable code.**  The generator has no guard.
3. **The UI cannot produce an out-of-range value.**  `web/app.js` renders every
   parameter as `<input type="range">` with `min`/`max` from the spec table, so
   a UI-pinned value is bounded by construction.  **The only routes for an
   out-of-range user value are free-text chat and images / sketches.**

⟹ Range enforcement is **entirely prose-level**.  Nothing mechanical backs it.

## Structurally impossible cases (not padding the matrix)

| Combination | Why it is a null set |
|---|---|
| USER-supplied + FREE | FREE is *defined* as absent from QUANTITATIVE INPUTS; a user number is LOCKED or SOFT TARGET. |
| SOFT TARGET + no authorisation | "the marker itself IS the authorisation to move the value (within range)". |
| UI-pinned + out of range | Unreachable — slider bounded (fact 3). |
| AGENT-chosen + LOCKED | **NOT null** — a directive "to keep it fixed LOCKS it (even if the user did not)". That is case **G7**. |

## PART 1 — GEOMETRY-GENERATING requests

| # | Case | What happens | Ends | User asked? |
|---|---|---|---|---|
| **G1** | USER / LOCKED / no auth | Receptionist forwards (no check, never clips); UII records verbatim; Planner untouched. **DCIC = CONTRADICTORY (see U-a).** DCII: hard FAIL, "MUST NOT APPROVE for any reason, including 'it is what the user asked for'" → ESCALATE | User asked to revise their own number | **YES** |
| **G2** | USER / LOCKED / auth exists | DCIC moves it, then range-validates; DCII re-validates ("authorisation never bypasses [min; max]") | In-range substitute | **NO** — and nothing requires telling the user (U-c) |
| **G3** | USER / SOFT TARGET | "Set a SOFT TARGET to whatever its goal calls for (within range)… never escalate to change one" → silently re-set in range; DCII must NOT flag it; DCOI judges it against the GOAL, never the number | In-range value | **NO**, no disclosure |
| **G4** | AGENT-chosen / FREE | DCIC catches it in its own draft check and fixes in-draft; if it slips, DCII → REVISE back | Fixed internally | NO |
| **G5** | AGENT-seeded from `SUGGESTED SECTION SHAPES` | **Silently CLAMPED** — the only clamp instruction in the system, scoped to non-user values | Clamped | NO |
| **G6** | USER real-world quantity whose CONVERSION lands out of range | UII cannot detect it ("conversion is the DCIC's job"); DCIC: "verify the result is in range; if not, revise the anchor or escalate" | Usually fixed by moving a *different* parameter | Only if impossible |
| **G7** | AGENT-chosen value frozen by a "keep fixed" directive | Self-correcting violates the directive; keeping it violates the range. The user carve-out is scoped to values "the USER literally provided", so it does not apply | **UNDEFINED (U-d)** — only exit is the accidental "CLARIFYed once and it persists" | Eventually, by accident |
| **G8** | G1, then the user REFUSES / re-states the number | Unchanged → hard FAIL → ESCALATE → asks again | **UNDEFINED (U-e) — infinite ask-loop.** No cap, no terminal, no degrade | Repeatedly |
| **G9** | User says "don't ask me back" + out-of-range LOCKED | No suppression rule in ANY agent | **UNDEFINED (U-f)** — falls back to G1; the system asks anyway, violating the directive | Yes (wrongly) |
| **G10** | Any out-of-range value on a PRECISION REFINE round (7-agent only) | DCIC forwards straight to the Tool Caller, **skipping the DCII**, on most rounds; its own check is then "the only parameter validation there is" | Single check | NO |
| **G11** | Any case with `<<DCII_OFF>>` | DCIC is sole checker; the hub's roster names no validator | Single check | Per G1/G4 |
| **G12** | An out-of-range value REACHES the Tool Caller | TC has **zero** range vocabulary; code does not check. If the generator hard-fails → ESCALATE; **if it renders anyway → the DCOI declines to re-check parameters** | **Silent pass-through to the deliverable is possible** | **NO** |

## PART 2 — EXTRACTION-ONLY requests

| # | Case | Ends | User asked? |
|---|---|---|---|
| **E1** | USER / LOCKED / out of range | Receptionist labels it extraction-only → UII extracts verbatim → Planner: "the extraction IS the deliverable… Do NOT hand off to the DCIC". **DCIC/DCII/TC/DCOI never run. The number is reported back never compared to its range, never flagged** | **NO — and not warned (U-g)** |
| **E2** | USER / SOFT TARGET | Identical | NO |
| **E3** | Value on an **unrecognised parameter NAME** | Receptionist replies directly and does NOT forward | **YES** |
| **E4** | Extraction-only turn, then "now build it" | Re-enters as G1; no re-validation at the transition (U-h) | Per G1 |

> **The sharpest asymmetry in the system:** a bad parameter **name** stops the
> request at the door; a bad parameter **value** never does.

## PART 3 — UNDEFINED cells

- **[U-a] G1 in the 7-agent DCIC.**  Three rules fire and point three ways:
  "strictly outside its range is a hard FAIL"; "Write a LOCKED value
  **verbatim** — do NOT round, adjust, re-scale"; "If nothing did, **restore
  the user's value**".  Nothing sequences them, and the DCIC's "What you CAN
  fix" list scopes out-of-range repair to *"a value **you generated**"*.
  **The 5-agent Creator is the only place in either topology where this is
  decided.**
- **[U-b]** How far into range an authorised move should land — undefined.
- **[U-c]** Disclosure after a substitution — no rule in EITHER topology
  requires telling the user their number was not honoured (design doc **D8**).
- **[U-d] G7**, **[U-e] G8** (design doc **D7**), **[U-f] G9** (**D1–D3**).
- **[U-g]** Extraction-only output is never annotated "out of range".
- **[U-h]** No re-validation when extraction-only becomes generation.

## PART 4 — Coherence WITHIN the 7-agent system

1. **Two agents claim the same authority; one is wrong.**  Planner: the DCII
   *"is the only gate that validates parameter values before mesh
   generation"*.  DCIC: *"You are… the **first line of defence**"* — an
   unconditional gate, outside any `<<DCII_ONLY>>` tag.  The Planner's claim is
   false and would mislead any recovery plan built on it.
2. **Direct contradiction on a routing edge.**  Planner: *"Do not skip it."*
   DCIC: *"forward MOST refine rounds STRAIGHT to the Tool Caller — skipping
   the DCII."*  The DCIC wins at runtime; the Planner has no idea.
3. **An agent relies on something no agent does.**  Planner: *"Do NOT paste
   their current values (the Orchestrator / Receptionist splice those from the
   extraction)."*  Neither does — the Receptionist *recalls*, it cannot read
   the extraction.  ⟹ **the one question only the user can answer ("your X is
   outside [lo; hi], may we move it?") can reach them with no numbers in it.**
4. **The Receptionist's model of downstream validation is one-third wrong** —
   it names "UII / DCIC / DCII" as validators; the UII validates nothing.
5. **The DCII hands the DCIC a job its routing list does not cover** (scoped to
   self-generated values).
6. **A value CAN reach the generator unchecked — three paths:** precision
   refine rounds; `<<DCII_OFF>>` sessions; a DCIC slip the DCII misses.  **No
   backstop of any kind** behind them (facts 1–2).  The DCII's justification —
   *"the generator fails… on out-of-range inputs"* — is an assumption with
   nothing enforcing it.
7. **The last observer assumes an agent that may not have run.**  DCOI: *"You
   do NOT re-check parameters (that's the DCII)"* — false on every precision
   refine round and every DCII-off session, exactly when it is the only
   observer left.
8. **Nobody owns disclosure** (see U-c).

**What IS coherent:** substitution authority is given to exactly one agent
(the DCIC/Creator) and every other agent is barred from it — Receptionist
"never silently clip", Planner never supplies numbers, DCOI owns no values,
Tool Caller may not tweak.  The three-state model is applied consistently by
the four agents that receive `$value_states`.

## PART 5 — Coherence ACROSS topologies

**Headline: the 7-agent range-checks TWICE, deliberately, with an explicit
anti-delegation warning on each side.  The 5-agent checks ONCE — by the agent
that authored the numbers — and both warnings were deleted rather than
answered.**

- DCIC: *"The DCII independently re-checks EVERYTHING you just checked… That
  redundancy is deliberate: **you can make a mistake reviewing your own
  work**."*
- DCII: *"That is NOT a reason to relax yours… **exactly as if no prior check
  had happened**."*
- Grep across all 5-agent drafts + fragments for those warnings: **zero hits.**
- **Independence is also lost at the DCOI override**: 7-agent it overrides *"a
  DCII APPROVE"* (one agent overruling another); 5-agent *"a Creator PASS"*.
  ⟹ **the 5-agent has ZERO independent numeric validation of
  `parameters.json`.**  Inherent to the merge — but the risk paragraph should
  have been replaced by a compensating rule, and was not.

| # | Difference | Verdict |
|---|---|---|
| D-1 | **G1 becomes decidable** — the Creator has the out-of-range routing rule the DCIC lacks | **Deliberate — the merge accidentally FIXED [U-a]** |
| D-2 | Escalation now carries the numbers ("Include their current values — the Receptionist cannot read it") | **Deliberate fix of finding 3** |
| D-3 | The DCII-skip edge is gone; the Creator always range-checks | **Deliberate — removes finding 2 and G10** |
| D-4 | The "only gate" claim is gone | **Deliberate — removes finding 1** |
| D-5 | The mis-scoped "What you CAN fix" list is gone | **Deliberate — removes finding 5** |
| D-6 | Receptionist dispatches into the UII directly | Deliberate; no range effect |
| D-7 | Roster says the Creator *"SELF-VALIDATES what it wrote"* — but it validates the **draft before writing** | **ACCIDENTAL DRIFT — worth fixing** |
| D-8 | Tool-failure CLARIFY retargeted DCII → Creator | Deliberate |
| D-9 | Everything else identical modulo renames | Faithful merge |
| D-10 | G7 survives unchanged in both | Pre-existing hole carried forward |

**Net:** the merge *fixed* five within-topology defects purely as a side effect
of collapsing agents, introduced one small drift (D-7), and paid for it with
the loss of the only independent numeric check.  The unhandled cases —
**G7, G8, G9, U-b, U-c, U-g, U-h** — are identical in both topologies, and
three of them are already written up as decided-but-unbuilt design in
`design_no_ask_back_and_range_degrade.md`.
