"""The configurators a repository holds: ``setups/<name>/``, all stored the
same way (``engine/setups.py``, ``setups/README.md``).

1. ENGINE -- a folder of ``setups/`` is a setup when it holds a
   ``pack.yaml``; the default is ``setups/propeller``, else the first setup
   (a package holds one); with none, ``setups/propeller`` all the same --
   no other layout is read; ``DC_PACK_DIR`` is taken from the root when
   relative, as it is when absolute.
2. THE REPOSITORY -- the propeller is committed in ``setups/propeller``, no
   ``dc_pack/`` is left; ``config.py`` and the Studio run it by default, and
   both take ``DC_PACK_DIR`` alike; the vacuum hose adapter is committed
   too (TODO F125) and no ignore file leaves a configurator out; the image
   installs what every setup's tools need -- the ``Dockerfile`` is the
   package builder's merge of all of them (``studio/package.py``
   ``merge_apt``), for the hose adapter the pinned OpenSCAD.
3. REMEMBERED AND SETTINGS -- the configurator loaded last is remembered
   (``ACTIVE_SETUP_FILE`` in the tests) and started with, while it is a
   folder of ``setups/`` -- by the engine and the local Studio, never by a
   shared Studio copy, which starts from the propeller; each one's Workflow
   Settings files are its own (``workflow_settings/setups/<setup>/``), and
   the propeller moves its old ones there once; only ``database: true`` in a
   ``pack.yaml`` lets a setup use the database; packages leave the files
   this computer saves out.
4. SWITCH -- loading another configurator in place (``engine/switch.py``)
   equals a fresh start with it: a process that starts with the propeller
   and loads a stand-in configurator (other words, one more parameter, no
   database), the vacuum hose adapter, and the propeller again, has after each load what a process started with that
   one has -- every agent's prompt and tools and primer in topologies 3, 5
   and 7, the texts modules keep (``on_load``), the database rule, the
   Workflow Settings files, the archive's record -- and the configurator's
   page serves the same page, scripts and lists.  No module takes a copy,
   at import, of what a load reads again (the globals of each ``on_load``
   function, the Workflow Settings paths), nor reads the setup at import
   into anything else: either would keep the configurator loaded first.
5. MENU -- the main menu lists the configurators of ``setups/`` with the
   loaded one marked; loading one is refused while a session, a turn or the
   queue runs (409, said on the menu too), without the invite code (401),
   for a name that is not a folder of ``setups/`` (404), and for a setup
   that cannot run (422, with its problems: the loaded one stays); a load
   is remembered for the next start.

    py -3.13 extra_utilities/tests/smoke_test_setups.py
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine import setups as S  # noqa: E402

FAILURES: list[str] = []


def check(ok: bool, what: str) -> None:
    if not ok:
        FAILURES.append(what)


def _run(group, tag: str):
    try:
        return group()
    except Exception as exc:                                        # noqa: BLE001
        check(False, f"{tag} {type(exc).__name__}: {str(exc)[:300]}")
        return None


def setup(root: Path, name: str, pack_yaml: bool = True) -> Path:
    d = root / "setups" / name
    d.mkdir(parents=True)
    if pack_yaml:
        (d / "pack.yaml").write_text("pack_format: 1\n", encoding="utf-8")
    return d


def check_engine() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="setups_smoke_"))
    try:
        (tmp / "dc_pack").mkdir()
        (tmp / "dc_pack" / "pack.yaml").write_text("pack_format: 1\n", encoding="utf-8")
        check(S.all_setups(tmp) == [] and S.default_setup(tmp) == tmp / "setups" / "propeller",
              f"[ENGINE] no setups/ (an old dc_pack/ is not read): {S.all_setups(tmp)} {S.default_setup(tmp)}")
        b = setup(tmp, "bravo")
        a = setup(tmp, "alpha")
        setup(tmp, "notes", pack_yaml=False)
        (tmp / "setups" / "README.md").write_text("x", encoding="utf-8")
        check(S.all_setups(tmp) == [a, b], f"[ENGINE] the setups: {S.all_setups(tmp)}")
        check(S.default_setup(tmp) == a, f"[ENGINE] without a propeller, the first: {S.default_setup(tmp)}")
        p = setup(tmp, "propeller")
        check(S.default_setup(tmp) == p, f"[ENGINE] the propeller first: {S.default_setup(tmp)}")
        check(S.resolve(tmp, None) == p and S.resolve(tmp, "") == p, "[ENGINE] an empty DC_PACK_DIR")
        check(S.resolve(tmp, "setups/bravo") == b, f"[ENGINE] a relative one: {S.resolve(tmp, 'setups/bravo')}")
        check(S.resolve(tmp, str(b)) == b, "[ENGINE] an absolute one")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _default_in_child(env_value: str | None) -> list[str]:
    env = {k: v for k, v in os.environ.items() if k != "DC_PACK_DIR"}
    if env_value is not None:
        env["DC_PACK_DIR"] = env_value
    # Not the configurator this computer loaded last.
    env.update(PYTHONIOENCODING="utf-8", DATABASE_URL="", DATABASE_PUBLIC_URL="",
               ACTIVE_SETUP_FILE=str(Path(tempfile.mkdtemp(prefix="setups_active_")) / "none.json"))
    code = ("import config; from studio.__main__ import default_pack; "
            "print(config.DC_PACK_DIR); print(default_pack())")
    out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env, capture_output=True,
                         text=True, encoding="utf-8", timeout=120)
    return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]


def check_repo() -> None:
    tracked = subprocess.run(["git", "ls-files", "setups", "dc_pack"], cwd=str(ROOT), capture_output=True,
                             text=True, check=True).stdout.split()
    check("setups/propeller/pack.yaml" in tracked and "setups/README.md" in tracked
          and not any(t.startswith("dc_pack/") for t in tracked),
          "[REPO] the propeller is not committed in setups/propeller, or dc_pack/ is left")
    check("setups/vacuum_hose_adapter/pack.yaml" in tracked
          and "setups/vacuum_hose_adapter/tools/vacuum_hose_adapter/vacuum-hose-adapter.scad" in tracked,
          "[REPO] the vacuum hose adapter is not committed")
    from studio import package as K
    setups = [s for s in sorted((ROOT / "setups").iterdir()) if (s / "pack.yaml").is_file()]
    ignored = [s.name for s in setups
               if subprocess.run(["git", "check-ignore", "-q", f"setups/{s.name}/pack.yaml"],
                                 cwd=str(ROOT)).returncode == 0]
    check(not ignored, f"[REPO] git leaves out {ignored}")
    docker = K.IgnoreRules((ROOT / ".dockerignore").read_text(encoding="utf-8"))
    out = [s.name for s in setups if docker.ignored(f"setups/{s.name}", True)]
    check(not out, f"[REPO] the images leave out {out}")
    # the image: what every setup's tools need, as a package of each would have it
    tools = {}
    for s in setups:
        tools.update(K.setup_files(s))
    dock = (ROOT / "Dockerfile").read_bytes().decode("utf-8")
    merged, _notes = K.merge_apt(dock, tools)
    check(merged == dock, "[IMAGE] the Dockerfile lacks what a setup's tools need (studio/package.py merge_apt)")
    check(dock.splitlines().count(K.OPENSCAD_MARK) == 1 and "ENV OPENSCAD_PATH=/opt/openscad/AppRun" in dock,
          "[IMAGE] the image does not install the pinned OpenSCAD the hose adapter runs")
    check(not (ROOT / "dc_pack").exists(), "[REPO] a dc_pack/ folder is left")
    want = str(ROOT / "setups" / "propeller")
    got = _default_in_child(None)
    check(got == [want, want], f"[REPO] the default for config.py and the Studio: {got}")
    other = str(ROOT / "setups" / "elsewhere")
    got = _default_in_child("setups/elsewhere")
    check(got == [other, other], f"[REPO] DC_PACK_DIR for config.py and the Studio: {got}")


def check_remembered() -> None:
    from engine import pack
    tmp = Path(tempfile.mkdtemp(prefix="setups_smoke_"))
    old = os.environ.get(S.ACTIVE_ENV)
    os.environ[S.ACTIVE_ENV] = str(tmp / "state" / "active.json")
    try:
        p, b = setup(tmp, "propeller"), setup(tmp, "bravo")
        check(S.remembered(tmp) is None and S.resolve(tmp, "") == p, "[REMEMBERED] nothing remembered yet")
        S.remember(tmp, b)
        check(json.loads((tmp / "state" / "active.json").read_text(encoding="utf-8")) == {"setup": "bravo"},
              "[REMEMBERED] the file written")
        check(S.remembered(tmp) == b and S.resolve(tmp, "") == b and S.resolve(tmp, "setups/propeller") == p,
              f"[REMEMBERED] the one loaded last is started with, unless DC_PACK_DIR names one: {S.resolve(tmp, '')}")
        S.remember(tmp, tmp / "elsewhere")
        check(S.remembered(tmp) == b, "[REMEMBERED] a folder outside setups/ was remembered")
        for text in ('{"setup": "gone"}', '{"setup": "../setups/bravo"}', "not json", '["bravo"]'):
            (tmp / "state" / "active.json").write_text(text, encoding="utf-8")
            check(S.remembered(tmp) is None and S.resolve(tmp, "") == p,
                  f"[REMEMBERED] {text!r} is not a configurator to start with")
        # The Studio: locally the one loaded last; a shared copy (online, or
        # inside the app) starts from the propeller.
        import studio.__main__ as SM
        S.remember(tmp, b)
        real_repo, real_env = SM.REPO, os.environ.pop("DC_PACK_DIR", None)
        try:
            SM.REPO = tmp
            check(SM.default_pack() == b and SM.example_pack() == p,
                  f"[REMEMBERED] the Studio: local {SM.default_pack()}, shared copy {SM.example_pack()}")
            os.environ["DC_PACK_DIR"] = "setups/bravo"
            check(SM.default_pack() == b and SM.example_pack() == b,
                  "[REMEMBERED] DC_PACK_DIR does not name the Studio's setup")
        finally:
            SM.REPO = real_repo
            os.environ.pop("DC_PACK_DIR", None)
            if real_env is not None:
                os.environ["DC_PACK_DIR"] = real_env
        # Workflow Settings: each setup's own; the old file moves once, for
        # setups/propeller only.
        ws = tmp / "workflow_settings"
        ws.mkdir()
        (ws / "tool_settings.json").write_text("{}\n", encoding="utf-8")
        check(S.settings_file(tmp, b, "tool_settings.json") == ws / "setups" / "bravo" / "tool_settings.json"
              and (ws / "tool_settings.json").is_file(), "[SETTINGS] another setup took the propeller's file")
        f = S.settings_file(tmp, p, "tool_settings.json")
        check(f == ws / "setups" / "propeller" / "tool_settings.json" and f.is_file()
              and not (ws / "tool_settings.json").exists(), "[SETTINGS] the propeller's file did not move")
        (ws / "tool_settings.json").write_text('{"x": 1}\n', encoding="utf-8")
        check(S.settings_file(tmp, p, "tool_settings.json").read_text(encoding="utf-8") == "{}\n",
              "[SETTINGS] a file already in place was replaced")
        # The database: only database: true.
        for text, want in (("database: true\n", True), ("", False), ("database: yes please\n", False),
                           ("database: 1\n", False), ("database: [\n", False)):
            (b / "pack.yaml").write_text("pack_format: 1\n" + text, encoding="utf-8")
            check(pack.uses_database(b) is want, f"[DATABASE] {text!r} gives {pack.uses_database(b)}")
        check(pack.uses_database(ROOT / "setups" / "propeller"), "[DATABASE] the propeller may not use it")
        check(not pack.uses_database(ROOT / "setups" / "vacuum_hose_adapter"),
              "[DATABASE] the vacuum hose adapter may use it")
        from studio import package as K
        from studio import prepare as PR
        for rel in ("workflow_settings/active_setup.json", "workflow_settings/setups/propeller/tool_settings.json"):
            check(K._skipped(rel), f"[PACKAGE] a package takes {rel}")
        check(("workflow_settings/setups", True, "workflow_settings/setups/") in PR.GIT_OUT,
              "[PACKAGE] Prepare for GitHub does not keep workflow_settings/setups/ out of git")
    finally:
        if old is None:
            os.environ.pop(S.ACTIVE_ENV, None)
        else:
            os.environ[S.ACTIVE_ENV] = old
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# SWITCH: child processes
# ---------------------------------------------------------------------------

# The stand-in configurator: the propeller in other words -- at least one
# word of every text a load reads again -- with one more parameter, one
# render view fewer, and without the database.
_STAND_IN_WORDS = {"fragments/dc/dc_name.md": "turbine",
                   "fragments/dc/app_title.md": "Turbine Design Configurator",
                   "fragments/dc/domain_description.md": "turbine design configurator system",
                   "fragments/dc/search_query_examples.md": "'wide turbine vanes that stalled'",
                   "fragments/dc/parameter_search_example.md": '"bladeCount": 4, "zzProbe": 0.5',
                   "fragments/tools/output_model.md": "solid",
                   "fragments/tools/output_models.md": "solids",
                   "fragments/tools/output_images.md": "views",
                   "fragments/tools/output_images_label.md": "View images"}


def stand_in(root: Path, name: str = "turbine") -> Path:
    d = root / "setups" / name
    shutil.copytree(ROOT / "setups" / "propeller", d, ignore=shutil.ignore_patterns("__pycache__"))
    for rel, text in _STAND_IN_WORDS.items():
        (d / rel).write_text(text + "\n", encoding="utf-8")
    spec = json.loads((d / "parameters.json").read_text(encoding="utf-8"))
    spec["parameters"].append({"name": "zzProbe", "type": "float", "min": 0, "max": 1, "step": 0.1,
                               "default": 0.5, "group": "outer", "label": "Probe", "unit": "mm",
                               "db_unit": "mm", "db_description": "A stand-in parameter"})
    spec["groups"][-1]["order"].append("zzProbe")
    (d / "parameters.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    lst = d / "fragments" / "dc" / "parameter_list.md"
    lst.write_text(lst.read_text(encoding="utf-8") + "\n``zzProbe`` [0; 1] mm: a stand-in parameter.\n",
                   encoding="utf-8")
    gen = d / "tools" / "generate_and_render_propeller" / "tool.yaml"
    gen.write_text(re.sub(r"(?m)^    - \{view: side, .*\n", "", gen.read_text(encoding="utf-8")),
                   encoding="utf-8")
    y = d / "pack.yaml"
    text = re.sub(r"(?m)^database: true\n", "", y.read_text(encoding="utf-8"))
    y.write_text(re.sub(r"(?m)^(  (?:small|medium|large): \{.*)\}$", r"\1, zzProbe: 0.5}", text),
                 encoding="utf-8")
    return d


def _child_env(first: Path, active: Path) -> dict:
    env = dict(os.environ)
    env.update(PYTHONIOENCODING="utf-8", DATABASE_URL="", DATABASE_PUBLIC_URL="", INVITE_CODE="",
               OPENAI_API_KEY=env.get("OPENAI_API_KEY") or "sk-dummy", DC_PACK_DIR=str(first),
               ACTIVE_SETUP_FILE=str(active))
    for v in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME",
              "S3_ENDPOINT_URL", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
        env.pop(v, None)
    return env


def _start(mode: str, setups: list[Path], out: Path, active: Path):
    return subprocess.Popen([sys.executable, str(Path(__file__).resolve()), mode, str(out)]
                            + [str(s) for s in setups], cwd=str(ROOT), env=_child_env(setups[0], active),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _finish(proc, out: Path, tag: str):
    log, _ = proc.communicate(timeout=900)
    if proc.returncode != 0 or not out.is_file():
        tail = log.decode("utf-8", "replace")[-1500:]
        check(False, f"{tag} the child failed ({proc.returncode}): {tail}")
        return None
    return json.loads(out.read_text(encoding="utf-8"))


def _diff(a: dict, b: dict) -> list[str]:
    out = []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k), b.get(k)
        if x == y:
            continue
        if isinstance(x, dict) and isinstance(y, dict):
            inner = sorted(i for i in set(x) | set(y) if x.get(i) != y.get(i))
            out.append(f"{k}: {inner[:6]}")
        else:
            out.append(f"{k}: {str(x)[:80]!r} vs {str(y)[:80]!r}")
    return out


def _engine_snapshot() -> dict:
    import config
    import topology_prompt_snapshot as TPS
    import studio.engine_view as EV
    from agents import loader
    from agents.database_handler import database_handler as DH
    from agents.database_handler import db_writer as DW
    from agents.dc_output_inspector import dc_output_inspector as DCOI
    from agents.requirements_analyst import requirements_analyst as RA
    from agents.shared import attempt_views as AV
    from agents.shared import context_pruner as CP
    from agents.shared import postgres_pool, r2_uploader
    from agents.shared import prompts as P
    from agents.shared import sessions_queue as SQ
    from agents.shared.session import Session
    from engine import pack, parameter_access as PA, pack_tools as PT
    from tools.database_search import database_search as DS
    snap: dict = {}
    for t in (3, 5, 7):
        snap[f"prompts {t}"] = TPS._assemble(t)["prompts"]
        snap[f"tools {t}"] = EV.team_tools(t)
        snap[f"primer {t}"] = EV.primer_view(t)
    import datetime
    rec = Path(tempfile.mkdtemp(prefix="setups_archive_"))
    loader._write_configurator(rec)
    config.DATABASE_URL = "postgresql://stand-in"
    for v in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"):
        os.environ[v] = "stand-in"
    try:
        database = [pack.uses_database(), postgres_pool._resolve_url() != "", r2_uploader.is_enabled()]
    finally:
        config.DATABASE_URL = ""
        for v in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"):
            os.environ.pop(v, None)
    snap["module texts"] = {
        "DC_NAME": P.DC_NAME, "PARAMETER_NAMES": list(P.PARAMETER_NAMES),
        "PARAMETER_TYPES": {k: repr(v) for k, v in P.PARAMETER_TYPES.items()},
        "pruner": [CP.COARSE_SUMMARY_PROMPT, CP.FINE_SUMMARY_PROMPT, CP.ULTRA_COMPACT_SUMMARY_PROMPT],
        "classifier": SQ._CLASSIFIER_SYSTEM,
        "database_search": [DS._QUERY_DOC, DS._QUERY_DOC_EITHER, DS._PARAMETERS_DOC],
        "requirements_analyst": [RA._IMAGE_PERSISTENCE_ON, RA._IMAGE_PERSISTENCE_OFF, RA._COMPARISON_MODE_1],
        "dc_output_inspector": [DCOI._IMAGE_PERSISTENCE_ON, DCOI._IMAGE_PERSISTENCE_OFF,
                                DCOI._COMPARISON_MODE_1],
        "views": [[list(v) for v in AV.VIEWS], sorted(AV.MESH_VIEWS), AV.VIEW_FILES],
        "dh reminder": DH.agent_facing_tail(),
        "stitching": DW._load_stitching_prompt(),
    }
    code = {}
    for name in sorted(PT._read_manifests()):
        try:
            code[name] = Path(PT.plugin(name).module.__file__).resolve().as_posix()
        except Exception as exc:                                    # noqa: BLE001
            code[name] = type(exc).__name__
    snap["tool code"] = code
    snap["setup"] = {
        "settings files": [PT.OVERRIDES_PATH.relative_to(ROOT).as_posix(),
                           PA.OVERRIDES_PATH.relative_to(ROOT).as_posix()],
        "database, pool, file store": database,
        "session": Session(session_id="setups_smoke",
                           session_ts=datetime.datetime.now(datetime.timezone.utc)).setup,
        "archive record": json.loads((rec / "configurator.json").read_text(encoding="utf-8")),
    }
    shutil.rmtree(rec, ignore_errors=True)
    return snap


def engine_child(out: str, setups: list[str]) -> int:
    import studio.engine_view as EV
    EV.load_engine()
    EV.setup_defaults("base")
    from engine import switch
    snaps = [_engine_snapshot()]
    for s in setups[1:]:
        switch.load(Path(s))
        snaps.append(_engine_snapshot())
    Path(out).write_text(json.dumps(snaps, default=str), encoding="utf-8")
    return 0


_WEB_GETS = ("/configurator", "/pack/page.js", "/pack/parameters.js", "/api/parameters",
             "/api/tool_settings", "/api/parameter_access", "/api/settings", "/api/render_compression",
             "/pack/preview/preview.js", "/pack/assets/general-profile.png")


def _web_snapshot(client) -> dict:
    snap = {}
    for path in _WEB_GETS:
        r = client.get(path)
        body = (r.content.decode("utf-8", "replace") if "png" not in path
                else hashlib.sha256(r.content).hexdigest())
        snap[path] = f"{r.status_code} {r.headers.get('content-type')} {body}"
    return snap


def web_child(out: str, setups: list[str]) -> int:
    from fastapi.testclient import TestClient
    import web_app
    client = TestClient(web_app.app)
    snaps = [_web_snapshot(client)]
    for s in setups[1:]:
        web_app._switch.load(Path(s))
        snaps.append(_web_snapshot(client))
    Path(out).write_text(json.dumps(snaps), encoding="utf-8")
    return 0


def menu_child(out: str, setups: list[str]) -> int:
    """The menu and its load call, on a root of its own: setups[0] its
    propeller, then the stand-in and two broken ones beside it."""
    from fastapi.testclient import TestClient
    import web_app
    from agents.shared import context_pruner as CP
    from agents.shared import prompts as P
    from agents.shared import sessions_queue as SQ
    root = Path(setups[0]).parents[1]
    propeller = (P.DC_NAME, list(P.PARAMETER_NAMES), CP.COARSE_SUMMARY_PROMPT, SQ._CLASSIFIER_SYSTEM)
    web_app.PROJECT_ROOT = root
    client = TestClient(web_app.app)
    found: list[str] = []

    def ok(cond, what):
        if not cond:
            found.append(what)

    def words():
        r = client.get("/pack/page.js").text
        return json.loads(r[len("window.PACK_PAGE = "):].rstrip().rstrip(";"))["words"]["dc_name"]

    def load(name):
        return client.post("/api/setups/load", json={"setup": name})

    d = client.get("/api/setups").json()
    ok([(s["setup"], s["loaded"]) for s in d["setups"]] == [("broken", False), ("propeller", True),
                                                          ("turbine", False), ("wordless", False)]
       and d["refusal"] is None,
       f"[MENU] the list: {d}")
    page = client.get("/").text
    cards = re.findall(r'<a class="choice" href="/configurator" data-setup="([^"]+)" data-loaded="(\d)"', page)
    ok(cards == [("broken", "0"), ("propeller", "1"), ("turbine", "0"), ("wordless", "0")]
       and 'href="/studio/"' in page
       and "<h2>Turbine Design Configurator</h2>" in page
       and '<h2>Propeller Design Configurator <em class="badge">Loaded</em></h2>' in page
       and '<p id="refusal" class="note"></p>' in page and not re.findall(r"\$[A-Za-z_]", page),
       f"[MENU] the page's cards: {cards}")
    r = load("turbine")
    ok(r.status_code == 200 and words() == "turbine" and P.DC_NAME == "turbine",
       f"[MENU] loading the stand-in: {r.status_code} {r.text[:200]} {words()}")
    ok(json.loads(Path(os.environ["ACTIVE_SETUP_FILE"]).read_text(encoding="utf-8")) == {"setup": "turbine"},
       "[MENU] the load was not remembered")
    for name in ("nope", "../setups/turbine", "setups/turbine", ""):
        ok(load(name).status_code == 404, f"[MENU] {name!r} is not a configurator of setups/")
    states = (("_BOX.session", "A design session is open"), ("_TURN_IN_FLIGHT", "A chat turn is running"),
              ("_END_IN_FLIGHT", "A session is being saved"), ("_QUEUE_IN_FLIGHT", "A Sessions Queue is running"))
    for state, says in states:
        if state == "_BOX.session":
            web_app._BOX.session = object()
        else:
            setattr(web_app, state, True)
        try:
            r = load("propeller")
            ok(r.status_code == 409 and says in r.json()["detail"] and words() == "turbine",
               f"[MENU] {state}: loading answered {r.status_code} {r.text[:160]}")
            ok(load("turbine").status_code == 200, f"[MENU] {state}: the loaded one does not just open")
            ok(says in client.get("/").text and says in client.get("/api/setups").json()["refusal"],
               f"[MENU] {state}: the menu does not say why")
        finally:
            if state == "_BOX.session":
                web_app._BOX.session = None
            else:
                setattr(web_app, state, False)
    real = web_app._configured_invite_code
    web_app._configured_invite_code = lambda: "qzx-code"
    web_app._BOX.authed = False
    try:
        ok(load("propeller").status_code == 401 and words() == "turbine", "[MENU] loaded without the invite code")
        ok(client.post("/api/auth", json={"code": "qzx-code"}).status_code == 200, "[MENU] the invite code")
        ok(load("propeller").status_code == 200 and words() == "propeller", "[MENU] the code given, not loaded")
    finally:
        web_app._configured_invite_code = real
    r = load("broken")
    detail = r.json().get("detail") if r.status_code == 422 else None
    ok(isinstance(detail, dict) and detail.get("problems") and any("parameters.json" in p for p in detail["problems"])
       and words() == "propeller" and P.DC_NAME == "propeller"
       and web_app._pack.pack_dir() == root / "setups" / "propeller",
       f"[MENU] a broken setup: {r.status_code} {r.text[:300]} -- loaded now: {web_app._pack.pack_dir()}")
    ok(json.loads(Path(os.environ["ACTIVE_SETUP_FILE"]).read_text(encoding="utf-8")) == {"setup": "propeller"},
       "[MENU] a refused load was remembered")
    # One whose words cannot all be read: the queue classifier's is missing,
    # and its function runs after the parameters' -- so the load fails
    # half-way, and what was read of it is put back.
    hooks = web_app._switch._HOOKS
    ok(hooks.index(SQ._fill_classifier) > hooks.index(P._read_setup_data),
       "[MENU] the classifier's words are read first: the half-way failure tests nothing")
    r = load("wordless")
    ok(r.status_code == 422 and "produced_outputs_examples" in str(r.json().get("detail"))
       and (P.DC_NAME, list(P.PARAMETER_NAMES), CP.COARSE_SUMMARY_PROMPT, SQ._CLASSIFIER_SYSTEM) == propeller
       and words() == "propeller", f"[MENU] a setup missing a word: {r.status_code} {r.text[:300]} {P.DC_NAME}")
    Path(out).write_text(json.dumps(found), encoding="utf-8")
    return 0


def _runtime_files() -> list[Path]:
    files = [ROOT / "web_app.py", ROOT / "config.py"]
    for folder in ("agents", "tools", "engine", "workflow_settings"):
        files += (ROOT / folder).rglob("*.py")
    files += (ROOT / "setups").glob("*/tools/**/*.py")
    return [f for f in files if "__pycache__" not in f.parts]


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


_BLOCKS = ("body", "orelse", "finalbody", "handlers")


def _import_time(body):
    """The statements of *body* run at import: not inside a function, nor
    under ``if __name__ == "__main__":``."""
    for node in body:
        if isinstance(node, ast.If) and ast.unparse(node.test) in ('__name__ == "__main__"',
                                                                  "__name__ == '__main__'"):
            continue
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for field in _BLOCKS:
            yield from _import_time(getattr(node, field, []) or [])


def _own_expressions(node) -> list:
    """What statement *node* itself evaluates (not its blocks; of a
    function, its decorators and default values)."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.decorator_list + [d for d in node.args.defaults + node.args.kw_defaults if d]
    out = []
    for field, value in ast.iter_fields(node):
        if field not in _BLOCKS:
            out += value if isinstance(value, list) else [value]
    return [v for v in out if isinstance(v, ast.AST)]


