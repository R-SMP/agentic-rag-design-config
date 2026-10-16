# MAS Blueprint — a multi-agent system you set up for your own design configurator

**Proposal v1 — 2026-10-14, revision 1 the same day** (§0A: the Studio becomes a hosted web
app).  Written from a design review of the owner's concept, with the owner's decisions
recorded in §1.  This is the brief for the coding session that will build it.

MAS = multi-agent system.  DC = design configurator (the parametric model the agents
drive — today, the propeller).  "Pack" = the one folder that holds everything specific to
one DC.

---

## 0. Where this starts and what must not move

| Branch | Role | Rule |
|---|---|---|
| `main` (`3c11296`) | The propeller system as it is today. | Stays as is. |
| `MAS-generalized-v2` (`9dbb3e1`) | The propeller system with every DC/tool phrase moved out of the generic prompts into 68 `$slot` fragments; assembled prompts identical to `main` except 31 line re-wraps. | Stays as is. |
| **`MAS-blueprint`** (new, from `MAS-generalized-v2`) | Where this proposal is built. | All work happens here. |
| `MT-web-deploy` | The LIVE Railway deploy branch (every push redeploys). | Never commit or push to it. |

Publishing the blueprint as a separate GitHub *template repository* with clean history is a
later step (§12), not part of this work.

---

## 0A. Revision 1 (2026-10-14): a hosted Studio (option A); hosted runs later (option C)

**What changed.**  The Studio is no longer only a local app: it becomes a **web app reached
through a URL**.  Its landing page has three large buttons:

1. **Use the Propeller Configurator** — opens the ready-made example (the propeller
   deployment run by the owner; invite code as today).
2. **Create your own** — opens the Studio, blank or starting from the propeller example.
3. **Import a setup** — upload a setup file made earlier with the Studio.

The Studio offers two downloads:

* **Setup file** — the configurator alone (the `dc_pack`, §4.1) as one versioned file.
  It is the Studio's save format: upload it with button 3 to continue editing.
* **Full package** — engine + pack, ready to push to a private repo and deploy.

**What is in scope now (option A) and what is not.**

| | Now (A) | Later (C) |
|---|---|---|
| Edit, preview prompts, static Validate, download setup file / full package | yes | yes |
| "Import a setup" | opens the setup **in the Studio** (edit, validate, view prompts, re-download) | also **runs** it on the page |
| Running a configurator on the hosted site | only the propeller example (button 1) | setups whose tools are all **remote** (HTTP endpoint or RhinoCompute URL hosted by the user), with the user's own LLM API key |
| User Python executed on the hosted server | **never** | **never** (only the engine runs; remote tools are called over HTTP) |

"Open in Codespaces" / "Deploy to Railway" one-click buttons (option B) are **not** planned.

**Why the line is drawn there.**  A setup contains the user's Python tools.  Running them on
the hosted server would let uploaded code read the server's secrets and reach other users,
would need every configurator's dependencies installed on one server (the propeller alone
needs OSMesa, Node, trimesh, pyrender, the Rhino libraries), and would need isolated sessions
for many users (today `web_app.py` holds one in-process session, single worker — W13, F22).
Option C avoids executing user code by restricting hosted runs to remote tools; it still
needs the multi-user work (F22) and a bring-your-own-key policy, so it comes after A.

**Consequences for this brief** (each section below is updated accordingly):

* **One Studio, two modes.**  The same Studio code runs **hosted** (the default) or
  **locally** (`python -m studio`).  Hosted mode never imports or runs pack tools: Validate is
  static plus prompt assembly, and "Test tool" is disabled with a note.  Local mode adds "Test
  tool", the full offline checks with the user's tools, and the git steps.
* **No secrets in the hosted Studio.**  It only lists which secrets each tool needs; values
  are entered in the user's own `.env` / deployment variables after download.
* **Saving.**  No accounts in A: the setup file is the save format, plus an autosave of the
  draft in the browser's local storage (best effort; the user is told to download).
* **D8 adapted.**  Hosted: "Validate" + "Download setup file" + "Download full package".  The
  former "Prepare for GitHub" steps (§9) move into the full package as a local command
  (`python -m studio prepare`), run on the user's machine.
* **Setup file format.**  A zip of the pack with `pack.yaml: pack_format` and the engine
  version that wrote it; never secrets; tool Python files are included and flagged as code.
  Importing an older format runs the pack migrations (§4.1).  Size and file-type limits on
  upload; the server stores nothing after the browser session.
* **Hosting.**  The Studio is deployed as its own service (not inside the propeller app),
  holding no engine secrets (no LLM, database or R2 keys) — nothing in it is worth stealing.

---

## 1. Decisions already taken by the owner

| # | Question | Decision |
|---|---|---|
| D1 | Where does DC-specific content live? | **One "DC pack" folder.** The engine reads it at runtime; the setup app edits only this folder. |
| D2 | Where does the setup app run? | ~~A separate local app, never deployed.~~ **Revised (§0A): a hosted web app with a landing page (propeller example / create your own / import a setup); the same code also runs locally.**  Hosted runs of imported setups: later, remote tools only (option C). |
| D3 | Examples shipped | **Propeller only** (as the example pack). |
| D4 | Branch | New branch **`MAS-blueprint` from `MAS-generalized-v2`**; `main` and `MAS-generalized-v2` untouched. |
| D5 | User tool format | **Plain Python function + a manifest.** No LangChain in user code; generator tools return a structured result. |
| D6 | Topologies in the fragment editor | **Three columns (3-agent left, 5-agent middle, 7-agent right), one row per fragment**, shared rows aligned across columns, an **explicit link icon** per shared row (§6.3). |
| D7 | Where tool text may go in a prompt | **Fixed named sections** per agent.  TODO: also allow "anywhere". |
| D8 | Final buttons | **Two separate buttons: "Validate" and "Prepare for GitHub".**  Revised (§0A): hosted = "Validate", "Download setup file", "Download full package"; "Prepare for GitHub" becomes a local command inside the full package. |
| D9 | Live preview in the web app | **Optional, two levels**: a generic server-side "Preview" (runs the generator, shows its images) for every DC; an instant in-browser preview only if the pack ships one (the propeller does). |
| D10 | Editing agents / topologies | **Not in v1** (TODO). |
| D11 | AI drafting of fields | **Not in v1** — TODO + developer notes (§12). |

