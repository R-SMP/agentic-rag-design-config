"""``generate_and_render_propeller`` -- the propeller generator's two steps.

The engine (``engine/pack_tools.run_generator``) owns everything around
them: it checks that ``parameters_path`` lies in an attempt folder, reads and
validates the record, reuses a ``propeller_mesh.obj`` already in the folder
(append-only: never overwritten) and joins the two results into the text
the agent gets.  This file only:

* :func:`build` -- generates the mesh with the selected geometry backend
  (FEG or RhinoCompute, falling back to the other) and writes it, its
  per-component sidecar and the provenance record;
* :func:`render` -- renders the three views and, when the ``mesh_checks``
  setting is on, runs the quality checks, with the render core chosen by
  the ``render_library`` setting.

Both read this tool's settings (``tool.yaml``) from ``inp.settings``.
"""

from __future__ import annotations

import json
import logging

from engine.tooling import BuildResult, GeneratorInput, RenderResult

from . import generate_mesh as _geometry
from .generate_mesh import (
    MESH_PROVENANCE_FILE,
    MeshGenerationError,  # noqa: F401  (raised through build; web callers catch it)
    _COMPONENTS_FILENAME,
    _backend_label,
    render_agent_mesh_obj_text,
)

logger = logging.getLogger("propeller_agent")


def build(inp: GeneratorInput) -> BuildResult:
    """Generate the mesh into ``inp.model_path``.  Raises
    ``MeshGenerationError`` when both geometry backends fail."""
    _geometry.set_geometry_backend(inp.settings["geometry_backend"])
    out_path_dir, output_path = inp.attempt_dir, inp.model_path

    # Delegate to the backend dispatcher (selected backend + bidirectional
    # fallback).  On MeshGenerationError the geometry failed on BOTH
    # backends — the engine returns the error and does NOT render.
    mesh_text, vertex_count, components_text, backend_used = (
        render_agent_mesh_obj_text(inp.params)
    )

    # Write the primary mesh.
    output_path.write_text(mesh_text, encoding="utf-8")

    # F75b: record what produced it.  Best-effort on purpose — a sidecar
    # we cannot write must never fail a mesh that built fine; its absence
    # only means a later parameter write has nothing to check against,
    # which is exactly the pre-F75b behaviour.
    try:
        (out_path_dir / MESH_PROVENANCE_FILE).write_text(
            json.dumps(inp.params, indent=2, ensure_ascii=False),
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
    files = [output_path]
    if components_text is not None:
        sidecar_path = out_path_dir / _COMPONENTS_FILENAME
        sidecar_path.write_text(components_text, encoding="utf-8")
        files.append(sidecar_path)

    return BuildResult(
        summary=(
            f"Mesh saved to {output_path.resolve()} ({file_size} bytes, "
            f"{vertex_count} vertices). Parts: {parts_used}. "
            f"Geometry backend: {_backend_label(backend_used)}."
        ),
        model_files=files,
    )


def render_and_check(mesh_path: str, output_dir: str, settings: dict) -> str:
    """The render+check core chosen by the ``render_library`` setting, with
    the quality checks switched by ``mesh_checks``."""
    if settings["render_library"] == "pyvista":
        from . import render_mesh_pyvista as core
        run = core.render_and_check_pv
    else:
        from . import render_mesh as core
        run = core.render_and_check
    core.set_mesh_checks(bool(settings["mesh_checks"]))
    return run(mesh_path, output_dir)


def render(inp: GeneratorInput) -> RenderResult:
    """Render (and check) the attempt's mesh: the three views and the
    report the agent reads.  Existing renders are reused by the core."""
    return RenderResult(report=render_and_check(
        str(inp.model_path), str(inp.attempt_dir), inp.settings))
