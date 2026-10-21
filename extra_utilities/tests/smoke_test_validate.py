"""Offline check of Validate (MAS-blueprint P7, ``studio/validate.py``).

1. A SECOND SETUP.  A planter-box configurator is made from a copy of the
   propeller's setup through the Studio's own calls: five parameters in two
   groups (the agents' parameter lists follow), new names, a generator, a
   geometry tool and a helper from the templates, the Download buttons and
   the picture samples pointed at them, the propeller's four tools removed.
   ``python -m studio validate`` answers 0 for it and writes its report: no
   failure and one warning -- the texts that still carry conditions about
   the removed tools (17 files) --; the three tools run clean; every
   topology's prompts are filled in, the Tool Caller's and the Design
   Engineer's too (no tool of this setup declares the render-check block);
   a scripted turn goes through in each topology; the seven developer
   checks pass, the parameter-access check noting the 18 conditions.
2. THE PROPELLER, through the Studio (``validate_start`` /
   ``validate_state``): a second start joins the run, the progress counts
   up, no failure; every part is there (9 loading items, the prompts of
   topologies 3 / 5 / 7, the 12 parameter lists, one item per tool, the
   turn, the seven developer checks); a tool that cannot run on this
   computer is a warning saying what it needs; the report is current, and
   out of date once a file of the setup changes.
3. BROKEN COPIES, each caught by its own check with its reason: a setup
   in a newer format; a parameter file that is not JSON (the lists cannot be checked either) or
   has min above max; a manifest of an unknown kind; the Download buttons
   naming no geometry tool; a picture sample missing a parameter; a text's
   only file deleted; a required secret this computer does not set (a
   warning); a condition about a tool the setup does not have (a warning,
   the file named) and one about a misspelt tool (no warning: the
   parameter-access check fails it, naming the tool meant); a parameter
   list with a changed range or a missing entry; an unknown ``$name`` and
   a stray brace in a text; a helper that raises (a failure) or imports a
   package that is not installed (a warning naming it); a generator that
   writes its picture under another name; a several-line text used inside
   a sentence (the slot-splice check).  On the command line a setup with a
   failure answers 1.
4. CHOICE AND ON/OFF PARAMETERS (MAS-blueprint P6d).  The planter's drain
   holes become on/off and a finish choice is added, used only with drain
   holes; its lists and picture samples are written by hand.  The loading
   checks, the 12 lists, the topology-7 prompts and the parameter check pass;
   then a list with a changed label, a list without the "(only when ...)",
   a sample giving the on/off parameter a number and a default that is not
   one of the choices each fail with their reason.

Takes about five minutes.  Run from the repo root (naming groups runs only
those: ``second``, ``broken``, ``typed``, ``server``):
    py -3.13 extra_utilities/tests/smoke_test_validate.py [second] [broken] [typed] [server]
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ["DATABASE_URL"] = ""
os.environ["DATABASE_PUBLIC_URL"] = ""
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from studio import validate as V                 # noqa: E402
from studio.tools_edit import run_tool_test      # noqa: E402

FAILURES: list[str] = []
PACK = ROOT / "dc_pack"


def check(ok: bool, what: str) -> None:
    if not ok:
        FAILURES.append(what)


def _run(group, tag: str):
    try:
        return group()
    except Exception as exc:                         # noqa: BLE001
        import traceback
        check(False, f"{tag} crashed: {type(exc).__name__}: {exc}\n{traceback.format_exc()[-1500:]}")
        return None


class Studio:
    """``python -m studio --pack <pack>`` on a free port."""

    def __init__(self, pack_dir: Path):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "studio", "--pack", str(pack_dir), "--port", str(self.port),
             "--workers", "0"], cwd=str(ROOT), env=dict(os.environ),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=10)
                return
            except OSError:
                if self.proc.poll() is not None:
                    break
                time.sleep(0.3)
        raise RuntimeError("the Studio did not start")

    def call(self, name: str, *args) -> dict:
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/{name}", method="POST",
            data=json.dumps({"args": list(args)}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            return json.loads(e.read())

    def ok(self, name: str, *args) -> dict:
        d = self.call(name, *args)
        if not d.get("ok"):
            raise RuntimeError(f"{name}: {json.dumps(d)[:1200]}")
        return d

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def copy_of(src: Path, to: Path) -> Path:
    shutil.copytree(src, to, ignore=shutil.ignore_patterns("__pycache__"))
    return to


def edit(path: Path, old: str, new: str, count: int = 1) -> None:
    text = path.read_bytes().decode("utf-8")
    assert text.count(old) >= count, (path, old)
    path.write_bytes(text.replace(old, new, count).encode("utf-8"))


def titles(items: list) -> dict:
    return {i["title"]: i for i in items}


# ---------------------------------------------------------------------------
# 1. a second setup, made through the Studio
# ---------------------------------------------------------------------------

def _param(name, typ, lo, hi, step, default, group, label, unit, desc):
    return {"name": name, "type": typ, "min": lo, "max": hi, "step": step, "default": default,
            "group": group, "label": label, "unit": unit, "db_unit": unit or "count",
            "db_description": desc}


def build_second_setup(tmp: Path) -> Path:
    planter = copy_of(PACK, tmp / "planter_pack")
    shutil.rmtree(planter / "preview", ignore_errors=True)
    st = Studio(planter)
    try:
        data = st.ok("get_all")["data"]
        spec = {
            "groups": [
                {"id": "box", "label": "Box", "image": None, "image_alt": "",
                 "order": ["boxLength", "boxWidth", "boxHeight"]},
                {"id": "walls", "label": "Walls", "image": None, "image_alt": "",
                 "order": ["wallThickness", "drainHoles"]}],
            "parameters": [
                _param("boxLength", "float", 200, 1200, 10, 600, "box", "Length", "mm", "Outer length"),
                _param("boxWidth", "float", 150, 600, 10, 300, "box", "Width", "mm", "Outer width"),
                _param("boxHeight", "float", 100, 600, 10, 250, "box", "Height", "mm", "Outer height"),
                _param("wallThickness", "float", 4, 30, 1, 12, "walls", "Wall thickness", "mm",
                       "Thickness of the side walls"),
                _param("drainHoles", "int", 0, 12, 1, 4, "walls", "Drain holes", "",
                       "Drain holes in the floor")]}
        st.ok("save_parameters", spec, data["params_edit"]["sha"])
        data = st.ok("get_all")["data"]
        by = {s["slot"]: s for s in data["slots"]}
        for slot, text in (("dc_name", "planter box configurator"),
                           ("domain_description", "garden planter boxes")):
            s = by[slot]
            if s["linked"]:
                st.ok("save_field", slot, None, {"all": text}, {"all": s["values"]["7"]})
            else:
                st.ok("save_field", slot, None, {n: text for n in ("7", "5", "3")},
                      {n: s["values"][n] for n in ("7", "5", "3")})
        for name, disp, kind in (("planter_geometry", "Planter geometry", "geometry"),
                                 ("build_planter", "Build planter", "generator"),
                                 ("planter_summary", "Planter summary", "helper")):
            st.ok("new_tool", name, disp, kind, None)
    finally:
        st.stop()
    # pack.yaml: the Download buttons and the picture samples (no Studio screen yet)
    py = planter / "pack.yaml"
    raw = py.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n").replace("  geometry_tool: rhino_geometry",
                                             "  geometry_tool: planter_geometry")
    text = text.partition("render_samples:\n")[0] + (
        "render_samples:\n"
        "  small: {boxLength: 300, boxWidth: 200, boxHeight: 150, wallThickness: 8, drainHoles: 2}\n"
        "  large: {boxLength: 1100, boxWidth: 500, boxHeight: 500, wallThickness: 20, drainHoles: 8}\n")
    py.write_bytes(text.replace("\n", eol).encode("utf-8"))
    st = Studio(planter)
    try:
        # Remove tool lists the texts with a part about the tool: its switch
        # and its settings' conditions alike.
        marked = st.ok("remove_tool_preview", "generate_and_render_propeller")["marked"]
        check(len(marked) >= 17 and "fragments/dc/hard_constraints_dc.t7.md" in marked
              and "fragments/tools/tool_run_history_contents.t5.md" in marked,
              f"[SECOND] Remove tool's texts about the generator: {marked}")
        for tool in ("generate_and_render_propeller", "render_blade_sections",
                     "rhino_geometry", "feg_geometry"):
            st.ok("remove_tool", tool)
    finally:
        st.stop()
    return planter


def check_second(tmp: Path, planter: Path) -> str:
    out = tmp / "planter_report.json"
    proc = subprocess.run([sys.executable, "-m", "studio", "validate", "--pack", str(planter),
                           "--json", str(out)], cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=1200)
    check(proc.returncode == 0, f"[SECOND] python -m studio validate answered {proc.returncode}: "
                                f"{proc.stdout[-1500:]}")
    check("WARN: 24 passed, 1 warning(s), 0 failed" in proc.stdout,
          f"[SECOND] the printed report's last line: {proc.stdout.strip().splitlines()[-1:]}")
    rep = json.loads(out.read_text(encoding="utf-8"))
    items = rep["items"]
    t = titles(items)
    check(rep["status"] == "warn" and rep["counts"] == {"pass": 24, "warn": 1, "fail": 0},
          f"[SECOND] status {rep['status']} {rep['counts']}: "
          f"{[(i['title'], i['lines'][:2]) for i in items if i['status'] != 'pass']}")
    dead = t.get("Text about a tool the setup does not have") or {"lines": [], "status": None}
    check(dead["status"] == "warn" and len(dead["lines"]) == 17
          and all(ln.startswith("planter_pack/fragments/") for ln in dead["lines"]),
          f"[SECOND] the conditions about removed tools: {dead['status']} {dead['lines'][:3]}")
    check(any("render_blade_sections" in ln for ln in dead["lines"])
          and any("generate_and_render_propeller.mesh_checks" in ln for ln in dead["lines"]),
          "[SECOND] the conditions listed do not name the removed tools")
    check([i["part"] for i in items] == ["A"] * 10 + ["B"] * 3 + ["C"] + ["D"] * 3 + ["E"] + ["X"] * 7,
          f"[SECOND] the parts: {[i['part'] for i in items]}")
    for n, agents in ((7, ("Tool Caller",)), (5, ("Tool Caller",)), (3, ("Design Engineer",))):
        b = t.get(f"Topology {n}") or {}
        check(b.get("status") == "pass" and all(a in (b.get("tokens") or {}) for a in agents),
              f"[SECOND] topology {n}: {b.get('status')} {b.get('lines', [])[:3]}")
    for tool in ("build_planter", "planter_geometry", "planter_summary"):
        d = t.get(tool) or {}
        check(d.get("status") == "pass" and d.get("part") == "D",
              f"[SECOND] the tool {tool}: {d.get('status')} {d.get('lines', [])[:3]}")
    check((t.get("12 parameter list(s)") or {}).get("status") == "pass",
          "[SECOND] the 12 parameter lists do not pass")
    check((t.get("One turn per topology, a fake model") or {}).get("status") == "pass",
          "[SECOND] the scripted turn does not pass")
    pa = t.get("Parameter access") or {}
    check(pa.get("status") == "pass" and len(pa.get("notes") or []) == 18,
          f"[SECOND] the parameter-access check: {pa.get('status')}, {len(pa.get('notes') or [])} notes")
    return f"second setup: {rep['counts']} in {rep['seconds']} s"


# ---------------------------------------------------------------------------
# 2. the propeller, through the Studio
# ---------------------------------------------------------------------------

def check_server(tmp: Path) -> str:
    prop = copy_of(PACK, tmp / "prop" / "dc_pack")
    st = Studio(prop)
    try:
        first = st.ok("validate_start")["data"]
        again = st.ok("validate_start")["data"]
        check(first["running"] and again["running"],
              f"[SERVER] validate_start: {first['running']}, then {again['running']}")
        seen, deadline, state = set(), time.time() + 1200, again
        while state["running"] and time.time() < deadline:
            time.sleep(1)
            state = st.ok("validate_state")["data"]
            if state["running"]:
                seen.add((state["done"], state["total"]))
        check(not state["running"], "[SERVER] Validate did not end in 20 minutes")
        check(any(0 < d < n for d, n in seen),
              f"[SERVER] no progress was seen while it ran: {sorted(seen)[:5]}")
        rep = state["report"]
        check(rep is not None and state["current"] and state["error"] is None,
              f"[SERVER] the report: {bool(rep)}, current {state['current']}, {state['error']}")
        if not rep:
            return "no report"
        items = rep["items"]
        tools = sorted(p.parent.name for p in (prop / "tools").glob("*/tool.yaml"))
        check(rep["status"] != "fail",
              f"[SERVER] the propeller fails: {[(i['title'], i['lines'][:2]) for i in items if i['status'] == 'fail']}")
        check([i["part"] for i in items] == ["A"] * 10 + ["B"] * 3 + ["C"] + ["D"] * len(tools)
              + ["E"] + ["X"] * 7, f"[SERVER] the parts: {[i['part'] for i in items]}")
        check([i["title"] for i in items if i["part"] == "D"] == tools,
              f"[SERVER] the tools: {[i['title'] for i in items if i['part'] == 'D']}")
        for i in items:
            if i["part"] == "D" and i["status"] == "warn":
                check(i["lines"][0].startswith("It could not run on this computer: it needs "),
                      f"[SERVER] the warning for {i['title']}: {i['lines'][:2]}")
            if i["part"] != "D" and i["status"] == "warn":
                check(False, f"[SERVER] a warning for the propeller: {i['title']}: {i['lines'][:2]}")
        check(titles(items)["12 parameter list(s)"]["status"] == "pass",
              "[SERVER] the propeller's 12 lists do not pass")
        f = prop / "fragments" / "dc" / "dc_name.md"
        f.write_bytes(f.read_bytes())
        os.utime(f, None)
        later = st.ok("validate_state")["data"]
        check(not later["current"], "[SERVER] a changed file did not make the report out of date")
        return f"propeller: {rep['counts']} in {rep['seconds']} s"
    finally:
        st.stop()


# ---------------------------------------------------------------------------
# 3. broken copies
# ---------------------------------------------------------------------------

def load(copy: Path) -> dict:
    return titles(V._child(["load"], copy))


def prompts7(copy: Path) -> dict:
    return V._prompt_items({("base", 7): V._child(["prompts", "base", "7"], copy)}, V._names())[0]


def tool(copy: Path, name: str) -> dict:
    spec = json.loads((copy / "parameters.json").read_text(encoding="utf-8"))
    return V.tool_item(name, run_tool_test(ROOT, copy, name,
                                           {p["name"]: p["default"] for p in spec["parameters"]}))


def dev(copy: Path, script: str) -> dict:
    return V._script_item("X", script, script, copy)


def has(i: dict, status: str, *words) -> bool:
    text = "\n".join(i.get("lines") or [])
    return i.get("status") == status and all(w in text for w in words)


def check_broken(tmp: Path, planter: Path) -> str:
    n = [0]

    def case(base: Path) -> Path:
        n[0] += 1
        return copy_of(base, tmp / f"broken{n[0]}" / base.name)

    # A: parameters.json
    c = case(PACK)
    (c / "parameters.json").write_text("{ not json", encoding="utf-8")
    got = load(c)
    check(has(got["parameters.json"], "fail", "not valid JSON"),
          f"[BROKEN] parameters.json not JSON: {got['parameters.json']}")
    check(has(got["1 parameter list(s)"] if "1 parameter list(s)" in got else
              got.get("0 parameter list(s)", {}), "fail", "cannot be read"),
          f"[BROKEN] the lists with an unreadable parameters.json: {list(got)}")
    proc = subprocess.run([sys.executable, "-m", "studio", "validate", "--pack", str(c)],
                          cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=1200)
    check(proc.returncode == 1, f"[BROKEN] python -m studio validate answered {proc.returncode} "
                                f"for a broken setup")
    c = case(PACK)
    spec = json.loads((c / "parameters.json").read_text(encoding="utf-8"))
    spec["parameters"][0].update(min=10, max=5)
    (c / "parameters.json").write_text(json.dumps(spec), encoding="utf-8")
    got = load(c)
    check(has(got["parameters.json"], "fail", "must be smaller than max"),
          f"[BROKEN] min above max: {got['parameters.json']}")
    # A: the setup's format
    c = case(PACK)
    edit(c / "pack.yaml", "pack_format: 1", "pack_format: 99")
    check(has(load(c)["The setup's format (pack.yaml)"], "fail", "newer engine"),
          "[BROKEN] a setup in a newer format")
    # A: a manifest, the Download buttons, the samples, a text
    c = case(PACK)
    edit(c / "tools" / "render_blade_sections" / "tool.yaml", "kind: helper", "kind: wizard")
    check(load(c)["The tools' manifests"]["status"] == "fail", "[BROKEN] a manifest of kind wizard")
    c = case(PACK)
    edit(c / "pack.yaml", "geometry_tool: rhino_geometry", "geometry_tool: ghost_tool")
    check(has(load(c)["The Download buttons (pack.yaml)"], "fail", "ghost_tool"),
          "[BROKEN] the Download buttons naming no tool")
    c = case(PACK)
    edit(c / "pack.yaml", "small: {bladeCount: 3, ", "small: {")
    check(has(load(c)["The picture samples (pack.yaml)"], "fail", "small"),
          "[BROKEN] a picture sample missing a parameter")
    c = case(PACK)
    (c / "fragments" / "dc" / "dc_name.md").unlink()
    check(has(load(c)["The texts"], "fail", "$dc_name"), "[BROKEN] a text's only file deleted")
    # A: a required secret, conditions about tools the setup does not have
    c = case(PACK)
    edit(c / "tools" / "render_blade_sections" / "tool.yaml", "list_order: 10",
         "list_order: 10\nsecrets:\n  - {env: QZX_NOT_SET_SECRET, required: true, "
         "description: \"A test secret.\"}")
    sec = load(c)["Secrets the tools need"]
    check(has(sec, "warn", "QZX_NOT_SET_SECRET", "render_blade_sections"),
          f"[BROKEN] a required secret not set: {sec}")
    c = case(PACK)
    f = c / "fragments" / "dc" / "capabilities_cannot.md"
    raw = f.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    f.write_bytes((raw + eol + "<<IF:tool:gone_tool_qzx>>gone<</IF:tool:gone_tool_qzx>>" + eol
                   + "<<IF:tool:render_blade_sectons>>typo<</IF:tool:render_blade_sectons>>"
                   + eol).encode("utf-8"))
    dead = load(c)["Text about a tool the setup does not have"]
    check(has(dead, "warn", "capabilities_cannot.md", "gone_tool_qzx")
          and "render_blade_sectons" not in "\n".join(dead["lines"]),
          f"[BROKEN] a condition about a removed tool and a misspelt one: {dead}")
    pa = dev(c, "smoke_test_parameter_access")
    check(has(pa, "fail", "a misspelling of render_blade_sections"),
          f"[BROKEN] the misspelt tool in the parameter-access check: {pa['lines'][:4]}")
    # C: the lists
    c = case(PACK)
    f = c / "fragments" / "dc" / "parameter_list@tool_caller.t7.md"
    edit(f, "— Number of blades [3; 6]", "— Number of blades [3; 7]")
    lists = load(c)["12 parameter list(s)"]
    check(has(lists, "fail", "parameter_list@tool_caller.t7.md", "bladeCount", "[3; 7]"),
          f"[BROKEN] a list's range changed: {lists}")
    c = case(PACK)
    f = c / "fragments" / "dc" / "parameter_list@tool_caller.t7.md"
    raw = f.read_bytes().decode("utf-8")
    lines = raw.split("\n")
    last = max(i for i, ln in enumerate(lines) if re.match(r"\s*\d+\.\s", ln))
    f.write_bytes("\n".join(lines[:last] + lines[last + 1:]).encode("utf-8"))
    lists = load(c)["12 parameter list(s)"]
    check(has(lists, "fail", "parameter_list@tool_caller.t7.md", "names"),
          f"[BROKEN] a list missing an entry: {lists}")
    # B: an unknown $name, a stray brace
    c = case(PACK)
    f = c / "fragments" / "dc" / "capabilities_cannot.md"
    edit(f, "\n", "\nAlso $not_a_slot_qzx here.\n")
    b = prompts7(c)
    check(has(b, "fail", "$not_a_slot_qzx left unfilled"), f"[BROKEN] an unknown $name: {b}")
    c = case(PACK)
    f = c / "fragments" / "dc" / "capabilities_cannot.md"
    edit(f, "\n", "\nA stray {qzx} brace.\n")
    b = prompts7(c)
    check(has(b, "fail", "could not be filled in"), f"[BROKEN] a stray brace: {b}")
    # D: a helper that raises, or needs a package that is not installed; a picture renamed
    c = case(planter)
    edit(c / "tools" / "planter_summary" / "planter_summary.py",
         '    """Read the attempt\'s parameter values and summarise them."""\n',
         '    """Read the attempt\'s parameter values and summarise them."""\n'
         '    raise RuntimeError("QZX broken on purpose")\n')
    d = tool(c, "planter_summary")
    check(has(d, "fail", "The run failed", "QZX broken on purpose"), f"[BROKEN] a helper that raises: {d}")
    c = case(planter)
    edit(c / "tools" / "planter_summary" / "planter_summary.py", "import json\n",
         "import json\nimport qzx_missing_pkg\n")
    d = tool(c, "planter_summary")
    check(has(d, "warn", "It could not run on this computer: it needs the Python package qzx_missing_pkg"),
          f"[BROKEN] a helper needing a package that is not installed: {d}")
    c = case(planter)
    edit(c / "tools" / "build_planter" / "build_planter.py", 'f"render_{VIEW}.png"', 'f"picture_{VIEW}.png"')
    d = tool(c, "build_planter")
    check(has(d, "fail", "render_build_planter.png", "did not make it"),
          f"[BROKEN] a generator's picture under another name: {d}")
    # X: a several-line text inside a sentence
    c = case(PACK)
    edit(c / "fragments" / "dc" / "capabilities_cannot.md", "\n", "\nSee $parameter_list here.\n")
    x = dev(c, "smoke_test_slot_splices")
    check(x["status"] == "fail" and x["lines"], f"[BROKEN] a slot splice: {x}")
    return f"{n[0]} broken copies"


