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

1. Create a new file in this folder (or `tools_config/`).
2. Add it to the loader in `agents/shared/prompts.py`.
3. Reference it as `$your_new_slot` in any generic template that
   needs it.
