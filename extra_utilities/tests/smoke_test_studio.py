"""The Studio (MAS-blueprint P5a-P6b): the real server on a copy of the pack.

``python -m studio --pack <copy>`` is started as the user starts it, and its
page and its one call (``POST /api/get_all``) are checked:

1. SERVER.  The page, its scripts and the setup's pictures are served (and
   always revalidated); an unknown call answers ``{ok: false}``; a folder
   without ``pack.yaml`` is refused at start.
2. FIELDS.  Every text field of the slot registry (``source: pack``) is
   shown, filed under its registry section -- a section the page has --
   with the texts the engine reads for each topology and each agent copy,
   and files that exist.
3. WHERE.  Every assembly lines up with its marked twin (no agent without
   spans), and every field whose text is in a prompt has its "where it
   lands" sentences, in that topology.
4. PROMPTS.  The prompts shown are byte for byte the prompt matrix's
   ``base`` prompts (``extra_utilities/prompt_matrix/baseline_manifest.json``).
5. CACHE.  A second call answers from the kept copy; a changed file of the
   setup is seen by the next call (its text, the prompts, the field's place
   in them);
   and, with a stand-in build, one build serves callers that arrive
   together, a failed build is retried, and Python's ``__pycache__`` does
   not count as a change.
6. GENERIC.  The page names no configurator (its words come from the
   setup), and the Studio draft's data builder uses the Studio's functions
   instead of copies of them.

Since MAS-blueprint P5b the prompt viewer shows any choice of the settings
that change what an agent sees (``POST /api/view``):

7. VIEWER.  Every combination of ``prompt_matrix.py`` the viewer can
   express, in topologies 7 / 5 / 3: the prompts
   are the matrix baseline's and each agent's tools are the tool
   baseline's (``tool_baseline.json``), byte for byte; the token counts
   are tiktoken cl100k's of the text shown; a choice the setup does not
   offer is refused, and equal views get equal choices (a setting that
   does nothing in the topology, an access cell equal to the setup's).
   The worker pool: each job is answered by a process of its own (a
   waiting one, or a cold one when none waits), and closing the pool
   ends the waiting ones.  After a change to a file of the setup (group
   5), the default view shows it.

Since MAS-blueprint P6a the Studio edits the text fields
(``studio/editing.py``, ``POST /api/save_field`` and the others):

8. EDIT.  Every field -- each shared text and each agent's own copy -- is
   saved with a marker of its own: the Studio lists it as changed, shows
   it, and every prompt that held the field's text holds the marked one;
   the comparison with the setup as the Studio opened it names exactly the
   agents whose prompts changed.  Put back, the setup is byte for byte as
   it was.  Unlinking every linked field and giving every shared text an
   own copy changes no prompt; linking again and removing the copies, or
   linking an unlinked field and Undo, leave the setup byte for byte as it
   was.  Braces, a line break in a one-line field, an unknown $name or
   flag, an unclosed marker are refused with their reason; a stale page,
   and a change to a field whose files changed, as a conflict; none of
   them writes anything.  A file keeps its line endings.  The page checks
   a text exactly as the server does (Node runs the page's own code).

Since MAS-blueprint P6b it edits the parameters and the access grid
(``studio/params_edit.py``, ``POST /api/save_parameters`` and the others):

9. PARAMS.  ``parameters.json`` is written back in its own layout byte for
   byte.  Every parameter's range is changed, it is renamed (the old name
   retired), removed, moved within its group; a new parameter is added at
   the end of each group -- each time every agent's parameter list is in
   step with the file (the drift check's own parser), a new entry in the
   list's own shape, and saving the file as it was leaves the setup byte for
   byte as it was.  With every range changed, every prompt that showed a
   range shows the new one and the diff shows it; a list's Undo stays in
   step.  Groups, a moved parameter and an uploaded picture, an import and a
   CSV are undone by Undo all, byte for byte; previews write nothing.  Bad
   files are refused with the engine's own problems, a stale page as a
   conflict; a non-PNG, too large or existing picture, a CSV with an
   unknown column, no name column, a bad number or a new name without a
   group, are refused.  Every access cell goes through every state and back
   (pack.yaml byte for byte); the Database Handler cannot take "tool".  The
   page checks a parameter file exactly as the engine does (Node).

Takes about six minutes.  Run from the repo root:
    py -3.13 extra_utilities/tests/smoke_test_studio.py
"""
from __future__ import annotations

import ast
import base64
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ["DATABASE_URL"] = ""
os.environ["DATABASE_PUBLIC_URL"] = ""
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import config                                    # noqa: E402
from engine import pack                          # noqa: E402
from studio import server as studio_server       # noqa: E402

FAILURES: list[str] = []
STUDIO_JS = ROOT / "studio" / "web" / "studio.js"


def check(ok: bool, what: str) -> None:
    if not ok:
        FAILURES.append(what)


def _run(group, tag: str):
    """*group*(), reporting a crash under its tag."""
    try:
        return group()
    except Exception as exc:                                        # noqa: BLE001
        check(False, f"{tag} {type(exc).__name__}: {str(exc)[:300]}")
        return None


def _ws(s: str) -> str:
    return " ".join(s.split())


# ---------------------------------------------------------------------------
# the server
# ---------------------------------------------------------------------------

