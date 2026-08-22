# Prompt reduction — Receptionist / Orchestrator / Planner / UII

**Source of truth:** `7agent_reduced_system_prompts_PDFnotes1_4agents.pdf`
(52 pages, the first 52 of the 113-page `extra_utilities/7agent_reduced_system_prompts.pdf`,
built at commit `4786832`).
**Target system:** `SYSTEM_TOPOLOGY = 7`, `PROMPT_VARIANT = "reduced"`.
**Scope:** the four agents reviewed so far — Receptionist, Orchestrator, Planner,
User Input Inspector. DCIC, DCII, Tool Caller, DCOI and the Database Handler are
**not** in scope and must come out of this work byte-identical.

**Markup key** (the reviewer's own convention):

| colour | count | meaning |
|---|---|---|
| red | 289 spans | delete the highlighted text |
| light yellow | 23 spans | modify / substitute — the adjacent comment says how |
| dark yellow | 3 spans | same as light yellow |
| green | 1 span | move this text (p. 22, Orchestrator) |
| typed comments | 63 | instructions, questions, or the rationale for a nearby highlight |

**How the anchors below were produced.** Every highlight annotation was read out
of the PDF with its colour and its covered words, then matched back to the
repository source by normalising both sides (markdown syntax stripped, all
whitespace removed) and searching. 275 of 316 spans matched a source file
exactly; the remainder are tool-name markers (the highlight covers a tool's
title, meaning "this tool", not "this text") and text generated at runtime by
`reduced7/agents/shared/routing.py`, both placed by hand and called out
explicitly. Line numbers are as of commit `4786832`; a span marked `~` matched
fuzzily and should be eyeballed before cutting.

---

## 0. Decisions already taken (do not re-litigate)

1. **Per-agent scoped copies, not global edits.** Most red cuts land inside
   fragments shared by all nine agents, and the four reviewed agents cut them
   *differently*. Every such cut is therefore made in a **per-agent scoped copy**
   so DCIC / DCII / TC / DCOI / DH keep today's text untouched. See §A1 for the
   mechanism and which slots need registering.
2. **`list_attempts` + `read_attempt` merge into one `read_attempts` tool**, which
   also lists each attempt's file paths (§B1).
3. **`dc_params_list` is a new tool bound to the Planner and the Orchestrator.**
   The Receptionist and the UII keep their inline parameter list (§B2).
4. **Hedged comments are decisions.** "I would remove this tool from the
   receptionist" is recorded as *remove it*.
5. **`ocr_regions` is unbound from the Planner only**; UII / DCII / DCOI keep it,
   and their crop-attachment flags stay at the `False` default.
6. **The canonical pipeline string gains acronyms and the Planner-approval tail**
   (§A3), applied to the Orchestrator's and the Planner's prompts only. The third
   copy — the flow line inside `reduced7/agents/shared/routing.py` — is
   deliberately **left alone** until DCIC/DCII/TC/DCOI are reviewed.

---

## 0.1 ⚠ Which tree to apply this to — READ FIRST

The PDF, and therefore every path and line number below, was built from commit
`4786832` on branch `claude/lucid-chandrasekhar-346c71`, where the reduced
variant still lived in its own two trees (`agents/7agent_reduced/` for the `.md`
overrides, `reduced7/` for the forked code) selected by `PROMPT_VARIANT`.

**That layout no longer exists on the mainline.** `4786832` is an *ancestor* of
`0df0129`, which promoted the reduced prompts to be THE standard: `b94e07b`
deleted `agents/7agent_reduced/`, `929694e` folded `reduced7/agents/shared/routing.py`
into `agents/shared/routing.py`, and `5b0ddb7` removed `PROMPT_VARIANT` entirely.
`main`, `stage-a-web-deploy` and `claude/7agent-reduced-prompt-429b3a` all carry
the promoted layout.

**The good news: the promotion was faithful.** Of the 25 files this spec anchors
into, **24 are byte-identical** across the promotion — so every line number below
still holds. Only `routing.py` changed. Translate the paths:

| path in this spec (at `4786832`) | path on the promoted mainline |
|---|---|
| `agents/7agent_reduced/<agent>/prompt_7agents_reduced.md` | `agents/<agent>/prompt.md` |
| `agents/7agent_reduced/prompt_fragments/X_7agents_reduced.md` | `agents/shared/prompt_fragments/X.md` |
| `agents/7agent_reduced/dc_config/X_7agents_reduced.md` | `DC_prompt_fragments/dc_config/X.md` |
| `agents/7agent_reduced/dc_config/user_input_types/X_7agents_reduced.md` | `DC_prompt_fragments/dc_config/user_input_types/X.md` |
| `agents/7agent_reduced/tools_config/X_7agents_reduced.md` | `DC_prompt_fragments/tools_config/X.md` |
| `reduced7/agents/shared/routing.py` | `agents/shared/routing.py` — **content differs, re-locate by heading** |

**Consequences for the instructions below:**

* **Scoped copies lose the suffix.** `scoped_fragment_path()` builds the name as
  `{stem}_{agent}{suffix}`, and with no `agents/7agent/` directory the lookup
  falls through to the shared folder. So
  `generic_constraints_receptionist_7agents_reduced.md` becomes
  `agents/shared/prompt_fragments/generic_constraints_receptionist.md`, and
  `hard_constraints_tools_planner_7agents_reduced.md` becomes
  `DC_prompt_fragments/tools_config/hard_constraints_tools_planner.md`. The
  mechanism itself (§A1) survived the promotion unchanged — same seven registered
  slots, same naming rule.
* **Drop every `PROMPT_VARIANT` reference.** It no longer exists; assembling for
  verification needs only `SYSTEM_TOPOLOGY = 7`.
* **§A2's routing sections moved.** In the promoted `agents/shared/routing.py`
  (297 lines): `## Routing` at 175, `### How to decide where to route` at 218,
  `### Do not loop — ESCALATE when stuck` at 241, `### Permission / authorisation
  issues` at 251, `### Routing is a tool call — MANDATORY` at 270. The per-agent
  allow-list goes here, and it now affects **every** topology that shares this
  module — so default it to today's full set and reduce only `planner` and
  `user_input_inspector`.
* **The DBa profile key has already been renamed** by `5b0ddb7`. Verified on the
  promoted tree: `profile_key()` returns just the topology (`"7"`), and
  `workflow_settings/database_access.json` holds a single `"7"` profile carrying
  the distribution this spec calls `"7-reduced"`. Read §B5 with that substitution.

If instead you branch from `4786832` and apply the spec as written, everything
below is literal — but you inherit a tree the mainline has since deleted, and
merging it back will be painful. **Applying on the promoted mainline with the
translation above is the recommended route.**

---

## A. Plumbing that must land first

### A1. Register four more slots as scopable

`agents/shared/prompts.py` → `SCOPED_FRAGMENTS`. Today it holds seven slots. A
slot must be registered here before a per-agent copy of its fragment is read at
all; without this, the scoped files created in Part C are inert.

Add:

```python
"pipeline_flow":   ("generic", "pipeline_flow.md"),
"value_states":    ("generic", "value_states.md"),
"dc_structure":    ("dc",      "dc_config/structure.md"),
```

Notes:

* `pipeline_flow` is registered as `pipeline_flow.md` even though the shared file
  is `pipeline_flow_uii_first.md`. `scoped_fragment_path()` only uses the
  registered name to *build* the scoped filename — it never reads the shared
  file — so this yields clean names like
  `pipeline_flow_orchestrator_7agents_reduced.md` and cannot be confused with the
  existing `pipeline_flow_planner_first.md`.
* **Do NOT register `blade_sections_visualizer`.** Its scoped name for the
  Planner would collide with the existing per-agent overlay file
  `agents/7agent_reduced/tools_config/blade_sections_visualizer_planner_7agents_reduced.md`,
  which feeds a *different* slot (`$blade_sections_visualizer_per_agent`). The
  Planner's rewrite folds into that overlay instead (§C3.2).
* Registering a slot costs one `is_file()` check per agent per template build and
  nothing else, so this is safe.

### A2. Per-agent routing sections

`reduced7/agents/shared/routing.py:routing_instructions()` emits a fixed set of
sections for every chain agent. The Planner and the UII cut most of them
(pp. 35, 47), so the builder needs to know which sections an agent gets.

Sections currently emitted (line numbers in that file):

| section | line |
|---|---|
| `## Routing` + natural-flow line + position lines | 78 |
| `### How to decide where to route` | 120 |
| *Available routing tools* (the per-agent `.md` fragment) | — |
| `### Do not loop — ESCALATE when stuck` | 141 |
| `### Permission / authorisation issues → Orchestrator` | ~155 |
| `### Routing is a tool call — MANDATORY` | 170 |

Add an allow-list keyed by agent, defaulting to **all** sections (so the four
unreviewed chain agents are unaffected), with `planner` and
`user_input_inspector` reduced per §C3.4 and §C4.4.

### A3. The canonical pipeline string

New form — acronyms only where one already exists in this codebase, and the tail
routed through the Planner as final approver:

```
user → Receptionist → Orchestrator → User Input Inspector (UII) → Planner →
DC Input Creator (DCIC) → <<DCII_ONLY>>DC Input Inspector (DCII) → <</DCII_ONLY>>Tool Caller (TC) →
DC Output Inspector (DCOI) → Orchestrator → Planner → Orchestrator → Receptionist → user
```

**Keep the `<<DCII_ONLY>>` / `<</DCII_ONLY>>` markers exactly where they are** —
they are what lets the DC Input Inspector be switched off. Applies to the two
scoped `pipeline_flow` copies created in §C2.1 and §C3.1.

---

## B. Tool-layer changes

### B1. `list_attempts` + `read_attempt` → `read_attempts`

Source: `agents/shared/attempts_tool.py`. Comments on pp. 24, 28, 37, 49.

Replace both tools with one:

```
read_attempts(attempt_numbers: list[int] | None = None) -> str
```

* **No argument** — behave as `list_attempts` does today (numbered summary of
  every attempt folder + the `Has:` line), **and additionally print each
  attempt's `description.txt` content when present.**
* **With attempt numbers** — print the same per-attempt summary for only those
  attempts, and for each also print `description.txt` **and the full
  `parameters.json`** when present.
* **In both modes**, list each attempt's file paths — every `render_*.png`
  (including `render_blade_sections.png`) and `propeller_mesh.obj` — as absolute
  paths. This is what replaces `read_attempt`'s file-path behaviour, which the
  Receptionist needs to drive `visualize_3d_model`.
* Attempt numbers only; no paths are ever passed in.
* Delete `read_attempt` and `list_attempts` and every import of them.

**Callers to update:** `agents/receptionist/receptionist.py`,
`agents/orchestrator/orchestrator.py`, `agents/planner/planner.py`,
`agents/user_input_inspector/user_input_inspector.py`, plus the four unreviewed
chain agents which import them today — those four keep an attempts tool, so point
them at `read_attempts` rather than dropping it.

**Prompt text that names the old tools** must be updated wherever it survives the
cuts; the cut tables below flag each occurrence.

### B2. New tool — `dc_params_list`

Comments on pp. 30, 31. Bound to the **Planner** and the **Orchestrator** only.

```
dc_params_list() -> str
```

Returns the same text the `$parameter_list` fragment renders today
(`DC_prompt_fragments/dc_config/parameters.md`) — the 16 parameters with units and
ranges, plus the maxPos/thickness note. No arguments.

Rationale, in the reviewer's words: *"make this set of parameters something
retrieved by the planner if it explicitly CALLS FOR IT … this way, it won't
always be when not required."* The block is ~1 900 characters in every prompt
that carries it.

The Receptionist and the UII **keep** their inline `$parameter_list` block and do
**not** get this tool.

### B3. Planner reads user inputs, not just queries

Comment p. 36. Unbind `read_user_queries` from the Planner and bind the UII's
existing `read_user_inputs(path)` instead — the whole inputs directory (every
text/JSON file concatenated, including the image notes, plus the list of image
paths). `read_extracted_inputs` stays.

`read_user_queries` is defined in `agents/planner/planner.py` and used nowhere
else; delete it with the binding.

### B4. Per-agent bind lists — before → after

| agent | remove | add | keep |
|---|---|---|---|
| **Receptionist** | `read_input_text` (p. 13), `read_attempt` → merged | `read_attempts` | `read_agent_history`, `call_orchestrator`, `calculate`, `visualize_3d_model`, `propose_attempt` |
| **Orchestrator** | `calculate` (p. 24), `read_attempt` (p. 24), `new_attempt` (p. 25) | `read_attempts`, `dc_params_list` | all 7 `call_*` routing tools, `read_agent_history` |
| **Planner** | `read_user_queries` (p. 36), `read_attempt` (p. 37), `list_input_files` / `read_input_text` / `read_image_notes` (p. 38), `view_images` (p. 39), `ocr_regions` (p. 39) | `read_user_inputs`, `read_attempts`, `dc_params_list` | `read_extracted_inputs`, `calculate`, `read_agent_history`, 3 × `call_*`, `database_search` (RAG) |
| **UII** | `list_attempts` / `read_attempt` (p. 49), `list_input_files` / `read_input_text` / `read_image_notes` (p. 50) | — | `read_user_inputs`, `write_extraction`, `calculate`, `view_images`, `ocr_regions`, `call_planner`, `call_orchestrator`, `database_search` + `retrieve_user_inputs` (RAG) |

The UII's justification, verbatim: *"These three tools are useless if the UII
already has a tool that reads all the text user inputs at once, giving it also
the paths to the images … nothing else is needed for the UII."*

Mechanically: the Planner and the UII should no longer call
`build_user_inputs_tools(...)` for the text-file tools. The Planner ends with no
image tools at all — pass `include_image_tools=False` **and** drop
`list_input_files` / `read_input_text`, i.e. stop calling the builder for the
Planner entirely and bind `read_user_inputs` directly. The UII keeps
`view_images` + `ocr_regions` but loses the three text-file tools.

### B5. Config knock-ons

* `workflow_settings/ocr_access.json` / `ocr_access.DEFAULT_AGENTS` still list
  `planner`. With `view_images` and `ocr_regions` unbound, that flag becomes
  inert and its Workflow-Settings toggle a no-op. Remove `planner` from
  `DEFAULT_AGENTS` and from the JSON, or leave it and accept a dead switch —
  **decide explicitly, don't leave it by accident.**
* `workflow_settings/ocr_region_crops_access.DEFAULT_AGENTS` correctly lists only
  `user_input_inspector`, `dc_input_inspector`, `dc_output_inspector`. Leave it,
  and leave `_DEFAULT_VALUE = False`.
* `database_access.json` profile `"7-reduced"` is unchanged by this work.

---

## C. Per-agent changes

Each agent has four parts: the scoped copies to create, the structural
moves/rewrites the typed comments ask for, the tool changes, and then the
generated table of every highlighted span with its source anchor.

---

### C1. Receptionist

PDF pp. 5–14. Prompt: `agents/7agent_reduced/receptionist/prompt_7agents_reduced.md`.

#### C1.1 Scoped copies to create

| new file | copy of | why |
|---|---|---|
| `agents/7agent_reduced/prompt_fragments/generic_constraints_receptionist_7agents_reduced.md` | `generic_constraints_7agents_reduced.md` | 3 spans cut here that the other agents keep. Reviewer's rationale (p. 11): *"many of these don'ts are not useful for the receptionist"* |
| `agents/7agent_reduced/tools_config/hard_constraints_tools_receptionist_7agents_reduced.md` | `hard_constraints_tools_7agents_reduced.md` | 1 span cut |

`$output_file_locations`, `$visualize_3d_model_tool` and `$propose_attempt_tool`
resolve to fragments **only the Receptionist consumes** — edit those files
directly, no scoped copy needed. Confirmed by slot→consumer analysis.

#### C1.2 Edits the comments ask for

1. **p. 9 — "Render images: missing the blade sections renders."**
   In `DC_prompt_fragments/dc_config/output_file_locations.md`, the *Render
   images* bullet lists only `render_isometric.png`, `render_top.png`,
   `render_side.png`. The blade-sections tool also writes into the attempt folder
   — `render_blade_sections.png`, or `render_blade_sections_grid.png` in grid mode
   (`tools/render_blade_sections/render_blade_sections.py:112`). Add them, naming
   `render_blade_sections` as the writer.
2. **p. 5 — "repetition."** This is the *rationale* for the red cut of the
   `visualize_3d_model` mechanics paragraph, not a separate instruction: the
   paragraph restates what the tool's own description already says. No extra
   action — make the cut and move on.
3. **p. 11 — "many of these don'ts are not useful for the receptionist."**
   Rationale for the three red spans in the DON'Ts list. The red spans are the
   operative instruction; do not cut further on the strength of the comment.
4. **Blade-sections awareness — delete for this agent.** The whole
   `$blade_sections_visualizer` section is red (p. 11). Remove lines 386–390 of
   the prompt, i.e. the entire `<<BSV_ON>>…<</BSV_ON>><<BSV_OFF>>…<</BSV_OFF>>`
   region. ⚠ **Flagged:** that also removes the `<<BSV_OFF>>` branch, which the
   PDF could not show (it renders only when the visualizer is disabled). Deleting
   both branches is the coherent reading — confirm if you disagree.

#### C1.3 Tool changes

* Unbind `read_input_text` (p. 13 — the comment sits beside `read_input_text`,
  which is red; `visualize_3d_model` immediately below it is **not** highlighted
  and stays).
* `list_attempts` / `read_attempt` → `read_attempts` (§B1). The Receptionist is
  the caller that needs `read_attempts` to return file paths, for
  `visualize_3d_model`.
* Prompt text naming `read_attempt(n, "parameters.json")` and the
  `read_attempt(n, "render_*.png")` procedure must be rewritten to the new tool.

#### C1.4 Every highlighted span, with its source anchor

Generated directly from the PDF annotations. `lines` are 1-based in the named file at commit `4786832`; `p.` is the PDF page; `~` marks a fuzzy match to verify by eye. `RED` = delete the text. `YEL` / `DKYEL` = modify per the comment recorded above. `GREEN` = move. Adjacent highlights of the same colour are merged into one row, so a row can cover several annotations.

##### `DC_prompt_fragments/dc_config/output_file_locations.md` — 4 spans

| lines | colour | p. | text |
|---|---|---|---|
| 2-6 | RED | 9 | The folder is created via new_attempt by the DC Input Creator (or, only as a special-case fallback, the Orchestrator); downstream agents target the same folder by reading the Current attempt: label in their hand- off. |
| 9-12 | RED | 9 | (written by the DC Input Creator's write_parameters tool). (written by the Tool Caller's generate_and_render_propeller tool). |
| 14-17 | RED | 9 | (written by the same generate_and_render_propeller tool's built-in render step). written at folder creation time by whichever agent invoked new_attempt . |
| 19-27 | RED | 9 | An attempt folder MAY be partial: it might carry only parameters.json (a parameter set was authored but no mesh ever generated), only parameters + mes … arameters give identical geometry), so re-running it on an attempt that already has a mesh/renders needs no new attempt. |

##### `DC_prompt_fragments/tools_config/blade_sections_visualizer.md` — 1 span

> The whole fragment is dropped for this agent — delete the `$slot` line and its heading from the prompt rather than editing this file.

| lines | colour | p. | text |
|---|---|---|---|
| 1-12 | RED | 11 | Blade-sections visualizer The system can render JUST the blade cross-sections — a flat image showing the three blade sections (Inner, Middle, Outer) s …  section details), the sections can be rendered and refined cheaply on their own, and can even be the final deliverable. |

