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

# Windows consoles default to cp1252, and the pipeline strings contain
# U+2192 (→).  Without this, a failure whose detail quotes one crashes the
# report with a UnicodeEncodeError instead of printing the finding — the
# test still exits non-zero, but says nothing useful about why.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Pre-seed package stubs so the real submodules import normally.
for _name, _rel in (("agents", "agents"), ("agents.shared", "agents/shared")):
    _m = types.ModuleType(_name)
    _m.__path__ = [str(ROOT / _rel)]
    sys.modules[_name] = _m

# routing_tools.py needs langchain_core for StructuredTool, which is not
# installed here.  Stub the ONE symbol it imports so the rest of that
# module — the identity tables, stuck_escalation, the hub-aware routing
# tool factory — can be exercised for real rather than by replica.
_lc = types.ModuleType("langchain_core")
_lc.__path__ = []
_lct = types.ModuleType("langchain_core.tools")


class _StubStructuredTool:  # noqa: D101
    @staticmethod
    def from_function(*a, **k):
        return None


_lct.StructuredTool = _StubStructuredTool
sys.modules["langchain_core"] = _lc
sys.modules["langchain_core.tools"] = _lct

from agents.shared import prompts, routing, routing_tools, topology  # noqa: E402

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

# The Database Handler is the ONLY agent whose assembled template is never
# passed through ``str.format()`` — ``database_handler.py`` builds it with
# ``_build_template`` alone.  Literal braces in its prompt are therefore
# harmless, and it deliberately carries a JSON example.  Every other agent
# IS formatted at construction, so a stray brace there is fatal at startup.
# The Receptionist joined the formatted set when it gained its two path
# slots; before that it was the second exception.
NEVER_FORMATTED = frozenset({"database_handler"})

