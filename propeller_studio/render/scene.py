"""PyVista scene construction: materials, lighting, camera, overlays.

One function -- :func:`render_view` -- turns a
:class:`~propeller_studio.geometry.backends.PropellerGeometry` plus a settings
tree into an image array.  Both the standalone renders and the technical
drawing's 3D views go through it, so a view in the drawing is the same picture
as the standalone render of that angle, only styled differently.

Lights are attached to the CAMERA, not to the world.  A world-fixed rig makes
the top view bright and the bottom view black; a camera rig gives every angle
the same modelling, which is what you want when comparing views on one sheet.
"""

from __future__ import annotations

import math

import numpy as np
import pyvista as pv

from propeller_studio.settings import part_material, resolve_view

pv.OFF_SCREEN = True

# Section colours, matching the repo's existing blade-section renders so the
# curves on the 3D read as the same objects as the 2D section drawings.
SECTION_COLORS = {
    "inner": (37, 99, 235),      # blue
    "middle": (22, 163, 74),     # green
    "outer": (220, 38, 38),      # red
}


def hex_to_rgb(value):
    """``"#b87333"`` -> ``(0.72, 0.45, 0.20)`` floats in 0..1."""
    s = str(value).strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError("Not a hex colour: %r" % (value,))
    return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


# ---------------------------------------------------------------------------
# Environment (for PBR)
# ---------------------------------------------------------------------------

_ENV_CACHE = {}


def environment_texture(n=128):
    """A procedural sky/ground cubemap so PBR metals have something to reflect.

    Without an environment texture a metallic surface reflects nothing and
    renders near-black -- the single most common way a PBR render comes out
    looking broken.  This is deliberately plain (a soft vertical gradient, no
    features) so it flatters the form without printing recognisable reflections
    onto it.
    """
    if n in _ENV_CACHE:
        return _ENV_CACHE[n]

    sky = np.array([238, 243, 252], dtype=float)
    horizon = np.array([206, 213, 226], dtype=float)
    ground = np.array([118, 119, 124], dtype=float)

    grids = []
    for face in range(6):
        img = np.zeros((n, n, 3), dtype=np.uint8)
        for y in range(n):
            t = y / (n - 1)
            if face == 2:            # +Z
                c = sky
            elif face == 3:          # -Z
                c = ground
            else:                    # side faces: sky at top -> ground at base
                c = horizon + (ground - horizon) * t if t > 0.5 else sky + (horizon - sky) * (t * 2)
            img[y, :] = np.clip(c, 0, 255).astype(np.uint8)
        grid = pv.ImageData(dimensions=(n, n, 1))
        grid["data"] = img.reshape(-1, 3, order="C")
        grids.append(grid)

    tex = pv.Texture(grids)
    _ENV_CACHE[n] = tex
    return tex


# ---------------------------------------------------------------------------
# Lighting
# ---------------------------------------------------------------------------

def _camera_light(position, intensity, color=(1.0, 1.0, 1.0)):
    light = pv.Light(position=position, color=color, light_type="cameralight")
    light.intensity = intensity
    return light


# (position in camera space, intensity) triples per preset.
_RIGS = {
    # Classic three-point: key upper-left, fill lower-right, rim behind.
    "studio": [((-0.7, 0.9, 1.0), 0.95), ((1.0, -0.4, 0.7), 0.40), ((0.2, 0.4, -1.0), 0.55)],
    # Broad and low-contrast -- shows shape without hard terminators.
    "soft": [((-0.4, 0.6, 1.0), 0.62), ((0.7, 0.2, 0.8), 0.50), ((0.0, -0.8, 0.6), 0.34),
             ((0.0, 0.0, 1.0), 0.30)],
    # Single hard key with a strong rim: maximum form, deep shadows.
    "dramatic": [((-1.0, 0.5, 0.35), 1.15), ((0.9, -0.3, 0.5), 0.16), ((0.4, 0.8, -1.0), 0.75)],
    # Near-shadowless, even illumination -- the right choice under a drawing.
    "technical": [((0.0, 0.0, 1.0), 0.70), ((-0.8, 0.5, 0.6), 0.42),
                  ((0.8, 0.5, 0.6), 0.42), ((0.0, -0.9, 0.5), 0.34)],
}


