"""Smoke test for agents/shared/session.py.

Verifies:
1. A hand-built Session with several AgentStates and chain-log
   exchanges round-trips through to_dict / from_dict — every field
   survives serialisation and deserialisation.
2. assert_plain_data accepts the to_dict output, and json.dumps
   accepts it too (the strongest test of "plain data").
3. assert_plain_data raises TypeError with a dotted-path message
   when given a dict with a non-plain leaf, so smoke tests can pin
   the offending field.
4. Session.create_for_v3 namespaces the per-session paths under each
   base directory, while a bare ``Session(...)`` leaves the path
   fields at None — the path-convention separation between v3 and v4.
5. Unknown agent_key in AgentState raises ValueError so typos
   surface at construction time, not at serialisation time.

The test does not require any LLM credentials and does not touch
the filesystem (all paths are constructed but never resolved).

Run from the project root:
    .venv/Scripts/python.exe extra_utilities/smoke_test_session_to_from_dict.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.shared.session import (
    AgentState,
    Session,
    assert_plain_data,
)


# ---------------------------------------------------------------------
# Fixture — a Session with plausible state across several agents
# ---------------------------------------------------------------------
sample_session = Session.create_for_v3(
    session_id="ID042_20260510_153015",
    base_inputs_dir=Path("inputs"),
    base_attempts_dir=Path("attempts"),
    base_logs_dir=Path("logs"),
    session_ts=datetime(2026, 5, 10, 15, 30, 15, tzinfo=timezone.utc),
    user_id="vincenzo@eth",
    rag_enabled=True,  # an override of the baked default
)
sample_session.agent_states["receptionist"] = AgentState(
    agent_key="receptionist",
    messages=[{"role": "system", "content": "you are receptionist"}],
    cycle_start_ts=1715357415.123,
)
sample_session.agent_states["planner"] = AgentState(
    agent_key="planner",
    messages=[{"role": "system", "content": "you are planner"}],
    pending_hop={"target": "user_input_inspector", "message": "extract this"},
    current_plan="Step 1: ...\n\nStep 2: ...",
)
sample_session.agent_states["dc_input_creator"] = AgentState(
    agent_key="dc_input_creator",
    pending_image_blocks=[
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
    ],
    pending_image_paths=["/inputs/some_user_image.png"],
)
sample_session.chain_log_exchanges = [
    {"from_agent": "orchestrator", "to_agent": "planner",
     "message": "go", "ts": "2026-05-10T15:30:16+00:00"},
    {"from_agent": "planner", "to_agent": "user_input_inspector",
     "message": "extract", "ts": "2026-05-10T15:30:18+00:00"},
]


# ---------------------------------------------------------------------
# Case 1: round-trip via to_dict / from_dict
# ---------------------------------------------------------------------
d = sample_session.to_dict()
restored = Session.from_dict(d)

assert restored.session_id              == sample_session.session_id
assert restored.session_ts              == sample_session.session_ts
assert restored.user_id                 == sample_session.user_id
assert restored.dc_name                 == sample_session.dc_name
assert restored.schema_version          == sample_session.schema_version
assert restored.dc_inspector_enabled    == sample_session.dc_inspector_enabled
assert restored.rag_enabled             is True   # override survives
assert restored.mesh_checks             == sample_session.mesh_checks
assert restored.chain_access            == sample_session.chain_access
assert restored.keep_images_in_context  == sample_session.keep_images_in_context
assert restored.dcoi_comparison_mode    == sample_session.dcoi_comparison_mode
assert restored.planner_first           == sample_session.planner_first
assert restored.render_library          == sample_session.render_library
assert restored.chain_log_exchanges     == sample_session.chain_log_exchanges
assert restored.inputs_dir              == sample_session.inputs_dir
assert restored.attempts_dir            == sample_session.attempts_dir
assert restored.logs_dir                == sample_session.logs_dir
assert set(restored.agent_states)       == set(sample_session.agent_states)
for key, original in sample_session.agent_states.items():
    rt = restored.agent_states[key]
    assert rt.agent_key             == original.agent_key
    assert rt.messages              == original.messages
    assert rt.pending_hop           == original.pending_hop
    assert rt.pending_image_blocks  == original.pending_image_blocks
    assert rt.pending_image_paths   == original.pending_image_paths
    assert rt.cycle_start_ts        == original.cycle_start_ts
    assert rt.current_plan          == original.current_plan
print("PASS case 1 — Session round-trips to_dict / from_dict")


# ---------------------------------------------------------------------
# Case 2: assert_plain_data accepts to_dict output and json.dumps it
# ---------------------------------------------------------------------
assert_plain_data(d)
encoded = json.dumps(d)
assert isinstance(encoded, str) and len(encoded) > 0
print("PASS case 2 — assert_plain_data + json.dumps accept to_dict output")


# ---------------------------------------------------------------------
# Case 3: assert_plain_data raises with dotted path on non-plain leaf
# ---------------------------------------------------------------------
bad = {"agent_states": {"planner": {"current_plan": Path("/oops/live/object")}}}
try:
    assert_plain_data(bad)
except TypeError as e:
    msg = str(e)
    assert "agent_states.planner.current_plan" in msg, (
        f"expected dotted path 'agent_states.planner.current_plan' "
        f"in error, got: {msg}"
    )
    assert "Path" in msg, (
        f"expected 'Path' (or PosixPath/WindowsPath) in error, got: {msg}"
    )
    print("PASS case 3 — assert_plain_data points at the offending dotted path")
else:
    raise AssertionError("expected TypeError for Path leaf, got nothing")


# ---------------------------------------------------------------------
# Case 4: v3 factory namespaces paths; bare Session leaves them None
# ---------------------------------------------------------------------
v3 = Session.create_for_v3(
    session_id="X_001",
    base_inputs_dir=Path("inputs"),
    base_attempts_dir=Path("attempts"),
    base_logs_dir=Path("logs"),
)
assert v3.inputs_dir   == Path("inputs")   / "X_001"
assert v3.attempts_dir == Path("attempts") / "X_001"
assert v3.logs_dir     == Path("logs")     / "X_001"

bare = Session(
    session_id="legacy_v4",
    session_ts=datetime.now(timezone.utc),
)
assert bare.inputs_dir   is None
assert bare.attempts_dir is None
assert bare.logs_dir     is None
print("PASS case 4 — v3 factory namespaces paths; bare Session leaves them None")


# ---------------------------------------------------------------------
# Case 5: unknown agent_key in AgentState raises ValueError
# ---------------------------------------------------------------------
try:
    AgentState(agent_key="recpetionist")  # typo on purpose
except ValueError as e:
    assert "recpetionist" in str(e)
    print("PASS case 5 — unknown agent_key raises ValueError at construction")
else:
    raise AssertionError("expected ValueError for unknown agent_key")


print()
print("Session round-trip smoke test passed.")
