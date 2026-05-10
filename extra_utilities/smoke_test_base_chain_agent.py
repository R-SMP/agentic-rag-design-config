"""Smoke test for agents/shared/base_chain_agent.py via the converted
Receptionist.

Verifies:
1. Constructing a Receptionist with a fresh AgentState + Session
   yields the expected initial attributes (empty messages, None
   pending_hop, system_prompt set, base_llm and llm both present,
   cycle_start_ts seeded to "now" since state.cycle_start_ts was None).
2. snapshot_state() returns an AgentState with shape matching the
   live Receptionist.
3. Round-trip: snapshot_state on one instance, then construct a
   second Receptionist from that AgentState — every field is
   preserved (messages, pending_hop, image buffers, cycle_start_ts).
4. Constructing without a Session raises TypeError (the Session is
   now mandatory).
5. AgentState.agent_key mismatched against the class's AGENT_KEY
   raises ValueError.
6. (Live LLM call) base_llm.invoke responds to a one-shot prompt —
   confirms the LLMClientCache + BaseChainAgent wiring delivers a
   working LLM client.  Requires OPENAI_API_KEY.

Run from the project root:
    .venv/Scripts/python.exe extra_utilities/smoke_test_base_chain_agent.py
"""

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load agents/.env into os.environ so case 6's OPENAI_API_KEY gate
# sees the key.  llm_provider already reads agents/.env via
# dotenv_values for LLM construction (so cases 1-5 work without this
# load), but the key is not propagated to os.environ unless we ask.
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "agents" / ".env")

from langchain_core.messages import HumanMessage

from agents.receptionist.receptionist import Receptionist
from agents.shared.session import AgentState, Session


def _build_session() -> Session:
    """A v4-mode Session with the workflow_settings defaults.

    No v3 path namespacing — bare Session with all-None path fields.
    """
    return Session(
        session_id="smoke_base_chain_agent",
        session_ts=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------
# Case 1: fresh construction yields expected initial attributes
# ---------------------------------------------------------------------
session = _build_session()
r = Receptionist(state=AgentState(agent_key="receptionist"), session=session)

assert r.AGENT_KEY == "receptionist"
assert r.messages == []
assert r._pending_hop is None
assert r._pending_image_blocks == []
assert r._pending_image_paths == []
assert isinstance(r.cycle_start_ts, float), (
    "cycle_start_ts must be seeded to a float on fresh construction"
)
assert r.system_prompt  # truthy non-empty string
assert r.base_llm is not None
assert r.llm is not None
assert r.llm is r.base_llm, (
    "Receptionist.llm should equal base_llm before set_tools binds tools"
)
assert r.session is session
assert r.keep_images_in_context is False  # session default
print("PASS case 1 — fresh Receptionist has expected initial attributes")


# ---------------------------------------------------------------------
# Case 2: snapshot_state shape
# ---------------------------------------------------------------------
snap = r.snapshot_state()
assert isinstance(snap, AgentState)
assert snap.agent_key == "receptionist"
assert snap.messages == []
assert snap.pending_hop is None
assert snap.pending_image_blocks == []
assert snap.pending_image_paths == []
assert snap.cycle_start_ts == r.cycle_start_ts
assert snap.current_plan == ""  # Receptionist has no plan; default
print("PASS case 2 — snapshot_state returns a correctly-shaped AgentState")


# ---------------------------------------------------------------------
# Case 3: round-trip through snapshot/restore
# ---------------------------------------------------------------------
# Mutate the live Receptionist with a plausible mid-session state.
r.messages.append(HumanMessage(content="user said something"))
r._pending_image_blocks.append(
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}
)
r._pending_image_paths.append("/inputs/x.png")
r.cycle_start_ts = 1715357415.5
# Simulate a routing-tool firing by setting pending_hop directly.
from agents.shared.routing_tools import AgentHop
r._pending_hop = AgentHop(target="orchestrator", message="forwarding")

snap2 = r.snapshot_state()

# Build a second Receptionist from the snapshot.
session2 = _build_session()
r2 = Receptionist(state=snap2, session=session2)

assert r2.messages == r.messages
assert r2._pending_image_blocks == r._pending_image_blocks
assert r2._pending_image_paths == r._pending_image_paths
assert r2.cycle_start_ts == 1715357415.5, (
    "cycle_start_ts must be honoured (not re-seeded) when state has a value"
)
assert r2._pending_hop is not None
assert r2._pending_hop.target == "orchestrator"
assert r2._pending_hop.message == "forwarding"
print("PASS case 3 — Receptionist round-trips through snapshot/restore")


# ---------------------------------------------------------------------
# Case 4: missing Session raises TypeError
# ---------------------------------------------------------------------
try:
    Receptionist(state=AgentState(agent_key="receptionist"))
except TypeError as e:
    assert "Session" in str(e)
    print("PASS case 4 — missing Session raises TypeError")
else:
    raise AssertionError("expected TypeError when Session is omitted")


# ---------------------------------------------------------------------
# Case 5: agent_key mismatch raises ValueError
# ---------------------------------------------------------------------
try:
    Receptionist(state=AgentState(agent_key="planner"), session=session)
except ValueError as e:
    assert "planner" in str(e) and "receptionist" in str(e)
    print("PASS case 5 — agent_key mismatch raises ValueError")
else:
    raise AssertionError("expected ValueError for agent_key mismatch")


# ---------------------------------------------------------------------
# Case 6: real LLM round-trip via base_llm
# ---------------------------------------------------------------------
if not os.environ.get("OPENAI_API_KEY"):
    print("SKIP  case 6 — OPENAI_API_KEY not set; skipping live LLM call")
else:
    t0 = time.time()
    response = r.base_llm.invoke([
        HumanMessage(content="Reply with the single word OK and nothing else."),
    ])
    dt = time.time() - t0
    text = (response.content or "").strip()
    assert isinstance(text, str) and len(text) > 0, (
        f"expected a non-empty string response, got {text!r}"
    )
    print(f"PASS case 6 — live LLM call returned {text!r} in {dt:.2f}s")


print()
print("BaseChainAgent / Receptionist smoke test passed.")
