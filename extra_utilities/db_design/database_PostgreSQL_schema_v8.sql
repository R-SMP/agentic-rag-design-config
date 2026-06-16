-- ============================================================
-- Design Copilot — PostgreSQL schema (v8)
--
-- Source of truth for the design decisions this schema implements:
--   extra_utilities/db_design/database_and_RAG_architecture.md
--
-- Changes vs v7 (multimodal extension, 2026-06-15):
--   * NEW table ``chunks_mm`` — a parallel copy of ``chunks`` that
--     holds the voyage-multimodal-3.5 (2048-dim) re-embedding of
--     every TEXT entry PLUS new rows for the session's IMAGES
--     (user-input images + attempt renders).  See architecture doc
--     §6.3.  The original ``chunks`` table is unchanged.
--       - ``embedding`` is ``vector(2048)`` (was ``vector(1024)``).
--       - The HNSW vector index is built on a ``halfvec(2048)`` cast
--         because pgvector's HNSW on the float ``vector`` type is
--         capped at 2000 dims; ``halfvec`` raises that to 4000.
--         Requires pgvector >= 0.7.0.
--       - Image rows reuse the existing column shape (no new
--         columns): user images use agent_from='User' /
--         field='User Image Input'; renders use
--         agent_from='tool_caller' / field='Attempt Visual Render';
--         both field_type='Semantic', body = the image's R2 name,
--         embedding_input = the fused note/description text.
--       - ``session_id`` / ``attempt_id`` FK to the EXISTING
--         ``sessions`` / ``dc_attempts`` tables (metadata reused,
--         not duplicated).
--   * Reapply procedure: idempotent CREATE TABLE / CREATE INDEX in
--     ``migrations/migrate_v7_to_v8.py`` for an existing v7 DB.  For
--     fresh deploys, applying this file directly via
--     ``apply_schema.py`` includes ``chunks_mm``.
--
-- Changes vs v6 (locked 2026-06-03, Phase 5B):
--   * rag_queries — generalised from "database_search log" to
--     "all RAG-related tool log".  Three column-level changes:
--       - NEW column ``tool_name TEXT NOT NULL DEFAULT 'database_search'``
--         identifying which tool produced the row.  Existing rows
--         backfill to ``'database_search'`` via the DEFAULT; the new
--         retrieve tools (Phase 5B / 5C — see architecture doc §4 +
--         the Phase 5 notes) log with
--         ``tool_name='retrieve_user_inputs'`` or
--         ``'retrieve_attempt'``.
--       - NEW column ``images_flag BOOLEAN`` (nullable).  Records
--         the images_flag argument when the row was produced by a
--         retrieve_* tool; NULL for database_search rows.
--       - ``attempt_specific`` RELAXED to nullable.  database_search
--         still always supplies a value; retrieve_* tools have no
--         attempt_specific concept and pass NULL.
--     New index ``idx_rag_queries_tool_name`` so per-tool analytics
--     queries do not full-scan the table.
--
--   * Reapply procedure: idempotent ALTER TABLE statements run by
--     ``extra_utilities/db_design/migrations/migrate_v6_to_v7.py``.
--     For fresh deploys, applying this file directly via
--     ``apply_schema.py`` is also fine.
--
-- Changes vs v5 (locked 2026-06-02, Phase 3E):
--   * NEW SEQUENCE ``session_counter`` — drives the IDNNN counter
--     in session_id slugs.  Replaces the filesystem scan in
--     ``agents/loader.py::_next_session_id``, which won't work
--     once the Railway volume is retired (every session would
--     restart at ID001 → collision storm).  The SEQUENCE is
--     globally unique across deploys / container rebuilds /
--     restarts.  When Postgres is unreachable, the loader falls
--     back to a timestamp-with-microseconds slug
--     (``ID_YYYYMMDD_HHMMSS_uuuuuu``) so local + R2 saves still
--     proceed.  See architecture doc §9.10 +
--     warnings_developer.md W31.
--
--   * Reapply procedure: ``CREATE SEQUENCE IF NOT EXISTS`` is
--     idempotent.  When upgrading an existing v5 deployment with
--     live data, run
--     ``extra_utilities/db_design/migrations/migrate_v5_to_v6.py``
--     instead of re-applying this schema file from scratch — the
--     migration adds the SEQUENCE AND seeds its initial value to
--     MAX(existing IDNNN) so the next nextval returns max+1.
--     Fresh deploys (empty DB) can apply this file directly via
--     apply_schema.py.
--
-- Changes vs v4 (locked 2026-06-02):
--   * sessions: the two free-text feedback columns
--     ``feedback_what_worked`` and ``feedback_what_didnt`` collapse
--     into a SINGLE ``feedback TEXT`` column.  Rationale: the End
--     Session modal's question list may grow over time (current = 2
--     questions; future = N questions).  The per-question content
--     remains addressable via ``chunks`` rows (one row per feedback
--     question, ``agent_from='User'``, ``field='Positive User
--     Comments'`` or ``'Negative User Comments'``).  ``sessions
--     .feedback`` accumulates the concatenated raw text for quick
--     session-level filtering.  ``satisfaction`` stays as the
--     numeric quick-score.  (architecture doc §3.3 rewrite)
--
--   * chunks_embedding_consistent_with_field_type CHECK constraint
--     RELAXED: a Semantic row may now have NULL embedding +
--     embedding_model when ``is_empty = TRUE``.  This permits the
--     End-Session feedback safety-net rows — an unanswered fixed
--     feedback question is recorded as ``is_empty=TRUE`` so a
--     downstream consumer sees an explicit "asked but not answered"
--     marker rather than missing the row entirely.  The partial
--     HNSW index already excludes ``is_empty`` rows, so retrieval
--     is unaffected.  See architecture doc §3.1 (with v5 addendum).
--
--   * Reapply procedure: ``CREATE TABLE`` is not idempotent, so a
--     re-apply against a non-empty database requires dropping the
--     existing tables first.  Use the companion script
--     ``extra_utilities/db_design/drop_all_tables.sql`` (six
--     ``DROP TABLE IF EXISTS ... CASCADE`` statements in
--     dependency-safe order) before re-applying v5.
--
-- Changes vs v3 (locked 2026-06-01, preserved in v4):
--   * NEW CHECK constraint on chunks linking field_type ↔
--     embedding / embedding_model. Prevents:
--       - Semantic rows with NULL embedding (unsearchable orphans),
--       - Quantitative rows with an embedding set (wasted vector slot),
--       - Semantic rows with embedding but no embedding_model
--         (cannot apply the §4.9 model-mismatch skip rule).
--     (architecture doc §3.1)
--
--   * idx_chunks_embedding is now a PARTIAL HNSW index, restricted
--     to rows that retrieval would actually return. The vector index
--     is smaller (~25% less RAM in typical use), faster to build,
--     and faster at query time. (architecture doc §3.2)
--
--     IMPORTANT: every vector search query MUST include the three
--     predicates the partial index requires:
--       WHERE NOT is_error AND NOT is_empty AND field_type = 'Semantic'
--     Otherwise Postgres falls back to a sequential scan — correct
--     but ~1000× slower with no warning. The backend MUST wrap the
--     query in a single helper function. See §8 invariant 8 in the
--     architecture doc.
--
--   * NEW rag_queries table — logs every call to the database_search
--     tool. Used for debugging, offline retrieval-quality evaluation,
--     usage analytics, and cost tracking. (architecture doc §3.4)
--     (Generalised in v7 to also log retrieve_* calls — see above.)
--
-- Application-layer behaviour changes locked in the same round but
-- with NO SQL impact (documented here for traceability):
--   * End-Session user feedback is written to BOTH sessions.feedback
--     (analytics; collapsed to one column in v5) AND chunks rows
--     (retrieval), under field names 'Positive User Comments' /
--     'Negative User Comments'.  (architecture doc §3.3)
--   * DH retries failed chunks INSERTs up to DATABASE_ENTRY_MAX_RETRIES
--     times (workflow-settings variable, default 3). On exhaustion,
--     the Q+A is uploaded to the R2 safety folder for the session
--     under <session_id>/safety/session/ or <session_id>/safety/
--     attempt_<NNN>/ so no user data is lost.  Safety files are
--     written DIRECTLY to R2 (no local copy) from v9 onwards — the
--     Railway local volume is being retired.  (architecture doc §3.5)
--
-- 6 tables (unchanged from v4). Ordered so foreign keys resolve in
-- creation order:
--   dc_parameter_schemas   (standalone)
--   sessions
--   dc_attempts            (FK -> sessions)
--   chunks                 (FK -> sessions, FK -> dc_attempts)
--   dc_attempt_parameters  (FK -> dc_attempts)
--   rag_queries            (FK -> sessions, ON DELETE SET NULL)
-- ============================================================

-- Required extensions:
--   pgvector  -> for the vector(1024) column on chunks
CREATE EXTENSION IF NOT EXISTS vector;


-- ------------------------------------------------------------
-- session_counter                                       (NEW in v6)
-- Global monotonic counter driving the IDNNN portion of every
-- session_id slug (architecture doc §9.10, Phase 3E).
--
-- ``agents/loader.py::_resolve_session_name`` calls
--   SELECT nextval('session_counter')
-- at first DH-save time (Q-SID-3 = β: lazy allocation) and
-- formats the slug as ``ID{nnn:03d}_{YYYYMMDD_HHMMSS}``.
--
-- When Postgres is unreachable, the loader falls back to a
-- timestamp-with-microseconds slug (no counter advance) so the
-- local save + R2 mirror can still proceed (Q-SID-2 = ii).
--
-- The SEQUENCE persists across deploys / container rebuilds —
-- its ``last_value`` is part of the DB dump.  pg_dump/pg_restore
-- preserves it.
--
-- Width note: ``:03d`` padding lets the counter run to 999 with
-- a stable 3-digit slug width; beyond that the slug naturally
-- extends to 4+ digits.  Lexicographic sort breaks at the
-- ID999→ID1000 boundary; numeric sort is always correct.  Bump
-- the padding (e.g. to ``:06d``) only if the breakage matters.
-- ------------------------------------------------------------
CREATE SEQUENCE IF NOT EXISTS session_counter
    INCREMENT 1
    START 1
    MINVALUE 1
    NO MAXVALUE
    NO CYCLE;


-- ------------------------------------------------------------
-- dc_parameter_schemas
-- Versioned parameter inventory.  Composite PK.
-- Unchanged from v2.
-- ------------------------------------------------------------
CREATE TABLE dc_parameter_schemas (
    schema_version  INTEGER           NOT NULL,             -- composite PK part 1: version number
    param_name      TEXT              NOT NULL,             -- composite PK part 2: parameter name
    min_value       DOUBLE PRECISION  NOT NULL,             -- lower bound for parameter
    max_value       DOUBLE PRECISION  NOT NULL,             -- upper bound for parameter
    unit            TEXT,                                   -- physical unit (e.g. 'm/s', 'deg')
    description     TEXT,                                   -- human-readable description
    introduced_at   TIMESTAMPTZ       NOT NULL DEFAULT NOW(),  -- when this param was added
    retired_at      TIMESTAMPTZ,                            -- NULL = still active in this schema version
    PRIMARY KEY (schema_version, param_name),
    -- Catch inverted ranges at insert time.  ``<=`` (not ``<``)
    -- permits degenerate ranges where min=max — the canonical way
    -- to express a user-locked parameter ("this value must be
    -- exactly X").
    CONSTRAINT dc_parameter_schemas_min_le_max
        CHECK (min_value <= max_value)
);


-- ------------------------------------------------------------
-- sessions
-- Parent table — one row per saved session.
--
-- Includes session-level metafilter column (user_provided_images,
-- added in v3) and the end-of-session feedback columns (satisfaction
-- + ``feedback`` collapsed-text in v5).
-- ------------------------------------------------------------
CREATE TABLE sessions (
    session_id              TEXT         PRIMARY KEY,                 -- surrogate session identifier
    session_ts              TIMESTAMPTZ  NOT NULL,                    -- when the session started
    user_id                 TEXT,                                     -- optional user identifier (no FK; F22 deferred)
    dc_name                 TEXT         NOT NULL,                    -- Design Copilot name (e.g. 'propeller')
    dc_inspector_enabled    BOOLEAN      NOT NULL,                    -- whether DC inspector was active
    schema_version          INTEGER      NOT NULL,                    -- parameter schema version active for this session
                                                                      --   (logical ref to dc_parameter_schemas.schema_version;
                                                                      --    not an enforceable FK because that PK is composite)
    notes                   TEXT,                                     -- free-text session notes
    -- End-of-session user feedback (collapsed to a single TEXT column
    -- in v5; the per-question content is mirrored to chunks rows as
    -- 'Positive User Comments' / 'Negative User Comments' per
    -- architecture doc §3.3.  satisfaction stays as the numeric quick-
    -- score; the free-text from the End Session modal accumulates into
    -- ``feedback``.  Future expansion of the modal's question list
    -- requires NO further schema changes — new questions become
    -- additional chunks rows; their text appends into ``feedback``.)
    satisfaction            SMALLINT     CHECK (satisfaction BETWEEN 0 AND 10),
                                                                      -- 10 = "yes", 5 = "partially", 0 = "no",
                                                                      -- NULL = no feedback supplied
    feedback                TEXT,                                     -- concatenated free-text from the modal
    -- Session-level metafilter (added in v3)
    user_provided_images    BOOLEAN      NOT NULL DEFAULT FALSE,      -- did the user supply images as input?
    saved_at                TIMESTAMPTZ  NOT NULL DEFAULT NOW()       -- row creation timestamp
);

-- Indexes supporting the database_search metafilters:
CREATE INDEX idx_sessions_dc_name        ON sessions (dc_name);
CREATE INDEX idx_sessions_session_ts     ON sessions (session_ts);
CREATE INDEX idx_sessions_schema_version ON sessions (schema_version);
CREATE INDEX idx_sessions_satisfaction   ON sessions (satisfaction)
    WHERE satisfaction IS NOT NULL;
CREATE INDEX idx_sessions_user_id        ON sessions (user_id)
    WHERE user_id IS NOT NULL;


-- ------------------------------------------------------------
-- dc_attempts
-- One row per design iteration the user worked through.
--
-- Includes attempt-level metafilter columns (has_geometry,
-- has_renders, added in v3).
-- ------------------------------------------------------------
CREATE TABLE dc_attempts (
    attempt_id      BIGSERIAL    PRIMARY KEY,                                              -- auto-incrementing PK
    session_id      TEXT         NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                                                                                            -- -> sessions.session_id
    attempt_label   TEXT         NOT NULL UNIQUE,                                          -- '<TS>_<NNN>_<slug>' folder name
    schema_version  INTEGER      NOT NULL,                                                 -- schema used for this attempt (indexed)
                                                                                            --   (logical ref to dc_parameter_schemas, see note above)
    parameters_json JSONB        NOT NULL,                                                 -- full parameter snapshot
    -- Attempt-level metafilters (added in v3)
    has_geometry    BOOLEAN      NOT NULL DEFAULT FALSE,                                   -- was a 3D mesh generated for this attempt?
    has_renders     BOOLEAN      NOT NULL DEFAULT FALSE,                                   -- were visual renders generated for this attempt?
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),                                   -- row creation timestamp
    UNIQUE (session_id, attempt_label)
);

CREATE INDEX idx_dc_attempts_schema_version ON dc_attempts (schema_version);

-- Partial indexes on the metafilter booleans.
-- TRUE is usually the minority, so partial indexes keep the index
-- small and the WHERE has_* = TRUE queries fast.
CREATE INDEX idx_dc_attempts_has_geometry ON dc_attempts (attempt_id) WHERE has_geometry;
CREATE INDEX idx_dc_attempts_has_renders  ON dc_attempts (attempt_id) WHERE has_renders;


-- ------------------------------------------------------------
-- chunks
-- Unified RAG corpus — many rows per session (HNSW vector index).
--
-- New in v4 (preserved unchanged in v5):
--   * CHECK constraint linking field_type ↔ embedding /
--     embedding_model — see architecture doc §3.1. The Database
--     Handler retries failed inserts up to DATABASE_ENTRY_MAX_RETRIES
--     times; on exhaustion the Q+A is uploaded to the R2 safety folder
--     (architecture doc §3.5).
--   * idx_chunks_embedding is now a partial HNSW index — see below.
--
-- embedding_input (added in v3) stores the natural-language stitched
-- paragraph fed to text-embedding-3-large (locked Option B embedding
-- format, architecture doc §6.1). NULL for Quantitative rows.
-- ------------------------------------------------------------
CREATE TABLE chunks (
    id               BIGSERIAL     PRIMARY KEY,                                              -- auto-incrementing PK
    session_id       TEXT          NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                                                                                              -- -> sessions.session_id
    attempt_id       BIGINT        REFERENCES dc_attempts(attempt_id) ON DELETE CASCADE,     -- -> dc_attempts.attempt_id (NULL = session-level)
    agent_from       TEXT          NOT NULL,                -- originating agent identifier (indexed)
    agents_to        TEXT[]        NOT NULL,                -- access-control list (GIN indexed) — the only ACL for the RAG
    field            TEXT          NOT NULL,                -- DH schedule field (e.g. 'Plan') (indexed)
    field_type       TEXT          NOT NULL                 -- 'Semantic' | 'Quantitative' (CHECK-enforced)
                                   CHECK (field_type IN ('Semantic', 'Quantitative')),
    question         TEXT,                                  -- DH's literal question text
    body             TEXT          NOT NULL,                -- Answer (Semantic) or JSON payload (Quantitative)
    item_index       SMALLINT,                              -- 1-based multi-answer-split index; NULL = canonical single row
    embedding        vector(1024),                          -- cosine-similarity vector (HNSW index); NULL for Quantitative
    embedding_model  TEXT,                                  -- e.g. 'openai/text-embedding-3-large/1024'
    embedding_input  TEXT,                                  -- exact stitched paragraph fed to the embedding model (Option B; added in v3)
    is_error         BOOLEAN       NOT NULL DEFAULT FALSE,  -- marks error rows (filtered out of vector search)
    is_empty         BOOLEAN       NOT NULL DEFAULT FALSE,  -- marks empty-answer rows (filtered out of vector search)
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),  -- row creation timestamp
    UNIQUE (session_id, agent_from, field, attempt_id, item_index, embedding_model),
    -- v5 cross-column CHECK enforcing the field_type ↔ embedding
    -- contract.  Relaxed from v4 to allow Semantic safety-net rows
    -- (is_empty=TRUE) to carry NULL embedding + NULL embedding_model.
    -- See architecture doc §3.1 (v5 addendum).
    CONSTRAINT chunks_embedding_consistent_with_field_type CHECK (
        (field_type = 'Quantitative' AND embedding IS NULL     AND embedding_model IS NULL)
        OR
        (field_type = 'Semantic'     AND is_empty)
        OR
        (field_type = 'Semantic'     AND embedding IS NOT NULL AND embedding_model IS NOT NULL)
    )
    -- NOTE on NULL semantics: PostgreSQL's default treats NULLs as
    -- DISTINCT in UNIQUE constraints, so two rows where attempt_id
    -- IS NULL or item_index IS NULL will NOT collide just because
    -- their NULLs match — which is what we want for the v9 DH save
    -- flow.  If you need the opposite (single canonical row per
    -- session+agent+field+model), upgrade to Postgres 15+ and add
    -- ``NULLS NOT DISTINCT`` to the UNIQUE clause above.
);

