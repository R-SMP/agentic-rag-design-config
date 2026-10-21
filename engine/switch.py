"""Load another configurator in this process: the web app's main menu
(MAS-blueprint setups, step 2).

The engine reads the active setup -- ``config.DC_PACK_DIR`` -- through
``engine/pack.py`` on every call.  What it keeps from one setup is
forgotten here: the files ``engine/pack.py`` and ``engine/pack_tools.py``
hold, the tools' code (the ``_dc_pack_tools.*`` modules) and the path of
the setup's Workflow Settings files (``engine/setups.py``).  A module that
keeps words or data of the setup in a constant registers, with
:func:`on_load`, how to read them again, and :func:`load` runs it.  The
agents are built per session (``agents/hub.build_hub``), so the next
session is the new configurator's.
"""

from __future__ import annotations

import importlib
import json
import sys
import threading
from pathlib import Path

import yaml

import config
from engine import pack as _pack
from engine import pack_tools as _pack_tools
from engine import parameter_access as _parameter_access
from engine import parameters as _parameters
from engine import primer as _primer

_HOOKS: list = []
_LOCK = threading.Lock()


class SetupError(ValueError):
    """The setup cannot run here; :attr:`problems` says why."""

    def __init__(self, message: str, problems: list[str]):
        super().__init__(message)
        self.problems = list(problems)


def on_load(fn):
    """Register *fn* -- a module's words or data of the setup, read again
    -- to run after another setup is loaded.  Returns *fn* (a decorator)."""
    _HOOKS.append(fn)
    return fn


def _point(setup: Path) -> None:
    """The engine reads *setup* from now on, with nothing kept of another."""
    config.DC_PACK_DIR = Path(setup)
    for cache in (_pack._folders_cache, _pack._claims_cache, _pack._names_cache,
                  _pack_tools._manifests_cache, _pack_tools._llm_tools):
        cache.clear()
    _pack_tools._warned_stale.clear()
    prefix = _pack_tools._PKG_PREFIX
    for name in [m for m in sys.modules if m == prefix or m.startswith(prefix + ".")]:
        del sys.modules[name]
    importlib.invalidate_caches()
    _pack_tools.OVERRIDES_PATH = _pack_tools.overrides_path()
    _parameter_access.OVERRIDES_PATH = _parameter_access.overrides_path()


def _lines(exc: Exception) -> list[str]:
    return [ln for ln in str(exc).split("\n") if ln.strip()] or [type(exc).__name__]


def problems() -> list[str]:
    """What keeps the active setup from running: its format, its
    ``parameters.json``, its tools, its primer and its agents' access to the
    parameter list, as the engine checks them ([] when it can run)."""
    root = _pack.pack_dir()
    try:
        problem = _pack.format_problem(root)
    except (OSError, yaml.YAMLError) as exc:
        return [f"pack.yaml: {exc}"]
    if problem:
        return [problem]
    out: list[str] = []
    try:
        spec = json.loads((root / "parameters.json").read_text(encoding="utf-8"))
        out += [f"parameters.json: {p}" for p in _parameters.validate(spec)]
    except (OSError, ValueError) as exc:
        out.append(f"parameters.json: {exc}")
    for check in (_pack_tools._read_manifests, _primer.read, _parameter_access.default_table):
        try:
            check()
        except Exception as exc:                                    # noqa: BLE001
            out += _lines(exc)
    return out


def load(setup: Path) -> None:
    """Make *setup* the active setup of this process.  Raises
    :class:`SetupError` -- the active one stays -- when it cannot run."""
    setup = Path(setup)
    with _LOCK:
        old = Path(config.DC_PACK_DIR)
        _point(setup)
        found = problems()
        if not found:
            try:
                for fn in list(_HOOKS):
                    fn()
                return
            except Exception as exc:                                # noqa: BLE001
                found = [f"reading it: {type(exc).__name__}: {exc}"]
        _point(old)
        for fn in list(_HOOKS):
            fn()
        raise SetupError(f"{setup.name} cannot be loaded.", found)