---

## 2. The user journey (refined)

*(Revised by §0A.)*

1. Open the Studio's URL.  Landing page: **Use the Propeller Configurator** / **Create your
   own** / **Import a setup**.
2. "Create your own" → choose **"Start from the propeller example"** or **"Start blank"**.
   Blank = every field empty, the propeller value shown beside it as reference.
   (Working locally instead: clone, Python 3.13, `pip install -r requirements.txt`,
   `python -m studio` → `http://localhost:8600`.)
5. Fill the sections in order (§6.1): identity → parameters → configurator description →
   outputs & vocabulary → tools → examples → agent access → settings & secrets.
6. Inspect the result in the **Prompt viewer** (flowchart → click an agent → full prompt).
7. Press **Validate** until it is green (hosted: static checks + prompt assembly).
8. **Download the setup file** (to continue later via "Import a setup") and/or **the full
   package**.
9. Locally, in the unpacked full package: fill `.env`, run `python -m studio prepare`
   (tool test runs, offline checks, git hygiene, first commit, `DEPLOY.md`), create the
   private repo, push, deploy on Railway (or elsewhere).
10. Later: import the setup file in the Studio → edit → Validate → download → replace
    `dc_pack/` in the repo → commit → push → redeploy.  Engine updates from the blueprint are
    pulled with `git pull upstream MAS-blueprint`; they never touch the pack (§4.1).

---

## 3. Critique of the original concept, and the fixes

| # | Gap in the concept | Fix in this proposal |
|---|---|---|
| C1 | **The DC is not only in the prompts.**  The parameter set alone has six hand-synced copies: `DC_prompt_fragments/dc_config/parameter_keys.txt`, `parameters.md`, `web_app._PREVIEW_PARAM_SPEC`, the slider list in `web/app.js` (~line 5879) plus a key list (~line 1040), `extra_utilities/db_design/populate_dc_parameter_schemas.py`, and the `dc_parameter_schemas` table.  Also DC-specific: the in-browser 3D preview (`web/feg/*.js`: blade, NACA, ring), the OBJ viewer (`web/viewer.js`), the render-view registry (`agents/shared/attempt_views.py`), the geometry/render tools (`tools/generate_mesh`, `render_mesh`, `render_blade_sections`), DC settings in the generic `workflow_settings/settings.py`, the parameter primer image (`agents/shared/dc_primer.py`), and the Dockerfile's system packages. | Everything DC-specific moves into the pack (§4.2 lists every item and its new home); the parameter set gets ONE spec (§4.4). |
| C2 | **"DONE generates the code"** makes re-editing and engine upgrades painful. | Data-driven runtime: the engine reads the pack every session, as `prompts.py` already reads fragments.  The buttons only validate and prepare git (§8, §9). |
| C3 | **No upgrade path.** | User content confined to `dc_pack/` + `.env`; the engine never writes into the pack; the pack carries a `pack_format` version and the Studio migrates old packs (§4.1). |
| C4 | **"Drop a Python file" has no contract.**  The pipeline depends on what the generator returns: model file, images for the inspector, quality numbers.  Today that is a prose convention (agents copy paths under a `Render images:` label). | A tool contract (§5): manifest + plain function; generators return a structured `GeneratorResult`; the engine writes labels, attempt records, uploads. |
| C5 | **Tools bound to agents** don't survive topologies (the Tool Caller does not exist in topology 3). | Tools bind to **roles**, mapped to agents per topology by the existing `agents/shared/agent_roles.py` (§5.4). |
| C6 | **Too many fields**: ~110 DC/tool slots on `MAS-generalized-v2`, stored in 148 files plus 263 topology-5/3 mirror files. | A slot registry with required/optional, empty-safe flags, grouping, the propeller value beside every field, "where used" previews; AI drafting later (§6, §12). |
| C7 | **Grammar coupling**: a phrase slot sits inside a generic sentence ("a factual lookup `$past_run_lookup_examples` or …"); empty or wrongly-shaped text breaks the sentence. | Each slot declares its *kind* and whether it may be empty; the editor shows every sentence it lands in, live (§6.4). |
| C8 | **Tool-specific settings** (`BLADE_SECTIONS_VISUALIZER_ENABLED`, `MESH_CHECKS`, `RENDER_LIBRARY`, `GEOMETRY_BACKEND`, `ATTEMPT_VIEW_*`) live in the generic settings, and the prompt markers `<<BSV_ON>>` / `<<MESH_ON>>` are named after propeller tools. | Tools declare their own settings and flags; one generic marker syntax `<<IF:flag>>…<</IF:flag>>` (§4.5). |
| C9 | **Secrets and deployment** are implicit. | Each tool declares the secrets it needs; the Studio writes them only to `.env`; "Prepare for GitHub" generates `DEPLOY.md` with every variable to set (§9). |
| C10 | **Python-side DC text** is still in code: hub feedback instructions, runtime blocks, tool descriptions, the `Render images:` label in `agents/shared/routing_tools.py`, `user_inputs_tool.py`, the topology `tool_text.py` overlays, and the Receptionist's runtime block title "Confirmed render files produced this cycle" (`receptionist.py`).  (TODO F106 on `MAS-generalized-v2`.) | Moved into slots / vocabulary in Phase 4 (§10).  Done in P4a (the words) and P4b (the file names), 2026-10-16. |
| C11 | **Publishing**: this repo's history contains propeller material (sessions, training images, the Grasshopper file `tools/generate_mesh/Propeller_Raul_V1.2.gh` — check its ownership before any public release). | Template repo with clean history later (§12). |

