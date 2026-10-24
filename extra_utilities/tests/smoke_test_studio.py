"""The Studio (MAS-blueprint P5a-P6c): the real server on a copy of the pack.

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
   instead of copies of them.  Every text field the Studio shows has a plain
   title in the slot registry, and no title names a configurator either; its
   groups are whole (each grouped field's group is listed for its section,
   each listed group has a field).  The page's own line functions -- the
   lines that differ per team size, "Differences only", the light
   formatting, a tool's test status, the error in a few words -- give the
   expected answers (run by Node).

Since MAS-blueprint P5b the prompt viewer shows any choice of the settings
that change what an agent sees (``POST /api/view``):

7b. WRITTEN.  Asked "as written", the viewer keeps every settings-specific
   region of every agent's prompt in the teams of 7, 5 and 3, between a label
   in plain words and its end (agents/shared/prompts.py AS_WRITTEN; every
   database tool on, so the database texts are in): every
   kind of region is labelled, none is left as a raw marker; a view not asked
   so shows no label, and a non-boolean ask is refused.

7. VIEWER.  Every combination of ``prompt_matrix.py`` the viewer can
   express, in topologies 3 / 5 / 7: the prompts
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

Since MAS-blueprint P6c it edits the tools (``studio/tools_edit.py``,
``studio/yaml_patch.py``):

10. TOOLS.  Every value the manifest form edits, of every tool (display
   name, description, argument texts, roles, the switch, each setting's
   default / label / description, each picture's label / order / on, the
   list order) and a declared secret, is saved -- the file reads back as
   the form's manifest -- and put back byte for byte.  Bad manifests are
   refused with the engine's own reasons, a stale page as a conflict.  The
   manifest as text, every text file of every tool, every binary file
   (replaced), a file added: each back byte for byte; a Python syntax
   error saves with a warning; uploads outside the folder, into prompts/
   or over a file without its sha are refused; a tool-list entry with
   braces is refused.  A tool still named by another tool's setting or by
   the Download buttons cannot be removed; removing the only generator
   warns; one tool is removed (the prompts change) and its Undo brings it
   back byte for byte, as a tool changed in several places is.
11. NEWTOOL.  A tool from each template (helper, generator, geometry) is
   made only once the engine takes it, runs cleanly in Test tool on the
   defaults and on a sample (its answer, picture, model), and the setup
   assembles with it -- the tool runner lists the new helper and generator;
   a copy of each tool gets pictures and a model file of its own, no texts
   of the original, a helper's function renamed after it, and Test tool
   reports what the copied code still does under the original's names;
   Undo takes every new tool away byte for byte.  Bad names, an existing or
   reserved name, a removed tool's name, no display name, no template, an
   unknown source are refused.  Test tool reports a failing tool instead of
   failing, keeps the tool's own output lines, and stops a run at its time
   limit; nothing in the setup changes.

Takes about nine minutes.  Run from the repo root:
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
    check(status == 200 and 'src="static/studio.js"' in page and 'src="static/bridge.js"' in page,
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
        # the $slots of the prompts and the fields the app's code reads (P8)
        registry = {**pack.slots(source="pack", use="prompt"), **pack.slots(source="pack", use="runtime")}
        shown = {s["slot"]: s for s in D["slots"]}
        check({n for n, s in shown.items() if s.get("runtime")} == set(pack.slots(source="pack", use="runtime")),
              f"[FIELDS] the fields marked as read by the app: {sorted(n for n, s in shown.items() if s.get('runtime'))}")
        check(set(shown) == set(registry),
              f"[FIELDS] fields shown != the registry's: missing {sorted(set(registry) - set(shown))}, "
              f"extra {sorted(set(shown) - set(registry))}")
        sections = set(re.findall(r"\{ id: '(\w+)', stage: \d+", STUDIO_JS.read_text(encoding="utf-8")))
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
        if s.get("runtime"):
            # placed by the app's code, not by a $name: the page says its
            # sentences are not traced (P8), so it has none here
            check(not D["where"].get(s["slot"]), f"[WHERE] {s['slot']} is read by the app but has landing sentences")
            continue
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


# What the as-written view says for each kind of region (agents/shared/prompts.py).
WRITTEN_LABELS = ("only when the DC Input Inspector is on", "only when the DC Input Inspector is off",
                  "only when RAG is on", "only for an agent with a database tool",
                  "only for an agent that can fetch saved user inputs", "only for an agent that can look at pictures",
                  "only for an agent that cannot look at pictures", "only for an agent in the forward chain (not the hub)",
                  "only when the agent gets the parameter list")


def check_as_written(st: Studio) -> str:
    seen, regions = set(), 0
    raw = re.compile(r"<</?(?:DCII_ONLY|DCII_OFF|HAS_DBA|HAS_USER_INPUTS|CAN_SEE|CANNOT_SEE|RAG_ON|CHAIN_ONLY|IF|IFNOT)\b")
    for n in (7, 5, 3):
        # every database tool on, so the database texts (and their regions) are in
        status, d = st.call("view", {"topology": n, "rag": "all", "as_written": True})
        check(status == 200 and d.get("ok"), f"[WRITTEN] team of {n}: {str(d)[:300]}")
        if not d.get("ok"):
            continue
        for agent, text in d["data"]["prompts"].items():
            left = raw.findall(text)
            check(not left, f"[WRITTEN] team of {n}, {agent}: regions left as raw markers: {left[:3]}")
            labels = [x.replace("\u00a0", " ") for x in re.findall(r"⟦([^⟧]*)⟧", text)]
            check(labels.count("end") * 2 == len(labels), f"[WRITTEN] team of {n}, {agent}: labels and ends do not pair")
            seen.update(labels)
            regions += labels.count("end")
    missing = [x for x in WRITTEN_LABELS if x not in seen]
    check(not missing, f"[WRITTEN] kinds never labelled: {missing}")
    check(any(x.startswith("only when the ") and x.endswith(" tool is on") for x in seen),
          f"[WRITTEN] no tool's region labelled: {sorted(seen)[:8]}")
    status, d = st.call("view", {"topology": 7})
    check(d.get("ok") and not any("⟦" in x for x in d["data"]["prompts"].values()),
          "[WRITTEN] a view not asked as written shows labels")
    status, d = st.call("view", {"topology": 7, "as_written": "yes"})
    check(d.get("ok") is False, "[WRITTEN] as_written 'yes' was accepted")
    return f"{regions} regions labelled over the teams of 7, 5 and 3"


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
    shown = {k: v for k, v in pack.registry().items() if v.get("source") == "pack" and v.get("section")}
    untitled = sorted(k for k, v in shown.items() if not str(v.get("title") or "").strip())
    check(not untitled, f"[GENERIC] Studio text fields without a plain title (engine/slot_registry.yaml): {untitled}")
    named = sorted(k for k, v in shown.items()
                   if any(w in str(v.get("title") or "").lower() for w in ("propeller", "blade", "impeller", "hose", "airfoil")))
    check(not named, f"[GENERIC] titles that name a configurator: {named}")
    import yaml
    groups = yaml.safe_load(pack.REGISTRY_PATH.read_text(encoding="utf-8")).get("groups") or {}
    stray = sorted(k for k, v in shown.items() if v.get("group") and v["group"] not in groups.get(v["section"], []))
    check(not stray, f"[GENERIC] fields whose group is not listed for their section: {stray}")
    empty = sorted(f"{sec}: {g}" for sec, gs in groups.items() for g in gs
                   if not any(v.get("section") == sec and v.get("group") == g for v in shown.values()))
    check(not empty, f"[GENERIC] groups without a field: {empty}")


def _js_piece(js: str, name: str) -> str:
    """The function or ``var`` statement *name* of studio.js, whole (its
    brackets counted)."""
    if f"\n  var {name} = " in js:
        i, depth = js.index(f"\n  var {name} = ") + 1, 0
        for k in range(i, len(js)):
            depth += 1 if js[k] in "{[(" else -1 if js[k] in "}])" else 0
            if js[k] == ";" and depth == 0:
                return js[i:k + 1]
        raise ValueError(name)
    i = js.index(f"\n  function {name}(") + 1
    depth = 0
    for k in range(js.index("{", i), len(js)):
        depth += {"{": 1, "}": -1}.get(js[k], 0)
        if depth == 0:
            return js[i:k + 1]
    raise ValueError(name)


def check_page_js() -> str:
    """The page's line functions run by Node: the lines that differ per team
    size, the merged "Differences only", the light formatting."""
    node = shutil.which("node")
    if not node:
        return "Node not found: not run"
    js = STUDIO_JS.read_text(encoding="utf-8")
    head = ("function esc(s) { return String(s).replace(/[&<>\"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', "
            "'>': '&gt;', '\"': '&quot;' }[c]; }); }\n")
    head += "var TESTS = {}, STATE = {};\nfunction toolState(n) { return STATE[n] || null; }\n"
    head += "function TE() { return { tools: { qzx: 1, qzx_2: 1 }, removed: ['gone'] }; }\n"
    prog = head + "\n".join(_js_piece(js, n) for n in ("lcsPairs", "diffMarks", "mergeTexts", "mdLine", "mdText", "toolSig",
                                                        "toolStatus", "ERROR_HINTS", "plainError",
                                                        "toolSlug", "pyFunctions", "slotByName", "pathPlace", "valPages",
                                                        "VAL_WORD", "proposedOf", "unitMismatch", "settingItems",
                                                        "primerPictureChanged", "textsChanged", "pageChanged",
                                                        "pageProblems", "firstPara")) + """