##### `DC_prompt_fragments/tools_config/propose_attempt.md` — 3 spans

| lines | colour | p. | text |
|---|---|---|---|
| 5-10 | RED | 5 | what the user sees (non-FIXED rows move to the proposed value and every row, FIXED included, gets a "PROPOSED VALUE: X" label), and that FIXED rows ar … nt them: the user is shown the dict literally, so a value you did not confirm for a specific named attempt is forbidden. |
| 26-27 | RED | 6 | — the mechanism is STICKY: it must keep showing the last endorsed proposal until a new one arrives. |
| 33-34 | RED | 6 | return value says nothing about design quality: the no-fabrication rule holds — never describe or judge an attempt from it. |

##### `DC_prompt_fragments/tools_config/visualize_3d_model.md` — 3 spans

| lines | colour | p. | text |
|---|---|---|---|
| 3-10 | RED | 5 | visualize_3d_model(obj_path) 's mechanics — that it shows an attempt's propeller_mesh.obj in the web viewer, its args, and that it tells you NOTHING a … / "Show to user:", or a legacy "DC parameters written this cycle" / "Confirmed render files produced this cycle" block). |
| 14-17 | RED | 5 | — in practice while composing a Situation B reply that carries a finished-design block: read_attempt the designated attempt for its real paths, then visualize_3d_model its propeller_mesh.obj . * |
| 22-22 | RED | 5 | (see the HARD rule on inventing observations). |

##### `agents/7agent_reduced/prompt_fragments/generic_constraints_7agents_reduced.md` — 3 spans

> ⚠ Shared file. Make these cuts in the scoped copy `agents/7agent_reduced/prompt_fragments/generic_constraints_receptionist_7agents_reduced.md`, **not** here.

| lines | colour | p. | text |
|---|---|---|---|
| 16-18 | RED | 11 | If your bound tools can't do it, ESCALATE — hand the problem to whoever can resolve it. |
| 20-20 | RED | 11 | — ESCALATE instead. |
| 23-27 | RED | 11 | DON'T communicate in plain prose. The ONLY channel to another agent is a routing tool call; any text you emit without one is silently discarded and th … r work. The only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up. |

