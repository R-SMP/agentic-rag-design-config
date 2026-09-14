"""Phase 5C smoke test for retrieve_attempt.

Live test against:
  * Railway Postgres (sessions + dc_attempts + rag_queries — schema v7).
  * Cloudflare R2 (PUT + GET + LIST under the Phase 5A key shape
    ``<sid>/attempts/<NNN>__<global_id>/<file>``).

8 named assertions covering the happy path, that retrieval hands back
PATHS and never image bytes, the render-view policy filter, the
has_renders=FALSE branch, the Postgres parameters fallback, unknown
global ids, the token-cap trim, and the rag_queries log row.

Run from repo root::

    python extra_utilities/db_design/smoke_test_retrieve_attempt.py

Cost: ~10 R2 PUTs (~70 bytes for the PNGs) + ~12 R2 GETs + a handful
of Postgres queries.  Sub-cent; sub-second wall-clock.

Cleanup: always wipes its own synthetic data (sessions row + cascaded
dc_attempts rows + rag_queries rows + R2 objects).  Set
``SMOKE_NO_CLEANUP=1`` to leave it in place for manual inspection.
"""

from __future__ import annotations

import json
import os
import struct
import sys
import time
import zlib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

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

# Force ``agents`` to import BEFORE ``tools`` (per CLAUDE.md note).
import agents  # noqa: F401, E402

from agents.shared import postgres_pool, r2_uploader  # noqa: E402
from psycopg.types.json import Json  # noqa: E402
from tools.retrieve_attempt import retrieve_attempt as mod  # noqa: E402
from tools.retrieve_attempt.retrieve_attempt import (  # noqa: E402
    _run_retrieve_attempt,
)
from workflow_settings import settings as workflow_settings  # noqa: E402


# ============================================================
# Test fixtures
# ============================================================
_TS = int(time.time())
SESSION_X = f"_smoke_test_retrieve_attempt_{_TS}"
CALLER = "_smoke_retrieve_attempt"

# attempt_label format: <YYYYMMDD>_<HHMMSS>_<NNN>_<slug>.  We bake
# the run timestamp into the slug so re-running within the same
# wall-clock second still produces unique labels (the UNIQUE
# constraint on dc_attempts.attempt_label would otherwise fail).
LABEL_A = f"20260603_120000_001_smoke_a_{_TS}"
LABEL_B = f"20260603_120000_002_smoke_b_{_TS}"
LABEL_C = f"20260603_120000_003_smoke_c_{_TS}"

NNN_A, NNN_B, NNN_C = "001", "002", "003"


