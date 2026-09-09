# Topology 3 — Stage 9, round 2: the owner's PDF mark-up, turned into edits

Source: `3agent_system_prompts_v2.pdf` (the v2 build of the assembled 3-agent
prompts), annotated by the owner.

**Mark-up key** (owner's, as stated): RED = remove · YELLOW = modify/edit ·
black hand-typed text = the replacement wording, or a comment about what to
move where.

**Extraction method.** 46 highlights carry a colour. The typed comments are
NOT PDF annotations — they are flattened page content, separable only by a
font census (Arial, pure black, 4–12 pt, against the document's own
SegoeUI/Consolas at `#1a1a1a`). 17 typed notes were recovered that way, and
each was matched to the highlight nearest it on the page.

**Scope, per the owner.** Only the Receptionist, the Planner and the Design
Engineer. The Requirements Analyst and everything after it carry **zero**
annotations and are deliberately untouched here. The Receptionist also
carries zero annotations — it is in scope only for the duplication
question (§O).

| PDF pages | agent | annotated? |
|---|---|---|
| 5-12 | Receptionist | no marks |
| 13-22 | Planner | p.13, 15, 16 |
| 23-37 | Design Engineer | p.23, 24, 26, 27, 29, 30, 31 |
| 38-53 | Requirements Analyst | *out of scope this round* |
| 54-61 | Database Handler | *out of scope this round* |

**How to read the tables.** Every row names the file and the CURRENT line
numbers in worktree `rebuild-3-agent-topology-6ca792` at commit `069033c`.
Line numbers shift as edits land — apply top-down within a file, or
re-locate by the quoted text.

**ALL APPLIED.** Every decision in this document (R1-R21) is in the
worktree. See **§Z — the application**, at the end, for what ran and what
was verified.

> ⚠ **Every line number below predates the application.** They describe
> the tree at `069033c`. Re-locate by the quoted text, not by number.

---

## §A — Planner, "Available Agents" (PDF p.13)

File: `agents/3agent/prompt_fragments/available_agents_planner_3agents.md`.
It still carries the Stage-4 shape: **two RA bullets and two DE bullets**,
one of each from each topology-5 parent.

| # | lines | mark | edit |
|---|---|---|---|
| **A1** | 6-13 | YEL + note | **Merge the two RA bullets into one**, with the *extraction* text (L11-13, the yellow one) placed **BEFORE** the *visual-analysis* text (L6-10). Owner's note: *"Add the RA's second paragraph to the previous paragraph about the RA. This yellow-highlighted text should be put BEFORE the other description 'loads the rendered PNGs…'"* |
| **A2** | 14-28 | YEL + note | **Merge the two DE bullets into one.** Owner's note: *"Add the DE's first paragraph to the second."* |
| **A3** | 19 | YEL | `works from` → `uses` |
| **A4** | 21 | YEL | `It can be asked for` → `for calling` |
| **A5** | 19-21 | RED | delete `— the record of the $parameter_count parameter values the DE authored.` |
| **A6** | 25-26 | RED | delete `and (if enabled) the quality-check numbers.` |

**A1 — proposed AFTER**

    - **Requirements Analyst (RA)**: reads user_query.txt and any other
      input files in the inputs directory (text, sketches/images),
      extracts design values, intent, and constraints.  It also loads the
      rendered PNGs using the paths supplied by the Design Engineer and
      performs a qualitative visual analysis, calling you to approve the
      design or to flag defects and problems.  Cannot measure precise
      dimensions; comments on overall shape, proportions, and feature count.

**A2 + A3 + A4 + A5 + A6 — proposed AFTER**

    - **Design Engineer (DE)**: writes the complete $parameter_count-parameter
      set to parameters.json.  This is the only agent that authors concrete
      numeric parameter values.  Translates qualitative guidance (a directive
      of the form "increase <param X>") into numbers.  It then uses that
      attempt's ``parameters.json``<<BSV_ON>> for calling
      ``render_blade_sections`` — the three blade cross-sections alone, with
      no 3D mesh<</BSV_ON>>.  Or it points ``generate_and_render_propeller``
      at that ``parameters.json`` and calls it once — the tool reads the
      record itself and produces the mesh file and the image renders of the
      mesh.  Also has a ``calculate`` tool for arithmetic.
      Reports the produced file paths for the Requirements Analyst.

✅ **A2 ordering resolved — see R20** (Option A, authoring first).

> ⚠ **The same duplicated bullets live in a second file.** `$available_agents`
> resolves to `available_agents_planner_3agents.md` for the Planner and to
> `available_agents_3agents.md` for the **Database Handler**. The unscoped
> copy has the identical two-RA / two-DE split (L8-15, L16-29). It was not
> annotated because the DH's prompt starts on p.54, outside the reviewed
> range. Left alone, the two files disagree about who does what.
> ✅ **Resolved — see R12.**

---

## §B — Planner, Role 1 (PDF p.15)

File: `agents/3agent/planner/prompt_3agents.md`.

| # | line | mark | edit |
|---|---|---|---|
| **B1** | 174 | RED + YEL + note | heading: delete `meaningful`; `content` → `images or complex content` |
| **B2** | 181-182 | YEL + note | rephrase and **expand** — see below |
| **B3** | 184 | YEL + note | `new content` → `new complex content` |
| **B4** | 196 | YEL + note | `is already captured in the extraction` → `the system knows or that the system already analyzed` |
| **B5** | 198 | YEL + note | `extraction` → `analysis of inputs` |
| **B6** | 202-203 | RED | delete the whole sentence |

**B1**

* BEFORE — `## Role 1 — Route through the Requirements Analyst on new meaningful user content`
* AFTER — `## Role 1 — Route through the Requirements Analyst on new user images or complex content`

**B2** — owner's note: *"'and it contains content that the RA should analyze
further, or that only the RA can analyze (e.g. images), the RA must be called
first'. Rephrase this and expand this accordingly."*

* BEFORE (L181-182) — `Whenever the user has supplied NEW meaningful content this turn, the RA must see it.`
* AFTER (proposed):

      Whenever the user has supplied NEW content this turn AND it contains
      material the Requirements Analyst should analyse further — or that ONLY
      the RA can analyse (images, sketches, drawings) — the RA must be called
      first.  Plain numbers and plain prose the DE can already act on do
      not need the RA.

  The last sentence is the "expand accordingly" half: it is what tells the
  Planner when NOT to call the RA. ✅ **Approved with the owner's
  correction — see R21.**

**B4 / B5**

* BEFORE (L196-198):

      A repeat of what is already captured in the extraction does not require
      a RA rewrite.  Use judgement; when in doubt, route through the RA so
      the extraction stays current.

* AFTER:

      A repeat of what the system knows or that the system already analyzed
      does not require a RA rewrite.  Use judgement; when in doubt, route
      through the RA so the analysis of inputs stays current.

**B6** — delete `This does NOT apply to an extraction-only ask: those always go through the RA first, even when the extraction looks current.`

---

## §C — Planner, "Extraction-only asks" (PDF p.16)

| # | lines | mark | edit |
|---|---|---|---|
| **C1** | 211-215 | YEL + RED + note | rewrite the routing sentence; delete `Deliver the answer through the Receptionist once that work is done.` |
| **C2** | 217 | YEL + note | expand the no-geometry rule to name the standing directive AND the section renders |

Owner's notes, verbatim:

* *"The Design Engineer is the agent required to do calculations and assign specific values to all the non-locked user inputs. The Requirements Analyst analyzes images, and extracts complex info from the user inputs."*
* *"For these requests that ask to extract or choose design parameters, and do not ask for any design generated, specify to the DE that NO GEOMETRY needs to be generated. Same goes for the blade section renders."*

BEFORE (L211-217):

    Route to the Requirements Analyst FIRST, so the inputs are actually
    extracted.  Then, if the ask needs any
    calculation on the extracted values, route to the Design Engineer with a
    standing directive that says VALUES ONLY (no geometry).  Deliver the
    answer through the Receptionist once that work is done.

    Do NOT let the ask reach GEOMETRY: no mesh, no renders.

AFTER (proposed):

    The Design Engineer is the agent that does the calculations and assigns
    specific values to every non-locked user input.  The Requirements
    Analyst analyses images and extracts complex information from the user's
    inputs.  Route through the RA first only when the ask needs that — an
    image, a sketch, anything only the RA can read.  Then route to the
    Design Engineer with a standing directive that says VALUES ONLY, and
    once the final set of parameters is obtained, deliver the answer
    through the Receptionist as usual.

    For any request that asks to extract or choose design parameters and
    does NOT ask for a design to be generated, the standing directive must
    say plainly that NO GEOMETRY is to be generated — no mesh, no 3D
    renders, and no blade-section renders either.

✅ **Resolved — see R10.**

---

## §D — Planner, the three value states (PDF p.16)

File: `agents/3agent/prompt_fragments/value_states_planner_3agents.md`.

| # | lines | mark | edit |
|---|---|---|---|
| **D1** | 1-2 | RED | delete `read off the QUANTITATIVE INPUTS the Requirements Analyst reported:` |

* BEFORE — `Every value the user could have given is in exactly one of three states, read off the QUANTITATIVE INPUTS the Requirements Analyst reported:`
* AFTER — `Every value the user could have given is in exactly one of three states:`

---

## §E — Design Engineer, the utility-tool list (PDF p.23)

Owner's note, with no highlight: *"as first bullet point here, there should be
the tool to create a new attempt"*.

File: `agents/3agent/tools_config/tool_inventory_design_engineer_3agents.md`.

| # | lines | edit |
|---|---|---|
| **E1** | 1 | insert `new_attempt_parameters` as bullet **1**, renumbering the rest |

Proposed insert:

    1. **new_attempt_parameters(parameters, slug, description)** — open a NEW
       attempt folder and write the complete parameter set into it, in one
       call.  Returns the attempt's NUMBER and absolute folder path.

> ⚠ The numbering in this fragment is written by hand around `<<BSV_ON>>` /
> `<<BSV_OFF>>` markers (L1, L5, L12, L13), so every number must be shifted in
> BOTH branches or the list mis-numbers itself the moment the blade-sections
> visualizer is toggled.
>
> ✅ The overlap with the DE prompt's own two mentions is resolved in
> **R14** — the inventory keeps the mechanics, the policy section keeps the
> cadence.

---

## §F — Design Engineer, the parameter list is printed TWICE (PDF p.24)

File: `agents/3agent/dc_config/parameters_design_engineer_3agents.md` — a
Stage-4 mechanical concatenation, so the 16-parameter table appears at
L16-48 and again at L52-74. The assembled prompt carries both.

RED covers L16-50 — the FIRST copy.

| # | lines | mark | edit |
|---|---|---|---|
| **F1** | 16-50 | RED | delete one of the two copies |

✅ **Resolved — see R2.**  The owner agreed to delete the SECOND
copy (L49-74) instead, so the superset survives.

---

## §G — Design Engineer, "Reading QUANTITATIVE INPUTS" (PDF p.26)

File: `agents/3agent/design_engineer/prompt_3agents.md`.

| # | lines | mark | edit |
|---|---|---|---|
| **G1** | 90-91 | YEL + RED + note | `QUANTITATIVE INPUTS contains two kinds of entry:` → `Every QUANTITATIVE INPUT can be of one of these two kinds:` |
| **G2** | 93 | RED | delete `The line names` |
| **G3** | 98 | RED | delete `The line describes` |

AFTER (L89-103):

    The user's inputs carry every numerical or quantisable value the user
    supplied.  Every QUANTITATIVE INPUT can be of one of these two kinds:

      * **Parameter-level entries.**  A quantity that is plainly one of the
        configurator's parameters, in that parameter's own unit — whatever
        words the user used for it ("average outer ring radius: 70 mm" is
        ``impellerRadius``).  The value maps DIRECTLY into that parameter's
        cell.
      * **Real-world-quantity entries.**  A real-world quantity in a unit /
        frame of reference that does not match a configurator parameter
        directly.  These ARE design intent, but they have no single cell in
        parameters.json — honour each as closely as practical or decline it
        with a reason, per "Real-world-quantity QUANTITATIVE INPUTS" below.

---

## §H — Design Engineer, the three value states (PDF p.26-27)

File: `agents/3agent/prompt_fragments/value_states_design_engineer_3agents.md`.

| # | line | mark | edit |
|---|---|---|---|
| **H1** | 4 | RED | delete `a value the user stated plainly there, with no marker.` |
| **H2** | 7-8 | RED | delete ``a value marked ``SOFT TARGET (goal: …; keep near … if free)``.`` |
| **H3** | 13 | RED | delete `a parameter absent from QUANTITATIVE INPUTS:` |

AFTER (L4-14):

    - **LOCKED** — the user fixed it.  LOCKED is not an absolute wall: it
      may change when an authorisation frees it (below).
    - **SOFT TARGET** — the user subordinated it to that goal, so it is
      neither locked nor free.  **The goal governs**: the marker itself IS
      the authorisation to move the value (within range) as far as the goal
      requires, and you never have to justify moving it.  The stated value
      is a reference, not a pull — it settles the parameter only when the
      goal does NOT bear on it.
    - **FREE** — it is your choice within range.

✅ **Resolved — see R3.**  The owner approved a rewrite that keeps every
recogniser while dropping the "read it off a section" framing.

---

## §I — Design Engineer, real-world quantities and conditionals (PDF p.27)

| # | lines | mark | edit |
|---|---|---|---|
| **I1** | 123 | YEL + note | `QUANTITATIVE INPUTS` → `the user` |
| **I2** | 166-167 | RED + YEL + note | delete `When the extraction records a relation the RA could not settle`; `),` → `:` |

**I1**

* BEFORE — `When QUANTITATIVE INPUTS states a real-world quantity in a unit / frame that does not match how the configurator stores it, …`
* AFTER — `When the user states a real-world quantity in a unit / frame that does not match how the configurator stores it, …`

**I2**

* BEFORE (L166-170):

      **Conditional inputs.**  When the extraction records a relation the RA
      could not settle ("if X is larger than Y…"), settle it once you have
      chosen the values it depends on: compute both sides with ``calculate``,
      …

* AFTER:

      **Conditional inputs** ("if X is larger than Y…"): settle it once you
      have chosen the values it depends on — compute both sides with
      ``calculate``, …

---

## §J — Design Engineer, the Tool-Caller half (PDF p.29)

File: `agents/3agent/design_engineer/prompt_3agents.md`. Six edits, four of
them moves.

| # | lines | mark | edit |
|---|---|---|---|
| **J1** | 326-341 | YEL + note | **MOVE** `## Loading parameters (IMPORTANT)` to sit **before** `## Hand-off to the next agent (IMPORTANT)` (currently L266) |
| **J2** | 273-274 ← 353-356 | YEL + note | **SUBSTITUTE** the 2-line example in the Hand-off section with the 3-line block from the Data-Flow section |
| **J3** | 348-351, 358-360 | RED | delete the `## Data Flow and reporting file paths (IMPORTANT)` heading, its lead-in paragraph, and its closing sentence |
| **J4** | 343-346 | RED + YEL + note | delete the `## HARD LIMITS — Do NOT` heading; **MOVE** its single bullet to be the **second** bullet of `**What you CANNOT fix — Hand back to the Planner immediately if asked:**` (L314) |
| **J5** | 322-324 | RED | delete the second `You are the Design Engineer for a $domain_description.` and the `<!-- SCAFFOLD JOIN … -->` marker above it |
| **J6** | 315-318 | RED | delete `or whether a design choice is "intentional".` and the whole `Engineering opinions…` bullet |
| **J7** | 362-365 | RED | delete the whole `## Using read_attempts` section |

**J2** — owner's note: *"use this list of 3 elements in the 'Hand-off to the
next agent (IMPORTANT)' instead of what that section currently has as
example"*, plus *"substituted (see later)"* written beside the 2-line block.

* BEFORE (L273-274):

      Current attempt <N>: <attempt-folder path you wrote into>
      Parameters file (newly written this cycle): <Current attempt>/parameters.json

* AFTER (taken verbatim from L353-356):

      Current attempt <N>: <attempt-folder path you wrote into>
      Mesh file: <absolute mesh path from the tool's return text>
      Render images:
        <absolute path of each render image, one per line>

✅ **Resolved — see R4.**

**J6** — AFTER (L314-319):

    **What you CANNOT fix — Hand back to the Planner immediately if asked:**
      - Questions about design intent and operating conditions.
      - You cannot edit meshes, perform boolean unions, weld vertices,
        remesh, fill holes, recompute normals, prune components, or change
        output filenames.  These operations do not exist in this workflow.
      - Anything none of your available sources can supply.

  (J4's moved bullet is shown here in its landing position, as bullet 2.)

✅ **Resolved — see R5**, which carries the full diff for §J.

---

## §K — Design Engineer, the hard-constraint blocks are printed TWICE (PDF p.30-31)

Both files are Stage-4 mechanical concatenations. RED covers the second copy
in each.

| # | file | lines | edit |
|---|---|---|---|
| **K1** | `agents/3agent/prompt_fragments/generic_constraints_design_engineer_3agents.md` | 45-73 | delete the `SCAFFOLD JOIN` marker and the whole second DOs/DON'Ts block |
| **K2** | `agents/3agent/dc_config/hard_constraints_dc_design_engineer_3agents.md` | 23-28 | delete the `SCAFFOLD JOIN` marker and the second `### Domain hard rules` block |

Both deletions are safe as marked — in each case the **first** copy is the
superset:

* K1 — the surviving DON'Ts say "hand back to **the Planner**"; the deleted
  copy said "hand the problem to whoever can resolve it" and "never address
  the user yourself" without naming where to route. The topology-3-correct
  wording is the one that survives.
* K2 — the surviving rule adds `and there is no mesh-editing capability:
  geometry changes only by changing them and regenerating. Reject invented
  parameters — they do not exist.`

---

## §L — Not annotated, but it belongs in this round: the SCAFFOLD banners

The PDF renders every prompt *exactly as the model receives it*. On p.23,
24, 30 and 31 you can read, inside the Design Engineer's own system prompt:

    <!-- SCAFFOLD - NOT THE FINAL TEXT ---
         … It is a concatenation, NOT a union: it states some concepts twice,
         and it can carry rules that contradict each other or name agents
         topology 3 never builds.
         Replaced WHOLESALE at Stage 9 … -->

Nothing in `agents/shared/prompts.py` strips HTML comments — verified. These
banners are **shipped to the model**, and they instruct it that its own
prompt is unreliable and self-contradictory.

**15 files still carry a banner, a `SCAFFOLD JOIN` marker, or both:**

    agents/3agent/dc_config/hard_constraints_dc_design_engineer_3agents.md
    agents/3agent/dc_config/hard_constraints_dc_requirements_analyst_3agents.md
    agents/3agent/dc_config/parameters_design_engineer_3agents.md
    agents/3agent/dc_config/parameters_requirements_analyst_3agents.md
    agents/3agent/dc_config/user_input_types/sketch_handling_requirements_analyst_3agents.md
    agents/3agent/design_engineer/prompt_3agents.md
    agents/3agent/prompt_fragments/generic_constraints_design_engineer_3agents.md
    agents/3agent/prompt_fragments/routing_design_engineer_3agents.md
    agents/3agent/prompt_fragments/routing_requirements_analyst_3agents.md
    agents/3agent/requirements_analyst/prompt_3agents.md
    agents/3agent/tools_config/blade_sections_visualizer_design_engineer_3agents.md
    agents/3agent/tools_config/blade_sections_visualizer_requirements_analyst_3agents.md
    agents/3agent/tools_config/database_search_design_engineer_3agents.md
    agents/3agent/tools_config/database_search_requirements_analyst_3agents.md
    agents/3agent/tools_config/hard_constraints_tools_requirements_analyst_3agents.md

| # | edit |
|---|---|
| **L1** | delete every `<!-- SCAFFOLD - NOT THE FINAL TEXT … -->` banner and every `<!-- SCAFFOLD JOIN … -->` marker across all 15 files |

Only 6 of the 15 are Design Engineer files; the rest belong to the
Requirements Analyst, which is out of scope for content but not for this —
the banner is not content, it is a build artefact. Recommend removing all 15
in one sweep regardless of scope.

---
---

# The three questions

---

## §R — RESOLVED (apply these)

Decisions taken in step 2. Each replaces an open item above; the item it
resolves has been struck from §M / §N / §O.

### R1 — the Design Engineer's attempt-folder deadlock  *(resolves X1, U13)*

**Problem.** `design_engineer/prompt_3agents.md` said, 15 lines apart in the
same section, that the DE OWNS attempt creation (L228) and that its incoming
hand-off MUST carry a `Current attempt <N>:` line it may not write outside of
(L234), and that it must hand back to the Planner if that line is missing
(L240). In topology 3 the hand-off comes from the Planner, which has no
attempt tool — so the DE was instructed to stop and ask for a line nobody
can produce, on the first cycle of every run.

**Decision (owner, agreed as proposed).** Keep ownership, delete the
inherited Tool-Caller guard, and fold its one useful clause into "No aimless
repeat".

**Edit** — `agents/3agent/design_engineer/prompt_3agents.md`, replace L216-242
in full:

    ## Attempt folders

    Each generation cycle is anchored on an attempt folder under
    ``attempts/`` — the canonical home for that cycle's
    ``parameters.json``, mesh, and renders.

    **You OWN attempt creation.**  Nobody hands you a folder: you open it
    yourself with ``new_attempt_parameters``, exactly one per generation —
    never a second attempt for the SAME generation.  That folder is the only
    one you write into this cycle.

    **No aimless repeat.**  Before you write, check whether an earlier attempt
    already holds the same set.  If one does, do NOT open another: name that
    attempt's number and folder path in your hand-off and let the chain work
    from it — NEW artefacts for the same set of values belong in that SAME
    attempt folder.  Re-running a tool on an attempt that already holds a mesh
    or renders is fine and needs no new attempt.

    **If you discover a real error AFTER writing**, that correction is a NEW
    generation: call ``new_attempt_parameters`` again for the corrected set.

Net −9 lines. The paragraph at L234-238 and the guard at L240-242 go
entirely; the clause *"Re-running a tool on an attempt that already holds a
mesh or renders is fine and needs no new attempt"* is the only survivor and
moves into "No aimless repeat", where it belongs.

⚠ The deleted guard is the last consumer of `Parameters file:` in the DE's
INCOMING direction. The outgoing direction is still open — see **N4 / X5**.

---

### R2 — the parameter list is printed twice  *(resolves N1 / F1, and half of U12)*

**Problem.** `dc_config/parameters_design_engineer_3agents.md` carries the
16-parameter table twice — L16-48 (DC Input Creator) and L52-74 (Tool
Caller). The PDF's RED span covers the FIRST copy, but that copy is a strict
superset: four pieces of information live only in it.

| line | present only in the first copy |
|---|---|
| 21 | `(The outer-ring HEIGHT is not a parameter — it is derived automatically to fit the outer blade section.)` |
| 31 | `middlePos`'s conversion — `radius = 4 + middlePos·(impellerRadius − 4) mm`; the second copy's L65 stops at `1 = tip [0.3; 0.7]` |
| 42-43 | `innerMaxPos / outerMaxPos move the CAMBER crest only, and do nothing at zero camber.` |
| 45-48 | `innerThickness / outerThickness … the chordwise position of maximum thickness is fixed at ~30% of chord and no parameter changes it.` |

The last two are corrective text: the parameter NAMES read as if they
controlled the position of maximum thickness, and those paragraphs exist to
stop a model concluding that.

**Decision (owner, agreed as proposed).** Delete the SECOND copy, not the
first.

**Edit** — `agents/3agent/dc_config/parameters_design_engineer_3agents.md`:
delete **L49-74** (the trailing blank line, the `<!-- SCAFFOLD JOIN … -->`
marker, and the whole second table). Keep L16-48 verbatim. With §L's banner
removal (L1-14) the file is then the first table and nothing else.

---

### R3 — the three value states keep their recognisers  *(resolves N2 / H1-H3)*

**Problem.** The three RED spans in
`prompt_fragments/value_states_design_engineer_3agents.md` are, in each
bullet, the clause that says how to RECOGNISE the state. Applied literally,
the DE would know what LOCKED / SOFT TARGET / FREE mean and have no way to
tell which one a value is in.

**Verified, not assumed:** the `SOFT TARGET` marker is still live under
topology 3. `requirements_analyst/prompt_3agents.md` L113-121 still tells the
RA to author it —

    - Radius of propeller: ~75 mm — SOFT TARGET (goal: match the sketched
      blade shape; keep near 75 mm if free, but vary freely to fit the shape)

Round 1 removed the extraction FILE, not the marker; the RA now reports it
verbally. L7-8 of this fragment is the only place in the DE's whole
assembled prompt that describes the string it must match.

**Decision (owner, approved as recommended).** Keep each recogniser, drop the
"read off the user's QUANTITATIVE INPUTS" section framing that the red was
aimed at, and re-anchor on what the user said / what the RA reported.

**Edit** — `agents/3agent/prompt_fragments/value_states_design_engineer_3agents.md`,
replace L1-14:

    Every value the user could have given is in exactly one of three states:

    - **LOCKED** — the user stated it plainly, with no marker and no goal
      attached.  The user fixed it.  LOCKED is not an absolute wall: it may
      change when an authorisation frees it (below).
    - **SOFT TARGET** — the user gave the value but subordinated it to a
      qualitative goal.  The Requirements Analyst reports these with an
      explicit marker naming the goal and how tightly to hold the number,
      e.g. ``Radius of propeller: ~75 mm — SOFT TARGET (goal: match the
      sketched blade shape; keep near 75 mm if free)``.  It is neither locked
      nor free.  **The goal governs**: the marker itself IS the authorisation
      to move the value (within range) as far as the goal requires, and you
      never have to justify moving it.  The stated value is a reference, not
      a pull — it settles the parameter only when the goal does NOT bear on
      it.
    - **FREE** — the user said nothing that fixes it: it is your choice
      within range.

Net −1 line on LOCKED and on FREE, +2 on SOFT TARGET. L15 onward
("Freeing a LOCKED value") is untouched.

---

### R4 — the hand-off block, and the two rules that depended on `Parameters file:`  *(resolves J2, N4, X5)*

**Problem.** J2 substitutes the 3-element list into the Hand-off section, which
drops the `Parameters file (newly written this cycle):` label. Three rules
depended on it. R1 already removed one (the L240-242 hand-back guard); two
remained:

| line | dependency |
|---|---|
| 276-278 | a paragraph whose whole purpose is explaining the phrase `(newly written this cycle)` |
| 334 | `call ``render_blade_sections`` with the ``Parameters file:`` path` |

No information is lost by dropping the label — `Current attempt <N>:` survives
and the parameters file is always `<Current attempt>/parameters.json`.

**Decision (owner, agreed as proposed).**

**Edit 1** — `design_engineer/prompt_3agents.md`, replace L270-278 (−3 lines):

    When you FORWARD, that message MUST carry these lines, each on its own
    line, with paths copied verbatim from THIS cycle's tool return texts:

        Current attempt <N>: <attempt-folder path you wrote into>
        Mesh file: <absolute mesh path from the tool's return text>
        Render images:
          <absolute path of each render image, one per line>

Two clauses are salvaged here from the Data-Flow section that §J3 deletes:
*"each on its own line"* (from L349-351, the only statement of the format) and
*"from THIS cycle's tool return texts"* — the compressed form of the RED
sentence at L358-360, keeping the anti-stale constraint without keeping the
sentence.

**Edit 2** — same file, L333-334, inside the `<<BSV_ON>>` region:

* BEFORE — `For the sections, call ``render_blade_sections`` with the ``Parameters file:`` path and generate no mesh and no 3D renders this cycle,`
* AFTER — `For the sections, call ``render_blade_sections`` with the path of the attempt's own ``parameters.json`` — the path ``new_attempt_parameters`` returned — and generate no mesh and no 3D renders this cycle,`

Consistent with R1: the DE knows the path because it opened the folder itself,
not because a label arrived.

---

### R5 — the Design Engineer's tail, restructured  *(resolves N5; applies J1, J3, J4, J5, J6, J7 and R4)*

**Problem.** `{render_check_library_block}` (L341) is a Python `.format()`
slot, not prose. It resolves to `off_3agents.md`, **an empty file**, because
`MESH_CHECKS = False` — so it is invisible in the annotated PDF, yet dropping
it raises `KeyError: 'render_check_library_block'` at agent construction, and
it becomes ~30 lines of live text the moment mesh checks are switched on.

**Decision (owner, agreed as proposed).** J1 moves L326-341 **as one block**,
slot included, so the slot stays with the geometry-tool instructions it
documents. The rest of §J is applied in the same pass because the marks
overlap the same 45 lines.

**Verified against the post-R9 file:** 366 lines → 339, net **−27**.
(Pre-sweep the same edit measured −30; three of those lines were the
`SCAFFOLD JOIN` marker and its blanks, which R9 already removed. An
earlier estimate of −41 in conversation was wrong.)

One judgement call beyond the mark-up: J6 would leave
`Questions about design intent, operating conditions,` on a dangling comma,
so it reads `design intent and operating conditions`.

**The exact edit:**

```diff
--- a/agents/3agent/design_engineer/prompt_3agents.md
+++ b/agents/3agent/design_engineer/prompt_3agents.md
@@ -248,19 +248,35 @@
 ``parameters.json`` into it, so validate your draft first: a rejected call
 creates nothing.
 
+## Loading parameters (IMPORTANT)
+Both geometry tools read ``parameters.json`` from disk themselves: pass the path of the attempt's own
+``parameters.json``, never values.  Generate from the FILE ON DISK, not from what
+you believe you wrote.
+
+<<BSV_ON>>**Render type — the directive decides, not you.**  The standing
+directive names which ONE output type this phase renders, and the hand-off may
+name it too.  For the sections, call ``render_blade_sections`` with the path
+of the attempt's own ``parameters.json`` — the path ``new_attempt_parameters``
+returned — and generate no mesh and no 3D renders this cycle,
+reporting the PNG path it returns under ``Render images:`` exactly as you would
+a 3D render; for the full 3D, call ``generate_and_render_propeller``.  Never
+both in one cycle.  If nothing names a type, hand back to the Planner
+(``call_planner``) and ask rather than choosing.<</BSV_ON>>
+
+
+{render_check_library_block}
+
 ## Hand-off to the next agent (IMPORTANT)
 Your note to the next agent IS the ``message`` argument of your routing
 call.  Do NOT repeat the parameter JSON in it — the tool put that on disk.
 
-When you FORWARD, that message MUST carry these lines
-with absolute paths, each copied verbatim from where you got it:
+When you FORWARD, that message MUST carry these lines, each on its own
+line, with paths copied verbatim from THIS cycle's tool return texts:
 
     Current attempt <N>: <attempt-folder path you wrote into>
-    Parameters file (newly written this cycle): <Current attempt>/parameters.json
-
-The phrase ``(newly written this cycle)`` tells the
-next agent that ``parameters.json`` has just been written and is the
-authoritative parameter set for this cycle.
+    Mesh file: <absolute mesh path from the tool's return text>
+    Render images:
+      <absolute path of each render image, one per line>
 
 Beyond those lines, write whatever prose is genuinely useful to
 the next agent.  If some of the values you just wrote did NOT come
@@ -297,54 +313,11 @@
 it out — re-issue the SAME call with that argument added.
 
 **What you CANNOT fix — Hand back to the Planner immediately if asked:**
-  - Questions about design intent, operating conditions, or whether a
-    design choice is "intentional".
-  - Engineering opinions about whether a user-specified value is a good
-    idea (style choices, taper / shape preferences, etc.).
+  - Questions about design intent and operating conditions.
+  - You cannot edit meshes, perform boolean unions, weld vertices,
+    remesh, fill holes, recompute normals, prune components, or change
+    output filenames.  These operations do not exist in this workflow.
   - Anything none of your available sources can supply.
-
-You are the Design Engineer for a $domain_description.
-
-## Loading parameters (IMPORTANT)
-Both geometry tools read ``parameters.json`` from disk themselves: pass the path of the attempt's own
-``parameters.json``, never values.  Generate from the FILE ON DISK, not from what
-you believe you wrote.
-
-<<BSV_ON>>**Render type — the directive decides, not you.**  The standing
-directive names which ONE output type this phase renders, and the hand-off may
-name it too.  For the sections, call ``render_blade_sections`` with the
-``Parameters file:`` path and generate no mesh and no 3D renders this cycle,
-reporting the PNG path it returns under ``Render images:`` exactly as you would
-a 3D render; for the full 3D, call ``generate_and_render_propeller``.  Never
-both in one cycle.  If nothing names a type, hand back to the Planner
-(``call_planner``) and ask rather than choosing.<</BSV_ON>>
-
-
-{render_check_library_block}
-
-## HARD LIMITS — Do NOT
-- You cannot edit meshes, perform boolean unions, weld vertices,
-  remesh, fill holes, recompute normals, prune components, or change
-  output filenames.  These operations do not exist in this workflow.
-
-## Data Flow and reporting file paths (IMPORTANT)
-Keep the ``message`` argument of your routing tool brief.  Three labels
-MUST appear when the relevant artifacts were produced this cycle, each
-on its own line, with paths copied verbatim from the tool return texts:
-
-    Current attempt <N>: <attempt-folder path you wrote into>
-    Mesh file: <absolute mesh path from the tool's return text>
-    Render images:
-      <absolute path of each render image, one per line>
-
-Say which artefacts the tool wrote this cycle, and report only the
-numbers from THIS cycle's return, never one you remember from an
-earlier cycle.
-
-## Using read_attempts
-``read_attempts(n)`` is how you see an attempt's numbers — you need it for
-the range check above.  Do not browse attempt after attempt, and do not use
-it to invent your own retry strategies; that is the Planner's call.
 
 ## Hard constraints
 $hard_constraints_generic
```

Read the `-` lines as three groups: **moved** (`## Loading parameters` →
`{render_check_library_block}`, the three `Mesh file:` / `Render images:`
lines, and the mesh-limits bullet all reappear above); **deleted as marked**
(the `SCAFFOLD JOIN` marker and the duplicate `You are the Design
Engineer…`, the `## HARD LIMITS — Do NOT` heading, the whole
`## Data Flow and reporting file paths` section, `## Using read_attempts`,
and J6's two bullet cuts); **reworded** (the one comma above).

`<<DCII_ONLY>>` at L287-297 is deliberately untouched — that is X6.

---

### R6 — the FORWARD move, and the two other statements of the RA trigger  *(withdraws X2, retires U6, resolves U7)*

**Correction — X2 was my error.** I reported that the `FORWARD` common move
resolves to `<<PF_ON>>` ("route to the Requirements Analyst") and therefore
contradicted `pipeline_flow`. The opposite is true:
`agents/shared/prompts.py:185` —

    def _planner_first_effective() -> bool:
        return PLANNER_FIRST if _hub_agent() == "orchestrator" else False

— returns False for every topology whose hub is not the Orchestrator, so
topology 3 ships the **`<<PF_OFF>>`** branch, *"route to the Design
Engineer"*. Page 14 of the annotated PDF confirms it verbatim. `FORWARD`,
`pipeline_flow` and `routing_planner` already agreed with each other and with
DE-first. **X2 is withdrawn.**

**U6 is retired with it.** The duplicated `Input directory: {user_inputs_dir}`
block at L50-58 lives INSIDE the `<<PF_ON>>` region, so it never reaches a
model. It is dead source, not a shipped duplicate.

**What actually remains** is created by the §B edits: once Role 1 says
*"images or complex content"*, two other statements of the same trigger still
say *"meaningful new content"*.

**Decision (owner, agreed as proposed).**

**Edit 1** — `agents/3agent/planner/prompt_3agents.md`, L45-64 (−8 lines).
Aligns the INPUT ANALYSIS trigger and drops the unreachable `<<PF_ON>>`
branch. Safe: this file is read only by topology 3; the 7-agent Planner has
its own.

```diff
   * **INPUT ANALYSIS** — route to the Requirements Analyst
     (``call_requirements_analyst``) to (re-)read the user's inputs.
-    Take this move whenever the user
-    added meaningful new content that downstream agents must see; Role 1
-    below gives the path line every such call MUST carry.
-  * **FORWARD** — hand the pipeline its next step<<PF_ON>>: route to the Requirements
-    Analyst (``call_requirements_analyst``).  Every RA forward
-    MUST carry this line verbatim (the RA reads files
-    only via the path you give it):
-
-        Input directory: {user_inputs_dir}
-
-    plus, optionally, a short focus/strategy note and any
-    disambiguating annotation from the Receptionist — do not paste file
-    content; the RA reads the files itself.<</PF_ON>><<PF_OFF>>: route to the Design
+    Take this move whenever the user added images or other content only
+    the RA can analyse; Role 1 below gives the rule and the path line
+    every such call MUST carry.
+  * **FORWARD** — hand the pipeline its next step: route to the Design
     Engineer (``call_design_engineer``) with a clear qualitative
     strategy directive (e.g. "increase <param X>", "honour the user's
     locked <param Y> = N"), any disambiguation affecting which
     parameters change, any user authorisation the DE needs to know
-    about, and the slug + intent for the attempt the DE will open.<</PF_OFF>>
+    about, and the slug + intent for the attempt the DE will open.
```

**Edit 2** — `agents/3agent/prompt_fragments/routing_planner_3agents.md` L5-9,
U7's third copy:

```diff
 - ``call_requirements_analyst(message)`` — (re-)read the user inputs.
-  Route here whenever the user added meaningful new content that
-  downstream agents must see; and CLARIFY back to the Requirements
-  Analyst if what it reported is missing required information or
-  contains an inconsistency that only it can resolve.
+  Route here whenever the user added images or other content only the
+  RA can analyse; and CLARIFY back to the Requirements Analyst if what
+  it reported is missing required information or contains an
+  inconsistency that only it can resolve.
```

Both edits track §B2's wording — change that and these follow.

---

### R7 — "the extraction" removed from the Planner  *(resolves X3)*

**Problem.** Round 1 removed `extracted_inputs.txt` from topology 3 — the RA
reports verbally instead. §B and §I clean four mentions; three live ones
remained, all in the Planner.

**Verified, not assumed:** `DESIGN INTENT` and `PRECISION DEMAND` are NOT
stale. `requirements_analyst/prompt_3agents.md` L136 and L143 still tell the
RA to author both, and it states them in its hand-off. Only the word
*extraction* — the file — needs replacing; the labels stay.

**Decision (owner, agreed as proposed).** Apply the three Planner edits, plus
the same hygiene on the unreachable `value_states_3agents.md`. Leave
`sketch_handling_3agents.md` L130-134 alone — also unreachable, but RA
territory and out of scope this round.

**Edit 1** — `agents/3agent/planner/prompt_3agents.md` (three hunks):

```diff
--- a/agents/3agent/planner/prompt_3agents.md
+++ b/agents/3agent/planner/prompt_3agents.md
@@ -89,8 +89,9 @@
     is not doing its work.
 
     A **PRECISION INPUT-MATCH job** is the canonical case.  When the
-    extraction signals the user wants one or more features to closely reproduce a
-    precise input — a ``PRECISION DEMAND`` line in DESIGN INTENT, a PRECISE
+    Requirements Analyst reports that the user wants one or more features to
+    closely reproduce a precise input — a ``PRECISION DEMAND`` under DESIGN
+    INTENT, a PRECISE
     SKETCH verdict on a drawing, or wording like "match as
     precisely as possible / try as many attempts as needed" — DECIDE it is a
     precision job and issue a standing directive for it.  What follows is an
@@ -165,8 +166,8 @@
     run (a question answered from the agents' histories or the stored
     files, a written proposal): put the user-facing answer in Part 2 via
     ``call_receptionist``.  A values-only request still needs the agent
-    that AUTHORS the values; answering from the extraction alone means
-    nobody derived them.
+    that AUTHORS the values; answering from the Requirements Analyst's
+    report alone means nobody derived them.
   * **ASK THE USER** — when you need permission or guidance only the
     user can give (Rules 5–6 below): put the question in Part 2 via
     ``call_receptionist``, stating what to ask and what you need back.
@@ -352,7 +353,8 @@
     which levers ACTUALLY moved before directing another revision.
   - **Error interpretation** — a tool failure or confusing log points at
     a specific attempt; read its files to see what was generated.
-  - **Ambiguous request** — the extraction leaves you genuinely unsure
+  - **Ambiguous request** — the Requirements Analyst's report leaves you
+    genuinely unsure
     (e.g. "do something different from before" but "before" isn't
     captured) and prior attempts would clarify.
 
```

**Edit 2** — `agents/3agent/prompt_fragments/value_states_3agents.md`. This
fragment is UNREACHABLE today (all three agents that splice `$value_states`
have a scoped override), so this is hygiene against the day one is removed,
not a live fix. It also deletes authorisation route (C), which describes an
inline `(unlocked by user)` annotation in a file format that no longer
exists:

```diff
--- a/agents/3agent/prompt_fragments/value_states_3agents.md
+++ b/agents/3agent/prompt_fragments/value_states_3agents.md
@@ -1,5 +1,5 @@
 Every value the user could have given is in exactly one of three states,
-read off the extraction's QUANTITATIVE INPUTS section:
+read off the user's QUANTITATIVE INPUTS:
 
 - **LOCKED** — a value the user stated plainly there, with no marker.  The
   user fixed it.  LOCKED is not an absolute wall: it may change when an
@@ -22,23 +22,19 @@
   as LOCKED for that cycle.
 
 **Freeing a LOCKED value.**  A LOCKED value may change only with an
-authorisation, discoverable from ANY of these (one is enough):
+authorisation, discoverable from EITHER of these:
   (A) the **incoming hand-off** names one — a user permission (blanket
       "vary as needed" / "automated conservative adjustments OK", scoped
       "except <param X>", or parameter-specific "the user approved changing
       <param Y>") or a strategy / recovery directive to change the value; a
       CLARIFY bounce may carry one too;
-  (B) the **extraction's DESIGN INTENT section** records one — a user
-      authorisation the RA wrote, standing every cycle until revoked; or
-  (C) the value's own QUANTITATIVE INPUTS line carries an
-      ``(unlocked by user)`` annotation, IF PRESENT — an older extraction may
-      still carry this inline mark; today a released value is simply omitted
-      from the section (which makes it FREE) rather than annotated.
-One source is enough — never demand a "ritual re-confirmation" of an
+  (B) the **DESIGN INTENT** records one — a user authorisation the RA
+      reported, standing every cycle until revoked.
+Either source is enough — never demand a "ritual re-confirmation" of an
 authorisation the hand-off already carries.  A line literally saying
 "user-locked" is only the DEFAULT lock and does NOT override a current
-authorisation — the hand-off, DESIGN INTENT, and any inline annotation are
-the current sources of truth.  How FAR an authorised (or soft) value may
+authorisation — the hand-off and DESIGN INTENT are the current sources of
+truth.  How FAR an authorised (or soft) value may
 move follows the wording: "as needed / only if necessary" = the smallest
 change that restores viability, staying close to the user's number; "freely
 / as much as possible" (or nothing said) = as far as the goal requires,
```

---

### R8 — sweep every `<<DCII_ONLY>>` region out of `agents/3agent/`  *(resolves X6)*

**Measured, not asserted.** I assembled all five topology-3 prompts with
`extra_utilities/topology_prompt_snapshot.py save` and grepped them for
`DCII|DC Input Inspector|call_dc_input_inspector`:

    3agent/database_handler.txt      0 hits
    3agent/design_engineer.txt       0 hits
    3agent/planner.txt               0 hits
    3agent/receptionist.txt          0 hits
    3agent/requirements_analyst.txt  0 hits

Control, the same grep on the 7-agent prompts, proving the check can fail:
`dc_input_creator` 7, `orchestrator` 5, `planner` 4, `database_handler` 3,
`tool_caller` 2.

So **none of this text is shown to any 3-agent agent.** The only live trace
is three stray blank lines in `design_engineer.txt` (L455-458) where the
11-line block was stripped. X6 is housekeeping, not a behaviour defect —
downgraded from 🟡.

**Why the sweep is provably a no-op.** There are **no `<<DCII_OFF>>` regions
anywhere in `agents/3agent/`**. With the DCII off, `apply_dcii_filter` does
exactly `_DCII_ONLY_RE.sub("", text)` plus an unwrap of OFF regions that
matches nothing — so hand-deleting the ONLY regions reproduces the filter's
own output byte for byte.

**Decision (owner).** Sweep **all 8 sites**, including the RA's and the
Database Handler's, not just the 5 in this round's scope.

| file | lines | shape |
|---|---|---|
| `design_engineer/prompt_3agents.md` | 161 | inline → `    hand-off.` |
| `design_engineer/prompt_3agents.md` | 287-297 | whole block, markers included |
| `planner/prompt_3agents.md` | 233 | inline → `  Sequence: Design Engineer → Requirements Analyst` |
| `planner/prompt_3agents.md` | 240 | inline → `  no specific value).  Then Design Engineer → Requirements Analyst."` |
| `prompt_fragments/available_agents_planner_3agents.md` | 29-33 | whole DCII bullet |
| `prompt_fragments/available_agents_3agents.md` | 30-34 | whole DCII bullet |
| `requirements_analyst/prompt_3agents.md` | 301-302, 304-305 | two inline |
| `dc_config/visual_inspection_guide_3agents.md` | 44-45 | inline |
| `tools_config/agent_tools_overview_brief_3agents.md` | 18-21 | whole DCII bullet |

Deleting the two `available_agents` bullets also removes two of X3's latent
"extraction" references. Collapse the blank-line run left behind at
`design_engineer/prompt_3agents.md` L285-299 to a single blank line.

**Acceptance test.** Snapshot before and after with
`topology_prompt_snapshot.py save` / `diff`: **every topology-3 prompt must
be byte-identical**, except `design_engineer` which loses two blank lines.
Any other difference means a region was mis-cut.

---

### R9 — the SCAFFOLD banners, swept  *(resolves L1)*  ✅ APPLIED

**Measured before acting.** Assembling the topology-3 prompts and matching
`<!-- SCAFFOLD.*?-->`:

    3agent/database_handler.txt       0 banners       0 chars  of 22112   (0.0%)
    3agent/design_engineer.txt       10 banners    4214 chars  of 34580  (12.2%)
    3agent/planner.txt                0 banners       0 chars  of 24254   (0.0%)
    3agent/receptionist.txt           0 banners       0 chars  of 15946   (0.0%)
    3agent/requirements_analyst.txt  12 banners    5340 chars  of 36291  (14.7%)

9 554 characters of *"NOT THE FINAL TEXT … it states some concepts twice, and
it can carry rules that contradict each other or name agents topology 3 never
builds"* were being shipped to the two merged agents, inside their own system
prompts. Nothing strips HTML comments — grepped, and confirmed by the
measurement.

**Decision (owner).** Sweep all 15 files. **Applied.**

**What ran.** `re.sub(r"\n*<!-- SCAFFOLD.*?-->\n*", "\n\n", src, DOTALL)`
per file, then a leading-blank strip for the banners that sit at a file head,
written back as CRLF. One guard mattered: bare **`SCAFFOLDING`** is legitimate
prose in the sketch fragments (pre-printed form content), so the
post-condition asserts on `<!-- SCAFFOLD`, not on `SCAFFOLD`.

    15 files, 30 comments, -13080 source chars, -261 lines
    git diff --stat: 15 files changed, 261 deletions(-)      <- no insertions

**Test — `topology_prompt_snapshot.py save` before and after, then `diff`:**

| topology | result |
|---|---|
| 7 | all 9 prompts **byte-identical** |
| 5 | all 7 prompts **byte-identical** |
| 3 | `database_handler`, `planner`, `receptionist` **byte-identical** |
| 3 | `design_engineer` 34 580 → 30 345 (**−4 235**) |
| 3 | `requirements_analyst` 36 291 → 30 924 (**−5 367**) |

**−9 602 characters** off the two shipped prompts, against 9 554 of comment
text — the extra 48 are the collapsed blank lines. And the two checks that
make it airtight:

* **0 added lines** across the entire snapshot diff;
* every removed line is comment text or blank. The only removed lines that
  do not contain the word SCAFFOLD are the 2nd and 3rd lines of the RA's
  multi-line JOIN marker (`except "## User inputs", moved down out of the
  User Input Inspector half … -->`), verified in `git diff` to sit inside the
  comment.

`grep -rl "<!-- SCAFFOLD" agents/` now returns nothing.

---

### R10 — the extraction-only answer keeps its route to the user  *(resolves N3 / C1)*

**Problem.** C1's RED removes `Deliver the answer through the Receptionist
once that work is done.` — the only sentence in that section closing the loop.
Two general rules do cover it (`## Output format` L34-41, and the
`REPLY DIRECTLY` move L164-169), but an extraction-only ask is exactly the
case where the Planner may reason *"this is not a cycle"* and reach for the
no-tool-call fall-back, which is the one path that bypasses the Receptionist.

**Decision (owner).** Option A — fold a clause into §C's rewrite rather than
keep the sentence, in the owner's own words.

**Edit** — the last sentence of §C's first replacement paragraph:

```diff
-  Then route to the
-  Design Engineer with a standing directive that says VALUES ONLY.
+  Then route to the Design Engineer with a standing directive that says
+  VALUES ONLY, and once the final set of parameters is obtained, deliver
+  the answer through the Receptionist as usual.
```

§C still shrinks overall: the red sentence goes, and the surviving clause
now also names the trigger (*the final set of parameters is obtained*) that
the deleted one left implicit.

---

### R11 — the Receptionist states the fallback report rule once  *(resolves X7 / U3)*

**Correction on the diagnosis.** I first called the
`"DC parameters written this cycle"` block *legacy* and *deprecated*. It is
neither. `agents/receptionist/receptionist.py:327` builds it in code, gated on
`if not self._handoff_names_attempt(system_result):` — it is the **live
fallback branch** for a hand-off that names no attempt folder. Both branches
map to running code, and `extra_utilities/prompt_defects_found.md:177` already
recorded this ("NOT dead").

**What is actually wrong.** The same live rule is stated twice — L139-141 in
Situation B and L200-202 under Reporting attempts — and the second
back-references the first with *"use it as before"*, so neither is
self-contained.

**Decision (owner).** Option B — one statement, in the section that owns
reporting.

```diff
--- a/agents/3agent/receptionist/prompt_3agents.md
+++ b/agents/3agent/receptionist/prompt_3agents.md
@@ -136,9 +136,6 @@
 If the summary includes a question from the system, ask the user
 plainly and make it easy to answer.
 
-If the summary reports a finished result with a "DC parameters written
-this cycle" block, list those $parameter_count values verbatim plus the
-render paths from the "Confirmed render files produced this cycle" block.
 If it reports an error or exhausted attempts, tell the user what happened
 and what was tried — do not hide it behind a terse line.
 
@@ -197,9 +194,11 @@
 precision phase the hand-off reports: a plateau or a residual gap
 must be SAID, never rounded up to "matches your sketch".
 
-Anti-stale: if instead a legacy "DC parameters written this cycle" /
-"Confirmed render files produced this cycle" block is present, use it as
-before.  If NEITHER block is present, state no parameter values or paths
+Anti-stale: if instead a "DC parameters written this cycle" /
+"Confirmed render files produced this cycle" block is present — the
+fallback the system attaches when the hand-off names no attempt — list
+those $parameter_count values verbatim plus those render paths.  If
+NEITHER block is present, state no parameter values or paths
 as THIS CYCLE'S RESULT — disk files may be stale; if generation/rendering
 failed, say so and list no artifacts.  (Values the hand-off itself spells
 out in prose are not "stale": relay them as the hand-off's, not as a read
```

Net −1 line, plus two gains: *"use it as before"* stops dangling, and the word
**"legacy"** goes. Calling a live code path legacy invites a model to
under-weight it.

---

### R12 — the Database Handler's copy of Available Agents  *(resolves U1)*

**Problem.** `$available_agents` resolves to two files:
`available_agents_planner_3agents.md` for the Planner (§A) and
`available_agents_3agents.md` for the **Database Handler**. Both carry the
Stage-4 two-RA / two-DE split; §A fixes only the Planner's. Left alone, the
agent whose entire job is interviewing the others about what they did would
be told there are four agents where there are two.

**Decision (owner, agreed as proposed).** Apply §A's A1, A2, A4 and A6 to the
DH's third-person variant. A5 does not apply — this copy never carried
*"the record of the N parameter values the DE authored"*.

```diff
--- a/agents/3agent/prompt_fragments/available_agents_3agents.md
+++ b/agents/3agent/prompt_fragments/available_agents_3agents.md
@@ -6,26 +6,22 @@
   before the pipeline ever starts and composes every outgoing message
   to the user.
-- **Requirements Analyst (RA)**: loads the rendered PNGs using the
-  paths supplied by the Design Engineer and performs a qualitative visual
-  analysis.  It calls the Planner to approve the design or to flag
-  defects and problems.  Cannot measure precise dimensions; comments
-  on overall shape, proportions, and feature count.
 - **Requirements Analyst (RA)**: reads user_query.txt and any other
   input files in the inputs directory (text, JSON, sketches/images),
-  extracts design values, intent, and constraints.
-- **Design Engineer (DE)**: writes
-  the complete $parameter_count-parameter set to parameters.json.  This is the only
-  agent that authors concrete numeric parameter values.  Translates
-  qualitative guidance (a directive of the form "increase <param X>")
-  into numbers.
-- **Design Engineer (DE)**: points ``generate_and_render_propeller``
-  at an attempt's ``parameters.json`` and calls it once — the tool reads
-  that record itself and produces the mesh file
-  AND, as its built-in final step, the renders and (if enabled) the
-  quality-check numbers.<<BSV_ON>>  It can instead be asked for
-  ``render_blade_sections`` — the three blade cross-sections alone,
-  with no 3D mesh.<</BSV_ON>>  Also has a ``calculate`` tool for
-  arithmetic.  Reports the produced file paths for the Requirements
-  Analyst.
+  extracts design values, intent, and constraints.  It also loads the
+  rendered PNGs using the paths supplied by the Design Engineer and
+  performs a qualitative visual analysis, calling the Planner to approve
+  the design or to flag defects and problems.  Cannot measure precise
+  dimensions; comments on overall shape, proportions, and feature count.
+- **Design Engineer (DE)**: writes the complete $parameter_count-parameter
+  set to parameters.json.  This is the only agent that authors concrete
+  numeric parameter values.  Translates qualitative guidance (a directive
+  of the form "increase <param X>") into numbers.  It then uses that
+  attempt's ``parameters.json``<<BSV_ON>> for calling
+  ``render_blade_sections`` — the three blade cross-sections alone, with
+  no 3D mesh<</BSV_ON>>.  Or it points ``generate_and_render_propeller``
+  at that ``parameters.json`` and calls it once — the tool reads that
+  record itself and produces the mesh file and the image renders of the
+  mesh.  Also has a ``calculate`` tool for arithmetic.
+  Reports the produced file paths for the Requirements Analyst.
 <<DCII_ONLY>>- **DC Input Inspector (DCII)**: reads parameters.json and
   the extraction from disk and validates that the parameter
```

Net −4 lines. Three things deliberately kept different from §A:

* **third person throughout** — *"calling the Planner"*, not *"calling you"*:
  the reader is the Database Handler, which is not in the chain;
* **`(text, JSON, sketches/images)`** — the DH's copy names JSON and the
  Planner's does not; each is left as it stands rather than silently
  harmonised;
* the Planner and Receptionist bullets are untouched — the DH's are already
  shorter than the Planner's, by design.

The `<<DCII_ONLY>>` bullet visible at the foot of the diff is removed
separately by **R8**.

---

### R13 — the Receptionist's image rules, and its `read_agent_history` menu  *(closes U2, resolves U4)*

**U2 — withdrawn, kept as is (owner's call).** I called the three "you never
analyse images" passages the Receptionist's largest duplication. Read in
full, they are three different rules that share a premise:

| lines | scope | action |
|---|---|---|
| 9-10 | the user's INPUT images | run the pairing check and the note-content check |
| 91-96 | the system's OUTPUT renders | never fabricate statements about them |
| 218-220 | how to RESPOND to an extraction ask | do not deflect with *"I cannot analyse images"* |

No contradiction and no redundant rule; the third exists because the
Receptionist *was* deflecting extraction asks, so deleting it re-opens that.
**No change.**

**U4 — also not the duplication I flagged, but it uncovered a real defect.**
L63-66 is a one-line pointer inside the two-response-paths list and L105-117
is the full procedure; that pairing is fine. The procedure itself, however,
did not survive the Stage-8 renames:

    5-agent parent (prompt_5agents.md:110-113)
      (DCOI for the visual verdict, Planner for reasoning, Tool Caller for
       what ran + metrics + paths, DCIC for chosen parameter values, UII for
       extracted intent; call it more than once if needed)

DCOI→RA, UII→RA, Tool Caller→DE, DCIC→DE turned five distinct agents into
**three, listed five times**. The Receptionist is handed a menu naming the
Design Engineer twice and the Requirements Analyst twice, as if they were
four agents it could choose between — and this is the one list that tells it
*who to ask about what*, so the confusion costs a wasted tool call exactly
where it lands.

**Decision (owner, agreed as proposed).**

```diff
--- a/agents/3agent/receptionist/prompt_3agents.md
+++ b/agents/3agent/receptionist/prompt_3agents.md
@@ -106,10 +106,11 @@
 diameter did the last design end up with?", "did the render succeed?") or
 what the system observed / concluded ("what would you change?", "any
 suggestions?") — do NOT answer from imagination.  First
-``read_agent_history`` on whichever agent saw it (RA for the visual
-verdict, Planner for reasoning, Design Engineer for what ran + metrics +
-paths, Design Engineer for chosen parameter values, RA for extracted intent; call
-it more than once if needed).  If the histories answer it, quote/
+``read_agent_history`` on whichever agent saw it (the Requirements Analyst
+for the visual verdict and for what it extracted from the user's inputs;
+the Design Engineer for the parameter values it chose and for what its
+tools ran, produced and reported; the Planner for reasoning; call it more
+than once if needed).  If the histories answer it, quote/
 paraphrase faithfully and reply directly, attributing nothing to
 yourself.  If they lack it — or the user may want more than they contain
 — forward to the Planner (a non-design forward) with what you found
```

Net +1 line. Three agents, three entries, each naming both things that agent
now covers — which also makes this the first place in the Receptionist's
prompt that says out loud what the two merges merged. L63-66 is left alone.

---

### R14 — `new_attempt_parameters`, split by what each place is for  *(closes U5, resolves U8)*

**U5 — not a defect (owner's call).** The two "when unsure, forward it"
sentences have different triggers — *is this a lookup or a new request?*
(L116-117) and *which attempt does "that one" mean?* (L185). They share a
shape and nothing else. **No change.**

**U8 — three descriptions, but the fix is a split, not a delete.**
`new_attempt_parameters` would be described in the tool inventory (§E), in
`## Attempt folders` (R1, as ownership), and in `## Read + write tools —
policy`. A **fourth** copy is the tool's own schema
(`agents/design_engineer/design_engineer.py:110-135`), which already carries
every mechanic including *"a rejected call creates nothing"* and *"Returns the
new attempt's NUMBER and absolute folder path"*.

The two prompt locations are for different moments, and their own headings say
so: `## Your Role … UTILITY tools` is the capability inventory read once at the
top, and `## Read + write tools — policy (mechanics are in each tool's
schema)` sits between `## Attempt folders` and `## Hand-off`, at the moment of
use.

**Decision (owner) — Option A, split by purpose.**

```diff
@@ tool_inventory_design_engineer_3agents.md — §E's new bullet 1 (mechanics)
+1. **new_attempt_parameters(parameters, slug, description)** — open a NEW
+   attempt folder and write the complete parameter set into it, in one
+   call.  Returns the attempt's NUMBER and absolute folder path.

@@ design_engineer/prompt_3agents.md — the policy entry (cadence only)
-**``new_attempt_parameters(parameters, slug, description)``** — exactly ONE
-successful call per cycle.  It opens the attempt AND writes
-``parameters.json`` into it, so validate your draft first: a rejected call
-creates nothing.
+**``new_attempt_parameters(...)``** — exactly ONE successful call per
+generation, and a correction after writing is a NEW generation.  Validate
+your draft first: a rejected call creates nothing.
```

**The factual error this removes.** "exactly ONE successful call per **cycle**"
contradicts `## Attempt folders` twelve lines above it, which mandates
*"If you discover a real error AFTER writing, that correction is a NEW
generation: call ``new_attempt_parameters`` again for the corrected set."*
A cycle can legitimately hold two calls; a generation cannot. (Distinct from
the render-type rule — a cycle still produces the full mesh **or** the blade
sections, never both.)

Net +3 lines in the inventory, −1 in the policy.

---

### R15 — the Planner's "Output format" says one thing twice  *(resolves U9)*

**Four of the five sites are not duplicates.** `available_agents_planner`
L3-5 is the agent roster; L134-137 (APPROVE) and L170-172 (ASK THE USER) each
name what THAT move's Part 2 must carry; HARD RULE 6 (L317-320) is the
load-bearing statement the other three lean on. All keep their place.

**The fifth is a repeat inside one paragraph:**

    33| ## Output format
    34| The normal end of a cycle is ``call_receptionist``, which composes the
    35| user-facing wording.  For you a response with NO tool call does not
    36| halt silently as it would for a chain agent — it ends the dispatch and
    37| its text goes to the user verbatim as the final answer.  That is how a
    38| turn ends when you fail to route, and it is the only channel left if
    39| the Receptionist itself cannot deliver.  Treat it as an emergency
    40| fall-back, never as a way to reply: the Receptionist composes what the
    41| user reads.

L34-35 and L40-41 make the same claim eight lines apart.

**Decision (owner, agreed as proposed).**

```diff
 the Receptionist itself cannot deliver.  Treat it as an emergency
-fall-back, never as a way to reply: the Receptionist composes what the
-user reads.
+fall-back, never as a way to reply.
```

−1 line. The paragraph already opens with the claim, and the sentence's own
point — *emergency fall-back, never a way to reply* — survives intact.

---

### R16 — `read_attempts` is described twice, correctly  *(closes U10)*

R5 already deletes the third description (`## Using read_attempts`). The two
that remain are the split approved in R14:

* `tool_inventory_design_engineer_3agents.md` bullet 4 — **mechanics**: what
  the tool returns with and without arguments, and that every path comes back
  absolute;
* `## Read + write tools — policy` L243-244 — **when to call**: *"inspect
  prior attempts of this session when a directive resembles one you handled
  before."*

No sentence is repeated. **Not a defect; no change** (owner's call).

**What R5's deleted section contained**, checked so nothing needed is lost:

    ## Using read_attempts
    ``read_attempts(n)`` is how you see an attempt's numbers — you need it for
    the range check above.  Do not browse attempt after attempt, and do not use
    it to invent your own retry strategies; that is the Planner's call.

Two claims there survive nowhere else, and neither should:

* *"you need it for the range check above"* is **stale** —
  `## Validate before you write (HARD)` checks the draft the DE is holding,
  not a stored attempt, so `read_attempts` is not needed for it;
* *"do not browse attempt after attempt … that is the Planner's call"* was
  written for the Tool Caller, an executor with no business choosing strategy.
  The merged DE authors its own values, and `## Acting on a Planner
  qualitative directive (HARD)` already bounds that — *"you have exactly TWO
  valid responses"*.

---

### R17 — "pass ONLY that file's path", stated four times  *(resolves U11)*

Four, not three — the fourth is the tool's own schema
(`tools/render_blade_sections/render_blade_sections.py`: *"Pass the absolute
path to a parameters JSON file (an attempt's ``parameters.json``)"*, plus the
`parameters_path` Args line).

The two `tool_inventory` bullets are per-tool and each carries the **ONLY**
that turns the statement into a warning — they stay. The Loading-parameters
lead-in restates it a third time in front of the sentence that is its actual
reason for existing.

**Decision (owner, agreed as proposed).**

```diff
 ## Loading parameters (IMPORTANT)
-Both geometry tools read ``parameters.json`` from disk themselves: pass the path of the attempt's own
-``parameters.json``, never values.  Generate from the FILE ON DISK, not from what
-you believe you wrote.
+Both geometry tools read ``parameters.json`` from disk themselves.
+Generate from the FILE ON DISK, not from what you believe you wrote.
```

−1 line. The unifying statement survives, and so does the load-bearing rule —
*generate from the file on disk, not from what you believe you wrote* — the
only one of the four that catches a write that silently failed.

---

### R18 — retired agents inside the TOOL DESCRIPTIONS  *(resolves X8, found while checking U11)*  ✅ APPLIED

**How it was found.** Verifying U11 meant reading the geometry tools' schemas.
Those schemas reach the model but are not part of any assembled prompt, so I
grepped the *"Tools bound to this agent"* pages of the annotated PDF for
retired agent names. The prompts come out of this round clean; the tool
descriptions did not.

| tool | agent(s) | live today? |
|---|---|---|
| `render_blade_sections` | Design Engineer (PDF p.36) | **yes** |
| `propose_attempt` | Receptionist (p.11) | **yes** |
| `retrieve_user_inputs` | Receptionist, Planner, DE, RA (p.12, 21, 37, 51) | only with RAG on |

This is the class round 1's §E fixed in `agents/topology3/tool_text.py`,
surviving in the one place a prompt sweep structurally cannot look.

**Decision (owner). Applied.** All three replacements make the shared text
topology-NEUTRAL rather than forking it, so no overlay entry is needed and
topologies 7 and 5 are at least as accurate as before.

```diff
--- a/tools/render_blade_sections/render_blade_sections.py
-    shown to the user in the chat; any agent with an image-reading tool (e.g.
-    the DC Output Inspector via ``view_images``) can view it by passing
-    the returned path.
+    shown to the user in the chat; any agent with an image-reading tool
+    (``view_images``) can view it by passing the returned path.

--- a/agents/receptionist/propose_attempt_tool.py
-    (or have been told by Planner / DCOI) that a given attempt
+    (or have been told so in your hand-off) that a given attempt

--- a/tools/retrieve_user_inputs/retrieve_user_inputs.py
-        The response prints, per session: the User Input Inspector's
-        structured extraction of the inputs (or, for a session archived
+        The response prints, per session: the structured extraction of the
+        inputs recorded for that session (or, for a session archived
```

**`propose_attempt` was wrong in every topology, not only this one.** Checked
against the wiring — `orchestrator.py:440`, `planner5.py:410` and Planner3's
equivalent — the Receptionist is reachable **only from the hub**. The DC
Output Inspector has no edge to it anywhere, and under topology 7 the caller
is the Orchestrator, not the Planner.

`retrieve_user_inputs` named both a retired agent AND the extraction artefact
decision A2 removed. It describes ARCHIVED sessions, which genuinely hold a
UII extraction, so the neutral wording stays true of the archive without
implying topology 3 has either.

**Verification.**

    git diff --stat: 3 files changed, 5 insertions(+), 6 deletions(-)
    topology_prompt_snapshot diff: ALL 21 prompts byte-identical
      (7-agent 9/9, 5-agent 7/7, 3-agent 5/5)
    smoke_test_prompt_tool_audit.py: PASS

⚠ **The snapshot check cannot validate this class of edit** — tool
descriptions are not part of the assembled prompt, so all 21 stay identical
whether the edit is right or wrong. Its value here is the opposite: it proves
nothing *else* moved. The real checks are the tool audit and re-reading the
tool pages of the next PDF build.

**Swept and cleared, not model-visible:** `tools/generate_mesh/generate_mesh.py`
L201-206 (a source comment) and L210-219 (`_param_mismatches`, a private
helper, not a `@tool`) both mention the Orchestrator; `generate_and_render_propeller`'s
own docstring is clean. `agents/shared/dc_params_tool.py:53` names the DC
Input Creator but is already overridden for topology 3 by the §E overlay, and
`smoke_test_topology3_tool_text.py` asserts it.

---

### R19 — the `middlePos` formula, stated four times  *(closed, kept as is)*

The four statements that reach the Design Engineer:

| # | file | what it says |
|---|---|---|
| 1 | `structure_3agents.md` L11-12 | the geometry: *"positioned at radius 4 + middlePos·(impellerRadius − 4) mm"* |
| 2 | `parameters_design_engineer_3agents.md` L31 | the parameter row, same formula, with the range |
| 3 | `modelling_notes_design_engineer_3agents.md` L5-8 | same formula **plus** *"— NOT ``middlePos × impellerRadius``"* and the 4 mm root / 8 mm hub distinction |
| 4 | `modelling_notes_design_engineer_3agents.md` L27-28 | the **INVERSE**: `middlePos = (r − 4) / (impellerRadius − 4)` |

**Decision (owner): leave all four.**

The reasoning, recorded so a later round does not re-open it: #4 is a
different formula (solving for `middlePos` from a radius, which is what a
user-stated distance needs); #3 is the only one that names the WRONG answer;
#1 and #2 each sit where a reader looks for that fact — what the geometry is,
and what the parameter means.

And the history matters. This formula was wrong across the prompts and the
test decks until it was corrected — older material used from-centre
`distance / R`. The repetition reads as padding but is deliberate: the same
error kept reappearing, so the rule was stamped into the three places a model
might look. Removing a copy re-opens a defect that has already shipped once.

---

### R20 — the merged Design Engineer bullet: authoring first  *(resolves A2)*

**The question.** *"Add the DE's first paragraph to the second"* did not say
which half leads.

**Decision (owner): Option A — authoring first**, plus a rewording of the
render clause.

Two reasons beyond taste, recorded so the order is not re-litigated:

* **A1 set the precedent.** For the Requirements Analyst the owner was
  explicit — the *extraction* text goes BEFORE the *"loads the rendered
  PNGs"* text, i.e. the earlier pipeline step first. Applied to the DE,
  authoring precedes executing.
* **The alternative introduces a forward reference.** Opening with *"uses an
  attempt's ``parameters.json``"* before anything says who wrote one, then
  explaining at the end that the DE created it, needs the phrase *"in the
  first place"* to hold together — the seam showing.

**Owner's rewording**, applied to §A and to R12's Database Handler copy so
the two files stay aligned:

```diff
-  record itself and produces the mesh file AND, as its built-in final
-  step, the renders.
+  record itself and produces the mesh file and the image renders of the
+  mesh.
```

*"calls it once"* still carries the one-call-does-both point, so nothing is
lost by dropping *"as its built-in final step"* here. Note that the phrase
survives — deliberately — in `tool_inventory_design_engineer_3agents.md`
bullet 2, where it is the tool's own mechanics and tells the DE it needs no
second call.

---

### R21 — Role 1's "expand accordingly" half  *(resolves B2)*

**The question.** The owner's note supplied the *rephrase*; the *expand* half
was mine, and it is the sentence that decides how often the RA runs.

**Decision (owner): keep both sentences, with one correction.**

```diff
-first.  Plain numbers and plain prose you can already act on do not
-need the RA.
+first.  Plain numbers and plain prose the DE can already act on do
+not need the RA.
```

**The correction fixes a real error, not just a preference.** This sentence
sits in the PLANNER's prompt, so "you can already act on" addressed the
Planner — but the Planner is precisely the agent that must NOT act on values.
HARD RULE 3 (L287-298): *"You neither analyse design values nor pre-compute
the work you direct … You may RELAY a user-stated value verbatim … You may
not DERIVE one."* Naming the DE makes the test the right one: can the DE act
on this as written, or does something have to be read out of an image first?

**Final wording of §B2:**

    Whenever the user has supplied NEW content this turn AND it contains
    material the Requirements Analyst should analyse further — or that ONLY
    the RA can analyse (images, sketches, drawings) — the RA must be called
    first.  Plain numbers and plain prose the DE can already act on do
    not need the RA.

Sentence 2 is what gives the rule a floor. Without a stated negative case
*"content the RA should analyse further"* has none — every message contains
some content, and the safe reading is always to call the RA, which is the
behaviour this edit exists to change.

Note R6's two edits track this wording: the INPUT ANALYSIS move and
`routing_planner_3agents.md` both say *"images or other content only the RA
can analyse"*, which stays consistent with sentence 1.

---

## §M — Logic inconsistencies

Ordered by how likely each is to stop or corrupt a real run.

✅ **All seven are resolved** — X1 → R1, X2 → withdrawn (R6),
X3 → R7, X4 → §A1-A2, X5 → R4, X6 → R8, X7 → R11.

## §N — Did you remove anything critical?

Five. Two I would not apply as marked.

✅ **All five are resolved** — N1 → R2, N2 → R3, N3 → R10, N4 → R4,
N5 → R5.

## §O — Duplications you did not mark

### Receptionist

| # | what | where |
|---|---|---|
| ~~**U2**~~ *(kept as is → R13)* | *"you never analyse images"* stated three separate times | L9-10 (`You do NOT analyse images`), L90-96 (`you NEVER invent observations … about them`), L218-220 (`You never analyse images yourself for ANY request`) |
| ~~**U3**~~ *(solved → R11)* | the legacy `"DC parameters written this cycle"` reporting procedure, given twice with different framing | L139-143 and L200-206 → also **X7** |
| ~~**U4**~~ *(solved → R13, re-diagnosed)* | `read_agent_history` guidance, given twice | L63-66 (inside response-path 2) and L105-117 (inside the anti-hallucination rule) |
| ~~**U5**~~ *(not a defect → R14)* | *"when unsure, forward it"* | L116-117 (`When unsure whether a message is such a question or a new design ask, forward it.`) and L185 (`If you cannot identify which attempt they mean, do NOT guess: forward it.`) |

~~`U2` is the largest…~~ **Withdrawn — see R13.** The three passages are
three different rules sharing a premise, not one rule stated three times.

### Planner

| # | what | where |
|---|---|---|
| ~~**U6**~~ *(retired → R6)* | the `Input directory: {user_inputs_dir}` mandate, **verbatim twice** including the "do not paste file content; the RA reads the files itself" trailer | L50-58 (FORWARD move) and L186-194 (Role 1) |
| ~~**U7**~~ *(solved → R6)* | *"route to the RA whenever the user added meaningful new content that downstream agents must see"*, three times | L45-49 (INPUT ANALYSIS move), L181-184 (Role 1), and `routing_planner_3agents.md` L5-9 |
| ~~**U1**~~ *(solved → R12)* | the two-RA / two-DE Available-Agents split, in **two files** | `available_agents_planner_3agents.md` (Planner) and `available_agents_3agents.md` (Database Handler) |
| ~~**U9**~~ *(solved → R15)* | *"the Receptionist composes the wording, you supply the substance"*, five times | L34-41 (Output format), L134-137 (APPROVE), L170-172 (ASK THE USER), L317-320 (HARD RULE 6), `available_agents_planner_3agents.md` L3-5 |

`U6` turned out NOT to be a live duplication — see R6. `U7` is solved
there too.

### Design Engineer

| # | what | where |
|---|---|---|
| ~~**U8**~~ *(solved → R14)* | `new_attempt_parameters` described twice, three times after §E | L228-232 (Attempt folders), L261-264 (Read+write policy), and §E's new bullet 1 |
| ~~**U10**~~ *(not a defect → R16)* | `read_attempts` described three times | `tool_inventory_design_engineer_3agents.md` L13-18, prompt L258-259, prompt L362-365 (§J7 deletes this one — after it, still two) |
| ~~**U11**~~ *(solved → R17)* | *"pass ONLY that file's path / never values"* three times | `tool_inventory` L3 and L7, prompt L327-328 |
| ~~**U12**~~ *(kept as is → R19)* | the `middlePos` radius conversion, **four times** | `parameters_design_engineer_3agents.md` L31 and L65, `modelling_notes_design_engineer_3agents.md` L8 (forward) and L28 (inverse), plus `structure_3agents.md` L12 |
| **U13** | the attempt-folder definition stated twice inside one section | L218-220 and L234-235 → the pair that also produces **X1** |

~~`U12` survives §F only partly…~~ **Kept as is — see R19.**

---
---

# Step-2 tracker

Each item below is open. As you rule on one, the decision is recorded here
and the item is struck from the list above.

| id | topic | status | your decision |
|---|---|---|---|
| ~~A2~~ | which DE half leads in the merged bullet | **solved → R20** | Option A, authoring first + reworded render clause |
| ~~B2~~ | my "expand accordingly" wording | **solved → R21** | kept, with "you" → "the DE" |
| ~~N1 / F1~~ | which parameter-list copy to delete | **solved → R2** | delete the SECOND copy |
| ~~N2 / H1-H3~~ | the value-state recognisers | **solved → R3** | keep the recognisers, drop the section framing |
| ~~N3 / C1~~ | how the extraction-only answer reaches the user | **solved → R10** | Option A, owner's wording |
| ~~N4 / X5 / J2~~ | the `Parameters file:` label and its dependants | **solved → R4** | agreed as proposed |
| ~~N5~~ | re-homing `{render_check_library_block}` | **solved → R5** | move L326-341 as one block |
| ~~X4~~ | two RA / two DE identities in Available Agents | **solved → §A1-A2** | the merge closes it |
| ~~X1~~ | the DE's attempt-folder deadlock | **solved → R1** | agreed as proposed |
| ~~X2~~ | RA-first vs DE-first in the FORWARD move | **withdrawn → R6** | my error; topology 3 already ships DE-first |
| ~~X3~~ | the surviving "extraction" references | **solved → R7** | 3 live Planner edits + `value_states_3agents.md` hygiene |
| ~~X6~~ | dead `<<DCII_ONLY>>` text | **solved → R8** | sweep all 8 sites; verified it ships nowhere in topology 3 |
| ~~X7 / U3~~ | the Receptionist's two report formats | **solved → R11** | Option B; the block is live code, not legacy |
| ~~U1~~ | the DH's copy of Available Agents | **solved → R12** | apply §A to the third-person variant |
| ~~U2~~ | three "you never analyse images" | **kept as is → R13** | three different rules, one premise — not a defect |
| ~~U4~~ | two `read_agent_history` guidances | **solved → R13** | re-diagnosed: the menu names 3 agents 5 times |
| ~~U5~~ | two "when unsure, forward it" | **not a defect → R14** | different triggers |
| ~~U6~~ | the verbatim `Input directory:` block | **retired → R6** | dead `<<PF_ON>>` source, never shipped |
| ~~U7~~ | three "route to the RA when…" | **solved → R6** | align both with §B2 |
| ~~U8~~ | three `new_attempt_parameters` descriptions | **solved → R14** | Option A: inventory = mechanics, policy = cadence |
| ~~U9~~ | five "the Receptionist composes the wording" | **solved → R15** | one real repeat, inside `## Output format` |
| ~~U10~~ | two `read_attempts` descriptions | **not a defect → R16** | mechanics vs policy, the R14 split |
| ~~U11~~ | four "pass ONLY that file's path" | **solved → R17** | trim the Loading-parameters lead-in |
| ~~X8~~ | retired agents in the tool descriptions | **solved → R18, APPLIED** | found while checking U11; 3 shared modules made topology-neutral |
| ~~U12~~ | four `middlePos` formulas | **kept as is → R19** | #4 is the inverse, #3 names the wrong answer; the repetition is deliberate |
| ~~U13~~ | two attempt-folder definitions | **solved → R1** | folded into the attempt-folder rewrite |
| ~~L1~~ | remove all 15 SCAFFOLD banners | **solved → R9, APPLIED** | −9 602 chars shipped; 7 and 5 byte-identical |

---
---

# §Z — the application

Applied in three passes on 2026-09-09, in worktree
`rebuild-3-agent-topology-6ca792`, branch
`claude/rebuild-3-agent-topology-6ca792`.

| pass | what | files | result |
|---|---|---:|---|
| 1 | **R9** — the SCAFFOLD sweep | 15 | 30 comments, 261 deletions, 0 insertions |
| 2 | **R18** — retired agents in the tool descriptions | 3 | 5 insertions, 6 deletions |
| 3 | **R1-R8, R10-R17, R20, R21 + §A-§K** | 16 | 18 substitutions on the DE prompt, 26 across the rest |

Every substitution asserted its anchor text and its uniqueness before running,
so a stale anchor failed loudly rather than silently matching the wrong place.

## What the prompts became

    topology 7    all 9 prompts BYTE-IDENTICAL
    topology 5    all 7 prompts BYTE-IDENTICAL
    topology 3    receptionist          15 946 -> 15 906   (-40)
                  planner               24 254 -> 24 550   (+296)
                  design_engineer       34 580 -> 25 870   (-8 710, -25.2%)
                  requirements_analyst  36 291 -> 30 924   (-5 367, -14.8%)
                  database_handler      22 112 -> 22 029   (-83)

The Planner GREW: §B2's floor sentence and §C's rewritten extraction-only
section add more than B1/B6/R15/R6 remove. That is the intended trade — the
round was never about size.

## Verification

    topology_prompt_snapshot.py diff      7 and 5 byte-identical, 3 as above
    smoke_test_prompt_tool_audit.py       PASS
    smoke_test_topology3_tool_text.py     ALL PASS
    smoke_test_slot_splices.py            PASS
    smoke_test_hub_attributes.py          PASS (problems: none)
    smoke_test_topology_fragments.py      PASS
    dry_run_topology.py                   ALL PASS - 3 topologies drove a
                                          complete turn end to end
    smoke_test_prompt_format.py           pre-existing FAIL: no module 'trimesh'
                                          (environment, not this round)

Residue sweep across `agents/3agent/`: **0** files still contain
`<!-- SCAFFOLD`, `DCII`, `PF_ON`, `PF_OFF`, `Parameters file:` or
`HARD LIMITS`. Three files still say "the extraction", all deliberately out of
scope — the Database Handler's prompt, the unreachable
`sketch_handling_3agents.md`, and an RA-scoped blade-sections fragment.

## The PDF

`dump.py` and `build_html.py` gained topology-3 support:

* `AGENTS_BY_TOPOLOGY[3]`;
* `_t3_tools()` — the merged agents' bound tools are taken from the **real
  hub**, via the `bind_tools` spy that `smoke_test_prompt_tool_audit.bound_3`
  uses, never transcribed;
* `runtime_slots()` delegates to `topology_prompt_snapshot._runtime_slots`,
  the module the rebuild already verifies every prompt against, rather than
  transcribing the merged agents' `{slot}` values a second time;
* `DISPLAY` / `ROLE` rows and `ROLE4_REL` for topology 3.

**Cross-check:** `dump3.json`'s five prompts are **byte-identical** to
`topology_prompt_snapshot`'s. Two independent assemblers agree.

**Render:** 59 pages, 1.74 MB, body text measured at **8.7 pt** with the pypdf
`cm[3]` visitor — no silent Chrome shrink-to-fit.

## One new finding, NOT applied

`tools/generate_mesh/generate_mesh.py:777-781` — the `parameters_path`
argument description of `generate_and_render_propeller` reads:

    "Absolute path of the attempt's ``parameters.json`` — the same path "
    "the hand-off carries under ``Parameters file:``.  ..."

R4 removed that label from the DE's hand-off, so this cross-reference now
points at nothing. Same class as R18, found only because it shows on p.32 of
the rebuilt PDF. Proposed one-line fix, **awaiting a decision**:

```diff
-        "Absolute path of the attempt's ``parameters.json`` — the same path "
-        "the hand-off carries under ``Parameters file:``.  The mesh and the "
+        "Absolute path of the attempt's ``parameters.json`` — the same path "
+        "the hand-off carries under ``Current attempt <N>:``.  The mesh and the "
```