---

## 4. Architecture

### 4.1 Engine vs pack

```
<repo>/
  agents/  tools/  web/  web_app.py  workflow_settings/ ...   ENGINE (owned by the blueprint)
  engine/slot_registry.yaml                                   every slot the engine offers (§4.3)
  studio/                                                     the local setup app (not deployed)
  dc_pack/                                                    EVERYTHING DC-specific (owned by the user)
    pack.yaml            identity, pack_format, flags, agent parameter access, vocabulary
    parameters.json      the parameter spec (§4.4)
    fragments/           one .md per slot (+ topology / role overrides, §4.3)
    tools/<tool>/        tool.yaml + tool.py (+ requirements.txt, apt.txt, assets)
    assets/              primer image, profile images, example inputs
    preview/             optional in-browser preview module (JS)   [propeller: today's web/feg]
    examples/            example queries, benchmark decks (optional)
  .env                   secrets — local only, git-ignored
```

* The engine **never writes** into `dc_pack/` at runtime; only the Studio does.
* `pack.yaml: pack_format: 1`.  When the engine adds or renames a slot, it bumps the format
  and ships a migration the Studio applies (new slots appear as "new — please fill").
* Only one pack is active (`DC_PACK_DIR`, default `dc_pack/`).  The propeller example ships
  as `dc_pack/` on the branch (D3); "Start blank" moves it to `examples/propeller_pack/`
  (kept for reference) and creates an empty pack.

### 4.2 Inventory: what moves into the pack

| Layer | Today (on `MAS-generalized-v2`) | In the pack |
|---|---|---|
| DC/tool prompt text | `DC_prompt_fragments/dc_config/*`, `tools_config/*`, `agents/5agent/{dc_config,tools_config}`, `agents/3agent/{…}` | `fragments/` |
| Parameter set | the six copies listed in C1 | `parameters.json` (single source) |
| Generator + render tools | `tools/generate_mesh/`, `tools/render_mesh/`, `tools/render_blade_sections/`, `tools/__init__.py` wiring | `tools/<tool>/` plugins |
| Tool descriptions (LLM schema) | docstrings + `agents/topology{3,5}/tool_text.py` overlays | `tool.yaml` (+ per-topology variants) |
| Render views | `agents/shared/attempt_views.py` (`render_isometric.png`, …) | declared in the generator's manifest (`outputs.images`) |
| DC settings | `BLADE_SECTIONS_VISUALIZER_ENABLED`, `MESH_CHECKS`, `RENDER_LIBRARY`, `GEOMETRY_BACKEND`, `ATTEMPT_VIEW_*`, `DC_PARAMS_PRIMER_ENABLED` | tool/pack settings (§4.5) |
| Live preview | `web/feg/*.js`, `/api/preview_mesh`, `/api/download_geometry` | `preview/` (optional) + generic server preview |
| Parameters view (sliders) | hard-coded in `web/app.js` | generated from `parameters.json` |
| 3D viewer | `web/viewer.js` (OBJ only) | engine; picks a loader by `outputs.model_format` (obj/glb/none) |
| Primer / profile images | `DC_prompt_fragments/dc_config/images/`, `web/images/` | `assets/` |
| DB parameter schema seed | `populate_dc_parameter_schemas.py` | engine seeds from `parameters.json` at startup (§4.4) |
| Dependencies | `requirements.txt` (trimesh, pyrender, pyvista, rhino3dm, compute-rhino3d, DracoPy), Dockerfile apt list (OSMesa, Node) | per-tool `requirements.txt` / `apt.txt`, merged by "Prepare" |
| Secrets | `RHINO_COMPUTE_URL`, `RHINO_COMPUTE_API_KEY` in `config.py` | declared in the tool manifest |
| Propeller-only tests & tools | `smoke_test_ring_height.py`, `propeller_studio`, benchmark decks | `dc_pack/tests/`, `examples/` |

### 4.3 The slot registry (engine-owned, one file)

Today a slot is registered in four places (`_build_slots`, `FRAGMENT_TO_SLOT`,
`INLINE_FRAGMENT_SLOTS`, the README tables).  Replace them with
`engine/slot_registry.yaml`; `prompts.py`, the Studio and the README tables all read it.

```yaml
past_run_lookup_examples:
  section: examples             # Studio section (§6.1)
  folder: dc                    # dc | tools  (kept for the pack layout)
  kind: phrase                  # phrase (one line, inline) | block (multi-line, own line) | word (vocabulary)
  required: true
  empty_ok: false               # may an empty value ship?  false => Validate fails on empty
  topologies: [7, 5, 3]         # which columns show the row
  scoped_by_role: false         # true => one value per role (hard_constraints_dc, parameters, …)
  label: "Example questions about an earlier run"
  description: >
    Two or three questions a user might ask about a previous design, in parentheses,
    quoted.  The first should name a property of YOUR configurator's output.
  example: '("what diameter did the last design end up with?", "did the render succeed?")'
  depends_on: null              # e.g. "generators>1", "flag:mesh_checks"
  shared_with: null             # TODO (§12): reuse one value for several slots
```

