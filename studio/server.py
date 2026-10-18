"""The Studio's web server (MAS-blueprint P5: read-only).

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

This process never imports the engine: the assembler stubs runtime
packages (FastAPI among them) in the process that runs it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import threading
from collections import OrderedDict
from concurrent.futures import Future
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from studio import engine_view

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

    def run(self, choice: dict, timeout: float = 300) -> tuple[dict, bool]:
        """The view of *choice*, and whether a waiting worker answered it."""
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
            out, err = proc.communicate((json.dumps(choice) + "\n").encode("utf-8"),
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

    def get(self, fp: str, choice: dict) -> dict:
        key = (fp, json.dumps(choice, sort_keys=True))
        with self._lock:
            if key in self._done:
                self._done.move_to_end(key)
                return self._done[key]
            fut = self._pending.get(key)
            if fut is None:
                fut = Future()
                self._pending[key] = fut
                threading.Thread(target=self._run, args=(key, choice, fut), daemon=True).start()
        return fut.result()

    def _run(self, key, choice: dict, fut: Future) -> None:
        try:
            data, pooled = self.pool.run(choice)
            data["tokens"] = {a: count_tokens(t) for a, t in data["prompts"].items()}
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


def _ok(**kw) -> JSONResponse:
    return JSONResponse(dict(kw, ok=True))


def _fail(error: str, status: int = 200) -> JSONResponse:
    return JSONResponse({"ok": False, "error": error}, status_code=status)


def create_app(pack_dir: Path, workers: int = 2) -> FastAPI:
    view = PackView(pack_dir)
    pool = WorkerPool(pack_dir, size=workers)
    views = ViewCache(pool)

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

    app = FastAPI(title="MAS Studio", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.view = view
    app.state.pool = pool
    app.state.views = views

    @app.middleware("http")
    async def no_stale_page(request: Request, call_next):
        # The page and its scripts change with the Studio: always revalidate.
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/")
    async def index():
        return FileResponse(WEB / "index.html")

    @app.post("/api/get_all")
    async def get_all():
        try:
            data = await asyncio.to_thread(view.get)
        except Exception as exc:  # noqa: BLE001
            return _fail(f"The engine could not assemble this setup: {exc}")
        return _ok(data=data)

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
    if (pack_dir / "assets").is_dir():
        app.mount("/pack/assets", StaticFiles(directory=pack_dir / "assets"), name="assets")
    return app


def _quiet(fn) -> None:
    try:
        fn()
    except Exception:  # noqa: BLE001 -- the page's call reports it
        pass
