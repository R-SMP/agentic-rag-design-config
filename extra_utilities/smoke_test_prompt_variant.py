"""PROMPT_VARIANT — assemble every prompt under each variant and diff the hashes.

Answers the question that matters when applying the shrink proposal one cut at
a time:

    Does selecting PROMPT_VARIANT="reduced" change EXACTLY the agents the
    override files on disk are supposed to change, and nothing else?

Three properties, all derived from what is on disk — nothing about WHICH files
have an override is hard-coded here, so adding or reverting a cut needs no edit
to this file:

  (1) REACHED     every file under agents/<N>agent_<variant>/ is actually
                  resolved by prompts._topology_override.  A typo in the suffix
                  (``_7agent_reduced`` for ``_7agents_reduced``) does not raise
                  — the lookup misses and the prompt is silently the standard
                  text.  This is the failure mode the whole variant mechanism
                  is most exposed to, and smoke_test_topology_fragments does
                  NOT cover it: that suite walks agents/<N>agent/ only.

  (2) BLAST RADIUS  the set of agents whose assembled prompt differs between
                  variants equals the set predicted from those files.  Catches
                  both a leak (an override reaching an agent it should not) and
                  a miss (an override reaching fewer agents than its slot is
                  spliced into).

  (3) INERT       a topology with no variant directory assembles byte-identical
                  prompts under every variant.  Guards the resolver itself:
                  variant machinery must not perturb the topologies in use.

  (4) CONSUMED    text the override DELETED from its base must be absent from
                  the assembled prompt.  (1) proves a file is resolvable, not
                  that the assembly path reads it — and when a second override
                  already moves the same agents, a dead one passes both (1) and
                  (2) unnoticed.  Found by mutation-testing this file.

Run with Python >= 3.10 (prompts.py uses PEP-604 annotations at runtime)::

    py extra_utilities/smoke_test_prompt_variant.py

Only ``agents/__init__.py`` is stubbed, for the same reason as
smoke_test_topology_fragments: it eagerly imports every agent class and so
drags in langchain_core, which is not installed here.  prompts.py itself
imports nothing beyond the standard library and workflow_settings, so what runs
below is the shipping resolver.
"""

import hashlib
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Windows consoles default to cp1252 and the prompts contain U+2192 (→).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

for _name, _rel in (("agents", "agents"), ("agents.shared", "agents/shared")):
    _m = types.ModuleType(_name)
    _m.__path__ = [str(ROOT / _rel)]
    sys.modules[_name] = _m

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

from agents.shared import prompts  # noqa: E402

AGENTS_DIR = ROOT / "agents"
DC_FRAGMENTS_DIR = ROOT / "DC_prompt_fragments"
GENERIC_FRAGMENTS_DIR = AGENTS_DIR / "shared" / "prompt_fragments"

# Which agents each topology builds.  Mirrors smoke_test_topology_fragments;
# the Database Handler sits outside the design chain and exists in all three.
AGENTS_BY_TOPOLOGY = {
    7: [
        "receptionist", "orchestrator", "planner", "user_input_inspector",
        "dc_input_creator", "dc_input_inspector", "tool_caller",
        "dc_output_inspector", "database_handler",
    ],
    5: [
        "receptionist", "conductor", "user_input_inspector", "creator",
        "dc_output_inspector", "database_handler",
    ],
    3: ["receptionist", "architect", "designer", "database_handler"],
}

# Variants the settings editor offers, minus the baseline.
VARIANTS = ["reduced"]

failures: list[str] = []
notes: list[str] = []

# Variant files with NO shared original, consumed by CODE rather than spliced
# into a prompt — e.g. the end-of-session feedback envelope, which is prepended
# to a runtime message by feedback_tool.feedback_envelope().  They shadow
# nothing, so they must not be expected to move any assembled prompt.
#
# DECLARED in extra_utilities/fork_manifest.json (relation "new"), never
# inferred from "the base file is missing": a typo in an override's basename
# also makes its base look missing, and inferring would silently reclassify
# that typo as intentional — the exact failure the REACHED check exists for.
_RUNTIME_ONLY: set[str] = set()
_MANIFEST = ROOT / "extra_utilities" / "fork_manifest.json"
if _MANIFEST.is_file():
    import json as _json
    for _e in _json.loads(_MANIFEST.read_text(encoding="utf-8")).get("forks", []):
        if _e.get("relation") == "new" or _e.get("origin") is None:
            _RUNTIME_ONLY.add(_e["fork"])
