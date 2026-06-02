# Database and RAG Architecture — Design Decisions

**Status:** design phase. Implementation begins after the user gives the go-ahead.
**Companion file:** `database_PostgreSQL_schema_v4.sql` (in this folder). v4 = v3 + all §3 decisions locked 2026-06-01 (CHECK constraint on chunks, partial HNSW index, rag_queries log table). `database_PostgreSQL_schema_v2.sql` and `_v3.sql` kept as historical records.
**Last updated:** 2026-06-01.

This file captures every architectural decision made during the
6 March meeting design discussion on the PostgreSQL backend and the
RAG layer that sits on top of it. It is the single source of truth
for these choices until they migrate into the project repo
(`extra_utilities/database_design_notes.md` is the eventual target
once decisions are locked).

---

## 1. Database schema (v2)

Five tables; see `database_PostgreSQL_schema_v2.sql` for the
full DDL. Headline points:

| Table | Role |
|---|---|
| `dc_parameter_schemas` | Versioned parameter inventory (composite PK on `schema_version, param_name`). |
| `sessions` | Parent table, one row per saved session. |
| `dc_attempts` | One row per design iteration within a session. |
| `chunks` | Unified RAG corpus — many rows per session. Vector(1024) + HNSW. |
| `dc_attempt_parameters` | Long-format scalar mirror of attempt params for masked-RMSE queries. |

Schema-version evolution rules (from the meeting):

| Event | What changes |
|---|---|
| Add a parameter to a DC | Insert one row into `dc_parameter_schemas` with new `schema_version`. New attempts gain one extra row in `dc_attempt_parameters`. Old attempts unchanged. |
| Remove a parameter | Set `retired_at` in `dc_parameter_schemas`. New attempts stop recording it. Old attempts keep their existing rows. |
| Rename a parameter | New `schema_version` with the renamed entry. Old data stays addressable under its original `schema_version`. |
| Change a parameter's range (min/max) | New `schema_version` with updated normalisation. Old attempts queryable under their version's normalisation; new attempts use the new one. |

> **End-Session feedback questions are NOT versioned via
> `schema_version`.**  They live in code
> (`FIXED_FEEDBACK_QUESTIONS` in `workflow_settings/fixed_feedback_questions.py`)
> and are mirrored to `chunks` rows.  Adding a feedback question is
> a code edit; no schema bump is required because the chunks mirror
> is open-ended and `sessions.feedback` is labelled-block text.  See
> §3.3 + §3.7.

---

## 2. Schema changes accepted in this discussion

### 2.1 Metafilter columns (new)

Add these columns to support the metafilter feature in the
`database_search` tool. Add now even though the tool ships later.

**On `sessions`:**
```sql
ALTER TABLE sessions
  ADD COLUMN user_provided_images BOOLEAN NOT NULL DEFAULT FALSE;
```

**On `dc_attempts`:**
```sql
ALTER TABLE dc_attempts
  ADD COLUMN has_geometry BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN has_renders  BOOLEAN NOT NULL DEFAULT FALSE;

-- Partial indexes (TRUE is usually the minority):
CREATE INDEX idx_dc_attempts_has_geometry ON dc_attempts(attempt_id) WHERE has_geometry;
CREATE INDEX idx_dc_attempts_has_renders  ON dc_attempts(attempt_id) WHERE has_renders;
```

**On `chunks`** (required by the locked Option B embedding format — see §6):
```sql
ALTER TABLE chunks
  ADD COLUMN embedding_input TEXT;
-- Stores the exact natural-language stitched paragraph that was fed
-- to text-embedding-3-large. Kept separate from `body` so the
-- canonical Q/A text stays untouched and re-embedding remains
-- reproducible. Nullable for Quantitative rows (no embedding) and
-- legacy rows.
```

### 2.2 Metafilters supported by columns already present in v2

These need no new columns, just indexes and tool wiring:

| Metafilter | Source column | Index needed? |
|---|---|---|
| `dc_name` exact match | `sessions.dc_name` | Yes — add `CREATE INDEX idx_sessions_dc_name ON sessions(dc_name);` |
| `satisfaction >= X` | `sessions.satisfaction` | Yes — `CREATE INDEX idx_sessions_satisfaction ON sessions(satisfaction) WHERE satisfaction IS NOT NULL;` |
| `session_ts` range | `sessions.session_ts` | Yes — `CREATE INDEX idx_sessions_session_ts ON sessions(session_ts);` |
| `schema_version` exact | `sessions.schema_version` and `dc_attempts.schema_version` | `dc_attempts.schema_version` already indexed; add `CREATE INDEX idx_sessions_schema_version ON sessions(schema_version);` |
| Has any feedback | derived: `satisfaction IS NOT NULL OR feedback_what_worked IS NOT NULL OR feedback_what_didnt IS NOT NULL` | Optional expression index later |
| `agent_from` exact | `chunks.agent_from` | Already indexed |
| `field` exact | `chunks.field` | Already indexed (but see TODO below — usage pattern not yet locked) |
| `dc_inspector_enabled` | `sessions.dc_inspector_enabled` | Optional |
| `user_id` exact (post-F22) | `sessions.user_id` | Yes — `CREATE INDEX idx_sessions_user_id ON sessions(user_id) WHERE user_id IS NOT NULL;` |
| Parameter value ranges (e.g. `bladeCount >= 5`) | `dc_attempt_parameters (param_name, raw_value)` | Already indexed |

### 2.3 Metafilters explicitly rejected

- **`chosen_for_user`, `dcii_verdict`, `dcoi_verdict`** — user does not want these.
- **Number of attempts in session** — derivable, low value as a hard filter.
- **Free-text body filters** — that's what the semantic search is for.

---

## 3. Schema additions and write-reliability behaviour locked 2026-06-01

These four items were "pending" earlier and have now all been
**accepted**. The schema changes appear in `database_PostgreSQL_schema_v4.sql`;
the runtime behaviour described in §3.5 is application-layer and does
not change the SQL itself.

### 3.1 CHECK constraint linking `chunks.field_type` ↔ `embedding` / `embedding_model`

```sql
ALTER TABLE chunks
  ADD CONSTRAINT chunks_embedding_consistent_with_field_type CHECK (
    (field_type = 'Quantitative' AND embedding IS NULL AND embedding_model IS NULL)
    OR
    (field_type = 'Semantic'     AND embedding IS NOT NULL AND embedding_model IS NOT NULL)
  );
```

Prevents three classes of silent data corruption:
- Semantic rows with NULL embedding — unsearchable orphans inflating
  the corpus count.
- Quantitative rows with an embedding set — wasted vector slot, may
  surface in semantic searches it shouldn't.
- Semantic rows with embedding but no `embedding_model` — the
  model-mismatch skip rule at query time (§4.9) cannot be applied
  because the row's model is unknown.

**Behaviour on violation:** see §3.5 — the Database Handler retries
the INSERT up to `DATABASE_ENTRY_MAX_RETRIES` times. If still failing,
the Q+A is saved to the R2 safety folder instead.

