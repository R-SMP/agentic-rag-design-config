"""The dimensioned blade-section drawings.

One axes per section, drawn in millimetres in the section's own placed frame --
the same (Y, Z) frame the 3D geometry uses -- so the shape on the sheet is the
true projection of the shape in the render, at the section's real angle of
attack.

Every annotation is individually switchable; :func:`draw_section` reads the
``drawing.sections.annotations`` block straight from the settings tree.
"""

from __future__ import annotations

import numpy as np

from propeller_studio.drawing import dimensions as D
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
    """Half-extent (mm) large enough to frame EVERY selected section.

    Used when ``common_scale`` is on: all panels then share one mm-per-point
    scale, so an inner chord of 10 mm looks half a middle chord of 20 mm --
    which is the whole point of drawing them on one sheet.
    """
    worst = 0.0
    for k in kinds:
        w, h = section_span(k, params)
        worst = max(worst, w, h)
    return max(worst * 0.5 * pad, 1.0)


def draw_section(ax, kind, params, annotations, *, half_span=None, aspect=1.0,
                 grid=True, title=True, scale_note=None):
    """Draw one dimensioned section into *ax*.  Returns its metrics dict."""
    m = airfoil.section_metrics(kind, params)
    color = SECTION_COLORS[kind]
    pts = m["outline_xy"]
    centroid = pts.mean(axis=0)

    if half_span is None:
        w, h = section_span(kind, params)
        half_span = max(w, h) * 0.5 * 1.35

    # The window is the PANEL's shape, not a square: an airfoil is wide and
    # flat, so a square window spends most of its area on empty grid and
    # shrinks the subject.  mm-per-point is identical either way, so the stated
    # common scale is unaffected.
    ax.set_aspect("equal", adjustable="box")
    half_w = half_span * float(aspect)
    half_h = half_span
    xlim = (centroid[0] - half_w, centroid[0] + half_w)
    ylim = (centroid[1] - half_h, centroid[1] + half_h)

    if grid:
        D.mm_grid(ax, xlim, ylim, step=1.0, major_every=5)

    ax.fill(pts[:, 0], pts[:, 1], color=color, alpha=0.10, zorder=2)
    closed = np.vstack([pts, pts[:1]])
    ax.plot(closed[:, 0], closed[:, 1], color=color, lw=D.OBJ_LW, zorder=4,
            solid_joinstyle="round")

    le = np.asarray(m["le_xy"])
    te = np.asarray(m["te_xy"])
    chord_len = m["chord_mm"]

    if annotations.get("chord_line", True):
        ax.plot([le[0], te[0]], [le[1], te[1]], color=CHORD_COLOR, lw=0.7,
                zorder=5)
    if annotations.get("camber_line", True) and m["has_camber"]:
        cl = m["camber_line_xy"]
        ax.plot(cl[:, 0], cl[:, 1], color=CAMBER_COLOR, lw=0.9,
                ls=(0, (5, 2.5)), zorder=5)

    unit = half_span  # every offset below is a fraction of the panel half-size
    win_w = xlim[1] - xlim[0]
    win_h = ylim[1] - ylim[0]

    if annotations.get("chord"):
        # Offset scaled to the SECTION, capped by the panel: a fixed fraction of
        # the window pushes a wide section's chord label past the frame edge.
        chord_off = min(unit * 0.30, chord_len * 0.30, win_h * 0.20)
        D.linear_dim(ax, te, le, offset=chord_off, side=-1.0,
                     label="CHORD %.2f mm" % chord_len)

    if annotations.get("angle"):
        datum = te + np.array([chord_len * 0.75, 0.0])
        D.angular_dim(ax, te, datum, le, radius=chord_len * 0.42,
                      label="%.1f°" % m["angle_deg"],
                      datum_len=chord_len * 0.62)

    # Thickness and camber are dimensioned ACROSS a section only a millimetre
    # or two deep, so their values go on leaders rather than on the dimension
    # line.  Rotated text sitting in that gap collides with the outline, the
    # camber line and the angle arc -- three labels fighting over the same
    # 2 mm, which is how a drawing becomes unreadable at print size.
    if annotations.get("thickness"):
        up = np.asarray(m["thickness_upper_xy"])
        lo_pt = np.asarray(m["thickness_lower_xy"])
        D.linear_dim(ax, lo_pt, up, offset=0.0, show_text=False)
        # Anchored to the panel, not to the feature: a chord-relative offset
        # scales with the section and walks a long label straight off the
        # sheet on the wide middle section.
        D.leader(ax, (up + lo_pt) / 2.0,
                 "t max %.2f mm  (%.1f%% c @ %.0f%% c)" % (
                     m["max_thickness_mm"], m["thickness_pct"],
                     100 * m["thickness_station_frac"]),
                 landing=(xlim[0] + win_w * 0.05, ylim[1] - win_h * 0.11),
                 landing_len=win_w * 0.02, text_dir=1.0)

    if annotations.get("camber"):
        if m["has_camber"]:
            crest = np.asarray(m["camber_crest_xy"])
            D.linear_dim(ax, m["camber_chord_xy"], crest, offset=0.0,
                         color=CAMBER_COLOR, show_text=False)
            D.leader(ax, crest,
                     "camber %.2f mm  (%.1f%% c)  crest %.0f/10 c" % (
                         m["max_camber_mm"], m["camber_pct"], m["crest_tenths"]),
                     landing=(xlim[1] - win_w * 0.05, ylim[1] - win_h * 0.21),
                     landing_len=win_w * 0.02, text_dir=-1.0,
                     color=CAMBER_COLOR)
        else:
            ax.text(xlim[1] - win_w * 0.05, ylim[1] - win_h * 0.21,
                    "no camber (symmetric)", ha="right", va="center",
                    fontsize=D.FONT_DIM, color=CAMBER_COLOR, zorder=7)

    if annotations.get("le_te"):
        ax.annotate("LE", xy=tuple(le), xytext=(le[0] + unit * 0.16, le[1] + unit * 0.16),
                    fontsize=D.FONT_DIM, color=CHORD_COLOR,
                    arrowprops=dict(arrowstyle="-", color=CHORD_COLOR, lw=0.5), zorder=7)
        ax.annotate("TE", xy=tuple(te), xytext=(te[0] - unit * 0.22, te[1] - unit * 0.18),
                    fontsize=D.FONT_DIM, color=CHORD_COLOR,
                    arrowprops=dict(arrowstyle="-", color=CHORD_COLOR, lw=0.5), zorder=7)

    if annotations.get("le_radius"):
        # NACA 4-digit leading-edge radius: r = 1.1019 * t^2 * c.
        r_le = 1.1019 * (m["thickness_pct"] / 100.0) ** 2 * chord_len
        ax.add_patch(__import__("matplotlib.patches", fromlist=["Circle"]).Circle(
            tuple(le + (te - le) / max(chord_len, 1e-9) * r_le), r_le,
            fill=False, ec=D.DIM_COLOR, lw=D.EXT_LW, zorder=6))
        D.leader(ax, le, "R %.3f mm" % r_le,
                 landing=(xlim[1] - win_w * 0.05, ylim[0] + win_h * 0.30),
                 landing_len=win_w * 0.02, text_dir=-1.0)

    if annotations.get("bbox"):
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        ax.add_patch(__import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle(
            (lo[0], lo[1]), hi[0] - lo[0], hi[1] - lo[1], fill=False,
            ec=D.CENTER_COLOR, lw=D.EXT_LW, ls=(0, (4, 3)), zorder=3))
        D.linear_dim(ax, (lo[0], lo[1]), (hi[0], lo[1]), offset=-unit * 0.16,
                     label="%.2f" % (hi[0] - lo[0]), color=D.CENTER_COLOR)
        D.linear_dim(ax, (hi[0], lo[1]), (hi[0], hi[1]), offset=unit * 0.16,
                     label="%.2f" % (hi[1] - lo[1]), color=D.CENTER_COLOR)

    station_bits = []
    if annotations.get("radial_station"):
        station_bits.append("r = %.2f mm" % m["radius_mm"])
    if annotations.get("span_position"):
        station_bits.append("span %.2f (from 4 mm root)" % m["span_fraction"])
    if station_bits:
        ax.text(xlim[0] + unit * 0.05, ylim[1] - unit * 0.07, "   ".join(station_bits),
                ha="left", va="top", fontsize=D.FONT_DIM, color="#444444", zorder=7)

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
        ax.text(xlim[0] + unit * 0.05, ylim[0] + unit * 0.05, "\n".join(rows),
                ha="left", va="bottom", fontsize=D.FONT_DIM - 0.4, color="#333333",
                family="monospace", zorder=7,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#dddddd", lw=0.4))

    if title:
        label = SECTION_LABELS[kind] + " SECTION"
        if scale_note:
            label += "    " + scale_note
        ax.set_title(label, fontsize=7.6, color=color, pad=4, fontweight="bold")

    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    for spine in ax.spines.values():
        spine.set_edgecolor("#bbbbbb")
        spine.set_linewidth(0.6)
    ax.set_xticks([])
    ax.set_yticks([])
    return m
