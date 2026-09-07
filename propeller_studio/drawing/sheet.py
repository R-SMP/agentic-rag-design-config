"""The technical drawing sheet.

Composes one ISO sheet: frame, title block, the 3D views with their outline
overlaid, and the dimensioned blade sections beside them -- all in a single
image, as asked.  Every element is switchable from the settings tree.

Both bands are drawn TO A STATED SCALE chosen from the standard series, and the
scale is printed in the title block.  Auto-framing each panel to fill its box
would look tidier and be a lie: a drawing that names a scale has to be at it.

Layout is packed TOP-DOWN at each band's *needed* height rather than split by a
fixed fraction.  The scale series is coarse -- 1:1 then 1:2 -- so a fixed split
routinely leaves a third of a band empty while the other band is cramped.
"""

from __future__ import annotations

import datetime as _dt

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

from propeller_studio import params as P
from propeller_studio import settings as S
from propeller_studio.drawing import sections as SEC
from propeller_studio.render import scene

MM = 1.0 / 25.4          # mm -> inches

# Standard scale series as paper-mm per model-mm, largest first.  The ISO 5455
# decade values plus the 2.5 and 4 steps that drawings use in practice: with the
# decade series alone, an available 3.9x rounds all the way down to 2:1 and
# throws away half the panel.
SCALE_SERIES = (100, 50, 20, 10, 5, 4, 2.5, 2, 1,
                0.5, 0.4, 0.25, 0.2, 0.1, 0.05, 0.04, 0.025, 0.02, 0.01)

# The padding factors below are already generous, so a scale that overshoots the
# computed fit by a few percent still fits comfortably.  Without this, a fit of
# 3.99 would drop to 2.5 for want of 0.3 %.
SCALE_TOLERANCE = 1.04

CAPTION_H = 6.0          # mm reserved above a panel for its caption
BAND_GAP = 5.0
PANEL_PAD = 3.0

# Room a section panel needs beyond the airfoil itself, as multiples of the
# widest / tallest section: chord dimension below, leaders above, value table.
SEC_PAD_W = 1.18
SEC_PAD_H = 1.62


def nice_scale(max_scale):
    """Largest standard scale that still fits within *max_scale*."""
    limit = max_scale * SCALE_TOLERANCE
    for s in SCALE_SERIES:
        if s <= limit:
            return s
    return SCALE_SERIES[-1]


def scale_text(s):
    if s >= 1:
        return "%g : 1" % s
    return "1 : %g" % round(1.0 / s, 4)


def _bounding_radius(geom):
    """Radius of the smallest sphere about the model centre.

    View-INDEPENDENT on purpose: every orthographic direction then shares one
    scale, which is what lets the title block state a single number.
    """
    lo, hi = geom.bounds()
    center = (lo + hi) / 2.0
    allv = np.vstack([p.vertices for p in geom.parts.values()])
    return float(np.linalg.norm(allv - center, axis=1).max())


def _axes(fig, rect_mm, sheet_mm):
    """Add an axes from a millimetre rectangle (x, y, w, h) on the sheet."""
    W, H = sheet_mm
    x, y, w, h = rect_mm
    return fig.add_axes([x / W, y / H, w / W, h / H])


def _blank(ax):
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    return ax


def _section_needs(kinds, params):
    """Widest and tallest section, padded for the annotations around them."""
    need_w = need_h = 0.0
    for k in kinds:
        w, h = SEC.section_span(k, params)
        need_w, need_h = max(need_w, w), max(need_h, h)
    return max(need_w, 1.0) * SEC_PAD_W, max(need_h, 1.0) * SEC_PAD_H


