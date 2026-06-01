"""Smoke test for the Phase 3A foundation:

  - config.DATABASE_URL / config.DATABASE_PUBLIC_URL are visible.
  - workflow_settings.settings.DATABASE_ENTRY_MAX_RETRIES exists.
  - agents.shared.postgres_pool opens a connection to Railway,
    answers a trivial query, registers the pgvector adapter, and
    round-trips a vector(1024) literal.

Run from the repo root:

    python extra_utilities/db_design/smoke_test_postgres_pool.py

Exits 0 on success, non-zero on any failure (with a clear error
message).  Safe to re-run — does NOT mutate any table.

Expected output on success::

    [config]       DATABASE_URL: SET (postgres.railway.internal:5432/...)
    [config]       DATABASE_PUBLIC_URL: SET (zephyr.proxy.rlwy.net:57143/...)
    [settings]     DATABASE_ENTRY_MAX_RETRIES = 3
    [pool]         is_enabled() = True
    [pool]         opening pool against zephyr.proxy.rlwy.net:57143/railway
    [pool]         SELECT 1 -> (1,)
    [pgvector]     extension version: 0.8.2
    [pgvector]     vector round-trip OK: [0.1, 0.2, ..., 0.3] (1024 dims)
    [schema]       Tables: chunks, dc_attempt_parameters, dc_attempts, dc_parameter_schemas, rag_queries, sessions
    [schema]       dc_parameter_schemas (schema_version=1): 17 rows

    PASS - Postgres foundation is wired correctly.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

# Make the repo root importable so `config`, `agents.shared.postgres_pool`,
# and `workflow_settings.settings` resolve regardless of where the
# script is invoked from.  Same pattern as the other smoke tests in
# extra_utilities/, just one level deeper.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _mask(url: str) -> str:
    if not url:
        return "<empty>"
    try:
        return url.split("@", 1)[1]
    except IndexError:
        return "<unparseable>"


def main() -> int:
    # ----- 1. config -------------------------------------------------
    try:
        import config
    except Exception as exc:
        print(f"FAIL - could not import config: {exc}")
        return 1

    db_url = getattr(config, "DATABASE_URL", None)
    db_pub = getattr(config, "DATABASE_PUBLIC_URL", None)
    if db_url is None or db_pub is None:
        print(
            "FAIL - config is missing DATABASE_URL / DATABASE_PUBLIC_URL "
            "attributes.  Update config.py."
        )
        return 1
    print(
        f"[config]       DATABASE_URL: "
        f"{'SET (' + _mask(db_url) + ')' if db_url else 'EMPTY'}"
    )
    print(
        f"[config]       DATABASE_PUBLIC_URL: "
        f"{'SET (' + _mask(db_pub) + ')' if db_pub else 'EMPTY'}"
    )

    if not (db_url or db_pub):
        print(
            "FAIL - neither URL is set.  Put DATABASE_PUBLIC_URL "
            "in the repo-root .env (use the Railway proxy URL "
            "from the Postgres service Variables tab)."
        )
        return 1

    # ----- 2. settings -----------------------------------------------
    try:
        from workflow_settings import settings as workflow_settings
    except Exception as exc:
        print(f"FAIL - could not import workflow_settings.settings: {exc}")
        return 1
    retries = getattr(workflow_settings, "DATABASE_ENTRY_MAX_RETRIES", None)
    if not isinstance(retries, int) or retries < 1:
        print(
            f"FAIL - DATABASE_ENTRY_MAX_RETRIES is not a positive int "
            f"(got {retries!r}).  Update workflow_settings/settings.py."
        )
        return 1
    print(f"[settings]     DATABASE_ENTRY_MAX_RETRIES = {retries}")

    # ----- 3. pool wiring --------------------------------------------
    # NOTE: we load agents/shared/postgres_pool.py *directly* via
    # importlib instead of ``from agents.shared import postgres_pool``.
    # Going through the package would trigger ``agents/__init__.py``,
    # which imports the full Orchestrator (langchain + langgraph + the
    # whole agent dep tree).  This smoke test exists to verify the
    # Postgres wiring in isolation — it should run without requiring
    # the entire agent stack to be importable.  Production callers
    # outside this smoke test go through ``from agents.shared import
    # postgres_pool`` as normal.
    try:
        import importlib.util
        _spec = importlib.util.spec_from_file_location(
            "postgres_pool",
            _REPO_ROOT / "agents" / "shared" / "postgres_pool.py",
        )
        if _spec is None or _spec.loader is None:
            print("FAIL - could not build importlib spec for postgres_pool")
            return 1
        postgres_pool = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(postgres_pool)
    except Exception as exc:
        print(f"FAIL - could not import postgres_pool: {exc}")
        traceback.print_exc()
        return 1

    if not postgres_pool.is_enabled():
        print("FAIL - postgres_pool.is_enabled() returned False.")
        return 1
    print("[pool]         is_enabled() = True")

    try:
        print(f"[pool]         opening pool against {_mask(db_pub or db_url)}")
        with postgres_pool.connection() as conn:
            with conn.cursor() as cur:
                # Trivial sanity check.
                cur.execute("SELECT 1")
                row = cur.fetchone()
                print(f"[pool]         SELECT 1 -> {row}")
                if row != (1,):
                    print(f"FAIL - SELECT 1 returned {row!r}, expected (1,)")
                    return 1

                # pgvector extension is active?
                cur.execute(
                    "SELECT extversion FROM pg_extension "
                    "WHERE extname = 'vector'"
                )
                ext = cur.fetchone()
                if not ext:
                    print("FAIL - pgvector extension is not installed.")
                    return 1
                print(f"[pgvector]     extension version: {ext[0]}")

                # Vector round-trip — confirms register_vector is wired.
                # Cast a Python list to vector(1024) and back.  pgvector's
                # Python adapter should return either a list or numpy
                # array; we accept either.
                sample = [0.0] * 1024
                sample[0] = 0.1
                sample[1] = 0.2
                sample[1023] = 0.3
                cur.execute(
                    "SELECT %s::vector(1024) AS v",
                    (sample,),
                )
                v = cur.fetchone()[0]
                try:
                    dims = len(v)
                except TypeError:
                    print(
                        f"FAIL - vector round-trip returned non-iterable "
                        f"{type(v).__name__}: {v!r}"
                    )
                    return 1
                if dims != 1024:
                    print(
                        f"FAIL - vector round-trip returned {dims} dims, "
                        f"expected 1024"
                    )
                    return 1
                head = [round(float(x), 3) for x in list(v)[:3]]
                tail = round(float(v[-1]), 3)
                print(
                    f"[pgvector]     vector round-trip OK: "
                    f"{head} ... {tail} ({dims} dims)"
                )

                # ----- 4. schema sanity (read-only) ------------------
                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' "
                    "ORDER BY table_name"
                )
                tables = [r[0] for r in cur.fetchall()]
                expected = {
                    "chunks",
                    "dc_attempt_parameters",
                    "dc_attempts",
                    "dc_parameter_schemas",
                    "rag_queries",
                    "sessions",
                }
                missing = expected - set(tables)
                if missing:
                    print(f"FAIL - missing tables: {sorted(missing)}")
                    return 1
                print(f"[schema]       Tables: {', '.join(tables)}")

                cur.execute(
                    "SELECT COUNT(*) FROM dc_parameter_schemas "
                    "WHERE schema_version = 1"
                )
                (n,) = cur.fetchone()
                print(
                    f"[schema]       dc_parameter_schemas (schema_version=1): "
                    f"{n} rows"
                )
                if n != 17:
                    print(
                        f"FAIL - expected 17 parameter rows at "
                        f"schema_version=1, found {n}.  Run "
                        f"populate_dc_parameter_schemas.py."
                    )
                    return 1
    except postgres_pool.PostgresDisabledError as exc:
        print(f"FAIL - {exc}")
        return 1
    except Exception as exc:
        print(f"FAIL - pool / query error: {exc}")
        traceback.print_exc()
        return 1
    finally:
        postgres_pool.close_pool()

    print()
    print("PASS - Postgres foundation is wired correctly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
