"""Per-component mesh-quality diagnostic.

Standalone script — run independently of the multi-agent system.

Usage (run from the project root):
    python extra_utilities/check_mesh_components.py <path/to/mesh.obj>

What it does
------------
Parses an .obj file group-by-group (``g <name>`` markers), then
reports for EACH group on its own AND for the whole mesh as a single
concatenated geometry:

    - vertex count
    - face count
    - watertightness (every edge shared by exactly two faces)
    - number of degenerate faces (triangle area < 1e-10 mm^2)
    - signed volume (only when watertight)

Each view is reported twice: as written in the .obj (no welding) and
again after merging coincident vertices.  The diff between the two
isolates "missing weld" defects from genuine geometry defects.

The metrics + threshold match the live ``render_and_check_mesh``
tools so this script's "watertight / degenerate" numbers are directly
comparable to the QC line the Tool Caller emits during a session.

Why per-component?
------------------
The propeller generator's RhinoCompute path can fall back from a
single welded ``MeshFinal`` output to four separately-emitted
components (``MeshLauncher``, ``MeshRing``, ``MeshProfile``,
``MeshSimpleInterface``).  In the fallback case the .obj contains
multiple ``g`` groups whose seams are NOT welded across components,
so the combined mesh is structurally non-watertight even when each
component is watertight on its own.  This script makes that
distinction visible: if every component reports ``watertight=yes``
but the combined mesh reports ``watertight=no``, the failure is
purely an export-side weld issue, not a parameter-quality issue.

Component-level analysis when MeshFinal is the primary output
-------------------------------------------------------------
When ``MeshFinal`` was the primary output, ``propeller_mesh.obj``
contains only one ``g MeshFinal`` group — the four individual
components are NOT in that file.  To still allow per-component
inspection, the live generator silently writes a sidecar file
``propeller_mesh_components.obj`` next to the main file containing
the four named components as ``g`` groups.  This script
auto-discovers that sidecar (sibling file in the same folder) and
runs the same analysis on it as a separate section after the
primary report.
"""

import sys
from pathlib import Path

import numpy as np
import trimesh

DEGEN_THRESHOLD_MM2 = 1e-10

# Example of command to run with path (from the project root):
'''
.venv/Scripts/python.exe extra_utilities/check_mesh_components.py "previous_sessions/ID002_20260429_140653/attempts/20260429_140723_001_user_specified_17_params/propeller_mesh.obj"
'''

def parse_obj_groups(path: Path):
    """Yield ``(group_name, vertices_array, faces_array)`` per ``g`` group.

    Vertex indices are remapped per group so each yielded
    ``(verts, faces)`` pair stands alone — usable as-is to construct
    a ``trimesh.Trimesh``.

    Faces with more than three vertex indices are triangulated as a
    simple fan from the first index.  ``v/vt``, ``v/vt/vn``, and
    ``v//vn`` face-token formats are all accepted; only the vertex
    index (the part before the first slash) is consumed.
    """
    all_vertices: list[tuple[float, float, float]] = []
    groups: list[tuple[str, list[tuple[int, int, int]]]] = []
    current: tuple[str, list[tuple[int, int, int]]] | None = None

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            tok = line.strip().split()
            if not tok:
                continue
            head = tok[0]
            if head == "v":
                all_vertices.append((float(tok[1]), float(tok[2]), float(tok[3])))
            elif head == "g":
                name = " ".join(tok[1:]) if len(tok) > 1 else f"group_{len(groups) + 1}"
                current = (name, [])
                groups.append(current)
            elif head == "f":
                if current is None:
                    current = ("(default)", [])
                    groups.append(current)
                idx: list[int] = []
                for t in tok[1:]:
                    v_part = t.split("/")[0]
                    idx.append(int(v_part) - 1)
                if len(idx) == 3:
                    current[1].append((idx[0], idx[1], idx[2]))
                elif len(idx) > 3:
                    for i in range(1, len(idx) - 1):
                        current[1].append((idx[0], idx[i], idx[i + 1]))

    for name, faces_global in groups:
        if not faces_global:
            continue
        used = sorted({i for tri in faces_global for i in tri})
        if not used:
            continue
        remap = {old: new for new, old in enumerate(used)}
        verts = np.array([all_vertices[i] for i in used], dtype=np.float64)
        faces = np.array(
            [[remap[i] for i in tri] for tri in faces_global], dtype=np.int64
        )
        yield name, verts, faces


