"""Generate the fixed sample renders for the "Render compression" settings panel.

Writes 6 PNGs into ``web/render_samples/``:
  cross_{small,medium,large}.png — blade-section diagrams (pure PIL; runs anywhere)
  geo_{small,medium,large}.png   — 3D isometric mesh renders (FEG geometry via
                                   headless Node + the pyrender pipeline)

The 3D geometry samples need the FEG exporter (Node) + the render_mesh pyrender
stack (OSMesa), so run ``--geo`` INSIDE the app container.  The cross-section
samples are pure PIL and run anywhere.  See extra_utilities/feg_render_demo.py
for the same sidestep-import + OSMesa notes.

Usage:
  python extra_utilities/gen_render_samples.py --cross   # cross-sections only (local)
  python extra_utilities/gen_render_samples.py --geo     # 3D isometrics (container)
  python extra_utilities/gen_render_samples.py           # both
"""
import argparse
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "render_samples"
EXPORTER = ROOT / "tools" / "generate_mesh" / "feg_export.mjs"

# small / medium / large propellers — vary diameter, chords, and angles so the
# samples span the render-size range the compression slider is tuned against.
_BASE = dict(impellerThickness=2, innerMaxPos=4, outerMaxPos=4, middlePos=0.6)
SIZES = {
    "small": dict(_BASE, bladeCount=3, impellerRadius=60,
                  innerThickness=8, innerCamber=1, innerChord=4, innerAngle=8,
                  middleChord=12, middleAngle=12,
                  outerThickness=8, outerCamber=2, outerChord=8, outerAngle=16),
    "medium": dict(_BASE, bladeCount=5, impellerRadius=70,
                   innerThickness=5, innerCamber=1, innerChord=7, innerAngle=10,
                   middleChord=22, middleAngle=15,
                   outerThickness=6, outerCamber=2, outerChord=16, outerAngle=20),
    "large": dict(_BASE, bladeCount=6, impellerRadius=80,
                  innerThickness=6, innerCamber=2, innerChord=12, innerAngle=12,
                  middleChord=30, middleAngle=18,
                  outerThickness=7, outerCamber=3, outerChord=30, outerAngle=24),
}


def _load_by_path(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def gen_cross():
    """3 blade-section diagrams via tools/render_blade_sections/draw.py."""
    for n in ("tools", "tools.render_blade_sections"):
        m = types.ModuleType(n); m.__path__ = []; sys.modules.setdefault(n, m)
    _load_by_path("tools.render_blade_sections.sections_geom",
                  ROOT / "tools/render_blade_sections/sections_geom.py")
    draw = _load_by_path("tools.render_blade_sections.draw",
                         ROOT / "tools/render_blade_sections/draw.py")
    for size, p in SIZES.items():
        dst = OUT / f"cross_{size}.png"
        w, h = draw.render_png(p, False, dst)
        print(f"cross_{size}: {w}x{h} -> {dst}")


def gen_geo():
    """3 isometric 3D renders: FEG geometry (Node) -> OBJ -> render_mesh pyrender."""
    import trimesh
    base = Path("/app") if Path("/app/tools/render_mesh").is_dir() else ROOT
    sys.path.insert(0, str(base))
    for n in ("agents", "agents.shared", "agents.shared.agent_activity"):
        sys.modules.setdefault(n, types.ModuleType(n))
    sys.modules["agents.shared.agent_activity"].tool_active = (
        lambda *a, **k: (lambda fn: fn))
    rm = _load_by_path("_render_mesh_standalone",
                       base / "tools/render_mesh/render_mesh.py")
    for size, p in SIZES.items():
        proc = subprocess.run(["node", str(EXPORTER), json.dumps(p)],
                              capture_output=True, text=True, timeout=180)
        if proc.returncode != 0:
            print(f"geo_{size}: FEG export FAILED:\n{proc.stderr}")
            continue
        obj = OUT / f"_geo_{size}.obj"
        obj.write_text(proc.stdout, encoding="utf-8")
        loaded = trimesh.load(str(obj))
        mesh = (trimesh.util.concatenate(list(loaded.geometry.values()))
                if isinstance(loaded, trimesh.Scene) else loaded)
        tmp = OUT / f"_tmp_{size}"
        tmp.mkdir(exist_ok=True)
        rm._render_mesh_views(mesh, tmp)   # writes render_isometric/_top/_side.png
        (OUT / f"geo_{size}.png").write_bytes((tmp / "render_isometric.png").read_bytes())
        for f in tmp.iterdir():
            f.unlink()
        tmp.rmdir()
        obj.unlink()
        print(f"geo_{size}: isometric -> {OUT / f'geo_{size}.png'}")


def main():
    ap = argparse.ArgumentParser(description="Render-compression sample generator")
    ap.add_argument("--cross", action="store_true", help="cross-section samples only")
    ap.add_argument("--geo", action="store_true", help="3D isometric samples only")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    both = not (args.cross or args.geo)
    if args.cross or both:
        gen_cross()
    if args.geo or both:
        gen_geo()


if __name__ == "__main__":
    main()
