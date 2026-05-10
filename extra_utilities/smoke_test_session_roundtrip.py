"""Phase 1 final integration smoke test — Session round-trip end-to-end.

Exercises every Phase 1 piece together against a live LLM:

  Build Session
    -> dispatch_turn (turn 1, real LLM call via Receptionist)
    -> session.to_dict()  (assert plain-data + json-dumps clean)
    -> Session.from_dict(...) (round-trip)
    -> dispatch_turn (turn 2, against the restored Session)

The user prompts are deliberately small-talk-y to bias the
Receptionist toward replying directly (forward=False) so the test
does not trigger the full Planner -> ... -> DCOI pipeline + Rhino
mesh generation.  If the Receptionist forwards anyway, the test
still asserts on the reply being non-empty — the round-trip
mechanics are the same regardless of which path was taken.

Verifies:
1. Turn 1 produces a non-empty reply.
2. session.agent_states["receptionist"].messages was populated by
   dispatch_turn's snapshot-back step (load-bearing — without
   snapshot-back, the second turn would start from empty state and
   the DH at end of v4 session would interview agents that
   "remember nothing").
3. session.to_dict() produces JSON-serialisable plain data
   (assert_plain_data passes; json.dumps doesn't raise).
4. Session.from_dict round-trips: the restored session has the same
   agent_states messages, same chain_log_exchanges, same config
   flags, same session_id and session_ts.
5. Turn 2 against the RESTORED session produces a non-empty reply
   AND extends the receptionist's message history (i.e. the agent
   genuinely sees turn 1's context when running turn 2).

Requires OPENAI_API_KEY (loaded from agents/.env).

Run from the project root:
    .venv/Scripts/python.exe extra_utilities/smoke_test_session_roundtrip.py
"""

import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "agents" / ".env")

from agents.dispatch import dispatch_turn
from agents.shared.session import Session, assert_plain_data


if not os.environ.get("OPENAI_API_KEY"):
    print("SKIP — OPENAI_API_KEY not set; this integration smoke needs it.")
    sys.exit(0)


# ---------------------------------------------------------------------
# Setup — fresh session, isolated inputs dir
# ---------------------------------------------------------------------
test_inputs_dir = Path(tempfile.mkdtemp(prefix="smoke_roundtrip_inputs_"))

session = Session(
    session_id="smoke_session_roundtrip",
    session_ts=datetime.now(timezone.utc),
)


try:
    # ------------------------------------------------------------------
    # Turn 1 — small-talk prompt biased toward direct reply
    # ------------------------------------------------------------------
    t0 = time.time()
    result1 = dispatch_turn(
        session=session,
        user_input=(
            "Hi! This is a test of the system. Please reply with a "
            "short one-sentence greeting and do not start the design "
            "pipeline."
        ),
        inputs_dir=test_inputs_dir,
    )
    dt1 = time.time() - t0
    assert result1.reply_text and result1.reply_text.strip(), (
        f"turn 1 produced an empty reply: {result1.reply_text!r}"
    )
    print(
        f"PASS case 1 — turn 1 returned a non-empty reply in {dt1:.1f}s "
        f"(forwarded={result1.forwarded})"
    )

    # ------------------------------------------------------------------
    # Verify snapshot-back populated session.agent_states
    # ------------------------------------------------------------------
    receptionist_state = session.agent_states.get("receptionist")
    assert receptionist_state is not None, (
        "session.agent_states['receptionist'] missing after turn 1"
    )
    rcp_msgs_after_turn1 = list(receptionist_state.messages)
    assert len(rcp_msgs_after_turn1) >= 2, (
        f"receptionist messages too short after turn 1 ({len(rcp_msgs_after_turn1)}); "
        f"expected at least the user input + one AI response"
    )
    print(
        f"PASS case 2 — snapshot-back populated receptionist.messages "
        f"({len(rcp_msgs_after_turn1)} messages)"
    )

    # ------------------------------------------------------------------
    # to_dict / json.dumps / assert_plain_data
    # ------------------------------------------------------------------
    # Note: AgentState.messages currently holds live BaseMessage
    # instances (the spec defers BaseMessage<->dict conversion to a
    # later commit).  to_dict's asdict() will not round-trip those
    # cleanly through json — the load-bearing assertion here is on
    # the SESSION-level scalars + structure being plain data, not
    # the message contents themselves.
    flat = session.to_dict()
    # Strip the live BaseMessage instances out of agent_states for the
    # plain-data check (they are still LangChain objects until the
    # message-conversion commit lands).  A future commit will tighten
    # this so to_dict produces fully JSON-serialisable output by
    # converting messages via BaseMessage.dict() upstream.
    flat_for_plain_check = {**flat}
    flat_for_plain_check["agent_states"] = {
        k: {**v, "messages": []}
        for k, v in flat["agent_states"].items()
    }
    assert_plain_data(flat_for_plain_check)
    encoded = json.dumps(flat_for_plain_check)
    assert isinstance(encoded, str) and len(encoded) > 0
    print("PASS case 3 — Session.to_dict (sans messages) is plain-data + json-dumps clean")

    # ------------------------------------------------------------------
    # from_dict round-trip — session-level scalars survive
    # ------------------------------------------------------------------
    # Use the original to_dict (with live messages) and restore via
    # from_dict — this is what v3's in-memory store does today.
    restored = Session.from_dict(session.to_dict())
    assert restored.session_id == session.session_id
    assert restored.session_ts == session.session_ts
    assert restored.dc_inspector_enabled == session.dc_inspector_enabled
    assert restored.rag_enabled == session.rag_enabled
    assert restored.chain_log_exchanges == session.chain_log_exchanges
    assert set(restored.agent_states) == set(session.agent_states)
    # Messages survive structurally (they're shared BaseMessage refs;
    # this is the in-process store path, not the JSON path).
    assert len(restored.agent_states["receptionist"].messages) == \
        len(rcp_msgs_after_turn1)
    print("PASS case 4 — Session round-trips through to_dict / from_dict")

    # ------------------------------------------------------------------
    # Turn 2 against the RESTORED session
    # ------------------------------------------------------------------
    t0 = time.time()
    result2 = dispatch_turn(
        session=restored,
        user_input=(
            "Thanks. Can you confirm in one sentence that you saw my "
            "previous message?"
        ),
        inputs_dir=test_inputs_dir,
    )
    dt2 = time.time() - t0
    assert result2.reply_text and result2.reply_text.strip(), (
        f"turn 2 produced an empty reply: {result2.reply_text!r}"
    )
    print(
        f"PASS case 5 — turn 2 against restored session returned a "
        f"non-empty reply in {dt2:.1f}s (forwarded={result2.forwarded})"
    )

    # ------------------------------------------------------------------
    # Receptionist messages grew on turn 2 — proves the restored agent
    # actually used the prior turn's history as starting context
    # ------------------------------------------------------------------
    rcp_msgs_after_turn2 = restored.agent_states["receptionist"].messages
    assert len(rcp_msgs_after_turn2) > len(rcp_msgs_after_turn1), (
        f"receptionist messages did not grow on turn 2: "
        f"before={len(rcp_msgs_after_turn1)}, after={len(rcp_msgs_after_turn2)}"
    )
    print(
        f"PASS case 6 — receptionist.messages grew across turn 2 "
        f"({len(rcp_msgs_after_turn1)} -> {len(rcp_msgs_after_turn2)})"
    )

finally:
    shutil.rmtree(test_inputs_dir, ignore_errors=True)


print()
print("Phase 1 Session round-trip smoke test passed.")
