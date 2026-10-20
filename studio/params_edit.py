"""Editing a setup's parameters and agent access (MAS-blueprint P6b): the
server's side, without the engine.

* ``parameters.json`` is written in its own layout -- one line per group and
  per parameter, the file's line endings, characters as they are
  (:func:`format_spec` reproduces today's file byte for byte), so a change
  touches only the lines it should.  The engine's own validator checks a
  new file first (``engine/parameters.py``, run in an engine process by the
  server).
* The agents' parameter LISTS (the files of ``$parameter_list``: the shared
  text and every agent's copy) are hand-written, one numbered entry per
  parameter -- `` 1. bladeCount   (integer)   — Number of blades [3; 6]``.
  :func:`update_list` keeps one in step with a new parameter file: a
  changed name or ``[min; max]`` is rewritten in place, a removed
  parameter's entry goes, a new one gets an entry in the list's own
  columns, the entries follow the file's order and are renumbered.  Each
  list's own wording is kept.  A choice or on/off parameter's entry ends
  with its values (``: hose = Hose connector | mag = Magnetic flange``,
  ``: true | false``) and any parameter's with its ``(only when ...)``
  (MAS-blueprint P6d); an entry whose values or type change is written
  again in the list's shape, its own description kept.  An entry whose parameter is back as it was
  when the Studio opened gets its OPENED lines back, at its opened place,
  so a change and its Undo leave the list byte for byte as it was.
* The agent-access grid is a block of ``pack.yaml``; :func:`set_access`
  rewrites one agent's line in the block's own alignment.
"""

from __future__ import annotations

import csv
import difflib
import hashlib
import io
import json
import re
import threading
from decimal import Decimal
from pathlib import Path

# A number's keys; a choice's and an on/off parameter's are the same less
# min / max / step, a choice with "choices" (MAS-blueprint P6d).
PARAM_KEYS = ("name", "type", "min", "max", "step", "choices", "default", "group",
              "label", "unit", "db_unit", "db_description", "used_when")
GROUP_KEYS = ("id", "label", "image", "image_alt", "order")
LIST_SLOT = "parameter_list"

# An entry of a parameter list, and its range: the drift check's own shapes
# (extra_utilities/tests/smoke_test_parameters.py).
ENTRY_RE = re.compile(r"^(\s*)(\d+)\.(\s+)([A-Za-z_][A-Za-z0-9_]*)\b")
RANGE_RE = re.compile(r"\[\s*(-?[\d.]+)\s*;\s*(-?[\d.]+)\s*\]")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def num(v) -> str:
    """A number as the files write it: ``6``, ``0.3``, never ``6.0`` or an exponent."""
    f = float(v)
    if f.is_integer():
        return str(int(f))
    s = repr(f)
    return format(Decimal(s), "f") if "e" in s or "E" in s else s


# ---------------------------------------------------------------------------
# parameters.json
# ---------------------------------------------------------------------------

def normalise(spec: dict) -> dict:
    """*spec* with each object's keys in the file's order (unknown keys
    last, for the validator to name)."""
    def order(d: dict, keys) -> dict:
        return {**{k: d[k] for k in keys if k in d}, **{k: v for k, v in d.items() if k not in keys}}
    out = {"groups": [order(g, GROUP_KEYS) if isinstance(g, dict) else g for g in spec.get("groups", [])],
           "parameters": [order(p, PARAM_KEYS) if isinstance(p, dict) else p
                          for p in spec.get("parameters", [])]}
    if "retired" in spec:
        out["retired"] = spec["retired"]
    for k, v in spec.items():
        if k not in out:
            out[k] = v
    return out


def format_spec(spec: dict, eol: str = "\r\n") -> bytes:
    """The file's layout: one line per group, per parameter, the retired list."""
    d = (lambda o: json.dumps(o, ensure_ascii=False))
    out = ["{", '  "groups": [']
    gs, ps = spec["groups"], spec["parameters"]
    out += ["    " + d(g) + ("," if i < len(gs) - 1 else "") for i, g in enumerate(gs)]
    out += ["  ],", '  "parameters": [']
    out += ["    " + d(p) + ("," if i < len(ps) - 1 else "") for i, p in enumerate(ps)]
    rest = [k for k in spec if k not in ("groups", "parameters")]
    out += ["  ]" + ("," if rest else "")]
    for i, k in enumerate(rest):
        out += [f"  {d(k)}: {d(spec[k])}" + ("," if i < len(rest) - 1 else "")]
    out += ["}"]
    return (eol.join(out) + eol).encode("utf-8")


def eol_of(raw: bytes) -> str:
    return "\r\n" if b"\r\n" in raw else "\n"


def retire(cur: dict, new: dict, opened: dict) -> dict:
    """*new* with ``retired`` kept right: a name that is a parameter again
    leaves it; a parameter of the setup AS OPENED that *new* drops joins it
    (an old record carrying it is then read without it).  A parameter added
    and removed since the Studio opened never joins."""
    if not isinstance(new.get("retired", []), list) or not isinstance(new.get("parameters"), list):
        return normalise(new)               # the validator names the problem
    names = [p.get("name") for p in new.get("parameters", []) if isinstance(p, dict)]
    opened_names = {p["name"] for p in opened.get("parameters", [])} | set(opened.get("retired", []))
    retired = [n for n in new.get("retired", cur.get("retired", [])) if n not in names]
    for p in cur.get("parameters", []):
        n = p["name"]
        if n not in names and n in opened_names and n not in retired:
            retired.append(n)
    out = dict(new)
    if retired or "retired" in new or "retired" in cur:
        out["retired"] = retired
    return normalise(out)