def check_import_copies() -> None:
    """What a load reads again -- the globals each ``on_load`` function sets,
    and the Workflow Settings paths ``engine/switch.py`` sets -- is read
    from its module where it is used: no module takes a copy at import."""
    trees = {f: ast.parse(f.read_text(encoding="utf-8")) for f in _runtime_files()}
    hooked: dict[str, set[str]] = {"engine.pack_tools": {"OVERRIDES_PATH"},
                                   "engine.parameter_access": {"OVERRIDES_PATH"}}
    on_load: dict[Path, set[str]] = {}
    for f, tree in trees.items():
        fns = on_load[f] = {n.args[0].id for n in ast.walk(tree) if isinstance(n, ast.Call)
                            and getattr(n.func, "attr", None) == "on_load" and n.args
                            and isinstance(n.args[0], ast.Name)}
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in fns:
                names = {g for sub in ast.walk(node) if isinstance(sub, ast.Global) for g in sub.names}
                hooked.setdefault(_module_name(f), set()).update(names)
    check(len(hooked) >= 9 and "PARAMETER_NAMES" in hooked.get("agents.shared.prompts", set()),
          f"[COPIES] the values a load reads again were not found: {sorted(hooked)}")
    for f, tree in trees.items():
        own = _module_name(f)
        aliases: dict[str, str] = {}
        for node in _import_time(tree.body):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name in hooked:
                        aliases[a.asname or a.name] = a.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                taken = {a.name for a in node.names} & hooked.get(node.module, set())
                check(not taken, f"[COPIES] {f.relative_to(ROOT).as_posix()}:{node.lineno} takes "
                                 f"{sorted(taken)} from {node.module} at import")
                for a in node.names:
                    if f"{node.module}.{a.name}" in hooked:
                        aliases[a.asname or a.name] = f"{node.module}.{a.name}"
        for node in _import_time(tree.body):
            for sub in (s for e in _own_expressions(node) for s in ast.walk(e)):
                if (isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name)
                        and aliases.get(sub.value.id) not in (None, own)
                        and sub.attr in hooked[aliases[sub.value.id]]):
                    check(False, f"[COPIES] {f.relative_to(ROOT).as_posix()}:{sub.lineno} reads "
                                 f"{sub.value.id}.{sub.attr} at import")
    # Nor does a module read the setup at import -- itself, or through one
    # of its own functions -- other than into what its own on_load function
    # reads again.
    for f, tree in trees.items():
        own = _module_name(f)
        if own in _READERS:
            continue
        readers: dict[str, str] = {}
        for node in _import_time(tree.body):
            if isinstance(node, ast.Import):
                readers.update({a.asname or a.name: a.name for a in node.names if a.name in _READERS})
            elif isinstance(node, ast.ImportFrom) and node.module:
                for a in node.names:
                    full = f"{node.module}.{a.name}"
                    if full in _READERS or node.module in _READERS:
                        readers[a.asname or a.name] = full

        def reader(fn):
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id in readers:
                name = f"{readers[fn.value.id]}.{fn.attr}"
            else:
                name = readers.get(fn.id) if isinstance(fn, ast.Name) else None
            return None if name in _ENGINE_ONLY else name

        functions = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and n.name not in on_load[f]}
        grew = True
        while grew:
            grew = False
            for name, fn in functions.items():
                if name not in readers and any(isinstance(s, ast.Call) and reader(s.func)
                                               for s in ast.walk(fn)):
                    readers[name] = f"{own}.{name}"
                    grew = True
        for node in _import_time(tree.body):
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target] if isinstance(node, ast.AnnAssign) else [])
            if targets and all(isinstance(t, ast.Name) and t.id in hooked.get(own, set()) for t in targets):
                continue
            for call in (s for e in _own_expressions(node) for s in _walk_no_lambda(e)
                         if isinstance(s, ast.Call)):
                name = reader(call.func)
                if name:
                    check(False, f"[COPIES] {f.relative_to(ROOT).as_posix()}:{call.lineno} calls "
                                 f"{name} at import, and no on_load function reads it again")