def _add_lights(plotter, lighting):
    gain = float(lighting.get("intensity", 1.0))
    custom = lighting.get("custom") or []
    if custom:
        for spec in custom:
            plotter.add_light(_camera_light(
                tuple(spec.get("position", (0, 0, 1))),
                float(spec.get("intensity", 0.6)) * gain,
                hex_to_rgb(spec.get("color", "#ffffff")),
            ))
        return
    for pos, inten in _RIGS[lighting.get("preset", "studio")]:
        plotter.add_light(_camera_light(pos, inten * gain))


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

def direction_from(az_deg, el_deg):
    """Unit eye-direction (from the model toward the camera) for az/el."""
    az, el = math.radians(az_deg), math.radians(el_deg)
    return np.array([math.cos(el) * math.cos(az),
                     math.cos(el) * math.sin(az),
                     math.sin(el)], dtype=float)


def _up_for(direction):
    """+Z up, unless the view looks straight down the axis, where +Z is
    degenerate and +Y is the conventional page-up for a plan view."""
    if abs(direction[2]) > 0.999:
        return np.array([0.0, 1.0, 0.0])
    return np.array([0.0, 0.0, 1.0])


def aim(plotter, center, direction, *, projection="perspective", zoom=1.0):
    d = np.asarray(direction, dtype=float)
    d = d / (np.linalg.norm(d) or 1.0)
    center = np.asarray(center, dtype=float)
    plotter.camera_position = [tuple(center + d), tuple(center), tuple(_up_for(d))]
    if projection == "orthographic":
        plotter.enable_parallel_projection()
    else:
        plotter.disable_parallel_projection()
    plotter.reset_camera()
    if zoom and zoom != 1.0:
        plotter.camera.zoom(float(zoom))


# ---------------------------------------------------------------------------
# Meshes
# ---------------------------------------------------------------------------

def part_to_polydata(part):
    faces = np.hstack([np.full((part.faces.shape[0], 1), 3, dtype=np.int64),
                       part.faces]).ravel()
    return pv.PolyData(np.asarray(part.vertices, dtype=float), faces)


def section_polyline(points, close=True):
    pts = np.asarray(points, dtype=float)
    if close and len(pts) and not np.allclose(pts[0], pts[-1]):
        pts = np.vstack([pts, pts[:1]])
    n = len(pts)
    return pv.PolyData(pts, lines=np.hstack([[n], np.arange(n)]).astype(np.int64))


# ---------------------------------------------------------------------------
# The renderer
# ---------------------------------------------------------------------------