var out = {
  marks: diffMarks({'3': 'a\\nb\\nc', '5': 'a\\nB\\nc', '7': 'a\\nb\\nc'}),
  same: diffMarks({'5': 'x\\ny', '7': 'x\\ny'}),
  merged: mergeTexts({'3': 'a\\nb\\nc', '5': 'a\\nB\\nc', '7': 'a\\nb\\nc'}).lines,
  line: mdLine('<b>x</b> **y** `z` $slot_name <<IF:tool:t>>'),
  text: mdText('# Head\\nplain\\n\\nmarked', {3: 1})
};
STATE.a = { opened: true, gone_files: [], files: [{ path: 'tool.yaml', sha: '1' }, { path: 'prompts/x.md', sha: '2', prompts: true }] };
STATE.b = { opened: true, gone_files: [], files: [{ path: 'tool.yaml', sha: '3', changed: true }] };
var st = [toolStatus('a').k + '|' + toolStatus('a').text, toolStatus('b').k];
TESTS.a = { report: { seconds: 7, mismatches: [] }, sig: toolSig('a') };
st.push(toolStatus('a').k);
STATE.a.files[1].sha = '9';
st.push(toolStatus('a').k);
TESTS.a.report = { failed: true, mismatches: [] };
st.push(toolStatus('a').k);
STATE.a.files[0].sha = '8';
st.push(toolStatus('a').k + '|' + toolStatus('a').text);
out.status = st;
out.slugs = [toolSlug('Hose adapter (v2)!'), toolSlug('Qzx'), toolSlug('3D viewer'), toolSlug('Gone'), toolSlug('  ')];
out.fns = pyFunctions('import x\\n\\ndef first(a):\\n    def inner():\\n        pass\\n\\nclass K:\\n    def method(self):\\n        pass\\n\\ndef second (b) :\\n    return b\\n');
// the menu's marks
var D = { slots: [{ slot: 'dc_name', section: 'identity' }, { slot: 'tool_entry_x', section: 'tools' }, { slot: 'parameter_list', section: 'parameters' }],
  changed: [], tools: [], primer: { image: 'p.png', rows: [{ agent: 'planner', cells: { '7': true } }], problems: [] },
  parameters: { parameters: [{ name: 'a', unit: 'mm', unit_prompt: 'millimetres' }] }, parameter_access: { rows: [{ agent: 'planner', cells: { '7': 'full' } }] } };
var PEDATA = { spec: { parameters: [{ name: 'a' }] }, access_opened: { planner: { '7': 'full' } } };
function PE() { return PEDATA; }
var PREDATA = { opened: { image: 'p.png', agents: { '7': ['planner'] } }, picture: {} };
function PRE() { return PREDATA; }
var TEDATA = { tools: {}, removed: [] };
TE = function () { return TEDATA; };
function getPath(o, path) { return path.reduce(function (x, k) { return x == null ? undefined : x[k]; }, o); }
function geometryTools() { return []; }
var VAL = { state: null };
function marks() { return ['identity', 'parameters', 'tools', 'settings', 'primer', 'access'].map(function (id) {
  var p = pageProblems(id); return id + ':' + (p.length ? (p.some(function (x) { return x.k === 'bad'; }) ? 'bad' : 'warn') : pageChanged(id) ? 'good' : 'none'); }).join(' '); }
out.marks0 = marks();
D.parameters.parameters[0].unit_prompt = 'mm';
PREDATA.picture.sha = 'b';
PREDATA.opened.picture_sha = 'a';
D.changed = ['dc_name@planner', 'tools/qzx/prompts/tool_list_entry.md', 'assets/p.png'];
out.marks1 = marks();
D.changed = ['parameters.json', 'pack.yaml'];
D.parameter_access.rows[0].cells['7'] = 'names';
PREDATA.opened.agents['7'] = [];
STATE.qzx = { manifest: { settings: [{ name: 's', 'default': 2 }] }, opened_manifest: { settings: [{ name: 's', 'default': 1 }] } };
TEDATA.tools = { qzx: 1 };
out.marks2 = marks();
VAL.state = { current: false, report: { items: [
  { status: 'fail', title: 'The texts', lines: ['$dc_name (7-agent team): bad'] },
  { status: 'warn', title: 'Text about a tool', lines: ['tools/qzx/prompts/tool_entry_x.md: <<IF:tool:y>>', 'fragments/dc/parameter_list.md: x'] },
  { status: 'pass', title: 'Agent access', lines: [], link: { section: 'access' } },
  { status: 'fail', title: 'The primer', lines: [], link: { section: 'primer' } }] } };
out.marks3 = marks();
out.marktext = (pageProblems('identity')[0] || {}).text;
out.para = [firstPara('One\\nline.\\n\\nArgs:\\n  x'), firstPara(''), firstPara('A  b\\n \\nc')];
out.errors = [plainError({ error: 'Traceback (most recent call last):\\n  ...\\nFileNotFoundError: openscad: not found' }),
              plainError({ error: 'line 1\\nValueError: bad value\\n' })];
