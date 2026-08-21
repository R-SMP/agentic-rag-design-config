# Smoke-test & utility script index

Every hand-run script under `extra_utilities/`.  There is **no CI, no
pytest, no conftest** in this repo -- these are run individually by hand,
usually as `python extra_utilities/<name>.py`.

**Scripts are deliberately NOT relocated into a subfolder.**  Each one
computes the repo root by depth from its own location (7 files use
`Path(__file__).resolve().parents[1]`, 86 sites use chained `.parent`), so
moving them would mean editing the bootstrap of every file plus `web_app.py`
(which shells out to `gen_render_samples.py`) and `.claude/settings.local.json`
(which whitelists `smoke_test_param_rename.py` by path).  This index replaces
that move.

## Legend

| Flag | Meaning |
|---|---|
| `py>=3.10` | Cannot run under the py3.8 worktree interpreter |
| **writes into the real tree** | Leaves probe files/folders behind -- see notes |
| **costs money** | Makes billed LLM API calls |
| **BROKEN** | Calls an API that has since changed -- see "Known-broken" below |

## Root smoke tests  (32)

| Script | Needs | Flags | Guards / does |
|---|---|---|---|
| `smoke_test_all_chain_agents.py` | llm-api |  | Asserts Orchestrator(session=…) builds all seven chain agents as BaseChainAgent subclasses with the right AGENT_KEYs, materialises one AgentState slot per agent in session.agent_states, and that sn... |
| `smoke_test_async_turn.py` | none |  | Asserts the /api/turn 202 + SSE turn_done contract with dispatch_turn stubbed: 202 with a 12-hex turn_id, 400 on a blank message, 409 on a concurrent turn, an end-to-end SSE turn_done payload (turn... |
| `smoke_test_attempt_coherence.py` | none | **writes into the real tree** | Proves generate_and_render_propeller builds ONLY from an attempt's own parameters.json — a missing/malformed/15-key/non-numeric/JSON-list record fails cleanly and writes no mesh, an existing mesh i... |
| `smoke_test_attempt_renders.py` | none |  | Offline check of the attempt render-view registry and the save-time render-completion pass (render/geometry tools stubbed into sys.modules): enabled_views tracks the settings flags, the R2 attempt... |
| `smoke_test_base_chain_agent.py` | llm-api |  | Asserts the BaseChainAgent contract through the Receptionist: fresh-construction defaults (empty messages, seeded cycle_start_ts, llm is base_llm), snapshot_state shape, full snapshot→restore round... |
| `smoke_test_database_access.py` | none | py>=3.10 | Offline check of the per-(profile, agent, tool) DBa store: that profile '7' still resolves byte-for-byte to the pre-profiles flat behaviour, that '7-reduced' matches the owner's decided 24-cell dis... |
| `smoke_test_database_handler.py` | none as designed | **BROKEN** | Asserts DatabaseHandler is a BaseChainAgent registering its own session slot, that it requires a Session, that populate_database writes one .txt per (agent, field) row of a patched 2-row SCHEDULE,... |
| `smoke_test_dh_batching.py` | none |  | Covers the pure half of the Database Handler's batching: candidate_runs grouping rules, plan/batch label allocation, validate_plan's five rejection modes with lossless repair, read_batch_result's c... |
| `smoke_test_dispatch_turn.py` | llm-api |  | Asserts dispatch_turn's 5 branches: save_user_input writes a timestamped user_query.txt, forward=False returns the Receptionist's reply verbatim, forward=True builds a kickoff carrying the summary... |
| `smoke_test_fork_drift.py` | other | py>=3.10 | Reads extra_utilities/fork_manifest.json and FAILS when any forked file's origin has been committed to since the fork was recorded, when a fork on disk has no manifest entry, or when a manifest ent... |
| `smoke_test_generate_mesh.py` | rhino |  | End-to-end live run of generate_and_render_propeller against the configured geometry backend: writes a 16-key parameters.json into a fresh timestamped attempt folder under ATTEMPTS_DIR, invokes the... |
| `smoke_test_google_vision.py` | google-vision |  | Live Google Cloud Vision connectivity + detection-recall probe on an annotated render (prints full text, callout regions and raw word boxes, then checks six known callouts), plus a non-fatal exerci... |
| `smoke_test_image_buffer.py` | none |  | Asserts the image buffer-and-flush contiguity mechanism across four message shapes (dual parallel tool call, empty-flush no-op, three parallel calls with two image-loading, and two image-loading ca... |
| `smoke_test_image_compression.py` | none |  | ~35 checks on agents/shared/image_compression.py: cap-respecting downscale with format preserved, byte-identical small-image passthrough, exotic decode modes (I;16/F/CMYK) compressing instead of cr... |
| `smoke_test_llm_client_cache.py` | none |  | Asserts the LLM client cache memoises on the (provider, model, api_key) triple: same agent hits, two agents with the same triple share one client, a different triple or a different api_key builds a... |
| `smoke_test_llm_routing.py` | none |  | Nine-case exercise of the LLM-routing read/write path against a tempdir mini-checkout: defaults, per-agent override write with shared API-key preservation, read-back, global-mode switch preserving... |
| `smoke_test_no_parallel_kwarg.py` | none |  | Constructs the whole Orchestrator + 7-chain-agent stack against a fake Anthropic client and asserts every construction-time bind_tools() call receives ZERO kwargs (i.e. the parallel_tool_calls=Fals... |
| `smoke_test_ocr_grouping.py` | none |  | Ten deterministic checks on group_words_into_regions with synthetic word boxes: same-line merge, same-band gap-split, separate vertical bands ordered top-to-bottom with ids, order-independence (pro... |
| `smoke_test_orchestrator.py` | llm-api |  | Asserts Orchestrator is a BaseChainAgent with its own AgentState slot, requires a Session, that routing tools append 4-key exchange dicts with a tz-aware ISO ts, that the chain log is session-scope... |
| `smoke_test_param_rename.py` | none |  | Intercepts EvaluateDefinition to capture the ParamName of every input tree the tool sends to RhinoCompute and asserts exactly 17 names arrive — the 16 canonical camelCase inputs from parameter_keys... |
| `smoke_test_prompt_cache.py` | llm-api | **costs money** | Drives real Anthropic calls through the shipped helpers (make_system_message / history_cache_control / invoke_with_retry) to prove the explicit system breakpoint and the top-level automatic breakpo... |
| `smoke_test_prompt_format.py` | none |  | Pulls each of the 8 .format()-wired agent TEMPLATEs from agents.shared.prompts and calls .format_map() with a stub mapping, catching literal `{}`/unmatched braces/malformed slots that would otherwi... |
| `smoke_test_prompt_variant.py` | none |  | For each PROMPT_VARIANT, proves every file under agents/<N>agent_<variant>/ is actually REACHED by prompts._topology_override, that the set of agents whose assembled prompt differs equals the BLAST... |
| `smoke_test_prompts_hot_reload.py` | none | py>=3.10 | Points prompts.py's 5 path constants at a tempdir fixture tree and proves _build_slots() and _build_template() re-read fragments from disk on EVERY call (mutating name.txt between two rounds), so a... |
| `smoke_test_r2_upload.py` | r2 |  | Step-by-step live probe of the Cloudflare R2 mirror: env vars, boto3 + r2_uploader import and is_enabled, endpoint/client construction, auth probe, direct put_object, upload_file, upload_directory... |
| `smoke_test_render_blade_sections.py` | none |  | Asserts the blade-sections geometry (point counts + finiteness for inner/middle/outer), draw.render_png producing valid PNGs at default/min/max params with grid differing from no-grid, and the @too... |
| `smoke_test_ring_height.py` | node |  | Drift guard: asserts the pure-Python fitted_ring_height port matches the REAL web/feg JS (executed under Node) to within 1e-9 mm across 552 param sets (500 random + all-min/all-max corners + 50 int... |
| `smoke_test_session_archival.py` | none |  | Asserts agents.loader._archive_previous_session() sweeps logs/traces/agent_histories/attempts/input_images AND every orphan file at inputs/ root into previous_sessions/<id>/, deletes the emptied lo... |
| `smoke_test_session_roundtrip.py` | llm-api |  | End-to-end two-turn integration: dispatch_turn against a live LLM, then asserts snapshot-back populated session.agent_states['receptionist'].messages, that to_dict (with live BaseMessages stripped)... |
| `smoke_test_session_to_from_dict.py` | none |  | Asserts Session.to_dict/from_dict round-trips every config flag, path field, chain-log exchange and per-agent AgentState field; that to_dict output passes assert_plain_data and json.dumps; that ass... |
| `smoke_test_slot_splices.py` | none |  | Scans every $-slot substitution target (agent prompt*.md plus every prompt_fragments/, tools_config/ and dc_config/ tree, variants included) and fails when a slot that resolves to MULTI-LINE conten... |
| `smoke_test_topology_fragments.py` | none | py>=3.10 - **writes into the real tree** | Builds every prompt for topologies 7 and 5 under both PLANNER_FIRST settings and asserts COVERAGE (every agents/<N>agent/ override is read), NO-LEAK, ISOLATION, no unsubstituted $slots, $routing_hu... |

## Root utilities (not tests)  (3)

| Script | Needs | Flags | Guards / does |
|---|---|---|---|
| `check_mesh_components.py` | none |  | Standalone .obj diagnostic: parses a mesh group-by-group and reports verts/faces/watertightness/degenerate-face count/signed volume for each component and for the concatenated whole, both as-writte... |
| `feg_render_demo.py` | node |  | Manual demo: builds a propeller with the headless-Node FEG exporter (reusing web/feg/* verbatim so the geometry matches the browser preview) and renders it three ways — a self-contained pure-PIL so... |
| `gen_render_samples.py` | node |  | Generates the fixed sample renders for the 'Render compression' settings panel: three blade-section diagrams via tools/render_blade_sections/draw.render_png (--cross, pure PIL, runs anywhere) and t... |

## db_design/  (16)

| Script | Needs | Flags | Guards / does |
|---|---|---|---|
| `db_design/apply_schema.py` | postgres |  | Generic one-shot runner: executes whatever .sql file is passed as argv[1] against DATABASE_PUBLIC_URL/DATABASE_URL in one autocommit connection, then prints a pgvector/tables/indexes verification r... |
| `db_design/migrations/migrate_v5_to_v6.py` | postgres |  | Adds the session_counter SEQUENCE and setval-seeds it from MAX(IDNNN) parsed out of existing sessions.session_id, so the next nextval returns max+1 and no slug collides. |
| `db_design/migrations/migrate_v6_to_v7.py` | postgres |  | Idempotent ALTERs on rag_queries: ADD COLUMN tool_name TEXT NOT NULL DEFAULT 'database_search', ADD COLUMN images_flag BOOLEAN, ALTER COLUMN attempt_specific DROP NOT NULL, plus CREATE INDEX idx_ra... |
| `db_design/migrations/migrate_v7_to_v8.py` | postgres |  | Creates the chunks_mm table + its 4 indexes (CREATE TABLE/INDEX IF NOT EXISTS), with the HNSW halfvec(2048) index built in its own transaction behind a pgvector-version guard so the table is still... |
| `db_design/populate_dc_parameter_schemas.py` | postgres |  | Idempotent append-only seeder for the dc_parameter_schemas table: inserts schema_version=1 (17 params, history) and schema_version=2 (16 params, impellerHeight removed — the CURRENT set), via INSER... |
| `db_design/smoke_test_database_search.py` | postgres, llm-api |  | 26-assertion live verifier for the database_search tool: window-function dedup over the candidate pool, per-row ACL via chunks.agents_to[] (planner sees a Planner-only secret, receptionist does not... |
| `db_design/smoke_test_database_search_mm.py` | postgres, llm-api |  | Verifies database_search read-routing against chunks_mm in MODE_SINGLE_VECTOR, including the graceful fallback to the text-only chunks path when Voyage is unavailable (forced by nulling voyage_mm._... |
| `db_design/smoke_test_db_writer.py` | postgres, llm-api, r2 |  | Canonical Phase 3B end-to-end verifier for agents/database_handler/db_writer.py — 14 numbered checks covering stitch_for_embedding, embed_text, upsert_session/attempt/attempt_parameters, all four i... |
| `db_design/smoke_test_db_writer_mm.py` | postgres, r2, llm-api |  | Exercises db_writer_mm.mirror_session_to_mm(session_id, force=True) against a real session, then verifies chunks_mm row counts per field and that embeddings are non-NULL. |
| `db_design/smoke_test_dh_kwarg_propagation.py` | none |  | Pure-AST guard against NameError-class regressions: for 9 DatabaseHandler methods, parses the source and asserts every bare-Name kwarg value resolves to a parameter, local binding, module global, b... |
| `db_design/smoke_test_phase_3c.py` | postgres, llm-api, r2 |  | Exercises DatabaseHandler._phase_3c_persist_chunk directly against a mock self, proving session-scoped rows keep item_index=NULL while attempt-scoped rows are PROMOTED to item_index=1, plus the Sti... |
| `db_design/smoke_test_postgres_pool.py` | postgres |  | Phase 3A foundation check: config.DATABASE_URL/DATABASE_PUBLIC_URL visible, workflow_settings.DATABASE_ENTRY_MAX_RETRIES exists, postgres_pool connects to Railway, pgvector registered, vector(1024)... |
| `db_design/smoke_test_resolve_session_name.py` | postgres |  | Verifies agents.loader._resolve_session_name() produces monotonically increasing, non-colliding IDNNN_ slugs off the Postgres session_counter SEQUENCE, and exercises the microsecond-timestamp fallb... |
| `db_design/smoke_test_retrieve_attempt.py` | postgres, r2 | **BROKEN** | Phase 5C verifier for the retrieve_attempt tool: asserts <description>/<parameters>/<renders> blocks, render_views_in_scope policy gating across the three view toggles, per-view image-block counts,... |
| `db_design/smoke_test_retrieve_user_inputs.py` | postgres, r2 | **BROKEN** | Phase 5B verifier for the retrieve_user_inputs tool: asserts <user_query>/<image_notes>/<images> XML blocks, image-block counts under images_flag on/off, and best-effort rag_queries logging. |
| `db_design/smoke_test_voyage_mm.py` | llm-api |  | Verifies agents/shared/voyage_mm.py against the LIVE Voyage API: model string, embed_text / embed_image / embed_fused each return VOYAGE_MM_DIMS-length vectors, using a PIL-generated throwaway image. |

## prompt_efficiency/  (2)

| Script | Needs | Flags | Guards / does |
|---|---|---|---|
| `prompt_efficiency/measure_image_tokens.py` | none |  | Synthesises representative images (mesh render, tall blade-section diagram, phone photo, scanned sketch), runs each through compress_for_model at the size-based auto-default, and reports vision-tok... |
| `prompt_efficiency/measure_prompts.py` | none |  | Dependency-free stdlib replica of prompts.py::_build_template so assembled per-agent prompts can be measured and integrity-checked under Python 3.8, where the real assembler cannot be imported; rep... |

## Non-obvious facts worth knowing before you run anything

- **The only script that runs as-is in the bare py3.8 worktree** is
  `smoke_test_slot_splices.py` (pure stdlib).
- **Side effects on the real tree.**  `smoke_test_topology_fragments` writes
  `DC_prompt_fragments/dc_config/hard_constraints_dc_dc_input_inspector.md` and
  `agents/5agent/prompt_fragments/routing_user_input_inspector_uii_first_5agents.md`;
  `smoke_test_attempt_coherence` creates `g_*` / `f75*` folders under the real
  `ATTEMPTS_DIR`.  Check `git status` afterwards.
- **`smoke_test_prompt_cache`** costs a few cents.  Its `check_phase_isolation()`
  is free and runs first.
- **`smoke_test_generate_mesh`** needs a live backend (RhinoCompute, or Node +
  the FEG exporter).  It is the deliberate live counterpart to
  `smoke_test_attempt_coherence`, which stubs it.
- **Deliberate couplings.**  `smoke_test_attempt_coherence` and
  `smoke_test_param_rename` share the one-arg `_validate_output_dir` contract,
  pinned from source at `tools/generate_mesh/generate_mesh.py:825-826`.
  `smoke_test_ring_height` guards the JS-to-Python port of the ring-height fit
  and is named from `tools/generate_mesh/ring_height.py:20,29` -- it is the ONLY
  guard for that drift and must never be removed.
- **`smoke_test_slot_splices.py` FALSE-FAILS in the main worktree.**  It walks
  the tree from the repo root, and the main checkout contains
  `.claude/worktrees/` with every sibling worktree inside it -- so it scans all
  of them.  Measured 2026-08-21: **987 substitution targets and 23 "problems"
  from the main worktree, vs 121 targets and a clean PASS from a worktree that
  has no nested checkouts.**  Every one of the 23 came from a sibling branch.
  Before believing a FAIL, check whether the reported paths contain
  `.claude/worktrees/`.  The same trap applies to any repo-root grep run from
  the main checkout.

- **`db_design/migrations/*.py` are not tests.**  They are an ordered, idempotent
  migration ledger (decision T18 in
  `db_design/database_and_RAG_architecture.md:1051`).  Schema v8 itself still
  prescribes running them on non-empty databases, and `migrate_v7_to_v8.py:92`
  is the only idempotent creator of the live `chunks_mm` table.

## Known-broken (repair proposed, not yet applied)

| Script | Breakage |
|---|---|
| `smoke_test_database_handler.py` | `patch.object(dh_module, "SCHEDULE", ...)` at `:159,:208` is a no-op -- `populate_database` now reads `workflow_settings.dh_schedule.read_for_dh()`.  `_fake_invoke` at `:81` cannot absorb the `cache_control=` kwarg every DH call site now passes.  Labels `DH-formulate` / `DH-decide` (`:90,:95,:191,:194`) have 0 grep hits.  **Do not delete:** its case 4 is the only executable assertion that `populate_database` neither replaces nor mutates `session.agent_states[k].messages` -- now also a prompt-cache byte-stability precondition. |
| `db_design/smoke_test_retrieve_user_inputs.py` | Passes the removed `images_flag=` kwarg at 6 sites and unpacks a 3-tuple from a function that now returns `str`.  ~16 lines of mechanical repair; every assertion target still exists. |
| `db_design/smoke_test_retrieve_attempt.py` | Same two breakages at 7 sites. |
| `smoke_test_r2_upload.py` | Not broken, but step 7b (`:398-401`) omits `global_attempt_id`, so the doubled-prefix regression is guarded on the legacy key shape production no longer uses. |

