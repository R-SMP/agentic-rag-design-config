"""Smoke test for the v3 Phase 1 commit 6 conversion of DatabaseHandler
to a BaseChainAgent operating directly on session.agent_states (no
freeze/restore pump).

Verifies:
1. DatabaseHandler is a BaseChainAgent subclass with AGENT_KEY ==
   "database_handler"; constructing one materialises a slot in
   session.agent_states.
2. DatabaseHandler() without a Session raises TypeError (uniform with
   every other agent — every agent now requires a Session).
3. populate_database writes one .txt file per (agent, field) row in
   the truncated test SCHEDULE under session_dir/<agent>/<field>.txt
   with the expected content blocks.
4. populate_database does NOT mutate
   session.agent_states[agent_key].messages — the DH conversation
   runs in a local buffer.  This is the load-bearing W6/O4
   resolution: mid-DH-interview, the per-agent AgentState messages
   are byte-for-byte the same list object with the same contents
   as before populate_database was called.
5. populate_database can be invoked from JUST a Session (the
   orchestrator= kwarg is optional; the DH builds one internally
   when the caller doesn't supply it) — the use case Phase 3
   Streamlit will need.

LLM calls are mocked with a canned-response stub so the test is
deterministic and fast (no API calls, no spend).

Run from the project root:
    .venv/Scripts/python.exe extra_utilities/smoke_test_database_handler.py
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

from langchain_core.messages import HumanMessage

from agents.database_handler import database_handler as dh_module
from agents.database_handler.database_handler import DatabaseHandler
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.session import AgentState, Session


# ---------------------------------------------------------------------
# Fixture: a small SCHEDULE with two rows (one Semantic, one
# Quantitative) and canned LLM responses
# ---------------------------------------------------------------------
TEST_SCHEDULE = [
    {
        "agent_key": "planner",
        "field": "Test field A",
        "type": "Semantic",
        "description": "First test field, semantic",
    },
    {
        "agent_key": "user_input_inspector",
        "field": "Test field B",
        "type": "Quantitative",
        "description": "Second test field, quantitative",
    },
]


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content
        self.tool_calls = []


_call_log: list[tuple[str, str]] = []


def _fake_invoke(llm, messages, agent_label: str):
    """Canned-response stub for invoke_with_retry.

    Routes responses by the agent_label the DH passes:
      - "DH-formulate"  -> a one-line question
      - "DH<-<agent>"   -> a one-line answer
      - "DH-decide"     -> SAVE: <body>
    """
    _call_log.append((agent_label, str(messages[-1].content)[:60]))
    if agent_label == "DH-formulate":
        return _FakeResponse("What did you do this session?")
    if agent_label.startswith("DH<-"):
        agent_key = agent_label[len("DH<-"):]
        return _FakeResponse(f"I am the {agent_key} and I did stuff.")
    if agent_label == "DH-decide":
        return _FakeResponse(
            "SAVE: This session, the agent did stuff and produced output."
        )
    return _FakeResponse("(unexpected label: " + agent_label + ")")


def _build_session() -> Session:
    return Session(
        session_id="smoke_database_handler",
        session_ts=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------
# Case 1: DH is a BaseChainAgent subclass + state slot is created
# ---------------------------------------------------------------------
session = _build_session()
dh = DatabaseHandler(session=session)
assert isinstance(dh, BaseChainAgent)
assert dh.AGENT_KEY == "database_handler"
assert "database_handler" in session.agent_states
print("PASS case 1 — DatabaseHandler subclasses BaseChainAgent and registers its slot")


# ---------------------------------------------------------------------
# Case 2: DatabaseHandler() without Session raises TypeError
# ---------------------------------------------------------------------
try:
    DatabaseHandler()
except TypeError as e:
    assert "Session" in str(e)
    print("PASS case 2 — DatabaseHandler() without Session raises TypeError")
else:
    raise AssertionError("expected TypeError when Session is omitted")


# ---------------------------------------------------------------------
# Case 3+4: populate_database writes files AND does not mutate
# session.agent_states messages
# ---------------------------------------------------------------------
session2 = _build_session()
dh2 = DatabaseHandler(session=session2)

# Pre-populate two AgentStates with plausible session-time messages
# (so we can verify they're not mutated during the DH interview).
planner_state = session2.agent_states.setdefault(
    "planner", AgentState(agent_key="planner"),
)
planner_state.messages.append(HumanMessage(content="planner did its thing"))
pre_planner_id = id(planner_state.messages)
pre_planner_messages = list(planner_state.messages)

uii_state = session2.agent_states.setdefault(
    "user_input_inspector", AgentState(agent_key="user_input_inspector"),
)
uii_state.messages.append(HumanMessage(content="user wanted a 3-blade prop"))
pre_uii_id = id(uii_state.messages)
pre_uii_messages = list(uii_state.messages)

_call_log.clear()
test_dir = Path(tempfile.mkdtemp(prefix="smoke_dh_"))
try:
    with patch.object(dh_module, "invoke_with_retry", _fake_invoke), \
         patch.object(dh_module, "SCHEDULE", TEST_SCHEDULE):
        written = dh2.populate_database(test_dir)

    # Two schedule entries -> two files written
    assert written == 2, f"expected 2 entries written, got {written}"
    planner_file = test_dir / "planner" / "test_field_a.txt"
    uii_file = test_dir / "user_input_inspector" / "test_field_b.txt"
    assert planner_file.exists(), f"missing {planner_file}"
    assert uii_file.exists(), f"missing {uii_file}"

    planner_content = planner_file.read_text(encoding="utf-8")
    assert "--- Field ---" in planner_content
    assert "Test field A" in planner_content
    assert "What did you do this session?" in planner_content
    assert "agent did stuff" in planner_content

    print("PASS case 3 — populate_database wrote both .txt files with expected layout")

    # The KEY invariant: AgentState messages must NOT have been mutated.
    assert id(planner_state.messages) == pre_planner_id, (
        "planner_state.messages was REPLACED with a new list object — "
        "the W6/O4 resolution requires the same list to remain in place"
    )
    assert planner_state.messages == pre_planner_messages, (
        "planner_state.messages contents changed during populate_database"
    )
    assert id(uii_state.messages) == pre_uii_id
    assert uii_state.messages == pre_uii_messages
    print("PASS case 4 — session.agent_states messages unchanged across populate_database")

    # Sanity: the canned LLM calls fired in the expected pattern
    labels = [c[0] for c in _call_log]
    assert labels.count("DH-formulate") == 2  # once per field
    assert labels.count("DH<-planner") == 1
    assert labels.count("DH<-user_input_inspector") == 1
    assert labels.count("DH-decide") == 2
finally:
    shutil.rmtree(test_dir, ignore_errors=True)


# ---------------------------------------------------------------------
# Case 5: populate_database can be invoked without a pre-built
# orchestrator (Phase 3 Streamlit use case)
# ---------------------------------------------------------------------
session3 = _build_session()
dh3 = DatabaseHandler(session=session3)
test_dir2 = Path(tempfile.mkdtemp(prefix="smoke_dh_no_orch_"))
try:
    with patch.object(dh_module, "invoke_with_retry", _fake_invoke), \
         patch.object(dh_module, "SCHEDULE", TEST_SCHEDULE[:1]):
        # No orchestrator= kwarg supplied; the DH must build one internally.
        written = dh3.populate_database(test_dir2)
    assert written == 1
    assert (test_dir2 / "planner" / "test_field_a.txt").exists()
    print("PASS case 5 — populate_database works without an externally-supplied orchestrator")
finally:
    shutil.rmtree(test_dir2, ignore_errors=True)


print()
print("DatabaseHandler smoke test passed.")
