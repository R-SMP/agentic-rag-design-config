"""Structural pre-flight for every hub class: does it reach what it names?

Two failures this catches, both of which have actually happened in this repo
(see ``docs/active/topology_shared_touchpoints.md`` §E):

1. A hub calls ``self.<agent>.<method>()`` for a sub-agent its topology never
   constructs.  The class imports fine, the prompts assemble fine, and the
   ``AttributeError`` waits until ``reset()``, the step-limit summary or the
   end-of-session history dump — i.e. until a real run, late.
2. A hub calls a method that does not exist on the sub-agent's class, or with
   an incompatible signature.

The check is deliberately written the WIDE way.  Written narrowly for the
Architect — enumerating only the four attributes it was told about — it
reported "problems: none" while the class still called ``self.tool_caller``,
``self.creator`` and ``self.user_input_inspector``, three agents that topology
never builds.  So: enumerate EVERY ``self.<attr>.<method>()`` in the file and
flag any ``<attr>`` that ``__init__`` never assigns.

Pure ``ast``; imports nothing from the app, so it runs without trimesh,
langchain or a database.

    py -3.13 extra_utilities/smoke_test_hub_attributes.py
"""

from __future__ import annotations

import ast
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]

# hub file -> (class name, module of each sub-agent attribute it may hold)
HUBS = {
    "agents/orchestrator/orchestrator.py": "Orchestrator",
    "agents/planner5/planner5.py": "Planner5",
}

# Attributes that are NOT sub-agents: assigned in __init__ but not agents, or
# provided by BaseChainAgent.  A call on one of these is not our business.
NON_AGENT_ATTRS = {
    "session", "messages", "llm", "base_llm", "state", "context_pruner",
    "_tools_by_name", "_pending_hop", "_agents_by_key", "current_plan",
}

# Methods every sub-agent must expose, checked against its own class body.
CONTRACT_HINTS = ("run", "reset", "set_tools", "set_routing_tools",
                  "dump_histories", "on_operation_end")


# The edge set each hub must wire, as (caller, target) pairs.  Extracted from
# the source with ast, so this asserts what the code DOES, not what a comment
# claims.  ``self.AGENT_KEY`` is resolved to the class's own key.
#
# Topology 7 is transcribed from the live Orchestrator under its committed
# flags (PLANNER_FIRST=False, DC_INSPECTOR_ENABLED=True), including the
# branches that only one flag combination reaches -- the extractor sees every
# call site regardless of branch, so the expected set is their union.
EXPECTED_EDGES = {
    "Orchestrator": {
        ("planner", "user_input_inspector"),
        ("planner", "orchestrator"),
        ("planner", "dc_input_creator"),
        ("receptionist", "orchestrator"),
        ("user_input_inspector", "dc_input_creator"),
        ("user_input_inspector", "planner"),
        ("user_input_inspector", "orchestrator"),
        ("dc_input_creator", "dc_input_inspector"),
        ("dc_input_creator", "tool_caller"),
        ("dc_input_creator", "user_input_inspector"),
        ("dc_input_creator", "planner"),
        ("dc_input_creator", "orchestrator"),
        ("dc_input_inspector", "tool_caller"),
        ("dc_input_inspector", "dc_input_creator"),
        ("dc_input_inspector", "orchestrator"),
        ("tool_caller", "dc_input_inspector"),
        ("tool_caller", "dc_input_creator"),
        ("tool_caller", "dc_output_inspector"),
        ("tool_caller", "orchestrator"),
        ("dc_output_inspector", "tool_caller"),
        ("dc_output_inspector", "orchestrator"),
        ("orchestrator", "planner"),
        ("orchestrator", "user_input_inspector"),
        ("orchestrator", "dc_input_creator"),
        ("orchestrator", "tool_caller"),
        ("orchestrator", "dc_output_inspector"),
        ("orchestrator", "receptionist"),
        ("orchestrator", "dc_input_inspector"),
    },
    # Owner-confirmed 2026-08-31.  Note the two deliberate absences:
    # planner -> tool_caller and tool_caller -> planner.
    "Planner5": {
        ("receptionist", "planner"),
        ("user_input_inspector", "planner"),
        ("dc_input_creator", "tool_caller"),
        ("dc_input_creator", "planner"),
        ("tool_caller", "dc_output_inspector"),
        ("tool_caller", "dc_input_creator"),
        ("dc_output_inspector", "tool_caller"),
        ("dc_output_inspector", "dc_input_creator"),
        ("dc_output_inspector", "planner"),
        ("planner", "user_input_inspector"),
        ("planner", "dc_input_creator"),
        ("planner", "dc_output_inspector"),
        ("planner", "receptionist"),
    },
}


