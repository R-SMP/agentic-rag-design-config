# Generic / cross-agent prompt fragments

This folder holds prompt fragments that are **shared by more than one
agent** OR **organisational fragments authored per-agent that belong
to the prompt-fragment library** (rather than to any single
`agents/<name>/prompt.md`).

| File | Scope | Slot syntax |
| --- | --- | --- |
| `generic_constraints.md` | DOs / DON'Ts every agent inherits, regardless of DC or tool. | `$hard_constraints_generic` |
| `routing_receptionist.md` | Receptionist's "which agents can you call" section. | `$routing_receptionist` |
| `routing_orchestrator.md` | The HUB's "which agents can you call" section. One file per team size — this one for the 7-agent Orchestrator, `agents/5agent/prompt_fragments/routing_planner_5agents.md` and `agents/3agent/prompt_fragments/routing_planner_3agents.md` for the Planner, the hub of the 5- and 3-agent teams — behind a single slot that names no team size, so only the running team's file is ever read. | `$routing_hub` |
| `routing_planner.md` | Planner's "Available routing tools" subsection (loaded by `routing_instructions(...)` at wiring time, not via `$`-slot). | (loaded by `routing.py`) |
| `routing_user_input_inspector.md` | UII's "Available routing tools" subsection. | (loaded by `routing.py`) |
| `routing_dc_input_creator.md` | DCIC's "Available routing tools" subsection. | (loaded by `routing.py`) |
| `routing_dc_input_inspector.md` | DCII's "Available routing tools" subsection. | (loaded by `routing.py`) |
| `routing_tool_caller.md` | Tool Caller's "Available routing tools" subsection. | (loaded by `routing.py`) |
| `routing_dc_output_inspector.md` | DCOI's "Available routing tools" subsection. | (loaded by `routing.py`) |
| `pipeline_flow.md` | Canonical "Normal Pipeline Flow" description (the User Input Inspector runs before the Planner); the 5- and 3-agent systems have their own copy. | `$pipeline_flow` |
| `available_agents.md` | Directory of every agent in the system with role descriptions (used by the Planner). May reference other `$`-slots (e.g. `$parameter_count`); `_build_template` runs a second pass to resolve them. | `$available_agents` |

**Configurator-agnostic.**  Nothing in this folder (or in an agent's prompt
body) names the design configurator, its tools or their outputs.  Where a
sentence needs such a word or example it names a `$slot` whose text lives in the pack,
`setups/<setup>/fragments/` — see `setups/<setup>/README.md`, "Phrase slots".  The routing fragments loaded
by `routing.py` get the same `$slot` substitution (and inline re-wrap) since
2026-10.  The same holds for the text the engine writes for the agents in
Python (tool descriptions, tool answers, runtime blocks) since MAS-blueprint
P4a: its words about the configurator are `$names` filled from the pack by
`agents/shared/pack_text.py`; the file names it still carries follow in P4b.

**Conditional regions inside fragments and prompts.** Several flags
gate optional content:

- `<<DCII_ONLY>>…<</DCII_ONLY>>` and `<<DCII_OFF>>…<</DCII_OFF>>` —
  resolved against `DC_INSPECTOR_ENABLED`.
- `<<IF:flag>>…<</IF:flag>>` / `<<IFNOT:flag>>…<</IFNOT:flag>>` — kept when
  the flag is on (IF) or off (IFNOT); a line the removal leaves empty
  disappears with it.  The pack's flags, `tool:<tool>` and
  `setting:<tool>.<name>`, are declared in `setups/<setup>/pack.yaml`
  (`engine/pack_flags.py`) and live only in the pack's fragments; the
  per-agent `param_list` / `param_ranges` come from the parameter-access
  table.  The generic files carry no pack flag.
- `<<HAS_DBA>>…<</HAS_DBA>>` — **per-agent**, kept only for agents that
  have `database_search` access.
- `<<CHAIN_ONLY>>…<</CHAIN_ONLY>>` — **per-agent**, stripped for the two
  user-facing agents (Receptionist, Orchestrator) and kept for the six
  chain agents.

`apply_flag_filters(text)` in `agents/shared/prompts.py` runs the global
(DCII / PF / BSV) passes; the per-agent `<<HAS_DBA>>` and `<<CHAIN_ONLY>>`
filters run in `_build_template` (they need the agent identity). All run
after every `$`-slot substitution.

The chain agents' routing fragments are pulled in at wiring time by
`agents/shared/routing.py:routing_instructions(...)`, which composes
them with the shared decision-rule / loop-prevention / "routing is a
tool call" boilerplate.  The Receptionist and Orchestrator routing
fragments are spliced into their `prompt.md` at import time via the
`$`-slot mechanism in `agents/shared/prompts.py`.

**User-input-type fragments (e.g. how to handle sketches, photos,
or 3D renderings) are DC-specific** — they live in the pack
(`setups/<setup>/fragments/dc/sketch_*.md`), not here. This
is because different DCs accept different reference types: a
photo-based DC has no use for sketch-handling rules, and a
sketch-based DC has no use for photo-handling rules.

The DC-specific and tool-specific fragments (parameter list, structure,
modelling notes, capabilities, tool inventory, …) live in the
design-configurator pack, `setups/<setup>/fragments/`, split into `dc/` and
`tools/`. Edit those when retargeting the system at a different
design configurator or swapping the bound tools.

Per-agent templates themselves live in `agents/<agent_name>/prompt.md`.
The two placeholder syntaxes (`$slot` for fragment splicing, `{name}`
for runtime values) coexist without colliding.
