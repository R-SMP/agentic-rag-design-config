# Database design notes (v5+ cloud RAG corpus)

This file records every design decision made about the persistent database that
backs the cloud version of the multi-agent design configurator. It is the
authoritative reference for `chunks`, `sessions`, `dc_attempts`,
`dc_attempt_parameters`, and `dc_parameter_schemas`.

For the *open* items still being decided, see `TODO_known_issues.md`. For
runtime invariants that apply regardless of storage layer, see
`warnings_developer.md`.

---

## D1. Engine and extension

- **Postgres + pgvector** (>= 0.5) regardless of host.
- Hosted as **Railway Postgres** for MVP (chosen alongside Railway as backend
  host). Migration to **Azure Database for PostgreSQL Flexible Server** is the
  documented production path; the schema is identical.

## D2. Index policy

- **HNSW from day one** on `chunks.embedding` (cosine ops). Supersedes the
  "Flat / sequential scan for now" line in the prior database-structure
  spreadsheet's "Semantic Closest Entry" sheet.
- Quantitative search uses **flat / sequential scan** of
  `dc_attempt_parameters` joined to `dc_parameter_schemas`. HNSW does not
  apply because the masked-SSD operator is not indexable. Expected to remain
  fine until ~1M attempts.

## D3. Schema-evolution doctrine

- **Field name lives in a value, not in a column header.** Adding a new
  question, new agent, new field type means new *rows* — never new columns.
  No `ALTER TABLE` for content evolution.
- **Schema version replication in `dc_parameter_schemas`.** Every parameter
  in every active version is recorded *even if unchanged from the previous
  version*. Trade-off: bigger table for cleaner queries
  (`WHERE schema_version = N` returns the complete schema with no fallback
  logic). Worth the disk.
- **Manual schema bumps for now.** When the DC parameter inventory changes
  (range, name, addition, retirement), insert new rows into
  `dc_parameter_schemas` by hand with `schema_version = previous + 1`.
  See `TODO_known_issues.md` for the future auto-loader.
- **Schema version recorded twice** (on `sessions.schema_version` and on
  every `dc_attempts.schema_version`). The redundancy is invariant: all
  attempts of one session share the same schema version because the DC is
  not redeployed mid-session.

## D4. Identity and linkage

- **Double-ID system.** `session_id` ties chunks to their parent session;
  `attempt_id` (NULLable) ties Quantitative chunks AND attempt-specific
  Semantic chunks to one specific attempt within that session. Without
  `attempt_id`, you cannot tell "Successful parameters" of attempt 1701
  from attempt 1702 in the same session. **Critical** — this is what makes
  per-attempt retrieval possible.
- **`agent_from` is set by Python**, not by the Database Handler. The save
  code knows which agent is being interviewed.
- **`agents_to` is also set by Python**, via a `agents_to_for(agent_from,
  field)` lookup table in the save code. The DH never touches the
  access-control list. To broaden access without re-running sessions, edit
  the lookup and run a one-shot `UPDATE chunks SET agents_to = ... WHERE
  ...` script.

## D5. Three classes of chunk

| Class | When | `attempt_id` | `embedding` | Example field |
|---|---|---|---|---|
| Session-level Semantic | post-mortem about the whole session | NULL | populated | "Receptionist Response problem" |
| Attempt-level Semantic | post-mortem about one specific attempt | populated | populated | "Which was the best attempt?" → points to the named-best attempt |
| Quantitative | always describes one attempt | populated | NULL | "Successful parameters - DCIC" |

The Python `SCHEDULE` carries a per-field `attempt_scope` flag
(`'session'` or `'attempt'`). The save code uses it to decide whether
`chunks.attempt_id` is NULL or set. The schema does not encode the rule —
it just stores the result.

## D6. Quantitative — double-format storage

- The same parameter content lives in **`chunks.body`** (JSON, in the
  catalog, for human readability and unified retrieval) and in
  **`dc_attempts.parameters_json`** (JSONB, source of truth for masked-RMSE
  query construction).
- The single-transaction save (D9) guarantees they never diverge. If you
  ever change one writer, change the other in the same commit.
- **`dc_attempt_parameters` is the long-format scalar mirror.** One row per
  `(attempt_id, param_name)`, holding `raw_value` only. Joined to
  `dc_parameter_schemas` at query time to compute `norm_value` on the fly.
- This double-format storage may evolve — re-evaluate once we have actual
  retrieval-performance data on real corpus sizes.

## D7. Normalisation rule

- `norm_value = (raw_value - schema.min_value) / (schema.max_value -
  schema.min_value)`, computed at query time via JOIN to
  `dc_parameter_schemas`. **Never stored.**
- The JOIN targets the **current** (most recent active, `retired_at IS
  NULL`) schema entry per `param_name`. This means old attempts are
  renormalised under today's ranges, so masked-RMSE queries can compare
  attempts across all schema versions on a common scale.
