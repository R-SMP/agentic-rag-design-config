"""The dimensioned blade-section drawings.

One axes per section, drawn in millimetres in the section's own placed frame --
the same (Y, Z) frame the 3D geometry uses -- so the shape on the sheet is the
true projection of the shape in the render, at the section's real angle of
attack.

Every annotation is individually switchable; :func:`draw_section` reads the
``drawing.sections.annotations`` block straight from the settings tree.

Labels are PLACED, not positioned: each is offered a ladder of candidate
anchors and takes the first that collides with nothing already drawn (see
``placement.Placer``).  Fixed offsets cannot work here -- the panel is a
different shape in the stacked and column layouts, and every extra toggle adds
another label competing for the same two millimetres around the airfoil.
"""

from __future__ import annotations

import math

import numpy as np
from matplotlib.patches import Circle, Rectangle

from propeller_studio.drawing import dimensions as D
from propeller_studio.drawing.placement import Placer
from propeller_studio.geometry import airfoil

SECTION_COLORS = {
    "inner": "#2563eb",
    "middle": "#16a34a",
    "outer": "#dc2626",
}
SECTION_LABELS = {"inner": "INNER", "middle": "MIDDLE", "outer": "OUTER"}

CAMBER_COLOR = "#c60c8c"
CHORD_COLOR = "#141414"


def section_span(kind, params):
    """Bounding-box size (width, height) in mm of a placed section."""
    pts = airfoil.build_section_2d(kind, params)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    return float(hi[0] - lo[0]), float(hi[1] - lo[1])


def common_half_span(kinds, params, pad=1.35):
    """Half-extent (mm) large enough to frame EVERY selected section."""
    worst = 0.0
    for k in kinds:
        w, h = section_span(k, params)
        worst = max(worst, w, h)
    return max(worst * 0.5 * pad, 1.0)