def changes(cur: dict, new: dict, renames: dict) -> dict:
    """What *new* changes in *cur*: parameters added / removed / renamed,
    fields changed, the order, groups, retired names."""
    cp = {p["name"]: p for p in cur["parameters"]}
    np_ = {p["name"]: p for p in new["parameters"]}
    inv = {v: k for k, v in renames.items()}
    added = [n for n in np_ if n not in cp and n not in inv]
    removed = [n for n in cp if n not in np_ and n not in renames]
    fields = {}
    for n, p in np_.items():
        old = cp.get(inv.get(n, n))
        if old is None:
            continue
        diff = {k: [old.get(k), p.get(k)] for k in PARAM_KEYS if k != "name" and old.get(k) != p.get(k)}
        if diff:
            fields[n] = diff
    cg = {g["id"]: g for g in cur["groups"]}
    ng = {g["id"]: g for g in new["groups"]}
    groups = {"added": [g for g in ng if g not in cg], "removed": [g for g in cg if g not in ng],
              "changed": {g: {k: [cg[g].get(k), ng[g].get(k)] for k in GROUP_KEYS
                              if k != "id" and cg[g].get(k) != ng[g].get(k)}
                          for g in ng if g in cg and cg[g] != ng[g]},
              "order": [g for g in cg if g in ng] != [g for g in ng if g in cg]}
    kept_old = [inv.get(n, n) for n in np_ if inv.get(n, n) in cp]
    return {"added": added, "removed": removed, "renamed": dict(renames), "fields": fields,
            "order": [n for n in cp if n in kept_old] != kept_old, "groups": groups,
            "retired": [n for n in new.get("retired", []) if n not in cur.get("retired", [])]}


def range_changes(cur: dict, new: dict, renames: dict) -> bool:
    """Names, types, ranges or a choice's values changed: the database needs
    a new schema."""
    key = (lambda s: [(p["name"], p["type"], p.get("min"), p.get("max"),
                       [c.get("value") for c in p.get("choices") or []]) for p in s["parameters"]])
    return key(cur) != key(new) or bool(renames)


# ---------------------------------------------------------------------------
# the parameter lists
# ---------------------------------------------------------------------------

def parse_entries(lines: list[str]) -> list[tuple[int, int, str]]:
    """``[(start, end, name)]``: an entry runs from its numbered line over the
    lines that continue it -- not blank, not a heading, not another entry
    (the drift check's own rule)."""
    out, i = [], 0
    while i < len(lines):
        m = ENTRY_RE.match(lines[i])
        if not m:
            i += 1
            continue
        j = i + 1
        while (j < len(lines) and lines[j].strip() and not lines[j].lstrip().startswith("#")
               and not ENTRY_RE.match(lines[j])):
            j += 1
        out.append((i, j, m.group(4)))
        i = j
    return out


def _entry_state(lines: list[str]):
    """(name, min, max) as the entry writes them (min/max None without a range)."""
    name = ENTRY_RE.match(lines[0]).group(4)
    last = None
    for ln in lines:
        for m in RANGE_RE.finditer(ln):
            last = m
    return (name, float(last.group(1)), float(last.group(2))) if last else (name, None, None)


def retarget(lines: list[str], name: str, lo, hi) -> list[str]:
    """The entry with *name* and ``[lo; hi]``: the name is replaced in place
    (the column after it kept), each bound only where its value differs."""
    lines = list(lines)
    m = ENTRY_RE.match(lines[0])
    old = m.group(4)
    if old != name:
        head, rest = lines[0][:m.start(4)], lines[0][m.end(4):]
        pad = len(rest) - len(rest.lstrip(" "))
        if pad:
            lines[0] = head + name + " " * max(1, len(old) + pad - len(name)) + rest[pad:]
        else:
            lines[0] = head + name + rest
    where = None
    for i, ln in enumerate(lines):
        for r in RANGE_RE.finditer(ln):
            where = (i, r)
    if where is not None:
        i, r = where
        ln = lines[i]
        out = ln[:r.start(1)]
        out += r.group(1) if float(r.group(1)) == float(lo) else num(lo)
        out += ln[r.end(1):r.start(2)]
        out += r.group(2) if float(r.group(2)) == float(hi) else num(hi)
        lines[i] = out + ln[r.end(2):]
    return lines


def _plain(lines: list[str]) -> list[str]:
    """The entry with its number blanked (for comparing entries)."""
    return [ENTRY_RE.sub(lambda m: m.group(1) + "#." + m.group(3) + m.group(4), lines[0])] + lines[1:]


def _columns(lines: list[str], entries) -> tuple[int, int, int, bool] | None:
    """The list's own shape, from its first entry: (name column, "("
    column, column of what follows the parenthesis, whether entries carry
    a "— description").  Some lists write only the range after it."""
    for s, _e, _n in entries:
        ln = lines[s]
        m = ENTRY_RE.match(ln)
        p, d, b = ln.find("(", m.end(4)), ln.find("—", m.end(4)), ln.find("[", m.end(4))
        if 0 < p < d:
            return m.start(4), p, d, True
        if 0 < p < b:
            return m.start(4), p, b, False
    return None