> **v5 addendum (2026-06-02).** The constraint was relaxed in schema
> v5 to allow Semantic rows with `is_empty = TRUE` to carry NULL
> `embedding` + NULL `embedding_model`.  The constraint now reads as
> a three-arm disjunction:
>
> ```sql
> CONSTRAINT chunks_embedding_consistent_with_field_type CHECK (
>     (field_type = 'Quantitative' AND embedding IS NULL     AND embedding_model IS NULL)
>     OR
>     (field_type = 'Semantic'     AND is_empty)
>     OR
>     (field_type = 'Semantic'     AND embedding IS NOT NULL AND embedding_model IS NOT NULL)
> );
> ```
>
> The third arm is unchanged from v4 (the original Semantic row
> shape).  The middle arm is new: it permits the End-Session
> feedback safety-net rows.  When a user does not answer one of the
> fixed feedback questions at End Session time, the Database Handler
> still writes a `chunks` row for that question with `is_empty=TRUE`,
> `body=""`, `embedding=NULL`, `embedding_model=NULL`.  Rationale:
> downstream consumers see an explicit "asked but not answered"
> marker (audit-trail behaviour) rather than missing the row
> entirely.  The partial HNSW index (§3.2) already excludes
> `is_empty` rows, so the relaxation does NOT affect retrieval.

### 3.2 Partial HNSW index excluding error / empty / Quantitative rows

```sql
DROP INDEX IF EXISTS idx_chunks_embedding;
CREATE INDEX idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops)
  WHERE NOT is_error AND NOT is_empty AND field_type = 'Semantic';
```

Smaller index → less RAM, faster index builds, faster vector queries.
The index ignores rows that retrieval would never return anyway
(error / empty / Quantitative).

**REQUIRED query template** — Postgres only uses a partial index when
the query's `WHERE` clause logically implies the index's `WHERE`.
Every vector search query MUST include exactly these three predicates:

```sql
SELECT ...
FROM chunks
WHERE NOT is_error
  AND NOT is_empty
  AND field_type = 'Semantic'
  AND ...   -- additional filters: agents_to ACL, embedding_model match, metafilters
ORDER BY embedding <=> $query_vec
LIMIT $k;
```

Forgetting any of the three predicates causes Postgres to fall back to
a sequential scan — correct but ~1000× slower with no warning. The
backend implementation locks this prefix into a single helper function
(see §8 invariant 8).

### 3.3 End-Session feedback — `sessions.feedback` + `chunks` rows

> **Rewritten 2026-06-02** to reflect the v5 collapse of
> `sessions.feedback_what_worked` + `sessions.feedback_what_didnt`
> into a single `sessions.feedback TEXT` column (see the v5
> changelog at the top of
> `database_PostgreSQL_schema_v5.sql`).  Behaviour for the `chunks`
> mirror is unchanged from the v4 design.

When the user submits the End Session modal, the backend writes:

1. **ONE row update on `sessions`** populating two columns —
   `sessions.satisfaction` (the numeric quick-score, 0–10) and
   `sessions.feedback` (a single `TEXT` column, v5).  When the user
   answered both feedback questions, the column holds a labelled-
   block concatenation:

   ```
   --- Positive ---
   <answer to "What worked well in this session?">

   --- Negative ---
   <answer to "What didn't work well?">
   ```

   When only one question was answered, only that block appears.
   When neither was answered, the column stays NULL.  The labelled-
   block format is the same delimiter convention used by the DH's
   per-Q+A files on disk, so a human reading the column directly
   sees the structure immediately.  The format is open-ended: a
   future third feedback question just appends another labelled
   block (e.g. `--- Suggestion ---`), no schema change required.

2. **UP TO TWO extra rows on `chunks`**, one per answered question.
   An unanswered question is NOT written (no empty / placeholder
   row).  When a question is answered, the row is:
   - `agent_from = 'User'`
   - `agents_to = DEFAULT_AGENTS_TO_ACL` (the 9 primary chain agents
     — see §3.6 + invariant 14)
   - `field = 'Positive User Comments'`  *(for the "what worked"
     question)*  OR  `field = 'Negative User Comments'`  *(for the
     "what didn't" question)*
   - `field_type = 'Semantic'`
   - `body = <raw answer text from the modal>`
   - `question = <the exact fixed question wording>`
   - `embedding_input` = the Option-B stitched paragraph
   - `embedding`, `embedding_model` populated as usual
   - `attempt_id = NULL` (session-scoped)

The text remains in the `sessions` table for analytics (quick
session-level scans, no JSON parsing needed); the chunks copies are
the **retrieval surface**.  Agents can semantically retrieve real
user feedback through the `database_search` tool — e.g. *"what did
past users say about thin propellers?"* surfaces relevant
Positive / Negative User Comments rows.

**Question wording is fixed in code, NOT in the dh_schedule.**  The
two questions are defined in `FIXED_FEEDBACK_QUESTIONS` in
`workflow_settings/dh_schedule.py` (a developer constant) and
rendered as a read-only table at the bottom of the "Questions for
Saved Sessions" web view — see §3.7.  Adding a third feedback
question is a code edit (append to the constant); no schema
migration is required because the `chunks` mirror is open-ended
and `sessions.feedback` is just appended labelled-block text.

### 3.4 `rag_queries` log table

Every call to the `database_search` tool is logged for debugging,
offline evaluation, usage analytics, and cost tracking.

```sql
CREATE TABLE rag_queries (
  id                  BIGSERIAL    PRIMARY KEY,
  ts                  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  session_id          TEXT         REFERENCES sessions(session_id) ON DELETE SET NULL,
  caller_agent        TEXT         NOT NULL,                          -- which agent called the tool
  query_text          TEXT,                                            -- the input_key_text
  query_params        JSONB,                                           -- input_key_parameters_list (TODO T1)
  n_requested         INTEGER      NOT NULL,
  attempt_specific    BOOLEAN      NOT NULL,
  metafilters         JSONB,                                           -- the METAFILTERS dict
  embedding_model     TEXT,                                            -- model used to embed the query
  n_returned          INTEGER      NOT NULL,                           -- distinct anchors returned
  returned_anchor_ids JSONB,                                           -- [{session_id, attempt_id?, score}, ...]
  skipped_count       INTEGER      NOT NULL DEFAULT 0,                 -- rows skipped due to embedding-model mismatch
  truncated_anchors   INTEGER      NOT NULL DEFAULT 0,                 -- anchors dropped by token cap
  latency_ms          INTEGER,
  error_message       TEXT
);
CREATE INDEX idx_rag_queries_ts            ON rag_queries(ts);
CREATE INDEX idx_rag_queries_session_id    ON rag_queries(session_id);
CREATE INDEX idx_rag_queries_caller_agent  ON rag_queries(caller_agent);
```

Notes:
- `ON DELETE SET NULL` on the session FK so deleting a session leaves
  its query history intact (useful for cross-session analytics).
- Retention policy is a follow-up decision — see T13 in §7.

### 3.5 DH retry behaviour and R2 safety fallback

> **R2 is the failure escape hatch, not the primary store.** In the
> happy path, DH-saved Q+A text lives **only** in the Postgres
> `chunks` table — there is no R2 mirror for Q+A text in this
> architecture. This is a deliberate change from earlier v9 R2 dual /
> 3-path behaviour where Q+A was always mirrored to R2. The R2
> safety folder described below is exclusively where Q+A goes when
> `DATABASE_ENTRY_MAX_RETRIES` is exhausted on the Postgres INSERT.
>
> Other session artefacts that don't fit in Postgres — mesh files,
> renders, user-provided input images — continue to live on R2 as
> before; this scope change applies to Q+A text only.

