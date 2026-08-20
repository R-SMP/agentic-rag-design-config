"""F75 — an attempt folder's mesh must come from its own parameters.json.

Proves BOTH directions, which is the whole point: a guard that only fires is
as bad as one that never does, because this one sits on the path EVERY
geometry call takes and a false refusal blocks legitimate work unattended.

F75b       a mesh built before any parameters.json records the values that
           produced it, so a LATER write_parameters cannot label it with
           numbers it did not come from; folders without a sidecar proceed.

FIRES      build-branch mismatch refuses and builds nothing; reuse-branch
           mismatch WARNS without refusing and without touching the mesh; a
           genuinely small difference is still caught.
DOES NOT   matching params; no parameters.json; ``{}``; a 15-key file; a
OVER-FIRE  legacy 17-key file; int-vs-float on disk; float repr noise.

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
# device smoke_test_prompt_variant and smoke_test_topology_fragments use.
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


def _invoke(d, **over):
    args = dict(GOOD); args.update(over); args["output_dir"] = str(d)
    return gm.generate_and_render_propeller.invoke(args)


def check(label, cond, detail=""):
    print("  %s %s%s" % ("OK  " if cond else "FAIL", label,
                         "" if cond else "  <- " + detail))
    if not cond:
        failures.append(label)


gm.render_agent_mesh_obj_text = _stub_backend
gm._render_and_check_fn = _stub_render

print("F75 attempt-folder coherence\n")
print("MUST FIRE")

d = _mk("f75_build_mismatch", GOOD)
_calls["backend"] = 0
out = _invoke(d, middleChord=22.0)
check("build + mismatch -> refuses", out.startswith("Error:"), out[:90])
check("  names the parameter and BOTH values",
      "middleChord" in out and "22.0" in out and "20.0" in out)
check("  backend NOT called", _calls["backend"] == 0)
check("  no mesh written", not (d / gm._MESH_FILENAME).is_file())

d = _mk("f75_reuse_mismatch", GOOD, with_mesh=True)
before = (d / gm._MESH_FILENAME).read_bytes(), (d / gm._MESH_FILENAME).stat().st_mtime
_calls["backend"] = 0
out = _invoke(d, middleChord=22.0)
check("reuse + mismatch -> does NOT refuse", not out.startswith("Error:"))
check("  reuses and WARNS", "Reused existing mesh" in out and "WARNING" in out)
check("  mesh untouched (bytes + mtime)",
      ((d / gm._MESH_FILENAME).read_bytes(),
       (d / gm._MESH_FILENAME).stat().st_mtime) == before)
check("  backend NOT called", _calls["backend"] == 0)

d = _mk("f75_small_diff", dict(GOOD, middlePos=0.55))
out = _invoke(d, middlePos=0.56)
check("small real difference (0.55 vs 0.56) -> refuses", out.startswith("Error:"))

print("\nMUST NOT OVER-FIRE")

for _i, (label, params, over) in enumerate([
    ("matching params",                 GOOD,                         {}),
    ("no parameters.json at all",       None,                         {}),
    ("parameters.json == {}",           {},                           {}),
    ("15 of 16 keys",                   {k: v for k, v in list(GOOD.items())[:15]}, {}),
    ("legacy 17-key (impellerHeight)",  dict(GOOD, impellerHeight=12.0), {}),
    ("int/float on disk (3.0 vs 3)",    dict(GOOD, bladeCount=3.0, impellerRadius=68),
                                        {"bladeCount": 3, "impellerRadius": 68.0}),
    ("float repr noise",                dict(GOOD, middlePos=0.30000000000000004),
                                        {"middlePos": 0.3}),
]):
    # index, not hash(): PYTHONHASHSEED randomises str hashes per run, so a
    # hash-derived folder name would differ between runs and leak temp dirs.
    d = _mk("f75_ok_%d" % _i, params)
    _calls["backend"] = 0
    out = _invoke(d, **over)
    check(label + " -> proceeds",
          (not out.startswith("Error:")) and _calls["backend"] == 1, out[:90])

print("")
print("F75b — MESH-FIRST PROVENANCE")

# Build into a folder with NO parameters.json — the LEGITIMATE mesh-first
# order (the Orchestrator's fallback folder, the 3-agent Designer).  It must
# still proceed, and must now record what produced the mesh.
d = _mk("f75b_sidecar", None)
_calls["backend"] = 0
out = _invoke(d)
side = d / gm.MESH_PROVENANCE_FILE
check("mesh-first build still proceeds",
      (not out.startswith("Error:")) and _calls["backend"] == 1, out[:90])
check("  provenance sidecar written", side.is_file())
if side.is_file():
    rec = json.loads(side.read_text(encoding="utf-8"))
    check("  sidecar holds the 16 canonical keys",
          set(rec) == set(GOOD), str(sorted(set(rec) ^ set(GOOD))))
    check("  sidecar values are the ones passed",
          all(float(rec[k]) == float(GOOD[k]) for k in GOOD))

# The decision function the three write_parameters handlers call.
check("agreeing params -> [] (write allowed)",
      gm.mesh_provenance_mismatches(d, GOOD) == [])
_diff = gm.mesh_provenance_mismatches(d, dict(GOOD, middleChord=22.0))
check("contradicting params -> refusal list", bool(_diff))
check("  names the parameter and BOTH values",
      bool(_diff) and "middleChord" in _diff[0]
      and "22.0" in _diff[0] and "20.0" in _diff[0])

# Every folder that existed before F75b has a mesh and no sidecar.  Those must
# stay writable, exactly as F75 lets an absent parameters.json proceed.
d = _mk("f75b_legacy", None, with_mesh=True)
check("legacy folder (mesh, no sidecar) -> None (write allowed)",
      gm.mesh_provenance_mismatches(d, GOOD) is None)

# The sidecar describes the mesh ON DISK, not whatever numbers a later call
# happened to carry — so the reuse branch must leave it alone.
d = _mk("f75b_reuse", None)
_invoke(d)
_first = (d / gm.MESH_PROVENANCE_FILE).read_bytes()
_invoke(d, middleChord=22.0)
check("reuse leaves the sidecar untouched",
      (d / gm.MESH_PROVENANCE_FILE).read_bytes() == _first)

print("")
print("PLACEMENT")

# The guard deliberately did NOT go into _validate_output_dir.  One reason is
# checkable offline and is asserted here rather than trusted: smoke_test_param_
# rename.py patches that function with a ONE-ARGUMENT lambda
# (``lambda raw: (Path(raw), None)``), so adding a parameter would TypeError it.
# That test needs langchain_core and cannot run in a bare worktree, so this
# stands in for it.
import inspect  # noqa: E402

_sig = inspect.signature(gm._validate_output_dir)
check("_validate_output_dir still takes exactly one parameter",
      len(_sig.parameters) == 1, str(_sig))
check("  and still returns via the (path, error) contract",
      gm._validate_output_dir("")[0] is None
      and gm._validate_output_dir("")[1].startswith("Error:"))

for d in gm.ATTEMPTS_DIR.glob("f75*"):
    shutil.rmtree(d, ignore_errors=True)

print()
if failures:
    print("FAIL — %d problem(s): %s" % (len(failures), failures))
    raise SystemExit(1)
print("PASS — the guard fires on every incoherent build, warns without "
      "refusing on reuse, stays silent on all seven legitimate shapes, and "
      "the mesh-first order now carries provenance that a later "
      "write_parameters is checked against.")
