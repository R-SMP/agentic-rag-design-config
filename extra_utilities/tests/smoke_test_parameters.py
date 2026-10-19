"""The parameter file and the parameter schema, offline.

``dc_pack/parameters.json`` is the ONE source of the parameter data (names,
order, types, ranges, groups) since MAS-blueprint P2; ``engine/parameters.py``
loads and checks it, ``engine/parameter_schema.py`` compares it with -- and
uploads it to -- table ``dc_parameter_schemas``.  Five groups of checks:

1. VALIDATION.  The real file passes, and each kind of broken file is caught
   with a message naming the parameter or group at fault.
2. DRIFT.  The agents' parameter LISTS are hand-written text
   (``dc_pack/fragments/dc/parameter_list*.md``), not generated.  Every one
   must name the same parameters, in the same order, with the same
   ``[min; max]`` as the file.  This is the guard that keeps the two from
   drifting apart.
3. BUILDERS.  What the validator, the slider page, the preview check and the
   database get from the file has the shape each one expects.
4. SCHEMA UPLOAD.  Matching, planning, the upload and the retirements, run
   against a STAND-IN connection that keeps the table in memory -- never the
   live database.
5. TYPES (MAS-blueprint P6d).  A made-up setup with choice and on/off
   parameters and ``used_when``: it is valid, each kind of broken one is
   caught, its values are checked, stored and searched as the readers
   expect, a list entry must carry its values, and its schema rows need the
   v10 columns (stand-in database again).

Run from the repo root:  py -3.13 extra_utilities/tests/smoke_test_parameters.py
"""
from __future__ import annotations

import copy
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from engine import pack, parameter_schema, parameters  # noqa: E402

FAILURES: list[str] = []


def check(ok: bool, what: str) -> None:
    if not ok:
        FAILURES.append(what)


# ---------------------------------------------------------------------------
# 1. Validation
# ---------------------------------------------------------------------------

def _broken(spec: dict, edit) -> list[str]:
    s = copy.deepcopy(spec)
    edit(s)
    return parameters.validate(s)


def _param(s: dict, name: str) -> dict:
    return next(p for p in s["parameters"] if p["name"] == name)


def check_validation(spec: dict) -> None:
    check(parameters.validate(spec) == [],
          f"[VALIDATION] the real parameters.json has problems: "
          f"{parameters.validate(spec)}")
    first = spec["parameters"][0]["name"]
    cases = {
        "duplicate name": lambda s: s["parameters"].append(
            dict(s["parameters"][0])),
        "must be smaller than max": lambda s: _param(s, first).update(min=10, max=5),
        "is outside": lambda s: _param(s, first).update(default=_param(s, first)["max"] + 1),
        "whole-number": lambda s: _param(s, first).update(type="int", min=0, max=10,
                                                         default=1, step=0.5),
        "step must be positive": lambda s: _param(s, first).update(step=0),
        'type must be "int", "float", "choice" or "bool"': lambda s: _param(s, first).update(type="text"),
        "does not exist": lambda s: _param(s, first).update(group="nowhere"),
        "not listed in the order of its group": lambda s: s["groups"][0]["order"].remove(
            s["groups"][0]["order"][0]),
        "listed in two groups": lambda s: s["groups"].append(
            dict(s["groups"][0], id="second_group_of_the_check",
                 order=[s["groups"][0]["order"][0]])),
        "which is not a parameter": lambda s: s["groups"][0]["order"].append("ghost"),
        'unknown field "colour"': lambda s: _param(s, first).update(colour="red"),
        'missing field "db_unit"': lambda s: _param(s, first).pop("db_unit"),
        "must be numbers": lambda s: _param(s, first).update(min="3"),
        "listed as retired but still a parameter": lambda s: s.update(retired=[first]),
        "listed as retired twice": lambda s: s.update(retired=["gone", "gone"]),
        "must be a list of names": lambda s: s.update(retired="gone"),
        'and, optionally, "retired"': lambda s: s.update(colours=[]),
    }
    for expected, edit in cases.items():
        problems = _broken(spec, edit)
        check(any(expected in p for p in problems),
              f"[VALIDATION] a file with a '{expected}' error was not caught "
              f"(got {problems})")
    check(parameters.validate({"parameters": []}) != [],
          "[VALIDATION] a file without groups was accepted")
    no_retired = copy.deepcopy(spec)
    no_retired.pop("retired", None)
    check(parameters.validate(no_retired) == [] and parameters.retired(no_retired) == (),
          "[VALIDATION] a file without the optional retired list was not accepted")
    check(set(parameters.retired(spec)).isdisjoint(parameters.names(spec)),
          "[VALIDATION] a retired name is still a parameter")


