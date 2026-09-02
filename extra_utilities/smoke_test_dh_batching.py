"""Smoke test — Database Handler batching, step 3a.

Covers the pure half of the batching build: candidate-run formation,
labelling and plan validation, plus the two schedule guarantees the DH
depends on (sub-row contiguity, and the repair applied on load).

Deliberately stdlib-only.  ``agents/database_handler/batch_tools.py``
imports ``langchain_core`` for its ``@tool`` decorators, which is not
installed in every worktree, so the helper functions are loaded from
source with that import stubbed.  Everything exercised here is pure
Python — no LLM, no network, no database.

Run:

    py extra_utilities/smoke_test_dh_batching.py

Exit code 0 = all pass.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Stub preamble — same convention as smoke_test_topology_fragments.py.
#
# ``agents/__init__.py`` eagerly imports every agent class, so importing
# anything under ``agents.`` drags in langchain.  Pre-seeding the package
# stubs lets the real submodule load without its parent's side effects,
# and stubbing the ONE langchain symbol batch_tools uses (the ``@tool``
# decorator) means the module's own logic is exercised for real rather
# than by a replica that could drift from it.
# ---------------------------------------------------------------------------

for _name, _rel in (
    ("agents", "agents"),
    ("agents.database_handler", "agents/database_handler"),
):
    _m = types.ModuleType(_name)
    _m.__path__ = [str(REPO / _rel)]
    sys.modules[_name] = _m

_lc = types.ModuleType("langchain_core")
_lc.__path__ = []
_lct = types.ModuleType("langchain_core.tools")
_lct.tool = lambda fn: fn          # the decorator is identity here
sys.modules["langchain_core"] = _lc
sys.modules["langchain_core.tools"] = _lct

from agents.database_handler import batch_tools as B   # noqa: E402
from workflow_settings import dh_schedule as S         # noqa: E402
from workflow_settings import settings as _settings    # noqa: E402

FAILS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{('  — ' + detail) if detail else ''}")
    if not ok:
        FAILS.append(label)


def row(rid, name, agent="planner", scope="session", parent=None, typ="Semantic"):
    return {
        "id": rid, "field": name, "name": name, "description": "d",
        "agent_key": agent, "from_agent": agent, "to_agents": [],
        "scope": scope, "type": typ, "parent_id": parent,
        "sub_index": None, "requires_dcii_enabled": False,
    }


def ids(groups):
    return [[r["id"] for r in g] for g in groups]


# ===========================================================================
print("\n-- candidate runs ---------------------------------------------------")

# A schedule shaped UNLIKE the shipped default on purpose: an agent that
# appears twice non-adjacently, a Quantitative row, an identifying block
# whose children belong to two different agents, and a trailing session row.
MIXED = [
    row("s1", "UII a", "user_input_inspector"),
    row("s2", "UII b", "user_input_inspector"),
    row("s3", "UII quant", "user_input_inspector", typ="Quantitative"),
    row("s4", "TC a", "tool_caller"),
    row("p1", "Which attempt", "dc_output_inspector", scope="attempt"),
    row("k1", "Describe it", "dc_output_inspector", scope="attempt", parent="p1"),
    row("k2", "What failed", "dc_output_inspector", scope="attempt", parent="p1"),
    row("k3", "Planner view", "planner", scope="attempt", parent="p1"),
    row("s5", "UII again", "user_input_inspector"),
]

runs = B.candidate_runs(MIXED)
check("no row is lost", sum(len(r) for r in runs) == len(MIXED))
check("consecutive same-agent rows form one run", ids(runs)[0] == ["s1", "s2", "s3"],
      str(ids(runs)))
check("a different agent starts a new run", ids(runs)[1] == ["s4"])
check("an identifying row is always alone", ids(runs)[2] == ["p1"])
check("same-agent children of one parent group together", ids(runs)[3] == ["k1", "k2"])
check("a child of another agent starts its own run", ids(runs)[4] == ["k3"])
check("the same agent re-appearing later is a SEPARATE run",
      ids(runs)[5] == ["s5"] and len(runs) == 6, str(ids(runs)))

# Two identifying rows side by side must not merge, even though they share
# agent, scope and parent.
TWO_ID = [
    row("pa", "Which A", "dc_output_inspector", scope="attempt"),
    row("ca", "A child", "dc_output_inspector", scope="attempt", parent="pa"),
    row("pb", "Which B", "dc_output_inspector", scope="attempt"),
    row("cb", "B child", "dc_output_inspector", scope="attempt", parent="pb"),
]
check("adjacent identifying rows never merge",
      ids(B.candidate_runs(TWO_ID)) == [["pa"], ["ca"], ["pb"], ["cb"]],
      str(ids(B.candidate_runs(TWO_ID))))

check("a row after an identifying row does not join it",
      ids(B.candidate_runs([
          row("p", "Which", "planner", scope="attempt"),
          row("s", "Session", "planner"),
      ])) == [["p"], ["s"]])
check("empty schedule is handled", B.candidate_runs([]) == [])

# Scope is never crossed, even for one agent with rows adjacent.
check("session and attempt rows for one agent never share a run",
      ids(B.candidate_runs([
          row("a", "A", "planner"),
          row("b", "B", "planner", scope="attempt", parent="ghost"),
      ])) == [["a"], ["b"]])

# ===========================================================================
print("\n-- labels -----------------------------------------------------------")

check("plan labels are R1..Rn",
      list(B.label_rows(MIXED, "plan")) == [f"R{i}" for i in range(1, 10)])
check("batch labels are A, B, C", list(B.label_rows(MIXED[:3])) == ["A", "B", "C"])
check("batch labels pass Z correctly",
      list(B.label_rows([row(str(i), str(i)) for i in range(28)]))[25:28]
      == ["Z", "AA", "AB"])
check("labels map to the right rows",
      B.label_rows(MIXED, "plan")["R5"]["id"] == "p1")
check("labels are unique", len(set(B.label_rows(MIXED, "plan"))) == len(MIXED))

# ===========================================================================
print("\n-- plan validation --------------------------------------------------")

labels = B.label_rows(MIXED, "plan")

groups, problems = B.validate_plan(
    [{"labels": ["R1", "R2", "R3"]}, {"labels": ["R4"]}, {"labels": ["R5"]},
     {"labels": ["R6", "R7"]}, {"labels": ["R8"]}, {"labels": ["R9"]}],
    runs, labels,
)
check("a legal plan is accepted verbatim", not problems, str(problems))
check("a legal plan yields the proposed groups",
      ids(groups) == [["s1", "s2", "s3"], ["s4"], ["p1"], ["k1", "k2"], ["k3"], ["s5"]],
      str(ids(groups)))

# Cross-run group: R3 (UII session) with R4 (Tool Caller) — must be split.
groups, problems = B.validate_plan(
    [{"labels": ["R1", "R2"]}, {"labels": ["R3", "R4"]}, {"labels": ["R5"]},
     {"labels": ["R6", "R7", "R8"]}, {"labels": ["R9"]}],
    runs, labels,
)
check("a cross-run group is reported",
      any("cannot share one call" in p for p in problems), str(problems))
check("a cross-run group is SPLIT, not dropped",
      ["s3"] in ids(groups) and ["s4"] in ids(groups), str(ids(groups)))
check("splitting loses no rows",
      sorted(r for g in ids(groups) for r in g) == sorted(r["id"] for r in MIXED))

# Omitted rows become singletons.
groups, problems = B.validate_plan([{"labels": ["R1", "R2"]}], runs, labels)
check("omitted rows are reported", any("left out of the plan" in p for p in problems))
check("omitted rows become singletons and nothing is lost",
      sorted(r for g in ids(groups) for r in g) == sorted(r["id"] for r in MIXED),
      str(ids(groups)))

# Duplicate + unknown labels.
groups, problems = B.validate_plan(
    [{"labels": ["R1", "R1"]}, {"labels": ["R99"]}], runs, labels,
)
check("a repeated label is reported", any("more than one batch" in p for p in problems))
check("an unknown label is reported", any("not a label" in p for p in problems))
check("a row is never duplicated across groups",
      len([r for g in ids(groups) for r in g]) == len(MIXED), str(ids(groups)))

# Shapes the model might emit.
groups, _ = B.validate_plan([["R1", "R2"]], runs, labels)
check("a bare list of labels is tolerated", ["s1", "s2"] in ids(groups), str(ids(groups)))
_, problems = B.validate_plan(["nonsense"], runs, labels)
check("a malformed batch is reported", any("not an object" in p for p in problems))
groups, _ = B.validate_plan([], runs, labels)
check("an empty plan degrades to one row per group",
      ids(groups) == [[r["id"]] for r in MIXED], str(ids(groups)))

# Groups come back in schedule order however they were listed.
groups, _ = B.validate_plan(
    [{"labels": ["R9"]}, {"labels": ["R5"]}, {"labels": ["R1", "R2", "R3"]},
     {"labels": ["R4"]}, {"labels": ["R6", "R7"]}, {"labels": ["R8"]}],
    runs, labels,
)
check("groups are returned in schedule order",
      ids(groups)[0] == ["s1", "s2", "s3"] and ids(groups)[-1] == ["s5"],
      str(ids(groups)))

check("the no-batching fallback covers every row exactly once",
      ids(B.no_batching_plan(runs)) == [[r["id"]] for r in MIXED])

# ===========================================================================
print("\n-- batch result: coverage + mapping ---------------------------------")

OPEN = {"A", "B", "C"}


def result(saves=(), followups=(), skips=()):
    return B.read_batch_result(
        {"saves": list(saves), "followups": list(followups), "skips": list(skips)},
        set(OPEN),
    )


s, f, k, p = result(
    saves=[{"label": "A", "question": "q", "answer": "a"},
           {"label": "B", "question": "q", "answer": "a"}],
    skips=["C"],
)
check("a complete result validates", not p, str(p))
check("saves are keyed by label", set(s) == {"A", "B"} and s["A"][0]["answer"] == "a")
check("skips are collected", k == {"C"})

s, f, k, p = result(
    saves=[{"label": "A", "question": "q1", "answer": "a1"},
           {"label": "A", "question": "q2", "answer": "a2"}],
    followups=[{"label": "B", "question": "more?"}], skips=["C"],
)
check("a label may repeat in saves (multi-answer split)", len(s["A"]) == 2)
check("followups are captured", f == {"B": "more?"})
check("a repeated save label is not a problem", not p, str(p))

# The two failure modes the whole design exists to catch.
_s, _f, _k, p = result(saves=[{"label": "A", "question": "q", "answer": "a"}])
check("a FORGOTTEN label is reported by name",
      any("not covered at all" in x and "B" in x and "C" in x for x in p), str(p))

_s, _f, _k, p = result(
    saves=[{"label": "A", "question": "q", "answer": "a"},
           {"label": "Z", "question": "q", "answer": "a"}],
    followups=[{"label": "B", "question": "?"}], skips=["C"],
)
check("an INVENTED label is reported and dropped",
      any("'Z'" in x or '"Z"' in x for x in p) and "Z" not in _s, str(p))

_s, _f, _k, p = result(
    saves=[{"label": "A", "question": "q", "answer": "a"}],
    followups=[{"label": "A", "question": "?"}, {"label": "B", "question": "?"}],
    skips=["C"],
)
check("a label in two lists is reported",
      any("pick one" in x for x in p), str(p))

_s, _f, _k, p = result(
    saves=[{"label": "A", "question": "", "answer": "a"}],
    followups=[{"label": "B", "question": "?"}], skips=["C"],
)
check("a save missing its question is rejected, not stored",
      "A" not in _s and any("missing its question" in x for x in p), str(p))

s, _f, _k, _p = result(
    saves=[{"label": "A", "question": "q", "answer": "a", "attempt": "002"},
           {"label": "B", "question": "q", "answer": "a"}],
    skips=["C"],
)
check("an attempt tag rides on the entry that carries it",
      s["A"][0]["attempt"] == "002" and s["B"][0]["attempt"] is None)

s, _f, k, _p = result(
    saves=[{"label": "A", "question": "q", "answer": "a"}],
    followups=[{"label": "B", "question": "?"}],
    skips=[{"label": "C"}],
)
check("a skip given as an object is tolerated", k == {"C"})

_s, _f, _k, p = B.read_batch_result({}, set(OPEN))
check("an empty result reports every label as uncovered",
      any("not covered at all" in x for x in p), str(p))

# ===========================================================================
print("\n-- the real shipped schedule ----------------------------------------")

live = S.read_for_dh()
live_runs = B.candidate_runs(live)
check("the shipped schedule loads", len(live) == 36, f"{len(live)} rows")
check("runs cover it exactly", sum(len(r) for r in live_runs) == len(live))
check("every identifying row is alone",
      all(len(r) == 1 for r in live_runs if B.is_identifying(r[0])))
check("no run mixes agents", all(len({e["agent_key"] for e in r}) == 1 for r in live_runs))
check("no run mixes scopes", all(len({e["scope"] for e in r}) == 1 for r in live_runs))
check("no run mixes parents",
      all(len({e["parent_id"] for e in r}) == 1 for r in live_runs))

live_labels = B.label_rows(live, "plan")
full = [{"labels": [lab for lab, r in live_labels.items() if r in run]}
        for run in live_runs]
groups, problems = B.validate_plan(full, live_runs, live_labels)
check("batching every run whole is a legal plan", not problems, str(problems))
saved = sum(2 * (len(g) - 1) for g in groups)
check("that plan would save calls", saved > 0,
      f"{len(live)} rows -> {len(groups)} batches, {saved} fewer LLM calls per pass")

# ===========================================================================
print("\n-- the batch loop, end to end ---------------------------------------")
#
# _run_batch is a method on DatabaseHandler, which cannot be imported here
# (it pulls in the whole agent stack).  It is loaded from source and run
# against a stand-in whose forced-tool turns are SCRIPTED, so the loop's
# control flow — rounds, coverage retry, cap exhaustion, resolution order
# — is exercised for real.
import ast          # noqa: E402
import textwrap     # noqa: E402

_DH_SRC = (REPO / "agents/database_handler/database_handler.py").read_text(
    encoding="utf-8")
_tree = ast.parse(_DH_SRC)
_methods = {
    n.name: ast.get_source_segment(_DH_SRC, n)
    for cls in _tree.body if isinstance(cls, ast.ClassDef)
    for n in cls.body if isinstance(n, ast.FunctionDef)
}

_ns = {
    "bt": B,
    "logger": types.SimpleNamespace(info=lambda *a, **k: None,
                                    warning=lambda *a, **k: None),
    "MAX_DH_TURNS_PER_FIELD": 3,
    "_without_image_blocks": lambda m: (list(m), 0),
    "HumanMessage": lambda content: types.SimpleNamespace(content=content),
    "count_tokens": lambda s: len(str(s).split()),
}
for _name in ("_run_batch", "_batch_decision_instruction"):
    exec(compile(textwrap.dedent(_methods[_name]), _name, "exec"), _ns)


class ScriptedDH:
    """A DatabaseHandler stand-in whose tool turns come from a script."""

    _run_batch = _ns["_run_batch"]
    _batch_decision_instruction = _ns["_batch_decision_instruction"]

    def __init__(self, questions, script):
        self.max_response_tokens = 700
        self.messages = []
        self._questions = questions
        self._script = list(script)
        self.asked_rounds = []
        self.tool_calls = 0

    # --- stubs for the collaborators _run_batch reaches for ---
    def _batch_questions(self, agent_key, labelled):
        return {lab: self._questions.get(lab, "q?") for lab in labelled}

    def _ask_agent(self, **kw):
        self.asked_rounds.append(kw["question"])
        return "the agent's reply"

    def _shorten_over_cap(self, agent_key, labelled, saves):
        return saves

    @staticmethod
    def _clean_saves(labelled, saves):      # exercised separately below
        return saves

    def _force_tool_args(self, tool_obj, name, instruction, label, retries=2):
        self.tool_calls += 1
        return self._script.pop(0) if self._script else None


ROWS = [row("a", "A field"), row("b", "B field"), row("c", "C field")]


def drive(script, questions=None):
    dh = ScriptedDH(questions or {}, script)
    got = []
    dh._run_batch(
        rows=ROWS, agent_key="planner", agent_system_prompt="",
        agent_provider="openai", agent_base_llm=None, agent_messages=[],
        on_resolved=lambda r, res: got.append((r["id"], res)),
    )
    return dh, got


# 1 — everything settled in one round.
dh, got = drive([{
    "saves": [{"label": "A", "question": "q", "answer": "a1"},
              {"label": "B", "question": "q", "answer": "a2"}],
    "followups": [], "skips": ["C"],
}])
check("one round settles the whole batch", len(dh.asked_rounds) == 1,
      f"{len(dh.asked_rounds)} agent call(s)")
check("saves and skips both resolve",
      [g[0] for g in got] == ["a", "b", "c"], str([g[0] for g in got]))
check("a skip resolves as None", got[2][1] is None)
check("a save resolves with its entries", got[0][1][0]["answer"] == "a1")
check("all three questions go out in ONE message",
      all(x in dh.asked_rounds[0] for x in ("[A]", "[B]", "[C]")))

# 2 — a follow-up round asks ONLY the open row.
dh, got = drive([
    {"saves": [{"label": "A", "question": "q", "answer": "a"}],
     "followups": [{"label": "B", "question": "and B?"}], "skips": ["C"]},
    {"saves": [{"label": "B", "question": "q", "answer": "b"}],
     "followups": [], "skips": []},
])
check("a follow-up round runs", len(dh.asked_rounds) == 2)
check("the follow-up asks only the open row",
      "and B?" in dh.asked_rounds[1] and "[A]" not in dh.asked_rounds[1],
      dh.asked_rounds[1][:60])
check("rows settled in round 1 are not re-resolved",
      [g[0] for g in got] == ["a", "c", "b"], str([g[0] for g in got]))

# 3 — coverage failure: retry, then per-row fallback for what is still open.
dh, got = drive([
    {"saves": [{"label": "A", "question": "q", "answer": "a"}],
     "followups": [], "skips": []},                       # B and C uncovered
    {"saves": [{"label": "A", "question": "q", "answer": "a"},
               {"label": "B", "question": "q", "answer": "b"}],
     "followups": [], "skips": []},                       # retry: C still out
])
check("a coverage failure triggers exactly one retry", dh.tool_calls == 2,
      f"{dh.tool_calls} tool call(s)")
check("uncovered rows fall through as 'unsettled'",
      ("c", "unsettled") in got, str(got))
check("rows the retry did cover are still saved",
      [g[0] for g in got if g[1] != "unsettled"] == ["a", "b"], str(got))

# 4 — cap exhaustion: a DH that only ever follows up.
loop = {"saves": [], "followups": [
    {"label": lab, "question": "again?"} for lab in ("A", "B", "C")],
    "skips": []}
dh, got = drive([loop, loop, loop, {
    "saves": [{"label": "A", "question": "q", "answer": "a"}],
    "followups": [], "skips": ["B"],
}])
check("the round cap stops the agent calls at MAX", len(dh.asked_rounds) == 3,
      f"{len(dh.asked_rounds)} agent call(s)")
check("the forced final round costs ONE extra DH call, no agent call",
      dh.tool_calls == 4, f"{dh.tool_calls} tool call(s)")
check("the final round's saves and skips are honoured",
      dict(got)["a"][0]["answer"] == "a" and dict(got)["b"] is None, str(got))
check("a row never settled is skipped, not left without an artefact",
      dict(got)["c"] is None, str(got))
check("cap exhaustion does NOT fall back to per-row conversations",
      not any(v == "unsettled" for _k, v in got), str(got))

# 5 — the tool call failing outright.
dh, got = drive([None])
check("a failed decision drops every row to the per-row fallback",
      [g for g in got] == [("a", "unsettled"), ("b", "unsettled"),
                           ("c", "unsettled")], str(got))

# ===========================================================================
print("\n-- the cleanup backstop routes by row type --------------------------")
# The DH's prompt tells it to strip paths / routing-JSON / literal \n
# itself; in practice models echo the wrapper they saw, so the backstop
# stays.  It must apply to Semantic rows ONLY — cleaning a Quantitative
# body could alter a number or a unit.
_clean_ns = {"_clean_semantic_body": lambda s: f"<cleaned:{s}>"}
exec(compile(textwrap.dedent(_methods["_clean_saves"]).replace(
    "@staticmethod\n", "", 1), "_clean_saves", "exec"), _clean_ns)
_clean_saves = _clean_ns["_clean_saves"]

_labelled = {"S": row("s", "Semantic row"),
             "Q": row("q", "Quant row", typ="Quantitative")}
_out = _clean_saves(_labelled, {
    "S": [{"question": "q", "answer": "a", "attempt": None}],
    "Q": [{"question": "q", "answer": "17 mm", "attempt": None}],
})
check("a Semantic entry is cleaned",
      _out["S"][0]["answer"] == "<cleaned:a>", str(_out["S"]))
check("a Quantitative entry is left EXACTLY as saved",
      _out["Q"][0]["answer"] == "17 mm", str(_out["Q"]))
check("cleaning preserves the attempt tag",
      _out["S"][0]["attempt"] is None and "attempt" in _out["S"][0])

_out2 = _clean_saves(_labelled, {
    "S": [{"question": "q", "answer": "", "attempt": "002"}]})
check("an empty field falls back to the original rather than vanishing",
      _out2["S"][0]["answer"] == "" or _out2["S"][0]["answer"].startswith("<"),
      str(_out2["S"]))
check("cleaning preserves a set attempt tag", _out2["S"][0]["attempt"] == "002")

# ===========================================================================
print("\n-- schedule guarantees the batcher relies on ------------------------")

def srow(rid, name, agent="planner", scope="session", parent=None):
    return {"id": rid, "name": name, "description": "d", "from_agent": agent,
            "to_agents": [], "scope": scope, "type": "Semantic",
            "parent_id": parent, "sub_index": None,
            "requires_dcii_enabled": False}


clean = [srow("p", "P", scope="attempt"),
         srow("c1", "C1", scope="attempt", parent="p"),
         srow("c2", "C2", scope="attempt", parent="p"),
         srow("s", "S")]
wedged = [clean[0], clean[3], clean[1], clean[2]]

check("a contiguous block validates", S._schedule_problem(clean) is None)
check("a wedged row is rejected", S._schedule_problem(wedged) is not None)
repaired, shifted = S._reorder_children(wedged)
check("the load-time repair restores contiguity",
      S._schedule_problem(repaired) is None and shifted > 0, f"shifted={shifted}")
check("the repair keeps every row",
      sorted(r["id"] for r in repaired) == sorted(r["id"] for r in wedged))
check("the repair is a no-op when clean", S._reorder_children(clean)[1] == 0)
check("the shipped schedule is contract-clean",
      S._schedule_problem(S.read_state()["questions"]) is None)

# ===========================================================================
print("\n-- F19d: every schedule row names an agent its hub BUILDS ----------")

# The DH resolves a row's ``from_agent`` against the hub's ``_agents_by_key``.
# A row naming an agent that hub does not build does not merely warn: the
# unknown-agent branch calls _phase_3c_persist_chunk(..., is_error=True),
# which writes an ``ERROR:`` row into the R2 mirror AND the Postgres
# ``chunks`` table, where it comes back at retrieval time.
#
# The registry reader is SHARED with topology_prompt_snapshot.py (F47), so
# there is one derivation of "which agents does this hub build", taken from
# the hub's own literal.  extra_utilities/hub_registry.py records why
# neither AGENTS_BY_TOPOLOGY table answers this question.
sys.path.insert(0, str(REPO / "extra_utilities"))
from hub_registry import registry_keys_from_source          # noqa: E402

_HUBS = {
    7: ("agents/orchestrator/orchestrator.py", 36, "dh_schedule.json"),
    5: ("agents/planner5/planner5.py",         33, "dh_schedule_5agents.json"),
}

_saved_topology = getattr(_settings, "SYSTEM_TOPOLOGY", 7)
try:
    for _topo, (_hub_rel, _want_rows, _want_file) in _HUBS.items():
        _settings.SYSTEM_TOPOLOGY = _topo
        _built = registry_keys_from_source(REPO / _hub_rel)
        check(f"topology {_topo}: the hub registry parses",
              bool(_built) and not any(str(k).startswith("<unparsed")
                                       for k in _built),
              str(sorted(_built)))
        check(f"topology {_topo}: reads {_want_file}",
              S.schedule_path().name == _want_file, S.schedule_path().name)
        _rows = S.read_state()["questions"]
        check(f"topology {_topo}: {_want_rows} rows", len(_rows) == _want_rows,
              f"got {len(_rows)}")
        _orphans = sorted({r["from_agent"] for r in _rows} - _built)
        check(f"topology {_topo}: every from_agent is an agent the hub builds",
              not _orphans,
              f"rows naming an agent this hub does not build: {_orphans}")
finally:
    _settings.SYSTEM_TOPOLOGY = _saved_topology

# ===========================================================================
print()
if FAILS:
    print(f"{len(FAILS)} FAILURE(S): {FAILS}")
    sys.exit(1)
print("ALL PASS")
sys.exit(0)