process.stdout.write(JSON.stringify(out));
"""
    p = subprocess.run([node], input=prog, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if p.returncode != 0:
        check(False, f"[PAGE] the page's line functions do not run: {p.stderr[-300:]}")
        return "not run"
    r = json.loads(p.stdout)
    check(r["marks"] == {"3": {"1": 1}, "5": {"1": 1}, "7": {"1": 1}}, f"[PAGE] the lines that differ: {r['marks']}")
    check(r["same"] == {"5": {}, "7": {}}, f"[PAGE] two equal texts have lines that differ: {r['same']}")
    check([(x["line"], x["teams"]) for x in r["merged"]] == [("a", ["3", "5", "7"]), ("B", ["5"]), ("b", ["3", "7"]), ("c", ["3", "5", "7"])],
          f"[PAGE] Differences only: {r['merged']}")
    check("&lt;b&gt;x&lt;/b&gt;" in r["line"] and "<b>y</b>" in r["line"] and "<code>z</code>" in r["line"]
          and '<span class="sv">$slot_name</span>' in r["line"] and '<span class="mk">&lt;&lt;IF:tool:t&gt;&gt;</span>' in r["line"],
          f"[PAGE] the light formatting of a line: {r['line']}")
    check(r["text"] == '<div class="ln h">Head</div><div class="ln">plain</div><div class="ln">&nbsp;</div><div class="ln dif">marked</div>',
          f"[PAGE] the light formatting of a text: {r['text']}")
    check(r["status"] == ["|not tested yet", "warn", "good", "good", "bad", "warn|⚠ changed, not tested"],
          f"[PAGE] a tool's test status: {r['status']}")
    check(r["errors"][0].startswith("OpenSCAD was not found") and r["errors"][0].endswith("FileNotFoundError: openscad: not found")
          and r["errors"][1] == "ValueError: bad value", f"[PAGE] the error in a few words: {r['errors']}")
    check(r["slugs"] == ["hose_adapter_v2", "qzx_3", "tool_3d_viewer", "gone_2", "tool"], f"[PAGE] a tool's folder name: {r['slugs']}")
    check(r["fns"] == ["first", "second"], f"[PAGE] a script's top-level functions: {r['fns']}")
    want = ["identity:none parameters:warn tools:none settings:none primer:none access:none",
            "identity:good parameters:none tools:good settings:none primer:good access:none",
            "identity:none parameters:good tools:none settings:good primer:good access:good",
            "identity:bad parameters:warn tools:warn settings:good primer:bad access:good"]
    got = [r["marks0"], r["marks1"], r["marks2"], r["marks3"]]
    check(got == want, f"[PAGE] the menu's marks: {got}")
    check(r["marktext"] == "Validate › The texts: failed (before the last change: run Validate again)", f"[PAGE] a mark's line: {r['marktext']!r}")
    check(r["para"] == ["One line.", "", "A b"], f"[PAGE] a description's first paragraph: {r['para']}")
    return ("the lines that differ, Differences only, the formatting, a tool's test status, the error in a few words, "
            "a tool's folder name, a script's functions, the menu's marks")


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
    ranges, numbered 1..n -- read by the drift check's own parser; a choice's
    or an on/off parameter's entry holds its values, and any entry its
    "(only when ...)" (engine/parameters.py entry_problem)."""
    from engine import parameters as eparams
    from smoke_test_parameters import parameter_entries, parse_parameter_list
    want = [(p["name"], (float(p["min"]), float(p["max"])) if "min" in p else None) for p in spec["parameters"]]
    by = {p["name"]: p for p in spec["parameters"]}
    ok = True
    for rel in rels:
        text = (copy / rel).read_bytes().decode("utf-8")
        got = parse_parameter_list(text)
        wrong = [(n, eparams.entry_problem(by[n], body)) for _, n, body in parameter_entries(text)
                 if n in by and eparams.entry_problem(by[n], body)]
        good = ([n for n, _, _ in got] == list(range(1, len(got) + 1))
                and [(nm, r) for _, nm, r in got] == want and not wrong)
        check(good, f"[PARAMS] {what}: {rel} is not in step with parameters.json "
                    f"({[(nm, r) for _, nm, r in got][:3]}... vs {want[:3]}...; {wrong[:2]})")
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
    # A choice's / an on/off parameter's list words: the engine's, word for word.
    from smoke_test_parameters import TYPED_SPEC
    check(all(PE.values_text(p) == eparams.values_text(p) and PE.used_when_text(p) == eparams.used_when_text(p)
              for p in TYPED_SPEC["parameters"]),
          "[PARAMS] the Studio's list words for choice and on/off parameters are not the engine's")
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
    # 1b. Choice and on/off parameters, "only when" (MAS-blueprint P6d):
    # a number made on/off, a new choice used only with it, a number used only
    # with it; the choices changed and moved; each back byte for byte.
    s = copymod.deepcopy(spec)
    onoff = s["parameters"][1]
    for k in ("min", "max", "step"):
        onoff.pop(k)
    onoff.update(type="bool", default=True)
    g0 = s["parameters"][0]["group"]
    last = max(k for k, p in enumerate(s["parameters"]) if p["group"] == g0)
    s["parameters"].insert(last + 1, {"name": "qzxFinish", "type": "choice",
                                      "choices": [{"value": "raw", "label": "Raw wood"}, {"value": "oiled", "label": "Oiled"}],
                                      "default": "raw", "group": g0, "label": "Finish", "unit": "", "db_unit": "choice",
                                      "db_description": "Surface finish", "used_when": {onoff["name"]: True}})
    next(x for x in s["groups"] if x["id"] == g0)["order"].append("qzxFinish")
    s["parameters"][-1]["used_when"] = {onoff["name"]: [True, False]}
    status, r = st.call("preview_parameters", s, sha, {})
    check(r.get("ok") and r.get("database") is True, f"[PARAMS] typed: the preview: {str(r)[:200]}")
    sha = _save(st, "typed", s, sha)
    _lists_agree(copy, lists, s, "typed")
    for rel in lists:
        body = (copy / rel).read_bytes().decode("utf-8")
        line = next((ln for ln in body.splitlines() if "qzxFinish" in ln), "")
        described = any("— " in ln for ln in ref[rel].decode("utf-8").splitlines() if re.match(r"^\s*\d+\.", ln))
        tail = ("raw = Raw wood | oiled = Oiled (only when " + onoff["name"] + " = true)")
        check("(choice)" in line and (line.rstrip().endswith("— Surface finish: " + tail) if described
                                      else line.rstrip().endswith(tail) and "—" not in line),
              f"[PARAMS] typed: {rel} entry {line!r}")
        # the entry made on/off keeps the list's own description
        old = next((ln for ln in ref[rel].decode("utf-8").splitlines()
                    if re.match(r"^\s*\d+\.\s+" + onoff["name"] + r"\b", ln)), "")
        own = old.split("— ", 1)[1].rsplit(" [", 1)[0] if "— " in old else None
        line = next((ln for ln in body.splitlines() if re.match(r"^\s*\d+\.\s+" + onoff["name"] + r"\b", ln)), "")
        check(line.rstrip().endswith((f"— {own}: " if own else "") + "true | false") and "on/off" in line,
              f"[PARAMS] typed: {rel} on/off entry {line!r} (its own description: {own!r})")
    status, d = st.call("get_all")
    info = {p["name"]: p for p in ((d.get("data") or {}).get("parameters") or {}).get("parameters", [])}
    check(status == 200 and d.get("ok") and info.get("qzxFinish", {}).get("copies_agree") is True
          and info.get(onoff["name"], {}).get("min") is None,
          f"[PARAMS] typed: the Studio's own data: {status} {str(info.get('qzxFinish'))[:160]}")
    s2 = copymod.deepcopy(s)
    fin = next(p for p in s2["parameters"] if p["name"] == "qzxFinish")
    fin["choices"] = [{"value": "oiled", "label": "Oiled"}, {"value": "raw", "label": "Raw wood"},
                      {"value": "waxed", "label": "Waxed"}]
    status, r = st.call("preview_parameters", s2, sha, {})
    check(r.get("ok") and r.get("database") is True, f"[PARAMS] typed: choices moved, not a new schema: {str(r)[:200]}")
    sha = _save(st, "typed choices", s2, sha)
    _lists_agree(copy, lists, s2, "typed choices")
    status, r = st.call("csv_parameters", "name,type,choices,default,group\n"
                        f"qzxPick,choice,1 = One | 2 = Two,2,{g0}\nqzxFinish,on/off,yes,\n")
    c = r.get("spec") or {}
    got = {p["name"]: p for p in c.get("parameters", [])}
    check(r.get("ok") and r.get("problems") == []
          and got.get("qzxPick", {}).get("choices") == [{"value": 1, "label": "One"}, {"value": 2, "label": "Two"}]
          and got.get("qzxPick", {}).get("default") == 2
          and got.get("qzxFinish", {}).get("type") == "bool" and "choices" not in got.get("qzxFinish", {}),
          f"[PARAMS] typed: CSV: {str(r)[:300]}")
    if c:
        sha = _save(st, "typed CSV", c, sha)
        _lists_agree(copy, lists, c, "typed CSV")
    sha = _save(st, "typed, back", spec, sha)
    _same("typed, then back")
    for text, words in (("name,type,group\nqzxC,choice," + g0 + "\n", 'needs a "choices" column'),
                        ("name,type,default,group\nqzxB,on/off,maybe," + g0 + "\n", "is not true or false"),
                        ("name,type,choices,default,group\nqzxC,choice,a | b,c," + g0 + "\n", "is not one of its choices")):
        status, r = st.call("csv_parameters", text)
        check(any(words in p for p in r.get("problems", [])), f"[PARAMS] typed CSV {text!r}: not refused ({words}): {r.get('problems')}")
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
    # The page checks a file exactly as the engine does (Node runs the page's own code),
    # choice and on/off parameters too (MAS-blueprint P6d).
    from smoke_test_parameters import PROPOSED_SPEC, TYPED_SPEC, typed_bad_specs
    odd = [{"groups": [], "parameters": []}, [], {"groups": [], "parameters": [{}], "x": 1}]
    typed = [TYPED_SPEC, PROPOSED_SPEC] + typed_bad_specs()
    js = _js_validate([spec] + bad_specs + odd + typed)
    if js is not None:
        check(len(js) == 1 + len(bad_specs) + len(odd) + len(typed), "[PARAMS] the page checked fewer files than it was given")
        for s, got in zip([spec] + bad_specs + odd + typed, js):
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
    # 8. The presets (the Studio's Simple mode): each writes the whole grid in
    # one change, as the page was told; "opened" puts pack.yaml back byte for byte.
    status, d = st.call("get_all")
    presets, ysha = d["data"]["params_edit"]["access_presets"], d["data"]["params_edit"]["pack_yaml_sha"]
    check(set(presets) == set(PE.ACCESS_PRESETS), f"[PARAMS] the access presets offered: {sorted(presets)}")

    def grid_now():
        return {a: c for a, (_i, c) in PE.access_rows((copy / "pack.yaml").read_bytes().decode("utf-8").replace("\r\n", "\n")).items()}
    opened = grid_now()
    refgrid = {a: c for a, (_i, c) in PE.access_rows(PE.reference_pack_yaml().read_text(encoding="utf-8").replace("\r\n", "\n")).items()}
    check(all(s == "full" for c in presets["full"].values() for s in c.values()), "[PARAMS] the full preset is not full everywhere")
    check(all(s == ("names" if a in pa["no_tool"] else "tool") for a, c in presets["lean"].items() for s in c.values()),
          f"[PARAMS] the lean preset: {presets['lean']}")
    check(all(presets["reference"][a][k] == refgrid.get(a, {}).get(k, opened[a][k]) for a in opened for k in opened[a]),
          "[PARAMS] the reference preset is not the reference configurator's grid")
    check(presets["opened"] == opened, "[PARAMS] the opened preset is not the grid as opened")
    for name in ("full", "lean", "reference", "opened"):
        r = _call_ok(st, f"access preset {name}", "set_access_preset", name, ysha)
        ysha = r.get("pack_yaml_sha", ysha)
        check(grid_now() == presets[name], f"[PARAMS] access preset {name}: pack.yaml holds {grid_now()}")
    check((copy / "pack.yaml").read_bytes() == yref, "[PARAMS] the presets and back to opened: pack.yaml not byte for byte")
    status, r = st.call("set_access_preset", "qzx", ysha)
    check(r.get("ok") is False and "is not a preset" in r.get("error", ""), f"[PARAMS] preset qzx: {str(r)[:200]}")
    status, r = st.call("set_access_preset", "full", "0" * 64)
    check(r.get("ok") is False and r.get("conflict") is True, "[PARAMS] a preset with a stale page: not a conflict")
    _same("after the parameter editor")
    return (f"{cases} parameters each changed / renamed / removed / moved and back, a new one in each of "
            f"{len(spec['groups'])} groups, {len(lists)} lists kept in step, {shown} ranges seen in the "
            f"prompts, groups + a picture, imports, CSV, {len(bad_specs)} bad files refused, {cells} access "
            f"changes; byte for byte" + ("" if js is not None else "; Node not found: page check not run"))