# Who hands the UII its paths at the START of a turn.  In the 7-agent flow
# the Orchestrator kicks off the UII; in the 5-agent flow the Receptionist
# routes to it directly.  They get the paths differently, and deliberately
# so: the Orchestrator relays the ``Input file directory:`` line it already
# receives in the dispatch kickoff and names the extraction file inside it,
# while the Receptionist carries both as runtime slots filled at
# construction.  What this check enforces is only that whoever kicks off
# actually STATES both — the UII's read and write tools each take a required
# ``path`` with no default, so an unstated path leaves it guessing.
UII_KICKOFF_AGENT = {7: "orchestrator", 5: "receptionist"}

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

    # --- FORMAT: every assembled prompt must survive str.format() ---------
    # The codebase's top recorded gotcha: agent prompts are .format()ed at
    # construction, so ONE literal { or } anywhere in a prompt or in any of
    # the ~40 fragments spliced into it raises KeyError/ValueError and takes
    # the whole pipeline down at startup.  Feeding each template exactly the
    # slots it declares reproduces what the agent does for real.
    for agent in AGENTS_BY_TOPOLOGY[topo]:
        if agent in NEVER_FORMATTED:
            continue
        declared = prompts.PROMPT_MD_RUNTIME_SLOTS.get(agent, frozenset())
        kwargs = {k: f"<{k}>" for k in declared}
        try:
            built[agent].format(**kwargs)
        except Exception as exc:  # noqa: BLE001
            fail(case, "FORMAT",
                 f"{agent}: assembled prompt fails .format() with its own "
                 f"declared slots ({sorted(declared) or 'none'}) — "
                 f"{type(exc).__name__}: {exc}.  A literal brace needs "
                 f"doubling to {{{{ / }}}}.")

    # --- UII-PATHS: whoever can call the UII must state its two paths -----
    # write_extraction's ``path`` and read_user_inputs's ``path`` are both
    # REQUIRED with no default, so an agent that calls the UII without
    # stating them leaves the UII guessing.  That is exactly how the
    # 7-agent system regressed unnoticed: the only emitter sat inside a
    # <<PF_ON>> block, PLANNER_FIRST flipped to False, and the block was
    # silently stripped.
    # Only the agent that KICKS OFF the UII is required to state them.
    # Agents that merely CLARIFY back to the UII later in the same turn are
    # exempt: agents are stateful within a session, so a UII that already
    # ran still holds the original hand-off — and its paths — in its own
    # message history.  (The Planner under PF_OFF is exactly such a case.)
    #
    # The label must BEGIN a line, i.e. actually be emitted, not merely
    # mentioned: a shared fragment discusses "the paths a hand-off label
    # gives (``Input directory:`` …)" in prose, and a bare substring test
    # would accept that as if the instruction were still there.
    agent = UII_KICKOFF_AGENT[topo]
    emitted = {ln.strip() for ln in built[agent].splitlines()}
    for label in ("Input directory:", "Extraction output file:"):
        if not any(ln.startswith(label) for ln in emitted):
            fail(case, "UII-PATHS",
                 f"{agent} kicks off the UII but its prompt never emits a "
                 f"{label!r} line — the UII's tools require an explicit path")

    # --- CHAIN_ONLY: the hub must not keep chain-link rules ---------------
    # Anchors are DERIVED from the fragment THIS topology actually resolves
    # -- one per <<CHAIN_ONLY>> region, the longest line inside it -- rather
    # than hard-coded.  Hard-coding is what made the previous version of
    # this check rot: its marker lived in a bullet that was later cut, and a
    # marker matching nothing makes BOTH halves pass vacuously (the hub is
    # trivially "clean" of a string no prompt contains).  Deriving also
    # covers regions added later, and survives a rewording.
    #
    # It must stay per-topology: topology 5 keeps its own
    # generic_constraints_5agents.md, whose regions are worded differently.
    # Do not shorten an anchor to something both files share -- both hubs
    # RELAY standing directives, so a short "=== STANDING DIRECTIVES ..."
    # substring is present in the hub and the absence half would false-fail.
    #
    # NOT "FORWARD to your natural": that bullet was cut from the shared
    # fragment deliberately, as provably duplicated with routing.py, which
    # owns FORWARD-is-default and states it at routing.py:202-213.  It
    # reaches agents through the {routing_instructions} slot, filled at
    # construction -- so it is NOT in _build_template output and a check
    # here could never see it.  That rule is asserted on the routing block
    # itself, further down.
    regions = prompts._CHAIN_ONLY_RE.findall(
        prompts._read_generic_fragment("generic_constraints.md"))
    if not regions:
        fail(case, "CHAIN_ONLY",
             "generic_constraints.md has no <<CHAIN_ONLY>> region left — "
             "this check would pass vacuously")
    for region in regions:
        lines = [ln.strip() for ln in region.splitlines()
                 if len(ln.strip()) >= 40]
        if not lines:
            fail(case, "CHAIN_ONLY",
                 "a <<CHAIN_ONLY>> region has no line long enough to anchor "
                 "on — shorten the threshold or the region is now trivial")
            continue
        marker = max(lines, key=len)
        if marker in hub_text:
            fail(case, "CHAIN_ONLY",
                 f"the hub ({hub}) kept a chain-link rule: '{marker[:48]}'")
        for agent in AGENTS_BY_TOPOLOGY[topo]:
            if agent in (hub, "receptionist", "database_handler"):
                continue
            if marker not in built[agent]:
                fail(case, "CHAIN_ONLY",
                     f"chain agent {agent} LOST a chain-link rule: "
                     f"'{marker[:48]}'")


# ---------------------------------------------------------------------------

for _topo in (7, 5):
    for _pf in (False, True):
        check_case(_topo, _pf)

