"""Topology-aware fragment resolution — end-to-end check.

Answers one question:

    With ``SYSTEM_TOPOLOGY = 5``, does every assembled prompt read the
    5-agent copy of a fragment where one exists, and the shared original
    everywhere else — while topology 7 keeps reading exactly what it read
    before the topology indirection existed?

This imports the REAL ``agents/shared/prompts.py`` and
``agents/shared/routing.py``, not a replica.  Only ``agents/__init__.py``
is stubbed: it eagerly imports every agent class and so drags in
``langchain_core``, which is not installed here.  ``prompts.py`` and
``routing.py`` themselves import nothing beyond the standard library and
``workflow_settings``, so what runs below is the shipping resolver.

Nothing is hard-coded about WHICH fragments have a 5-agent copy — the
expected mapping is derived by walking ``agents/<N>agent/`` on disk, so
adding or removing an override needs no edit here.

Every case is run under BOTH settings of ``PLANNER_FIRST``, because that
flag branches some fragment names and only means something in the 7-agent
system.  A third, non-existent topology is exercised to confirm the
override machinery degrades to plain shared reads rather than crashing.

Run with Python >= 3.10 (``prompts.py`` uses PEP-604 ``X | None``
annotations at runtime)::

    py extra_utilities/smoke_test_topology_fragments.py
"""

import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Pre-seed package stubs so the real submodules import normally.
for _name, _rel in (("agents", "agents"), ("agents.shared", "agents/shared")):
    _m = types.ModuleType(_name)
    _m.__path__ = [str(ROOT / _rel)]
    sys.modules[_name] = _m

from agents.shared import prompts, routing  # noqa: E402

DC_FRAGMENTS_DIR = ROOT / "DC_prompt_fragments"
GENERIC_FRAGMENTS_DIR = ROOT / "agents" / "shared" / "prompt_fragments"

# Which agents each topology actually builds.  The Database Handler sits
# outside the design chain and exists in both.
AGENTS_BY_TOPOLOGY = {
    7: [
        "receptionist", "orchestrator", "planner", "user_input_inspector",
        "dc_input_creator", "dc_input_inspector", "tool_caller",
        "dc_output_inspector", "database_handler",
    ],
    5: [
        "receptionist", "conductor", "user_input_inspector", "creator",
        "tool_caller", "dc_output_inspector", "database_handler",
    ],
}

# The ``fragment_name=`` values each topology's chain agents pass to
# ``routing_instructions`` (grepped from the agent classes).  ``{pf}``
# expands to whichever PLANNER_FIRST branch is in force for the case.
ROUTING_FRAGMENTS_BY_TOPOLOGY = {
    7: [
        "routing_planner_{pf}.md",
        "routing_user_input_inspector_{pf}.md",
        "routing_dc_input_creator_{pf}.md",
        "routing_dc_input_inspector.md",
        "routing_tool_caller.md",
        "routing_dc_output_inspector.md",
    ],
    5: [
        "routing_user_input_inspector_{pf}.md",
        "routing_creator.md",
        "routing_tool_caller.md",
        "routing_dc_output_inspector.md",
    ],
}

# Each topology's hub — the agent whose prompt must NOT keep the
# <<CHAIN_ONLY>> rules, since "escalate to the hub" addressed to the hub
# is self-referential.
HUB_BY_TOPOLOGY = {7: "orchestrator", 5: "conductor"}

# Routing-tool names unique to each topology's hub fragment.  Used to prove
# $routing_hub resolved to the RIGHT file, not merely to some file: the
# 7-agent hub can call the Planner, the 5-agent hub can call the Creator,
# and neither name exists in the other topology.
HUB_MARKERS = {7: ("call_planner", "call_creator"),
               5: ("call_creator", "call_planner")}

# Defects found by this harness that are awaiting an approved fix.  Listed
# so the rest of the suite still reports a meaningful PASS/FAIL; each is
# printed separately and never silently swallowed.
KNOWN_PENDING: set = set()

failures: list[str] = []
pending: list[str] = []
notes: list[str] = []


def fail(case: str, check: str, msg: str) -> None:
    (pending if msg in KNOWN_PENDING else failures).append(
        f"[{check}] {case}: {msg}"
    )


def rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


