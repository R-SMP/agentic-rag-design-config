"""Airfoil + section math, in pure Python.

A vendored, extended copy of ``tools/render_blade_sections/sections_geom.py``
and the height-relevant part of ``tools/generate_mesh/ring_height.py``, both of
which are themselves verified ports of ``web/feg/naca.js``, ``placement.js``,
``profiles.js`` and ``ring.js``.  ``propeller_studio/dev/drift_check.py`` diffs
this module's outputs against the live ``web/feg`` modules via Node.

Why a copy: this package is meant to be lifted into a standalone repository.
Importing the multi-agent app's modules would make that a rewrite instead of a
move.

Two coordinate frames appear here, and they agree by construction:

* **profile space** -- ``y`` chordwise in [0, 1] (0 = LEADING edge), ``z``
  normal offset, both as fractions of chord.
* **placed world** -- millimetres, ``placement.js`` convention:
  ``X`` radial (out from the rotation axis), ``Y`` chordwise, ``Z`` axial
  (the propeller rotation axis / thrust direction).

A section's placed points all share one ``X`` (its radius), so the section
drawing is the exact ``(Y, Z)`` projection of the 3D section -- the 2D
drawings and the 3D geometry cannot disagree about shape.
"""

from __future__ import annotations

import math

import numpy as np

# Mirrors web/feg/constants.js.
COUNT_I = 25
CLEARANCE = 1.0
INNER_RADIUS_FIXED = 4.0
HUB = {"radius": 8.28, "baseZ": -5.0, "height": 10.0}

SECTION_KINDS = ("inner", "middle", "outer")


# ---------------------------------------------------------------------------
# Port of web/feg/naca.js
# ---------------------------------------------------------------------------

def build_symmetric_profile(count_i, thickness_pct):
    """Symmetric NACA thickness contour as (y, z) in profile space.

    Walks the lower surface from TE to LE, then the upper surface LE to TE, so
    the result is one closed loop with a consistent winding.
    """
    n = count_i + 1
    samples = [i / (n - 1) for i in range(n)]
    cos_vals = [math.cos(s) for s in samples]
    cs, ce = cos_vals[0], cos_vals[n - 1]
    remapped = [(v - cs) / (ce - cs) for v in cos_vals]

    t_n = thickness_pct * 0.01
    z = [_half_thickness(y, t_n) for y in remapped]

    pts = [(remapped[i], -z[i]) for i in range(n - 1, -1, -1)]
    pts += [(remapped[i], z[i]) for i in range(1, n)]
    return pts


def _half_thickness(y, t_n):
    """NACA 4-digit half-thickness at chordwise fraction *y* (``t_n`` = t/c)."""
    sy = math.sqrt(y) if y > 0 else 0.0
    return (t_n / 0.2) * (
        0.2969 * sy
        - 0.1260 * y
        - 0.3516 * y * y
        + 0.2843 * y * y * y
        - 0.1015 * y * y * y * y
    )


def build_camber_curve(high_point_dec, camber_pct):
    """NACA mean line as 21 (y, z) samples in profile space."""
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


def morph_profile_onto_camber(profile_pts, camber_pts):
    """Offset the symmetric contour along the camber-line normal."""
    n = len(camber_pts)
    out = []
    for (py, pz) in profile_pts:
        f_idx = py * (n - 1)
        seg = min(n - 2, max(0, int(math.floor(f_idx))))
        u = min(1.0, max(0.0, f_idx - seg))
        c0, c1 = camber_pts[seg], camber_pts[seg + 1]
        c_y = c0[0] + (c1[0] - c0[0]) * u
        c_z = c0[1] + (c1[1] - c0[1]) * u
        t_y, t_z = c1[0] - c0[0], c1[1] - c0[1]
        t_len = math.hypot(t_y, t_z) or 1.0
        out.append((c_y + pz * (-t_z / t_len), c_z + pz * (t_y / t_len)))
    return out


# ---------------------------------------------------------------------------
# Per-section parameter resolution (curves.js:sectionParams + profiles.js)
# ---------------------------------------------------------------------------