- `param_name`, `min_value`, `max_value`, and `unit` mirror the Grasshopper
  input names declared in
  `DC_prompt_fragments/dc_config/parameter_keys.txt` and
  `DC_prompt_fragments/dc_config/parameters.md`. The Grasshopper file is
  the source of truth; `dc_parameter_schemas` reflects whatever is
  declared there at the moment of each schema bump.

## D8. Masked-RMSE behaviour quirks

1. **Parameter retired between versions** → not in `chosen_parameters`,
   not in the mask, ignored. Old attempt rows for the retired parameter
   are left in place but contribute nothing.
2. **Old attempt missing a parameter that exists in the current schema**
   → that dimension is masked out *for that specific candidate*.
   Effective mask = `chosen_parameters ∧ candidate_has_this_param`.
   Consequence: candidates with different effective masks produce
   different-sized RMSEs. **The result-set must always carry "matched
   dims = k" alongside RMSE so consumers know how comparable the values
   are.**
3. **Old `raw_value` falls outside the current `(min, max)`** →
   `norm_value` is < 0 or > 1. **This is intentional and must not be
   clipped** — it correctly signals "out of current range".

## D9. Single-transaction save

Every saved session writes to four tables in **one Postgres transaction**:
`sessions`, `chunks`, `dc_attempts`, `dc_attempt_parameters`. A partial
failure rolls back fully. There is no half-saved state in the database.
DDL boot order: `sessions → dc_attempts → dc_attempt_parameters → chunks`
(chunks last because of the `attempt_id` FK).

## D10. Outcome semantics

- **`dc_attempts.outcome`** is per-attempt: the verdict the DC Output
  Inspector gave to that specific attempt (`'APPROVE' | 'REVISE' | NULL`).
- **`sessions.final_outcome`** is session-level. The rule is:
  **"APPROVE if any attempt was approved, else the last attempt's
  outcome."** This is computed by the save code, not denormalised onto
  `chunks`. There is no `chunks.outcome` column — consumers JOIN to
  `sessions.final_outcome` if they need it.
- **The Database Handler is responsible for asking the system for the
  per-attempt outcomes** during the save interview, so the save code can
  apply the rule. This is a DH-side schedule item, not an automated DB
  trigger.

## D11. Embedding contract

- **Vector text construction (Option B).**
  `text_to_embed = f"{field}\n{question}\n{body}"`. The vector encodes
  schema context, so `agent_from = 'planner'` + cosine ranking does most
  of the discrimination work without needing per-field filters.
- **`question` is stored verbatim** as the DH actually asked it, not a
  generic version. The same field can have slightly different question
  phrasings across sessions — that's intentional and the embedding picks
  it up.
- **Embedding model string convention.** `provider/model/dims`, e.g.
  `openai/text-embedding-3-large/1024`. Used as the join key for
  "old + new vectors coexist" and for migration scripts.
- **Re-embedding under a new model creates new rows** (because
  `embedding_model` is part of the UNIQUE key), it does not UPDATE.
  Approximately doubles row count until you decide to delete the
  old-model rows.
- **Body-length cap is enforced upstream by the Database Handler**
  (~700 cl100k tokens, prefer <600 for Semantic; no cap for
  Quantitative). The storage layer applies no truncation —
  `chunks.body TEXT` has no length limit.

## D12. Access-control invariant

- The DB schema enforces nothing on `agents_to` directly. The
  invariant is enforced **at the agent retrieval-tool layer** by a
  single `AgentQueryTool` constructed per agent with the requesting
  identity pinned at construction time. The access filter
  `WHERE <pinned_agent> = ANY(agents_to)` is injected unconditionally
  into every query — not a parameter the agent can override or omit.
- Optional defence-in-depth: enable Postgres Row-Level Security so
  the DB rejects any query that doesn't carry the pinned agent
  identity. Defer until the tool layer is in place and tested.

## D13. Filter-then-search vs search-then-filter

- All filters go in the SQL `WHERE` clause. Postgres' query planner
  picks the execution order (filter-first via B-tree/GIN indexes or
  vector-first via HNSW + post-filter) per query, based on live
  table statistics. The result set is identical either way; only
  speed differs.
- **Never pull candidates into Python and rank there** — that bypasses
  every index and the planner. The single exception is masked-RMSE,
  which has no indexable operator and uses sequential scan inside
  Postgres (PL/pgSQL or expression).

## D14. Re-embedding script