# (topo, variant, override filename, affected agents, text it deleted)
consumed_probes: list[tuple[int, str, str, list[str], str]] = []


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def assemble(topo: int, planner_first: bool, variant: str, agent: str):
    """(sha, length) for one prompt, or ('MISSING', reason)."""
    prompts._workflow_settings.SYSTEM_TOPOLOGY = topo
    prompts._workflow_settings.PROMPT_VARIANT = variant
    prompts.PLANNER_FIRST = planner_first
    try:
        text = prompts._build_template(agent)
    except FileNotFoundError as exc:
        return ("MISSING", Path(str(exc).split("'")[-2]).name)
    except Exception as exc:  # noqa: BLE001
        return ("ERROR", f"{type(exc).__name__}: {exc}")
    return (hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], len(text))


# ---------------------------------------------------------------------------
# Deriving the expected blast radius from the override files on disk
# ---------------------------------------------------------------------------

def _mentions_slot(text: str, slot: str) -> bool:
    """True when *text* references ``$slot`` as a WHOLE identifier.

    A bare ``f"${slot}" in text`` is wrong whenever one slot name is a PREFIX
    of another.  Live case: ``$agent_tools_overview`` is a prefix of
    ``$agent_tools_overview_brief``, so agents/database_handler/prompt.md —
    which references only the _brief slot — matched BOTH.  The test then put
    the Database Handler in the expected blast radius of an
    agent_tools_overview override, saw its prompt (correctly) not change, and
    failed with [BLAST] on a change that was right.  Reproduced before this
    fix; the same hazard sits on the nested-slot loop below.

    Production is unaffected: ``string.Template.safe_substitute``
    (prompts.py:1000-1001) matches the longest identifier, and the admin UI
    scans with ``\\$([a-z_][a-z0-9_]*)``.  This was a test-only defect — which
    is worse than it sounds, because the gate is the thing that decides a
    prompt change is safe.
    """
    return re.search(rf"\${re.escape(slot)}(?![A-Za-z0-9_])", text) is not None


def _prompt_md_slot_users() -> dict[str, set[str]]:
    """$slot -> agents whose own prompt.md references it, one nesting level
    resolved (available_agents.md itself references $tool_inventory, and
    _build_template runs two substitution passes to handle exactly that)."""
    direct: dict[str, set[str]] = {}
    for agent_dir in sorted(AGENTS_DIR.iterdir()):
        md = agent_dir / "prompt.md"
        if not md.is_file():
            continue
        text = md.read_text(encoding="utf-8")
        for path, slot in prompts.FRAGMENT_TO_SLOT.items():  # noqa: B007
            if _mentions_slot(text, slot):
                direct.setdefault(slot, set()).add(agent_dir.name)
    # Propagate one level: a fragment that mentions $inner is read by everyone
    # who reads the outer fragment.
    for path, slot in prompts.FRAGMENT_TO_SLOT.items():
        p = ROOT / path
        if not p.is_file():
            continue
        body = p.read_text(encoding="utf-8")
        for inner_slot in set(prompts.FRAGMENT_TO_SLOT.values()):
            if _mentions_slot(body, inner_slot) and slot in direct:
                direct.setdefault(inner_slot, set()).update(direct[slot])
    return direct


def _base_of(override: Path, topo: int, variant: str) -> Path | None:
    """Repo-relative source path an override file shadows, or None."""
    rel = override.relative_to(AGENTS_DIR / f"{topo}agent_{variant}")
    suffix = f"_{topo}agents_{variant}"
    if not rel.stem.endswith(suffix):
        return None
    base_name = rel.stem[: -len(suffix)] + rel.suffix
    parts = rel.parts
    if parts[0] == "prompt_fragments":
        return (GENERIC_FRAGMENTS_DIR / Path(*parts[1:]).with_name(base_name)
                ).relative_to(ROOT)
    if parts[0] in ("dc_config", "tools_config"):
        return (DC_FRAGMENTS_DIR / rel.with_name(base_name)).relative_to(ROOT)
    # <agent>/prompt.md
    return Path("agents") / parts[0] / base_name


