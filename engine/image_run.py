"""Run the pack's image tools on parameter sets -- in a process of its own.

Two callers in the web app need the tools' pictures of parameter values that
are not an attempt:

* the Parameters page's generic **Preview** button, for a pack without a
  browser preview module (``dc_pack/preview/``);
* the render-compression panel's **Generate samples** button: the pictures
  of the pack's sample parameter sets (``render_samples`` in
  ``dc_pack/pack.yaml``), one per compression kind and size.

The tools write into attempt folders, and a helper may refuse any other
place (blade sections does).  So each set gets an attempt folder in a
throw-away attempts root, and the run happens in a child process
(:func:`run_in_child`) whose ``config.ATTEMPTS_DIR`` is that root: nothing
reaches the session's own attempts folder, which the Receptionist reads as
"the latest attempt" and End Session archives.

A run is what the save step does for an attempt (``agents/shared/
attempt_renders.py``): every switched-on tool that makes pictures -- the
helpers first, called with the parameter file, then the generator, which
builds its model and renders it -- and the pictures of the switched-on
views, in their declared order.

    python -m engine.image_run <sets.json> <root>

reads ``{"<name>": {<parameter>: <value>, ...}, ...}`` and prints
``{"<name>": {"images": [...], "errors": [...]}}`` (see :func:`run`).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import yaml

import config
from engine import pack as _pack
from engine import pack_tools
from engine import parameters as _parameters

# The render-compression panel's name for each compression kind's samples
# (web_app.py: <name>_<size>.png).
SAMPLE_NAMES = {"cross_sections": "cross", "3d_render": "geo"}


def render_sample_sets(path: Path | None = None) -> dict[str, dict]:
    """``render_samples`` from ``dc_pack/pack.yaml``: size name -> a full
    parameter set (every parameter, a number each; the values are pictures
    for the compression slider, so a range is not enforced).  ``{}`` when
    the pack names none."""
    path = path or _pack.pack_dir() / "pack.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return {}
    sets = data.get("render_samples") or {}
    names = set(_parameters.names())
    problems = []
    if not isinstance(sets, dict):
        problems.append("render_samples maps a size name to a parameter set")
        sets = {}
    for size, values in sets.items():
        if not isinstance(values, dict) or set(values) != names or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) for v in values.values()):
            problems.append(f"render_samples.{size}: must give every parameter "
                            f"({len(names)}) a number, and nothing else")
    if problems:
        raise pack_tools.PackToolError(f"{path.name}: " + "; ".join(problems))
    return {size: {n: values[n] for n in _parameters.names()} for size, values in sets.items()}


def run(params: dict, root: Path, name: str = "preview") -> dict:
    """Make the pictures of *params* in an attempt folder under *root* (the
    attempts root of this run).  Returns ``{"images": [{tool, view, label,
    compression, order, path}], "errors": [{tool, message}]}``.  Sets
    ``config.ATTEMPTS_DIR`` to *root* while it runs (the child process's
    own; restored after)."""
    folder = root / f"{datetime.now():%Y%m%d_%H%M%S}_001_{name}"
    folder.mkdir(parents=True)
    params_file = folder / "parameters.json"
    params_file.write_text(json.dumps(params, indent=2), encoding="utf-8")
    real = config.ATTEMPTS_DIR
    config.ATTEMPTS_DIR = root
    errors: list[dict] = []
    try:
        rows = [r for r in pack_tools.image_outputs()
                if pack_tools.is_enabled(r["tool"]) and pack_tools.view_enabled(r["view"])]
        tools = []
        for r in rows:
            if r["tool"] not in tools:
                tools.append(r["tool"])
        kinds = {t: pack_tools.manifest(t)["kind"] for t in tools}
        # Like the save step: the helpers first (they need only the
        # parameter file), then the generator.
        for tool in [t for t in tools if kinds[t] == "helper"]:
            try:
                answer = pack_tools.plugin(tool).function(
                    pack_tools.manifest(tool)["entrypoint"])(str(params_file))
                if isinstance(answer, str) and answer.startswith("Error"):
                    errors.append({"tool": tool, "message": answer})
            except Exception as exc:  # noqa: BLE001 — report, keep the others
                errors.append({"tool": tool, "message": f"{type(exc).__name__}: {exc}"})
        for tool in [t for t in tools if kinds[t] == "generator"]:
            try:
                answer = pack_tools.run_generator(tool, str(params_file))
                first = answer.split("\n", 1)[0]
                if answer.startswith("Error") or "error:" in first:
                    errors.append({"tool": tool, "message": first})
                elif "Render step failed" in answer:
                    errors.append({"tool": tool, "message":
                                   answer[answer.index("Render step failed"):][:300]})
            except Exception as exc:  # noqa: BLE001
                errors.append({"tool": tool, "message": f"{type(exc).__name__}: {exc}"})
    finally:
        config.ATTEMPTS_DIR = real
    labels = {}
    for t in tools:
        for img in pack_tools.manifest(t)["outputs"].get("images") or []:
            labels[img["view"]] = img.get("label", img["view"])
    images = [{"tool": r["tool"], "view": r["view"], "label": labels.get(r["view"], r["view"]),
               "compression": r["compression"], "order": r["order"],
               "path": str(folder / r["file"])}
              for r in rows if (folder / r["file"]).is_file()]
    return {"images": images, "errors": errors}


def run_in_child(sets: dict[str, dict], timeout: float = 240) -> tuple[dict, Path]:
    """Run :func:`run` for each named parameter set in a child process with
    its own attempts root.  Returns ``(result by name, the root)``; the
    caller deletes the root when it has read the pictures.  Raises
    RuntimeError when the child fails."""
    root = Path(tempfile.mkdtemp(prefix="mas_images_"))
    sets_file = root / "sets.json"
    sets_file.write_text(json.dumps(sets), encoding="utf-8")
    repo = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", DC_PACK_DIR=str(config.DC_PACK_DIR))
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "engine.image_run", str(sets_file), str(root / "attempts")],
            cwd=str(repo), env=env, capture_output=True, text=True, encoding="utf-8",
            timeout=timeout)
    except subprocess.TimeoutExpired:
        shutil.rmtree(root, ignore_errors=True)
        raise RuntimeError(f"the tools took longer than {timeout:g} s") from None
    if proc.returncode != 0:
        shutil.rmtree(root, ignore_errors=True)
        raise RuntimeError(((proc.stderr or proc.stdout) or "no output").strip()[-600:])
    out = proc.stdout.strip().splitlines()
    return json.loads(out[-1] if out else "{}"), root


def make_render_samples(out_dir: Path, timeout: float = 600) -> dict:
    """The render-compression panel's samples: every image tool run on each
    of the pack's sample sets; per compression kind, the first picture of
    that kind (by declared order) is kept as ``<cross|geo>_<size>.png`` in
    *out_dir*.  Returns ``{"written": [...], "errors": [...]}``."""
    sets = render_sample_sets()
    if not sets:
        return {"written": [], "errors": [{"tool": "", "message":
                                           "dc_pack/pack.yaml names no render_samples"}]}
    result, root = run_in_child(sets, timeout=timeout)
    written, errors = [], []
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        for size, res in result.items():
            errors += [dict(e, set=size) for e in res.get("errors", [])]
            for kind, short in SAMPLE_NAMES.items():
                first = next((i for i in sorted(res.get("images", []), key=lambda i: i["order"])
                              if i["compression"] == kind), None)
                if first:
                    dest = out_dir / f"{short}_{size}.png"
                    shutil.copyfile(first["path"], dest)
                    written.append(dest.name)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return {"written": written, "errors": errors}


def _main(argv: list[str]) -> int:
    sets = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    root = Path(argv[1])
    out = {name: run(params, root, name) for name, params in sets.items()}
    sys.stdout.write("\n" + json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