##### `agents/7agent_reduced/receptionist/prompt_7agents_reduced.md` — 23 spans

| lines | colour | p. | text |
|---|---|---|---|
| 25-26 | RED | 5 | (the UII inspects the image itself) |
| 43-44 | RED | 6 | You have exactly two ways to respond, and you choose by reasoning about what the user actually wants. |
| 62-70 | RED | 6 | Map each plain value to a parameter from "Parameter Ranges" below (normalising the unit — e.g. "3/10ths" → 3 in tenths). If a name is NOT in the table …  to restate. (Plausible-looking names such as hub_radius, hub_height, fillet_radius or tip_clearance do NOT exist here.) |
| 75-77 | RED | 6 | Never state in a forward summary that values are "within range", since you did not check. And never silently clip, round, or redistribute a user's value: substituting values is not your job. |
| 90-98 | RED | 6 | Usually worth relaying when present: the user's stated intent, constraints, strategy preferences ("cap at 2 retries"), use-cases / tolerances, and — i …  value). Ground every sentence in what the user literally said; leave out anything redundant, off-topic, or unsupported. |
| 105-107 | RED | 6 | Downstream agents never see the user's original wording; what you write IS what they see, and a softened directive often gets ignored. |
| 126-128 | RED | 7 | (typically via Situation B, where the technical summary asked the user for an authorisation, a clarification, or a choice between options), |
| 133-135 | RED | 7 | The pipeline is actively waiting on that answer; a direct reply ("Understood — I will keep X") strands it and leaves the open request unresolved. |
| 141-151 | RED | 7 | The ONLY exceptions are: * The user's message is plainly not an answer at all — pure confusion ("huh?", "what?", "are you there?", "what do you want m … l question is still open, and if it means forwarding, say in your summary that the earlier question is still unanswered. |
| 156-157 | RED | 7 | the quality-check report, |
| 182-183 | RED | 7 | it routes through the Planner / DCOI for a grounded answer. |
| 190-192 | RED | 7 | If the user later doubts it or asks the chain to verify, that is a Situation-A forward — the chain re-examines, never you. |
| 196-196 | RED | 7 | no canonical phrases that force one branch over the other. |
| 198-199 | RED | 7 | Never invent design intent for a user message that doesn't actually carry any — do not manufacture a forward summary. |
| 266-267 | RED | 8 | If the user asks for something on the CANNOT list, tell them plainly that this system does not do it, and offer only CAN-list alternatives. |
| 281-284 | RED | 9 | and (optionally) read_attempt(n, "render_isometric.png") / render_top.png / render_side.png — bare filenames, never a wildcard — to confirm render paths. |
| 290-291 | RED | 9 | Its tool block above carries the endorsing and hedging wordings and the manual trigger. |
| 296-297 | RED | 10 | — but do NOT propose_attempt (the recommendation has not changed). |
| 303-305 | RED | 10 | Do not quietly present the delivered numbers as if they were the requested ones. |
| 313-314 | RED | 10 | ("matched the section shapes as closely as the NACA model allows; the drawn leading edge is sharper than the model can reach") |
| 317-319 | RED | 10 | Both notes must come FROM the hand-off — never work out a mismatch reason or a fidelity claim yourself; if the hand-off carries none, make none. |
| 337-340 | RED | 10 | The User Input Inspector extracts the usable information from the user's text + images into extracted_inputs.txt , and the relevant part comes back to the user via you, WITHOUT running the rest of the design- generation chain. |
| 346-348 | RED | 10 | (The UII extracts everything relevant — including items with no DC parameter mapping; downstream agents filter to the configurable subset, so an extraction-only ask can yield more than the final parameter set.) |

##### `agents/7agent_reduced/tools_config/hard_constraints_tools_7agents_reduced.md` — 1 span

> ⚠ Shared file. Make these cuts in the scoped copy `agents/7agent_reduced/tools_config/hard_constraints_tools_receptionist_7agents_reduced.md`, **not** here.

| lines | colour | p. | text |
|---|---|---|---|
| 6-7 | RED | 11 | Batch into ONE call; a second only when a later expression needs an earlier result. |

##### `agents/shared/prompt_fragments/routing_receptionist.md` — 1 span

| lines | colour | p. | text |
|---|---|---|---|
| 9-9 | RED | 10 | which decides the next step. |

##### Spans generated at runtime, or covering a tool name

These cover a tool's title (meaning “this tool” — the action is on the binding, not on text) or text emitted by `reduced7/agents/shared/routing.py`. Each is accounted for in the narrative above.

- [RED] p.8 — HARD — permission-to-vary questions name only user-locked values. When the system asks whether numeric values may be varied, the ONLY values in question are the ones the user literally provided — typi

##### Short substitutions (under ~15 characters)

Too short to locate reliably by text search — every one is spelled out in the narrative above, with its replacement.

- [RED] p.5 — that
- [RED] p.6 — Its
- [RED] p.13 — read_input_text

---

### C2. Orchestrator

PDF pp. 15–25. Prompt: `agents/7agent_reduced/orchestrator/prompt_7agents_reduced.md`.

#### C2.1 Scoped copies to create

| new file | copy of | why |
|---|---|---|
| `agents/7agent_reduced/prompt_fragments/pipeline_flow_orchestrator_7agents_reduced.md` | `agents/shared/prompt_fragments/pipeline_flow_uii_first.md` | new pipeline string (§A3); the Planner cuts this fragment differently |
| `agents/7agent_reduced/prompt_fragments/generic_constraints_orchestrator_7agents_reduced.md` | `generic_constraints_7agents_reduced.md` | 2 spans cut |
| `agents/7agent_reduced/tools_config/hard_constraints_tools_orchestrator_7agents_reduced.md` | `hard_constraints_tools_7agents_reduced.md` | 1 span cut, **plus** the whole `calculate` bullet (§C2.3) |

`$tool_caller_capabilities`, `$agent_tools_overview` and `$routing_hub`
(→ `routing_orchestrator.md`) are consumed by the Orchestrator alone — edit
directly.

#### C2.2 Whole-slot removals — delete the `$slot` line **and its heading**

No scoped copy is needed when an agent drops a fragment entirely.

| prompt lines | what goes |
|---|---|
| 315–324 | `### Do NOT seed follow-ups the system cannot deliver` + its prose + `$capabilities_can` + `$capabilities_cannot` (red, pp. 18–19) |
| 422–428 | `## The $parameter_count Design Parameters …` + `$parameter_list` (red, p. 20) — the Orchestrator gets `dc_params_list` instead (§B2) |
| 480–481 | `## Hard constraints — DC-specific` + `$hard_constraints_dc` (red, p. 21) |
| 510–513 | the whole `<<BSV_ON>>…<<BSV_OFF>>` blade-sections region (red, p. 22) |

#### C2.3 Edits the comments ask for

1. **p. 15 — acronyms + Planner tail.** Apply §A3's string in the new scoped
   `pipeline_flow_orchestrator` copy. The reviewer wrote the tail explicitly:
   *"Planner --> orchestrator --> receptionist --> user"*.
2. **p. 17 — `"inputs", not "sketch"`.** In the precision-refine-loop section,
   *"runs a TIGHT refine loop against the user's sketch"* → *"against the user's
   inputs"*.
3. **p. 20 — "tool caller description missing the tool to generate blades
   renders!"** `DC_prompt_fragments/tools_config/tool_caller_capabilities.md`
   says the Tool Caller calls *"exactly two design-tool actions and nothing
   else"* — `generate_and_render_propeller` and `calculate`. It also holds
   `render_blade_sections`. Rewrite the entry to name all three and drop the
   "exactly two … and nothing else" framing.
4. **p. 22 — "and also blade sections renders!"** In
   `agents/shared/prompt_fragments/routing_orchestrator.md`, the
   `call_tool_caller(message)` line reads *"(re-)run mesh generation and rendering
   for an existing attempt"*. Add the blade-sections render as an alternative
   the Tool Caller can be asked for.
5. **p. 22 — the green span, the only "move" in the whole markup.** Take
   *"the normal end of a cycle is `call_receptionist`, which composes the
   user-facing wording."* and put it at the **start** of the `## Output format`
   paragraph (prompt line 491), before *"For you a response with NO tool call
   does not halt silently…"*. Remove it from its current position at the end.
6. **`calculate` bullet must go too.** Removing the `calculate` tool (§B4) makes
   the *"DO route EVERY arithmetic operation through the `calculate` tool"* rule
   in `hard_constraints_tools` a reference to a tool the Orchestrator no longer
   holds. Cut that bullet in the Orchestrator's scoped copy.
   ⚠ **Flagged:** a fifth comment reading *"I would remove this tool entirely from
   the orchestrator"* sits at the top of p. 22 under *Hard constraints —
   tool-specific*, with no tool card next to it. It plausibly refers either to
   this `calculate` bullet or to the red `new_attempt` paragraph lower on the same
   page. Both readings are already covered by cuts recorded here, so nothing is
   lost either way — but say which you meant if it matters.

#### C2.4 Tool changes

Remove `calculate` (p. 24), `read_attempt` (p. 24), `new_attempt` (p. 25).
`list_attempts` → `read_attempts` (p. 24: *"Tool modified. See the planner's
tools for a description"*). Add `dc_params_list`. `read_agent_history` is
unhighlighted and stays. All seven `call_*` routing tools stay.

**Decided — `new_attempt` goes, and the fallback goes with it.** It exists on the
Orchestrator today as the documented fallback for when the DCIC cannot open its
own attempt; the owner has confirmed it is not wanted. The DCIC becomes the sole
creator of attempt folders, with no backstop. The matching prompt prose is
already red (p. 22), so nothing further is needed — but when removing the
binding, also strip any surviving "only as a special-case fallback" wording
(it appears in `output_file_locations.md` and in the Planner's attempt-tools
section, both already covered by red spans).

#### C2.5 Every highlighted span, with its source anchor

Generated directly from the PDF annotations. `lines` are 1-based in the named file at commit `4786832`; `p.` is the PDF page; `~` marks a fuzzy match to verify by eye. `RED` = delete the text. `YEL` / `DKYEL` = modify per the comment recorded above. `GREEN` = move. Adjacent highlights of the same colour are merged into one row, so a row can cover several annotations.

##### `DC_prompt_fragments/tools_config/blade_sections_visualizer.md` — 1 span

> The whole fragment is dropped for this agent — delete the `$slot` line and its heading from the prompt rather than editing this file.

| lines | colour | p. | text |
|---|---|---|---|
| 1-12 | RED | 22 | Blade-sections visualizer The system can render JUST the blade cross-sections — a flat image showing the three blade sections (Inner, Middle, Outer) s …  section details), the sections can be rendered and refined cheaply on their own, and can even be the final deliverable. |

