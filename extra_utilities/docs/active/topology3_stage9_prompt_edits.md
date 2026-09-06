# Topology 3 — Stage 9, round 1: removals, edits and concatenations

**Written 2026-09-06 against `3b93d17`.**  This is the worklist for the session
that performs Stage 9 of `topology3_rebuild_plan.md`.

**Source.**  `…/Meetings/08.28/3-agent system/v1/system_prompts3_v1.pdf` — the
**5-agent** system's seven assembled prompts, annotated by the owner.
Extracted mechanically with `pymupdf`: **94 highlights (84 YELLOW, 10 RED)**
plus **11 inserted notes** (the notes are page text in Arial 8pt black, not
annotation objects — every other glyph in the document is SegoeUI/Consolas in
`#1a1a1a`, which is how they were found).

**The owner's key:** RED = remove · YELLOW = modify/edit · inserted text =
replacement wording or instruction.

**Scope of THIS round.**  Removing what is useless and concatenating what is
useful.  **NOT** uniting texts into shared paragraphs/sections — that is a
later round.

> ⚠ **The PDF annotates the 5-agent prompts, but a decision taken on
> 2026-09-06 changes the 3-agent architecture underneath them.**  Several
> annotations therefore mean MORE than they say on the page.  Read §1 before
> §4.

---

## 1. Architecture decisions locked 2026-09-06

These came from the owner in the session that produced this file.  Every one
of them changes what an annotation implies.

| # | Decision |
|---|---|
| **A1** | **`extracted_inputs.txt` does not exist in topology 3.**  The Requirements Analyst has no `write_extraction` tool, so nothing writes it — and therefore nothing may read it. |
| **A2** | **The RA communicates everything it extracts VERBALLY**, in its hand-off message.  This holds for quantitative values, qualitative descriptions, design intent, and any mix.  It is deliberately free-form prose, NOT a structured block standing in for the old file. |
| **A3** | **The RA does NOT communicate image crop regions to anyone.**  It is the only agent in this topology that can see images, so there is nobody to relay them to. |
| **A4** | **The Design Engineer reads the user inputs directly.**  It binds a `read_user_inputs` variant in place of `read_extracted_inputs`. |
| **A5** | **That variant shows image NAMES but NOT paths.**  The user's words: *"show the images names, but NOT their paths!  the names of the images may be needed as well."*  A path is only useful to an agent that can open the image or relay it; the DE is neither. |
| **A6** | **Natural flow is DESIGN-ENGINEER-FIRST:** `User → Receptionist → Planner → Design Engineer → Requirements Analyst → Planner → Receptionist → User`.  The RA-first path is the EXCEPTION the Planner selects by standing directive when the images must be read before any number can be chosen. |
| **A7** | **The RA keeps the ROUGH SKETCH / PRECISE SKETCH vocabulary and still issues that verdict** — it simply STATES it in the hand-off instead of recording it in a file section.  Deleting the vocabulary outright would silently remove the only thing that starts a precision job from a drawing. |
| **A8** | **`DCOI_COMPARISON_MODE` becomes inert under topology 3**, by the same mechanism as `PLANNER_FIRST` and `DC_INSPECTOR_ENABLED`: visible in the UI showing its real value, greyed out, a write refused.  Modes 2 and 3 name a file that will never exist.  The RA carries the mode-1 block unconditionally. |
| **A9** | **The RA's merged prompt is built on the DC OUTPUT INSPECTOR's spine**, with the UII's material folded in.  The RA's standing job is CRITIC; reading the user's images is a capability it uses when directed, not its default turn.  *(This supersedes the literal reading of the two page-23 notes, which were written while the UII was still assumed to be the base.)* |
| **A10** | **The Planner's `read_attempts` section stays for now** — revisit after a live 3-agent run.  (Answer to the owner's own "ask me again later" note on p18.) |

### 1.1 The three worked cases the owner gave

Carry these into the Planner's flow text; they are the branch table.

1. *User asks to extract inputs from TEXT* → the **DE** reads the user input
   text, reads the user inputs, writes the parameters, hands back to the
   Planner.  The RA is never called.
2. *User asks to read the blade count / extract inputs from IMAGES* → the
   Planner already knows this from the user's text, and issues a **standing
   directive telling the RA to analyse the images**; if calculations are
   needed the RA is instructed to call the **DE**.
