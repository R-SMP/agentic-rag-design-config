# -*- coding: utf-8 -*-
"""Offline smoke test for the per-(profile, agent, tool) DBa store.

No database, no LLM, no network.  Two halves:

* Part A runs against the REAL shipped ``database_access.json``, so the
  committed distribution is what gets checked.
* Part B points ``_PATH`` at temp files to exercise round-trips, a legacy
  flat file, and a malformed one.

The headline assertion is Part A case 1: for every agent, the standard
7-agent profile must resolve EXACTLY as it did before profiles existed.
The pre-change values are embedded as a literal below, so that is proven
against a fixed reference rather than against the code's own defaults.

Run:  py extra_utilities/smoke_test_database_access.py
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

from workflow_settings import database_access as da          # noqa: E402
from workflow_settings import settings as st                 # noqa: E402


# The state of database_access.json IMMEDIATELY BEFORE per-tool flags
# landed.  Agents absent from that file fell back to _DEFAULT_VALUE=True.
_PRE_CHANGE_FLAT = {
    "dc_input_creator":     True,
    "dc_input_inspector":   True,
    "dc_output_inspector":  True,
    "orchestrator":         False,
    "planner":              True,
    "receptionist":         True,
    "tool_caller":          False,
    "user_input_inspector": True,
}

# The owner's decided distribution for the reduced 7-agent system.
_REDUCED_EXPECTED = {
    "receptionist":         (False, False, False),
    "orchestrator":         (False, False, False),
    "planner":              (True,  False, False),
    "user_input_inspector": (True,  True,  False),
    "dc_input_creator":     (True,  False, True),
    "dc_input_inspector":   (True,  True,  True),
    "dc_output_inspector":  (True,  False, True),
    "tool_caller":          (False, False, False),
}

_FAILS: list[str] = []


def check(name: str, cond: bool, detail: object = "") -> None:
    print(("  PASS  " if cond else "  FAIL  ") + name
          + ("" if cond else "\n          -> " + str(detail)[:400]))
    if not cond:
        _FAILS.append(name)


class _Settings:
    """Temporarily force RAG_ENABLED / SYSTEM_TOPOLOGY / PROMPT_VARIANT."""

    def __init__(self, **kw):
        self.kw = kw
        self.old = {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.old[k] = getattr(st, k, None)
            setattr(st, k, v)
        return self

    def __exit__(self, *exc):
        for k, v in self.old.items():
            if v is None:
                try:
                    delattr(st, k)
                except AttributeError:
                    pass
            else:
                setattr(st, k, v)
        return False


class _StoreFile:
    """Temporarily point da._PATH at a temp file holding *payload*."""

    def __init__(self, payload, raw: str | None = None):
        self.payload, self.raw = payload, raw

    def __enter__(self):
        self.dir = tempfile.TemporaryDirectory()
        p = Path(self.dir.name) / "database_access.json"
        if self.raw is not None:
            p.write_text(self.raw, encoding="utf-8")
        elif self.payload is not None:
            p.write_text(json.dumps(self.payload), encoding="utf-8")
        self.old, da._PATH = da._PATH, p
        return p

    def __exit__(self, *exc):
        da._PATH = self.old
        self.dir.cleanup()
        return False


print("=" * 68)
print("PART A - against the real shipped database_access.json")
print("=" * 68)

# --- 1. standard 7 resolves exactly as it did before profiles ----------
print("case 1 - profile '7' is byte-for-byte the pre-change behaviour")
with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7, PROMPT_VARIANT="standard"):
    mismatches = []
    for agent in da.DEFAULT_AGENTS:
        want = _PRE_CHANGE_FLAT.get(agent, True)   # absent -> default True
        got_any = da.is_enabled_for(agent)
        tools = da.get_tools(agent)
        if got_any != want or any(v != want for v in tools.values()):
            mismatches.append((agent, want, got_any, tools))
    check("all %d agents match the pre-change values"
          % len(da.DEFAULT_AGENTS), not mismatches, mismatches)

# --- 2. the reduced profile matches the decided table ------------------
print("case 2 - profile '7-reduced' matches the decided distribution")
with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7, PROMPT_VARIANT="reduced"):
    bad = []
    for agent, (s_, u_, a_) in _REDUCED_EXPECTED.items():
        t = da.get_tools(agent)
        if (t["search"], t["user_inputs"], t["attempt"]) != (s_, u_, a_):
            bad.append((agent, (s_, u_, a_), t))
    check("all 24 cells match", not bad, bad)
    check("Receptionist / Orchestrator / Tool Caller hold NOTHING",
          not any(da.is_enabled_for(a) for a in
                  ("receptionist", "orchestrator", "tool_caller")))
    check("DCIC has attempt but NOT user_inputs",
          da.is_enabled_for("dc_input_creator", "attempt")
          and not da.is_enabled_for("dc_input_creator", "user_inputs"))
    check("Planner has search ONLY",
          da.is_enabled_for("planner", "search")
          and not da.is_enabled_for("planner", "user_inputs")
          and not da.is_enabled_for("planner", "attempt"))

# --- 3. an ABSENT profile falls back to today's all-on behaviour -------
print("case 3 - profiles '5' and '3' are absent -> all-on fallback")
for topo in (5, 3):
    with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=topo,
                   PROMPT_VARIANT="standard"):
        allon = all(
            all(da.get_tools(a).values()) for a in da.DEFAULT_AGENTS
        )
        check("topology %d: every agent holds every tool" % topo, allon)

# --- 4. profile_key mapping -------------------------------------------
print("case 4 - profile_key()")
cases = [
    (7, "standard", "7"), (7, "reduced", "7-reduced"),
    (5, "standard", "5"), (3, "reduced", "3-reduced"),
    (7, "", "7"), (7, "  ", "7"),
]
for topo, variant, want in cases:
    with _Settings(SYSTEM_TOPOLOGY=topo, PROMPT_VARIANT=variant):
        got = da.profile_key()
        check("(%s, %r) -> %r" % (topo, variant, want), got == want, got)

# --- 5. tool=None is the OR of the three ------------------------------
print("case 5 - tool=None collapses to 'holds any tool'")
for variant in ("standard", "reduced"):
    with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7,
                   PROMPT_VARIANT=variant):
        wrong = [
            a for a in da.DEFAULT_AGENTS
            if da.is_enabled_for(a) != any(da.get_tools(a).values())
        ]
        check("%s: OR holds for all agents" % variant, not wrong, wrong)
        wrong2 = [
            a for a in da.DEFAULT_AGENTS
            if da.get_all()[a] != any(da.get_all_tools()[a].values())
        ]
        check("%s: get_all() is the collapsed get_all_tools()" % variant,
              not wrong2, wrong2)

# --- 6. the master switch still dominates ------------------------------
print("case 6 - RAG_ENABLED=False forces everything False")
for variant in ("standard", "reduced"):
    with _Settings(RAG_ENABLED=False, SYSTEM_TOPOLOGY=7,
                   PROMPT_VARIANT=variant):
        any_on = any(
            da.is_enabled_for(a, t)
            for a in da.DEFAULT_AGENTS for t in da.TOOLS
        ) or any(da.is_enabled_for(a) for a in da.DEFAULT_AGENTS)
        check("%s: nothing is enabled" % variant, not any_on)
        check("%s: stored state still readable (get is unmasked)" % variant,
              da.get("dc_input_inspector", "search") is True)

print()
print("=" * 68)
print("PART B - temp store files")
print("=" * 68)

# --- 7. set_one touches exactly one cell -------------------------------
print("case 7 - set_one writes one cell and nothing else")
seed = {
    "7":         {a: {t: True for t in da.TOOLS} for a in da.DEFAULT_AGENTS},
    "7-reduced": {a: {t: True for t in da.TOOLS} for a in da.DEFAULT_AGENTS},
}
with _StoreFile(seed) as path:
    with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7,
                   PROMPT_VARIANT="reduced"):
        da.set_one("planner", "attempt", False)
        after = json.loads(path.read_text(encoding="utf-8"))
    check("target cell flipped",
          after["7-reduced"]["planner"]["attempt"] is False)
    others = [
        (a, t) for a in da.DEFAULT_AGENTS for t in da.TOOLS
        if not (a == "planner" and t == "attempt")
        and after["7-reduced"][a][t] is not True
    ]
    check("the other 35 cells in that profile are untouched",
          not others, others)
    check("the OTHER profile is untouched",
          all(all(v.values()) for v in after["7"].values()))

# --- 8. legacy flat file, and a malformed one --------------------------
print("case 8 - legacy flat file and malformed file")
with _StoreFile(_PRE_CHANGE_FLAT):
    with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7,
                   PROMPT_VARIANT="standard"):
        wrong = [
            a for a in _PRE_CHANGE_FLAT
            if any(v != _PRE_CHANGE_FLAT[a]
                   for v in da.get_tools(a).values())
        ]
        check("flat file is read as the '7' profile", not wrong, wrong)
    with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7,
                   PROMPT_VARIANT="reduced"):
        check("a flat file does NOT leak into '7-reduced'",
              all(all(da.get_tools(a).values()) for a in da.DEFAULT_AGENTS))

with _StoreFile(None, raw="{ this is not json"):
    with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7,
                   PROMPT_VARIANT="standard"):
        check("malformed file falls back to defaults, does not raise",
              all(all(da.get_tools(a).values()) for a in da.DEFAULT_AGENTS))

with _StoreFile(None):   # no file at all
    with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7,
                   PROMPT_VARIANT="standard"):
        check("missing file falls back to defaults",
              all(all(da.get_tools(a).values()) for a in da.DEFAULT_AGENTS))

# --- 9. unknown agent / tool ------------------------------------------
print("case 9 - unknown names")
with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7, PROMPT_VARIANT="reduced"):
    check("unknown agent -> False", da.is_enabled_for("nope") is False)
    check("unknown tool -> False",
          da.is_enabled_for("planner", "nope") is False)
for bad_call, label in (
    (lambda: da.set_one("nope", "search", True), "set_one unknown agent"),
    (lambda: da.set_one("planner", "nope", True), "set_one unknown tool"),
):
    try:
        bad_call()
        check(label + " raises ValueError", False, "did not raise")
    except ValueError:
        check(label + " raises ValueError", True)
    except Exception as exc:
        check(label + " raises ValueError", False, repr(exc))

print()
if _FAILS:
    print("FAIL - %d assertion(s): %s" % (len(_FAILS), _FAILS))
    sys.exit(1)
print("PASS - the DBa store resolves per (profile, agent, tool); standard 7 "
      "is unchanged and undecided profiles fall back to all-on.")