# ---------------------------------------------------------------------------
# the tool editor (P6c)
# ---------------------------------------------------------------------------

def _tool_ok(st: Studio, what: str, name: str, *args) -> dict:
    status, r = st.call(name, *args)
    check(status == 200 and r.get("ok") is True, f"[TOOLS] {what}: {name} answered {status} {str(r)[:300]}")
    return r


def _form_changes(m: dict, geometry: list) -> list:
    """Every value the manifest form edits, each changed: (path, value)."""
    out = [(["display_name"], m["display_name"] + " QZX"),
           (["description"], m["description"].rstrip("\n") + "\nQZX added line.")]
    for a, text in (m.get("args") or {}).items():
        out.append((["args", a], text + " QZX"))
    if m.get("roles"):
        extra = next(r for r in ("output_inspector", "planner") if r not in m["roles"])
        out.append((["roles"], m["roles"] + [extra]))
    sw = m.get("switch")
    if sw:
        out += [(["switch", "default"], not sw["default"]), (["switch", "label"], sw["label"] + " QZX"),
                (["switch", "description"], sw["description"] + " QZX")]
    for i, s in enumerate(m.get("settings") or []):
        if s["type"] == "bool":
            new = not s["default"]
        elif s["type"] == "enum":
            new = next(v for v in s["values"] if v != s["default"])
        else:
            new = next(v for v in geometry + (["none"] if s.get("none") else []) if v != s["default"])
        out += [(["settings", i, "default"], new), (["settings", i, "label"], s["label"] + " QZX"),
                (["settings", i, "description"], s["description"] + " QZX")]
    for i, im in enumerate((m.get("outputs") or {}).get("images") or []):
        out += [(["outputs", "images", i, "label"], im["label"] + " QZX"),
                (["outputs", "images", i, "order"], im["order"] + 1),
                (["outputs", "images", i, "default_enabled"], not im["default_enabled"])]
    if "list_order" in m:
        out.append((["list_order"], m["list_order"] + 1))
    return out


