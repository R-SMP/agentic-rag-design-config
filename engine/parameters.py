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
parameters, in the same order, with the same ranges, and the Studio keeps
them so when it saves this file (``studio/params_edit.py``).

No version number lives here: the database assigns one when the parameters
are uploaded (``engine/parameter_schema.py``).

``retired`` (optional) lists names that were parameters once and are no
longer: a record that still carries one is read without it
(:func:`retired`), instead of being rejected for an unknown name.

Types (MAS-blueprint P6d): ``int`` and ``float`` numbers (``min``,
``max``, ``step``); ``choice`` -- one of its ``choices``, each
``{"value", "label"}``; ``bool`` -- on/off, ``true`` or ``false``.  Any
parameter may carry ``used_when``, ``{other: value or [values]}``: it only
matters while each named choice or on/off parameter has one of those
values (the agents are told; the slider page hides it otherwise).  A
record holds every parameter either way.  :func:`check_value` is the one
check of a value against its parameter; :func:`all_numbers` tells the
readers whose words say "a number" whether they still may.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from engine import pack as _pack

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TYPES = {"int": int, "float": float, "choice": object, "bool": bool}
# A number parameter's fields; a choice's and an on/off parameter's.
_PARAM_KEYS = ("name", "type", "min", "max", "step", "default", "group",
               "label", "unit", "db_unit", "db_description")
_CHOICE_KEYS = ("name", "type", "choices", "default", "group", "label", "unit",
                "db_unit", "db_description")
_BOOL_KEYS = ("name", "type", "default", "group", "label", "unit", "db_unit",
              "db_description")
_KEYS = {"int": _PARAM_KEYS, "float": _PARAM_KEYS, "choice": _CHOICE_KEYS, "bool": _BOOL_KEYS}
_OPTIONAL_KEYS = ("used_when",)
_GROUP_KEYS = ("id", "label", "image", "image_alt", "order")
# What a choice's value and label may not hold: the agents' list writes
# them as "value = label | value = label".
_CHOICE_TEXT_BAD = re.compile(r"[|\n\r]| = ")


class ParameterSpecError(ValueError):
    """``parameters.json`` is missing or invalid; the message lists every
    problem, each naming the parameter or group it is about."""


def spec_path() -> Path:
    return _pack.pack_dir() / "parameters.json"


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _same(a, b) -> bool:
    """Equal values, true / false never equal to 1 / 0."""
    return isinstance(a, bool) == isinstance(b, bool) and a == b


def _check_choices(name: str, p: dict, problems: list[str]) -> None:
    ch = p.get("choices")
    if not isinstance(ch, list) or len(ch) < 2 or not all(isinstance(c, dict) for c in ch):
        problems.append(f"{name}: choices must be a list of at least two {{value, label}}")
        return
    seen: list = []
    for c in ch:
        v = c.get("value")
        for k in sorted({"value", "label"} ^ set(c)):
            problems.append(f"{name}: a choice has {'no' if k not in c else 'an unknown field'} \"{k}\"")
        if not ((isinstance(v, str) and v.strip() and not _CHOICE_TEXT_BAD.search(v)) or _number(v)):
            problems.append(f"{name}: a choice's value must be a number or text without \"|\", "
                            f"\" = \" or a line break (got {v!r})")
        elif any(_same(v, s) for s in seen):
            problems.append(f"{name}: the choice {v!r} is listed twice")
        else:
            seen.append(v)
        label = c.get("label")
        if "label" in c and (not isinstance(label, str) or _CHOICE_TEXT_BAD.search(label)):
            problems.append(f"{name}: the label of the choice {v!r} must be text without \"|\", "
                            f"\" = \" or a line break")
    if not any(_same(p.get("default"), s) for s in seen):
        problems.append(f"{name}: default {p.get('default')!r} is not one of its choices")


