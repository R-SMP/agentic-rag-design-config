"""Engineering-drawing dimension primitives, drawn in matplotlib data space.

Everything here works in millimetres in the axes' own data coordinates, so a
dimension lands on the geometry it describes without a second transform to
drift out of step.

The primitives are the ordinary ones: a linear dimension (extension lines,
arrowheads, a value that reads along the line), an angular dimension (arc plus
value), a leader with a landing, and a centre mark.
"""

from __future__ import annotations

import math

import numpy as np

# House style.  Line weights are in points; a technical drawing wants dimension
# lines clearly LIGHTER than the object outline they describe.
DIM_COLOR = "#1b3a6b"
DIM_LW = 0.7
EXT_LW = 0.5
OBJ_LW = 1.5
CENTER_COLOR = "#7a7a7a"
FONT_DIM = 6.2
ARROW = "-|>"


def _unit(v):
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else np.array([1.0, 0.0])


def _perp(v):
    return np.array([-v[1], v[0]])


def _fmt(value, decimals=2, unit=""):
    return ("%.*f" % (decimals, value)).rstrip("0").rstrip(".") + unit


def linear_dim(ax, p1, p2, *, offset=0.0, label=None, decimals=2, unit=" mm",
               color=DIM_COLOR, fontsize=FONT_DIM, ext_overshoot=None,
               flip_text=False, side=1.0, show_text=True):
    """Dimension the distance between *p1* and *p2*.

    ``offset`` moves the dimension line perpendicular to p1->p2 (``side``
    picks which way).  The text sits on the line and reads along it, flipped
    upright so it is never upside-down -- a dimension you have to rotate the
    page to read is a dimension that gets misread.
    """
    p1 = np.asarray(p1, dtype=float)
    p2 = np.asarray(p2, dtype=float)
    d = p2 - p1
    length = float(np.linalg.norm(d))
    if length < 1e-9:
        return
    u = _unit(d)
    n = _perp(u) * float(side)
    off = n * float(offset)

    a, b = p1 + off, p2 + off
    if ext_overshoot is None:
        ext_overshoot = abs(offset) * 0.12 + length * 0.02
    for base, tip in ((p1, a), (p2, b)):
        ext = tip + _unit(tip - base) * ext_overshoot if offset else tip
        ax.plot([base[0], ext[0]], [base[1], ext[1]],
                color=color, lw=EXT_LW, solid_capstyle="butt", zorder=6)

    ax.annotate("", xy=tuple(b), xytext=tuple(a), zorder=6,
                arrowprops=dict(arrowstyle=ARROW + "," + "head_length=0.5,head_width=0.18",
                                color=color, lw=DIM_LW, shrinkA=0, shrinkB=0))
    ax.annotate("", xy=tuple(a), xytext=tuple(b), zorder=6,
                arrowprops=dict(arrowstyle=ARROW + "," + "head_length=0.5,head_width=0.18",
                                color=color, lw=DIM_LW, shrinkA=0, shrinkB=0))

    if not show_text:
        return
    text = label if label is not None else _fmt(length, decimals, unit)
    ang = math.degrees(math.atan2(u[1], u[0]))
    if ang > 90 or ang <= -90:
        ang += 180
    mid = (a + b) / 2.0
    pad = _perp(u) * (length * 0.035 + 0.12) * (-1.0 if flip_text else 1.0) * float(side)
    ax.text(mid[0] + pad[0], mid[1] + pad[1], text, rotation=ang,
            rotation_mode="anchor", ha="center", va="bottom",
            fontsize=fontsize, color=color, zorder=7)