def check_tools(st: Studio, copy: Path) -> str:
    """Every value of every manifest through the form, the manifests as
    text, every file of every tool, the tool-list entries, removal, Undo --
    each byte for byte back; the refusals."""
    import copy as copymod
    import yaml as _yaml
    ref = _snapshot(copy)

    def same(what):
        return _same_files(copy, ref, what, "[TOOLS]")
    status, d = st.call("get_all")
    D0 = d["data"]
    TE = D0["tools_edit"]
    names = sorted(TE["tools"])
    check(D0["changed"] == [] and TE["removed"] == [] and len(names) >= 1,
          f"[TOOLS] fresh setup: changed {D0['changed']}, removed {TE['removed']}")
    rhino = next((t for t in D0["tools"] if t["name"] == "rhino_geometry"), None)
    check(rhino is None or [s["env"] for s in rhino["secrets"]] == ["RHINO_COMPUTE_URL", "RHINO_COMPUTE_API_KEY"],
          "[TOOLS] the data does not carry rhino_geometry's secrets")
    geometry = [n for n in names if TE["tools"][n]["manifest"].get("kind") == "geometry"]

    def path_value(m, path):
        for p in path:
            m = m[p]
        return m

    # 1. Every value the form edits, changed and back; a secret added and taken out.
    forms = 0
    for name in names:
        m0 = TE["tools"][name]["manifest"]
        sha = TE["tools"][name]["sha"]
        changes = _form_changes(m0, geometry) + [(["secrets"], (m0.get("secrets") or []) + [
            {"env": "QZX_TEST_KEY", "required": True, "description": "A test variable: never set."}])]
        for path, value in changes:
            m = copymod.deepcopy(m0)
            mm = m
            for p in path[:-1]:
                mm = mm[p]
            mm[path[-1]] = value
            status, r = st.call("save_manifest", name, m, sha)
            what = f"{name} {'.'.join(map(str, path))}"
            if not (r.get("ok") is True):
                check(False, f"[TOOLS] {what}: the form's change was refused: {str(r)[:300]}")
                continue
            sha = r["sha"]
            back = _yaml.safe_load((copy / "tools" / name / "tool.yaml").read_bytes().decode("utf-8"))
            check(back == m, f"[TOOLS] {what}: tool.yaml does not read back as the form's manifest")
            r = _tool_ok(st, f"{what}, back", "save_manifest", name, m0, sha)
            sha = r.get("sha", sha)
            forms += 1
        same(f"{name}: every form value changed and back")
    # 2. Refusals: the engine's own messages; nothing written.
    name = next(n for n in names if TE["tools"][n]["manifest"].get("kind") != "geometry")
    m0, sha = TE["tools"][name]["manifest"], TE["tools"][name]["sha"]
    bad = [("an unknown kind", {"kind": "qzx"}, "kind must be one of"),
           ("no description", {"description": ""}, "description is required"),
           ("no role", {"roles": []}, "roles must list"),
           ("an unknown role", {"roles": ["qzx"]}, "roles must list"),
           ("an unknown field", {"qzx": 1}, "unknown field 'qzx'"),
           ("another name", {"name": "qzx_other"}, "name must be the folder name"),
           ("a bad secret", {"secrets": [{"env": "qzx", "description": "x"}]}, "secrets[0] is")]
    for what, edit, words in bad:
        m = dict(copymod.deepcopy(m0), **edit)
        status, r = st.call("save_manifest", name, m, sha)
        check(r.get("ok") is False and any(words in p for p in r.get("problems", [])),
              f"[TOOLS] {what}: not refused with the engine's reason: {str(r)[:300]}")
    s_bad = next(((i, s) for i, s in enumerate(m0.get("settings") or []) if s["type"] == "enum"), None)
    if s_bad:
        m = copymod.deepcopy(m0)
        m["settings"][s_bad[0]]["default"] = "qzx_not_a_value"
        status, r = st.call("save_manifest", name, m, sha)
        check(r.get("ok") is False and any("values must list the default" in p for p in r.get("problems", [])),
              f"[TOOLS] an enum default not among its values: not refused: {str(r)[:200]}")
    status, r = st.call("save_manifest", name, dict(m0, display_name="x"), "0" * 64)
    check(r.get("ok") is False and r.get("conflict") is True, "[TOOLS] a stale page: not a conflict")
    same("after the refused manifests")
    # 3. The manifest as text: a comment added and back; broken YAML refused.
    text0 = (copy / "tools" / name / "tool.yaml").read_bytes().decode("utf-8").replace("\r\n", "\n")
    r = _tool_ok(st, "tool.yaml text", "save_tool_file", name, "tool.yaml", "# QZX comment\n" + text0, sha)
    raw = (copy / "tools" / name / "tool.yaml").read_bytes()
    check(raw.startswith(b"# QZX comment") and (b"\r\n" in raw) == (b"\r\n" in ref[f"tools/{name}/tool.yaml"]),
          "[TOOLS] tool.yaml text: not written in the file's own line endings")
    _tool_ok(st, "tool.yaml text, back", "save_tool_file", name, "tool.yaml", text0, r.get("sha"))
    status, r = st.call("save_tool_file", name, "tool.yaml", text0 + "\n  : [unclosed\n", sha)
    check(r.get("ok") is False and r.get("problems"), f"[TOOLS] broken YAML text: not refused: {str(r)[:200]}")
    same("the manifest as text and back")
    # 4. Every file of every tool: a text file edited and back, a binary
    #    replaced and back, a file added and taken out.
    files = 0
    for tname in names:
        for f in TE["tools"][tname]["files"]:
            rel = f["path"]
            if rel == "tool.yaml" or (f["prompts"] and not f["entry"]):
                continue
            if f["text"]:
                status, r = st.call("tool_file", tname, rel)
                text = r.get("text")
                mark = {".py": "# QZX\n", ".mjs": "// QZX\n", ".js": "// QZX\n"}.get(Path(rel).suffix, "QZX\n")
                new = text + ("" if text.endswith("\n") else "\n") + mark
                r2 = _tool_ok(st, f"{tname}/{rel}", "save_tool_file", tname, rel, new, r.get("sha"))
                raw = (copy / "tools" / tname / rel).read_bytes()
                old = ref[f"tools/{tname}/{rel}"]
                check((b"\r\n" in raw) == (b"\r\n" in old) or b"\n" not in old,
                      f"[TOOLS] {tname}/{rel}: line endings not kept")
                if rel.endswith(".py"):
                    r3 = _tool_ok(st, f"{tname}/{rel} broken", "save_tool_file", tname, rel, new + "def broken(:\n", r2.get("sha"))
                    check(any("does not compile" in w for w in r3.get("warnings", [])),
                          f"[TOOLS] {tname}/{rel}: a syntax error gave no warning")
            else:
                _tool_ok(st, f"{tname}/{rel} replaced", "upload_tool_file", tname, rel,
                         base64.b64encode(b"QZX not the real file").decode(), f["sha"])
            _tool_ok(st, f"{tname}/{rel} undo", "undo_tool_file", tname, rel)
            files += 1
    status, r = st.call("tool_file", names[0], "tool.yaml")
    _tool_ok(st, "a file added", "upload_tool_file", names[0], "qzx_added.txt", base64.b64encode(b"qzx\n").decode(), None)
    status, d = st.call("get_all")
    added = [f for f in d["data"]["tools_edit"]["tools"][names[0]]["files"] if f["path"] == "qzx_added.txt"]
    check(added and added[0]["added"] and f"tools/{names[0]}/qzx_added.txt" in d["data"]["changed"],
          "[TOOLS] an added file is not listed as added and changed")
    _tool_ok(st, "an added file, undo", "undo_tool_file", names[0], "qzx_added.txt")
    for rel, words in (("../qzx.txt", "not a file name"), ("prompts/qzx.md", "text fields"),
                       ("__pycache__/x.py", "not a file name")):
        status, r = st.call("upload_tool_file", names[0], rel, base64.b64encode(b"x").decode(), None)
        check(r.get("ok") is False and words in r.get("error", ""), f"[TOOLS] upload to {rel}: not refused: {r}")
    status, r = st.call("upload_tool_file", names[0], "tool.yaml", base64.b64encode(b"x").decode(), None)
    check(r.get("ok") is False and r.get("conflict") is True, "[TOOLS] an upload over an existing file without its sha: not a conflict")
    same("every tool file edited or replaced, and back")
    # 5. The tool-list entries: prompt text, checked like a text field.
    for tname in names:
        for f in [f for f in TE["tools"][tname]["files"] if f["entry"]]:
            status, r = st.call("tool_file", tname, f["path"])
            status, r2 = st.call("save_tool_file", tname, f["path"], r["text"] + " {QZX}", r["sha"])
            check(r2.get("ok") is False and any("{ or }" in p for p in r2.get("problems", [])),
                  f"[TOOLS] {tname} list entry with braces: not refused: {str(r2)[:200]}")
    same("after the refused list entries")
    # 6. Removal: what still names a tool blocks it; one is removed, the
    #    prompts lose it, and Undo brings it back byte for byte.
    removable = None
    for tname in names:
        status, r = st.call("remove_tool_preview", tname)
        uses = [o for o in names if o != tname and any(
            s.get("type") == "tool" and s.get("default") == tname
            for s in TE["tools"][o]["manifest"].get("settings") or [])]
        check(bool(r.get("blockers")) == bool(uses) or "pack.yaml" in " ".join(r.get("blockers", [])),
              f"[TOOLS] {tname}: removal blockers {r.get('blockers')} but used by {uses}")
        if TE["tools"][tname]["manifest"].get("kind") == "generator":
            check(any("only generator" in w for w in r.get("warnings", [])),
                  f"[TOOLS] {tname}: no warning for removing the only generator")
        elif not r.get("blockers") and not r.get("problems") and removable is None:
            removable = tname
        if r.get("blockers"):
            status, r2 = st.call("remove_tool", tname)
            check(r2.get("ok") is False, f"[TOOLS] {tname}: removed although it is still used")
    shown = 0
    if removable:
        _tool_ok(st, f"remove {removable}", "remove_tool", removable)
        check(not (copy / "tools" / removable).exists(), f"[TOOLS] {removable}: its folder is still there")
        status, d = st.call("get_all")
        D1 = d["data"]
        check(removable not in [t["name"] for t in D1["tools"]] and D1["tools_edit"]["removed"] == [removable],
              f"[TOOLS] after removing {removable}: still listed")
        shown = sum(D1["prompts"][t]["prompts"].get(a) != p
                    for t in ("7", "5", "3") for a, p in D0["prompts"][t]["prompts"].items())
        check(shown > 0, f"[TOOLS] after removing {removable}: no prompt changed")
        _tool_ok(st, f"undo {removable}", "undo_tool", removable)
        same(f"{removable} removed, then Undo")
    # 7. A tool with several changes, put back whole.
    tname = names[-1]
    m = copymod.deepcopy(TE["tools"][tname]["manifest"])
    m["display_name"] += " QZX"
    r = _tool_ok(st, "a manifest change", "save_manifest", tname, m, TE["tools"][tname]["sha"])
    _tool_ok(st, "a file added", "upload_tool_file", tname, "qzx_more.txt", base64.b64encode(b"q\n").decode(), None)
    _tool_ok(st, "the tool's Undo", "undo_tool", tname)
    same("a tool changed in several places, then its Undo")
    return (f"{forms} form values of {len(names)} manifests changed and back, {files} tool files edited or "
            f"replaced and back, the refusals, removal of {removable or 'no tool'} ({shown} prompts changed) "
            f"and its Undo; byte for byte")