def measure(mesh: trimesh.Trimesh) -> dict:
    """Compute the four metrics for one Trimesh."""
    n_verts = len(mesh.vertices)
    n_faces = len(mesh.faces)
    if n_faces == 0:
        return {
            "verts": n_verts, "faces": 0,
            "watertight": False, "degenerate": 0, "volume": None,
        }
    watertight = bool(mesh.is_watertight)
    n_degen = int(np.sum(mesh.area_faces < DEGEN_THRESHOLD_MM2))
    volume = float(mesh.volume) if watertight else None
    return {
        "verts": n_verts, "faces": n_faces,
        "watertight": watertight, "degenerate": n_degen,
        "volume": volume,
    }


def fmt_row(label: str, m: dict, label_width: int) -> str:
    line = (
        f"  {label:<{label_width}}  "
        f"verts={m['verts']:>6}  faces={m['faces']:>6}  "
        f"watertight={'yes' if m['watertight'] else 'no ':<3}  "
        f"degenerate={m['degenerate']:>4}"
    )
    if m["faces"]:
        pct = 100.0 * m["degenerate"] / m["faces"]
        line += f" ({pct:5.2f}%)"
    if m["volume"] is not None:
        line += f"  volume={m['volume']:.1f} mm^3"
    return line


def analyze_file(path: Path, banner: str) -> int:
    """Run the per-component + combined diagnostic on one .obj file.

    Returns 0 on success, 1 if no geometry groups could be parsed.
    """
    print("=" * 72)
    print(banner)
    print(f"  {path}")
    print("=" * 72)
    print()

    components: list[tuple[str, trimesh.Trimesh]] = []
    for name, verts, faces in parse_obj_groups(path):
        # process=False keeps the file's vertices verbatim (no welding).
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        components.append((name, mesh))

    if not components:
        print("No geometry groups parsed.  Is the file a valid .obj with 'v' / 'f' lines?")
        return 1

    label_width = max(
        len(name) for name, _ in components + [("Combined mesh", None)]
    )

    print("--- Per-component metrics (as written, no weld) ---")
    for name, mesh in components:
        print(fmt_row(name, measure(mesh), label_width))

    print()
    print("--- Per-component metrics after vertex-weld (each component welded singly) ---")
    # Same per-component view, but each component's internal coincident
    # vertices are merged first.  Isolates "unwelded internal vertices"
    # (e.g. Draco-emitted duplicates) from genuinely open geometry.
    for name, mesh in components:
        welded = mesh.copy()
        welded.merge_vertices()
        print(fmt_row(name, measure(welded), label_width))

    print()
    print("--- Combined mesh (all groups concatenated as written, no weld) ---")
    if len(components) > 1:
        combined = trimesh.util.concatenate([m for _, m in components])
    else:
        combined = components[0][1]
    print(fmt_row("Combined mesh", measure(combined), label_width))

    print()
    print("--- Combined mesh after vertex-weld (diagnostic only) ---")
    welded_combined = combined.copy()
    welded_combined.merge_vertices()
    print(fmt_row("Welded combined", measure(welded_combined), label_width))
    if not measure(combined)["watertight"] and measure(welded_combined)["watertight"]:
        print(
            "\nNote: the combined mesh becomes watertight after welding "
            "coincident vertices.  This means the components are individually\n"
            "      well-formed and the only defect is unwelded seams between "
            "groups in the .obj — i.e. an export-side artifact rather\n"
            "      than a parameter-quality issue."
        )
    print()
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] in {"-h", "--help"}:
        print(__doc__)
        return 0 if argv[1:] in (["-h"], ["--help"]) else 2

    path = Path(argv[1]).expanduser().resolve()
    if not path.is_file():
        print(f"Error: '{path}' is not an existing file.")
        return 2

    print(f"Degenerate-face threshold: triangle area < {DEGEN_THRESHOLD_MM2} mm^2")
    print()

    rc = analyze_file(path, "PRIMARY MESH")

    # Auto-discover the per-component sidecar written by
    # generate_propeller_mesh when MeshFinal was the primary output.
    sidecar_name = "propeller_mesh_components.obj"
    sidecar = path.parent / sidecar_name
    if sidecar.is_file() and sidecar.resolve() != path.resolve():
        analyze_file(
            sidecar,
            "PER-COMPONENT SIDECAR (written by the live generator alongside "
            "the primary mesh whenever MeshFinal was used as the main output)",
        )
    else:
        print(
            f"(No sidecar '{sidecar_name}' found in {path.parent}.  "
            f"This is expected if the .obj was produced before the sidecar "
            f"feature was added, or if the run took the fallback path so the "
            f"components are already present as 'g' groups inside the primary "
            f"mesh above.)"
        )

    return rc

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
