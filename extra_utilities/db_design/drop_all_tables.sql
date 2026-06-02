-- ============================================================
-- drop_all_tables.sql — DESTRUCTIVE.  Removes every Design-Copilot
-- table created by ``database_PostgreSQL_schema_v?.sql``.
--
-- Use this BEFORE re-applying a fresh schema version against a
-- database that already has the previous version's tables, since
-- ``CREATE TABLE`` is not idempotent.  Typical sequence::
--
--     python apply_schema.py drop_all_tables.sql
--     python apply_schema.py database_PostgreSQL_schema_v5.sql
--     python populate_dc_parameter_schemas.py
--
-- ``DROP TABLE IF EXISTS ... CASCADE`` is safe to run against a
-- database where some / none of the tables exist.  CASCADE drops the
-- FK-bearing tables in dependency order regardless of their listed
-- order here, but the listed order below mirrors the dependency tree
-- (leaves first, roots last) for clarity.
--
-- This file does NOT drop the ``vector`` extension — extensions are
-- shared installation state and the next schema apply expects it
-- already present.
-- ============================================================

DROP TABLE IF EXISTS rag_queries           CASCADE;
DROP TABLE IF EXISTS dc_attempt_parameters CASCADE;
DROP TABLE IF EXISTS chunks                CASCADE;
DROP TABLE IF EXISTS dc_attempts           CASCADE;
DROP TABLE IF EXISTS sessions              CASCADE;
DROP TABLE IF EXISTS dc_parameter_schemas  CASCADE;
