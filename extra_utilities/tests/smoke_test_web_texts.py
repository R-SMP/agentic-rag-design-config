"""The web page's configurator words and tools, offline: from the pack.

Since MAS-blueprint P4c the page names the configurator only through the
pack: ``web_app.py`` fills ``web/index.html``'s ``$name`` words as it serves
it (HTML-escaped, ``agents/shared/pack_text.py``), and hands the page's
script the words and tools it needs in ``/pack/page.js``.  Four groups of
checks, against the real FastAPI app (only packages that are not installed
are stubbed; no database):

1. PAGE.  The start page (``/``) offers the configurator and the MAS
   Studio, in the pack's words.  With the propeller pack the configurator's
   page (``/configurator``) shows exactly the texts it carried
   before (the title, the chat box, the empty viewer and its Download
   button, the database-entry example and checkbox), the Parameters page's
   Download button names the geometry tool chosen for downloads, the
   Copy-parameters button gives the parameter count from the pack, no
   ``$name`` is left unfilled, and ``/pack/page.js`` carries the words, the
   tools and the generator's model (file, format, up axis).
2. PACK WORDS.  With a copy of the pack whose words are stand-ins (one of
   them with ``<`` and ``&``), the page and ``/pack/page.js`` say the
   stand-ins, escaped, and no longer the propeller's texts.
3. TOOLS.  The tools ``/pack/page.js`` lists for the flowchart's TOOLS panel
   and the LLM routing chart: the pack's switched-on tools (generators
   first) then the engine's standard ones; a switched-off tool is not
   listed; and every ``@generic_tool`` name in the code is in
   ``agent_activity.STANDARD_TOOLS``, and every name there is used.
4. RETIRED.  A record carrying a name ``parameters.json`` lists as retired
   is read without it by the web app's preview check and by
   ``propose_attempt``.
5. PREVIEW.  The pack's browser preview module and pictures are served
   (/pack/preview/, /pack/assets/), ``/pack/page.js`` says the pack has a
   preview, the slider page's group pictures point there, the
   render-compression panel offers the pack's sample sizes and shows the
   pack's own samples; and -- under Node, when ``three`` resolves -- the
   module exports the contract and builds the model, its extra view and
   its group figures from the default parameters.
6. TYPES (MAS-blueprint P6d).  The slider page's tabs are not written into
   ``index.html`` (the page makes one per group of parameters.json); and --
   under Node -- the page's own code for choice and on/off parameters and
   "only when" (cut out of ``web/app.js``, a stand-in for the rows): which
   rows hide, what the FIXED block and Copy parameters say (a hidden
   parameter is left out), what "Use these parameters" fixes, what a
   proposal changes (a FIXED row keeps its value) and how it reads, which
   values fit.  With that setup as the pack, the server: the page and its
   parameters are served, the preview check, ``propose_attempt`` and a
   manual database entry (a stand-in writer) take a choice's value and
   true / false as they are and refuse one that does not fit.
7. ONE DEPLOY.  The MAS Studio inside this server, at ``/studio/``: nothing
   of it is made until it is first opened; then its shared setup is a copy
   of the pack (the pack itself untouched), it asks for the configurator's
   own access code, its link to the configurator is ``/configurator``, and
   its page, scripts, guide, pictures and downloads answer under
   ``/studio/`` (its page names no address from the server's root).
   Without an access code it is open, as the configurator is.

Run from the repo root:  py -3.13 extra_utilities/tests/smoke_test_web_texts.py
"""
from __future__ import annotations

import importlib.abc
import importlib.machinery
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
os.environ["DATABASE_URL"] = ""
os.environ["DATABASE_PUBLIC_URL"] = ""
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

# Heavy runtime packages the page never touches; stubbed only when they are
# not installed (the finder runs last).
_STUB_ROOTS = {"trimesh", "pyrender", "pyvista", "rhino3dm", "compute_rhino3d",
               "voyageai", "manifold3d", "mapbox_earcut", "embreex", "vtk",
               "fast_simplification", "xatlas", "DracoPy", "collada", "pycollada"}


class _Loader(importlib.abc.Loader):
    def create_module(self, spec):
        m = MagicMock(name=spec.name)
        m.__name__, m.__path__, m.__spec__, m.__all__ = spec.name, [], spec, []
        return m

    def exec_module(self, module):
        return None


