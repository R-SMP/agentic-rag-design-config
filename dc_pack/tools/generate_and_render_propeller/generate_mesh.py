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

2. :func:`render_agent_mesh_obj_text` — AGENT path: the selected
   geometry backend with a bidirectional fallback.  The tool around it is
   ``generate_and_render_propeller`` (MAS-blueprint P3c): the engine
   (``engine/pack_tools.run_generator``) checks the attempt folder, reads
   the parameter record and reuses an existing mesh; this folder's
   ``tool.py`` builds the mesh with this helper and renders it.

Failures raise :class:`MeshGenerationError` -- a ``ToolError``, so the
engine returns its message as the tool's result string (preserving the
prior contract).
"""

import base64
import functools
import json
import logging
import math
import subprocess
from pathlib import Path

import numpy as np
import DracoPy
import compute_rhino3d.Grasshopper as gh_compute
import compute_rhino3d.Util
from config import (
    RHINO_COMPUTE_URL,
    RHINO_COMPUTE_API_KEY,
)
from engine.tooling import ToolError

from .ring_height import fitted_ring_height

# The Grasshopper definition RhinoCompute runs, kept beside this module.
GH_DEFINITION_PATH = Path(__file__).resolve().parent / "Propeller_Raul_V1.2.gh"

# Configure RhinoCompute connection
compute_rhino3d.Util.url = RHINO_COMPUTE_URL
if RHINO_COMPUTE_API_KEY:
    compute_rhino3d.Util.apiKey = RHINO_COMPUTE_API_KEY

logger = logging.getLogger("mas_agent")


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

# Canonical 16-parameter INPUT set.  The ring height is NOT an input: it
# is DERIVED (ring_height.fitted_ring_height) and injected as the .gh's
# ``impellerHeight`` port inside _render_mesh_obj_text_cached, so the
# RhinoCompute geometry's ring matches the FEG 3D preview.  Used by
# render_mesh_obj_text to validate caller-supplied dicts.
_CANONICAL_PARAM_NAMES = frozenset({
    "bladeCount",
    "impellerRadius",
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


# ---------------------------------------------------------------------------
# Geometry backend selection (agent path only).
# ---------------------------------------------------------------------------
# ``generate_and_render_propeller`` can build the mesh two ways:
#   "rhino"  RhinoCompute + Grasshopper (the .gh definition) — the source of
#            truth for the downloadable deliverable, but depends on an external
#            server that can be unreachable.
#   "feg"    headless Node running the SAME web/feg/* modules the browser 3D
#            preview uses (feg_export.mjs) — local, fast, no external server; a
#            visually-faithful sub-mm approximation of the .gh.
# Whichever is selected, the OTHER is used as an automatic fallback when the
# first fails (bidirectional).  The live-preview / RCG-download helper
# ``render_mesh_obj_text`` ALWAYS uses RhinoCompute, independent of this.
GEOMETRY_BACKENDS: tuple[str, ...] = ("feg", "rhino")
_geometry_backend: str = "feg"

# Headless FEG exporter + its source tree (used for cache invalidation).
_FEG_EXPORTER = Path(__file__).resolve().parent / "feg_export.mjs"
_FEG_SOURCE_DIR = Path(__file__).resolve().parents[3] / "web" / "feg"


def set_geometry_backend(backend: str) -> None:
    """Pick the agent-path geometry backend ("feg" or "rhino").

    Called by loader.py at session build (mirrors ``set_render_library``).
    Raises on an unknown choice so a typo fails loudly at startup.
    """
    global _geometry_backend
    if backend not in GEOMETRY_BACKENDS:
        raise ValueError(
            f"Unknown geometry backend {backend!r}; expected one of "
            f"{GEOMETRY_BACKENDS}."
        )
    _geometry_backend = backend


def get_geometry_backend() -> str:
    """Return the currently selected agent-path geometry backend."""
    return _geometry_backend


class MeshGenerationError(ToolError, RuntimeError):
    """Raised by :func:`render_mesh_obj_text` when RhinoCompute fails,
    returns no usable mesh output, or all mesh parts fail to decode.

    The agent path catches this and converts it back to a status
    string for the tool's return value; the live-preview HTTP route
    converts it to a 4xx/5xx response."""


# F75: attempt-folder coherence.
# DORMANT since the tool began reading parameters.json itself: the values it
# builds from now COME from the record, so they cannot disagree with it and
# this comparison is unreachable via the agent path.  Kept deliberately — it
# still guards any future caller that reintroduces value-passing, and deleting
# a working guard in the same change that removes its trigger is how a safety
# net gets lost twice.  ``mesh_provenance_mismatches`` below is likewise quiet
# now that a mesh cannot precede its record.
# --- F75: attempt-folder coherence -----------------------------------------
# A folder's mesh must come from that folder's own parameters.json.  The
# tolerance below only absorbs float repr / round-trip noise: parameters.json
# is written from the same LLM-authored numbers the tool call carries, so any
# REAL difference is orders of magnitude larger.
_PARAM_REL_TOL = 1e-9
_PARAM_ABS_TOL = 1e-12

# The three integer-typed parameters (declared ``Annotated[int, ...]`` on the
# tool) — compared exactly.  The other 13 are floats.
_INT_PARAM_NAMES = frozenset({"bladeCount", "innerMaxPos", "outerMaxPos"})


# F75b: the mesh-first order.  A mesh may legitimately be built into a folder
# that has no parameters.json yet (the Orchestrator's fallback folder, the
# 3-agent Designer's call ordering).  This sidecar records exactly what
# produced that mesh, so a LATER parameter write cannot label it with numbers
# it did not come from — the same corruption F75 blocks in the params-first
# order, arriving by the other door.
MESH_PROVENANCE_FILE = "mesh_params.json"


def _param_mismatches(out_dir, param_values, record_name="parameters.json"):
    """Compare *param_values* against ``<out_dir>/<record_name>``.

    Returns ``None`` when there is NOTHING TO COMPARE — no parameters.json,
    unreadable, not a JSON object, a non-numeric value, or one of the
    canonical 16 keys missing.  An absent or incomplete record is NOT a
    mismatch: legitimate callers reach this tool before any parameters.json
    exists (e.g. the Orchestrator's fallback folder, or a script that
    generates directly), and F75 is about a folder whose
    record DISAGREES with its mesh — which presupposes a complete record.

    Returns ``[]`` when all 16 agree, else a list of readable differences.

    A legacy ``impellerHeight`` key is ignored, mirroring _normalize_params:
    pre-dda1560 folders still carry the 17th key, and that check runs inside
    the backends, i.e. after this point.
    """
    params_path = out_dir / record_name
    if not params_path.is_file():
        return None
    try:
        on_disk = json.loads(params_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(
            "generate_mesh: %s unreadable or not valid JSON (%s) — "
            "parameter coherence NOT checked.", params_path, exc,
        )
        return None
    if not isinstance(on_disk, dict):
        return None

    mismatches = []
    for name in sorted(_CANONICAL_PARAM_NAMES):
        recorded = on_disk.get(name)
        if isinstance(recorded, bool) or not isinstance(recorded, (int, float)):
            logger.warning(
                "generate_mesh: %s has no usable '%s' value — parameter "
                "coherence NOT checked.", params_path, name,
            )
            return None
        passed = param_values[name]
        if isinstance(passed, bool) or not isinstance(passed, (int, float)):
            # Defensive: args_schema should have coerced this already.  If it
            # did not, degrade to "proceed" — today's behaviour — never to a
            # false refusal.
            logger.warning(
                "generate_mesh: passed '%s' is %r, not a number — parameter "
                "coherence NOT checked.", name, passed,
            )
            return None
        if name in _INT_PARAM_NAMES:
            same = passed == recorded
        else:
            same = math.isclose(
                float(passed), float(recorded),
                rel_tol=_PARAM_REL_TOL, abs_tol=_PARAM_ABS_TOL,
            )
        if not same:
            mismatches.append(
                f"{name}: you passed {passed}, the folder holds {recorded}"
            )
    return mismatches


def mesh_provenance_mismatches(attempt_dir, param_values):
    """Compare *param_values* against the mesh provenance sidecar.

    Public because the parameter-writing handlers call it before
    writing a record into a folder that may already hold a mesh.

    Returns ``None`` when there is NOTHING TO COMPARE — no sidecar, which is
    every attempt folder built before F75b — so this can never refuse a
    legacy folder.  ``[]`` when the mesh was built from these very values,
    else a list of readable differences.
    """
    return _param_mismatches(Path(attempt_dir), param_values,
                             record_name=MESH_PROVENANCE_FILE)


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


def _normalize_params(
    params: dict[str, int | float],
) -> dict[str, int | float]:
    """Drop a legacy ``impellerHeight`` key (ring height is derived now) and
    validate the canonical 16 keys.  Shared by both geometry backends.
    Raises :class:`MeshGenerationError` on a missing/unknown key."""
    if "impellerHeight" in params:
        logger.warning(
            "generate_mesh: ignoring legacy 'impellerHeight' key "
            "(ring height is now derived from the outer section)."
        )
        params = {k: v for k, v in params.items() if k != "impellerHeight"}

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
    return params


def render_mesh_obj_text(
    params: dict[str, int | float],
) -> tuple[str, int, str | None]:
    """Pure mesh-generation helper.  Used by both the agent path
    (:func:`generate_and_render_propeller`) and the live-preview HTTP route
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
    # Normalise + validate (drops a legacy impellerHeight key, checks the 16)
    # BEFORE touching RhinoCompute.
    params = _normalize_params(params)

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
# FEG geometry backend: headless Node running web/feg/* (feg_export.mjs).
# ---------------------------------------------------------------------------

