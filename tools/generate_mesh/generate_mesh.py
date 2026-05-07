"""Design configurator — generates propeller mesh via Grasshopper + RhinoCompute."""

import base64
from pathlib import Path
from typing import Annotated

import numpy as np
import DracoPy
import compute_rhino3d.Grasshopper as gh_compute
import compute_rhino3d.Util
from langchain_core.tools import tool

from config import (
    GH_DEFINITION_PATH,
    ATTEMPTS_DIR,
    RHINO_COMPUTE_URL,
    RHINO_COMPUTE_API_KEY,
)

# Configure RhinoCompute connection
compute_rhino3d.Util.url = RHINO_COMPUTE_URL
if RHINO_COMPUTE_API_KEY:
    compute_rhino3d.Util.apiKey = RHINO_COMPUTE_API_KEY


_MESH_FILENAME = "propeller_mesh.obj"
_COMPONENTS_FILENAME = "propeller_mesh_components.obj"

# The four named per-component outputs the GH definition exposes
# alongside MeshFinal.  These are saved to a sidecar .obj file
# whenever MeshFinal was the primary mesh source, so an offline
# diagnostic (``check_mesh_components.py``) can analyse each
# component on its own even when the live mesh is the merged
# MeshFinal output.
_COMPONENT_OUTPUT_NAMES = (
    "MeshSimpleInterface",
    "MeshProfile",
    "MeshRing",
    "MeshLauncher",
)