# What reads the active setup (a call at import is read once), and what of
# it reads only the engine's own slot registry.
_READERS = {"engine.pack", "engine.pack_tools", "engine.parameters", "engine.primer",
            "engine.parameter_access", "engine.image_run", "engine.parameter_schema",
            "agents.shared.pack_text"}
_ENGINE_ONLY = {"engine.pack.registry", "engine.pack.slots", "engine.pack.slot_spec"}


def _walk_no_lambda(node):
    """ast.walk without what a lambda runs when it is called."""
    yield node
    if isinstance(node, ast.Lambda):
        return
    for child in ast.iter_child_nodes(node):
        yield from _walk_no_lambda(child)


def check_switch() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="setups_switch_"))
    try:
        prop = ROOT / "setups" / "propeller"
        turbine = stand_in(tmp)
        hose = ROOT / "setups" / "vacuum_hose_adapter"
        others = [turbine, hose]
        active = tmp / "active.json"
        for mode, tag in (("--engine-child", "[SWITCH]"), ("--web-child", "[SWITCH PAGE]")):
            seq = [prop] + others + [prop]
            procs = {"switched": (_start(mode, seq, tmp / f"{mode}_seq.json", active), tmp / f"{mode}_seq.json")}
            for o in others:
                f = tmp / f"{mode}_{o.name}.json"
                procs[o.name] = (_start(mode, [o], f, active), f)
            got = {k: _finish(p, f, f"{tag} {k}:") for k, (p, f) in procs.items()}
            if any(v is None for v in got.values()):
                continue
            snaps = got["switched"]
            check(len(snaps) == len(seq), f"{tag} {len(snaps)} snapshots for {len(seq)} setups")
            d = _diff(snaps[0], snaps[-1])
            check(not d, f"{tag} the propeller after the others is not the propeller: {d[:4]}")
            for i, o in enumerate(others, 1):
                d = _diff(got[o.name][0], snaps[i])
                check(not d, f"{tag} {o.name} loaded in place is not {o.name} at start: {d[:4]}")
                check(_diff(snaps[0], snaps[i]), f"{tag} {o.name} looks like the propeller: the test proves nothing")
            if mode == "--engine-child":
                t = snaps[1]["module texts"]
                check(t["DC_NAME"] == "turbine" and t["PARAMETER_NAMES"][-1] == "zzProbe"
                      and snaps[1]["setup"]["database, pool, file store"] == [False, False, False]
                      and snaps[0]["setup"]["database, pool, file store"] == [True, True, True]
                      and snaps[1]["setup"]["settings files"] == [
                          "workflow_settings/setups/turbine/tool_settings.json",
                          "workflow_settings/setups/turbine/parameter_access.json"]
                      and snaps[1]["setup"]["archive record"] == {
                          "setup": "turbine", "title": "Turbine Design Configurator", "dc_name": "turbine"}
                      and snaps[1]["setup"]["session"] == "turbine",
                      f"{tag} the stand-in's own: {t['DC_NAME']} {snaps[1]['setup']}")
        # The menu, on a root of its own.
        root = tmp / "menu"
        shutil.copytree(prop, root / "setups" / "propeller", ignore=shutil.ignore_patterns("__pycache__"))
        stand_in(root)
        broken = stand_in(root, "broken")
        (broken / "parameters.json").write_text('{"groups": [], "parameters": [{"name": "x"}]}\n',
                                                encoding="utf-8")
        (stand_in(root, "wordless") / "fragments" / "tools" / "produced_outputs_examples.md").unlink()
        f = tmp / "menu.json"
        found = _finish(_start("--menu-child", [root / "setups" / "propeller"], f, tmp / "menu_active.json"),
                        f, "[MENU]")
        for line in found or []:
            check(False, line)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    _run(check_engine, "[ENGINE]")
    _run(check_repo, "[REPO]")
    _run(check_remembered, "[REMEMBERED]")
    _run(check_import_copies, "[COPIES]")
    _run(check_switch, "[SWITCH]")
    if FAILURES:
        print(f"FAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("PASS - every configurator is a folder of setups/, the propeller the default for the engine and "
          "the Studio alike, DC_PACK_DIR taken from the root, the vacuum hose adapter committed and in the "
          "image with the OpenSCAD its tools need; the one loaded last is started with, each keeps its own "
          "Workflow Settings, only database: true uses the database; loading the stand-in, the vacuum hose "
          "adapter, then the propeller in place "
          "equals a fresh start with each (prompts, tools and primer in topologies 3/5/7, module texts, "
          "pages); the menu loads, refuses and remembers as it should.")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--engine-child"]:
        sys.exit(engine_child(sys.argv[2], sys.argv[3:]))
    if sys.argv[1:2] == ["--web-child"]:
        sys.exit(web_child(sys.argv[2], sys.argv[3:]))
    if sys.argv[1:2] == ["--menu-child"]:
        sys.exit(menu_child(sys.argv[2], sys.argv[3:]))
    sys.exit(main())