# The words of a choice's or an on/off parameter's entry -- engine/parameters.py
# values_text / used_when_text, word for word (smoke_test_studio compares
# them); the Studio's server does not load the engine.
_TYPE_WORDS = {"choice": "choice", "bool": "on/off"}


def _typed(p: dict) -> bool:
    return p.get("type") in _TYPE_WORDS


def _shown(v) -> str:
    return json.dumps(v) if isinstance(v, bool) else str(v)


def values_text(p: dict) -> str:
    """``hose = Hose connector | mag = Magnetic flange``, ``true | false``, or ""."""
    if p.get("type") == "choice":
        return " | ".join(f"{_shown(c['value'])} = {c['label']}" for c in p["choices"])
    if p.get("type") == "bool":
        return "true | false"
    return ""


def used_when_text(p: dict) -> str:
    """`` (only when End1_Style = mag or flange, and Barbs = true)``, or ""."""
    uw = p.get("used_when") or {}
    if not uw:
        return ""
    parts = [f"{other} = " + " or ".join(_shown(w) for w in (want if isinstance(want, list) else [want]))
             for other, want in uw.items()]
    return " (only when " + ", and ".join(parts) + ")"


_WHEN_RE = re.compile(r"\s*\(only when .*\)\s*$")


def fresh_entry(p: dict, cols, desc: str | None = None) -> list[str]:
    """A new parameter's entry, in the list's own columns and shape
    (renumbered later); *desc* in place of its database description."""
    typed = _typed(p)
    parts = (([p["unit"]] if p.get("unit") else [])
             + (["integer"] if p["type"] == "int" else [_TYPE_WORDS[p["type"]]] if typed else []))
    paren = "(" + (", ".join(parts) if parts else "unitless") + ")"
    desc = desc or p.get("db_description") or p.get("label") or p["name"]
    rng = values_text(p) if typed else f"[{num(p['min'])}; {num(p['max'])}]"
    sep = ": " if typed else " "
    when = used_when_text(p)
    if cols is None:
        return [f" 1. {p['name']} {paren} — {desc}{sep}{rng}{when}"]
    c_name, c_paren, c_next, described = cols
    head = " 1. ".rjust(c_name) if c_name >= 4 else " 1. "
    name = p["name"].ljust(c_paren - c_name) if len(p["name"]) < c_paren - c_name else p["name"] + " "
    paren = paren.ljust(c_next - c_paren) if len(paren) < c_next - c_paren else paren + " "
    return [head + name + paren + (f"— {desc}{sep}{rng}" if described else rng) + when]


def _description(lines: list[str]) -> str | None:
    """The entry's own description: after its "—", before its range or its
    values (and its "(only when ...)"); None in a list without them."""
    flat = _WHEN_RE.sub("", " ".join(" ".join(lines).split()))
    if "—" not in flat:
        return None
    desc = flat.split("—", 1)[1]
    m = RANGE_RE.search(desc)
    if m:
        desc = desc[:m.start()]
    elif " | " in desc:
        desc = desc[:desc.index(" | ")].rpartition(": ")[0]
    return desc.strip() or None


def _set_when(lines: list[str], when: str) -> list[str]:
    """The entry ending with *when* (``" (only when ...)"`` or nothing)."""
    out = [_WHEN_RE.sub("", ln) for ln in lines]
    if when:
        out[-1] = out[-1].rstrip() + when
    return out if out != lines else lines


def fit(lines: list[str], p: dict, cols) -> list[str]:
    """The entry *lines* made to say *p*.  A number keeps its lines, its
    name and range rewritten in place (:func:`retarget`); a choice's or an
    on/off parameter's keeps them while they hold its values, else it is
    written again in the list's shape (:func:`fresh_entry`) with its own
    description -- so is an entry whose parameter changes between a number
    and a choice / on/off.  Either ends with its "(only when ...)"."""
    flat = " ".join(" ".join(lines).split())
    if _typed(p):
        if RANGE_RE.search(_WHEN_RE.sub("", flat)) or " ".join(values_text(p).split()) not in flat:
            return fresh_entry(p, cols, _description(lines))
        return _set_when(retarget(lines, p["name"], None, None), used_when_text(p))
    if not RANGE_RE.search(flat):
        return fresh_entry(p, cols, _description(lines))
    return _set_when(retarget(lines, p["name"], p["min"], p["max"]), used_when_text(p))


def _lis(seq: list[int]) -> set[int]:
    """Indexes (into *seq*) of a longest increasing subsequence."""
    import bisect
    tails, tails_i, prev = [], [], [-1] * len(seq)
    for i, v in enumerate(seq):
        k = bisect.bisect_left(tails, v)
        if k == len(tails):
            tails.append(v)
            tails_i.append(i)
        else:
            tails[k], tails_i[k] = v, i
        prev[i] = tails_i[k - 1] if k else -1
    out, i = set(), tails_i[-1] if tails_i else -1
    while i >= 0:
        out.add(i)
        i = prev[i]
    return out


