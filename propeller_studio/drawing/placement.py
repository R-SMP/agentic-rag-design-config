"""Collision-aware label placement for the drawing panels.

A dimensioned airfoil carries six or more labels around a shape only a couple
of millimetres deep.  Placing them at fixed offsets works for one parameter set
and fails for the next: a wide chord, a fat section or an extra toggle turns
two labels into one unreadable overlap.

So labels are PLACED rather than positioned.  Each one is offered a ladder of
candidate anchors; the first that collides with nothing already on the panel
wins, and if none is clean the least-bad is used.  Leader lines are checked too
-- a leader that crosses the value table is as wrong as text on text.

Everything is measured with the real matplotlib renderer in display (pixel)
coordinates, so the test is against what will actually be drawn rather than an
estimate of it.
"""

from __future__ import annotations

import numpy as np
from matplotlib.transforms import Bbox

# Anchor zones as (x, y) fractions of the panel, with the alignment that grows
# the text INWARD from that corner.
ZONES = {
    "TL": (0.02, 0.97, "left", "top"),
    "TR": (0.98, 0.97, "right", "top"),
    "ML": (0.02, 0.60, "left", "center"),
    "MR": (0.98, 0.60, "right", "center"),
    "BL": (0.02, 0.03, "left", "bottom"),
    "BR": (0.98, 0.03, "right", "bottom"),
}

# Vertical nudges applied to each zone, in panel fractions, tried in order.
LADDER = (0.0, -0.09, -0.18, -0.27, 0.09, 0.18)