def _check_used_when(params: list, problems: list[str]) -> None:
    by = {p["name"]: p for p in params if isinstance(p, dict) and isinstance(p.get("name"), str)}
    edges: dict[str, list[str]] = {}
    for name, p in by.items():
        if "used_when" not in p:
            continue
        uw = p["used_when"]
        if not isinstance(uw, dict) or not uw:
            problems.append(f"{name}: used_when must name at least one choice or on/off parameter "
                            f"and its value(s)")
            continue
        edges[name] = []
        for other, want in uw.items():
            q = by.get(other)
            if other == name:
                problems.append(f"{name}: used_when names the parameter itself")
            elif q is None:
                problems.append(f"{name}: used_when names {other!r}, which is not a parameter")
            elif q.get("type") not in ("choice", "bool"):
                problems.append(f"{name}: used_when names {other!r}, which is not a choice or "
                                f"on/off parameter")
            else:
                edges[name].append(other)
                wants = want if isinstance(want, list) else [want]
                if not wants:
                    problems.append(f"{name}: used_when gives {other} no value")
                for w in wants:
                    if check_value(q, w) is not None:
                        problems.append(f"{name}: used_when: {other} has no value {w!r}")
    # A condition may not go round in a circle (A only when B, B only when A).
    state: dict[str, int] = {}

    def visit(n: str, path: list[str]) -> None:
        state[n] = 1
        for m in edges.get(n, []):
            if state.get(m) == 1:
                loop = path[path.index(m):] + [m] if m in path else [n, m]
                problems.append(f"{loop[0]}: used_when goes round in a circle ({' -> '.join(loop)})")
            elif m not in state:
                visit(m, path + [m])
        state[n] = 2
    for n in edges:
        if n not in state:
            visit(n, [n])


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
        typ = p.get("type") if isinstance(p.get("type"), str) else None
        keys = set(_KEYS.get(typ, _PARAM_KEYS)) | (set(_OPTIONAL_KEYS) & set(p))
        for k in sorted(keys ^ set(p)):
            problems.append(f"{where}: {'missing' if k not in p else 'unknown'} field \"{k}\"")
        if not isinstance(name, str) or not _NAME_RE.match(name):
            problems.append(f"{where}: name must be a plain identifier (letters, digits, _)")
            continue
        if name in names:
            problems.append(f"{name}: duplicate name")
        names.append(name)
        if typ not in _KEYS:
            problems.append(f"{name}: type must be \"int\", \"float\", \"choice\" or \"bool\"")
        if typ in ("choice", "bool"):
            if typ == "choice":
                _check_choices(name, p, problems)
            elif not isinstance(p.get("default"), bool):
                problems.append(f"{name}: default must be true or false")
            for k in ("label", "unit", "db_unit", "db_description", "group"):
                if k in p and not isinstance(p[k], str):
                    problems.append(f"{name}: {k} must be text")
            continue
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
    _check_used_when(params, problems)
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
    """``{name: {"type", "min", "max"}}`` -- the web app's preview check
    (a choice: ``{"type", "choices"}``, an on/off parameter: ``{"type"}``)."""
    def one(p):
        if p["type"] == "choice":
            return {"type": "choice", "choices": choice_values(p)}
        if p["type"] == "bool":
            return {"type": "bool"}
        return {"type": p["type"], "min": p["min"], "max": p["max"]}
    return {p["name"]: one(p) for p in (spec or load())["parameters"]}


def slider_groups(spec: dict | None = None) -> list[dict]:
    """The slider page's groups, in the shape ``web/app.js`` uses
    (``PARAM_GROUPS``): page label, diagram, and each slider in page order."""
    spec = spec or load()
    by_name = {p["name"]: p for p in spec["parameters"]}
    def control(p):
        if p["type"] == "choice":
            out = {"key": p["name"], "label": p["label"], "unit": p["unit"], "type": "choice",
                   "choices": [{"value": c["value"], "label": c["label"]} for c in p["choices"]],
                   "value": p["default"]}
        elif p["type"] == "bool":
            out = {"key": p["name"], "label": p["label"], "unit": p["unit"], "type": "bool",
                   "value": p["default"]}
        else:
            out = {"key": p["name"], "label": p["label"], "unit": p["unit"],
                   "min": p["min"], "max": p["max"], "step": p["step"], "value": p["default"]}
        if "used_when" in p:
            out["usedWhen"] = p["used_when"]
        return out
    return [{
        "key": g["id"], "label": g["label"], "image": g["image"],
        "imageAlt": g["image_alt"],
        "params": [control(by_name[n]) for n in g["order"]],
    } for g in spec["groups"]]


def page_payload(spec: dict | None = None) -> dict:
    """What ``/pack/parameters.js`` hands the page as ``window.PACK_PARAMETERS``."""
    spec = spec or load()
    return {"names": list(names(spec)), "groups": slider_groups(spec)}


def db_rows(spec: dict | None = None) -> list[dict]:
    """The rows of table ``dc_parameter_schemas`` for these parameters.  A
    choice or on/off parameter's row also carries ``param_type`` and
    ``choices`` (the additive columns of schema v10); its value is stored as
    a number (:func:`to_db`), so its range is 0 .. its last position."""
    def row(p):
        if p["type"] == "choice":
            return {"param_name": p["name"], "min_value": 0, "max_value": len(p["choices"]) - 1,
                    "unit": p["db_unit"], "description": p["db_description"],
                    "param_type": "choice", "choices": choice_values(p)}
        if p["type"] == "bool":
            return {"param_name": p["name"], "min_value": 0, "max_value": 1,
                    "unit": p["db_unit"], "description": p["db_description"],
                    "param_type": "bool", "choices": None}
        return {"param_name": p["name"], "min_value": p["min"], "max_value": p["max"],
                "unit": p["db_unit"], "description": p["db_description"]}
    return [row(p) for p in (spec or load())["parameters"]]


