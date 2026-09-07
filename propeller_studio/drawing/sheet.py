"""The technical drawing sheet.

Composes one ISO sheet: frame, title block, the 3D views with their outline
overlaid, and the dimensioned blade sections beside them -- all in a single
image, as asked.  Every element is switchable from the settings tree.

Two layouts:

``stacked``          views in a band across the top, sections in a band below.
``sections_right``   views fill the left of the sheet, sections run down a
                     column on the right (``sections_left`` mirrors it).

Both bands are drawn TO A STATED SCALE chosen from the standard series, and the
scale is printed in the title block.  Auto-framing each panel to fill its box
would look tidier and be a lie: a drawing that names a scale has to be at it.

Panels are arranged by :func:`_grid`, which picks the rows x columns that make
the panels largest rather than assuming a single row -- in the column layout the
views get a narrower, taller region, where two rows of two beats one row of
four by a wide margin.
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

# Ceiling on the height the views band may take in the stacked layout.  In fill
# mode the views really do claim their whole allowance, so this is the knob that
# decides how the sheet is split between big pictures and legible dimensions.
VIEWS_HEIGHT_SHARE = 0.52

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
    """A scale as a printable ratio, 3 significant figures.

    Fill mode produces ratios like 1 : 1.18 that are not on the preferred
    series; they are still true, and stating the real number beats stating a
    tidy one the drawing is not actually at.
    """
    if s >= 1:
        return "%.3g : 1" % s
    return "1 : %.3g" % (1.0 / s)


def pick_scale(fit, mode):
    """Turn an available fit into the scale to draw at."""
    return nice_scale(fit) if mode == "standard" else fit


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


def _grid(n, rect_w, rect_h, *, caption_h=CAPTION_H, pad=PANEL_PAD, force_cols=None):
    """Rows x columns that make each panel as large as possible.

    Returns ``(rows, cols, panel_w, panel_h)``.  ``force_cols`` pins the column
    count (the section column is one-wide by definition).
    """
    best = None
    options = [force_cols] if force_cols else range(1, n + 1)
    for cols in options:
        rows = -(-n // cols)
        pw = (rect_w - pad * (cols - 1)) / cols
        ph = (rect_h - (caption_h + pad) * rows + pad) / rows
        if pw <= 1 or ph <= 1:
            continue
        score = min(pw, ph)
        if best is None or score > best[0]:
            best = (score, rows, cols, pw, ph)
    if best is None:                       # degenerate sheet; fail visibly, not silently
        return 1, max(1, n), max(1.0, rect_w / max(1, n)), max(1.0, rect_h - caption_h)
    return best[1], best[2], best[3], best[4]


def _cells(rect, rows, cols, panel_w, panel_h, *, caption_h=CAPTION_H,
           pad=PANEL_PAD, count=None):
    """Yield the (x, y, w, h) of each panel, centred inside *rect*."""
    rx, ry, rw, rh = rect
    n = count if count is not None else rows * cols
    cell_h = panel_h + caption_h
    block_h = rows * cell_h + (rows - 1) * pad
    block_w = cols * panel_w + (cols - 1) * pad
    top = ry + rh - max(0.0, rh - block_h) / 2.0
    for i in range(n):
        r, c = divmod(i, cols)
        # Centre each row on its OWN contents: three views in a 2x2 grid leave
        # the last one hanging against the left margin otherwise.
        in_row = min(cols, n - r * cols)
        row_w = in_row * panel_w + (in_row - 1) * pad
        left = rx + max(0.0, rw - row_w) / 2.0
        yield (left + c * (panel_w + pad),
               top - (r + 1) * cell_h - r * pad,
               panel_w, panel_h)


def render_sheet(geom, s, *, out_paths, title=None, warnings=(), inspect=None):
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

    view_specs = [S.resolve_view(v) for v in d["views"]]
    sec_kinds = list(d["sections"]["which"]) if d["sections"]["enabled"] else []
    has_views, has_secs = bool(view_specs), bool(sec_kinds)

    layout = d.get("layout", "stacked")
    scale_mode = d.get("scale_mode", "fill")
    requested_sec_scale = S.parse_scale(d["sections"].get("scale"))
    fs = float(d.get("font_scale", 1.0))
    column = layout in ("sections_right", "sections_left") and has_views and has_secs

    # ---- carve the content area into a views region and a sections region -
    if column:
        frac = min(0.7, max(0.15, float(d.get("sections_column_fraction", 0.38))))
        col_w = content[2] * frac
        rest_w = content[2] - col_w - BAND_GAP
        if layout == "sections_right":
            views_rect = (content[0], content[1], rest_w, content[3])
            secs_rect = (content[0] + rest_w + BAND_GAP, content[1], col_w, content[3])
        else:
            secs_rect = (content[0], content[1], col_w, content[3])
            views_rect = (content[0] + col_w + BAND_GAP, content[1], rest_w, content[3])
        sec_force_cols = 1
    else:
        views_rect = secs_rect = None
        sec_force_cols = len(sec_kinds) or 1

    meta = {"views": [], "sections": sec_kinds}
    section_axes = []
    view_scale = sec_scale = None

    # ---- views ------------------------------------------------------------
    v_rows = v_cols = 0
    v_pw = v_ph = 0.0
    if has_views:
        radius = _bounding_radius(geom)
        region = views_rect or (content[0], content[1], content[2],
                                content[3] * (VIEWS_HEIGHT_SHARE if has_secs else 1.0))
        v_rows, v_cols, v_pw, v_ph = _grid(len(view_specs), region[2], region[3])
        headroom = 0.94 if scale_mode == "standard" else 0.98
        view_scale = pick_scale(min(v_pw, v_ph) * headroom / (2 * radius), scale_mode)
        v_ph = min(v_ph, 2 * radius * view_scale * 1.06)

    views_band = (v_rows * (v_ph + CAPTION_H) + (v_rows - 1) * PANEL_PAD) if has_views else 0.0

    # ---- sections ---------------------------------------------------------
    s_rows = s_cols = 0
    s_pw = s_ph = 0.0
    if has_secs:
        if column:
            region = secs_rect
        else:
            avail_h = content[3] - views_band - (BAND_GAP if has_views else 0.0)
            region = (content[0], content[1], content[2], avail_h)
        s_rows, s_cols, s_pw, s_ph = _grid(len(sec_kinds), region[2], region[3],
                                           force_cols=sec_force_cols)
        need_w, need_h = _section_needs(sec_kinds, params)
        # An explicit scale implies a common one: a chosen ratio that differed
        # per panel would not be a scale at all.
        if requested_sec_scale:
            sec_scale = requested_sec_scale
            s_ph = min(s_ph, need_h * sec_scale * 1.7)
        elif d["sections"]["common_scale"]:
            sec_scale = pick_scale(min(s_pw / need_w, s_ph / need_h), scale_mode)
            # Fill the region rather than shrink-wrapping the subject: the scale
            # is fixed by the series, so a tight box would only mean a small
            # airfoil floating above empty sheet.  The cap stops a very small
            # section being framed by a vast field of grid.
            s_ph = min(s_ph, need_h * sec_scale * 1.7)
        secs_band = s_rows * (s_ph + CAPTION_H) + (s_rows - 1) * PANEL_PAD

        if requested_sec_scale:
            # Report a chosen scale the sheet cannot hold, naming the largest
            # that would fit.  Honour it anyway: quietly reducing a scale the
            # reader asked for is how a drawing comes to state one number and
            # be at another.
            raw_w = raw_h = 0.0
            for k in sec_kinds:
                w, h = SEC.section_span(k, params)
                raw_w, raw_h = max(raw_w, w), max(raw_h, h)
            if raw_w * sec_scale > s_pw or raw_h * sec_scale > s_ph:
                largest = min(s_pw / max(raw_w, 1e-9), s_ph / max(raw_h, 1e-9))
                warnings = list(warnings) + [
                    "Sections drawn at the requested %s, which overflows the "
                    "%.0f x %.0f mm panel; %s is the largest that fits."
                    % (scale_text(sec_scale), s_pw, s_ph, scale_text(largest))
                ]

    # In the stacked layout both bands share one column of space, so centre the
    # pair vertically; in the column layout each region centres within itself.
    if not column:
        used = views_band + (secs_band + BAND_GAP if has_secs and has_views else
                             (secs_band if has_secs else 0.0))
        slack = max(0.0, content[3] - used) / 2.0
        top = content[1] + content[3] - slack
        views_rect = (content[0], top - views_band, content[2], views_band)
        secs_rect = (content[0], top - views_band - (BAND_GAP if has_views else 0.0)
                     - secs_band, content[2], secs_band)

    if has_views:
        px_h = int(max(360, v_ph * d["dpi"] / 25.4))
        px_w = int(max(360, v_pw * d["dpi"] / 25.4))
        half_world_h = (v_ph / view_scale) / 2.0
        style = dict(d["view_style"])
        cells = list(_cells(views_rect, v_rows, v_cols, v_pw, v_ph,
                            count=len(view_specs)))
        for (name, az, el), cell in zip(view_specs, cells):
            img = scene.render_view(
                geom, s, {"name": name, "az": az, "el": el},
                width=px_w, height=px_h, style=style,
                projection="orthographic", parallel_scale=half_world_h,
                # A drawing sits on paper, not on a studio backdrop: force the
                # view's background off whatever the render preset says.
                background={"mode": "transparent"}, transparent=True,
            )
            ax = _blank(_axes(fig, cell, (W, H)))
            ax.imshow(img)
            ax.patch.set_alpha(0)
            if d["view_style"].get("labels", True):
                ax.set_title("%s  (az %g°, el %g°)" % (name.upper(), az, el),
                             fontsize=7.6 * fs, pad=3, color="#222222")
            meta["views"].append({"name": name, "az": az, "el": el,
                                  "scale": scale_text(view_scale)})

    if has_secs:
        aspect = s_pw / s_ph
        if requested_sec_scale or d["sections"]["common_scale"]:
            half_spans = {k: (s_ph / sec_scale) / 2.0 for k in sec_kinds}
        else:
            half_spans = {}
            for k in sec_kinds:
                w, h = SEC.section_span(k, params)
                half_spans[k] = max(w * SEC_PAD_W / max(aspect, 1e-6),
                                    h * SEC_PAD_H) * 0.5
        cells = list(_cells(secs_rect, s_rows, s_cols, s_pw, s_ph,
                            count=len(sec_kinds)))
        for kind, cell in zip(sec_kinds, cells):
            ax = _axes(fig, cell, (W, H))
            note = None
            if requested_sec_scale:
                note = scale_text(sec_scale)
            elif not d["sections"]["common_scale"]:
                note = scale_text(s_ph / (2 * half_spans[kind]))
            SEC.draw_section(ax, kind, params, d["sections"]["annotations"],
                             half_span=half_spans[kind], aspect=aspect,
                             grid=d["sections"].get("grid", True),
                             scale_note=note, font_scale=fs)
            section_axes.append(ax)

    if fax is not None and (sheet["title_block"] or d["param_table"]):
        _draw_strip(fax, frame, strip_h, s, geom, title=title,
                    view_scale=view_scale, sec_scale=sec_scale,
                    warnings=warnings, font_scale=fs)

    # Hook for the label-overlap check: it needs the live figure (extents only
    # exist against a renderer), and re-deriving the layout in the test would
    # test the copy rather than the sheet.
    if inspect is not None:
        inspect(fig, section_axes)

    written = {}
    for fmt, path in (out_paths or {}).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(path), format=fmt, dpi=int(d["dpi"]), facecolor="white")
        written[fmt] = str(path)
    plt.close(fig)

    meta.update({
        "layout": layout,
        "scale_mode": scale_mode,
        "sheet": "%s %s" % (sheet["size"], sheet["orientation"]),
        "sheet_mm": [W, H],
        "view_scale": scale_text(view_scale) if view_scale else None,
        "section_scale": scale_text(sec_scale) if sec_scale else None,
        "section_scale_requested": bool(requested_sec_scale),
        "warnings": list(warnings),
        "files": written,
    })
    return meta


def _draw_strip(fax, frame, strip_h, s, geom, *, title, view_scale, sec_scale,
                warnings, font_scale=1.0):
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
            ("UNITS / PROJECTION", "mm   orthographic"),
            ("DRAWN / DATE", "%s   %s" % (d.get("drawn_by") or "-",
                                          _dt.date.today().isoformat())),
        ]
        rh = strip_h / len(rows)
        for i, (k, v) in enumerate(rows):
            ry = top - (i + 1) * rh
            if i:
                fax.plot([tb_x, right], [ry + rh, ry + rh], color="#999999", lw=0.4)
            fax.text(tb_x + 2.0, ry + rh * 0.5, k, fontsize=5.4 * font_scale,
                     va="center", color="#666666")
            fax.text(tb_x + tb_w * 0.34, ry + rh * 0.5, v,
                     fontsize=6.6 * font_scale, va="center", color="#111111")

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
