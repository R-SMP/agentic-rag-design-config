# `extra_utilities/` — start here

Everything in this folder is developer-facing: trackers, design documents and
hand-run scripts. **Nothing here is imported by the running system** — except
`prompt_efficiency/` and `db_design/migrations/`, which are tooling with real
inputs, and `fork_manifest.json`, which `smoke_test_fork_drift.py` reads.

---

## The four things you probably want

| I want to… | Go to |
|---|---|
| see what is broken or missing | `TODO_known_issues.md` — **read its index, don't `cat` it** (220 KB) |
| know what I must not break | `warnings_developer.md` — W1–W42, the invariant registry |
| run or understand a script | `SMOKE_TESTS.md` — all 54, what each guards, what each costs |
| know how the owner wants work done | `working_agreements.md` — the six standing rules |

---

## Layout

```
extra_utilities/
├── README.md                 this file
├── TODO_known_issues.md      LIVE tracker — 77 open entries + a grep index
├── TODO_archive.md           31 closed entries, verbatim.  Ids are retired, never reused.
├── warnings_developer.md     LIVE invariant registry — W1–W42
├── SMOKE_TESTS.md            index of the 54 hand-run scripts
├── working_agreements.md     the owner's standing rules for how work is done
│
├── smoke_test_*.py           32 hand-run scripts (see SMOKE_TESTS.md)
├── check_mesh_components.py  .obj diagnostic
├── feg_render_demo.py        FEG render demo + the circular-import sidestep notes
├── gen_render_samples.py     regenerates web/render_samples/geo_*.png
├── fork_manifest.json        read by smoke_test_fork_drift.py — not documentation
│
├── docs/
│   ├── active/               being written against right now
│   ├── reference/            durable; not tied to build state
│   └── archive/              finished; read-only history (+ archive/scripts/)
│
├── db_design/                schema history, migrations, DB smoke tests
│   ├── database_and_RAG_architecture.md   ← the DB/RAG source of truth
│   ├── database_design_notes.md           D0–D15 doctrine (its DDL block is v5-era)
│   ├── database_PostgreSQL_schema_v2..v8.sql
│   ├── migrations/           an ORDERED, idempotent ledger — not one-off scripts
│   └── archive/              schema v1 (the one version no document cites)
│
├── prompt_efficiency/        the 349-cut shrink proposal + its verifier.  APPEND-ONLY.
├── embedding_tests/          a LIVE web view (8 FastAPI routes) — not a finished experiment
└── draft_5agent_fragments/   one leftover draft; see the note below
```

### `docs/active/` — work in flight

| File | What it is |
|---|---|
| `design_rag_customization_sequence.md` | The RAG tool-customisation sequence. Some step statuses lag the code — verify before trusting. |
| `design_3agent_architecture.md` | **Authoritative** for the 3-agent roster, edge set and refine loop. Overrides `design_agent_count_variants.md` §7.4 and W3. |
| `topology_shared_touchpoints.md` | Every shared file a new agent must be added to, plus §G (the selector design and obstacle ledger). |
| `value_states_and_out_of_range.md` | LOCKED / SOFT TARGET / FREE, the out-of-range 2×2, and the full case matrix. Merged from three files — read Part B, then A, then C. |

### `docs/reference/` — durable

`web_interface_notes.md` · `cloud_architecture_notes.md` · `cloud_deploy_runbook.md`
· `OCR_technology_notes.md` · `benchmark_suite.md` · `design_prompt_caching.md`
· `design_agent_count_variants.md` (rationale; partly superseded — see its banner)
· `design_tool_merges.md` (a decision brief still awaiting owner answers)

### `docs/archive/` — history

`agent_count_variants_build_tracker.md` (the 5-agent build log; its file-local
`A1`–`A7` were renamed from `F1`–`F7` to end a collision with the global ids) ·
`design_precision_sections_match.md` (closed, §10 records the two production
runs) · `docs/archive/scripts/build_agent_table_v5.py` (⚠ regenerating it overwrites a sheet
it cannot reproduce — read its header).