def angular_dim(ax, vertex, p_from, p_to, *, radius, label=None, decimals=1,
                color=DIM_COLOR, fontsize=FONT_DIM, datum_len=None):
    """Dimension the angle at *vertex* between the rays to *p_from*/*p_to*.

    Draws the datum ray, the arc, arrowheads tangent to the arc, and the value
    outside the arc.
    """
    vertex = np.asarray(vertex, dtype=float)
    a0 = math.atan2(*(np.asarray(p_from, float) - vertex)[::-1])
    a1 = math.atan2(*(np.asarray(p_to, float) - vertex)[::-1])
    sweep = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi

    if datum_len:
        d = vertex + np.array([math.cos(a0), math.sin(a0)]) * datum_len
        ax.plot([vertex[0], d[0]], [vertex[1], d[1]], color=color, lw=EXT_LW,
                ls=(0, (6, 3)), zorder=6)

    ts = np.linspace(a0, a0 + sweep, 64)
    arc = np.column_stack([vertex[0] + radius * np.cos(ts),
                           vertex[1] + radius * np.sin(ts)])
    ax.plot(arc[:, 0], arc[:, 1], color=color, lw=DIM_LW, zorder=6)
    for tip, prev in ((arc[-1], arc[-4]), (arc[0], arc[3])):
        ax.annotate("", xy=tuple(tip), xytext=tuple(prev), zorder=6,
                    arrowprops=dict(arrowstyle=ARROW + ",head_length=0.5,head_width=0.18",
                                    color=color, lw=DIM_LW, shrinkA=0, shrinkB=0))

    mid_a = a0 + sweep / 2.0
    tp = vertex + np.array([math.cos(mid_a), math.sin(mid_a)]) * (radius * 1.08 + 0.25)
    text = label if label is not None else (
        _fmt(abs(math.degrees(sweep)), decimals, "") + "°")
    ax.text(tp[0], tp[1], text, ha="left" if math.cos(mid_a) >= 0 else "right",
            va="center", fontsize=fontsize, color=color, zorder=7)


def leader(ax, target, text, *, landing, color=DIM_COLOR, fontsize=FONT_DIM,
           landing_len=None, ha=None, text_dir=None):
    """A leader from *target* to a landing point, with text on the landing.

    ``text_dir`` (+1 right, -1 left) sets which way the text grows, INDEPENDENT
    of which way the elbow points.  That separation matters: a label anchored to
    the left edge of a panel must still read rightwards, or it runs off the
    sheet -- which is precisely what happens when the text direction is inferred
    from the elbow.
    """
    target = np.asarray(target, dtype=float)
    landing = np.asarray(landing, dtype=float)
    elbow_sign = 1.0 if landing[0] >= target[0] else -1.0
    if landing_len is None:
        landing_len = abs(landing[0] - target[0]) * 0.18 + 0.4
    sign = float(text_dir) if text_dir else elbow_sign
    end = landing + np.array([landing_len * sign, 0.0])
    ax.plot([target[0], landing[0], end[0]], [target[1], landing[1], end[1]],
            color=color, lw=DIM_LW, zorder=6)
    ax.plot([target[0]], [target[1]], marker="o", ms=1.8, color=color, zorder=7)
    ax.text(end[0] + 0.15 * sign, end[1], text, va="center",
            ha=(ha or ("left" if sign > 0 else "right")),
            fontsize=fontsize, color=color, zorder=7)


def center_mark(ax, point, size, *, color=CENTER_COLOR, lw=0.5):
    x, y = float(point[0]), float(point[1])
    ax.plot([x - size, x + size], [y, y], color=color, lw=lw,
            ls=(0, (7, 2, 1, 2)), zorder=5)
    ax.plot([x, x], [y - size, y + size], color=color, lw=lw,
            ls=(0, (7, 2, 1, 2)), zorder=5)


def mm_grid(ax, xlim, ylim, *, step=1.0, major_every=5,
            minor="#e6e6e6", major="#cfcfcf", lw=0.4):
    """A 1 mm reference grid with a heavier line every *major_every* mm."""
    x0 = math.floor(xlim[0] / step) * step
    y0 = math.floor(ylim[0] / step) * step
    x = x0
    while x <= xlim[1]:
        is_major = abs(x / (step * major_every) - round(x / (step * major_every))) < 1e-9
        ax.plot([x, x], list(ylim), color=major if is_major else minor,
                lw=lw * (1.4 if is_major else 1.0), zorder=0)
        x += step
    y = y0
    while y <= ylim[1]:
        is_major = abs(y / (step * major_every) - round(y / (step * major_every))) < 1e-9
        ax.plot(list(xlim), [y, y], color=major if is_major else minor,
                lw=lw * (1.4 if is_major else 1.0), zorder=0)
        y += step
