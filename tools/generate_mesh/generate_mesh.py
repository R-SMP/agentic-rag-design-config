"""Design configurator — generates propeller mesh via Grasshopper + RhinoCompute.

The module exposes two entry points with different audiences:

1. :func:`render_mesh_obj_text` — PURE helper used by both the agent
   path AND the new live-preview path (``/api/preview_mesh``, Step 6
   of the Parameters Inputs redesign).  Returns OBJ text + vertex
   count + optional components-sidecar OBJ text.  No side effects:
   does NOT write to disk, does NOT create attempt folders, does NOT
   emit agent-activity heartbeats.  Memoised via ``lru_cache(maxsize=64)``
   keyed on (sorted-tuple of params, current GH definition mtime) so
   slider wiggling in the live preview is cheap on cache hits and
   editing the .gh file automatically invalidates stale entries.

2. :func:`generate_propeller_mesh` — AGENT path: same LangChain ``@tool``
   the tool caller has always invoked.  Validates that ``output_dir``
   is an attempt folder under ``ATTEMPTS_DIR``, delegates the actual
   mesh generation to :func:`render_mesh_obj_text`, then writes the
   primary mesh + optional per-component sidecar to disk and returns
   a status string.  External behaviour identical to pre-Step-5.

Failures inside the pure helper raise :class:`MeshGenerationError`;
the agent path catches it and returns the error message as the tool's
result string (preserving the prior contract).
"""

import base64
import functools
from pathlib import Path
from typing import Annotated

import numpy as np
import DracoPy
import compute_rhino3d.Grasshopper as gh_compute
import compute_rhino3d.Util
from langchain_core.tools import tool

from agents.shared.agent_activity import tool_active
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

# Canonical 17-parameter set the GH definition expects.  Used by
# render_mesh_obj_text to validate caller-supplied dicts before
# building the RhinoCompute payload.
_CANONICAL_PARAM_NAMES = frozenset({
    "bladeCount",
    "impellerRadius",
    "impellerHeight",
    "impellerThickness",
    "innerThickness",
    "innerMaxPos",
    "innerCamber",
    "innerChord",
    "innerAngle",
    "middlePos",
    "middleChord",
    "middleAngle",
    "outerThickness",
    "outerMaxPos",
    "outerCamber",
    "outerChord",
    "outerAngle",
})

# Cache size for render_mesh_obj_text.  Slider wiggling in the live
# preview (Step 7) generates lots of identical-or-near-identical
# requests; 64 entries keeps the hot working set in memory at the cost
# of maybe a few MB of OBJ text.
_PREVIEW_CACHE_SIZE = 64


