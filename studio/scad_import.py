"""A tool from an OpenSCAD model (MAS-blueprint P6f): the server's side,
without the engine.

**Reading** (:func:`read`).  OpenSCAD's Customizer shows a model's
settings: the top-level assignments of a plain value -- a number, a text,
true / false, a list of them -- above the first ``module`` or
``function``, in the tabs of ``/* [Group] */`` comments (``[Hidden]`` is
not shown).  The comment lines just above a setting describe it; the
comment after it on its line is its control: ``// [a, b: B]`` a drop-down
(values, each with an optional label), ``// [10]`` / ``// [0:10]`` /
``// [0:0.5:10]`` a slider (max; min:max; min:step:max), ``// 0.1`` a
step.  Each setting becomes a row, proposed as:

* a **parameter** -- a number (``int`` when its step and default are
  whole), a choice, an on/off setting; a drop-down of evenly spaced numbers
  is a number; a pair ``[mm, inch]`` (its description says "(mm, inch)")
  is one ``<Name>_mm`` parameter, its inch part 0; another list of numbers
  is a parameter per number (``_x`` / ``_y`` / ``_z``).  A number without a
  slider gets a PROPOSED range, marked ``"range": "proposed"`` for the
  owner to review: half to double its default, rounded out to its step;
  0 to ten steps from a default of 0.  A setting of a tab "<Base> - <Sub>"
  is proposed as used only when a choice of tab <Base> has the one value
  whose label starts with <Sub>'s first word ("Connector 1 - Flange": only
  when End1_Style = flange).
* **detail** -- ``fa`` / ``fs`` / ``fn`` (or ``$fa`` ...): the tool's
  ``detail`` (``engine/backends/openscad.py``), the model's own values for
  the Download buttons, coarser for the agents' runs (quicker).
* left to **the model** -- text, colours and other lists, and the tab
  "other": never given, so the model keeps its own value.  A number, a
  choice or an on/off setting may be left to the model too.

**Importing** (:class:`Importer`), one of two ways, chosen each time:

* **new** -- start a new configurator: ``parameters.json`` becomes the
  picked parameters (a group per tab), each agent's parameter list is
  written new (:func:`studio.params_edit.fresh_list`), the setup's
  generators and geometry tools go, the model comes in as a generator and
  a geometry tool (each with its own copy of the model file), the Download
  buttons use the new geometry tool and the picture samples are one set,
  the defaults (``pack.yaml``); the setup's browser preview (``preview/``),
  which draws the old model, goes, so the Parameters page offers its Preview
  button.  The texts stay, for the owner to adapt.
* **add** -- one more tool: its parameters are added (a name the setup has
  already is refused), each list gets their entries (as a parameter save
  does), every picture sample their defaults; the model comes in as the
  generator if the setup has none, else as a geometry tool.

All of it is checked first on a copy of the setup by the engine's check of
a whole setup (its parameters, its tools); **Undo the import** puts every
file it touched back, byte for byte (a removed tool's folder, and the
preview, are kept aside whole until then).
"""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path

import yaml

from studio import params_edit, primer_edit, yaml_patch
from studio.editing import EditError
from studio.tools_edit import MANIFEST, TOOL_RE, UPLOAD_MAX, ToolsEditor

_GROUP_RE = re.compile(r"^\s*/\*\s*\[\s*(.*?)\s*\]\s*\*/")
_STOP_RE = re.compile(r"^\s*(module|function)\b")
_SETTING_RE = re.compile(r"^\s*(\$?[A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)\s*(.*)$")
_COMMENT_RE = re.compile(r"^\s*//(.*)$")
_INCLUDE_RE = re.compile(r"^\s*(?:include|use)\s*<([^>]*)>")
_NUMBER_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_UNIT_RE = re.compile(r"\((mm|cm|m|in|inch|inches|deg|degrees|°|%)\)", re.I)
_UNITS = {"in": "inch", "inches": "inch", "deg": "degrees", "°": "degrees"}
_PAIR_RE = re.compile(r"\s*\(\s*mm\s*,\s*inch(?:es)?\s*\)", re.I)
_ESCAPES = {'"': '"', "\\": "\\", "n": "\n", "t": "\t", "r": "\r"}
DETAIL = ("fa", "fs", "fn")        # the model's detail settings, with or without $
AXES = ("x", "y", "z")
MODEL_TABS_LEFT = ("other",)       # tabs left to the model by default
# The agents' runs: coarser than the model's own detail (quicker).
_COARSE = {"fa": lambda v: max(v, 6), "fs": lambda v: max(v, 1), "fn": lambda v: v if v == 0 else min(v, 24)}
PICKS = ("parameter", "detail", "model")
MODES = ("new", "add")
PREVIEW = "preview"                # the setup's browser preview (engine/pack.py)
_PREVIEW_HELD = "_preview"         # its place in an import's hold (no tool name starts with _)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _clean(x):
    """A number as the files keep it: a whole number an int."""
    if isinstance(x, Decimal):
        return int(x) if x == x.to_integral_value() else float(str(x.normalize()))
    return int(x) if float(x).is_integer() else float(x)


def _dec(x) -> Decimal:
    return Decimal(repr(float(x)))


def _decimals(*values) -> int:
    return max(max(0, -_dec(v).normalize().as_tuple().exponent) for v in values)


# ---------------------------------------------------------------------------
# reading the Customizer
# ---------------------------------------------------------------------------

class _Unreadable(ValueError):
    """Not a plain value (an expression): not a Customizer setting."""


def _statement(rhs: str) -> tuple[str, str] | None:
    """(value, the rest of the line) of an assignment's right side, up to
    its ``;`` outside texts and brackets; None when it does not end there."""
    depth, quoted, i = 0, False, 0
    while i < len(rhs):
        c = rhs[i]
        if quoted:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                quoted = False
        elif c == '"':
            quoted = True
        elif c in "[(":
            depth += 1
        elif c in "])":
            depth -= 1
        elif c == ";" and depth == 0:
            return rhs[:i], rhs[i + 1:]
        elif rhs.startswith("//", i):
            return None
        i += 1
    return None


