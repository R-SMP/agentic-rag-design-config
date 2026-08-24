# Prompt reduction, round 3 — DC Output Inspector

**Source:** `7agent_reduced_system_prompts_PDFnotes3_DCOI.pdf`
(14 pages — pages 86–99 of the original 113-page build, extracted).
**Applies to:** `stage-a-web-deploy` at `8e75646` or later.
**Companions:** `prompt_reduction_4agents_changes.md` (round 1, applied in
`afc33fa`) and `prompt_reduction_3agents_changes.md` (round 2, applied in
`a9c36a5`).

122 highlights and 26 typed comments. Same convention as before:

| colour | count | meaning |
|---|---|---|
| red | 101 | delete the highlighted text |
| light yellow | 21 | modify / substitute — the adjacent comment says how |

No dark yellow, no green this round. After this, only the **Database Handler**
remains unreviewed.

---

## 0.1 What has already changed underneath this PDF

The PDF was marked up on the original build (`4786832`). The DCOI has moved
since, in four separate ways, and every anchor below was resolved against the
working tree at `8e75646` — so the paths and line numbers are current. Read
this list first, because it explains most of the "no automatic source match"
rows:

| already applied | by | consequence for this round |
|---|---|---|
| `## ROUTING` restructure — decision bullets folded into the tool bullets | `a9c36a5` (round 2 §A2) | **p. 9's "do here the same that was done for the Tool Caller" is already done.** Only the ESCALATE rewording remains |
| `Current attempt:` → `Current attempt <N>:` | `a9c36a5` (round 2 §A4) | spans quoting the old label no longer match verbatim |
| hard-constraints heading merge | `a9c36a5` (round 2 §A1) | the three `## Hard constraints — …` headings are already one |
| `list_attempts` / `read_attempt` → `read_attempts` | rounds 1–2 | the p. 5 and p. 10 tool cards are already resolved |
| `SKETCH CROP REGION` → `USEFUL INPUT IMAGES` + `crop_regions`; `ocr_regions` → `reread_text_regions` | `7267eb6` | the crop-region sentences were rewritten; the OCR tool card is renamed |

Also already gone globally: "Batch into ONE call; a second only when a later
expression needs an earlier result." (cut in round 1), which is why the p. 7
red span over it does not match.

---

## 0.2 How to apply these tables

**One row per annotation — nothing merged, nothing elided**, and the
machine-readable source is committed beside this file as
`round3_annotations.json`. Work from the JSON, and after each deletion check
that the span's **tail** is gone, not just its opening words. That is the
failure mode round 1's merged-and-elided tables produced.

---

## 0.3 Decisions already taken (do not re-litigate)

1. **This round is DCOI-only.** Nothing here changes another agent's prompt.
   The two "all agents" items the PDF asks for were already delivered in
   round 2.
2. **Comparison-mode text: apply to ALL THREE modes.** The block lives in
   `agents/dc_output_inspector/dc_output_inspector.py` as three runtime strings
   (`_COMPARISON_MODE_1/2/3`), not as a `$slot` fragment. The PDF shows mode 3.
3. **Scoped copies for `value_states` and `visual_inspection_guide`** rather
   than direct edits — the 5-agent DCOI and Creator read both and have no base
   override to shield them.
4. **`generic_constraints.md` and `routing_dc_output_inspector.md` ARE edited
   directly** — no other 7-agent prompt reads them, and topology 5 is shielded
   by its own `*_5agents.md` base overrides.
5. **The DCOI gains both `read_extracted_inputs` and `read_user_inputs`**, and
   keeps `view_images` + `reread_text_regions`.
6. **Feature-level feedback becomes an equal option**, not the only one and not
   the primary one.
7. **One precision mechanism, whichever target(s) the directive names** — see §C4.
8. **The comparison text names all four extraction sections**, including
   `QUALITATIVE DESCRIPTIONS`, which had been wrongly dropped.

---

## A. Mechanism

### A1. Register one more scopable slot

`agents/shared/prompts.py` → `SCOPED_FRAGMENTS`. Add:

```python
"visual_inspection_guide": ("dc", "dc_config/visual_inspection_guide.md"),
```

`value_states` is already registered (round 1). Without this registration the
scoped copy in §C1 is read by nobody and the cuts silently do nothing.

### A2. Scoped copies to create

| new file | copy of | why a copy rather than a direct edit |
|---|---|---|
| `agents/shared/prompt_fragments/value_states_dc_output_inspector.md` | `value_states.md` | 5 spans cut; the 5-agent DCOI and the Creator read the shared file with no base override |
| `DC_prompt_fragments/dc_config/visual_inspection_guide_dc_output_inspector.md` | `visual_inspection_guide.md` | 9 spans cut; the 5-agent DCOI reads the shared file with no base override |
| `DC_prompt_fragments/dc_config/hard_constraints_dc_dc_output_inspector.md` | `hard_constraints_dc.md` | 1 span cut; the Receptionist still reads the shared file |

