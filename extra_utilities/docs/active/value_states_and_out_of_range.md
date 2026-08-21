# Value states & out-of-range handling

*Merged 2026-08-21 from three files that were one subject split three ways.
Nothing was rewritten: each source is reproduced in full below, with its
heading levels shifted down one so the document has a single H1.  The only
added text is this header and the three part banners.*

| Part | Was | Covers |
|---|---|---|
| **A** | `design_no_ask_back_and_range_degrade.md` | The decisions: global no-escalation (D1-D8), the out-of-range 2x2, the degrade-to-soft-target mechanism, the change-surface audit and gaps G1-G8 |
| **B** | `design_soft_targets.md` | The three-state model (LOCKED / SOFT TARGET / FREE) that Part A's degrade lands in, and the literal marker syntax |
| **C** | `analysis_out_of_range_cases.md` | The full case matrix [U-a]-[U-h], the coherence audit, and the authoritative close status for G1-G10 |

**Reading order if you are new to this:** B first (the model), then A (the
decisions built on it), then C (what actually happens in each case today).
Part C is the most current: it carries the 2026-08-01 fixes and is the place to
look for whether a given gap is closed.

**Heads-up on status.** Part A's own header still says "DESIGN AGREED, NOT YET
BUILT". That is only half true -- the Receptionist range-gate removal and
several of the G-items shipped; Part C records which. Trust Part C's close
status over Part A's header.

---

## PART A -- "Don't ask back" (global no-escalation) + out-of-range value degrade

*Source: `design_soft_targets.md`'s sibling `design_no_ask_back_and_range_degrade.md`.
This is the file this document was renamed from, so `git log --follow` resolves
here.*


**Status:** DESIGN AGREED, NOT YET BUILT.  Decisions below were made by the
product owner on 2026-07-28 via explicit multiple-choice sign-off.  Nothing in
this document has been applied to any prompt yet.

**Origin.** Surfaced while rewiring the live 7-agent prompts onto the shared
`$value_states` fragment.  The trigger was **benchmark 6**: the user states a
value that is OUT OF RANGE, asks to keep it, and asks the system NOT to ask
back.  The pipeline had no answer for this — worse, it had a hard gate at the
front door that would violate the directive outright (see "The blocker").

Related: [[v9_soft_targets]] (the three-state model this builds on),
`extra_utilities/docs/archive/agent_count_variants_build_tracker.md` (the rewiring work this
interrupted).

---