**Resolution** (most specific first): `(role, topology)` → `(role)` → `(topology)` → base.
Pack files: `fragments/<slot>.md` (linked / base), `fragments/<slot>.t5.md`
(topology override), `fragments/<slot>@<role>.md` (role-scoped),
`fragments/<slot>@<role>.t3.md`.  The Studio's link icon (§6.3) is exactly
"override files exist or not".

**Keep the safety rules that exist today**: every slot resolves to a file or to "" (no
`FileNotFoundError` — W42); no `{` or `}` in any fragment (W45); a phrase slot stays one
line and is re-wrapped by the assembler (`INLINE_FRAGMENT_SLOTS` / `wrap_inline_lines`,
already on `MAS-generalized-v2`); a word slot never triggers a re-wrap.

### 4.4 The parameter spec — single source of truth

`dc_pack/parameters.json` (JSON Schema shipped as `engine/schemas/parameters.schema.json`):

```json
{
  "schema_version": 2,
  "groups": [{"id": "ring", "label": "General / ring"}, {"id": "inner", "label": "Inner blade section"}],
  "parameters": [
    {"name": "bladeCount", "type": "int", "min": 3, "max": 6, "default": 3, "step": 1,
     "unit": "", "group": "ring", "label": "Blade Count",
     "description": "Number of blades.",
     "prompt_notes": "Integer only."}
  ]
}
```

Generated / read from it (no more hand-synced copies): the canonical key list and types
(today `parameter_keys.txt`), `$parameter_count`, the parameter list given to agents (today
`parameters.md` — generated in three variants: *full* (names, types, units, ranges, notes),
*names + units*, *names only*), the runtime validator, the web sliders, the preview
validator, the `dc_params_list` tool output, `param_rank` (parameter search), and the DB
seed.  **Any change to names, types or ranges bumps `schema_version`**; the engine seeds a new
`dc_parameter_schemas` version at startup and retires removed parameters (the current seeder
already does this — move its logic into the engine).  Hand-written prose can be appended per
parameter (`prompt_notes`) and as a free block (the `modelling_notes` slot).

**Import/export**: JSON upload, CSV paste (name, type, min, max, default, unit,
description), or the table editor.

### 4.5 Flags and conditional text

Today: `<<BSV_ON>>`, `<<BSV_OFF>>`, `<<MESH_ON>>`, `<<MESH_OFF>>` (propeller-named) next to
generic ones (`<<RAG_ON>>`, `<<HAS_DBA>>`, `<<DCII_ONLY>>`, `<<PF_ON>>`, `<<CHAIN_ONLY>>`,
`<<CAN_SEE>>`, …).

Proposal: one generic syntax for pack flags, `<<IF:flag>>…<</IF:flag>>` and
`<<IFNOT:flag>>…<</IFNOT:flag>>`, where `flag` is:

* `tool:<name>` — the tool is enabled this session (replaces BSV);
* `setting:<tool>.<name>` — a boolean tool setting (replaces MESH, e.g. `setting:generate.quality_checks`);
* `generators>1` — more than one generator tool enabled (the multi-tool statements);
* engine flags keep their current markers.

Tool settings are declared in `tool.yaml` and appear in Workflow Settings under the tool's
name, read fresh per session exactly like today's settings.  Keep `<<BSV_ON>>` / `<<MESH_ON>>`
as aliases during migration so prompts stay identical.

The whole-line rule added on `MAS-generalized-v2` (a `<<MESH_ON>>` region alone on a line
disappears with its line) generalises to every `IF` region.

### 4.6 Per-agent access to the parameter list

A per-role setting with four states (mutually exclusive, as the owner specified):

| State | Meaning | Propeller today |
|---|---|---|
| `inline_full` | full list in the system prompt | DC Input Creator, DC Input Inspector, Tool Caller |
| `inline_names` | names (+units) only in the prompt | DC Output Inspector (`DCOI_KNOWS_PARAMS_RANGES` off) |
| `tool` | no list in the prompt; the `dc_params_list` tool returns it | Planner, Orchestrator, Receptionist |
| `none` | neither | User Input Inspector (`UII_PARAMETER_LIST_ENABLED` off) |

Stored in `pack.yaml: parameter_access: {role: state}`.  The "when to call it" sentence of
the tool is per role (today `_USE_BY_AGENT` in `agents/shared/dc_params_tool.py`) → a
role-scoped slot.  This replaces `UII_PARAMETER_LIST_ENABLED`, `DCOI_KNOWS_PARAMS_RANGES`
and the hard-coded bindings in the agent classes.  Checked on `MAS-generalized-v2`: inline
`$parameter_list` in the DC Input Creator, DC Input Inspector, Tool Caller, Design Engineer,
DC Output Inspector and Requirements Analyst bodies (the inspectors through a scoped copy
whose ranges are switched by `DCOI_KNOWS_PARAMS_RANGES`); the UII only under
`UII_PARAMETER_LIST_ENABLED`; `dc_params_list` bound in the Planner, Planner5, Planner3,
Orchestrator and Receptionist classes.  The migration must reproduce today's prompts exactly.

### 4.7 Output vocabulary and hand-off labels

The 13 vocabulary slots on `MAS-generalized-v2` (`$output_model` = mesh,
`$output_images` = renders, `$output_image` = render, `$output_images_label` = Render images,
…) stay word slots.  Two improvements:

* The Studio fills the inflected forms from one noun with simple rules (plural +s,
  caps, past participle), each editable, each shown in two real sentences (§6.4).
* The labels the tool runner writes (`Mesh file:`, `Render images:`) are produced by the
  **engine** from `GeneratorResult` (§5.3), so agents no longer copy paths by hand, and the
  Python-side copies (C10) read the same vocabulary.

---

## 5. Tools

### 5.1 Kinds

| Kind | What it is | Default role | Propeller |
|---|---|---|---|
| `generator` | builds the design from the attempt's parameters and produces outputs for inspection; exactly one is primary | tool runner | `generate_and_render_propeller` |
| `alt_generator` | a second output type (enables the multi-tool statements, `generators>1`) | tool runner | `render_blade_sections` |
| `helper` | a pure function the agents may call (arithmetic, lookups, conversions) | any | — (`calculate` is engine-generic) |
| `inspection` | works on images / outputs | output inspector | — (`view_images`, OCR are engine-generic) |

Engine-generic tools stay in the engine: routing, `calculate`, `view_images`, OCR,
`write_extraction`, `new_attempt_parameters`, `read_attempts`, the database tools,
`visualize_3d_model` / `propose_attempt` (to be renamed — F105 on `MAS-generalized-v2`).

### 5.2 The manifest — `dc_pack/tools/<name>/tool.yaml`

```yaml
name: generate_and_render_propeller      # LLM-facing tool name (snake_case, unique)
display_name: Propeller Configurator     # flowchart / log label (today @tool_active)
kind: generator
entrypoint: tool.py:generate             # module:function
description: |                           # the tool schema description the LLM sees
  Generate the propeller 3D geometry from an attempt's own parameters.json, …
description_by_topology: {}              # optional per-topology variants (today tool_text.py)
roles: [tool_runner]                     # §5.4
prompt_texts:                            # §5.5 — text inserted into fixed sections
  tool_runner:
    usage: "…"                           # section: "How to use your configurator tools"
    constraints: "…"                     # section: "Hard constraints — tools"
outputs:
  model_format: obj                      # obj | glb | stl | step | none
  images:                                # views the inspector receives
    - {view: isometric, file: render_isometric.png, default_enabled: true}
    - {view: top,       file: render_top.png,       default_enabled: true}
    - {view: side,      file: render_side.png,      default_enabled: false}
  metrics: true                          # returns quality-check numbers
settings:
  - {name: quality_checks, type: bool, default: false, description: "Run mesh quality checks"}
  - {name: backend, type: enum, values: [feg, rhino], default: feg, description: "Geometry backend"}
secrets:
  - {env: RHINO_COMPUTE_URL, required: false, description: "RhinoCompute server URL"}
  - {env: RHINO_COMPUTE_API_KEY, required: false, description: "RhinoCompute API key"}
dependencies:
  pip: [trimesh>=4.0.0, pyrender>=0.1.45, compute-rhino3d>=0.12.0, rhino3dm>=8.0.0, DracoPy>=0.4.0]
  apt: [libgl1, libglu1-mesa, libosmesa6, nodejs, npm]
timeout_s: 180
```

### 5.3 The Python contract — no LangChain in user code

```python
from mas.tooling import GeneratorInput, GeneratorResult, ImageOut

def generate(inp: GeneratorInput) -> GeneratorResult:
    # inp.params      : dict, already validated and typed against parameters.json
    # inp.attempt_dir : Path, the attempt folder to write into
    # inp.settings    : dict of this tool's settings (manifest), read fresh
    # inp.secret(name): reads a declared secret from the environment
    ...
    return GeneratorResult(
        model_files=[inp.attempt_dir / "propeller_mesh.obj"],
        images=[ImageOut(path=..., view="isometric")],
        metrics={"watertight": True, "volume_mm3": 1234.5},
        warnings=[],
        summary="Saved mesh (12 345 vertices, 4 parts, backend feg).",
    )
```

The engine owns everything around it: the LLM-facing signature (`parameters_path` only, as
today), path validation (today `_validate_output_dir` / `_read_param_record` in
`generate_mesh.py`), reading and validating the record, reuse of an existing output
(append-only), the timeout, error capture, the text returned to the LLM (summary + the
labelled lists in the vocabulary of §4.7), the attempt record, the R2 upload and the
flowchart "tool active" label.  Helpers are plain functions with type hints; the engine
builds their schema from the hints and the manifest.

**Adapters** (templates the "New tool" window offers, so users do not start from nothing):

* **RhinoCompute + Grasshopper** — upload the `.gh`, map each Grasshopper input to a
  parameter, name the output mesh; reuses today's Draco decoding in `generate_mesh.py`.
* **Python function** — any local Python code.
* **Node script** — like today's FEG export (`tools/generate_mesh/feg_export.mjs`).
* **HTTP endpoint** — POST the parameters, receive files/URLs.

### 5.4 Binding by role

Roles are the seven-agent roles plus the Database Handler: `receptionist`, `hub`,
`planner`, `input_extractor` (UII), `parameter_author` (DCIC), `parameter_checker` (DCII),
`tool_runner` (TC), `output_inspector` (DCOI), `database_handler`.  The engine maps a role to
the agent that holds it in the running topology via `agents/shared/agent_roles.py` (e.g.
`tool_runner` → Design Engineer in topology 3).  This replaces the hard-coded tool lists in
the agent classes (e.g. `ToolCaller.__init__` building `utility_tools`).  Planned TODO F102
(editable role map) fits naturally later.

### 5.5 Fixed insertion sections (D7)

Every agent body gets a small set of named sections, filled by concatenating the texts of
all tools bound to that role (in tool order):