- Standalone CLI: `extra_utilities/reembed_corpus.py`. Run only
  when the embedding model genuinely changes
  (`EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, or
  `EMBEDDING_VECTOR_DIMS` in `workflow_settings/settings.py`).
- Iterates every Semantic chunk under the *old* model, computes the
  new vector under the new model, INSERTs as a new row with the new
  `embedding_model` value. Old rows survive — they coexist with the
  new ones. A separate `prune_old_embeddings.py` script can delete
  superseded rows when explicitly invoked.

## D15. Save trigger and the user-facing "Save" button

The single-transaction save in D9 is invoked from exactly one user
action: pressing **"Save"** in the web UI at end-of-session.  This
button is **not present in Stage A** — Stage A ships a Streamlit
chat with only an **"End Session"** control that clears
`st.session_state` and reloads with no DB write.  The "Save"
button arrives in **Stage B**, alongside Phase 2 (DB schema +
save flow) and the wiring of the DH into the Streamlit handler.

Implications for the schema:

- **No row in `sessions`, `dc_attempts`, `dc_attempt_parameters`,
  or `chunks` is ever written by Stage A.**  Stage A traffic
  produces no DB activity at all.  This is why Phase 6 brings up
  Postgres locally but the Stage A Streamlit pod has no
  `DATABASE_URL` requirement — the connection is provisioned but
  unused.
- **The Phase 2 save code can assume the user explicitly opted in.**
  No silent saves on browser close / Ctrl-C / unhandled exception
  in Stage B either, by analogy with `warnings_developer.md` W8.
- **One Save click → one D9 transaction.**  Re-clicking Save inside
  the same session is a no-op (the `sessions.session_id` UNIQUE
  constraint and the `chunks` UNIQUE on
  `(session_id, agent_from, field, embedding_model)` would reject
  duplicates anyway, but the UI should disable the button after
  the first successful save rather than rely on the DB to fail).

See also: `cloud_architecture_notes.md` C6 (Stage A UI control
labelling); `TODO_known_issues.md` O10 (open Stage B UX questions
for the Save button); `warnings_developer.md` W14 (do-not-add-Save
discipline for Stage A).

---

## Quick-reference DDL

The current authoritative DDL for the five tables. Re-paste here when
anything changes.

```sql
-- sessions: parent table, one row per saved session
CREATE TABLE sessions (
  session_id            TEXT PRIMARY KEY,
  session_ts            TIMESTAMPTZ NOT NULL,
  user_id               TEXT,
  dc_name               TEXT NOT NULL,
  dc_inspector_enabled  BOOLEAN NOT NULL,
  schema_version        INTEGER NOT NULL,
  final_outcome         TEXT,
  notes                 TEXT,
  saved_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- dc_parameter_schemas: versioned parameter inventory
CREATE TABLE dc_parameter_schemas (
  schema_version  INTEGER NOT NULL,
  param_name      TEXT NOT NULL,
  min_value       DOUBLE PRECISION NOT NULL,
  max_value       DOUBLE PRECISION NOT NULL,
  unit            TEXT,
  description     TEXT,
  introduced_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  retired_at      TIMESTAMPTZ,
  PRIMARY KEY (schema_version, param_name)
);

-- dc_attempts: one row per attempt iterated through during a session
CREATE TABLE dc_attempts (
  attempt_id        BIGSERIAL PRIMARY KEY,
  session_id        TEXT NOT NULL REFERENCES sessions(session_id),
  attempt_label     TEXT NOT NULL,
  schema_version    INTEGER NOT NULL,
  parameters_json   JSONB NOT NULL,
  outcome           TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (session_id, attempt_label)
);
CREATE INDEX dc_attempts_session         ON dc_attempts (session_id);
CREATE INDEX dc_attempts_schema_version  ON dc_attempts (schema_version);

-- dc_attempt_parameters: long-format scalar mirror for masked-RMSE
CREATE TABLE dc_attempt_parameters (
  attempt_id  BIGINT NOT NULL REFERENCES dc_attempts(attempt_id) ON DELETE CASCADE,
  param_name  TEXT NOT NULL,
  raw_value   DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (attempt_id, param_name)
);
CREATE INDEX dc_attempt_params_param ON dc_attempt_parameters (param_name, raw_value);

-- chunks: unified RAG corpus catalog, many rows per session
CREATE TABLE chunks (
  id              BIGSERIAL PRIMARY KEY,
  session_id      TEXT NOT NULL REFERENCES sessions(session_id),
  attempt_id      BIGINT REFERENCES dc_attempts(attempt_id),
  agent_from      TEXT NOT NULL,
  agents_to       TEXT[] NOT NULL,
  field           TEXT NOT NULL,
  field_type      TEXT NOT NULL,
  question        TEXT,
  body            TEXT NOT NULL,
  embedding       vector(1024),
  embedding_model TEXT,
  is_error        BOOLEAN NOT NULL DEFAULT FALSE,
  is_empty        BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (session_id, agent_from, field, embedding_model)
);
CREATE INDEX chunks_emb_hnsw    ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_agent_from  ON chunks (agent_from);
CREATE INDEX chunks_agents_to   ON chunks USING gin (agents_to);
CREATE INDEX chunks_session     ON chunks (session_id);
CREATE INDEX chunks_attempt     ON chunks (attempt_id);
CREATE INDEX chunks_field       ON chunks (field);
```