class Studio:
    """``python -m studio --pack <pack>`` on a free port."""

    def __init__(self, pack_dir: Path):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "studio", "--pack", str(pack_dir), "--port", str(self.port),
             "--workers", "4"],
            cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                self.get("/")
                return
            except OSError:
                if self.proc.poll() is not None:
                    break
                time.sleep(0.3)
        raise RuntimeError("the Studio did not start: "
                           + (self.proc.stdout.read().decode("utf-8", "replace")
                              if self.proc.poll() is not None else "no answer in 60 s"))

    def get(self, path: str):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=30) as r:
            return r.status, dict(r.headers), r.read()

    def call(self, name: str, *args) -> tuple[int, dict]:
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/{name}", method="POST",
            data=json.dumps({"args": list(args)}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def check_server(st: Studio, D: dict) -> None:
    status, headers, body = st.get("/")
    page = body.decode("utf-8")
    check(status == 200 and "/static/studio.js" in page and "/static/bridge.js" in page,
          f"[SERVER] GET /: {status} {page[:120]!r}")
    check(headers.get("cache-control") == "no-cache",
          f"[SERVER] the page is not revalidated: {headers.get('cache-control')}")
    for f in ("studio.js", "bridge.js", "base.css", "studio.css"):
        status, headers, body = st.get(f"/static/{f}")
        check(status == 200 and body, f"[SERVER] /static/{f}: {status}")
    for gid, url in D["group_images"].items():
        status, _, body = st.get(url)
        check(status == 200 and body[:8] == b"\x89PNG\r\n\x1a\n", f"[SERVER] {gid} picture {url}: {status}")
    status, d = st.call("no_such_call")
    check(status == 404 and d.get("ok") is False and "no_such_call" in d.get("error", ""),
          f"[SERVER] unknown call: {status} {d}")
    # A folder that is not a setup is refused at start.
    with tempfile.TemporaryDirectory() as empty:
        p = subprocess.run([sys.executable, "-m", "studio", "--pack", empty, "--port", "1"],
                           cwd=str(ROOT), capture_output=True, text=True, timeout=60)
        check(p.returncode == 2 and "no pack.yaml" in p.stderr,
              f"[SERVER] a folder without pack.yaml: rc={p.returncode} {p.stderr[-200:]!r}")


# ---------------------------------------------------------------------------
# the data
# ---------------------------------------------------------------------------

def check_fields(D: dict, copy: Path) -> int:
    real = config.DC_PACK_DIR
    config.DC_PACK_DIR = copy
    try:
        registry = pack.slots(source="pack", use="prompt")
        shown = {s["slot"]: s for s in D["slots"]}
        check(set(shown) == set(registry),
              f"[FIELDS] fields shown != the registry's: missing {sorted(set(registry) - set(shown))}, "
              f"extra {sorted(set(shown) - set(registry))}")
        sections = set(re.findall(r"\{ id: '(\w+)', n: \d+", STUDIO_JS.read_text(encoding="utf-8")))
        for name, spec in registry.items():
            s = shown.get(name)
            if s is None:
                continue
            check(s["section"] == spec.get("section") and s["section"] in sections,
                  f"[FIELDS] {name}: section {s['section']!r} (registry {spec.get('section')!r}, "
                  f"the page's {sorted(sections)})")
            for t in ("7", "5", "3"):
                v = s["values"][t]
                if v is not None:
                    check(v == pack.read(name, int(t)),
                          f"[FIELDS] {name} topology {t}: the Studio shows another text than the engine reads")
            for var in s["variants"]:
                for t in ("7", "5", "3"):
                    v = var["values"][t]
                    if v is not None:
                        check(v == pack.read(name, int(t), var["agent"]),
                              f"[FIELDS] {name}@{var['agent']} topology {t}: another text than the engine reads")
        for name, by_agent in D["files"].items():
            for files in by_agent.values():
                for f in files:
                    check((copy.parent / f).is_file(), f"[FIELDS] {name}: {f} does not exist")
        return len(shown)
    finally:
        config.DC_PACK_DIR = real


def check_where(D: dict) -> int:
    bad = {k: [a for a, s in v.items() if s == "FAILED"] for k, v in D["align"].items()}
    check(len(D["align"]) == 6 and not any(bad.values()), f"[WHERE] assemblies without spans: {bad}")
    checked = 0
    for s in D["slots"]:
        if s["kind"] == "word":
            continue
        for t in ("7", "5", "3"):
            v = s["values"][t]
            # A text with a marked region or a $name is not in a prompt as
            # written; short texts may occur by chance.
            if not v or len(v) < 40 or "<<" in v or "$" in v:
                continue
            prompts = D["prompts"][t]["prompts"]
            if not any(_ws(v) in _ws(p) for p in prompts.values()):
                continue
            checked += 1
            rows = D["where"].get(s["slot"], [])
            check(any(int(t) in topos for r in rows for topos in r["agents"].values()),
                  f"[WHERE] {s['slot']} is in a topology-{t} prompt but has no sentence there")
    return checked


def check_prompts(D: dict) -> int:
    m = json.loads((ROOT / "extra_utilities/prompt_matrix/baseline_manifest.json").read_text(encoding="utf-8"))
    n = 0
    for t in ("7", "5", "3"):
        want = m[f"base/{t}"]["prompts"]
        got = D["prompts"][t]["prompts"]
        check(set(got) == set(want), f"[PROMPTS] topology {t}: agents {sorted(got)} != {sorted(want)}")
        for agent, text in got.items():
            n += 1
            check(hashlib.sha256(text.encode("utf-8")).hexdigest() == want.get(agent),
                  f"[PROMPTS] topology {t} {agent}: not the prompt matrix's base prompt")
    return n


def check_cache(st: Studio, D: dict, copy: Path, first_secs: float) -> str:
    t0 = time.time()
    status, d = st.call("get_all")
    again = time.time() - t0
    check(status == 200 and d["ok"] and d["data"] == D, "[CACHE] a second call answered other data")
    check(again < min(10.0, first_secs / 4),
          f"[CACHE] a second call took {again:.1f} s (the build {first_secs:.1f} s): not kept")
    # Change a field that lands in a base prompt.
    target = next(s for s in D["slots"] if s["kind"] == "block" and s["origin"] == "dc"
                  and s["linked"] and any(not r["only_with_features"] for r in D["where"].get(s["slot"], [])))
    rel = D["files"][target["slot"]][""][0]
    path = copy.parent / rel
    # The default view, kept before the change (the views kept are the most
    # recent ones): after the change it must not be the one answered.
    st.call("view", {"topology": 7})
    marker = "Studio smoke marker 7341: this sentence was added by the check."
    raw = path.read_bytes()
    path.write_bytes(raw.rstrip() + ("\n\n" + marker + "\n").encode("utf-8"))
    t0 = time.time()
    status, d = st.call("get_all")
    rebuilt = time.time() - t0
    if not (status == 200 and d.get("ok")):
        check(False, f"[CACHE] the call after a change failed: {d}")
        return "failed"
    new = d["data"]
    slot = next(s for s in new["slots"] if s["slot"] == target["slot"])
    check(marker in slot["values"]["7"], f"[CACHE] {rel} changed, the Studio still shows the old text")
    check(any(marker in p for t in ("7", "5", "3") for p in new["prompts"][t]["prompts"].values()),
          f"[CACHE] {rel} changed, no prompt shows it")
    # Its place in the prompts moved with it: the field's span holds the
    # added sentence (a sentence card shortens a long text, so not there).
    check(any(nm == target["slot"] and marker in p[s:e]
              for t in ("7", "5", "3")
              for agent, p in new["prompts"][t]["prompts"].items()
              for s, e, nm, _ in new["prompts"][t]["spans"].get(agent, [])),
          f"[CACHE] {rel} changed, the field's place in the prompts does not hold it")
    status, v = st.call("view", {"topology": 7})
    check(status == 200 and v.get("ok")
          and any(marker in p for p in v["data"]["prompts"].values()),
          f"[VIEWER] {rel} changed, the default view still shows the old prompts")
    path.write_bytes(raw)                    # the setup as it was, for group 8
    return f"kept copy in {again:.2f} s; after a change to {rel}, rebuilt in {rebuilt:.0f} s"


def check_cache_unit() -> None:
    """PackView with a stand-in build: one build for callers that arrive
    together, a failure is not kept, __pycache__ is not a change."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "pack.yaml").write_text("name: x\n", encoding="utf-8")
        calls = []
        gate = threading.Event()

        def build(p):
            calls.append(p)
            gate.wait(5)
            if len(calls) == 2:
                raise RuntimeError("stand-in failure")
            return {"n": len(calls)}

        view = studio_server.PackView(d, build=build)
        out = []
        threads = [threading.Thread(target=lambda: out.append(view.get())) for _ in range(4)]
        for th in threads:
            th.start()
        time.sleep(0.3)
        gate.set()
        for th in threads:
            th.join(10)
        check(len(calls) == 1 and out == [{"n": 1}] * 4,
              f"[CACHE] callers arriving together: {len(calls)} builds, answers {out}")
        fp = studio_server.fingerprint(d)
        (d / "__pycache__").mkdir()
        (d / "__pycache__" / "x.pyc").write_bytes(b"x")
        check(studio_server.fingerprint(d) == fp and view.get() == {"n": 1},
              "[CACHE] a __pycache__ file counts as a change")
        (d / "pack.yaml").write_text("name: y\n", encoding="utf-8")
        check(studio_server.fingerprint(d) != fp, "[CACHE] a changed file keeps the fingerprint")
        try:
            view.get()
            check(False, "[CACHE] the stand-in failure was not raised")
        except RuntimeError:
            pass
        check(view.get() == {"n": 3} and len(calls) == 3,
              f"[CACHE] a failed build is kept instead of retried: {len(calls)} builds")


def _matrix_choices() -> dict:
    """``prompt_matrix.py``'s combinations as viewer choices, through the
    matrix's own translation tables: combination -> (the choice without
    topology and access, {topology: access cells}).  A setting the viewer
    does not offer stays in the choice, and the viewer refuses it."""
    sys.path.insert(0, str(ROOT / "extra_utilities" / "scripts"))
    import prompt_matrix as PM
    out = {}
    for combo, overrides in PM.CONFIGS.items():
        ov = dict(overrides)
        choice: dict = {"settings": {}, "tools": {}}
        rag, all_db = ov.pop("RAG_ENABLED", None), ov.pop("_ALL_DB_TOOLS", False)
        if all_db:
            choice["rag"] = "all"
        elif rag is not None:
            choice["rag"] = "on" if rag else "off"
        access: dict = {}
        for name, (on, off) in PM._ACCESS_FROM_SETTING.items():
            if name in ov:
                for agent, row in (on if ov.pop(name) else off).items():
                    for n, state in row.items():
                        access.setdefault(n, {})[agent] = state
        for name, (tool, key) in PM._TOOL_SETTING_FROM_SETTING.items():
            if name in ov:
                choice["tools"].setdefault(tool, {})[key] = ov.pop(name)
        choice["settings"] = ov
        out[combo] = (choice, access)
    return out


def _tool_sha(tool: dict) -> str:
    """As tool_matrix.py hashes a bound tool: name, description, arguments."""
    d = {"name": tool["name"], "description": tool["description"], "args": tool["args"]}
    return hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


def check_viewer(st: Studio) -> str:
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    prompts = json.loads((ROOT / "extra_utilities/prompt_matrix/baseline_manifest.json")
                         .read_text(encoding="utf-8"))
    tools = json.loads((ROOT / "extra_utilities/prompt_matrix/tool_baseline.json")
                       .read_text(encoding="utf-8"))
    combos = _matrix_choices()
    jobs = [(combo, n, dict(choice, topology=n, access=access.get(n, {})))
            for combo, (choice, access) in combos.items() for n in (7, 5, 3)]

    def one(job):
        combo, n, choice = job
        return combo, n, st.call("view", choice)

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(one, jobs))
    secs = time.time() - t0
    n_prompts = n_tools = 0
    for combo, n, (status, d) in results:
        where = f"{combo}/{n}"
        if not (status == 200 and d.get("ok")):
            check(False, f"[VIEWER] {where}: {str(d)[:300]}")
            continue
        v = d["data"]
        want = prompts[where]["prompts"]
        check(set(v["prompts"]) == set(want), f"[VIEWER] {where}: agents {sorted(v['prompts'])}")
        for agent, text in v["prompts"].items():
            n_prompts += 1
            check(hashlib.sha256(text.encode("utf-8")).hexdigest() == want.get(agent),
                  f"[VIEWER] {where} {agent}: not the prompt matrix's prompt")
            check(v["tokens"][agent] == len(enc.encode(text)),
                  f"[VIEWER] {where} {agent}: {v['tokens'][agent]} tokens, cl100k says "
                  f"{len(enc.encode(text))}")
        want_tools = {a: calls[-1]["tools"] for a, calls in tools[where].items()}
        got_tools = {a: [{"name": x["name"], "sha": _tool_sha(x)} for x in ts]
                     for a, ts in v["tools"].items()}
        check(got_tools == want_tools,
              f"[VIEWER] {where}: tools differ from the tool baseline for "
              f"{sorted(a for a in set(got_tools) | set(want_tools) if got_tools.get(a) != want_tools.get(a))}")
        for ts in v["tools"].values():
            for x in ts:
                n_tools += 1
                check(x["tokens"] == len(enc.encode(studio_server.tool_text(x))),
                      f"[VIEWER] {where} {x['name']}: tool tokens are not cl100k's")
    # A choice the setup does not offer.
    for bad, needle in (({"settings": {"NO_SUCH": True}}, "NO_SUCH"),
                        ({"rag": "maybe"}, "rag"),
                        ({"access": {"database_handler": "tool"}}, "database_handler"),
                        ({"tools": {"no_such_tool": {}}}, "no_such_tool")):
        status, d = st.call("view", dict(bad, topology=7))
        check(d.get("ok") is False and needle in d.get("error", ""),
              f"[VIEWER] the choice {bad} was not refused by name: {d}")
    return (f"{len(jobs)} views ({len(combos)} matrix combinations x 3 topologies) "
            f"in {secs:.0f} s: {n_prompts} prompts and {n_tools} tools as the baselines")


def check_choices(D: dict) -> None:
    from studio import engine_view as V
    base5 = V.canonical_choice({"topology": 5}, D)
    same = V.canonical_choice({"topology": 5, "settings": {"DC_INSPECTOR_ENABLED": False,
                                                           "CHAIN_ACCESS": False}}, D)
    check(same == base5, "[VIEWER] settings that do nothing in topology 5 make another choice")
    cell = next(r["cells"]["7"] for r in D["parameter_access"]["rows"]
                if r["agent"] == "user_input_inspector")
    check(V.canonical_choice({"topology": 7, "access": {"user_input_inspector": cell}}, D)
          == V.canonical_choice({"topology": 7}, D),
          "[VIEWER] an access cell equal to the setup's makes another choice")
    try:
        V.canonical_choice({"topology": 3, "access": {"user_input_inspector": "full"}}, D)
        check(False, "[VIEWER] an access cell for an agent the topology lacks was accepted")
    except V.ChoiceError:
        pass


def check_pool(D: dict, copy: Path) -> str:
    from studio import engine_view as V
    choice = V.canonical_choice({"topology": 3}, D)
    pool = studio_server.WorkerPool(copy, size=1)
    try:
        pool.fill()
        answers = []
        for _ in range(2):
            view, pooled = pool.run(choice)
            answers.append(pooled)
            deadline = time.time() + 30
            while pool.started < len(answers) + 1 and time.time() < deadline:
                time.sleep(0.1)
        check(answers == [True, True] and pool.started == 3,
              f"[VIEWER] the pool: jobs answered by waiting workers {answers}, "
              f"{pool.started} processes started (want 3: one per job + one waiting)")
        waiting = list(pool._idle)
        pool.close()
        time.sleep(0.5)
        check(waiting and all(p.poll() is not None for p in waiting),
              "[VIEWER] closing the pool left a waiting worker running")
        cold = studio_server.WorkerPool(copy, size=0)
        view_cold, pooled = cold.run(choice)
        check(pooled is False and view_cold["prompts"] == view["prompts"],
              "[VIEWER] a job with no worker waiting: not answered the same by a cold process")
    finally:
        pool.close()
    return "pool: one process per job, cold when none waits"


def check_generic() -> None:
    js = STUDIO_JS.read_text(encoding="utf-8").lower()
    for word in ("propeller", "blade", "impeller", "rhino", "feg", "airfoil"):
        check(word not in js, f"[GENERIC] studio/web/studio.js names {word!r}: the page must take it from the setup")
    src = (ROOT / "extra_utilities/docs/studio_draft/build_draft_data.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    defs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    moved = {"_bootstrap", "_pack_slots", "_strip", "_norm", "_child", "_run_children",
             "_parameters", "_topology_texts", "_slots", "_roles", "_parameter_access",
             "_settings_values", "_tools", "_tool_settings", "_where", "_env_names"}
    check("from studio import engine_view" in src and not (defs & moved),
          f"[GENERIC] the draft builder keeps its own copies: {sorted(defs & moved)}")


# ---------------------------------------------------------------------------
# editing (P6a)
# ---------------------------------------------------------------------------

def _snapshot(folder: Path) -> dict:
    """Every file of a setup folder: relative path -> bytes."""
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


def _same_files(copy: Path, ref: dict, what: str, tag: str = "[EDIT]") -> bool:
    now = _snapshot(copy)
    differ = sorted(set(now) ^ set(ref)) + sorted(k for k in set(now) & set(ref) if now[k] != ref[k])
    check(not differ, f"{tag} {what}: the setup is not byte for byte as it was: {differ[:6]}"
                      + (f" (+{len(differ) - 6} more)" if len(differ) > 6 else ""))
    return not differ


def _fields(D: dict) -> list:
    """Every editable field: (slot, agent or None, kind, strip, values, linked)."""
    out = []
    for s in D["slots"]:
        spec = D["slot_specs"][s["slot"]]
        if spec["missing"] != "empty":
            out.append((s["slot"], None, s["kind"], spec["strip"], s["values"], s["linked"]))
        for v in s["variants"]:
            out.append((s["slot"], v["agent"], s["kind"], spec["strip"], v["values"], v["linked"]))
    return out


def _topologies(D: dict, agent) -> list:
    if agent is None or agent == "database_handler":
        return ["7", "5", "3"]
    return [t for t in ("7", "5", "3") if agent in D["roles"]["roster"][t]]


def _call_ok(st: Studio, what: str, name: str, *args) -> dict:
    status, r = st.call(name, *args)
    check(status == 200 and r.get("ok") is True, f"[EDIT] {what}: {name} answered {status} {str(r)[:300]}")
    return r


def _js_checks(D: dict, texts: list) -> list | None:
    """The page's own checkText (studio/web/studio.js) run by Node on *texts*;
    None when Node is not installed."""
    node = shutil.which("node")
    if not node:
        return None
    js = STUDIO_JS.read_text(encoding="utf-8")
    start, end = js.index("  var NAME_RE"), js.index("  function problemsOf")
    stub = {k: D[k] for k in ("text_names", "text_flags", "pack_tools")}
    prog = ("var D = " + json.dumps(stub) + ";\n" + js[start:end]
            + "\nvar cases = " + json.dumps(texts) + ";\n"
            + "process.stdout.write(JSON.stringify(cases.map(function (c) { return checkText(c[0], c[1]); })));\n")
    p = subprocess.run([node], input=prog, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if p.returncode != 0:
        check(False, f"[EDIT] the page's checks do not run: {p.stderr[-300:]}")
        return []
    return json.loads(p.stdout)


def check_edit(st: Studio, copy: Path) -> str:
    """Every text field through the server: to a marker and back, unlinked
    and linked again, given an own copy and freed of it, Undo; the refusals;
    the comparison with the setup as the Studio opened it."""
    from studio import editing
    ref = _snapshot(copy)
    status, d = st.call("get_all")
    D0 = d["data"]
    check(D0.get("changed") == [], f"[EDIT] fresh setup: changed fields {D0.get('changed')}")
    status, r = st.call("diff", {"topology": 7}, "planner")
    check(r.get("ok") and r["data"]["changed_agents"] == []
          and all(op == "=" for op, _ in r["data"]["lines"]),
          f"[EDIT] nothing changed, yet the diff shows changes: {str(r)[:300]}")
    fields = _fields(D0)

    # 1. Every field to a marker of its own: saved, shown, in the prompts.
    marks = {}
    for i, (slot, agent, kind, strip, values, linked) in enumerate(fields):
        tag = f"QZX{i}"
        mark = (lambda t: t + ("\n\n" if kind == "block" else " ") + tag)
        if linked:
            vals, base = {"all": mark(values["7"])}, {"all": values["7"]}
        else:
            keys = [t for t in _topologies(D0, agent) if values[t] is not None]
            vals, base = {t: mark(values[t]) for t in keys}, {t: values[t] for t in keys}
        _call_ok(st, f"{slot}@{agent} to a marker", "save_field", slot, agent, vals, base)
        marks[(slot, agent)] = tag
    status, d = st.call("get_all")
    D1 = d["data"]
    names = sorted(slot + (f"@{agent}" if agent else "") for slot, agent, *_ in fields)
    check(D1["changed"] == names,
          f"[EDIT] changed fields after marking all {len(names)}: {len(D1['changed'])} listed")
    shown = {(f[0], f[1]): f[4] for f in _fields(D1)}
    for (slot, agent), tag in marks.items():
        vals = shown.get((slot, agent), {})
        check(all(v is None or v.endswith(tag) for v in vals.values()) and any(vals.values()),
              f"[EDIT] {slot}@{agent}: the Studio does not show the saved text")
    # Wherever a field's text was in a prompt, the marked text is now.
    slots = {f[0] for f in fields} | {s["slot"] for s in D0["slots"]}
    places = {(t, agent, nm) for t in ("7", "5", "3")
              for agent, spans in D0["prompts"][t]["spans"].items()
              for _s, _e, nm, _d in spans if nm in slots}
    landed = 0
    for t, agent, slot in sorted(places):
        text = D1["prompts"][t]["prompts"][agent]
        ok = any(nm == slot and "QZX" in text[s:e]
                 for s, e, nm, _ in D1["prompts"][t]["spans"].get(agent, []))
        check(ok, f"[EDIT] {slot}: marked, but {agent}'s prompt (topology {t}) does not show it there")
        landed += ok
    # The comparison with the setup as it was opened.
    want = sorted(a for a in D1["prompts"]["7"]["prompts"]
                  if D1["prompts"]["7"]["prompts"][a] != D0["prompts"]["7"]["prompts"][a])
    status, r = st.call("diff", {"topology": 7}, want[0] if want else "planner")
    got = r.get("data") or {}
    check(r.get("ok") and got.get("changed_agents") == want,
          f"[EDIT] diff: changed agents {got.get('changed_agents')} != {want}")
    check(any(op == "+" and "QZX" in ln for op, ln in got.get("lines", []))
          and any(op == "-" for op, ln in got.get("lines", [])),
          "[EDIT] diff: the marked lines are not shown as changed")
    # ...and back to the opened texts: byte for byte.
    for slot, agent, kind, strip, values, linked in fields:
        now = shown[(slot, agent)]
        if linked:
            vals, base = {"all": values["7"]}, {"all": now["7"]}
        else:
            keys = [t for t in _topologies(D0, agent) if values[t] is not None]
            vals, base = {t: values[t] for t in keys}, {t: now[t] for t in keys}
        _call_ok(st, f"{slot}@{agent} back", "save_field", slot, agent, vals, base)
    _same_files(copy, ref, f"{len(fields)} fields marked and put back")

    # 2. Unlink every linked field, give every shared text an own copy: no
    #    prompt changes.  Then link again, remove the copies: byte for byte.
    readers: dict = {}
    for slot, rows in D0["where"].items():
        for row in rows:
            readers.setdefault(slot, set()).update(row["agents"])
    all_agents = sorted({a for t in D0["roles"]["roster"].values() for a in t} | {"database_handler"})
    unlinked, copies = [], []
    for i, (slot, agent, kind, strip, values, linked) in enumerate(fields):
        has = {a for s, a, *_ in fields if s == slot and a}
        if agent is None:
            free = [a for a in sorted(readers.get(slot, ())) if a not in has] + \
                   [a for a in all_agents if a not in has]
            if i % 2 and linked and len(_topologies(D0, None)) > 1:
                _call_ok(st, f"{slot} unlink", "unlink_field", slot, None)
                unlinked.append((slot, None))
                linked = False
            if free:
                _call_ok(st, f"{slot} own copy for {free[0]}", "own_copy", slot, free[0])
                copies.append((slot, free[0]))
        if linked and len(_topologies(D0, agent)) > 1:
            _call_ok(st, f"{slot}@{agent} unlink", "unlink_field", slot, agent)
            unlinked.append((slot, agent))
    for s in D0["slots"]:                       # the per-agent-only fields: a new, empty copy
        if D0["slot_specs"][s["slot"]]["missing"] == "empty":
            has = {v["agent"] for v in s["variants"]}
            free = [a for a in all_agents if a not in has]
            if free:
                _call_ok(st, f"{s['slot']} own copy for {free[0]}", "own_copy", s["slot"], free[0])
                copies.append((s["slot"], free[0]))
    status, d = st.call("get_all")
    D2 = d["data"]
    for t in ("7", "5", "3"):
        for a, p in D0["prompts"][t]["prompts"].items():
            check(D2["prompts"][t]["prompts"].get(a) == p,
                  f"[EDIT] after {len(unlinked)} unlinks and {len(copies)} own copies, "
                  f"{a}'s prompt (topology {t}) changed")
    after = {(f[0], f[1]): f for f in _fields(D2)}
    for slot, agent in unlinked:
        f = after.get((slot, agent))
        check(f is not None and f[5] is False
              and all(f[4][t] is not None for t in _topologies(D0, agent)),
              f"[EDIT] {slot}@{agent}: after unlink, not one file per topology "
              f"({None if f is None else {t: f[4][t] is not None for t in f[4]}})")
    for slot, agent in copies:
        check((slot, agent) in after, f"[EDIT] {slot}: {agent}'s new own copy is not shown")
    for slot, agent in copies:
        _call_ok(st, f"{slot} remove {agent}'s copy", "remove_copy", slot, agent)
    for slot, agent in unlinked:
        keep = _topologies(D0, agent)[0]
        _call_ok(st, f"{slot}@{agent} link", "link_field", slot, agent, keep)
    _same_files(copy, ref, f"{len(unlinked)} fields unlinked and linked again, "
                           f"{len(copies)} own copies given and removed")

    # 3. Link every unlinked field (it keeps the 7-agent text, the others
    #    go), then Undo: byte for byte.
    relinked = 0
    for slot, agent, kind, strip, values, linked in fields:
        if linked or len(_topologies(D0, agent)) < 2:
            continue
        keep = next(t for t in _topologies(D0, agent) if values[t] is not None)
        _call_ok(st, f"{slot}@{agent} link", "link_field", slot, agent, keep)
        folder = copy / D0["slot_specs"][slot]["dir"]
        files = editing.field_files(folder, editing.field_name(slot, agent))
        check(set(files) == {"md"}, f"[EDIT] {slot}@{agent}: after link, files {sorted(files)}")
        _call_ok(st, f"{slot}@{agent} undo", "undo_field", slot, agent)
        relinked += 1
    _same_files(copy, ref, f"{relinked} unlinked fields linked, then Undo")

    # 4. What is refused, and changes nothing.
    word = next(f for f in fields if f[2] == "word" and f[5] and f[1] is None)
    phrase = next(f for f in fields if f[2] == "phrase" and f[5] and f[1] is None)
    block = next(f for f in fields if f[2] == "block" and f[5] and f[1] is None
                 and f[4]["7"])
    unl = next(f for f in fields if not f[5] and f[1] is None)
    overlay = next(s for s in D0["slots"] if D0["slot_specs"][s["slot"]]["missing"] == "empty")
    with_copy = next((s["slot"], v["agent"]) for s in D0["slots"] for v in s["variants"])
    missing_tool = "qzx_no_such_tool"
    refusals = [
        ("braces", (block[0], None, {"all": "a { b }"}, {"all": block[4]["7"]}), "{ or }"),
        ("a line break in a phrase", (phrase[0], None, {"all": "a\nb"}, {"all": phrase[4]["7"]}), "one-line"),
        ("an unknown $name", (block[0], None, {"all": "x $qzx_nope y"}, {"all": block[4]["7"]}), "$qzx_nope"),
        ("an unclosed marker", (block[0], None, {"all": "<<RAG_ON>>x"}, {"all": block[4]["7"]}), "not closed"),
        ("an unknown flag", (block[0], None, {"all": "<<IF:qzx>>x<</IF:qzx>>"}, {"all": block[4]["7"]}), "unknown flag"),
    ]
    for what, args, words in refusals:
        status, r = st.call("save_field", *args)
        check(r.get("ok") is False and any(words in p for p in r.get("problems", [])) and not r.get("conflict"),
              f"[EDIT] {what}: not refused with its reason: {str(r)[:300]}")
    conflicts = [
        ("a stale page", "save_field", (word[0], None, {"all": "x"}, {"all": word[4]["7"] + "?"})),
        ("linked text for an unlinked field", "save_field",
         (unl[0], None, {"all": "x"}, {"all": unl[4]["7"]})),
        ("an own copy that exists", "own_copy", with_copy),
        ("removing a copy that does not exist", "remove_copy", (word[0], "receptionist")
         if (word[0], "receptionist") not in {(f[0], f[1]) for f in fields} else (word[0], "tool_caller")),
        ("linking a linked field", "link_field", (word[0], None, "7")),
        ("unlinking an unlinked field", "unlink_field", (unl[0], None)),
    ]
    for what, name, args in conflicts:
        status, r = st.call(name, *args)
        check(r.get("ok") is False and r.get("conflict") is True,
              f"[EDIT] {what}: not refused as a conflict: {str(r)[:300]}")
    for what, name, args in [
            ("a shared text for a per-agent-only field", "save_field",
             (overlay["slot"], None, {"all": "x"}, {"all": None})),
            ("an unknown field", "save_field", ("qzx_nope", None, {"all": "x"}, {"all": None})),
            ("an unknown agent", "own_copy", (word[0], "qzx_agent")),
            ("no agent", "own_copy", (word[0], None))]:
        status, r = st.call(name, *args)
        check(r.get("ok") is False and r.get("error"), f"[EDIT] {what}: not refused: {str(r)[:300]}")
    _same_files(copy, ref, "after the refused changes")
    # A flag of a tool the setup lacks reads as off (the engine's rule): allowed.
    r = _call_ok(st, "a flag of a missing tool", "save_field", block[0], None,
                 {"all": f"<<IF:tool:{missing_tool}>>x<</IF:tool:{missing_tool}>>"}, {"all": block[4]["7"]})
    # An empty text is saved, with a warning; Undo puts the field back.
    r = _call_ok(st, "an empty text", "save_field", block[0], None, {"all": ""},
                 {"all": f"<<IF:tool:{missing_tool}>>x<</IF:tool:{missing_tool}>>"})
    check(any("empty" in w for w in r.get("warnings", [])), f"[EDIT] an empty text: no warning {r}")
    _call_ok(st, "undo", "undo_field", block[0], None)
    _same_files(copy, ref, "after an edit and Undo")
    # Line endings: a CRLF file stays CRLF, an LF file LF, the final newline kept.
    for want in (b"\r\n", b"\n"):
        f = next((f for f in fields if f[5] and f[2] == "block" and f[4]["7"]
                  and editing._eol(ref.get(f"{D0['slot_specs'][f[0]]['dir']}/"
                                           f"{editing.field_name(f[0], f[1])}.md", b"")) == want), None)
        if f is None:
            continue
        rel = f"{D0['slot_specs'][f[0]]['dir']}/{editing.field_name(f[0], f[1])}.md"
        _call_ok(st, f"{rel} line endings", "save_field", f[0], f[1],
                 {"all": f[4]["7"] + "\nQZX end"}, {"all": f[4]["7"]})
        raw = (copy / rel).read_bytes()
        other = b"\n" if want == b"\r\n" else b"\r\n"
        check(raw.endswith(b"QZX end" + want) and (want == b"\n" and b"\r" not in raw
                                                   or want == b"\r\n" and raw.count(b"\n") == raw.count(b"\r\n")),
              f"[EDIT] {rel}: line endings not kept ({want!r}, not {other!r})")
        _call_ok(st, "undo", "undo_field", f[0], f[1])
    _same_files(copy, ref, "after the line-ending edits and Undo")

    # 5. The page checks a text as the server does (Node runs the page's own code).
    cases = [("block", "a { b"), ("phrase", "a\nb"), ("block", "x $qzx_nope $dc_name"),
             ("block", "<<RAG_ON>>x"), ("block", "<<IF:qzx>>x<</IF:qzx>>"),
             ("block", f"<<IF:tool:{missing_tool}>>x<</IF:tool:{missing_tool}>>"),
             ("word", "fine"), ("block", "}<<A>>\n$qzx_b $qzx_a <<IF:zz>>")]
    js = _js_checks(D0, cases)
    if js is not None:
        names_, flags_, tools_ = set(D0["text_names"]), set(D0["text_flags"]), set(D0["pack_tools"])
        for (kind, text), got_js in zip(cases, js):
            want_py = editing.check_text(kind, text, names_, flags_, tools_)
            check(got_js == want_py, f"[EDIT] the page checks {text!r} otherwise than the server: "
                                     f"{got_js} != {want_py}")
    return (f"{len(fields)} fields marked ({landed} landing places) and put back; {len(unlinked)} "
            f"unlinked and linked again; {len(copies)} own copies given and removed; {relinked} linked "
            f"then undone; byte for byte" + ("" if js is not None else "; Node not found: page checks not run"))


# ---------------------------------------------------------------------------
# the parameter editor and the access grid (P6b)
# ---------------------------------------------------------------------------

def _lists_agree(copy: Path, rels: list, spec: dict, what: str) -> bool:
    """Every parameter list names the file's parameters, in order, with its
    ranges, numbered 1..n -- read by the drift check's own parser."""
    from smoke_test_parameters import parse_parameter_list
    want = [(p["name"], (float(p["min"]), float(p["max"]))) for p in spec["parameters"]]
    ok = True
    for rel in rels:
        got = parse_parameter_list((copy / rel).read_bytes().decode("utf-8"))
        good = ([n for n, _, _ in got] == list(range(1, len(got) + 1))
                and [(nm, r) for _, nm, r in got] == want)
        check(good, f"[PARAMS] {what}: {rel} is not in step with parameters.json "
                    f"({[(nm, r) for _, nm, r in got][:3]}... vs {want[:3]}...)")
        ok = ok and good
    return ok