class _LastResort(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in _STUB_ROOTS:
            return importlib.machinery.ModuleSpec(fullname, _Loader(), is_package=True)
        return None


sys.meta_path.append(_LastResort())

import config  # noqa: E402
import web_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agents.shared.agent_activity import STANDARD_TOOLS  # noqa: E402
from engine import pack_tools, parameters  # noqa: E402

FAILURES: list[str] = []
CLIENT = TestClient(web_app.app)

# The texts the page carried before P4c, which the propeller pack must still
# produce.
PROPELLER_TEXTS = [
    "<title>Propeller Design Configurator</title>",
    "<h1>Propeller Design Configurator</h1>",
    'placeholder="Describe the propeller you want to design…"',
    "No model yet — generate a propeller and it will appear here.",
    'placeholder="e.g. A five-blade ring propeller with a deliberately thin ring..."',
    "Is this a render of a propeller generated with our design tool?",
    'title="Save the displayed .obj mesh"',
]
# Written since P4c (b): the Parameters page's Download button names the
# geometry tool chosen for downloads (pack.yaml's default: RhinoCompute).
PAGE_TEXTS_P4C = [
    'title="Generate and download the geometry made by RhinoCompute (.obj)"',
    'title="Copy the canonical 16-parameter list to your clipboard"',
]
MODEL = {"file": "propeller_mesh.obj", "ext": ".obj", "format": "obj",
         "media_type": "model/obj", "up_axis": "z"}

# Stand-in words for the PACK WORDS check: pack file -> text.
_STAND_INS = {
    "fragments/dc/app_title.md": "Turbine <Studio> & Co",
    "fragments/dc/dc_name.md": "turbine",
    "fragments/dc/manual_entry_text_example.md": "A three-vane turbine with a wide hub...",
    "fragments/tools/output_image.md": "drawing",
    "fragments/tools/output_model.md": "widget",
}


def check(ok: bool, what: str) -> None:
    if not ok:
        FAILURES.append(what)


def _page_js() -> dict:
    r = CLIENT.get("/pack/page.js")
    prefix = "window.PACK_PAGE = "
    check(r.status_code == 200 and "javascript" in r.headers.get("content-type", "")
          and r.text.startswith(prefix), f"[PAGE] /pack/page.js: {r.status_code} {r.text[:80]!r}")
    return json.loads(r.text[len(prefix):].rstrip().rstrip(";"))


def check_page() -> None:
    r = CLIENT.get("/")
    start = r.text
    check(r.status_code == 200 and "text/html" in r.headers.get("content-type", "")
          and "<title>Propeller Design Configurator</title>" in start
          and 'href="/configurator"' in start and 'href="/studio/"' in start
          and "<h2>The propeller configurator</h2>" in start and "<h2>MAS Studio</h2>" in start
          and not re.findall(r"\$[A-Za-z_]", start),
          f"[PAGE] the start page (GET /): {r.status_code} {start[:120]!r}")
    r = CLIENT.get("/configurator")
    page = r.text
    check(r.status_code == 200 and "text/html" in r.headers.get("content-type", ""),
          f"[PAGE] GET /configurator answered {r.status_code} {r.headers.get('content-type')}")
    for text in PROPELLER_TEXTS + PAGE_TEXTS_P4C:
        check(page.count(text) == 1, f"[PAGE] the page does not show {text!r} once")
    left = sorted(set(re.findall(r"\$[A-Za-z_][A-Za-z0-9_]*", page)))
    check(not left, f"[PAGE] unfilled words on the page: {left}")
    check("\\d{6}$</code>" in page, "[PAGE] the page's literal dollar sign ($$) is not a '$'")
    check('<script src="/pack/page.js"></script>' in page, "[PAGE] the page does not load /pack/page.js")
    js = _page_js()
    check(js["words"] == {"dc_name": "propeller", "output_model": "mesh"},
          f"[PAGE] /pack/page.js words: {js['words']}")
    check(js["model"] == MODEL, f"[PAGE] /pack/page.js model: {js['model']}")
    # The Download choice reaches the Parameters page's button.
    try:
        pack_tools.settings_override_for_tests({"downloads": {"geometry_tool": "feg_geometry"}})
        check('title="Generate and download the geometry made by FEG (.obj)"'
              in CLIENT.get("/configurator").text, "[PAGE] the Download choice does not reach the page")
        pack_tools.settings_override_for_tests({"downloads": {"geometry_tool": "saved"}})
        check('title="Generate and download the geometry made by FEG (.obj)"'
              in CLIENT.get("/configurator").text,
              "[PAGE] with the saved file chosen, the page does not name the generator's tool")
    finally:
        pack_tools.settings_override_for_tests(None)


def check_pack_words() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="web_words_"))
    shutil.copytree(ROOT / "dc_pack", tmp / "dc_pack",
                    ignore=shutil.ignore_patterns("__pycache__"))
    for rel, text in _STAND_INS.items():
        (tmp / "dc_pack" / rel).write_text(text + "\n", encoding="utf-8")
    real = config.DC_PACK_DIR
    try:
        config.DC_PACK_DIR = tmp / "dc_pack"
        check("<h2>The turbine configurator</h2>" in CLIENT.get("/").text,
              "[PACK WORDS] the start page does not name the stand-in configurator")
        page = CLIENT.get("/configurator").text
        for text in ("<title>Turbine &lt;Studio&gt; &amp; Co</title>",
                     "<h1>Turbine &lt;Studio&gt; &amp; Co</h1>",
                     'placeholder="Describe the turbine you want to design…"',
                     "No model yet — generate a turbine and it will appear here.",
                     'placeholder="e.g. A three-vane turbine with a wide hub..."',
                     "Is this a drawing of a turbine generated with our design tool?",
                     'title="Save the displayed .obj widget"'):
            check(text in page, f"[PACK WORDS] the page does not show {text!r}")
        for text in PROPELLER_TEXTS:
            check(text not in page, f"[PACK WORDS] the page still shows {text!r}")
        words = _page_js()["words"]
        check(words == {"dc_name": "turbine", "output_model": "widget"},
              f"[PACK WORDS] /pack/page.js words: {words}")
    except Exception as exc:                                        # noqa: BLE001
        check(False, f"[PACK WORDS] {type(exc).__name__}: {str(exc)[:200]}")
    finally:
        config.DC_PACK_DIR = real
        shutil.rmtree(tmp, ignore_errors=True)
    return len(_STAND_INS)


