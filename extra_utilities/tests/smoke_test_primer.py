"""The primer is the setup's: its picture, its text and who gets it.

(MAS-blueprint, after P8; TODO F127.)  ``engine/primer.py`` reads the
``primer`` section of ``pack.yaml``, ``agents/shared/dc_primer.py`` sends it,
every agent's call splices it, and the Studio's Primer page edits it
(``studio/primer_edit.py``).

1. ENGINE -- the propeller's section reads as the default, and so does a
   setup without the section (not declared); a bad section is refused with
   one sentence per problem; the picture is None when it is not named,
   missing or not a PNG; an unregistered topology reads the 7-agent list.
2. MESSAGES -- against a message built here from the files by name: for the
   propeller, every agent of every topology x four providers x caching on /
   off x the switch on / off gets the text block, the picture block and --
   Anthropic with caching on -- the trailing marker, the six design agents
   only.  A primer without a picture (the marker on its text), a picture
   without a text, neither (nothing), a missing or non-PNG picture (the text
   alone), an agent ticked or not; ``primer_tokens_for`` agrees, and
   ``primed_history`` puts it after the leading system messages.
3. CALLS -- one scripted turn per topology, a fake model (the harness of
   ``dry_run_topology.py``, every agent on the way): with every agent ticked
   each call carries the primer; with the propeller's own setup, only the
   six design agents' calls do.
4. VALIDATE -- its primer item passes for the propeller, fails for a bad
   section, a missing picture or a ticked agent with nothing to send, and
   warns about a picture a model provider shrinks.
5. EDITOR -- ``studio/primer_edit.py`` on copies: a hand-laid section (a
   comment inside) and a setup without one come back byte for byte after a
   tick and an untick and after each Undo; the same PNG sent again changes
   nothing; a picture added where the setup had none goes with its Undo.
   IMPORT -- ``pack.yaml`` after an import that starts a new configurator
   gives the primer to no agent and keeps its picture (the section is added
   to a setup without one); an import of one more tool leaves it.
6. STUDIO -- on a copy: the page's data (the rows, the picture, the text
   field in its section), ticking and unticking (in the roster's order), a
   JPEG and a WebP stored as PNGs, a large one warned about, the picture
   removed, each Undo back to the files byte for byte; a stale page, the
   Database Handler and an agent outside the topology refused; the Prompt
   viewer's primer per agent, with its tokens.

    py -3.13 extra_utilities/tests/smoke_test_primer.py
"""

from __future__ import annotations

import base64
import io
import json
import os
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
os.environ["PYTHONIOENCODING"] = "utf-8"
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import yaml                                      # noqa: E402
from PIL import Image                            # noqa: E402

import config                                    # noqa: E402
from engine import pack                          # noqa: E402
from engine import primer                        # noqa: E402
from studio import primer_edit                   # noqa: E402

FAILURES: list[str] = []
SIX = {7: ["user_input_inspector", "dc_input_creator", "dc_input_inspector", "dc_output_inspector"],
       5: ["user_input_inspector", "dc_input_creator", "dc_output_inspector"],
       3: ["design_engineer", "requirements_analyst"]}
FRAGS = ROOT / "setups" / "propeller" / "fragments" / "dc"


def check(ok: bool, what: str) -> None:
    if not ok:
        FAILURES.append(what)


def _run(group, tag: str):
    try:
        return group()
    except Exception as exc:                                        # noqa: BLE001
        import traceback
        check(False, f"{tag} {type(exc).__name__}: {str(exc)[:300]}\n{traceback.format_exc()[-800:]}")
        return None


def copy_setup() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="primer_smoke_"))
    shutil.copytree(ROOT / "setups" / "propeller", tmp / "dc_pack", ignore=shutil.ignore_patterns("__pycache__"))
    return tmp / "dc_pack"


def set_section(pack_dir: Path, sec: dict | None) -> None:
    """*pack_dir*'s pack.yaml with the primer section *sec* (None: none)."""
    p = pack_dir / "pack.yaml"
    raw = p.read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    out = primer_edit.write_section(text, sec, None) if sec is not None else \
        primer_edit.write_section(text, None, None)
    p.write_bytes(out.replace("\n", "\r\n" if b"\r\n" in raw else "\n").encode("utf-8"))


def set_raw_section(pack_dir: Path, raw_yaml: str) -> None:
    """pack.yaml with its primer section replaced by *raw_yaml* as written."""
    set_section(pack_dir, None)
    p = pack_dir / "pack.yaml"
    p.write_text(p.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + raw_yaml.strip("\n") + "\n",
                 encoding="utf-8")


