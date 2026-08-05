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
            if f"${slot}" in text:
                direct.setdefault(slot, set()).add(agent_dir.name)
    # Propagate one level: a fragment that mentions $inner is read by everyone
    # who reads the outer fragment.
    for path, slot in prompts.FRAGMENT_TO_SLOT.items():
        p = ROOT / path
        if not p.is_file():
            continue
        body = p.read_text(encoding="utf-8")
        for inner_slot in set(prompts.FRAGMENT_TO_SLOT.values()):
            if f"${inner_slot}" in body and slot in direct:
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
        if base_posix.endswith("/prompt.md"):
            who = {base.parts[1]}
        else:
            slot = prompts.FRAGMENT_TO_SLOT.get(base_posix)
            if slot is None:
                owner = _scoped_owner_of(base_posix)
                if owner is None:
                    failures.append(
                        f"[UNKNOWN] {f.relative_to(ROOT)} shadows {base_posix}, "
                        "which is neither a prompt.md, a FRAGMENT_TO_SLOT entry, "
                        "nor a recognised per-agent scoped copy"
                    )
                    continue
                who = {owner}
            else:
                who = set(slot_users.get(slot, set()))
        who &= agents_here
        expected |= who
        probe = _deleted_probe(ROOT / base, f)
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


def _scoped_owner_of(base_posix: str) -> str | None:
    """Agent owning a per-agent scoped copy path, or None."""
    roots = {
        "generic": "agents/shared/prompt_fragments/",
        "dc": "DC_prompt_fragments/",
    }
    for slot, (root, rel) in prompts.SCOPED_FRAGMENTS.items():  # noqa: B007
        b = Path(rel)
        sub = b.parent.as_posix()
        want = roots[root] + ("" if sub == "." else sub + "/")
        if not base_posix.startswith(want):
            continue
        name = base_posix[len(want):]
        if name.startswith(b.stem + "_") and name.endswith(b.suffix):
            agent = name[len(b.stem) + 1: len(name) - len(b.suffix)]
            if agent in prompts.PROMPT_MD_RUNTIME_SLOTS:
                return agent
    return None


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
