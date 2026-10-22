"""A tool from an OpenSCAD model (MAS-blueprint P6f, ``studio/scad_import.py``).

The Studio reads a model's Customizer settings, proposes what each one
becomes, and imports the model -- as a new configurator, or as one more
tool -- with an Undo.  Five groups of checks:

1. READ.  A made-up model with every form the Customizer knows: tabs
   (``[Hidden]`` left out, the reading stops at the first module), the
   description above a setting or after it, drop-downs (labelled, plain,
   quoted, of evenly spaced numbers -- a number -- or not), sliders
   (``[max]``, ``[min:max]``, ``[min:step:max]``), steps, on/off, text,
   an ``[mm, inch]`` pair, lists of numbers, a colour, an expression (not a
   setting), a value over two lines, a setting set twice, the detail
   settings, an ``include``; each row's kind, proposal and parameters,
   exactly; the proposed ranges; the "only when" proposals of the
   "<Base> - <Sub>" tabs; the owner's picks laid over.
2. FILES.  The generator's and the geometry tool's manifests read back as
   meant; ``pack.yaml`` -- a new configurator's one picture sample and
   Download tool, one more tool's defaults added to every sample -- with
   every other line as it was; a new parameter list in each list's shape.
3. SERVER.  The real Studio (``python -m studio``) on a copy of the pack:
   ``scad_read`` (the rows, what each way would do here), the refusals (no
   way chosen, a pick a setting cannot take, a tool or parameter name the
   setup has) writing nothing; a NEW CONFIGURATOR -- the generators and
   geometry tools replaced, the browser preview put aside, the parameters,
   the lists, ``pack.yaml``;
   Validate's own checks of the setup pass (A: it loads, with the "Ranges
   to review" warning; B: every agent's prompt of each topology builds;
   C: every list agrees), the parameter editor's Undo refused while the
   import can be undone, and Undo the import leaves the setup byte for
   byte as it was; ONE MORE TOOL -- a geometry tool beside the propeller's
   generator, the lists and the samples in step, the preview left, Undo
   byte for byte; a file changed after an import makes Undo name it first
   (and undo it when asked); three imports -- the second a new configurator
   with no preview to put aside, a preview made after them named by the
   first one's Undo -- undone, the last first.
4. PAGE.  The Studio page's own functions, run by Node (P6f-2): a range an
   import proposed is kept by every edit of its row but min or max (and by
   a change of type and back), and dropped by Keep; the import dialog's
   counts -- parameters, proposed ranges, "only when" -- and names equal
   the server's for several picks (``apply_picks`` + ``assemble``), and a
   tab's pick keeps only what differs from the proposal.  ``"range":
   "proposed"`` itself is the engine's (the parameter tests check its
   refusals): Validate warns while one is left, its Open showing them.
5. THE REAL MODEL -- when the vacuum hose adapter (``HOSE_ADAPTER_DIR``,
   or ``DCs/vacuum-hose-adapter-openscad-main`` beside a folder above the
   repo) is on this computer, else SKIP; it stays outside the repository
   (its author asks that the script not be hosted).  Its 194 settings in
   23 tabs read as counted by hand; imported as a new configurator, the
   setup passes the engine's check and Validate's A and C; with OpenSCAD
   (``OPENSCAD_PATH`` or the PATH), the geometry tool builds the model of
   the defaults (Test tool).

Run from the repo root:  py -3.13 extra_utilities/tests/smoke_test_scad_import.py
[read] [files] [page] [server] [real]  (the groups to run; all by default)
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from studio import params_edit as PE  # noqa: E402
from studio import scad_import as S  # noqa: E402
from studio import validate as V  # noqa: E402

FAILURES: list[str] = []
HOSE = "vacuum-hose-adapter-openscad-main"


def check(ok: bool, what: str) -> None:
    if not ok:
        FAILURES.append(what)


def _run(group, tag: str):
    try:
        return group()
    except Exception as exc:                                        # noqa: BLE001
        import traceback
        check(False, f"{tag} {type(exc).__name__}: {exc}\n{traceback.format_exc()[-1500:]}")
        return None


# ---------------------------------------------------------------------------
# 1. read
# ---------------------------------------------------------------------------

MODEL = r'''// A made-up model for the Studio's import test (MAS-blueprint P6f).
include <lib/parts.scad>

// a comment before a blank line describes nothing

/* [Body] */
// Wall thickness (mm).
Wall = 2; //0.1
// The style of the end
End_Style = "hose"; // [hose: Hose connector, mag: Magnetic flange, flange: Flange]
Measure = "outer"; //[inner, outer]
Lock = "0"; //["0":none, "3":M3, "3cnc": M3 insert]
Count = 1; //[1, 2, 3, 4]
Odd = 5; //[5, 7, 12]
Angle = 30; // [0:90]
Ratio = 0.5; // [0:0.25:1]
Teeth = 6; // [12]
Barbs = false;
// End diameter (mm, inch)...
Diameter = [50, 0]; //0.5
Offset = [1, -2.5]; // 0.5
Size = [10, 5, 10, 2];
Colour = ["", 1]; //The colour, then its alpha.
Label = "hi \"x\"!";
Derived = Wall * 2;
Twice = 1;
Long = [1,
  2];
Twice = 3;
Neg = -2;
Small = 0.75; // 0.01
Exp = 1e2;

/* [Body - Hose connector] */
Barb_Count = 8;
/*[Body - Magnetic flange] */
Magnets = 6; //1
/* [Body - Extension] */
Ext = 0;

/* [other] */
Debug = false;

/* [Model detail] */
fa = 4;
fs = 0.5;
$fn = 0;
$vpr = [0, 0, 0];

/* [Hidden] */
Secret = 3;

/* [After] */
Later = 1;

module end_of_customizer_opts() {}
NotASetting = 1;
'''


# A second model: one more tool beside an imported generator.
SECOND = "/* [Extra] */\n// Extra length (mm)\nExtra_Len = 5; //[0:20]\n"


def _num(name, typ, lo, hi, step, default, proposed, label=None, unit="", desc=None, **more):
    p = {"name": name, "type": typ, "min": lo, "max": hi, "step": step}
    if proposed:
        p["range"] = "proposed"
    p.update(default=default, label=label or name.replace("_", " "), unit=unit, db_unit=unit,
             db_description=desc or label or name.replace("_", " "))
    p.update(more)
    return p


def _choice(name, pairs, default, desc=None):
    return {"name": name, "type": "choice", "choices": [{"value": v, "label": lab} for v, lab in pairs],
            "default": default, "label": name.replace("_", " "), "unit": "", "db_unit": "",
            "db_description": desc or name.replace("_", " ")}


# setting -> (kind, pick, parameters)
WANT = {
    "Wall": ("number", "parameter", [_num("Wall", "float", 1, 4, 0.1, 2, True, unit="mm",
                                          desc="Wall thickness (mm)")]),
    "End_Style": ("choice", "parameter", [_choice("End_Style", [("hose", "Hose connector"),
                                                                ("mag", "Magnetic flange"), ("flange", "Flange")],
                                                  "hose", "The style of the end")]),
    "Measure": ("choice", "parameter", [_choice("Measure", [("inner", "inner"), ("outer", "outer")], "outer")]),
    "Lock": ("choice", "parameter", [_choice("Lock", [("0", "none"), ("3", "M3"), ("3cnc", "M3 insert")], "0")]),
    "Count": ("choice", "parameter", [_num("Count", "int", 1, 4, 1, 1, False)]),
    "Odd": ("choice", "parameter", [_choice("Odd", [(5, "5"), (7, "7"), (12, "12")], 5)]),
    "Angle": ("number", "parameter", [_num("Angle", "int", 0, 90, 1, 30, False)]),
    "Ratio": ("number", "parameter", [_num("Ratio", "float", 0, 1, 0.25, 0.5, False)]),
    "Teeth": ("number", "parameter", [_num("Teeth", "int", 0, 12, 1, 6, False)]),
    "Barbs": ("bool", "parameter", [{"name": "Barbs", "type": "bool", "default": False, "label": "Barbs",
                                     "unit": "", "db_unit": "", "db_description": "Barbs"}]),
    "Diameter": ("pair", "parameter", [_num("Diameter_mm", "float", 25, 100, 0.5, 50, True,
                                            label="Diameter (mm)", unit="mm", desc="End diameter...")]),
    "Offset": ("vector", "parameter", [_num("Offset_x", "float", 0.5, 2, 0.5, 1, True),
                                       _num("Offset_y", "float", -5, -1, 0.5, -2.5, True)]),
    "Size": ("vector", "parameter", [_num("Size_1", "int", 5, 20, 1, 10, True),
                                     _num("Size_2", "int", 2, 10, 1, 5, True),
                                     _num("Size_3", "int", 5, 20, 1, 10, True),
                                     _num("Size_4", "int", 1, 4, 1, 2, True)]),
    "Colour": ("list", "model", []),
    "Label": ("text", "model", []),
    "Twice": ("number", "parameter", [_num("Twice", "int", 1, 6, 1, 3, True)]),
    "Neg": ("number", "parameter", [_num("Neg", "int", -4, -1, 1, -2, True)]),
    "Small": ("number", "parameter", [_num("Small", "float", 0.37, 1.5, 0.01, 0.75, True)]),
    "Exp": ("number", "parameter", [_num("Exp", "int", 50, 200, 1, 100, True)]),
    "Barb_Count": ("number", "parameter", [_num("Barb_Count", "int", 4, 16, 1, 8, True)]),
    "Magnets": ("number", "parameter", [_num("Magnets", "int", 3, 12, 1, 6, True)]),
    "Ext": ("number", "parameter", [_num("Ext", "int", 0, 10, 1, 0, True)]),
    "Debug": ("bool", "model", [{"name": "Debug", "type": "bool", "default": False, "label": "Debug",
                                 "unit": "", "db_unit": "", "db_description": "Debug"}]),
    "fa": ("number", "detail", None),
    "fs": ("number", "detail", None),
    "$fn": ("number", "detail", []),
    "Later": ("number", "parameter", [_num("Later", "int", 0, 2, 1, 1, True)]),
}


def check_read() -> str:
    f = S.read(MODEL)
    rows = {r["setting"]: r for r in f["rows"]}
    check(list(rows) == list(WANT), f"[READ] the settings: {list(rows)}")
    for name, (kind, pick, params) in WANT.items():
        r = rows.get(name)
        if r is None:
            continue
        check(r["kind"] == kind and r["pick"] == pick, f"[READ] {name}: {r['kind']} / {r['pick']}, "
                                                       f"not {kind} / {pick}")
        if params is not None:
            check(r["parameters"] == params, f"[READ] {name}'s parameters:\n  {r['parameters']}\n  "
                                             f"not {params}")
    check(rows["Colour"]["description"] == "The colour, then its alpha" and rows["Colour"]["picks"] == ["model"],
          f"[READ] a colour: {rows['Colour']}")
    check(rows["Label"]["default"] == 'hi "x"!', f"[READ] a text's escapes: {rows['Label']['default']!r}")
    check(rows["Wall"]["description"] == "Wall thickness (mm)" and rows["Measure"]["description"] == "",
          "[READ] a description is the comment lines just above a setting, and only those")
    check(rows["Debug"]["picks"] == ["parameter", "model"] and rows["fa"]["picks"] == ["detail", "model"]
          and rows["Wall"]["picks"] == ["parameter", "model"], "[READ] the picks a row may take")
    check(rows["Count"]["control"] == "drop-down (4)" and rows["Ratio"]["control"] == "slider 0..1 step 0.25"
          and rows["Wall"]["control"] == "step 0.1" and rows["Barbs"]["control"] == "",
          f"[READ] the controls: {[rows[k]['control'] for k in ('Count', 'Ratio', 'Wall', 'Barbs')]}")
    check(f["includes"] == ["lib/parts.scad"], f"[READ] includes: {f['includes']}")
    check(len(f["notes"]) == 2 and f["notes"][0].startswith("Long (line 27): not read")
          and f["notes"][1].startswith("Twice is set twice"), f"[READ] notes: {f['notes']}")
    whens = {k: r["when"] for k, r in rows.items() if r["when"]}
    check(whens == {"Barb_Count": {"End_Style": "hose"}, "Magnets": {"End_Style": "mag"}},
          f"[READ] the 'only when' proposals: {whens}")
    check(f["groups"] == ["Body", "Body - Hose connector", "Body - Magnetic flange", "Body - Extension",
                          "other", "Model detail", "After"], f"[READ] the tabs: {f['groups']}")
    check(f["counts"] == {"settings": 27, "number": 15, "choice": 5, "bool": 2, "pair": 1, "vector": 2,
                          "list": 1, "text": 1, "parameters": 25, "proposed": 16},
          f"[READ] the counts: {f['counts']}")
    # proposed ranges: half to double, rounded out to the step; 0 to ten steps
    for d, step, want in ((8, 1, (4, 16)), (0, 0.1, (0, 1)), (0, 1, (0, 10)), (0.75, 0.01, (0.37, 1.5)),
                          (-2, 1, (-4, -1)), (2.5, 0.1, (1.2, 5)), (0.05, 0.1, (0, 0.1)), (1, 1, (0, 2))):
        got = S.proposed_range(d, step)
        check(got == want and got[0] <= d <= got[1], f"[READ] proposed range of {d} step {step}: {got}, not {want}")
    # values
    for text, want in (("[40 ,0]", [40, 0]), ("[1, 2,]", [1, 2]), ("-.5", -0.5), ("1e2", 100.0),
                       ('"a\\tb"', "a\tb"), ("true", True), ("[]", []), ('[["", 1], 2]', [["", 1], 2])):
        check(S.literal(text) == want, f"[READ] the value {text}: {S.literal(text)!r}")
    for text in ("Wall * 2", "foo()", "[1, 2", "truex", '"open'):
        try:
            S.literal(text)
            check(False, f"[READ] the expression {text!r} read as a value")
        except S._Unreadable:
            pass
    # the owner's picks
    rows2 = S.apply_picks(f, {"End_Style": "model", "Debug": "parameter", "fa": "model"}, {"Magnets": False})
    by2 = {r["setting"]: r for r in rows2}
    check(by2["Barb_Count"]["when"] is None and by2["Magnets"]["when"] is None and by2["Debug"]["pick"] == "parameter",
          "[READ] a choice left to the model takes its 'only when' with it; a 'when' can be dropped")
    params, groups, parts, detail = S.assemble(rows2)
    check([g["id"] for g in groups] == ["body", "body_hose_connector", "body_magnetic_flange",
                                        "body_extension", "other", "after"]
          and [p["name"] for p in params][:3] == ["Wall", "Measure", "Lock"]
          and all(p["group"] == "body" for p in params[:3]),
          f"[READ] the groups: {[g['id'] for g in groups]}, {[p['name'] for p in params][:4]}")
    check(parts == {"Diameter": ["Diameter_mm", 0], "Offset": ["Offset_x", "Offset_y"],
                    "Size": ["Size_1", "Size_2", "Size_3", "Size_4"]}, f"[READ] parts: {parts}")
    check(detail == {"agent": {"fs": 1, "$fn": 0}, "download": {"fs": 0.5, "$fn": 0}},
          f"[READ] detail (fa left to the model): {detail}")
    for picks, words in (({"Label": "parameter"}, "Label cannot be 'parameter'"),
                         ({"Nope": "model"}, "no setting 'Nope'"), ({"fa": "parameter"}, "fa cannot be")):
        try:
            S.apply_picks(f, picks, None)
            check(False, f"[READ] the pick {picks} was taken")
        except S.EditError as exc:
            check(words in str(exc), f"[READ] the pick {picks}: {exc}")
    return f"{len(rows)} settings read as meant"


# ---------------------------------------------------------------------------
# 2. files
# ---------------------------------------------------------------------------

def check_files() -> str:
    f = S.read(MODEL)
    params, groups, parts, detail = S.assemble(f["rows"])
    files, want = S.generator_files("made_up", "Made up", "made-up.scad", b"cube(1);\n", parts, detail, 30)
    m = yaml.safe_load(files["tool.yaml"])
    check(m == want and m["parts"]["Size"] == ["Size_1", "Size_2", "Size_3", "Size_4"]
          and m["detail"]["agent"] == {"fa": 6, "fs": 1, "$fn": 0} and m["outputs"]["model_file"] == "made_up.obj"
          and files["made-up.scad"] == b"cube(1);\n"
          and files["prompts/tool_list_entry.md"].decode().startswith("**made_up** — build ``made_up.obj``"),
          f"[FILES] the generator: {sorted(files)} {m}")
    files, want = S.geometry_files("made_up_geometry", "Made up geometry", "made-up.scad", b"x", {}, {}, "Made up")
    m = yaml.safe_load(files["tool.yaml"])
    check(m == want and "parts" not in m and "detail" not in m and set(files) == {"tool.yaml", "made-up.scad"}
          and m["description"] == "Builds the Made up model from its parameters with OpenSCAD.",
          f"[FILES] the geometry tool: {m}")
    check(S.tool_name("vacuum-hose-adapter.scad") == "vacuum_hose_adapter"
          and S.display_name("vacuum-hose-adapter.scad") == "Vacuum hose adapter"
          and S.tool_name("3d box.scad") == "model_3d_box" and S.model_file("my model (2).SCAD") == "my-model-2-.scad"
          and S.model_file("../x") == "x.scad", "[FILES] the names made from a file name")
    # pack.yaml
    text = (config.DC_PACK_DIR / "pack.yaml").read_bytes().decode("utf-8").replace("\r\n", "\n")
    data = yaml.safe_load(text)
    defaults = {p["name"]: p["default"] for p in params}
    new = S.pack_yaml(text, "new", defaults, "made_up_geometry")
    a, b = text.split("\n"), new.split("\n")
    changed = [ln for ln in b if ln not in a]
    got = yaml.safe_load(new)
    # ... and no agent gets the primer, which still shows the propeller
    check(got["render_samples"] == {"default": defaults} and got["downloads"] == {"geometry_tool": "made_up_geometry"}
          and got["parameter_access"] == data["parameter_access"]
          and got["primer"] == {"image": data["primer"]["image"], "agents": {7: [], 5: [], 3: []}}
          and changed == ["    7: []", "    5: []", "    3: []", "  geometry_tool: made_up_geometry",
                          "  default: " + yaml_inline(defaults)]
          and [ln for ln in a if ln not in b] == [ln for ln in a if ln.startswith(("    7: [", "    5: [", "    3: ["))]
          + ["  geometry_tool: rhino_geometry"]
          + [ln for ln in a if ln.startswith(("  small:", "  medium:", "  large:"))],
          f"[FILES] pack.yaml for a new configurator: + {changed[:3]}")
    # the samples are written in the file's own layout, never by the fallback
    fallback = S.yaml_patch.patch
    S.yaml_patch.patch = lambda *a, **k: (_ for _ in ()).throw(AssertionError("the fallback was used"))
    try:
        alone = yaml.safe_load(S.pack_yaml(text, "new", defaults, None))
        check(alone["render_samples"] == {"default": defaults} and alone["downloads"] == data["downloads"],
              "[FILES] pack.yaml's samples alone")
        add = S.pack_yaml(text, "add", {"Wall": 2, "End_Style": "hose"}, None)
    finally:
        S.yaml_patch.patch = fallback
    got = yaml.safe_load(add)
    check(all(got["render_samples"][k] == dict(v, Wall=2, End_Style="hose") for k, v in data["render_samples"].items())
          and list(got["render_samples"]["small"])[-2:] == ["Wall", "End_Style"] and got["downloads"] == data["downloads"]
          and sum(1 for x, y in zip(text.split("\n"), add.split("\n")) if x != y) == 3
          and len(add.split("\n")) == len(text.split("\n")), "[FILES] pack.yaml for one more tool")
    # a new list in each list's shape: Validate's own check of it
    spec = PE.normalise({"groups": groups, "parameters": params})
    # Paste CSV: a min or max typed ends the proposal; another field keeps it
    for csv_text, keeps in (("name,min\nWall,0.5\n", False), ("name,max\nWall,9\n", False),
                            ("name,label,min\nWall,Wall X,1\n", True),
                            ("name,type,choices\nWall,choice,a = A | b = B\n", False)):
        got, problems = PE.from_csv(csv_text, spec)
        w = next(p for p in got["parameters"] if p["name"] == "Wall")
        check(not problems and ("range" in w) == keeps, f"[FILES] CSV {csv_text!r}: {w} {problems}")
    lists = sorted((config.DC_PACK_DIR / "fragments" / "dc").glob("parameter_list*.md"))
    from engine import parameters as ep
    for f_ in lists:
        old = f_.read_bytes().decode("utf-8").replace("\r\n", "\n")
        out = PE.fresh_list(spec, old).split("\n")
        entries = PE.parse_entries(out)
        got = [PE._entry_state(out[s:e]) for s, e, _n in entries]
        numbers = [int(PE.ENTRY_RE.match(out[s]).group(2)) for s, _e, _n in entries]
        bad = [p["name"] for (s, e, _n), p in zip(entries, spec["parameters"])
               if ep.entry_problem(p, " ".join(out[s:e]))]
        check([g[0] for g in got] == [p["name"] for p in spec["parameters"]] and not bad
              and numbers == list(range(1, len(numbers) + 1)) and out[0] == "### Body"
              and ("—" in out[1]) == PE._columns(old.split("\n"), PE.parse_entries(old.split("\n")))[3],
              f"[FILES] the new list from {f_.name}: {bad} {out[:3]}")
    return f"manifests, pack.yaml both ways, {len(lists)} new lists"


def yaml_inline(v) -> str:
    from studio import yaml_patch
    return yaml_patch.inline(v)


# ---------------------------------------------------------------------------
# 4. the page (Node)
# ---------------------------------------------------------------------------

STUDIO_JS = ROOT / "studio" / "web" / "studio.js"
PAGE_PIECES = ("NUMERIC", "P_KEYS", "TYPE_KEYS", "clone", "parseNum", "typedType", "entryOf", "retype",
               "withInput", "withoutRanges", "scadView", "scadSetPick", "scadParamText", "scadWhenText",
               "andList", "importDid")


def js_piece(js: str, name: str) -> str:
    """The function or ``var`` statement *name* of studio.js, whole."""
    import re
    m = re.search(r"\n  (function " + name + r"\(|var " + name + r" = )", js)
    i, depth = m.start() + 1, 0
    if m.group(1).startswith("function"):
        for k in range(js.index("{", i), len(js)):
            depth += {"{": 1, "}": -1}.get(js[k], 0)
            if depth == 0:
                return js[i:k + 1]
    for k in range(i, len(js)):
        c = js[k]
        depth += 1 if c in "{[(" else -1 if c in "}])" else 0
        if c == ";" and depth == 0:
            return js[i:k + 1]
    raise ValueError(name)


def run_page(program: str):
    """*program* after the page's pieces, in Node; its JSON answer (None without Node)."""
    import subprocess
    node = shutil.which("node")
    if not node:
        return None
    js = STUDIO_JS.read_text(encoding="utf-8")
    head = "var SAVED = {};\nfunction savedParam(k) { return SAVED[k] || null; }\n"
    src = head + "\n".join(js_piece(js, n) for n in PAGE_PIECES) + "\n" + program
    p = subprocess.run([node], input=src, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if p.returncode != 0:
        check(False, f"[PAGE] the page's functions do not run: {p.stderr[-400:]}")
        return {}
    return json.loads(p.stdout)


def _server_view(found: dict, picks: dict, when: dict) -> dict:
    params, _g, _p, _d = S.assemble(S.apply_picks(found, picks, when))
    return {"parameters": len(params), "proposed": sum(1 for p in params if p.get("range") == "proposed"),
            "when": sum(1 for p in params if "used_when" in p), "names": [p["name"] for p in params]}


def check_page() -> str:
    f = S.read(MODEL)
    cases = [({}, {}), ({"End_Style": "model"}, {}), ({}, {"Magnets": False}),
             ({"Debug": "parameter", "Wall": "model", "fa": "model"}, {"Barb_Count": False})]
    hose = hose_dir()
    sets = [("made-up", f, cases)]
    if hose is not None:
        h = S.read((hose / "combined" / "vacuum-hose-adapter.scad").read_text(encoding="utf-8"))
        sets.append(("hose", h, [({}, {}), ({"End1_Style": "model"}, {"End2_Barbs_Count": False}),
                                 ({"Transition_End2_Count": "model"}, {})]))
    wall = {"name": "Wall", "type": "float", "min": "1", "max": "4", "step": "0.1", "range": "proposed", "default": "2",
            "group": "body", "label": "Wall", "unit": "mm", "db_unit": "mm", "db_description": "Wall thickness"}
    saved = dict(wall, min=1, max=4, step=0.1, default=2)
    choice = {"name": "Style", "type": "choice", "choices": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
              "range": "proposed", "default": "a", "group": "body", "label": "Style", "unit": "", "db_unit": "",
              "db_description": "Style"}
    spec = {"groups": [], "parameters": [saved, dict(saved, name="Other")]}
    program = f"""
var out = {{}};
var f = {json.dumps(wall)};
out.keys = Object.keys(entryOf(f));
out.entry = entryOf(f);
out.label = withInput(f, 'label', 'Wall X').range === 'proposed';
out.unit = withInput(f, 'unit', 'cm').range === 'proposed';
out.min = 'range' in withInput(f, 'min', '0.5');
out.max = 'range' in withInput(f, 'max', '9');
out.untouched = f.range === 'proposed';
var g = clone(f);
retype('Wall', g, 'choice');
out.toChoice = 'range' in g || 'range' in entryOf(g);
SAVED.Wall = {json.dumps(saved)};
retype('Wall', g, 'float');
out.back = g.range === 'proposed' && entryOf(g).range === 'proposed';
out.typed = 'range' in entryOf({json.dumps(choice)});
out.without = withoutRanges({json.dumps(spec)}, ['Wall']);
out.views = {{}};
var SETS = {json.dumps({name: {"rows": found["rows"], "cases": [[p, {k: False for k in w}] for p, w in cs]}
                        for name, found, cs in sets})};
Object.keys(SETS).forEach(function (n) {{
  out.views[n] = SETS[n].cases.map(function (c) {{
    var v = scadView(SETS[n].rows, c[0], c[1]);
    return {{ parameters: v.parameters, proposed: v.proposed, when: v.when, names: v.names }};
  }});
}});
var rows = SETS['made-up'].rows, tab = rows.filter(function (r) {{ return r.group === 'Body'; }});
var picks = {{}};
scadSetPick(picks, tab, 'model');
out.tabModel = clone(picks);
scadSetPick(picks, tab, 'parameter');
out.tabBack = picks;
out.texts = [scadParamText(rows[0].parameters[0]), scadParamText(rows[1].parameters[0]),
             scadParamText(rows.filter(function (r) {{ return r.setting === 'Barbs'; }})[0].parameters[0]),
             scadWhenText({{ End_Style: 'hose' }}), scadWhenText({{ Barbs: true }}),
             importDid({{ mode: 'new', added: ['a', 'a_geometry'], removed: ['g', 'x', 'y'], parameters: 25 }}),
             importDid({{ mode: 'add', added: ['b'], removed: [], parameters: 3 }}),
             importDid({{ mode: 'new', added: ['a', 'a_geometry'], removed: ['g'], preview: true, parameters: 2 }}),
             importDid({{ mode: 'new', added: ['a', 'a_geometry'], removed: [], preview: true, parameters: 2 }})];
process.stdout.write(JSON.stringify(out));
"""
    out = run_page(program)
    if out is None:
        return "SKIP (Node not found)"
    check(out.get("keys") == ["name", "type", "min", "max", "step", "range", "default", "group", "label", "unit",
                              "db_unit", "db_description"] and out.get("entry", {}).get("min") == 1,
          f"[PAGE] a row's entry keeps the proposal, after its step: {out.get('keys')}")
    check(out.get("label") and out.get("unit") and out.get("min") is False and out.get("max") is False
          and out.get("untouched"), f"[PAGE] an input keeps the proposal unless it is min or max: {out}")
    check(out.get("toChoice") is False and out.get("back") is True and out.get("typed") is False,
          f"[PAGE] a change of type drops the proposal, and back brings it: {out}")
    w = (out.get("without") or {}).get("parameters", [{}, {}])
    check("range" not in w[0] and w[1].get("range") == "proposed", f"[PAGE] Keep for one parameter: {w}")
    n = 0
    for name, found, cs in sets:
        for (p, wh), got in zip(cs, out.get("views", {}).get(name, [])):
            want = _server_view(found, p, wh)
            check(got == want, f"[PAGE] {name} {p} {wh}: the dialog's counts {dict(got, names=len(got['names']))} "
                               f"are not the server's {dict(want, names=len(want['names']))}")
            n += 1
    body = [r for r in f["rows"] if r["group"] == "Body"]
    want = {r["setting"]: "model" for r in body if r["pick"] == "parameter" and "model" in r["picks"]}
    check(out.get("tabModel") == want and out.get("tabBack") == {},
          f"[PAGE] a tab's pick: {out.get('tabModel')} / back: {out.get('tabBack')}")
    check(out.get("texts") == ["Wall · float [1; 4]", "End_Style · choice (3)", "Barbs · on/off",
                               "only when End_Style = hose", "only when Barbs = true",
                               "as a new configurator: added a and a_geometry; removed g, x and y; 25 parameters.",
                               "as one more tool: added b and its 3 parameters.",
                               "as a new configurator: added a and a_geometry; removed g and the browser preview; "
                               "2 parameters.",
                               "as a new configurator: added a and a_geometry; removed the browser preview; "
                               "2 parameters."],
          f"[PAGE] the dialog's words: {out.get('texts')}")
    return f"the proposal kept / dropped / kept again; {n} pick sets counted as the server counts them"


# ---------------------------------------------------------------------------
# 3. the server
# ---------------------------------------------------------------------------

def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _validate(pack: Path, prompts: bool = True) -> list[dict]:
    """Validate's A, B (each topology, both combinations) and C on *pack*."""
    load = V._child(["load"], pack)
    if not prompts:
        return load
    jobs = [(c, n) for c, _ in V.COMBOS for n in V.TOPOLOGIES]
    with ThreadPoolExecutor(max_workers=6) as pool:
        got = dict(zip(jobs, pool.map(lambda j: V._child(["prompts", j[0], str(j[1])], pack), jobs)))
    return load + V._prompt_items(got, {})


def _statuses(items: list[dict]) -> dict:
    return {i["title"]: (i["status"], i["lines"][:3]) for i in items}


def check_server(tmp: Path) -> str:
    import smoke_test_studio as SS
    pack = tmp / "dc_pack"
    shutil.copytree(config.DC_PACK_DIR, pack, ignore=shutil.ignore_patterns("__pycache__"))
    ref = SS._snapshot(pack)

    def same(what):
        now = SS._snapshot(pack)
        differ = sorted(set(now) ^ set(ref)) + sorted(k for k in set(now) & set(ref) if now[k] != ref[k])
        check(not differ, f"[SERVER] {what}: the setup is not byte for byte as it was: {differ[:6]}")

    st = SS.Studio(pack)
    try:
        status, r = st.call("scad_read", _b64(MODEL), "made-up.scad")
        check(r.get("ok") and r["counts"]["parameters"] == 25 and r["name"] == "made_up"
              and r["setup"] == {"generators": ["generate_and_render_propeller"],
                                 "geometry": ["feg_geometry", "rhino_geometry"],
                                 "helpers": ["render_blade_sections"], "downloads": "rhino_geometry",
                                 "preview": True,
                                 "parameters": [p["name"] for p in json.loads((pack / "parameters.json").read_text(
                                     encoding="utf-8"))["parameters"]], "add_as": "geometry"},
              f"[SERVER] scad_read: {str(r)[:400]}")
        status, r = st.call("scad_read", _b64("x = foo();\nmodule m() {}\n"), "empty.scad")
        check(r.get("ok") is False and "has no settings" in r.get("error", ""), f"[SERVER] a model without settings: {r}")
        status, r = st.call("scad_read", base64.b64encode(b"\xff\xfe\x00bad").decode(), "bin.scad")
        check(r.get("ok") is False and "not text" in r.get("error", ""), f"[SERVER] a binary file: {r}")
        status, headers, setup_zip = st.get("/download/setup")
        check(status == 200 and setup_zip[:2] == b"PK", f"[SERVER] the setup file: {status}")
        # the engine's check of the result refuses it: nothing written
        blade = pack / "tools/render_blade_sections/tool.yaml"
        blade_raw = blade.read_bytes()
        blade.write_bytes(blade_raw + b"qzx_field: 1\n")
        status, r = st.call("scad_import", _b64(MODEL), "made-up.scad", "new")
        blade.write_bytes(blade_raw)
        check(r.get("ok") is False and "the engine refuses" in r.get("error", "")
              and any("qzx_field" in p for p in r.get("problems", [])), f"[SERVER] the engine's refusal: {str(r)[:300]}")
        same("after the engine refused the result")
        # refusals write nothing
        refusals = [
            (("made-up.scad", None), "Choose how to import"),
            (("made-up.scad", "new", {"Label": "parameter"}), "Label cannot be"),
            (("made-up.scad", "add", None, None, "render_blade_sections"), "already has a tool render_blade_sections"),
            (("made-up.scad", "new", None, None, "Bad Name"), "must be lower case"),
            (("made-up.scad", "add", {k: "model" for k, (_k, p, _x) in WANT.items() if p == "parameter"}),
             "Pick at least one setting"),
        ]
        for args, words in refusals:
            status, r = st.call("scad_import", _b64(MODEL), *args)
            check(r.get("ok") is False and words in r.get("error", ""), f"[SERVER] {args[1:]}: {str(r)[:300]}")
        clash = MODEL.replace("Later = 1;", "Later = 1;\nbladeCount = 4;")
        status, r = st.call("scad_import", _b64(clash), "clash.scad", "add")
        check(r.get("ok") is False and r.get("problems") == ["bladeCount"], f"[SERVER] a parameter clash: {str(r)[:300]}")
        lock = 'Lock = "0"; //["0":none, "3":M3, "3cnc": M3 insert]'
        status, r = st.call("scad_import", _b64(MODEL.replace(lock, 'Lock = "0"; //["0":none, "0":again]')),
                            "dup.scad", "new", {"Lock": "parameter"})
        check(r.get("ok") is False and "Lock cannot be 'parameter'" in r.get("error", ""),
              f"[SERVER] a drop-down of one value made a choice: {str(r)[:200]}")
        same("after the refused imports")
        status, r = st.call("undo_parameters")
        check(r.get("ok") is True, f"[SERVER] the parameter editor's Undo with no import: {str(r)[:200]}")
        same("after the parameter editor's Undo with no import")
        status, r = st.call("scad_undo")
        check(r.get("ok") is False and "no import" in r.get("error", ""), f"[SERVER] Undo with no import: {r}")

        # a new configurator
        status, r = st.call("scad_import", _b64(MODEL), "made-up.scad", "new")
        check(r.get("ok") is True and r["added"] == ["made_up", "made_up_geometry"]
              and r["removed"] == ["feg_geometry", "generate_and_render_propeller", "rhino_geometry"]
              and r["preview"] is True and not (pack / "preview").exists()
              and r["parameters"] == 25 and r["proposed"] == 16 and len(r["lists"]) == 12
              and any("These tools stay: render_blade_sections" in w for w in r["warnings"])
              and any("only the model file was copied" in w for w in r["warnings"]),
              f"[SERVER] a new configurator: {str(r)[:600]}")
        tools = sorted(p.name for p in (pack / "tools").iterdir() if (p / "tool.yaml").is_file())
        spec = json.loads((pack / "parameters.json").read_text(encoding="utf-8"))
        y = yaml.safe_load((pack / "pack.yaml").read_text(encoding="utf-8"))
        check(tools == ["made_up", "made_up_geometry", "render_blade_sections"]
              and (pack / "tools/made_up/made-up.scad").read_text(encoding="utf-8") == MODEL
              and (pack / "tools/made_up_geometry/made-up.scad").read_text(encoding="utf-8") == MODEL
              and len(spec["parameters"]) == 25 and "retired" not in spec
              and y["downloads"]["geometry_tool"] == "made_up_geometry" and list(y["render_samples"]) == ["default"]
              and PE.eol_of((pack / "parameters.json").read_bytes()) == PE.eol_of(ref["parameters.json"])
              and '"step": 0.1, "range": "proposed", "default": 2, "group": "body"' in
              (pack / "parameters.json").read_text(encoding="utf-8"),
              f"[SERVER] the new configurator's files: {tools}")
        status, d = st.call("get_all")
        D = d.get("data") or {}
        made = {t["name"]: t for t in D.get("tools", [])}
        check(D.get("scad_import") == {"mode": "new", "model": "made-up.scad", "added": ["made_up", "made_up_geometry"],
                                       "removed": ["feg_geometry", "generate_and_render_propeller", "rhino_geometry"],
                                       "preview": True, "parameters": 25}
              and "parameters.json" in D.get("changed", []) and "tools/made_up/tool.yaml" in D.get("changed", [])
              and made.get("made_up", {}).get("file") == "tools/made_up/made-up.scad"
              and made.get("made_up_geometry", {}).get("kind") == "geometry",
              f"[SERVER] get_all after the import: {d.get('error', '')[-300:]} {D.get('scad_import')} "
              f"{D.get('changed', [])[:5]} {made.get('made_up')}")
        items = _validate(pack)
        st_ = _statuses(items)
        fails = {k: v for k, v in st_.items() if v[0] == V.FAIL}
        check(not fails and st_.get("Ranges to review", ("",))[0] == V.WARN
              and "16 parameter(s)" in st_["Ranges to review"][1][0]
              and next(i for i in items if i["title"] == "Ranges to review")["link"] == {"section": "parameters",
                                                                                       "filter": "ranges"}
              and st_.get("12 parameter list(s)", ("",))[0] == V.PASS
              and all(st_.get(f"Topology {n}", ("",))[0] == V.PASS for n in V.TOPOLOGIES),
              f"[SERVER] Validate on the new configurator: {fails or st_}")
        status, r = st.call("undo_parameters")
        check(r.get("ok") is False and "Undo the import" in r.get("error", ""),
              f"[SERVER] the parameter editor's Undo during an import: {r}")
        status, r = st.call("scad_undo")
        check(r.get("ok") is True and r["undone"]["mode"] == "new" and r["undone"]["preview"] is True,
              f"[SERVER] Undo the import: {r}")
        same("a new configurator, then Undo the import")
        status, d = st.call("get_all")
        check((d.get("data") or {}).get("scad_import") is None and (d.get("data") or {}).get("changed") == [],
              f"[SERVER] get_all after the Undo: {(d.get('data') or {}).get('changed')}")

        # one more tool
        status, r = st.call("scad_import", _b64(MODEL), "made-up.scad", "add", None, None, "hose_box", "Hose box")
        check(r.get("ok") is True and r["added"] == ["hose_box"] and r["removed"] == [] and len(r["lists"]) == 12
              and r["preview"] is False and (pack / "preview/preview.js").is_file(),
              f"[SERVER] one more tool: {str(r)[:400]}")
        m = yaml.safe_load((pack / "tools/hose_box/tool.yaml").read_text(encoding="utf-8"))
        spec = json.loads((pack / "parameters.json").read_text(encoding="utf-8"))
        y = yaml.safe_load((pack / "pack.yaml").read_text(encoding="utf-8"))
        check(m["kind"] == "geometry" and m["display_name"] == "Hose box" and len(spec["parameters"]) == 16 + 25
              and [g["id"] for g in spec["groups"]][-5:] == ["body", "body_hose_connector", "body_magnetic_flange",
                                                             "body_extension", "after"]
              and all(len(v) == 41 for v in y["render_samples"].values()) and y["downloads"]["geometry_tool"] == "rhino_geometry",
              f"[SERVER] one more tool's files: {m.get('kind')} {len(spec['parameters'])}")
        check(SS._lists_agree(pack, sorted(f"fragments/dc/{p.name}" for p in (pack / "fragments/dc").glob(
            "parameter_list*.md")), spec, "one more tool"), f"[SERVER] one more tool: the lists: {SS.FAILURES[-1:]}")
        items = _validate(pack, prompts=False)
        fails = {k: v for k, v in _statuses(items).items() if v[0] == V.FAIL}
        check(not fails, f"[SERVER] Validate on one more tool: {fails}")
        # a change after the import: Undo names it first
        p = pack / "parameters.json"
        p.write_bytes(p.read_bytes().replace(b'"label": "Wall"', b'"label": "Wall!"'))
        t = pack / "tools/hose_box/tool.yaml"
        t.write_bytes(t.read_bytes() + b"# qzx\n")
        status, r = st.call("scad_undo")
        check(r.get("ok") is False and r.get("problems") == ["parameters.json", "tools/hose_box/"],
              f"[SERVER] Undo after a change: {r}")
        status, r = st.call("scad_undo", True)
        check(r.get("ok") is True, f"[SERVER] Undo anyway: {r}")
        same("one more tool, a change, then Undo anyway")

        # three imports, undone the last first
        moved = []
        for source, args in ((MODEL, ("made-up.scad", "new")),
                             (MODEL, ("made-up.scad", "new")),
                             (SECOND, ("second.scad", "add", None, None, "second", "Second"))):
            status, r = st.call("scad_import", _b64(source), *args)
            check(r.get("ok") is True, f"[SERVER] import {args[1]}: {str(r)[:300]}")
            moved.append(r.get("preview"))
            if len(moved) == 1:
                status, r = st.call("scad_read", _b64(MODEL), "made-up.scad")
                check(r.get("ok") and r["setup"]["preview"] is False,
                      f"[SERVER] scad_read once the preview is aside: {r.get('setup')}")
        check(moved == [True, False, False], f"[SERVER] the preview put aside by the first import only: {moved}")
        m = yaml.safe_load((pack / "tools/second/tool.yaml").read_text(encoding="utf-8"))
        check(m["kind"] == "geometry", f"[SERVER] one more tool beside an imported generator: {m['kind']}")
        for _ in range(2):
            status, r = st.call("scad_undo")
            check(r.get("ok") is True and r["undone"]["preview"] is False, f"[SERVER] Undo: {r}")
        check(not (pack / "preview").exists(), "[SERVER] the preview came back before its own import's Undo")
        # a preview made since: the first import's Undo names it, and puts the old one back when asked
        (pack / "preview").mkdir()
        (pack / "preview/preview.js").write_text("export function buildModel() { return null; }\n", encoding="utf-8")
        status, r = st.call("scad_undo")
        check(r.get("ok") is False and r.get("problems") == ["preview/"], f"[SERVER] Undo after a preview was made: {r}")
        status, r = st.call("scad_undo", True)
        check(r.get("ok") is True and r["undone"]["preview"] is True, f"[SERVER] Undo anyway: {r}")
        same("three imports and a preview made since, then three Undos")
        # a setup file opened after an import: the import can no longer be undone
        status, r = st.call("scad_import", _b64(MODEL), "made-up.scad", "new")
        status, r = st.call("open_setup", base64.b64encode(setup_zip).decode("ascii"), "dc_setup.zip")
        check(r.get("ok") is True, f"[SERVER] Open setup file: {str(r)[:300]}")
        status, d = st.call("get_all")
        status, r = st.call("scad_undo")
        check((d.get("data") or {}).get("scad_import") is None and r.get("ok") is False
              and "no import" in r.get("error", ""), f"[SERVER] an import after Open setup file: {r}")
        same("an import, then Open setup file")
    finally:
        st.stop()
    return ("read, 10 refusals, a new configurator (Validate A-C, the preview put aside) and one more tool, "
            "each undone byte for byte; Open setup file ends an import's Undo")


# ---------------------------------------------------------------------------
# 5. the real model
# ---------------------------------------------------------------------------

def hose_dir() -> Path | None:
    raw = os.getenv("HOSE_ADAPTER_DIR")
    if raw:
        return Path(raw) if Path(raw).is_dir() else None
    return next((p / "DCs" / HOSE for p in ROOT.parents if (p / "DCs" / HOSE).is_dir()), None)


def check_real(tmp: Path) -> str:
    folder = hose_dir()
    if folder is None:
        return f"SKIP (the hose adapter is not on this computer: set HOSE_ADAPTER_DIR to {HOSE})"
    model = folder / "combined" / "vacuum-hose-adapter.scad"
    text = model.read_text(encoding="utf-8")
    f = S.read(text)
    check(f["counts"] == {"settings": 194, "number": 131, "choice": 34, "pair": 6, "text": 3, "bool": 10,
                          "vector": 5, "list": 5, "parameters": 187, "proposed": 146} and len(f["groups"]) == 23
          and not f["notes"] and not f["includes"], f"[REAL] the counts: {f['counts']} {len(f['groups'])} {f['notes']}")
    rows = {r["setting"]: r for r in f["rows"]}
    whens = {}
    for r in f["rows"]:
        whens.setdefault(r["group"], set()).add(json.dumps(r["when"]))
    check(rows["End1_Diameter"]["parameters"][0]["name"] == "End1_Diameter_mm"
          and rows["Transition_End2_Count"]["parameters"][0]["type"] == "int"
          and rows["End1_Magnet_Twist_Lock_Size"]["parameters"][0]["choices"][2] == {"value": "3cnc",
                                                                                     "label": "M3 with CNC Kitchen insert"}
          and whens["Connector 2 - Magnetic Flange"] == {'{"End2_Style": "mag"}'}
          and whens["Connector 3 - Nozzle"] == {'{"End3_Style": "nozzle"}'}
          and whens["Connector 1 - Extension"] == {"null"}
          and sum(1 for r in f["rows"] if r["when"]) == 92,
          f"[REAL] the rows: {[(k, v) for k, v in whens.items() if v != {'null'}][:4]}")
    # a new configurator, by the importer itself (the engine's checks in their own process)
    from studio import server as SV
    from studio import tools_edit as TE
    pack = tmp / "hose" / "dc_pack"
    shutil.copytree(config.DC_PACK_DIR, pack, ignore=shutil.ignore_patterns("__pycache__"))
    opened = tmp / "hose" / "opened" / "dc_pack"
    shutil.copytree(pack, opened)
    checker = SV.Checker(pack)
    try:
        params = PE.ParamsEditor(pack, opened, checker.check)
        tools = TE.ToolsEditor(pack, opened, checker.check_tools, ROOT)
        imp = S.Importer(pack, opened, checker.check_setup, params, tools)
        data = {"slot_specs": {"parameter_list": {"dir": "fragments/dc"}}}
        r = imp.run(data, base64.b64encode(model.read_bytes()).decode(), model.name, "new")
        check(r["added"] == ["vacuum_hose_adapter", "vacuum_hose_adapter_geometry"] and r["parameters"] == 187
              and r["preview"] is True and not (pack / "preview").exists(), f"[REAL] the import: {r}")
        items = _validate(pack, prompts=False)
        st_ = _statuses(items)
        fails = {k: v for k, v in st_.items() if v[0] == V.FAIL}
        check(not fails and "146 parameter(s)" in st_["Ranges to review"][1][0],
              f"[REAL] Validate on the hose configurator: {fails}")
        built = "OpenSCAD not on this computer: the model not built"
        if (os.getenv("OPENSCAD_PATH") or "").strip() or shutil.which("openscad"):
            spec = json.loads((pack / "parameters.json").read_text(encoding="utf-8"))
            rep = TE.run_tool_test(ROOT, pack, "vacuum_hose_adapter_geometry",
                                   {p["name"]: p["default"] for p in spec["parameters"]}, None, 600)
            check(not rep.get("failed") and (rep.get("model") or {}).get("vertices", 0) > 1000,
                  f"[REAL] the geometry tool on the defaults: {rep.get('error')} {rep.get('model')} {rep.get('output', [])[-5:]}")
            built = f"the defaults built by OpenSCAD ({(rep.get('model') or {}).get('vertices')} vertices)"
        imp.undo(data)
        now = {p.relative_to(pack).as_posix(): p.read_bytes() for p in pack.rglob("*")
               if p.is_file() and "__pycache__" not in p.parts}
        then = {p.relative_to(opened).as_posix(): p.read_bytes() for p in opened.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts}
        check(now == then, f"[REAL] Undo the import: {sorted(set(now) ^ set(then))[:5]}")
        imp.close()
    finally:
        checker.close()
    return f"194 settings read; imported (Validate A and C); {built}; undone"


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="scad_import_smoke_"))
    only = set(sys.argv[1:]) or {"read", "files", "page", "server", "real"}
    read = files = page = server = real = "not run"
    try:
        if "read" in only:
            read = _run(check_read, "[READ]")
        if "files" in only:
            files = _run(check_files, "[FILES]")
        if "page" in only:
            page = _run(check_page, "[PAGE]")
        if "server" in only:
            server = _run(lambda: check_server(tmp), "[SERVER]")
        if "real" in only:
            real = _run(lambda: check_real(tmp), "[REAL]")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"read: {read}; files: {files}; page: {page}; server: {server}; real: {real}")
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - a model's Customizer settings are read and proposed as parameters, detail or the "
          "model's own, imported as a new configurator or one more tool that the engine and Validate "
          "accept, and each import is undone byte for byte.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
