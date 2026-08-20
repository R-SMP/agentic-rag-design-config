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

2. :func:`generate_and_render_propeller` — AGENT path: the LangChain
   ``@tool`` the Tool Caller invokes.  Validates that ``output_dir`` is
   an attempt folder under ``ATTEMPTS_DIR``, builds the mesh (selected
   geometry backend + bidirectional fallback), writes the primary mesh +
   optional per-component sidecar to disk, and THEN runs the render+check
   step (injected by ``tools/__init__`` via :func:`set_render_and_check_fn`)
   as its built-in final phase — returning one combined status string.
   A pre-existing mesh is reused in place (append-only); a geometry
   failure skips the render step.

Failures inside the pure helper raise :class:`MeshGenerationError`;
the agent path catches it and returns the error message as the tool's
result string (preserving the prior contract).
"""

import base64
import functools
import json
import logging
import math
import subprocess
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
from tools.generate_mesh.ring_height import fitted_ring_height

# Configure RhinoCompute connection
compute_rhino3d.Util.url = RHINO_COMPUTE_URL
if RHINO_COMPUTE_API_KEY:
    compute_rhino3d.Util.apiKey = RHINO_COMPUTE_API_KEY

logger = logging.getLogger("propeller_agent")


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
_FEG_SOURCE_DIR = Path(__file__).resolve().parents[2] / "web" / "feg"


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


# ---------------------------------------------------------------------------
# Render backend injection (agent path only).
# ---------------------------------------------------------------------------
# ``generate_and_render_propeller`` runs the render+check as its built-in
# final step.  The actual render core (trimesh or pyvista) is chosen at
# session start by ``tools/__init__`` (via ``set_render_library``) and injected
# here, so this module needs no import of the render backends — which would
# pull trimesh / pyrender / pyvista into the pure live-preview path that only
# needs geometry.  ``None`` until wired; ``tools/__init__`` wires a default at
# import, so in the agent path it is always set by the time the tool runs.
_render_and_check_fn = None


def set_render_and_check_fn(fn) -> None:
    """Inject the render+check core that ``generate_and_render_propeller``
    calls after a successful geometry build.  Called by ``tools/__init__``,
    which owns the trimesh-vs-pyvista selection."""
    global _render_and_check_fn
    _render_and_check_fn = fn


class MeshGenerationError(RuntimeError):
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
# produced that mesh, so a LATER write_parameters cannot label it with numbers
# it did not come from — the same corruption F75 blocks in the params-first
# order, arriving by the other door.
MESH_PROVENANCE_FILE = "mesh_params.json"


def _param_mismatches(out_dir, param_values, record_name="parameters.json"):
    """Compare *param_values* against ``<out_dir>/<record_name>``.

    Returns ``None`` when there is NOTHING TO COMPARE — no parameters.json,
    unreadable, not a JSON object, a non-numeric value, or one of the
    canonical 16 keys missing.  An absent or incomplete record is NOT a
    mismatch: legitimate callers reach this tool before any parameters.json
    exists (the Orchestrator's fallback folder, the 3-agent Designer's call
    ordering, smoke_test_generate_mesh), and F75 is about a folder whose
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

    Public because the three ``write_parameters`` handlers call it before
    writing a record into a folder that may already hold a mesh.

    Returns ``None`` when there is NOTHING TO COMPARE — no sidecar, which is
    every attempt folder built before F75b — so this can never refuse a
    legacy folder.  ``[]`` when the mesh was built from these very values,
    else a list of readable differences.
    """
    return _param_mismatches(Path(attempt_dir), param_values,
                             record_name=MESH_PROVENANCE_FILE)


def _read_param_record(params_file):
    """Read an attempt's ``parameters.json`` into the 16-key kwargs dict.

    This replaced sixteen tool arguments.  The model used to retype every
    number into the call, which is the entire reason F75 and F75b exist; the
    values now come FROM the record, so a mesh cannot disagree with it.

    Returns ``(values, None)`` on success, ``(None, "Error: ...")`` otherwise.
    Every error is written for the AGENT to act on, not for a log.

    A legacy ``impellerHeight`` key is ignored, mirroring _param_mismatches:
    pre-dda1560 folders still carry the 17th key and the backends derive it.
    """
    if not params_file.is_file():
        return None, (
            f"Error: no parameters.json at {params_file}.  An attempt's mesh "
            f"is built FROM its parameter record, so the record must exist "
            f"first — call ``write_parameters`` for this attempt (or point "
            f"this call at the attempt that already has one)."
        )
    try:
        raw_record = json.loads(params_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, (
            f"Error: could not read {params_file}: {exc}.  The file must be "
            f"a JSON object mapping each parameter name to a number."
        )
    if not isinstance(raw_record, dict):
        return None, (
            f"Error: {params_file} is not a JSON object.  It must map each "
            f"parameter name to a number."
        )

    values = {}
    missing, non_numeric = [], []
    for name in _CANONICAL_PARAM_NAMES:
        if name not in raw_record:
            missing.append(name)
            continue
        v = raw_record[name]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            non_numeric.append(name)
            continue
        values[name] = v
    if missing or non_numeric:
        parts = [f"Error: {params_file} is not a complete parameter record."]
        if missing:
            parts.append(f"Missing keys: {sorted(missing)}")
        if non_numeric:
            parts.append(f"Non-numeric values: {sorted(non_numeric)}")
        parts.append(
            "No mesh was built.  Fix the record with ``write_parameters`` on "
            "a NEW attempt rather than editing this one — attempt folders are "
            "append-only."
        )
        return None, "  ".join(parts)
    return values, None


def _validate_output_dir(raw: str) -> tuple[Path | None, str | None]:
    """Resolve and validate an attempt folder for writing the mesh.

    Returns ``(path, None)`` on success, ``(None, error_message)`` on
    failure.  The folder must already exist (created by ``new_attempt``)
    and live under ``attempts/``.  A pre-existing
    ``propeller_mesh.obj`` is NOT rejected — the merged tool reuses it in
    place (append-only; never overwritten) and proceeds to the render
    step.
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
            f"{attempts_root}.  ``generate_and_render_propeller`` only "
            f"writes inside an attempt folder."
        )
    # A pre-existing propeller_mesh.obj is NOT an error: the merged
    # generate_and_render_propeller REUSES it in place (append-only —
    # never overwritten) and proceeds to the render step, so a retry
    # after a render hiccup needs no new attempt.
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


