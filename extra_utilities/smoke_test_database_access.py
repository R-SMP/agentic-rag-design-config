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


# A LEGACY flat ``{agent: bool}`` store, as written before per-tool flags
# landed.  Kept only as a fixture for case 8: such a file predates profiles
# and is read as the "7" profile.
_LEGACY_FLAT = {
    "dc_input_creator":     True,
    "dc_input_inspector":   True,
    "dc_output_inspector":  True,
    "orchestrator":         False,
    "planner":              True,
    "receptionist":         True,
    "tool_caller":          False,
    "user_input_inspector": True,
}

# The owner's decided distribution for the 7-agent system.
_EXPECTED = {
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
    """Temporarily force RAG_ENABLED / SYSTEM_TOPOLOGY."""

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

# --- 1. the '7' profile matches the decided table ----------------------
#
# There used to be a case here asserting that profile "7" reproduced the
# pre-per-tool-flags behaviour byte for byte.  That guarantee was given up
# deliberately: when the reduced prompts were promoted to BE the 7-agent
# system, its narrower distribution was promoted with them and the old
# all-on row was discarded.  Asserting the old values now would assert the
# promotion had not happened.
print("case 1 - profile '7' matches the decided distribution")
with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7):
    bad = []
    for agent, (s_, u_, a_) in _EXPECTED.items():
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
    with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=topo):
        allon = all(
            all(da.get_tools(a).values()) for a in da.DEFAULT_AGENTS
        )
        check("topology %d: every agent holds every tool" % topo, allon)

# --- 4. profile_key mapping -------------------------------------------
print("case 4 - profile_key()")
for topo, want in [(7, "7"), (5, "5"), (3, "3")]:
    with _Settings(SYSTEM_TOPOLOGY=topo):
        got = da.profile_key()
        check("topology %s -> %r" % (topo, want), got == want, got)

# --- 5. tool=None is the OR of the three ------------------------------
print("case 5 - tool=None collapses to 'holds any tool'")
with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7):
    wrong = [
        a for a in da.DEFAULT_AGENTS
        if da.is_enabled_for(a) != any(da.get_tools(a).values())
    ]
    check("OR holds for all agents", not wrong, wrong)
    wrong2 = [
        a for a in da.DEFAULT_AGENTS
        if da.get_all()[a] != any(da.get_all_tools()[a].values())
    ]
    check("get_all() is the collapsed get_all_tools()", not wrong2, wrong2)

# --- 6. the master switch still dominates ------------------------------
print("case 6 - RAG_ENABLED=False forces everything False")
with _Settings(RAG_ENABLED=False, SYSTEM_TOPOLOGY=7):
    any_on = any(
        da.is_enabled_for(a, t)
        for a in da.DEFAULT_AGENTS for t in da.TOOLS
    ) or any(da.is_enabled_for(a) for a in da.DEFAULT_AGENTS)
    check("nothing is enabled", not any_on)
    check("stored state still readable (get is unmasked)",
          da.get("dc_input_inspector", "search") is True)

print()
print("=" * 68)
print("PART B - temp store files")
print("=" * 68)

# --- 7. set_one touches exactly one cell -------------------------------
print("case 7 - set_one writes one cell and nothing else")
# The second profile is "5" — profile isolation is per TOPOLOGY now that
# the variant dimension is gone, and a write under topology 7 must not
# reach it.
seed = {
    "7": {a: {t: True for t in da.TOOLS} for a in da.DEFAULT_AGENTS},
    "5": {a: {t: True for t in da.TOOLS} for a in da.DEFAULT_AGENTS},
}
with _StoreFile(seed) as path:
    with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7):
        da.set_one("planner", "attempt", False)
        after = json.loads(path.read_text(encoding="utf-8"))
    check("target cell flipped",
          after["7"]["planner"]["attempt"] is False)
    others = [
        (a, t) for a in da.DEFAULT_AGENTS for t in da.TOOLS
        if not (a == "planner" and t == "attempt")
        and after["7"][a][t] is not True
    ]
    check("the other 35 cells in that profile are untouched",
          not others, others)
    check("the OTHER profile is untouched",
          all(all(v.values()) for v in after["5"].values()))

# --- 8. legacy flat file, and a malformed one --------------------------
print("case 8 - legacy flat file and malformed file")
with _StoreFile(_LEGACY_FLAT):
    with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7):
        wrong = [
            a for a in _LEGACY_FLAT
            if any(v != _LEGACY_FLAT[a]
                   for v in da.get_tools(a).values())
        ]
        check("flat file is read as the '7' profile", not wrong, wrong)
    with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=5):
        check("a flat file does NOT leak into another topology's profile",
              all(all(da.get_tools(a).values()) for a in da.DEFAULT_AGENTS))