def draw_section(ax, kind, params, annotations, *, half_span=None, aspect=1.0,
                 grid=True, title=True, scale_note=None, font_scale=1.0):
    """Draw one dimensioned section into *ax*.  Returns its metrics dict."""
    m = airfoil.section_metrics(kind, params)
    color = SECTION_COLORS[kind]
    pts = m["outline_xy"]
    centroid = pts.mean(axis=0)

    if half_span is None:
        w, h = section_span(kind, params)
        half_span = max(w, h) * 0.5 * 1.35

    # The window is the PANEL's shape, not a square: an airfoil is wide and
    # flat, so a square window spends most of its area on empty grid.
    # mm-per-point is identical either way, so the stated scale is unaffected.
    ax.set_aspect("equal", adjustable="box")
    half_w = half_span * float(aspect)
    half_h = half_span
    xlim = (centroid[0] - half_w, centroid[0] + half_w)
    ylim = (centroid[1] - half_h, centroid[1] + half_h)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)

    if grid:
        D.mm_grid(ax, xlim, ylim, step=1.0, major_every=5)

    ax.fill(pts[:, 0], pts[:, 1], color=color, alpha=0.10, zorder=2)
    closed = np.vstack([pts, pts[:1]])
    ax.plot(closed[:, 0], closed[:, 1], color=color, lw=D.OBJ_LW, zorder=4,
            solid_joinstyle="round")

    le = np.asarray(m["le_xy"])
    te = np.asarray(m["te_xy"])
    chord_len = m["chord_mm"]
    # One knob for every annotation size, so "make the values readable" is a
    # single setting rather than a hunt through a dozen literals.
    fs = D.FONT_DIM * float(font_scale)

    if annotations.get("chord_line", True):
        ax.plot([le[0], te[0]], [le[1], te[1]], color=CHORD_COLOR, lw=0.7, zorder=5)
    if annotations.get("camber_line", True) and m["has_camber"]:
        cl = m["camber_line_xy"]
        ax.plot(cl[:, 0], cl[:, 1], color=CAMBER_COLOR, lw=0.9,
                ls=(0, (5, 2.5)), zorder=5)

    if title:
        label = SECTION_LABELS[kind] + " SECTION"
        if scale_note:
            label += "    " + scale_note
        ax.set_title(label, fontsize=8.4 * float(font_scale), color=color,
                     pad=4, fontweight="bold")
    for spine in ax.spines.values():
        spine.set_edgecolor("#bbbbbb")
        spine.set_linewidth(0.6)
    ax.set_xticks([])
    ax.set_yticks([])

    # ---- annotations, placed rather than positioned ----------------------
    placer = Placer(ax)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    # The airfoil itself is occupied: a label sitting on the shape it measures
    # is the one overlap no amount of leader routing can excuse.
    placer.reserve_data(lo[0], lo[1], hi[0], hi[1])

    unit = half_span
    win_w = xlim[1] - xlim[0]
    win_h = ylim[1] - ylim[0]

    # ---- phase 1: draw every dimension LINE, arc and patch ---------------
    # Lines are geometry and go where the geometry says.  Only their VALUES are
    # placed, in phase 2 -- so a line may cross another line (which a drawing
    # tolerates) while no value crosses a value or a box (which it does not).
    jobs = []          # (size_rank, callable) -- placed largest first

    if annotations.get("chord"):
        chord_off = min(unit * 0.30, chord_len * 0.30, win_h * 0.20)
        a, b, _ = D.linear_dim(ax, te, le, offset=chord_off, side=-1.0,
                               show_text=False)
        placer.reserve_line(a, b)
        jobs.append((2, lambda a=a, b=b: placer.place_on_line(
            "CHORD %.2f mm" % chord_len, a, b,
            color=D.DIM_COLOR, fontsize=fs)))

    if annotations.get("angle"):
        datum = te + np.array([chord_len * 0.75, 0.0])
        vertex, a0, sweep, arc_r, _ = D.angular_dim(
            ax, te, datum, le, radius=chord_len * 0.42,
            datum_len=chord_len * 0.62, show_text=False)
        cands = []
        for rm in (1.12, 1.45, 1.85, 2.3):
            for f in (0.5, 0.75, 0.25, 1.0):
                ang = a0 + sweep * f
                cands.append((vertex[0] + arc_r * rm * math.cos(ang),
                              vertex[1] + arc_r * rm * math.sin(ang),
                              "left" if math.cos(ang) >= 0 else "right",
                              "center", None))
        # Like every other value, the angle gets a leader fallback: penned in
        # beside a crowded arc it would otherwise shrink itself into
        # illegibility rather than move somewhere it can be read.
        arc_mid = (vertex[0] + arc_r * math.cos(a0 + sweep * 0.5),
                   vertex[1] + arc_r * math.sin(a0 + sweep * 0.5))
        on_arc = len(cands)
        cands = cands + placer.zone_candidates(
            ["MR", "TR", "BR", "ML", "TL", "BL"], arc_mid, (0.14, 0.24, 0.34))
        jobs.append((1, lambda c=cands, a=arc_mid, n=on_arc: placer.place(
            "%.1f°" % m["angle_deg"], c,
            color=D.DIM_COLOR, fontsize=fs,
            leader_from=a, leader_from_index=n)))

    if annotations.get("thickness"):
        up = np.asarray(m["thickness_upper_xy"])
        lo_pt = np.asarray(m["thickness_lower_xy"])
        D.linear_dim(ax, lo_pt, up, offset=0.0, show_text=False)
        placer.reserve_line(lo_pt, up)
        mid = tuple((up + lo_pt) / 2.0)
        jobs.append((3, lambda mid=mid: placer.place_text(
            "t max %.2f mm  (%.1f%% c @ %.0f%% c)" % (
                m["max_thickness_mm"], m["thickness_pct"],
                100 * m["thickness_station_frac"]),
            zones=["TL", "ML", "BL", "TR", "MR", "BR"],
            color=D.DIM_COLOR, fontsize=fs, leader_from=mid)))

    if annotations.get("camber"):
        if m["has_camber"]:
            crest = tuple(np.asarray(m["camber_crest_xy"]))
            D.linear_dim(ax, m["camber_chord_xy"], crest, offset=0.0,
                         color=CAMBER_COLOR, show_text=False)
            placer.reserve_line(m["camber_chord_xy"], crest)
            jobs.append((3, lambda crest=crest: placer.place_text(
                "camber %.2f mm  (%.1f%% c)  crest %.0f/10 c" % (
                    m["max_camber_mm"], m["camber_pct"], m["crest_tenths"]),
                zones=["TR", "MR", "BR", "TL", "ML", "BL"],
                color=CAMBER_COLOR, fontsize=fs, leader_from=crest)))
        else:
            jobs.append((2, lambda: placer.place_text(
                "no camber (symmetric)", zones=["TR", "MR", "BR", "TL"],
                color=CAMBER_COLOR, fontsize=fs)))

    if annotations.get("bbox"):
        ax.add_patch(Rectangle((lo[0], lo[1]), hi[0] - lo[0], hi[1] - lo[1],
                               fill=False, ec=D.CENTER_COLOR, lw=D.EXT_LW,
                               ls=(0, (4, 3)), zorder=3))
        a, b, _ = D.linear_dim(ax, (lo[0], lo[1]), (hi[0], lo[1]),
                               offset=-min(unit * 0.14, win_h * 0.10),
                               color=D.CENTER_COLOR, show_text=False)
        placer.reserve_line(a, b)
        jobs.append((1, lambda a=a, b=b: placer.place_on_line(
            "%.2f" % (hi[0] - lo[0]), a, b,
            color=D.CENTER_COLOR, fontsize=fs)))
        a2, b2, _ = D.linear_dim(ax, (hi[0], lo[1]), (hi[0], hi[1]),
                                 offset=min(unit * 0.14, win_w * 0.06),
                                 color=D.CENTER_COLOR, show_text=False)
        placer.reserve_line(a2, b2)
        jobs.append((1, lambda a=a2, b=b2: placer.place_on_line(
            "%.2f" % (hi[1] - lo[1]), a, b,
            color=D.CENTER_COLOR, fontsize=fs)))

    r_le = 1.1019 * (m["thickness_pct"] / 100.0) ** 2 * chord_len
    if annotations.get("le_radius"):
        # NACA 4-digit leading-edge radius: r = 1.1019 * t^2 * c.
        centre = le + (te - le) / max(chord_len, 1e-9) * r_le
        ax.add_patch(Circle(tuple(centre), r_le, fill=False, ec=D.DIM_COLOR,
                            lw=D.EXT_LW, zorder=6))
        jobs.append((2, lambda: placer.place_text(
            "LE radius %.3f mm" % r_le, zones=["BR", "MR", "BL", "TR"],
            color=D.DIM_COLOR, fontsize=fs, leader_from=tuple(le))))

    if annotations.get("le_te"):
        for pt, txt in ((le, "LE"), (te, "TE")):
            jobs.append((0, lambda pt=pt, txt=txt: placer.place_text(
                txt, zones=["TR", "TL", "BR", "BL"], color=CHORD_COLOR,
                fontsize=fs, leader_from=tuple(pt),
                radii=(0.055, 0.09, 0.14, 0.20))))

    station_bits = []
    if annotations.get("radial_station"):
        station_bits.append("r = %.2f mm" % m["radius_mm"])
    if annotations.get("span_position"):
        station_bits.append("span %.2f (from 4 mm root)" % m["span_fraction"])
    if station_bits:
        # Two fallbacks, in order of what they give up: the line break first,
        # then the parenthetical.  "(from 4 mm root)" is the last thing to go --
        # span is measured from the blade root at r = 4 mm, not from the centre,
        # and a reader who assumes otherwise misreads every middle section.
        jobs.append((4, lambda: placer.place_text(
            "   ".join(station_bits), zones=["TL", "TR", "BL", "BR"],
            color="#444444", fontsize=fs,
            alt_texts=("\n".join(station_bits),
                       "\n".join(station_bits).replace(" (from 4 mm root)", "")))))

    if annotations.get("value_table"):
        rows = [
            "chord   %6.2f mm" % chord_len,
            "angle   %6.1f°" % m["angle_deg"],
            "t max   %6.2f mm  (%.1f%% c @ %.0f%% c)" % (
                m["max_thickness_mm"], m["thickness_pct"],
                100 * m["thickness_station_frac"]),
            "camber  %6.2f mm  (%.1f%% c @ %.0f%% c)" % (
                m["max_camber_mm"], m["camber_pct"],
                100 * m["camber_station_frac"]),
        ]
        jobs.append((9, lambda: placer.place_text(
            "\n".join(rows), zones=["BL", "BR", "TL", "TR"],
            color="#333333", fontsize=fs - 0.5, family="monospace",
            bbox=dict(boxstyle="round,pad=0.25", fc="white",
                      ec="#dddddd", lw=0.4))))

    # ---- phase 2: place the values, LARGEST FIRST ------------------------
    # Whoever is placed first gets the space.  Placing the four-line value table
    # LAST meant that on a small panel it was the one item with nowhere left to
    # go, so it is now first: the small values have leaders and can travel
    # around it, while it cannot travel around them.
    for _, job in sorted(jobs, key=lambda item: -item[0]):
        job()

    return m
