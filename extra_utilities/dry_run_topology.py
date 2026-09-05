"""Drive ONE COMPLETE TURN per topology against a scripted fake LLM.

No network, no tokens, no API key that has to be real.  Everything else is
the PRODUCTION path: the real ``dispatch_turn``, the real Receptionist
``validate_input``, every agent's real run loop, the real routing tools and
the real hub dispatch loop.  Only ``invoke_with_retry`` is replaced.

Why this exists
---------------
The static suite checks TEXT and STRUCTURE — which files a prompt reads, which
tools a class binds, which edges a hub wires.  None of it runs a turn, and
every defect the two live 5-agent runs found was invisible to all of it
(``topology_shared_touchpoints.md`` §F):

* ``receptionist.validate_input`` decided "did it forward?" by comparing the
  hop target against the literal ``"orchestrator"``, so under another topology
  the user got a BLANK reply;
* ``dispatch_turn`` computed the Receptionist's chosen target and then threw
  it away, always starting the hub;
* a hub called ``self.tool_caller`` in ``reset()`` for an agent its topology
  never built — an ``AttributeError`` waiting for the end of a session.

All three are wiring, all three surface on the first hop, and all three are
free to catch here.

What the script asserts
-----------------------
``ROUTES`` is an ORDERED list of ``(agent label, tool to call)``.  The fake
asserts the agent being invoked is the one the script expects NEXT, then hands
back that tool call.  So it verifies the exact hop SEQUENCE, not merely that a
turn completed: route somewhere unexpected and the run fails on the spot,
naming who was invoked and who should have been.

It also proves each edge is really bound.  The fake returns a tool NAME; if
the agent does not hold that routing tool its run loop answers "unknown tool"
and never routes, so the turn stalls.

One subprocess per topology, for the same reason
``topology_prompt_snapshot.py`` uses one: ``prompts.py`` reads
``SYSTEM_TOPOLOGY`` fresh on every call but captures ``PLANNER_FIRST`` and
``DC_INSPECTOR_ENABLED`` at IMPORT, so two topologies in one process would
give the second the first's flags.

Usage
-----
    py -3.13 extra_utilities/dry_run_topology.py
    py -3.13 extra_utilities/dry_run_topology.py --topology 3
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_BOOTSTRAP_DIR = REPO / "extra_utilities" / "prompt_pdf"


# ---------------------------------------------------------------------------
# The scripted turns
#
# Each entry is (agent label as passed to invoke_with_retry, tool to invoke).
# A ``None`` tool means "answer with prose", which is how a turn ends: the
# Receptionist's prose IS the user-facing reply.
#
# The routes are chosen to touch every edge that carries a turn, not to be
# minimal.  Topology 3 in particular walks the refine loop
# (Design Engineer -> Requirements Analyst) that the Planner is NOT in, since
# that edge is the whole point of the topology.
# ---------------------------------------------------------------------------

ROUTES: dict[int, list[tuple[str, str | None]]] = {
    7: [
        ("Receptionist",  "call_orchestrator"),
        ("Orchestrator",  "call_user_input_inspector"),
        ("UII",           "call_planner"),
        ("Planner",       "call_orchestrator"),
        ("Orchestrator",  "call_receptionist"),
        ("Receptionist",  None),
    ],
    5: [
        ("Receptionist",  "call_planner"),
        ("Planner",       "call_user_input_inspector"),
        ("UII",           "call_planner"),
        ("Planner",       "call_dc_input_creator"),
        ("DCIC",          "call_tool_caller"),
        ("Tool Caller",   "call_dc_output_inspector"),
        ("DCOI",          "call_planner"),
        ("Planner",       "call_receptionist"),
        ("Receptionist",  None),
    ],
    3: [
        ("Receptionist",  "call_planner"),
        # New user material -> requirements, returned to the hub.
        ("Planner",       "call_requirements_analyst"),
        ("RA",            "call_planner"),
        # The hub starts the design cycle.
        ("Planner",       "call_design_engineer"),
        # The refine loop: the Planner is deliberately NOT in it.
        ("DEng",          "call_requirements_analyst"),
        ("RA",            "call_design_engineer"),
        ("DEng",          "call_requirements_analyst"),
        # ... and back to the hub to approve.
        ("RA",            "call_planner"),
        ("Planner",       "call_receptionist"),
        ("Receptionist",  None),
    ],
}


# ---------------------------------------------------------------------------
# Child process: one topology, one turn
# ---------------------------------------------------------------------------

_CHILD = r'''
import json, sys, tempfile, shutil
from pathlib import Path

sys.modules["simplejson"] = None
sys.modules["chardet"] = None
sys.path.insert(0, r"{bootstrap}")
import bootstrap
bootstrap.install()

TOPO = int(sys.argv[1])
SCRIPT = json.loads(sys.argv[2])

from workflow_settings import settings as S
S.SYSTEM_TOPOLOGY = TOPO
# Determinism: the primer injects an IMAGE at invoke time, and RAG would bind
# three more tools.  Neither is what this harness is testing.
S.DC_PARAMS_PRIMER_ENABLED = False
S.RAG_ENABLED = False

from langchain_core.messages import AIMessage

seen = []          # (label, tool) actually observed, in order
problems = []
step = {{"i": 0}}


def fake_invoke(llm, messages, agent_name, **kw):
    i = step["i"]
    if i >= len(SCRIPT):
        problems.append("script exhausted but %r was invoked again" % agent_name)
        return AIMessage(content="(script exhausted)")
    want_label, want_tool = SCRIPT[i]
    if agent_name != want_label:
        problems.append(
            "step %d: %r was invoked, expected %r" % (i, agent_name, want_label))
        # Keep going with what the script says so the turn still terminates.
    step["i"] = i + 1
    seen.append([agent_name, want_tool])
    if want_tool is None:
        return AIMessage(content="Dry run: composed reply for the user.")
    return AIMessage(
        content="",
        tool_calls=[{{"name": want_tool,
                     "args": {{"message": "dry-run hand-off %d" % i}},
                     "id": "dry_%d" % i}}],
    )


# Every agent binds invoke_with_retry BY NAME at import, so patching the source
# module reaches nobody.  Patch each agent module that already holds one.
from agents.hub import build_hub
from agents.shared.session import Session
from agents import dispatch as dispatch_mod

hub_session_dir = Path(tempfile.mkdtemp(prefix="dryrun_%d_" % TOPO))
try:
    from datetime import datetime, timezone
    sess = Session(session_id="dry_run_%d" % TOPO,
                   session_ts=datetime.now(timezone.utc))
    hub = build_hub(sess)

    patched = []
    for name, mod in list(sys.modules.items()):
        if name.startswith("agents") and hasattr(mod, "invoke_with_retry"):
            mod.invoke_with_retry = fake_invoke
            patched.append(name)

    inputs_dir = hub_session_dir / "inputs"
    attempts_dir = hub_session_dir / "attempts"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    attempts_dir.mkdir(parents=True, exist_ok=True)

    result = dispatch_mod.dispatch_turn(
        sess, "design me a propeller that matches this sketch",
        inputs_dir=inputs_dir, attempts_dir=attempts_dir, hub=hub,
    )
    payload = {{
        "topology": TOPO,
        "patched_modules": len(patched),
        "hub": type(hub).__name__,
        "forwarded": bool(result.forwarded),
        "reply": (result.reply_text or "")[:200],
        "seen": seen,
        "problems": problems,
        "steps_consumed": step["i"],
    }}
except Exception as exc:
    import traceback
    payload = {{"topology": TOPO, "fatal": "%s: %s" % (type(exc).__name__, exc),
               "trace": traceback.format_exc()[-1500:],
               "seen": seen, "problems": problems}}
finally:
    shutil.rmtree(hub_session_dir, ignore_errors=True)

sys.stdout.write("@@JSON@@" + json.dumps(payload))
'''


def _run_child(topology: int) -> dict:
    script = json.dumps(ROUTES[topology])
    code = _CHILD.format(bootstrap=str(_BOOTSTRAP_DIR))
    proc = subprocess.run(
        [sys.executable, "-c", code, str(topology), script],
        capture_output=True, text=True, cwd=str(REPO),
        env={**_env()},
    )
    marker = "@@JSON@@"
    if marker not in proc.stdout:
        return {"topology": topology,
                "fatal": "child produced no result",
                "trace": (proc.stdout[-800:] + "\n" + proc.stderr[-1500:])}
    return json.loads(proc.stdout.split(marker, 1)[1])


def _env() -> dict:
    import os
    e = dict(os.environ)
    # A key must be PRESENT for a client to construct; no call is made.
    e.setdefault("OPENAI_API_KEY", "sk-dummy")
    e["PYTHONIOENCODING"] = "utf-8"
    return e


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _report(res: dict, expected: list) -> bool:
    topo = res["topology"]
    print(f"=== topology {topo} ===")
    if "fatal" in res:
        print(f"  FATAL  {res['fatal']}")
        for line in (res.get("trace") or "").splitlines()[-12:]:
            print(f"         {line}")
        return False

    ok = True
    print(f"  hub: {res['hub']}   agent modules patched: "
          f"{res['patched_modules']}")
    want = [[a, t] for a, t in expected]
    seen = res["seen"]
    for i, step in enumerate(want):
        got = seen[i] if i < len(seen) else None
        mark = "OK " if got == step else "!! "
        if got != step:
            ok = False
        arrow = f"{step[0]:<14} -> {step[1] or '(prose, ends the turn)'}"
        print(f"  {mark}{i + 1:>2}. {arrow}"
              + ("" if got == step else f"      GOT {got}"))
    if len(seen) != len(want):
        ok = False
        print(f"  !! {len(seen)} agent invocations, expected {len(want)}")
    if not res["forwarded"]:
        ok = False
        print("  !! the Receptionist did NOT forward into the pipeline")
    if not (res["reply"] or "").strip():
        ok = False
        print("  !! the turn produced an EMPTY user-facing reply")
    else:
        print(f"  reply: {res['reply']!r}")
    for p in res["problems"]:
        ok = False
        print(f"  !! {p}")
    print(f"  --> {'PASS' if ok else 'FAIL'}")
    return ok


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--topology", type=int, choices=sorted(ROUTES),
                    help="only this one (default: all)")
    args = ap.parse_args(argv)
    topologies = [args.topology] if args.topology else sorted(ROUTES,
                                                              reverse=True)
    results = []
    for t in topologies:
        results.append(_report(_run_child(t), ROUTES[t]))
        print()
    bad = [t for t, ok in zip(topologies, results) if not ok]
    if bad:
        print(f"FAIL — topologies {bad} did not drive a clean turn")
        return 1
    print(f"ALL PASS — {len(topologies)} topolog"
          f"{'y' if len(topologies) == 1 else 'ies'} drove a complete turn "
          f"end to end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