def expected_differing(topo: int, variant: str) -> tuple[set[str], list[str]]:
    """Agents an existing override set should change, plus per-file notes."""
    topo_dir = AGENTS_DIR / f"{topo}agent_{variant}"
    if not topo_dir.is_dir():
        return set(), []
    slot_users = _prompt_md_slot_users()
    agents_here = set(AGENTS_BY_TOPOLOGY[topo])
    expected: set[str] = set()
    lines: list[str] = []
    for f in sorted(topo_dir.rglob("*.md")):
        if f.relative_to(ROOT).as_posix() in _RUNTIME_ONLY:
            # Still must RESOLVE — a runtime-only override that the resolver
            # cannot find is as broken as any other, it just fails silently in
            # code rather than in a prompt.
            rel_name = f.name.replace(f"_{topo}agents_{variant}", "")
            sub = f.parent.relative_to(topo_dir).as_posix()
            lookup = (f"{sub}/{rel_name}" if sub != "." else rel_name)
            prompts._workflow_settings.SYSTEM_TOPOLOGY = topo
            prompts._workflow_settings.PROMPT_VARIANT = variant
            got = prompts._topology_override(lookup)
            if got is None or Path(got).resolve() != f.resolve():
                failures.append(
                    f"[REACHED] {f.relative_to(ROOT)} (runtime-only) is never "
                    f"resolved: _topology_override({lookup!r}) -> {got}"
                )
            else:
                lines.append(f"{f.name} -> (runtime-only; shadows no prompt)")
            continue
        base = _base_of(f, topo, variant)
        if base is None:
            failures.append(
                f"[NAME] {f.relative_to(ROOT)} does not end in "
                f"_{topo}agents_{variant} — the resolver will never find it"
            )
            continue
        # (1) REACHED — the shipping resolver must return this exact file.
        prompts._workflow_settings.SYSTEM_TOPOLOGY = topo
        prompts._workflow_settings.PROMPT_VARIANT = variant
        lookup = str(base)
        for prefix in ("DC_prompt_fragments/", "agents/shared/", "agents/"):
            p = lookup.replace("\\", "/")
            if p.startswith(prefix):
                lookup = p[len(prefix):]
                break
        got = prompts._topology_override(lookup)
        if got is None or Path(got).resolve() != f.resolve():
            failures.append(
                f"[REACHED] {f.relative_to(ROOT)} is never resolved: "
                f"_topology_override({lookup!r}) -> {got}"
            )
        # (2) who should move
        base_posix = base.as_posix()
        probe_base = ROOT / base
        if base_posix.endswith("/prompt.md"):
            who = {base.parts[1]}
        else:
            slot = prompts.FRAGMENT_TO_SLOT.get(base_posix)
            if slot is None:
                found = _scoped_slot_owner(base_posix)
                if found is None:
                    overlay = _overlay_owner(base_posix)
                    owner = overlay[1] if overlay else _routing_fragment_owner(base_posix)
                    if owner is None:
                        failures.append(
                            f"[UNKNOWN] {f.relative_to(ROOT)} shadows {base_posix}, "
                            "which is neither a prompt.md, a FRAGMENT_TO_SLOT entry, "
                            "a recognised per-agent scoped copy, a per-agent overlay, "
                            "nor a chain routing fragment"
                        )
                        continue
                    # An overlay DOES shadow a real shared file of its own, so
                    # the default probe_base (ROOT / base) is already correct —
                    # unlike a scoped copy, which shadows nothing.  Fall
                    # THROUGH rather than continue, so the overlay still gets
                    # its CONSUMED probe; that probe is the only thing standing
                    # between a DEAD override and a green run.
                    who = {owner}
                else:
                    scoped_slot, owner = found
                    who = {owner}
                    # A scoped copy shadows no file of its own — the text it
                    # REPLACES is whatever that agent would otherwise receive
                    # for the slot (this variant's override of it, else the
                    # shared original).  Without this, the copy gets no
                    # CONSUMED probe, and because a sibling override already
                    # moves the same agent a DEAD scoped copy would sail
                    # through REACHED and BLAST.
                    probe_base = _effective_slot_file(scoped_slot, topo, variant)
            else:
                who = set(slot_users.get(slot, set()))
        who &= agents_here
        expected |= who
        probe = _deleted_probe(probe_base, f) if probe_base else None
        if who and probe:
            consumed_probes.append((topo, variant, f.name, sorted(who), probe))
        lines.append(f"{f.name} -> {sorted(who) or '(no agent in this topology)'}")
    return expected, lines