_GENERIC_RE = re.compile(r"@generic_tool\(\s*\"([^\"]+)\"\s*\)")


def check_tools() -> None:
    tools = _page_js()["tools"]
    want = [{"name": "generate_and_render_propeller", "label": "Propeller Configurator"},
            {"name": "render_blade_sections", "label": "Blade Sections"}]
    check(tools["pack"] == want, f"[TOOLS] pack tools: {tools['pack']}")
    check(tools["standard"] == list(STANDARD_TOOLS), f"[TOOLS] standard tools: {tools['standard']}")
    try:
        pack_tools.settings_override_for_tests({"render_blade_sections": {"enabled": False}})
        off = _page_js()["tools"]["pack"]
        check(off == want[:1], f"[TOOLS] with blade sections switched off: {off}")
    finally:
        pack_tools.settings_override_for_tests(None)
    used = set()
    for folder in ("agents", "tools", "engine"):
        for f in (ROOT / folder).rglob("*.py"):
            used |= set(_GENERIC_RE.findall(f.read_text(encoding="utf-8")))
    check(used - set(STANDARD_TOOLS) == set(),
          f"[TOOLS] @generic_tool names missing from STANDARD_TOOLS: {sorted(used - set(STANDARD_TOOLS))}")
    check(set(STANDARD_TOOLS) - used == set(),
          f"[TOOLS] STANDARD_TOOLS names no tool reports: {sorted(set(STANDARD_TOOLS) - used)}")
    check(len(set(STANDARD_TOOLS)) == len(STANDARD_TOOLS), "[TOOLS] STANDARD_TOOLS lists a name twice")