def _validate_output_dir(raw: str) -> tuple[Path | None, str | None]:
    """Resolve and validate an attempt folder for writing the mesh.

    Returns ``(path, None)`` on success, ``(None, error_message)`` on
    failure.  The folder must already exist (created by
    ``new_attempt``), must live under ``logs/attempts/``, and must not
    already contain a ``propeller_mesh.obj``.
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
            f"{attempts_root}.  ``generate_propeller_mesh`` only "
            f"writes inside an attempt folder."
        )
    target = path / _MESH_FILENAME
    if target.exists():
        return None, (
            f"Error: '{target}' already exists.  Attempt folders are "
            f"append-only — a generated mesh cannot be overwritten.  "
            f"Create a NEW attempt via ``new_attempt`` if these "
            f"parameters need a fresh run."
        )
    return path, None


def _decode_parts_to_obj(
    mesh_parts: list[tuple[str, str]],
    header: str,
) -> tuple[str, int, int]:
    """Decode a list of ``(group_name, base64_draco)`` pairs into a single
    OBJ-format string.

    Returns ``(obj_text, total_vertex_count, decoded_part_count)``.
    Each successfully-decoded part is emitted as its own ``g <name>``
    group with face indices offset by the running vertex count, so
    multiple groups can coexist in one .obj without colliding.
    """
    obj_lines = [header]
    vertex_offset = 0
    decoded_count = 0

    for group_name, b64_data in mesh_parts:
        try:
            draco_bytes = base64.b64decode(b64_data)
            mesh = DracoPy.decode(draco_bytes)
        except Exception as exc:
            print(f"Warning: failed to decode {group_name}: {exc}")
            continue

        # DracoPy returns points as (N,3) and faces as (M,3) numpy arrays
        points = np.asarray(mesh.points).reshape(-1, 3)
        faces = np.asarray(mesh.faces).reshape(-1, 3)

        obj_lines.append(f"g {group_name}")

        for x, y, z in points:
            obj_lines.append(f"v {x} {y} {z}")

        for f1, f2, f3 in faces:
            obj_lines.append(
                f"f {f1 + vertex_offset + 1} "
                f"{f2 + vertex_offset + 1} "
                f"{f3 + vertex_offset + 1}"
            )

        vertex_offset += len(points)
        decoded_count += 1

    return "\n".join(obj_lines), vertex_offset, decoded_count


@tool
def generate_propeller_mesh(
    output_dir: Annotated[
        str,
        "Absolute path of the attempt folder where propeller_mesh.obj "
        "should be written (the same path the hand-off carries under "
        "``Current attempt:``).  Must already exist (created by "
        "``new_attempt``); must not already contain propeller_mesh.obj.",
    ],
    bladeCount: Annotated[int, "Number of blades (positive integer)"],
    impellerRadius: Annotated[float, "Outer radius of the impeller ring (mm)"],
    impellerHeight: Annotated[float, "Height of the outer ring (mm)"],
    impellerThickness: Annotated[float, "Thickness of the outer ring (mm)"],
    innerThickness: Annotated[float, "Inner-section profile thickness (% of chord)"],
    innerMaxPos: Annotated[int, "Inner-section max-thickness position (integer, tenths of chord)"],
    innerCamber: Annotated[float, "Inner-section camber (% of chord)"],
    innerChord: Annotated[float, "Inner-section chord length (mm)"],
    innerAngle: Annotated[float, "Inner-section angle of attack (degrees)"],
    middlePos: Annotated[float, "Middle-section radial position (x impellerRadius, dimensionless)"],
    middleChord: Annotated[float, "Middle-section chord length (mm)"],
    middleAngle: Annotated[float, "Middle-section angle of attack (degrees)"],
    outerThickness: Annotated[float, "Outer-section profile thickness (% of chord)"],
    outerMaxPos: Annotated[int, "Outer-section max-thickness position (integer, tenths of chord)"],
    outerCamber: Annotated[float, "Outer-section camber (% of chord)"],
    outerChord: Annotated[float, "Outer-section chord length (mm)"],
    outerAngle: Annotated[float, "Outer-section angle of attack (degrees)"],
) -> str:
    """Send the 17 propeller design parameters to the Grasshopper definition
    via RhinoCompute, retrieve the generated mesh, and save it to
    ``<output_dir>/propeller_mesh.obj``.

    ``output_dir`` MUST be the absolute path of an attempt folder
    (created earlier by ``new_attempt``).  This tool does NOT write
    anywhere else: the .obj is the only file it produces, and it
    refuses to run if that file already exists in the target folder.

    Returns the absolute path to the saved mesh file, or an error
    message.
    """

    out_path_dir, err = _validate_output_dir(output_dir)
    if err is not None:
        return err

    # Identity mapping: the @tool's keyword-argument names ARE the
    # parameter names the Grasshopper definition exposes.  The agent
    # writes parameters.json with the same camelCase keys, the
    # ``write_parameters`` / ``read_parameters`` round-trip preserves
    # them, and RhinoCompute matches them by ParamName against the
    # .gh definition's input ports — no translation layer anywhere.
    #
    # IMPORTANT: this contract requires the .gh definition's 17 input
    # parameters to be named exactly as below.  If they ever drift,
    # either the .gh side must rename to match, or this dict must
    # become a translation again.
    param_values: dict[str, int | float] = {
        "bladeCount": bladeCount,
        "impellerRadius": impellerRadius,
        "impellerHeight": impellerHeight,
        "impellerThickness": impellerThickness,
        "innerThickness": innerThickness,
        "innerMaxPos": innerMaxPos,
        "innerCamber": innerCamber,
        "innerChord": innerChord,
        "innerAngle": innerAngle,
        "middlePos": middlePos,
        "middleChord": middleChord,
        "middleAngle": middleAngle,
        "outerThickness": outerThickness,
        "outerMaxPos": outerMaxPos,
        "outerCamber": outerCamber,
        "outerChord": outerChord,
        "outerAngle": outerAngle,
    }

    # Build Grasshopper DataTree inputs.
    # Note: the library's DataTree.Append uses '{}'.format(idx) which
    # consumes the curly braces, producing key "0" instead of "{0}".
    # RhinoCompute expects "{0}" path keys, so we build the dicts manually.
    input_trees = []
    for param_name, value in param_values.items():
        if isinstance(value, int):
            dtype = "System.Int32"
        else:
            dtype = "System.Double"
        tree = type("Tree", (), {"data": {
            "ParamName": param_name,
            "InnerTree": {
                "{0}": [{"type": dtype, "data": str(value)}]
            },
        }})()
        input_trees.append(tree)

    # Pass the .gh file path directly — the library reads and encodes it
    try:
        output = gh_compute.EvaluateDefinition(str(GH_DEFINITION_PATH), input_trees)
    except Exception as exc:
        return f"RhinoCompute error: {exc}"

    # The response may be a dict with a "values" key, or a list directly
    if isinstance(output, dict):
        values = output.get("values", [])
    else:
        values = output

    # Helper: extract base64 Draco strings from an output item's InnerTree
    def _extract_draco_strings(item: dict) -> list[str]:
        strings: list[str] = []
        for bk in sorted(item.get("InnerTree", {}).keys()):
            for leaf in item["InnerTree"][bk]:
                data = leaf.get("data", "")
                if isinstance(data, str):
                    data = data.strip().strip('"')
                if data:
                    strings.append(data)
        return strings

    # Try MeshFinal first; fall back to individual mesh parts
    mesh_parts: list[tuple[str, str]] = []  # (group_name, b64_draco)

    for item in values:
        pname = item.get("ParamName", "")
        if "MeshFinal" in pname:
            for s in _extract_draco_strings(item):
                mesh_parts.append(("MeshFinal", s))
            break

    mesh_final_used = bool(mesh_parts)

    if not mesh_parts:
        # MeshFinal was empty — combine the individual component meshes
        for item in values:
            pname = item.get("ParamName", "")
            if pname in _COMPONENT_OUTPUT_NAMES:
                for s in _extract_draco_strings(item):
                    mesh_parts.append((pname, s))

    if not mesh_parts:
        available = [item.get("ParamName", "?") for item in values]
        return f"Error: No mesh data found. Available outputs: {available}"

    # Decode the main mesh into the live ``propeller_mesh.obj``
    mesh_text, vertex_offset, decoded_count = _decode_parts_to_obj(
        mesh_parts,
        header="# Propeller mesh generated via RhinoCompute",
    )
    if decoded_count == 0:
        return "Error: All mesh parts failed to decode from Draco format."

    output_path = out_path_dir / _MESH_FILENAME
    output_path.write_text(mesh_text, encoding="utf-8")
    file_size = output_path.stat().st_size
    parts_used = ", ".join(dict.fromkeys(name for name, _ in mesh_parts))

    # Sidecar: when MeshFinal was the primary output, also save the
    # four named components to a separate .obj so the offline
    # diagnostic script can inspect each one individually.  Skipped
    # on the fallback path (the four components are already present
    # as ``g`` groups inside ``propeller_mesh.obj``).  Written
    # silently — the live tools never read this file.
    if mesh_final_used:
        component_parts: list[tuple[str, str]] = []
        for item in values:
            pname = item.get("ParamName", "")
            if pname in _COMPONENT_OUTPUT_NAMES:
                for s in _extract_draco_strings(item):
                    component_parts.append((pname, s))
        if component_parts:
            sidecar_text, _, sidecar_count = _decode_parts_to_obj(
                component_parts,
                header="# Per-component meshes (companion to propeller_mesh.obj)",
            )
            if sidecar_count > 0:
                sidecar_path = out_path_dir / _COMPONENTS_FILENAME
                sidecar_path.write_text(sidecar_text, encoding="utf-8")

    return (
        f"Mesh saved to {output_path.resolve()} ({file_size} bytes, "
        f"{vertex_offset} vertices). Parts: {parts_used}."
    )
