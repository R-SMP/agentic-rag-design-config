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

## Phrase slots: DC- and tool-specific words inside generic sentences (2026-10)

The generic fragments (`agents/shared/prompt_fragments/` and the 5/3 mirrors)
and every agent prompt body are configurator-agnostic.  Wherever a generic
sentence needs a DC- or tool-specific word, example or statement, it names a
`$slot` whose fragment lives here, in `dc_config/` or `tools_config/`.  Three
rules decide what a fragment holds:

1. **Small and describable.**  A fragment holds only the specific phrase (an
   example in parentheses WITH its parentheses, an example list, a tool name,
   a view list), never the generic sentence around it.  Each one is described
   in the table of its folder's README, so a new configurator can be supported
   by rewriting fragments without reading the agent prompts.
2. **One line per phrase.**  A phrase fragment is written on ONE line.  The
   assembler re-wraps any line such a slot made longer than 80 characters
   (`INLINE_FRAGMENT_SLOTS` and `wrap_inline_lines` in
   `agents/shared/prompts.py`).  A real block (example lines, a whole DC
   section) keeps its lines, and its `$slot` stands alone on its line.
3. **More than one DC tool is itself DC-specific.**  A statement that exists
   only because this DC has two geometry tools / output types (blade-section
   renders vs the full 3D model, "Never both", "Both geometry tools", multi-phase
   precision) is ONE fragment, including its connecting words and its
   `<<BSV_ON>>` / `<<MESH_ON>>` markers.  A single-tool DC empties or rewrites
   that one fragment.

Every fragment has a copy per topology: `X.md` here (topology 7),
`agents/5agent/<folder>/X_5agents.md` and `agents/3agent/<folder>/X_3agents.md`.
A topology that does not use a slot keeps an EMPTY copy: `_build_slots()`
reads every slot in every topology, so a missing file fails the session build
(`warnings_developer.md` W42) and a missing mirror breaks the topology-5/3
MIRROR check.