Edit **directly**, no copy needed: `generic_constraints.md`,
`routing_dc_output_inspector.md`,
`blade_sections_visualizer_dc_output_inspector.md`, and the DCOI's own
`prompt.md`. `hard_constraints_tools.md` needs no copy at all this round — its
only marked span was already cut in round 1.

---

## B. Tool-layer changes

| change | source | note |
|---|---|---|
| **Add `read_extracted_inputs`** | p. 10 — *"Add to the DCOI the tool read_extracted_inputs, as the DCIC has it"* | The DCOI's whole job is comparing the render against the extraction; it currently has no direct reader for it |
| **Replace `list_input_files` + `read_input_text` + `read_image_notes` with `read_user_inputs`** | p. 12 — *"As for the UII, substitute this with the same tool used by the UII to read all user queries and image notes and list all input images paths"* | Same trade the Planner (round 1) and DCII (round 2) made |
| **Keep** `view_images`, `reread_text_regions`, `read_attempts`, `calculate`, `call_tool_caller`, `call_orchestrator` | cards unhighlighted | `reread_text_regions` is `ocr_regions` under its `7267eb6` name |

**Before → after:** `read_attempts, calculate, list_input_files,
read_input_text, read_image_notes, view_images, reread_text_regions,
call_tool_caller, call_orchestrator` (9, +2 RAG) → **`read_extracted_inputs,
read_user_inputs, read_attempts, calculate, view_images, reread_text_regions,
call_tool_caller, call_orchestrator`** (8, +2 RAG).

Every prompt reference to the three removed readers must go with them — the
comparison-mode blocks name `read_input_text(path=…)`, `list_input_files()` and
`read_image_notes()` explicitly (§C2).

---

## C. Content changes

### C1. Loading render images — the always-present primer (p. 1)

Two comments on the yellow `Rules:` block:

1. *"these rules are not stacking vertically, fix this"* — the two rules render
   as running prose. Make them a real list.
2. *"this needs rephrasing, or a note/remark, because there is an image that is
   given ALWAYS to the DCOI because it helps the agent to understand the
   structure of the propeller"* — that is the DC-parameter primer diagram
   (`DC_PARAMS_PRIMER_ENABLED = True`). The rule "If NO image paths were
   provided, you CANNOT perform a visual analysis" is therefore literally false
   as written: an image IS always present.

   **Rephrase to separate the primer from the renders.** The primer is a
   REFERENCE for understanding the geometry and the parameter names — it is
   never evidence about this cycle's design. With no render paths the DCOI still
   cannot judge the output, and must say so and ESCALATE. Keep the
   anti-fabrication force; remove the false premise.

### C2. Comparison sources — all three mode strings (p. 2)

In `agents/dc_output_inspector/dc_output_inspector.py`, apply to
`_COMPARISON_MODE_1`, `_COMPARISON_MODE_2` **and** `_COMPARISON_MODE_3`:

* **Tool names.** `read_input_text(path=/app/inputs/extracted_inputs.txt)` →
  `read_extracted_inputs(path)`; the raw-input tool list
  (`list_input_files()`, `read_input_text(...)`, `read_image_notes()`,
  `view_images([...])`) → **`read_user_inputs()` and `view_images()`**, per the
  p. 2 comment. Any mode that names a removed tool is a dangling reference.
* **Name all four extraction sections.** The text names only `QUANTITATIVE
  INPUTS` and `DESIGN INTENT`. It must name **`QUANTITATIVE INPUTS`,
  `QUALITATIVE DESCRIPTIONS`, `DESIGN INTENT AND FUNCTIONAL REQUIREMENTS` and
  `USEFUL INPUT IMAGES`** — the canonical headers `write_extraction` emits
  (`agents/user_input_inspector/user_input_inspector.py:405-409`).
  `QUALITATIVE DESCRIPTIONS` had been dropped and should always have been there;
  `USEFUL INPUT IMAGES` is where the crop boxes now live.
* **Scope sentence.** "The comparison source(s) in scope this session: extraction
  ALWAYS, plus the user's raw inputs WHEN your judgement says they are needed."
  → **"…extraction ALWAYS, then inputs (images and/or texts) when your judgement
  says they are needed."** ("then" instead of "plus"; "inputs (images and/or
  texts)" instead of "raw inputs".)
* Red cuts inside the block are in the table.

### C3. Precision job — vocabulary (p. 2)

* `Precision **section-matching**` → **`Precision Job`**
* "The bar is **SHAPE fidelity**: the user…" → **"fidelity to the user request
  and design intent"**
* `Compare the render against the user's sketch, side by side` → prefix with
  **"(If user images are present)"**, and `sketch` → **`image(s)`**
* `its sections region` → **"region where precision is seeked"**
* p. 3: `drawing` → **"input image"** (both occurrences); `drawing` in "match the
  drawing as closely as the configurator can express" → **"inputs/request"**
