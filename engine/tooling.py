"""The plain-Python contract for a pack tool -- no LangChain in tool code.

A tool lives in ``dc_pack/tools/<name>/``: a ``tool.yaml`` manifest plus its
Python code.  The engine (``engine/pack_tools.py``) reads the manifest,
imports the code, builds the LLM-facing tool from the manifest (name,
description, argument texts) and binds it to the agents that hold the
tool's roles.  The tool code only does the configurator-specific work.

Three kinds of tool:

* **generator** -- builds the design from an attempt's ``parameters.json``.
  It provides two functions, named in its manifest:

      build(inp: GeneratorInput) -> BuildResult     # writes the model files
      render(inp: GeneratorInput) -> RenderResult   # views + checks

  The engine owns everything around them: the LLM argument
  (``parameters_path``), checking that it points into an attempt folder,
  reading and validating the parameter record against
  ``dc_pack/parameters.json``, reusing a model file that is already there
  (append-only: an attempt is never overwritten), turning a
  :class:`ToolError` into the text the agent gets, and joining the build
  summary and the render report into the tool's answer.  ``render`` is also
  what the save-time pass calls to re-create missing views.

  A generator whose settings include ``geometry_tool`` (and, optionally,
  ``fallback_geometry_tool``) -- settings of ``type: tool``, ``tool_kind:
  geometry`` -- gets ``inp.make_model``: it builds the model with the
  chosen geometry tool, then the fallback, and returns a :class:`MadeModel`.

* **helper** -- one plain function with type hints, e.g.
  ``render_blade_sections(parameters_path: str, grid: bool = False) -> str``.
  The engine builds the LLM tool from its signature and the manifest's
  description; the function returns the text the agent gets.

* **geometry** -- builds the model from the parameters, for a generator
  (its ``geometry_tool`` setting) and for the web app's Download buttons
  (Workflow Settings > Tools > Downloads); never given to an agent.  One
  plain function, named by ``entrypoint``::

      make_model(params: dict) -> GeometryResult

  ``params`` is already checked against ``dc_pack/parameters.json``
  (complete, typed, canonical order).  It writes nothing: it returns the
  model in the format its manifest declares (``outputs.model_format``, the
  generator's), and raises :class:`ToolError` when it cannot.

A generator or a geometry tool may instead name a model file the engine
runs, with no code of its own: ``backend: openscad`` (``engine/backends/``,
MAS-blueprint P6e).  Its pictures come from the engine's renderer
(``engine/mesh_render.py``).

A tool that makes images of an attempt follows the image contract in
``dc_pack/README.md`` ("What the engine reads from a tool's outputs").

``inp.settings`` holds the tool's own settings (declared in its manifest,
changed in Workflow Settings), read fresh for every call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


class ToolError(Exception):
    """A failure the agent should read, not a crash.  The engine returns the
    message as the tool's answer -- as written when it starts with an error
    label (``Error:``, ``FEG error:`` ...), otherwise behind ``Error: ``."""


@dataclass
class GeometryResult:
    model: str                       # the model file's content
    vertex_count: int | None = None  # for the summary the agent reads
    extra_files: dict = field(default_factory=dict)  # name -> content, beside the model


@dataclass
class MadeModel:
    result: GeometryResult
    made_by: str                     # display name of the geometry tool that made it
    chosen: str                      # display name of the one the settings chose first


@dataclass
class GeneratorInput:
    params: dict                     # the record, validated, canonical order
    attempt_dir: Path                # the attempt folder (resolved)
    model_path: Path                 # attempt_dir / the manifest's model_file
    settings: dict = field(default_factory=dict)
    make_model: Callable[[dict], MadeModel] | None = None


@dataclass
class BuildResult:
    summary: str                     # first part of the answer to the agent
    model_files: list = field(default_factory=list)


@dataclass
class RenderResult:
    report: str                      # second part of the answer to the agent
    images: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
