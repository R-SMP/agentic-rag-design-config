"""The pack's tools: ``dc_pack/tools/<name>/tool.yaml`` + its Python code.

The engine side of the tool contract (``engine/tooling.py``):

* **loading** -- every ``tool.yaml`` is read and checked, and kept while
  the files it was read and checked from are unchanged (``engine/pack.py``:
  their size and modification time); a tool's code is imported on first
  use, as a package of its own folder, so its modules import each other
  relatively (``from .ring_height import …``);
* **the LLM tool** -- built from the manifest: its name, description and
  argument texts, with the flowchart label (``display_name``) around it.
  For a generator the engine also runs the steps around the tool's own
  ``build`` / ``render`` (see :func:`run_generator`);
* **binding by role** -- a tool lists the roles it serves (``tool_runner``
  …); :func:`agent_tools` gives an agent the tools of every role it holds in
  the running topology (``agents/shared/agent_roles.py``: the Tool Caller in
  the 7- and 5-agent systems, the Design Engineer in the 3-agent one);
* **settings** -- each tool declares its own (and an on/off ``switch``, and
  one ``view_<view>`` switch per image it produces), with defaults; the
  values changed in Workflow Settings are stored in
  ``workflow_settings/tool_settings.json`` (only the changed ones) and read
  fresh on every call;
* **prompt flags** -- ``tool:<name>`` (the tool is on) and
  ``setting:<name>.<setting>`` (a boolean setting), for the ``<<IF:…>>``
  regions of the pack's fragments (``engine/pack_flags.py``);
* **render views** -- the images the tools produce, in order, for the view
  registry (``agents/shared/attempt_views.py``);
* **geometry tools** -- ``kind: geometry``: they build the model from the
  parameters for a generator (its ``geometry_tool`` /
  ``fallback_geometry_tool`` settings, :func:`make_model`) and for the web
  app's Download buttons (the ``downloads`` choice, default in
  ``dc_pack/pack.yaml``); no agent is given one;
* **secrets** -- the environment variables a tool reads (``secrets``: the
  names, whether each is required, a sentence each).  Names only: the
  values live in ``.env`` or the hosting provider, never in the pack;
* **outputs** -- each picture view, and each generator's model file, is one
  tool's (two tools would write the same file into an attempt).

Imports nothing from ``agents`` at module level: ``prompts`` reads the flags
through here while ``agents`` is still being imported.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import re
import sys
import tempfile
import threading
import types
from dataclasses import dataclass
from pathlib import Path
from string import Template

import yaml

import config
from engine import pack as _pack
from engine import parameters as _parameters
from engine.tooling import GeneratorInput, MadeModel, ToolError

logger = logging.getLogger("mas_agent")

# The kinds of tool an agent can be given; a ``geometry`` tool is called by
# the engine only (a generator's geometry_tool, the Download buttons).
KINDS = ("generator", "helper")
GEOMETRY = "geometry"
ALL_KINDS = KINDS + (GEOMETRY,)
# The model formats the web app's 3D viewer can load, with the media type
# a download is served as.  A generator without outputs.model_file has no
# model (format "none"): the viewer and the Download buttons are hidden.
MODEL_FORMATS = {"obj": "model/obj"}
UP_AXES = ("y", "z")
# The generator settings that pick its geometry tools (type: tool).
GEOMETRY_SETTING, FALLBACK_SETTING = "geometry_tool", "fallback_geometry_tool"
NONE = "none"
# The Download buttons' choice is stored with the tools' settings under
# this name (so no tool may be called so); SAVED = the file the run built.
DOWNLOADS, SAVED = "downloads", "saved"
# The roles a tool can serve, named for what the agent does, and the
# seven-agent agent that holds each one in the 7-agent system.  In the other
# topologies the holder comes from agents/shared/agent_roles.py.
ROLES = {
    "receptionist": "receptionist",
    "hub": "orchestrator",
    "planner": "planner",
    "input_extractor": "user_input_inspector",
    "parameter_author": "dc_input_creator",
    "parameter_checker": "dc_input_inspector",
    "tool_runner": "tool_caller",
    "output_inspector": "dc_output_inspector",
}
OVERRIDES_PATH = (Path(__file__).resolve().parents[1]
                  / "workflow_settings" / "tool_settings.json")
_LOCK = threading.Lock()
_PKG_PREFIX = "_dc_pack_tools"
_ERROR_LABEL_RE = re.compile(r"^(?:[A-Za-z]+ )?[Ee]rror:")
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_REF_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\.py:([A-Za-z_][A-Za-z0-9_]*)$")
# An environment variable's name, as a tool declares it under secrets.
_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SECRET_KEYS = {"env", "required", "description"}

_TOP_KEYS = {"name", "display_name", "kind", "roles", "description", "build",
             "render", "entrypoint", "args", "outputs", "switch", "settings",
             "list_order", "prompt_slots", "fill_on_save", "image_note",
             "runtime_blocks", "secrets"}
_SETTING_KEYS = {"name", "type", "values", "default", "label", "description",
                 "tool_kind", "none"}
_IMAGE_KEYS = {"view", "file", "order", "default_enabled", "label", "compression",
               "variants"}
# The picture contract: a tool's picture of view V is the PNG file
# render_<V>.png in the attempt folder it is given (a variant X of it:
# render_<V>_<X>.png), and it states which of the two Workflow Settings
# shrink strengths applies to it.
IMAGE_PREFIX, IMAGE_SUFFIX = "render_", ".png"
COMPRESSION_KINDS = ("cross_sections", "3d_render")
_BLOCK_KEYS = {"slot", "off_unless", "off_slot"}
_SETTING_REF_RE = re.compile(r"\$\{?([a-z][a-z0-9_]*)\}?")


def image_file(view: str, variant: str | None = None) -> str:
    """The file name of a picture of *view* (or of its *variant*)."""
    return f"{IMAGE_PREFIX}{view}{'_' + variant if variant else ''}{IMAGE_SUFFIX}"


class PackToolError(ValueError):
    """A tool manifest, a tool setting or the settings file is invalid."""


# ---------------------------------------------------------------------------
# Manifests
# ---------------------------------------------------------------------------

def tools_dir() -> Path:
    return _pack.pack_dir() / "tools"


def _check_manifest(folder: Path, m) -> list[str]:
    where = f"{folder.name}/tool.yaml"
    if not isinstance(m, dict):
        return [f"{where}: must be a mapping"]
    p = [f"{where}: unknown field {k!r}" for k in sorted(set(m) - _TOP_KEYS)]
    if m.get("name") != folder.name:
        p.append(f"{where}: name must be the folder name {folder.name!r}")
    if folder.name == DOWNLOADS:
        p.append(f"{where}: {DOWNLOADS!r} is reserved (the Download buttons' settings)")
    for k in ("display_name", "description"):
        if not isinstance(m.get(k), str) or not m.get(k).strip():
            p.append(f"{where}: {k} is required text")
    if m.get("kind") not in ALL_KINDS:
        p.append(f"{where}: kind must be one of {', '.join(ALL_KINDS)}")
    roles = m.get("roles")
    if m.get("kind") == GEOMETRY:
        if roles is not None or m.get("args") is not None or m.get("switch") is not None:
            p.append(f"{where}: a geometry tool has no roles, args or switch "
                     f"(the engine calls it, never an agent)")
    elif not isinstance(roles, list) or not roles or any(r not in ROLES for r in roles):
        p.append(f"{where}: roles must list some of {', '.join(ROLES)}")
    if m.get("kind") == "generator":
        for k in ("build", "render"):
            if not _REF_RE.match(str(m.get(k, ""))):
                p.append(f"{where}: {k} must be '<module>.py:<function>'")
        args = m.get("args") or {}
        if set(args) != {"parameters_path"} or not isinstance(args.get("parameters_path"), str):
            p.append(f"{where}: a generator's args are exactly parameters_path: <text>")
        out = m.get("outputs") or {}
        if not isinstance(out.get("model_file"), str):
            p.append(f"{where}: a generator declares outputs.model_file")
        elif out.get("model_format") not in MODEL_FORMATS \
                or Path(out["model_file"]).suffix != f".{out.get('model_format')}":
            p.append(f"{where}: outputs.model_format is one of "
                     f"{', '.join(MODEL_FORMATS)}, the model file's extension")
        if out.get("up_axis", "y") not in UP_AXES:
            p.append(f"{where}: outputs.up_axis is one of {', '.join(UP_AXES)}")
    elif m.get("kind") in ("helper", GEOMETRY):
        if not _REF_RE.match(str(m.get("entrypoint", ""))):
            p.append(f"{where}: entrypoint must be '<module>.py:<function>'")
    outputs = m.get("outputs") or {}
    if m.get("kind") == GEOMETRY:
        if not isinstance(outputs, dict) or set(outputs) != {"model_format"} \
                or outputs["model_format"] not in MODEL_FORMATS:
            p.append(f"{where}: a geometry tool's outputs are exactly model_format: "
                     f"one of {', '.join(MODEL_FORMATS)}")
    elif not isinstance(outputs, dict) or set(outputs) - {
            "model_file", "model_format", "up_axis", "images"}:
        p.append(f"{where}: outputs holds model_file, model_format, up_axis and images only")
    images = (outputs or {}).get("images") or []
    for i, img in enumerate(images):
        if not isinstance(img, dict) or set(img) - _IMAGE_KEYS or not {
                "view", "file", "order", "default_enabled", "compression"} <= set(img):
            p.append(f"{where}: outputs.images[{i}] needs view, file, order, "
                     f"default_enabled, compression (and optionally label, variants)")
            continue
        if not _NAME_RE.match(str(img["view"])) or img["file"] != image_file(img["view"]):
            p.append(f"{where}: outputs.images[{i}]: the picture of view "
                     f"{img['view']!r} must be the file {image_file(str(img['view']))!r}")
        if img["compression"] not in COMPRESSION_KINDS:
            p.append(f"{where}: outputs.images[{i}]: compression is one of "
                     f"{', '.join(COMPRESSION_KINDS)}")
        variants = img.get("variants", [])
        if not isinstance(variants, list) or any(not _NAME_RE.match(str(v)) for v in variants):
            p.append(f"{where}: outputs.images[{i}]: variants lists short names")
    if images and not isinstance(m.get("fill_on_save"), bool):
        p.append(f"{where}: a tool that makes pictures says fill_on_save: true|false "
                 f"(may the save step use it to add missing pictures)")
    if m.get("image_note") is not None and not _REF_RE.match(str(m["image_note"])):
        p.append(f"{where}: image_note must be '<module>.py:<function>'")
    sw = m.get("switch")
    if sw is not None and (not isinstance(sw, dict) or not isinstance(sw.get("default"), bool)
                           or set(sw) - {"default", "label", "description"}):
        p.append(f"{where}: switch is {{default: true|false, label, description}}")
    for i, s in enumerate(m.get("settings") or []):
        if not isinstance(s, dict) or set(s) - _SETTING_KEYS:
            p.append(f"{where}: settings[{i}] has unknown fields")
            continue
        if not _NAME_RE.match(str(s.get("name", ""))) or s["name"] == "enabled" \
                or str(s["name"]).startswith("view_"):
            p.append(f"{where}: settings[{i}] needs a name (not 'enabled' / 'view_…')")
        if s.get("type") == "bool":
            if not isinstance(s.get("default"), bool):
                p.append(f"{where}: setting {s.get('name')}: a bool default is true/false")
        elif s.get("type") == "enum":
            vals = s.get("values")
            if not isinstance(vals, list) or s.get("default") not in vals:
                p.append(f"{where}: setting {s.get('name')}: values must list the default")
        elif s.get("type") == "tool":
            # The choices are the pack's tools of that kind (manifests()
            # checks the default names one of them).
            if s.get("tool_kind") != GEOMETRY or "values" in s \
                    or not isinstance(s.get("none", False), bool) \
                    or not isinstance(s.get("default"), str):
                p.append(f"{where}: setting {s.get('name')}: a tool setting is "
                         f"{{tool_kind: {GEOMETRY}, default: <tool>, none: true|false}}")
        else:
            p.append(f"{where}: setting {s.get('name')}: type is bool, enum or tool")
        if s.get("type") != "tool" and ({"tool_kind", "none"} & set(s)):
            p.append(f"{where}: setting {s.get('name')}: tool_kind / none are for "
                     f"type: tool")
    # The environment variables it reads: names, never values.
    secrets = m.get("secrets", [])
    if not isinstance(secrets, list):
        p.append(f"{where}: secrets lists {{env: NAME, required: true|false, description}}")
        secrets = []
    seen_env: set[str] = set()
    for i, s in enumerate(secrets):
        if (not isinstance(s, dict) or set(s) - _SECRET_KEYS
                or not _ENV_RE.match(str(s.get("env", "")))
                or not isinstance(s.get("required", False), bool)
                or not isinstance(s.get("description"), str) or not s["description"].strip()):
            p.append(f"{where}: secrets[{i}] is {{env: NAME (capitals, digits, _), "
                     f"required: true|false, description: <text>}}")
        elif s["env"] in seen_env:
            p.append(f"{where}: secrets names {s['env']} twice")
        else:
            seen_env.add(s["env"])
    # Its place in the tool runner's numbered tool list, and the text it owns.
    runner = isinstance(roles, list) and "tool_runner" in roles
    order = m.get("list_order")
    if runner and (not isinstance(order, int) or isinstance(order, bool)):
        p.append(f"{where}: a tool_runner tool needs list_order: <number> "
                 f"(its place in the tool runner's tool list)")
    if not runner and order is not None:
        p.append(f"{where}: list_order is for tool_runner tools only")
    if runner and not (folder / _pack.TOOL_PROMPTS / f"{_pack.TOOL_LIST_ENTRY}.md").is_file() \
            and not list((folder / _pack.TOOL_PROMPTS).glob(f"{_pack.TOOL_LIST_ENTRY}.t*.md")):
        p.append(f"{where}: a tool_runner tool needs {_pack.TOOL_PROMPTS}/"
                 f"{_pack.TOOL_LIST_ENTRY}.md (its entry in the tool list)")
    owned = m.get("prompt_slots", [])
    if not isinstance(owned, list) or any(not isinstance(s, str) for s in owned):
        p.append(f"{where}: prompt_slots lists slot names")
        owned = []
    if len(set(owned)) != len(owned):
        p.append(f"{where}: prompt_slots names a slot twice")
    reg = _pack.registry()
    for s in owned:
        if reg.get(s, {}).get("filled_by") != "tool":
            p.append(f"{where}: prompt_slots: ${s} is not a tool-text slot "
                     f"(filled_by: tool in engine/slot_registry.yaml)")
    # runtime_blocks: a {placeholder} of the tool runner's prompt that one of
    # this tool's slots fills, chosen by the tool's own settings.
    blocks = m.get("runtime_blocks") or {}
    if not isinstance(blocks, dict):
        p.append(f"{where}: runtime_blocks maps a placeholder to {{slot, off_unless, off_slot}}")
        blocks = {}
    specs = {s.get("name"): s for s in (m.get("settings") or []) if isinstance(s, dict)}
    for name, b in blocks.items():
        if not _NAME_RE.match(str(name)) or not isinstance(b, dict) or set(b) - _BLOCK_KEYS \
                or not isinstance(b.get("slot"), str):
            p.append(f"{where}: runtime_blocks.{name} is {{slot, off_unless, off_slot}}")
            continue
        refs = _SETTING_REF_RE.findall(b["slot"])
        if any(specs.get(r, {}).get("type") != "enum" for r in refs):
            p.append(f"{where}: runtime_blocks.{name}: its slot may only name enum settings")
            continue
        slots = [b["slot"]]
        for r in refs:
            slots = [Template(s).safe_substitute({r: v}) for s in slots
                     for v in specs[r]["values"]]
        if "off_unless" in b:
            if specs.get(b["off_unless"], {}).get("type") != "bool" \
                    or not isinstance(b.get("off_slot"), str):
                p.append(f"{where}: runtime_blocks.{name}: off_unless names a bool "
                         f"setting, with an off_slot")
                continue
            slots.append(b["off_slot"])
        for s in slots:
            if s not in owned:
                p.append(f"{where}: runtime_blocks.{name} can read ${s}, which is not "
                         f"in the tool's prompt_slots")
    return p


def _check_tool_texts(found: dict[str, dict]) -> list[str]:
    """Who owns which text: one owner per slot, every owned slot has a file
    in its tool's ``prompts/``, every file there belongs to a slot the tool
    lists, and no tool-text slot keeps a file in ``fragments/``."""
    p: list[str] = []
    owner: dict[str, str] = {}
    for name, m in found.items():
        owned = m.get("prompt_slots") if isinstance(m, dict) else None
        owned = [s for s in owned if isinstance(s, str)] if isinstance(owned, list) else []
        for s in owned:
            if s in owner:
                p.append(f"${s} is claimed by both {owner[s]} and {name}")
            owner.setdefault(s, name)
        d = _pack.tool_prompts_dir(name)
        files = sorted(d.glob("*.md")) if d.is_dir() else []
        slots_with_files = {_pack.slot_of_file(f.name) for f in files}
        for s in owned:
            if s not in slots_with_files:
                p.append(f"{name}/{_pack.TOOL_PROMPTS}/: no file for ${s}, "
                         f"which its tool.yaml lists")
        for f in files:
            s = _pack.slot_of_file(f.name)
            if s != _pack.TOOL_LIST_ENTRY and s not in owned:
                p.append(f"{name}/{_pack.TOOL_PROMPTS}/{f.name}: its slot ${s} "
                         f"is not in the tool's prompt_slots")
    for folder in _pack.FOLDERS:
        d = _pack.fragments_dir() / folder
        for f in sorted(d.glob("*.md")) if d.is_dir() else []:
            s = _pack.slot_of_file(f.name)
            if _pack.registry().get(s, {}).get("filled_by") == "tool":
                p.append(f"fragments/{folder}/{f.name}: ${s} is tool text -- "
                         f"it belongs in the prompts/ folder of the tool that owns it")
    return p


_manifests_cache: dict[tuple, dict[str, dict]] = {}


def _checked_manifests() -> dict[str, dict]:
    """The checked manifests, kept while the files they are read and
    checked from are unchanged (``engine/pack.py``: the tools' stamp and
    the ``fragments/`` folders').  The kept dict is never handed out."""
    key = (_pack.tools_stamp(),
           tuple(_pack.stamp(_pack.fragments_dir() / f) for f in _pack.FOLDERS))
    found = _manifests_cache.get(key)
    if found is None:
        found = _read_manifests()
        _manifests_cache.clear()
        if _pack.settled(key[0] + key[1]):
            _manifests_cache[key] = found
    return found


def _read_manifests() -> dict[str, dict]:
    out: dict[str, dict] = {}
    problems: list[str] = []
    root = tools_dir()
    for name in _pack.tool_folders():
        folder = root / name
        f = folder / "tool.yaml"
        if not f.is_file():
            continue
        m = yaml.safe_load(f.read_text(encoding="utf-8"))
        problems += _check_manifest(folder, m)
        out[folder.name] = m
    problems += _check_tool_texts(out)
    problems += _check_geometry(out)
    problems += _check_outputs(out)
    if problems:
        raise PackToolError("\n".join(problems))
    return out


def _copy(value):
    """A deep copy of plain YAML data (dicts, lists, scalars)."""
    if isinstance(value, dict):
        return {k: _copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_copy(v) for v in value]
    return value


def manifests() -> dict[str, dict]:
    """``{name: manifest}`` for every tool of the pack, in folder order: a
    copy of its own for each caller.  Raises PackToolError listing every
    problem."""
    return _copy(_checked_manifests())


def _check_geometry(found: dict[str, dict]) -> list[str]:
    """A tool setting's default names one of the pack's geometry tools (or
    ``none`` where allowed), and every geometry tool makes the model in the
    generator's format."""
    p: list[str] = []
    ok = [n for n, m in found.items() if isinstance(m, dict) and m.get("kind") == GEOMETRY]
    formats = {(m.get("outputs") or {}).get("model_format")
               for m in found.values() if isinstance(m, dict) and m.get("kind") == "generator"}
    for name in ok:
        fmt = (found[name].get("outputs") or {}).get("model_format")
        if formats and fmt not in formats:
            p.append(f"{name}/tool.yaml: makes {fmt!r} models, the generator's are "
                     f"{', '.join(sorted(map(str, formats)))}")
    for name, m in found.items():
        for s in (m.get("settings") or []) if isinstance(m, dict) else []:
            if isinstance(s, dict) and s.get("type") == "tool":
                allowed = ok + ([NONE] if s.get("none") else [])
                if s.get("default") not in allowed:
                    p.append(f"{name}/tool.yaml: setting {s.get('name')}: the default "
                             f"{s.get('default')!r} is not one of the pack's geometry "
                             f"tools ({', '.join(allowed) or 'none'})")
    return p


def _check_outputs(found: dict[str, dict]) -> list[str]:
    """Each picture view, and each generator's model file, belongs to one
    tool: two tools writing the same file name would overwrite each other's
    output in an attempt (and share one view switch)."""
    p: list[str] = []
    views: dict[str, str] = {}
    models: dict[str, str] = {}
    for name, m in found.items():
        out = (m.get("outputs") or {}) if isinstance(m, dict) else {}
        for img in out.get("images") or [] if isinstance(out, dict) else []:
            v = img.get("view") if isinstance(img, dict) else None
            if v in views and views[v] != name:
                p.append(f"{name}/tool.yaml: the picture view {v!r} is already {views[v]}'s "
                         f"(each view is one tool's)")
            elif v is not None:
                views[v] = name
        f = out.get("model_file") if isinstance(out, dict) and m.get("kind") == "generator" else None
        if f is not None:
            if f in models:
                p.append(f"{name}/tool.yaml: the model file {f!r} is already {models[f]}'s")
            else:
                models[f] = name
    return p


def manifest(name: str) -> dict:
    try:
        return _copy(_checked_manifests()[name])
    except KeyError:
        raise PackToolError(f"the pack has no tool {name!r}") from None


# ---------------------------------------------------------------------------
# Code
# ---------------------------------------------------------------------------

@dataclass
class Plugin:
    name: str
    folder: Path

    @property
    def package(self) -> str:
        return f"{_PKG_PREFIX}.{self.name}"

    def _ensure_package(self) -> None:
        if _PKG_PREFIX not in sys.modules:
            root = types.ModuleType(_PKG_PREFIX)
            root.__path__ = []
            sys.modules[_PKG_PREFIX] = root
        if self.package not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                self.package, self.folder / "__init__.py",
                submodule_search_locations=[str(self.folder)])
            pkg = importlib.util.module_from_spec(spec)
            sys.modules[self.package] = pkg
            if (self.folder / "__init__.py").is_file():
                spec.loader.exec_module(pkg)

    def submodule(self, module: str):
        """One module of the tool's folder (``generate_mesh``, ``draw`` …)."""
        self._ensure_package()
        return importlib.import_module(f"{self.package}.{module}")

    def function(self, ref: str):
        mod, fn = _REF_RE.match(ref).groups()
        return getattr(self.submodule(mod), fn)

    @property
    def module(self):
        """The module of the tool's entry point (its build / entrypoint)."""
        m = manifest(self.name)
        ref = m.get("build") or m.get("entrypoint")
        return self.submodule(_REF_RE.match(ref).group(1))


