-- ============================================================
-- Design Copilot — PostgreSQL schema
-- 5 tables. Tables are ordered so foreign keys resolve in
-- creation order:
--   dc_parameter_schemas (standalone)
--   sessions
--   dc_attempts        (FK -> sessions)
--   chunks             (FK -> sessions, FK -> dc_attempts)
--   dc_attempt_parameters (FK -> dc_attempts)
-- ============================================================

-- Required extensions:
--   pgvector  -> for the vector(1024) column on chunks
CREATE EXTENSION IF NOT EXISTS vector;


-- ------------------------------------------------------------
-- dc_parameter_schemas
-- Versioned parameter inventory. Composite PK.
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
    PRIMARY KEY (schema_version, param_name)
);


-- ------------------------------------------------------------
-- sessions
-- Parent table — one row per saved session.
-- ------------------------------------------------------------
CREATE TABLE sessions (
    session_id            TEXT         PRIMARY KEY,         -- surrogate session identifier
    session_ts            TIMESTAMPTZ  NOT NULL,            -- when the session started
    user_id               TEXT,                             -- optional user identifier
    dc_name               TEXT         NOT NULL,            -- Design Copilot name (e.g. 'propeller')
    dc_inspector_enabled  BOOLEAN      NOT NULL,            -- whether DC inspector was active
    schema_version        INTEGER      NOT NULL,            -- parameter schema version active for this session
                                                            --   (logical ref to dc_parameter_schemas.schema_version;
                                                            --    not an enforceable FK because that PK is composite)
    final_outcome         TEXT,                             -- 'APPROVE' | 'REVISE' | NULL
    notes                 TEXT,                             -- free-text session notes
    saved_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW()  -- row creation timestamp
);


-- ------------------------------------------------------------
-- dc_attempts
-- One row per design iteration the user worked through.
-- ------------------------------------------------------------
CREATE TABLE dc_attempts (
    attempt_id      BIGSERIAL    PRIMARY KEY,               -- auto-incrementing PK
    session_id      TEXT         NOT NULL REFERENCES sessions(session_id),  -- -> sessions.session_id
    attempt_label   TEXT         NOT NULL UNIQUE,           -- '<TS>_<NNN>_<slug>' folder name
    schema_version  INTEGER      NOT NULL,                  -- schema used for this attempt (indexed)
                                                            --   (logical ref to dc_parameter_schemas, see note above)
    parameters_json JSONB        NOT NULL,                  -- full parameter snapshot
    outcome         TEXT,                                   -- 'APPROVE' | 'REVISE' | NULL
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),    -- row creation timestamp
    UNIQUE (session_id, attempt_label)
);

CREATE INDEX idx_dc_attempts_schema_version ON dc_attempts (schema_version);


-- ------------------------------------------------------------
-- chunks
-- Unified RAG corpus — many rows per session (HNSW vector index).
-- ------------------------------------------------------------
CREATE TABLE chunks (
    id               BIGSERIAL     PRIMARY KEY,             -- auto-incrementing PK
    session_id       TEXT          NOT NULL REFERENCES sessions(session_id),     -- -> sessions.session_id
    attempt_id       BIGINT        REFERENCES dc_attempts(attempt_id),           -- -> dc_attempts.attempt_id (NULL = session-level)
    agent_from       TEXT          NOT NULL,                -- originating agent identifier (indexed)
    agents_to        TEXT[]        NOT NULL,                -- access-control list (GIN indexed)
    field            TEXT          NOT NULL,                -- DH schedule field (e.g. 'Plan') (indexed)
    field_type       TEXT          NOT NULL,                -- 'Semantic' | 'Quantitative'
    question         TEXT,                                  -- DH's literal question text
    body             TEXT          NOT NULL,                -- Answer (Semantic) or JSON payload (Quantitative)
    embedding        vector(1024),                          -- cosine-similarity vector (HNSW index); NULL for Quantitative
    embedding_model  TEXT,                                  -- e.g. 'openai/text-embedding-3-large/1024'
    is_error         BOOLEAN       NOT NULL DEFAULT FALSE,  -- marks error rows
    is_empty         BOOLEAN       NOT NULL DEFAULT FALSE,  -- marks empty-answer rows
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),  -- row creation timestamp
    UNIQUE (session_id, agent_from, field, embedding_model)
);

CREATE INDEX idx_chunks_agent_from ON chunks (agent_from);
CREATE INDEX idx_chunks_field      ON chunks (field);
CREATE INDEX idx_chunks_agents_to  ON chunks USING GIN (agents_to);
CREATE INDEX idx_chunks_embedding  ON chunks USING hnsw (embedding vector_cosine_ops);


-- ------------------------------------------------------------
-- dc_attempt_parameters
-- Long-format scalar mirror for masked-RMSE analytics. Composite PK.
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
