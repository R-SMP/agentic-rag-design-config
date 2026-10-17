"""The Studio, read-only (MAS-blueprint P5a): the real server on a copy of the pack.

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

Takes about two minutes (two full assemblies).  Run from the repo root:
    py -3.13 extra_utilities/tests/smoke_test_studio.py
"""
from __future__ import annotations

import ast
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
            [sys.executable, "-m", "studio", "--pack", str(pack_dir), "--port", str(self.port)],
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
            summary["cache"] = _run(lambda: check_cache(st, D, copy, first), "[CACHE]")
            summary["first"] = f"{first:.0f} s"
    finally:
        if st is not None:
            st.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"first assembly {summary.get('first')}; {summary.get('fields')} fields shown as the "
          f"engine reads them; {summary.get('where')} field texts (per topology) found in a "
          f"prompt, each with its sentences there; {summary.get('prompts')} prompts = the prompt matrix's base; "
          f"{summary.get('cache')}")
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - the Studio shows every field of the setup, where each one lands, and "
          "the engine's own prompts, and sees a changed file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
