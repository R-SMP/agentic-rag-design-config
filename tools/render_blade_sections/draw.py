"""PIL drawing for the Blade-sections render (no langchain — pure PIL).

Kept separate from ``render_blade_sections.py`` (the ``@tool`` wrapper) so the
rendering can be unit-tested without the langchain / agent dependencies.
Produces the same look as the in-browser ``web/feg/sections_view.js``: three
airfoils stacked Inner -> Middle -> Outer, each rotated by its angle of
attack, colour-coded with a name label (in a left gutter so it never overlaps
the airfoils), translucent-filled + stroked, on an optional light 1 mm grid,
with a bottom-right angle protractor whose vertex is at the bottom-LEFT so the
angles open COUNTERCLOCKWISE (up-right) from the horizontal.

The whole scene is drawn at ``_SUPERSAMPLE``x and downscaled with LANCZOS, so
the lines and text are crisp/antialiased rather than jagged.  The canvas is
sized tightly to the content.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

from tools.render_blade_sections.sections_geom import build_section_points

try:  # Pillow >= 9.1 moved the resampling enum
    _LANCZOS = Image.Resampling.LANCZOS
except AttributeError:  # pragma: no cover - older Pillow
    _LANCZOS = Image.LANCZOS


# Top-to-bottom order + per-section colour (matches web/feg/sections_view.js).
SECTIONS = (
    ("inner", "Inner", "innerAngle", (37, 99, 235)),    # blue
    ("middle", "Middle", "middleAngle", (22, 163, 74)),  # green
    ("outer", "Outer", "outerAngle", (220, 38, 38)),     # red
)

# Logical (final-image) constants.  The scene is rendered at _SUPERSAMPLE x
# these and downscaled, so everything stays crisp.
#
# The WHOLE layout was scaled x(18/11) from the earlier PX_PER_MM=11 tuning so
# the render is ~1.6x larger natively (~690x285) and stays legible when a
# side-by-side comparison (view_images match_height=640) scales it up — WITHOUT
# upscaling it 3-4x.  All the layout + font constants scale together, so the
# section/label/protractor BALANCE from the rebalance is preserved.
PX_PER_MM = 18         # final px per mm → 1 mm grid square = 18 px
_MARGIN = 26
_GAP = 29              # vertical gap between stacked sections
_LABEL_GUTTER = 98     # left column reserved for the Inner/Middle/Outer labels
_PROT_R = 183          # protractor radius
_SUPERSAMPLE = 3
_BG = (247, 247, 247)
_GRID_MINOR = (221, 221, 221)
_GRID_MAJOR = (198, 198, 198)
_MAJOR_EVERY_MM = 5
_PROTRACTOR_MAX_DEG = 25

# Text sizes (final px).  Scaled with the layout above so the labels stay
# legible next to the section shapes (which scale with the physical mm size).
_FONT_LABEL = 36       # Inner / Middle / Outer name labels
_FONT_TITLE = 29       # protractor "Angle of attack" title
_FONT_ANGLE = 26       # per-ray angle values


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


def _draw_grid(draw, w, h, ppm, lw):
    for color, step in ((_GRID_MINOR, ppm), (_GRID_MAJOR, ppm * _MAJOR_EVERY_MM)):
        x = 0.0
        while x <= w:
            px = round(x)
            draw.line([(px, 0), (px, h)], fill=color, width=lw)
            x += step
        y = 0.0
        while y <= h:
            py = round(y)
            draw.line([(0, py), (w, py)], fill=color, width=lw)
            y += step


def _draw_protractor(draw, vx, vy, r, secs, font_title, font_small, ss):
    """Vertex at the bottom-LEFT (vx, vy): the 0 deg baseline points RIGHT and
    angles open COUNTERCLOCKWISE (up-right).  Panel hugs the 0-25 deg wedge
    with a centred title just above it."""
    max_deg = _PROTRACTOR_MAX_DEG
    top = vy - r * math.sin(math.radians(max_deg))   # y of the highest ray tip

    panel_left = vx - 10 * ss
    panel_right = vx + r + 40 * ss
    panel_top = top - 42 * ss   # title band — scaled with _FONT_TITLE (18->29)
    panel_bottom = vy + 8 * ss
    draw.rectangle([panel_left, panel_top, panel_right, panel_bottom],
                   fill=(255, 255, 255), outline=(208, 208, 208), width=ss)

    title = "Angle of attack"
    tw = draw.textlength(title, font=font_title)
    cxp = (panel_left + panel_right) / 2.0
    draw.text((cxp - tw / 2.0, panel_top + 6 * ss), title,
              fill=(90, 90, 90), font=font_title)

    # Baseline (0 deg) + arc + 5 deg ticks.
    draw.line([(vx, vy), (vx + r, vy)], fill=(150, 150, 150), width=ss)
    arc = [(vx + r * math.cos(math.radians(d)), vy - r * math.sin(math.radians(d)))
           for d in range(0, max_deg + 1)]
    draw.line(arc, fill=(150, 150, 150), width=ss)
    for d in range(0, max_deg + 1, 5):
        a = math.radians(d)
        c, s = math.cos(a), math.sin(a)
        draw.line([(vx + (r - 6 * ss) * c, vy - (r - 6 * ss) * s),
                   (vx + r * c, vy - r * s)], fill=(176, 176, 176), width=ss)

    # One ray per section, in its colour, + its degree value just past the tip.
    for sec in secs:
        ang = max(0.0, min(float(max_deg), sec["angle"]))
        a = math.radians(ang)
        c, s = math.cos(a), math.sin(a)
        ex, ey = vx + r * c, vy - r * s
        draw.line([(vx, vy), (ex, ey)], fill=sec["color"], width=2 * ss)
        draw.text((vx + (r + 5 * ss) * c, vy - (r + 5 * ss) * s - 7 * ss),
                  f"{round(sec['angle'])}°", fill=sec["color"], font=font_small)


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

    # Render at SUPERSAMPLE x, then downscale (LANCZOS) for crisp antialiasing.
    ss = _SUPERSAMPLE
    ppm = PX_PER_MM * ss
    margin = _MARGIN * ss
    gap = _GAP * ss
    gutter = _LABEL_GUTTER * ss

    sec_col_w = max(s["w"] for s in secs) * ppm
    band_h = [max(1.0, s["h"] * ppm) for s in secs]
    content_h = sum(band_h) + gap * (len(secs) - 1)

    # Protractor in its own column on the right; box only as tall as the
    # 0-25 deg wedge (plus the title).
    prot_r = _PROT_R * ss
    prot_box_w = prot_r + 44 * ss
    prot_box_h = int(prot_r * math.sin(math.radians(_PROTRACTOR_MAX_DEG))) + 52 * ss
    gap_x = 16 * ss

    w = int(round(margin + gutter + sec_col_w + gap_x + prot_box_w + margin))
    h = int(round(margin + max(content_h, prot_box_h) + margin))
    sec_cx = margin + gutter + sec_col_w / 2.0

    y = float(margin)
    for i, s in enumerate(secs):
        bh = band_h[i]
        cy = y + bh / 2.0
        s["cy"] = cy
        s["px"] = [
            (sec_cx + (px - s["cx"]) * ppm, cy - (pz - s["cz"]) * ppm)
            for (px, pz) in s["pts"]
        ]
        y += bh + gap

    base = Image.new("RGBA", (w, h), _BG + (255,))
    draw = ImageDraw.Draw(base)
    if grid:
        _draw_grid(draw, w, h, ppm, ss)

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for s in secs:
        odraw.polygon(s["px"], fill=s["color"] + (46,))
    base = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(base)

    font = _load_font(_FONT_LABEL * ss)
    font_title = _load_font(_FONT_TITLE * ss)
    font_small = _load_font(_FONT_ANGLE * ss)
    for s in secs:
        draw.line(s["px"] + [s["px"][0]], fill=s["color"], width=2 * ss, joint="curve")
        # Label in the left gutter, vertically centred on the section.
        lb = font.getbbox(s["label"])
        draw.text((margin, s["cy"] - (lb[1] + lb[3]) / 2.0), s["label"],
                  fill=s["color"], font=font)

    # Vertex at the bottom-LEFT of the protractor column (rays open up-right).
    _draw_protractor(draw, w - margin - prot_box_w + 8 * ss, h - margin, prot_r,
                     secs, font_title, font_small, ss)

    final = base.convert("RGB").resize((w // ss, h // ss), _LANCZOS)
    final.save(str(out_path))
    return final.size