def interpolate_middle(middle_pos, inner, outer, impeller_radius):
    """Linear inner->outer interpolation of the NACA shape params + radius.

    The middle section has NO independent thickness / camber / crest parameter:
    each is the weighted average of the inner and outer values at
    ``middlePos``, so the middle can only reach a value that BOTH ends reach.
    """
    t = max(0.0, min(1.0, middle_pos))
    return {
        "thickness": inner["thickness"] + (outer["thickness"] - inner["thickness"]) * t,
        "highPt": inner["highPt"] + (outer["highPt"] - inner["highPt"]) * t,
        "camber": inner["camber"] + (outer["camber"] - inner["camber"]) * t,
        "radius": INNER_RADIUS_FIXED + (impeller_radius - INNER_RADIUS_FIXED) * t,
    }


def section_params(kind, params):
    """Resolve one section's shape values, chord, angle and radius.

    ``radius`` is the radial station in mm from the rotation axis.  The blade
    root is at r = 4 mm (NOT the centre), so the middle section's radius is
    ``4 + middlePos * (impellerRadius - 4)``.
    """
    if kind == "inner":
        return {
            "thickness": float(params["innerThickness"]),
            "highPt": float(params["innerMaxPos"]),
            "camber": float(params["innerCamber"]),
            "chord": float(params["innerChord"]),
            "angleDeg": float(params["innerAngle"]),
            "radius": INNER_RADIUS_FIXED,
            "project": False,
        }
    if kind == "outer":
        return {
            "thickness": float(params["outerThickness"]),
            "highPt": float(params["outerMaxPos"]),
            "camber": float(params["outerCamber"]),
            "chord": float(params["outerChord"]),
            "angleDeg": float(params["outerAngle"]),
            "radius": float(params["impellerRadius"]),
            "project": True,
        }
    if kind != "middle":
        raise ValueError("Unknown section %r; expected one of %r" % (kind, SECTION_KINDS))

    m = interpolate_middle(
        float(params["middlePos"]),
        {"thickness": float(params["innerThickness"]),
         "highPt": float(params["innerMaxPos"]),
         "camber": float(params["innerCamber"])},
        {"thickness": float(params["outerThickness"]),
         "highPt": float(params["outerMaxPos"]),
         "camber": float(params["outerCamber"])},
        float(params["impellerRadius"]),
    )
    return {
        "thickness": m["thickness"],
        "highPt": m["highPt"],
        "camber": m["camber"],
        "chord": float(params["middleChord"]),
        "angleDeg": float(params["middleAngle"]),
        "radius": m["radius"],
        "project": False,
    }


# ---------------------------------------------------------------------------
# Placement (placement.js + profiles.js:projectOntoCylinder)
# ---------------------------------------------------------------------------

def place_2d(sp):
    """Return ``place(y, z) -> (Y, Z)`` in mm: the section drawing's frame.

    Identical to ``placement.js``'s Y and Z output, so this IS the (Y, Z)
    projection of the placed 3D section.  The mirror across ``Y = chord/2``
    puts the LEADING edge at +Y; the rotation is the angle of attack about the
    radial axis.
    """
    chord = float(sp["chord"])
    ang = math.radians(float(sp["angleDeg"]))
    ca, sa = math.cos(ang), math.sin(ang)
    half = chord * 0.5

    def place(y, z):
        y_m = half - y * chord
        z_m = z * chord
        return (y_m * ca - z_m * sa, y_m * sa + z_m * ca)

    return place


def build_section_2d(kind, params, count_i=COUNT_I):
    """Closed (N, 2) airfoil outline for *kind*, in mm, in the drawing frame."""
    sp = section_params(kind, params)
    morphed = morph_profile_onto_camber(
        build_symmetric_profile(count_i, sp["thickness"]),
        build_camber_curve(sp["highPt"], sp["camber"]),
    )
    place = place_2d(sp)
    return np.array([place(y, z) for (y, z) in morphed], dtype=float)


def build_section_3d(kind, params, count_i=COUNT_I):
    """Closed (N, 3) placed section in world mm.

    The OUTER section is projected radially onto the impeller cylinder
    (``profiles.js:projectOntoCylinder``), which changes X and Y but never Z --
    which is why the derived ring height ignores the projection.
    """
    sp = section_params(kind, params)
    pts2 = build_section_2d(kind, params, count_i)
    radius = float(sp["radius"])
    out = np.column_stack([np.full(len(pts2), radius), pts2[:, 0], pts2[:, 1]])
    if sp["project"]:
        radial = np.hypot(out[:, 0], out[:, 1])
        k = np.where(
            radial < 1e-9, 1.0,
            float(params["impellerRadius"]) / np.maximum(radial, 1e-9),
        )
        out[:, 0] *= k
        out[:, 1] *= k
    return out