def check_retired() -> None:
    retired = parameters.retired()
    check(retired == ("impellerHeight",), f"[RETIRED] parameters.json lists {retired}")
    record = {p["name"]: p["default"] for p in parameters.load()["parameters"]}
    stray = dict(record, **{n: 1.0 for n in retired})
    try:
        got = web_app._coerce_preview_params(stray)
        check(set(got) == set(record), f"[RETIRED] the preview check kept {sorted(set(got) - set(record))}")
    except ValueError as exc:
        check(False, f"[RETIRED] the preview check rejected a record with a retired name: {exc}")
    from agents.receptionist import propose_attempt_tool as P
    att = Path(tempfile.mkdtemp(prefix="web_retired_")).resolve()
    real = (P.ATTEMPTS_DIR, P.publish)
    sent: list = []
    try:
        P.ATTEMPTS_DIR, P.publish = att, sent.append
        folder = att / "20260101_000000_001_x"
        folder.mkdir()
        (folder / "parameters.json").write_text(json.dumps(stray), encoding="utf-8")
        answer = P.propose_attempt.invoke({"parameters_path": str(folder / "parameters.json")})
        check(answer.startswith("Surfaced") and len(sent) == 1
              and set(sent[0]["values"]) == set(record),
              f"[RETIRED] propose_attempt: {answer[:120]!r}, sent {sent}")
    finally:
        P.ATTEMPTS_DIR, P.publish = real
        shutil.rmtree(att, ignore_errors=True)


def _run(group, tag: str):
    """*group*(), reporting a crash under its tag."""
    try:
        return group()
    except Exception as exc:                                        # noqa: BLE001
        check(False, f"{tag} {type(exc).__name__}: {str(exc)[:200]}")
        return 0


_NODE_CONTRACT = r'''
import { pathToFileURL } from "node:url";
const mod = await import(pathToFileURL(process.env.PREVIEW_JS).href);
const params = JSON.parse(process.env.PREVIEW_PARAMS);
const THREE = await import("three");
const model = mod.buildModel(params, new THREE.MeshStandardMaterial());
let meshes = 0, lines = 0;
model.traverse((c) => { if (c.isMesh) meshes++; if (c.userData && c.userData.isProfileLine) lines++; });
mod.highlightGroup(model, "inner");
console.log(JSON.stringify({
  exports: Object.keys(mod).sort(), meshes, lines,
  views: mod.views.map((v) => v.id), groups: mod.groupFigures,
  title: typeof mod.modelTitle,
}));
'''


def check_preview() -> str:
    import subprocess
    js = _page_js()
    check(js.get("preview") is True, f"[PREVIEW] /pack/page.js preview: {js.get('preview')}")
    r = CLIENT.get("/pack/preview/preview.js")
    check(r.status_code == 200 and "buildModel" in r.text,
          f"[PREVIEW] /pack/preview/preview.js: {r.status_code}")
    for path in ("/pack/preview/feg/propeller.js", "/pack/assets/general-profile.png",
                 "/pack/assets/render_samples/cross_small.png"):
        check(CLIENT.get(path).status_code == 200, f"[PREVIEW] {path} is not served")
    groups = parameters.load()["groups"]
    check(all(g["image"] == f"/pack/assets/{g['id']}-profile.png" for g in groups),
          f"[PREVIEW] group pictures: {[g['image'] for g in groups]}")
    d = CLIENT.get("/api/render_compression").json()
    check(d["sizes"] == ["small", "medium", "large"] and d["cross_available"] is True,
          f"[PREVIEW] render compression: {d}")
    s = CLIENT.get("/api/render_compression/sample",
                   params={"kind": "cross", "size": "small", "degree": 0}).json()
    check(s.get("preview") == "/pack/assets/render_samples/cross_small.png",
          f"[PREVIEW] the pack's sample is not what the panel shows: {s.get('preview')}")
    # The module's contract, under Node (as feg_geometry's exporter runs it).
    params = {p["name"]: p["default"] for p in parameters.load()["parameters"]}
    # --eval resolves "three" from the working directory (the repo root).
    env = dict(os.environ, PREVIEW_JS=str(ROOT / "dc_pack" / "preview" / "preview.js"),
               PREVIEW_PARAMS=json.dumps(params))
    try:
        p = subprocess.run(["node", "--input-type=module", "-e", _NODE_CONTRACT],
                           capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=120)
    except FileNotFoundError:
        return "SKIP (no node)"
    if p.returncode != 0 and "Cannot find package 'three'" in p.stderr:
        return "SKIP (three not installed)"
    if p.returncode != 0:
        check(False, f"[PREVIEW] the module failed under Node: {p.stderr.strip()[-300:]}")
        return "failed"
    got = json.loads(p.stdout.strip().splitlines()[-1])
    check(got["exports"] == ["buildModel", "drawGroupFigure", "groupFigures",
                              "highlightGroup", "modelTitle", "views"]
          and got["meshes"] > 0 and got["lines"] == 3 and got["views"] == ["sections"]
          and got["groups"] == ["inner", "middle", "outer"] and got["title"] == "string",
          f"[PREVIEW] the module's contract under Node: {got}")
    return f"{got['meshes']} meshes, {got['lines']} section outlines"