3. *User asks to follow a specific directive with its inputs* → the Planner
   issues a standing directive addressed to **both**.  If inputs must be
   analysed first the **RA goes first**; otherwise the **DE** does.  The two
   then go back and forth until the request is satisfied.

---

## 2. Coverage — what the PDF does and does NOT cover

| PDF agent | pages | annotations | status |
|---|---|---|---|
| Receptionist | 5–12 | 3 YEL + 1 note | partially analysed |
| **Planner** | 13–22 | **82** | analysed |
| User Input Inspector | 23–31 | 9 (6 RED) | partially analysed |
| DC Input Creator | 32–41 | **0** | **NOT analysed** |
| Tool Caller | 42–49 | **0** | **NOT analysed** |
| DC Output Inspector | 50–60 | **0** | **NOT analysed** |
| Database Handler | 61–68 | **0** | **NOT analysed** |

**Consequence to hold on to:** the Design Engineer's prompt is a merge of two
agents the owner has not annotated at all, and the RA's DCOI half — its
SPINE, per A9 — is likewise unannotated.  §4 therefore covers the Planner
thoroughly and the two merged agents only where a decision in §1 forces an
edit.  **Everything else in those prompts is untouched and awaits a later
round.**

---

## 3. §A — CODE PREREQUISITES

The prompt edits below are unsafe without these.  A prompt that stops naming
`write_extraction` while the class still binds it is exactly the prompt/tool
drift `smoke_test_prompt_tool_audit.py` exists to catch — and the reverse
(unbinding first) leaves prompts naming a tool nothing binds.  **Land these
first, in this order.**

| # | File | Change |
|---|---|---|
| **C1** | `agents/requirements_analyst/requirements_analyst.py` | Delete the `write_extraction` `@tool` stub AND `_handle_write_extraction_tool`.  Remove it from `all_tools` and from the run loop's dispatch. |
| **C2** | same | Delete the `read_extracted_inputs` `@tool` stub AND `_handle_read_extraction_tool`, and its run-loop branch.  (A1: nothing writes the file.) |
| **C3** | same | `_COMPARISON_MODE_2` / `_COMPARISON_MODE_3` are dead under A8.  Keep `_build_comparison_mode_block` but have topology 3 always resolve mode 1; delete the two dead blocks, or leave them unreferenced with a comment.  **Do not delete `comparison_mode_block` from `PROMPT_MD_RUNTIME_SLOTS`** — the slot is still filled, just always with mode-1 text. |
| **C4** | `agents/design_engineer/design_engineer.py` | Delete the `read_extracted_inputs` stub, `_handle_read_tool` and `_strip_images_section` (the images-section strip is moot once there is no extraction).  Bind the new `read_user_inputs` variant instead, with its own handler. |
| **C5** | `agents/shared/user_inputs_tool.py` | Add `include_image_paths: bool = True` to `read_user_inputs_summary`.  When False the image listing emits `  - <name>` only, and the hint stops saying *"Their paths, for relaying to an agent that can view them:"* — the DE relays nothing.  **A5.** |
| **C6** | `agents/topology3/tool_text.py` | Add a `design_engineer` entry to `READ_INPUTS_DOC_BY_AGENT` describing the no-paths view.  Also add the `requirements_analyst` entry now deferred at Stage 8 — A1/A2 settle the wording question that blocked it (there is no `Input directory:` label to prefer over a comparison-source path any more, because there is no extraction to compare against). |
| **C7** | `agents/shared/routing.py` | `_PIPELINE_BY_TOPOLOGY[3]` → the **A6** string, Design-Engineer-first, with the User at both ends. |
| **C8** | `workflow_settings/editor.py` | `_INERT_UNDER_TOPOLOGY["DCOI_COMPARISON_MODE"] = (frozenset({3}), "<reason>")`.  **A8.** |
| **C9** | `extra_utilities/dry_run_topology.py` | `ROUTES[3]` must follow the new order (Planner → DE → RA → Planner), or the harness asserts a sequence the system no longer produces. |
| **C10** | `extra_utilities/topology_prompt_snapshot.py` | `_ROUTING_SHAPE["requirements_analyst"]`'s `prev_agent` and the DE's `next_agent` still read correctly under A6, but re-check after C7.  The RA's `_runtime_slots` branch must stop referencing the deleted comparison modes. |

