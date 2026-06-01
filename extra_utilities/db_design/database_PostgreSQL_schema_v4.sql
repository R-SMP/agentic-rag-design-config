-- ============================================================
-- Design Copilot — PostgreSQL schema (v4)
--
-- Source of truth for the design decisions this schema implements:
--   extra_utilities/db_design/database_and_RAG_architecture.md
--
-- Changes vs v3 (locked 2026-06-01):
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
--
-- Application-layer behaviour changes locked in the same round but
-- with NO SQL impact (documented here for traceability):
--   * End-Session user feedback is written to BOTH sessions.feedback_*
--     (analytics) AND chunks rows (retrieval), under field names
--     'Positive User Comments' / 'Negative User Comments'.
--     (architecture doc §3.3)
--   * DH retries failed chunks INSERTs up to DATABASE_ENTRY_MAX_RETRIES
--     times (new workflow-settings variable, default 3). On exhaustion,
--     the Q+A is saved to the R2 safety folder for the session under
--     <session_id>/safety/session/ or <session_id>/safety/attempt_<NNN>/
--     so no user data is lost. (architecture doc §3.5)
--
-- 6 tables (was 5 in v3). Ordered so foreign keys resolve in
-- creation order:
--   dc_parameter_schemas   (standalone)
--   sessions
--   dc_attempts            (FK -> sessions)
--   chunks                 (FK -> sessions, FK -> dc_attempts)
--   dc_attempt_parameters  (FK -> dc_attempts)
--   rag_queries            (FK -> sessions, ON DELETE SET NULL)   *** NEW in v4
-- ============================================================

-- Required extensions:
--   pgvector  -> for the vector(1024) column on chunks
CREATE EXTENSION IF NOT EXISTS vector;


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
-- added in v3) and end-of-session feedback columns
-- (satisfaction + free-text, added in v2).
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
    -- End-of-session user feedback (added in v2; ALSO mirrored to chunks
    -- rows as 'Positive User Comments' / 'Negative User Comments'
    -- per architecture doc §3.3)
    satisfaction            SMALLINT     CHECK (satisfaction BETWEEN 0 AND 10),
                                                                      -- 10 = "yes", 5 = "partially", 0 = "no",
                                                                      -- NULL = no feedback supplied
    feedback_what_worked    TEXT,                                     -- optional free-text from the modal
    feedback_what_didnt     TEXT,                                     -- optional free-text from the modal
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
-- New in v4:
--   * CHECK constraint linking field_type ↔ embedding /
--     embedding_model — see architecture doc §3.1. The Database
--     Handler retries failed inserts up to DATABASE_ENTRY_MAX_RETRIES
--     times; on exhaustion the Q+A is saved to the R2 safety folder
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
    -- NEW in v4: cross-column CHECK enforcing the field_type ↔
    -- embedding contract. See architecture doc §3.1.
    CONSTRAINT chunks_embedding_consistent_with_field_type CHECK (
        (field_type = 'Quantitative' AND embedding IS NULL     AND embedding_model IS NULL)
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

-- NEW in v4: PARTIAL HNSW vector index. Only rows that retrieval
-- would actually return are indexed: Semantic rows with valid
-- embedding, excluding error/empty markers.
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
-- rag_queries                                          *** NEW in v4 ***
-- Append-only log of every call to the database_search tool.
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
    ts                  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),                                 -- when the search was issued
    session_id          TEXT         REFERENCES sessions(session_id) ON DELETE SET NULL,    -- the calling session (NULLed on session delete)
    caller_agent        TEXT         NOT NULL,                                                -- which agent invoked database_search
    query_text          TEXT,                                                                 -- the input_key_text argument
    query_params        JSONB,                                                                -- the input_key_parameters_list (TODO T1)
    n_requested         INTEGER      NOT NULL,                                                -- N argument (counts anchors per §4.3)
    attempt_specific    BOOLEAN      NOT NULL,                                                -- attempt_specific_flag argument
    metafilters         JSONB,                                                                -- the METAFILTERS dict
    embedding_model     TEXT,                                                                 -- model used to embed the query
    n_returned          INTEGER      NOT NULL,                                                -- distinct anchors actually returned
    returned_anchor_ids JSONB,                                                                -- [{session_id, attempt_id?, score}, ...]
    skipped_count       INTEGER      NOT NULL DEFAULT 0,                                      -- rows skipped due to embedding-model mismatch
    truncated_anchors   INTEGER      NOT NULL DEFAULT 0,                                      -- anchors dropped by the token cap
    latency_ms          INTEGER,                                                              -- end-to-end search latency
    error_message       TEXT                                                                  -- non-NULL iff the search errored
);

CREATE INDEX idx_rag_queries_ts            ON rag_queries (ts);
CREATE INDEX idx_rag_queries_session_id    ON rag_queries (session_id);
CREATE INDEX idx_rag_queries_caller_agent  ON rag_queries (caller_agent);
