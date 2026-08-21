"""Make an attempt's render set complete, just before it is archived.

An attempt used to be archived with whatever renders the Tool Caller
happened to have produced.  If it never called the blade-sections tool,
that attempt has no blade-sections render — permanently, because saving is
irreversible.  This module closes that: given an attempt folder holding a
``parameters.json``, it CREATES every enabled render that is missing, using
the same tools the live workflow uses, and then the uploader archives a
complete record.

BEST-EFFORT, ALWAYS
-------------------
:func:`ensure_renders` NEVER raises.  End Session must not fail (W1): one
bad render must not cost the whole attempt, and a systematic render failure
must not silently archive nothing.  Every outcome is reported per view --
found / generated / failed -- so a thin archive is diagnosable afterwards
rather than mysterious.

ORDER MATTERS
-------------
Blade sections come FIRST.  They render from ``parameters.json`` alone, so
they are always possible; the 3D views need ``propeller_mesh.obj`` and, when
that is absent, the geometry backend.  Doing the cheap always-possible one
first means an unreachable geometry backend cannot block it.

THE EXPENSIVE PATH
------------------
When an enabled 3D view is missing AND the mesh is absent, completing it
means invoking the geometry backend (FEG via Node, or RhinoCompute) inside
the save.  That is an external call on the one path that must not fail,
which is why ``ATTEMPT_RENDER_COMPLETION_ON_SAVE`` exists as a master
off-switch and ``ATTEMPT_RENDER_COMPLETION_TIMEOUT_S`` bounds it per
attempt.  Heavy imports are LAZY, inside the functions, so importing this
module costs nothing.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from agents.shared import attempt_views
from workflow_settings import settings as _settings

logger = logging.getLogger("propeller_agent")

_PARAMS = "parameters.json"
_MESH = "propeller_mesh.obj"


def _enabled() -> bool:
    return bool(getattr(_settings, "ATTEMPT_RENDER_COMPLETION_ON_SAVE", True))


def _timeout_s() -> int:
    try:
        return int(getattr(_settings, "ATTEMPT_RENDER_COMPLETION_TIMEOUT_S", 120))
    except (TypeError, ValueError):
        return 120


def _missing(folder: Path, views: list[str]) -> list[str]:
    return [v for v in views
            if not (folder / attempt_views.VIEW_FILES[v]).is_file()]


def _render_blade_sections(folder: Path, report: dict) -> None:
    """Blade sections from parameters.json.  No mesh needed."""
    try:
        from tools.render_blade_sections.render_blade_sections import (
            render_blade_sections,
        )
        out = render_blade_sections(str((folder / _PARAMS).resolve()))
    except Exception as exc:  # noqa: BLE001 — never break the save
        report["failed"].append(("blade_sections",
                                 f"{type(exc).__name__}: {exc}"))
        return
    if (folder / attempt_views.VIEW_FILES["blade_sections"]).is_file():
        report["generated"].append("blade_sections")
    else:
        report["failed"].append(
            ("blade_sections", str(out)[:200] or "tool wrote no file"))


def _render_mesh_views(folder: Path, missing: list[str], report: dict) -> None:
    """The 3D views.  Generates the mesh first when it is absent.

    The render core writes all three mesh views in ONE call, so this runs
    once for the whole set rather than per view.
    """
    mesh = folder / _MESH
    if not mesh.is_file():
        try:
            from tools.generate_mesh.generate_mesh import (
                generate_and_render_propeller,
            )
        except Exception as exc:  # noqa: BLE001
            for v in missing:
                report["failed"].append(
                    (v, f"geometry tool unavailable: {type(exc).__name__}"))
            return
        try:
            # It takes ONLY the parameters path and derives the attempt
            # folder from it, so geometry can never be built from one
            # attempt's numbers into another's folder.  It builds the mesh
            # AND renders the three views in the same call.
            #
            # ``.func`` unwraps the @tool StructuredTool to the underlying
            # callable.  The @tool_active layer beneath is safe here: its
            # instrumentation is wrapped in try/except precisely so it
            # cannot break a real invocation, and there is no agent turn in
            # flight during a save.
            fn = getattr(generate_and_render_propeller, "func",
                         generate_and_render_propeller)
            fn(str((folder / _PARAMS).resolve()))
        except Exception as exc:  # noqa: BLE001
            for v in missing:
                report["failed"].append(
                    (v, f"mesh generation failed: {type(exc).__name__}: {exc}"))
            return
        # generate_and_render_propeller renders as part of the same call
        for v in list(missing):
            if (folder / attempt_views.VIEW_FILES[v]).is_file():
                report["generated"].append(v)
            else:
                report["failed"].append((v, "mesh built but render absent"))
        return

    # Mesh already there — render only.
    try:
        from tools import get_render_core
        core = get_render_core()
        core(str(mesh.resolve()), str(folder.resolve()))
    except Exception as exc:  # noqa: BLE001
        for v in missing:
            report["failed"].append(
                (v, f"render failed: {type(exc).__name__}: {exc}"))
        return
    for v in missing:
        if (folder / attempt_views.VIEW_FILES[v]).is_file():
            report["generated"].append(v)
        else:
            report["failed"].append((v, "render core wrote no file"))


def ensure_renders(attempt_folder: Path) -> dict:
    """Create every enabled render *attempt_folder* is missing.

    Returns ``{"found": [...], "generated": [...], "failed": [(view, why)],
    "skipped": <reason or None>}``.  NEVER raises.
    """
    report: dict = {"found": [], "generated": [], "failed": [], "skipped": None}
    try:
        folder = Path(attempt_folder)
        if not _enabled():
            report["skipped"] = "ATTEMPT_RENDER_COMPLETION_ON_SAVE is off"
            return report
        if not folder.is_dir():
            report["skipped"] = "not a directory"
            return report
        if not (folder / _PARAMS).is_file():
            # Nothing to render FROM.  An attempt with no parameters is not
            # an incomplete record, it is a different kind of record.
            report["skipped"] = f"no {_PARAMS}"
            return report

        views = attempt_views.enabled_views()
        report["found"] = [v for v in views if v not in _missing(folder, views)]
        missing = _missing(folder, views)
        if not missing:
            return report

        started = time.monotonic()
        # Cheap and always possible first: blade sections need only the
        # parameters file, so an unreachable geometry backend cannot block
        # them.
        if "blade_sections" in missing:
            _render_blade_sections(folder, report)

        mesh_missing = [v for v in missing if v in attempt_views.MESH_VIEWS]
        if mesh_missing:
            if time.monotonic() - started > _timeout_s():
                for v in mesh_missing:
                    report["failed"].append((v, "timeout before 3D render"))
            else:
                _render_mesh_views(folder, mesh_missing, report)
    except Exception as exc:  # noqa: BLE001 — the whole point: never raise
        report["failed"].append(("*", f"{type(exc).__name__}: {exc}"))
    return report


def log_report(attempt_folder: Path, report: dict) -> None:
    """One log line naming found / generated / failed, per attempt."""
    name = Path(attempt_folder).name
    if report.get("skipped"):
        logger.info("[renders]  %s: skipped (%s)", name, report["skipped"])
        return
    logger.info(
        "[renders]  %s: found=%s generated=%s failed=%s",
        name,
        ",".join(report["found"]) or "-",
        ",".join(report["generated"]) or "-",
        ",".join("%s(%s)" % (v, why[:60]) for v, why in report["failed"])
        or "-",
    )