* p. 3: `DC Input Creator,` → **"other agents"**

### C4. One precision mechanism, target set by the directive (p. 3)

The whole `Full-3D precision check (when the directive targets the 3D)` section
is red. It does **not** mean the DCOI stops handling 3D jobs. The owner's
wording: *"it's running the REQUIRED precision loop: it can run a precision loop
for the sections, one for the 3D geometry, or with BOTH at the same time. It all
depends on the directive."*

So: delete the separate 3D branch and its sections-vs-3D framing, and state once
that the loop compares whatever the standing directive names — the blade
sections, the whole-propeller 3D views, or both in the same job — against
whatever renders the hand-off supplied. Everything that was 3D-branch-specific
(the "no never-approve-the-first-render rule here", "the 3D loop is usually
short", the sections-converged-first ordering) goes.

**Move, don't delete:** the yellow *"Iterate only if an UNLOCKED lever helps…
A value marked SOFT TARGET counts as an available lever here, NOT a locked
number."* moves **before the "When to stop" paragraph** (p. 3 marginal note).
Its `(A6b).` and `to the DCIC` fragments are red within it.

### C5. When to stop (p. 3)

* `(you judge; a code cap backstops you)` → state the budget concretely:
  **roughly 2–3 refine rounds**, rather than referring to an unnamed code cap.
* **Add**, at the end of the paragraph: *"When you finalize, state to the Planner
  which was the BEST ATTEMPT so far."*

### C6. Move "Override authority" after "Verdict shape" (p. 4)

The whole `Override authority and reporting upstream interpretation problems`
paragraph moves to sit **after** the `Verdict shape` section. Apply its red cuts
in place first.

### C7. Feedback may name features, not only parameters (p. 6)

The owner's note: *"I do not want the DCOI to focus just on telling which
parameters to move: that can also be assessed, in some cases, by the DCIC and
DCII. The DCOI can often just say which geometric FEATURES are far off, and the
DCIC + DCII can then understand which parameter(s) to change."*

* `name which of the 16 parameters *seem* to need adjustment` → **"name which
  geometry features and/or which of the parameters seem to need adjustment"**
* the example `("<param X> looks too small / large")` → **add a generic-feature
  example alongside it**, e.g. *"the blade looks too twisted"*.
* Feature-level and parameter-level feedback are **equally valid**; prefer the
  feature when unsure which parameter is responsible. Do not make features the
  primary mode, and do not delete the existing parameter guidance.

### C8. ROUTING — one rewording only (p. 9)

The restructure itself is already applied. What remains is the ESCALATE
condition. Today it reads "or ESCALATE when something is fundamentally wrong and
you cannot fix it." The comment asks for something concrete: *"instead of 'no
agent in the chain can fix it', say something like 'it relates to tool problems,
authorization needs, revises that you cannot act upon'."*

Rewrite it to name those cases — a tool failure, a missing authorisation, or a
REVISE you cannot act on yourself — instead of the abstract "fundamentally
wrong". The red cuts in `routing_dc_output_inspector.md` still apply.

### C9. Every annotation, with its source anchor

**One row per annotation — nothing merged, nothing elided.** `lines` are 1-based in the named file at `8e75646`; `p.` is the annotated PDF page. `RED` = delete the text. `YEL` = modify, per the comment recorded above. The same data is in `round3_annotations.json` — prefer iterating that.

##### `DC_prompt_fragments/dc_config/hard_constraints_dc.md` — 1 annotation

> ⚠ Shared file. Make this cut in the scoped copy `DC_prompt_fragments/dc_config/hard_constraints_dc_dc_output_inspector.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 2-6 | RED | 7 | The 16 named parameters are the ONLY design levers and there is no mesh-editing capability: geometry changes only by changing them and regenerating via the DC Input Creator → Tool Caller path. Reject invented parameters (hub_radius, fillet_radius, tip_clearance, any "supplemental" value) — they do not exist. |

##### `DC_prompt_fragments/dc_config/visual_inspection_guide.md` — 9 annotations

> ⚠ Shared file. Make this cut in the scoped copy `DC_prompt_fragments/dc_config/visual_inspection_guide_dc_output_inspector.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 1-6 | RED | 4 | A propeller with correct geometry should show: - A continuous circular outer ring. - The requested number of evenly spaced blades connecting the centre hub to the outer ring. - Smooth blade surfaces without holes, spikes, or self-intersections. - Proportions consistent with the input parameters (impellerRadius, impellerThickness, etc.). The outer-ring HEIGHT auto-fits the outer blade section (derived, not an input). |
| 8-12 | RED | 4 | What you can typically check visually for this DC Blade count (count blades in the top-down view). Outer ring presence and continuity (visible in all three views). |
| 13-15 | RED | 5 | Hub presence and approximate proportion. Broad vs. narrow blade planform; rounded vs. squared tips. Blade-to-ring connection vs. detached blade tips. |
| 17-29 | RED | 5 | The three shape levers, and what each one actually moves *Thickness (% of chord) — how thick the section is. Its THICKEST POINT is FIXED at ~30% chord and no parameter can move it. *Camber (% of chord) — how curved the mean line is; 0 = a symmetric section with no crest at all. *MaxPos (tenths of chord) — where the CAMBER CREST sits along the chord. It does not move the thickest point, and does nothing when camber is 0. So "the high point is too far forward" is a statement about the CAMBER crest. If a section instead looks thickest in the wrong place, NO parameter can fix it — say so plainly rather than asking for a *MaxPos change. |
| 37-37 | RED | 5 | What is typically NOT resolvable at render resolution |
| 39-39 | RED | 5 | Sub-millimetre thicknesses (ring or blade section). |
| 40-41 | RED | 5 | Exact twist angles in degrees. Exact chord lengths within ~1 mm. |
| 42-42 | RED | 5 | Camber percentages and the high-point (camber-crest) position. |
| 44-45 | RED | 5 | When a claim falls in the "not resolvable" bucket, mark it as such and trust falls on the DCIC's parameter choice and the DCII's authorisation check. |

##### `DC_prompt_fragments/tools_config/blade_sections_visualizer_dc_output_inspector.md` — 1 annotation

> Edit this file DIRECTLY — already a per-agent overlay.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 11-22 | RED | 9 | pass its recorded crop box in regions (the list aligned by index with your paths ) so only the relevant section area is compared, not the whole page. Give clear, precise feedback aimed at refining the section parameters; the fast sections loop may need many iterations, so keep each round focused and do not waste it on irrelevant remarks. If the fix is to render (or re-render) the blade sections on the same attempt, REVISE straight back to the Tool Caller ( call_tool_caller ) and ask it to render the blade sections — do NOT escalate to the Orchestrator for this, which would needlessly open a new attempt when the current one just needs its sections rendered. Escalate only for a genuinely new design direction or a blocker you cannot fix. |

##### `agents/dc_output_inspector/dc_output_inspector.py` — 9 annotations

> Runtime-injected Python strings, not a `$slot` fragment — the three `_COMPARISON_MODE_*` constants and the image-persistence blocks. Edit the constants; line numbers are in that file.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 52-52 | RED | 1 | You are STATEFUL: |
| 64-64 | RED | 1 | Mode: KEEP IMAGES IN CONTEXT (OFF). |
| 71-71 | RED | 2 | This session is configured to |
| 79-79 | RED | 2 | 1. view_images([...]) — load this cycle's renders |
| 139-140 | RED | 2 | — focusing on its QUANTITATIVE INPUTS and DESIGN INTENT sections), |
| 141-142 | YEL | 2 | user_query.txt , paired image+note) |
| 149-156 | RED | 2 | and form your visual judgement of the rendered design on its own terms before reading any comparison source. This ordering matters: loading a comparison source first anchors the model on its stated features, after which it tends to confabulate agreement on the render rather than actually counting / observing what the render shows. Render-first forces an independent reading. 2. read_input_text(path=/app/inputs/extracted_inputs.txt) — |
| 161-176 | RED | 2 | Use QUANTITATIVE INPUTS and DESIGN INTENT as your primary comparison source. 3. When ANY of the following is true, ALSO consult the user's raw inputs: - DESIGN INTENT in the extraction explicitly references a visual / structural feature most reliably resolvable from the reference image (e.g. an instruction to match a sketch's silhouette, layout, or proportions closely). - QUANTITATIVE INPUTS contains a real-world- quantity entry whose unit / framing seems ambiguous and the paired note might disambiguate. - You suspect the extraction may have misread something the user supplied (a count discrepancy, a value that disagrees with what is plainly visible in the reference image, etc.). Use the user-input tools as needed: list_input_files() , read_input_text(path of /app/inputs/user_query.txt or a paired _note.txt) , read_image_notes() , view_images([...]) . 4. Otherwise, the extraction alone is sufficient. Don't burn LLM turns loading user inputs you don't need to consult. |
| 182-183 | RED | 2 | The comparison source(s) in scope this session: extraction ALWAYS, |

