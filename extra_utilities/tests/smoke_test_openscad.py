"""The OpenSCAD backend (MAS-blueprint P6e, ``engine/backends/``), offline.

A generator or a geometry tool whose ``tool.yaml`` says ``backend:
openscad`` is run by the engine: the parameters go to OpenSCAD as a
parameter set, its STL becomes the engine's OBJ, a generator's pictures
come from the engine's renderer.  Five groups of checks:

1. VALUES.  What OpenSCAD is given: the parameter set's texts (numbers,
   true / false, text, lists with text), ``parts`` put together, ``fixed``,
   ``detail`` per purpose (a ``$`` name as a definition).
2. STL.  A binary and an ASCII STL read to the same shared corners; the
   OBJ written from them; the size and volume of a cube.
3. MANIFESTS.  A backend tool's manifest checks: an unknown backend, a
   helper with one, ``build`` beside one, a missing model file, ``parts`` /
   ``fixed`` / ``detail`` / ``timeout`` of the wrong shape, ``parts``
   naming no parameter.
4. A STAND-IN OPENSCAD (a small Python program in its place): the engine's
   generator run of a backend tool writes the model, and its report carries
   what OpenSCAD was given and said; a geometry tool makes the model at the
   downloads' detail; a run that fails, one that takes too long and a
   program that is not there each give their clear error -- Validate reads
   the last as "this computer lacks the program OpenSCAD" -- and a
   downloaded package's image installs the pinned OpenSCAD (its libraries
   on the apt-get line, the snapshot checked against its sha256), once,
   and goes back to the engine's own Dockerfile without the tool (the
   repository's has it for the hose adapter, setups/vacuum_hose_adapter).
5. THE REAL ONE -- when OpenSCAD (``OPENSCAD_PATH`` or the PATH) and the
   vacuum hose adapter (``HOSE_ADAPTER_DIR``, or ``DCs/vacuum-hose-adapter-
   openscad-main`` beside a folder above the repo) are on this computer,
   else SKIP.  The model's download, with its samples, is not in the
   repository (the setup carries only its script).  The engine's run of a set of settings
   equals OpenSCAD's own run of them (``-D``), byte for byte after the
   conversion; the generator and the geometry tool of a setup made around
   the model build it; the 2023 sample configurations
   (``vacuum-hose-adapter-samples.scad``, translated to today's settings)
   are rebuilt and compared with ``samples/*.stl`` (size and volume,
   reported: the samples are from 2022 and the model has changed since).

Run from the repo root:  py -3.13 extra_utilities/tests/smoke_test_openscad.py
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from engine import pack_tools  # noqa: E402
from engine.backends import openscad as O  # noqa: E402
from engine.tooling import ToolError  # noqa: E402

FAILURES: list[str] = []
HOSE = "vacuum-hose-adapter-openscad-main"


def check(ok: bool, what: str) -> None:
    if not ok:
        FAILURES.append(what)


def _run(group, tag: str):
    try:
        return group()
    except Exception as exc:                                        # noqa: BLE001
        import traceback
        check(False, f"{tag} {type(exc).__name__}: {exc}\n{traceback.format_exc()[-1200:]}")
        return None


# ---------------------------------------------------------------------------
# 1. values
# ---------------------------------------------------------------------------

def check_values() -> None:
    cases = [(3, "3"), (3.0, "3"), (0.1, "0.1"), (-2.5, "-2.5"), (True, "true"), (False, "false"),
             ("hose", "hose"), ([50, 0], "[50, 0]"), (["", 1], '["", 1]'), ([0.5, True], "[0.5, true]")]
    for v, want in cases:
        check(O.scad_value(v) == want, f"[VALUES] {v!r} is written {O.scad_value(v)!r}, not {want!r}")
    m = {"parts": {"End1_Diameter": ["End1_Diameter_mm", 0], "Offset": ["Off_x", "Off_y"]},
         "fixed": {"Enable_Help": False, "End1_Color": ["", 1]},
         "detail": {"agent": {"fa": 8, "fs": 2, "$fn": 0}, "download": {"fa": 3, "fs": 0.1}}}
    params = {"End1_Style": "mag", "End1_Diameter_mm": 50.5, "Off_x": 1, "Off_y": -2, "Count": 6}
    got, defines = O.settings_for(m, params, "agent")
    check(got == {"End1_Style": "mag", "Count": 6, "End1_Diameter": [50.5, 0], "Offset": [1, -2],
                  "Enable_Help": False, "End1_Color": ["", 1], "fa": 8, "fs": 2}
          and defines == ["$fn=0"], f"[VALUES] an agent's settings: {got} {defines}")
    got, defines = O.settings_for(m, params, "download")
    check(got["fa"] == 3 and got["fs"] == 0.1 and defines == [], f"[VALUES] a download's: {got} {defines}")


# ---------------------------------------------------------------------------
# 2. STL
# ---------------------------------------------------------------------------

_CUBE = [((0, 0, 0), (1, 1, 0), (1, 0, 0)), ((0, 0, 0), (0, 1, 0), (1, 1, 0)),
         ((0, 0, 1), (1, 0, 1), (1, 1, 1)), ((0, 0, 1), (1, 1, 1), (0, 1, 1)),
         ((0, 0, 0), (1, 0, 0), (1, 0, 1)), ((0, 0, 0), (1, 0, 1), (0, 0, 1)),
         ((0, 1, 0), (1, 1, 1), (1, 1, 0)), ((0, 1, 0), (0, 1, 1), (1, 1, 1)),
         ((0, 0, 0), (0, 0, 1), (0, 1, 1)), ((0, 0, 0), (0, 1, 1), (0, 1, 0)),
         ((1, 0, 0), (1, 1, 0), (1, 1, 1)), ((1, 0, 0), (1, 1, 1), (1, 0, 1))]


def cube_stl(side: float, binary: bool) -> bytes:
    tris = [[[c * side for c in p] for p in t] for t in _CUBE]
    if binary:
        out = b"\0" * 80 + struct.pack("<I", len(tris))
        for t in tris:
            out += struct.pack("<12fH", 0, 0, 0, *[c for p in t for c in p], 0)
        return out
    lines = ["solid cube"]
    for t in tris:
        lines += ["  facet normal 0 0 0", "    outer loop"] + [f"      vertex {x} {y} {z}" for x, y, z in t] \
            + ["    endloop", "  endfacet"]
    return ("\n".join(lines + ["endsolid cube"]) + "\n").encode("ascii")


def check_stl() -> None:
    vb, fb = O.read_stl(cube_stl(2, True))
    va, fa = O.read_stl(cube_stl(2, False))
    check(len(vb) == 8 and len(fb) == 12 and (vb == va).all() and (fb == fa).all(),
          f"[STL] binary / ASCII cube: {len(vb)} / {len(va)} corners, {len(fb)} / {len(fa)} faces")
    obj = O.to_obj(vb, fb, "a cube")
    lines = obj.splitlines()
    check(lines[0] == "# a cube" and sum(ln.startswith("v ") for ln in lines) == 8
          and sum(ln.startswith("f ") for ln in lines) == 12 and "f 1 " in obj,
          f"[STL] the OBJ: {lines[:3]}")
    m = O.measures(vb, fb)
    check(m["size"] == [2.0, 2.0, 2.0] and abs(m["volume"] - 8.0) < 1e-9, f"[STL] the cube's measures: {m}")
    try:
        O.read_stl(b"not an stl")
        check(False, "[STL] a file that is no STL was read")
    except ToolError as exc:
        check("could not be read" in str(exc), f"[STL] a bad file: {exc}")


# ---------------------------------------------------------------------------
# a setup made around a model
# ---------------------------------------------------------------------------

def _number(name, lo, hi, step, default, unit="mm"):
    return {"name": name, "type": "float", "min": lo, "max": hi, "step": step, "default": default,
            "group": "ends", "label": name, "unit": unit, "db_unit": unit, "db_description": name}


PARAMETERS = {
    "groups": [{"id": "ends", "label": "Ends", "image": "/pack/assets/general-profile.png", "image_alt": "",
                "order": ["End1_Style", "End1_Diameter_mm", "End2_Diameter_mm", "Transition_Length"]}],
    "parameters": [
        {"name": "End1_Style", "type": "choice", "default": "hose", "group": "ends", "label": "End 1 style",
         "choices": [{"value": "hose", "label": "Hose connector"}, {"value": "mag", "label": "Magnetic flange"}],
         "unit": "", "db_unit": "choice", "db_description": "End 1 style"},
        _number("End1_Diameter_mm", 20, 150, 0.5, 100),
        _number("End2_Diameter_mm", 20, 150, 0.5, 60),
        _number("Transition_Length", 0, 100, 1, 0)]}
PARTS = {"End1_Diameter": ["End1_Diameter_mm", 0], "End2_Diameter": ["End2_Diameter_mm", 0]}
IMAGES = [{"view": v, "file": f"render_{v}.png", "order": i + 1, "default_enabled": True,
           "compression": "3d_render"} for i, v in enumerate(("isometric", "top", "side"))]


def manifests(model: str, detail: dict | None = None, timeout: float = 120) -> dict[str, dict]:
    common = {"backend": "openscad", "model": model, "parts": PARTS, "fixed": {"Enable_Help": False},
              "detail": detail or {"agent": {"fa": 8, "fs": 2}, "download": {"fa": 6, "fs": 1}},
              "timeout": timeout}
    return {
        "hose_adapter": {"name": "hose_adapter", "display_name": "Hose adapter", "kind": "generator",
                         "roles": ["tool_runner"], "description": "Builds the adapter with OpenSCAD.",
                         **common, "args": {"parameters_path": "The attempt's parameters.json."},
                         "outputs": {"model_file": "adapter.obj", "model_format": "obj", "up_axis": "z",
                                     "images": IMAGES},
                         "fill_on_save": True, "list_order": 1},
        "hose_geometry": {"name": "hose_geometry", "display_name": "Hose geometry", "kind": "geometry",
                          "description": "The adapter's model for the Download buttons.", **common,
                          "outputs": {"model_format": "obj"}},
    }


def make_setup(tmp: Path, model_src: Path | None, found: dict[str, dict],
               model_name: str = "adapter.scad") -> Path:
    """A copy of the pack with its tools replaced by *found* (each with the
    model file, as *model_name*), its parameters by :data:`PARAMETERS`."""
    pack = tmp / "dc_pack"
    shutil.copytree(ROOT / "setups" / "propeller", pack, ignore=shutil.ignore_patterns("__pycache__"))
    for t in list((pack / "tools").iterdir()):
        shutil.rmtree(t)
    for name, m in found.items():
        folder = pack / "tools" / name
        (folder / "prompts").mkdir(parents=True)
        (folder / "tool.yaml").write_text(yaml.safe_dump(m, sort_keys=False), encoding="utf-8")
        if "tool_runner" in (m.get("roles") or []):
            (folder / "prompts" / "tool_list_entry.md").write_text(f"{name} -- builds the model.\n",
                                                                   encoding="utf-8")
        if model_src is not None and m.get("model"):
            shutil.copyfile(model_src, folder / model_name)
    (pack / "parameters.json").write_text(json.dumps(PARAMETERS, indent=2), encoding="utf-8")
    y = pack / "pack.yaml"
    y.write_text(y.read_text(encoding="utf-8").replace("geometry_tool: rhino_geometry",
                                                       "geometry_tool: hose_geometry"), encoding="utf-8")
    return pack


class Setup:
    """``config.DC_PACK_DIR`` / ``ATTEMPTS_DIR`` pointed at a setup and an
    attempts folder of their own while it is open."""

    def __init__(self, pack: Path, attempts: Path):
        self.pack, self.attempts = pack, attempts

    def __enter__(self):
        self.saved = (config.DC_PACK_DIR, config.ATTEMPTS_DIR)
        config.DC_PACK_DIR, config.ATTEMPTS_DIR = self.pack, self.attempts
        self.attempts.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(self, *exc):
        config.DC_PACK_DIR, config.ATTEMPTS_DIR = self.saved
        return False

    def attempt(self, params: dict, n: int = 1) -> Path:
        folder = self.attempts / f"20260101_000000_{n:03d}_test"
        folder.mkdir(parents=True, exist_ok=True)
        f = folder / "parameters.json"
        f.write_text(json.dumps(params), encoding="utf-8")
        return f


DEFAULTS = {p["name"]: p["default"] for p in PARAMETERS["parameters"]}


class StandInRenderer:
    """``engine.mesh_render`` replaced while open: the renderer needs trimesh
    and pyrender, which may not be on this computer (the render step is the
    propeller's own, checked with the propeller)."""

    def __init__(self, answer: str = "(stand-in render of {name})"):
        self.answer = answer

    def __enter__(self):
        import types

        import engine
        self.saved = (sys.modules.get("engine.mesh_render"), getattr(engine, "mesh_render", None))
        stub = types.ModuleType("engine.mesh_render")
        stub.set_mesh_checks = lambda on: None
        stub.render_and_check = lambda mesh, out: self.answer.format(name=Path(mesh).name)
        sys.modules["engine.mesh_render"] = stub
        engine.mesh_render = stub
        return self

    def __exit__(self, *exc):
        import engine
        module, attr = self.saved
        if module is None:
            sys.modules.pop("engine.mesh_render", None)
        else:
            sys.modules["engine.mesh_render"] = module
        if attr is None:
            if hasattr(engine, "mesh_render"):
                del engine.mesh_render
        else:
            engine.mesh_render = attr
        return False


# ---------------------------------------------------------------------------
# 3. manifests
# ---------------------------------------------------------------------------

def check_manifests(tmp: Path) -> int:
    base = manifests("adapter.scad")
    cases = [
        (lambda f: f["hose_adapter"].update(backend="freecad"), "backend is one of openscad"),
        (lambda f: f.update(helper={"name": "helper", "display_name": "H", "kind": "helper",
                                    "roles": ["tool_runner"], "description": "d", "backend": "openscad",
                                    "model": "adapter.scad", "list_order": 2,
                                    "args": {"parameters_path": "p"}}),
         "a backend runs a generator or a geometry tool"),
        (lambda f: f["hose_adapter"].update(build="tool.py:build"), "has no build"),
        (lambda f: f["hose_geometry"].update(model="other.scad"), "is not in the tool's folder"),
        (lambda f: f["hose_geometry"].update(model="../adapter.scad"), "model is the name of an OpenSCAD file"),
        (lambda f: f["hose_adapter"].update(parts={"End1_Diameter": "End1_Diameter_mm"}), "parts maps a setting"),
        (lambda f: f["hose_adapter"].update(parts={"End1_Diameter": ["Ghost_mm", 0]}),
         "parts names 'Ghost_mm', which is not a parameter"),
        (lambda f: f["hose_adapter"].update(fixed={"x": {"a": 1}}), "fixed maps a setting"),
        (lambda f: f["hose_adapter"].update(detail={"preview": {"fa": 1}}), "detail is"),
        (lambda f: f["hose_adapter"].update(timeout=0), "timeout is a number of seconds"),
    ]
    model = tmp / "stand-in.scad"
    model.write_text("cube(1);\n", encoding="utf-8")
    n = 0
    for i, (edit, words) in enumerate(cases):
        found = json.loads(json.dumps(base))
        edit(found)
        with Setup(make_setup(tmp / f"m{i}", model, found), tmp / f"m{i}" / "attempts"):
            try:
                pack_tools.manifests()
                check(False, f"[MANIFESTS] a manifest with '{words}' was accepted")
            except pack_tools.PackToolError as exc:
                check(words in str(exc), f"[MANIFESTS] '{words}': {str(exc)[:300]}")
        n += 1
    with Setup(make_setup(tmp / "ok", model, base), tmp / "ok" / "attempts"):
        found = pack_tools.manifests()
        check(set(found) == {"hose_adapter", "hose_geometry"}, f"[MANIFESTS] the good setup: {sorted(found)}")
    return n


# ---------------------------------------------------------------------------
# 4. a stand-in OpenSCAD
# ---------------------------------------------------------------------------

FAKE = r'''
import json, os, sys, time
a = sys.argv[1:]
out, sets, name = a[a.index("-o") + 1], a[a.index("-p") + 1], a[a.index("-P") + 1]
vals = json.load(open(sets, encoding="utf-8"))["parameterSets"][name]
mode = os.environ.get("FAKE_OPENSCAD", "ok")
if mode == "fail":
    print("ERROR: Parser error: syntax error in file adapter.scad, line 3", file=sys.stderr)
    sys.exit(1)
if mode == "slow":
    time.sleep(20)
print('ECHO: "given", ' + json.dumps({"set": vals, "defines": [a[i + 1] for i, x in enumerate(a) if x == "-D"],
                                     "model": os.path.basename(a[-1]), "cwd": os.path.basename(os.getcwd())},
                                    sort_keys=True), file=sys.stderr)
print("WARNING: a stand-in warning", file=sys.stderr)
d = float(vals["End1_Diameter"].strip("[]").split(",")[0])
open(out, "wb").write(CUBE(d))
'''


def check_stand_in(tmp: Path) -> str:
    fake = tmp / "fake_openscad.py"
    import inspect
    fake.write_text("import struct\n" + inspect.getsource(cube_stl).replace("cube_stl", "_cube")
                    + f"\n_CUBE = {_CUBE!r}\nCUBE = lambda d: _cube(d, True)\n" + FAKE, encoding="utf-8")
    real_program = O.program
    O.program = lambda: [sys.executable, str(fake)]
    model = tmp / "stand-in.scad"
    model.write_text("cube(1);\n", encoding="utf-8")
    try:
        with Setup(make_setup(tmp / "fake", model, manifests("adapter.scad")), tmp / "fake" / "attempts") as s:
            params = dict(DEFAULTS, End1_Style="mag", End1_Diameter_mm=60)
            with StandInRenderer():
                answer = pack_tools.run_generator("hose_adapter", str(s.attempt(params)))
            folder = s.attempts / "20260101_000000_001_test"
            obj = folder / "adapter.obj"
            given = next((json.loads(ln.split('"given", ', 1)[1]) for ln in answer.splitlines()
                          if '"given"' in ln), {})
            check(obj.is_file() and obj.read_text(encoding="utf-8").startswith("# made by OpenSCAD from adapter.scad")
                  and "Saved the model adapter.obj (8 vertices; its size 60.0 x 60.0 x 60.0)" in answer
                  and "WARNING: a stand-in warning" in answer and "(stand-in render of adapter.obj)" in answer,
                  f"[STAND-IN] the generator's answer: {answer[:400]}")
            check(given.get("set") == {"End1_Style": "mag", "Transition_Length": "0", "End1_Diameter": "[60, 0]",
                                       "End2_Diameter": "[60, 0]", "Enable_Help": "false", "fa": "8", "fs": "2"}
                  and given.get("defines") == [] and given.get("model") == "adapter.scad"
                  and given.get("cwd") == "hose_adapter",
                  f"[STAND-IN] what OpenSCAD was given: {given}")
            again = pack_tools.run_generator("hose_adapter", str(folder / "parameters.json"))
            check(again.startswith("Reused existing"), f"[STAND-IN] a second run did not reuse the model: {again[:120]}")
            made = pack_tools.make_model(params, ["hose_geometry"])
            check(made.result.vertex_count == 8 and made.result.model.startswith("# made by OpenSCAD")
                  and made.made_by == "Hose geometry", f"[STAND-IN] the geometry tool: {made}")
            os.environ["FAKE_OPENSCAD"] = "fail"
            try:
                bad = pack_tools.run_generator("hose_adapter", str(s.attempt(params, 2)))
            finally:
                os.environ.pop("FAKE_OPENSCAD", None)
            check(bad.startswith("Error: OpenSCAD could not build adapter.scad: ERROR: Parser error")
                  and not (s.attempts / "20260101_000000_002_test" / "adapter.obj").exists(),
                  f"[STAND-IN] a failing run: {bad[:200]}")
        with Setup(make_setup(tmp / "slow", model, manifests("adapter.scad", timeout=1)), tmp / "slow" / "attempts") as s:
            os.environ["FAKE_OPENSCAD"] = "slow"
            try:
                slow = pack_tools.run_generator("hose_adapter", str(s.attempt(DEFAULTS)))
            finally:
                os.environ.pop("FAKE_OPENSCAD", None)
            check("OpenSCAD did not finish adapter.scad within 1 s" in slow, f"[STAND-IN] a run too long: {slow[:200]}")
    finally:
        O.program = real_program
    saved = os.environ.get(O.PROGRAM_ENV)
    os.environ[O.PROGRAM_ENV] = str(tmp / "no-such-openscad.exe")
    try:
        O.program()
        check(False, "[STAND-IN] a program that is not there was found")
    except ToolError as exc:
        check(str(exc).startswith(O.NOT_FOUND) and "no-such-openscad.exe" in str(exc),
              f"[STAND-IN] no program: {exc}")
    finally:
        if saved is None:
            os.environ.pop(O.PROGRAM_ENV, None)
        else:
            os.environ[O.PROGRAM_ENV] = saved
    from studio import package, validate
    check(validate._lacks(O.NOT_FOUND) == "the program OpenSCAD",
          f"[STAND-IN] Validate reads a missing OpenSCAD as: {validate._lacks(O.NOT_FOUND)!r}")
    y = tmp / "tool.yaml"
    y.write_text(yaml.safe_dump(manifests("adapter.scad")["hose_adapter"]), encoding="utf-8")
    dock = package.merge_apt((ROOT / "Dockerfile").read_text(encoding="utf-8"), {})[0]   # the engine's own
    check(package.OPENSCAD_MARK not in dock, "[STAND-IN] the engine's own Dockerfile keeps the OpenSCAD block")
    merged, notes = package.merge_apt(dock, {"tools/hose_adapter/tool.yaml": y})
    lines = merged.splitlines()
    apt_end = next(i for i, ln in enumerate(lines) if "rm -rf /var/lib/apt/lists/*" in ln)
    check(all(f"        {lib} \\" in lines[:apt_end] for lib in package.OPENSCAD_LIBS)
          and lines.count(package.OPENSCAD_MARK) == 1 and lines.index(package.OPENSCAD_MARK) == apt_end + 2
          and f"https://files.openscad.org/snapshots/{package.OPENSCAD_APPIMAGE} \\" in merged
          and f'"{package.OPENSCAD_SHA256}  /tmp/openscad.AppImage" | sha256sum -c -' in merged
          and "ENV OPENSCAD_PATH=/opt/openscad/AppRun" in lines
          and not any(ln.strip() == "openscad \\" for ln in lines)
          and any(f"installs OpenSCAD {package.OPENSCAD_VERSION}" in n for n in notes),
          f"[STAND-IN] the package's image does not install the pinned OpenSCAD: {notes}")
    check(package.merge_apt(merged, {"tools/hose_adapter/tool.yaml": y})[0] == merged
          and package.merge_apt(merged, {})[0] == dock,
          "[STAND-IN] merging again changes the Dockerfile, or the tool gone does not give the engine's back")
    return "generator, geometry tool, failure, timeout, no program, Validate's warning, the package"


# ---------------------------------------------------------------------------
# 5. the real OpenSCAD and the hose adapter
# ---------------------------------------------------------------------------

def hose_dir() -> Path | None:
    raw = os.getenv("HOSE_ADAPTER_DIR")
    if raw:
        return Path(raw) if Path(raw).is_dir() else None
    return next((p / "DCs" / HOSE for p in ROOT.parents if (p / "DCs" / HOSE).is_dir()), None)


def _d_value(v) -> str:
    return json.dumps(v) if isinstance(v, str) else O.scad_value(v)


def direct(model: Path, settings: dict) -> bytes:
    """OpenSCAD's own run of *settings*, each a definition (``-D``)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "direct.stl"
        args = O.program() + ["-o", str(out)]
        for k, v in settings.items():
            args += ["-D", f"{k}={_d_value(v)}"]
        subprocess.run(args + [str(model)], cwd=str(model.parent), capture_output=True, timeout=300)
        return out.read_bytes()


# The 2023 sample configurations (vacuum-hose-adapter-samples.scad), in
# today's settings, and the sample model each made.
SAMPLES = {
    "50to30": ("50mm_hose_to_30mm_hose.stl", {
        "End1_Style": "hose", "End1_Measurement": "outer", "End1_Diameter": [50, 0], "End1_Length": [40, 0],
        "End1_Extension_StopThickness": 4, "End1_Extension_StopLength": 8, "Transition_Style": "bend+taper",
        "Transition_Length": 10, "End2_Style": "hose", "End2_Measurement": "outer", "End2_Diameter": [40, 0],
        "End2_Length": [40, 0], "End2_Taper": 2}),
    "50to30bend45deg": ("50mm_hose_to_30mm_hose_bent_by_45deg.stl", {
        "End1_Style": "hose", "End1_Measurement": "outer", "End1_Diameter": [50, 0], "End1_Length": [40, 0],
        "End1_Extension_StopThickness": 4, "End1_Extension_StopLength": 8, "Transition_Style": "bend+taper",
        "Transition_Length": 10, "Transition_Bend_Radius": 10, "Transition_Angle": 45, "End2_Style": "hose",
        "End2_Measurement": "outer", "End2_Diameter": [40, 0], "End2_Length": [40, 0], "End2_Taper": 2}),
    "50to100": ("50mm_hose_to_100mm_hose.stl", {
        "End1_Style": "hose", "End1_Measurement": "outer", "End1_Diameter": [50, 0], "End1_Length": [40, 0],
        "End1_Taper": 2, "Transition_Style": "bend+taper", "Transition_Length": 50, "End2_Style": "hose",
        "End2_Measurement": "outer", "End2_Diameter": [100, 0], "End2_Length": [50, 0], "End2_Taper": 2,
        "End2_Extension_StopThickness": 4, "End2_Extension_StopLength": 8}),
    "50toflat": ("flat_plate_to_50mm_hose.stl", {
        "End1_Style": "hose", "End1_Measurement": "inner", "End1_Diameter": [50, 0], "End1_Length": [45, 0],
        "End1_Ring": "recessed", "Transition_Style": "flat", "Transition_Length": 6, "End2_Style": "hose",
        "End2_Measurement": "outer", "End2_Diameter": [100, 0]}),
    "mag50to40": ("50mm_magnet_to_40mm.stl", {
        "Alignment_Depth": 2, "Alignment_Upper_Width": 3, "Alignment_Lower_Width": 0.5,
        "Alignment_Side_Clearance": 0.25, "Alignment_Depth_Clearance": 0.75, "End1_Style": "mag",
        "End1_Measurement": "inner", "End1_Diameter": [50, 0], "End1_Length": [15, 0], "End1_Magnets_Count": 8,
        "End1_Magnet_Diameter": 10.5, "End1_Magnet_Thickness": 2.5, "End1_Magnet_Border": 3,
        "End1_Magnet_Flange_Thickness": 7, "End1_Ring": "recessed", "Transition_Style": "bend+taper",
        "Transition_Length": 10, "End2_Style": "hose", "End2_Measurement": "outer", "End2_Diameter": [40, 0],
        "End2_Length": [40, 0], "End2_Taper": 2}),
    "mag50to100": ("50mm_magnet_to_100mm.stl", {
        "Alignment_Depth": 2, "Alignment_Upper_Width": 3, "Alignment_Lower_Width": 0.5,
        "Alignment_Side_Clearance": 0.25, "Alignment_Depth_Clearance": 0.75, "End1_Style": "mag",
        "End1_Measurement": "inner", "End1_Diameter": [50, 0], "End1_Length": [15, 0], "End1_Magnets_Count": 8,
        "End1_Magnet_Diameter": 10.5, "End1_Magnet_Thickness": 2.5, "End1_Magnet_Border": 3,
        "End1_Magnet_Flange_Thickness": 7, "End1_Ring": "recessed", "Transition_Style": "bend+taper",
        "Transition_Length": 25, "End2_Style": "hose", "End2_Measurement": "outer", "End2_Diameter": [100, 0],
        "End2_Length": [50, 0]}),
}
# The samples file's own detail ($fa = 6, $fs = 1): the model's fa / fs settings.
SAMPLE_DETAIL = {"fa": 6, "fs": 1}


def check_real(tmp: Path) -> str:
    try:
        O.program()
    except ToolError:
        return "SKIP (no OpenSCAD on this computer: set OPENSCAD_PATH)"
    folder = hose_dir()
    if folder is None:
        return f"SKIP (the hose adapter is not on this computer: set HOSE_ADAPTER_DIR to {HOSE})"
    model = folder / "combined" / "vacuum-hose-adapter.scad"
    # (a) the engine's run == OpenSCAD's own run of the same settings
    settings = {"End1_Style": "mag", "End1_Diameter": [50, 0], "End2_Diameter": [30, 0], "End1_Magnets_Count": 6,
                "Transition_Length": 10, "Enable_Help": False, "fa": 8, "fs": 2}
    raw, said = O.run(model, settings)
    mine = O.to_obj(*O.read_stl(raw), "x")
    theirs = O.to_obj(*O.read_stl(direct(model, settings)), "x")
    check(mine == theirs and mine.count("\nv ") > 100,
          f"[REAL] the engine's run differs from OpenSCAD's own ({mine.count(chr(10) + 'v ')} / "
          f"{theirs.count(chr(10) + 'v ')} corners)")
    # (b) a setup made around the model
    with Setup(make_setup(tmp / "real", model, manifests("vacuum-hose-adapter.scad"),
                          "vacuum-hose-adapter.scad"), tmp / "real" / "attempts") as s:
        params = dict(DEFAULTS, End1_Diameter_mm=50, End2_Diameter_mm=30, Transition_Length=10)
        try:
            import pyrender  # noqa: F401
            import trimesh  # noqa: F401
            answer = pack_tools.run_generator("hose_adapter", str(s.attempt(params)))
        except ImportError:
            # this computer cannot draw: the model is built, the pictures not
            with StandInRenderer("(render skipped here)"):
                answer = pack_tools.run_generator("hose_adapter", str(s.attempt(params)))
        obj = s.attempts / "20260101_000000_001_test" / "adapter.obj"
        check(obj.is_file() and "made by OpenSCAD from vacuum-hose-adapter.scad" in answer
              and obj.read_text(encoding="utf-8").count("\nv ") > 100,
              f"[REAL] the generator: {answer[:300]}")
        coarse = obj.read_text(encoding="utf-8").count("\nv ")
        made = pack_tools.make_model(params, ["hose_geometry"])
        check(made.result.vertex_count > coarse,
              f"[REAL] the geometry tool's download detail is not finer: {made.result.vertex_count} vs {coarse}")
    # (c) the 2023 samples, rebuilt and compared
    rows = []
    for name, (stl, values) in SAMPLES.items():
        sample = folder / "samples" / stl
        if not sample.is_file():
            continue
        try:
            raw, _said = O.run(model, dict(values, **SAMPLE_DETAIL, Enable_Help=False), timeout=600)
        except ToolError as exc:
            check(False, f"[REAL] the sample {name} does not build: {exc}")
            continue
        a = O.measures(*O.read_stl(raw))
        b = O.measures(*O.read_stl(sample.read_bytes()))
        rows.append((name, sorted(a["size"]), sorted(b["size"]), a["volume"], b["volume"]))
    print("  sample                 rebuilt size (sorted)          2022 sample size            volume ratio")
    for name, sa, sb, va, vb in rows:
        print(f"  {name:20s}  {' x '.join(f'{x:6.1f}' for x in sa)}   {' x '.join(f'{x:6.1f}' for x in sb)}"
              f"   {va / vb if vb else 0:6.3f}")
    check(len(rows) == len(SAMPLES), f"[REAL] {len(rows)} of {len(SAMPLES)} samples rebuilt")
    return f"OpenSCAD's own run matched; setup built; {len(rows)} samples rebuilt and compared"


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="openscad_smoke_"))
    try:
        _run(check_values, "[VALUES]")
        _run(check_stl, "[STL]")
        n = _run(lambda: check_manifests(tmp), "[MANIFESTS]")
        stand_in = _run(lambda: check_stand_in(tmp), "[STAND-IN]")
        real = _run(lambda: check_real(tmp), "[REAL]")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"{n} broken manifests refused; stand-in: {stand_in}; real: {real}")
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - a backend tool's manifest is checked, OpenSCAD is given the parameters as the "
          "model's own settings, its STL becomes the engine's OBJ, the generator and the geometry "
          "tool run it, and a failure, a timeout or a missing program says so.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