def render_sheet(geom, s, *, out_paths, title=None, warnings=()):
    """Draw the sheet for *geom* and write it to every path in *out_paths*.

    ``out_paths`` maps format -> Path (``{"png": ..., "pdf": ..., "svg": ...}``).
    Returns the metadata the manifest records.
    """
    d = s["drawing"]
    sheet = d["sheet"]
    W, H = S.sheet_size_mm(sheet)
    margin = float(sheet["margin_mm"])
    params = geom.params

    fig = plt.figure(figsize=(W * MM, H * MM), dpi=int(d["dpi"]))
    fig.patch.set_facecolor("white")

    frame = (margin, margin, W - 2 * margin, H - 2 * margin)
    fax = None
    if sheet["frame"]:
        fax = _blank(fig.add_axes([0, 0, 1, 1]))
        fax.set_xlim(0, W)
        fax.set_ylim(0, H)
        fax.patch.set_alpha(0)
        fax.add_patch(Rectangle((frame[0], frame[1]), frame[2], frame[3],
                                fill=False, ec="#222222", lw=1.1))
        fax.add_patch(Rectangle((frame[0] + 1.2, frame[1] + 1.2),
                                frame[2] - 2.4, frame[3] - 2.4,
                                fill=False, ec="#222222", lw=0.5))
    elif sheet["title_block"] or d["param_table"]:
        fax = _blank(fig.add_axes([0, 0, 1, 1]))
        fax.set_xlim(0, W)
        fax.set_ylim(0, H)
        fax.patch.set_alpha(0)

    strip_h = max(30.0, H * 0.11) if (sheet["title_block"] or d["param_table"]) else 0.0
    content = (frame[0] + 3, frame[1] + strip_h + 4.0,
               frame[2] - 6, frame[3] - strip_h - 4.0 - 3)
    content_top = content[1] + content[3]

    view_specs = [S.resolve_view(v) for v in d["views"]]
    sec_kinds = list(d["sections"]["which"]) if d["sections"]["enabled"] else []
    has_views, has_secs = bool(view_specs), bool(sec_kinds)

    # ---- decide both scales, then take only the height each band needs ----
    view_scale = sec_scale = None
    view_panel_w = view_panel_h = 0.0
    sec_panel_w = sec_panel_h = 0.0

    if has_views:
        radius = _bounding_radius(geom)
        view_panel_w = (content[2] - PANEL_PAD * (len(view_specs) - 1)) / len(view_specs)
        allow_h = (content[3] * 0.58 if has_secs else content[3]) - CAPTION_H
        view_scale = nice_scale(min(view_panel_w, allow_h) * 0.94 / (2 * radius))
        view_panel_h = min(allow_h, 2 * radius * view_scale * 1.06)

    views_band = (view_panel_h + CAPTION_H) if has_views else 0.0

    if has_secs:
        sec_panel_w = (content[2] - PANEL_PAD * (len(sec_kinds) - 1)) / len(sec_kinds)
        allow_h = content[3] - views_band - (BAND_GAP if has_views else 0.0) - CAPTION_H
        need_w, need_h = _section_needs(sec_kinds, params)
        if d["sections"]["common_scale"]:
            sec_scale = nice_scale(min(sec_panel_w / need_w, allow_h / need_h))
            # Fill the band rather than shrink-wrapping the subject: the scale
            # is fixed by the series, so a tight box would only mean a small
            # airfoil floating above empty sheet.  The cap stops a very small
            # section from being framed by a vast field of grid.
            sec_panel_h = min(allow_h, need_h * sec_scale * 1.7)
        else:
            # Each section fills its own box; the panel is simply the space.
            sec_panel_h = allow_h

    # Centre the bands vertically in whatever is left.  Packing hard against
    # the top leaves a short sheet -- two views and two sections on A4 -- with
    # a third of its height blank below, which reads as a layout failure rather
    # than as a deliberately sparse drawing.
    used_h = views_band
    if has_secs:
        used_h += (BAND_GAP if has_views else 0.0) + sec_panel_h + CAPTION_H
    band_top = content_top - max(0.0, content[3] - used_h) / 2.0

    # ---- 3D views --------------------------------------------------------
    meta = {"views": [], "sections": sec_kinds}
    if has_views:
        view_y = band_top - views_band
        px_h = int(max(360, view_panel_h * d["dpi"] / 25.4))
        px_w = int(max(360, view_panel_w * d["dpi"] / 25.4))
        half_world_h = (view_panel_h / view_scale) / 2.0
        style = dict(d["view_style"])

        for i, (name, az, el) in enumerate(view_specs):
            img = scene.render_view(
                geom, s, {"name": name, "az": az, "el": el},
                width=px_w, height=px_h, style=style,
                projection="orthographic", parallel_scale=half_world_h,
                # A drawing sits on paper, not on a studio backdrop: force the
                # view's background off whatever the render preset says.
                background={"mode": "transparent"}, transparent=True,
            )
            x = content[0] + i * (view_panel_w + PANEL_PAD)
            ax = _blank(_axes(fig, (x, view_y, view_panel_w, view_panel_h), (W, H)))
            ax.imshow(img)
            ax.patch.set_alpha(0)
            if d["view_style"].get("labels", True):
                ax.set_title("%s  (az %g°, el %g°)" % (name.upper(), az, el),
                             fontsize=7.2, pad=3, color="#222222")
            meta["views"].append({"name": name, "az": az, "el": el,
                                  "scale": scale_text(view_scale)})

    # ---- blade sections (directly beneath the views) ---------------------
    if has_secs:
        sec_y = band_top - views_band - (BAND_GAP if has_views else 0.0) \
                - sec_panel_h - CAPTION_H
        aspect = sec_panel_w / sec_panel_h
        if d["sections"]["common_scale"]:
            half_spans = {k: (sec_panel_h / sec_scale) / 2.0 for k in sec_kinds}
        else:
            half_spans = {}
            for k in sec_kinds:
                w, h = SEC.section_span(k, params)
                half_spans[k] = max(w * SEC_PAD_W / max(aspect, 1e-6),
                                    h * SEC_PAD_H) * 0.5

        for i, kind in enumerate(sec_kinds):
            x = content[0] + i * (sec_panel_w + PANEL_PAD)
            ax = _axes(fig, (x, sec_y, sec_panel_w, sec_panel_h), (W, H))
            note = None
            if not d["sections"]["common_scale"]:
                note = scale_text(sec_panel_h / (2 * half_spans[kind]))
            SEC.draw_section(ax, kind, params, d["sections"]["annotations"],
                             half_span=half_spans[kind], aspect=aspect,
                             grid=d["sections"].get("grid", True),
                             scale_note=note)

    if fax is not None and (sheet["title_block"] or d["param_table"]):
        _draw_strip(fax, frame, strip_h, s, geom, title=title,
                    view_scale=view_scale, sec_scale=sec_scale, warnings=warnings)

    written = {}
    for fmt, path in (out_paths or {}).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(path), format=fmt, dpi=int(d["dpi"]), facecolor="white")
        written[fmt] = str(path)
    plt.close(fig)

    meta.update({
        "sheet": "%s %s" % (sheet["size"], sheet["orientation"]),
        "sheet_mm": [W, H],
        "view_scale": scale_text(view_scale) if view_scale else None,
        "section_scale": scale_text(sec_scale) if sec_scale else None,
        "files": written,
    })
    return meta