> ### ✅ STATUS UPDATE (2026-07-28) — the front-door blocker is GONE, feature shrunk
>
> The owner decided to **remove the Receptionist's out-of-range blocking
> entirely** ("it's easier like this at this point"), independently of this
> feature. Applied: the `## Quantitative viability check` became a
> `## Parameter-name check` — steps 2 (compare to range) and 3 (block) are
> DELETED, along with the "only claim within range if you just ran the check"
> paragraph and the "once all values are in range … proceed" precondition.
> **Kept:** step 1 name-mapping (an unrecognised parameter name still bounces),
> and the no-clip half — *"never silently clip, round, or redistribute a user's
> value: substituting values is not your job"* (D6 gives substitution to the
> DCIC). Added: *"an out-of-range number is NEVER a reason to stop a request at
> the door."* Grep confirmed **no other agent** depended on this gate.
>
> **Consequences for D1–D8:**
> - **The "blocker that started it" (below) no longer exists.** An out-of-range
>   value now always flows into the pipeline.
> - **D4's extraction-only column is SATISFIED already** — such a request now
>   reaches the UII, is extracted as-is, and the Planner replies (it already
>   refuses to hand extraction-only work to the DCIC). This unblocks the
>   owner's **text-only parameter-extraction benchmark tests**, which the gate
>   was silently failing.
> - **D4's geometry+normal cell still asks the user**, just LATER — from the
>   DCII via the Orchestrator instead of at the door. Behaviour preserved.
> - **The feature's Receptionist work shrinks accordingly**: what remains there
>   is the no-ask-back suppression of its OTHER gates (image pairing, off-topic
>   notes, unrecognised names) and D8 disclosure — not the range gate.
>
> ### ✅ G2 — PARTLY WRONG AS ORIGINALLY WRITTEN
> I claimed no agent classifies extraction-only vs geometry. **It does exist:**
> the Receptionist is told to *"mention in your `call_orchestrator` summary that
> this is an extraction-only request (no full design run expected) so the
> Orchestrator can route appropriately"*, and the Planner acts on it —
> *"Extraction-only … the extraction IS the deliverable … Do NOT hand off to the
> DCIC and do not trigger mesh/render work."* What is genuinely missing is only
> the relay of that classification to the **UII**, which needs it for D5.
>
> ### ✅ G5 — RESOLVED (owner insight, 2026-07-28)
> G5 was: the UII is told *"conversion is the DCIC's job"*, so for a 4 cm chord
> against a 30 mm limit it may never convert, never detect the breach, and never
> write the marker — leaving D4's own worked example with no route to a degrade.
> **Resolution: the DCIC must know the degrade rule too, not just the UII.**
> The DCIC is the agent that CONVERTS, so it is the one that DISCOVERS the
> breach in exactly the case the UII cannot. Therefore:
>   * the **UII** marks the degrade when it CAN detect it (unit matches a param);
>   * the **DCIC** applies it when IT discovers the breach after conversion, and
>     documents the substitution in its hand-off;
>   * the **DCII** must accept a documented degrade as authorised, or it flags
>     the resulting move as a VIOLATION;
>   * in the merged **Creator** all three collapse into one agent.
> The authority-based out-of-range phrasing now live in the DCII (escalate only
> when NOTHING authorises the move — marker, hand-off permission, DESIGN INTENT,
> or directive) is what makes this addition clean: once a degrade IS authorised,
> the routing rules already handle it with no further edits.

### The blocker that started it (HISTORICAL — resolved, see status update above)

`agents/receptionist/prompt.md` line ~81 already gates every out-of-range user
value at the front door:

> **If any FAIL, reply directly** (path 2): name each out-of-range parameter
> with its value and range side-by-side (omit in-range ones), ask the user for
> revised in-range values, and do NOT ``call_orchestrator`` this turn.  Never
> silently clip, round, or redistribute an out-of-range value — the user must
> choose the fix.

So benchmark 6 never reaches the pipeline: the Receptionist stops and asks —
exactly what the user forbade.  There was also **no "don't ask back" support
anywhere** in the live prompts (the phrase appears only in
`design_precision_sections_match.md`, for the precision refine loop's autonomous
termination — a different thing).

---

### The decisions (D1–D8) — all FINAL

#### D1. Global no-escalation mode
A user instruction like "do not ask me back" / "don't ask questions" / "proceed
without asking" is a **STANDING directive**: recorded in the extraction's
**DESIGN INTENT** section, valid every cycle **until the user revokes it**
(same lifetime as the existing user authorisations).

It suppresses **ALL user-facing questions pipeline-wide** — the Receptionist's
front-door gates, the DCIC's escalations, the DCII's escalations, the Planner's
escalate-to-user, and the Orchestrator's relaying of any of them.

> Inter-agent CLARIFY is **unaffected** — it never reaches the user.  Only
> user-facing questions are suppressed.

#### D2. It is FULLY global — not just value/range questions
Chosen deliberately over the narrower "value/range only" option.  Even an
**unrecognised parameter name** or an unreadable input — which today bounces
back to the user asking them to restate — must instead get the agents' best
interpretation (or be skipped), and be **disclosed** in the final answer.

*Owner's rationale:* it is what an unattended overnight benchmark run needs to
keep moving, and it is the plain meaning of "don't ask me anything".
*Accepted risk:* the system may guess on genuinely ambiguous input.  D8 is the
mitigation — every guess must be disclosed.

#### D3. The floor — never block, always report
The pipeline **never blocks mid-run**.  It always finishes and produces the best
result it can; the **final answer** states plainly what could not be honoured
and why.  The directive is **NEVER overridden**: a limit is **REPORTED**, never
turned into a question.  (Explicitly chosen over an "override as a last resort"
escape hatch, which would reintroduce the mid-run stall in unattended runs.)

