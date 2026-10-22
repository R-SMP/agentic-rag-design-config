"""The agent role map (agents/shared/agent_roles.py) and the three things it drives.

1. ROSTER matches what each hub really builds (read from the hub source),
   and DISPLAY matches routing_tools.AGENT_DISPLAY.
2. Retrieval: who may read answers addressed to whom, per topology -- both
   directions, the hub taking the Orchestrator's role, and the topology-5
   RAG_DCIC_READS_DCII toggle.
3. The question table maps DOWNWARD only, and a skipped row takes its
   sub-rows with it.
4. The <agent_roles> legend: absent when every named agent exists here,
   otherwise exactly ONE line, right after <search_meta>, listing only the
   agents actually found -- however many sessions name them.

Offline: no database, no network, no LLM.

    py -3.13 extra_utilities/tests/smoke_test_agent_roles.py
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "extra_utilities" / "prompt_pdf"))
sys.path.insert(0, str(REPO / "extra_utilities" / "scripts"))
sys.modules["simplejson"] = None
sys.modules["chardet"] = None
import bootstrap  # noqa: E402
bootstrap.install()

import hub_registry  # noqa: E402
from agents.shared import agent_roles as R  # noqa: E402
from workflow_settings import settings as S  # noqa: E402

problems: list[str] = []


def check(cond, msg):
    if not cond:
        problems.append(msg)


# --- 1. roster + display names --------------------------------------------
HUB_FILE = {7: "agents/orchestrator/orchestrator.py",
            5: "agents/planner5/planner5.py",
            3: "agents/planner3/planner3.py"}
for t, f in HUB_FILE.items():
    built = hub_registry.registry_keys_from_source(REPO / f)
    check(built == set(R.ROSTER[t]),
          f"ROSTER[{t}] {sorted(R.ROSTER[t])} != hub {f} {sorted(built)}")

from agents.shared.routing_tools import AGENT_DISPLAY  # noqa: E402
for k, name in R.DISPLAY.items():
    check(AGENT_DISPLAY.get(k) == name,
          f"DISPLAY[{k}]={name!r} but routing_tools.AGENT_DISPLAY says "
          f"{AGENT_DISPLAY.get(k)!r}")

# --- 2. retrieval -----------------------------------------------------------
S.RAG_DCIC_READS_DCII = True
READS = {
    (3, "design_engineer"):      {"design_engineer", "dc_input_creator", "dc_input_inspector", "tool_caller"},
    (3, "requirements_analyst"): {"requirements_analyst", "user_input_inspector", "dc_output_inspector"},
    (3, "planner"):              {"planner", "orchestrator"},
    (5, "planner"):              {"planner", "orchestrator"},
    (5, "dc_input_creator"):     {"dc_input_creator", "dc_input_inspector", "design_engineer"},
    (5, "tool_caller"):          {"tool_caller", "design_engineer"},
    (7, "dc_input_creator"):     {"dc_input_creator", "design_engineer"},
    (7, "dc_input_inspector"):   {"dc_input_inspector", "design_engineer"},
    (7, "user_input_inspector"): {"user_input_inspector", "requirements_analyst"},
    (7, "dc_output_inspector"):  {"dc_output_inspector", "requirements_analyst"},
    (7, "orchestrator"):         {"orchestrator"},          # no reverse hub mapping
    (7, "planner"):              {"planner"},
    (7, "receptionist"):         {"receptionist"},
}
for (t, a), want in READS.items():
    got = set(R.readable_keys(a, t))
    check(got == want, f"t{t} {a} reads {sorted(got)}, expected {sorted(want)}")

S.RAG_DCIC_READS_DCII = False
check(set(R.readable_keys("dc_input_creator", 5)) == {"dc_input_creator", "design_engineer"},
      "t5 toggle OFF: DCIC must stop reading DCII answers")
check("dc_input_inspector" in R.readable_keys("design_engineer", 3),
      "toggle OFF must not touch topology 3")
S.RAG_DCIC_READS_DCII = True

# --- 3. question table: downward only --------------------------------------
QA = {
    (3, "dc_output_inspector"): "requirements_analyst",
    (3, "user_input_inspector"): "requirements_analyst",
    (3, "tool_caller"): "design_engineer",
    (3, "orchestrator"): "planner",
    (5, "orchestrator"): "planner",
    (5, "dc_input_inspector"): "dc_input_creator",
    (7, "design_engineer"): None,
    (7, "requirements_analyst"): None,
    (5, "design_engineer"): None,
    (7, "dc_input_inspector"): "dc_input_inspector",
}
for (t, f), want in QA.items():
    check(R.question_answerer(f, t) == want,
          f"t{t} question from {f} -> {R.question_answerer(f, t)}, expected {want}")
S.RAG_DCIC_READS_DCII = False
check(R.question_answerer("dc_input_inspector", 5) is None,
      "t5 toggle OFF: a DCII question row must be skipped")
S.RAG_DCIC_READS_DCII = True

from workflow_settings import dh_schedule  # noqa: E402


def row(i, frm, parent=None, scope="session"):
    return {"id": f"r{i}", "name": f"Row {i}", "description": "d", "from_agent": frm,
            "to_agents": [frm], "scope": scope, "type": "Semantic",
            "parent_id": parent, "sub_index": 1 if parent else None}


rows = [row(1, "dc_output_inspector"), row(2, "design_engineer"),
        row(3, "requirements_analyst", scope="attempt"),
        row(4, "planner", parent="r3", scope="attempt"),
        row(5, "orchestrator")]
real_read_state = dh_schedule.read_state
dh_schedule.read_state = lambda: {"questions": [dict(r) for r in rows]}
try:
    S.TEAM_SIZE = 3
    got3 = [(e["id"], e["agent_key"]) for e in dh_schedule.read_for_dh()]
    check(got3 == [("r1", "requirements_analyst"), ("r2", "design_engineer"),
                   ("r3", "requirements_analyst"), ("r4", "planner"),
                   ("r5", "planner")], f"read_for_dh under t3: {got3}")
    S.TEAM_SIZE = 7
    got7 = [(e["id"], e["agent_key"]) for e in dh_schedule.read_for_dh()]
    check(got7 == [("r1", "dc_output_inspector"), ("r5", "orchestrator")],
          f"read_for_dh under t7 (DE/RA rows and the RA row's child skipped): {got7}")
    check(all(e["to_agents"] == [r["from_agent"]] for e, r in
              zip(dh_schedule.read_for_dh(), [rows[0], rows[4]])),
          "to_agents must be stored exactly as written")
finally:
    dh_schedule.read_state = real_read_state
    S.TEAM_SIZE = 7

# --- 4. the legend, in a real assembled response ----------------------------
from tools.database_search import database_search as D  # noqa: E402


def chunk(cid, sid, frm, field, body):
    return D.ExpandedChunk(chunk_id=cid, session_id=sid, attempt_id=None,
                           attempt_label=None, agent_from=frm, field=field,
                           field_type="Semantic", question="q", body=body,
                           item_index=None, embedding_input=None, dist=None)


def respond(chunks_by_sid, topo):
    S.TEAM_SIZE = topo
    anchors = [D.AnchorHit(session_id=s, attempt_id=None, attempt_label=None,
                           dist=0.2, best_chunk_id=c[0].chunk_id)
               for s, c in chunks_by_sid.items()]
    meta = D.SearchMeta(n_requested=5, n_returned=len(anchors), attempt_specific=False,
                        metafilters_repr="{}", embedding_model="m",
                        skipped_due_to_model_mismatch=0)
    return D._build_response_full(meta=meta, anchors=anchors,
                                  chunks_by_anchor=chunks_by_sid, attempt_specific=False,
                                  metafilters_applied=False, omitted=0, token_cap=99999,
                                  available_attempts_by_session={})


seven = {
    "S1": [chunk(1, "S1", "dc_input_inspector", "Problem - DCII", "rejected the set")],
    "S2": [chunk(2, "S2", "user_input_inspector", "Design intent", "the Tool Caller rendered")],
    "S3": [chunk(3, "S3", "dc_input_inspector", "Rejection of inputs - DCII", "again")],
}
r3 = respond(seven, 3)
lines = r3.splitlines()
check(lines[0].startswith("<search_meta") and lines[1].startswith("<agent_roles>"),
      "t3: the legend must be the line right after <search_meta>")
check(r3.count("<agent_roles>") == 1, "t3: exactly one legend for three sessions")
check("DC Input Inspector (DCII)" in r3 and "User Input Inspector (UII)" in r3
      and "Tool Caller" in lines[1] and "Orchestrator" not in lines[1],
      f"t3 legend lists exactly the agents found: {lines[1]}")
check('agent="DC Input Inspector"' in r3, "authors are shown as display names")

r7 = respond(seven, 7)
check("<agent_roles>" not in r7, "t7: no legend when every named agent exists here")

three = {"S4": [chunk(4, "S4", "design_engineer", "Valid solution", "ok")],
         "S5": [chunk(5, "S5", "User", "Positive User Comments", "nice")]}
r5 = respond(three, 5)
check(r5.count("<agent_roles>") == 1 and "Design Engineer → DC Input Creator and Tool Caller" in r5,
      f"t5 reverse legend: {r5.splitlines()[1]}")
check('agent="User"' in r5, "User stays User")
S.TEAM_SIZE = 7

print("problems:", "none" if not problems else "")
for p in problems:
    print("  -", p)
sys.exit(1 if problems else 0)