def _draw_strip(fax, frame, strip_h, s, geom, *, title, view_scale, sec_scale,
                warnings):
    """Title block on the right of the bottom strip, notes/params on the left."""
    d = s["drawing"]
    params = geom.params
    x0, y0 = frame[0] + 1.2, frame[1] + 1.2
    right = frame[0] + frame[2] - 1.2
    top = y0 + strip_h

    tb_w = min(150.0, frame[2] * 0.46)
    tb_x = right - tb_w

    if d["sheet"]["title_block"]:
        fax.add_patch(Rectangle((tb_x, y0), tb_w, strip_h, fill=False,
                                ec="#222222", lw=0.9))
        rows = [
            ("TITLE", title or d.get("title") or "Propeller assembly"),
            ("GEOMETRY", "RhinoCompute + Grasshopper" if geom.backend == "rhino"
                         else "FEG (web/feg, headless Node)"),
            ("BLADES / RADIUS", "%g blades   R %g mm   ring t %g mm" % (
                params["bladeCount"], params["impellerRadius"],
                params["impellerThickness"])),
            ("SCALE", "   ".join(filter(None, [
                ("views " + scale_text(view_scale)) if view_scale else None,
                ("sections " + scale_text(sec_scale)) if sec_scale else None,
            ])) or "not to scale"),
            ("UNITS / PROJECTION", "mm   orthographic (views arranged left to right)"),
            ("DRAWN / DATE", "%s   %s" % (d.get("drawn_by") or "-",
                                          _dt.date.today().isoformat())),
        ]
        rh = strip_h / len(rows)
        for i, (k, v) in enumerate(rows):
            ry = top - (i + 1) * rh
            if i:
                fax.plot([tb_x, right], [ry + rh, ry + rh], color="#999999", lw=0.4)
            fax.text(tb_x + 2.0, ry + rh * 0.5, k, fontsize=4.8, va="center",
                     color="#666666")
            fax.text(tb_x + tb_w * 0.34, ry + rh * 0.5, v, fontsize=5.8,
                     va="center", color="#111111")

    lx = x0 + 2.0
    lw = tb_x - lx - 4.0
    if d.get("param_table"):
        groups = {}
        for spec in P.PARAM_SPECS:
            groups.setdefault(spec.group, []).append(spec)
        col_w = lw / max(1, len(groups))
        for ci, (gname, specs) in enumerate(groups.items()):
            cx = lx + ci * col_w
            fax.text(cx, top - 2.0, gname.upper(), fontsize=4.8, va="top",
                     color="#666666")
            for ri, spec in enumerate(specs):
                v = params.get(spec.name)
                fax.text(cx, top - 5.6 - ri * 3.1,
                         "%-17s %-6s %s" % (spec.name,
                                            ("%g" % v) if v is not None else "-",
                                            spec.unit),
                         fontsize=4.6, va="top", color="#222222",
                         family="monospace")

    notes = list(warnings or ())
    if d.get("notes"):
        notes.insert(0, d["notes"])
    if notes and not d.get("param_table"):
        fax.text(lx, top - 3.0, "NOTES", fontsize=4.8, va="top", color="#666666")
        fax.text(lx, top - 6.5, "\n".join("- " + n for n in notes[:6]),
                 fontsize=5.0, va="top", color="#8a3a00")
