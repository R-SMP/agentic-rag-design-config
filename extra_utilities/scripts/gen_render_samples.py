"""Make the sample pictures of the "Render compression" settings panel.

The same as the panel's Generate samples button: every image tool of the
pack is run on each of the pack's sample parameter sets (``render_samples``
in ``dc_pack/pack.yaml``), in a process of its own, and per compression
kind the first picture of that kind is kept as
``web/render_samples/<cross|geo>_<size>.png`` (``engine/image_run.py``).

The 3D pictures need what the generator needs (Node for FEG, the pyrender
stack and OSMesa for the render), so run it INSIDE the app container; the
pack ships its own cross-section samples (``dc_pack/assets/render_samples/``)
for when none were made.

Usage:
  python extra_utilities/scripts/gen_render_samples.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "render_samples"
sys.path.insert(0, str(ROOT))


def main():
    from engine import image_run
    res = image_run.make_render_samples(OUT)
    for name in res["written"]:
        print(f"{name} -> {OUT / name}")
    for e in res["errors"]:
        print(f"FAILED ({e.get('set')}, {e.get('tool')}): {e['message']}")
    return 0 if res["written"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
