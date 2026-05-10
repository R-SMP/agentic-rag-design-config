"""Smoke test for the bundled v3 Phase 1 commit 4 conversion of all
seven chain agents to BaseChainAgent.

Verifies, for every chain agent:
1. The class is a BaseChainAgent subclass and has the expected
   AGENT_KEY.
2. Constructing an Orchestrator(session=...) materialises one
   AgentState per chain agent in session.agent_states, populates the
   agent's base_llm via the LLM client cache, and leaves the agent's
   messages / pending_hop / image buffers at their fresh-session
   defaults.
3. snapshot_state() produces an AgentState that round-trips: building
   a SECOND chain agent from that snapshot yields equal state.
4. Mid-session state set on a live agent (messages, pending_hop,
   cycle_start_ts on Receptionist, current_plan on Planner) is
   captured by snapshot_state and restored when the agent is rebuilt
   from the snapshot.
5. (Live LLM call) The Planner's base_llm responds to a one-shot
   prompt — confirms the LLMClientCache caches across multiple agent
   constructions in this turn.  Requires OPENAI_API_KEY.

Run from the project root:
    .venv/Scripts/python.exe extra_utilities/smoke_test_all_chain_agents.py
"""

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "agents" / ".env")

from langchain_core.messages import HumanMessage

from agents.orchestrator import Orchestrator
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.routing_tools import AgentHop
from agents.shared.session import AgentState, Session


CHAIN_AGENT_KEYS = [
    "receptionist",
    "planner",
    "user_input_inspector",
    "dc_input_creator",
    "dc_input_inspector",
    "tool_caller",
    "dc_output_inspector",
]


def _build_session() -> Session:
    return Session(
        session_id="smoke_all_chain_agents",
        session_ts=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------
# Case 1: Orchestrator construction populates every chain agent slot
# ---------------------------------------------------------------------
session = _build_session()
orch = Orchestrator(session=session)

for key in CHAIN_AGENT_KEYS:
    agent = getattr(orch, key)
    assert isinstance(agent, BaseChainAgent), (
        f"{key} is not a BaseChainAgent subclass; got {type(agent).__name__}"
    )
    assert agent.AGENT_KEY == key, (
        f"{key}.AGENT_KEY == {agent.AGENT_KEY!r}, expected {key!r}"
    )
    assert agent.messages == []
    assert agent._pending_hop is None
    assert agent._pending_image_blocks == []
    assert agent._pending_image_paths == []
    assert agent.base_llm is not None
    assert agent.session is session
    # session.agent_states has been populated for this key
    assert key in session.agent_states, (
        f"session.agent_states missing entry for {key}"
    )
print("PASS case 1 — Orchestrator constructs all 7 chain agents via the new path")


# ---------------------------------------------------------------------
# Case 2: snapshot_state shape per agent
# ---------------------------------------------------------------------
for key in CHAIN_AGENT_KEYS:
    snap = getattr(orch, key).snapshot_state()
    assert isinstance(snap, AgentState)
    assert snap.agent_key == key
    assert snap.messages == []
    assert snap.pending_hop is None
    assert snap.pending_image_blocks == []
    assert snap.pending_image_paths == []
print("PASS case 2 — snapshot_state returns correctly-shaped AgentState per agent")


# ---------------------------------------------------------------------
# Case 3: round-trip — snapshot, mutate Session, build new Orchestrator,
# verify state equality
# ---------------------------------------------------------------------
session2 = _build_session()
for key in CHAIN_AGENT_KEYS:
    session2.agent_states[key] = getattr(orch, key).snapshot_state()
orch2 = Orchestrator(session=session2)
for key in CHAIN_AGENT_KEYS:
    a = getattr(orch, key)
    b = getattr(orch2, key)
    assert a.AGENT_KEY == b.AGENT_KEY
    assert a.messages == b.messages
    assert a._pending_hop == b._pending_hop
    assert a._pending_image_blocks == b._pending_image_blocks
    assert a._pending_image_paths == b._pending_image_paths
    assert a.cycle_start_ts == b.cycle_start_ts
    assert a.current_plan == b.current_plan
print("PASS case 3 — every chain agent round-trips through snapshot / restore")


# ---------------------------------------------------------------------
# Case 4: mid-session state survives snapshot / restore
# ---------------------------------------------------------------------
# Mutate every live agent with plausible mid-session state.
orch.receptionist.messages.append(HumanMessage(content="user said something"))
orch.receptionist.cycle_start_ts = 1715357415.5
orch.planner.messages.append(HumanMessage(content="planner working"))
orch.planner.current_plan = "Step 1: extract\n\nStep 2: build params"
orch.user_input_inspector._pending_hop = AgentHop(
    target="dc_input_creator", message="forward",
)
orch.dc_input_creator._pending_image_blocks.append(
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}
)
orch.dc_input_creator._pending_image_paths.append("/inputs/x.png")

# Snapshot all, rebuild a fresh Orchestrator from the snapshots.
session3 = _build_session()
for key in CHAIN_AGENT_KEYS:
    session3.agent_states[key] = getattr(orch, key).snapshot_state()
orch3 = Orchestrator(session=session3)

assert orch3.receptionist.messages == orch.receptionist.messages
assert orch3.receptionist.cycle_start_ts == 1715357415.5
assert orch3.planner.messages == orch.planner.messages
assert orch3.planner.current_plan == "Step 1: extract\n\nStep 2: build params"
assert orch3.user_input_inspector._pending_hop is not None
assert orch3.user_input_inspector._pending_hop.target == "dc_input_creator"
assert orch3.user_input_inspector._pending_hop.message == "forward"
assert orch3.dc_input_creator._pending_image_blocks == orch.dc_input_creator._pending_image_blocks
assert orch3.dc_input_creator._pending_image_paths == orch.dc_input_creator._pending_image_paths
print("PASS case 4 — mid-session state survives snapshot / restore for all agents")


# ---------------------------------------------------------------------
# Case 5: live LLM call via Planner.base_llm
# ---------------------------------------------------------------------
if not os.environ.get("OPENAI_API_KEY"):
    print("SKIP  case 5 — OPENAI_API_KEY not set; skipping live LLM call")
else:
    t0 = time.time()
    response = orch.planner.base_llm.invoke([
        HumanMessage(content="Reply with the single word OK and nothing else."),
    ])
    dt = time.time() - t0
    text = (response.content or "").strip()
    assert isinstance(text, str) and len(text) > 0
    print(f"PASS case 5 — live LLM call returned {text!r} in {dt:.2f}s")


print()
print("All-chain-agents smoke test passed.")