def _save(st: Studio, what: str, spec: dict, sha: str, renames: dict | None = None) -> str:
    """save_parameters; the new file's fingerprint (the old one if refused)."""
    status, r = st.call("save_parameters", spec, sha, renames or {})
    check(r.get("ok") is True, f"[PARAMS] {what}: save refused: {str(r)[:300]}")
    return r.get("sha", sha)


def _js_validate(specs: list) -> list | None:
    """The page's own validateSpec (studio/web/studio.js) run by Node."""
    node = shutil.which("node")
    if not node:
        return None
    js = STUDIO_JS.read_text(encoding="utf-8")
    start, end = js.index("  // -- engine/parameters.py validate"), js.index("  // -- end validate")
    head = "var P_KEYS = " + json.dumps(["name", "type", "min", "max", "step", "default", "group",
                                         "label", "unit", "db_unit", "db_description"]) + \
           ";\nvar G_KEYS = " + json.dumps(["id", "label", "image", "image_alt", "order"]) + ";\n"
    prog = (head + js[start:end] + "\nvar cases = " + json.dumps(specs) + ";\n"
            "process.stdout.write(JSON.stringify(cases.map(validateSpec)));\n")
    p = subprocess.run([node], input=prog, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if p.returncode != 0:
        check(False, f"[PARAMS] the page's parameter check does not run: {p.stderr[-300:]}")
        return []
    return json.loads(p.stdout)


def check_params(st: Studio, copy: Path) -> str:
    """Every parameter changed through the server -- its range, its name,
    gone, moved, a new one in each group -- with the agents' lists in step
    and each change undone byte for byte; groups and a picture; imports
    and CSV; the refusals; every access cell; the page's own check."""
    import copy as copymod
    from engine import parameters as eparams
    from studio import params_edit as PE
    ref = _snapshot(copy)

    def _same(what):
        return _same_files(copy, ref, what, "[PARAMS]")
    status, d = st.call("get_all")
    D0 = d["data"]
    P0 = D0["params_edit"]
    spec, sha0, lists = P0["spec"], P0["sha"], P0["lists"]
    check(D0["changed"] == [], f"[PARAMS] fresh setup: changed {D0['changed']}")
    raw = (copy / "parameters.json").read_bytes()
    check(PE.format_spec(json.loads(raw), PE.eol_of(raw)) == raw,
          "[PARAMS] the writer does not reproduce parameters.json byte for byte")
    check(len(lists) >= 1 and all((copy / r).is_file() for r in lists),
          f"[PARAMS] the parameter lists: {lists}")
    names = [p["name"] for p in spec["parameters"]]
    sha = sha0
    cases = 0

    def back(what):
        nonlocal sha
        sha = _save(st, f"{what}, back", spec, sha)
        _same(f"{what}, then back")

    # 1. Each parameter: its range, its name, gone -- and back.
    for i, name in enumerate(names):
        s = copymod.deepcopy(spec)
        p = s["parameters"][i]
        p["max"] = p["max"] + p["step"] * 2
        sha = _save(st, f"{name} range", s, sha)
        _lists_agree(copy, lists, s, f"{name} range")
        back(f"{name} range")
        s = copymod.deepcopy(spec)
        new = name + "Qx"
        s["parameters"][i]["name"] = new
        for g in s["groups"]:
            g["order"] = [new if n == name else n for n in g["order"]]
        sha = _save(st, f"{name} renamed", s, sha, {name: new})
        saved = json.loads((copy / "parameters.json").read_bytes())
        check(name in saved.get("retired", []), f"[PARAMS] {name} renamed: the old name is not retired")
        _lists_agree(copy, lists, s, f"{name} renamed")
        sha = _save(st, f"{name} renamed, back", spec, sha, {new: name})
        _same(f"{name} renamed, then back")
        s = copymod.deepcopy(spec)
        del s["parameters"][i]
        for g in s["groups"]:
            g["order"] = [n for n in g["order"] if n != name]
        sha = _save(st, f"{name} removed", s, sha)
        _lists_agree(copy, lists, s, f"{name} removed")
        back(f"{name} removed")
        # moved within its group (the order the lists follow)
        j = next((k for k in range(i + 1, len(names)) if spec["parameters"][k]["group"] == spec["parameters"][i]["group"]), None)
        if j is not None:
            s = copymod.deepcopy(spec)
            s["parameters"][i], s["parameters"][j] = s["parameters"][j], s["parameters"][i]
            sha = _save(st, f"{name} moved", s, sha)
            _lists_agree(copy, lists, s, f"{name} moved")
            back(f"{name} moved")
        cases += 1
    # An imported order that moves a parameter across another group's
    # parameters (and so across the lists' headings), then back.
    for gi in range(len(spec["groups"]) - 1):
        a = max(k for k, p in enumerate(spec["parameters"]) if p["group"] == spec["groups"][gi]["id"])
        b = min(k for k, p in enumerate(spec["parameters"]) if p["group"] == spec["groups"][gi + 1]["id"])
        s = copymod.deepcopy(spec)
        s["parameters"][a], s["parameters"][b] = s["parameters"][b], s["parameters"][a]
        sha = _save(st, f"order across {spec['groups'][gi]['id']}/{spec['groups'][gi + 1]['id']}", s, sha)
        _lists_agree(copy, lists, s, f"order across groups {gi}")
        back(f"order across groups {gi}")
    # 2. A new parameter at the end of each group, in each list's own shape.
    for g in spec["groups"]:
        s = copymod.deepcopy(spec)
        last = max(k for k, p in enumerate(s["parameters"]) if p["group"] == g["id"])
        s["parameters"].insert(last + 1, {"name": "qzxNew", "type": "int", "min": 1, "max": 4, "step": 1,
                                          "default": 2, "group": g["id"], "label": "Qzx", "unit": "",
                                          "db_unit": "", "db_description": "A test parameter"})
        next(x for x in s["groups"] if x["id"] == g["id"])["order"].append("qzxNew")
        sha = _save(st, f"new parameter in {g['id']}", s, sha)
        _lists_agree(copy, lists, s, f"new parameter in {g['id']}")
        for rel in lists:
            line = next((ln for ln in (copy / rel).read_bytes().decode("utf-8").splitlines() if "qzxNew" in ln), "")
            # in the list's own shape: with a "— description" where its entries carry one
            described = any("— " in ln for ln in ref[rel].decode("utf-8").splitlines()
                            if re.match(r"^\s*\d+\.", ln))
            want = "(integer)" in line and (line.rstrip().endswith("— A test parameter [1; 4]") if described
                                            else line.rstrip().endswith("[1; 4]") and "—" not in line)
            check(want, f"[PARAMS] new parameter in {g['id']}: {rel} entry {line!r}")
        back(f"new parameter in {g['id']}")
    # 3. The prompts: every range changed at once, then the diff and the prompts show it.
    s = copymod.deepcopy(spec)
    for p in s["parameters"]:
        p["max"] = p["max"] + p["step"]
    sha = _save(st, "every range", s, sha)
    status, d = st.call("get_all")
    D1 = d["data"]
    shown = 0
    for t in ("7", "5", "3"):
        for agent, text in D0["prompts"][t]["prompts"].items():
            for p, q in zip(spec["parameters"], s["parameters"]):
                old = f"[{PE.num(p['min'])}; {PE.num(p['max'])}]"
                if re.search(rf"\b{p['name']}\b[^\n]*{re.escape(old)}", text):
                    new = f"[{PE.num(q['min'])}; {PE.num(q['max'])}]"
                    ok = re.search(rf"\b{q['name']}\b[^\n]*{re.escape(new)}", D1["prompts"][t]["prompts"][agent])
                    check(bool(ok), f"[PARAMS] every range: {agent}'s prompt (topology {t}) does not show {q['name']} {new}")
                    shown += 1
    check(shown > 0, "[PARAMS] every range: no prompt showed a parameter range")
    status, r = st.call("diff", {"topology": 7}, "dc_input_creator")
    check(r.get("ok") and "dc_input_creator" in r["data"]["changed_agents"]
          and any(op == "+" and "]" in ln for op, ln in r["data"]["lines"]),
          f"[PARAMS] every range: the diff does not show the Parameter author's changed list: {str(r)[:200]}")
    # A text field's Undo of a list keeps it in step with the parameters now.
    lst = D0["slot_specs"][PE.LIST_SLOT]
    shared = f"{lst['dir']}/{PE.LIST_SLOT}.md"
    if shared in lists:
        _call_ok(st, "list undo", "undo_field", PE.LIST_SLOT, None)
        _lists_agree(copy, [shared], s, "a list's Undo after a range change")
    back("every range")
    # 4. Groups and a picture; Undo all.
    s = copymod.deepcopy(spec)
    png = next((copy / "assets").glob("*.png")).read_bytes()
    status, r = st.call("upload_picture", "Qzx Group.png", base64.b64encode(png).decode())
    check(r.get("ok") and r.get("path") == "/pack/assets/qzx-group.png", f"[PARAMS] upload: {str(r)[:200]}")
    for fname, bad, why in (("Qzx Bad1.png", b"not a png", "Only PNG"),
                            ("Qzx Bad2.png", b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024), "limit is 2 MB"),
                            ("Qzx Group.png", png, "already exists")):
        status, r = st.call("upload_picture", fname, base64.b64encode(bad).decode())
        check(r.get("ok") is False and why in r.get("error", ""), f"[PARAMS] upload refused ({why}): {str(r)[:200]}")
    moved = s["parameters"][-1]["name"]
    for g in s["groups"]:
        g["order"] = [n for n in g["order"] if n != moved]
    s["groups"].append({"id": "qzx", "label": "Qzx", "image": "/pack/assets/qzx-group.png",
                        "image_alt": "Qzx", "order": [moved]})
    s["parameters"][-1]["group"] = "qzx"
    s["groups"][0]["label"] += " Q"
    s["groups"][0], s["groups"][1] = s["groups"][1], s["groups"][0]
    sha = _save(st, "groups", s, sha)
    _lists_agree(copy, lists, s, "groups")
    r = _call_ok(st, "undo all", "undo_parameters")
    sha = r.get("sha", sha)
    _same("groups and a picture, then Undo all")
    # 5. Imports: the same file, a changed one; a CSV.
    status, r = st.call("preview_parameters", spec, sha, {})
    check(r.get("ok") and r.get("same") is True and not r.get("lists"),
          f"[PARAMS] importing the same file: not \"no change\": {str(r)[:200]}")
    s = copymod.deepcopy(spec)
    s["parameters"][0]["max"] += s["parameters"][0]["step"]
    gone = s["parameters"].pop(3)["name"]
    for g in s["groups"]:
        g["order"] = [n for n in g["order"] if n != gone]
    status, r = st.call("preview_parameters", s, sha, {})
    c = r.get("changes") or {}
    code_ok = (gone in r.get("code_uses", {})) == bool(PE.code_uses(copy, [gone])[gone])
    check(bool(r.get("ok")) and c.get("removed") == [gone] and names[0] in c.get("fields", {})
          and len(r.get("lists", [])) == len(lists) and r.get("database") is True and code_ok,
          f"[PARAMS] import preview: {str(r)[:300]}")
    _same("after previews (nothing written)")
    sha = _save(st, "import", s, sha)
    _lists_agree(copy, lists, s, "import")
    sha = _call_ok(st, "undo all", "undo_parameters").get("sha", sha)
    _same("import, then Undo all")
    p1 = spec["parameters"][1]
    csv_text = f"name,max,label\n{p1['name']},{PE.num(p1['max'] + p1['step'])},Qzx label\n"
    status, r = st.call("csv_parameters", csv_text)
    s = r.get("spec") or {}
    check(r.get("ok") and r.get("problems") == [] and s.get("parameters", [{}, {}])[1].get("label") == "Qzx label",
          f"[PARAMS] CSV: {str(r)[:200]}")
    if s:
        sha = _save(st, "CSV", s, sha)
        _lists_agree(copy, lists, s, "CSV")
        back("CSV")
    for text, words in (("name,qzx\na,1\n", "Unknown column"), ("min,max\n1,2\n", "no \"name\""),
                        (f"name,max\n{p1['name']},abc\n", "not a number"), ("name,min,max\nqzxNew,1,2\n", "needs a group"),
                        ("name,min,max,group\nqzxNew,1,2,nogroup\n", "does not exist")):
        status, r = st.call("csv_parameters", text)
        check(any(words in p for p in r.get("problems", [])), f"[PARAMS] CSV {text!r}: not refused ({words}): {r.get('problems')}")
    # 6. Refusals: the engine's own messages; nothing written.
    opened = json.loads(raw)
    bad_specs = []

    def bad(edit):
        s = copymod.deepcopy(spec)
        edit(s)
        bad_specs.append(s)
    bad(lambda s: s["parameters"][0].update(min=s["parameters"][0]["max"] + 1))
    bad(lambda s: s["parameters"][1].update(default=10 ** 6))
    bad(lambda s: s["parameters"][0].update(step=0.5, type="int"))
    bad(lambda s: s["parameters"][2].update(name="2bad"))
    bad(lambda s: s["parameters"][3].update(name=s["parameters"][4]["name"]))
    bad(lambda s: s["parameters"][5].pop("unit"))
    bad(lambda s: s["parameters"][6].update(colour="red"))
    bad(lambda s: s["parameters"][7].update(group="qzx_missing"))
    bad(lambda s: s["groups"][0]["order"].append("qzx_nobody"))
    bad(lambda s: s["groups"][1]["order"].append(s["groups"][0]["order"][0]))
    bad(lambda s: s["parameters"][8].update(min="a"))
    bad(lambda s: s["groups"][0].pop("image_alt"))
    bad(lambda s: s["parameters"][0].update(step=0))
    bad(lambda s: s["parameters"][1].update(type="double"))
    bad(lambda s: s["parameters"][2].update(label=7))
    bad(lambda s: s.update(retired=["qzxOld", "qzxOld", "9bad"]))
    bad(lambda s: s.update(retired="qzxOld"))
    bad(lambda s: s["groups"].append(dict(s["groups"][0], order=[])))
    bad(lambda s: s["groups"].append("qzx"))
    bad(lambda s: s["parameters"].append("qzx"))
    for s in bad_specs:
        status, r = st.call("save_parameters", s, sha, {})
        want = eparams.validate(PE.retire(spec, PE.normalise(s), opened))
        check(r.get("ok") is False and r.get("problems") == want and want,
              f"[PARAMS] a bad file: refused with {r.get('problems')}, the engine says {want}")
    status, r = st.call("save_parameters", spec, "0" * 64, {})
    check(r.get("ok") is False and r.get("conflict") is True, f"[PARAMS] a stale page: not a conflict: {str(r)[:200]}")
    status, r = st.call("save_parameters", spec, sha, {"qzxA": "qzxB"})
    check(r.get("ok") is False and any("renaming" in p for p in r.get("problems", [])),
          f"[PARAMS] a rename that does not match: not refused: {str(r)[:200]}")
    _same("after the refused saves")
    # The page checks a file exactly as the engine does (Node runs the page's own code).
    js = _js_validate([spec] + bad_specs + [{"groups": [], "parameters": []}, [], {"groups": [], "parameters": [{}], "x": 1}])
    if js is not None:
        for s, got in zip([spec] + bad_specs + [{"groups": [], "parameters": []}, [], {"groups": [], "parameters": [{}], "x": 1}], js):
            want = eparams.validate(s)
            check(got == want, f"[PARAMS] the page checks a file otherwise than the engine: {got} != {want}")
    # 7. Every access cell through every state, and back; the refusals.
    yref = (copy / "pack.yaml").read_bytes()
    ysha = P0["pack_yaml_sha"]
    pa = D0["parameter_access"]
    states = [x["id"] for x in pa["states"]]
    cells = 0
    for row in pa["rows"]:
        for t, orig in row["cells"].items():
            for state in states:
                if state == orig:
                    continue
                status, r = st.call("set_access", row["agent"], t, state, ysha)
                if state == "tool" and row["agent"] in pa["no_tool"]:
                    check(r.get("ok") is False, f"[PARAMS] {row['agent']} took \"tool\"")
                    continue
                check(r.get("ok") is True, f"[PARAMS] access {row['agent']} {t} {state}: {str(r)[:200]}")
                ysha = r.get("pack_yaml_sha", ysha)
                now = PE.access_rows((copy / "pack.yaml").read_bytes().decode("utf-8").replace("\r\n", "\n"))
                check(now[row["agent"]][1][t] == state, f"[PARAMS] access {row['agent']} {t}: not {state} in pack.yaml")
                status, r = st.call("set_access", row["agent"], t, orig, ysha)
                ysha = r.get("pack_yaml_sha", ysha)
                check((copy / "pack.yaml").read_bytes() == yref,
                      f"[PARAMS] access {row['agent']} {t} {state} and back: pack.yaml not byte for byte")
                cells += 1
    for args, words in ((("qzx_agent", "7", "full"), "has no cell"), (("planner", "9", "full"), "has no cell"),
                        (("planner", "7", "qzx"), "is not a state")):
        status, r = st.call("set_access", *args, ysha)
        check(r.get("ok") is False and words in r.get("error", ""), f"[PARAMS] access {args}: {str(r)[:200]}")
    status, r = st.call("set_access", "planner", "7", "full", "0" * 64)
    check(r.get("ok") is False and r.get("conflict") is True, "[PARAMS] access with a stale page: not a conflict")
    hub = next(r for r in pa["rows"] if r["agent"] == "planner")
    other = next(x for x in states if x != hub["cells"]["7"] and x != "tool")
    status, r = st.call("set_access", "planner", "7", other, ysha)
    _call_ok(st, "undo access", "undo_access", "planner")
    check((copy / "pack.yaml").read_bytes() == yref, "[PARAMS] undo_access: pack.yaml not byte for byte")
    _same("after the parameter editor")
    return (f"{cases} parameters each changed / renamed / removed / moved and back, a new one in each of "
            f"{len(spec['groups'])} groups, {len(lists)} lists kept in step, {shown} ranges seen in the "
            f"prompts, groups + a picture, imports, CSV, {len(bad_specs)} bad files refused, {cells} access "
            f"changes; byte for byte" + ("" if js is not None else "; Node not found: page check not run"))


