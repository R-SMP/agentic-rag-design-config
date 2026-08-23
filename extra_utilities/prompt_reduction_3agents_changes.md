# Prompt reduction, round 2 — DC Input Creator / DC Input Inspector / Tool Caller

**Source:** `7agent_reduced_system_prompts_PDFnotes2_3Agents.pdf`
(33 pages — pages 53–85 of the original 113-page build, extracted).
**Applies to:** `stage-a-web-deploy` at `afc33fa` or later.
**Companion:** `prompt_reduction_4agents_changes.md` (round 1, applied in `afc33fa`).

254 highlights and 60 typed comments. Same markup convention as round 1:

| colour | count | meaning |
|---|---|---|
| red | 221 | delete the highlighted text |
| light yellow | 30 | modify / substitute — the adjacent comment says how |
| dark yellow | 3 | same as light yellow |
| typed comments | 60 | instructions, questions, or the rationale for a nearby highlight |

There is no green this round.

---

## 0.1 Line numbers are CURRENT — no path translation needed

Round 1's spec had to be read through a translation table, because the PDF
predated the promotion. **This one does not.** The PDF was still built from the
old tree, but every anchor below was resolved against the working tree at
`afc33fa`, so the paths and line numbers are the ones you will actually edit.

That is only safe because the drift is small, and it was measured:

| file | `4786832` (PDF) → `afc33fa` (today) |
|---|---|
| `agents/dc_input_inspector/prompt.md` | **identical** |
| `agents/dc_input_creator/prompt.md` | 2 lines changed — round 1's `list_attempts`/`read_attempt` → `read_attempts` rename, line-neutral |
| `agents/tool_caller/prompt.md` | 4 lines changed — the same rename, line-neutral |
| `agents/shared/prompt_fragments/generic_constraints.md` | **identical** |
| `DC_prompt_fragments/dc_config/hard_constraints_dc.md` | **identical** |
| `DC_prompt_fragments/tools_config/hard_constraints_tools.md` | −1 line ("Batch into ONE call…" already cut in round 1) |

Two consequences worth knowing before you start:

* **Some spans are already gone.** "Batch into ONE call; a second only when a
  later expression needs an earlier result." is highlighted red on pp. 7, 20 and
  29, but round 1 already removed it globally. It shows up under *No automatic
  source match*. Do not go looking for it.