def _feg_sources_mtime_ns() -> int:
    """Newest mtime across the FEG exporter + web/feg/*.js — part of the FEG
    cache key so editing the geometry code evicts stale entries."""
    paths = [_FEG_EXPORTER, *_FEG_SOURCE_DIR.glob("*.js")]
    try:
        return max((p.stat().st_mtime_ns for p in paths), default=0)
    except OSError:
        return 0


@functools.lru_cache(maxsize=_PREVIEW_CACHE_SIZE)
def _feg_render_mesh_obj_text_cached(
    params_tuple: tuple,
    feg_mtime_ns: int,
) -> tuple[str, int, None]:
    """Memoised FEG mesh generation.  See :func:`_feg_render_mesh_obj_text`.

    ``feg_mtime_ns`` is cache-key only (evicts on a web/feg edit)."""
    del feg_mtime_ns
    params = dict(params_tuple)
    try:
        proc = subprocess.run(
            ["node", str(_FEG_EXPORTER), json.dumps(params)],
            capture_output=True, text=True, timeout=120,
        )
    except FileNotFoundError as exc:
        raise MeshGenerationError(
            f"FEG error: Node runtime not found ({exc})."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise MeshGenerationError(
            f"FEG error: exporter timed out ({exc})."
        ) from exc
    except Exception as exc:  # noqa: BLE001 — surface any launch failure
        raise MeshGenerationError(f"FEG error: {exc}") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[-500:]
        raise MeshGenerationError(
            f"FEG error: exporter exited {proc.returncode}: {detail}"
        )

    mesh_text = proc.stdout
    vertex_count = sum(
        1 for ln in mesh_text.splitlines() if ln.startswith("v ")
    )
    if vertex_count == 0:
        raise MeshGenerationError("FEG error: exporter produced no vertices.")
    # FEG bakes everything into a single mesh — no per-component sidecar.
    return mesh_text, vertex_count, None


def _feg_render_mesh_obj_text(
    params: dict[str, int | float],
) -> tuple[str, int, str | None]:
    """FEG counterpart of :func:`render_mesh_obj_text`: build the mesh via the
    headless-Node FEG exporter (web/feg/*), returning
    ``(obj_text, vertex_count, None)``.  Pure; memoised; raises
    :class:`MeshGenerationError` (message prefixed ``FEG error:``)."""
    params = _normalize_params(params)
    params_tuple = tuple(sorted(params.items()))
    return _feg_render_mesh_obj_text_cached(
        params_tuple, _feg_sources_mtime_ns()
    )


# ---------------------------------------------------------------------------
# Agent-path dispatcher: selected backend + bidirectional fallback.
# ---------------------------------------------------------------------------

def render_agent_mesh_obj_text(
    params: dict[str, int | float],
) -> tuple[str, int, str | None, str]:
    """Generate the mesh for the AGENT path, honouring the selected geometry
    backend and falling back to the OTHER backend on failure.

    Returns ``(obj_text, vertex_count, components_obj_text, backend_used)``
    where ``backend_used`` is "feg" or "rhino".  Raises
    :class:`MeshGenerationError` (combining both errors) only if BOTH
    backends fail.
    """
    primary = _geometry_backend
    order = [primary] + [b for b in GEOMETRY_BACKENDS if b != primary]
    errors: list[str] = []
    for backend in order:
        try:
            if backend == "feg":
                text, vcount, comps = _feg_render_mesh_obj_text(params)
            else:
                text, vcount, comps = render_mesh_obj_text(params)
        except MeshGenerationError as exc:
            logger.warning("Geometry backend %r failed: %s", backend, exc)
            errors.append(f"{backend}: {exc}")
            continue
        if errors:
            logger.warning(
                "Geometry backend %r failed; used %r as fallback.",
                primary, backend,
            )
        return text, vcount, comps, backend
    raise MeshGenerationError(
        "All geometry backends failed — " + " | ".join(errors)
    )


def _backend_label(backend_used: str) -> str:
    """Human label for the tool result, noting when a fallback was used."""
    names = {"feg": "FEG", "rhino": "RhinoCompute"}
    used = names.get(backend_used, backend_used)
    if backend_used != _geometry_backend:
        other = names.get(_geometry_backend, _geometry_backend)
        return f"{used} (fallback — {other} unavailable)"
    return used