**After C1–C10, expect the known-pending lists to shrink**: several of the
8 ORPHAN findings in `smoke_test_prompt_tool_audit` and 14 HUB findings in
`smoke_test_topology_fragments` are exactly the strings §4 deletes.  Re-run
both and prune `KNOWN_PENDING` to whatever genuinely survives — **do not leave
a pending entry masking a defect that is now fixed.**

---

## 4. §B — Global edits across `agents/3agent/`

These are the bulk of the 84 yellow highlights.  Almost every yellow on pages
13–22 is one of these four renames; they are listed once here rather than 82
times below.

> ⚠ **Scope is the WHOLE tree, not just `prompt.md`.**  The PDF shows
> ASSEMBLED prompts, so a name that appears once on the page may live in a
> spliced fragment.  Measured across all 82 files of `agents/3agent/`:

### B1 — Agent renames (204 occurrences, ~30 files)

| find | replace | count |
|---|---|---|
| `User Input Inspector` | `Requirements Analyst` | 20 |
| `UII` | `RA` | 35 |
| `DC Output Inspector` | `Requirements Analyst` | 33 |
| `DCOI` | `RA` | 23 |
| `DC Input Creator` | `Design Engineer` | 36 |
| `DCIC` | `DE` | 16 |
| `Tool Caller` | `Design Engineer` | 41 |
| `TC` (word-boundary) | `DE` | 6 |

⚠ **Not a blind sed.**  Two source agents collapse onto ONE target in both
columns, so a sentence naming both parents becomes a sentence naming the same
agent twice — *"the DC Input Creator hands to the Tool Caller"* becomes *"the
Design Engineer hands to the Design Engineer"*.  **Every sentence containing
two of the merged names must be rewritten, not substituted.**  Grep for
co-occurrence first:

```bash
grep -rnE "(DC Input Creator|DCIC|Tool Caller).*(DC Input Creator|DCIC|Tool Caller)" agents/3agent/
grep -rnE "(User Input Inspector|UII|DC Output Inspector|DCOI).*(User Input Inspector|UII|DC Output Inspector|DCOI)" agents/3agent/
```

⚠ `TC` as a bare word-boundary match is risky (it appears inside other
tokens in some fragments).  Check each of the 6 by hand.

### B2 — Extraction removal (28 occurrences, ~14 files) — **A1**

| find | action | count |
|---|---|---|
| `extracted_inputs.txt` | remove the sentence/clause; rewrite if it carries other meaning | 16 |
| `write_extraction` | remove | 5 |
| `read_extracted_inputs` | remove | 1 |
| `Extracted inputs file:` | remove the hand-off label and any "MUST carry this line verbatim" rule around it | 3 |
| `Extraction output file:` | remove | 3 |

Replace the *function*, not just the string: wherever a prompt says "read the
extraction", it must now say the DE reads the **user inputs** directly (A4) or
that the RA **tells** it (A2).

### B3 — Routing-tool renames

| find | replace | note |
|---|---|---|
| `call_user_input_inspector` | `call_requirements_analyst` | 4 occurrences |
| `call_dc_input_creator` | `call_design_engineer` | 6 |
| `call_tool_caller` | `call_design_engineer` | 4 — **then de-duplicate**: an agent that had edges to both the DCIC and the TC now has two bullets for one tool |
| `call_dc_output_inspector` | **DELETE from the Planner** (p22 RED + note) | 2 — see §5.2 |

---

## 5. §C — Per-agent edits, annotation by annotation

### 5.1 Receptionist — `agents/3agent/receptionist/prompt_3agents.md`

**p10, 3 YELLOW + note.**  Note: *"adjust the agents listed in this tool
description, sholud match those available in the 3-agent topology"*.

* The three yellows are all inside the `read_agent_history` tool description —
  the human-readable names list, the snake_case keys list, and the
  `agent_name` parameter text.
* **✅ ALREADY DONE.**  `agents/topology3/tool_text.py`'s
  `READ_AGENT_HISTORY_DESCRIPTION` was regenerated from the topology-3 roster
  at Stage 8, and `smoke_test_topology3_tool_text.py` asserts it names all four
  built agents and none of the six retired ones.  **Verify, do not re-edit.**