def _minimal_png() -> bytes:
    """1×1 transparent PNG, generated in-memory (~70 bytes)."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
    ihdr = (
        struct.pack(">I", len(ihdr_data))
        + b"IHDR" + ihdr_data
        + struct.pack(">I", ihdr_crc)
    )
    raw = bytes([0, 0, 0, 0, 0])
    idat_data = zlib.compress(raw)
    idat_crc = zlib.crc32(b"IDAT" + idat_data)
    idat = (
        struct.pack(">I", len(idat_data))
        + b"IDAT" + idat_data
        + struct.pack(">I", idat_crc)
    )
    iend_crc = zlib.crc32(b"IEND")
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
    return sig + ihdr + idat + iend


PNG_BYTES = _minimal_png()


# ============================================================
# Setup helpers
# ============================================================
def _seed_session_for_attempt(sid: str) -> None:
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions ("
                "  session_id, session_ts, dc_name, dc_inspector_enabled, "
                "  schema_version, user_provided_images"
                ") VALUES (%s, NOW(), %s, %s, %s, %s) "
                "ON CONFLICT (session_id) DO NOTHING",
                (sid, "_smoke", False, 1, False),
            )


def _seed_attempt(
    sid: str, *, attempt_label: str, has_renders: bool,
    has_geometry: bool = True,
) -> int:
    """INSERT a dc_attempts row and return the BIGSERIAL attempt_id."""
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO dc_attempts ("
                "  session_id, attempt_label, schema_version, "
                "  parameters_json, has_geometry, has_renders"
                ") VALUES (%s, %s, %s, %s, %s, %s) "
                "RETURNING attempt_id",
                (
                    sid, attempt_label, 1,
                    Json({"bladeCount": 5, "_smoke": True}),
                    has_geometry, has_renders,
                ),
            )
            (gid,) = cur.fetchone()
    return int(gid)


def _put_r2_text(key: str, content: str) -> None:
    client = r2_uploader._client()  # noqa: SLF001
    bucket = r2_uploader._env("R2_BUCKET_NAME")  # noqa: SLF001
    full_key = f"{r2_uploader._key_prefix()}{key}"  # noqa: SLF001
    client.put_object(
        Bucket=bucket, Key=full_key,
        Body=content.encode("utf-8"), ContentType="text/plain",
    )


def _put_r2_bytes(key: str, data: bytes, content_type: str = "image/png") -> None:
    client = r2_uploader._client()  # noqa: SLF001
    bucket = r2_uploader._env("R2_BUCKET_NAME")  # noqa: SLF001
    full_key = f"{r2_uploader._key_prefix()}{key}"  # noqa: SLF001
    client.put_object(
        Bucket=bucket, Key=full_key, Body=data, ContentType=content_type,
    )


def _cleanup_r2_session(sid: str) -> None:
    client = r2_uploader._client()  # noqa: SLF001
    if client is None:
        return
    bucket = r2_uploader._env("R2_BUCKET_NAME")  # noqa: SLF001
    prefix = f"{r2_uploader._key_prefix()}{sid}/"  # noqa: SLF001
    keys_to_delete: list[dict] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            keys_to_delete.append({"Key": obj["Key"]})
    for i in range(0, len(keys_to_delete), 1000):
        batch = keys_to_delete[i:i + 1000]
        if batch:
            client.delete_objects(Bucket=bucket, Delete={"Objects": batch})


def _cleanup_postgres() -> None:
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM rag_queries WHERE caller_agent = %s",
                (CALLER,),
            )
            # CASCADE on dc_attempts.session_id removes attempts; on
            # rag_queries.session_id sets it NULL (already deleted above).
            cur.execute(
                "DELETE FROM sessions "
                "WHERE session_id LIKE '\\_smoke\\_test\\_retrieve\\_attempt\\_%' "
                "ESCAPE '\\'",
            )


# ============================================================
# Main
# ============================================================
def main() -> int:
    if not postgres_pool.is_enabled():
        print("FAIL - postgres_pool not enabled.  Set DATABASE_PUBLIC_URL or DATABASE_URL.")
        return 1
    if not r2_uploader.is_enabled():
        print("FAIL - r2_uploader not enabled.  Set R2_* env vars.")
        return 1

    print(f"[smoke-retrieve-attempt]  TS suffix = {_TS}")

    # Save originals so render-view flag patching can be reverted.
    _orig_iso = workflow_settings.ATTEMPT_VIEW_ISOMETRIC
    _orig_top = workflow_settings.ATTEMPT_VIEW_TOP
    _orig_side = workflow_settings.ATTEMPT_VIEW_SIDE
    # Added to the product after this suite was written, and it defaults
    # to True -- so every render_views_in_scope assertion below is wrong
    # unless each test pins it explicitly.
    _orig_bsv = workflow_settings.ATTEMPT_VIEW_BLADE_SECTIONS
    _orig_cap = mod._MAX_RESPONSE_TOKENS

    exit_code = 0
    try:
        print("[smoke-retrieve-attempt]  seeding test data...")

        _seed_session_for_attempt(SESSION_X)
        GID_A = _seed_attempt(
            SESSION_X, attempt_label=LABEL_A, has_renders=True,
        )
        GID_B = _seed_attempt(
            SESSION_X, attempt_label=LABEL_B, has_renders=False,
        )
        GID_C = _seed_attempt(
            SESSION_X, attempt_label=LABEL_C, has_renders=True,
        )
        FAKE_GID = 99_999_999

        # Seed R2 for A: full set (3 renders + description + parameters)
        base_a = f"{SESSION_X}/attempts/{NNN_A}__{GID_A}"
        _put_r2_text(
            f"{base_a}/description.txt",
            "A 5-blade ring propeller, smoke-test attempt A.",
        )
        _put_r2_text(
            f"{base_a}/parameters.json",
            '{"bladeCount": 5, "_smoke": true}',
        )
        _put_r2_bytes(f"{base_a}/render_isometric.png", PNG_BYTES)
        _put_r2_bytes(f"{base_a}/render_top.png", PNG_BYTES)
        _put_r2_bytes(f"{base_a}/render_side.png", PNG_BYTES)

        # Seed R2 for B: description + parameters only (no renders;
        # mirrors has_renders=False in Postgres)
        base_b = f"{SESSION_X}/attempts/{NNN_B}__{GID_B}"
        _put_r2_text(
            f"{base_b}/description.txt",
            "Smoke-test attempt B (no renders).",
        )
        _put_r2_text(
            f"{base_b}/parameters.json",
            '{"bladeCount": 3, "_smoke": true}',
        )

        # SESSION_X attempts/<NNN>__<GID_C>/: nothing in R2 (test 5)

        # ============================================================
        # Test 1: happy_path_with_renders (all 3 views ON in policy)
        # ============================================================
        workflow_settings.ATTEMPT_VIEW_ISOMETRIC = True
        workflow_settings.ATTEMPT_VIEW_TOP = True
        workflow_settings.ATTEMPT_VIEW_SIDE = True
        workflow_settings.ATTEMPT_VIEW_BLADE_SECTIONS = False
        xml = _run_retrieve_attempt(
            caller_agent=CALLER,
            global_attempt_ids=[GID_A],
        )
        assert "<description>" in xml, f"missing <description>:\n{xml[:500]}"
        assert "ring propeller" in xml, "missing description text"
        assert "<parameters>" in xml, "missing <parameters>"
        assert "bladeCount" in xml, "missing parameters content"
        assert "<renders>" in xml, "missing <renders>"
        assert 'render_views_in_scope="isometric,top,side"' in xml, (
            f"unexpected render_views_in_scope: {xml[:500]}"
        )
        for _f in ("render_isometric.png", "render_top.png",
                   "render_side.png"):
            assert _f in xml, f"missing {_f}"
        assert "<folder path=" in xml, "missing <folder> listing"
        print("OK happy_path_with_renders")

        # ============================================================
        # Test 2: renders_are_paths_never_bytes
        # ============================================================
        # The 2026-08-20 retrieval rework removed images_flag and image
        # attachment outright: this tool DOWNLOADS and names paths, and
        # ``view_images`` is what actually looks.  Pin that contract.
        xml = _run_retrieve_attempt(
            caller_agent=CALLER,
            global_attempt_ids=[GID_A],
        )
        assert "<description>" in xml
        assert "<parameters>" in xml
        assert "<render name=" in xml and "key=" in xml, (
            "renders must be named by PATH"
        )
        assert "base64" not in xml, "no image bytes may appear in the XML"
        print("OK renders_are_paths_never_bytes")

        # ============================================================
        # Test 3: render_view_policy_filter (only isometric ON)
        # ============================================================
        workflow_settings.ATTEMPT_VIEW_ISOMETRIC = True
        workflow_settings.ATTEMPT_VIEW_TOP = False
        workflow_settings.ATTEMPT_VIEW_SIDE = False
        workflow_settings.ATTEMPT_VIEW_BLADE_SECTIONS = False
        xml = _run_retrieve_attempt(
            caller_agent=CALLER,
            global_attempt_ids=[GID_A],
        )
        assert 'render_views_in_scope="isometric"' in xml, (
            f"expected only isometric in scope, got:\n{xml[:500]}"
        )
        assert "<renders>" in xml
        # Scoped to <renders> ON PURPOSE.  Test 1 cached all three PNGs
        # into attempts/_retrieved/<gid>/, and <folder> lists whatever is
        # on disk -- so the out-of-scope files legitimately still appear
        # there.  What the policy filters is the <renders> block.
        _renders = xml.split("<renders>")[1].split("</renders>")[0]
        assert "render_isometric.png" in _renders
        assert "render_top.png" not in _renders, "top is out of scope"
        assert "render_side.png" not in _renders, "side is out of scope"
        print("OK render_view_policy_filter")

        # ============================================================
        # Test 4: no_renders_attempt (has_renders=FALSE in Postgres)
        # ============================================================
        # Reset views back to all-on so the filter doesn't mask the test
        workflow_settings.ATTEMPT_VIEW_ISOMETRIC = True
        workflow_settings.ATTEMPT_VIEW_TOP = True
        workflow_settings.ATTEMPT_VIEW_SIDE = True
        workflow_settings.ATTEMPT_VIEW_BLADE_SECTIONS = False
        xml = _run_retrieve_attempt(
            caller_agent=CALLER,
            global_attempt_ids=[GID_B],
        )
        assert "<description>" in xml, "missing description"
        assert "<parameters>" in xml, "missing parameters"
        assert "<renders>" not in xml, (
            "<renders> should be absent (has_renders=FALSE)"
        )
        print("OK no_renders_attempt")

        # ============================================================
        # Test 5: parameters_fallback (Postgres row only; no R2)
        # ============================================================
        # GID_C has a dc_attempts row and NOTHING in R2.  The description
        # is unrecoverable and must still report <missing/>.  The
        # parameters must NOT, because dc_attempts.parameters_json is
        # JSONB NOT NULL and the tool falls back to it -- _seed_attempt
        # wrote {"bladeCount": 5, "_smoke": True} there.
        xml = _run_retrieve_attempt(
            caller_agent=CALLER,
            global_attempt_ids=[GID_C],
        )
        assert "<missing" in xml, (
            f"expected <missing/> markers, got:\n{xml[:500]}"
        )
        assert "description.txt" in xml, "expected description.txt in missing"
        assert f"{NNN_C}__{GID_C}/parameters.json" not in xml, (
            "parameters.json must NOT be reported missing -- the Postgres "
            f"fallback should have supplied it:\n{xml[:800]}"
        )
        assert "<parameters>" in xml, "expected <parameters> from Postgres"
        # Real JSON, not a double-encoded string: psycopg hands JSONB back
        # as a dict, and json.dumps over an already-serialised str would
        # wrap the whole thing in quotes.  THIS is the assertion that
        # proves the psycopg return type on live infra.
        _inner = xml.split("<parameters>")[1].split("</parameters>")[0]
        _inner = _inner.split("CDATA[")[1].split("]]")[0]
        assert json.loads(_inner) == {"bladeCount": 5, "_smoke": True}, (
            f"parameters CDATA did not round-trip: {_inner!r}"
        )
        # The fallback must not persist into the retrieval cache: a
        # non-empty folder makes every later call take the cache path and
        # stop re-trying R2 for the description and the renders.
        assert not list(mod._retrieved_dir(GID_C).glob("*")), (
            "the Postgres fallback must not persist into "
            f"{mod._retrieved_dir(GID_C)}"
        )
        print("OK parameters_fallback")

        # ============================================================
        # Test 6: not_found
        # ============================================================
        xml = _run_retrieve_attempt(
            caller_agent=CALLER,
            global_attempt_ids=[FAKE_GID],
        )
        assert 'status="not_found"' in xml, (
            f"expected not_found marker, got:\n{xml[:500]}"
        )
        assert str(FAKE_GID) in xml
        print("OK not_found")

        # ============================================================
        # Test 7: trim_cap
        # ============================================================
        mod._MAX_RESPONSE_TOKENS = 150
        try:
            xml = _run_retrieve_attempt(
                caller_agent=CALLER,
                global_attempt_ids=[GID_A, GID_B, GID_C],
            )
        finally:
            mod._MAX_RESPONSE_TOKENS = _orig_cap
        assert 'truncated="true"' in xml, (
            f"expected truncated=\"true\", got:\n{xml[:500]}"
        )
        assert "omitted_attempts=" in xml, (
            "expected <truncated omitted_attempts=\"K\"/> footer"
        )
        print("OK trim_cap")

        # ============================================================
        # Test 8: rag_queries_log
        # ============================================================
        with postgres_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) "
                    "FROM rag_queries "
                    "WHERE caller_agent = %s "
                    "  AND tool_name = 'retrieve_attempt'",
                    (CALLER,),
                )
                (row_count,) = cur.fetchone()
                cur.execute(
                    "SELECT n_requested, n_returned, images_flag, "
                    "       tool_name, query_params "
                    "FROM rag_queries "
                    "WHERE caller_agent = %s "
                    "  AND tool_name = 'retrieve_attempt' "
                    "ORDER BY id DESC "
                    "LIMIT 1",
                    (CALLER,),
                )
                latest = cur.fetchone()
        assert row_count >= 7, (
            f"expected >= 7 rag_queries rows from this test, got {row_count}"
        )
        assert latest is not None, "no rag_queries rows found"
        n_req, n_ret, images_flag, tool_name, query_params = latest
        assert tool_name == "retrieve_attempt", (
            f"unexpected tool_name: {tool_name}"
        )
        assert n_req is not None and n_req >= 1
        print(
            f"OK rag_queries_log "
            f"(latest: tool={tool_name}, n_requested={n_req}, "
            f"n_returned={n_ret}, images_flag={images_flag}, "
            f"total_rows_this_test={row_count})"
        )

        print()
        print("PASS - retrieve_attempt smoke test")
    except AssertionError as exc:
        print(f"FAIL - assertion: {exc}")
        exit_code = 1
    except Exception as exc:
        print(f"FAIL - unexpected: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        exit_code = 1
    finally:
        # Restore patched settings even if a test crashed mid-patch
        workflow_settings.ATTEMPT_VIEW_ISOMETRIC = _orig_iso
        workflow_settings.ATTEMPT_VIEW_TOP = _orig_top
        workflow_settings.ATTEMPT_VIEW_SIDE = _orig_side
        workflow_settings.ATTEMPT_VIEW_BLADE_SECTIONS = _orig_bsv
        mod._MAX_RESPONSE_TOKENS = _orig_cap

        if os.environ.get("SMOKE_NO_CLEANUP") == "1":
            print()
            print(
                "[smoke-retrieve-attempt]  SMOKE_NO_CLEANUP=1; "
                "leaving synthetic data in place."
            )
        else:
            print()
            print("[smoke-retrieve-attempt]  cleanup...")
            try:
                _cleanup_r2_session(SESSION_X)
            except Exception as exc:
                print(f"  R2 cleanup warning for {SESSION_X}: {exc}")
            try:
                _cleanup_postgres()
            except Exception as exc:
                print(f"  Postgres cleanup warning: {exc}")
            try:
                postgres_pool.close_pool()
            except Exception:
                pass
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
