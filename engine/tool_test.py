"""Test one tool of the pack on a parameter set -- in a process of its own.

The Studio's **Test tool** (MAS-blueprint P6c): the tool is called the way
the system calls it -- a generator or a helper as the agents' tool runner
calls it, with the path of an attempt's ``parameters.json``; a geometry tool
as the engine calls it (``make_model``) -- on an attempt folder of its own
under a throw-away attempts root (``config.ATTEMPTS_DIR`` is set to it in
this process, as ``engine/image_run.py`` does), with this run's settings
laid over the tool's own.

    python -m engine.tool_test <job.json> <report.json>

reads ``{"tool": name, "params": {parameter: value}, "settings": {setting:
value}, "root": attempts root}`` and writes the report (:func:`run`).  What
the tool itself prints or logs, and what the programs it starts print, go
to this process's stdout / stderr: the caller keeps them as the run's
output lines.
"""

from __future__ import annotations

import base64
import json
import logging
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import config
from engine import pack_tools
from engine.tooling import ToolError

PICTURE_MAX = 3 * 1024 * 1024


def _png_size(raw: bytes) -> tuple[int, int] | None:
    if raw[:8] != b"\x89PNG\r\n\x1a\n" or len(raw) < 24:
        return None
    return int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")


def _vertices(raw: bytes) -> int | None:
    """The vertex count of an OBJ model (``v`` lines)."""
    try:
        return sum(1 for ln in raw.decode("utf-8", "replace").splitlines() if ln.startswith("v "))
    except Exception:                                           # noqa: BLE001
        return None


def _picture(path: Path, view, label, declared: bool) -> dict:
    raw = path.read_bytes()
    size = _png_size(raw)
    return {"view": view, "label": label, "file": path.name, "bytes": len(raw), "declared": declared,
            "width": size[0] if size else None, "height": size[1] if size else None,
            "png": base64.b64encode(raw).decode("ascii") if len(raw) <= PICTURE_MAX and size else None}


def run(tool: str, params: dict, settings: dict | None, root: Path) -> dict:
    """The report of one run: ``answer`` (what the agent -- or, for a
    geometry tool, the engine -- gets), ``error`` (a traceback, or the
    tool's own error), ``seconds``, ``files`` written, ``pictures`` (each
    declared one that was made, any other PNG, base64), ``model`` (file,
    bytes, vertex count) and ``mismatches`` with the manifest."""
    m = pack_tools.manifest(tool)
    kind = m["kind"]
    folder = root / f"{datetime.now():%Y%m%d_%H%M%S}_001_test"
    folder.mkdir(parents=True)
    params_file = folder / "parameters.json"
    params_file.write_text(json.dumps(params, indent=2), encoding="utf-8")
    real = config.ATTEMPTS_DIR
    config.ATTEMPTS_DIR = root
    pack_tools.settings_override_for_tests({tool: dict(settings)} if settings else None)
    report = {"tool": tool, "kind": kind, "answer": None, "error": None, "seconds": None,
              "settings": dict(pack_tools.settings(tool)), "files": [], "pictures": [],
              "model": None, "mismatches": []}
    made = None
    t0 = time.perf_counter()
    try:
        if kind == "generator":
            report["answer"] = pack_tools.run_generator(tool, str(params_file))
        elif kind == "helper":
            answer = pack_tools.plugin(tool).function(m["entrypoint"])(str(params_file))
            report["answer"] = answer if isinstance(answer, str) else repr(answer)
        else:
            values, err = pack_tools._read_record(params_file)
            if err is not None:
                report["answer"] = err
            else:
                made = pack_tools.make_model(values, [tool])
                fmt = m["outputs"]["model_format"]
                (folder / f"model.{fmt}").write_text(made.result.model, encoding="utf-8")
                for fname, content in (made.result.extra_files or {}).items():
                    (folder / fname).write_text(content, encoding="utf-8")
                report["answer"] = (f"{m['display_name']} made a .{fmt} model: "
                                    f"{made.result.vertex_count} vertices (as the tool says), "
                                    f"{len(made.result.model.encode('utf-8'))} bytes.")
    except ToolError as exc:
        report["error"] = str(exc)
    except Exception:                                           # noqa: BLE001
        report["error"] = traceback.format_exc()
    finally:
        report["seconds"] = round(time.perf_counter() - t0, 2)
        config.ATTEMPTS_DIR = real
        pack_tools.settings_override_for_tests(None)
    answer = str(report["answer"] or "")
    # An error answer, or a generator whose render step failed (its answer
    # keeps the build summary first), as engine/image_run.py reads them.
    failed = (bool(report["error"]) or answer.startswith("Error")
              or "error:" in answer.split("\n", 1)[0] or "Render step failed" in answer)
    report["failed"] = failed
    # What it wrote
    for p in sorted(folder.rglob("*")):
        if p.is_file() and p != params_file:
            report["files"].append({"file": p.relative_to(folder).as_posix(), "bytes": p.stat().st_size})
    # The pictures: the declared ones, then any other picture file
    declared = (m.get("outputs") or {}).get("images") or []
    seen = set()
    for img in declared:
        path = folder / img["file"]
        on = report["settings"].get(f"view_{img['view']}", img.get("default_enabled", True))
        if path.is_file():
            report["pictures"].append(_picture(path, img["view"], img.get("label", img["view"]), True))
            seen.add(path.name)
        elif on and not failed:
            report["mismatches"].append(f"The manifest declares the picture {img['file']} "
                                        f"(view {img['view']}), but the run did not make it.")
    for p in sorted(folder.glob("*.png")):
        if p.name not in seen:
            report["pictures"].append(_picture(p, None, p.name, False))
            report["mismatches"].append(f"The run made {p.name}, which the manifest does not "
                                        f"declare (a picture of view V is render_V.png).")
    # The model
    if kind == "generator":
        f = (m.get("outputs") or {}).get("model_file")
        path = folder / f if f else None
        if path is not None and path.is_file():
            raw = path.read_bytes()
            report["model"] = {"file": f, "bytes": len(raw), "vertices": _vertices(raw)}
            if not raw.strip():
                report["mismatches"].append(f"The model file {f} is empty.")
        elif f and not failed:
            report["mismatches"].append(f"The manifest names the model file {f}, but the run "
                                        f"did not write it.")
    elif kind == "geometry" and made is not None:
        raw = made.result.model.encode("utf-8")
        counted = _vertices(raw)
        report["model"] = {"file": f"model.{m['outputs']['model_format']}", "bytes": len(raw),
                           "vertices": counted}
        if not raw.strip():
            report["mismatches"].append("The model the tool returned is empty.")
        elif made.result.vertex_count is not None and counted != made.result.vertex_count:
            report["mismatches"].append(f"The tool says {made.result.vertex_count} vertices; the "
                                        f"model has {counted}.")
    return report


def _main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(levelname)s %(name)s: %(message)s")
    job = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    try:
        report = run(job["tool"], job.get("params") or {}, job.get("settings"), Path(job["root"]))
    except Exception:                                           # noqa: BLE001
        report = {"tool": job.get("tool"), "failed": True, "error": traceback.format_exc(),
                  "files": [], "pictures": [], "model": None, "mismatches": []}
    Path(argv[1]).write_text(json.dumps(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
