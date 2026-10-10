-- ============================================================
-- migrate_v8_to_v9.sql — upgrade an existing schema-v8 database to v9.
--
-- Idempotent (safe to run more than once) and all-or-nothing (one
-- transaction).  REMOVES NO DATA: it adds one nullable column + index,
-- drops one redundant constraint, and fills retired_at on rows whose
-- parameter a later schema version dropped.  See the "Changes vs v8"
-- header of database_PostgreSQL_schema_v9.sql.
--
-- Run from the repo root:
--   py -3.13 extra_utilities/db_design/apply_schema.py extra_utilities/db_design/migrations/migrate_v8_to_v9.sql
-- Take a backup first (pg_dump, or the CSV + catalog method).
-- ============================================================

BEGIN;

-- 1. rag_queries.run_session_id: the calling session's id for every
--    session, saved or not (no foreign key).
ALTER TABLE rag_queries ADD COLUMN IF NOT EXISTS run_session_id TEXT;
CREATE INDEX IF NOT EXISTS idx_rag_queries_run_session_id
    ON rag_queries (run_session_id);

-- 2. dc_attempts: keep UNIQUE (session_id, attempt_label) — the upsert's
--    ON CONFLICT target — and drop the single-column UNIQUE on
--    attempt_label, whatever name it was created under.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint con
         WHERE con.conrelid = 'dc_attempts'::regclass
           AND con.contype = 'u'
           AND (SELECT array_agg(a.attname::text ORDER BY a.attname)
                  FROM pg_attribute a
                 WHERE a.attrelid = con.conrelid
                   AND a.attnum = ANY (con.conkey))
               = ARRAY['attempt_label', 'session_id']
    ) THEN
        RAISE EXCEPTION 'dc_attempts has no UNIQUE (session_id, attempt_label); '
                        'refusing to drop the attempt_label constraint';
    END IF;
END $$;

DO $$
DECLARE
    c text;
BEGIN
    FOR c IN
        SELECT con.conname
          FROM pg_constraint con
         WHERE con.conrelid = 'dc_attempts'::regclass
           AND con.contype = 'u'
           AND con.conkey = ARRAY[(SELECT a.attnum
                                     FROM pg_attribute a
                                    WHERE a.attrelid = 'dc_attempts'::regclass
                                      AND a.attname = 'attempt_label')]::smallint[]
    LOOP
        EXECUTE format('ALTER TABLE dc_attempts DROP CONSTRAINT %I', c);
    END LOOP;
END $$;

-- 3. dc_parameter_schemas: a parameter in version N that version N+1 no
--    longer has was retired when N+1 was seeded.  Same statement the
--    seeder (populate_dc_parameter_schemas.py) runs.  Today this marks
--    the v1 impellerHeight row.
UPDATE dc_parameter_schemas AS old
   SET retired_at = nxt.seeded_at
  FROM (SELECT schema_version, MIN(introduced_at) AS seeded_at
          FROM dc_parameter_schemas
         GROUP BY schema_version) AS nxt
 WHERE nxt.schema_version = old.schema_version + 1
   AND old.retired_at IS NULL
   AND NOT EXISTS (SELECT 1 FROM dc_parameter_schemas AS n
                    WHERE n.schema_version = old.schema_version + 1
                      AND n.param_name = old.param_name);

COMMIT;