# ---------------------------------------------------------------------------
# New tool and Test tool (P6c-2)
# ---------------------------------------------------------------------------

def check_new_tools(st: Studio, copy: Path) -> str:
    """A tool from each template and a copy of each tool: made only when the
    engine takes it, run by Test tool, gone again with Undo byte for byte;
    the refusals; Test tool's report, time limit and output lines."""
    import yaml as _yaml
    ref = _snapshot(copy)

    def same(what):
        return _same_files(copy, ref, what, "[NEWTOOL]")

    def ok(what, name, *args):
        status, r = st.call(name, *args)
        check(status == 200 and r.get("ok") is True, f"[NEWTOOL] {what}: {name} answered {status} {str(r)[:300]}")
        return r
    status, d = st.call("get_all")
    D0 = d["data"]
    tools0 = sorted(D0["tools_edit"]["tools"])
    params = {p["name"]: p["default"] for p in D0["params_edit"]["spec"]["parameters"]}
    sample = next(iter((D0["tools_edit"]["samples"] or {}).values()), params)
    # 1. A tool from each template: it runs cleanly; the setup assembles with it.
    made = []
    for kind in ("helper", "generator", "geometry"):
        name = f"qzx_{kind}"
        r = ok(f"the {kind} template", "new_tool", name, f"Qzx {kind}: a test", kind)
        if not r.get("ok"):
            continue
        made.append(name)
        m = _yaml.safe_load((copy / "tools" / name / "tool.yaml").read_bytes().decode("utf-8"))
        check(m.get("name") == name and m.get("kind") == kind and m.get("display_name") == f"Qzx {kind}: a test",
              f"[NEWTOOL] the {kind} template: its manifest names {m.get('name')}, {m.get('kind')}, {m.get('display_name')!r}")
        for values, label in ((params, "defaults"), (sample, "a sample")):
            status, r = st.call("test_tool", name, values, {})
            rep = r.get("report") or {}
            check(r.get("ok") and not rep.get("failed") and not rep.get("mismatches") and rep.get("seconds") is not None,
                  f"[NEWTOOL] the {kind} template on {label}: the run did not come out clean: "
                  f"{str({k: rep.get(k) for k in ('failed', 'error', 'answer', 'mismatches')})[:400]}")
            if kind == "generator":
                check([p["file"] for p in rep.get("pictures", []) if p["declared"] and p.get("png")] == [f"render_{name}.png"]
                      and (rep.get("model") or {}).get("vertices") == 8,
                      f"[NEWTOOL] the generator template: picture {rep.get('pictures')} / model {rep.get('model')}")
            elif kind == "geometry":
                check((rep.get("model") or {}).get("vertices") == 8, f"[NEWTOOL] the geometry template: model {rep.get('model')}")
            else:
                check(str(rep.get("answer", "")).startswith(f"Read {len(values)} parameter values"),
                      f"[NEWTOOL] the helper template: answer {str(rep.get('answer'))[:200]!r}")
    status, d = st.call("get_all")
    if status == 200 and d.get("ok"):
        D1 = d["data"]
        check(sorted(t["name"] for t in D1["tools"]) == sorted(tools0 + made),
              f"[NEWTOOL] after the templates the setup lists {[t['name'] for t in D1['tools']]}")
        runner = [a for t in ("7", "5", "3") for a, tl in D1["prompts"][t]["prompts"].items()
                  if "qzx_helper" in tl and "qzx_generator" in tl]
        check(bool(runner), "[NEWTOOL] no tool runner's prompt lists the new helper and generator")
    else:
        check(False, f"[NEWTOOL] the setup no longer assembles with the template tools: {str(d)[:300]}")
    # 2. A copy of each tool: its own pictures and model file, no texts of
    #    its own, a helper's function renamed; then Test tool.
    copies = []
    for src in tools0:
        name = f"copy_{src}"[:30]
        r = ok(f"a copy of {src}", "new_tool", name, f"Copy of {src}", None, src)
        if not r.get("ok"):
            continue
        copies.append(name)
        m = _yaml.safe_load((copy / "tools" / name / "tool.yaml").read_bytes().decode("utf-8"))
        om = D0["tools_edit"]["tools"][src]["manifest"]
        views = [i["view"] for i in (m.get("outputs") or {}).get("images") or []]
        oviews = [i["view"] for i in (om.get("outputs") or {}).get("images") or []]
        check(m["name"] == name and not m.get("prompt_slots") and not set(views) & set(oviews)
              and all(i["file"] == f"render_{i['view']}.png" for i in (m.get("outputs") or {}).get("images") or []),
              f"[NEWTOOL] the copy of {src}: name {m['name']}, slots {m.get('prompt_slots')}, views {views}")
        if om.get("kind") == "generator":
            check(m["outputs"]["model_file"] != om["outputs"]["model_file"],
                  f"[NEWTOOL] the copy of {src} writes the same model file")
        if om.get("kind") == "helper":
            module, fn = m["entrypoint"].split(":")
            check(fn == name and f"def {name}(" in (copy / "tools" / name / module).read_text(encoding="utf-8"),
                  f"[NEWTOOL] the copy of {src}: its function is not named after it ({m['entrypoint']})")
        texts = [p for p in (copy / "tools" / name / "prompts").glob("*.md")] if (copy / "tools" / name / "prompts").is_dir() else []
        check(all(p.name.startswith("tool_list_entry") for p in texts),
              f"[NEWTOOL] the copy of {src} keeps texts of the original: {[p.name for p in texts]}")
        status, r = st.call("test_tool", name, params, {})
        rep = r.get("report") or {}
        check(r.get("ok") and rep.get("seconds") is not None and ("answer" in rep or rep.get("error")),
              f"[NEWTOOL] Test tool on the copy of {src}: no report: {str(r)[:300]}")
        if om.get("kind") == "helper" and om.get("outputs", {}).get("images"):
            # the copied code still writes the original's picture: reported
            check(any("does not declare" in x for x in rep.get("mismatches", [])),
                  f"[NEWTOOL] the copy of {src}: its picture under the original's name was not reported: "
                  f"{rep.get('mismatches')}")
    # 3. Undo: every new tool goes, byte for byte.
    for name in made + copies:
        ok(f"undo {name}", "undo_tool", name)
    same("the template tools and the copies, then Undo")
    # 3b. Add a tool (the Studio's wizard): a tool made with the roles asked,
    #     and a tool of each kind from an uploaded script -- its file as sent,
    #     its manifest naming the script's function(s) -- that runs; the
    #     refusals; Undo, byte for byte.
    ok("a helper with two roles", "new_tool", "qzx_roles", "Qzx roles", "helper", None, ["tool_runner", "planner"])
    m = _yaml.safe_load((copy / "tools" / "qzx_roles" / "tool.yaml").read_bytes().decode("utf-8"))
    check(m.get("roles") == ["tool_runner", "planner"], f"[NEWTOOL] a new tool's roles: {m.get('roles')}")
    # What it does: the description's first paragraph, the rest kept
    what = "Says how heavy the part is, from an attempt's parameters, in grams and in a sentence the agent can quote."
    tmpl = _yaml.safe_load((ROOT / "studio" / "tool_templates" / "helper" / "tool.yaml").read_text(encoding="utf-8"))["description"]
    ok("a helper with what it does", "new_tool", "qzx_what", "Qzx what", "helper", None, None, "  " + what + "\n")
    m = _yaml.safe_load((copy / "tools" / "qzx_what" / "tool.yaml").read_bytes().decode("utf-8"))
    desc = str(m.get("description"))
    check(" ".join(desc.split("\n\n")[0].split()) == what and desc.split("\n\n", 1)[1:] == tmpl.split("\n\n", 1)[1:]
          and all(len(ln) <= 72 for ln in desc.split("\n\n")[0].split("\n")),
          f"[NEWTOOL] a helper's what it does: {desc[:300]!r}")
    src = sorted(D0["tools_edit"]["tools"])[0]
    old = str(D0["tools_edit"]["tools"][src]["manifest"].get("description") or "")
    ok("a copy with what it does", "new_tool", "qzx_cwhat", "Qzx cwhat", None, src, None, "Copied for the test.")
    m = _yaml.safe_load((copy / "tools" / "qzx_cwhat" / "tool.yaml").read_bytes().decode("utf-8"))
    desc = str(m.get("description"))
    check(desc.split("\n\n")[0] == "Copied for the test." and desc.split("\n\n", 1)[1:] == old.split("\n\n", 1)[1:],
          f"[NEWTOOL] a copy's what it does: {desc[:300]!r} (was {old[:200]!r})")
    status, r = st.call("new_tool", "qzx_bad", "x", "helper", None, None, "x" * 301)
    check(r.get("ok") is False and "at most 300 characters" in r.get("error", ""), f"[NEWTOOL] a what it does of 301 characters: not refused: {r}")
    templates = ROOT / "studio" / "tool_templates"

    def code_of(kind, fn):
        return (templates / kind / "__NAME__.py").read_text(encoding="utf-8").replace("__NAME__", fn).replace("__DISPLAY__", "Qzx")
    scripts = [("helper", "qzx_script", "my-helper.py", code_of("helper", "qzx_script"), {"entrypoint": "qzx_script"}),
               ("geometry", "qzx_geo", "geo.py", code_of("geometry", "x"), {"entrypoint": "make_model"}),
               ("generator", "qzx_gen", "gen.py", code_of("generator", "qzx_gen"), {"build": "build", "render": "render"})]
    from_code = ["qzx_roles", "qzx_what", "qzx_cwhat"]
    for kind, name, fname, code, entry in scripts:
        b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
        what = "Builds the Qzx model." if kind == "geometry" else None
        r = ok(f"a {kind} from a script", "new_tool_from_code", name, f"Qzx {kind} script", kind, fname, b64, entry, None, what)
        if not r.get("ok"):
            continue
        from_code.append(name)
        m = _yaml.safe_load((copy / "tools" / name / "tool.yaml").read_bytes().decode("utf-8"))
        if what:
            check(m.get("description") == what, f"[NEWTOOL] the {kind} from a script: its what it does {m.get('description')!r}")
        module = re.sub(r"[^A-Za-z0-9_]", "_", Path(fname).stem) + ".py"
        check((copy / "tools" / name / module).read_bytes() == code.encode("utf-8")
              and not (copy / "tools" / name / f"{name}.py").exists(),
              f"[NEWTOOL] the {kind} from a script: {module} is not the script, or the template's code stayed")
        keys = ("build", "render") if kind == "generator" else ("entrypoint",)
        check(all(m.get(k) == f"{module}:{entry[k]}" for k in keys),
              f"[NEWTOOL] the {kind} from a script names {[m.get(k) for k in keys]}")
        status, r = st.call("test_tool", name, params, {})
        rep = r.get("report") or {}
        check(r.get("ok") and not rep.get("failed") and not rep.get("mismatches"),
              f"[NEWTOOL] the {kind} from a script does not run cleanly: "
              f"{str({k: rep.get(k) for k in ('failed', 'error', 'mismatches')})[:300]}")
    ok_b64 = base64.b64encode(code_of("helper", "qzx_script").encode("utf-8")).decode("ascii")
    for args, words in ((("qzx_bad", "x", "helper", "s.py", ok_b64, {"entrypoint": "qzx_script"}, None), "named like the tool"),
                        (("qzx_bad", "x", "helper", "s.txt", ok_b64, {"entrypoint": "qzx_bad"}, None), "Python file"),
                        (("qzx_bad", "x", "helper", "s.py", ok_b64, {"entrypoint": "qzx_bad"}, None), "has no function"),
                        (("qzx_bad", "x", "generator", "s.py", ok_b64, {"build": "qzx_script"}, None), "function for render"),
                        (("qzx_bad", "x", "helper", "s.py", "%%%", {"entrypoint": "qzx_bad"}, None), "did not arrive whole")):
        status, r = st.call("new_tool_from_code", *args)
        check(r.get("ok") is False and words in r.get("error", ""), f"[NEWTOOL] new_tool_from_code{args[:4]}: not refused ({words}): {r}")
    status, r = st.call("new_tool", "qzx_bad", "x", "geometry", None, ["planner"])
    check(r.get("ok") is False and "has no roles" in r.get("error", ""), f"[NEWTOOL] a download builder with roles: not refused: {r}")
    for name in from_code:
        ok(f"undo {name}", "undo_tool", name)
    same("the tools with roles and from scripts, then Undo")
    # 4. The refusals.
    removable = "render_blade_sections" if "render_blade_sections" in tools0 else None
    cases = [(("Bad Name", "x", "helper"), "lower case"), ((tools0[0], "x", "helper"), "already has a tool"),
             (("downloads", "x", "helper"), "reserved"), (("qzx_ok", "", "helper"), "display name"),
             (("qzx_ok", "x", "qzx"), "Start from a template"), (("qzx_ok", "x", None, "qzx_nope"), "no tool")]
    # a generator named after a picture view another tool declares: the
    # engine refuses it (each view is one tool's)
    taken = next((i["view"] for t in tools0 for i in (D0["tools_edit"]["tools"][t]["manifest"].get("outputs") or {}).get("images") or []
                  if t != i["view"]), None)
    if taken:
        cases.append(((taken, "x", "generator"), "cannot be made"))
    for args, words in cases:
        status, r = st.call("new_tool", *args)
        check(r.get("ok") is False and words in r.get("error", ""), f"[NEWTOOL] new_tool{args}: not refused ({words}): {r}")
    if removable:
        ok("remove", "remove_tool", removable)
        status, r = st.call("new_tool", removable, "x", "helper")
        check(r.get("ok") is False and "removed since the Studio opened" in r.get("error", ""),
              f"[NEWTOOL] a new tool under a removed tool's name: not refused: {r}")
        ok("undo the removal", "undo_tool", removable)
    same("after the refused new tools")
    # 5. Test tool: a run that fails is reported, not a crash; the time limit;
    #    the tool's own output lines; nothing in the setup changes.
    for name in tools0:
        status, r = st.call("test_tool", name, params, {})
        rep = r.get("report") or {}
        check(r.get("ok") and rep.get("seconds") is not None
              and (rep.get("failed") is False or rep.get("error") or "Error" in str(rep.get("answer"))
                   or "failed" in str(rep.get("answer"))),
              f"[NEWTOOL] Test tool on {name}: {str({k: rep.get(k) for k in ('failed', 'error', 'answer')})[:300]}")
    ok("a printing helper", "new_tool", "qzx_slow", "Qzx slow", "helper")
    py = copy / "tools" / "qzx_slow" / "qzx_slow.py"
    status, rf = st.call("tool_file", "qzx_slow", "qzx_slow.py")
    text = rf["text"].replace('    path = Path(parameters_path)',
                              '    import sys, time\n    print("QZX-PRINT", flush=True)\n'
                              '    print("QZX-ERR", file=sys.stderr, flush=True)\n'
                              '    if "slow" in parameters_path or Path(parameters_path).parent.name.endswith("test"):\n'
                              '        time.sleep(float(__import__("os").environ.get("QZX_SLEEP", "0")))\n'
                              '    path = Path(parameters_path)')
    ok("the printing helper's code", "save_tool_file", "qzx_slow", "qzx_slow.py", text, rf["sha"])
    status, r = st.call("test_tool", "qzx_slow", params, {})
    rep = r.get("report") or {}
    check("QZX-PRINT" in rep.get("output", []) and "QZX-ERR" in rep.get("output", []) and not rep.get("failed"),
          f"[NEWTOOL] Test tool did not keep the tool's own output: {rep.get('output')}")
    text2 = text.replace('time.sleep(float(__import__("os").environ.get("QZX_SLEEP", "0")))', "time.sleep(30)")
    ok("the slow helper's code", "save_tool_file", "qzx_slow", "qzx_slow.py", text2, py and _sha_of(py))
    t0 = time.time()
    status, r = st.call("test_tool", "qzx_slow", params, {}, 5)
    rep = r.get("report") or {}
    check(rep.get("failed") and "longer than 5 s" in str(rep.get("error")) and time.time() - t0 < 25,
          f"[NEWTOOL] the time limit: {str({k: rep.get(k) for k in ('failed', 'error')})} after {time.time() - t0:.0f} s")
    ok("undo the printing helper", "undo_tool", "qzx_slow")
    same("after the test runs")
    return (f"{len(made)} templates made, run clean and undone; {len(copies)} copies made, run and undone; "
            f"{len(cases) + (1 if removable else 0)} new tools refused; every tool test-run; the time limit "
            f"and the tool's own output kept; byte for byte")


