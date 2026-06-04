"""Smoke test for the /api/turn 202 + SSE turn_done flow (W31-area).

Exercises the request shape and the /api/events turn_done branch
with ``dispatch_turn`` monkey-patched to a synthetic stub.  Does
NOT exercise the multi-agent pipeline — that's covered by manual
in-browser verification.  Costs nothing to run (no LLM calls).

What gets verified
------------------
 1. POST /api/turn happy path returns HTTP 202 with
    ``{ok=True, status="started", turn_id=<12 hex chars>}``.
 2. POST /api/turn with empty / whitespace message returns HTTP 400.
 3. POST /api/turn while ``_TURN_IN_FLIGHT`` is True returns HTTP 409
    (concurrent-turn guard).
 4. End-to-end: open /api/events, POST /api/turn, the matching
    ``turn_done`` event arrives carrying the documented payload
    (turn_id, ok, reply, forwarded, artefacts, error).
 5. ``_TURN_IN_FLIGHT`` is cleared by the background task's
    ``finally`` (a follow-up POST after turn_done succeeds).

Run from the repo root::

    python extra_utilities/smoke_test_async_turn.py

Exits 0 on full pass, non-zero on any failure with a clear marker.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv as _load_dotenv  # type: ignore
    _load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

# Import agents BEFORE anything that touches ``tools`` (CLAUDE.md
# item 6 — same bootstrap as db_design/smoke_test_*.py).
import agents  # noqa: F401, E402

import httpx  # noqa: E402

import web_app  # noqa: E402


# ---------------------------------------------------------------------
# Stubs — keep the test focused on HTTP plumbing + SSE wiring, not
# the multi-agent stack.  ``dispatch_turn`` and ``_ensure_session``
# are both module-level names in web_app, so a simple setattr is
# enough to redirect them.
# ---------------------------------------------------------------------

def _fake_dispatch_turn(*, session, user_input, inputs_dir,
                       fixed_params=None, released_params=None):
    return SimpleNamespace(
        reply_text=f"fake reply to: {user_input}",
        forwarded=True,
        new_artefacts_paths=[],
    )


def _fake_ensure_session():
    return SimpleNamespace(session_id="smoke_test_session")


def _install_stubs() -> None:
    web_app.dispatch_turn = _fake_dispatch_turn
    web_app._ensure_session = _fake_ensure_session
    web_app._TURN_IN_FLIGHT = False
    os.environ.pop("INVITE_CODE", None)  # default-open auth


async def _wait_for_flag_clear(timeout: float = 3.0) -> None:
    """The background task clears ``_TURN_IN_FLIGHT`` in its finally
    AFTER publishing turn_done, so the event has definitely fired by
    the time the flag clears.  Cheaper than re-opening SSE."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while web_app._TURN_IN_FLIGHT:
        if loop.time() > deadline:
            raise AssertionError(
                "timed out waiting for _TURN_IN_FLIGHT to clear"
            )
        await asyncio.sleep(0.05)


# ---------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------

async def test_happy_path_202(client: httpx.AsyncClient) -> None:
    res = await client.post("/api/turn", json={"message": "hello"})
    assert res.status_code == 202, \
        f"expected 202, got {res.status_code}: {res.text}"
    body = res.json()
    assert body.get("ok") is True, f"ok mismatch: {body!r}"
    assert body.get("status") == "started", f"status mismatch: {body!r}"
    turn_id = body.get("turn_id")
    assert isinstance(turn_id, str) and len(turn_id) == 12, \
        f"turn_id shape: {turn_id!r}"
    await _wait_for_flag_clear()


async def test_empty_message_400(client: httpx.AsyncClient) -> None:
    res = await client.post("/api/turn", json={"message": "   "})
    assert res.status_code == 400, \
        f"expected 400, got {res.status_code}: {res.text}"


async def test_concurrent_turn_409(client: httpx.AsyncClient) -> None:
    web_app._TURN_IN_FLIGHT = True
    try:
        res = await client.post("/api/turn", json={"message": "second"})
        assert res.status_code == 409, \
            f"expected 409, got {res.status_code}: {res.text}"
    finally:
        web_app._TURN_IN_FLIGHT = False


async def test_sse_round_trip(client: httpx.AsyncClient) -> None:
    received: list[dict] = []
    sse_open = asyncio.Event()
    seen_turn_done = asyncio.Event()

    async def consume_sse() -> None:
        async with client.stream("GET", "/api/events", timeout=5.0) as r:
            assert r.status_code == 200
            first = True
            async for chunk in r.aiter_text():
                if first:
                    sse_open.set()
                    first = False
                for line in chunk.split("\n"):
                    if line.startswith("data: "):
                        evt = json.loads(line[len("data: "):])
                        received.append(evt)
                        if evt.get("type") == "turn_done":
                            seen_turn_done.set()
                            return

    consumer = asyncio.create_task(consume_sse())
    # Wait until the SSE stream is open + subscribed to viz_bus
    # before publishing.  The first chunk is the ``: connected``
    # comment line, which arrives as soon as ``api_events`` has
    # registered its queue with viz_bus.
    await asyncio.wait_for(sse_open.wait(), timeout=2.0)

    res = await client.post("/api/turn", json={"message": "smoke ping"})
    assert res.status_code == 202
    turn_id = res.json()["turn_id"]

    try:
        await asyncio.wait_for(seen_turn_done.wait(), timeout=3.0)
    finally:
        consumer.cancel()
        try:
            await consumer
        except (asyncio.CancelledError, Exception):
            pass

    turn_done = next(e for e in received if e.get("type") == "turn_done")
    assert turn_done["turn_id"] == turn_id, \
        f"turn_id mismatch: {turn_done['turn_id']!r} vs {turn_id!r}"
    assert turn_done["ok"] is True
    assert turn_done["reply"] == "fake reply to: smoke ping"
    assert turn_done["forwarded"] is True
    assert turn_done["artefacts"] == []
    assert turn_done["error"] is None
    await _wait_for_flag_clear()


async def test_flag_cleared_allows_followup(client: httpx.AsyncClient) -> None:
    res1 = await client.post("/api/turn", json={"message": "first"})
    assert res1.status_code == 202
    await _wait_for_flag_clear()
    assert web_app._TURN_IN_FLIGHT is False, "_TURN_IN_FLIGHT not cleared"

    res2 = await client.post("/api/turn", json={"message": "second"})
    assert res2.status_code == 202, \
        f"second POST got {res2.status_code} (expected 202): {res2.text}"
    await _wait_for_flag_clear()


# ---------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------

async def _main() -> int:
    _install_stubs()
    failures = 0
    tests = [
        test_happy_path_202,
        test_empty_message_400,
        test_concurrent_turn_409,
        test_sse_round_trip,
        test_flag_cleared_allows_followup,
    ]
    transport = httpx.ASGITransport(app=web_app.app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        for fn in tests:
            web_app._TURN_IN_FLIGHT = False
            try:
                await fn(client)
                print(f"  PASS  {fn.__name__}")
            except AssertionError as e:
                print(f"  FAIL  {fn.__name__}: {e}")
                failures += 1
            except Exception as e:
                print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
                failures += 1

    if failures:
        print(f"\n{failures} failure(s)")
        return 1
    print("\nPASS - /api/turn 202 + turn_done SSE flow verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