# The page's own functions, cut out of web/app.js (they end at a "}" in the
# first column).
_PAGE_FUNCTIONS = ("paramsFormatValue", "paramsFormatValueWithUnit", "paramsPicked", "paramsSame",
                   "paramsFits", "paramsValueText", "paramsShownValue", "paramsIsUsed",
                   "paramsApplyUsedWhen", "paramsBuildFixedParamsDict", "paramsBuildSubmitMessage",
                   "paramsSetState", "paramsSetPick", "paramsFixAll", "paramsApplyProposal")

_NODE_TYPES = r'''
const groups = JSON.parse(process.env.GROUPS);
var PARAM_GROUPS = groups;
var PACK_PAGE = { words: { dc_name: "test configurator" } };
var paramSpecByKey = {}, paramState = {}, paramRowState = {}, rows = {}, els = {};
for (const g of groups) for (const p of g.params) {
  paramSpecByKey[p.key] = p; paramState[p.key] = p.value; paramRowState[p.key] = "vary";
}
var document = {
  querySelector: (sel) => {
    const m = /data-param-key="([^"]+)"/.exec(sel);
    return m ? (rows[m[1]] = rows[m[1]] || { hidden: false, dataset: {}, querySelector: () => null })
             : null;
  },
  getElementById: (id) => (els[id] = els[id] || { textContent: "", value: "", checked: false }),
};
function paramsRequestFEG() {}
FUNCTIONS
const hidden = () => Object.keys(rows).filter((k) => rows[k].hidden).sort();
const out = {};
paramsApplyUsedWhen();
out.hiddenAtStart = hidden();
for (const k of Object.keys(paramRowState)) paramRowState[k] = "fixed";
out.fixedAtStart = paramsBuildFixedParamsDict();
paramState.End1_Style = "mag";
paramsApplyUsedWhen();
out.hiddenWithMag = hidden();
out.fixedWithMag = paramsBuildFixedParamsDict();
out.copyWithMag = paramsBuildSubmitMessage();
for (const k of Object.keys(paramRowState)) paramRowState[k] = "vary";
paramState.End1_Style = "hose";
paramsApplyUsedWhen();
paramsFixAll();
out.fixAll = Object.keys(paramRowState).filter((k) => paramRowState[k] === "fixed").sort();
for (const k of Object.keys(paramRowState)) paramRowState[k] = "vary";
paramRowState.Count = "fixed";
paramsApplyProposal({ End1_Style: "mag", Barbs: true, Length: "x", Count: 3, FlangeDia: 12,
                      Ghost: 1 });
out.proposal = {
  state: paramState, rowState: paramRowState, hidden: hidden(),
  text: els["param-proposed-End1_Style"].textContent, pick: els["param-End1_Style"].value,
  check: els["param-Barbs"].checked, cur: els["param-cur-Barbs"].textContent,
};
paramsApplyProposal({ End1_Style: "ring", Barbs: 1 });
out.badProposal = [paramState.End1_Style, paramState.Barbs];
paramState.Barbs = true;
const s = paramSpecByKey;
out.shown = [paramsShownValue(s.End1_Style, "mag"), paramsShownValue(s.Barbs, true),
             paramsShownValue(s.Barbs, false), paramsShownValue(s.Length, 42)];
out.fits = [paramsFits(s.End1_Style, "mag"), paramsFits(s.End1_Style, "ring"),
            paramsFits(s.Barbs, false), paramsFits(s.Barbs, 1)];
s.Barbs.usedWhen = { End1_Style: ["hose", "mag"] };
out.listWant = paramsIsUsed(s.Barbs);
console.log(JSON.stringify(out));
'''


def _js_function(src: str, name: str) -> str:
    start = src.index(f"\nfunction {name}(") + 1
    return src[start:src.index("\n}\n", start) + 3]