def _string(text: str, pos: int) -> tuple[str, int]:
    """The text starting with the quote at *pos*, its escapes read; and
    where it ends."""
    out, i = [], pos + 1
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            n = text[i + 1]
            hexes = {"u": 4, "x": 2}.get(n, 0)
            if hexes and re.fullmatch(r"[0-9a-fA-F]+", text[i + 2:i + 2 + hexes] or "-"):
                out.append(chr(int(text[i + 2:i + 2 + hexes], 16)))
                i += 2 + hexes
                continue
            out.append(_ESCAPES.get(n, n))
            i += 2
            continue
        if c == '"':
            return "".join(out), i + 1
        out.append(c)
        i += 1
    raise _Unreadable(text)


def literal(text: str):
    """The plain value *text* writes -- a number, a text, true / false, a
    list of them; raises _Unreadable for anything else (an expression)."""
    pos = 0

    def space():
        nonlocal pos
        while pos < len(text) and text[pos] in " \t":
            pos += 1

    def value():
        nonlocal pos
        space()
        if pos >= len(text):
            raise _Unreadable(text)
        if text[pos] == '"':
            out, pos = _string(text, pos)
            return out
        if text[pos] == "[":
            pos += 1
            items = []
            space()
            while pos < len(text) and text[pos] != "]":
                items.append(value())
                space()
                if pos < len(text) and text[pos] == ",":
                    pos += 1
                    space()
                elif pos >= len(text) or text[pos] != "]":
                    raise _Unreadable(text)
            if pos >= len(text):
                raise _Unreadable(text)
            pos += 1
            return items
        for word, v in (("true", True), ("false", False)):
            if text.startswith(word, pos):          # "truex" fails at the next character
                pos += len(word)
                return v
        m = _NUMBER_RE.match(text, pos)
        if m is None:
            raise _Unreadable(text)
        pos = m.end()
        s = m.group()
        return float(s) if any(ch in s for ch in ".eE") else int(s)

    v = value()
    space()
    if pos != len(text):
        raise _Unreadable(text)
    return v


def _items(inner: str) -> list[tuple[object, str | None, bool]]:
    """A drop-down's items: (value text, label or None, quoted)."""
    parts, cur, quoted, i = [], "", False, 0
    while i < len(inner):
        c = inner[i]
        if c == "\\" and quoted and i + 1 < len(inner):
            cur += inner[i:i + 2]
            i += 2
            continue
        if c == '"':
            quoted = not quoted
        if c == "," and not quoted:
            parts.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    parts.append(cur)
    out = []
    for part in (p.strip() for p in parts):
        if not part:
            continue
        # value:label, the colon outside the quotes
        q, cut = False, None
        for j, c in enumerate(part):
            if c == '"':
                q = not q
            elif c == ":" and not q:
                cut = j
                break
        value, label = (part, None) if cut is None else (part[:cut].strip(), part[cut + 1:].strip())
        isq = len(value) >= 2 and value[0] == value[-1] == '"'
        if isq:
            value = _string(value, 0)[0]
        if label is not None and len(label) >= 2 and label[0] == label[-1] == '"':
            label = _string(label, 0)[0]
        out.append((value, label or None, isq))
    return out


def _control(comment: str, default) -> tuple[str, object] | None:
    """What the comment after a setting makes of it: ``("choices", items)``,
    ``("slider", (min, step or None, max))``, ``("step", s)``,
    ``("text", comment)`` -- or None."""
    c = comment.strip()
    if not c:
        return None
    numeric = _is_number(default) or (isinstance(default, list) and bool(default)
                                      and all(_is_number(x) for x in default))
    if c.startswith("[") and c.endswith("]"):
        inner = c[1:-1]
        bits = [b.strip() for b in inner.split(":")]
        if numeric and "," not in inner and 1 <= len(bits) <= 3 and all(
                _NUMBER_RE.fullmatch(b) for b in bits):
            nums = [literal(b) for b in bits]
            if len(nums) == 1:
                return "slider", (0, None, nums[0])
            if len(nums) == 2:
                return "slider", (nums[0], None, nums[1])
            return "slider", (nums[0], nums[1], nums[2])
        try:
            items = _items(inner)
        except _Unreadable:
            items = []
        return ("choices", items) if items else ("text", c)
    if _NUMBER_RE.fullmatch(c):
        return ("step", literal(c)) if numeric else None
    return "text", c


def _kind(value, control, desc: str) -> str:
    if isinstance(value, bool):
        return "bool"
    choices = control is not None and control[0] == "choices"
    if _is_number(value):
        return "choice" if choices else "number"
    if isinstance(value, str):
        return "choice" if choices else "text"
    if value and all(_is_number(x) for x in value):
        return "pair" if len(value) == 2 and _PAIR_RE.search(desc) else "vector"
    return "list"


def _control_text(control) -> str:
    if control is None:
        return ""
    what, x = control
    if what == "choices":
        return f"drop-down ({len(x)})"
    if what == "slider":
        lo, step, hi = x
        return f"slider {lo}..{hi}" + (f" step {step}" if step is not None else "")
    if what == "step":
        return f"step {x}"
    return ""


def _scan(text: str) -> tuple[list[dict], list[str], list[str]]:
    """(the settings, notes, included files) of a model's Customizer."""
    rows: dict[str, dict] = {}
    notes, includes, above = [], [], []
    group, hidden = "Parameters", False
    for n, line in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        if _STOP_RE.match(line):
            break
        g = _GROUP_RE.match(line)
        if g:
            group = g.group(1) or "Parameters"
            hidden, above = group.lower() == "hidden", []
            continue
        inc = _INCLUDE_RE.match(line)
        if inc:
            includes.append(inc.group(1).strip())
            above = []
            continue
        c = _COMMENT_RE.match(line)
        if c:
            above.append(c.group(1).strip())
            continue
        s = _SETTING_RE.match(line)
        desc, above = " ".join(x for x in above if x), []
        if s is None or hidden:
            continue
        name, rhs = s.groups()
        if name.startswith("$") and name[1:] not in DETAIL:
            continue                     # OpenSCAD's own variables are no settings
        st = _statement(rhs)
        if st is None:
            notes.append(f"{name} (line {n}): not read -- its value does not end on its line.")
            continue
        try:
            value = literal(st[0].strip())
        except _Unreadable:
            continue                     # an expression: not a Customizer setting
        rest = st[1].strip()
        control = _control(rest[2:], value) if rest.startswith("//") else None
        if control is not None and control[0] == "text":
            desc = desc or control[1]
            control = None
        desc = re.sub(r"(?<!\.)\.$", "", desc.strip())     # its closing full stop (not "...")
        if name in rows:
            notes.append(f"{name} is set twice; the last one counts (as in OpenSCAD).")
            del rows[name]
        rows[name] = {"setting": name, "group": group, "line": n, "description": desc,
                      "default": value, "kind": _kind(value, control, desc), "control": control}
    return list(rows.values()), notes, includes