# ---------------------------------------------------------------------------
# Derive the override -> shared-original map from disk
# ---------------------------------------------------------------------------

def shared_original(override: Path, topo: int) -> Path | None:
    """The file ``override`` shadows, derived from its mirrored location."""
    parts = override.resolve().relative_to(
        ROOT / "agents" / f"{topo}agent"
    ).parts
    sub, name = parts[0], parts[-1]
    stem = name[: -len(f"_{topo}agents{override.suffix}")]
    inner = Path(*parts[1:-1])
    original = f"{stem}{override.suffix}"
    if sub == "prompt_fragments":
        return GENERIC_FRAGMENTS_DIR / inner / original
    if sub in ("dc_config", "tools_config"):
        return DC_FRAGMENTS_DIR / sub / inner / original
    # Otherwise <agent>/prompt.md — an agent that also exists in 7-agent.
    return ROOT / "agents" / sub / inner / original


def overrides_for(topo: int) -> dict:
    d = ROOT / "agents" / f"{topo}agent"
    if not d.is_dir():
        return {}
    return {
        f.resolve(): shared_original(f, topo)
        for f in sorted(d.rglob("*"))
        if f.is_file() and f.suffix in (".md", ".txt")
    }


# ---------------------------------------------------------------------------
# Assemble every prompt for one (topology, PLANNER_FIRST) case
# ---------------------------------------------------------------------------

def assemble(topo: int, planner_first: bool, *, as_topology: int | None = None
             ) -> tuple[set, dict]:
    """Build every prompt for one case, returning (files read, templates).

    ``as_topology`` selects WHICH agent/routing set to build when the
    topology under test has no set of its own — used by the DEGRADE case,
    which drives the 7-agent workload through a non-existent topology.
    """
    which = as_topology if as_topology is not None else topo
    prompts._workflow_settings.SYSTEM_TOPOLOGY = topo
    prompts.PLANNER_FIRST = planner_first
    seen: set = set()
    original = Path.read_text

    def spy(self, *a, **k):
        seen.add(self.resolve())
        return original(self, *a, **k)

    pf = "planner_first" if planner_first else "uii_first"
    built: dict = {}
    Path.read_text = spy
    try:
        for agent in AGENTS_BY_TOPOLOGY[which]:
            built[agent] = prompts._build_template(agent)
        for frag in ROUTING_FRAGMENTS_BY_TOPOLOGY[which]:
            name = frag.format(pf=pf)
            built[f"routing::{name}"] = routing._load_routing_fragment(name)
    finally:
        Path.read_text = original
    return seen, built