def _deleted_probe(base_path: Path, override_path: Path) -> str | None:
    """A distinctive line the override REMOVED from its base, or None.

    Used to prove the assembly path actually READ the override.  Marker lines
    are skipped: a conditional region may be stripped by a flag filter rather
    than by the override, which would make the probe ambiguous.
    """
    if not base_path.is_file():
        return None
    over = {
        ln.strip() for ln in
        override_path.read_text(encoding="utf-8").splitlines()
    }
    cands = [
        ln.strip()
        for ln in base_path.read_text(encoding="utf-8").splitlines()
        if ln.strip() not in over
        and len(ln.strip()) >= 40
        and "<<" not in ln
        and "$" not in ln
    ]
    return max(cands, key=len) if cands else None


_SCOPED_ROOT_PREFIX = {
    "generic": "agents/shared/prompt_fragments/",
    "dc": "DC_prompt_fragments/",
}


def _scoped_slot_owner(base_posix: str) -> tuple[str, str] | None:
    """(slot, agent) for a per-agent scoped copy path, or None."""
    for slot, (root, rel) in prompts.SCOPED_FRAGMENTS.items():
        b = Path(rel)
        sub = b.parent.as_posix()
        want = _SCOPED_ROOT_PREFIX[root] + ("" if sub == "." else sub + "/")
        if not base_posix.startswith(want):
            continue
        name = base_posix[len(want):]
        if name.startswith(b.stem + "_") and name.endswith(b.suffix):
            agent = name[len(b.stem) + 1: len(name) - len(b.suffix)]
            if agent in prompts.PROMPT_MD_RUNTIME_SLOTS:
                return slot, agent
    return None


# Per-agent OVERLAY families.  Distinct from a SCOPED_FRAGMENTS copy: a scoped
# copy replaces the value of a SHARED slot and falls back to the shared file,
# whereas an overlay has its OWN slot that resolves to "" for any agent with no
# file — see ``_build_template``'s ``$database_search_per_agent`` and
# ``$blade_sections_visualizer_per_agent`` handling.  They appear in neither
# FRAGMENT_TO_SLOT nor SCOPED_FRAGMENTS, so without this table the gate cannot
# classify a variant override of one and reports [UNKNOWN].
_PER_AGENT_OVERLAYS = {
    "DC_prompt_fragments/tools_config/database_search_":
        "database_search_per_agent",
    "DC_prompt_fragments/tools_config/blade_sections_visualizer_":
        "blade_sections_visualizer_per_agent",
}


def _overlay_owner(base_posix: str) -> tuple[str, str] | None:
    """(slot, agent) for a per-agent overlay path, or None.

    The agent-name test also rejects same-prefix siblings that are NOT
    overlays — ``blade_sections_visualizer_off.md`` yields "off", which is no
    agent, so it falls through rather than being mis-attributed.
    """
    for prefix, slot in _PER_AGENT_OVERLAYS.items():
        if base_posix.startswith(prefix) and base_posix.endswith(".md"):
            agent = base_posix[len(prefix):-len(".md")]
            if agent in prompts.PROMPT_MD_RUNTIME_SLOTS:
                return slot, agent
    return None


# Chain-agent ROUTING fragments.  Deliberately absent from FRAGMENT_TO_SLOT
# because they load at WIRING time via routing._load_routing_fragment, not at
# template-build time — so the gate's build-time categories could not see them
# and any variant override of one was reported [UNKNOWN] (F69).  The owner is
# fixed by which agent passes that fragment_name at its routing_instructions()
# call site.  The HUB fragments (routing_orchestrator, routing_receptionist,
# routing_conductor_5agents) are NOT here — they are real slots, and the
# FRAGMENT_TO_SLOT branch already classifies them.
_ROUTING_FRAGMENT_AGENTS = {
    "routing_dc_input_creator_planner_first":     "dc_input_creator",
    "routing_dc_input_creator_uii_first":         "dc_input_creator",
    "routing_dc_input_inspector":                 "dc_input_inspector",
    "routing_dc_output_inspector":                "dc_output_inspector",
    "routing_planner_planner_first":              "planner",
    "routing_planner_uii_first":                  "planner",
    "routing_tool_caller":                        "tool_caller",
    "routing_user_input_inspector_planner_first": "user_input_inspector",
    "routing_user_input_inspector_uii_first":     "user_input_inspector",
}


