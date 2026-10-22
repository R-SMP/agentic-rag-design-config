"""TEAM_SIZE (called SYSTEM_TOPOLOGY until 2026-10-22), offline.  Three groups:

1. THE READER.  ``workflow_settings/team_size.read`` takes the new name,
   the old one alone, the new one over the old one, and 7 when neither is
   there.  The real ``settings.py`` holds ``TEAM_SIZE`` only.
2. AN OLD SETTINGS FILE.  On a copy of ``settings.py`` that still says
   ``SYSTEM_TOPOLOGY`` (written to a temporary path, never the real one):
   Workflow Settings shows it with the 3 / 5 / 7 choices and greys out what
   that team size ignores; a save under either name rewrites that line; the
   LLM routing chart reads it.  On the real file, a save under the old name
   (an old browser tab) lands on ``TEAM_SIZE``.
3. THE WORDS.  No text a user reads says "topology": the configurator's and
   the Studio's pages (outside comments), the messages the server, the
   Studio and the engine send (Python strings that are not docstrings), and
   the Workflow Settings help texts.  Code names (``lr-topology``,
   ``topology=``) are not text.

Run from the repo root:
    py -3.13 extra_utilities/tests/smoke_test_team_size.py
"""
from __future__ import annotations

import ast
import os
import re
import shutil
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")

from workflow_settings import editor          # noqa: E402
from workflow_settings import llm_routing     # noqa: E402
from workflow_settings import team_size       # noqa: E402

FAILURES: list[str] = []


def check(ok: bool, msg: str) -> None:
    if not ok:
        FAILURES.append(msg)


# --------------------------------------------------------------------------
# 1. the reader
# --------------------------------------------------------------------------

def check_reader() -> None:
    def mod(**kw):
        return types.SimpleNamespace(**kw)

    check(team_size.read(mod(TEAM_SIZE=5)) == 5, "[READ] the new name")
    check(team_size.read(mod(SYSTEM_TOPOLOGY=3)) == 3, "[READ] the old name alone")
    check(team_size.read(mod(TEAM_SIZE=5, SYSTEM_TOPOLOGY=3)) == 5, "[READ] the new name wins")
    check(team_size.read(mod()) == 7, "[READ] neither name: 7")
    names = {n.target.id for n in editor._parse_nodes()[1]}
    check("TEAM_SIZE" in names and "SYSTEM_TOPOLOGY" not in names,
          "[READ] the real settings.py holds TEAM_SIZE only")


# --------------------------------------------------------------------------
# 2. an old settings file
# --------------------------------------------------------------------------

def _size_line(path: Path) -> str:
    return next(ln for ln in path.read_text(encoding="utf-8").splitlines()
                if re.match(r"(TEAM_SIZE|SYSTEM_TOPOLOGY)\s*:", ln))


def check_old_file() -> None:
    real = editor.SETTINGS_PATH
    tmp = Path(tempfile.mkdtemp(prefix="team_size_"))
    try:
        old = tmp / "settings.py"
        text = real.read_bytes().decode("utf-8")
        check(text.count("\nTEAM_SIZE: int = ") == 1, "[OLD] the real file has one TEAM_SIZE line")
        old.write_bytes(text.replace("\nTEAM_SIZE: int = ", "\nSYSTEM_TOPOLOGY: int = ").encode("utf-8"))
        editor.SETTINGS_PATH = old

        editor.write_updates({"SYSTEM_TOPOLOGY": 5})
        schema = {item["name"]: item for item in editor.read_schema()}
        item = schema.get("SYSTEM_TOPOLOGY") or {}
        check("TEAM_SIZE" not in schema and item.get("value") == 5 and item.get("options") == [3, 5, 7],
              f"[OLD] Workflow Settings shows the old name with 3 / 5 / 7: {item.get('value')} {item.get('options')}")
        check(bool((schema.get("DC_INSPECTOR_ENABLED") or {}).get("disabled")),
              "[OLD] a 5-agent team greys out DC_INSPECTOR_ENABLED")
        check(llm_routing.current_topology() == 5, "[OLD] the LLM routing chart reads the old name")
        try:
            editor.write_updates({"DC_INSPECTOR_ENABLED": False})
            check(False, "[OLD] a setting the 5-agent team ignores was saved")
        except editor.SettingsError:
            pass

        editor.write_updates({"TEAM_SIZE": 3})
        check(_size_line(old).startswith("SYSTEM_TOPOLOGY: int = 3"),
              f"[OLD] a save under the new name rewrites the old line: {_size_line(old)!r}")
        check(llm_routing.current_topology() == 3, "[OLD] the chart follows")

        # the real file's shape, under an old browser tab's name
        new = tmp / "settings_new.py"
        new.write_bytes(text.encode("utf-8"))
        editor.SETTINGS_PATH = new
        editor.write_internal({"SYSTEM_TOPOLOGY": 5})
        check(_size_line(new).startswith("TEAM_SIZE: int = 5"),
              f"[NEW] a save under the old name lands on TEAM_SIZE: {_size_line(new)!r}")
        check(new.read_bytes().count(b"SYSTEM_TOPOLOGY: int") == 0, "[NEW] no old-name line written")
        try:
            editor.write_updates({"TEAM_SIZE": 4})
            check(False, "[NEW] a team size of 4 was saved")
        except editor.SettingsError:
            pass
    finally:
        editor.SETTINGS_PATH = real
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 3. the words
# --------------------------------------------------------------------------

