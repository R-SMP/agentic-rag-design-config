"""The OpenSCAD backend (MAS-blueprint P6e): a model file is the tool.

A generator's or a geometry tool's ``tool.yaml``::

    backend: openscad
    model: vacuum-hose-adapter.scad       # in the tool's folder
    parts:                                # a setting made of parameters
      End1_Diameter: [End1_Diameter_mm, 0]
    fixed: {Enable_Help: false}           # settings the agents never change
    detail:                               # per purpose: an agent's run, a download
      agent: {fa: 6, fs: 1}
      download: {fa: 3, fs: 0.1}
    timeout: 120                          # seconds (default 120)

What OpenSCAD is given (:func:`settings_for`): every parameter that no
``parts`` entry uses, by its own name; each ``parts`` setting, its
parameter names replaced by their values (numbers, ``true`` / ``false`` and
text stay as they are); ``fixed``; and the purpose's ``detail``.  They go in
an OpenSCAD parameter set (``openscad -p set.json -P engine``), which reads
text and lists as the model's own customizer does; a ``detail`` name
starting with ``$`` (``$fn``) is a definition (``-D``) instead.

The program is ``OPENSCAD_PATH`` (the program, or its folder) or
``openscad`` on the PATH; without it the tool answers with
:data:`NOT_FOUND`.  OpenSCAD's STL becomes the engine's model format, OBJ
(:func:`read_stl`, :func:`to_obj`: the corners shared, in a fixed order, so
the same settings give the same file); a generator's pictures come from the
engine's renderer (``engine/mesh_render.py``), as the propeller's do.
OpenSCAD's ECHO / WARNING / ERROR lines reach the agent.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from engine.tooling import BuildResult, GeometryResult, RenderResult, ToolError

PROGRAM_ENV = "OPENSCAD_PATH"
SET_NAME = "engine"
DEFAULT_TIMEOUT = 120
PURPOSES = ("agent", "download")
NOT_FOUND = ("OpenSCAD was not found on this computer: install it (openscad.org) and put "
             "it on the PATH, or set OPENSCAD_PATH to the program.")
_SAID_RE = re.compile(r"^(ECHO|WARNING|ERROR|DEPRECATED)\b")
_SAID_MAX = 12
_SIMPLE = (bool, int, float, str)


# ---------------------------------------------------------------------------
# The manifest
# ---------------------------------------------------------------------------

def _value_ok(v) -> bool:
    return isinstance(v, _SIMPLE) or (isinstance(v, list) and all(isinstance(x, _SIMPLE) for x in v))


def check(folder: Path, m: dict, where: str) -> list[str]:
    p = []
    model = m.get("model")
    if not isinstance(model, str) or Path(model).name != model or not model.endswith(".scad"):
        p.append(f"{where}: model is the name of an OpenSCAD file (.scad) in the tool's folder")
    elif not (folder / model).is_file():
        p.append(f"{where}: model {model!r} is not in the tool's folder")
    parts = m.get("parts", {})
    if not isinstance(parts, dict) or any(
            not isinstance(v, list) or not v or any(not isinstance(x, (bool, int, float, str)) for x in v)
            for v in parts.values()):
        p.append(f"{where}: parts maps a setting to a list of parameter names and numbers "
                 f"(e.g. End1_Diameter: [End1_Diameter_mm, 0])")
    fixed = m.get("fixed", {})
    if not isinstance(fixed, dict) or not all(_value_ok(v) for v in fixed.values()):
        p.append(f"{where}: fixed maps a setting to a number, true / false, text or a list of them")
    detail = m.get("detail", {})
    if not isinstance(detail, dict) or set(detail) - set(PURPOSES) or not all(
            isinstance(d, dict) and all(_value_ok(v) for v in d.values()) for d in detail.values()):
        p.append(f"{where}: detail is {{agent: {{setting: value}}, download: {{setting: value}}}}")
    t = m.get("timeout", DEFAULT_TIMEOUT)
    if isinstance(t, bool) or not isinstance(t, (int, float)) or t <= 0:
        p.append(f"{where}: timeout is a number of seconds")
    return p


# ---------------------------------------------------------------------------
# The program and its settings
# ---------------------------------------------------------------------------

def program() -> list[str]:
    """The command that starts OpenSCAD.  Raises ToolError without one."""
    raw = (os.getenv(PROGRAM_ENV) or "").strip()
    if raw:
        p = Path(raw)
        if p.is_dir():
            # openscad.com on Windows: the console program (it waits, and prints)
            for name in ("openscad.com", "openscad", "openscad.exe"):
                if (p / name).is_file():
                    return [str(p / name)]
        elif p.is_file():
            return [str(p)]
        raise ToolError(f"{NOT_FOUND}  ({PROGRAM_ENV} is {raw!r}, which is not the program.)")
    found = shutil.which("openscad")
    if not found:
        raise ToolError(NOT_FOUND)
    return [found]


def _num(v) -> str:
    if isinstance(v, int):
        return str(v)
    return str(int(v)) if float(v).is_integer() else repr(float(v))


def scad_value(v) -> str:
    """*v* as an OpenSCAD parameter set writes it (the text it reads back)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return _num(v)
    if isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(json.dumps(x) if isinstance(x, str) else scad_value(x) for x in v) + "]"
    raise ToolError(f"OpenSCAD cannot take the value {v!r}")


