"""Migrate Postgres from schema v7 to v8 (multimodal `chunks_mm` table).

Adds a SECOND chunks table, ``chunks_mm``, that holds the
voyage-multimodal-3.5 (2048-dim) re-embedding of every text entry
PLUS new rows for the session's images (user-input images + attempt
renders).  The original ``chunks`` table is NOT touched.

``chunks_mm`` is structurally identical to ``chunks`` except:

  * ``embedding`` is ``vector(2048)`` (was ``vector(1024)``), and
  * the HNSW index is built on a ``halfvec(2048)`` cast, because
    pgvector's HNSW index on the float ``vector`` type is capped at
    2000 dimensions (8 KB page limit).  ``halfvec`` raises the HNSW
    limit to 4000 dims.  ``halfvec`` requires pgvector >= 0.7.0.

Image rows reuse the existing column shape (no new columns):

  * user images  -> agent_from='User',        field='User Image Input'
  * renders      -> agent_from='tool_caller',  field='Attempt Visual Render'
  * both         -> field_type='Semantic', agents_to=DEFAULT_AGENTS_TO_ACL,
                    body = the image's R2 name, embedding_input = the
                    fused note/description text.

Metadata is REUSED, not duplicated: ``chunks_mm.session_id`` /
``attempt_id`` FK straight to the existing ``sessions`` /
``dc_attempts`` tables.

Idempotency
-----------
Every statement uses ``IF NOT EXISTS`` (table + indexes), so
re-running this script is a no-op.  The backfill that fills the
table is separate and is itself re-runnable per session.

The vector index is created in its OWN transaction, guarded by a
pgvector-version check: if ``halfvec`` is unavailable the table is
still created and usable (retrieval is not wired yet at v8), and a
clear warning is printed so the index can be added after a pgvector
upgrade.

Run from repo root::

    python extra_utilities/db_design/migrations/migrate_v7_to_v8.py

Exits 0 on success, non-zero on failure.

When to use this script
-----------------------
- **Existing v7 deployment** (Railway today): RUN THIS SCRIPT.  It
  adds ``chunks_mm`` + its indexes without touching any existing
  table or row.
- **Fresh deployment with empty DB**: do NOT need this script —
  applying ``database_PostgreSQL_schema_v8.sql`` directly via
  ``apply_schema.py`` already includes ``chunks_mm``.  Running this
  script anyway is harmless (idempotent).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Force stdout/stderr to UTF-8 with replace-on-error so the migration
# script runs cleanly on Windows consoles (cp1252 default).  Otherwise
# an arrow character in a status message would UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass

try:
    from dotenv import load_dotenv as _load_dotenv  # type: ignore
    _load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

from agents.shared import postgres_pool  # noqa: E402


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

# chunks_mm — a structural copy of chunks with vector(2048).  The CHECK
# and UNIQUE constraints are IDENTICAL to chunks (image rows are
# Semantic with a real embedding, so they satisfy the Semantic branch).
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS chunks_mm (
    id               BIGSERIAL     PRIMARY KEY,
    session_id       TEXT          NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    attempt_id       BIGINT        REFERENCES dc_attempts(attempt_id) ON DELETE CASCADE,
    agent_from       TEXT          NOT NULL,
    agents_to        TEXT[]        NOT NULL,
    field            TEXT          NOT NULL,
    field_type       TEXT          NOT NULL
                                   CHECK (field_type IN ('Semantic', 'Quantitative')),
    question         TEXT,
    body             TEXT          NOT NULL,
    item_index       SMALLINT,
    embedding        vector(2048),
    embedding_model  TEXT,
    embedding_input  TEXT,
    is_error         BOOLEAN       NOT NULL DEFAULT FALSE,
    is_empty         BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, agent_from, field, attempt_id, item_index, embedding_model),
    CONSTRAINT chunks_mm_embedding_consistent_with_field_type CHECK (
        (field_type = 'Quantitative' AND embedding IS NULL     AND embedding_model IS NULL)
        OR
        (field_type = 'Semantic'     AND is_empty)
        OR
        (field_type = 'Semantic'     AND embedding IS NOT NULL AND embedding_model IS NOT NULL)
    )
);
"""

_SECONDARY_INDEXES: list[tuple[str, str]] = [
    (
        "idx_chunks_mm_agent_from",
        "CREATE INDEX IF NOT EXISTS idx_chunks_mm_agent_from "
        "ON chunks_mm (agent_from)",
    ),
    (
        "idx_chunks_mm_field",
        "CREATE INDEX IF NOT EXISTS idx_chunks_mm_field "
        "ON chunks_mm (field)",
    ),
    (
        "idx_chunks_mm_attempt_id",
        "CREATE INDEX IF NOT EXISTS idx_chunks_mm_attempt_id "
        "ON chunks_mm (attempt_id)",
    ),
    (
        "idx_chunks_mm_agents_to",
        "CREATE INDEX IF NOT EXISTS idx_chunks_mm_agents_to "
        "ON chunks_mm USING GIN (agents_to)",
    ),
]