def check_types() -> str:
    import subprocess

    sys.path.insert(0, str(ROOT / "extra_utilities" / "tests"))
    from smoke_test_parameters import TYPED_SPEC
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    check('<div class="params-tabs"></div>' in html and "data-paramtab=" not in html
          and '<div class="params-panes"></div>' in html,
          "[TYPES] index.html writes the slider page's tabs itself (the page makes them "
          "from parameters.json)")
    src = (ROOT / "web" / "app.js").read_text(encoding="utf-8").replace("\r\n", "\n")
    prog = _NODE_TYPES.replace("FUNCTIONS", "\n".join(_js_function(src, n) for n in _PAGE_FUNCTIONS))
    env = dict(os.environ, GROUPS=json.dumps(parameters.slider_groups(TYPED_SPEC)))
    try:
        p = subprocess.run(["node", "--input-type=module", "-e", prog], capture_output=True,
                           text=True, encoding="utf-8", cwd=str(ROOT), env=env, timeout=120)
    except FileNotFoundError:
        return "SKIP (no node)"
    if p.returncode != 0:
        check(False, f"[TYPES] the page's code failed under Node: {p.stderr.strip()[-300:]}")
        return "failed"
    got = json.loads(p.stdout.strip().splitlines()[-1])
    check(got["hiddenAtStart"] == ["FlangeDia"] and got["hiddenWithMag"] == ["Barbs"],
          f"[TYPES] the rows hidden by \"only when\": {got['hiddenAtStart']} / {got['hiddenWithMag']}")
    check(got["fixedAtStart"] == {"Length": "50 mm", "Count": "2", "End1_Style": "hose",
                                  "Barbs": "false"},
          f"[TYPES] the FIXED block (FlangeDia hidden): {got['fixedAtStart']}")
    check(got["fixedWithMag"] == {"Length": "50 mm", "Count": "2", "End1_Style": "mag",
                                  "FlangeDia": "10.00 mm"},
          f"[TYPES] the FIXED block (Barbs hidden): {got['fixedWithMag']}")
    check("End1_Style: mag" in got["copyWithMag"] and "FlangeDia: 10.00 mm" in got["copyWithMag"]
          and "Barbs" not in got["copyWithMag"],
          f"[TYPES] Copy parameters: {got['copyWithMag']!r}")
    check(got["shown"] == ["mag (Magnetic flange)", "on", "off", "42 mm"],
          f"[TYPES] how a proposal reads: {got['shown']}")
    check(got["fits"] == [True, False, True, False], f"[TYPES] which values fit: {got['fits']}")
    check(got["listWant"] is True, "[TYPES] an \"only when\" with a list of values does not hold")
    check(got["fixAll"] == ["Barbs", "Count", "End1_Style", "Length"],
          f"[TYPES] \"Use these parameters\" fixed {got['fixAll']} (FlangeDia is hidden)")
    p = got["proposal"]
    check(p["state"] == {"Length": 50.0, "Count": 2, "End1_Style": "mag", "Barbs": True,
                         "FlangeDia": 12}
          and p["rowState"] == {"Length": "vary", "Count": "fixed", "End1_Style": "proposed",
                                "Barbs": "proposed", "FlangeDia": "proposed"}
          and p["hidden"] == ["Barbs"] and p["text"] == "PROPOSED VALUE: mag (Magnetic flange)"
          and p["pick"] == "1" and p["check"] is True and p["cur"] == "on",
          f"[TYPES] a proposal: {p}")
    check(got["badProposal"] == ["mag", True],
          f"[TYPES] a proposal with values that do not fit changed the page: {got['badProposal']}")
    _check_typed_server(TYPED_SPEC)
    return f"{len(_PAGE_FUNCTIONS)} page functions run"


