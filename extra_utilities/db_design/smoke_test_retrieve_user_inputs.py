"""Phase 5B smoke test for retrieve_user_inputs.

Live test against:
  * Railway Postgres (sessions + rag_queries tables — schema v7).
  * Cloudflare R2 (PUT + GET + LIST under <SMOKE_SESSION_ID>/user_inputs/).

Exercises 8 named assertions covering the happy path, the local layout
(images under ``input_images/``, mirroring the live tree), the cache
re-read, the pre-extraction fallback, missing R2 files, unknown session
IDs, the token-cap trim, and the rag_queries log row.

Run from repo root::

    python extra_utilities/db_design/smoke_test_retrieve_user_inputs.py

Cost: a handful of R2 PUTs (~1 KB each) + a dozen GETs + a few Postgres
queries.  Sub-cent; sub-second wall-clock excluding cold starts.

Cleanup: always wipes its own synthetic data — sessions + rag_queries
rows, R2 objects, AND the local ``inputs/_retrieved/<sid>/`` folders the
tool materialises (the pre-2026-09-15 version of this test leaked those).
Set ``SMOKE_NO_CLEANUP=1`` to leave it all in place for inspection.

Revived 2026-09-15.  It had been dead for some time: it unpacked a
3-tuple from a function that returns a plain string, passed an
``images_flag`` argument the tool no longer has, asserted an
``<image_notes>`` block replaced by notes nested inside ``<image>``, and
never seeded an ``extracted_inputs.txt``, so every assertion exercised
the legacy no-extraction fallback rather than the live path.
"""

from __future__ import annotations

import os
import shutil
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
SESSION_A = f"_smoke_test_retrieve_a_{_TS}"   # extraction + images + note
SESSION_B = f"_smoke_test_retrieve_b_{_TS}"   # queries.txt only, NO extraction
SESSION_C = f"_smoke_test_retrieve_c_{_TS}"   # Postgres row only, no R2
SESSION_FAKE = f"_smoke_test_retrieve_fake_{_TS}"  # not in Postgres
CALLER = "_smoke_retrieve"

IMG_NAME = "blade_ref.png"
SIDECAR_NAME = "blade_ref.compression.json"
NOTE_NAME = "blade_ref_note.txt"


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

EXTRACTION_TEXT = (
    "QUANTITATIVE INPUTS:\n"
    "  Blade count: 5\n\n"
    "QUALITATIVE DESCRIPTIONS:\n"
    "  The ring should read as thin.\n\n"
    "DESIGN INTENT:\n"
    "  A clean five-blade ring propeller.  INTERPRETATION: straightforward\n\n"
    "USEFUL INPUT IMAGES:\n"
    "  blade_ref.png — swept blade reference.\n"
)

# The literal the response must NOT contain for SESSION_A: the raw
# conversation stays on disk once an extraction exists.  That is the whole
# premise of F99, so it is asserted rather than assumed.
RAW_ONLY_PHRASE = "and please hurry, the review is tomorrow"


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


