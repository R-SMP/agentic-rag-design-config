# Design — "Don't ask back" (global no-escalation) + out-of-range value degrade

**Status:** DESIGN AGREED, NOT YET BUILT.  Decisions below were made by the
product owner on 2026-07-28 via explicit multiple-choice sign-off.  Nothing in
this document has been applied to any prompt yet.

**Origin.** Surfaced while rewiring the live 7-agent prompts onto the shared
`$value_states` fragment.  The trigger was **benchmark 6**: the user states a
value that is OUT OF RANGE, asks to keep it, and asks the system NOT to ask
back.  The pipeline had no answer for this — worse, it had a hard gate at the
front door that would violate the directive outright (see "The blocker").

Related: [[v9_soft_targets]] (the three-state model this builds on),
`extra_utilities/agent_count_variants_build_tracker.md` (the rewiring work this
interrupted).

---

## The blocker that started it

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

## The decisions (D1–D8) — all FINAL

### D1. Global no-escalation mode
A user instruction like "do not ask me back" / "don't ask questions" / "proceed
without asking" is a **STANDING directive**: recorded in the extraction's
**DESIGN INTENT** section, valid every cycle **until the user revokes it**
(same lifetime as the existing user authorisations).

It suppresses **ALL user-facing questions pipeline-wide** — the Receptionist's
front-door gates, the DCIC's escalations, the DCII's escalations, the Planner's
escalate-to-user, and the Orchestrator's relaying of any of them.

> Inter-agent CLARIFY is **unaffected** — it never reaches the user.  Only
> user-facing questions are suppressed.

### D2. It is FULLY global — not just value/range questions
Chosen deliberately over the narrower "value/range only" option.  Even an
**unrecognised parameter name** or an unreadable input — which today bounces
back to the user asking them to restate — must instead get the agents' best
interpretation (or be skipped), and be **disclosed** in the final answer.

*Owner's rationale:* it is what an unattended overnight benchmark run needs to
keep moving, and it is the plain meaning of "don't ask me anything".
*Accepted risk:* the system may guess on genuinely ambiguous input.  D8 is the
mitigation — every guess must be disclosed.

### D3. The floor — never block, always report
The pipeline **never blocks mid-run**.  It always finishes and produces the best
result it can; the **final answer** states plainly what could not be honoured
and why.  The directive is **NEVER overridden**: a limit is **REPORTED**, never
turned into a question.  (Explicitly chosen over an "override as a last resort"
escape hatch, which would reintroduce the mid-run stall in unattended runs.)

### D4. Out-of-range user values — the 2×2
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

### D5. The substitution is modelled as a DEGRADE TO SOFT TARGET
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

### D6. Who substitutes
**The DC Input Creator chooses the in-range number** — it is the only agent that
authors concrete values — and **documents the substitution in its hand-off**.
**The DC Input Inspector verifies** it is in range and coherent with the user's
intent.  **The Planner stays qualitative-only**, consistent with its HARD RULE 7
(never invent numeric values).

### D7. Insistence counts as authorisation
If the system **did** ask about an out-of-range value (no directive was in
force) and the user **insists on keeping it**, the same degrade + substitution +
disclosure applies.  Asking again is pointless and geometry still cannot accept
the number — being told and still insisting **is** the authorisation.  One rule
covers both routes into the situation.

### D8. Disclosure is mandatory
Whenever a user's number was **not honoured**, or an input was **guessed at or
skipped**, the **final answer to the user must say so concretely** — name the
parameter, the user's value, the value actually used, and why.  This is the
mitigation for the risk D2 accepts.

---

## Consequences already identified

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

# CHANGE-SURFACE AUDIT (2026-07-28) — 10-agent map + design critic

**Scale: 95 sites must change**, across every agent except the Tool Caller:
Receptionist 16, Planner 16, DCIC 15, UII 12, Orchestrator 6, DCII 5, DCOI 4,
fragments 21, Tool Caller 0.

## ⛔ Blockers found (each VERIFIED against the code by hand)

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

## ⚠ Design gaps D1–D8 do NOT answer

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

## Build ORDER (dependency-forced, from the critic)

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

## One thing to REUSE rather than reinvent

`$value_states` authorisation source **(B)** — *"the extraction's DESIGN INTENT
section records one … standing every cycle until revoked"* — is EXACTLY D1's
persistence mechanism, already defined and already read by the DCIC, DCII and
Planner.  D1's standing directive should be written as an instance of (B), not
as a new mechanism.  (NOT to be confused with the Planner's
`=== STANDING DIRECTIVES ===` hand-off block, which only the Planner may set.)
The UII also already has a **"Reporting preferences"** slot in DESIGN INTENT
(e.g. *"do not report back until a viable solution is found"*) — the natural
home for the no-ask-back directive.

## Open items (to resolve during the build)

- G1–G8 above, each needing a product decision.
- Whether `$value_states` itself should mention the degrade, or whether it stays
  purely user-authored and the degrade is explained where it is created (UII).
