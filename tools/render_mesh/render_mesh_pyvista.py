"""Mesh quality-checking tool — PyVista / VTK backend for the metrics,
shared pyrender pipeline for the visual renders.

Mirrors the contract of ``tools/render_mesh/render_mesh.py`` (the
trimesh-metrics backend): same arguments, same three render
filenames, same attempt-folder integrity rules, same
``set_mesh_checks`` toggle.  Only the deterministic-checks library
differs here — the visual renders go through the same pyrender
pipeline used by the trimesh backend so the three PNGs are visually
identical regardless of which backend was chosen at startup.

The two tools register the SAME LangChain tool name
(``render_and_check_mesh``) so prompt fragments and routing wiring
stay backend-agnostic.  ``tools/__init__.py`` decides which of the
two is bound to the Tool Caller for a given session based on the
user's startup choice.
"""

from pathlib import Path

import numpy as np
import pyvista as pv
import trimesh
from langchain_core.tools import tool

from config import ATTEMPTS_DIR
from tools.render_mesh.render_mesh import _render_mesh_views

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

    The folder must exist (created by ``new_attempt``), live under
    ``logs/attempts/``, and not already contain any of the three
    render PNGs this tool produces.
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
            f"{attempts_root}.  ``render_and_check_mesh`` only writes "
            f"inside an attempt folder."
        )
    existing = [n for n in _RENDER_NAMES if (path / n).exists()]
    if existing:
        return None, (
            f"Error: render file(s) {existing} already exist in "
            f"{path}.  Attempt folders are append-only — renders "
            f"cannot be overwritten.  Create a NEW attempt via "
            f"``new_attempt`` if these parameters need re-rendering."
        )
    return path, None


# ---------------------------------------------------------------------------
# Mesh load + metric helpers
# ---------------------------------------------------------------------------


def _load_polydata(mesh_path: Path) -> pv.PolyData:
    """Read *mesh_path* and return a triangulated PolyData.

    PyVista's reader sometimes returns a ``MultiBlock`` for OBJ files
    that carry multiple geometry groups.  In that case the blocks are
    merged into a single PolyData, then triangulated so per-cell area
    arrays have well-defined semantics.
    """
    raw = pv.read(str(mesh_path))
    if isinstance(raw, pv.MultiBlock):
        # Concatenate every PolyData child into one mesh.
        polys = [b for b in raw if isinstance(b, pv.PolyData) and b.n_points > 0]
        if not polys:
            raise ValueError("Mesh file loaded as empty MultiBlock (no PolyData).")
        mesh = polys[0].copy()
        for extra in polys[1:]:
            mesh = mesh.merge(extra)
    else:
        mesh = raw

    if not isinstance(mesh, pv.PolyData):
        # extract_surface returns PolyData for any other dataset type.
        mesh = mesh.extract_surface()

    if not mesh.is_all_triangles:
        mesh = mesh.triangulate()
    return mesh


def _load_trimesh_for_render(mesh_path: Path) -> "trimesh.Trimesh":
    """Re-load *mesh_path* via trimesh so the shared pyrender pipeline
    can render it.  Mirrors the loader logic in
    ``tools/render_mesh/render_mesh.py`` (Scene → concatenated mesh)."""
    loaded = trimesh.load(str(mesh_path))
    if isinstance(loaded, trimesh.Scene):
        geometries = list(loaded.geometry.values())
        if not geometries:
            raise ValueError(
                "Mesh file loaded as empty trimesh Scene (no geometry)."
            )
        return trimesh.util.concatenate(geometries)
    return loaded


def _signed_volume(mesh: pv.PolyData) -> float:
    """Return the mesh's signed volume in mm^3.

    PyVista's ``volume`` property is unsigned and only meaningful for
    closed surfaces.  We compute the signed volume directly via the
    divergence-theorem sum over triangles so that inverted normals
    surface as a non-positive value (mirroring the trimesh backend's
    ``mesh.volume`` semantics).
    """
    pts = np.asarray(mesh.points, dtype=np.float64)
    # PyVista PolyData face array is flat: [n0, i00, i01, ..., n1, i10, ...].
    # For an all-triangles mesh every n_k == 3, so we reshape to (-1, 4) and
    # drop the leading count column.
    faces = mesh.faces.reshape(-1, 4)[:, 1:4]
    tri = pts[faces]
    v0, v1, v2 = tri[:, 0], tri[:, 1], tri[:, 2]
    # Signed volume contribution of each tetrahedron formed with the origin.
    signed = np.einsum("ij,ij->i", v0, np.cross(v1, v2)) / 6.0
    return float(signed.sum())