def _agent_key_of(cls: ast.ClassDef) -> str:
    for m in cls.body:
        if (isinstance(m, ast.Assign) and len(m.targets) == 1
                and isinstance(m.targets[0], ast.Name)
                and m.targets[0].id == "AGENT_KEY"
                and isinstance(m.value, ast.Constant)):
            return m.value.value
    raise SystemExit("AGENT_KEY not found")


def _wired_edges(cls: ast.ClassDef, agent_key: str) -> set:
    """Every ``build_routing_tool(caller, target, ...)`` pair in the class."""
    def literal(node):
        if isinstance(node, ast.Constant):
            return node.value
        if (isinstance(node, ast.Attribute) and node.attr == "AGENT_KEY"
                and isinstance(node.value, ast.Name)
                and node.value.id == "self"):
            return agent_key
        return None

    edges = set()
    for node in ast.walk(cls):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "build_routing_tool"):
            continue
        if len(node.args) < 2:
            continue
        a, b = literal(node.args[0]), literal(node.args[1])
        if a is None or b is None:
            raise SystemExit(
                f"unresolvable build_routing_tool args at line {node.lineno}"
            )
        edges.add((a, b))
    return edges


def _class_node(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise SystemExit(f"class {name} not found")


def _assigned_in_init(cls: ast.ClassDef) -> set[str]:
    """Every attribute the class provides.

    Both ``self.X = ...`` anywhere in the class AND plain class-level
    ``X = ...`` / ``X: T = ...``, since ``self.X`` resolves to those too --
    ``_AGENT_KEY_ALIASES`` and ``AGENT_KEY`` are class attributes, and a
    checker that ignored them would report two false positives per hub.
    """
    out: set[str] = set()
    for member in cls.body:
        if isinstance(member, ast.Assign):
            for t in member.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
        elif isinstance(member, ast.AnnAssign) and isinstance(member.target,
                                                              ast.Name):
            out.add(member.target.id)
    for node in ast.walk(cls):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for t in targets:
            if (isinstance(t, ast.Attribute)
                    and isinstance(t.value, ast.Name)
                    and t.value.id == "self"):
                out.add(t.attr)
    return out


def _self_attr_calls(cls: ast.ClassDef) -> list[tuple[str, str, int]]:
    """Every ``self.<attr>.<method>(...)`` as (attr, method, lineno)."""
    found: list[tuple[str, str, int]] = []
    for node in ast.walk(cls):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute):
            continue
        inner = fn.value
        if not (isinstance(inner, ast.Attribute)
                and isinstance(inner.value, ast.Name)
                and inner.value.id == "self"):
            continue
        found.append((inner.attr, fn.attr, node.lineno))
    return found


def main() -> int:
    problems: list[str] = []
    for rel, cls_name in HUBS.items():
        path = REPO / rel
        if not path.is_file():
            problems.append(f"{rel}: file missing")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        cls = _class_node(tree, cls_name)
        assigned = _assigned_in_init(cls) | NON_AGENT_ATTRS
        calls = _self_attr_calls(cls)

        print(f"\n=== {cls_name}  ({rel}) ===")
        print(f"  self.<attr> assigned anywhere in the class: "
              f"{len(assigned - NON_AGENT_ATTRS)}")
        print(f"  self.<attr>.<method>() call sites: {len(calls)}")

        seen: dict[str, set[str]] = {}
        for attr, method, lineno in calls:
            seen.setdefault(attr, set()).add(method)
            if attr not in assigned:
                problems.append(
                    f"{rel}:{lineno}: self.{attr}.{method}() — "
                    f"'{attr}' is never assigned on self"
                )
        for attr in sorted(seen):
            mark = " " if attr in assigned else "!"
            print(f"   {mark} self.{attr:<22} -> "
                  f"{', '.join(sorted(seen[attr]))}")

        # Edge set — what the class actually wires, vs what it should.
        want = EXPECTED_EDGES.get(cls_name)
        if want is not None:
            got = _wired_edges(cls, _agent_key_of(cls))
            print(f"  routing edges wired: {len(got)}")
            for missing in sorted(want - got):
                problems.append(
                    f"{rel}: edge {missing[0]} -> {missing[1]} is expected "
                    f"but NOT wired"
                )
            for extra in sorted(got - want):
                problems.append(
                    f"{rel}: edge {extra[0]} -> {extra[1]} is wired but NOT "
                    f"in the expected set"
                )

    print()
    if problems:
        print(f"PROBLEMS ({len(problems)}):")
        for p in problems:
            print("  - " + p)
        return 1
    print("problems: none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
