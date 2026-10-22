"""The Studio's web server (MAS-blueprint P5-P6: local mode).

Serves the page (``studio/web/``), the setup's pictures (``/pack/assets/``)
and answers the page's calls: ``POST /api/<name>`` with ``{"args": [...]}``
-> ``{"ok": true, ...}`` or ``{"ok": false, "error": "<sentence>"}``, the
studio UI kit's contract (the draft's mock bridge answered the same calls).

* ``get_all`` -- the setup as the engine reads and assembles it
  (``studio/engine_view.py``, child processes, a few seconds), kept until a
  file of the setup changes: each call compares the setup's fingerprint --
  every file's path, size and modification time -- with the one the data
  was built from.  The first build starts with the server.
* ``view`` -- the prompt viewer: one topology assembled under a choice of
  settings, with each agent's tools and the token counts (P5b).  Answered by
  a pool of engine processes that wait with the big libraries loaded and
  take one job each; kept per (fingerprint, choice), the 32 most recent.
  The three default views are made right after the first build.
* the editing calls (P6a) -- ``save_field``, ``unlink_field``,
  ``link_field``, ``own_copy``, ``remove_copy``, ``undo_field``
  (``studio/editing.py``), on the setup's own files -- and ``diff``: a view
  compared with the same view of the setup as the Studio OPENED it (a copy
  taken when the server starts, also what Undo restores).
* the parameter editor (P6b, ``studio/params_edit.py``) --
  ``preview_parameters`` / ``save_parameters`` / ``undo_parameters``,
  ``csv_parameters``, ``upload_picture`` / ``drop_pictures``, and the
  access grid's ``set_access`` / ``undo_access``.  A new parameter file is
  checked by the engine's own validator, in one engine process that stays
  (``python -m studio.engine_view checker``).
* the tool editor (P6c, ``studio/tools_edit.py``) -- ``tool_file``,
  ``save_manifest``, ``save_tool_file``, ``upload_tool_file``,
  ``undo_tool_file``, ``undo_tool``, ``remove_tool_preview``,
  ``remove_tool``, ``new_tool`` (a template or a copy) and ``test_tool``
  (one run, ``engine/tool_test.py``, in a process of its own).  A change that could stop the engine loading the tools is
  checked first by the engine's own check, on a throw-away copy of the
  setup (in the same engine process).
* the primer (``studio/primer_edit.py``) -- ``set_primer_agent`` (who
  gets it, per topology), ``primer_picture`` (a PNG, JPEG or WebP, stored
  as a PNG), ``remove_primer_picture`` and ``undo_primer``; its text is a
  text field.
* a tool from an OpenSCAD model (P6f, ``studio/scad_import.py``) --
  ``scad_read`` (the model's settings and what each is proposed as),
  ``scad_import`` (a new configurator, or one more tool; checked first by
  the engine's check of a whole setup) and ``scad_undo``.  While an import
  can be undone, ``undo_parameters`` is refused: the import's Undo puts
  the parameters back together with its tools.
* ``validate_start`` / ``validate_state`` -- Validate (P7,
  ``studio/validate.py``): one run at a time, in a thread of its own, its
  progress and its last report, and whether the setup is still as it was
  when that run started.
* the downloads (P7-2, ``studio/package.py``) -- ``download_preview`` (what a
  download holds, the key scan, Validate's last result), ``GET
  /download/setup`` and ``GET /download/package`` (the zip); and
  ``open_setup``: a setup file replaces the setup, once the engine's check
  takes it, and the Studio starts again from it (Undo, the prompt diff).
* ``prepare_run`` -- Prepare for GitHub (P7-3, ``studio/prepare.py``), in a
  folder made by Download full package: it checks and fixes the folder and
  answers the git commands; it never runs git.

**Online** (P7b-lite, ``python -m studio --online``): one shared setup for
everyone who has the access code (:class:`Access`: ``INVITE_CODE``, asked
once per browser and kept in a signed cookie; every call but the page, its
scripts, ``session``, ``auth`` and ``config`` needs it), and ``start_from``:
the setup replaced by one of the configurators -- every one of the
repository's ``setups/``, and the example it started from when that lies
elsewhere (``--pack``).

This process never imports the engine: the assembler stubs runtime
packages (FastAPI among them) in the process that runs it.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import difflib
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
from fastapi.staticfiles import StaticFiles

from studio import editing, engine_view, params_edit, primer_edit, scad_import, tools_edit
from studio import package as packaging
from studio import prepare as preparing
from studio import validate as validation

WEB = Path(__file__).resolve().parent / "web"


def fingerprint(pack_dir: Path) -> str:
    """Every file of the setup -- path, size, modification time -- hashed.
    Python's ``__pycache__`` folders are left out (running a tool writes
    them)."""
    h = hashlib.sha256()
    for p in sorted(pack_dir.rglob("*")):
        if "__pycache__" in p.parts or not p.is_file():
            continue
        st = p.stat()
        h.update(f"{p.relative_to(pack_dir).as_posix()}\0{st.st_size}\0{st.st_mtime_ns}\n"
                 .encode("utf-8"))
    return h.hexdigest()


class PackView:
    """The Studio's data for one setup folder, rebuilt when it changes."""

    def __init__(self, pack_dir: Path, build=engine_view.build):
        self.pack_dir = pack_dir
        self._build = build
        self._lock = threading.Lock()
        self._data: dict | None = None
        self._data_fp: str | None = None
        self._pending: tuple[str, Future] | None = None
        self.builds = 0

    def get(self) -> dict:
        """The data for the setup as it is now."""
        return self.get_with_fingerprint()[0]

    def latest(self) -> dict:
        """The last data built, without waiting for a rebuild (what the
        editing calls need -- folders, names, the roster -- does not change
        with a text edit); the first build when there is none yet."""
        with self._lock:
            if self._data is not None:
                return self._data
        return self.get()

    def get_with_fingerprint(self) -> tuple[dict, str]:
        """The data for the setup as it is now, and the fingerprint it was
        built for: the kept copy, or a build (one at a time; callers that
        arrive meanwhile wait for it)."""
        fp = fingerprint(self.pack_dir)
        with self._lock:
            if self._data is not None and self._data_fp == fp:
                return self._data, fp
            if self._pending is None or self._pending[0] != fp:
                fut: Future = Future()
                self._pending = (fp, fut)
                threading.Thread(target=self._run, args=(fp, fut), daemon=True).start()
            fut = self._pending[1]
        return fut.result(), fp

    def _run(self, fp: str, fut: Future) -> None:
        try:
            data = self._build(self.pack_dir)
        except BaseException as exc:  # noqa: BLE001 -- handed to the callers
            with self._lock:
                if self._pending is not None and self._pending[1] is fut:
                    self._pending = None          # the next call tries again
            fut.set_exception(exc)
            return
        with self._lock:
            self.builds += 1
            # Keyed by the fingerprint taken BEFORE the build: a file
            # changed meanwhile makes the next call build again.
            self._data, self._data_fp = data, fp
            if self._pending is not None and self._pending[1] is fut:
                self._pending = None
        fut.set_result(data)


