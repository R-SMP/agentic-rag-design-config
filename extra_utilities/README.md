# `extra_utilities/` — start here

Everything in this folder is developer-facing: the TODO list, the invariant
registry, explanation documents, the database schema and a few hand-run
scripts.  The running app imports nothing from here; the one exception is
`scripts/gen_render_samples.py`, which `web_app.py` runs as a subprocess when
the Render-compression panel regenerates its sample images.

The folder was cleaned up on 2026-10-10, at the end of development.  Build
plans, hand-over notes, prompt-review records, most test scripts and the old
schema migrations were removed; what they knew that is not explained elsewhere
is in [`extra_info.md`](extra_info.md), and every removed file is still in git
history (`extra_info.md` §13 says where).

---

## The things you probably want

| I want to… | Go to |
|---|---|
| see what is broken or missing | `TODO_known_issues.md` — **read its index, don't `cat` it** (~4 600 lines) |
| know what I must not break | `warnings_developer.md` — the W-numbered invariant registry |
| understand a design decision the docs don't explain | `extra_info.md` |
| understand the database and RAG layer | `db_design/database_and_RAG_architecture.md` |
| run a check after changing prompts or wiring | `tests/README.md` |
| know how an AI assistant should work in this repo | `AI_ASSISTANT_RULES.md` |

---

## Layout

```
extra_utilities/
├── README.md                 this file
├── extra_info.md             what the removed development records knew
├── AI_ASSISTANT_RULES.md     the owner's standing rules for AI coding assistants
├── TODO_known_issues.md      LIVE tracker — open entries + an index at the top
├── TODO_archive.md           closed entries, verbatim.  Ids are retired, never reused.
├── warnings_developer.md     LIVE invariant registry (W-numbered)
│
├── docs/                     explanation documents
│   ├── web_interface_notes.md          the web UI: design + decisions log
│   ├── cloud_architecture_notes.md     hosting, auth, session-state decisions
│   ├── cloud_deploy_runbook.md         Railway: how it was stood up + how it deploys now
│   ├── OCR_technology_notes.md         Google Cloud Vision OCR
│   ├── benchmark_suite.md              the benchmark and the three experiments
│   ├── value_states_and_out_of_range.md  LOCKED / SOFT TARGET / FREE + out-of-range handling
│   ├── topology_shared_touchpoints.md  every shared registry a new agent must be added to
│   ├── design_precision_sections_match.md  the precision sections-matching feature
│   ├── design_prompt_caching.md        how prompt caching works here and what it costs
│   └── design_reasoning_support.md     extended-thinking support — a plan, not yet built
│
├── db_design/
│   ├── database_and_RAG_architecture.md   the DB/RAG source of truth
│   ├── database_design_notes.md           D0–D15 doctrine (its DDL block is v5-era)
│   ├── database_PostgreSQL_schema_v9.sql  the current schema
│   ├── migrations/migrate_v8_to_v9.sql    upgrades a v8 database (idempotent)
│   ├── apply_schema.py                    run a .sql file against DATABASE_URL
│   ├── populate_dc_parameter_schemas.py   upload the parameter schema (fallback for the button)
│   └── drop_all_tables.sql                wipe before re-applying the schema
│
├── tests/                    eight offline checks + their README
├── scripts/                  hand-run tools (see below)
├── prompt_pdf/               builds the assembled-prompts PDF, and reads a marked-up
│                             copy back into file + line edits (its own README)
├── prompt_efficiency/        measure_prompts.py + measure_image_tokens.py (token counts)
└── dc_params_primer/         regenerates the DC-parameter primer image (its own README)
```

**Building a fresh database:** `drop_all_tables.sql` (if needed) →
`database_PostgreSQL_schema_v9.sql` → `populate_dc_parameter_schemas.py`,
each run through `apply_schema.py` (see `drop_all_tables.sql`'s header).
Upgrading an older database needs the migration ledger from git history —
`extra_info.md` §11.

### `scripts/`

| Script | What it does |
|---|---|
| `gen_render_samples.py` | Regenerates `web/render_samples/` (the Render-compression panel's samples).  **The app runs this one** — do not move it without updating `web_app.py`. |
| `topology_prompt_snapshot.py` | `save <dir>` assembles and hashes every agent's full prompt per topology; `diff <a> <b>` shows which agents moved.  The standard check before and after any prompt edit. |
| `hub_registry.py` | Reads which agents a hub really builds from its `_agents_by_key` literal; used by the snapshot script. |
| `check_mesh_components.py` | Per-component report for a generated `.obj` (watertightness, volume, degenerate faces). |
| `feg_render_demo.py` | Builds a propeller with the headless FEG exporter and renders it three ways. |

Run them from the repository root, e.g.
`py -3.13 extra_utilities/scripts/topology_prompt_snapshot.py save C:/tmp/snap`.

---

## ID namespaces — they do not share a counter

| Prefix | Lives in | Meaning |
|---|---|---|
| `F` | `TODO_known_issues.md` / `TODO_archive.md` | future work and defects |
| `O` / `OPS` / `R` | `TODO_known_issues.md` | open issues / pre-deploy ops / resolved |
| `W` | `warnings_developer.md` | invariants |
| `T` | `db_design/database_and_RAG_architecture.md` | deferred DB/RAG items |
| `D` | `db_design/database_design_notes.md` | DB doctrine decisions |

**Ids are never reused and never renumbered** — many are cited from live
source.  Before filing a new one, take the highest id in BOTH TODO files (or in
`warnings_developer.md`) and add one.

---

## Things that look removable and are not

- **Five 0-byte `.md` prompt fragments are load-bearing**, two of them in a
  way that crashes the app at import and two in a way that silently changes a
  prompt.  Read `warnings_developer.md` **W42** before deleting any empty file.
- **`scripts/gen_render_samples.py`** is run by `web_app.py` by path.
- **`prompt_pdf/bootstrap.py`** stubs the heavy imports so the agent tree loads
  without `trimesh` / `langchain_*`; two of the tests and the snapshot script
  depend on it.
- **`prompt_efficiency/baseline_tokens.json`** is the baseline
  `measure_prompts.py` compares against.

## Planned files that were never written

These names appear in open work items as intentions, not broken links:
`reembed_corpus.py` (`db_design/database_design_notes.md` D14) and
`tests/smoke_test_context_pruner.py` / `tests/smoke_test_dh_multi.py`
(`TODO_known_issues.md`, "Suggested test layout").
