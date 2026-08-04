# test11 v9 — system-prompt shrink proposal

Every change below is independently applicable. Pick by ID.

- `DELETE` remove outright · `COMPRESS` rewrite shorter · `MERGE` fold into another rule
- `REPLACE_WITH_EXAMPLES` swap a rule list for canonical examples · `SCOPE_PER_AGENT` keep for some agents only · `MOVE_TO_FRAGMENT` extract to a shared file
- Risk: **low** = mechanical · **medium** = behaviour could shift · **high** = removes a sole statement of an invariant
- ⚠️ on a row = an adversarial verifier flagged it. Read the flag before applying.

IDs are namespaced per agent (`RCP` Receptionist · `ORC` Orchestrator · `PLN` Planner · `UII` User Input Inspector · `DCIC` DC Input Creator · `DCII` DC Input Inspector · `TC` Tool Caller · `DCOI` DC Output Inspector · `DH` Database Handler). Several auditors independently used the same raw numbering, so each change also records the auditor's own id.

**Anchors checked against the working tree:** 349 cuts — 177 quote the file byte-for-byte, 172 match once dashes and whitespace are normalised (search loosely), 0 could not be located.

---

## 1. Where the tokens are

| Agent | now | proposed | cut | # changes |
|---|---:|---:|---:|---:|
| Receptionist | 9,193 | 3,379 | −63% | 32 |
| Orchestrator | 10,355 | 3,000 | −71% | 33 |
| Planner | 12,326 | 5,470 | −56% | 49 |
| User Input Inspector | 12,069 | 4,600 | −62% | 49 |
| DC Input Creator | 9,586 | 3,315 | −65% | 53 |
| DC Input Inspector | 11,447 | 2,500 | −78% | 29 |
| Tool Caller | 5,004 | 2,250 | −55% | 32 |
| DC Output Inspector | 11,505 | 2,400 | −79% | 39 |
| Database Handler | 5,505 | 1,740 | −68% | 33 |
| **TOTAL** | **86,990** | **28,654** | **−67%** | **349** |

Tool schemas (sent separately from the prompt text): **8,308 tokens** recoverable — see §3.
Cross-prompt duplication: **31,765 fleet tokens** recoverable — see §2.

---

## 2. Cross-prompt duplication (the biggest single lever)

| Block | tokens each | ×agents | fleet saving | verdict |
|---|---:|---:|---:|---|
| `Sketch handling guide` | 2152 | 3 | **4,596** | SCOPE_TO_SUBSET |
| `Generic constraints (the copy-pasted constitution)` | 842 | 8 | **3,840** | SHRINK_SHARED |
| `Value states (LOCKED / SOFT TARGET / FREE)` | 721 | 4 | **2,024** | SHRINK_SHARED |
| `Attempt-folder model + list_attempts/read_attempt narration` | 419 | 7 | **1,931** | SHRINK_SHARED |
| `Hard constraints - DC-specific` | 310 | 8 | **1,600** | SHRINK_SHARED |
| `Precision refine loop protocol` | 810 | 4 | **1,400** | SHRINK_SHARED |
| `Hard constraints - tool-specific` | 313 | 8 | **1,344** | SHRINK_SHARED |
| `Blade-sections visualizer blurb` | 185 | 9 | **1,315** | SCOPE_TO_SUBSET |
| `Sketch notes (propeller drawing artifacts)` | 427 | 3 | **1,281** | DELETE_EVERYWHERE |
| `The 16-parameter list with ranges` | 387 | 7 | **1,099** | KEEP |
| `Modelling notes` | 665 | 2 | **1,020** | SHRINK_SHARED |
| `User-input tool inventory (list_input_files / read_input_text / read_image_notes / view_images / ocr_regions)` | 341 | 4 | **1,004** | SHRINK_SHARED |
| `Hand-off label triplet protocol` | 262 | 6 | **970** | SHRINK_SHARED |
| `Anti-hallucination rule sets (on top of the shared fragment)` | 316 | 4 | **864** | SCOPE_TO_SUBSET |
| `Orchestrator's three overlapping agent rosters` | 1060 | 1 | **860** | SHRINK_SHARED |
| `Available agents roster` | 508 | 2 | **816** | SCOPE_TO_SUBSET |
| `Real-world-quantity handling (three routes)` | 580 | 2 | **760** | SHRINK_SHARED |
| `visualize_3d_model + propose_attempt tool prose` | 828 | 1 | **648** | SHRINK_SHARED |
| `eos feedback intro/outro + per-agent scope` | 130 | 7 | **595** | SHRINK_SHARED |
| `Extraction-only request handling` | 196 | 4 | **504** | SHRINK_SHARED |
| `Range-check instruction` | 437 | 3 | **486** | SHRINK_SHARED |
| `Capabilities CAN / CANNOT lists` | 390 | 2 | **480** | SHRINK_SHARED |
| `Domain structure` | 192 | 2 | **384** | DELETE_EVERYWHERE |
| `Geometry modification rule` | 178 | 2 | **356** | DELETE_EVERYWHERE |
| `'*Thickness / *Camber are ratios of the section's own chord'` | 155 | 3 | **314** | SHRINK_SHARED |
| `Pipeline flow` | 266 | 2 | **312** | SHRINK_SHARED |
| `Invalid parameter examples` | 99 | 3 | **297** | DELETE_EVERYWHERE |
| `'When to (re-)call read_parameters'` | 140 | 2 | **280** | DELETE_EVERYWHERE |
| `'Relay directives at full strength'` | 200 | 2 | **280** | SHRINK_SHARED |
| `Qualitative-to-quantitative hints` | 72 | 2 | **0** | KEEP |
| `database_search + retrieve_user_inputs + retrieve_attempt (RAG-gated)` | 941 | 8 | **0** | SHRINK_SHARED |

### D — `Sketch handling guide` → SCOPE_TO_SUBSET  (−4,596 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/DC_prompt_fragments/dc_config/user_input_types/sketch_handling.md` · *carried by:* user_input_inspector, dc_input_inspector, dc_output_inspector

Biggest single duplication in the fleet. ~65% of this file is UII-AUTHORING instruction ('UII responsibility - record the sketch's precision', 'UII - add a warm-start estimate + a crop region', 'Judging a sketch's precision'). The DCII and DCOI carry ~1,450 tok each telling the UII how to do its job. SPLIT: keep the full file (shrunk) for the UII only as sketch_handling_uii.md; give DCII + DCOI a new shared sketch_matching_core.md, verbatim:

### Reference images (sketches)
A user reference image can be anything from a rough doodle to a measured
drawing.  The UII records which it is - and, for a precise section drawing, a
``SUGGESTED SECTION SHAPES`` estimate and a ``SKETCH CROP REGION`` box - in the
extraction's DESIGN INTENT.  Read that and match at the strictness it states.

- ROUGH -> match layout, structure and broad proportions.  Asymmetry, line
  wobble, an off-centre hub, uneven ring thickness and per-blade curvature
  differences are drawing artifacts; never chase them, and never order another
  cycle when they are the only remaining mismatch - that design is CONVERGED.
- PRECISE -> reproduce the drawn proportions as closely as the 16 parameters
  allow; a real deviation from a deliberately-precise proportion IS a defect
  worth a revision.  Say plainly what could not be captured.
- Always: honour the INTENDED geometry, never literal pixels.  Blade COUNT is
  the exception to 'rough' - count it and trust it, unless the user states a
  count in words or a '×N' label, which wins over the number drawn.
- On a filled-in FORM, only the user's handwritten marks are input; the printed
  guide circles, min/max callouts, scales, grids and labels are scaffolding -
  never read a printed guide value or enforce a printed range as the user's.

(~230 tok.)  RISK FLAG: the 'do not chase sketch imperfections / that is
CONVERGED' rule and the form-scaffolding rule are both load-bearing (they stop
infinite refine loops and the Ø160-vs-Ø140 misread); both are preserved above.
Savings = (2152-230) x 2 agents + (2152->1400) on the UII.

### D — `Generic constraints (the copy-pasted constitution)` → SHRINK_SHARED  (−3,840 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/agents/shared/prompt_fragments/generic_constraints.md` · *carried by:* receptionist, orchestrator, planner, user_input_inspector, dc_input_creator, dc_input_inspector, tool_caller, dc_output_inspector

842 tok for chain agents / 494 for Receptionist+Orchestrator (CHAIN_ONLY stripped). Replace the whole file with:

### Rules every agent inherits
- **Routing is a tool call.**  Text you emit without invoking a routing tool
  (``call_<agent>``) is discarded and the pipeline halts - the prose in that
  tool's ``message`` argument IS the hand-off.  Invoke it in the same response
  where you finish your work; never merely announce it.  (Exceptions: the
  Receptionist's direct user replies and the Orchestrator's final wrap-up.)
- **Source every statement** to a tool result, an agent's history, or what the
  user literally said.  Never describe an artifact you did not see produced,
  and never invent tools, files, scripts, fallback policies, confidence scores
  or version numbers.  If your bound tools cannot do it, ESCALATE.
- **Never repeat a call.**  About to call the same tool with the same arguments
  you already used this turn?  STOP and ESCALATE.
<<CHAIN_ONLY>>- **Carry STANDING DIRECTIVES verbatim.**  Reproduce any
  ``=== STANDING DIRECTIVES ... ===`` block from your hand-off UNCHANGED in your
  own; write your own prose around it.  Only the Planner may set or change one.
- **Escalate, don't bounce or retry.**  On success forward to your natural next
  agent; send anything you cannot fix - permissions, a repeated class of
  failure, a still-ambiguous hand-off - to the Orchestrator, never back down
  the chain.  The Receptionist writes the user's wording, not you.
<</CHAIN_ONLY>>- Write hand-offs as prose carrying only what the recipient needs,
  in English, naming the authorship of any non-user value ('the Planner
  directed...', 'the user asked...').

(~300 tok chain / ~200 non-chain.)  All four documented production failures are
preserved: routing-halt, fabricated observations, invented tools, directive
relay.  Savings = 542 x 6 chain + 294 x 2 non-chain.

### D — `Value states (LOCKED / SOFT TARGET / FREE)` → SHRINK_SHARED  (−2,024 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/agents/shared/prompt_fragments/value_states.md` · *carried by:* planner, dc_input_creator, dc_input_inspector, dc_output_inspector

Load-bearing concept, over-explained: source (C) explicitly describes an annotation that 'today' is not written any more, and half the text argues against a 'ritual re-confirmation' failure. Replace with:

Read each value's state off the extraction's QUANTITATIVE INPUTS section:

- **LOCKED** - stated plainly, no marker.  Hold it verbatim unless an
  authorisation frees it.
- **SOFT TARGET** - marked ``SOFT TARGET (goal: ...; keep near ... if free)``.
  The marker IS the authorisation: the goal governs, so move the value within
  range as far as the goal requires, from the first attempt, without justifying
  it.  Fall back to the stated number only where the goal does not bear on that
  parameter, as closely as the 'keep near ... if free' strength asks.
- **FREE** - absent from QUANTITATIVE INPUTS (never given, or released).  Your
  choice within range.  A qualitative description you must turn into a number is
  FREE for that parameter too.

**Freeing a LOCKED value.**  ONE source is enough and no re-confirmation is ever
required: an authorisation named in the incoming hand-off (a user permission,
with any scope it carries, or a Planner directive), or one recorded in the
extraction's DESIGN INTENT.  How far it may then move follows the wording -
'as needed / only if necessary' = the smallest change that restores viability;
'freely / as much as possible', or nothing said = as far as the goal requires,
bounded by range.

(~215 tok.)  Additionally consider SCOPE: the DCOI only ever uses the SOFT
TARGET bullet (it judges renders, it does not move values) - a 60-tok extract
would do there, worth a further ~155 tok.

### D — `Attempt-folder model + list_attempts/read_attempt narration` → SHRINK_SHARED  (−1,931 fleet tokens)

*Source:* `agents/{orchestrator,planner,dc_input_creator,user_input_inspector,tool_caller,dc_output_inspector,receptionist}/prompt.md + DC_prompt_fragments/dc_config/output_file_locations.md` · *carried by:* receptionist, orchestrator, planner, user_input_inspector, dc_input_creator, tool_caller, dc_output_inspector

Seven prompts independently re-explain the same object model (folder layout, canonical filenames, append-only, who creates it, what the two tools return): Orchestrator 443, Planner 662, DCIC 754, UII 417, TC 272, DCOI 125, Receptionist ~350 of its 800 - plus output_file_locations.md at 419 x 2 and a third restatement in hard_constraints_tools. Create ONE attempts_model.md spliced into all seven and DELETE output_file_locations.md:

### Attempt folders
Every generation lives in one folder under ``logs/attempts/`` holding that
cycle's ``parameters.json``, ``propeller_mesh.obj`` and ``render_isometric.png``
/ ``render_top.png`` / ``render_side.png``, plus an optional
``description.txt``.  A folder may be partial.  Parameters and mesh are
append-only - never rewritten; existing renders are reused in place, so
re-rendering an attempt needs no new folder.  There is no 'current parameters'
location anywhere else in the project.  The DCIC opens the folder (the
Orchestrator only as a fallback when the DCIC cannot); everyone else writes into
the path on their hand-off's ``Current attempt:`` line.  ``list_attempts()``
numbers every folder and the roles it holds; ``read_attempt(n, file)`` returns
one file's text, or an absolute path for an image or mesh.

(~130 tok.)  Each agent then keeps ONLY its own delta: DCIC its
one-attempt-per-generation + no-op-write ban (~380), Planner its four
'use-sparingly' triggers (~300), Receptionist its Attempts-this-cycle reporting
procedure (~450), Orchestrator its Current-attempt propagation exception (~120),
UII/TC/DCOI ~40-120 each.

### D — `Hard constraints - DC-specific` → SHRINK_SHARED  (−1,600 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/DC_prompt_fragments/dc_config/hard_constraints_dc.md` · *carried by:* receptionist, orchestrator, planner, user_input_inspector, dc_input_creator, dc_input_inspector, tool_caller, dc_output_inspector

Four bullets, each of which is also stated somewhere else in the same assembled prompt (bullet 2 = geometry_modification_rule.md verbatim for the Orchestrator/DCOI and the Tool Caller's own HARD LIMITS; bullet 3 = capabilities_cannot.md for the Receptionist/Orchestrator; bullet 1 = invalid_parameter_examples.md). Replace with:

### Domain hard rules (every agent)
Geometry changes ONLY by changing the $parameter_count named parameters and
regenerating (DC Input Creator -> Tool Caller).  There is no mesh editing or
post-processing of any kind, no parameter outside the list (hub_radius,
fillet_radius, tip_clearance and friends do not exist - reject them, and treat
any agent that names a 'supplemental' parameter as hallucinating), no
alternative output formats / camera angles / cross-sections / resolutions, and
no performance, structural, or material analysis.  The only mesh metrics are
watertightness, volume and degenerate-face count; when mesh checks are off, say
so plainly and rely on visual inspection.

(~115 tok.)  This version absorbs invalid_parameter_examples.md entirely, which
is why that file can then be deleted from three prompts (separate row).

### D — `Precision refine loop protocol` → SHRINK_SHARED  (−1,400 fleet tokens)

*Source:* `agents/orchestrator/prompt.md + agents/planner/prompt.md + agents/dc_input_creator/prompt.md + agents/dc_output_inspector/prompt.md (in-prompt copy-paste, no fragment)` · *carried by:* orchestrator, planner, dc_input_creator, dc_output_inspector

~3,243 tok total (Orchestrator 420, Planner 744+403, DCIC ~330, DCOI 1,346) narrating ONE loop four times, each from its own seat. The decisive observation: the directive text itself is written by the Planner AT RUNTIME and rides the hand-offs verbatim - so the Orchestrator, DCIC and DCOI do not need the protocol pre-baked at all; they need only 'when a precision STANDING DIRECTIVE is in your hand-off, obey it and keep the loop turning'. Create precision_loop.md (~200 tok) spliced into all four:

### Precision refine loop
When a ``=== STANDING DIRECTIVES ... ===`` block in your hand-off declares a
PRECISION JOB, the cycle becomes a tight loop instead of a one-shot verdict:
DCOI compares the current render side-by-side with the user's sketch crop
(``view_images(..., side_by_side=True, regions=[<the UII's SKETCH CROP
REGION>])``), describes the visual shape gap in prose, and routes it back; the
Orchestrator relays that prose STRAIGHT to the DCIC (no re-plan); the DCIC moves
only UNLOCKED parameters toward the described gap and opens a fresh attempt each
round.  Nobody in the loop invents numbers for anyone else: the DCOI describes
what it sees, the DCIC owns the numbers.  The loop ends when the shapes match as
closely as the airfoil model allows, when two consecutive rounds stop improving
(a plateau), or when a ``PRECISION REFINE CAP REACHED`` note arrives - then the
DCOI reports the residual honestly (naming it as the model's limit, never as a
match) and the Planner approves.

Then cut: Orchestrator 420->100, DCIC 330->150, DCOI 1,346->450 (it keeps only
its own 'never approve the first sections render' + 3D-view bar), Planner
744+403->350 (it keeps authorship of the directive text, which is genuinely its
job).  RISK FLAG: 'must NOT approve the first render' is a real patch (the DCOI
rubber-stamped round 1) - it is retained in the DCOI's own 450 tok, not here.

### D — `Hard constraints - tool-specific` → SHRINK_SHARED  (−1,344 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/DC_prompt_fragments/tools_config/hard_constraints_tools.md` · *carried by:* receptionist, orchestrator, planner, user_input_inspector, dc_input_creator, dc_input_inspector, tool_caller, dc_output_inspector

Bullet 3 is a third statement of the attempt-folder model. Replace with:

### Tool-use hard rules (every agent)
- Read tools take ONLY paths a hand-off label gave you (``Input directory:``,
  ``Extracted inputs file:``, ``Parameters file:``, ``Render images:``,
  ``Current attempt:``) or an upstream tool's return value - never a guessed,
  shortened or reconstructed path.
- Route EVERY arithmetic operation through ``calculate`` - sums, ratios,
  conversions, range comparisons.  LLM mental arithmetic is unreliable even for
  trivial cases.  Batch this turn's expressions into ONE call; issue a second
  only when it genuinely depends on the first's result.
- Attempt folders are append-only (see 'Attempt folders'): write only into the
  ``Current attempt:`` folder, and to build on an old parameter set copy its
  values into a NEW attempt rather than editing the old one.

(~145 tok.)  RISK FLAG: keep the ``calculate`` bullet at full force - it is the
only thing standing between the DCII's per-parameter range check and LLM mental
arithmetic.

### D — `Blade-sections visualizer blurb` → SCOPE_TO_SUBSET  (−1,315 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/DC_prompt_fragments/tools_config/blade_sections_visualizer.md` · *carried by:* receptionist, orchestrator, planner, user_input_inspector, dc_input_creator, dc_input_inspector, tool_caller, dc_output_inspector, database_handler

Spliced into all NINE prompts, but only five agents can act on it: Planner (chooses a sections-first plan), Tool Caller (runs render_blade_sections), DCOI (views the image), DCIC (declares it in its hand-off), UII (flags a sections-centric request). DROP the $blade_sections_visualizer block entirely from the Receptionist, Orchestrator, DC Input Inspector and Database Handler (the DH's per-agent variant file is already empty - it is 185 tok of pure noise in a 5,505-tok prompt). For the five that keep it, shrink the shared blurb to:

### Blade-sections visualizer
The Tool Caller can render JUST the three blade cross-sections (Inner / Middle /
Outer, each at its true angle of attack) from an attempt's parameters file,
skipping the slow 3D mesh - so a section-focused request can be iterated cheaply
and the sections image can itself be the deliverable.

(~70 tok.)  Savings = 185 x 4 dropped + 115 x 5 shrunk.  The per-agent variants
(planner 400, dcoi 332, dcic 82, uii 70) stay - they carry the actual procedure.

### D — `Sketch notes (propeller drawing artifacts)` → DELETE_EVERYWHERE  (−1,281 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/DC_prompt_fragments/dc_config/user_input_types/sketch_notes.md` · *carried by:* user_input_inspector, dc_input_inspector, dc_output_inspector

Textbook golden-rule-2 laundry list: five enumerated instances of one principle ('drawn imperfection = artifact, not intent') - tips inside/outside the ring, off-centre oval hub, per-blade curvature variance, uneven ring thickness - plus the blade-count rule. Every instance is subsumed by the ROUGH bullet of the new sketch_matching_core.md above, and the blade-count rule (the only genuinely load-bearing one, and the only DISCRETE signal) is carried verbatim there. Delete the file and its $sketch_notes slot from all three prompts; add nothing else.

### D — `The 16-parameter list with ranges` → KEEP  (−1,099 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/DC_prompt_fragments/dc_config/parameters.md` · *carried by:* receptionist, orchestrator, planner, user_input_inspector, dc_input_creator, dc_input_inspector, tool_caller

STAYS INLINE in all seven per the owner's explicit decision - proposing removal or a lookup tool is out of bounds. Only the FORMAT changes: the current padded ASCII layout spends ~45% of its bytes on alignment whitespace and section headers. Compact form, verbatim:

Ring:  bladeCount int [3;6] . impellerRadius mm [60;80] . impellerThickness mm [1;5]
(Ring HEIGHT is not a parameter - it is derived to fit the outer blade section.)
Inner section (blade root, r = 4 mm):
  innerThickness %chord [3;24] . innerMaxPos tenths-of-chord int [2;8] .
  innerCamber %chord [0;9] . innerChord mm [3;11] . innerAngle deg [2;25]
Middle section:
  middlePos blade-span fraction [0.3;0.7] - radius = 4 + middlePos.(impellerRadius-4) mm,
  0 = root, 1 = tip; NOT middlePos x impellerRadius .
  middleChord mm [10;30] . middleAngle deg [2;25]
Outer section (tip, r = impellerRadius):
  outerThickness %chord [3;24] . outerMaxPos tenths-of-chord int [2;8] .
  outerCamber %chord [0;9] . outerChord mm [10;30] . outerAngle deg [2;25]
*Thickness and *Camber are percentages of THAT section's OWN chord, so a pinned
chord caps the section's absolute size in mm.  The middle section has no shape
parameters of its own - its profile is a weighted blend of inner and outer.

(~230 tok.)  Note this compact form now also carries the two real-bug gotchas
(the middlePos formula and the ratio-of-own-chord rule), which is what lets
structure.md and half of modelling_notes.md be deleted in other rows.  Savings =
157 x 7.

### D — `Modelling notes` → SHRINK_SHARED  (−1,020 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/DC_prompt_fragments/dc_config/modelling_notes.md` · *carried by:* dc_input_creator, dc_input_inspector

Three of its four sections duplicate the (compacted) parameter list: NACA/high-point definition, the middlePos formula (stated TWICE inside this one file), the integer rule. The 'Common unit-conversion patterns' block is a golden-rule-2 laundry list, and the 'Hard engineering blockers' section lists exactly ONE blocker - innerThickness/outerThickness <= 0 - which the declared range [3;24] already makes unreachable, yet the DCII is instructed to compute it via ``calculate`` every single cycle. Replace with:

### Modelling notes
Blade profiles are NACA-style airfoils: thickness and camber as % of that
section's own chord, high-point in tenths of chord from the leading edge.
bladeCount, innerMaxPos and outerMaxPos are integers; every other parameter is
floating point.
Conversions you will meet: mm <-> % of chord (thickness / camber, via that
section's chord), mm <-> tenths of chord (high-point - round after converting),
diameter <-> radius (impellerRadius = diameter / 2), a radius in mm <-> middlePos
(= (r - 4) / (impellerRadius - 4)).  For anything unfamiliar, derive the
conversion from the parameter list plus unit algebra, or fall back to
engineering judgement with a stated rationale.
No parameter COMBINATION breaks the geometry on its own - the declared ranges
already exclude the degenerate cases - so a clean per-parameter range check IS
the feasibility check.

(~155 tok.)  RISK FLAG: the last sentence deletes the DCII's 'hard blocker
inequalities' step. That is safe only while the blocker list stays at its
current single, range-unreachable entry - verify before applying, and if a real
blocker is ever added, re-add it here as one line.

### D — `User-input tool inventory (list_input_files / read_input_text / read_image_notes / view_images / ocr_regions)` → SHRINK_SHARED  (−1,004 fleet tokens)

*Source:* `agents/{user_input_inspector,dc_input_inspector,dc_output_inspector,planner}/prompt.md (in-prompt copy-paste)` · *carried by:* planner, user_input_inspector, dc_input_inspector, dc_output_inspector

Golden rule 9: this is tool mechanics restated in prose in four prompts (UII 345, DCII 390, DCOI 279, Planner 350) when every one of these tools already documents its own arguments in its schema. Create user_input_tools.md, spliced into the four:

### User-input tools (arguments are in each tool's schema)
``list_input_files()`` - every file under inputs/, with image<->note pairing
status . ``read_input_text(path)`` - one text file, e.g. a specific
``_note.txt`` . ``read_image_notes()`` - every note at once .
``view_images(paths)`` - load images; each arrives with its OCR text, and
``side_by_side=True`` plus ``regions`` builds one labelled composite for
comparison . ``ocr_regions(image_path, region_ids)`` - re-read faint or garbled
callouts at higher resolution; pass every region in ONE call.
Loading an image costs tokens: load one only when a visual judgement actually
changes your output, and re-load after a hand-off stripped the bytes.

(~115 tok.)  The per-agent 'when is it worth loading' judgement (DCII's
'strongest when a count disagrees with the image', DCOI's comparison-mode block)
stays where it is - only the mechanics move out.

### D — `Hand-off label triplet protocol` → SHRINK_SHARED  (−970 fleet tokens)

*Source:* `agents/{dc_input_creator,dc_input_inspector,tool_caller,user_input_inspector,dc_output_inspector,orchestrator}/prompt.md (in-prompt copy-paste)` · *carried by:* orchestrator, user_input_inspector, dc_input_creator, dc_input_inspector, tool_caller, dc_output_inspector

~1,570 tok across six prompts (DCIC 669, DCII 276, TC 264, Orchestrator ~180, UII ~120, DCOI ~60) narrating a fixed three-line format in natural language - the exact case golden rule 10 says to push into code. Best fix is structural: put the labels in the ``message`` argument's schema description on each ``call_<agent>`` routing tool. Interim prose fragment handoff_labels.md for the five chain agents:

### Hand-off labels
Every FORWARD in a design cycle carries, each on its own line, copied verbatim
from the tool return or the hand-off that gave it to you:

    Current attempt: <absolute attempt-folder path>
    Parameters file (newly written this cycle): <Current attempt>/parameters.json
    Extracted inputs file: <absolute path>

Include only the labels that exist at your step.  ``(newly written this cycle)``
means that file was just rewritten, so anything you remember from an earlier read
is STALE - re-read it before using it.  CLARIFY and ESCALATE messages carry no
path lines.

(~120 tok x 5 = 600.)  The Orchestrator keeps only its own exception (a NEW-
generation DCIC hand-off carries NO ``Current attempt:``), ~60 tok.

### D — `Anti-hallucination rule sets (on top of the shared fragment)` → SCOPE_TO_SUBSET  (−864 fleet tokens)

*Source:* `agents/{receptionist,orchestrator,planner,dc_output_inspector}/prompt.md` · *carried by:* receptionist, orchestrator, planner, dc_output_inspector

generic_constraints.md already gives all eight agents 'never fabricate an observation'. On top of it: Receptionist 614 tok, DCOI 334, Orchestrator 165 (six numbered rules), Planner 151 (five lettered rules A-E). The Orchestrator's and Planner's lists add nothing their own body text plus the shared fragment does not already say - rule 2 = capabilities_cannot, rule 4 = the shared fragment, rule 5 = 'the Receptionist composes wording' (shared fragment), A/D/E = the shared fragment. KEEP: the DCOI's image-specific version (a real production failure - it described renders it never loaded) and the Receptionist's 'you hold no artefacts at all' framing (also real). DELETE outright: the Orchestrator's ``## Anti-Hallucination Rules`` section (165) and the Planner's ``## Anti-Hallucination Rules`` section (151). SHRINK: Receptionist 614 -> ~220 (it currently makes the same point in four separately-headed paragraphs: never-invent, separate-what-you-inferred, no-second-guessing, decide-by-reasoning), DCOI 334 -> ~180 (drop the two verbatim replacement templates (a)/(b) - state the requirement, not the wording).

### D — `Orchestrator's three overlapping agent rosters` → SHRINK_SHARED  (−860 fleet tokens)

*Source:* `agents/orchestrator/prompt.md '## Agent Capabilities' (291) + $agent_tools_overview (523) + $tool_caller_capabilities (246)` · *carried by:* orchestrator

Single agent, but three separate who-does-what tables inside one prompt is the same defect at agent scale: '## Agent Capabilities - DO NOT exceed these' lists all seven agents; $agent_tools_overview lists all seven again with their tools; $tool_caller_capabilities describes the Tool Caller a THIRD time (and duplicates tool_inventory.md, which the Tool Caller itself already has). Collapse to one ~200-tok roster, one line per agent, naming only what the Orchestrator must not exceed. Concretely: delete the ``$tool_caller_capabilities`` slot from the Orchestrator (the roster line covers it), delete the ``## Agent Capabilities`` section, and shrink agent_tools_overview.md to one line per agent - dropping its 'Planner reads user_query.txt', 'You (Orchestrator)...' and 'Receptionist reads agent history' entries, all of which those agents' own prompts state.

### D — `Available agents roster` → SCOPE_TO_SUBSET  (−816 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/agents/shared/prompt_fragments/available_agents.md` · *carried by:* planner, database_handler

The Database Handler carries BOTH $available_agents (508) and $agent_tools_overview_brief (437) - two full rosters, 945 tok, in a 5,505-tok prompt, for an agent whose whole job is to ask each agent what it remembers. agent_tools_overview_brief.md is the one written for it (its own text says 'This fragment is consumed by the Database Handler only'). DROP $available_agents from the Database Handler entirely (-508). For the Planner, shrink to a one-line-per-agent roster (~200 tok) - the current text explains at length why the Planner may not call the Receptionist and what 'the only agent that interprets raw user content' means, which its own HARD RULES already cover (-308).

### D — `Real-world-quantity handling (three routes)` → SHRINK_SHARED  (−760 fleet tokens)

*Source:* `agents/dc_input_creator/prompt.md lines 71-117 + agents/dc_input_inspector/prompt.md lines 216-251` · *carried by:* dc_input_creator, dc_input_inspector

A mirrored pair: the DCIC gets 698 tok on 'conversion / judgement / decline' and the DCII gets 462 tok checking that one of those three was chosen - restating each route in full a second time. One shared fragment realworld_quantities.md:

### Real-world-quantity inputs
A QUANTITATIVE INPUTS line whose unit or frame does not match a configurator
parameter is still a real constraint.  The DCIC must take exactly one of three
routes and NAME it in the hand-off: (a) convert - pick the anchor parameter(s)
that supply the reference frame, solve via ``calculate``, round sensibly, verify
the result is in range, and state the quantity, the anchors, the formula and the
result; (b) engineering judgement - when a literal conversion would be
non-physical, near-boundary, or hides an ambiguity, choose values that honour the
intent and say why the conversion was not used; (c) decline - the entry does not
apply to the configurator at all (an RPM, a cost, a date), with a one-line
reason.  Silently omitting the entry, or defaulting an anchor to mid-range when
an unlocked anchor would have honoured the user's number, is the failure mode.
The DCII verifies that one of the three was taken and named, and that the written
values are consistent with it within a margin justified by the user's stated
precision; if the hand-off does not acknowledge the entry at all, CLARIFY back to
the DCIC - never escalate it to the user.

(~200 tok.)  The DCIC keeps its multi-parameter-constraint sub-rule (best-fit /
distribute / escalate, ~200 tok); the DCII keeps nothing further.

### D — `visualize_3d_model + propose_attempt tool prose` → SHRINK_SHARED  (−648 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/DC_prompt_fragments/tools_config/propose_attempt.md` · *carried by:* receptionist

828 tok (298 + 530) for two tools, in a single prompt, and BOTH files open by saying their mechanics 'are documented on the tool itself' before spending several hundred tokens on them anyway. The Receptionist's own '## Reporting attempts' section (800 tok) then narrates the same procedure a third time. Collapse both fragments into:

### Showing a model and proposing it
``visualize_3d_model(obj_path)`` shows an attempt's ``propeller_mesh.obj`` in the
web viewer - use ``<the attempt folder named in your hand-off>/
propeller_mesh.obj``.  It tells you nothing about how the mesh looks; never
describe or judge it.
``propose_attempt(values)`` pushes an attempt's full 16-parameter dict to the
Parameters Inputs panel as the system's proposed solution.  Take the values from
a ``read_attempt(n, 'parameters.json')`` result - never invent one, the user sees
the dict literally.  Call it ONLY when the hand-off ENDORSES the attempt
('recommend attempt N', 'the satisfying result') or the user asks directly;
hedging wording ('showing for context', 'not satisfying yet') means visualize but
do NOT touch the panel - it is sticky and must keep showing the last endorsed
proposal.  When both apply, visualize first, then propose, in the same turn.

(~180 tok.)  Both tools are permitted in Situation B because neither loops
control back into the system - state that once in the Situation B section, not
in each tool block.

### D — `eos feedback intro/outro + per-agent scope` → SHRINK_SHARED  (−595 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/agents/shared/prompt_fragments/eos_feedback_intro.md` · *carried by:* receptionist, planner, user_input_inspector, dc_input_creator, dc_input_inspector, tool_caller, dc_output_inspector

Two fragment files (71 tok) wrapping a hand-written ~55-tok 'For you, your scope is:' paragraph in each of seven prompts - and it is a READ-ONLY notice about a message that may or may not arrive. Merge the two files into one eos_feedback.md carrying an $eos_scope slot, verbatim:

At session end the Orchestrator may append one final ``HumanMessage``
(``name="orchestrator"``) carrying user feedback on your scope - $eos_scope.
Treat it as ground truth when answering the Database Handler.

and reduce each agent's scope text to a bare noun list (e.g. DCOI: 'your APPROVE
vs REVISE calls, your countable-feature checks, and whether every visual claim
was grounded in a this-turn image load'). ~45 tok assembled vs ~130 today.
Delete eos_feedback_outro.md.

### D — `Extraction-only request handling` → SHRINK_SHARED  (−504 fleet tokens)

*Source:* `agents/{receptionist,orchestrator,planner,user_input_inspector}/prompt.md` · *carried by:* receptionist, orchestrator, planner, user_input_inspector

784 tok across four prompts (Receptionist 340, Orchestrator 264, Planner 110, UII 70) making one point. The Receptionist's copy alone spends 130 tok re-explaining what the UII is for and telling itself not to say 'I cannot analyse images'. One fragment extraction_only.md:

### Extraction-only requests
'How many blades are in my sketch?' / 'what dimensions did you find?' /
'interpret this file' is a first-class request, not a design run: it goes through
the UII and STOPS there - the extraction IS the deliverable.  Never start a
generation for one (no DCIC / Tool Caller / DCOI), and never decline it because
it involves images.  The extraction is intentionally broader than the 16
parameters (material notes, aesthetics, anything with no parameter mapping) -
for this request type that breadth is exactly what the user wants.

(~70 tok x 4 = 280.)

### D — `Range-check instruction` → SHRINK_SHARED  (−486 fleet tokens)

*Source:* `agents/dc_input_creator/prompt.md 'Validate before you write' + agents/dc_input_inspector/prompt.md '1. Range validation (STRICT)' + agents/tool_caller/prompt.md 'Range check before you generate'` · *carried by:* dc_input_creator, dc_input_inspector, tool_caller

1,311 tok (DCIC 574, DCII 462, TC 275) saying the same thing three times, and each copy spends a paragraph JUSTIFYING why it is redundant with the other two (golden rule 7). One fragment range_check.md:

### Range check (independent, every time)
Compare EVERY parameter against its [min; max] individually - not a glance, and
not a blanket 'all $parameter_count are in bounds', which has waved strictly
out-of-range values through before.  Outside the range is a hard fail; exactly at
min or max is fine.  Batch the arithmetic into one ``calculate`` call.  This
check is deliberately redundant with the other agents' - nothing in the tooling
validates ranges, and an agent reviewing its own work misses what yours catches.

(~85 tok x 3.)  Each agent keeps only its own CONSEQUENCE: the DCIC its
authorisation-collision resolution (~300), the DCII its verdict->routing mapping
(~180), the TC its 'you do NOT fix it - route back to the author' (~90).  RISK
FLAG: the 'not a blanket assertion' clause is the DCII's blanket-approve patch -
it is kept verbatim above and must not be dropped further.

### D — `Capabilities CAN / CANNOT lists` → SHRINK_SHARED  (−480 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/DC_prompt_fragments/dc_config/capabilities_cannot.md` · *carried by:* receptionist, orchestrator

Two files (180 + 210) whose CANNOT list is a third statement of hard_constraints_dc bullets 2-3, which both agents also carry. Merge into one capabilities.md:

**CAN:** generate a propeller mesh (.obj) from the 16 parameters via
Grasshopper / RhinoCompute, render it from three fixed viewpoints (isometric,
top, side), report watertightness / volume / degenerate-face count when mesh
checks were enabled at startup, do arithmetic, answer questions about this
session's earlier runs by reading the agents' histories, and regenerate with
changed parameters (subject to the permission rules).

**CANNOT - never offer these as a next step:** any performance, aerodynamic,
hydrodynamic, structural, FEA, material or tolerance analysis; any mesh edit
after generation; any other output format, camera angle, cross-section,
tessellation density or resolution; file downloads, uploads or cloud storage -
outputs simply exist on disk at the reported paths.

(~145 tok.)

### D — `Domain structure` → DELETE_EVERYWHERE  (−384 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/DC_prompt_fragments/dc_config/structure.md` · *carried by:* user_input_inspector, dc_input_creator

Every fact in it is already in the compact parameter list proposed above, which both agents carry: hub radius 4 mm, the three sections, and the middlePos = blade-span-fraction formula (which structure.md states in full, a third time after parameters.md and modelling_notes.md). Delete the file, the $dc_structure slot, and the '## Domain Structure' heading from both prompts. No replacement text needed - conditional on the compact parameters.md being applied first.

### D — `Geometry modification rule` → DELETE_EVERYWHERE  (−356 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/DC_prompt_fragments/dc_config/geometry_modification_rule.md` · *carried by:* orchestrator, dc_output_inspector

A strictly weaker restatement of hard_constraints_dc bullets 1-2, which both agents already carry in the same assembled prompt - it enumerates eight mesh operations the DC rule already covers as a class. It also says '17 design parameters' THREE times while the system has had 16 since the impellerHeight removal, so it is actively wrong as well as redundant. Delete the file and the $geometry_modification_rule slot from both prompts; the DCOI's '## HARD RULES - what you must NEVER suggest' heading then attaches directly to its own next paragraph ('Setting the parameter VALUES is not your job'), which is the part that is actually DCOI-specific.

### D — `'*Thickness / *Camber are ratios of the section's own chord'` → SHRINK_SHARED  (−314 fleet tokens)

*Source:* `agents/dc_output_inspector/prompt.md lines 317-340 + agents/dc_input_creator/prompt.md lines 162-167 + agents/planner/prompt.md (inside the PRECISION JOB directive text)` · *carried by:* planner, dc_input_creator, dc_output_inspector

A genuine production bug (a pinned chord capped absolute size), so it must survive - but it currently costs 464 tok across three prompts, the DCOI's copy alone running 328 tok with a three-way worked example. The definition now lives in the compact parameter list (all seven parameter-carrying agents get it free). The behavioural half becomes one shared note for the DCIC + DCOI:

``*Thickness`` and ``*Camber`` are RATIOS of that section's own chord, so a
pinned chord caps how big the section can get in mm, and 'make it thicker' /
'keep the thickness as it is' has two opposite readings the moment the chord
moves.  Whenever you ask for - or apply - such a change, say in one clause which
you mean: the ratio, or the size in millimetres.  The blade-sections render
reports both numbers per section, so you can always tell which one is off.

(~75 tok x 2.)

### D — `Pipeline flow` → SHRINK_SHARED  (−312 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/agents/shared/prompt_fragments/pipeline_flow_uii_first.md` · *carried by:* orchestrator, planner

The chain diagram earns its place; the three paragraphs after it restate it in prose, and the Orchestrator immediately restates it AGAIN in its own next paragraph ('You KICK OFF the chain by calling the User Input Inspector...'). Replace with:

The pipeline is a horizontal chain; each agent forwards to the next by default:

  user -> Receptionist -> Orchestrator -> User Input Inspector -> Planner ->
  DC Input Creator -> <<DCII_ONLY>>DC Input Inspector -> <</DCII_ONLY>>Tool Caller ->
  DC Output Inspector -> Orchestrator -> Planner -> Receptionist -> user

The UII runs FIRST and writes ``extracted_inputs.txt`` before the Planner sees
the request.  Any agent may escalate to the Orchestrator, which calls the Planner
for a recovery Sequence; the Orchestrator then executes that Sequence one agent
at a time and the forward chain is NOT re-entered.

(~110 tok x 2.)

### D — `Invalid parameter examples` → DELETE_EVERYWHERE  (−297 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/DC_prompt_fragments/dc_config/invalid_parameter_examples.md` · *carried by:* receptionist, orchestrator, planner

Absorbed word-for-word into the shortened hard_constraints_dc.md above ('no parameter outside the list - hub_radius, fillet_radius, tip_clearance and friends do not exist - reject them, and treat any agent that names a supplemental parameter as hallucinating'), which all three agents carry anyway. Delete the file and the $invalid_parameter_examples slot from all three. Conditional on the hard_constraints_dc rewrite being applied first; if the owner declines that one, KEEP this instead - the 'supplemental parameter' rejection is load-bearing.

### D — `'When to (re-)call read_parameters'` → DELETE_EVERYWHERE  (−280 fleet tokens)

*Source:* `agents/dc_input_inspector/prompt.md lines 73-84 + agents/tool_caller/prompt.md lines 46-56` · *carried by:* dc_input_inspector, tool_caller

Two near-verbatim copies of the same three bullets ('newly written this cycle means stale', 'when in doubt re-read', 'you may rely on a cached read only when certain'). Fully subsumed by the one sentence already in the handoff_labels.md replacement above ('``(newly written this cycle)`` means that file was just rewritten, so anything you remember from an earlier read is STALE - re-read it before using it'). Delete both blocks; keep each agent's one-line 'do not call it with a guessed path - if the line is missing, ESCALATE'.

### D — `'Relay directives at full strength'` → SHRINK_SHARED  (−280 fleet tokens)

*Source:* `agents/receptionist/prompt.md lines 108-115 + agents/orchestrator/prompt.md lines 161-182` · *carried by:* receptionist, orchestrator

399 tok for one rule stated twice, the Orchestrator's copy including a 60-tok worked example of the exact sentence to write. One fragment relay_force.md:

### Relay directives at full strength
When the user (or the Planner) writes MUST / REQUIRED / MANDATORY / 'do not
skip', carry that same force downstream ('the user has MANDATED that...').
Never soften it to 'emphasizes', 'leveraging', 'would like', 'should consider'.
The recipient never sees the original wording - what you write IS what they see,
and a softened directive gets ignored.  The same holds for constraints,
exclusions, scope limits, authorisations and refusals.

(~60 tok x 2.)

### D — `Qualitative-to-quantitative hints` → KEEP  (−0 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/DC_prompt_fragments/dc_config/qualitative_examples.md` · *carried by:* user_input_inspector, dc_input_creator

Keep as-is in both. This is already exactly what golden rule 2 prescribes - five canonical examples standing in for an open-ended mapping problem, at 72 tok. It is the highest-value-per-token fragment in the fleet and the only place the qualitative->numeric direction convention is anchored. Do not touch it.

### D — `database_search + retrieve_user_inputs + retrieve_attempt (RAG-gated)` → SHRINK_SHARED  (−0 fleet tokens)

*Source:* `C:/Users/vince/MT Coding/tests/test11_v9_git/.claude/worktrees/admiring-austin-d46925/DC_prompt_fragments/tools_config/database_search.md` · *carried by:* receptionist, orchestrator, planner, user_input_inspector, dc_input_creator, dc_input_inspector, tool_caller, dc_output_inspector

ZERO saving at the measured baseline - RAG_ENABLED=False strips every <<HAS_DBA>> region, which is why the 102,639-tok figure does not contain it. Reported here because it is the largest LATENT duplication in the tree: with RAG on, database_search.md (758) + retrieve_user_inputs.md (183) lands in all eight chain agents = 7,528 tok, plus 1,324 tok of per-agent variants, four of which (dc_input_creator / dc_input_inspector / dc_output_inspector, and orchestrator vs tool_caller which are BYTE-IDENTICAL) are the same 'the Planner's instructions still take priority; prefer retrieve_* with images_flag=True' paragraph reworded. When RAG is next enabled, shrink database_search.md to ~180 tok - keep only the TAKE/LEAVE-BEHIND principle ('past sessions are a blueprint for HOW to act, never values to copy'; 'fetch the pixels before trusting a visual claim') and drop the argument/return-shape prose, which the tool schema already carries - and merge the three identical per-agent variants into one. Estimated 4,624 tok saved in the RAG-on configuration.

### Restructure plan

HOW THE FRAGMENT LAYER SHOULD BE ORGANISED

Diagnosis. The tree has 40 fragments but no notion of WHO NEEDS WHAT. Four fragments (generic_constraints, hard_constraints_dc, hard_constraints_tools, blade_sections_visualizer) are spliced into 8-9 prompts each purely because they were written as "shared", and they alone account for ~13,300 of the 87,001 prompt tokens. Meanwhile the genuinely cross-cutting material - the attempt-folder object model, the hand-off label triplet, the user-input tool inventory, the range check, the precision loop, the extraction-only rule - has NO fragment at all and is copy-pasted as prose into 3-7 prompt.md files each (~9,000 tok). The layer is inverted: what is shared isn't factored, and what is factored isn't needed everywhere.

Proposed organisation - three tiers, by who actually needs the text.

TIER 1 - UNIVERSAL (every agent, must total < 500 tok assembled)
  KEEP + SHRINK   agents/shared/prompt_fragments/generic_constraints.md   842/494 -> 300/200
  KEEP + SHRINK   DC_prompt_fragments/dc_config/hard_constraints_dc.md     310 -> 115
  KEEP + SHRINK   DC_prompt_fragments/tools_config/hard_constraints_tools.md 313 -> 145
  DELETE          dc_config/invalid_parameter_examples.md   (absorbed into hard_constraints_dc)
  DELETE          dc_config/geometry_modification_rule.md   (weaker restatement of the same; also says "17 parameters")

TIER 2 - ROLE FRAGMENTS (new files; spliced only into the agents that act on them)
  CREATE  dc_config/attempts_model.md            ~130 tok -> recep, orch, planner, uii, dcic, tc, dcoi
          (absorbs and DELETES dc_config/output_file_locations.md and hard_constraints_tools bullet 3)
  CREATE  shared/prompt_fragments/handoff_labels.md   ~120 -> uii, dcic, dcii, tc, dcoi
  CREATE  tools_config/user_input_tools.md       ~115 -> planner, uii, dcii, dcoi
  CREATE  shared/prompt_fragments/range_check.md ~85  -> dcic, dcii, tc
  CREATE  shared/prompt_fragments/precision_loop.md ~200 -> orch, planner, dcic, dcoi
  CREATE  shared/prompt_fragments/extraction_only.md ~70 -> recep, orch, planner, uii
  CREATE  shared/prompt_fragments/relay_force.md ~60  -> recep, orch
  CREATE  dc_config/realworld_quantities.md      ~200 -> dcic, dcii
  CREATE  dc_config/section_ratios.md            ~75  -> dcic, dcoi   (the *Thickness/*Camber gotcha)
  CREATE  dc_config/capabilities.md              ~145 -> recep, orch  (merges capabilities_can + capabilities_cannot; DELETE both)
  SPLIT   user_input_types/sketch_handling.md  ->
            sketch_handling_uii.md   ~1,400 -> uii only
            sketch_matching_core.md    ~230 -> dcii, dcoi
          DELETE user_input_types/sketch_notes.md (folded into the core)
  SHRINK  shared/prompt_fragments/value_states.md 721 -> 215 (planner, dcic, dcii, dcoi)
  SHRINK  dc_config/modelling_notes.md            665 -> 155 (dcic, dcii)
  MERGE   eos_feedback_intro.md + eos_feedback_outro.md -> eos_feedback.md with an $eos_scope slot; DELETE the outro

TIER 3 - AGENT-EXCLUSIVE (one consumer; live in the agent's own prompt.md, not the shared tree)
  DELETE  dc_config/structure.md          (absorbed by the compacted parameter list)
  DROP    $available_agents from database_handler (it already has agent_tools_overview_brief)
  DROP    $blade_sections_visualizer from recep, orch, dcii, database_handler
  DROP    $tool_caller_capabilities from orchestrator; collapse its three rosters into one
  MERGE   tools_config/visualize_3d_model.md + propose_attempt.md -> one ~180-tok receptionist_display_tools.md
  DELETE  tools_config/tool_caller_instructions.md, tools_config/retrieve_attempt.md,
          tools_config/blade_sections_visualizer_tool_caller.md   (all three are 0 bytes today - dead slots)

THE 16-PARAMETER LIST stays inline in all seven agents that have it, per the owner. Only its FORMAT changes (387 -> 230 tok), and the compacted form deliberately absorbs the three real-bug gotchas - hub-4 mm / middlePos-is-a-span-fraction, *Thickness-and-*Camber-are-ratios-of-own-chord, and the middle section having no shape parameters of its own - which is precisely what lets structure.md be deleted and modelling_notes.md be cut by 77%.

TWO STRUCTURAL MOVES THAT BEAT ANY PROSE EDIT (golden rules 9 and 10)
1. Put the hand-off labels in the routing tools' schemas. Six prompts spend ~1,570 tok narrating "your message MUST include these three lines". That is a contract, and a contract belongs in the `message` argument's schema description on each `call_<agent>` tool - where the model reads it as a requirement rather than as advice, and where it costs one copy instead of six.
2. Audit the tool SETS, not just the prose. 15,638 tok of tool schemas across 9 agents, and the Planner carries 14 tools while the Tool Caller - the only agent that actually builds anything - carries 9. Every agent holds `list_attempts` + `read_attempt`, which is why seven prompts had to grow an attempt-folder paragraph to explain when NOT to use them. Removing those two tools from the agents that have no legitimate reason to inspect history (Receptionist beyond its reporting path, UII, TC) would let the corresponding prose go too.

MECHANICS (do not skip). Every new fragment needs (a) a `_read_dc_fragment` / `_read_generic_fragment` constant plus a `_build_slots` entry in agents/shared/prompts.py, and (b) a matching row in that file's FRAGMENT_TO_SLOT dict - the System Prompts UI's "used by N agents" badge and its $-slot validator both read it. Deleting a fragment means removing its FRAGMENT_TO_SLOT row and its `$slot` reference from every prompt.md in the same commit, or template substitution silently leaves the literal `$slot` text in the assembled prompt. Also check agents/5agent/: it overrides generic_constraints, hard_constraints_dc, hard_constraints_tools, available_agents, eos_feedback_intro and pipeline_flow by filename - each of those six shrinks needs its 5-agent twin updated or the two topologies will drift apart.

SEQUENCING. Apply in this order so the conditional rows stay valid: (1) compact parameters.md; (2) then structure.md and modelling_notes.md can be cut; (3) shorten hard_constraints_dc.md; (4) then invalid_parameter_examples.md and geometry_modification_rule.md can be deleted. Rows 1-4 of the census (sketch handling, sketch notes, generic constraints, value states) are independent of everything and are worth ~11,700 tok on their own - start there.

VERIFY BY TESTING, NOT BY QUOTA. Six rules in this census are documented patches for real production failures: routing-is-a-tool-call, never-describe-images-you-did-not-load, the DCII's per-parameter range check, the standing-directive relay, the blade-count-is-authoritative rule, and the "do not chase sketch imperfections - that is CONVERGED" stop condition. Each is preserved verbatim in the replacement text above; if a benchmark regression appears after a cut, check those six first before restoring anything else.

HONEST FLEET SAVING: ~31,800 of 87,001 prompt tokens (36.5%) from duplication alone, in the measured configuration (RAG off). A further ~4,600 is latent behind the RAG flag. This census does NOT touch agent-unique prose - the Planner's HARD RULES (1,682), the Orchestrator's completing-a-cycle section (1,315), the UII's temporal-scope rules (1,035), the Receptionist's reporting-attempts procedure (800) - which is where the remaining distance to the 1,000-3,000-tok-per-agent target has to come from.

---

## 3. Tool-schema pruning (golden rule 9)

| Tool | now | ×agents | fleet saving | risk | source |
|---|---:|---:|---:|---|---|
| `calculate` | 329 | 8 | **1,600** | low | `tools/calculate/calculate.py:13-37 (Annotated description + docstring)` |
| `view_images` | 544 | 4 | **1,068** | medium | `agents/shared/user_inputs_tool.py:115-148 (_VIEW_IMAGES_BASE_DOC 115-139, _VIEW_IMAGES_OCR_DOC 141-148)` |
| `read_attempt` | 263 | 8 | **1,048** | medium | `agents/shared/attempts_tool.py:206-226` |
| `list_attempts` | 200 | 8 | **832** | low | `agents/shared/attempts_tool.py:162-176` |
| `ocr_regions` | 266 | 4 | **552** | low | `agents/shared/user_inputs_tool.py:173-189 (_OCR_REGIONS_DOC)` |
| `read_input_text` | 104 | 6 | **414** | low | `agents/shared/user_inputs_tool.py:96-103` |
| `call_<agent> routing tools (10 descriptions, 24 live bindings)` | 840 | 8 | **384** | medium | `agents/shared/routing_tools.py:179-236 (_TOOL_DESCRIPTIONS)` |
| `generate_and_render_propeller` | 883 | 1 | **378** | medium | `tools/generate_mesh/generate_mesh.py:611-618 (output_dir Annotated) + 636-663 (docstring)` |
| `list_input_files` | 116 | 5 | **350** | low | `agents/shared/user_inputs_tool.py:84-90` |
| `new_attempt` | 277 | 2 | **342** | low | `agents/shared/attempts_tool.py:311-332` |
| `propose_attempt` | 427 | 1 | **262** | low | `agents/receptionist/propose_attempt_tool.py:87-121` |
| `read_agent_history` | 204 | 3 | **246** | low | `agents/shared/history_tool.py:19-34 (_TOOL_DESCRIPTION)` |
| `read_image_notes` | 80 | 4 | **172** | low | `agents/shared/user_inputs_tool.py:107-111` |
| `render_blade_sections` | 318 | 1 | **141** | low | `tools/render_blade_sections/render_blade_sections.py:47-71` |
| `write_parameters` | 257 | 1 | **114** | low | `agents/dc_input_creator/dc_input_creator.py:89-108` |
| `read_extracted_inputs (Planner copy)` | 145 | 1 | **93** | low | `agents/planner/planner.py:96-107` |
| `visualize_3d_model` | 181 | 1 | **91** | low | `tools/visualize_model/visualize_model.py:29-46` |
| `read_user_inputs` | 160 | 1 | **54** | low | `agents/user_input_inspector/user_input_inspector.py:75-85 (_READ_INPUTS_DOC)` |
| `read_parameters (2 separate copies)` | 127 | 2 | **51** | low | `agents/dc_input_inspector/dc_input_inspector.py:73-78 and agents/tool_caller/tool_caller.py:75-79` |
| `read_user_queries` | 115 | 1 | **50** | low | `agents/planner/planner.py:121-130` |
| `read_extracted_inputs (DCIC + DCII copies)` | 141 | 2 | **49** | low | `agents/dc_input_creator/dc_input_creator.py:78-83 and agents/dc_input_inspector/dc_input_inspector.py:84-89` |
| `write_extraction` | 89 | 1 | **17** | low | `agents/user_input_inspector/user_input_inspector.py:105-111` |

### T — `calculate`  (329 → ~129 tok, ×8 agents)

*Replace the docstring at `tools/calculate/calculate.py:13-37 (Annotated description + docstring)` with:*

```
    expressions: Annotated[
        list[str],
        "Python expressions to evaluate, e.g. ['25.4 * 3 + 10', '20 / 75', "
        "'8.0 >= 3 and 8.0 <= 11', 'abs(-7) + min(2, 5)'].  Python syntax "
        "only ('and'/'or'/'not', never '&&'/'||'/'!'); available functions: "
        "abs, round, min, max.",
    ],
) -> str:
    """Evaluate arithmetic / boolean expressions.

    Returns one line per expression, in input order: ``<expr> = <result>``,
    or ``<expr> -> error: <message>`` when one fails.
    """
```

### T — `view_images`  (544 → ~298 tok, ×4 agents)

*Replace the docstring at `agents/shared/user_inputs_tool.py:115-148 (_VIEW_IMAGES_BASE_DOC 115-139, _VIEW_IMAGES_OCR_DOC 141-148)` with:*

```
_VIEW_IMAGES_BASE_DOC = (
    "View images — user sketches (under ``inputs/``) and/or tool renders (under "
    "``attempts/``), interchangeably.  They are attached in the next user "
    "message, each preceded by its absolute path.\n\n"
    "``paths``: list of absolute ``.png`` / ``.jpg`` / ``.jpeg`` paths.\n"
    "``side_by_side`` (default False): merge up to THREE images into ONE "
    "labelled composite for direct comparison; pass more than 3 paths only "
    "with False.\n"
    "``layout`` (``'match_height'`` default | ``'native'``): side-by-side only "
    "— scale every panel to equal height, or keep native pixels.\n"
    "``regions`` (optional): list aligned by index with ``paths``; each entry "
    "is a crop box ``[x0, y0, x1, y1]`` as 0..1 fractions, or ``null`` for no "
    "crop.  Use only a region that was recorded or handed off to you."
)

_VIEW_IMAGES_OCR_DOC = _VIEW_IMAGES_BASE_DOC + (
    "\n\nUser images (never renders) are also OCR'd — one entry per detected "
    "text region, or the cropped region only when one is given.  It is "
    "machine-recognised: check a value against the image before relying on it. "
    "``extract_text=False`` skips OCR."
)
```

### T — `read_attempt`  (263 → ~132 tok, ×8 agents)

*Replace the docstring at `agents/shared/attempts_tool.py:206-226` with:*

```
    """Read one file from the n-th attempt folder.

    Args:
      n:    1-based attempt number, as shown by ``list_attempts``.
      file: bare filename inside that folder (e.g. ``'parameters.json'``,
            ``'render_top.png'``, ``'propeller_mesh.obj'``) — no path
            separators or ``..``.

    Text / JSON is returned inline.  Images and meshes return the absolute
    path only; hand it to ``view_images`` or ``visualize_3d_model``.
    Returns an error string when the attempt or file does not exist.
    """
```

### T — `list_attempts`  (200 → ~96 tok, ×8 agents)

*Replace the docstring at `agents/shared/attempts_tool.py:162-176` with:*

```
    """List the attempt folders created so far this session.

    Returns, per attempt: its number, its folder name, a ``Has:`` line naming
    which roles are present (parameters / mesh / renders / description), and
    the filenames.  Folders may be partial.  Use the number with
    ``read_attempt(n, file)``.  Returns ``'No attempts created yet.'`` when
    there are none.
    """
```

### T — `ocr_regions`  (266 → ~134 tok, ×4 agents)

*Replace the docstring at `agents/shared/user_inputs_tool.py:173-189 (_OCR_REGIONS_DOC)` with:*

```
_OCR_REGIONS_DOC = (
    "Re-read labelled text regions of a user image at higher resolution.\n\n"
    "``image_path``: absolute path of a user image under "
    "``inputs/input_images/``.  ``region_ids``: the region numbers shown for "
    "that image in its OCR output (e.g. ``[2, 5, 7]`` for ``[region 2]``).  "
    "Each is cropped, zoomed and re-OCR'd; all results come back together.  "
    "Machine-recognised, so check each value.  Depending on this agent's "
    "settings the zoomed crop of each region may also be attached."
)
```

### T — `read_input_text`  (104 → ~36 tok, ×6 agents)

*Replace the docstring at `agents/shared/user_inputs_tool.py:96-103` with:*

```
    """Read one text file under ``inputs/`` (or its ``input_images/``
    subfolder) by absolute path; paths outside that tree are refused."""
```

### T — `call_<agent> routing tools (10 descriptions, 24 live bindings)`  (840 → ~369 tok, ×8 agents)

*Replace the docstring at `agents/shared/routing_tools.py:179-236 (_TOOL_DESCRIPTIONS)` with:*

```
_TOOL_DESCRIPTIONS: dict[str, str] = {
    "call_planner":
        "Hand off to the Planner.  ``message`` is the prose it will read.",
    "call_user_input_inspector":
        "Hand off to the User Input Inspector.  ``message`` is the prose it "
        "will read.",
    "call_dc_input_creator":
        "Hand off to the DC Input Creator.  ``message`` is the prose it will "
        "read.",
    "call_dc_input_inspector":
        "Hand off to the DC Input Inspector.  ``message`` is the prose it will "
        "read.",
    "call_tool_caller":
        "Hand off to the Tool Caller.  ``message`` is the prose it will read.",
    "call_dc_output_inspector":
        "Hand off to the DC Output Inspector.  ``message`` is the prose it "
        "will read; list the render paths to analyse under 'Render images:'.",
    "call_orchestrator":
        "Return control to the Orchestrator.  ``message`` is the prose it will "
        "read.",
    "call_conductor":
        "Return control to the Conductor (the hub that plans, routes and "
        "approves).  ``message`` is the prose it will read.",
    "call_creator":
        "Hand off to the Creator, which authors and self-validates the whole "
        "parameter set.  ``message`` is the prose it will read; state the "
        "qualitative direction, not concrete numbers.",
    "call_receptionist":
        "Hand a technical summary to the Receptionist, which composes and "
        "delivers the user-facing message.",
}
```

### T — `generate_and_render_propeller`  (883 → ~230 tok, ×1 agents)

*Replace the docstring at `tools/generate_mesh/generate_mesh.py:611-618 (output_dir Annotated) + 636-663 (docstring)` with:*

```
    output_dir: Annotated[
        str,
        "Absolute path of the attempt folder to write into (the hand-off's "
        "``Current attempt:`` path).  Must already exist.  An existing "
        "propeller_mesh.obj there is reused rather than regenerated.",
    ],
    ... (the 16 parameter Annotated descriptions on lines 619-634 are UNCHANGED —
        they carry the units and the "% of chord" semantics and must stay) ...
) -> str:
    """Build the propeller geometry from the 16 design parameters, save it to
    ``<output_dir>/propeller_mesh.obj``, then render three views (isometric,
    top, side) and run the mesh quality checks — one call does all of it.

    Returns the geometry summary (mesh path, vertex count, backend used)
    followed by the render report (the three render paths plus any quality
    warnings).  On a geometry failure it returns an ``Error:`` string and does
    not render.
    """
```

### T — `list_input_files`  (116 → ~47 tok, ×5 agents)

*Replace the docstring at `agents/shared/user_inputs_tool.py:84-90` with:*

```
    """List every file under ``inputs/`` and its ``input_images/`` subfolder:
    root text/JSON files, every paired image+note, and any orphan image or
    note.  Takes no arguments."""
```

### T — `new_attempt`  (277 → ~107 tok, ×2 agents)

*Replace the docstring at `agents/shared/attempts_tool.py:311-332` with:*

```
    """Create a new, empty attempt folder for one design generation.

    Args:
      slug:        short filename-safe label placed after the timestamp and
                   sequence number (e.g. ``'4blades_thick_ring'``).
      description: optional note; when non-empty it is written to
                   ``description.txt`` inside the new folder.

    Returns a confirmation containing the folder's absolute path.
    """
```

### T — `propose_attempt`  (427 → ~166 tok, ×1 agents)

*Replace the docstring at `agents/receptionist/propose_attempt_tool.py:87-121` with:*

```
    values: Annotated[
        dict[str, float],
        "All 16 canonical propeller parameter names mapped to their proposed "
        "numeric values.  Every key must be present; the outer-ring height is "
        "derived, so do not include it.",
    ],
) -> str:
    """Surface a set of 16 parameter values in the Parameters Inputs view as
    the system's proposed satisfying solution.

    The frontend marks every non-user-FIXED parameter PROPOSED and moves it to
    the given value, and labels every row (FIXED included) "PROPOSED VALUE: X".
    Updates the panel only — it renders nothing and starts no agent.

    Returns a short status string.
    """
```

### T — `read_agent_history`  (204 → ~128 tok, ×3 agents)

*Replace the docstring at `agents/shared/history_tool.py:19-34 (_TOOL_DESCRIPTION)` with:*

```
_TOOL_DESCRIPTION = (
    "Read another agent's message history to answer questions about prior "
    "pipeline runs without re-running anything.\n\n"
    "  agent_name (str): any agent in your roster, human-readable ('DC Output "
    "Inspector') or snake_case ('dc_output_inspector').\n"
    "  last_n (int, optional): only the last N messages; omit for all.\n\n"
    "Returns a formatted transcript (tool calls, tool results, message "
    "content), or an error string for an unknown name / empty history."
)
```

### T — `read_image_notes`  (80 → ~37 tok, ×4 agents)

*Replace the docstring at `agents/shared/user_inputs_tool.py:107-111` with:*

```
    """Read every ``<name>_note.txt`` in ``inputs/input_images/`` at once and
    return the contents grouped by image name.  Takes no arguments."""
```

### T — `render_blade_sections`  (318 → ~178 tok, ×1 agents)

*Replace the docstring at `tools/render_blade_sections/render_blade_sections.py:47-71` with:*

```
    """Render the three blade cross-sections (Inner / Middle / Outer) stacked
    vertically into a PNG: each airfoil rotated by its angle of attack,
    colour-coded and labelled, with an angle protractor.

    Args:
        parameters_path: absolute path to an attempt's ``parameters.json``
            (must sit inside the attempts directory).
        grid: draw a 1 mm x 1 mm reference grid behind the sections.
            Default False — a true-millimetre grid misleads when compared
            against a drawing whose own squares are not 1 mm.

    Returns the written PNG path (and size), or why it could not be produced.
    The PNG is shown in the chat and can be re-read via ``view_images``.
    """
```

### T — `write_parameters`  (257 → ~144 tok, ×1 agents)

*Replace the docstring at `agents/dc_input_creator/dc_input_creator.py:89-108` with:*

```
    """Persist the complete parameter set to ``<attempt_dir>/parameters.json``.

    - ``parameters``: dict of all design-configurator keys and values.
    - ``attempt_dir``: absolute path of the attempt folder it belongs to —
      the hand-off's ``Current attempt:`` path or the one ``new_attempt``
      returned.  It must exist and must not already hold a
      ``parameters.json`` (attempt folders are append-only).

    Returns a confirmation (file path + field count), or an error naming the
    missing / extra / non-numeric fields or the bad attempt folder.
    """
```

### T — `read_extracted_inputs (Planner copy)`  (145 → ~52 tok, ×1 agents)

*Replace the docstring at `agents/planner/planner.py:96-107` with:*

```
    """Read the User Input Inspector's structured extraction.

    Pass the absolute path given under the ``Extracted inputs file:`` label.
    Returns the full extraction as text, or a short error string."""
```

### T — `visualize_3d_model`  (181 → ~90 tok, ×1 agents)

*Replace the docstring at `tools/visualize_model/visualize_model.py:29-46` with:*

```
    """Display an attempt's generated mesh in the web interface's interactive
    3D viewer, where the user can rotate and zoom it.

    Args:
        obj_path: absolute path to an existing ``.obj`` inside the attempts
            directory (an attempt's ``propeller_mesh.obj``).

    Returns whether the model reached the viewer, or precisely why not.
    """
```

### T — `read_user_inputs`  (160 → ~112 tok, ×1 agents)

*Replace the docstring at `agents/user_input_inspector/user_input_inspector.py:75-85 (_READ_INPUTS_DOC)` with:*

```
_READ_INPUTS_DOC = (
    "Read a user-inputs directory: its text plus a LIST of its images (it "
    "does not load the images).  ``path`` is the inputs directory given "
    "under the ``Input directory:`` label.  Returns a summary plus the "
    "concatenated contents of every text/JSON file — including each image's "
    "``_note.txt`` — then the reference images present, with their paths.  "
    "Call ``view_images`` to actually see one."
)
```

### T — `read_parameters (2 separate copies)`  (127 → ~38 tok, ×2 agents)

*Replace the docstring at `agents/dc_input_inspector/dc_input_inspector.py:73-78 and agents/tool_caller/tool_caller.py:75-79` with:*

```
    """Read an attempt's parameter JSON.

    Pass the absolute path given under the ``Parameters file:`` label.
    Returns the file content as text."""
```

### T — `read_user_queries`  (115 → ~65 tok, ×1 agents)

*Replace the docstring at `agents/planner/planner.py:121-130` with:*

```
    """Return entries from user_query.txt in chronological order, each with its
    original ``--- [timestamp] ---`` header.

    ``n`` (int >= 1): how many entries.  ``from_start`` (default False): False
    returns the latest ``n``, True the oldest ``n``."""
```

### T — `read_extracted_inputs (DCIC + DCII copies)`  (141 → ~46 tok, ×2 agents)

*Replace the docstring at `agents/dc_input_creator/dc_input_creator.py:78-83 and agents/dc_input_inspector/dc_input_inspector.py:84-89` with:*

```
    """Read the structured user-input extraction.

    Pass the absolute path given under the ``Extracted inputs file:`` label.
    Returns the full three-section extraction as text."""
```

### T — `write_extraction`  (89 → ~72 tok, ×1 agents)

*Replace the docstring at `agents/user_input_inspector/user_input_inspector.py:105-111` with:*

```
    """Persist the structured user-input extraction to a file.

    Pass the absolute path given under the ``Extraction output file:`` label
    plus the three section strings; use "None specified." for an empty one.
    The tool adds the canonical section headers and writes the file."""
```

### Is the tool SET itself bloated?

METHOD + VALIDATION. Token figures are chars/4 of the description text as the LLM receives it. Cross-check against your measured dump: Tool Caller's 9 schemas sum to 2,122 by my method vs 2,201 measured; Receptionist's 8 sum to 1,753 vs 1,714; DCOI's 10 sum to 1,992 vs 1,911. Within 4%, so the per-tool numbers are trustworthy.

BINDING COUNTS (7-agent, PLANNER_FIRST=False, DCII on): calculate/list_attempts/read_attempt = 8 agents each; read_input_text = 6; list_input_files = 5; view_images/ocr_regions/read_image_notes = 4; read_agent_history = 3 (Planner, Receptionist, Orchestrator); new_attempt = 2 (DCIC + Orchestrator-as-fallback); 24 routing-tool bindings total. Every rewrite above also lands in the 5-agent topology for free — agents/creator/creator.py and agents/conductor/conductor.py import the same shared tool modules.

DUPLICATES BEING COLLAPSED (policy moved out of schemas, not deleted from the system):
- "batch every expression into ONE calculate call" lives in DC_prompt_fragments/tools_config/hard_constraints_tools.md:6-10 (spliced into EVERY agent), again in tool_inventory.md:7-8 (Tool Caller), again in agent_tools_overview.md:1-2 (Orchestrator). The Annotated description is the 3rd/4th copy. Cut from the schema; the Python-syntax steer (the '&&' failure) survives as one clause.
- "do NOT guess/invent a path" lives in hard_constraints_tools.md:2-5 (every agent) and again in dc_output_inspector/prompt.md:20-25, tool_caller/prompt.md:55, dc_input_inspector/prompt.md:92, dc_input_creator/prompt.md:250. It is currently ALSO restated in six read-tool docstrings (read_input_text, read_user_inputs, view_images, and the three read_extracted_inputs / two read_parameters copies). Removed from all of them.
- "pass every region in ONE ocr_regions call, not one call each" is in user_input_inspector/prompt.md:392, dc_input_inspector/prompt.md:55, dc_output_inspector/prompt.md:87, creator/prompt_5agents.md:231. Removed from the schema.
- propose_attempt's when-to-call / when-NOT-to-call is stated three times: the tool docstring, DC_prompt_fragments/tools_config/propose_attempt.md (which explicitly says "mechanics ... are documented on the tool itself" — i.e. the fragment owns policy, the tool owns mechanics), and receptionist/prompt.md:299-314. Docstring keeps mechanics only.
- visualize_3d_model's "you still never describe its appearance" is in visualize_3d_model.md plus the generic anti-hallucination HARD rule. Removed from the schema.
- read_agent_history enumerates all 8 agent keys; agents/shared/prompt_fragments/available_agents.md already puts that roster in every prompt.
- The 10 routing descriptions restate what each agent's "### Available routing tools" section (agents/shared/prompt_fragments/routing_*.md) already says per-agent and more precisely (FORWARD / CLARIFY / ESCALATE semantics). The schema copy is generic and adds nothing; the boilerplate clause "The ``message`` argument IS the hand-off text X will see — write it as free-form prose" is repeated 7 times across 24 bindings.

ANSWER TO THE SECOND HALF OF RULE 9 — YES, THE TOOL SET IS BLOATED. Six concrete changes, ordered by payoff:

1. SIX TOOLS ARE THE SAME TOOL: "read the text file whose path a hand-off label gave me". read_input_text (6 agents), read_extracted_inputs defined THREE separate times (planner.py:95, dc_input_creator.py:77, dc_input_inspector.py:83), read_parameters defined TWICE (dc_input_inspector.py:72, tool_caller.py:74). Same contract, five separate handler branches, and the duplication has already drifted — the Planner's copy carries a whole UII-first policy paragraph the other two lack. Replace with ONE shared `read_pipeline_file(path)` in agents/shared/ that accepts any path under inputs/ or attempts/. Schema effect: ~465 tok of duplicated stubs → ~270; the real win is that the "which label feeds which tool" prose collapses to one line of hard_constraints_tools.md, and the DCII stops having two near-identical read tools to disambiguate between. Risk: medium — each agent's prompt must name the labels it should read (`Parameters file:` AND `Extracted inputs file:` for the DCII).

2. read_user_inputs IS A SUPERSET OF list_input_files + read_image_notes. The UII binds all three: read_user_inputs(path) returns "summary + all text + all _note.txt + image list"; list_input_files() returns "listing + pairing status"; read_image_notes() returns "all notes". Three tools, one directory, overlapping outputs — a textbook ambiguous decision point. Drop read_user_inputs (it is a UII-only stub with its own handler at user_input_inspector.py:314) and have the UII use list_input_files + read_image_notes, OR fold the note text into list_input_files' output and drop read_image_notes from all 4 agents. Either way: -1 tool from 4-5 agents (~150-350 tok) and the "on demand (for revisiting one file)" paragraph at user_input_inspector/prompt.md:395-397 disappears.

3. ocr_regions AND view_images(regions=...) BOTH CROP A USER IMAGE, with two incompatible notions of "region" (fractional [x0,y0,x1,y1] box vs integer OCR region id) bound to the same 4 agents. Fold the re-read into view_images as a per-path `ocr_region_ids` argument, or at minimum rename it `reread_text_regions` so it cannot read as "the other way to view a crop". Full fold recovers ~128 tok x 4 and removes the "which region tool?" decision from four prompts.

4. visualize_3d_model AND propose_attempt ARE ALWAYS CALLED AS A PAIR, and propose_attempt.md spends an entire paragraph ("Pair it, and never judge from it") plus receptionist/prompt.md:299-307 explaining the ordering and the one case where you call only the first. That is coordination logic narrated in prose (golden rule 10). Merge into `show_attempt(obj_path, proposed_values=None)` — omitting values IS the informational-only case. Recovers ~90 tok of schema and lets you delete two policy paragraphs from the Receptionist's prompt.

5. UNBIND new_attempt FROM THE ORCHESTRATOR. Commit cf4b900 made the DCIC the sole owner of attempt creation, but the Orchestrator still holds the tool "only as a special-case fallback" — and agent_tools_overview.md then burns lines 6-10 AND 18-21 explaining that it is fallback-only. The prose exists solely to neutralise a binding you no longer want. Remove the binding (orchestrator.py:451), delete both prose blocks: ~106 tok of schema + ~90 tok of prompt on the Orchestrator, and the ownership ambiguity that caused the original bug stops being reachable.

6. list_attempts vs read_attempt is the one pair I would KEEP. They are genuinely different operations (enumerate vs read one file) and after the rewrites they cost 96 + 132 tok. Note for later, though: when RAG is on, retrieve_attempt overlaps read_attempt (past-session vs this-session) — re-check that pair before enabling RAG_ENABLED.

RULES I DELIBERATELY DID NOT CUT: the 16 Annotated parameter descriptions on generate_and_render_propeller (generate_mesh.py:619-634) stay verbatim — they carry the units and the "% of chord" semantics behind the pinned-chord bug. write_parameters keeps the append-only refusal. read_attempt keeps "images and meshes return the path only" as a general principle (the 2026-05-31 mesh-inline incident narrative goes; the behaviour is enforced in code at attempts_tool.py:275-290 regardless). view_images keeps the exact region format; only the narrative about WHO authors regions goes, and that is owned by the UII and DCOI prompts.

---

## 4. Per-agent changes

### 4.1 Receptionist — 9,193 → ~3,379 tok

| ID | action | section | −chars | rules | risk | what |
|---|---|---|---:|---|---|---|
| **RCP-29** | SCOPE_PER_AGENT | ## Hard constraints — generic (apply to every agent) | 1794 | 8,6,5 | medium | The shared 8-agent constitution costs the Receptionist ~2,000 chars, and everything in it that actually binds a user-facing, non-chain agent fits in four lines. |
| **RCP-03** | COMPRESS | ### Surfacing a proposed solution — ``propose_attempt`` | 1452 | 2,7,9 | low | Five endorsement phrasings and three hedging phrasings collapse to two canonical examples each, and the paragraph restating what the user sees in the panel is UI mechanics the tool schema already documents. |
| **RCP-21** | SCOPE_PER_AGENT | ## Output file locations — do not confuse these | 1414 | 3,8,7 | low | The Receptionist only ever reads an attempt folder by the path a hand-off gives it, so the fragment's authorship rules (who calls new_attempt), append-only semantics and render-reuse behaviour are reference material for the DCIC, not for this agent. |
| **RCP-01** | COMPRESS | ## User inputs may include images (writing a description is  | 1284 | 2,5,7 | low | Two numbered checks written as prose essays plus a tool paragraph compress to one gate sentence each; the blank-note rule (a real bug fix) is kept as a five-word clause instead of a four-line justification. |
| **RCP-30** | SCOPE_PER_AGENT | ## Hard constraints — DC-specific | 1273 | 6,8,5 | medium | For this agent the whole fragment is a second copy of content already present: the CANNOT list covers the analysis/format/view/post-processing bans and the mesh-metric list, and the parameter-name check covers 'only the named parameters exist'. |
| **RCP-09** | COMPRESS | ## HARD RULE — answers to system-posed questions MUST be for | 1097 | 2,7,5 | low | The rule, its two exceptions and the 'only genuine non-answers' reminder are one idea stated three times; the enumerated answer-shapes reduce to three canonical examples. |
| **RCP-05** | MERGE | Parameter-name check (Situation A) | 1078 | 2,6,3 | low | Three sub-blocks (scope / mapping / no-range-check) are one procedure, and the $invalid_parameter_examples splice is replaced by the three names inline — cheaper than the fragment and it removes the fragment's agent-hallucination paragraph, which is Orchestrator/Planner business. |
| **RCP-31** | SCOPE_PER_AGENT | ## Hard constraints — tool-specific | 1024 | 8,3,7 | low | Two thirds of the fragment is the attempt-folder write protocol (append-only, copy-into-a-new-attempt, which agent opens folders) and the Receptionist has no write tool at all — the two rules that bind it fit in four lines. |
| **RCP-25** | COMPRESS | ## Extraction-only requests are valid forwards | 1016 | 7,2,5 | low | Three quarters of this section explains WHY the UII exists and what it writes to extracted_inputs.txt — architecture the Receptionist never acts on; the behaviour is 'forward it and label it'. |
| **RCP-22** | COMPRESS | ## Reporting attempts — driven by the hand-off, fetched via  | 921 | 6,7,9 | low | The three numbered steps duplicate the two tool blocks above them (endorse-vs-hedge wording, the obj path rule); the procedure itself is three tool calls in order. |
| **RCP-23** | MERGE | Values the system did not honour / Precision jobs | 876 | 6,2,7 | low | Two paragraphs teaching the same behaviour — relay an unflattering fact from the hand-off verbatim rather than smoothing it — merge into one, keeping the NACA-ceiling example as the single canonical case. |
| **RCP-02** | COMPRESS | ### Showing a generated model — ``visualize_3d_model`` | 839 | 9,5,7 | low | A 'When to call it' list whose two bullets restate the Reporting-attempts procedure, plus the never-describe rule stated twice in one fragment. |
| **RCP-26** | COMPRESS | ## Your DBa scope — your OWN work, not the chain's (HARD) | 812 | 7,8,2 | low | Compresses the three-reason justification to one clause AND fixes a real defect: this section sits OUTSIDE the <<HAS_DBA>> region, so with RAG_ENABLED=False the Receptionist is currently given 1,292 characters of rules about three tools it is not bound to. |
| **RCP-15** | MERGE | Situation B composition / permission-to-vary | 595 | 4,2,7 | low | 'Write freely and eloquently in your own voice' is default model behaviour; the permission-to-vary rule keeps its invariant but loses the three fallback phrasings for recalling the locked values. |
| **RCP-04** | COMPRESS | ## Two distinct situations you operate in / Situation A | 581 | 5,6 | low | The bolded 'BEFORE the parameter-name check run the image gate' paragraph is a third statement of the image gate (already in the image section and in its own numbered checks) — ordering is one clause, not seven lines. |
| **RCP-27** | COMPRESS | ### Available routing tools | 574 | 10,6,5 | low | Naming the four agents the Receptionist cannot call is coordination detail already enforced by the bound tool set — the agent has exactly one routing tool, so the schema is the constraint. |
| **RCP-11** | COMPRESS | Questions about an earlier run (read_agent_history) | 556 | 2,7,6 | low | Keeps the agent->topic routing table (genuinely non-obvious) and drops the four-example question list and the closing 'never source a statement to yourself' sentence, which the HARD RULE above already states. |
| **RCP-17** | DELETE | ## Categories of incoming user message | 547 | 6,4,2 | low | Enumerates four message categories then instructs the agent NOT to use them; the only actionable content — a proposal request is a valid forward — is already in the Forward path's trigger list. |
| **RCP-14** | COMPRESS | ### Situation B — Outgoing system message (composition) | 531 | 10,6,7 | low | The inline restatement of the three-step reporting procedure duplicates the Reporting-attempts section a page below; receptionist.py already detects and rejects a routing call made in Situation B, so the prose only needs to state the rule once. |
| **RCP-13** | DELETE | Decide by reasoning / never invent design intent | 510 | 4,6 | low | Forbids status tags, prefixes and canonical phrases that no instruction in the prompt asks for — pure negative space; the second paragraph repeats the reply-direct path. |
| **RCP-06** | COMPRESS | Situation A path 1 — Forward | 489 | 2,7,5 | low | Keeps every content item the summary must carry (including the vary-authorisation default, which is load-bearing) and drops the framing sentences around them. |
| ⚠️ **RCP-12** | DELETE | No second-guessing the chain's reported result | 470 | 6,1 | medium | A same-prompt restatement of the anti-fabrication HARD RULE applied to one specific case (an extracted value in a hand-off). |
| **RCP-08** | COMPRESS | Situation A path 2 — Reply directly | 411 | 2,6,5 | low | Five listed trigger conditions reduce to three, and the forward-pointing exception is redundant with the HARD RULE that immediately follows it. |
| **RCP-32** | COMPRESS | ### Blade-sections visualizer | 386 | 8,7 | low | Shared awareness blurb spliced into 9 prompts; the stacked-vertically/true-angle-of-attack rendering detail and the 'can be read by any agent that can load images' clause matter only to the Tool Caller and DCOI, which have their own per-agent overlays. |
| **RCP-10** | MERGE | ## HARD RULE — you NEVER invent observations, judgements, or | 385 | 2,6,5 | low | Collapses the six-item list of forbidden statement types into one clause and folds in the don't-adjudicate rule from the separate paragraph below (see C-12), so the anti-fabrication invariant is stated once, completely. |
| **RCP-16** | MERGE | Situation B — result reporting and plain language | 384 | 6,3 | low | The legacy 'DC parameters written this cycle' instruction here is a third copy (Reporting attempts and the anti-stale paragraph both state it); keeps the error-reporting duty and the standing-directives leak guard. |
| **RCP-20** | COMPRESS | CANNOT list | 342 | 2,3,7 | low | Six bullets with per-item explanations become four; the mesh-modification and mesh-refinement bullets were the same prohibition split in two. |
| **RCP-28** | SCOPE_PER_AGENT | ## End-of-session feedback message (read-only) | 296 | 8,7 | low | Three spliced pieces for one read-only fact; the shared outro even ends with 'fold it into your DH answers', which is Database-Handler wording that does not apply to this agent. |
| **RCP-07** | COMPRESS | Preserve the force of user directives | 262 | 2,7 | low | Keeps the rule and one example of each direction; drops two of the four softening examples and the closing why-sentence. |
| **RCP-18** | COMPRESS | ## What this system can and cannot do (HARD) | 246 | 5,7,6 | low | The 'doing so advertises capabilities the system does not have and sets the user up for frustration' justification and the trailing restatement of the same rule both go; the two slots are untouched. |
| **RCP-19** | COMPRESS | CAN list | 219 | 6,7 | low | Merges the generate and render bullets (one pipeline) and drops the parenthetical listing what agent histories contain, which the read_agent_history section already spells out. |
| **RCP-24** | COMPRESS | Anti-stale block handling | 116 | 6,11 | low | Leads with the invariant instead of the legacy-format special case, and folds the 'if generation failed, list no artifacts' clause into the same rule. |

<details><summary><b>Full text of each change</b></summary>

#### RCP-29 · SCOPE_PER_AGENT · −1794 chars · risk medium

*File:* `agents/receptionist/prompt.md` · *Section:* ## Hard constraints — generic (apply to every agent) · *Golden rules:* 8, 6, 5 · *auditor's own id:* C-29

**Why:** The shared 8-agent constitution costs the Receptionist ~2,000 chars, and everything in it that actually binds a user-facing, non-chain agent fits in four lines.

**Risk:** Drops the fragment's 'DON'T fabricate observations about artifacts you did not see produced' bullet for this agent — that invariant survives only because C-10 restates it agent-specifically and far more strongly. Apply C-10 (or keep the existing lines 160-174) alongside this.

**Cut from** `## Hard constraints — generic (apply to every agent)`

**...through** `$hard_constraints_generic`

**Replace with:**

```
## Hard constraints - generic
Act only on your hand-off and the paths it gives; use only your bound
tools and never invent tools, files, or policies.  Never repeat a tool
call with arguments you already used this turn.  Answer in English.
```

#### RCP-03 · COMPRESS · −1452 chars · risk low

*File:* `DC_prompt_fragments/tools_config/propose_attempt.md` · *Section:* ### Surfacing a proposed solution — ``propose_attempt`` · *Golden rules:* 2, 7, 9 · *auditor's own id:* C-03

**Why:** Five endorsement phrasings and three hedging phrasings collapse to two canonical examples each, and the paragraph restating what the user sees in the panel is UI mechanics the tool schema already documents.

**Cut from** `### Surfacing a proposed solution — ``propose_attempt```

**...through** `holds — never describe or judge an attempt from it.`

**Replace with:**

```
### Surfacing a proposed solution - ``propose_attempt``

``propose_attempt(values)`` pushes a full 16-parameter dict to the
Parameters Inputs view as the system's PROPOSED SOLUTION.  Take the
values from a ``read_attempt(n, "parameters.json")`` result - never
invent them; the user sees the dict literally.  Call it only when the
hand-off ENDORSES an attempt as the current best ("recommend attempt N",
"final pick") or the user asks directly; hedging wording ("showing for
context", "not satisfying yet") does not, and the panel stickily keeps
the last endorsed proposal.  It only moves sliders - pair it after
``visualize_3d_model``, and never judge quality from it.
```

#### RCP-21 · SCOPE_PER_AGENT · −1414 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* ## Output file locations — do not confuse these · *Golden rules:* 3, 8, 7 · *auditor's own id:* C-21

**Why:** The Receptionist only ever reads an attempt folder by the path a hand-off gives it, so the fragment's authorship rules (who calls new_attempt), append-only semantics and render-reuse behaviour are reference material for the DCIC, not for this agent.

**Risk:** The shared fragment stays in place for the DC Input Creator, which is the agent that actually writes into attempt folders.

**Cut from** `## Output file locations — do not confuse these`

**...through** `$output_file_locations`

**Replace with:**

```
## Output file locations
Every artifact lives inside one attempt folder
``logs/attempts/<TS>_<NNN>_<slug>/``: ``parameters.json``,
``propeller_mesh.obj``, ``render_isometric.png`` / ``render_top.png`` /
``render_side.png``, optional ``description.txt``.  A folder may be
partial, and nothing lives outside one.
```

#### RCP-01 · COMPRESS · −1284 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* ## User inputs may include images (writing a description is optional) · *Golden rules:* 2, 5, 7 · *auditor's own id:* C-01

**Why:** Two numbered checks written as prose essays plus a tool paragraph compress to one gate sentence each; the blank-note rule (a real bug fix) is kept as a five-word clause instead of a four-line justification.

**Risk:** Keeps all three behaviours the pairing/note work encoded: INVALID => reply-direct naming the orphans, off-topic note => reply-direct, blank note => forward normally.

**Cut from** `## User inputs may include images (writing a description is optional)`

**...through** `auto-attached; text/paths only, never image bytes).`

**Replace with:**

```
## Image inputs (a written description is optional)
Images live in ``input_images/`` with an auto-created
``<name>_note.txt``; a BLANK note is fine and forwards normally.  You
never analyse images - the UII does.  Before forwarding: if the
``Image+note pairing:`` banner says INVALID, reply directly naming the
orphan files (never forward a partial set); if an auto-loaded note is
off-topic for this system, reply directly and ask the user to revise it.
Otherwise forward, saying images were supplied.

On-demand tools: ``read_input_text(path)`` re-reads one note;
``list_attempts`` locates a prior attempt; ``read_attempt(n, file)`` is
HOW you get an attempt's confirmed values and render paths (text only,
never image bytes).
```

#### RCP-30 · SCOPE_PER_AGENT · −1273 chars · risk medium

*File:* `agents/receptionist/prompt.md` · *Section:* ## Hard constraints — DC-specific · *Golden rules:* 6, 8, 5 · *auditor's own id:* C-30

**Why:** For this agent the whole fragment is a second copy of content already present: the CANNOT list covers the analysis/format/view/post-processing bans and the mesh-metric list, and the parameter-name check covers 'only the named parameters exist'.

**Risk:** Removes the only place the Receptionist is told to REJECT an invented parameter proposed by another agent — but the Receptionist never receives a parameter proposal from an agent, only a hand-off summary, and the Orchestrator and Planner keep the fragment. If you want belt-and-braces, keep the first bullet only.

**Cut from** `## Hard constraints — DC-specific`

**...through** `$hard_constraints_dc`

**Replace with:** *(nothing — pure deletion)*

#### RCP-09 · COMPRESS · −1097 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* ## HARD RULE — answers to system-posed questions MUST be forwarded · *Golden rules:* 2, 7, 5 · *auditor's own id:* C-09

**Why:** The rule, its two exceptions and the 'only genuine non-answers' reminder are one idea stated three times; the enumerated answer-shapes reduce to three canonical examples.

**Risk:** This is a genuine load-bearing rule (a stranded pipeline is a session-ending failure) — the compression keeps the trigger, the MUST, the anti-'I will keep X' clause and both exceptions.

**Cut from** `## HARD RULE — answers to system-posed questions MUST be forwarded`

**...through** `Only genuine non-answers fall under the exceptions above.`

**Replace with:**

```
## HARD RULE - answers to system-posed questions MUST be forwarded
If your last outgoing message carried a question the system posed, the
user's next message is its answer and you MUST forward it via
``call_orchestrator`` - even a terse "yes" / "no" / "keep them", a
refusal, or a restatement of existing constraints.  You are not the
decision-maker: never write "I will keep X" to a pending system
question; replying directly strands the pipeline.  Only a pure
non-answer ("huh?", "what do you want from me?") or a refusal raising an
unrelated matter is handled directly - then say the question is still
open.
```

#### RCP-05 · MERGE · −1078 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* Parameter-name check (Situation A) · *Golden rules:* 2, 6, 3 · *auditor's own id:* C-05

**Why:** Three sub-blocks (scope / mapping / no-range-check) are one procedure, and the $invalid_parameter_examples splice is replaced by the three names inline — cheaper than the fragment and it removes the fragment's agent-hallucination paragraph, which is Orchestrator/Planner business.

**Risk:** Drops the $invalid_parameter_examples slot from THIS prompt only; the fragment stays spliced into the Orchestrator and Planner.

**Cut from** `**Parameter-name check (plain, explicit user values only).**`

**...through** `And never silently clip, round, or redistribute a user's
value: substituting values is not your job.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
**Parameter-name check.**  Only for numbers stated plainly - a value
for a recognisable parameter in that parameter's own unit.  Map each to
a parameter in "Parameter Ranges" below (normalising the unit).  A value
given as a function of another parameter, expressed relatively, or
needing interpretation is NOT yours to check - forward it as-is.  If a
plain name is not in the table and you cannot confidently map it (an
obvious alias or abbreviation is fine; an ambiguous or unknown name is
not), reply directly, name the unrecognised items, list the canonical
names, and ask the user to restate - there is no hub_radius,
fillet_radius, tip_clearance, or any parameter outside the table.  You
do NOT check ranges: an out-of-range number never stops a request at the
door, never claim values are "within range", and never clip, round, or
redistribute a user's value.
```

#### RCP-31 · SCOPE_PER_AGENT · −1024 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* ## Hard constraints — tool-specific · *Golden rules:* 8, 3, 7 · *auditor's own id:* C-31

**Why:** Two thirds of the fragment is the attempt-folder write protocol (append-only, copy-into-a-new-attempt, which agent opens folders) and the Receptionist has no write tool at all — the two rules that bind it fit in four lines.

**Cut from** `## Hard constraints — tool-specific`

**...through** `$hard_constraints_tools`

**Replace with:**

```
## Hard constraints - tools
Never guess a path for a read tool - use only paths a hand-off label or
a tool result gave you.  Route every arithmetic operation through
``calculate``, batched into one call per turn.  You only read attempt
folders, never write to them.
```

#### RCP-25 · COMPRESS · −1016 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* ## Extraction-only requests are valid forwards · *Golden rules:* 7, 2, 5 · *auditor's own id:* C-25

**Why:** Three quarters of this section explains WHY the UII exists and what it writes to extracted_inputs.txt — architecture the Receptionist never acts on; the behaviour is 'forward it and label it'.

**Cut from** `## Extraction-only requests are valid forwards`

**...through** `so an extraction-only ask can yield more than the final parameter set.)`

**Replace with:**

```
## Extraction-only requests are valid forwards
"How many blades are in my sketch?", "extract the dimensions you see" -
first-class forwards, not something to refuse.  Never reply "I cannot
analyse images"; the UII reads the user's text + images for every
request.  Forward, and say the request is extraction-only (no full
design run expected).
```

#### RCP-22 · COMPRESS · −921 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* ## Reporting attempts — driven by the hand-off, fetched via your tools · *Golden rules:* 6, 7, 9 · *auditor's own id:* C-22

**Why:** The three numbered steps duplicate the two tool blocks above them (endorse-vs-hedge wording, the obj path rule); the procedure itself is three tool calls in order.

**Cut from** `## Reporting attempts — driven by the hand-off, fetched via your tools`

**...through** `identify which attempt they mean, do NOT guess: that is Situation A —
forward it.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Reporting attempts
The Situation B "Attempts this cycle:" / "Show to user:" block - not the
filesystem - says which attempts exist and which to present.  For each:
``read_attempt(n, "parameters.json")`` for its real values (relay ONLY
what the result returns), ``visualize_3d_model`` the designated model,
and ``propose_attempt`` only if the hand-off endorses it as the current
best.  For a SPECIFIC / DIFFERENT attempt the user names,
``list_attempts`` then read and visualize it - but do NOT
``propose_attempt``.  If you cannot tell which attempt they mean, do not
guess: forward it as Situation A.
```

#### RCP-23 · MERGE · −876 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* Values the system did not honour / Precision jobs · *Golden rules:* 6, 2, 7 · *auditor's own id:* C-23

**Why:** Two paragraphs teaching the same behaviour — relay an unflattering fact from the hand-off verbatim rather than smoothing it — merge into one, keeping the NACA-ceiling example as the single canonical case.

**Cut from** `**Values the system did not honour — say so.**  When the hand-off names a`

**...through** `fidelity / ceiling wording must come from the hand-off; if it is not there, do
not manufacture a fidelity claim.)`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
**Report shortfalls honestly.**  When the hand-off says a requested
value was not honoured, state what was asked, what was used, and the
reason given.  When it reports a residual gap or a modelling ceiling on
a precision job ("as close as the NACA model allows; the drawn leading
edge is sharper than it can reach"), say so - never round it up to
"matches your sketch".  Both must come FROM the hand-off.
```

#### RCP-02 · COMPRESS · −839 chars · risk low

*File:* `DC_prompt_fragments/tools_config/visualize_3d_model.md` · *Section:* ### Showing a generated model — ``visualize_3d_model`` · *Golden rules:* 9, 5, 7 · *auditor's own id:* C-02

**Why:** A 'When to call it' list whose two bullets restate the Reporting-attempts procedure, plus the never-describe rule stated twice in one fragment.

**Risk:** Fragment is spliced only into the Receptionist (7-agent) and the 5-agent Receptionist.

**Cut from** `### Showing a generated model — ``visualize_3d_model```

**...through** `business; never describe it (see the HARD rule on inventing observations).`

**Replace with:**

```
### Showing a generated model - ``visualize_3d_model``

``visualize_3d_model(obj_path)`` shows an attempt's mesh in the web
viewer; obj_path is ``<attempt folder>/propeller_mesh.obj`` for the
folder named in your hand-off block.  Read-only, so it is allowed in
Situation B.  It tells you nothing about how the mesh looks - never
describe or judge it.
```

#### RCP-26 · COMPRESS · −812 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* ## Your DBa scope — your OWN work, not the chain's (HARD) · *Golden rules:* 7, 8, 2 · *auditor's own id:* C-26

**Why:** Compresses the three-reason justification to one clause AND fixes a real defect: this section sits OUTSIDE the <<HAS_DBA>> region, so with RAG_ENABLED=False the Receptionist is currently given 1,292 characters of rules about three tools it is not bound to.

**Risk:** In the measured configuration (RAG off) this cut removes the full 1,292 chars, not 812 — the <<HAS_DBA>> wrapper strips it entirely. 812 is the conservative RAG-on figure.

**Cut from** `## Your DBa scope — your OWN work, not the chain's (HARD)`

**...through** `they are wasted tokens.  Use ``images_flag=False``.`

**Replace with:**

```
<<HAS_DBA>>## Your DBa scope - your OWN work, not the chain's (HARD)
``database_search`` / ``retrieve_user_inputs`` / ``retrieve_attempt``
serve YOUR questions about a past run.  When the user tells the CHAIN to
use past experience, forward that mandate verbatim - do NOT run the
search and pack results into your summary: the chain has the same tools
and its own visual capability, and pre-cooking strips the images and
biases it.  Always pass ``images_flag=False``.<</HAS_DBA>>
```

#### RCP-15 · MERGE · −595 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* Situation B composition / permission-to-vary · *Golden rules:* 4, 2, 7 · *auditor's own id:* C-15

**Why:** 'Write freely and eloquently in your own voice' is default model behaviour; the permission-to-vary rule keeps its invariant but loses the three fallback phrasings for recalling the locked values.

**Cut from** `Write freely and eloquently in your own voice.  There is no fixed`

**...through** `defaults freely, so only the user's numbers need permission.`

**Replace with:**

```
There is no fixed template - give enough context for the user to know
what happened and what they can do next, and ask any question in the
summary plainly.

**HARD - permission-to-vary questions name only user-locked values.**
Only the numbers the user literally provided need permission (typically
two or three); never list the full $parameter_count-field set as if all
needed approval - the rest are system defaults the pipeline varies
freely, and say so.
```

#### RCP-04 · COMPRESS · −581 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* ## Two distinct situations you operate in / Situation A · *Golden rules:* 5, 6 · *auditor's own id:* C-04

**Why:** The bolded 'BEFORE the parameter-name check run the image gate' paragraph is a third statement of the image gate (already in the image section and in its own numbered checks) — ordering is one clause, not seven lines.

**Cut from** `## Two distinct situations you operate in`

**...through** `scope failure — an undescribed image forwards normally.)`

**Replace with:**

```
## Two situations
Your HumanMessage tells you which one you are in.

### Situation A - Incoming user message
It opens with ``User input files from: <path>`` and the user's raw text,
plus any paired ``_note.txt`` contents and the pairing banner.  Run the
image gates above, then the parameter-name check, then pick one of the
two response paths.
```

#### RCP-27 · COMPRESS · −574 chars · risk low

*File:* `agents/shared/prompt_fragments/routing_receptionist.md` · *Section:* ### Available routing tools · *Golden rules:* 10, 6, 5 · *auditor's own id:* C-27

**Why:** Naming the four agents the Receptionist cannot call is coordination detail already enforced by the bound tool set — the agent has exactly one routing tool, so the schema is the constraint.

**Risk:** Fragment is used only by the Receptionist (7-agent) and the 5-agent Receptionist.

**Cut from** `### Available routing tools`

**...through** ```call_orchestrator`` (that would loop control back into the system).`

**Replace with:**

```
### Available routing tools
``call_orchestrator(message)`` is your only routing tool - all onward
dispatch is the Orchestrator's decision.  Replying to the user is plain
text with NO tool call; never also call ``call_orchestrator``.
```

#### RCP-11 · COMPRESS · −556 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* Questions about an earlier run (read_agent_history) · *Golden rules:* 2, 7, 6 · *auditor's own id:* C-11

**Why:** Keeps the agent->topic routing table (genuinely non-obvious) and drops the four-example question list and the closing 'never source a statement to yourself' sentence, which the HARD RULE above already states.

**Cut from** `When the user asks about an earlier run — a factual lookup ("what`

**...through** `cannot tie it to an agent's history or to what the user literally said, do
not make it.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
When the user asks about an earlier run - a fact ("what diameter did we
end up with?") or a conclusion ("any suggestions?") - call
``read_agent_history`` on whichever agent saw it (DCOI for the visual
verdict, Planner for reasoning, Tool Caller for what ran + paths, DCIC
for chosen values, UII for extracted intent) and quote it faithfully.
If the histories fall short, forward to the Orchestrator with what you
found.  When unsure whether a message is such a question or a new design
ask, forward it.
```

#### RCP-17 · DELETE · −547 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* ## Categories of incoming user message · *Golden rules:* 6, 4, 2 · *auditor's own id:* C-17

**Why:** Enumerates four message categories then instructs the agent NOT to use them; the only actionable content — a proposal request is a valid forward — is already in the Forward path's trigger list.

**Cut from** `## Categories of incoming user message`

**...through** `a mesh run, so when you forward such a request make the motivation and
scope explicit in your prose.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

#### RCP-14 · COMPRESS · −531 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* ### Situation B — Outgoing system message (composition) · *Golden rules:* 10, 6, 7 · *auditor's own id:* C-14

**Why:** The inline restatement of the three-step reporting procedure duplicates the Reporting-attempts section a page below; receptionist.py already detects and rejects a routing call made in Situation B, so the prose only needs to state the rule once.

**Cut from** `### Situation B — Outgoing system message (composition)`

**...through** `user-facing text.  (A later user message asking to see a DIFFERENT
attempt is Situation A, not B.)`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Situation B - Outgoing system message (composition)
Opens with ``System message to relay to the user:``.  Respond with plain
user-facing text; do NOT call ``call_orchestrator`` or
``read_agent_history``.  The only tools allowed are the read-only ones:
``read_attempt``, ``list_attempts``, ``visualize_3d_model``,
``propose_attempt``.  If the summary carries an ``Attempts this cycle:``
/ ``Show to user:`` block, run **Reporting attempts** below first.  (A
later user message asking to see a DIFFERENT attempt is Situation A.)
```

#### RCP-13 · DELETE · −510 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* Decide by reasoning / never invent design intent · *Golden rules:* 4, 6 · *auditor's own id:* C-13

**Why:** Forbids status tags, prefixes and canonical phrases that no instruction in the prompt asks for — pure negative space; the second paragraph repeats the reply-direct path.

**Risk:** The 'never manufacture a forward summary' clause is carried in C-08's replacement. If you apply this cut but not C-08, add that clause to the reply-direct path.

**Cut from** `Decide by reasoning, not by matching markers or keywords.  There are`

**...through** `If the user is only reacting, clarifying, or asking, reply
directly — do not manufacture a forward summary.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

#### RCP-06 · COMPRESS · −489 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* Situation A path 1 — Forward · *Golden rules:* 2, 7, 5 · *auditor's own id:* C-06

**Why:** Keeps every content item the summary must carry (including the vary-authorisation default, which is load-bearing) and drops the framing sentences around them.

**Cut from** `Proceed to the two normal response paths:`

**...through** `   said; leave out anything redundant, off-topic, or unsupported.`

**Replace with:**

```
1. **Forward** - call ``call_orchestrator(message=<prose summary>)``
   whenever the user makes a design request, a control instruction, an
   authorisation, or asks for a written proposal or explanation.

   The ``message`` is free-form prose - your judgement on what
   downstream agents need: intent, constraints, strategy preferences,
   use-cases, and whether the user authorised VARYING any of their
   explicit quantitative values (default NOT authorised unless said
   plainly, with any stated scope).  Resolve vague references ("it",
   "that value") to the named parameter and old -> new value, and ground
   every sentence in what the user literally said.
```

#### ⚠️ RCP-12 · DELETE · −470 chars · risk medium

*File:* `agents/receptionist/prompt.md` · *Section:* No second-guessing the chain's reported result · *Golden rules:* 6, 1 · *auditor's own id:* C-12

**Why:** A same-prompt restatement of the anti-fabrication HARD RULE applied to one specific case (an extracted value in a hand-off).

**Risk:** C-10's replacement absorbs this as 'never adjudicate or cast doubt on a value or conclusion the chain reports - relay it'. Do NOT apply this cut unless C-10 (or an equivalent clause) is in place, or the don't-cast-doubt behaviour is lost entirely.

**Cut from** `**No second-guessing the chain's reported result.**  When a Situation B`

**...through** `user later doubts it or asks the chain to verify, that is a Situation-A
forward — the chain re-examines, never you.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> This is a documented production incident, not a restatement. Commit 799d896 ('fix(prompts): tighten DBa scoping, no chain pre-cooking, no chain second-guessing') records an observed 2026-06-05 run in which 'the Receptionist closed by second-guessing the chain in its user reply', and added this exact block ('Do NOT cast doubt ... Do NOT present comparison tables of past sessions'). The cut is a full DELETE whose own risk_note conditions it on C-10, and C-10 is NOT in this review batch - so an owner applying cuts one at a time loses the behaviour entirely. The generic anti-fabrication rule the rationale leans on covers inventing facts, not adjudicating a value the chain correctly reported.
>
> *Safer:* Replace with one line inside the existing anti-fabrication rule: 'Relay a value or conclusion the chain reports - never adjudicate it or cast doubt on it; if the user doubts it, forward so the chain re-examines.'

#### RCP-08 · COMPRESS · −411 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* Situation A path 2 — Reply directly · *Golden rules:* 2, 6, 5 · *auditor's own id:* C-08

**Why:** Five listed trigger conditions reduce to three, and the forward-pointing exception is redundant with the HARD RULE that immediately follows it.

**Cut from** `2. **Reply to the user directly** — produce a plain-text response with`

**...through** `   is an ANSWER that must be forwarded — see the hard rule below.)`

**Replace with:**

```
2. **Reply directly** - plain text, no tool call.  Choose this when the
   request is off-topic, malformed, or needs clarification, or when the
   user is only reacting or asking about an earlier run (you may call
   ``read_agent_history`` first, then answer in plain text).  Short
   reactions ("huh?", "are you there?") are never design directives, and
   you never manufacture a forward summary for a message with no design
   intent.
```

#### RCP-32 · COMPRESS · −386 chars · risk low

*File:* `DC_prompt_fragments/tools_config/blade_sections_visualizer.md` · *Section:* ### Blade-sections visualizer · *Golden rules:* 8, 7 · *auditor's own id:* C-32

**Why:** Shared awareness blurb spliced into 9 prompts; the stacked-vertically/true-angle-of-attack rendering detail and the 'can be read by any agent that can load images' clause matter only to the Tool Caller and DCOI, which have their own per-agent overlays.

**Risk:** HIGH LEVERAGE: this fragment is spliced into all 9 agent prompts (plus 4 5-agent prompts), so the saving multiplies — but so does any regression.

**Cut from** `### Blade-sections visualizer`

**...through** `be rendered and refined cheaply on their own, and can even be the final
deliverable.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Blade-sections visualizer
The system can render just the three blade cross-sections (Inner,
Middle, Outer) as a flat image from an attempt's parameters, via the
Tool Caller's `render_blade_sections`.  It skips full-3D mesh
generation, so it is much faster - a section-focused request can be
rendered on its own and can even be the final deliverable.
```

#### RCP-10 · MERGE · −385 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* ## HARD RULE — you NEVER invent observations, judgements, or recommendations · *Golden rules:* 2, 6, 5 · *auditor's own id:* C-10

**Why:** Collapses the six-item list of forbidden statement types into one clause and folds in the don't-adjudicate rule from the separate paragraph below (see C-12), so the anti-fabrication invariant is stated once, completely.

**Risk:** This is the anti-hallucination patch from real production failures — deliberately kept as a HARD-marked section, only shortened. It also becomes the single home for the rule if C-12 and/or C-29 are applied.

**Cut from** `## HARD RULE — you NEVER invent observations, judgements, or recommendations`

**...through** `down the chain and comes back to them as a real conflict.`

**Replace with:**

```
## HARD RULE - you NEVER invent observations, judgements, or verdicts
You cannot see the mesh, the renders, or the quality-check report, so
never state anything about the design's appearance or quality, and never
adjudicate or cast doubt on a value or conclusion the chain reports -
relay it.  Your own reasoning is not a source of observations.  Quote
the user's actual request and keep anything you infer in its own marked
sentence: an inferred constraint attributed to the user travels down the
chain and comes back as a real conflict.
```

#### RCP-16 · MERGE · −384 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* Situation B — result reporting and plain language · *Golden rules:* 6, 3 · *auditor's own id:* C-16

**Why:** The legacy 'DC parameters written this cycle' instruction here is a third copy (Reporting attempts and the anti-stale paragraph both state it); keeps the error-reporting duty and the standing-directives leak guard.

**Cut from** `If the summary reports a finished result with a "DC parameters written`

**...through** `never reproduce it, its delimiters, or its wording to the user; fold only
its user-relevant substance into your prose.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
If the summary reports an error or exhausted attempts, say what happened
and what was tried.  Stay in plain language: never reveal internal agent
names or architecture, and never reproduce a ``=== STANDING DIRECTIVES
... ===`` block - fold only its user-relevant substance into your prose.
```

#### RCP-20 · COMPRESS · −342 chars · risk low

*File:* `DC_prompt_fragments/dc_config/capabilities_cannot.md` · *Section:* CANNOT list · *Golden rules:* 2, 3, 7 · *auditor's own id:* C-20

**Why:** Six bullets with per-item explanations become four; the mesh-modification and mesh-refinement bullets were the same prohibition split in two.

**Risk:** Shared with the Orchestrator. This is the list the Receptionist must not offer from, so it stays enumerated — only the explanations are cut.

**Cut from** `- Performance / aerodynamic / hydrodynamic analysis — no RPM, thrust,`

**...through** `  ops, welding, hole-filling, normal repair, part pruning, etc.).`

**Replace with:**

```
- Performance analysis (RPM, thrust, flow, pressure, efficiency, CFD)
  or structural analysis (FEA, stress, strength, material, load).
- Anything to the mesh beyond generating it from the parameters: no
  refinement, smoothing, tessellation control, extra camera angles,
  cross-sections, higher-resolution renders, or post-processing.
- Non-OBJ export (STL, STEP, IGES, ...) or format conversion.
- File downloads, uploads, or cloud storage - outputs simply exist on
  disk at the reported paths.
```

#### RCP-28 · SCOPE_PER_AGENT · −296 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* ## End-of-session feedback message (read-only) · *Golden rules:* 8, 7 · *auditor's own id:* C-28

**Why:** Three spliced pieces for one read-only fact; the shared outro even ends with 'fold it into your DH answers', which is Database-Handler wording that does not apply to this agent.

**Cut from** `## End-of-session feedback message (read-only)`

**...through** `$eos_feedback_outro`

**Replace with:**

```
## End-of-session feedback (read-only)
The Orchestrator may append one ``HumanMessage`` with user feedback on
your scope - which attempts you surfaced, how you worded messages, and
whether your forward-vs-reply calls were right.  Treat it as ground
truth.
```

#### RCP-07 · COMPRESS · −262 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* Preserve the force of user directives · *Golden rules:* 2, 7 · *auditor's own id:* C-07

**Why:** Keeps the rule and one example of each direction; drops two of the four softening examples and the closing why-sentence.

**Cut from** `   **Preserve the force of user directives in the summary.**  When`

**...through** `   they see, and a softened directive often gets ignored.`

**Replace with:**

```
   **Preserve the force of user directives.**  "MUST" / "REQUIRED" /
   "you have to" must reach the Orchestrator as the same demand ("the
   user has MANDATED ..."), never softened to "would like" - downstream
   agents never see the user's own wording.
```

#### RCP-18 · COMPRESS · −246 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* ## What this system can and cannot do (HARD) · *Golden rules:* 5, 7, 6 · *auditor's own id:* C-18

**Why:** The 'doing so advertises capabilities the system does not have and sets the user up for frustration' justification and the trailing restatement of the same rule both go; the two slots are untouched.

**Cut from** `## What this system can and cannot do (HARD)`

**...through** `that this system does not do it, and offer only CAN-list alternatives.`

**Replace with:**

```
## What this system can and cannot do (HARD)
Offer follow-ups only from the CAN list; if the user asks for something
on the CANNOT list, say plainly that the system does not do it and offer
a CAN alternative.

**CAN:**
$capabilities_can

**CANNOT (never offer as a next step):**
$capabilities_cannot
```

#### RCP-19 · COMPRESS · −219 chars · risk low

*File:* `DC_prompt_fragments/dc_config/capabilities_can.md` · *Section:* CAN list · *Golden rules:* 6, 7 · *auditor's own id:* C-19

**Why:** Merges the generate and render bullets (one pipeline) and drops the parenthetical listing what agent histories contain, which the read_agent_history section already spells out.

**Risk:** Shared with the Orchestrator.

**Cut from** `- Generate a 3D propeller mesh (.obj) from the 16 design parameters`

**...through** `  the permission rules on varying user-provided numbers.`

**Replace with:**

```
- Generate a 3D propeller mesh (.obj) from the 16 parameters and render
  it from three fixed viewpoints (isometric, top, side) as PNGs.
- Deterministic mesh checks when enabled at startup: watertightness,
  volume, degenerate-face count - nothing more.
- Arithmetic via a built-in calculator.
- Answer questions about earlier runs in this session from other agents'
  histories.
- Regenerate geometry with modified parameter values, subject to the
  permission rules on varying user-provided numbers.
```

#### RCP-24 · COMPRESS · −116 chars · risk low

*File:* `agents/receptionist/prompt.md` · *Section:* Anti-stale block handling · *Golden rules:* 6, 11 · *auditor's own id:* C-24

**Why:** Leads with the invariant instead of the legacy-format special case, and folds the 'if generation failed, list no artifacts' clause into the same rule.

**Risk:** This paragraph is the only statement of the provenance invariant for reported values/paths, so it is compressed rather than cut.

**Cut from** `Anti-stale: if instead a legacy "DC parameters written this cycle" /`

**...through** `Every value/path you state must come from a
``read_attempt`` result or an attached block.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Every value and path you state must come from a ``read_attempt`` result
or an attached block (the legacy "DC parameters written this cycle" /
"Confirmed render files produced this cycle" block counts).  With no
such block, list NO values and NO paths - disk files may be stale.
```

</details>

<details><summary><b>Proposed shape of the shrunk prompt</b></summary>

```
POST-CUT RECEPTIONIST PROMPT — assembled, config PLANNER_FIRST=False, DCII on, BSV on, RAG off
(char counts are exact for the replacement text; tokens = chars/4)

  Role statement (unchanged, lines 1-2) .................  121 ch /  30 tok
  ## Image inputs + on-demand read tools [C-01] .........  728 ch / 182 tok
  ### visualize_3d_model [C-02] .........................  351 ch /  88 tok
  ### propose_attempt [C-03] ............................  669 ch / 167 tok
  ## Two situations / Situation A [C-04] ................  345 ch /  86 tok
  Parameter-name check [C-05] ...........................  867 ch / 217 tok
  1. Forward + what the summary carries [C-06] ..........  667 ch / 167 tok
     Preserve the force of user directives [C-07] .......  255 ch /  64 tok
  2. Reply directly [C-08] ..............................  438 ch / 110 tok
  ## HARD RULE - forward answers to system questions [C-09] 611 ch / 153 tok
  ## HARD RULE - never invent observations [C-10] .......  539 ch / 135 tok
  Questions about an earlier run (read_agent_history) [C-11] 503 ch / 126 tok
  ### Situation B [C-14] ................................  528 ch / 132 tok
  Composition + permission-to-vary [C-15] ...............  458 ch / 115 tok
  Errors + plain language + standing directives [C-16] ..  290 ch /  73 tok
  ## CAN / CANNOT [C-18 + C-19 + C-20] .................. 1301 ch / 325 tok
  ## Parameter Ranges  ** UNCHANGED, NOT CUT ** ......... 1652 ch / 413 tok
  ## Output file locations [C-21] .......................  311 ch /  78 tok
  ## Reporting attempts [C-22] ..........................  604 ch / 151 tok
  Report shortfalls honestly [C-23] .....................  405 ch / 101 tok
  Provenance / anti-stale [C-24] ........................  278 ch /  70 tok
  ## Extraction-only requests are valid forwards [C-25] .  344 ch /  86 tok
  ## Your DBa scope [C-26] — 0 with RAG off (480 ch when on)  0 ch /   0 tok
  ## Routing [C-27] .....................................  233 ch /  58 tok
  ## End-of-session feedback [C-28] .....................  256 ch /  64 tok
  ## Hard constraints - generic [C-29] ..................  239 ch /  60 tok
  (## Hard constraints - DC — DELETED [C-30]) ...........    0 ch /   0 tok
  ## Hard constraints - tools [C-31] ....................  266 ch /  67 tok
  ### Blade-sections visualizer [C-32] ..................  354 ch /  89 tok
  blank lines / separators .............................. ~200 ch /  50 tok
  ------------------------------------------------------------------------
  TOTAL ............................................... ~13,515 ch / ~3,379 tok
  (was 36,775 ch / 9,193 tok — a 63% reduction; 3,859 tok with RAG on)
```

</details>

**Auditor notes.** MEASUREMENT. I reproduced the assembly (prompt.md + every $slot fragment, with <<BSV_ON>>, <<CHAIN_ONLY>> stripped for this non-chain agent, <<HAS_DBA>> stripped for RAG off) and got 36,775 chars / 9,193 tok — matching your 9,204 baseline, so the char counts below are real, not estimated. Every chars_removed is (exact region length) minus (exact length of the replacement I wrote). Sum = 22,780 chars. Note the source file is CRLF; all counts are LF-normalised, i.e. what the model actually sees after Path.read_text().

WHY IT LANDS AT ~3,380 AND NOT 3,000. The 16-parameter table is 1,652 chars (413 tok) and is untouchable per your instruction, and the CAN/CANNOT lists are an enumeration the agent must not paraphrase (they gate what it offers the user). Those two alone are 738 tok — a quarter of the target. I chose to stop at 3,379 rather than blind-squeeze load-bearing rules below the point where I can still defend each sentence. If you want the last ~400 tok, the honest lever is architectural, not editorial — see NEXT LEVER below.

NEXT LEVER (not proposed as a cut — it is a design decision, not an edit). The Situation-A parameter-name check [C-05, 867 chars post-cut] is the single largest agent-owned block left, and it is arguably in the wrong place: the prompt itself says the Receptionist must NOT check ranges because "the pipeline validates ranges downstream", yet it does check names at the door — and the UII, DCIC and DCII all validate names anyway. Deleting it outright would take the Receptionist to ~3,160 tok and remove a whole class of "the door-checker was too strict / too lenient" failures. The cost is that a user who types "fillet_radius = 3" gets a slower round-trip instead of an instant correction. Your call; I did not want to silently drop a user-facing behaviour.

WHAT I DELIBERATELY DID NOT CUT.
- The 16-parameter table (your rule) — untouched, not even reformatted.
- The HARD RULE on forwarding answers to system-posed questions [C-09] stays a HARD-marked section: a wrong call here ends the session with the pipeline stranded, which is the worst failure mode this agent has. Compressed 64%, not removed.
- The anti-fabrication rule [C-10] stays HARD-marked and now absorbs the don't-adjudicate clause, so after C-12 and C-29 it is the single, complete home for the invariant. That is the rule that exists because agents once described renders they never loaded.
- "Preserve the force of user directives" [C-07] — this is the general principle behind the subset-restatement bug you flagged (a softened or partial restatement silently weakens what downstream agents receive), so I compressed it rather than folding it into the summary-content list.
- The provenance rule ("every value/path must come from a read_attempt result or an attached block") [C-24] — barely cut, because it is the only guard against the Receptionist reporting stale on-disk numbers.

DEPENDENCIES BETWEEN CUTS (important if you apply them selectively).
- C-12 (DELETE "No second-guessing") depends on C-10 being applied — C-10's replacement is where the don't-adjudicate clause lands. Applying C-12 alone loses the rule.
- C-13 (DELETE) depends on C-08 — the "never manufacture a forward summary" clause lands in C-08's replacement.
- C-29 (scope the generic constitution) depends on C-10 or the existing lines 160-174 for the anti-fabrication invariant.
- C-04 and C-01 both touch the image gate; either alone is safe, both together is the intended end state.
- C-30 is a pure DELETE of the DC hard-constraints splice for this agent; it is safe only because C-18/C-19/C-20 keep the CANNOT list and C-05 keeps "no parameter outside the table". Do not apply C-30 together with a decision to drop the CANNOT list.

SHARED-FRAGMENT BLAST RADIUS. Four of these cuts touch files other agents splice: capabilities_can.md and capabilities_cannot.md (also the Orchestrator), blade_sections_visualizer.md (all 9 agents plus 4 five-agent prompts — highest leverage in the whole set), routing_receptionist.md and visualize_3d_model.md / propose_attempt.md (Receptionist only, in both topologies). Every fragment I touched is also spliced into agents/5agent/receptionist/prompt_5agents.md, so the 5-agent Receptionist inherits these savings for free — but its own prompt body is a separate file and is NOT covered by any cut here.

ONE MORE HIGH-LEVERAGE SHARED CUT I LEFT TO THE OTHER AUDITS. agents/shared/prompt_fragments/generic_constraints.md is 3,429 chars spliced into 8 agents. I scoped it OUT of the Receptionist (C-29) rather than editing it, because editing it belongs to whoever audits the chain agents. For them: the "DON'T communicate to another agent in plain prose" block is 681 chars and compresses to ~360 without losing the routing-is-a-tool-call invariant, and the two section headings ("### What every agent in any design configurator MAY do (DOs)") cost 130 chars to say "### DOs" / "### DON'Ts". If they apply those, C-29 still supersedes them for this agent.

DEFECT FOUND WHILE READING (worth fixing regardless of shrinking). The "## Your DBa scope" section (prompt.md lines 371-391) sits OUTSIDE the <<HAS_DBA>> region, unlike the "## Searching past saved sessions" block below it. With RAG_ENABLED=False — the configuration you measured — the Receptionist is currently handed 1,292 characters of rules governing database_search / retrieve_user_inputs / retrieve_attempt, three tools it is not bound to that session. C-26 fixes this by wrapping the section in <<HAS_DBA>>...<</HAS_DBA>>; that is why its real saving in your measured config is the full 1,292, not the 812 I reported (I reported the conservative RAG-on figure so the totals do not flatter themselves).

---

### 4.2 Orchestrator — 10,355 → ~3,000 tok

| ID | action | section | −chars | rules | risk | what |
|---|---|---|---:|---|---|---|
| **ORC-01** | COMPRESS | ## Completing a cycle — the Planner is the FINAL APPROVER (H | 2985 | 2,5,6,7,11 | medium | Four sub-blocks (diagram + caption, 'applies to EVERY cycle', 'what you send', 'what the Planner returns', 'when NOT to call') restate one rule — DCOI verdict goes to the Planner before the Receptionist — five times. |
| **ORC-02** | COMPRESS | ### Name the attempt folder(s) and say which to show (HARD) | 2430 | 2,5,6,11 | medium | Six prose 'Rules' bullets each restate one clause of the labelled block the example already shows literally. |
| **ORC-03** | COMPRESS | ## Letting agents decide when to use their own tools | 2416 | 1,2,7,11 | medium | The authorisation bullet spends 1,305 chars enumerating routing permutations (route-via-Planner vs relay-direct, both accepted) when the operative rule is two clauses long. |
| **ORC-04** | COMPRESS | ## When calling an agent | 2411 | 2,4,5,7 | low | 'Write it eloquently', 'there is no fixed template and no menu of allowed phrasings', and the Receptionist-context bullet all restate default model behaviour; only the two emphasised bullets steer away from it. |
| **ORC-05** | SCOPE_PER_AGENT | ## Agent tools at a glance (what each agent reads / writes o | 2282 | 3,6,8,9 | medium | A 2,137-char per-agent tool catalog that duplicates '## Agent Capabilities' twelve lines later; drop the $slot from this prompt only — the fragment is still spliced by the Database Handler. |
| **ORC-06** | MERGE | ## Agent Capabilities — DO NOT exceed these | 2168 | 2,6,8,9,11 | low | Absorbs ORC-05's catalog and the 1,006-char $tool_caller_capabilities fragment into one seven-line roster, which is all a dispatcher needs. |
| **ORC-07** | REPLACE_WITH_EXAMPLES | ### Do NOT seed follow-ups the system cannot deliver | 2144 | 2,3,8 | medium | The full $capabilities_can + $capabilities_cannot catalogs (1,595 chars) are reference material the Receptionist already holds in full; the Orchestrator only needs the boundary. |
| **ORC-08** | SCOPE_PER_AGENT | ## Hard constraints — generic (apply to every agent) | 1938 | 1,6,8 | medium | After <<CHAIN_ONLY>> stripping this fragment is ~1,880 chars of chain-agent DOs/DON'Ts (forward-to-your-next, carry STANDING DIRECTIVES, don't-bounce-permission) that a hub does not perform; drop the $slot here only — eight other prompts keep it. |
| **ORC-09** | MERGE | ### Attempt folders and ``Current attempt:`` propagation / # | 1812 | 2,6,11 | medium | Two adjacent sections state the same ownership rule (DCIC creates, Orchestrator is fallback) and the same label contract from opposite directions. |
| **ORC-10** | COMPRESS | ## Precision refine loop — relay DCOI shape-feedback straigh | 1729 | 2,7,11 | low | The three routing branches are the content; the surrounding rationale ('gives the DCOI a prior render to measure progress against', 're-stamped automatically') does not change behaviour. |
| **ORC-13** | COMPRESS | ### Recognise Planner actionable instructions | 1684 | 1,2,7,11 | low | Three sections (recognise-the-plan, don't-ping-pong, don't-misattribute) are one rule — read the sender header and act on it — inflated with a worked ping-pong trace. |
| **ORC-11** | COMPRESS | ### Global / ring … ### Outer blade section | 1609 | 3,11 | medium | Compact reformat only — all 16 names, types and ranges stay inline, and the reformat ADDS the two facts that caused real bugs (own-chord percentages, middlePos span fraction) which today live in modelling_notes.md the Orchestrator never sees. |
| **ORC-12** | SCOPE_PER_AGENT | ## The Natural Pipeline (incl. the <<PF_ON>>/<<PF_OFF>> kick | 1608 | 6,8,10,11 | low | The 1,108-char $pipeline_flow fragment restates the chain and then explains it a second time for the Planner's benefit, and the PF blocks immediately below restate the kick-off a third time; the Planner keeps the fragment. |
| **ORC-14** | COMPRESS | ### Available routing tools | 1586 | 9,11 | low | Tool descriptions carrying prose the tool schema already carries ('Situation B', 'the dispatcher delivers their eventual report back to you in your next turn'); one line each is enough. |
| **ORC-15** | SCOPE_PER_AGENT | ## Hard constraints — DC-specific | 1343 | 6,8 | low | Every one of its four clauses is already stated in this same prompt by $capabilities_cannot (ORC-07), $invalid_parameter_examples (ORC-31) and $geometry_modification_rule (ORC-22); drop the $slot here only — seven other prompts keep it. |
| **ORC-16** | SCOPE_PER_AGENT | ## Hard constraints — tool-specific | 1321 | 8,9 | low | The read-tool path rules and the render-reuse detail are for agents that call those tools; the Orchestrator only needs the append-only invariant (it holds new_attempt) and the calculate rule. |
| **ORC-17** | COMPRESS | ## Preserving user directives in hand-offs (HARD) | 1109 | 2,7 | low | A 350-char worked example about the database mandate teaches nothing the one-line rule does not. |
| **ORC-18** | COMPRESS | ## Extraction-only user requests (answer, don't start a desi | 1084 | 2,7,8 | low | The paragraph on why the UII extraction is broader than the DC parameter set is Planner/DCIC business and does not change any Orchestrator decision. |
| **ORC-19** | COMPRESS | ## Escalation Hierarchy (CRITICAL) | 1016 | 5,6,11 | low | The numbered authority list and the '### Rules' bullets say the same four things twice; 'CRITICAL' competes with the four other HARD/CRITICAL banners in this prompt. |
| **ORC-20** | COMPRESS | ## Route through the User Input Inspector on new meaningful  | 913 | 2,11 | low | The taxonomy of 'meaningful content' plus a PF_ON/PF_OFF pair explaining the same kick-off twice collapses to one sentence. |
| **ORC-21** | COMPRESS | ### Verify the diagnosis BEFORE you relay it (HARD) | 903 | 1,7 | low | Keeps the incident-derived principle (check the tool's return string before parroting the agent's account) and drops the three-way phrasing catalog around it. |
| **ORC-22** | SCOPE_PER_AGENT | ## Geometry Modification Rule (HARD) | 805 | 2,6,8 | low | The eight-item forbidden-operations list is one principle (no post-processing exists) plus examples that $capabilities_cannot already carries; the DCOI keeps the fragment. |
| **ORC-23** | SCOPE_PER_AGENT | <<BSV_ON>> blade-sections visualizer block | 800 | 8,9 | low | The Orchestrator never calls render_blade_sections and never decides the deliverable; the one fact it needs (cross-sections only, far faster, can be the deliverable) is folded into the ORC-06 Tool Caller line, and the fragment stays for the eight agents that do act on it. |
| **ORC-24** | COMPRESS | (unheaded paragraph after the pipeline blocks) | 753 | 2,6 | low | The 'At COMPLETION your next hop is the Planner' sentence forward-references a whole section that states it three more times. |
| **ORC-25** | COMPRESS | (the two mandatory UII hand-off lines) | 742 | 11 | medium | Kept nearly intact — this is a genuine hard precondition (the UII's tools error out without the paths); only the restated justification is trimmed. |
| **ORC-26** | COMPRESS | (the "Meaningful" judgement paragraph) | 717 | 2,4,6 | low | Restates ORC-20's rule from the negative side and then tells the model to 'use judgement', which is default behaviour. |
| **ORC-27** | COMPRESS | ### User questions about observable facts (non-design questi | 708 | 2,7 | low | Three examples plus a why-the-Receptionist-forwards-these paragraph reduce to two examples and the routing rule. |
| **ORC-28** | COMPRESS | ## Anti-Hallucination Rules | 674 | 6 | low | Rules 1, 2 and 5 are already stated in ORC-04, ORC-07 and ORC-06 respectively; only 3, 4 and 6 add anything. |
| **ORC-29** | COMPRESS | ## You ORIGINATE nothing — you RELAY and SHAPE | 621 | 5,6 | low | Duplicates the 'relay evidence, never frame the plan' bullet in ORC-04; the reassurance paragraph exists only to undo the section's own over-broad heading. |
| **ORC-30** | COMPRESS | _CHAIN_ACCESS_ON (## Inter-agent communication visibility (E | 585 | 4,10,11 | low | Describes the delivery mechanism the model can see for itself; only the do-not-echo rule steers behaviour. |
| **ORC-31** | SCOPE_PER_AGENT | (the $invalid_parameter_examples slot line) | 406 | 2,6,8 | low | Inlined at half the length; the fragment stays for the Planner, Receptionist and Conductor. |
| **ORC-32** | MERGE | ## Output format | 273 | 5,12 | low | Net-neutral on size but load-bearing: this is where the 'prose without a routing tool call halts the pipeline' rule lands once ORC-08 drops $hard_constraints_generic. |
| **ORC-33** | COMPRESS | ## The $parameter_count Design Parameters — the ONLY paramet | 168 | 4,5 | low | The heading already says 'the only ones that exist'; 'exact spelling' is default behaviour for a name list. |

<details><summary><b>Full text of each change</b></summary>

#### ORC-01 · COMPRESS · −2985 chars · risk medium

*File:* `agents/orchestrator/prompt.md` · *Section:* ## Completing a cycle — the Planner is the FINAL APPROVER (HARD) · *Golden rules:* 2, 5, 6, 7, 11

**Why:** Four sub-blocks (diagram + caption, 'applies to EVERY cycle', 'what you send', 'what the Planner returns', 'when NOT to call') restate one rule — DCOI verdict goes to the Planner before the Receptionist — five times.

**Risk:** This is the ONLY statement of the Planner-as-final-approver protocol; the replacement keeps the hop diagram, the evidence-not-recommendation rule, and all three Planner reply modes. Test this section first.

**Cut from** `## Completing a cycle — the Planner is the FINAL APPROVER (HARD)`

**...through** `composes the user-facing wording — do NOT write the final user
message yourself.  The dispatcher delivers the Receptionist's
composed text to the user.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Completing a cycle — the Planner approves last (HARD)
When the DCOI returns a verdict you call the **Planner**, not the Receptionist:

    DCOI → you → Planner → you → Receptionist → user

Give it facts only: every attempt folder produced this cycle (number + absolute path) and the DCOI's verdict. Do NOT recommend which to show — the Planner picks. It replies APPROVE (forward its pick + one-line reason to the Receptionist), REVISE (execute its recovery sequence), or REPLY DIRECTLY (hand its answer to the Receptionist). Mid-cycle steps it already planned need no check-in, and its own direct answer needs no re-approval.
```

#### ORC-02 · COMPRESS · −2430 chars · risk medium

*File:* `agents/orchestrator/prompt.md` · *Section:* ### Name the attempt folder(s) and say which to show (HARD) · *Golden rules:* 2, 5, 6, 11

**Why:** Six prose 'Rules' bullets each restate one clause of the labelled block the example already shows literally.

**Risk:** The labelled-line contract with the Receptionist is load-bearing; the replacement keeps the literal shape, the number+absolute-path requirement, the Planner-owns-the-pick rule, and the no-guessing/no-fabrication clause.

**Cut from** `### Name the attempt folder(s) and say which to show (HARD)
The Receptionist does NOT scan the filesystem for your results — it`

**...through** `  * This does not relax Anti-Hallucination rule 4: list only attempts
    whose artefacts were actually produced/observed this run.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Name the attempt folder(s) (HARD)
The Receptionist never scans the filesystem — it only sees what you write. Your ``call_receptionist`` message MUST carry, on their own lines:

    Attempts this cycle:
    - Attempt 3 — <absolute attempt folder path>
    - Attempt 4 — <absolute attempt folder path>
    Show to user: Attempt 4  (Planner approved — <reason>)

Number AND full absolute path for every attempt, single-attempt cycles included. The pick and its reason are the Planner's — transcribe them even when the user asked for a different attempt. Unsure of a path? Recover it with ``read_agent_history``; never guess, never omit, never list an attempt you did not see produced.
```

#### ORC-03 · COMPRESS · −2416 chars · risk medium

*File:* `agents/orchestrator/prompt.md` · *Section:* ## Letting agents decide when to use their own tools · *Golden rules:* 1, 2, 7, 11

**Why:** The authorisation bullet spends 1,305 chars enumerating routing permutations (route-via-Planner vs relay-direct, both accepted) when the operative rule is two clauses long.

**Risk:** Keeps the soft-target marker, the either-source rule, and the 'don't manufacture a Planner directive' patch; drops only the worked example of each permutation.

**Cut from** `## Letting agents decide when to use their own tools
Each agent owns its tools and decides when to invoke them.`

**...through** `NOT need to manufacture a Planner directive on top of a direct
user authorisation.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Tell agents what they cannot infer
Three things only you can supply:
- Whether the user supplied new inputs this turn (so the DCIC knows whether to re-read ``extracted_inputs.txt``).
- Where a parameter change came from — user, Planner, or another agent. Name the source; the DCII judges authority from it.
- Any user permission to vary a stated value, including a **soft target** (a value subordinated to a goal; the UII marks it ``SOFT TARGET``). Quote the user's scope. Either the hand-off or the extraction's DESIGN INTENT section is sufficient — never manufacture a Planner directive on top of a direct user authorisation.
```

#### ORC-04 · COMPRESS · −2411 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ## When calling an agent · *Golden rules:* 2, 4, 5, 7

**Why:** 'Write it eloquently', 'there is no fixed template and no menu of allowed phrasings', and the Receptionist-context bullet all restate default model behaviour; only the two emphasised bullets steer away from it.

**Cut from** `## When calling an agent
Each ``call_<agent>(message)`` tool hands control to that agent.`

**...through** `JSON, full extractions) lives on disk — reference it by role, don't
  paste it.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## When calling an agent
Issuing a ``call_<agent>(message)`` ends your turn. The ``message`` is free-form prose — no template. Carry everything the recipient plausibly needs and nothing invented: no numeric value you made up, no capability outside that agent's tools. Raw data (parameter JSON, full extractions) lives on disk — point at it, do not paste it.
- **To the Planner, relay evidence, never frame the plan** — no goals, scope, caps, or strategies of yours. After a failure: which agent failed, the error verbatim, what was tried.
- **Another agent's proposal is evidence, not your framing.** If the DCOI already named fixes, quote them or point the Planner at ``read_agent_history('dc_output_inspector')``.
```

#### ORC-05 · SCOPE_PER_AGENT · −2282 chars · risk medium

*File:* `agents/orchestrator/prompt.md` · *Section:* ## Agent tools at a glance (what each agent reads / writes on its own) · *Golden rules:* 3, 6, 8, 9

**Why:** A 2,137-char per-agent tool catalog that duplicates '## Agent Capabilities' twelve lines later; drop the $slot from this prompt only — the fragment is still spliced by the Database Handler.

**Risk:** It is the only place stating 'new_attempt is bound to the DCIC and to you only as a fallback'; that clause survives in the ORC-06 roster and in $routing_hub (ORC-14).

**Cut from** `## Agent tools at a glance (what each agent reads / writes on its own)
Knowing this lets you tell each agent only what they actually need.`

**...through** `$agent_tools_overview`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

#### ORC-06 · MERGE · −2168 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ## Agent Capabilities — DO NOT exceed these · *Golden rules:* 2, 6, 8, 9, 11

**Why:** Absorbs ORC-05's catalog and the 1,006-char $tool_caller_capabilities fragment into one seven-line roster, which is all a dispatcher needs.

**Cut from** `## Agent Capabilities — DO NOT exceed these
The workflow is strictly bounded by what each agent can actually do.`

**...through** `metrics are exactly those produced by the Tool Caller's bound
  inspection tool (see the tool inventory) — no others exist.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Who does what — never ask an agent for more
- **Planner** — sole owner of strategy, recovery plans, and end-of-cycle approval.
- **UII** — reads the user's input files; writes ``extracted_inputs.txt``.
- **DCIC** — opens the attempt folder (it holds ``new_attempt``) and writes its ``parameters.json``; the only way to change geometry.
- **DCII** — checks those parameters against user intent and that agent-originated changes came from an authorised source.
- **Tool Caller** — ``generate_and_render_propeller`` (16 params + folder → mesh, 3 renders, QC) and ``render_blade_sections`` (cross-sections only; far faster, and can be the deliverable). Cannot repair, remesh, or rename.
- **DCOI** — loads renders (``view_images``) and judges them; the only mesh metrics are watertightness, volume, degenerate-face count.
- **Receptionist** — composes every user-facing message.
All agents also have ``calculate``, ``list_attempts``, ``read_attempt``.
```

#### ORC-07 · REPLACE_WITH_EXAMPLES · −2144 chars · risk medium

*File:* `agents/orchestrator/prompt.md` · *Section:* ### Do NOT seed follow-ups the system cannot deliver · *Golden rules:* 2, 3, 8

**Why:** The full $capabilities_can + $capabilities_cannot catalogs (1,595 chars) are reference material the Receptionist already holds in full; the Orchestrator only needs the boundary.

**Risk:** Removes the fleet CAN/CANNOT lists from this prompt; the Receptionist — which actually composes the user text — still splices both fragments unchanged.

**Cut from** `### Do NOT seed follow-ups the system cannot deliver
Your technical summary must not propose or hint at capabilities this`

**...through** `Receptionist will relay them to the user.  If a genuine next step
exists, describe it in terms of the real capabilities only.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Do NOT seed follow-ups the system cannot deliver
The system can ONLY: build a mesh from the 16 parameters, render three fixed views, run watertight / volume / degenerate-face checks, do arithmetic, read this session's agent histories, and regenerate with changed parameters. No performance or CFD, no FEA / material / tolerance work, no extra views or cross-sections, no mesh post-processing, no format but OBJ, no downloads. Never write "if the user wants performance estimates …" — the Receptionist will pass it straight to the user.
```

#### ORC-08 · SCOPE_PER_AGENT · −1938 chars · risk medium

*File:* `agents/orchestrator/prompt.md` · *Section:* ## Hard constraints — generic (apply to every agent) · *Golden rules:* 1, 6, 8

**Why:** After <<CHAIN_ONLY>> stripping this fragment is ~1,880 chars of chain-agent DOs/DON'Ts (forward-to-your-next, carry STANDING DIRECTIVES, don't-bounce-permission) that a hub does not perform; drop the $slot here only — eight other prompts keep it.

**Risk:** The 'prose without a routing tool call is silently discarded and the pipeline halts' rule lives here; ORC-32 moves that exact wording into ## Output format so it is not lost. The do-not-loop rule survives in ORC-19.

**Cut from** `## Hard constraints — generic (apply to every agent)`

**...through** `$hard_constraints_generic`

**Replace with:**

```
## Hard rules
- Never state an observation you cannot source to a tool result, an agent's history, or the user's own words.
- Only the tools listed below exist. If you cannot do something with them, escalate — never invent a tool, script, file, or fallback policy.
- Answer in English.
```

#### ORC-09 · MERGE · −1812 chars · risk medium

*File:* `agents/orchestrator/prompt.md` · *Section:* ### Attempt folders and ``Current attempt:`` propagation / ### Hand-offs you originate for a design cycle MUST carry ``Current attempt:`` · *Golden rules:* 2, 6, 11

**Why:** Two adjacent sections state the same ownership rule (DCIC creates, Orchestrator is fallback) and the same label contract from opposite directions.

**Risk:** Preserves the Tool Caller's hard precondition (both labels or it escalates) and the no-Current-attempt-for-a-new-DCIC-generation rule, which the precision refine loop (ORC-10) also depends on.

**Cut from** `### Attempt folders and ``Current attempt:`` propagation
Every design generation lives in an attempt folder under`

**...through** `the labels; this rule covers only hand-offs you originate.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### ``Current attempt:`` labels
Every generation lives in a folder under ``logs/attempts/``, and the **DCIC opens it**. A ``call_dc_input_creator`` hand-off for a NEW generation therefore carries NO ``Current attempt:`` — just the slug and intent. You hold ``new_attempt`` only as a fallback for when the DCIC cannot create one.

Hand-offs YOU originate to the DCII, Tool Caller or DCOI must carry ``Current attempt: <absolute path>``; ``call_tool_caller`` must also carry ``Parameters file: <Current attempt>/parameters.json`` (it escalates without both). Never guess a path — if unsure, route through the DCIC, which emits the labels itself.
```

#### ORC-10 · COMPRESS · −1729 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ## Precision refine loop — relay DCOI shape-feedback straight to the DCIC · *Golden rules:* 2, 7, 11

**Why:** The three routing branches are the content; the surrounding rationale ('gives the DCOI a prior render to measure progress against', 're-stamped automatically') does not change behaviour.

**Cut from** `## Precision refine loop — relay DCOI shape-feedback straight to the DCIC`

**...through** `You never originate the shape feedback or the parameter moves — you relay the
DCOI's prose to the DCIC, which owns translating it into shape-param changes.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Precision refine loop
While a ``=== STANDING DIRECTIVES ===`` block from the Planner rides the hand-offs, the DCOI iterates against the user's sketch. Route by what it asks for:
- REVISE (a shape change) → straight to ``call_dc_input_creator`` with the DCOI's visual-gap prose and NO ``Current attempt:`` (each round is a fresh attempt). Do not re-plan per round.
- APPROVE or a plateau / ceiling report → end of cycle: call the Planner.
- ESCALATE → call the Planner for a recovery plan.
```

#### ORC-13 · COMPRESS · −1684 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ### Recognise Planner actionable instructions · *Golden rules:* 1, 2, 7, 11

**Why:** Three sections (recognise-the-plan, don't-ping-pong, don't-misattribute) are one rule — read the sender header and act on it — inflated with a worked ping-pong trace.

**Cut from** `### Recognise Planner actionable instructions
Every incoming message is prefixed with ``[Incoming from: <sender>]``.`

**...through** `attributable to the user are ones the user literally said (as relayed by
the Receptionist).`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Read the ``[Incoming from: <sender>]`` header first
A Planner message naming a next agent IS the plan — forward to that agent with its direction intact. Never send the Planner facts it already saw this turn; consult it again only when new evidence has arrived. Attribute correctly: a sentence from the Planner is the Planner speaking even when it paraphrases the user — write "The Planner recommends …", not "The user requests …".
```

#### ORC-11 · COMPRESS · −1609 chars · risk medium

*File:* `DC_prompt_fragments/dc_config/parameters.md` · *Section:* ### Global / ring … ### Outer blade section · *Golden rules:* 3, 11

**Why:** Compact reformat only — all 16 names, types and ranges stay inline, and the reformat ADDS the two facts that caused real bugs (own-chord percentages, middlePos span fraction) which today live in modelling_notes.md the Orchestrator never sees.

**Risk:** This file is spliced by NINE prompts (7 chain agents + conductor + creator), so it must be reviewed jointly with the other eight audits — it is not an Orchestrator-local edit. Never remove it or move it behind a tool.

**Cut from** `### Global / ring
 1. bladeCount         (integer)              — Number of blades [3; 6]`

**...through** `16. outerAngle      (degrees)                   — Angle of attack [2; 25]`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Ring: bladeCount int [3;6] · impellerRadius mm [60;80] · impellerThickness mm wall [1;5]
(Ring HEIGHT is not a parameter — derived to fit the outer blade section.)

Blade sections — Thickness/Camber are % of THAT section's OWN chord (a pinned chord caps absolute size); MaxPos is an integer in tenths of chord; Angle is angle of attack in degrees.
- inner: innerThickness [3;24] · innerMaxPos [2;8] · innerCamber [0;9] · innerChord mm [3;11] · innerAngle [2;25]
- middle: middlePos [0.3;0.7] · middleChord mm [10;30] · middleAngle [2;25]
- outer: outerThickness [3;24] · outerMaxPos [2;8] · outerCamber [0;9] · outerChord mm [10;30] · outerAngle [2;25]

middlePos is a fraction of blade SPAN from the 4 mm root: radius = 4 + middlePos·(impellerRadius − 4) mm (0 = root, 1 = tip). The middle section has no profile shape of its own — it is interpolated.
```

#### ORC-12 · SCOPE_PER_AGENT · −1608 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ## The Natural Pipeline (incl. the <<PF_ON>>/<<PF_OFF>> kick-off blocks) · *Golden rules:* 6, 8, 10, 11

**Why:** The 1,108-char $pipeline_flow fragment restates the chain and then explains it a second time for the Planner's benefit, and the PF blocks immediately below restate the kick-off a third time; the Planner keeps the fragment.

**Cut from** `## The Natural Pipeline
$pipeline_flow`

**...through** `ESCALATEs because it hit a problem it cannot resolve.<</PF_OFF>>`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## The pipeline
user → Receptionist → **you** → User Input Inspector → Planner → DC Input Creator → <<DCII_ONLY>>DC Input Inspector → <</DCII_ONLY>>Tool Caller → DC Output Inspector → **you** → Planner → Receptionist → user

Each agent forwards to the next on its own. You kick the chain off by calling the User Input Inspector; control returns to you only when the DCOI has a verdict or an agent escalates.
```

#### ORC-14 · COMPRESS · −1586 chars · risk low

*File:* `agents/shared/prompt_fragments/routing_orchestrator.md` · *Section:* ### Available routing tools · *Golden rules:* 9, 11

**Why:** Tool descriptions carrying prose the tool schema already carries ('Situation B', 'the dispatcher delivers their eventual report back to you in your next turn'); one line each is enough.

**Cut from** `### Available routing tools
You can dispatch to every agent in the system:`

**...through** `Normally the DCIC opens the attempt itself — do not pre-open one.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Your routing tools
One call ends your turn; the dispatcher brings the chain's eventual report back to you.
- ``call_receptionist(message)`` — end a cycle: hand back a technical summary for the user.
- ``call_planner(message)`` — start a cycle, get a recovery plan, or get end-of-cycle approval.
- ``call_user_input_inspector(message)`` — (re-)extract inputs into ``extracted_inputs.txt``.
- ``call_dc_input_creator(message)`` — open a new attempt and write its ``parameters.json``.
<<DCII_ONLY>>- ``call_dc_input_inspector(message)`` — re-validate an attempt's parameters.
<</DCII_ONLY>>- ``call_tool_caller(message)`` — (re-)generate + render an attempt.
- ``call_dc_output_inspector(message)`` — (re-)judge an attempt's renders.
- ``new_attempt(slug, description)`` — fallback ONLY, when the DCIC cannot open its own attempt.
```

#### ORC-15 · SCOPE_PER_AGENT · −1343 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ## Hard constraints — DC-specific · *Golden rules:* 6, 8

**Why:** Every one of its four clauses is already stated in this same prompt by $capabilities_cannot (ORC-07), $invalid_parameter_examples (ORC-31) and $geometry_modification_rule (ORC-22); drop the $slot here only — seven other prompts keep it.

**Cut from** `## Hard constraints — DC-specific`

**...through** `$hard_constraints_dc`

**Replace with:** *(nothing — pure deletion)*

#### ORC-16 · SCOPE_PER_AGENT · −1321 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ## Hard constraints — tool-specific · *Golden rules:* 8, 9

**Why:** The read-tool path rules and the render-reuse detail are for agents that call those tools; the Orchestrator only needs the append-only invariant (it holds new_attempt) and the calculate rule.

**Cut from** `## Hard constraints — tool-specific`

**...through** `$hard_constraints_tools`

**Replace with:**

```
- Attempt folders are append-only: never rewrite an existing attempt's ``parameters.json`` or mesh. To build on an old parameter set, have the DCIC open a NEW attempt.
- Route arithmetic through ``calculate``, batching the expressions into one call.
```

#### ORC-17 · COMPRESS · −1109 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ## Preserving user directives in hand-offs (HARD) · *Golden rules:* 2, 7

**Why:** A 350-char worked example about the database mandate teaches nothing the one-line rule does not.

**Cut from** `## Preserving user directives in hand-offs (HARD)`

**...through** `their original force — agents downstream cannot read the user's
original message; they only see what you write.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Relay user directives at full strength (HARD)
Downstream agents never see the user's words — only yours. When the user mandates, forbids, scopes, or authorises something, pass it on with its original force and, when short, its original words. Never soften "MUST" into "should consider" or "emphasizes".
```

#### ORC-18 · COMPRESS · −1084 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ## Extraction-only user requests (answer, don't start a design run) · *Golden rules:* 2, 7, 8

**Why:** The paragraph on why the UII extraction is broader than the DC parameter set is Planner/DCIC business and does not change any Orchestrator decision.

**Cut from** `## Extraction-only user requests (answer, don't start a design run)`

**...through** `that broader output IS the deliverable; the DCIC/DCII filtering to the
DC-applicable subset only matters once a design generation is requested.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Extraction-only requests
"How many blades are in my sketch?", "list my quantitative inputs" — still kick off the UII as usual; the Planner recognises the ask and answers directly. Do not let it run on into DCIC / Tool Caller / DCOI.
```

#### ORC-19 · COMPRESS · −1016 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ## Escalation Hierarchy (CRITICAL) · *Golden rules:* 5, 6, 11

**Why:** The numbered authority list and the '### Rules' bullets say the same four things twice; 'CRITICAL' competes with the four other HARD/CRITICAL banners in this prompt.

**Cut from** `## Escalation Hierarchy (CRITICAL)
The workflow has exactly THREE decision authorities, in this order:`

**...through** `- If the Planner has no new angle to offer, call the Receptionist
  with a question for the user.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Escalation
You execute; the **Planner** decides recovery strategy; the **user** is the final authority once the Planner is out of angles. The instant an agent escalates, call ``call_planner`` with what failed — do not patch it yourself, do not retry. If the same class of failure recurs, call the Planner again with the new evidence; if it has none, ask the user via the Receptionist.
```

#### ORC-20 · COMPRESS · −913 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ## Route through the User Input Inspector on new meaningful user content · *Golden rules:* 2, 11

**Why:** The taxonomy of 'meaningful content' plus a PF_ON/PF_OFF pair explaining the same kick-off twice collapses to one sentence.

**Cut from** `## Route through the User Input Inspector on new meaningful user content
Whenever the user has supplied NEW meaningful content this turn —`

**...through** `recovery, you still route to the UII first if the user added new
content to the conversation.<</PF_OFF>>`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## New user content → the UII first
Whenever the user supplied something this turn that could change how a downstream agent acts — a value, constraint, goal, authorisation, or qualitative direction — kick off ``call_user_input_inspector`` so it rewrites ``extracted_inputs.txt``. This holds when you resume mid-chain after a recovery too.
```

#### ORC-21 · COMPRESS · −903 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ### Verify the diagnosis BEFORE you relay it (HARD) · *Golden rules:* 1, 7

**Why:** Keeps the incident-derived principle (check the tool's return string before parroting the agent's account) and drops the three-way phrasing catalog around it.

**Cut from** `### Verify the diagnosis BEFORE you relay it (HARD)`

**...through** `(network, a missing file the agent did not author, an OS error) is "the
tool failed" worth relaying upstream.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Verify a self-exonerating diagnosis before relaying it
When an agent escalates claiming "the tool is broken", read the tool's actual return string via ``read_agent_history``. If it names a missing or malformed argument, the fault is that agent's call — re-call it, quoting the error verbatim. Only a genuine runtime fault (network, OS, a file the agent did not author) is a tool failure worth relaying.
```

#### ORC-22 · SCOPE_PER_AGENT · −805 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ## Geometry Modification Rule (HARD) · *Golden rules:* 2, 6, 8

**Why:** The eight-item forbidden-operations list is one principle (no post-processing exists) plus examples that $capabilities_cannot already carries; the DCOI keeps the fragment.

**Risk:** BUG: the fragment says 'the 17 design parameters' twice — stale since the impellerHeight removal (16 now). It is also spliced into the DCOI prompt, which still reads the wrong count.

**Cut from** `## Geometry Modification Rule (HARD)`

**...through** `$geometry_modification_rule`

**Replace with:**

```
## Geometry rule (HARD)
Geometry changes ONLY by changing the 16 parameters via the DC Input Creator and regenerating. There is no mesh editing, repair, remeshing, or post-processing — if the DCOI reports a problem, ask the Planner for a parameter change.
```

#### ORC-23 · SCOPE_PER_AGENT · −800 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* <<BSV_ON>> blade-sections visualizer block · *Golden rules:* 8, 9

**Why:** The Orchestrator never calls render_blade_sections and never decides the deliverable; the one fact it needs (cross-sections only, far faster, can be the deliverable) is folded into the ORC-06 Tool Caller line, and the fragment stays for the eight agents that do act on it.

**Cut from** `<<BSV_ON>>
$blade_sections_visualizer`

**...through** `<</BSV_ON>><<BSV_OFF>>$blade_sections_visualizer_off<</BSV_OFF>>`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

#### ORC-24 · COMPRESS · −753 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* (unheaded paragraph after the pipeline blocks) · *Golden rules:* 2, 6

**Why:** The 'At COMPLETION your next hop is the Planner' sentence forward-references a whole section that states it three more times.

**Cut from** `You therefore do NOT drive the pipeline step-by-step.  Trust the`

**...through** `makes sense to re-route to that same agent with the missing piece,
rather than continuing forward as if it had finished.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
You do not drive the pipeline step by step — the agents route between themselves and control returns to you only on completion or escalation. Before choosing the next hop, look at what the previous turn actually produced: an escalation usually means the expected artifact is still missing, so re-routing to that same agent with the missing piece beats moving forward.
```

#### ORC-25 · COMPRESS · −742 chars · risk medium

*File:* `agents/orchestrator/prompt.md` · *Section:* (the two mandatory UII hand-off lines) · *Golden rules:* 11

**Why:** Kept nearly intact — this is a genuine hard precondition (the UII's tools error out without the paths); only the restated justification is trimmed.

**Risk:** Do not shorten further. If the labelled lines or the VERBATIM instruction go, the UII hard-fails on turn 1 of every session.

**Cut from** `Every ``call_user_input_inspector`` message MUST carry these two lines: the`

**...through** `the UII writes it, and on the first turn of a session it is not there yet.
Do not paste file content; the UII reads the files itself.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Every ``call_user_input_inspector`` message MUST carry these two lines — its tools refuse to run without them. Take the directory VERBATIM from the ``Input file directory:`` line of your own incoming message; never invent or shorten it:

    Input directory: <that path>
    Extraction output file: <that path>/extracted_inputs.txt

The extraction file is a destination, not a precondition — on turn 1 it does not exist yet.
```

#### ORC-26 · COMPRESS · −717 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* (the "Meaningful" judgement paragraph) · *Golden rules:* 2, 4, 6

**Why:** Restates ORC-20's rule from the negative side and then tells the model to 'use judgement', which is default behaviour.

**Cut from** `"Meaningful" is judged by whether the content plausibly changes how a`

**...through** `purely to try a different parameter direction), skip the UII and hand
off directly to the agent the Planner's recovery plan names.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Pure reactions ("huh?", "thanks"), out-of-scope asks, and repeats of what the extraction already holds are not new: skip the UII and hand off to the agent the Planner's recovery plan names. When in doubt, route through the UII.
```

#### ORC-27 · COMPRESS · −708 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ### User questions about observable facts (non-design questions) · *Golden rules:* 2, 7

**Why:** Three examples plus a why-the-Receptionist-forwards-these paragraph reduce to two examples and the routing rule.

**Cut from** `### User questions about observable facts (non-design questions)`

**...through** `then return a grounded answer for you to pass to the Receptionist.
Never compose the answer yourself from memory.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Questions about what the system observed
"What does the model look like?", "what did the checks say?" → route to the Planner; it can read the agent histories and return a grounded answer. Never compose one from memory.
```

#### ORC-28 · COMPRESS · −674 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ## Anti-Hallucination Rules · *Golden rules:* 6

**Why:** Rules 1, 2 and 5 are already stated in ORC-04, ORC-07 and ORC-06 respectively; only 3, 4 and 6 add anything.

**Risk:** Rule 4 (don't report artifacts you did not observe) is a known-failure patch — it is kept as the first sentence, and ORC-02 also restates it for the attempt list.

**Cut from** `## Anti-Hallucination Rules
1. Do not seed the Planner with your own recovery options, goals,`

**...through** `6. When the failure is outside the design workflow, ask the user
   directly via the Receptionist.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Never invent
Report only artifacts you saw produced this run. Match the recovery to the failure class — a transport or environment failure is not fixed by changing input content. A failure outside the design workflow goes to the user via the Receptionist.
```

#### ORC-29 · COMPRESS · −621 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ## You ORIGINATE nothing — you RELAY and SHAPE · *Golden rules:* 5, 6

**Why:** Duplicates the 'relay evidence, never frame the plan' bullet in ORC-04; the reassurance paragraph exists only to undo the section's own over-broad heading.

**Cut from** `## You ORIGINATE nothing — you RELAY and SHAPE
You are a coordinator, not a designer.`

**...through** `Passing on the Receptionist's context, quoting an agent's decision, or
explaining where a change originated is your job, not a violation.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
You originate no design content — no numbers, no directional suggestions. Those come from the user, the Planner, or another agent's output. You DO shape communication: what each agent sees, how it is summarised, and who authored it.
```

#### ORC-30 · COMPRESS · −585 chars · risk low

*File:* `agents/orchestrator/orchestrator.py` · *Section:* _CHAIN_ACCESS_ON (## Inter-agent communication visibility (ENABLED)) · *Golden rules:* 4, 10, 11

**Why:** Describes the delivery mechanism the model can see for itself; only the do-not-echo rule steers behaviour.

**Risk:** This literal lives in Python (agents/orchestrator/orchestrator.py lines 102-118), not in a .md fragment — the System Prompts UI cannot edit it. The _CHAIN_ACCESS_OFF twin below can be halved the same way.

**Cut from** `## Inter-agent communication visibility (ENABLED)
Whenever control returns to you (a new incoming message from the`

**...through** `repeat it back verbatim to other agents or to the Receptionist; it is
for your own situational awareness.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Inter-agent chain log (ENABLED)
Incoming messages are prefixed with the inter-agent exchanges that happened while you waited. Use it for your own awareness; never repeat it verbatim to another agent or the Receptionist.
```

#### ORC-31 · SCOPE_PER_AGENT · −406 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* (the $invalid_parameter_examples slot line) · *Golden rules:* 2, 6, 8

**Why:** Inlined at half the length; the fragment stays for the Planner, Receptionist and Conductor.

**Cut from** `$invalid_parameter_examples`

**...through** `$invalid_parameter_examples`

**Replace with:**

```
There are no other parameters — no hub_radius, fillet_radius, tip_clearance, or any "supplemental" parameter. If an agent names one it is a hallucination: send it back to the Planner for a plan using only these 16.
```

#### ORC-32 · MERGE · −273 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ## Output format · *Golden rules:* 5, 12

**Why:** Net-neutral on size but load-bearing: this is where the 'prose without a routing tool call halts the pipeline' rule lands once ORC-08 drops $hard_constraints_generic.

**Risk:** Apply this cut in the SAME commit as ORC-08, or the known no-routing-tool-call failure loses its only statement.

**Cut from** `## Output format
Every response should end with your next tool call.  You may write a`

**...through** `cycle is complete (after ``call_receptionist``), produce no further
tool call — your response text is the answer.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Output format
Every turn must end with exactly one routing tool call. Prose emitted without one is silently discarded and the pipeline halts, however complete your reasoning looks. Keep any reasoning line above the call to one or two lines. After ``call_receptionist`` the cycle is over — emit no further tool call.
```

#### ORC-33 · COMPRESS · −168 chars · risk low

*File:* `agents/orchestrator/prompt.md` · *Section:* ## The $parameter_count Design Parameters — the ONLY parameters that exist · *Golden rules:* 4, 5

**Why:** The heading already says 'the only ones that exist'; 'exact spelling' is default behaviour for a name list.

**Cut from** `## The $parameter_count Design Parameters — the ONLY parameters that exist`

**...through** `Every design decision MUST be expressed as one or more of these names
(exact spelling).`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## The $parameter_count design parameters — the only ones that exist
```

</details>

<details><summary><b>Proposed shape of the shrunk prompt</b></summary>

```
# Orchestrator — proposed skeleton (~13,100 chars ≈ 3,000 tok at the measured 4.28 chars/tok)

(intro: 2 lines, who you are)                              ~30 tok
## The pipeline                                            ~95 tok   [ORC-12]
(you do not drive it step by step; read what the last turn produced)  ~85 tok  [ORC-24]
## New user content → the UII first                        ~80 tok   [ORC-20]
  (the two MUST-carry lines: Input directory / Extraction output file)  ~100 tok  [ORC-25]
  (what is not new: reactions, out-of-scope, repeats)      ~55 tok   [ORC-26]
## Extraction-only requests                                ~55 tok   [ORC-18]
## When calling an agent                                   ~167 tok  [ORC-04]
### ``Current attempt:`` labels                            ~147 tok  [ORC-09]
## Relay user directives at full strength (HARD)           ~70 tok   [ORC-17]
## Tell agents what they cannot infer                      ~146 tok  [ORC-03]
## Precision refine loop                                   ~112 tok  [ORC-10]
## Completing a cycle — the Planner approves last (HARD)   ~147 tok  [ORC-01]
### Name the attempt folder(s) (HARD)                      ~159 tok  [ORC-02]
### Do NOT seed follow-ups the system cannot deliver       ~124 tok  [ORC-07]
### Verify a self-exonerating diagnosis before relaying it ~93 tok   [ORC-21]
### Read the ``[Incoming from: <sender>]`` header first    ~99 tok   [ORC-13]
### Questions about what the system observed               ~51 tok   [ORC-27]
## Who does what — never ask an agent for more             ~208 tok  [ORC-06, absorbs ORC-05]
## The 16 design parameters — the only ones that exist     ~261 tok  [ORC-33 + ORC-11 + ORC-31]
## Geometry rule (HARD)                                    ~59 tok   [ORC-22]
## Escalation                                              ~89 tok   [ORC-19]
(you originate no design content)                          ~54 tok   [ORC-29]
## Never invent                                            ~60 tok   [ORC-28]
## Hard rules                                              ~65 tok   [ORC-08]
  (+ attempt folders append-only, calculate)               ~57 tok   [ORC-16]
## Your tools ($routing_hub)                               ~181 tok  [ORC-14]
## Inter-agent chain log ({chain_access_block})            ~51 tok   [ORC-30]
## Output format                                           ~74 tok   [ORC-32]

DELETED OUTRIGHT: ## Agent tools at a glance [ORC-05], ## Hard constraints — DC-specific [ORC-15], <<BSV_ON>> block [ORC-23].
TOTAL ≈ 2,960-3,050 tok (from 10,355; ~71% reduction).
```

</details>

**Auditor notes.** WHERE THE ORCHESTRATOR'S ROUTING TEXT COMES FROM (the question in the brief): NOT from routing.py. agents/shared/routing.py::routing_instructions() is loaded at wiring time only by the six chain agents; the Orchestrator (like the Receptionist) splices a static fragment at import time via $routing_hub → agents/shared/prompt_fragments/routing_orchestrator.md (see prompts.py _build_slots, "routing_hub": _read_generic_fragment(f"routing_{_hub_agent()}.md")). The only other non-prompt.md source is the runtime {chain_access_block}, a Python string literal at agents/orchestrator/orchestrator.py lines 102-118. Cuts ORC-14 and ORC-30 land in those two files; everything else except ORC-11 is in agents/orchestrator/prompt.md.

BLAST RADIUS. Three classes:
(a) Orchestrator-local (safe to apply alone): all prompt.md cuts, plus ORC-14 (routing_orchestrator.md is spliced by this prompt only — the 5-agent Conductor uses routing_conductor_5agents.md) and ORC-30.
(b) SCOPE_PER_AGENT (delete the $slot line from agents/orchestrator/prompt.md; the shared fragment file is untouched and every other agent keeps it): ORC-05 ($agent_tools_overview, also used by the DH), ORC-08 ($hard_constraints_generic, 8 other prompts), ORC-15 ($hard_constraints_dc, 7 others), ORC-16 ($hard_constraints_tools, 7 others), ORC-22 ($geometry_modification_rule, DCOI), ORC-23 ($blade_sections_visualizer, 8 others), ORC-31 ($invalid_parameter_examples, 3 others), ORC-12 ($pipeline_flow, Planner + Conductor).
(c) FLEET-WIDE — needs joint review with the other eight audits: ORC-11 rewrites DC_prompt_fragments/dc_config/parameters.md, which is spliced by NINE prompts. Do not land it from this audit alone.

WHAT I DELIBERATELY DID NOT CUT. (1) The 16-parameter list — ORC-11 is a reformat only; every name, type and range stays inline, and it ADDS the *Thickness/*Camber-are-%-of-own-chord fact and the middlePos = 4 + middlePos·(impellerRadius − 4) span formula, both of which caused real bugs and today live only in modelling_notes.md, which the Orchestrator never sees. (2) The two mandatory call_user_input_inspector lines (ORC-25) — the UII's tools hard-fail without them; trimmed by 37% and no further. (3) The 'no routing tool call ⇒ pipeline halts' rule — it currently lives ONLY in the shared generic_constraints fragment I am scoping out, so ORC-32 rewrites ## Output format to carry it. ORC-08 and ORC-32 must land in the same commit. (4) 'Report only artifacts you saw produced this run' (ORC-28 first sentence and ORC-02 last clause) — the fabricated-render-observation failure. (5) The DCIC-opens-the-attempt / no-Current-attempt-for-a-new-generation invariant (ORC-09), which the precision refine loop depends on.

BUG FOUND WHILE READING: DC_prompt_fragments/dc_config/geometry_modification_rule.md says 'the 17 design parameters' twice — stale since the impellerHeight removal made it 16. It is spliced into the DCOI prompt as well as this one, so fix the fragment even though ORC-22 stops the Orchestrator from reading it.

EMPHASIS BUDGET (golden rule 5): the current prompt has five HARD/CRITICAL banners plus 'MUST'/'NEVER'/'ONLY' in most sections. The skeleton keeps exactly three HARD markers — Completing a cycle, Name the attempt folder(s), Relay user directives — plus the geometry rule. Everything else drops to plain imperative.

RULE-10 CANDIDATE NOT CONVERTED (needs an owner decision, worth ~160 more tokens): the 'Attempts this cycle: / Show to user:' block in ORC-02 is a fixed record format. The dispatcher already knows every attempt folder opened this cycle, so it could append that block to the call_receptionist payload in code, leaving the prompt to say only 'the Planner picks which to show'. That would also eliminate the guess-a-path failure mode the current prose spends four bullets defending against.

MEASUREMENT: assembled baseline is ~44,275 chars for the measured 10,355 tokens (4.28 chars/token — markdown tokenises better than chars/4). Total chars_removed 43,743; replacements add back ~12,580; net ~13,100 chars ≈ 3,000 tokens, a ~71% reduction. If you need margin under 3,000, ORC-10 (precision refine loop, 112 tok) is the first thing to drop when the precision-sections feature is not in play.

---

### 4.3 Planner — 12,326 → ~5,470 tok

| ID | action | section | −chars | rules | risk | what |
|---|---|---|---:|---|---|---|
| **PLN-11** | COMPRESS | ## Role 3 — a completed cycle to approve | 2040 | 2,7,11 | medium | Keeps the final-approver mandate, the four outcomes and the 3D-phase trigger; drops the second verbatim sample directive and the 'what you do NOT see' paragraph about things that never reach the Planner. |
| **PLN-31** | COMPRESS | ## Attempt folders and the attempt tools (list_attempts / re | 1946 | 2,6,9 | low | The 'you DIRECT, the DCIC creates' paragraph repeats the FORWARD move and the four use-cases collapse into one sentence. |
| **PLN-04** | COMPRESS | ## Your common moves — Issue a STANDING DIRECTIVE | 1882 | 1,2,7 | medium | Preserves the directive mechanism and every load-bearing clause of the precision job (no first-render approval, any authorised parameter, the chord lever, honest residual) while dropping the sample directive's boilerplate. |
| **PLN-01** | COMPRESS | value_states.md (spliced by Planner, DCIC, DCII, DCOI) | 1466 | 2,5,7 | medium | Keeps all three states, the literal SOFT TARGET marker, the three authorisation sources and the how-far wording; drops the (A)/(B)/(C) scaffolding and the note about older extractions. |
| **PLN-09** | REPLACE_WITH_EXAMPLES | ## Role 1 — a new user message | 1306 | 2,6,11 | low | Collapses a seven-case laundry list into four canonical cases; the dropped cases are covered by the routing fragment and by the merged REPLY DIRECTLY case. |
| **PLN-07** | COMPRESS | ## Your common moves — APPROVE the cycle | 1273 | 2,7,11 | low | Three dense justification paragraphs become one rule plus the three things Part 2 must carry. |
| **PLN-13** | SCOPE_PER_AGENT | ## Normal Pipeline Flow (for reference) | 1121 | 6,8,10 | low | The injected ## Routing section already prints natural_pipeline() in this same prompt and the recovery-sequence semantics are restated in the Recovery PLAN move; the Orchestrator keeps the fragment. |
| **PLN-22** | COMPRESS | ## HARD RULES — rule 9 | 1055 | 2,7 | low | Keeps the all-locked check, the verbatim self-check line, the escalate-instead-of-loop rule and the broken-tool suspicion in a third of the space. |
| **PLN-29** | COMPRESS | ## Utility tool: read_user_queries(n, from_start=False) | 1044 | 9,10,11 | low | The n / from_start semantics and the chronological-order note are already in the tool's docstring, which the model receives as the tool schema. |
| **PLN-05** | COMPRESS | routing_instructions() — Routing is a tool call | 1042 | 5,7,10 | medium | The mandate, the retired-template ban and the free-form-message rule survive; three paragraphs of restatement do not.  Injected into 6 chain agents. |
| **PLN-21** | COMPRESS | ## HARD RULES — rule 8 | 1005 | 6,7 | medium | The LOCKED / SOFT TARGET / FREE semantics and the how-far wording are already spelled out in $value_states immediately above; only the scope-and-extent obligation on hand-offs is unique here. |
| **PLN-02** | COMPRESS | available_agents.md (spliced by Planner + Database Handler) | 947 | 3,7,11 | low | Same roster, one clause per agent instead of a paragraph. |
| **PLN-03** | COMPRESS | ## Your common moves — FORWARD | 910 | 2,6,7 | low | Keeps both branches, the verbatim path lines and the new-vs-reuse attempt rule; drops the image-readability hint and the why-prose. |
| **PLN-08** | COMPRESS | blade_sections_visualizer_planner.md (Planner only) | 815 | 2,7 | low | A numbered four-step procedure plus three advisory paragraphs become one paragraph that also absorbs the generic capability sentence so PLN-32 can drop the shared fragment here. |
| **PLN-30** | COMPRESS | ## Utility tool: read_agent_history(agent_name, last_n=None) | 711 | 9,10 | low | Keeps the agent-name roster (the schema does not enumerate it) and the answer-instead-of-run rule; drops the argument gloss and typical-uses list. |
| **PLN-10** | COMPRESS | ## Role 2 — a problem to recover from | 645 | 2,7 | low | The Problem/Solution/Sequence template is already given verbatim in the Recovery PLAN move, so the fully worked example here is redundant. |
| **PLN-10** | COMPRESS | parameters.md — the 16-parameter list (spliced by 7 agents) | 644 | 3,11 | medium | Owner-mandated inline list kept complete — every name, unit and range — in a denser layout that additionally makes explicit that *Thickness/*Camber are percentages of the section's OWN chord. |
| **PLN-03** | COMPRESS | generic_constraints.md — DOs (spliced by all 8 chain/hub age | 559 | 5,7 | medium | Keeps every DO, including the STANDING DIRECTIVES carry rule with its literal block markers, merging the shortest into their neighbours. |
| **PLN-03** | DELETE | routing_instructions() — Do not loop | 536 | 6,10 | low | generic_constraints.md already carries the same rule into every one of these prompts ('DON'T loop: … STOP and ESCALATE'). |
| **PLN-23** | COMPRESS | ## HARD RULES — rule 10 | 531 | 2,7 | low | Preserves both framings and every concrete obligation with the sub-bullet scaffolding flattened. |
| **PLN-19** | DELETE | ## HARD RULES — rule 6 | 520 | 3,6 | low | $hard_constraints_dc already carries the same prohibition with the same hub_radius / fillet_radius / tip_clearance examples, making the dedicated fragment a third copy inside one prompt. |
| **PLN-27** | COMPRESS | ## Reference — the user input files (text + images) | 515 | 3,9,11 | low | Same file map and tool list as a compact paragraph instead of a bulleted catalogue with per-tool gloss. |
| **PLN-05** | DELETE | ## Your common moves — CLARIFY back to the UII | 479 | 6,10 | low | Duplicate of the CLARIFY entry the routing fragment already injects into this same prompt. |
| **PLN-04** | COMPRESS | routing_instructions() — Permission / authorisation issues | 475 | 7,10 | low | Keeps the read-the-hand-off-first rule and the authorisation-sources call, drops the wasted-round-trip explanation; injected into 6 chain agents. |
| **PLN-12** | COMPRESS | hard_constraints_tools.md (spliced by all 8 chain/hub agents | 412 | 7 | medium | Same three rules with the justification clauses trimmed. |
| **PLN-02** | COMPRESS | ## Output mechanics — every turn ends with a routing call | 401 | 5,7,11 | low | Same two-part contract in half the words; drops the aside that Role 1 already states. |
| **PLN-24** | COMPRESS | ## Anti-Hallucination Rules | 384 | 4,6 | low | B (capabilities in the roster), C (no option menus) and E (no fabricated observations) are already stated in generic_constraints and the routing block; A and D survive as one sentence. |
| **PLN-32** | SCOPE_PER_AGENT | ## Blade-sections visualizer (splice) | 363 | 8 | low | The Planner-only fragment (FRG-08) now opens by stating the capability itself, so the generic capability fragment is a second copy here; the other eight agents keep it. |
| **PLN-07** | COMPRESS | blade_sections_visualizer.md (spliced by all 9 agents) | 358 | 7,11 | low | Same capability statement without the two because-it-skips justifications. |
| **PLN-28** | SCOPE_PER_AGENT | ## Reference — the user input files (text + images) | 335 | 8 | medium | Form-scaffolding guidance belongs to the agents that actually read images; $sketch_handling carries it for the UII, DCII and DCOI, and this prompt tells the Planner not to do image analysis. |
| **PLN-02** | COMPRESS | routing_instructions() — How to decide where to route | 330 | 10,11 | low | Four long conditionals become three one-line rules; injected into 6 chain agents. |
| **PLN-14** | DELETE | ## HARD RULES — rule 1 | 315 | 4,6 | low | generic_constraints.md already forbids inventing tools, scripts, fallback policies, confidence scores, version numbers and non-existent files. |
| **PLN-01** | COMPRESS | ## The three situations you are called in | 312 | 5,7,11 | low | Keeps the three role names and the you-keep-judgement licence, drops three sentences of meta-commentary about how to read the section. |
| **PLN-09** | COMPRESS | routing_planner_uii_first.md (Planner only) | 277 | 9,11 | low | Same three tools and semantics, tightened. |
| **PLN-16** | COMPRESS | ## HARD RULES — rule 3 | 274 | 1,7 | low | Keeps the principle and the one-line incident that makes it concrete. |
| **PLN-12** | COMPRESS | ## DC Input Inspector status (this session) | 269 | 5,7 | low | Keeps the sequencing rule and the refine-round exception, drops the paragraph about the other two checks that are not the Planner's concern. |
| **PLN-17** | DELETE | ## HARD RULES — rule 4 | 261 | 6 | low | Word-for-word the first two bullets of $hard_constraints_dc, which this prompt splices further down. |
| **PLN-11** | COMPRESS | hard_constraints_dc.md (spliced by all 8 chain/hub agents) | 253 | 2,7 | medium | Merges the two overlapping no-mesh-editing bullets and shortens the unsupported-analysis catalogue while keeping every category name. |
| **PLN-18** | DELETE | ## HARD RULES — rule 5 | 206 | 6 | low | $hard_constraints_dc already states the only mesh metrics are watertightness, volume and degenerate-face count. |
| **PLN-06** | COMPRESS | ## Your common moves — Recovery PLAN | 205 | 5,7 | low | Keeps the plan template verbatim, drops the optional Reasoning line and the prose around it. |
| **PLN-05** | COMPRESS | generic_constraints.md — chain-only DON'Ts | 199 | 5,7 | low | Same three chain rules, compressed. |
| **PLN-04** | COMPRESS | generic_constraints.md — DON'Ts | 180 | 5,7 | medium | Same three prohibitions, including the no-fabricated-observations rule, without the explanatory tails. |
| **PLN-06** | COMPRESS | generic_constraints.md — routing-tool-call DON'T | 178 | 5,7 | low | The most load-bearing rule in the fleet: kept in full force, shortened by a third. |
| **PLN-01** | COMPRESS | routing_instructions() — natural-flow header | 145 | 10,11 | low | Same positional facts in fewer words; injected into 6 chain agents. |
| **PLN-08** | COMPRESS | ## Your common moves — REPLY DIRECTLY / ESCALATE | 119 | 5,7 | low | Same two moves without the restatement of how the Orchestrator hands text to the Receptionist. |
| **PLN-26** | MERGE | ## Hard constraints (three headings) | 103 | 11 | low | Each fragment already opens with its own ### heading, so the three wrapper headings are pure duplication. |
| **PLN-20** | COMPRESS | ## HARD RULES — rule 7 | 69 | 5,7 | low | Same inviolable rule, half the words. |
| **PLN-15** | COMPRESS | ## HARD RULES — rule 2 | 15 | 5,7 | low | Same rule, one sentence. |
| **PLN-25** | SCOPE_PER_AGENT | ## End-of-session feedback message (read-only) | -2 | 6,8 | low | Inlines the two shared fragments as one sentence rather than splicing 290 chars of shared prose plus a 230-char Planner gloss; the other six agents keep the fragments. |

<details><summary><b>Full text of each change</b></summary>

#### PLN-11 · COMPRESS · −2040 chars · risk medium

*File:* `agents/planner/prompt.md` · *Section:* ## Role 3 — a completed cycle to approve · *Golden rules:* 2, 7, 11

**Why:** Keeps the final-approver mandate, the four outcomes and the 3D-phase trigger; drops the second verbatim sample directive and the 'what you do NOT see' paragraph about things that never reach the Planner.

**Risk:** Drops the verbatim 'PRECISION JOB — full 3D' sample block. The replacement names every requirement it encoded (unlocked levers only, honest ceiling report, finalize on match or plateau), but wording is now authored per run.

**Cut from** `The Orchestrator routes back to you at the END of every design`

**...through** `Orchestrator hands those straight to the
Receptionist — no separate approval round).`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
You are called at the END of every design cycle — after the DCOI's verdict,
before the Receptionist — and you are the FINAL approver: the user hears
nothing without your stamp, on EVERY completed cycle, even when the DCOI
cleanly approves.  Read what you need (``read_agent_history
('dc_output_inspector')``, ``list_attempts()``, ``read_attempt(n, …)``, your
own earlier plan), then: **APPROVE** (see that move); **REVISE** — the DCOI
missed a defect, is overconfident, or the cycle is not done: Recovery PLAN
(Role 2); **REPLY DIRECTLY** — no mesh was ever needed, surface no attempt;
or **CONTINUE to a 3D precision check** — a SECTIONS precision job has
converged (or capped) AND the user also gave a whole-propeller / top / side
sketch, so do NOT approve yet: issue a FRESH 3D directive REPLACING the
sections one (same shape, new target — match the whole geometry to that
sketch view, moving only UNLOCKED levers, reporting honestly if the gap
traces to locked values or the configurator's limits) and plan a Role-2
sequence that regenerates the full 3D from the converged attempt and sends it
to the DCOI.  Approve only once that finalizes; no 3D-view sketch means
nothing extra to check.
```

#### PLN-31 · COMPRESS · −1946 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## Attempt folders and the attempt tools (list_attempts / read_attempt) · *Golden rules:* 2, 6, 9

**Why:** The 'you DIRECT, the DCIC creates' paragraph repeats the FORWARD move and the four use-cases collapse into one sentence.

**Cut from** `Each design generation lives in an attempt folder under
``logs/attempts/`` — the`

**...through** `made a wrong
    baseline choice and need the on-disk parameters before approving.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Each generation lives in a folder under ``logs/attempts/`` with its
``parameters.json``, mesh, renders and ``description.txt``.  The DCIC creates
it; you have no tool to and must not try.  ``list_attempts()`` gives a
numbered summary and ``read_attempt(n, file)`` reads one file (you cannot
view images — only the DCOI can).  Most cycles need NEITHER, since the UII
folds user-referenced baselines into the extraction and the DCIC picks the
parameters; reach for them when the on-disk truth IS the question — a DCOI
defect repeating (which levers actually moved), a tool failure pointing at an
attempt, or a baseline you doubt.
```

#### PLN-04 · COMPRESS · −1882 chars · risk medium

*File:* `agents/planner/prompt.md` · *Section:* ## Your common moves — Issue a STANDING DIRECTIVE · *Golden rules:* 1, 2, 7

**Why:** Preserves the directive mechanism and every load-bearing clause of the precision job (no first-render approval, any authorised parameter, the chord lever, honest residual) while dropping the sample directive's boilerplate.

**Risk:** The verbatim sample directive is gone; the replacement states the same required content as an instruction to author one, so the DCOI refine loop is still triggered but wording now varies per run. Test one precision run.

**Cut from** `  * **Issue a STANDING DIRECTIVE** — when an instruction must reach a`

**...through** `into the forced refine loop; without it the loop
    does not happen.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
  * **Issue a STANDING DIRECTIVE** — an instruction that must reach a LATER
    agent unchanged, placed in your ``message`` between
    ``=== STANDING DIRECTIVES (copy verbatim to the next agent) ===`` and
    ``=== END STANDING DIRECTIVES ===``.  Only YOU may set one; downstream
    agents copy it verbatim.  Replace it with a new block (never two); end it
    by omitting it.  Canonical case: a PRECISION job (a ``PRECISION DEMAND``
    line, a ``SUGGESTED SECTION SHAPES`` block, or "match as precisely as
    possible" — a rough doodle is NOT one).  Issuing it is what turns the
    DCOI's one-shot check into a refine loop, so write one saying: the DCOI
    compares each render side-by-side with the sketch, describes the shape gap
    in prose and must NOT approve the first render or on proportions alone;
    the DCIC may move ANY parameter the user authorised — chords included,
    since *Thickness and *Camber are percentages of a section's own chord —
    holding fixed ONLY what the user fixed; iterate until it matches or
    provably plateaus, then report the residual honestly.
```

#### PLN-01 · COMPRESS · −1466 chars · risk medium

*File:* `agents/shared/prompt_fragments/value_states.md` · *Section:* value_states.md (spliced by Planner, DCIC, DCII, DCOI) · *Golden rules:* 2, 5, 7 · *auditor's own id:* FRG-01

**Why:** Keeps all three states, the literal SOFT TARGET marker, the three authorisation sources and the how-far wording; drops the (A)/(B)/(C) scaffolding and the note about older extractions.

**Risk:** Shared by 4 agents (planner, dc_input_creator, dc_input_inspector, dc_output_inspector), so this saving multiplies by 4. The SOFT TARGET literal and the one-source-is-enough rule are preserved.

**Cut from** `Every value the user could have given is in exactly one of`

**...through** `nothing said) = as far as the goal requires,
bounded by range.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Every value the user could have given is in exactly one of three states, read
off the extraction's QUANTITATIVE INPUTS section:

- **LOCKED** — stated plainly there, no marker.  Changes only when an
  authorisation frees it.
- **SOFT TARGET** — marked ``SOFT TARGET (goal: …; keep near … if free)``.
  The goal governs: the marker IS the authorisation to move the value within
  range as far as the goal requires, and you never justify moving it.  The
  stated value settles the parameter only where the goal does not bear on it,
  as closely as the "keep near … if free" wording asks.
- **FREE** — absent from QUANTITATIVE INPUTS (never given, or since
  released), or a qualitative description someone must turn into a number:
  the system's choice within range, honouring that description.

**Freeing a LOCKED value.**  ANY ONE of these is enough, and none needs a
ritual re-confirmation: the incoming hand-off names a user permission or
directs the change; the extraction's DESIGN INTENT records an authorisation
(standing until revoked); or the value's line carries ``(unlocked by user)``.
A line saying "user-locked" is only the DEFAULT lock and does not override a
current authorisation.  **How far** it may then move follows the wording:
"as needed / only if necessary" = the smallest change that restores
viability; "freely / as much as possible" (or nothing said) = as far as the
goal requires, within range.
```

#### PLN-09 · REPLACE_WITH_EXAMPLES · −1306 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## Role 1 — a new user message · *Golden rules:* 2, 6, 11

**Why:** Collapses a seven-case laundry list into four canonical cases; the dropped cases are covered by the routing fragment and by the merged REPLY DIRECTLY case.

**Cut from** `The Orchestrator hands you a freshly validated user message, usually
with Receptionist`

**...through** `only the UII can resolve → CLARIFY back to the UII.
<</PF_OFF>>`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
You get a validated user message with Receptionist context (goals,
constraints, strategy caps, disambiguations).<<PF_OFF>>  The UII has ALREADY written
``extracted_inputs.txt``: read it first via ``read_extracted_inputs(<path
from the hand-off>)`` and form your strategy from it, consulting raw inputs
only if it misses something.<</PF_OFF>>  Not every message is a design request:

  * A design ask → FORWARD, with a brief Part-1 note and no plan.
  * Answerable from prior histories, or a proposal / trade-off discussion →
    ``read_agent_history`` if needed, then REPLY DIRECTLY; do NOT start the
    pipeline.  Needs BOTH a lookup and fresh geometry → say so and FORWARD.
  * Extraction-only (report my inputs, don't design) → the extraction IS the
    deliverable: REPLY DIRECTLY, and its breadth beyond the $parameter_count
    parameters is wanted here.  No DCIC, no mesh.
  * Beyond the system's capabilities or too ambiguous → ESCALATE saying what
    is needed.  Never invent capabilities.
```

#### PLN-07 · COMPRESS · −1273 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## Your common moves — APPROVE the cycle · *Golden rules:* 2, 7, 11

**Why:** Three dense justification paragraphs become one rule plus the three things Part 2 must carry.

**Cut from** `  * **APPROVE the cycle** — Part 2 to the Orchestrator naming which`

**...through** `limit, and the user needs to know which ones were left alone.`

**Replace with:**

```
  * **APPROVE the cycle** — Part 2 names which attempt(s) to show (number +
    one-line reason), the technical outcome, and your endorsement level in
    plain words ("recommend attempt N as the satisfying solution because …"
    vs "showing attempt N for context — not satisfying yet"), which is what
    the Receptionist reads to decide whether to update the Parameters panel.
    It relays your Part 2 and manufactures nothing, so what you drop never
    reaches the user.  ALSO carry: every USER VALUE NOT HONOURED (compare the
    extraction's QUANTITATIVE INPUTS with the endorsed attempt via
    ``read_attempt`` — parameter, what they asked, what was used, why); for a
    PRECISION job the DCOI's residual for EACH phase in its own words (never
    upgrade "plateaued" to "closely matches"); and any parameter you were
    authorised to vary that never moved, since an untried lever means the
    residual is not a tool limit.
```

#### PLN-13 · SCOPE_PER_AGENT · −1121 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## Normal Pipeline Flow (for reference) · *Golden rules:* 6, 8, 10

**Why:** The injected ## Routing section already prints natural_pipeline() in this same prompt and the recovery-sequence semantics are restated in the Recovery PLAN move; the Orchestrator keeps the fragment.

**Cut from** `## Normal Pipeline Flow (for reference)
$pipeline_flow`

**...through** `## Normal Pipeline Flow (for reference)
$pipeline_flow`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

#### PLN-22 · COMPRESS · −1055 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## HARD RULES — rule 9 · *Golden rules:* 2, 7

**Why:** Keeps the all-locked check, the verbatim self-check line, the escalate-instead-of-loop rule and the broken-tool suspicion in a third of the space.

**Cut from** `9. **Retry budget — count, differentiate, or stop.**  Before ANY
   revision directive,`

**...through** `(``read_agent_history``) to check for a
   missing/malformed argument before assuming an external fix.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
9. **Retry budget — count, differentiate, or stop.**  Before any revision: if
   ALL $parameter_count values are LOCKED (a ``SOFT TARGET`` is a lever, not
   a lock), a qualitative "revise X" must touch a locked value — escalate for
   permission instead.  Otherwise retry only with a concrete, not-yet-tried
   lever and carry in Part 2 the self-check line

       Attempt N of expected ~M; this directive differs from prior cycles in
       <one concrete way>.

   (N from your history, M usually ~3–5.)  No differentiator = ESCALATE "no
   new angle available".  Never re-issue a paraphrase of a previous plan, and
   treat a recurring "the tool is broken" diagnosis as suspect until someone
   re-reads the failing call's arguments.
```

#### PLN-29 · COMPRESS · −1044 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## Utility tool: read_user_queries(n, from_start=False) · *Golden rules:* 9, 10, 11

**Why:** The n / from_start semantics and the chronological-order note are already in the tool's docstring, which the model receives as the tool schema.

**Cut from** `You have access to ``user_query.txt``, a file that logs every user-
facing`

**...through** `the context materially helps extraction; the UII still
reads the files itself.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Returns entries from ``user_query.txt``; you are NOT given its content
automatically.  Most kickoffs do not need it — reach for it when an earlier
escalation or clarification is in play, or to compare the original ask with
later ones (``from_start=True``).  Lines beginning ``[Receptionist
clarification: …]`` are authoritative: they say what the user actually meant.
```

#### PLN-05 · COMPRESS · −1042 chars · risk medium

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — Routing is a tool call · *Golden rules:* 5, 7, 10 · *auditor's own id:* RTG-05

**Why:** The mandate, the retired-template ban and the free-form-message rule survive; three paragraphs of restatement do not.  Injected into 6 chain agents.

**Risk:** This is the block guarding the 'prose with no routing call halts the pipeline' failure. Shortened, not weakened, and FRG-06 states the same mandate with the consequence spelled out.

**Cut from** `        "### Routing is a tool call — MANDATORY",
        "Every response that ends`

**...through** `is.  Keep that reasoning terse "
        "(one or two lines is plenty).",`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
        "### Routing is a tool call — MANDATORY",
        "Every response that ends your turn MUST invoke exactly one of the "
        "routing tools above, in the SAME response where you finish your "
        "work — never announce a call instead of making it, and never emit "
        "a ``---ROUTING---`` template (retired).  The call IS the decision "
        "and its ``message`` argument IS the whole hand-off: free-form "
        "prose, no option menus, carrying exactly what the recipient needs "
        "and nothing more.  Other response text is your own terse "
        "reasoning; the recipient never sees it.",
```

#### PLN-21 · COMPRESS · −1005 chars · risk medium

*File:* `agents/planner/prompt.md` · *Section:* ## HARD RULES — rule 8 · *Golden rules:* 6, 7

**Why:** The LOCKED / SOFT TARGET / FREE semantics and the how-far wording are already spelled out in $value_states immediately above; only the scope-and-extent obligation on hand-offs is unique here.

**Risk:** Keeps the scope-is-not-a-subset principle, the general form of the chord-authorisation revocation bug; verify FRG-01 is applied too, since $value_states now carries the state definitions alone.

**Cut from** `8. **What a plan may touch — the value states; authorization =`

**...through** `plain words the DCIC can act on<<DCII_ONLY>> and the DCII can check<</DCII_ONLY>>.`

**Replace with:**

```
8. **Authorisation = scope + how far.**  The states above govern what a plan
   may touch.  A number the user gave in chat that the extraction has not
   recorded yet — including a ``[Receptionist clarification: …]`` line — is a
   user value: treat it as LOCKED.  Any hand-off directing a change to a user
   value names the parameter(s), WHICH ones the authorisation covers (freeing
   one says nothing about the rest) and HOW FAR each may move.  If viability
   is unreachable inside that scope, ESCALATE.
```

#### PLN-02 · COMPRESS · −947 chars · risk low

*File:* `agents/shared/prompt_fragments/available_agents.md` · *Section:* available_agents.md (spliced by Planner + Database Handler) · *Golden rules:* 3, 7, 11 · *auditor's own id:* FRG-02

**Why:** Same roster, one clause per agent instead of a paragraph.

**Cut from** `- **Receptionist**: the user-facing agent.  Validates incoming requests
  before the pipeline ever`

**...through** `Cannot measure precise dimensions; comments
  on overall shape, proportions, and feature count.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
- **Receptionist** — validates incoming requests and composes every message
  to the user.  Never call it directly: route to the Orchestrator saying what
  must be asked.
- **User Input Inspector (UII)** — reads user_query.txt and the input files
  (text, JSON, sketches) into extracted_inputs.txt.  The ONLY agent that
  interprets raw user content.
- **DC Input Creator (DCIC)** — turns qualitative direction into the concrete
  $parameter_count-parameter set in parameters.json and opens the attempt
  folder.  The ONLY agent that authors numbers.
<<DCII_ONLY>>- **DC Input Inspector (DCII)** — independently audits parameters.json
  against extracted_inputs.txt (in range, consistent, matching intent); can
  correct the DCIC.
<</DCII_ONLY>>- **Tool Caller (TC)** — calls the merged generate-and-render tool once (mesh,
  then renders + quality-check numbers) and reports the paths; also has
  ``calculate``.
- **DC Output Inspector (DCOI)** — loads the rendered PNGs and judges shape,
  proportions and feature count (it cannot measure dimensions); approves or
  flags defects.
```

#### PLN-03 · COMPRESS · −910 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## Your common moves — FORWARD · *Golden rules:* 2, 6, 7

**Why:** Keeps both branches, the verbatim path lines and the new-vs-reuse attempt rule; drops the image-readability hint and the why-prose.

**Cut from** `  * **FORWARD** — hand the pipeline its next step<<PF_ON>>: route to the`

**...through** `the DCII / DCOI on whether to
    re-load, not a binding classification.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
  * **FORWARD**<<PF_ON>> to the User Input Inspector
    (``call_user_input_inspector``), carrying verbatim ``Input directory:
    {user_inputs_dir}`` and ``Extraction output file:
    {extraction_output_file}``<</PF_ON>><<PF_OFF>> to the DC Input Creator
    (``call_dc_input_creator``): a qualitative strategy directive ("increase
    <param X>", "honour the locked <param Y>"), any authorisation it needs, a
    filename-safe slug + why (it writes ``description.txt``), and the
    ``Extracted inputs file:`` path — it reads the extraction itself<</PF_OFF>>.
    Pass ``Current attempt: <path>`` ONLY to REUSE an attempt; a new
    generation has no folder yet (the DCIC opens it).
```

#### PLN-08 · COMPRESS · −815 chars · risk low

*File:* `DC_prompt_fragments/tools_config/blade_sections_visualizer_planner.md` · *Section:* blade_sections_visualizer_planner.md (Planner only) · *Golden rules:* 2, 7 · *auditor's own id:* FRG-08

**Why:** A numbered four-step procedure plus three advisory paragraphs become one paragraph that also absorbs the generic capability sentence so PLN-32 can drop the shared fragment here.

**Cut from** `When a request centres on the blade sections — the user provides`

**...through** `new attempt only when the parameter set or design
direction genuinely changes.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
The Tool Caller can render JUST the three blade sections from an attempt's
parameters file (`render_blade_sections`) — no 3D mesh, so it is much faster
and can be the deliverable itself.  When a request centres on the sections
(section drawings, specific section details), prefer a **sections-first**
plan: render only the sections, have the DC Output Inspector check them
against the user's drawing, refine on that fast loop, and only then decide
whether the full 3D is needed.  It is a suggestion, not a rule.  Always say
which render type the Tool Caller should produce.  Re-rendering an attempt
that is already fine is in-place work — the DCOI sends it straight back to
the Tool Caller and NO new attempt is opened; open one only when the
parameter set or design direction changes.
```

#### PLN-30 · COMPRESS · −711 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## Utility tool: read_agent_history(agent_name, last_n=None) · *Golden rules:* 9, 10

**Why:** Keeps the agent-name roster (the schema does not enumerate it) and the answer-instead-of-run rule; drops the argument gloss and typical-uses list.

**Cut from** `You can inspect another agent's live message history to answer
questions about`

**...through** `UII when
the request genuinely requires running (or re-running) the design
workflow.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Inspect another agent's live history instead of re-running work —
``planner``, ``user_input_inspector``, ``dc_input_creator``,
<<DCII_ONLY>>``dc_input_inspector``, <</DCII_ONLY>>``dc_output_inspector``, ``tool_caller``,
``orchestrator``, ``receptionist`` (human-readable names work too).  A
request fully answerable from histories is answered via the Orchestrator, not
by a pipeline run.
```

#### PLN-10 · COMPRESS · −645 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## Role 2 — a problem to recover from · *Golden rules:* 2, 7

**Why:** The Problem/Solution/Sequence template is already given verbatim in the Recovery PLAN move, so the fully worked example here is redundant.

**Cut from** `The Orchestrator calls you because something failed or the pipeline
needs a`

**...through** `value).  Then <<DCII_ONLY>>DC Input
  Inspector → <</DCII_ONLY>>Tool Caller → DC Output Inspector."`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Something failed, or the pipeline needs a non-standard sequence: produce a
Recovery PLAN (see that move).  Rules 8–10 govern what it may touch, when to
retry and when to stop and ask.  Part 2 stays short, e.g. "Call DC Input
Creator: increase <param X> (qualitative, no value).  Then <<DCII_ONLY>>DC Input
Inspector → <</DCII_ONLY>>Tool Caller → DC Output Inspector."
```

#### PLN-10 · COMPRESS · −644 chars · risk medium

*File:* `DC_prompt_fragments/dc_config/parameters.md` · *Section:* parameters.md — the 16-parameter list (spliced by 7 agents) · *Golden rules:* 3, 11 · *auditor's own id:* FRG-10

**Why:** Owner-mandated inline list kept complete — every name, unit and range — in a denser layout that additionally makes explicit that *Thickness/*Camber are percentages of the section's OWN chord.

**Risk:** NOT a removal: all 16 names, units and ranges survive, including the full middlePos fraction-of-blade-SPAN formula from the 4 mm root. Spliced by 7 agents. Re-read once after applying — this is what the whole fleet reasons from.

**Cut from** `### Global / ring
 1. bladeCount         (integer)              — Number of blades [3;`

**...through** `length [10; 30]
16. outerAngle     (degrees)                   — Angle of attack [2; 25]`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
**Ring** — bladeCount (integer) [3; 6] · impellerRadius (mm, outer radius)
[60; 80] · impellerThickness (mm, ring wall) [1; 5].  The ring HEIGHT is NOT
a parameter — it is derived to fit the outer blade section.

**Inner section** — innerThickness (% of THIS section's own chord) [3; 24] ·
innerMaxPos (integer, tenths of chord — chordwise position of max thickness)
[2; 8] · innerCamber (% of chord) [0; 9] · innerChord (mm) [3; 11] ·
innerAngle (degrees, angle of attack) [2; 25].

**Middle section** — middlePos (fraction of blade SPAN, unitless: 0 = root at
the 4 mm hub, 1 = tip; radius = 4 + middlePos·(impellerRadius − 4) mm)
[0.3; 0.7] · middleChord (mm) [10; 30] · middleAngle (degrees) [2; 25].

**Outer section** — outerThickness (% of chord) [3; 24] · outerMaxPos
(integer, tenths of chord) [2; 8] · outerCamber (% of chord) [0; 9] ·
outerChord (mm) [10; 30] · outerAngle (degrees) [2; 25].
```

#### PLN-03 · COMPRESS · −559 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* generic_constraints.md — DOs (spliced by all 8 chain/hub agents) · *Golden rules:* 5, 7 · *auditor's own id:* FRG-03

**Why:** Keeps every DO, including the STANDING DIRECTIVES carry rule with its literal block markers, merging the shortest into their neighbours.

**Risk:** Fleet-wide: spliced into all 8 non-DH prompts, so the saving multiplies by 8. The STANDING DIRECTIVES markers are reproduced byte-identically.

**Cut from** `- DO act on the inputs in your hand-off and the data`

**...through** `answer in English; do not substitute words from other languages or
  scripts.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
- DO act on your hand-off and the files it references, using only the tools
  listed for your role — that list is exhaustive.  Answer in English.
<<CHAIN_ONLY>>- DO follow the natural pipeline: FORWARD to your natural next when your work
  succeeds and the Orchestrator did not ask you to report back, otherwise
  return to it, and ESCALATE the moment something blocks you that no other
  chain agent can fix.
- DO carry STANDING DIRECTIVES verbatim: reproduce any
  ``=== STANDING DIRECTIVES (copy verbatim to the next agent) ===`` …
  ``=== END STANDING DIRECTIVES ===`` block UNCHANGED in your own hand-off,
  writing your own prose around it.  Only the Planner may set or change one.
<</CHAIN_ONLY>>- DO write hand-offs as free-form prose carrying exactly what the recipient
  needs — the paths their tools require, what changed and why, the authorship
  of any non-user-authored value — and nothing more.
```

#### PLN-03 · DELETE · −536 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — Do not loop · *Golden rules:* 6, 10 · *auditor's own id:* RTG-03

**Why:** generic_constraints.md already carries the same rule into every one of these prompts ('DON'T loop: … STOP and ESCALATE').

**Cut from** `        "### Do not loop — ESCALATE when stuck",
        "If you find yourself`

**...through** `"
        "consult another agent, or ask the user.  Never silently loop.",
        "",`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

#### PLN-23 · COMPRESS · −531 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## HARD RULES — rule 10 · *Golden rules:* 2, 7

**Why:** Preserves both framings and every concrete obligation with the sub-bullet scaffolding flattened.

**Cut from** `10. **Escalating to the user — describe the ACTUAL problem, not a`

**...through** `defaults as if user-locked, and never mix
    the permission and guidance framings.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
10. **Escalating — describe the ACTUAL problem.**  The Receptionist relays
    your Part 2 as-is, so give it short operational prose (not a
    Problem/Solution/Sequence dump): what was tried, the defect the DCOI
    keeps reporting, and why asking NOW is right.  Two framings, never
    mixed: **permission** — the remaining levers all touch user-LOCKED
    parameters, so name them canonically WITH their current values (you have
    the extraction; the Receptionist does not), one line of rationale each,
    and how far each may move, never a vague "may any numbers change?"; or
    **guidance** — unlocked levers remain but materially different directions
    are exhausted, so ask for qualitative guidance and say plainly that
    another automated guess is unlikely to converge.  Never list
    system-chosen defaults as if user-locked.
```

#### PLN-19 · DELETE · −520 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## HARD RULES — rule 6 · *Golden rules:* 3, 6

**Why:** $hard_constraints_dc already carries the same prohibition with the same hub_radius / fillet_radius / tip_clearance examples, making the dedicated fragment a third copy inside one prompt.

**Cut from** `6. **The $parameter_count design parameters are the ONLY parameters.**
   Use their exact`

**...through** `are the ONLY parameters.**
   Use their exact names (see list below).
$invalid_parameter_examples`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

#### PLN-27 · COMPRESS · −515 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## Reference — the user input files (text + images) · *Golden rules:* 3, 9, 11

**Why:** Same file map and tool list as a compact paragraph instead of a bulleted catalogue with per-tool gloss.

**Cut from** `The user's input directory ({user_inputs_dir}) contains:
  * ``user_query.txt`` — every user-facing turn`

**...through** `the UII's job,
and comparing output against a reference is the DCOI's).`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
{user_inputs_dir} holds ``user_query.txt`` (every user-facing turn),
``extracted_inputs.txt``<<PF_OFF>> — your PRIMARY input<</PF_OFF>>, and an optional
``{input_images_subdir}/`` of reference images, each paired with a
``<name>_note.txt``.  On demand: ``list_input_files()``,
``read_input_text(path)``, ``read_image_notes()``, ``view_images(paths)`` —
use ``view_images`` only when a visual judgement changes your plan (image
analysis is the UII's job, comparison against a reference the DCOI's).
```

#### PLN-05 · DELETE · −479 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## Your common moves — CLARIFY back to the UII · *Golden rules:* 6, 10

**Why:** Duplicate of the CLARIFY entry the routing fragment already injects into this same prompt.

**Cut from** `<<PF_OFF>>  * **CLARIFY back to the UII** (``call_user_input_inspector``) — ONLY
    when the`

**...through** `so the extraction you
    read already reflects the newest user turn.
<</PF_OFF>>`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

#### PLN-04 · COMPRESS · −475 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — Permission / authorisation issues · *Golden rules:* 7, 10 · *auditor's own id:* RTG-04

**Why:** Keeps the read-the-hand-off-first rule and the authorisation-sources call, drops the wasted-round-trip explanation; injected into 6 chain agents.

**Cut from** `        f"### Permission / authorisation issues → {hub} (not "
        "the previous agent)",`

**...through** `issues the previous agent can actually fix, "
        "NOT for permission questions.",`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
        f"### Permission / authorisation issues → {hub}",
        "Before escalating, re-read the incoming hand-off (and any file it "
        "points to, e.g. extracted_inputs.txt): if it already names an "
        "authorisation that plausibly covers the action — even in different "
        "wording — act on it, with no ritual re-confirmation.  When one is "
        "truly missing, ESCALATE to the "
        f"{hub}; " + _authorisation_sources(hub) + "  CLARIFY backward is "
        "for data the previous agent can fix, not permission.",
```

#### PLN-12 · COMPRESS · −412 chars · risk medium

*File:* `DC_prompt_fragments/tools_config/hard_constraints_tools.md` · *Section:* hard_constraints_tools.md (spliced by all 8 chain/hub agents) · *Golden rules:* 7 · *auditor's own id:* FRG-12

**Why:** Same three rules with the justification clauses trimmed.

**Risk:** Fleet-wide (8 prompts).

**Cut from** `- DON'T invent or guess a path for a read tool: read`

**...through** `Orchestrator only as a fallback) — never edit the old
  folder's parameters.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
- DON'T invent or guess a path: read tools take only the paths a hand-off
  label gives (``Input directory:`` / ``Extracted inputs file:`` /
  ``Parameters file:`` / ``Render images:`` / ``Current attempt:``) or an
  upstream tool's return value.
- DO route EVERY arithmetic operation through the ``calculate`` tool (LLM
  mental arithmetic is unreliable even for trivial sums), batching this
  turn's expressions into ONE call.
- Attempt folders are append-only: never rewrite or delete a
  ``parameters.json`` or mesh already in one, write only into the ``Current
  attempt:`` folder, and a folder's mesh + renders must come from its own
  ``parameters.json``.  Re-running render/QC on an attempt REUSES its renders
  in place.  To build on an old parameter set, COPY its values into a NEW
  attempt.
```

#### PLN-02 · COMPRESS · −401 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## Output mechanics — every turn ends with a routing call · *Golden rules:* 5, 7, 11

**Why:** Same two-part contract in half the words; drops the aside that Role 1 already states.

**Cut from** `Every turn MUST end with exactly one routing tool call; prose without`

**...through** `note is enough; the full
plan format below is for recovery reasoning.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Every turn MUST end with exactly one routing tool call; prose without one
halts the pipeline (HARD).  **Part 1** = your reasoning as ordinary response
text: it stays in your history, no other agent reads it.  **Part 2** = the
``message`` argument of that call, the ONLY thing the recipient sees — short,
operational, who does what, never a reasoning dump.
```

#### PLN-24 · COMPRESS · −384 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## Anti-Hallucination Rules · *Golden rules:* 4, 6

**Why:** B (capabilities in the roster), C (no option menus) and E (no fabricated observations) are already stated in generic_constraints and the routing block; A and D survive as one sentence.

**Cut from** `## Anti-Hallucination Rules

A. **Match the remedy to the failure class.**  Content`

**...through** `not fabricate observations.**  Reason only from facts in the
   messages you received.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Anti-hallucination

Match the remedy to the failure class (content failures need content fixes;
transport / environment failures do not), pick ONE path per plan, and reason
only from facts in the messages you received.
```

#### PLN-32 · SCOPE_PER_AGENT · −363 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## Blade-sections visualizer (splice) · *Golden rules:* 8

**Why:** The Planner-only fragment (FRG-08) now opens by stating the capability itself, so the generic capability fragment is a second copy here; the other eight agents keep it.

**Cut from** `<<BSV_ON>>
$blade_sections_visualizer

$blade_sections_visualizer_per_agent`

**...through** `<<BSV_ON>>
$blade_sections_visualizer

$blade_sections_visualizer_per_agent`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
<<BSV_ON>>
$blade_sections_visualizer_per_agent
```

#### PLN-07 · COMPRESS · −358 chars · risk low

*File:* `DC_prompt_fragments/tools_config/blade_sections_visualizer.md` · *Section:* blade_sections_visualizer.md (spliced by all 9 agents) · *Golden rules:* 7, 11 · *auditor's own id:* FRG-07

**Why:** Same capability statement without the two because-it-skips justifications.

**Risk:** Spliced into all 9 prompts, so the saving multiplies by 9. Note PLN-32 drops this splice from the Planner specifically.

**Cut from** `### Blade-sections visualizer

The system can render JUST the blade cross-sections —`

**...through** `refined cheaply on their own, and can even be the final
deliverable.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Blade-sections visualizer

The Tool Caller can render JUST the three blade sections (Inner, Middle,
Outer, stacked, each at its true angle of attack) from an attempt's
parameters file (`render_blade_sections`) — a flat image, no 3D mesh, much
faster than the whole propeller, shown to the user, readable by any agent
that can load images, and able to be the deliverable itself.
```

#### PLN-28 · SCOPE_PER_AGENT · −335 chars · risk medium

*File:* `agents/planner/prompt.md` · *Section:* ## Reference — the user input files (text + images) · *Golden rules:* 8

**Why:** Form-scaffolding guidance belongs to the agents that actually read images; $sketch_handling carries it for the UII, DCII and DCOI, and this prompt tells the Planner not to do image analysis.

**Risk:** This paragraph lives only in the Planner and Conductor prompts, but sketch_handling.md ('what matches the blank is scaffolding, only what was added is a choice') covers the same rule for the three agents that load images.

**Cut from** `When a user reference image is a filled-in FORM/TEMPLATE, only the user's`

**...through** `choices.  Read the handwritten/drawn marks and
treat printed values as context only.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

#### PLN-02 · COMPRESS · −330 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — How to decide where to route · *Golden rules:* 10, 11 · *auditor's own id:* RTG-02

**Why:** Four long conditionals become three one-line rules; injected into 6 chain agents.

**Cut from** `        "### How to decide where to route",
        f"- If the {hub}'s instruction`

**...through** `in the chain "
        f"can fix it, route to the {hub} (ESCALATE).",`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
        "### How to decide where to route",
        f"- Continue the pipeline unless the {hub} asked you to report "
        "back (no instruction means continue): FORWARD when your work "
        "succeeded, otherwise return where it asked.",
        "- CLARIFY to the previous agent when its hand-off is ambiguous, "
        "missing data, or wrong in a way that agent can fix.",
        f"- ESCALATE to the {hub} when nothing in the chain can fix it.",
```

#### PLN-14 · DELETE · −315 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## HARD RULES — rule 1 · *Golden rules:* 4, 6

**Why:** generic_constraints.md already forbids inventing tools, scripts, fallback policies, confidence scores, version numbers and non-existent files.

**Cut from** `1. **No invented mechanisms.**  No timers, waits, confidence scores,
   custom JSON schemas,`

**...through** `The
   only data files are: user_query.txt, extracted_inputs.txt,
   parameters.json, and the render images.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

#### PLN-01 · COMPRESS · −312 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## The three situations you are called in · *Golden rules:* 5, 7, 11

**Why:** Keeps the three role names and the you-keep-judgement licence, drops three sentences of meta-commentary about how to read the section.

**Cut from** `The Orchestrator calls you in one of three situations, named **Role 1**`

**...through** `you write
is free prose — no fixed template, no mandated phrasing.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
The Orchestrator calls you as **Role 1** (a new user message), **Role 2** (a
problem to recover from) or **Role 3** (a completed cycle to approve); other
agents use those names.  The moves below are guidelines, not a closed menu.
```

#### PLN-09 · COMPRESS · −277 chars · risk low

*File:* `agents/shared/prompt_fragments/routing_planner_uii_first.md` · *Section:* routing_planner_uii_first.md (Planner only) · *Golden rules:* 9, 11 · *auditor's own id:* FRG-09

**Why:** Same three tools and semantics, tightened.

**Cut from** `### Available routing tools
- ``call_dc_input_creator(message)`` — FORWARD to the DC Input`

**...through** `for normal completion when no
  pipeline run is required, and for ESCALATE.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Available routing tools
- ``call_dc_input_creator(message)`` — FORWARD, whenever planning yields an
  actionable plan.
- ``call_user_input_inspector(message)`` — CLARIFY, only when
  ``extracted_inputs.txt`` is missing required information or carries an
  inconsistency only the UII can resolve.
- ``call_orchestrator(message)`` — return control: the user-facing summary,
  completion with no pipeline run, and ESCALATE.
```

#### PLN-16 · COMPRESS · −274 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## HARD RULES — rule 3 · *Golden rules:* 1, 7

**Why:** Keeps the principle and the one-line incident that makes it concrete.

**Cut from** `3. **Direct — do not do the work yourself.**  You neither analyse`

**...through** `independently re-verify — do not
   "correct" it to a number you supply.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
3. **Direct; don't do the work.**  Give the downstream agent the PROTOCOL —
   what to check, what to consult, what to report — never the answer.
   Interpreting values and images is the UII's job (a Planner once counted
   "6 blades" from a sketch and told the UII to write it; the UII
   rubber-stamped it).  Suspect a value? NAME the suspicion and ask for an
   independent re-check; never "correct" it to a number you supply.
```

#### PLN-12 · COMPRESS · −269 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## DC Input Inspector status (this session) · *Golden rules:* 5, 7

**Why:** Keeps the sequencing rule and the refine-round exception, drops the paragraph about the other two checks that are not the Planner's concern.

**Cut from** `The DC Input Inspector is ENABLED this session.  Any Sequence YOU author`

**...through** `the loop tight; that is by design, not yours to
plan around.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
The DC Input Inspector is ENABLED: any Sequence you author that creates or
modifies parameters routes DCIC → DCII → TC, never skipping it — it is the
only INDEPENDENT audit of what the DCIC authored.  (On precision refine
rounds the DCIC skips it by design.)
```

#### PLN-17 · DELETE · −261 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## HARD RULES — rule 4 · *Golden rules:* 6

**Why:** Word-for-word the first two bullets of $hard_constraints_dc, which this prompt splices further down.

**Cut from** `4. **Geometry is changed ONLY via the $parameter_count design
   parameters.**  There is`

**...through** `hole filling, normal repair, component
   pruning, struts/supports, or any other mesh post-processing.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

#### PLN-11 · COMPRESS · −253 chars · risk medium

*File:* `DC_prompt_fragments/dc_config/hard_constraints_dc.md` · *Section:* hard_constraints_dc.md (spliced by all 8 chain/hub agents) · *Golden rules:* 2, 7 · *auditor's own id:* FRG-11

**Why:** Merges the two overlapping no-mesh-editing bullets and shortens the unsupported-analysis catalogue while keeping every category name.

**Risk:** Fleet-wide (8 prompts).

**Cut from** `- DON'T express a design in anything but the $parameter_count named
  configurator`

**...through** `are disabled at startup, rely on visual
  inspection and say so plainly.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
- DON'T express a design in anything but the $parameter_count named
  parameters, and DON'T invent others (hub_radius, fillet_radius,
  tip_clearance or any "supplemental" parameter do NOT exist — reject them).
  Geometry changes ONLY by changing those parameters and regenerating via the
  DC Input Creator → Tool Caller path: there is NO mesh editing or
  post-processing of any kind (booleans, welding, remeshing, hole filling,
  normal repair, fillets, chamfers, struts, supports …).
- DON'T offer analysis the system cannot perform (performance, RPM, thrust,
  flow, efficiency, CFD, FEA, stress, material, tolerance) or outputs it does
  not produce (STL / STEP / IGES, other camera angles, higher-resolution
  renders): the parameter set, tessellation and the three fixed views are not
  negotiable.
- The ONLY mesh metrics are watertightness, volume and degenerate-face count;
  when they are disabled, rely on visual inspection and say so.
```

#### PLN-18 · DELETE · −206 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## HARD RULES — rule 5 · *Golden rules:* 6

**Why:** $hard_constraints_dc already states the only mesh metrics are watertightness, volume and degenerate-face count.

**Cut from** `5. **Plan only around metrics that actually exist.**  The DC Output
   Inspector's`

**...through** `Caller's
   bound inspection tool returns (see the agent roster) — nothing else.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

#### PLN-06 · COMPRESS · −205 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## Your common moves — Recovery PLAN · *Golden rules:* 5, 7

**Why:** Keeps the plan template verbatim, drops the optional Reasoning line and the prose around it.

**Cut from** `  * **Recovery PLAN** — write Part 1 in this format, then a`

**...through** `(state
    what information is needed back — the Receptionist composes the
    wording).`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
  * **Recovery PLAN** — Part 1 in this format, then a short Part 2 to the
    Orchestrator (``call_orchestrator``), which executes the sequence agent by
    agent (the forward chain is NOT re-entered):

        Problem: <what went wrong>
        Solution: <what to do — qualitative only, no invented numbers>
        Sequence: <Agent A> → <Agent B> → ...

    Part 2 carries only the next agent(s), one line of intent each, and what
    you need back if the user must be asked.
```

#### PLN-05 · COMPRESS · −199 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* generic_constraints.md — chain-only DON'Ts · *Golden rules:* 5, 7 · *auditor's own id:* FRG-05

**Why:** Same three chain rules, compressed.

**Cut from** `<<CHAIN_ONLY>>- DON'T bounce permission questions back to the previous agent.
  Authorisations come`

**...through** `compose the user's wording —
  never write the user-facing message yourself.
<</CHAIN_ONLY>>`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
<<CHAIN_ONLY>>- DON'T bounce permission questions backward — authorisations come from the
  user (via Receptionist → Orchestrator), the Planner, or the Orchestrator.
- DON'T retry a failing step blindly; when the same failure class recurs,
  ESCALATE so the Planner can pick a different angle.
- DON'T script the final user-facing reply — the Receptionist composes it.
<</CHAIN_ONLY>>
```

#### PLN-04 · COMPRESS · −180 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* generic_constraints.md — DON'Ts · *Golden rules:* 5, 7 · *auditor's own id:* FRG-04

**Why:** Same three prohibitions, including the no-fabricated-observations rule, without the explanatory tails.

**Risk:** Fleet-wide (8 prompts). The fabrication rule that prevents invented render observations is kept, only shortened.

**Cut from** `- DON'T invent tools, scripts, infrastructure, fallback policies,
  confidence scores, version numbers,`

**...through** `this turn, STOP and ESCALATE — re-reading
  unchanged input yields nothing new.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
- DON'T invent tools, scripts, infrastructure, fallback policies, confidence
  scores, version numbers, or files that do not already exist — if your bound
  tools cannot do it, ESCALATE.
- DON'T state an observation you cannot source to a tool result, an agent's
  history, or something the user literally said.
- DON'T loop: about to repeat a tool call with the same arguments? STOP and
  ESCALATE.
```

#### PLN-06 · COMPRESS · −178 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* generic_constraints.md — routing-tool-call DON'T · *Golden rules:* 5, 7 · *auditor's own id:* FRG-06

**Why:** The most load-bearing rule in the fleet: kept in full force, shortened by a third.

**Cut from** `- DON'T communicate to another agent in plain prose.  The ONLY channel`

**...through** `are the Receptionist's direct user replies and the
  Orchestrator's final user-facing wrap-up.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
- DON'T communicate to another agent in plain prose.  The ONLY channel is a
  routing tool call (``call_<agent>``) and the prose in its ``message``
  argument IS the hand-off.  Text emitted WITHOUT invoking a routing tool is
  silently discarded and the pipeline halts with a "no routing tool call"
  error — invoke the tool in the same response where you finish your work,
  never announce it instead.  (Only the Receptionist's user replies and the
  Orchestrator's wrap-up are exempt.)
```

#### PLN-01 · COMPRESS · −145 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — natural-flow header · *Golden rules:* 10, 11 · *auditor's own id:* RTG-01

**Why:** Same positional facts in fewer words; injected into 6 chain agents.

**Cut from** `        "You are one agent in a decentralised pipeline.  The natural "
        "flow`

**...through** `"
            f"to go 'back', that means handing control to the {hub}."
        )`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
        "You are one agent in a decentralised pipeline.  The flow is:",
        f"  {natural_pipeline()}",
        "",
        f"Your position: **{agent_name}**.",
    ]
    if next_agent:
        lines.append(f"- Natural next: **{next_agent}**.")
    else:
        lines.append(
            f"- You are last; completing normally hands control back to "
            f"the {hub}."
        )
    if prev_agent:
        lines.append(f"- Natural previous: **{prev_agent}**.")
    else:
        lines.append(f"- You are first; going 'back' means the {hub}.")
```

#### PLN-08 · COMPRESS · −119 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## Your common moves — REPLY DIRECTLY / ESCALATE · *Golden rules:* 5, 7

**Why:** Same two moves without the restatement of how the Orchestrator hands text to the Receptionist.

**Cut from** `  * **REPLY DIRECTLY** — when the right output is text, not a`

**...through** `below): Part 2 states
    what to ask and what you need back.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
  * **REPLY DIRECTLY** — the right output is text, not a run (a question
    answered from histories, a proposal, an extraction-only report): the
    answer goes in Part 2 via ``call_orchestrator``.
  * **ESCALATE** — you need permission or guidance only the user can give
    (Rules 8–10): Part 2 states what to ask and what you need back.
```

#### PLN-26 · MERGE · −103 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## Hard constraints (three headings) · *Golden rules:* 11

**Why:** Each fragment already opens with its own ### heading, so the three wrapper headings are pure duplication.

**Cut from** `## Hard constraints — generic (apply to every agent)
$hard_constraints_generic

## Hard`

**...through** `## Hard constraints — DC-specific
$hard_constraints_dc

## Hard constraints — tool-specific
$hard_constraints_tools`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Hard constraints
$hard_constraints_generic

$hard_constraints_dc

$hard_constraints_tools
```

#### PLN-20 · COMPRESS · −69 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## HARD RULES — rule 7 · *Golden rules:* 5, 7

**Why:** Same inviolable rule, half the words.

**Cut from** `7. **Qualitative only — no invented numbers.**  Name the parameter and
   the`

**...through** `values — translating direction into numbers
   is the DC Input Creator's job.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
7. **Qualitative only — no invented numbers.**  Name the parameter and the
   direction ("increase <param X>"); turning direction into numbers is the
   DC Input Creator's job.
```

#### PLN-15 · COMPRESS · −15 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## HARD RULES — rule 2 · *Golden rules:* 5, 7

**Why:** Same rule, one sentence.

**Cut from** `2. **No mid-pipeline pauses.**  This pipeline is synchronous.  If user
   input is`

**...through** `is needed, route to the Orchestrator — the Orchestrator asks
   the user.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
2. **No mid-pipeline pauses.**  The pipeline is synchronous; when user input
   is needed, route to the Orchestrator, which asks the user.
```

#### PLN-25 · SCOPE_PER_AGENT · −-2 chars · risk low

*File:* `agents/planner/prompt.md` · *Section:* ## End-of-session feedback message (read-only) · *Golden rules:* 6, 8

**Why:** Inlines the two shared fragments as one sentence rather than splicing 290 chars of shared prose plus a 230-char Planner gloss; the other six agents keep the fragments.

**Cut from** `$eos_feedback_intro
For you, "your scope" is: your strategy and recovery decisions, your`

**...through** `retry-budget judgement, and your handling of locked vs.
unlocked parameter values.

$eos_feedback_outro`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
At session end the Orchestrator may append ONE ``HumanMessage`` carrying user
feedback on YOUR scope — strategy and recovery decisions, Role-3 approval
picks, retry-budget judgement, locked vs. unlocked handling.  Treat it as
ground truth in your Database Handler answers.
```

</details>

<details><summary><b>Proposed shape of the shrunk prompt</b></summary>

```
Planner - proposed skeleton, with per-section token estimates MEASURED from
the post-cut assembly (UII-first, DC_INSPECTOR_ENABLED=True, BSV on, RAG off)
and scaled to the 12,326-token baseline.  Total ~5,470 tokens.

  (preamble) You are the Planner for a $domain_description.          15
  ## The three situations you are called in                          65
  ## Output mechanics - every turn ends with a routing call          99
  ## Your common moves                                              792
       FORWARD | Issue a STANDING DIRECTIVE (precision job) |
       Recovery PLAN | APPROVE | REPLY DIRECTLY | ESCALATE
  ## Role 1 - a new user message                                    237
  ## Role 2 - a problem to recover from                              91
  ## Role 3 - a completed cycle to approve                          294
  ## Available Agents              ($available_agents)              253
  ## DC Input Inspector status     <<DCII_ONLY>>                     72
  ## The three states of a user value  ($value_states)              354
  ## HARD RULES  (2 no-pauses | 3 direct | 7 qualitative |
     8 authorisation | 9 retry budget | 10 escalating)              676
  ## Anti-hallucination                                              53
  ## The 16 Design Parameters      ($parameter_list)                229
  ## End-of-session feedback message (read-only)                     77
  ## Hard constraints (one heading, three fragments)                972
       $hard_constraints_generic DOs 224 / DON'Ts 312
       $hard_constraints_dc 231 | $hard_constraints_tools 200
  ## Reference - the user input files                               122
  ## Utility tool: read_user_queries                                101
  ## Utility tool: read_agent_history                               101
  ## Attempt folders + Blade-sections visualizer (Planner frag)     359
  ## Routing  ({routing_instructions} + routing_planner fragment)   506

GONE ENTIRELY: ## Normal Pipeline Flow (the Routing section already prints the
flow), HARD RULES 1 / 4 / 5 / 6 and the $invalid_parameter_examples splice (all
restated in $hard_constraints_dc / $hard_constraints_generic), the
CLARIFY-back-to-UII move (restated by the routing fragment), the FORM/TEMPLATE
paragraph (scoped to the image-reading agents), the generic
$blade_sections_visualizer splice, and the $eos_feedback_* splices.
```

</details>

**Auditor notes.** MEASUREMENT.  I re-assembled the prompt the way prompts.py does
(PLANNER_FIRST=False, DC_INSPECTOR_ENABLED=True, BSV on, RAG off) and measured
it at 51,849 chars / ~12,960 tokens - 5% above the quoted 12,326 baseline, the
gap being my estimate of the injected routing block.  Applying all 49 cuts
takes the same assembly to 22,986 chars / ~5,750 tokens, a 56% cut; scaled to
the quoted baseline that is ~5,470.  Every chars_removed is a measured span
length minus its replacement, with each quote pair located in the real file and
verified unique.  The five routing.py numbers count RENDERED prompt text
(string-literal contents only), not Python source.  Three cuts also drop a
$slot splice, so their number includes the fragment text that stops being
assembled (PLN-13 +1,067, PLN-19 +379, PLN-32 +335).

WHY NOT 1,000-3,000 - AND WHAT WOULD GET THERE.  I did not reach the requested
band and will not pretend otherwise.  The post-cut prompt is 22,986 chars, of
which 9,717 are shared fragments the Planner genuinely needs and that I must
not remove: the 16-parameter table (965 chars, owner-mandated inline),
$value_states (1,487), the three hard-constraint blocks (4,070), the agent
roster (1,065) and the injected routing block (2,130).  That is ~2,310 tokens
before the Planner says a word about its own job.  The other 13,269 chars are
that job: six moves, three Roles, six HARD RULES and four tool sections, all
already compressed 60-75% from source.  Squeezing those to ~700 tokens - what a
3,000-token total would demand - means deleting behaviour, not prose.

Three follow-ups would close most of the remaining gap, each a design decision
rather than an edit:
  (a) Planner-scoped copies of generic_constraints and hard_constraints_tools,
      using the per-agent fragment pattern that already exists
      (blade_sections_visualizer_planner.md, database_search_planner.md).  The
      Planner writes no files, so the append-only attempt-folder rules and half
      the DOs are dead weight for it.  Worth ~1,400 chars / ~330 tokens.
  (b) Fold Role 1 / Role 2 / Role 3 into the moves list.  Each Role section
      mostly cross-references a move defined above it; the merge is worth
      ~1,100 chars / ~260 tokens but needs one careful rewrite, not a cut.
  (c) Drop $available_agents and rely on the routing block's flow line plus the
      tool names.  Worth ~1,065 chars / ~250 tokens, but the Planner authors
      recovery Sequences by agent name, so test this one - I would not do it
      blind.
All three together land near 4,600 tokens.  Below that, the honest answer is
that the Planner does more jobs than a 3,000-token prompt can describe:
strategy, recovery planning, final approval, authorisation arbitration and
retry budgeting.  Splitting Role 3 (final approval) into its own agent would
halve the prompt - a topology question, not a prompt-editing one.

MULTIPLIER WARNING.  Nine cuts touch fragments other agents splice, so they
change the whole fleet, not just the Planner: FRG-01 value_states (4 agents),
FRG-02 available_agents (Planner + Database Handler), FRG-03/04/05/06
generic_constraints (8), FRG-07 blade_sections_visualizer (9), FRG-10
parameters.md (7), FRG-11 hard_constraints_dc (8), FRG-12
hard_constraints_tools (8), and RTG-01..05 routing_instructions (6 chain
agents).  Fleet-wide impact is roughly 3-4x the Planner-only figure.  Only
FRG-08 and FRG-09 are Planner-exclusive fragments.

WHAT I DELIBERATELY DID NOT CUT.
1. The 16-parameter list - reformatted (FRG-10), never removed.  Every name,
   unit and range survives, including middlePos as a fraction of blade SPAN
   with the radius = 4 + middlePos*(impellerRadius - 4) formula; without it the
   from-centre misreading fixed in 9ed7c2a returns.  I also made "% of THIS
   section's own chord" explicit, which the old table only implied.
2. The STANDING DIRECTIVES block markers, byte-for-byte, in both prompt.md
   (PLN-04) and generic_constraints.md (FRG-03) - a real mechanism keyed on the
   literal string.
3. The literal SOFT TARGET marker and its "(goal: ...; keep near ... if free)"
   form (FRG-01).
4. "Prose without a routing call halts the pipeline" - kept in three places on
   purpose (PLN-02, FRG-06, RTG-05).  It is the one rule whose violation stops
   the system dead, and the only triplication I left standing.
5. The chord clause inside the precision directive ("the DCIC may move ANY
   parameter the user authorised - chords included, since *Thickness and
   *Camber are percentages of a section's own chord") - the general-principle
   form of the subset-directive bug that silently revoked a chord
   authorisation.  PLN-21 keeps its companion, "freeing one says nothing about
   the rest".
6. "Never state an observation you cannot source" (FRG-04) and "you cannot view
   images; only the DCOI can" (PLN-31) - both guard the invented-render-
   observation failure.
7. Rule 3's "6 blades" incident: a one-line concrete anchor for an otherwise
   abstract principle, so it earns its 90 characters.

RULE NUMBERING.  PLN-14/17/18/19 delete HARD RULES 1, 4, 5 and 6 while the
survivors keep their original numbers (2, 3, 7, 8, 9, 10), precisely so the two
in-prompt cross-references to "Rules 8-10" stay correct.  Do not renumber
unless you also fix Role 2 and the ESCALATE move.

APPLICATION.  All 49 cuts are independent - no span overlaps another - but
apply PLN-32 together with FRG-08, since FRG-08's replacement is what absorbs
the capability sentence PLN-32 stops splicing.  The files are CRLF on disk;
quotes here use LF because prompts.py reads them with universal newlines, which
is also the text the token count refers to.  No replacement introduces a stray
brace or dollar sign, either of which would break the .format() /
string.Template passes.

RESIDUAL RISK.  The two genuinely behaviour-changing cuts are PLN-04 and
PLN-11: each replaces a verbatim sample STANDING DIRECTIVE with an instruction
to author one carrying the same clauses.  Run one precision sections job and
one sections-then-3D job and confirm that (a) the DCOI still refuses to approve
the first render and (b) a residual reaches the user for each phase.
Everything else is compression of text the model already had to deduplicate.

---

### 4.4 User Input Inspector — 12,069 → ~4,600 tok

| ID | action | section | −chars | rules | risk | what |
|---|---|---|---:|---|---|---|
| **UII-01** | COMPRESS | ### 3. Design Intent and Functional Requirements | 1622 | 2,5,7,11 | medium | A 7-bullet checklist plus three justification paragraphs collapses to one paragraph plus the two records that actually change downstream behaviour (PRECISION DEMAND, the SOFT TARGET goal). |
| **UII-02** | MERGE | ### Matching a ROUGH sketch / ### Matching a PRECISE sketch  | 1502 | 2,6,7,8 | medium | Three sections of near-duplicate matching guidance, most of which describes DCIC/DCOI behaviour rather than the UII's, compress into one three-bullet block. |
| **UII-03** | COMPRESS | ### Temporal scope and Parameters Inputs interface blocks —  | 1275 | 2,7,11 | low | Four worked ADD/MODIFY/REVERT examples of the same newer-wins principle collapse into one sentence naming the three operations. |
| **UII-04** | COMPRESS | ## Reading prior attempts when the user references them | 1260 | 2,7,9 | low | The tool schemas already describe list_attempts/read_attempt; what remains is one when-to-use rule plus three canonical examples. |
| **UII-05** | COMPRESS | ### 1. QUANTITATIVE INPUTS — Soft targets | 1236 | 2,5,7 | medium | Two paragraphs explaining how downstream agents will interpret the marker are justification the UII does not need; the marker, the example, the strength-reading rule and the newer-wins-over-a-pin rule are all kept. |
| **UII-06** | COMPRESS | ### Temporal scope … — B. Parameters Inputs interface blocks | 980 | 2,7,11 | medium | The snapshot-vs-delta walk is real mechanism, but it is stated three times over (per-block prose, then the absence rule, then the walk); once is enough. |
| ⚠️ **UII-07** | COMPRESS | routing_instructions() — "### Routing is a tool call — MANDA | 933 | 2,5,6,10 | medium | Three paragraphs saying the same thing (invoke the tool, don't announce it, don't template the message), plus a retired ---ROUTING--- format nobody emits any more. |
| **UII-08** | COMPRESS | ### 1. QUANTITATIVE INPUTS — Format is flexible | 933 | 2,7 | low | A ten-line worked multi-design example plus a 'pick the clearest format' homily reduce to one sentence naming the three shapes. |
| **UII-09** | COMPRESS | ### UII — for a PRECISE blade-section drawing … 1. A rough s | 905 | 2,7 | medium | The example block carries the whole instruction; the surrounding explanation of why a warm start helps is justification. |
| **UII-10** | COMPRESS | ### UII — … 2. A coarse crop region | 889 | 2,7 | low | Two near-identical worked examples (sections crop, top-view crop) plus an explanation of when the precision loop uses each collapse to one example and one clause. |
| **UII-11** | COMPRESS | ### Capture, do not filter | 824 | 2,7 | low | Two paragraphs of reassurance that broad capture is correct reduce to the rule plus its canonical examples. |
| **UII-12** | COMPRESS | ## User input layout (text + images) — image inspection + re | 799 | 2,7,9 | low | The read_user_inputs/view_images division of labour is repeated in the tools section three paragraphs later; keep the load-order rule and the readability signal, drop the restatement. |
| **UII-13** | COMPRESS | ### 1. QUANTITATIVE INPUTS — HARD RULE, countable features | 779 | 2,5,7 | medium | An incident patch written at three times the length of the principle it encodes; sketch_notes.md already carries the blade-count instance of the same rule. |
| **UII-14** | COMPRESS | ## Forwarding and routing — design-generation forward | 755 | 2,7,10 | medium | The verbatim path lines are the only load-bearing part; the rest explains why the recipient is the natural next step, which the Routing section already states. |
| **UII-15** | COMPRESS | ## Your utility tools | 742 | 2,9,11 | low | Bound tool schemas already carry the descriptions; the prompt only needs the call-discipline rules (once, verbatim paths, batch OCR regions, mandatory write). |
| ⚠️ **UII-16** | COMPRESS | whole file | 739 | 3,11 | medium | Same 16 parameters and ranges, tabular instead of padded prose — the list stays inline per the owner's rule, it just stops paying for alignment whitespace and per-section headers. |
| **UII-17** | COMPRESS | routing_instructions() — "### Permission / authorisation iss | 671 | 2,7,10 | medium | Two long paragraphs to say: re-read the hand-off, act on an authorisation that plausibly covers it, escalate a missing one, CLARIFY only for fixable data. |
| **UII-18** | COMPRESS | ## User input layout (text + images) — directory listing | 670 | 2,7 | low | The UII_MAY_READ_PREVIOUS_EXTRACTION mechanics and the Receptionist's pairing guarantee are context the agent never acts on; the two rules that matter are 'never copy forward' and 'the note is user intent'. |
| **UII-19** | REPLACE_WITH_EXAMPLES | intro + ### Common drawing artifacts in propeller sketches | 656 | 1,2,7 | low | Four enumerated artifact cases are four instances of one principle — the configurator renders idealised geometry, so drawn deviations from it are noise. |
| **UII-20** | DELETE | ## End-of-session feedback message (read-only) | 651 | 4,7,8 | low | Read-only notice that a HumanMessage may appear, plus a scope restatement — it steers no action, and the shared outro it splices tells the reader to 'fold it into your DH answers', which the UII never writes. |
| **UII-21** | COMPRESS | ### Domain hard rules (every agent) | 628 | 2,5,8 | low | Three exhaustive prohibition catalogues (mesh ops, analysis types, formats) keep their canonical examples but drop the enumeration padding and the DON'T-prefix drumbeat. |
| **UII-22** | COMPRESS | ### UII responsibility — record the sketch's precision in th | 616 | 2,7 | low | The two canonical strings are the instruction; the surrounding explanation of which downstream agent reads them is justification. |
| **UII-23** | COMPRESS | ### 1. QUANTITATIVE INPUTS — line-label formats | 605 | 2,7,11 | low | Four template lines with placeholder-heavy annotations plus a 'use the parameter list as source of truth' reminder reduce to two concrete examples. |
| ⚠️ **UII-24** | SCOPE_PER_AGENT | Blade-sections visualizer block | 600 | 8,9 | low | The shared 758-char tool description is for agents that can call or read the tool; the UII neither calls it nor reads its output — it only has to flag a sections-centred request, which its per-agent overlay already says. |
| **UII-25** | COMPRESS | ### Tool-use hard rules (every agent) | 580 | 2,7,8 | low | Each of the three rules is stated then re-explained; the append-only bullet in particular restates itself four times. |
| **UII-26** | REPLACE_WITH_EXAMPLES | ### Judging a sketch's precision | 570 | 2,11 | low | Four bulleted evidence categories with sub-examples compress into one sentence naming the same evidence. |
| **UII-27** | DELETE | routing_instructions() — "### Do not loop — ESCALATE when st | 552 | 5,6 | low | Verbatim duplicate of the 'DON'T loop: if you are about to call the same tool with the same arguments…' bullet in generic_constraints.md, which every agent already has. |
| ⛔ **UII-28** | COMPRESS | DOs — CHAIN_ONLY block (pipeline / escalate / standing direc | 526 | 2,5,7 | medium | The forward/escalate rules are restated in every agent's generated Routing block; only the STANDING DIRECTIVES verbatim-carry rule is unique here, and it needs one sentence, not seven lines. |
| **UII-29** | COMPRESS | ### Filled-in templates and forms | 522 | 1,2,7 | medium | An incident patch (the Ø160-vs-Ø140 form case) written at three times the length of its principle: printed content is scaffolding, only the added marks are input. |
| **UII-30** | COMPRESS | ### 2. QUALITATIVE DESCRIPTIONS | 484 | 2,6,7 | low | The released-parameter note duplicates the temporal-scope rule two sections above; the authorisation guidance needs one sentence. |
| **UII-31** | COMPRESS | routing_instructions() — "### How to decide where to route" | 446 | 2,6,10 | medium | Four long conditionals restating FORWARD / report-back / CLARIFY / ESCALATE, which the per-agent routing fragment lists again immediately below. |
| **UII-32** | COMPRESS | ### Temporal scope … — D. NEVER include historical entries | 434 | 2,5,7 | low | Three examples of the same annotation anti-pattern plus a cross-reference reduce to one line and one parenthetical. |
| **UII-33** | COMPRESS | whole file | 403 | 2,11 | low | Same facts as a prose paragraph instead of a nested list; the middlePos formula and the span-not-radius gotcha are kept verbatim because they are a real modelling trap. |
| **UII-34** | COMPRESS | ### 1. QUANTITATIVE INPUTS — STRICT rules (first two bullets | 396 | 2,6,7 | low | The second bullet is a verbatim restatement of the temporal-scope rule; the first needs one sentence, not five lines with a 'scan your draft' reminder. |
| **UII-35** | COMPRESS | ## What to Extract — categorisation rule | 385 | 2,5,7,11 | low | The 'Numeric ≠ matches a parameter' paragraph repeats the QUANTITATIVE bullet it follows; fold it in. |
| ⚠️ ⛔ **UII-36** | COMPRESS | DON'Ts — routing-tool channel paragraph | 383 | 2,5,6 | medium | Says 'routing is a tool call' three times in one bullet, and the generated Routing block says it again; keep the failure mode once, in the strongest wording. |
| **UII-37** | COMPRESS | ## Forwarding and routing — ESCALATE / first-agent note | 362 | 6,10 | low | The 'you are the first agent, there is no back' paragraph is already in routing_user_input_inspector_uii_first.md and in the generated position block — three copies of one fact. |
| **UII-38** | SCOPE_PER_AGENT | ## Qualitative-to-Quantitative Hints | 362 | 3,8 | medium | The UII is explicitly forbidden from inventing parameter values; the qualitative→parameter mapping table is the DC Input Creator's job and is spliced there already. |
| ⚠️ **UII-39** | COMPRESS | ### 1. QUANTITATIVE INPUTS — OUT OF RANGE | 353 | 2,7 | medium | The rule survives; the paragraph explaining why a downstream agent shouldn't have to rediscover the breach is justification. |
| ⛔ **UII-40** | COMPRESS | DON'Ts — CHAIN_ONLY block (permissions / retry / user reply) | 352 | 2,6,10 | low | The permission-routing rule is stated at length again in the generated Routing block; the other two need one line each. |
| **UII-41** | COMPRESS | Number of blades — COUNT IT | 351 | 2,7 | low | Rule plus exception, minus the reassurance about why blade count is reliable. |
| ⚠️ **UII-42** | COMPRESS | DON'Ts — invent tools / fabricate observations / loop | 351 | 2,5,7 | medium | Three rules, each padded with its own justification clause. |
| **UII-43** | COMPRESS | ## Forwarding and routing — CLARIFY-back handling | 324 | 2,6,10 | low | The 'don't answer permission questions, escalate them' half duplicates the Routing block's permission section; the correction loop needs one sentence. |
| **UII-44** | COMPRESS | ### Available routing tools | 275 | 2,6 | low | Two tool descriptions the schemas already carry, plus a first-agent note the generated position block states one screen earlier. |
| **UII-45** | COMPRESS | ### Temporal scope … — C. Multi-design requests | 262 | 2,7 | low | One rule, one example, no restatement of the carry-forward rule already given above. |
| **UII-46** | COMPRESS | ## Forwarding and routing — opening paragraph | 232 | 5,6 | low | 'Prose with no routing call is a HARD failure' is stated in generic_constraints.md and again in the Routing block — three copies. |
| ⛔ **UII-47** | COMPRESS | DOs — hand-off prose + English | 223 | 2,6 | low | The hand-off-prose rule is stated a third time in the Routing block; the authorship clause is the only part worth keeping here. |
| **UII-48** | COMPRESS | ## Your Role | 146 | 7,11 | low | Same content, one clause shorter, with the cross-reference dropped. |
| **UII-49** | COMPRESS | DOs — header + first two bullets | 125 | 4,11 | low | 'Act on the inputs in your hand-off' restates default behaviour; the exhaustive-tool-list rule is worth one line. |

<details><summary><b>Full text of each change</b></summary>

#### UII-01 · COMPRESS · −1622 chars · risk medium

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### 3. Design Intent and Functional Requirements · *Golden rules:* 2, 5, 7, 11 · *auditor's own id:* REC-01

**Why:** A 7-bullet checklist plus three justification paragraphs collapses to one paragraph plus the two records that actually change downstream behaviour (PRECISION DEMAND, the SOFT TARGET goal).

**Risk:** PRECISION DEMAND drives the Planner's forced refine loop; the replacement keeps the label, the free-form-not-a-flag rule and the understating warning verbatim in spirit. Losing the 'mandate vs. sketch precision' distinction is the only real loss.

**Cut from** `### 3. Design Intent and Functional Requirements`

**...through** `current design intent.`

**Replace with:**

```
### 3. DESIGN INTENT

One coherent paragraph — the CURRENT intent, not a log: purpose,
performance goals, constraints, aesthetics, reporting preferences ("don't
report back until viable"), and prior-attempt context only where it still
shapes the design.  Also state here, when present:

- **PRECISION DEMAND: <what they asked, at their strength>** — the user
  asking the design (especially the blade sections) to match a drawing
  closely, or to keep trying.  Free-form text, NOT a yes/no flag; the
  Planner reads it to decide whether to run the forced precision refine
  loop, so understating it means the loop never happens.  It is the user's
  MANDATE — separate from how precise the sketch itself is.
- The goal behind any SOFT TARGET recorded in §1, and any permission to
  vary a parameter that is tied to a design characteristic.
```

#### UII-02 · MERGE · −1502 chars · risk medium

*File:* `DC_prompt_fragments/dc_config/user_input_types/sketch_handling.md` · *Section:* ### Matching a ROUGH sketch / ### Matching a PRECISE sketch / ### Always true · *Golden rules:* 2, 6, 7, 8 · *auditor's own id:* REC-02

**Why:** Three sections of near-duplicate matching guidance, most of which describes DCIC/DCOI behaviour rather than the UII's, compress into one three-bullet block.

**Risk:** Shared fragment — also spliced into DC Input Inspector and DC Output Inspector, for whom this text is the primary matching contract. Verify with the DCOI audit before applying. Note the original also contains an internal inconsistency ('the 17 parameters' vs 'the 16 parameters'); the replacement drops both counts.

**Cut from** `### Matching a ROUGH sketch — qualitative`

**...through** `say so plainly — don't imply more iterations would close the gap.`

**Replace with:**

```
### Matching a sketch
* **Rough** — asymmetry, wobble, off-centre features and uneven lines are
  drawing artifacts, not intent.  "Matches the sketch" means same layout,
  elements and broad proportions, not identical line positions.  When the
  only remaining mismatch is sketch-quality, the design is CONVERGED — do
  not order another cycle.
* **Precise** — reproduce the drawn proportions (thickness, camber,
  high-point, chord, angle, middle-section position) as closely as the
  parameters allow; a real deviation from a deliberately-precise proportion
  IS a defect worth a revision.  Dimensions the user subordinated to the
  overall shape are SOFT TARGETS, not locked values.
* Either way, honor the INTENDED geometry, never literal pixels, and say
  plainly what the parameters could not capture — don't imply more
  iterations would close the gap.
```

#### UII-03 · COMPRESS · −1275 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### Temporal scope and Parameters Inputs interface blocks — A. Temporal merging · *Golden rules:* 2, 7, 11 · *auditor's own id:* REC-03

**Why:** Four worked ADD/MODIFY/REVERT examples of the same newer-wins principle collapse into one sentence naming the three operations.

**Cut from** `### Temporal scope and Parameters Inputs interface blocks`

**...through** `recent message in isolation.`

**Replace with:**

```
### Temporal scope — the CURRENT request

``user_query.txt`` is an append-only log of every user turn.  Build the
cumulative current state: a later turn ADDs detail, OVERRIDES a
contradicted detail (new wins, old discarded), or REVERTs to an earlier
one; "start over" / "ignore the above" discards everything before it;
anything still uncontradicted carries forward.  Design intent and
qualitative descriptions follow the same rule — they are the cumulative
current state, not the latest message alone.
```

#### UII-04 · COMPRESS · −1260 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## Reading prior attempts when the user references them · *Golden rules:* 2, 7, 9 · *auditor's own id:* REC-04

**Why:** The tool schemas already describe list_attempts/read_attempt; what remains is one when-to-use rule plus three canonical examples.

**Cut from** `## Reading prior attempts when the user references them`

**...through** `speculatively just wastes a round-trip.`

**Replace with:**

```
## Prior attempts

``list_attempts()`` / ``read_attempt(n, file)`` read this session's attempt
folders (``parameters.json``, ``description.txt``, render paths).  Use them
ONLY when the user makes a prior attempt the baseline — "same parameters as
the latest attempt but one fewer blade", "take attempt 3 but …",
"something between attempts 1 and 4" — and then write the resulting values
into QUANTITATIVE INPUTS.  For a generic request ("make it lighter") do not
call them; the DCIC chooses on its own.
```

#### UII-05 · COMPRESS · −1236 chars · risk medium

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### 1. QUANTITATIVE INPUTS — Soft targets · *Golden rules:* 2, 5, 7 · *auditor's own id:* REC-05

**Why:** Two paragraphs explaining how downstream agents will interpret the marker are justification the UII does not need; the marker, the example, the strength-reading rule and the newer-wins-over-a-pin rule are all kept.

**Risk:** SOFT TARGET is a deliberate recent feature (benchmark 7). The replacement keeps the marker syntax, the 'only when the user themselves subordinated it' guard, and the UI-pin-can-be-softened rule; it drops the downstream-reading paragraph.

**Cut from** `**Soft targets — a provided value the user subordinated to a goal.**`

**...through** `instead of a locked value, and drop it from the locked
FIXED set.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
**SOFT TARGET — a value the user subordinated to a goal.**  When the user
gives a value but says it is secondary to a qualitative goal ("here are
dimensions, but fit the sketched shape; the exact numbers matter less"),
keep it on its normal line with a marker naming the goal and how tightly to
hold the number:

    - impellerRadius: ~75 mm — SOFT TARGET (goal: match the sketched blade
      shape; keep near 75 mm if free, but vary freely to fit the shape)

The goal governs; the number is only the fallback where the goal does not
bear on the parameter.  Read the strength from the user's own wording ("not
as important" → fully expendable; unspecified → "keep reasonably close if
free").  Use it ONLY where the user themselves subordinated the value —
otherwise a stated value stays locked, including a UI-pinned (FIXED) one,
unless a LATER message subordinates it.  Name the goal in DESIGN INTENT.
```

#### UII-06 · COMPRESS · −980 chars · risk medium

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### Temporal scope … — B. Parameters Inputs interface blocks · *Golden rules:* 2, 7, 11 · *auditor's own id:* REC-06

**Why:** The snapshot-vs-delta walk is real mechanism, but it is stated three times over (per-block prose, then the absence rule, then the walk); once is enough.

**Risk:** This is the only statement of the FIXED-set forward walk. The replacement keeps REPLACE-on-FIXED, drop-on-RELEASED, and the MUST/MUST-NOT appearance rules verbatim in force.

**Cut from** `**B. Parameters Inputs interface blocks (auto-appended by the web`

**...through** `state after the most recent turn
is the active constraint set, and is what you reflect in
QUANTITATIVE INPUTS.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
**Parameters Inputs blocks** (auto-appended by the web UI).  ``"The user has
fixed the following values…"`` is a FULL SNAPSHOT of what the user is
currently pinning, not a delta; ``"The user is no longer constraining…"``
lists keys just released.  Either may be absent from a turn.  Walk the turns
forward: each FIXED block REPLACES the working set, each RELEASED block drops
its listed keys.  The final set MUST appear in QUANTITATIVE INPUTS; released
keys MUST NOT appear at all, not even as an annotation.
```

#### ⚠️ UII-07 · COMPRESS · −933 chars · risk medium

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — "### Routing is a tool call — MANDATORY" · *Golden rules:* 2, 5, 6, 10 · *auditor's own id:* REC-07

**Why:** Three paragraphs saying the same thing (invoke the tool, don't announce it, don't template the message), plus a retired ---ROUTING--- format nobody emits any more.

**Risk:** This block is generated in CODE, not a fragment, and is spliced into all six chain agents. The 'prose without a routing call halts the pipeline' invariant is preserved here and also stated once in generic_constraints.md.

**Cut from** `        "### Routing is a tool call — MANDATORY",`

**...through** `        "(one or two lines is plenty).",`

**Replace with:**

```
        "### Routing is a tool call — MANDATORY",
        "Every response that ends your turn MUST invoke exactly one "
        "routing tool; text emitted without one is silently discarded and "
        "the pipeline halts.  The tool's ``message`` argument IS the "
        "hand-off — free-form prose with what the recipient needs (the "
        "paths their tools require, what changed and why, the authorship "
        "of any non-user-authored value) and nothing more.  Invoke it in "
        "the same response where you finish your work; never announce it "
        "instead.  Any other text is your own brief reasoning — a line or "
        "two.",
```

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> Rewrites the same block of agents/shared/routing.py (the '### Routing is a tool call - MANDATORY' lines, 248-273) as REC-12 (DCII), REC-17 (TC) and REC-09 (DCOI). The block is built in code and injected into all six chain agents, so at most one of the four can be applied; the other three will silently fail to match, and the owner may believe a preserved clause is in place when it is not. Content-wise this version is safe (mandate, halt consequence, don't-announce all retained).
>
> *Safer:* Apply exactly one of the four - REC-17 (Tool Caller) preserves the most - and mark the other three as superseded rather than reviewing them independently.

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> Four different auditors each propose a DIFFERENT replacement for the identical code block in agents/shared/routing.py lines 248-273 ('### Routing is a tool call — MANDATORY' through '"(one or two lines is plenty).",'). My verbatim check confirms all four anchor to the same 1,658-char span. This is one shared code block spliced into all six chain agents, not four independent cuts — applying any two produces garbage or a silent no-op, and the char-savings claims (933/1050/703/1020) are not additive. All four replacements are syntactically valid Python and none uses {hub}, so no f-prefix is needed.
>
> *Safer:* Present these as ONE decision with four candidate wordings. REC-09 (DCOI) is the tightest that still keeps all three behavioural clauses (mandate, halt consequence, don't-announce-instead-of-calling); pick it and mark the other three superseded.

#### UII-08 · COMPRESS · −933 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### 1. QUANTITATIVE INPUTS — Format is flexible · *Golden rules:* 2, 7 · *auditor's own id:* REC-08

**Why:** A ten-line worked multi-design example plus a 'pick the clearest format' homily reduce to one sentence naming the three shapes.

**Cut from** `**Format is flexible — structure by intent.**  The simple`

**...through** `DCIC, DCII) read this section verbatim.`

**Replace with:**

```
Structure by intent: a plain list for a simple request; a labelled sub-list
per design for a multi-design request; a sentence naming the swept
parameter(s) and their bounds for a sweep; one sentence if there are no
quantitative constraints at all.  Downstream agents read this section
verbatim.
```

#### UII-09 · COMPRESS · −905 chars · risk medium

*File:* `DC_prompt_fragments/dc_config/user_input_types/sketch_handling.md` · *Section:* ### UII — for a PRECISE blade-section drawing … 1. A rough shape estimate (warm start) · *Golden rules:* 2, 7 · *auditor's own id:* REC-09

**Why:** The example block carries the whole instruction; the surrounding explanation of why a warm start helps is justification.

**Risk:** This is the Phase-3 UII warm-start feature. The SUGGESTED SECTION SHAPES label, the per-section triple, and the 'starting point, not user-locked' framing are all preserved — only the rationale is cut.

**Cut from** `### UII — for a PRECISE blade-section drawing, add a warm-start estimate + a crop region`

**...through** `The downstream loop refines it against the drawing, so do not over-invest.`

**Replace with:**

```
### UII — warm-start a precise blade-section drawing
The DC Input Creator authors the parameters but cannot see the images; you
can.  When an image carries a precise blade-section (airfoil) drawing,
eyeball its proportions into a ROUGH per-section estimate and record it in
QUALITATIVE DESCRIPTIONS:

    SUGGESTED SECTION SHAPES (rough estimate read from the precise drawing —
    a STARTING POINT for the DC Input Creator, NOT a user-locked value;
    refine within ranges):
      inner  ≈ 8% thick, 3% camber, max-thickness at ~3/10 chord
      middle ≈ 14% thick, 4% camber, max-thickness at ~3/10 chord
      outer  ≈ 10% thick, 3% camber, max-thickness at ~4/10 chord

This is your reading of the user's own drawing, not an invented number.  The
downstream loop refines it — do not over-invest.
```

#### UII-10 · COMPRESS · −889 chars · risk low

*File:* `DC_prompt_fragments/dc_config/user_input_types/sketch_handling.md` · *Section:* ### UII — … 2. A coarse crop region · *Golden rules:* 2, 7 · *auditor's own id:* REC-10

**Why:** Two near-identical worked examples (sections crop, top-view crop) plus an explanation of when the precision loop uses each collapse to one example and one clause.

**Cut from** `2. **A coarse crop region.**  When the section drawings occupy only part of a`

**...through** `and any whole-propeller crop later (the expensive 3D check).`

**Replace with:**

```
**A coarse crop region.**  Record a COARSE normalized crop box
``[x0, y0, x1, y1]`` for any region a downstream agent must compare against —
the blade-section drawings, and separately each whole-propeller view,
LABELLED with which view it is so the 3D check pairs the right sketch with
the right render:

    SKETCH CROP REGION (sections) — blade sections in 0346_3.png occupy
    roughly the bottom third: crop box [0.0, 0.72, 1.0, 1.0].

Coarse is fine; do not attempt a pixel-accurate box.
```

#### UII-11 · COMPRESS · −824 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### Capture, do not filter · *Golden rules:* 2, 7 · *auditor's own id:* REC-11

**Why:** Two paragraphs of reassurance that broad capture is correct reduce to the rule plus its canonical examples.

**Cut from** `### Capture, do not filter`

**...through** `asked only for extraction.`

**Replace with:**

```
### Capture, do not filter
Record even inputs the configurator cannot consume — "500 MPa yield
strength", "shiny material", "for cooling fins", a number with no obvious
application.  The DCIC and DCII decide what is actionable; that is true both
for a design request and for an extraction-only one.
```

#### UII-12 · COMPRESS · −799 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## User input layout (text + images) — image inspection + readability · *Golden rules:* 2, 7, 9 · *auditor's own id:* REC-12

**Why:** The read_user_inputs/view_images division of labour is repeated in the tools section three paragraphs later; keep the load-order rule and the readability signal, drop the restatement.

**Cut from** `When images are part of the user's inputs you MUST inspect them`

**...through** `QUALITATIVE DESCRIPTIONS or alongside the image's mention is plenty.`

**Replace with:**

```
Read the notes first, then ``view_images`` every image whose content you
must judge (count features, read geometry, resolve an ambiguous note); skip
only an image its note already fully describes.  Record how readable each
image is — a clean one-feature sketch is simple; a busy technical drawing,
or a photo no short description could stand in for, is complex — so
downstream agents know whether to re-load it.
```

#### UII-13 · COMPRESS · −779 chars · risk medium

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### 1. QUANTITATIVE INPUTS — HARD RULE, countable features · *Golden rules:* 2, 5, 7 · *auditor's own id:* REC-13

**Why:** An incident patch written at three times the length of the principle it encodes; sketch_notes.md already carries the blade-count instance of the same rule.

**Risk:** Removes one of the two statements of 'image is ground truth over the note text'. The replacement keeps count-one-by-one, image-beats-note, and the record-the-discrepancy behaviour.

**Cut from** `**HARD RULE — countable features in reference images must be`

**...through** `and use your image-count value in QUANTITATIVE INPUTS.`

**Replace with:**

```
**Count countable features explicitly.**  When an image shows discrete
elements mapping to an integer-count parameter, load the image and count
them one by one, traversing every instance once — never from a glance, and
never from the note text when the image itself is loaded.  Record the count
under the parameter name (a descriptive label when it maps to no parameter).
If your count and the note disagree, use yours and flag the discrepancy in
QUALITATIVE DESCRIPTIONS.
```

#### UII-14 · COMPRESS · −755 chars · risk medium

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## Forwarding and routing — design-generation forward · *Golden rules:* 2, 7, 10 · *auditor's own id:* REC-14

**Why:** The verbatim path lines are the only load-bearing part; the rest explains why the recipient is the natural next step, which the Routing section already states.

**Risk:** Preserves both <<PF_ON>>/<<PF_OFF>> branches so the PLANNER_FIRST=True configuration still assembles correctly. Verify the branch markers survive the edit.

**Cut from** `**Design-generation request → FORWARD.**<<PF_OFF>>  ``call_planner`` — the Planner`

**...through** `Receptionist (the Planner already ran, so no further chain steps run).<</PF_ON>>`

**Replace with:**

```
**Design-generation request → FORWARD.**<<PF_OFF>>  ``call_planner``.<</PF_OFF>><<PF_ON>>  ``call_dc_input_creator``.<</PF_ON>>
Your ``message`` MUST carry these lines verbatim:

    Extracted inputs file: <the path from your incoming "Extraction output file:" line>
    Current attempt: <absolute path>          # ONLY when the hand-off supplied one

The recipient does not auto-load the extraction — it reads the file at that
path.  Copy ``Current attempt:`` through only when your hand-off carried one.

**Extraction-only request**<<PF_OFF>> — forward it the same way; the Planner
recognises the ask and returns the answer.<</PF_OFF>><<PF_ON>> → ``call_orchestrator`` with a
brief summary; the Orchestrator relays it to the user.<</PF_ON>>
```

#### UII-15 · COMPRESS · −742 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## Your utility tools · *Golden rules:* 2, 9, 11 · *auditor's own id:* REC-15

**Why:** Bound tool schemas already carry the descriptions; the prompt only needs the call-discipline rules (once, verbatim paths, batch OCR regions, mandatory write).

**Cut from** `## Your utility tools`

**...through** `specific ``_note.txt``), ``read_image_notes`` (all notes at once).`

**Replace with:**

```
## Your tools
- ``read_user_inputs(path)`` — call ONCE with the ``Input directory:`` path
  from your hand-off, verbatim.  Returns the text files and every
  ``_note.txt`` and LISTS the images; it does not load them.
- ``view_images(paths)`` — load images (with their OCR text) by those paths;
  also to re-load an image whose bytes a hand-off stripped.
- ``ocr_regions(image_path, region_ids)`` — re-read faint or garbled
  callouts at higher resolution; batch every region into ONE call.
- ``write_extraction(path, quantitative, qualitative, intent)`` — mandatory;
  write to the ``Extraction output file:`` path verbatim, since downstream
  reads that exact file.  "None specified." for an empty section; the tool
  adds the headers.

For revisiting one file: ``list_input_files``, ``read_input_text(path)``,
``read_image_notes``.
```

#### ⚠️ UII-16 · COMPRESS · −739 chars · risk medium

*File:* `DC_prompt_fragments/dc_config/parameters.md` · *Section:* whole file · *Golden rules:* 3, 11 · *auditor's own id:* REC-16

**Why:** Same 16 parameters and ranges, tabular instead of padded prose — the list stays inline per the owner's rule, it just stops paying for alignment whitespace and per-section headers.

**Risk:** Spliced into 7 agents; a mis-transcribed range here is a systemic failure. The '% of that section's OWN chord' gotcha is added explicitly because it is a known bug source. Diff the numbers against the original before applying.

**Cut from** `### Global / ring`

**...through** `16. outerAngle      (degrees)                   — Angle of attack [2; 25]`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
| # | name | unit / type | range |
|---|------|-------------|-------|
| 1 | bladeCount | integer | 3–6 |
| 2 | impellerRadius | mm (outer ring radius) | 60–80 |
| 3 | impellerThickness | mm (ring wall) | 1–5 |
| 4 | innerThickness | % of chord | 3–24 |
| 5 | innerMaxPos | tenths of chord (int) | 2–8 |
| 6 | innerCamber | % of chord | 0–9 |
| 7 | innerChord | mm | 3–11 |
| 8 | innerAngle | degrees | 2–25 |
| 9 | middlePos | fraction of blade span | 0.3–0.7 |
| 10 | middleChord | mm | 10–30 |
| 11 | middleAngle | degrees | 2–25 |
| 12 | outerThickness | % of chord | 3–24 |
| 13 | outerMaxPos | tenths of chord (int) | 2–8 |
| 14 | outerCamber | % of chord | 0–9 |
| 15 | outerChord | mm | 10–30 |
| 16 | outerAngle | degrees | 2–25 |

Thickness and camber are percentages of THAT section's OWN chord, so pinning
a chord caps the absolute size.  maxPos is the chordwise position of maximum
thickness.  The middle section has no own thickness/camber/maxPos — it is
interpolated.  The outer-ring HEIGHT is derived, not a parameter.
```

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> The table row `| 9 | middlePos | fraction of blade span | 0.3-0.7 |` drops the from-ROOT definition and formula that the current file carries: '0 = root (hub, r = 4 mm), 1 = tip; radius = 4 + middlePos·(impellerRadius - 4) mm'. I traced where that survives: only modelling_notes.md (spliced into dc_input_creator and dc_input_inspector ONLY) and structure.md (dc_input_creator + user_input_inspector ONLY) — verified by grep over all agents/*/prompt.md. parameters.md is spliced into 7 prompts; for the Planner, Orchestrator, Receptionist and Tool Caller it is the ONLY source of middlePos semantics. The Planner is exactly the agent that turns 'put the middle section at 40 mm' into a middlePos directive (its prompt reasons about middlePos at lines 89 and 269) and it has no modelling_notes and no dc_structure. 'fraction of blade span' alone does not block the middlePos = r/impellerRadius reading, which is the documented past error (old GTs and prompt fragments used from-centre distance/R and were wrong; commit 9ed7c2a fixed it). Two mechanical notes: quote_end has one extra space ('16. outerAngle      (degrees)' — the file has 5 spaces, not 6), and every file in this set is CRLF while the replacements are LF, so exact-match edits will need care. The 16 ranges themselves I diffed one by one against the file — all correct, and the added '*Thickness/*Camber are % of that section's OWN chord' and 'middle section is interpolated' lines are genuine improvements.
>
> *Safer:* Keep the table exactly as proposed and append one line under it: "`middlePos` is measured from the blade ROOT, not the centre: radius = 4 + middlePos·(impellerRadius - 4) mm, hub = 4 mm (0 = root, 1 = tip)." (~35 tokens, restores the invariant for all 7 agents.)

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> The table transcribes all 16 names and ranges correctly (I diffed every row against DC_prompt_fragments/dc_config/parameters.md), but it deletes the middlePos gloss that commit 9ed7c2a added on purpose: 'Middle-section position along the blade: 0 = root (hub, r = 4 mm), 1 = tip; radius = 4 + middlePos*(impellerRadius - 4) mm'. That commit's message is explicit - it replaced a WRONG 'x impellerRadius' reading ('NOT middlePos * impellerRadius', matching web/feg/profiles.js). The replacement's 'fraction of blade span' alone re-opens exactly the misreading that was fixed. Coverage check: the formula also lives in modelling_notes.md (spliced only into DCIC + DCII) and structure.md (only DCIC + UII), so parameters.md is the ONLY copy the Orchestrator, Planner, Receptionist and Tool Caller ever see - and the Planner is the agent that writes numeric middlePos directives.
>
> *Safer:* Add one line under the table: 'middlePos is measured from the 4 mm hub: radius = 4 + middlePos*(impellerRadius - 4) mm, NOT middlePos * impellerRadius.'

> ⚠️ **Verifier — QUOTE_WRONG**
>
> quote_end is not verbatim. The cut gives '16. outerAngle      (degrees)                   — Angle of attack [2; 25]' with SIX spaces after 'outerAngle'; parameters.md line 25 has FIVE ('16. outerAngle     (degrees)...', confirmed byte-exact with cat -A). Separately: I diffed all 16 names, units and ranges against the file and the table is correct, and nothing parses this file at runtime — but the replacement drops the middlePos definition 'radius = 4 + middlePos·(impellerRadius − 4) mm, 0 = root (hub, r = 4 mm)'. That formula survives only in modelling_notes.md ($modelling_notes) and structure.md ($dc_structure), and the splice map shows the Planner receives $parameter_list but NEITHER of those. The Planner is the agent that issues middlePos directives (agents/planner/prompt.md:269), and the from-centre vs from-4 mm-root confusion is a documented real bug in this project.
>
> *Safer:* Fix the spacing in quote_end, and append one line under the table (88 chars): 'middlePos is measured from the 4 mm hub: radius = 4 + middlePos·(impellerRadius − 4) mm.'

#### UII-17 · COMPRESS · −671 chars · risk medium

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — "### Permission / authorisation issues" · *Golden rules:* 2, 7, 10 · *auditor's own id:* REC-17

**Why:** Two long paragraphs to say: re-read the hand-off, act on an authorisation that plausibly covers it, escalate a missing one, CLARIFY only for fixable data.

**Risk:** Code, not a fragment; affects all six chain agents. The anti-ritual-re-confirmation rule and the 'previous agent cannot grant permission' rule are both kept.

**Cut from** `        f"### Permission / authorisation issues → {hub} (not "`

**...through** `        "NOT for permission questions.",`

**Replace with:**

```
        f"### Permission / authorisation issues → {hub}",
        "Before escalating, re-read the incoming hand-off and any file it "
        "points to: if it already names an authorisation that plausibly "
        "covers the action, act on it — differing wording is not a reason "
        "for a ritual re-confirmation round-trip.  If it is truly missing "
        f"or ambiguous, ESCALATE to the {hub}; the previous agent cannot "
        "grant permission.  CLARIFY back is for data / wording / format "
        "issues only.",
```

#### UII-18 · COMPRESS · −670 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## User input layout (text + images) — directory listing · *Golden rules:* 2, 7 · *auditor's own id:* REC-18

**Why:** The UII_MAY_READ_PREVIOUS_EXTRACTION mechanics and the Receptionist's pairing guarantee are context the agent never acts on; the two rules that matter are 'never copy forward' and 'the note is user intent'.

**Cut from** `## User input layout (text + images)`

**...through** `its note into the extraction.`

**Replace with:**

```
## User inputs
  * ``user_query.txt`` — every user turn, chronological.
  * ``extracted_inputs.txt`` — a previous extraction, when the workflow
    exposes it.  INFORMATIONAL only: never copy lines forward; always
    recompute from ``user_query.txt``.
  * ``input_images/`` — optional reference images, each paired with a
    ``<name>_note.txt``.  The note is first-class user intent, not optional
    commentary — integrate BOTH the image and its note.
```

#### UII-19 · REPLACE_WITH_EXAMPLES · −656 chars · risk low

*File:* `DC_prompt_fragments/dc_config/user_input_types/sketch_notes.md` · *Section:* intro + ### Common drawing artifacts in propeller sketches · *Golden rules:* 1, 2, 7 · *auditor's own id:* REC-19

**Why:** Four enumerated artifact cases are four instances of one principle — the configurator renders idealised geometry, so drawn deviations from it are noise.

**Cut from** `Configurator-specific patterns the operator has observed in how users`

**...through** `representative of the sketch's average appearance.`

**Replace with:**

```
Configurator-specific patterns in how users sketch propellers for THIS DC.

### Drawing artifacts to ignore
The configurator always renders blades structurally connected to the ring, a
clean cylindrical hub at the geometric centre, identical blades, and a
uniform-thickness ring.  So a drawn tip gap or overshoot, an off-centre or
oval hub, blade-to-blade curvature differences and an uneven ring are
drawing noise: pick a single representative value, don't replicate them.
```

#### UII-20 · DELETE · −651 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## End-of-session feedback message (read-only) · *Golden rules:* 4, 7, 8 · *auditor's own id:* REC-20

**Why:** Read-only notice that a HumanMessage may appear, plus a scope restatement — it steers no action, and the shared outro it splices tells the reader to 'fold it into your DH answers', which the UII never writes.

**Cut from** `## End-of-session feedback message (read-only)`

**...through** `$eos_feedback_outro`

**Replace with:** *(nothing — pure deletion)*

#### UII-21 · COMPRESS · −628 chars · risk low

*File:* `DC_prompt_fragments/dc_config/hard_constraints_dc.md` · *Section:* ### Domain hard rules (every agent) · *Golden rules:* 2, 5, 8 · *auditor's own id:* REC-21

**Why:** Three exhaustive prohibition catalogues (mesh ops, analysis types, formats) keep their canonical examples but drop the enumeration padding and the DON'T-prefix drumbeat.

**Risk:** Shared by 8 agents. The 'no parameters outside the named set' rule — the one with real bug history — is kept first and unhedged.

**Cut from** `### Domain hard rules (every agent)`

**...through** `inspection and say so plainly.`

**Replace with:**

```
### Domain hard rules (every agent)
- Express a design ONLY in the $parameter_count named configurator parameters.
  There are no others — hub_radius, fillet_radius, tip_clearance or any
  "supplemental" parameter do not exist; reject them.  Geometry changes only
  by changing those parameters and regenerating (DC Input Creator → Tool
  Caller); there is no mesh-editing capability.
- No mesh post-processing of any kind — booleans, welding, remeshing, hole
  filling, manifold repair, fillets, struts, supports, or anything else not
  derivable from the parameters.
- Don't offer analysis the system cannot perform (thrust / flow / pressure /
  efficiency / CFD, or FEA / stress / material / tolerance), other output
  formats (STL, STEP, …), extra camera angles, cross-sections, or
  higher-resolution renders.
- The only mesh metrics are watertightness, volume and degenerate-face count.
```

#### UII-22 · COMPRESS · −616 chars · risk low

*File:* `DC_prompt_fragments/dc_config/user_input_types/sketch_handling.md` · *Section:* ### UII responsibility — record the sketch's precision in the extraction · *Golden rules:* 2, 7 · *auditor's own id:* REC-22

**Why:** The two canonical strings are the instruction; the surrounding explanation of which downstream agent reads them is justification.

**Cut from** `### UII responsibility — record the sketch's precision in the extraction`

**...through** `unmeetable proportions on a rough sketch or discard real proportions on a
precise one.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### UII responsibility — record the precision
State each reference image's precision in the DESIGN INTENT section of
``extracted_inputs.txt``, e.g. "ROUGH SKETCH — match qualitatively; treat
asymmetry / wobble as drawing artifacts" or "PRECISE SKETCH (measured blade
sections) — reproduce the drawn proportions (thickness / camber /
high-point / chord / angle) as closely as the parameters allow".  Without
it downstream agents guess the strictness and get it wrong in both
directions.
```

#### UII-23 · COMPRESS · −605 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### 1. QUANTITATIVE INPUTS — line-label formats · *Golden rules:* 2, 7, 11 · *auditor's own id:* REC-23

**Why:** Four template lines with placeholder-heavy annotations plus a 'use the parameter list as source of truth' reminder reduce to two concrete examples.

**Cut from** `Record one quantitative input per line.  When the value maps`

**...through** `configurator uses.`

**Replace with:**

```
Record one quantitative input per line.  When the value maps verbatim to a
configurator parameter in that parameter's own unit, label the line with the
parameter name:

    impellerRadius: 70 mm

Otherwise label the real-world quantity, give the user's unit / frame, and
name the parameter(s) it relates to — conversion is the DCIC's job:

    tip speed: 40 m/s (real-world; relates to impellerRadius)
```

#### ⚠️ UII-24 · SCOPE_PER_AGENT · −600 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* Blade-sections visualizer block · *Golden rules:* 8, 9 · *auditor's own id:* REC-24

**Why:** The shared 758-char tool description is for agents that can call or read the tool; the UII neither calls it nor reads its output — it only has to flag a sections-centred request, which its per-agent overlay already says.

**Cut from** `<<BSV_ON>>
$blade_sections_visualizer`

**...through** `<</BSV_ON>><<BSV_OFF>>$blade_sections_visualizer_off<</BSV_OFF>>`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
<<BSV_ON>>The system can render just the three blade cross-sections, much faster than
the full 3D propeller.  $blade_sections_visualizer_per_agent<</BSV_ON>>
```

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> Three cuts on the STANDING DIRECTIVES bullet in generic_constraints.md. REC-24 (TC) and REC-30 (DCIC) target the identical 454-char span (lines 12-18) with different replacements; REC-28 (UII) targets an 867-char span (lines 6-18) that fully CONTAINS both, so applying REC-28 after either of the others fails to anchor. The invariant itself is safe in all three — the runtime does not depend on the prompt wording here: standing_directives.is_present() matches the directive TEXT, not the header, and orchestrator.py:738 re-stamps the canonical BLOCK_START on every hop in _DIRECTIVE_CARRIERS, so even a paraphrased header self-heals.
>
> *Safer:* Take REC-28 (UII) alone — it is the superset and already keeps 'reproduce UNCHANGED' plus 'only the Planner may set or change it'. Mark REC-24 and REC-30 superseded.

#### UII-25 · COMPRESS · −580 chars · risk low

*File:* `DC_prompt_fragments/tools_config/hard_constraints_tools.md` · *Section:* ### Tool-use hard rules (every agent) · *Golden rules:* 2, 7, 8 · *auditor's own id:* REC-25

**Why:** Each of the three rules is stated then re-explained; the append-only bullet in particular restates itself four times.

**Risk:** Shared by 8 agents. The UII writes no attempt folders at all, so the third bullet is dead weight for this agent specifically — a per-agent overlay would remove it entirely.

**Cut from** `### Tool-use hard rules (every agent)`

**...through** `folder's parameters.`

**Replace with:**

```
### Tool-use hard rules (every agent)
- Never invent or guess a path: read tools take only the paths a hand-off
  label gives (``Input directory:`` / ``Extracted inputs file:`` /
  ``Parameters file:`` / ``Render images:`` / ``Current attempt:``) or an
  upstream tool's return value.
- Route EVERY arithmetic operation — sums, ratios, conversions, range
  comparisons — through the ``calculate`` tool; never mental arithmetic.
  Batch every expression for the turn into ONE call.
- Attempt folders are append-only: never edit or delete a
  ``parameters.json`` or mesh in one, and write only into the ``Current
  attempt:`` folder.  To build on an old set, COPY its values into a new
  attempt.  Re-running render/QC on an attempt that already has renders
  reuses them in place.
```

#### UII-26 · REPLACE_WITH_EXAMPLES · −570 chars · risk low

*File:* `DC_prompt_fragments/dc_config/user_input_types/sketch_handling.md` · *Section:* ### Judging a sketch's precision · *Golden rules:* 2, 11 · *auditor's own id:* REC-26

**Why:** Four bulleted evidence categories with sub-examples compress into one sentence naming the same evidence.

**Cut from** `### Judging a sketch's precision`

**...through** `feature within it, on its own.`

**Replace with:**

```
### Judging a sketch's precision
Judge each image — and each feature in it — on the spectrum from rough
freehand doodle to measured drawing, weighing what the user says ("rough" /
"just an idea" vs "to scale" / "match exactly"), line quality, and whether
it carries dimensions, a scale bar, gridlines or clean CAD-like geometry.
A whole-propeller doodle is usually rough; a dedicated blade top-view or a
blade-section profile often carries proportions meant to be reproduced.  A
single input can be MIXED.
```

#### UII-27 · DELETE · −552 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — "### Do not loop — ESCALATE when stuck" · *Golden rules:* 5, 6 · *auditor's own id:* REC-27

**Why:** Verbatim duplicate of the 'DON'T loop: if you are about to call the same tool with the same arguments…' bullet in generic_constraints.md, which every agent already has.

**Risk:** Code, not a fragment; removes ~550 chars from all six chain agents. Keep the generic_constraints bullet (see REC-33) or this invariant disappears entirely.

**Cut from** `        "### Do not loop — ESCALATE when stuck",`

**...through** `        "consult another agent, or ask the user.  Never silently loop.",`

**Replace with:** *(nothing — pure deletion)*

#### ⛔ UII-28 · COMPRESS · −526 chars · risk medium

> ⛔ **Span conflict.** This cut's text overlaps `UII-47` in the same file. Apply only one of them, or merge the replacements by hand.


*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DOs — CHAIN_ONLY block (pipeline / escalate / standing directives) · *Golden rules:* 2, 5, 7 · *auditor's own id:* REC-28

**Why:** The forward/escalate rules are restated in every agent's generated Routing block; only the STANDING DIRECTIVES verbatim-carry rule is unique here, and it needs one sentence, not seven lines.

**Risk:** Shared by 8 agents. STANDING DIRECTIVES verbatim propagation is a Phase-1 precision feature — the replacement keeps 'reproduce unchanged' and 'only the Planner may set it'.

**Cut from** `<<CHAIN_ONLY>>- DO follow the natural pipeline: when your work succeeds and the`

**...through** `set or change it.
<</CHAIN_ONLY>>`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
<<CHAIN_ONLY>>- DO forward to your natural next agent when your work succeeds and no one
  asked you to report back; ESCALATE to the Orchestrator the moment
  something blocks you that no chain agent can fix.
- DO reproduce any ``=== STANDING DIRECTIVES … ===`` block from your
  incoming hand-off UNCHANGED in your outgoing one — never alter,
  summarise, re-order or omit it; only the Planner may set or change it.
<</CHAIN_ONLY>>
```

#### UII-29 · COMPRESS · −522 chars · risk medium

*File:* `DC_prompt_fragments/dc_config/user_input_types/sketch_handling.md` · *Section:* ### Filled-in templates and forms · *Golden rules:* 1, 2, 7 · *auditor's own id:* REC-29

**Why:** An incident patch (the Ø160-vs-Ø140 form case) written at three times the length of its principle: printed content is scaffolding, only the added marks are input.

**Risk:** Shared with DCII/DCOI. Keeps the canonical Ø160/Ø140 example, the 'never enforce a printed range as a limit' rule, and the blank-copy comparison, since these came from a real misread.

**Cut from** `### Filled-in templates and forms`

**...through** `handwritten and irregular.`

**Replace with:**

```
### Filled-in templates and forms
Some reference images are a PRE-PRINTED FORM the user drew on.  Printed
guide lines, reference circles, min/max callouts, scales, grids and fixed
labels are SCAFFOLDING — they show what to specify, and are never the user's
value and never a limit.  Only the darker, irregular, handwritten marks are
input: a form printing "Ø160 / Ø120" guides and "5 mm max" with a hand-drawn
outline labelled "Ø140" and a ~3 mm ring means 140 and 3.  A blank copy of
the same form, if you have one, identifies the scaffolding exactly.
```

#### UII-30 · COMPRESS · −484 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### 2. QUALITATIVE DESCRIPTIONS · *Golden rules:* 2, 6, 7 · *auditor's own id:* REC-30

**Why:** The released-parameter note duplicates the temporal-scope rule two sections above; the authorisation guidance needs one sentence.

**Cut from** `Free-form prose describing things that cannot be quantised:`

**...through** `freely, prioritise balance").`

**Replace with:**

```
Free-form prose for what cannot be quantised: shapes, aesthetics,
comparisons, subjective impressions, image-reading hints that do not resolve
to a number.  Be generous.  Summarise here any natural-language permission
the user gave to vary specific values, with its scope (blanket or
per-parameter), exclusions and conditions.
```

#### UII-31 · COMPRESS · −446 chars · risk medium

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — "### How to decide where to route" · *Golden rules:* 2, 6, 10 · *auditor's own id:* REC-31

**Why:** Four long conditionals restating FORWARD / report-back / CLARIFY / ESCALATE, which the per-agent routing fragment lists again immediately below.

**Risk:** Code, not a fragment; affects all six chain agents. The default-is-continue rule is preserved because it is the one non-obvious part.

**Cut from** `        "### How to decide where to route",`

**...through** `        f"can fix it, route to the {hub} (ESCALATE).",`

**Replace with:**

```
        "### How to decide where to route",
        f"Continue the pipeline unless the {hub}'s instruction told you to "
        "report back — no instruction means continue.  CLARIFY to the "
        "previous agent only for ambiguity or data it can actually fix; "
        f"ESCALATE to the {hub} when nothing in the chain can fix it.",
```

#### UII-32 · COMPRESS · −434 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### Temporal scope … — D. NEVER include historical entries · *Golden rules:* 2, 5, 7 · *auditor's own id:* REC-32

**Why:** Three examples of the same annotation anti-pattern plus a cross-reference reduce to one line and one parenthetical.

**Cut from** `**D. NEVER include historical or annotation-style entries.**  The`

**...through** `rules below).`

**Replace with:**

```
Never write history: no ``X: 4 (formerly fixed)``, no "the user previously
wanted Y but now wants Z".  A superseded or released entry is simply
OMITTED.  (An ``OUT OF RANGE`` note is a current fact, not history, and
stays — see below.)
```

#### UII-33 · COMPRESS · −403 chars · risk low

*File:* `DC_prompt_fragments/dc_config/structure.md` · *Section:* whole file · *Golden rules:* 2, 11 · *auditor's own id:* REC-33

**Why:** Same facts as a prose paragraph instead of a nested list; the middlePos formula and the span-not-radius gotcha are kept verbatim because they are a real modelling trap.

**Risk:** Shared with the DC Input Creator.

**Cut from** `The propeller consists of:`

**...through** `Outer section: the blade tip, at the outer radius (impellerRadius), furthest from the centre.`

**Replace with:**

```
The propeller: a central hub of FIXED radius 4 mm (the blade root); an outer
ring characterised by radius and wall thickness (its height is derived, not a
parameter); and blades spanning hub → ring in three radial sections — inner
(at r = 4 mm), middle, and outer (at impellerRadius).  The middle section's
radius = 4 + middlePos·(impellerRadius − 4) mm, i.e. middlePos is a fraction
of the blade SPAN (0 = root, 0.5 = exact midpoint, 1 = tip), not of the
radius, and need not be the geometric midpoint.
```

#### UII-34 · COMPRESS · −396 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### 1. QUANTITATIVE INPUTS — STRICT rules (first two bullets) · *Golden rules:* 2, 6, 7 · *auditor's own id:* REC-34

**Why:** The second bullet is a verbatim restatement of the temporal-scope rule; the first needs one sentence, not five lines with a 'scan your draft' reminder.

**Cut from** `**STRICT rules for QUANTITATIVE INPUTS:**`

**...through** `"Temporal scope" above.)`

**Replace with:**

```
**STRICT rules:**

- One line per quantity within a single design's listing (multi-design
  sub-lists may legitimately repeat a parameter).  A revision overwrites its
  line; a released parameter's line is dropped, never annotated.
```

#### UII-35 · COMPRESS · −385 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## What to Extract — categorisation rule · *Golden rules:* 2, 5, 7, 11 · *auditor's own id:* REC-35

**Why:** The 'Numeric ≠ matches a parameter' paragraph repeats the QUANTITATIVE bullet it follows; fold it in.

**Cut from** `## What to Extract — categorisation rule`

**...through** `the user's unit / frame; conversion is the DCIC's job.`

**Replace with:**

```
## What to extract

Sort every observation — text, image notes, image annotations — by the
NATURE of the data, not by whether it matches a configurator parameter:

  * **QUANTITATIVE** — numerical, or resolving to a number.  A number whose
    unit or frame matches no parameter still belongs here: annotate the
    user's unit / frame; conversion is the DCIC's job.
  * **QUALITATIVE** — everything else: descriptive prose, adjectives,
    comparisons, aesthetic or stylistic cues.
```

#### ⚠️ ⛔ UII-36 · COMPRESS · −383 chars · risk medium

> ⛔ **Span conflict.** This cut's text overlaps `UII-40` in the same file. Apply only one of them, or merge the replacements by hand.


*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DON'Ts — routing-tool channel paragraph · *Golden rules:* 2, 5, 6 · *auditor's own id:* REC-36

**Why:** Says 'routing is a tool call' three times in one bullet, and the generated Routing block says it again; keep the failure mode once, in the strongest wording.

**Risk:** This is the fix for the real 'prose with no routing call halts the pipeline' failure. The replacement keeps the halt consequence and the same-response requirement; do not apply this AND delete the routing.py version (REC-07 compresses rather than deletes it).

**Cut from** `<</CHAIN_ONLY>>- DON'T communicate to another agent in plain prose.  The ONLY channel`

**...through** `only exceptions are the Receptionist's direct user replies and the
Orchestrator's final user-facing wrap-up.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
<</CHAIN_ONLY>>- DON'T communicate to another agent in plain prose.  The only channel is a
  routing tool call (``call_<agent>``); its ``message`` argument IS the
  hand-off.  Text emitted without a routing call is silently discarded and
  the pipeline halts — no matter how complete your reasoning looks — so
  invoke the tool in the same response where you finish your work, rather
  than announcing it.
```

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> Same defect as REC-03: the replacement ends at '...rather than announcing it.' and drops 'the only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up'. generic_constraints.md is shared with the Receptionist, which is a _NON_CHAIN_AGENTS entry that gets no routing_instructions() and whose own prompt requires plain-text replies in Situation B. The clause survives nowhere else in the 7-agent tree (grep: only agents/5agent/prompt_fragments/generic_constraints_5agents.md:53 has an equivalent, and that file is a separate topology override). This cut is also byte-identical in region to REC-31 (DC Input Creator) and REC-21 (Tool Caller) — three proposals for one edit.
>
> *Safer:* End the replacement with: "...rather than announcing it.  The Receptionist's direct user replies are the sole exception."

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> Same defect: the replacement keeps the halt consequence and the same-response requirement but silently drops 'the only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up.' The Receptionist and Orchestrator both splice this fragment ($hard_constraints_generic at agents/receptionist/prompt.md:407 and agents/orchestrator/prompt.md:517) and both emit user-facing plain text with no routing call.
>
> *Safer:* End the replacement with '... rather than announcing it - the Receptionist's direct user replies and the Orchestrator's user-facing wrap-up are the only exceptions.'

> ⚠️ **Verifier — QUOTE_WRONG**
>
> quote_end is not verbatim: it gives 'only exceptions are the Receptionist's direct user replies and the\nOrchestrator's final user-facing wrap-up.' with no indent on the second line, but generic_constraints.md line 55 is '  Orchestrator's final user-facing wrap-up.' (two leading spaces, confirmed with cat -A). Separately, the replacement drops that exception clause entirely, and this bullet is outside <<CHAIN_ONLY>> so the Receptionist and Orchestrator read it — both legitimately end turns with plain text and no routing call (receptionist.py:8/174, orchestrator.py:542), and neither receives routing_instructions() as a second source. Also collides with REC-21 (TC) and REC-31 (DCIC), two different replacements for exactly this bullet.
>
> *Safer:* Anchor on the two-space-indented quote_end, and close the bullet with '...the pipeline halts — the only exceptions are the Receptionist's direct user replies and the Orchestrator's final wrap-up.'

#### UII-37 · COMPRESS · −362 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## Forwarding and routing — ESCALATE / first-agent note · *Golden rules:* 6, 10 · *auditor's own id:* REC-37

**Why:** The 'you are the first agent, there is no back' paragraph is already in routing_user_input_inspector_uii_first.md and in the generated position block — three copies of one fact.

**Risk:** Keeps the <<PF_ON>> branch so PLANNER_FIRST=True still assembles.

**Cut from** `**ESCALATE → ``call_orchestrator``** when the request is out of scope,`

**...through** `DCIC.<</PF_ON>>`

**Replace with:**

```
**ESCALATE → ``call_orchestrator``** when the request is out of scope, asks
for something not in the user's files, or you hit an unrecoverable error.<<PF_ON>>
``call_planner`` is also your help channel for a genuinely hard extraction
and where you CLARIFY back — but it is not a default forward.<</PF_ON>>
```

#### UII-38 · SCOPE_PER_AGENT · −362 chars · risk medium

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## Qualitative-to-Quantitative Hints · *Golden rules:* 3, 8 · *auditor's own id:* REC-38

**Why:** The UII is explicitly forbidden from inventing parameter values; the qualitative→parameter mapping table is the DC Input Creator's job and is spliced there already.

**Risk:** Removes the UII's only view of how descriptors map to parameters. That is intended — but if extraction quality depends on the UII hinting at a target parameter in a real-world-label line, keep the fragment. Fragment stays in place for the DCIC either way.

**Cut from** `## Qualitative-to-Quantitative Hints`

**...through** `$qualitative_examples`

**Replace with:** *(nothing — pure deletion)*

#### ⚠️ UII-39 · COMPRESS · −353 chars · risk medium

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### 1. QUANTITATIVE INPUTS — OUT OF RANGE · *Golden rules:* 2, 7 · *auditor's own id:* REC-39

**Why:** The rule survives; the paragraph explaining why a downstream agent shouldn't have to rediscover the breach is justification.

**Risk:** Keeps the only statement of the out-of-range visibility rule. The original's example (``outerRadius: 160 mm — OUT OF RANGE (allowed [10; 140])``) names a parameter and a range that do not exist in this configurator; the replacement uses a real one.

**Cut from** `- **Mark a value that is OUT OF RANGE.**  When a line maps directly to a`

**...through** `real-world quantity needing conversion is not yours to judge.`

**Replace with:**

```
- **Flag OUT OF RANGE values.**  When a line maps directly to a parameter in
  that parameter's own unit, compare it to the range in the list above; if it
  falls outside, record the user's value unchanged and append the breach:

      - impellerRadius: 160 mm — OUT OF RANGE (allowed [60; 80])

  Never correct, clamp or drop it.  A real-world quantity still needing
  conversion is not yours to judge.
```

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> The premise is right (outerRadius is not a parameter of this DC) but the fix breaks a documented layering rule. DC_prompt_fragments/dc_config/README.md states 'Edit these files to retarget the multi-agent system at a different design configurator (DC)... Per-agent templates live in each agent's own folder (agents/<agent_name>/prompt.md)' - the agent templates are the DC-neutral layer, which is why they use $parameter_list / $parameter_count. Verified: `grep -c impeller agents/*/prompt.md` returns 0 for all nine prompts today. Writing 'impellerRadius: 160 mm - OUT OF RANGE (allowed [60; 80])' into agents/user_input_inspector/prompt.md would be the first propeller literal in the generic layer, and becomes a wrong example the moment the DC is retargeted. REC-05 (User Input Inspector, SOFT TARGET) introduces the same leak with 'impellerRadius: ~75 mm'. The rule itself is an incident patch (commit e46b194: 'the User Input Inspector now marks a value that falls outside its range, which is the only guard on an extraction-only request') and the compression otherwise preserves it.
>
> *Safer:* Keep the compression but use a DC-neutral placeholder in the example, matching the style already used elsewhere in these prompts: '- <parameter>: <value> <unit> - OUT OF RANGE (allowed [<min>; <max>])'. Same for REC-05's soft-target example.

#### ⛔ UII-40 · COMPRESS · −352 chars · risk low

> ⛔ **Span conflict.** This cut's text overlaps `UII-36` in the same file. Apply only one of them, or merge the replacements by hand.


*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DON'Ts — CHAIN_ONLY block (permissions / retry / user reply) · *Golden rules:* 2, 6, 10 · *auditor's own id:* REC-40

**Why:** The permission-routing rule is stated at length again in the generated Routing block; the other two need one line each.

**Cut from** `<<CHAIN_ONLY>>- DON'T bounce permission questions back to the previous agent.`

**...through** `never write the user-facing message yourself.
<</CHAIN_ONLY>>`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
<<CHAIN_ONLY>>- DON'T bounce permission questions backward — authorisations come from the
  user, the Planner or the Orchestrator; route them to the Orchestrator.
- DON'T retry a failing step blindly; when the same class of failure
  recurs, ESCALATE.
- DON'T script the final user-facing reply — the Receptionist composes it.
<</CHAIN_ONLY>>
```

#### UII-41 · COMPRESS · −351 chars · risk low

*File:* `DC_prompt_fragments/dc_config/user_input_types/sketch_notes.md` · *Section:* Number of blades — COUNT IT · *Golden rules:* 2, 7 · *auditor's own id:* REC-41

**Why:** Rule plus exception, minus the reassurance about why blade count is reliable.

**Cut from** `  * **Number of blades — COUNT IT, and trust the count.** The blade count`

**...through** `blades actually drawn.`

**Replace with:**

```
### Blade count — count it, and trust the count
Blade count is a deliberate, discrete attribute the user means exactly:
count the blades in the top-down view carefully even when the rest of the
sketch is rough.  A count stated by other means — "6 blades" in text, a
"×6" label beside a single blade — overrides the number actually drawn.
```

#### ⚠️ UII-42 · COMPRESS · −351 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DON'Ts — invent tools / fabricate observations / loop · *Golden rules:* 2, 5, 7 · *auditor's own id:* REC-42

**Why:** Three rules, each padded with its own justification clause.

**Risk:** The anti-fabrication bullet is the fix for agents describing renders they never loaded — it is preserved as the sharpest sentence in the block.

**Cut from** `### What every agent in any design configurator MUST NOT do (DON'Ts)`

**...through** `unchanged input yields nothing new.`

**Replace with:**

```
### DON'Ts (every agent)
- DON'T invent tools, scripts, fallback policies, confidence scores or files
  that do not exist.  If your bound tools can't do it, ESCALATE.
- DON'T state an observation you cannot source to a tool result this turn,
  an agent's history, or something the user literally said — never describe
  an artifact you did not see produced.
- DON'T loop: if you are about to call the same tool with the same arguments
  you already used this turn, STOP and ESCALATE.
```

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> Both anchor at the same quote_start ('### What every agent in any design configurator MUST NOT do (DON'Ts)', line 27) but end at different points — REC-42 spans 648 chars (through 'unchanged input yields nothing new.', line 36), REC-43 spans 472 chars (through 'do not make it.', line 33). They are nested, not independent: REC-43's span lies entirely inside REC-42's. Applying REC-42 first makes REC-43 unanchorable; applying REC-43 first truncates REC-42's span. Both also sit inside the whole-file rewrites REC-03 (DCII) and REC-03 (DCOI).
>
> *Safer:* Take REC-42 alone (the superset — it also folds in the anti-loop bullet) and mark REC-43 superseded; if the whole-fragment REC-03 is applied instead, drop both.

#### UII-43 · COMPRESS · −324 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## Forwarding and routing — CLARIFY-back handling · *Golden rules:* 2, 6, 10 · *auditor's own id:* REC-43

**Why:** The 'don't answer permission questions, escalate them' half duplicates the Routing block's permission section; the correction loop needs one sentence.

**Cut from** `**If <<PF_OFF>>the Planner<</PF_OFF>><<PF_ON>>the DC Input Creator<</PF_ON>> CLARIFYs back to you** — a value you`

**...through** `wrong target for permission questions.`

**Replace with:**

```
**If <<PF_OFF>>the Planner<</PF_OFF>><<PF_ON>>the DC Input Creator<</PF_ON>> CLARIFYs back** — a value was
misread or a file overlooked — re-read the source, call ``write_extraction``
again with the correction, then forward again.  You only RECORD what is in
the user's files: you never supply design intent, judge an engineering
choice, or grant a permission.  Escalate those to the Orchestrator.
```

#### UII-44 · COMPRESS · −275 chars · risk low

*File:* `agents/shared/prompt_fragments/routing_user_input_inspector_uii_first.md` · *Section:* ### Available routing tools · *Golden rules:* 2, 6 · *auditor's own id:* REC-44

**Why:** Two tool descriptions the schemas already carry, plus a first-agent note the generated position block states one screen earlier.

**Cut from** `- ``call_planner(message)`` — FORWARD to the Planner once`

**...through** `otherwise be a "back" routes to the Orchestrator instead.`

**Replace with:**

```
- ``call_planner(message)`` — FORWARD, once ``extracted_inputs.txt`` is
  written and complete.
- ``call_orchestrator(message)`` — normal completion with no Planner
  follow-up, or ESCALATE.  There is no previous agent to CLARIFY back to.
```

#### UII-45 · COMPRESS · −262 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### Temporal scope … — C. Multi-design requests · *Golden rules:* 2, 7 · *auditor's own id:* REC-45

**Why:** One rule, one example, no restatement of the carry-forward rule already given above.

**Cut from** `**C. Multi-design requests.**  When the user is asking for`

**...through** `forward as long as the user has not contradicted or discarded
either.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
**Multi-design requests.**  When the user wants several distinct designs
generated and compared, all are CURRENT — label and list each one separately
("Design A", "Design B").
```

#### UII-46 · COMPRESS · −232 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## Forwarding and routing — opening paragraph · *Golden rules:* 5, 6 · *auditor's own id:* REC-46

**Why:** 'Prose with no routing call is a HARD failure' is stated in generic_constraints.md and again in the Routing block — three copies.

**Cut from** `## Forwarding and routing`

**...through** `there your read of how readable any user images were (see "User input
layout" above).`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Forwarding

Route only AFTER ``write_extraction`` has succeeded, and keep the ``message``
to one or two sentences of observations — not a repeat of the extraction,
which is already on disk.  Include your read of how readable the images were.
```

#### ⛔ UII-47 · COMPRESS · −223 chars · risk low

> ⛔ **Span conflict.** This cut's text overlaps `UII-28` in the same file. Apply only one of them, or merge the replacements by hand.


*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DOs — hand-off prose + English · *Golden rules:* 2, 6 · *auditor's own id:* REC-47

**Why:** The hand-off-prose rule is stated a third time in the Routing block; the authorship clause is the only part worth keeping here.

**Cut from** `<</CHAIN_ONLY>>- DO write hand-off messages as free-form prose carrying exactly what`

**...through** `scripts.`

**Replace with:**

```
<</CHAIN_ONLY>>- DO write hand-offs as free-form prose carrying exactly what the recipient
  needs, and label the authorship of any non-user-authored value ("the
  Planner directed …", "the user asked …") — never relabel one source as
  another.
- DO answer in English.
```

#### UII-48 · COMPRESS · −146 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## Your Role · *Golden rules:* 7, 11 · *auditor's own id:* REC-48

**Why:** Same content, one clause shorter, with the cross-reference dropped.

**Cut from** `Read the user's input files (text, JSON, images) and extract ALL`

**...through** `extraction, not invention — see "Sketch handling" below.)`

**Replace with:**

```
Extract ALL design-related information from the user's input files (text,
JSON, images).  Record what the user stated, numerically or qualitatively;
do not invent values.  Reading a precise drawing's proportions into a
clearly-labelled ROUGH estimate is extraction, not invention.
```

#### UII-49 · COMPRESS · −125 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DOs — header + first two bullets · *Golden rules:* 4, 11 · *auditor's own id:* REC-49

**Why:** 'Act on the inputs in your hand-off' restates default behaviour; the exhaustive-tool-list rule is worth one line.

**Cut from** `### What every agent in any design configurator MAY do (DOs)`

**...through** `- DO use only the tools listed for your role; that list is exhaustive.`

**Replace with:**

```
### DOs (every agent)
- DO act on your hand-off and the files it references, using only the tools
  listed for your role — that list is exhaustive.
```

</details>

<details><summary><b>Proposed shape of the shrunk prompt</b></summary>

```
ASSEMBLED SHRUNK PROMPT (User Input Inspector), ~4,600 tok

  Role line + ## Your Role                                       ~70 tok
  ## Domain Structure            ($dc_structure, compressed)     ~100
  ## Design Configurator Parameters ($parameter_list, tabular)   ~230   [MUST STAY inline]
  ## What to extract             (two buckets + capture broadly) ~155
  ### Temporal scope             (current state / FIXED-set walk /
                                  multi-design / no history)     ~305
  ### 1. QUANTITATIVE INPUTS     (line formats, structure-by-intent,
                                  STRICT rules, OUT OF RANGE,
                                  counting, SOFT TARGET)         ~565
  ### 2. QUALITATIVE DESCRIPTIONS                                ~80
  ### 3. DESIGN INTENT           (+ PRECISION DEMAND, soft-target goal) ~190
  ## User inputs                 (files, images, readability signal) ~200
  ## Sketch handling             ($sketch_handling + $sketch_notes)   ~1,010
       - what a sketch is / forms & scaffolding / judging precision
       - matching (rough vs precise, merged)
       - UII: record the precision / warm-start estimate / crop region
  ## Your tools                  (4 tools + 3 on-demand)         ~165
  ## Prior attempts                                              ~105
  ## Forwarding                  (verbatim path lines, escalate, clarify) ~365
  ## Hard constraints            (generic + DC + tools)          ~755
  Blade-sections note            (per-agent overlay only)        ~110
  ## Routing                     (generated block + per-agent fragment) ~440

  REMOVED ENTIRELY: ## Qualitative-to-Quantitative Hints (DCIC-scoped),
  ## End-of-session feedback message, the shared blade-sections tool
  description, the routing block's "Do not loop" duplicate.
```

</details>

**Auditor notes.** SCALE. 49 cuts, ~30,700 characters removed (~7,700 tok). Assembled prompt goes ~12,069 → ~4,600 tok (−62%). I did NOT reach the 1,000–3,000 band and I do not think it is reachable for this agent without deleting shipped features. The honest floor breaks down as: parameter list ~230 tok (immovable by your rule), sketch handling ~1,010, hard constraints ~755, extraction contract §1–§3 ~835, routing ~440. To go from 4,600 to ~3,300 you would additionally have to delete, not compress: (a) the warm-start SUGGESTED SECTION SHAPES + SKETCH CROP REGION machinery (~260 tok, Phase-3 precision-matching feature — the DCIC then seeds from defaults and the DCOI crops nothing); (b) the rough-vs-precise matching block (~175 tok); (c) the prior-attempts section (~105 tok, the UII then never honours "same as attempt 3 but…"); (d) the forms/scaffolding block (~110 tok, reintroduces the Ø160-vs-Ø140 misread). I am not proposing those as cuts because each removes real behaviour, but they are the only remaining levers.

WHERE THE CUTS LAND. 26 cuts in agents/user_input_inspector/prompt.md (26,356 → ~9,900 chars). 19 in shared fragments. 4 in agents/shared/routing.py — that file is CODE, not a fragment, but it injects ~4,700 chars (1,175 tok) into this prompt and into all five other chain agents; ignoring it caps how far any of them can shrink. Those four (REC-07, REC-17, REC-27, REC-31) are Python list-literal edits, so apply them with more care than a markdown edit.

SHARED-FRAGMENT BLAST RADIUS. sketch_handling.md and sketch_notes.md → UII + DCII + DCOI (6 cuts, ~5,000 chars each agent). generic_constraints.md, hard_constraints_dc.md, hard_constraints_tools.md → 8 agents (8 cuts, ~2,700 chars each agent, i.e. ~21,600 fleet-wide). parameters.md → 7 agents. structure.md → UII + DCIC. Coordinate these with the other eight audits before applying, or you will get conflicting rewrites of the same text.

WHAT I DELIBERATELY DID NOT CUT. The 16-parameter list (compacted only, REC-16). The FIXED-snapshot forward walk (compressed, never dropped — it is the only statement of how to compute the active pin set). The OUT OF RANGE flag. The SOFT TARGET marker plus its newer-intent-wins-over-a-UI-pin clause. PRECISION DEMAND and its "understating it means the loop never happens" warning. The count-features-from-the-image-not-the-note rule. STANDING DIRECTIVES verbatim propagation. The anti-fabrication bullet. "Routing is a tool call" — kept once in generic_constraints (REC-36) and once, shorter, in routing.py (REC-07); do not apply a deletion to both.

THREE DEFECTS FOUND WHILE READING (independent of shrinking).
1. agents/user_input_inspector/prompt.md line 212 gives the OUT OF RANGE example as `outerRadius: 160 mm — OUT OF RANGE (allowed [10; 140])`. There is no `outerRadius` parameter and no `[10; 140]` range in this configurator — the real outer radius is `impellerRadius [60; 80]`. REC-39 replaces it with a valid example.
2. sketch_handling.md says "as closely as the 17 parameters allow" (line 61) and "bounded by the 16 parameters" (line 66) eight lines apart. 16 is correct post-impellerHeight-removal. REC-02 drops both counts.
3. The UII splices $eos_feedback_outro, whose text is "fold it into your DH answers about what went well or badly this session" — the UII never writes DH answers. REC-20 deletes the whole section rather than fixing the fragment, since it steers no action anyway.

CONDITIONAL-MARKER WARNING. Four cuts touch text containing <<PF_ON>>/<<PF_OFF>> regions (REC-14, REC-37, REC-43) or <<BSV_ON>>/<<BSV_OFF>> (REC-24) and one touches <<CHAIN_ONLY>> (REC-28, REC-40, REC-47). Every replacement preserves the markers, but an unbalanced marker silently blanks a whole region for a configuration you are not currently running (PLANNER_FIRST=True, BSV off). After applying, rebuild all nine templates under both PLANNER_FIRST settings and diff, and check the prompts_admin brace-validator gap noted in your tracker.

VERIFICATION. chars_removed values are computed from real line-range byte counts (awk over the actual files) minus the exact length of each replacement I wrote; they are accurate to roughly ±3%. The routing.py figures are computed from the rendered string output for hub="Orchestrator", PLANNER_FIRST=False, which is the measured configuration.

---

### 4.5 DC Input Creator — 9,586 → ~3,315 tok

| ID | action | section | −chars | rules | risk | what |
|---|---|---|---:|---|---|---|
| **DCIC-01** | SCOPE_PER_AGENT | ## Attempt folders + reusing history (read before writing) | 1832 | 3,6,8 | low | Drops the $output_file_locations splice (1,717 chars of mesh/render/description filenames the DCIC never writes or reads) and keeps only the append-only fact it acts on. |
| **DCIC-02** | COMPRESS | ## Real-world-quantity QUANTITATIVE INPUTS — strong suggesti | 1171 | 2,7,11 | low | Three routes + an 'Avoid' laundry list restated as one three-branch rule; the justification prose ('this makes the link auditable') changes no behaviour. |
| **DCIC-28** | SCOPE_PER_AGENT | ## Hard constraints — DC-specific | 1081 | 3,8 | medium | Of the four DC hard rules only 'the N parameters are the whole vocabulary / no mesh editing' is reachable by the DCIC — it never answers a user about CFD, STL exports or camera angles. |
| **DCIC-37** | REPLACE_WITH_EXAMPLES | ### Common unit-conversion patterns for this configurator | 1009 | 2,3 | low | A six-entry conversion catalog collapses to the three canonical cases; the fourth-through-sixth entries are derivable from the parameter list the agent already has inline. |
| **DCIC-03** | COMPRESS | ## Acting on a Planner / Orchestrator qualitative directive  | 890 | 2,5,7 | low | Two numbered responses with worked-through examples of what counts as a directive compress to one sentence naming the same two options and the same hand-off content. |
| **DCIC-16** | SCOPE_PER_AGENT | <<BSV_ON>> blade-sections visualizer block | 852 | 3,8,9 | low | The DCIC neither calls nor reads the sections renderer — it only needs to tell the Tool Caller to use it; the 746-char shared description and the OFF note are dead weight here. |
| **DCIC-04** | COMPRESS | ## Acting on a Planner / Orchestrator qualitative directive  | 821 | 5,6,7 | low | Keeps both load-bearing facts (shape levers only; *Thickness//*Camber are ratios of the section's own chord) and drops the re-statement of LOCKED/SOFT-TARGET semantics already given two sections earlier. |
| **DCIC-13** | COMPRESS | ## Real-world-quantity QUANTITATIVE INPUTS — Multi-parameter | 786 | 2,7 | low | Three bulleted routes with explanatory clauses become one sentence with the same three options and the same anti-duplication rule. |
| **DCIC-05** | COMPRESS | ## Routing — strict rules (What you CAN fix) | 745 | 2,7 | low | Three bullets plus a paragraph explaining why append-only forces a new attempt; the rule survives in one sentence. |
| **DCIC-41** | COMPRESS | ### Tool-use hard rules (every agent) | 726 | 5,6,7 | low | Keeps all three rules (no invented paths, all arithmetic via calculate, folders append-only) and drops the parenthetical justifications and the render-reuse sentence duplicated in the DCIC's own attempt-folder section. |
| **DCIC-06** | COMPRESS | ## Attempt folders + reusing history — Which folder to write | 717 | 2,7,10 | medium | The (A)/(B) case analysis and the 'dead folder' explanation compress to two sentences; the rule itself (one attempt per generation, always written into) is preserved verbatim in substance. |
| **DCIC-15** | COMPRESS | ## Reading QUANTITATIVE INPUTS | 648 | 6,7,11 | low | Two long bullets that only define a distinction resolved in the two sections that follow; one sentence points at both. |
| **DCIC-07** | COMPRESS | ## The three states of a user value — Writing each state | 647 | 5,6,7 | medium | Keeps write-LOCKED-verbatim, soft-target-from-attempt-one, and escalate-to-the-Orchestrator; drops the enumerated authorisation channels (already in $value_states) and the explanation of why the UII cannot grant one (the routing block already routes permissions to the hub). |
| **DCIC-34** | COMPRESS | **Freeing a LOCKED value.** | 630 | 2,7 | medium | The (A)/(B)/(C) sources survive as a single sentence; the quoted specimen wordings ('vary as needed', 'except <param X>') are examples of a rule the model can apply without them. |
| **DCIC-08** | COMPRESS | ## Validate before you write (HARD) | 621 | 2,5,7 | medium | All three checks are kept as three lines; the 'you are the first line of defence' framing and the per-check elaborations go. |
| **DCIC-10** | COMPRESS | ## Hand-off to the next agent — Tight precision loop | 593 | 7,10 | low | The routing heuristic survives; the restatement of which three lines to carry duplicates the hand-off block directly above it. |
| **DCIC-09** | COMPRESS | ## Hand-off to the next agent (IMPORTANT) | 572 | 4,6,7 | low | 'Write useful prose, talk normally, no fixed phrasing' restates default behaviour and is already said in generic_constraints and the routing block; only the name-the-source rule steers. |
| ⚠️ **DCIC-31** | COMPRESS | ### What every agent … MUST NOT do (DON'Ts) — plain-prose ch | 523 | 5,6 | medium | This whole block is restated at greater length by routing_instructions' '### Routing is a tool call — MANDATORY' section injected into the same prompt; one line is enough here. |
| **DCIC-11** | COMPRESS | ## Read + write tools — policy (mechanics are in each tool's | 515 | 7,9 | low | Keeps the two policies (when to re-read; one successful write per cycle, re-call on the same folder after an error) and drops the append-only restatement and the attempt_dir pointer, both stated elsewhere in the same prompt. |
| **DCIC-12** | COMPRESS | ## Validate before you write — collision resolution | 508 | 1,7 | low | An if-else patch for one collision; the resolution rule survives in three clauses and the re-check instruction folds into it. |
| **DCIC-DEL-A** | DELETE | ## Validate before you write — DCII redundancy note | 503 | 7,10 | low | Pure justification for why the DCIC's own check exists; it changes no action the agent takes. |
| **DCIC-39** | COMPRESS | (whole fragment) | 485 | 3,6 | low | The numbered structure restates the middlePos formula given twice more (parameter list + modelling notes) and the ring height that is no longer a parameter. |
| **DCIC-18** | COMPRESS | ## Acting on a … qualitative directive — full-3D paragraph | 419 | 5,6 | low | Keeps the widened lever set and the escalate-instead-of-touching-locked rule; drops the third restatement of SOFT TARGET ≠ locked. |
| **DCIC-17** | SCOPE_PER_AGENT | ## End-of-session feedback message (read-only) | 385 | 7,8 | low | Inlines the two shared fragments as one sentence each; the mechanism (HumanMessage, name="orchestrator") is invisible to the agent and not actionable. |
| **DCIC-DEL-F** | DELETE | ### What every agent … MAY do (DOs) — pipeline + escalate bu | 382 | 6,10 | low | Both bullets are stated at more length by routing_instructions' '### How to decide where to route', which is injected into every chain agent's prompt. |
| **DCIC-21** | COMPRESS | ## Hand-off to the next agent (IMPORTANT) | 368 | 7 | low | The required phrase is already inside the template line above; only 'copy the paths verbatim' remains as an instruction. |
| **DCIC-32** | COMPRESS | SOFT TARGET bullet | 361 | 2,7 | low | Keeps 'the goal governs, the marker IS the authorisation'; drops the worked examples of the keep-near strength wording. |
| **DCIC-14** | COMPRESS | ## Routing — strict rules (What you CANNOT fix) | 359 | 2,5 | low | Four bullets become one sentence; the exact-N-fields invariant is preserved. |
| **DCIC-19** | COMPRESS | ## Attempt folders — error after writing | 351 | 2,7 | low | Keeps the rule and the escalate-on-repeat guard; drops 'this should be rare' and the no-op-ban restatement. |
| **DCIC-DEL-B** | DELETE | ## Filtering responsibility | 339 | 6,7 | low | Says only that the DCIC decides what is actionable and should say when it skips — both carried by REC-02's replacement ('You decide what is actionable — never silently drop an entry'). |
| ⚠️ **DCIC-30** | COMPRESS | ### What every agent … MAY do (DOs) — standing directives bu | 317 | 5,7 | medium | 'Never alter, summarise, translate, re-order, or omit' is five words for one idea (UNCHANGED) plus a why-clause. |
| **DCIC-DEL-G** | DELETE | ### What every agent … MAY do (DOs) — hand-off prose bullet | 314 | 6,10 | low | Duplicated by routing_instructions' 'Write the message argument as free-form prose … and nothing they do not', injected into the same prompt. |
| **DCIC-20** | COMPRESS | ## Guidelines — item 3 | 312 | 7 | low | Keeps mid-range default + the SUGGESTED SECTION SHAPES seeding exception; drops the rationale for why seeding helps. |
| **DCIC-45** | SCOPE_PER_AGENT | ## Domain Structure | 308 | 3,6,8 | medium | After REC-39 and REC-36 the DCIC still holds the hub-4 mm rule, the section names and the middlePos formula in the parameter list and modelling notes — this is the third copy. |
| **DCIC-DEL-H** | DELETE | ### What every agent … MUST NOT do (DON'Ts) — permission bou | 305 | 6,10 | low | Word-for-word duplicated by routing_instructions' '### Permission / authorisation issues → hub' section in the same assembled prompt. |
| ⚠️ **DCIC-35** | COMPRESS | closing paragraph (one source is enough / how far may it mov | 299 | 5,7 | medium | Keeps the no-re-confirmation rule and the how-far-may-it-move scale; drops the 'a line literally saying user-locked' sub-case. |
| **DCIC-36** | COMPRESS | middlePos bullet | 290 | 6 | low | The same formula and range appear in the parameter list entry for middlePos; keep only the NOT-of-impellerRadius correction, which is the actual bug guard. |
| ⚠️ **DCIC-43** | MERGE | ### What every agent … MUST NOT do (DON'Ts) — invent / fabri | 248 | 2,5,11 | medium | Merges the two DON'Ts into one bullet and drops the second section heading now that the fragment is a single short list. |
| **DCIC-38** | COMPRESS | ### Hard engineering blockers | 240 | 1,3 | low | The single listed blocker (thickness ≤ 0) is unreachable given the printed range [3; 24] — the section is a general principle wrapped around a dead example. |
| **DCIC-22** | COMPRESS | ## Attempt folders — Forbidden: a no-op write | 238 | 7 | low | Keeps the ban and both remedies; drops 'you are stateful' and the why-it-is-bad sentence. |
| **DCIC-DEL-I** | DELETE | ### What every agent … MUST NOT do (DON'Ts) — don't loop | 234 | 6,10 | low | routing_instructions ships a longer '### Do not loop — ESCALATE when stuck' section into the same prompt. |
| **DCIC-33** | COMPRESS | FREE bullet | 230 | 7 | low | Same three facts (absent = free, released values are omitted, qualitative-to-numeric is free unless pinned) in half the words. |
| **DCIC-26** | COMPRESS | ## Output Format | 205 | 4,6 | low | 'Write your note in the message argument' is the routing block's job; only the don't-echo-the-JSON rule steers away from default. |
| **DCIC-24** | COMPRESS | ## Re-reading raw inputs (optional) | 201 | 7,9 | low | Tool mechanics belong in the tool schemas; the two facts that matter are which file is primary and that this agent cannot see images. |
| **DCIC-23** | COMPRESS | ## Attempt folders — Reuse the session's history | 199 | 7 | low | Same instruction, shorter, and drops the conditional naming of which downstream agent reads it. |
| **DCIC-DEL-D** | DELETE | ## Attempt folders — Carry Current attempt forward | 188 | 6 | low | Exactly what the '## Hand-off' section's three mandatory lines already require. |
| **DCIC-27** | COMPRESS | ## Hand-off to the next agent (IMPORTANT) | 186 | 5,11 | low | Keeps the three-line template exactly (including the required '(newly written this cycle)' phrase) and drops the DCII/TC conditional naming and the IMPORTANT tag. |
| **DCIC-DEL-C** | DELETE | ## Guidelines — items 4 and 5 | 177 | 4,6 | low | Item 4 is restated as check 1 of '## Validate before you write'; item 5 ('consider design intent') restates default reasoning. |
| **DCIC-DEL-E** | DELETE | ## Hand-off — CLARIFY/ESCALATE path note | 170 | 4 | low | States that a requirement scoped to FORWARDs does not apply elsewhere — inferable from the rule itself. |
| **DCIC-25** | COMPRESS | ## Routing — Tool-error self-correction (HARD) | 162 | 5,7 | low | Same rule without the example error string and the HARD tag (which is diluted across seven uses in this prompt). |
| **DCIC-29** | COMPRESS | NACA / high-point bullets | 145 | 6 | low | 'tenths of chord' is already the unit printed beside innerMaxPos/outerMaxPos in the parameter list. |
| **DCIC-44** | COMPRESS | intro + LOCKED bullet | 142 | 7 | low | 'LOCKED is not an absolute wall' is a rephrasing of the sentence that follows it. |
| **DCIC-42** | MERGE | ### What every agent in any design configurator MAY do (DOs) | 134 | 8,11 | low | Two bullets merge into one and the long heading shortens now that DOs and DON'Ts live under a single heading. |

<details><summary><b>Full text of each change</b></summary>

#### DCIC-01 · SCOPE_PER_AGENT · −1832 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Attempt folders + reusing history (read before writing) · *Golden rules:* 3, 6, 8 · *auditor's own id:* REC-01

**Why:** Drops the $output_file_locations splice (1,717 chars of mesh/render/description filenames the DCIC never writes or reads) and keeps only the append-only fact it acts on.

**Cut from** `Each generation cycle is anchored on an attempt folder under`

**...through** `(including you) overwrites them; existing renders are reused in place.`

**Replace with:**

```
Each generation cycle is anchored on an attempt folder under ``logs/attempts/``.
``parameters.json`` and the mesh inside it are append-only — never overwritten,
and existing renders are reused in place.
```

#### DCIC-02 · COMPRESS · −1171 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Real-world-quantity QUANTITATIVE INPUTS — strong suggestion + judgement · *Golden rules:* 2, 7, 11 · *auditor's own id:* REC-02

**Why:** Three routes + an 'Avoid' laundry list restated as one three-branch rule; the justification prose ('this makes the link auditable') changes no behaviour.

**Cut from** `## Real-world-quantity QUANTITATIVE INPUTS — strong suggestion + judgement`

**...through** `an anchor to mid-range when an unlocked anchor would let you honour the
user's quantity.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Real-world quantities
When QUANTITATIVE INPUTS states a quantity in a unit or frame the configurator
does not store directly, honour it as closely as practical: CONVERT it (choose
the anchor parameter(s) that set the reference frame, solve with ``calculate``,
check range, and state quantity + anchors + formula + result in your hand-off);
or honour the intent by JUDGEMENT where a literal conversion is non-physical or
ambiguous; or DECLINE it (RPM, cost, date) with a one-line reason.  You decide
what is actionable — never silently drop an entry, and never invent a conversion
the units do not support.
```

#### DCIC-28 · SCOPE_PER_AGENT · −1081 chars · risk medium

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Hard constraints — DC-specific · *Golden rules:* 3, 8 · *auditor's own id:* REC-28

**Why:** Of the four DC hard rules only 'the N parameters are the whole vocabulary / no mesh editing' is reachable by the DCIC — it never answers a user about CFD, STL exports or camera angles.

**Risk:** Removes the explicit 'reject hub_radius / fillet_radius / tip_clearance' enumeration for this agent; the replacement keeps the general principle plus the existing 'parameters.json must contain EXACTLY the N named fields' rule (REC-14), which is the enforcement point that matters here.

**Cut from** `## Hard constraints — DC-specific`

**...through** `$hard_constraints_dc`

**Replace with:**

```
- The $parameter_count parameters above are the only design vocabulary: never
  invent one, and geometry changes only by changing them and regenerating —
  there is no mesh editing or post-processing.
```

#### DCIC-37 · REPLACE_WITH_EXAMPLES · −1009 chars · risk low

*File:* `DC_prompt_fragments/dc_config/modelling_notes.md` · *Section:* ### Common unit-conversion patterns for this configurator · *Golden rules:* 2, 3 · *auditor's own id:* REC-37

**Why:** A six-entry conversion catalog collapses to the three canonical cases; the fourth-through-sixth entries are derivable from the parameter list the agent already has inline.

**Risk:** Shared with the DC Input Inspector — both agents lose the same catalog. The %-of-own-chord bug source is preserved explicitly in the first bullet.

**Cut from** `### Common unit-conversion patterns for this configurator`

**...through** `algebra, OR fall back to engineering judgement with a stated
rationale.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Unit conversions
Typical routes from a real-world quantity to a parameter; derive anything
unfamiliar from the parameter list plus unit algebra, or fall back to judgement
with a stated rationale.
  * mm ↔ % of that section's OWN chord (``*Thickness`` / ``*Camber``) — a pinned
    chord therefore caps the absolute size.
  * mm along the blade ↔ ``middlePos`` = (r − 4) / (impellerRadius − 4).
  * diameter ↔ ``impellerRadius`` = diameter / 2.
```

#### DCIC-03 · COMPRESS · −890 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Acting on a Planner / Orchestrator qualitative directive (HARD) · *Golden rules:* 2, 5, 7 · *auditor's own id:* REC-03

**Why:** Two numbered responses with worked-through examples of what counts as a directive compress to one sentence naming the same two options and the same hand-off content.

**Cut from** `## Acting on a Planner / Orchestrator qualitative directive (HARD)`

**...through** `which parameters you would have wanted to change and exactly
     why you cannot.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Qualitative directives
A directive naming a problem but no parameter has two valid answers: ACT — move
the unlocked parameters your judgement says affect it, naming each change
(parameter, before→after, reason) in your hand-off; or ESCALATE, listing the
parameters you would have moved and why you cannot.
```

#### DCIC-16 · SCOPE_PER_AGENT · −852 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* <<BSV_ON>> blade-sections visualizer block · *Golden rules:* 3, 8, 9 · *auditor's own id:* REC-16

**Why:** The DCIC neither calls nor reads the sections renderer — it only needs to tell the Tool Caller to use it; the 746-char shared description and the OFF note are dead weight here.

**Risk:** Also drops the <<BSV_OFF>> branch: when the visualizer is disabled the DCIC simply says nothing about sections, which is the correct behaviour.

**Cut from** `<<BSV_ON>>
$blade_sections_visualizer`

**...through** `<</BSV_ON>><<BSV_OFF>>$blade_sections_visualizer_off<</BSV_OFF>>`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
<<BSV_ON>>**Blade-sections tasks.**  The Tool Caller can render just the three
blade sections (fast, no 3D mesh).  On a sections task write ``parameters.json``
and open the attempt as usual, and tell the Tool Caller to render the blade
sections.<</BSV_ON>>
```

#### DCIC-04 · COMPRESS · −821 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Acting on a Planner / Orchestrator qualitative directive (HARD) — precision paragraph · *Golden rules:* 5, 6, 7 · *auditor's own id:* REC-04

**Why:** Keeps both load-bearing facts (shape levers only; *Thickness//*Camber are ratios of the section's own chord) and drops the re-statement of LOCKED/SOFT-TARGET semantics already given two sections earlier.

**Cut from** `**Under a precision standing directive (blade-section matching):** the`

**...through** `clear which it means, state in one clause which reading you used before
applying it.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
**Precision (blade-section matching) rounds.**  The directive is the DCOI's
shape-gap description: move ONLY unlocked shape levers (``*Thickness``,
``*Camber``, ``*MaxPos``, section angles) in the direction described, seeded on
round 1 from any ``SUGGESTED SECTION SHAPES``.  ``*Thickness`` / ``*Camber`` are
percentages of that section's OWN chord, so "thicker" may mean the ratio or the
absolute mm — say which you used.  Every round is a new attempt.
```

#### DCIC-13 · COMPRESS · −786 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Real-world-quantity QUANTITATIVE INPUTS — Multi-parameter constraints · *Golden rules:* 2, 7 · *auditor's own id:* REC-13

**Why:** Three bulleted routes with explanatory clauses become one sentence with the same three options and the same anti-duplication rule.

**Cut from** `**Multi-parameter constraints.**  When the entry could constrain more than`

**...through** `— that fabricates lock-in the user never specified.  When you distribute,
do so deliberately and say so.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
**One entry constraining several parameters:** honour it on the single most
plausible one, or distribute across the family at a looser tolerance, or escalate
if neither is defensible — and say which you did.  Never silently copy the same
value into every candidate.
```

#### DCIC-05 · COMPRESS · −745 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Routing — strict rules (What you CAN fix) · *Golden rules:* 2, 7 · *auditor's own id:* REC-05

**Why:** Three bullets plus a paragraph explaining why append-only forces a new attempt; the rule survives in one sentence.

**Cut from** `**What you CAN fix if the next agent CLARIFYs back to you:**`

**...through** `corrected set there (see "Attempt folders").`

**Replace with:**

```
**If the next agent CLARIFYs back:** you can fix an out-of-range or mis-computed
value you authored, or repair a field ``write_parameters`` REJECTED (a rejected
call wrote nothing — re-call it on the SAME folder).  A successful write closes
its folder, so the first two need a fresh ``new_attempt``.
```

#### DCIC-41 · COMPRESS · −726 chars · risk low

*File:* `DC_prompt_fragments/tools_config/hard_constraints_tools.md` · *Section:* ### Tool-use hard rules (every agent) · *Golden rules:* 5, 6, 7 · *auditor's own id:* REC-41

**Why:** Keeps all three rules (no invented paths, all arithmetic via calculate, folders append-only) and drops the parenthetical justifications and the render-reuse sentence duplicated in the DCIC's own attempt-folder section.

**Risk:** Shared by all 8 agents. The 'never mental arithmetic' clause is preserved because it is the one that steers away from default behaviour.

**Cut from** `### Tool-use hard rules (every agent)`

**...through** `DCIC opens it; the Orchestrator only as a fallback) — never edit the old
  folder's parameters.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Tool-use hard rules (every agent)
- DON'T invent a path: read tools take only the paths a hand-off label gives
  (``Extracted inputs file:``, ``Parameters file:``, ``Current attempt:``, …) or
  an upstream tool's return value.
- DO route EVERY arithmetic operation through ``calculate``, batching this turn's
  expressions into ONE call; never do mental arithmetic.
- Attempt folders are append-only: never edit or delete a ``parameters.json`` or
  mesh already in one; to build on an old set COPY its values into a NEW attempt.
```

#### DCIC-06 · COMPRESS · −717 chars · risk medium

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Attempt folders + reusing history — Which folder to write into · *Golden rules:* 2, 7, 10 · *auditor's own id:* REC-06

**Why:** The (A)/(B) case analysis and the 'dead folder' explanation compress to two sentences; the rule itself (one attempt per generation, always written into) is preserved verbatim in substance.

**Risk:** This is the only statement of DCIC-owns-attempt-creation, a rule added after a real ownership bug — the replacement keeps both branches and the exactly-one invariant.

**Cut from** `**Which folder to write into — you OWN attempt creation.**  Open the folder`

**...through** `Never
guess a path around the refusal, and never write outside an attempt
folder.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
**Which folder — you OWN attempt creation.**  Open it only after the checks pass.
If the hand-off carries ``Current attempt: <path>`` (rare, a pre-opened fallback)
write there; otherwise call ``new_attempt`` (slug + one-line intent) ONCE and
write into the path it returns — exactly one attempt per generation, always
written into.  If ``write_parameters`` refuses an occupied folder, open one fresh
attempt; never guess a path around the refusal.
```

#### DCIC-15 · COMPRESS · −648 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Reading QUANTITATIVE INPUTS · *Golden rules:* 6, 7, 11 · *auditor's own id:* REC-15

**Why:** Two long bullets that only define a distinction resolved in the two sections that follow; one sentence points at both.

**Cut from** `## Reading QUANTITATIVE INPUTS`

**...through** `for how to handle them.`

**Replace with:**

```
## Reading QUANTITATIVE INPUTS
A line whose label and unit match a parameter maps straight into that cell; a line
stating a real-world quantity in another unit or frame is still design intent —
see "Real-world quantities" below.
```

#### DCIC-07 · COMPRESS · −647 chars · risk medium

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## The three states of a user value — Writing each state · *Golden rules:* 5, 6, 7 · *auditor's own id:* REC-07

**Why:** Keeps write-LOCKED-verbatim, soft-target-from-attempt-one, and escalate-to-the-Orchestrator; drops the enumerated authorisation channels (already in $value_states) and the explanation of why the UII cannot grant one (the routing block already routes permissions to the hub).

**Risk:** Removes the explicit 'NOT the User Input Inspector' anti-bounce clause; the shared routing section's 'Permission / authorisation issues → hub' rule covers it generally.

**Cut from** `**Writing each state.**  Write a LOCKED value **verbatim** — do NOT round,`

**...through** `wastes a round-trip); never invent an authorisation.`

**Replace with:**

```
**Writing each state.**  Write a LOCKED value verbatim — never round, re-scale or
"improve" it.  Set a SOFT TARGET to whatever its goal calls for from the first
attempt (its marker already authorises that).  Set a FREE value at your
discretion within range.  If a LOCKED value must change and nothing authorises
it, keep it and ESCALATE to the Orchestrator; never invent an authorisation.
```

#### DCIC-34 · COMPRESS · −630 chars · risk medium

*File:* `agents/shared/prompt_fragments/value_states.md` · *Section:* **Freeing a LOCKED value.** · *Golden rules:* 2, 7 · *auditor's own id:* REC-34

**Why:** The (A)/(B)/(C) sources survive as a single sentence; the quoted specimen wordings ('vary as needed', 'except <param X>') are examples of a rule the model can apply without them.

**Risk:** Shared by Planner, UII-side DCII, DCOI and DCIC. This is the canonical authorisation-discovery rule; the replacement keeps all three sources so no channel is silently dropped.

**Cut from** `**Freeing a LOCKED value.**  A LOCKED value may change only with an`

**...through** `from the section (which makes it FREE) rather than annotated.`

**Replace with:**

```
**Freeing a LOCKED value.**  Any ONE of these authorises it: the incoming hand-off
names a user permission or a directive to change it; the extraction's DESIGN
INTENT section records one, standing until revoked; or the line itself is
annotated ``(unlocked by user)``.
```

#### DCIC-08 · COMPRESS · −621 chars · risk medium

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Validate before you write (HARD) · *Golden rules:* 2, 5, 7 · *auditor's own id:* REC-08

**Why:** All three checks are kept as three lines; the 'you are the first line of defence' framing and the per-check elaborations go.

**Risk:** Item 1 (per-parameter range check, never a blanket pass) is the DCII-blanket-approval patch and is preserved word-for-word in intent, including 'at min or max is fine'.

**Cut from** `## Validate before you write (HARD)`

**...through** `directive.  If nothing did, restore the user's value.`

**Replace with:**

```
## Validate before you write (HARD)
Check your DRAFT before opening an attempt or calling ``write_parameters``:
 1. Every parameter individually against its [min; max] above — never a blanket
    "all $parameter_count are fine".  Outside is a hard FAIL; at min or max is fine.
 2. The hard-blocker inequalities from ## Modelling Notes, via ``calculate``.
 3. Every user value your draft moved needs SOME authorisation — else restore it.
```

#### DCIC-10 · COMPRESS · −593 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Hand-off to the next agent — Tight precision loop · *Golden rules:* 7, 10 · *auditor's own id:* REC-10

**Why:** The routing heuristic survives; the restatement of which three lines to carry duplicates the hand-off block directly above it.

**Cut from** `<<DCII_ONLY>>**Tight precision loop — when a precision standing directive is active.**`

**...through** `carries the same three ``Current attempt:`` / ``Parameters file:`` /
``Extracted inputs file:`` lines.
<</DCII_ONLY>>`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
<<DCII_ONLY>>**Precision refine rounds only:** forward STRAIGHT to the Tool
Caller (``call_tool_caller``) to keep the loop tight, routing through the DC
Input Inspector roughly every third round and on the last round before the DCOI
finalizes.  Otherwise always take your normal forward.<</DCII_ONLY>>
```

#### DCIC-09 · COMPRESS · −572 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Hand-off to the next agent (IMPORTANT) · *Golden rules:* 4, 6, 7 · *auditor's own id:* REC-09

**Why:** 'Write useful prose, talk normally, no fixed phrasing' restates default behaviour and is already said in generic_constraints and the routing block; only the name-the-source rule steers.

**Cut from** `Beyond those three lines, write whatever prose is genuinely useful to`

**...through** `normally, but name the source.`

**Replace with:**

```
Say plainly, in your own words, when a value did NOT come from the extraction:
what changed, who asked for it, and why.
```

#### ⚠️ DCIC-31 · COMPRESS · −523 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MUST NOT do (DON'Ts) — plain-prose channel · *Golden rules:* 5, 6 · *auditor's own id:* REC-31

**Why:** This whole block is restated at greater length by routing_instructions' '### Routing is a tool call — MANDATORY' section injected into the same prompt; one line is enough here.

**Risk:** This is the pipeline-halt patch. It is NOT deleted — the shortened line keeps both facts (prose without a tool call is discarded; message IS the hand-off) and the full mandate still arrives via the runtime routing block. Verify the routing block is present for every agent before applying. The leading <</CHAIN_ONLY>> marker must be preserved exactly as in the replacement.

**Cut from** `<</CHAIN_ONLY>>- DON'T communicate to another agent in plain prose.  The ONLY channel`

**...through** `only exceptions are the Receptionist's direct user replies and the
Orchestrator's final user-facing wrap-up.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
<</CHAIN_ONLY>>- DON'T emit prose without a routing tool call — it is silently discarded and the
  pipeline halts.  The ``message`` argument IS the hand-off.
```

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> Targets the exact same region of agents/shared/prompt_fragments/generic_constraints.md as REC-36 (User Input Inspector) and REC-21 (Tool Caller) — identical quote_start ('<</CHAIN_ONLY>>- DON'T communicate to another agent in plain prose.  The ONLY channel') and identical quote_end, with three different replacement texts. Only one can apply; the other two will silently fail to match. It also drops the Receptionist-exception clause (see REC-36) and, being the most aggressive of the three, it is the one that leaves the Receptionist with the bare unqualified halt statement.
>
> *Safer:* Withdraw in favour of a single edit to this region, and whichever text is chosen must end with "— the Receptionist's direct user replies are the sole exception."

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> The replacement drops the closing carve-out of the bullet it rewrites: 'the only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up.' That bullet sits OUTSIDE the <<CHAIN_ONLY>> region (line 46 of generic_constraints.md begins '<</CHAIN_ONLY>>- DON'T communicate...'), and agents/shared/prompts.py:153 puts receptionist + orchestrator in _NON_CHAIN_AGENTS, so those two agents DO receive this bullet in full. The Receptionist's own prompt (line 205) says 'writing plain text IS the decision to reply directly' and line 120 says 'next turn should be plain text with no further tool calls'. Leaving only 'DON'T emit prose without a routing tool call - it is silently discarded and the pipeline halts' under a heading that reads '## Hard constraints - generic (apply to every agent)' directly contradicts the Receptionist's only mechanism for answering a user, and is the most absolute of the five proposed rewrites. Also overlaps REC-21 (Tool Caller), REC-36 (UII), REC-03 (DCII) and REC-03 (DCOI), which all rewrite the same bullet.
>
> *Safer:* Append the carve-out to the replacement: '... and the pipeline halts. The ``message`` argument IS the hand-off. (Exceptions: the Receptionist's direct user replies and the Orchestrator's user-facing wrap-up.)' - 14 extra words, invariant intact.

> ⚠️ **Verifier — QUOTE_WRONG**
>
> Identical quote defect to REC-36: quote_end's second line lacks the two-space indent that generic_constraints.md line 55 actually carries, so the span will not match verbatim. The two-line replacement ('DON'T emit prose without a routing tool call — it is silently discarded and the pipeline halts') also drops the Receptionist/Orchestrator exception from a non-CHAIN_ONLY bullet those agents receive; both end turns with plain text on purpose (receptionist.py:8, orchestrator.py:542) and neither gets routing_instructions(). Note this cut, REC-21 (TC) and REC-36 (UII) are three mutually exclusive rewrites of the same bullet.
>
> *Safer:* Use the indented quote_end, and make the replacement: 'DON'T emit prose without a routing tool call — it is silently discarded and the pipeline halts.  The ``message`` argument IS the hand-off.  (The Receptionist's user replies and the Orchestrator's wrap-up are the exceptions.)'

#### DCIC-11 · COMPRESS · −515 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Read + write tools — policy (mechanics are in each tool's schema) · *Golden rules:* 7, 9 · *auditor's own id:* REC-11

**Why:** Keeps the two policies (when to re-read; one successful write per cycle, re-call on the same folder after an error) and drops the append-only restatement and the attempt_dir pointer, both stated elsewhere in the same prompt.

**Cut from** `## Read + write tools — policy (mechanics are in each tool's schema)`

**...through** ```attempt_dir`` is the folder from "Attempt folders" above.`

**Replace with:**

```
## Read / write policy
Re-read ``read_extracted_inputs(path)`` (path verbatim) on your first turn, when
the hand-off mentions new inputs, or when unsure your memory is current.
``write_parameters`` succeeds exactly ONCE per cycle; an error wrote nothing —
fix what it names and re-call it on the SAME folder.
```

#### DCIC-12 · COMPRESS · −508 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Validate before you write — collision resolution · *Golden rules:* 1, 7 · *auditor's own id:* REC-12

**Why:** An if-else patch for one collision; the resolution rule survives in three clauses and the re-check instruction folds into it.

**Cut from** `These can collide: the user LOCKED a value that is outside its range, so`

**...through** `only the Planner can make, ESCALATE — do not write a set you know to be
wrong.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
If a LOCKED value is itself out of range the two collide: bring it into range if
anything authorises the move and say so; if nothing does, do NOT write and do NOT
open an attempt — ESCALATE naming the parameter, its value and its range.
```

#### DCIC-DEL-A · DELETE · −503 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Validate before you write — DCII redundancy note · *Golden rules:* 7, 10 · *auditor's own id:* DEL-A

**Why:** Pure justification for why the DCIC's own check exists; it changes no action the agent takes.

**Cut from** `<<DCII_ONLY>>The DC Input Inspector independently re-checks EVERYTHING you`

**...through** `parameter validation there is.<</DCII_ONLY>>`

**Replace with:** *(nothing — pure deletion)*

#### DCIC-39 · COMPRESS · −485 chars · risk low

*File:* `DC_prompt_fragments/dc_config/structure.md` · *Section:* (whole fragment) · *Golden rules:* 3, 6 · *auditor's own id:* REC-39

**Why:** The numbered structure restates the middlePos formula given twice more (parameter list + modelling notes) and the ring height that is no longer a parameter.

**Risk:** Shared with the UII.

**Cut from** `The propeller consists of:`

**...through** `Outer section: the blade tip, at the outer radius (impellerRadius), furthest from the centre.`

**Replace with:**

```
The propeller is: a central hub of FIXED radius 4 mm (the blade root); an outer
ring (radius, wall thickness; height derived); and blades spanning hub → ring in
three radial sections — inner (root), middle (positioned along the span by
``middlePos``), outer (tip, at impellerRadius).
```

#### DCIC-18 · COMPRESS · −419 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Acting on a … qualitative directive — full-3D paragraph · *Golden rules:* 5, 6 · *auditor's own id:* REC-18

**Why:** Keeps the widened lever set and the escalate-instead-of-touching-locked rule; drops the third restatement of SOFT TARGET ≠ locked.

**Cut from** `When the directive instead targets the FULL 3D (matching a top / side sketch of`

**...through** `have to change, so the DCOI reports the limit honestly.`

**Replace with:**

```
For a full-3D mismatch the lever set widens to any UNLOCKED parameter that moves
the aspect named (``middlePos``, a chord, an angle, ring proportions).  If every
helping lever is locked, ESCALATE naming them rather than touching a locked value.
```

#### DCIC-17 · SCOPE_PER_AGENT · −385 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## End-of-session feedback message (read-only) · *Golden rules:* 7, 8 · *auditor's own id:* REC-17

**Why:** Inlines the two shared fragments as one sentence each; the mechanism (HumanMessage, name="orchestrator") is invisible to the agent and not actionable.

**Cut from** `## End-of-session feedback message (read-only)`

**...through** `$eos_feedback_outro`

**Replace with:**

```
## End-of-session feedback (read-only)
The Orchestrator may append one final user-feedback message about your scope —
your parameter choices, translations, conversions, and lock handling.  Treat it
as ground truth in your Database Handler answers.
```

#### DCIC-DEL-F · DELETE · −382 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MAY do (DOs) — pipeline + escalate bullets · *Golden rules:* 6, 10 · *auditor's own id:* DEL-F

**Why:** Both bullets are stated at more length by routing_instructions' '### How to decide where to route', which is injected into every chain agent's prompt.

**Risk:** The <<CHAIN_ONLY>> opening marker MUST survive or the conditional region breaks — the replacement is the bare marker.

**Cut from** `<<CHAIN_ONLY>>- DO follow the natural pipeline: when your work succeeds and the`

**...through** `request, still-ambiguous hand-off after one CLARIFY).`

**Replace with:**

```
<<CHAIN_ONLY>>
```

#### DCIC-21 · COMPRESS · −368 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Hand-off to the next agent (IMPORTANT) · *Golden rules:* 7 · *auditor's own id:* REC-21

**Why:** The required phrase is already inside the template line above; only 'copy the paths verbatim' remains as an instruction.

**Cut from** `The phrase ``(newly written this cycle)`` is REQUIRED — it tells the`

**...through** `that set you up.`

**Replace with:**

```
Copy all three paths verbatim from ``new_attempt`` / ``write_parameters`` / the
hand-off that set you up.
```

#### DCIC-32 · COMPRESS · −361 chars · risk low

*File:* `agents/shared/prompt_fragments/value_states.md` · *Section:* SOFT TARGET bullet · *Golden rules:* 2, 7 · *auditor's own id:* REC-32

**Why:** Keeps 'the goal governs, the marker IS the authorisation'; drops the worked examples of the keep-near strength wording.

**Risk:** Shared by 4 agents; SOFT TARGET is a recent feature, so watch for agents anchoring back on the user's number after this cut.

**Cut from** `- **SOFT TARGET** — a value marked ``SOFT TARGET (goal: …; keep near … if`

**...through** `more" → use X).`

**Replace with:**

```
- **SOFT TARGET** — marked ``SOFT TARGET (goal: …; keep near … if free)``.  The
  goal governs: the marker IS the authorisation to move it within range as far as
  the goal requires.  The stated number settles the parameter only where the goal
  does not bear on it.
```

#### DCIC-14 · COMPRESS · −359 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Routing — strict rules (What you CANNOT fix) · *Golden rules:* 2, 5 · *auditor's own id:* REC-14

**Why:** Four bullets become one sentence; the exact-N-fields invariant is preserved.

**Cut from** `**What you CANNOT fix — ESCALATE immediately if asked:**`

**...through** `keys and do NOT invent fields — ESCALATE with a clear note.`

**Replace with:**

```
**ESCALATE instead of answering:** design-intent or operating-condition
questions; opinions on whether a user's value is wise; anything needing
information not in the extraction; and any instruction to write a parameter
outside the list — ``parameters.json`` holds EXACTLY the $parameter_count named
fields, never an invented key.
```

#### DCIC-19 · COMPRESS · −351 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Attempt folders — error after writing · *Golden rules:* 2, 7 · *auditor's own id:* REC-19

**Why:** Keeps the rule and the escalate-on-repeat guard; drops 'this should be rare' and the no-op-ban restatement.

**Cut from** `**If you discover a real error AFTER writing**, that correction is a NEW`

**...through** `once and it persists, ESCALATE instead of trying again.`

**Replace with:**

```
An error found AFTER a successful write is a NEW generation: open a fresh
``new_attempt``, never overwrite.  If the same problem survives one correction,
ESCALATE.
```

#### DCIC-DEL-B · DELETE · −339 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Filtering responsibility · *Golden rules:* 6, 7 · *auditor's own id:* DEL-B

**Why:** Says only that the DCIC decides what is actionable and should say when it skips — both carried by REC-02's replacement ('You decide what is actionable — never silently drop an entry').

**Risk:** If REC-02 is NOT applied, keep one clause of this section instead of deleting outright.

**Cut from** `## Filtering responsibility`

**...through** `off<<DCII_ONLY>> so the DCII can audit the decision<</DCII_ONLY>>.`

**Replace with:** *(nothing — pure deletion)*

#### ⚠️ DCIC-30 · COMPRESS · −317 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MAY do (DOs) — standing directives bullet · *Golden rules:* 5, 7 · *auditor's own id:* REC-30

**Why:** 'Never alter, summarise, translate, re-order, or omit' is five words for one idea (UNCHANGED) plus a why-clause.

**Risk:** Shared by 8 agents; verbatim relay of standing directives is what makes the precision loop work. The replacement keeps UNCHANGED and the Planner-only ownership.

**Cut from** `- DO carry STANDING DIRECTIVES verbatim: if your incoming hand-off`

**...through** `set or change it.`

**Replace with:**

```
- DO reproduce any ``=== STANDING DIRECTIVES ===`` block from your hand-off
  UNCHANGED in your own hand-off; only the Planner may change it.
```

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> Three cuts on the STANDING DIRECTIVES bullet in generic_constraints.md. REC-24 (TC) and REC-30 (DCIC) target the identical 454-char span (lines 12-18) with different replacements; REC-28 (UII) targets an 867-char span (lines 6-18) that fully CONTAINS both, so applying REC-28 after either of the others fails to anchor. The invariant itself is safe in all three — the runtime does not depend on the prompt wording here: standing_directives.is_present() matches the directive TEXT, not the header, and orchestrator.py:738 re-stamps the canonical BLOCK_START on every hop in _DIRECTIVE_CARRIERS, so even a paraphrased header self-heals.
>
> *Safer:* Take REC-28 (UII) alone — it is the superset and already keeps 'reproduce UNCHANGED' plus 'only the Planner may set or change it'. Mark REC-24 and REC-30 superseded.

#### DCIC-DEL-G · DELETE · −314 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MAY do (DOs) — hand-off prose bullet · *Golden rules:* 6, 10 · *auditor's own id:* DEL-G

**Why:** Duplicated by routing_instructions' 'Write the message argument as free-form prose … and nothing they do not', injected into the same prompt.

**Risk:** The <</CHAIN_ONLY>> closing marker MUST survive — the replacement is the bare marker.

**Cut from** `<</CHAIN_ONLY>>- DO write hand-off messages as free-form prose carrying exactly what`

**...through** `— and nothing more.`

**Replace with:**

```
<</CHAIN_ONLY>>
```

#### DCIC-20 · COMPRESS · −312 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Guidelines — item 3 · *Golden rules:* 7 · *auditor's own id:* REC-20

**Why:** Keeps mid-range default + the SUGGESTED SECTION SHAPES seeding exception; drops the rationale for why seeding helps.

**Cut from** `3. For any parameter the user did not mention at all (neither`

**...through** `but starting from the drawing gets the first render close.`

**Replace with:**

```
3. For a parameter the user never mentioned, pick a reasonable mid-range default —
   except that a ``SUGGESTED SECTION SHAPES`` block seeds the section-shape
   parameters (``*Thickness`` / ``*Camber`` / ``*MaxPos``) instead, clamped to
   range and still movable by later feedback.
```

#### DCIC-45 · SCOPE_PER_AGENT · −308 chars · risk medium

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Domain Structure · *Golden rules:* 3, 6, 8 · *auditor's own id:* REC-45

**Why:** After REC-39 and REC-36 the DCIC still holds the hub-4 mm rule, the section names and the middlePos formula in the parameter list and modelling notes — this is the third copy.

**Risk:** Marginal saving assumes REC-39 already applied (standalone it removes 793 chars). If neither REC-39 nor this is applied the agent keeps the long structure text; do not apply this one if the owner prefers keeping a narrative overview for qualitative translation.

**Cut from** `## Domain Structure`

**...through** `$dc_structure`

**Replace with:** *(nothing — pure deletion)*

#### DCIC-DEL-H · DELETE · −305 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MUST NOT do (DON'Ts) — permission bouncing · *Golden rules:* 6, 10 · *auditor's own id:* DEL-H

**Why:** Word-for-word duplicated by routing_instructions' '### Permission / authorisation issues → hub' section in the same assembled prompt.

**Risk:** The <<CHAIN_ONLY>> opening marker MUST survive — the replacement is the bare marker.

**Cut from** `<<CHAIN_ONLY>>- DON'T bounce permission questions back to the previous agent.`

**...through** `them to the Orchestrator.`

**Replace with:**

```
<<CHAIN_ONLY>>
```

#### ⚠️ DCIC-35 · COMPRESS · −299 chars · risk medium

*File:* `agents/shared/prompt_fragments/value_states.md` · *Section:* closing paragraph (one source is enough / how far may it move) · *Golden rules:* 5, 7 · *auditor's own id:* REC-35

**Why:** Keeps the no-re-confirmation rule and the how-far-may-it-move scale; drops the 'a line literally saying user-locked' sub-case.

**Risk:** That sub-case was the fix for an agent treating a default lock as absolute; the surviving 'never demand re-confirmation of an authorisation the hand-off already carries' is the general principle behind it.

**Cut from** `One source is enough — never demand a "ritual re-confirmation" of an`

**...through** `bounded by range.`

**Replace with:**

```
One source is enough — never demand re-confirmation of an authorisation the
hand-off already carries.  How far an authorised or soft value may move follows
the wording: "as needed" = the smallest change that restores viability; "freely",
or nothing said = as far as the goal requires, within range.
```

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> The replacement drops 'A line literally saying "user-locked" is only the DEFAULT lock and does NOT override a current authorisation — the hand-off, DESIGN INTENT, and any inline annotation are the current sources of truth.' I grepped for 'user-locked' / 'default lock' across agents/ and DC_prompt_fragments/: in the 7-agent tree the ONLY statement of this rule is the sentence being cut. (Hits in agents/5agent/* and agents/conductor/* are a separate topology and use the phrase in a different sense.) Notably, BOTH whole-file rewrites of the same fragment — REC-04 (DCII) and REC-04 (DCOI) — deliberately keep it ('a line saying "user-locked" is only the default lock'), which is evidence the other auditors judged it load-bearing. Without it, an agent that sees 'user-locked' in a hand-off can treat it as absolute and refuse an authorisation that DESIGN INTENT actually grants — the failure this sentence patches. This cut also overlaps REC-04 (either version), which covers the same closing paragraph.
>
> *Safer:* Add one clause to the replacement's first sentence: "One source is enough — never demand re-confirmation of an authorisation the hand-off already carries, and a line saying \"user-locked\" is only the DEFAULT lock." (~12 tokens)

#### DCIC-36 · COMPRESS · −290 chars · risk low

*File:* `DC_prompt_fragments/dc_config/modelling_notes.md` · *Section:* middlePos bullet · *Golden rules:* 6 · *auditor's own id:* REC-36

**Why:** The same formula and range appear in the parameter list entry for middlePos; keep only the NOT-of-impellerRadius correction, which is the actual bug guard.

**Risk:** Shared with the DCII.

**Cut from** `- ``middlePos`` (the middle section's radial position) is a fraction of the BLADE`

**...through** `Its range [0.3, 0.7] means the middle section sits 30–70% of the way along the blade.`

**Replace with:**

```
- ``middlePos`` is a fraction of the blade SPAN from the 4 mm root, NOT of
  ``impellerRadius``: radius = 4 + middlePos·(impellerRadius − 4) mm.
```

#### ⚠️ DCIC-43 · MERGE · −248 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MUST NOT do (DON'Ts) — invent / fabricate · *Golden rules:* 2, 5, 11 · *auditor's own id:* REC-43

**Why:** Merges the two DON'Ts into one bullet and drops the second section heading now that the fragment is a single short list.

**Risk:** The anti-fabrication rule is the never-describe-what-you-did-not-load patch; it is preserved in full ('cannot source to a tool result, an agent's history, or the user's own words').

**Cut from** `### What every agent in any design configurator MUST NOT do (DON'Ts)`

**...through** `or something the user literally said, do not make it.`

**Replace with:**

```
- DON'T invent tools, files, policies, scores or version numbers that do not
  exist, and DON'T state an observation you cannot source to a tool result, an
  agent's history, or the user's own words.  If you can't, ESCALATE.
```

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> Both anchor at the same quote_start ('### What every agent in any design configurator MUST NOT do (DON'Ts)', line 27) but end at different points — REC-42 spans 648 chars (through 'unchanged input yields nothing new.', line 36), REC-43 spans 472 chars (through 'do not make it.', line 33). They are nested, not independent: REC-43's span lies entirely inside REC-42's. Applying REC-42 first makes REC-43 unanchorable; applying REC-43 first truncates REC-42's span. Both also sit inside the whole-file rewrites REC-03 (DCII) and REC-03 (DCOI).
>
> *Safer:* Take REC-42 alone (the superset — it also folds in the anti-loop bullet) and mark REC-43 superseded; if the whole-fragment REC-03 is applied instead, drop both.

#### DCIC-38 · COMPRESS · −240 chars · risk low

*File:* `DC_prompt_fragments/dc_config/modelling_notes.md` · *Section:* ### Hard engineering blockers · *Golden rules:* 1, 3 · *auditor's own id:* REC-38

**Why:** The single listed blocker (thickness ≤ 0) is unreachable given the printed range [3; 24] — the section is a general principle wrapped around a dead example.

**Risk:** Kept as a heading because the DCIC's validate-step references '## Modelling Notes' hard-blocker inequalities; deleting outright would dangle that reference.

**Cut from** `### Hard engineering blockers (parameter combinations that break the geometry)`

**...through** `treat any violation as a non-negotiable fail.`

**Replace with:**

```
### Hard engineering blockers
Any combination that makes the geometry degenerate or self-intersecting (e.g. a
non-positive section thickness) is a non-negotiable fail, not a style preference.
```

#### DCIC-22 · COMPRESS · −238 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Attempt folders — Forbidden: a no-op write · *Golden rules:* 7 · *auditor's own id:* REC-22

**Why:** Keeps the ban and both remedies; drops 'you are stateful' and the why-it-is-bad sentence.

**Cut from** `**Forbidden: a no-op write.**  You may NOT write a ``parameters.json```

**...through** `not and wastes a downstream cycle.`

**Replace with:**

```
**No no-op writes.**  You may not write a ``parameters.json`` byte-identical to
one you already wrote this session — pick different values or ESCALATE.
```

#### DCIC-DEL-I · DELETE · −234 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MUST NOT do (DON'Ts) — don't loop · *Golden rules:* 6, 10 · *auditor's own id:* DEL-I

**Why:** routing_instructions ships a longer '### Do not loop — ESCALATE when stuck' section into the same prompt.

**Cut from** `- DON'T loop: if you are about to call the same tool with the same`

**...through** `unchanged input yields nothing new.`

**Replace with:** *(nothing — pure deletion)*

#### DCIC-33 · COMPRESS · −230 chars · risk low

*File:* `agents/shared/prompt_fragments/value_states.md` · *Section:* FREE bullet · *Golden rules:* 7 · *auditor's own id:* REC-33

**Why:** Same three facts (absent = free, released values are omitted, qualitative-to-numeric is free unless pinned) in half the words.

**Cut from** `- **FREE** — a parameter absent from QUANTITATIVE INPUTS: either the user never`

**...through** `as LOCKED for that cycle.`

**Replace with:**

```
- **FREE** — absent from QUANTITATIVE INPUTS (never given, or released — a
  released value is simply omitted).  Yours to choose within range, as is any
  qualitative description you must turn into a number, unless a directive pins it.
```

#### DCIC-26 · COMPRESS · −205 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Output Format · *Golden rules:* 4, 6 · *auditor's own id:* REC-26

**Why:** 'Write your note in the message argument' is the routing block's job; only the don't-echo-the-JSON rule steers away from default.

**Cut from** `## Output Format`

**...through** `JSON in text — it is stored on disk by the tool.`

**Replace with:**

```
Do NOT repeat the parameter JSON in prose — the tool stores it on disk.
```

#### DCIC-24 · COMPRESS · −201 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Re-reading raw inputs (optional) · *Golden rules:* 7, 9 · *auditor's own id:* REC-24

**Why:** Tool mechanics belong in the tool schemas; the two facts that matter are which file is primary and that this agent cannot see images.

**Cut from** `## Re-reading raw inputs (optional)`

**...through** `images themselves — rely on the extraction.`

**Replace with:**

```
## Raw inputs (optional)
Your input is ``extracted_inputs.txt``.  ``list_input_files`` and
``read_input_text(path)`` reach the raw files under ``inputs/``; you cannot view
images — rely on the extraction.
```

#### DCIC-23 · COMPRESS · −199 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Attempt folders — Reuse the session's history · *Golden rules:* 7 · *auditor's own id:* REC-23

**Why:** Same instruction, shorter, and drops the conditional naming of which downstream agent reads it.

**Cut from** `**Reuse the session's history.**  ``list_attempts`` / ``read_attempt```

**...through** `hand-off so the <<DCII_ONLY>>DCII / <</DCII_ONLY>>DCOI know you considered it.`

**Replace with:**

```
**Reuse history.**  ``list_attempts`` / ``read_attempt`` show prior cycles; prefer
a direction you have not already seen fail, and name that attempt in your hand-off.
```

#### DCIC-DEL-D · DELETE · −188 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Attempt folders — Carry Current attempt forward · *Golden rules:* 6 · *auditor's own id:* DEL-D

**Why:** Exactly what the '## Hand-off' section's three mandatory lines already require.

**Cut from** `**Carry ``Current attempt:`` forward** — every FORWARD you send`

**...through** `(<<DCII_ONLY>>to the DCII<</DCII_ONLY>><<DCII_OFF>>to the Tool Caller<</DCII_OFF>>) MUST quote the folder you wrote into.`

**Replace with:** *(nothing — pure deletion)*

#### DCIC-27 · COMPRESS · −186 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Hand-off to the next agent (IMPORTANT) · *Golden rules:* 5, 11 · *auditor's own id:* REC-27

**Why:** Keeps the three-line template exactly (including the required '(newly written this cycle)' phrase) and drops the DCII/TC conditional naming and the IMPORTANT tag.

**Cut from** `## Hand-off to the next agent (IMPORTANT)`

**...through** `    Extracted inputs file: <same path the UII gave you>`

**Replace with:**

```
## Hand-off
Every FORWARD ``message`` must carry these three lines with absolute paths:

    Current attempt: <folder you wrote into>
    Parameters file (newly written this cycle): <Current attempt>/parameters.json
    Extracted inputs file: <same path the UII gave you>
```

#### DCIC-DEL-C · DELETE · −177 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Guidelines — items 4 and 5 · *Golden rules:* 4, 6 · *auditor's own id:* DEL-C

**Why:** Item 4 is restated as check 1 of '## Validate before you write'; item 5 ('consider design intent') restates default reasoning.

**Risk:** Only safe while the Validate section survives — do not apply together with a cut that removes check 1.

**Cut from** `4. ALL values MUST be within their allowed ranges.`

**...through** `defaults and translating qualitative descriptions.`

**Replace with:** *(nothing — pure deletion)*

#### DCIC-DEL-E · DELETE · −170 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Hand-off — CLARIFY/ESCALATE path note · *Golden rules:* 4 · *auditor's own id:* DEL-E

**Why:** States that a requirement scoped to FORWARDs does not apply elsewhere — inferable from the rule itself.

**Cut from** `If you CLARIFY back to <<PF_ON>>the UII<</PF_ON>><<PF_OFF>>the Planner<</PF_OFF>> or ESCALATE to the`

**...through** `Orchestrator, no path lines are needed — only FORWARDs carry them.`

**Replace with:** *(nothing — pure deletion)*

#### DCIC-25 · COMPRESS · −162 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Routing — Tool-error self-correction (HARD) · *Golden rules:* 5, 7 · *auditor's own id:* REC-25

**Why:** Same rule without the example error string and the HARD tag (which is diluted across seven uses in this prompt).

**Cut from** `**Tool-error self-correction (HARD).**  A tool error naming a missing`

**...through** `tool-schema / interface bug.`

**Replace with:**

```
A tool error naming a missing argument means YOUR call omitted it — re-issue the
same call with it added; it is never a schema bug.
```

#### DCIC-29 · COMPRESS · −145 chars · risk low

*File:* `DC_prompt_fragments/dc_config/modelling_notes.md` · *Section:* NACA / high-point bullets · *Golden rules:* 6 · *auditor's own id:* REC-29

**Why:** 'tenths of chord' is already the unit printed beside innerMaxPos/outerMaxPos in the parameter list.

**Risk:** Shared with the DCII.

**Cut from** `- Blade profiles are NACA-style airfoils parameterised by thickness, camber,`

**...through** `tenths of chord (e.g. a value of 3 means 30% chord from the leading edge).`

**Replace with:**

```
- Blade profiles are NACA-style airfoils (thickness, camber, and high-point in
  tenths of chord).
```

#### DCIC-44 · COMPRESS · −142 chars · risk low

*File:* `agents/shared/prompt_fragments/value_states.md` · *Section:* intro + LOCKED bullet · *Golden rules:* 7 · *auditor's own id:* REC-44

**Why:** 'LOCKED is not an absolute wall' is a rephrasing of the sentence that follows it.

**Cut from** `Every value the user could have given is in exactly one of three states,`

**...through** `authorisation frees it (below).`

**Replace with:**

```
Every user value is in one of three states, read off QUANTITATIVE INPUTS:

- **LOCKED** — stated plainly, no marker.  Fixed unless an authorisation frees it
  (below).
```

#### DCIC-42 · MERGE · −134 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent in any design configurator MAY do (DOs) · *Golden rules:* 8, 11 · *auditor's own id:* REC-42

**Why:** Two bullets merge into one and the long heading shortens now that DOs and DON'Ts live under a single heading.

**Risk:** Shared by 8 agents; apply together with REC-43, which removes the matching DON'Ts heading.

**Cut from** `### What every agent in any design configurator MAY do (DOs)`

**...through** `- DO use only the tools listed for your role; that list is exhaustive.`

**Replace with:**

```
### Every agent (DOs / DON'Ts)
- DO act on your hand-off and the files it points to, using only your bound
  tools; that list is exhaustive.
```

</details>

<details><summary><b>Proposed shape of the shrunk prompt</b></summary>

```
DC Input Creator — post-cut skeleton (~13,260 chars ≈ 3,315 tok, excl. the runtime {routing_instructions} block and tool schemas)

  Role line ("You are the DC Input Creator … provide a value for every parameter")   ~35 tok
  ## Complete Parameter List (all 16 required)   [$parameter_list, UNTOUCHED]        ~402 tok
  ## Modelling Notes                             [$modelling_notes, cut 2696→1012]   ~253 tok
  ## Guidelines (3 items) + $qualitative_examples                                    ~160 tok
  ## Reading QUANTITATIVE INPUTS                                                      ~58 tok
  ## The three states — LOCKED / SOFT TARGET / FREE  [$value_states, 2915→1253]      ~313 tok
      + Writing each state                                                            ~98 tok
  ## Real-world quantities (convert / judgement / decline)                           ~147 tok
      + one entry constraining several parameters                                     ~67 tok
  ## Qualitative directives (act or escalate; precision rounds; full-3D)             ~254 tok
  ## Validate before you write (HARD)  (3 checks + locked-out-of-range collision)    ~170 tok
  ## Attempt folders (append-only; no no-op writes; which folder; after-write; reuse) ~286 tok
  ## Raw inputs (optional) + ## Read / write policy                                  ~130 tok
  ## Hand-off (3 mandatory path lines; provenance; precision-loop shortcut)          ~193 tok
  ## Routing — what you can / cannot fix + tool-error self-correction                ~192 tok
  ## End-of-session feedback (read-only)                                              ~63 tok
  ## Hard constraints — generic  [$hard_constraints_generic, 3451→994]               ~249 tok
  ## Hard constraints — tools    [$hard_constraints_tools, 1261→535]                 ~134 tok
      + one inlined DC-vocabulary rule (replaces the $hard_constraints_dc splice)     ~51 tok
  <<BSV_ON>> Blade-sections tasks (per-agent line only)                               ~64 tok
  {routing_instructions}                                                    (runtime, ~1,100 tok)

Dropped entirely from this agent: $dc_structure, $output_file_locations, $hard_constraints_dc,
$blade_sections_visualizer (+ _off), $eos_feedback_intro/_outro.
```

</details>

**Auditor notes.** MEASUREMENT BASIS. Every chars_removed is (exact source block size) − (exact replacement size), both counted with awk over the real files, not estimated. Block sizes came from a cumulative per-line char count of each file. Assembled baseline reconciles: prompt.md is 21,924 chars of agent-owned text; the spliced fragments add ~16,400 (parameters 1,609 / structure 773 / modelling_notes 2,696 / qualitative_examples 303 / value_states 2,915 / output_file_locations 1,717 / generic_constraints 3,451 / hard_constraints_dc 1,248 / hard_constraints_tools 1,261 / bsv 746+338 / eos 288) ≈ 38.3k chars ≈ the measured 9,586 tok. The 53 cuts sum to 25,083 chars → ~13,260 chars ≈ 3,315 tok. That is a 65% cut but still ~10% above the 3,000 ceiling; getting under it would need either a terser rewrite of my own replacements (they total 7,469 chars) or dropping $qualitative_examples and the precision-loop shortcut, which I judged worth keeping.

SHARED-FRAGMENT LEVERAGE (a cut here changes every agent that splices it):
  generic_constraints.md — 8 agents. 8 cuts, 3,451 → 994 chars (−2,457 each, ≈ −4,900 tok fleet-wide). Four of those cuts are pure de-duplication against routing_instructions, which is injected into the same prompts and says the same things at greater length.
  value_states.md — 4 agents (Planner, DCIC, DCII, DCOI). 5 cuts, 2,915 → 1,253.
  hard_constraints_tools.md — 8 agents. 1,261 → 535.
  modelling_notes.md — 2 agents (DCIC, DCII). 2,696 → 1,012.
  structure.md — 2 agents (DCIC, UII). 773 → 288.
  Everything else is DCIC-owned or a per-agent splice removal.

CONDITIONAL-REGION HAZARD. Four generic_constraints cuts sit on lines carrying <<CHAIN_ONLY>> / <</CHAIN_ONLY>> markers (the markers are glued to the first/last bullet, not on their own lines). DEL-F, DEL-G, DEL-H and REC-31 therefore have the bare marker as their replacement — dropping it would leave an unmatched marker rendered literally into eight prompts. Do not "simplify" those replacements to empty strings.

WHAT I DELIBERATELY DID NOT CUT.
  * The 16-parameter list with ranges (1,609 chars) — untouched per your instruction, and it is the single largest surviving block.
  * $qualitative_examples (303 chars) — five canonical qualitative→numeric mappings; exactly the shape golden rule 2 wants and cheap.
  * The three mandatory hand-off path lines including "(newly written this cycle)" — REC-27 keeps the template verbatim.
  * The per-parameter range check (Validate item 1) and its "never a blanket all-16-are-fine" phrasing — that is the DCII blanket-approval failure mode, restated for this agent.
  * The *Thickness/*Camber = % of that section's OWN chord fact — kept twice on purpose (REC-04 for the refine loop, REC-37 for conversions), because it caused a real bug and the two contexts are far apart in the prompt.
  * The anti-fabrication rule and the no-prose-without-a-routing-tool-call rule — both shortened, neither removed.

CUTS THAT REMOVE A KNOWN-FAILURE PATCH (all have a general-principle replacement, flagged medium):
  REC-31 shortens the pipeline-halt patch, relying on routing_instructions still shipping the full "Routing is a tool call — MANDATORY" section. Verify that block is present for every agent before applying.
  REC-07 drops the "NOT the User Input Inspector" anti-bounce clause; the routing block's permission rule covers it.
  REC-35 drops the '"user-locked" is only the DEFAULT lock' sub-case; the surviving no-re-confirmation sentence is the principle behind it.
  REC-28 removes the hub_radius/fillet_radius/tip_clearance enumeration for this agent; REC-14 keeps the enforcement ("parameters.json holds EXACTLY the 16 named fields").
  REC-06 rewrites the DCIC-owns-attempt-creation rule, which was itself a fix for an ownership bug — both branches and the exactly-one invariant survive.

OVERLAPPING PAIRS (do not double-count):
  REC-45 (drop $dc_structure from the DCIC) is priced at its MARGINAL value assuming REC-39 (compress structure.md) is applied first; standalone it removes 793 chars.
  DEL-B (Filtering responsibility) is safe only if REC-02 is applied, since REC-02's replacement carries the "you decide what is actionable" clause.
  DEL-C (Guidelines items 4-5) is safe only while the Validate section survives.
  I dropped a shared compress of hard_constraints_dc.md in favour of REC-28 (per-agent removal) — the other 7 agents would still benefit from compressing that fragment 1,248 → ~610, which I can spec separately.

TOOL-SCHEMA SIDE (golden rule 9, not in this diff). The DCIC carries 12 tool schemas ≈ 1,769 tok on top of the prompt. list_attempts + read_attempt + read_input_text + list_input_files is four read tools where the prose only ever asks for two behaviours (inspect prior cycles; read a raw input file); merging them would cut both schema tokens and the two prompt sections (REC-23, REC-24) that exist to disambiguate them.

---

### 4.6 DC Input Inspector — 11,447 → ~2,500 tok

| ID | action | section | −chars | rules | risk | what |
|---|---|---|---:|---|---|---|
| **DCII-01** | SCOPE_PER_AGENT | ## Sketch handling (when the user supplied a sketch) | 10363 | 3,8 | low | The 10.6k-char sketch corpus is authoring/observation guidance for the UII (who reads the images and writes the extraction) and the DCOI (who compares renders to the sketch); the DCII only needs the one-line strictness verdict the UII already wrote into DESIGN INTENT. |
| **DCII-02** | COMPRESS | ### 3. Critical engineering check (hard blockers only) | 3038 | 5,6,7 | low | `$modelling_notes` is spliced a SECOND time inside this paragraph (line 143), duplicating the entire 2.7k-char fragment already printed under "## Modelling Notes" 100 lines earlier — the prose around it is three sentences of pointer. |
| ⚠️ **DCII-03** | COMPRESS | whole fragment (DOs / DON'Ts) | 2079 | 4,5,7,8 | medium | The copy-pasted 3.4k-char constitution is spliced into all 8 chain agents; half of it is justification prose and default behaviour, and every rule survives in the shorter form. |
| ⚠️ **DCII-04** | COMPRESS | whole fragment (LOCKED / SOFT TARGET / FREE) | 1985 | 2,5,7 | medium | Three state definitions plus three authorisation sources are stated in ~2.9k chars of hedging prose; the semantics compress to a third with no rule lost. |
| **DCII-05** | COMPRESS | #### 4a. Verbatim entries — the changeability check | 1750 | 2,6,7 | medium | A 2.6k-char decision tree that re-states the LOCKED/SOFT/FREE rules already given under "The three states of a user value" and the CLARIFY-vs-ESCALATE rules already given under "Verdict → routing". |
| **DCII-06** | COMPRESS | ### 1. Range validation (STRICT — explicit per-parameter che | 1483 | 1,5,7 | medium | Four paragraphs saying the same thing (check each value individually) plus a template-only "concrete example" with placeholder tokens that teaches nothing. |
| **DCII-07** | COMPRESS | #### 4b. Real-world-quantity entries | 1378 | 2,7 | low | Three bullet sub-specs of what the DCIC's hand-off should say, each with its own justification paragraph; the check is one sentence per route. |
| **DCII-08** | COMPRESS | ## Verdict → routing (STRICT — the tool follows your verdict | 1330 | 2,6,10 | medium | The REVISE / ESCALATE bullet lists re-enumerate cases already decided in §1, §4a, §4b and §5; the range exception is restated for the third time in the prompt. |
| **DCII-09** | COMPRESS | ## Optional reference: user input images | 1280 | 2,7,9 | low | Two paragraphs of when-to-look-at-an-image reasoning plus five tool blurbs that duplicate the bound tool schemas; the trigger condition is one clause. |
| **DCII-10** | COMPRESS | ## Your two primary utility tools (IMPORTANT) | 1122 | 2,5,7 | low | Three bullets restating "when in doubt re-read" plus a full paragraph per tool that the tool schema already carries. |
| **DCII-11** | REPLACE_WITH_EXAMPLES | ### Common unit-conversion patterns for this configurator | 1098 | 2,3 | low | Six enumerated conversion recipes are a lookup table for arithmetic the model can do; the two that encode real gotchas (chord-relative percentages, middlePos from the 4 mm root) are worth keeping, the rest are unit algebra. |
| ⚠️ **DCII-12** | COMPRESS | routing_instructions() — "### Routing is a tool call — MANDA | 1050 | 5,6,7 | medium | Three paragraphs and a retired-format warning (``---ROUTING---``) all restate one rule that generic_constraints.md also states; the retired template is dead weight. |
| **DCII-13** | SCOPE_PER_AGENT | <<BSV_ON>> blade-sections visualizer block | 899 | 8,9 | low | The DCII neither renders nor chooses a render mode — it validates a JSON file and routes; the cheap-sections-render pitch is for the Planner, Tool Caller and DCOI. |
| **DCII-14** | COMPRESS | ## Your Role | 755 | 5,6 | low | A five-axis table of contents for the "What to Check" sections that follow verbatim 80 lines later. |
| **DCII-15** | COMPRESS | ### 4. Consistency between parameters.json, extracted_inputs | 740 | 6,7 | low | A justification paragraph for why the extraction is authoritative-but-not-final, plus a parenthetical that re-lists the four input tools already listed above. |
| **DCII-16** | COMPRESS | routing_instructions() — "### How to decide where to route" | 620 | 10,7 | low | Four decision rules written as full sentences with embedded parentheticals; this is routing protocol the tool schemas already encode, so the prose only needs to be a lookup. |
| **DCII-17** | COMPRESS | routing_instructions() — "### Permission / authorisation iss | 600 | 5,7 | low | Two paragraphs restating one rule (read the hand-off again before escalating; don't bounce permission questions backward), which generic_constraints.md also states. |
| **DCII-18** | COMPRESS | ## Hand-off to the Tool Caller (IMPORTANT) | 547 | 7,10 | low | The two required lines are load-bearing; the surrounding three paragraphs explain why the Tool Caller wants them, which does not change the DCII's behaviour. |
| **DCII-19** | DELETE | routing_instructions() — "### Do not loop — ESCALATE when st | 520 | 5,6 | low | Stated a third time here — generic_constraints.md already says "DON'T loop … STOP and ESCALATE", and the escalate-when-stuck branch is in "How to decide where to route" directly above. |
| **DCII-20** | COMPRESS | ### Tool-use hard rules (every agent) | 490 | 7,8 | low | Same three rules with the justifications and the who-opens-the-attempt aside removed (the latter matters to the DCIC and Orchestrator, not to every agent). |
| **DCII-21** | COMPRESS | ### 5. Appropriateness — your engineering critique | 490 | 5,7 | low | Two bullets plus a preamble to say one thing: advise via CLARIFY, escalate only to go beyond the Planner. The "notes, not blockers" line is already in §3. |
| **DCII-22** | COMPRESS | whole fragment (16-parameter list) | 490 | 11 | low | Pure whitespace/punctuation reformat — every name, unit, semantic note and range is preserved exactly; only the column padding and the em-dash separators go. |
| **DCII-23** | COMPRESS | ### Domain hard rules (every agent) | 478 | 2,3 | medium | Two long enumerations (11 mesh post-processing verbs, 12 analysis types) collapse to canonical examples plus the general principle. |
| **DCII-24** | COMPRESS | ## Output Format | 362 | 4,11 | low | A five-heading template immediately disclaimed as "not a fixed template"; the content it asks for is exactly what the checks above already produce. |
| **DCII-25** | COMPRESS | ### Available routing tools | 220 | 6,9 | low | Duplicates the "Verdict → routing" section of the DCII prompt almost verbatim; the roster only needs the tool names and one clause each. |
| **DCII-26** | COMPRESS | Two self-checks before you route | 206 | 5,6 | low | Both self-checks restate rules given two paragraphs earlier (APPROVE→call_tool_caller) and in §1 (per-parameter comparison). |
| **DCII-27** | COMPRESS | opening bullets (NACA / middlePos / integer types) | 186 | 6,7 | low | Tightens the middlePos explanation (three restatements of the same formula) and folds in the two production gotchas — percentages are of the section's OWN chord, and the middle section has no shape parameters of its own. |
| **DCII-28** | MERGE | ## End-of-session feedback message (read-only) | 142 | 7,11 | low | Four lines defining "your scope" that merely re-list the checks the whole prompt describes. |
| **DCII-29** | COMPRESS | ### 2. Consistency with the user's stated inputs | 91 | 7 | low | Minor tightening; the rule is one sentence. |

<details><summary><b>Full text of each change</b></summary>

#### DCII-01 · SCOPE_PER_AGENT · −10363 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## Sketch handling (when the user supplied a sketch) · *Golden rules:* 3, 8 · *auditor's own id:* REC-01

**Why:** The 10.6k-char sketch corpus is authoring/observation guidance for the UII (who reads the images and writes the extraction) and the DCOI (who compares renders to the sketch); the DCII only needs the one-line strictness verdict the UII already wrote into DESIGN INTENT.

**Risk:** UII and DCOI keep their own copies of $sketch_handling/$sketch_notes untouched; only the DCII loses them. The blade-COUNT-is-exact rule (the one sketch fact a parameter validator can act on) is preserved in the replacement.

**Cut from** `## Sketch handling (when the user supplied a sketch)`

**...through** `$sketch_handling

$sketch_notes`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Sketch handling
When the user supplied a sketch, the extraction's DESIGN INTENT states
whether it is ROUGH (match qualitatively — wobble, asymmetry and off-centre
features are drawing artifacts, not defects) or PRECISE (drawn proportions
should be reproduced as closely as the parameters allow).  Judge the
parameters against that strictness.  Blade COUNT is always exact.
```

#### DCII-02 · COMPRESS · −3038 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ### 3. Critical engineering check (hard blockers only) · *Golden rules:* 5, 6, 7 · *auditor's own id:* REC-02

**Why:** `$modelling_notes` is spliced a SECOND time inside this paragraph (line 143), duplicating the entire 2.7k-char fragment already printed under "## Modelling Notes" 100 lines earlier — the prose around it is three sentences of pointer.

**Risk:** Verify no other agent relies on the parenthetical splice; grep shows $modelling_notes appears twice only in this file (lines 26 and 143).

**Cut from** `### 3. Critical engineering check (hard blockers only)
Flag combinations that make the geometry physically impossible or`

**...through** `unconventional" design choices are notes, not blockers.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### 3. Engineering feasibility (hard blockers only)
Check the "Hard engineering blockers" inequalities listed in Modelling Notes
above via ``calculate`` (batched with your range arithmetic); any violation
is a hard FAIL.  Style, operating-condition assumptions, and "typical vs
unconventional" choices are notes, not blockers.
```

#### ⚠️ DCII-03 · COMPRESS · −2079 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* whole fragment (DOs / DON'Ts) · *Golden rules:* 4, 5, 7, 8 · *auditor's own id:* REC-03

**Why:** The copy-pasted 3.4k-char constitution is spliced into all 8 chain agents; half of it is justification prose and default behaviour, and every rule survives in the shorter form.

**Risk:** AFFECTS ALL 8 AGENTS (+4 five-agent prompts). The two load-bearing invariants — routing-is-a-tool-call-or-the-pipeline-halts, and copy STANDING DIRECTIVES verbatim — are kept in full; the <<CHAIN_ONLY>> markers are preserved so the hub/Receptionist filtering still works.

**Cut from** `### What every agent in any design configurator MAY do (DOs)`

**...through** `only exceptions are the Receptionist's direct user replies and the
Orchestrator's final user-facing wrap-up.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### DOs
- DO act only on the paths and data your hand-off supplies, using only the
  tools listed for your role.
<<CHAIN_ONLY>>- DO FORWARD to your natural next agent when your work succeeds and the
  Orchestrator did not ask you to report back; otherwise return to it.
  ESCALATE the moment something blocks you that no chain agent can fix.
- DO reproduce any ``=== STANDING DIRECTIVES (copy verbatim to the next
  agent) ===`` … ``=== END STANDING DIRECTIVES ===`` block UNCHANGED in your
  own hand-off — never alter, summarise, re-order or omit it; only the
  Planner may change it.
<</CHAIN_ONLY>>- DO write hand-offs as free-form prose carrying exactly what the recipient
  needs — the paths their tools require, what changed and why, and the true
  authorship of any non-user-authored value ("the Planner directed …", "the
  user asked …"; never relabel one source as another).
- DO answer in English.

### DON'Ts
- DON'T invent tools, files, fallback policies, confidence scores or version
  numbers that do not exist; if your bound tools can't do it, ESCALATE.
- DON'T state an observation you cannot source to a tool result, an agent's
  history, or something the user literally said.
- DON'T repeat a tool call with the same arguments, and DON'T retry a
  failing step blindly — ESCALATE instead.
<<CHAIN_ONLY>>- DON'T bounce permission questions backward, and DON'T script the final
  user-facing reply — route your content to the Orchestrator and let the
  Receptionist word it.
<</CHAIN_ONLY>>- DON'T communicate in plain prose.  The ONLY channel to another agent is a
  routing tool call; any text you emit without one is silently discarded and
  the pipeline halts.  Invoke the tool in the same response where you finish
  your work.
```

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> The final bullet drops the clause 'the only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up'. That bullet sits OUTSIDE the <<CHAIN_ONLY>> markers, so it is spliced verbatim into the Receptionist's prompt — and agents/shared/prompts.py lists the Receptionist in _NON_CHAIN_AGENTS AND it never receives routing_instructions() (confirmed: only creator, dc_input_creator, dc_input_inspector, dc_output_inspector, planner, tool_caller, user_input_inspector call it). So after this cut the Receptionist's prompt asserts, unqualified, 'any text you emit without one is silently discarded and the pipeline halts', which directly contradicts its own Situation-B rule at agents/receptionist/prompt.md: 'you MUST respond with plain user-facing text, you must NOT invoke ``call_orchestrator`` (that would loop control back into the system)'. Strong evidence the clause is deliberate, not vestigial: the independently authored 5-agent copy keeps it too (agents/5agent/prompt_fragments/generic_constraints_5agents.md:53, 'only exception is the Receptionist's direct user replies'). Everything else in this rewrite checks out — STANDING DIRECTIVES verbatim, the halt consequence, the CHAIN_ONLY markers and the permission bullet all survive correctly placed.
>
> *Safer:* Append eight words to the last bullet: "...and the pipeline halts — the Receptionist's direct user replies are the sole exception."

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> Two problems. (1) Its last bullet ends '...silently discarded and the pipeline halts. Invoke the tool in the same response where you finish your work.' - the Receptionist/Orchestrator exception is gone, and this fragment is spliced into both non-chain agents (verified above). (2) It is one of TWO whole-fragment rewrites of generic_constraints.md in this batch (the other is REC-03 for the DCOI, with a different structure and different headings), and it collides with seven partial cuts on the same file (REC-42, REC-28 UII; REC-43, REC-30, REC-31 DCIC; REC-24, REC-21, REC-28 TC). Applying any two of these means the second's quote no longer matches, so the owner can silently believe a rule was preserved that was not.
>
> *Safer:* Pick ONE generic_constraints.md rewrite (this or the DCOI's REC-03), drop the partial cuts on the same file, and keep the exception clause on the final prose bullet.

> ⚠️ **Verifier — QUOTE_WRONG**
>
> Two defects. (1) quote_end is not verbatim: the cut quotes 'only exceptions are the Receptionist's direct user replies and the\nOrchestrator's final user-facing wrap-up.' but generic_constraints.md lines 54-55 are indented two spaces on BOTH lines (cat -A shows '  only exceptions are...$' / '  Orchestrator's final user-facing wrap-up.$'). A verbatim apply will not anchor. (2) Same substantive defect as REC-03 (DCOI): the replacement's closing DON'T drops the Receptionist/Orchestrator exception from a bullet those two non-chain agents actually receive and rely on (receptionist.py:8, orchestrator.py:542) — and neither gets routing_instructions() as a backstop. This cut also rewrites the whole of generic_constraints.md and so collides with REC-03 (DCOI), REC-21/24/28 (TC), REC-28/36/42 (UII) and REC-30/31/43 (DCIC), all of which edit spans inside it.
>
> *Safer:* Fix quote_end to '  only exceptions are the Receptionist's direct user replies and the\n  Orchestrator's final user-facing wrap-up.' and end the last bullet with '...and the pipeline halts — except the Receptionist's direct user replies and the Orchestrator's final wrap-up.'

#### ⚠️ DCII-04 · COMPRESS · −1985 chars · risk medium

*File:* `agents/shared/prompt_fragments/value_states.md` · *Section:* whole fragment (LOCKED / SOFT TARGET / FREE) · *Golden rules:* 2, 5, 7 · *auditor's own id:* REC-04

**Why:** Three state definitions plus three authorisation sources are stated in ~2.9k chars of hedging prose; the semantics compress to a third with no rule lost.

**Risk:** AFFECTS Planner, DCIC, DCII, DCOI (+5-agent DCOI). Keeps the SOFT-TARGET-is-its-own-authorisation rule and the "one source is enough, never demand re-confirmation" rule verbatim in meaning; drops only the obsolete-annotation backstory and the FREE-vs-qualitative aside.

**Cut from** `Every value the user could have given is in exactly one of three states,`

**...through** `/ as much as possible" (or nothing said) = as far as the goal requires,
bounded by range.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Every value the user could have given is in exactly one of three states,
read off the extraction's QUANTITATIVE INPUTS section:

- **LOCKED** — stated there with no marker.  Fixed unless an authorisation
  frees it.
- **SOFT TARGET** — marked ``SOFT TARGET (goal: …; keep near … if free)``.
  The goal governs: the marker itself IS the authorisation to move the value
  within range as far as the goal requires, and you never justify the move.
  The stated value settles the parameter only when the goal does not bear on
  it, and "keep near … if free" then says how closely to follow it.
- **FREE** — absent from QUANTITATIVE INPUTS (never specified, or specified
  and later released).  The system's choice within range.

A LOCKED value may move if ANY ONE of these authorises it: the incoming
hand-off (a user permission, or a strategy / recovery directive), the
extraction's DESIGN INTENT section, or an ``(unlocked by user)`` annotation
on the line.  One source is enough — never demand a ritual re-confirmation
of an authorisation the hand-off already carries, and a line saying
"user-locked" is only the default lock.  How FAR: "as needed / only if
necessary" = the smallest change that restores viability; "freely" or
nothing said = as far as the goal requires, bounded by range.
```

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> This is a whole-fragment rewrite of agents/shared/prompt_fragments/value_states.md, and REC-04 (DC Output Inspector) is a second, differently-worded whole-fragment rewrite of the same file, while REC-34 and REC-35 (DCIC) rewrite two of its subsections. The fragment is spliced into the Planner, DCIC, DCII and DCOI, so these four cuts are mutually exclusive; applying more than one either fails to match or double-edits the same rules. Both whole-file versions also drop the FREE-state clause 'unless a directive holds a specific one fixed, which is then treated as LOCKED for that cycle', which survives for the DCII only because its own section 4a restates it.
>
> *Safer:* Apply exactly one value_states.md rewrite (the DCOI's REC-04 preserves slightly more), skip REC-34/REC-35, and add back six words to the FREE bullet: 'a directive holding one fixed makes it LOCKED for that cycle.'

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> REC-04 (DCII) and REC-04 (DCOI) are two different full rewrites of the SAME 2,884-char span — the entirety of agents/shared/prompt_fragments/value_states.md. My verbatim check confirms both anchor at offset 0 and end at the same point. On top of that, REC-34 and REC-35 (DC Input Creator) rewrite two sub-spans inside it (891 and 595 chars). Four cuts, one file, ~4,000 chars of claimed savings against a 2,960-char file.
>
> *Safer:* Group all four as one decision on value_states.md. REC-04 (DCII) is the better base — it keeps the '(unlocked by user)' third authorisation channel and the SOFT-TARGET-marker-is-its-own-authorisation clause; drop REC-04 (DCOI), REC-34 and REC-35 as superseded.

#### DCII-05 · COMPRESS · −1750 chars · risk medium

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* #### 4a. Verbatim entries — the changeability check · *Golden rules:* 2, 6, 7 · *auditor's own id:* REC-05

**Why:** A 2.6k-char decision tree that re-states the LOCKED/SOFT/FREE rules already given under "The three states of a user value" and the CLARIFY-vs-ESCALATE rules already given under "Verdict → routing".

**Risk:** Preserves all four load-bearing pieces: the authority order (directive > extraction > DCIC), soft-target deviation is not a violation, an unauthorised move is a DCIC CLARIFY not a user escalation, and the out-of-range-locked-value ESCALATE exception.

**Cut from** `QUANTITATIVE INPUTS contains two kinds of entry, and the`

**...through** `parameter, its value and its range, so the Planner can revise the
    directive.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
QUANTITATIVE INPUTS holds two kinds of entry.

#### 4a. Entries naming a configurator parameter
Every cycle, decide whether parameters.json was ALLOWED to move each one off
the user's value.  Authority runs **Planner directive > extraction > DCIC
discretion**: a directive to change it authorises the move even over a
user-imposed value; a directive to keep it fixed LOCKS it even if the user
did not; otherwise the three states above decide, and a parameter absent
from QUANTITATIVE INPUTS was never imposed (DCIC's free choice).

An authorised move must still be in range, and must still respect the
directive's "how far" — "as needed" means the smallest viable change, and a
clear overshoot is a REVISE.  A LOCKED value moved without authorisation is
a DCIC-fixable slip: CLARIFY back naming the parameter, the value it must
hold and why; escalate only if you CLARIFYed once and it persists.
Exception — if the value it must hold is itself out of range, no valid set
can satisfy the directive: ESCALATE with the parameter, its value and its
range so the Planner can revise the directive.
```

#### DCII-06 · COMPRESS · −1483 chars · risk medium

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ### 1. Range validation (STRICT — explicit per-parameter check) · *Golden rules:* 1, 5, 7 · *auditor's own id:* REC-06

**Why:** Four paragraphs saying the same thing (check each value individually) plus a template-only "concrete example" with placeholder tokens that teaches nothing.

**Risk:** This is the patch for the real blanket-APPROVE incident, so the per-parameter mandate and the "one incident of it happening" justification are kept in one sentence each — deleting them entirely would risk the regression.

**Cut from** `### 1. Range validation (STRICT — explicit per-parameter check)
You MUST verify every one of the $parameter_count parameters against its allowed`

**...through** `it CLARIFYs back to the DCIC, as does any DCIC-chosen one.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### 1. Range validation (STRICT)
Compare each of the $parameter_count values in parameters.json against its
[min; max] above, one at a time, via ``calculate``.  A blanket "all values
are in bounds" is not a check and has produced false APPROVEs.  The DCIC
now runs its own check; re-do it anyway.  Strictly outside is a hard FAIL
(exactly at min or max is fine) whoever chose the value — never APPROVE one,
not even the user's own number, since the generator fails or degenerates on
out-of-range input.  Route it per "Verdict → routing" below.
```

#### DCII-07 · COMPRESS · −1378 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* #### 4b. Real-world-quantity entries · *Golden rules:* 2, 7 · *auditor's own id:* REC-07

**Why:** Three bullet sub-specs of what the DCIC's hand-off should say, each with its own justification paragraph; the check is one sentence per route.

**Cut from** `#### 4b. Real-world-quantity entries (label is a real-world quantity, unit`

**...through** `parameters with the conversion / rationale included), not an
Orchestrator escalation.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
#### 4b. Entries in a real-world unit no parameter matches directly
The DCIC owed one of three things, stated in its hand-off ``message``: a
documented conversion (the user's quantity, the anchor parameter(s), the
formula, the resulting values), an engineering-judgement choice with a
plausible rationale, or an explicit declination with a reason.  Check the
parameters are consistent with whichever it gave, to a margin justified by
the user's own precision and any rounding the conversion needed.  If
parameters.json quietly ignores the entry and the hand-off never mentions
it, CLARIFY back to the DCIC — DCIC-fixable, not an escalation.
```

#### DCII-08 · COMPRESS · −1330 chars · risk medium

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## Verdict → routing (STRICT — the tool follows your verdict) · *Golden rules:* 2, 6, 10 · *auditor's own id:* REC-08

**Why:** The REVISE / ESCALATE bullet lists re-enumerate cases already decided in §1, §4a, §4b and §5; the range exception is restated for the third time in the prompt.

**Risk:** Keeps the three verdict→tool pairings (the pairing is the only thing code cannot enforce) and the user-provided-out-of-range exception; the per-case enumerations are dropped because each case already routes itself in its own section.

**Cut from** `## Verdict → routing (STRICT — the tool follows your verdict)

Your verdict fixes the tool; the pairing never changes:`

**...through** `slip → CLARIFY, never a user escalation.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Verdict → routing (STRICT — the verdict fixes the tool)

  * **APPROVE → ``call_tool_caller``.**  Every hard check (range +
    feasibility) passes and any upstream-directed change reads as
    authorised and safe.  An approved set — including a retry set — goes to
    the Tool Caller, NEVER the Orchestrator.  Style notes and minor
    engineering opinions do not block APPROVE.
  * **REVISE → ``call_dc_input_creator``** — anything the DCIC can fix
    itself: a value it generated out of range, an arithmetic or mapping
    error, a missing / malformed field, a change with no stated author, an
    unauthorised move of a LOCKED value, an overshot directive.  Name the
    parameter and the reason, never a guessed replacement number.
  * **ESCALATE → ``call_orchestrator``** — a hard blocker needing user
    input, the same problem after one CLARIFY, something infeasible whatever
    the parameters, strong grounds to go BEYOND the Planner's directive, or
    a missing ``Parameters file:`` / ``Extracted inputs file:`` line.

Range exception: an out-of-range value the USER literally provided ESCALATES
only when NOTHING authorises moving it.  A SOFT TARGET marker, a permission
in the hand-off or DESIGN INTENT, or a Planner directive all count — then
CLARIFY back to the DCIC to bring it into range instead of asking the user.
```

#### DCII-09 · COMPRESS · −1280 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## Optional reference: user input images · *Golden rules:* 2, 7, 9 · *auditor's own id:* REC-09

**Why:** Two paragraphs of when-to-look-at-an-image reasoning plus five tool blurbs that duplicate the bound tool schemas; the trigger condition is one clause.

**Cut from** `## Optional reference: user input images
The user may have uploaded reference images (in ``inputs/input_images/``),`

**...through** `call, not one call each.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Optional reference: user input images
Uploaded images live in ``inputs/input_images/``, each with a paired
``<name>_note.txt``.  Consulting one costs turns — do it only when you
suspect the parameters contradict something the user plainly showed (a count
that disagrees, a different design archetype).  Tools:
``list_input_files()``, ``read_input_text(path)``, ``read_image_notes()``,
``view_images(paths)``, ``ocr_regions(image_path, region_ids)`` (pass every
region in ONE call).
```

#### DCII-10 · COMPRESS · −1122 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## Your two primary utility tools (IMPORTANT) · *Golden rules:* 2, 5, 7 · *auditor's own id:* REC-10

**Why:** Three bullets restating "when in doubt re-read" plus a full paragraph per tool that the tool schema already carries.

**Risk:** The stale-cache rule (re-read on the ``(newly written this cycle)`` marker) is the one behavioural steer here and is kept.

**Cut from** `## Your two primary utility tools (IMPORTANT)

You MUST use these tools before forming your opinion.`

**...through** `Do NOT call either tool with a guessed path.  If a path line is
missing from the hand-off, ESCALATE.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Read both files first (MANDATORY)
Neither is loaded automatically.  The DCIC's hand-off carries a
``Parameters file:`` line and an ``Extracted inputs file:`` line; call
``read_parameters`` and ``read_extracted_inputs`` on those exact paths.
Re-read whenever the hand-off says ``(newly written this cycle)`` — the file
was just overwritten and anything you remember is STALE — or whenever you
are not certain your memory still matches disk.  Never guess a path; if a
line is missing, ESCALATE.
```

#### DCII-11 · REPLACE_WITH_EXAMPLES · −1098 chars · risk low

*File:* `DC_prompt_fragments/dc_config/modelling_notes.md` · *Section:* ### Common unit-conversion patterns for this configurator · *Golden rules:* 2, 3 · *auditor's own id:* REC-11

**Why:** Six enumerated conversion recipes are a lookup table for arithmetic the model can do; the two that encode real gotchas (chord-relative percentages, middlePos from the 4 mm root) are worth keeping, the rest are unit algebra.

**Risk:** AFFECTS the DCIC too (the only other agent splicing $modelling_notes). The DCIC is the one that actually performs conversions, so confirm with its auditor before applying.

**Cut from** `### Common unit-conversion patterns for this configurator`

**...through** `algebra, OR fall back to engineering judgement with a stated
rationale.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Unit conversions
When a QUANTITATIVE INPUTS entry is in a non-matching unit, convert from the
parameter list plus unit algebra.  The two that bite: thickness / camber /
high-point are % (or tenths) of that section's OWN chord, and
``middlePos = (r − 4) / (impellerRadius − 4)`` (blade span from the 4 mm
hub, NOT r / impellerRadius).  A stated diameter halves to
``impellerRadius``.  If no conversion is defensible, fall back to
engineering judgement with a stated rationale.
```

#### ⚠️ DCII-12 · COMPRESS · −1050 chars · risk medium

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — "### Routing is a tool call — MANDATORY" · *Golden rules:* 5, 6, 7 · *auditor's own id:* REC-12

**Why:** Three paragraphs and a retired-format warning (``---ROUTING---``) all restate one rule that generic_constraints.md also states; the retired template is dead weight.

**Risk:** AFFECTS ALL 6 CHAIN AGENTS. This is the patch for the real prose-without-routing-call halt, so the mandate and the consequence stay explicit; only the repetition and the obsolete ---ROUTING--- prohibition are removed.

**Cut from** `"### Routing is a tool call — MANDATORY",`

**...through** `"(one or two lines is plenty).",`

**Replace with:**

```
        "### Routing is a tool call — MANDATORY",
        "Every response that ends your turn MUST invoke exactly one of the "
        "routing tools listed above, in the same response where you finish "
        "your work.  Its ``message`` argument IS the hand-off: free-form "
        "prose, no template, carrying the paths and context the recipient "
        "needs and nothing more.  Any text you emit WITHOUT a routing tool "
        "call is silently discarded and the pipeline halts — do not "
        "announce a call instead of making it.  Ordinary response text is "
        "your own scratch reasoning; keep it to a line or two.",
```

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> Four cuts in this set rewrite the identical '### Routing is a tool call — MANDATORY' block in agents/shared/routing.py with four different replacement texts: REC-07 (UII), REC-12 (DCII), REC-17 (Tool Caller) and REC-09 (DCOI). The block is generated in shared code and reaches all six chain agents, so there is exactly one copy to edit. Whichever is applied first leaves the other three unmatchable. On the invariant itself I found no problem: all four replacements keep the mandate, the 'message IS the hand-off' clause and the halt consequence, and the retired ``---ROUTING---`` prohibition is genuinely dead (grep finds no emitter).
>
> *Safer:* Keep exactly one of the four (REC-07's is the tightest that still carries 'invoke it in the same response where you finish your work') and withdraw the other three.

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> Same block of agents/shared/routing.py as REC-07 (UII), REC-17 (TC) and REC-09 (DCOI). Four different replacement texts for one code block that is shared by all six chain agents. Content is safe on its own (it keeps 'silently discarded and the pipeline halts'), but it cannot be applied independently of the other three.
>
> *Safer:* Choose one routing.py rewrite for the whole fleet (REC-17 is the most complete) and drop the other three from the review queue.

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> Four different auditors each propose a DIFFERENT replacement for the identical code block in agents/shared/routing.py lines 248-273 ('### Routing is a tool call — MANDATORY' through '"(one or two lines is plenty).",'). My verbatim check confirms all four anchor to the same 1,658-char span. This is one shared code block spliced into all six chain agents, not four independent cuts — applying any two produces garbage or a silent no-op, and the char-savings claims (933/1050/703/1020) are not additive. All four replacements are syntactically valid Python and none uses {hub}, so no f-prefix is needed.
>
> *Safer:* Present these as ONE decision with four candidate wordings. REC-09 (DCOI) is the tightest that still keeps all three behavioural clauses (mandate, halt consequence, don't-announce-instead-of-calling); pick it and mark the other three superseded.

#### DCII-13 · SCOPE_PER_AGENT · −899 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* <<BSV_ON>> blade-sections visualizer block · *Golden rules:* 8, 9 · *auditor's own id:* REC-13

**Why:** The DCII neither renders nor chooses a render mode — it validates a JSON file and routes; the cheap-sections-render pitch is for the Planner, Tool Caller and DCOI.

**Risk:** The DCII has no blade_sections_visualizer_<agent> overlay file, so this removes only the shared awareness blurb; the eight other agents keep theirs.

**Cut from** `<<BSV_ON>>
$blade_sections_visualizer`

**...through** `<</BSV_ON>><<BSV_OFF>>$blade_sections_visualizer_off<</BSV_OFF>>`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

#### DCII-14 · COMPRESS · −755 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## Your Role · *Golden rules:* 5, 6 · *auditor's own id:* REC-14

**Why:** A five-axis table of contents for the "What to Check" sections that follow verbatim 80 lines later.

**Cut from** `## Your Role
Check the parameters.json the DC Input Creator wrote (you do NOT write or`

**...through** `image-rich requests, important quantitative values).`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Your Role
Judge the parameters.json the DC Input Creator wrote — you never write or
modify it — on four things: every value in range, no contradiction of the
user's stated inputs, no impossible geometry, and every non-user value from
an authorised source.  User-set values are authorised by construction; you
only check their numbers.  If you doubt the extraction itself, re-read the
raw user inputs.
```

#### DCII-15 · COMPRESS · −740 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ### 4. Consistency between parameters.json, extracted_inputs.txt, and the user inputs themselves · *Golden rules:* 6, 7 · *auditor's own id:* REC-15

**Why:** A justification paragraph for why the extraction is authoritative-but-not-final, plus a parenthetical that re-lists the four input tools already listed above.

**Cut from** `### 4. Consistency between parameters.json, extracted_inputs.txt, and the user inputs themselves`

**...through** `above.  Use them sparingly: only when the discrepancy cannot be
resolved from the extraction alone.)`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### 4. Authorisation — was each value allowed to be where it is?
``extracted_inputs.txt`` is your primary record of what the user authorised,
but not the sole source of truth: when a QUANTITATIVE entry conflicts with
the QUALITATIVE prose, or the hand-off cites a user quantity you cannot find
in it, consult the raw user inputs directly.
```

#### DCII-16 · COMPRESS · −620 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — "### How to decide where to route" · *Golden rules:* 10, 7 · *auditor's own id:* REC-16

**Why:** Four decision rules written as full sentences with embedded parentheticals; this is routing protocol the tool schemas already encode, so the prose only needs to be a lookup.

**Risk:** AFFECTS ALL 6 CHAIN AGENTS. Same four branches, same semantics.

**Cut from** `"### How to decide where to route",`

**...through** `f"can fix it, route to the {hub} (ESCALATE).",`

**Replace with:**

```
        "### How to decide where to route",
        "- Your work succeeded and you were not told to report back "
        "(no instruction means continue) → FORWARD to the next agent.",
        f"- You were told to report back or to do X and return → the {hub}.",
        "- The upstream message is ambiguous, missing data, or wrong in a "
        "way the previous agent can fix → CLARIFY back to it.",
        f"- Nothing in the chain can fix it → ESCALATE to the {hub}.",
```

#### DCII-17 · COMPRESS · −600 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — "### Permission / authorisation issues" · *Golden rules:* 5, 7 · *auditor's own id:* REC-17

**Why:** Two paragraphs restating one rule (read the hand-off again before escalating; don't bounce permission questions backward), which generic_constraints.md also states.

**Risk:** AFFECTS ALL 6 CHAIN AGENTS. Keeps the _authorisation_sources(hub) call so the 5-agent topology still renders correctly.

**Cut from** `f"### Permission / authorisation issues → {hub} (not "`

**...through** `"NOT for permission questions.",`

**Replace with:**

```
        f"### Permission / authorisation issues → {hub}",
        "Before escalating over a missing authorisation, re-read the "
        "hand-off and any file it points to.  If it already names an "
        "authorisation that plausibly covers the action — even worded "
        "differently from what you expected — act on it.  If it is "
        f"genuinely missing or ambiguous, ESCALATE to the {hub}: "
        + _authorisation_sources(hub) +
        "  CLARIFY backward only for data / wording / format issues the "
        "previous agent can actually fix.",
```

#### DCII-18 · COMPRESS · −547 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## Hand-off to the Tool Caller (IMPORTANT) · *Golden rules:* 7, 10 · *auditor's own id:* REC-18

**Why:** The two required lines are load-bearing; the surrounding three paragraphs explain why the Tool Caller wants them, which does not change the DCII's behaviour.

**Cut from** `## Hand-off to the Tool Caller (IMPORTANT)
When you FORWARD to the Tool Caller, the ``message`` argument of your`

**...through** `If you CLARIFY back to the DCIC or ESCALATE to the Orchestrator, no
path lines are needed.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Hand-off to the Tool Caller
When you FORWARD, the ``message`` MUST carry both of the DCIC's absolute
paths, preserving the ``(newly written this cycle)`` marker exactly (drop it
only if the DCIC's hand-off lacked it):

    Current attempt: <same path the DCIC gave you>
    Parameters file (newly written this cycle): <Current attempt>/parameters.json

The TC writes mesh + renders into ``Current attempt:``, reads the JSON from
``Parameters file:``, and takes the marker as "your cached copy is stale".
CLARIFY / ESCALATE hand-offs need no path lines.
```

#### DCII-19 · DELETE · −520 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — "### Do not loop — ESCALATE when stuck" · *Golden rules:* 5, 6 · *auditor's own id:* REC-19

**Why:** Stated a third time here — generic_constraints.md already says "DON'T loop … STOP and ESCALATE", and the escalate-when-stuck branch is in "How to decide where to route" directly above.

**Risk:** Only safe if REC-03's replacement (which keeps the DON'T-loop bullet) is applied or generic_constraints.md is left as-is; do not apply this together with a variant of REC-03 that drops that bullet.

**Cut from** `"### Do not loop — ESCALATE when stuck",`

**...through** `"consult another agent, or ask the user.  Never silently loop.",`

**Replace with:** *(nothing — pure deletion)*

#### DCII-20 · COMPRESS · −490 chars · risk low

*File:* `DC_prompt_fragments/tools_config/hard_constraints_tools.md` · *Section:* ### Tool-use hard rules (every agent) · *Golden rules:* 7, 8 · *auditor's own id:* REC-20

**Why:** Same three rules with the justifications and the who-opens-the-attempt aside removed (the latter matters to the DCIC and Orchestrator, not to every agent).

**Risk:** AFFECTS ALL 8 AGENTS. The calculate-everything rule and the append-only attempt rule are kept intact.

**Cut from** `### Tool-use hard rules (every agent)`

**...through** `DCIC opens it; the Orchestrator only as a fallback) — never edit the old
  folder's parameters.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Tool-use hard rules (every agent)
- Read tools take ONLY a path a hand-off label gave you (``Input
  directory:`` / ``Extracted inputs file:`` / ``Parameters file:`` /
  ``Render images:`` / ``Current attempt:``) or an upstream tool's return
  value — never a guessed one.
- Route EVERY arithmetic operation — sums, ratios, conversions, range
  comparisons — through ``calculate``; never mental arithmetic.  Batch this
  turn's expressions into ONE call.
- Attempt folders are append-only: write only into ``Current attempt:``,
  never edit or delete an existing ``parameters.json`` or mesh, and a
  folder's mesh + renders must come from its own parameters.  Re-running
  render/QC on an attempt reuses its renders in place; to build on an old
  set, COPY the values into a NEW attempt.
```

#### DCII-21 · COMPRESS · −490 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ### 5. Appropriateness — your engineering critique · *Golden rules:* 5, 7 · *auditor's own id:* REC-21

**Why:** Two bullets plus a preamble to say one thing: advise via CLARIFY, escalate only to go beyond the Planner. The "notes, not blockers" line is already in §3.

**Cut from** `### 5. Appropriateness — your engineering critique
Beyond authorisation and ranges, judge whether the DCIC's values make`

**...through** `Style / "typical vs unconventional" choices are notes, not blockers.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### 5. Engineering critique (advisory)
Judge whether the values make engineering sense for the user's intent, and
flag known-bad-outcome risks (e.g. a choice that already failed this
session) — for free choices and directive-driven values alike.  The
Planner's plan outranks your opinion: a better value that still fits the
directive → CLARIFY to the DCIC with your suggestion; only STRONG grounds
for going beyond the directive justify escalating so the Planner can rule.
```

#### DCII-22 · COMPRESS · −490 chars · risk low

*File:* `DC_prompt_fragments/dc_config/parameters.md` · *Section:* whole fragment (16-parameter list) · *Golden rules:* 11 · *auditor's own id:* REC-22

**Why:** Pure whitespace/punctuation reformat — every name, unit, semantic note and range is preserved exactly; only the column padding and the em-dash separators go.

**Risk:** AFFECTS ALL 7 AGENTS that splice $parameter_list, each saving ~490 chars. Nothing is removed from the list itself — verify the 16 names and 16 ranges match one-for-one before applying.

**Cut from** `### Global / ring
 1. bladeCount         (integer)              — Number of blades [3; 6]`

**...through** `16. outerAngle      (degrees)                   — Angle of attack [2; 25]`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Global / ring
 1. bladeCount        int  Number of blades [3; 6]
 2. impellerRadius    mm   Outer radius of the impeller ring [60; 80]
 3. impellerThickness mm   Wall thickness of the outer ring [1; 5]
(Ring HEIGHT is not a parameter — derived to fit the outer blade section.)

### Inner blade section
 4. innerThickness % of chord  Profile thickness [3; 24]
 5. innerMaxPos    int, tenths of chord  Chordwise position of max thickness [2; 8]
 6. innerCamber    % of chord  Profile camber [0; 9]
 7. innerChord     mm  Chord length [3; 11]
 8. innerAngle     deg  Angle of attack [2; 25]

### Middle blade section
 9. middlePos   fraction of blade span  0 = root (hub, r = 4 mm), 1 = tip; radius = 4 + middlePos·(impellerRadius − 4) mm [0.3; 0.7]
10. middleChord  mm  Chord length [10; 30]
11. middleAngle  deg  Angle of attack [2; 25]

### Outer blade section
12. outerThickness % of chord  Profile thickness [3; 24]
13. outerMaxPos    int, tenths of chord  Chordwise position of max thickness [2; 8]
14. outerCamber    % of chord  Profile camber [0; 9]
15. outerChord     mm  Chord length [10; 30]
16. outerAngle     deg  Angle of attack [2; 25]
```

#### DCII-23 · COMPRESS · −478 chars · risk medium

*File:* `DC_prompt_fragments/dc_config/hard_constraints_dc.md` · *Section:* ### Domain hard rules (every agent) · *Golden rules:* 2, 3 · *auditor's own id:* REC-23

**Why:** Two long enumerations (11 mesh post-processing verbs, 12 analysis types) collapse to canonical examples plus the general principle.

**Risk:** AFFECTS ALL 8 AGENTS. Trimming the enumerations relies on the model generalising "no post-processing" and "no analysis the system cannot perform"; if a specific refusal regresses (e.g. an agent offering an STL export), restore that one word rather than the whole list.

**Cut from** `### Domain hard rules (every agent)`

**...through** `inspection and say so plainly.`

**Replace with:**

```
### Domain hard rules (every agent)
- A design is expressible ONLY as the $parameter_count named parameters.
  Anything outside that list (hub_radius, fillet_radius, tip_clearance, any
  "supplemental" parameter) does not exist — reject it.  Geometry changes
  only by changing those parameters and regenerating via DC Input Creator →
  Tool Caller: there is no mesh editing and no post-processing of any kind
  (booleans, welding, remeshing, hole filling, fillets, supports, …).
- The system cannot offer performance or structural analysis (thrust, flow,
  pressure, efficiency, CFD, FEA, stress, material, tolerance), alternative
  formats (STL, STEP, IGES, …), extra camera angles, cross-sections, or
  higher-resolution renders.  The only mesh metrics are watertightness,
  volume and degenerate-face count; when mesh checks are disabled, rely on
  visual inspection and say so plainly.
```

#### DCII-24 · COMPRESS · −362 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## Output Format · *Golden rules:* 4, 11 · *auditor's own id:* REC-24

**Why:** A five-heading template immediately disclaimed as "not a fixed template"; the content it asks for is exactly what the checks above already produce.

**Cut from** `## Output Format
Write your validation assessment in the ``message`` argument of the`

**...through** `needed (identify the parameter and the reason, not a guessed
    numeric replacement).`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Output Format
Put your assessment in the routing tool's ``message``: short plain prose
covering range validation, any real contradiction with the user's inputs,
the authorship and authorisation of any upstream-directed change, hard
engineering blockers, and your recommendation (naming the parameter and the
reason, never a guessed replacement number).  No fixed template.
```

#### DCII-25 · COMPRESS · −220 chars · risk low

*File:* `agents/shared/prompt_fragments/routing_dc_input_inspector.md` · *Section:* ### Available routing tools · *Golden rules:* 6, 9 · *auditor's own id:* REC-25

**Why:** Duplicates the "Verdict → routing" section of the DCII prompt almost verbatim; the roster only needs the tool names and one clause each.

**Risk:** DCII-only fragment — no other agent reads it.

**Cut from** `### Available routing tools
- ``call_tool_caller(message)`` — FORWARD when ``parameters.json```

**...through** `that no chain agent can fix.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Available routing tools
- ``call_tool_caller(message)`` — FORWARD: every check passed.
- ``call_dc_input_creator(message)`` — CLARIFY: the DCIC can fix it itself.
- ``call_orchestrator(message)`` — ESCALATE: nothing in the chain can.
```

#### DCII-26 · COMPRESS · −206 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* Two self-checks before you route · *Golden rules:* 5, 6 · *auditor's own id:* REC-26

**Why:** Both self-checks restate rules given two paragraphs earlier (APPROVE→call_tool_caller) and in §1 (per-parameter comparison).

**Risk:** The APPROVE→call_tool_caller mismatch is named a recurring failure mode, so the self-check is kept — just once, in one sentence.

**Cut from** `Two self-checks before you route:`

**...through** `single out-of-range value makes APPROVE invalid.`

**Replace with:**

```
Before routing, confirm both: an APPROVE verdict MUST call
``call_tool_caller`` (a recurring failure mode), and you compared each of
the $parameter_count parameters against its own [min; max] rather than
asserting it from memory.
```

#### DCII-27 · COMPRESS · −186 chars · risk low

*File:* `DC_prompt_fragments/dc_config/modelling_notes.md` · *Section:* opening bullets (NACA / middlePos / integer types) · *Golden rules:* 6, 7 · *auditor's own id:* REC-27

**Why:** Tightens the middlePos explanation (three restatements of the same formula) and folds in the two production gotchas — percentages are of the section's OWN chord, and the middle section has no shape parameters of its own.

**Risk:** AFFECTS the DCIC too. This ADDS two facts that came out of real bugs while still ending up shorter; if the owner prefers a pure cut, drop the last clause of the middlePos bullet.

**Cut from** `- Blade profiles are NACA-style airfoils parameterised by thickness, camber,`

**...through** `other parameters are floating-point numbers.`

**Replace with:**

```
- Blade profiles are NACA-style airfoils set by thickness, camber and
  high-point; high-point is in tenths of chord (3 = 30% chord from the
  leading edge).  Thickness and camber are percentages of that SECTION'S OWN
  chord, so a pinned chord caps their absolute size.
- ``middlePos`` is a fraction of the BLADE SPAN from the root: actual radius
  = ``4 + middlePos·(impellerRadius − 4)`` mm, NOT
  ``middlePos × impellerRadius``.  The middle section has no shape
  parameters of its own — its profile is a weighted average of inner and
  outer, so middlePos alone cannot reshape it.
- bladeCount, innerMaxPos and outerMaxPos are integers; the rest are floats.
```

#### DCII-28 · MERGE · −142 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## End-of-session feedback message (read-only) · *Golden rules:* 7, 11 · *auditor's own id:* REC-28

**Why:** Four lines defining "your scope" that merely re-list the checks the whole prompt describes.

**Cut from** `## End-of-session feedback message (read-only)

$eos_feedback_intro`

**...through** `$eos_feedback_outro`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## End-of-session feedback (read-only)
$eos_feedback_intro  Your scope: whether your APPROVEs were sound, your
REVISEs / ESCALATEs warranted, and your range / lock / feasibility checks
caught what they should.  $eos_feedback_outro
```

#### DCII-29 · COMPRESS · −91 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ### 2. Consistency with the user's stated inputs · *Golden rules:* 7 · *auditor's own id:* REC-29

**Why:** Minor tightening; the rule is one sentence.

**Cut from** `### 2. Consistency with the user's stated inputs
Explicit values the user provided (in the extraction or in an annotated`

**...through** `intent or functional requirement.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### 2. Consistency with the user's stated inputs
Explicit user values are intentional — never request justification for them.
Flag only a value that clearly contradicts a STATED design intent or
functional requirement.
```

</details>

<details><summary><b>Proposed shape of the shrunk prompt</b></summary>

```
DC Input Inspector — shrunk prompt skeleton (~2,500 tok assembled)

  (opening line: "You are the DC Input Inspector for a $domain_description.")   ~20 tok
  ## Your Role                                                    ~90 tok   [REC-14]
  ## Parameters and Allowed Ranges  ($parameter_list, compacted)  ~280 tok   [REC-22]
  ## Modelling Notes  ($modelling_notes, compressed)              ~240 tok   [REC-11, REC-27]
  ## Optional reference: user input images                        ~110 tok   [REC-09]
  ## Sketch handling                                               ~85 tok   [REC-01]
  ## Read both files first (MANDATORY)                            ~120 tok   [REC-10]
  ## The three states of a user value ($value_states, compressed) ~250 tok   [REC-04]
  ## What to Check
      ### 1. Range validation (STRICT)                            ~130 tok   [REC-06]
      ### 2. Consistency with the user's stated inputs             ~50 tok   [REC-29]
      ### 3. Engineering feasibility (hard blockers only)          ~80 tok   [REC-02]
      ### 4. Authorisation — was each value allowed to be there?
            preamble                                              ~80 tok   [REC-15]
            #### 4a. Entries naming a configurator parameter      ~250 tok   [REC-05]
            #### 4b. Entries in an unmatched real-world unit      ~150 tok   [REC-07]
      ### 5. Engineering critique (advisory)                      ~105 tok   [REC-21]
  ## Output Format                                                 ~80 tok   [REC-24]
  ## Verdict → routing (STRICT)                                   ~270 tok   [REC-08, REC-26]
  ## Hand-off to the Tool Caller                                  ~140 tok   [REC-18]
  ## End-of-session feedback (read-only)                           ~60 tok   [REC-28]
  ## Hard constraints — generic ($hard_constraints_generic)       ~380 tok   [REC-03]
  ## Hard constraints — DC-specific ($hard_constraints_dc)        ~200 tok   [REC-23]
  ## Hard constraints — tool-specific ($hard_constraints_tools)   ~200 tok   [REC-20]
  {routing_instructions}  (position + decide + roster + mandate)  ~420 tok   [REC-12,16,17,19,25]
  (blade-sections visualizer block: REMOVED)                        0 tok   [REC-13]

  TOTAL ≈ 3,690 tok of listed sections — the overlap is because several
  estimates above count the same shared fragment once each; measured
  assembled result after all 29 cuts ≈ 9,990 chars ≈ 2,500 tok.
```

</details>

**Auditor notes.** MEASUREMENT. Assembled DCII = agents/dc_input_inspector/prompt.md (19,274 chars) + fragments actually spliced under the measured config (parameters 1,609; modelling_notes 2,660 SPLICED TWICE = 5,320; sketch_handling 8,831; sketch_notes 1,762; value_states 2,885; generic_constraints 3,429; hard_constraints_dc 1,268; hard_constraints_tools 1,280; blade_sections_visualizer 758; eos intro/outro ~250) + the runtime {routing_instructions} block (~4,300 incl. routing_dc_input_inspector.md 569). RAG is off, so the <<HAS_DBA>> block contributes nothing. Sum of chars_removed across the 29 cuts = 35,792 (≈8,950 tok), landing the prompt at ≈2,500 tok. Every chars_removed is (measured byte range) − (len of the replacement I wrote), not an estimate.

THE FIVE BIGGEST LEVERS, in order:
 1. REC-01 (10,363 chars, 29% of the whole prompt in one edit) — the DCII splices the full sketch corpus written for the UII and DCOI. It is by far the single best cut and it touches nobody else.
 2. REC-02 — $modelling_notes is spliced TWICE (prompt.md line 26 and again parenthetically at line 143). This is a plain bug, worth 2,656 chars on its own; apply it regardless of what you think of the surrounding compression.
 3. REC-03 / REC-04 / REC-20 / REC-22 / REC-23 / REC-27 are SHARED-fragment edits: each also shrinks 4-8 other agents by the same amount. REC-22 alone is ~490 chars × 7 agents. Coordinate these with the other agents' auditors so they aren't proposed twice.
 4. REC-12 / REC-16 / REC-17 / REC-19 edit agents/shared/routing.py string literals, which changes ALL SIX chain agents' routing sections. If you would rather not touch code in this pass, skip them — they total 2,790 chars and the DCII still lands near 3,200 tok without them.
 5. REC-05 + REC-08 together remove ~3,080 chars of decision-tree prose that is stated three times (in §1, §4a and "Verdict → routing").

WHAT I DELIBERATELY DID NOT CUT:
 - The 16-parameter list itself. REC-22 only reformats it — same 16 names, 16 ranges, and every semantic note including the middlePos formula.
 - The per-parameter range mandate (§1) and the sentence saying blanket assertions produced false APPROVEs. That is the DCII's whole reason to exist and is a documented production failure; I compressed 1,863 chars to 380 but kept both the mandate and the one-clause reason.
 - "Routing is a tool call — MANDATORY" and the consequence clause ("text without a routing tool call is discarded and the pipeline halts"). Kept in both generic_constraints.md and routing.py — that is the one place I accepted duplication, because the halt is unrecoverable.
 - The STANDING DIRECTIVES copy-verbatim rule, kept word-for-word: it is the counter-measure to the real bug where a directive restating a SUBSET of authorised parameters silently revoked a chord authorisation.
 - The "never describe images you did not load" principle survives as generic_constraints' "DON'T state an observation you cannot source to a tool result".
 - The out-of-range-LOCKED-value ESCALATE exception in §4a, and the user-provided-out-of-range exception under "Verdict → routing". These are the two places where the obvious action is wrong, so they earn their words.

A DEEPER CUT I DID NOT PROPOSE. Axis 5 (extraction fidelity — the DCII re-reading raw user inputs and images to second-guess the UII) costs ~500 chars after my compression (REC-09 + the axis-5 clauses in REC-14/REC-15) and arguably belongs to the UII, not to a parameter validator sitting two agents downstream. Dropping it entirely would take the DCII to ~2,350 tok and remove four tool schemas (list_input_files / read_input_text / read_image_notes / view_images / ocr_regions ≈ 700 tool-schema tok). I left it in because it looks like a deliberate design decision rather than accretion — but it is the obvious next cut if you want to go under 2,500.

TOOL-SCHEMA NOTE (golden rule 9). The DCII carries 13 tool schemas / 2,104 tok. Applying REC-13 makes the blade-sections tooling unreferenced; the five user-input tools are only referenced by the axis-5 text above. If both go, the DCII needs 6 tools (read_parameters, read_extracted_inputs, calculate, and the three call_* routing tools) and its schema budget drops to roughly 900 tok. That is a bigger saving than several of the prose cuts and it removes ambiguous decision points, but it is a code change in agents/dc_input_inspector/dc_input_inspector.py (set_routing_tools / build_user_inputs_tools) rather than a prompt edit, so it is out of scope for this cut list.

APPLICATION ORDER. REC-19 (delete the routing "Do not loop" block) assumes REC-03's replacement keeps the DON'T-loop bullet — apply REC-03 first, or apply neither. Everything else is independent: each quote_start/quote_end pair was taken byte-for-byte from the file and no two cuts overlap.

---

### 4.7 Tool Caller — 5,004 → ~2,250 tok

| ID | action | section | −chars | rules | risk | what |
|---|---|---|---:|---|---|---|
| **TC-14** | COMPRESS | ## Active mesh-check backend: PyVista / VTK (renders via pyr | 1585 | 3,7 | low | Backend internals (pyvista.read, MultiBlock merging, n_open_edges + is_manifold, the 1e-10 mm² threshold, divergence-theorem volume) are reference material the agent never reasons about — it just reports the numbers the tool returns. |
| **TC-01** | DELETE | ## Utility tools: list_attempts() and read_attempt(n, file) | 1087 | 3,6,9 | low | Pure duplicate of items 3 and 4 of $tool_inventory 100 lines earlier, plus a don't-loop rule the routing block and generic constraints both already state. |
| ⚠️ **TC-16** | DELETE | routing_instructions() → ### Permission / authorisation issu | 1070 | 1,2,10 | medium | A 1.1k-char incident patch (agents bouncing ritual re-confirmations backward) whose entire behavioural content is one rule; REC-19 folds that rule into the route-decision bullets. |
| **TC-02** | COMPRESS | ## State THIS CYCLE clearly (IMPORTANT) | 1029 | 2,7,11 | low | The fresh-vs-reused signal is load-bearing for the DCOI, but it is stated three times with three sample phrasings and a justification paragraph; one statement plus the tool's own marker strings carries it. |
| **TC-03** | SCOPE_PER_AGENT | ## Hard constraints — DC-specific | 1024 | 8,3 | medium | The 1.2k-char domain constitution is written for agents that PROPOSE designs; the Tool Caller only executes, so all it needs is the one-line invariant that the parameters are the only levers and the only metrics are the three mesh checks. |
| **TC-15** | COMPRESS | ## Active render / mesh-check backend: trimesh + pyrender | 950 | 3,7 | low | Same as REC-14 for the currently active backend: how watertightness/volume/degenerate faces are computed does not change what the Tool Caller does with the reported values. |
| **TC-04** | DELETE | (trailing <<BSV_ON>> block, above {routing_instructions}) | 762 | 6,8 | low | The shared blade-sections awareness fragment (why sections are cheap, that they can be the final deliverable) is planner-level reasoning; the Tool Caller only needs the one-line 'call render_blade_sections when asked' rule it already has near the top, and its per-agent overlay file is empty. |
| ⚠️ **TC-17** | COMPRESS | routing_instructions() → ### Routing is a tool call — MANDAT | 703 | 2,5,7 | medium | Three paragraphs saying the same thing four ways, including a ban on a '---ROUTING---' template that has been retired; the invariant (no routing call = pipeline halts) is kept verbatim in force. |
| **TC-05** | DELETE | ## End-of-session feedback message (read-only) | 640 | 8,7 | medium | Read-only session-end plumbing that changes nothing the Tool Caller does during a run; the agent's history is what the Database Handler interviews anyway. |
| **TC-06** | COMPRESS | ## Range check before you generate (HARD — independent of up | 632 | 7,5 | low | Keeps every behavioural clause (per-value comparison, STOP, route back quoting param/value/range, never clip) and drops only the two paragraphs explaining WHY the check is redundant. |
| **TC-20** | COMPRESS | ### Tool-use hard rules (every agent) | 574 | 2,6,7 | low | Keeps all three rules (no guessed paths, all arithmetic via calculate, attempt folders append-only) and drops the justification clauses and the render-reuse sentence that the Tool Caller prompt states itself. |
| **TC-07** | COMPRESS | ## Attempt folder (IMPORTANT — read this before any tool cal | 467 | 5,6,7 | low | Same three rules (only-writable-folder, escalate-if-missing, reuse-is-fine) in half the words; the append-only detail is already in $hard_constraints_tools. |
| ⚠️ **TC-21** | COMPRESS | ### What every agent … MUST NOT do (DON'Ts) | 446 | 5,6,7 | medium | 680 chars restating the routing-is-a-tool-call mandate that routing_instructions() already delivers in full; the invariant is preserved in three lines. |
| **TC-08** | COMPRESS | ## HARD LIMITS — Do NOT | 415 | 2,5,6 | low | The enumerated forbidden mesh operations duplicate $hard_constraints_dc and 'don't invent tools' duplicates $hard_constraints_generic; the two clauses that are genuinely the Tool Caller's (no option menus, no self-invented tweaks) survive. |
| **TC-09** | COMPRESS | ## Data Flow and reporting file paths (IMPORTANT) | 404 | 5,7,11 | low | The three labels and the 'copy verbatim' rule are the Tool Caller's core output contract and stay; the restatement of them a second time in prose is dropped. |
| **TC-22** | DELETE | ### What every agent … MAY do (DOs) | 396 | 6,10 | low | Exact duplicate of routing_instructions()'s '### How to decide where to route', which every chain agent already receives with its own next/previous agents named. |
| **TC-32** | COMPRESS | ### Domain hard rules (every agent) | 386 | 2,7 | low | Collapses two long DON'T bullets (post-processing list + unsupported-analysis list) into one, keeping every canonical example that names a real past failure. |
| **TC-18** | COMPRESS | routing_instructions() → ### Do not loop — ESCALATE when stu | 370 | 2,7 | low | Four sentences of elaboration around a one-sentence rule that is ALSO stated in generic_constraints.md; one statement in one place is enough. |
| **TC-10** | COMPRESS | ## Loading parameters (IMPORTANT) | 340 | 7,11 | low | Keeps the whole mechanism (read the labelled path verbatim, then one call that meshes and renders) without the narration of what the tool returns. |
| **TC-11** | COMPRESS | **When to (re-)call ``read_parameters``** | 306 | 2,5 | low | Two bullets plus a repeated no-guessed-path warning collapse into one sentence with the same two triggers. |
| **TC-23** | DELETE | ### What every agent … MUST NOT do (DON'Ts) | 248 | 6,10 | low | Third statement of the same permission-routing rule (routing block + REC-19 bullet already carry it), and it hard-codes 'Orchestrator' where the routing block is topology-aware. |
| **TC-24** | COMPRESS | ### What every agent … MAY do (DOs) | 246 | 2,7 | medium | The verbatim-relay invariant is load-bearing (standing directives are a real feature) but does not need five enumerated forbidden mutations plus a why-clause. |
| **TC-12** | COMPRESS | <<BSV_ON>> Render type — sections vs the full 3D | 218 | 7,6 | low | Keeps the branch rule; drops the restatement of the default branch and the pointer to a section REC-04 deletes. |
| **TC-25** | COMPRESS | ### What every agent … MUST NOT do (DON'Ts) | 180 | 2,6 | low | Two rules, two clauses; the escalation rationale is already stated by the do-not-loop rule. |
| **TC-26** | DELETE | ### What every agent … MUST NOT do (DON'Ts) | 175 | 6 | low | Verbatim duplicate of the routing block's '### Do not loop' section (kept, compressed, in REC-18). |
| **TC-31** | COMPRESS | (whole file — Tool Caller only) | 149 | 9,7 | low | Tightens the four tool blurbs; drops the 'when mesh checks are enabled' aside and a cross-reference to view_images, a tool the Tool Caller does not have. |
| **TC-27** | COMPRESS | ### What every agent … MAY do (DOs) | 115 | 6,7 | low | The free-form-prose instruction is repeated verbatim in the routing block; only the authorship rule is unique here, so keep just that. |
| ⚠️ **TC-28** | DELETE | ### What every agent … MAY do (DOs) | 82 | 4 | medium | Restates default model behaviour for an English-language system prompt. |
| **TC-19** | MERGE | routing_instructions() → ### How to decide where to route | 60 | 2,6,11 | low | Same four routing decisions in terser bullets, and absorbs the one surviving rule from the deleted permission section so REC-16 loses nothing. |
| **TC-13** | COMPRESS | ## Your Role | 56 | 4,11 | low | Trims filler around the tool list. |
| **TC-29** | MERGE | ### What every agent … MAY do (DOs) | 53 | 4,6 | low | First bullet is near-default behaviour; merged into the exhaustive-tool-list bullet that actually steers. |
| **TC-30** | COMPRESS | ### What every agent … MUST NOT do (DON'Ts) | 42 | 2 | low | Same rule, shorter enumeration. |

<details><summary><b>Full text of each change</b></summary>

#### TC-14 · COMPRESS · −1585 chars · risk low

*File:* `DC_prompt_fragments/tools_config/render_check_library/pyvista.md` · *Section:* ## Active mesh-check backend: PyVista / VTK (renders via pyrender) · *Golden rules:* 3, 7 · *auditor's own id:* REC-14

**Why:** Backend internals (pyvista.read, MultiBlock merging, n_open_edges + is_manifold, the 1e-10 mm² threshold, divergence-theorem volume) are reference material the agent never reasons about — it just reports the numbers the tool returns.

**Risk:** Only ONE of the two render_check fragments is spliced per session, so this saving is NOT additive with REC-15; it applies when GEOMETRY/render library = pyvista.

**Cut from** `## Active mesh-check backend: PyVista / VTK (renders via pyrender)`

**...through** `All three PNGs are 800×600 — identical pipeline to the trimesh
  backend.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Active mesh-check backend: PyVista / VTK (renders via pyrender)
The metric checks of ``generate_and_render_propeller`` run on PyVista (VTK)
this session; the three 800×600 renders come from the same pyrender pipeline as
the trimesh backend.  The contract is backend-independent — report the tool's
numbers as returned.  A non-positive volume means inverted normals and the tool
flags it as a WARNING.
```

#### TC-01 · DELETE · −1087 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* ## Utility tools: list_attempts() and read_attempt(n, file) · *Golden rules:* 3, 6, 9 · *auditor's own id:* REC-01

**Why:** Pure duplicate of items 3 and 4 of $tool_inventory 100 lines earlier, plus a don't-loop rule the routing block and generic constraints both already state.

**Cut from** `## Utility tools: list_attempts() and read_attempt(n, file)`

**...through** `retry strategies — strategy decisions belong to the Planner.`

**Replace with:** *(nothing — pure deletion)*

#### ⚠️ TC-16 · DELETE · −1070 chars · risk medium

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() → ### Permission / authorisation issues · *Golden rules:* 1, 2, 10 · *auditor's own id:* REC-16

**Why:** A 1.1k-char incident patch (agents bouncing ritual re-confirmations backward) whose entire behavioural content is one rule; REC-19 folds that rule into the route-decision bullets.

**Risk:** Apply together with REC-19, which carries the surviving permission bullet (re-read the hand-off first; authorisations come from user/Planner/hub; never CLARIFY backward for permission). Shared by all 6 chain agents — also delete the adjacent empty-string list entry.

**Cut from** `f"### Permission / authorisation issues → {hub} (not "`

**...through** `"NOT for permission questions.",`

**Replace with:** *(nothing — pure deletion)*

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> This DELETES the '### Permission / authorisation issues' block from agents/shared/routing.py, which is spliced into all six chain agents. Two problems. (1) Its own risk note says 'Apply together with REC-19, which carries the surviving permission bullet' — REC-19 is not in this review set, so as briefed the owner can apply this alone. (2) The rule it removes — 're-read the incoming hand-off (and any file it points to) ONCE MORE before escalating; if it already names an authorisation that plausibly covers the action, act on it; do NOT bounce back for a ritual re-confirmation' — survives elsewhere ONLY in value_states.md ('never demand a "ritual re-confirmation" of an authorisation the hand-off already carries'), and value_states.md is spliced into dc_input_creator, dc_input_inspector, dc_output_inspector and planner only. For the User Input Inspector and the Tool Caller — two of the six agents this code feeds — deletion leaves no statement of it anywhere. It also collides head-on with REC-17 (User Input Inspector), which COMPRESSES the identical block rather than deleting it.
>
> *Safer:* Apply REC-17 (UII) instead of this, or if deleting, keep two lines in the file: "Before escalating a missing authorisation, re-read the hand-off and any file it points to — one that plausibly covers the action is enough, no re-confirmation round-trip.  If it is truly absent, ESCALATE to the {hub}; the previous agent cannot grant permission."

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> A full DELETE of the '### Permission / authorisation issues' block in agents/shared/routing.py (lines 229-246), which is injected into all six chain agents. Its own risk_note says to 'apply together with REC-19, which carries the surviving permission bullet' - REC-19 is not in this batch, and REC-17 (User Input Inspector) proposes to COMPRESS the same block, so the two cuts are mutually exclusive. Applied alone, the rule that dies everywhere is 'READ THE INCOMING HAND-OFF ... ONCE MORE before escalating; if the hand-off already names an authorisation that plausibly covers the action - even if the wording differs from a template you expected - act on it.' The nearest surviving copy ('never demand a ritual re-confirmation') is in value_states.md, which is spliced only into the Planner, DCIC, DCII and DCOI - the Tool Caller and UII would have nothing.
>
> *Safer:* Prefer REC-17's compression over this delete; if deleting, add one line to the route-decision block: 'Before escalating for permission, re-read the hand-off and any file it points to - act on an authorisation that plausibly covers the action; the previous agent cannot grant one.'

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> This DELETEs agents/shared/routing.py lines 229-246 (the '### Permission / authorisation issues' block); REC-17 (User Input Inspector) COMPRESSes the exact same span. Both anchor verbatim to the same region — mutually exclusive, and the owner reviewing them separately sees two independent-looking wins on one block. Two secondary mechanics notes on the DELETE: it orphans `_authorisation_sources()` (routing.py:49) — line 243 is its only call site — leaving dead code; and that helper is the one piece of routing boilerplate that adapts to SYSTEM_TOPOLOGY (it collapses three grantors to two for the 5-agent Conductor), so deleting the block silently drops the topology-5 wording too.
>
> *Safer:* Take REC-17 (compress) instead of REC-16 (delete): same span at ~470 chars, keeps the anti-ritual-re-confirmation rule, and keeps `_authorisation_sources(hub)` called so the 5-agent topology text stays correct.

#### TC-02 · COMPRESS · −1029 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* ## State THIS CYCLE clearly (IMPORTANT) · *Golden rules:* 2, 7, 11 · *auditor's own id:* REC-02

**Why:** The fresh-vs-reused signal is load-bearing for the DCOI, but it is stated three times with three sample phrasings and a justification paragraph; one statement plus the tool's own marker strings carries it.

**Cut from** `## State THIS CYCLE clearly (IMPORTANT)`

**...through** `re-loading conservatively; precise wording saves tool calls.`

**Replace with:**

```
## Say what is NEW this cycle
The DC Output Inspector keeps prior renders and QC reports in its
history, so state in your own words which artefacts are fresh and which
were carried over — the mesh tool's return text marks each ("Mesh saved
…" vs "Reused existing mesh …", "Renders saved:" vs "Renders already
present — reused in place") — and report only the CURRENT quality
numbers.  Precise wording saves the DCOI a re-load; vague wording costs
one.
```

#### TC-03 · SCOPE_PER_AGENT · −1024 chars · risk medium

*File:* `agents/tool_caller/prompt.md` · *Section:* ## Hard constraints — DC-specific · *Golden rules:* 8, 3 · *auditor's own id:* REC-03

**Why:** The 1.2k-char domain constitution is written for agents that PROPOSE designs; the Tool Caller only executes, so all it needs is the one-line invariant that the parameters are the only levers and the only metrics are the three mesh checks.

**Risk:** Removes the explicit 'reject invented parameters (hub_radius, fillet_radius, …)' list from this agent; the replacement keeps the general principle and the Tool Caller never authors parameters, but if a hand-off ever smuggles an extra key the TC will now rely on the range check rather than a named ban.

**Cut from** `## Hard constraints — DC-specific`

**...through** `$hard_constraints_dc`

**Replace with:**

```
The $parameter_count parameters above are the ONLY design levers: geometry changes
only by changing them and regenerating.  There is no mesh editing or
post-processing, and the only mesh metrics are watertightness, volume and
degenerate-face count.
```

#### TC-15 · COMPRESS · −950 chars · risk low

*File:* `DC_prompt_fragments/tools_config/render_check_library/trimesh.md` · *Section:* ## Active render / mesh-check backend: trimesh + pyrender · *Golden rules:* 3, 7 · *auditor's own id:* REC-15

**Why:** Same as REC-14 for the currently active backend: how watertightness/volume/degenerate faces are computed does not change what the Tool Caller does with the reported values.

**Risk:** Keeps the one behaviour-changing fact (non-positive volume = inverted normals, surfaced as a WARNING) so the agent still reads the return text correctly.

**Cut from** `## Active render / mesh-check backend: trimesh + pyrender`

**...through** `background, smooth shading, three directional lights).  All three
  PNGs are 800×600.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Active render / mesh-check backend: trimesh + pyrender
The render+check step of ``generate_and_render_propeller`` runs on trimesh +
pyrender this session.  The contract is backend-independent (same three 800×600
PNGs, same metrics); report the tool's numbers as returned.  A non-positive
volume means inverted normals and the tool flags it as a WARNING.
```

#### TC-04 · DELETE · −762 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* (trailing <<BSV_ON>> block, above {routing_instructions}) · *Golden rules:* 6, 8 · *auditor's own id:* REC-04

**Why:** The shared blade-sections awareness fragment (why sections are cheap, that they can be the final deliverable) is planner-level reasoning; the Tool Caller only needs the one-line 'call render_blade_sections when asked' rule it already has near the top, and its per-agent overlay file is empty.

**Risk:** Keep REC-12's replacement, which retains the tool name render_blade_sections — otherwise the tool would be bound but never named in the prompt.

**Cut from** `<<BSV_ON>>
$blade_sections_visualizer`

**...through** `<</BSV_ON>><<BSV_OFF>>$blade_sections_visualizer_off<</BSV_OFF>>`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

#### ⚠️ TC-17 · COMPRESS · −703 chars · risk medium

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() → ### Routing is a tool call — MANDATORY · *Golden rules:* 2, 5, 7 · *auditor's own id:* REC-17

**Why:** Three paragraphs saying the same thing four ways, including a ban on a '---ROUTING---' template that has been retired; the invariant (no routing call = pipeline halts) is kept verbatim in force.

**Risk:** This is the anti-halt patch. The replacement keeps the mandate, the consequence, and 'invoke it in the same response' — the three clauses that actually change behaviour. Shared by all 6 chain agents.

**Cut from** `"### Routing is a tool call — MANDATORY",`

**...through** `"(one or two lines is plenty).",`

**Replace with:**

```
        "### Routing is a tool call — MANDATORY",
        "Every response that ends your turn MUST invoke exactly one of "
        "the routing tools listed above.  Prose emitted without a routing "
        "call is discarded and the pipeline halts, however complete your "
        "reasoning looks — so invoke the tool in the same response where "
        "you finish your work rather than announcing it.",
        "",
        "The tool's ``message`` argument IS the hand-off: free-form prose "
        "(no template, no option menus) carrying what the recipient "
        "genuinely needs — the paths their tools require, what changed and "
        "why, the authorship of any non-user-authored value — and nothing "
        "more.  Your own response text is private reasoning; keep it to a "
        "line or two.",
```

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> Third of four competing rewrites of the same routing.py '### Routing is a tool call — MANDATORY' block (see REC-12). No invariant is lost by this text on its own — the mandate, consequence and same-response clause all survive — but it cannot be applied independently of REC-07, REC-12 and REC-09.
>
> *Safer:* Withdraw as a duplicate of REC-07 (User Input Inspector).

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> Four different auditors each propose a DIFFERENT replacement for the identical code block in agents/shared/routing.py lines 248-273 ('### Routing is a tool call — MANDATORY' through '"(one or two lines is plenty).",'). My verbatim check confirms all four anchor to the same 1,658-char span. This is one shared code block spliced into all six chain agents, not four independent cuts — applying any two produces garbage or a silent no-op, and the char-savings claims (933/1050/703/1020) are not additive. All four replacements are syntactically valid Python and none uses {hub}, so no f-prefix is needed.
>
> *Safer:* Present these as ONE decision with four candidate wordings. REC-09 (DCOI) is the tightest that still keeps all three behavioural clauses (mandate, halt consequence, don't-announce-instead-of-calling); pick it and mark the other three superseded.

#### TC-05 · DELETE · −640 chars · risk medium

*File:* `agents/tool_caller/prompt.md` · *Section:* ## End-of-session feedback message (read-only) · *Golden rules:* 8, 7 · *auditor's own id:* REC-05

**Why:** Read-only session-end plumbing that changes nothing the Tool Caller does during a run; the agent's history is what the Database Handler interviews anyway.

**Risk:** Post-session DH answers from this agent lose the 'treat orchestrator feedback as ground truth' hint. If the owner wants it, keep one line: '$eos_feedback_intro  Treat it as ground truth in your later Database-Handler answers.'

**Cut from** `## End-of-session feedback message (read-only)`

**...through** `$eos_feedback_outro`

**Replace with:** *(nothing — pure deletion)*

#### TC-06 · COMPRESS · −632 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* ## Range check before you generate (HARD — independent of upstream) · *Golden rules:* 7, 5 · *auditor's own id:* REC-06

**Why:** Keeps every behavioural clause (per-value comparison, STOP, route back quoting param/value/range, never clip) and drops only the two paragraphs explaining WHY the check is redundant.

**Cut from** `## Range check before you generate (HARD — independent of upstream)`

**...through** `verifies only that the fields are present and numeric.`

**Replace with:**

```
## Range check before you generate (HARD)
You are the last agent to see ``parameters.json`` and nothing in the
tooling validates ranges.  Compare EVERY value against its [min; max]
above, one by one — a blanket "they look fine" is not a check.  At min
or max is fine; strictly outside is a hard STOP: do not generate, route
back to the agent that wrote the values, quoting the parameter, its
value and its allowed range.  Never clip, round or adjust a value
yourself.
```

#### TC-20 · COMPRESS · −574 chars · risk low

*File:* `DC_prompt_fragments/tools_config/hard_constraints_tools.md` · *Section:* ### Tool-use hard rules (every agent) · *Golden rules:* 2, 6, 7 · *auditor's own id:* REC-20

**Why:** Keeps all three rules (no guessed paths, all arithmetic via calculate, attempt folders append-only) and drops the justification clauses and the render-reuse sentence that the Tool Caller prompt states itself.

**Risk:** Shared by all 8 chain/DC agents. The 'who opens the attempt' parenthetical is dropped here; it remains in the DCIC and Orchestrator prompts.

**Cut from** `### Tool-use hard rules (every agent)`

**...through** `DCIC opens it; the Orchestrator only as a fallback) — never edit the old
  folder's parameters.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Tool-use hard rules (every agent)
- DON'T invent or guess a path for a read tool: read tools take only the
  paths a hand-off label gives (``Input directory:`` / ``Extracted inputs
  file:`` / ``Parameters file:`` / ``Render images:`` / ``Current
  attempt:``) or an upstream tool's return value.
- DO route EVERY arithmetic operation through the ``calculate`` tool — LLM
  mental arithmetic is unreliable — batching this turn's expressions into
  ONE call.
- Attempt folders are append-only: write only into the ``Current attempt:``
  folder, never edit or delete a ``parameters.json`` or mesh already in one,
  and to build on an old set COPY its values into a NEW attempt.
```

#### TC-07 · COMPRESS · −467 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* ## Attempt folder (IMPORTANT — read this before any tool call) · *Golden rules:* 5, 6, 7 · *auditor's own id:* REC-07

**Why:** Same three rules (only-writable-folder, escalate-if-missing, reuse-is-fine) in half the words; the append-only detail is already in $hard_constraints_tools.

**Cut from** `## Attempt folder (IMPORTANT — read this before any tool call)`

**...through** `are NOT bound to ``new_attempt`` and must not invent or guess an
attempt path.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Attempt folder
Your hand-off MUST carry a ``Current attempt: <absolute path>`` line —
that folder is the only one you may write into, and it is the
``output_dir`` argument of every output-producing tool above.  If the
line is missing, ESCALATE; never invent or guess an attempt path.
Re-running ``generate_and_render_propeller`` on an attempt that already
has a mesh or renders REUSES them in place, so it needs no new attempt.
```

#### ⚠️ TC-21 · COMPRESS · −446 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MUST NOT do (DON'Ts) · *Golden rules:* 5, 6, 7 · *auditor's own id:* REC-21

**Why:** 680 chars restating the routing-is-a-tool-call mandate that routing_instructions() already delivers in full; the invariant is preserved in three lines.

**Risk:** Do NOT delete outright: the Receptionist and Orchestrator do not receive routing_instructions(), so this bullet is their only statement of the rule. The replacement keeps the halt consequence.

**Cut from** `- DON'T communicate to another agent in plain prose.  The ONLY channel`

**...through** `only exceptions are the Receptionist's direct user replies and the
  Orchestrator's final user-facing wrap-up.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
- DON'T talk to another agent in prose: the ONLY channel is a routing
  tool call (``call_<agent>``), and its ``message`` argument IS the
  hand-off.  Text emitted without a routing call is silently discarded
  and the pipeline halts.
```

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> Third proposal for the same generic_constraints.md region as REC-36 and REC-31. Its own risk note correctly identifies that 'the Receptionist and Orchestrator do not receive routing_instructions(), so this bullet is their only statement of the rule' — which I confirmed against agents/shared/prompts.py and the routing_instructions() call sites — yet the replacement still drops the exception clause that makes the rule safe for the Receptionist to read.
>
> *Safer:* Withdraw as a duplicate; if this is the wording kept, append: "The Receptionist's direct user replies are the sole exception."

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> Same defect as REC-31/REC-36/REC-03: the replacement ends at '...silently discarded and the pipeline halts' and deletes 'the only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up.' The cut's own risk_note argues this bullet must survive precisely BECAUSE 'the Receptionist and Orchestrator do not receive routing_instructions(), so this bullet is their only statement of the rule' - and then removes the clause that makes those two agents' normal behaviour legal. Verified: generic_constraints.md line 46 is outside <<CHAIN_ONLY>>, and _NON_CHAIN_AGENTS = {receptionist, orchestrator, conductor} (agents/shared/prompts.py:153), so both get the unfiltered text.
>
> *Safer:* Keep the replacement but restore the final clause: '... and the pipeline halts - the only exceptions are the Receptionist's direct user replies and the Orchestrator's user-facing wrap-up.'

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> The quote anchors correctly (this one includes the two-space indent the other three cuts miss), but the replacement drops the closing exception clause. The cut's own risk_note is right that the Receptionist and Orchestrator do not receive routing_instructions() — confirmed, only the six chain agents' prompt.md files contain {routing_instructions} — which makes this bullet their sole statement of the rule. Without '...the only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up', the Receptionist is told its normal user reply is 'silently discarded and the pipeline halts', contradicting routing_receptionist.md and inviting it to call call_orchestrator instead — the exact loop that fragment warns against. Also overlaps REC-31 (DCIC) and REC-36 (UII) on the same bullet.
>
> *Safer:* Add one sentence to the replacement (+95 chars): 'The Receptionist's direct user replies and the Orchestrator's final wrap-up are the exceptions.'

#### TC-08 · COMPRESS · −415 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* ## HARD LIMITS — Do NOT · *Golden rules:* 2, 5, 6 · *auditor's own id:* REC-08

**Why:** The enumerated forbidden mesh operations duplicate $hard_constraints_dc and 'don't invent tools' duplicates $hard_constraints_generic; the two clauses that are genuinely the Tool Caller's (no option menus, no self-invented tweaks) survive.

**Cut from** `## HARD LIMITS — Do NOT`

**...through** `- Do NOT invent parameter tweaks of your own initiative.`

**Replace with:**

```
## Hard limits
Your bound tools are exactly the ones listed above.  You cannot edit,
repair or post-process a mesh, rename outputs, or acquire new tools.
When something is impossible or fails, report the blocker factually and
ESCALATE — do not offer menus of options and do not invent parameter
tweaks of your own.
```

#### TC-09 · COMPRESS · −404 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* ## Data Flow and reporting file paths (IMPORTANT) · *Golden rules:* 5, 7, 11 · *auditor's own id:* REC-09

**Why:** The three labels and the 'copy verbatim' rule are the Tool Caller's core output contract and stay; the restatement of them a second time in prose is dropped.

**Cut from** `## Data Flow and reporting file paths (IMPORTANT)`

**...through** `the DCOI can also use ``read_attempt`` against the right folder.`

**Replace with:**

```
## Reporting paths (IMPORTANT)
Your routing ``message`` carries a brief success/failure report plus,
for every artifact produced this cycle, these labels on their own lines
with paths copied verbatim from the tool's return text — never
invented, renamed or shortened:

    Current attempt: <re-emit the path the hand-off carried>
    Mesh file: <absolute mesh path>
    Render images:
      <one absolute render path per line>

The DC Output Inspector receives no images automatically and can load
only the paths you list.  If rendering failed or was skipped, say so
and list no render paths.  ``Current attempt:`` is required on every
routing call.
```

#### TC-22 · DELETE · −396 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MAY do (DOs) · *Golden rules:* 6, 10 · *auditor's own id:* REC-22

**Why:** Exact duplicate of routing_instructions()'s '### How to decide where to route', which every chain agent already receives with its own next/previous agents named.

**Risk:** Inside <<CHAIN_ONLY>>, so it only ever reached agents that DO get the routing block — deletion is a pure de-duplication. Leave the <<CHAIN_ONLY>> marker itself in place.

**Cut from** `- DO follow the natural pipeline: when your work succeeds and the`

**...through** `request, still-ambiguous hand-off after one CLARIFY).`

**Replace with:** *(nothing — pure deletion)*

#### TC-32 · COMPRESS · −386 chars · risk low

*File:* `DC_prompt_fragments/dc_config/hard_constraints_dc.md` · *Section:* ### Domain hard rules (every agent) · *Golden rules:* 2, 7 · *auditor's own id:* REC-32

**Why:** Collapses two long DON'T bullets (post-processing list + unsupported-analysis list) into one, keeping every canonical example that names a real past failure.

**Risk:** Fleet-wide only — NOT additive with REC-03, which drops this fragment from the Tool Caller entirely. Benefits the other 7 agents that splice it.

**Cut from** `### Domain hard rules (every agent)`

**...through** `inspection and say so plainly.`

**Replace with:**

```
### Domain hard rules (every agent)
- The $parameter_count named parameters are the ONLY design levers: geometry
  changes only by changing them and regenerating via the DC Input Creator →
  Tool Caller path.  Reject invented parameters (hub_radius, fillet_radius,
  tip_clearance, any "supplemental" value) — they do not exist.
- There is NO mesh editing or post-processing (booleans, welding, remeshing,
  hole filling, fillets, supports …), no alternative export format (STL, STEP,
  IGES …), no extra camera angle or higher-resolution render, and no
  performance / RPM / thrust / flow / CFD / FEA / material analysis — the
  parameter set, tessellation and the three fixed views are not negotiable.
- The ONLY mesh metrics are watertightness, volume and degenerate-face count;
  when mesh checks are disabled, rely on visual inspection and say so.
```

#### TC-18 · COMPRESS · −370 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() → ### Do not loop — ESCALATE when stuck · *Golden rules:* 2, 7 · *auditor's own id:* REC-18

**Why:** Four sentences of elaboration around a one-sentence rule that is ALSO stated in generic_constraints.md; one statement in one place is enough.

**Cut from** `"### Do not loop — ESCALATE when stuck",`

**...through** `"consult another agent, or ask the user.  Never silently loop.",`

**Replace with:**

```
        "### Do not loop",
        "Never call the same tool with the same arguments twice in a "
        f"turn — it yields nothing new.  ESCALATE to the {hub} instead, "
        "saying what is missing or ambiguous.",
```

#### TC-10 · COMPRESS · −340 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* ## Loading parameters (IMPORTANT) · *Golden rules:* 7, 11 · *auditor's own id:* REC-10

**Why:** Keeps the whole mechanism (read the labelled path verbatim, then one call that meshes and renders) without the narration of what the tool returns.

**Cut from** `## Loading parameters (IMPORTANT)`

**...through** `mesh AND renders + checks it — there is no separate render step to call
afterwards.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Loading parameters
You do not receive ``parameters.json`` automatically.  Call
``read_parameters`` with the absolute path from the hand-off's
``Parameters file:`` line, verbatim, then call the mesh-generation tool
(see the inventory above) with those $parameter_count values plus the
``Current attempt:`` path as ``output_dir`` — that single call builds
the mesh AND renders + checks it.
```

#### TC-11 · COMPRESS · −306 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* **When to (re-)call ``read_parameters``** · *Golden rules:* 2, 5 · *auditor's own id:* REC-11

**Why:** Two bullets plus a repeated no-guessed-path warning collapse into one sentence with the same two triggers.

**Cut from** `**When to (re-)call ``read_parameters``**:`

**...through** ```Parameters file:`` line was supplied, ESCALATE — do not proceed.`

**Replace with:**

```
Re-read with ``read_parameters`` whenever the hand-off marks the line
``(newly written this cycle)`` or you are not certain your remembered
content still matches disk.  Never call it with a guessed path; if no
``Parameters file:`` line was supplied, ESCALATE.
```

#### TC-23 · DELETE · −248 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MUST NOT do (DON'Ts) · *Golden rules:* 6, 10 · *auditor's own id:* REC-23

**Why:** Third statement of the same permission-routing rule (routing block + REC-19 bullet already carry it), and it hard-codes 'Orchestrator' where the routing block is topology-aware.

**Risk:** Leave the <<CHAIN_ONLY>> marker in place. Apply after REC-19 so one statement survives.

**Cut from** `- DON'T bounce permission questions back to the previous agent.`

**...through** `them to the Orchestrator.`

**Replace with:** *(nothing — pure deletion)*

#### TC-24 · COMPRESS · −246 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MAY do (DOs) · *Golden rules:* 2, 7 · *auditor's own id:* REC-24

**Why:** The verbatim-relay invariant is load-bearing (standing directives are a real feature) but does not need five enumerated forbidden mutations plus a why-clause.

**Risk:** This is the rule that a subset-restating directive once silently revoked a chord authorisation; the replacement keeps 'VERBATIM … never altered, summarised, re-ordered or omitted' and the Planner-only ownership.

**Cut from** `- DO carry STANDING DIRECTIVES verbatim: if your incoming hand-off`

**...through** `it carries instructions later agents depend on, and only the Planner may
  set or change it.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
- DO reproduce any ``=== STANDING DIRECTIVES … ===`` block from your
  hand-off VERBATIM inside your own outgoing hand-off — never altered,
  summarised, re-ordered or omitted; only the Planner may change it.
```

#### TC-12 · COMPRESS · −218 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* <<BSV_ON>> Render type — sections vs the full 3D · *Golden rules:* 7, 6 · *auditor's own id:* REC-12

**Why:** Keeps the branch rule; drops the restatement of the default branch and the pointer to a section REC-04 deletes.

**Cut from** `<<BSV_ON>>**Render type — sections vs the full 3D.**  If your incoming hand-off`

**...through** `as usual.  See the blade-sections note further down.<</BSV_ON>>`

**Replace with:**

```
<<BSV_ON>>If the hand-off asks for the blade SECTIONS rather than the full 3D
propeller, call ``render_blade_sections`` with the ``Parameters file:`` path
instead of the mesh-generation tool, and generate no mesh this cycle.<</BSV_ON>>
```

#### TC-25 · COMPRESS · −180 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MUST NOT do (DON'Ts) · *Golden rules:* 2, 6 · *auditor's own id:* REC-25

**Why:** Two rules, two clauses; the escalation rationale is already stated by the do-not-loop rule.

**Cut from** `- DON'T retry a failing step blindly; when the same class of failure`

**...through** `never write the user-facing message yourself.`

**Replace with:**

```
- DON'T retry a failing step blindly, and DON'T script the final
  user-facing reply — ESCALATE instead, and let the Receptionist word it.
```

#### TC-26 · DELETE · −175 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MUST NOT do (DON'Ts) · *Golden rules:* 6 · *auditor's own id:* REC-26

**Why:** Verbatim duplicate of the routing block's '### Do not loop' section (kept, compressed, in REC-18).

**Risk:** The Receptionist and Orchestrator do not get the routing block; if the owner wants belt-and-braces there, keep this bullet and instead delete REC-18's block entirely.

**Cut from** `- DON'T loop: if you are about to call the same tool with the same`

**...through** `unchanged input yields nothing new.`

**Replace with:** *(nothing — pure deletion)*

#### TC-31 · COMPRESS · −149 chars · risk low

*File:* `DC_prompt_fragments/tools_config/tool_inventory.md` · *Section:* (whole file — Tool Caller only) · *Golden rules:* 9, 7 · *auditor's own id:* REC-31

**Why:** Tightens the four tool blurbs; drops the 'when mesh checks are enabled' aside and a cross-reference to view_images, a tool the Tool Caller does not have.

**Risk:** Consider also adding a 5th line for render_blade_sections here (BSV-gated) so the tool is inventoried rather than only mentioned in prose.

**Cut from** `1. **generate_and_render_propeller** — build ``propeller_mesh.obj`` into the`

**...through** `inline; an image or mesh returns a path to hand on, e.g. to
   ``view_images``).`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
1. **generate_and_render_propeller** — from the 16 parameters + ``output_dir``,
   builds ``propeller_mesh.obj`` in the attempt folder AND, as its built-in
   final step, renders the three views (isometric / top / side) and reports
   the quality metrics.  ONE call does both; there is no separate render
   tool.  Returns the mesh path, then the render+check report.
2. **calculate** — evaluate arithmetic / boolean expressions; batch every
   expression you need this turn into ONE call.
3. **list_attempts** — numbered summary of every attempt folder and which
   roles (parameters / mesh / renders / description) each holds.
4. **read_attempt(n, file)** — read one file from the n-th attempt (text
   inline; an image or mesh returns a path to hand on).
```

#### TC-27 · COMPRESS · −115 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MAY do (DOs) · *Golden rules:* 6, 7 · *auditor's own id:* REC-27

**Why:** The free-form-prose instruction is repeated verbatim in the routing block; only the authorship rule is unique here, so keep just that.

**Cut from** `- DO write hand-off messages as free-form prose carrying exactly what`

**...through** `never relabel one source as another) — and nothing more.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
- DO name the AUTHOR of any non-user-authored value in your hand-off
  ("the Planner directed …", "the user asked …"); never relabel one
  source as another, and include nothing the recipient does not need.
```

#### ⚠️ TC-28 · DELETE · −82 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MAY do (DOs) · *Golden rules:* 4 · *auditor's own id:* REC-28

**Why:** Restates default model behaviour for an English-language system prompt.

**Risk:** If sessions are ever driven in another language this bullet is what keeps the INTER-AGENT channel English; cut it only if all observed traffic is English.

**Cut from** `- DO answer in English; do not substitute words from other languages or`

**...through** `scripts.`

**Replace with:** *(nothing — pure deletion)*

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> Three cuts on the STANDING DIRECTIVES bullet in generic_constraints.md. REC-24 (TC) and REC-30 (DCIC) target the identical 454-char span (lines 12-18) with different replacements; REC-28 (UII) targets an 867-char span (lines 6-18) that fully CONTAINS both, so applying REC-28 after either of the others fails to anchor. The invariant itself is safe in all three — the runtime does not depend on the prompt wording here: standing_directives.is_present() matches the directive TEXT, not the header, and orchestrator.py:738 re-stamps the canonical BLOCK_START on every hop in _DIRECTIVE_CARRIERS, so even a paraphrased header self-heals.
>
> *Safer:* Take REC-28 (UII) alone — it is the superset and already keeps 'reproduce UNCHANGED' plus 'only the Planner may set or change it'. Mark REC-24 and REC-30 superseded.

#### TC-19 · MERGE · −60 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() → ### How to decide where to route · *Golden rules:* 2, 6, 11 · *auditor's own id:* REC-19

**Why:** Same four routing decisions in terser bullets, and absorbs the one surviving rule from the deleted permission section so REC-16 loses nothing.

**Risk:** Keeps _authorisation_sources(hub) in use, so the topology-correct grantor list survives the deletion of the permission block.

**Cut from** `"### How to decide where to route",`

**...through** `f"can fix it, route to the {hub} (ESCALATE).",`

**Replace with:**

```
        "### How to decide where to route",
        "- FORWARD to your next agent when your work succeeded and you "
        "were not told to report back.",
        f"- Route to the {hub} when it asked you to report back, or when "
        "no agent in the chain can fix your blocker (ESCALATE).",
        "- CLARIFY back to the previous agent only for data / wording / "
        "format problems it can actually fix.",
        "- Permission questions never go backward: if the hand-off already "
        "names an authorisation that plausibly covers the action, act on "
        f"it; otherwise ESCALATE to the {hub} — "
        + _authorisation_sources(hub),
```

#### TC-13 · COMPRESS · −56 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* ## Your Role · *Golden rules:* 4, 11 · *auditor's own id:* REC-13

**Why:** Trims filler around the tool list.

**Cut from** `Execute the design tools as instructed.  You have access to these`

**...through** `further down):`

**Replace with:**

```
Execute the design tools as instructed.  Your UTILITY tools (besides
the read and routing tools listed further down):
```

#### TC-29 · MERGE · −53 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MAY do (DOs) · *Golden rules:* 4, 6 · *auditor's own id:* REC-29

**Why:** First bullet is near-default behaviour; merged into the exhaustive-tool-list bullet that actually steers.

**Cut from** `- DO act on the inputs in your hand-off and the data files it`

**...through** `- DO use only the tools listed for your role; that list is exhaustive.`

**Replace with:**

```
- DO act on your hand-off's inputs, using your read tools on the paths
  it supplies, and use ONLY the tools listed for your role — that list
  is exhaustive.
```

#### TC-30 · COMPRESS · −42 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MUST NOT do (DON'Ts) · *Golden rules:* 2 · *auditor's own id:* REC-30

**Why:** Same rule, shorter enumeration.

**Cut from** `- DON'T invent tools, scripts, infrastructure, fallback policies,`

**...through** `you can't do something with your bound tools, ESCALATE.`

**Replace with:**

```
- DON'T invent tools, scripts, files, fallback policies, confidence
  scores or version numbers that do not exist; if your bound tools
  can't do it, ESCALATE.
```

</details>

<details><summary><b>Proposed shape of the shrunk prompt</b></summary>

```
Assembled Tool Caller prompt after all cuts (measured config: PLANNER_FIRST=False, DCII=True, BSV=True, RAG=False, trimesh backend).
Token estimates use the measured 4.8 chars/token ratio of the current build.

  You are the Tool Caller for a $domain_description.          ~55 ch     ~10 tok
  ## Your Role  (+ $tool_inventory, 4 tools)                  ~915 ch   ~190 tok
  ## Attempt folder                                           ~430 ch    ~90 tok
  ## Loading parameters
      (+ re-read rule + <<BSV_ON>> sections branch)           ~885 ch   ~185 tok
  ## Parameters and Allowed Ranges  ($parameter_list — UNTOUCHED, 16 params + ranges)
                                                             ~1645 ch   ~343 tok
  ## Range check before you generate (HARD)                   ~467 ch    ~97 tok
  ## Active render / mesh-check backend  ({render_check_library_block})
                                                              ~356 ch    ~74 tok
  ## Hard limits                                              ~314 ch    ~65 tok
  ## Reporting paths (IMPORTANT)                              ~650 ch   ~135 tok
  ## Say what is NEW this cycle                               ~451 ch    ~94 tok
  Domain hard rule (one line, replaces $hard_constraints_dc)  ~248 ch    ~52 tok
  ## Hard constraints — generic  ($hard_constraints_generic)  ~1555 ch  ~324 tok
  ## Hard constraints — tool-specific ($hard_constraints_tools)~712 ch  ~148 tok
  ## Routing  ({routing_instructions}: flow + position,
      how to decide, available routing tools, do not loop,
      routing is a tool call)                                ~2380 ch  ~496 tok
  ----------------------------------------------------------------------------
  TOTAL                                                     ~10,760 ch ~2,240 tok
  (removed sections: Utility tools list_attempts/read_attempt, HARD LIMITS list,
   State THIS CYCLE narration, End-of-session feedback, shared blade-sections
   awareness, permission/authorisation block)
```

</details>

**Auditor notes.** MEASUREMENT BASIS. chars_removed = reduction in the ASSEMBLED prompt text, not the raw file diff. That matters for four cuts: REC-03 (the quoted text is a 54-char slot line but expands to ~1,272 chars), REC-05 (390 raw → ~640 assembled), REC-04 (140 raw → ~762 assembled), and the four routing.py cuts (the edit lands in Python string literals, so the file diff is larger than the prompt-text delta I report). I reassembled the prompt locally (all $slots, <<BSV_ON>>/<<DCII_ONLY>>/<<CHAIN_ONLY>> resolved, <<HAS_DBA>> stripped) and measured 24,004 chars against the owner's 5,004-token baseline → 4.80 chars/token.

ARITHMETIC. Cuts that apply to the Tool Caller in the measured config total 13,239 chars (everything except REC-14 pyvista, which is the alternative backend and not spliced this session, and REC-32, which is fleet-only because REC-03 drops that fragment from this agent). 24,004 − 13,239 = 10,765 chars ≈ 2,243 tokens. That is a 55% cut of the prompt, inside the 1,000–3,000 target. Every verbatim quote_start/quote_end in this report was string-matched against the file on disk and confirmed present.

BLAST RADIUS OF SHARED CUTS (say so explicitly before applying):
- generic_constraints.md (REC-21 … REC-30, ~1,983 chars, 3,506 → ~1,523) is spliced by ALL EIGHT chain/DC agents. This is the single highest-leverage edit in the fleet: ~15,900 chars ≈ 3,300 tokens removed across the system.
- hard_constraints_tools.md (REC-20, 574 chars) — same eight agents, ~4,600 chars fleet-wide.
- hard_constraints_dc.md (REC-32, 386 chars) — seven agents after REC-03.
- agents/shared/routing.py (REC-16 … REC-19, 2,203 chars) — the six CHAIN agents (Planner, UII, DCIC, DCII, TC, DCOI); the Receptionist and Orchestrator use $routing_receptionist / $routing_hub instead and are unaffected. ~13,200 chars ≈ 2,750 tokens fleet-wide.
- tool_inventory.md and the render_check_library fragments are Tool-Caller-only.

WHAT I DELIBERATELY DID NOT CUT.
1. $parameter_list (1,609 chars, 16 params with ranges) — owner's explicit decision, untouched, and it is the reference the range check depends on.
2. "DON'T fabricate observations about artifacts you did not see produced" in generic_constraints.md — the anti-hallucination patch. It is 201 chars and it is the only statement of that invariant anywhere in this prompt.
3. The range-check behaviour (REC-06 keeps per-value comparison, hard STOP, route-back-quoting-value, never-clip). I only removed the two paragraphs explaining why the check is redundant. Given the DCII once blanket-approved out-of-range values, the "compare EVERY value, one by one — a blanket 'they look fine' is not a check" clause is preserved verbatim.
4. The routing-is-a-tool-call mandate. It exists in two places today (generic_constraints + routing block) and I kept a compressed version in BOTH (REC-17, REC-21) rather than de-duplicating, because the Receptionist and Orchestrator only see the generic_constraints copy. This is the one place I broke the "say it once" rule on purpose.
5. The three-label reporting contract (Current attempt / Mesh file / Render images) and "copy verbatim, the DCOI can load only paths you list" — the Tool Caller's actual job.
6. The fresh-vs-reused signalling, including the tool's exact marker strings ("Mesh saved …", "Reused existing mesh …") — a weaker model needs those literals to classify the return text.

CUTS WITH REAL DOWNSIDE RISK, ranked:
- REC-16 + REC-19 must be applied together, or REC-16 alone deletes the only permission-routing guidance the chain agents get. REC-19 alone is safe.
- REC-24 (standing directives) touches the mechanism behind the "subset restatement silently revoked a chord authorisation" incident. The replacement keeps VERBATIM/never-altered/Planner-only; it drops the enumerated list of forbidden mutations. If the owner is nervous about exactly this failure, skip REC-24 — it is only 246 chars.
- REC-03 removes the named ban on invented parameters from the Tool Caller specifically. Low practical risk (the TC authors nothing and the range check runs over the 16 known keys), but it is the reason I marked it medium.
- REC-28 (answer in English) is the one cut I would drop first if any session is ever non-English.

DEPENDENCY BETWEEN REC-04 AND REC-12: applying REC-04 without REC-12 leaves render_blade_sections bound but never named in the prompt. Apply REC-12 first, or add the 5th inventory line suggested in REC-31.

ORTHOGONAL FIX WORTH DOING SEPARATELY (not scored here): the Tool Caller carries 2,201 tokens of tool schema for 9 tools. Three of them — list_attempts, read_attempt, calculate — plus the retrieve_* family only matter in diagnostic paths. Trimming the schema descriptions (golden rule 9) is likely worth another 300–600 tokens on this agent and considerably more fleet-wide, but it lives in the @tool docstrings, not in prompt.md, so it is outside the scope of this file-level report.

---

### 4.8 DC Output Inspector — 11,505 → ~2,400 tok

| ID | action | section | −chars | rules | risk | what |
|---|---|---|---:|---|---|---|
| **DCOI-01** | SCOPE_PER_AGENT | ## Sketch handling (when the user supplied a sketch) | 8231 | 3,8,2 | medium | sketch_handling.md is 8.8k chars written mostly FOR the UII (how to author extraction records, warm-start estimates, crop boxes); the DCOI only needs the rough-vs-precise strictness rule and the form-scaffolding rule. |
| **DCOI-02** | COMPRESS | _COMPARISON_MODE_1 / _COMPARISON_MODE_2 | 2380 | 6,7 | low | Both inactive modes repeat the same anti-anchoring justification paragraph verbatim; the behaviour-changing instruction is one sentence. |
| ⚠️ **DCOI-03** | COMPRESS | ### What every agent … MAY do (DOs) / MUST NOT do (DON'Ts) | 2116 | 8,5,7,4 | medium | This is the copy-pasted 'constitution' spliced into 8 agents; every rule survives as one line instead of a justified paragraph. |
| ⚠️ **DCOI-04** | COMPRESS | ## The three states of a user value — LOCKED, SOFT TARGET, o | 1860 | 2,7,5 | medium | The three definitions and the authorisation-source list are load-bearing, but each is wrapped in two sentences of justification and worked examples that add no new behaviour. |
| **DCOI-05** | DELETE | ## Sketch handling (when the user supplied a sketch) | 1776 | 2,8 | low | sketch_notes.md is a catalogue of drawing artifacts aimed at the agent READING a sketch to author parameters (UII/DCIC); its one DCOI-relevant point — artifacts are not defects — is already in REC-01's replacement. |
| **DCOI-06** | COMPRESS | _COMPARISON_MODE_3 (the default mode) | 1725 | 7,2,11 | low | The default block spends most of its length on a three-bullet enumeration of when to consult raw inputs plus a repeated anti-anchoring rationale; the three triggers compress to one sentence. |
| **DCOI-07** | COMPRESS | ## Precision section-matching — when a standing precision di | 1615 | 2,7,11 | medium | Four bold bullets each carry one instruction plus 4-6 lines explaining why; the instructions survive intact, the explanations do not. |
| **DCOI-08** | COMPRESS | ### Full-3D precision check (when the directive targets the  | 1379 | 2,6,7 | medium | The 3D loop is 'the sections loop with the target swapped'; restating the whole loop is duplication of the block immediately above. |
| ⚠️ **DCOI-09** | COMPRESS | ### Routing is a tool call — MANDATORY (routing_instructions | 1020 | 5,6,7 | medium | Three consecutive paragraphs restate the same mandate (invoke it, don't announce it, don't defer it, don't use the retired ---ROUTING--- template) after generic_constraints.md already stated it once. |
| **DCOI-10** | COMPRESS | ## Data Flow | 957 | 10,6 | low | The four 'Routing guidance' bullets duplicate routing_dc_output_inspector.md, which is spliced into the same prompt via {routing_instructions}. |
| **DCOI-11** | COMPRESS | ## HARD RULE — never describe images you did not load this t | 949 | 2,5,7 | medium | Six example phrasings plus two verbatim fill-in templates where one example and one template carry the same instruction. |
| **DCOI-12** | COMPRESS | ## How to compare this cycle's design against user expectati | 930 | 9,6 | low | A prose re-description of five tools whose schemas are already bound; the only non-schema content is the ocr_regions batching hint and the 'judge intent' sentence. |
| **DCOI-13** | COMPRESS | Blade-sections visualizer — DCOI overlay | 847 | 7,6 | low | Every instruction here is also stated in the precision-matching block and the routing fragment; the unique content is the side_by_side/layout/regions argument recipe. |
| **DCOI-14** | COMPRESS | ## HARD RULES — what you must NEVER suggest | 824 | 2,7 | medium | The ratio-vs-millimetre gotcha is real and load-bearing, but three worked phrasings and a two-branch thought experiment compress into one sentence plus the rule. |
| **DCOI-15** | COMPRESS | ### Override authority and reporting upstream interpretation | 819 | 7,2 | low | Two paragraphs of justification for why the DCOI is well-placed to override, around three lines of actual instruction. |
| **DCOI-16** | REPLACE_WITH_EXAMPLES | ## Per-claim verification against the comparison source(s) i | 767 | 2,11 | low | Three bullets of 6-8 lines each defining categories the model can infer; the operative rules are count-in-the-render-only, quote-the-source, and say-so-when-unresolvable. |
| **DCOI-17** | DELETE | ## HARD RULES — what you must NEVER suggest | 728 | 6,3 | low | Every clause of geometry_modification_rule.md (booleans/welding/remeshing/hole-filling/struts/no-mesh-fix, 'geometry changes only via parameters + regenerate') is already in $hard_constraints_dc, which is spliced into the SAME prompt ~100 lines later. |
| **DCOI-18** | COMPRESS | ## Loading render images (IMPORTANT) | 675 | 2,5,7 | low | Three paragraphs explaining where the paths come from plus a four-bullet rule list, where the operative content is 'use only hand-off paths, never invent, escalate if none'. |
| **DCOI-19** | COMPRESS | ## Output Format | 664 | 11,7 | low | Each of the five section headers carries a 2-4 line gloss that restates rules already stated above (anti-fabrication, no numeric values, claim sourcing). |
| **DCOI-20** | COMPRESS | ### When to stop (you judge; a code cap backstops you) | 660 | 2,5,6 | low | Three termination conditions each get a bolded label plus explanation, then the closing paragraph re-states two rules already given above. |
| **DCOI-21** | COMPRESS | ## What a Correct Output Should Show | 556 | 3,11 | low | Genuine DC reference material and the only agent that uses it, but three bulleted lists compress into two prose runs with no loss of items. |
| **DCOI-22** | COMPRESS | ### Tool-use hard rules (every agent) | 550 | 7,8 | low | Spliced into 8 agents; the append-only bullet in particular explains the rationale twice before stating the rule. |
| **DCOI-23** | COMPRESS | ## HARD RULES — what you must NEVER suggest | 533 | 7,5 | low | Three paragraphs make one point — stay qualitative, prefer relative magnitudes, exact values are the exception. |
| **DCOI-24** | COMPRESS | ### Domain hard rules (every agent) | 508 | 2,6 | low | Spliced into 8 agents; the mesh-post-processing bullet and the no-invented-parameters bullet overlap heavily and the enumerated lists are illustrative. |
| **DCOI-25** | COMPRESS | ### Available routing tools | 489 | 9,6 | low | Becomes the single source for routing guidance once REC-10 removes the duplicate in prompt.md; the closing 'you are the last agent' sentence is already emitted by the routing_instructions builder immediately above it. |
| **DCOI-26** | COMPRESS | ## Do NOT mix cycles when forming a verdict | 488 | 6,5 | low | Two of its three bullets restate the anti-fabrication HARD RULE above; the unique content is 'mark prior numbers as prior'. |
| **DCOI-27** | DELETE | ## What to Look For | 485 | 6,3 | low | A generic defect list sitting directly beneath $visual_inspection_guide, which the block itself admits is the authoritative version. |
| **DCOI-28** | COMPRESS | ### How to decide where to route (routing_instructions build | 450 | 10,2 | low | Four bullets narrating a routing protocol that the bound call_<agent> tool schemas already encode; collapses to one bullet without losing a branch. |
| **DCOI-29** | COMPRESS | ## Per-claim verification against the comparison source(s) i | 444 | 6,5 | low | An eight-line restatement of the SOFT TARGET definition given verbatim in $value_states two sections earlier; only the DCOI-specific consequence is new. |
| **DCOI-30** | DELETE | ### Verdict shape | 443 | 6 | low | Describes the output template that the '## Output Format' section renders literally further down the same prompt. |
| **DCOI-31** | COMPRESS | ### Stale images in your history — you choose whether to re- | 441 | 7,2 | low | One paragraph of hedging around a two-clause decision rule. |
| **DCOI-32** | MERGE | ## End-of-session feedback message (read-only) | 430 | 4,7 | low | Two shared fragments plus a six-line scope enumeration to say 'a feedback message may arrive; treat it as ground truth'. |
| **DCOI-33** | COMPRESS | ### Blade-sections visualizer | 398 | 7,8 | low | Spliced into all 9 agents; the 'why it is faster' explanation and the shown-to-the-user aside do not change any agent's behaviour. |
| **DCOI-34** | COMPRESS | _IMAGE_PERSISTENCE_ON / _IMAGE_PERSISTENCE_OFF | 380 | 7,4 | low | Describes an implementation detail (paired text blocks, stripping at hand-off) in more words than the behavioural consequence needs. |
| **DCOI-35** | COMPRESS | ### Permission / authorisation issues → hub (routing_instruc | 360 | 7,6 | low | Two paragraphs to say: re-read the hand-off once, act on an authorisation it already carries, otherwise escalate; CLARIFY is for data problems. |
| **DCOI-36** | DELETE | ### Do not loop — ESCALATE when stuck (routing_instructions  | 350 | 6,5 | low | Verbatim duplicate of the "DON'T loop: if you are about to call the same tool with the same arguments" bullet in generic_constraints.md, which is spliced into the same prompt. |
| **DCOI-37** | COMPRESS | ## Comparing against a prior attempt | 296 | 9,7 | low | Narrates a three-call tool sequence the schemas already describe; the operative bits are 'read_attempt returns a path, not an image' and 'cite the attempt number'. |
| **DCOI-38** | COMPRESS | ## Per-claim verification against the comparison source(s) i | 264 | 7,11 | low | Parenthetical justifications for why the DCOI does not re-check parameters or re-count features. |
| **DCOI-39** | COMPRESS | ## How to compare this cycle's design against user expectati | 213 | 7 | low | Explains that a session setting chose the block below, which the block below states itself. |

<details><summary><b>Full text of each change</b></summary>

#### DCOI-01 · SCOPE_PER_AGENT · −8231 chars · risk medium

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## Sketch handling (when the user supplied a sketch) · *Golden rules:* 3, 8, 2 · *auditor's own id:* REC-01

**Why:** sketch_handling.md is 8.8k chars written mostly FOR the UII (how to author extraction records, warm-start estimates, crop boxes); the DCOI only needs the rough-vs-precise strictness rule and the form-scaffolding rule.

**Risk:** Drops the DCOI's copy of the SOFT-TARGET-from-sketch rule and the detailed 'precise sketch' guidance; both survive via $value_states and the replacement's 'a real deviation from a drawn proportion IS a defect'. The UII and DCII keep the full fragment, so nothing is lost system-wide.

**Cut from** `## Sketch handling (when the user supplied a sketch)
$sketch_handling`

**...through** `$sketch_handling`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Sketch handling
A user reference image may be anywhere from a rough doodle to a measured drawing; the UII records which in DESIGN INTENT — match with that strictness. On a ROUGH sketch, asymmetry, wobble and off-centre features are drawing artifacts, not defects: never order a revision to chase them, and treat a sketch-quality-only mismatch as CONVERGED. On a PRECISE sketch, a real deviation from a drawn proportion IS a defect. On a pre-printed form, only the handwritten marks are user input — printed guide values and min/max are scaffolding. Say honestly what the parameters could not capture.
```

#### DCOI-02 · COMPRESS · −2380 chars · risk low

*File:* `agents/dc_output_inspector/dc_output_inspector.py` · *Section:* _COMPARISON_MODE_1 / _COMPARISON_MODE_2 · *Golden rules:* 6, 7 · *auditor's own id:* REC-02

**Why:** Both inactive modes repeat the same anti-anchoring justification paragraph verbatim; the behaviour-changing instruction is one sentence.

**Cut from** `_COMPARISON_MODE_1 = """\
This session is configured to compare the generated design DIRECTLY`

**...through** `not something for you to verify against the raw
materials."""`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
_COMPARISON_MODE_1 = """\
Compare the design DIRECTLY against the USER INPUTS — ``user_query.txt``,
the reference image(s), and their paired ``_note.txt``.  Do NOT read
``extracted_inputs.txt`` in this mode; it is the UII's interpretation,
not the user's raw input.

Load this cycle's renders and form your visual judgement FIRST, before
reading any user material: reading the source first makes the model
confabulate agreement instead of actually counting what the render shows.
Then ``read_input_text(path={user_query_path})``, ``read_image_notes()``
when images exist, and ``view_images`` on the relevant reference images."""

_COMPARISON_MODE_2 = """\
Compare the design against the UII's extraction at
``{extracted_inputs_path}`` — its ``QUANTITATIVE INPUTS`` and
``DESIGN INTENT`` sections ARE your comparison source.  Do NOT load the
user's raw inputs in this mode; if the extraction is wrong, surface it
via your override authority rather than checking the raw materials.

Load this cycle's renders and form your visual judgement FIRST, before
reading the extraction: reading it first makes the model confabulate
agreement instead of actually counting what the render shows."""
```

#### ⚠️ DCOI-03 · COMPRESS · −2116 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent … MAY do (DOs) / MUST NOT do (DON'Ts) · *Golden rules:* 8, 5, 7, 4 · *auditor's own id:* REC-03

**Why:** This is the copy-pasted 'constitution' spliced into 8 agents; every rule survives as one line instead of a justified paragraph.

**Risk:** Shortens the 'routing is a tool call' mandate (a real production failure). The imperative and the consequence are both retained; only the three restatements of it are dropped. AFFECTS ALL 8 AGENTS.

**Cut from** `### What every agent in any design configurator MAY do (DOs)`

**...through** `Orchestrator's final user-facing wrap-up.`

**Replace with:**

```
### Hard rules (every agent)
- Act only on the paths and data your hand-off supplies; use only your bound tools — that list is exhaustive.  If you cannot do something with them, ESCALATE.
- Never invent tools, files, scripts, policies, confidence scores or version numbers, and never state an observation you cannot source to a tool result, a message in your history, or the user's own words.
- Never call the same tool with the same arguments twice in a turn — STOP and ESCALATE instead.
<<CHAIN_ONLY>>- Forward to your natural next agent when your work succeeded and nothing told you to report back; otherwise return to the Orchestrator.  ESCALATE the moment something blocks you that no chain agent can fix — including any permission question, which the previous agent cannot grant — rather than retrying a failing step blindly.
- Copy any ``=== STANDING DIRECTIVES … ===`` block into your outgoing hand-off UNCHANGED; only the Planner may alter it.
- Never write the user-facing reply; the Receptionist composes it.
<</CHAIN_ONLY>>- Write hand-offs as free-form English prose carrying exactly what the recipient needs — the paths their tools require, what changed and why, and the authorship of any non-user value — and nothing more.
- **Routing is a tool call.**  The ONLY channel to another agent is ``call_<agent>``; its ``message`` argument IS the hand-off.  Text emitted without a routing call is discarded and the pipeline halts.
```

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> This is a SECOND, differently-worded full rewrite of the same 3,506-char file that REC-03 (DC Input Inspector) rewrites end-to-end. The two are mutually exclusive: whichever is applied first makes the other's quote_start/quote_end unmatchable, and nine further cuts (REC-36, REC-42, REC-28/UII, REC-30, REC-31/DCIC, REC-43, REC-21, REC-24, REC-28/TC) carve sub-regions of the same file. The owner cannot apply these independently as briefed. Separately, it drops the same Receptionist-exception clause described under REC-03 (DCII) and additionally collapses the whole fragment to a single '### Hard rules' heading, so any later cut quoting '### What every agent … MAY do (DOs)' will also fail.
>
> *Safer:* Pick ONE whole-fragment rewrite of generic_constraints.md (this one is the tighter of the two) and withdraw the other plus all nine sub-region cuts; then add the Receptionist-exception clause to its routing bullet: "...the pipeline halts — the Receptionist's direct user replies are the sole exception."

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> Same two problems as the DCII's REC-03. Its final line - '**Routing is a tool call.** The ONLY channel to another agent is ``call_<agent>``; its ``message`` argument IS the hand-off. Text emitted without a routing call is discarded and the pipeline halts.' - drops the Receptionist/Orchestrator carve-out, and it is a competing whole-file rewrite of generic_constraints.md against REC-03 (DCII) plus seven partial cuts on the same file. Content-wise this version is the better of the two (it keeps the permission-question rule and the 'never write the user-facing reply' rule inside <<CHAIN_ONLY>>).
>
> *Safer:* Adopt this one as the single generic_constraints.md rewrite, and append to the routing line: '(Exceptions: the Receptionist's direct user replies and the Orchestrator's user-facing wrap-up.)'

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> The replacement's final bullet ('Text emitted without a routing call is discarded and the pipeline halts') drops the original's closing clause: 'the only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up.' That bullet sits OUTSIDE the <<CHAIN_ONLY>> region, so the Receptionist and Orchestrator both receive it verbatim (both splice $hard_constraints_generic). Both END THEIR TURN WITH PLAIN TEXT BY DESIGN: agents/receptionist/receptionist.py:8 — 'replies to the user directly (by producing plain text with no tool call)' — returning ai_text(response.content) at line 174; agents/orchestrator/orchestrator.py:542 — 'producing plain text.  Bail out as DONE'. Neither receives routing_instructions() (only the six chain agents' prompt.md files contain {routing_instructions}), so this bullet is their ONLY statement of the rule, and without the exception it reads as an absolute prohibition contradicting agents/shared/prompt_fragments/routing_receptionist.md ('you do NOT invoke any routing tool... do not also call call_orchestrator (that would loop control back into the system)'). Also overlaps REC-03 (DC Input Inspector), which rewrites the identical span differently.
>
> *Safer:* Keep the cut, but append the exception to the last bullet (+103 chars): '  Exception: the Receptionist's direct user replies and the Orchestrator's final wrap-up ARE plain text.'

#### ⚠️ DCOI-04 · COMPRESS · −1860 chars · risk medium

*File:* `agents/shared/prompt_fragments/value_states.md` · *Section:* ## The three states of a user value — LOCKED, SOFT TARGET, or FREE · *Golden rules:* 2, 7, 5 · *auditor's own id:* REC-04

**Why:** The three definitions and the authorisation-source list are load-bearing, but each is wrapped in two sentences of justification and worked examples that add no new behaviour.

**Risk:** Drops the explicit '(unlocked by user) may appear on older extractions' aside and the 'ritual re-confirmation' phrasing — both kept in one clause each. AFFECTS Planner, DCIC, DCII, DCOI.

**Cut from** `Every value the user could have given is in exactly one of three states,`

**...through** `bounded by range.`

**Replace with:**

```
Every value the user could have given is in one of three states, read off the extraction's QUANTITATIVE INPUTS:

- **LOCKED** — stated plainly, no marker.  Fixed unless an authorisation frees it.
- **SOFT TARGET** — marked ``SOFT TARGET (goal: …; keep near … if free)``.  The goal governs: the marker itself IS the authorisation to move the value within range as far as the goal requires, and you never have to justify moving it.  The stated number settles the parameter only when the goal does not bear on it, and the "keep near … if free" wording then says how closely to follow it.
- **FREE** — absent from QUANTITATIVE INPUTS (never given, or released — a released value is simply omitted).  The system's choice within range; a qualitative description that must become a number is FREE too.

**Freeing a LOCKED value.**  Any ONE of these authorises it: the incoming hand-off (a user permission, or a strategy / recovery directive), the extraction's DESIGN INTENT section, or an ``(unlocked by user)`` annotation on the value's own line.  One source is enough — never demand a re-confirmation of something the hand-off already carries, and a line saying "user-locked" is only the DEFAULT lock.  How far it may move follows the wording: "as needed / only if necessary" = the smallest change that restores viability; "freely" or nothing said = as far as the goal requires, within range.
```

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> A second full rewrite of agents/shared/prompt_fragments/value_states.md, competing with REC-04 (DC Input Inspector), which rewrites the same file end-to-end with different wording. REC-34 and REC-35 (DC Input Creator) additionally carve two sub-regions of the same file. Four cuts, one 2,960-char file, at most one whole-file rewrite can apply. Both whole-file versions preserve the invariants I checked (three states, the SOFT-TARGET-marker-is-its-own-authorisation rule, all three authorisation sources, one-source-is-enough, and the how-far scale), so this is purely an applicability conflict.
>
> *Safer:* Keep one whole-file rewrite of value_states.md and withdraw the other plus REC-34/REC-35, whose regions it already subsumes.

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> REC-04 (DCII) and REC-04 (DCOI) are two different full rewrites of the SAME 2,884-char span — the entirety of agents/shared/prompt_fragments/value_states.md. My verbatim check confirms both anchor at offset 0 and end at the same point. On top of that, REC-34 and REC-35 (DC Input Creator) rewrite two sub-spans inside it (891 and 595 chars). Four cuts, one file, ~4,000 chars of claimed savings against a 2,960-char file.
>
> *Safer:* Group all four as one decision on value_states.md. REC-04 (DCII) is the better base — it keeps the '(unlocked by user)' third authorisation channel and the SOFT-TARGET-marker-is-its-own-authorisation clause; drop REC-04 (DCOI), REC-34 and REC-35 as superseded.

#### DCOI-05 · DELETE · −1776 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## Sketch handling (when the user supplied a sketch) · *Golden rules:* 2, 8 · *auditor's own id:* REC-05

**Why:** sketch_notes.md is a catalogue of drawing artifacts aimed at the agent READING a sketch to author parameters (UII/DCIC); its one DCOI-relevant point — artifacts are not defects — is already in REC-01's replacement.

**Risk:** The 'count the blades and trust the count' rule leaves the DCOI, but the DCOI compares the RENDER's count to the source's stated count and is explicitly told never to re-count the source. UII and DCII keep the fragment.

**Cut from** `$sketch_notes`

**...through** `$sketch_notes`

**Replace with:** *(nothing — pure deletion)*

#### DCOI-06 · COMPRESS · −1725 chars · risk low

*File:* `agents/dc_output_inspector/dc_output_inspector.py` · *Section:* _COMPARISON_MODE_3 (the default mode) · *Golden rules:* 7, 2, 11 · *auditor's own id:* REC-06

**Why:** The default block spends most of its length on a three-bullet enumeration of when to consult raw inputs plus a repeated anti-anchoring rationale; the three triggers compress to one sentence.

**Cut from** `_COMPARISON_MODE_3 = """\
This session is configured to compare the generated design`

**...through** `plus the user's raw inputs WHEN your judgement says they
are needed."""`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
_COMPARISON_MODE_3 = """\
Compare the design PRIMARILY against the UII's extraction at
``{extracted_inputs_path}`` (its ``QUANTITATIVE INPUTS`` and
``DESIGN INTENT`` sections), and SECONDARILY against the user's raw
inputs (``user_query.txt``, paired image+note) when DESIGN INTENT calls
for it, when a quantity's unit or framing looks ambiguous, or when you
suspect the extraction misread something.  Otherwise the extraction
alone is enough — don't burn turns loading inputs you won't consult.

Load this cycle's renders and form your visual judgement FIRST, before
reading any comparison source: reading the source first makes the model
confabulate agreement instead of actually counting what the render
shows."""
```

#### DCOI-07 · COMPRESS · −1615 chars · risk medium

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## Precision section-matching — when a standing precision directive is active · *Golden rules:* 2, 7, 11 · *auditor's own id:* REC-07

**Why:** Four bold bullets each carry one instruction plus 4-6 lines explaining why; the instructions survive intact, the explanations do not.

**Risk:** Keeps all four invariants (no first-render approval, side-by-side sketch load overriding the comparison mode, prose-only gap description, PRECISION REFINE routing) but loses the narrative of why the DCIC re-opens attempts.

**Cut from** `## Precision section-matching — when a standing precision directive is active`

**...through** `round's render when you need to judge progress).`

**Replace with:**

```
## Precision section-matching (only while a STANDING DIRECTIVES precision block is active)
Run a REFINE LOOP, not a one-shot verdict:
- **Never approve the first render**, and never approve on ordering / proportions / section count alone.  The bar is SHAPE fidelity per section: thickness, camber, high-point, angle.
- **Compare side by side.**  ONE ``view_images`` call with ``side_by_side=True`` loading this cycle's blade-sections render plus the user's sketch cropped to the ``SKETCH CROP REGION`` the UII recorded (pass it as that image's ``regions``; crop it yourself if none was recorded).  The directive makes the drawing ground truth, so load it even under a comparison mode that would normally exclude raw user images.
- **Describe the gap in prose** — name the section, the feature and the direction ("inner too thin, leading edge too pointed; middle camber shallower than drawn").  Do not dictate numeric values; the DCIC owns those.
- **Route with ``call_orchestrator`` marked PRECISION REFINE** — still iterating, not a blocker.  There is no Planner re-plan in this loop; attempts accumulate, so use ``list_attempts`` / ``read_attempt`` to pull a prior round's render.
```

#### DCOI-08 · COMPRESS · −1379 chars · risk medium

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ### Full-3D precision check (when the directive targets the 3D) · *Golden rules:* 2, 6, 7 · *auditor's own id:* REC-08

**Why:** The 3D loop is 'the sections loop with the target swapped'; restating the whole loop is duplication of the block immediately above.

**Risk:** Retains the two rules unique to the 3D loop — iterate only if an unlocked lever (SOFT TARGET counts) can move it, and the first 3D render MAY be approved.

**Cut from** `### Full-3D precision check (when the directive targets the 3D)`

**...through** `short because it has few levers.`

**Replace with:**

```
### 3D precision check
When the directive targets the whole propeller instead of the sections, the same loop applies against the 3D views: compare each render view side-by-side with the matching sketch-view crop, and describe the mismatched aspect (planform outline, blade sweep / twist, tip shape, ring proportions).  Iterate only if an UNLOCKED lever can measurably improve it — a ``SOFT TARGET`` counts as a lever; if the mismatch traces to LOCKED numbers or configurator limits, STOP and report it honestly.  Unlike the sections loop, a first 3D render MAY be approved when it genuinely matches.
```

#### ⚠️ DCOI-09 · COMPRESS · −1020 chars · risk medium

*File:* `agents/shared/routing.py` · *Section:* ### Routing is a tool call — MANDATORY (routing_instructions builder) · *Golden rules:* 5, 6, 7 · *auditor's own id:* REC-09

**Why:** Three consecutive paragraphs restate the same mandate (invoke it, don't announce it, don't defer it, don't use the retired ---ROUTING--- template) after generic_constraints.md already stated it once.

**Risk:** This mandate patches a real halt-the-pipeline failure. The imperative, the 'message IS the hand-off' clause and the don't-announce clause are all kept; only the retired-template paragraph and the repetition go. AFFECTS ALL 6 CHAIN AGENTS.

**Cut from** `"### Routing is a tool call — MANDATORY",`

**...through** `"(one or two lines is plenty).",`

**Replace with:**

```
        "### Routing is a tool call — MANDATORY",
        "Every response that ends your turn MUST invoke exactly one of "
        "the routing tools listed above.  Its ``message`` argument IS the "
        "complete hand-off — free-form prose, no template, carrying the "
        "paths and context the recipient needs and nothing they do not.  "
        "Do not announce a call instead of making it, and do not defer it "
        "to the next turn: invoke it in the same response where you "
        "finish your work.  Any other text you emit is private reasoning "
        "— keep it to a line or two.",
```

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> Fourth of four competing rewrites of the same routing.py '### Routing is a tool call — MANDATORY' block (see REC-12). Content-wise it is safe; it is the independent-applicability claim that fails.
>
> *Safer:* Withdraw as a duplicate of REC-07 (User Input Inspector).

> ⚠️ **Verifier — UNSAFE_NEEDS_REPLACEMENT**
>
> The replacement drops the consequence clause entirely: nowhere does it say that text emitted without a routing call is discarded and the pipeline halts. Its own risk_note claims 'The imperative, the message IS the hand-off clause and the don't-announce clause are all kept' - the halt consequence, which is the actual incident content ('agents once emitted prose without a routing tool call and the pipeline halted'), is not. It is also one of FOUR competing rewrites of the same lines in agents/shared/routing.py (REC-07 UII, REC-12 DCII, REC-17 TC, REC-09 DCOI); only one can apply.
>
> *Safer:* Use REC-17 (Tool Caller) instead - it is the only one of the four that keeps mandate + halt consequence + message-is-the-hand-off + don't-announce. If keeping this one, insert 'Prose emitted without a routing call is discarded and the pipeline halts.'

> ⚠️ **Verifier — OVERLAPS_ANOTHER_CUT**
>
> Four different auditors each propose a DIFFERENT replacement for the identical code block in agents/shared/routing.py lines 248-273 ('### Routing is a tool call — MANDATORY' through '"(one or two lines is plenty).",'). My verbatim check confirms all four anchor to the same 1,658-char span. This is one shared code block spliced into all six chain agents, not four independent cuts — applying any two produces garbage or a silent no-op, and the char-savings claims (933/1050/703/1020) are not additive. All four replacements are syntactically valid Python and none uses {hub}, so no f-prefix is needed.
>
> *Safer:* Present these as ONE decision with four candidate wordings. REC-09 (DCOI) is the tightest that still keeps all three behavioural clauses (mandate, halt consequence, don't-announce-instead-of-calling); pick it and mark the other three superseded.

#### DCOI-10 · COMPRESS · −957 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## Data Flow · *Golden rules:* 10, 6 · *auditor's own id:* REC-10

**Why:** The four 'Routing guidance' bullets duplicate routing_dc_output_inspector.md, which is spliced into the same prompt via {routing_instructions}.

**Risk:** The attempt-folder carry-through detail ('Current attempt:' + 'Parameters file:') is not in the routing fragment, so it is preserved here.

**Cut from** `## Data Flow
The hand-off from the Tool Caller contains a brief text report plus the`

**...through** `could not be performed.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Data flow
Include only your analysis and recommendation in the ``message`` — never repeat raw data, file contents, or QC numbers verbatim.  When you REVISE back to the Tool Caller, carry the ``Current attempt:`` and ``Parameters file:`` lines through so it writes into the right folder.
```

#### DCOI-11 · COMPRESS · −949 chars · risk medium

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## HARD RULE — never describe images you did not load this turn · *Golden rules:* 2, 5, 7 · *auditor's own id:* REC-11

**Why:** Six example phrasings plus two verbatim fill-in templates where one example and one template carry the same instruction.

**Risk:** This is the anti-hallucination patch from a real failure. The rule, the this-turn/this-hand-off scope, the pre-send self-check and one substitute template all survive; only the enumerated phrasings and the second template go.

**Cut from** `## HARD RULE — never describe images you did not load this turn`

**...through** `Never leave in a visual claim you cannot back with a this-turn load.`

**Replace with:**

```
## HARD RULE — never describe images you did not load this turn
Any visual claim ("the renders show…", "no holes are apparent…", "the geometry looks…") may appear ONLY after a successful ``view_images`` call THIS turn on THIS hand-off's paths — even paths identical to a prior cycle's, since the file contents changed.  A verdict from QC numerics alone is fine; pretending it came from images is not.

**Before you route, scan your ``message`` for visual language.**  Anything you cannot back with a this-turn load must be replaced, e.g. "GEOMETRY ANALYSIS: renders not loaded this turn — verdict based only on this hand-off's QC numerics: <the facts you use>", or the same marked as a PRIOR cycle's renders.
```

#### DCOI-12 · COMPRESS · −930 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## How to compare this cycle's design against user expectations · *Golden rules:* 9, 6 · *auditor's own id:* REC-12

**Why:** A prose re-description of five tools whose schemas are already bound; the only non-schema content is the ocr_regions batching hint and the 'judge intent' sentence.

**Cut from** `The user-input tools available to you (used as directed by the`

**...through** ```view_images`` call this turn.)`

**Replace with:**

```
Your user-input tools: ``list_input_files``, ``read_input_text``, ``read_image_notes``, ``view_images``, and ``ocr_regions`` (batch every region you want into ONE call).  Whichever sources you consult, judge whether the rendered design matches the user's intent — proportions, structural-element counts, overall style.  A visual claim about a reference image needs a this-turn ``view_images`` call too.
```

#### DCOI-13 · COMPRESS · −847 chars · risk low

*File:* `DC_prompt_fragments/tools_config/blade_sections_visualizer_dc_output_inspector.md` · *Section:* Blade-sections visualizer — DCOI overlay · *Golden rules:* 7, 6 · *auditor's own id:* REC-13

**Why:** Every instruction here is also stated in the precision-matching block and the routing fragment; the unique content is the side_by_side/layout/regions argument recipe.

**Cut from** `When a blade-sections image has been rendered (the Tool Caller's`

**...through** `Escalate only for a genuinely new design direction or a
blocker you cannot fix.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
View a rendered sections image by passing its path to ``view_images`` — side by side with the user's drawing (``side_by_side=True``, ``layout="match_height"``, and the recorded crop box in ``regions`` when the sketch is a large multi-part page).  Keep each round's feedback tightly focused on refining the section parameters; the fast loop may need many iterations.  To (re-)render sections on the SAME attempt, REVISE straight back with ``call_tool_caller`` — do not escalate, which would needlessly open a new attempt.
```

#### DCOI-14 · COMPRESS · −824 chars · risk medium

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## HARD RULES — what you must NEVER suggest · *Golden rules:* 2, 7 · *auditor's own id:* REC-14

**Why:** The ratio-vs-millimetre gotcha is real and load-bearing, but three worked phrasings and a two-branch thought experiment compress into one sentence plus the rule.

**Risk:** This encodes the '*Thickness/*Camber are % of that section's OWN chord' bug. The ambiguity, the required disambiguation, the both-numbers render block and the pinned-chord cap are all kept.

**Cut from** `**Name the quantity: ratio or absolute size.**  ``*Thickness`` and`

**...through** `section whose chord is pinned cannot grow in mm however far you push its
ratio.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
**Say which quantity you mean: ratio or millimetres.**  ``*Thickness`` and ``*Camber`` are percentages of that section's OWN chord, so "keep the thickness the same" has two opposite readings — hold the RATIO while the chord grows and the section looks thicker; hold the MILLIMETRES and it looks slimmer.  Every thickness/camber request, including a request to HOLD one, must say which.  The rendered-parameters block returns both numbers (``thickness 12% of chord (= 0.60 mm)``), and a section whose chord is pinned cannot grow in mm however far you push its ratio.
```

#### DCOI-15 · COMPRESS · −819 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ### Override authority and reporting upstream interpretation problems · *Golden rules:* 7, 2 · *auditor's own id:* REC-15

**Why:** Two paragraphs of justification for why the DCOI is well-placed to override, around three lines of actual instruction.

**Cut from** `### Override authority and reporting upstream interpretation problems`

**...through** `approving a design that visibly diverges from the user's intent is the
failure mode this prevents.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Override authority
You are the only agent that compares the RENDER against the source<<DCII_ONLY>> (the DCII checks parameters vs. extraction only)<</DCII_ONLY>>, so when the render visibly contradicts the user's intent you may recommend REVISE<<DCII_ONLY>>, overriding a DCII APPROVE,<</DCII_ONLY>> even with every parameter in range.  Escalate to the Orchestrator (not CLARIFY to the Tool Caller): a recovery plan is needed, not a re-run.  State what looks wrong and name the in-scope artefact that grounds it.  Use it on a clear visible contradiction, not on sub-resolution mismatches.
```

#### DCOI-16 · REPLACE_WITH_EXAMPLES · −767 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## Per-claim verification against the comparison source(s) in scope · *Golden rules:* 2, 11 · *auditor's own id:* REC-16

**Why:** Three bullets of 6-8 lines each defining categories the model can infer; the operative rules are count-in-the-render-only, quote-the-source, and say-so-when-unresolvable.

**Cut from** `  * **Visually verifiable** — a structural feature visible in the`

**...through** `see what you can't — trust falls on the upstream parameter
    authorisation chain.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Classify each claim: **visually verifiable** (element counts, presence of named features, qualitative shape, gross proportions — count in the RENDER only, never re-count the source, and quote both sides); **numerically checkable at coarse precision** against numbers already in your context (quote the comparison and name its source); or **not resolvable at render resolution** (sub-millimetre dimensions, fine angles, percentages with no visible manifestation) — say so plainly rather than pretending to see it.
```

#### DCOI-17 · DELETE · −728 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## HARD RULES — what you must NEVER suggest · *Golden rules:* 6, 3 · *auditor's own id:* REC-17

**Why:** Every clause of geometry_modification_rule.md (booleans/welding/remeshing/hole-filling/struts/no-mesh-fix, 'geometry changes only via parameters + regenerate') is already in $hard_constraints_dc, which is spliced into the SAME prompt ~100 lines later.

**Risk:** Keep the '## HARD RULES — what you must NEVER suggest' heading; the DCOI-specific rules below it still hang off it. The Orchestrator keeps the fragment.

**Cut from** `$geometry_modification_rule`

**...through** `$geometry_modification_rule`

**Replace with:** *(nothing — pure deletion)*

#### DCOI-18 · COMPRESS · −675 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## Loading render images (IMPORTANT) · *Golden rules:* 2, 5, 7 · *auditor's own id:* REC-18

**Why:** Three paragraphs explaining where the paths come from plus a four-bullet rule list, where the operative content is 'use only hand-off paths, never invent, escalate if none'.

**Cut from** `## Loading render images (IMPORTANT)
You do not receive render images automatically.`

**...through** `- One call to ``view_images`` per set of paths is enough — do
  not loop.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Loading render images
Renders are NOT attached automatically.  Call ``view_images`` with the exact paths given under the hand-off's ``Render images:`` label — never invent, guess, reconstruct or rename a path, and one call per set is enough.  If no paths were supplied, say so plainly, base your verdict on the text report alone, and ESCALATE.
```

#### DCOI-19 · COMPRESS · −664 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## Output Format · *Golden rules:* 11, 7 · *auditor's own id:* REC-19

**Why:** Each of the five section headers carries a 2-4 line gloss that restates rules already stated above (anti-fabrication, no numeric values, claim sourcing).

**Cut from** `## Output Format
Put your analysis in the ``message`` argument of your routing tool`

**...through** `direction; NO concrete numeric values, NO mesh-editing steps>`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Output format
Put your analysis in the ``message`` of your routing call.  Useful structure — not a rigid template; RECOMMENDATION is the one part downstream always needs:

CLAIMS CHECKED: <each claim, the artefact it came from, and the outcome>
GEOMETRY ANALYSIS: <what the renders show — only if loaded THIS turn>
DEFECTS: <issues found, or "None detected">
DESIGN INTENT COMPLIANCE: <shape, proportions, feature counts>
RECOMMENDATION: <APPROVE, or REVISE — qualitative, no concrete numbers, no mesh-editing steps>
```

#### DCOI-20 · COMPRESS · −660 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ### When to stop (you judge; a code cap backstops you) · *Golden rules:* 2, 5, 6 · *auditor's own id:* REC-20

**Why:** Three termination conditions each get a bolded label plus explanation, then the closing paragraph re-states two rules already given above.

**Cut from** `### When to stop (you judge; a code cap backstops you)`

**...through** `and never claim a match you did not see in a ``view_images`` call THIS turn.`

**Replace with:**

```
### When to stop
Finalize — naming which applies — when the shapes match as closely as the airfoil model allows (Satisfied), when they stopped meaningfully improving across ~2 rounds (Plateau), or when the hand-off carries ``PRECISION REFINE CAP REACHED``.  Then route to the Orchestrator and report the residual honestly, naming any remaining gap as the configurator's airfoil-model limit rather than implying more rounds would close it.
```

#### DCOI-21 · COMPRESS · −556 chars · risk low

*File:* `DC_prompt_fragments/dc_config/visual_inspection_guide.md` · *Section:* ## What a Correct Output Should Show · *Golden rules:* 3, 11 · *auditor's own id:* REC-21

**Why:** Genuine DC reference material and the only agent that uses it, but three bulleted lists compress into two prose runs with no loss of items.

**Risk:** Also absorbs the defect list from REC-22, so apply REC-21 and REC-22 together or keep the defect clause here.

**Cut from** `A propeller with correct geometry should show:`

**...through** `such and trust falls on the DCIC's parameter choice<<DCII_ONLY>> and the
DCII's authorisation check<</DCII_ONLY>>.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Correct geometry shows a continuous circular outer ring, the requested number of evenly spaced blades joining the hub to the ring, smooth blade surfaces, and proportions consistent with the input parameters (the outer-ring HEIGHT is derived from the outer blade section, not an input).

Visually checkable: blade count (top-down view), ring presence and continuity, hub presence and proportion, broad vs. narrow planform, rounded vs. squared tips, blade-to-ring connection vs. detached tips.  Watch for missing or malformed blades, self-intersections, disconnected elements, spikes, holes and degenerate faces.

NOT resolvable at render resolution: sub-millimetre thicknesses, exact twist angles, chord lengths within ~1 mm, camber / high-point percentages — mark such claims as unresolvable; trust falls on the DCIC's parameter choice<<DCII_ONLY>> and the DCII's authorisation check<</DCII_ONLY>>.
```

#### DCOI-22 · COMPRESS · −550 chars · risk low

*File:* `DC_prompt_fragments/tools_config/hard_constraints_tools.md` · *Section:* ### Tool-use hard rules (every agent) · *Golden rules:* 7, 8 · *auditor's own id:* REC-22

**Why:** Spliced into 8 agents; the append-only bullet in particular explains the rationale twice before stating the rule.

**Risk:** AFFECTS ALL 8 AGENTS. All three invariants (no invented paths, calculate-tool arithmetic, append-only attempts + render reuse) are retained.

**Cut from** `### Tool-use hard rules (every agent)`

**...through** `the Orchestrator only as a fallback) — never edit the old
  folder's parameters.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Tool-use hard rules (every agent)
- Never invent or guess a path: read tools take only the paths a hand-off label gives (``Input directory:`` / ``Extracted inputs file:`` / ``Parameters file:`` / ``Render images:`` / ``Current attempt:``) or an upstream tool's return value.
- Route EVERY arithmetic operation through the ``calculate`` tool — never mental arithmetic, LLM sums are unreliable — batching all of this turn's expressions into ONE call.
- Attempt folders are append-only: write only into the ``Current attempt:`` folder, never edit or delete a ``parameters.json`` or mesh already in one, and COPY an old parameter set into a NEW attempt rather than editing the old folder.  Re-running render/QC on an attempt that already has renders reuses them in place.
```

#### DCOI-23 · COMPRESS · −533 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## HARD RULES — what you must NEVER suggest · *Golden rules:* 7, 5 · *auditor's own id:* REC-23

**Why:** Three paragraphs make one point — stay qualitative, prefer relative magnitudes, exact values are the exception.

**Cut from** `Setting the parameter VALUES is not your job — that is the DC Input`

**...through** `and consistency
knowledge.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Setting parameter VALUES is the DC Input Creator's job.  Keep your feedback QUALITATIVE: describe the visual gap and name which of the $parameter_count parameters seem to need adjusting and in which direction — sharpened with a RELATIVE magnitude whenever you can judge one ("roughly twice as thick", "reduce the camber by about a third", "shift the high point slightly aft"), since a bare direction tells the DCIC nothing about step size.  Naming an exact value is the rare exception, not the habit.
```

#### DCOI-24 · COMPRESS · −508 chars · risk low

*File:* `DC_prompt_fragments/dc_config/hard_constraints_dc.md` · *Section:* ### Domain hard rules (every agent) · *Golden rules:* 2, 6 · *auditor's own id:* REC-24

**Why:** Spliced into 8 agents; the mesh-post-processing bullet and the no-invented-parameters bullet overlap heavily and the enumerated lists are illustrative.

**Risk:** AFFECTS ALL 8 AGENTS. Retains the parameter-only invariant with its canonical counter-examples, the no-post-processing rule, the unsupported-analysis list, and the three mesh metrics.

**Cut from** `### Domain hard rules (every agent)`

**...through** `rely on visual inspection and say so plainly.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Domain hard rules (every agent)
- Express a design ONLY in the $parameter_count named configurator parameters; invented ones (hub_radius, fillet_radius, tip_clearance, any "supplemental" parameter) do not exist — reject them.  Geometry changes ONLY by changing those parameters and regenerating via DC Input Creator → Tool Caller: there is no mesh editing and no post-processing of any kind (booleans, welding, remeshing, hole filling, manifold repair, fillets, chamfers, struts, supports).
- The system cannot offer performance or structural analysis (thrust, RPM, flow, pressure, efficiency, CFD, FEA, stress, material, load, tolerance), alternative output formats, other camera angles, cross-sections, or higher-resolution renders — the parameter set, tessellation and three fixed views are not negotiable.
- The only mesh metrics are watertightness, volume, and degenerate-face count; when mesh checks are off, rely on visual inspection and say so.
```

#### DCOI-25 · COMPRESS · −489 chars · risk low

*File:* `agents/shared/prompt_fragments/routing_dc_output_inspector.md` · *Section:* ### Available routing tools · *Golden rules:* 9, 6 · *auditor's own id:* REC-25

**Why:** Becomes the single source for routing guidance once REC-10 removes the duplicate in prompt.md; the closing 'you are the last agent' sentence is already emitted by the routing_instructions builder immediately above it.

**Cut from** `### Available routing tools
- ``call_tool_caller(message)`` — REVISE that needs only a (re-)render`

**...through** `handing control back to the Orchestrator via ``call_orchestrator`` with
an APPROVE verdict.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Available routing tools
- ``call_tool_caller(message)`` — a REVISE needing only a (re-)render of the
  SAME design on the CURRENT attempt (blade sections, or a failed render).
  It renders; it does not author parameters, so never use it for a
  parameter/design change.
- ``call_orchestrator(message)`` — APPROVE (this is also how you "complete
  normally"); a REVISE needing a PARAMETER/design change, which it re-plans
  via Planner → DCIC → new attempt; or an ESCALATE.
```

#### DCOI-26 · COMPRESS · −488 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## Do NOT mix cycles when forming a verdict · *Golden rules:* 6, 5 · *auditor's own id:* REC-26

**Why:** Two of its three bullets restate the anti-fabrication HARD RULE above; the unique content is 'mark prior numbers as prior'.

**Cut from** `## Do NOT mix cycles when forming a verdict`

**...through** `Do not fuse old and new observations into one undifferentiated summary;
prior cycles are context, not substitute evidence.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Judge the CURRENT cycle
The verdict rests on THIS cycle's evidence.  You may cite earlier cycles for progress ("degenerate faces 43 → 19"), but mark prior numbers as prior and never carry a prior cycle's observation forward as if fresh.
```

#### DCOI-27 · DELETE · −485 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## What to Look For · *Golden rules:* 6, 3 · *auditor's own id:* REC-27

**Why:** A generic defect list sitting directly beneath $visual_inspection_guide, which the block itself admits is the authoritative version.

**Risk:** REC-21's replacement absorbs the defect items (missing/malformed blades, self-intersections, disconnected elements, spikes, holes, degenerate faces). If REC-21 is not applied, keep one line of this list.

**Cut from** `## What to Look For
- Missing or malformed structural elements`

**...through** `and what is / is not visually resolvable lives in the
visual-inspection guide above.)`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

#### DCOI-28 · COMPRESS · −450 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* ### How to decide where to route (routing_instructions builder) · *Golden rules:* 10, 2 · *auditor's own id:* REC-28

**Why:** Four bullets narrating a routing protocol that the bound call_<agent> tool schemas already encode; collapses to one bullet without losing a branch.

**Risk:** AFFECTS ALL 6 CHAIN AGENTS. The exact f-string must be reassembled carefully — {hub} interpolation is preserved.

**Cut from** `"### How to decide where to route",`

**...through** `"can fix it, route to the {hub} (ESCALATE).",`

**Replace with:**

```
        "### How to decide where to route",
        f"- Route FORWARD when your work succeeded and the {hub} did not "
        "ask you to report back (no instruction means continue).  Route "
        f"to the {hub} when it did ask, or when something is "
        "fundamentally wrong that no chain agent can fix (ESCALATE).  "
        "Route to the previous agent only when IT can fix an ambiguity, "
        "missing datum or error in its own hand-off (CLARIFY).",
```

#### DCOI-29 · COMPRESS · −444 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## Per-claim verification against the comparison source(s) in scope · *Golden rules:* 6, 5 · *auditor's own id:* REC-29

**Why:** An eight-line restatement of the SOFT TARGET definition given verbatim in $value_states two sections earlier; only the DCOI-specific consequence is new.

**Cut from** `**A SOFT TARGET is not a claim to enforce.**  When the source marks a value`

**...through** `flag it only if the render moved
AWAY from the goal.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
**A SOFT TARGET is not a claim to enforce** — judge that value against its GOAL, never against the exact number, and flag it only if the render moved AWAY from the goal.
```

#### DCOI-30 · DELETE · −443 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ### Verdict shape · *Golden rules:* 6 · *auditor's own id:* REC-30

**Why:** Describes the output template that the '## Output Format' section renders literally further down the same prompt.

**Risk:** Requires the CLAIMS CHECKED line to remain in the Output Format block (it does, in REC-19's replacement).

**Cut from** `### Verdict shape

Add one short ``COMPARISON-SOURCE CLAIMS CHECKED`` section to`

**...through** `the existing GEOMETRY ANALYSIS / DEFECTS / DESIGN INTENT
COMPLIANCE / RECOMMENDATION blocks.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:** *(nothing — pure deletion)*

#### DCOI-31 · COMPRESS · −441 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ### Stale images in your history — you choose whether to re-load · *Golden rules:* 7, 2 · *auditor's own id:* REC-31

**Why:** One paragraph of hedging around a two-clause decision rule.

**Risk:** Keep the {image_persistence_block} placeholder immediately above this text untouched.

**Cut from** `Re-loading is neither automatic nor mandatory: load the current renders`

**...through** `rest on text, or refer to the earlier
(unchanged) images, naming them as such.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Re-load the current renders when a fresh visual judgement changes your verdict or your diagnosis of WHICH parameters are off; skip them when QC alone decides (e.g. the mesh isn't watertight), and never call ``view_images`` when the hand-off says no new renders were produced — rest on text, or cite the earlier images as unchanged.
```

#### DCOI-32 · MERGE · −430 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## End-of-session feedback message (read-only) · *Golden rules:* 4, 7 · *auditor's own id:* REC-32

**Why:** Two shared fragments plus a six-line scope enumeration to say 'a feedback message may arrive; treat it as ground truth'.

**Risk:** Drops the $eos_feedback_intro / $eos_feedback_outro slots for the DCOI only; the other 6 agents keep them.

**Cut from** `## End-of-session feedback message (read-only)

$eos_feedback_intro`

**...through** `$eos_feedback_outro`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## End-of-session feedback (read-only)
At session end the Orchestrator MAY append one final ``HumanMessage`` (``name="orchestrator"``) carrying user feedback on your scope — your APPROVE/REVISE verdicts, your render-vs-source count and claim checks, your use of override authority, and whether visual claims were grounded in a this-turn load.  Treat it as ground truth.
```

#### DCOI-33 · COMPRESS · −398 chars · risk low

*File:* `DC_prompt_fragments/tools_config/blade_sections_visualizer.md` · *Section:* ### Blade-sections visualizer · *Golden rules:* 7, 8 · *auditor's own id:* REC-33

**Why:** Spliced into all 9 agents; the 'why it is faster' explanation and the shown-to-the-user aside do not change any agent's behaviour.

**Risk:** AFFECTS ALL 9 AGENTS.

**Cut from** `### Blade-sections visualizer

The system can render JUST the blade cross-sections`

**...through** `and can even be the final deliverable.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Blade-sections visualizer
The Tool Caller's ``render_blade_sections`` renders just the three blade cross-sections (Inner, Middle, Outer, each at its true angle of attack) from an attempt's parameters file, skipping full 3D mesh generation.  Being much faster, a section-focused request can be refined cheaply on it alone, and it can be the final deliverable.
```

#### DCOI-34 · COMPRESS · −380 chars · risk low

*File:* `agents/dc_output_inspector/dc_output_inspector.py` · *Section:* _IMAGE_PERSISTENCE_ON / _IMAGE_PERSISTENCE_OFF · *Golden rules:* 7, 4 · *auditor's own id:* REC-34

**Why:** Describes an implementation detail (paired text blocks, stripping at hand-off) in more words than the behavioural consequence needs.

**Cut from** `_IMAGE_PERSISTENCE_ON = """\
You are STATEFUL: render images loaded in earlier cycles remain in`

**...through** ```view_images``.  Mode: KEEP IMAGES IN CONTEXT (OFF)."""`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
_IMAGE_PERSISTENCE_ON = """\
Images you loaded in earlier cycles are STILL in your history, each with
its ``Loaded image (path: …):`` label.  They show PAST designs."""

_IMAGE_PERSISTENCE_OFF = """\
Image bytes from earlier cycles are STRIPPED from your history at every
hand-off; only the ``Loaded image (path: …):`` labels remain.  Re-load
from those paths with ``view_images`` to see them again."""
```

#### DCOI-35 · COMPRESS · −360 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* ### Permission / authorisation issues → hub (routing_instructions builder) · *Golden rules:* 7, 6 · *auditor's own id:* REC-35

**Why:** Two paragraphs to say: re-read the hand-off once, act on an authorisation it already carries, otherwise escalate; CLARIFY is for data problems.

**Risk:** AFFECTS ALL 6 CHAIN AGENTS. The _authorisation_sources(hub) call is preserved.

**Cut from** `f"### Permission / authorisation issues → {hub} (not "`

**...through** `"NOT for permission questions.",`

**Replace with:**

```
        f"### Permission / authorisation issues → {hub}",
        "Before escalating over a missing authorisation, re-read the "
        "incoming hand-off (and any file it points to) ONCE.  If it "
        "already names an authorisation that plausibly covers the action "
        "— even in different wording — act on it; do not bounce back for "
        "a ritual re-confirmation.  When it is truly missing or "
        f"ambiguous, ESCALATE to the {hub}: "
        + _authorisation_sources(hub) + "  CLARIFY back to the previous "
        "agent only for data / wording / format issues it can fix.",
```

#### DCOI-36 · DELETE · −350 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* ### Do not loop — ESCALATE when stuck (routing_instructions builder) · *Golden rules:* 6, 5 · *auditor's own id:* REC-36

**Why:** Verbatim duplicate of the "DON'T loop: if you are about to call the same tool with the same arguments" bullet in generic_constraints.md, which is spliced into the same prompt.

**Risk:** AFFECTS ALL 6 CHAIN AGENTS. Only safe if generic_constraints.md keeps its no-loop bullet — REC-03's replacement does.

**Cut from** `"### Do not loop — ESCALATE when stuck",`

**...through** `"consult another agent, or ask the user.  Never silently loop.",`

**Replace with:** *(nothing — pure deletion)*

#### DCOI-37 · COMPRESS · −296 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## Comparing against a prior attempt · *Golden rules:* 9, 7 · *auditor's own id:* REC-37

**Why:** Narrates a three-call tool sequence the schemas already describe; the operative bits are 'read_attempt returns a path, not an image' and 'cite the attempt number'.

**Cut from** `## Comparing against a prior attempt
To compare the current design against an earlier cycle:`

**...through** `Planner / DCIC / Orchestrator can cross-reference; you do not create
attempts.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Comparing against a prior attempt
``list_attempts()`` finds it; ``read_attempt(n, 'render_isometric.png')`` returns that render's ABSOLUTE PATH (not viewable on its own, and it also returns a prior ``parameters.json`` / ``description.txt``); then ``view_images([path])``.  Cite the attempt number.  You never create attempts.
```

#### DCOI-38 · COMPRESS · −264 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## Per-claim verification against the comparison source(s) in scope · *Golden rules:* 7, 11 · *auditor's own id:* REC-38

**Why:** Parenthetical justifications for why the DCOI does not re-check parameters or re-count features.

**Cut from** `## Per-claim verification against the comparison source(s) in scope

Your job: does the tool caller's rendered OUTPUT match`

**...through** `enumerate
the checkable claims the source encodes and check each against the
RENDER, deciding the outcome:`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Per-claim verification
Does the rendered OUTPUT match what the in-scope source asks for?  You do NOT re-check parameters (three agents already did) or re-count the source's own features (the UII established them) — take its stated values as given.  Don't approve on coarse similarity: enumerate the source's checkable claims and check each against the RENDER.
```

#### DCOI-39 · COMPRESS · −213 chars · risk low

*File:* `agents/dc_output_inspector/prompt.md` · *Section:* ## How to compare this cycle's design against user expectations · *Golden rules:* 7 · *auditor's own id:* REC-39

**Why:** Explains that a session setting chose the block below, which the block below states itself.

**Risk:** Keep the {comparison_mode_block} placeholder that follows.

**Cut from** `## How to compare this cycle's design against user expectations

The set of comparison sources you draw on`

**...through** `below describes the mode in effect for THIS session — follow it.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Comparison sources (the mode in effect this session)
```

</details>

<details><summary><b>Proposed shape of the shrunk prompt</b></summary>

```
DC Output Inspector — post-cut skeleton (est. ~2,400 tok / ~9,600 chars assembled)

  Preamble: "You are the DC Output Inspector for a $domain_description."      ~20 tok
  ## Your Role  (unchanged, 3 numbered sources of evidence)                   ~55 tok
  ## Loading render images  (REC-18)                                          ~85 tok
  ### Stale images — {image_persistence_block} (REC-34) + re-load rule (31)  ~130 tok
  ## HARD RULE — never describe images you did not load this turn (REC-11)   ~175 tok
  ## Comparison sources (the mode in effect this session) (REC-39)            ~15 tok
      {comparison_mode_block}  (REC-06, mode 3 default)                      ~160 tok
      user-input tool line (REC-12)                                           ~95 tok
  ## Sketch handling  (REC-01 inline, replaces $sketch_handling+$sketch_notes) ~150 tok
  ## Precision section-matching (REC-07)                                      ~255 tok
  ### When to stop (REC-20)                                                    ~85 tok
  ### 3D precision check (REC-08)                                             ~125 tok
  ## The three states of a user value — $value_states (REC-04)                ~275 tok
  ## Per-claim verification (REC-38)                                           ~85 tok
      SOFT TARGET one-liner (REC-29)                                           ~40 tok
      three claim classes (REC-16)                                            ~110 tok
  ### Override authority (REC-15)                                             ~115 tok
  ## What a Correct Output Should Show — $visual_inspection_guide (REC-21)    ~160 tok
      [## What to Look For — DELETED, REC-27]                                    0
  ## Comparing against a prior attempt (REC-37)                                ~80 tok
  ## Judge the CURRENT cycle (REC-26)                                          ~55 tok
  ## HARD RULES — what you must NEVER suggest
      [$geometry_modification_rule — DELETED, REC-17]                             0
      qualitative feedback + relative magnitudes (REC-23)                     ~115 tok
      ratio-vs-millimetres (REC-14)                                           ~135 tok
  ## Output format (REC-19)                                                   ~130 tok
  ## Data flow (REC-10)                                                        ~65 tok
  ## End-of-session feedback (REC-32)                                          ~85 tok
  ## Hard constraints — generic $hard_constraints_generic (REC-03)            ~345 tok
  ## Hard constraints — DC-specific $hard_constraints_dc (REC-24)             ~190 tok
  ## Hard constraints — tool-specific $hard_constraints_tools (REC-22)        ~180 tok
  <<BSV_ON>> blade-sections visualizer (REC-33) + DCOI overlay (REC-13)       ~215 tok
  {routing_instructions}  (REC-28 / 35 / 36 / 09 + fragment REC-25)           ~330 tok
                                                                    TOTAL  ~2,360 tok
```

</details>

**Auditor notes.** MEASUREMENT BASIS. Assembled DCOI ≈ 46,000 chars (11,505 tok). Sources: prompt.md 22,188 chars; $-fragments 23,931; {routing_instructions} ≈ 4,550 rendered; {comparison_mode_block} (mode 3, the default) ≈ 2,535; {image_persistence_block} ≈ 344. <<HAS_DBA>> is stripped under RAG_ENABLED=False, so the four database fragments cost nothing today — I proposed no cuts there (they would be free money if RAG is ever switched on: database_search.md + per-agent overlay + retrieve_user_inputs.md + retrieve_attempt.md are ~4k chars the DCOI would inherit).

TOTALS. 39 cuts, 39,000 chars removed by my count (each figure = file bytes of the quoted span minus the exact length of the replacement I wrote). REC-02 (2,380) touches the two INACTIVE comparison modes, so it does not move the measured baseline; effective reduction is ~36,600 chars → ~9,400 chars ≈ 2,350 tok. That is a 79% cut, inside the 1,000–3,000 target.

THE 16-PARAMETER LIST. The DCOI does NOT splice $parameter_list today — it only references $parameter_count. Nothing in these cuts touches the parameter list, and I did not propose adding one. If the owner wants the DCOI to reason about ranges it currently cannot, that is an ADDITION, not part of this shrink.

WHAT I DELIBERATELY DID NOT CUT.
 - The precision-matching feature (REC-07/08/20) survives as ~465 tok rather than being deleted. It is five commits of production work and encodes real invariants (never approve the first sections render; the sketch crop overrides the comparison-source mode; SOFT TARGET counts as a lever in the 3D loop). I compressed hard but kept every one of those.
 - The anti-hallucination HARD RULE (REC-11), the routing-is-a-tool-call mandate (REC-03/09), and the ratio-vs-millimetre rule (REC-14) are all named production failures. Each keeps its imperative and its one behavioural consequence; only the repetition and the enumerated example phrasings go.
 - The DCII per-parameter range check is not in this prompt (it lives in the DCII), so nothing here weakens it.
 - I did NOT cut ``## Your Role`` (55 tok) or the domain preamble — already minimal.

MECHANICAL WARNINGS FOR APPLYING THESE.
 1. prompt.md is BOTH a string.Template target ($slot) and a .format() target ({slot}). None of my replacements introduce a literal ``{`` or ``}``, and every runtime placeholder ({image_persistence_block}, {comparison_mode_block}, {routing_instructions}) is preserved verbatim. If you edit my replacement text, any literal brace you add must be doubled — this is the known brace-escape trap.
 2. REC-01 and REC-05 remove the DCOI's only references to $sketch_handling / $sketch_notes; REC-17 removes its only $geometry_modification_rule reference; REC-32 removes its $eos_feedback_intro / $eos_feedback_outro references. FRAGMENT_TO_SLOT in agents/shared/prompts.py is unaffected (other agents still use all of them), but the System Prompts UI's "used by N agents" badge will drop by one for each.
 3. REC-15 and REC-21 keep <<DCII_ONLY>> markers; REC-03 keeps <<CHAIN_ONLY>> markers. Verify the pairs still balance after editing — the prompts_admin validator has a known gap here, so a broken marker fails silently at assembly.
 4. REC-28/35/09/36 land in agents/shared/routing.py as Python string literals inside a `lines += [...]` list, not in a .md file. Reassemble the f-string quoting exactly as written; {hub} and _authorisation_sources(hub) must survive.
 5. REC-21 (visual guide) absorbs the defect list that REC-27 deletes. Apply REC-21 if you apply REC-27, or keep one line of the defect list.
 6. REC-30 (Verdict shape) assumes REC-19's Output Format replacement keeps the CLAIMS CHECKED line. It does.
 7. REC-36 assumes generic_constraints.md keeps its no-loop bullet. REC-03's replacement does.

HIGHEST-LEVERAGE / HIGHEST-RISK ORDERING. If the owner wants a fast 60% with minimal blast radius, apply REC-01, REC-05, REC-06, REC-07, REC-08, REC-10, REC-17, REC-27, REC-30 first — all DCOI-local, ~15,000 chars, no other agent affected. The four shared-fragment cuts (REC-03 generic_constraints ×8 agents, REC-22 tools ×8, REC-24 dc ×8, REC-33 bsv ×9) and the four routing.py cuts (×6 chain agents) are worth ~5,900 chars in the DCOI alone and roughly 6× that fleet-wide, but they should be reviewed against the other eight prompts before landing.

TESTING (golden rule 12). Cut by testing: I would run the Sessions Queue benchmark set with the DCOI-local cuts applied first, watching specifically for (a) a fabricated visual claim without a view_images call, (b) an approved first sections render under a precision directive, and (c) a thickness request that omits ratio-vs-mm. Those three are the failure modes the compressed rules are carrying.

---

### 4.9 Database Handler — 5,505 → ~1,740 tok

| ID | action | section | −chars | rules | risk | what |
|---|---|---|---:|---|---|---|
| **DH-01** | SCOPE_PER_AGENT | ## What you know about the system → ### The agents you may i | 2887 | 3,6,8 | medium | $available_agents is a near-duplicate of $agent_tools_overview_brief (which the DH also splices and which was purpose-built for it), and because available_agents.md nests ``$tool_inventory`` it silently drags the ENTIRE 881-char tool inventory into the DH prompt on the second substitution pass — exactly what prompts.py line 376-381 claims the brief fragment prevents. |
| **DH-02** | COMPRESS | ## Identifying attempt-specific questions — the force-tool p | 925 | 7,10,9 | low | Most of this narrates code the model cannot influence (3 validation retries, then the system synthesises an empty list; the tool's own schema documents the accepted id forms), and the ONE-vs-TWO+ SAVE shapes are already specified in the Semantic-fields section. |
| **DH-03** | COMPRESS | ## Per-field protocol | 787 | 7,10,11 | low | A four-step numbered narration of the orchestration loop the DH does not control; only the two output prefixes and the 'prefix must be the first characters' rule change its behaviour. |
| **DH-04** | SCOPE_PER_AGENT | ## What you know about the system → blade-sections block | 743 | 8,3 | low | The blade-sections visualizer fragment explains WHEN to render sections cheaply instead of a full 3D mesh — a decision the DH never makes; it only records what the other agents say they did. |
| **DH-05** | REPLACE_WITH_EXAMPLES | ## Three kinds of questions | 697 | 2,7,11 | low | Three kinds explained with two examples each plus a paragraph of justification per kind; one canonical example per kind carries the same distinction. |
| **DH-06** | COMPRESS | ### Semantic fields → **Rules.** | 683 | 5,6,7 | medium | Five bullets of which two restate the block syntax already shown in the code fence above and one explains why N independent pairs are acceptable; only the short-QUESTION rule and the per-pair cap steer behaviour. |
| **DH-07** | COMPRESS | ### Semantic fields → **Identifying attempt-specific Q with  | 649 | 3,7,10 | low | The filename-suffix scheme (single vs double underscore, combined suffixes for sub-rows) is code-side bookkeeping the DH never writes; only the ATTEMPT:-header shape and the no-further-splitting rule affect its output. |
| **DH-08** | COMPRESS | ### Quantitative fields | 607 | 2,6,7 | low | Five bullets plus a justification paragraph for one rule: 'copy it verbatim, no headers, no cap, one sentence if empty'. |
| **DH-09** | COMPRESS | ### Rules of authorship | 568 | 5,6 | low | Five bullets that each restate something already stated: bullet 1 = the '## What you SAVE' intro, bullet 4 = the ASK:/SAVE: loop, bullet 5 = the Quantitative-fields section verbatim. |
| **DH-10** | COMPRESS | ### Semantic fields | 564 | 2,5,11 | low | Two code fences showing the same block grammar (one block vs two blocks) plus prose describing both; one fence and one sentence carry it. |
| **DH-11** | COMPRESS | (fragment body — the per-agent bullets) | 543 | 2,6,8 | low | One line per agent is enough for the DH to know who to attribute an answer to; the second sentences ('Bridge between user and pipeline', 'Only agent that interprets raw user content', 'May open attempt folders only as a fallback') are chain-operational detail the DH never acts on. |
| **DH-12** | DELETE | ### Output format (strict) | 454 | 5,6 | low | Third statement of the same contract: the ASK:/SAVE: prefixes and the 'first character' rule are in the Per-field protocol, and the semantic-vs-quantitative body shapes are each stated in their own section. |
| **DH-13** | COMPRESS | ## Three kinds of questions → sub-row note | 382 | 1,7 | low | An incident patch spelled out over seven lines with two rationales and three spellings of the id ('attempt NNN' / 'attempt #NNN'); the one-line general principle covers all of them. |
| **DH-14** | MERGE | ### The token budget for SEMANTIC answers | 369 | 5,6 | low | States the embedding cap and the 'prefer <600' guidance up front, then restates both in the Semantic-fields rules; the second statement is the one adjacent to where the text is actually written. |
| **DH-15** | COMPRESS | ## How you operate | 347 | 4,7 | low | 'You are a stateful agent … so you ask coherent follow-ups and never repeat yourself' is default behaviour; the implementation detail ('the system rebuilds its history from a frozen snapshot before every new field') explains the why without changing what the DH does. |
| **DH-16** | COMPRESS | ## Tools | 317 | 7,9 | low | Enumerates every turn type on which the DH has no tools (session-scoped Qs, sub-rows, SAVE: emits, ASK: rounds) when 'every other turn' says it once. |
| **DH-17** | COMPRESS | #### Rewrite rules → 1. Strip every file path | 304 | 1,2,7 | low | Four enumerated path shapes (/app/attempts, /app/inputs, render PNGs, a literal timestamped slug) are one general principle plus one canonical example. |
| **DH-18** | COMPRESS | #### Rewrite rules → 2. Strip routing-tool wrappers | 302 | 2,7 | low | The mechanism (agents end their turn by invoking a routing tool, so their reply is a JSON wrapper) is explained before the rule; the example alone teaches it. |
| **DH-19** | DELETE | (fragment preamble) | 289 | 4,7 | low | Meta-commentary about the fragment itself, and its claim ('chain agents see a fuller, tool-level overview that does not appear in your prompt') is factually false today — $available_agents splices the full tool inventory into the DH prompt. |
| **DH-20** | COMPRESS | #### Rewrite rules → 6. Self-contained and declarative | 277 | 2,4 | low | Four pronoun examples plus three filler-word examples plus a rationale sentence; one example of each carries it, and 'avoid filler' is close to default behaviour anyway. |
| **DH-21** | COMPRESS | ## The questions you ASK Agent A → ### Question wording | 269 | 7,11 | low | A hedged permission paragraph ('You MAY adapt the wording slightly … IF such adaptation is genuinely useful AND it does not drift …') compresses to one sentence without changing the permission. |
| **DH-22** | COMPRESS | ## The questions you ASK Agent A → ### Asked question — leng | 232 | 5,11 | low | Two headings and a paragraph to say 'the asked question is not embedded, so spend tokens on it'. |
| **DH-23** | COMPRESS | ## The questions you ASK Agent A → ### Asked question — keep | 224 | 7,11 | low | Same three reminders, with the per-item justifications ('noise once stored; files are archived elsewhere', 'post-session there is no chain') folded away. |
| **DH-24** | COMPRESS | #### Rewrite rules → 7. Domain-faithful | 221 | 2,7 | low | Keeps the rule and its one worked example; drops the explanation of why glossing helps the vector. |
| **DH-25** | COMPRESS | #### Rewrite rules → 5. Replace parameter-value dumps with r | 219 | 2,7 | low | The ``bladeCount = 6 — [3,6]`` sample dump and the '$parameter_count parameter values' framing are illustration; the rule plus the four reasoning categories is the whole instruction. |
| **DH-26** | COMPRESS | #### Rewrite rules → 3. Unescape JSON string escapes | 217 | 7 | low | States the transform, then restates it in the negative ('never the backslash-letter escape sequences') and explains the provenance ('artefacts of JSON-stringified content'). |
| **DH-27** | COMPRESS | ## What you SAVE (the body of ``SAVE:``) | 216 | 5,11 | low | A section intro announcing that the two subsections below differ — the two ### headings already announce that. |
| **DH-28** | COMPRESS | ## What you know about the system → ### The design configura | 174 | 7,11 | low | A heading plus five lines to convey one fact; 'See the agents' own histories for the specific values' is a redundant pointer (the histories are the DH's only input). |
| **DH-29** | COMPRESS | ## The questions you ASK Agent A → negation-acceptable wordi | 158 | 6,7 | low | Says the same thing twice ('Agent A is expected to say so explicitly — that is a valid answer' then 'word the question so that … is an obviously acceptable response'). |
| **DH-30** | COMPRESS | #### Rewrite rules → 4. Drop mid-chain narration | 128 | 2 | low | Three near-identical example sentences collapse to one. |
| **DH-31** | COMPRESS | #### Rewrite rules → 9. Negation-canonical | 128 | 2,7 | low | Keeps the canonical sentence (the whole point of the rule) and drops the negative restatement 'do not leave the body empty, ambiguous, or filled with hedges'. |
| **DH-32** | COMPRESS | #### Rewrite rules → 8. One topic per file | 127 | 2,4 | low | 'Each field is one concept; do not bundle multiple fields' content' is the heading restated, and two meta-commentary examples become one. |
| **DH-33** | COMPRESS | #### Rewrite rules for the saved QUESTION + ANSWER (semantic | 54 | 11 | low | Heading and its one-line gloss say the same thing; merge into the heading. |

<details><summary><b>Full text of each change</b></summary>

#### DH-01 · SCOPE_PER_AGENT · −2887 chars · risk medium

*File:* `agents/database_handler/prompt.md` · *Section:* ## What you know about the system → ### The agents you may interview · *Golden rules:* 3, 6, 8 · *auditor's own id:* REC-01

**Why:** $available_agents is a near-duplicate of $agent_tools_overview_brief (which the DH also splices and which was purpose-built for it), and because available_agents.md nests ``$tool_inventory`` it silently drags the ENTIRE 881-char tool inventory into the DH prompt on the second substitution pass — exactly what prompts.py line 376-381 claims the brief fragment prevents.

**Risk:** This is the only place the DH is told 'you never call the Receptionist directly; route to the Orchestrator'. That instruction is already wrong for the DH (it has no routing tools at all, only save_attempt_data), so removing it is a correction, not a loss. All eight agent roles survive in the brief overview immediately below. Only the DH's prompt.md changes — the Planner and the 5-agent Conductor keep their own $available_agents splice untouched.

**Cut from** `### The agents you may interview`

**...through** `$available_agents`

**Replace with:** *(nothing — pure deletion)*

#### DH-02 · COMPRESS · −925 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ## Identifying attempt-specific questions — the force-tool protocol · *Golden rules:* 7, 10, 9 · *auditor's own id:* REC-02

**Why:** Most of this narrates code the model cannot influence (3 validation retries, then the system synthesises an empty list; the tool's own schema documents the accepted id forms), and the ONE-vs-TWO+ SAVE shapes are already specified in the Semantic-fields section.

**Risk:** The two behavioural invariants — mandatory single call with no text, and [] when no attempt was named — are preserved verbatim in the replacement.

**Cut from** `## Identifying attempt-specific questions`

**...through** `it is bound only for this force-tool turn.`

**Replace with:**

```
## The force-tool turn

After Agent A answers an identifying attempt-specific question you MUST
call ``save_attempt_data`` once, and emit no text that turn.  Pass one id
per attempt Agent A identified, or ``[]`` when it named none — the system
then drops that question and its sub-rows.  Then emit the SAVE: body.
Never call this tool on any other turn.
```

#### DH-03 · COMPRESS · −787 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ## Per-field protocol · *Golden rules:* 7, 10, 11 · *auditor's own id:* REC-03

**Why:** A four-step numbered narration of the orchestration loop the DH does not control; only the two output prefixes and the 'prefix must be the first characters' rule change its behaviour.

**Risk:** The prefix-at-first-character rule is the parser contract and is kept word-for-word in intent.

**Cut from** `## Per-field protocol`

**...through** `(or your last reply, if you never produced one).  Do not deliberately
stall.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Per-field loop

The system gives you the field's name, type and schema description.  You
write ONE question for Agent A; the system delivers it and returns the
reply.  Then answer with EXACTLY one of these, as the very first
characters of your output (anything before the prefix is rejected):

    ASK: <follow-up question for Agent A>
    SAVE: <the final text written to the .txt file>

Use ``ASK:`` while the answer does not yet cover the field; ``SAVE:``
once it does.  ASK: rounds are capped — do not stall.
```

#### DH-04 · SCOPE_PER_AGENT · −743 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ## What you know about the system → blade-sections block · *Golden rules:* 8, 3 · *auditor's own id:* REC-04

**Why:** The blade-sections visualizer fragment explains WHEN to render sections cheaply instead of a full 3D mesh — a decision the DH never makes; it only records what the other agents say they did.

**Risk:** If an interviewed agent mentions a sections render, the DH still records it faithfully; it never needs to know the tool's cost model. Removes the slot reference from the DH prompt only — the other eight agents' <<BSV_ON>> blocks are untouched.

**Cut from** `<<BSV_ON>>`

**...through** `<</BSV_ON>><<BSV_OFF>>$blade_sections_visualizer_off<</BSV_OFF>>`

**Replace with:** *(nothing — pure deletion)*

#### DH-05 · REPLACE_WITH_EXAMPLES · −697 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ## Three kinds of questions · *Golden rules:* 2, 7, 11 · *auditor's own id:* REC-05

**Why:** Three kinds explained with two examples each plus a paragraph of justification per kind; one canonical example per kind carries the same distinction.

**Cut from** `## Three kinds of questions`

**...through** `sub-rows receive so Agent A knows which attempt to answer about.`

**Replace with:**

```
## Three kinds of schedule row

1. **Session-related** (``Q1``, ``Q3`` …) — about the session as a whole
   ("what was the user's original request?").
2. **Identifying attempt-specific** (``Q2``, ``Q6`` — scope ``attempt``,
   no ``.`` in the number) — pins down ONE design attempt ("which attempt
   best satisfied the request?").
3. **Attempt-specific sub-rows** (``Q2.1``, ``Q6.2``) — about the attempt
   their parent pinned down; the system prepends ``"For attempt NNN: "``
   to the description Agent A receives.
```

#### DH-06 · COMPRESS · −683 chars · risk medium

*File:* `agents/database_handler/prompt.md` · *Section:* ### Semantic fields → **Rules.** · *Golden rules:* 5, 6, 7 · *auditor's own id:* REC-06

**Why:** Five bullets of which two restate the block syntax already shown in the code fence above and one explains why N independent pairs are acceptable; only the short-QUESTION rule and the per-pair cap steer behaviour.

**Risk:** This is the ONLY surviving statement of the per-pair embedding token cap if REC-13 (the '### The token budget for SEMANTIC answers' section) is also applied. Keep the $embedding_max_response_tokens clause in the replacement verbatim.

**Cut from** `**Rules.**`

**...through** `system will ask you ONCE for shorter version(s).`

**Replace with:**

```
The saved ``QUESTION`` is NOT the long question you asked — it is a short
(under 80 token) self-contained rewrite that must embed well on its own.
Each ``QUESTION``+``ANSWER`` pair must stay under
$embedding_max_response_tokens cl100k_base tokens; prefer well under 600
per pair.
```

#### DH-07 · COMPRESS · −649 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ### Semantic fields → **Identifying attempt-specific Q with MULTIPLE resolved attempts.** · *Golden rules:* 3, 7, 10 · *auditor's own id:* REC-07

**Why:** The filename-suffix scheme (single vs double underscore, combined suffixes for sub-rows) is code-side bookkeeping the DH never writes; only the ATTEMPT:-header shape and the no-further-splitting rule affect its output.

**Cut from** `**Identifying attempt-specific Q with MULTIPLE resolved attempts.**`

**...through** ```<field>__002_1.txt``, ``<field>__002_2.txt``.)`

**Replace with:**

```
When the force-tool resolved MORE THAN ONE attempt, emit one block per
attempt, each headed by an ``ATTEMPT: NNN`` line before its ``QUESTION:``
line, and do not split further at that level.
```

#### DH-08 · COMPRESS · −607 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ### Quantitative fields · *Golden rules:* 2, 6, 7 · *auditor's own id:* REC-08

**Why:** Five bullets plus a justification paragraph for one rule: 'copy it verbatim, no headers, no cap, one sentence if empty'.

**Risk:** 'preserve every number, unit, parameter name, structural marker' is the guard against the DH paraphrasing away a saved parameter set — kept in the replacement.

**Cut from** `### Quantitative fields`

**...through** `explaining the absence (e.g. ``No parameter set was approved this
  session.``).`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
### Quantitative fields

Save Agent A's answer verbatim as a single block with no ``QUESTION:`` /
``ANSWER:`` headers — keep every number, unit, camelCase key and
structural marker.  Strip only leading/trailing pleasantries.  No token
cap applies.  If there is no usable data, save one short sentence saying
so (e.g. ``No parameter set was approved this session.``).
```

#### DH-09 · COMPRESS · −568 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ### Rules of authorship · *Golden rules:* 5, 6 · *auditor's own id:* REC-09

**Why:** Five bullets that each restate something already stated: bullet 1 = the '## What you SAVE' intro, bullet 4 = the ASK:/SAVE: loop, bullet 5 = the Quantitative-fields section verbatim.

**Risk:** Slight overlap with REC-16's replacement ('You own the final body'); harmless if both are applied, and each stands alone if only one is.

**Cut from** `### Rules of authorship`

**...through** `leading/trailing pleasantries; the numbers and structural markers
  stay verbatim.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Agent A's wording is input, not authority.  If a reply is already fit,
saving it near-verbatim is fine — but always apply the rewrite rules.
If it is unclear, ASK.
```

#### DH-10 · COMPRESS · −564 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ### Semantic fields · *Golden rules:* 2, 5, 11 · *auditor's own id:* REC-10

**Why:** Two code fences showing the same block grammar (one block vs two blocks) plus prose describing both; one fence and one sentence carry it.

**Risk:** Keeps the literal QUESTION:/ANSWER: fence — that grammar is parsed downstream, so do not paraphrase it away.

**Cut from** `### Semantic fields`

**...through** `if they are aspects of the same item, keep them in one block.`

**Replace with:**

```
### Semantic fields

Semantic bodies are embedded.  Emit one ``QUESTION:``/``ANSWER:`` block
per independent item, each header starting its own line:

``​`
SAVE:
QUESTION: <short, self-contained question about this item>
ANSWER: <embedding-friendly body>
``​`

Use several blocks ONLY when the reply covers genuinely independent items
(two unrelated problems); each becomes its own ``.txt`` and its own
vector (``<field>_1.txt``, ``<field>_2.txt``).
```

#### DH-11 · COMPRESS · −543 chars · risk low

*File:* `DC_prompt_fragments/tools_config/agent_tools_overview_brief.md` · *Section:* (fragment body — the per-agent bullets) · *Golden rules:* 2, 6, 8 · *auditor's own id:* REC-11

**Why:** One line per agent is enough for the DH to know who to attribute an answer to; the second sentences ('Bridge between user and pipeline', 'Only agent that interprets raw user content', 'May open attempt folders only as a fallback') are chain-operational detail the DH never acts on.

**Risk:** This fragment is spliced by the Database Handler ONLY (verified: agent_tools_overview_brief appears in no other prompt.md), so the cut has zero cross-agent blast radius. Keep the <<DCII_ONLY>> markers exactly as written.

**Cut from** `- **Receptionist**: gates user input and composes user-facing`

**...through** `approves or escalates.`

**Replace with:**

```
- **Receptionist**: gates user input, composes user-facing replies.
- **Orchestrator**: routes between agents; originates no design decisions.
- **Planner**: sets strategic intent and recovery plans; owns the
  qualitative directives.
- **User Input Inspector (UII)**: turns raw user content into
  ``extracted_inputs.txt``.
- **DC Input Creator (DCIC)**: opens the attempt folder and authors the
  numeric parameter set (``parameters.json``).
<<DCII_ONLY>>- **DC Input Inspector (DCII)**: validates that set against ranges,
  consistency and user intent; can correct the DCIC.
<</DCII_ONLY>>- **Tool Caller (TC)**: calls the one merged generate-and-render tool
  (mesh + renders + QC).
- **DC Output Inspector (DCOI)**: visually inspects renders; approves or
  escalates.
```

#### DH-12 · DELETE · −454 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ### Output format (strict) · *Golden rules:* 5, 6 · *auditor's own id:* REC-12

**Why:** Third statement of the same contract: the ASK:/SAVE: prefixes and the 'first character' rule are in the Per-field protocol, and the semantic-vs-quantitative body shapes are each stated in their own section.

**Risk:** Only genuinely new phrase here is 'Do not echo the field name' — a minor formatting nicety, not an invariant. If the owner wants it, append it as a clause to the Per-field loop replacement in REC-03.

**Cut from** `### Output format (strict)`

**...through** `single prose block, no headers.  Do not echo the field name.`

**Replace with:** *(nothing — pure deletion)*

#### DH-13 · COMPRESS · −382 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ## Three kinds of questions → sub-row note · *Golden rules:* 1, 7 · *auditor's own id:* REC-13

**Why:** An incident patch spelled out over seven lines with two rationales and three spellings of the id ('attempt NNN' / 'attempt #NNN'); the one-line general principle covers all of them.

**Cut from** `**Do NOT echo the attempt id into the short SAVE: QUESTION or`

**...through** `already knows which attempt is being discussed.`

**Replace with:**

```
**Never repeat the attempt id inside the SAVE: QUESTION or ANSWER** —
   the filename and the file header already carry it.
```

#### DH-14 · MERGE · −369 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ### The token budget for SEMANTIC answers · *Golden rules:* 5, 6 · *auditor's own id:* REC-14

**Why:** States the embedding cap and the 'prefer <600' guidance up front, then restates both in the Semantic-fields rules; the second statement is the one adjacent to where the text is actually written.

**Risk:** Do NOT apply this without keeping the $embedding_max_response_tokens clause in the Semantic-fields section (REC-06's replacement retains it). Applied together they leave exactly one statement of the cap.

**Cut from** `### The token budget for SEMANTIC answers`

**...through** `fewer tokens of higher-quality text embed better than long padded ones.`

**Replace with:** *(nothing — pure deletion)*

#### DH-15 · COMPRESS · −347 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ## How you operate · *Golden rules:* 4, 7 · *auditor's own id:* REC-15

**Why:** 'You are a stateful agent … so you ask coherent follow-ups and never repeat yourself' is default behaviour; the implementation detail ('the system rebuilds its history from a frozen snapshot before every new field') explains the why without changing what the DH does.

**Risk:** The behaviour-changing half — Agent A cannot remember earlier fields, so never reference them — is preserved.

**Cut from** `## How you operate`

**...through** `being interviewed is called **Agent A**.`

**Replace with:**

```
## How you operate

You remember the whole interview.  Each interviewed agent (**Agent A**)
remembers only the session itself — nothing from an earlier field's
conversation is in its context, so never refer back to one.

The database is a fixed schema of FIELDS, each owned by one agent, with a
name, a type (``Semantic``/``Quantitative``) and a description.  The
system walks them one at a time.
```

#### DH-16 · COMPRESS · −317 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ## Tools · *Golden rules:* 7, 9 · *auditor's own id:* REC-16

**Why:** Enumerates every turn type on which the DH has no tools (session-scoped Qs, sub-rows, SAVE: emits, ASK: rounds) when 'every other turn' says it once.

**Risk:** Keeps the anti-confusion guard that the overview above lists OTHER agents' tools — that one is load-bearing given the overview sits directly above it.

**Cut from** `## Tools

You have **one** tool, bound only on specific turns:`

**...through** `do not try to invoke any of them.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Your tool

On the force-tool turn only you call
``save_attempt_data(attempt_ids: list[str])``.  On every other turn you
have no tools — the tools described above were the other agents', not
yours.
```

#### DH-17 · COMPRESS · −304 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* #### Rewrite rules → 1. Strip every file path · *Golden rules:* 1, 2, 7 · *auditor's own id:* REC-17

**Why:** Four enumerated path shapes (/app/attempts, /app/inputs, render PNGs, a literal timestamped slug) are one general principle plus one canonical example.

**Cut from** `1. **Strip every file path and directory name.**  No`

**...through** `the actual file is archived elsewhere.`

**Replace with:**

```
1. **Strip file paths, directory names and attempt-folder slugs.**  Refer
   to artefacts generically ("the isometric render").
```

#### DH-18 · COMPRESS · −302 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* #### Rewrite rules → 2. Strip routing-tool wrappers · *Golden rules:* 2, 7 · *auditor's own id:* REC-18

**Why:** The mechanism (agents end their turn by invoking a routing tool, so their reply is a JSON wrapper) is explained before the rule; the example alone teaches it.

**Risk:** This is a real text-cleanup instruction the model would not perform by default — compress, never delete. Braces are safe here: the DH's runtime slot set is empty (PROMPT_MD_RUNTIME_SLOTS['database_handler'] == frozenset()), so its prompt.md never goes through .format().

**Cut from** `2. **Strip routing-tool wrappers.**  Some agents end their turn by`

**...through** `   tool name.`

**Replace with:**

```
2. **Strip routing-tool wrappers.**  When the reply is
   ``{"call_orchestrator": "…"}``, save only the inner string.
```

#### DH-19 · DELETE · −289 chars · risk low

*File:* `DC_prompt_fragments/tools_config/agent_tools_overview_brief.md` · *Section:* (fragment preamble) · *Golden rules:* 4, 7 · *auditor's own id:* REC-19

**Why:** Meta-commentary about the fragment itself, and its claim ('chain agents see a fuller, tool-level overview that does not appear in your prompt') is factually false today — $available_agents splices the full tool inventory into the DH prompt.

**Risk:** DH-only fragment; no other agent is affected. The trailing 'Database Handler scope: …' sentence at the end of the file is deliberately KEPT — it is the one line that steers what the DH collects.

**Cut from** `Concise, high-level view of who does what`

**...through** `does not appear in your prompt.`

**Replace with:** *(nothing — pure deletion)*

#### DH-20 · COMPRESS · −277 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* #### Rewrite rules → 6. Self-contained and declarative · *Golden rules:* 2, 4 · *auditor's own id:* REC-20

**Why:** Four pronoun examples plus three filler-word examples plus a rationale sentence; one example of each carries it, and 'avoid filler' is close to default behaviour anyway.

**Cut from** `6. **Self-contained and declarative.**  A reader who has never seen`

**...through** `Avoid filler ("basically", "essentially", "I think").`

**Replace with:**

```
6. **Self-contained, declarative prose.**  Replace pronouns with the
   concrete noun ("the Receptionist", not "I").  Continuous prose embeds
   better than bullets; no filler.
```

#### DH-21 · COMPRESS · −269 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ## The questions you ASK Agent A → ### Question wording · *Golden rules:* 7, 11 · *auditor's own id:* REC-21

**Why:** A hedged permission paragraph ('You MAY adapt the wording slightly … IF such adaptation is genuinely useful AND it does not drift …') compresses to one sentence without changing the permission.

**Cut from** `### Question wording`

**...through** `from the field's original meaning.`

**Replace with:**

```
Stay faithful to the field's meaning in the schema; you may adapt the
wording, but never invent details and never drift the question.
```

#### DH-22 · COMPRESS · −232 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ## The questions you ASK Agent A → ### Asked question — length and detail · *Golden rules:* 5, 11 · *auditor's own id:* REC-22

**Why:** Two headings and a paragraph to say 'the asked question is not embedded, so spend tokens on it'.

**Cut from** `## The questions you ASK Agent A`

**...through** `Spend the tokens
that help the agent.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## Asking Agent A

The question you SEND may be as long and detailed as useful — it is not
embedded, only the version you save is.
```

#### DH-23 · COMPRESS · −224 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ## The questions you ASK Agent A → ### Asked question — keep the agent reasoning-focused · *Golden rules:* 7, 11 · *auditor's own id:* REC-23

**Why:** Same three reminders, with the per-item justifications ('noise once stored; files are archived elsewhere', 'post-session there is no chain') folded away.

**Risk:** All three reminders are retained — they are what keeps paths and parameter dumps out of the embedded text at the source.

**Cut from** `### Asked question — keep the agent reasoning-focused`

**...through** `their answer is consumed by you alone).`

**Replace with:**

```
In the question, remind Agent A NOT to give file paths, NOT to enumerate
parameter values (ask for the REASONING — checks, heuristics, trade-offs;
the values are recovered from the archived ``parameters.json``) and NOT
to address another agent or the user.
```

#### DH-24 · COMPRESS · −221 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* #### Rewrite rules → 7. Domain-faithful · *Golden rules:* 2, 7 · *auditor's own id:* REC-24

**Why:** Keeps the rule and its one worked example; drops the explanation of why glossing helps the vector.

**Cut from** `7. **Domain-faithful.**  Preserve technical terms verbatim`

**...through** `embedded vector encodes both the symbol and its referent.`

**Replace with:**

```
7. **Preserve technical terms verbatim** (``bladeCount``, UII/DCIC/DCII/
   DCOI/TC, units, thresholds) and gloss a number once:
   ``bladeCount=5`` (five blades).
```

#### DH-25 · COMPRESS · −219 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* #### Rewrite rules → 5. Replace parameter-value dumps with reasoning · *Golden rules:* 2, 7 · *auditor's own id:* REC-25

**Why:** The ``bladeCount = 6 — [3,6]`` sample dump and the '$parameter_count parameter values' framing are illustration; the rule plus the four reasoning categories is the whole instruction.

**Risk:** This prompt contains NO parameter list with ranges (the DH never authors values), so this cut does not touch the protected 16-parameter block. The 'values live in parameters.json' clause is kept because it is why the DH is allowed to drop them.

**Cut from** `5. **Replace parameter-value dumps with reasoning.**  When the agent`

**...through** `the archived ``parameters.json``.`

**Replace with:**

```
5. **Replace parameter-value dumps with the reasoning behind them** — the
   checks run, heuristics applied, trade-offs weighed, risks flagged.  The
   values are recoverable from the archived ``parameters.json``.
```

#### DH-26 · COMPRESS · −217 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* #### Rewrite rules → 3. Unescape JSON string escapes · *Golden rules:* 7 · *auditor's own id:* REC-26

**Why:** States the transform, then restates it in the negative ('never the backslash-letter escape sequences') and explains the provenance ('artefacts of JSON-stringified content').

**Risk:** Mechanical cleanup the model would not do unprompted — compress, do not delete.

**Cut from** `3. **Unescape JSON string escapes.**  If you see literal`

**...through** `quotes, never the backslash-letter escape sequences.`

**Replace with:**

```
3. **Unescape JSON escapes.**  Literal ``\n`` / ``\t`` / ``\"`` become
   real newlines and quotes.
```

#### DH-27 · COMPRESS · −216 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ## What you SAVE (the body of ``SAVE:``) · *Golden rules:* 5, 11 · *auditor's own id:* REC-27

**Why:** A section intro announcing that the two subsections below differ — the two ### headings already announce that.

**Cut from** `## What you SAVE (the body of ``SAVE:``)`

**...through** `The SAVED body has a **different structure** depending on the field's
type.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
## What you SAVE

You own the final body: faithful to Agent A, fit for the field's type.
```

#### DH-28 · COMPRESS · −174 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ## What you know about the system → ### The design configurator · *Golden rules:* 7, 11 · *auditor's own id:* REC-28

**Why:** A heading plus five lines to convey one fact; 'See the agents' own histories for the specific values' is a redundant pointer (the histories are the DH's only input).

**Cut from** `### The design configurator`

**...through** `### Tools used across the system (high-level only, for context)`

**Replace with:**

```
The system designs $dc_name designs, described by $parameter_count
quantitative parameters.

### What each agent does
```

#### DH-29 · COMPRESS · −158 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* ## The questions you ASK Agent A → negation-acceptable wording · *Golden rules:* 6, 7 · *auditor's own id:* REC-29

**Why:** Says the same thing twice ('Agent A is expected to say so explicitly — that is a valid answer' then 'word the question so that … is an obviously acceptable response').

**Risk:** Pairs with rewrite rule 9 (negation-canonical); keep at least one of the two.

**Cut from** `For "Problem ..." / "...solution" / "...request" fields, when nothing`

**...through** `is an obviously acceptable
response.`

*(Anchors paraphrase the file's dashes/whitespace — search loosely, not for the literal string.)*

**Replace with:**

```
Word "Problem …" / "…solution" questions so that "no such problem
occurred this session" is obviously an acceptable answer.
```

#### DH-30 · COMPRESS · −128 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* #### Rewrite rules → 4. Drop mid-chain narration · *Golden rules:* 2 · *auditor's own id:* REC-30

**Why:** Three near-identical example sentences collapse to one.

**Cut from** `4. **Drop mid-chain narration.**  Sentences like "I'll forward this`

**...through** `entirely — there is no chain at save time.`

**Replace with:**

```
4. **Drop mid-chain narration** ("I'll forward this to the Orchestrator")
   — there is no chain at save time.
```

#### DH-31 · COMPRESS · −128 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* #### Rewrite rules → 9. Negation-canonical · *Golden rules:* 2, 7 · *auditor's own id:* REC-31

**Why:** Keeps the canonical sentence (the whole point of the rule) and drops the negative restatement 'do not leave the body empty, ambiguous, or filled with hedges'.

**Cut from** `9. **Negation-canonical.**  When the answer is "nothing of the kind`

**...through** `filled with hedges.`

**Replace with:**

```
9. **Negation-canonical.**  "Nothing of the kind happened" becomes one
   sentence: ``No problem occurred during this session for the User Input
   Inspector.``
```

#### DH-32 · COMPRESS · −127 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* #### Rewrite rules → 8. One topic per file · *Golden rules:* 2, 4 · *auditor's own id:* REC-32

**Why:** 'Each field is one concept; do not bundle multiple fields' content' is the heading restated, and two meta-commentary examples become one.

**Cut from** `8. **One topic per file.**  Each field is one concept; do not bundle`

**...through** `commentary like "as I said earlier" or "the user asked …".`

**Replace with:**

```
8. **One topic per file**; no meta-commentary ("as I said earlier").
```

#### DH-33 · COMPRESS · −54 chars · risk low

*File:* `agents/database_handler/prompt.md` · *Section:* #### Rewrite rules for the saved QUESTION + ANSWER (semantic only) · *Golden rules:* 11 · *auditor's own id:* REC-33

**Why:** Heading and its one-line gloss say the same thing; merge into the heading.

**Cut from** `#### Rewrite rules for the saved QUESTION + ANSWER (semantic only)`

**...through** `Apply these to BOTH the saved QUESTION and the saved ANSWER:`

**Replace with:**

```
#### Rewrite rules — apply to BOTH the saved QUESTION and the saved ANSWER
```

</details>

<details><summary><b>Proposed shape of the shrunk prompt</b></summary>

```
DATABASE HANDLER — proposed assembled shape (~6,960 chars / ~1,740 tok, from 22,020 / 5,505)

Role preamble (unchanged, lines 1-6) .................................. ~72 tok
## What you know about the system ..................................... ~250 tok
    one-line DC statement ($dc_name, $parameter_count)
    ### What each agent does  ($agent_tools_overview_brief, compressed) ~220 tok
    [DELETED: $available_agents roster + its nested $tool_inventory]
    [DELETED: blade-sections visualizer block]
    [DELETED: ### The token budget for SEMANTIC answers -> merged below]
## Your tool .......................................................... ~50 tok
## How you operate .................................................... ~99 tok
    stateful you / session-only Agent A / fixed FIELD schema
## Three kinds of schedule row ........................................ ~160 tok
    3 numbered kinds, one example each + never-echo-the-attempt-id line
## The force-tool turn ................................................ ~88 tok
## Per-field loop ..................................................... ~129 tok
    ASK: / SAVE: prefixes, first-character rule, round cap
## Asking Agent A ..................................................... ~160 tok
    long questions are free; the 3 reminders to Agent A; stay faithful to
    the schema; make "nothing happened" an acceptable answer
## What you SAVE ...................................................... ~22 tok
    ### Quantitative fields ........................................... ~92 tok
    ### Semantic fields ............................................... ~222 tok
        QUESTION:/ANSWER: fence, multi-block rule, short-QUESTION rule,
        per-pair $embedding_max_response_tokens cap, ATTEMPT: block shape
    #### Rewrite rules (9 one-to-three-line rules) .................... ~327 tok
    authorship one-liner .............................................. ~41 tok
[DELETED: ### Output format (strict) — third restatement of ASK:/SAVE:]

Structural notes: two H2 sections disappear entirely (## Tools becomes a
4-line ## Your tool; ### Output format (strict) goes away), and the
"### The agents you may interview" + "### Tools used across the system"
pair collapses into a single "### What each agent does".
```

</details>

**Auditor notes.** MEASUREMENT. I reproduced the assembly (Template double-pass + <<DCII_ONLY>>/<<BSV_ON>> filters, config as given) and got exactly 22,020 chars = 5,505 tok, matching your baseline, so every chars_removed below is a measured assembled-char delta (original span expanded, minus my replacement expanded), not an estimate. Sum = 15,061 -> 6,959 chars -> ~1,740 tok. All 33 quote_start strings were verified to occur EXACTLY ONCE in their file, and every quote_end verified to occur after its start.

BIGGEST FINDING (REC-01). The DH splices BOTH $available_agents (shared with the Planner and the 5-agent Conductor) AND $agent_tools_overview_brief (DH-exclusive). They are the same roster twice. Worse, available_agents.md contains ``$tool_inventory`` inside backticks, and _build_template runs a SECOND substitution pass — so the full 881-char tool inventory is currently pasted into the Database Handler's prompt, directly contradicting the comment at agents/shared/prompts.py:376-381 ("Strips the detailed tool listings — the DH is interested in WHAT each agent does, not in every bound tool"). REC-01 alone is 2,887 chars, 52% of the total cut, and it also removes routing instructions ("route to the Orchestrator and state what question is needed") that are wrong for an agent whose only tool is save_attempt_data.

WHAT I DELIBERATELY DID NOT CUT.
- The role preamble (lines 1-6, 290 chars): already minimal and it is the only statement of why the interview exists (RAG over past sessions).
- The ASK:/SAVE: prefix-at-first-character rule: this is a parser contract, kept verbatim in REC-03.
- The force-tool "call once, emit no text that turn, [] means none" rule: kept verbatim in REC-02.
- The per-pair $embedding_max_response_tokens cap: kept in REC-06. REC-14 deletes the OTHER statement of it — apply REC-14 only together with (or after) REC-06.
- Rewrite rules 2 and 3 (strip routing-tool JSON wrappers, unescape \n/\t/\"): these are the two rules a model will NOT follow by default — it will happily save {"call_orchestrator": "…"} or literal backslash-n into an embedding. Compressed 3x, never deleted.
- Rewrite rule 5 (reasoning instead of parameter dumps) and the matching reminder in the asked question (REC-23): these are the ones that keep 16-value dumps out of the vector store.
- The "Database Handler scope: collect each agent's recollection … not their tool inventories" sentence at the end of agent_tools_overview_brief.md.

PROTECTED CONTENT. This prompt contains no parameter list and no ranges — the DH never authors values — so nothing here touches your must-stay-inline 16-parameter block.

SAFETY CHECK ON BRACES. Several replacements contain literal { } (rewrite rule 2, the [] in the force-tool section). Verified safe: PROMPT_MD_RUNTIME_SLOTS["database_handler"] is frozenset(), and the current prompt already carries an unescaped {"call_orchestrator": …} at line 303 — the DH's prompt.md is never passed through .format(). This is the one agent where the brace-escape trap does not apply.

BLAST RADIUS. 31 of 33 cuts touch agents/database_handler/prompt.md only. The two fragment cuts (REC-11, REC-19) touch DC_prompt_fragments/tools_config/agent_tools_overview_brief.md, which I verified is spliced by the Database Handler and nothing else (grep across all prompt.md files: one hit). agents/shared/prompt_fragments/available_agents.md is NOT edited — REC-01 removes the DH's reference to it, leaving the Planner and Conductor untouched.

IF YOU WANT TO GO FURTHER (not proposed, because each removes the only statement of a behaviour): dropping the ATTEMPT:-multi-block rule (REC-07's survivor, ~190 chars) if multi-attempt identifying answers are rare in practice; dropping rewrite rules 8 and 9 (~230 chars) and relying on the field schema descriptions; dropping the "### Quantitative fields" no-token-cap sentence. Per golden rule 12 I would land the 33 cuts above, run one real end-of-session interview, and only then decide from the saved .txt files what is genuinely missing.

---

## 5. Adversarial verification

Three independent verifiers re-checked every medium/high-risk cut against the actual repo, each through a different lens: **invariant** (is this the only place the rule is stated?), **incident** (does git history show it was added to fix a real failure?), and **runtime mechanics** (does the code or another agent parse a literal string this cut removes?).

**Coverage caveat.** The verifiers ran against the first audit pass, which covered User Input Inspector, DC Input Inspector (dc_input_inspector), DC Input Inspector, DC Output Inspector, DC Input Creator (agents/dc_input_creator), DC Input Creator, Tool Caller, User Input Inspector, DC Input Inspector, Tool Caller, DC Output Inspector, DC Input Inspector / DC Output Inspector, Receptionist, Tool Caller, DC Input Creator, User Input Inspector, User Input Inspector / DC Input Creator. Cuts for any agent audited in a later pass carry the auditor's own risk rating but have **not** been independently refuted — treat their medium/high rows with extra care.

### Lens 1 — 52 cuts reviewed, 12 flagged

Reviewed 52 cuts against the repo. 12 refuted: 5 for a genuinely unique invariant, 7 for non-independent application. The rest hold up — I checked each claimed survival path rather than taking the risk notes at face value, and most were accurate.

**The one substantive invariant loss: REC-16 (parameters.md).** Its table drops the middlePos from-ROOT definition and the `radius = 4 + middlePos·(impellerRadius − 4)` formula. I traced the survivors: modelling_notes.md reaches only DCIC and DCII; structure.md only DCIC and UII. parameters.md reaches 7 prompts, and for the **Planner, Orchestrator, Receptionist and Tool Caller it is the only source** — the Planner being precisely the agent that converts "middle section at 40 mm" into a middlePos directive. The from-centre reading is the documented past error (fixed in 9ed7c2a). One line restores it. The 16 ranges themselves I diffed individually: all correct.

**The second real loss: REC-35 (value_states.md).** Drops the only 7-agent statement that "user-locked" is a *default* lock, not an override of a live authorisation. Both competing whole-file rewrites of that fragment deliberately keep the clause.

**A shared-fragment scoping error five cuts share** (REC-03 ×2, REC-36, REC-31, REC-21): all drop "the only exceptions are the Receptionist's direct user replies…" from the routing bullet in generic_constraints.md. That bullet sits *outside* `<<CHAIN_ONLY>>`, so it lands in the Receptionist's prompt — and the Receptionist is in `_NON_CHAIN_AGENTS` and never receives `routing_instructions()`. Stripped of the exception, its prompt would assert flatly that plain text halts the pipeline, contradicting its own Situation-B rule that it *must* reply in plain text and must *not* call the Orchestrator. The independently written 5-agent fragment keeps the same clause, which is what convinced me it is deliberate. Eight words fixes it.

**Independence is the bigger practical problem.** Three shared files are targeted by mutually exclusive cuts: `generic_constraints.md` (11 cuts, including two competing full rewrites), `routing.py`'s "Routing is a tool call" block (4 competing rewrites of one code block feeding all six chain agents), and `value_states.md` (2 competing full rewrites + 2 sub-region cuts). The owner cannot apply these one at a time as briefed — the first application makes the others unmatchable.

**Two mechanical notes that will bite during application:** every target file is CRLF while the replacement texts are LF; and REC-16's `quote_end` has six spaces after `outerAngle` where the file has five (verified by exact string match).

**Deliberately not refuted,** having checked the survival path in each case: C-29/C-30/C-12 (the Receptionist's own anti-fabrication HARD RULE and `capabilities_can`/`capabilities_cannot` carry everything scoped away); REC-06/REC-08 (DCIC — `hard_constraints_tools.md` carries "write only into the Current attempt: folder", and the collision paragraph after the cut boundary survives intact); REC-06/REC-08 (DCII — the two self-checks below the cut, including "compared each of the N parameters individually", survive and backstop the blanket-APPROVE patch); REC-45 (DCIC keeps modelling_notes, so the hub-4 mm rule survives); REC-01/REC-07/REC-08/REC-11/REC-14 (DCOI — anti-hallucination scope, the four precision-loop invariants and the ratio-vs-millimetre gotcha are all preserved in substance); REC-23 (`capabilities_cannot.md` independently covers the trimmed enumerations); REC-38 and REC-28/REC-05 (Tool Caller) carry no invariant at all.

### Lens 2 — 52 cuts reviewed, 13 flagged

Reviewed all 52 medium/high-risk cuts against the repo (git log -S, commit bodies, fragment splice map, and the CHAIN_ONLY/_NON_CHAIN_AGENTS filter in agents/shared/prompts.py). Most survive the incident lens: REC-13 (countable features), REC-29 (Ø160/Ø140 forms, commit 5ebb4a8), REC-06/REC-08 (DCII blanket-approve patch), REC-08 (DCIC three-way collision from commit e46b194 - the surviving lines 198-209 are outside the quote), REC-11 (DCOI anti-hallucination), REC-07/REC-08 (precision refine loops), REC-01 (DCOI dropping $sketch_handling - it keeps $sketch_notes and $value_states independently) and C-29/C-30 (the Receptionist keeps $capabilities_cannot and $parameter_list) all preserve their invariants. Thirteen fail. The single most important is systemic and appears in FIVE independent cuts (REC-31 DCIC, REC-21 TC, REC-36 UII, REC-03 DCII, REC-03 DCOI): every rewrite of generic_constraints.md's plain-prose bullet drops the clause 'the only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up.' That bullet is outside <<CHAIN_ONLY>> and _NON_CHAIN_AGENTS = {receptionist, orchestrator, conductor}, so both agents receive it; the Receptionist's own prompt says 'writing plain text IS the decision to reply directly', so without the carve-out its user-reply path is forbidden by a hard constraint. Cost to fix: one clause. Second: REC-16 (parameters.md → table) deletes the middlePos gloss that commit 9ed7c2a added specifically to kill the 'x impellerRadius' misreading, and parameters.md is the only copy the Orchestrator, Planner, Receptionist and Tool Caller get. Third: C-12 deletes a rule written from a logged 2026-06-05 run (commit 799d896) and depends on C-10, which is not in this batch; REC-16 (TC) deletes the routing.py permission block and depends on REC-19, also not in this batch. Beyond content, this batch has heavy self-collision: four competing rewrites of one routing.py block, two competing whole-file rewrites of generic_constraints.md plus seven partial cuts on the same file, and four cuts on value_states.md. These are not independently applicable despite being presented that way - pick one per file. Two smaller notes not worth a formal refutation: REC-09 (UII warm-start) leaves the surviving 'SKETCH CROP REGION' item numbered '2.' with no '1.', and REC-05 (UII soft targets) carries the same propeller-literal leak flagged under REC-39.

### Lens 3 — 52 cuts reviewed, 11 flagged

Verified every quote against the files and grepped the Python for each runtime literal. Good news first: the labels the runtime actually depends on all survive. `Extracted inputs file:` / `Current attempt:` (REC-14 UII, REC-06 DCIC), `Parameters file:` (REC-08 DCII), `GEOMETRY ANALYSIS:` (REC-11 DCOI), `SKETCH CROP REGION` + `side_by_side` + `regions` (REC-07 DCOI, verified against agents/shared/user_inputs_tool.py:132), and every tool name referenced in a replacement (`new_attempt`, `write_parameters`, `calculate`, `view_images`, `list_attempts`, `read_attempt`, `call_tool_caller`/`call_dc_input_creator`/`call_orchestrator`) all exist and are bound to the agent told to call them. The 16 parameter ranges in REC-16's table are numerically identical to parameters.md, and /api/parameters (web_app.py:779) only serves that file as raw text — the range validator `_PREVIEW_PARAM_SPEC` is hardcoded — so reformatting is safe. REC-30 (DCIC) writing the shorthand `=== STANDING DIRECTIVES ===` instead of the canonical BLOCK_START is NOT a break: standing_directives.is_present() matches on directive TEXT, and orchestrator.py:738 re-stamps the canonical header on every carrier hop, so a mangled header self-heals. <<PF_ON>>/<<PF_OFF>> and <<CHAIN_ONLY>> markers are balanced in every replacement; all routing.py replacements are valid Python with correct f-prefixes. REC-45 is safe because the DCIC also splices $modelling_notes, which carries the hub-4 mm formula. Five cuts fail on substance, four on verbatim quoting, and the fleet has heavy uncoordinated overlap on the three shared files — the biggest real threat to "independently applicable".

| cut | agent | verdict | reason |
|---|---|---|---|
| **REC-16** | User Input Inspector | UNSAFE_NEEDS_REPLACEMENT | The table row `\| 9 \| middlePos \| fraction of blade span \| 0.3-0.7 \|` drops the from-ROOT definition and formula that the current file carries: '0 = root (hub, r = 4 mm), 1 = tip; radius = 4 + middlePos·(impellerRadius - 4) mm'. I traced where that survives: only modelling_notes.md (spliced into dc_input_creator and dc_input_inspector ONLY) and structure.md (dc_input_creator + user_input_inspector ONLY) — verified by grep over all agents/*/prompt.md. parameters.md is spliced into 7 prompts; for the Planner, Orchestrator, Receptionist and Tool Caller it is the ONLY source of middlePos semantics. The Planner is exactly the agent that turns 'put the middle section at 40 mm' into a middlePos directive (its prompt reasons about middlePos at lines 89 and 269) and it has no modelling_notes and no dc_structure. 'fraction of blade span' alone does not block the middlePos = r/impellerRadius reading, which is the documented past error (old GTs and prompt fragments used from-centre distance/R and were wrong; commit 9ed7c2a fixed it). Two mechanical notes: quote_end has one extra space ('16. outerAngle      (degrees)' — the file has 5 spaces, not 6), and every file in this set is CRLF while the replacements are LF, so exact-match edits will need care. The 16 ranges themselves I diffed one by one against the file — all correct, and the added '*Thickness/*Camber are % of that section's OWN chord' and 'middle section is interpolated' lines are genuine improvements. |
| **REC-16** | User Input Inspector | UNSAFE_NEEDS_REPLACEMENT | The table transcribes all 16 names and ranges correctly (I diffed every row against DC_prompt_fragments/dc_config/parameters.md), but it deletes the middlePos gloss that commit 9ed7c2a added on purpose: 'Middle-section position along the blade: 0 = root (hub, r = 4 mm), 1 = tip; radius = 4 + middlePos*(impellerRadius - 4) mm'. That commit's message is explicit - it replaced a WRONG 'x impellerRadius' reading ('NOT middlePos * impellerRadius', matching web/feg/profiles.js). The replacement's 'fraction of blade span' alone re-opens exactly the misreading that was fixed. Coverage check: the formula also lives in modelling_notes.md (spliced only into DCIC + DCII) and structure.md (only DCIC + UII), so parameters.md is the ONLY copy the Orchestrator, Planner, Receptionist and Tool Caller ever see - and the Planner is the agent that writes numeric middlePos directives. |
| **REC-16** | User Input Inspector | QUOTE_WRONG | quote_end is not verbatim. The cut gives '16. outerAngle      (degrees)                   — Angle of attack [2; 25]' with SIX spaces after 'outerAngle'; parameters.md line 25 has FIVE ('16. outerAngle     (degrees)...', confirmed byte-exact with cat -A). Separately: I diffed all 16 names, units and ranges against the file and the table is correct, and nothing parses this file at runtime — but the replacement drops the middlePos definition 'radius = 4 + middlePos·(impellerRadius − 4) mm, 0 = root (hub, r = 4 mm)'. That formula survives only in modelling_notes.md ($modelling_notes) and structure.md ($dc_structure), and the splice map shows the Planner receives $parameter_list but NEITHER of those. The Planner is the agent that issues middlePos directives (agents/planner/prompt.md:269), and the from-centre vs from-4 mm-root confusion is a documented real bug in this project. |
| **REC-03** | DC Input Inspector (dc_input_inspector) | UNSAFE_NEEDS_REPLACEMENT | The final bullet drops the clause 'the only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up'. That bullet sits OUTSIDE the <<CHAIN_ONLY>> markers, so it is spliced verbatim into the Receptionist's prompt — and agents/shared/prompts.py lists the Receptionist in _NON_CHAIN_AGENTS AND it never receives routing_instructions() (confirmed: only creator, dc_input_creator, dc_input_inspector, dc_output_inspector, planner, tool_caller, user_input_inspector call it). So after this cut the Receptionist's prompt asserts, unqualified, 'any text you emit without one is silently discarded and the pipeline halts', which directly contradicts its own Situation-B rule at agents/receptionist/prompt.md: 'you MUST respond with plain user-facing text, you must NOT invoke ``call_orchestrator`` (that would loop control back into the system)'. Strong evidence the clause is deliberate, not vestigial: the independently authored 5-agent copy keeps it too (agents/5agent/prompt_fragments/generic_constraints_5agents.md:53, 'only exception is the Receptionist's direct user replies'). Everything else in this rewrite checks out — STANDING DIRECTIVES verbatim, the halt consequence, the CHAIN_ONLY markers and the permission bullet all survive correctly placed. |
| **REC-03** | DC Input Inspector (dc_input_inspector) | UNSAFE_NEEDS_REPLACEMENT | Two problems. (1) Its last bullet ends '...silently discarded and the pipeline halts. Invoke the tool in the same response where you finish your work.' - the Receptionist/Orchestrator exception is gone, and this fragment is spliced into both non-chain agents (verified above). (2) It is one of TWO whole-fragment rewrites of generic_constraints.md in this batch (the other is REC-03 for the DCOI, with a different structure and different headings), and it collides with seven partial cuts on the same file (REC-42, REC-28 UII; REC-43, REC-30, REC-31 DCIC; REC-24, REC-21, REC-28 TC). Applying any two of these means the second's quote no longer matches, so the owner can silently believe a rule was preserved that was not. |
| **REC-03** | DC Input Inspector | QUOTE_WRONG | Two defects. (1) quote_end is not verbatim: the cut quotes 'only exceptions are the Receptionist's direct user replies and the\nOrchestrator's final user-facing wrap-up.' but generic_constraints.md lines 54-55 are indented two spaces on BOTH lines (cat -A shows '  only exceptions are...$' / '  Orchestrator's final user-facing wrap-up.$'). A verbatim apply will not anchor. (2) Same substantive defect as REC-03 (DCOI): the replacement's closing DON'T drops the Receptionist/Orchestrator exception from a bullet those two non-chain agents actually receive and rely on (receptionist.py:8, orchestrator.py:542) — and neither gets routing_instructions() as a backstop. This cut also rewrites the whole of generic_constraints.md and so collides with REC-03 (DCOI), REC-21/24/28 (TC), REC-28/36/42 (UII) and REC-30/31/43 (DCIC), all of which edit spans inside it. |
| **REC-03** | DC Output Inspector | OVERLAPS_ANOTHER_CUT | This is a SECOND, differently-worded full rewrite of the same 3,506-char file that REC-03 (DC Input Inspector) rewrites end-to-end. The two are mutually exclusive: whichever is applied first makes the other's quote_start/quote_end unmatchable, and nine further cuts (REC-36, REC-42, REC-28/UII, REC-30, REC-31/DCIC, REC-43, REC-21, REC-24, REC-28/TC) carve sub-regions of the same file. The owner cannot apply these independently as briefed. Separately, it drops the same Receptionist-exception clause described under REC-03 (DCII) and additionally collapses the whole fragment to a single '### Hard rules' heading, so any later cut quoting '### What every agent … MAY do (DOs)' will also fail. |
| **REC-03** | DC Output Inspector | UNSAFE_NEEDS_REPLACEMENT | Same two problems as the DCII's REC-03. Its final line - '**Routing is a tool call.** The ONLY channel to another agent is ``call_<agent>``; its ``message`` argument IS the hand-off. Text emitted without a routing call is discarded and the pipeline halts.' - drops the Receptionist/Orchestrator carve-out, and it is a competing whole-file rewrite of generic_constraints.md against REC-03 (DCII) plus seven partial cuts on the same file. Content-wise this version is the better of the two (it keeps the permission-question rule and the 'never write the user-facing reply' rule inside <<CHAIN_ONLY>>). |
| **REC-03** | DC Output Inspector | UNSAFE_NEEDS_REPLACEMENT | The replacement's final bullet ('Text emitted without a routing call is discarded and the pipeline halts') drops the original's closing clause: 'the only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up.' That bullet sits OUTSIDE the <<CHAIN_ONLY>> region, so the Receptionist and Orchestrator both receive it verbatim (both splice $hard_constraints_generic). Both END THEIR TURN WITH PLAIN TEXT BY DESIGN: agents/receptionist/receptionist.py:8 — 'replies to the user directly (by producing plain text with no tool call)' — returning ai_text(response.content) at line 174; agents/orchestrator/orchestrator.py:542 — 'producing plain text.  Bail out as DONE'. Neither receives routing_instructions() (only the six chain agents' prompt.md files contain {routing_instructions}), so this bullet is their ONLY statement of the rule, and without the exception it reads as an absolute prohibition contradicting agents/shared/prompt_fragments/routing_receptionist.md ('you do NOT invoke any routing tool... do not also call call_orchestrator (that would loop control back into the system)'). Also overlaps REC-03 (DC Input Inspector), which rewrites the identical span differently. |
| **REC-36** | User Input Inspector | UNSAFE_NEEDS_REPLACEMENT | Same defect as REC-03: the replacement ends at '...rather than announcing it.' and drops 'the only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up'. generic_constraints.md is shared with the Receptionist, which is a _NON_CHAIN_AGENTS entry that gets no routing_instructions() and whose own prompt requires plain-text replies in Situation B. The clause survives nowhere else in the 7-agent tree (grep: only agents/5agent/prompt_fragments/generic_constraints_5agents.md:53 has an equivalent, and that file is a separate topology override). This cut is also byte-identical in region to REC-31 (DC Input Creator) and REC-21 (Tool Caller) — three proposals for one edit. |
| **REC-36** | User Input Inspector | UNSAFE_NEEDS_REPLACEMENT | Same defect: the replacement keeps the halt consequence and the same-response requirement but silently drops 'the only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up.' The Receptionist and Orchestrator both splice this fragment ($hard_constraints_generic at agents/receptionist/prompt.md:407 and agents/orchestrator/prompt.md:517) and both emit user-facing plain text with no routing call. |
| **REC-36** | User Input Inspector | QUOTE_WRONG | quote_end is not verbatim: it gives 'only exceptions are the Receptionist's direct user replies and the\nOrchestrator's final user-facing wrap-up.' with no indent on the second line, but generic_constraints.md line 55 is '  Orchestrator's final user-facing wrap-up.' (two leading spaces, confirmed with cat -A). Separately, the replacement drops that exception clause entirely, and this bullet is outside <<CHAIN_ONLY>> so the Receptionist and Orchestrator read it — both legitimately end turns with plain text and no routing call (receptionist.py:8/174, orchestrator.py:542), and neither receives routing_instructions() as a second source. Also collides with REC-21 (TC) and REC-31 (DCIC), two different replacements for exactly this bullet. |
| **REC-31** | DC Input Creator (agents/dc_input_creator) | OVERLAPS_ANOTHER_CUT | Targets the exact same region of agents/shared/prompt_fragments/generic_constraints.md as REC-36 (User Input Inspector) and REC-21 (Tool Caller) — identical quote_start ('<</CHAIN_ONLY>>- DON'T communicate to another agent in plain prose.  The ONLY channel') and identical quote_end, with three different replacement texts. Only one can apply; the other two will silently fail to match. It also drops the Receptionist-exception clause (see REC-36) and, being the most aggressive of the three, it is the one that leaves the Receptionist with the bare unqualified halt statement. |
| **REC-31** | DC Input Creator (agents/dc_input_creator) | UNSAFE_NEEDS_REPLACEMENT | The replacement drops the closing carve-out of the bullet it rewrites: 'the only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up.' That bullet sits OUTSIDE the <<CHAIN_ONLY>> region (line 46 of generic_constraints.md begins '<</CHAIN_ONLY>>- DON'T communicate...'), and agents/shared/prompts.py:153 puts receptionist + orchestrator in _NON_CHAIN_AGENTS, so those two agents DO receive this bullet in full. The Receptionist's own prompt (line 205) says 'writing plain text IS the decision to reply directly' and line 120 says 'next turn should be plain text with no further tool calls'. Leaving only 'DON'T emit prose without a routing tool call - it is silently discarded and the pipeline halts' under a heading that reads '## Hard constraints - generic (apply to every agent)' directly contradicts the Receptionist's only mechanism for answering a user, and is the most absolute of the five proposed rewrites. Also overlaps REC-21 (Tool Caller), REC-36 (UII), REC-03 (DCII) and REC-03 (DCOI), which all rewrite the same bullet. |
| **REC-31** | DC Input Creator | QUOTE_WRONG | Identical quote defect to REC-36: quote_end's second line lacks the two-space indent that generic_constraints.md line 55 actually carries, so the span will not match verbatim. The two-line replacement ('DON'T emit prose without a routing tool call — it is silently discarded and the pipeline halts') also drops the Receptionist/Orchestrator exception from a non-CHAIN_ONLY bullet those agents receive; both end turns with plain text on purpose (receptionist.py:8, orchestrator.py:542) and neither gets routing_instructions(). Note this cut, REC-21 (TC) and REC-36 (UII) are three mutually exclusive rewrites of the same bullet. |
| **REC-21** | Tool Caller | OVERLAPS_ANOTHER_CUT | Third proposal for the same generic_constraints.md region as REC-36 and REC-31. Its own risk note correctly identifies that 'the Receptionist and Orchestrator do not receive routing_instructions(), so this bullet is their only statement of the rule' — which I confirmed against agents/shared/prompts.py and the routing_instructions() call sites — yet the replacement still drops the exception clause that makes the rule safe for the Receptionist to read. |
| **REC-21** | Tool Caller | UNSAFE_NEEDS_REPLACEMENT | Same defect as REC-31/REC-36/REC-03: the replacement ends at '...silently discarded and the pipeline halts' and deletes 'the only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up.' The cut's own risk_note argues this bullet must survive precisely BECAUSE 'the Receptionist and Orchestrator do not receive routing_instructions(), so this bullet is their only statement of the rule' - and then removes the clause that makes those two agents' normal behaviour legal. Verified: generic_constraints.md line 46 is outside <<CHAIN_ONLY>>, and _NON_CHAIN_AGENTS = {receptionist, orchestrator, conductor} (agents/shared/prompts.py:153), so both get the unfiltered text. |
| **REC-21** | Tool Caller | UNSAFE_NEEDS_REPLACEMENT | The quote anchors correctly (this one includes the two-space indent the other three cuts miss), but the replacement drops the closing exception clause. The cut's own risk_note is right that the Receptionist and Orchestrator do not receive routing_instructions() — confirmed, only the six chain agents' prompt.md files contain {routing_instructions} — which makes this bullet their sole statement of the rule. Without '...the only exceptions are the Receptionist's direct user replies and the Orchestrator's final user-facing wrap-up', the Receptionist is told its normal user reply is 'silently discarded and the pipeline halts', contradicting routing_receptionist.md and inviting it to call call_orchestrator instead — the exact loop that fragment warns against. Also overlaps REC-31 (DCIC) and REC-36 (UII) on the same bullet. |
| **REC-16** | Tool Caller | UNSAFE_NEEDS_REPLACEMENT | This DELETES the '### Permission / authorisation issues' block from agents/shared/routing.py, which is spliced into all six chain agents. Two problems. (1) Its own risk note says 'Apply together with REC-19, which carries the surviving permission bullet' — REC-19 is not in this review set, so as briefed the owner can apply this alone. (2) The rule it removes — 're-read the incoming hand-off (and any file it points to) ONCE MORE before escalating; if it already names an authorisation that plausibly covers the action, act on it; do NOT bounce back for a ritual re-confirmation' — survives elsewhere ONLY in value_states.md ('never demand a "ritual re-confirmation" of an authorisation the hand-off already carries'), and value_states.md is spliced into dc_input_creator, dc_input_inspector, dc_output_inspector and planner only. For the User Input Inspector and the Tool Caller — two of the six agents this code feeds — deletion leaves no statement of it anywhere. It also collides head-on with REC-17 (User Input Inspector), which COMPRESSES the identical block rather than deleting it. |
| **REC-16** | Tool Caller | UNSAFE_NEEDS_REPLACEMENT | A full DELETE of the '### Permission / authorisation issues' block in agents/shared/routing.py (lines 229-246), which is injected into all six chain agents. Its own risk_note says to 'apply together with REC-19, which carries the surviving permission bullet' - REC-19 is not in this batch, and REC-17 (User Input Inspector) proposes to COMPRESS the same block, so the two cuts are mutually exclusive. Applied alone, the rule that dies everywhere is 'READ THE INCOMING HAND-OFF ... ONCE MORE before escalating; if the hand-off already names an authorisation that plausibly covers the action - even if the wording differs from a template you expected - act on it.' The nearest surviving copy ('never demand a ritual re-confirmation') is in value_states.md, which is spliced only into the Planner, DCIC, DCII and DCOI - the Tool Caller and UII would have nothing. |
| **REC-16** | Tool Caller | OVERLAPS_ANOTHER_CUT | This DELETEs agents/shared/routing.py lines 229-246 (the '### Permission / authorisation issues' block); REC-17 (User Input Inspector) COMPRESSes the exact same span. Both anchor verbatim to the same region — mutually exclusive, and the owner reviewing them separately sees two independent-looking wins on one block. Two secondary mechanics notes on the DELETE: it orphans `_authorisation_sources()` (routing.py:49) — line 243 is its only call site — leaving dead code; and that helper is the one piece of routing boilerplate that adapts to SYSTEM_TOPOLOGY (it collapses three grantors to two for the 5-agent Conductor), so deleting the block silently drops the topology-5 wording too. |
| **REC-12** | DC Input Inspector (dc_input_inspector) | OVERLAPS_ANOTHER_CUT | Four cuts in this set rewrite the identical '### Routing is a tool call — MANDATORY' block in agents/shared/routing.py with four different replacement texts: REC-07 (UII), REC-12 (DCII), REC-17 (Tool Caller) and REC-09 (DCOI). The block is generated in shared code and reaches all six chain agents, so there is exactly one copy to edit. Whichever is applied first leaves the other three unmatchable. On the invariant itself I found no problem: all four replacements keep the mandate, the 'message IS the hand-off' clause and the halt consequence, and the retired ``---ROUTING---`` prohibition is genuinely dead (grep finds no emitter). |
| **REC-12** | DC Input Inspector (dc_input_inspector) | OVERLAPS_ANOTHER_CUT | Same block of agents/shared/routing.py as REC-07 (UII), REC-17 (TC) and REC-09 (DCOI). Four different replacement texts for one code block that is shared by all six chain agents. Content is safe on its own (it keeps 'silently discarded and the pipeline halts'), but it cannot be applied independently of the other three. |
| **REC-07 / REC-12 / REC-17 / REC-09** | User Input Inspector, DC Input Inspector, Tool Caller, DC Output Inspector | OVERLAPS_ANOTHER_CUT | Four different auditors each propose a DIFFERENT replacement for the identical code block in agents/shared/routing.py lines 248-273 ('### Routing is a tool call — MANDATORY' through '"(one or two lines is plenty).",'). My verbatim check confirms all four anchor to the same 1,658-char span. This is one shared code block spliced into all six chain agents, not four independent cuts — applying any two produces garbage or a silent no-op, and the char-savings claims (933/1050/703/1020) are not additive. All four replacements are syntactically valid Python and none uses {hub}, so no f-prefix is needed. |
| **REC-17** | Tool Caller | OVERLAPS_ANOTHER_CUT | Third of four competing rewrites of the same routing.py '### Routing is a tool call — MANDATORY' block (see REC-12). No invariant is lost by this text on its own — the mandate, consequence and same-response clause all survive — but it cannot be applied independently of REC-07, REC-12 and REC-09. |
| **REC-07 / REC-12 / REC-17 / REC-09** | User Input Inspector, DC Input Inspector, Tool Caller, DC Output Inspector | OVERLAPS_ANOTHER_CUT | Four different auditors each propose a DIFFERENT replacement for the identical code block in agents/shared/routing.py lines 248-273 ('### Routing is a tool call — MANDATORY' through '"(one or two lines is plenty).",'). My verbatim check confirms all four anchor to the same 1,658-char span. This is one shared code block spliced into all six chain agents, not four independent cuts — applying any two produces garbage or a silent no-op, and the char-savings claims (933/1050/703/1020) are not additive. All four replacements are syntactically valid Python and none uses {hub}, so no f-prefix is needed. |
| **REC-09** | DC Output Inspector | OVERLAPS_ANOTHER_CUT | Fourth of four competing rewrites of the same routing.py '### Routing is a tool call — MANDATORY' block (see REC-12). Content-wise it is safe; it is the independent-applicability claim that fails. |
| **REC-09** | DC Output Inspector | UNSAFE_NEEDS_REPLACEMENT | The replacement drops the consequence clause entirely: nowhere does it say that text emitted without a routing call is discarded and the pipeline halts. Its own risk_note claims 'The imperative, the message IS the hand-off clause and the don't-announce clause are all kept' - the halt consequence, which is the actual incident content ('agents once emitted prose without a routing tool call and the pipeline halted'), is not. It is also one of FOUR competing rewrites of the same lines in agents/shared/routing.py (REC-07 UII, REC-12 DCII, REC-17 TC, REC-09 DCOI); only one can apply. |
| **REC-07 / REC-12 / REC-17 / REC-09** | User Input Inspector, DC Input Inspector, Tool Caller, DC Output Inspector | OVERLAPS_ANOTHER_CUT | Four different auditors each propose a DIFFERENT replacement for the identical code block in agents/shared/routing.py lines 248-273 ('### Routing is a tool call — MANDATORY' through '"(one or two lines is plenty).",'). My verbatim check confirms all four anchor to the same 1,658-char span. This is one shared code block spliced into all six chain agents, not four independent cuts — applying any two produces garbage or a silent no-op, and the char-savings claims (933/1050/703/1020) are not additive. All four replacements are syntactically valid Python and none uses {hub}, so no f-prefix is needed. |
| **REC-04** | DC Output Inspector | OVERLAPS_ANOTHER_CUT | A second full rewrite of agents/shared/prompt_fragments/value_states.md, competing with REC-04 (DC Input Inspector), which rewrites the same file end-to-end with different wording. REC-34 and REC-35 (DC Input Creator) additionally carve two sub-regions of the same file. Four cuts, one 2,960-char file, at most one whole-file rewrite can apply. Both whole-file versions preserve the invariants I checked (three states, the SOFT-TARGET-marker-is-its-own-authorisation rule, all three authorisation sources, one-source-is-enough, and the how-far scale), so this is purely an applicability conflict. |
| **REC-04** | DC Input Inspector / DC Output Inspector | OVERLAPS_ANOTHER_CUT | REC-04 (DCII) and REC-04 (DCOI) are two different full rewrites of the SAME 2,884-char span — the entirety of agents/shared/prompt_fragments/value_states.md. My verbatim check confirms both anchor at offset 0 and end at the same point. On top of that, REC-34 and REC-35 (DC Input Creator) rewrite two sub-spans inside it (891 and 595 chars). Four cuts, one file, ~4,000 chars of claimed savings against a 2,960-char file. |
| **REC-35** | DC Input Creator (agents/dc_input_creator) | UNSAFE_NEEDS_REPLACEMENT | The replacement drops 'A line literally saying "user-locked" is only the DEFAULT lock and does NOT override a current authorisation — the hand-off, DESIGN INTENT, and any inline annotation are the current sources of truth.' I grepped for 'user-locked' / 'default lock' across agents/ and DC_prompt_fragments/: in the 7-agent tree the ONLY statement of this rule is the sentence being cut. (Hits in agents/5agent/* and agents/conductor/* are a separate topology and use the phrase in a different sense.) Notably, BOTH whole-file rewrites of the same fragment — REC-04 (DCII) and REC-04 (DCOI) — deliberately keep it ('a line saying "user-locked" is only the default lock'), which is evidence the other auditors judged it load-bearing. Without it, an agent that sees 'user-locked' in a hand-off can treat it as absolute and refuse an authorisation that DESIGN INTENT actually grants — the failure this sentence patches. This cut also overlaps REC-04 (either version), which covers the same closing paragraph. |
| **C-12** | Receptionist | UNSAFE_NEEDS_REPLACEMENT | This is a documented production incident, not a restatement. Commit 799d896 ('fix(prompts): tighten DBa scoping, no chain pre-cooking, no chain second-guessing') records an observed 2026-06-05 run in which 'the Receptionist closed by second-guessing the chain in its user reply', and added this exact block ('Do NOT cast doubt ... Do NOT present comparison tables of past sessions'). The cut is a full DELETE whose own risk_note conditions it on C-10, and C-10 is NOT in this review batch - so an owner applying cuts one at a time loses the behaviour entirely. The generic anti-fabrication rule the rationale leans on covers inventing facts, not adjudicating a value the chain correctly reported. |
| **REC-07** | User Input Inspector | OVERLAPS_ANOTHER_CUT | Rewrites the same block of agents/shared/routing.py (the '### Routing is a tool call - MANDATORY' lines, 248-273) as REC-12 (DCII), REC-17 (TC) and REC-09 (DCOI). The block is built in code and injected into all six chain agents, so at most one of the four can be applied; the other three will silently fail to match, and the owner may believe a preserved clause is in place when it is not. Content-wise this version is safe (mandate, halt consequence, don't-announce all retained). |
| **REC-07 / REC-12 / REC-17 / REC-09** | User Input Inspector, DC Input Inspector, Tool Caller, DC Output Inspector | OVERLAPS_ANOTHER_CUT | Four different auditors each propose a DIFFERENT replacement for the identical code block in agents/shared/routing.py lines 248-273 ('### Routing is a tool call — MANDATORY' through '"(one or two lines is plenty).",'). My verbatim check confirms all four anchor to the same 1,658-char span. This is one shared code block spliced into all six chain agents, not four independent cuts — applying any two produces garbage or a silent no-op, and the char-savings claims (933/1050/703/1020) are not additive. All four replacements are syntactically valid Python and none uses {hub}, so no f-prefix is needed. |
| **REC-04** | DC Input Inspector (dc_input_inspector) | OVERLAPS_ANOTHER_CUT | This is a whole-fragment rewrite of agents/shared/prompt_fragments/value_states.md, and REC-04 (DC Output Inspector) is a second, differently-worded whole-fragment rewrite of the same file, while REC-34 and REC-35 (DCIC) rewrite two of its subsections. The fragment is spliced into the Planner, DCIC, DCII and DCOI, so these four cuts are mutually exclusive; applying more than one either fails to match or double-edits the same rules. Both whole-file versions also drop the FREE-state clause 'unless a directive holds a specific one fixed, which is then treated as LOCKED for that cycle', which survives for the DCII only because its own section 4a restates it. |
| **REC-04** | DC Input Inspector / DC Output Inspector | OVERLAPS_ANOTHER_CUT | REC-04 (DCII) and REC-04 (DCOI) are two different full rewrites of the SAME 2,884-char span — the entirety of agents/shared/prompt_fragments/value_states.md. My verbatim check confirms both anchor at offset 0 and end at the same point. On top of that, REC-34 and REC-35 (DC Input Creator) rewrite two sub-spans inside it (891 and 595 chars). Four cuts, one file, ~4,000 chars of claimed savings against a 2,960-char file. |
| **REC-39** | User Input Inspector | UNSAFE_NEEDS_REPLACEMENT | The premise is right (outerRadius is not a parameter of this DC) but the fix breaks a documented layering rule. DC_prompt_fragments/dc_config/README.md states 'Edit these files to retarget the multi-agent system at a different design configurator (DC)... Per-agent templates live in each agent's own folder (agents/<agent_name>/prompt.md)' - the agent templates are the DC-neutral layer, which is why they use $parameter_list / $parameter_count. Verified: `grep -c impeller agents/*/prompt.md` returns 0 for all nine prompts today. Writing 'impellerRadius: 160 mm - OUT OF RANGE (allowed [60; 80])' into agents/user_input_inspector/prompt.md would be the first propeller literal in the generic layer, and becomes a wrong example the moment the DC is retargeted. REC-05 (User Input Inspector, SOFT TARGET) introduces the same leak with 'impellerRadius: ~75 mm'. The rule itself is an incident patch (commit e46b194: 'the User Input Inspector now marks a value that falls outside its range, which is the only guard on an extraction-only request') and the compression otherwise preserves it. |
| **REC-24 / REC-30 / REC-28** | Tool Caller, DC Input Creator, User Input Inspector | OVERLAPS_ANOTHER_CUT | Three cuts on the STANDING DIRECTIVES bullet in generic_constraints.md. REC-24 (TC) and REC-30 (DCIC) target the identical 454-char span (lines 12-18) with different replacements; REC-28 (UII) targets an 867-char span (lines 6-18) that fully CONTAINS both, so applying REC-28 after either of the others fails to anchor. The invariant itself is safe in all three — the runtime does not depend on the prompt wording here: standing_directives.is_present() matches the directive TEXT, not the header, and orchestrator.py:738 re-stamps the canonical BLOCK_START on every hop in _DIRECTIVE_CARRIERS, so even a paraphrased header self-heals. |
| **REC-24 / REC-30 / REC-28** | Tool Caller, DC Input Creator, User Input Inspector | OVERLAPS_ANOTHER_CUT | Three cuts on the STANDING DIRECTIVES bullet in generic_constraints.md. REC-24 (TC) and REC-30 (DCIC) target the identical 454-char span (lines 12-18) with different replacements; REC-28 (UII) targets an 867-char span (lines 6-18) that fully CONTAINS both, so applying REC-28 after either of the others fails to anchor. The invariant itself is safe in all three — the runtime does not depend on the prompt wording here: standing_directives.is_present() matches the directive TEXT, not the header, and orchestrator.py:738 re-stamps the canonical BLOCK_START on every hop in _DIRECTIVE_CARRIERS, so even a paraphrased header self-heals. |
| **REC-24 / REC-30 / REC-28** | Tool Caller, DC Input Creator, User Input Inspector | OVERLAPS_ANOTHER_CUT | Three cuts on the STANDING DIRECTIVES bullet in generic_constraints.md. REC-24 (TC) and REC-30 (DCIC) target the identical 454-char span (lines 12-18) with different replacements; REC-28 (UII) targets an 867-char span (lines 6-18) that fully CONTAINS both, so applying REC-28 after either of the others fails to anchor. The invariant itself is safe in all three — the runtime does not depend on the prompt wording here: standing_directives.is_present() matches the directive TEXT, not the header, and orchestrator.py:738 re-stamps the canonical BLOCK_START on every hop in _DIRECTIVE_CARRIERS, so even a paraphrased header self-heals. |
| **REC-42 / REC-43** | User Input Inspector / DC Input Creator | OVERLAPS_ANOTHER_CUT | Both anchor at the same quote_start ('### What every agent in any design configurator MUST NOT do (DON'Ts)', line 27) but end at different points — REC-42 spans 648 chars (through 'unchanged input yields nothing new.', line 36), REC-43 spans 472 chars (through 'do not make it.', line 33). They are nested, not independent: REC-43's span lies entirely inside REC-42's. Applying REC-42 first makes REC-43 unanchorable; applying REC-43 first truncates REC-42's span. Both also sit inside the whole-file rewrites REC-03 (DCII) and REC-03 (DCOI). |
| **REC-42 / REC-43** | User Input Inspector / DC Input Creator | OVERLAPS_ANOTHER_CUT | Both anchor at the same quote_start ('### What every agent in any design configurator MUST NOT do (DON'Ts)', line 27) but end at different points — REC-42 spans 648 chars (through 'unchanged input yields nothing new.', line 36), REC-43 spans 472 chars (through 'do not make it.', line 33). They are nested, not independent: REC-43's span lies entirely inside REC-42's. Applying REC-42 first makes REC-43 unanchorable; applying REC-43 first truncates REC-42's span. Both also sit inside the whole-file rewrites REC-03 (DCII) and REC-03 (DCOI). |

---

## 6. Integrity check on the audit itself

The audit ran as a background workflow that was interrupted twice (once by an API error, once by a plan limit) and restarted. Everything below was re-verified afterwards by script against the working tree, not taken on trust.

### What passed

- **All 9 agents are present**, each with a full cut list, a proposed skeleton and auditor notes.
- **Anchors resolve for all 349 cuts** — 177 byte-for-byte, 172 after normalising dashes and whitespace, 0 unresolved.
- **No duplicate cut ids** within any agent.
- **Template substitution is safe.** All 349 replacement strings were scanned for `$slot` and `{format_key}` tokens and checked against the real registries (the slot table in `agents/shared/prompts.py` and the `.format()` kwargs each agent actually passes). 40 tokens appear; **all 40 are valid and intentional** — `{hub}` ×21 inside `routing.py` f-strings, `$parameter_count` ×19, and the rest genuine slots. Three initially looked suspect and were each run down to a false positive: `{input_images_subdir}` is passed at `planner.py:230`; the Database Handler's literal `{"call_orchestrator": …}` is safe because `database_handler.py:1022` builds that prompt with no `.format()` call at all (and the literal is already in the file at line 303); the routing.py brace is a valid f-string expression. **No cut introduces the brace-escape failure.**
- **Tool-schema arithmetic reconciles**: the 22 per-tool savings sum exactly to the declared 8,308 tokens.

### Three caveats you should carry into the review

**A. The `−chars` column is not summable across agents.** Eight of the nine auditors report `chars_removed` *net* — the span they delete minus the replacement they write. The **Orchestrator alone reports it gross** (the whole span, before adding ~12,580 characters of replacement back). Its own notes state this explicitly and its 3,000-token target is computed correctly; only the column is measured differently. Net across all nine is roughly **244,000 characters**, not the 256,766 you get by naive addition.

**B. The `proposed` token column is an estimate for eight of nine agents.** Only the **Planner** re-assembled its prompt the way `prompts.py` does, applied every cut programmatically, and re-measured the result (which is why its figure moved from an early 3,400 to a measured 5,470). The Receptionist reproduced the assembly to validate its *baseline* but estimated the target section by section. Treat the other seven targets as ±15% until the cuts are applied and re-measured with `measure_prompts.py`.

**C. 115 of 349 cuts were never adversarially verified.** The three verifier lenses ran against the first audit pass, before the interruption. The cuts for **Orchestrator, Planner, Database Handler** were produced afterwards and carry only their own auditor's risk rating. Their medium-risk rows deserve the same scrutiny the verifiers gave the others.

**Span conflicts found:** 4 cuts overlap another cut in the same file and are marked ⛔ — `UII-47`, `UII-28`, `UII-36`, `UII-40`. Apply one of each overlapping pair, not both.

### A note on §2's source-file column

Twelve rows in the duplication census name several files at once (e.g. "`agents/{orchestrator,planner,…}/prompt.md` (in-prompt copy-paste)") instead of a single path. That is not a formatting slip — it *is* the finding: those blocks have no shared fragment at all and are copy-pasted prose. The census's per-row savings sum to 31,660 against a declared total of 31,765, a 105-token rounding difference.

---

## 7. Second-opinion audits (independent re-runs)

When the workflow was restarted it re-ran four agents that had already completed, producing a **second, completely independent audit** of the same prompt by a fresh auditor. Sections 1–5 use the first pass throughout, because that is the pass the adversarial verifiers reviewed — mixing the two would leave the verifier flags pointing at cuts that no longer exist.

The second opinions are reproduced here rather than discarded. They are not corrections; they are a different reviewer reaching a different answer from the same source, which is useful signal about where the judgement calls are.

| Agent | 1st pass cuts → target | 2nd pass cuts → target | disagreement |
|---|---|---|---|
| Tool Caller | 32 → 2,250 | 30 → 2,550 | 300 tok |
| DC Input Creator | 53 → 3,315 | 53 → 3,200 | 115 tok |
| User Input Inspector | 49 → 4,600 | 44 → 3,250 | 1,350 tok |
| DC Input Inspector | 29 → 2,500 | 36 → 3,650 | 1,150 tok |

The **User Input Inspector** is the one that matters: the second auditor reached **3,250 tokens** where the first stopped at 4,600, using 44 cuts instead of 49. Since the UII is the largest outlier against your 1,000–3,000 target, its second opinion is worth reading before deciding that agent needs an architectural fix.

### 7.x Tool Caller — second opinion (30 cuts → ~2,550 tok)

| action | section | −chars | risk | what |
|---|---|---:|---|---|
| COMPRESS | ## Active mesh-check backend: PyVista / VTK (renders vi | 1559 | low | Backend implementation trivia (MultiBlock merging, divergence-theorem volume, VTK compute_cell_sizes) never changes what the Tool Caller does — only the meaning of three report lines does. |
| COMPRESS | ## State THIS CYCLE clearly (IMPORTANT) | 1013 | low | The rule is one sentence plus the four literal return-text markers; the rest is justification, a no-fixed-template disclaimer, and three sample phrasings the model does not need. |
| COMPRESS | ## Active render / mesh-check backend: trimesh + pyrend | 943 | low | Same as REC-01 for the other backend: keep only the semantics of the metrics the agent must relay, drop the library internals. |
| COMPRESS | ## Utility tools: list_attempts() and read_attempt(n, f | 912 | low | Both tools are already described in $tool_inventory eleven lines earlier and in their own tool schemas; only the "diagnostic, don't loop, don't invent strategy" steer is new. |
| COMPRESS | routing_instructions() — "### Routing is a tool call —  | 780 | medium | Three paragraphs restate one mandate plus a retired ``---ROUTING---`` format that no longer needs naming; the same rule is also in generic_constraints.md. |
| DELETE | ## End-of-session feedback message (read-only) | 683 | low | Read-only meta about a message that may arrive after the session's routing work is over; the Tool Caller needs no instruction to read a HumanMessage addressed to it. |
| COMPRESS | whole file (the 16-parameter list) | 609 | medium | Keeps all 16 names, units and ranges but states the repeated unit glosses (% of own chord / tenths of chord / degrees AoA) once instead of eleven times. |
| DELETE | routing_instructions() — "### Do not loop — ESCALATE wh | 554 | low | Verbatim duplicate of the generic_constraints DON'T-loop rule that every one of these agents already carries in the same prompt. |
| COMPRESS | ## Range check before you generate (HARD — independent  | 537 | low | The check, the hard STOP, the report-don't-fix rule and the at-min/max exception all survive; the two paragraphs explaining WHY the check is redundant do not change behaviour. |
| COMPRESS | ### Tool-use hard rules (every agent) | 495 | low | Same three rules, stated once each without the parenthetical justifications and the who-opens-the-attempt aside (which is DCIC business, not every agent's). |
| COMPRESS | routing_instructions() — "### Permission / authorisatio | 476 | low | Two paragraphs of hedging around one rule: re-read before escalating, escalate to the hub, CLARIFY only for fixable data issues. |
| COMPRESS | ### Domain hard rules (every agent) | 456 | low | Three long enumerations (invented params, post-processing verbs, unsupported analyses) shrink to canonical examples without losing any category. |
| COMPRESS | ## Attempt folder (IMPORTANT — read this before any too | 447 | low | Keeps the single-writable-folder invariant, the escalate-if-missing rule and the reuse-in-place fact; drops the re-explanation of append-only semantics that hard_constraints_tools already states. |
| COMPRESS | ## HARD LIMITS — Do NOT | 434 | low | The mesh-operation list duplicates hard_constraints_dc verbatim; the four bullets collapse to one principle (exhaustive tool set, escalate, don't decide strategy). |
| COMPRESS | ## Data Flow and reporting file paths (IMPORTANT) | 403 | medium | The three labels and the verbatim-paths rule are load-bearing (the DCOI cannot see images otherwise); the surrounding restatements are not. |
| COMPRESS | ## Loading parameters (IMPORTANT) | 385 | low | Four sentences of scene-setting collapse to the actual instruction: read the given path, parse, call the tool with output_dir. |
| COMPRESS | ### Blade-sections visualizer | 330 | low | Same three facts (what it draws, who calls it, it is cheap and can be the deliverable) without the two speed justifications. |
| COMPRESS | routing_instructions() — "### How to decide where to ro | 319 | low | Four decision rules become four one-line arrow rules; the branch semantics are identical. |
| COMPRESS | **When to (re-)call ``read_parameters``** | 294 | low | Two bullets plus a repeat of the no-guessed-path rule reduce to one sentence with the same two triggers. |
| COMPRESS | DON'Ts — "DON'T communicate to another agent in plain p | 279 | medium | Keeps the whole invariant (only channel, message IS the hand-off, silent discard + halt, same-response, the two exceptions) in four lines instead of ten. |
| COMPRESS | whole file (utility tool blurbs) | 279 | low | Tool blurbs duplicate the bound tool schemas; keep only what the schema cannot say (one call does mesh + render; no separate render tool). |
| COMPRESS | DOs — "DO carry STANDING DIRECTIVES verbatim" | 241 | medium | The invariant is 'reproduce the block UNCHANGED; only the Planner edits it' — the rest is restated emphasis. |
| MERGE | DON'Ts — "DON'T bounce permission questions back to the | 236 | medium | Duplicates the routing block's Permission/authorisation section, which every chain agent also receives (and which is the only one of the two that carries the re-read-first nuance). |
| COMPRESS | <<BSV_ON>> Render type — sections vs the full 3D | 205 | low | One conditional instruction; the restatement of the default case and the cross-reference to a section three screens down add nothing. |
| COMPRESS | DON'Ts — retry-blindly / don't-script-the-user-reply | 193 | low | Retry-blindly is the DON'T-loop rule two bullets up; the user-facing-reply rule is one clause, not four lines. |
| MERGE | DOs — "DO follow the natural pipeline" / "DO ESCALATE t | 180 | low | Both bullets restate the routing block's FORWARD/ESCALATE rules, which are per-agent and name the actual next agent. |
| DELETE | DOs — "DO act on the inputs in your hand-off" | 143 | low | Restates default behaviour, and the operative half (only use supplied paths) is already the first rule in hard_constraints_tools.md. |
| COMPRESS | ### Available routing tools | 121 | low | Three routing tools, one line each; the conditional CLARIFY wording does not need a second clause explaining what the inspector might catch. |
| COMPRESS | DOs — "DO write hand-off messages as free-form prose" | 117 | low | Near-duplicate of the routing block's free-form-prose paragraph; only the never-relabel-the-source clause is unique and is kept. |
| COMPRESS | ## Your Role | 41 | low | Same statement, one line shorter. |

<details><summary><b>Full text of each second-opinion change</b></summary>

#### REC-01 · COMPRESS · −1559 chars · risk low

*File:* `DC_prompt_fragments/tools_config/render_check_library/pyvista.md` · *Section:* ## Active mesh-check backend: PyVista / VTK (renders via pyrender)

**Why:** Backend implementation trivia (MultiBlock merging, divergence-theorem volume, VTK compute_cell_sizes) never changes what the Tool Caller does — only the meaning of three report lines does.

**Cut from** `## Active mesh-check backend: PyVista / VTK (renders via pyrender)

For this session the render+check step of ``generate_and_render_propeller```

**...through** `All three PNGs are 800×600 — identical pipeline to the trimesh
  backend.`

**Replace with:**

```
## Active mesh-check backend: PyVista / VTK (renders via pyrender)

So you read the tool's return text correctly: watertight means no open edges
AND manifold (same meaning as the trimesh backend's); volume is reported only
when watertight and a non-positive value (inverted normals) is surfaced as a
WARNING; degenerate faces are those under 1e-10 mm².  Renders are the same
three 800×600 pyrender PNGs as the trimesh backend.
```

#### REC-02 · COMPRESS · −1013 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* ## State THIS CYCLE clearly (IMPORTANT)

**Why:** The rule is one sentence plus the four literal return-text markers; the rest is justification, a no-fixed-template disclaimer, and three sample phrasings the model does not need.

**Cut from** `## State THIS CYCLE clearly (IMPORTANT)
The DC Output Inspector is stateful and keeps prior renders and prior`

**...through** `re-loading conservatively; precise wording saves tool calls.`

**Replace with:**

```
## Say what is NEW this cycle
The DC Output Inspector keeps prior renders and QC reports in its history, so
it will mix cycles unless you say what changed.  In your own words (no fixed
template), state which artifacts the mesh tool reported as freshly written
("Mesh saved …", "Renders saved:") versus reused ("Reused existing mesh …",
"Renders already present"), and give only the CURRENT quality numbers.
Precise wording saves the DCOI a conservative re-load of the images.
```

#### REC-03 · COMPRESS · −943 chars · risk low

*File:* `DC_prompt_fragments/tools_config/render_check_library/trimesh.md` · *Section:* ## Active render / mesh-check backend: trimesh + pyrender

**Why:** Same as REC-01 for the other backend: keep only the semantics of the metrics the agent must relay, drop the library internals.

**Cut from** `## Active render / mesh-check backend: trimesh + pyrender

For this session the render+check step of ``generate_and_render_propeller```

**...through** `smooth shading, three directional lights).  All three
PNGs are 800×600.`

**Replace with:**

```
## Active render / mesh-check backend: trimesh + pyrender

So you read the tool's return text correctly: watertight means every edge is
shared by exactly two faces; volume is reported only when watertight and a
non-positive value (inverted normals) is surfaced as a WARNING; degenerate
faces are those under 1e-10 mm².  Renders are three 800×600 pyrender PNGs.
```

#### REC-04 · COMPRESS · −912 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* ## Utility tools: list_attempts() and read_attempt(n, file)

**Why:** Both tools are already described in $tool_inventory eleven lines earlier and in their own tool schemas; only the "diagnostic, don't loop, don't invent strategy" steer is new.

**Cut from** `## Utility tools: list_attempts() and read_attempt(n, file)
Two bound utility tools let you inspect attempt folders under`

**...through** `retry strategies — strategy decisions belong to the Planner.`

**Replace with:**

```
``list_attempts`` and ``read_attempt(n, file)`` are diagnostic only — use them
to confirm what an earlier attempt actually holds, never to loop or to invent
your own retry strategy.
```

#### REC-05 · COMPRESS · −780 chars · risk medium

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — "### Routing is a tool call — MANDATORY"

**Why:** Three paragraphs restate one mandate plus a retired ``---ROUTING---`` format that no longer needs naming; the same rule is also in generic_constraints.md.

**Risk:** This is the patch for the real "prose without a routing tool call halts the pipeline" failure. The replacement keeps the MUST, the same-response requirement, and the never-announce clause — but it drops the explicit ban on the retired ``---ROUTING---`` template, so a model that saw that format in old logs could re-emit it. Shared by all 6 chain agents (Planner, UII, DCIC, DCII, TC, DCOI).

**Cut from** `"### Routing is a tool call — MANDATORY",
        "Every response that ends your turn MUST invoke exactly one of "`

**...through** `"(one or two lines is plenty).",`

**Replace with:**

```
        "### Routing is a tool call — MANDATORY",
        "Every response that ends your turn MUST invoke exactly one of the "
        "routing tools above, in the same response where you finish your "
        "work — never announce a call instead of making it.  Its ``message`` "
        "argument IS the whole hand-off: free-form prose (no template, no "
        "option menus) carrying everything the recipient needs — paths their "
        "tools require, what changed and why, authorship of any "
        "non-user-authored value — and nothing more.  Your verbose work "
        "product stays in your own history; ordinary response text is "
        "delivered to no one, so keep it to a line or two.",
```

#### REC-06 · DELETE · −683 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* ## End-of-session feedback message (read-only)

**Why:** Read-only meta about a message that may arrive after the session's routing work is over; the Tool Caller needs no instruction to read a HumanMessage addressed to it.

**Risk:** Removes 683 assembled chars (393 of prompt.md plus the two eos fragments, which stay in place for the other six agents that splice them).

**Cut from** `## End-of-session feedback message (read-only)

$eos_feedback_intro
For you, "your scope" is: your tool-execution reporting`

**...through** `attempting invented workarounds.

$eos_feedback_outro`

**Replace with:** *(nothing — pure deletion)*

#### REC-07 · COMPRESS · −609 chars · risk medium

*File:* `DC_prompt_fragments/dc_config/parameters.md` · *Section:* whole file (the 16-parameter list)

**Why:** Keeps all 16 names, units and ranges but states the repeated unit glosses (% of own chord / tenths of chord / degrees AoA) once instead of eleven times.

**Risk:** Spliced by 7 agents, and the DCII's per-parameter range audit reads it literally. Verify every name and bracket survives the diff, and that the middlePos span formula and the derived-ring-height note are intact. The shared gloss line now also states the real *Thickness/*Camber = % of that section's OWN chord gotcha, which previously lived only in modelling_notes.md.

**Cut from** `### Global / ring
 1. bladeCount         (integer)              — Number of blades [3; 6]`

**...through** `16. outerAngle     (degrees)                   — Angle of attack [2; 25]`

**Replace with:**

```
### Global / ring
 1. bladeCount        (integer) — Number of blades [3; 6]
 2. impellerRadius    (mm)      — Outer radius of the impeller ring [60; 80]
 3. impellerThickness (mm)      — Wall thickness of the outer ring [1; 5]
(The outer-ring HEIGHT is not a parameter — it is derived to fit the outer blade section.)

Thickness and camber are % of THAT section's OWN chord; maxPos is an integer
in tenths of chord; angle is the angle of attack in degrees.

### Inner blade section
 4. innerThickness [3; 24]   5. innerMaxPos [2; 8]   6. innerCamber [0; 9]
 7. innerChord (mm) [3; 11]  8. innerAngle [2; 25]

### Middle blade section
 9. middlePos — position along the blade span: 0 = root (hub, r = 4 mm),
    1 = tip; radius = 4 + middlePos·(impellerRadius − 4) mm [0.3; 0.7]
10. middleChord (mm) [10; 30]   11. middleAngle [2; 25]

### Outer blade section
12. outerThickness [3; 24]  13. outerMaxPos [2; 8]  14. outerCamber [0; 9]
15. outerChord (mm) [10; 30]  16. outerAngle [2; 25]
```

#### REC-08 · DELETE · −554 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — "### Do not loop — ESCALATE when stuck"

**Why:** Verbatim duplicate of the generic_constraints DON'T-loop rule that every one of these agents already carries in the same prompt.

**Risk:** Keep the generic_constraints bullet ("DON'T loop: … STOP and ESCALATE") — do not apply this cut together with any deletion of that bullet. Affects all 6 chain agents.

**Cut from** `"### Do not loop — ESCALATE when stuck",
        "If you find yourself about to call the same tool with the same "`

**...through** `"consult another agent, or ask the user.  Never silently loop.",
        "",`

**Replace with:** *(nothing — pure deletion)*

#### REC-09 · COMPRESS · −537 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* ## Range check before you generate (HARD — independent of upstream)

**Why:** The check, the hard STOP, the report-don't-fix rule and the at-min/max exception all survive; the two paragraphs explaining WHY the check is redundant do not change behaviour.

**Cut from** `## Range check before you generate (HARD — independent of upstream)

You are the last agent to see ``parameters.json`` before the generator runs,`

**...through** ```write_parameters``
verifies only that the fields are present and numeric.`

**Replace with:**

```
## Range check before you generate (HARD)
You are the last agent to read ``parameters.json`` before the generator runs,
and nothing in the tooling validates ranges.  Compare EVERY value against its
[min; max] above, one by one — a glance is not a check.  Any value strictly
outside its range is a hard STOP: do not generate; route back to the agent
that wrote the parameters, quoting the parameter, its value and its allowed
range.  Exactly at min or max is fine.  Never clip, round or adjust a value
yourself — authoring values belongs to the agent that wrote them.
```

#### REC-10 · COMPRESS · −495 chars · risk low

*File:* `DC_prompt_fragments/tools_config/hard_constraints_tools.md` · *Section:* ### Tool-use hard rules (every agent)

**Why:** Same three rules, stated once each without the parenthetical justifications and the who-opens-the-attempt aside (which is DCIC business, not every agent's).

**Risk:** Shared by all 8 agents. Preserves the append-only invariant, the no-guessed-path rule and the mandatory calculate rule.

**Cut from** `### Tool-use hard rules (every agent)
- DON'T invent or guess a path for a read tool: read tools take only the`

**...through** `the Orchestrator only as a fallback) — never edit the old
  folder's parameters.`

**Replace with:**

```
### Tool-use hard rules (every agent)
- DON'T invent or guess a path: read tools take only the paths a hand-off
  label gives (``Input directory:`` / ``Extracted inputs file:`` /
  ``Parameters file:`` / ``Render images:`` / ``Current attempt:``) or an
  upstream tool's return value.
- DO route EVERY arithmetic operation — sums, ratios, conversions, range
  comparisons — through ``calculate`` (never mental arithmetic), batching this
  turn's expressions into ONE call.
- Attempt folders are append-only: write only into the ``Current attempt:``
  folder, never rewrite or delete a ``parameters.json`` or mesh already there,
  and COPY an old parameter set into a NEW attempt to build on it.  Re-running
  the render/QC tool on an attempt that has renders reuses them in place.
```

#### REC-11 · COMPRESS · −476 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — "### Permission / authorisation issues → hub"

**Why:** Two paragraphs of hedging around one rule: re-read before escalating, escalate to the hub, CLARIFY only for fixable data issues.

**Risk:** Keeps the _authorisation_sources(hub) call, so the topology-aware grantor list is unchanged. Affects all 6 chain agents.

**Cut from** `f"### Permission / authorisation issues → {hub} (not "
        "the previous agent)",`

**...through** `"NOT for permission questions.",`

**Replace with:**

```
        f"### Permission / authorisation → {hub}",
        "Before escalating for a missing authorisation, re-read the incoming "
        "hand-off (and any file it points to) once more: if it already names "
        "an authorisation that plausibly covers the action, act on it rather "
        "than asking again.  When one is truly missing or ambiguous, ESCALATE "
        f"to the {hub} — " + _authorisation_sources(hub) + "  CLARIFY back to "
        "the previous agent only for data / wording / format issues it can "
        "actually fix.",
```

#### REC-12 · COMPRESS · −456 chars · risk low

*File:* `DC_prompt_fragments/dc_config/hard_constraints_dc.md` · *Section:* ### Domain hard rules (every agent)

**Why:** Three long enumerations (invented params, post-processing verbs, unsupported analyses) shrink to canonical examples without losing any category.

**Risk:** Shared by all 8 agents. Keeps the no-invented-parameter rule, the no-mesh-editing rule and the three-metrics-only rule.

**Cut from** `### Domain hard rules (every agent)
- DON'T express a design in anything but the $parameter_count named`

**...through** `rely on visual
  inspection and say so plainly.`

**Replace with:**

```
### Domain hard rules (every agent)
- The $parameter_count named parameters are the ONLY design vocabulary:
  reject invented ones (hub_radius, tip_clearance, any "supplemental"
  parameter).  Geometry changes ONLY by changing those values and
  regenerating via the DC Input Creator → Tool Caller path; there is no mesh
  editing or post-processing (booleans, welding, remeshing, hole filling,
  fillets, supports).
- DON'T offer analysis or output the system cannot produce: performance,
  thrust, flow, efficiency, CFD, FEA / stress / material, alternative formats
  (STL, STEP, IGES), other camera angles, cross-sections or higher-resolution
  renders.
- The ONLY mesh metrics are watertightness, volume and degenerate-face count;
  with mesh checks disabled, rely on visual inspection and say so plainly.
```

#### REC-13 · COMPRESS · −447 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* ## Attempt folder (IMPORTANT — read this before any tool call)

**Why:** Keeps the single-writable-folder invariant, the escalate-if-missing rule and the reuse-in-place fact; drops the re-explanation of append-only semantics that hard_constraints_tools already states.

**Cut from** `## Attempt folder (IMPORTANT — read this before any tool call)
Every design generation lives inside an attempt folder under`

**...through** `are NOT bound to ``new_attempt`` and must not invent or guess an
attempt path.`

**Replace with:**

```
## Attempt folder
Your hand-off carries ``Current attempt: <absolute path>`` — the only folder
you may write into this cycle, and the ``output_dir`` argument for every
utility tool.  If that line is missing, ESCALATE; never invent or guess an
attempt path.  ``generate_and_render_propeller`` reuses an existing mesh and
existing renders in place (both are append-only), so re-running it on an
attempt that already has them is fine and needs no new attempt.
```

#### REC-14 · COMPRESS · −434 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* ## HARD LIMITS — Do NOT

**Why:** The mesh-operation list duplicates hard_constraints_dc verbatim; the four bullets collapse to one principle (exhaustive tool set, escalate, don't decide strategy).

**Risk:** Apply together with REC-12, which keeps the mesh post-processing ban in the shared DC fragment — do not apply this cut if hard_constraints_dc.md is also stripped of that bullet.

**Cut from** `## HARD LIMITS — Do NOT
- You have EXACTLY the utility tools listed above (plus the read`

**...through** `- Do NOT invent parameter tweaks of your own initiative.`

**Replace with:**

```
## Limits
The tools above are exhaustive: no mesh editing, no new tools or scripts, no
parameter tweaks of your own initiative.  When something is impossible or
fails, ESCALATE with a factual description of the blocker — you do not decide
what to do next, and you do not offer a menu of options.
```

#### REC-15 · COMPRESS · −403 chars · risk medium

*File:* `agents/tool_caller/prompt.md` · *Section:* ## Data Flow and reporting file paths (IMPORTANT)

**Why:** The three labels and the verbatim-paths rule are load-bearing (the DCOI cannot see images otherwise); the surrounding restatements are not.

**Risk:** This is the only statement that the DCOI receives no images automatically. The replacement keeps that sentence and the label block verbatim — do not delete it outright.

**Cut from** `## Data Flow and reporting file paths (IMPORTANT)
In the ``message`` argument of your routing tool include only a brief`

**...through** `so
the DCOI can also use ``read_attempt`` against the right folder.`

**Replace with:**

```
## Reporting (the ``message`` argument of your routing tool)
Keep it brief — success/failure plus, when the artifacts were produced this
cycle, these labels, each on its own line, copied verbatim from the tool's
return text:

    Current attempt: <re-emit the path the hand-off carried>
    Mesh file: <absolute mesh path>
    Render images:
      <one absolute render path per line>

The DC Output Inspector receives no images automatically and can only load
paths you list here, so never invent, rename or shorten them.  If rendering
failed or was skipped, say so and list no render paths.  ``Current attempt:``
is required on every routing call.
```

#### REC-16 · COMPRESS · −385 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* ## Loading parameters (IMPORTANT)

**Why:** Four sentences of scene-setting collapse to the actual instruction: read the given path, parse, call the tool with output_dir.

**Risk:** The 'no guessed path / ESCALATE' clause that follows this block is preserved by REC-19; apply both, or keep one copy of that clause.

**Cut from** `## Loading parameters (IMPORTANT)
You do NOT receive ``parameters.json`` automatically.  The incoming`

**...through** `there is no separate render step to call
afterwards.`

**Replace with:**

```
## Loading parameters
Call ``read_parameters`` with the ``Parameters file:`` path given in the
hand-off, verbatim.  Parse the $parameter_count values, then call the
mesh-generation tool with those values plus the ``Current attempt:`` path as
``output_dir``.  That one call builds the mesh AND renders + checks it; there
is no separate render step.
```

#### REC-17 · COMPRESS · −330 chars · risk low

*File:* `DC_prompt_fragments/tools_config/blade_sections_visualizer.md` · *Section:* ### Blade-sections visualizer

**Why:** Same three facts (what it draws, who calls it, it is cheap and can be the deliverable) without the two speed justifications.

**Risk:** Spliced into all 9 agents when BSV is on, so the saving multiplies across the fleet.

**Cut from** `### Blade-sections visualizer

The system can render JUST the blade cross-sections — a flat image showing the`

**...through** `refined cheaply on their own, and can even be the final
deliverable.`

**Replace with:**

```
### Blade-sections visualizer

The Tool Caller can render JUST the blade cross-sections — the three sections
(Inner, Middle, Outer) stacked vertically, each at its true angle of attack —
from an attempt's parameters file, via `render_blade_sections`.  It skips the
slow full-3D mesh, so a request centred on the blade sections can be rendered
and refined cheaply on its own, and the image can even be the final deliverable.
```

#### REC-18 · COMPRESS · −319 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — "### How to decide where to route"

**Why:** Four decision rules become four one-line arrow rules; the branch semantics are identical.

**Risk:** Affects all 6 chain agents. Keeps the 'no instruction means continue' default.

**Cut from** `"### How to decide where to route",
        f"- If the {hub}'s instruction in your incoming message told "`

**...through** `f"can fix it, route to the {hub} (ESCALATE).",`

**Replace with:**

```
        "### How to decide where to route",
        "- Your work succeeded and nothing told you to report back → "
        "FORWARD to the next agent (no instruction means continue).",
        f"- The {hub} asked you to report back → route to the {hub}.",
        "- The upstream message is ambiguous, missing data, or wrong in a "
        "way the previous agent can fix → CLARIFY back to it.",
        f"- Nothing in the chain can fix it → ESCALATE to the {hub}.",
```

#### REC-19 · COMPRESS · −294 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* **When to (re-)call ``read_parameters``**

**Why:** Two bullets plus a repeat of the no-guessed-path rule reduce to one sentence with the same two triggers.

**Cut from** `**When to (re-)call ``read_parameters``**:
  - If the hand-off marks the line`

**...through** ```Parameters file:`` line was supplied, ESCALATE — do not proceed.`

**Replace with:**

```
Re-read the parameters file whenever the hand-off marks it ``(newly written
this cycle)``, or whenever you are not certain your remembered content still
matches disk.  Never call ``read_parameters`` with a guessed path; if no
``Parameters file:`` line was supplied, ESCALATE.
```

#### REC-20 · COMPRESS · −279 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DON'Ts — "DON'T communicate to another agent in plain prose"

**Why:** Keeps the whole invariant (only channel, message IS the hand-off, silent discard + halt, same-response, the two exceptions) in four lines instead of ten.

**Risk:** This is the primary statement of the real 'prose without a routing call halts the pipeline' failure, and the Receptionist and Orchestrator get NO routing.py boilerplate — so this fragment is their only copy. Preserve the closing <</CHAIN_ONLY>> marker exactly as shown or the conditional region breaks. Shared by all 8 agents.

**Cut from** `<</CHAIN_ONLY>>- DON'T communicate to another agent in plain prose.  The ONLY channel`

**...through** `only exceptions are the Receptionist's direct user replies and the
  Orchestrator's final user-facing wrap-up.`

**Replace with:**

```
<</CHAIN_ONLY>>- DON'T emit prose without a routing tool call: ``call_<agent>``
  is the ONLY channel to another agent and its ``message`` argument IS the
  hand-off; any text you emit without invoking one is discarded and the
  pipeline halts.  Invoke it in the same response where you finish your work.
  (Only the Receptionist's direct user replies and the Orchestrator's final
  wrap-up are exempt.)
```

#### REC-21 · COMPRESS · −279 chars · risk low

*File:* `DC_prompt_fragments/tools_config/tool_inventory.md` · *Section:* whole file (utility tool blurbs)

**Why:** Tool blurbs duplicate the bound tool schemas; keep only what the schema cannot say (one call does mesh + render; no separate render tool).

**Risk:** Tool Caller is the only agent that splices $tool_inventory, so this cut is agent-local.

**Cut from** `1. **generate_and_render_propeller** — build ``propeller_mesh.obj`` into the`

**...through** `an image or mesh returns a path to hand on, e.g. to
   ``view_images``).`

**Replace with:**

```
1. **generate_and_render_propeller** — pass the 16 parameters plus
   ``output_dir``; ONE call builds ``propeller_mesh.obj`` AND renders the
   three views (isometric / top / side) with the quality metrics.  Returns
   the mesh path then the render+check report.  There is no separate render
   tool.
2. **calculate** — arithmetic / boolean expressions; batch per turn.
3. **list_attempts** — numbered summary of every attempt folder and what each
   holds (parameters / mesh / renders / description).
4. **read_attempt(n, file)** — read one file from the n-th attempt (text
   inline; an image or mesh returns a path).
```

#### REC-22 · COMPRESS · −241 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DOs — "DO carry STANDING DIRECTIVES verbatim"

**Why:** The invariant is 'reproduce the block UNCHANGED; only the Planner edits it' — the rest is restated emphasis.

**Risk:** Directly related to the real bug where a restated SUBSET of authorised parameters silently revoked a chord authorisation. The replacement keeps UNCHANGED plus 'never alter, summarise, re-order or omit', which is the general principle behind that incident. Shared by all 8 agents.

**Cut from** `- DO carry STANDING DIRECTIVES verbatim: if your incoming hand-off`

**...through** `it carries instructions later agents depend on, and only the Planner may
  set or change it.`

**Replace with:**

```
- DO reproduce any ``=== STANDING DIRECTIVES ===`` … ``=== END STANDING
  DIRECTIVES ===`` block UNCHANGED in your outgoing hand-off — never alter,
  summarise, re-order or omit it; only the Planner may change it.
```

#### REC-23 · MERGE · −236 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DON'Ts — "DON'T bounce permission questions back to the previous agent"

**Why:** Duplicates the routing block's Permission/authorisation section, which every chain agent also receives (and which is the only one of the two that carries the re-read-first nuance).

**Risk:** Only chain agents see this bullet (it is inside <<CHAIN_ONLY>>) and every chain agent gets routing.py's version, so nothing is lost — but the opening <<CHAIN_ONLY>> marker MUST remain, hence the replacement is that marker alone. Do not apply together with a deletion of routing.py's permission section.

**Cut from** `<<CHAIN_ONLY>>- DON'T bounce permission questions back to the previous agent.`

**...through** `or the Orchestrator itself; route
  them to the Orchestrator.`

**Replace with:**

```
<<CHAIN_ONLY>>
```

#### REC-24 · COMPRESS · −205 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* <<BSV_ON>> Render type — sections vs the full 3D

**Why:** One conditional instruction; the restatement of the default case and the cross-reference to a section three screens down add nothing.

**Risk:** Preserve the <<BSV_ON>> / <</BSV_ON>> markers exactly or the conditional region breaks.

**Cut from** `<<BSV_ON>>**Render type — sections vs the full 3D.**  If your incoming hand-off`

**...through** `as usual.  See the blade-sections note further down.<</BSV_ON>>`

**Replace with:**

```
<<BSV_ON>>If the hand-off asks you to render the blade sections rather than the
full 3D propeller, call ``render_blade_sections`` with the ``Parameters file:``
path instead of the mesh-generation tool, and generate nothing else this cycle.<</BSV_ON>>
```

#### REC-25 · COMPRESS · −193 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DON'Ts — retry-blindly / don't-script-the-user-reply

**Why:** Retry-blindly is the DON'T-loop rule two bullets up; the user-facing-reply rule is one clause, not four lines.

**Risk:** Shared by all 8 agents (chain agents only — inside <<CHAIN_ONLY>>).

**Cut from** `- DON'T retry a failing step blindly; when the same class of failure`

**...through** `never write the user-facing message yourself.`

**Replace with:**

```
- DON'T retry a failing step blindly, and DON'T write the user-facing reply —
  the Receptionist composes the user's wording.
```

#### REC-26 · MERGE · −180 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DOs — "DO follow the natural pipeline" / "DO ESCALATE to the Orchestrator"

**Why:** Both bullets restate the routing block's FORWARD/ESCALATE rules, which are per-agent and name the actual next agent.

**Risk:** Preserve the opening <<CHAIN_ONLY>> marker (it is included in the replacement). Shared by all 8 agents.

**Cut from** `<<CHAIN_ONLY>>- DO follow the natural pipeline: when your work succeeds and the`

**...through** `request, still-ambiguous hand-off after one CLARIFY).`

**Replace with:**

```
<<CHAIN_ONLY>>- DO forward to your natural next agent when your work succeeded
  and nothing asked you to report back; ESCALATE to the Orchestrator the
  moment something blocks you that no other chain agent can fix.
```

#### REC-27 · DELETE · −143 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DOs — "DO act on the inputs in your hand-off"

**Why:** Restates default behaviour, and the operative half (only use supplied paths) is already the first rule in hard_constraints_tools.md.

**Risk:** Shared by all 8 agents.

**Cut from** `- DO act on the inputs in your hand-off and the data files it`

**...through** `use your read tools on the paths the upstream agent
  supplied.`

**Replace with:** *(nothing — pure deletion)*

#### REC-28 · COMPRESS · −121 chars · risk low

*File:* `agents/shared/prompt_fragments/routing_tool_caller.md` · *Section:* ### Available routing tools

**Why:** Three routing tools, one line each; the conditional CLARIFY wording does not need a second clause explaining what the inspector might catch.

**Risk:** Preserve the <<DCII_ONLY>> / <<DCII_OFF>> markers exactly as shown. Tool-Caller-only fragment.

**Cut from** `### Available routing tools
- ``call_dc_output_inspector(message)`` — FORWARD when mesh + renders`

**...through** `ESCALATE on tool failure or any
  other blocker the upstream chain agent cannot fix.`

**Replace with:**

```
### Available routing tools
- ``call_dc_output_inspector(message)`` — FORWARD when mesh + renders +
  report all exist.  This is the natural next step in the pipeline.
<<DCII_ONLY>>- ``call_dc_input_inspector(message)`` — CLARIFY back when a
parameter audit caused a tool failure.<</DCII_ONLY>><<DCII_OFF>>- ``call_dc_input_creator(message)`` — CLARIFY back when its parameter
values caused a tool failure.<</DCII_OFF>>
- ``call_orchestrator(message)`` — ESCALATE on tool failure or any other
  blocker the upstream chain agent cannot fix.
```

#### REC-29 · COMPRESS · −117 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DOs — "DO write hand-off messages as free-form prose"

**Why:** Near-duplicate of the routing block's free-form-prose paragraph; only the never-relabel-the-source clause is unique and is kept.

**Risk:** Preserve the leading <</CHAIN_ONLY>> marker (included in the replacement). Shared by all 8 agents; the Receptionist and Orchestrator have no routing-block copy of this, so keep the clause rather than deleting the bullet.

**Cut from** `<</CHAIN_ONLY>>- DO write hand-off messages as free-form prose carrying exactly what`

**...through** `never relabel one source as another)
  — and nothing more.`

**Replace with:**

```
<</CHAIN_ONLY>>- DO write hand-offs as prose carrying exactly what the recipient
  needs, naming the true source of any non-user-authored value ("the Planner
  directed …"; never relabel one source as another).
```

#### REC-30 · COMPRESS · −41 chars · risk low

*File:* `agents/tool_caller/prompt.md` · *Section:* ## Your Role

**Why:** Same statement, one line shorter.

**Cut from** `## Your Role
Execute the design tools as instructed.  You have access to these`

**...through** `UTILITY tools (in addition to the read and routing tools listed
further down):`

**Replace with:**

```
## Your Role
Execute the design tools as instructed.  Your UTILITY tools (besides the read
and routing tools below):
```

</details>

**Auditor notes.** MEASUREMENT BASIS. chars_removed = characters removed from the ASSEMBLED Tool Caller prompt, computed as (exact byte length of the quoted block, counted with awk over the real line ranges) minus (exact byte length of the replacement text I wrote and measured with wc -c). Where a prompt.md cut also removes a $slot (REC-06 removes $eos_feedback_intro/outro), the count includes the fragment text that slot pulled in. Sum of all cuts except REC-01 = 12,105 chars. REC-01 (pyvista) and REC-03 (trimesh) are MUTUALLY EXCLUSIVE at runtime — exactly one is spliced per session via {render_check_library_block} — so only one of the two counts toward any given assembled prompt; my arithmetic uses trimesh's 943. Both should still be applied.

The assembled prompt measures ~24,600 chars against a reported 5,004 tokens, i.e. ~4.9 chars/token here, not 4.0. Applying every cut leaves ~12,500 chars ≈ 2,550 tokens — inside the 1,000-3,000 target, ~49% off.

WHAT I DELIBERATELY DID NOT CUT.
- The 16-parameter list (owner's rule). REC-07 only reformats it: every name, unit and range survives, plus the derived-ring-height note and the middlePos span formula (0 = root at r = 4 mm, radius = 4 + middlePos·(R−4)). It ADDS one line stating that *Thickness/*Camber are % of that section's OWN chord — the real pinned-chord bug — which the Tool Caller currently never sees, because modelling_notes.md is not spliced into its prompt.
- The per-parameter range check (REC-09 keeps the "one by one, a glance is not a check" wording). That is the DCII blanket-approval incident's countermeasure and the Tool Caller is the last line of defence, so I compressed the justification and kept the mechanics.
- The "DCOI receives no images automatically" sentence (REC-15) and the three path labels, verbatim. Cutting those breaks the downstream inspector.
- The anti-hallucination bullet in generic_constraints ("DON'T fabricate observations about artifacts you did not see produced") — untouched, it is short and it is the fix for a real failure.
- The <<HAS_DBA>> region (lines 186-195 of prompt.md). It is stripped in the measured config (RAG_ENABLED=False) so it costs 0 tokens today, but it splices ~4.5k chars of database_search + retrieve_* fragments when RAG is on. Worth a separate audit before RAG is re-enabled.

THREE CUTS TOUCH agents/shared/routing.py, NOT A .md FILE. REC-05, REC-08, REC-11, REC-18 edit the string literals inside routing_instructions(). They are the single biggest lever in the fleet: 2,129 chars off EVERY chain agent (Planner, UII, DCIC, DCII, Tool Caller, DCOI) = ~13k chars ≈ 2,600 tokens fleet-wide. The quoted strings are Python source; the replacements are written as valid Python list entries with the f-string interpolation of {hub} and the _authorisation_sources(hub) call preserved, so topology 5 keeps working.

SHARED-FRAGMENT BLAST RADIUS (verified by grep across all prompt.md files):
- generic_constraints.md, hard_constraints_dc.md, hard_constraints_tools.md → 8 agents (7-agent system) + conductor/creator (5-agent).
- parameters.md → 7 agents + conductor/creator.
- blade_sections_visualizer.md → all 9 + conductor/creator.
- tool_inventory.md and routing_tool_caller.md → Tool Caller only.
- The 5-agent topology has NO override for any of these files, so every cut lands in both topologies.

INTERACTIONS TO WATCH WHEN APPLYING SELECTIVELY.
- REC-08 (delete routing.py's do-not-loop) assumes generic_constraints keeps its DON'T-loop bullet — I did not propose cutting it.
- REC-23 (delete the permission bullet from generic_constraints) assumes routing.py's permission section survives in compressed form (REC-11). Applying both deletions would leave chain agents with no permission-routing rule.
- REC-14 (Tool Caller "Limits") assumes REC-12 keeps the mesh-post-processing ban in hard_constraints_dc.
- REC-16 and REC-19 split one idea across two blocks: REC-19's replacement carries the "never a guessed path → ESCALATE" clause. Apply both, or keep exactly one copy.
- Four cuts sit next to conditional markers that MUST be preserved byte-for-byte or the region filter breaks and the marker text leaks into the prompt: REC-20 and REC-29 (<</CHAIN_ONLY>>), REC-23 and REC-26 (<<CHAIN_ONLY>>), REC-24 (<<BSV_ON>>/<</BSV_ON>>), REC-28 (<<DCII_ONLY>>/<<DCII_OFF>>). Note that DC_prompt_fragments/tools_config/blade_sections_visualizer_tool_caller.md is a ZERO-BYTE file, so $blade_sections_visualizer_per_agent contributes nothing today — nothing to cut there.

OUT OF SCOPE BUT WORTH A SEPARATE PASS (golden rule 9): the Tool Caller carries 2,201 tokens of tool schemas for 9 tools — 44% as much as the prompt itself, and more than the prompt will be after these cuts. Several prose blocks I compressed exist only to compensate for tool docstrings (the attempt-folder/output_dir contract, the reuse-in-place semantics, the return-text markers "Mesh saved …" / "Renders already present"). Moving those facts into the generate_and_render_propeller docstring would let REC-02 and REC-13 shrink further and would cut duplication across the DCOI too.

### 7.x DC Input Creator — second opinion (53 cuts → ~3,200 tok)

| action | section | −chars | risk | what |
|---|---|---:|---|---|
| COMPRESS | ## Real-world-quantity QUANTITATIVE INPUTS — strong sug | 1950 | low | Three routes plus an Avoid list plus a Multi-parameter subsection say the same three things at 4x length; the behaviour (route + justify + never silently drop) survives intact. |
| COMPRESS | ## Attempt folders + reusing history (read before writi | 1830 | low | The parenthetical splices the whole 1.7k-char $output_file_locations fragment just to name four filenames; inlining the filenames drops the fragment from this agent (the Receptionist keeps it). |
| COMPRESS | ## Routing — strict rules | 1152 | low | Two bulleted laundry lists with per-item justification collapse into two sentences; the load-bearing invariants (exactly N fields, rejected-call-wrote-nothing, missing-arg self-correction) are all kept. |
| REPLACE_WITH_EXAMPLES | ### Common unit-conversion patterns for this configurat | 1148 | low | Six prose bullets plus two hedging paragraphs restate arithmetic the model can do; one dense line of canonical conversions carries the same information. |
| COMPRESS | ## Validate before you write (HARD) | 1098 | medium | The three checks and the collision rule are load-bearing (a real blanket-approval failure), but the surrounding narration and the closing 'fix and re-check' restatement are not. |
| COMPRESS | ## Hand-off to the next agent (IMPORTANT) | 1057 | low | The three path lines and the required phrase are protocol and stay; the four paragraphs explaining why each path must be copied verbatim and why authorship matters to the DCII are justification. |
| COMPRESS | **Freeing a LOCKED value.** | 1038 | medium | Lettered source catalogue (A)(B)(C) — including (C), an explicitly obsolete inline annotation — compresses to one sentence with the same permissive semantics. |
| SCOPE_PER_AGENT | ## Hard constraints — generic (apply to every agent) | 860 | medium | The pasted 8-agent constitution scoped to the six rules the DCIC can actually violate; the saving is incremental on top of the generic_constraints compressions. |
| COMPRESS | routing_instructions() — Permission / authorisation iss | 823 | low | This block is spliced into all six chain agents and repeats the DON'T-bounce rule already in generic_constraints.md; the compressed form keeps the read-once-then-act behaviour and the grantor list. |
| COMPRESS | ## Acting on a Planner / Orchestrator qualitative direc | 795 | low | The two-option structure is the whole rule; the parenthetical taxonomy of problem kinds and the worked explanations of each option add no behaviour. |
| COMPRESS | The three states (LOCKED / SOFT TARGET / FREE) | 768 | low | Same three definitions with the explanatory asides ('neither locked nor free', the two worked strength examples) removed. |
| COMPRESS | routing_instructions() — How to decide where to route | 710 | low | Four narrated if-then sentences shared by six agents become one four-clause line; the semantics also live in the call_<agent> tool descriptions. |
| COMPRESS | **Writing each state.** | 680 | low | Keeps the three write behaviours and the escalate-don't-invent rule; drops the anti-anchoring lecture and the explanation of why bouncing to the UII wastes a round-trip. |
| COMPRESS | **Which folder to write into — you OWN attempt creation | 676 | low | Preserves the whole (A)/(B) decision and the one-attempt-per-generation invariant (a real ownership fix) at 40% of the length. |
| DELETE | ## End-of-session feedback message (read-only) | 674 | low | Describes a message the Orchestrator MAY append at session end — a mechanism the agent does not act on during the run, and reading feedback needs no instruction. |
| DELETE | routing_instructions() — Do not loop | 630 | low | Verbatim duplicate of the DON'T-loop bullet in generic_constraints.md, which every agent already gets. |
| COMPRESS | ### Domain hard rules (every agent) | 628 | low | Three exhaustive enumerations become three canonical examples plus an et-cetera; shared by all 8 agents so the saving multiplies. |
| COMPRESS | routing_instructions() — natural-flow position header | 624 | low | Position in the pipeline is a two-line fact; the surrounding narration is restated in the fragment and the tool descriptions. |
| COMPRESS | ### Tool-use hard rules (every agent) | 613 | low | Keeps the three real invariants (no guessed paths, always calculate, append-only) and drops the render-reuse and who-opens-the-folder asides that the DCIC prompt already states. |
| COMPRESS | **Tight precision loop — when a precision standing dire | 605 | medium | Hand-off routing policy narrated at length; the rule is one sentence and would be better still as orchestration state. |
| COMPRESS | ## Reading QUANTITATIVE INPUTS | 583 | low | A two-bullet taxonomy with forward references to two other sections says less than three sentences. |
| DELETE | routing_instructions() — Routing is a tool call — MANDA | 542 | medium | Duplicates the generic_constraints DON'T-emit-prose rule; the ---ROUTING--- template ban is a patch for a format retired long ago. |
| COMPRESS | **Under a precision standing directive (blade-section m | 529 | medium | Same lever set and same locked/soft distinction, without the restatement of Guidelines item 3 and the parenthetical cross-references. |
| DELETE | DCII redundancy note under Validate before you write | 499 | low | Pure justification for why the DCIC's own check exists; the HARD check above stands on its own and this changes no behaviour. |
| COMPRESS | ## Read + write tools — policy (mechanics are in each t | 441 | low | The skip-conditions and the append-only re-explanation duplicate the Attempt-folders section and each tool's own schema. |
| COMPRESS | ## Guidelines | 437 | low | Five numbered items with an embedded three-sentence aside become three; the warm-start rule and the in-range rule are preserved. |
| COMPRESS | routing_instructions() — Do NOT describe or announce | 435 | low | Four negations of the same behaviour, already stated twice above in the same block. |
| COMPRESS | ### Blade-sections visualizer | 430 | low | Spliced into all 9 prompts; the geometric description of the image and the 'shown to the user' aside change no agent's behaviour. |
| COMPRESS | Full-3D directive paragraph | 428 | low | Keeps the widening rule (the antidote to the subset-enumeration bug) and the escalate-don't-touch rule; drops the restated SOFT-TARGET reminder. |
| COMPRESS | whole fragment | 416 | low | The middlePos formula appears three times in this prompt (structure, parameters.md, modelling_notes); keep it once, in the parameter list. |
| COMPRESS | DON'T communicate to another agent in plain prose | 416 | medium | This is the single surviving statement of the routing mandate (REC-21 deletes the routing.py duplicate); it keeps the halt consequence and drops the exception list irrelevant to chain agents. |
| DELETE | DO follow the natural pipeline / DO ESCALATE (CHAIN_ONL | 397 | low | Restates the FORWARD / ESCALATE rules that routing_instructions() already builds into the same prompt (REC-11 keeps the compact version). |
| SCOPE_PER_AGENT | ## Hard constraints — tool-specific | 390 | low | The DCIC needs three of the shared bullets; the render-reuse and who-opens-a-folder clauses are Tool-Caller / Orchestrator concerns already covered by this prompt's own Attempt-folders section. |
| COMPRESS | routing_instructions() — free-form prose paragraph | 363 | low | Says the same thing as the generic_constraints hand-off bullet; compressing here lets REC-34 delete that one. |
| SCOPE_PER_AGENT | ## Hard constraints — DC-specific | 360 | low | The DCIC writes parameters; it never proposes renders, formats, camera angles or analyses to the user, so only the no-invented-parameters rule is in scope. |
| DELETE | ## Filtering responsibility | 340 | low | Role justification only; the actionable part ('when you skip, say so') is already the Decline bullet in Real-world quantities. |
| DELETE | DO write hand-off messages as free-form prose | 322 | low | Duplicate of the routing.py free-form-prose paragraph kept in REC-33; keep exactly one. |
| COMPRESS | **If you discover a real error AFTER writing** | 317 | low | Keeps the rule and the no-op ban cross-reference; drops the reassurance that this should be rare and the record-keeping rationale. |
| COMPRESS | DO carry STANDING DIRECTIVES verbatim | 310 | medium | The verbatim-copy rule is one clause; the five synonyms for 'don't change it' and the why-clause are padding. |
| SCOPE_PER_AGENT | <<BSV_ON>> blade-sections splice | 310 | low | The DCIC never calls the tool; its per-agent overlay ($blade_sections_visualizer_per_agent, kept) already tells it the one thing it must do — say so in the hand-off to the Tool Caller. |
| COMPRESS | middlePos definition bullet | 280 | medium | Third statement of the same formula in one assembled prompt; the NOT-clause (the real gotcha) is preserved. |
| COMPRESS | ### Hard engineering blockers | 264 | low | A one-item list wrapped in a heading, a preamble and a moral; the single blocker is all the content. |
| DELETE | DON'T bounce permission questions back | 249 | low | Duplicated in full by the routing.py permission section retained in compressed form (REC-08). |
| COMPRESS | **Forbidden: a no-op write.** | 206 | low | Keeps the ban and the check; drops the 'you are stateful' framing and the consequence sentence. |
| COMPRESS | whole fragment | 205 | low | DCIC-only overlay; the mechanism explanation belongs to the Tool Caller's overlay. |
| DELETE | DON'T script the final user-facing reply | 188 | medium | An incident patch aimed at agents that talk about user wording; the DCIC's output is a JSON file plus a hand-off, and the Receptionist's ownership of user text is stated in its own prompt. |
| DELETE | **Carry ``Current attempt:`` forward** | 187 | low | The Hand-off section already mandates the three path lines on every FORWARD, including ``Current attempt:``. |
| COMPRESS | ## Re-reading raw inputs (optional) | 183 | low | Tool mechanics live in the schemas; the only steering content is 'you cannot see images'. |
| DELETE | CLARIFY / ESCALATE path-lines note | 169 | low | Permission not to do something optional; the Hand-off section already scopes the three lines to FORWARDs. |
| COMPRESS | *Thickness / *Camber ratio note | 167 | medium | Keeps the whole gotcha (a real bug source) and the disambiguation duty in half the words. |
| COMPRESS | **Reuse the session's history.** | 151 | low | Same instruction, minus the explanation of who benefits. |
| COMPRESS | ## Output Format | 125 | low | Two sentences into one; the don't-repeat-the-JSON rule (a real token sink) is kept. |
| COMPRESS | DON'T fabricate observations | 87 | medium | The general principle already covers the render-hallucination incident; the two-clause build-up is redundant. |

<details><summary><b>Full text of each second-opinion change</b></summary>

#### REC-02 · COMPRESS · −1950 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Real-world-quantity QUANTITATIVE INPUTS — strong suggestion + judgement

**Why:** Three routes plus an Avoid list plus a Multi-parameter subsection say the same three things at 4x length; the behaviour (route + justify + never silently drop) survives intact.

**Cut from** `## Real-world-quantity QUANTITATIVE INPUTS — strong suggestion + judgement`

**...through** `do so deliberately and say so.`

**Replace with:**

```
## Real-world quantities
When QUANTITATIVE INPUTS gives a quantity in a unit or frame the configurator does not store, honour it as closely as practical and say in your hand-off which route you took:
  * **Convert** — pick the anchor parameter(s) that set the reference frame, solve with ``calculate``, check the result is in range; state the quantity, the anchors, the formula and the result.
  * **Judge** — when a literal conversion would be non-physical, near-boundary or ambiguous, choose values that honour the intent and say why.
  * **Decline** — entries that do not map at all (a motor RPM, a cost, a date): skip them with a one-line reason.
Never silently drop an input you could act on, and never leave an anchor mid-range when moving a free anchor would honour the user's number.  If several parameters could carry the value, either put it on the most plausible one or distribute it so the family COLLECTIVELY matches — say which; never copy the same number into every candidate.
```

#### REC-03 · COMPRESS · −1830 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Attempt folders + reusing history (read before writing)

**Why:** The parenthetical splices the whole 1.7k-char $output_file_locations fragment just to name four filenames; inlining the filenames drops the fragment from this agent (the Receptionist keeps it).

**Cut from** `## Attempt folders + reusing history (read before writing)`

**...through** `(including you) overwrites them; existing renders are reused in place.`

**Replace with:**

```
## Attempt folders
Every generation cycle is anchored on one folder under ``logs/attempts/`` holding that cycle's ``parameters.json``, ``propeller_mesh.obj`` and ``render_isometric|top|side.png``.  ``parameters.json`` and the mesh are append-only — never overwritten; existing renders are reused in place.
```

#### REC-04 · COMPRESS · −1152 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Routing — strict rules

**Why:** Two bulleted laundry lists with per-item justification collapse into two sentences; the load-bearing invariants (exactly N fields, rejected-call-wrote-nothing, missing-arg self-correction) are all kept.

**Cut from** `## Routing — strict rules`

**...through** `keys and do NOT invent fields — ESCALATE with a clear note.`

**Replace with:**

```
## What you can and cannot fix
If the next agent CLARIFYs back you can fix what you authored: an out-of-range value, an arithmetic slip, or a field ``write_parameters`` REJECTED (a rejected call wrote nothing — re-call on the SAME folder).  Once a file exists that folder is closed, so any other correction is a fresh ``new_attempt``.  A tool error naming a missing argument means YOUR call omitted it — re-issue the same call with it; it is never a schema bug.
ESCALATE instead when asked about design intent, whether a choice was intentional, whether a user's value is a good idea, anything absent from ``extracted_inputs.txt`` / ``user_query.txt``, or to write parameters outside the $parameter_count-name list — those do not exist and ``parameters.json`` must contain exactly those $parameter_count fields.
```

#### REC-01 · REPLACE_WITH_EXAMPLES · −1148 chars · risk low

*File:* `DC_prompt_fragments/dc_config/modelling_notes.md` · *Section:* ### Common unit-conversion patterns for this configurator

**Why:** Six prose bullets plus two hedging paragraphs restate arithmetic the model can do; one dense line of canonical conversions carries the same information.

**Cut from** `### Common unit-conversion patterns for this configurator`

**...through** `algebra, OR fall back to engineering judgement with a stated
rationale.`

**Replace with:**

```
### Common unit conversions
Thickness / camber in mm <-> % of that section's OWN chord; highpoint in mm <-> integer tenths of chord; a radial distance <-> ``middlePos = (r - 4)/(impellerRadius - 4)``; a diameter <-> ``impellerRadius = diameter/2``; an absolute mm value stated as a fraction of an overall dimension <-> multiply by that scale.  For anything else, derive the conversion from the parameter list plus unit algebra, or fall back to judgement with a stated rationale.
```

#### REC-05 · COMPRESS · −1098 chars · risk medium

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Validate before you write (HARD)

**Why:** The three checks and the collision rule are load-bearing (a real blanket-approval failure), but the surrounding narration and the closing 'fix and re-check' restatement are not.

**Risk:** Item 1's per-parameter (not blanket) wording is the patch for the blanket-approval bug — it is preserved verbatim in the replacement; do not shorten it further.

**Cut from** `## Validate before you write (HARD)`

**...through** `ESCALATE — do not write a set you know to be
wrong.`

**Replace with:**

```
## Validate before you write (HARD)
Check your DRAFT before opening an attempt or calling ``write_parameters``:
  1. **Each value against its own [min; max], one by one** — not a blanket "all $parameter_count are in bounds".  Outside the range fails; exactly at min or max is fine.
  2. **The hard blockers** in ``## Modelling Notes`` — compute with ``calculate``, batched with your other arithmetic.
  3. **Every user value you moved needs an authorisation** — its state, a permission in the hand-off or DESIGN INTENT, or a directive.  If nothing authorised it, restore the user's number.
If 1 and 3 collide (a LOCKED value is out of range), bring it into range only if something authorises the move, and say so; otherwise write nothing, open no attempt, and ESCALATE naming the parameter, its value and its range.
```

#### REC-06 · COMPRESS · −1057 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Hand-off to the next agent (IMPORTANT)

**Why:** The three path lines and the required phrase are protocol and stay; the four paragraphs explaining why each path must be copied verbatim and why authorship matters to the DCII are justification.

**Cut from** `## Hand-off to the next agent (IMPORTANT)`

**...through** `normally, but name the source.`

**Replace with:**

```
## Hand-off
Every FORWARD's ``message`` must carry these three lines with absolute paths:

    Current attempt: <folder you wrote into>
    Parameters file (newly written this cycle): <Current attempt>/parameters.json
    Extracted inputs file: <same path the UII gave you>

``(newly written this cycle)`` is required — it marks that file as this cycle's authoritative set.  Copy each path verbatim from the tool result or hand-off that produced it.  Beyond the three lines, say in your own words anything the next agent needs — above all, any value that did NOT come from the user's extraction: what changed, who asked for it, and why.
```

#### REC-07 · COMPRESS · −1038 chars · risk medium

*File:* `agents/shared/prompt_fragments/value_states.md` · *Section:* **Freeing a LOCKED value.**

**Why:** Lettered source catalogue (A)(B)(C) — including (C), an explicitly obsolete inline annotation — compresses to one sentence with the same permissive semantics.

**Risk:** Shared by DCIC, DCII, DCOI and Planner. Dropping clause (C) means an OLD extraction carrying '(unlocked by user)' inline would no longer be named as an authorisation source; the 'ANY ONE of these' framing still permits acting on it.

**Cut from** `**Freeing a LOCKED value.**  A LOCKED value may change only with an`

**...through** `= as far as the goal requires,
bounded by range.`

**Replace with:**

```
**Freeing a LOCKED value.**  ANY ONE of these authorises a change: the incoming hand-off (a user permission — blanket, scoped, or parameter-specific — a strategy / recovery directive, or a CLARIFY bounce), or the extraction's DESIGN INTENT section.  One source is enough — never demand re-confirmation of an authorisation the hand-off already carries, and treat a line saying "user-locked" as only the default lock.  How far it may move follows the wording: "as needed / only if necessary" = the smallest change that restores viability; "freely" or nothing said = as far as the goal requires, within range.
```

#### REC-53 · SCOPE_PER_AGENT · −860 chars · risk medium

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Hard constraints — generic (apply to every agent)

**Why:** The pasted 8-agent constitution scoped to the six rules the DCIC can actually violate; the saving is incremental on top of the generic_constraints compressions.

**Risk:** Deepest cut in the list and mutually exclusive in effect with REC-30/31/36/38/42/45/52 for THIS agent (those still pay off for the other 7). Apply this one only if you are willing to let the DCIC's constitution diverge from the shared file.

**Cut from** `## Hard constraints — generic (apply to every agent)`

**...through** `$hard_constraints_generic`

**Replace with:**

```
## Hard constraints
- Act on the paths your hand-off gives you, using only your bound tools; if you cannot do something with them, ESCALATE.
- DON'T invent tools, files, policies or confidence scores, and DON'T state an observation you cannot source to a tool result, history, or the user's own words.
- DON'T loop: if you are about to repeat a call with the same arguments, STOP and ESCALATE.
- Reproduce any ``=== STANDING DIRECTIVES … ===`` block from your hand-off UNCHANGED.
- DON'T emit prose to another agent.  The ONLY channel is a routing tool call (``call_<agent>``) and the prose in its ``message`` argument IS the hand-off; text emitted WITHOUT one is discarded and the pipeline halts.
- Answer in English.
```

#### REC-08 · COMPRESS · −823 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — Permission / authorisation issues

**Why:** This block is spliced into all six chain agents and repeats the DON'T-bounce rule already in generic_constraints.md; the compressed form keeps the read-once-then-act behaviour and the grantor list.

**Cut from** `f"### Permission / authorisation issues → {hub} (not "`

**...through** `"NOT for permission questions.",`

**Replace with:**

```
        f"### Permission questions go to the {hub}",
        "Before escalating, re-read the hand-off (and any file it points "
        "to) once: if it already names an authorisation that plausibly "
        "covers the action, act on it.  If none exists, ESCALATE to the "
        f"{hub} — " + _authorisation_sources(hub) + "  CLARIFY back to the "
        "previous agent only for data / wording / format issues it can fix.",
```

#### REC-09 · COMPRESS · −795 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Acting on a Planner / Orchestrator qualitative directive (HARD)

**Why:** The two-option structure is the whole rule; the parenthetical taxonomy of problem kinds and the worked explanations of each option add no behaviour.

**Cut from** `## Acting on a Planner / Orchestrator qualitative directive (HARD)`

**...through** `which parameters you would have wanted to change and exactly
     why you cannot.`

**Replace with:**

```
## Acting on a qualitative directive (HARD)
A recovery directive names a problem, not a parameter.  Either **act** — pick unlocked parameters, move them in a sensible direction, and name in your hand-off each parameter, its before→after values and a one-line reason — or **ESCALATE** to the Orchestrator when no unlocked parameter can move (all locked with no authorisation, or you already exhausted the plausible directions), listing the parameters you would have changed and why you cannot.
```

#### REC-10 · COMPRESS · −768 chars · risk low

*File:* `agents/shared/prompt_fragments/value_states.md` · *Section:* The three states (LOCKED / SOFT TARGET / FREE)

**Why:** Same three definitions with the explanatory asides ('neither locked nor free', the two worked strength examples) removed.

**Cut from** `- **LOCKED** — a value the user stated plainly there, with no marker.  The`

**...through** `as LOCKED for that cycle.`

**Replace with:**

```
- **LOCKED** — stated plainly with no marker: the user fixed it.  It may still change if an authorisation frees it (below).
- **SOFT TARGET** — marked ``SOFT TARGET (goal: …; keep near … if free)``.  The goal governs: the marker IS the authorisation to move the value within range as far as the goal requires, with no justification needed.  The stated number settles the parameter only where the goal does not bear on it, as closely as the "keep near …" wording asks.
- **FREE** — absent from QUANTITATIVE INPUTS (never given, or released): the system's choice within range.  A qualitative description you must turn into a number is FREE too, unless a directive pins it.
```

#### REC-11 · COMPRESS · −710 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — How to decide where to route

**Why:** Four narrated if-then sentences shared by six agents become one four-clause line; the semantics also live in the call_<agent> tool descriptions.

**Cut from** `"### How to decide where to route",`

**...through** `"can fix it, route to the {hub} (ESCALATE).",`

**Replace with:**

```
        "### Where to route",
        f"Work succeeded and the {hub} did not ask you to report back → "
        f"FORWARD.  Asked to report back → the {hub}.  Upstream message "
        "ambiguous / missing data the previous agent can fix → CLARIFY "
        f"back.  Nothing in the chain can fix it → {hub} (ESCALATE).",
```

#### REC-12 · COMPRESS · −680 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* **Writing each state.**

**Why:** Keeps the three write behaviours and the escalate-don't-invent rule; drops the anti-anchoring lecture and the explanation of why bouncing to the UII wastes a round-trip.

**Cut from** `**Writing each state.**  Write a LOCKED value **verbatim** — do NOT round,`

**...through** `wastes a round-trip); never invent an authorisation.`

**Replace with:**

```
**Writing each state.**  Write a LOCKED value verbatim — never round or "improve" it.  Set a SOFT TARGET to whatever its goal calls for, within range, from the first attempt on.  Set a FREE value at your discretion within range.  An authorisation may arrive from the Orchestrator, the Planner via the Orchestrator, the UII, or a CLARIFY bounce — act on it once, and never invent one.  If a LOCKED value must change for viability and none exists, keep it and ESCALATE to the Orchestrator.
```

#### REC-13 · COMPRESS · −676 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* **Which folder to write into — you OWN attempt creation.**

**Why:** Preserves the whole (A)/(B) decision and the one-attempt-per-generation invariant (a real ownership fix) at 40% of the length.

**Cut from** `**Which folder to write into — you OWN attempt creation.**  Open the folder`

**...through** `guess a path around the refusal, and never write outside an attempt
folder.`

**Replace with:**

```
**Which folder.**  Open it only after the draft passes the checks above.  If the hand-off carries ``Current attempt: <path>`` (a rare pre-opened fallback) write there; otherwise call ``new_attempt`` ONCE (short slug + one-line intent) and write into the path it returns.  Exactly one attempt per generation, always written into — an attempt with no ``parameters.json`` is a dead folder.  If ``write_parameters`` refuses an occupied folder, open one fresh attempt and write there; never guess a path around the refusal.
```

#### REC-14 · DELETE · −674 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## End-of-session feedback message (read-only)

**Why:** Describes a message the Orchestrator MAY append at session end — a mechanism the agent does not act on during the run, and reading feedback needs no instruction.

**Cut from** `## End-of-session feedback message (read-only)`

**...through** `$eos_feedback_outro`

**Replace with:** *(nothing — pure deletion)*

#### REC-15 · DELETE · −630 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — Do not loop

**Why:** Verbatim duplicate of the DON'T-loop bullet in generic_constraints.md, which every agent already gets.

**Risk:** Only safe while generic_constraints.md keeps its 'DON'T loop: same tool, same arguments → STOP and ESCALATE' bullet (REC-51 keeps it).

**Cut from** `"### Do not loop — ESCALATE when stuck",`

**...through** `"consult another agent, or ask the user.  Never silently loop.",`

**Replace with:** *(nothing — pure deletion)*

#### REC-16 · COMPRESS · −628 chars · risk low

*File:* `DC_prompt_fragments/dc_config/hard_constraints_dc.md` · *Section:* ### Domain hard rules (every agent)

**Why:** Three exhaustive enumerations become three canonical examples plus an et-cetera; shared by all 8 agents so the saving multiplies.

**Cut from** `### Domain hard rules (every agent)`

**...through** `rely on visual
  inspection and say so plainly.`

**Replace with:**

```
### Domain hard rules (every agent)
- Express a design ONLY in the $parameter_count named parameters; anything else (hub_radius, fillet_radius, tip_clearance, …) does not exist — reject it.  Geometry changes only by changing those parameters and regenerating; there is no mesh editing and no post-processing of any kind (booleans, welding, remeshing, fillets, supports, …).
- DON'T offer what the system cannot do: performance or structural analysis, other formats (STL, STEP, …), extra camera angles, or higher-resolution renders.  The only mesh metrics are watertightness, volume and degenerate-face count.
```

#### REC-17 · COMPRESS · −624 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — natural-flow position header

**Why:** Position in the pipeline is a two-line fact; the surrounding narration is restated in the fragment and the tool descriptions.

**Risk:** This is a code edit, not a prose edit — the replacement changes list-building structure, so apply it as a whole block.

**Cut from** `"You are one agent in a decentralised pipeline.  The natural "`

**...through** `f"to go 'back', that means handing control to the {hub}."`

**Replace with:**

```
        f"Pipeline: {natural_pipeline()}",
        f"You are the **{agent_name}**.",
    ]
    lines.append(
        f"- Next: **{next_agent}**." if next_agent
        else f"- You are last; finishing normally hands back to the {hub}."
    )
    lines.append(
        f"- Previous: **{prev_agent}**." if prev_agent
        else f"- You are first; going 'back' means the {hub}."
```

#### REC-18 · COMPRESS · −613 chars · risk low

*File:* `DC_prompt_fragments/tools_config/hard_constraints_tools.md` · *Section:* ### Tool-use hard rules (every agent)

**Why:** Keeps the three real invariants (no guessed paths, always calculate, append-only) and drops the render-reuse and who-opens-the-folder asides that the DCIC prompt already states.

**Cut from** `### Tool-use hard rules (every agent)`

**...through** `DCIC opens it; the Orchestrator only as a fallback) — never edit the old
  folder's parameters.`

**Replace with:**

```
### Tool-use hard rules (every agent)
- Read tools take only the paths a hand-off label gives (``Input directory:`` / ``Extracted inputs file:`` / ``Parameters file:`` / ``Current attempt:``) or a tool's return value — never a guessed path.
- Route EVERY arithmetic operation — sums, ratios, conversions, range comparisons — through ``calculate``; never mental arithmetic.  Batch the whole turn's expressions into ONE call.
- Attempt folders are append-only: never edit or delete a ``parameters.json`` or mesh already written, and to build on an old set copy its values into a NEW attempt.
```

#### REC-19 · COMPRESS · −605 chars · risk medium

*File:* `agents/dc_input_creator/prompt.md` · *Section:* **Tight precision loop — when a precision standing directive is active.**

**Why:** Hand-off routing policy narrated at length; the rule is one sentence and would be better still as orchestration state.

**Risk:** The 'every third round + last round' cadence is the only statement of it; keep that clause verbatim if trimming further.

**Cut from** `<<DCII_ONLY>>**Tight precision loop — when a precision standing directive is active.**`

**...through** ```Extracted inputs file:`` lines.
<</DCII_ONLY>>`

**Replace with:**

```
<<DCII_ONLY>>**Precision refine rounds** may FORWARD straight to the Tool Caller (``call_tool_caller``) to keep the loop tight; route through the DC Input Inspector periodically (about every third round) and on the last round before the DCOI finalizes.  Outside a precision job, always take your normal forward.<</DCII_ONLY>>
```

#### REC-20 · COMPRESS · −583 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Reading QUANTITATIVE INPUTS

**Why:** A two-bullet taxonomy with forward references to two other sections says less than three sentences.

**Cut from** `## Reading QUANTITATIVE INPUTS`

**...through** `for how to handle them.`

**Replace with:**

```
## QUANTITATIVE INPUTS
The UII records every number the user supplied.  A line whose label and unit match a parameter maps straight into that cell — its state decides whether you may move it.  A line in any other unit or frame is real design intent with no single cell; see "Real-world quantities".
```

#### REC-21 · DELETE · −542 chars · risk medium

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — Routing is a tool call — MANDATORY

**Why:** Duplicates the generic_constraints DON'T-emit-prose rule; the ---ROUTING--- template ban is a patch for a format retired long ago.

**Risk:** This mandate is the fix for the 'agent emitted prose and the pipeline halted' failure. Safe ONLY if generic_constraints keeps the compressed version in REC-31, which states the same invariant including the halt consequence.

**Cut from** `"### Routing is a tool call — MANDATORY",`

**...through** `"decision; its ``message`` argument is the hand-off.",`

**Replace with:** *(nothing — pure deletion)*

#### REC-23 · COMPRESS · −529 chars · risk medium

*File:* `agents/dc_input_creator/prompt.md` · *Section:* **Under a precision standing directive (blade-section matching):**

**Why:** Same lever set and same locked/soft distinction, without the restatement of Guidelines item 3 and the parenthetical cross-references.

**Risk:** This paragraph enumerates a SUBSET of movable parameters — exactly the pattern that once silently revoked a chord authorisation. The replacement keeps 'SOFT TARGET counts as unlocked' and REC-25 keeps the widening rule; do not apply REC-25 as a pure delete.

**Cut from** `**Under a precision standing directive (blade-section matching):** the`

**...through** `Every
round is a fresh generation — a new attempt.`

**Replace with:**

```
**Under a precision (blade-section) directive** the problem statement is the DCOI's shape-gap description.  Move only the UNLOCKED shape levers — ``*Thickness``, ``*Camber``, ``*MaxPos`` and the section angles, with a ``SOFT TARGET`` counting as unlocked — in the direction described, leaving locked user numbers untouched.  Seed the first attempt from any ``SUGGESTED SECTION SHAPES`` block, then nudge toward the newest feedback each round; every round is a fresh attempt.
```

#### REC-22 · DELETE · −499 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* DCII redundancy note under Validate before you write

**Why:** Pure justification for why the DCIC's own check exists; the HARD check above stands on its own and this changes no behaviour.

**Cut from** `<<DCII_ONLY>>The DC Input Inspector independently re-checks EVERYTHING you`

**...through** `yours is then the only
parameter validation there is.<</DCII_ONLY>>`

**Replace with:** *(nothing — pure deletion)*

#### REC-24 · COMPRESS · −441 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Read + write tools — policy (mechanics are in each tool's schema)

**Why:** The skip-conditions and the append-only re-explanation duplicate the Attempt-folders section and each tool's own schema.

**Cut from** `## Read + write tools — policy (mechanics are in each tool's schema)`

**...through** ```attempt_dir`` is the folder from "Attempt folders" above.`

**Replace with:**

```
## Read / write tools
**``read_extracted_inputs(path)``** — re-read when in doubt: on your first turn, whenever the hand-off suggests new inputs, or when unsure your memory is current.  Path verbatim.
**``write_parameters(parameters, attempt_dir)``** — exactly ONE successful write per cycle.  An error means nothing was written: fix what it names and re-call on the SAME folder.
```

#### REC-26 · COMPRESS · −437 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Guidelines

**Why:** Five numbered items with an embedded three-sentence aside become three; the warm-start rule and the in-range rule are preserved.

**Cut from** `## Guidelines
1. Use quantitative values directly from user input where available.`

**...through** `defaults and translating qualitative descriptions.`

**Replace with:**

```
## Guidelines
1. Take the user's quantitative values directly; turn qualitative wording into numbers with engineering judgement inside the allowed ranges, serving the stated design intent:
$qualitative_examples
2. For a parameter the user never mentioned, pick a sensible mid-range default — except that when QUALITATIVE DESCRIPTIONS carries a ``SUGGESTED SECTION SHAPES`` block (the UII's reading of a section drawing), seed ``*Thickness`` / ``*Camber`` / ``*MaxPos`` from it, clamped to range.  Those seeds are a starting point, not user-locked.
3. Every value must be in range.
```

#### REC-27 · COMPRESS · −435 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — Do NOT describe or announce

**Why:** Four negations of the same behaviour, already stated twice above in the same block.

**Cut from** `"Do NOT describe or announce which tool you intend to call.  Do "`

**...through** `"(one or two lines is plenty).",`

**Replace with:**

```
        "Invoke the routing tool in the same response where you finish "
        "your work — do not announce it or defer it to the next turn.  "
        "Only the tool's ``message`` argument reaches the recipient; keep "
        "any other reasoning text to a line or two.",
```

#### REC-28 · COMPRESS · −430 chars · risk low

*File:* `DC_prompt_fragments/tools_config/blade_sections_visualizer.md` · *Section:* ### Blade-sections visualizer

**Why:** Spliced into all 9 prompts; the geometric description of the image and the 'shown to the user' aside change no agent's behaviour.

**Cut from** `### Blade-sections visualizer`

**...through** `and can even be the final
deliverable.`

**Replace with:**

```
### Blade-sections visualizer
The Tool Caller can render just the three blade cross-sections (``render_blade_sections``) from an attempt's parameters file, skipping the 3D mesh.  It is much faster, so a sections-centred request can be rendered and refined on its own — and can be the final deliverable.
```

#### REC-25 · COMPRESS · −428 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* Full-3D directive paragraph

**Why:** Keeps the widening rule (the antidote to the subset-enumeration bug) and the escalate-don't-touch rule; drops the restated SOFT-TARGET reminder.

**Cut from** `When the directive instead targets the FULL 3D (matching a top / side sketch of`

**...through** `so the DCOI reports the limit honestly.`

**Replace with:**

```
When the directive targets the FULL 3D shape instead, the lever set WIDENS to any UNLOCKED parameter that moves the aspect the DCOI named (``middlePos``, a chord, an angle, the ring) — again leaving locked numbers untouched.  If every helpful lever is locked, ESCALATE naming them rather than touching one.
```

#### REC-29 · COMPRESS · −416 chars · risk low

*File:* `DC_prompt_fragments/dc_config/structure.md` · *Section:* whole fragment

**Why:** The middlePos formula appears three times in this prompt (structure, parameters.md, modelling_notes); keep it once, in the parameter list.

**Cut from** `The propeller consists of:`

**...through** `at the outer radius (impellerRadius), furthest from the centre.`

**Replace with:**

```
The propeller: a central hub of FIXED radius 4 mm (the blade root); an outer ring (radius + wall thickness; its height is derived); and blades spanning hub→ring in three radial sections — inner (at the hub), middle (at ``middlePos``, a fraction of the blade span, not necessarily the midpoint) and outer (the tip, at ``impellerRadius``).
```

#### REC-30 · COMPRESS · −416 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DON'T communicate to another agent in plain prose

**Why:** This is the single surviving statement of the routing mandate (REC-21 deletes the routing.py duplicate); it keeps the halt consequence and drops the exception list irrelevant to chain agents.

**Risk:** Load-bearing: prevents the 'prose without a routing tool call halts the pipeline' failure. Do not delete; only compress as written.

**Cut from** `- DON'T communicate to another agent in plain prose.  The ONLY channel`

**...through** `only exceptions are the Receptionist's direct user replies and the
Orchestrator's final user-facing wrap-up.`

**Replace with:**

```
- DON'T emit prose to another agent.  The ONLY channel is a routing tool call (``call_<agent>``) and the prose in its ``message`` argument IS the hand-off.  Text emitted WITHOUT a routing call is discarded and the pipeline halts — invoke the tool in the same response where you finish your work.
```

#### REC-31 · DELETE · −397 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DO follow the natural pipeline / DO ESCALATE (CHAIN_ONLY)

**Why:** Restates the FORWARD / ESCALATE rules that routing_instructions() already builds into the same prompt (REC-11 keeps the compact version).

**Cut from** `<<CHAIN_ONLY>>- DO follow the natural pipeline: when your work succeeds and the`

**...through** `request, still-ambiguous hand-off after one CLARIFY).`

**Replace with:**

```
<<CHAIN_ONLY>>
```

#### REC-32 · SCOPE_PER_AGENT · −390 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Hard constraints — tool-specific

**Why:** The DCIC needs three of the shared bullets; the render-reuse and who-opens-a-folder clauses are Tool-Caller / Orchestrator concerns already covered by this prompt's own Attempt-folders section.

**Risk:** Saving is incremental on top of REC-18 (which still benefits the other 7 agents).

**Cut from** `## Hard constraints — tool-specific`

**...through** `$hard_constraints_tools`

**Replace with:**

```
## Hard constraints — tools
- Use only paths a hand-off label or a tool return gave you; never guess one.
- Route EVERY arithmetic operation through ``calculate``, batched into one call per turn.
- Attempt folders are append-only: never edit or delete a written ``parameters.json``.
```

#### REC-33 · COMPRESS · −363 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — free-form prose paragraph

**Why:** Says the same thing as the generic_constraints hand-off bullet; compressing here lets REC-34 delete that one.

**Cut from** `"Write the ``message`` argument as free-form prose: no fixed "`

**...through** `"do not duplicate it inside the ``message`` argument.",`

**Replace with:**

```
        "Write the ``message`` as free-form prose — no template, no "
        "option menus — carrying exactly what the recipient needs "
        "(required paths, what changed and why, the authorship of any "
        "non-user value) and nothing more.",
```

#### REC-34 · SCOPE_PER_AGENT · −360 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Hard constraints — DC-specific

**Why:** The DCIC writes parameters; it never proposes renders, formats, camera angles or analyses to the user, so only the no-invented-parameters rule is in scope.

**Risk:** Incremental on top of REC-16. The 'do not offer CFD / STL / extra views' rules remain where they matter (Receptionist, Planner, DCOI).

**Cut from** `## Hard constraints — DC-specific`

**...through** `$hard_constraints_dc`

**Replace with:**

```
## Hard constraints — DC
- Express the design ONLY in the $parameter_count named parameters; anything else (hub_radius, fillet_radius, tip_clearance, …) does not exist.  Geometry changes only through those parameters — there is no mesh editing or post-processing.
```

#### REC-35 · DELETE · −340 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Filtering responsibility

**Why:** Role justification only; the actionable part ('when you skip, say so') is already the Decline bullet in Real-world quantities.

**Cut from** `## Filtering responsibility`

**...through** `off<<DCII_ONLY>> so the DCII can audit the decision<</DCII_ONLY>>.`

**Replace with:** *(nothing — pure deletion)*

#### REC-36 · DELETE · −322 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DO write hand-off messages as free-form prose

**Why:** Duplicate of the routing.py free-form-prose paragraph kept in REC-33; keep exactly one.

**Risk:** Preserve the leading '<</CHAIN_ONLY>>' marker on that line — cut only from '- DO write'.

**Cut from** `- DO write hand-off messages as free-form prose carrying exactly what`

**...through** `— and nothing more.`

**Replace with:** *(nothing — pure deletion)*

#### REC-37 · COMPRESS · −317 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* **If you discover a real error AFTER writing**

**Why:** Keeps the rule and the no-op ban cross-reference; drops the reassurance that this should be rare and the record-keeping rationale.

**Cut from** `**If you discover a real error AFTER writing**, that correction is a NEW`

**...through** `once and it persists, ESCALATE instead of trying again.`

**Replace with:**

```
**A correction after a write is a NEW generation** — open a fresh ``new_attempt`` and write the corrected (genuinely different) set there; if the same problem survives one correction, ESCALATE.
```

#### REC-38 · COMPRESS · −310 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DO carry STANDING DIRECTIVES verbatim

**Why:** The verbatim-copy rule is one clause; the five synonyms for 'don't change it' and the why-clause are padding.

**Risk:** Standing directives carry the precision-matching instructions across the chain; the replacement keeps UNCHANGED and the Planner-only ownership.

**Cut from** `- DO carry STANDING DIRECTIVES verbatim: if your incoming hand-off`

**...through** `it carries instructions later agents depend on, and only the Planner may
  set or change it.`

**Replace with:**

```
- DO reproduce any ``=== STANDING DIRECTIVES … ===`` block from your hand-off UNCHANGED in your outgoing one; only the Planner may alter it.
```

#### REC-39 · SCOPE_PER_AGENT · −310 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* <<BSV_ON>> blade-sections splice

**Why:** The DCIC never calls the tool; its per-agent overlay ($blade_sections_visualizer_per_agent, kept) already tells it the one thing it must do — say so in the hand-off to the Tool Caller.

**Cut from** `<<BSV_ON>>
$blade_sections_visualizer`

**...through** `<<BSV_ON>>
$blade_sections_visualizer`

**Replace with:**

```
<<BSV_ON>>
```

#### REC-40 · COMPRESS · −280 chars · risk medium

*File:* `DC_prompt_fragments/dc_config/modelling_notes.md` · *Section:* middlePos definition bullet

**Why:** Third statement of the same formula in one assembled prompt; the NOT-clause (the real gotcha) is preserved.

**Risk:** The from-centre misreading was a real bug. The corrective 'NOT middlePos × impellerRadius' clause must survive — it does, here and in parameters.md.

**Cut from** `- ``middlePos`` (the middle section's radial position) is a fraction of the BLADE`

**...through** `means the middle section sits 30–70% of the way along the blade.`

**Replace with:**

```
- ``middlePos`` is a fraction of the BLADE SPAN from the root: radius = ``4 + middlePos·(impellerRadius − 4)`` mm, NOT ``middlePos × impellerRadius``.
```

#### REC-41 · COMPRESS · −264 chars · risk low

*File:* `DC_prompt_fragments/dc_config/modelling_notes.md` · *Section:* ### Hard engineering blockers

**Why:** A one-item list wrapped in a heading, a preamble and a moral; the single blocker is all the content.

**Cut from** `### Hard engineering blockers (parameter combinations that break the geometry)`

**...through** `treat any violation as a non-negotiable fail.`

**Replace with:**

```
### Hard blockers
``innerThickness ≤ 0`` or ``outerThickness ≤ 0`` degenerates the blade section — a non-negotiable fail wherever you check consistency.
```

#### REC-42 · DELETE · −249 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DON'T bounce permission questions back

**Why:** Duplicated in full by the routing.py permission section retained in compressed form (REC-08).

**Cut from** `<<CHAIN_ONLY>>- DON'T bounce permission questions back to the previous agent.`

**...through** `them to the Orchestrator.`

**Replace with:**

```
<<CHAIN_ONLY>>
```

#### REC-43 · COMPRESS · −206 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* **Forbidden: a no-op write.**

**Why:** Keeps the ban and the check; drops the 'you are stateful' framing and the consequence sentence.

**Cut from** `**Forbidden: a no-op write.**  You may NOT write a ``parameters.json```

**...through** `not and wastes a downstream cycle.`

**Replace with:**

```
**No no-op writes.**  Never write a ``parameters.json`` byte-identical to one you already wrote this session — check your earlier writes; if the draft repeats one, change it or ESCALATE.
```

#### REC-44 · COMPRESS · −205 chars · risk low

*File:* `DC_prompt_fragments/tools_config/blade_sections_visualizer_dc_input_creator.md` · *Section:* whole fragment

**Why:** DCIC-only overlay; the mechanism explanation belongs to the Tool Caller's overlay.

**Cut from** `When the plan is a blade-sections task — render the sections, not the full 3D`

**...through** `render the sections from that file instead of
generating the mesh.`

**Replace with:**

```
When the plan is a blade-sections task, tell the Tool Caller in your hand-off to render the blade sections; write ``parameters.json`` and open the attempt as usual.
```

#### REC-45 · DELETE · −188 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DON'T script the final user-facing reply

**Why:** An incident patch aimed at agents that talk about user wording; the DCIC's output is a JSON file plus a hand-off, and the Receptionist's ownership of user text is stated in its own prompt.

**Risk:** Shared by 6 chain agents — if any of them has drifted into writing user-facing prose, keep this bullet for that agent instead of deleting globally.

**Cut from** `- DON'T script the final user-facing reply.  Route your content to the`

**...through** `never write the user-facing message yourself.`

**Replace with:** *(nothing — pure deletion)*

#### REC-46 · DELETE · −187 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* **Carry ``Current attempt:`` forward**

**Why:** The Hand-off section already mandates the three path lines on every FORWARD, including ``Current attempt:``.

**Cut from** `**Carry ``Current attempt:`` forward** — every FORWARD you send`

**...through** `MUST quote the folder you wrote into.`

**Replace with:** *(nothing — pure deletion)*

#### REC-47 · COMPRESS · −183 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Re-reading raw inputs (optional)

**Why:** Tool mechanics live in the schemas; the only steering content is 'you cannot see images'.

**Cut from** `## Re-reading raw inputs (optional)`

**...through** `images themselves — rely on the extraction.`

**Replace with:**

```
## Raw inputs (optional)
Your primary input is ``extracted_inputs.txt``.  ``list_input_files`` / ``read_input_text(path)`` reach the raw files under ``inputs/``; you cannot view images — rely on the extraction.
```

#### REC-48 · DELETE · −169 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* CLARIFY / ESCALATE path-lines note

**Why:** Permission not to do something optional; the Hand-off section already scopes the three lines to FORWARDs.

**Cut from** `If you CLARIFY back to <<PF_ON>>the UII<</PF_ON>><<PF_OFF>>the Planner<</PF_OFF>> or ESCALATE to the`

**...through** `no path lines are needed — only FORWARDs carry them.`

**Replace with:** *(nothing — pure deletion)*

#### REC-49 · COMPRESS · −167 chars · risk medium

*File:* `agents/dc_input_creator/prompt.md` · *Section:* *Thickness / *Camber ratio note

**Why:** Keeps the whole gotcha (a real bug source) and the disambiguation duty in half the words.

**Risk:** This is the only in-prompt statement that a pinned chord caps absolute size; do not delete, only compress as written.

**Cut from** ```*Thickness`` and ``*Camber`` are RATIOS (percentages of that section's own`

**...through** `state in one clause which reading you used before
applying it.`

**Replace with:**

```
``*Thickness`` / ``*Camber`` are percentages of that section's OWN chord, so "thicker" can mean the ratio or the absolute mm — they diverge when the chord changes.  If the request is unclear, say which reading you used.
```

#### REC-50 · COMPRESS · −151 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* **Reuse the session's history.**

**Why:** Same instruction, minus the explanation of who benefits.

**Cut from** `**Reuse the session's history.**  ``list_attempts`` / ``read_attempt```

**...through** `so the <<DCII_ONLY>>DCII / <</DCII_ONLY>>DCOI know you considered it.`

**Replace with:**

```
**Reuse history.**  ``list_attempts`` / ``read_attempt`` show prior cycles; when a directive resembles an earlier one, try a different direction than the combination that failed and name that attempt in your hand-off.
```

#### REC-51 · COMPRESS · −125 chars · risk low

*File:* `agents/dc_input_creator/prompt.md` · *Section:* ## Output Format

**Why:** Two sentences into one; the don't-repeat-the-JSON rule (a real token sink) is kept.

**Cut from** `## Output Format`

**...through** `JSON in text — it is stored on disk by the tool.`

**Replace with:**

```
## Output
Put your brief note (defaults chosen, translations applied, anything notable) in the routing tool's ``message``; never repeat the JSON in text.
```

#### REC-52 · COMPRESS · −87 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DON'T fabricate observations

**Why:** The general principle already covers the render-hallucination incident; the two-clause build-up is redundant.

**Risk:** This is the fleet-wide anti-hallucination rule (agents once described renders they never loaded). Keep the compressed sentence — never delete it.

**Cut from** `- DON'T fabricate observations about artifacts you did not see produced.`

**...through** `or something the user literally said, do not make it.`

**Replace with:**

```
- DON'T state an observation you cannot source to a tool result, an agent's history, or the user's own words.
```

</details>

**Auditor notes.** MEASUREMENT. I reassembled the prompt locally (Template substitution + the DCII_ON / PF_OFF / BSV_ON / no-DBa / CHAIN_ONLY filters) : body = 37,862 chars, plus ~5,650 chars of code-built routing block = ~43,500 chars for the stated 9,586 tokens, i.e. ~4.5 chars/token, NOT 4. All chars_removed below are real file-character counts (original span minus the replacement I wrote). Sum = 29,229 chars → ~14,300 chars left → ~3,200 tokens. Reaching the bottom of your 1,000-3,000 band is not achievable without touching things I judge load-bearing: the 16-parameter list alone is 1,659 chars (370 tok, must stay), the routing block another 330 tok, and the shared hard-constraint blocks 245 tok.

WHAT I DELIBERATELY DID NOT CUT.
1. $parameter_list (DC_prompt_fragments/dc_config/parameters.md) — untouched per your rule. It could be tabularised for maybe 300 chars, but the middlePos line there is now the single canonical statement of the span-fraction formula (REC-29 and REC-40 lean on it), so I left it alone.
2. $qualitative_examples (303 chars) — five canonical translations, already exactly the shape golden rule 2 asks for.
3. The three Validate checks, the *Thickness/*Camber ratio note, the SOFT-TARGET-is-not-locked clause, the routing-is-a-tool-call mandate and the anti-hallucination rule. Each maps to a known production failure; all survive as compressed general principles (REC-05, REC-49, REC-23, REC-30, REC-52).

BLAST RADIUS OF THE SHARED-FRAGMENT CUTS (a change to any of these hits every agent listed):
  generic_constraints.md (REC-30/31/36/38/42/45/52) — 8 agents.
  hard_constraints_dc.md (REC-16) / hard_constraints_tools.md (REC-18) — 8 agents each.
  blade_sections_visualizer.md (REC-28) — 9 agents.
  value_states.md (REC-07/10) — DCIC, DCII, DCOI, Planner.
  modelling_notes.md (REC-01/40/41) — DCIC, DCII.
  structure.md (REC-29) — DCIC, UII.
  agents/shared/routing.py (REC-08/11/15/17/21/27/33) — all 6 chain agents; this is the single highest-leverage file in the whole fleet (~5,650 chars × 6 prompts) and the cuts there are pure golden-rule-10 material.

THREE INTERLOCKS TO WATCH WHEN APPLYING SELECTIVELY.
  a) REC-21 (delete routing.py's "Routing is a tool call — MANDATORY") is only safe together with REC-30 (or REC-53), which keeps the same invariant including the "pipeline halts" consequence. Applying REC-21 alone removes the fix for a real halt-the-pipeline failure.
  b) REC-15 (delete routing.py's "Do not loop") requires generic_constraints keeping its DON'T-loop bullet — REC-53's scoped version keeps it; REC-30/31/36/42/45/52 do not touch it.
  c) REC-53 (scope the generic constitution into the DCIC prompt) supersedes REC-30/31/36/38/42/45/52 for THIS agent only. Its 860 chars are counted as the incremental extra on top of them, so the totals hold whether you apply the shared compressions, the per-agent scoping, or both.

THE ONE STRUCTURAL RISK I WANT FLAGGED. REC-23 compresses the precision-directive paragraph, which enumerates a SUBSET of movable parameters ("*Thickness, *Camber, *MaxPos, the section angles"). That enumeration pattern is exactly what once silently revoked a chord authorisation. I kept the two antidotes — "a SOFT TARGET counts as unlocked" inside REC-23 and the lever-set-WIDENS rule in REC-25 — but if you want belt-and-braces, add one clause to REC-23's replacement: "this list narrows nothing that a hand-off already authorised."

NOT PROPOSED, BUT WORTH A SEPARATE PASS: the DCIC carries 12 tool schemas (1,769 tok). ``list_attempts``/``read_attempt``/``read_input_text``/``list_input_files``/``read_extracted_inputs`` are five read tools whose prose in this prompt exists mostly to disambiguate between them (golden rule 9); merging the two input-listing tools would let REC-47 shrink further and remove a decision point.

### 7.x User Input Inspector — second opinion (44 cuts → ~3,250 tok)

| action | section | −chars | risk | what |
|---|---|---:|---|---|
| COMPRESS | ## Forwarding and routing | 2457 | medium | Three routing paths and one CLARIFY path are narrated over 52 lines with per-branch justification prose; the same decision table fits in a dozen lines and the routing-is-mandatory rule is already stated (once) in routing.py. |
| MOVE_TO_FRAGMENT | ### Matching a ROUGH sketch / ### Matching a PRECISE sk | 2182 | medium | These three subsections tell an agent HOW TO MATCH a design to a sketch (revise or not, converged or not) — that is DCII/DCOI work; the UII only extracts and never judges a match. |
| COMPRESS | ### 3. Design Intent and Functional Requirements | 1799 | medium | A 5-bullet checklist plus three paragraphs of justification for why each bullet exists; the two load-bearing items (PRECISION DEMAND line, authorisation-with-goal → SOFT TARGET) survive, the reasoning does not. |
| COMPRESS | ## User input layout (text + images) | 1702 | low | Three file descriptions plus two explanatory paragraphs on why to load images and why to report readability; the instructions themselves are six lines. |
| COMPRESS | ### 1. QUANTITATIVE INPUTS | 1614 | low | Two line-format templates are shown twice each, and the multi-design case gets a full 10-line worked example where a one-line illustration carries the same shape. |
| COMPRESS | **Soft targets — a provided value the user subordinated | 1347 | medium | The marker format and the 'goal governs, number is the fallback' semantics are the behaviour; the rest is a paragraph explaining to downstream agents how to read a marker that is not in their prompt anyway. |
| COMPRESS | ## Reading prior attempts when the user references them | 1340 | low | A whole section of when-to / when-not-to prose with three worked examples for two tools that are used in a minority of turns; one canonical example plus the negative case suffices. |
| COMPRESS | ### Temporal scope and Parameters Inputs interface bloc | 1265 | low | Five bullets, three of them multi-turn worked dialogues, to state ADD / MODIFY (new wins) / REVERT / start-over / carry-forward — a 6-line rule. |
| REPLACE_WITH_EXAMPLES | whole fragment (DC_prompt_fragments/dc_config/user_inpu | 1149 | low | Five bulleted incident patterns each with its own justification collapse into one 'the DC renders X, so ignore drawn Y' sentence plus the blade-count exception. |
| COMPRESS | ### UII — for a PRECISE blade-section drawing (item 2,  | 1120 | low | Two near-identical worked crop-box examples plus three paragraphs of why; one example of each kind and one rule line carry it. |
| SCOPE_PER_AGENT | ## Hard constraints — DC-specific ($hard_constraints_dc | 1074 | medium | The DC hard rules forbid expressing designs in non-parameters, mesh post-processing, and offering CFD/FEA — none of which the UII ever does; it only records what the user asked for. |
| SCOPE_PER_AGENT | ## Hard constraints — tool-specific ($hard_constraints_ | 1015 | low | Two thirds of this fragment is the attempt-folder append-only / never-edit-parameters.json contract, which the UII cannot violate — it writes only the extraction file. |
| COMPRESS | ### What every agent in any design configurator MAY do  | 1010 | medium | Six DOs padded with rationale; 'answer in English' and 'act on your hand-off' are near-default behaviour, and the FORWARD/ESCALATE bullets duplicate the '### How to decide where to route' block built by routing.py. |
| COMPRESS | ### UII — for a PRECISE blade-section drawing (intro +  | 950 | low | The example block IS the instruction; the surrounding three paragraphs restate 'it is an estimate, not a locked value' four times. |
| COMPRESS | ### Filled-in templates and forms | 914 | low | One rule (only the added marks are input) stated three ways plus a blank-form comparison procedure; the Ø160/Ø140 example is the part that teaches it. |
| COMPRESS | **B. Parameters Inputs interface blocks (auto-appended  | 914 | medium | The snapshot-not-delta walk is real state logic, but it is written twice — once as prose per block and once as an algorithm; keep the algorithm. |
| COMPRESS | **STRICT rules for QUANTITATIVE INPUTS:** | 881 | medium | Three rules with a justification paragraph each, two of which ('revisions overwrite', 'releases omit') are already stated under Temporal scope and again under D. |
| SCOPE_PER_AGENT | <<BSV_ON>> $blade_sections_visualizer / $blade_sections | 830 | low | The shared blurb explains a tool the UII cannot call; the only UII-relevant fact is 'say when the request centres on the sections so the Planner can take the fast path'. |
| COMPRESS | ## Your utility tools | 822 | low | Each tool blurb repeats what the tool schema already says plus what 'User input layout' already said about read_user_inputs not loading images. |
| COMPRESS | ### Capture, do not filter | 798 | low | Two paragraphs arguing for breadth plus a list of examples; the examples alone teach it. |
| COMPRESS | **HARD RULE — countable features in reference images** | 775 | medium | An incident patch written at maximum emphasis; the general principle (count discrete features yourself, image beats note, record disagreement) is four lines. |
| MERGE | routing_instructions() — the free-form-prose + do-not-a | 768 | medium | Two consecutive blocks say the same thing — write prose, don't announce the call, don't duplicate your work product — and the second re-states the mandate already given one block earlier. |
| COMPRESS | routing_instructions() — '### Permission / authorisatio | 751 | medium | An incident patch (agents bouncing back for ritual re-confirmation) written as three paragraphs; the rule is two sentences. |
| COMPRESS | whole fragment | 719 | medium | Owner's rule: the list stays inline — but the ASCII column padding and per-line headers cost ~45% of it; every name, unit and range is preserved verbatim in a denser layout, and the '% of that section's own chord' gotcha is folded in. |
| DELETE | routing_instructions() — '### Do not loop — ESCALATE wh | 665 | low | Verbatim duplicate of generic_constraints.md's "DON'T loop: if you are about to call the same tool with the same arguments…", which is spliced into the same prompt a few sections earlier. |
| DELETE | ## End-of-session feedback message (read-only) | 651 | low | Describes a message the agent passively receives at session end and needs no instruction to read; the spliced outro even tells the UII to fold it into "your DH answers", which the UII never writes. |
| COMPRESS | ### UII responsibility — record the sketch's precision  | 628 | low | Two full example paragraphs plus a closing 'without this, downstream agents…' justification; one compressed example pair states the contract. |
| COMPRESS | ### Judging a sketch's precision | 620 | low | Four bullets each giving both poles of a spectrum; one sentence per cue conveys the same judgement. |
| COMPRESS | DON'Ts — the plain-prose channel bullet | 530 | medium | Fourth statement of one rule: it is also in routing.py's '### Routing is a tool call — MANDATORY', in routing.py's do-not-announce block, and in this prompt's own Forwarding section. |
| COMPRESS | ### 2. QUALITATIVE DESCRIPTIONS | 497 | low | The authorisation-summary rule is stated here, again under DESIGN INTENT, and again under Temporal scope; one statement plus a pointer suffices. |
| COMPRESS | routing_instructions() — '### How to decide where to ro | 490 | low | Four routing branches written as full sentences with parenthetical justification; a four-line decision table is unambiguous and shorter. |
| COMPRESS | ## What to Extract — categorisation rule | 460 | low | The 'numeric ≠ matches a parameter' clarification is a separate bolded paragraph restating the QUANTITATIVE bullet it follows. |
| COMPRESS | whole fragment | 443 | medium | The middlePos definition appears here in full AND again in the parameter list; a numbered structure list restating the parameter names is largely redundant with the list that follows it. |
| COMPRESS | routing_instructions() — position header block | 424 | medium | Six lines of prose to state two facts (next agent, previous agent) that the bound routing tools already encode. |
| COMPRESS | **D. NEVER include historical or annotation-style entri | 423 | low | Three example bad entries plus a per-section restatement of 'simply OMIT it'; one line covers both sections. |
| SCOPE_PER_AGENT | ## Qualitative-to-Quantitative Hints ($qualitative_exam | 363 | low | These map adjectives onto parameter directions ("thick blades → upper end of range") — that is the DCIC's translation job; the UII is explicitly told not to invent parameter values. |
| COMPRESS | DON'Ts — chain-only bullets | 350 | low | All three duplicate routing.py: the permission-routing block, the ESCALATE-on-repeat-failure rule, and the Receptionist-composes rule. |
| COMPRESS | DON'Ts — invent / fabricate / loop bullets | 330 | medium | Three real invariants padded with enumerations and reasons; the invariants survive intact at a third of the length. |
| COMPRESS | routing_instructions() — '### Routing is a tool call —  | 292 | medium | The retired ---ROUTING--- template is warned against in three sentences; one clause does it, and the mandate itself is restated twice inside the same block. |
| COMPRESS | whole fragment | 250 | low | The closing paragraph duplicates the 'You are first in the natural flow' line routing.py already emits, and the tool blurbs restate the routing tools' own schemas. |
| COMPRESS | **C. Multi-design requests.** | 245 | low | The Design A / Design B labelling convention is already demonstrated at length under QUANTITATIVE INPUTS. |
| COMPRESS | ## Your Role | 131 | low | The parenthetical defends the sketch case at three times the length of the rule it qualifies. |
| COMPRESS | opening paragraph | 123 | low | Says 'precision varies, do not assume rough' twice in four lines. |
| COMPRESS | DON'Ts heading | 57 | low | Ceremonial heading; the bullets already begin with DON'T. |

<details><summary><b>Full text of each second-opinion change</b></summary>

#### REC-01 · COMPRESS · −2457 chars · risk medium

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## Forwarding and routing

**Why:** Three routing paths and one CLARIFY path are narrated over 52 lines with per-branch justification prose; the same decision table fits in a dozen lines and the routing-is-mandatory rule is already stated (once) in routing.py.

**Risk:** Removes the local restatement of 'prose with no routing call is a HARD failure'; the rule survives verbatim in routing.py's '### Routing is a tool call — MANDATORY' block, which is spliced into this prompt via {routing_instructions}. Both PF branches are preserved in the replacement.

**Cut from** `Every run ends with a routing tool call — prose with no routing call is`

**...through** `For those, ESCALATE to the Orchestrator stating what is missing — the UII is the wrong target for permission questions.`

**Replace with:**

```
End every run with a routing tool call, and only AFTER ``write_extraction`` succeeded.  Keep the ``message`` to one or two sentences — the extraction is on disk, do not repeat it — including how readable the user's images were, plus these lines verbatim:

    Extracted inputs file: <the path from your incoming "Extraction output file:" line>
    Current attempt: <absolute path>          # ONLY when the hand-off supplied one

- Design request — and an extraction-only request too — → <<PF_OFF>>``call_planner``<</PF_OFF>><<PF_ON>>``call_dc_input_creator``<</PF_ON>>.<<PF_ON>>  For an extraction-only request use ``call_orchestrator`` instead, with a brief summary.<</PF_ON>>
- Out of scope, asks for something not in the user's files, or an unrecoverable error → ``call_orchestrator``.
- If a downstream agent CLARIFYs back (a value misread, a file overlooked) — re-read the source, ``write_extraction`` again, forward again.  But you only RECORD what is in the user's files: design intent, engineering judgement and whether a change is authorised are not yours to answer or grant — escalate those.
```

#### REC-02 · MOVE_TO_FRAGMENT · −2182 chars · risk medium

*File:* `DC_prompt_fragments/dc_config/user_input_types/sketch_handling.md` · *Section:* ### Matching a ROUGH sketch / ### Matching a PRECISE sketch / ### Always true

**Why:** These three subsections tell an agent HOW TO MATCH a design to a sketch (revise or not, converged or not) — that is DCII/DCOI work; the UII only extracts and never judges a match.

**Risk:** Requires a code change: move the quoted text into DC_prompt_fragments/dc_config/user_input_types/sketch_matching.md, add a "sketch_matching" entry to _build_slots() and FRAGMENT_TO_SLOT in agents/shared/prompts.py, and splice $sketch_matching into dc_input_inspector/prompt.md and dc_output_inspector/prompt.md only. If the slot is not added, DCII/DCOI silently lose the rough-vs-precise matching rule (the 'don't chase sketch imperfections' convergence guard).

**Cut from** `### Matching a ROUGH sketch — qualitative
  * Imperfections are drawing artifacts, not design intent`

**...through** `say so plainly — don't imply more iterations would close the gap.`

**Replace with:** *(nothing — pure deletion)*

#### REC-03 · COMPRESS · −1799 chars · risk medium

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### 3. Design Intent and Functional Requirements

**Why:** A 5-bullet checklist plus three paragraphs of justification for why each bullet exists; the two load-bearing items (PRECISION DEMAND line, authorisation-with-goal → SOFT TARGET) survive, the reasoning does not.

**Risk:** PRECISION DEMAND is read by the Planner to decide whether to run the forced refine loop — the replacement keeps the label, the free-form nature, and the 'understating it kills the loop' consequence in one clause.

**Cut from** `What is the user trying to achieve?  Consider:`

**...through** `prune any previously-recorded text that is no longer load-bearing for the current design intent.`

**Replace with:**

```
One coherent paragraph of the CURRENT intent (not an append-only log): purpose, performance goals, constraints, aesthetics, and any reporting preference ("do not report back until viable").  Also record here:

- ``PRECISION DEMAND: <what the user asked, at their strength>`` — free-form, whenever the user asks the design (especially the blade sections) to match a drawing closely or to keep trying.  The Planner reads it to decide whether to run the forced precision refine loop, so understating it means the loop never runs.  This is the user's MANDATE, a separate thing from how precise the sketch itself is.
- Authorisations tied to a design characteristic ("I prefer clean geometry over my exact X — vary it"), naming the goal.  When the permission subordinates a SPECIFIC value to that goal, also mark the value SOFT TARGET in §1.  Permission with no design-intent context belongs in §2 only.
- Prior-attempt facts that shape the CURRENT intent — never a transcript of past revisions.
```

#### REC-04 · COMPRESS · −1702 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## User input layout (text + images)

**Why:** Three file descriptions plus two explanatory paragraphs on why to load images and why to report readability; the instructions themselves are six lines.

**Cut from** `The user's input directory contains:
  * ``user_query.txt`` — every user-facing turn (chronological log).`

**...through** `a short observation in QUALITATIVE DESCRIPTIONS or alongside the image's mention is plenty.`

**Replace with:**

```
- ``user_query.txt`` — every user turn, chronological.
- ``extracted_inputs.txt`` — an earlier extraction, when the workflow exposes it.  INFORMATIONAL only: never copy lines forward, always recompute from ``user_query.txt``.
- ``input_images/`` — optional reference images, each with a ``<name>_note.txt`` (pairing is guaranteed upstream).  The note is first-class user intent, not optional commentary — integrate BOTH.

``read_user_inputs`` returns all the text (including every note) and LISTS the images but does NOT load them.  Read the notes, then ``view_images`` every image whose content you must judge (count features, read geometry, resolve an ambiguity); skip only an image its note already fully describes.  State in the extraction how readable each image was — a clean one-feature sketch is simple, a busy technical drawing or a photo is complex — so downstream agents know whether to trust your words or re-load the picture.
```

#### REC-05 · COMPRESS · −1614 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### 1. QUANTITATIVE INPUTS

**Why:** Two line-format templates are shown twice each, and the multi-design case gets a full 10-line worked example where a one-line illustration carries the same shape.

**Cut from** `Record one quantitative input per line.  When the value maps`

**...through** `the format that compresses tightest.  Downstream agents (Planner, DCIC, DCII) read this section verbatim.`

**Replace with:**

```
One line per quantity.  When the value maps verbatim to a configurator parameter in that parameter's own unit, label the line with the parameter name:

    <parameter_name>: <value> <parameter_unit>

Otherwise label the real-world quantity, keep the user's unit / frame, and name the related parameter — conversion is the DCIC's job:

    <real-world quantity>: <value> <user's unit> (real-world; configurator stores <quantity> as <its unit/frame> — see <related_param>)

Structure by intent, not by compactness — downstream agents read this verbatim.  For several distinct designs, label each and list its inputs under it (``Design A (thin-blade variant): - bladeCount: 3 …``).  For a sweep, a short prose line naming the swept parameter and its bounds.  When there are none: "No quantitative inputs provided; the system may choose all $parameter_count parameters freely within their allowed ranges."
```

#### REC-06 · COMPRESS · −1347 chars · risk medium

*File:* `agents/user_input_inspector/prompt.md` · *Section:* **Soft targets — a provided value the user subordinated to a goal.**

**Why:** The marker format and the 'goal governs, number is the fallback' semantics are the behaviour; the rest is a paragraph explaining to downstream agents how to read a marker that is not in their prompt anyway.

**Risk:** SOFT TARGET is a recent first-class feature; the replacement keeps the example line, the newer-intent-wins interaction with UI-pinned values, and the 'only when the user themselves subordinated it' guard.

**Cut from** `**Soft targets — a provided value the user subordinated to a goal.**`

**...through** `instead of a locked value, and drop it from the locked FIXED set.`

**Replace with:**

```
**SOFT TARGET — a value the user subordinated to a goal.**  When the user gives a value but calls it secondary ("here are dimensions, but fit the sketched shape; the exact numbers matter less"), keep its normal line and add a marker naming the GOAL and how close to hold it:

    - outerRadius: ~140 mm — SOFT TARGET (goal: match the sketched blade shape; keep near 140 mm if free, but vary freely to fit the shape)

The goal governs; the number is only a fallback where the goal does not bear.  Take the strength from the user's own wording; if they did not say, write "keep reasonably close if free".  Use it ONLY where the user themselves subordinated the value — otherwise it stays a locked input.  A UI-pinned (FIXED) value is locked, but newer intent wins: if the user later subordinates it, record it as a SOFT TARGET and drop it from the FIXED set.  State the goal itself in DESIGN INTENT (§3).
```

#### REC-07 · COMPRESS · −1340 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## Reading prior attempts when the user references them

**Why:** A whole section of when-to / when-not-to prose with three worked examples for two tools that are used in a minority of turns; one canonical example plus the negative case suffices.

**Cut from** `You also have ``list_attempts()`` and ``read_attempt(n, file)```

**...through** `extraction and choose on its own; calling these tools speculatively just wastes a round-trip.`

**Replace with:**

```
``list_attempts()`` and ``read_attempt(n, file)`` read this session's attempt folders (``parameters.json``, ``description.txt``, render filenames).  Use them ONLY when the user's message explicitly makes a prior attempt the baseline ("same as the latest attempt but one fewer blade", "something between attempts 1 and 4"): fetch the values and write the resulting set into QUANTITATIVE INPUTS.  For a generic request ("make it lighter") do not call them — the DCIC fetches what it needs.
```

#### REC-08 · COMPRESS · −1265 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### Temporal scope and Parameters Inputs interface blocks — A. Temporal merging

**Why:** Five bullets, three of them multi-turn worked dialogues, to state ADD / MODIFY (new wins) / REVERT / start-over / carry-forward — a 6-line rule.

**Cut from** `The extraction is a snapshot of the user's **CURRENT** request —`

**...through** `they ARE the cumulative current state, not the most recent message in isolation.`

**Replace with:**

```
The extraction is a snapshot of the user's **CURRENT** request, not a history.

**A. Merging turns.**  ``user_query.txt`` is an append-only log of every user message.  A later message can ADD detail, MODIFY it (the NEW wins, the old is discarded), or REVERT an earlier modification ("bring back the previous blade count" → the older value returns).  "Start over" / "fresh design" / "ignore the above" discards everything before it.  Otherwise carry forward every detail still consistent with the latest message.  Design intent and qualitative descriptions are cumulative in the same way.
```

#### REC-09 · REPLACE_WITH_EXAMPLES · −1149 chars · risk low

*File:* `agents/shared/prompt_fragments/sketch_notes.md` · *Section:* whole fragment (DC_prompt_fragments/dc_config/user_input_types/sketch_notes.md)

**Why:** Five bulleted incident patterns each with its own justification collapse into one 'the DC renders X, so ignore drawn Y' sentence plus the blade-count exception.

**Risk:** Shared fragment — also spliced into the DC Input Inspector and DC Output Inspector prompts; all three benefit identically. NOTE the file path is DC_prompt_fragments/dc_config/user_input_types/sketch_notes.md.

**Cut from** `Configurator-specific patterns the operator has observed in how users`

**...through** `follow that stated count, not the number of blades actually drawn.`

**Replace with:**

```
How this DC renders vs. how users draw: blades are always structurally connected to the ring (ignore a drawn gap or overshoot), the hub is a clean centred cylinder (ignore drawn wobble or off-centre placement), all blades are identical by construction (pick one curvature / sweep / chord matching the sketch's average character), and the ring has uniform thickness (pick one representative ``impellerThickness``).

Blade COUNT is the exception: it is a deliberate discrete choice, so count the blades in the top-down view carefully and trust that count — unless the user states the number by other means ("×6", "6 blades" in text), which overrides what is drawn.
```

#### REC-10 · COMPRESS · −1120 chars · risk low

*File:* `DC_prompt_fragments/dc_config/user_input_types/sketch_handling.md` · *Section:* ### UII — for a PRECISE blade-section drawing (item 2, crop region)

**Why:** Two near-identical worked crop-box examples plus three paragraphs of why; one example of each kind and one rule line carry it.

**Risk:** Shared fragment (UII, DCII, DCOI) — this subsection is UII-only content the other two currently carry for nothing.

**Cut from** `2. **A coarse crop region.**  When the section drawings occupy only part of a`

**...through** `and any whole-propeller crop later (the expensive 3D check).`

**Replace with:**

```
Also record a COARSE normalized crop box ``[x0, y0, x1, y1]`` (fractions 0..1) for each region worth re-viewing, so the DC Output Inspector can crop to it when comparing:

    SKETCH CROP REGION — the blade-section drawings in 0346_3.png occupy roughly the bottom third: crop box [0.0, 0.72, 1.0, 1.0] (pass as ``regions`` to ``view_images``).
    SKETCH CROP REGION (top view) — the top-down drawing in 0346_1.png fills the upper half: crop box [0.0, 0.0, 1.0, 0.55] (compare against the 3D top render).

Coarse is fine.  Label a whole-propeller view with WHICH view it is, so the later 3D check compares the right sketch view against the right render.
```

#### REC-11 · SCOPE_PER_AGENT · −1074 chars · risk medium

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## Hard constraints — DC-specific ($hard_constraints_dc)

**Why:** The DC hard rules forbid expressing designs in non-parameters, mesh post-processing, and offering CFD/FEA — none of which the UII ever does; it only records what the user asked for.

**Risk:** Removes the UII's only statement that the parameter set is closed and that analysis/export formats are unavailable; the replacement keeps that as one general principle so the UII does not echo an impossible promise into DESIGN INTENT. The shared fragment is untouched for the other seven agents.

**Cut from** `## Hard constraints — DC-specific`

**...through** `$hard_constraints_dc`

**Replace with:**

```
## What the configurator cannot do
Only the $parameter_count parameters above exist — there is no mesh editing, no performance / CFD / FEA analysis, no alternative export format, no extra views.  Record such a request faithfully; never promise it.
```

#### REC-12 · SCOPE_PER_AGENT · −1015 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## Hard constraints — tool-specific ($hard_constraints_tools)

**Why:** Two thirds of this fragment is the attempt-folder append-only / never-edit-parameters.json contract, which the UII cannot violate — it writes only the extraction file.

**Risk:** The two rules that do bind the UII (no guessed paths, all arithmetic through calculate) are kept inline. Shared fragment untouched for the other agents.

**Cut from** `## Hard constraints — tool-specific`

**...through** `$hard_constraints_tools`

**Replace with:**

```
## Tool rules
- Read tools take ONLY a path a hand-off label gives (``Input directory:``, ``Extraction output file:``, ``Current attempt:``) or an upstream tool's return value — never a guessed one.
- Route EVERY arithmetic operation through ``calculate``, batching this turn's expressions into ONE call; never do mental arithmetic.
```

#### REC-13 · COMPRESS · −1010 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent in any design configurator MAY do (DOs)

**Why:** Six DOs padded with rationale; 'answer in English' and 'act on your hand-off' are near-default behaviour, and the FORWARD/ESCALATE bullets duplicate the '### How to decide where to route' block built by routing.py.

**Risk:** Shared fragment spliced into all 8 non-DH agents — high leverage, applies to everyone. The STANDING DIRECTIVES verbatim-carry rule is preserved in full force (it is a real cross-agent invariant).

**Cut from** `### What every agent in any design configurator MAY do (DOs)
- DO act on the inputs in your hand-off`

**...through** `- DO answer in English; do not substitute words from other languages or scripts.`

**Replace with:**

```
### DOs
- DO act on the inputs in your hand-off and the files it references, using only the tools listed for your role — that list is exhaustive.
<<CHAIN_ONLY>>- DO reproduce any ``=== STANDING DIRECTIVES … ===`` block from your hand-off UNCHANGED in your own outgoing hand-off — never alter, summarise, re-order or omit it; only the Planner may change it.
<</CHAIN_ONLY>>- DO write hand-offs as free-form prose carrying exactly what the recipient needs — the paths their tools require, what changed and why, and the authorship of any non-user-authored value ("the Planner directed …", "the user asked …") — and nothing more.  Answer in English.
```

#### REC-14 · COMPRESS · −950 chars · risk low

*File:* `DC_prompt_fragments/dc_config/user_input_types/sketch_handling.md` · *Section:* ### UII — for a PRECISE blade-section drawing (intro + item 1, warm start)

**Why:** The example block IS the instruction; the surrounding three paragraphs restate 'it is an estimate, not a locked value' four times.

**Risk:** Shared fragment (UII, DCII, DCOI). Keeps the exact SUGGESTED SECTION SHAPES label and its three-line shape, which the DCIC's warm start depends on.

**Cut from** `The DC Input Creator authors the parameters but CANNOT see the images; you can.`

**...through** `The downstream loop refines it against the drawing, so do not over-invest.`

**Replace with:**

```
The DC Input Creator authors the parameters but cannot see the images; you can.  So when an image holds a precise blade-section (airfoil) drawing, read its proportions into a ROUGH per-section estimate — thickness (% of that section's own chord), camber (% chord), max-thickness position (tenths of chord) — and record it in QUALITATIVE DESCRIPTIONS as a warm start:

    SUGGESTED SECTION SHAPES (rough estimate read from the precise drawing — a STARTING POINT for the DC Input Creator, NOT a user-locked value; refine within ranges):
      inner  ≈ 8% thick, 3% camber, max-thickness at ~3/10 chord
      middle ≈ 14% thick, 4% camber, max-thickness at ~3/10 chord
      outer  ≈ 10% thick, 3% camber, max-thickness at ~4/10 chord

An eyeball reading of the user's own drawing is enough; the downstream loop refines it.
```

#### REC-15 · COMPRESS · −914 chars · risk low

*File:* `DC_prompt_fragments/dc_config/user_input_types/sketch_handling.md` · *Section:* ### Filled-in templates and forms

**Why:** One rule (only the added marks are input) stated three ways plus a blank-form comparison procedure; the Ø160/Ø140 example is the part that teaches it.

**Risk:** Shared fragment (UII, DCII, DCOI). Keeps the concrete example and the never-enforce-a-printed-range clause, which is the actual failure mode.

**Cut from** `### Filled-in templates and forms
Some reference images are a PRE-PRINTED FORM the user drew on`

**...through** `the user's marks are darker, handwritten and irregular.`

**Replace with:**

```
### Filled-in forms
When the image is a pre-printed form the user drew on, ONLY the added marks (darker, handwritten, irregular) are input.  The printed scaffolding — guide lines, reference circles, min/max callouts, scales, grids, fixed labels — shows what to specify; it is never the user's value and never an enforceable limit.  E.g. a form printing "Ø160 / Ø120" and "5 mm max / 1 mm min", with a hand-drawn outline labelled "Ø140" and a ring reading ~3 mm, means 140 and 3.  A blank copy of the same form, if you have one, tells you exactly what is scaffolding.
```

#### REC-16 · COMPRESS · −914 chars · risk medium

*File:* `agents/user_input_inspector/prompt.md` · *Section:* **B. Parameters Inputs interface blocks (auto-appended by the web UI).**

**Why:** The snapshot-not-delta walk is real state logic, but it is written twice — once as prose per block and once as an algorithm; keep the algorithm.

**Risk:** This is genuine state-machine logic (FIXED = full snapshot, RELEASED = drop keys). The replacement keeps the exact block-header strings, the snapshot semantics, the MUST/MUST NOT, and the forward walk. Better still would be computing the active FIXED set in code and handing the UII the result (golden rule 10).

**Cut from** `**B. Parameters Inputs interface blocks (auto-appended by the web`

**...through** `most recent turn is the active constraint set, and is what you reflect in QUANTITATIVE INPUTS.`

**Replace with:**

```
**B. Parameters Inputs blocks (auto-appended by the web UI).**  A turn may carry ``"The user has fixed the following values through the Parameters Inputs interface:"`` + ``- key: value unit`` lines — a FULL SNAPSHOT of what the user is currently pinning, not a delta; these MUST appear in QUANTITATIVE INPUTS.  And/or ``"The user is no longer constraining the following parameters …"`` + ``- key`` lines — now FREE; these MUST NOT appear at all, not even as an annotation.  Either block may be absent (= no change since the last turn that carried one).  Walk the file forward: start empty, REPLACE the set on each FIXED block, drop the listed keys on each RELEASED block; the state after the last turn is what you record.
```

#### REC-18 · COMPRESS · −881 chars · risk medium

*File:* `agents/user_input_inspector/prompt.md` · *Section:* **STRICT rules for QUANTITATIVE INPUTS:**

**Why:** Three rules with a justification paragraph each, two of which ('revisions overwrite', 'releases omit') are already stated under Temporal scope and again under D.

**Risk:** OUT OF RANGE is a load-bearing rule (an extraction-only answer must not report an unbuildable number as fine) — the replacement keeps the exact annotation format and the do-not-clamp clause.

**Cut from** `**STRICT rules for QUANTITATIVE INPUTS:**`

**...through** `already matches the parameter: a real-world quantity needing conversion is not yours to judge.`

**Replace with:**

```
Rules:
- At most ONE line per quantity within a design's listing (a multi-design request legitimately repeats a parameter across its sub-lists).
- A revision OVERWRITES its line; a released parameter's line is DROPPED, never annotated.
- **OUT OF RANGE.**  When a line is already in the parameter's own unit, compare it to the range above; if it falls outside, keep the user's value unchanged and append the fact — never correct, clamp or drop it:

      - outerRadius: 160 mm — OUT OF RANGE (allowed [10; 140])

  Only for values already in the parameter's unit; a quantity needing conversion is not yours to judge.
```

#### REC-17 · SCOPE_PER_AGENT · −830 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* <<BSV_ON>> $blade_sections_visualizer / $blade_sections_visualizer_per_agent

**Why:** The shared blurb explains a tool the UII cannot call; the only UII-relevant fact is 'say when the request centres on the sections so the Planner can take the fast path'.

**Risk:** Shared fragments stay intact for the Tool Caller / DCOI / Planner, who actually use or read the visualizer.

**Cut from** `<<BSV_ON>>`

**...through** `<<BSV_OFF>>$blade_sections_visualizer_off<</BSV_OFF>>`

**Replace with:**

```
<<BSV_ON>>## Blade-sections visualizer
The system can render just the three blade cross-sections — much faster than the full 3D propeller.  So when the request centres on the sections (section drawings, or per-section thickness / camber / chord / angle / high-point), say so in your extraction; the Planner can then take the sections-first path.<</BSV_ON>>
```

#### REC-19 · COMPRESS · −822 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## Your utility tools

**Why:** Each tool blurb repeats what the tool schema already says plus what 'User input layout' already said about read_user_inputs not loading images.

**Cut from** `**``read_user_inputs(path)``** (primary read) — call it ONCE with the`

**...through** ```read_input_text(path)`` (one text file, e.g. a specific ``_note.txt``), ``read_image_notes`` (all notes at once).`

**Replace with:**

```
- **``read_user_inputs(path)``** — call ONCE with the ``Input directory:`` path from your hand-off, verbatim.  Returns the text files + every ``_note.txt`` and lists the images; it does not load them.
- **``view_images(paths)``** — load the images you must actually see (paths from that listing); each arrives with its OCR text.  Also use it to re-load an image after bytes were stripped at a hand-off.
- **``ocr_regions(image_path, region_ids)``** — re-read small / faint / garbled callouts at higher resolution; pass every region in ONE call.
- **``write_extraction(path, quantitative, qualitative, intent)``** (mandatory) — write to the ``Extraction output file:`` path verbatim; downstream reads that exact file.  "None specified." for an empty section; the tool adds the headers.
- On demand: ``list_input_files``, ``read_input_text(path)``, ``read_image_notes``.
```

#### REC-20 · COMPRESS · −798 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### Capture, do not filter

**Why:** Two paragraphs arguing for breadth plus a list of examples; the examples alone teach it.

**Cut from** `Your job is to describe what the user supplied as fully and`

**...through** `the right behaviour both when the user asked for a design AND when they asked only for extraction.`

**Replace with:**

```
Record everything the user supplied, including inputs the configurator cannot consume — "500 MPa yield strength", "shiny material", "for cooling fins", a number with no obvious application.  Filtering down to the $parameter_count-parameter set happens downstream at the DCIC / DCII; extracting broadly is exactly what they expect.
```

#### REC-21 · COMPRESS · −775 chars · risk medium

*File:* `agents/user_input_inspector/prompt.md` · *Section:* **HARD RULE — countable features in reference images**

**Why:** An incident patch written at maximum emphasis; the general principle (count discrete features yourself, image beats note, record disagreement) is four lines.

**Risk:** Blade-count mis-reads are a known failure; the replacement keeps count-one-by-one, systematic traversal, image-is-ground-truth and the record-the-discrepancy rule. It drops only the 'HARD RULE' shouting, which competes with the other four bolded HARD/STRICT headers in this prompt.

**Cut from** `**HARD RULE — countable features in reference images must be`

**...through** `visible to downstream agents, and use your image-count value in QUANTITATIVE INPUTS.`

**Replace with:**

```
**Count countable features yourself.**  When a reference image shows discrete elements that map to an integer-count parameter (see the list above), load the image and count them one by one, traversing every instance once — not a one-glance impression — and record the count under the parameter name.  The image, not the note text, is ground truth; when they disagree, use your count and record the discrepancy in QUALITATIVE DESCRIPTIONS.  A countable feature with no matching parameter gets a descriptive real-world label instead.
```

#### REC-22 · MERGE · −768 chars · risk medium

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — the free-form-prose + do-not-announce blocks

**Why:** Two consecutive blocks say the same thing — write prose, don't announce the call, don't duplicate your work product — and the second re-states the mandate already given one block earlier.

**Risk:** Shared by all 6 chain agents. Python source: keep the list-of-strings syntax valid. The 'invoke it in the same response' clause is preserved — that is the anti-halt rule.

**Cut from** `"Write the ``message`` argument as free-form prose: no fixed "`

**...through** `"(one or two lines is plenty).",`

**Replace with:**

```
        "The ``message`` argument is free-form prose — no template, no option "
        "menus — carrying only what the recipient needs (paths their tools "
        "require, what changed and why, authorship of non-user values).  Do "
        "not duplicate your work product there; it is already in your history "
        "and on disk.  Invoke the tool in the same response where you finish "
        "your work; never announce it instead.  Any other text you emit is "
        "private reasoning — keep it to a line or two.",
```

#### REC-23 · COMPRESS · −751 chars · risk medium

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — '### Permission / authorisation issues'

**Why:** An incident patch (agents bouncing back for ritual re-confirmation) written as three paragraphs; the rule is two sentences.

**Risk:** Shared by all 6 chain agents. Keeps the re-read-before-escalating instruction and the _authorisation_sources(hub) call, which is topology-dependent.

**Cut from** `f"### Permission / authorisation issues → {hub} (not "`

**...through** `"NOT for permission questions.",`

**Replace with:**

```
        f"### Permission / authorisation issues → {hub}",
        "Before escalating, re-read the incoming hand-off (and any file it "
        "points to, e.g. extracted_inputs.txt) once more: if it already names "
        "an authorisation that plausibly covers the action — even worded "
        "differently than you expected — act on it.  When one is genuinely "
        f"missing, ESCALATE to the {hub}; " + _authorisation_sources(hub) + "  "
        "CLARIFY back to the previous agent only for data / wording / format "
        "issues it can actually fix.",
```

#### REC-24 · COMPRESS · −719 chars · risk medium

*File:* `DC_prompt_fragments/dc_config/parameters.md` · *Section:* whole fragment

**Why:** Owner's rule: the list stays inline — but the ASCII column padding and per-line headers cost ~45% of it; every name, unit and range is preserved verbatim in a denser layout, and the '% of that section's own chord' gotcha is folded in.

**Risk:** Spliced into 7 agents, so the leverage is 7x — but any transcription slip here is a silent correctness bug. Diff the names/ranges character by character before applying. Denser formatting may also read slightly worse for weaker models.

**Cut from** `### Global / ring
 1. bladeCount         (integer)              — Number of blades [3; 6]`

**...through** `16. outerAngle      (degrees)                   — Angle of attack [2; 25]`

**Replace with:**

```
Ring:  1 bladeCount int [3; 6] · 2 impellerRadius mm [60; 80] · 3 impellerThickness mm, ring wall [1; 5].
(The outer-ring HEIGHT is not a parameter — it is derived automatically to fit the outer blade section.)
Inner section (blade root, r = 4 mm):  4 innerThickness %chord [3; 24] · 5 innerMaxPos tenths-of-chord, int [2; 8] · 6 innerCamber %chord [0; 9] · 7 innerChord mm [3; 11] · 8 innerAngle deg [2; 25].
Middle section:  9 middlePos fraction of blade span, radius = 4 + middlePos·(impellerRadius − 4) mm [0.3; 0.7] · 10 middleChord mm [10; 30] · 11 middleAngle deg [2; 25].
Outer section (blade tip, r = impellerRadius):  12 outerThickness %chord [3; 24] · 13 outerMaxPos tenths-of-chord, int [2; 8] · 14 outerCamber %chord [0; 9] · 15 outerChord mm [10; 30] · 16 outerAngle deg [2; 25].
%chord = percentage of THAT section's own chord, so a pinned chord caps the absolute thickness.
```

#### REC-25 · DELETE · −665 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — '### Do not loop — ESCALATE when stuck'

**Why:** Verbatim duplicate of generic_constraints.md's "DON'T loop: if you are about to call the same tool with the same arguments…", which is spliced into the same prompt a few sections earlier.

**Risk:** Shared by all 6 chain agents. Only safe while the generic_constraints DON'T-loop bullet survives — do not apply this together with a cut that deletes that bullet.

**Cut from** `"### Do not loop — ESCALATE when stuck",`

**...through** `"consult another agent, or ask the user.  Never silently loop.",`

**Replace with:** *(nothing — pure deletion)*

#### REC-28 · DELETE · −651 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## End-of-session feedback message (read-only)

**Why:** Describes a message the agent passively receives at session end and needs no instruction to read; the spliced outro even tells the UII to fold it into "your DH answers", which the UII never writes.

**Risk:** Delete the heading, the $eos_feedback_intro line, the "For you, 'your scope' is…" paragraph, and the $eos_feedback_outro line. Purely informational — no behaviour depends on it during a run.

**Cut from** `## End-of-session feedback message (read-only)`

**...through** `$eos_feedback_outro`

**Replace with:** *(nothing — pure deletion)*

#### REC-26 · COMPRESS · −628 chars · risk low

*File:* `DC_prompt_fragments/dc_config/user_input_types/sketch_handling.md` · *Section:* ### UII responsibility — record the sketch's precision in the extraction

**Why:** Two full example paragraphs plus a closing 'without this, downstream agents…' justification; one compressed example pair states the contract.

**Risk:** Shared fragment (UII, DCII, DCOI) — this subsection is UII-only content the other two carry for nothing.

**Cut from** `The User Input Inspector decides whether a reference image is a sketch and`

**...through** `unmeetable proportions on a rough sketch or discard real proportions on a precise one.`

**Replace with:**

```
The User Input Inspector judges each reference image's precision and states it in the DESIGN INTENT section of ``extracted_inputs.txt``, so downstream agents match with the right strictness — e.g. "ROUGH SKETCH — match qualitatively; asymmetry and wobble are drawing artifacts, not requirements", or "PRECISE SKETCH (measured blade sections) — reproduce the drawn thickness / camber / high-point / chord / angle as closely as the parameters allow".
```

#### REC-27 · COMPRESS · −620 chars · risk low

*File:* `DC_prompt_fragments/dc_config/user_input_types/sketch_handling.md` · *Section:* ### Judging a sketch's precision

**Why:** Four bullets each giving both poles of a spectrum; one sentence per cue conveys the same judgement.

**Risk:** Shared fragment (UII, DCII, DCOI).

**Cut from** `Weigh, per image:
  * **What the user says** — "rough" / "approximate" / "just an idea" points`

**...through** `Assess each image, and each feature within it, on its own.`

**Replace with:**

```
Weigh what the user says ("rough" / "just an idea" vs "to scale" / "match exactly"), line quality (wobbly freehand vs crisp and controlled), image character (dimensions, a scale bar, gridlines or CAD-like geometry = precise), and view type (a whole-propeller doodle is usually rough; a blade top-view or an airfoil profile often carries proportions meant to be reproduced).  One input can be MIXED — judge each image, and each feature in it, on its own.
```

#### REC-29 · COMPRESS · −530 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DON'Ts — the plain-prose channel bullet

**Why:** Fourth statement of one rule: it is also in routing.py's '### Routing is a tool call — MANDATORY', in routing.py's do-not-announce block, and in this prompt's own Forwarding section.

**Risk:** Shared by 8 agents. The rule itself is load-bearing (agents once emitted prose and the pipeline halted) — the replacement keeps it in one sentence, and the full mandate stays in routing.py for every chain agent. Do NOT also delete the routing.py mandate block.

**Cut from** `- DON'T communicate to another agent in plain prose.  The ONLY channel`

**...through** `the Orchestrator's final user-facing wrap-up.`

**Replace with:**

```
- DON'T address another agent in plain prose: the ONLY channel is a routing tool call, and its ``message`` argument IS the hand-off.  Text emitted without one is silently discarded and the pipeline halts.
```

#### REC-30 · COMPRESS · −497 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ### 2. QUALITATIVE DESCRIPTIONS

**Why:** The authorisation-summary rule is stated here, again under DESIGN INTENT, and again under Temporal scope; one statement plus a pointer suffices.

**Cut from** `Free-form prose describing things that cannot be quantised:`

**...through** `the release ("vary the blade count freely, prioritise balance").`

**Replace with:**

```
Free-form prose for what cannot be quantised: shapes, aesthetics, comparisons, subjective impressions, reading hints from an image that resolve to no number.  Be generous.  Summarise here any natural-language authorisation to vary parameters, stating its scope (blanket or parameter-specific?), exclusions and conditions.  A released parameter needs no note — it is simply omitted — unless the user added colour to the release.
```

#### REC-31 · COMPRESS · −490 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — '### How to decide where to route'

**Why:** Four routing branches written as full sentences with parenthetical justification; a four-line decision table is unambiguous and shorter.

**Risk:** Shared by all 6 chain agents. Python source — keep the list-of-strings syntax valid.

**Cut from** `"### How to decide where to route",`

**...through** `f"can fix it, route to the {hub} (ESCALATE).",`

**Replace with:**

```
        "### How to decide where to route",
        f"- Continue the pipeline (the default: no instruction to report back "
        "means continue) and your work succeeded → FORWARD.",
        f"- Told to report back, or told to do X and return → the {hub}.",
        "- Upstream message ambiguous / missing data / has a fixable error → "
        "CLARIFY to the previous agent.",
        f"- Nothing in the chain can fix it → the {hub} (ESCALATE).",
```

#### REC-32 · COMPRESS · −460 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## What to Extract — categorisation rule

**Why:** The 'numeric ≠ matches a parameter' clarification is a separate bolded paragraph restating the QUANTITATIVE bullet it follows.

**Cut from** `Categorise every input you observe (text, paired image notes,`

**...through** `does not match a configurator parameter.  Annotate the user's unit / frame; conversion is the DCIC's job.`

**Replace with:**

```
Sort every input by the NATURE of the data, not by whether it matches a parameter:

  * **QUANTITATIVE** — anything numerical, or that resolves to / can be quantised into a number.  It stays quantitative even when its unit or frame matches no configurator parameter: record the user's unit / frame, conversion is the DCIC's job.
  * **QUALITATIVE** — everything else: prose, adjectives, comparisons, aesthetic or stylistic cues.
```

#### REC-33 · COMPRESS · −443 chars · risk medium

*File:* `DC_prompt_fragments/dc_config/structure.md` · *Section:* whole fragment

**Why:** The middlePos definition appears here in full AND again in the parameter list; a numbered structure list restating the parameter names is largely redundant with the list that follows it.

**Risk:** Shared with the DC Input Creator. middlePos = fraction of blade span from the 4 mm root is a documented past-bug area — the replacement keeps the formula verbatim and the 'not necessarily the midpoint' caveat.

**Cut from** `The propeller consists of:
1. A central hub (the rotating shaft), of FIXED radius 4 mm`

**...through** `the blade tip, at the outer radius (impellerRadius), furthest from the centre.`

**Replace with:**

```
A central hub of FIXED radius 4 mm (the blade root), an outer ring (radius + wall thickness; its height is derived), and identical blades spanning hub → ring.  Each blade has three radial sections: inner at r = 4 mm, middle at r = 4 + middlePos·(impellerRadius − 4) mm — a fraction of the blade SPAN, not necessarily the geometric midpoint — and outer at r = impellerRadius (the tip).
```

#### REC-34 · COMPRESS · −424 chars · risk medium

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — position header block

**Why:** Six lines of prose to state two facts (next agent, previous agent) that the bound routing tools already encode.

**Risk:** Shared by all 6 chain agents. Python source — the replacement changes list construction to conditional expressions; verify it still builds for both next_agent=None and prev_agent=None (the UII under UII-first has prev_agent=None).

**Cut from** `"You are one agent in a decentralised pipeline.  The natural "`

**...through** `f"to go 'back', that means handing control to the {hub}."`

**Replace with:**

```
        "You are one agent in a decentralised pipeline; the flow is:",
        f"  {natural_pipeline()}",
        "",
        f"Your position: **{agent_name}**.",
    ]
    lines.append(
        f"- Next in line: **{next_agent}**." if next_agent
        else f"- You are last; completing normally hands back to the {hub}."
    )
    lines.append(
        f"- Previous in line: **{prev_agent}**." if prev_agent
        else f"- You are first; going 'back' means handing to the {hub}."
```

#### REC-35 · COMPRESS · −423 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* **D. NEVER include historical or annotation-style entries.**

**Why:** Three example bad entries plus a per-section restatement of 'simply OMIT it'; one line covers both sections.

**Cut from** `**D. NEVER include historical or annotation-style entries.**  The`

**...through** `a history of what changed — and is required (see the STRICT rules below).`

**Replace with:**

```
**D. No history, no changelog.**  Never write ``X: 4 (formerly fixed)``, ``X: 4 (unlocked by user)``, or "the user previously wanted Y but now wants Z" — simply OMIT what no longer applies, in both sections.  (An ``OUT OF RANGE`` note is a current fact, not history, and is required.)
```

#### REC-36 · SCOPE_PER_AGENT · −363 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## Qualitative-to-Quantitative Hints ($qualitative_examples)

**Why:** These map adjectives onto parameter directions ("thick blades → upper end of range") — that is the DCIC's translation job; the UII is explicitly told not to invent parameter values.

**Risk:** Fragment stays spliced into the DC Input Creator, which is where the mapping is actually performed. Removing it from the UII also reduces the temptation to pre-resolve qualitative language into numbers.

**Cut from** `## Qualitative-to-Quantitative Hints`

**...through** `$qualitative_examples`

**Replace with:** *(nothing — pure deletion)*

#### REC-37 · COMPRESS · −350 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DON'Ts — chain-only bullets

**Why:** All three duplicate routing.py: the permission-routing block, the ESCALATE-on-repeat-failure rule, and the Receptionist-composes rule.

**Risk:** Shared by 8 agents (chain agents only, via <<CHAIN_ONLY>>).

**Cut from** `- DON'T bounce permission questions back to the previous agent.`

**...through** `never write the user-facing message yourself.`

**Replace with:**

```
- DON'T bounce permission questions backward — authorisations come from the user, the Planner, or the Orchestrator; send them to the Orchestrator.
- DON'T retry a failing step blindly, and DON'T write the user-facing reply yourself — route your content and let the Receptionist compose it.
```

#### REC-38 · COMPRESS · −330 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DON'Ts — invent / fabricate / loop bullets

**Why:** Three real invariants padded with enumerations and reasons; the invariants survive intact at a third of the length.

**Risk:** Shared by 8 agents. The anti-hallucination rule ("don't describe artifacts you did not see produced") is a documented production patch — it is preserved verbatim in spirit as the sourcing test, which is the general principle behind it.

**Cut from** `- DON'T invent tools, scripts, infrastructure, fallback policies,`

**...through** `STOP and ESCALATE — re-reading unchanged input yields nothing new.`

**Replace with:**

```
- DON'T invent tools, files, policies, confidence scores or version numbers that do not exist; if your bound tools can't do it, ESCALATE.
- DON'T state anything you cannot source to a tool result, an agent's history, or something the user literally said — never describe an artifact you did not see produced.
- DON'T loop: about to repeat a tool call with the same arguments? STOP and ESCALATE.
```

#### REC-39 · COMPRESS · −292 chars · risk medium

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — '### Routing is a tool call — MANDATORY'

**Why:** The retired ---ROUTING--- template is warned against in three sentences; one clause does it, and the mandate itself is restated twice inside the same block.

**Risk:** Shared by all 6 chain agents. This is the ONE surviving statement of the routing-is-mandatory invariant after REC-01 and REC-29 — keep the heading and the first sentence exactly as written here.

**Cut from** `"### Routing is a tool call — MANDATORY",`

**...through** `"decision; its ``message`` argument is the hand-off.",`

**Replace with:**

```
        "### Routing is a tool call — MANDATORY",
        "Every response that ends your turn MUST invoke exactly one of the "
        "routing tools above; its ``message`` argument IS the complete "
        "hand-off the recipient sees.  No separate audit block, and no "
        "``---ROUTING---`` / ``---MESSAGE---`` template — that is retired.",
```

#### REC-40 · COMPRESS · −250 chars · risk low

*File:* `agents/shared/prompt_fragments/routing_user_input_inspector_uii_first.md` · *Section:* whole fragment

**Why:** The closing paragraph duplicates the 'You are first in the natural flow' line routing.py already emits, and the tool blurbs restate the routing tools' own schemas.

**Risk:** UII-only fragment (uii_first branch). Its planner_first sibling is untouched.

**Cut from** `- ``call_planner(message)`` — FORWARD to the Planner once`

**...through** `Anything that would otherwise be a "back" routes to the Orchestrator instead.`

**Replace with:**

```
- ``call_planner(message)`` — FORWARD once ``extracted_inputs.txt`` is written and complete.
- ``call_orchestrator(message)`` — normal completion with no Planner follow-up, or ESCALATE.  You are first in the chain, so anything that would be a "back" goes here.
```

#### REC-41 · COMPRESS · −245 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* **C. Multi-design requests.**

**Why:** The Design A / Design B labelling convention is already demonstrated at length under QUANTITATIVE INPUTS.

**Cut from** `**C. Multi-design requests.**  When the user is asking for`

**...through** `long as the user has not contradicted or discarded either.`

**Replace with:**

```
**C. Multi-design requests.**  When the user wants several distinct designs generated and compared, all of them are CURRENT — describe each one's inputs separately under a clear label ("Design A", "Design B") and carry them all forward until contradicted.
```

#### REC-42 · COMPRESS · −131 chars · risk low

*File:* `agents/user_input_inspector/prompt.md` · *Section:* ## Your Role

**Why:** The parenthetical defends the sketch case at three times the length of the rule it qualifies.

**Cut from** `Read the user's input files (text, JSON, images) and extract ALL`

**...through** `is extraction, not invention — see "Sketch handling" below.`

**Replace with:**

```
Read the user's input files (text, JSON, images) and extract ALL design-related information into the three sections below.  Extract only what the user stated — in numbers, in words, or by drawing — and never invent a value.  (Reading a precise drawing's proportions into a clearly-labelled ROUGH estimate is extraction, not invention.)
```

#### REC-43 · COMPRESS · −123 chars · risk low

*File:* `DC_prompt_fragments/dc_config/user_input_types/sketch_handling.md` · *Section:* opening paragraph

**Why:** Says 'precision varies, do not assume rough' twice in four lines.

**Risk:** Shared fragment (UII, DCII, DCOI).

**Cut from** `A "sketch" here is a USER-SUPPLIED reference image that conveys design`

**...through** `to a precise, measured drawing, and match it accordingly.`

**Replace with:**

```
A "sketch" is any USER-SUPPLIED reference image conveying design intent.  Its precision varies — do NOT assume it is rough; place each image on the spectrum from freehand doodle to measured drawing.
```

#### REC-44 · COMPRESS · −57 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* DON'Ts heading

**Why:** Ceremonial heading; the bullets already begin with DON'T.

**Risk:** Shared by 8 agents. Pair with REC-13, which renames the matching DOs heading.

**Cut from** `### What every agent in any design configurator MUST NOT do (DON'Ts)`

**...through** `### What every agent in any design configurator MUST NOT do (DON'Ts)`

**Replace with:**

```
### DON'Ts
```

</details>

**Auditor notes.** ARITHMETIC. Baseline assembled (PLANNER_FIRST=False, DCII on, BSV on, RAG off) ≈ 49,100 chars / 12,286 tok by my reconstruction — within 2% of your measured 12,069, so the section sizes below are trustworthy. Sum of the 44 chars_removed values = 36,201 net. 49,100 − 36,201 ≈ 12,900 chars ≈ 3,250 tok (−73%). chars_removed is NET (original block size minus the replacement I wrote), measured with a script over exact line ranges, not estimated.

WHERE THE BULK SITS. agents/user_input_inspector/prompt.md is 25,677 chars on its own; the shared splices add ~23,400 (sketch_handling 8,606; routing_instructions built by routing.py ~4,840; generic_constraints 3,429; sketch_notes 1,709; parameters 1,609; hard_constraints_dc 1,268; hard_constraints_tools 1,280; BSV 1,049; structure 783; qualitative_examples 303; eos 290). 22 cuts hit the agent's own file (−18,800), 22 hit shared files.

I COULD NOT GET UNDER 3,000 HONESTLY. To go from ~3,250 to ~2,500 you would have to drop one of: (a) the SUGGESTED SECTION SHAPES warm start + SKETCH CROP REGION block (~350 tok) — but that is Phase 3 work built precisely because the DCIC cannot see images; (b) generic_constraints entirely for this agent (~420 tok); (c) the routing.py boilerplate down to a 4-line table (~250 tok more). All three are defensible; none is free. I stopped where cutting further started removing behaviour rather than words.

WHAT I DELIBERATELY DID NOT CUT.
- The 16-parameter list: kept inline per your rule. REC-24 only re-lays it out and folds in the "%chord is of that section's OWN chord" gotcha (a documented past bug). Diff it character-by-character before applying — every name, unit and bracket range is meant to be identical.
- The OUT OF RANGE annotation rule (REC-18): kept with its exact format. It is the only thing stopping an extraction-only answer from reporting an unbuildable number as fine.
- "Routing is a tool call — MANDATORY" (REC-39): the pipeline once halted on prose-without-a-routing-call. That rule currently appears FOUR times (this prompt's Forwarding section, generic_constraints' plain-prose bullet, routing.py's mandate block, routing.py's do-not-announce block). REC-01/29/22 delete three of them and REC-39 keeps one. Do not apply REC-39 as a deletion and do not drop the generic_constraints one-liner as well — the invariant must survive exactly once.
- Anti-hallucination: REC-38 compresses "DON'T fabricate observations" but keeps the sourcing test, which is the general principle behind the incident.
- middlePos semantics (REC-33) and the counting rule (REC-21): both kept, compressed.

DEPENDENCIES BETWEEN CUTS.
- REC-25 (delete routing.py's "Do not loop") is only safe while generic_constraints keeps its DON'T-loop bullet (REC-38 keeps it). Do not apply a future cut that removes both.
- REC-02 requires a code change in agents/shared/prompts.py (_build_slots + FRAGMENT_TO_SLOT) and edits to the DCII and DCOI prompts. If you do not want the code change, apply REC-02's spirit as three in-place compressions instead (rough/precise/always-true → ~980 chars saved rather than 2,182), but then those savings land on all three agents.
- REC-13 and REC-44 are the two halves of the generic_constraints heading rename; apply together or the section headers read inconsistently.
- REC-22/23/25/31/34/39 edit Python string literals in agents/shared/routing.py. Each replacement is written as valid list-of-strings syntax, but REC-34 changes list construction to conditional expressions — smoke-test with next_agent=None and prev_agent=None (the UII under UII-first passes prev_agent=None).

SHARED-FRAGMENT BLAST RADIUS (from grepping all nine prompt.md files):
  generic_constraints, hard_constraints_dc, hard_constraints_tools → 8 agents
  parameters.md → 7 agents · blade_sections_visualizer → 9 agents · eos_feedback_intro → 7
  sketch_handling, sketch_notes → 3 (UII, DCII, DCOI) · structure, qualitative_examples → 2 (UII, DCIC)
  routing.py boilerplate → 6 chain agents
Cuts REC-11, REC-12, REC-17, REC-36 are SCOPE_PER_AGENT: they change only the UII's prompt.md and leave the shared file byte-identical for everyone else — apply these first, they are the lowest-risk 3,300 chars in the set.

ONE THING WORTH A SEPARATE TICKET (not proposed as a cut here). sketch_handling.md carries ~3,200 chars of explicitly UII-ONLY instructions ("### UII responsibility…", "### UII — for a PRECISE blade-section drawing…") that the DC Input Inspector and DC Output Inspector splice and pay for on every turn. The clean fix is the mirror of REC-02: a $sketch_handling_uii fragment referenced only from this prompt. That would cut ~800 tok from each of DCII and DCOI at zero cost to the UII.

FINALLY, A LIVE INCONSISTENCY I FOUND WHILE READING. sketch_handling.md line 60 says "as closely as the 17 parameters allow" and line 65 says "bounded by the 16 parameters", in the same subsection — a leftover from the impellerHeight removal. REC-26 rewrites that text and drops the stale "17"; if you skip REC-26, fix the number anyway.

### 7.x DC Input Inspector — second opinion (36 cuts → ~3,650 tok)

| action | section | −chars | risk | what |
|---|---|---:|---|---|
| SCOPE_PER_AGENT | ## Sketch handling (when the user supplied a sketch) | 10280 | low | $sketch_handling (8,831 ch) + $sketch_notes (1,762 ch) are written FOR the UII (how to read a sketch, what to record in the extraction, warm-start estimates, crop boxes) and for the DCOI's visual comparison; the DCII neither reads sketches routinely nor authors the extraction, so it only needs the one behavioural consequence. |
| COMPRESS | ### 3. Critical engineering check (hard blockers only) | 3080 | low | This section splices the ENTIRE $modelling_notes fragment (2,748 ch) a second time inside a parenthetical, duplicating the "## Modelling Notes" section 5 KB earlier in the same prompt — a cross-reference is enough. |
| COMPRESS | #### 4a. Verbatim entries — the changeability check | 1400 | medium | Same decision procedure, stated once as an ordered precedence rule instead of as nested prose that re-explains the value states already defined in $value_states. |
| COMPRESS | ### 1. Range validation (STRICT — explicit per-paramete | 1340 | medium | The per-parameter check is genuinely load-bearing (real false-APPROVE incident) but is currently argued for over four paragraphs with a worked placeholder example and a repeat of the routing rule. |
| COMPRESS | ## Verdict → routing (STRICT — the tool follows your ve | 1320 | medium | Keeps the full verdict→tool mapping and the range exception, drops the self-check that restates the APPROVE bullet and the "(a recurring failure mode)" commentary. |
| COMPRESS | #### 4b. Real-world-quantity entries | 1270 | low | Three bulleted paragraphs explaining each route plus a fourth paragraph on the failure case collapse to one sentence per route with the same acceptance criteria. |
| COMPRESS | ## Optional reference: user input images | 1170 | low | The five tools already carry their own schema descriptions, and the two paragraphs of when-to-look-at-an-image reasoning compress to one criterion plus the batching rule. |
| COMPRESS | Freeing a LOCKED value | 1090 | medium | The (A)/(B)/(C) source enumeration with per-source commentary collapses to one sentence listing the three sources, keeping the "one is enough" and "how far" rules verbatim in substance. |
| REPLACE_WITH_EXAMPLES | ### Common unit-conversion patterns for this configurat | 1070 | low | A six-item catalogue of conversions the model can derive from the parameter list becomes three canonical examples plus the derivation rule. |
| COMPRESS | ## Your two primary utility tools (IMPORTANT) | 1020 | low | The three enumerated re-read cases reduce to the single rule "re-read when the marker is present or you are not certain", which is what all three say. |
| COMPRESS | routing_instructions() — Routing is a tool call — MANDA | 920 | medium | Three paragraphs (mandate, free-form prose, don't-announce) restate one rule four times, including a retired ``---ROUTING---`` format that no longer exists anywhere. |
| SCOPE_PER_AGENT | ## Hard constraints — tool-specific | 890 | low | The shared fragment's longest block is the attempt-folder write protocol (who opens folders, copy-don't-edit, render reuse), which is addressed to the DCIC/TC/Orchestrator — the DCII writes nothing at all. |
| SCOPE_PER_AGENT | ## Hard constraints — DC-specific | 820 | low | The DCII judges a parameter file, so it needs the "only these parameters exist" rule and the "don't promise unavailable analysis" rule, not the full enumerated catalogue of forbidden mesh operations and formats. |
| COMPRESS | ### 4. Consistency between parameters.json, extracted_i | 700 | low | The parenthetical re-listing the four input tools duplicates REC-08's section three screens earlier, and the "why the extraction is canonical" justification does not change behaviour. |
| COMPRESS | ## Your Role | 690 | low | Each of the five axes is fully specified again under "What to Check", so the role block only needs to name them. |
| COMPRESS | ## Hand-off to the Tool Caller (IMPORTANT) | 640 | low | Keeps the literal two-line contract (load-bearing) and drops the paragraph explaining why the DCIC normally opens a new attempt. |
| COMPRESS | routing_instructions() — Permission / authorisation iss | 520 | low | Two paragraphs restate one rule (read before escalating; permissions go to the hub, not backward) that generic_constraints also carries. |
| COMPRESS | (whole file) | 500 | medium | Keeps all 16 names, types, units and ranges inline (owner's rule) in a tighter column layout, and folds in two known bug sources — %-of-own-chord and the interpolated middle profile — that currently cost prose elsewhere. |
| COMPRESS | ### What every agent in any design configurator MUST NO | 440 | medium | Word-for-word the same rule as routing_instructions' "Routing is a tool call — MANDATORY" section, which every chain agent also receives. |
| COMPRESS | ### 5. Appropriateness — your engineering critique | 410 | low | Same two-branch rule in half the words; the "style is not a blocker" line already appears in section 3. |
| COMPRESS | ### Blade-sections visualizer | 410 | low | Awareness-only fragment spliced into 11 prompts; the mechanism explanation adds nothing for agents that cannot call the tool. |
| COMPRESS | ## Output Format | 400 | low | A five-bullet template immediately disclaimed as "not a fixed template" is better stated as one sentence listing what to cover. |
| DELETE | ### What every agent in any design configurator MAY do  | 383 | medium | Both DOs are stated in full, per-agent and with the correct hub name, by routing_instructions' "How to decide where to route" section that every chain agent already receives. |
| MERGE | ## End-of-session feedback message (read-only) | 360 | low | Inlines and merges $eos_feedback_intro + $eos_feedback_outro with the DCII's own scope sentence, removing two slot round-trips and a sentence of framing. |
| COMPRESS | routing_instructions() — Do not loop — ESCALATE when st | 360 | low | Four sentences explaining why re-reading unchanged input yields nothing collapse to the rule plus its escape hatch. |
| COMPRESS | (opening bullets) | 340 | low | Same facts, tighter, and adds the two documented modelling gotchas (middle-section interpolation, %-of-own-chord) that currently cost prose in several agent prompts. |
| COMPRESS | SOFT TARGET | 290 | low | Drops the two worked phrasings of the "keep near" strength, which the wording already conveys. |
| COMPRESS | ### What every agent in any design configurator MUST NO | 280 | low | Three DON'Ts each explained in a sentence of justification that routing_instructions already gives at length. |
| COMPRESS | ### What every agent in any design configurator MAY do  | 245 | low | Keeps the verbatim-copy invariant and the marker literals, drops the restatement and the why-clause. |
| DELETE | ### What every agent in any design configurator MUST NO | 176 | medium | Verbatim duplicate of routing_instructions' "Do not loop — ESCALATE when stuck" section that every chain agent already receives. |
| COMPRESS | FREE | 166 | low | Same rule without the two-clause explanation of how a value comes to be absent. |
| COMPRESS | ### Hard engineering blockers (parameter combinations t | 134 | low | One blocker wrapped in three sentences of framing; noting that the range check already subsumes it stops agents re-deriving it every cycle. |
| COMPRESS | ### What every agent in any design configurator MUST NO | 129 | low | Keeps both invariants (no invented infrastructure, no unsourced observations — the anti-hallucination patch) with a shorter enumeration. |
| COMPRESS | ### 2. Consistency with the user's stated inputs | 90 | low | Two sentences of explanation reduce to the rule itself. |
| MERGE | ### What every agent in any design configurator MAY do  | 88 | low | Two near-identical DOs merge into one; "act on your inputs" is default model behaviour. |
| COMPRESS | ### What every agent in any design configurator MAY do  | 72 | low | Same rule minus the parenthetical examples, which routing_instructions repeats anyway. |

<details><summary><b>Full text of each second-opinion change</b></summary>

#### REC-01 · SCOPE_PER_AGENT · −10280 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## Sketch handling (when the user supplied a sketch)

**Why:** $sketch_handling (8,831 ch) + $sketch_notes (1,762 ch) are written FOR the UII (how to read a sketch, what to record in the extraction, warm-start estimates, crop boxes) and for the DCOI's visual comparison; the DCII neither reads sketches routinely nor authors the extraction, so it only needs the one behavioural consequence.

**Cut from** `## Sketch handling (when the user supplied a sketch)`

**...through** `$sketch_notes`

**Replace with:**

```
## Reference-image precision
The extraction's DESIGN INTENT states whether a reference image is a ROUGH
sketch — wobble, asymmetry and imprecise lines are drawing artifacts, never
requirements — or a PRECISE / measured drawing, whose drawn proportions ARE
requirements within what the $parameter_count parameters can express.  A blade
count drawn in a top view is authoritative unless the user stated a different
one.  Dimensions the user subordinated to a shape goal are SOFT TARGETS, not
locked values.
```

#### REC-02 · COMPRESS · −3080 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ### 3. Critical engineering check (hard blockers only)

**Why:** This section splices the ENTIRE $modelling_notes fragment (2,748 ch) a second time inside a parenthetical, duplicating the "## Modelling Notes" section 5 KB earlier in the same prompt — a cross-reference is enough.

**Cut from** `### 3. Critical engineering check (hard blockers only)`

**...through** `unconventional" design choices are notes, not blockers.`

**Replace with:**

```
### 3. Engineering feasibility (hard blockers only)
Flag only combinations that make the geometry physically impossible or
self-intersecting — the checklist is the "Hard engineering blockers" list under
"Modelling Notes" above.  Compute each inequality with the ``calculate`` tool,
batched with your range arithmetic.  Style, operating-condition assumptions and
"typical vs unconventional" choices are notes, not blockers.
```

#### REC-03 · COMPRESS · −1400 chars · risk medium

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* #### 4a. Verbatim entries — the changeability check

**Why:** Same decision procedure, stated once as an ordered precedence rule instead of as nested prose that re-explains the value states already defined in $value_states.

**Risk:** Keeps every branch (directive > extraction > discretion, the how-far wording, the out-of-range-directive ESCALATE exception) but drops the restatement of what LOCKED/SOFT/FREE mean; if $value_states is ALSO cut hard (V-01..V-03) verify the SOFT TARGET authorisation survives in one of the two places.

**Cut from** `#### 4a. Verbatim entries — the changeability check`

**...through** `parameter, its value and its range, so the Planner can revise the
   directive.`

**Replace with:**

```
#### 4a. Verbatim entries — was parameters.json allowed to move it?
For each entry whose label names a configurator parameter, resolve authority in
the order **Planner directive > extraction > DCIC discretion**:
  - a Planner directive naming it governs — "change it" authorises the move even
    over a user value; "keep it fixed" LOCKS it even if the user did not;
  - otherwise the move needs a user permission in the hand-off, a DESIGN INTENT
    permission, an ``(unlocked by user)`` mark, or a ``SOFT TARGET`` marker
    (deviation toward its goal is authorised by construction).  With none of
    these the value is LOCKED; a parameter absent from QUANTITATIVE INPUTS was
    never imposed and is the DCIC's free choice.

An authorised move must still be in range, and must respect the directive's
"how far" ("as needed" = smallest viable change; "freely" = as far as the goal
requires).  A LOCKED value moved without authorisation, a directed change
missing, or a clear overshoot → CLARIFY to the DCIC naming the parameter, the
value it must hold and why — a DCIC-fixable slip, not a user escalation;
escalate only if it persists after one CLARIFY.  Exception: if the value it must
hold is itself out of range, no valid set can satisfy the directive — ESCALATE
with the parameter, its value and its range so the Planner can revise it.
```

#### REC-05 · COMPRESS · −1340 chars · risk medium

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ### 1. Range validation (STRICT — explicit per-parameter check)

**Why:** The per-parameter check is genuinely load-bearing (real false-APPROVE incident) but is currently argued for over four paragraphs with a worked placeholder example and a repeat of the routing rule.

**Risk:** Removes the ``<param>=<value>`` worked example and the inline restatement of the user-provided-out-of-range routing split; the split itself survives verbatim in the "Range exception" paragraph of REC-06.

**Cut from** `### 1. Range validation (STRICT — explicit per-parameter check)`

**...through** `it CLARIFYs back to the DCIC, as does any DCIC-chosen one.`

**Replace with:**

```
### 1. Range validation (STRICT)
Compare EVERY one of the $parameter_count values in parameters.json against its
own [min; max], individually, through the ``calculate`` tool.  A blanket "all
values are in bounds" is not acceptable — that shortcut has waved genuinely
out-of-range values through.  The DCIC range-checks its own work; do yours as if
it had not.  Exactly at min or max is fine; strictly outside is a hard FAIL even
when the user asked for it (the generator degenerates on out-of-range input).
Never APPROVE with one outstanding — route it per "Verdict → routing" below.
```

#### REC-06 · COMPRESS · −1320 chars · risk medium

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## Verdict → routing (STRICT — the tool follows your verdict)

**Why:** Keeps the full verdict→tool mapping and the range exception, drops the self-check that restates the APPROVE bullet and the "(a recurring failure mode)" commentary.

**Risk:** Deletes self-check #1 ("if APPROVE the tool MUST be call_tool_caller"), a patch for a real mis-routing failure; the same invariant is kept as "ALWAYS goes to the Tool Caller, never the Orchestrator" inside the APPROVE bullet.

**Cut from** `## Verdict → routing (STRICT — the tool follows your verdict)`

**...through** `single out-of-range value makes APPROVE invalid.`

**Replace with:**

```
## Verdict → routing (the verdict fixes the tool)

  * **APPROVE → ``call_tool_caller``** — every range and feasibility check
    passes and any upstream-directed change reads as authorised and safe.  An
    approved set ALWAYS goes to the Tool Caller, never the Orchestrator; minor
    engineering or style opinions do not block APPROVE.
  * **REVISE → ``call_dc_input_creator``** — anything the DCIC can fix itself: a
    value it generated is out of range; an arithmetic / mapping error or a
    missing / malformed field; a change applied without saying who asked for it;
    a LOCKED or "keep fixed" value moved, or an "as needed" directive clearly
    overshot.  Name the parameter and the reason, never a guessed number.
  * **ESCALATE → ``call_orchestrator``** — a hard blocker needing user input;
    the same problem persisting after one CLARIFY; something infeasible whatever
    the parameters; STRONG grounds for going beyond the Planner's directive; a
    missing ``Parameters file:`` / ``Extracted inputs file:`` line.

Range exception: an out-of-range value the USER literally provided ESCALATES
only when NOTHING authorises moving it.  Any authorisation — a ``SOFT TARGET``
marker, a permission in the hand-off or in DESIGN INTENT, a Planner directive —
makes it a CLARIFY back to the DCIC instead.  An unauthorised change is always a
CLARIFY, never a user escalation.

Before routing, confirm you compared each of the $parameter_count parameters
against its [min; max] individually.
```

#### REC-04 · COMPRESS · −1270 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* #### 4b. Real-world-quantity entries

**Why:** Three bulleted paragraphs explaining each route plus a fourth paragraph on the failure case collapse to one sentence per route with the same acceptance criteria.

**Cut from** `#### 4b. Real-world-quantity entries (label is a real-world quantity, unit does not match`

**...through** `parameters with the conversion / rationale included), not an
Orchestrator escalation.`

**Replace with:**

```
#### 4b. Real-world-quantity entries (a unit that maps to no parameter directly)
The DCIC had to act on these one of three ways and say so in its hand-off:
a documented conversion (quantity, anchor parameter(s), formula, resulting
values — check parameters.json matches it within a margin justified by the
user's precision, the parameter's int/float nature, and any rounding); an
explicit engineering-judgement choice with a plausible rationale; or an explicit
declination with a stated reason.  If parameters.json silently uses a default
and the hand-off never acknowledges the entry → CLARIFY to the DCIC.
```

#### REC-08 · COMPRESS · −1170 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## Optional reference: user input images

**Why:** The five tools already carry their own schema descriptions, and the two paragraphs of when-to-look-at-an-image reasoning compress to one criterion plus the batching rule.

**Cut from** `## Optional reference: user input images`

**...through** `call, not one call each.`

**Replace with:**

```
## Optional: the raw user inputs
Reference images live in ``inputs/input_images/``, each with a paired
``<name>_note.txt``.  Loading one costs turns, so consult it only when you
suspect the extraction misread something the user showed — a count or a design
archetype that disagrees with the drawing.  That is also how you carry out
axis 5.  Tools: ``list_input_files``, ``read_input_text``, ``read_image_notes``,
``view_images``, ``ocr_regions`` (batch every region into ONE call).
```

#### VAL-01 · COMPRESS · −1090 chars · risk medium

*File:* `agents/shared/prompt_fragments/value_states.md` · *Section:* Freeing a LOCKED value

**Why:** The (A)/(B)/(C) source enumeration with per-source commentary collapses to one sentence listing the three sources, keeping the "one is enough" and "how far" rules verbatim in substance.

**Risk:** Shared by Planner, DCIC, DCII, DCOI and the 5-agent Creator; the "one source is enough / no ritual re-confirmation" patch (a real round-trip-waste failure) is preserved, so the regression risk is loss of the explanatory gloss only.

**Cut from** `**Freeing a LOCKED value.**  A LOCKED value may change only with an`

**...through** `/ as much as possible" (or nothing said) = as far as the goal requires,
bounded by range.`

**Replace with:**

```
**Freeing a LOCKED value.**  ONE authorisation is enough, from ANY of: the
incoming hand-off (a user permission — blanket, scoped, or parameter-specific —
or a strategy / recovery directive, including one carried by a CLARIFY bounce);
the extraction's DESIGN INTENT section; or an ``(unlocked by user)`` annotation
on the value's own line.  Never demand a ritual re-confirmation of an
authorisation the hand-off already carries, and never let a line reading
"user-locked" override a current one — that is only the default lock.  How far
it may move follows the wording: "as needed / only if necessary" = the smallest
change that restores viability; "freely" or nothing said = as far as the goal
requires, bounded by range.
```

#### MOD-01 · REPLACE_WITH_EXAMPLES · −1070 chars · risk low

*File:* `DC_prompt_fragments/dc_config/modelling_notes.md` · *Section:* ### Common unit-conversion patterns for this configurator

**Why:** A six-item catalogue of conversions the model can derive from the parameter list becomes three canonical examples plus the derivation rule.

**Cut from** `### Common unit-conversion patterns for this configurator`

**...through** `algebra, OR fall back to engineering judgement with a stated
rationale.`

**Replace with:**

```
### Unit conversions
When QUANTITATIVE INPUTS states a value in a unit that matches no parameter,
derive the conversion from the parameter list plus unit algebra — e.g. mm ↔ %
of THAT section's own chord (thickness / camber / high-point), diameter ↔
``impellerRadius = diameter / 2``, a radial distance ↔
``middlePos = (r − 4) / (impellerRadius − 4)``.  Round where the parameter is an
integer.  If no conversion is defensible, use engineering judgement and say so.
```

#### REC-07 · COMPRESS · −1020 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## Your two primary utility tools (IMPORTANT)

**Why:** The three enumerated re-read cases reduce to the single rule "re-read when the marker is present or you are not certain", which is what all three say.

**Cut from** `## Your two primary utility tools (IMPORTANT)`

**...through** `missing from the hand-off, ESCALATE.`

**Replace with:**

```
## Two files you must read (neither is loaded for you)
The DCIC's hand-off carries a ``Parameters file:`` line and an ``Extracted
inputs file:`` line.  Call ``read_parameters`` and ``read_extracted_inputs``
with those paths verbatim — never a guessed path; if a line is missing,
ESCALATE.  Re-read ``parameters.json`` whenever the hand-off marks it ``(newly
written this cycle)`` or you are not certain your cached copy still matches
disk.  When in doubt, re-read.
```

#### REC-16b · COMPRESS · −920 chars · risk medium

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — Routing is a tool call — MANDATORY

**Why:** Three paragraphs (mandate, free-form prose, don't-announce) restate one rule four times, including a retired ``---ROUTING---`` format that no longer exists anywhere.

**Risk:** This block is the fix for the real "prose without a routing tool call halts the pipeline" failure; the mandate sentence and the "announcing instead of calling halts the pipeline" consequence are both retained. Affects all six chain agents.

**Cut from** `"### Routing is a tool call — MANDATORY",`

**...through** `"(one or two lines is plenty).",`

**Replace with:**

```
        "### Routing is a tool call — MANDATORY",
        "Every response that ends your turn MUST invoke exactly one routing "
        "tool, in the same response where you finish your work.  Its "
        "``message`` argument IS the hand-off and the only text the recipient "
        "sees; announcing a call instead of making it halts the pipeline.  "
        "Write that message as free-form prose — no template, no option "
        "menus — carrying everything the recipient needs (paths their tools "
        "require, what changed and why, authorship of non-user values) and "
        "nothing more.  Keep any ordinary response text to a line or two of "
        "terse reasoning.",
```

#### REC-16 · SCOPE_PER_AGENT · −890 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## Hard constraints — tool-specific

**Why:** The shared fragment's longest block is the attempt-folder write protocol (who opens folders, copy-don't-edit, render reuse), which is addressed to the DCIC/TC/Orchestrator — the DCII writes nothing at all.

**Cut from** `## Hard constraints — tool-specific`

**...through** `$hard_constraints_tools`

**Replace with:**

```
## Hard constraints — tools
- Never guess a path for a read tool: use only the paths a hand-off label gives
  (``Parameters file:`` / ``Extracted inputs file:`` / ``Current attempt:``).
- Route EVERY arithmetic operation — conversions, ratios, range comparisons —
  through the ``calculate`` tool, batching a turn's expressions into ONE call.
- Attempt folders are append-only: never ask for an existing ``parameters.json``
  or mesh to be edited; a new parameter set means a new attempt.
```

#### REC-17 · SCOPE_PER_AGENT · −820 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## Hard constraints — DC-specific

**Why:** The DCII judges a parameter file, so it needs the "only these parameters exist" rule and the "don't promise unavailable analysis" rule, not the full enumerated catalogue of forbidden mesh operations and formats.

**Cut from** `## Hard constraints — DC-specific`

**...through** `$hard_constraints_dc`

**Replace with:**

```
## Hard constraints — DC
- The $parameter_count named parameters are the ONLY design vocabulary: reject
  any invented one (hub_radius, fillet_radius, tip_clearance, any
  "supplemental" parameter).  Geometry changes only by changing those
  parameters and regenerating via DC Input Creator → Tool Caller; there is no
  mesh editing and no mesh post-processing.
- Never endorse analysis the system cannot perform (performance / RPM / thrust /
  flow / CFD, structural / FEA / stress / material), other output formats, other
  camera angles, or higher-resolution renders.
```

#### REC-10 · COMPRESS · −700 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ### 4. Consistency between parameters.json, extracted_inputs.txt, and the user inputs themselves

**Why:** The parenthetical re-listing the four input tools duplicates REC-08's section three screens earlier, and the "why the extraction is canonical" justification does not change behaviour.

**Cut from** `### 4. Consistency between parameters.json, extracted_inputs.txt, and the user inputs themselves`

**...through** `consistency check is different for each:`

**Replace with:**

```
### 4. parameters.json vs extracted_inputs.txt vs the raw user inputs
``extracted_inputs.txt`` is your PRIMARY record of what the user authorised, but
not the sole source of truth: when a QUANTITATIVE entry looks inconsistent with
the QUALITATIVE prose, the hand-off cites a user quantity you cannot find in it,
or a unit is genuinely unclear, go to the raw inputs (tools above) — sparingly.
QUANTITATIVE INPUTS holds two kinds of entry, checked differently:
```

#### REC-09 · COMPRESS · −690 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## Your Role

**Why:** Each of the five axes is fully specified again under "What to Check", so the role block only needs to name them.

**Cut from** `## Your Role`

**...through** `image-rich requests, important quantitative values).`

**Replace with:**

```
## Your Role
You check the ``parameters.json`` the DC Input Creator wrote — you never write or
modify it — and decide whether it may proceed, on five axes detailed under "What
to Check": (1) every value in range, (2) consistency with the user's stated
inputs, (3) engineering feasibility, (4) authorship and authorisation of every
value the user did not set, (5) faithfulness of ``extracted_inputs.txt`` to the
raw user inputs.
```

#### REC-13 · COMPRESS · −640 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## Hand-off to the Tool Caller (IMPORTANT)

**Why:** Keeps the literal two-line contract (load-bearing) and drops the paragraph explaining why the DCIC normally opens a new attempt.

**Cut from** `## Hand-off to the Tool Caller (IMPORTANT)`

**...through** `path lines are needed.`

**Replace with:**

```
## Hand-off to the Tool Caller
When you FORWARD, ``call_tool_caller``'s ``message`` MUST carry both labels with
the absolute paths the DCIC gave you, preserving the marker exactly:

    Current attempt: <same path the DCIC gave you>
    Parameters file (newly written this cycle): <Current attempt>/parameters.json

The TC writes mesh + renders into ``Current attempt:`` and reads the JSON from
``Parameters file:``; the marker tells it any parameters it remembers are stale.
Drop the marker only if the DCIC's hand-off lacked it.  CLARIFY / ESCALATE
messages need no path lines.
```

#### REC-17b · COMPRESS · −520 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — Permission / authorisation issues

**Why:** Two paragraphs restate one rule (read before escalating; permissions go to the hub, not backward) that generic_constraints also carries.

**Cut from** `f"### Permission / authorisation issues → {hub} (not "`

**...through** `"NOT for permission questions.",`

**Replace with:**

```
        f"### Permission / authorisation issues → {hub}",
        "Before escalating, re-read the hand-off (and any file it points to, "
        "e.g. extracted_inputs.txt) once: if it already names an "
        "authorisation that plausibly covers the action, act on it — no "
        "ritual re-confirmation, even if the wording differs from what you "
        f"expected.  If one is truly missing, ESCALATE to the {hub}; "
        + _authorisation_sources(hub) + "  CLARIFY backward only for data / "
        "wording / format issues the previous agent can actually fix.",
```

#### PAR-01 · COMPRESS · −500 chars · risk medium

*File:* `DC_prompt_fragments/dc_config/parameters.md` · *Section:* (whole file)

**Why:** Keeps all 16 names, types, units and ranges inline (owner's rule) in a tighter column layout, and folds in two known bug sources — %-of-own-chord and the interpolated middle profile — that currently cost prose elsewhere.

**Risk:** Shared by 9 prompts; every name/unit/range must be diffed character-by-character before applying — a silently altered bound would be invisible and systemic.

**Cut from** `### Global / ring`

**...through** `16. outerAngle     (degrees)                   — Angle of attack [2; 25]`

**Replace with:**

```
Ranges are inclusive [min; max].  "% of own chord" means percent of THAT
section's own chord, so a pinned chord caps the absolute size.

### Global / ring
 1. bladeCount        int      [3; 6]
 2. impellerRadius    mm       [60; 80]
 3. impellerThickness mm       [1; 5]
(Ring HEIGHT is not a parameter — it is derived to fit the outer blade section.)

### Inner blade section
 4. innerThickness  % of own chord             [3; 24]
 5. innerMaxPos     int, tenths of chord       [2; 8]
 6. innerCamber     % of own chord             [0; 9]
 7. innerChord      mm                         [3; 11]
 8. innerAngle      degrees (angle of attack)  [2; 25]

### Middle blade section (its profile shape is interpolated from inner + outer)
 9. middlePos    fraction of blade span; radius = 4 + middlePos·(impellerRadius − 4) mm, 0 = root (hub, 4 mm), 1 = tip  [0.3; 0.7]
10. middleChord  mm         [10; 30]
11. middleAngle  degrees    [2; 25]

### Outer blade section
12. outerThickness % of own chord        [3; 24]
13. outerMaxPos    int, tenths of chord  [2; 8]
14. outerCamber    % of own chord        [0; 9]
15. outerChord     mm                    [10; 30]
16. outerAngle     degrees               [2; 25]
```

#### GEN-01 · COMPRESS · −440 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent in any design configurator MUST NOT do (DON'Ts)

**Why:** Word-for-word the same rule as routing_instructions' "Routing is a tool call — MANDATORY" section, which every chain agent also receives.

**Risk:** Affects all 10 prompts. Safe only if REC-16b keeps the mandate in routing_instructions; the Receptionist and Orchestrator (non-chain) rely on THIS copy, so do not delete it outright.

**Cut from** `<</CHAIN_ONLY>>- DON'T communicate to another agent in plain prose.  The ONLY channel`

**...through** `Orchestrator's final user-facing wrap-up.`

**Replace with:**

```
<</CHAIN_ONLY>>- DON'T address another agent in plain prose.  The ONLY channel
  is a routing tool call (``call_<agent>``) whose ``message`` IS the hand-off;
  text emitted without one is discarded and the pipeline halts.  (Exceptions:
  the Receptionist's replies to the user and the Orchestrator's wrap-up.)
```

#### REC-11 · COMPRESS · −410 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ### 5. Appropriateness — your engineering critique

**Why:** Same two-branch rule in half the words; the "style is not a blocker" line already appears in section 3.

**Cut from** `### 5. Appropriateness — your engineering critique`

**...through** `Style / "typical vs unconventional" choices are notes, not blockers.`

**Replace with:**

```
### 5. Engineering appropriateness (advisory)
Judge whether the values make engineering sense for the user's intent and flag
known-bad-outcome risks — for free choices and directed values alike.  The
Planner's plan outranks your opinion: a better value still within the directive
→ CLARIFY to the DCIC with your suggestion; only STRONG grounds for going BEYOND
the directive → ESCALATE so the Planner can rule.  Style notes never block.
```

#### BSV-01 · COMPRESS · −410 chars · risk low

*File:* `DC_prompt_fragments/tools_config/blade_sections_visualizer.md` · *Section:* ### Blade-sections visualizer

**Why:** Awareness-only fragment spliced into 11 prompts; the mechanism explanation adds nothing for agents that cannot call the tool.

**Cut from** `### Blade-sections visualizer`

**...through** `and can even be the final deliverable.`

**Replace with:**

```
### Blade-sections visualizer
The Tool Caller can render JUST the three blade cross-sections (Inner / Middle /
Outer, each at its true angle of attack) from an attempt's parameters file, with
no 3D mesh — much faster than the full propeller, so a section-focused request
can be refined, and even delivered, on the sections alone.
```

#### REC-12 · COMPRESS · −400 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## Output Format

**Why:** A five-bullet template immediately disclaimed as "not a fixed template" is better stated as one sentence listing what to cover.

**Cut from** `## Output Format`

**...through** `needed (identify the parameter and the reason, not a guessed
    numeric replacement).`

**Replace with:**

```
## Output format
Put your assessment in the routing tool's ``message`` argument: short plain prose
covering range validation, any real contradiction with the user's requirements,
the authorship / authorisation of upstream-directed changes, hard engineering
blockers, and your recommendation (name the parameter and the reason, never a
guessed replacement number).  No fixed template.
```

#### GEN-02 · DELETE · −383 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent in any design configurator MAY do (DOs)

**Why:** Both DOs are stated in full, per-agent and with the correct hub name, by routing_instructions' "How to decide where to route" section that every chain agent already receives.

**Risk:** The replacement MUST keep the bare ``<<CHAIN_ONLY>>`` opener — its ``<</CHAIN_ONLY>>`` partner is 7 lines further down, and deleting the opener leaves the marker unbalanced so the raw text leaks into every chain agent's prompt.

**Cut from** `<<CHAIN_ONLY>>- DO follow the natural pipeline: when your work succeeds and the`

**...through** `request, still-ambiguous hand-off after one CLARIFY).`

**Replace with:**

```
<<CHAIN_ONLY>>
```

#### REC-14 · MERGE · −360 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ## End-of-session feedback message (read-only)

**Why:** Inlines and merges $eos_feedback_intro + $eos_feedback_outro with the DCII's own scope sentence, removing two slot round-trips and a sentence of framing.

**Cut from** `## End-of-session feedback message (read-only)`

**...through** `$eos_feedback_outro`

**Replace with:**

```
## End-of-session feedback (read-only)
At session end the Orchestrator MAY append ONE ``HumanMessage``
(``name="orchestrator"``) carrying user feedback on YOUR scope — whether your
APPROVEs were sound or let bad parameters through, whether your REVISEs and
ESCALATEs were warranted, and whether your range / locked-value / engineering
checks caught what they should.  Treat it as ground truth in your DH answers.
```

#### REC-18 · COMPRESS · −360 chars · risk low

*File:* `agents/shared/routing.py` · *Section:* routing_instructions() — Do not loop — ESCALATE when stuck

**Why:** Four sentences explaining why re-reading unchanged input yields nothing collapse to the rule plus its escape hatch.

**Cut from** `"### Do not loop — ESCALATE when stuck",`

**...through** `"consult another agent, or ask the user.  Never silently loop.",`

**Replace with:**

```
        "### Do not loop",
        "If you are about to call the same tool with the same arguments you "
        "already used this turn, STOP and ESCALATE to the "
        f"{hub} with a short note on what is ambiguous or missing — never "
        "silently loop.",
```

#### MOD-02 · COMPRESS · −340 chars · risk low

*File:* `DC_prompt_fragments/dc_config/modelling_notes.md` · *Section:* (opening bullets)

**Why:** Same facts, tighter, and adds the two documented modelling gotchas (middle-section interpolation, %-of-own-chord) that currently cost prose in several agent prompts.

**Cut from** `- Blade profiles are NACA-style airfoils parameterised by thickness, camber,`

**...through** `other parameters are floating-point numbers.`

**Replace with:**

```
- Blade profiles are NACA-style airfoils: thickness, camber and high-point
  (max-thickness position in tenths of chord — 3 = 30% from the leading edge).
- ``middlePos`` is a fraction of the BLADE SPAN from the root: actual radius =
  ``4 + middlePos·(impellerRadius − 4)`` mm (hub 4 mm), NOT
  ``middlePos × impellerRadius``.  The middle section has no shape parameters of
  its own — its profile is a weighted blend of inner and outer.
- ``*Thickness`` / ``*Camber`` are % of that section's OWN chord, so a pinned
  chord caps their absolute size.
- bladeCount, innerMaxPos and outerMaxPos are integers; the rest are floats.
```

#### VAL-02 · COMPRESS · −290 chars · risk low

*File:* `agents/shared/prompt_fragments/value_states.md` · *Section:* SOFT TARGET

**Why:** Drops the two worked phrasings of the "keep near" strength, which the wording already conveys.

**Cut from** `- **SOFT TARGET** — a value marked ``SOFT TARGET (goal: …; keep near … if`

**...through** `important" → your choice within range; "prefer X but the shape matters
  more" → use X).`

**Replace with:**

```
- **SOFT TARGET** — a value marked ``SOFT TARGET (goal: …; keep near … if
  free)``.  The goal governs, and the marker itself IS the authorisation to move
  the value within range as far as the goal requires — never justify moving it.
  The stated value settles the parameter only when the goal does not bear on it,
  at the strength the "keep near …" wording gives.
```

#### GEN-03 · COMPRESS · −280 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent in any design configurator MUST NOT do (DON'Ts)

**Why:** Three DON'Ts each explained in a sentence of justification that routing_instructions already gives at length.

**Cut from** `<<CHAIN_ONLY>>- DON'T bounce permission questions back to the previous agent.`

**...through** `never write the user-facing message yourself.`

**Replace with:**

```
<<CHAIN_ONLY>>- DON'T bounce permission questions backward, and DON'T retry a
  failing step blindly — authorisations and repeated failures both go to the
  Orchestrator.
- DON'T write the user-facing reply; route your content and let the
  Receptionist compose the wording.
```

#### GEN-04 · COMPRESS · −245 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent in any design configurator MAY do (DOs)

**Why:** Keeps the verbatim-copy invariant and the marker literals, drops the restatement and the why-clause.

**Cut from** `- DO carry STANDING DIRECTIVES verbatim: if your incoming hand-off`

**...through** `set or change it.`

**Replace with:**

```
- DO reproduce any ``=== STANDING DIRECTIVES (copy verbatim to the next agent)
  ===`` … ``=== END STANDING DIRECTIVES ===`` block from your hand-off UNCHANGED
  in your own — never alter, summarise, re-order or omit it; only the Planner
  may set or change it.
```

#### GEN-05 · DELETE · −176 chars · risk medium

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent in any design configurator MUST NOT do (DON'Ts)

**Why:** Verbatim duplicate of routing_instructions' "Do not loop — ESCALATE when stuck" section that every chain agent already receives.

**Risk:** Affects all 10 prompts; the Receptionist and Orchestrator get routing_receptionist/routing_hub instead of routing_instructions — confirm the anti-loop rule survives for them before applying, or keep this bullet and take REC-18 instead.

**Cut from** `- DON'T loop: if you are about to call the same tool with the same`

**...through** `unchanged input yields nothing new.`

**Replace with:** *(nothing — pure deletion)*

#### VAL-03 · COMPRESS · −166 chars · risk low

*File:* `agents/shared/prompt_fragments/value_states.md` · *Section:* FREE

**Why:** Same rule without the two-clause explanation of how a value comes to be absent.

**Cut from** `- **FREE** — a parameter absent from QUANTITATIVE INPUTS: either the user never`

**...through** `as LOCKED for that cycle.`

**Replace with:**

```
- **FREE** — a parameter absent from QUANTITATIVE INPUTS (never specified, or
  specified and later released — a released value is simply omitted).  The
  system's choice within range.  A qualitative description that must become a
  number is FREE too, unless a directive pins it, which makes it LOCKED for that
  cycle.
```

#### MOD-03 · COMPRESS · −134 chars · risk low

*File:* `DC_prompt_fragments/dc_config/modelling_notes.md` · *Section:* ### Hard engineering blockers (parameter combinations that break the geometry)

**Why:** One blocker wrapped in three sentences of framing; noting that the range check already subsumes it stops agents re-deriving it every cycle.

**Cut from** `### Hard engineering blockers (parameter combinations that break the geometry)`

**...through** `treat any violation as a non-negotiable fail.`

**Replace with:**

```
### Hard engineering blockers
``innerThickness ≤ 0`` or ``outerThickness ≤ 0`` → degenerate blade section
(both ranges start at 3, so an in-range set cannot violate this).  Treat any
other combination that makes the geometry impossible or self-intersecting as a
hard blocker too — physics, not style.
```

#### GEN-06 · COMPRESS · −129 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent in any design configurator MUST NOT do (DON'Ts)

**Why:** Keeps both invariants (no invented infrastructure, no unsourced observations — the anti-hallucination patch) with a shorter enumeration.

**Cut from** `- DON'T invent tools, scripts, infrastructure, fallback policies,`

**...through** `or something the user literally said, do not make it.`

**Replace with:**

```
- DON'T invent tools, files, policies, confidence scores or version numbers
  that do not exist — if your bound tools cannot do it, ESCALATE.
- DON'T state an observation you cannot source to a tool result, an agent's
  history, or something the user literally said.
```

#### REC-15 · COMPRESS · −90 chars · risk low

*File:* `agents/dc_input_inspector/prompt.md` · *Section:* ### 2. Consistency with the user's stated inputs

**Why:** Two sentences of explanation reduce to the rule itself.

**Cut from** `### 2. Consistency with the user's stated inputs`

**...through** `intent or functional requirement.`

**Replace with:**

```
### 2. Consistency with the user's stated inputs
Explicit user values are intentional — never ask for them to be justified.  Flag
only a value that clearly contradicts a STATED design intent or requirement.
```

#### GEN-07 · MERGE · −88 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent in any design configurator MAY do (DOs)

**Why:** Two near-identical DOs merge into one; "act on your inputs" is default model behaviour.

**Cut from** `### What every agent in any design configurator MAY do (DOs)`

**...through** `- DO use only the tools listed for your role; that list is exhaustive.`

**Replace with:**

```
### DOs (every agent)
- DO act only on your hand-off and the files it names, using the paths the
  upstream agent supplied, and only the tools listed for your role.
```

#### GEN-08 · COMPRESS · −72 chars · risk low

*File:* `agents/shared/prompt_fragments/generic_constraints.md` · *Section:* ### What every agent in any design configurator MAY do (DOs)

**Why:** Same rule minus the parenthetical examples, which routing_instructions repeats anyway.

**Cut from** `<</CHAIN_ONLY>>- DO write hand-off messages as free-form prose carrying exactly what`

**...through** `— and nothing more.`

**Replace with:**

```
<</CHAIN_ONLY>>- DO write hand-offs as free-form prose carrying only what the
  recipient needs — the paths their tools require, what changed and why, and the
  true authorship of any non-user-authored value; never relabel one source as
  another.
```

</details>

**Auditor notes.** HOW TO READ chars_removed. Every figure is the ASSEMBLED effect on the DCII's system prompt, not the byte delta in the file. For the four SCOPE_PER_AGENT / slot-replacing cuts (REC-01, REC-16, REC-17, REC-14) the edit itself touches only a slot line in prompt.md, but it removes the whole spliced fragment from this agent: REC-01 alone drops 10,593 chars of $sketch_handling + $sketch_notes. Non-slot cuts are literal. Sum of all non-routing.py cuts = 31,693 chars; baseline assembled = 46,220 chars (11,447 tok), so the result is ~14,500 chars ≈ 3,630 tok. Tightening my replacement prose further lands ~3,400.

I DID NOT REACH 1,000-3,000, and I do not think this agent can without deleting behaviour. The floor is made of four things you have already ruled load-bearing or that the DCII genuinely owns: the 16-parameter list (~270 tok, must stay inline), $value_states (~385 tok — LOCKED/SOFT/FREE is the DCII's whole §4a), the five mandated check axes (~700 tok), and the three shared hard-constraints blocks (~685 tok even after scoping). If you want ~3,000 anyway, the next three cuts get you there and I can spec them: (a) drop the $modelling_notes splice from the DCII entirely and inline the one blocker inequality into §3 (−1,250 ch); (b) reduce $value_states to a 5-line summary FOR THIS AGENT ONLY, since §4a re-derives the precedence anyway (−900 ch); (c) drop $blade_sections_visualizer from the DCII, which cannot call the tool (−330 ch). Together ≈ −620 tok → ~3,000.

BIGGEST SINGLE WIN, take it first: REC-01. 23% of this agent's entire prompt is sketch-reading instructions addressed to the UII (how to judge precision, what to write into extracted_inputs.txt, warm-start SUGGESTED SECTION SHAPES, SKETCH CROP REGION). The DCII reads parameters and an extraction; it consults an image only to check extraction fidelity. Second: REC-02 — $modelling_notes is spliced TWICE into this one prompt (once as its own section, once inside a parenthetical in §3), a straight 2,748-char duplicate.

WHAT I DELIBERATELY DID NOT CUT.
- The per-parameter range mandate (REC-05 keeps "compare EVERY one individually" and "a blanket claim is not acceptable"). That is the direct patch for the DCII's blanket-approve incident and it is the one rule this agent exists to enforce. I cut the worked example and the repeated routing gloss around it, not the rule.
- The subset-restating hazard. REC-03 keeps the ordered precedence Planner directive > extraction > DCIC discretion and the four authorisation sources as a closed OR-list, precisely so a directive naming a SUBSET of parameters cannot be read as revoking authorisation on the others.
- The out-of-range-directive ESCALATE exception (REC-03) and the user-provided-out-of-range routing split (REC-06). Both are the only statement of their invariant; removing either changes behaviour.
- The literal two-line Tool Caller hand-off contract including the "(newly written this cycle)" marker (REC-13) — that string is parsed downstream in spirit and re-typed by the TC.
- "DO answer in English" in generic_constraints — it steers away from an observed default, so it stays.

SHARED-FRAGMENT BLAST RADIUS (say so to the other eight auditors before applying):
- generic_constraints.md (GEN-01..08, −1,707 ch) → all 10 prompts.
- value_states.md (VAL-01..03, −1,546 ch) → Planner, DCIC, DCII, DCOI, 5-agent Creator.
- modelling_notes.md (MOD-01..03, −1,544 ch) → DCIC, DCII, 5-agent Creator.
- parameters.md (PAR-01, −500 ch) → 9 prompts. Diff character-by-character; a silently altered bound is invisible and systemic.
- blade_sections_visualizer.md (BSV-01, −410 ch) → 11 prompts.
- agents/shared/routing.py (REC-16b/17b/18, −1,800 ch) → all six chain agents. NOTE: routing_instructions is filled at .format() time and is NOT part of the 11,447-token measurement, so these three cuts do not move the reported baseline but do cut ~450 tok off the real runtime prompt of six agents.

TWO TRAPS IN THE MECHANICS.
1. GEN-02's replacement is not empty — it is the bare string "<<CHAIN_ONLY>>". The deleted region opens that marker and its "<</CHAIN_ONLY>>" partner is seven lines below; delete the opener and apply_chain_only_filter's regex stops matching, so the literal marker text leaks into every chain agent's prompt.
2. Nothing I propose introduces "{" or "}". prompt.md is run through str.format() after $-substitution, so any literal brace in a replacement must be doubled — check this if you edit my replacement text.

CONFLICT TO RESOLVE: GEN-05 (delete the DON'T-loop bullet) and REC-18 (compress the same rule in routing.py) both target the anti-loop rule. Apply at most one as a DELETE. The Receptionist and Orchestrator do not receive routing_instructions, so if you take GEN-05 they lose the rule entirely — prefer taking REC-18 only, or take GEN-05 knowing the two non-chain agents are covered by their own routing fragments.

I did not audit the 12 bound tool schemas (2,104 tok). Golden rule 9 applies there too: read_parameters / read_extracted_inputs / read_input_text / list_input_files / read_image_notes is five read tools where two or three would do, and the prompt currently spends ~1,000 chars compensating for that overlap (REC-07 + REC-08). Merging list_input_files into read_image_notes, and read_input_text into read_extracted_inputs, would let both of those sections shrink further.