CREATE INDEX idx_chunks_agent_from ON chunks (agent_from);
CREATE INDEX idx_chunks_field      ON chunks (field);
CREATE INDEX idx_chunks_attempt_id ON chunks (attempt_id);   -- explicit FK index
CREATE INDEX idx_chunks_agents_to  ON chunks USING GIN  (agents_to);

-- v4 PARTIAL HNSW vector index (preserved in v5). Only rows that
-- retrieval would actually return are indexed: Semantic rows with
-- valid embedding, excluding error/empty markers.
--
-- IMPORTANT: every vector search query MUST include the three
-- predicates below in its WHERE clause for Postgres to use this
-- index. See architecture doc §3.2 + §8 invariant 8.
CREATE INDEX idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops)
    WHERE NOT is_error AND NOT is_empty AND field_type = 'Semantic';


-- ------------------------------------------------------------
-- dc_attempt_parameters
-- Long-format scalar mirror for masked-RMSE analytics. Composite PK.
-- Unchanged from v2.
-- ------------------------------------------------------------
CREATE TABLE dc_attempt_parameters (
    attempt_id  BIGINT            NOT NULL                  -- composite PK part 1
                REFERENCES dc_attempts(attempt_id) ON DELETE CASCADE,  -- -> dc_attempts.attempt_id (CASCADE DELETE)
    param_name  TEXT              NOT NULL,                 -- composite PK part 2: parameter name
    raw_value   DOUBLE PRECISION  NOT NULL,                 -- scalar parameter value for masked-RMSE queries
    PRIMARY KEY (attempt_id, param_name)
);

