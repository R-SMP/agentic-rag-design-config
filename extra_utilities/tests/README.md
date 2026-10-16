# Offline checks

Twelve hand-run scripts that need no network, no database and no API spend.
There is no CI and no pytest: run each one directly from the **repository
root**.

```bash
py -3.13 extra_utilities/tests/dry_run_topology.py
```

Use Python 3.13 — the default 3.8 cannot parse the agent code's type hints.
Where `trimesh` / `langchain_*` are not installed, the scripts that import the
agent tree stub them through `extra_utilities/prompt_pdf/bootstrap.py`; set
`OPENAI_API_KEY=sk-dummy` (a key must exist to construct agents; nothing is
sent) and `PYTHONIOENCODING=utf-8` if you pipe the output.

These six were kept when the other ~50 test scripts were removed on
2026-10-10.  `extra_utilities/extra_info.md` §13 lists every removed script,
what it guarded and how to restore it from git.

## The checks

| Script | Run it after… | What it proves |
|---|---|---|
| `dry_run_topology.py` | any change to routing, a hub, an agent's run loop or the dispatcher | Drives ONE complete turn per topology (7, 5 and 3) against a scripted fake LLM.  Everything except the LLM call is the production path: the real `dispatch_turn`, the real Receptionist, every agent's run loop, the real routing tools and hub dispatch.  It asserts the exact sequence of hops, so a mis-route fails naming who was called and who should have been, and an unbound tool name stalls the turn.  `--topology N` runs one topology; each runs in its own subprocess.  This is the only check that catches the defects both early 5-agent live runs hit (a blank user reply, a discarded start target, a hub calling an agent it never built). |
| `smoke_test_topology_fragments.py` | any prompt or fragment edit | Builds every prompt for topologies 7, 5 and 3 and checks that no topology reads another's files, no `$slot` is left unsubstituted, the hub routing resolves correctly, and topologies 5 and 3 read **nothing** from the shared prompt trees (the MIRROR invariant) and, in `dc_pack/`, topologies read only their own `.t<N>` or linked files (PACK-MIRROR).  Findings awaiting an owner-approved prompt edit are printed as KNOWN-PENDING rather than passed silently.  Needs Python ≥ 3.10.  **Writes probe fragments into the real tree and removes them** — check `git status` afterwards. |
| `smoke_test_hub_attributes.py` | any change to a hub class | Pure AST, imports nothing.  For every hub: every `self.<attr>.<method>()` refers to an attribute the class actually has (the defect that left an old hub calling three agents its topology never built), and the wired routing edges match the expected edge set read from the source. |
| `smoke_test_slot_splices.py` | any fragment edit | Scans every prompt and fragment and fails when a `$slot` that expands to several lines does not stand alone on its own line.  Pure standard library. |
| `smoke_test_prompt_format.py` | any prompt edit | Formats every agent template of topologies 7, 5 and 3 (one subprocess per topology) with a stub mapping, under RAG off, RAG on, and RAG on with every database tool forced on, catching a literal `{` / `}` or an unmatched brace before it reaches agent construction (see `warnings_developer.md` W45; TODO F101). |
| `smoke_test_agent_roles.py` | any change to `agents/shared/agent_roles.py`, a hub's roster, `database_search`'s ACL or the DH question loader | The agent role map across topologies: `ROSTER` matches what each hub builds and `DISPLAY` matches `routing_tools.AGENT_DISPLAY`; who may read which past answers per topology (both directions, the hub taking the Orchestrator's role, the `RAG_DCIC_READS_DCII` toggle); that the question table maps "Agent from" downward only and drops a skipped row's sub-rows; and that a real assembled `database_search` response carries the `<agent_roles>` legend once, right after `<search_meta>`, listing only the agents found.  Offline (stubbed imports). |
| `smoke_test_ring_height.py` | any change to `web/feg/` or `dc_pack/tools/rhino_geometry/ring_height.py` | The Python port of the outer-ring height fit must match the real `web/feg` JavaScript (run under Node) to within 1e-9 mm over 552 parameter sets.  **It is the only guard for that port — never remove it.**  Needs Node and `node_modules/three` (`npm install` in the repo root); without them it prints SKIP. |
| `smoke_test_parameters.py` | any change to `dc_pack/parameters.json`, a `parameter_list*.md` fragment, `engine/parameters.py` or `engine/parameter_schema.py` | `parameters.json` is valid (each kind of broken file is caught, a bad `retired` list included); every hand-written parameter list in `dc_pack/fragments/dc/` names the same parameters, in the same order, with the same `[min; max]`; what the validator, slider page, preview check and database get from the file is well-formed; and the schema upload (matching, automatic numbering, retirements) behaves, against a stand-in database — never the live one. |
| `smoke_test_parameter_access.py` | any change to the `parameter_access` table in `dc_pack/pack.yaml`, `engine/parameter_access.py`, a prompt's `<<IF:param_list>>` region, or any `<<IF:…>>` marker | The grid has exactly one cell per agent each topology builds (plus the Database Handler); every agent prompt has one `<<IF:param_list>>` region around `$parameter_list`; each state shows the list with its ranges, without them, or not at all, binds `dc_params_list` only for "tool", and leaves no marker; the settings file stores only changed cells; every `<<IF:flag>>` / `<<IFNOT:flag>>` in a prompt or fragment names a known flag and is closed. |
| `smoke_test_pack_tools.py` | any change to a `dc_pack/tools/<tool>/` folder (its `prompts/` included), `engine/pack_tools.py`, `engine/pack.py`, `engine/tooling.py`, `agents/shared/attempt_renders.py` or `agents/shared/image_compression.py` | Every `tool.yaml` is valid and builds its agent tool; the settings come from the manifests, a value a manifest does not allow is refused, saving keeps only the changes and reset removes the file (on a temporary path); the tool runner of each topology — Tool Caller in 7 and 5, Design Engineer in 3 — gets both tools, blade sections only while switched on, and no other agent gets either; and 23 cases (the generator with stand-in back-ends, the blade-sections tool for real) answer exactly what the tools answered before they moved into the pack (`fixtures/pack_tools_golden.json`): the text, the files written, the back-end calls; each tool owns its prompt text (every tool-text slot has exactly one owner and its files in that tool's `prompts/`, and seven deliberately broken copies of the pack are refused); the engine-built tool list equals the six hand-numbered lists the prompts carried before (`fixtures/tool_lists.json`); and a copy of the pack without the blade-sections folder builds all 21 prompts with no trace of the tool; seven manifests that break the image contract are refused (a file not named `render_<view>.png`, a missing or unknown `compression`, no `fill_on_save`, a bad `image_note`, a runtime block reading a slot its tool does not own or naming a bool setting); the save step asks blade sections first, then the generator (build when the model is missing, render only when it is there), and skips a tool with `fill_on_save: false` (stand-in tools); every image and variant gets the shrink strength the old file-name rule gave; and the render-check block follows the generator's settings in all four combinations; the geometry tools load as tools no agent is given, the generator's two geometry settings and the Downloads choice list them (display names, `none`, the saved file, the `pack.yaml` default), a value still saved for a removed setting is skipped, `make_model` (stand-in geometry tools) uses the chosen tool, falls back, and reports one tool's error or both by display name, and five broken geometry packs are refused. |
| `smoke_test_web_texts.py` | any change to the words in `web/index.html`, `/pack/page.js`, the flowchart's tool list (`agent_activity.STANDARD_TOOLS`, a `@generic_tool` name, `engine/pack_tools.page_tools`) or the retired parameter names | Runs the real FastAPI app (only packages that are not installed are stubbed; no database).  The page served with the propeller pack shows exactly the texts it carried before (title, chat box, empty viewer, database-entry example and checkbox) with no `$name` left; with a pack whose words are stand-ins (one with `<` and `&`) the page and `/pack/page.js` say the stand-ins, escaped; `/pack/page.js` lists the pack's switched-on tools then the 15 standard ones, and every `@generic_tool` name is in that list; a record carrying a retired parameter name is read without it by the preview check and `propose_attempt`; the Parameters page's Download button names the geometry tool chosen for downloads, and `/pack/page.js` carries the model (file, format, up axis). |
| `smoke_test_engine_texts.py` | any change to text Python writes for the agents, to `agents/shared/pack_text.py`, or to a pack word it uses | The tools, answers and texts the engine writes for the agents equal what they were before P4a and P4b (`fixtures/engine_texts.json`, recorded on `683d1bf`): nine tools' descriptions in topologies 7 / 5 / 3, four tools' answers on a fixture folder (including the note under an opened image and `database_search`'s answer to an empty search), the Context Pruner's prompts, the Database Handler's reminder and stitching prompt, the Sessions Queue's run classifier, the hubs' end-of-session instructions and refine-cap message, the Receptionist's block.  Rebuilt from a pack whose words are swapped for stand-ins, they say the stand-ins instead. |

## Things worth knowing before you trust a result

- **A repo-wide grep run from the main checkout** walks `.claude/worktrees/`
  too and scans the other checkouts.  If a hit names a path under
  `.claude/worktrees/`, it is not about this checkout.
- **A stale `.pyc` can serve the wrong `SYSTEM_TOPOLOGY`** (switching 7 → 5 → 3
  is a size-preserving edit).  If a check contradicts an earlier green run,
  delete every `__pycache__` folder and run it again.
- **For any prompt edit, also snapshot the assembled prompts** before and
  after: `py -3.13 extra_utilities/scripts/topology_prompt_snapshot.py save <dir>`,
  then `diff <dirA> <dirB>`.  State which agents moved and which are
  byte-identical; a topology-5 or topology-3 edit must leave topology 7's
  prompts untouched.
- **For a refactor that must move no prompt at all** (the MAS-blueprint
  phases), use the settings matrix:
  `py -3.13 extra_utilities/scripts/prompt_matrix.py save extra_utilities/prompt_matrix/snapshots/<name>`
  assembles 357 prompts (17 setting combinations x topologies 7, 5 and 3), and
  `diff extra_utilities/prompt_matrix/baseline_manifest.json extra_utilities/prompt_matrix/snapshots/<name>`
  must report 0 differences.  `wsdiff` and `classify` explain any that remain.
- **For a change that must move no tool**, compare the tools every agent is
  given: `py -3.13 extra_utilities/scripts/tool_matrix.py save <file>` records
  them under the same 17 combinations (name, description, argument schema),
  and `tool_matrix.py diff extra_utilities/prompt_matrix/tool_baseline.json <file>`
  must report 0 differences.
