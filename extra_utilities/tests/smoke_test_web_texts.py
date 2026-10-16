"""The web page's configurator words and tools, offline: from the pack.

Since MAS-blueprint P4c the page names the configurator only through the
pack: ``web_app.py`` fills ``web/index.html``'s ``$name`` words as it serves
it (HTML-escaped, ``agents/shared/pack_text.py``), and hands the page's
script the words and tools it needs in ``/pack/page.js``.  Four groups of
checks, against the real FastAPI app (only packages that are not installed
are stubbed; no database):

1. PAGE.  With the propeller pack the page shows exactly the texts it carried
   before (the title, the chat box, the empty viewer, the database-entry
   example and checkbox), no ``$name`` is left unfilled, and
   ``/pack/page.js`` carries the words and the tools.
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
]

# Stand-in words for the PACK WORDS check: pack file -> text.
_STAND_INS = {
    "fragments/dc/app_title.md": "Turbine <Studio> & Co",
    "fragments/dc/dc_name.md": "turbine",
    "fragments/dc/manual_entry_text_example.md": "A three-vane turbine with a wide hub...",
    "fragments/tools/output_image.md": "drawing",
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
    page = r.text
    check(r.status_code == 200 and "text/html" in r.headers.get("content-type", ""),
          f"[PAGE] GET / answered {r.status_code} {r.headers.get('content-type')}")
    for text in PROPELLER_TEXTS:
        check(page.count(text) == 1, f"[PAGE] the page does not show {text!r} once")
    left = sorted(set(re.findall(r"\$[A-Za-z_][A-Za-z0-9_]*", page)))
    check(not left, f"[PAGE] unfilled words on the page: {left}")
    check("\\d{6}$</code>" in page, "[PAGE] the page's literal dollar sign ($$) is not a '$'")
    check('<script src="/pack/page.js"></script>' in page, "[PAGE] the page does not load /pack/page.js")
    words = _page_js()["words"]
    check(words == {"dc_name": "propeller"}, f"[PAGE] /pack/page.js words: {words}")


def check_pack_words() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="web_words_"))
    shutil.copytree(ROOT / "dc_pack", tmp / "dc_pack",
                    ignore=shutil.ignore_patterns("__pycache__"))
    for rel, text in _STAND_INS.items():
        (tmp / "dc_pack" / rel).write_text(text + "\n", encoding="utf-8")
    real = config.DC_PACK_DIR
    try:
        config.DC_PACK_DIR = tmp / "dc_pack"
        page = CLIENT.get("/").text
        for text in ("<title>Turbine &lt;Studio&gt; &amp; Co</title>",
                     "<h1>Turbine &lt;Studio&gt; &amp; Co</h1>",
                     'placeholder="Describe the turbine you want to design…"',
                     "No model yet — generate a turbine and it will appear here.",
                     'placeholder="e.g. A three-vane turbine with a wide hub..."',
                     "Is this a drawing of a turbine generated with our design tool?"):
            check(text in page, f"[PACK WORDS] the page does not show {text!r}")
        for text in PROPELLER_TEXTS:
            check(text not in page, f"[PACK WORDS] the page still shows {text!r}")
        words = _page_js()["words"]
        check(words == {"dc_name": "turbine"}, f"[PACK WORDS] /pack/page.js words: {words}")
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


def main() -> int:
    _run(check_page, "[PAGE]")
    n_words = _run(check_pack_words, "[PACK WORDS]")
    _run(check_tools, "[TOOLS]")
    _run(check_retired, "[RETIRED]")
    print(f"{len(PROPELLER_TEXTS)} page texts checked; {n_words} pack words swapped for "
          f"stand-ins; {len(pack_tools.page_tools())} pack tools + {len(STANDARD_TOOLS)} "
          f"standard tools listed")
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - the page takes the configurator's words and tools from the pack, "
          "escaped, and a record's retired parameter names are dropped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