def picture(fmt: str, size=(64, 32)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (30, 120, 200)).save(buf, fmt)
    return buf.getvalue()


def use(pack_dir: Path) -> None:
    """The engine reads *pack_dir* from now on (its kept file data cleared)."""
    config.DC_PACK_DIR = pack_dir
    for cache in (pack._folders_cache, pack._claims_cache, pack._names_cache):
        cache.clear()


def snapshot(d: Path) -> dict:
    return {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(d.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


# ---------------------------------------------------------------------------
# 1. the engine's reading
# ---------------------------------------------------------------------------

def check_engine() -> None:
    real = config.DC_PACK_DIR
    try:
        got = primer.read()
        check(got == {**primer.DEFAULT, "declared": True}, f"[ENGINE] the propeller's primer: {got}")
        check(primer.image_path() == pack.asset_path("dc_params_primer.png"), "[ENGINE] its picture")
        check(primer.agents_for(9) == SIX[7], "[ENGINE] an unregistered topology does not read the 7 list")
        d = copy_setup()
        use(d)
        set_section(d, None)
        check("primer" not in (yaml.safe_load((d / "pack.yaml").read_text(encoding="utf-8")) or {}),
              "[ENGINE] the section was not taken out of the copy")
        got = primer.read()
        check(got == {**primer.DEFAULT, "declared": False}, f"[ENGINE] a setup without the section: {got}")
        set_section(d, {"image": None, "agents": {7: ["planner"], 5: [], 3: []}})
        check(primer.read() == {"image": None, "agents": {7: ["planner"], 5: [], 3: []}, "declared": True}
              and primer.image_path() is None and primer.gets("planner", 7) and not primer.gets("planner", 5),
              f"[ENGINE] no picture, the planner in 7: {primer.read()}")
        set_section(d, {"image": "nowhere.png", "agents": {7: [], 5: [], 3: []}})
        check(primer.image_path() is None, "[ENGINE] a missing picture is not None")
        (d / "assets" / "fake.png").write_bytes(picture("JPEG"))
        set_section(d, {"image": "fake.png", "agents": {7: [], 5: [], 3: []}})
        check(primer.image_path() is None, "[ENGINE] a JPEG named .png is not None")
        bad = {"image": "x.jpg", "colour": 1,
               "agents": {7: ["database_handler", "design_engineer", "planner", "planner"], 4: [],
                          5: "planner"}}
        problems = primer.problems_of(bad)
        for word in ("'colour'", "x.jpg", "database_handler cannot get the primer", "'design_engineer' is not an agent",
                     "planner is listed twice", "4 is not a team size (3, 5, 7)", "agents 5 must be a list"):
            check(any(word in p for p in problems), f"[ENGINE] no problem names {word}: {problems}")
        check(len(problems) == 7, f"[ENGINE] {len(problems)} problems, not 7: {problems}")
        check(primer.problems_of("x") and primer.problems_of({"agents": [1]}),
              "[ENGINE] a primer that is no mapping, or agents that are no mapping")
        set_raw_section(d, "primer:\n  image: x.jpg\n  agents:\n    7: [database_handler]\n")
        try:
            primer.read()
            check(False, "[ENGINE] a bad section was read")
        except primer.PrimerError as exc:
            check("x.jpg" in str(exc) and "database_handler" in str(exc), f"[ENGINE] refused as: {exc}")
        shutil.rmtree(d.parent, ignore_errors=True)
    finally:
        use(real)


# ---------------------------------------------------------------------------
# 2. the messages
# ---------------------------------------------------------------------------

def text_file(agent: str, topology: int, root: Path) -> Path:
    """The primer text this agent reads, by the files' own names."""
    own = root / "fragments" / "dc" / f"dc_params_primer_text@{agent}.t{topology}.md"
    return own if own.is_file() else root / "fragments" / "dc" / "dc_params_primer_text.md"


def expected(provider: str, text: str, png: bytes | None, cache_on: bool) -> list:
    from agents.shared.llm_provider import make_image_block, system_cache_control
    content = [{"type": "text", "text": text}] if text else []
    if png is not None:
        content.append(make_image_block(base64.b64encode(png).decode(), provider, media_type="image/png"))
    if not content:
        return []
    if provider == "anthropic" and cache_on:
        cc = system_cache_control("anthropic")
        if png is not None:
            content.append({"type": "text", "text": "END OF REFERENCE DIAGRAM.", "cache_control": cc})
        else:
            content[-1] = {**content[-1], "cache_control": cc}
    return [content]


def check_messages() -> None:
    from langchain_core.messages import HumanMessage, SystemMessage

    from agents.database_handler.token_utils import count_tokens
    from agents.shared import agent_roles
    from agents.shared import dc_primer as DP
    from workflow_settings import settings as S
    real = config.DC_PACK_DIR
    saved = (S.DC_PARAMS_PRIMER_ENABLED, S.PROMPT_CACHE_SCOPE, S.TEAM_SIZE)
    png = (ROOT / "setups" / "propeller" / "assets" / "dc_params_primer.png").read_bytes()
    n = 0
    try:
        for flag in (True, False):
            S.DC_PARAMS_PRIMER_ENABLED = flag
            for cache_on in (False, True):
                S.PROMPT_CACHE_SCOPE = "system+history" if cache_on else "off"
                for topo in (7, 5, 3):
                    S.TEAM_SIZE = topo
                    for agent in agent_roles.ROSTER[topo] + ("database_handler",):
                        gets = flag and agent in SIX[topo]
                        text = text_file(agent, topo, ROOT / "setups" / "propeller").read_text(encoding="utf-8").rstrip()
                        for prov in ("openai", "anthropic", "google", "openrouter"):
                            got = [m.content for m in DP.dc_primer_messages(prov, agent)]
                            want = expected(prov, text, png, cache_on) if gets else []
                            n += 1
                            check(got == want, f"[MESSAGES] {agent} topology {topo} {prov} caching "
                                               f"{cache_on} switch {flag}: not the primer it should get")
                        tokens = DP.primer_tokens_for(agent)
                        want_tokens = (primer.image_tokens(930, 309) + count_tokens(text)) if gets else 0
                        check(tokens == want_tokens, f"[MESSAGES] {agent} {topo}: {tokens} tokens, not {want_tokens}")
        check(n == 2 * 2 * 4 * (8 + 6 + 4 + 3), f"[MESSAGES] {n} cases")
        S.DC_PARAMS_PRIMER_ENABLED, S.PROMPT_CACHE_SCOPE, S.TEAM_SIZE = True, "system+history", 7
        # primed_history: after the leading system messages
        hist = [SystemMessage(content="summary"), HumanMessage(content="hi")]
        out = DP.primed_history("openai", "dc_input_creator", hist)
        check(len(out) == 3 and out[0] is hist[0] and isinstance(out[1], HumanMessage)
              and out[2] is hist[1], "[MESSAGES] primed_history did not splice after the system message")
        check(DP.primed_history("openai", "planner", hist) == hist, "[MESSAGES] the planner got one")
        # other setups
        d = copy_setup()
        use(d)
        own_text = text_file("planner", 7, d).read_text(encoding="utf-8").rstrip()
        set_section(d, {"image": None, "agents": {7: ["planner"], 5: [], 3: []}})
        for cache_on in (False, True):
            S.PROMPT_CACHE_SCOPE = "system+history" if cache_on else "off"
            got = [m.content for m in DP.dc_primer_messages("anthropic", "planner")]
            check(got == expected("anthropic", own_text, None, cache_on),
                  f"[MESSAGES] a primer without a picture, caching {cache_on}: {str(got)[:200]}")
        check(DP.dc_primer_messages("openai", "dc_input_creator") == [], "[MESSAGES] an unticked agent got one")
        check(DP.primer_tokens_for("planner") == count_tokens(own_text), "[MESSAGES] tokens of the text alone")
        set_section(d, {"image": "dc_params_primer.png", "agents": {7: ["planner"], 5: [], 3: []}})
        (d / "fragments" / "dc" / "dc_params_primer_text.md").write_text("", encoding="utf-8")
        got = [m.content for m in DP.dc_primer_messages("openai", "planner")]
        check(got == expected("openai", "", png, False), "[MESSAGES] a picture without a text")
        check(DP.primer_tokens_for("planner") == primer.image_tokens(930, 309), "[MESSAGES] tokens of the picture alone")
        set_section(d, {"image": None, "agents": {7: ["planner"], 5: [], 3: []}})
        check(DP.dc_primer_messages("openai", "planner") == [] and DP.primer_tokens_for("planner") == 0,
              "[MESSAGES] neither a picture nor a text sends something")
        (d / "fragments" / "dc" / "dc_params_primer_text.md").write_text("Look.\n", encoding="utf-8")
        set_section(d, {"image": "gone.png", "agents": {7: ["planner"], 5: [], 3: []}})
        check([m.content for m in DP.dc_primer_messages("openai", "planner")] == expected("openai", "Look.", None, False),
              "[MESSAGES] a missing picture: not the text alone")
        (d / "assets" / "jpeg.png").write_bytes(picture("JPEG"))
        set_section(d, {"image": "jpeg.png", "agents": {7: ["planner"], 5: [], 3: []}})
        check([m.content for m in DP.dc_primer_messages("openai", "planner")] == expected("openai", "Look.", None, False),
              "[MESSAGES] a picture that is not a PNG: not the text alone")
        new_png = picture("PNG", (40, 20))
        (d / "assets" / "jpeg.png").write_bytes(new_png)
        check([m.content for m in DP.dc_primer_messages("openai", "planner")] == expected("openai", "Look.", new_png, False),
              "[MESSAGES] a picture replaced on disk is not sent at once")
        shutil.rmtree(d.parent, ignore_errors=True)
    finally:
        S.DC_PARAMS_PRIMER_ENABLED, S.PROMPT_CACHE_SCOPE, S.TEAM_SIZE = saved
        use(real)



# ---------------------------------------------------------------------------
# 3. every agent's call (one scripted turn per topology)
# ---------------------------------------------------------------------------

ROUTES = {
    7: [("Receptionist", "call_orchestrator"), ("Orchestrator", "call_user_input_inspector"),
        ("UII", "call_planner"), ("Planner", "call_orchestrator"),
        ("Orchestrator", "call_dc_input_creator"), ("DCIC", "call_dc_input_inspector"),
        ("DCII", "call_tool_caller"), ("Tool Caller", "call_dc_output_inspector"),
        ("DCOI", "call_orchestrator"), ("Orchestrator", "call_receptionist"), ("Receptionist", None)],
    5: [("Receptionist", "call_planner"), ("Planner", "call_user_input_inspector"),
        ("UII", "call_planner"), ("Planner", "call_dc_input_creator"), ("DCIC", "call_tool_caller"),
        ("Tool Caller", "call_dc_output_inspector"), ("DCOI", "call_planner"),
        ("Planner", "call_receptionist"), ("Receptionist", None)],
    3: [("Receptionist", "call_planner"), ("Planner", "call_design_engineer"),
        ("DEng", "call_requirements_analyst"), ("RA", "call_planner"),
        ("Planner", "call_receptionist"), ("Receptionist", None)],
}
LABEL_AGENT = {"Receptionist": "receptionist", "Orchestrator": "orchestrator", "UII": "user_input_inspector",
               "Planner": "planner", "DCIC": "dc_input_creator", "DCII": "dc_input_inspector",
               "Tool Caller": "tool_caller", "DCOI": "dc_output_inspector", "DEng": "design_engineer",
               "RA": "requirements_analyst"}

_CHILD = r'''
import json, sys, tempfile, shutil
from pathlib import Path
sys.modules["simplejson"] = None
sys.modules["chardet"] = None
sys.path.insert(0, @BOOTSTRAP@)
import bootstrap
bootstrap.install()
TOPO = int(sys.argv[1])
SCRIPT = json.loads(sys.argv[2])
from workflow_settings import settings as S
S.TEAM_SIZE = TOPO
S.DC_PARAMS_PRIMER_ENABLED = True
S.RAG_ENABLED = False
from langchain_core.messages import AIMessage, HumanMessage
seen, problems, step = [], [], {"i": 0}

def has_primer(messages):
    for m in messages:
        if isinstance(m, HumanMessage) and isinstance(m.content, list):
            if any(isinstance(b, dict) and b.get("type") in ("image_url", "image") for b in m.content):
                return True
    return False

def fake_invoke(llm, messages, agent_name, **kw):
    i = step["i"]
    if i >= len(SCRIPT):
        problems.append("script exhausted but %r was invoked again" % agent_name)
        return AIMessage(content="(script exhausted)")
    want_label, want_tool = SCRIPT[i]
    if agent_name != want_label:
        problems.append("step %d: %r was invoked, expected %r" % (i, agent_name, want_label))
    step["i"] = i + 1
    seen.append([agent_name, has_primer(messages)])
    if want_tool is None:
        return AIMessage(content="Dry run: composed reply for the user.")
    return AIMessage(content="", tool_calls=[{"name": want_tool, "args": {"message": "hand-off %d" % i},
                                              "id": "dry_%d" % i}])

from agents.hub import build_hub
from agents.shared.session import Session
from agents import dispatch as dispatch_mod
work = Path(tempfile.mkdtemp(prefix="primer_turn_%d_" % TOPO))
try:
    from datetime import datetime, timezone
    sess = Session(session_id="primer_turn_%d" % TOPO, session_ts=datetime.now(timezone.utc))
    hub = build_hub(sess)
    for name, mod in list(sys.modules.items()):
        if name.startswith("agents") and hasattr(mod, "invoke_with_retry"):
            mod.invoke_with_retry = fake_invoke
    (work / "inputs").mkdir(parents=True)
    (work / "attempts").mkdir(parents=True)
    dispatch_mod.dispatch_turn(sess, "design me a propeller", inputs_dir=work / "inputs",
                               attempts_dir=work / "attempts", hub=hub)
    payload = {"seen": seen, "problems": problems}
except Exception as exc:
    import traceback
    payload = {"fatal": "%s: %s" % (type(exc).__name__, exc), "trace": traceback.format_exc()[-1500:],
               "seen": seen, "problems": problems}
finally:
    shutil.rmtree(work, ignore_errors=True)
sys.stdout.write("@@JSON@@" + json.dumps(payload))
'''


def turn(topology: int, pack_dir: Path) -> dict:
    code = _CHILD.replace("@BOOTSTRAP@", repr(str(ROOT / "extra_utilities" / "prompt_pdf")))
    env = dict(os.environ, DC_PACK_DIR=str(pack_dir), PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-c", code, str(topology), json.dumps(ROUTES[topology])],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=str(ROOT), env=env, timeout=600)
    if "@@JSON@@" not in proc.stdout:
        return {"fatal": "no result", "trace": proc.stdout[-800:] + proc.stderr[-1500:]}
    return json.loads(proc.stdout.split("@@JSON@@", 1)[1])


def check_calls() -> str:
    from agents.shared import agent_roles
    every = copy_setup()
    set_section(every, {"image": "dc_params_primer.png",
                        "agents": {t: list(agent_roles.ROSTER[t]) for t in (7, 5, 3)}})
    counted = 0
    try:
        for name, d in (("every agent ticked", every), ("the propeller's setup", ROOT / "setups" / "propeller")):
            for topo in (7, 5, 3):
                res = turn(topo, d)
                if "fatal" in res:
                    check(False, f"[CALLS] {name}, topology {topo}: {res['fatal']}\n{res.get('trace', '')[-600:]}")
                    continue
                check(not res["problems"], f"[CALLS] {name}, topology {topo}: {res['problems']}")
                check([s[0] for s in res["seen"]] == [r[0] for r in ROUTES[topo]],
                      f"[CALLS] {name}, topology {topo}: the turn went {[s[0] for s in res['seen']]}")
                for label, primed in res["seen"]:
                    agent = LABEL_AGENT[label]
                    want = d is every or agent in SIX[topo]
                    counted += 1
                    check(primed == want, f"[CALLS] {name}, topology {topo}: {label}'s call "
                                          f"{'carries' if primed else 'lacks'} the primer")
    finally:
        shutil.rmtree(every.parent, ignore_errors=True)
    return f"{counted} calls"


# ---------------------------------------------------------------------------
# 4. Validate
# ---------------------------------------------------------------------------

def check_validate() -> str:
    from studio import validate as V

    def primer_item(d: Path) -> dict:
        items = V._child(["load"], d)
        return next((i for i in items if i["title"] == "The primer (pack.yaml)"), {})

    it = primer_item(ROOT / "setups" / "propeller")
    check(it.get("status") == V.PASS and it.get("link") == {"section": "primer"},
          f"[VALIDATE] the propeller's primer: {it}")
    d = copy_setup()
    try:
        set_raw_section(d, "primer:\n  image: dc_params_primer.png\n  agents:\n    7: [database_handler]\n")
        it = primer_item(d)
        check(it.get("status") == V.FAIL and any("database_handler" in ln for ln in it["lines"]),
              f"[VALIDATE] a bad section: {it}")
        set_section(d, {"image": "gone.png", "agents": {7: [], 5: [], 3: []}})
        it = primer_item(d)
        check(it.get("status") == V.FAIL and any("gone.png" in ln and "missing" in ln for ln in it["lines"]),
              f"[VALIDATE] a missing picture: {it}")
        set_section(d, {"image": None, "agents": {7: ["planner"], 5: [], 3: []}})
        (d / "fragments" / "dc" / "dc_params_primer_text.md").write_text("\n", encoding="utf-8")
        it = primer_item(d)
        check(it.get("status") == V.FAIL and any("planner (7-agent)" in ln and "no picture and no text" in ln
                                                for ln in it["lines"]),
              f"[VALIDATE] a ticked agent with nothing to send: {it}")
        (d / "assets" / "big.png").write_bytes(picture("PNG", (2000, 900)))
        set_section(d, {"image": "big.png", "agents": {7: ["planner"], 5: [], 3: []}})
        it = primer_item(d)
        check(it.get("status") == V.WARN and any("2000 x 900" in ln for ln in it["lines"]),
              f"[VALIDATE] a picture a provider shrinks: {it}")
    finally:
        shutil.rmtree(d.parent, ignore_errors=True)
    return "5 setups"


# ---------------------------------------------------------------------------
# 5. the editor, in this process; the import
# ---------------------------------------------------------------------------

ROSTER = {"7": ["receptionist", "orchestrator", "user_input_inspector", "planner", "dc_input_creator",
                "dc_input_inspector", "tool_caller", "dc_output_inspector"],
          "5": ["receptionist", "planner", "user_input_inspector", "dc_input_creator", "tool_caller",
                "dc_output_inspector"],
          "3": ["receptionist", "planner", "design_engineer", "requirements_analyst"]}


def check_editor() -> None:
    NL = chr(10)
    data = {"roles": {"roster": ROSTER}}
    hand = ("primer:            # set by hand" + NL + "  image: dc_params_primer.png" + NL + "  agents:" + NL
            + "    7: [dc_input_creator]   # the creator only" + NL + "    5: []" + NL + "    3: []" + NL)
    for name, raw in (("a hand-laid section", hand), ("no section", None)):
        d = copy_setup()
        if raw is None:
            set_section(d, None)
        else:
            set_raw_section(d, raw)
        opened = d.parent / "opened" / "dc_pack"
        shutil.copytree(d, opened)
        ed = primer_edit.PrimerEditor(d, opened)
        before = snapshot(d)
        sha = ed.state(data)["pack_yaml_sha"]
        r = ed.set_agent(data, "planner", 5, True, sha)
        ed.set_agent(data, "planner", 5, False, r["pack_yaml_sha"])
        check(snapshot(d) == before, f"[EDITOR] {name}: a tick and an untick are not byte for byte")
        r = ed.set_agent(data, "receptionist", 3, True, ed.state(data)["pack_yaml_sha"])
        png = (d / "assets" / "dc_params_primer.png").read_bytes()
        r = ed.set_picture(data, base64.b64encode(png).decode(), "same.png", r["pack_yaml_sha"])
        check(r["warnings"] == [] and (d / "assets" / "dc_params_primer.png").read_bytes() == png
              and ed.changed() == [], f"[EDITOR] {name}: the same PNG sent again changed something")
        ed.remove_picture(data, r["pack_yaml_sha"])
        ed.undo(data, "picture")
        ed.undo(data, "agents")
        check(snapshot(d) == before, f"[EDITOR] {name}: Undo is not byte for byte "
              f"{[k for k in set(before) | set(snapshot(d)) if before.get(k) != snapshot(d).get(k)]}")
        shutil.rmtree(d.parent, ignore_errors=True)
    # a picture where the setup had none
    d = copy_setup()
    set_section(d, {"image": None, "agents": {7: [], 5: [], 3: []}})
    (d / "assets" / "dc_params_primer.png").unlink()
    opened = d.parent / "opened" / "dc_pack"
    shutil.copytree(d, opened)
    ed = primer_edit.PrimerEditor(d, opened)
    before = snapshot(d)
    r = ed.set_picture(data, base64.b64encode(picture("PNG")).decode(), "new.png", ed.state(data)["pack_yaml_sha"])
    check((d / "assets" / "dc_params_primer.png").is_file() and
          yaml.safe_load((d / "pack.yaml").read_text(encoding="utf-8"))["primer"]["image"] == "dc_params_primer.png",
          "[EDITOR] a picture where the setup had none is not named")
    ed.undo(data, "picture")
    check(snapshot(d) == before, "[EDITOR] the Undo of a new picture left something")
    shutil.rmtree(d.parent, ignore_errors=True)


def check_import() -> None:
    from studio import scad_import
    text = (ROOT / "setups" / "propeller" / "pack.yaml").read_text(encoding="utf-8").replace("\r\n", "\n")
    new = yaml.safe_load(scad_import.pack_yaml(text, "new", {"a": 1}, "geo"))
    check(new["primer"] == {"image": "dc_params_primer.png", "agents": {7: [], 5: [], 3: []}},
          f"[IMPORT] a new configurator's primer: {new['primer']}")
    check(new["downloads"] == {"geometry_tool": "geo"} and new["render_samples"] == {"default": {"a": 1}},
          "[IMPORT] the rest of pack.yaml after a new configurator")
    add = yaml.safe_load(scad_import.pack_yaml(text, "add", {"a": 1}, None))
    check(add["primer"] == yaml.safe_load(text)["primer"], "[IMPORT] one more tool changed the primer")
    bare = primer_edit.write_section(text, None, None)
    out = scad_import.pack_yaml(bare, "new", {"a": 1}, "geo")
    check(yaml.safe_load(out)["primer"]["agents"] == {7: [], 5: [], 3: []}
          and primer_edit.COMMENT.split("\n")[0] in out,
          "[IMPORT] a setup without the section: no section with its comment after a new configurator")


# ---------------------------------------------------------------------------
# 6. the Studio
# ---------------------------------------------------------------------------

class Studio:
    """``python -m studio --pack <pack>`` on a free port."""

    def __init__(self, pack_dir: Path):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "studio", "--pack", str(pack_dir), "--port", str(self.port),
             "--workers", "2"], cwd=str(ROOT), env=dict(os.environ),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                self.get("/")
                return
            except OSError:
                if self.proc.poll() is not None:
                    break
                time.sleep(0.3)
        raise RuntimeError("the Studio did not start")

    def get(self, path: str):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=30) as r:
            return r.status, dict(r.headers), r.read()

    def call(self, name: str, *args) -> dict:
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/{name}", method="POST",
                                     data=json.dumps({"args": list(args)}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            return json.loads(e.read())

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def check_studio() -> str:
    d = copy_setup()
    before = snapshot(d)
    st = Studio(d)
    try:
        r = st.call("get_all")
        D = r["data"]
        P, E = D["primer"], D["primer_edit"]
        rows = {x["agent"]: x for x in P["rows"]}
        check(list(rows) == ["receptionist", "orchestrator", "user_input_inspector", "planner", "dc_input_creator",
                             "dc_input_inspector", "tool_caller", "dc_output_inspector", "design_engineer",
                             "requirements_analyst"], f"[STUDIO] the rows: {list(rows)}")
        check(rows["orchestrator"]["cells"] == {"7": False} and rows["user_input_inspector"]["cells"] == {"7": True, "5": True}
              and rows["user_input_inspector"]["copies"] == [7, 5] and rows["requirements_analyst"]["copies"] == [3],
              f"[STUDIO] cells and copies: {rows['user_input_inspector']} {rows['requirements_analyst']}")
        check(P["picture"] == {"file": "dc_params_primer.png", "width": 930, "height": 309, "bytes": 141438,
                               "tokens": 384} and P["declared"] and not P["problems"],
              f"[STUDIO] the picture: {P['picture']}")
        check(E["opened"]["agents"] == {str(t): SIX[t] for t in (7, 5, 3)} and E["picture"]["sha"] == E["opened"]["picture_sha"],
              f"[STUDIO] the editor's opened state: {E['opened']}")
        s = next(x for x in D["slots"] if x["slot"] == "dc_params_primer_text")
        check(s["section"] == "primer" and s["runtime"] and [v["agent"] for v in s["variants"]] ==
              ["requirements_analyst", "user_input_inspector"], f"[STUDIO] the text field: {s['section']} {s['variants']}")
        sha = E["pack_yaml_sha"]
        r = st.call("set_primer_agent", "planner", "7", True, sha)
        check(r.get("ok"), f"[STUDIO] tick the planner: {r}")
        r = st.call("set_primer_agent", "receptionist", 7, True, r.get("pack_yaml_sha"))
        y = yaml.safe_load((d / "pack.yaml").read_text(encoding="utf-8"))["primer"]
        check(y["agents"][7] == ["receptionist", "user_input_inspector", "planner", "dc_input_creator",
                                 "dc_input_inspector", "dc_output_inspector"],
              f"[STUDIO] the 7 list after two ticks: {y['agents'][7]}")
        bad = st.call("set_primer_agent", "planner", 7, False, sha)
        check(bad.get("ok") is False and bad.get("conflict"), f"[STUDIO] a stale page: {bad}")
        sha = r.get("pack_yaml_sha")
        for args, word in ((("database_handler", 7, True), "only saves the session"),
                           (("design_engineer", 7, True), "not an agent of the 7-agent team"),
                           (("planner", 4, True), "4-agent")):
            bad = st.call("set_primer_agent", *args, sha)
            check(bad.get("ok") is False and word in bad.get("error", ""), f"[STUDIO] {args}: {bad}")
        view = st.call("view", {"topology": 7})["data"]
        pv = view["primer"]
        check(set(pv) == set(SIX[7]) | {"receptionist", "planner"} and pv["receptionist"]["text_tokens"] > 0
              and pv["receptionist"]["picture"]["tokens"] == 384 and pv["user_input_inspector"]["own_copy"]
              and not pv["receptionist"]["own_copy"] and pv["receptionist"]["enabled"],
              f"[STUDIO] the Prompt viewer's primer: { {a: (p['own_copy'], p['text_tokens']) for a, p in pv.items()} }")
        jpeg = picture("JPEG", (120, 60))
        r = st.call("primer_picture", base64.b64encode(jpeg).decode(), "x.jpg", sha)
        stored = (d / "assets" / "dc_params_primer.png").read_bytes()
        check(r.get("ok") and r["picture"]["width"] == 120 and stored[:8] == primer.PNG_SIGNATURE
              and "Stored as a PNG (JPEG sent)." in r.get("warnings", []),
              f"[STUDIO] a JPEG: {r.get('error') or r.get('warnings')}")
        r = st.call("primer_picture", base64.b64encode(picture("WEBP", (1800, 700))).decode(), "x.webp",
                    r.get("pack_yaml_sha"))
        check(r.get("ok") and r["picture"]["large"] and any("1800 x 700" in w for w in r.get("warnings", [])),
              f"[STUDIO] a large WebP: {r.get('warnings')}")
        D = st.call("get_all")["data"]
        check("assets/dc_params_primer.png" in D["changed"] and D["primer"]["picture"]["width"] == 1800,
              f"[STUDIO] the replaced picture is not seen: {D['changed']}")
        r = st.call("primer_picture", base64.b64encode(b"GIF89a....").decode(), "x.gif", D["primer_edit"]["pack_yaml_sha"])
        check(r.get("ok") is False and "PNG, JPEG or WebP" in r.get("error", ""), f"[STUDIO] a GIF: {r}")
        r = st.call("remove_primer_picture", D["primer_edit"]["pack_yaml_sha"])
        check(r.get("ok") and not (d / "assets" / "dc_params_primer.png").exists()
              and yaml.safe_load((d / "pack.yaml").read_text(encoding="utf-8"))["primer"]["image"] is None,
              f"[STUDIO] remove the picture: {r}")
        view = st.call("view", {"topology": 7})["data"]
        check(view["primer"]["planner"]["picture"] is None and view["primer"]["planner"]["text"],
              "[STUDIO] the Prompt viewer after the picture went")
        r = st.call("undo_primer", "picture")
        check(r.get("ok") and (d / "assets" / "dc_params_primer.png").read_bytes() == before["assets/dc_params_primer.png"],
              f"[STUDIO] Undo the picture: {r}")
        r = st.call("undo_primer", "agents")
        check(r.get("ok") and snapshot(d) == before,
              f"[STUDIO] Undo both: not the files as opened "
              f"{[k for k in set(before) | set(snapshot(d)) if before.get(k) != snapshot(d).get(k)]}")
        r = st.call("undo_primer", "colour")
        check(r.get("ok") is False, "[STUDIO] an Undo of something else")
    finally:
        st.stop()
        shutil.rmtree(d.parent, ignore_errors=True)
    return "page data, 4 calls, Undo"


def check_page() -> None:
    js = (ROOT / "studio" / "web" / "studio.js").read_text(encoding="utf-8")
    server = (ROOT / "studio" / "server.py").read_text(encoding="utf-8")
    for name in ("set_primer_agent", "primer_picture", "remove_primer_picture", "undo_primer"):
        check(f"'{name}'" in js and f'("{name}", primer.' in server, f"[PAGE] {name}: page and server disagree")
    check("{ id: 'primer', n: 3, label: 'Primer' }" in js, "[PAGE] the Primer section is not the third")


def main() -> int:
    summary = {}
    _run(check_engine, "[ENGINE]")
    _run(check_messages, "[MESSAGES]")
    _run(check_editor, "[EDITOR]")
    _run(check_import, "[IMPORT]")
    _run(check_page, "[PAGE]")
    summary["calls"] = _run(check_calls, "[CALLS]")
    summary["validate"] = _run(check_validate, "[VALIDATE]")
    summary["studio"] = _run(check_studio, "[STUDIO]")
    if FAILURES:
        print(f"FAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("PASS - the primer is the setup's: the engine reads its section (or the default), each agent it "
          "names gets exactly its text and picture with every call and no other does, Validate checks it, a "
          f"new configurator gives it to no agent, and the Studio's Primer page edits it and puts it back "
          f"byte for byte ({summary}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