with _StoreFile(None, raw="{ this is not json"):
    with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7):
        check("malformed file falls back to defaults, does not raise",
              all(all(da.get_tools(a).values()) for a in da.DEFAULT_AGENTS))

with _StoreFile(None):   # no file at all
    with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7):
        check("missing file falls back to defaults",
              all(all(da.get_tools(a).values()) for a in da.DEFAULT_AGENTS))

# --- 9. unknown agent / tool ------------------------------------------
print("case 9 - unknown names")
with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7):
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

# --- 10. dba_tools_for() binds exactly the profile's tools -------------
print("case 10 - agents/shared/dba_tools.py returns the right tool set")
# The module imports the three factories, which import langchain, so it
# cannot be imported here.  ast-extract the function and run the REAL body
# against stub factories instead.
import ast                                                    # noqa: E402

_helper_src = (ROOT / "agents" / "shared" / "dba_tools.py").read_text(
    encoding="utf-8")
_fn = next(
    (n for n in ast.parse(_helper_src).body
     if isinstance(n, ast.FunctionDef) and n.name == "dba_tools_for"),
    None,
)
check("dba_tools_for is extractable", _fn is not None)

if _fn is not None:
    class _Stub:
        def __init__(self, name):
            self.name = name

    _g = {
        "database_access": da,
        "_FACTORIES": (
            ("search",      lambda a: _Stub("database_search")),
            ("user_inputs", lambda a: _Stub("retrieve_user_inputs")),
            ("attempt",     lambda a: _Stub("retrieve_attempt")),
        ),
    }
    exec(compile(ast.get_source_segment(_helper_src, _fn),
                 "<dba_tools>", "exec"), _g)
    dba_tools_for = _g["dba_tools_for"]

    _NAME = {"search": "database_search",
             "user_inputs": "retrieve_user_inputs",
             "attempt": "retrieve_attempt"}

    with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7):
        bad = []
        for agent, (s_, u_, a_) in _EXPECTED.items():
            want = [_NAME[k] for k, on in
                    (("search", s_), ("user_inputs", u_), ("attempt", a_)) if on]
            got = [t.name for t in dba_tools_for(agent)]
            if got != want:
                bad.append((agent, want, got))
        check("every agent binds exactly its row", not bad, bad)
        check("Receptionist binds NOTHING",
              dba_tools_for("receptionist") == [])
        check("DCIC binds search + attempt, no user_inputs",
              [t.name for t in dba_tools_for("dc_input_creator")]
              == ["database_search", "retrieve_attempt"])
        check("Planner binds search only",
              [t.name for t in dba_tools_for("planner")]
              == ["database_search"])
        check("a fully-enabled agent binds all three",
              [t.name for t in dba_tools_for("dc_input_inspector")]
              == ["database_search", "retrieve_user_inputs",
                  "retrieve_attempt"])
        check("a disabled agent binds nothing",
              dba_tools_for("tool_caller") == [])

    with _Settings(RAG_ENABLED=False, SYSTEM_TOPOLOGY=7):
        check("master switch off -> every agent binds nothing",
              all(dba_tools_for(a) == [] for a in da.DEFAULT_AGENTS))

# --- 11. the assembled prompt drops sections for tools not held --------
print("case 11 - prompt slots blank for tools the agent does not hold")
# agents/__init__ eagerly imports every agent class, and langchain_core is
# absent here, so stub both the package and the one symbol prompts.py needs
# -- the same preamble smoke_test_topology_fragments uses.
import types                                                   # noqa: E402

for _n, _r in (("agents", "agents"), ("agents.shared", "agents/shared")):
    _m = types.ModuleType(_n)
    _m.__path__ = [str(ROOT / _r)]
    sys.modules.setdefault(_n, _m)
_lc = types.ModuleType("langchain_core")
_lc.__path__ = []
_lct = types.ModuleType("langchain_core.tools")


class _StubStructuredTool:
    @staticmethod
    def from_function(*a, **k):
        return None


_lct.StructuredTool = _StubStructuredTool
sys.modules.setdefault("langchain_core", _lc)
sys.modules.setdefault("langchain_core.tools", _lct)

from agents.shared import prompts as _prompts                  # noqa: E402

_SEARCH_MARK = "database_search`` runs a semantic"
_RETRIEVE_MARK = "Retrieving past saved content"


def _probe(agent: str) -> tuple[bool, bool]:
    flat = " ".join(_prompts._build_template(agent).split())
    return (_SEARCH_MARK in flat, _RETRIEVE_MARK in flat)