| Section slot | Heading in the prompt | Typical content |
|---|---|---|
| `$tools_usage_<role>` | "How to use your configurator tools" | when to call which tool, what to pass |
| `$tools_constraints_<role>` | inside "Hard constraints — tools" | what the tool cannot do (e.g. the mesh-editing ban) |
| `$tools_reporting_<role>` | "Reporting tool results" | what to put in the hand-off |

Empty sections disappear with their heading.  Phase 3 must move today's propeller tool
texts into these sections **without** changing the assembled prompts, or show the owner every
difference for approval.  TODO: "insert anywhere".

**As built (P3d, 2026-10-16).**  The propeller's tool text did not move under new headings:
it moved, unchanged, into the tools' own folders (`dc_pack/tools/<tool>/prompts/`, listed in
each `tool.yaml` under `prompt_slots`), so all 357 prompts stayed byte-identical.  The one
section built from the tools is the tool runner's numbered tool list (`$tool_inventory`),
assembled from each tool's `tool_list_entry.md`.  The three headings above remain an option
for later.

### 5.6 Testing a tool in the Studio

**Local mode only (§0A)** — the hosted Studio never runs pack code; there the button is
disabled with "available after download: `python -m studio`".  "Test tool" runs the entrypoint **in a subprocess** with the parameter defaults (or a chosen
example set), with the declared settings and secrets, and shows: import errors,
missing dependencies, the timing, the returned summary, the images, the metrics, and any
mismatch between the manifest and what was produced (e.g. a declared view missing).

---

## 6. The Studio

### 6.1 Sections, in order

| # | Section | Fields (examples) | Required? |
|---|---|---|---|
| 1 | Identity | DC name (`dc_name`), domain description | yes |
| 2 | Parameters | table / JSON / CSV (§4.4) | yes |
| 3 | Configurator description | structure (`dc_structure`), modelling notes, lever map, qualitative examples, invalid-parameter examples, capabilities can / cannot, hard constraints (per role) | partly |
| 4 | Outputs & vocabulary | the 13 word slots, render views, visual inspection guide, precision targets | yes |
| 5 | Tools | list + "New tool" (§6.5) | ≥1 generator |
| 6 | Examples | the ~25 example phrase slots (extraction-only questions, soft-target line, shape-gap example, …) | mostly |
| 7 | User input types | sketch handling / notes (per accepted input type) | optional |
| 8 | Agent access | parameter access matrix (§4.6), tool ↔ role overview | yes (defaults) |
| 9 | Settings & secrets | tool settings defaults; LLM keys, DB, R2, tool secrets → `.env` only | partly |
| 10 | Prompt viewer | §6.6 | — |
| 11 | Validate | §8 | — |
| 12 | Prepare for GitHub | §9 | — |

Progress bar per section; a section turns green when its required fields pass validation.

### 6.2 Field types

* **word** — single word or short noun phrase (vocabulary).  Small input.
* **phrase** — one line, inline in a sentence.  Single-line input; line breaks are refused.
* **block** — multi-line Markdown.  Text area with a monospaced preview.
* **structured** — parameters, tools, access matrix: tables / forms, never free text.

### 6.3 The 3-column topology grid (owner's design, D6)

* Columns: **3-agent (left), 5-agent (middle), 7-agent (right)**.  Rows: one per fragment
  (per role for role-scoped fragments; the row label shows the role and, per column, the
  agent that holds it — e.g. "tool runner: Design Engineer | Tool Caller | Tool Caller").
* A fragment that exists in only some topologies shows only in those columns.
* A fragment shared by two or three topologies appears **in-line on the same row**.
* **Link icon** per shared row:
  * *Linked* (default): editing any column and pressing Save updates all linked columns —
    they are identical.
  * Click the chain → *unlinked*: from then on each column saves on its own, and the row gets
    a **coloured outline** across the columns.
  * Click again → re-link: the Studio asks which column's text to keep for all.
* Rows whose propeller example already differs between topologies (e.g. the render-type
  paragraph: "route back" vs "hand back to the DC Input Creator") start unlinked.
* Storage: linked = only `fragments/<slot>.md`; unlinked = `<slot>.t3.md` / `.t5.md` /
  `.t7.md` (§4.3).

### 6.4 What each field shows (how to tell the user what to enter)

For every field, next to the input:

1. **Label + one-sentence description** from the registry ("Two or three questions a user
   might ask about a previous design, in parentheses").
2. **The propeller value** as grey reference text, with a "copy example" button.
3. **Where it lands** — every sentence in every assembled prompt where the slot appears,
   rendered live with the current value highlighted, per agent and topology ("Receptionist
   (7, 5, 3): *When the user asks about an earlier run — a factual lookup **(…)** or what
   the system observed …*").  Computed by the engine's assembler with sentinel values, the
   technique already used by `extra_utilities/prompt_pdf/provenance.py`.
4. **Shape hints**: "one line", "starts with a comma", "in parentheses", "plural noun".
5. **Live checks**: braces, line breaks in a phrase, an unknown `$`, length vs the example,
   "empty is not allowed here".
6. **Conditional visibility**: multi-tool fragments are hidden while only one generator
   exists; mesh-check fragments while no generator declares metrics.

### 6.5 "New tool" overlay

Fields: name, display name, kind, adapter (§5.3), entrypoint file (drop zone), description
(schema text, per-topology variants optional), roles (checkboxes; shows the agent per
topology), prompt texts per role and section (§5.5) with the same "where it lands" preview,
outputs (model format, image views), settings, secrets, dependencies (pip / apt / Node),
timeout, and a **Test tool** button (§5.6).  Saving writes `dc_pack/tools/<name>/`.

### 6.6 Prompt viewer

* Flowchart per topology (reuse the agent flowchart graphics already in `web/app.js`).
* A **settings bar** (topology, RAG, each tool enabled, each tool setting, Planner-first, DC
  Input Inspector on/off, …) — prompts depend on settings; 17 combinations were needed to
  verify `MAS-generalized-v2`.
* Click an agent → overlay with the full assembled prompt, **coloured by origin**: generic
  engine text, DC fragment, tool text, runtime block; hover = slot name + "edit" link.
* Below the prompt: the bound tools with their schema descriptions (the LLM sees those too),
  token count, and a diff against the propeller example or against the last commit.

### 6.7 Tech

FastAPI + vanilla JS, the same stack as `web_app.py` (Streamlit was removed — F4).  Revised
(§0A): deployed as its **own service** (landing page + Studio; no engine secrets), and also
runnable locally with `python -m studio`; a mode flag (`STUDIO_MODE=hosted|local`) gates
everything that executes pack code.  It stays out of the configurator's Docker image
(`.dockerignore`).  The Studio imports the engine's assembler — it never re-implements prompt assembly (a replica drifts: see TODO F107,
`measure_prompts.py`).

---

## 7. The web app (deployed) after the change

* Parameters Inputs view built from `parameters.json` (labels, units, ranges, steps, groups).
* Preview (D9): level 1 = "Preview" button → server runs the primary generator into a
  scratch folder → shows its images (any DC); level 2 = the pack's `preview/` module renders
  instantly in the browser (propeller: today's `web/feg`).
* Model viewer chooses a loader by `outputs.model_format`; `none` = images only.
* Download: the generator's model files (today `/api/download_geometry` regenerates via
  RhinoCompute — becomes a tool option).
* Workflow Settings shows the pack's tool settings in their own group.

---

## 8. "Validate" button

Runs everything below and reports pass / warn / fail with a link to the field:

1. Pack schema: `pack.yaml`, `parameters.json`, every `tool.yaml`.
2. Slots: required filled; `empty_ok`; phrase = one line; no `{`/`}`; no unknown `$name`;
   markers balanced; per-topology rows consistent with the registry.
3. Parameters: unique valid names, `min < max`, defaults in range, integer types integral.
4. Tools: import in a subprocess; manifest ↔ signature; exactly one primary generator;
   roles exist; declared secrets present in `.env` (warn); dependencies installed; test
   run with defaults produces every declared output.
5. Assembly: every agent × topology × the settings matrix assembles; no leftover `$` or
   marker; token count per agent; then the existing offline checks
   (`smoke_test_prompt_format`, `smoke_test_slot_splices`, `smoke_test_topology_fragments`
   adapted to the pack, `dry_run_topology` with the scripted fake LLM, `smoke_test_agent_roles`).
6. Optional, opt-in: one live session with a cheap model on an example query (shows the
   estimated cost first).

The result is stored with a hash of the pack, so "Prepare" can tell whether it is current.

---

## 9. "Prepare for GitHub" button

*Revised (§0A): this is no longer a hosted button.  It is the local command
`python -m studio prepare` shipped inside the full package (and a button in the Studio's
local mode).  The hosted Studio's downloads produce the files of steps 2, 4 and 5 already;
steps 1, 3 and 6 run on the user's machine.*

1. Requires a passing Validate for the current pack hash.
2. `.gitignore` check/repair: `.env`, `*.env` (not `.env.example`), runtime folders
   (`logs/`, `attempts/`, `database/`, `previous_sessions/`, `inputs/…`), Studio caches,
   `__pycache__`.  `.dockerignore` excludes `studio/` and `examples/`.
3. **Secret scan** of every file that would be committed (API-key patterns, private keys,
   the values present in `.env`).
4. Merge dependencies: engine `requirements.txt` + every tool's `pip` list (conflicts
   reported); generate the Dockerfile's apt line from the tools' `apt` lists.
5. Generate `DEPLOY.md`: every environment variable (engine + tools) with description and
   whether required; Railway steps (Postgres with pgvector if the database is used, optional
   R2, single worker — `web_app.py` keeps in-process state); "Stage A" (no database) works.
6. Git: `git init` if needed, `git status` summary, first commit (message template, **no AI
   attribution**), and the exact commands for `gh repo create <name> --private --source .
   --push` — run only after the user confirms.

---

## 10. Implementation phases (each verifiable)

| Phase | Work | Acceptance |
|---|---|---|
| P0 | Branch `MAS-blueprint` from `MAS-generalized-v2`; commit the prompt-matrix harness (§11) under `extra_utilities/scripts/`; take the baseline snapshot. | Baseline of 357 prompts saved. |
| P1 | Pack loader + slot registry; move all fragments into `dc_pack/fragments/` with base/override files (§4.3); `prompts.py` reads the registry. | All 357 prompts **byte-identical** to P0; the 7 offline checks pass. |
| P2 | `parameters.json` single source; generate the key list, `$parameter_count`, the three list variants, sliders, preview spec, DB seed; parameter-access matrix (§4.6). | Prompts identical; slider page identical; DB seed equal row-for-row. |
| P3 | Tool contract, plugin loader, role binding, insertion sections, `IF` flags, tool settings; port the propeller generator and blade-sections tool to plugins. | Prompts identical (or every diff approved); tool schema texts identical; a propeller run produces the same files and hand-off. |
| P4 | Python-side DC text (C10 / F106); engine-generated hand-off labels; the web app made generic (§7). | Prompts identical; web app works with the propeller pack. |
| P5 | Studio, read-only: pack browser, the 3-column grid, prompt viewer. | Every slot visible with "where it lands". |
| P6 | Studio editing: grid with the link icon, parameters editor, New tool overlay + Test tool, settings & secrets. | Round-trip: editing then reverting leaves the pack byte-identical. |
| P7 | Validate; the two downloads (setup file, full package); local `prepare` command; `DEPLOY.md`. | Studio → propeller example → Validate green → download full package → `prepare` → deploys on Railway; the setup file re-imports byte-identically. |
| P7b | Hosted Studio: landing page (3 buttons), `STUDIO_MODE=hosted`, own service, upload limits, browser autosave. | No code path in hosted mode imports pack Python (test: a pack whose tool raises on import validates and downloads fine). |
| P8 | User docs ("Getting started", "Write a tool", "Adapters"); **acceptance test with a throw-away second DC** (not shipped, per D3) built only through the Studio. | The throw-away DC runs a full session. |