---

## ID namespaces — six of them, and they do not share a counter

| Prefix | Lives in | Meaning |
|---|---|---|
| `F` | `TODO_known_issues.md` | future work / defects. Next free: **F94**. `F36` reserved on a sibling branch. |
| `O` / `OPS` / `R` | `TODO_known_issues.md` | open issues / pre-deploy ops / resolved |
| `W` | `warnings_developer.md` | invariants. Next free: **W43**. |
| `T` | `db_design/database_and_RAG_architecture.md` | deferred DB/RAG items |
| `D` | `db_design/database_design_notes.md` | DB doctrine decisions |
| `A` | `docs/archive/agent_count_variants_build_tracker.md` | file-local, closed |

**Ids are never reused and never renumbered.** ~19 `F`/`O` ids and 24 `W` ids are
cited from live source, and the `F` counter is a single space reserved across git
branches. A prefix only means something *together with its file* — `F1` in the
build tracker meant something completely different from `F1` in the tracker,
which is why the former is now `A1`.

---

## Things that look removable and are not

- **Five 0-byte `.md` fragments are load-bearing**, two of them in a way that
  crashes the app at import and two in a way that silently changes a prompt with
  no error. Read `warnings_developer.md` **W42** before deleting any empty file.
- **`db_design/migrations/*.py` are not one-off scripts.** Schema v8 still
  prescribes running them on non-empty databases, and `migrate_v7_to_v8.py:92` is
  the only *idempotent* creator of the live `chunks_mm` table.
- **Old schema files v2–v7 are each cited** — from production code
  (`web_app.py:1124` → v5), from `loader.py:81` (→ v6), or by an explicit
  retention decision in `database_and_RAG_architecture.md:4`.
- **`embedding_tests/` is live**, not a finished experiment: `web_app.py`
  imports it and serves 8 routes; `sketches/` is enumerated at runtime, so every
  image in it is a corpus row.
- **`prompt_efficiency/PROMPT_SHRINK_PROPOSAL_7agent.md` is append-only** — it is
  cited by exact line number from `docs/reference/design_tool_merges.md`.
- **`draft_5agent_fragments/routing_boilerplate.md`** is a leftover draft whose
  siblings were deleted as they landed. It is kept pending a check that its
  `NATURAL_PIPELINE` string still matches what the code emits. ⚠ Its
  "RELATED LIVE FINDING" section is **stale**: it says no live agent emits the
  `Input directory:` / `Extraction output file:` labels, but `fa5e2f5`
  (2026-08-03, two days after that was traced) made
  `agents/orchestrator/prompt.md:54-55` emit them unconditionally, fed by
  `agents/dispatch.py:329`.

---

## Five paths named in the docs that are not files

Traced 2026-08-21. **None of them is rot to be deleted** — they fall into two
groups, and each citation now says which.

**Delivered, then removed.** Both were real files, absorbed into the shipped
5-agent prompts and deleted in `b2f2a31` (2026-08-01):

| Path | Landed as |
|---|---|
| `draft_prompt_conductor.md` | `agents/conductor/prompt_5agents.md` |
| `draft_prompt_creator.md` | `agents/creator/prompt_5agents.md` |

**Planned, never written.** Zero commits have ever touched these paths. They
are forward references inside open work items — a described intent, not a
broken link:

| Path | Described in |
|---|---|
| `reembed_corpus.py` | `db_design/database_design_notes.md` D14 |
| `smoke_test_context_pruner.py` | `TODO_known_issues.md`, "Suggested test layout" |
| `smoke_test_dh_multi.py` | `TODO_known_issues.md`, "Suggested test layout" |

The two smoke tests are already marked `(new)` where they appear. `D14`
presented `reembed_corpus.py` as an existing standalone CLI and now says
PLANNED.
