# Design-Configurator-Specific Prompt Fragments

Edit these files to retarget the multi-agent system at a different design
configurator (DC).  Each file contains ONLY the value that gets spliced
into the generic agent templates — no surrounding prose, no headers
(unless the value itself is a multi-line section), no leading/trailing
whitespace beyond what you actually want in the prompt.

The loader in `agents/shared/prompts.py` reads each file, strips
trailing whitespace, and substitutes the content into every per-agent
template that names the corresponding slot.  Per-agent templates live
in each agent's own folder (`agents/<agent_name>/prompt.md`).

| File | What goes in it | Slots in the per-agent templates |
| --- | --- | --- |
| `name.txt` | Short DC name, e.g. `propeller`. | `$dc_name` |
| `domain_description.txt` | Domain phrase used in agent introductions, e.g. `propeller design configurator system`. | `$domain_description` |
| `parameter_count.txt` | Total number of design parameters, e.g. `17`. | `$parameter_count` |
| `structure.md` | Anatomy of the object the DC produces (rings, blades, sections — for a different DC, replace with that DC's structure). | `$dc_structure` |
| `parameters.md` | The full ordered parameter list, names + units + ranges (LLM-facing prose). | `$parameter_list` |
| `parameter_keys.txt` | Canonical machine-readable key list (one key per line, optional `: int` / `: float` annotation).  Single source of truth used by the runtime validator AND for canonical JSON ordering.  Order MUST match `parameters.md`. | (used at runtime by `DCInputCreator`, not a prompt slot) |
| `modelling_notes.md` | Any DC-specific notes (e.g. NACA airfoils, integer vs float discipline). | `$modelling_notes` |
| `qualitative_examples.md` | Worked examples of "qualitative phrase → numeric direction". | `$qualitative_examples` |
| `visual_inspection_guide.md` | What a correct rendered output looks like (used by the DC Output Inspector). | `$visual_inspection_guide` |
| `capabilities_can.md` | What the system CAN do — bullet list (Receptionist + Orchestrator use this when offering follow-ups). | `$capabilities_can` |
| `capabilities_cannot.md` | What the system CANNOT do — bullet list. | `$capabilities_cannot` |
| `output_file_locations.md` | Where outputs land on disk. | `$output_file_locations` |
| `geometry_modification_rule.md` | Hard rule on how the geometry may be modified. | `$geometry_modification_rule` |
| `invalid_parameter_examples.md` | Examples of parameter names that DON'T exist (anti-hallucination). | `$invalid_parameter_examples` |
| `hard_constraints_dc.md` | DC-specific DOs and DON'Ts (positive + negative reinforcement). | `$hard_constraints_dc` |

User-input-type fragments live in the [`user_input_types/`](user_input_types/README.md)
subfolder. Each accepted reference type for this DC has a
`<type>_handling.md` (definition + how to treat it) and a
`<type>_notes.md` (operator-curated DC-specific patterns).
Currently registered: `sketch_handling.md` (slot
`$sketch_handling`) + `sketch_notes.md` (slot `$sketch_notes`).
See [`user_input_types/README.md`](user_input_types/README.md) for
the convention and how to add new types.

## How substitution works

The per-agent templates use `$slot_name` placeholders (Python's
`string.Template` syntax) for these DC slots.  At import time the
prompts package calls `Template(...).safe_substitute(...)` to fill
them in.  Per-agent runtime placeholders (`{routing_block}`,
`{natural_pipeline}`, `{chain_access_block}`) use the regular
`{name}` style and are filled in with `.format(...)` when the agent
is wired up.

## Adding a new slot

1. Create `X.md` in this folder (or `tools_config/`), plus
   `agents/5agent/<folder>/X_5agents.md` and
   `agents/3agent/<folder>/X_3agents.md` (empty where a topology does not
   use it).  The slot name is the file stem, `$X`.
2. Register it in `agents/shared/prompts.py`: `_build_slots()` and
   `FRAGMENT_TO_SLOT`; a one-line phrase used inside a sentence also goes
   in `INLINE_FRAGMENT_SLOTS` (a vocabulary word that only puts the author's
   own word back does not).
3. Reference it as `$X` in the generic template or fragment that needs it
   (routing fragments are substituted too since 2026-10).
4. Add it to the table below (or to the one in `tools_config/README.md`).

## Phrase and example slots (2026-10)

The rules are in `../README.md`, "Phrase slots".  "Used in" names the agent
bodies / generic fragments that reference the slot, in any topology.

| File | Kind | Used in | What goes in it | Current propeller value |
| --- | --- | --- | --- | --- |
| `past_run_lookup_examples.md` | phrase | receptionist | Example factual questions about an earlier run, in parentheses. | ("what diameter did the last design end up with?", "did the render succeed?") |
| `extraction_only_examples_user.md` | phrase | receptionist | Example user requests that ask only for extraction (Receptionist list). | "what is the number of blades in my sketch?", "extract the dimensions you see… |
| `extraction_only_examples.md` | phrase | orchestrator, planner | Example forwarded requests that ask only for extraction (hub list). | "how many blades are in my sketch?", "what dimensions did you find?", "list m… |
| `non_consumable_input_examples.md` | phrase | requirements_analyst, user_input_inspector | Example inputs the configurator cannot consume (quoted list). | "500 MPa yield strength", "shiny material", "for cooling fins" |
| `quantitative_input_example.md` | block | requirements_analyst, user_input_inspector | Two example QUANTITATIVE INPUTS lines (block). | Radius of propeller: 70 mm ⏎     tip speed: 40 m/s |
| `countable_feature_example.md` | phrase | requirements_analyst, user_input_inspector | A countable feature of this DC, as 'the ... for example'. | the blades for example |
| `stated_count_example.md` | phrase | requirements_analyst, user_input_inspector | A count written beside a drawing, quoted. | "6 blades" |
| `soft_target_example.md` | phrase | requirements_analyst, user_input_inspector | One example extraction line with a SOFT TARGET marker. | Radius of propeller: ~75 mm — SOFT TARGET (goal: match the sketched blade sha… |
| `soft_target_marker_example.md` | phrase | value_states_design_engineer.md | A shorter SOFT TARGET marker example (Design Engineer value states). (topology 3 only) | Radius of propeller: ~75 mm — SOFT TARGET (goal: match the sketched blade sha… |
| `useful_input_images_example.md` | block | user_input_inspector | Worked USEFUL INPUT IMAGES block for one image (block). | sketch_2.png — technical template sheet: the three blade-section profiles ⏎  … |
| `lever_map.md` | block | dc_input_creator, design_engineer | The 'Which lever moves what' section: which parameters change which aspect (block, with heading). | ## Which lever moves what ⏎  ⏎ "Shape" means two different things here, and d… |
| `parameter_level_entry_example.md` | phrase | dc_input_creator, design_engineer | Example of a user quantity that maps directly onto one parameter, in parentheses. | ("average outer ring radius: 70 mm" is ``impellerRadius``) |
| `non_applicable_input_examples.md` | phrase | dc_input_creator, design_engineer | Example entries that do not apply to the configurator, in parentheses. | (a motor RPM, a cost, a date) |
| `shape_gap_example.md` | phrase | dc_output_inspector, requirements_analyst | Example free-form description of a visual shape gap (quoted). | "inner is too thin and its leading edge too pointed; middle camber is shallow… |
| `unlocked_lever_examples.md` | phrase | dc_output_inspector, requirements_analyst | Example unlocked levers that could improve a mismatch. | a section's radial position (``middlePos``) shifting the planform, a chord, o… |
| `sub_resolution_examples.md` | phrase | dc_output_inspector, requirements_analyst | Example quantities the renders cannot resolve, in parentheses. | (sub-millimetre dimensions, percentages with no visible structural manifestat… |
| `prior_finding_citation_example.md` | phrase | dc_output_inspector, requirements_analyst | Example of marking a prior-cycle finding, in parentheses. | ("previous: blade tips clipped the ring → current: clear") |
| `feature_feedback_examples.md` | phrase | dc_output_inspector, requirements_analyst | Example feature / parameter direction feedback, in parentheses. | ("the blade looks too twisted"; "<param X> looks too small / large") |
| `relative_magnitude_examples.md` | phrase | dc_output_inspector, requirements_analyst | Example relative-magnitude requests (quoted list). | "make the inner section roughly twice as thick", "increase the thickness by ~… |
| `ratio_vs_absolute_feedback.md` | block | dc_output_inspector, requirements_analyst | Block: name the quantity (ratio vs absolute size) for this DC's ratio parameters. | **Name the quantity: ratio or absolute size.** ⏎  ⏎ Whenever you ask for a th… |
| `dh_parameter_dump_example.md` | phrase | database_handler | Example of how a parameter-value dump looks, in parentheses. | (often in the form ``bladeCount = 6 — [3,6]``, etc.) |
| `dh_concrete_noun_examples.md` | phrase | database_handler | Example pronoun-to-concrete-noun replacements, in parentheses. | (e.g. "the 5-blade propeller variant" instead of "this one"; "the Receptionis… |
| `dh_parameter_name_example.md` | phrase | database_handler | This DC's parameter naming convention with one example name. | camelCase parameter names like ``bladeCount`` |
| `dh_numeric_fact_example.md` | phrase | database_handler | Example of spelling out a numeric fact, in parentheses. | ("``bladeCount=5`` (five blades)") |
| `dh_structural_marker_examples.md` | phrase | database_handler | Structural markers in agents' answers to preserve, in parentheses. | (camelCase keys, JSON-like notation if Agent A used it) |