class WorkerPool:
    """Engine processes waiting for one view each (``python -m
    studio.engine_view worker``): each has loaded the big libraries while it
    waited, takes ONE job and ends, and the pool starts another.  When none
    is waiting, a job starts a process of its own."""

    def __init__(self, pack_dir: Path, size: int = 2):
        self.pack_dir = pack_dir
        self.size = size
        self._idle: list[subprocess.Popen] = []
        self._lock = threading.Lock()
        self._closed = False
        self.started = 0

    def _spawn(self) -> subprocess.Popen:
        env = dict(os.environ, PYTHONIOENCODING="utf-8", DC_PACK_DIR=str(self.pack_dir),
                   # Building a team must never reach a database; a model key
                   # must exist for the agents to be built (nothing is sent).
                   DATABASE_URL="", DATABASE_PUBLIC_URL="")
        env.setdefault("OPENAI_API_KEY", "sk-dummy")
        self.started += 1
        return subprocess.Popen([sys.executable, "-m", "studio.engine_view", "worker"],
                                cwd=str(engine_view.REPO), env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def fill(self) -> None:
        """Start workers until *size* are waiting."""
        with self._lock:
            if self._closed:
                return
            self._idle = [p for p in self._idle if p.poll() is None]
            while len(self._idle) < self.size:
                self._idle.append(self._spawn())

    def run(self, choice: dict, timeout: float = 300,
            pack_dir: Path | None = None) -> tuple[dict, bool]:
        """The view of *choice* (of the setup in *pack_dir*, default the
        pool's), and whether a waiting worker answered it."""
        with self._lock:
            proc = None
            while self._idle and proc is None:
                p = self._idle.pop(0)
                if p.poll() is None:
                    proc = p
            pooled = proc is not None
            if proc is None:
                proc = self._spawn()
        threading.Thread(target=self.fill, daemon=True).start()
        try:
            job = dict(choice, pack_dir=str(pack_dir)) if pack_dir else choice
            out, err = proc.communicate((json.dumps(job) + "\n").encode("utf-8"),
                                        timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError(f"the view took longer than {timeout:g} s") from None
        if proc.returncode != 0:
            raise RuntimeError(err.decode("utf-8", "replace").strip()[-3000:] or "no output")
        return json.loads(out.decode("utf-8")), pooled

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for p in self._idle:
                p.kill()
            self._idle = []


class Checker:
    """One engine process that answers parameter checks
    (``python -m studio.engine_view checker``), started when first needed
    and again if it ends."""

    def __init__(self, pack_dir: Path):
        self.pack_dir = pack_dir
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def _start(self) -> subprocess.Popen:
        env = dict(os.environ, PYTHONIOENCODING="utf-8", DC_PACK_DIR=str(self.pack_dir),
                   DATABASE_URL="", DATABASE_PUBLIC_URL="")
        env.setdefault("OPENAI_API_KEY", "sk-dummy")
        return subprocess.Popen([sys.executable, "-m", "studio.engine_view", "checker"],
                                cwd=str(engine_view.REPO), env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def check(self, spec: dict) -> list[str]:
        """The engine's check of a parameter file."""
        return self.ask({"parameters": spec})

    def check_tools(self, pack_copy: Path) -> list[str]:
        """The engine's check of the tools of a setup copy."""
        return self.ask({"tools_check": str(pack_copy)})

    def check_setup(self, pack_copy: Path) -> list[str]:
        """The engine's check of a whole setup copy (a setup file opened)."""
        return self.ask({"setup_check": str(pack_copy)})

    def ask(self, job: dict) -> list[str]:
        line = (json.dumps(job) + "\n").encode("utf-8")
        with self._lock:
            for attempt in (1, 2):
                if self._proc is None or self._proc.poll() is not None:
                    self._proc = self._start()
                try:
                    self._proc.stdin.write(line)
                    self._proc.stdin.flush()
                    answer = self._proc.stdout.readline()
                    if answer:
                        return json.loads(answer.decode("utf-8"))["problems"]
                except (OSError, ValueError):
                    pass
                self._proc.kill()
                self._proc = None
        raise RuntimeError("the engine's check did not answer")

    def close(self) -> None:
        with self._lock:
            if self._proc is not None:
                self._proc.kill()
                self._proc = None


_ENCODING = None


def count_tokens(text: str) -> int:
    """Tokens of *text* under tiktoken's ``cl100k_base`` -- the engine's own
    counter (``agents/database_handler/token_utils.py``), counted here
    because the engine processes stub tiktoken; without it, the same
    fallback (characters / 4, rounded up)."""
    global _ENCODING
    if not text:
        return 0
    if _ENCODING is None:
        try:
            import tiktoken
            _ENCODING = tiktoken.get_encoding("cl100k_base")
        except Exception:  # noqa: BLE001
            _ENCODING = False
    if _ENCODING:
        return len(_ENCODING.encode(text))
    return max(1, (len(text) + 3) // 4)


def tool_text(tool: dict) -> str:
    """A tool as the model is sent it: name, description, argument schema."""
    return json.dumps({"name": tool["name"], "description": tool["description"],
                       "parameters": tool["args"]}, ensure_ascii=False, sort_keys=True)


class ViewCache:
    """Views kept per (setup fingerprint, choice), the *size* most recent;
    one job per view at a time (callers that arrive meanwhile wait)."""

    def __init__(self, pool: WorkerPool, size: int = 32):
        self.pool = pool
        self.size = size
        self._lock = threading.Lock()
        self._done: OrderedDict = OrderedDict()
        self._pending: dict = {}
        self.jobs = 0

    def get(self, fp: str, choice: dict, pack_dir: Path | None = None) -> dict:
        """The view of *choice* for the setup whose fingerprint is *fp*
        (*pack_dir*: another copy than the pool's)."""
        key = (fp, json.dumps(choice, sort_keys=True))
        with self._lock:
            if key in self._done:
                self._done.move_to_end(key)
                return self._done[key]
            fut = self._pending.get(key)
            if fut is None:
                fut = Future()
                self._pending[key] = fut
                threading.Thread(target=self._run, args=(key, choice, fut, pack_dir),
                                 daemon=True).start()
        return fut.result()

    def _run(self, key, choice: dict, fut: Future, pack_dir: Path | None = None) -> None:
        try:
            data, pooled = self.pool.run(choice, pack_dir=pack_dir)
            data["tokens"] = {a: count_tokens(t) for a, t in data["prompts"].items()}
            for p in (data.get("primer") or {}).values():
                p["text_tokens"] = count_tokens(p["text"])
            for tools in data["tools"].values():
                for t in tools:
                    t["tokens"] = count_tokens(tool_text(t))
            data.update(choice=choice, pooled=pooled)
        except BaseException as exc:  # noqa: BLE001 -- handed to the callers
            with self._lock:
                self._pending.pop(key, None)
            fut.set_exception(exc)
            return
        with self._lock:
            self.jobs += 1
            self._done[key] = data
            while len(self._done) > self.size:
                self._done.popitem(last=False)
            self._pending.pop(key, None)
        fut.set_result(data)


ACCESS_COOKIE = "studio_access"
ACCESS_DAYS = 30
# What the page needs before its access code is typed.
OPEN_PATHS = {"/", "/api/session", "/api/auth", "/api/config"}


class Access:
    """The online Studio's way in: one access code (``INVITE_CODE``), the
    propeller app's check (compared in constant time), remembered per
    browser in a cookie signed with *secret* (``STUDIO_SECRET``, else a
    random one per process: a restart asks for the code again)."""

    def __init__(self, code: str, secret: bytes | None = None):
        self.code = code
        self.secret = secret or os.urandom(32)

    def check_code(self, submitted) -> bool:
        return isinstance(submitted, str) and hmac.compare_digest(
            submitted.strip().encode("utf-8"), self.code.encode("utf-8"))

    def _sign(self, issued: str) -> str:
        return hmac.new(self.secret, issued.encode("ascii"), hashlib.sha256).hexdigest()

    def token(self) -> str:
        issued = str(int(time.time()))
        return f"{issued}.{self._sign(issued)}"

    def valid(self, token) -> bool:
        if not isinstance(token, str) or "." not in token:
            return False
        issued, sig = token.split(".", 1)
        if not issued.isdigit() or not hmac.compare_digest(sig, self._sign(issued)):
            return False
        return time.time() - int(issued) < ACCESS_DAYS * 86400


class Validation:
    """Validate (``studio/validate.py``) in a thread of its own: one run at
    a time, its progress, its last report."""

    def __init__(self, pack_dir: Path, run=validation.run):
        self.pack_dir = pack_dir
        self._run_fn = run
        self._lock = threading.Lock()
        self.running = False
        self.done = self.total = 0
        self.items: list = []
        self.report: dict | None = None
        self.error: str | None = None

    def start(self) -> dict:
        with self._lock:
            if not self.running:
                self.running, self.done, self.total, self.items, self.error = True, 0, 0, [], None
                threading.Thread(target=self._run, daemon=True).start()
        return self.state()

    def _progress(self, done: int, total: int, items: list) -> None:
        with self._lock:
            self.done, self.total, self.items = done, total, items

    def _run(self) -> None:
        try:
            report = self._run_fn(self.pack_dir, progress=self._progress)
            with self._lock:
                self.report = report
        except Exception as exc:  # noqa: BLE001 -- shown on the page
            with self._lock:
                self.error = f"Validate could not run: {type(exc).__name__}: {exc}"
        finally:
            with self._lock:
                self.running = False

    def state(self) -> dict:
        """``running``, ``done`` / ``total`` checks, the ``items`` ended so
        far, the last ``report`` and whether it is ``current`` (the setup's
        files as they were when it started)."""
        fp = fingerprint(self.pack_dir)
        with self._lock:
            return {"running": self.running, "done": self.done, "total": self.total,
                    "items": list(self.items) if self.running else [],
                    "report": self.report, "error": self.error,
                    "current": bool(self.report) and self.report["fingerprint"] == fp}


def _ok(**kw) -> JSONResponse:
    return JSONResponse(dict(kw, ok=True))


def _fail(error: str, status: int = 200) -> JSONResponse:
    return JSONResponse({"ok": False, "error": error}, status_code=status)


def prompt_diff(before: str, after: str) -> list[list[str]]:
    """Line diff: ``[["=" | "-" | "+", line], ...]``."""
    a, b = before.split("\n"), after.split("\n")
    out: list[list[str]] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out += [["=", ln] for ln in a[i1:i2]]
        else:
            out += [["-", ln] for ln in a[i1:i2]] + [["+", ln] for ln in b[j1:j2]]
    return out


def _configurator(url: str | None, example_dir: Path | None, menu: bool = False) -> dict | None:
    """The configurator the Studio links to: ``{url, name}`` -- the name is
    the example setup's (the live configurator runs it: "propeller"), None
    when the example does not say it in one file -- or, *menu*, the main
    menu of the app the Studio is inside (``{url, name: None, menu: True}``);
    None without a URL."""
    if not url:
        return None
    if menu:
        return {"url": url, "name": None, "menu": True}
    name = None
    if example_dir is not None:
        f = example_dir / "fragments" / "dc" / "dc_name.md"
        if f.is_file():
            name = f.read_text(encoding="utf-8").strip() or None
    return {"url": url, "name": name}


def _setup_title(folder: Path) -> str:
    """A setup's title: its ``$app_title`` text, else ``$dc_name``, else its
    folder's name."""
    for slot in ("app_title", "dc_name"):
        try:
            text = " ".join((folder / "fragments" / "dc" / f"{slot}.md").read_text(encoding="utf-8").split())
        except OSError:
            continue
        if text:
            return text
    return folder.name


def _start_points(example_dir: Path | None) -> list[tuple[str, Path]]:
    """What the shared setup can start from (online): every configurator of
    the repository's ``setups/`` -- and first, the example it started from
    when that lies elsewhere (``--pack``) -- as (key, folder)."""
    if example_dir is None:
        return []
    from engine.setups import all_setups
    found = [(p.name, p) for p in all_setups(engine_view.REPO)]
    if example_dir.resolve() not in {p.resolve() for _key, p in found}:
        found.insert(0, ("--pack", example_dir))
    return found


def create_app(pack_dir: Path, workers: int = 2, online: bool = False,
               access_code: str | None = None, example_dir: Path | None = None,
               configurator_url: str | None = None, require_code: bool = True,
               configurator_menu: bool = False) -> FastAPI:
    """The Studio for the setup in *pack_dir*.  *online*: behind
    *access_code* (required unless *require_code* is false: the Studio
    inside the configurator's server, ``studio/embedded.py``, is open when
    the configurator is), with ``start_from`` (:func:`_start_points`, from
    *example_dir*) and a link to the configurator at *configurator_url* --
    the app's main menu when *configurator_menu* -- on the landing page and
    on the access-code page, before the code."""
    if online and not access_code and require_code:
        raise ValueError("the online Studio needs an access code")
    configurator = _configurator(configurator_url, example_dir, configurator_menu)
    access = (Access(access_code, (os.getenv("STUDIO_SECRET") or "").encode("utf-8") or None)
              if online and access_code else None)
    view = PackView(pack_dir)
    pool = WorkerPool(pack_dir, size=workers)
    views = ViewCache(pool)
    # The setup as the Studio opened it: Undo restores from it, the prompt
    # diff compares with it.
    opened_root = Path(tempfile.mkdtemp(prefix="studio_opened_"))
    opened_dir = editing.copy_setup(pack_dir, opened_root / pack_dir.name)
    # Its views are kept under a key of their own: a copy keeps the files'
    # times, so its fingerprint is the setup's at opening -- and a default
    # view still being made when the first edit lands is kept under that.
    opened_key = "opened:" + fingerprint(opened_dir)
    editor = editing.Editor(pack_dir, opened_dir)
    checker = Checker(pack_dir)
    params = params_edit.ParamsEditor(pack_dir, opened_dir, checker.check)
    tools = tools_edit.ToolsEditor(pack_dir, opened_dir, checker.check_tools, engine_view.REPO)
    primer = primer_edit.PrimerEditor(pack_dir, opened_dir)
    importer = scad_import.Importer(pack_dir, opened_dir, checker.check_setup, params, tools)
    changed_cache: dict = {}
    validator = Validation(pack_dir)
    open_lock = threading.Lock()
    # Prepare for GitHub works in a folder made by Download full package.
    prepare_why = ("Online, Prepare for GitHub is not here: download the full package and run "
                   "python -m studio prepare in it, on your computer." if online
                   else preparing.check_folder(engine_view.REPO, pack_dir))

    def changed(data: dict, fp: str) -> dict:
        """The changed fields and files, and the parameter editor's state."""
        if fp not in changed_cache:
            changed_cache.clear()
            changed_cache[fp] = {"changed": editor.changed(data) + params.changed() + tools.changed()
                                 + primer.changed(),
                                 "params_edit": params.state(data),
                                 "primer_edit": primer.state(data),
                                 "tools_edit": tools.state(data),
                                 "prepare": {"available": prepare_why is None, "why": prepare_why},
                                 "online": online, "configurator": configurator,
                                 "starts": [{"key": key, "title": _setup_title(p),
                                             "folder": (p.name if key == "--pack"
                                                        else f"setups/{p.name}")}
                                            for key, p in _start_points(example_dir)],
                                 "scad_import": importer.state()}
        return changed_cache[fp]

    def first_build() -> None:
        # The data, then the three default views (the prompt viewer opens on
        # one of them).
        data, fp = view.get_with_fingerprint()
        pool.fill()
        for n in engine_view.TOPOLOGIES:
            views.get(fp, engine_view.canonical_choice({"topology": n}, data))

    @asynccontextmanager
    async def lifespan(app):
        threading.Thread(target=lambda: _quiet(first_build), daemon=True).start()
        yield
        pool.close()
        checker.close()
        importer.close()
        shutil.rmtree(opened_root, ignore_errors=True)

    app = FastAPI(title="MAS Studio", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.view = view
    app.state.pool = pool
    app.state.views = views
    app.state.editor = editor
    app.state.params = params
    app.state.tools = tools
    app.state.importer = importer
    app.state.validator = validator

    def own_path(request: Request) -> str:
        # The path below where the Studio is served: inside the
        # configurator's server it is mounted at /studio (studio/embedded.py).
        path, root = request.url.path, request.scope.get("root_path") or ""
        return (path[len(root):] or "/") if root and path.startswith(root) else path

    @app.middleware("http")
    async def access_gate(request: Request, call_next):
        # Online, every call but the page, its scripts and the way in needs
        # the access code's cookie.
        path = own_path(request)
        if (access is not None and path not in OPEN_PATHS and not path.startswith("/static/")
                and not access.valid(request.cookies.get(ACCESS_COOKIE))):
            return JSONResponse({"ok": False, "auth": True, "error": "Type the access code first."},
                                status_code=401)
        return await call_next(request)

    @app.middleware("http")
    async def no_stale_page(request: Request, call_next):
        # The page and its scripts change with the Studio: always revalidate.
        response = await call_next(request)
        if not own_path(request).startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/")
    async def index():
        return FileResponse(WEB / "index.html")

    @app.get("/api/config")
    async def health():
        # What a platform's health check asks for (the Dockerfile's HEALTHCHECK).
        return _ok(app="MAS Studio", online=online)

    @app.post("/api/session")
    async def session(request: Request):
        # The configurator's link too: the access-code page offers it.
        return _ok(online=online, authed=access is None
                   or access.valid(request.cookies.get(ACCESS_COOKIE)),
                   configurator=configurator)

    @app.post("/api/auth")
    async def auth(request: Request):
        if access is None:
            return _ok()
        args = await _args(request)
        if not access.check_code(args[0] if args else None):
            await asyncio.sleep(0.5)                  # a guess at a time
            return _fail("The access code did not match.", 401)
        response = _ok()
        secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
        response.set_cookie(ACCESS_COOKIE, access.token(), max_age=ACCESS_DAYS * 86400,
                            httponly=True, samesite="lax", secure=secure)
        return response

    @app.post("/api/get_all")
    async def get_all():
        try:
            data, fp = await asyncio.to_thread(view.get_with_fingerprint)
            data = dict(data, **await asyncio.to_thread(changed, data, fp))
        except Exception as exc:  # noqa: BLE001
            return _fail(f"The engine could not assemble this setup: {exc}")
        return _ok(data=data)

    async def _args(request: Request) -> list:
        try:
            return list((await request.json()).get("args") or [])
        except Exception:  # noqa: BLE001
            return []

    def _edit(fn):
        """An editing call: ``fn(data, *args)`` on the latest data, answering
        its dict (or its warnings); refusals answer ``{ok: false, error,
        problems, conflict}``."""
        async def endpoint(request: Request):
            args = await _args(request)
            try:
                data = await asyncio.to_thread(view.latest)
                result = await asyncio.to_thread(fn, data, *args)
            except editing.EditError as exc:
                return JSONResponse({"ok": False, "error": str(exc), "problems": exc.problems,
                                     "conflict": isinstance(exc, editing.Conflict)})
            except TypeError as exc:
                return _fail(f"Wrong arguments: {exc}")
            except Exception as exc:  # noqa: BLE001 -- answered, never a bare 500
                return _fail(f"The Studio could not do this: {type(exc).__name__}: {exc}")
            if isinstance(result, dict):
                return _ok(**result)
            return _ok(warnings=result or [])
        return endpoint

    def undo_field(data: dict, slot: str, agent=None):
        # A parameter list put back as opened is brought in step with the
        # parameters as they are now.
        warnings = editor.undo(data, slot, agent)
        if slot == params_edit.LIST_SLOT:
            params.sync_lists(data)
        return warnings

    def undo_parameters(data: dict):
        if importer.state() is not None:
            raise editing.EditError("An import put these parameters in: undo it with Undo the import "
                                    "(it puts its tools back too).")
        return params.undo_all(data)

    def csv_parameters(data: dict, text: str):
        _raw, spec = params._spec(pack_dir)
        new, problems = params_edit.from_csv(str(text), spec)
        return {"spec": new, "problems": problems}

    def _download(data: dict, kind: str):
        """(file name, its files, the dependency notes, its folder, setup_info)."""
        if kind not in ("setup", "package"):
            raise editing.EditError(f"There is no {kind!r} download.")
        pk = data.get("pack") or {}
        name, title, dc = packaging.names(pack_dir, pk.get("title") or pk.get("name"))
        folder = packaging.setup_folder(pk.get("name"))
        info = packaging.setup_info(pack_dir, dc, validator.state())
        if kind == "setup":
            return f"{name}_setup.zip", packaging.setup_contents(pack_dir, info, folder), [], None, info
        files, notes = packaging.package_contents(pack_dir, name, title, dc, info, engine_view.REPO,
                                                  folder=folder)
        return f"{name}_package.zip", files, notes, name, info

    def download_preview(data: dict, kind: str) -> dict:
        # the setup as it is now: its title ($app_title, P8) names the files
        fname, files, notes, _folder, info = _download(view.get(), kind)
        return {"file": fname, "files": len(files), "bytes": sum(len(v) for v in files.values()),
                "findings": packaging.scan(files), "notes": notes, "validate": info["validate"],
                "engine": info["engine"]}

    def open_setup(data: dict, b64, filename=None) -> dict:
        try:
            raw = base64.b64decode(str(b64), validate=True)
        except (binascii.Error, ValueError):
            raise editing.EditError("The file did not arrive whole.") from None
        try:
            files, info = packaging.read_setup_file(raw)
        except packaging.PackageError as exc:
            raise editing.EditError(str(exc), exc.problems) from None
        return _replace_with(files, info, filename)

    def start_from(data: dict, key=None, word=None) -> dict:
        points = dict(_start_points(example_dir))
        if not points:
            raise editing.EditError("This Studio has no configurator to start from.")
        if key not in points:
            raise editing.EditError("There is no such configurator to start from.")
        if word != "replace":
            raise editing.EditError("Type replace to confirm: it replaces the setup for everyone.")
        files = {rel: p.read_bytes() for rel, p in packaging.setup_files(points[key]).items()}
        return _replace_with(files, None, _setup_title(points[key]))

    def _replace_with(files: dict, info, filename) -> dict:
        """The setup becomes *files*, once the engine's check takes them,
        and the Studio starts again from it."""
        nonlocal opened_key
        with open_lock:
            if validator.state()["running"]:
                raise editing.EditError("Validate is running: open the file once it has finished.")
            stage_root = Path(tempfile.mkdtemp(prefix="studio_open_"))
            try:
                stage = stage_root / pack_dir.name
                packaging.replace_setup(stage, files)
                problems = checker.check_setup(stage)
                if problems:
                    raise editing.EditError("This setup file cannot be opened.", problems)
                packaging.replace_setup(pack_dir, files)
            finally:
                shutil.rmtree(stage_root, ignore_errors=True)
            # The Studio starts again from it: Undo and the prompt diff.
            shutil.rmtree(opened_dir, ignore_errors=True)
            editing.copy_setup(pack_dir, opened_dir)
            opened_key = "opened:" + fingerprint(opened_dir)
            params.since_opened = {}
            importer.forget()
            changed_cache.clear()
        warnings = []
        made, here = str((info or {}).get("engine") or ""), packaging.engine_version()
        if made and made != "unknown" and here != "unknown" and made.split("+")[0] != here.split("+")[0]:
            warnings.append(f"It was made with engine {made}; this Studio runs {here}.")
        return {"file": filename, "files": len(files), "info": info, "warnings": warnings}

    def prepare_run(data: dict) -> dict:
        if prepare_why:
            raise editing.EditError(prepare_why)
        state = validator.state()
        if state["running"]:
            raise editing.EditError("Validate is running: prepare once it has finished.")
        if not (state["report"] and state["current"]):
            return {"needs_validate": True}
        return {"result": preparing.run(engine_view.REPO, state["report"])}

    for name, fn in (("save_field", editor.save), ("unlink_field", editor.unlink),
                     ("link_field", editor.link), ("own_copy", editor.own_copy),
                     ("remove_copy", editor.remove_copy), ("undo_field", undo_field),
                     ("preview_parameters", params.preview), ("save_parameters", params.save),
                     ("undo_parameters", undo_parameters), ("csv_parameters", csv_parameters),
                     ("upload_picture", params.upload_picture),
                     ("drop_pictures", params.drop_unused_pictures),
                     ("set_access", params.set_access), ("undo_access", params.undo_access),
                     ("set_primer_agent", primer.set_agent), ("primer_picture", primer.set_picture),
                     ("remove_primer_picture", primer.remove_picture), ("undo_primer", primer.undo),
                     ("tool_file", tools.read_file), ("save_manifest", tools.save_manifest),
                     ("save_tool_file", tools.save_file), ("upload_tool_file", tools.upload_file),
                     ("undo_tool_file", tools.undo_file), ("undo_tool", tools.undo_tool),
                     ("remove_tool_preview", tools.remove_preview), ("remove_tool", tools.remove_tool),
                     ("new_tool", tools.new_tool), ("test_tool", tools.test_tool),
                     ("scad_read", importer.read), ("scad_import", importer.run),
                     ("scad_undo", importer.undo),
                     ("download_preview", download_preview), ("open_setup", open_setup),
                     ("prepare_run", prepare_run), ("start_from", start_from)):
        app.add_api_route(f"/api/{name}", _edit(fn), methods=["POST"])

    @app.get("/download/{kind}")
    async def download(kind: str):
        if kind not in ("setup", "package"):
            return _fail(f"There is no {kind} download.", 404)
        try:
            # the data of the setup as it is now, not the last built: a
            # text field ($app_title) names the download (P8)
            data = await asyncio.to_thread(view.get)
            fname, files, _notes, folder, _info = await asyncio.to_thread(_download, data, kind)
            tmp = Path(tempfile.mkdtemp(prefix="studio_download_"))
            path = await asyncio.to_thread(packaging.write_zip, files, tmp / fname, folder)
        except Exception as exc:  # noqa: BLE001
            return _fail(f"The download could not be made: {type(exc).__name__}: {exc}")
        return FileResponse(path, filename=fname, media_type="application/zip",
                            background=BackgroundTask(shutil.rmtree, tmp, True))

    @app.post("/api/validate_start")
    async def validate_start():
        return _ok(data=await asyncio.to_thread(validator.start))

    @app.post("/api/validate_state")
    async def validate_state():
        return _ok(data=await asyncio.to_thread(validator.state))

    @app.post("/api/diff")
    async def api_diff(request: Request):
        args = await _args(request)
        try:
            data, fp = await asyncio.to_thread(view.get_with_fingerprint)
            choice = engine_view.canonical_choice(args[0] if args else {}, data)
            now, then = await asyncio.gather(
                asyncio.to_thread(views.get, fp, choice),
                asyncio.to_thread(views.get, opened_key, choice, opened_dir))
        except engine_view.ChoiceError as exc:
            return _fail(f"This setup does not offer that choice: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(f"The engine could not assemble this view: {exc}")
        agents = sorted(set(now["prompts"]) | set(then["prompts"]))
        changed_agents = [a for a in agents
                          if now["prompts"].get(a) != then["prompts"].get(a)]
        agent = args[1] if len(args) > 1 else None
        lines = (prompt_diff(then["prompts"].get(agent, ""), now["prompts"].get(agent, ""))
                 if agent else [])
        return _ok(data={"changed_agents": changed_agents, "lines": lines})

    @app.post("/api/view")
    async def api_view(request: Request):
        try:
            args = (await request.json()).get("args") or []
        except Exception:  # noqa: BLE001
            args = []
        try:
            data, fp = await asyncio.to_thread(view.get_with_fingerprint)
            choice = engine_view.canonical_choice(args[0] if args else {}, data)
            result = await asyncio.to_thread(views.get, fp, choice)
        except engine_view.ChoiceError as exc:
            return _fail(f"This setup does not offer that choice: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _fail(f"The engine could not assemble this view: {exc}")
        return _ok(data=result)

    @app.post("/api/{name}")
    async def unknown(name: str):
        return _fail(f"The Studio has no {name} call yet.", 404)

    app.mount("/static", StaticFiles(directory=WEB), name="static")
    # Pictures uploaded later (P6b) are served too: the folder may not exist yet.
    app.mount("/pack/assets", StaticFiles(directory=pack_dir / "assets", check_dir=False),
              name="assets")
    return app


def _quiet(fn) -> None:
    try:
        fn()
    except Exception:  # noqa: BLE001 -- the page's call reports it
        pass