# ---------------------------------------------------------------------------
# Values (MAS-blueprint P6d)
# ---------------------------------------------------------------------------

def by_name(spec: dict | None = None) -> dict[str, dict]:
    return {p["name"]: p for p in (spec or load())["parameters"]}


def all_numbers(spec: dict | None = None) -> bool:
    """True when every parameter is a number: the setups whose readers keep
    today's words ("a number")."""
    return all(p["type"] in ("int", "float") for p in (spec or load())["parameters"])


def choice_values(p: dict) -> list:
    ch = p.get("choices")
    return [c["value"] for c in ch if isinstance(c, dict) and "value" in c] if isinstance(ch, list) else []


def check_value(p: dict, value) -> str | None:
    """Why *value* does not fit the parameter *p*, or None: a number for a
    number, true / false for an on/off parameter, one of its values for a
    choice.  Ranges are not checked here (the inspecting agents judge them)."""
    if p["type"] == "bool":
        return None if isinstance(value, bool) else "must be true or false"
    if p["type"] == "choice":
        values = choice_values(p)
        if any(_same(value, v) for v in values):
            return None
        return "must be one of: " + ", ".join(json.dumps(v) if not isinstance(v, str) else v
                                              for v in values)
    return None if _number(value) else "must be a number"


VALUE_PHRASE = "its value (a number, one of its choices, or true / false)"


def value_phrase(spec: dict | None = None) -> str:
    """How the agents' texts name a parameter's value: "a number" while
    every parameter is one (today's words), :data:`VALUE_PHRASE` otherwise."""
    return "a number" if all_numbers(spec) else VALUE_PHRASE


def wrong_values(record: dict, spec: dict | None = None) -> list[tuple[str, str]]:
    """``[(name, why)]`` for each value of *record* that does not fit its
    parameter, in the parameters' order (names the setup lacks are skipped)."""
    by = by_name(spec)
    out = []
    for name in by:
        if name in record:
            why = check_value(by[name], record[name])
            if why:
                out.append((name, why))
    return out


def wrong_text(wrong: list[tuple[str, str]]) -> str:
    return "; ".join(f"{name} {why}" for name, why in wrong)


def to_db(p: dict, value) -> float:
    """*value* as the database stores it: a number as itself, on/off as
    1 / 0, a choice as its position in the parameter's list."""
    if p["type"] == "bool":
        return 1.0 if value else 0.0
    if p["type"] == "choice":
        return float(next(i for i, v in enumerate(choice_values(p)) if _same(v, value)))
    return float(value)


def is_used(p: dict, values: dict) -> bool:
    """Whether *p* matters for the *values* (its ``used_when`` holds)."""
    for other, want in (p.get("used_when") or {}).items():
        wants = want if isinstance(want, list) else [want]
        if not any(_same(values.get(other), w) for w in wants):
            return False
    return True


def _shown(v) -> str:
    return json.dumps(v) if isinstance(v, bool) else str(v)


def values_text(p: dict) -> str:
    """What a choice or on/off parameter's list entry ends with: its values
    with their labels (``hose = Hose connector | mag = Magnetic flange``),
    or ``true | false``; "" for a number."""
    if p["type"] == "choice":
        return " | ".join(f"{_shown(c['value'])} = {c['label']}" for c in p["choices"])
    if p["type"] == "bool":
        return "true | false"
    return ""


def used_when_text(p: dict) -> str:
    """`` (only when End1_Style = mag or flange, and Barbs = true)`` -- the
    end of a list entry whose parameter has ``used_when``; "" otherwise."""
    uw = p.get("used_when") or {}
    if not uw:
        return ""
    parts = [f"{other} = " + " or ".join(_shown(w) for w in (want if isinstance(want, list) else [want]))
             for other, want in uw.items()]
    return " (only when " + ", and ".join(parts) + ")"


def entry_problem(p: dict, entry: str) -> str | None:
    """Why a hand-written list entry (its lines, joined) disagrees with *p*
    beyond its range, or None: it must hold :func:`values_text` and
    :func:`used_when_text` as they are (line breaks and runs of spaces
    aside).  Always None for a number without ``used_when``."""
    flat = " ".join(entry.split())
    problems = []
    for what, text in (("list", values_text(p)), ("say", used_when_text(p).strip())):
        text = " ".join(text.split())
        if text and text not in flat:
            problems.append(f'does not {what} "{text}", as parameters.json has it')
    return "; ".join(problems) or None