# ---------------------------------------------------------------------------
# Render & check tool
# ---------------------------------------------------------------------------


@tool("render_and_check_mesh")
def render_and_check_mesh_pv(mesh_path: str, output_dir: str) -> str:
    """Render the mesh at ``mesh_path`` from three viewpoints (isometric,
    top-down, side) and run geometric quality checks.

    PyVista / VTK backend.  Same contract as the trimesh backend.

    Both arguments are REQUIRED.

    - ``mesh_path``: absolute path of the .obj mesh to render.  Pass
      the path that ``generate_propeller_mesh`` just returned — do
      NOT call this tool with a guessed path.
    - ``output_dir``: absolute path of the attempt folder where the
      three render PNGs should be written.  Pass the same attempt
      folder that holds the mesh (the path the hand-off carries
      under ``Current attempt:``).  The folder must already exist
      (created by ``new_attempt``) and must NOT already contain any
      of the three render files — attempt folders are append-only.

    Returns an analysis report listing the saved render paths plus
    any warnings or issues detected.
    """
    if not isinstance(mesh_path, str) or not mesh_path.strip():
        return (
            "Error: missing or non-string 'mesh_path' argument.  Pass "
            "the absolute path that generate_propeller_mesh returned."
        )
    mesh_path_obj = Path(mesh_path)
    if not mesh_path_obj.is_file():
        return (
            f"Error: '{mesh_path}' is not an existing file.  Run "
            f"generate_propeller_mesh first and pass its returned path."
        )

    out_dir, err = _validate_output_dir(output_dir)
    if err is not None:
        return err

    try:
        mesh = _load_polydata(mesh_path_obj)
    except Exception as exc:
        return f"Error loading mesh: {exc}"

    findings: list[str] = []

    # --- Basic statistics (always reported) ---
    n_verts = mesh.n_points
    n_faces = mesh.n_cells
    findings.append(f"Vertices: {n_verts}, Faces: {n_faces}")

    if n_verts == 0 or n_faces == 0:
        findings.append("CRITICAL: Mesh is empty — generation likely failed.")
        return "\n".join(findings)

    bb = mesh.bounds  # (xmin, xmax, ymin, ymax, zmin, zmax)
    bx = bb[1] - bb[0]
    by = bb[3] - bb[2]
    bz = bb[5] - bb[4]
    findings.append(f"Bounding box: {bx:.1f} x {by:.1f} x {bz:.1f} mm")

    # --- Deterministic quality checks (only when enabled) ---
    if MESH_CHECKS_ENABLED:
        # Watertight: PyVista exposes boundary edges via ``n_open_edges``
        # (count of edges shared by exactly one face) and non-manifold
        # status via ``is_manifold`` (no edges shared by 3+ faces).  A
        # watertight mesh has zero of both.
        is_watertight = (mesh.n_open_edges == 0) and bool(mesh.is_manifold)
        findings.append(f"Watertight: {'yes' if is_watertight else 'no'}")
        if is_watertight:
            vol = _signed_volume(mesh)
            findings.append(f"Volume: {vol:.1f} mm3")
            if vol <= 0:
                findings.append(
                    "WARNING: Non-positive volume — normals may be inverted."
                )

        # Degenerate faces: VTK's compute_cell_sizes attaches an ``Area``
        # array per cell.  Threshold matches the trimesh backend (mm^2).
        sized = mesh.compute_cell_sizes(length=False, area=True, volume=False)
        face_areas = np.asarray(sized.cell_data["Area"], dtype=np.float64)
        n_degen = int(np.sum(face_areas < 1e-10))
        if n_degen > 0:
            pct = 100.0 * n_degen / n_faces
            findings.append(
                f"WARNING: {n_degen} degenerate faces ({pct:.1f}% of total)"
            )
    else:
        findings.append("(Deterministic quality checks skipped)")

    # --- Render from multiple viewpoints (always performed) ---
    # Renders go through the shared pyrender pipeline so the three
    # PNGs are visually identical regardless of which metric backend
    # was selected.  Re-load the mesh via trimesh for the renderer.
    render_paths: list[Path] = []
    try:
        render_mesh = _load_trimesh_for_render(mesh_path_obj)
        render_paths = _render_mesh_views(render_mesh, out_dir)
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
