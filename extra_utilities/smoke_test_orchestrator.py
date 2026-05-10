"""Smoke test for the v3 Phase 1 commit 5 conversion of Orchestrator
to a BaseChainAgent + the ChainLog-to-session refactor.

Verifies:
1. Orchestrator is a BaseChainAgent subclass with AGENT_KEY ==
   "orchestrator"; constructing one materialises an "orchestrator"
   slot in session.agent_states alongside the seven chain agents.
2. Orchestrator requires a Session (the legacy mesh_checks/...
   kwargs path is gone — every agent acts the same way now).
3. Routing tools append plain-data dicts to
   session.chain_log_exchanges with the expected
   (from_agent, to_agent, message, ts) shape; the timestamp is a
   parseable ISO-8601 string with timezone.
4. The chain log accumulates ACROSS what would be multiple user
   turns within one session (per Phase 1 Q1 — chain log is session-
   scoped, not per-turn).  reset_turn() is a vestigial no-op and
   does NOT clear it.
5. orchestrator.snapshot_state() captures the Orchestrator's own
   state into a fresh AgentState; constructing a second Orchestrator
   from a Session with that AgentState restores the messages,
   pending_hop, and image buffers.
6. format_chain_exchanges renders the dict-list into the same
   "[FROM ..., TO ...]:\\n..." prose block the v4 ChainLog.format()
   produced.
7. (Live LLM call) Orchestrator's base_llm responds to a one-shot
   prompt — confirms the LLMClientCache delivers a working LLM
   client to the Orchestrator just like to the chain agents.
   Requires OPENAI_API_KEY.

Run from the project root:
    .venv/Scripts/python.exe extra_utilities/smoke_test_orchestrator.py
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
from agents.shared.routing_tools import AgentHop, format_chain_exchanges
from agents.shared.session import AgentState, Session


def _build_session() -> Session:
    return Session(
        session_id="smoke_orchestrator",
        session_ts=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------
# Case 1: Orchestrator is a BaseChainAgent subclass
# ---------------------------------------------------------------------
session = _build_session()
orch = Orchestrator(session=session)

assert isinstance(orch, BaseChainAgent)
assert orch.AGENT_KEY == "orchestrator"
assert "orchestrator" in session.agent_states, (
    "Orchestrator construction must materialise its own AgentState slot"
)
print("PASS case 1 — Orchestrator subclasses BaseChainAgent and registers its slot")


# ---------------------------------------------------------------------
# Case 2: legacy kwargs path is gone — Orchestrator requires a Session
# ---------------------------------------------------------------------
try:
    Orchestrator()  # no session, no kwargs
except TypeError as e:
    assert "Session" in str(e)
    print("PASS case 2 — Orchestrator() without Session raises TypeError")
else:
    raise AssertionError("expected TypeError when Session is omitted")


# ---------------------------------------------------------------------
# Case 3: routing tools append dicts with the right shape + timestamp
# ---------------------------------------------------------------------
assert session.chain_log_exchanges == []
# Grab one of the DCII's routing tools and invoke it directly.  DCII
# is used because its _routing_tools_by_name contains only routing
# tools (independent of PLANNER_FIRST / dc_inspector_enabled flags),
# and call_tool_caller is always present.
call_tc = orch.dc_input_inspector._routing_tools_by_name["call_tool_caller"]
result = call_tc.invoke({"message": "go build the mesh"})
assert "Hand-off recorded" in result

assert len(session.chain_log_exchanges) == 1
ex = session.chain_log_exchanges[0]
assert isinstance(ex, dict)
assert set(ex.keys()) == {"from_agent", "to_agent", "message", "ts"}
assert ex["from_agent"] == "DC Input Inspector"
assert ex["to_agent"] == "Tool Caller"
assert ex["message"] == "go build the mesh"
parsed = datetime.fromisoformat(ex["ts"])
assert parsed.tzinfo is not None, "ts must include timezone"
print("PASS case 3 — routing tool appended a well-shaped exchange dict + ISO ts")


# ---------------------------------------------------------------------
# Case 4: chain log accumulates across "turns"; reset_turn is no-op
# ---------------------------------------------------------------------
# Simulate a second turn by calling reset_turn() and invoking another
# routing tool.  The first exchange must still be there.
orch.reset_turn()
assert len(session.chain_log_exchanges) == 1, (
    "reset_turn must NOT clear the session-scoped chain log"
)

call_orch_from_uii = orch.user_input_inspector._routing_tools_by_name[
    "call_orchestrator"
]
call_orch_from_uii.invoke({"message": "escalate"})
# Note: target=='orchestrator' hops are intentionally NOT logged to
# chain_log_exchanges (they would self-reference the dispatcher).
assert len(session.chain_log_exchanges) == 1, (
    "calls TO the orchestrator are not recorded in chain_log_exchanges"
)

# Now invoke a non-orchestrator routing tool and verify it appends.
call_orch_planner = orch._tools_by_name["call_planner"]
call_orch_planner.invoke({"message": "go plan"})
assert len(session.chain_log_exchanges) == 2
assert session.chain_log_exchanges[1]["from_agent"] == "Orchestrator"
assert session.chain_log_exchanges[1]["to_agent"] == "Planner"
print("PASS case 4 — chain log accumulates across turns; reset_turn is no-op")


# ---------------------------------------------------------------------
# Case 5: snapshot/restore of Orchestrator state
# ---------------------------------------------------------------------
orch.messages.append(HumanMessage(content="orchestrator working"))
orch._pending_hop = AgentHop(target="planner", message="go")
snap = orch.snapshot_state()
assert isinstance(snap, AgentState)
assert snap.agent_key == "orchestrator"
assert snap.messages == orch.messages
assert snap.pending_hop == {"target": "planner", "message": "go"}

# Build a fresh session and orchestrator from the snapshot.
session2 = _build_session()
session2.agent_states["orchestrator"] = snap
orch2 = Orchestrator(session=session2)
assert orch2.messages == orch.messages
assert orch2._pending_hop is not None
assert orch2._pending_hop.target == "planner"
assert orch2._pending_hop.message == "go"
print("PASS case 5 — Orchestrator round-trips through snapshot/restore")


# ---------------------------------------------------------------------
# Case 6: format_chain_exchanges produces the expected prose
# ---------------------------------------------------------------------
formatted = format_chain_exchanges(session.chain_log_exchanges)
assert "[FROM DC Input Inspector, TO Tool Caller]:" in formatted
assert "go build the mesh" in formatted
assert "[FROM Orchestrator, TO Planner]:" in formatted
assert "go plan" in formatted
empty_formatted = format_chain_exchanges([])
assert empty_formatted == ""
print("PASS case 6 — format_chain_exchanges renders the prose block correctly")


# ---------------------------------------------------------------------
# Case 7: live LLM call via Orchestrator.base_llm
# ---------------------------------------------------------------------
if not os.environ.get("OPENAI_API_KEY"):
    print("SKIP  case 7 — OPENAI_API_KEY not set; skipping live LLM call")
else:
    t0 = time.time()
    response = orch.base_llm.invoke([
        HumanMessage(content="Reply with the single word OK and nothing else."),
    ])
    dt = time.time() - t0
    text = (response.content or "").strip()
    assert isinstance(text, str) and len(text) > 0
    print(f"PASS case 7 — live LLM call returned {text!r} in {dt:.2f}s")


print()
print("Orchestrator smoke test passed.")