# ---------------------------------------------------------------------------
# the proposals
# ---------------------------------------------------------------------------

def proposed_range(default, step) -> tuple:
    """Half to double *default*, rounded out to *step*; 0 to ten steps
    from 0."""
    d, s = _dec(default), _dec(step)
    if d > 0:
        lo, hi = d / 2, d * 2
    elif d < 0:
        lo, hi = d * 2, d / 2
    else:
        lo, hi = Decimal(0), s * 10
    lo = (lo / s).to_integral_value(ROUND_FLOOR) * s
    hi = (hi / s).to_integral_value(ROUND_CEILING) * s
    return _clean(lo), _clean(hi)


def _unit(desc: str) -> str:
    m = _UNIT_RE.search(desc)
    if not m:
        return ""
    u = m.group(1).lower() if m.group(1) != "°" else "°"
    return _UNITS.get(u, u)


def _number(name, default, step, rng, label, desc, unit) -> dict:
    """A number parameter: *rng* (min, max) from the model, else proposed."""
    proposed = rng is None
    lo, hi = proposed_range(default, step) if proposed else rng
    whole = all(float(x).is_integer() for x in (default, step, lo, hi))
    p = {"name": name, "type": "int" if whole else "float", "min": _clean(lo), "max": _clean(hi),
         "step": _clean(step)}
    if proposed:
        p["range"] = "proposed"
    p.update({"default": _clean(default), "label": label, "unit": unit, "db_unit": unit,
              "db_description": desc or label})
    return p


_LABEL_BAD = re.compile(r"[|\n\r]| = ")


def _choice(row: dict, label: str, desc: str) -> tuple[dict | None, str | None]:
    """(the parameter of a drop-down, or None and why not)."""
    default, items = row["default"], row["control"][1]
    values = []
    for text, lab, quoted in items:
        if _is_number(default):
            if quoted or not _NUMBER_RE.fullmatch(str(text)):
                return None, "its drop-down holds a value that is not a number"
            v = literal(str(text))
        else:
            v = text if isinstance(text, str) else str(text)
        if any(v == x and isinstance(v, bool) == isinstance(x, bool) for x, _l in values):
            continue
        values.append((v, lab))
    if _is_number(default) and len(values) >= 2 and all(lab is None or lab == str(v) for v, lab in values):
        nums = [v for v, _l in values]
        diffs = {_dec(b) - _dec(a) for a, b in zip(nums, nums[1:])}
        if len(diffs) == 1 and next(iter(diffs)) > 0 and nums[0] <= default <= nums[-1]:
            # evenly spaced numbers: a number, its range the model's
            step = next(iter(diffs))
            return _number(row["setting"], default, _clean(step), (nums[0], nums[-1]), label, desc,
                           _unit(desc)), None
    if len(values) < 2:
        return None, "its drop-down has fewer than two values"
    if not any(v == default for v, _l in values):
        return None, f"its default {default!r} is not one of its drop-down's values"
    choices = []
    for v, lab in values:
        if isinstance(v, str) and (not v.strip() or _LABEL_BAD.search(v)):
            return None, f"its value {v!r} cannot be a choice (empty, or with |, \" = \" or a line break)"
        lab = lab if lab is not None else str(v)
        choices.append({"value": v, "label": _LABEL_BAD.sub(lambda m: "/" if m.group() == "|" else " - ", lab)})
    return {"name": row["setting"], "type": "choice", "choices": choices, "default": default,
            "label": label, "unit": "", "db_unit": "", "db_description": desc or label}, None


def _parameters(row: dict, taken: set[str]) -> tuple[list[dict] | None, str | None]:
    """The parameters *row* would make (no group, no used_when yet), or
    (None, why it cannot be one)."""
    name, kind, desc, default = row["setting"], row["kind"], row["description"], row["default"]
    label = name.replace("_", " ")
    control = row["control"]
    step = control[1] if control and control[0] == "step" else None
    if kind == "bool":
        return [{"name": name, "type": "bool", "default": default, "label": label, "unit": "",
                 "db_unit": "", "db_description": desc or label}], None
    if kind == "choice":
        p, why = _choice(row, label, desc)
        return ([p], None) if p else (None, why)
    if kind == "number":
        rng = None
        if control and control[0] == "slider":
            lo, sstep, hi = control[1]
            step = sstep
            if lo < hi:
                rng = (min(lo, default), max(hi, default))
        step = step or 10 ** -_decimals(default, *(rng or ()))
        return [_number(name, default, step, rng, label, desc, _unit(desc))], None
    if kind in ("pair", "vector"):
        step = step or 10 ** -_decimals(*default)
        if kind == "pair":
            mm, inch = default
            base = _PAIR_RE.sub("", desc).strip()
            value = mm if mm or not inch else _clean(round(_dec(inch) * Decimal("25.4") / _dec(step)) * _dec(step))
            return [_number(_unique(f"{name}_mm", taken), value, step, None, f"{label} (mm)",
                            base, "mm")], None
        axes = AXES if len(default) <= 3 else [str(i + 1) for i in range(len(default))]
        return [_number(_unique(f"{name}_{a}", taken), v, step, None, f"{label} {a}",
                        f"{desc} ({a})" if desc else "", _unit(desc))
                for a, v in zip(axes, default)], None
    return None, None


def _unique(name: str, taken: set[str]) -> str:
    out, n = name, 2
    while out in taken:
        out, n = f"{name}_{n}", n + 1
    taken.add(out)
    return out


