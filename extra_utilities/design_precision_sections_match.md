# Precision Sections-Matching — Consolidated Design Spec

**Status:** DESIGN — approved decisions captured, not yet implemented. 2026-07-15 (rev 3).
**Origin:** `LOG_systemNotCheckingCrossSections.txt` (session `web_20260714_140221`). The
system did not iterate to match the user's precise blade-section drawings before generating
the 3D geometry, despite an explicit *"recreate as precisely as possible / make as many
attempts as needed / match the details in the sketches"* mandate.

> **rev 2 changes:** the section comparison is now **render vs a crop of the user's sketch**
> (not a synthetic "clean redraw"), so the old A4 "verify the redraw" step dissolves; precision
> is **not a flag** but a **Planner-issued verbose directive** carried by a new general
> **Component C — standing-directives propagation**; the DCOI's composite is **saved + shown in
> chat**.

---

## 1. Problem

From the log: on the **first** turn the sections-first loop ran exactly ONCE — DCIC wrote
params → Tool Caller rendered the blade sections → the DCOI **approved that first render** →
straight to full 3D. The user pushed back (*"they are not matching closely with my sketch"*);
only THEN did it iterate (attempts 2–4).

Root causes:

- **A — DCOI approval bar too low.** Approved on "ordering + broad proportions"; explicitly
  declined to judge shape (*"camber ... thickness/max-position ... not resolvable from the render
  resolution; those remain covered by the parameter authorisation chain"*).
- **B — Section shapes never extracted.** `0346_3.png` has labelled Inner/Middle/Outer Blade
  Section drawings, but the UII extracted only chords + angles; the airfoil-shape params
  (`*Thickness`, `*MaxPos`, `*Camber`) were left UNLOCKED for the DCIC to pick.
- **D — "As many attempts as needed" = permission, not mandate.** Recorded as "vary as needed /
  smallest change to stay viable" → default was approve-early.
- **C — (compounding) comparison render low-fidelity.** Cross-section render drawn small (~421 px)
  and compressed (`CROSS_SECTIONS_DEGREE` 74 → ~346 px model-facing). Secondary to A/B/D.
- **E — (ceiling) NACA airfoil model.** The thickness/camber/max-position parameterization can
  only approximate a freehand curve; never surfaced — silently approved.

---

## 2. Goals / non-goals

**Goals:** on a precision mandate, actively iterate the section shapes until close or provably at
the configurator's limit — autonomously, no asking back; a legible apples-to-apples comparison
image; honest ceiling reporting; **important instructions that must survive the whole agent chain
never get silently dropped**. **Non-goals:** changing locked numbers; replacing the NACA
parameterization; coordinate-perfect reproduction.

---

## 3. Three components

- **A. Precision-matching loop (GENERAL)** — the workflow behaviour: *iterate the relevant unlocked
  params until the relevant render matches the relevant user-provided reference.* Blade sections
  and the full 3D are two **instances**; the **Planner picks which comparison(s) run per request**,
  based on what the user provided. Sections (§4) is the worked example because it's the cheap,
  common case; §4.0 states the generalization.
- **B. Unified image view/crop/stitch tool** — one image tool for every image agent; the loop's
  measuring stick.
- **C. Standing-directives propagation** — a *general* mechanism so a Planner directive (precision
  being its first user) survives Planner → … → DCOI intact.

---

## 4. Component A — precision-matching loop (general; sections is the worked example)

### A0. Generalization
The loop is **not sections-specific**. It is one capability — *iterate the relevant unlocked params
until the relevant render matches the relevant user-provided reference* — and it applies to **any**
render↔reference pair:
- section drawings → match the **sections render** (cheap: `render_blade_sections` only);
- a top / side / perspective sketch of the whole propeller → match that **3D render view** (expensive:
  regenerates the mesh each round);
- several references → a **sequence** of matches.

**The Planner decides, per request + what the user provided, which comparison(s) to run** and in
what order, and encodes that in the precision directive (§C). *(Q "Planner decides per request".)*
When both cheap and expensive references exist, run **cheap first, then expensive** — converge the
sections cheaply, then carry that into the full 3D. *(Q "cheap first, then expensive".)* Expensive
3D loops use the **same ~8 cap + iterate-if-lever-else-report** (§A6/§A6b) — the few 3D levers +
plateau keep them bounded. *(Q "same ~8 cap".)*

Everything below (A1–A7) is written for the **sections instance**; the same machinery — extract a
target (A2), compare render↔reference (A3), forced iterate (A5), DCOI-judged/code-capped
termination (A6), honest ceiling report (A7) — applies unchanged to the 3D instance, with "sections
render" → "3D view render", "sketch sections crop" → "the relevant sketch view crop", and "shape
params" → "whatever unlocked params move the mismatched aspect".

### A1. Trigger + the precision directive (NOT a flag)
The **UII** captures the user's precision demand in the extraction as **verbose text** (faithful
to intent — *not* a boolean). The **Planner** reads it, **decides** this is a precision job, and
**issues a verbose verbatim directive** into the Standing-Directives block (§C) — e.g. *"PRECISION
JOB: iterate the blade-section shapes against the user's cropped sketch until they closely match
or the configurator's airfoil model is provably at its limit; the DCOI must NOT approve on
proportions alone and must NOT approve the first render; vary only the unlocked shape params;
preserve all locked numbers."* That directive rides the chain to the DCOI, guaranteed by §C.
There is **no `precision_mode` flag**. *(Q "UII infers"; user note "Planner-decided verbatim
command, propagated via messages, must not be lost".)*

### A2. Warm-start shape estimate (extract)
The UII visually **estimates initial airfoil-shape params** (`*Thickness/MaxPos/Camber`) from the
drawings to **seed the DCIC's first attempt** so the first render starts close. These are a
starting point, *not* a rendered target — and deliberately a **rough eyeball estimate**: the loop
refines it against the sketch, so the UII need not carefully read the grid. The UII also records
**coarse crop regions** (§B5). *(Q2 "extract + refine"; "model-estimated params"; "rough eyeball,
let the loop refine".)*

### A3. The comparison — render vs a crop of your sketch
The Tool Caller renders the blade sections from the DCIC's **current** params (one render). The
**DCOI**, using the unified tool (§B), **stitches [that render + a crop of the user's sketch's
sections region] side-by-side** and judges the render against the actual drawing. The DCOI decides
what to compare; the Tool Caller only *produces* render files, it does not composite. There is
**no synthetic "redraw"** — your sketch is the reference. The comparison is **whole-strip**: one
composite per round holding the full 3-section render + the full sketch-sections crop; the DCOI
maps inner/middle/outer by the coloured labels (no per-section splitting). *(Q "your sketch
(cropped)"; "whole-strip, map by label/colour".)* Implementation note (owned):
`render_blade_sections` gets a larger, fixed native resolution so the render half stays legible
after the crop is scale-matched to it.

### A4. *(dissolved)*
Because the comparison is directly against the user's sketch, there is no separate reconstruction
to verify and nothing to "re-estimate" — the sketch is the ground truth throughout. (This step
existed only in the earlier "clean redraw" design.)

### A5. Iterate (forced by the standing directive)
Bound by the precision directive (§C), the DCOI may **not** approve on proportions/ordering and
**not** approve the first render. It **describes the visual gap in free-form prose** ("inner too
thin, leading edge too pointed, camber too shallow") and the **DCIC translates that into
shape-param moves** — adjusting the **shape params only** (locked numbers preserved) → re-render →
re-compare. Both roles are preserved; no agent reaches into another's job. *(Q "describe the visual
gap".)*

**Routing — tight cycle.** Once the Planner has set up the precision job, each round is a **tight
loop**: DCOI feedback → DCIC → render → DCOI, with **no re-planning per round**. A **full DCII
validation pass** runs periodically (≈ every 3 rounds) and **before finalizing**, to catch param
drift. *(Q "tight cycle + periodic full check".)*

### A6. Termination (autonomous — never ask back)
Stop when ANY of: **Satisfied** (DCOI judges render ≈ sketch) or **Plateau** (the DCOI reports no
meaningful improvement across ~2 consecutive rounds = the configurator's airfoil ceiling) — both
**DCOI judgments in prose** — or the **~8-round hard cap**, a **code backstop in `step_caps`**
(like the existing `MAX_*` guards) so a stuck loop can never run forever regardless of prose.
*(Q "DCOI judges, code caps"; "plateau + generous cap".)* Always report the residual + whether it
hit the model's limit.

### A6b. Full-3D precision check
After the sections converge, generate the full 3D, then the DCOI **precision-checks the 3D renders
against the sketch's top/side views** (same view tool + a UII crop region). If an **unlocked** lever
can improve the match (e.g. a section's radial position affecting the planform), iterate on it; if
the mismatch traces to your **locked** numbers or the configurator's limits, **report it honestly
without touching locked values**. *(Q "3D also precision-checked"; "iterate if a lever exists, else
report".)*

### A7. Reporting
The Receptionist states the achieved fidelity and, if it stopped at the NACA-airfoil ceiling,
**says so explicitly** rather than silently approving.

### A — components to change
- `agents/user_input_inspector/*` (+ prompt): capture the precision demand (verbose) + estimate
  warm-start shape params + record coarse crop regions.
- `agents/planner/*` (+ prompt): decide precision jobs; **issue the standing directive** (§C).
- `agents/dc_output_inspector/*` (+ prompt): obey the standing precision directive; strict
  shape-fidelity bar; stitch render + sketch-crop via §B; plateau reporting.
- `agents/dc_input_creator/*` (+ prompt): shape-only adjustments toward the DCOI's feedback;
  preserve locked numbers.
- `tools/render_blade_sections/*` (`draw.py`): larger fixed native resolution for legible crops.
- Extraction schema: precision demand (verbose) + warm-start shape target + sketch-region records.
- `agents/step_caps.py`: the sections-loop cap.

---

## 5. Component B — unified image view/crop/stitch tool

### B1. Replaces + scope
Replaces `load_render_images` + `load_input_images` with ONE `view_images` tool for **all
image-loading agents** (UII, Planner, DCII, DCOI). `ocr_regions` + the non-visual tools stay.

### B2. Shape (indicative)
`view_images(items, side_by_side=False, layout="match_height", extract_text=<auto>)`, each `item`
= `{path, region?}`, `region` = optional **coarse** normalized crop box `[x0,y0,x1,y1]`.

### B3. Modes
- **Default = separate full-size blocks** (no 3-view regression; >3 allowed).
- **`side_by_side=True` → one composite**, capped at **3**.
- **Per-call `layout`**: `match_height` (shape comparison; same-scale renders line up) or `native`
  (detail).
- **Styling** = approved example-A: labelled gray header bar per panel, thin borders, white gaps.

### B4. OCR
Optional; user-image paths (auto-detected: `inputs/` = user, `attempts/` = render) get OCR text
attached; renders never OCR'd; toggle via `extract_text`.

### B5. Crop region (per-path, UII-owned)
Each item may carry a **coarse** normalized crop box, applied before stitching. Only the **UII**
determines these boxes — recorded at extraction (which image, coarse box, what it contains).
Downstream agents pass `{sketch_path, region}` using the UII's box; they never guess coordinates.
Coarse because VLMs are unreliable at tight pixel boxes. *(Empirically shown by
`example_images/stitched_examples/`: a whole-page sketch stitches illegibly; a coarse crop fixes
it.)*

### B6. Composite output — saved + shown
The DCOI's composite is **saved to the attempt folder** AND **surfaced in the chat UI**, so the
user sees exactly what was compared (transparent + debuggable). Built at a resolution that survives
the vision-API downscaling + our compression (long edge ≈ within the model cap; precision-mode
comparison images not over-compressed). *(Q "saved + shown in chat".)*

### B — components to change
`agents/shared/user_inputs_tool.py` (the `view_images` tool: compose + crop + OCR + layout; retire
the two old loaders for image agents); a PIL stitch/crop helper (scratchpad `stitch_proto.py` is
the basis); image-agent prompts; the chat-UI surface for the saved composite; the flowchart caption.

---

## 6. Component C — standing-directives propagation (general)

### C1. The block
Every inter-agent hand-off carries a reserved, clearly-marked block:
`── STANDING DIRECTIVES (copy verbatim to the next agent) ──`.

### C2. Issue + carry
Only the **Planner registers** standing directives (planning authority). **Every other agent
copies the block forward verbatim** — it may add its own prose around it, but must never drop or
paraphrase it. *(Q "Planner-issued, others carry".)*

### C3. Orchestrator backstop (re-stamp on loss)
The **Orchestrator** (full chain visibility via `CHAIN_ACCESS`) **detects when a hand-off dropped
or degraded** the block and re-stamps the directives; it does *not* re-inject unconditionally.
*(Q "re-stamp only on loss".)* This needs loss-detection: compare each mediated hand-off against
the known active directives.

### C4. General
Any must-not-be-lost instruction uses this mechanism; the **precision directive is the first
user**. *(Q "general standing-directives".)*

### C — components to change
`agents/shared/routing_tools.py` (hand-off assembly carries the block); `agents/orchestrator/*`
(loss-detection + re-stamp; track active directives); `agents/planner/*` (register directives);
ALL agent prompts (the copy-verbatim rule).

---

## 7. Decisions log

| # | Question | Choice |
|---|---|---|
| 1 | Root cause | Both — approval logic + shape extraction |
| 2 | Match mechanism | Both — extract (warm start) then refine |
| 3 | Precision ⇒ force iteration? | Yes |
| 4 | Compare against | **Your sketch (cropped)** — no synthetic redraw |
| 5 | Layout | Side-by-side |
| 6 | Warm-start target | Model-estimated params (seed only) |
| 7 | When to stop | Satisfied / plateau / cap (~8), autonomous |
| 8 | Wrong target | *(dissolved — sketch is the reference)* |
| 9 | Tool scope | All image-loading agents |
| 10 | Composite | A flag (default = separate) |
| 11 | OCR | Optional, inside the tool |
| 12 | Composite layout | Agent chooses per call (match-height / native) |
| 13 | Path cap | 3 only when compositing |
| 14 | Stitch styling | Keep example-A |
| 15 | Sketch comparison | Always crop the region |
| 16 | Crop-region source | UII, coarse box |
| 17 | Crop location | Parameter of the view tool |
| 18 | precision represented as | **Verbose Planner directive, NOT a flag** |
| 19 | Directive carried by | **Component C** (standing-directives block) |
| 20 | Composite output | Saved + shown in chat |
| 21 | Anti-loss mechanism | Block + Orchestrator backstop |
| 22 | Backstop activeness | Re-stamp only on detected loss |
| 23 | Directive source | Planner-issued; others carry verbatim |
| 24 | Directive scope | General (any must-not-be-lost instruction) |
| 25 | Comparison granularity | Whole-strip (DCOI maps by label/colour) |
| 26 | Feedback style | DCOI describes the visual gap; DCIC translates |
| 27 | Warm-start effort | Rough eyeball; the loop refines |
| 28 | Loop routing | Tight cycle + periodic full DCII check |
| 29 | Termination enforcement | DCOI judges; code cap backstop (~8) |
| 30 | 3D check | 3D also precision-checked vs top/side views |
| 31 | 3D mismatch | Iterate if unlocked lever, else report honestly |
| 32 | Loop scope | GENERAL — any render↔reference, not just sections |
| 33 | Comparison selection | Planner decides per request + provided references |
| 34 | Multi-ref sequencing | Cheap (sections) first, then expensive (3D) |

---

## 8. Open items / defaults / risks

**Defaults to set (flag to change):** normalized crop boxes; composite long edge ≈ 1500 px;
plateau = "no meaningful improvement" ×2 rounds; warm-start estimation in UII, strict bar in DCOI;
the composite saved under the attempt folder.

**Risks / hard parts:**
- **VLM shape-estimation + comparison** — the warm start + the DCOI's render-vs-sketch judgment are
  both vision-model calls on freehand drawings; the forced loop + strict bar are the mitigation.
- **NACA ceiling** — some drawn shapes unreachable; A7 must report it.
- **Cross-style comparison** — clean render vs freehand sketch; the crop + match-height layout help,
  but the DCOI still normalises by eye.
- **Loss-detection reliability (C3)** — the Orchestrator must reliably notice a dropped directive;
  false negatives silently lose it (the failure mode we're fixing). Worth erring toward
  re-stamping when unsure.
- **Token cost** — precision runs render + judge many times at higher fidelity; plateau + cap bound
  it.

---

## 9. Suggested phasing (buildable incrementally)

1. **C — standing-directives propagation.** Infrastructure the loop's reliability depends on;
   independently valuable. Block convention + Planner issue + Orchestrator loss-detection.
2. **B — the unified view/crop/stitch tool.** Independently useful + testable; ships the measuring
   stick.
3. **A2 + A3** — UII warm-start estimation + `render_blade_sections` legible-crop resolution +
   DCOI render-vs-sketch-crop comparison.
4. **A1 + A5 + A6** — Planner precision directive (via C) + the forced tight-cycle loop + the
   DCOI-judged / code-capped termination.
5. **A6b + A7** — full-3D precision check (iterate unlocked levers, else report) + honest ceiling
   reporting.

Each phase is shippable and reviewable on its own.
