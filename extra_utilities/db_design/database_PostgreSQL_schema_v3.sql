-- ============================================================
-- Design Copilot — PostgreSQL schema (v3)
--
-- Source of truth for the design decisions this schema implements:
--   extra_utilities/db_design/database_and_RAG_architecture.md
--
-- Changes vs v2:
--   * sessions gains user_provided_images BOOLEAN NOT NULL DEFAULT
--     FALSE — session-level metafilter for "did the user provide
--     images?". (architecture doc §2.1)
--
--   * dc_attempts gains has_geometry and has_renders (both BOOLEAN
--     NOT NULL DEFAULT FALSE) — attempt-level metafilters for
--     "does this attempt have a generated mesh / visual renders?".
--     Each gets a partial index limited to TRUE rows.
--     (architecture doc §2.1)
--
--   * chunks gains embedding_input TEXT (nullable) — stores the
--     exact natural-language stitched paragraph that was fed to
--     text-embedding-3-large. Kept separate from `body` so the
--     canonical Q/A text stays untouched and re-embedding remains
--     reproducible. NULL for Quantitative rows (no embedding) and
--     legacy rows. Required by the locked Option B embedding
--     format. (architecture doc §2.1 and §6.1)
--
--   * New indexes to support the metafilter feature in the
--     forthcoming database_search tool (architecture doc §2.2):
--       - idx_sessions_dc_name         ON sessions(dc_name)
--       - idx_sessions_satisfaction    ON sessions(satisfaction)
--                                          WHERE satisfaction IS NOT NULL
--       - idx_sessions_session_ts      ON sessions(session_ts)
--       - idx_sessions_schema_version  ON sessions(schema_version)
--       - idx_sessions_user_id         ON sessions(user_id)
--                                          WHERE user_id IS NOT NULL
--       - idx_dc_attempts_has_geometry partial ON dc_attempts(attempt_id)
--                                          WHERE has_geometry
--       - idx_dc_attempts_has_renders  partial ON dc_attempts(attempt_id)
--                                          WHERE has_renders
--
-- Still PENDING (will become v4 once decided — architecture doc §3):
--   1. CHECK constraint linking chunks.field_type ↔ embedding /
--      embedding_model — prevent Semantic rows with NULL embedding
--      or Quantitative rows with an embedding set.
--   2. Partial HNSW index excluding error/empty/Quantitative rows
--      for a smaller, faster vector index.
--   3. End-Session feedback (sessions.feedback_what_worked /
--      sessions.feedback_what_didnt) ALSO written as chunks rows
--      so the RAG can retrieve them.
--   4. rag_queries log table — debugging and offline retrieval
--      evaluation.
--
-- 5 tables. Tables are ordered so foreign keys resolve in creation
-- order:
--   dc_parameter_schemas (standalone)
--   sessions
--   dc_attempts            (FK -> sessions)
--   chunks                 (FK -> sessions, FK -> dc_attempts)
--   dc_attempt_parameters  (FK -> dc_attempts)
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
-- Changes in v3:
--   * user_provided_images (BOOLEAN, NOT NULL, DEFAULT FALSE) —
--     session-level metafilter for the database_search tool.
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
    -- End-of-session user feedback (added in v2)
    satisfaction            SMALLINT     CHECK (satisfaction BETWEEN 0 AND 10),
                                                                      -- 10 = "yes", 5 = "partially", 0 = "no",
                                                                      -- NULL = no feedback supplied
    feedback_what_worked    TEXT,                                     -- optional free-text from the modal
    feedback_what_didnt     TEXT,                                     -- optional free-text from the modal
    -- Session-level metafilter (new in v3)
    user_provided_images    BOOLEAN      NOT NULL DEFAULT FALSE,      -- did the user supply images as input?
    saved_at                TIMESTAMPTZ  NOT NULL DEFAULT NOW()       -- row creation timestamp
);

-- Indexes supporting the database_search metafilters (new in v3):
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
-- Changes in v3:
--   * has_geometry (BOOLEAN, NOT NULL, DEFAULT FALSE) —
--     attempt-level metafilter: was a 3D mesh generated for this
--     attempt?
--   * has_renders  (BOOLEAN, NOT NULL, DEFAULT FALSE) —
--     attempt-level metafilter: were visual renders generated for
--     this attempt?
-- ------------------------------------------------------------
CREATE TABLE dc_attempts (
    attempt_id      BIGSERIAL    PRIMARY KEY,                                              -- auto-incrementing PK
    session_id      TEXT         NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                                                                                            -- -> sessions.session_id
    attempt_label   TEXT         NOT NULL UNIQUE,                                          -- '<TS>_<NNN>_<slug>' folder name
    schema_version  INTEGER      NOT NULL,                                                 -- schema used for this attempt (indexed)
                                                                                            --   (logical ref to dc_parameter_schemas, see note above)
    parameters_json JSONB        NOT NULL,                                                 -- full parameter snapshot
    -- Attempt-level metafilters (new in v3)
    has_geometry    BOOLEAN      NOT NULL DEFAULT FALSE,                                   -- was a 3D mesh generated for this attempt?
    has_renders     BOOLEAN      NOT NULL DEFAULT FALSE,                                   -- were visual renders generated for this attempt?
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),                                   -- row creation timestamp
    UNIQUE (session_id, attempt_label)
);

CREATE INDEX idx_dc_attempts_schema_version ON dc_attempts (schema_version);

-- Partial indexes on the metafilter booleans (new in v3).
-- TRUE is usually the minority, so partial indexes keep the index
-- small and the WHERE has_* = TRUE queries fast.
CREATE INDEX idx_dc_attempts_has_geometry ON dc_attempts (attempt_id) WHERE has_geometry;
CREATE INDEX idx_dc_attempts_has_renders  ON dc_attempts (attempt_id) WHERE has_renders;


-- ------------------------------------------------------------
-- chunks
-- Unified RAG corpus — many rows per session (HNSW vector index).
--
-- Changes in v3:
--   * embedding_input TEXT (nullable) — stores the exact
--     natural-language stitched paragraph that was fed to
--     text-embedding-3-large (locked Option B embedding format,
--     architecture doc §6.1). Kept separate from `body` so the
--     canonical Q/A text stays untouched and re-embedding remains
--     reproducible. NULL for:
--       - Quantitative rows (no embedding at all)
--       - legacy rows that pre-date Option B
--       - Option-B rewrite failures that fell back to labelled
--         concatenation (the fallback string is short enough that
--         storing it here is optional; if you store it, set this
--         column to the actual string used)
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
    embedding_input  TEXT,                                  -- exact stitched paragraph fed to the embedding model (Option B) — NEW in v3
    is_error         BOOLEAN       NOT NULL DEFAULT FALSE,  -- marks error rows
    is_empty         BOOLEAN       NOT NULL DEFAULT FALSE,  -- marks empty-answer rows
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),  -- row creation timestamp
    UNIQUE (session_id, agent_from, field, attempt_id, item_index, embedding_model)
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
CREATE INDEX idx_chunks_embedding  ON chunks USING hnsw (embedding vector_cosine_ops);


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