# ---------------------------------------------------------------------------
# Derived ring height (ring.js:computeRingDimensions)
# ---------------------------------------------------------------------------

def ring_dimensions(params):
    """``{bottomZ, topZ, fittedHeight, centerZ}`` for the auto-fitted ring."""
    z = build_section_3d("outer", params)[:, 2]
    z_min, z_max = float(z.min()), float(z.max())
    bottom = z_min - CLEARANCE
    top = z_max + CLEARANCE
    return {
        "bottomZ": bottom,
        "topZ": top,
        "fittedHeight": (z_max - z_min) + 2 * CLEARANCE,
        "centerZ": 0.5 * (top + bottom),
    }


def fitted_ring_height(params):
    """The derived outer-ring height in mm (injected as the .gh's
    ``impellerHeight`` port so RhinoCompute matches the FEG geometry)."""
    return ring_dimensions(params)["fittedHeight"]


# ---------------------------------------------------------------------------
# Quantities the technical drawing dimensions
# ---------------------------------------------------------------------------

def section_metrics(kind, params):
    """Everything the dimensioned section drawing needs, in drawing-frame mm.

    ``max_thickness`` is measured PERPENDICULAR TO THE CAMBER LINE and its
    station is found from the NACA thickness function itself -- it is NOT at
    ``innerMaxPos`` / ``outerMaxPos``.  Those parameters move the CAMBER crest
    only; the thickness peak sits near 30 % chord and no parameter moves it.
    Reporting the crest station as the thickness station is the easiest way to
    mislabel one of these drawings, so the two are computed separately.
    """
    sp = section_params(kind, params)
    chord = sp["chord"]
    t_n = sp["thickness"] * 0.01
    place = place_2d(sp)

    # Max thickness: maximise the NACA half-thickness over a fine chordwise
    # sweep.  Analytic differentiation of the 4-digit polynomial has a sqrt
    # singularity at the leading edge; a sweep is exact to ~1e-4 chord here and
    # cannot converge onto the wrong root.
    ys = np.linspace(1e-6, 1.0, 20001)
    halves = np.array([_half_thickness(float(y), t_n) for y in ys])
    i_max = int(np.argmax(halves))
    y_t = float(ys[i_max])
    half_t = float(halves[i_max])

    cam = build_camber_curve(sp["highPt"], sp["camber"])
    upper = morph_profile_onto_camber([(y_t, half_t)], cam)[0]
    lower = morph_profile_onto_camber([(y_t, -half_t)], cam)[0]

    # Max camber: the mean line's peak.  At zero camber the mean line lies on
    # the chord and there is nothing to dimension.
    cam_arr = np.array(cam, dtype=float)
    j_max = int(np.argmax(np.abs(cam_arr[:, 1])))
    y_c = float(cam_arr[j_max, 0])
    z_c = float(cam_arr[j_max, 1])

    impeller_radius = float(params["impellerRadius"])
    span_den = max(1e-9, impeller_radius - INNER_RADIUS_FIXED)

    return {
        "kind": kind,
        "chord_mm": chord,
        "angle_deg": sp["angleDeg"],
        "radius_mm": sp["radius"],
        "span_fraction": (sp["radius"] - INNER_RADIUS_FIXED) / span_den,
        "thickness_pct": sp["thickness"],
        "camber_pct": sp["camber"],
        "crest_tenths": sp["highPt"],
        "max_thickness_mm": 2.0 * half_t * chord,
        "thickness_station_frac": y_t,
        "thickness_upper_xy": place(*upper),
        "thickness_lower_xy": place(*lower),
        "max_camber_mm": abs(z_c) * chord,
        "camber_station_frac": y_c,
        "camber_crest_xy": place(y_c, z_c),
        "camber_chord_xy": place(y_c, 0.0),
        "has_camber": sp["camber"] > 0,
        "le_xy": place(0.0, 0.0),
        "te_xy": place(1.0, 0.0),
        "camber_line_xy": np.array([place(y, z) for (y, z) in cam], dtype=float),
        "outline_xy": build_section_2d(kind, params),
    }