def update_list(text: str, new: dict, renames: dict | None = None,
                opened_text: str | None = None) -> str:
    """The parameter list *text* (LF) kept in step with the parameter file
    *new*.  *renames*: ``{old: new}`` names renamed by this change.
    *opened_text*: the same list as the Studio opened it -- an entry that
    has only had this module's updates since then is rebuilt from its
    opened lines, and a parameter coming back is put back at its opened
    place."""
    renames = renames or {}
    lines = text.split("\n")
    entries = parse_entries(lines)
    params = {p["name"]: p for p in new["parameters"]}
    order = [p["name"] for p in new["parameters"]]
    rank = {n: i for i, n in enumerate(order)}
    cols = _columns(lines, entries)

    olines = opened_text.split("\n") if opened_text is not None else []
    oentries = parse_entries(olines)
    oblock = {n: olines[s:e] for s, e, n in oentries}
    oneigh = {}
    for k, (s, e, n) in enumerate(oentries):
        prev = oentries[k - 1] if k else None
        nxt = oentries[k + 1] if k + 1 < len(oentries) else None
        oneigh[n] = (prev[2] if prev and prev[1] == s else None,
                     nxt[2] if nxt and nxt[0] == e else None)

    def block(name: str, cur: list[str] | None) -> list[str]:
        p = params[name]
        o = oblock.get(name)
        if o is not None:
            if cur is None:
                return fit(o, p, cols)
            st = _entry_state(cur)
            if st[1] is not None and _plain(retarget(o, *st)) == _plain(cur):
                return fit(o, p, cols)
        if cur is None:
            return fresh_entry(p, cols)
        return fit(cur, p, cols)

    # the list as items: a plain line, or an entry (by its NEW name)
    items: list = []
    pos = 0
    for s, e, n in entries:
        items += [("line", ln) for ln in lines[pos:s]]
        new_name = renames.get(n, n)
        if new_name in params and not any(it[0] == "entry" and it[1] == new_name for it in items):
            items.append(("entry", new_name, lines[s:e]))
        pos = e
    items += [("line", ln) for ln in lines[pos:]]
    # entries that stay where they are: the longest run already in the new order
    placed = [it for it in items if it[0] == "entry"]
    keep = _lis([rank[it[1]] for it in placed])
    moved = {placed[i][1]: placed[i][2] for i in range(len(placed)) if i not in keep}
    items = [it for it in items if not (it[0] == "entry" and it[1] in moved)]
    items = [("entry", it[1], block(it[1], it[2])) if it[0] == "entry" else it for it in items]
    # the moved and the new, in the file's order
    for name in order:
        at = {it[1]: i for i, it in enumerate(items) if it[0] == "entry"}
        if name in at:
            continue
        lines_ = block(name, moved.get(name))
        i = rank[name]
        before = order[i - 1] if i else None
        after = next((n for n in order[i + 1:] if n in at), None)
        op, on = oneigh.get(name, (None, None))
        if name in oblock and op is not None and op == before and before in at:
            k = at[before] + 1
        elif name in oblock and on is not None and on == after and after in at:
            k = at[after]
        elif before is not None and before in at:
            k = at[before] + 1
        elif after is not None:
            k = at[after]
        else:
            k = len(items)
        items.insert(k, ("entry", name, lines_))
    # renumber, keeping each number's width
    out, n = [], 0
    for it in items:
        if it[0] == "line":
            out.append(it[1])
            continue
        n += 1
        first = it[2][0]
        m = ENTRY_RE.match(first)
        field = m.group(1) + m.group(2)
        out.append(str(n).rjust(len(field)) + first[m.end(2):])
        out += it[2][1:]
    return "\n".join(out)


def compose_renames(since_opened: dict, renames: dict) -> dict:
    """``{opened name: name now}`` after *renames* (``{name now: new name}``)."""
    out = {o: renames.get(c, c) for o, c in since_opened.items()}
    for c, n in renames.items():
        if c not in since_opened.values() and c not in out:
            out[c] = n
    return {o: n for o, n in out.items() if o != n}


def step_list(text: str, opened_text: str, cur: dict, new: dict,
              since_opened: dict, renames: dict) -> str:
    """One change to a parameter list.  While the list has had only these
    updates since the Studio opened (it equals the opened list brought to
    *cur*), it is rebuilt from the opened list -- so the result depends on
    the parameters alone, and putting them back gives the opened bytes.  A
    list edited by hand meanwhile is updated where it stands."""
    if update_list(opened_text, cur, since_opened, opened_text) == text:
        return update_list(opened_text, new, compose_renames(since_opened, renames), opened_text)
    return update_list(text, new, renames, opened_text)


def list_diff(old: str, new: str) -> list[list[str]]:
    """Changed lines with one line around them: ``[[op, line], ...]``, a
    ``["…", ""]`` between hunks."""
    a, b = old.split("\n"), new.split("\n")
    out: list[list[str]] = []
    for grp in difflib.SequenceMatcher(None, a, b, autojunk=False).get_grouped_opcodes(1):
        if out:
            out.append(["…", ""])
        for op, i1, i2, j1, j2 in grp:
            if op == "equal":
                out += [["=", ln] for ln in a[i1:i2]]
            else:
                out += [["-", ln] for ln in a[i1:i2]] + [["+", ln] for ln in b[j1:j2]]
    return out


# ---------------------------------------------------------------------------
# Paste CSV
# ---------------------------------------------------------------------------

CSV_COLUMNS = {"name": "name", "type": "type", "min": "min", "max": "max", "step": "step",
               "default": "default", "unit": "unit", "label": "label", "group": "group",
               "description": "db_description", "db_description": "db_description",
               "db_unit": "db_unit", "choices": "choices"}
_CSV_TYPES = {"integer": "int", "int": "int", "float": "float", "number": "float",
              "choice": "choice", "on/off": "bool", "onoff": "bool", "bool": "bool", "boolean": "bool"}
