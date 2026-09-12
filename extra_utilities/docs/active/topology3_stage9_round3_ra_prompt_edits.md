# Topology 3 — Stage 9, round 3: the Requirements Analyst

Source: `3agent_system_prompts_v4.pdf` — the **round-2 build** (59 pages, RA at
30 924 chars), annotated by the owner.

**Mark-up key** (owner's): RED = remove · YELLOW = modify/edit · black
hand-typed text = the replacement wording, or a comment about what to move
where.

**Extraction.** 26 highlights, all on the Requirements Analyst's pages
(35, 36, 37, 39, 40, 41, 43, 44), plus **8 typed notes** recovered by font
census — Arial 10 pt pure black against the document's SegoeUI/Consolas at
`#1a1a1a`. Each note was matched to the highlight nearest it by y-position.

**Scope.** The Requirements Analyst only. The Receptionist, Planner, Design
Engineer and Database Handler carry no marks in this round and are touched only
where an RA edit forces it.

**Line numbers** are the worktree `rebuild-3-agent-topology-6ca792` at commit
`679bce4`. Apply top-down within a file, or re-locate by the quoted text.

**ALL APPLIED.** Every decision (R1-R14) is in the worktree — see
**§Z — the application** at the end for what ran and what was verified.

Decisions taken in step 2 are recorded in **§R**, and the item each one
resolves is struck from the sections above.

---

## §A — Your Role (PDF p.35)

| # | file · lines | mark | edit |
|---|---|---|---|
| ~~**A1**~~ | `requirements_analyst/prompt_3agents.md` L7 | YEL + note | `the stated functional requirements` → `what the user is requesting for` — **carried by R2** |

Owner's note, verbatim: *"what the user is requesting for."*

* BEFORE — `3. Whether the design matches the stated functional requirements.`
* AFTER — `3. Whether the design matches what the user is requesting for.`

> ⚠ The same phrase appears again in the RA's **Output Format** (L364-366):
> `DESIGN INTENT COMPLIANCE: <does the geometry match the stated functional
> requirements? …>`. Only one was highlighted. → **U1**

---

## §B — The three extraction sections (PDF p.36)

File: `agents/3agent/requirements_analyst/prompt_3agents.md`.

| # | line | mark | edit |
|---|---|---|---|
| **B1** | 69 | RED | delete `Record one quantitative input per line.` |
| **B2** | 117 | RED | delete `Be generous.` |
| **B3** | 117 | RED | delete `here` (in `Summarise here any natural-language permission`) |
| **B4** | 123 | RED | delete `One coherent paragraph —` |
| **B5** | 126 | RED | delete `here,` (in `Also state here, when present:`) |

**B1** — AFTER (L69-70):

    Label the quantity in the user's own words and give their unit / frame:

**B2 + B3** — AFTER (L115-119):

    Free-form prose for what cannot be quantised: shapes, aesthetics,
    comparisons, subjective impressions, image-reading hints that do not resolve
    to a number.  Summarise any natural-language permission the user gave to
    vary specific values, with its scope (blanket or per-parameter), exclusions
    and conditions.

**B4 + B5** — AFTER (L123-126):

    The CURRENT intent, not a log: purpose, performance goals, constraints,
    aesthetics, reporting preferences ("don't report back until viable"), and
    prior-attempt context only where it still shapes the design.  Also state,
    when present:

> ⚠ **B4 removes the only instruction about §3's SHAPE.** `One coherent
> paragraph` is what stops DESIGN INTENT becoming a bullet dump. Nothing else
> in the section says how long or how structured it should be. → **N1**

---

## §C — The duplicate opener (PDF p.37)

| # | file · line | mark | edit |
|---|---|---|---|
| **C1** | `requirements_analyst/prompt_3agents.md` L146 | RED | delete `You are the Requirements Analyst for a $domain_description.` |

This is the Stage-4 concatenation seam: the prompt opens with that sentence at
**L1** and says it again at **L146**, where the DC-Output-Inspector half began.
Deleting the second is unambiguously right — it is the RA's exact counterpart
of the Design Engineer's duplicate opener that round 2 removed (R5's J5).

---

## §D — The three value states: MOVE, then rephrase (PDF p.36 + p.39)

Two of the owner's notes say the same thing from opposite ends:

* p.36, sitting immediately above `### 1. QUANTITATIVE INPUTS` —
  *"put here the definition of LOCKER, FREE, SOFT LOCKED"*
* p.39, beside the section heading —
  *"this section should be moved above, before explainint the quantitative inputs"*

| # | what | edit |
|---|---|---|
| **D1** | `## The three states of a user value — LOCKED, SOFT TARGET, or FREE` + `$value_states` (`prompt_3agents.md` L247-248) | **MOVE** to immediately before `### 1. QUANTITATIVE INPUTS` (L67) |
| **D2** | `prompt_fragments/value_states_requirements_analyst_3agents.md` L1-14 | rephrase — see below |

> ⚠ **The owner's note names the states as "LOCKER, FREE, SOFT LOCKED".** The
> prompt's three states are **LOCKED / SOFT TARGET / FREE**, and `SOFT TARGET`
> is a literal marker string the RA writes and the Design Engineer matches
> against. If a rename is wanted it has to move in both prompts at once. I have
> assumed these are typos and kept the existing names. → **Q1**

### D2 — the RED spans inside the fragment, and the owner's open question

The owner's note on p.39 is explicit that this one is undecided:

> *"this text in red, I don't know whether to remove it entirely or just
> rephrase it accordingly to mention explicit user values provided."*

The RED spans are #09, #10, #11, #13, #14, #15:

| # | line | RED text |
|---|---|---|
| 09 | 2 | `read off the QUANTITATIVE INPUTS you recorded from the user's inputs:` |
| 10 | 7-8 | `a value marked SOFT TARGET (goal: …; keep near … if free).` |
| 11 | 8 | `that` (in *"subordinated it to that goal"*) |
| 13 | 9 | `the marker itself IS the` |
| 14 | 10 | `you` (in *"and you never have to justify moving it"*) |
| 15 | 13 | `a parameter absent from QUANTITATIVE INPUTS:` |

**My answer: rephrase, do not delete** — and the MOVE is the reason.

Every one of those spans anchors the states to a **QUANTITATIVE INPUTS section
the RA has not yet been told to write**. That reads fine at L247, after §1. Move
the block to L67 and every one becomes a forward reference to a section the
reader has not reached. That is exactly why they are marked, and it is why
deleting them is the wrong repair: the problem is the ANCHOR, not the
recogniser.

**AFTER** — `value_states_requirements_analyst_3agents.md`, replacing L1-14:

    Every value the user could have given is in exactly one of three states.
    Decide the state from what the user actually said:

    - **LOCKED** — the user stated the value plainly and attached no goal to
      it.  The user fixed it.  LOCKED is not an absolute wall: it may change
      when an authorisation frees it.
    - **SOFT TARGET** — the user gave the value but subordinated it to a
      qualitative goal, so it is neither locked nor free.  **The goal
      governs**: that subordination IS the authorisation to move the value
      (within range) as far as the goal requires, and it never has to be
      justified.  The stated value is a reference, not a pull — it settles the
      parameter only when the goal does NOT bear on it.
    - **FREE** — the user said nothing that fixes it: it is the system's
      choice within range.

Every recogniser survives, re-anchored on the user's words. This is the same
resolution the owner approved for the Design Engineer's copy in round 2 (R3).

---

## §E — Per-claim verification (PDF p.39)

| # | line | mark | edit |
|---|---|---|---|
| **E1** | 252 | YEL + note | `Your job:` → `Your job when a render is produced:` |
| **E2** | 254-255 | RED | delete `You do NOT re-check parameters (the chain already did) — take its stated values as given.` |
| **E3** | 256 | RED | delete `the source encodes` |
| **E4** | 264-265 | RED | delete `count in the RENDER only and compare with the source's expected count —` |

Owner's note: *"Your job when a render is produced: "*

**AFTER** (L252-257):

    Your job when a render is produced: does the Design Engineer's rendered
    OUTPUT match what the in-scope source(s) — the user's raw inputs — ask
    for?  Don't approve on coarse similarity alone: enumerate the checkable
    claims and check each against the RENDER, deciding the outcome:

**E4** — AFTER (L262-266):

        State the claim, what the render shows, and whether they agree —
        specific, both sides quoted, not a one-word verdict.  For counts,
        count them one by one, traversing every instance once, never
        from a glance.

> ⚠ **E2 is the one deletion here with a consequence.** *"You do NOT re-check
> parameters (the chain already did)"* is the only sentence keeping the RA out
> of the Design Engineer's job. → **N2**

---

## §F — The 16-parameter list is printed twice (PDF p.40-41)

File: `agents/3agent/dc_config/parameters_requirements_analyst_3agents.md`,
57 lines, two copies:

* **copy 1, L1-23** — names + **descriptions** + ranges, ranges **hard-coded**;
* **copy 2, L25-57** — names only, ranges wrapped in
  `<<DCOI_RANGES_ON>>`, **plus three geometry notes copy 1 does not have**.

The RED covers **copy 2**.

| # | lines | mark | edit |
|---|---|---|---|
| **F1** | 25-57 | RED | delete one of the two copies |

✅ **Resolved — see R1.**  The owner agreed to a UNION: one list, copy 1's
descriptions, the ranges moved inside the `<<DCOI_RANGES_ON>>` gate, and
copy 2's notes folded in.

---

## §G — ROUTING (PDF p.43-44)

File: `agents/3agent/prompt_fragments/routing_requirements_analyst_3agents.md`
(41 lines). This fragment is still a raw Stage-4 concatenation and the owner
marked most of the seam.

Owner's notes:
* p.43, under the `ROUTING` heading — *"put here the bullet points of the call_(agent) instructions"*
* p.44, beside the `call_design_engineer` block — *"join these points together"*
* p.44 — *"these call_(agent) instructions should be put under \"ROUTING\""*

| # | lines | mark | edit |
|---|---|---|---|
| **G1** | 1-6 | RED | delete the first `call_planner` bullet **and** its *"The same tool is how you report a problem…"* paragraph |
| **G2** | 13-14 | RED | delete `Keep the message to one or two sentences of observations.  Include your read of how readable the images were.` |
| **G3** | 28-33 | YEL + note | **join** the two `call_design_engineer` bullets into one |
| **G4** | 28-41 | note ×2 | **MOVE** all four `call_*` bullets to the TOP of the fragment, directly under the `ROUTING` heading |

**Current order** (what the model reads): `call_planner` FORWARD →
report-a-problem → CLARIFY-to-Planner → keep-it-short → if-the-Planner-CLARIFYs
→ *Routing is a tool call — MANDATORY* → then, finally, the four `call_*`
bullets.

**AFTER** — the whole fragment:

    - ``call_design_engineer(message)`` — call it when you request a
      PARAMETER/design change through a REVISE message; to hand back a
      PRECISION REFINE gap description while the refine loop is still turning;
      when nothing about the design changes (a render that failed, or a
      blade-sections render of the CURRENT attempt's existing
      ``parameters.json``); and to send a clarification request (CLARIFY) when
      the incoming hand-off is ambiguous, missing data, or contains an error
      the Design Engineer can fix.
    - ``call_planner(message)`` — call it when you APPROVE a design, when you
      recommend REVISE because the upstream INTERPRETATION diverged even
      though every parameter is in range, or when a tool failure, a missing
      authorisation, or a problem you cannot solve yourself stops you: hand it
      back to the Planner and say plainly what blocked you.

    If you cannot do your job because the incoming hand-off is ambiguous,
    missing data, or contains an error the sender can fix, hand back with a
    clear clarification request (CLARIFY) — to the Design Engineer when it can
    fix it, to the Planner otherwise.

    **If the Planner CLARIFYs back to you** — a value you extracted was
    ambiguous or misread, or a file was overlooked — re-read the source and
    forward again.

    ### Routing is a tool call — MANDATORY
    Do NOT describe or announce which tool you intend to call.  Do NOT wait
    for the next turn to invoke it.  Do NOT substitute the tool call with
    free-form prose that says "routing to X".  In the same response where you
    finish your work, invoke the tool.  Any ordinary response text you produce
    is for your own brief reasoning only — it is NOT delivered to the
    recipient; only the tool's ``message`` argument is.

41 lines → 30. Two `call_*` bullets instead of four, both at the top, each
listing every occasion it is used.

✅ **Resolved — see R3**, which also recovers the inputs-only turn (**P5**).

---

# The three questions

Every claim below was checked against the **assembled** prompt — the RA's
30 924-character text exactly as the model receives it — not against the source
fragments. Counts are whitespace-insensitive.

---

## §M — Logic inconsistencies

### X1 — 🔴 "Your Role" lists item 1, then item 3

The first thing the Requirements Analyst reads:

    ## Your Role
    Analyse the generated propeller geometry by examining:
    1. The rendered images (isometric, top-down, side views).
    3. Whether the design matches the stated functional requirements.

Item 2 is `<<MESH_ON>>2. The quality-check report (if available) in the hand-off
message.<</MESH_ON>>` (source L6). `MESH_CHECKS = False`, so it is stripped —
but the numbering was never made conditional with it. Verified: the string
`quality-check report` appears **0 times** in the assembled prompt.

So the RA is handed a three-item list of what to examine, is shown items 1 and
3, and is left to infer that an item 2 exists somewhere. This is the exact
failure mode recorded in round 4 of the earlier prompt reduction, where the
DC Output Inspector fabricated QC affordances from residue like this — and it
sits on the same line the owner highlighted for **A1**.

Fix: put the number inside the gate, or renumber to 1/2.

### X2 — 🔴 The RA has TWO output formats and is never told which to use when

    ## What to extract      -> §1 QUANTITATIVE INPUTS
                               §2 QUALITATIVE DESCRIPTIONS
                               §3 DESIGN INTENT
                            (a three-section structured document, ~95 lines
                             of rules about how to write it)

    ## Output Format        -> COMPARISON-SOURCE CLAIMS CHECKED
                               GEOMETRY ANALYSIS
                               DEFECTS
                               DESIGN INTENT COMPLIANCE
                               RECOMMENDATION
                            ("These sections help structure the verdict")

Neither cross-references the other. Only the second says what it is for. And
**nothing anywhere says where §1/§2/§3 go** — in the 5-agent topology they were
the sections of a file the User Input Inspector WROTE; topology 3 has no such
file, so they can only be prose in the routing message, and the prompt never
says so.

The RA runs in two distinct situations — extract on the way down, judge the
render on the way back — and the prompt never names them. The owner's **E1**
edit (*"Your job **when a render is produced**"*) is the first sentence in the
whole prompt to acknowledge that there are two, which is why I think this is
the round's most valuable finding.

### X3 — 🔴 `DCOI_KNOWS_PARAMS_RANGES` is defeated: the RA sees every range and is never told the rule

`workflow_settings/settings.py:726` — `DCOI_KNOWS_PARAMS_RANGES: bool = False`.
The setting exists to decide whether the RA is shown the parameters' allowed
ranges.

What actually reaches the model today:

    ### Global / ring                                     <- copy 1, L1-23
     1. bladeCount         (integer)      — Number of blades [3; 6]
     2. impellerRadius     (mm)           — Outer radius … [60; 80]
     3. impellerThickness  (mm)           — Wall thickness … [1; 5]

    ### Global / ring                                     <- copy 2, L25-57
     1. bladeCount         (integer)
     2. impellerRadius     (mm)
     3. impellerThickness  (mm)

Copy 2 respects the gate. **Copy 1 hard-codes the ranges**, so they ship
regardless. Meanwhile the paragraph that tells the RA how to USE them —

    <<DCOI_RANGES_ON>>You are given the NAMES and the allowed ranges.  Use the
    ranges to tell a gap you can ask to close from one you cannot: never ask
    for a value outside its range …<</DCOI_RANGES_ON>>

— IS gated, and is stripped. Verified: 0 occurrences in the assembled prompt.

**Net effect: the RA is shown every allowed range with no instruction about
them, which is the worst of both settings.** Applying **F1** as marked deletes
copy 2 and makes that permanent.

### X4 — 🔴 CLARIFY has two different targets, on the same trigger

`routing_requirements_analyst_3agents.md`:

    L8-11   If you cannot do your job because the incoming hand-off is
            ambiguous, missing data, or contains an error the sender can fix,
            hand back to the Planner with ``call_planner`` and a clear
            clarification request (CLARIFY).

    L31-33  Also route to the Design Engineer with a clear clarification
            request (CLARIFY) if you cannot do your job because the incoming
            hand-off is ambiguous, missing data, or contains an error it can
            fix.

Same condition, near-identical wording, **two different recipients**. A model
that reads the first and stops has learned the wrong one for the common case:
the RA's incoming hand-off comes from the Design Engineer, not the Planner.
The owner's §G edits collapse this — my §G AFTER resolves it as *"to the Design
Engineer when it can fix it, to the Planner otherwise"* — but it is worth
naming as a defect rather than as tidying.

### X5 — 🟠 `call_design_engineer` is described twice, with disjoint conditions

    L28-30  ``call_design_engineer(message)`` — when nothing about the design
            changes: a render that failed, or a blade-sections render of the
            CURRENT attempt's existing ``parameters.json``.

    L34-36  ``call_design_engineer(message)`` — call it when you request a
            PARAMETER/design change through a REVISE message, and to hand back
            a PRECISION REFINE gap description while the refine loop is still
            turning.

The first says the tool is for cases where **nothing changes**; the second says
it is for **requesting a change**. Read in order, the first teaches the reader a
rule the second contradicts. This is the owner's *"join these points together"*
(**G3**), and it is the reason it matters.

---

## §O — Duplications the mark-up did not catch

All four verified by whitespace-insensitive count against the assembled prompt.

| # | what | where | count |
|---|---|---|---:|
| **U1** | `the stated functional requirements` | `## Your Role` **and** `Output Format`'s `DESIGN INTENT COMPLIANCE:` | 2 |
| **U2** | the SOFT TARGET rule, incl. the words *"The goal governs"* | §1's `SOFT TARGET —` bullet **and** the value-states fragment | 2 |
| **U3** | `### Filled-in templates and forms` | `sketch_handling_requirements_analyst_3agents.md` L4 **and** L44 | 2 |
| **U4** | `count them one by one, traversing every instance once, never from a glance` | §1's *Count countable features* **and** *Per-claim verification* | 2 |

**U1 is created by A1.** The owner's edit changes the Your-Role copy to *"what
the user is requesting for"* and leaves the Output-Format copy saying *"the
stated functional requirements"*. Two names for one check, in one prompt.

**U2 gets worse under D1.** Today the two SOFT TARGET statements are ~215 lines
apart. Moving the value-states block to sit immediately before §1 puts them
~30 lines apart, both opening with *"The goal governs"*. The move is right; the
duplication has to be resolved with it.

**U3 is the RA's last Stage-4 seam.** `sketch_handling_requirements_analyst_3agents.md`
is still a two-half concatenation, and the two halves each carry a
`### Filled-in templates and forms` section — one saying *"only the marks added
on top (darker, handwritten, irregular) are input"*, the other *"only the marks
added on top are input"*. Same rule, one slightly poorer. Out of the owner's
marked scope, but it is the file the next round would have to open anyway.

**U4** is the same sentence in two sections that are about different things —
counting during extraction, and counting during verification. Arguably fine;
noted for a decision rather than proposed for deletion.

---

## §Q — one question the mark-up raises

### Q1 — "LOCKER, FREE, SOFT LOCKED"

The p.36 note asks for *"the definition of LOCKER, FREE, SOFT LOCKED"*. The
prompt's three states are **LOCKED**, **SOFT TARGET** and **FREE**, and
`SOFT TARGET (goal: …; keep near … if free)` is a **literal marker string** the
RA writes into its report and the Design Engineer matches against — round 2's
R3 kept that string in the DE's prompt specifically so the two agents agree on
it.

I have read `LOCKER` / `SOFT LOCKED` as typos and kept the existing names. If
you do want a rename, it has to move in the RA's fragment, the DE's fragment and
the Planner's fragment in the same commit, or the two ends of the hand-off stop
matching.

---
## §N — Did you remove anything critical?

Four. One I would not apply as marked at all.

### N3 — 🔴 §F deletes the copy that respects the ranges setting, and two facts that exist nowhere else

`parameters_requirements_analyst_3agents.md` holds the list twice, and
**neither copy is a superset** — this is a union, not a choice:

| | copy 1 (L1-23) | copy 2 (L25-57) — the RED one |
|---|---|---|
| parameter descriptions (*"— Number of blades"*, *"— Profile thickness"*) | ✅ | ❌ |
| allowed ranges | hard-coded, **always shown** | wrapped in `<<DCOI_RANGES_ON>>` |
| *"(The outer-ring HEIGHT is not a parameter …)"* | ❌ | ✅ |
| *"(The central hub is a FIXED cylinder of radius 8 mm — not a parameter …)"* | ❌ | ✅ |
| *"(The middle section has NO thickness, camber or high-point of its own.)"* | ❌ | ✅ |

Checked against the assembled prompt, whitespace-insensitively:

* `outer-ring HEIGHT is not a parameter` — **1×**, only in copy 2. Deleting
  copy 2 loses it.
* `The middle section has NO thickness, camber or high-point of its own` —
  **1×**, only in copy 2; the alternative phrasing *"no profile parameters"*
  appears **0×**. Deleting copy 2 loses it. This is the fact the precision
  sections-matching runs turned up the hard way — the middle section has no
  shape parameters of its own, so asking to reshape it directly is a request
  the configurator cannot serve.
* `hub hides the innermost part` — **2×**: copy 2, and `## Domain Structure`.
  This one survives the deletion; only the explicit *"not a parameter"* framing
  is lost.

And the ranges problem is **X3**: deleting copy 2 makes
`DCOI_KNOWS_PARAMS_RANGES` permanently inert.

**Recommendation — a union, not a deletion.** Keep copy 1's descriptions, put
its ranges behind the same gate copy 2 uses, and fold in copy 2's two unique
notes. One list, descriptions kept, the setting works again, nothing lost. I'll
bring the exact text as a step-2 item.

### N2 — 🔴 §E's E2 removes the RA's only boundary against re-doing the Design Engineer's job

    You do NOT re-check parameters (the chain already did) — take its stated
    values as given.

Two reasons this one carries weight:

1. It is the only sentence in the RA's prompt that says so. Nothing else scopes
   the RA away from parameter auditing.
2. **It is no longer true as written, which is probably why it reads oddly.**
   *"the chain already did"* described the 7-agent topology, where the DC Input
   Inspector performed an independent parameter audit. Topology 3 has no such
   agent — round 2 removed the last of that text from the Design Engineer. The
   only parameter check left is the DE checking its own draft
   (`## Validate before you write (HARD)`).

So the sentence is half right: the RA should still not re-check parameters —
that is not its job and it cannot see them reliably — but the *reason* given is
false. Deleting it removes a true rule along with a false justification.

**Recommendation:** keep the rule, drop the false reason —
*"Do not re-check the parameter values: take the Design Engineer's stated
values as given and judge the RENDER."*

### N1 — 🟠 §B's B4 removes the only instruction about §3's shape

`One coherent paragraph —` is the only thing in `### 3. DESIGN INTENT` that
says how long or how structured the section should be. Everything else there is
about content. Without it, §3 has no stated shape while §1 and §2 both do
(*"one quantitative input per line"* — itself deleted by **B1** — and
*"Free-form prose"*).

Low cost to keep three words; flagging it so the removal is deliberate.

### N4 — 🟠 §G's G1 removes the out-of-scope and missing-file hand-back cases

    The same tool is how you report a problem: hand back to the Planner with a
    description of the problem when the request is out of scope, asks for
    something not in the user's files, or you hit an unrecoverable error.

The surviving `call_planner` bullet names APPROVE, INTERPRETATION-REVISE, and
*"a tool failure, a missing authorisation, or a problem you cannot solve
yourself"*. **Out of scope** and **asks for something not in the user's files**
are not instances of any of those — they are the RA discovering the request
cannot be served at all, which is a different thing from being blocked.

My §G AFTER folds them under *"a problem you cannot solve yourself"*. That is a
stretch. Say the word and I will name all three explicitly.

---

## §P — what a five-lens audit found on top

A fleet of five finders (duplication · stale references · logic · what the RED
marks break · cross-agent consistency) swept the assembled prompt, and every
finding was then handed to an independent agent told to REFUTE it. **33 raised,
14 survived.** Nine of those add something not already in §M/§N/§O; the other
five are the same findings from a different angle and are folded into X1-X5.

I re-verified each of the nine myself before recording it — the counts below
are mine, not the fleet's.

### P1 — 🔴 `### Tool-use hard rules` is printed twice, and the copies differ

Assembled prompt, lines 557-565 — verbatim:

    ### Tool-use hard rules
    - DON'T invent or guess a path.  Every path you hand a tool must trace to
      your incoming message or to a tool result.

    ### Tool-use hard rules
    - DON'T invent or guess a path.  Every path you hand a tool must trace to
      your incoming message or to a tool result.
    - DO route EVERY arithmetic operation through the ``calculate`` tool —
      never mental arithmetic, even for trivial sums.

Same heading, same first rule, and the second copy adds the `calculate` rule.
The first copy is a strict subset. This is the `$hard_constraints_tools` seam,
the RA's counterpart of the duplicate blocks round 2 removed from the Design
Engineer (§K).

### P2 — 🔴 The hand-off is capped at "one or two sentences" and it is the ONLY carrier of the extraction

    Keep the ``message`` to one or two sentences of observations.  Include
    your read of how readable the images were.

Topology 3 has no extraction file. The routing `message` is the only channel by
which QUANTITATIVE INPUTS, QUALITATIVE DESCRIPTIONS and DESIGN INTENT can reach
anyone. The same prompt then demands one input per line, a `SOFT TARGET` marker
per softened value, a coherent paragraph of design intent, and a mandatory
`INTERPRETATION:` line. **Both cannot be obeyed**, and the failure is silent
and directional: a value squeezed out by the cap is not "missing" downstream,
it reads as **FREE** — the Design Engineer's own rule is *"FREE — the user said
nothing that fixes it: it is the system's choice within range."*

**Your G2 already deletes exactly this line.** That mark is not tidying; it
removes a live contradiction. Worth knowing what it was doing.

### P3 — 🟠 The REQUIRED side-by-side call cannot hold the images it is told to load

The precision loop (assembled L284-289):

    **(If user images are present) Compare the render against the user's
    image(s), side by side.**  In ONE ``view_images`` call with
    ``side_by_side=True``, load the current render (from the ``Render images:``
    paths) together with the user's image(s) …

`agents/shared/user_inputs_tool.py:937-940`:

    if side_by_side and resolved:
        # Merge up to 3 (cropped) panels into ONE labelled composite image.
        pil_panels, labels = [], []
        for j, r in enumerate(resolved[:3]):

A 3D phase hand-off carries three render views (isometric / top / side) plus at
least one user image — four or more panels. `resolved[:3]` **silently drops the
rest**: no error, no mention in the returned summary. The RA is told this
comparison is REQUIRED, does it, and is never told part of what it asked for
was discarded.

### P4 — 🟠 The no-renders fallback points at the report X1 deleted

    If NO render paths were provided, you CANNOT perform a visual analysis …
    Say so plainly, base your response on the text report only …

*"The text report"* is the quality-check report — item **2** of the Your Role
list, the one `<<MESH_ON>>` strips. With `MESH_CHECKS = False` there is no text
report at all, so the sole fallback offered when renders are missing names an
artefact the RA can never receive. X1 and P4 are the same hole seen from two
sides.

### P5 — 🟠 After G1, no surviving `call_planner` condition matches an extraction turn

The RA's first pass is inputs-only: the Planner's `INPUT ANALYSIS` move routes
to it *"to (re-)read the user's inputs"*, before any attempt exists. On that
turn there is no render, nothing to APPROVE, no INTERPRETATION divergence, no
tool failure — and the RED deletes *"FORWARD to the Planner. This is the
natural next step,"* which was the only unconditional route.

This is **N4** sharpened: it is not just the out-of-scope case that loses its
bullet, it is the RA's entire normal extraction turn. My §G AFTER does not fix
this either — I will bring a corrected `call_planner` bullet in step 2.

### P6 — 🟠 The RA drives a "PRECISION REFINE" loop through a Design Engineer that has never heard the phrase

Counted in the assembled prompts:

| string | RA | DE |
|---|---:|---:|
| `PRECISION REFINE` | 3 | **0** |
| `refine` | many | **0** |

The RA is told to *"hand your gap description back with `call_design_engineer`,
clearly marked as a PRECISION REFINE — still iterating, not a blocker."* The DE
has no section about precision refinement at all; its only instruction for
acting on a prose gap description is `## Acting on a Planner qualitative
directive (HARD)`, which is scoped to the **Planner** as the sender and whose
second valid response is to hand the problem back.

### P7 — 🟠 `Input directory:` is required only of Planner hand-offs, but the refine loop bypasses the Planner

| prompt | occurrences of `Input directory` |
|---|---:|
| Planner | 1 (*"Every `call_requirements_analyst` AND `call_design_engineer` message MUST carry this line verbatim"*) |
| Requirements Analyst | **0** |
| Design Engineer | **0** |

Both read tools' schemas say the path comes *"supplied in your hand-off under
the `Input directory:` label (do NOT guess a path)"*. The RA↔DE refine loop is
exactly the leg the Planner is not on, and neither agent is told to carry the
label forward. First re-read inside a refine loop has no path to use.

### P8 — 🟡 The Planner's roster and the Planner's own Role 3 disagree about where defects go

`available_agents_planner_3agents.md` — *"performs a qualitative visual
analysis, calling **you** to approve the design or **to flag defects and
problems**"*. Twenty lines later, Role 3 — *"a mid-loop REVISE goes straight
back to the Design Engineer."* The RA agrees with Role 3. The roster is stale.

(This is a **Planner** file, out of this round's scope — noted for the next.)

### P9 — 🟡 Two RA output labels are read by nobody

`QUALITATIVE DESCRIPTIONS` and the mandatory `INTERPRETATION:` line appear in
**no other agent's prompt**. The Planner names `PRECISION DEMAND`, `DESIGN
INTENT` and `PRECISE SKETCH`; the DE names `QUANTITATIVE INPUTS` and `DESIGN
INTENT`. So the RA is compelled to emit an INTERPRETATION verdict on every run
(*"State one every time"*) into a pipeline where no recipient is told to read
it. Not a defect on its own — but it is the cheapest thing to cut if P2's
sentence cap is ever to be honoured.

### Where I overrode the refuters

Three refutations reasoned from an artefact of MY extraction tool rather than
from the files, and I have kept the findings they tried to kill:

* *"RED #21 shows `!! NO MATCH` … proving it is not a valid deletion mark"* —
  `!! NO MATCH` means my locator's fuzzy threshold did not fire on a long span,
  nothing more. The text is plainly at
  `parameters_requirements_analyst_3agents.md` L44-50. **N3 stands.**
* The same reasoning was used against the *"outer-ring HEIGHT is not a
  parameter"* loss. I counted it directly in the assembled prompt: **1×**.
  **N3 stands.**
* *"RED #17 … misidentifies the source and scope"* of the do-not-re-check-
  parameters boundary. The sentence is at `prompt_3agents.md` L254-255 and
  there is no other. **N2 stands**, with the correction that its stated reason
  is false (which is the more interesting half).

The other 16 refutations I accept; several killed hypotheses of my own,
including a tempting one that the `<<MESH_ON>>` markers were stale residue —
they are live toggle infrastructure, and only the numbering around them is
broken (X1).

---
---
---

# §R — RESOLVED

### R1 — one parameter list, with the ranges behind their gate  *(resolves X3, N3, F1)*

**Problem.** `parameters_requirements_analyst_3agents.md` printed the list
twice and **neither copy was a superset**:

| | copy 1 (L1-23) | copy 2 (L25-57) — the RED one |
|---|---|---|
| parameter descriptions | ✅ | ❌ |
| allowed ranges | hard-coded, **always shown** | wrapped in `<<DCOI_RANGES_ON>>` |
| *outer-ring HEIGHT is not a parameter* | ❌ | ✅ (**1×** in the whole prompt) |
| *the central hub is not a parameter* | ❌ | ✅ |
| *the middle section has NO thickness, camber or high-point* | ❌ | ✅ (**1×** in the whole prompt) |

`DCOI_KNOWS_PARAMS_RANGES = False` (`workflow_settings/settings.py:726`), so the
gated guidance paragraph — *"You are given the NAMES and the allowed ranges.
Use the ranges to tell a gap you can ask to close from one you cannot…"* — was
stripped (0 occurrences), while copy 1 leaked every range anyway. **The RA was
shown all 16 ranges and never told the rule that governs them**, and deleting
copy 2 as marked would have made that permanent.

**Decision (owner, agreed as proposed).** A union, not a choice.

**Edit** — replace the whole file, 57 lines → 30:

```
### Global / ring
 1. bladeCount         (integer)                             — Number of blades<<DCOI_RANGES_ON>> [3; 6]<</DCOI_RANGES_ON>>
 2. impellerRadius     (mm)                                  — Outer radius of the impeller ring<<DCOI_RANGES_ON>> [60; 80]<</DCOI_RANGES_ON>>
 3. impellerThickness  (mm)                                  — Wall thickness of the outer ring<<DCOI_RANGES_ON>> [1; 5]<</DCOI_RANGES_ON>>

(The outer-ring HEIGHT is not a parameter — it is derived automatically to fit
the outer blade section.)

(The central hub — a FIXED cylinder of radius 8 mm — is not a parameter either.)

### Inner blade section
 4. innerThickness     (% of the INNER chord)                — Profile thickness<<DCOI_RANGES_ON>> [3; 24]<</DCOI_RANGES_ON>>
 5. innerMaxPos        (tenths of the INNER chord, integer)  — Chordwise position of max camber<<DCOI_RANGES_ON>> [2; 8]<</DCOI_RANGES_ON>>
 6. innerCamber        (% of the INNER chord)                — Profile camber<<DCOI_RANGES_ON>> [0; 9]<</DCOI_RANGES_ON>>
 7. innerChord         (mm)                                  — Chord length<<DCOI_RANGES_ON>> [3; 11]<</DCOI_RANGES_ON>>
 8. innerAngle         (degrees)                             — Angle of attack<<DCOI_RANGES_ON>> [2; 25]<</DCOI_RANGES_ON>>

### Middle blade section
 9. middlePos          (fraction of blade span, unitless)    — Middle-section position along the blade: 0 = root (INNER BLADE SECTION, r = 4 mm), 1 = tip<<DCOI_RANGES_ON>> [0.3; 0.7]<</DCOI_RANGES_ON>>
10. middleChord        (mm)                                  — Chord length<<DCOI_RANGES_ON>> [10; 30]<</DCOI_RANGES_ON>>
11. middleAngle        (degrees)                             — Angle of attack<<DCOI_RANGES_ON>> [2; 25]<</DCOI_RANGES_ON>>

(The middle section has NO thickness, camber or high-point of its own.)

### Outer blade section
12. outerThickness     (% of the OUTER chord)                — Profile thickness<<DCOI_RANGES_ON>> [3; 24]<</DCOI_RANGES_ON>>
13. outerMaxPos        (tenths of the OUTER chord, integer)  — Chordwise position of max camber<<DCOI_RANGES_ON>> [2; 8]<</DCOI_RANGES_ON>>
14. outerCamber        (% of the OUTER chord)                — Profile camber<<DCOI_RANGES_ON>> [0; 9]<</DCOI_RANGES_ON>>
15. outerChord         (mm)                                  — Chord length<<DCOI_RANGES_ON>> [10; 30]<</DCOI_RANGES_ON>>
16. outerAngle         (degrees)                             — Angle of attack<<DCOI_RANGES_ON>> [2; 25]<</DCOI_RANGES_ON>>
```

The `<<DCOI_RANGES_ON>>` markers are resolved at assembly time, so one file
gives two outcomes: with the setting **False** (today) the RA reads names and
descriptions and **no ranges**; with it **True** every `[min; max]` reappears,
alongside the guidance paragraph that is gated the same way. Either way the
prompt and the setting now agree.

The hub note was shortened. Its second half — *"It is LARGER than the blade
root at r = 4 mm, so the hub hides the innermost part of each blade"* — already
appears verbatim in `## Domain Structure` (counted: 2×). In a section headed
*"the ONLY parameters that exist"* the load-bearing half is *"is not a
parameter"*, so that is what survives.

---

### R2 — the hole where item 2 used to be  *(resolves X1, P4; carries A1)*

**Problem.** One cause, two symptoms. `MESH_CHECKS = False` strips the
`<<MESH_ON>>` region but not the number in front of it.

*Symptom 1* — the first list the RA reads assembles as `1.` … `3.`, with no
`2.`  *Symptom 2* — the no-renders fallback then offers that stripped item as
the thing to fall back ON. `text report` and `quality-check` occur in exactly
two places in the whole prompt: L6 (stripped) and L169.

**Decision (owner, agreed as proposed).**

**Edit 1** — `requirements_analyst/prompt_3agents.md` L4-7. Move the gated item
to the END so the numbering is contiguous in both states, and apply **A1** to
what is now item 2:

```diff
 Analyse the generated $dc_name geometry by examining:
-1. The rendered images (isometric, top-down, side views).<<MESH_ON>>
-2. The quality-check report (if available) in the hand-off message.<</MESH_ON>>
-3. Whether the design matches the stated functional requirements.
+1. The rendered images (isometric, top-down, side views).
+2. Whether the design matches what the user is requesting for.<<MESH_ON>>
+3. The quality-check report (if available) in the hand-off message.<</MESH_ON>>
```

mesh off → `1. 2.`; mesh on → `1. 2. 3.`  No conditional numbering, nothing to
get wrong when the toggle flips. Safe because the list enumerates what to
examine, not a sequence.

**Edit 2** — L166-169, so the fallback names something that exists in both
states:

```diff
   tool with empty or fabricated paths.  Say so plainly, base your response
-  on the text report only, and route per ROUTING below.
+  on what the hand-off itself states<<MESH_ON>> plus the quality-check
+  report<</MESH_ON>>, and route per ROUTING below.
```

---

### R3 — the ROUTING fragment, rebuilt  *(resolves X4, X5, P2, P5, N4, G1-G4)*

**Problem.** All seven marks live in one 41-line file that was still a raw
Stage-4 concatenation:

* `call_planner` described at L1-6 **and** L37-41; `call_design_engineer` at
  L28-30 **and** L34-36, the first saying the tool is for *"when nothing about
  the design changes"* and the second for *requesting* a change (**X5**);
* CLARIFY at L8-11 (→ the **Planner**) and L31-33 (→ the **Design Engineer**),
  on a word-for-word identical trigger, with the RA's most common sender being
  the DE (**X4**);
* `Keep the message to one or two sentences of observations` (L13) capping the
  ONLY channel that carries the whole extraction, in a topology with no
  extraction file — a value squeezed out by that cap does not read as missing
  downstream, it reads as **FREE** (**P2**);
* the four `call_*` bullets arriving LAST, after the rules that depend on them.

**Decision (owner, agreed as proposed).** Replace the file — 41 lines → 32:

```
- ``call_design_engineer(message)`` — call it when you request a
  PARAMETER/design change through a REVISE message; to hand back a PRECISION
  REFINE gap description while the refine loop is still turning; when nothing
  about the design changes (a render that failed, or a blade-sections render
  of the CURRENT attempt's existing ``parameters.json``); and to send a
  clarification request (CLARIFY) when the incoming hand-off is ambiguous,
  missing data, or contains an error the Design Engineer can fix.
- ``call_planner(message)`` — call it to report what you found on an
  inputs-only turn, when you APPROVE a design, when you recommend REVISE
  because the upstream INTERPRETATION diverged even though every parameter is
  in range, and when something stops you: a tool failure, a missing
  authorisation, a request that is out of scope or asks for something not in
  the user's files, or any problem you cannot solve yourself — hand it back
  and say plainly what blocked you.

**If the Planner CLARIFYs back to you** — a value you extracted was
ambiguous or misread, or a file was overlooked — re-read the source and
forward again.

### Routing is a tool call — MANDATORY
Do NOT describe or announce which tool you intend to call.  Do NOT wait
for the next turn to invoke it.  Do NOT substitute the tool call with
free-form prose that says "routing to X".  In the same response where you
finish your work, invoke the tool.  Any ordinary response text you produce
is for your own brief reasoning only — it is NOT delivered to the
recipient; only the tool's ``message`` argument is.
```

**What each mark did.**

| mark | effect |
|---|---|
| **G4** | both `call_*` bullets now open the fragment, under `ROUTING` — the owner's two notes |
| **G3** | the two `call_design_engineer` bullets become one, which closes **X5** |
| **X4** | CLARIFY resolved by scope: *"an error the Design Engineer can fix"* → the DE; everything else that blocks you → the Planner |
| **G1** | the FORWARD bullet and the report-a-problem paragraph deleted, as marked |
| **G2** | the one-or-two-sentence cap deleted, as marked — this is **P2** |
| **N4** | G1's loss recovered: *"a request that is out of scope or asks for something not in the user's files"* |
| **P5** | and the one my §G draft got wrong — *"to report what you found on an inputs-only turn"*. Without it the RA's normal extraction turn matches no condition at all, because there is no render to approve or revise. |

---

### R4 — the two situations the RA is called in  *(resolves X2, audit finding 03; gives E1 a home)*

**Problem.** The prompt carried two complete output specifications that never
referenced each other — `## What to extract` (§1/§2/§3, ~120 lines) and
`## Output Format` (five verdict labels) — and only the second said what it was
for. **Nothing said where §1/§2/§3 go**: in the 5-agent topology they were the
sections of a file the User Input Inspector wrote, and topology 3 deleted the
file without saying what replaced it. On an inputs-only turn the one section
declared always-required was unsatisfiable: `RECOMMENDATION: <APPROVE, or
REVISE …>` with no design to approve.

Both of the RA's neighbours already solve this — the Receptionist has
`## Two distinct situations you operate in`, the Planner has `## The three
situations you are called in`. The RA was the only multi-mode agent without
one, and it is the one that inherited two whole jobs from two parents.

**Decision (owner, agreed as proposed, plus the Output-Format clause).**

**Edit 1** — insert after `## Your Role`, before `## Domain Structure`:

    ## The two situations you are called in

    **Situation A — INPUTS ONLY.**  The Planner routes to you to (re-)read the
    user's inputs; no render exists yet.  What you produce is the EXTRACTION —
    the three sections under "What to extract" below — written as prose in your
    routing ``message``.  There is no extraction file in this system: your
    message IS the record, so anything you leave out is lost.  Route to the
    Planner.

    **Situation B — A RENDER TO JUDGE.**  The Design Engineer hands you render
    paths.  What you produce is the VERDICT — the labels under "Output Format"
    below.  You still read the user's inputs here, but as the EVIDENCE you
    compare the render against, not to re-report them.  Route per ROUTING.

**Edit 2** — `## Output Format`'s opener, so the pairing is visible from both
ends:

```diff
 ## Output Format
-These sections help structure the verdict — use them when useful, not as
-a rigid template; RECOMMENDATION is the one part downstream always
-needs.
+These sections help structure the verdict in Situation B — use them when
+useful, not as a rigid template; RECOMMENDATION is the one part downstream
+always needs.
```

+14 lines. §1/§2/§3 finally have a destination and a stated reason — *"your
message IS the record"*, the same fact that made **P2**'s sentence cap
dangerous. `RECOMMENDATION` stops being required on a turn with nothing to
recommend. **E1** now names a situation the prompt has defined. And the audit's
*"§3 implies a file"* finding closes, because §1/§2/§3 are explicitly labels in
the message.

---

### R5 — the value states: moved, re-anchored, de-duplicated  *(resolves D1, D2, U2, Q1)*

**Q1 settled first.** The owner confirms *"LOCKER"* and *"SOFT LOCKED"* were
typos: the states are **LOCKED** and **SOFT TARGET**. No rename. This matters
because `SOFT TARGET (goal: …; keep near … if free)` is a literal string the RA
writes and the Design Engineer matches against — round 2's R3 kept it in the
DE's prompt for exactly that reason.

**D1 — the move.** Both notes ask for it from opposite ends. Move
`## The three states of a user value — LOCKED, SOFT TARGET, or FREE` +
`$value_states` from between *When to stop* and *Per-claim verification* to
immediately **before** `### 1. QUANTITATIVE INPUTS`.

**D2 — and therefore the rephrase, not the deletion.** The owner's note was
explicit that this was undecided: *"I don't know whether to remove it entirely
or just rephrase it accordingly to mention explicit user values provided."*

Every RED span in the fragment anchors a state to a **QUANTITATIVE INPUTS
section the RA has not yet been told to write**. That reads fine where the
block sits today, after §1. Move it above §1 and every one becomes a forward
reference. The problem is the ANCHOR, not the recogniser — so re-anchor them on
what the user said.

**Edit 1** — `value_states_requirements_analyst_3agents.md`, replacing L1-14:

    Every value the user could have given is in exactly one of three states.
    Decide the state from what the user actually said:

    - **LOCKED** — the user stated the value plainly and attached no goal to
      it.  The user fixed it.  LOCKED is not an absolute wall: it may change
      when an authorisation frees it.
    - **SOFT TARGET** — the user gave the value but subordinated it to a
      qualitative goal, so it is neither locked nor free.  **The goal
      governs**: that subordination IS the authorisation to move the value
      (within range) as far as the goal requires, and it never has to be
      justified.  The stated value is a reference, not a pull — it settles the
      parameter only when the goal does NOT bear on it.
    - **FREE** — the user said nothing that fixes it: it is the system's
      choice within range.

**U2 — the duplication the move exposes.** The SOFT TARGET rule is stated
twice; after D1 the copies land ~30 lines apart, both containing the words
*"The goal governs"*. The overlap is exactly one sentence, and it is the
SEMANTICS, which the block above now owns. What §1 uniquely carries is how to
RECOGNISE and RECORD one — the example phrasing, the marker format, the
strength rule.

**Edit 2** — `requirements_analyst/prompt_3agents.md` L108-111:

```diff
       - Radius of propeller: ~75 mm — SOFT TARGET (goal: match the sketched
         blade shape; keep near 75 mm if free, but vary freely to fit the
         shape)
 
-  The goal governs; the number is only the fallback where the goal does not
-  bear on the parameter.  Read the strength from the user's own wording
+  Read the strength from the user's own wording
   ("not as important" → fully expendable; unspecified → "keep reasonably
   close if free").
```

−1 line, and a clean division of labour: the block says what the state MEANS,
§1 says how to SPOT and WRITE it.

---

### R6 — Per-claim verification: E1-E4  *(resolves N2, U4)*

**Decision (owner, agreed as proposed, including inverting E4).**

**Edit** — `requirements_analyst/prompt_3agents.md` L252-266:

```diff
-Your job: does the Design Engineer's rendered OUTPUT match what the in-scope
-source(s) — the user's raw inputs — ask
-for?  You do NOT re-check parameters (the chain already did) — take its
-stated values as given.  Don't approve on coarse similarity alone:
-enumerate the checkable claims the source encodes and check each against
-the RENDER, deciding the outcome:
+Your job when a render is produced: does the Design Engineer's rendered
+OUTPUT match what the in-scope source(s) — the user's raw inputs — ask for?
+Do not re-check the parameter VALUES — take the Design Engineer's stated
+values as given and judge the RENDER.  Don't approve on coarse similarity
+alone: enumerate the checkable claims and check each against the RENDER,
+deciding the outcome:

     State the claim, what the render shows, and whether they agree —
-    specific, both sides quoted, not a one-word verdict.  For counts,
-    count in the RENDER only and compare with the source's expected
-    count — count them one by one, traversing every instance once, never
-    from a glance.
+    specific, both sides quoted, not a one-word verdict.  For counts, count
+    in the RENDER only and compare with what the source leads you to expect.
```

**N2 — E2's rule kept, its reason dropped.** The sentence was half right and
half stale. The RULE is the only one of its kind: nothing else in the RA's
prompt scopes it away from parameter auditing, and after **R1** it will not
even hold the ranges to audit against. The REASON — *"the chain already did"* —
described the 7-agent topology, where the DC Input Inspector ran an independent
parameter audit; topology 3 has no such agent, and round 2 removed the last of
that text from the Design Engineer. Deleting the sentence outright would have
taken a true rule out along with a false justification.

**U4 — E4 inverted, and this is the point.** The RED covered
*"count in the RENDER only and compare with the source's expected count —"*,
leaving *"count them one by one, traversing every instance once, never from a
glance."*  But the surviving clause is **the duplicate**: verbatim identical to
§1 L90-91 in *Count countable features*. The clause marked for deletion is the
unique one — the only text distinguishing the RA's two counting jobs (§1 counts
what the USER'S DRAWING shows; here it counts what the RENDER shows, and
compares). So the halves are swapped: the echo goes, the distinction stays.

*(`the source's expected count` → `what the source leads you to expect`: the
source is a sketch, not a table, and rarely states a count outright.)*

---

### R7 — two single-line wording items  *(resolves N1/B4, U1)*

**N1 / B4 — `One coherent paragraph —` was factually wrong, not just terse.**
§3 is a paragraph PLUS a bullet (`PRECISION DEMAND`) PLUS a mandatory closing
line (`INTERPRETATION:`) — the prompt contradicts the phrase twelve lines
later. But deleting it outright leaves §3 the only one of the three sections
with no shape guidance (§1 has a list format, §2 says *"Free-form prose"*).

**Decision (owner):** make it true rather than delete it.

```diff
 ### 3. DESIGN INTENT
 
-One coherent paragraph — the CURRENT intent, not a log: purpose,
+Continuous prose, not a log — the CURRENT intent: purpose,
 performance goals, constraints, aesthetics, reporting preferences ("don't
 report back until viable"), and prior-attempt context only where it still
 shapes the design.  Also state, when present:
```

±0 lines. *Prose, not a log* was the half doing work — it stops §3 becoming a
chronology. The paragraph COUNT was the half that was wrong. (`Also state
here,` → `Also state,` is **B5**, unchanged.)

**U1 — the second `stated functional requirements`.** **A1** changes the
Your-Role copy (carried by **R2**); the phrase appears twice, and the other is
the label the RA actually emits, so it is the one downstream reads.

```diff
-DESIGN INTENT COMPLIANCE: <does the geometry match the stated functional
-requirements?  You can't precisely measure dimensions, but you can judge
-overall shape, proportions, and feature counts>
+DESIGN INTENT COMPLIANCE: <does the geometry match what the user is
+requesting for?  You can't precisely measure dimensions, but you can judge
+overall shape, proportions, and feature counts>
```

---

### R8 — `### Tool-use hard rules` printed twice  *(resolves P1)*

Not marked by the owner — the last of the RA's Stage-4 seams in the constraints
area, and the tidiest case in the round: **copy 1 is a strict subset of copy
2**, so unlike §F this is a choice, not a union.

**Edit** — `agents/3agent/tools_config/hard_constraints_tools_requirements_analyst_3agents.md`,
delete L1-4:

```diff
-### Tool-use hard rules
-- DON'T invent or guess a path.  Every path you hand a tool must trace to
-  your incoming message or to a tool result.
-
 ### Tool-use hard rules
 - DON'T invent or guess a path.  Every path you hand a tool must trace to
   your incoming message or to a tool result.
 - DO route EVERY arithmetic operation through the ``calculate`` tool —
   never mental arithmetic, even for trivial sums.
```

−4 lines. The RA's counterpart of the duplicate DOs/DON'Ts and Domain-hard-rules
blocks round 2 removed from the Design Engineer (§K there).

**Verified before ruling, not assumed:** the surviving copy is not merely
longer, it is the correct one — `calculate` IS bound to the RA. From
`dump3.json`, the RA's 7 tools with RAG off:

    read_user_inputs, read_attempts, calculate, view_images,
    reread_text_regions, call_design_engineer, call_planner

so the rule the second copy adds governs a tool the agent actually holds.

---

### R9 — `### Filled-in templates and forms` printed twice  *(resolves U3)*

The RA's last Stage-4 seam. `sketch_handling_requirements_analyst_3agents.md`
carries the section at L4-11 and again at L44-51. The two differ by **one
clause**:

    L7  (copy 1)   only the marks added on top (darker, handwritten, irregular) are input.
    L47 (copy 2)   only the marks added on top are input.

Everything else is word-for-word identical, so **copy 1 is the superset** — it
keeps the three cues that tell a vision agent how to tell a user's mark from
printed scaffolding, which is the section's whole job.

**Edit** — delete L43-51 (copy 2 and its preceding blank). 51 lines → 42.

Note this runs the OPPOSITE way from R1: there the RED covered the copy that
was better in one respect, so the halves had to be merged; here the earlier
copy is better in the only respect the two differ, so the later one simply
goes.

Position is right as well: the surviving copy sits in the User-Input-Inspector
half, BEFORE `### Judging a sketch's precision` — the RA learns how to read a
form before it judges how precise the drawing is.

---

### R10 — the REQUIRED side-by-side call cannot hold what it is told to load  *(resolves P3)*

**Problem.** The precision loop (L208-216) tells the RA to load, in ONE
`view_images` call with `side_by_side=True`, *"the current render (from the
``Render images:`` paths) together with the user's image(s)"*, and calls the
comparison REQUIRED. A 3D phase supplies THREE render views plus at least one
user image. `agents/shared/user_inputs_tool.py:937-940`:

    if side_by_side and resolved:
        # Merge up to 3 (cropped) panels into ONE labelled composite image.
        pil_panels, labels = [], []
        for j, r in enumerate(resolved[:3]):