##### `DC_prompt_fragments/tools_config/tool_caller_capabilities.md` — 3 spans

| lines | colour | p. | text |
|---|---|---|---|
| 1-2 | RED | 20 | and nothing else: |
| 5-10 | RED | 20 | returns the mesh path and the three render paths) (arithmetic only). It REUSES an existing propeller_mesh.obj in place (mesh + parameters are append-o … exist (identical parameters give identical geometry), so re-running it on an already-built attempt needs no new attempt. |
| 13-14 | RED | 20 | — only the attempt folder it was given. |

##### `agents/7agent_reduced/dc_config/hard_constraints_dc_7agents_reduced.md` — 1 span

> The whole fragment is dropped for this agent — delete the `$slot` line and its heading from the prompt rather than editing this file.

| lines | colour | p. | text |
|---|---|---|---|
| 2-6 ~ | RED | 21 | Hard constraints — DC-specific Domain hard rules (every agent) The 16 named parameters are the ONLY design levers and there is no mesh-editing capabil … th. Reject invented parameters (hub_radius, fillet_radius, tip_clearance, any "supplemental" value) — they do not exist. |

##### `agents/7agent_reduced/orchestrator/prompt_7agents_reduced.md` — 43 spans

| lines | colour | p. | text |
|---|---|---|---|
| 22-27 | RED | 15 | When deciding the next agent, glance at what the previous turn actually produced, not just who was called. An ESCALATE back to you usually means the a … makes sense to re-route to that same agent with the missing piece, rather than continuing forward as if it had finished. |
| 47-48 | RED | 15 | and on the first turn of a session it is not there yet. Do not paste file content; the UII reads the files itself. |
| 50-53 | RED | 15 | "Meaningful" is judged by whether the content plausibly changes how a downstream agent would act. New parameter values, new constraints, new goals, a new permission to vary a locked value, a new strategy cap — all meaningful. |
| 70-72 ~ | RED | 16 | The UII extracts; the Planner then recognises the extraction-only ask, does NOT start a design generation, and returns the answer as a direct reply. You relay that answer to the user via the Receptionist. |
| 77-77 | RED | 16 | those exist to generate geometry, which is not what was asked. |
| 88-89 | RED | 16 | There is no fixed template and no menu of allowed phrasings. |
| 93-96 | RED | 16 | Lose no useful context. When the Planner needs to see the Receptionist's summary to understand the situation, include the relevant parts of it in your own words (or quote it). |
| 99-100 | RED | 16 | It reads the user's query, annotations, and agent histories and decides autonomously. |
| 104-104 | RED | 16 | (typically the DCOI on ESCALATE) |
| 107-108 | RED | 16 | This is a judgement call; if nothing actionable was said, invent nothing. |
| 111-114 | RED | 16 | If the Planner directed a parameter change (a directive of the form "increase <param X> qualitatively" or "reduce <param Y>"), communicate that directive in prose to the DC Input Creator so downstream agents understand where the change originated. |
| 121-125 | RED | 16 | everyone else works in the folder named in its hand-off. and the DCIC opens the attempt itself when it sees no Current attempt: in its hand-off — so you do NOT pre-open one for a normal new generation. |
| 133-139 | RED | 16 | give the DCIC one ONLY when you pre-opened an empty folder as the fallback, because a folder that already holds a parameters.json is closed and the DC …  Current attempt: to the Tool Caller or the DC Output Inspector — do NOT open a new one, and do NOT send it to the DCIC. |
| 157-160 | RED | 17 | Concretely: if the user wrote "the agents MUST use past experience from the database", your hand-off should say "The user has MANDATED that you use past experience from the database — this is a HARD directive, not optional." |
| 164-165 | RED | 17 | agents downstream cannot read the user's original message; they only see what you write. |
| 176-177 | RED | 17 | (you are resuming the chain to try a different parameter direction), |
| 183-188 ~ | RED | 17 | (to the DCIC or Planner, as appropriate) — quote or paraphrase the user's exact scope. This includes the user SUBORDINATING a provided value to a goal … accept either (i) an authorisation named in the hand-off OR (ii) one recorded in the extraction's DESIGN INTENT section. |
| 205-205 | RED | 17 | differently from a normal cycle, |
| 211-217 | RED | 17 | — the DCIC opens a fresh attempt for the adjusted params itself (each round is a new attempt, which also gives the DCOI a prior render to measure prog … DCOI loop turning. The standing-directive block rides through verbatim (re-stamped automatically if any agent drops it). |
| 221-223 | RED | 17 | A real blocker (ESCALATE) — no images, a locked-value conflict, or a failure no tight-loop step can fix → route to the Planner for a recovery plan, as usual. |
| 225-226 | RED | 17 | You never originate the shape feedback or the parameter moves — you relay the DCOI's prose to the DCIC, which owns translating it into shape-param changes. |
| 230-231 | RED | 17 | (DC Output Inspector returned its verdict, or you reach any point where the cycle is "done"), |
| 236-236 | RED | 15 | Receptionist → user |
| 238-242 | RED | 17 | This applies to EVERY completed cycle: single-attempt, multi-attempt ("give me 3 designs and pick the best"), and recovery flows that eventually reached a DCOI verdict. Even when DCOI cleanly approves a single attempt, the Planner is the one who authorises the message sent to the user. |
| 244-267 | RED | 18 | What you send to the Planner at end-of-cycle: * A factual summary of WHAT was produced this cycle — every attempt folder (number + absolute path per t … mpt to surface (e.g. the user asked a question). Same path as the "When the Planner returns a direct answer" rule below. |
| 271-275 ~ | RED | 18 | — DCIC → DCII → Tool Caller → DCOI runs as one block, with no check-in between agents. (its Role 1 reply to a new user message) — re-routing would be circular. See "When the Planner returns a direct answer" below. |
| 277-280 | RED | 18 | Once the Planner has approved, call call_receptionist with the brief technical summary it returned. The Receptionist composes the user-facing wording — do not write the final user message yourself; the dispatcher delivers its composed text and the cycle ends. |
| 284-285 | RED | 18 | then pulls each attempt's details itself with its read_attempt / list_attempts tools. |
| 287-288 | RED | 18 | on their own lines, |
| 291-294 | RED | 18 | (which the 3D viewer takes), never a slug alone — plus an explicit statement of which attempt(s) the Receptionist should show the user. (keep the labelled lines; the surrounding prose is yours): |
| 302-313 | RED | 18 | Rules: * Single-design cycle: still list the one attempt and set "Show to user" to it. * Transcribe the Planner's pick and its one-line reason verbati … ssed to the Planner, which factored it in. * Never omit an attempt whose artefacts you observed being produced this run. |
| 355-362 | RED | 19 | Recognise Planner actionable instructions Every incoming message is prefixed with [Incoming from: <sender>] . Read that header FIRST. When the sender  … le plan. Your job is to forward to X with the Planner's direction preserved, not to re-pose the question to the Planner. |
| 364-366 | RED | 19 | The ping-pong pattern "Orchestrator → Planner → Orchestrator → Planner → …" with no new evidence between hops is a coordination bug. |
| 368-371 | RED | 19 | If not, forward to the named agent instead. Consult the Planner again only when (a) new evidence has arrived since the last Planner turn (e.g. a fresh DCOI verdict the Planner hasn't seen), and (b) the current instruction is genuinely stale against that evidence. |
| 376-382 | RED | 19 | Never attribute a Planner directive to the user, and label sources correctly. A sentence under [Incoming from: Planner] is the Planner speaking, even  … uests …"; the only sentences attributable to the user are ones the user literally said (as relayed by the Receptionist). |
| 388-394 | RED | 19 | (rightly) so the system — not the Receptionist's imagination — produces the answer. it has read_agent_history and can inspect the DC Output Inspector' … eport, then return a grounded answer for you to pass to the Receptionist. Never compose the answer yourself from memory. |
| 403-404 | RED | 19 | It names an attempt's slug + intent but cannot open the folder itself. |
| 416-417 | RED | 20 | Loads images via its own view_images tool (given paths in the Tool Caller's message). |
| 461-462 | RED | 21 | Design content comes from the Planner (qualitative), the user (quantitative), or other agents' outputs. |
| 468-475 | RED | 21 | Anti-Hallucination Rules 1. Do not propose external scripts, infrastructure control, or any "if supported" capability — the roster above is the whole  … failure falls outside the design workflow entirely (nothing the Planner can re-plan), ask the user via the Receptionist. |
| 492-493 | RED | 22 | You may write a short reasoning line above your tool call, but keep it terse. |
| 496-496 | RED | 22 | not a way to answer: |
| 496-497 | GREEN | 22 | the normal end of a cycle is call_receptionist , which composes the user-facing wording. |

##### `agents/7agent_reduced/prompt_fragments/generic_constraints_7agents_reduced.md` — 2 spans

> ⚠ Shared file. Make these cuts in the scoped copy `agents/7agent_reduced/prompt_fragments/generic_constraints_orchestrator_7agents_reduced.md`, **not** here.

| lines | colour | p. | text |
|---|---|---|---|
| 16-20 | RED | 21 | If your bound tools can't do it, ESCALATE — hand the problem to whoever can resolve it. DON'T repeat a tool call with the same arguments, and DON'T retry a failing step blindly — ESCALATE instead. |
| 23-27 | RED | 21 | DON'T communicate in plain prose. The ONLY channel to another agent is a routing tool call; any text you emit without one is silently discarded and th … r work. The only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up. |

##### `agents/7agent_reduced/tools_config/agent_tools_overview_7agents_reduced.md` — 1 span

| lines | colour | p. | text |
|---|---|---|---|
| 1-4 ~ | RED | 20 | Tool reach worth naming in a hand-off Beyond the roster above: the DC Output Inspector's view_images is not limited to the renders just produced — it  … rs. When progress across cycles is the question, name those earlier render paths in the hand-off alongside the new ones. |

##### `agents/7agent_reduced/tools_config/hard_constraints_tools_7agents_reduced.md` — 1 span

> ⚠ Shared file. Make these cuts in the scoped copy `agents/7agent_reduced/tools_config/hard_constraints_tools_orchestrator_7agents_reduced.md`, **not** here.

| lines | colour | p. | text |
|---|---|---|---|
| 6-7 | RED | 22 | Batch into ONE call; a second only when a later expression needs an earlier result. |

##### `agents/shared/prompt_fragments/pipeline_flow_uii_first.md` — 1 span

> ⚠ Shared file. Make these cuts in the scoped copy `agents/7agent_reduced/prompt_fragments/pipeline_flow_orchestrator_7agents_reduced.md`, **not** here.

| lines | colour | p. | text |
|---|---|---|---|
| 15-15 | RED | 15 | In this configuration |

##### `agents/shared/prompt_fragments/routing_orchestrator.md` — 2 spans

| lines | colour | p. | text |
|---|---|---|---|
| 22-24 | RED | 22 | (the dispatcher delivers their eventual report back to you in your next turn) |
| 26-29 | RED | 22 | You also have new_attempt(slug, description) to allocate a fresh attempt folder, but ONLY as a special-case fallback for when the DCIC cannot open its own attempt (it blocks, loops, or errors on creation). Normally the DCIC opens the attempt itself — do not pre- open one. |

##### Spans generated at runtime, or covering a tool name

These cover a tool's title (meaning “this tool” — the action is on the binding, not on text) or text emitted by `reduced7/agents/shared/routing.py`. Each is accounted for in the narrative above.

- [RED] p.16 — If you are unsure of a path, do NOT guess — route through the DCIC, which emits the labels itself. When the chain flows DCIC → (DCII →) Tool Caller naturally, the upstream agent supplies the labels; t
- [RED] p.18 — Do NOT seed follow-ups the system cannot deliver Your technical summary must not propose or hint at capabilities this system does not have. This system can ONLY do what is on the CAN list: Generate a 
- [RED] p.19 — Do NOT write lines like "if the user wants performance estimates …", "ask about material or tolerances …", "offer higher-resolution renders …" — those are hallucinated capabilities and the Receptionis
- [RED] p.20 — The 16 Design Parameters — the ONLY parameters that exist Every design decision MUST be expressed as one or more of these names (exact spelling). If any agent names a parameter outside this list, it i
- [RED] p.22 — clearly labelled
- [RED] p.22 — it is for your own situational awareness.

##### Short substitutions (under ~15 characters)

Too short to locate reliably by text search — every one is spelled out in the narrative above, with its replacement.

- [RED] p.16 — by role,
- [RED] p.16 — therefore
- [RED] p.17 — sketch
- [RED] p.18 — produced (or
- [RED] p.20 — exactly two
- [RED] p.20 — three
- [RED] p.22 — (ENABLED)
- [RED] p.24 — calculate
- [RED] p.24 — list_attempts
- [RED] p.24 — read_attempt
- [RED] p.25 — new_attempt

---

### C3. Planner

PDF pp. 26–40. Prompt: `agents/7agent_reduced/planner/prompt_7agents_reduced.md`.
The heaviest agent: 133 spans.

#### C3.1 Scoped copies to create

| new file | copy of | why |
|---|---|---|
| `agents/7agent_reduced/prompt_fragments/pipeline_flow_planner_7agents_reduced.md` | `pipeline_flow_uii_first.md` | new string + 2 paragraphs cut that the Orchestrator keeps |
| `agents/7agent_reduced/prompt_fragments/available_agents_planner_7agents_reduced.md` | `available_agents.md` | Tool Caller entry rewritten; also used by the DH, which must not change |
| `agents/7agent_reduced/prompt_fragments/value_states_planner_7agents_reduced.md` | `value_states.md` | 4 spans cut; also used by DCIC/DCII/DCOI |
| `agents/7agent_reduced/prompt_fragments/generic_constraints_planner_7agents_reduced.md` | `generic_constraints_7agents_reduced.md` | 4 spans cut |
| `agents/7agent_reduced/tools_config/hard_constraints_tools_planner_7agents_reduced.md` | `hard_constraints_tools_7agents_reduced.md` | 1 span cut |

#### C3.2 Structural moves and rewrites

1. **Move the pipeline flow + agent roster to the top** (p. 26):
   *"I would position here the normal pipeline flow and available agents, keeping
   the routing for where it is now. Reason: the propeller has to be explained and
   what the framework generates has to be explained."*
   Move prompt lines **271–275** (`## Available Agents` + `$available_agents` +
   `## Normal Pipeline Flow (for reference)` + `$pipeline_flow`) to sit
   immediately after the `## The three situations you are called in` section
   (i.e. after line 11, before `## Output mechanics` at line 13). Leave the
   `## Routing` section where it is.
2. **Delete `## DC Input Inspector status (this session)`** — prompt lines
   277–285, fully red (p. 29). Note this is inside a `<<DCII_ONLY>>` region;
   remove the region's contents but keep the markers balanced.
3. **Precision-directive vocabulary** (pp. 26–27) — the job is no longer
   section-specific:
   * `A **PRECISION SECTION-MATCH job**` → `A **PRECISION INPUT-MATCH job**`
   * `the user wants the blade sections to closely reproduce` → `…wants one or more features to closely reproduce`
   * `a precise drawing` → `a precise input`
   * delete `blade-section` before `drawing` in *"a PRECISE SKETCH verdict on a blade-section drawing"*
   * in the directive template: delete `— blade sections.` and `the blade-section SHAPES`; `the user's cropped sketch` → `the user's input(s)`; `the sketch crop` → `the input(s)`; delete `shape` in *"the visual shape gap"*
   * `Keep iterating until the sections closely match` → `…until the DC output closely matches`
   * after `(a plateau)` add `due to parameters limited ranges`
4. **Role 3 — the "continue" branch** (p. 28). Four substitutions, in the
   reviewer's words:
   * `CONTINUE to **the 3D precision check**` → `CONTINUE to **another user request**`
   * `the user **also supplied a top / side / perspective sketch of the whole propeller that the 3D geometry should match**` → `the user **had given more requests** / **still not satisfied**`
   * the yellow `(e.g. a section's radial position / middlePos affecting the planform, a chord, or an angle);` → `while not substantially altering the work of the previous precision job`
   * the closing yellow paragraph *"Only after this 3D check finalizes do you APPROVE to the user. If the user gave NO 3D-view sketch, there is nothing extra to check — approve as normal."* → *"Once all the user requests that could have been done with the current data have been completed, you can APPROVE to the user."*
5. **Tool Caller entry order** (p. 29): *"for the TC, first explain the json of
   parameters, then the render_blade sections, then the one to generate and
   render the whole propeller."* Rewrite the TC bullet in the scoped
   `available_agents` copy in that order.
6. **Pipeline string + "you"** (p. 29): apply §A3 in the scoped `pipeline_flow`
   copy, and change *"which then calls **the Planner** for a recovery plan"* →
   *"which then calls **you** for a recovery plan"*.
7. **Parameter list → tool** (pp. 30–31). Delete prompt lines 407–408
   (`## The $parameter_count Design Parameters …` + `$parameter_list`). In HARD
   RULE 4, replace the red `(listed below)` with the reviewer's sentence:
   *"If you need to see which they are and what they represent, use
   `dc_params_list`."*
8. **Blade sections — 3D first, then sections** (p. 34): *"here I would explain
   BOTH the 3D geometry generation AND the blade-section visualizer. I would
   start with the former."*
   Delete `$blade_sections_visualizer` (prompt line 525) and fold a rewritten
   version into the Planner's existing overlay
   `agents/7agent_reduced/tools_config/blade_sections_visualizer_planner_7agents_reduced.md`,
   which now opens with full-3D geometry generation and then covers the sections
   visualizer. Apply within it: `mesh` → `geometry`, `drawing` → `inputs`, and the
   red cuts in the table below.
9. **Duplicate routing block** (p. 34): *"this other routing is a repetition."*
   The `## Routing` heading, natural-flow line and position lines emitted by
   `reduced7/agents/shared/routing.py` duplicate the roster and flow now moved to
   the top of the prompt. Suppress that section for the Planner via §A2.

#### C3.3 Answer to the question on p. 27

*"shouldn't this be written Part-2 instead of Part-1?"* — on *"A genuine design
ask → FORWARD with a brief Part-1 note only."* **Part-1 is correct**: Part 1 is
the reasoning text that stays in the Planner's own history, and the sentence says
that reasoning can be brief. The routing call's Part 2 is always required and is
not what the sentence is limiting. **No action** — the whole bullet block is red
and disappears anyway.

#### C3.4 Routing-section reduction (§A2)

Red on p. 35 covers `### How to decide where to route`, `### Do not loop —
ESCALATE when stuck`, `### Permission / authorisation issues → Orchestrator`,
`### Routing is a tool call — MANDATORY` and the free-form-prose paragraph.
What survives for the Planner: the **Available routing tools** fragment
(`routing_planner_uii_first.md`) plus the two sentences at the end of the
mandatory-tool-call section that are *not* highlighted (*"Do NOT describe or
announce which tool you intend to call…"*).

#### C3.5 Tool changes

Per §B4. `read_user_queries` → `read_user_inputs` (§B3); drop `read_attempt`,
`list_input_files`, `read_input_text`, `read_image_notes`, `view_images`,
`ocr_regions`; add `read_attempts` and `dc_params_list`.

Prompt sections that describe now-unbound tools must go with them — the table
below flags each: `## Utility tool: read_user_queries…` (line 441),
`## Reference — the user input files (text + images)` (line 419), and
`## Attempt folders and the attempt tools (list_attempts / read_attempt)`
(line 477, retitled and rewritten for `read_attempts`).

#### C3.6 Every highlighted span, with its source anchor

Generated directly from the PDF annotations. `lines` are 1-based in the named file at commit `4786832`; `p.` is the PDF page; `~` marks a fuzzy match to verify by eye. `RED` = delete the text. `YEL` / `DKYEL` = modify per the comment recorded above. `GREEN` = move. Adjacent highlights of the same colour are merged into one row, so a row can cover several annotations.

##### `DC_prompt_fragments/dc_config/parameters.md` — 1 span

> The whole fragment is dropped for this agent — delete the `$slot` line and its heading from the prompt rather than editing this file.

| lines | colour | p. | text |
|---|---|---|---|
| 26-28 | RED | 32 | 14. outerCamber (% of chord) — Profile camber [0; 9] 15. outerChord (mm) — Chord length [10; 30] 16. outerAngle (degrees) — Angle of attack [2; 25] |

##### `DC_prompt_fragments/tools_config/blade_sections_visualizer.md` — 1 span

> The `$blade_sections_visualizer` slot is removed from the Planner's prompt (§C3.2 item 8). This fragment's text, with the cuts below applied, is folded into the Planner's overlay `agents/7agent_reduced/tools_config/blade_sections_visualizer_planner_7agents_reduced.md` — do not edit the shared file.

| lines | colour | p. | text |
|---|---|---|---|
| 4-7 | RED | 34 | stacked vertically, each at its true angle of attack (the render_blade_sections tool) is shown to the user and |

##### `agents/7agent_reduced/dc_config/hard_constraints_dc_7agents_reduced.md` — 1 span

> The whole fragment is dropped for this agent — delete the `$slot` line and its heading from the prompt rather than editing this file.

| lines | colour | p. | text |
|---|---|---|---|
| 2-6 ~ | RED | 32 | Hard constraints — DC-specific Domain hard rules (every agent) The 16 named parameters are the ONLY design levers and there is no mesh-editing capabil … th. Reject invented parameters (hub_radius, fillet_radius, tip_clearance, any "supplemental" value) — they do not exist. |

##### `agents/7agent_reduced/planner/prompt_7agents_reduced.md` — 48 spans

| lines | colour | p. | text |
|---|---|---|---|
| 49-53 ~ | RED | 26 | The DCIC reads the extraction itself — do not paste its content. Include Current attempt: <absolute path> ONLY when REUSING an existing attempt whose  … add your sense of how readable each is — a hint for the DCII / DCOI on whether to re-load, not a binding classification. |
| 66-67 | RED | 26 | — you can only REPLACE it, which also restarts that phase's refine budget. |
| 69-70 ~ | DKYEL | 26 | SECTION-MATCH INPUT the blade sections |
| 77-77 | RED | 26 | the blade-section SHAPES — blade sections. |
| 83-84 | RED | 27 | — section shapes, CHORDS, angles and middlePos alike — and holds fixed ONLY what the user themselves fixed (name it explicitly here). |
| 90-92 | RED | 27 | — a rough freehand doodle is NOT a precision job; a measured, to-scale section drawing with a matching user demand is. |
| 95-100 ~ | RED | 27 | without it the loop does not happen. * CLARIFY back to the UII ( call_user_input_inspector ) — ONLY for a defective extraction (your routing tools bel … hrough the Orchestrator → UII BEFORE you are called, so the extraction you read already reflects the newest user turn. * |
| 111-114 | RED | 27 | Part 2 carries only: the next agent(s) to call with one line of qualitative intent each, and whether the user must be asked (state what information is needed back — the Receptionist composes the wording). |
| 121-122 | RED | 27 | The Receptionist reads that wording to decide whether to update the Parameters panel; |
| 126-128 ~ | RED | 27 | Compare the extraction's QUANTITATIVE INPUTS against that attempt ( read_attempt ) — only values the user actually stated, not all 16. |
| 132-135 | RED | 27 | The Receptionist relays BOTH notes FROM your hand-off and manufactures neither: a dropped value reaches the user as if their number had been used, and a dropped residual oversells a plateaued or ceiling-limited match as a satisfying solution. |
| 137-143 | RED | 27 | — a sections plateau must not disappear because a later 3D phase ran. Never restate a plateau as a match: if the DCOI said "partially matched" or "pla … tempt) — an untried lever means the residual is NOT a tool limit, and the user needs to know which ones were left alone. |
| 156-157 | RED | 27 | — goals, constraints, strategy caps ("try only two designs then report back"), disambiguating annotations. |
| 158-158 | YEL | 36 | read_user_queries |
| 158-159 | RED | 27 | read_user_queries gives you the rest when you need it. |
| 162-176 ~ | RED | 27 | Typical handling: A genuine design ask → FORWARD with a brief Part-1 note only. A question answerable from prior agent histories → read_agent_history  …  "sections" after (a plateau) add "due to parameters limited ranges" shouldn't this be written Part-2 instead of Part-1? |
| 194-197 ~ | RED | 28 | when a directive you wrote cannot be turned into parameter values. Rules 6–8 below govern what a plan may touch, when to retry, and when to stop and ask the user instead. |
| 220-223 | RED | 28 | (single-attempt, multi-attempt, recovery flows that reached a verdict), You know you are here because the hand- off carries the cycle outcome — the attempt folders produced and DCOI's verdict — and asks you to approve. |
| 227-227 | RED | 28 | / read_attempt(n, ...) |
| 232-239 | RED | 28 | — the verdict aligns with your plan and the output reasonably matches the request. (See the APPROVE move for what Part 2 carries and how to phrase the … ole 2). the request never needed a generated mesh but the chain ran anyway (see the move above); no attempt is surfaced. |
| 240-240 | YEL | 28 | the 3D precision check |
| 242-243 | YEL | 28 | a top / side / perspective sketch of the whole propeller that the 3D geometry should match, |
| 244-250 | RED | 28 | Instead ISSUE A FRESH 3D precision directive (replacing the sections one — see "Issue a STANDING DIRECTIVE") and produce a Recovery PLAN (Role 2) that …  top/side render views against the relevant sketch view. The 3D directive mirrors the sections one but swaps the target, |
| 256-258 | YEL | 28 | (e.g. a section's radial position / middlePos affecting the planform, a chord, or an angle); |
| 262-263 | YEL | 28 | Only after this 3D check finalizes do you APPROVE to the user. If the user gave NO 3D-view sketch, there is nothing extra to check — approve as normal. |
| 265-269 | RED | 29 | What you do NOT see in Role 3: mid-cycle hops along a sequence you already authored (the Orchestrator forwards those without you; you see the cycle ag … irect answers you already gave (the Orchestrator hands those straight to the Receptionist — no separate approval round). |
| 277-285 | RED | 29 | DC Input Inspector status Any Sequence YOU author that creates or modifies parameters must route through the DC Input Inspector between the DC Input C … . On most precision refine rounds the DCIC skips it to keep the loop tight; that is by design, not yours to plan around. |
| 299-300 | RED | 30 | (interpreting specific numbers and mapping them to parameters is the UII's job) |
| 304-310 | RED | 30 | you name the parameter and the direction ("increase <param X>"), the DC Input Creator turns that into a value. (Observed failure: the Planner counted  …  is wrong, NAME the suspicion and ask the agent to independently re-verify — do not "correct" it to a number you supply. |
| 316-321 ~ | RED | 30 | 5. Plan only around metrics and levers that actually exist. The DC Output Inspector's read is qualitative. The only numbers are the mesh metrics the T …  session. The only levers a refinement can move are the 16 design parameters written to parameters.json. parameters.json |
| 323-323 | RED | 30 | The three states above govern what a plan may touch: |
| 329-332 | RED | 30 | A number the user gave in chat that the extraction has not yet recorded — including a [Receptionist clarification: …] line — is a user value too: treat it as LOCKED until the extraction says otherwise. |
| 341-344 ~ | RED | 30 | When you DO direct a change to a user-supplied value, your routing message names the parameter(s), the authorisation each rests on, and how far each may move — plain words the DCIC can act on and the DCII can check. |
| 362-373 | RED | 31 | — raise it only when each attempt genuinely breaks new ground.) If you cannot name a concrete differentiator, that IS the signal to escalate. Never re … ent's last tool result ( read_agent_history ) to check for a missing/malformed argument before assuming an external fix. |
| 382-390 | RED | 31 | (locked-value collision — the remaining levers all touch user-locked parameters): (why this parameter, given the defect and the exhausted non-locked l … ange?". (out of qualitative levers — unlocked parameters remain but you have exhausted materially different directions): |
| 392-393 | RED | 31 | not permission; say plainly that another automated guess is unlikely to converge. |
| 395-396 | RED | 31 | Never list system-chosen defaults as if user-locked, and never mix the permission and guidance framings. |
| 402-404 | RED | 31 | B. Use only capabilities in the agent roster above. Do not propose external scripts, infrastructure control, or any "if supported" capability. |
| 410-410 | RED | 32 | (apply to every agent) |
| 435-439 | RED | 32 | When a user reference image is a filled-in FORM/TEMPLATE, only the user's own marks are inputs — the pre-printed guides, reference circles, min/max ca … specify and the allowed ranges), NOT choices. Read the handwritten/drawn marks and treat printed values as context only. |
| 441-462 | RED | 33 | Utility tool: read_user_queries(n, from_start=False) You do NOT receive user_query.txt automatically — call this tool when you actually need to inspec … at you find when forwarding to the UII if the context materially helps extraction; the UII still reads the files itself. |
| 464-475 | RED | 33 | Utility tool: read_agent_history(agent_name, last_n=None) You can inspect another agent's live message history to answer questions about prior pipelin … eline run. Forward into the chain only when the request genuinely requires running (or re- running) the design workflow. |
| 477-477 | RED | 33 | and the attempt tools |
| 479-482 | RED | 33 | (the Orchestrator may, only as a fallback when the DCIC cannot). You do NOT have a tool to create attempt folders and must NOT try to open one yourself. |
| 484-490 | RED | 33 | Opening a folder — you DIRECT, the DCIC creates. In your Part-2 message name a short, filename-safe slug (the dominant choice or recovery hypothesis)  … es parameters.json into it. Reuse is the only case that carries a Current attempt: — see the FORWARD move above for how. |
| 493-499 | RED | 33 | read_attempt(n, file) reads one file from one. Most cycles need NEITHER: the UII already folds user-referenced baselines ("use attempt 3 but…") into t … henever the user stated a value or authorised a lever (the not-honoured-value and untried-lever checks above). Otherwise |
| 503-504 | RED | 33 | (the histories show what was said; the attempts show what hit disk). |
| 510-511 | RED | 33 | - Baseline verification — you suspect the UII/DCIC made a wrong baseline choice and need the on-disk parameters before approving. |

##### `agents/7agent_reduced/prompt_fragments/generic_constraints_7agents_reduced.md` — 4 spans

> ⚠ Shared file. Make these cuts in the scoped copy `agents/7agent_reduced/prompt_fragments/generic_constraints_planner_7agents_reduced.md`, **not** here.

| lines | colour | p. | text |
|---|---|---|---|
| 3-6 | RED | 32 | DO reproduce any === STANDING DIRECTIVES (copy verbatim to the next agent) === … === END STANDING DIRECTIVES === block UNCHANGED in your own hand-off — never alter, summarise, translate, re-order or omit it; only the Planner may change it. |
| 9-10 | RED | 32 | ("the Planner directed …", "the user asked …"; never relabel one source as another). |
| 14-18 | RED | 32 | DON'T invent tools, files, fallback policies, confidence scores or version numbers that do not exist, and DON'T state an observation you cannot source … istory, or the user's own words. If your bound tools can't do it, ESCALATE — hand the problem to whoever can resolve it. |
| 26-27 | RED | 32 | The only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up. |

##### `agents/7agent_reduced/tools_config/blade_sections_visualizer_planner_7agents_reduced.md` — 3 spans

| lines | colour | p. | text |
|---|---|---|---|
| 6-7 | RED | 34 | — it is much faster because it skips RhinoCompute. |
| 16-19 | RED | 34 | If the user asks for the maximum precision possible, use the cheap sections loop to run several refinement passes, tightening the geometry as much as is reasonable. Keep this fast: plan tightly and avoid unnecessary cycles. |
| 23-27 | RED | 34 | Re-rendering or observing the sections of an attempt that is already fine is in-place work, not a new design: the DC Output Inspector should send it s … mpt folders, once per generation. Only direct a NEW design when the parameter set or design direction genuinely changes. |

##### `agents/7agent_reduced/tools_config/hard_constraints_tools_7agents_reduced.md` — 1 span

> ⚠ Shared file. Make these cuts in the scoped copy `agents/7agent_reduced/tools_config/hard_constraints_tools_planner_7agents_reduced.md`, **not** here.

| lines | colour | p. | text |
|---|---|---|---|
| 6-7 | RED | 32 | Batch into ONE call; a second only when a later expression needs an earlier result. |

##### `agents/shared/prompt_fragments/available_agents.md` — 1 span

> ⚠ Shared file. Make these cuts in the scoped copy `agents/7agent_reduced/prompt_fragments/available_agents_planner_7agents_reduced.md`, **not** here.

| lines | colour | p. | text |
|---|---|---|---|
| 21-25 ~ | YEL | 29 | points generate_and_render_propeller at an attempt's parameters.json and calls it once — the tool reads that record itself and produces the mesh file  … heck numbers. It can instead be asked for render_blade_sections — the three blade cross-sections alone, with no 3D mesh. |

##### `agents/shared/prompt_fragments/pipeline_flow_uii_first.md` — 2 spans

> ⚠ Shared file. Make these cuts in the scoped copy `agents/7agent_reduced/prompt_fragments/pipeline_flow_planner_7agents_reduced.md`, **not** here.

| lines | colour | p. | text |
|---|---|---|---|
| 10-13 | RED | 29 | The Planner's recovery Sequence picks out a subset of these agents in the order they should be called; the Orchestrator executes that sequence one agent at a time — the standard forward chain is NOT re-entered. |
| 15-20 | RED | 29 | In this configuration the User Input Inspector runs FIRST: it extracts the user's intent and writes extracted_inputs.txt before the Planner sees the r … raw user inputs (texts + notes) if it needs more context, before forwarding the actionable plan to the DC Input Creator. |

##### `agents/shared/prompt_fragments/value_states.md` — 4 spans

> ⚠ Shared file. Make these cuts in the scoped copy `agents/7agent_reduced/prompt_fragments/value_states_planner_7agents_reduced.md`, **not** here.

| lines | colour | p. | text |
|---|---|---|---|
| 11-22 | RED | 29 | not a pull — it settles the parameter only when the goal does NOT bear on it, and the "keep near … if free" strength then says how closely to follow i …  for that parameter too — unless a directive holds a specific one fixed, which is then treated as LOCKED for that cycle. |
| 27-30 | RED | 30 | scoped "except <param X>", or a strategy / recovery directive to change the value; a CLARIFY bounce may carry one too; |
| 34-36 | RED | 30 | IF PRESENT — an older extraction may still carry this inline mark; today a released value is simply omitted from the section (which makes it FREE) rather than annotated. |
| 38-45 | RED | 30 | A line literally saying "user-locked" is only the DEFAULT lock and does NOT override a current authorisation — How FAR an authorised (or soft) value m …  to the user's number; "freely / as much as possible" (or nothing said) = as far as the goal requires, bounded by range. |

##### Spans generated at runtime, or covering a tool name

These cover a tool's title (meaning “this tool” — the action is on the binding, not on text) or text emitted by `reduced7/agents/shared/routing.py`. Each is accounted for in the narrative above.

- [RED] p.28 — motivation prose and judge. Extraction-only (the user asked to read/report their inputs, not to design) → the extraction IS the deliverable (the UII already produced it): REPLY DIRECTLY with what shou
- [YEL] p.29 — user → Receptionist → Orchestrator → User Input Inspector → Planner → DC Input Creator → DC Input Inspector → Tool Caller → DC Output Inspector → Orchestrator → Receptionist → user
- [RED] p.30 — What a plan may touch — the value states; authorization = scope + how far. The three states above govern what a plan may touch: no plan may change a LOCKED value without the user's authorisation; a SO
- [RED] p.30 — Before ANY revision directive, read the extraction's QUANTITATIVE INPUTS and count the locked values — a value marked SOFT TARGET is an available lever, NOT a locked value, so exclude it: if all 16 pa
- [YEL] p.31 — The 16 Design Parameters — the ONLY parameters that exist Global / ring 1. bladeCount (integer) — Number of blades [3; 6] 2. impellerRadius (mm) — Outer radius of the impeller ring [60; 80] 3. impelle
- [RED] p.32 — Reference — the user input files (text + images) The user's input directory (/app/inputs) contains: * user_query.txt — every user-facing turn (chronological log). * extracted_inputs.txt — the UII's st
- [RED] p.34 — Routing You are one agent in a decentralised pipeline. The natural flow is: Orchestrator → User Input Inspector → Planner → DC Input Creator → DC Input Inspector → Tool Caller → DC Output Inspector → 
- [RED] p.35 — How to decide where to route If the Orchestrator's instruction in your incoming message told you to continue the pipeline (explicitly or by default, since no instruction to report back means continue)
- [RED] p.35 — Do not loop — ESCALATE when stuck If you find yourself about to call the same tool with the same arguments you already called earlier in this turn, STOP. Calling the same read tool twice on unchanged 
- [RED] p.35 — Permission / authorisation issues → Orchestrator (not the previous agent) If a rule in your system prompt blocks an action unless some authorisation is present, READ THE INCOMING HAND-OFF (and any ups
- [RED] p.35 — Routing is a tool call — MANDATORY Every response that ends your turn MUST invoke exactly one of the routing tools listed above. The tool's message argument IS the complete hand-off text the recipient
- [RED] p.35 — Write the message argument as free-form prose: no fixed template, no enumerated option menus, no placeholder phrasings. Include everything the recipient genuinely needs (paths the recipient's tools re
- [RED] p.35 — Keep that reasoning terse (one or two lines is plenty).
- [RED] p.39 — Depending on this agent's settings the tool may also attach the zoomed crop image of each region so you can verify against it.

##### Short substitutions (under ~15 characters)

Too short to locate reliably by text search — every one is spelled out in the narrative above, with its replacement.

- [RED] p.26 — below
- [RED] p.26 — blade- section
- [DKYEL] p.26 — drawing
- [YEL] p.26 — cropped sketch.
- [YEL] p.26 — sketch crop
- [RED] p.26 — shape
- [YEL] p.27 — sections
- [RED] p.27 — NACA airfoil
- [RED] p.27 — The
- [YEL] p.28 — list_attempts()
- [RED] p.28 — SECTIONS
- [YEL] p.28 — also
- [YEL] p.28 — supplied
- [RED] p.29 — JSON,
- [YEL] p.29 — the Planner
- [RED] p.29 — (this session)
- [RED] p.30 — (listed below).
- [RED] p.32 — (every agent)
- [YEL] p.33 — (list_attempts
- [RED] p.33 — / read_attempt)
- [YEL] p.33 — list_attempts()
- [RED] p.34 — slow
- [RED] p.34 — mesh
- [YEL] p.34 — mesh
- [YEL] p.34 — drawing
- [YEL] p.37 — list_attempts
- [RED] p.37 — read_attempt
- [RED] p.38 — list_input_files
- [RED] p.38 — read_input_text
- [RED] p.38 — read_image_notes
- [RED] p.39 — view_images
- [RED] p.39 — ocr_regions

---

### C4. User Input Inspector

PDF pp. 41–52. Prompt: `agents/7agent_reduced/user_input_inspector/prompt_7agents_reduced.md`.

#### C4.1 Scoped copies to create

| new file | copy of | why |
|---|---|---|
| `agents/7agent_reduced/dc_config/structure_user_input_inspector_7agents_reduced.md` | `DC_prompt_fragments/dc_config/structure.md` | 2 cuts + 1 rephrase; also used by the DCIC |
| `agents/7agent_reduced/prompt_fragments/generic_constraints_user_input_inspector_7agents_reduced.md` | `generic_constraints_7agents_reduced.md` | 2 spans cut |
| `agents/7agent_reduced/tools_config/hard_constraints_tools_user_input_inspector_7agents_reduced.md` | `hard_constraints_tools_7agents_reduced.md` | 1 span cut |

`sketch_handling_user_input_inspector_7agents_reduced.md` is **already** a scoped
copy — edit it in place.

#### C4.2 Edits the comments ask for

1. **p. 41 — "rephrase this text highlighted in yellow."** In the scoped
   `structure` copy: *"so its radius = 4 + middlePos·(impellerRadius − 4) mm. It
   need not be the geometric midpoint."* ⚠ **The comment says rephrase but not
   into what.** Suggested: *"its radius follows from middlePos and the ring
   radius, and is not necessarily the blade's midpoint."* Confirm or supply your
   own wording.
2. **p. 43 — `instead of "each", use "they may be"`.** *"input_images/ — optional
   reference images, each paired with a `<name>_note.txt`"* → *"…they may be
   paired with a `<name>_note.txt`"*.
3. **p. 43 — "WRONG: it is any USER-SUPPLIED drawing containing design
   details."** Replace the definition in
   `sketch_handling_user_input_inspector_7agents_reduced.md`: *"A 'sketch' is any
   USER-SUPPLIED reference image conveying design intent"* → *"A 'sketch' is any
   USER-SUPPLIED drawing containing design details."*
4. **p. 44 — "the UII shouldn't be needed to care about attempts folders."**
   Delete the whole `## Prior attempts` section (prompt lines 177–186) and unbind
   both attempt tools.
5. **Three merges into "Available routing tools"** (pp. 44, 45, 47). The reviewer
   wants the routing material consolidated rather than spread across five
   headings:
   * p. 44 — *"Put the content of this paragraph together with 'How to decide
     where to route', instead of here"* → the `## Forwarding` paragraph (line 187).
   * p. 44 — *"join this with what is currently in 'Available Routing tools'"* →
     the design-generation FORWARD paragraph with its `Extracted inputs file:`
     line.
   * p. 45 — *"Join this Escalate and Clarify with what is currently written in
     'Available routing tools'"* → the ESCALATE / Planner-CLARIFY paragraphs.
   * p. 47 — *"add what remains of this whole paragraph, including the title, to
     'Available routing tools'"* → whatever survives the red cuts in
     `### Routing is a tool call — MANDATORY`.
   All four land in `agents/shared/prompt_fragments/routing_user_input_inspector_uii_first.md`,
   which only the UII consumes. Suppress the now-empty sections via §A2.
6. **Delete the `### Blade sections` block** — prompt lines 248–250, fully red
   (p. 47), including its `$blade_sections_visualizer_per_agent` reference.
7. **p. 45 — "RAG will be shortened later on."** Acknowledged, **no action in
   this pass**. The `<<HAS_DBA>>` region stays as-is.

#### C4.3 Tool changes

Unbind `list_attempts`, `read_attempt` (p. 49), `list_input_files`,
`read_input_text`, `read_image_notes` (p. 50). Keep `read_user_inputs`,
`write_extraction`, `calculate`, `view_images`, `ocr_regions`, both routing tools
and both RAG tools — `retrieve_user_inputs` on p. 50 is **not** highlighted and
stays.

#### C4.4 Routing-section reduction (§A2)

Red on p. 47 covers the `## Routing` header block, most of `How to decide where
to route`, `Do not loop — ESCALATE when stuck`, most of `Permission /
authorisation issues`, and `Routing is a tool call — MANDATORY`. After the merges
in C4.2.5 the UII should emit **only** the Available-routing-tools fragment plus
the surviving CLARIFY sentence and the "Do NOT describe or announce which tool
you intend to call" paragraph.

#### C4.5 Every highlighted span, with its source anchor

Generated directly from the PDF annotations. `lines` are 1-based in the named file at commit `4786832`; `p.` is the PDF page; `~` marks a fuzzy match to verify by eye. `RED` = delete the text. `YEL` / `DKYEL` = modify per the comment recorded above. `GREEN` = move. Adjacent highlights of the same colour are merged into one row, so a row can cover several annotations.

##### `DC_prompt_fragments/dc_config/structure.md` — 1 span

> ⚠ Shared file. Make these cuts in the scoped copy `agents/7agent_reduced/dc_config/structure_user_input_inspector_7agents_reduced.md`, **not** here.

| lines | colour | p. | text |
|---|---|---|---|
| 8-9 | YEL | 41 | so its radius = 4 + middlePos·(impellerRadius − 4) mm. It need not be the geometric midpoint. |

##### `DC_prompt_fragments/tools_config/blade_sections_visualizer_user_input_inspector.md` — 1 span

> The whole fragment is dropped for this agent — delete the `$slot` line and its heading from the prompt rather than editing this file.

| lines | colour | p. | text |
|---|---|---|---|
| 1-4 ~ | RED | 47 | Blade sections The system can render just the three blade cross-sections, much faster than the full 3D propeller. When the user's request centres on t … hord, angle, high-point) — make that clear in your extraction, so the Planner can choose the faster sections-first path. |

##### `agents/7agent_reduced/dc_config/user_input_types/sketch_handling_user_input_inspector_7agents_reduced.md` — 2 spans

| lines | colour | p. | text |
|---|---|---|---|
| 1-1 | RED | 43 | reference image conveying design intent. |
| 17-21 | RED | 44 | or CAD-like geometry no dimensioning, and and view type (a whole-propeller doodle is usually rough; a dedicated blade top-view or a blade-section profile often carries proportions meant to be reproduced). |

##### `agents/7agent_reduced/prompt_fragments/generic_constraints_7agents_reduced.md` — 2 spans

> ⚠ Shared file. Make these cuts in the scoped copy `agents/7agent_reduced/prompt_fragments/generic_constraints_user_input_inspector_7agents_reduced.md`, **not** here.

| lines | colour | p. | text |
|---|---|---|---|
| 21-22 | RED | 45 | DON'T script the final user-facing reply — route your content to the Orchestrator. |
| 25-27 | RED | 45 | Invoke the tool in the same response where you finish your work. The only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up. |

##### `agents/7agent_reduced/tools_config/hard_constraints_tools_7agents_reduced.md` — 1 span

> ⚠ Shared file. Make these cuts in the scoped copy `agents/7agent_reduced/tools_config/hard_constraints_tools_user_input_inspector_7agents_reduced.md`, **not** here.

| lines | colour | p. | text |
|---|---|---|---|
| 6-7 | RED | 45 | Batch into ONE call; a second only when a later expression needs an earlier result. |

##### `agents/7agent_reduced/user_input_inspector/prompt_7agents_reduced.md` — 12 spans

| lines | colour | p. | text |
|---|---|---|---|
| 32-33 | RED | 42 | The other agents decide what is actionable; that is true both for a design request and for an extraction-only one. |
| 45-45 | RED | 42 | (auto-appended by the web UI). |
| 83-86 | RED | 42 | One line per quantity within a single design's listing (multi-design sub-lists may legitimately repeat a parameter). A revision overwrites its line; a released parameter's line is dropped, never annotated. |
| 93-94 | RED | 43 | Never correct, clamp or drop it. A real-world quantity still needing conversion is not yours to judge. |
| 118-120 | RED | 43 | Use it ONLY where the user themselves subordinated the value — otherwise a stated value stays locked, including a UI-pinned (FIXED) one, unless a LATER message subordinates it. Name the goal in DESIGN INTENT. |
| 139-143 | RED | 43 | Free-form text, NOT a yes/no flag — understating it silently loses the demand. It is the user's MANDATE — separate from how precise the sketch itself is. The goal behind any SOFT TARGET recorded in §1, and any permission to vary a parameter that is tied to a design characteristic. |
| 156-157 | RED | 43 | The note is first-class user intent, not optional commentary — integrate BOTH the image and its note. |
| 159-162 | RED | 43 | Record how readable each image is — a clean one-feature sketch is simple; a busy technical drawing, or a photo no short description could stand in for, is complex. |
| 177-185 | RED | 44 | Prior attempts list_attempts() / read_attempt(n, file) read this session's attempt folders ( parameters.json , description.txt , render paths). Use th … nd then write the resulting values into QUANTITATIVE INPUTS. For a generic request ("make it lighter") do not call them. |
| 189-191 | RED | 44 | Route only AFTER write_extraction has succeeded, and keep the message to one or two sentences of observations — not a repeat of the extraction, which is already on disk. Include your read of how readable the images were. |
| 200-200 | RED | 44 | Current attempt: <absolute path> # ONLY when the hand-off supplied one |
| 222-227 | RED | 45 | But do NOT try to answer what is not in the user's files: design intent, operating conditions, whether a value is a good engineering choice, or whethe …  For those, ESCALATE to the Orchestrator stating what is missing — the UII is the wrong target for permission questions. |

##### `agents/shared/prompt_fragments/routing_user_input_inspector_uii_first.md` — 1 span

| lines | colour | p. | text |
|---|---|---|---|
| 9-11 | RED | 47 | You are the first agent in the natural flow; there is no "previous" agent in the chain for you to CLARIFY back to. Anything that would otherwise be a "back" routes to the Orchestrator instead. |

##### `reduced7/agents/shared/routing.py` — 2 spans

| lines | colour | p. | text |
|---|---|---|---|
| 177-177 ~ | RED | 47 | The tool call is the routing decision; its message argument is the hand-off. |
| 182-183 ~ | RED | 47 | the recipient's tools require, and nothing they do not. non-user-authored values) |

##### Spans generated at runtime, or covering a tool name

These cover a tool's title (meaning “this tool” — the action is on the binding, not on text) or text emitted by `reduced7/agents/shared/routing.py`. Each is accounted for in the narrative above.

- [RED] p.44 — The recipient does not auto-load the extraction — it reads the file at that path. When your incoming hand-off carried a Current attempt: , copy it through (the Planner relays it to the DCIC); otherwis
- [RED] p.47 — Routing You are one agent in a decentralised pipeline. The natural flow is: Orchestrator → User Input Inspector → Planner → DC Input Creator → DC Input Inspector → Tool Caller → DC Output Inspector → 
- [RED] p.47 — If the Orchestrator's instruction in your incoming message told you to continue the pipeline (explicitly or by default, since no instruction to report back means continue), and your own work succeeded
- [RED] p.47 — If something is fundamentally wrong and no agent in the chain can fix it, route to the Orchestrator (ESCALATE).
- [RED] p.47 — Do not loop — ESCALATE when stuck If you find yourself about to call the same tool with the same arguments you already called earlier in this turn, STOP. Calling the same read tool twice on unchanged 
- [RED] p.47 — If a rule in your system prompt blocks an action unless some authorisation is present, READ THE INCOMING HAND-OFF (and any upstream file the hand-off points to, e.g. extracted_inputs.txt) ONCE MORE be
- [RED] p.47 — context about what changed and why, authorship of any add what remains of this whole paragraph, including the title, to "Available routing
- [RED] p.47 — The previous agent in the chain typically CANNOT grant permission — authorisations come from the user (relayed by the Receptionist → Orchestrator), from the Planner (relayed by the Orchestrator), or f
- [RED] p.47 — Routing is a tool call — MANDATORY Every response that ends your turn MUST invoke exactly one of the routing tools listed above.
- [RED] p.47 — The tool's message argument IS the complete hand-off text the recipient will see — there is NO separate audit block to emit. Do NOT write a ---ROUTING--- / --- MESSAGE--- / ---END--- template; that fo
- [RED] p.47 — Write the message argument as free-form prose: no fixed template, no enumerated option menus, no placeholder phrasings. Include everything the recipient genuinely needs (paths
- [RED] p.48 — Your verbose work product stays in your own history and (where applicable) on disk — do not duplicate it inside the message argument.
- [RED] p.48 — Keep that reasoning terse (one or two lines is plenty).

##### Short substitutions (under ~15 characters)

Too short to locate reliably by text search — every one is spelled out in the narrative above, with its replacement.

- [RED] p.41 — (r = 4 mm)
- [RED] p.41 — (radius 4 mm).
- [YEL] p.43 — each
- [RED] p.44 — Forwarding
- [RED] p.49 — list_attempts
- [RED] p.49 — read_attempt
- [RED] p.50 — list_input_files
- [RED] p.50 — read_input_text
- [RED] p.50 — read_image_notes

---

## D. Checks to run before calling this done

1. **Nothing but the four agents moved.** Assemble all nine prompts before and
   after (`agents/shared/prompts.py` with `SYSTEM_TOPOLOGY=7`,
   `PROMPT_VARIANT="reduced"`) and diff. DCIC, DCII, Tool Caller, DCOI and the
   Database Handler must be **byte-identical**. This is the single most important
   check — it is what the scoped-copy approach buys, and a missed registration in
   §A1 silently defeats it.
2. **No unresolved placeholders.** No `$slot`, `{slot}` or `<<MARKER>>` may
   survive in any assembled prompt. Deleting a `$slot` line while leaving its
   heading produces a bare heading; deleting inside a `<<…>>` region while
   dropping one delimiter produces a leaked marker.
3. **Every bound tool is described, every described tool is bound.** Cross-check
   each agent's final bind list against its prompt text. The existing
   `retrieve_attempt` gap (bound to DCIC/DCII/DCOI, never described) is
   pre-existing and out of scope — do not "fix" it here.
4. **`read_attempts` callers.** Grep for `list_attempts` and `read_attempt`
   repo-wide; the four unreviewed chain agents also import them.

---

## E. Flagged for your decision

| # | item | where |
|---|---|---|
| 1 | Fifth "remove this tool" comment on p. 22 has no adjacent tool card — `calculate` bullet or `new_attempt` paragraph? Both are already cut, so nothing is lost either way. | §C2.3 |
| 2 | Deleting the Receptionist's blade-sections region also deletes the `<<BSV_OFF>>` branch the PDF could not show. | §C1.2 |
| 3 | The p. 41 "rephrase" comment does not say what to rephrase *into*. A wording is proposed. | §C4.1 |
| 4 | `planner` is still listed in `ocr_access.DEFAULT_AGENTS`; with no image tools its toggle becomes a no-op. Remove, or keep a dead switch. | §B5 |
| 5 | RAG sections are untouched this pass, per "RAG will be shortened later on". | §C4.2 |

---

