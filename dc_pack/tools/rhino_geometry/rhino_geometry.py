"""The RhinoCompute geometry tool: the propeller built by RhinoCompute from
the Grasshopper definition beside this module -- the exact geometry.

Needs the RhinoCompute server (``RHINO_COMPUTE_URL`` /
``RHINO_COMPUTE_API_KEY`` in ``config.py``).  The ring height is not a
parameter: it is derived (``ring_height.fitted_ring_height``, a port of
``web/feg``) and fed to the definition's ``impellerHeight`` input, so the
ring matches the FEG geometry.  When the definition's merged ``MeshFinal``
output is used, the four components also come back as a separate file
(``propeller_mesh_components.obj``) for offline diagnostics.

:func:`make_model` is memoised on the parameters and the definition's mtime,
so editing the ``.gh`` file evicts stale entries.  The engine calls it
(``engine/pack_tools.make_model``: the generator's geometry tool, the web
app's Download buttons) with parameters it has already checked.
"""

import base64
import functools
from pathlib import Path

import numpy as np
import DracoPy
import compute_rhino3d.Grasshopper as gh_compute
import compute_rhino3d.Util
from config import (
    RHINO_COMPUTE_URL,
    RHINO_COMPUTE_API_KEY,
)
from engine.tooling import GeometryResult, ToolError

from .ring_height import fitted_ring_height

# The Grasshopper definition RhinoCompute runs, kept beside this module.
GH_DEFINITION_PATH = Path(__file__).resolve().parent / "Propeller_Raul_V1.2.gh"

# Configure RhinoCompute connection
compute_rhino3d.Util.url = RHINO_COMPUTE_URL
if RHINO_COMPUTE_API_KEY:
    compute_rhino3d.Util.apiKey = RHINO_COMPUTE_API_KEY

# The per-component companion file, written beside the model.
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

# Slider wiggling on the Parameters page and repeated downloads ask for the
# same parameters again; 64 entries keep the hot working set in memory at
# the cost of a few MB of OBJ text.
_CACHE_SIZE = 64


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


def _extract_draco_strings(item: dict) -> list[str]:
    """Extract base64 Draco strings from a RhinoCompute output item's
    InnerTree.  Strips surrounding quotes/whitespace from each leaf's
    ``data`` field and skips empty leaves."""
    strings: list[str] = []
    for bk in sorted(item.get("InnerTree", {}).keys()):
        for leaf in item["InnerTree"][bk]:
            data = leaf.get("data", "")
            if isinstance(data, str):
                data = data.strip().strip('"')
            if data:
                strings.append(data)
    return strings


# ---------------------------------------------------------------------------
# RhinoCompute call + Draco decode, no side effects.
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=_CACHE_SIZE)
def _make_cached(
    params_tuple: tuple,
    gh_mtime_ns: int,
) -> tuple[str, int, str | None]:
    """Memoised implementation of :func:`make_model`: ``(mesh_obj_text,
    vertex_count, components_obj_text)``.

    ``gh_mtime_ns`` is part of the cache key so editing the .gh file
    on disk evicts stale entries on the next call.  The value itself
    is unused inside the function — only its participation in the
    cache key matters."""
    del gh_mtime_ns   # cache-key only; not used in computation

    param_values = dict(params_tuple)
    # Ring height is DERIVED, not an input: inject the fitted height into the
    # .gh's ``impellerHeight`` port so the RhinoCompute geometry's ring
    # matches the FEG 3D preview exactly.  ring_height.fitted_ring_height is
    # a port of web/feg verified bit-for-bit by smoke_test_ring_height.py.
    param_values["impellerHeight"] = fitted_ring_height(param_values)

    # Build Grasshopper DataTree inputs.
    # Note: the library's DataTree.Append uses '{}'.format(idx) which
    # consumes the curly braces, producing key "0" instead of "{0}".
    # RhinoCompute expects "{0}" path keys, so we build the dicts
    # manually via an anonymous-class wrapper that exposes a ``data``
    # attribute (the shape EvaluateDefinition expects).
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

    # Pass the .gh file path directly — the library reads and encodes it.
    try:
        output = gh_compute.EvaluateDefinition(
            str(GH_DEFINITION_PATH), input_trees
        )
    except Exception as exc:
        raise ToolError(f"RhinoCompute error: {exc}") from exc

    # The response may be a dict with a "values" key, or a list directly.
    if isinstance(output, dict):
        values = output.get("values", [])
    else:
        values = output

    # Try MeshFinal first; fall back to individual mesh parts.
    mesh_parts: list[tuple[str, str]] = []   # (group_name, b64_draco)
    for item in values:
        pname = item.get("ParamName", "")
        if "MeshFinal" in pname:
            for s in _extract_draco_strings(item):
                mesh_parts.append(("MeshFinal", s))
            break

    mesh_final_used = bool(mesh_parts)

    if not mesh_parts:
        # MeshFinal was empty — combine the individual component meshes.
        for item in values:
            pname = item.get("ParamName", "")
            if pname in _COMPONENT_OUTPUT_NAMES:
                for s in _extract_draco_strings(item):
                    mesh_parts.append((pname, s))

    if not mesh_parts:
        available = [item.get("ParamName", "?") for item in values]
        raise ToolError(
            f"No mesh data found. Available outputs: {available}"
        )

    # Decode the primary mesh.
    mesh_text, vertex_count, decoded_count = _decode_parts_to_obj(
        mesh_parts,
        header="# Propeller mesh generated via RhinoCompute",
    )
    if decoded_count == 0:
        raise ToolError(
            "All mesh parts failed to decode from Draco format."
        )

    # Components sidecar: only meaningful when MeshFinal was the
    # primary output (otherwise the components are already present
    # as ``g`` groups inside the main mesh OBJ).  None signals the
    # caller "no sidecar to write".
    components_text: str | None = None
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
                components_text = sidecar_text

    return mesh_text, vertex_count, components_text


def make_model(params: dict) -> GeometryResult:
    """The propeller's model from *params*, via RhinoCompute.  Raises
    ToolError (``RhinoCompute error: …`` when the call fails)."""
    try:
        gh_mtime_ns = GH_DEFINITION_PATH.stat().st_mtime_ns
    except OSError:
        gh_mtime_ns = 0
    text, vertex_count, components = _make_cached(tuple(sorted(params.items())), gh_mtime_ns)
    return GeometryResult(
        model=text, vertex_count=vertex_count,
        extra_files={_COMPONENTS_FILENAME: components} if components is not None else {})