with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7):
    # Planner holds search ONLY, so the retrieve fragment must go.
    check("Planner keeps search, loses the retrieve section",
          _probe("planner") == (True, False), _probe("planner"))
    # Receptionist holds nothing -> <<HAS_DBA>> strips both.
    check("Receptionist loses both sections",
          _probe("receptionist") == (False, False), _probe("receptionist"))
    # holding EITHER retrieve tool keeps the shared fragment, which covers
    # both of them: UII has user_inputs, DCIC and DCOI have attempt.
    for _a in ("user_input_inspector", "dc_input_creator",
               "dc_output_inspector", "dc_input_inspector"):
        check("%s keeps both sections" % _a,
              _probe(_a) == (True, True), _probe(_a))

# --- 12. reduced-scoped per-agent fragments -----------------------------
print("case 12 - no agent is pointed at a retrieval tool it does not hold")
# The shared per-agent DBa fragments used to point the UII at
# retrieve_attempt and the DCOI at retrieve_user_inputs.  That was correct
# only while every agent held all three.  Scoped per-agent overrides fixed
# it, and those overrides are now the shared text itself.
#
# This case used to assert the CONTRAST between the two variants: the
# "standard" prompts still carry the sentence, the "reduced" ones do not.
# There is one system now, so that half asserted the promotion had failed.
# What is worth pinning is the half that protects the fleet -- an agent is
# not pointed at a tool it lacks -- which is what remains below, and which
# case 13 re-proves as a property.
_UII_ATTEMPT = "Likewise ``retrieve_attempt(...)`` when"
_DCOI_INPUTS = "how past users' inputs looked"


def _assembled(agent: str) -> str:
    return " ".join(_prompts._build_template(agent).split())


with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7):
    check("UII is NOT told to use retrieve_attempt (it holds "
          "search + user_inputs only)",
          _UII_ATTEMPT not in _assembled("user_input_inspector"))
    check("DCOI is NOT told to fetch past user inputs (it holds "
          "search + attempt only)",
          _DCOI_INPUTS not in _assembled("dc_output_inspector"))
    # the rework must not have dropped anything else
    for _mark, _who in (
        ("MANDATORY on at least one in-scope session", "user_input_inspector"),
        ("side_by_side=True", "dc_output_inspector"),
    ):
        check("%s keeps '%s'" % (_who, _mark[:34]),
              _mark in _assembled(_who))

# --- 13. THE INVARIANT --------------------------------------------------
print("case 13 - an agent only ever reads about tools it HOLDS")
# The point of everything above.  Cases 11 and 12 check named sections and
# specific sentences; this one is the property itself, so it keeps holding
# when the fragments are reworded again.
#
# Both shared fragments used to name a fixed pair of retrieve tools --
# database_search.md in its blueprint / fetch-the-pixels / available_attempts
# paragraphs, and retrieve_user_inputs.md in its opener -- which no override
# could fix, because the correct text differs per agent.  They now refer to
# "whichever retrieval tools you hold" instead, which is true in every
# profile.  A side benefit: naming no argument means no argument to go stale.
def _invariant_violations() -> list:
    out = []
    for _a in da.DEFAULT_AGENTS:
        try:
            _flat = " ".join(_prompts._build_template(_a).split())
        except Exception:
            continue              # not every slug has a prompt in topology 7
        _t = da.get_tools(_a)
        if _flat.count("retrieve_user_inputs") and not _t["user_inputs"]:
            out.append((_a, "reads retrieve_user_inputs"))
        if _flat.count("retrieve_attempt") and not _t["attempt"]:
            out.append((_a, "reads retrieve_attempt"))
    return out


with _Settings(RAG_ENABLED=True, SYSTEM_TOPOLOGY=7):
    # HARD, with no allowance.  This used to exempt the Orchestrator: its
    # worked example scripted the hub to say "Call database_search (and/or
    # retrieve_user_inputs / retrieve_attempt)" OUTSIDE <<HAS_DBA>>, so the
    # sentence survived for a hub holding nothing (F89).  The prompts that
    # were promoted to BE the 7-agent system had already deleted it, so the
    # exemption is gone and any violation is now a failure.
    check("no agent is told about a tool it does not hold",
          not _invariant_violations(), _invariant_violations())

print()
if _FAILS:
    print("FAIL - %d assertion(s): %s" % (len(_FAILS), _FAILS))
    sys.exit(1)
print("PASS - the DBa store resolves per (profile, agent, tool); profile '7' "
      "matches the decided table and undecided profiles fall back to all-on.")
