"""FEG render demo — build a propeller with the browser FEG geometry (headless
Node, reusing web/feg/*) and render it, so you can see how the agent-facing
renders come out.

Two render modes:
  * default (LOCAL, no Docker): a self-contained PIL software rasteriser —
    flat-shaded, depth-sorted, 3 views (isometric/top/side).  Approximate
    style; runs anywhere PIL + Node are available.  Files: preview_*.png
  * --render-mesh (FAITHFUL): the REAL agent pipeline (tools/render_mesh,
    pyrender, 800x600, 3 views).  Run this INSIDE the app container (it needs
    pyrender + OSMesa).  Files: render_*.png

Requires Node (host) for geometry generation unless you pass an existing --obj.
Reuses web/feg/* verbatim, so the geometry matches the browser live preview.

Usage:
  python extra_utilities/feg_render_demo.py                     # local PIL preview
  python extra_utilities/feg_render_demo.py --render-mesh       # faithful (in container)
  python extra_utilities/feg_render_demo.py --obj some.obj      # render an existing OBJ
  python extra_utilities/feg_render_demo.py --params '{...}'    # custom 17 params

Outputs to extra_utilities/feg_render_examples/ (override with --out).
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
EXPORTER = ROOT / "tools" / "generate_mesh" / "feg_export.mjs"
DEFAULT_OUT = ROOT / "extra_utilities" / "feg_render_examples"

# A representative in-range sample (matches the Task-3 sketch's section dims).
DEFAULT_PARAMS = {
    "bladeCount": 5, "impellerRadius": 70, "impellerHeight": 8,
    "impellerThickness": 3,
    "innerThickness": 12, "innerMaxPos": 4, "innerCamber": 4,
    "innerChord": 10, "innerAngle": 23,
    "middlePos": 0.5, "middleChord": 30, "middleAngle": 22,
    "outerThickness": 8, "outerMaxPos": 4, "outerCamber": 3,
    "outerChord": 20, "outerAngle": 15,
}

# (name, eye-direction-from-centre, up) — identical to tools/render_mesh.
VIEWS = [
    ("isometric", (1.0, 1.0, 0.7), (0.0, 0.0, 1.0)),
    ("top",       (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    ("side",      (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
]


def generate_obj(params, out_obj):
    """Run the headless-Node FEG exporter -> OBJ text -> file."""
    if not EXPORTER.is_file():
        sys.exit(f"FEG exporter not found: {EXPORTER}")
    proc = subprocess.run(
        ["node", str(EXPORTER), json.dumps(params)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        sys.exit(f"node FEG export failed:\n{proc.stderr}")
    out_obj.write_text(proc.stdout, encoding="utf-8")
    sys.stderr.write(proc.stderr)  # the exporter's stats line
    return out_obj


# --------------------------------------------------------------------------
# Self-contained PIL software rasteriser (pure Python; no numpy / no GL)
# --------------------------------------------------------------------------
def _load_obj(path):
    verts, faces = [], []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            p = line.split()
            verts.append((float(p[1]), float(p[2]), float(p[3])))
        elif line.startswith("f "):
            idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
            if len(idx) >= 3:
                faces.append((idx[0], idx[1], idx[2]))
    return verts, faces


def _nrm(v):
    m = math.sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2]) or 1.0
    return (v[0]/m, v[1]/m, v[2]/m)
def _crs(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def _dot(a, b):
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
def _sub(a, b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])


def software_render(obj, out_dir, prefix="preview", W=800, H=600):
    verts, faces = _load_obj(obj)
    c = tuple(sum(v[i] for v in verts) / len(verts) for i in range(3))
    for name, view_dir, up in VIEWS:
        n = _nrm(view_dir)
        right = _nrm(_crs(up, n))
        camup = _crs(n, right)
        proj = [(_dot(_sub(v, c), right), _dot(_sub(v, c), camup),
                 _dot(_sub(v, c), n)) for v in verts]
        xs = [p[0] for p in proj]; ys = [p[1] for p in proj]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        pad = 0.12
        scale = min(W*(1-2*pad)/((maxx-minx) or 1),
                    H*(1-2*pad)/((maxy-miny) or 1))
        ox = W/2 - (minx+maxx)/2*scale
        oy = H/2 + (miny+maxy)/2*scale
        def scr(p):
            return (ox + p[0]*scale, oy - p[1]*scale)
        tris = []
        for (a, b, cc) in faces:
            depth = (proj[a][2]+proj[b][2]+proj[cc][2])/3.0
            fn = _nrm(_crs(_sub(verts[b], verts[a]), _sub(verts[cc], verts[a])))
            s = int(max(0, min(255, 232*(0.32+0.68*abs(_dot(fn, n))))))
            tris.append((depth, scr(proj[a]), scr(proj[b]), scr(proj[cc]), s))
        tris.sort(key=lambda t: t[0])  # painter's: far first
        img = Image.new("RGB", (W, H), (250, 250, 250))
        d = ImageDraw.Draw(img)
        for _, pa, pb, pc, s in tris:
            d.polygon([pa, pb, pc], fill=(s, s, min(255, s+10)))
        img.save(out_dir / f"{prefix}_{name}.png")
    return [out_dir / f"{prefix}_{v[0]}.png" for v in VIEWS]


def rendermesh_render(obj, out_dir):
    """Faithful render via the real render_mesh pipeline (run in the container).

    render_mesh.py lives in the ``tools`` package, whose __init__ eagerly pulls
    the whole agents stack -> a circular import when render_mesh is imported
    fresh/standalone (the app avoids it via its own import order).  Sidestep it:
    put the repo root on sys.path (for ``config``), stub the single agent
    decorator render_mesh.py imports, then load render_mesh.py BY FILE PATH so
    ``tools/__init__`` never runs.  The render code itself is reused verbatim.
    """
    import importlib.util
    import types

    base = Path("/app") if Path("/app/tools/render_mesh").is_dir() else ROOT
    sys.path.insert(0, str(base))
    for name in ("agents", "agents.shared", "agents.shared.agent_activity"):
        sys.modules.setdefault(name, types.ModuleType(name))
    sys.modules["agents.shared.agent_activity"].tool_active = (
        lambda *a, **k: (lambda fn: fn)
    )
    spec = importlib.util.spec_from_file_location(
        "_render_mesh_standalone",
        base / "tools" / "render_mesh" / "render_mesh.py",
    )
    rm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rm)

    import trimesh
    loaded = trimesh.load(str(obj))
    if isinstance(loaded, trimesh.Scene):
        mesh = trimesh.util.concatenate(list(loaded.geometry.values()))
    else:
        mesh = loaded
    return rm._render_mesh_views(mesh, out_dir)  # writes render_{view}.png


def main():
    ap = argparse.ArgumentParser(description="FEG render demo")
    ap.add_argument("--obj", help="render an existing OBJ (skip Node generation)")
    ap.add_argument("--render-mesh", action="store_true",
                    help="faithful pyrender pipeline (run inside the app container)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--params", help="JSON dict of the 17 params (default: built-in sample)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.obj:
        obj = Path(args.obj)
    else:
        params = json.loads(args.params) if args.params else DEFAULT_PARAMS
        obj = generate_obj(params, out_dir / "propeller_mesh.obj")

    if args.render_mesh:
        saved = rendermesh_render(obj, out_dir)
        print("Faithful render_mesh renders:", [Path(p).name for p in saved])
    else:
        saved = software_render(obj, out_dir)
        print("Software-preview renders:", [p.name for p in saved])
    print("Saved to:", out_dir)


if __name__ == "__main__":
    main()