# ---------------------------------------------------------------------------

def main() -> int:
    _run(check_cache_unit, "[CACHE]")
    _run(check_generic, "[GENERIC]")
    tmp = Path(tempfile.mkdtemp(prefix="studio_smoke_"))
    copy = tmp / "dc_pack"
    shutil.copytree(config.DC_PACK_DIR, copy, ignore=shutil.ignore_patterns("__pycache__"))
    st = None
    summary = {}
    try:
        st = Studio(copy)
        t0 = time.time()
        status, d = st.call("get_all")
        first = time.time() - t0
        if not (status == 200 and d.get("ok")):
            check(False, f"[SERVER] get_all: {status} {str(d)[:600]}")
        else:
            D = d["data"]
            _run(lambda: check_server(st, D), "[SERVER]")
            summary["fields"] = _run(lambda: check_fields(D, copy), "[FIELDS]")
            summary["where"] = _run(lambda: check_where(D), "[WHERE]")
            summary["prompts"] = _run(lambda: check_prompts(D), "[PROMPTS]")
            summary["viewer"] = _run(lambda: check_viewer(st), "[VIEWER]")
            _run(lambda: check_choices(D), "[VIEWER]")
            summary["pool"] = _run(lambda: check_pool(D, copy), "[VIEWER]")
            summary["cache"] = _run(lambda: check_cache(st, D, copy, first), "[CACHE]")
            summary["edit"] = _run(lambda: check_edit(st, copy), "[EDIT]")
            summary["params"] = _run(lambda: check_params(st, copy), "[PARAMS]")
            summary["first"] = f"{first:.0f} s"
    finally:
        if st is not None:
            st.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"first assembly {summary.get('first')}; {summary.get('fields')} fields shown as the "
          f"engine reads them; {summary.get('where')} field texts (per topology) found in a "
          f"prompt, each with its sentences there; {summary.get('prompts')} prompts = the prompt matrix's base; "
          f"{summary.get('cache')}; {summary.get('viewer')}; {summary.get('pool')}; "
          f"editing: {summary.get('edit')}; parameters: {summary.get('params')}")
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - the Studio shows every field of the setup, where each one lands, and "
          "the engine's own prompts and tools under every choice of settings, sees "
          "a changed file, edits every text field, parameter and access cell, and puts "
          "each back byte for byte.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
