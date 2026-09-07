"""The two geometry backends, behind one contract.

``build(params, backend=...)`` returns a :class:`PropellerGeometry` whose parts
are TAGGED (blade / ring / hub / ...) so each can be coloured independently,
and whose three section curves are present regardless of which backend ran.

Backends
--------
``feg``    headless Node running the vendored ``feg_js/`` copy of ``web/feg``
           -- the same geometry the browser 3D preview shows.  Local, fast,
           needs Node + ``three`` on the module path.
``rhino``  RhinoCompute evaluating the Grasshopper definition -- the source of
           truth for the manufacturable deliverable.  Needs a reachable
           RhinoCompute server.

There is deliberately **no fallback between them**.  The two produce visibly
different geometry, so quietly substituting one would put FEG geometry under a
sheet whose title block says "RhinoCompute" -- a mislabelled drawing is worse
than a failed one.  An unreachable server raises :class:`GeometryError`.

Section curves are always computed in Python (``airfoil.build_section_3d``), so
they are identical across backends.  For the ``feg`` backend the exporter's own
curves are compared against them and the largest disagreement is recorded in
``meta['section_agreement_mm']`` -- a live drift alarm on every run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from propeller_studio.geometry import airfoil

BACKENDS = ("feg", "rhino")

_HERE = Path(__file__).resolve().parent
_EXPORTER = _HERE / "feg_export_parts.mjs"

# Grasshopper output name -> studio part name.  An output not listed here is
# kept under its own name rather than being guessed at: an unknown part that
# shows up in the render under its real name is a question; one silently folded
# into "blade" is a wrong drawing.
_RHINO_PART_NAMES = {
    "MeshProfile": "blade",
    "MeshRing": "ring",
    "MeshSimpleInterface": "hub",
    "MeshLauncher": "launcher",
}

# Canonical draw order / default part list.
PART_ORDER = ("blade", "ring", "hub", "launcher", "body")


class GeometryError(RuntimeError):
    """A backend could not produce geometry.  The message is written to be
    shown to the person who asked for the render, not to a log."""


@dataclass
class Part:
    name: str
    vertices: np.ndarray          # (N, 3) float
    faces: np.ndarray             # (M, 3) int

    @property
    def n_vertices(self) -> int:
        return int(self.vertices.shape[0])

    @property
    def n_faces(self) -> int:
        return int(self.faces.shape[0])


@dataclass
class PropellerGeometry:
    backend: str
    parts: dict
    sections: dict
    params: dict
    meta: dict = field(default_factory=dict)

    def ordered_parts(self):
        """Parts in a stable order: the known ones first, then any extras."""
        known = [n for n in PART_ORDER if n in self.parts]
        extra = sorted(n for n in self.parts if n not in PART_ORDER)
        return [(n, self.parts[n]) for n in known + extra]

    def bounds(self):
        """``(min_xyz, max_xyz)`` over every part, as float arrays."""
        allv = np.vstack([p.vertices for p in self.parts.values()])
        return allv.min(axis=0), allv.max(axis=0)

    def summary(self) -> str:
        bits = ["%s=%dv/%df" % (n, p.n_vertices, p.n_faces)
                for n, p in self.ordered_parts()]
        return "%s: %s" % (self.backend, " ".join(bits))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build(params, backend="feg", *, node_bin=None, gh_path=None,
          rhino_url=None, rhino_api_key=None, timeout=180):
    """Build the propeller with *backend*.  Raises :class:`GeometryError`."""
    if backend not in BACKENDS:
        raise GeometryError(
            "Unknown geometry backend %r; expected one of %s." % (backend, ", ".join(BACKENDS))
        )
    t0 = time.time()
    if backend == "feg":
        geom = _build_feg(params, node_bin=node_bin, timeout=timeout)
    else:
        geom = _build_rhino(params, gh_path=gh_path, rhino_url=rhino_url,
                            rhino_api_key=rhino_api_key, timeout=timeout)
    geom.meta["build_seconds"] = round(time.time() - t0, 3)
    geom.meta["ring"] = airfoil.ring_dimensions(params)
    return geom


def _python_sections(params):
    return {k: airfoil.build_section_3d(k, params) for k in airfoil.SECTION_KINDS}


# ---------------------------------------------------------------------------
# FEG backend (headless Node)
# ---------------------------------------------------------------------------

def _resolve_node(node_bin):
    exe = node_bin or os.environ.get("PROPELLER_STUDIO_NODE") or "node"
    found = shutil.which(exe)
    if not found:
        raise GeometryError(
            "The 'feg' backend needs Node.js on PATH (looked for %r).  Install "
            "Node 18+, or pass --node-bin with the full path to node.exe." % exe
        )
    return found


def _build_feg(params, *, node_bin=None, timeout=180):
    node = _resolve_node(node_bin)
    if not _EXPORTER.is_file():
        raise GeometryError("FEG exporter missing at %s" % _EXPORTER)

    payload = json.dumps({k: v for k, v in params.items() if not k.startswith("__")})
    try:
        proc = subprocess.run(
            [node, str(_EXPORTER), payload],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(_EXPORTER.parent),
        )
    except subprocess.TimeoutExpired:
        raise GeometryError("FEG export timed out after %ss." % timeout) from None
    except OSError as exc:
        raise GeometryError("Could not run Node: %s" % exc) from exc

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        hint = ""
        if "Cannot find package 'three'" in detail or "ERR_MODULE_NOT_FOUND" in detail:
            hint = ("\nThe 'three' package is not resolvable from %s.  Run "
                    "`npm install` in the repository root." % _EXPORTER.parent)
        raise GeometryError("FEG export failed (exit %s):\n%s%s"
                            % (proc.returncode, detail, hint))

    try:
        raw = json.loads(proc.stdout)
    except ValueError as exc:
        raise GeometryError("FEG exporter returned unreadable JSON: %s" % exc) from exc

    parts = {}
    for name, p in raw.get("parts", {}).items():
        verts = np.asarray(p["positions"], dtype=float).reshape(-1, 3)
        faces = np.asarray(p["indices"], dtype=np.int64).reshape(-1, 3)
        parts[name] = Part(name, verts, faces)
    if not parts:
        raise GeometryError("FEG exporter produced no geometry.")

    sections = _python_sections(params)

    # Drift alarm: the exporter's own curves vs the Python port.  The exporter
    # closes each loop with a repeated first point, so compare the common head.
    worst = 0.0
    for key, js_pts in (raw.get("sections") or {}).items():
        if key not in sections:
            continue
        a = np.asarray(js_pts, dtype=float)
        b = sections[key]
        n = min(len(a), len(b))
        if n:
            worst = max(worst, float(np.abs(a[:n] - b[:n]).max()))

    meta = dict(raw.get("meta") or {})
    meta["section_agreement_mm"] = worst
    meta["node"] = node
    return PropellerGeometry("feg", parts, sections, dict(params), meta)


# ---------------------------------------------------------------------------
# RhinoCompute backend
# ---------------------------------------------------------------------------

def _default_gh_path():
    """The Grasshopper definition, searched where it lives in this repository
    and then where a standalone checkout would keep it."""
    for cand in (
        Path(os.environ.get("PROPELLER_STUDIO_GH", "")) if os.environ.get("PROPELLER_STUDIO_GH") else None,
        _HERE.parents[1] / "tools" / "generate_mesh" / "Propeller_Raul_V1.2.gh",
        _HERE / "Propeller_Raul_V1.2.gh",
        _HERE.parent / "Propeller_Raul_V1.2.gh",
    ):
        if cand and cand.is_file():
            return cand
    return None


def _preflight(url, timeout=5):
    """Confirm a RhinoCompute server answers before sending a definition.

    Without this the failure surfaces as a connection traceback from deep
    inside the client library, which reads like a bug in this tool rather than
    "your server is not running".
    """
    import requests

    probe = url if url.endswith("/") else url + "/"
    try:
        requests.get(probe + "version", timeout=timeout)
    except Exception:
        try:
            requests.get(probe, timeout=timeout)
        except Exception as exc:
            raise GeometryError(
                "RhinoCompute is not reachable at %s (%s).\n"
                "Start your local RhinoCompute server, or pass --rhino-url, or "
                "switch to the 'feg' backend with --backend feg.\n"
                "This tool never silently substitutes one backend for the "
                "other -- a drawing labelled RhinoCompute must BE RhinoCompute."
                % (url, type(exc).__name__)
            ) from exc


def _extract_draco_strings(item):
    out = []
    for bk in sorted((item.get("InnerTree") or {}).keys()):
        for leaf in item["InnerTree"][bk]:
            data = leaf.get("data", "")
            if isinstance(data, str):
                data = data.strip().strip('"')
            if data:
                out.append(data)
    return out


def _build_rhino(params, *, gh_path=None, rhino_url=None, rhino_api_key=None,
                 timeout=180):
    try:
        import base64
        import DracoPy
        import compute_rhino3d.Grasshopper as gh_compute
        import compute_rhino3d.Util
    except ImportError as exc:
        raise GeometryError(
            "The 'rhino' backend needs compute-rhino3d and DracoPy:\n"
            "    .venv-studio/Scripts/python -m pip install compute-rhino3d DracoPy\n"
            "(%s)" % exc
        ) from exc

    gh = Path(gh_path) if gh_path else _default_gh_path()
    if gh is None or not gh.is_file():
        raise GeometryError(
            "Grasshopper definition not found.  Pass --gh-path, or set "
            "PROPELLER_STUDIO_GH, pointing at Propeller_Raul_V1.2.gh."
        )

    url = rhino_url or os.environ.get("RHINO_COMPUTE_URL") or "http://localhost:6500/"
    key = rhino_api_key if rhino_api_key is not None else os.environ.get("RHINO_COMPUTE_API_KEY", "")
    _preflight(url)

    compute_rhino3d.Util.url = url
    if key:
        compute_rhino3d.Util.apiKey = key

    # The ring height is DERIVED, not an input: inject the fitted height into
    # the .gh's impellerHeight port so the Rhino ring matches the FEG one.
    values = {k: v for k, v in params.items() if not k.startswith("__")}
    values["impellerHeight"] = airfoil.fitted_ring_height(params)

    # DataTree.Append formats the path key as "0" rather than "{0}", which
    # RhinoCompute rejects, so the trees are built by hand.
    trees = []
    for name, value in values.items():
        dtype = "System.Int32" if isinstance(value, int) and not isinstance(value, bool) else "System.Double"
        trees.append(type("Tree", (), {"data": {
            "ParamName": name,
            "InnerTree": {"{0}": [{"type": dtype, "data": str(value)}]},
        }})())

    try:
        output = gh_compute.EvaluateDefinition(str(gh), trees)
    except Exception as exc:
        raise GeometryError("RhinoCompute error while evaluating %s: %s" % (gh.name, exc)) from exc

    items = output.get("values", []) if isinstance(output, dict) else output

    # Prefer the COMPONENTS over the merged MeshFinal -- the opposite of the
    # agent pipeline's preference, and deliberately so: this tool colours parts
    # individually, and MeshFinal arrives as one anonymous body.
    named = {}
    for item in items:
        pname = item.get("ParamName", "")
        base = pname.rsplit(".", 1)[-1]
        if base in _RHINO_PART_NAMES:
            named.setdefault(base, []).extend(_extract_draco_strings(item))

    parts = {}
    if named:
        for gh_name, blobs in named.items():
            part = _decode_part(_RHINO_PART_NAMES[gh_name], blobs, DracoPy, base64)
            if part is not None:
                parts[part.name] = part

    if not parts:
        blobs = []
        for item in items:
            if "MeshFinal" in item.get("ParamName", ""):
                blobs.extend(_extract_draco_strings(item))
        part = _decode_part("body", blobs, DracoPy, base64)
        if part is not None:
            parts["body"] = part

    if not parts:
        available = [i.get("ParamName", "?") for i in items]
        raise GeometryError(
            "RhinoCompute returned no decodable mesh.  Outputs seen: %s" % available
        )

    meta = {
        "gh": str(gh),
        "url": url,
        "merged_only": list(parts) == ["body"],
        "bladeCount": int(params.get("bladeCount", 0)),
    }
    return PropellerGeometry("rhino", parts, _python_sections(params), dict(params), meta)


def _decode_part(name, blobs, DracoPy, base64):
    """Decode and concatenate the Draco blobs of one part."""
    verts, faces, offset = [], [], 0
    for b64 in blobs:
        try:
            mesh = DracoPy.decode(base64.b64decode(b64))
        except Exception:
            continue
        v = np.asarray(mesh.points, dtype=float).reshape(-1, 3)
        f = np.asarray(mesh.faces, dtype=np.int64).reshape(-1, 3)
        verts.append(v)
        faces.append(f + offset)
        offset += len(v)
    if not verts:
        return None
    return Part(name, np.vstack(verts), np.vstack(faces))
