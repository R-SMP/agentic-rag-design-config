# Tool-Specific Prompt Fragments

Edit these files when the SET OF BOUND TOOLS changes — different domain
generators, different render backends, different utility tools.  Each
file contains ONLY the value that gets spliced into the per-agent
templates.

| File | What goes in it | Slots in the per-agent templates |
| --- | --- | --- |
| `tool_inventory.md` | Numbered list of utility tools the Tool Caller is bound to (name, behaviour, what they return, plus any tool-produced metric lists). | `$tool_inventory` |
| `tool_caller_instructions.md` | How the Tool Caller should use its tools, including Tool-Caller-only DOs/DON'Ts (e.g. "call generate_and_render_propeller once — it builds the mesh AND renders/checks it in one call", "call calculate for arithmetic", "do NOT call your utility tools to 'fix' a mesh — ESCALATE instead"). | `$tool_caller_instructions` |
| `tool_caller_capabilities.md` | One-paragraph description of the Tool Caller's bounded capability — used by the Orchestrator's "Agent Capabilities" section. | `$tool_caller_capabilities` |
| `agent_tools_overview.md` | "Agent tools at a glance" — what each agent reads / writes via its bound tools (Orchestrator-facing). | `$agent_tools_overview` |
| `hard_constraints_tools.md` | Tool-related DOs and DON'Ts that apply to **every** agent in the system (no inventing tools, no guessing paths, no calling read tools in a loop, copy paths verbatim).  Tool-Caller-specific tool rules live in `tool_caller_instructions.md`, not here. | `$hard_constraints_tools` |

## Why these are tool-specific (not DC-specific)

A different propeller-mesh generator with the same DC parameters
would change `tool_inventory.md` (different generator name, different
arguments) but leave the DC config alone.  Conversely, swapping the
DC for, say, a turbine wheel keeps the same Grasshopper / Rhino
tooling shape (one merged generate-and-render tool) but rewrites
every file in `dc_config/`.

## How substitution works

Same `$slot_name` mechanism as `dc_config/`.  See
`dc_config/README.md`.

## Phrase, multi-tool and vocabulary slots (2026-10)

The rules are in `../README.md`, "Phrase slots".  "Used in" names the agent
bodies / generic fragments that reference the slot, in any topology.

### Single-tool facts

| File | Kind | Used in | What goes in it | Current propeller value |
| --- | --- | --- | --- | --- |
| `geometry_tool_name.md` | phrase | available_agents.md | Name of the DC tool that generates the geometry and renders it (code-quoted). | ``generate_and_render_propeller`` |
| `geometry_model_filename.md` | phrase | receptionist | File name of the 3D model the geometry tool writes (code-quoted). | ``propeller_mesh.obj`` |
| `render_view_list.md` | phrase | dc_output_inspector, requirements_analyst | The fixed render views the geometry tool produces, in parentheses. | (isometric, top-down, side views) |
| `quality_check_numbers.md` | phrase | available_agents.md, available_agents_planner.md | The geometry tool's quality-check output, as 'the ... numbers'. | the quality-check numbers |
| `quality_check_report.md` | phrase | orchestrator | Name of the geometry tool's quality-check report. | quality-check report |
| `qc_numerics_verdict_rule.md` | phrase | dc_output_inspector, requirements_analyst | Sentence (with <<MESH_ON>> markers) allowing a verdict on quality-check figures alone. | <<MESH_ON>>  Forming a verdict on QC numerics alone is fine; pretending it ca… |
| `mesh_check_role_item.md` | block | dc_output_inspector, requirements_analyst | Inspector role-list item (with <<MESH_ON>> markers) for the quality-check report. | <<MESH_ON>>2. The quality-check report (if available) in the hand-off message… |
| `no_render_fallback_qc.md` | phrase | requirements_analyst | Clause (with <<MESH_ON>> markers) adding the quality-check report to the no-render fallback. (topology 3 only) | <<MESH_ON>> plus the quality-check report<</MESH_ON>> |

