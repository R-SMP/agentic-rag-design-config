"""Phase 5B smoke test for retrieve_user_inputs.

Live test against:
  * Railway Postgres (sessions + rag_queries tables — schema v7).
  * Cloudflare R2 (PUT + GET + LIST under <SMOKE_SESSION_ID>/user_inputs/).

Exercises 7 named assertions covering the happy path, image
flag semantics, missing R2 files, unknown session IDs, the token-cap
trim, and the rag_queries log row.

Run from repo root::

    python extra_utilities/db_design/smoke_test_retrieve_user_inputs.py

Cost: a handful of R2 PUTs (~1 KB each) + 7-ish GETs + a few Postgres
queries.  Sub-cent; sub-second wall-clock excluding cold starts.

Cleanup: always wipes its own synthetic data (sessions + rag_queries
rows + R2 objects).  Set ``SMOKE_NO_CLEANUP=1`` to leave it in place
for manual inspection.
"""

from __future__ import annotations

import os
import struct
import sys
import time
import zlib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Force stdout/stderr to UTF-8 with replace-on-error so the script
# runs cleanly on Windows consoles (cp1252 default).
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

# Force the ``agents`` package to import BEFORE ``tools`` (per the
# project's circular-import note in CLAUDE.md).
import agents  # noqa: F401, E402

from agents.shared import postgres_pool, r2_uploader  # noqa: E402
from tools.retrieve_user_inputs import retrieve_user_inputs as mod  # noqa: E402
from tools.retrieve_user_inputs.retrieve_user_inputs import (  # noqa: E402
    _run_retrieve_user_inputs,
)


# ============================================================
# Test fixtures
# ============================================================
_TS = int(time.time())
SESSION_A = f"_smoke_test_retrieve_a_{_TS}"   # has images + note
SESSION_B = f"_smoke_test_retrieve_b_{_TS}"   # text only
SESSION_C = f"_smoke_test_retrieve_c_{_TS}"   # Postgres row only, no R2
SESSION_FAKE = f"_smoke_test_retrieve_fake_{_TS}"  # not in Postgres
CALLER = "_smoke_retrieve"


def _minimal_png() -> bytes:
    """Build a valid 1x1 transparent PNG entirely in-memory (~70 bytes).

    Generated from primitives so the byte sequence is provably valid
    rather than transcribed from a hex string that might be subtly
    wrong.
    """
    sig = b"\x89PNG\r\n\x1a\n"
    # IHDR: 1×1, 8-bit, RGBA, no interlace
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
    ihdr = (
        struct.pack(">I", len(ihdr_data))
        + b"IHDR" + ihdr_data
        + struct.pack(">I", ihdr_crc)
    )
    # IDAT: one row with filter byte 0 + one RGBA pixel (0,0,0,0)
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
def _seed_session(sid: str, *, has_images: bool) -> None:
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions ("
                "  session_id, session_ts, dc_name, dc_inspector_enabled, "
                "  schema_version, user_provided_images"
                ") VALUES (%s, NOW(), %s, %s, %s, %s) "
                "ON CONFLICT (session_id) DO NOTHING",
                (sid, "_smoke", False, 1, has_images),
            )


def _put_r2_text(key: str, content: str) -> None:
    client = r2_uploader._client()  # noqa: SLF001
    bucket = r2_uploader._env("R2_BUCKET_NAME")  # noqa: SLF001
    full_key = f"{r2_uploader._key_prefix()}{key}"  # noqa: SLF001
    client.put_object(
        Bucket=bucket,
        Key=full_key,
        Body=content.encode("utf-8"),
        ContentType="text/plain",
    )