def _whens(rows: list[dict]) -> dict[str, dict]:
    """``{setting: {choice: value}}``: a setting of tab "<Base> - <Sub>" is
    used only when a choice of tab <Base> (a parameter) has the one value
    whose label starts with <Sub>'s first word -- when exactly one choice
    of <Base> has such a value."""
    by_tab: dict[str, list[dict]] = {}
    for r in rows:
        by_tab.setdefault(r["group"].strip().lower(), []).append(r)
    out = {}
    for r in rows:
        base, sep, sub = r["group"].partition(" - ")
        words = sub.split()
        if not sep or not words or r["pick"] != "parameter":
            continue
        first, hits = words[0].lower(), []
        for c in by_tab.get(base.strip().lower(), []):
            ps = c.get("parameters") or []
            if c["pick"] != "parameter" or len(ps) != 1 or ps[0]["type"] != "choice":
                continue
            match = [ch["value"] for ch in ps[0]["choices"]
                     if ch["label"].split()[:1] and ch["label"].split()[0].lower() == first]
            if len(match) == 1:
                hits.append((ps[0]["name"], match[0]))
        if len(hits) == 1:
            out[r["setting"]] = {hits[0][0]: hits[0][1]}
    return out


def read(text: str) -> dict:
    """The model's Customizer settings as rows, each with its proposal:
    ``pick`` (parameter / detail / model), the ``picks`` it may take, the
    ``parameters`` it would make, ``when`` (its proposed used_when)."""
    rows, notes, includes = _scan(text)
    taken = {r["setting"] for r in rows}
    for r in rows:
        bare = r["setting"].lstrip("$")
        params, why = (None, None) if r["setting"].startswith("$") else _parameters(r, taken)
        r["control"] = _control_text(r["control"])
        r["parameters"] = params or []
        r["note"] = why
        if bare in DETAIL and _is_number(r["default"]):
            r["pick"], r["picks"] = "detail", ["detail", "model"]
        elif not params:
            r["pick"], r["picks"] = "model", ["model"]
        else:
            r["pick"] = "model" if r["group"].strip().lower() in MODEL_TABS_LEFT else "parameter"
            r["picks"] = ["parameter", "model"]
    whens = _whens(rows)
    for r in rows:
        r["when"] = whens.get(r["setting"])
    kinds = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    made = [p for r in rows if r["pick"] == "parameter" for p in r["parameters"]]
    return {"rows": rows, "notes": notes, "includes": includes,
            "groups": list(dict.fromkeys(r["group"] for r in rows)),
            "counts": {"settings": len(rows), **kinds, "parameters": len(made),
                       "proposed": sum(1 for p in made if p.get("range") == "proposed")}}


def apply_picks(found: dict, picks: dict | None, when: dict | None) -> list[dict]:
    """The rows with the owner's *picks* (``{setting: pick}``) and *when*
    (``{setting: false}`` drops a proposed used_when) laid over."""
    rows = [dict(r) for r in found["rows"]]
    by = {r["setting"]: r for r in rows}
    for k, v in (picks or {}).items():
        if k not in by:
            raise EditError(f"The model has no setting {k!r}.")
        if v not in by[k]["picks"]:
            raise EditError(f"{k} cannot be {v!r} (it can be: {', '.join(by[k]['picks'])}).")
        by[k]["pick"] = v
    whens = _whens(rows)
    off = {k for k, v in (when or {}).items() if v is False}
    for r in rows:
        r["when"] = None if r["setting"] in off else whens.get(r["setting"])
    return rows


def _slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return s if s and s[0].isalpha() else f"group_{s}" if s else "group"


def assemble(rows: list[dict], taken_groups=()) -> tuple[list[dict], list[dict], dict, dict]:
    """(parameters, groups, parts, detail) of the picked rows: a group per
    tab (its id new beside *taken_groups*), the parameters group by group
    in the model's order."""
    ids, groups, params = {}, {}, {}
    used = set(taken_groups)
    for r in rows:
        if r["pick"] != "parameter":
            continue
        tab = r["group"]
        if tab not in ids:
            ids[tab] = _unique(_slug(tab), used)
            groups[tab] = {"id": ids[tab], "label": tab, "image": "", "image_alt": "", "order": []}
            params[tab] = []
        for p in r["parameters"]:
            q = dict(p, group=ids[tab])
            if r.get("when"):
                q["used_when"] = r["when"]
            params[tab].append(q)
            groups[tab]["order"].append(q["name"])
    parts = {}
    for r in rows:
        if r["pick"] == "parameter" and r["kind"] in ("pair", "vector"):
            names = [p["name"] for p in r["parameters"]]
            parts[r["setting"]] = [names[0], 0] if r["kind"] == "pair" else names
    download = {r["setting"]: r["default"] for r in rows if r["pick"] == "detail"}
    detail = {}
    if download:
        detail = {"agent": {k: _COARSE[k.lstrip("$")](v) for k, v in download.items()},
                  "download": download}
    return ([params_edit.normalise({"groups": [], "parameters": [p]})["parameters"][0]
             for tab in params for p in params[tab]], list(groups.values()), parts, detail)


# ---------------------------------------------------------------------------
# the tool's files
# ---------------------------------------------------------------------------