### Multi-tool statements (empty for a single-tool DC)

| File | Kind | Used in | What goes in it | Current propeller value |
| --- | --- | --- | --- | --- |
| `roster_sections_tool_sentence.md` | phrase | available_agents.md | Roster sentence (with its <<BSV_ON>> markers) naming the extra sections-only tool; empty for a single-tool DC. | <<BSV_ON>>  It can instead be asked for ``render_blade_sections`` — the three… |
| `roster_tools_clause.md` | phrase | available_agents.md, available_agents_planner.md | Roster clause naming the DC's geometry tools, ending with the main tool's name ('... Or it points <tool>'). | <<BSV_ON>>  It can be asked for ``render_blade_sections`` — the three blade c… |
| `routing_sections_alternative.md` | phrase | routing_orchestrator.md | Hub routing clause (with <<BSV_ON>> markers) offering the sections-only render; empty for a single-tool DC. | <<BSV_ON>>, or render just its blade sections (``render_blade_sections``)<</B… |
| `sections_rerun_case.md` | phrase | routing_dc_output_inspector.md, routing_requirements_analyst.md | Inspector routing: the extra no-design-change case only a sections render creates (leading ', or ...'). | , or a blade-sections render of the CURRENT attempt's existing ``parameters.j… |
| `directive_output_choice.md` | phrase | planner | What a standing directive imposes when geometry must be created, naming the alternative outputs. | to impose the ONE output this phase creates: the blade-section renders, or th… |
| `precision_multi_phase_rule.md` | phrase | planner | Planner rule for runs with more than one precision phase; empty when the DC has one output type. | If the run had MORE THAN ONE precision phase (e.g. the sections, then the ful… |
| `precision_continue_directive_example.md` | block | planner | Example STANDING DIRECTIVES body that moves a precision job to its next phase. | PRECISION JOB — full 3D geometry ONLY.  The blade sections have ⏎         con… |
| `precision_match_subject.md` | phrase | receptionist | What a precision job matches against, naming its possible targets. | sketch (sections and / or the full 3D) |
| `precision_gap_description.md` | phrase | receptionist | What the inspector's fidelity verdict reports, naming this DC's model ceiling. | how closely it matched, and any gap it named as the airfoil-model / geometry … |
| `precision_match_targets.md` | phrase | dc_output_inspector, requirements_analyst | What a precision directive can name as the target to match. | the blade sections, the whole-propeller 3D views, or both in the same job |
| `values_only_excluded_outputs.md` | phrase | planner | The geometry outputs a VALUES ONLY directive excludes (list). (topology 3 only) | no mesh, no 3D renders, and no blade-section renders either |
| `geometry_tools_loading_rule.md` | phrase | design_engineer, tool_caller | Tool-runner sentence: how the geometry tool(s) read the parameters file. | Both geometry tools take the hand-off's ``Parameters file:`` path and read it… |
| `render_type_choice.md` | block | design_engineer, tool_caller | Tool-runner paragraph: which DC tool to call for which output type (BSV only). | <<BSV_ON>>**Render type — the directive decides, not you.**  The standing ⏎ d… |
| `sections_tool_block_full.md` | block | database_handler | Sections-tool block (BSV markers + its fragments) for the Database Handler. | <<BSV_ON>> ⏎ $blade_sections_visualizer ⏎  ⏎ $blade_sections_visualizer_per_a… |
| `sections_tool_block_overlay.md` | block | planner | Sections-tool block (BSV markers + per-agent overlay) for the Planner. | <<BSV_ON>> ⏎ $blade_sections_visualizer_per_agent ⏎ <</BSV_ON>><<BSV_OFF>>$bl… |

### Geometry-editing ban

| File | Kind | Used in | What goes in it | Current propeller value |
| --- | --- | --- | --- | --- |
| `geometry_editing_ban.md` | phrase | planner | Sentence stating which geometry post-processing operations do NOT exist (Planner). | There is NO mesh-editing capability: no boolean unions, welding, remeshing, h… |
| `mesh_editing_operations_actions.md` | phrase | design_engineer, tool_caller | The same operations as verbs ('You cannot ...'). | edit meshes, perform boolean unions, weld vertices, remesh, fill holes, recom… |
| `recommendation_exclusions.md` | phrase | dc_output_inspector, requirements_analyst | What a REVISE recommendation must not contain. | NO mesh-editing steps |

### Examples tied to the tool output

| File | Kind | Used in | What goes in it | Current propeller value |
| --- | --- | --- | --- | --- |
| `observable_fact_questions.md` | phrase | orchestrator | Example user questions about what the system observed or concluded. | "what does the model look like?", "what would you change?", "what did the che… |
| `tool_run_history_contents.md` | phrase | receptionist | What the tool runner's history holds about a run. | what ran + metrics + paths |
| `visual_claim_examples.md` | phrase | dc_output_inspector, requirements_analyst | Example phrases that count as visual claims, in parentheses. | ("the renders show…", "the side view shows…", "the <feature> appears…", "no h… |
| `dh_artefact_reference_examples.md` | phrase | database_handler | Example generic references to an archived artefact, in parentheses. | ("the isometric render", "the saved parameter set") |

### Output vocabulary

| File | Kind | Used in | What goes in it | Current propeller value |
| --- | --- | --- | --- | --- |
| `output_model.md` | phrase | available_agents.md, available_agents_planner.md, dc_input_creator, dc_output_inspector, design_engineer, planner, receptionist, requirements_analyst, routing_orchestrator.md, tool_caller | The kind of geometry model the geometry tool generates. | mesh |
| `output_model_label.md` | phrase | design_engineer, tool_caller | Hand-off label for the generated model file (without the colon). | Mesh file |
| `output_image.md` | phrase | database_handler, dc_input_inspector, dc_output_inspector, design_engineer, planner, receptionist, requirements_analyst, routing_dc_output_inspector.md, routing_requirements_analyst.md, tool_caller | Singular noun for one output image (also used as a modifier: '... paths'). | render |
| `output_images.md` | phrase | available_agents.md, available_agents_planner.md, dc_input_creator, dc_output_inspector, design_engineer, planner, receptionist, requirements_analyst, routing_orchestrator.md, routing_planner.md, tool_caller | Plural noun for the output images the inspector judges. | renders |
| `output_image_caps.md` | phrase | dc_output_inspector, requirements_analyst | Capitalised (emphasised) form of the output image noun. | RENDER |
| `output_images_long.md` | phrase | dc_output_inspector, orchestrator, receptionist, requirements_analyst | The images the geometry tool produces for inspection (long form). | rendered images |
| `output_image_files.md` | phrase | available_agents.md, available_agents_planner.md | The output image files, as named in the agent roster. | rendered PNGs |
| `output_images_label.md` | phrase | dc_output_inspector, design_engineer, requirements_analyst, tool_caller | Hand-off label under which the tool runner lists the output images (without the colon). | Render images |
| `output_produced.md` | phrase | dc_output_inspector, orchestrator, requirements_analyst | Adjective/participle: produced by the geometry tool's imaging step. | rendered |
| `output_action.md` | phrase | dc_input_creator, routing_dc_input_creator_uii_first.md | Verb: produce the output images. | render |
| `output_reaction.md` | phrase | dc_output_inspector | Verb: produce the output images again. | re-render |
| `output_reactions.md` | phrase | dc_output_inspector, requirements_analyst | Verb, 3rd person: produces the output images again. | re-renders |
| `output_action_noun.md` | phrase | receptionist, routing_orchestrator.md | Noun for the act of producing the output images. | rendering |