# ---------------------------------------------------------------------------
# Agent path: LangChain @tool that the tool caller invokes.
# ---------------------------------------------------------------------------

@tool
@tool_active("Propeller Configurator")
def generate_and_render_propeller(
    parameters_path: Annotated[
        str,
        "Absolute path of the attempt's ``parameters.json`` — the same path "
        "the hand-off carries under ``Parameters file:``.  The mesh and the "
        "render PNGs are written into that file's OWN attempt folder, so the "
        "geometry can never be built from one attempt's numbers into another "
        "attempt's folder.",
    ],
) -> str:
    """Generate the propeller 3D geometry from an attempt's own
    ``parameters.json``, save it to that attempt's ``propeller_mesh.obj``,
    THEN render it (three views —
    isometric, top, side) and run mesh quality checks, all in one call.  The
    render step is the automatic next step after a successful geometry build
    and is skipped only if the geometry generation itself fails.  (The
    outer-ring height is NOT a parameter — it is derived from the outer blade
    section and injected automatically so the mesh matches the 3D preview.)

    Geometry backend: chosen by the ``GEOMETRY_BACKEND`` workflow setting —
    either RhinoCompute + the Grasshopper definition (the exact geometry) or a
    headless-Node FEG export of the same ``web/feg`` modules the 3D preview
    uses (a fast, local, visually-faithful sub-mm approximation).  If the
    selected backend fails, the tool AUTOMATICALLY falls back to the other, so
    a RhinoCompute outage no longer blocks a run.  The return string names the
    backend actually used (and flags a fallback).  Regardless of which backend
    built the working mesh here, the user's downloadable deliverable is
    regenerated via RhinoCompute.

    ``parameters_path`` MUST be the absolute path of an attempt's
    ``parameters.json`` (written earlier by ``write_parameters``).  You do NOT
    pass the values themselves and you do NOT pass an output directory: the
    tool reads the record and writes into that record's own folder, so a mesh
    can never be built from one attempt's numbers into another attempt's
    folder.  If that folder already contains ``propeller_mesh.obj`` the
    existing mesh is REUSED in place (append-only — never overwritten) and the
    tool proceeds straight to the render step.

    Returns a combined status string: the geometry summary (saved/reused mesh
    path, vertex count, parts, backend) followed by the render+check report
    (the three saved render paths plus any quality warnings).  On geometry
    failure (both backends) it returns an ``Error:`` / ``RhinoCompute error:``
    / ``FEG error:`` message and does NOT render.
    """
    params_file = Path(parameters_path)
    # _validate_output_dir keeps its ONE-argument contract deliberately:
    # smoke_test_param_rename patches it with a one-arg lambda and
    # smoke_test_attempt_coherence asserts the arity, so the folder is derived
    # here rather than by giving that helper a second parameter.
    out_path_dir, err = _validate_output_dir(str(params_file.parent))
    if err is not None:
        return err

    param_values, err = _read_param_record(params_file)
    if err is not None:
        return err

    output_path = out_path_dir / _MESH_FILENAME

    # Identity mapping: the KEYS in parameters.json ARE the parameter names
    # the Grasshopper definition exposes.  ``write_parameters`` writes those
    # camelCase keys, ``_read_param_record`` reads them back unchanged, and
    # RhinoCompute matches them by ParamName against the .gh definition's
    # input ports — no translation layer anywhere.
    #
    # IMPORTANT: this contract requires the .gh definition's input parameters
    # to be named exactly as in _CANONICAL_PARAM_NAMES.  The .gh's 17th port,
    # ``impellerHeight``, is NOT sent from here — render_mesh_obj_text derives
    # it (the ring auto-fits the outer section) and injects it.

    # --- Geometry: reuse an existing mesh in place, else build it. ---
    if output_path.is_file():
        # Append-only: never overwrite.  The mesh was built from THIS
        # FOLDER's parameters, which are now the only numbers this tool can
        # be given, so a reuse can no longer answer a different set by
        # accident.  This is the path every DCOI re-render takes.
        geometry_summary = (
            f"Reused existing mesh at {output_path.resolve()} "
            f"({output_path.stat().st_size} bytes; geometry not "
            f"regenerated)."
        )
    else:
        # Delegate to the backend dispatcher (selected backend +
        # bidirectional fallback).  On MeshGenerationError the geometry
        # failed on BOTH backends — return the error and do NOT render.
        try:
            mesh_text, vertex_count, components_text, backend_used = (
                render_agent_mesh_obj_text(param_values)
            )
        except MeshGenerationError as exc:
            msg = str(exc)
            # Preserve the prior contract: error strings start with "Error:",
            # "RhinoCompute error:" or "FEG error:" so the agent can pattern-
            # match; a combined both-backends-failed message and everything
            # else gets the generic "Error:" prefix.
            if msg.startswith(("Error:", "RhinoCompute error:", "FEG error:")):
                return msg
            return f"Error: {msg}"

        # Write the primary mesh.
        output_path.write_text(mesh_text, encoding="utf-8")

        # F75b: record what produced it.  Best-effort on purpose — a sidecar
        # we cannot write must never fail a mesh that built fine; its absence
        # only means a later write_parameters has nothing to check against,
        # which is exactly the pre-F75b behaviour.
        try:
            (out_path_dir / MESH_PROVENANCE_FILE).write_text(
                json.dumps(param_values, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(
                "[F75b] mesh provenance sidecar not written to %s: %s",
                out_path_dir, exc)
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

        geometry_summary = (
            f"Mesh saved to {output_path.resolve()} ({file_size} bytes, "
            f"{vertex_count} vertices). Parts: {parts_used}. "
            f"Geometry backend: {_backend_label(backend_used)}."
        )

    # --- Renders: the always-done next step after a good geometry build. ---
    # The render+check core (trimesh or pyvista) is injected by
    # ``tools/__init__``.  A render failure never masks a good mesh — the
    # mesh is already on disk and the report notes the render problem.
    if _render_and_check_fn is None:
        return (
            geometry_summary
            + "\n\n(Render step unavailable — no render backend wired.)"
        )
    try:
        render_report = _render_and_check_fn(
            str(output_path), str(out_path_dir)
        )
    except Exception as exc:  # noqa: BLE001 — a render error must not lose the mesh
        render_report = f"Render step failed: {exc}"

    return f"{geometry_summary}\n\n{render_report}"