_CSV_BOOLS = {"true": True, "on": True, "yes": True, "1": True,
              "false": False, "off": False, "no": False, "0": False}


def _csv_number(text: str):
    v = float(text)
    return int(v) if v.is_integer() else v


def _csv_choices(text: str) -> list[dict]:
    """``hose = Hose connector | mag = Magnetic flange`` (as the agents' lists
    write them): ``[{value, label}]``; a value that reads as a number is one,
    a choice without `` = `` is its own label."""
    out = []
    for item in (s.strip() for s in text.split("|")):
        if not item:
            continue
        value, _sep, label = item.partition(" = ")
        value = value.strip()
        try:
            value = _csv_number(value)
        except ValueError:
            pass
        out.append({"value": value, "label": label.strip() or str(value)})
    return out


def _csv_default(text: str, kind: str, choices: list):
    """(*text* as a default of a *kind* parameter, None) or (None, why not)."""
    if kind == "bool":
        b = _CSV_BOOLS.get(text.lower())
        return (b, None) if b is not None else (None, "is not true or false")
    if kind == "choice":
        for c in choices:
            if _shown(c["value"]) == text:
                return c["value"], None
        return None, "is not one of its choices"
    try:
        return _csv_number(text), None
    except ValueError:
        return None, "is not a number"


def from_csv(text: str, spec: dict) -> tuple[dict, list[str]]:
    """*spec* with the CSV's rows laid over it, matched by name: the header
    names the columns (name, type, min, max, step, default, unit, label,
    group, description, choices -- and db_unit); only those columns change.
    A choice's ``choices`` are written as the agents' lists write them
    (``hose = Hose connector | mag = Magnetic flange``), its type ``choice``,
    an on/off parameter's ``on/off``.  A new name is added after the last
    parameter of its group.  Parameters the CSV does not name stay.
    Returns (new spec, problems)."""
    problems: list[str] = []
    body = text.strip("﻿\r\n ")
    if not body:
        return spec, ["The CSV is empty."]
    first = body.splitlines()[0]
    delim = max(("\t", ";", ","), key=first.count)
    rows = list(csv.reader(io.StringIO(body), delimiter=delim))
    header = [h.strip().lower() for h in rows[0]]
    unknown = [h for h in header if h not in CSV_COLUMNS]
    if unknown:
        problems.append("Unknown column(s): " + ", ".join(unknown) + ".  The columns are: "
                        "name, type, min, max, step, default, unit, label, group, description, "
                        "choices.")
    if "name" not in header:
        problems.append("The header has no \"name\" column.")
    if problems:
        return spec, problems
    out = json.loads(json.dumps(spec))
    by_name = {p["name"]: p for p in out["parameters"]}
    groups = {g["id"]: g for g in out["groups"]}
    labels = {g["label"].strip().lower(): g["id"] for g in out["groups"]}
    for r, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue
        cells = {CSV_COLUMNS[h]: (row[i].strip() if i < len(row) else "") for i, h in enumerate(header)}
        name = cells.pop("name")
        where = f"row {r} ({name or 'no name'})"
        if not name:
            problems.append(f"{where}: no name.")
            continue
        vals: dict = {}
        default = None
        for k, v in cells.items():
            if v == "" and k not in ("unit", "db_unit"):
                continue
            if k in ("min", "max", "step"):
                try:
                    vals[k] = _csv_number(v)
                except ValueError:
                    problems.append(f"{where}: {k} {v!r} is not a number.")
            elif k == "default":
                default = v          # read below, by the parameter's type
            elif k == "type":
                t = v.lower()
                vals[k] = _CSV_TYPES.get(t, t)
            elif k == "choices":
                vals[k] = _csv_choices(v)
            elif k == "group":
                gid = v if v in groups else labels.get(v.lower())
                if gid is None:
                    problems.append(f"{where}: group {v!r} does not exist (add it in the table first).")
                else:
                    vals[k] = gid
            else:
                vals[k] = v
        p = by_name.get(name)
        kind = vals.get("type", p["type"] if p is not None else "float")
        choices = vals.get("choices") or (p or {}).get("choices") or []
        if kind == "choice" and len(choices) < 2:
            problems.append(f"{where}: a choice needs a \"choices\" column: "
                            f"value = label | value = label.")
            continue
        if default is not None:
            got, why = _csv_default(default, kind, choices)
            if why:
                problems.append(f"{where}: default {default!r} {why}.")
            else:
                vals["default"] = got
        if p is not None:
            old_group = p["group"]
            was_typed = _typed(p)
            p.update(vals)
            if _typed(p) or was_typed:
                # The keys of its type (a choice and an on/off parameter
                # have no range; a number has no choices) and a default
                # that fits it.
                for k in (("min", "max", "step") if _typed(p) else ()) + (
                        ("choices",) if p["type"] != "choice" else ()):
                    p.pop(k, None)
                if "default" not in vals:
                    p["default"] = (choices[0]["value"] if p["type"] == "choice" else False
                                    if p["type"] == "bool" else p.get("min", 0))
                if not _typed(p) and ("min" not in p or "max" not in p):
                    problems.append(f"{where}: a number needs min and max.")
                    continue
                if not _typed(p):
                    p.setdefault("step", 1)
            if p["group"] != old_group:
                groups[old_group]["order"].remove(name)
                groups[p["group"]]["order"].append(name)
            continue
        if "group" not in vals:
            problems.append(f"{where}: a new parameter needs a group.")
            continue
        if kind in ("choice", "bool"):
            p = {"name": name, "type": kind, **({"choices": choices} if kind == "choice" else {}),
                 "default": vals.get("default", choices[0]["value"] if kind == "choice" else False),
                 "group": vals["group"], "label": vals.get("label", name), "unit": vals.get("unit", ""),
                 "db_unit": vals.get("db_unit", vals.get("unit", "")),
                 "db_description": vals.get("db_description", vals.get("label", name))}
            last = max((i for i, q in enumerate(out["parameters"]) if q["group"] == p["group"]), default=None)
            out["parameters"].insert(len(out["parameters"]) if last is None else last + 1, p)
            groups[p["group"]]["order"].append(name)
            by_name[name] = p
            continue
        if "min" not in vals or "max" not in vals:
            problems.append(f"{where}: a new parameter needs min and max.")
            continue
        p = {"name": name, "type": vals.get("type", "float"), "min": vals["min"], "max": vals["max"],
             "step": vals.get("step", 1), "default": vals.get("default", vals["min"]),
             "group": vals["group"], "label": vals.get("label", name), "unit": vals.get("unit", ""),
             "db_unit": vals.get("db_unit", vals.get("unit", "")),
             "db_description": vals.get("db_description", vals.get("label", name))}
        last = max((i for i, q in enumerate(out["parameters"]) if q["group"] == p["group"]), default=None)
        out["parameters"].insert(len(out["parameters"]) if last is None else last + 1, p)
        groups[p["group"]]["order"].append(name)
        by_name[name] = p
    return normalise(out), problems