def _check_typed_server(spec: dict) -> None:
    """The server with a copy of the pack holding *spec* (choice and on/off
    parameters): the page, the preview check, propose_attempt, a manual entry."""
    import types

    from agents.receptionist import propose_attempt_tool as P
    tmp = Path(tempfile.mkdtemp(prefix="web_types_"))
    shutil.copytree(ROOT / "dc_pack", tmp / "dc_pack", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp / "dc_pack" / "parameters.json").write_text(json.dumps(spec), encoding="utf-8")
    good = {"Length": 40, "Count": 2, "End1_Style": "mag", "Barbs": False, "FlangeDia": 12.5}
    real = (config.DC_PACK_DIR, P.ATTEMPTS_DIR, P.publish, web_app.manual_entry.create_manual_entry,
            web_app._busy_reason)
    sent: list = []
    seen: dict = {}

    def fake_create(**kw):
        seen.update(kw)
        return types.SimpleNamespace(session_id="MANUAL_test", attempt_id=1)
    try:
        config.DC_PACK_DIR = tmp / "dc_pack"
        check(CLIENT.get("/configurator").status_code == 200, "[TYPES] the page is not served for a typed setup")
        js = CLIENT.get("/pack/parameters.js").text
        check('"usedWhen"' in js and '"type": "choice"' in js.replace('":"', '": "'),
              "[TYPES] /pack/parameters.js does not carry the choices and \"only when\"")
        check(web_app._coerce_preview_params(good) == good,
              "[TYPES] the preview check changed a good typed record")
        try:
            web_app._coerce_preview_params(dict(good, End1_Style="ring"))
            check(False, "[TYPES] the preview check took End1_Style='ring'")
        except ValueError as exc:
            check("must be one of: hose, mag" in str(exc), f"[TYPES] the preview check said: {exc}")
        att = (tmp / "attempts").resolve()
        P.ATTEMPTS_DIR, P.publish = att, sent.append
        folder = att / "20260101_000000_001_x"
        folder.mkdir(parents=True)
        (folder / "parameters.json").write_text(json.dumps(good), encoding="utf-8")
        answer = P.propose_attempt.invoke({"parameters_path": str(folder / "parameters.json")})
        check(answer.startswith("Surfaced") and sent and sent[0]["values"] == dict(good, Length=40.0, Count=2.0)
              and isinstance(sent[0]["values"]["Count"], float),
              f"[TYPES] propose_attempt: {answer[:120]} {sent}")
        (folder / "parameters.json").write_text(json.dumps(dict(good, Barbs="no")), encoding="utf-8")
        answer = P.propose_attempt.invoke({"parameters_path": str(folder / "parameters.json")})
        check("values that do not fit: Barbs must be true or false" in answer,
              f"[TYPES] propose_attempt took Barbs='no': {answer[:160]}")
        web_app.manual_entry.create_manual_entry = fake_create
        web_app._busy_reason = lambda: None
        r = CLIENT.post("/api/manual_entry", data={"text": "a typed entry", "parameters_json": json.dumps(
            {"Length": 40, "End1_Style": "mag", "Barbs": True})})
        check(r.status_code == 200 and seen.get("parameters") == {"Length": 40.0, "End1_Style": "mag",
                                                                  "Barbs": True},
              f"[TYPES] a manual entry: {r.status_code} {r.text[:120]} -> {seen.get('parameters')}")
    finally:
        (config.DC_PACK_DIR, P.ATTEMPTS_DIR, P.publish, web_app.manual_entry.create_manual_entry,
         web_app._busy_reason) = real
        shutil.rmtree(tmp, ignore_errors=True)