class Placer:
    """Tracks what is already occupied on one panel, in display coordinates."""

    def __init__(self, ax, pad_px=2.0):
        self.ax = ax
        self.fig = ax.get_figure()
        self.pad = float(pad_px)
        self.boxes = []
        self.lines = []          # drawn dimension lines, as display segments
        try:
            self.renderer = self.fig.canvas.get_renderer()
        except AttributeError:                       # non-Agg canvas
            self.fig.canvas.draw()
            self.renderer = self.fig.canvas.get_renderer()

    # -- coordinate helpers -------------------------------------------------

    def to_display(self, xy):
        return self.ax.transData.transform(np.asarray(xy, dtype=float))

    def data_rect(self, x0, y0, x1, y1):
        (dx0, dy0) = self.to_display((min(x0, x1), min(y0, y1)))
        (dx1, dy1) = self.to_display((max(x0, x1), max(y0, y1)))
        return Bbox([[dx0, dy0], [dx1, dy1]])

    # -- occupancy ----------------------------------------------------------

    def reserve(self, bbox):
        if bbox is not None:
            self.boxes.append(bbox.expanded(1.0, 1.0).padded(self.pad))

    def reserve_data(self, x0, y0, x1, y1):
        self.reserve(self.data_rect(x0, y0, x1, y1))

    def reserve_artist(self, artist):
        if artist is None:
            return
        try:
            self.reserve(artist.get_window_extent(renderer=self.renderer))
        except Exception:
            pass

    def reserve_line(self, p0, p1):
        """Record a drawn dimension line so no VALUE is placed across it.

        A number with a dimension line ruled through it is as unreadable as two
        numbers on top of each other, and it is the failure that survives a
        text-vs-text check.
        """
        self.lines.append((self.to_display(p0), self.to_display(p1)))

    def crossed_by_line(self, bbox):
        """Count of reserved dimension lines passing through *bbox*."""
        return sum(1 for a, b in self.lines if _seg_hits_box(a, b, bbox))

    def overlap(self, bbox):
        """Total overlapping area in px^2 against everything reserved."""
        total = 0.0
        for other in self.boxes:
            ix = min(bbox.x1, other.x1) - max(bbox.x0, other.x0)
            iy = min(bbox.y1, other.y1) - max(bbox.y0, other.y0)
            if ix > 0 and iy > 0:
                total += ix * iy
        return total

    def segment_blocked(self, p0, p1, ignore=()):
        """True if the data-space segment p0->p1 crosses anything reserved."""
        a = self.to_display(p0)
        b = self.to_display(p1)
        for other in self.boxes:
            if any(other is g for g in ignore):
                continue
            if _seg_hits_box(a, b, other):
                return True
        return False

    # -- placement ----------------------------------------------------------

    def _candidates(self, zones, leader_from, w, h, x0, y0, radii):
        """Candidate anchors, nearest-to-the-feature first.

        A label that can sit beside the thing it measures should: routing every
        callout to a panel corner is collision-free but produces leaders that
        cross the whole drawing.  Panel zones are the fallback, for when the
        neighbourhood of the feature is already full.
        """
        out = []
        if leader_from is not None:
            fx, fy = float(leader_from[0]), float(leader_from[1])
            step = min(w, h)
            for r in radii:
                for dx, dy in ((1, 0.55), (-1, 0.55), (1, -0.55), (-1, -0.55),
                               (1, 0), (-1, 0), (0.2, 1), (0.2, -1)):
                    out.append((fx + dx * step * r, fy + dy * step * r,
                                "left" if dx >= 0 else "right", "center", None))
        for zone in zones:
            zx, zy, ha, va = ZONES[zone]
            for dy in LADDER:
                out.append((x0 + zx * w, y0 + (zy + dy) * h, ha, va, None))
        return out

    def zone_candidates(self, zones, leader_from, radii=(0.16, 0.26, 0.38)):
        """Public candidate builder, for callers that mix their own anchors with
        the panel-zone fallbacks (the angle value sits on its arc first)."""
        x0, x1 = self.ax.get_xlim()
        y0, y1 = self.ax.get_ylim()
        return self._candidates(zones, leader_from, x1 - x0, y1 - y0, x0, y0, radii)

    def place(self, text, candidates, *, color, fontsize, leader_from=None,
              leader_from_index=0, zorder=7, family=None, bbox=None,
              alt_texts=()):
        """Draw *text* at the first candidate that collides with nothing.

        ``candidates`` is an ordered list of ``(x, y, ha, va, rotation)``.  A
        candidate is rejected if its box leaves the panel, overlaps anything
        already reserved, or -- when there is a leader -- if that leader would
        cross something.  If none is clean the least-bad is used, so a label is
        never silently dropped.

        Returns ``(artist, (x, y), ha)``.
        """
        x0, x1 = self.ax.get_xlim()
        w = x1 - x0
        panel = self.ax.get_window_extent(renderer=self.renderer).padded(-2.0)

        artist = self.ax.text(x0, self.ax.get_ylim()[0], text, color=color,
                              fontsize=fontsize, zorder=zorder, family=family,
                              bbox=bbox)
        def sweep():
            """Best (score, ...) over every candidate for the current text."""
            found = None
            for idx, (px, py, ha, va, rot) in enumerate(candidates):
                artist.set_position((px, py))
                artist.set_ha(ha)
                artist.set_va(va)
                artist.set_rotation(rot or 0)
                if rot is not None:
                    artist.set_rotation_mode("anchor")
                try:
                    bb = artist.get_window_extent(renderer=self.renderer)
                except Exception:
                    continue
                # Ranked worst-first: leaving the panel, then overlapping text
                # or a box, then merely being crossed by a dimension line.
                score = (self.overlap(bb)
                         + _outside_area(bb, panel) * 4.0
                         + self.crossed_by_line(bb) * 25.0)
                needs_leader = leader_from is not None and idx >= leader_from_index
                if score == 0.0 and needs_leader:
                    if self.segment_blocked(
                            leader_from, self._leader_anchor((px, py), ha, w)):
                        score = 1.0    # clean box, but the leader crosses
                if found is None or score < found[0]:
                    found = (score, (px, py), ha, va, rot, bb, needs_leader)
                if score == 0.0:
                    break
            return found

        # A long label in a narrow panel may not fit at the requested size at
        # all.  Rather than let it escape the frame, fall back through the
        # caller's more compact wordings first -- a line break costs nothing --
        # and only then shrink, which costs the legibility the size was chosen
        # for.
        best = None
        for shrink in (1.0, 0.92, 0.84, 0.76, 0.68, 0.60):
            artist.set_fontsize(fontsize * shrink)
            for variant in (text,) + tuple(alt_texts):
                artist.set_text(variant)
                found = sweep()
                if found is None:
                    continue
                if best is None or found[0] < best[0]:
                    best = found + (variant, fontsize * shrink)
                if found[0] == 0.0:
                    break
            if best and best[0] == 0.0:
                break

        _, pos, ha, va, rot, bb, needs_leader, variant, size = best
        artist.set_text(variant)
        artist.set_fontsize(size)
        artist.set_position(pos)
        artist.set_ha(ha)
        artist.set_va(va)
        artist.set_rotation(rot or 0)
        self.reserve(bb)
        if needs_leader:
            self._draw_leader(leader_from, pos, ha, w, color)
        return artist, pos, ha

    def place_text(self, text, *, zones, color, fontsize, leader_from=None,
                   radii=(0.16, 0.26, 0.38), **kw):
        """Place a free-floating label, near its feature where possible."""
        x0, x1 = self.ax.get_xlim()
        y0, y1 = self.ax.get_ylim()
        cands = self._candidates(zones, leader_from, x1 - x0, y1 - y0, x0, y0, radii)
        return self.place(text, cands, color=color, fontsize=fontsize,
                          leader_from=leader_from, **kw)

    def place_on_line(self, text, p1, p2, *, color, fontsize,
                      fracs=(0.5, 0.62, 0.38, 0.76, 0.24), gaps=(0.55, 1.5, 2.6),
                      **kw):
        """Place a dimension VALUE on its own dimension line.

        Convention keeps the value on the line it measures, so this slides it
        along and flips it across rather than moving it away.  Only when both
        sides are blocked at every station does the caller's fallback matter --
        which is why the chord value used to land on top of the bbox value.
        """
        p1 = np.asarray(p1, dtype=float)
        p2 = np.asarray(p2, dtype=float)
        d = p2 - p1
        length = float(np.linalg.norm(d))
        if length < 1e-9:
            return None, tuple(p1), "center"
        u = d / length
        n = np.array([-u[1], u[0]])
        rot = float(np.degrees(np.arctan2(u[1], u[0])))
        if rot > 90 or rot <= -90:
            rot += 180

        cands = []
        for gap in gaps:
            for side in (1.0, -1.0):
                for f in fracs:
                    base = p1 + d * f + n * (length * 0.02 + 0.1) * gap * side
                    cands.append((base[0], base[1], "center",
                                  "bottom" if side > 0 else "top", rot))
        on_line = len(cands)

        # When the whole dimension line is congested -- a short chord on a small
        # panel with the bounding box and the value table already down there --
        # the value comes OFF the line on a leader, which is what a draughtsman
        # does.  Without this the placer could only pick the least-bad overlap.
        x0, x1 = self.ax.get_xlim()
        y0, y1 = self.ax.get_ylim()
        mid = tuple(p1 + d * 0.5)
        cands += self._candidates(["TR", "TL", "BR", "BL", "MR", "ML"], mid,
                                  x1 - x0, y1 - y0, x0, y0, (0.14, 0.24, 0.36))
        return self.place(text, cands, color=color, fontsize=fontsize,
                          leader_from=mid, leader_from_index=on_line, **kw)

    def _leader_anchor(self, pos, ha, w):
        """The point on the label the leader should touch."""
        gap = w * 0.012
        if ha == "left":
            return (pos[0] - gap, pos[1])
        if ha == "right":
            return (pos[0] + gap, pos[1])
        return (pos[0], pos[1])

    def _draw_leader(self, target, pos, ha, w, color):
        """Elbow from *target* to the label: a short horizontal landing under
        the text, then a straight run to the feature."""
        from propeller_studio.drawing import dimensions as D

        edge = self._leader_anchor(pos, ha, w)
        stub = w * 0.03
        knee = (edge[0] - stub if ha == "left" else edge[0] + stub, edge[1])
        self.ax.plot([target[0], knee[0], edge[0]],
                     [target[1], knee[1], edge[1]],
                     color=color, lw=D.DIM_LW, zorder=6,
                     solid_capstyle="round")
        self.ax.plot([target[0]], [target[1]], marker="o", ms=1.8,
                     color=color, zorder=7)