#### D4. Out-of-range user values — the 2×2
The gate fires **only** for a geometry-generating request with **no** no-ask-back
directive:

|                      | **extraction-only request**            | **geometry-generating request**                        |
|----------------------|----------------------------------------|--------------------------------------------------------|
| **normal**           | extract as-is (out of range and all)   | *today's behaviour:* ask the user (the gate fires)      |
| **"don't ask back"** | extract as-is                          | **substitute the best in-range approximation** (D5/D6)  |

- **Extraction-only** = "read my inputs / tell me the parameters" — nothing is
  generated, so an out-of-range value is simply recorded, flagged out of range.
  Nothing is substituted, nothing is blocked.
- **Geometry-generating** = blade-section render, 3D render, mesh — anything the
  generator must consume.  The out-of-range value **cannot** be used, so the
  system substitutes the best in-range equivalent of what the user meant,
  chosen from: the user's request, the other inputs, the design goal, and the
  agent's engineering discretion.
- **Worked example:** the sketch says outer blade chord **4 cm**; the allowed
  max is **30 mm**; the system picks a coherent in-range value instead.

#### D5. The substitution is modelled as a DEGRADE TO SOFT TARGET
The out-of-range LOCKED value **degrades into a SOFT TARGET**, using the
**existing `SOFT TARGET` marker** (no new state, no new token), with a goal that
names the origin:

```
- outerChord: 40 mm — OUT OF RANGE (allowed max 30); SOFT TARGET (goal:
  honour the user's 40 mm as closely as the range allows)
```

This reuses every piece of machinery already built: the DCIC seeds near and
moves within range, the DCII does not flag the deviation, the DCOI judges it
against its goal rather than the number, and the Planner counts it as an
available lever rather than a locked value.

**⚠ This requires AMENDING a live UII rule.**
`agents/user_input_inspector/prompt.md` ~line 242 currently says:

> Use a soft target ONLY when the user themselves subordinated the value to a
> goal — a value stated plainly with no such subordination stays a normal
> (locked) QUANTITATIVE INPUT.

D5 creates the **one sanctioned system-authored exception** to that rule.  The
amendment must be narrow: out-of-range + geometry-generating request only.

#### D6. Who substitutes
**The DC Input Creator chooses the in-range number** — it is the only agent that
authors concrete values — and **documents the substitution in its hand-off**.
**The DC Input Inspector verifies** it is in range and coherent with the user's
intent.  **The Planner stays qualitative-only**, consistent with its HARD RULE 7
(never invent numeric values).

#### D7. Insistence counts as authorisation
If the system **did** ask about an out-of-range value (no directive was in
force) and the user **insists on keeping it**, the same degrade + substitution +
disclosure applies.  Asking again is pointless and geometry still cannot accept
the number — being told and still insisting **is** the authorisation.  One rule
covers both routes into the situation.

#### D8. Disclosure is mandatory
Whenever a user's number was **not honoured**, or an input was **guessed at or
skipped**, the **final answer to the user must say so concretely** — name the
parameter, the user's value, the value actually used, and why.  This is the
mitigation for the risk D2 accepts.

---

### Consequences already identified

- **Supersedes the pending "P2" edit.**  The earlier proposal (a soft-target
  out-of-range value CLARIFYs to the DCIC instead of escalating to the user)
  is still correct but INCOMPLETE — it must be extended with the D4/D5 degrade
  case.  Do not apply the old P2 wording as-is.
- **The Receptionist is the biggest change surface**: it owns the front-door
  gates (out-of-range AND unrecognised-name), the permission-to-vary block, and
  the final-answer delivery where D8's disclosure must land.
- **The UII gains two new jobs**: recording the standing no-ask-back directive
  in DESIGN INTENT, and applying the D5 degrade marker (it already carries
  `$parameter_list` with the ranges, so it CAN detect out-of-range).