def check_one_deploy() -> str:
    """The Studio mounted at /studio (studio/embedded.py), against a
    workspace of its own; run last (it sets INVITE_CODE while it runs)."""
    import anyio

    tmp = Path(tempfile.mkdtemp(prefix="web_studio_"))
    ws = tmp / "workspace"
    saved = {k: os.environ.get(k) for k in ("STUDIO_WORKSPACE", "INVITE_CODE")}
    before = {p.relative_to(ROOT).as_posix(): p.read_bytes()
              for p in (ROOT / "dc_pack").rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    try:
        os.environ["STUDIO_WORKSPACE"], os.environ["INVITE_CODE"] = str(ws), "web-texts-code"
        check(CLIENT.get("/").status_code == 200 and not ws.exists() and not web_app._STUDIO.started,
              "[ONE DEPLOY] the Studio was made before anyone opened it")
        r = CLIENT.get("/studio", follow_redirects=False)
        check(r.status_code in (307, 308) and r.headers.get("location", "").endswith("/studio/"),
              f"[ONE DEPLOY] /studio does not lead to /studio/: {r.status_code} {r.headers.get('location')}")
        r = CLIENT.get("/studio/")
        check(r.status_code == 200 and 'src="static/studio.js"' in r.text and web_app._STUDIO.started,
              f"[ONE DEPLOY] the Studio's page: {r.status_code} {r.text[:120]!r}")
        check((ws / "dc_pack" / "parameters.json").read_bytes()
              == (ROOT / "dc_pack" / "parameters.json").read_bytes(),
              "[ONE DEPLOY] the Studio's shared setup is not a copy of the pack")
        for path in ("/studio/static/studio.js", "/studio/static/bridge.js", "/studio/static/guide.html",
                     "/studio/static/base.css"):
            check(CLIENT.get(path).status_code == 200, f"[ONE DEPLOY] {path} is not served")
        s = CLIENT.post("/studio/api/session", json={"args": []}).json()
        check(s.get("online") is True and s.get("authed") is False
              and s.get("configurator") == {"url": "/configurator", "name": "propeller"},
              f"[ONE DEPLOY] the Studio's session before the code: {s}")
        r = CLIENT.post("/studio/api/get_all", json={"args": []})
        check(r.status_code == 401, f"[ONE DEPLOY] the Studio answered without the code: {r.status_code}")
        r = CLIENT.post("/studio/api/auth", json={"args": ["not the code"]})
        check(r.status_code == 401, f"[ONE DEPLOY] a wrong code opened the Studio: {r.status_code}")
        r = CLIENT.post("/studio/api/auth", json={"args": ["web-texts-code"]})
        check(r.status_code == 200 and r.json().get("ok"), f"[ONE DEPLOY] the configurator's code: {r.text[:120]}")
        r = CLIENT.get("/studio/pack/assets/general-profile.png")
        check(r.status_code == 200 and r.content[:4] == b"\x89PNG",
              f"[ONE DEPLOY] the setup's pictures under /studio/: {r.status_code}")
        r = CLIENT.get("/studio/download/setup")
        check(r.status_code == 200 and r.content[:2] == b"PK",
              f"[ONE DEPLOY] Download setup file under /studio/: {r.status_code}")
        check(CLIENT.get("/api/config").status_code == 200, "[ONE DEPLOY] the configurator stopped answering")
        # The Studio's page reaches its server by relative addresses only, and
        # shows the setup's pictures from its own copy.
        for rel in ("bridge.js", "studio.js", "index.html", "guide.html"):
            text = (ROOT / "studio" / "web" / rel).read_text(encoding="utf-8")
            found = re.findall(r"""['"]/(?:api|static|download)/""", text)
            check(not found, f"[ONE DEPLOY] studio/web/{rel} names an address from the root: {found}")
        js = (ROOT / "studio" / "web" / "studio.js").read_text(encoding="utf-8")
        # a group's picture in the parameter table and in its inspector, and the primer's
        check(js.count("src: own(") == 3, "[ONE DEPLOY] the Studio does not show the pictures from its own copy")
        # Without an access code (a local run), the Studio is open.
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from studio.embedded import LazyStudio
        os.environ.pop("INVITE_CODE", None)
        os.environ["STUDIO_WORKSPACE"] = str(tmp / "open")
        bare = LazyStudio()
        host = FastAPI()
        host.mount("/studio", bare)
        try:
            s = TestClient(host).post("/studio/api/session", json={"args": []}).json()
            check(s.get("online") is True and s.get("authed") is True,
                  f"[ONE DEPLOY] without a code the Studio is not open: {s}")
        finally:
            anyio.run(bare.close)
    finally:
        anyio.run(web_app._STUDIO.close)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)
    after = {p.relative_to(ROOT).as_posix(): p.read_bytes()
             for p in (ROOT / "dc_pack").rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    check(after == before, "[ONE DEPLOY] the pack changed while the Studio ran")
    return "the Studio at /studio/"


def main() -> int:
    _run(check_page, "[PAGE]")
    n_words = _run(check_pack_words, "[PACK WORDS]")
    _run(check_tools, "[TOOLS]")
    _run(check_retired, "[RETIRED]")
    node = _run(check_preview, "[PREVIEW]")
    types = _run(check_types, "[TYPES]")
    one = _run(check_one_deploy, "[ONE DEPLOY]")
    print(f"{len(PROPELLER_TEXTS)} page texts checked; {n_words} pack words swapped for "
          f"stand-ins; {len(pack_tools.page_tools())} pack tools + {len(STANDARD_TOOLS)} "
          f"standard tools listed; the preview module under Node: {node}; choice and "
          f"on/off parameters under Node: {types}; one deploy: {one}")
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - the page takes the configurator's words, tools, browser preview and "
          "parameter tabs from the pack, escaped, a record's retired parameter names are "
          "dropped, choice / on/off parameters and \"only when\" behave, and the start page "
          "offers the configurator and the MAS Studio, served from this server at /studio/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
