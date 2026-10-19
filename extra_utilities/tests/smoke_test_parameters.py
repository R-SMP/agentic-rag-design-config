"""The parameter file and the parameter schema, offline.

``dc_pack/parameters.json`` is the ONE source of the parameter data (names,
order, types, ranges, groups) since MAS-blueprint P2; ``engine/parameters.py``
loads and checks it, ``engine/parameter_schema.py`` compares it with -- and
uploads it to -- table ``dc_parameter_schemas``.  Four groups of checks:

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
        'type must be "int" or "float"': lambda s: _param(s, first).update(type="bool"),
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
    out = []
    for number, name, body in entries:
        r = _RANGE_RE.search(body)
        out.append((number, name, (float(r.group(1)), float(r.group(2))) if r else None))
    return out


def check_drift(spec: dict) -> int:
    expected = [(p["name"], (float(p["min"]), float(p["max"])))
                for p in spec["parameters"]]
    files = sorted((pack.fragments_dir() / "dc").glob("parameter_list*.md"))
    check(bool(files), "[DRIFT] no parameter_list*.md file found in the pack")
    for f in files:
        got = parse_parameter_list(f.read_text(encoding="utf-8"))
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
    return len(files)


# ---------------------------------------------------------------------------
# 3. Builders
# ---------------------------------------------------------------------------

def check_builders(spec: dict) -> None:
    names = parameters.names(spec)
    check(len(names) == parameters.count(spec) == len(set(names)),
          "[BUILDERS] names() / count() disagree or repeat a name")
    types = parameters.types(spec)
    check(list(types) == list(names) and set(types.values()) <= {int, float},
          "[BUILDERS] types() does not cover every name with int/float")
    preview = parameters.preview_spec(spec)
    check(list(preview) == list(names), "[BUILDERS] preview_spec() keys != names")
    for n, s in preview.items():
        check(set(s) == {"type", "min", "max"} and s["min"] < s["max"],
              f"[BUILDERS] preview_spec()[{n}] is malformed: {s}")
    groups = parameters.slider_groups(spec)
    seen = [p["key"] for g in groups for p in g["params"]]
    check(sorted(seen) == sorted(names),
          "[BUILDERS] slider_groups() does not show every parameter exactly once")
    for g in groups:
        check(set(g) == {"key", "label", "image", "imageAlt", "params"},
              f"[BUILDERS] slider group {g.get('key')} has fields {sorted(g)}")
        for p in g["params"]:
            check(set(p) == {"key", "label", "unit", "min", "max", "step", "value"},
                  f"[BUILDERS] slider {p.get('key')} has fields {sorted(p)}")
            check(p["min"] <= p["value"] <= p["max"],
                  f"[BUILDERS] slider {p['key']} starts outside its range")
    payload = parameters.page_payload(spec)
    check(payload["names"] == list(names) and payload["groups"] == groups,
          "[BUILDERS] page_payload() is not {names, slider_groups}")
    json.dumps(payload)        # must be JSON-serialisable for /pack/parameters.js
    rows = parameters.db_rows(spec)
    check([r["param_name"] for r in rows] == list(names)
          and all(set(r) == {"param_name", "min_value", "max_value", "unit",
                             "description"} for r in rows),
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

    def __init__(self, rows: list[dict] | None = None):
        self.rows = [dict(r) for r in rows or []]
        self.sql: list[str] = []
        self.clock = datetime(2026, 1, 1, tzinfo=timezone.utc)

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
        assert sql == parameter_schema._INSERT_SQL, f"unexpected SQL: {sql}"
        c = self.conn
        c.sql.append("INSERT")
        c.clock += timedelta(minutes=1)
        for v, name, lo, hi, unit, desc in seq:
            assert not any(r["schema_version"] == v and r["param_name"] == name
                           for r in c.rows), "primary key violated"
            assert lo <= hi, "CHECK min_value <= max_value violated"
            c.rows.append({"schema_version": v, "param_name": name,
                           "min_value": float(lo), "max_value": float(hi),
                           "unit": unit, "description": desc,
                           "introduced_at": c.clock, "retired_at": None})

    def fetchall(self):
        return self.result


def _table(version: int, rows: list[dict]) -> list[dict]:
    """*rows* stored as the database returns them: floats, timestamps."""
    t = datetime(2025, 1, version, tzinfo=timezone.utc)
    return [{"schema_version": version, "param_name": r["param_name"],
             "min_value": float(r["min_value"]), "max_value": float(r["max_value"]),
             "unit": r["unit"], "description": r["description"],
             "introduced_at": t, "retired_at": None} for r in rows]


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


def main() -> int:
    spec = parameters.load()
    check_validation(spec)
    n_files = check_drift(spec)
    check_builders(spec)
    check_schema(spec)
    print(f"{parameters.count(spec)} parameters in {len(spec['groups'])} groups; "
          f"{n_files} hand-written parameter list(s) compared")
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - parameters.json is valid, every parameter list agrees with "
          "it, the builders are well-formed and the schema upload behaves "
          "(stand-in database).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