- **Routing verdicts need re-checking**: several agents' `ESCALATE` verdicts
  exist specifically to reach the user.  Under D1 those need a defined
  destination or a defined suppression.

---

## CHANGE-SURFACE AUDIT (2026-07-28) — 10-agent map + design critic

**Scale: 95 sites must change**, across every agent except the Tool Caller:
Receptionist 16, Planner 16, DCIC 15, UII 12, Orchestrator 6, DCII 5, DCOI 4,
fragments 21, Tool Caller 0.

### ⛔ Blockers found (each VERIFIED against the code by hand)

**B1 — A DCII↔DCIC livelock where every exit is an escalation.**  If the UII
does not emit the D5 marker, the DCII reads `outerChord: 40 mm` unmarked
(= LOCKED) vs `parameters.json` = 30 → VIOLATION → CLARIFY to the DCIC.  The
DCIC obeys "write a LOCKED value verbatim" → writes 40 → DCII §1 out-of-range →
must not approve → ESCALATE, which D1 has disarmed.  Next lap the DCIC's
"forbidden: a no-op write … or skip the write and ESCALATE" also ends in an
escalation.  **Removing the escalate exits without a replacement terminal turns
this into a 200-hop burn** (`MAX_DISPATCH_HOPS = 200`, verified).

**B2 — Two CODE-level blockers; prompt edits cannot fix them.**
  (a) `agents/user_input_inspector/user_input_inspector.py:352-357` injects into
      the `read_user_inputs` TOOL RESULT: *"WARNING: image+note pairing is
      INVALID.  The Receptionist should have caught this — ESCALATE so the user
      can be asked to fix the uploads."*  Unreachable today only because the
      Receptionist gates; D1 makes it reachable and it issues the forbidden
      instruction from a channel the prompt cannot override.  VERIFIED verbatim.
  (b) There is **NO code-level range check anywhere**: `write_parameters`
      validates key set + numeric-ness only (VERIFIED).  So D4's "the
      out-of-range value CANNOT be used" is enforced purely by prose — in the
      DCII, which the DCIC skips ~2 rounds in 3 on precision jobs, and which
      does not exist at all in the `DCII_OFF` build.

**B3 — D5's "reuses all existing soft-target machinery" is FALSE in 1 of 3
shipped DCOI configurations.**  `_COMPARISON_MODE_1` says *"Do NOT read
``extracted_inputs.txt`` in this mode"* (VERIFIED).  The DCOI's soft-target
carve-out is conditioned on *"when the SOURCE marks a value SOFT TARGET"* — in
mode 1 the source is the sketch saying "4 cm", which carries no marker.  The
carve-out can never fire, and the DCOI's override-authority rule then reads the
substitution as an upstream misinterpretation and escalates.

**B4 — D8's disclosure has no legal path to the user.**  Three independent rules
block it: the Receptionist's *"Every value/path you state must come from a
``read_attempt`` result or an attached block"* (the user's original 40 mm is in
neither); the Orchestrator's hand-off spec, which does not require substitution
facts; and the DCOI's *"do NOT repeat raw data … verbatim"*, which drops the
facts two hops before the agent that authors the user-facing summary.  Also the
Receptionist has **zero** soft-target vocabulary (VERIFIED: 0 occurrences of
`SOFT TARGET` / `$value_states`) — it has no word for "a value you supplied that
the system moved".

### ⚠ Design gaps D1–D8 do NOT answer