-- param_name is also indexed together with raw_value for masked-RMSE queries
CREATE INDEX idx_dc_attempt_parameters_param_value
    ON dc_attempt_parameters (param_name, raw_value);


-- ------------------------------------------------------------
-- rag_queries                                          (added in v4; generalised in v7)
-- Append-only log of every call to a RAG-related tool.  Originally
-- shipped in v4 as a database_search-only log; v7 widens it to also
-- record retrieve_user_inputs and retrieve_attempt calls so all
-- RAG-related tool usage lives in a single observability table.
--
-- Used for debugging, offline retrieval-quality evaluation, usage
-- analytics, and cost tracking. (architecture doc §3.4)
--
-- The session_id FK uses ON DELETE SET NULL so deleting a session
-- does NOT destroy its query history — useful for cross-session
-- analytics. If the session row is gone, the FK simply becomes NULL.
--
-- Retention policy: TODO T13 — decide on a TTL (e.g. 90 days) and
-- implement a cleanup job. For now the table grows unbounded.
-- ------------------------------------------------------------
CREATE TABLE rag_queries (
    id                  BIGSERIAL    PRIMARY KEY,                                            -- auto-incrementing PK
    ts                  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),                                 -- when the call was issued
    session_id          TEXT         REFERENCES sessions(session_id) ON DELETE SET NULL,    -- the calling session (NULLed on session delete)
    caller_agent        TEXT         NOT NULL,                                                -- which agent invoked the tool
    tool_name           TEXT         NOT NULL DEFAULT 'database_search',                     -- v7: which RAG tool ('database_search', 'retrieve_user_inputs', 'retrieve_attempt')
    query_text          TEXT,                                                                 -- the input_key_text argument (database_search only)
    query_params        JSONB,                                                                -- the input_key_parameters_list (database_search; TODO T1) OR the retrieve_* ID list
    n_requested         INTEGER      NOT NULL,                                                -- N argument (database_search anchors; retrieve_* ID count)
    attempt_specific    BOOLEAN,                                                              -- v7: NULLABLE.  database_search supplies a value; retrieve_* tools pass NULL
    images_flag         BOOLEAN,                                                              -- v7: NEW.  Retrieve_* images_flag argument; NULL for database_search
    metafilters         JSONB,                                                                -- database_search METAFILTERS dict (NULL for retrieve_*)
    embedding_model     TEXT,                                                                 -- model used to embed the query (database_search only; NULL for retrieve_*)
    n_returned          INTEGER      NOT NULL,                                                -- distinct anchors / sessions / attempts actually returned
    returned_anchor_ids JSONB,                                                                -- [{session_id, attempt_id?, score}, ...] or [{session_id}, ...] or [{attempt_id}, ...]
    skipped_count       INTEGER      NOT NULL DEFAULT 0,                                      -- database_search: rows skipped due to embedding-model mismatch.  Retrieve_*: IDs that errored / not_found
    truncated_anchors   INTEGER      NOT NULL DEFAULT 0,                                      -- anchors / sessions / attempts dropped by the token cap
    latency_ms          INTEGER,                                                              -- end-to-end call latency
    error_message       TEXT                                                                  -- non-NULL iff the call errored
);