# The word in prose; the setting's old NAME, written where it is explained, is not.
WORD = re.compile(r"(?<!SYSTEM_)topolog", re.I)
# Code names that are not text a user reads.
CODE = re.compile(r"lr-topology[\w-]*|data-topo\w*|data-k=\"topology\"|\$\{[^}]*\}")
PROSE = re.compile(r"(?i)\btopolog(y|ies)\b")
# In a script, the word as prose: after a word that is not a keyword ("per
# topology", "the 5-agent topology"), or capitalised at the start of a text
# ('Topology').  Code names -- ``topology: 7``, ``(topology)``,
# ``return topology`` -- are not prose.
JS_PROSE = re.compile(
    r"(?:\b(?!(?:return|const|let|var|typeof|function|new|in|of|await|case|if|else)\b)[a-z]+\s+|-agent\s+)"
    r"topolog(?:y|ies)\b|['\"`>(]\s*Topolog(?:y|ies)\b")


def _js_hits(path: Path, src: str) -> list[str]:
    """The script's lines that say the word as prose; comment lines, and a
    `` // `` comment after code, go first."""
    hits = []
    for k, ln in enumerate(src.splitlines(), 1):
        if ln.lstrip().startswith(("//", "*", "/*")):
            continue
        code = CODE.sub("", re.sub(r"\s//\s.*$", "", ln))
        if JS_PROSE.search(code):
            hits.append(f"{path.relative_to(ROOT)}:{k}: {ln.strip()[:120]}")
    return hits


def _page_hits(path: Path, text: str) -> list[str]:
    """The page's lines outside comments that say the word."""
    return [f"{path.relative_to(ROOT)}:{k}: {ln.strip()[:120]}"
            for k, ln in enumerate(text.splitlines(), 1) if PROSE.search(CODE.sub("", ln))]


def _py_hits(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            b = node.body
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant):
                docs.add(id(b[0].value))
    hits = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs
                and WORD.search(node.value) and not re.fullmatch(r"[\w./-]*", node.value)
                and not node.value.startswith("[QUEUE]")):      # server log lines
            hits.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.value.strip()[:120]!r}")
    return hits


def check_words() -> int:
    pages = [ROOT / "web/index.html", ROOT / "web/app.js", *sorted((ROOT / "studio/web").glob("*.html")),
             *sorted((ROOT / "studio/web").glob("*.js"))]
    hits = []
    for p in pages:
        src = p.read_text(encoding="utf-8")
        src = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
        hits += _js_hits(p, src) if p.suffix == ".js" else _page_hits(p, src)
    py = [p for d in ("studio", "engine", "workflow_settings") for p in sorted((ROOT / d).rglob("*.py"))]
    py += [ROOT / "web_app.py", ROOT / "agents/shared/sessions_queue.py"]
    for p in py:
        hits += _py_hits(p)
    for item in editor.read_schema():
        for field in ("group", "help", "disabled_note"):
            if WORD.search(str(item.get(field) or "")):
                hits.append(f"Workflow Settings {item['name']} {field}")
    for h in hits:
        check(False, f"[WORDS] says topology: {h}")
    return len(pages) + len(py)


def main() -> int:
    check_reader()
    check_old_file()
    n = check_words()
    print(f"the reader; an old settings file; {n} files read for the word")
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - TEAM_SIZE is read under either name, an old settings file "
          "still works, and no text a user reads says topology.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
