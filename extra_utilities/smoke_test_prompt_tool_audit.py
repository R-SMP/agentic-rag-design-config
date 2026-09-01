"""Does every tool an agent's PROMPT names actually exist in its bound set?

This is the defence against the one hazard the topology rebuild cannot design
away.  The 5-agent DCOI, UII and Tool Caller reuse the SAME ``AGENT_KEY`` as
their 7-agent twins, so their PROMPT has a topology override while their TOOL
BINDING does not.  A prompt can therefore promise a tool the class no longer
binds, and nothing raises: the agent simply calls something that is not there,
or works around its absence.

It has already happened twice in this repo:

* the 5-agent Conductor's prompt documented ``read_extracted_inputs`` and
  ``read_user_queries``, with a whole ``## Utility tool:`` section for the
  latter, while the class bound neither.  Live cost, every design turn: an
  ``Error: no attempts created yet``, then a wasted hop to the Tool Caller
  purely to have a file read back, ~60k tokens, and the only tool error in
  the run;
* the 5-agent DCOI's prompt documented ``list_input_files``,
  ``read_input_text`` and ``read_image_notes`` months after the class stopped
  binding any of them.

Both halves are DERIVED, never transcribed:

* the prompt side is the real assembled prompt, from
  ``topology_prompt_snapshot`` (which is itself cross-validated against
  ``prompt_pdf/dump.py``);
* the bound side is ``dump.json``'s real ``bind_tools`` lists for topology 7,
  and for topology 5 the same UTILITY tools (the classes are unchanged) plus
  the routing edges extracted from ``planner5.py`` with ``ast``.

    py -3.13 extra_utilities/smoke_test_prompt_tool_audit.py
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DUMP = ROOT / "extra_utilities" / "prompt_pdf" / "dump.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Tools that were REMOVED from the codebase.  A prompt still naming one is a
# defect even if no agent binds anything by that name any more -- the model is
# being told to call something that does not exist.
RETIRED_TOOLS = {
    "list_input_files", "read_input_text", "read_image_notes",
    "read_user_queries", "read_parameters", "new_attempt",
    "generate_propeller_mesh", "render_and_check_mesh",
}

# Agents built per topology.  The Database Handler is post-session and binds
# its own tools outside any hub, so it is audited from dump.json alone.
AGENTS = {
    7: ["receptionist", "orchestrator", "planner", "user_input_inspector",
        "dc_input_creator", "dc_input_inspector", "tool_caller",
        "dc_output_inspector", "database_handler"],
    5: ["receptionist", "planner", "user_input_inspector",
        "dc_input_creator", "tool_caller", "dc_output_inspector",
        "database_handler"],
}

# A prompt may legitimately NAME a tool it does not itself hold: the hub's
# roster describes what each agent can do, and the Database Handler's prompt
# describes the whole system.  So "named but not bound to me" is a note, not a
# failure.
#
# What is never legitimate is naming a tool that NO agent in the topology
# binds.  That is precisely the shape of all three defects on record -- the
# Conductor's ``read_user_queries``, the DCOI's ``list_input_files``, and a
# topology-5 prompt still saying ``call_orchestrator`` -- and it cannot be
# explained away as describing a neighbour, because there is no neighbour.
#
# Findings awaiting an approved fix.  Each entry is a tuple of substrings that
# must ALL appear in the finding line.
KNOWN_PENDING: tuple = (
    # Topology 5's prompt tree is a byte-identical fork of topology 7's, so it
    # still routes to ``call_orchestrator``.  The deliberate identical-first
    # baseline; the owner's prompt edits re-point it.
    ("topology 5", "``call_orchestrator``"),
)

failures: list[str] = []
pending: list[str] = []
notes: list[str] = []


def report(line: str) -> None:
    known = any(all(part in line for part in entry) for entry in KNOWN_PENDING)
    (pending if known else failures).append(line)


# ---------------------------------------------------------------------------
# The bound side
# ---------------------------------------------------------------------------

def load_dump() -> dict:
    """dump.json, regenerating it if absent (it is gitignored)."""
    if not DUMP.is_file():
        print("dump.json missing — running prompt_pdf/dump.py to build it")
        subprocess.run([sys.executable, "dump.py"],
                       cwd=str(DUMP.parent), check=True,
                       capture_output=True)
    return json.loads(DUMP.read_text(encoding="utf-8"))


def bound_7(dump: dict) -> dict:
    return {a: {t["name"] for t in rec["rag_off"]["tools"]}
            for a, rec in dump["agents"].items()}


def planner5_edges() -> set:
    """(caller, target) pairs wired by Planner5, read from its source."""
    src = (ROOT / "agents" / "planner5" / "planner5.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "Planner5")
    key = next(m.value.value for m in cls.body
               if isinstance(m, ast.Assign)
               and isinstance(m.targets[0], ast.Name)
               and m.targets[0].id == "AGENT_KEY")

    def lit(node):
        if isinstance(node, ast.Constant):
            return node.value
        if (isinstance(node, ast.Attribute) and node.attr == "AGENT_KEY"
                and isinstance(node.value, ast.Name)
                and node.value.id == "self"):
            return key
        return None

    out = set()
    for node in ast.walk(cls):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "build_routing_tool"
                and len(node.args) >= 2):
            a, b = lit(node.args[0]), lit(node.args[1])
            if a and b:
                out.add((a, b))
    return out


def bound_5(b7: dict) -> dict:
    """Topology 5's bound set, DERIVED.

    The chain agents' classes are the same objects in both topologies, so
    their UTILITY tools are identical; only the routing edges differ, and
    those come from Planner5's own source.
    """
    edges = planner5_edges()
    out = {}
    for agent in AGENTS[5]:
        utility = {t for t in b7.get(agent, set())
                   if not t.startswith("call_")}
        routing = {f"call_{tgt}" for src, tgt in edges if src == agent}
        out[agent] = utility | routing
    return out


# ---------------------------------------------------------------------------
# The prompt side
# ---------------------------------------------------------------------------

_spec = importlib.util.spec_from_file_location(
    "_tps", ROOT / "extra_utilities" / "topology_prompt_snapshot.py")
_tps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tps)

# ``x`` in double backticks, or a bare x( call -- the two ways this codebase
# writes a tool name.  A bare word is deliberately NOT matched: "calculate"
# and "planner" are ordinary English here.
_MENTION = re.compile(r"``([a-z_][a-z0-9_]*)``|\b([a-z_][a-z0-9_]*)\(")


def mentioned(text: str, vocabulary: set) -> set:
    found = set()
    for a, b in _MENTION.findall(text):
        name = a or b
        if name in vocabulary:
            found.add(name)
    return found


# ---------------------------------------------------------------------------

def main() -> int:
    dump = load_dump()
    b7 = bound_7(dump)
    bound = {7: b7, 5: bound_5(b7)}

    vocabulary = set(RETIRED_TOOLS)
    for per_agent in bound.values():
        for names in per_agent.values():
            vocabulary |= names

    # Every tool ANY agent of a topology binds -- the set a prompt of that
    # topology may legitimately mention.
    anywhere = {t: set().union(*bound[t].values()) for t in bound}

    for topo in (7, 5):
        data = _tps._run_child(topo)
        if "fatal" in data:
            failures.append(f"topology {topo}: could not assemble — "
                            f"{data['fatal']}")
            continue
        print(f"\n=== topology {topo} ===")
        for agent in AGENTS[topo]:
            text = data["prompts"].get(agent)
            if text is None:
                failures.append(f"topology {topo}: {agent} did not assemble")
                continue
            says = mentioned(text, vocabulary)
            has = bound.get(topo, {}).get(agent, set())

            orphan = sorted(says - anywhere[topo] - RETIRED_TOOLS)
            retired = sorted(says & RETIRED_TOOLS)
            elsewhere = sorted((says - has) & anywhere[topo])
            unmentioned = sorted(has - says)

            print(f"  {agent:<22} bound={len(has):<3} named={len(says):<3}"
                  f" names-nothing-binds={len(orphan)}"
                  f" retired={len(retired)}")
            for t in orphan:
                report(
                    f"[ORPHAN] topology {topo} {agent}: the prompt names "
                    f"``{t}`` but NO agent in this topology binds it"
                )
            for t in retired:
                report(
                    f"[RETIRED] topology {topo} {agent}: the prompt names "
                    f"``{t}``, a tool that no longer exists anywhere"
                )
            if elsewhere:
                notes.append(
                    f"topology {topo} {agent}: names a tool bound to another "
                    f"agent, not to itself — {elsewhere}"
                )
            if unmentioned:
                notes.append(
                    f"topology {topo} {agent}: bound but never named in the "
                    f"prompt — {unmentioned}"
                )

    print()
    for n in notes:
        print("NOTE  " + n)
    print()
    if pending:
        print(f"KNOWN-PENDING (awaiting an approved fix) — {len(pending)}:")
        for f in sorted(pending):
            print("  " + f)
        print()
    if failures:
        print(f"FAIL — {len(failures)} problem(s):")
        for f in failures:
            print("  " + f)
        return 1
    print("PASS — no prompt names a tool that nothing in its topology binds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