def _put_r2_bytes(key: str, data: bytes, content_type: str = "image/png") -> None:
    client = r2_uploader._client()  # noqa: SLF001
    bucket = r2_uploader._env("R2_BUCKET_NAME")  # noqa: SLF001
    full_key = f"{r2_uploader._key_prefix()}{key}"  # noqa: SLF001
    client.put_object(
        Bucket=bucket,
        Key=full_key,
        Body=data,
        ContentType=content_type,
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
    # delete_objects caps at 1000 per call
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
            cur.execute(
                "DELETE FROM sessions "
                "WHERE session_id LIKE '\\_smoke\\_test\\_retrieve\\_%' "
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

    print(f"[smoke-retrieve-user-inputs]  TS suffix = {_TS}")

    exit_code = 0
    try:
        print("[smoke-retrieve-user-inputs]  seeding test data...")

        # Seed Postgres rows
        _seed_session(SESSION_A, has_images=True)
        _seed_session(SESSION_B, has_images=False)
        _seed_session(SESSION_C, has_images=False)
        # SESSION_FAKE: NOT inserted (test 5)

        # Seed R2 — A has full set; B has just queries.txt; C has nothing
        _put_r2_text(
            f"{SESSION_A}/user_inputs/queries.txt",
            "--- [2026-06-03 10:00:00] ---\n"
            "make me a propeller with 5 thin blades and a clean ring",
        )
        _put_r2_text(
            f"{SESSION_A}/user_inputs/images/blade_ref_note.txt",
            "A reference photo showing a swept blade with a thin trailing edge.",
        )
        _put_r2_bytes(
            f"{SESSION_A}/user_inputs/images/blade_ref.png",
            PNG_BYTES,
        )

        _put_r2_text(
            f"{SESSION_B}/user_inputs/queries.txt",
            "--- [2026-06-03 10:30:00] ---\n"
            "design a simple ring propeller",
        )

        # SESSION_C: Postgres row exists; R2 has nothing → tests <missing/> marker


        # ============================================================
        # Test 1: happy_path_with_images
        # ============================================================
        xml, image_blocks, image_paths = _run_retrieve_user_inputs(
            caller_agent=CALLER,
            session_ids=[SESSION_A],
            images_flag=True,
        )
        assert "<user_query>" in xml, f"missing <user_query>:\n{xml[:500]}"
        assert "swept blade" in xml, "expected note text in XML"
        assert "<image_notes>" in xml, "missing <image_notes> block"
        assert "<images>" in xml, "missing <images> block"
        assert "blade_ref" in xml, "missing image name in XML"
        assert len(image_blocks) == 1, (
            f"expected 1 image_block, got {len(image_blocks)}"
        )
        assert len(image_paths) == 1, (
            f"expected 1 image_path, got {len(image_paths)}"
        )
        assert "blade_ref.png" in image_paths[0], (
            f"image_path looks wrong: {image_paths[0]}"
        )
        print("OK happy_path_with_images")

        # ============================================================
        # Test 2: happy_path_no_images_flag
        # ============================================================
        xml, image_blocks, image_paths = _run_retrieve_user_inputs(
            caller_agent=CALLER,
            session_ids=[SESSION_A],
            images_flag=False,
        )
        assert "<user_query>" in xml
        assert "<image_notes>" in xml, (
            "<image_notes> should be present even with images_flag=False"
        )
        assert "swept blade" in xml, "note text should still appear"
        assert "<images>" not in xml, (
            "<images> block should be absent with images_flag=False"
        )
        assert len(image_blocks) == 0, (
            f"expected 0 image_blocks, got {len(image_blocks)}"
        )
        print("OK happy_path_no_images_flag")

        # ============================================================
        # Test 3: no_images_session
        # ============================================================
        xml, image_blocks, _ = _run_retrieve_user_inputs(
            caller_agent=CALLER,
            session_ids=[SESSION_B],
            images_flag=True,
        )
        assert "<user_query>" in xml, "missing <user_query>"
        assert "ring propeller" in xml, "missing queries.txt content"
        assert "<image_notes>" not in xml, (
            "<image_notes> should be absent — session B has no images"
        )
        assert "<images>" not in xml, "<images> should be absent"
        assert len(image_blocks) == 0
        print("OK no_images_session")

        # ============================================================
        # Test 4: r2_missing_queries
        # ============================================================
        xml, _, _ = _run_retrieve_user_inputs(
            caller_agent=CALLER,
            session_ids=[SESSION_C],
            images_flag=False,
        )
        assert "<missing" in xml, (
            f"expected <missing/> marker, got:\n{xml[:500]}"
        )
        assert "queries.txt" in xml, "expected queries.txt in missing marker"
        print("OK r2_missing_queries")

        # ============================================================
        # Test 5: not_found
        # ============================================================
        xml, _, _ = _run_retrieve_user_inputs(
            caller_agent=CALLER,
            session_ids=[SESSION_FAKE],
            images_flag=False,
        )
        assert 'status="not_found"' in xml, (
            f"expected status=\"not_found\", got:\n{xml[:500]}"
        )
        assert SESSION_FAKE in xml, "fake session_id should appear in response"
        print("OK not_found")

        # ============================================================
        # Test 6: trim_cap
        # ============================================================
        original_cap = mod._MAX_RESPONSE_TOKENS
        try:
            # Tight enough that not all 3 sessions can fit at once.
            mod._MAX_RESPONSE_TOKENS = 150
            xml, _, _ = _run_retrieve_user_inputs(
                caller_agent=CALLER,
                session_ids=[SESSION_A, SESSION_B, SESSION_C],
                images_flag=False,
            )
        finally:
            mod._MAX_RESPONSE_TOKENS = original_cap
        assert 'truncated="true"' in xml, (
            f"expected truncated=\"true\", got:\n{xml[:500]}"
        )
        assert "omitted_sessions=" in xml, (
            "expected <truncated omitted_sessions=\"K\"/> footer"
        )
        print("OK trim_cap")

        # ============================================================
        # Test 7: rag_queries_log
        # ============================================================
        with postgres_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) "
                    "FROM rag_queries "
                    "WHERE caller_agent = %s "
                    "  AND tool_name = 'retrieve_user_inputs'",
                    (CALLER,),
                )
                (row_count,) = cur.fetchone()
                cur.execute(
                    "SELECT n_requested, n_returned, images_flag, "
                    "       tool_name, query_params "
                    "FROM rag_queries "
                    "WHERE caller_agent = %s "
                    "  AND tool_name = 'retrieve_user_inputs' "
                    "ORDER BY id DESC "
                    "LIMIT 1",
                    (CALLER,),
                )
                latest = cur.fetchone()
        assert row_count >= 6, (
            f"expected >= 6 rag_queries rows from this test, got {row_count}"
        )
        assert latest is not None, "no rag_queries rows found"
        n_req, n_ret, images_flag, tool_name, query_params = latest
        assert tool_name == "retrieve_user_inputs", (
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
        print("PASS - retrieve_user_inputs smoke test")
    except AssertionError as exc:
        print(f"FAIL - assertion: {exc}")
        exit_code = 1
    except Exception as exc:
        print(f"FAIL - unexpected: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        exit_code = 1
    finally:
        if os.environ.get("SMOKE_NO_CLEANUP") == "1":
            print()
            print(
                "[smoke-retrieve-user-inputs]  SMOKE_NO_CLEANUP=1; "
                "leaving synthetic data in place."
            )
        else:
            print()
            print("[smoke-retrieve-user-inputs]  cleanup...")
            for sid in (SESSION_A, SESSION_B, SESSION_C):
                try:
                    _cleanup_r2_session(sid)
                except Exception as exc:
                    print(f"  R2 cleanup warning for {sid}: {exc}")
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