def settings_for(m: dict, params: dict, purpose: str) -> tuple[dict, list[str]]:
    """``(settings, definitions)``: what OpenSCAD is given for *params* --
    the parameter set and the ``-D`` definitions (``detail``'s ``$`` names)."""
    parts = m.get("parts") or {}
    used = {x for vals in parts.values() for x in vals if isinstance(x, str)}
    out = {k: v for k, v in params.items() if k not in used}
    for setting, vals in parts.items():
        out[setting] = [params[x] if isinstance(x, str) else x for x in vals]
    out.update(m.get("fixed") or {})
    defines = []
    for k, v in ((m.get("detail") or {}).get(purpose) or {}).items():
        if k.startswith("$"):
            defines.append(f"{k}={scad_value(v)}")
        else:
            out[k] = v
    return out, defines


def run(model: Path, settings: dict, defines: list[str] = (), timeout: float = DEFAULT_TIMEOUT
        ) -> tuple[bytes, list[str]]:
    """``(STL, said)``: the STL OpenSCAD makes of *model* with *settings*,
    and its ECHO / WARNING / ERROR lines.  Raises ToolError."""
    cmd = program()
    with tempfile.TemporaryDirectory(prefix="openscad_") as tmp:
        tmp = Path(tmp)
        sets = tmp / "set.json"
        sets.write_text(json.dumps({"parameterSets": {SET_NAME: {
            k: scad_value(v) for k, v in settings.items()}}, "fileFormatVersion": "1"}, indent=1),
            encoding="utf-8")
        out = tmp / "model.stl"
        args = cmd + ["-o", str(out), "-p", str(sets), "-P", SET_NAME]
        for d in defines:
            args += ["-D", d]
        args.append(str(model))
        try:
            proc = subprocess.run(args, cwd=str(model.parent), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ToolError(f"OpenSCAD did not finish {model.name} within {timeout:g} s: try "
                            f"coarser detail, or a longer timeout in the tool's tool.yaml.") from None
        except OSError as exc:
            raise ToolError(f"{NOT_FOUND}  ({exc})") from None
        said = [ln.strip() for ln in (proc.stdout + "\n" + proc.stderr).splitlines()
                if _SAID_RE.match(ln.strip())]
        if proc.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
            why = [ln for ln in said if ln.startswith("ERROR")] or [
                ln.strip() for ln in (proc.stderr or proc.stdout).strip().splitlines()[-3:]]
            raise ToolError(f"OpenSCAD could not build {model.name}: "
                            + (" | ".join(why[:5]) or f"it ended with code {proc.returncode}"))
        return out.read_bytes(), said


# ---------------------------------------------------------------------------
# STL -> the engine's model (OBJ)
# ---------------------------------------------------------------------------

_BINARY = np.dtype([("normal", "<f4", 3), ("corners", "<f4", (3, 3)), ("attr", "<u2")])


def read_stl(raw: bytes) -> tuple[np.ndarray, np.ndarray]:
    """``(vertices (n, 3), faces (m, 3))`` of a binary or ASCII STL, each
    corner shared by the faces that meet there, in a fixed order."""
    if len(raw) >= 84:
        n = struct.unpack_from("<I", raw, 80)[0]
        if 84 + 50 * n == len(raw):
            corners = np.frombuffer(raw, dtype=_BINARY, count=n, offset=84)["corners"]
            return _shared(corners.reshape(-1, 3).astype(float))
    pts = [ln.split()[1:4] for ln in raw.decode("ascii", errors="replace").splitlines()
           if ln.strip().startswith("vertex")]
    if not pts or len(pts) % 3:
        raise ToolError("OpenSCAD's STL could not be read")
    return _shared(np.array(pts, dtype=float))


def _shared(corners: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    vertices, inverse = np.unique(corners, axis=0, return_inverse=True)
    return vertices, inverse.reshape(-1, 3)


def to_obj(vertices: np.ndarray, faces: np.ndarray, note: str) -> str:
    """The OBJ text: a comment line, the vertices, the faces (1-based)."""
    f = (lambda x: format(float(x), ".9g"))
    lines = [f"# {note}"]
    lines += [f"v {f(x)} {f(y)} {f(z)}" for x, y, z in vertices]
    lines += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in faces]
    return "\n".join(lines) + "\n"


def measures(vertices: np.ndarray, faces: np.ndarray) -> dict:
    """``size`` (the bounding box's three sides) and ``volume`` (of a
    closed surface; 0 for none)."""
    if not len(faces):
        return {"size": [0.0, 0.0, 0.0], "volume": 0.0}
    tri = vertices[faces]
    volume = float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)
    return {"size": [float(s) for s in vertices.max(axis=0) - vertices.min(axis=0)],
            "volume": abs(volume)}