def tool_name(model: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", Path(model).stem.lower()).strip("_")
    return (s if s and s[0].isalpha() else f"model_{s}".rstrip("_"))[:48]


def display_name(model: str) -> str:
    s = " ".join(re.sub(r"[-_]+", " ", Path(model).stem).split())
    return (s[:1].upper() + s[1:])[:60] or "Model"


def model_file(filename: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(str(filename or "model.scad")).name).strip("-.")
    s = s if s and s[0].isalnum() else f"model{s}"
    return s[:-5] + ".scad" if s.lower().endswith(".scad") else s + ".scad"


_IMAGES = [{"view": "isometric", "file": "render_isometric.png", "order": 10, "default_enabled": True,
            "compression": "3d_render", "label": "Render view: isometric"},
           {"view": "top", "file": "render_top.png", "order": 20, "default_enabled": True,
            "compression": "3d_render", "label": "Render view: top"},
           {"view": "side", "file": "render_side.png", "order": 40, "default_enabled": False,
            "compression": "3d_render", "label": "Render view: side"}]


def _y(v) -> str:
    return yaml_patch.inline(v)


def _backend_lines(model: str, parts: dict, detail: dict) -> list[str]:
    out = ["# The model the engine runs (engine/backends/openscad.py): each parameter",
           "# goes to the model's setting of the same name; parts puts several",
           "# parameters into one setting; every other setting keeps the model's own value.",
           "backend: openscad", f"model: {_y(model)}"]
    if parts:
        out += ["parts:"] + [f"  {_y(k)}: {_y(v)}" for k, v in parts.items()]
    if detail:
        out += ["# The model's detail: its own for the Download buttons, coarser for the",
                "# agents' runs (quicker).",
                "detail:"] + [f"  {k}: {_y(v)}" for k, v in detail.items()]
    return out


# The settings an imported tool gets (Workflow Settings > Tools): OpenSCAD's
# engine, and -- a generator's -- the mesh checks, off (engine/backends/openscad.py).
ENGINE_SETTING = {"name": "openscad_engine", "type": "enum", "values": ["manifold", "cgal"],
                  "default": "manifold", "label": "OpenSCAD engine",
                  "description": ("Manifold = OpenSCAD's newer engine, fast; CGAL = its original one, "
                                  "much slower.  Neither removes the slivers a model's own shapes may leave.")}
CHECKS_SETTING = {"name": "mesh_checks", "type": "bool", "default": False, "label": "Mesh quality checks",
                  "description": ("ON = the render step also reports watertightness, volume and "
                                  "degenerate faces; OFF = only the renders, and the agents judge visually.")}


def _settings_lines(specs: list[dict]) -> list[str]:
    out = ["", "settings:"]
    for s in specs:
        out.append(f"  - name: {s['name']}")
        out += [f"    {k}: {_y(s[k])}" for k in ("type", "values", "default", "label", "description") if k in s]
    return out


def generator_files(name: str, display: str, model: str, source: bytes, parts: dict,
                    detail: dict, list_order: int) -> tuple[dict[str, bytes], dict]:
    """A generator's folder (its manifest, its model, its tool-list entry)."""
    want = {"name": name, "display_name": display, "kind": "generator", "roles": ["tool_runner"],
            "backend": "openscad", "model": model, **({"parts": parts} if parts else {}),
            **({"detail": detail} if detail else {}),
            "description": (
                f"Build the {display} model from an attempt's own ``parameters.json``\n"
                f"with OpenSCAD, save it to that attempt's ``{name}.obj``, THEN render it\n"
                "(three views: isometric, top, side) and, when Mesh quality checks is on, check\n"
                "it, all in one call.\n"
                f"If the folder already holds ``{name}.obj``, that model is reused.\n"
                "Returns the model's path and size and anything OpenSCAD said (its\n"
                "ECHO, WARNING and ERROR lines), then the render report; if OpenSCAD\n"
                "fails, an ``Error:`` message and no pictures."),
            "args": {"parameters_path": (
                "Absolute path of the attempt's ``parameters.json``: the model and its\n"
                "pictures are written into that file's own attempt folder.")},
            "outputs": {"model_file": f"{name}.obj", "model_format": "obj", "up_axis": "z",
                        "images": _IMAGES},
            "fill_on_save": True, "list_order": list_order,
            "settings": [ENGINE_SETTING, CHECKS_SETTING]}
    lines = [f"# {display}: a generator made by the Studio from the OpenSCAD model",
             f"# {model}.  It builds the model from an attempt's",
             "# parameters.json, then the engine's renderer makes its pictures.",
             f"name: {name}", f"display_name: {_y(display)}", "kind: generator",
             "roles: [tool_runner]"]
    lines += _backend_lines(model, parts, detail)
    lines += ["", "description: " + yaml_patch.literal(want["description"], 2),
              "args:", "  parameters_path: " + yaml_patch.literal(want["args"]["parameters_path"], 4),
              "", "outputs:", f"  model_file: {name}.obj", "  model_format: obj", "  up_axis: z",
              "  images:"] + [f"    - {_y(i)}" for i in _IMAGES]
    lines += ["", "# May the save step use this tool to add a missing picture to an attempt it",
              "# archives?", "fill_on_save: true", "",
              "# Its place in the tool runner's numbered tool list (its entry is",
              "# prompts/tool_list_entry.md).", f"list_order: {list_order}"]
    lines += _settings_lines(want["settings"])
    entry = (f"**{name}** — build ``{name}.obj`` into an attempt\n"
             "   folder with OpenSCAD from that attempt's own ``parameters.json`` (pass\n"
             "   ONLY that file's path — the tool reads the values and writes beside\n"
             "   them) AND, as its final step, render the three views (isometric / top /\n"
             "   side).  Returns the model path, anything OpenSCAD said and the\n"
             "   render+check report.\n")
    return {MANIFEST: _manifest(lines, want), model: source,
            "prompts/tool_list_entry.md": entry.encode("utf-8")}, want


def geometry_files(name: str, display: str, model: str, source: bytes, parts: dict,
                   detail: dict, what: str | None = None) -> tuple[dict[str, bytes], dict]:
    """A geometry tool's folder (its manifest, its own copy of the model);
    *what*: the model's name in its description (its display name)."""
    want = {"name": name, "display_name": display, "kind": "geometry", "backend": "openscad",
            "model": model, **({"parts": parts} if parts else {}), **({"detail": detail} if detail else {}),
            "description": f"Builds the {what or display} model from its parameters with OpenSCAD.",
            "outputs": {"model_format": "obj"}, "settings": [ENGINE_SETTING]}
    lines = [f"# {display}: a geometry tool made by the Studio from the OpenSCAD model",
             f"# {model}, with a copy of the model of its own.  It",
             "# builds the model from the parameters for the Download buttons (and a",
             "# generator's geometry tool setting); never for an agent.",
             f"name: {name}", f"display_name: {_y(display)}", "kind: geometry"]
    lines += _backend_lines(model, parts, detail)
    lines += ["", "description: " + _y(want["description"]), "", "outputs:", "  model_format: obj"]
    lines += _settings_lines(want["settings"])
    return {MANIFEST: _manifest(lines, want), model: source}, want


def _manifest(lines: list[str], want: dict) -> bytes:
    text = "\n".join(lines) + "\n"
    if yaml.safe_load(text) != want:
        raise EditError("The tool's manifest could not be written (the Studio's own mistake).")
    return text.encode("utf-8")


# ---------------------------------------------------------------------------
# pack.yaml: the Download buttons and the picture samples
# ---------------------------------------------------------------------------

def _block(lines: list[str], key: str) -> tuple[int, int] | None:
    """(first, end) of top-level block *key*'s own lines -- its header and
    its indented lines, not the blank lines after them."""
    head = re.compile(rf"^{re.escape(key)}:\s*(#.*)?$")
    for i, ln in enumerate(lines):
        if head.match(ln):
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j][:1].isspace()):
                j += 1
            while j > i + 1 and not lines[j - 1].strip():
                j -= 1
            return i, j
    return None


