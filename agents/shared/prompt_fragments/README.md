# Generic / cross-agent prompt fragments

This folder holds prompt fragments that are **shared by more than one
agent** OR **organisational fragments authored per-agent that belong
to the prompt-fragment library** (rather than to any single
`agents/<name>/prompt.md`).

| File | Scope | Slot syntax |
| --- | --- | --- |
| `generic_constraints.md` | DOs / DON'Ts every agent inherits, regardless of DC or tool. | `$hard_constraints_generic` |
| `routing_receptionist.md` | Receptionist's "which agents can you call" section. | `$routing_receptionist` |
| `routing_orchestrator.md` | Orchestrator's "which agents can you call" section. | `$routing_orchestrator` |
| `routing_planner.md` | Planner's "Available routing tools" subsection (loaded by `routing_instructions(...)` at wiring time, not via `$`-slot). | (loaded by `routing.py`) |
| `routing_user_input_inspector.md` | UII's "Available routing tools" subsection. | (loaded by `routing.py`) |
| `routing_dc_input_creator.md` | DCIC's "Available routing tools" subsection. | (loaded by `routing.py`) |
| `routing_dc_input_inspector.md` | DCII's "Available routing tools" subsection. | (loaded by `routing.py`) |
| `routing_tool_caller.md` | Tool Caller's "Available routing tools" subsection. | (loaded by `routing.py`) |
| `routing_dc_output_inspector.md` | DCOI's "Available routing tools" subsection. | (loaded by `routing.py`) |
| `pipeline_flow_planner_first.md` | Canonical "Normal Pipeline Flow" description used when `PLANNER_FIRST=True`. | `$pipeline_flow` (selected by flag) |
| `pipeline_flow_uii_first.md` | Same but for `PLANNER_FIRST=False` (UII runs before Planner). | `$pipeline_flow` (selected by flag) |
| `routing_planner_planner_first.md` / `routing_planner_uii_first.md` | Planner's "Available routing tools" subsection. The first variant is used when the Planner is first; the second when the UII is first. | (loaded by `routing.py` based on `PLANNER_FIRST`) |
| `routing_user_input_inspector_planner_first.md` / `routing_user_input_inspector_uii_first.md` | UII's "Available routing tools" subsection, dual-variant on `PLANNER_FIRST`. | (loaded by `routing.py`) |
| `routing_dc_input_creator_planner_first.md` / `routing_dc_input_creator_uii_first.md` | DCIC's "Available routing tools" subsection, dual-variant on `PLANNER_FIRST`. | (loaded by `routing.py`) |
| `available_agents.md` | Directory of every agent in the system with role descriptions (used by the Planner). May reference other `$`-slots (e.g. `$parameter_count`, `$tool_inventory`); `_build_template` runs a second pass to resolve them. | `$available_agents` |

**Conditional regions inside fragments and prompts.** Two flags
gate optional content:

- `<<DCII_ONLY>>…<</DCII_ONLY>>` and `<<DCII_OFF>>…<</DCII_OFF>>` —
  resolved against `DC_INSPECTOR_ENABLED`.
- `<<PF_ON>>…<</PF_ON>>` and `<<PF_OFF>>…<</PF_OFF>>` — resolved
  against `PLANNER_FIRST`.

`apply_flag_filters(text)` in `agents/shared/prompts.py` runs both
passes after every `$`-slot substitution.

The chain agents' routing fragments are pulled in at wiring time by
`agents/shared/routing.py:routing_instructions(...)`, which composes
them with the shared decision-rule / loop-prevention / "routing is a
tool call" boilerplate.  The Receptionist and Orchestrator routing
fragments are spliced into their `prompt.md` at import time via the
`$`-slot mechanism in `agents/shared/prompts.py`.

**User-input-type fragments (e.g. how to handle sketches, photos,
or 3D renderings) are DC-specific** — they live under
`DC_prompt_fragments/dc_config/user_input_types/`, not here. This
is because different DCs accept different reference types: a
photo-based DC has no use for sketch-handling rules, and a
sketch-based DC has no use for photo-handling rules.

The DC-specific and tool-specific fragments (parameter list, structure,
modelling notes, capabilities, tool inventory, …) have moved to the
top-level `DC_prompt_fragments/` folder, split into `dc_config/` and
`tools_config/`. Edit those when retargeting the system at a different
design configurator or swapping the bound tools.

Per-agent templates themselves live in `agents/<agent_name>/prompt.md`.
The two placeholder syntaxes (`$slot` for fragment splicing, `{name}`
for runtime values) coexist without colliding.