def plugin(name: str) -> Plugin:
    manifest(name)
    return Plugin(name, tools_dir() / name)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

_test_overrides: dict[str, dict] = {}


def _choices(kind: str, none: bool, extra: dict | None = None) -> tuple[list, dict]:
    """The values and their labels of a choice among the pack's tools of
    *kind* (display names), with ``none`` and *extra* choices."""
    tools = {n: m["display_name"] for n, m in manifests().items() if m["kind"] == kind}
    labels = dict(tools, **(extra or {}), **({NONE: NONE} if none else {}))
    return list(labels), labels


def _resolved(s: dict) -> dict:
    """A declared setting as the panel and the checks see it: a ``tool``
    setting becomes an enum of the pack's tools of its kind, with labels."""
    s = dict(s)
    if s.get("type") == "tool":
        s["values"], s["labels"] = _choices(s.pop("tool_kind"), s.pop("none", False))
        s["type"] = "enum"
    return s


def download_specs() -> list[dict]:
    """The Download buttons' choice: which geometry tool rebuilds the model a
    user downloads, or the file the run saved.  Its default is
    ``downloads.geometry_tool`` in ``dc_pack/pack.yaml``."""
    values, labels = _choices(GEOMETRY, False, {SAVED: "the saved file"})
    try:
        data = yaml.safe_load((_pack.pack_dir() / "pack.yaml").read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        data = {}
    default = ((data.get("downloads") or {}).get("geometry_tool")) or SAVED
    if default not in values:
        raise PackToolError(f"pack.yaml: downloads.geometry_tool {default!r} is not one "
                            f"of {', '.join(values)}")
    return [{"name": "geometry_tool", "type": "enum", "values": values,
             "labels": labels, "default": default,
             "label": "Download geometry with",
             "description": ("The tool that makes the geometry the Download buttons "
                             "give (from the attempt's parameters, or from the sliders "
                             "on the Parameters page).  If it fails, the saved file is "
                             "downloaded.  the saved file = the geometry the run built.")}]


def setting_specs(name: str) -> list[dict]:
    """Every setting of the tool: its switch (``enabled``), its declared
    settings, and one ``view_<view>`` per image it produces.  (For
    :data:`DOWNLOADS`: the Download buttons' choice.)"""
    if name == DOWNLOADS:
        return download_specs()
    m = manifest(name)
    specs: list[dict] = []
    if m.get("switch") is not None:
        sw = m["switch"]
        specs.append({"name": "enabled", "type": "bool", "default": sw["default"],
                      "label": sw.get("label", "Enabled"),
                      "description": sw.get("description", "")})
    specs += [_resolved(s) for s in m.get("settings") or []]
    for img in (m.get("outputs") or {}).get("images") or []:
        specs.append({"name": f"view_{img['view']}", "type": "bool",
                      "default": img["default_enabled"],
                      "label": img.get("label", f"Render view: {img['view']}"),
                      "description": f"Create, save and retrieve {img['file']} "
                                     f"for every attempt."})
    return specs


def defaults(name: str) -> dict:
    return {s["name"]: s["default"] for s in setting_specs(name)}


def _check_value(tool: str, spec: dict, value) -> str | None:
    if spec["type"] == "bool" and not isinstance(value, bool):
        return f"{tool}.{spec['name']}: must be true or false"
    if spec["type"] == "enum" and value not in spec["values"]:
        return f"{tool}.{spec['name']}: must be one of {', '.join(map(str, spec['values']))}"
    return None


def _validated(raw, source: str) -> dict[str, dict]:
    if not isinstance(raw, dict):
        raise PackToolError(f"{source}: must map tool -> {{setting: value}}")
    problems, out = [], {}
    tools = manifests()
    for tool, values in raw.items():
        if tool not in tools and tool != DOWNLOADS:
            problems.append(f"{source}: no tool {tool!r} in the pack")
            continue
        if not isinstance(values, dict):
            problems.append(f"{source}: {tool} must map setting -> value")
            continue
        specs = {s["name"]: s for s in setting_specs(tool)}
        for k, v in values.items():
            if k not in specs:
                problems.append(f"{source}: {tool} has no setting {k!r}")
                continue
            err = _check_value(tool, specs[k], v)
            if err:
                problems.append(f"{source}: {err}")
                continue
            out.setdefault(tool, {})[k] = v
    if problems:
        raise PackToolError("\n".join(problems))
    return out


_warned_stale: set[str] = set()     # stale saved settings already logged


def read_overrides() -> dict[str, dict]:
    """The values changed in Workflow Settings.  Values saved for a tool
    that is no longer in the pack (its folder was removed), or for a setting
    a tool no longer has, are left out, like the tool or the setting; the
    next save drops them from the file."""
    try:
        raw = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if isinstance(raw, dict):
        present = set(manifests()) | {DOWNLOADS}
        kept = {}
        for t, v in raw.items():
            if t not in present:
                continue
            if isinstance(v, dict):
                names = {s["name"] for s in setting_specs(t)}
                for k in sorted(f"{t}.{k}" for k in set(v) - names):
                    if k not in _warned_stale:
                        _warned_stale.add(k)
                        logger.warning("[TOOLS] %s: ignoring the saved setting %r, "
                                       "which the tool no longer has",
                                       OVERRIDES_PATH.name, k)
                v = {k: x for k, x in v.items() if k in names}
            kept[t] = v
        raw = kept
    return _validated(raw, OVERRIDES_PATH.name)


def settings(name: str) -> dict:
    """The tool's settings for the session being built: defaults, then the
    Workflow Settings changes."""
    out = defaults(name)
    out.update(read_overrides().get(name, {}))
    out.update(_test_overrides.get(name, {}))
    return out


def save_overrides(values: dict) -> dict[str, dict]:
    """Store the Workflow Settings choice (*values*: every tool's settings as
    the page sends them); only values that differ from the defaults are
    written, none -> the file is removed.  Returns what was stored."""
    wanted = _validated(values, "request")
    diff = {t: {k: v for k, v in vals.items() if defaults(t)[k] != v}
            for t, vals in wanted.items()}
    diff = {t: vals for t, vals in diff.items() if vals}
    with _LOCK:
        if not diff:
            OVERRIDES_PATH.unlink(missing_ok=True)
            return {}
        fd, tmp = tempfile.mkstemp(dir=OVERRIDES_PATH.parent,
                                   prefix=".tool_settings.", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(diff, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, OVERRIDES_PATH)
    return diff


def reset_overrides() -> None:
    with _LOCK:
        OVERRIDES_PATH.unlink(missing_ok=True)


def settings_override_for_tests(values: dict | None) -> None:
    """Checks and harnesses only: lay *values* over every tool's settings in
    this process (``None`` / ``{}`` clears).  Never touches the file."""
    _test_overrides.clear()
    for tool, vals in (values or {}).items():
        _test_overrides[tool] = dict(vals)


def is_enabled(name: str) -> bool:
    return bool(settings(name).get("enabled", True))


def setting(name: str, key: str):
    return settings(name)[key]


def generators() -> list[str]:
    return [n for n, m in manifests().items() if m["kind"] == "generator"]


def geometry_tools() -> list[str]:
    return [n for n, m in manifests().items() if m["kind"] == GEOMETRY]


def download_tool() -> str:
    """The Download buttons' choice: a geometry tool's name, or SAVED."""
    return settings(DOWNLOADS)["geometry_tool"]


def page_tools() -> list[dict]:
    """The switched-on tools the agents can call, as the web app shows
    them (the flowchart's TOOLS panel, the LLM routing chart): name and
    display name, generators first, each kind in folder order."""
    return [{"name": n, "label": m["display_name"]}
            for kind in KINDS for n, m in manifests().items()
            if m["kind"] == kind and is_enabled(n)]


# ---------------------------------------------------------------------------
# Prompt flags and render views
# ---------------------------------------------------------------------------

def flag_values() -> dict[str, bool]:
    """``tool:<name>`` and ``setting:<name>.<setting>`` (bool settings) for
    every tool of the pack."""
    out: dict[str, bool] = {}
    for name in manifests():
        vals = settings(name)
        out[f"tool:{name}"] = bool(vals.get("enabled", True))
        for s in setting_specs(name):
            if s["type"] == "bool" and s["name"] != "enabled":
                out[f"setting:{name}.{s['name']}"] = bool(vals[s["name"]])
    return out


_FLAG_TOOL_RE = re.compile(
    r"^(?:tool:([a-z][a-z0-9_]*)|setting:([a-z][a-z0-9_]*)\.[a-z0-9_]+)$")


def names_absent_tool(flag: str) -> bool:
    """True for a ``tool:<name>`` / ``setting:<name>.<setting>`` flag whose
    tool is not in the pack (removed): the prompts read it as switched off.
    A misspelt setting of a tool that IS in the pack stays an error."""
    m = _FLAG_TOOL_RE.match(flag)
    return bool(m) and (m.group(1) or m.group(2)) not in manifests()


def image_outputs() -> list[dict]:
    """Every image the tools produce, in their declared order:
    ``{view, file, order, tool, setting, compression, variant_files}``
    (``setting``: its on/off switch)."""
    rows = []
    for name, m in manifests().items():
        for img in (m.get("outputs") or {}).get("images") or []:
            rows.append({"view": img["view"], "file": img["file"],
                         "order": img["order"], "tool": name,
                         "setting": f"view_{img['view']}",
                         "compression": img["compression"],
                         "variant_files": [image_file(img["view"], v)
                                           for v in img.get("variants") or []]})
    return sorted(rows, key=lambda r: r["order"])


def view_enabled(view: str) -> bool:
    for r in image_outputs():
        if r["view"] == view:
            return bool(settings(r["tool"])[r["setting"]])
    return False


def compression_kind(file_name: str) -> str | None:
    """The shrink strength (one of :data:`COMPRESSION_KINDS`) a tool declares
    for the picture *file_name* (or a variant of it); None for any other
    file."""
    for r in image_outputs():
        if file_name == r["file"] or file_name in r["variant_files"]:
            return r["compression"]
    return None


def model_info() -> dict | None:
    """The generator's model as the web app shows it -- ``{file, ext,
    format, media_type, up_axis}`` -- or None when it makes none."""
    gens = generators()
    out = manifest(gens[0])["outputs"] if gens else {}
    if not out.get("model_file"):
        return None
    fmt = out["model_format"]
    return {"file": out["model_file"], "ext": Path(out["model_file"]).suffix,
            "format": fmt, "media_type": MODEL_FORMATS[fmt],
            "up_axis": out.get("up_axis", "y")}


def model_file() -> str | None:
    """The file name of the generator's model (``outputs.model_file``)."""
    gens = generators()
    return manifest(gens[0])["outputs"]["model_file"] if gens else None


def image_notes(params: dict) -> list[str]:
    """The notes the tools write under an attempt's opened picture
    (``image_note`` in tool.yaml), from that attempt's parameters, in folder
    order.  Every tool that declares one, switched on or not."""
    out = []
    for name, m in manifests().items():
        if m.get("image_note"):
            out.append(plugin(name).function(m["image_note"])(params))
    return out


def settings_snapshot() -> dict[str, dict]:
    """Every tool's settings, as one session takes them at its start."""
    return {name: settings(name) for name in manifests()}


def runtime_block_slot(placeholder: str, snapshot: dict[str, dict]) -> str | None:
    """The slot that fills *placeholder* of the tool runner's prompt
    (``runtime_blocks`` in a tool.yaml), chosen by the tool's settings in
    *snapshot* (:func:`settings_snapshot`); None when no tool declares it."""
    for name, m in manifests().items():
        b = (m.get("runtime_blocks") or {}).get(placeholder)
        if b is None:
            continue
        vals = snapshot.get(name) or settings(name)
        if "off_unless" in b and not vals.get(b["off_unless"]):
            return b["off_slot"]
        return Template(b["slot"]).substitute({k: v for k, v in vals.items()})
    return None


# ---------------------------------------------------------------------------
# Running a generator
# ---------------------------------------------------------------------------

def _attempt_folder(raw: str, tool: str) -> tuple[Path | None, str | None]:
    """Resolve and check the attempt folder a generator writes into."""
    if not isinstance(raw, str) or not raw.strip():
        return None, (
            "Error: missing or non-string 'output_dir'.  Pass the "
            "absolute path of the attempt folder (the same path the "
            "hand-off carries under ``Current attempt <N>:``)."
        )
    path = Path(raw).resolve()
    if not path.is_dir():
        return None, (
            f"Error: '{raw}' is not an existing directory.  Create the "
            f"attempt folder first and pass its absolute path."
        )
    try:
        attempts_root = config.ATTEMPTS_DIR.resolve()
    except OSError:
        attempts_root = config.ATTEMPTS_DIR
    if attempts_root not in path.parents and path != attempts_root:
        return None, (
            f"Error: '{path}' is not an attempt folder under "
            f"{attempts_root}.  ``{tool}`` only "
            f"writes inside an attempt folder."
        )
    return path, None


def _read_record(params_file: Path) -> tuple[dict | None, str | None]:
    """An attempt's ``parameters.json`` as ``{name: value}`` in the
    parameters' canonical order, or the error the agent gets.  A key that is
    not a parameter (a legacy ``impellerHeight``) is ignored."""
    if not params_file.is_file():
        return None, (
            f"Error: no parameters.json at {params_file}.  An attempt's {_model_word()} "
            f"is built FROM its parameter record, so the record must exist "
            f"first — point this call at an attempt that has one."
        )
    try:
        raw_record = json.loads(params_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, (
            f"Error: could not read {params_file}: {exc}.  The file must be "
            f"a JSON object mapping each parameter name to {_parameters.value_phrase()}."
        )
    if not isinstance(raw_record, dict):
        return None, (
            f"Error: {params_file} is not a JSON object.  It must map each "
            f"parameter name to {_parameters.value_phrase()}."
        )
    # Choice and on/off parameters (MAS-blueprint P6d): each value is
    # checked against its own parameter.
    typed = not _parameters.all_numbers()
    by = _parameters.by_name() if typed else {}
    values, missing, non_numeric, wrong = {}, [], [], []
    for name in _parameters.names():
        if name not in raw_record:
            missing.append(name)
            continue
        v = raw_record[name]
        if typed:
            why = _parameters.check_value(by[name], v)
            if why:
                wrong.append((name, why))
                continue
        elif isinstance(v, bool) or not isinstance(v, (int, float)):
            non_numeric.append(name)
            continue
        values[name] = v
    if missing or non_numeric or wrong:
        parts = [f"Error: {params_file} is not a complete parameter record."]
        if missing:
            parts.append(f"Missing keys: {sorted(missing)}")
        if non_numeric:
            parts.append(f"Non-numeric values: {sorted(non_numeric)}")
        if wrong:
            parts.append(f"Values that do not fit: {_parameters.wrong_text(wrong)}")
        parts.append(
            f"No {_model_word()} was built.  Fix the record on a NEW attempt rather than "
            "editing this one — attempt folders are append-only."
        )
        return None, "  ".join(parts)
    return values, None


def _model_word() -> str:
    """The pack's word for the model file ("mesh"): ``$output_model``."""
    return _pack.read("output_model", _pack.REFERENCE_TOPOLOGY)


def make_model(params: dict, order: list[str]) -> MadeModel:
    """The model built from *params* by the first geometry tool of *order*
    that succeeds (each failure is logged).  Raises ToolError: one tool's
    own error, or -- when every one failed -- all of them, by display name."""
    errors: list[ToolError] = []
    for name in order:
        m = manifest(name)
        try:
            result = plugin(name).function(m["entrypoint"])(dict(params))
        except ToolError as exc:
            logger.warning("Geometry tool %r failed: %s", name, exc)
            errors.append(exc)
            continue
        if errors:
            logger.warning("Geometry tool %r failed; used %r as fallback.",
                           order[0], name)
        return MadeModel(result=result, made_by=m["display_name"],
                         chosen=manifest(order[0])["display_name"])
    if len(errors) == 1:
        raise errors[0]
    raise ToolError("All geometry backends failed — " + " | ".join(
        f"{manifest(n)['display_name']}: {e}" for n, e in zip(order, errors)))


def geometry_order(values: dict) -> list[str]:
    """A generator's geometry tools in the order to try them: its
    ``geometry_tool``, then its ``fallback_geometry_tool`` (unless none)."""
    first = values.get(GEOMETRY_SETTING)
    if not first:
        return []
    second = values.get(FALLBACK_SETTING, NONE)
    return [first] + ([second] if second not in (NONE, first) else [])


def generator_input(name: str, parameters_path: str):
    """``(GeneratorInput, None)`` or ``(None, error text)`` for a generator
    call: the attempt folder and the parameter record, checked."""
    params_file = Path(parameters_path)
    out_dir, err = _attempt_folder(str(params_file.parent), name)
    if err is not None:
        return None, err
    values, err = _read_record(params_file)
    if err is not None:
        return None, err
    model_path = out_dir / manifest(name)["outputs"]["model_file"]
    values_ = settings(name)
    order = geometry_order(values_)
    return GeneratorInput(
        params=values, attempt_dir=out_dir, model_path=model_path, settings=values_,
        make_model=(lambda p: make_model(p, order)) if order else None), None


def run_generator(name: str, parameters_path: str) -> str:
    """What a generator tool answers the agent: the build summary (or the
    reuse note), a blank line, the render report -- or an error."""
    inp, err = generator_input(name, parameters_path)
    if err is not None:
        return err
    m, p = manifest(name), plugin(name)
    if inp.model_path.is_file():
        # Append-only: an attempt's model is never overwritten.
        summary = (
            f"Reused existing {_model_word()} at {inp.model_path.resolve()} "
            f"({inp.model_path.stat().st_size} bytes; geometry not "
            f"regenerated)."
        )
    else:
        try:
            summary = p.function(m["build"])(inp).summary
        except ToolError as exc:
            msg = str(exc)
            return msg if _ERROR_LABEL_RE.match(msg) else f"Error: {msg}"
    try:
        report = p.function(m["render"])(inp).report
    except Exception as exc:  # noqa: BLE001 — a render error must not lose the model
        report = f"Render step failed: {exc}"
    return f"{summary}\n\n{report}"


def render_existing(name: str, attempt_dir) -> str:
    """Render an attempt whose model file is already there (the save-time
    pass that re-creates missing views).  The render step needs only the
    model and the folder, so the parameter record is not read."""
    folder = Path(attempt_dir).resolve()
    inp = GeneratorInput(params={}, attempt_dir=folder,
                         model_path=folder / manifest(name)["outputs"]["model_file"],
                         settings=settings(name))
    return plugin(name).function(manifest(name)["render"])(inp).report


# ---------------------------------------------------------------------------
# The LLM tools
# ---------------------------------------------------------------------------

_llm_tools: dict[tuple, object] = {}


def _make_llm_tool(name: str):
    from typing import Annotated

    from langchain_core.tools import tool as _tool

    from agents.shared.agent_activity import tool_active

    m = manifest(name)
    if m["kind"] == GEOMETRY:
        raise PackToolError(f"{name} is a geometry tool: the engine calls it, "
                            f"no agent does")
    if m["kind"] == "generator":
        def impl(parameters_path):
            return run_generator(name, parameters_path)
        impl.__annotations__ = {
            "parameters_path": Annotated[str, m["args"]["parameters_path"]],
            "return": str,
        }
        impl.__name__ = impl.__qualname__ = name
    else:
        fn = plugin(name).function(m["entrypoint"])
        if fn.__name__ != name:
            raise PackToolError(f"{name}: the entrypoint function must be named {name!r}")
        impl = fn
    wrapped = tool_active(m["display_name"])(impl)
    wrapped.__doc__ = m["description"]
    return _tool(wrapped)


def llm_tool(name: str):
    """The LLM-facing tool (built once per process and pack)."""
    key = (str(_pack.pack_dir()), name)
    if key not in _llm_tools:
        _llm_tools[key] = _make_llm_tool(name)
    return _llm_tools[key]


def _holds(agent_key: str, role: str) -> bool:
    from agents.shared import agent_roles
    from agents.shared.topology import topology
    return agent_roles.holder(ROLES[role], topology()) == agent_key


def agent_tools(agent_key: str, kinds: tuple[str, ...] = KINDS) -> list:
    """The enabled pack tools of *kinds* for the roles *agent_key* holds in
    the running topology, generators first, each kind in folder order."""
    out = []
    for kind in kinds:
        for name, m in manifests().items():
            if m["kind"] != kind or not is_enabled(name):
                continue
            if any(_holds(agent_key, r) for r in m["roles"]):
                out.append(llm_tool(name))
    return out


# ---------------------------------------------------------------------------
# The tool runner's numbered tool list ($tool_inventory)
# ---------------------------------------------------------------------------

# The engine tools the list names around the pack's own: the parameter
# author's tool first when the tool runner also writes the parameters (the
# Design Engineer in topology 3), then calculate and read_attempts.  Their
# entries are pack text: the slots tool_entry_<tool> in fragments/tools/.
_LIST_BEFORE = (("parameter_author", "new_attempt_parameters"),)
_LIST_AFTER = ("calculate", "read_attempts")


def tool_list(agent_key: str) -> str:
    """The numbered list of the tools *agent_key* runs, for its
    ``$tool_inventory``: the engine tools above, and between them every
    switched-on pack tool of the ``tool_runner`` role, in ``list_order``,
    each with its ``prompts/tool_list_entry.md``.  "" for an agent that does
    not run the tools."""
    if not _holds(agent_key, "tool_runner"):
        return ""
    from agents.shared.topology import topology
    topo = topology()
    entries = [_pack.read(f"tool_entry_{tool}", topo)
               for role, tool in _LIST_BEFORE if _holds(agent_key, role)]
    ours = sorted((m["list_order"], name) for name, m in manifests().items()
                  if "tool_runner" in (m.get("roles") or []) and is_enabled(name))
    for _order, name in ours:
        path = _pack.tool_list_entry_path(name, topo)
        entries.append(path.read_text(encoding="utf-8").rstrip())
    entries += [_pack.read(f"tool_entry_{tool}", topo) for tool in _LIST_AFTER]
    return "\n".join(f"{i}. {text}" for i, text in enumerate(entries, 1))