When an INSERT into `chunks` fails (e.g. CHECK constraint violation
from §3.1, NOT NULL violation, transient DB error, embedding-pipeline
failure that leaves `embedding_model` NULL on a Semantic row), the
Database Handler reacts as follows:

#### 3.5.1 New workflow-settings variable: `DATABASE_ENTRY_MAX_RETRIES`

A new variable added to the workflow-settings UI, customisable by the
developer.

- **Default value:** `3`
- **Description text (shown next to the setting in the dev UI):**

  > Maximum number of attempts the Database Handler makes to INSERT a
  > Q+A row into the `chunks` table when the insert fails (CHECK
  > constraint violation, embedding-pipeline error, transient DB error,
  > etc.). If all attempts are exhausted, the Q+A is written to the R2
  > safety folder for the session and skipped from the database. Set
  > higher if you see transient errors frequently; set lower if you
  > want fast failover to safety storage.

- **Example:** a Semantic Q+A is generated, but the embedding-API call
  is rate-limited and returns no vector. With
  `DATABASE_ENTRY_MAX_RETRIES = 3`, the DH retries the
  embed-then-insert flow up to 3 times. If still failing on the 3rd
  retry, the raw Q+A is saved to
  `<session_id>/safety/.../<filename>.txt` in R2 so no user data is
  lost.

#### 3.5.2 Retry rules

1. **Retry on:** CHECK violation (after the DH fixes the inputs, e.g.
   re-runs the embedding), NOT NULL violation, transient DB error,
   network timeout.
2. **Do NOT retry on `UNIQUE` violation.** That means a row already
   exists for `(session_id, agent_from, field, attempt_id, item_index,
   embedding_model)` — an earlier save succeeded; skip silently.
3. Backoff strategy between retries (fixed delay, exponential, etc.)
   is an implementation detail not pinned here.

#### 3.5.3 R2 safety folder — structure (locked from user's choice)

Layout: **Option C — grouped by anchor inside one `safety/`**

```
<session_id>/
  safety/
    session/                          # session-generic failures live here
      <field>.txt                     # e.g. Plan.txt
      <field>_M.txt                   # e.g. Plan_2.txt (multi-answer split index 2)
    attempt_<NNN>/                    # one folder per attempt with at least one failure
      <field>__<NNN>.txt              # e.g. BadAttempt__001.txt
      <field>__<NNN>_M.txt            # e.g. BadAttempt__001_2.txt
```

- **Filename**: same as the DH source filename — exactly matches the
  v9 DH filename matrix
  (`<field>.txt` / `<field>_M.txt` / `<field>__NNN.txt` / `<field>__NNN_M.txt`)
  so a recovery script can pair safety ↔ source trivially.
- **One file per failed Q (flat).** No bundling, even in the cascade
  scenario (§3.5.5) — each cascaded Q is its own file.

#### 3.5.4 Safety-file content (locked format)

Each safety file contains a diagnostic header followed by the canonical
v9 Q+A block:

```
--- SAFETY-SAVE DIAGNOSTIC ---
Timestamp:                 2026-06-01T14:30:52Z
Retry count:               3 of 3
Last DB error:             chunks_embedding_consistent_with_field_type CHECK violation:
                           field_type='Semantic' but embedding IS NULL
Field type:                Semantic
Attempt ID:                001            (or "session-generic")
Cascade source:            (none)         (or "identifying-Q for attempt_001 failed -
                                            see <field>__001.txt in this folder")
Agents allowed to access this answer:  Receptionist, DH, DCII, DCOI, Planner
--- Field ---
<field_name>
--- Question ---
<question_text>
--- Answer ---
<answer_text>
```

The `Agents allowed to access this answer:` line preserves the
`agents_to` ACL so a recovery script (and a human reader) knows who
could have seen this chunk had it landed in the DB.

#### 3.5.5 Cascade behaviour for identifying-Q failures