_SAMPLE_RE = re.compile(r"^(\s+)([^\s:#][^:#]*):\s*\{(.*)\}\s*$")


def pack_yaml(text: str, mode: str, defaults: dict, geometry: str | None) -> str:
    """pack.yaml (LF) after the import: the picture samples -- one set, the
    defaults (new), or every set with the new parameters' defaults (add) --
    the Download buttons' geometry tool (new), and no agent given the
    primer, which still shows the old configurator (new)."""
    data = yaml.safe_load(text) or {}
    want = copy.deepcopy(data)
    lines = text.split("\n")
    span = _block(lines, "render_samples")
    sets = data.get("render_samples")
    if mode == "new":
        want["render_samples"] = {"default": dict(defaults)}
        body = [f"  default: {_y(defaults)}"]
        if span is not None:
            lines[span[0] + 1:span[1]] = body
        elif "render_samples" not in data:
            while lines and not lines[-1].strip():
                lines.pop()
            lines += ["", "render_samples:"] + body + [""]
    elif isinstance(sets, dict) and sets:
        want["render_samples"] = {k: {**(v or {}), **defaults} for k, v in sets.items()}
        add = _y(defaults)[1:-1]
        if span is not None:
            for i in range(span[0] + 1, span[1]):
                m = _SAMPLE_RE.match(lines[i])
                if m:
                    close = lines[i].rindex("}")
                    lines[i] = lines[i][:close] + (", " if m.group(3).strip() else "") + add + lines[i][close:]
    out = "\n".join(lines)
    if mode == "new":
        sec = primer_edit.effective(out)
        sec["agents"] = {t: [] for t in primer_edit.TOPOLOGIES}
        out = primer_edit.write_section(out, sec, None)
        want["primer"] = sec
    if geometry is not None:
        want.setdefault("downloads", {})
        if not isinstance(want["downloads"], dict):
            want["downloads"] = {}
        want["downloads"]["geometry_tool"] = geometry
    try:
        if yaml.safe_load(out) != want:
            out = yaml_patch.patch(out, want)
    except (yaml.YAMLError, yaml_patch.PatchError) as exc:
        raise EditError(f"pack.yaml could not be updated in its own layout ({exc}): change its "
                        "render_samples and downloads by hand, then import again.") from None
    return out


# ---------------------------------------------------------------------------
# the import
# ---------------------------------------------------------------------------