def _cleanup_local(sid: str) -> None:
    """Remove ``inputs/_retrieved/<sid>/``, which the tool materialises.

    In a real session ``loader.py`` deletes the whole cache at End Session;
    a smoke test has no End Session, so it cleans up after itself.
    """
    shutil.rmtree(mod._retrieved_dir(sid), ignore_errors=True)  # noqa: SLF001


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
        # SESSION_FAKE: NOT inserted (test 6)

        # Seed R2.  A is the modern shape: extraction + raw conversation +
        # image + note + compression sidecar.  B predates extractions, so it
        # has queries.txt alone.  C has nothing.
        _put_r2_text(
            f"{SESSION_A}/user_inputs/extracted_inputs.txt",
            EXTRACTION_TEXT,
        )
        _put_r2_text(
            f"{SESSION_A}/user_inputs/queries.txt",
            "--- [2026-06-03 10:00:00] USER ---\n"
            "make me a propeller with 5 thin blades and a clean ring, "
            f"{RAW_ONLY_PHRASE}\n"
            "--- [2026-06-03 10:00:12] RECEPTIONIST ---\n"
            "Understood — forwarding that now.\n",
        )
        _put_r2_text(
            f"{SESSION_A}/user_inputs/images/{NOTE_NAME}",
            "A reference photo showing a swept blade with a thin trailing edge.",
        )
        _put_r2_bytes(
            f"{SESSION_A}/user_inputs/images/{IMG_NAME}",
            PNG_BYTES,
        )
        _put_r2_text(
            f"{SESSION_A}/user_inputs/images/{SIDECAR_NAME}",
            '{"degree": 60}',
        )

        _put_r2_text(
            f"{SESSION_B}/user_inputs/queries.txt",
            "--- [2026-06-03 10:30:00] USER ---\n"
            "design a simple ring propeller",
        )

        # SESSION_C: Postgres row exists; R2 has nothing → tests <missing/>

        # Start from a clean local cache so test 1 exercises the FETCH path
        # and test 3 exercises the CACHE path, deterministically.
        for _sid in (SESSION_A, SESSION_B, SESSION_C):
            _cleanup_local(_sid)

        # ============================================================
        # Test 1: happy_path_with_extraction
        # ============================================================
        xml = _run_retrieve_user_inputs(
            caller_agent=CALLER,
            session_ids=[SESSION_A],
        )
        assert "<extracted_inputs>" in xml, (
            f"missing <extracted_inputs>:\n{xml[:600]}"
        )
        assert "QUANTITATIVE INPUTS" in xml, "extraction body did not survive"
        assert "<user_query>" not in xml, (
            "<user_query> must NOT be printed when an extraction exists — "
            "the raw conversation stays on disk (F99)"
        )
        assert RAW_ONLY_PHRASE not in xml, (
            "the raw conversation leaked into the response"
        )
        assert "<images>" in xml, "missing <images> block"
        assert "swept blade" in xml, "expected note text nested in <image>"
        assert "blade_ref" in xml, "missing image name in XML"
        print("OK happy_path_with_extraction")

        # ============================================================
        # Test 2: local_layout_mirrors_live_tree
        # ============================================================
        dest = mod._retrieved_dir(SESSION_A)          # noqa: SLF001
        img_dir = mod._images_dir(dest)               # noqa: SLF001
        assert (img_dir / IMG_NAME).is_file(), (
            f"image not at {img_dir / IMG_NAME}; retrieval must mirror the "
            f"live tree's input_images/ subfolder"
        )
        assert (img_dir / NOTE_NAME).is_file(), "note did not follow the image"
        assert (img_dir / SIDECAR_NAME).is_file(), (
            "compression sidecar must sit BESIDE its image — that is where "
            "image_compression.read_degree looks"
        )
        assert not (dest / IMG_NAME).exists(), (
            "image is ALSO at the folder root; the flat layout should be gone"
        )
        assert (dest / "queries.txt").is_file(), "queries.txt should be at root"
        assert (dest / "extracted_inputs.txt").is_file(), (
            "extracted_inputs.txt should be at root"
        )
        # <folder> must still be a complete inventory now that it is nested.
        assert f"input_images/{IMG_NAME}" in xml, (
            f"<folder> did not list the nested image; got:\n{xml[:900]}"
        )
        # The printed <image path=...> must point INTO the subfolder.
        assert str((img_dir / IMG_NAME).resolve()) in xml, (
            "<image path=...> does not point at the materialised file"
        )
        print("OK local_layout_mirrors_live_tree")

        # ============================================================
        # Test 3: cache_reread
        # ------------------------------------------------------------
        # The second call is served from disk by _local_images().  Pointed
        # at the wrong folder it silently returns NO images, which only ever
        # shows on a repeat retrieval — so it is asserted explicitly.
        # ============================================================
        xml_cached = _run_retrieve_user_inputs(
            caller_agent=CALLER,
            session_ids=[SESSION_A],
        )
        assert "<images>" in xml_cached, (
            "cached re-read lost the <images> block"
        )
        assert "blade_ref" in xml_cached, "cached re-read lost the image"
        assert "swept blade" in xml_cached, "cached re-read lost the note"
        assert "<extracted_inputs>" in xml_cached, (
            "cached re-read lost the extraction"
        )
        assert f"input_images/{IMG_NAME}" in xml_cached, (
            "cached re-read dropped the nested image from <folder>"
        )
        print("OK cache_reread")

        # ============================================================
        # Test 4: no_extraction_falls_back_to_raw
        # ============================================================
        xml = _run_retrieve_user_inputs(
            caller_agent=CALLER,
            session_ids=[SESSION_B],
        )
        assert "<user_query>" in xml, (
            "a session archived before extractions must fall back to the raw "
            f"text; got:\n{xml[:600]}"
        )
        assert "ring propeller" in xml, "missing queries.txt content"
        assert "<missing" in xml, (
            "the fallback should also mark the absent extraction"
        )
        assert "<images>" not in xml, "<images> should be absent — B has none"
        print("OK no_extraction_falls_back_to_raw")

        # ============================================================
        # Test 5: r2_missing_everything
        # ============================================================
        xml = _run_retrieve_user_inputs(
            caller_agent=CALLER,
            session_ids=[SESSION_C],
        )
        assert "<missing" in xml, (
            f"expected <missing/> marker, got:\n{xml[:500]}"
        )
        assert "queries.txt" in xml, "expected queries.txt in missing marker"
        print("OK r2_missing_everything")

        # ============================================================
        # Test 6: not_found
        # ============================================================
        xml = _run_retrieve_user_inputs(
            caller_agent=CALLER,
            session_ids=[SESSION_FAKE],
        )
        assert 'status="not_found"' in xml, (
            f"expected status=\"not_found\", got:\n{xml[:500]}"
        )
        assert SESSION_FAKE in xml, "fake session_id should appear in response"
        print("OK not_found")

        # ============================================================
        # Test 7: trim_cap
        # ============================================================
        original_cap = mod._MAX_RESPONSE_TOKENS
        try:
            # Tight enough that not all 3 sessions can fit at once.
            mod._MAX_RESPONSE_TOKENS = 150
            xml = _run_retrieve_user_inputs(
                caller_agent=CALLER,
                session_ids=[SESSION_A, SESSION_B, SESSION_C],
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
        # Test 8: rag_queries_log
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
        # Six calls reach the tool: tests 1, 3, 4, 5, 6 and 7.  Test 2 makes
        # no call of its own -- it inspects the disk the first call wrote,
        # and the XML that call returned.
        assert row_count >= 6, (
            f"expected >= 6 rag_queries rows from this test, got {row_count}"
        )
        assert latest is not None, "no rag_queries rows found"
        n_req, n_ret, images_flag, tool_name, query_params = latest
        assert tool_name == "retrieve_user_inputs", (
            f"unexpected tool_name: {tool_name}"
        )
        assert n_req is not None and n_req >= 1
        assert images_flag is False, (
            "images_flag must be False — no image bytes reach the caller's "
            f"context any more; got {images_flag}"
        )
        print(
            f"OK rag_queries_log "
            f"(latest: tool={tool_name}, n_requested={n_req}, "
            f"n_returned={n_ret}, images_flag={images_flag}, "
            f"total_rows_this_test={row_count})"
        )

        print()
        print("PASS - retrieve_user_inputs smoke test (8/8)")
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
                    _cleanup_local(sid)
                except Exception as exc:
                    print(f"  local cleanup warning for {sid}: {exc}")
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
