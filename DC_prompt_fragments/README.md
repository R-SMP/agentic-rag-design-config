# DC prompt fragments

Top-level home for every prompt fragment that is **specific to the
current design configurator (DC) or to the bound tool set**. Edit
files here when retargeting the multi-agent system at a different DC
or swapping out the tools — the per-agent templates in
`agents/<agent_name>/prompt.md` and the agent classes themselves should
stay put.

| Folder | Scope | Slot syntax |
| --- | --- | --- |
| `dc_config/` | Design-configurator-specific (parameter list, structure, modelling notes, capabilities, …). Edit when retargeting at a new DC. | `$dc_name`, `$parameter_list`, `$dc_structure`, `$capabilities_can`, … |
| `tools_config/` | Tool-specific (utility-tool inventory, tool-related hard constraints, agent-tool overview). Edit when the bound tools change. | `$tool_inventory`, `$tool_caller_instructions`, `$agent_tools_overview`, `$hard_constraints_tools`, … |

The single generic-constraints fragment (DOs / DON'Ts every agent
inherits, regardless of DC or tool) lives separately at
`agents/shared/prompt_fragments/generic_constraints.md`.

## How substitution works

The loader in `agents/shared/prompts.py` reads each file in `dc_config/`
and `tools_config/`, strips trailing whitespace, and substitutes the
content into every per-agent template that names the corresponding
`$slot`. See `dc_config/README.md` for the per-file slot map.