def _routing_fragment_owner(base_posix: str) -> str | None:
    """Agent that loads this chain routing fragment, or None."""
    if not base_posix.startswith("agents/shared/prompt_fragments/routing_"):
        return None
    return _ROUTING_FRAGMENT_AGENTS.get(Path(base_posix).stem)


def _check_routing_table() -> list:
    """Every routing_*.md must be classifiable: hub ones via FRAGMENT_TO_SLOT,
    chain ones via _ROUTING_FRAGMENT_AGENTS.  Without this the table silently
    goes stale the moment a routing fragment is added or renamed, and the gate
    quietly returns to reporting [UNKNOWN] for a legitimate override."""
    problems = []
    for frag in sorted(GENERIC_FRAGMENTS_DIR.glob("routing_*.md")):
        rel = frag.relative_to(ROOT).as_posix()
        if rel in prompts.FRAGMENT_TO_SLOT or frag.stem in _ROUTING_FRAGMENT_AGENTS:
            continue
        problems.append(
            f"[ROUTING TABLE] {rel} is in neither FRAGMENT_TO_SLOT nor "
            "_ROUTING_FRAGMENT_AGENTS — a variant override of it would be "
            "reported [UNKNOWN] (F69)"
        )
    return problems


def _effective_slot_file(slot: str, topo: int, variant: str) -> Path | None:
    """The file an agent WITHOUT a scoped copy receives for *slot*.

    This variant's override of the shared fragment when one exists, else the
    shared original — i.e. exactly what the scoped copy is displacing.
    """
    root, rel = prompts.SCOPED_FRAGMENTS[slot]
    prompts._workflow_settings.SYSTEM_TOPOLOGY = topo
    prompts._workflow_settings.PROMPT_VARIANT = variant
    lookup = f"prompt_fragments/{rel}" if root == "generic" else rel
    override = prompts._topology_override(lookup)
    if override is not None:
        return Path(override)
    shared = (GENERIC_FRAGMENTS_DIR if root == "generic"
              else DC_FRAGMENTS_DIR) / rel
    return shared if shared.is_file() else None


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

for variant in VARIANTS:
    for topo in (7, 5, 3):
        exp, lines = expected_differing(topo, variant)
        has_dir = (AGENTS_DIR / f"{topo}agent_{variant}").is_dir()
        for pf in (False, True):
            actual: set[str] = set()
            skipped: list[str] = []
            for agent in AGENTS_BY_TOPOLOGY[topo]:
                std = assemble(topo, pf, "standard", agent)
                red = assemble(topo, pf, variant, agent)
                if std[0] in ("MISSING", "ERROR"):
                    # Not assemblable under EITHER variant is a pre-existing
                    # state (topology 3 ships no prompt.md yet), not a variant
                    # defect.  Only flag a DIVERGENCE.
                    if std != red:
                        failures.append(
                            f"[ASSEMBLE] topo{topo} pf={pf} {agent}: standard "
                            f"{std} but {variant} {red}"
                        )
                    skipped.append(agent)
                    continue
                if std != red:
                    actual.add(agent)
            if skipped:
                notes.append(
                    f"topology {topo}: {len(skipped)} prompt(s) not assemblable "
                    f"under either variant, skipped ({', '.join(skipped)})"
                )
            # (3) INERT — no variant directory means no difference at all.
            if not has_dir and actual:
                failures.append(
                    f"[INERT] topology {topo} has no {topo}agent_{variant}/ "
                    f"directory yet these prompts differ between variants: "
                    f"{sorted(actual)}"
                )
            # (2) BLAST RADIUS
            if actual != exp:
                leaked = sorted(actual - exp)
                missed = sorted(exp - actual)
                detail = []
                if leaked:
                    detail.append(f"changed but should NOT have: {leaked}")
                if missed:
                    detail.append(f"should have changed but did NOT: {missed}")
                failures.append(
                    f"[BLAST] topo{topo} pf={pf} variant={variant} — "
                    + "; ".join(detail)
                )
        if has_dir:
            notes.append(
                f"topology {topo} / {variant}: {len(lines)} override(s), "
                f"expected to move {sorted(exp)}"
            )
            for ln in lines:
                notes.append(f"    {ln}")

