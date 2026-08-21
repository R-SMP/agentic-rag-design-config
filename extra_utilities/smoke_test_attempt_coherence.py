"""An attempt's mesh must come from that attempt's own parameters.json.

Since the tool takes the RECORD'S PATH instead of sixteen values, that is
enforced by construction rather than checked: there is no way to hand it a
number that disagrees with the record.  This test therefore proves three
things.

CONTRACT   the tool reads the record and builds from it; a missing,
           malformed or incomplete record fails CLEANLY, names what is wrong,
           and builds nothing.
DORMANT    F75's comparison helper still behaves, tested directly.  It is
           unreachable through the tool now, and is kept precisely so a
           regression that reintroduces value-passing is still caught.
F75b       a mesh records the values that produced it, so a later
           write_parameters cannot label it with numbers it did not come
           from; folders without a sidecar proceed untouched.

Fully offline — the geometry backend and the render step are stubbed, so no
RhinoCompute, no FEG, no Node, no PNGs.

    py extra_utilities/smoke_test_attempt_coherence.py
"""
import json
import shutil
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ``tools/__init__.py`` pulls in langchain_core, which is not installed in the
# bare worktree.  Stub the ``@tool`` decorator FUNCTIONALLY — the object it
# returns must still expose ``.invoke(args_dict)`` — so the real tool body runs
# here.  smoke_test_generate_mesh.py imports for real and therefore only runs in
# a full environment; a guard test that cannot be executed proves nothing, hence
# the stub.
#
# DELIBERATE LIMITATION: this bypasses langchain's args_schema coercion, so the
# test never sees a string "68.0" arriving where a float is declared.  That path
# is covered by the defensive isinstance branch in _param_mismatches, which
# degrades to "proceed" — today's behaviour — rather than to a false refusal.
try:
    import langchain_core.tools as _probe
    assert _probe is not None
except ModuleNotFoundError:                                  # pragma: no cover
    class _StubTool:
        def __init__(self, fn):
            self._fn = fn
            self.name = getattr(fn, "__name__", "tool")
            self.description = (fn.__doc__ or "")

        def invoke(self, args):
            return self._fn(**args)

    def _stub_tool_decorator(*a, **k):
        if len(a) == 1 and callable(a[0]) and not k:
            return _StubTool(a[0])
        return lambda fn: _StubTool(fn)

    _lc = types.ModuleType("langchain_core"); _lc.__path__ = []
    _lct = types.ModuleType("langchain_core.tools")
    _lct.tool = _stub_tool_decorator
    _lct.StructuredTool = _StubTool
    sys.modules["langchain_core"] = _lc
    sys.modules["langchain_core.tools"] = _lct

# ``agents/__init__.py`` eagerly imports every agent class (and so
# langchain_core.messages).  Register ``agents`` / ``agents.shared`` as
# namespace packages so submodule imports resolve WITHOUT running it — the same
# device smoke_test_topology_fragments uses.
# ``tools/__init__.py`` imports every tool eagerly, dragging in trimesh and
# pyvista.  Same device: make ``tools`` a namespace package so
# tools.generate_mesh.generate_mesh imports on its own.
for _name, _rel in (
    ("agents", "agents"), ("agents.shared", "agents/shared"),
    ("tools", "tools"), ("tools.generate_mesh", "tools/generate_mesh"),
):
    if _name not in sys.modules:
        _m = types.ModuleType(_name)
        _m.__path__ = [str(ROOT / _rel)]
        sys.modules[_name] = _m

# generate_mesh.py's own third-party imports.  None is exercised by this test:
# the RhinoCompute/FEG backend is replaced by a stub below, so nothing here is
# ever called — these exist only so the module body can execute.
def _stub_module(name, **attrs):
    if name in sys.modules:
        return
    m = types.ModuleType(name)
    m.__path__ = []
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m


for _dep in ("numpy", "DracoPy"):
    try:
        __import__(_dep)
    except ModuleNotFoundError:                              # pragma: no cover
        _stub_module(_dep)

try:
    import compute_rhino3d.Util as _probe
    assert _probe is not None
except ModuleNotFoundError:                                  # pragma: no cover
    _stub_module("compute_rhino3d")
    _stub_module("compute_rhino3d.Util", url=None, apiKey=None)
    _stub_module("compute_rhino3d.Grasshopper", EvaluateDefinition=None)
    sys.modules["compute_rhino3d"].Util = sys.modules["compute_rhino3d.Util"]
    sys.modules["compute_rhino3d"].Grasshopper = sys.modules["compute_rhino3d.Grasshopper"]

try:
    from agents.shared.agent_activity import tool_active as _probe
    assert _probe is not None
