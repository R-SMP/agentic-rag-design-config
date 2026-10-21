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
| `fragments/tools/` | Tool text that no one tool owns: the output vocabulary, the texts about the engine's own tools (database search, retrieval, `calculate` …, with their entries in the tool runner's tool list), the tool rules every agent gets, … |
| `tools/<tool>/` | One folder per tool: `tool.yaml` (its name, its kind — `generator`, `helper` or `geometry` —, the role that may call it (a geometry tool has none: the engine calls it, for the generator and the Download buttons), the text the agents read, its outputs, and its settings with their defaults) plus plain Python with no LangChain in it (the contract is `engine/tooling.py`).  The engine loads them, builds the agents' tools and gives each to whichever agent holds its role in the running topology (`engine/pack_tools.py`).  A tool's switch and settings are its `<<IF:tool:…>>` / `<<IF:setting:…>>` flags; Workflow Settings › Tools changes them for the next session (`workflow_settings/tool_settings.json`).  Its `prompts/` folder holds the prompt text it owns — the slots its `tool.yaml` lists under `prompt_slots`, named as in `fragments/` — and `tool_list_entry.md`, its entry in the tool runner's numbered tool list (placed by `list_order`).  Delete a tool's folder and its text goes with it: its slots read empty, and a marked passage about it elsewhere reads as switched off.  A tool lists the environment variables it reads under `secrets` (`{env: NAME, required: true|false, description: …}`): names only, never a value. |
| `parameters.json` | The parameters: names in canonical (JSON) order, types, ranges, steps, defaults, groups, and each consumer's wording (slider label/unit, database unit/description).  The one source for the validator, `$parameter_count`, the slider page, the preview check and the database schema (`engine/parameters.py`).  The agents' parameter lists stay hand-written; `smoke_test_parameters.py` checks they agree.  Names under `retired` were parameters once: a record that still carries one is read without it (the web app's preview check, `propose_attempt`). |
| `pack.yaml` | The pack's own settings.  `parameter_access`, who sees the parameter list for each agent and topology (full list / names only / through the `dc_params_list` tool / nothing).  It is the default; Workflow Settings › Parameter list access changes cells for the next session (`engine/parameter_access.py`).  `render_samples`, the parameter sets the render-compression panel's sample pictures are made from (its Generate samples button, `engine/image_run.py`).  `downloads.geometry_tool`, the geometry tool that rebuilds the model the web app's Download buttons give (or `saved`, the file the run built); Workflow Settings › Tools › Downloads changes it for the next session.  `primer`, the primer's picture (a PNG in `assets/`, or none: the text alone) and, per topology, the agents that get it (`engine/primer.py`, the Studio's Primer page); a setup without it gives the six design agents `assets/dc_params_primer.png`. |
| `assets/` | Images, served at `/pack/assets/`: the primer's picture (`dc_params_primer.png`, named in `pack.yaml`'s `primer`), the Parameters page's group pictures (named in `parameters.json`), and `render_samples/`, the render-compression panel's samples until its Generate samples button makes newer ones. |
| `preview/` | The Parameters page's browser preview, served at `/pack/preview/`: `preview.js` exports `buildModel(params, material)` (the live 3D model) and, optionally, `highlightGroup` (the part the group being edited shapes), `views` (more left-pane views — the propeller's Blade sections), `groupFigures` + `drawGroupFigure` (a live drawing beside a group's picture) and `modelTitle`.  The propeller's runs FEG (`preview/feg/`), which the `feg_geometry` tool also runs under Node.  Without `preview.js` the page offers a generic Preview button instead: the tools' pictures of the slider values, made on the server (`engine/image_run.py`). |

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

A slot a tool owns (`filled_by: tool` in the registry, listed in the tool's
`prompt_slots`) follows the same rules inside that tool's `prompts/` folder.

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

* `render_check_library_trimesh` / `_pyvista` / `_off` (in the generator's
  `prompts/`) — the render + mesh-check block the Tool Caller (Design Engineer
  in topology 3) receives through its `{render_check_library_block}`
  placeholder.  The generator's `tool.yaml` picks it (`runtime_blocks`): the
  `_off` block while `mesh_checks` is off, else the one named after
  `render_library`.  A new backend is a new `render_library` value with its
  branch in `tool.py` plus its `render_check_library_<value>.md` (listed in
  `prompt_slots` and the registry).  A setup none of whose tools declares
  the block gives those agents none (the placeholder is filled with nothing).
* `tool_entry_calculate` / `_read_attempts` / `_new_attempt_parameters` — the
  engine tools' entries in the tool runner's numbered tool list
  (`$tool_inventory`), which the engine builds around the pack tools'
  `tool_list_entry.md` (`engine/pack_tools.tool_list`).
* `attempt_slug_example`, `crop_reuse_example`, `search_query_examples`,
  `parameter_search_example` (without its braces: the engine writes them),
  `dh_stitching_example_answer` / `_paragraph`, `refine_cap_limits`,
  `produced_outputs_examples` (the Sessions Queue's run classifier) and the
  word `output_models` — the configurator's words in the text Python writes
  for the agents (tool descriptions, tool answers, runtime blocks), filled in
  by `agents/shared/pack_text.py` together with the vocabulary those texts
  share with the prompts.
* `app_title` and `manual_entry_text_example` — the web page's own words: the
  app's name (browser tab and page heading) and the example in the
  database-entry form.  `web_app.py` fills `web/index.html`'s `$name` words
  as it serves the page (HTML-escaped) with these and the vocabulary
  (`$dc_name`, `$output_image`); the page's script gets the words it needs
  from `/pack/page.js`.
* `dc_params_primer_text` — the primer's text, sent with its picture at
  invoke time to the agents `pack.yaml`'s `primer` names
  (`agents/shared/dc_primer.py`); an agent with its own copy gets that
  instead.

## What the engine reads from a tool's outputs

* **The model file** — the generator's `outputs.model_file`
  (`propeller_mesh.obj`).  Every place that looks for an attempt's model
  uses this one name: `read_attempts`, the save step, the upload,
  `visualize_3d_model`, the web app's 3D viewer and Download buttons.  With
  it, `model_format` (`obj`: the viewer's loader and the downloads' media
  type) and `up_axis` (`z`: the viewer turns the model upright).  When the
  setup makes no model, the web app shows no 3D viewer and no Download
  buttons (a generator without a model file: TODO F119).
* **Geometry tools** — `kind: geometry`, making the generator's
  `model_format`: one function, `make_model(params) -> GeometryResult`
  (`engine/tooling.py`), never given to an agent.  The generator's
  `geometry_tool` / `fallback_geometry_tool` settings (`type: tool`,
  `tool_kind: geometry`) choose which one builds an attempt's model, and
  `downloads.geometry_tool` in `pack.yaml` which one rebuilds a download.
  The propeller's are `feg_geometry` (FEG) and `rhino_geometry`
  (RhinoCompute).
* **A model instead of code** — a generator or a geometry tool may say
  `backend: openscad` and name an OpenSCAD file in its folder (`model:`);
  the engine runs it (`engine/backends/openscad.py`): every parameter goes
  to OpenSCAD as the model's own setting of that name, `parts` puts a
  setting together from parameters (`End1_Diameter: [End1_Diameter_mm, 0]`),
  `fixed` gives settings the agents never change, `detail` the settings of
  an agent's run and of a download (a generator builds at `agent`, a
  geometry tool at `download`), `timeout` its limit in seconds.  The STL
  becomes the OBJ model file; a generator's pictures are the engine's
  renderer's (`render_isometric` / `_top` / `_side`).  OpenSCAD is
  `OPENSCAD_PATH`, else `openscad` on the PATH; a downloaded package
  installs Debian's `openscad` in its image.
* **Images** — `outputs.images`, one entry per view, under one contract that
  `engine/pack_tools.py` checks when the pack loads:
  * an image of view `V` is the PNG `render_<V>.png`, written into the
    attempt folder the tool is given; a variant `X` of it (blade sections'
    1 mm grid) is `render_<V>_<X>.png`, listed under `variants`;
  * `compression: 3d_render` or `cross_sections` — which shrink strength
    applies before a model sees it (Workflow Settings › Render compression);
  * `default_enabled` — its switch (Workflow Settings › Tools): a view left
    off is not made, not saved and not fetched.
* **`fill_on_save: true|false`** (required when a tool lists images) — may
  the save step (`agents/shared/attempt_renders.py`) ask this tool for an
  image an attempt is missing when it is archived?  A helper is called with
  the attempt's `parameters.json` path as its first argument; a generator
  builds its model if it is absent, else re-renders.
* **`image_note`** (optional, `file.py:function`) — called with an attempt's
  parameters; its text is shown under that attempt's opened images
  (`view_images`).  Blade sections print the values each section was drawn
  from.

"render" in these names — and in the database's `has_renders`,
`retrieve_attempt`'s `<renders>`, the generator's `render()` step — is the
engine's word for "an image a tool made"; the agents read the pack's own
word (`$output_image`).

## User input types

Each kind of reference input this DC accepts beyond plain text (hand-drawn
sketches, photographs, 2D drawings, CAD screenshots, …) has a pair of slots:
`<type>_handling` (what the input type is and the rules every reasoning agent
follows with one) and `<type>_notes` (operator-curated patterns specific to
this DC).  This DC accepts sketches: `sketch_handling`, `sketch_notes`, plus
`sketch_precision_examples` and `sketch_crop_example`.