---

## 11. Developer notes for the coding session

**Owner rules** (`extra_utilities/AI_ASSISTANT_RULES.md`):
* Never commit or push unless the owner says so; never touch `MT-web-deploy`; no AI
  attribution anywhere (no `Co-Authored-By`, no "Generated with").
* Propose, then apply — one change at a time.  Show every BEFORE/AFTER **as chat text**:
  the owner cannot see the preview pane of the multiple-choice question tool.
* Every system-prompt edit is approved individually; ask design questions with the
  multiple-choice tool.

**Technical facts that bite** (verified on `MAS-generalized-v2`):
* `_build_slots()` reads every slot in every topology on every agent build: a missing file
  is a crash, an empty file is a valid "nothing" (W42).
* No literal `{` or `}` in any fragment: bodies are `.format()`ed after substitution (W45).
* Topologies 5 and 3 must read nothing from the shared trees
  (`smoke_test_topology_fragments.py`, MIRROR check) — P1 changes the layout, so adapt the
  check to the new resolution order, do not drop it.
* Inline phrase slots are delimited during assembly and re-wrapped at 80 columns
  (`INLINE_FRAGMENT_SLOTS`, `mark_inline_slots`, `wrap_inline_lines` in
  `agents/shared/prompts.py`); vocabulary slots are deliberately NOT in that set.
* Routing fragments are `$`-substituted (`routing._load_routing_fragment`).
* `PLANNER_FIRST` and `DC_INSPECTOR_ENABLED` are captured at import: assemble one topology
  per process.  A stale `.pyc` can serve the wrong topology — clear `__pycache__`.
* Run with `py -3.13` on Windows; `extra_utilities/prompt_pdf/bootstrap.py` stubs the heavy 3D
  imports so prompts assemble without them.  The working tree is CRLF (`core.autocrlf=true`).

**Verification harness.**  The 17-settings × 3-topology prompt snapshot used to verify
`MAS-generalized-v2` (`matrix_snapshot.py` + `analyze_diff.py`) exists only in a previous
session's scratch folder.  P0 must recreate and commit it.  Per combination, it patches
`workflow_settings.settings` (and `database_access.is_enabled_for` for "every DB tool") in a
child process, then calls `extra_utilities/scripts/topology_prompt_snapshot.py::_assemble`.  It
has a byte diff and a whitespace-normalised diff, and classifies every difference as
reflow, blank line or text.

**Open TODOs carried from `MAS-generalized-v2`**: F104 (feature-gated fragments shipping
with the feature off — fixable once flags are generic, §4.5), F105 (rename
`visualize_3d_model` / `propose_attempt`), F106 (Python-side text — P4), F107
(`measure_prompts.py` stale), F108 (overlapping fragments — the registry's `shared_with`).

---

## 12. Future work (owner TODOs)

* **AI drafting** (D11): a "Draft with AI" button per section — from the DC description, the
  parameter table and the tool manifests, an LLM drafts the example and description slots;
  the user reviews every value before it is saved.  Design the registry descriptions and
  examples now so they can serve as the drafting prompt later.
* **Insert tool text anywhere** (D7), in addition to the fixed sections.
* **Edit agents and topologies** (D10): add/remove agents, new topologies, an editable role
  map (F102).
* **Simplify and reuse descriptions**: `shared_with` / derived slots so one answer fills
  several fields (e.g. the two extraction-only example lists, the two soft-target examples).
* **Template repository** with clean history for public distribution (C11).
* A read-only prompt viewer inside the deployed app.
* **Option C — run imported setups on the hosted page** (§0A): only setups whose tools are
  all remote (HTTP endpoint / RhinoCompute URL hosted by the user), with the user's own LLM
  API key; requires multi-user session isolation first (F22).

---

## 13. Risks and open questions

* **P1–P4 are large refactors of a working system.**  Each phase must end with the prompt
  matrix identical to the baseline; any intended difference is shown to the owner.
* **Fragment count stays high** until descriptions are merged (F108, §12); the Studio's
  required/optional split and conditional visibility are what keep it usable.
* **Grammar coupling** cannot be fully validated by code: "where it lands" and the example
  are the safety net; the live smoke test (§8.6) is the final check.
* **Tool dependencies** may be heavy or OS-specific (OSMesa, Node, Rhino); the Test tool
  button must run in the same environment the Docker image will have, or say clearly that it
  does not.
* **Hosted Studio abuse**: uploads are limited in size and type, nothing is kept server-side,
  and no pack code runs there (§0A); the propeller demo keeps its invite code.
* **Licensing** of example assets (the Grasshopper file, images) before any public release.