except (ModuleNotFoundError, ImportError):                   # pragma: no cover
    _stub_module("agents.shared.agent_activity",
                 tool_active=lambda *a, **k: (lambda fn: fn),
                 generic_tool=lambda *a, **k: (lambda fn: fn))

from tools.generate_mesh import generate_mesh as gm  # noqa: E402

GOOD = {
    "bladeCount": 4, "impellerRadius": 68.0, "impellerThickness": 3.0,
    "innerThickness": 12.0, "innerMaxPos": 3, "innerCamber": 4.0,
    "innerChord": 18.0, "innerAngle": 30.0, "middlePos": 0.5,
    "middleChord": 20.0, "middleAngle": 22.0, "outerThickness": 9.0,
    "outerMaxPos": 4, "outerCamber": 3.0, "outerChord": 16.0,
    "outerAngle": 14.0,
}
assert set(GOOD) == set(gm._CANONICAL_PARAM_NAMES), "GOOD drifted from the canonical 16"

failures: list[str] = []
_calls = {"backend": 0}


def _stub_backend(params):
    _calls["backend"] += 1
    return ("g MeshFinal\nv 0 0 0\n", 1, None, "stub")


def _stub_render(mesh_path, output_dir):
    return "Renders saved:\n  stub.png"


def _mk(name, params_json=None, with_mesh=False):
    d = gm.ATTEMPTS_DIR / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    if params_json is not None:
        (d / "parameters.json").write_text(
            json.dumps(params_json), encoding="utf-8")
    if with_mesh:
        (d / gm._MESH_FILENAME).write_text("g Old\nv 1 1 1\n", encoding="utf-8")
    return d


def _invoke(d):
    """Call the tool the only way it can now be called: point it at a
    parameters.json.  There is no way to hand it values, which is the point."""
    return gm.generate_and_render_propeller.invoke(
        {"parameters_path": str(d / "parameters.json")})


def check(label, cond, detail=""):
    print("  %s %s%s" % ("OK  " if cond else "FAIL", label,
                         "" if cond else "  <- " + detail))
    if not cond:
        failures.append(label)


gm.render_agent_mesh_obj_text = _stub_backend
gm._render_and_check_fn = _stub_render

print("attempt-folder coherence\n")
print("TOOL CONTRACT — the record is the only input")

d = _mk("g_happy", GOOD)
_calls["backend"] = 0
out = _invoke(d)
check("complete record -> builds",
      (not out.startswith("Error:")) and _calls["backend"] == 1, out[:90])
check("  mesh landed in the RECORD's own folder",
      (d / gm._MESH_FILENAME).is_file())

d = _mk("g_legacy17", dict(GOOD, impellerHeight=12.0))
_calls["backend"] = 0
out = _invoke(d)
check("legacy 17-key record -> builds (impellerHeight ignored)",
      (not out.startswith("Error:")) and _calls["backend"] == 1, out[:90])

for label, params, must_say in [
    ("no parameters.json",      None,                                  "write_parameters"),
    ("15 of 16 keys",           {k: v for k, v in list(GOOD.items())[:15]}, "Missing keys"),
    ("non-numeric value",       dict(GOOD, middleChord="20.0"),        "Non-numeric"),
    ("boolean value",           dict(GOOD, bladeCount=True),           "Non-numeric"),
    ("record is a JSON list",   [1, 2, 3],                             "not a JSON object"),
]:
    d = _mk("g_bad_" + label.split()[0], params)
    _calls["backend"] = 0
    out = _invoke(d)
    check(label + " -> clean error",
          out.startswith("Error:") and _calls["backend"] == 0, out[:90])
    check("  says what is wrong (%r)" % must_say, must_say in out, out[:120])
    check("  no mesh written", not (d / gm._MESH_FILENAME).is_file())

d = _mk("g_malformed", None)
(d / "parameters.json").write_text("{not json", encoding="utf-8")
_calls["backend"] = 0
out = _invoke(d)
check("malformed JSON -> clean error",
      out.startswith("Error:") and _calls["backend"] == 0, out[:90])

d = _mk("g_reuse", GOOD, with_mesh=True)
_calls["backend"] = 0
before = (d / gm._MESH_FILENAME).read_bytes()
out = _invoke(d)
check("existing mesh -> reused, backend NOT called",
      "Reused existing mesh" in out and _calls["backend"] == 0, out[:90])
check("  mesh untouched", (d / gm._MESH_FILENAME).read_bytes() == before)

print("")
print("F75 COMPARISON — dormant, tested directly")

# Unreachable through the tool now.  Kept so that reintroducing value-passing
# cannot quietly ship without this firing again.
d = _mk("f75_unit", GOOD)
check("mismatch detected", bool(gm._param_mismatches(d, dict(GOOD, middleChord=22.0))))
_m = gm._param_mismatches(d, dict(GOOD, middleChord=22.0))
check("  names the parameter and BOTH values",
      "middleChord" in _m[0] and "22.0" in _m[0] and "20.0" in _m[0], str(_m))
