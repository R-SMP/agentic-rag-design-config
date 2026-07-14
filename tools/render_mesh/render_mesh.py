"""Visual rendering and mesh quality-checking core (trimesh backend).

Exposes :func:`render_and_check` — the render+check step that the merged
``generate_and_render_propeller`` tool runs after a successful geometry
build.  ``tools/__init__`` wires it as the active backend when the trimesh
render library is selected.
"""

from pathlib import Path

import numpy as np
import trimesh
import pyrender
from PIL import Image

from config import ATTEMPTS_DIR

# Module-level toggle: when False the deterministic quality checks
# (watertight, volume, degenerate faces) are skipped.  Visual rendering
# is always performed.
MESH_CHECKS_ENABLED: bool = True


def set_mesh_checks(enabled: bool) -> None:
    """Turn deterministic mesh quality checks on or off."""
    global MESH_CHECKS_ENABLED
    MESH_CHECKS_ENABLED = enabled


_RENDER_NAMES = ("render_isometric.png", "render_top.png", "render_side.png")


def _validate_output_dir(raw: str) -> tuple[Path | None, str | None]:
    """Resolve and validate an attempt folder for writing renders.

    The folder must exist (created by ``new_attempt``) and live under
    ``logs/attempts/``.  Pre-existing render PNGs are NOT an error — the
    caller reuses them in place (identical parameters give identical
    geometry, so re-running this tool needs no new attempt).
    """
    if not isinstance(raw, str) or not raw.strip():
        return None, (
            "Error: missing or non-string 'output_dir'.  Pass the "
            "absolute path of the attempt folder created by "
            "``new_attempt`` (the same path the hand-off carries "
            "under ``Current attempt:``)."
        )
    path = Path(raw).resolve()
    if not path.is_dir():
        return None, (
            f"Error: '{raw}' is not an existing directory.  Create the "
            f"attempt folder first via ``new_attempt`` and pass its "
            f"absolute path."
        )
    try:
        attempts_root = ATTEMPTS_DIR.resolve()
    except OSError:
        attempts_root = ATTEMPTS_DIR
    if attempts_root not in path.parents and path != attempts_root:
        return None, (
            f"Error: '{path}' is not an attempt folder under "
            f"{attempts_root}.  The render step only writes inside an "
            f"attempt folder."
        )
    return path, None


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _look_at_matrix(eye, target, up=None):
    """Compute a 4x4 camera-to-world pose matrix (OpenGL convention)."""
    if up is None:
        up = np.array([0.0, 0.0, 1.0])
    eye = np.asarray(eye, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    up = np.asarray(up, dtype=np.float64)

    forward = target - eye
    forward /= np.linalg.norm(forward)

    right = np.cross(forward, up)
    norm = np.linalg.norm(right)
    if norm < 1e-6:
        up = np.array([1.0, 0.0, 0.0])
        right = np.cross(forward, up)
        norm = np.linalg.norm(right)
    right /= norm

    true_up = np.cross(right, forward)

    pose = np.eye(4)
    pose[:3, 0] = right
    pose[:3, 1] = true_up
    pose[:3, 2] = -forward
    pose[:3, 3] = eye
    return pose


def _compute_framing_distance(center, bounds, eye_direction, up_hint, yfov, aspect, padding=0.15):
    """Compute camera distance so the mesh bounding box fills the viewport.

    Projects all 8 bounding-box corners onto the camera's view plane (using
    the right/up vectors derived from *eye_direction* and *up_hint*), then
    calculates the minimum distance that keeps every projected corner inside
    the frame with *padding* fraction of margin on each side.
    """
    eye_direction = np.asarray(eye_direction, dtype=np.float64)
    eye_direction = eye_direction / np.linalg.norm(eye_direction)

    # Build a temporary pose just to obtain the camera right/up vectors
    temp_eye = center + eye_direction
    pose = _look_at_matrix(temp_eye, center, up_hint)
    cam_right = pose[:3, 0]
    cam_up = pose[:3, 1]

    # 8 bounding-box corners
    bmin, bmax = bounds[0], bounds[1]
    corners = np.array([
        [bmin[0], bmin[1], bmin[2]],
        [bmin[0], bmin[1], bmax[2]],
        [bmin[0], bmax[1], bmin[2]],
        [bmin[0], bmax[1], bmax[2]],
        [bmax[0], bmin[1], bmin[2]],
        [bmax[0], bmin[1], bmax[2]],
        [bmax[0], bmax[1], bmin[2]],
        [bmax[0], bmax[1], bmax[2]],
    ])

    # Project onto the camera plane (relative to the look-at center)
    relative = corners - center
    proj_right = relative @ cam_right
    proj_up = relative @ cam_up

    half_w = max(abs(proj_right.max()), abs(proj_right.min()))
    half_h = max(abs(proj_up.max()), abs(proj_up.min()))

    # Add padding so the model doesn't touch the frame edges
    half_w *= (1.0 + padding)
    half_h *= (1.0 + padding)

    # Distance needed so that half_h / half_w fit within the perspective frustum
    d_vert = half_h / np.tan(yfov / 2.0)
    d_horiz = half_w / (np.tan(yfov / 2.0) * aspect)

    return max(d_vert, d_horiz)


def _render_mesh_views(mesh, output_dir):
    """Render a trimesh object from three viewpoints using pyrender.

    The camera is placed per-view at the exact distance that frames the
    model's bounding box tightly in the viewport (with a small margin).

    Returns a list of saved image file paths.
    """
    IMG_W, IMG_H = 800, 600
    YFOV = np.pi / 4.0
    aspect = IMG_W / IMG_H

    scene = pyrender.Scene(
        ambient_light=np.array([0.3, 0.3, 0.3, 1.0]),
        bg_color=np.array([1.0, 1.0, 1.0, 1.0]),
    )

    py_mesh = pyrender.Mesh.from_trimesh(mesh, smooth=True)
    scene.add(py_mesh)

    # Directional lights from multiple angles for good coverage
    for direction in ([1, 1, 2], [-1, -1, 2], [0, 0, -1]):
        light = pyrender.DirectionalLight(color=np.ones(3), intensity=3.0)
        light_pose = _look_at_matrix(
            np.array(direction, dtype=float), np.zeros(3)
        )
        scene.add(light, pose=light_pose)

    center = mesh.centroid
    camera = pyrender.PerspectiveCamera(yfov=YFOV)

    # Each view: (name, eye_direction_from_center, up_hint)
    views = [
        ("isometric", np.array([1.0, 1.0, 0.7]),  np.array([0.0, 0.0, 1.0])),
        ("top",       np.array([0.0, 0.0, 1.0]),  np.array([0.0, 1.0, 0.0])),
        ("side",      np.array([1.0, 0.0, 0.0]),  np.array([0.0, 0.0, 1.0])),
    ]

    renderer = pyrender.OffscreenRenderer(IMG_W, IMG_H)
    saved = []

    for name, eye_dir, up in views:
        dist = _compute_framing_distance(
            center, mesh.bounds, eye_dir, up, YFOV, aspect, padding=0.15,
        )
        eye = center + (eye_dir / np.linalg.norm(eye_dir)) * dist

        pose = _look_at_matrix(eye, center, up)
        cam_node = scene.add(camera, pose=pose)
        color, _ = renderer.render(scene)
        scene.remove_node(cam_node)

        img = Image.fromarray(color)
        path = output_dir / f"render_{name}.png"
        img.save(str(path))
        saved.append(path)

    renderer.delete()
    return saved


# ---------------------------------------------------------------------------
# Render & check core (trimesh backend)
# ---------------------------------------------------------------------------


def render_and_check(mesh_path: str, output_dir: str) -> str:
    """Render the mesh at ``mesh_path`` from three viewpoints (isometric,
    top-down, side) and run geometric quality checks (trimesh backend).

    Internal helper — the render+check phase of
    ``generate_and_render_propeller`` (the merged geometry+renders tool).
    ``tools/__init__`` wires this as the active render backend when the
    trimesh library is selected.

    - ``mesh_path``: absolute path of the .obj mesh to render.
    - ``output_dir``: the attempt folder where the three render PNGs are
      written.  If the three render files are already present they are
      REUSED (not re-rendered) — identical parameters give identical
      geometry.

    Returns an analysis report listing the saved render paths plus any
    warnings or issues detected.
    """
    if not isinstance(mesh_path, str) or not mesh_path.strip():
        return (
            "Error: missing or non-string 'mesh_path' — the render step "
            "was given no mesh to render."
        )
    mesh_path_obj = Path(mesh_path)
    if not mesh_path_obj.is_file():
        return (
            f"Error: '{mesh_path}' is not an existing file — the geometry "
            f"must be generated before the render step runs."
        )

    out_dir, err = _validate_output_dir(output_dir)
    if err is not None:
        return err

    try:
        loaded = trimesh.load(str(mesh_path_obj))
    except Exception as exc:
        return f"Error loading mesh: {exc}"

    if isinstance(loaded, trimesh.Scene):
        geometries = list(loaded.geometry.values())
        if not geometries:
            return "Error: Mesh file loaded as empty scene (no geometry)."
        mesh = trimesh.util.concatenate(geometries)
    else:
        mesh = loaded

    findings = []

    # --- Basic statistics (always reported) ---
    n_verts = len(mesh.vertices)
    n_faces = len(mesh.faces)
    findings.append(f"Vertices: {n_verts}, Faces: {n_faces}")

    if n_verts == 0 or n_faces == 0:
        findings.append("CRITICAL: Mesh is empty — generation likely failed.")
        return "\n".join(findings)

    bb = mesh.extents
    findings.append(
        f"Bounding box: {bb[0]:.1f} x {bb[1]:.1f} x {bb[2]:.1f} mm"
    )

    # --- Deterministic quality checks (only when enabled) ---
    if MESH_CHECKS_ENABLED:
        # Watertight / volume
        findings.append(f"Watertight: {'yes' if mesh.is_watertight else 'no'}")
        if mesh.is_watertight:
            vol = mesh.volume
            findings.append(f"Volume: {vol:.1f} mm3")
            if vol <= 0:
                findings.append(
                    "WARNING: Non-positive volume — normals may be inverted."
                )

        # Degenerate faces
        face_areas = mesh.area_faces
        n_degen = int(np.sum(face_areas < 1e-10))
        if n_degen > 0:
            pct = 100.0 * n_degen / n_faces
            findings.append(
                f"WARNING: {n_degen} degenerate faces ({pct:.1f}% of total)"
            )
    else:
        findings.append("(Deterministic quality checks skipped)")

    # --- Renders: reuse if already present, else render fresh ---
    # Identical parameters produce identical geometry, so when all three
    # render PNGs already exist we REUSE them (no re-render, no need for a
    # new attempt).  Only the render files are handled this way — the mesh
    # and parameters stay immutable.
    existing_renders = [out_dir / n for n in _RENDER_NAMES
                        if (out_dir / n).is_file()]
    if len(existing_renders) == len(_RENDER_NAMES):
        findings.append(
            "Renders already present — reused in place (identical "
            "parameters give identical geometry; not re-rendered):"
        )
        for p in existing_renders:
            findings.append(f"  {p.resolve()}")
    else:
        try:
            render_paths = _render_mesh_views(mesh, out_dir)
            findings.append("Renders saved:")
            for p in render_paths:
                findings.append(f"  {p.resolve()}")
        except Exception as exc:
            findings.append(f"Rendering skipped (error: {exc})")

    findings.append(f"Attempt folder: {out_dir.resolve()}")

    # --- Summary ---
    if MESH_CHECKS_ENABLED:
        warnings = [f for f in findings if "WARNING" in f or "CRITICAL" in f]
        if warnings:
            findings.append(
                f"\n{len(warnings)} issue(s) detected — review parameters "
                f"and consider regenerating."
            )
        else:
            findings.append(
                "\nMesh appears geometrically valid. No issues detected."
            )

    return "\n".join(findings)
