"""Derived outer-ring height for the propeller.

The outer ring AUTO-FITS the outer blade section — its height is NOT an input
parameter (``impellerHeight`` was removed).  This module is the single source
of truth for that derived height on the server side, so the RhinoCompute
geometry's ring height stays identical to the in-browser FEG 3D preview: the
computed value is injected into the ``.gh`` definition in place of the old
``impellerHeight`` input.

It ports, verbatim, the height-relevant part of ``web/feg``:
  * ``naca.js``      — symmetric NACA thickness + camber mean-line + morph
  * ``placement.js`` — the axial (Z) coordinate of the placed outer section
  * ``ring.js``      — ``fittedHeight = (zMax - zMin) + 2·clearance``

``projectOntoCylinder`` (profiles.js) keeps Z unchanged, so the cylinder
projection is irrelevant to the height and is intentionally not ported.  The
fitted height therefore depends on exactly five params: ``outerThickness,
outerMaxPos, outerCamber, outerChord, outerAngle``.

**Drift guard:** ``extra_utilities/smoke_test_ring_height.py`` verifies this
port bit-for-bit against the real ``web/feg`` modules (Python vs Node,
< 1e-9 mm) over hundreds of param sets.  Keep this module and ``web/feg`` in
sync; the constants below mirror ``web/feg/constants.js``.
"""
from __future__ import annotations

import math

# Mirror web/feg/constants.js (guarded by smoke_test_ring_height.py).
_COUNT_I = 25
_CLEARANCE = 1.0


# ---- Port of web/feg/naca.js ------------------------------------------------
def _build_symmetric_profile(count_i: int, thickness_pct: float):
    n = count_i + 1
    samples = [i / (n - 1) for i in range(n)]
    cos_vals = [math.cos(s) for s in samples]
    cs = cos_vals[0]
    ce = cos_vals[n - 1]
    remapped = [(v - cs) / (ce - cs) for v in cos_vals]
    t_n = thickness_pct * 0.01
    z = []
    for y in remapped:
        sy = 0.0 if y <= 0 else math.sqrt(y)
        z.append((t_n / 0.2) * (
            0.2969 * sy
            - 0.1260 * y
            - 0.3516 * y * y
            + 0.2843 * y * y * y
            - 0.1015 * y * y * y * y
        ))
    pts = []
    for i in range(n - 1, -1, -1):
        pts.append((remapped[i], -z[i]))
    for i in range(1, n):
        pts.append((remapped[i], z[i]))
    return pts


def _build_camber_curve(high_point_dec: float, camber_pct: float):
    p = max(0.001, min(0.999, high_point_dec * 0.1))
    m = camber_pct * 0.01
    n = 21
    pts = []
    for i in range(n):
        x = i / (n - 1)
        if x <= p:
            z = (m / (p * p)) * (2 * p * x - x * x)
        else:
            denom = (1 - p) * (1 - p)
            z = (m / denom) * ((1 - 2 * p) + 2 * p * x - x * x)
        pts.append((x, z))
    return pts


def _morph_profile_onto_camber(profile_pts, camber_pts):
    n = len(camber_pts)
    out = []
    for (py, pz) in profile_pts:
        f_idx = py * (n - 1)
        seg_idx = min(n - 2, max(0, math.floor(f_idx)))
        u = min(1.0, max(0.0, f_idx - seg_idx))
        c0y, c0z = camber_pts[seg_idx]
        c1y, c1z = camber_pts[seg_idx + 1]
        c_y = c0y + (c1y - c0y) * u
        c_z = c0z + (c1z - c0z) * u
        t_y = c1y - c0y
        t_z = c1z - c0z
        t_len = math.sqrt(t_y * t_y + t_z * t_z) or 1.0
        n_y = -t_z / t_len
        n_z = t_y / t_len
        out.append((c_y + pz * n_y, c_z + pz * n_z))
    return out


# ---- Fitted outer-ring height ----------------------------------------------
def fitted_ring_height(params: dict) -> float:
    """Return the derived outer-ring height (mm) for *params* — identical to
    the FEG preview's ``computeRingDimensions(...).fittedHeight``.

    Reads only the five outer-section keys.  Raises ``KeyError`` if any is
    missing (callers should have validated the param set first).
    """
    outer_thickness = float(params["outerThickness"])
    outer_max_pos = float(params["outerMaxPos"])
    outer_camber = float(params["outerCamber"])
    outer_chord = float(params["outerChord"])
    outer_angle = float(params["outerAngle"])

    sym = _build_symmetric_profile(_COUNT_I, outer_thickness)
    cam = _build_camber_curve(outer_max_pos, outer_camber)
    morphed = _morph_profile_onto_camber(sym, cam)

    ang = math.radians(outer_angle)
    ca, sa = math.cos(ang), math.sin(ang)
    half = outer_chord * 0.5
    # placeProfile Z (projectOntoCylinder keeps Z, so it is ignored):
    #   yM = chord/2 - y*chord ; zM = z*chord ; zR = yM*sin + zM*cos
    zs = [
        (half - y * outer_chord) * sa + (z * outer_chord) * ca
        for (y, z) in morphed
    ]
    return (max(zs) - min(zs)) + 2 * _CLEARANCE