`resolved[:3]` keeps three and **silently drops the rest** — no error, nothing
in the returned summary. The RA performs a comparison it is told is mandatory
and is never told part of it did not arrive.

**Decision (owner).** Fix both ends; the prompt now, the tool as a prerequisite.

**Edit (this round)** — `requirements_analyst/prompt_3agents.md` L208-214:

```diff
 - **(If user images are present) Compare the render against the user's
   image(s), side by side.**  In ONE ``view_images`` call with
-  ``side_by_side=True``, load the current render (from the ``Render images:``
-  paths) together with the user's image(s) cropped to the region where
-  precision is seeked — pick a COARSE crop box around that region
+  ``side_by_side=True``, load the ONE render view that best shows the feature
+  under discussion (from the ``Render images:`` paths) together with the
+  user's image(s) cropped to the region where precision is seeked — the tool
+  merges at most THREE panels, so choose them.  Pick a COARSE crop box
   yourself and pass it as ``crop_regions`` (coarse is fine; if you cannot
   isolate a region, view the image whole).
```

±0 lines. The RA is told the cap exists AND how to spend it: one render view,
not all three, because the user's sketch is the ground truth and the comparison
is per-feature.

**CODE PREREQUISITE C1 — not part of this round.**
`agents/shared/user_inputs_tool.py` must say when it drops panels. Append to
the summary it already returns, e.g.

    side_by_side: merged 3 of 5 panels; 2 were dropped (<name>, <name>).
    Call again with a narrower selection to see them.

