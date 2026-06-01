# Database and RAG Architecture — Design Decisions

**Status:** design phase. Implementation begins after the user gives the go-ahead.
**Companion file:** `database_PostgreSQL_schema_v2.sql` (in this folder).
**Last updated:** 2026-05-31.

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

## 3. Pending schema decisions (still open)

These were proposed during the discussion but not yet accepted or
rejected by the user. Listed here so they're not forgotten.

1. **CHECK constraint linking `field_type` ↔ `embedding` / `embedding_model`** —
   prevents Semantic rows with NULL embedding or Quantitative rows
   with an embedding.
2. **Partial HNSW index excluding errors/empties / Quantitative rows** —
   smaller, faster index.
3. **End-Session feedback as `chunks` rows** — currently only on
   `sessions`, so invisible to the RAG. Proposal: also write them as
   chunks at session-end with `agent_from='User'`.
4. **`rag_queries` log table** — for debugging and offline retrieval
   evaluation. Recommended from day one.

*(The earlier item about `chunks.embedding_input TEXT` has been
**accepted** as a consequence of locking Option B in §6 — see §2.1
for the DDL.)*

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
  treat it like a system prompt and version it.
- Use a cheap model for the rewrite (the embedding is what matters,
  not the rewrite's prose quality).
- If the rewrite call fails, fall back to Option C labelled
  concatenation for that chunk and flag it (e.g. a new `is_fallback_embedding`
  column, or store a sentinel in `embedding_input`) so it can be
  re-stitched later.

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
| T9 | `rag_queries` log table — debugging and offline evaluation of retrieval quality | Decision pending (see §3.4) | New table in schema |
| T10 | Stage B verdict columns (`dcii_verdict`, `dcoi_verdict`, `chosen_for_user`) | User explicitly **rejected** these as metafilters for now | Revisit only if requirements change |
| T11 | **Option A — Dual embeddings + RRF** for the chunks corpus. Store two vectors per record (one for the question, one for the answer/stitched-paragraph) and fuse the two ANN searches with Reciprocal Rank Fusion at query time. | Locked Option B for v1; Option A is the possible future upgrade if Option B's retrieval quality proves insufficient with real usage data. | Schema: split `chunks.embedding` into `embedding_question` + `embedding_answer`, OR introduce a child table `chunks_embeddings(chunk_id, embedding_kind, embedding)`. Backend: two ANN queries + RRF fusion. |

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