class MeshGenerationError(RuntimeError):
    """Raised by :func:`render_mesh_obj_text` when RhinoCompute fails,
    returns no usable mesh output, or all mesh parts fail to decode.

    The agent path catches this and converts it back to a status
    string for the tool's return value; the live-preview HTTP route
    converts it to a 4xx/5xx response."""


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
# Pure helper: RhinoCompute call + Draco decode, no side effects.
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=_PREVIEW_CACHE_SIZE)
def _render_mesh_obj_text_cached(
    params_tuple: tuple,
    gh_mtime_ns: int,
) -> tuple[str, int, str | None]:
    """Memoised inner implementation.  See :func:`render_mesh_obj_text`
    for the public, dict-keyed API.

    ``gh_mtime_ns`` is part of the cache key so editing the .gh file
    on disk evicts stale entries on the next call.  The value itself
    is unused inside the function — only its participation in the
    cache key matters."""
    del gh_mtime_ns   # cache-key only; not used in computation

    param_values = dict(params_tuple)

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
        raise MeshGenerationError(f"RhinoCompute error: {exc}") from exc

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
        raise MeshGenerationError(
            f"No mesh data found. Available outputs: {available}"
        )

    # Decode the primary mesh.
    mesh_text, vertex_count, decoded_count = _decode_parts_to_obj(
        mesh_parts,
        header="# Propeller mesh generated via RhinoCompute",
    )
    if decoded_count == 0:
        raise MeshGenerationError(
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


def render_mesh_obj_text(
    params: dict[str, int | float],
) -> tuple[str, int, str | None]:
    """Pure mesh-generation helper.  Used by both the agent path
    (:func:`generate_propeller_mesh`) and the live-preview HTTP route
    ``/api/preview_mesh`` (Step 6 of the Parameters Inputs redesign).

    Args:
        params: dict mapping the 17 canonical propeller parameter
            names (see :data:`_CANONICAL_PARAM_NAMES`) to int|float
            values.  Extra or missing keys raise
            :class:`MeshGenerationError` BEFORE the RhinoCompute call.

    Returns:
        ``(mesh_obj_text, vertex_count, components_obj_text)``:
            - ``mesh_obj_text``: OBJ file contents as a UTF-8 string
              (suitable to write to disk OR return as an HTTP body).
            - ``vertex_count``: total decoded vertices (diagnostic).
            - ``components_obj_text``: per-component sidecar OBJ
              (4 named groups), or ``None`` when MeshFinal was not
              the primary output (in which case the components are
              already present as ``g`` groups inside ``mesh_obj_text``,
              so no sidecar is needed).

    Raises:
        MeshGenerationError: on parameter-validation failure,
            RhinoCompute call failure, missing mesh outputs, or
            Draco decode failure on every part.

    Side effects: NONE.  Does NOT write to disk, does NOT create
    attempt folders, does NOT emit agent-activity heartbeats.  Pure.

    Memoisation: results cached via ``functools.lru_cache(maxsize=64)``
    keyed on ``(sorted-tuple of params.items(), GH-definition mtime_ns)``.
    Editing ``Propeller_Raul_V1.2.gh`` on disk evicts stale entries
    automatically.  Only successful results are cached — exceptions
    are NOT cached, so a transient RhinoCompute failure does not
    pollute the cache.
    """
    # Validate keys against the canonical 17 BEFORE touching RhinoCompute.
    keys = set(params.keys())
    missing = _CANONICAL_PARAM_NAMES - keys
    extra = keys - _CANONICAL_PARAM_NAMES
    if missing or extra:
        problems = []
        if missing:
            problems.append(f"missing keys: {sorted(missing)}")
        if extra:
            problems.append(f"unknown keys: {sorted(extra)}")
        raise MeshGenerationError(
            "Invalid parameter dict — " + "; ".join(problems)
        )

    # Cache key: sorted tuple of (key, value) so dict insertion order
    # doesn't fragment the cache.
    params_tuple = tuple(sorted(params.items()))

    # GH-file mtime: included in the cache key so editing the .gh file
    # invalidates prior entries on the next call.  If the file is
    # missing, fall through with mtime_ns=0 and let RhinoCompute fail
    # loudly inside the cached impl.
    try:
        gh_mtime_ns = GH_DEFINITION_PATH.stat().st_mtime_ns
    except OSError:
        gh_mtime_ns = 0

    return _render_mesh_obj_text_cached(params_tuple, gh_mtime_ns)


# ---------------------------------------------------------------------------
# Agent path: LangChain @tool that the tool caller invokes.
# ---------------------------------------------------------------------------

@tool
@tool_active("Propeller Configurator")
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

    Internally delegates the RhinoCompute call + Draco decode to the
    pure :func:`render_mesh_obj_text` helper (Step 5 of the
    Parameters Inputs redesign) so the same generation logic is shared
    with the live-preview HTTP route ``/api/preview_mesh``.  External
    behaviour preserved exactly — same return-string format, same disk
    writes, same sidecar emission.
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

    # Delegate to the pure helper.  Catch MeshGenerationError and
    # convert back to the tool's status-string contract.
    try:
        mesh_text, vertex_count, components_text = render_mesh_obj_text(
            param_values
        )
    except MeshGenerationError as exc:
        msg = str(exc)
        # Preserve the prior contract: error strings start with
        # "Error:" or "RhinoCompute error:" so the agent can pattern-
        # match.  The pure helper's RhinoCompute messages already
        # start with "RhinoCompute error:"; everything else gets the
        # generic "Error:" prefix.
        if msg.startswith(("Error:", "RhinoCompute error:")):
            return msg
        return f"Error: {msg}"

    # Write the primary mesh.
    output_path = out_path_dir / _MESH_FILENAME
    output_path.write_text(mesh_text, encoding="utf-8")
    file_size = output_path.stat().st_size

    # Compute the parts-used summary by re-parsing the OBJ for the
    # ``g <name>`` group lines.  Cheap and avoids threading raw mesh
    # parts through the helper's return value.
    parts_used_set: list[str] = []
    for line in mesh_text.splitlines():
        if line.startswith("g "):
            name = line[2:].strip()
            if name and name not in parts_used_set:
                parts_used_set.append(name)
    parts_used = ", ".join(parts_used_set) if parts_used_set else "MeshFinal"

    # Sidecar: when MeshFinal was the primary output, also save the
    # four named components to a separate .obj so the offline
    # diagnostic script can inspect each one individually.  Skipped
    # on the fallback path (the four components are already present
    # as ``g`` groups inside ``propeller_mesh.obj``).  Written
    # silently — the live tools never read this file.
    if components_text is not None:
        sidecar_path = out_path_dir / _COMPONENTS_FILENAME
        sidecar_path.write_text(components_text, encoding="utf-8")

    return (
        f"Mesh saved to {output_path.resolve()} ({file_size} bytes, "
        f"{vertex_count} vertices). Parts: {parts_used}."
    )