def _sha_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------

def main() -> int:
    _run(check_cache_unit, "[CACHE]")
    _run(check_generic, "[GENERIC]")
    page_js = _run(check_page_js, "[PAGE]")
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
            summary["written"] = _run(lambda: check_as_written(st), "[WRITTEN]")
            _run(lambda: check_choices(D), "[VIEWER]")
            summary["pool"] = _run(lambda: check_pool(D, copy), "[VIEWER]")
            summary["cache"] = _run(lambda: check_cache(st, D, copy, first), "[CACHE]")
            summary["edit"] = _run(lambda: check_edit(st, copy), "[EDIT]")
            summary["params"] = _run(lambda: check_params(st, copy), "[PARAMS]")
            summary["tools"] = _run(lambda: check_tools(st, copy), "[TOOLS]")
            summary["new_tools"] = _run(lambda: check_new_tools(st, copy), "[NEWTOOL]")
            summary["first"] = f"{first:.0f} s"
    finally:
        if st is not None:
            st.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"first assembly {summary.get('first')}; {summary.get('fields')} fields shown as the "
          f"engine reads them; {summary.get('where')} field texts (per topology) found in a "
          f"prompt, each with its sentences there; {summary.get('prompts')} prompts = the prompt matrix's base; "
          f"{summary.get('cache')}; {summary.get('viewer')}; as written: {summary.get('written')}; {summary.get('pool')}; "
          f"editing: {summary.get('edit')}; parameters: {summary.get('params')}; "
          f"tools: {summary.get('tools')}; new tools: {summary.get('new_tools')}; the page's line functions: {page_js}")
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - the Studio shows every field of the setup, where each one lands, and "
          "the engine's own prompts and tools under every choice of settings, sees "
          "a changed file, edits every text field, parameter, access cell and tool, "
          "makes and test-runs new tools, and puts each back byte for byte.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
