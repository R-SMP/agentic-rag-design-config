"""PIL drawing for the Blade-sections render (no langchain — pure PIL).

Kept separate from ``render_blade_sections.py`` (the ``@tool`` wrapper) so the
rendering can be unit-tested without the langchain / agent dependencies.
Produces the SAME look as the in-browser ``web/feg/sections_view.js``: three
airfoils stacked Inner -> Middle -> Outer, each rotated by its angle of
attack, colour-coded with a name label, translucent-filled + stroked, on an
optional light 1 mm grid, with a bottom-right 0-25 deg protractor whose three
rays mark the sections' angles of attack.  The canvas is sized tightly to the
content (little wasted space, small gaps).
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

from tools.render_blade_sections.sections_geom import build_section_points


# Top-to-bottom order + per-section colour (matches web/feg/sections_view.js).
SECTIONS = (
    ("inner", "Inner", "innerAngle", (37, 99, 235)),    # blue
    ("middle", "Middle", "middleAngle", (22, 163, 74)),  # green
    ("outer", "Outer", "outerAngle", (220, 38, 38)),     # red
)

PX_PER_MM = 9          # fixed real scale → 1 mm grid square = 9 px
_MARGIN = 14           # px border around the content
_GAP = 16              # px between stacked sections
_BG = (247, 247, 247)
_GRID_MINOR = (220, 220, 220)
_GRID_MAJOR = (196, 196, 196)
_MAJOR_EVERY_MM = 5
_PROTRACTOR_MAX_DEG = 25


def _load_font(size):
    for name in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _bbox(pts):
    xs = [p[0] for p in pts]
    zs = [p[1] for p in pts]
    return min(xs), max(xs), min(zs), max(zs)


def _draw_grid(draw, w, h, ppm):
    for color, step in ((_GRID_MINOR, ppm), (_GRID_MAJOR, ppm * _MAJOR_EVERY_MM)):
        x = 0.0
        while x <= w:
            px = round(x) + 0.5
            draw.line([(px, 0), (px, h)], fill=color, width=1)
            x += step
        y = 0.0
        while y <= h:
            py = round(y) + 0.5
            draw.line([(0, py), (w, py)], fill=color, width=1)
            y += step


def _draw_protractor(draw, vx, vy, r, secs, font_small):
    """Draw the angle-of-attack protractor with its vertex at (vx, vy) and
    radius r, sweeping up-left from the 0 deg baseline."""
    draw.rectangle(
        [vx - r - 12, vy - r - 22, vx + 2, vy + 2],
        fill=(255, 255, 255), outline=(208, 208, 208),
    )
    draw.text((vx - r - 10, vy - r - 20), "Angle of attack",
              fill=(102, 102, 102), font=font_small)

    draw.line([(vx, vy), (vx - r, vy)], fill=(150, 150, 150), width=1)
    arc = []
    d = 0
    while d <= _PROTRACTOR_MAX_DEG:
        a = math.radians(d)
        arc.append((vx - r * math.cos(a), vy - r * math.sin(a)))
        d += 1
    if len(arc) >= 2:
        draw.line(arc, fill=(154, 154, 154), width=1)
    for d in range(0, _PROTRACTOR_MAX_DEG + 1, 5):
        a = math.radians(d)
        c, s = math.cos(a), math.sin(a)
        draw.line(
            [(vx - (r - 5) * c, vy - (r - 5) * s), (vx - r * c, vy - r * s)],
            fill=(176, 176, 176), width=1,
        )

    for sec in secs:
        ang = max(0.0, min(float(_PROTRACTOR_MAX_DEG), sec["angle"]))
        a = math.radians(ang)
        c, s = math.cos(a), math.sin(a)
        ex, ey = vx - r * c, vy - r * s
        draw.line([(vx, vy), (ex, ey)], fill=sec["color"], width=2)
        draw.text((ex - 24, ey - 14), f"{round(sec['angle'])}°",
                  fill=sec["color"], font=font_small)


def render_png(params, grid, out_path):
    """Render the stacked sections for ``params`` to ``out_path``.

    ``params`` is the 17-param dict (only the blade-section keys are used).
    ``grid`` toggles the 1 mm reference grid.  Returns the (width, height) of
    the written PNG.
    """
    secs = []
    for kind, label, anglekey, color in SECTIONS:
        pts = build_section_points(kind, params)
        xmin, xmax, zmin, zmax = _bbox(pts)
        secs.append({
            "label": label, "color": color, "angle": float(params[anglekey]),
            "pts": pts, "w": xmax - xmin, "h": zmax - zmin,
            "cx": (xmin + xmax) / 2.0, "cz": (zmin + zmax) / 2.0,
        })

    ppm = PX_PER_MM
    sec_col_w = max(s["w"] for s in secs) * ppm
    band_h = [max(1.0, s["h"] * ppm) for s in secs]
    content_h = sum(band_h) + _GAP * (len(secs) - 1)

    # The protractor lives in its own column on the right so it never overlaps
    # the (possibly short) section stack; the canvas is sized to whichever of
    # the two is taller — tight, with no wasted space around them.
    prot_r = 92
    prot_box_w = prot_r + 34
    prot_box_h = prot_r + 30
    gap_x = 14

    w = int(round(_MARGIN + sec_col_w + gap_x + prot_box_w + _MARGIN))
    h = int(round(_MARGIN + max(content_h, prot_box_h) + _MARGIN))
    sec_cx = _MARGIN + sec_col_w / 2.0

    y = float(_MARGIN)
    for i, s in enumerate(secs):
        bh = band_h[i]
        cy = y + bh / 2.0
        s["px"] = [
            (sec_cx + (px - s["cx"]) * ppm, cy - (pz - s["cz"]) * ppm)
            for (px, pz) in s["pts"]
        ]
        s["label_xy"] = (3, max(0.0, y - 2))
        y += bh + _GAP

    base = Image.new("RGBA", (w, h), _BG + (255,))
    draw = ImageDraw.Draw(base)
    if grid:
        _draw_grid(draw, w, h, ppm)

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for s in secs:
        odraw.polygon(s["px"], fill=s["color"] + (46,))
    base = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(base)

    font = _load_font(13)
    font_small = _load_font(11)
    for s in secs:
        draw.line(s["px"] + [s["px"][0]], fill=s["color"], width=2, joint="curve")
        draw.text(s["label_xy"], s["label"], fill=s["color"], font=font)

    _draw_protractor(draw, w - _MARGIN, h - _MARGIN, prot_r, secs, font_small)

    base.convert("RGB").save(str(out_path))
    return w, h