- **G1 — RESOLVED 2026-07-28: DISCRETION WINS.**  The conflict was: D4 says the
  substitute is the best approximation using *engineering discretion* (could be
  28 mm with a rebalanced ring); D5's goal text said *"as closely as the range
  allows"* (= 30).  **Owner's decision: best coherent design — the DCIC may
  depart from the boundary value when the design goal calls for it.**
  Consequences, all accepted:
    * D5's mandated goal wording must change from "as closely as the **range**
      allows" to "as closely as the **design** allows" — otherwise the marker
      itself re-imposes the boundary rule that was just overruled.
    * `$value_states`' default for a MISSING strength clause is *maximum
      freedom*, which is now CONSISTENT with discretion-wins — so the degrade
      marker should carry **no** "keep near … if free" clause.  (Had the owner
      chosen closest-to-the-number, the fragment would have needed a new
      minimum-deviation default.)
    * The DCII can no longer verify the substitution against a single expected
      number — it must judge the **rationale**.  **REUSE, do not invent:** the
      DCII already has exactly this machinery in §4b for real-world quantities
      — *"A stated engineering-judgement choice … Judge whether the rationale is
      plausible and the resulting parameter values are broadly consistent with
      the user's intent."*  The degrade check should be written as another
      instance of that route, which also means the DCIC must state its reason.
    * The DCOI loses the ability to detect a bad substitution by number alone
      (it judges the value against its goal, and any in-range value satisfies a
      discretionary goal).  Accepted; D8 disclosure is the backstop.
- **G2.**  The extraction-only-vs-geometry classification lives at the *Planner*,
  which in the default UII-first build runs AFTER the UII — so D5 makes the
  UII's output depend on a classification it does not have.
- **G3.**  The MIXED request ("tell me the dimensions AND render it") needs the
  value recorded as-is AND degraded, from one file with only three sections.
- **G4.**  An extraction-only turn POISONS the next geometry turn: the
  Orchestrator may skip a UII rewrite ("repeats … do not require a UII rewrite"),
  so the bare unmarked 40 flows into the build turn.
- **G5.**  Who detects out-of-range for a UNIT-MISMATCHED value?  The UII is told
  *"conversion is the DCIC's job"* (VERIFIED, prompt:33-36), so it may never
  convert 4 cm → 40 mm and therefore cannot compare it to a mm range — while the
  DCIC, which does convert, cannot write the extraction.  **D4's own worked
  example may have no route to a marker at all.**
- **G6.**  D7's insistence is not durable: the system's outgoing question is
  never written to `user_query.txt`, and there is no pending-question state, so
  the UII cannot tell "we asked and they refused" from a first statement.
- **G7.**  "start over" / "fresh design" DISCARDS prior context — does it revoke
  the standing directive?  If yes, gates silently switch back on mid-session.
- **G8.**  D3 has no positively-specified terminal.  The only mechanical stop
  emits *"halted before completion … likely a coordination bug"* naming no
  attempt and no values — neither a result (D3) nor a disclosure (D8).

### Build ORDER (dependency-forced, from the critic)

1. **`value_states.md`** — safe alone; must define the system-authored origin
   AND a degrade strength default before any agent can reference it.
2. **UII** — the ONLY-rule, ranges into scope, DESIGN INTENT recording.  Safe
   before the DCII, because an early marker is handled correctly by the
   unmodified DCII.
3. **DCII** — ⚠ **unsafe alone or early.**  Relaxing "user-provided
   out-of-range ESCALATES" before the UII emits the degrade removes the ONLY
   range enforcement in the system (see B2b) and ships out-of-range values
   straight to the geometry backend.  **Never before the UII.**
4. **DCIC** — the substitution author.
5. **Receptionist gate + Orchestrator/Planner terminals — MUST BE ONE COMMIT.**
   Suppressing the gate without the terminals leaves the only exits as
   escalations with no destination (→ B1).  Deleting the escalations without a
   replacement removes the pipeline's only loop-breaker.
6. **Code:** the UII `.py` warning (B2a) + a Receptionist directive signal
   (it gets no banner telling it a no-escalation directive is in force, and on
   cycle 1 its gates run before the UII has seen the message) + upgrading
   `_surface_limit_to_user` to carry the best attempt, since it becomes the
   de-facto terminal.

### One thing to REUSE rather than reinvent

`$value_states` authorisation source **(B)** — *"the extraction's DESIGN INTENT
section records one … standing every cycle until revoked"* — is EXACTLY D1's
persistence mechanism, already defined and already read by the DCIC, DCII and
Planner.  D1's standing directive should be written as an instance of (B), not
as a new mechanism.  (NOT to be confused with the Planner's
`=== STANDING DIRECTIVES ===` hand-off block, which only the Planner may set.)
The UII also already has a **"Reporting preferences"** slot in DESIGN INTENT
(e.g. *"do not report back until a viable solution is found"*) — the natural
home for the no-ask-back directive.