Silence is the defect; the cap itself is reasonable.

---

### R11 — the Design Engineer has never heard of PRECISION REFINE  *(resolves P6)*

Counted in the assembled prompts:

| string | RA | DE |
|---|---:|---:|
| `PRECISION REFINE` | 3 | **0** |
| `refine` | many | **0** |

The RA is told (L220-224) to *"hand your gap description back with
``call_design_engineer``, clearly marked as a PRECISION REFINE — still
iterating, not a blocker"*. The DE's only section for acting on a prose gap
description is `## Acting on a Planner qualitative directive (HARD)`, scoped to
**the Planner as sender** — and its second valid response is *hand back*, which
is exactly what breaks the loop the RA is told to keep turning.

**Decision (owner).** Fix the DE's prompt; the RA's wording is correct and R3
just made the RA→DE edge explicit.

**Edit** — `agents/3agent/design_engineer/prompt_3agents.md` L156-160:

```diff
-## Acting on a Planner qualitative directive (HARD)
-When the Planner hands you a qualitative recovery
-directive — a description of a problem to address (a quality
-issue, a structural defect, a behavioural deficiency, a
-proportion mismatch, etc.) — you have exactly TWO valid responses:
+## Acting on a qualitative directive (HARD)
+When the Planner hands you a qualitative recovery directive, or the
+Requirements Analyst hands you a PRECISION REFINE gap description — a
+description of a problem to address (a quality issue, a structural defect, a
+behavioural deficiency, a proportion mismatch, etc.) — you have exactly TWO
+valid responses:
```

