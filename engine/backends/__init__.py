"""The engine's tool backends (MAS-blueprint P6e).

A generator or a geometry tool may name a model file in its ``tool.yaml``
instead of code -- ``backend: openscad`` -- and the engine runs it: nothing
is written per tool.  The backend builds the model from the attempt's
parameters (a generator: the attempt's model file, then its pictures with
the engine's renderer; a geometry tool: the model, for a generator or the
Download buttons).  One backend for now; RhinoCompute, Node and HTTP ones
are TODO F124.

``engine/pack_tools.py`` checks a backend tool's manifest with :func:`check`
and calls :func:`build`, :func:`render` and :func:`make_model` where a
tool's own code would be called.
"""

from __future__ import annotations

from pathlib import Path

from engine.backends import openscad

BACKENDS = {"openscad": openscad}
# The manifest keys a backend reads (beside the generator's or geometry
# tool's own).
KEYS = ("backend", "model", "parts", "fixed", "detail", "timeout")


def check(folder: Path, m: dict, where: str) -> list[str]:
    """The problems of a backend tool's manifest (*m*, in *folder*)."""
    backend = BACKENDS.get(m.get("backend"))
    if backend is None:
        return [f"{where}: backend is one of {', '.join(sorted(BACKENDS))}"]
    if m.get("kind") not in ("generator", "geometry"):
        return [f"{where}: a backend runs a generator or a geometry tool"]
    p = [f"{where}: a backend tool has no {k} (the engine runs its model)"
         for k in ("build", "render", "entrypoint") if k in m]
    return p + backend.check(folder, m, where)


def parameter_names(m: dict) -> set[str]:
    """The parameters a backend tool's ``parts`` put together."""
    return {x for vals in (m.get("parts") or {}).values() if isinstance(vals, list)
            for x in vals if isinstance(x, str)}


def build(folder: Path, m: dict, inp):
    return BACKENDS[m["backend"]].build(folder, m, inp)


def render(folder: Path, m: dict, inp):
    return BACKENDS[m["backend"]].render(folder, m, inp)


def make_model(folder: Path, m: dict, params: dict):
    return BACKENDS[m["backend"]].make_model(folder, m, params)
