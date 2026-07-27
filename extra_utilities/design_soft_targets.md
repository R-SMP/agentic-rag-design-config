# Soft targets — provided values subordinate to a qualitative goal

**Problem.** The prompts treat any user-provided number as LOCKED-by-default,
with the only escape a free-prose "authorisation" in DESIGN INTENT. That
capture is fragile (it misfired in the precision-sections production runs),
and it can't crisply express **benchmark 7**: *"here are dimensions, but fit
the sketched shape — the exact dimensions are not as important."* There is no
first-class notion of a provided value that is a **soft target**: honoured
when free, but sacrificed to serve a goal when they conflict.

## The concept (DECIDED 2026-07-26)
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

## Where it touches the prompts (full 7-agent system FIRST)
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

## Order
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

## Recording format (DECIDED 2026-07-26): Option A — marker on the line
A soft target is recorded as a standardized marker on its QUANTITATIVE
INPUTS line (NO code change — extends the existing unit/frame annotation
convention). Shape:

    - outerRadius: ~140 mm — SOFT TARGET (goal: match the sketched blade
      shape; keep near 140 mm if free, but vary freely to fit the shape)

HARD RULE 8 then reads three cases off the line: an unmarked QUANTITATIVE
INPUT = LOCKED; one marked `SOFT TARGET (...)` = soft; anything not in
QUANTITATIVE INPUTS = FREE.

## Decisions log
- 2026-07-26: first-class named concept (not "strengthen the prose"); goal
  dominates + keep-close-if-free strength; **recording = Option A** (marker
  on the QUANTITATIVE INPUTS line, no code change).
