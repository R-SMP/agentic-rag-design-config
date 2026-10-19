"""Offline check of the downloads and Open setup file (MAS-blueprint P7-2,
``studio/package.py``).

1. THE SETUP FILE, from the Studio (``GET /download/setup``): the setup's
   files under ``dc_pack/``, byte for byte, and ``setup_info.json`` (the
   configurator, the engine, ``pack_format``, Validate not run).  Changed in
   the Studio, then opened again (``open_setup``): the setup is back byte for
   byte, nothing is listed as changed, Undo starts from it; a different
   setup file opened is the new start (nothing listed as changed).  A full package
   opens too (its ``dc_pack/`` is taken).  Refused, writing nothing: not a
   zip, no ``dc_pack/``, a path out of the folder, a file name Windows
   cannot hold, a setup in a newer
   format, a parameter file the engine refuses.
2. THE FULL PACKAGE (``GET /download/package``): one folder holding the
   engine -- every file git has or would take in the engine's folders, and
   no other (no notes, docs, benchmarks or propeller-only checks, no
   Workflow Settings saved on this computer, no ``.env``) --, this setup as
   ``dc_pack/``, ``README.md`` and ``DEPLOY.md`` naming the configurator and
   its tools' variables, ``.env.example`` with them, ``setup_info.json``.
   A tool's own ``requirements.txt`` and ``apt.txt`` are merged into
   ``requirements.txt`` and the ``Dockerfile`` (a package the engine names
   kept as the engine has it, with a note).  The engine's files are the same
   found by git and by walking the folders.
3. THE KEY SCAN: nothing in the engine or the propeller's setup; a planted
   key in a tool is listed by ``download_preview`` with its file, line and a
   masked value, and the download still works.
4. INSIDE THE PACKAGE, unpacked into an empty folder: ``python -m studio
   validate`` finds no failure -- the package holds all Validate needs.

Takes about two minutes.  Run from the repo root:
    py -3.13 extra_utilities/tests/smoke_test_package.py
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
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ["DATABASE_URL"] = ""
os.environ["DATABASE_PUBLIC_URL"] = ""
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from studio import package as K                  # noqa: E402

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

    def get(self, path: str) -> tuple[int, dict, bytes]:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=600) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

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

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def snapshot(folder: Path) -> dict[str, bytes]:
    return {rel: p.read_bytes() for rel, p in K.setup_files(folder).items()}


def zip_files(raw: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        return {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}


def make_zip(files: dict[str, bytes]) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ---------------------------------------------------------------------------
# 1. the setup file
# ---------------------------------------------------------------------------

def check_setup_file(st: Studio, copy: Path) -> str:
    before = snapshot(copy)
    status, headers, raw = st.get("/download/setup")
    check(status == 200 and "propeller_design_configurator_setup.zip" in headers.get("content-disposition", ""),
          f"[SETUP] GET /download/setup: {status} {headers.get('content-disposition')}")
    files = zip_files(raw)
    inside = {k[len("dc_pack/"):]: v for k, v in files.items() if k.startswith("dc_pack/")}
    check(inside == before, f"[SETUP] the setup file is not the setup byte for byte: "
                            f"{sorted(set(inside) ^ set(before))[:5]}")
    check(set(files) == {"setup_info.json"} | {f"dc_pack/{r}" for r in before},
          f"[SETUP] other files in the setup file: {sorted(set(files) - {'setup_info.json'} - {f'dc_pack/{r}' for r in before})[:5]}")
    info = json.loads(files.get("setup_info.json", b"{}"))
    check(info.get("configurator") == "Propeller Design Configurator" and info.get("pack_format") == 1
          and info.get("validate") == {"status": "not run"} and info.get("made_by") == "MAS Studio"
          and info.get("engine"), f"[SETUP] setup_info.json: {info}")
    # changed in the Studio, then opened again
    d = st.call("get_all")["data"]
    s = next(x for x in d["slots"] if x["slot"] == "dc_name")
    check(st.call("save_field", "dc_name", None, {"all": "a changed name"}, {"all": s["values"]["7"]})["ok"],
          "[SETUP] the test's own edit was refused")
    spec = json.loads((copy / "parameters.json").read_text(encoding="utf-8"))
    (copy / "assets" / "added_by_the_test.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    check(st.call("get_all")["data"]["changed"] != [], "[SETUP] the edits are not listed as changed")
    r = st.call("open_setup", base64.b64encode(raw).decode("ascii"), "setup.zip")
    check(r.get("ok") and r.get("files") == len(before), f"[SETUP] open_setup: {str(r)[:400]}")
    check(snapshot(copy) == before, "[SETUP] the setup opened again is not byte for byte the setup")
    d = st.call("get_all")["data"]
    check(d["changed"] == [], f"[SETUP] after opening, these are listed as changed: {d['changed'][:5]}")
    check(next(x for x in d["slots"] if x["slot"] == "dc_name")["values"]["7"] == s["values"]["7"],
          "[SETUP] the opened setup's name is not shown")
    # Undo now starts from the opened file: a change and its Undo leave it as opened
    st.call("save_field", "dc_name", None, {"all": "again"}, {"all": s["values"]["7"]})
    st.call("undo_field", "dc_name", None)
    check(snapshot(copy) == before, "[SETUP] Undo after opening does not go back to the opened file")
    # a setup file that differs from the setup: once opened, it is the start
    other = {f"dc_pack/{k}": v for k, v in inside.items()}
    other["dc_pack/fragments/dc/dc_name.md"] = b"another name\n"
    r = st.call("open_setup", make_zip(other), "other.zip")
    d = st.call("get_all")["data"]
    check(r.get("ok") and d["changed"] == []
          and next(x for x in d["slots"] if x["slot"] == "dc_name")["values"]["7"] == "another name",
          f"[SETUP] a different setup file opened: listed as changed {d['changed'][:4]}, {str(r)[:200]}")
    r = st.call("open_setup", base64.b64encode(raw).decode("ascii"), "setup.zip")
    check(r.get("ok") and snapshot(copy) == before, "[SETUP] the first setup file did not open again")
    # a full package opens too (its dc_pack/)
    _st, _h, pkg = st.get("/download/package")
    r = st.call("open_setup", base64.b64encode(pkg).decode("ascii"), "package.zip")
    check(r.get("ok") and snapshot(copy) == before, f"[SETUP] a full package did not open: {str(r)[:300]}")
    # refusals, each writing nothing
    newer = dict(inside)
    newer["pack.yaml"] = inside["pack.yaml"].replace(b"pack_format: 1", b"pack_format: 99")
    bad_spec = dict(inside)
    spec["parameters"][0].update(min=10, max=5)
    bad_spec["parameters.json"] = json.dumps(spec).encode("utf-8")
    cases = {
        "not a zip": (base64.b64encode(b"not a zip").decode("ascii"), "not a zip"),
        "no dc_pack/": (make_zip({"something/else.txt": b"x"}), "no dc_pack/"),
        "a path out of the folder": (make_zip({"dc_pack/pack.yaml": inside["pack.yaml"],
                                               "dc_pack/../escape.txt": b"x"}), "not a path"),
        "a newer format": (make_zip({f"dc_pack/{k}": v for k, v in newer.items()}), "newer engine"),
        "a file name Windows cannot hold": (make_zip({"dc_pack/pack.yaml": inside["pack.yaml"],
                                                      "dc_pack/fragments/x:y.md": b"x"}), "not a path"),
        "a parameter file the engine refuses": (make_zip({f"dc_pack/{k}": v for k, v in bad_spec.items()}),
                                                "must be smaller than max"),
    }
    for what, (b64, words) in cases.items():
        r = st.call("open_setup", b64, "x.zip")
        text = (r.get("error") or "") + " " + " ".join(r.get("problems") or [])
        check(r.get("ok") is False and words in text, f"[SETUP] {what}: not refused ({str(r)[:300]})")
        check(snapshot(copy) == before, f"[SETUP] {what}: the setup changed although it was refused")
    check(not (ROOT / "escape.txt").exists() and not (copy.parent / "escape.txt").exists(),
          "[SETUP] a file was written out of the folder")
    return f"setup file: {len(before)} files, round trip byte for byte, {len(cases)} refusals"


# ---------------------------------------------------------------------------
# 2-3. the full package and the key scan
# ---------------------------------------------------------------------------

def check_package(st: Studio, copy: Path, tmp: Path) -> str:
    # A new engine file not committed yet goes in; Workflow Settings saved on
    # this computer do not (each planted only for the run, if not there).
    probe = ROOT / "studio" / "zz_package_probe_untracked.py"
    saved = ROOT / "workflow_settings" / "tool_settings.json"
    planted = [f for f in (probe, saved) if not f.exists()]
    for f in planted:
        f.write_text("{}\n" if f is saved else "# a probe of smoke_test_package.py\n",
                     encoding="utf-8")
    try:
        git, walk = set(K.engine_files(use_git=True)), set(K.engine_files(use_git=False))
        check(git == walk, f"[PACKAGE] git and the folders name different engine files: "
                           f"{sorted(git ^ walk)[:6]}")
        check("studio/zz_package_probe_untracked.py" in git,
              "[PACKAGE] a new engine file not committed yet is left out")
        check("workflow_settings/tool_settings.json" not in git | walk,
              "[PACKAGE] the Workflow Settings saved on this computer are in the package")
    finally:
        for f in planted:
            f.unlink(missing_ok=True)
    # a tool of the setup with its own dependencies and a declared secret
    tool = copy / "tools" / "render_blade_sections"
    (tool / "requirements.txt").write_text("# for the test\nqzx-test-package==1.0\nnumpy==1.0\n",
                                           encoding="utf-8")
    (tool / "apt.txt").write_text("libqzx-test\n", encoding="utf-8")
    y = tool / "tool.yaml"
    yraw = y.read_bytes()
    y.write_bytes(yraw.replace(b"list_order: 10", b"list_order: 10\nsecrets:\n  - {env: QZX_TOOL_KEY, "
                               b"required: true, description: \"The test service's key.\"}"))
    try:
        pv = st.call("download_preview", "package")
        check(pv.get("ok") and pv["findings"] == [], f"[SCAN] findings in the engine and the setup: "
                                                     f"{pv.get('findings', pv)}"[:600])
        check(any("numpy" in n and "kept" in n for n in pv.get("notes", [])),
              f"[PACKAGE] no note for a package the engine already names: {pv.get('notes')}")
        status, headers, raw = st.get("/download/package")
        check(status == 200 and "propeller_design_configurator_package.zip" in headers.get("content-disposition", ""),
              f"[PACKAGE] GET /download/package: {status}")
        files = zip_files(raw)
        top = {k.split("/", 1)[0] for k in files}
        check(top == {"propeller_design_configurator"}, f"[PACKAGE] not one folder: {sorted(top)[:5]}")
        files = {k.split("/", 1)[1]: v for k, v in files.items()}
        setup = snapshot(copy)
        engine = set(K.engine_files())
        written = {"README.md", "DEPLOY.md", ".env.example", "setup_info.json"}
        want = engine | {f"dc_pack/{r}" for r in setup} | written
        check(set(files) == want, f"[PACKAGE] files: extra {sorted(set(files) - want)[:5]}, "
                                  f"missing {sorted(want - set(files))[:5]}")
        for rel in engine - {"requirements.txt", "Dockerfile"}:
            if files.get(rel) != (ROOT / rel).read_bytes():
                check(False, f"[PACKAGE] {rel} is not the engine's file")
                break
        check(all(files.get(f"dc_pack/{r}") == b for r, b in setup.items()),
              "[PACKAGE] dc_pack/ is not the setup byte for byte")
        for gone in ("extra_utilities/TODO_known_issues.md", "extra_utilities/docs/MAS_blueprint_proposal.md",
                     "extra_utilities/tests/smoke_test_pack_tools.py", "extra_utilities/tests/smoke_test_studio.py",
                     ".env", "workflow_settings/tool_settings.json", "CLAUDE.md"):
            check(gone not in files, f"[PACKAGE] {gone} is in the package")
        for need in ("studio/validate.py", "studio/package.py", "extra_utilities/tests/dry_run_topology.py",
                     "extra_utilities/scripts/topology_prompt_snapshot.py", "extra_utilities/prompt_pdf/bootstrap.py",
                     "extra_utilities/db_design/apply_schema.py", "web_app.py", "Dockerfile"):
            check(need in files, f"[PACKAGE] {need} is missing")
        req = files["requirements.txt"].decode("utf-8")
        check("qzx-test-package==1.0" in req and req.count("numpy") == (ROOT / "requirements.txt")
              .read_text(encoding="utf-8").count("numpy"), "[PACKAGE] the tool's requirements were not merged")
        dock = files["Dockerfile"].decode("utf-8")
        check("        libqzx-test \\" in dock
              and dock.index("libqzx-test") < dock.index("rm -rf /var/lib/apt/lists/*"),
              "[PACKAGE] the tool's apt.txt was not merged into the Dockerfile")
        env = files[".env.example"].decode("utf-8")
        check("QZX_TOOL_KEY=" in env and env.count("RHINO_COMPUTE_URL=") == 1,
              "[PACKAGE] .env.example lacks the tool's variable (or repeats one)")
        dep = files["DEPLOY.md"].decode("utf-8")
        check("# Deploying: Propeller Design Configurator" in dep and "`QZX_TOOL_KEY`" in dep
              and "`RHINO_COMPUTE_URL`" in dep and "{{" not in dep and "INVITE_CODE" in dep
              and "gh repo create propeller_design_configurator --private" in dep,
              "[PACKAGE] DEPLOY.md does not name the setup and its tools' variables")
        rd = files["README.md"].decode("utf-8")
        check(rd.startswith("# Propeller Design Configurator") and "{{" not in rd,
              "[PACKAGE] README.md does not name the setup")
        # 3. a planted key is listed, masked, and the download still works
        planted = "sk-proj-" + "A1b2C3d4" * 6
        f = tool / "render_blade_sections.py"
        f.write_bytes(f.read_bytes() + f"\nOPENAI_KEY = \"{planted}\"\n".encode("utf-8"))
        pv = st.call("download_preview", "setup")
        found = pv.get("findings") or []
        check(len(found) >= 1 and found[0]["file"].endswith("tools/render_blade_sections/render_blade_sections.py")
              and planted not in json.dumps(found) and found[0]["shown"].startswith("sk-p"),
              f"[SCAN] the planted key: {found}")
        status, _h, raw = st.get("/download/setup")
        check(status == 200 and planted.encode() in zip_files(raw)[
            "dc_pack/tools/render_blade_sections/render_blade_sections.py"],
              "[SCAN] the download is not possible once something looks like a key")
    finally:
        for p in (tool / "requirements.txt", tool / "apt.txt"):
            p.unlink(missing_ok=True)
        y.write_bytes(yraw)
        f = tool / "render_blade_sections.py"
        f.write_bytes((PACK / "tools" / "render_blade_sections" / "render_blade_sections.py").read_bytes())
    return f"package: {len(files)} files"


# ---------------------------------------------------------------------------
# 4. inside the package
# ---------------------------------------------------------------------------

def check_inside(st: Studio, tmp: Path) -> str:
    _s, _h, raw = st.get("/download/package")
    out = tmp / "unpacked"
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        z.extractall(out)
    folder = next(p for p in out.iterdir() if p.is_dir())
    env = dict(os.environ, DC_PACK_DIR="")
    proc = subprocess.run([sys.executable, "-m", "studio", "validate", "--json", str(tmp / "inside.json")],
                          cwd=str(folder), env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=1200)
    check(proc.returncode == 0, f"[INSIDE] Validate inside the package answered {proc.returncode}: "
                                f"{proc.stdout[-1500:]} {proc.stderr[-800:]}")
    rep = json.loads((tmp / "inside.json").read_text(encoding="utf-8")) if (tmp / "inside.json").is_file() else {}
    check(rep.get("pack_dir", "").replace("\\", "/").endswith("propeller_design_configurator/dc_pack"),
          f"[INSIDE] Validate did not check the package's own dc_pack: {rep.get('pack_dir')}")
    return f"inside the package: {rep.get('counts')}"


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="package_smoke_"))
    copy = tmp / "dc_pack"
    shutil.copytree(PACK, copy, ignore=shutil.ignore_patterns("__pycache__"))
    summary = []
    st = None
    try:
        st = Studio(copy)
        st.call("get_all")
        summary.append(_run(lambda: check_setup_file(st, copy), "[SETUP]"))
        summary.append(_run(lambda: check_package(st, copy, tmp), "[PACKAGE]"))
        summary.append(_run(lambda: check_inside(st, tmp), "[INSIDE]"))
    finally:
        if st is not None:
            st.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    print("; ".join(str(s) for s in summary))
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - the setup file is the setup and opens back byte for byte, a bad one is "
          "refused, the full package holds the engine, this setup and what is written for it, "
          "the key scan warns, and Validate passes inside the package.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