def _model(folder: Path, m: dict) -> Path:
    return folder / m["model"]


def _built(folder: Path, m: dict, params: dict, purpose: str) -> tuple[str, int, dict, list[str]]:
    model = _model(folder, m)
    settings, defines = settings_for(m, params, purpose)
    raw, said = run(model, settings, defines, float(m.get("timeout", DEFAULT_TIMEOUT)))
    vertices, faces = read_stl(raw)
    obj = to_obj(vertices, faces, f"made by OpenSCAD from {model.name}")
    return obj, len(vertices), measures(vertices, faces), said


def _said_text(said: list[str]) -> str:
    if not said:
        return ""
    more = f" (and {len(said) - _SAID_MAX} more)" if len(said) > _SAID_MAX else ""
    return "\nOpenSCAD said" + more + ":\n" + "\n".join("  " + ln for ln in said[:_SAID_MAX])


# ---------------------------------------------------------------------------
# A generator, a geometry tool
# ---------------------------------------------------------------------------

def build(folder: Path, m: dict, inp) -> BuildResult:
    """The attempt's model file, made by OpenSCAD at the agents' detail."""
    obj, n, size, said = _built(folder, m, inp.params, "agent")
    inp.model_path.write_text(obj, encoding="utf-8")
    sx, sy, sz = size["size"]
    return BuildResult(
        summary=(f"Saved the model {inp.model_path.name} ({n} vertices; its size "
                 f"{sx:.1f} x {sy:.1f} x {sz:.1f}), made by OpenSCAD from {m['model']}."
                 + _said_text(said)),
        model_files=[inp.model_path])


def render(folder: Path, m: dict, inp) -> RenderResult:
    """The attempt's pictures and checks, by the engine's renderer -- the
    library and the checks of the tool's own ``render_library`` /
    ``mesh_checks`` settings when it has them."""
    s = inp.settings or {}
    if s.get("render_library") == "pyvista":
        from engine import mesh_render_pyvista as core
        go = core.render_and_check_pv
    else:
        from engine import mesh_render as core
        go = core.render_and_check
    core.set_mesh_checks(bool(s.get("mesh_checks", True)))
    return RenderResult(report=go(str(inp.model_path), str(inp.attempt_dir)))


def make_model(folder: Path, m: dict, params: dict) -> GeometryResult:
    """The model, made by OpenSCAD at the downloads' detail."""
    obj, n, _size, _said = _built(folder, m, params, "download")
    return GeometryResult(model=obj, vertex_count=n)
