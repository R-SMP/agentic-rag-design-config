"""__DISPLAY__ -- a geometry tool (made from the Studio's geometry template).

``make_model`` gets the parameter values (already checked against the
setup's parameters.json: complete, typed, in order) and returns the model in
the format the manifest declares; it writes nothing and raises ToolError
when it cannot (engine/tooling.py).  This template returns a box whose three
sides are the first three parameter values.
"""

from __future__ import annotations

from engine.tooling import GeometryResult


def make_model(params: dict) -> GeometryResult:
    sides = [abs(float(v)) or 1.0 for v in params.values()][:3]
    while len(sides) < 3:
        sides.append(1.0)
    x, y, z = sides
    corners = [(a, b, c) for a in (0, x) for b in (0, y) for c in (0, z)]
    faces = [(1, 2, 4, 3), (5, 7, 8, 6), (1, 5, 6, 2), (3, 4, 8, 7), (1, 3, 7, 5), (2, 6, 8, 4)]
    lines = ([f"v {a:g} {b:g} {c:g}" for a, b, c in corners]
             + ["f " + " ".join(map(str, f)) for f in faces])
    return GeometryResult(model="\n".join(lines) + "\n", vertex_count=len(corners))
