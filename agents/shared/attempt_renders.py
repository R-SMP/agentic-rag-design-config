"""Make an attempt's render set complete, just before it is archived.

An attempt used to be archived with whatever renders the tool runner
happened to have produced.  If it never called a picture-making tool, that
attempt lacks that tool's pictures -- permanently, because saving is
irreversible.  This module closes that: given an attempt folder holding a
``parameters.json``, it CREATES every enabled picture that is missing, using
the same tools the live workflow uses, and then the uploader archives a
complete record.

WHICH TOOL MAKES WHICH PICTURE
------------------------------
The tools say so in their ``tool.yaml`` (engine/pack_tools.py): each lists
the pictures it makes (``outputs.images``, the picture contract: the PNG
``render_<view>.png`` written into the attempt folder it is given) and
whether this save step may use it to add a missing one (``fill_on_save``).
A picture whose tool does not allow it stays missing and is reported.

BEST-EFFORT, ALWAYS
-------------------
:func:`ensure_renders` NEVER raises.  End Session must not fail (W1): one
bad render must not cost the whole attempt, and a systematic render failure
must not silently archive nothing.  Every outcome is reported per view --
found / generated / failed -- so a thin archive is diagnosable afterwards
rather than mysterious.

ORDER MATTERS
-------------
Pictures from helper tools come FIRST.  A helper draws from
``parameters.json`` alone (it is called with that file's path as its first
argument), so it is always possible; the generator's pictures need its model
and, when that is absent, the geometry backend.  Doing the cheap
always-possible ones first means an unreachable geometry backend cannot
block them.

THE EXPENSIVE PATH
------------------
When an enabled generator picture is missing AND the model is absent,
completing it means invoking the geometry backend inside the save.  That is
an external call on the one path that must not fail, which is why
``ATTEMPT_RENDER_COMPLETION_ON_SAVE`` exists as a master off-switch and
``ATTEMPT_RENDER_COMPLETION_TIMEOUT_S`` bounds it per attempt.  Heavy
imports are LAZY, inside the functions, so importing this module costs
nothing.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from agents.shared import attempt_views
from workflow_settings import settings as _settings

logger = logging.getLogger("mas_agent")

_PARAMS = "parameters.json"


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


def _check(folder: Path, views: list[str], report: dict, why_absent: str) -> None:
    for v in views:
        if (folder / attempt_views.VIEW_FILES[v]).is_file():
            report["generated"].append(v)
        else:
            report["failed"].append((v, why_absent))


def _fill_from_helper(tool: str, folder: Path, views: list[str], report: dict) -> None:
    """A helper's pictures, from parameters.json alone."""
    try:
        from engine import pack_tools
        fn = pack_tools.plugin(tool).function(pack_tools.manifest(tool)["entrypoint"])
        out = fn(str((folder / _PARAMS).resolve()))
    except Exception as exc:  # noqa: BLE001 -- never break the save
        for v in views:
            report["failed"].append((v, f"{type(exc).__name__}: {exc}"))
        return
    _check(folder, views, report, str(out)[:200] or "tool wrote no file")


def _fill_from_generator(tool: str, folder: Path, views: list[str], report: dict) -> None:
    """The generator's pictures.  Builds its model first when it is absent;
    its render step writes all its pictures in ONE call, so this runs once
    for the whole set rather than per view."""
    from agents.shared.pack_text import fill
    from engine import pack_tools
    model = folder / (pack_tools.model_file() or "-")
    if not model.is_file():
        try:
            # The same run the agents' tool does: it takes ONLY the
            # parameters path and derives the attempt folder from it, so a
            # model can never be built from one attempt's numbers into
            # another's folder.  It builds the model AND renders it.
            pack_tools.run_generator(tool, str((folder / _PARAMS).resolve()))
        except Exception as exc:  # noqa: BLE001
            for v in views:
                report["failed"].append(
                    (v, fill("$output_model generation failed: ")
                     + f"{type(exc).__name__}: {exc}"))
            return
        _check(folder, views, report, fill("$output_model built but render absent"))
        return
    # The model is already there -- render only.
    try:
        pack_tools.render_existing(tool, folder)
    except Exception as exc:  # noqa: BLE001
        for v in views:
            report["failed"].append((v, f"render failed: {type(exc).__name__}: {exc}"))
        return
    _check(folder, views, report, "render core wrote no file")


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

        from engine import pack_tools
        tool_of = {r["view"]: r["tool"] for r in pack_tools.image_outputs()}
        by_tool: dict[str, list[str]] = {}
        for v in missing:
            tool = tool_of.get(v)
            if tool is None or not pack_tools.manifest(tool).get("fill_on_save"):
                report["failed"].append((v, "its tool does not add pictures at save time"))
            else:
                by_tool.setdefault(tool, []).append(v)
        manifests = pack_tools.manifests()
        helpers = [t for t in by_tool if manifests[t]["kind"] == "helper"]
        generators = [t for t in by_tool if manifests[t]["kind"] == "generator"]

        started = time.monotonic()
        # Cheap and always possible first: a helper needs only the
        # parameters file, so an unreachable geometry backend cannot block it.
        for tool in helpers:
            _fill_from_helper(tool, folder, by_tool[tool], report)
        for tool in generators:
            if time.monotonic() - started > _timeout_s():
                for v in by_tool[tool]:
                    report["failed"].append((v, "timeout before the generator ran"))
            else:
                _fill_from_generator(tool, folder, by_tool[tool], report)
    except Exception as exc:  # noqa: BLE001 -- the whole point: never raise
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