* The p21 note (*"fix the tool description for all agents that have this tool
  in the 3-agent system prompt — edits only applied for the 3-agent system
  topology!"*) is satisfied by the same overlay: it is topology-scoped by
  construction.

### 5.2 Planner — `agents/3agent/planner/prompt_3agents.md`

The 82 annotations are dominated by B1/B3 renames.  What follows is everything
that is **not** a plain rename.

**p13 — the agent roster.**

* NOTE *"UII and DCOI descriptions have to be united"* → one entry for the
  **Requirements Analyst**.  Per A9 the DCOI's description is the spine; fold
  in the UII's "can read the user's text and images" as a capability.
  **Delete** *"and writes extracted_inputs.txt"* and *"This is the only agent
  that interprets raw user content into…"* (A1/A2).
* NOTE *"DCIC and TC descriptions have to be united"* → one entry for the
  **Design Engineer**, covering authoring the 16 parameters AND generating /
  rendering.  Drop the hand-off between them; there is none.
* NOTE *"substitute this with the pipeline flow for the 3-agent system.  Add
  the user as well!"* → replace the flow line with the **A6** string.  The
  user appears at both ends.
* **RED** *"Each agent forwards to the next in line by default."* → delete.
* **RED** *"back to the previous agent in … line, or"* → delete.
  *(Both describe a linear chain that no longer exists: with two chain agents
  looping, "next in line" has no referent.)*

**p14 — the precision directive.**

* NOTE *"this part before the example has been already reworded in agent
  topologyes 7 and 5.  use the same rewording here."*
* **✅ ALREADY DONE.**  Commit `4e15726` reworded the lead-in so the
  standing-directive block reads as an EXAMPLE rather than a template, and it
  was imported into `agents/3agent/planner/prompt_3agents.md` at `e1e5f4a`
  (the file is byte-identical to the 5-agent source).  **Verify the text
  begins *"issue a standing directive for it.  What follows is an EXAMPLE of
  one…"* and make no further change.**

**p16 — RED** *", no DC Output Inspector."*  Delete the clause.  It sits in the
"Do NOT let the ask reach GEOMETRY" rule; the remaining prohibition (no mesh,
no renders) still stands and now reads *"no mesh, no renders."*

**p17 — the "A. / B." layout note.**  *"this should be on a new line.  if this
is not a pdf rendering problem but rather a problem in the way the planner's
system prompt is written, fix this."*
**✅ CHECKED — NO EDIT NEEDED.**  The source is already correct:
`prompt_3agents.md:339` `A. **Match the remedy to the failure class.**` and
`:341` `B. **One path per plan.**` are on separate lines.  The run-together
appearance is an artefact of the PDF builder's two-column layout.  Recorded so
it is not re-raised.

**p18 — the `read_attempts` / "Attempt folders" section.**  Owner's note:
*"Maybe this whole section could be removed … Ask me again later."*
**Asked and answered 2026-09-06: KEEP IT for now** (A10).  Apply only the B1
renames inside it.  Revisit after a live 3-agent run.

**p22 — RED `call_dc_output_inspector`** + note *"remove this tool from the
Planner"*.

* This is **not** the Planner losing its edge to the critic.  The Planner held
  TWO tools that now point at the same agent: `call_user_input_inspector` and
  `call_dc_output_inspector` both map to the Requirements Analyst.  One is
  RENAMED (B3), the other DELETED as a duplicate.
* **The code is already correct** — `Planner3._wire_routing` wires exactly
  three outgoing edges (`design_engineer`, `requirements_analyst`,
  `receptionist`).  This edit is to the PROMPT TEXT that lists the tools.
* After the edit the Planner's routing section must list exactly:
  `call_design_engineer`, `call_requirements_analyst`, `call_receptionist`.

**p19 / p20 — routing bullets and `read_agent_history`.**  All B1/B3 renames.
The p20 note (*"for read_agent_history, rename / edit the yellow-highlighted
sections for all descriptions of this tool that will be used by the 3-agent
system"*) is the overlay work already done at Stage 8 — see §5.1.

### 5.3 Requirements Analyst — `agents/3agent/requirements_analyst/prompt_3agents.md`

⚠ Remember A9: the file is currently a **mechanical concatenation** with the
UII half first and a `SCAFFOLD JOIN` marker before the DCOI half.  The Stage-9
union should be built the other way round — **DCOI spine, UII folded in** — so
these edits describe what happens to the UII-derived material, most of which
shrinks or goes.

**p23 — two notes.**  *"Add here also the description of the DCOI"* and *"Add
here also the role explanation of the DCOI"*, both on the UII's identity /
role section.  Under A9 this inverts: the DCOI's identity is the spine, and
what is folded in is the UII's *"can also read the user's text and images when
directed"*.  The merged identity must say the agent owns the requirements at
BOTH ends — derives them when asked, judges the render against them by default.

**p25 — RED.**  The whole *"Record the sketch's precision in DESIGN INTENT"*
block, including the ROUGH SKETCH / PRECISE SKETCH vocabulary.
⚠ **Do NOT delete wholesale.**  Per **A7**: remove only the *"record it in
DESIGN INTENT"* framing (there is no such section and no such file), and KEEP
the verdict and its exact vocabulary, restated as something the RA **says** in
its hand-off.  Deleting the vocabulary would remove the only trigger that
starts a precision job from a drawing.

**p27 — NOTE** *"in Routing, also add the routing to the other agent (the
Design engineer or however it is called)"*.
The RA's routing section must list **`call_design_engineer`** as well as
`call_planner`.  The code already wires both; this is the prompt text.

**p27 — RED** *"once `extracted_inputs.txt` is written and complete"* and the
`Extracted inputs file:` verbatim-line rule.  Delete both (A1).  The RA's
forward hand-off carries its findings as prose (A2), not a path.

**p28 — RED ×3.**  All three `write_extraction` dependencies:
* *"Route only AFTER `write_extraction` has succeeded…"*
* *"Pre-route self-check (mandatory).  … did `write_extraction` return
  success?"*
* *"If the Planner CLARIFYs back to you … call `write_extraction` again…"*

Delete all three (A1).  ⚠ **The middle one carries a rule worth preserving in
new form**: it exists so the agent does not route before its work is real.
Consider replacing it with a pre-route self-check appropriate to the new
contract — *did you actually state your findings in the message?* — but that is
a REWRITE, so propose it to the owner rather than writing it in this round.

### 5.4 Design Engineer — `agents/3agent/design_engineer/prompt_3agents.md`

**No annotations exist for this agent** (its two parents are on unannotated
pages).  Only the §1-forced edits apply in this round:

* B1/B3 renames.
* B2 extraction removal — the DE no longer reads an extraction (A4); its
  prompt must describe reading the **user inputs** instead, with image
  **names** but no paths (A5), and must state that it cannot see the images.
* The `SCAFFOLD JOIN` seam and both `SCAFFOLD - NOT THE FINAL TEXT` banners
  stay until the union round.
* Everything else awaits the owner's annotation of pages 32–49.

---

## 6. §D — CONCATENATIONS

Everything above removes or rewords.  This section is the other half of the
round: what gets **brought together**.

Both merged prompts are still Stage-4 mechanical concatenations — half A, a
`SCAFFOLD JOIN` marker, half B — so every subject either parent covered is now
covered twice, in two places, ~200 lines apart.

> **"Concatenate" here means CO-LOCATE, not rewrite.**  Bring the two texts
> under one heading, in order, both surviving verbatim.  Rewriting them into
> one flowing statement is the LATER round.

### 6.1 ⚠ The largest finding: every shared `$slot` is spliced TWICE

Both halves reference the same slots, so the assembled prompt carries each
fragment's full text twice.  Measured against the live assembled prompts:

| prompt | duplicated | of total | share |
|---|---:|---:|---:|
| Requirements Analyst | **15 811 chars** | 50 440 | **31 %** |
| Design Engineer | **13 852 chars** | 48 336 | **29 %** |

**~29 700 characters of verbatim duplication, removable by deleting 17
lines.**  These are NOT concatenations — there is nothing to join, because the
two references resolve to the identical fragment.  **Delete one reference (and
its heading where the heading is duplicated too); keep the other.**

**Requirements Analyst** — `agents/3agent/requirements_analyst/prompt_3agents.md`:

| slot | lines (A / B) | chars saved |
|---|---|---:|
| `$parameter_list` | 28 / 387 | 4 710 |
| `$sketch_handling` | 189 / 269 | 3 594 |
| `$database_search_tool` | 210 / 458 | 2 769 |
| `$hard_constraints_generic` | 203 / 451 | 1 594 |
| `$hard_constraints_tools` | 207 / 455 | 1 291 |
| `$hard_constraints_dc` | 205 / 453 | 1 006 |
| `$retrieve_user_inputs_tool` | 214 / 462 | 809 |
| `$domain_description` | 16 / 222 | 36 |
| `$database_search_per_agent` | 212 / 460 | 0 today |

**Design Engineer** — `agents/3agent/design_engineer/prompt_3agents.md`:

| slot | lines (A / B) | chars saved |
|---|---|---:|
| `$parameter_list` | 26 / 362 | 4 585 |
| `$hard_constraints_generic` | 309 / 412 | 4 049 |
| `$database_search_tool` | 316 / 419 | 2 769 |
| `$hard_constraints_dc` | 311 / 414 | 1 392 |
| `$retrieve_user_inputs_tool` | 320 / 423 | 809 |
| `$hard_constraints_tools` | 313 / 416 | 210 |
| `$domain_description` | 16 / 328 | 36 |
| `$database_search_per_agent` | 318 / 421 | 0 today |

⚠ **Three cautions.**

1. `$database_search_per_agent` resolves to **0 chars today** only because
   `RAG_ENABLED` is False.  De-duplicate it anyway — it doubles the moment RAG
   is switched on, and that is exactly the kind of latent duplication nobody
   goes back for.
2. **Do NOT de-duplicate the two WITHIN-half repeats.**  `$parameter_count`
   appears twice inside half A of the Design Engineer (L19, L25) and twice
   inside half B of the Requirements Analyst (L386, L400).  Those are the
   ORIGINAL prompts using a 2-character slot twice on purpose, not merge
   artefacts.
3. `$sketch_handling` in the RA resolves to
   `sketch_handling_requirements_analyst_3agents.md`, which is **itself a
   Stage-4 scaffold** — a concatenation of the UII's and the DCOI's sketch
   fragments.  Deleting one splice removes the 3 594-char duplicate; the
   fragment's own internal union is still owed, in the later round.

### 6.2 Requirements Analyst — section concatenations  *(owner-approved)*

| # | Sections | Action |
|---|---|---|
| **R1** | `## Your Role` L18 (UII) + L224 (DCOI) | ONE `## Your Role`.  **DCOI text FIRST**, UII text appended below — the critic identity is the default turn; reading the user's material is the capability it uses when directed (A9). |
| **R2** | `### 1. QUANTITATIVE INPUTS` L80, `### 2. QUALITATIVE DESCRIPTIONS` L126, `### 3. DESIGN INTENT` L134 | **Keep as WHAT TO LOOK FOR.**  Strip the file-format framing — the numbering, the section headers, every "write this to section N" — and keep the three CATEGORIES as the checklist of what the RA must identify and then STATE in its hand-off (A2). |
| **R3** | `### 4. USEFUL INPUT IMAGES` L150 | **DELETE entirely.**  Per A3 the RA never communicates crop regions: it is the only agent that can see images, so there is nobody to relay them to. |
| **R4** | `## Sketch handling` L188 + L268 | ONE section, both texts adjacent.  Also a slot de-duplication — see §6.1 caution 3. |
| **R5** | `## Hard constraints` L202 + L450 | ONE section (slot de-duplication, §6.1). |
| **R6** | `## Searching past saved sessions` L209 + `## Database tools` L457 | ONE section — same subject, different titles.  Keep the clearer heading. |
| **R7** | `## User inputs` L178 + `## Loading render images (IMPORTANT)` L230 | **Keep SEPARATE, move ADJACENT.**  Two different things loaded for two different purposes, and the DCOI's section carries the "never describe images you did not load this turn" HARD RULE (L249), which must not silently extend to user inputs. |

Net for R2 + R3: roughly 100 lines down to about 40.

### 6.3 Design Engineer — section concatenations  *(owner-approved)*

| # | Sections | Action |
|---|---|---|
| **D1** | `## Validate before you write (HARD)` L186 **+** `## Range check before you generate` L364 | **Keep L186 WHOLE; DELETE L364 entirely.**  L186 already does the range check AND the authorisation check AND owns the LOCKED-out-of-range rule.  L364's only added value was INDEPENDENCE — a second agent with fresh eyes — and merging is exactly what removes it.  What remains is either duplicated or now FALSE: "independent of upstream", "you do NOT fix it", "authoring values belongs to the agent that wrote them" and "hand back to the DC Input Creator" all describe a two-agent relationship that no longer exists.  Merge-doctrine rule 5. |
| | | 🔴 **`{render_check_library_block}` sits inside the deleted section (L381) and MUST be preserved.**  It is a runtime `.format()` slot; dropping it raises `KeyError` at agent construction.  Re-home it with the generation step. |
| **D2** | `## HARD LIMITS — Do NOT` L383 | **Keep bullet 1, delete bullets 2 and 3.**  Bullet 1 (cannot edit meshes, boolean unions, weld, remesh, rename outputs) is a true statement about the TOOLS and survives untouched.  Bullets 2 and 3 ("do NOT invent parameter tweaks of your own initiative", "do NOT decide what to do when something fails — hand back to the DC Input Creator") exist only to stop an executor overstepping into the author's territory.  Same agent now, so they would forbid the DE from doing its own job. |
| **D3** | `## Your input` L230 **+** `## Loading parameters (IMPORTANT)` L347 | Keep `## Your input`; **reduce L347 to a re-read note** placed with the generation step.  The DE receives no "Parameters file:" path — it created the folder itself.  What survives is worth keeping: generate from the FILE ON DISK, not from what you believe you wrote.  That is the guarantee `new_attempt_parameters` was designed around, and the only thing that catches a write that silently failed. |
| **D4** | `## Your Role` L18 + L330 | ONE section, **DCIC text first** — it authors before it executes. |
| **D5** | `## Attempt folders` L211 + `## Attempt folder (IMPORTANT…)` L336 | ONE section. |
| **D6** | `## Complete Parameter List` L25 + `## Parameters and Allowed Ranges` L361 | **NOT a concatenation — a DELETION.**  Verified: both reference the same `$parameter_list`, resolving to a Design-Engineer-scoped override of 4 585 chars, so the assembled prompt carries the entire list twice.  Keep ONE heading and ONE reference. |
| **D7** | `## Hard constraints` L308 + L411 | ONE section (slot de-duplication, §6.1). |
| **D8** | `## Searching past saved sessions` L315 + `## Database tools` L418 | ONE section. |

### 6.4 Ordering, once the concatenations are applied

Neither prompt should keep its A-then-B shape.  Proposed running order —
**for review, not yet applied**:

* **Requirements Analyst** (DCOI spine, A9): Role → what you can look at (the
  R7 pair) → the load-before-you-describe HARD RULE → how to compare → what to
  look for when reading inputs (R2) → sketch handling → standing directives and
  the precision refine loop → verification and override authority → phrasing
  and output format → hard constraints → database tools.
* **Design Engineer** (DCIC spine — it authors before it executes): Role →
  domain and parameter list → which lever moves what → reading the user's
  inputs → the three value states → validate before you write (D1) → attempt
  folders → generate and render → hand-off → routing → hard limits (D2) → hard
  constraints → database tools.

---

## 7. §E — Not yet analysed

The owner has not annotated the DC Input Creator (p32–41), the Tool Caller
(p42–49), the DC Output Inspector (p50–60) or the Database Handler (p61–68).

That matters more than it looks: **the DCOI is the RA's spine (A9) and the
DCIC+TC are the whole Design Engineer** — so the two merged agents are
precisely the material with no annotations.  Expect a second annotated round
covering those pages before the union stage.

The Database Handler's prompt also still describes the pipeline and the agent
roster; it will need the B1 renames even though nothing in it was highlighted.

---

## 8. §F — Open items for the owner

| # | Question |
|---|---|
| **Q1** | The RA's pre-route self-check (p28, middle RED) — replace with a findings-stated check, or drop the idea entirely? |
| **Q2** | With the DE going first and reading the inputs, does the **Receptionist** still describe the flow correctly?  Its prompt is unannotated but names the pipeline. |
| **Q3** | `MAX_SECTIONS_REFINE_ROUNDS` counts arrivals at the RA.  Under A6 the RA is the CRITIC, so a round is DE → RA — unchanged in meaning.  Confirm no retune is wanted. |
| **Q4** | The DH schedule (`dh_schedule_3agents.default.json`) still carries six question names referencing the UII / DCIC / Tool Caller.  The owner said he would adapt these himself if he runs the DH under topology 3 — confirm that still holds after A1 (two of them are about the extraction). |