class Importer:
    """Imports into the setup in *pack_dir* (*opened_dir*: as the Studio
    opened it); *check_setup(dir)* is the engine's check of a whole setup
    copy (``-> problems``); the parameter and tool editors' locks are held
    while it writes.  Each import can be undone, the last first."""

    def __init__(self, pack_dir: Path, opened_dir: Path, check_setup,
                 params: params_edit.ParamsEditor, tools: ToolsEditor):
        self.pack_dir, self.opened_dir, self.check_setup = pack_dir, opened_dir, check_setup
        self.params, self.tools = params, tools
        self.records: list[dict] = []
        self._hold = Path(tempfile.mkdtemp(prefix="studio_import_"))
        self._lock = threading.Lock()

    def close(self) -> None:
        shutil.rmtree(self._hold, ignore_errors=True)

    # -- what the page reads -------------------------------------------------

    def state(self) -> dict | None:
        """The last import, while it can be undone."""
        if not self.records:
            return None
        r = self.records[-1]
        return {k: r[k] for k in ("mode", "model", "added", "removed", "preview", "parameters")}

    def forget(self) -> None:
        """The setup was replaced: no import can be undone any more."""
        with self._lock:
            self.records = []
            for p in self._hold.iterdir():
                shutil.rmtree(p, ignore_errors=True)

    def _manifests(self) -> dict[str, dict]:
        out = {}
        for t in self.tools.tools(self.pack_dir):
            m, _err = self.tools._manifest_of(self.pack_dir, t)
            out[t] = m if isinstance(m, dict) else {}
        return out

    def setup(self) -> dict:
        """What each way would do here: the tools a new configurator
        replaces, and what one more tool becomes."""
        ms = self._manifests()
        kinds = {t: m.get("kind") for t, m in ms.items()}
        try:
            pack = yaml.safe_load((self.pack_dir / "pack.yaml").read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            pack = {}
        _raw, spec = self.params._spec(self.pack_dir)
        return {"generators": sorted(t for t, k in kinds.items() if k == "generator"),
                "geometry": sorted(t for t, k in kinds.items() if k == "geometry"),
                "helpers": sorted(t for t, k in kinds.items() if k not in ("generator", "geometry")),
                "downloads": (pack.get("downloads") or {}).get("geometry_tool"),
                "parameters": [p["name"] for p in spec["parameters"]],
                "preview": (self.pack_dir / PREVIEW).is_dir(),
                "add_as": "geometry" if "generator" in kinds.values() else "generator"}

    @staticmethod
    def _decode(b64, filename) -> tuple[str, bytes, str]:
        try:
            raw = base64.b64decode(str(b64), validate=True)
        except (binascii.Error, ValueError):
            raise EditError("The file did not arrive whole.") from None
        if len(raw) > UPLOAD_MAX:
            raise EditError(f"The file is {len(raw) / 1048576:.1f} MB; the limit is 20 MB.")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise EditError("The file is not text (UTF-8): an OpenSCAD model (.scad) is.") from None
        return text, raw, model_file(filename)

    def read(self, data: dict, b64, filename=None) -> dict:
        """The model's settings and their proposals, for the dialog."""
        text, _raw, model = self._decode(b64, filename)
        found = read(text)
        if not found["rows"]:
            raise EditError(f"{model} has no settings OpenSCAD's Customizer would show (plain values "
                            "assigned above its first module or function).")
        return {**found, "model": model, "name": tool_name(model), "display": display_name(model),
                "setup": self.setup(), "warnings": []}

    # -- the import ----------------------------------------------------------

    def _names(self, mode: str, name, display, model: str, gone: set[str]) -> tuple[str, str]:
        name = str(name or tool_name(model)).strip()
        display = str(display or display_name(model)).strip()
        if not TOOL_RE.match(name) or len(name) > 54:
            raise EditError("The tool's name must be lower case: letters, digits and _, starting with "
                            "a letter (at most 54 characters).")
        if not display or len(display) > 50 or any(ord(c) < 32 for c in display):
            raise EditError("Give the tool a display name (one line, at most 50 characters).")
        now = set(self.tools.tools(self.pack_dir))
        for n in ([name, f"{name}_geometry"] if mode == "new" else [name]):
            if n == "downloads":
                raise EditError("downloads is reserved (the Download buttons' settings).")
            if n in now - gone:
                raise EditError(f"The setup already has a tool {n}: choose another name.")
            if n not in now and (self.opened_dir / "tools" / n).exists():
                raise EditError(f"A tool {n} was removed since the Studio opened: put it back with its "
                                "Undo, or choose another name.")
        return name, display

    def _stage_check(self, files: dict[str, bytes], gone: list[str], preview: bool) -> list[str]:
        tmp = Path(tempfile.mkdtemp(prefix="studio_importcheck_"))
        try:
            copy = tmp / self.pack_dir.name
            shutil.copytree(self.pack_dir, copy,
                            ignore=shutil.ignore_patterns("__pycache__", "node_modules", "assets"))
            for t in gone:
                shutil.rmtree(copy / "tools" / t, ignore_errors=True)
            if preview:
                shutil.rmtree(copy / PREVIEW, ignore_errors=True)
            for rel, raw in files.items():
                p = copy / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(raw)
            return list(self.check_setup(copy))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _list_order(self, gone: set[str]) -> int:
        taken = {m.get("list_order") for t, m in self._manifests().items() if t not in gone}
        return 20 if 20 not in taken else max(x for x in taken if isinstance(x, int)) + 10

    def run(self, data: dict, b64, filename=None, mode=None, picks=None, when=None,
            name=None, display=None) -> dict:
        """Import the model *mode* ("new" or "add") with the owner's picks."""
        if mode not in MODES:
            raise EditError("Choose how to import: start a new configurator, or add it as one more tool.")
        text, source, model = self._decode(b64, filename)
        found = read(text)
        rows = apply_picks(found, picks if isinstance(picks, dict) else None,
                           when if isinstance(when, dict) else None)
        with self._lock, self.params._lock, self.tools._lock:
            ms = self._manifests()
            raw, cur = self.params._spec(self.pack_dir)
            eol = params_edit.eol_of(raw)
            gone = sorted(t for t, m in ms.items() if m.get("kind") in ("generator", "geometry")) \
                if mode == "new" else []
            # the old model's browser preview: it would draw it from parameters that are gone
            preview = mode == "new" and (self.pack_dir / PREVIEW).is_dir()
            name, display = self._names(mode, name, display, model, set(gone))
            params, groups, parts, detail = assemble(
                rows, () if mode == "new" else [g["id"] for g in cur["groups"]])
            if not params:
                raise EditError("Pick at least one setting as a parameter: the agents need something "
                                "to set.")
            defaults = {p["name"]: p["default"] for p in params}
            files: dict[str, bytes] = {}
            lists: list[str] = []
            if mode == "new":
                spec = params_edit.normalise({"groups": groups, "parameters": params})
                files["parameters.json"] = params_edit.format_spec(spec, eol)
                for rel in self.params.list_files(data):
                    p = self.pack_dir / rel
                    if p.is_file():
                        old = p.read_bytes()
                        new = params_edit.fresh_list(spec, old.decode("utf-8").replace("\r\n", "\n"))
                        files[rel] = new.replace("\n", params_edit.eol_of(old)).encode("utf-8")
                        lists.append(rel)
                gen, geo = name, f"{name}_geometry"
                made, _ = generator_files(gen, display, model, source, parts, detail,
                                          self._list_order(set(gone)))
                files.update({f"tools/{gen}/{k}": v for k, v in made.items()})
                made, _ = geometry_files(geo, f"{display} geometry", model, source, parts, detail, display)
                files.update({f"tools/{geo}/{k}": v for k, v in made.items()})
                added, download = [gen, geo], geo
            else:
                clash = [p["name"] for p in params if p["name"] in {q["name"] for q in cur["parameters"]}]
                if clash:
                    raise EditError("The setup has parameters of these names already: rename them "
                                    "there, leave these settings to the model, or start a new "
                                    "configurator.", clash)
                want = {**cur, "groups": cur["groups"] + groups, "parameters": cur["parameters"] + params}
                _raw, _cur, new, _ren, planned = self.params._plan(data, want, params_edit.sha(raw), {})
                files["parameters.json"] = params_edit.format_spec(new, eol)
                for rel, (_a, b) in planned.items():
                    old = (self.pack_dir / rel).read_bytes()
                    files[rel] = b.replace("\n", params_edit.eol_of(old)).encode("utf-8")
                    lists.append(rel)
                as_generator = not any(m.get("kind") == "generator" for m in ms.values())
                made, _ = (generator_files(name, display, model, source, parts, detail,
                                           self._list_order(set()))
                           if as_generator else geometry_files(name, display, model, source, parts, detail))
                files.update({f"tools/{name}/{k}": v for k, v in made.items()})
                added, download = [name], None
            ypath = self.pack_dir / "pack.yaml"
            yraw = ypath.read_bytes()
            ytext = pack_yaml(yraw.decode("utf-8").replace("\r\n", "\n"), mode, defaults, download)
            files["pack.yaml"] = ytext.replace("\n", params_edit.eol_of(yraw)).encode("utf-8")
            problems = self._stage_check(files, gone, preview)
            if problems:
                raise EditError("The import cannot be made: the engine refuses the result.", problems)
            # write it, keeping what it replaces
            hold = self._hold / str(len(self.records) + 1)
            shutil.rmtree(hold, ignore_errors=True)
            hold.mkdir(parents=True)
            before = {rel: ((self.pack_dir / rel).read_bytes() if (self.pack_dir / rel).is_file() else None)
                      for rel in files if not rel.startswith("tools/")}
            for t in gone:
                shutil.move(str(self.pack_dir / "tools" / t), str(hold / t))
            if preview:
                shutil.move(str(self.pack_dir / PREVIEW), str(hold / _PREVIEW_HELD))
            for rel, b in files.items():
                p = self.pack_dir / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b)
            record = {"mode": mode, "model": model, "added": added, "removed": gone, "preview": preview,
                      "hold": str(hold),
                      # the parameter editor's renames since opening: Undo puts them back
                      "before": before, "since_opened": dict(self.params.since_opened),
                      "parameters": len(params)}
            record["after"] = self._fingerprint(record)
            self.records.append(record)
        return {"mode": mode, "added": added, "removed": gone, "preview": preview, "parameters": len(params),
                "proposed": sum(1 for p in params if p.get("range") == "proposed"),
                "lists": lists, "database": True,
                "warnings": self._warnings(mode, found, gone, ms, len(params), params)}

    def _warnings(self, mode, found, gone, ms, n, params) -> list[str]:
        out = []
        proposed = sum(1 for p in params if p.get("range") == "proposed")
        if proposed:
            out.append(f"{proposed} of the {n} parameters have a proposed range (half to double the "
                       "model's default, or 0 to ten steps when it is 0): review them under Parameters; "
                       "Validate warns until then.")
        if mode == "new":
            helpers = sorted(t for t, m in ms.items() if t not in gone)
            if helpers:
                out.append("These tools stay: " + ", ".join(helpers) + ".  If one belongs to the old "
                           "configurator, remove it under Tools.")
            out.append("The texts stay as they were: adapt them to the new model (Prompt texts).")
            out.append("No agent gets the primer now: its picture and text still show the old "
                       "configurator.  Give it this model's on the Primer page, then tick the agents "
                       "that should get it.")
        if found["includes"]:
            out.append("The model uses other files (" + ", ".join(found["includes"]) + "): only the "
                       "model file was copied; add them to the tool's folder (Upload file).")
        out += found["notes"]
        if not (os.getenv("OPENSCAD_PATH") or "").strip() and not shutil.which("openscad"):
            out.append("OpenSCAD is not on this computer: Test tool and Validate will say so until it "
                       "is (install it, or set OPENSCAD_PATH).")
        from engine.setups import settings_file
        f = (settings_file(self.tools.repo, self.pack_dir, "tool_settings.json")
             if self.tools.repo else None)
        try:
            overrides = json.loads(f.read_text(encoding="utf-8")) if f and f.is_file() else {}
        except (OSError, ValueError):
            overrides = {}
        named = sorted({t for t in gone if t in overrides or any(
            isinstance(v, dict) and t in v.values() for v in overrides.values())})
        if named:
            out.append("Workflow Settings on this computer still mention " + ", ".join(named)
                       + ": change them there.")
        return out

    # -- Undo ----------------------------------------------------------------

    def _fingerprint(self, record: dict) -> dict[str, str | None]:
        """What the import left: each file it wrote, each tool it added (its
        files), each name of a tool it removed and the preview it put aside
        (absent)."""
        out = {}
        for rel in record["before"]:
            p = self.pack_dir / rel
            out[rel] = _sha(p.read_bytes()) if p.is_file() else None
        for t in record["added"]:
            files = self.tools.files(self.pack_dir / "tools" / t)
            out[f"tools/{t}/"] = _sha(json.dumps({k: _sha(v.read_bytes()) for k, v in files.items()},
                                                 sort_keys=True).encode()) if files else None
        for t in record["removed"]:
            if t not in record["added"]:
                out[f"tools/{t}/"] = "there" if (self.pack_dir / "tools" / t).exists() else None
        if record["preview"]:
            out[f"{PREVIEW}/"] = "there" if (self.pack_dir / PREVIEW).exists() else None
        return out

    def undo(self, data: dict, force=False) -> dict:
        """The last import undone: every file it wrote back as it was, the
        tools it added gone, the ones it removed back, the preview too.  Anything changed
        since the import is named first (*force* undoes it anyway)."""
        with self._lock, self.params._lock, self.tools._lock:
            if not self.records:
                raise EditError("There is no import to undo.")
            rec = self.records[-1]
            lost = [t for t in rec["removed"] if not (Path(rec["hold"]) / t).is_dir()]
            if rec["preview"] and not (Path(rec["hold"]) / _PREVIEW_HELD).is_dir():
                lost.append(f"{PREVIEW}/")
            if lost:
                raise EditError("The import cannot be undone: what it removed is no longer kept "
                                "(" + ", ".join(lost) + ").  Use each tool's Undo instead.")
            now = self._fingerprint(rec)
            changed = sorted(k for k, v in rec["after"].items() if now.get(k) != v)
            if changed and force is not True:
                raise EditError("These changed since the import; undoing it puts them back as they "
                                "were before it too:", changed)
            for t in rec["added"]:
                shutil.rmtree(self.pack_dir / "tools" / t, ignore_errors=True)
            for t in rec["removed"]:
                shutil.rmtree(self.pack_dir / "tools" / t, ignore_errors=True)
                shutil.move(str(Path(rec["hold"]) / t), str(self.pack_dir / "tools" / t))
            if rec["preview"]:
                shutil.rmtree(self.pack_dir / PREVIEW, ignore_errors=True)
                shutil.move(str(Path(rec["hold"]) / _PREVIEW_HELD), str(self.pack_dir / PREVIEW))
            for rel, raw in rec["before"].items():
                p = self.pack_dir / rel
                if raw is None:
                    if p.is_file():
                        p.unlink()
                elif not p.is_file() or p.read_bytes() != raw:
                    p.write_bytes(raw)
            self.params.since_opened = rec["since_opened"]
            self.records.pop()
            shutil.rmtree(rec["hold"], ignore_errors=True)
            return {"undone": {k: rec[k] for k in ("mode", "model", "added", "removed", "preview")},
                    "warnings": []}
