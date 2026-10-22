"""Offline check of the downloads and Open setup file (MAS-blueprint P7-2,
``studio/package.py``).

1. THE SETUP FILE, from the Studio (``GET /download/setup``): the setup's
   files under ``setups/propeller/`` (the folder named after the
   configurator, as in the repository), byte for byte, and
   ``setup_info.json`` (the
   configurator, the engine, ``pack_format``, Validate not run).  Changed in
   the Studio, then opened again (``open_setup``): the setup is back byte for
   byte, nothing is listed as changed, Undo starts from it; a different
   setup file opened is the new start (nothing listed as changed).  A full package
   opens too (its ``setups/propeller/`` is taken).  Refused, writing
   nothing: not a zip, no ``setups/<name>/`` (the old ``dc_pack/`` layout
   among them), two setups in one file, a path out of the folder, a file
   name Windows cannot hold, a setup in a newer format, a parameter file the
   engine refuses.
2. THE FULL PACKAGE (``GET /download/package``): one folder holding the
   engine -- every file git has or would take in the engine's folders, and
   no other (no notes, docs, benchmarks or propeller-only checks, no
   Workflow Settings saved on this computer, no ``.env``) --, this setup in
   ``setups/propeller/``, ``README.md`` and ``DEPLOY.md`` naming the
   configurator, its folder and its tools' variables, ``.env.example`` with
   them, ``setup_info.json``.  Its ``.gitignore`` and ``.dockerignore`` are
   the repository's without the lines for the repository's own ``setups/``
   (which leave the vacuum hose adapter out): neither leaves the package's
   configurator out.
   A tool's own ``requirements.txt`` and ``apt.txt`` are merged into
   ``requirements.txt`` and the ``Dockerfile`` (a package the engine names
   kept as the engine has it, with a note).  The engine's files are the same
   found by git and by walking the folders.
3. THE KEY SCAN: nothing in the engine or the propeller's setup; a planted
   key in a tool is listed by ``download_preview`` with its file, line and a
   masked value, and the download still works.
4. INSIDE THE PACKAGE, unpacked into an empty folder: ``python -m studio
   validate`` finds no failure on its ``setups/propeller/`` -- the package
   holds all Validate needs -- and the app's main menu lists that one
   configurator, loaded.
5. PREPARE FOR GITHUB (P7-3, ``studio/prepare.py``), in that folder: outside
   a package, in the blueprint's own repository, and in a folder with two
   configurators in ``setups/``, it refuses and changes nothing; given the
   Validate report, it
   adds what ``.gitignore`` and ``.dockerignore`` miss (git then leaves logs
   and the saved Workflow Settings out), removes a line that leaves the
   package's configurator out, lists a key and a ``.env`` value
   planted in a file (``.env`` itself is ignored), leaves
   ``requirements.txt``, the ``Dockerfile`` and an edited ``README.md`` as
   they are, writes ``DEPLOY.md`` and ``setup_info.json`` again, and prints
   the first-time commands -- it never runs git (no ``.git`` appears).  A
   second run changes nothing in the ignore files; once ``.git/config``
   names a remote it prints a commit and a push instead; a Validate failure
   stops it before anything changes.  The merge of the tools' dependencies
   run again gives the same files, and with the tools' files gone gives the
   engine's own back.  The Studio's button: unavailable outside a package;
   inside one it asks for Validate first, then answers the same commands,
   and asks again once the setup changes.

Takes about five minutes.  Run from the repo root (naming groups runs only
those: ``setup``, ``package``, ``prepare`` -- the last with 4):
    py -3.13 extra_utilities/tests/smoke_test_package.py [setup] [package] [prepare]
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
PACK = ROOT / "setups" / "propeller"
# The setup's folder in the downloads (the configurator's name: propeller).
SP = "setups/propeller/"


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

    def __init__(self, pack_dir: Path, cwd: Path = ROOT):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "studio", "--pack", str(pack_dir), "--port", str(self.port),
             "--workers", "0"], cwd=str(cwd), env=dict(os.environ, DC_PACK_DIR=""),
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
    inside = {k[len(SP):]: v for k, v in files.items() if k.startswith(SP)}
    check(inside == before, f"[SETUP] the setup file is not the setup byte for byte: "
                            f"{sorted(set(inside) ^ set(before))[:5]}")
    check(set(files) == {"setup_info.json"} | {f"{SP}{r}" for r in before},
          f"[SETUP] other files in the setup file: {sorted(set(files) - {'setup_info.json'} - {f'{SP}{r}' for r in before})[:5]}")
    info = json.loads(files.get("setup_info.json", b"{}"))
    check(info.get("configurator") == "Propeller Design Configurator" and info.get("pack_format") == 1
          and info.get("validate") == {"status": "not run"} and info.get("made_by") == "MAS Studio"
          and info.get("engine"), f"[SETUP] setup_info.json: {info}")
    # The title is a text field the Studio edits (P8): a download right after
    # it is saved -- no page re-read between -- carries the new title.  Each
    # download is the first read after its own save: a read that builds the
    # data anew would hand the other one fresh data either way.
    d = st.call("get_all")["data"]
    t = next(x for x in d["slots"] if x["slot"] == "app_title")
    check(t.get("runtime") is True, f"[SETUP] $app_title is not shown as read by the app: {t.get('runtime')}")
    check(st.call("save_field", "app_title", None, {"all": "Qzx Planter Configurator"},
                  {"all": t["values"]["7"]})["ok"], "[SETUP] the title could not be saved")
    status, headers, raw2 = st.get("/download/setup")
    info2 = json.loads(zip_files(raw2).get("setup_info.json", b"{}"))
    check("qzx_planter_configurator_setup.zip" in headers.get("content-disposition", "")
          and info2.get("configurator") == "Qzx Planter Configurator",
          f"[SETUP] a download right after the title changed: {headers.get('content-disposition')} {info2}")
    check(st.call("save_field", "app_title", None, {"all": "Qzx Lamp Configurator"},
                  {"all": "Qzx Planter Configurator"})["ok"], "[SETUP] the title could not be saved again")
    preview = st.call("download_preview", "setup")
    check(preview.get("file") == "qzx_lamp_configurator_setup.zip",
          f"[SETUP] the download preview right after the title changed: {preview.get('file')}")
    st.call("undo_field", "app_title", None)
    check(snapshot(copy) == before, "[SETUP] the title's Undo did not put the setup back")
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
    other = {f"{SP}{k}": v for k, v in inside.items()}
    other[f"{SP}fragments/dc/dc_name.md"] = b"another name\n"
    r = st.call("open_setup", make_zip(other), "other.zip")
    d = st.call("get_all")["data"]
    check(r.get("ok") and d["changed"] == []
          and next(x for x in d["slots"] if x["slot"] == "dc_name")["values"]["7"] == "another name",
          f"[SETUP] a different setup file opened: listed as changed {d['changed'][:4]}, {str(r)[:200]}")
    r = st.call("open_setup", base64.b64encode(raw).decode("ascii"), "setup.zip")
    check(r.get("ok") and snapshot(copy) == before, "[SETUP] the first setup file did not open again")
    # a full package opens too (its setups/propeller/)
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
        "no setups/<name>/": (make_zip({"something/else.txt": b"x"}), "no setups/<name>/"),
        "the old dc_pack/ layout": (make_zip({f"dc_pack/{k}": v for k, v in inside.items()}),
                                    "no setups/<name>/"),
        "two setups in one file": (make_zip({f"{SP}pack.yaml": inside["pack.yaml"],
                                             "setups/other/pack.yaml": inside["pack.yaml"]}),
                                   "two setups in one file"),
        "a path out of the folder": (make_zip({f"{SP}pack.yaml": inside["pack.yaml"],
                                               f"{SP}../escape.txt": b"x"}), "not a path"),
        "a newer format": (make_zip({f"{SP}{k}": v for k, v in newer.items()}), "newer engine"),
        "a file name Windows cannot hold": (make_zip({f"{SP}pack.yaml": inside["pack.yaml"],
                                                      f"{SP}fragments/x:y.md": b"x"}), "not a path"),
        "a parameter file the engine refuses": (make_zip({f"{SP}{k}": v for k, v in bad_spec.items()}),
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
        # prepare's own reading of .gitignore files agrees with git, file for file
        took = set(K.files_git_takes(ROOT))
        listed = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others",
                                 "--exclude-standard"], capture_output=True).stdout.decode("utf-8")
        gitset = {r for r in listed.split("\0") if r and (ROOT / r).is_file()}
        check(took == gitset, f"[PACKAGE] the .gitignore reading differs from git: "
                              f"{sorted(took ^ gitset)[:6]}")
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
        want = engine | {f"{SP}{r}" for r in setup} | written
        check(set(files) == want, f"[PACKAGE] files: extra {sorted(set(files) - want)[:5]}, "
                                  f"missing {sorted(want - set(files))[:5]}")
        merged_or_filtered = {"requirements.txt", "Dockerfile", ".gitignore", ".dockerignore"}
        for rel in engine - merged_or_filtered:
            if files.get(rel) != (ROOT / rel).read_bytes():
                check(False, f"[PACKAGE] {rel} is not the engine's file")
                break
        check(all(files.get(f"{SP}{r}") == b for r, b in setup.items()),
              f"[PACKAGE] {SP} is not the setup byte for byte")
        # the ignore files: the repository's, without its own setups/ lines
        for rel in (".gitignore", ".dockerignore"):
            repo_text = (ROOT / rel).read_bytes().decode("utf-8")
            text = files[rel].decode("utf-8")
            check(text == K.drop_ignore_lines(repo_text, K._repo_setups_line)[0]
                  and len(text.splitlines()) < len(repo_text.splitlines())
                  and "setups/vacuum_hose_adapter" not in text and "the vacuum hose" not in text,
                  f"[PACKAGE] {rel} is not the repository's without its setups/ lines")
            rules, repo_rules = K.IgnoreRules(text), K.IgnoreRules(repo_text)
            check(not rules.ignored("setups/propeller", True) and not rules.ignored("setups/vacuum_hose_adapter", True)
                  and repo_rules.ignored("setups/vacuum_hose_adapter", True)
                  and rules.ignored("workspace", True) and rules.ignored("logs", True) == repo_rules.ignored("logs", True),
                  f"[PACKAGE] {rel} leaves a configurator out, or lost another line")
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
        setup_now = K.setup_files(copy)
        check("# for the tool render_blade_sections (setups/propeller/tools/render_blade_sections/"
              "requirements.txt)" in req, "[PACKAGE] the merged requirements do not name the tool's folder")
        again = K.merge_requirements(req, setup_now, SP[:-1])[0], K.merge_apt(dock, setup_now)[0]
        check(again == (req, dock), "[PACKAGE] merging the tools' dependencies again changes the files")
        no_tools = {r: q for r, q in setup_now.items() if not r.endswith(("/requirements.txt", "/apt.txt"))}
        back = K.merge_requirements(req, no_tools, SP[:-1])[0], K.merge_apt(dock, no_tools)[0]
        check(back == ((ROOT / "requirements.txt").read_bytes().decode("utf-8"),
                       (ROOT / "Dockerfile").read_bytes().decode("utf-8")),
              "[PACKAGE] with the tools' files gone, the merge does not give the engine's files back")
        dep = files["DEPLOY.md"].decode("utf-8")
        check("# Deploying: Propeller Design Configurator" in dep and "`QZX_TOOL_KEY`" in dep
              and "`RHINO_COMPUTE_URL`" in dep and "{{" not in dep and "INVITE_CODE" in dep
              and "gh repo create propeller_design_configurator --private" in dep
              and "opens the MAS Studio on `setups/propeller/`" in dep and "dc_pack" not in dep,
              "[PACKAGE] DEPLOY.md does not name the setup, its folder and its tools' variables")
        rd = files["README.md"].decode("utf-8")
        check(rd.startswith("# Propeller Design Configurator") and "{{" not in rd
              and "`setups/propeller/` is this configurator" in rd and "dc_pack" not in rd,
              "[PACKAGE] README.md does not name the setup and its folder")
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
            f"{SP}tools/render_blade_sections/render_blade_sections.py"],
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
    check(rep.get("pack_dir", "").replace("\\", "/").endswith("propeller_design_configurator/setups/propeller"),
          f"[INSIDE] Validate did not check the package's own setups/propeller: {rep.get('pack_dir')}")
    # the app's main menu in the package: its one configurator, loaded
    code = ("import json, web_app; from fastapi.testclient import TestClient; "
            "print(json.dumps(TestClient(web_app.app).get('/api/setups').json()))")
    menu_env = dict(env, ACTIVE_SETUP_FILE=str(tmp / "inside_active.json"), INVITE_CODE="")
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(folder), env=menu_env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=600)
    last = (proc.stdout.strip().splitlines() or ["{}"])[-1]
    try:
        menu = json.loads(last)
    except ValueError:
        menu = {}
    check([(s.get("setup"), s.get("loaded")) for s in menu.get("setups", [])] == [("propeller", True)],
          f"[INSIDE] the package's main menu: {last[:300]} {proc.stderr[-600:]}")
    return f"inside the package: {rep.get('counts')}"


# ---------------------------------------------------------------------------
# 5. Prepare for GitHub
# ---------------------------------------------------------------------------

def _prepare(folder: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "studio", "prepare", *args], cwd=str(folder),
                          env=dict(os.environ, DC_PACK_DIR=""), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=1200)


def _drop_line(path: Path, line: str) -> None:
    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(eol)
    assert line in lines, (path, line)
    path.write_bytes(eol.join(ln for ln in lines if ln != line).encode("utf-8"))


def check_prepare(st: Studio, tmp: Path) -> str:
    folder = next(p for p in (tmp / "unpacked").iterdir() if p.is_dir())
    report = str(tmp / "inside.json")
    # outside a package: a copy of it without setup_info.json -- never this
    # repository, which a broken guard would change
    outside = tmp / "outside" / folder.name
    shutil.copytree(folder, outside)
    (outside / "setup_info.json").unlink()
    before = snapshot(outside)
    r = _prepare(outside)
    check(r.returncode == 2 and "Download full package" in r.stderr and snapshot(outside) == before,
          f"[PREPARE] outside a package: {r.returncode} {r.stderr[-300:]}")
    # ...and a package that holds the blueprint's own docs is its repository
    (outside / "setup_info.json").write_bytes((folder / "setup_info.json").read_bytes())
    (outside / "extra_utilities" / "docs").mkdir(parents=True)
    before = snapshot(outside)
    r = _prepare(outside)
    check(r.returncode == 2 and "blueprint's own repository" in r.stderr and snapshot(outside) == before,
          f"[PREPARE] the blueprint's own repository: {r.returncode} {r.stderr[-300:]}")
    # ...and a folder with two configurators is not a package
    shutil.rmtree(outside / "extra_utilities" / "docs")
    shutil.copytree(outside / "setups" / "propeller", outside / "setups" / "another",
                    ignore=shutil.ignore_patterns("__pycache__"))
    before = snapshot(outside)
    r = _prepare(outside)
    check(r.returncode == 2 and "A package holds one configurator" in r.stderr and snapshot(outside) == before,
          f"[PREPARE] two configurators: {r.returncode} {r.stderr[-300:]}")
    shutil.rmtree(outside.parent, ignore_errors=True)
    d = st.call("get_all")["data"]
    check(d.get("prepare", {}).get("available") is False and "Download full package" in (d["prepare"].get("why") or ""),
          f"[PREPARE] the Studio's button outside a package: {d.get('prepare')}")
    # what must stay out, removed; a key and a .env value planted
    _drop_line(folder / ".gitignore", "logs/")
    _drop_line(folder / ".gitignore", "workflow_settings/tool_settings.json")
    _drop_line(folder / ".dockerignore", "workspace/")
    # ...and the package's own configurator, left out by hand
    for rel in (".gitignore", ".dockerignore"):
        f = folder / rel
        f.write_bytes(f.read_bytes() + b"# kept out by hand\nsetups/propeller/\n")
    value = "sk-qzx-planted-" + "9" * 24
    (folder / ".env").write_text(f"OPENAI_API_KEY={value}\n", encoding="utf-8")
    (folder / "notes.txt").write_text(f"the key: {value}\n", encoding="utf-8")
    (folder / "README.md").write_bytes((folder / "README.md").read_bytes() + b"\nMy own line.\n")
    kept = {n: (folder / n).read_bytes() for n in ("requirements.txt", "Dockerfile", "README.md")}
    r = _prepare(folder, "--report", report)
    out = r.stdout
    check(r.returncode == 0 and "Using the Validate report given" in r.stderr,
          f"[PREPARE] prepare answered {r.returncode}: {out[-800:]} {r.stderr[-400:]}")
    check(".gitignore: added logs/, workflow_settings/tool_settings.json" in out
          and ".dockerignore: added workspace/" in out, f"[PREPARE] the ignore files were not repaired: {out[:600]}")
    check(".gitignore: removed setups/propeller/ (it left setups/propeller/ out)" in out
          and ".dockerignore: removed setups/propeller/ (it left setups/propeller/ out)" in out,
          f"[PREPARE] the line leaving the configurator out was not removed: {out[:700]}")
    rules = K.IgnoreRules((folder / ".gitignore").read_text(encoding="utf-8"))
    check(rules.ignored("logs", True) and rules.ignored("workflow_settings/tool_settings.json")
          and rules.ignored(".env") and not rules.ignored(".env.example")
          and not rules.ignored("setups/propeller", True)
          and "# kept out by hand" not in (folder / ".dockerignore").read_text(encoding="utf-8"),
          "[PREPARE] after the repair, git would still take logs/ or the saved settings, or leave the "
          "configurator out")
    check("notes.txt:1  an OpenAI, Anthropic or OpenRouter key" in out
          and "notes.txt:1  the value of OPENAI_API_KEY in .env" in out and value not in out
          and "\n  .env:" not in out, f"[PREPARE] the key scan: {out[out.find('looks like a key'):][:500]}")
    check(all((folder / n).read_bytes() == b for n, b in kept.items()),
          "[PREPARE] requirements.txt, the Dockerfile or the edited README.md changed")
    info = json.loads((folder / "setup_info.json").read_text(encoding="utf-8"))
    check(info.get("prepared") and info.get("validate", {}).get("status") == "warn",
          f"[PREPARE] setup_info.json: {info}")
    check("python -m studio prepare" in (folder / "DEPLOY.md").read_text(encoding="utf-8"),
          "[PREPARE] DEPLOY.md does not name prepare")
    check("git init -b main" in out and "gh repo create propeller_design_configurator --private --source . --push" in out
          and "Nothing was committed: prepare never runs git" in out and not (folder / ".git").exists(),
          f"[PREPARE] the first-time commands: {out[out.find('Nothing was committed'):][:600]}")
    # again: nothing to repair
    r = _prepare(folder, "--report", report)
    check(r.returncode == 0 and "ignore: added" not in r.stdout and "ignore: removed" not in r.stdout,
          f"[PREPARE] a second run repaired again: {r.stdout[:400]}")
    # later: a repository with a remote
    (folder / ".git").mkdir()
    (folder / ".git" / "config").write_text('[core]\n\tbare = false\n[remote "origin"]\n\turl = https://example.invalid/x.git\n',
                                            encoding="utf-8")
    r = _prepare(folder, "--report", report)
    check(r.returncode == 0 and "git push" in r.stdout and "gh repo create" not in r.stdout
          and "git init" not in r.stdout, f"[PREPARE] once a remote exists: {r.stdout[-500:]}")
    # the Studio's button, in the package
    pst = Studio(folder / "setups" / "propeller", cwd=folder)
    try:
        pst.call("get_all")
        a = pst.call("prepare_run")
        check(a.get("ok") and a.get("needs_validate"), f"[PREPARE] the button before Validate: {str(a)[:300]}")
        pst.call("validate_start")
        deadline = time.time() + 1200
        while time.time() < deadline and pst.call("validate_state")["data"]["running"]:
            time.sleep(2)
        b = pst.call("prepare_run")
        res = b.get("result") or {}
        check(b.get("ok") and res.get("ok") and res.get("commands", {}).get("case") == "update"
              and any(s[1] == "git push" for s in res["commands"]["steps"]),
              f"[PREPARE] the button after Validate: {str(b)[:400]}")
        # a change to the setup makes that Validate out of date: asked for again
        f = folder / "setups" / "propeller" / "fragments" / "dc" / "dc_name.md"
        f.write_bytes(f.read_bytes() + b"\n")
        c = pst.call("prepare_run")
        check(c.get("ok") and c.get("needs_validate"),
              f"[PREPARE] the button with a Validate older than the setup: {str(c)[:300]}")
    finally:
        pst.stop()
    # a Validate failure stops it before anything changes
    _drop_line(folder / ".gitignore", "logs/")
    gi = (folder / ".gitignore").read_bytes()
    spec = json.loads((folder / "setups" / "propeller" / "parameters.json").read_text(encoding="utf-8"))
    spec["parameters"][0].update(min=10, max=5)
    (folder / "setups" / "propeller" / "parameters.json").write_text(json.dumps(spec), encoding="utf-8")
    r = _prepare(folder)
    check(r.returncode == 1 and "Validate found failures" in r.stdout and (folder / ".gitignore").read_bytes() == gi,
          f"[PREPARE] a Validate failure: {r.returncode} {r.stdout[-400:]}")
    return "prepare: repaired, scanned, commands printed, no git run"


def main(argv: list[str]) -> int:
    groups = set(argv) or {"setup", "package", "prepare"}
    # This repository is no package: prepare must never have run in it.
    check(not (ROOT / "setup_info.json").exists(),
          "[PREPARE] this repository has a setup_info.json at its root: prepare ran here")
    tmp = Path(tempfile.mkdtemp(prefix="package_smoke_"))
    copy = tmp / "dc_pack"
    shutil.copytree(PACK, copy, ignore=shutil.ignore_patterns("__pycache__"))
    summary = []
    st = None
    try:
        st = Studio(copy)
        st.call("get_all")
        if "setup" in groups:
            summary.append(_run(lambda: check_setup_file(st, copy), "[SETUP]"))
        if "package" in groups:
            summary.append(_run(lambda: check_package(st, copy, tmp), "[PACKAGE]"))
        if "prepare" in groups or not argv:
            summary.append(_run(lambda: check_inside(st, tmp), "[INSIDE]"))
        if "prepare" in groups:
            summary.append(_run(lambda: check_prepare(st, tmp), "[PREPARE]"))
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
    print("\nPASS - the setup file is the setup in setups/propeller/ and opens back byte for byte, a "
          "bad one (the old dc_pack/ layout among them) is refused, the full package holds the engine, "
          "this setup in setups/propeller/ -- kept in git and the image -- and what is written for it, "
          "the key scan warns, Validate passes inside the package and its menu lists the configurator, "
          "and prepare readies it for GitHub without running git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