# Partial HNSW vector index built on a halfvec(2048) cast (pgvector
# >= 0.7.0).  Same partial predicate spirit as chunks: only rows that
# retrieval would actually return are indexed.  Note: image rows are
# Semantic with NOT is_empty / NOT is_error, so they ARE indexed.
_HALFVEC_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_chunks_mm_embedding ON chunks_mm
    USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops)
    WHERE embedding IS NOT NULL AND NOT is_error AND NOT is_empty;
"""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _version_tuple(ver: str) -> tuple[int, ...]:
    """Parse a pgvector extversion like '0.8.0' into (0, 8, 0).

    Tolerates trailing non-numeric segments (e.g. '0.7.0-rc1').
    """
    parts: list[int] = []
    for seg in ver.split("."):
        num = ""
        for ch in seg:
            if ch.isdigit():
                num += ch
            else:
                break
        if num == "":
            break
        parts.append(int(num))
    return tuple(parts)


def _version_ge(ver: str, minimum: tuple[int, ...]) -> bool:
    return _version_tuple(ver) >= minimum


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    if not postgres_pool.is_enabled():
        print(
            "FAIL - postgres_pool not enabled.  Set "
            "DATABASE_PUBLIC_URL (local dev) or DATABASE_URL "
            "(Railway internal) in .env before re-running."
        )
        return 1

    print("[migrate-v7-v8]  starting migration...")

    # 1. Table + secondary indexes (one transaction; commits on exit).
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_TABLE_SQL)
            print("[migrate-v7-v8]  CREATE TABLE chunks_mm OK")
            for name, sql in _SECONDARY_INDEXES:
                cur.execute(sql)
                print(f"[migrate-v7-v8]  CREATE INDEX {name} OK")

    # 2. Detect pgvector version, then create the halfvec HNSW index in
    #    its OWN transaction so a failure here cannot roll back the
    #    table above.
    ver: str | None = None
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            )
            row = cur.fetchone()
            ver = row[0] if row else None
    print(f"[migrate-v7-v8]  pgvector extension version = {ver!r}")

    if ver and _version_ge(ver, (0, 7, 0)):
        try:
            with postgres_pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(_HALFVEC_INDEX_SQL)
            print(
                "[migrate-v7-v8]  CREATE INDEX idx_chunks_mm_embedding "
                "(halfvec HNSW) OK"
            )
        except Exception as exc:  # noqa: BLE001 — index is best-effort
            print(
                f"[migrate-v7-v8]  WARN: halfvec HNSW index creation "
                f"failed: {type(exc).__name__}: {exc}"
            )
            print(
                "[migrate-v7-v8]         chunks_mm is created and usable; "
                "retrieval is not wired at v8 so the index can be added "
                "later."
            )
    else:
        print(
            f"[migrate-v7-v8]  SKIP vector index: pgvector {ver!r} lacks "
            "halfvec (need >= 0.7.0 for a vector(2048) HNSW index)."
        )
        print(
            "[migrate-v7-v8]         chunks_mm is created and usable; add "
            "idx_chunks_mm_embedding after upgrading pgvector."
        )

    # 3. Verification: confirm chunks_mm exists with the expected
    #    embedding column type + dimension.
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type, udt_name "
                "FROM information_schema.columns "
                "WHERE table_name = 'chunks_mm' "
                "  AND column_name = 'embedding'"
            )
            emb = cur.fetchone()
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name = 'chunks_mm'"
            )
            ncols = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM chunks_mm")
            nrows = cur.fetchone()[0]
            cur.execute(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'chunks_mm' ORDER BY indexname"
            )
            idxs = [r[0] for r in cur.fetchall()]

    print("[migrate-v7-v8]  verification —")
    print(f"[migrate-v7-v8]    chunks_mm columns      = {ncols}")
    print(f"[migrate-v7-v8]    chunks_mm.embedding    = {emb}")
    print(f"[migrate-v7-v8]    chunks_mm row count    = {nrows}")
    print(f"[migrate-v7-v8]    chunks_mm indexes      = {idxs}")

    try:
        postgres_pool.close_pool()
    except Exception:
        pass

    print()
    print("PASS - migration v7 -> v8 complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