±0 lines net. Both senders named, the same two responses apply.

⚠ This edits the **Design Engineer's** prompt, outside the scope the owner set
for round 3. Taken deliberately, because the loop is live and the RA half of it
is already written.

---

### R12 — `Input directory:` must survive the RA↔DE refine loop  *(resolves P7)*

Counted in the assembled prompts: `Input directory` appears **1×** in the
Planner (*"Every ``call_requirements_analyst`` AND ``call_design_engineer``
message MUST carry this line verbatim"*) and **0×** in both the RA and the DE.
Both agents' `read_user_inputs` schemas point at it:

    RA:  … supplied in your hand-off under the ``Input directory:`` label, or
         named in your comparison-source instructions (do NOT guess a path).
    DE:  … supplied in your hand-off under the ``Input directory:`` label
         (do NOT guess a path).

The precision refine loop is exactly the leg the Planner is NOT on — RA → DE →
RA, round after round — and neither agent is told to carry the label forward.

**Correction to the §P entry.** I filed this 🟠 as a hard break; it is 🟡. The
Planner's original message is still in each agent's own history, so the path is
recoverable — it simply is not where the schema says to look, and the schema
says *"do NOT guess"*. The realistic failure is an agent that declines to
re-read, not one that crashes.

**Decision (owner): Option A — carry the label forward**, rather than softening
the schemas. Three reasons:

1. it keeps the *"do NOT guess a path"* guard intact, which exists because path
   invention is a real failure mode here;
2. it preserves the invariant the rest of the system runs on — the incoming
   message is self-sufficient (cf. the Receptionist's *"does NOT scan the
   filesystem — it reports from THIS message"*);
3. softening would tell the agent to reach back to *"the earlier message that
   established it"* — the same stale-history reach the RA has a HARD RULE
   against for images. Teaching the opposite habit for paths, in one prompt, is
   how a cycle-3 render gets compared against a cycle-1 path.

**Edit 1** — the RA's `call_design_engineer` bullet (as rewritten in R3):

```diff
   missing data, or contains an error the Design Engineer can fix.
+  Carry the ``Input directory:`` line from your own incoming hand-off into
+  every message you send, so it survives rounds the Planner is not on.
```

**Edit 2** — the DE's `## Hand-off to the next agent (IMPORTANT)`, after the
three-label block (kept separate so the *"copied verbatim from THIS cycle's
tool return texts"* provenance rule stays accurate — the input directory does
not come from a tool return):

```diff
     Render images:
       <absolute path of each render image, one per line>
 
+Carry the ``Input directory:`` line from your own incoming hand-off too, so it
+survives rounds the Planner is not on.
+
 Beyond those lines, write whatever prose is genuinely useful to
```

+4 lines total. The label now propagates ALONG the loop the way the Planner
already propagates it INTO the loop.

⚠ Edit 2 touches the **Design Engineer's** prompt — the second deliberate
out-of-scope edit this round, after R11.

---

### R13 — the Planner's roster contradicts the Planner's own Role 3  *(resolves P8)*

**The roster** (`available_agents_planner_3agents.md` L8-12) — *"performs a
qualitative visual analysis, **calling you to approve the design or to flag
defects and problems**"*.

**Role 3, thirty lines later in the same prompt** (L243-245) — *"The
Requirements Analyst routes back to you when a design cycle FINISHES — not
after every verdict; **a mid-loop REVISE goes straight back to the Design
Engineer**."*

The RA agrees with Role 3: after R3 its `call_design_engineer` bullet owns
REVISE and PRECISION REFINE, and `call_planner` gets APPROVE, interpretation
divergence and blockers. The roster is stale — it describes the 5-agent DC
Output Inspector, which reported every verdict to the hub. It survived round
2's §A merge because I merged the two RA bullets faithfully without re-checking
that claim against Role 3.

**Why it matters more than it looks.** The roster is what the Planner reads to
decide whether a return from the RA is EXPECTED. Told it gets defects, a
Planner hearing nothing during a long refine loop has grounds to think
something stalled — and Role 3, which would correct it, is the section it
reaches only once a cycle has finished.

**Decision (owner), with the owner's rephrase.**

```diff
   extracts design values, intent, and constraints.  It also loads the
   rendered PNGs using the paths supplied by the Design Engineer and
-  performs a qualitative visual analysis, calling you to approve the
-  design or to flag defects and problems.  Cannot measure precise
-  dimensions; comments on overall shape, proportions, and feature count.
+  performs a qualitative visual analysis, calling you when a cycle FINISHES
+  — to approve, or to flag an upstream interpretation problem.  A mid-loop
+  REVISE goes straight back to the Design Engineer.  Cannot measure precise
+  dimensions; comments on overall shape, proportions, and feature count.
```

±0 lines. Roster, Role 3 and the RA's routing now agree.

**On the wording.** My draft read *"A mid-loop REVISE it sends straight to the
Design Engineer"* — object-fronted, which garden-paths the reader into parsing
*"REVISE it"* as a unit. The owner proposed the passive, *"is sent straight
to"*, which is clearly better. Settled one step further on Role 3's own phrase,
*"goes straight back to"*: it avoids both the garden path and the passive, and
since the entire point of the edit is to make the two statements agree, they
now agree verbatim.

⚠ The **Planner's** file — the third deliberate out-of-scope edit this round,
after R11 and R12. It is also a correction to my own round-2 merge, not to the
owner's mark-up.

---

### R14 — two RA output labels nobody is told to read  *(closes P9 — kept, and filed)*

`QUALITATIVE DESCRIPTIONS` and the mandatory `INTERPRETATION:` line appear in
**no other agent's assembled prompt**, while every other label the RA emits
does:

| label the RA emits | Planner | Design Engineer |
|---|---|---|
| `QUANTITATIVE INPUTS` | — | ✅ |
| `DESIGN INTENT` | ✅ | ✅ |
| `PRECISION DEMAND` | ✅ | — |
| `PRECISE SKETCH` | ✅ | — |
| **`QUALITATIVE DESCRIPTIONS`** | ❌ | ❌ |
| **`INTERPRETATION:`** | ❌ | ❌ |

**Decision (owner): keep both, and file it permanently.**

I filed P9 as dead weight — *"the cheapest thing to cut if the sentence cap is
ever to be honoured."* Two things changed while writing it up:

* **R3 deleted that cap**, so the pressure that made cutting attractive is gone;
* the two labels are **not symmetric**. `INTERPRETATION:` is a SELF-CHECK — its
  value, forcing the RA to distinguish *"I found no ambiguity"* from *"I did
  not look"*, is realised in the RA's own output discipline whether or not a
  recipient keys off it. And `QUALITATIVE DESCRIPTIONS` is a section §1's count
  rule routes conflicts INTO (*"use yours and record both in QUALITATIVE
  DESCRIPTIONS"*), so cutting the label orphans that instruction.

The useful move is the REVERSE of cutting — teach the Planner to act on them —
but that is new capability, not defect repair, and belongs in a Planner round.

**Filed as `F96` in `extra_utilities/TODO_known_issues.md`**, at the owner's
request, so it can be re-opened if the test runs show the RA's reports being
ignored or its ambiguity flags going nowhere. The entry records what the proper
fix would look like (Planner Role 1 acting on `INTERPRETATION: ambiguous`;
`QUALITATIVE DESCRIPTIONS` feeding the standing directive's wording).

---

---
---

# Step-2 tracker

**All items are resolved.** Each decision is recorded in §R above.

| id | topic | status | your decision |
|---|---|---|---|
| ~~X1~~ | `## Your Role` reads 1. then 3. | **solved → R2** | move the gated item last |
| ~~X2~~ | two output formats, no rule for which is when | **solved → R4** | name the two situations |
| ~~X3 / N3 / F1~~ | the ranges setting is defeated; which copy to keep | **solved → R1** | union: one list, ranges gated |
| ~~X4~~ | CLARIFY has two targets | **solved → R3** | split by who can fix it |
| ~~X5 / G3~~ | `call_design_engineer` twice, disjoint conditions | **solved → R3** | one bullet |
| ~~N1 / B4~~ | `One coherent paragraph —` | **solved → R7** | `Continuous prose, not a log` |
| ~~N2 / E2~~ | the "do not re-check parameters" boundary | **solved → R6** | keep the rule, drop the false reason |
| ~~N4 / G1~~ | out-of-scope and missing-file hand-backs | **solved → R3** | folded into `call_planner` |
| ~~U1~~ | `stated functional requirements` ×2 | **solved → R7** | align the Output-Format copy with A1 |
| ~~U2~~ | the SOFT TARGET rule ×2 | **solved → R5** | block = meaning, §1 = recording |
| ~~U3~~ | `Filled-in templates and forms` ×2 | **solved → R9** | keep copy 1 (has the three cues) |
| ~~U4~~ | `count them one by one …` ×2 | **solved → R6** | E4 inverted: the echo goes, not the distinction |
| ~~Q1~~ | "LOCKER / SOFT LOCKED" — typo, or a rename? | **solved → R5** | owner confirms: typo, no rename |
| ~~D1~~ | the value-states MOVE | **solved → R5** | above `### 1. QUANTITATIVE INPUTS` |
| ~~D2~~ | rephrase-vs-delete inside the value-states fragment | **solved → R5** | rephrase, re-anchored on the user |
| ~~G4~~ | move the `call_*` bullets under ROUTING | **solved → R3** | |
| ~~P1~~ | `Tool-use hard rules` printed twice | **solved → R8** | copy 1 is a strict subset; delete it |
| ~~P2 / G2~~ | the one-or-two-sentence cap vs the whole extraction | **solved → R3** | the cap is deleted |
| ~~P3~~ | `side_by_side` silently drops the 4th image | **solved → R10** | prompt now; tool logging as prerequisite **C1** |
| ~~P4~~ | the no-renders fallback names the deleted QC report | **solved → R2** | name the hand-off instead |
| ~~P5 / N4~~ | no `call_planner` condition matches an extraction turn | **solved → R3** | inputs-only turn named first |
| ~~P6~~ | the DE has never heard of PRECISION REFINE | **solved → R11** | broaden the DE's directive section (out-of-scope edit, agreed) |
| ~~P7~~ | `Input directory:` is not carried on the RA-DE refine loop | **solved → R12** | Option A: both agents carry it forward |
| ~~P8~~ | the Planner roster vs Role 3 on where defects go | **solved → R13** | roster now echoes Role 3 verbatim |
| ~~P9~~ | QUALITATIVE DESCRIPTIONS / INTERPRETATION read by nobody | **kept as is → R14** | filed as `F96` for the test runs |

---
---

# §Z — the application

Applied 2026-09-12 in worktree `rebuild-3-agent-topology-6ca792`, branch
`claude/rebuild-3-agent-topology-6ca792`. One pass, 19 substitutions across
8 files, every one asserting its anchor text AND its uniqueness before running.

| file | lines |
|---|---|
| `dc_config/parameters_requirements_analyst_3agents.md` | 57 → 30 |
| `requirements_analyst/prompt_3agents.md` | 391 → 401 |
| `prompt_fragments/value_states_requirements_analyst_3agents.md` | 14 → 14 |
| `prompt_fragments/routing_requirements_analyst_3agents.md` | 41 → 28 |
| `tools_config/hard_constraints_tools_requirements_analyst_3agents.md` | 9 → 5 |
| `dc_config/user_input_types/sketch_handling_requirements_analyst_3agents.md` | 51 → 42 |
| `design_engineer/prompt_3agents.md` | 317 → 321 |
| `prompt_fragments/available_agents_planner_3agents.md` | 23 → 24 |

## What the prompts became

    topology 7    all 9 prompts BYTE-IDENTICAL
    topology 5    all 7 prompts BYTE-IDENTICAL
    topology 3    receptionist          15 906 -> 15 906   (unchanged)
                  database_handler       22 029 -> 22 029   (unchanged)
                  planner                24 550 -> 24 642   (+92)
                  design_engineer        25 870 -> 26 055   (+185)
                  requirements_analyst   30 924 -> 28 878   (-2 046, -6.6%)

The RA shrinks; the Planner and the DE grow slightly, which is R11, R12 and
R13 — the three deliberate out-of-scope edits that close mechanisms whose RA
half this round rewrote.

## Verification

    topology_prompt_snapshot.py diff      7 and 5 byte-identical, 3 as above
    smoke_test_prompt_tool_audit.py       PASS
    smoke_test_topology3_tool_text.py     PASS
    smoke_test_slot_splices.py            PASS
    smoke_test_hub_attributes.py          PASS
    smoke_test_topology_fragments.py      PASS
    dry_run_topology.py                   ALL PASS - 3 topologies drove a
                                          complete turn end to end

Residue sweep over `agents/3agent/` — **0 files** still contain
`One coherent paragraph`, `Be generous`, `the chain already did`,
`Record one quantitative input per line`,
`Keep the ``message`` to one or two sentences`, or
`stated functional requirements`. Each duplicated heading is now singular:
`### Tool-use hard rules` 1×, `Filled-in templates and forms` 1×,
`### Global / ring` 1× in the RA's parameter fragment.

## The PDF

`3agent_system_prompts_v5.pdf` — **58 pages** (was 59), 1.72 MB, body text
measured at **8.7 pt** with the pypdf `cm[3]` visitor: no Chrome shrink-to-fit.

`SCAFFOLD` now appears **once** in the whole document (p.38) and it is the
legitimate prose *"its printed content … is SCAFFOLDING, not a user choice"* —
R9 removed the duplicate. Every other retired-agent hit is accounted for: pages
2, 4 and 58 are the front matter and the provenance appendix, and pages 23 and
35 are the Design Engineer's and Requirements Analyst's title-page blurbs,
which name their parent agents deliberately.

## Still open, carried forward

* **C1** — `agents/shared/user_inputs_tool.py` must report when `side_by_side`
  drops panels beyond three (R10). Silence is the defect; the cap is fine.
* **F96** — filed in `extra_utilities/TODO_known_issues.md`: the RA's
  `INTERPRETATION:` and `QUALITATIVE DESCRIPTIONS` labels that no agent is told
  to read (R14). Kept deliberately; re-open if the test runs show them going
  nowhere.
* **Round 2's leftover** — `tools/generate_mesh/generate_mesh.py:778`, the
  `parameters_path` schema still pointing at a `Parameters file:` label round 2
  removed from the hand-off. Visible on p.32 of the new PDF. Proposed fix was
  `Parameters file:` → `Current attempt <N>:`; never ruled on.
