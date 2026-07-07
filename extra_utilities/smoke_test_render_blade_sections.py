"""Smoke test for the ``render_blade_sections`` tool + its geometry/draw core.

Run from the repo root (needs the full env — langchain + Pillow)::

    python extra_utilities/smoke_test_render_blade_sections.py

Covers:
  * ``sections_geom.build_section_points`` — point counts + finiteness.
  * ``draw.render_png`` — writes a valid PNG (default / min / max, grid on and
    off), sizes are sane, and the grid version differs from the no-grid one.
  * the ``@tool`` wrapper — writes ``render_blade_sections[_grid].png`` into an
    attempt folder under ``ATTEMPTS_DIR`` and returns OK; rejects a missing
    key, a non-numeric value, and a path outside the attempts directory.

No network / LLM calls — purely local rendering + validation.
"""

import json
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import PIL.ImageChops as ImageChops  # noqa: E402
from PIL import Image  # noqa: E402

from config import ATTEMPTS_DIR  # noqa: E402
from tools.render_blade_sections.draw import render_png  # noqa: E402
from tools.render_blade_sections.render_blade_sections import (  # noqa: E402
    render_blade_sections,
)
from tools.render_blade_sections.sections_geom import (  # noqa: E402
    COUNT_I,
    build_section_points,
)

DEFAULT = {
    "bladeCount": 3, "impellerRadius": 71,
    "impellerThickness": 2,
    "innerThickness": 6, "innerMaxPos": 4, "innerCamber": 4, "innerChord": 11,
    "innerAngle": 25,
    "middlePos": 0.3, "middleChord": 20, "middleAngle": 15,
    "outerThickness": 6, "outerMaxPos": 4, "outerCamber": 4, "outerChord": 15,
    "outerAngle": 10,
}
MINS = {
    "innerThickness": 3, "innerMaxPos": 2, "innerCamber": 0, "innerChord": 3,
    "innerAngle": 2, "middlePos": 0.3, "middleChord": 10, "middleAngle": 2,
    "outerThickness": 3, "outerMaxPos": 2, "outerCamber": 0, "outerChord": 10,
    "outerAngle": 2,
}
MAXS = {
    "innerThickness": 24, "innerMaxPos": 8, "innerCamber": 9, "innerChord": 11,
    "innerAngle": 25, "middlePos": 0.7, "middleChord": 30, "middleAngle": 25,
    "outerThickness": 24, "outerMaxPos": 8, "outerCamber": 9, "outerChord": 30,
    "outerAngle": 25,
}

_failures = []


def check(cond, msg):
    print(("  ok  " if cond else "FAIL  ") + msg)
    if not cond:
        _failures.append(msg)


# --- 1. geometry --------------------------------------------------------------
for kind in ("inner", "middle", "outer"):
    pts = build_section_points(kind, DEFAULT)
    check(len(pts) == 2 * COUNT_I + 1, f"geom {kind}: {len(pts)} points")
    check(all(math.isfinite(x) and math.isfinite(z) for (x, z) in pts),
          f"geom {kind}: all finite")

# --- 2. draw.render_png -------------------------------------------------------
_tmp = tempfile.mkdtemp()
try:
    a = os.path.join(_tmp, "a.png")
    b = os.path.join(_tmp, "b.png")
    w, h = render_png(DEFAULT, False, a)
    with Image.open(a) as im:
        check(os.path.exists(a) and im.size == (w, h),
              f"render_png plain → valid {w}x{h} PNG")
    render_png(DEFAULT, True, b)
    with Image.open(a) as ia, Image.open(b) as ib:
        diff = ImageChops.difference(ia.convert("RGB"), ib.convert("RGB")).getbbox()
    check(diff is not None, "grid version differs from no-grid")
    for nm, pp in (("mins", MINS), ("maxs", MAXS)):
        wp, hp = render_png(pp, True, os.path.join(_tmp, nm + ".png"))
        check(wp > 0 and hp > 0, f"render_png {nm} → {wp}x{hp}")
finally:
    shutil.rmtree(_tmp, ignore_errors=True)

# --- 3. the @tool wrapper -----------------------------------------------------
attempt_dir = ATTEMPTS_DIR / "smoke_render_blade_sections"
attempt_dir.mkdir(parents=True, exist_ok=True)
try:
    pj = attempt_dir / "parameters.json"
    pj.write_text(json.dumps(DEFAULT), encoding="utf-8")

    res = render_blade_sections.invoke({"parameters_path": str(pj), "grid": False})
    check(res.startswith("render_blade_sections: OK"), f"tool OK → {res[:70]}")
    check((attempt_dir / "render_blade_sections.png").exists(),
          "wrote render_blade_sections.png")

    render_blade_sections.invoke({"parameters_path": str(pj), "grid": True})
    check((attempt_dir / "render_blade_sections_grid.png").exists(),
          "wrote render_blade_sections_grid.png (grid variant)")

    bad = dict(DEFAULT)
    del bad["innerChord"]
    bpj = attempt_dir / "bad.json"
    bpj.write_text(json.dumps(bad), encoding="utf-8")
    rbad = render_blade_sections.invoke({"parameters_path": str(bpj), "grid": False})
    check("FAILED" in rbad and "missing" in rbad, "missing key rejected")

    nbad = dict(DEFAULT)
    nbad["innerChord"] = "wide"
    npj = attempt_dir / "nonnum.json"
    npj.write_text(json.dumps(nbad), encoding="utf-8")
    rnum = render_blade_sections.invoke({"parameters_path": str(npj), "grid": False})
    check("FAILED" in rnum and "not" in rnum, "non-numeric value rejected")

    outside = tempfile.mkdtemp()
    try:
        opj = os.path.join(outside, "parameters.json")
        with open(opj, "w", encoding="utf-8") as fh:
            json.dump(DEFAULT, fh)
        rout = render_blade_sections.invoke({"parameters_path": opj, "grid": False})
        check("FAILED" in rout and "outside" in rout,
              "path outside attempts/ rejected")
    finally:
        shutil.rmtree(outside, ignore_errors=True)
finally:
    shutil.rmtree(attempt_dir, ignore_errors=True)

print()
if _failures:
    print(f"{len(_failures)} FAILURE(S)")
    sys.exit(1)
print("ALL PASS")