### Open items (to resolve during the build)

- G1–G8 above, each needing a product decision.
- Whether `$value_states` itself should mention the degrade, or whether it stays
  purely user-authored and the degrade is explained where it is created (UII).

---

## PART B -- Soft targets: provided values subordinate to a qualitative goal

*Source: `extra_utilities/design_soft_targets.md`, reproduced in full.
This is the model Part A's D5 "degrade to soft target" lands in.*

## Soft targets — provided values subordinate to a qualitative goal

**Problem.** The prompts treat any user-provided number as LOCKED-by-default,
with the only escape a free-prose "authorisation" in DESIGN INTENT. That
capture is fragile (it misfired in the precision-sections production runs),
and it can't crisply express **benchmark 7**: *"here are dimensions, but fit
the sketched shape — the exact dimensions are not as important."* There is no
first-class notion of a provided value that is a **soft target**: honoured
when free, but sacrificed to serve a goal when they conflict.

### The concept (DECIDED 2026-07-26)
Three states for a user-provided value, not two:
- **LOCKED** (default) — a hard constraint; never change without authorisation.
- **SOFT TARGET** — provided, but explicitly subordinate to a NAMED qualitative
  goal.  **The goal dominates:** vary the value freely to serve the goal when
  they conflict.  It also records a **keep-close-if-free** strength — how near
  to hold the value when there is slack (so "shape wins, but stay near 140 mm
  if you can" is expressible).  Recorded together with the goal it serves.
- **FREE** — the user expressed no value/preference; the system chooses within
  range.

So a soft target = "match if free, sacrifice to the goal on conflict, stay as
close as the keep-close strength asks when there's room."

### Where it touches the prompts (full 7-agent system FIRST)
1. **UII** (`agents/user_input_inspector/prompt.md`) — RECORD a soft target
   (value + goal + keep-close strength) in a standardized, recognizable form,
   distinct from a LOCKED QUANTITATIVE INPUT and from a free-prose note.
   Extend the "Sketch handling" precise-drawing case so a dimensioned sketch
   the user de-prioritises becomes soft targets, not locked values.
2. **Planner HARD RULE 8** (`agents/planner/prompt.md`) — the locked-vs-free
   model gains the SOFT TARGET third case + its semantics (goal dominates;
   keep close if free); directives naming a soft-target change rest on the
   goal, not on a fresh authorisation.
3. **DC Input Creator** (`agents/dc_input_creator/prompt.md`) — treat a soft
   target as a start-near-it reference it SHOULD move to serve the goal, not a
   value to reproduce.
4. **DC Input Inspector** (`agents/dc_input_inspector/prompt.md`) — do NOT flag
   a soft-target deviation as a violation; it is authorised by construction.
5. **DC Output Inspector** — already shape-focused (cannot measure precise
   dimensions), so likely little/no change; verify it doesn't punish a
   soft-target deviation.

### Order
1. **Full 7-agent system** (live prompts) — ✅ DONE (2026-07-26). Edits:
   UII (§1 SOFT TARGET marker convention + Q1 UI-pin-softening rule; §3
   authorisation bullet; `sketch_handling.md` precise-sketch bullet);
   Planner HARD RULE 8 (third case) + HARD RULE 9 (soft target = available
   lever, excluded from the locked count); DCIC ("Soft targets are NOT
   locked" case); DCII (a `SOFT TARGET` marker authorises the move — do not
   flag its deviation); DCOI ("a SOFT TARGET is not a claim to enforce —
   judge it vs its goal"); Orchestrator (relay-authorisations bullet names
   soft targets). Receptionist unchanged (does not handle parameter values).
2. **5-agent** drafts — **Conductor DONE** (2026-07-26): HARD RULE 8 third
   case + HARD RULE 9 soft-target exclusion + the "Relaying user
   authorisations" bullet names soft targets
   (`extra_utilities/draft_prompt_conductor.md`). The 5-agent **UII**,
   **Creator** (DCIC+DCII), and **DCOI** drafts do NOT exist yet (build-order
   stages 3-4); they MUST carry the soft-target handling when authored (UII
   marker convention + UI-pin-softening; Creator not-locked/start-near +
   self-validate-no-violation; DCOI not-a-claim).
3. Later, the **3-agent** system.

### Recording format (DECIDED 2026-07-26): Option A — marker on the line
A soft target is recorded as a standardized marker on its QUANTITATIVE
INPUTS line (NO code change — extends the existing unit/frame annotation
convention). Shape:

    - outerRadius: ~140 mm — SOFT TARGET (goal: match the sketched blade
      shape; keep near 140 mm if free, but vary freely to fit the shape)

HARD RULE 8 then reads three cases off the line: an unmarked QUANTITATIVE
INPUT = LOCKED; one marked `SOFT TARGET (...)` = soft; anything not in
QUANTITATIVE INPUTS = FREE.

### Decisions log
- 2026-07-26: first-class named concept (not "strengthen the prose"); goal
  dominates + keep-close-if-free strength; **recording = Option A** (marker
  on the QUANTITATIVE INPUTS line, no code change).

---

## PART C -- Out-of-range values: full case matrix + coherence audit

*Source: `extra_utilities/analysis_out_of_range_cases.md`, reproduced in full.
This part carries the AUTHORITATIVE close status for the G-items that Part A
lists as open -- where the two disagree, this one is newer.*

## Out-of-range values — full case matrix + coherence audit

> ### ✅ FIXES APPLIED 2026-08-01 (owner-approved, one at a time)
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

### Three facts established from CODE, not prompts

1. **`write_parameters` validates key-set + numeric-ness only** — no range
   comparison (`agents/dc_input_creator/dc_input_creator.py`).
2. **No range table exists in executable code.**  The generator has no guard.
3. **The UI cannot produce an out-of-range value.**  `web/app.js` renders every
   parameter as `<input type="range">` with `min`/`max` from the spec table, so
   a UI-pinned value is bounded by construction.  **The only routes for an
   out-of-range user value are free-text chat and images / sketches.**

⟹ Range enforcement is **entirely prose-level**.  Nothing mechanical backs it.

### Structurally impossible cases (not padding the matrix)

| Combination | Why it is a null set |
|---|---|
| USER-supplied + FREE | FREE is *defined* as absent from QUANTITATIVE INPUTS; a user number is LOCKED or SOFT TARGET. |
| SOFT TARGET + no authorisation | "the marker itself IS the authorisation to move the value (within range)". |
| UI-pinned + out of range | Unreachable — slider bounded (fact 3). |
| AGENT-chosen + LOCKED | **NOT null** — a directive "to keep it fixed LOCKS it (even if the user did not)". That is case **G7**. |

### PART 1 — GEOMETRY-GENERATING requests

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

### PART 2 — EXTRACTION-ONLY requests

| # | Case | Ends | User asked? |
|---|---|---|---|
| **E1** | USER / LOCKED / out of range | Receptionist labels it extraction-only → UII extracts verbatim → Planner: "the extraction IS the deliverable… Do NOT hand off to the DCIC". **DCIC/DCII/TC/DCOI never run. The number is reported back never compared to its range, never flagged** | **NO — and not warned (U-g)** |
| **E2** | USER / SOFT TARGET | Identical | NO |
| **E3** | Value on an **unrecognised parameter NAME** | Receptionist replies directly and does NOT forward | **YES** |
| **E4** | Extraction-only turn, then "now build it" | Re-enters as G1; no re-validation at the transition (U-h) | Per G1 |

> **The sharpest asymmetry in the system:** a bad parameter **name** stops the
> request at the door; a bad parameter **value** never does.

### PART 3 — UNDEFINED cells

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

### PART 4 — Coherence WITHIN the 7-agent system

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

### PART 5 — Coherence ACROSS topologies

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
