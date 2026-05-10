"""Smoke test for agents/dispatch.py.

Verifies that ``dispatch_turn`` correctly:
1. Saves the user's text to ``{inputs_dir}/user_query.txt`` with a
   timestamp header.
2. Invokes the Receptionist's ``validate_input``.
3. When the Receptionist replies directly (forward=False), returns a
   TurnResult with ``forwarded=False`` and the receptionist's reply
   text — skips Orchestrator.dispatch entirely.
4. When the Receptionist forwards (forward=True), runs
   ``Orchestrator.dispatch`` with a kickoff that includes the
   receptionist's summary and returns a TurnResult with
   ``forwarded=True`` and the dispatch result.
5. When ``Orchestrator.dispatch`` returns an empty string, substitutes
   the documented internal-error fallback message.
6. Reuses an externally-supplied Orchestrator (does not build a new
   one) — the v4 loader's optimisation.

Receptionist + Orchestrator are stubbed via patch.object so the test
runs without LLM calls.

Run from the project root:
    .venv/Scripts/python.exe extra_utilities/smoke_test_dispatch_turn.py
"""

import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "agents" / ".env")

from agents.dispatch import TurnResult, dispatch_turn, save_user_input
from agents.orchestrator import Orchestrator
from agents.shared.session import Session


def _build_session() -> Session:
    return Session(
        session_id="smoke_dispatch_turn",
        session_ts=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------
# Case 1: save_user_input writes a timestamped header
# ---------------------------------------------------------------------
test_dir = Path(tempfile.mkdtemp(prefix="smoke_dispatch_save_"))
try:
    out = save_user_input("hello, design me a propeller", test_dir)
    assert out == test_dir
    query_path = test_dir / "user_query.txt"
    assert query_path.exists()
    content = query_path.read_text(encoding="utf-8")
    assert "hello, design me a propeller" in content
    assert "--- [" in content and "] ---" in content
    print("PASS case 1 — save_user_input writes timestamped entry")
finally:
    shutil.rmtree(test_dir, ignore_errors=True)


# ---------------------------------------------------------------------
# Case 2: forward=False returns the receptionist's direct reply
# ---------------------------------------------------------------------
session = _build_session()
orch = Orchestrator(session=session)
test_dir = Path(tempfile.mkdtemp(prefix="smoke_dispatch_direct_"))
try:
    fake_validation = {
        "forward": False,
        "message": "I cannot help with that — please rephrase.",
        "input_dir": str(test_dir.resolve()),
        "file_types": [],
    }
    with patch.object(
        orch.receptionist, "validate_input",
        return_value=fake_validation,
    ):
        result = dispatch_turn(
            session=session,
            user_input="some user input",
            inputs_dir=test_dir,
            orchestrator=orch,
        )
    assert isinstance(result, TurnResult)
    assert result.forwarded is False
    assert result.reply_text == "I cannot help with that — please rephrase."
    # save_user_input ran, so user_query.txt exists
    assert (test_dir / "user_query.txt").exists()
    print("PASS case 2 — forward=False returns receptionist's direct reply")
finally:
    shutil.rmtree(test_dir, ignore_errors=True)


# ---------------------------------------------------------------------
# Case 3: forward=True runs dispatch and includes summary in kickoff
# ---------------------------------------------------------------------
session3 = _build_session()
orch3 = Orchestrator(session=session3)
test_dir3 = Path(tempfile.mkdtemp(prefix="smoke_dispatch_forward_"))
try:
    fake_validation = {
        "forward": True,
        "message": "[Incoming from: Receptionist]\n\nUser wants 3-blade prop, "
                   "200mm dia, drone use",
        "input_dir": str(test_dir3.resolve()),
        "file_types": ["text"],
    }
    captured_kickoff = []

    def _fake_dispatch(kickoff):
        captured_kickoff.append(kickoff)
        return "Here is your design: 3 blades, 200mm diameter."

    with patch.object(
        orch3.receptionist, "validate_input",
        return_value=fake_validation,
    ), patch.object(orch3, "dispatch", side_effect=_fake_dispatch):
        result = dispatch_turn(
            session=session3,
            user_input="design me a 3-blade prop",
            inputs_dir=test_dir3,
            orchestrator=orch3,
        )
    assert result.forwarded is True
    assert result.reply_text == "Here is your design: 3 blades, 200mm diameter."
    assert len(captured_kickoff) == 1
    kickoff = captured_kickoff[0]
    assert "[Incoming from: Receptionist]" in kickoff
    # The duplicate inner [Incoming from: Receptionist] label must be
    # stripped before being embedded under the summary header.
    assert kickoff.count("[Incoming from: Receptionist]") == 1
    assert "User wants 3-blade prop, 200mm dia, drone use" in kickoff
    assert f"Input file directory: {test_dir3.resolve()}" in kickoff
    assert "Available file types: text" in kickoff
    print("PASS case 3 — forward=True runs dispatch with proper kickoff")
finally:
    shutil.rmtree(test_dir3, ignore_errors=True)


# ---------------------------------------------------------------------
# Case 4: empty dispatch result substitutes the fallback message
# ---------------------------------------------------------------------
session4 = _build_session()
orch4 = Orchestrator(session=session4)
test_dir4 = Path(tempfile.mkdtemp(prefix="smoke_dispatch_empty_"))
try:
    fake_validation = {
        "forward": True,
        "message": "forward please",
        "input_dir": str(test_dir4.resolve()),
        "file_types": [],
    }
    with patch.object(
        orch4.receptionist, "validate_input",
        return_value=fake_validation,
    ), patch.object(orch4, "dispatch", return_value=""):
        result = dispatch_turn(
            session=session4,
            user_input="ping",
            inputs_dir=test_dir4,
            orchestrator=orch4,
        )
    assert result.forwarded is True
    assert "internal error" in result.reply_text.lower()
    assert "please re-send" in result.reply_text.lower()
    print("PASS case 4 — empty dispatch substitutes the fallback message")
finally:
    shutil.rmtree(test_dir4, ignore_errors=True)


# ---------------------------------------------------------------------
# Case 5: an externally-supplied Orchestrator is reused (not rebuilt)
# ---------------------------------------------------------------------
session5 = _build_session()
external_orch = Orchestrator(session=session5)
test_dir5 = Path(tempfile.mkdtemp(prefix="smoke_dispatch_reuse_"))
try:
    fake_validation = {
        "forward": False,
        "message": "ok",
        "input_dir": str(test_dir5.resolve()),
        "file_types": [],
    }
    with patch.object(
        external_orch.receptionist, "validate_input",
        return_value=fake_validation,
    ):
        result = dispatch_turn(
            session=session5,
            user_input="x",
            inputs_dir=test_dir5,
            orchestrator=external_orch,
        )
    assert result.forwarded is False
    assert result.reply_text == "ok"
    print("PASS case 5 — externally-supplied Orchestrator is reused")
finally:
    shutil.rmtree(test_dir5, ignore_errors=True)


print()
print("dispatch_turn smoke test passed.")