# ---------------------------------------------------------------------------
# 4. choice and on/off parameters
# ---------------------------------------------------------------------------

FINISH = (" 6. finish (choice) — Surface finish: raw = Raw wood | oiled = Oiled"
          " (only when drainHoles = true)")


def typed_planter(tmp: Path, planter: Path) -> Path:
    """The planter with drainHoles on/off and a finish choice used only with
    drain holes; the 12 lists and the picture samples follow, by hand."""
    c = copy_of(planter, tmp / "typed" / planter.name)
    spec = json.loads((c / "parameters.json").read_text(encoding="utf-8"))
    holes = next(p for p in spec["parameters"] if p["name"] == "drainHoles")
    for k in ("min", "max", "step"):
        holes.pop(k)
    holes.update(type="bool", default=True, db_unit="on/off")
    spec["parameters"].append({
        "name": "finish", "type": "choice",
        "choices": [{"value": "raw", "label": "Raw wood"}, {"value": "oiled", "label": "Oiled"}],
        "default": "raw", "group": "walls", "label": "Finish", "unit": "", "db_unit": "choice",
        "db_description": "Surface finish", "used_when": {"drainHoles": True}})
    next(g for g in spec["groups"] if g["id"] == "walls")["order"].append("finish")
    (c / "parameters.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    files = sorted((c / "fragments" / "dc").glob("parameter_list*.md"))
    for f in files:
        raw = f.read_bytes().decode("utf-8")
        eol = "\r\n" if "\r\n" in raw else "\n"
        lines = raw.replace("\r\n", "\n").split("\n")
        i = next(i for i, ln in enumerate(lines) if re.match(r"\s*5\.\s+drainHoles\b", ln))
        assert "[0; 12]" in lines[i], (f, lines[i])
        lines[i] = re.sub(r" ?\[0; 12\]", ": true | false", lines[i])
        lines.insert(i + 1, FINISH)
        f.write_bytes("\n".join(lines).replace("\n", eol).encode("utf-8"))
    edit(c / "pack.yaml", "wallThickness: 8, drainHoles: 2}",
         "wallThickness: 8, drainHoles: true, finish: oiled}")
    edit(c / "pack.yaml", "wallThickness: 20, drainHoles: 8}",
         "wallThickness: 20, drainHoles: false, finish: raw}")
    return c


def check_typed(tmp: Path, planter: Path) -> str:
    c = typed_planter(tmp, planter)
    got = load(c)
    bad = {t: i for t, i in got.items() if i["status"] == "fail"}
    check(not bad, f"[TYPED] the loading checks fail: {[(t, i['lines'][:2]) for t, i in bad.items()]}")
    check((got.get("12 parameter list(s)") or {}).get("status") == "pass",
          f"[TYPED] the 12 lists: {got.get('12 parameter list(s)')}")
    check((got.get("The picture samples (pack.yaml)") or {}).get("status") == "pass",
          f"[TYPED] the picture samples: {got.get('The picture samples (pack.yaml)')}")
    b = prompts7(c)
    check(b.get("status") == "pass", f"[TYPED] the topology-7 prompts: {b.get('status')} {b.get('lines', [])[:3]}")
    x = dev(c, "smoke_test_parameters")
    check(x.get("status") == "pass", f"[TYPED] the parameter check: {x.get('status')} {x.get('lines', [])[:4]}")
    n = [0]

    def case() -> Path:
        n[0] += 1
        return copy_of(c, tmp / f"typed{n[0]}" / c.name)
    one = "fragments/dc/parameter_list@tool_caller.t7.md"
    d = case()
    edit(d / one, "oiled = Oiled", "oiled = Oil")
    check(has(load(d)["12 parameter list(s)"], "fail", "parameter_list@tool_caller.t7.md",
              'finish does not list "raw = Raw wood | oiled = Oiled"'),
          f"[TYPED] a list with a changed label: {load(d)['12 parameter list(s)']}")
    d = case()
    edit(d / one, " (only when drainHoles = true)", "")
    check(has(load(d)["12 parameter list(s)"], "fail", 'finish does not say "(only when drainHoles = true)"'),
          "[TYPED] a list without the (only when ...)")
    d = case()
    edit(d / "pack.yaml", "drainHoles: true", "drainHoles: 2")
    check(has(load(d)["The picture samples (pack.yaml)"], "fail", "small",
              "its value (a number, one of its choices, or true / false)"),
          f"[TYPED] a sample giving drainHoles a number: {load(d)['The picture samples (pack.yaml)']}")
    d = case()
    edit(d / "parameters.json", '"default": "raw"', '"default": "varnished"')
    check(has(load(d)["parameters.json"], "fail", "finish: default 'varnished' is not one of its choices"),
          "[TYPED] a default that is not one of the choices")
    return f"typed planter: passes, {n[0]} broken copies caught"


def main(argv: list[str]) -> int:
    groups = set(argv) or {"second", "broken", "typed", "server"}
    tmp = Path(tempfile.mkdtemp(prefix="validate_smoke_"))
    summary = []
    try:
        if groups & {"second", "broken", "typed"}:
            planter = _run(lambda: build_second_setup(tmp), "[SECOND]")
            if planter is not None and "second" in groups:
                summary.append(_run(lambda: check_second(tmp, planter), "[SECOND]"))
            if planter is not None and "broken" in groups:
                summary.append(_run(lambda: check_broken(tmp, planter), "[BROKEN]"))
            if planter is not None and "typed" in groups:
                summary.append(_run(lambda: check_typed(tmp, planter), "[TYPED]"))
        if "server" in groups:
            summary.append(_run(lambda: check_server(tmp), "[SERVER]"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("; ".join(str(s) for s in summary))
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - Validate finds no failure in a second, non-propeller setup made through the "
          "Studio, in that setup with choice and on/off parameters, nor in the propeller, says "
          "what this computer lacks as a warning, and catches each broken copy with its reason.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
