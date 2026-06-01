-- ============================================================
-- Design Copilot — PostgreSQL schema (v2)
--
-- Changes vs v1:
--   * chunks.item_index added (SMALLINT NULL).  Captures the
--     multi-answer-split position (1-based) the DH emits when a
--     single field receives N back-to-back QUESTION:/ANSWER:
--     pairs.  NULL = canonical single row (no split).
--   * chunks UNIQUE rewritten to include attempt_id + item_index
--     so the v9 DH filename matrix (<field>.txt /
--     <field>_M.txt / <field>__NNN.txt / <field>__NNN_M.txt) can
--     ingest without collisions.
--   * sessions gains three feedback columns populated when the
--     user submits the End Session modal: satisfaction (SMALLINT
--     0–10 — 10 = "yes", 5 = "partially", 0 = "no", NULL = no
--     feedback supplied), feedback_what_worked, feedback_what_didnt.
--   * Every foreign key now declares ON DELETE CASCADE so deleting
--     a session row removes its attempts, chunks, and
--     attempt_parameters in one operation.  dc_attempt_parameters
--     already had CASCADE in v1 — now consistent everywhere.
--   * sessions.final_outcome and dc_attempts.outcome (both TEXT
--     in v1) are DROPPED.  Rationale: the session-level success
--     signal is now captured directly by the new satisfaction
--     column (user-supplied 0–10).  The attempt-level outcome
--     was semantically ambiguous (it collapsed three independent
--     verdicts — DCII parameter approval, DCOI render approval,
--     Planner Role-3 final pick — into one TEXT column).  Add
--     back as specific per-verdict columns (e.g. dcii_verdict,
--     dcoi_verdict, chosen_for_user) when Stage B ingestion is
--     wired and the exact query patterns are known.
--   * New explicit index on chunks.attempt_id (Postgres does NOT
--     auto-index FK columns; the leading column of the chunks
--     UNIQUE already covers session_id).
--   * Two new CHECK constraints catch a class of data-entry
--     errors at insert time:
--       - chunks.field_type IN ('Semantic', 'Quantitative')
--         (the schema documented this vocabulary in v1 but the
--         DB would silently accept typos like 'semantic')
--       - dc_parameter_schemas.min_value <= max_value
--         (<= permits degenerate / locked values where min=max,
--         which is the common pattern for user-locked parameters)
--
-- 5 tables.  Tables are ordered so foreign keys resolve in
-- creation order:
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
-- Unchanged from v1.
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
    -- v2: catch inverted ranges at insert time.  ``<=`` (not ``<``)
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
-- New in v2: three end-of-session-feedback columns
-- (satisfaction + two free-text fields), populated when the user
-- submits the End Session modal with `save=true` and a feedback
-- payload.  All three are nullable so a session that was archived
-- without feedback (or saved by a legacy client) inserts cleanly.
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
    -- End-of-session user feedback (new in v2)
    satisfaction            SMALLINT     CHECK (satisfaction BETWEEN 0 AND 10),
                                                                      -- 10 = "yes", 5 = "partially", 0 = "no",
                                                                      -- NULL = no feedback supplied
    feedback_what_worked    TEXT,                                     -- optional free-text from the modal
    feedback_what_didnt     TEXT,                                     -- optional free-text from the modal
    saved_at                TIMESTAMPTZ  NOT NULL DEFAULT NOW()       -- row creation timestamp
);


-- ------------------------------------------------------------
-- dc_attempts
-- One row per design iteration the user worked through.
--
-- Change in v2: session_id FK now CASCADES on delete (was no
-- action in v1).
-- ------------------------------------------------------------
CREATE TABLE dc_attempts (
    attempt_id      BIGSERIAL    PRIMARY KEY,                                              -- auto-incrementing PK
    session_id      TEXT         NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                                                                                            -- -> sessions.session_id
    attempt_label   TEXT         NOT NULL UNIQUE,                                          -- '<TS>_<NNN>_<slug>' folder name
    schema_version  INTEGER      NOT NULL,                                                 -- schema used for this attempt (indexed)
                                                                                            --   (logical ref to dc_parameter_schemas, see note above)
    parameters_json JSONB        NOT NULL,                                                 -- full parameter snapshot
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),                                   -- row creation timestamp
    UNIQUE (session_id, attempt_label)
);

CREATE INDEX idx_dc_attempts_schema_version ON dc_attempts (schema_version);


-- ------------------------------------------------------------
-- chunks
-- Unified RAG corpus — many rows per session (HNSW vector index).
--
-- Changes in v2:
--   * New column item_index SMALLINT NULL — captures the
--     multi-answer-split position (1-based) when the DH emits N
--     back-to-back QUESTION:/ANSWER: pairs for one field.  NULL
--     for the canonical single row (no split).
--   * UNIQUE rewritten to include attempt_id + item_index so the
--     four DH filename variants can ingest without collisions:
--       <field>.txt                  (attempt_id NULL, item_index NULL)
--       <field>_M.txt                (attempt_id NULL, item_index = M)
--       <field>__NNN.txt             (attempt_id = NNN, item_index NULL)
--       <field>__NNN_M.txt           (attempt_id = NNN, item_index = M)
--   * session_id and attempt_id FKs CASCADE on delete.
--   * New explicit index on attempt_id.
-- ------------------------------------------------------------
CREATE TABLE chunks (
    id               BIGSERIAL     PRIMARY KEY,                                              -- auto-incrementing PK
    session_id       TEXT          NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                                                                                              -- -> sessions.session_id
    attempt_id       BIGINT        REFERENCES dc_attempts(attempt_id) ON DELETE CASCADE,     -- -> dc_attempts.attempt_id (NULL = session-level)
    agent_from       TEXT          NOT NULL,                -- originating agent identifier (indexed)
    agents_to        TEXT[]        NOT NULL,                -- access-control list (GIN indexed)
    field            TEXT          NOT NULL,                -- DH schedule field (e.g. 'Plan') (indexed)
    field_type       TEXT          NOT NULL                 -- 'Semantic' | 'Quantitative' (CHECK-enforced in v2)
                                   CHECK (field_type IN ('Semantic', 'Quantitative')),
    question         TEXT,                                  -- DH's literal question text
    body             TEXT          NOT NULL,                -- Answer (Semantic) or JSON payload (Quantitative)
    item_index       SMALLINT,                              -- 1-based multi-answer-split index; NULL = canonical single row
    embedding        vector(1024),                          -- cosine-similarity vector (HNSW index); NULL for Quantitative
    embedding_model  TEXT,                                  -- e.g. 'openai/text-embedding-3-large/1024'
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
CREATE INDEX idx_chunks_attempt_id ON chunks (attempt_id);   -- explicit FK index (new in v2)
CREATE INDEX idx_chunks_agents_to  ON chunks USING GIN  (agents_to);
CREATE INDEX idx_chunks_embedding  ON chunks USING hnsw (embedding vector_cosine_ops);


-- ------------------------------------------------------------
-- dc_attempt_parameters
-- Long-format scalar mirror for masked-RMSE analytics. Composite PK.
-- Unchanged from v1 (already had ON DELETE CASCADE).
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
