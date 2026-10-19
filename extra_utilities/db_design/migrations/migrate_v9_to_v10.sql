-- ============================================================
-- migrate_v9_to_v10.sql — upgrade an existing schema-v9 database to v10.
--
-- Idempotent (safe to run more than once) and all-or-nothing (one
-- transaction).  REMOVES NO DATA: it adds two nullable columns to
-- dc_parameter_schemas.  See the "Changes vs v9" header of
-- database_PostgreSQL_schema_v10.sql.  Only a setup with choice or on/off
-- parameters needs them; a setup of numbers runs on v9 or v10 alike.
--
-- Run from the repo root:
--   py -3.13 extra_utilities/db_design/apply_schema.py extra_utilities/db_design/migrations/migrate_v9_to_v10.sql
-- Take a backup first (pg_dump, or the CSV + catalog method).
-- ============================================================

BEGIN;

ALTER TABLE dc_parameter_schemas ADD COLUMN IF NOT EXISTS param_type TEXT;
ALTER TABLE dc_parameter_schemas ADD COLUMN IF NOT EXISTS choices JSONB;

COMMIT;
