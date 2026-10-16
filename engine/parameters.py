"""The design configurator's parameters: ``dc_pack/parameters.json``.

The ONE source of the parameter data -- names and their canonical order,
types, ranges, steps, defaults, groups, and the wording each consumer shows:
the slider page's ``label`` / ``unit`` and the database rows' ``db_unit`` /
``db_description`` (kept apart because those consumers word the same
parameter differently today; making them agree is a separate change).

Read by the runtime validator (``prompts.PARAMETER_NAMES`` /
``PARAMETER_TYPES``), the ``$parameter_count`` slot, the web app's preview
check and slider page (``/pack/parameters.js``) and the parameter-schema
upload (``engine/parameter_schema.py``).  Read fresh on every call: it is a
small file and a local Studio may change it between sessions.

The agents' parameter LISTS are hand-written text in ``dc_pack/fragments/``
(``$parameter_list`` and its per-agent copies), not generated from here;
``extra_utilities/tests/smoke_test_parameters.py`` checks they name the same
parameters, in the same order, with the same ranges.

No version number lives here: the database assigns one when the parameters
are uploaded (``engine/parameter_schema.py``).

``retired`` (optional) lists names that were parameters once and are no
longer: a record that still carries one is read without it
(:func:`retired`), instead of being rejected for an unknown name.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from engine import pack as _pack

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TYPES = {"int": int, "float": float}
_PARAM_KEYS = ("name", "type", "min", "max", "step", "default", "group",
               "label", "unit", "db_unit", "db_description")
_GROUP_KEYS = ("id", "label", "image", "image_alt", "order")


class ParameterSpecError(ValueError):
    """``parameters.json`` is missing or invalid; the message lists every
    problem, each naming the parameter or group it is about."""


def spec_path() -> Path:
    return _pack.pack_dir() / "parameters.json"


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate(spec) -> list[str]:
    """Every problem in *spec* (an already-parsed parameters.json), or []."""
    if not isinstance(spec, dict) or not (
            {"groups", "parameters"} <= set(spec) <= {"groups", "parameters", "retired"}):
        return ['the file must be an object with "groups" and "parameters" '
                '(and, optionally, "retired")']
    problems: list[str] = []
    groups, params = spec["groups"], spec["parameters"]
    if not isinstance(groups, list) or not isinstance(params, list) or not params:
        return ['"groups" and "parameters" must be lists, "parameters" not empty']

    names: list[str] = []
    for i, p in enumerate(params):
        where = f"parameter #{i + 1}"
        if not isinstance(p, dict):
            problems.append(f"{where}: must be an object")
            continue
        name = p.get("name")
        if isinstance(name, str):
            where = name
        for k in sorted(set(_PARAM_KEYS) ^ set(p)):
            problems.append(f"{where}: {'missing' if k not in p else 'unknown'} field \"{k}\"")
        if not isinstance(name, str) or not _NAME_RE.match(name):
            problems.append(f"{where}: name must be a plain identifier (letters, digits, _)")
            continue
        if name in names:
            problems.append(f"{name}: duplicate name")
        names.append(name)
        typ = p.get("type")
        if typ not in _TYPES:
            problems.append(f"{name}: type must be \"int\" or \"float\"")
        lo, hi, step, default = p.get("min"), p.get("max"), p.get("step"), p.get("default")
        if not all(_number(v) for v in (lo, hi, step, default)):
            problems.append(f"{name}: min, max, step and default must be numbers")
            continue
        if not lo < hi:
            problems.append(f"{name}: min ({lo}) must be smaller than max ({hi})")
        if step <= 0:
            problems.append(f"{name}: step must be positive")
        if not lo <= default <= hi:
            problems.append(f"{name}: default {default} is outside [{lo}; {hi}]")
        if typ == "int" and not all(float(v).is_integer() for v in (lo, hi, step, default)):
            problems.append(f"{name}: an int parameter needs whole-number min, max, step and default")
        for k in ("label", "unit", "db_unit", "db_description", "group"):
            if k in p and not isinstance(p[k], str):
                problems.append(f"{name}: {k} must be text")

    gids: list[str] = []
    placed: dict[str, str] = {}
    for i, g in enumerate(groups):
        if not isinstance(g, dict):
            problems.append(f"group #{i + 1}: must be an object")
            continue
        gid = g.get("id") if isinstance(g.get("id"), str) else f"group #{i + 1}"
        for k in sorted(set(_GROUP_KEYS) ^ set(g)):
            problems.append(f"group {gid}: {'missing' if k not in g else 'unknown'} field \"{k}\"")
        if gid in gids:
            problems.append(f"group {gid}: duplicate id")
        gids.append(gid)
        for n in g.get("order") or []:
            if n not in names:
                problems.append(f"group {gid}: lists {n!r}, which is not a parameter")
            elif n in placed:
                problems.append(f"{n}: listed in two groups ({placed[n]}, {gid})")
            else:
                placed[n] = gid
    retired = spec.get("retired", [])
    if not isinstance(retired, list):
        problems.append('"retired" must be a list of names')
    else:
        for n in retired:
            if not isinstance(n, str) or not _NAME_RE.match(n):
                problems.append(f"retired name {n!r}: must be a plain identifier")
            elif n in names:
                problems.append(f"{n}: listed as retired but still a parameter")
            elif retired.count(n) > 1:
                problems.append(f"{n}: listed as retired twice")
    for p in params:
        if not isinstance(p, dict) or p.get("name") not in names:
            continue
        name, gid = p["name"], p.get("group")
        if gid not in gids:
            problems.append(f"{name}: group {gid!r} does not exist")
        elif placed.get(name) != gid:
            problems.append(f"{name}: not listed in the order of its group {gid!r}")
    return problems


def load(path: Path | None = None) -> dict:
    """The validated parameters.json.  Raises ParameterSpecError."""
    path = path or spec_path()
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ParameterSpecError(f"{path} does not exist") from None
    except json.JSONDecodeError as exc:
        raise ParameterSpecError(f"{path.name} is not valid JSON: {exc}") from None
    problems = validate(spec)
    if problems:
        raise ParameterSpecError(
            f"{path.name} has {len(problems)} problem(s):\n  " + "\n  ".join(problems))
    return spec


# ---------------------------------------------------------------------------
# What each consumer reads
# ---------------------------------------------------------------------------

def names(spec: dict | None = None) -> tuple[str, ...]:
    """The parameter names in canonical order (JSON field order, validator)."""
    return tuple(p["name"] for p in (spec or load())["parameters"])


def types(spec: dict | None = None) -> dict[str, type]:
    return {p["name"]: _TYPES[p["type"]] for p in (spec or load())["parameters"]}


def count(spec: dict | None = None) -> int:
    return len((spec or load())["parameters"])


def retired(spec: dict | None = None) -> tuple[str, ...]:
    """Names that are parameters no longer: a record carrying one is read
    without it (the web app's preview check, ``propose_attempt``)."""
    return tuple((spec or load()).get("retired", []))


def preview_spec(spec: dict | None = None) -> dict[str, dict]:
    """``{name: {"type", "min", "max"}}`` -- the web app's preview check."""
    return {p["name"]: {"type": p["type"], "min": p["min"], "max": p["max"]}
            for p in (spec or load())["parameters"]}


def slider_groups(spec: dict | None = None) -> list[dict]:
    """The slider page's groups, in the shape ``web/app.js`` uses
    (``PARAM_GROUPS``): page label, diagram, and each slider in page order."""
    spec = spec or load()
    by_name = {p["name"]: p for p in spec["parameters"]}
    return [{
        "key": g["id"], "label": g["label"], "image": g["image"],
        "imageAlt": g["image_alt"],
        "params": [{"key": n, "label": by_name[n]["label"], "unit": by_name[n]["unit"],
                    "min": by_name[n]["min"], "max": by_name[n]["max"],
                    "step": by_name[n]["step"], "value": by_name[n]["default"]}
                   for n in g["order"]],
    } for g in spec["groups"]]


def page_payload(spec: dict | None = None) -> dict:
    """What ``/pack/parameters.js`` hands the page as ``window.PACK_PARAMETERS``."""
    spec = spec or load()
    return {"names": list(names(spec)), "groups": slider_groups(spec)}


def db_rows(spec: dict | None = None) -> list[dict]:
    """The rows of table ``dc_parameter_schemas`` for these parameters."""
    return [{"param_name": p["name"], "min_value": p["min"], "max_value": p["max"],
             "unit": p["db_unit"], "description": p["db_description"]}
            for p in (spec or load())["parameters"]]
