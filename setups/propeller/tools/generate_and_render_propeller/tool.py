"""``generate_and_render_propeller`` -- the propeller generator's two steps.

The engine (``engine/pack_tools.run_generator``) owns everything around
them: it checks that ``parameters_path`` lies in an attempt folder, reads and
validates the record, reuses a ``propeller_mesh.obj`` already in the folder
(append-only: never overwritten) and joins the two results into the text
the agent gets.  This file only:

* :func:`build` -- has the engine build the mesh with the geometry tool
  its ``geometry_tool`` setting picks (``feg_geometry`` or
  ``rhino_geometry``; ``fallback_geometry_tool`` when it fails) and writes
  it, the files the geometry tool adds beside it and the provenance record;
* :func:`render` -- renders the three views and, when the ``mesh_checks``
  setting is on, runs the quality checks, with the render core chosen by
  the ``render_library`` setting.

Both read this tool's settings (``tool.yaml``) from ``inp.settings``.
"""

from __future__ import annotations

import json
import logging

from engine.tooling import BuildResult, GeneratorInput, MadeModel, RenderResult

from .mesh_provenance import MESH_PROVENANCE_FILE

logger = logging.getLogger("mas_agent")


def _backend_label(made: MadeModel) -> str:
    """The geometry tool that built the mesh, for the summary, noting when
    the fallback did."""
    if made.made_by != made.chosen:
        return f"{made.made_by} (fallback — {made.chosen} unavailable)"
    return made.made_by


def build(inp: GeneratorInput) -> BuildResult:
    """Generate the mesh into ``inp.model_path``.  Raises ``ToolError``
    when the geometry tool (and the fallback) fail."""
    out_path_dir, output_path = inp.attempt_dir, inp.model_path

    # The engine runs the chosen geometry tool, then the fallback.  On
    # ToolError no geometry was built — the engine returns the error and
    # does NOT render.
    made = inp.make_model(inp.params)
    mesh_text, vertex_count = made.result.model, made.result.vertex_count

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

    # The files the geometry tool adds beside the model (RhinoCompute's
    # per-component sidecar, for the offline diagnostic script).  Written
    # silently — the live tools never read them.
    files = [output_path]
    for name, text in made.result.extra_files.items():
        sidecar_path = out_path_dir / name
        sidecar_path.write_text(text, encoding="utf-8")
        files.append(sidecar_path)

    return BuildResult(
        summary=(
            f"Mesh saved to {output_path.resolve()} ({file_size} bytes, "
            f"{vertex_count} vertices). Parts: {parts_used}. "
            f"Geometry backend: {_backend_label(made)}."
        ),
        model_files=files,
    )


def render_and_check(mesh_path: str, output_dir: str, settings: dict) -> str:
    """The render+check core chosen by the ``render_library`` setting, with
    the quality checks switched by ``mesh_checks``."""
    if settings["render_library"] == "pyvista":
        from engine import mesh_render_pyvista as core
        run = core.render_and_check_pv
    else:
        from engine import mesh_render as core
        run = core.render_and_check
    core.set_mesh_checks(bool(settings["mesh_checks"]))
    return run(mesh_path, output_dir)


def render(inp: GeneratorInput) -> RenderResult:
    """Render (and check) the attempt's mesh: the three views and the
    report the agent reads.  Existing renders are reused by the core."""
    return RenderResult(report=render_and_check(
        str(inp.model_path), str(inp.attempt_dir), inp.settings))
