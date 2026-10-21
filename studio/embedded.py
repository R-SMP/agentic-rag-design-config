"""The Studio inside the configurator's own server: one deploy, one address.

``web_app.py`` mounts :data:`STUDIO` at ``/studio``, beside the configurator
(``/configurator``) and the main menu that offers both (``/``).  It is the
online Studio (``python -m studio --online``, ``studio/HOSTING.md``) on ONE
shared setup: a copy of the configurator's own setup in
``workspace/dc_pack`` (``STUDIO_WORKSPACE`` names another folder), so what
the Studio changes never reaches the running configurator.  It asks for the
configurator's own access code (``INVITE_CODE``; without one it is open, as
the configurator is), and its link to the configurator is ``/configurator``.

Nothing is made before the Studio is first opened: then the workspace gets
its copy (when it has none) and the Studio starts, its helper processes
with it.  The configurator's keys are in the same server, where a tool's
code run by Test tool or Validate could read them (TODO F122).
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def shared_setup(workspace: Path, example: Path) -> Path:
    """``<workspace>/dc_pack``, the online Studio's one shared setup: a copy
    of *example* when the workspace holds none (an incomplete one is
    replaced)."""
    pack = workspace / "dc_pack"
    if not (pack / "pack.yaml").is_file():
        shutil.rmtree(pack, ignore_errors=True)
        shutil.copytree(example, pack, ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
        print(f"The shared setup starts from {example}.", flush=True)
    return pack


class LazyStudio:
    """An ASGI app that makes the Studio on its first request and then
    hands every request to it.  :meth:`close` stops it (the server's
    shutdown); a mounted app is not told when the server starts or stops."""

    def __init__(self, configurator_url: str = "/configurator", workers: int = 2):
        self.configurator_url = configurator_url
        self.workers = workers
        self._app = None
        self._lifespan = None
        self._lock: asyncio.Lock | None = None

    @property
    def started(self) -> bool:
        return self._app is not None

    async def __call__(self, scope, receive, send):
        if self._app is None:
            await self._start()
        await self._app(scope, receive, send)

    async def _start(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if self._app is None:
                app = await asyncio.to_thread(self._make)
                self._lifespan = app.router.lifespan_context(app)
                await self._lifespan.__aenter__()
                self._app = app

    def _make(self):
        from studio.__main__ import default_pack
        from studio.server import create_app
        example = default_pack().resolve()
        workspace = Path(os.getenv("STUDIO_WORKSPACE") or REPO / "workspace").resolve()
        pack = shared_setup(workspace, example)
        code = (os.getenv("INVITE_CODE") or "").strip() or None
        return create_app(pack, workers=self.workers, online=True, access_code=code,
                          example_dir=example, configurator_url=self.configurator_url,
                          require_code=False)

    async def close(self) -> None:
        if self._lifespan is not None:
            lifespan, self._lifespan = self._lifespan, None
            await lifespan.__aexit__(None, None, None)


STUDIO = LazyStudio()