# ---------------------------------------------------------------------------
# where the code names a parameter
# ---------------------------------------------------------------------------

CODE_SUFFIXES = {".py", ".js", ".mjs", ".ts", ".yaml", ".yml", ".json", ".html", ".css"}


def code_uses(pack_dir: Path, names: list[str]) -> dict[str, list[list]]:
    """``{name: [[file, count], ...]}``: the setup's code and configuration
    files (not its text fields, pictures or parameters.json) that name each
    parameter."""
    pats = {n: re.compile(rf"\b{re.escape(n)}\b") for n in names}
    out: dict[str, list[list]] = {n: [] for n in names}
    for p in sorted(pack_dir.rglob("*")):
        rel = p.relative_to(pack_dir).as_posix()
        if (not p.is_file() or p.suffix.lower() not in CODE_SUFFIXES or rel == "parameters.json"
                or "__pycache__" in p.parts or "node_modules" in p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, pat in pats.items():
            c = len(pat.findall(text))
            if c:
                out[n].append([rel, c])
    return out


# ---------------------------------------------------------------------------
# the agent-access grid in pack.yaml
# ---------------------------------------------------------------------------

_ROW_RE = re.compile(r"^(\s+)([a-z_][a-z0-9_]*):(\s*)\{([^}]*)\}(.*)$")
_CELL_RE = re.compile(r"(\d+)\s*:\s*([a-z]+)")


def access_rows(text: str) -> dict[str, tuple[int, dict[str, str]]]:
    """``{agent: (line index, {topology: state})}`` of the ``parameter_access``
    block of pack.yaml (text, LF)."""
    lines = text.split("\n")
    out, inside = {}, False
    for i, ln in enumerate(lines):
        if re.match(r"^parameter_access:\s*(#.*)?$", ln):
            inside = True
            continue
        if inside:
            if ln.strip() and not ln[:1].isspace():
                break
            m = _ROW_RE.match(ln)
            if m:
                out[m.group(2)] = (i, {k: v for k, v in _CELL_RE.findall(m.group(4))})
    return out


def access_line(line: str, cells: dict[str, str]) -> str:
    """The row *line* with *cells* (same topologies, same order), in the
    block's alignment: each value but the last padded to 7 with its comma."""
    m = _ROW_RE.match(line)
    keys = [k for k, _ in _CELL_RE.findall(m.group(4))]
    body = "".join(f"{k}: " + ((cells[k] + ",").ljust(7) if i < len(keys) - 1 else cells[k])
                   for i, k in enumerate(keys))
    return f"{m.group(1)}{m.group(2)}:{m.group(3)}{{{body}}}{m.group(5)}"


def set_access(text: str, agent: str, topology: str, state: str) -> str:
    rows = access_rows(text)
    i, cells = rows[agent]
    lines = text.split("\n")
    lines[i] = access_line(lines[i], {**cells, topology: state})
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# the editor: files, checks, Undo
# ---------------------------------------------------------------------------

class ParamsEditor:
    """Changes to the parameters and the access grid of the setup in
    *pack_dir*; *opened_dir* is its copy as the Studio opened it; *check*
    is the engine's parameter check (``spec -> problems``).  One change at
    a time."""

    PICTURE_MAX = 2 * 1024 * 1024

    def __init__(self, pack_dir: Path, opened_dir: Path, check):
        self.pack_dir, self.opened_dir, self.check = pack_dir, opened_dir, check
        self._lock = threading.Lock()
        # {opened name: name now}: what the lists are rebuilt from (step_list)
        self.since_opened: dict = {}

    # -- files ---------------------------------------------------------------

    def _spec(self, root: Path) -> tuple[bytes, dict]:
        raw = (root / "parameters.json").read_bytes()
        return raw, json.loads(raw.decode("utf-8"))

    def list_files(self, data: dict) -> list[str]:
        """The parameter lists, relative to the setup: the files of
        ``$parameter_list`` -- its shared text and every agent's copy --
        in the setup now or as opened."""
        spec = (data.get("slot_specs") or {}).get(LIST_SLOT) or {}
        if not spec.get("dir"):
            return []
        pat = re.compile(rf"^{LIST_SLOT}(@[a-z0-9_]+)?(\.t\d+)?\.md$")
        out = set()
        for root in (self.pack_dir, self.opened_dir):
            folder = root / spec["dir"]
            if folder.is_dir():
                out |= {f"{spec['dir']}/{p.name}" for p in folder.iterdir() if pat.match(p.name)}
        return sorted(out)

    @staticmethod
    def _text(path: Path) -> str | None:
        return path.read_bytes().decode("utf-8").replace("\r\n", "\n") if path.is_file() else None

    def _write_text(self, rel: str, text: str) -> None:
        """*text* (LF) to the setup's file *rel*: the opened bytes when it is
        the opened text, else in the file's own line endings."""
        path, opened = self.pack_dir / rel, self.opened_dir / rel
        if opened.is_file() and self._text(opened) == text:
            raw = opened.read_bytes()
        else:
            eol = eol_of(path.read_bytes()) if path.is_file() else (
                eol_of(opened.read_bytes()) if opened.is_file() else "\n")
            raw = text.replace("\n", eol).encode("utf-8")
        if not path.is_file() or path.read_bytes() != raw:
            path.write_bytes(raw)

    # -- what the page reads -------------------------------------------------

    def state(self, data: dict) -> dict:
        raw, spec = self._spec(self.pack_dir)
        _, opened = self._spec(self.opened_dir)
        yraw = (self.pack_dir / "pack.yaml").read_bytes()
        ytext = self._text(self.opened_dir / "pack.yaml") or ""
        assets = self.pack_dir / "assets"
        return {
            "spec": spec, "sha": sha(raw), "opened": opened,
            "lists": self.list_files(data),
            "code_uses": code_uses(self.pack_dir, [p["name"] for p in spec["parameters"]]),
            "assets": sorted(p.name for p in assets.glob("*.png")) if assets.is_dir() else [],
            "pack_yaml_sha": sha(yraw), "since_opened": dict(self.since_opened),
            "access_opened": {a: cells for a, (_i, cells) in access_rows(ytext).items()},
        }

    def changed(self) -> list[str]:
        """The files of these editors that differ from the setup as opened."""
        out = []
        for rel in ("parameters.json", "pack.yaml"):
            a, b = self.pack_dir / rel, self.opened_dir / rel
            if not a.is_file() or not b.is_file() or a.read_bytes() != b.read_bytes():
                out.append(rel)
        now = {p.name for p in (self.pack_dir / "assets").glob("*") if p.is_file()}
        then = {p.name for p in (self.opened_dir / "assets").glob("*") if p.is_file()}
        out += [f"assets/{n}" for n in sorted(now ^ then)]
        return out

    # -- parameters ----------------------------------------------------------

    def _plan(self, data: dict, new: dict, base: str, renames):
        """(current bytes, current spec, the spec as it will be written,
        renames, {list: (old text, new text)})."""
        from studio.editing import Conflict, EditError
        raw, cur = self._spec(self.pack_dir)
        if base != sha(raw):
            raise Conflict("parameters.json changed on disk since the page read it.  "
                           "Reload the page to see it.")
        if not isinstance(new, dict) or not isinstance(renames or {}, dict):
            raise EditError("The page sent no parameter file.")
        renames = dict(renames or {})
        _, opened = self._spec(self.opened_dir)
        new = retire(cur, normalise(new), opened)
        problems = list(self.check(new))
        cur_names = [p["name"] for p in cur["parameters"]]
        new_names = [p.get("name") for p in new["parameters"] if isinstance(p, dict)]
        for o, n in renames.items():
            if o not in cur_names or n not in new_names or n in cur_names:
                problems.append(f"renaming {o!r} to {n!r}: the names do not match the parameters")
        if problems:
            raise EditError("The parameters cannot be saved.", problems)
        lists = {}
        for rel in self.list_files(data):
            text = self._text(self.pack_dir / rel)
            if text is None:
                continue
            otext = self._text(self.opened_dir / rel)
            out = (step_list(text, otext, cur, new, self.since_opened, renames) if otext is not None
                   else update_list(text, new, renames))
            if out != text:
                lists[rel] = (text, out)
        return raw, cur, new, renames, lists

    def preview(self, data: dict, new: dict, base: str, renames=None) -> dict:
        """What saving *new* would change -- nothing is written."""
        with self._lock:
            raw, cur, new, renames, lists = self._plan(data, new, base, renames)
            new_names = {q["name"] for q in new["parameters"]}
            gone = sorted({p["name"] for p in cur["parameters"] if p["name"] not in new_names})
            uses = code_uses(self.pack_dir, gone) if gone else {}
            return {"changes": changes(cur, new, renames), "spec": new,
                    "same": format_spec(new, eol_of(raw)) == raw,
                    "lists": [{"file": rel, "lines": list_diff(a, b)} for rel, (a, b) in sorted(lists.items())],
                    "code_uses": {n: u for n, u in uses.items() if u},
                    "database": range_changes(cur, new, renames)}

    def save(self, data: dict, new: dict, base: str, renames=None) -> dict:
        with self._lock:
            raw, cur, new, renames, lists = self._plan(data, new, base, renames)
            path = self.pack_dir / "parameters.json"
            oraw, opened = self._spec(self.opened_dir)
            out = (oraw if format_spec(new, "\n") == format_spec(normalise(opened), "\n")
                   else format_spec(new, eol_of(raw)))
            if out != raw:
                path.write_bytes(out)
            for rel, (_a, b) in lists.items():
                self._write_text(rel, b)
            self.since_opened = compose_renames(self.since_opened, renames)
            return {"lists": sorted(lists), "sha": sha(path.read_bytes()), "warnings": []}

    def undo_all(self, data: dict) -> dict:
        """parameters.json and the lists back as the Studio opened them, and
        any picture uploaded since then that no group uses goes."""
        with self._lock:
            raw, cur = self._spec(self.pack_dir)
            oraw, opened = self._spec(self.opened_dir)
            back = {v: k for k, v in self.since_opened.items()}
            for rel in self.list_files(data):
                text, otext = self._text(self.pack_dir / rel), self._text(self.opened_dir / rel)
                if text is None or otext is None:
                    continue
                self._write_text(rel, step_list(text, otext, cur, opened, self.since_opened, back))
            if raw != oraw:
                (self.pack_dir / "parameters.json").write_bytes(oraw)
            self.since_opened = {}
            self._drop_pictures(opened)
            return {"sha": sha(oraw), "warnings": []}

    def _drop_pictures(self, spec: dict) -> None:
        used = {str(g.get("image", "")).rsplit("/", 1)[-1] for g in spec["groups"]}
        then = {p.name for p in (self.opened_dir / "assets").glob("*") if p.is_file()}
        for p in (self.pack_dir / "assets").glob("*.png"):
            if p.name not in then and p.name not in used:
                p.unlink()

    def drop_unused_pictures(self, data: dict) -> dict:
        """A picture uploaded since opening that no group uses goes."""
        with self._lock:
            self._drop_pictures(self._spec(self.pack_dir)[1])
        return {"warnings": []}

    def sync_lists(self, data: dict) -> None:
        """Lists that are exactly as opened (a text field's Undo) brought in
        step with the parameters as they are now."""
        with self._lock:
            _, cur = self._spec(self.pack_dir)
            for rel in self.list_files(data):
                text, otext = self._text(self.pack_dir / rel), self._text(self.opened_dir / rel)
                if text is not None and otext is not None and text == otext:
                    self._write_text(rel, update_list(otext, cur, self.since_opened, otext))

    def upload_picture(self, data: dict, name: str, b64: str) -> dict:
        """A PNG (base64) into the setup's ``assets/``; its address for a group."""
        import base64
        import binascii
        from studio.editing import EditError
        stem = re.sub(r"[^a-z0-9_-]+", "-", str(name).lower().rsplit(".", 1)[0]).strip("-") or "picture"
        fname = stem + ".png"
        try:
            raw = base64.b64decode(str(b64), validate=True)
        except (binascii.Error, ValueError):
            raise EditError("The picture did not arrive whole.") from None
        if raw[:8] != b"\x89PNG\r\n\x1a\n":
            raise EditError("Only PNG pictures can be uploaded.")
        if len(raw) > self.PICTURE_MAX:
            raise EditError(f"The picture is {len(raw) / 1048576:.1f} MB; the limit is 2 MB.")
        with self._lock:
            path = self.pack_dir / "assets" / fname
            if path.exists():
                raise EditError(f"assets/{fname} already exists: pick it from the list, or rename "
                                "the file before uploading it.")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        return {"path": f"/pack/assets/{fname}", "file": fname, "warnings": []}

    # -- the access grid -----------------------------------------------------

    def set_access(self, data: dict, agent: str, topology, state: str, base: str) -> dict:
        from studio.editing import Conflict, EditError
        topology = str(topology)
        pa = data.get("parameter_access") or {}
        states = [s["id"] for s in pa.get("states", [])]
        with self._lock:
            raw = (self.pack_dir / "pack.yaml").read_bytes()
            if base != sha(raw):
                raise Conflict("pack.yaml changed on disk since the page read it.  Reload the page.")
            text = raw.decode("utf-8").replace("\r\n", "\n")
            rows = access_rows(text)
            if agent not in rows or topology not in rows[agent][1]:
                raise EditError(f"{agent} has no cell for the {topology}-agent topology.")
            if state not in states:
                raise EditError(f"{state!r} is not a state: {', '.join(states)}.")
            if state == "tool" and agent in pa.get("no_tool", []):
                raise EditError(f'{agent} cannot take "tool": it has no free tool loop.')
            self._write_text("pack.yaml", set_access(text, agent, topology, state))
            return {"pack_yaml_sha": sha((self.pack_dir / "pack.yaml").read_bytes()), "warnings": []}

    def undo_access(self, data: dict, agent: str) -> dict:
        """One agent's row back as the Studio opened it."""
        from studio.editing import EditError
        with self._lock:
            text = self._text(self.pack_dir / "pack.yaml")
            otext = self._text(self.opened_dir / "pack.yaml")
            rows, orows = access_rows(text), access_rows(otext)
            if agent not in rows or agent not in orows:
                raise EditError(f"{agent} has no row in the access grid.")
            lines = text.split("\n")
            lines[rows[agent][0]] = otext.split("\n")[orows[agent][0]]
            self._write_text("pack.yaml", "\n".join(lines))
            return {"pack_yaml_sha": sha((self.pack_dir / "pack.yaml").read_bytes()), "warnings": []}