def render_view(geom, s, view, *, width=None, height=None, style=None,
                transparent=None, parallel_scale=None, projection=None,
                background=None):
    """Render *geom* from *view*; return an ``(H, W, 3 or 4)`` uint8 array.

    ``style`` overrides ``settings['render']['overlays']`` and may also carry
    ``shaded`` (False draws the body as flat white, for a line-art view) and
    ``shading_strength`` (blends the body colour toward white).  The drawing
    sheet uses those to get technical-illustration views out of the same code
    path as the photographic renders.
    """
    r = s["render"]
    style = dict(r["overlays"], **(style or {}))
    width = int(width or r["width"])
    height = int(height or r["height"])

    bg = dict(r["background"], **(background or {}))
    mode = bg["mode"]
    if transparent is None:
        transparent = (mode == "transparent")

    plotter = pv.Plotter(off_screen=True, window_size=(width, height), lighting="none")
    try:
        if mode == "gradient":
            plotter.set_background(hex_to_rgb(bg["color2"]), top=hex_to_rgb(bg["color"]))
        elif mode in ("solid", "floor"):
            plotter.set_background(hex_to_rgb(bg["color"]))
        else:
            plotter.set_background((1.0, 1.0, 1.0))

        env = environment_texture()
        plotter.set_environment_texture(env)

        shaded = style.get("shaded", True)
        strength = float(style.get("shading_strength", 1.0))
        polys = {}
        for name, part in geom.ordered_parts():
            poly = part_to_polydata(part)
            polys[name] = poly
            mat = part_material(s, name)
            rgb = np.array(hex_to_rgb(mat["color"]))
            if not shaded:
                rgb = np.array([1.0, 1.0, 1.0])
            elif strength < 1.0:
                rgb = rgb + (np.array([1.0, 1.0, 1.0]) - rgb) * (1.0 - strength)
            plotter.add_mesh(
                poly,
                color=tuple(rgb),
                pbr=bool(shaded),
                metallic=float(mat["metallic"]) * (1.0 if shaded else 0.0),
                roughness=float(mat["roughness"]) if shaded else 1.0,
                opacity=float(mat.get("opacity", 1.0)),
                smooth_shading=True,
                specular=0.0,
                # Unlit when unshaded: with lighting on, a "white" body still
                # picks up Lambert falloff, so a line-art view comes out grey
                # wherever a surface turns away from the camera.  Flat colour is
                # what line art means.
                lighting=bool(shaded),
                ambient=0.0 if shaded else 1.0,
                show_edges=False,
            )
            if style.get("silhouette"):
                try:
                    plotter.add_silhouette(poly, color="black", line_width=2.0)
                except Exception:
                    pass
            if style.get("feature_edges"):
                # Weld first.  three.js emits the hub cylinder with duplicated
                # vertices, so on the raw mesh EVERY triangle edge counts as a
                # boundary edge and the hub renders as a black sunburst.  A
                # clean() merges coincident points and leaves only the real
                # rims and creases.
                welded = poly.clean(tolerance=1e-6)
                edges = welded.extract_feature_edges(
                    feature_angle=float(style.get("feature_angle", 45.0)),
                    boundary_edges=True, feature_edges=True,
                    non_manifold_edges=False, manifold_edges=False,
                )
                if edges.n_points:
                    plotter.add_mesh(edges, color="black", line_width=1.4,
                                     render_lines_as_tubes=False, lighting=False)
            if style.get("wireframe"):
                plotter.add_mesh(poly, style="wireframe", color=(0.25, 0.25, 0.25),
                                 line_width=0.5, opacity=0.45, lighting=False)

        lo, hi = geom.bounds()
        center = (lo + hi) / 2.0
        span = float(np.max(hi - lo))

        # Curves that should be OCCLUDED by the body belong in this pass, where
        # the depth buffer already does the right thing.  The always-on-top
        # case is handled by a composited overlay pass below.
        if style.get("section_curves") and not style.get("section_curves_on_top", True):
            for kind, pts in geom.sections.items():
                tube = section_polyline(pts).tube(radius=_curve_radius(span), n_sides=8)
                plotter.add_mesh(tube, color=tuple(c / 255 for c in SECTION_COLORS[kind]),
                                 lighting=False)

        if mode == "floor":
            span = float(np.max(hi - lo))
            floor = pv.Plane(center=(center[0], center[1], lo[2] - 0.02 * span),
                             direction=(0, 0, 1), i_size=span * 3, j_size=span * 3)
            plotter.add_mesh(floor, color=hex_to_rgb(bg["floor_color"]),
                             pbr=False, ambient=0.35, diffuse=0.75, specular=0.0)

        _add_lights(plotter, r["lighting"])

        name, az, el = resolve_view(view)
        proj = projection or r["projection"]
        aim(plotter, center, direction_from(az, el),
            projection=proj,
            zoom=1.0 if parallel_scale else r.get("zoom", 1.0))
        if parallel_scale:
            # An EXPLICIT scale, not auto-framing: the drawing sheet states a
            # scale in its title block, so the views must actually be at it.
            plotter.camera.parallel_scale = float(parallel_scale)

        if r.get("anti_aliasing", True):
            try:
                plotter.enable_anti_aliasing("ssaa")
            except Exception:
                pass
        if mode == "floor" and bg.get("shadow", True):
            try:
                plotter.enable_shadows()
            except Exception:
                pass

        # Captured verbatim so the overlay pass frames IDENTICALLY.  Letting
        # the overlay call reset_camera() would fit it to the curves' own
        # bounds and slide the overlay off the body by several millimetres.
        camera = _capture_camera(plotter)
        base = plotter.screenshot(return_img=True, transparent_background=bool(transparent))
    finally:
        plotter.close()

    if style.get("section_curves") and style.get("section_curves_on_top", True):
        overlay = _section_curve_pass(geom, camera, span, width, height,
                                      anti_aliasing=r.get("anti_aliasing", True))
        base = _composite(base, overlay)
    return base


