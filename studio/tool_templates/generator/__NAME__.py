"""__DISPLAY__ -- a generator (made from the Studio's generator template).

``build`` writes the model into the attempt folder (``inp.model_path``);
``render`` makes its picture, ``render_<view>.png`` beside it.  The engine
checks the parameter record, reuses a model that is already there, and joins
the two answers (engine/tooling.py).  This template builds a box whose three
sides are the first three parameter values, and draws its front view.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from engine.tooling import BuildResult, RenderResult

VIEW = "__NAME__"


def _sides(params: dict) -> tuple[float, float, float]:
    sides = [abs(float(v)) or 1.0 for v in params.values()][:3]
    while len(sides) < 3:
        sides.append(1.0)
    return sides[0], sides[1], sides[2]


def build(inp) -> BuildResult:
    x, y, z = _sides(inp.params)
    corners = [(a, b, c) for a in (0, x) for b in (0, y) for c in (0, z)]
    faces = [(1, 2, 4, 3), (5, 7, 8, 6), (1, 5, 6, 2), (3, 4, 8, 7), (1, 3, 7, 5), (2, 6, 8, 4)]
    lines = ([f"v {a:g} {b:g} {c:g}" for a, b, c in corners]
             + ["f " + " ".join(map(str, f)) for f in faces])
    inp.model_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return BuildResult(summary=f"Saved the model {inp.model_path.name} "
                               f"(a {x:g} x {y:g} x {z:g} box, 8 vertices).",
                       model_files=[inp.model_path])


def render(inp) -> RenderResult:
    x, _y, z = _sides(inp.params)
    size, pad = 400, 40
    k = (size - 2 * pad) / max(x, z)
    img = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([pad, size - pad - z * k, pad + x * k, size - pad], outline="black", width=3)
    path = inp.attempt_dir / f"render_{VIEW}.png"
    img.save(path)
    return RenderResult(report=f"Saved the picture {path} (front view).", images=[path])