* **The `read_attempts` rename is already done** for these three agents' prompts
  and bindings. The p.10 comment ("as previously said, this is renamed and
  customized (already done)") acknowledges this. What remains is everything
  *else* the tool comments ask for.

---

## 0.2 How to apply these tables — read this

Round 1's cut tables merged adjacent same-colour highlights into one row and
elided the middle of long spans with `…`. That elision hid two complete red
spans, which were then only half-applied — the leading half deleted, the
trailing half left in place. **This round's tables are one row per annotation,
nothing merged and nothing elided**, and the machine-readable source is
committed beside this file as `round2_annotations.json`.

Work annotation by annotation from the JSON, and after each deletion test that
the span's **tail** is gone, not just its opening words.

---

## 0.3 Decisions already taken (do not re-litigate)

1. **Scope of the "all agents" comments = all 9 agents of the 7-agent system.**
   Four comments say "remove from ALL the agents prompts" / "do the same thing
   for ALL agent system prompts". That covers the four agents reduced in round 1
   and the DC Output Inspector, not only the three reviewed here. The 5- and
   3-agent prompt sets are out of scope.
2. **The DC Output Inspector gets §A only** — the heading merge and the ROUTING
   restructure. **No content cuts**, since its body has not been reviewed.
   The **Database Handler is untouched**: it carries none of those headings and
   has no routing section.
3. **The ROUTING rebuild lands in `agents/shared/routing.py`, gated to
   topology 7**, so the dormant 5- and 3-agent systems keep today's output.
4. **`write_parameters` and `new_attempt` merge into one tool with no path
   argument.** Both names disappear from the codebase.
5. **The Tool Caller loses `read_parameters` too**, not just the DCII. Every
   reference to reading an attempt becomes `read_attempts(n)`, and any prose
   that only made sense for a path-based reader is rewritten around what
   `read_attempts` can actually do.
6. **The attempt NUMBER goes on the same line as the attempt PATH**, since they
   name the same thing (§A4).
7. **Hard constraints become one section, keeping all four sub-headings**, minus
   every "(every agent)" parenthetical (§A1).

---

## A. Cross-cutting changes — all 9 agents

These come from comments on pp. 1, 29 and 30 that explicitly say "all agents".
Apply them to every agent that still carries the structure, including the four
reduced in round 1 and the DC Output Inspector.

### A1. One "Hard constraints" section

Today an agent prompt carries three sibling sections. Collapse them into one.

Remove:

* the section title `## Hard constraints — DC-specific` (7 prompts still have it)
* the section title `## Hard constraints — tool-specific` (8 prompts)
* the suffix `— generic (apply to every agent)` from `## Hard constraints — generic (apply to every agent)` (6 prompts)
* the parenthetical `(every agent)` from the two sub-headings `### Domain hard rules (every agent)` and `### Tool-use hard rules (every agent)` — these live in the **shared** fragments `DC_prompt_fragments/dc_config/hard_constraints_dc.md:1` and `DC_prompt_fragments/tools_config/hard_constraints_tools.md:1`, so one edit each reaches every agent, which is what is wanted

Keep: a single `## Hard constraints` heading, and all four sub-headings —
`### DOs`, `### DON'Ts`, `### Domain hard rules`, `### Tool-use hard rules` —
in that order, with the DC and tool rules now nested under the one section.

### A2. Rebuild the routing block as one `## ROUTING` section

`agents/shared/routing.py:routing_instructions()` currently emits `## Routing`,
then `### How to decide where to route` (four decision bullets), then the
per-agent *Available routing tools* fragment, then three more sub-sections.
Round 1 already suppressed the trailing sub-sections for the Planner and the
UII via `_ROUTING_SECTIONS_BY_AGENT`.

The four decision bullets must be folded into the tool bullets they describe,
and the sub-headings dropped. The mapping the reviewer gave for the Tool Caller
generalises to every chain agent:

| decision bullet | attaches to |
|---|---|
| 1 — instruction says continue, and your work succeeded → FORWARD | the **next-agent** tool (`call_dc_output_inspector` for the TC) |
| 2 — instruction says report back / do X and return | the **hub** tool (`call_orchestrator`) |
| 3 — hand-off ambiguous, missing data, or an error the sender can fix → CLARIFY | the **previous-agent** tool (`call_dc_input_inspector` for the TC) |
| 4 — fundamentally wrong, no agent in the chain can fix it → ESCALATE | the **hub** tool (`call_orchestrator`) |

Also:

* Title the whole thing `## ROUTING`. Drop `### How to decide where to route`
  and `### Available routing tools` as separate headings.
* In bullet 1, replace the generic phrase `the next agent` with the actual
  agent's display name (p. 30: "DC Output Inspector").
* Bullet 3's `the agent that handed you this work — normally the <X> —` collapses
  to just the named agent, since it is now attached to that agent's own tool.
* The existing FORWARD condition already on the tool bullet is replaced by
  bullet 1's text, not appended to it — on p. 30, `— FORWARD when mesh + renders
  report all exist.` is struck through.
* Gate the new layout on `topology() == 7`. The 5- and 3-agent topologies share
  this module and must keep today's output.

What survives after the merge, still under `## ROUTING`: the tool bullets with
their folded-in conditions, and the closing paragraph "Do NOT describe or
announce which tool you intend to call… only the tool's `message` argument is."
minus its final sentence ("Keep that reasoning terse…"). Everything else the
builder emits is struck through on pp. 8-9, 21-22 and 30.

### A3. Domain structure wording (p. 1)

`DC_prompt_fragments/dc_config/structure.md` — consumed by the UII and the DCIC.
Two changes, both flagged "Change this for ALL domain structure sections present
in the agents that have it":

1. `so its radius = 4 + middlePos·(impellerRadius − 4) mm` → phrase it as a
   position, e.g. "it is positioned at radius 4 + middlePos·(impellerRadius − 4) mm".
2. **`impellerRadius` is used before it is introduced.** The domain-structure text
   names the outer ring by "radius, height, and wall thickness" but never ties
   that to the parameter name, so `impellerRadius` appears cold — and the
   "impeller" prefix invites confusion. Introduce it earlier in the same
   fragment, where the outer ring is first described.

### A4. Carry the attempt number beside the attempt path

`read_attempts(n)` takes attempt NUMBERS, but hand-offs carry PATHS. Rather than
force a lookup call, put the number on the same line as the path it refers to:

```
Current attempt 3: <absolute attempt folder path>
```

Update every producer and consumer of that label — the DCII's hand-off to the
Tool Caller (§C2), the Orchestrator's hand-offs, and the DCOI's reading of it.

---

## B. Tool-layer changes

### B1. DCIC — merge `write_parameters` + `new_attempt` into one tool

p. 11: *"join this with the write_parameters. Since the writing of parameters
always comes after creating a new attempt, it is not useful to split the two
tools. Rename this tool to something like 'new_attempt_parameters', and let it
CREATE the folder, with the desired optional slug, and with the desired optional
description, and let the system write the parameters as it is currently done in
the write_parameters. No need for a path input parameter. So, the tool will have
3 inputs in total. Join smartly, with no repetition of concepts, the two tool
descriptions as well!"*

```
new_attempt_parameters(parameters: dict,
                       slug: str = "attempt",
                       description: str = "") -> str
```

* Creates the attempt folder (timestamp + sequence + `slug`), writes
  `description.txt` when `description` is non-empty, then writes `parameters.json`
  into that same folder.
* **No path argument.** The folder it creates is the folder it writes into, so
  the two can never disagree — which is most of what the old prompt text about
  "which folder to write into" existed to prevent.
* Returns the folder's absolute path plus its attempt number, so the DCIC can
  put both on its `Current attempt N:` hand-off line (§A4).
* Both `new_attempt` and `write_parameters` are deleted. `new_attempt` is bound
  nowhere else — round 1 removed the Orchestrator's copy.
* Merge the two tool descriptions into one, without restating the shared
  concepts.

**Prompt consequence:** the DCIC's "Attempt folders" section (prompt L231-244) is
almost entirely red already, including the (A)/(B) branch on whether a folder was
pre-opened. With no path argument that branch cannot exist, so the red cuts and
this tool change agree.

### B2. DCII — one reader for the raw inputs, none for parameters

* **Drop `read_parameters`** (p. 22: *"not required since read_attempts already
  allows the agent to read json files of specific attempts"*).
* **Drop `list_input_files`, `read_input_text`, `read_image_notes`** and bind the
  UII's `read_user_inputs` instead (p. 24: *"as for the planner, give this agent
  the same tool as the UII, aka the read user inputs tool that was adapted"*).
* **Keep `read_extracted_inputs`** — axis 4 is literally the consistency check
  between `parameters.json` and `extracted_inputs.txt`, so it stays the primary
  reader, exactly as the Planner kept it in round 1.
* Keep `view_images` and `ocr_regions`; neither card is highlighted.

### B3. Tool Caller — every attempt read goes through `read_attempts(n)`

* **Drop `read_parameters`.**
* Rewrite every reference in the TC prompt so the attempt reader is
  `read_attempts(n)`, and re-word around what that tool actually does rather
  than what a path-based reader did. The live references are
  `agents/tool_caller/prompt.md:27` (the "when you need to SEE the values" line)
  and `:100-102` (the diagnostic-helper section).
* **The `Parameters file:` label stays.** It is not there for reading — it is the
  argument both geometry tools take. `generate_and_render_propeller(parameters_path)`
  and `render_blade_sections` are called with that absolute path
  (`tools/generate_mesh/generate_mesh.py:779-787`). Removing the reader does not
  remove the path.
* The TC prompt's staleness guidance at `:37-40` (re-read when the label says
  `(newly written this cycle)`) is red-marked and goes; nothing else depended on
  `read_parameters` for correctness.

### B4. DCIC — drop the raw-input readers

p. 12: *"The DCIC doesn't need to look directly at the inputs folder content"* —
drop `list_input_files` and `read_input_text`. The DCIC works from
`extracted_inputs.txt` via `read_extracted_inputs`, which its prompt already says
(`:262` "themselves — rely on the extraction", itself red because it is now
redundant). Unlike the DCII, the DCIC does **not** gain `read_user_inputs`.

### B5. Bind lists — before → after

| agent | today | remove | add | after |
|---|---|---|---|---|
| **DCIC** | 11 (+2 RAG) | `write_parameters`, `new_attempt`, `list_input_files`, `read_input_text` | `new_attempt_parameters` | `read_extracted_inputs`, `new_attempt_parameters`, `read_attempts`, `calculate`, 4 × `call_*` (+ `database_search`, `retrieve_attempt`) = **8 (+2)** |
| **DCII** | 12 (+3 RAG) | `read_parameters`, `list_input_files`, `read_input_text`, `read_image_notes` | `read_user_inputs` | `read_extracted_inputs`, `read_user_inputs`, `calculate`, `read_attempts`, `view_images`, `ocr_regions`, 3 × `call_*` (+ 3 RAG) = **9 (+3)** |
| **TC** | 8 | `read_parameters` | — | `generate_and_render_propeller`, `render_blade_sections`, `calculate`, `read_attempts`, 3 × `call_*` = **7** |
| **DCOI** | 9 (+2 RAG) | — | — | unchanged (§A only) |

---

## C. Per-agent changes

### C1. DC Input Creator — annotated pp. 1-13

#### C1.1 Scoped copies to create

Same rule as round 1: a shared fragment cut differently per agent gets a
per-agent copy, so unreviewed agents keep today's text.

| new file | copy of | why |
|---|---|---|
| `DC_prompt_fragments/dc_config/modelling_notes_dc_input_creator.md` | `modelling_notes.md` | 3 spans cut; DCII cuts a different subset, DCOI/TC are unreviewed |
| `DC_prompt_fragments/dc_config/qualitative_examples_dc_input_creator.md` | `qualitative_examples.md` | 1 span cut |
| `agents/shared/prompt_fragments/value_states_dc_input_creator.md` | `value_states.md` | 9 spans cut |
| `agents/shared/prompt_fragments/generic_constraints_dc_input_creator.md` | `generic_constraints.md` | 4 spans cut |
| `DC_prompt_fragments/dc_config/hard_constraints_dc_dc_input_creator.md` | `hard_constraints_dc.md` | 3 spans cut |
| `DC_prompt_fragments/tools_config/hard_constraints_tools_dc_input_creator.md` | `hard_constraints_tools.md` | 1 span cut |
| `DC_prompt_fragments/dc_config/structure_dc_input_creator.md` | `structure.md` | §A3 rewording — but see the note below |

**Two slots still need registering** in `agents/shared/prompts.py:SCOPED_FRAGMENTS`
before their scoped copies are read at all: `modelling_notes` and
`qualitative_examples`. `value_states`, `dc_structure`, `hard_constraints_generic`,
`hard_constraints_dc` and `hard_constraints_tools` were registered in round 1.

**§A3 is a shared change, not a scoped one** — the wording fix applies to every
agent that carries the domain structure, so make it in `structure.md` itself and
do **not** create a DCIC scoped copy for it. The row above is listed only so you
notice the overlap.

#### C1.2 "Which lever moves what" becomes its own chapter

p. 4: *"This 'lever' explanation of blades sections and overall propeller should
be turned into its own important chapter moved to be one of the first chapters,
right after the parameters list."*

Move the block that runs from "Which lever moves what:" through the `*Thickness`
/ `*Camber` ratios paragraph out of "Acting on a Planner / Orchestrator
qualitative directive" and place it directly after the parameter list, titled
`## Which lever moves what`. Within it:

* `Which lever moves what:` → **"Regarding the size and shape of blade sections,
  here a list of which lever moves what:"**
* the `**Shape**` bullet label → **"shape of blade sections"**
* the `**Size**` bullet label → **"size of blade sections"**
* after the ratios paragraph, add a second sub-paragraph — the reviewer's own
  words and bullets, verbatim:

  > Regarding the size and shape of the propeller as a whole:
  > - chords, angles, section shape parameters, impellerRadius, and middlePos, all change how a blade looks from different angles
  > - impellerRadius changes both overall size of the propeller and the shape of its blades
  > - number of blades does not change the shape of the blades
  > - outer ring thickness changes the size and looks of the outer ring

  Its position is marked on p. 4 by "put the additional small paragraph I
  mentioned here" — immediately before the FULL-3D paragraph, which is itself
  red and goes.

#### C1.3 Other comment-driven edits

* **p. 2** — yellow `defaults` → "new parameters values"; yellow
  `User Input Inspector` → name the file it produces:
  "file of extracted user inputs `extracted_inputs.txt`".
* **p. 3** — yellow `the system's` → "your". The dark-yellow "How FAR an
  authorised (or soft) value may move…" paragraph in `value_states.md:41-45`
  moves **into the "Writing each state" paragraph** that follows, placed before
  "Never write a soft target as a locked…".
* **p. 8** — yellow `no agent in the chain can` → "you cannot". Also
  "join this with the write_parameters" — the routing-section note is subsumed by
  §A2 and B1.
* **p. 10** — `list_attempts` card: already renamed in round 1, nothing to do.

#### C1.4 Every annotation, with its source anchor

**One row per annotation — nothing merged, nothing elided.** `lines` are 1-based in the named file at `afc33fa`; `p.` is the annotated PDF page. `RED` = delete the text. `YEL` / `DKYEL` = modify, per the comment recorded above. The same data is in `round2_annotations.json` — prefer iterating that.

##### `DC_prompt_fragments/dc_config/hard_constraints_dc.md` — 3 annotations

> ⚠ Shared file. Make this cut in the scoped copy `DC_prompt_fragments/dc_config/hard_constraints_dc_dc_input_creator.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 1-1 | RED | 7 | Domain hard rules (every agent) |
| 4-4 | RED | 7 | via the DC Input Creator → Tool Caller path. |
| 5-6 | RED | 7 | (hub_radius, fillet_radius, tip_clearance, any "supplemental" value) |

##### `DC_prompt_fragments/dc_config/modelling_notes.md` — 3 annotations

> ⚠ Shared file. Make this cut in the scoped copy `DC_prompt_fragments/dc_config/modelling_notes_dc_input_creator.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 5-5 | RED | 2 | (the middle section's radial position) |
| 32-35 | RED | 2 | Absolute mm ↔ fraction / percent of an overall scale parameter (when the user expresses a chord, height, or similar absolute- unit value as a fraction of diameter or radius, multiply by the corresponding scale). |
| 43-53 | RED | 2 | Hard engineering blockers (parameter combinations that break the geometry) These combinations make the geometry physically impossible or self-intersecting — flag them as hard blockers wherever you check parameter consistency: innerThickness ≤ 0 or outerThickness ≤ 0 → degenerate blade section. These are physics-derived blockers, not style preferences; treat any violation as a non-negotiable fail. |

##### `DC_prompt_fragments/dc_config/qualitative_examples.md` — 1 annotation

> ⚠ Shared file. Make this cut in the scoped copy `DC_prompt_fragments/dc_config/qualitative_examples_dc_input_creator.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 5-5 | RED | 2 | "blades closer to center"→ middlePos toward 0.3 |

##### `DC_prompt_fragments/dc_config/structure.md` — 1 annotation

> ⚠ Shared file. Make this cut in the scoped copy `DC_prompt_fragments/dc_config/structure_dc_input_creator.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 8-8 | YEL | 1 | middlePos·(impellerRadius |

##### `DC_prompt_fragments/tools_config/blade_sections_visualizer.md` — 1 annotation

> The whole fragment is dropped for this agent — delete the `$slot` line and its heading from the prompt rather than editing this file.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 1-12 | RED | 8 | Blade-sections visualizer The system can render JUST the blade cross-sections — a flat image showing the three blade sections (Inner, Middle, Outer) stacked vertically, each at its true angle of attack — without building the full 3D propeller. The Tool Caller generates it (the render_blade_sections tool) from an attempt's parameters file; the image is shown to the user and can be read by any agent that can load images. Because it skips the slow full-3D mesh generation, it is much faster than producing the whole propeller — so when a request centres on the blade sections (section drawings or specific section details), the sections can be rendered and refined cheaply on their own, and can even be the final deliverable. When the plan is a blade-sections task — render the sections, not the full 3D propeller — say so explicitly in your hand-off to the Tool Caller: tell it to render the blade sections. Write parameters.json and create the attempt as usual; the Tool Caller will render the sections from that file instead of generating the mesh. |

##### `DC_prompt_fragments/tools_config/hard_constraints_tools.md` — 1 annotation

> ⚠ Shared file. Make this cut in the scoped copy `DC_prompt_fragments/tools_config/hard_constraints_tools_dc_input_creator.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 2-3 | RED | 7 | Every path you hand a tool must trace to your incoming message or to a tool result. |

##### `agents/dc_input_creator/prompt.md` — 45 annotations

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 17-18 | RED | 2 | 1. Never replace a value the user gave with a default of your own — write what its LOCKED / SOFT TARGET / FREE state calls for. |
| 22-23 | RED | 2 | 3. For any parameter the user did not mention at all (neither numerically nor qualitatively), pick a reasonable mid-range default. |
| 30-30 | YEL | 2 | User Input Inspector |
| 36-38 | RED | 3 | Whether you may then move it off the user's number is set by its state (LOCKED / SOFT TARGET / FREE — see the next section). |
| 52-54 | RED | 3 | from the first attempt onward — do NOT anchor on the user's number and argue your way off it; fall back to that number only when the goal does not bear on that parameter. |
| 86-87 | RED | 4 | silently omitting an input you could act on (honour it or decline with a reason); |
| 102-103 | RED | 4 | (distributing would meaningfully diverge AND no single parameter is more plausible), |
| 105-107 | RED | 4 | Avoid silently duplicating the same value across all candidate parameters — that fabricates lock-in the user never specified. When you distribute, do so deliberately and say so. |
| 120-120 | RED | 4 | without a specific parameter named |
| 134-136 | RED | 4 | — list which parameters you would have wanted to change and exactly why you cannot. |
| 138-140 | RED | 4 | Move ANY parameter the directive authorises in the direction the DCOI described, holding fixed only what the user fixed — a SOFT TARGET is not locked, it is an available lever. |
| 140-140 | YEL | 4 | Which lever moves what: |
| 155-156 | RED | 4 | Each later round nudges toward the DCOI's newest feedback, and every round is a fresh generation — a new attempt. |
| 165-173 | RED | 4 | When the directive instead targets the FULL 3D (matching a top / side sketch of the whole propeller), the lever set WIDENS to whatever UNLOCKED parameter moves the mismatched aspect the DCOI named — a section's radial position ( middlePos ), a chord, an angle, or the ring proportions — still leaving every locked user number untouched. If NO unlocked parameter can move the mismatched aspect (the levers that would help are all locked — remembering that a SOFT TARGET counts as available, NOT locked), do not touch a locked value: ESCALATE with a concrete note on which locked parameters would have to change, so the DCOI reports the limit honestly. |
| 178-178 | RED | 10 | write_parameters |
| 182-183 | RED | 5 | Not a glance and not a blanket "all 16 are in bounds" — compare each value to the range printed in the parameter list above. |
| 185-187 | RED | 5 | 2. The hard-blocker inequalities from ## Modelling Notes — compute them with calculate (batch them in one call alongside your range arithmetic) and fix any violation. |
| 194-195 | RED | 5 | so item 1 says fix it and item 3 says restore it. |
| 199-200 | RED | 5 | naming the parameter, its value and its allowed range — only the user can revise their own number. |
| 202-205 | RED | 5 | Fix what you find in the DRAFT and re-check. Only a draft that passes gets an attempt folder and a write. If a problem needs the user or a decision only the Planner can make, ESCALATE — do not write a set you know to be wrong. |
| 207-214 | RED | 5 | The DC Input Inspector independently re-checks EVERYTHING you just checked — every range, every inequality, every moved user value — and adds the deeper checks on top. That redundancy is deliberate: you can make a mistake reviewing your own work, so your check NEVER substitutes for the DCII's. Yours exists to catch your slips early, and because on a precision refine round you forward straight to the Tool Caller — which re-checks the ranges but nothing else — yours is then the only check on whether you were authorised to move the user values you moved. |
| 221-222 | RED | 5 | parameters.json and the mesh are append-only: once written, no one (including you) overwrites them; existing renders are reused in place. |
| 225-226 | RED | 5 | You are stateful — before each write, check your prior write_parameters calls; |
| 228-229 | RED | 5 | A no-op tells the pipeline you "did something" when you did not and wastes a downstream cycle. |
| 231-231 | RED | 5 | Which folder to write into — |
| 231-240 | RED | 5 | Open the folder only once your draft has PASSED the checks above, so a check that escalates never leaves an empty attempt behind: (A) The hand-off carries Current attempt: <path> (rare — an empty folder the Orchestrator pre-opened for you as a fallback when you could not open one) → write into that folder. (B) No such label (a NEW generation — the normal case; the Planner names the slug + intent but does NOT open the folder) → call new_attempt (short descriptive slug + one-line intent) ONCE, then write parameters.json into the path it returns. |
| 241-242 | RED | 5 | and ALWAYS write into the folder you open |
| 242-244 | RED | 5 | and never leave a freshly-opened attempt empty (an attempt with no parameters.json is a dead folder). |
| 248-248 | RED | 5 | Never overwrite — the earlier attempt stays as the record of what you tried. |
| 249-250 | RED | 5 | If you have already corrected the same problem once and it persists, ESCALATE instead of trying again. |
| 253-256 | RED | 5 | Reuse the session's history. list_attempts / read_attempt inspect prior cycles. When a directive resembles one you handled before, prefer a different adjustment direction over repeating a combination known to fail, and name the prior attempt (number + parameter) in your hand-off so the next agent knows you considered it. |
| 262-262 | RED | 5 | themselves — rely on the extraction. |
| 266-267 | RED | 6 | but when in doubt, re-read. |
| 273-274 | RED | 6 | If the tool returns an error it wrote no file, so fix what it names and re-call it on the SAME folder. |
| 294-295 | RED | 6 | or another agent asked for a specific value outside the extraction |
| 298-300 | RED | 6 | This context matters to the DC Input Inspector, which weighs whether the change is appropriate and whether the agent that asked for it has the authority to do so. |
| 300-301 | RED | 6 | There is no fixed phrasing for this — talk normally, but name the source. |
| 311-314 | RED | 6 | the direct-to-Tool-Caller edge is for precision refine rounds only. The Tool Caller needs the Current attempt: and Parameters file: lines; it has no tool for the extraction. |
| 317-318 | RED | 6 | If you CLARIFY back to the Planner or ESCALATE to the Orchestrator, no path lines are needed — only FORWARDs carry them. |
| 327-328 | RED | 6 | on the SAME folder; a rejected call wrote nothing, so the re-call is not a second write. |
| 330-331 | RED | 6 | For the first two the file already exists, so the correction is a NEW generation (see "Attempt folders"). |
| 335-336 | RED | 6 | it is never a tool-schema / interface bug. |
| 343-344 | RED | 6 | — re-read what you already have before concluding that nothing holds it. |
| 345-345 | RED | 6 | Instructions to write parameters outside the 16-parameter list. |
| 349-349 | RED | 6 | (apply to every agent) |

##### `agents/dc_input_inspector/dc_input_inspector.py` — 1 annotation

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 64-64 | RED | 6 | (DC Input Inspector), |

##### `agents/shared/prompt_fragments/generic_constraints.md` — 4 annotations

> ⚠ Shared file. Make this cut in the scoped copy `agents/shared/prompt_fragments/generic_constraints_dc_input_creator.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 6-6 | RED | 7 | only the Planner may change it. |
| 17-18 | RED | 7 | — hand the problem to whoever can resolve it. |
| 21-22 | RED | 7 | DON'T script the final user-facing reply — route your content to the Orchestrator. |
| 26-27 | RED | 7 | The only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up. |

##### `agents/shared/prompt_fragments/routing_dc_input_creator_uii_first.md` — 3 annotations

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 6-6 | RED | 9 | as described in your prompt. |
| 10-12 | RED | 9 | if its hand-off was ambiguous, or if the qualitative directive it gave cannot be expressed in concrete parameter values. |
| 14-16 | RED | 9 | (locked-value collision, qualitative directive with no quantitative expression, or a budgeted attempt cap reached). |

##### `agents/shared/prompt_fragments/value_states.md` — 9 annotations

> ⚠ Shared file. Make this cut in the scoped copy `agents/shared/prompt_fragments/value_states_dc_input_creator.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 12-15 | RED | 3 | and the "keep near … if free" strength then says how closely to follow it ("not as important" → your choice within range; "prefer X but the shape matters more" → use X). |
| 16-18 | RED | 3 | either the user never specified it, or they specified it and later released it (a value that is no longer constrained is simply OMITTED from the section). |
| 19-22 | RED | 3 | A qualitative description that must be turned into a number is FREE for that parameter too — unless a directive holds a specific one fixed, which is then treated as LOCKED for that cycle. |
| 27-28 | RED | 3 | scoped "except <param X>", |
| 29-30 | RED | 3 | a CLARIFY bounce may carry one too; |
| 31-32 | RED | 3 | — a user authorisation the UII wrote, standing every cycle until revoked; |
| 34-36 | RED | 3 | IF PRESENT — an older extraction may still carry this inline mark; today a released value is simply omitted from the section (which makes it FREE) rather than annotated. |
| 38-40 | RED | 3 | A line literally saying "user-locked" is only the DEFAULT lock and does NOT override a current authorisation — |
| 41-45 | DKYEL | 3 | How FAR an authorised (or soft) value may move follows the wording: "as needed / only if necessary" = the smallest change that restores viability, staying close to the user's number; "freely / as much as possible" (or nothing said) = as far as the goal requires, bounded by range. |

##### `agents/shared/routing.py` — 2 annotations

> Generated at runtime. This text is not edited in place — it is produced by `routing_instructions()` and is restructured wholesale by §A2.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 315-315 | RED | 8 | since no instruction to report back means continue), |
| 324-324 | YEL | 8 | no agent in the chain can |

##### No automatic source match — place by hand

A span lands here when it is under ~15 characters, when it covers only a tool's name (meaning “this tool” — the action is on the binding), when it is text generated at runtime by `routing_instructions()`, or when round 1 already removed it. Each is accounted for in the narrative above.

| colour | p. | exact highlighted text |
|---|---|---|
| YEL | 1 | its radius |
| YEL | 2 | defaults |
| RED | 3 | Either way |
| YEL | 3 | the system's |
| RED | 3 | "as needed / |
| RED | 3 | round, |
| RED | 3 | re-scale, |
| YEL | 4 | Shape, |
| YEL | 4 | Size |
| RED | 5 | / read_attempt |
| YEL | 5 | list_input_files |
| RED | 5 | read_input_text |
| RED | 6 | mandatory: |
| RED | 6 | is REQUIRED — it |
| RED | 6 | Planner |
| RED | 7 | Batch into ONE call; a second only when a later expression needs an earlier result. |
| RED | 8 | Routing You are one agent in a decentralised pipeline. The natural flow is: Orchestrator → User Input Inspector → Planner → DC Input Creator → DC Input Inspector → Tool Caller → DC Output Inspector → Orchestrator Your position: DC Input Creator. - Your natural next in line is: DC Input Inspector. - Your natural previous in line is: Planner. |
| RED | 8 | — normally the Planner — |
| RED | 9 | Do not loop — ESCALATE when stuck If you find yourself about to call the same tool with the same arguments you already called earlier in this turn, STOP. Calling the same read tool twice on unchanged input, or re-thinking the same decision in a loop, will not give you new information. Instead, ESCALATE to the Orchestrator with a short note describing what is ambiguous or missing and what you would need to proceed. The Orchestrator can then re-dispatch you with new instructions, consult another agent, or ask the user. Never silently loop. |
| RED | 9 | Permission / authorisation issues → Orchestrator (not the previous agent) If a rule in your system prompt blocks an action unless some authorisation is present, READ THE INCOMING HAND-OFF (and any upstream file the hand-off points to, e.g. extracted_inputs.txt) ONCE MORE before escalating. If the hand-off already names an authorisation that plausibly covers the action — even if the wording differs from a template you expected — act on it. Do NOT bounce back to the previous agent in the chain for a ritual re-confirmation of something the hand-off already carries; that is a wasted round-trip. |
| RED | 9 | When an authorisation is truly missing or ambiguous, ESCALATE to the Orchestrator. The previous agent in the chain typically CANNOT grant permission — authorisations come from the user (relayed by the Receptionist → Orchestrator), from the Planner (relayed by the Orchestrator), or from the Orchestrator itself. CLARIFY back to the previous agent is appropriate for data / wording / format issues the previous agent can actually fix, NOT for permission questions. |
| RED | 9 | Every response that ends your turn MUST invoke exactly one of the routing tools listed above. The tool's message argument IS the complete hand-off text the recipient will see — there is NO separate audit block to emit. Do NOT write a ---ROUTING--- / --- MESSAGE--- / ---END--- template; that format has been retired. The tool call is the routing decision; its message argument is the hand-off. |
| RED | 9 | Do NOT write a ---ROUTING--- / --- MESSAGE--- / ---END--- template; that format has been retired. |
| RED | 9 | Write the message argument as free-form prose: no fixed template, no enumerated option menus, no placeholder phrasings. Include everything the recipient genuinely needs (paths the recipient's tools require, context about what changed and why, authorship of any non-user-authored values) and nothing they do not. Your verbose work product stays in your own history and (where applicable) on disk — do not duplicate it inside the message argument. |
| RED | 9 | Keep that reasoning terse (one or two lines is plenty). |
| DKYEL | 10 | list_attempts |
| RED | 11 | read_attempt |
| DKYEL | 11 | new_attempt |
| RED | 12 | list_input_files |
| RED | 13 | read_input_text |

---

### C2. DC Input Inspector — annotated pp. 14-26

#### C2.1 Scoped copies to create

| new file | copy of | why |
|---|---|---|
| `agents/shared/prompt_fragments/value_states_dc_input_inspector.md` | `value_states.md` | 9 spans cut (same set as the DCIC — but scope them separately, the DCOI still reads the shared file) |
| `agents/shared/prompt_fragments/generic_constraints_dc_input_inspector.md` | `generic_constraints.md` | 4 spans cut |
| `DC_prompt_fragments/dc_config/hard_constraints_dc_dc_input_inspector.md` | `hard_constraints_dc.md` | 2 spans cut |
| `DC_prompt_fragments/tools_config/hard_constraints_tools_dc_input_inspector.md` | `hard_constraints_tools.md` | 1 span cut |
| `DC_prompt_fragments/dc_config/modelling_notes_dc_input_inspector.md` | `modelling_notes.md` | 1 span cut |
| `DC_prompt_fragments/dc_config/parameters_dc_input_inspector.md` | `parameters.md` | 1 span cut |

#### C2.2 §4 — "Consistency between parameters.json, extracted_inputs.txt, and the user inputs themselves"

Four changes, all on p. 17, plus one relocation from p. 15:

1. **Insert the relocated sentence** after "…but it is NOT the sole source of
   truth." — the surviving yellow sentence from the deleted "Optional reference:
   user input images" section:

   > Whether the extraction's textual treatment suffices or the image is worth
   > re-loading depends on how complex it is, which you learn from the UII's
   > readability note in `extracted_inputs.txt`, from what your incoming hand-off
   > relays, and from the image note itself.

   Everything else in that section is red — delete the section entirely.
2. **Yellow** `When you have reason to doubt how the UII captured something —` →
   **"Other reasons to re-check are inconsistencies, such as:"**, and turn the
   comma-separated list that follows into **bullet points**.
3. **Yellow** `— you can and should` → **". In such cases, you can and should…"**
   (closing the previous sentence, starting a new one).
4. **Yellow** `*` — the inline `*` list markers in "* any authorisation listed
   above frees it; * a SOFT TARGET marker…" become **`-`**, and must **stack
   vertically** as a real list rather than running inline.
5. **Yellow** `Planner` in "user-imposed with no authorisation, or a Planner
   'keep fixed'" → **"system directive"**.

#### C2.3 Verdict → routing

p. 18: the APPROVE bullet's yellow tail ("and unlikely to repeat a known-bad
outcome. An approved set — including a retry set whose authorisation you judged
valid — goes to the Tool Caller, never back to the Orchestrator for a second
opinion; the sole exception is an incoming instruction that told you to report
back rather than continue.") is **replaced** by:

> ". OR If the Orchestrator's instruction in your incoming message told you to
> continue the pipeline (explicitly or implicitly) and your own checks all
> succeeded"

**Move the hand-off contract under APPROVE.** p. 18/19: *"Put here the content of
what once was the 'Hand-off to the Tool Caller (IMPORTANT)'"* / *"Put the yellow
text … under the 'APPROVE' bullet point of Verdict → routing"*. The surviving
yellow of that section is its opening sentence plus the code block:

```
Current attempt 3: <same path the DCIC gave you>
Parameters file (newly written this cycle): <Current attempt>/parameters.json
```

(note the attempt number, per §A4). The rest of the section — prompt L277-295 —
is red and goes with the heading.

**Add to the ESCALATE bullet**, verbatim from the comment:

> Any of the problems specified in the "What to Check" above that require
> escalation to the orchestrator. OR if the orchestrator, planner or any system
> directive told you to "report back once you are done" or to "do X and return".

#### C2.4 Tool-section consequences

`read_parameters` is unbound (§B2), so the yellow at prompt `:53-54`
(`read_parameters(path)` / "Parameters file: path your incoming hand-off carries,
verbatim") is rewritten per the p. 16 comments: **"read_attempts, instead of
read_parameters"** and **"'attempt numbers you want to check', instead of
'Parameters file: …'"**.

#### C2.5 Every annotation, with its source anchor

**One row per annotation — nothing merged, nothing elided.** `lines` are 1-based in the named file at `afc33fa`; `p.` is the annotated PDF page. `RED` = delete the text. `YEL` / `DKYEL` = modify, per the comment recorded above. The same data is in `round2_annotations.json` — prefer iterating that.

##### `DC_prompt_fragments/dc_config/hard_constraints_dc.md` — 2 annotations

> ⚠ Shared file. Make this cut in the scoped copy `DC_prompt_fragments/dc_config/hard_constraints_dc_dc_input_inspector.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 2-3 | RED | 19 | Hard constraints — DC-specific Domain hard rules (every agent) The 16 named parameters are the ONLY design levers and there is no mesh-editing capability: geometry changes only by changing them |
| 3-6 | RED | 19 | and regenerating via the DC Input Creator → Tool Caller path. Reject invented parameters (hub_radius, fillet_radius, tip_clearance, any "supplemental" value) — they do not exist. |

##### `DC_prompt_fragments/dc_config/modelling_notes.md` — 1 annotation

> ⚠ Shared file. Make this cut in the scoped copy `DC_prompt_fragments/dc_config/modelling_notes_dc_input_inspector.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 43-53 | RED | 15 | Hard engineering blockers (parameter combinations that break the geometry) These combinations make the geometry physically impossible or self-intersecting — flag them as hard blockers wherever you check parameter consistency: innerThickness ≤ 0 or outerThickness ≤ 0 → degenerate blade section. These are physics-derived blockers, not style preferences; treat any violation as a non-negotiable fail. |

##### `DC_prompt_fragments/dc_config/parameters.md` — 1 annotation

> ⚠ Shared file. Make this cut in the scoped copy `DC_prompt_fragments/dc_config/parameters_dc_input_inspector.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 19-19 | RED | 14 | radius = 4 + middlePos·(impellerRadius − 4) mm |

##### `DC_prompt_fragments/tools_config/blade_sections_visualizer.md` — 1 annotation

> The whole fragment is dropped for this agent — delete the `$slot` line and its heading from the prompt rather than editing this file.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 1-12 | RED | 21 | Blade-sections visualizer The system can render JUST the blade cross-sections — a flat image showing the three blade sections (Inner, Middle, Outer) stacked vertically, each at its true angle of attack — without building the full 3D propeller. The Tool Caller generates it (the render_blade_sections tool) from an attempt's parameters file; the image is shown to the user and can be read by any agent that can load images. Because it skips the slow full-3D mesh generation, it is much faster than producing the whole propeller — so when a request centres on the blade sections (section drawings or specific section details), the sections can be rendered and refined cheaply on their own, and can even be the final deliverable. |

##### `DC_prompt_fragments/tools_config/hard_constraints_tools.md` — 1 annotation

> ⚠ Shared file. Make this cut in the scoped copy `DC_prompt_fragments/tools_config/hard_constraints_tools_dc_input_inspector.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 1-1 | RED | 19 | Tool-use hard rules (every agent) |

##### `agents/dc_input_inspector/prompt.md` — 44 annotations

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 28-30 | RED | 15 | each with a <name>_note.txt — the Receptionist enforces the pairing before forwarding, so the note FILE always exists, though its written description is optional and may be blank. |
| 32-32 | RED | 15 | — it costs LLM turns and tokens. |
| 40-43 | RED | 15 | (This is also how you carry out the extraction-fidelity half of axis 4 when you suspect the UII misread something: load the image with view_images and compare it against what the extraction claims.) |
| 53-53 | YEL | 16 | read_parameters(path) |
| 53-54 | YEL | 16 | Parameters file: path your incoming hand-off carries, verbatim. |
| 54-55 | RED | 16 | whenever you are not CERTAIN that what you remember still matches disk, and |
| 57-57 | RED | 16 | normally in a NEW attempt folder, so what you remember describes a DIFFERENT attempt and is STALE. |
| 77-78 | RED | 16 | The DC Input Creator can misjudge its own work, and your independent pass is what catches that. |
| 81-83 | RED | 16 | users can and do provide values the generator cannot handle, and it fails or produces degenerate geometry on them. |
| 93-97 | RED | 17 | The DC-specific list of hard blockers — the parameter combinations that break the geometry, with the exact inequalities to check — lives in the ## Modelling Notes section above; use it as the authoritative checklist this cycle. |
| 97-99 | RED | 17 | Compute each inequality via the calculate tool (batched in a single call alongside your range-validation arithmetic), and |
| 109-109 | YEL | 17 | When you have reason to doubt how the UII captured something — |
| 113-114 | RED | 17 | or the extraction or an incoming hand-off reports that the user's inputs were hard to interpret |
| 115-116 | RED | 17 | only when the doubt cannot be resolved from the extraction alone. |
| 130-130 | RED | 17 | when it dispatches a recovery cycle |
| 131-133 | RED | 17 | A directive to change the value AUTHORISES the move, over any user-imposed value. A directive to keep it fixed LOCKS it, even if the user did not. |
| 135-138 | RED | 17 | * any authorisation listed above frees it; * a SOFT TARGET marker is itself authorisation to move toward its goal — do NOT flag either of these as a violation; * otherwise its QUANTITATIVE INPUTS value is LOCKED; |
| 139-140 | RED | 17 | — never imposed, or imposed and since released — |
| 144-148 | RED | 17 | — but still range-validate the new value (Section 1); authorisation never bypasses [min; max]. When a directive named a specific change, confirm parameters.json reflects it AND respects the "how far" wording it used; a missing move, or a clear overshoot, is a REVISE → CLARIFY back to the DCIC. |
| 151-152 | RED | 17 | — name the parameter, the value it must hold, and why. |
| 152-155 | RED | 17 | Do NOT escalate to the user; it is a DCIC-fixable slip. Escalate to the Orchestrator only if you CLARIFYed once and it persists, or the design is genuinely infeasible without the change. |
| 157-159 | RED | 17 | naming the parameter, its value and its range, so whoever imposed it — the Planner, or the user — can revise it. |
| 165-166 | RED | 17 | Verify that the DCIC's hand-off message carries one of: |
| 168-171 | RED | 17 | The hand-off should name the user's stated quantity, the anchor parameter(s) chosen, the conversion formula, and the resulting parameter value(s). |
| 173-176 | RED | 17 | — judge the margin from the precision of the user's stated value, the integer / float nature of the affected parameter, and any rounding the conversion required. |
| 177-179 | RED | 17 | The hand-off should name the user-stated quantity, the parameters chosen, and |
| 184-186 | RED | 17 | (the unit cannot be reconciled with any parameter, the value is not relevant to design generation, etc.). |
| 192-195 | RED | 18 | engineering judgement explicitly, or decline with a reason. This is a DCIC-fixable issue (regenerate parameters with the conversion / rationale included), not an Orchestrator escalation. |
| 200-200 | RED | 18 | (e.g. a choice like one that failed earlier this session) |
| 208-209 | RED | 18 | to put it to the Planner; |
| 209-209 | RED | 18 | you do not override the Planner yourself. |
| 226-226 | RED | 18 | the pairing never changes: |
| 229-229 | RED | 18 | upstream-directed |
| 230-234 | YEL | 18 | and unlikely to repeat a known-bad outcome. An approved set — including a retry set whose authorisation you judged valid — goes to the Tool Caller, never back to the Orchestrator for a second opinion; the sole exception is an incoming instruction that told you to report back rather than continue. |
| 234-235 | RED | 18 | Minor engineering opinions or style notes do not block APPROVE. |
| 257-264 | RED | 18 | One range exception: an out-of-range value the USER literally provided ESCALATES only when nothing authorises you to move it (only the user can revise their own number). Any authorisation counts — a SOFT TARGET marker, a permission in the hand-off or the extraction's DESIGN INTENT, or a Planner directive; when one applies, CLARIFY back to the DCIC to bring the value into range instead of asking the user. A DCIC-chosen out-of-range value always CLARIFYs back. An unauthorised change is always a DCIC-fixable slip → CLARIFY, never a user escalation. |
| 266-270 | RED | 18 | Two self-checks before you route: 1. If your verdict is APPROVE and you were not told to report back, the tool MUST be call_tool_caller — if you wrote "proceed to the Tool Caller" but are about to call anything else, STOP and fix it (a recurring failure |
| 271-273 | RED | 19 | mode). 2. Confirm you compared each of the 16 parameters against its [min; max] individually — never a memory or a blanket claim. A single out-of-range value makes APPROVE invalid. |
| 275-275 | RED | 19 | Hand-off to the Tool Caller (IMPORTANT) |
| 276-277 | YEL | 19 | When you FORWARD to the Tool Caller, the message argument of your call_tool_caller tool call MUST include these two lines |
| 277-279 | RED | 19 | with the absolute paths the DCIC gave you, preserving the (newly written this cycle) marker exactly: |
| 281-282 | YEL | 19 | Current attempt: <same path the DCIC gave you> Parameters file (newly written this cycle): <Current attempt>/parameters.json |
| 284-295 | RED | 19 | (If the DCIC's hand-off did NOT carry the (newly written this cycle) marker, drop it and just write Parameters file: — but normally the DCIC opens a NEW attempt for each generation and writes that attempt's parameters.json , so the marker will be present.) The Tool Caller ESCALATEs without both labels. It writes into the attempt folder named under Current attempt: — mesh and renders land there — and reads the JSON from the path on the Parameters file: line. The marker tells it that any parameter content it remembers is stale. If you CLARIFY back to the DCIC or ESCALATE to the Orchestrator, no path lines are needed. |
| 297-297 | RED | 19 | (apply to every agent) |

##### `agents/shared/prompt_fragments/generic_constraints.md` — 4 annotations

> ⚠ Shared file. Make this cut in the scoped copy `agents/shared/prompt_fragments/generic_constraints_dc_input_inspector.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 6-6 | RED | 19 | only the Planner may change it. |
| 17-18 | RED | 19 | — hand the problem to whoever can resolve it. |
| 21-22 | RED | 19 | DON'T script the final user-facing reply — route your content to the Orchestrator. |
| 26-27 | RED | 19 | The only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up. |

##### `agents/shared/prompt_fragments/value_states.md` — 9 annotations

> ⚠ Shared file. Make this cut in the scoped copy `agents/shared/prompt_fragments/value_states_dc_input_inspector.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 12-15 | RED | 16 | and the "keep near … if free" strength then says how closely to follow it ("not as important" → your choice within range; "prefer X but the shape matters more" → use X). |
| 16-18 | RED | 16 | either the user never specified it, or they specified it and later released it (a value that is no longer constrained is simply OMITTED from the section). Either way |
| 19-22 | RED | 16 | A qualitative description that must be turned into a number is FREE for that parameter too — unless a directive holds a specific one fixed, which is then treated as LOCKED for that cycle. |
| 27-28 | RED | 16 | scoped "except <param X>", |
| 29-30 | RED | 16 | a CLARIFY bounce may carry one too; |
| 31-32 | RED | 16 | — a user authorisation the UII wrote, standing every cycle until revoked; |
| 34-36 | RED | 16 | IF PRESENT — an older extraction may still carry this inline mark; today a released value is simply omitted from the section (which makes it FREE) rather than annotated. |
| 38-40 | RED | 16 | A line literally saying "user-locked" is only the DEFAULT lock and does NOT override a current authorisation — |
| 41-45 | RED | 16 | How FAR an authorised (or soft) value may move follows the wording: "as needed / only if necessary" = the smallest change that restores viability, staying close to the user's number; "freely / as much as possible" (or nothing said) = as far as the goal requires, bounded by range. |

##### `agents/shared/routing.py` — 1 annotation

> Generated at runtime. This text is not edited in place — it is produced by `routing_instructions()` and is restructured wholesale by §A2.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 315-315 | RED | 21 | since no instruction to report back means continue), |

##### No automatic source match — place by hand

A span lands here when it is under ~15 characters, when it covers only a tool's name (meaning “this tool” — the action is on the binding), when it is text generated at runtime by `routing_instructions()`, or when round 1 already removed it. Each is accounted for in the narrative above.

| colour | p. | exact highlighted text |
|---|---|---|
| RED | 14 | (hub, r = 4 mm), |
| RED | 16 | A blanket assertion like "all 16 values are within bounds" is NOT acceptable. |
| RED | 17 | If parameters.json silently uses a default or unrelated value for the constrained parameter(s) AND the DCIC's hand-off does not acknowledge the real-world-quantity entry at all, CLARIFY back to the DC Input Creator asking it to honour the entry, apply Add the "optional reference" yellow text I had flagged here, after this period in yellow. Instead of "when...", use: "Other reasons to re-check are inconsistencies, such as:" (use bullet points instead of commas" ". In such cases, you can and should..." shouldn't the "*" be a "-" instead? Also, they are not stacking vertically instead of "Planner", should say "system directive" |
| YEL | 17 | — you can of |
| YEL | 17 | and should |
| RED | 17 | sparingly: |
| YEL | 17 | * |
| YEL | 17 | Planner |
| RED | 18 | a value it generated is out of range; a feasibility inequality from ## Modelling Notes is violated, or a value clearly contradicts a STATED design intent, and different values could fix it; an arithmetic / mapping error, or a missing / malformed field; a change was applied but the DCIC did not say who requested it or why — ask for the missing authorship so you can judge it; a LOCKED value moved with no authorisation, a "keep fixed" parameter moved, or an "as needed" directive was clearly overshot (§4a) — regenerate respecting the constraint. |
| RED | 18 | a hard engineering blocker needs user input; you CLARIFYed once and the same problem persists; something is infeasible regardless of the parameters; you have STRONG grounds for a change BEYOND the Planner's directive (§5) — put it to the Planner via the Orchestrator; a required Parameters file: / Extracted inputs file: line is missing. |
| RED | 20 | Batch into ONE call; a second only when a later expression needs an earlier result. |
| RED | 21 | Routing You are one agent in a decentralised pipeline. The natural flow is: Orchestrator → User Input Inspector → Planner → DC Input Creator → DC Input Inspector → Tool Caller → DC Output Inspector → Orchestrator Your position: DC Input Inspector. - Your natural next in line is: Tool Caller. - Your natural previous in line is: DC Input Creator. |
| RED | 21 | How to decide where to route If the Orchestrator's instruction in your incoming message told you to continue the pipeline (explicitly or by default, since no instruction to report back means continue), and your own work succeeded, route FORWARD to the next agent. |
| RED | 21 | If the Orchestrator's instruction told you to report back or to do X and return, route to the Orchestrator once your work is done. If you cannot do your job because the incoming hand-off is ambiguous, missing data, or contains an error the sender can fix, route back to the agent that handed you this work — normally the DC Input Creator — with a clear clarification request (CLARIFY). If something is fundamentally wrong and no agent in the chain can fix it, route to the Orchestrator (ESCALATE). |
| RED | 21 | Available routing tools call_tool_caller(message) — FORWARD when parameters.json passes every check. This is the natural next step in the pipeline. call_dc_input_creator(message) — CLARIFY back to the DC Input Creator when the bad value originated with the DCIC and the DCIC can fix it on its own. call_orchestrator(message) — ESCALATE when the bad value originated with the user (the DCIC cannot unilaterally correct a user-locked value), or when something else blocks the inspection that no chain agent can fix. |
| RED | 21 | Do not loop — ESCALATE when stuck If you find yourself about to call the same tool with the same arguments you already called earlier in this turn, STOP. Calling the same read tool twice on unchanged input, or re-thinking the same decision in a loop, will not give you new information. Instead, ESCALATE to the Orchestrator with a short note describing what is ambiguous or missing and what you would need to proceed. The Orchestrator can then re-dispatch you with new instructions, consult another agent, or ask the user. Never silently loop. |
| RED | 21 | Permission / authorisation issues → Orchestrator (not the previous agent) If a rule in your system prompt blocks an action unless some authorisation is present, READ THE INCOMING HAND-OFF (and any upstream file the hand-off points to, e.g. extracted_inputs.txt) ONCE MORE before escalating. If the hand-off already names an authorisation that plausibly covers the action — even if the wording differs from a template you expected — act on it. Do NOT bounce back to the previous agent in the chain for a ritual re-confirmation of something the hand-off already carries; that is a wasted round-trip. When an authorisation is truly missing or ambiguous, ESCALATE to the Orchestrator. The previous agent in the chain typically CANNOT grant permission — authorisations come from the user (relayed by the Receptionist → Orchestrator), from the Planner (relayed by the Orchestrator), or from the Orchestrator itself. CLARIFY back to the previous agent is appropriate for data / wording / format issues the previous agent can actually fix, NOT for permission questions. |
| RED | 21 | Every response that ends your turn MUST invoke exactly one of the routing tools listed above. The tool's message argument IS the complete hand-off text the recipient will see — there is NO separate audit block to emit. Do NOT write a ---ROUTING--- / --- MESSAGE--- / ---END--- template; that format has been retired. The tool call is the routing decision; its message argument is the hand-off. |
| RED | 22 | Write the message argument as free-form prose: no fixed template, no enumerated option menus, no placeholder phrasings. Include everything the recipient genuinely needs (paths the recipient's tools require, context about what changed and why, authorship of any non-user-authored values) and nothing they do not. Your verbose work product stays in your own history and (where applicable) on disk — do not duplicate it inside the message argument. |
| RED | 22 | Keep that reasoning terse (one or two lines is plenty). |
| RED | 22 | read_parameters |
| YEL | 23 | list_attempts |
| RED | 23 | read_attempt |
| YEL | 24 | list_input_files |
| RED | 24 | read_input_text |
| RED | 25 | read_image_notes |

---

### C3. Tool Caller — annotated pp. 27-33

#### C3.1 Scoped copies to create

| new file | copy of | why |
|---|---|---|
| `agents/shared/prompt_fragments/generic_constraints_tool_caller.md` | `generic_constraints.md` | 3 spans cut |
| `DC_prompt_fragments/dc_config/hard_constraints_dc_tool_caller.md` | `hard_constraints_dc.md` | 1 span cut |
| `DC_prompt_fragments/dc_config/parameters_tool_caller.md` | `parameters.md` | 3 spans cut |
| `DC_prompt_fragments/tools_config/tool_inventory_tool_caller.md` | `tool_inventory.md` | 2 spans cut + the reorder below — **`tool_inventory` needs registering in `SCOPED_FRAGMENTS`** |

#### C3.2 Tool inventory — reorder and renumber (p. 27)

* *"Before the tool to generate and render the propeller (the current 1., will
  become 2.), put the tool to render the blade sections!"* — `render_blade_sections`
  becomes item 1, `generate_and_render_propeller` item 2.
* *"…to render JUST the blade sections…"* — the yellow at prompt `:31` picks up
  that wording.
* *"these points are not vertically-listed"* — the inventory renders as running
  prose; make it a real numbered list.
* *"list_attempts point 3. to be rewritten, both in tool name and in tool short
  explanation"* — becomes `read_attempts`, described by what it now does
  (summary of every attempt, or full `parameters.json` + `description.txt` +
  file paths for the numbers you pass).

#### C3.3 Attempt reading

Per §B3: `read_parameters` is gone; prompt `:27` and `:100-102` are rewritten
around `read_attempts(n)`. The tool card for `list_attempts` on p. 32 is yellow
and `read_attempt` red — both already resolved by round 1's rename; what remains
is the prose.

#### C3.4 Every annotation, with its source anchor

**One row per annotation — nothing merged, nothing elided.** `lines` are 1-based in the named file at `afc33fa`; `p.` is the annotated PDF page. `RED` = delete the text. `YEL` / `DKYEL` = modify, per the comment recorded above. The same data is in `round2_annotations.json` — prefer iterating that.

##### `DC_prompt_fragments/dc_config/hard_constraints_dc.md` — 1 annotation

> ⚠ Shared file. Make this cut in the scoped copy `DC_prompt_fragments/dc_config/hard_constraints_dc_tool_caller.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 3-6 | RED | 29 | geometry changes only by changing them and regenerating via the DC Input Creator → Tool Caller path. Reject invented parameters (hub_radius, fillet_radius, tip_clearance, any "supplemental" value) — they do not exist. |

##### `DC_prompt_fragments/dc_config/parameters.md` — 3 annotations

> ⚠ Shared file. Make this cut in the scoped copy `DC_prompt_fragments/dc_config/parameters_tool_caller.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 6-6 | RED | 27 | (The outer-ring HEIGHT is not a parameter — it is derived automatically to fit the outer blade section.) |
| 15-16 | RED | 28 | innerMaxPos / outerMaxPos move the CAMBER crest only, and do nothing at zero camber. Maximum THICKNESS is fixed at ~30% chord. |
| 19-19 | RED | 28 | radius = 4 + middlePos·(impellerRadius − 4) mm |

##### `DC_prompt_fragments/tools_config/tool_inventory.md` — 2 annotations

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 5-5 | RED | 27 | and — when mesh checks are enabled — the quality metrics. |
| 5-6 | RED | 27 | ONE call does both; there is no separate render tool to call. |

##### `agents/shared/prompt_fragments/generic_constraints.md` — 3 annotations

> ⚠ Shared file. Make this cut in the scoped copy `agents/shared/prompt_fragments/generic_constraints_tool_caller.md`, **not** here.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 6-6 | RED | 29 | only the Planner may change it. |
| 21-22 | RED | 29 | DON'T script the final user-facing reply — route your content to the Orchestrator. |
| 26-27 | RED | 29 | The only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up. |

##### `agents/shared/routing.py` — 2 annotations

> Generated at runtime. This text is not edited in place — it is produced by `routing_instructions()` and is restructured wholesale by §A2.

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 171-171 | RED | 30 | How to decide where to route |
| 322-322 | RED | 30 | the agent that handed you this work — normally |

##### `agents/tool_caller/prompt.md` — 16 annotations

| lines | colour | p. | exact highlighted text |
|---|---|---|---|
| 17-18 | RED | 27 | — you are NOT bound to new_attempt |
| 19-19 | RED | 27 | your routing tools name them. |
| 28-28 | RED | 27 | quoting them in a report — |
| 31-31 | YEL | 27 | to render the blade sections |
| 37-40 | RED | 27 | Re-read whenever you are not CERTAIN that what you remember still matches disk, and ALWAYS when the label reads Parameters file (newly written this cycle): — that marks a freshly written set, normally in a NEW attempt folder, so anything you remember is STALE. |
| 51-51 | RED | 28 | Do this per value, not as a glance — a blanket "they look fine" is not a check. |
| 54-54 | RED | 28 | — your routing tools name the agent to return to — |
| 62-66 | RED | 28 | This check is deliberately redundant: it exists because the agent that wrote these values was checking its own work, and because nothing in the tooling validates ranges. An out-of-range value is not rejected: the FEG backend (the default) silently accepts or clamps it, so the mesh can stop matching parameters.json . |
| 88-91 | RED | 29 | The DC Output Inspector receives no images automatically: this cycle's renders reach it ONLY as the paths you list under Render images: , and it locates the folder they sit in from your Current attempt: line, |
| 91-91 | RED | 29 | which is REQUIRED on every routing call. |
| 94-94 | RED | 29 | — the mesh tool's return text marks each one — |
| 94-94 | RED | 29 | the mesh tool's return text marks each one |
| 100-102 | RED | 29 | Reach for them only to confirm what was already tried — e.g. a hand-off cites "the parameters from attempt N" and you want to see what is on disk. Do not browse attempt after attempt, and do not use them to invent your own retry strategies; that is the Planner's call. |
| 105-105 | RED | 29 | (apply to every agent) |
| 108-108 | RED | 29 | Hard constraints — DC-specific |
| 111-111 | RED | 29 | Hard constraints — tool-specific |

##### No automatic source match — place by hand

A span lands here when it is under ~15 characters, when it covers only a tool's name (meaning “this tool” — the action is on the binding), when it is text generated at runtime by `routing_instructions()`, or when round 1 already removed it. Each is accounted for in the narrative above.

| colour | p. | exact highlighted text |
|---|---|---|
| RED | 27 | batch every expression you need this turn into ONE call. |
| YEL | 27 | list_attempts — numbered summary of every attempt folder and which roles (parameters / mesh / renders / description) each holds. |
| RED | 27 | 4. read_attempt(n, file) — read one file from the n-th attempt (text inline; an image or mesh returns a path to hand on to whoever can load it). |
| RED | 27 | only |
| RED | 27 | (IMPORTANT) |
| RED | 27 | — |
| RED | 28 | (hub, r = 4 mm), |
| RED | 28 | (Mesh quality checks are OFF this session: the render step returns the three views and the mesh's bounding box, but no watertightness / volume / degenerate-face numbers — so there are none to report.) |
| RED | 28 | Three |
| RED | 28 | MUST |
| YEL | 29 | list_attempts |
| RED | 29 | / read_attempt |
| RED | 29 | — generic |
| RED | 29 | (every agent) |
| RED | 29 | (every agent) |
| RED | 29 | Batch into ONE call; a second only when a later expression needs an earlier result. |
| RED | 29 | You are one agent in a decentralised pipeline. The natural flow is: Orchestrator → User Input Inspector → Planner → DC Input Creator → DC Input Inspector → Tool Caller → DC Output Inspector → Orchestrator Your position: Tool Caller. - Your natural next in line is: DC Output Inspector. - Your natural previous in line is: DC Input Inspector. |
| YEL | 30 | If the Orchestrator's instruction in your incoming message told you to continue the pipeline (explicitly or by default, since no instruction to report back means continue), and your own work succeeded, route FORWARD to the next agent. |
| YEL | 30 | next agent. |
| YEL | 30 | If the Orchestrator's instruction told you to report back or to do X and return, route to the Orchestrator once your work is done. If you cannot do your job because the incoming hand-off is ambiguous, missing data, or contains an error the sender can fix, route back to the agent that handed you this work — normally the DC Input Inspector — with a clear clarification request (CLARIFY). If something is fundamentally wrong and no agent in the chain can fix it, route to the Orchestrator (ESCALATE). |
| RED | 30 | — |
| RED | 30 | when mesh + renders report all exist. |
| RED | 30 | Do not loop — ESCALATE when stuck If you find yourself about to call the same tool with the same arguments you already called earlier in this turn, STOP. Calling the same read tool twice on unchanged input, or re-thinking the same decision in a loop, will not give you new information. Instead, ESCALATE to the Orchestrator with a short note describing what is ambiguous or missing and what you would need to proceed. The Orchestrator can then re-dispatch you with new instructions, consult another agent, or ask the user. Never silently loop. |
| RED | 30 | Permission / authorisation issues → Orchestrator (not the previous agent) If a rule in your system prompt blocks an action unless some authorisation is present, READ THE INCOMING HAND-OFF (and any upstream file the hand-off points to, e.g. extracted_inputs.txt) ONCE MORE before escalating. If the hand-off already names an authorisation that plausibly covers the action — even if the wording differs from a template you expected — act on it. Do NOT bounce back to the previous agent in the chain for a ritual re-confirmation of something the hand-off already carries; that is a wasted round-trip. When an authorisation is truly missing or ambiguous, ESCALATE to the Orchestrator. The previous agent in the chain typically CANNOT grant permission — authorisations come from the user (relayed by the Receptionist → Orchestrator), from the Planner (relayed by the Orchestrator), or from the Orchestrator itself. CLARIFY back to the previous agent is appropriate for data / wording / format issues the previous agent can actually fix, NOT for permission questions. |
| RED | 30 | Every response that ends your turn MUST invoke exactly one of the routing tools listed above. The tool's message argument IS the complete hand-off text the recipient will see — there is NO separate audit block to emit. Do NOT write a ---ROUTING--- / --- MESSAGE--- / ---END--- template; that format has been retired. The tool call is the routing decision; its message argument is the hand-off. Write the message argument as free-form prose: no fixed template, no enumerated option menus, no placeholder phrasings. Include everything the recipient genuinely needs (paths the recipient's tools require, context about what changed and why, authorship of any non-user-authored values) and nothing they do not. Your verbose work product stays in your own history and (where applicable) on disk — do not duplicate it inside the message argument. |
| RED | 30 | Keep that reasoning terse (one or two lines is plenty). |
| YEL | 32 | list_attempts |
| RED | 32 | read_attempt |

---

## D. Checks to run before calling this done

1. **Only the intended agents moved.** Assemble all nine prompts before and after
   with `extra_utilities/prompt_pdf/dump.py` and diff `dump.json`. Expect changes
   in DCIC, DCII, TC (content + tools), the DCOI and the four round-1 agents
   (§A only — headings and ROUTING), and **none at all in the Database Handler**.
2. **No unresolved placeholders.** No `$slot`, `{slot}` or `<<MARKER>>` may
   survive in any assembled prompt.
3. **Two new `SCOPED_FRAGMENTS` registrations** (`modelling_notes`,
   `qualitative_examples`) plus `tool_inventory` for the TC. A scoped file whose
   slot is not registered is silently inert — that is the failure mode to test
   for, by asserting the scoped text actually appears in the assembled prompt.
4. **Shared-tree scoped copies can shadow a topology override.** Round 1 hit this:
   a new `<slot>_<agent>.md` in the shared tree displaces
   `agents/5agent/…_5agents.md` for an agent that exists in both. Every scoped
   copy created here is for an agent that also exists in the 5-agent
   topology **except the Tool Caller**, so check DCIC and DCII against
   `agents/5agent/` and add byte-identical pass-through copies where needed.
5. **Every bound tool is described, every described tool is bound.** Especially
   after `new_attempt_parameters`: grep for `write_parameters` and `new_attempt`
   repo-wide, including the dormant 5-/3-agent prompts.
6. **`read_parameters` callers.** It is bound to the DCII and the TC today and to
   nothing else; both lose it. Confirm no prompt still names it.

---

## E. Flagged for your decision

| # | item | where |
|---|---|---|
| 1 | §A4 puts the attempt number on the `Current attempt N:` line. The alternative was the `Parameters file:` line; both name the same attempt, and `Current attempt:` is the label the TC, DCOI and Orchestrator all already share. | §A4 |
| 2 | §A3 asks for `impellerRadius` to be introduced before first use, but not where or in what words. A sentence is proposed where the outer ring is first described. | §A3 |
| 3 | One DCIC span ("(DC Input Inspector),", p. 6) matched `agents/dc_input_inspector/dc_input_inspector.py` — a false anchor from a two-word span. It belongs in the DCIC prompt; place it by eye. | §C1 table |
| 4 | The DCII and DCIC cut the **same 9 spans** from `value_states.md`. Two scoped copies with identical content is the literal reading of the per-agent rule; a single shared edit would be simpler but would also change the DCOI, which reads it and is unreviewed. | §C2.1 |
| 5 | RAG sections remain untouched, per round 1's "RAG will be shortened later on". | — |

---
