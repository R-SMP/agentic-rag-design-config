# Tool-Specific Prompt Fragments

Edit these files when the SET OF BOUND TOOLS changes — different domain
generators, different render backends, different utility tools.  Each
file contains ONLY the value that gets spliced into the per-agent
templates.

| File | What goes in it | Slots in the per-agent templates |
| --- | --- | --- |
| `tool_inventory.md` | Numbered list of utility tools the Tool Caller is bound to (name, behaviour, what they return, plus any tool-produced metric lists). | `$tool_inventory` |
| `tool_caller_instructions.md` | How the Tool Caller should chain its tools, including Tool-Caller-only DOs/DON'Ts (e.g. "call generate_propeller_mesh first, capture the path, pass it to render_and_check_mesh", "call calculate for arithmetic", "do NOT call your utility tools to 'fix' a mesh — ESCALATE instead"). | `$tool_caller_instructions` |
| `tool_caller_capabilities.md` | One-paragraph description of the Tool Caller's bounded capability — used by the Orchestrator's "Agent Capabilities" section. | `$tool_caller_capabilities` |
| `agent_tools_overview.md` | "Agent tools at a glance" — what each agent reads / writes via its bound tools (Orchestrator-facing). | `$agent_tools_overview` |
| `hard_constraints_tools.md` | Tool-related DOs and DON'Ts that apply to **every** agent in the system (no inventing tools, no guessing paths, no calling read tools in a loop, copy paths verbatim).  Tool-Caller-specific tool rules live in `tool_caller_instructions.md`, not here. | `$hard_constraints_tools` |

## Why these are tool-specific (not DC-specific)

A different propeller-mesh generator with the same DC parameters
would change `tool_inventory.md` (different generator name, different
arguments) but leave the DC config alone.  Conversely, swapping the
DC for, say, a turbine wheel keeps the same Grasshopper / Rhino
tooling shape (one generator, one render-and-check) but rewrites
every file in `dc_config/`.

## How substitution works

Same `$slot_name` mechanism as `dc_config/`.  See
`dc_config/README.md`.