# (5) ROUTING — the generated block is a RUNTIME slot, not part of _build_template.
#
# prompts._build_template leaves "{routing_instructions}" unfilled, so checks
# (1)-(4) above are blind to agents/shared/routing.py and to any variant fork of
# it — roughly 4,700 chars, ~10% of an assembled chain-agent prompt, and the
# place where the generated duplication lives (F60).  Without this case the
# reduced routing fork would be entirely untested.
#
# Same blast-radius rule as (2): the fork exists only for topology 7, so
# topologies 5 and 3 must be byte-identical across variants.
_ROUTING_PROBE = ("User Input Inspector", "Planner", None,
                  "routing_user_input_inspector_uii_first.md")
for variant in VARIANTS:
    fork = ROOT / "reduced7" / "agents" / "shared" / "routing.py"
    for topo in (7, 5, 3):
        out = {}
        for v in ("standard", variant):
            prompts._workflow_settings.SYSTEM_TOPOLOGY = topo
            prompts._workflow_settings.PROMPT_VARIANT = v
            try:
                out[v] = prompts.routing_instructions(*_ROUTING_PROBE)
            except Exception as exc:  # noqa: BLE001
                out[v] = f"ERROR:{type(exc).__name__}:{exc}"
        differs = out["standard"] != out[variant]
        if topo == 7:
            if fork.is_file() and not differs:
                failures.append(
                    f"[ROUTING] {fork.relative_to(ROOT)} exists but topology 7 "
                    f"produces an IDENTICAL routing block under variant "
                    f"'{variant}' — the selector in prompts.routing_instructions "
                    "is not reaching the fork"
                )
            if not fork.is_file() and differs:
                failures.append(
                    "[ROUTING] no reduced7 routing fork on disk, yet the "
                    f"topology-7 routing block differs under '{variant}'"
                )
        elif differs:
            failures.append(
                f"[ROUTING] topology {topo} has no routing fork, yet its "
                f"routing block differs between standard and '{variant}' — "
                "the variant selector is leaking across topologies"
            )
    if fork.is_file():
        notes.append(
            f"routing fork active for topology 7 / {variant}; topologies 5 and 3 "
            "byte-identical across variants"
        )


# (4) CONSUMED — text each override deleted must be gone from the assembly.
for topo, variant, fname, who, probe in consumed_probes:
    for agent in who:
        prompts._workflow_settings.SYSTEM_TOPOLOGY = topo
        prompts._workflow_settings.PROMPT_VARIANT = variant
        prompts.PLANNER_FIRST = False
        try:
            text = prompts._build_template(agent)
        except Exception:  # noqa: BLE001
            continue
        if probe in text:
            failures.append(
                f"[CONSUMED] topo{topo} {agent}: {fname} deletes "
                f"{probe[:60]!r}… but it is still in the assembled prompt — "
                "the override resolves but is not being read"
            )
if consumed_probes:
    notes.append(
        f"consumed-probe checks: {sum(len(w) for _, _, _, w, _ in consumed_probes)} "
        f"(agent x override) pairs"
    )

# ---------------------------------------------------------------------------
# The routing-fragment table must stay complete, or the [UNKNOWN] classifier
# silently regresses to F69 the next time a routing fragment is added.
_routing_table_problems = _check_routing_table()
failures.extend(_routing_table_problems)
notes.append(
    "routing-fragment table: %d chain fragment(s) classifiable, %d problem(s)"
    % (len(_ROUTING_FRAGMENT_AGENTS), len(_routing_table_problems))
)

print("PROMPT_VARIANT resolution summary")
for n in notes:
    print(f"  {n}")
print()

if failures:
    print(f"FAIL — {len(failures)} problem(s):\n")
    for f in failures:
        print(f"  {f}")
    sys.exit(1)
print("PASS — every variant override is reached, the blast radius matches the "
      "files on disk exactly, and topologies without a variant directory are "
      "byte-identical across variants.")
