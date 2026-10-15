# The design-configurator pack

Everything **specific to one design configurator (DC) or to its tools** lives
in this folder.  The engine (the agents, the tools' wiring, the web app) reads
it on every session build and never writes into it.  Edit files here when
retargeting the multi-agent system at a different DC or swapping out the
tools — the per-agent templates in `agents/<agent_name>/prompt.md` and the
agent classes themselves should stay put.  `DC_PACK_DIR` (`config.py`)
chooses another pack; the default is this folder.

| Path | What it holds |
| --- | --- |
| `fragments/dc/` | Text about the configurator: parameter list, structure, modelling notes, capabilities, examples, … |
| `fragments/tools/` | Text about the bound tools: tool inventory, tool rules, output vocabulary, render-check blocks, … |
| `parameters.json` | The parameters: names in canonical (JSON) order, types, ranges, steps, defaults, groups, and each consumer's wording (slider label/unit, database unit/description).  The one source for the validator, `$parameter_count`, the slider page, the preview check and the database schema (`engine/parameters.py`).  The agents' parameter lists stay hand-written; `smoke_test_parameters.py` checks they agree. |
| `pack.yaml` | The pack's own settings.  `parameter_access`, who sees the parameter list for each agent and topology (full list / names only / through the `dc_params_list` tool / nothing).  It is the default; Workflow Settings › Parameter list access changes cells for the next session (`engine/parameter_access.py`); and `tool_switches` / `tool_settings`, which Workflow Settings value turns each `<<IF:tool:…>>` / `<<IF:setting:…>>` flag on (until the tools get their own files). |
| `assets/` | Images — the parameter primer (`dc_params_primer.png`). |

The engine's own text — the DOs / DON'Ts every agent inherits, the routing
fragments, the pipeline flow — lives in `agents/shared/prompt_fragments/`.

## Which file fills which slot

Every `$slot` the engine offers is listed in `engine/slot_registry.yaml`: its
folder, its kind (`phrase`, `block`, `word`), the Studio section that shows it
and a one-sentence description.  A fragment file is named after its slot, and
its name says where it applies (`engine/pack.py`):

| File | Applies to |
| --- | --- |
| `<slot>.md` | every topology — one text ("linked") |
| `<slot>.t<N>.md` | topology N only — `.t7`, `.t5`, `.t3` ("unlinked") |
| `<slot>@<agent>.md` | that agent's own copy, in every topology |
| `<slot>@<agent>.t<N>.md` | that agent's own copy, in topology N |

The most specific file that exists wins: the agent's own copy if it has one,
else the slot's text for the topology, else the linked text, else the 7-agent
text.  **Editing a linked file changes every topology that uses it**; to
change one topology only, replace `<slot>.md` by `.t7` / `.t5` / `.t3` files
first.

* **An empty file is a decision.**  It resolves to nothing and ends the
  search; deleting it can restore longer text or crash the session build
  (`extra_utilities/warnings_developer.md` W42).  A topology that does not use
  a slot keeps an empty `<slot>.t<N>.md`.
* **No `{` or `}` in any fragment** (W45).
* The loader strips trailing whitespace (both ends for `strip: both` slots).

## Phrase slots: DC- and tool-specific words inside generic sentences

The generic fragments and every agent prompt body are configurator-agnostic.
Wherever a generic sentence needs a DC- or tool-specific word, example or
statement, it names a `$slot` whose text lives here.  Three rules decide what
a fragment holds:

1. **Small and describable.**  A fragment holds only the specific phrase (an
   example in parentheses WITH its parentheses, an example list, a tool name,
   a view list), never the generic sentence around it.  Each one is described
   in its registry entry, so a new configurator can be supported by rewriting
   fragments without reading the agent prompts.
2. **One line per phrase.**  A phrase fragment (`kind: phrase`) is written on
   ONE line.  The assembler re-wraps any line such a slot made longer than 80
   characters (`INLINE_FRAGMENT_SLOTS` and `wrap_inline_lines` in
   `agents/shared/prompts.py`).  A real block (example lines, a whole DC
   section) keeps its lines, and its `$slot` stands alone on its line.
3. **More than one DC tool is itself DC-specific.**  A statement that exists
   only because this DC has two geometry tools / output types (blade-section
   renders vs the full 3D model, "Never both", "Both geometry tools",
   multi-phase precision) is ONE fragment, including its connecting words and
   its `<<IF:tool:…>>` / `<<IF:setting:…>>` markers.  A single-tool DC empties or
   rewrites that one fragment.

## Adding a slot

1. Add its entry to `engine/slot_registry.yaml` (`source: pack`, `folder`,
   `kind`, `section`, `description`).
2. Create `fragments/<folder>/<slot>.md` — or `.t7` / `.t5` / `.t3` files when
   the topologies need different text, with an empty file for a topology that
   does not use it.
3. Reference it as `$<slot>` in the template or fragment that needs it
   (routing fragments are substituted too).

Nothing is registered in Python: the slot map, the phrase list and the reverse
index in `prompts.py` are derived from the registry.

## Fields read by Python rather than spliced (`use: runtime`)

* `render_check_library_trimesh` / `_pyvista` / `_off` — the render + mesh-check
  block the Tool Caller (Design Engineer in topology 3) receives through its
  `{render_check_library_block}` placeholder, chosen by `RENDER_LIBRARY` and
  `MESH_CHECKS`.  A new backend is an engine change (`tools/render_mesh/`,
  `RENDER_LIBRARIES` in `tools/__init__.py`) plus one such field.
* `dc_params_primer_text` — the text sent with the parameter primer image at
  invoke time (`agents/shared/dc_primer.py`); an agent with its own copy gets
  that instead.

## User input types

Each kind of reference input this DC accepts beyond plain text (hand-drawn
sketches, photographs, 2D drawings, CAD screenshots, …) has a pair of slots:
`<type>_handling` (what the input type is and the rules every reasoning agent
follows with one) and `<type>_notes` (operator-curated patterns specific to
this DC).  This DC accepts sketches: `sketch_handling`, `sketch_notes`, plus
`sketch_precision_examples` and `sketch_crop_example`.