# --- HUB: the routing boilerplate must name the ACTIVE topology's hub -----
# Chain agents whose ## Routing section is built by routing_instructions(),
# with the natural neighbours each topology gives them.
CHAIN_BY_TOPOLOGY = {
    7: [("User Input Inspector", "Planner", None,
         "routing_user_input_inspector_{pf}.md"),
        ("Tool Caller", "DC Output Inspector", "DC Input Inspector",
         "routing_tool_caller.md"),
        ("DC Output Inspector", None, "Tool Caller",
         "routing_dc_output_inspector.md")],
    5: [("User Input Inspector", "Conductor", "Receptionist",
         "routing_user_input_inspector_{pf}.md"),
        ("Creator", "Tool Caller", "Conductor", "routing_creator.md"),
        ("Tool Caller", "DC Output Inspector", "Creator",
         "routing_tool_caller.md"),
        ("DC Output Inspector", None, "Tool Caller",
         "routing_dc_output_inspector.md")],
}

for _topo, _rows in CHAIN_BY_TOPOLOGY.items():
    _other_hub = HUB_BY_TOPOLOGY[7 if _topo == 5 else 5]
    _other_display = {"orchestrator": "Orchestrator",
                      "conductor": "Conductor"}[_other_hub]
    for _pf_flag in (False, True):
        prompts._workflow_settings.SYSTEM_TOPOLOGY = _topo
        prompts.PLANNER_FIRST = _pf_flag
        _case = f"topology {_topo}, PLANNER_FIRST={_pf_flag}"
        _pf = "planner_first" if _pf_flag else "uii_first"
        _hub_disp = topology.hub_display()

        # natural_pipeline() must describe THIS topology.
        _flow = routing.natural_pipeline()
        if _other_display in _flow:
            fail(_case, "HUB",
                 f"natural_pipeline() names the other hub: {_flow}")
        if _hub_disp not in _flow:
            fail(_case, "HUB",
                 f"natural_pipeline() never names its own hub: {_flow}")

        for _name, _next, _prev, _frag in _rows:
            block = routing.routing_instructions(
                agent_name=_name, next_agent=_next, prev_agent=_prev,
                fragment_name=_frag.format(pf=_pf),
            )
            if _other_display in block:
                bad = [ln.strip() for ln in block.splitlines()
                       if _other_display in ln]
                fail(_case, "HUB",
                     f"{_name}'s routing section names the other hub "
                     f"({_other_display}): {bad[:2]}")
            # routing.py is now the SOLE owner of FORWARD-is-default:
            # generic_constraints.md dropped its copy as provably
            # duplicated, so nothing else in the system states it.
            if "route FORWARD to the next agent" not in block:
                fail(_case, "ROUTING",
                     f"{_name}'s routing block never states FORWARD-is-"
                     f"default -- generic_constraints.md no longer does")
            if f"the {_hub_disp}" not in block:
                fail(_case, "HUB",
                     f"{_name}'s routing section never names its own hub "
                     f"({_hub_disp})")
            # The Planner is a distinct grantor ONLY in the 7-agent system.
            has_planner_grantor = "from the Planner" in block
            if _topo == 7 and not has_planner_grantor:
                fail(_case, "HUB",
                     f"{_name}: 7-agent lost the Planner as an "
                     f"authorisation source")
            if _topo != 7 and has_planner_grantor:
                fail(_case, "HUB",
                     f"{_name}: names the Planner as an authorisation "
                     f"source, but it is merged into the hub here")

        # stuck_escalation must target the active hub, not a literal.
        hop = routing_tools.stuck_escalation("Tool Caller", "calculate")
        if hop.target != HUB_BY_TOPOLOGY[_topo]:
            fail(_case, "HUB",
                 f"stuck_escalation targets {hop.target!r}, expected "
                 f"{HUB_BY_TOPOLOGY[_topo]!r}")

# --- FACTORY: build_hub must return the active topology's hub -------------
# The real hub classes cannot be constructed here (they need a live
# langchain_core and a Session), so both modules are replaced by sentinels.
# What is under test is build_hub's BRANCH, which is the whole of its logic.
class _SentinelOrchestrator:
    def __init__(self, session=None, llm_cache=None):
        self.which = "orchestrator"


class _SentinelConductor:
    def __init__(self, session=None, llm_cache=None):
        self.which = "conductor"