##### `agents/dc_output_inspector/prompt.md` — 46 annotations

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 13-13 | RED | 9 | — normally the Tool Caller |
| 13-15 | RED | 1 | by the Tool Caller under a Render images: label in the message argument of its routing call; those paths live inside the cycle's attempt folder, named under the same hand-off's Current attempt: line. |
| 18-24 | YEL | 1 | Rules: - If NO image paths were provided, you CANNOT perform a visual analysis. Do not call the tool with empty or fabricated paths. State plainly that no image paths were supplied, base your response on the text report only, and ESCALATE so the Orchestrator can recover. - One call to view_images per set of paths is enough — do not loop. |
| 29-29 | RED | 1 | Re-loading is neither automatic nor mandatory: |
| 29-37 | RED | 1 | load the current renders when a fresh visual judgement adds value this turn — to decide a verdict the QC numbers don't settle, or to diagnose WHY a failure occurred and name which parameters likely need changing — and skip them when QC alone already decides (e.g. the mesh isn't watertight). Only re-load when new renders actually exist: if the hand-off says none were produced this cycle (e.g. "calculate only; renders unchanged"), don't call view_images — rest on text, or cite what you already recorded about the earlier (unchanged) images, naming it as such. |
| 52-63 | RED | 1 | — replace the GEOMETRY ANALYSIS section with whichever of these fits: (a) Verdict from QC numbers only: "GEOMETRY ANALYSIS: Renders not loaded this turn — visual analysis not performed; verdict based only on this hand-off's QC numerics: <the QC facts you use>." (b) Referring to a previous cycle's renders you can still see — re-loaded this turn from that attempt's path, or still shown as images in your history: "GEOMETRY ANALYSIS: Current-cycle renders not loaded; comparing only against a previous cycle's renders (<which>): <claims, marked as prior- cycle, not current>." Never leave in a visual claim you cannot back with a this-turn load. |
| 69-71 | RED | 2 | (The same "never describe what you didn't load this turn" rule covers reference images too — a visual claim about one needs a view_images call this turn.) |
| 76-76 | YEL | 2 | section-matching Job |
| 79-80 | RED | 2 | (match the blade sections to the user's precise drawing). |
| 83-84 | RED | 2 | and do NOT approve on ordering / proportions / section-count alone. |
| 84-84 | YEL | 2 | SHAPE fidelity: the user |
| 85-86 | RED | 2 | section's airfoil profile — thickness, camber, high-point, angle — against the drawing. |
| 90-90 | YEL | 2 | its sections region |
| 94-95 | RED | 3 | Judge the whole strip, mapping inner / middle / outer by the coloured labels. |
| 96-97 | RED | 3 | over the session's comparison- source mode: |
| 97-99 | RED | 3 | so load the sketch here even under a mode that would normally keep the user's raw input images out of scope. |
| 107-107 | YEL | 3 | DC Input Creator, |
| 109-111 | RED | 3 | below: under a precision directive there is no Planner re-plan; the DCIC opens a fresh attempt for the changed params each round, so the loop's attempts accumulate (use list_attempts / read_attempt to pull a PRIOR round's render when you need to judge progress). |
| 114-114 | RED | 3 | a code cap backstops you) |
| 123-124 | RED | 3 | (the Planner is the final approver) |
| 125-126 | RED | 3 | (the airfoil model's ceiling on a sections job; the geometry or a locked number on a 3D one) |
| 130-139 | RED | 3 | Full-3D precision check (when the directive targets the 3D) A precision directive may target the WHOLE-propeller 3D instead of the sections — the Planner issues it after the sections converge, when the user supplied a top / side / perspective sketch of the whole propeller. The SAME loop applies, with the target swapped: - Compare the 3D render views (isometric / top / side, from the Render images: paths) side-by-side with the relevant sketch view cropped to the propeller — a top-view sketch against the top render, a side sketch against the side render. Same view_images(side_by_side=True) + the UII's crop region (which for a 3D job covers the whole-propeller view, not the sections strip). - Judge the mismatched ASPECT — planform outline, blade sweep / twist, tip shape, ring proportions — and describe it in prose. |
| 144-148 | YEL | 3 | Iterate only if an UNLOCKED lever helps (A6b). If an unlocked parameter would measurably improve the mismatched aspect — e.g. a section's radial position ( middlePos ) shifting the planform, a chord, or an angle — route the gap to the DCIC as above. A value marked SOFT TARGET counts as an available lever here, NOT a locked number. |
| 148-151 | RED | 3 | If the mismatch traces to LOCKED user numbers or the configurator's limits, so nothing unlocked can move it, do NOT iterate: STOP and report the mismatch honestly, naming what could not be matched and why. |
| 152-155 | RED | 3 | - The first 3D render MAY be approved if it genuinely matches — unlike the sections loop, there is NO "never the first render" rule here, because the 3D is built from the already-converged sections, so a good first match is expected. The bar is only "not a coarse match alone". |
| 156-156 | RED | 3 | Termination is the same (Satisfied / Plateau / cap); |
| 156-157 | RED | 3 | the 3D loop is usually short because it has few levers. |
| 166-167 | RED | 4 | ending with the Tool Caller's range check before generating) |
| 167-168 | RED | 4 | or re-count features the source already states |
| 173-180 | RED | 4 | A SOFT TARGET is not a claim to enforce. When the source marks a value SOFT TARGET (goal: …) — or, when your in-scope source is the user's raw inputs, when the user's OWN WORDS subordinate a value to a goal ("these dimensions matter less than matching the shape") — the user subordinated it to that goal, so a render that deviates from the stated value to SERVE the goal is not a defect — judge that value against its GOAL (did the render move toward it?), never against the exact number; flag it only if the render moved AWAY from the goal. |
| 206-207 | RED | 4 | (the DCII's check is parameters-vs-extraction only). |
| 211-212 | RED | 4 | (not CLARIFY to the Tool Caller) |
| 212-213 | RED | 4 | — this needs a recovery plan revisiting the extraction / parameter step, not a re-run. |
| 219-221 | RED | 4 | — silently approving a design that visibly diverges from the user's intent is the failure mode this prevents. |
| 229-229 | RED | 4 | What a Correct Output Should Show |
| 251-252 | RED | 6 | you say which parameter looks wrong and in which direction. |
| 259-259 | YEL | 6 | ("<param X> looks too small / large"). |
| 264-264 | RED | 6 | "reduce the camber by about a third", |
| 271-278 | RED | 6 | *Thickness and *Camber are RATIOS — percentages of that section's own chord — so what you see in the render is the ratio multiplied by the chord. The two move independently as soon as the chord changes: hold the RATIO while the chord grows and the section gets visibly THICKER; hold the MILLIMETRES while the chord grows and it gets visibly SLIMMER. A bare "keep the thickness the same" therefore has two opposite readings, and the DCIC cannot tell which you meant. |
| 283-284 | RED | 6 | use whatever combination of chord and thickness-ratio achieves that" |
| 290-293 | RED | 6 | Those reported values give you BOTH numbers for every section (e.g. thickness 12% of chord (= 0.60 mm) ), so you can always tell which one is off — and a section whose chord is pinned cannot grow in mm however far you push its ratio. |
| 318-320 | RED | 6 | Data Flow Send your analysis opinion and recommendation — not the hand-off's raw data, file contents or quality-check numbers copied out verbatim. |
| 322-324 | RED | 7 | When a REVISE needs only a (re-)render of the SAME design — the blade sections, or a render that failed — carry the hand-off's Current attempt: and Parameters file: lines |
| 324-326 | RED | 7 | through to the Tool Caller so it renders into the folder this design already lives in; without the second line it can only escalate. |
| 326-327 | RED | 7 | Escalating a re-render to the Orchestrator instead needlessly opens a new attempt. |
| 329-335 | RED | 7 | When instead the REVISE calls for a PARAMETER or design change, that is the ordinary "REVISE → re-plan" path: hand it to the Orchestrator with call_orchestrator . Only a re-plan (Planner → DC Input Creator) can authorise different values, and the DCIC opens the NEW attempt folder they are written into. Do NOT ask for a re-render of the SAME attempt in the same breath as recommending different numbers — that render can only show the design you already rejected. |

##### `agents/shared/prompt_fragments/generic_constraints.md` — 4 annotations

> Edit this file DIRECTLY — no other 7-agent prompt reads it, and topology 5 is shielded by its own `generic_constraints_5agents.md` base override.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 6-6 | RED | 7 | only the Planner may change it. |
| 17-18 | RED | 7 | — hand the problem to whoever can resolve it. |
| 21-22 | RED | 7 | DON'T script the final user-facing reply — route your content to the Orchestrator. |
| 26-27 | RED | 7 | The only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up. |

##### `agents/shared/prompt_fragments/routing_dc_output_inspector.md` — 5 annotations

> Edit this file DIRECTLY — already DCOI-only; topology 5 has `routing_dc_output_inspector_5agents.md`.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 5-5 | RED | 9 | — the Tool Caller only renders; it does not author parameters. |
| 9-9 | RED | 9 | (signal a successful cycle; |
| 10-10 | RED | 9 | the Orchestrator then routes to the Receptionist); |
| 11-12 | RED | 9 | (the Orchestrator re-plans via the Planner → DCIC → new attempt); |
| 16-18 | RED | 9 | You are the last agent in the natural flow; "completing normally" means handing control back to the Orchestrator via call_orchestrator with an APPROVE verdict. |

##### `agents/shared/prompt_fragments/value_states.md` — 5 annotations

> ⚠ Shared file. Make this cut in the scoped copy `agents/shared/prompt_fragments/value_states_dc_output_inspector.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 12-15 | RED | 3 | and the "keep near … if free" strength then says how closely to follow it ("not as important" → your choice within range; "prefer X but the shape matters more" → use X). |
| 16-18 | RED | 3 | either the user never specified it, or they specified it and later released it (a value that is no longer constrained is simply OMITTED from the section). Either way |
| 19-22 | RED | 3 | A qualitative description that must be turned into a number is FREE for that parameter too — unless a directive holds a specific one fixed, which is then treated as LOCKED for that cycle. |
| 24-31 | RED | 3 | Freeing a LOCKED value. A LOCKED value may change only with an authorisation, discoverable from ANY of these (one is enough): (A) the incoming hand-off names one — a user permission (blanket "vary as needed" / "automated conservative adjustments OK", scoped "except <param X>", or parameter-specific "the user approved changing <param Y>") or a strategy / recovery directive to change the value; a CLARIFY bounce may carry one too; (B) the extraction's DESIGN INTENT section records one — a user |
| 32-45 | RED | 4 | authorisation the UII wrote, standing every cycle until revoked; or (C) the value's own QUANTITATIVE INPUTS line carries an (unlocked by user) annotation, IF PRESENT — an older extraction may still carry this inline mark; today a released value is simply omitted from the section (which makes it FREE) rather than annotated. One source is enough — never demand a "ritual re- confirmation" of an authorisation the hand-off already carries. A line literally saying "user-locked" is only the DEFAULT lock and does NOT override a current authorisation — the hand-off, DESIGN INTENT, and any inline annotation are the current sources of truth. How FAR an authorised (or soft) value may move follows the wording: "as needed / only if necessary" = the smallest change that restores viability, staying close to the user's number; "freely / as much as possible" (or nothing said) = as far as the goal requires, bounded by range. |

##### `agents/shared/routing.py` — 2 annotations

> Generated at runtime. This text is not edited in place — it is produced by `routing_instructions()` and is restructured wholesale by §A2.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 171-171 | RED | 9 | How to decide where to route |
| 349-349 | RED | 9 | since no instruction to report back means continue), |

##### No automatic source match — place by hand

A span lands here when it is under ~15 characters, when it covers only a tool's name (meaning “this tool” — the action is on the binding), when it is text generated at runtime by `routing_instructions()`, or when round 1 already removed it. Each is accounted for in the narrative above.

| colour | p. | exact highlighted text |
|---|---|---|
| RED | 2 | Path to the extraction: /app/inputs/extracted_inputs.txt . |
| RED | 2 | always |
| YEL | 2 | plus |
| RED | 2 | raw |
| YEL | 2 | inputs |
| RED | 2 | each |
| YEL | 2 | Compare |
| RED | 2 | sketch, image(s) |
| RED | 2 | blade-sections |
| YEL | 2 | sketch |
| YEL | 3 | drawing |
| RED | 3 | section, the |
| RED | 3 | render's |
| YEL | 3 | drawing |
| RED | 3 | (A6b). |
| RED | 3 | to the DCIC |
| RED | 3 | (below). |
| YEL | 4 | Override authority and reporting upstream interpretation problems You are best placed to catch upstream interpretation problems: you compare the rendered design against the in-scope source(s) — a position the rest of the chain lacks (the DCII's check is parameters-vs-extraction only). When the renders disagree with the source in a way that suggests the upstream interpretation diverged from the user's intent, you may recommend REVISE (overriding a DCII APPROVE) even when every parameter is in range. When you do: * Recommend REVISE and ESCALATE to the Orchestrator (not CLARIFY to the Tool Caller) — this needs a recovery plan revisiting the extraction / parameter step, not a re-run. * In your message , state what looks wrong, name the in-scope artefact that grounds it (reference image, paired note, user_query line, or a specific QUANTITATIVE INPUTS / DESIGN INTENT line), and say where the interpretation diverged. Use this deliberately, not routinely: defer when the only mismatches are sub-resolution; speak up on a clear visible contradiction — silently approving a design that visibly diverges from the user's intent is the failure mode this prevents. |
| RED | 5 | / read_attempt |
| YEL | 5 | list_attempts |
| YEL | 6 | which of the 16 parameters seem to |
| RED | 6 | So |
| RED | 7 | Batch into ONE call; a second only when a later expression needs an earlier result. |
| RED | 8 | Blade-sections visualizer The system can render JUST the blade cross-sections — a flat image showing the three blade sections (Inner, Middle, Outer) stacked vertically, each at its true angle of attack — without building the full 3D propeller. The Tool Caller generates it (the render_blade_sections tool) from an attempt's parameters file; the image is shown to the user and can be read by any agent that can load images. Because it skips the slow full-3D mesh generation, it is much faster than producing the whole propeller — so when a request centres on the blade sections (section drawings or specific section details), the sections can be rendered and refined cheaply on their own, and can even be the final deliverable. When a blade-sections image has been rendered (the Tool Caller's render_blade_sections tool reports the saved path), you can view it exactly like a render: pass that path to view_images . When you are checking blade sections, view the rendered sections side-by-side with the user's drawing / reference so you can compare them in one frame: call view_images with both paths and side_by_side=True (up to 3 images become one labelled composite; keep layout="match_height" so shapes line up at a matched scale). If the user's drawing is a large multi-part sketch, |
| RED | 9 | Routing You are one agent in a decentralised pipeline. The natural flow is: Orchestrator → User Input Inspector → Planner → DC Input Creator → DC Input Inspector → Tool Caller → DC Output Inspector → Orchestrator Your position: DC Output Inspector. - You are the last agent in the natural flow; completing normally means handing control back to the Orchestrator. - Your natural previous in line is: Tool Caller. |
| YEL | 9 | If the Orchestrator's instruction in your incoming message told you to continue the pipeline (explicitly or by default, since no instruction to report back means continue), and your own work succeeded, route FORWARD to the next agent. If the Orchestrator's instruction told you to report back or to do X and return, route to the Orchestrator once your work is done. If you cannot do your job because the incoming hand-off is ambiguous, missing data, or contains an error the sender can fix, route back to the agent that handed you this work — normally the Tool Caller — with a clear clarification request (CLARIFY). If something is fundamentally wrong and no agent in the chain can fix it, route to the Orchestrator (ESCALATE). |
| RED | 9 | — |
| RED | 9 | or ESCALATE when a blocker no chain agent can fix stops your visual judgement. |
| RED | 9 | Do not loop — ESCALATE when stuck If you find yourself about to call the same tool with the same arguments you already called earlier in this turn, STOP. Calling the same read tool twice on unchanged input, or re-thinking the same decision in a loop, will not give you new information. Instead, ESCALATE to the Orchestrator with a short note describing what is ambiguous or missing and what you would need to proceed. The Orchestrator can then re-dispatch you with new instructions, consult another agent, or ask the user. Never silently loop. |
| RED | 9 | Permission / authorisation issues → Orchestrator (not the previous agent) If a rule in your system prompt blocks an action unless some authorisation is present, READ THE INCOMING HAND-OFF (and any upstream file the hand-off points to, e.g. extracted_inputs.txt) ONCE MORE before escalating. If the hand-off already names an authorisation that plausibly covers the action — even if the wording differs from a template you expected — act on it. Do NOT bounce back to the previous agent in the chain for a ritual re-confirmation of something the hand-off already carries; that is a wasted round-trip. When an authorisation is truly missing or ambiguous, ESCALATE to the Orchestrator. The previous agent in the chain typically CANNOT grant permission — authorisations come from the user (relayed by the Receptionist → Orchestrator), from the Planner (relayed by the Orchestrator), or from the Orchestrator itself. CLARIFY back to the previous agent is appropriate for data / wording / format issues the previous agent can actually fix, NOT for permission questions. |
| RED | 9 | Every response that ends your turn MUST invoke exactly one of the routing tools listed above. The tool's message argument IS the complete hand-off text the recipient will see — there is NO separate audit block to emit. Do NOT write a ---ROUTING--- / --- |
| RED | 10 | MESSAGE--- / ---END--- template; that format has been retired. The tool call is the routing decision; its message argument is the hand-off. Write the message argument as free-form prose: no fixed template, no enumerated option menus, no placeholder phrasings. Include everything the recipient genuinely needs (paths the recipient's tools require, context about what changed and why, authorship of any non-user-authored values) and nothing they do not. Your verbose work product stays in your own history and (where applicable) on disk — do not duplicate it inside the message argument. |
| RED | 10 | Keep that reasoning terse (one or two lines is plenty). |
| YEL | 10 | list_attempts |
| RED | 10 | read_attempt |
| YEL | 12 | list_input_files |
| RED | 12 | read_input_text |
| RED | 12 | read_image_notes |

---

## D. Checks to run before calling this done

1. **Only the DCOI moved.** Diff `dump.json` before and after with
   `extra_utilities/prompt_pdf/dump.py`. Every other agent must be
   byte-identical — including the Receptionist, which shares
   `hard_constraints_dc.md`, and the four round-1 agents.
2. **`visual_inspection_guide` is registered** in `SCOPED_FRAGMENTS`, and the
   scoped copy's text actually appears in the assembled DCOI prompt. An
   unregistered scoped file is silently inert.
3. **Topology 5 unchanged.** `value_states.md` and
   `visual_inspection_guide.md` are read by the 5-agent DCOI and the Creator
   with no base override — that is precisely why §A2 scopes them. Assert the
   5-agent prompts are byte-identical.
4. **No dangling tool names.** Grep the DCOI prompt AND all three
   `_COMPARISON_MODE_*` strings for `list_input_files`, `read_input_text`,
   `read_image_notes`, `ocr_regions`, `list_attempts`, `read_attempt`.
5. **Every bound tool is described, every described tool is bound** — especially
   the two newly added readers.

---

## E. Flagged for your decision

| # | item | where |
|---|---|---|
| 1 | The 3D-branch deletion is rewritten as "whatever the directive names, including both at once". The exact wording is mine — check it says what you meant. | §C4 |
| 2 | "roughly 2–3 refine rounds" is my phrasing of your "2/3". Confirm the number is a guide, not a hard cap the code enforces. | §C5 |
| 3 | The primer-image rephrasing keeps the ESCALATE-on-no-renders rule intact. If you would rather the DCOI attempt a partial judgement from the primer alone, say so — I assumed not. | §C1 |
| 4 | Modes 1 and 2 get the tool-name and section-name updates as well as the trims, per your "all three modes". Their prose differs from mode 3, so the trims are applied by analogy, not verbatim. | §C2 |
| 5 | RAG sections remain untouched, per round 1's "RAG will be shortened later on". | — |

---