# ---------------------------------------------------------------------------
# 2. Drift: the hand-written parameter lists against the file
# ---------------------------------------------------------------------------

_ENTRY_RE = re.compile(r"^\s*(\d+)\.\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_RANGE_RE = re.compile(r"\[\s*(-?[\d.]+)\s*;\s*(-?[\d.]+)\s*\]")


def parse_parameter_list(text: str) -> list[tuple[int, str, tuple | None]]:
    """``[(number, name, (min, max) or None), ...]``.  An entry runs from its
    numbered line to the next entry, a blank line or a heading, so a range
    on a continuation line still belongs to it."""
    out = []
    for number, name, body in parameter_entries(text):
        r = _RANGE_RE.search(body)
        out.append((number, name, (float(r.group(1)), float(r.group(2))) if r else None))
    return out


def parameter_entries(text: str) -> list[tuple[int, str, str]]:
    """``[(number, name, its lines joined), ...]``, by the rule above."""
    entries: list[list] = []          # [number, name, text]
    open_entry = False
    for line in text.splitlines():
        m = _ENTRY_RE.match(line)
        if m:
            entries.append([int(m.group(1)), m.group(2), line])
            open_entry = True
        elif open_entry and line.strip() and not line.lstrip().startswith("#"):
            entries[-1][2] += " " + line
        else:
            open_entry = False
    return [tuple(e) for e in entries]


def check_drift(spec: dict) -> int:
    # a choice or on/off parameter has no range: its entry lists its values
    expected = [(p["name"], (float(p["min"]), float(p["max"])) if "min" in p else None)
                for p in spec["parameters"]]
    files = sorted((pack.fragments_dir() / "dc").glob("parameter_list*.md"))
    check(bool(files), "[DRIFT] no parameter_list*.md file found in the pack")
    for f in files:
        text = f.read_text(encoding="utf-8")
        got = parse_parameter_list(text)
        where = f"[DRIFT] {f.name}"
        numbers = [n for n, _, _ in got]
        check(numbers == list(range(1, len(got) + 1)),
              f"{where}: entries are numbered {numbers}, not 1..{len(got)}")
        names = [n for _, n, _ in got]
        want = [n for n, _ in expected]
        if names != want:
            check(False, f"{where}: names {names} differ from parameters.json {want}")
            continue
        for (_, name, rng), (_, want_rng) in zip(got, expected):
            check(rng == want_rng,
                  f"{where}: {name} has range {rng}, parameters.json says {want_rng}")
        for (_, name, body), p in zip(parameter_entries(text), spec["parameters"]):
            why = parameters.entry_problem(p, body)
            check(why is None, f"{where}: {name} {why}")
    return len(files)


# ---------------------------------------------------------------------------
# 3. Builders
# ---------------------------------------------------------------------------

def check_builders(spec: dict) -> None:
    names = parameters.names(spec)
    check(len(names) == parameters.count(spec) == len(set(names)),
          "[BUILDERS] names() / count() disagree or repeat a name")
    # A choice or on/off parameter has no range: its shapes are checked in
    # check_types (MAS-blueprint P6d).
    number = {p["name"] for p in spec["parameters"] if p["type"] in ("int", "float")}
    types = parameters.types(spec)
    check(list(types) == list(names) and all(types[n] in (int, float) for n in number),
          "[BUILDERS] types() does not cover every name with int/float")
    preview = parameters.preview_spec(spec)
    check(list(preview) == list(names), "[BUILDERS] preview_spec() keys != names")
    for n, s in preview.items():
        check(n not in number or set(s) == {"type", "min", "max"} and s["min"] < s["max"],
              f"[BUILDERS] preview_spec()[{n}] is malformed: {s}")
    groups = parameters.slider_groups(spec)
    seen = [p["key"] for g in groups for p in g["params"]]
    check(sorted(seen) == sorted(names),
          "[BUILDERS] slider_groups() does not show every parameter exactly once")
    for g in groups:
        check(set(g) == {"key", "label", "image", "imageAlt", "params"},
              f"[BUILDERS] slider group {g.get('key')} has fields {sorted(g)}")
        for p in g["params"]:
            if p["key"] not in number:
                continue
            check(set(p) - {"usedWhen"} == {"key", "label", "unit", "min", "max", "step", "value"},
                  f"[BUILDERS] slider {p.get('key')} has fields {sorted(p)}")
            check(p["min"] <= p["value"] <= p["max"],
                  f"[BUILDERS] slider {p['key']} starts outside its range")
    payload = parameters.page_payload(spec)
    check(payload["names"] == list(names) and payload["groups"] == groups,
          "[BUILDERS] page_payload() is not {names, slider_groups}")
    json.dumps(payload)        # must be JSON-serialisable for /pack/parameters.js
    rows = parameters.db_rows(spec)
    check([r["param_name"] for r in rows] == list(names)
          and all(set(r) == {"param_name", "min_value", "max_value", "unit", "description"}
                  | (set() if r["param_name"] in number else {"param_type", "choices"})
                  for r in rows),
          "[BUILDERS] db_rows() rows are malformed or out of order")
    reg = pack.registry().get("parameter_count", {})
    check(reg.get("source") == "generated" and reg.get("from") == "parameter_count",
          "[BUILDERS] $parameter_count is not a generated slot in the registry")
    check(not (pack.fragments_dir() / "dc" / "parameter_count.md").exists(),
          "[BUILDERS] a parameter_count.md fragment is back: the count is "
          "computed from parameters.json now")


# ---------------------------------------------------------------------------
# 4. Schema upload, against a stand-in connection
# ---------------------------------------------------------------------------

class FakeConn:
    """Table ``dc_parameter_schemas`` in memory, answering exactly the SQL
    ``engine/parameter_schema.py`` sends.  Anything else fails the check."""

    def __init__(self, rows: list[dict] | None = None, v10: bool = True):
        self.rows = [dict(r) for r in rows or []]
        self.sql: list[str] = []
        self.clock = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.v10 = v10          # False: a v9 table, without param_type / choices

    def cursor(self):
        return FakeCursor(self)


class FakeCursor:
    def __init__(self, conn: FakeConn):
        self.conn, self.result = conn, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        c = self.conn
        c.sql.append(sql.split()[0])
        if sql == parameter_schema._LOCK_SQL:
            return
        if sql == parameter_schema._SELECT_ALL_SQL:
            self.result = [(r["schema_version"], r["param_name"], r["min_value"],
                            r["max_value"], r["unit"], r["description"],
                            r["introduced_at"], r["retired_at"])
                           for r in sorted(c.rows, key=lambda r: (
                               r["schema_version"], r["param_name"]))]
            return
        if sql == parameter_schema._SELECT_TYPED_SQL:
            if not c.v10:
                raise UndefinedColumn('column "param_type" does not exist')
            self.result = [(r["schema_version"], r["param_name"], r["min_value"],
                            r["max_value"], r["unit"], r["description"],
                            r["introduced_at"], r["retired_at"], r.get("param_type"),
                            r.get("choices"))
                           for r in sorted(c.rows, key=lambda r: (
                               r["schema_version"], r["param_name"]))]
            return
        if sql == parameter_schema._RETIRE_SQL:
            version, names = params
            c.clock += timedelta(minutes=1)
            for r in c.rows:
                if (r["schema_version"] == version and r["param_name"] in names
                        and r["retired_at"] is None):
                    r["retired_at"] = c.clock
            return
        raise AssertionError(f"unexpected SQL: {sql}")

    def executemany(self, sql, seq):
        assert sql in (parameter_schema._INSERT_SQL, parameter_schema._INSERT_TYPED_SQL), \
            f"unexpected SQL: {sql}"
        c = self.conn
        c.sql.append("INSERT" if sql == parameter_schema._INSERT_SQL else "INSERT_TYPED")
        c.clock += timedelta(minutes=1)
        for v, name, lo, hi, unit, desc, *typed in seq:
            ptype, choices = typed or (None, None)
            assert choices is None or isinstance(choices, str), "choices must go in as JSON text"
            assert not any(r["schema_version"] == v and r["param_name"] == name
                           for r in c.rows), "primary key violated"
            assert lo <= hi, "CHECK min_value <= max_value violated"
            c.rows.append({"schema_version": v, "param_name": name,
                           "min_value": float(lo), "max_value": float(hi),
                           "unit": unit, "description": desc,
                           "introduced_at": c.clock, "retired_at": None,
                           "param_type": ptype,
                           "choices": json.loads(choices) if choices is not None else None})

    def fetchall(self):
        return self.result


class UndefinedColumn(Exception):
    """What psycopg raises for a column the table lacks (SQLSTATE 42703)."""
    sqlstate = "42703"


def _table(version: int, rows: list[dict]) -> list[dict]:
    """*rows* stored as the database returns them: floats, timestamps."""
    t = datetime(2025, 1, version, tzinfo=timezone.utc)
    return [{"schema_version": version, "param_name": r["param_name"],
             "min_value": float(r["min_value"]), "max_value": float(r["max_value"]),
             "unit": r["unit"], "description": r["description"],
             "introduced_at": t, "retired_at": None, "param_type": r.get("param_type"),
             "choices": r.get("choices")} for r in rows]


def check_schema(spec: dict) -> None:
    rows = parameter_schema.setup_rows(spec)
    n = len(rows)
    first = rows[0]["param_name"]

    # An empty table: nothing matches, the upload creates version 1.
    conn = FakeConn()
    check(parameter_schema.matching_version(conn, rows) is None,
          "[SCHEMA] an empty table reported a matching version")
    st = parameter_schema.status(conn, spec)
    check(st["state"] == "missing" and st["latest_version"] is None,
          f"[SCHEMA] empty table: status {st['state']}/{st['latest_version']}")
    conn.sql.clear()
    plan = parameter_schema.upload(conn, rows)
    check(plan == {"action": "insert", "version": 1, "previous": None, "retire": []},
          f"[SCHEMA] first upload planned {plan}")
    check(conn.sql[:2] == ["LOCK", "SELECT"],
          f"[SCHEMA] the upload did not lock the table before reading it: {conn.sql}")
    check(len(conn.rows) == n and parameter_schema.matching_version(conn, rows) == 1,
          "[SCHEMA] after the first upload version 1 does not match the setup")
    again = parameter_schema.upload(conn, rows)
    check(again == {"action": "none", "version": 1} and len(conn.rows) == n,
          f"[SCHEMA] a second upload of the same setup wrote rows: {again}")

    # Today's live layout: v1 = the setup + a parameter v2 dropped (retired),
    # v2 = the setup.  Version 2 matches; nothing to upload.
    old_extra = {"param_name": "impellerHeight", "min_value": 4, "max_value": 10,
                 "unit": "mm", "description": "Height of the outer ring"}
    live = _table(1, rows + [old_extra]) + _table(2, rows)
    for r in live:
        if r["schema_version"] == 1 and r["param_name"] == "impellerHeight":
            r["retired_at"] = datetime(2025, 1, 2, tzinfo=timezone.utc)
    conn = FakeConn(live)
    st = parameter_schema.status(conn, spec)
    check(st["state"] == "current" and st["matching_version"] == 2
          and st["latest_version"] == 2,
          f"[SCHEMA] live layout: status {st['state']} match {st['matching_version']}")
    check([v["version"] for v in st["versions"]] == [2, 1],
          "[SCHEMA] status() does not list versions newest first")
    check([r["param_name"] for r in st["versions"][0]["rows"]]
          == [r["param_name"] for r in rows],
          "[SCHEMA] status() does not list a version's rows in the setup's order")
    check(parameter_schema.upload(conn, rows)["action"] == "none",
          "[SCHEMA] live layout: an upload wrote rows although version 2 matches")

    # A changed range: no match, the next version, nothing retired.
    changed = copy.deepcopy(rows)
    changed[0]["max_value"] = changed[0]["max_value"] + 1
    plan = parameter_schema.upload(conn, changed)
    check(plan == {"action": "insert", "version": 3, "previous": 2, "retire": []},
          f"[SCHEMA] changed range planned {plan}")
    check(parameter_schema.matching_version(conn, changed) == 3
          and parameter_schema.matching_version(conn, rows) == 2,
          "[SCHEMA] after the range change, versions 3 / 2 do not match their sets")
    st = parameter_schema.status(conn, spec)
    check(st["state"] == "older" and st["matching_version"] == 2,
          f"[SCHEMA] the setup matching an older version reads as {st['state']}")

    # A dropped parameter: retired in the previous latest version, absent from
    # the new one; rows are never deleted.
    dropped = [r for r in changed if r["param_name"] != first]
    before = len(conn.rows)
    plan = parameter_schema.upload(conn, dropped)
    check(plan == {"action": "insert", "version": 4, "previous": 3, "retire": [first]},
          f"[SCHEMA] dropped parameter planned {plan}")
    gone = [r for r in conn.rows if r["param_name"] == first]
    check(len(conn.rows) == before + n - 1
          and [r["schema_version"] for r in gone] == [1, 2, 3]
          and all(r["retired_at"] is None for r in gone if r["schema_version"] != 3)
          and next(r for r in gone if r["schema_version"] == 3)["retired_at"] is not None,
          "[SCHEMA] the dropped parameter was not retired in version 3 only")

    # Comparison details: ints vs the database's floats, NULL vs "" text.
    nulls = [dict(r, unit=None if not r["unit"] else r["unit"]) for r in rows]
    check(parameter_schema.same_rows(_table(1, rows), rows)
          and parameter_schema.same_rows(nulls, [dict(r, unit=r["unit"] or "")
                                                 for r in rows]),
          "[SCHEMA] equal sets compared as different (float / NULL handling)")
    renamed = [dict(r, description=r["description"] + "!") if i == 0 else r
               for i, r in enumerate(rows)]
    check(not parameter_schema.same_rows(rows, renamed),
          "[SCHEMA] a changed description compared as equal")


# ---------------------------------------------------------------------------
# 5. Types: choice and on/off parameters, used_when (MAS-blueprint P6d)
# ---------------------------------------------------------------------------

def _number(name: str, lo, hi, step, default, unit: str = "mm", **more) -> dict:
    p = {"name": name, "type": "int" if isinstance(step, int) else "float", "min": lo, "max": hi,
         "step": step, "default": default, "group": "body", "label": name, "unit": unit,
         "db_unit": unit, "db_description": f"The {name.lower()}"}
    p.update(more)
    return p


# A made-up setup: two numbers, a choice, an on/off parameter used with one
# choice and a number used with the other.
TYPED_SPEC = {
    "groups": [{"id": "body", "label": "Body", "image": "/pack/assets/body.png", "image_alt": "Body",
                "order": ["Length", "Count", "End1_Style", "Barbs", "FlangeDia"]}],
    "parameters": [
        _number("Length", 10.0, 100.0, 1.0, 50.0),
        _number("Count", 1, 5, 1, 2, unit=""),
        {"name": "End1_Style", "type": "choice",
         "choices": [{"value": "hose", "label": "Hose connector"},
                     {"value": "mag", "label": "Magnetic flange"}],
         "default": "hose", "group": "body", "label": "End 1 style", "unit": "",
         "db_unit": "choice", "db_description": "Connector style"},
        {"name": "Barbs", "type": "bool", "default": False, "group": "body", "label": "Barbs",
         "unit": "", "db_unit": "on/off", "db_description": "Barbs on the hose end",
         "used_when": {"End1_Style": "hose"}},
        _number("FlangeDia", 5.0, 20.0, 0.5, 10.0, used_when={"End1_Style": "mag"}),
    ]}

# The same setup without its choice and on/off parameters (and conditions).
NUMBERS_SPEC = {
    "groups": [dict(TYPED_SPEC["groups"][0], order=["Length", "Count"])],
    "parameters": [dict(TYPED_SPEC["parameters"][0]), dict(TYPED_SPEC["parameters"][1])]}

# Each kind of broken typed file, and the words its problem must hold.
TYPED_BAD = {
    "is listed twice": lambda s: _param(s, "End1_Style")["choices"].append(
        {"value": "hose", "label": "Again"}),
    "is not one of its choices": lambda s: _param(s, "End1_Style").update(default="ring"),
    'must be text without "|"': lambda s: _param(s, "End1_Style")["choices"][0].update(label="a | b"),
    "a list of at least two": lambda s: _param(s, "End1_Style").update(
        choices=[{"value": "hose", "label": "Hose"}]),
    "a choice has no \"label\"": lambda s: _param(s, "End1_Style")["choices"][1].pop("label"),
    "a choice's value must be": lambda s: _param(s, "End1_Style")["choices"][1].update(value=""),
    "goes round in a circle": lambda s: _param(s, "End1_Style").update(used_when={"Barbs": True}),
    "which is not a choice or on/off parameter": lambda s: _param(s, "Barbs").update(
        used_when={"Length": 3}),
    "which is not a parameter": lambda s: _param(s, "Barbs").update(used_when={"Ghost": 3}),
    "has no value 'ring'": lambda s: _param(s, "Barbs").update(used_when={"End1_Style": "ring"}),
    "names the parameter itself": lambda s: _param(s, "Barbs").update(used_when={"Barbs": True}),
    "must name at least one": lambda s: _param(s, "Barbs").update(used_when={}),
    'unknown field "min"': lambda s: _param(s, "Barbs").update(min=0),
    "default must be true or false": lambda s: _param(s, "Barbs").update(default=1),
    "default True is not one of its choices": lambda s: _param(s, "End1_Style").update(default=True),
    "End1_Style has no value True": lambda s: _param(s, "Barbs").update(used_when={"End1_Style": True}),
    'missing field "choices"': lambda s: _param(s, "End1_Style").pop("choices"),
}


def typed_bad_specs() -> list[dict]:
    """The broken typed files (for the page's own check, smoke_test_studio)."""
    out = []
    for edit in TYPED_BAD.values():
        s = copy.deepcopy(TYPED_SPEC)
        edit(s)
        out.append(s)
    return out


def check_types(spec: dict) -> None:
    T = TYPED_SPEC
    by = parameters.by_name(T)
    check(parameters.validate(T) == [], f"[TYPES] the typed setup has problems: {parameters.validate(T)}")
    N = NUMBERS_SPEC
    check(parameters.validate(N) == [] and parameters.all_numbers(N) and not parameters.all_numbers(T),
          "[TYPES] all_numbers() is wrong for a setup of numbers or the typed setup")
    check(parameters.value_phrase(N) == "a number"
          and parameters.value_phrase(T) == parameters.VALUE_PHRASE,
          "[TYPES] value_phrase() does not keep \"a number\" for a setup of numbers")
    for expected, edit in TYPED_BAD.items():
        problems = _broken(T, edit)
        check(any(expected in p for p in problems),
              f"[TYPES] a typed file with a '{expected}' error was not caught (got {problems})")
    # a file whose choices are not even a list must not break the check
    for broken in ("ab", 7, ["hose", "mag"]):
        problems = _broken(T, lambda s: _param(s, "End1_Style").update(choices=broken))
        check(any("choices must be a list" in p for p in problems),
              f"[TYPES] choices={broken!r} was not caught (got {problems})")
    check(any("type must be" in p for p in _broken(T, lambda s: _param(s, "Length").update(type=["int"]))),
          "[TYPES] a type that is a list was not caught")

    # values
    cases = [("Length", 42, None), ("Length", "42", "must be a number"),
             ("Length", True, "must be a number"), ("End1_Style", "mag", None),
             ("End1_Style", "ring", "must be one of: hose, mag"), ("Barbs", True, None),
             ("Barbs", 1, "must be true or false")]
    for name, value, want in cases:
        check(parameters.check_value(by[name], value) == want,
              f"[TYPES] check_value({name}, {value!r}) = "
              f"{parameters.check_value(by[name], value)!r}, not {want!r}")
    record = {"Length": "long", "Count": 2, "End1_Style": "ring", "Barbs": False, "FlangeDia": 10}
    check(parameters.wrong_values(record, T) == [("Length", "must be a number"),
                                                ("End1_Style", "must be one of: hose, mag")],
          f"[TYPES] wrong_values() = {parameters.wrong_values(record, T)}")
    check([parameters.to_db(by[n], v) for n, v in
           (("Length", 42), ("End1_Style", "hose"), ("End1_Style", "mag"), ("Barbs", True),
            ("Barbs", False))] == [42.0, 0.0, 1.0, 1.0, 0.0],
          "[TYPES] to_db() does not store numbers / positions / 1-0")
    check(parameters.is_used(by["Barbs"], {"End1_Style": "hose"})
          and not parameters.is_used(by["Barbs"], {"End1_Style": "mag"})
          and parameters.is_used(by["Length"], {}),
          "[TYPES] is_used() does not follow used_when")

    # what the builders give
    rows = {r["param_name"]: r for r in parameters.db_rows(T)}
    check(rows["End1_Style"] == {"param_name": "End1_Style", "min_value": 0, "max_value": 1,
                                 "unit": "choice", "description": "Connector style",
                                 "param_type": "choice", "choices": ["hose", "mag"]}
          and rows["Barbs"]["param_type"] == "bool" and rows["Barbs"]["choices"] is None
          and "param_type" not in rows["Length"],
          f"[TYPES] db_rows() typed rows are wrong: {rows}")
    sliders = {p["key"]: p for g in parameters.slider_groups(T) for p in g["params"]}
    check(sliders["End1_Style"].get("type") == "choice"
          and sliders["End1_Style"]["choices"] == by["End1_Style"]["choices"]
          and sliders["Barbs"].get("type") == "bool" and sliders["Barbs"]["value"] is False
          and sliders["Barbs"].get("usedWhen") == {"End1_Style": "hose"}
          and sliders["FlangeDia"].get("usedWhen") == {"End1_Style": "mag"}
          and "usedWhen" not in sliders["Length"] and "type" not in sliders["Length"],
          f"[TYPES] slider_groups() controls are wrong: {sliders}")
    preview = parameters.preview_spec(T)
    check(preview["End1_Style"] == {"type": "choice", "choices": ["hose", "mag"]}
          and preview["Barbs"] == {"type": "bool"},
          f"[TYPES] preview_spec() is wrong: {preview}")

    # a list entry must carry the values and the condition
    check(parameters.values_text(by["End1_Style"]) == "hose = Hose connector | mag = Magnetic flange"
          and parameters.values_text(by["Barbs"]) == "true | false"
          and parameters.values_text(by["Length"]) == ""
          and parameters.used_when_text(by["Barbs"]) == " (only when End1_Style = hose)",
          "[TYPES] values_text() / used_when_text() changed")
    good = (" 3. End1_Style (choice) — Connector style:\n"
            "    hose = Hose connector | mag = Magnetic flange")
    check(parameters.entry_problem(by["End1_Style"], good) is None,
          "[TYPES] a correct (wrapped) choice entry was refused")
    check(parameters.entry_problem(by["End1_Style"], good.replace("Magnetic", "Magnet")) is not None,
          "[TYPES] a choice entry with a wrong label was accepted")
    check(parameters.entry_problem(by["Barbs"], " 4. Barbs (on/off) — Barbs: true | false") is not None,
          "[TYPES] an entry without its (only when ...) was accepted")
    check(parameters.entry_problem(by["Barbs"], " 4. Barbs (on/off) — Barbs: true | false"
                                                " (only when End1_Style = hose)") is None,
          "[TYPES] a correct on/off entry was refused")
    check(all(parameters.entry_problem(p, "") is None for p in spec["parameters"]
              if p["type"] in ("int", "float") and "used_when" not in p),
          "[TYPES] a number without used_when has an entry problem")

    # the schema rows, on a v10 table and on a v9 one
    rows = parameter_schema.setup_rows(T)
    conn = FakeConn()
    plan = parameter_schema.upload(conn, rows)
    check(plan["action"] == "insert" and conn.sql[-1] == "INSERT_TYPED"
          and parameter_schema.matching_version(conn, rows) == 1,
          f"[TYPES] a typed upload did not write and match version 1: {plan} {conn.sql}")
    stored = {r["param_name"]: r for r in conn.rows}
    check(stored["End1_Style"]["param_type"] == "choice"
          and stored["End1_Style"]["choices"] == ["hose", "mag"]
          and stored["Length"]["param_type"] is None and stored["Length"]["choices"] is None,
          f"[TYPES] the typed rows were stored wrongly: {stored}")
    check(parameter_schema.upload(conn, rows)["action"] == "none",
          "[TYPES] a second typed upload wrote rows")
    swapped = copy.deepcopy(T)
    _param(swapped, "End1_Style")["choices"].reverse()
    rows2 = parameter_schema.setup_rows(swapped)
    check(parameter_schema.matching_version(conn, rows2) is None
          and parameter_schema.upload(conn, rows2)["version"] == 2,
          "[TYPES] reordered choices matched the old version (stored positions would change)")
    relabelled = copy.deepcopy(T)
    _param(relabelled, "End1_Style")["choices"][0]["label"] = "Hose end"
    check(parameter_schema.matching_version(conn, parameter_schema.setup_rows(relabelled)) == 1,
          "[TYPES] a changed label made a new version (labels are not stored)")
    as_number = [dict(r) for r in rows]
    for r in as_number:
        r.pop("param_type", None)
        r.pop("choices", None)
    check(not parameter_schema.same_rows(rows, as_number),
          "[TYPES] a choice row compared equal to a number row with the same range")
    barbs = [r for r in rows if r["param_name"] == "Barbs"]
    check(not parameter_schema.same_rows(barbs, [r for r in as_number if r["param_name"] == "Barbs"]),
          "[TYPES] an on/off row compared equal to a number row with the range 0..1")
    st = parameter_schema.status(conn, swapped)
    shown = {r["param_name"]: r for r in st["setup"]}
    check(st["state"] == "current" and shown["End1_Style"]["param_type"] == "choice"
          and "param_type" not in shown["Length"],
          f"[TYPES] status() of a typed setup is wrong: {st['state']} {shown}")
    old = FakeConn(v10=False)
    try:
        parameter_schema.upload(old, rows)
        check(False, "[TYPES] a typed upload on a v9 table did not stop")
    except parameter_schema.NeedsSchemaV10 as exc:
        check("migrate_v9_to_v10.sql" in str(exc) and old.rows == [],
              f"[TYPES] the v9 table's refusal is unclear or wrote rows: {exc}")
    old = FakeConn(v10=False)
    check(parameter_schema.upload(old, parameter_schema.setup_rows(N))["action"] == "insert"
          and old.sql[-1] == "INSERT", "[TYPES] a setup of numbers no longer uploads to a v9 table")

    # the readers, with the typed setup as the active one
    check_typed_readers()


def check_typed_readers() -> None:
    """The record reader, the parameter search's query check and the
    picture samples, with :data:`TYPED_SPEC` as the active setup (a copy of
    the pack, its pictures left out, with the typed parameters.json)."""
    import shutil
    import tempfile

    from engine import image_run, pack_tools
    from tools.database_search import param_rank
    saved = config.DC_PACK_DIR
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "pack"
        shutil.copytree(pack.pack_dir(), folder, ignore=shutil.ignore_patterns("assets"))
        (folder / "parameters.json").write_text(json.dumps(TYPED_SPEC), encoding="utf-8")
        config.DC_PACK_DIR = folder
        try:
            good = {"Length": 40, "Count": 2, "End1_Style": "mag", "Barbs": False, "FlangeDia": 12.5}
            rec = folder / "record.json"
            rec.write_text(json.dumps(good), encoding="utf-8")
            values, err = pack_tools._read_record(rec)
            check(err is None and values == good, f"[TYPES] a good typed record was refused: {err}")
            rec.write_text(json.dumps(dict(good, End1_Style="ring", Barbs="no")), encoding="utf-8")
            values, err = pack_tools._read_record(rec)
            check(values is None and err and "Values that do not fit: End1_Style must be one of: "
                  "hose, mag; Barbs must be true or false" in err,
                  f"[TYPES] a bad typed record: {err}")
            schema = {"Length": (10.0, 100.0), "End1_Style": (0.0, 1.0), "Barbs": (0.0, 1.0)}
            check(param_rank.validate_query({"End1_Style": "mag", "Barbs": True, "Length": 40}, schema)
                  == {"End1_Style": 1.0, "Barbs": 1.0, "Length": 40.0},
                  "[TYPES] the search does not encode choice / on/off values as stored")
            for query, words in (({"End1_Style": "ring"}, "must be one of: hose, mag"),
                                 ({"Barbs": 1}, "must be true or false"),
                                 ({"Length": 400}, "outside its legal range")):
                try:
                    param_rank.validate_query(query, schema)
                    check(False, f"[TYPES] the search accepted {query}")
                except param_rank.ParameterQueryError as exc:
                    check(words in str(exc), f"[TYPES] the search refused {query} with: {exc}")
            calls = []

            class Cur:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

                def execute(self, sql, args):
                    calls.append(args)

                def fetchall(self):
                    return []

            class Conn:
                def cursor(self):
                    return Cur()
            param_rank.rank_attempts(Conn(), caller_agent="planner",
                                     params={"Length": 40.0, "End1_Style": 1.0}, n=3)
            check(calls and calls[0]["cats"] == [False, True],
                  f"[TYPES] the ranking does not flag the choice as matched-or-not: {calls}")
            yml = folder / "pack.yaml"
            yml.write_text(json.dumps({"render_samples": {"small": good}}), encoding="utf-8")
            check(image_run.render_sample_sets(yml) == {"small": good},
                  "[TYPES] typed picture samples were refused")
            yml.write_text(json.dumps({"render_samples": {"small": dict(good, Barbs=0)}}), encoding="utf-8")
            try:
                image_run.render_sample_sets(yml)
                check(False, "[TYPES] a picture sample with Barbs=0 was accepted")
            except pack_tools.PackToolError as exc:
                check(parameters.VALUE_PHRASE in str(exc), f"[TYPES] the sample refusal: {exc}")
        finally:
            config.DC_PACK_DIR = saved


def main() -> int:
    spec = parameters.load()
    check_validation(spec)
    n_files = check_drift(spec)
    check_builders(spec)
    check_schema(spec)
    check_types(spec)
    print(f"{parameters.count(spec)} parameters in {len(spec['groups'])} groups; "
          f"{n_files} hand-written parameter list(s) compared")
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - parameters.json is valid, every parameter list agrees with "
          "it, the builders are well-formed, the schema upload behaves "
          "(stand-in database) and choice / on/off parameters work.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