class _SentinelArchitect:
    def __init__(self, session=None, llm_cache=None):
        self.which = "architect"


_mo = types.ModuleType("agents.orchestrator")
_mo.Orchestrator = _SentinelOrchestrator
_mc = types.ModuleType("agents.conductor")
_mc.Conductor = _SentinelConductor
_ma = types.ModuleType("agents.architect")
_ma.Architect = _SentinelArchitect
sys.modules["agents.orchestrator"] = _mo
sys.modules["agents.conductor"] = _mc
sys.modules["agents.architect"] = _ma

from agents.hub import build_hub  # noqa: E402

for _topo, _expect in ((7, "orchestrator"), (5, "conductor"),
                       (3, "architect"), (99, "orchestrator")):
    prompts._workflow_settings.SYSTEM_TOPOLOGY = _topo
    got = build_hub(session=None).which
    if got != _expect:
        failures.append(
            f"[FACTORY] topology {_topo}: build_hub returned the {got} "
            f"hub, expected {_expect}"
        )

# --- IDENTITY: every table must agree on the agent-key universe -----------
# The 5-agent agents are registered in several independent tables.  Missing
# one is silent: dh_schedule.AGENT_KEYS validates schedule entries, so
# omitting 'conductor' there meant a schedule naming it was REJECTED and the
# DH could never interview the hub of a 5-agent run.
from agents.shared import session as _session_mod  # noqa: E402
from agents.shared import trace as _trace_mod  # noqa: E402
from workflow_settings import dh_schedule as _dh  # noqa: E402
from workflow_settings import llm_routing as _llm  # noqa: E402

for _agent in ("conductor", "creator"):
    _display = routing_tools.AGENT_DISPLAY.get(_agent)
    for _label, _ok in (
        ("routing_tools.AGENT_DISPLAY", _display is not None),
        ("routing_tools.ROUTING_TOOL_NAMES",
         f"call_{_agent}" in routing_tools.ROUTING_TOOL_NAMES),
        ("session.KNOWN_AGENT_KEYS", _agent in _session_mod.KNOWN_AGENT_KEYS),
        ("trace._AGENT_DISPLAY_NAMES",
         _display in _trace_mod._AGENT_DISPLAY_NAMES),
        ("llm_routing.AGENT_KEYS", _agent in _llm.AGENT_KEYS),
        ("dh_schedule.AGENT_KEYS", _agent in _dh.AGENT_KEYS),
        ("dh_schedule.AGENT_SHORT_LABELS", _agent in _dh.AGENT_SHORT_LABELS),
    ):
        if not _ok:
            failures.append(f"[IDENTITY] {_agent!r} missing from {_label}")

# Both 5-agent agents are constructed by build_hub now, so neither may
# still be flagged unwired in the LLM-routing spec.
for _k, _d, _wired in _llm.AGENT_SPEC:
    if _k in ("conductor", "creator") and not _wired:
        failures.append(
            f"[IDENTITY] llm_routing marks {_k!r} unwired, but build_hub "
            f"constructs it under topology 5"
        )

# --- TABLES: topology.py display names must match AGENT_DISPLAY -----------
for _key, _disp in topology._HUB_BY_TOPOLOGY.values():
    if routing_tools.AGENT_DISPLAY.get(_key) != _disp:
        failures.append(
            f"[TABLES] topology.py calls {_key!r} {_disp!r} but "
            f"AGENT_DISPLAY calls it "
            f"{routing_tools.AGENT_DISPLAY.get(_key)!r}"
        )