def _outside_area(bbox, panel):
    """Area of *bbox* falling outside *panel*, in px^2 (0 when contained)."""
    ix = min(bbox.x1, panel.x1) - max(bbox.x0, panel.x0)
    iy = min(bbox.y1, panel.y1) - max(bbox.y0, panel.y0)
    inside = max(0.0, ix) * max(0.0, iy)
    area = max(0.0, bbox.x1 - bbox.x0) * max(0.0, bbox.y1 - bbox.y0)
    return max(0.0, area - inside)


def _seg_hits_box(a, b, box):
    """Segment/rectangle intersection in display coordinates."""
    ax_, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    if box.contains(ax_, ay) or box.contains(bx, by):
        return True
    edges = (
        ((box.x0, box.y0), (box.x1, box.y0)),
        ((box.x1, box.y0), (box.x1, box.y1)),
        ((box.x1, box.y1), (box.x0, box.y1)),
        ((box.x0, box.y1), (box.x0, box.y0)),
    )
    for p, q in edges:
        if _segments_cross((ax_, ay), (bx, by), p, q):
            return True
    return False


def _orient(p, q, r):
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])


def _segments_cross(p1, p2, p3, p4):
    d1 = _orient(p3, p4, p1)
    d2 = _orient(p3, p4, p2)
    d3 = _orient(p1, p2, p3)
    d4 = _orient(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))
