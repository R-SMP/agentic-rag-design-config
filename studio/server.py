"""The Studio's web server (MAS-blueprint P5a: read-only).

Serves the page (``studio/web/``), the setup's pictures (``/pack/assets/``)
and answers the page's calls: ``POST /api/<name>`` with ``{"args": [...]}``
-> ``{"ok": true, ...}`` or ``{"ok": false, "error": "<sentence>"}``, the
studio UI kit's contract (the draft's mock bridge answered the same calls).

The data comes from the engine (``studio/engine_view.py``, child
processes, about half a minute) and is kept until a file of the setup
changes: each call compares the setup's fingerprint -- every file's path,
size and modification time -- with the one the data was built from.  The
first build starts with the server.

This process never imports the engine: the assembler stubs runtime
packages (FastAPI among them) in the process that runs it.
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
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
        """The data for the setup as it is now: the kept copy, or a build
        (one at a time; callers that arrive meanwhile wait for it)."""
        fp = fingerprint(self.pack_dir)
        with self._lock:
            if self._data is not None and self._data_fp == fp:
                return self._data
            if self._pending is None or self._pending[0] != fp:
                fut: Future = Future()
                self._pending = (fp, fut)
                threading.Thread(target=self._run, args=(fp, fut), daemon=True).start()
            fut = self._pending[1]
        return fut.result()

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


def _ok(**kw) -> JSONResponse:
    return JSONResponse(dict(kw, ok=True))


def _fail(error: str, status: int = 200) -> JSONResponse:
    return JSONResponse({"ok": False, "error": error}, status_code=status)


def create_app(pack_dir: Path) -> FastAPI:
    view = PackView(pack_dir)

    @asynccontextmanager
    async def lifespan(app):
        # Start the first build now, so the page finds it under way.
        threading.Thread(target=lambda: _quiet(view.get), daemon=True).start()
        yield

    app = FastAPI(title="MAS Studio", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.view = view

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