def check_case(topo: int, planner_first: bool) -> None:
    case = f"topology {topo}, PLANNER_FIRST={planner_first}"
    read, built = assemble(topo, planner_first)
    ov = overrides_for(topo)

    # --- COVERAGE: every override for this topology is actually read ------
    for p in sorted(ov):
        if p not in read:
            orig = ov[p]
            extra = (
                f"; the shared {rel(orig)} was read instead"
                if orig and orig.resolve() in read else ""
            )
            fail(case, "COVERAGE", f"{rel(p)} was never read{extra}")

    # --- NO-LEAK: never read the original of something we override --------
    for ovr, orig in ov.items():
        if orig is not None and orig.resolve() in read and ovr in read:
            fail(case, "NO-LEAK",
                 f"BOTH {rel(ovr)} and its original {rel(orig)} were read")

    # --- ISOLATION: never read ANOTHER topology's tree --------------------
    for p in sorted(read):
        for other in (3, 5, 7):
            if other != topo and f"agents/{other}agent/" in rel(p):
                fail(case, "ISOLATION",
                     f"topology {topo} read a {other}-agent file: {rel(p)}")
                break

    # --- SHARING: everything else comes from the shared trees -------------
    shared_read = [
        p for p in read
        if p not in ov and (
            str(GENERIC_FRAGMENTS_DIR) in str(p)
            or str(DC_FRAGMENTS_DIR) in str(p)
        )
    ]
    notes.append(
        f"{case}: {len(shared_read)} fragments read from the shared trees, "
        f"{len([p for p in ov if p in read])}/{len(ov)} overrides read"
    )

    # --- SLOTS: nothing left unsubstituted --------------------------------
    slot_names = set(prompts._build_slots()) | {
        "database_search_per_agent", "blade_sections_visualizer_per_agent",
    }
    for who, text in built.items():
        for m in sorted(set(re.findall(r"\$([a-z_][a-z0-9_]*)", text))):
            kind = ("left UNSUBSTITUTED" if m in slot_names
                    else "has no slot defined")
            fail(case, "SLOT", f"topology {topo} {who}: ${m} {kind}")

    # --- HUB SLOT: $routing_hub resolved to THIS topology's hub fragment --
    hub = HUB_BY_TOPOLOGY[topo]
    hub_text = built.get(hub, "")
    want, must_not = HUB_MARKERS[topo]
    if want not in hub_text:
        fail(case, "HUB-SLOT",
             f"the hub ({hub}) prompt lacks '{want}' — $routing_hub did not "
             f"resolve to routing_{hub}")
    if must_not in hub_text:
        fail(case, "HUB-SLOT",
             f"the hub ({hub}) prompt contains '{must_not}', which belongs "
             f"to the OTHER topology's hub fragment")
    for other_slot in ("$routing_orchestrator", "$routing_conductor"):
        for who, text in built.items():
            if other_slot in text:
                fail(case, "HUB-SLOT",
                     f"{who} still references the retired {other_slot}")

    # --- CHAIN_ONLY: the hub must not keep chain-link rules ---------------
    marker = "FORWARD to your natural"
    if marker in hub_text:
        fail(case, "CHAIN_ONLY",
             f"the hub ({hub}) kept the chain-link rules: '{marker}'")
    for agent in AGENTS_BY_TOPOLOGY[topo]:
        if agent in (hub, "receptionist", "database_handler"):
            continue
        if marker not in built[agent]:
            fail(case, "CHAIN_ONLY",
                 f"chain agent {agent} LOST the chain-link rules")


# ---------------------------------------------------------------------------

for _topo in (7, 5):
    for _pf in (False, True):
        check_case(_topo, _pf)

# --- DEGRADE: a topology with no directory must fall back, not crash ------
# Drive the SAME workload under topology 7 and under a topology that has no
# directory at all.  Every override lookup misses, so the two runs must read
# exactly the same files and produce exactly the same prompts.
try:
    base_read, base_built = assemble(7, False)
    deg_read, deg_built = assemble(3, False, as_topology=7)
    if deg_read != base_read:
        failures.append(
            f"[DEGRADE] topology 3 (no directory) read a different file set "
            f"than topology 7: {sorted(rel(p) for p in deg_read ^ base_read)}"
        )
    differing = [k for k in base_built if base_built[k] != deg_built.get(k)]
    if differing:
        failures.append(
            f"[DEGRADE] topology 3 produced different prompts than "
            f"topology 7 for: {differing}"
        )
except Exception as exc:  # noqa: BLE001
    failures.append(f"[DEGRADE] topology 3 raised {type(exc).__name__}: {exc}")

# --- PRECEDENCE: an exact-name override must beat the collapsed one -------
prompts._workflow_settings.SYSTEM_TOPOLOGY = 5
_exact = (ROOT / "agents" / "5agent" / "prompt_fragments"
          / "routing_user_input_inspector_uii_first_5agents.md")
try:
    _exact.write_text("### EXACT-NAME PROBE\n", encoding="utf-8")
    got = routing._load_routing_fragment(
        "routing_user_input_inspector_uii_first.md"
    )
    if "EXACT-NAME PROBE" not in got:
        failures.append(
            "[PRECEDENCE] a branched override (…_uii_first_5agents.md) exists "
            "but the collapsed name won instead"
        )
finally:
    _exact.unlink(missing_ok=True)

# ---------------------------------------------------------------------------

print("Resolution summary")
for n in notes:
    print(f"  {n}")
print()

if pending:
    print(f"KNOWN-PENDING (awaiting an approved fix) — {len(pending)}:")
    for p in sorted(set(pending)):
        print(f"  {p}")
    print()

if failures:
    print(f"FAIL — {len(failures)} problem(s):\n")
    for f in failures:
        print(f"  {f}")
    sys.exit(1)
print("PASS — every override reached, no original leaked, no cross-topology "
      "read, hub/chain filtering correct, missing topology degrades cleanly.")