check("agreement -> []", gm._param_mismatches(d, GOOD) == [])
check("small real difference (0.55 vs 0.56) caught",
      bool(gm._param_mismatches(_mk("f75_small", dict(GOOD, middlePos=0.55)),
                                dict(GOOD, middlePos=0.56))))
check("no record -> None", gm._param_mismatches(_mk("f75_none", None), GOOD) is None)
check("empty record -> None", gm._param_mismatches(_mk("f75_empty", {}), GOOD) is None)
check("15-key record -> None",
      gm._param_mismatches(_mk("f75_15", {k: v for k, v in list(GOOD.items())[:15]}),
                           GOOD) is None)
check("legacy 17-key -> []",
      gm._param_mismatches(_mk("f75_17", dict(GOOD, impellerHeight=12.0)), GOOD) == [])
check("int/float on disk (3.0 vs 3) -> []",
      gm._param_mismatches(_mk("f75_intfloat", dict(GOOD, bladeCount=3.0)),
                           dict(GOOD, bladeCount=3)) == [])
check("float repr noise -> []",
      gm._param_mismatches(_mk("f75_repr", dict(GOOD, middlePos=0.30000000000000004)),
                           dict(GOOD, middlePos=0.3)) == [])

print("")
print("F75b — MESH PROVENANCE")

d = _mk("f75b_sidecar", GOOD)
_invoke(d)
side = d / gm.MESH_PROVENANCE_FILE
check("build writes the provenance sidecar", side.is_file())
if side.is_file():
    rec = json.loads(side.read_text(encoding="utf-8"))
    check("  holds the 16 canonical keys", set(rec) == set(GOOD),
          str(sorted(set(rec) ^ set(GOOD))))
    check("  values are the record's", all(float(rec[k]) == float(GOOD[k]) for k in GOOD))

check("agreeing params -> [] (write allowed)",
      gm.mesh_provenance_mismatches(d, GOOD) == [])
_diff = gm.mesh_provenance_mismatches(d, dict(GOOD, middleChord=22.0))
check("contradicting params -> refusal list", bool(_diff))
check("  names the parameter and BOTH values",
      bool(_diff) and "middleChord" in _diff[0]
      and "22.0" in _diff[0] and "20.0" in _diff[0], str(_diff))

d = _mk("f75b_legacy", None, with_mesh=True)
check("legacy folder (mesh, no sidecar) -> None (write allowed)",
      gm.mesh_provenance_mismatches(d, GOOD) is None)

d = _mk("f75b_reuse", GOOD)
_invoke(d)
_first = (d / gm.MESH_PROVENANCE_FILE).read_bytes()
_invoke(d)
check("reuse leaves the sidecar untouched",
      (d / gm.MESH_PROVENANCE_FILE).read_bytes() == _first)

print("")
print("PLACEMENT")

# The guard deliberately did NOT go into _validate_output_dir.  One reason is
# checkable offline and is asserted here rather than trusted: smoke_test_param_
# rename.py patches that function with a ONE-ARGUMENT lambda
# (``lambda raw: (Path(raw), None)``), so adding a parameter would TypeError it.
# The tool derives the folder from the record's path for exactly this reason.
import inspect  # noqa: E402

_sig = inspect.signature(gm._validate_output_dir)
check("_validate_output_dir still takes exactly one parameter",
      len(_sig.parameters) == 1, str(_sig))
check("  and still returns via the (path, error) contract",
      gm._validate_output_dir("")[0] is None
      and gm._validate_output_dir("")[1].startswith("Error:"))

# The wrapped function, whichever wrapper is in play: ``_fn`` on this file's
# stub, ``func`` on a real langchain StructuredTool.
_tool_obj = gm.generate_and_render_propeller
_underlying = (getattr(_tool_obj, "_fn", None)
               or getattr(_tool_obj, "func", None)
               or _tool_obj)
_tool_sig = inspect.signature(_underlying)
check("the tool takes exactly one argument (the record's path)",
      list(_tool_sig.parameters) == ["parameters_path"], str(_tool_sig))

for d in gm.ATTEMPTS_DIR.glob("f75*"):
    shutil.rmtree(d, ignore_errors=True)
for d in gm.ATTEMPTS_DIR.glob("g_*"):
    shutil.rmtree(d, ignore_errors=True)

print()
if failures:
    print("FAIL — %d problem(s): %s" % (len(failures), failures))
    raise SystemExit(1)
print("PASS — the tool builds only from an attempt's own record and fails "
      "cleanly on every broken one; F75's dormant comparison still behaves; "
      "and a mesh carries the provenance a later write_parameters is checked "
      "against.")