# --- DEGRADE: an UNREGISTERED topology must fall back, not crash ----------
# Drive the SAME workload under topology 7 and under a topology that is in
# no table at all.  Every override lookup misses and the hub falls back to
# the Orchestrator, so the two runs must read exactly the same files and
# produce exactly the same prompts.
#
# The probe is deliberately a number NO topology uses.  It was 3 until the
# 3-agent was registered in _HUB_BY_TOPOLOGY; from that moment topology 3
# resolves $routing_hub to routing_architect.md and CRASHES until its
# fragments exist — which is correct and wanted.  Selecting a registered
# topology whose files are missing must fail loudly, never silently run the
# 7-agent set.  Only a genuinely unknown N tests the fall-back path.
try:
    base_read, base_built = assemble(7, False)
    deg_read, deg_built = assemble(99, False, as_topology=7)
    if deg_read != base_read:
        failures.append(
            f"[DEGRADE] an unregistered topology read a different file set "
            f"than topology 7: {sorted(rel(p) for p in deg_read ^ base_read)}"
        )
    differing = [k for k in base_built if base_built[k] != deg_built.get(k)]
    if differing:
        failures.append(
            f"[DEGRADE] an unregistered topology produced different "
            f"prompts than topology 7 for: {differing}"
        )
except Exception as exc:  # noqa: BLE001
    failures.append(
        f"[DEGRADE] an unregistered topology raised "
        f"{type(exc).__name__}: {exc}"
    )

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

# --- SCOPED FRAGMENTS: per-agent copies of a shared fragment --------------
#
# Two properties, both mutation-tested when written (§D: a check that has never
# failed has not been shown to work):
#   (1) with NO scoped file on disk the mechanism is inert — every assembled
#       prompt is byte-identical to what it was before the table existed;
#   (2) a scoped file wins for its OWN agent and for no other.
#
# The probe uses the 7-agent DC Input Inspector because it splices
# $hard_constraints_dc and is not the hub, so a leak would show up in seven
# sibling prompts.
prompts._workflow_settings.SYSTEM_TOPOLOGY = 7
prompts.PLANNER_FIRST = False

_SCOPE_AGENTS = [
    "receptionist", "orchestrator", "planner", "user_input_inspector",
    "dc_input_creator", "dc_input_inspector", "tool_caller",
    "dc_output_inspector",
]
_before = {a: prompts._build_template(a) for a in _SCOPE_AGENTS}

# (1) inertness — no scoped file exists for any registered slot right now.
_live = [
    (slot, a) for slot in prompts.SCOPED_FRAGMENTS for a in _SCOPE_AGENTS
    if prompts.scoped_fragment_path(slot, a) is not None
]
if _live:
    notes.append(
        f"scoped fragments live on disk: {sorted(_live)} — inertness case skipped"
    )

# (2) precedence + isolation.
_probe = (ROOT / "DC_prompt_fragments" / "dc_config"
          / "hard_constraints_dc_dc_input_inspector.md")
if _probe.exists():
    failures.append(
        f"[SCOPED] probe path {_probe.name} already exists — refusing to "
        "overwrite a real file; rename the probe"
    )
else:
    try:
        _probe.write_text("### SCOPED PROBE\n", encoding="utf-8")
        _after = {a: prompts._build_template(a) for a in _SCOPE_AGENTS}
        if "SCOPED PROBE" not in _after["dc_input_inspector"]:
            failures.append(
                "[SCOPED] dc_input_inspector has its own hard_constraints_dc "
                "copy on disk but assembled the SHARED fragment instead"
            )
        if "Domain hard rules" in _after["dc_input_inspector"]:
            failures.append(
                "[SCOPED] the scoped copy was ADDED alongside the shared "
                "fragment instead of REPLACING it"
            )
        _leaked = [
            a for a in _SCOPE_AGENTS
            if a != "dc_input_inspector" and _after[a] != _before[a]
        ]
        if _leaked:
            failures.append(
                f"[SCOPED] a dc_input_inspector-scoped fragment changed other "
                f"agents' prompts: {_leaked}"
            )
    finally:
        _probe.unlink(missing_ok=True)

    _restored = {a: prompts._build_template(a) for a in _SCOPE_AGENTS}
    _dirty = [a for a in _SCOPE_AGENTS if _restored[a] != _before[a]]
    if _dirty:
        failures.append(
            f"[SCOPED] removing the probe did not restore the shared "
            f"fragment for: {_dirty}"
        )

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