CREATE INDEX idx_rag_queries_ts            ON rag_queries (ts);
CREATE INDEX idx_rag_queries_session_id    ON rag_queries (session_id);
CREATE INDEX idx_rag_queries_caller_agent  ON rag_queries (caller_agent);
CREATE INDEX idx_rag_queries_tool_name     ON rag_queries (tool_name);


-- ------------------------------------------------------------
-- chunks_mm                                            (added in v8)
-- Parallel MULTIMODAL copy of `chunks` (architecture doc §6.3).
-- Structurally identical to `chunks` EXCEPT:
--   * embedding is vector(2048) — voyage-multimodal-3.5 output.
--   * the partial HNSW index is built on a halfvec(2048) cast,
--     because pgvector's HNSW on the float `vector` type is capped
--     at 2000 dims; halfvec raises the limit to 4000.  Requires
--     pgvector >= 0.7.0.
--
-- Holds (a) the multimodal re-embedding of every TEXT entry from
-- `chunks` (Semantic rows re-embedded with voyage-multimodal-3.5;
-- Quantitative + is_empty rows copied verbatim with NULL embedding)
-- and (b) new IMAGE rows.  Image rows reuse the existing column
-- shape — NO image-specific columns:
--   * user images  -> agent_from = 'User',        field = 'User Image Input'
--   * renders      -> agent_from = 'tool_caller',  field = 'Attempt Visual Render'
--   * both          -> field_type = 'Semantic', agents_to = all primary
--                      agents (DEFAULT_AGENTS_TO_ACL), body = the image's
--                      R2 name, embedding_input = the fused note /
--                      description text, embedding = the fused image+text
--                      vector.
--
-- session_id / attempt_id FK to the EXISTING sessions / dc_attempts
-- tables — metadata is reused, not duplicated.
--
-- The CHECK + UNIQUE constraints are IDENTICAL to `chunks`: image
-- rows are Semantic with a real embedding, so they satisfy the
-- Semantic branch of the CHECK.  The backfill fills this table with
-- a per-session delete-then-insert (re-runnable), so the UNIQUE
-- constraint is a safety net rather than the idempotency mechanism.
-- ------------------------------------------------------------
CREATE TABLE chunks_mm (
    id               BIGSERIAL     PRIMARY KEY,                                              -- auto-incrementing PK
    session_id       TEXT          NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                                                                                              -- -> sessions.session_id (REUSED, not duplicated)
    attempt_id       BIGINT        REFERENCES dc_attempts(attempt_id) ON DELETE CASCADE,     -- -> dc_attempts.attempt_id (NULL = session-level / user image)
    agent_from       TEXT          NOT NULL,                -- 'User' (user image) | 'tool_caller' (render) | originating agent (text)
    agents_to        TEXT[]        NOT NULL,                -- access-control list (GIN indexed)
    field            TEXT          NOT NULL,                -- 'User Image Input' | 'Attempt Visual Render' | DH schedule field (text)
    field_type       TEXT          NOT NULL                 -- 'Semantic' | 'Quantitative' (image rows are Semantic)
                                   CHECK (field_type IN ('Semantic', 'Quantitative')),
    question         TEXT,                                  -- DH's literal question text (NULL for image rows)
    body             TEXT          NOT NULL,                -- text answer / JSON (text rows) OR image R2 name (image rows)
    item_index       SMALLINT,                              -- multi-answer split (text) OR per-image / per-view index (image)
    embedding        vector(2048),                          -- voyage-multimodal-3.5 vector (HNSW via halfvec cast); NULL for Quantitative
    embedding_model  TEXT,                                  -- e.g. 'voyage/voyage-multimodal-3.5/2048'
    embedding_input  TEXT,                                  -- text fed to the model (stitched paragraph, or fused note/description for image rows)
    is_error         BOOLEAN       NOT NULL DEFAULT FALSE,  -- marks error rows (filtered out of vector search)
    is_empty         BOOLEAN       NOT NULL DEFAULT FALSE,  -- marks empty-answer rows (filtered out of vector search)
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),  -- row creation timestamp
    UNIQUE (session_id, agent_from, field, attempt_id, item_index, embedding_model),
    CONSTRAINT chunks_mm_embedding_consistent_with_field_type CHECK (
        (field_type = 'Quantitative' AND embedding IS NULL     AND embedding_model IS NULL)
        OR
        (field_type = 'Semantic'     AND is_empty)
        OR
        (field_type = 'Semantic'     AND embedding IS NOT NULL AND embedding_model IS NOT NULL)
    )
);

CREATE INDEX idx_chunks_mm_agent_from ON chunks_mm (agent_from);
CREATE INDEX idx_chunks_mm_field      ON chunks_mm (field);
CREATE INDEX idx_chunks_mm_attempt_id ON chunks_mm (attempt_id);   -- explicit FK index
CREATE INDEX idx_chunks_mm_agents_to  ON chunks_mm USING GIN  (agents_to);

-- Partial HNSW vector index on a halfvec(2048) cast.  Mirrors the
-- spirit of idx_chunks_embedding: only rows retrieval would return
-- are indexed (Semantic, valid embedding — image rows included).
-- Requires pgvector >= 0.7.0 for the halfvec type.
CREATE INDEX idx_chunks_mm_embedding ON chunks_mm
    USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops)
    WHERE embedding IS NOT NULL AND NOT is_error AND NOT is_empty;
