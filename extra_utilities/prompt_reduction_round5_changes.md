# Prompt reduction — round 5 (owner-annotated `7agent_reduced_system_ROUND2.pdf`)

Source PDF: `Meetings/08.20/system prompt reduction/7agent_reduced_system_ROUND2.pdf`,
annotated 2026-08-26. Built from the **pre-round-4** tree, so a number of spans no
longer match verbatim. Raw extraction: `extra_utilities/round5_annotations.json`
(62 highlights — 49 RED, 13 YELLOW — plus 11 pages of comments recovered by
diffing the annotated page text against the un-annotated build, because the
reviewer's typed notes are FLATTENED into page content, not stored as popups).

Colour key: RED = delete. YELLOW = modify / replace, usually with a typed note
alongside.

## Mapping outcome

| status | n |
|---|---|
| applies verbatim to the current tree | 53 |
| conflicts with a round-4 rewrite | 5 |
| already done by round 4 | 2 |
| partial | 1 |
| empty highlight, no text | 1 |

## Standing decisions taken this round

- **Topology 5 stays frozen.** Every new per-agent fragment gets a byte-identical
  `agents/5agent/` pass-through, as in rounds 3-4. Topology 5 has never been run
  end-to-end; this round must not be the thing that breaks it.
- **The three "is this a bullet list or a paragraph?" comments (p.7, p.22, p.69)
  are a PDF-BUILDER BUG, not a prompt bug.** `build_html.py` sets
  `MD_EXT = [..., "sane_lists", ...]`; `sane_lists` requires a blank line before a
  list that follows a paragraph, and the prompts splice list fragments directly
  under a bold lead-in (`**CAN do:**` / `$capabilities_can`). The model reads a
  correct list. Filed as **TODO F94**; no prompt changes. This makes [009], [010],
  [011], [023] and [024] NO-OPS.
- **The DC Input Creator gets ZERO edits.** [053] was withdrawn by the owner
  ("I was wrong in flagging that portion as red" — the Verbatim vs
  Real-world-quantity section stays, in the DCIC AND the DCII). [054]
  (Multi-parameter constraints) and [055] (Tool-error self-correction) were both
  declined after review.

## The headline change: the UII stops speaking the configurator's language

Highlights [043]-[047] remove parameter-name labelling from the extraction.
`impellerRadius: 70 mm` becomes `Radius of propeller: 70 mm`; the
`(real-world; relates to impellerRadius)` suffix goes. Owner: *"the UII doesn't
need to differentiate so much between verbatim and real world quantity, it just
sees whatever it sees."*

Consequences, all approved:

- [048] deletes the OUT OF RANGE rule from the UII. **No agent will carry the
  phrase "OUT OF RANGE" after this round** — the DCII (check 1) and the Tool
  Caller remain the range gates, but the extraction file no longer flags a
  breach, so an impossible user value surfaces one hop later than it does today.
- The dependent parenthetical at `agents/user_input_inspector/prompt.md:63-64`
  ("An ``OUT OF RANGE`` note is a current fact, not history, and stays — see the
  STRICT rules below") must go with it.
- `**Count countable features explicitly.**` says "Record the count under the
  parameter name" — must become a descriptive label. Consequential, not
  highlighted.
- The UII's scoped `hard_constraints_dc_user_input_inspector.md` opens "The 16
  named parameters ABOVE…" — the back-reference is dropped (owner's choice), so
  the sentence works whether or not the list is present.

**The DCIC and the DCII keep their Verbatim vs Real-world-quantity split.** It
stays reachable: a user who literally types `impellerRadius = 70mm` still
produces a parameter-named label. What changes is that the UII no longer
manufactures one.

## New workflow setting

`UII_PARAMETER_LIST_ENABLED: bool = False` in `workflow_settings/settings.py`,
gating the UII's `Design Configurator Parameters (for reference)` section.
Default FALSE per the p.29 comment. Cheap: `workflow_settings/editor.py`
auto-parses `settings.py` into the Workflow Settings editor, so a new boolean
surfaces in the web UI with no frontend work.

The UII gets a **scoped `parameters_user_input_inspector.md`** (owner: "make a
UII-specific version, as we often do… The parameters list of all the other
agents stay as they are now"), carrying the base list minus every RED bit:
[037] the outer-ring HEIGHT parenthetical, [038]+[039] the whole hub
parenthetical, [040] the `*MaxPos` / `*Thickness` notes, [041] the middlePos
radius formula. Needs an `agents/5agent/` pass-through — the topology-5 UII
shares `agent_dir_name`.

**[042] is a mis-colour.** The list continues onto p.30 and the continuation
caught RED instead of the YELLOW used on p.29. Owner confirmed: treat as yellow
— the whole list is one conditional block.

## The Receptionist loses its static parameter list

p.8 comment: *"Make this 'Parameter ranges' an optional retrieval using a
separate tool, like the planner already does. I want this information still
available because if the user asks a question about the capability of the tool,
the system must be able to respond."*

- `$parameter_list` leaves `agents/receptionist/prompt.md`.
- `dc_params_list` is bound to the Receptionist. It already exists
  (`agents/shared/dc_params_tool.py`) and is bound to the Planner and the
  Orchestrator. **It returns the SHARED `dc_config/parameters.md` by hard-coded
  path**, so a scoped Receptionist copy would NOT be served through it.
- A Receptionist-specific tool description, on the owner's framing: use it for
  quick answers and clarifications to the user about the available design inputs
  and their ranges. Per-agent tool descriptions are an established pattern here
  (`_VIEW_IMAGES_PATHS_BY_AGENT`, round 3).
- **The Parameter-name check is DROPPED entirely** (owner's choice), and with it
  the "Reject invented parameters (hub_radius, …)" sentence in
  `hard_constraints_dc_receptionist.md` ([016], "cut both, as marked"). After
  this the Receptionist has nothing about invented parameter names — deliberate,
  since it is no longer checking them.

## Per-agent edit inventory

### Receptionist

| id | action |
|---|---|
| [001] | delete "on upload, so the note FILE always exists;" |
| [002] | delete "yourself (the UII does that)" |
| [003]+[004] | compress the Pairing check to one line; delete "If both checks pass…". The `Image+note pairing: OK/INVALID` banner stays emitted (`receptionist.py:252`) and stays meaningful |
| [005] | reduce `visualize_3d_model.md` to the guard only — a literal delete would leave a bare heading |
| [006] | delete "No second-guessing the chain's reported result…" |
| [007] | delete "Decide by reasoning, not by matching markers or keywords…" |
| [008] | NO-OP — round 4 removed it; only the topology-5 copy survives, left alone |
| [009] [010] [011] | NO-OP — PDF rendering |
| [012] [013] | parameter list → `dc_params_list`; drop the Parameter-name check |
| [014]+[015] | `routing_receptionist.md`: "All onward dispatch goes through the Orchestrator." — [015] exists because deleting [014] alone strands an em-dash |
| [016] | cut "and regenerating" AND the Reject sentence, Receptionist copy only |

### Orchestrator

| id | action |
|---|---|
| [017] | delete "The UII extraction is deliberately broader…" |
| [018] | delete "Raw data (parameter JSON, full extractions) lives on disk…" — the bullet's first clause (anti-fabrication) stays |
| [019] | the "the UII has rewritten extracted_inputs.txt" example becomes conditional on the UII having actually rewritten it |
| [020]+[022] | the UII hop becomes MANDATORY for a new mid-session authorisation |
| [021] | NO-OP — round 4 already removed "Planner /" |

Owner declined hardening the separate "Route through the User Input Inspector"
section ("only the marked cuts"), so its "use judgement / a repeat does not
require a rewrite" softeners stay. The two paths therefore differ in force —
recorded deliberately.

### Planner

| id | action |
|---|---|
| [023] [024] | NO-OP |
| [025] | delete `prompt.md:190-196`, the body of the CONTINUE worked example. Owner chose the literal cut, so lines 188-189 survive and the example still models sections-then-3D |
| [026]+[027] | delete the 4-step sections-first plan and "This is a suggestion, not a rule… continue to the 3D once the sections are right" |
| [028] | "…render just the blade sections, or just the full 3D geometry, or both. It depends on the current request's needs." |
| [029] | delete "sections-first" from the surviving render-type line |

The "sections are much faster / can be the final deliverable" paragraph survives,
so the capability is still stated — only the prescriptive staging goes. This is
the T2/T3 finding acted on: runs 257/259/260 were instantiating a template the
prompt handed them.

### User Input Inspector

[030]-[035] Domain Structure deletions; [036]+[042] the new toggle; [037]-[041]
the scoped parameter-list copy; [043]-[047] the labelling change; [048] OUT OF
RANGE; [049] SOFT TARGET example relabelled "Radius of propeller"; [050]-[052]
the USEFUL INPUT IMAGES example trimmed.

Plus, on the owner's instruction, **STRICT rules becomes three peer bullets** —
`calculate` conditional rule, Count countable features, SOFT TARGET. Today only
the first two are `- ` items and the last two are bare bold paragraphs that have
fallen out of the list. That is source-side residue from an earlier round, not a
PDF artifact.

### DC Input Creator

None. All three highlights withdrawn.

### DC Output Inspector

| id | action |
|---|---|
| [056] | empty `visual_inspection_guide_dc_output_inspector.md` (all 5 lines are highlighted). 0-byte fragments are an established pattern here — 6 already exist — and topology 5 has its own `_5agents` override, so it is unaffected |
| [057] | delete "and QC numbers from the CURRENT hand-off." — consistent with round 4 gating the QC affordances that `MESH_CHECKS=False` makes unreachable |
| [058] | close the hub parenthetical rather than strand it |
| [059] | keep "(The middle section has NO thickness, camber or high-point of its own.)", drop the interpolation clause |
| [060] | "Setting the parameter VALUES is not your job." |
| [061] | NO-OP — PDF rendering |
| [062] | end the **held** example at "…as it is now" — fixing the comma and the quote the raw cut would strand |

## Corrections forced by the adversarial re-check

An 11-agent re-check re-derived every edit from this record and attacked it.
Two claims above were WRONG and are corrected here; five decisions were added.

**WRONG 1 — "the UII stops seeing the parameters when the toggle is off."**
It does not. `PRIMER_AGENT_KEYS` (`agents/shared/dc_primer.py:71`) includes
`user_input_inspector`, and `user_input_inspector.py:214` injects the
DC-parameter primer on EVERY invoke with `DC_PARAMS_PRIMER_ENABLED` defaulting
True. The primer text carries verbatim the things the RED spans delete — the
middlePos radius formula, the `0.3-0.7` band, the `*MaxPos` "CAMBER crest only"
sentence and the ~30 %-chord sentence — plus all 16 names. **Decision: ship a
UII-specific primer TEXT** stripped of names, formulas and ranges, keeping the
geometry orientation. `dc_primer_messages` gains an agent key and
`_MESSAGE_CACHE` keys on (provider, agent); `primer_tokens_for` follows. The
DIAGRAM is unchanged and still carries parameter labels — owner accepted that.

**WRONG 2 — "an out-of-range value surfaces one hop later."**
True on the design path only. The Orchestrator's extraction-only branch forbids
the design run outright, so the UII's flag was the ONLY gate there. **Decision:
the branch changes** — see below — which puts the DCII back on that path and
closes the gap.

### Five decisions added after the re-check

1. **Receptionist keeps one range disclaimer.** Deleting the Parameter-name
   check also deletes `prompt.md:58-60` ("You do NOT check whether a value falls
   inside its allowed range…"), which round 4 CITED when it dropped
   "— including range comparisons —" from
   `hard_constraints_tools_receptionist.md`. One replacement sentence survives
   outside the block: *"You do not validate the user's numbers at the door —
   neither their names nor their ranges; the pipeline does that."*
2. **`dc_params_list` binds on every topology.** `Receptionist.set_tools`
   (`receptionist.py:110`) has no topology branch and one class serves the
   Orchestrator (7), Conductor (5) and Architect (3). Owner chose to accept the
   overlap rather than introduce the first topology-conditional tool binding.
   Topologies 5 and 3 gain a tool duplicating text already in their prompts.
3. **The two entry kinds are renamed and their trigger reworded.**
   "Verbatim entries" → **"Parameter-level entries"**; "Real-world-quantity
   entries" unchanged. The trigger stops being literal name-matching: a line
   qualifies when it *plainly denotes* a configurator parameter in that
   parameter's own unit, whatever words the user used — owner: *"If I write
   'average outer ring radius', it's obviously referring to impellerRadius."*
   Live surface: `dc_input_creator/prompt.md` (6 lines),
   `dc_input_inspector/prompt.md` (4), `modelling_notes_dc_input_creator.md`,
   `modelling_notes_dc_input_inspector.md`,
   `agents/orchestrator/role4_feedback_instructions.md`. Topology 5's copies
   stay frozen. **This supersedes "the DC Input Creator gets ZERO edits".**
4. **The Orchestrator's extraction-only list loses the DCIC and DCII.** Owner:
   *"The design creation is done by Tool Caller, and then completed by the DCOI
   by visualizing the renders. This is what we do not want. The DCIC and DCII
   can just make calculations, create the parameters and report back."* The rule
   becomes a geometry prohibition with an explicit permission clause.
5. **The UII's sweep clause is reworded** — "a sentence naming the swept
   parameter(s) and their bounds" assumed both the labelling rule and the list.

### Defaults taken without a separate ruling

- **[041] keeps its range.** The span covers `radius = 4 + middlePos·(impellerRadius
  − 4) mm [0.3; 0.7]`; only the formula is cut, so middlePos is not the one entry
  of sixteen with no printed range. The same cut in
  `parameters_dc_input_inspector.md:28` and `parameters_tool_caller.md:14` left a
  double-space scar (`1 = tip;  [0.3; 0.7]`) — fixed in the same pass.
- **Setting name `UII_PARAMETER_LIST_ENABLED`, default False.**

### Mechanical repairs the re-check surfaced

- **Two EXISTING scoped UII fragments have no topology-5 override**, so editing
  them breaks the freeze: `structure_user_input_inspector.md` ([030]-[035]) and
  `hard_constraints_dc_user_input_inspector.md` (the "above" fix). Both need
  `agents/5agent/dc_config/*_5agents.md` pass-throughs holding the CURRENT text
  — as well as the new `parameters_user_input_inspector.md`. The record
  previously said "both new scoped files" and named only one; that was wrong on
  both count and kind.
- **`visualize_3d_model_tool` is NOT in `SCOPED_FRAGMENTS`**, so [005] cannot be
  scoped — a per-agent copy would be silently inert. It edits the shared file,
  which the topology-5 Receptionist also splices. Round 4 did the same thing
  knowingly; this round records it.
- **Stranded punctuation beyond the five already listed:** [001], [025],
  [031]-[035], [043], [045]/[046], [050]-[052], [057], [060].
- **Two new blank-line runs** in `receptionist/prompt.md` (after [004], and
  around [006]/[007]) must be collapsed.
- **The STRICT-rules restructure is one rewrite of `prompt.md:84-123`**, not a
  bullet-marker change: both bold paragraphs carry continuation prose, and the
  SOFT TARGET example already begins with `- `, so re-marking without
  re-indenting closes the list early.
- **Docs that go stale:** `agents/shared/dc_params_tool.py:6-7` ("The
  Receptionist and the UII keep the inline fragment and do NOT bind this tool" —
  both halves become false), `extra_utilities/docs/active/value_states_and_out_of_range.md:233`,
  and `extra_utilities/prompt_pdf/dump.py:161` which hand-replicates the
  Receptionist's bind order and would otherwise render the next review PDF
  without the new tool.

## Result — applied and verified 2026-08-26

| agent | before | after | delta |
|---|---|---|---|
| Receptionist | 20,376 | 16,164 | −4,212 |
| User Input Inspector | 17,800 | 14,400 | −3,400 |
| Planner | 21,325 | 20,013 | −1,312 |
| DC Output Inspector | 18,629 | 18,075 | −554 |
| Orchestrator | 17,310 | 16,900 | −410 |
| Tool Caller | 8,669 | 8,667 | −2 |
| DC Input Inspector | 17,757 | 17,838 | **+81** |
| DC Input Creator | 22,961 | 23,102 | **+141** |
| Database Handler | 22,780 | 22,780 | 0 |
| **TOTAL** | **167,607** | **157,939** | **−9,668 (−5.8 %)** |

The DCIC and DCII GREW: the "Parameter-level entries" trigger had to say more
than "matches exactly" did. Receptionist tools 6 → 7 (`dc_params_list`).

Verified: before/after `dump.json` across all nine agents in both RAG positions;
zero new residue against twelve patterns (unresolved `$slot` / `{slot}` /
`<<MARKER>>`, blank-line runs, empty code spans, bare `**`, empty bullets,
double em-dashes, stranded semicolons, empty parens, space-before-punctuation);
paren balance unchanged per prompt; **all seven topology-5 templates
byte-identical**; both new toggles exercised in both positions; five smoke
tests pass; pyflakes clean apart from one pre-existing unused `PIL` import.

### Topology-5 pass-throughs: FIVE, not three

The freeze needed two more than this document first said. A first
topology-5 assembly after the edits showed the Receptionist −44 and the DCOI
−97, both from SHARED files with no 5-agent override:

- `agents/5agent/tools_config/visualize_3d_model_5agents.md` — [005].
  `visualize_3d_model_tool` is not in `SCOPED_FRAGMENTS`, so a per-agent copy
  would have been inert; the topology override is the only lever.
- `agents/5agent/dc_config/parameters_dc_output_inspector_5agents.md` —
  [058]/[059] and the new `<<DCOI_RANGES_*>>` markers.

plus the three already planned (`structure_user_input_inspector_5agents.md`,
`hard_constraints_dc_user_input_inspector_5agents.md`,
`parameters_user_input_inspector_5agents.md`, the last holding the SHARED
`parameters.md` the 5-agent UII reads today).

**The lesson: "is this file scoped?" is the wrong question. The question is
"does topology 5 have an override for it?"** Round 4's rule — pass-throughs for
NEW scoped files — misses every EXISTING shared file an edit happens to touch.
Assemble topology 5 before and after; do not reason about it.

### Two pre-existing defects fixed in passing

- **`smoke_test_dc_primer.py` case 2 was failing at HEAD.** Round 4 split the
  `~30% chord` sentence and this fourth smoke test — not among the three round
  4 ran — still matched the pre-split wording. Re-locked to the two halves.
- **`1 = tip;  [0.3; 0.7]`** in `parameters_dc_input_inspector.md` and
  `parameters_tool_caller.md`: a stranded semicolon and double space left by an
  earlier cut of the same middlePos formula this round cuts for the UII.

### Left deliberately

The UII's `calculate` worked example still reads
`- outerCamber: 0.7 mm — test "is innerChord larger than 10 mm?"`. Those are
parameter names in an example of what a QUANTITATIVE INPUTS line looks like,
which is the behaviour [043]-[047] removes. It was not highlighted, and a user
may genuinely type "outerCamber", which the DCIC's Parameter-level branch now
explicitly covers — so it was left. Flagged to the owner; change it if the
example turns out to steer the UII back into parameter names.

## Traps carried into implementation

- **`dc_params_list` reads the shared `parameters.md` by hard-coded path**
  (`dc_params_tool.py:36`). Scoping that file per agent does NOT change what the
  tool returns — which is why the Receptionist's list moves to the tool while the
  UII's moves to a scoped copy. Two different mechanisms, deliberately.
- **A scoped file in the shared tree also reaches topology 5** when
  `agent_dir_name` matches. Both new scoped files this round need
  `agents/5agent/` pass-throughs.
- **Deleting a highlighted span often strands punctuation.** [015], [038], [058],
  [059] and [062] all exist only because the reviewer's span ends mid-clause. Round
  4 shipped this class of residue to production once; check every cut site.
- **[039] is a zero-text highlight** co-located with [038]. Read as the
  un-highlighted first half of the same parenthetical, making [038]+[039] a clean
  whole-parenthetical delete. Not separately confirmed with the owner.