def _curve_radius(span):
    """Tube radius for a section curve, scaled to the model so the curve reads
    the same weight on a 60 mm and an 80 mm propeller."""
    return max(span * 0.0022, 0.06)


def _capture_camera(plotter):
    cam = plotter.camera
    return {
        "position": tuple(cam.position),
        "focal_point": tuple(cam.focal_point),
        "up": tuple(cam.up),
        "parallel_projection": bool(cam.parallel_projection),
        "parallel_scale": float(cam.parallel_scale),
        "view_angle": float(cam.view_angle),
        "clipping_range": tuple(cam.clipping_range),
    }


def _apply_camera(plotter, camera):
    cam = plotter.camera
    cam.position = camera["position"]
    cam.focal_point = camera["focal_point"]
    cam.up = camera["up"]
    cam.parallel_projection = camera["parallel_projection"]
    cam.parallel_scale = camera["parallel_scale"]
    cam.view_angle = camera["view_angle"]
    cam.clipping_range = camera["clipping_range"]


def _composite(base, overlay_rgba):
    """Alpha-composite an RGBA overlay onto an RGB or RGBA base."""
    if overlay_rgba is None:
        return base
    a = overlay_rgba[:, :, 3:4].astype(np.float32) / 255.0
    fg = overlay_rgba[:, :, :3].astype(np.float32)
    out = base.copy()
    rgb = out[:, :, :3].astype(np.float32)
    out[:, :, :3] = np.clip(rgb * (1 - a) + fg * a, 0, 255).astype(np.uint8)
    if out.shape[2] == 4:
        out[:, :, 3] = np.maximum(out[:, :, 3], overlay_rgba[:, :, 3])
    return out


def _section_curve_pass(geom, camera, span, width, height, *, anti_aliasing=True):
    """Render ONLY the three section curves, transparent, on the SAME camera.

    A separate pass rather than extra actors in the main scene, because the
    curves lie exactly ON the blade surface and the INNER one is at r = 4 mm --
    inside the 8.28 mm hub.  In one pass the hub simply swallows it and the
    drawing silently loses a third of its subject.  Compositing a dedicated
    pass makes "always visible" a real guarantee instead of a depth-buffer
    coincidence.
    """
    plotter = pv.Plotter(off_screen=True, window_size=(width, height), lighting="none")
    try:
        plotter.set_background((1.0, 1.0, 1.0))
        for kind, pts in geom.sections.items():
            tube = section_polyline(pts).tube(radius=_curve_radius(span), n_sides=8)
            plotter.add_mesh(tube, color=tuple(c / 255 for c in SECTION_COLORS[kind]),
                             lighting=False)
        plotter.add_light(_camera_light((0, 0, 1), 1.0))
        _apply_camera(plotter, camera)
        if anti_aliasing:
            try:
                plotter.enable_anti_aliasing("ssaa")
            except Exception:
                pass
        return plotter.screenshot(return_img=True, transparent_background=True)
    finally:
        plotter.close()