If the failed Q+A is an **identifying attempt-related question** (the
question that establishes an attempt's identity in the dialogue), then
**all subsequent attempt-related Q+A for that same attempt are also
routed to the safety folder** — they cannot be safely inserted into
the DB because their parent attempt's identity row is not in a
consistent state.

- Each cascaded Q is saved as its own safety file in the same
  `attempt_<NNN>/` folder (flat layout, per user's choice).
- The cascaded files' diagnostic header records the original failure
  as the cause:
  ```
  Cascade source: identifying-Q for attempt_001 failed
                  (see <field>__001.txt in this folder)
  ```

#### 3.5.6 Recovery

A separate recovery script (out of v1 scope) can later scan
`<session>/safety/` folders, re-attempt the INSERT with corrected
inputs (e.g. successfully recompute the embedding), and on success
delete the safety file. See T12 in §7 TODO list.

### 3.6 Default `agents_to` ACL when the schedule omits it

The `chunks.agents_to` column on every inserted row is populated
from the DH-schedule entry's `to_agents` list.  When that list is
empty (the default for a freshly-added schedule row, and a common
state when an operator hasn't restricted access explicitly), the
DH inserts the row with **`agents_to = [all primary agents]`** —
i.e. Receptionist, DH, DCII, DCOI, Planner, Orchestrator, UII,
DCIC, TC (the nine chain agents).

Rationale: a permissive default maximises RAG retrieval utility
(every agent can find every past Q+A) and avoids the failure mode
where a row silently becomes invisible to the RAG because the
operator forgot to set `to_agents`.

To **restrict** visibility, populate `to_agents` explicitly in the
DH-schedule editor UI (the per-row "To" cell) — the click-to-pick
popover shows a help line stating that leaving it empty means "all
agents".  The same rule is mirrored into
`extra_utilities/warnings_developer.md` (W21).

The canonical list of "primary agents" lives in **one place** — the
`DEFAULT_AGENTS_TO_ACL` constant in
`agents/database_handler/db_writer.py` (Phase 3B).  When chain
agents are added or removed, update that constant; the architecture
doc's enumeration above is descriptive only.

### 3.7 Fixed feedback questions live in code, not in the schedule

The "Questions for Saved Sessions" web view
(`/workflow-settings` → schedule editor) has TWO zones:

1. **Top table — editable.**  The DH-schedule rows the developer
   customises through the UI.  Source of truth =
   `workflow_settings/dh_schedule.json`.  Loaded, edited and saved
   through `/api/dh_schedule` (GET / POST).
2. **Bottom table — read-only / greyed-out.**  Lists the two fixed
   feedback questions asked to the user at End Session.  Source of
   truth = the `FIXED_FEEDBACK_QUESTIONS` constant in
   `workflow_settings/fixed_feedback_questions.py` (a dedicated
   module — placed in its own file rather than inside
   `dh_schedule.py` so the boundary between user-editable schedule
   and developer-fixed feedback questions is unambiguous).  Cannot
   be edited from the UI; the table is informational only.  No
   "edit", "delete" or "reorder" controls are exposed for these
   rows.

Editing the fixed questions is a **developer action**, not a user
action.  When `FIXED_FEEDBACK_QUESTIONS` changes:
- The chunks rows written by future End-Session events carry the
  new question text (`chunks.question` reflects the constant at
  write time).
- No schema migration is required (the chunks mirror is open-ended
  and `sessions.feedback` is just labelled-block text — see §3.3).
- Past sessions' `chunks` rows keep the OLD question text frozen in
  their `chunks.question` column — that is the desired audit-trail
  behaviour.

Why fix the wording in code rather than in `dh_schedule.json`?
Because changing the wording mid-deploy via the UI would create a
silent mismatch: the modal in `web/app.js` shows hardcoded prompt
text, while the schedule's "question" field would drift.  Code is
the single source of truth here so the modal and the schedule view
stay in lockstep — both are derived from `FIXED_FEEDBACK_QUESTIONS`.

---

## 4. The `database_search` tool — locked design

### 4.1 Signature

```text
database_search(
    input_key_text(s),          -- single text for now; multi-text is a TODO
    input_key_parameters_list,  -- TODO (parameter-vector search via RMSE)
    N,                          -- number of ANCHORS (see §4.3)
    attempt_specific_flag,      -- bool
    METAFILTERS                 -- dict of hard filters (see §2)
)
```

### 4.2 Per-agent access control (the "pass key")

Every agent gets the tool. Every chunk row has `chunks.agents_to TEXT[]`
listing which agents may see it. The ACL is applied **both** as a
pre-filter to the ANN search and as a post-filter on the result
display.

- **Pre-filter at search time:** `WHERE $caller_agent = ANY(agents_to)` — the
  ranking never considers rows the caller cannot see. The GIN index
  on `agents_to` makes this cheap.
- **Post-filter at display time:** the retrieve-then-expand pass also
  respects the ACL when fetching all Q/A pairs in the returned
  sessions/attempts. An agent never sees a sibling Q/A pair it
  wouldn't have been granted directly.

### 4.3 `N` semantics — N counts ANCHORS, not chunks

Locked: **`N` is the number of distinct sessions or attempts to return.**

- If `attempt_specific_flag = False`, `N` = distinct sessions.
- If `attempt_specific_flag = True`, `N` = distinct attempts.

Backend implementation: over-fetch chunks (e.g. 3×N), dedupe by
session/attempt, take the top N distinct anchors, then expand each
anchor's Q/A.

> **NOTE for developers and system prompts:** N counts anchors, not
> chunks. An agent asking for `N=5` always gets up to 5 distinct
> sessions/attempts, not up to 5 chunks.

### 4.4 `attempt_specific_flag` semantics

- **`False`** (default): search across all chunks the agent can see
  (session-generic + attempt-specific). For each session in the top
  results, expand to all Q/A pairs in that session that the agent
  can see.
- **`True`**: search only attempt-specific chunks
  (`WHERE attempt_id IS NOT NULL`); skip session-generic chunks
  entirely from both the search and the expansion. For each attempt
  in the top results, expand only to Q/A pairs within that attempt.

A `True` call always returns a **subset** of what the same call with
`False` would have returned, because session-generic and
sibling-attempt content is excluded.

### 4.5 Token cap per tool call

Locked: token cap is enforced **server-side**, configurable from the
UI as a system workflow setting (so a developer can tune it without
a redeploy).

**Trimming policy when over cap:** trim from the **lowest-ranked
anchors first**, so the most relevant anchors survive intact. Append
a footer noting what was dropped, e.g.:

```xml
<truncated reason="token_limit" omitted_anchors="2" token_cap="30000"/>
```

> **NOTE for developers and system prompts:** when results exceed
> the token cap, the backend trims from the lowest-ranked anchors
> first — never partial-anchor truncation. Agents can re-call with a
> smaller `N` or `attempt_specific_flag = True` if they need more
> diverse anchors at the same cap.

### 4.6 Response header (always present)

Every tool response opens with a small meta block stating what
filters were actually applied. Helps the calling agent reason about
why results look the way they do.

```xml
<search_meta n_requested="5"
             n_returned="3"
             attempt_specific="false"
             metafilters="has_renders=true,bladeCount>=5"
             embedding_model="openai/text-embedding-3-large/1024"
             skipped_due_to_model_mismatch="0"/>
```

### 4.7 No-results payload (two variants)

When zero anchors match, return an explicit message (never empty
string). The exact wording depends on whether metafilters were
applied:

- **If metafilters were applied:**
  > "No results found. This may be related to the metafilters
  > applied — consider relaxing them."
- **If no metafilters were applied:**
  > "No results found."

Always still include the `<search_meta>` header.

### 4.8 Score visibility

The cosine similarity score for each anchor is included in the
returned XML so the LLM can calibrate confidence (e.g. distinguish a
0.91 hit from a 0.4 hit).

### 4.9 Embedding-model mismatch handling

Locked: at query time, only rows whose `embedding_model` matches the
query's expected model are considered. Mismatched rows are **skipped**,
and the skipped count is reported in `<search_meta>` so the agent
knows coverage was reduced.

> **TODO:** add a system-settings toggle (UI-configurable) to choose
> between "skip mismatched rows" (default, current behaviour) and
> "re-embed mismatched rows on the fly with the current model and
> include them." See §7 TODO list.

### 4.10 Non-text artefacts — separate two-step retrieval (NOT in `database_search`)

The `database_search` tool **never returns** user-input images or
attempt-render images. Its XML response is text-only — `<question>`,
`<answer>`, `<search_meta>`. This is a deliberate design choice, for
two compounding reasons:

1. **Most agents don't need to see images for most queries.** A
   query like *"what worked for a thin propeller?"* is answered
   purely from the textual Q+A in the corpus. Pulling images would
   inflate the token budget on every single search regardless of
   whether the images actually help — and the architecture doc §4.5
   token cap would then evict useful text content to make room for
   images the agent didn't need.

2. **An opt-in `return_images` flag at search time would still be
   wasteful, AND it does not lift the burden from the agent.**
   The agent calling `database_search` does not yet know whether
   the sessions/attempts about to be returned will actually be
   useful for its scope. Asking it to pre-commit to image retrieval
   means it'd either request images speculatively against anchors
   it's about to ignore, or default to "no" and lose the option
   without thinking. Neither is good. The decision *"do these
   images help me?"* can only be made AFTER the agent has read the
   text content of the retrieved anchors.

Instead, image retrieval is a **separate, second-step** tool the
agent invokes only AFTER reading the text response and deciding
that a specific anchor is worth deeper inspection:

1. **Step 1 — text-only search.** Agent calls
   `database_search(...)` and reads the returned
   `<question>` / `<answer>` content for each anchor in the XML.
2. **Step 2 — selective artefact fetch.** If (and only if) the
   agent decides the text content of a specific anchor is relevant
   AND that seeing images would help, it calls a **separate**
   artefact-fetch tool (T15, see §7) naming:
   - the specific `session_id` (and optionally `attempt_id`)
   - which artefact kinds to pull:
     `user_input_images`, `attempt_renders`, both, or neither.

Consequences of this pattern:

- Agents never see images they didn't ask for.
- Image bandwidth + token cost is paid only when the agent has
  already triaged the text and committed to looking closer at a
  specific anchor.
- An agent whose role does not include looking at images at all
  (e.g. one whose work is purely numeric/parametric) simply never
  calls the artefact-fetch tool — no per-query decision to make,
  no flag to remember.
- The `database_search` tool signature stays simple: no
  `return_images` flag, no per-call image-scope dial.

The artefact-fetch tool itself is **not yet built** — see T15 in
§7 below. The current Phase 3 implementation ships only
`database_search` (text). When the artefact-fetch tool lands, the
two-step calling pattern documented here is its contract; agents
calling it before triaging text are using it wrong.

---

## 5. Output format — XML (LOCKED)

**Status:** LOCKED 2026-05-31. The `database_search` tool returns
its results as XML.

### 5.1 Rationale

XML tags for the response payload. Confirmed compatible with:

- **Claude** — Anthropic's documented preferred format.
- **OpenAI (GPT-4o, GPT-4.1, o-series)** — Officially endorsed in the
  GPT-4.1 Prompting Guide ("XML: These also perform well, and we have
  improved adherence to information in XML with this model"). XML
  outperforms JSON for embedded document collections per OpenAI's
  own long-context tests.
- **Google Gemini (1.5, 2.0, 2.5; Pro and Flash)** — Officially
  endorsed in Google's Prompt Design Strategies page ("XML-style
  tags … or Markdown headings are effective").

### 5.2 Proposed shape

```xml
<session id="21000">
  <session_generic>
    <qa agent="DH" field="Plan" score="0.91">
      <question>...</question>
      <answer>...</answer>
    </qa>
  </session_generic>
  <attempt id="001">
    <qa agent="DCII" field="Bad Attempt" score="0.87">
      <question>...</question>
      <answer>...</answer>
    </qa>
    <qa agent="DCOI" field="Render Notes" score="0.82">
      <question>...</question>
      <answer>...</answer>
    </qa>
  </attempt>
</session>
<session id="43004">
  ...
</session>
```

### 5.3 Pitfall to watch (applies to both OpenAI and Gemini)

If any `<answer>` body itself contains literal XML, switch the
delimiter for that field (e.g. fenced markdown). For our Q/A corpus
this is unlikely — answers are prose.

---

## 6. Embedding format — Option B locked (natural-language stitching)

**Status:** LOCKED 2026-05-31 on **Option B (natural-language
stitching)**. Option A (dual embeddings + RRF) is **deferred** to
the TODO list as T11 — possible future upgrade if Option B's
retrieval quality proves insufficient once real usage data is
available.

The choice affects what string is fed to `text-embedding-3-large` at
index time. The locked design respects the existing `vector(1024)`
column and the HNSW index.

### 6.1 Option B — Natural-language stitching, single embedding (LOCKED)

At index time, the system uses an LLM to rewrite Field + Question +
Answer into a single coherent declarative paragraph, then embeds
that paragraph with `text-embedding-3-large`.

**Example rewrite of the current saved format:**

Raw (the format currently saved on disk):
```
--- Field ---
Bad Attempt
--- Question ---
Which design attempt was the weakest match to the user's requirements?
--- Answer ---
No attempt was a clear mismatch. All three designs met the core
requirements of a continuous ring, a central hub, and five broad
blades connecting hub to ring. The second attempt was the weakest
overall match because its ring read noticeably heavier than the
sketch intent, which called for a relatively thin ring. ...
```

Stitched (what actually gets embedded — stored in
`chunks.embedding_input`):
> "Regarding the bad-attempt assessment for this session: no attempt
> was a clear mismatch. All three designs met the core requirements
> of a continuous ring, a central hub, and five broad blades. The
> second attempt was the weakest overall match because its ring
> read noticeably heavier than the sketch intent, which called for
> a relatively thin ring. ..."

**Schema impact (already in §2.1):** `chunks.embedding_input TEXT`
stores the exact stitched string. Kept separate from `body` so the
canonical Q/A text stays untouched and re-embedding is reproducible.

**Pros:** matches `text-embedding-3-large`'s pretraining
distribution best (prose, not key:value); one vector per row; no
per-query LLM call.
**Cons:** one LLM call per chunk at index time (~$0.001 each with a
cheap model); retrieval quality depends on the rewrite prompt
quality.

**Implementation notes:**
- The rewrite prompt itself is a load-bearing piece of the system —
  treat it like a system prompt and version it.  Lives at
  `agents/database_handler/stitching_prompt.md` with a `version:` line
  in the frontmatter.
- Use a cheap model for the rewrite (the embedding is what matters,
  not the rewrite's prose quality).  Configured via two new workflow
  settings introduced in Phase 3B: `STITCHING_PROVIDER` (default
  `"OpenAI"`) and `STITCHING_MODEL` (default `"gpt-4o-mini"`).  Both
  are UI-configurable; the provider switch is gated on the matching
  API key being present in `.env`.
- **Stitching failure is treated as a chunks-INSERT failure** —
  there is NO automatic fallback to labelled-concatenation at the
  per-chunk level.  A failed stitch consumes a retry attempt; once
  `DATABASE_ENTRY_MAX_RETRIES` is exhausted, the raw Q+A is written
  to the R2 safety folder (§3.5) just like any other DB-insert
  failure.  This keeps the corpus uniform — every row in `chunks`
  has a real stitched-and-embedded paragraph in `embedding_input`,
  never a mechanical concatenation that an agent would later have
  to know how to interpret differently.

#### 6.1.1 Column mapping — what gets embedded vs what gets displayed

There are two text representations of the same Q+A on a `chunks` row,
and they serve different purposes:

| Column            | Holds                                                                 | Used for                                  |
|-------------------|-----------------------------------------------------------------------|-------------------------------------------|
| `field`           | Raw field name (e.g. `"Bad Attempt"`)                                 | Filter + display                          |
| `question`        | Raw DH question text                                                  | **Display at retrieval time**             |
| `body`            | Raw answer text (or JSON for Quantitative)                            | **Display at retrieval time**             |
| `embedding_input` | LLM-stitched prose paragraph (field + question + answer fused as one) | **What gets embedded** — never displayed  |
| `embedding`       | vector(1024) of `embedding_input`                                     | ANN similarity search                     |
| `embedding_model` | e.g. `'openai/text-embedding-3-large/1024'`                           | Model-mismatch filter (§4.9)              |

This separation is deliberate. The user-facing text (`question`,
`body`) stays exactly as the agent wrote it; the canonical Q/A
content is never paraphrased on disk. The **embedding** sees a prose
form that matches `text-embedding-3-large`'s pretraining
distribution, giving better retrieval recall on natural-language
queries.

At retrieval time, the calling agent receives `question` + `body` —
it **never sees** the stitched paragraph. The stitched paragraph
exists only to produce a good embedding.

#### 6.1.2 The Database Handler owns the stitch + embed + insert pipeline

When the DH receives a **Semantic** Q+A to save, it executes the full
chain itself:

1. **Receive** `(field, question, answer, field_type='Semantic',
   agent_from, agents_to, attempt_id?, ...)` from the answering agent.
2. **Stitch:** call the cheap rewrite LLM with the versioned rewrite
   prompt → produces `embedding_input` (the prose paragraph).
3. **Embed:** call the embeddings API
   (`text-embedding-3-large`, 1024 dim) on `embedding_input` →
   produces the `embedding` vector and records `embedding_model`.
4. **INSERT** into `chunks` with all columns populated (`field`,
   `question`, `body`, `embedding_input`, `embedding`,
   `embedding_model`, plus the rest).
5. **On failure:** retry up to `DATABASE_ENTRY_MAX_RETRIES`; if
   exhausted, write the Q+A to the R2 safety folder for the session
   (§3.5).

For **Quantitative** Q+A, steps 2 and 3 are skipped — the CHECK
constraint (§3.1) enforces that `embedding` and `embedding_model`
are NULL for Quantitative rows.

### 6.2 Rejected options (with reason)

- **Option A — Dual embeddings + RRF.** Deferred to T11 in the TODO
  list. Best retrieval recall, but doubles vector storage and adds
  query-path complexity. Revisit if Option B's recall is insufficient
  in real usage.
- **Option C — Labelled concatenation.** Strictly weaker than B in
  benchmarks for content-seeking queries; kept only as the per-chunk
  fallback when the rewrite call fails (see Implementation notes
  above).
- Raw concatenation (no labels) — weaker than C.
- Current `--- Field ---` heavy delimiters — no benefit vs. plain
  labels.
- Question-only — too narrow for paraphrase queries.
- Answer-only — loses field-label context.
- HyDE — latency tax not justified for in-session corpus.
- Instruction-prefixed — `text-embedding-3-large` was not trained
  with prefixes; wastes tokens.

---

## 7. TODO list

Items deferred to future iterations but recorded so they're not lost:

| # | Item | Why deferred | Where it lands |
|---|---|---|---|
| T1 | Parameter-vector search (RMSE against `dc_attempt_parameters`, normalised per `schema_version`'s min/max) | Ship semantic search first | `database_search` `input_key_parameters_list` argument |
| T2 | Multi-text search (combine scores across N input texts) | Single-text is enough for v1 | `input_key_text` becomes a list; fuse with RRF |
| T3 | Combined text + parameter search | Natural extension once T1 and T2 exist | Same tool; fuse text-rank with param-rank via RRF |
| T4 | "Next N" pagination — agent can request the next page of anchors after the first call | Out of scope for v1 | Add `offset` argument to `database_search` |
| T5 | Re-embed-on-the-fly toggle for mismatched embedding models — system setting (UI) | Skip-and-report is the default v1 behaviour | System workflow settings page |
| T6 | Token cap for `database_search` exposed as a UI-configurable system workflow setting | Ship with a hardcoded default first | System workflow settings page |
| T7 | Identify properly what to do with the `field` column in the database tables | Usage pattern not yet clear; affects how `field` metafilter is exposed | This file + `database_design_notes.md` |
| T8 | Reranker (cross-encoder over top-K) | Optional quality boost; defer until corpus growth makes it worthwhile | Backend retrieval pipeline |
| T9 | *(reserved — was `rag_queries` log table; now locked in §3.4)* | — | — |
| T10 | Stage B verdict columns (`dcii_verdict`, `dcoi_verdict`, `chosen_for_user`) | User explicitly **rejected** these as metafilters for now | Revisit only if requirements change |
| T11 | **Option A — Dual embeddings + RRF** for the chunks corpus. Store two vectors per record (one for the question, one for the answer/stitched-paragraph) and fuse the two ANN searches with Reciprocal Rank Fusion at query time. | Locked Option B for v1; Option A is the possible future upgrade if Option B's retrieval quality proves insufficient with real usage data. | Schema: split `chunks.embedding` into `embedding_question` + `embedding_answer`, OR introduce a child table `chunks_embeddings(chunk_id, embedding_kind, embedding)`. Backend: two ANN queries + RRF fusion. |
| T12 | **R2 safety-folder recovery pipeline** — scan `<session>/safety/` folders, re-attempt the INSERT into `chunks` with corrected inputs (e.g. successfully recompute the embedding), and on success delete the safety file. Handles cascade-failure files too (re-do the identifying-Q first, then the cascaded subsequent Qs). | Out of v1 scope; the safety folder itself ships in v1 so no user data is lost — recovery is a follow-up. | New standalone script in `extra_utilities/` plus integration with the DH. |
| T13 | **`rag_queries` retention policy** — decide on a TTL (e.g. 90 days), implement a cleanup job to drop rows older than the TTL. | The table itself ships in v1; retention is a scaling concern only relevant once the corpus is large. | Cron / scheduled task; settings on the workflow-settings page. |
| T14 | **UI wiring for `DATABASE_ENTRY_MAX_RETRIES`** — surface the new variable on the workflow-settings page with the description text from §3.5.1. | Variable definition is locked in §3.5.1; UI implementation is a separate task. | Workflow-settings page (same page as the token-cap setting in T6). |
| T15 | **Artefact-fetch tool** — separate from `database_search`. Given a specific `(session_id, attempt_id?)` anchor the caller has already triaged via text-only search, returns the requested image artefacts (`kinds=["user_input_images", "attempt_renders"]` or any subset). Reads from R2 since artefacts live there per §3.5 scope note. See §4.10 for the two-step retrieval rationale this tool is built to support. | Out of Phase 3 scope; text-only search ships first. The text response is enough for most agent decisions; image lookups are the long-tail follow-up. | New tool in `agents/database_handler/` or `agents/shared/`. Returns image bytes (or pre-signed R2 URLs) in the tool response. |
| T16 | **Anthropic-provider stitching client.** | Phase 3B locks `db_writer.py`'s stitching path to OpenAI (direct `openai` SDK).  Settings block #17 docstring AND the workflow-settings editor UI both lock `STITCHING_PROVIDER` to "OpenAI" while this is the case.  Anthropic is the next-most-likely cheap-LLM provider to support. | Add an Anthropic branch in `stitch_for_embedding()` in `agents/database_handler/db_writer.py`, gated on `ANTHROPIC_API_KEY`.  Unlock the provider input in `workflow_settings/editor.py` once available (extend `ENUM_OPTIONS["STITCHING_PROVIDER"]` to include `"Anthropic"`). |
| T17 | **Google-provider stitching client.** | Same rationale as T16; deferred for the same reason. | Same file pattern as T16; mirror the Google branch (`google.generativeai` SDK), gated on `GOOGLE_API_KEY`. |
| T18 | **Schema migration scripts (v4 → v5, and future v→v+1).** | v5 shipped via drop-and-recreate on 2026-06-02 because the Railway Postgres had no live data worth preserving.  Future schema bumps cannot make the same assumption — at least one production cutover with real session data is expected before v6. | New folder `extra_utilities/db_design/migrations/`.  One idempotent Python script per version bump: `migrate_v4_to_v5.py`, `migrate_v5_to_v6.py`, ….  Each script wraps `ALTER TABLE` + data backfill in a single transaction.  `apply_schema.py` stays the path for fresh-DB deploys; migrations are the path for non-empty DBs. |

---

## 8. Developer-facing invariants (always-true rules)

These are the rules a developer must respect when touching the
database or RAG code. Mirror these into
`extra_utilities/warnings_developer.md` and
`extra_utilities/database_design_notes.md` when the implementation
lands in the repo.

1. **`agents_to` is the only ACL** — never display a chunk to an agent
   whose name is not in `agents_to`. Applies to both the ANN search
   pre-filter and the post-search expansion.
2. **N counts anchors, not chunks** — see §4.3.
3. **Token cap trims lowest-ranked anchors first** — never partial-anchor
   truncation. See §4.5.
4. **Embedding-model mismatch is silent-skip by default** — count is
   reported in `<search_meta>`. See §4.9.
5. **No-results payload is explicit and metafilter-aware** — never
   return an empty string. See §4.7.
6. **`<search_meta>` header is always present** — even on zero results.
   See §4.6.
7. **Schema version is per-attempt** — old attempts query under their
   original `schema_version`'s parameter definitions, not the latest.
   See §1 evolution table.
8. **Vector search query template is locked** — every query against
   the chunks table that uses the HNSW index MUST include the prefix
   `WHERE NOT is_error AND NOT is_empty AND field_type = 'Semantic'`.
   The partial HNSW index (§3.2) is only used when these three
   predicates appear in the WHERE clause; forgetting any of them
   causes Postgres to fall back to a sequential scan with no warning.
   Implement once as a helper function (e.g. `vector_search_query()`)
   and call only that — never hand-roll a vector search query.
9. **DH retries failed `chunks` INSERTs up to
   `DATABASE_ENTRY_MAX_RETRIES` times** (default 3, UI-configurable).
   On exhaustion, the Q+A is written to the R2 safety folder for the
   session — never silently dropped. UNIQUE violations are the
   exception: they mean "already saved" and are NOT retried. See §3.5.
10. **End-Session feedback lives in two places** — `sessions.feedback_what_worked`
    and `sessions.feedback_what_didnt` (for analytics) AND in `chunks`
    rows under the field names `'Positive User Comments'` and
    `'Negative User Comments'` (for RAG retrieval). The chunk rows are
    written at session-end alongside the sessions-table update. See
    §3.3.
11. **Every `database_search` call is logged to `rag_queries`** — no
    silent searches. The log row is written even when the search
    returns zero anchors or errors. See §3.4.
12. **R2 safety folder is the failure escape hatch, not a happy-path
    mirror.** DH-saved Q+A text is **never** written to R2 in the
    happy path — Postgres `chunks` is the sole store. R2 receives
    Q+A only when `DATABASE_ENTRY_MAX_RETRIES` is exhausted on the
    Postgres INSERT. Non-Q+A session artefacts (mesh files, renders,
    user-provided images) continue to live on R2 as before — this
    rule applies to Q+A text only. See §3.5.
13. **`database_search` returns text only — never images.** User-
    input images and attempt-render PNGs are fetched via a separate
    artefact-fetch tool (T15) the agent invokes selectively against
    a specific anchor *after* triaging the text response. There is
    NO `return_images` flag on `database_search` and NO image content
    in any `<qa>` block. The two-step pattern (text first, then
    optional artefacts on triaged anchors) is intentional — see
    §4.10 for full rationale. Tool authors must not add an image
    side-channel to `database_search`; agent prompt authors must
    not instruct agents to expect images in the search response.
14. **Empty `to_agents` in a DH-schedule entry → row is inserted
    with `agents_to = [all primary agents]`.** The default is
    permissive on purpose so a forgotten ACL doesn't make a row
    silently invisible to the RAG. The canonical "all primary
    agents" list lives in ONE place: the `DEFAULT_AGENTS_TO_ACL`
    constant in `agents/database_handler/db_writer.py` (Phase 3B).
    When chain agents are added or removed, edit that constant —
    do not redefine the list anywhere else. See §3.6.

---

## 9. Implementation status — pause as of 2026-06-01

**Important.** The Postgres rollout is paused.  This section
captures the state at pause so the work can resume with zero
information loss — pointers to all completed code, all decisions,
all uncommitted drafts, and the next concrete step.  §1-§8 above
describe the design; this section is purely "where we are vs that
design".

### 9.1 Phase 1 — Railway Postgres provisioning  (COMPLETE)

- PostgreSQL service provisioned on Railway.
- `pgvector 0.8.2` installed and active.
- Public URL (proxy) and internal URL both reachable.
- Local `.env` populated with `DATABASE_URL` (internal) and
  `DATABASE_PUBLIC_URL` (proxy).
- Wired into the web service via Railway reference variables.

### 9.2 Phase 2 — Schema deployment + parameter seed  (COMPLETE)

- `database_PostgreSQL_schema_v4.sql` applied via
  `extra_utilities/db_design/apply_schema.py`.
- All 6 tables created (`chunks`, `dc_attempt_parameters`,
  `dc_attempts`, `dc_parameter_schemas`, `rag_queries`, `sessions`).
- All 26 indexes created (HNSW partial vector index, GIN ACL
  index, metafilter indexes, FK indexes).
- 17 propeller parameters seeded into `dc_parameter_schemas` at
  `schema_version = 1` via
  `extra_utilities/db_design/populate_dc_parameter_schemas.py`.
- Commit history for this phase: `1406041` (architecture doc + v3/v4
  SQL + apply_schema.py), `45fdf5d` (populate_dc_parameter_schemas).

### 9.3 Phase 3A — Foundation knobs and connection pool  (COMPLETE)

- `config.DATABASE_URL` and `config.DATABASE_PUBLIC_URL` added.
- `workflow_settings.DATABASE_ENTRY_MAX_RETRIES = 3` (block #16,
  UI-configurable).
- `agents/shared/postgres_pool.py` — lazy, optional
  `ConnectionPool` (min=1, max=4) with pgvector adapter registered
  per-connection.  Returns `None` / raises `PostgresDisabledError`
  cleanly when no URL is set.
- `extra_utilities/db_design/smoke_test_postgres_pool.py` —
  end-to-end verifier that runs locally without the full langchain
  stack (uses `importlib` to bypass `agents/__init__.py`).
  Verified PASS locally + Railway build clean + UI shows
  `DATABASE_ENTRY_MAX_RETRIES`.
- Commit: `b85a7fa` (prep — psycopg/pgvector deps, R2 scope
  clarification), `8d31e7e` (foundation code).

### 9.4 Phase 3B — DH ingest helper  (IN PROGRESS — sprint started 2026-06-02)

> **Resume sprint update (2026-06-02):** the stitching prompt at
> `agents/database_handler/stitching_prompt.md` was reviewed by the
> user and approved at `version: 1` (no edits).  Schema v5
> (`database_PostgreSQL_schema_v5.sql`) committed alongside
> `drop_all_tables.sql` — collapses
> `sessions.feedback_what_worked` + `sessions.feedback_what_didnt`
> into a single `sessions.feedback TEXT` column per §3.3 rewrite.
> Architecture doc §3.3 / §3.7 / §7 (T16, T17, T18) updated to
> reflect the resume sprint.  `db_writer.py` + smoke test +
> `FIXED_FEEDBACK_QUESTIONS` constant + workflow-settings UI
> changes still pending — see "NOT YET WRITTEN" below.

**Prep DONE and committed (`f99e5da`):**

- `workflow_settings/settings.py` block #17 — `STITCHING_PROVIDER`
  (default `"OpenAI"`) and `STITCHING_MODEL` (default
  `"gpt-4o-mini"`), full description with cost example + API-key
  gate.
- Architecture doc updates: §6.1 implementation-notes rewritten
  (stitching failure → retry → safety folder; no fallback
  concatenation), new §3.6 (default ACL = all primary agents),
  new §8 invariant 14.
- UI updates: `web/app.js` + `web/style.css` — popover help text
  for the To-cell + empty-state chip now reads "(all agents —
  click to restrict)".
- `extra_utilities/warnings_developer.md` W21 — empty
  `to_agents` ≠ no agents; canonical list lives only in
  `DEFAULT_AGENTS_TO_ACL`.

**Drafted but UNCOMMITTED at pause time:**

- `agents/database_handler/stitching_prompt.md` (v1).  The
  rewrite prompt for the cheap stitching LLM (Option B).
  Versioned via frontmatter (`version: 1`, `load_bearing: true`).
  Was scheduled for user review at the pause point — review
  before wiring it in when resuming.  See the inline worked
  examples in the file.

**NOT YET WRITTEN:**

- `agents/database_handler/db_writer.py`, the heart of 3B.  Must
  expose:
  - `stitch_for_embedding(field, question, answer) -> str` —
    calls the LLM selected by `STITCHING_PROVIDER`/`STITCHING_MODEL`
    using the prompt at `stitching_prompt.md`.
  - `embed_text(text) -> list[float]` — calls the embedding
    model selected by `EMBEDDING_PROVIDER`/`EMBEDDING_MODEL` at
    `EMBEDDING_VECTOR_DIMS` dims.
  - `upsert_session(...)`, `upsert_attempt(...)`,
    `upsert_attempt_parameters(...)` — populate the FK targets
    so chunks INSERTs don't fail on missing parent rows.
  - `insert_chunk(...)` — the full chain (stitch → embed →
    INSERT) with `DATABASE_ENTRY_MAX_RETRIES` retry + 1-second
    fixed-delay backoff + safety-folder fallback on exhaustion.
    Treats stitching failure as a DB-insert failure (no
    fallback concatenation).
  - `save_to_safety_folder(...)` — R2 write per §3.5.3 layout
    and §3.5.4 file content format, including the
    `Agents allowed to access this answer:` line.
  - `DEFAULT_AGENTS_TO_ACL` constant — the canonical list of
    "primary agents" used when a schedule entry's `to_agents`
    is empty (per §3.6 + invariant 14).
- `extra_utilities/db_design/smoke_test_db_writer.py` — end-to-end
  verifier that exercises stitch + embed + insert with a
  synthetic `_smoke_test_*` session_id and cleans up after itself.

**4 design decisions locked during 3B prep (re-confirm before
implementing):**

| Decision | Value |
|---|---|
| Stitching model | gpt-4o-mini default; UI-configurable provider+model gated on API key (see block #17 of settings.py) |
| Stitching failure | Treat as DB-insert failure → consume retry → exhausted → R2 safety folder.  NO labelled-concatenation fallback |
| Default ACL | All primary agents (canonical list in `DEFAULT_AGENTS_TO_ACL`) |
| Retry backoff | Fixed 1 s delay between attempts |

**Next concrete step when resuming:**

1. User reviews `stitching_prompt.md` and either approves it
   verbatim or edits it.  Bump the `version:` frontmatter if any
   substantive change is made.
2. Write `db_writer.py` per the contract above, importing the
   pool from `agents.shared.postgres_pool` and the prompt text
   from `stitching_prompt.md`.
3. Write `smoke_test_db_writer.py`.
4. Run the smoke test locally — confirm a synthetic insert hits
   the DB and a forced failure routes to R2 safety.
5. Commit + pause again before 3C.

### 9.5 Phase 3C — Hook DH save flow into Postgres  (NOT STARTED)

- In `populate_database()` (`agents/database_handler/database_handler.py`):
  - At startup: `db_writer.upsert_session(...)` then walk
    `config.ATTEMPTS_DIR` and `db_writer.upsert_attempt(...)` +
    `db_writer.upsert_attempt_parameters(...)` for each attempt
    (so chunks FKs resolve).
  - Per-Q+A: after `_write_entry()` succeeds locally, call
    `db_writer.insert_chunk(...)` (which handles the retry +
    safety fallback internally).
- R2 mirror stays active at this stage (belt and braces while we
  verify Postgres writes work end-to-end).

### 9.6 Phase 3D — Stop R2 Q+A mirror in happy path  (NOT STARTED)

- In `agents/database_handler/database_handler.py` line ~1613,
  change `_r2.upload_directory(... suffixes=(".txt", ".png",
  ".jpg", ".jpeg"))` to drop the `.txt` suffix.
- After this, R2 only sees the failure-case safety folder for
  Q+A text, plus non-Q+A artefacts (mesh, renders, user-input
  images).

### 9.7 Phase 4 — `database_search` tool  (NOT STARTED)

- Implement per §4 (signature, ACL via `agents_to`, anchor-based
  N semantics, token cap with lowest-ranked-anchor trim, XML
  response, no-results payload, embedding-model mismatch skip,
  `<search_meta>` header).
- Implement T15 (artefact-fetch tool) per §4.10 once the text
  tool is in production and the two-step pattern proves itself.

### 9.8 Commit chronology for the work above

In order:

| Commit | What |
|---|---|
| `1406041` | docs + v3/v4 SQL + apply_schema.py |
| `45fdf5d` | populate_dc_parameter_schemas.py |
| `b85a7fa` | phase 3 prep (psycopg deps, R2 scope clarification) |
| `8d31e7e` | phase 3a foundation (config + settings + pool + smoke test) |
| `3d73261` | web log: include the user message |
| `25d0348` | docs: text-only-search contract (§4.10) |
| `f99e5da` | phase 3b prep (settings #17, default-ACL, doc + UI + W21) |

### 9.9 Source-of-truth files

When resuming, the file you re-read first is this one (`database_and_RAG_architecture.md`); §1–§8 are the locked design, §9 is "where we paused".  Then in order of likely need:

- `extra_utilities/db_design/database_PostgreSQL_schema_v4.sql` — the live schema on Railway.
- `extra_utilities/db_design/apply_schema.py` — re-apply if you need to drop/recreate.
- `extra_utilities/db_design/populate_dc_parameter_schemas.py` — re-seed parameter schemas; idempotent.
- `extra_utilities/db_design/smoke_test_postgres_pool.py` — sanity-check the connection.
- `agents/shared/postgres_pool.py` — pool module.
- `agents/database_handler/stitching_prompt.md` — Option B rewrite prompt (review first when resuming).
- `workflow_settings/settings.py` blocks #16 and #17 — `DATABASE_ENTRY_MAX_RETRIES`, `STITCHING_PROVIDER`, `STITCHING_MODEL`.
- `extra_utilities/warnings_developer.md` W21 — default-ACL rule.
- `extra_utilities/TODO_known_issues.md` — F24 covers the parameters-view live preview (independent of database).
