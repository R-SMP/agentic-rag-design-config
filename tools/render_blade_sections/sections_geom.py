"""Pure-Python port of the blade-section airfoil math.

Faithful port of the in-browser ``web/feg/naca.js`` + ``web/feg/curves.js``
helpers so the server-side ``render_blade_sections`` tool draws the SAME
cross-sections the browser's "Blade sections" view shows:

  * symmetric NACA thickness contour (cos-clustered sampling),
  * NACA mean-line camber,
  * morph the thickness onto the camber,
  * place into a 2D world (TE on the left), scaled by chord and rotated by
    the section's angle of attack.

Middle-section thickness/high-point/camber are the inner→outer interpolation
(``interpolate_middle``); the middle's chord and angle are their own params.

No third-party deps — plain ``math`` — so it's trivially unit-testable.
"""

from __future__ import annotations

import math

# NACA + camber sample count (CONSTANTS.countI in the JS reference).
COUNT_I = 25


def build_symmetric_profile(count_i, thickness_pct):
    """Symmetric thickness contour as a list of (y, z) points (mirrors
    naca.js:buildSymmetricProfile)."""
    n = count_i + 1
    samples = [i / (n - 1) for i in range(n)]
    cos_vals = [math.cos(s) for s in samples]
    cs = cos_vals[0]
    ce = cos_vals[n - 1]
    remapped = [(v - cs) / (ce - cs) for v in cos_vals]

    t_n = thickness_pct * 0.01
    z = []
    for y in remapped:
        sy = math.sqrt(y) if y > 0 else 0.0
        z.append(
            (t_n / 0.2)
            * (
                0.2969 * sy
                - 0.1260 * y
                - 0.3516 * y * y
                + 0.2843 * y * y * y
                - 0.1015 * y * y * y * y
            )
        )

    pts = []
    for i in range(n - 1, -1, -1):
        pts.append((remapped[i], -z[i]))
    for i in range(1, n):
        pts.append((remapped[i], z[i]))
    return pts


def build_camber_curve(high_point_dec, camber_pct):
    """NACA mean-line as 21 (y, z) samples (mirrors naca.js:buildCamberCurve)."""
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
    """Offset the symmetric contour along the camber-line normal (mirrors
    naca.js:morphProfileOntoCamber)."""
    n = len(camber_pts)
    out = []
    for (py, pz) in profile_pts:
        f_idx = py * (n - 1)
        seg = min(n - 2, max(0, int(math.floor(f_idx))))
        u = min(1.0, max(0.0, f_idx - seg))

        c0 = camber_pts[seg]
        c1 = camber_pts[seg + 1]
        c_y = c0[0] + (c1[0] - c0[0]) * u
        c_z = c0[1] + (c1[1] - c0[1]) * u

        t_y = c1[0] - c0[0]
        t_z = c1[1] - c0[1]
        t_len = math.hypot(t_y, t_z) or 1.0
        n_y = -t_z / t_len
        n_z = t_y / t_len
        out.append((c_y + pz * n_y, c_z + pz * n_z))
    return out


def interpolate_middle(middle_pos, inner, outer):
    """Linear inner→outer interpolation of the NACA shape params (mirrors
    profiles.js:interpolateMiddleParams; the radius term is unused in 2D)."""
    t = max(0.0, min(1.0, middle_pos))
    return {
        "thickness": inner["thickness"] + (outer["thickness"] - inner["thickness"]) * t,
        "highPt": inner["highPt"] + (outer["highPt"] - inner["highPt"]) * t,
        "camber": inner["camber"] + (outer["camber"] - inner["camber"]) * t,
    }


def section_params(kind, params):
    """Resolve a section's (thickness, highPt, camber, chord, angleDeg) from
    the 17-param dict (mirrors curves.js:sectionParams)."""
    if kind == "inner":
        return {
            "thickness": params["innerThickness"],
            "highPt": params["innerMaxPos"],
            "camber": params["innerCamber"],
            "chord": params["innerChord"],
            "angleDeg": params["innerAngle"],
        }
    if kind == "outer":
        return {
            "thickness": params["outerThickness"],
            "highPt": params["outerMaxPos"],
            "camber": params["outerCamber"],
            "chord": params["outerChord"],
            "angleDeg": params["outerAngle"],
        }
    m = interpolate_middle(
        params["middlePos"],
        {
            "thickness": params["innerThickness"],
            "highPt": params["innerMaxPos"],
            "camber": params["innerCamber"],
        },
        {
            "thickness": params["outerThickness"],
            "highPt": params["outerMaxPos"],
            "camber": params["outerCamber"],
        },
    )
    return {
        "thickness": m["thickness"],
        "highPt": m["highPt"],
        "camber": m["camber"],
        "chord": params["middleChord"],
        "angleDeg": params["middleAngle"],
    }


def rendered_params_block(params):
    """Compact per-section summary of the values a render was drawn from.

    Attached to a ``view_images`` result so whoever is looking at a render can
    tie the picture to the numbers behind it.  Each shape value is reported
    BOTH as the parameter (a RATIO: % of that section's own chord) and as the
    absolute size it produces (mm), because the two move independently once the
    chord changes — a section whose chord is pinned cannot grow in mm however
    far its ratio is pushed.
    """
    lines = ["Parameters this render was drawn from:"]
    for kind, label in (("inner", "inner "), ("middle", "middle"), ("outer", "outer ")):
        sp = section_params(kind, params)
        c = float(sp["chord"])
        t = float(sp["thickness"])
        cam = float(sp["camber"])
        hp = float(sp["highPt"])
        lines.append(
            f"  {label}: chord {c:g} mm, angle {float(sp['angleDeg']):g} deg, "
            f"thickness {t:g}% of chord (= {t * c / 100.0:.2f} mm), "
            f"camber {cam:g}% (= {cam * c / 100.0:.2f} mm), "
            f"camber crest at {hp:g}/10 chord"
        )
    lines.append(
        "  MIDDLE SECTION: to fatten or reshape it, raise innerThickness / "
        "innerCamber AND outerThickness / outerCamber — the middle is their "
        f"weighted average at middlePos={float(params.get('middlePos', 0)):g}, so "
        "it reaches any value they BOTH reach.  middlePos only slides between "
        "them and cannot exceed either.  (The middle has no independent "
        "thickness / camber / max-position parameter of its own.)"
    )
    return "\n".join(lines)


def build_section_points(kind, params, count_i=COUNT_I):
    """The placed 2D airfoil for ``kind`` as a list of (x, z) points in mm,
    TE on the left and rotated by the section's angle of attack (mirrors
    curves.js:buildSectionPoints)."""
    sp = section_params(kind, params)
    sym = build_symmetric_profile(count_i, sp["thickness"])
    cam = build_camber_curve(sp["highPt"], sp["camber"])
    morphed = morph_profile_onto_camber(sym, cam)

    angle = sp["angleDeg"] * math.pi / 180.0
    ca = math.cos(angle)
    sa = math.sin(angle)
    chord = sp["chord"]

    pts = []
    for (y, z) in morphed:
        xw = (0.5 - y) * chord
        zw = z * chord
        pts.append((xw * ca - zw * sa, xw * sa + zw * ca))
    return pts
