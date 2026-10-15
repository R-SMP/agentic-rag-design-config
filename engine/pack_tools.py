"""The pack's tools: ``dc_pack/tools/<name>/tool.yaml`` + its Python code.

The engine side of the tool contract (``engine/tooling.py``):

* **loading** -- every ``tool.yaml`` is read and checked; a tool's code is
  imported on first use, as a package of its own folder, so its modules
  import each other relatively (``from .ring_height import …``);
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
  registry (``agents/shared/attempt_views.py``).

Imports nothing from ``agents`` at module level: ``prompts`` reads the flags
through here while ``agents`` is still being imported.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
import sys
import tempfile
import threading
import types
from dataclasses import dataclass
from pathlib import Path

import yaml

import config
from engine import pack as _pack
from engine import parameters as _parameters
from engine.tooling import GeneratorInput, ToolError

KINDS = ("generator", "helper")
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

_TOP_KEYS = {"name", "display_name", "kind", "roles", "description", "build",
             "render", "entrypoint", "args", "outputs", "switch", "settings"}
_SETTING_KEYS = {"name", "type", "values", "default", "label", "description"}
_IMAGE_KEYS = {"view", "file", "order", "default_enabled", "label"}


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
    for k in ("display_name", "description"):
        if not isinstance(m.get(k), str) or not m.get(k).strip():
            p.append(f"{where}: {k} is required text")
    if m.get("kind") not in KINDS:
        p.append(f"{where}: kind must be one of {', '.join(KINDS)}")
    roles = m.get("roles")
    if not isinstance(roles, list) or not roles or any(r not in ROLES for r in roles):
        p.append(f"{where}: roles must list some of {', '.join(ROLES)}")
    if m.get("kind") == "generator":
        for k in ("build", "render"):
            if not _REF_RE.match(str(m.get(k, ""))):
                p.append(f"{where}: {k} must be '<module>.py:<function>'")
        args = m.get("args") or {}
        if set(args) != {"parameters_path"} or not isinstance(args.get("parameters_path"), str):
            p.append(f"{where}: a generator's args are exactly parameters_path: <text>")
        if not isinstance((m.get("outputs") or {}).get("model_file"), str):
            p.append(f"{where}: a generator declares outputs.model_file")
    elif m.get("kind") == "helper":
        if not _REF_RE.match(str(m.get("entrypoint", ""))):
            p.append(f"{where}: entrypoint must be '<module>.py:<function>'")
    outputs = m.get("outputs") or {}
    if not isinstance(outputs, dict) or set(outputs) - {"model_file", "images"}:
        p.append(f"{where}: outputs holds model_file and images only")
    for i, img in enumerate((outputs or {}).get("images") or []):
        if not isinstance(img, dict) or set(img) - _IMAGE_KEYS or not {
                "view", "file", "order", "default_enabled"} <= set(img):
            p.append(f"{where}: outputs.images[{i}] needs view, file, order, "
                     f"default_enabled (and optionally label)")
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
        else:
            p.append(f"{where}: setting {s.get('name')}: type is bool or enum")
    return p


def manifests() -> dict[str, dict]:
    """``{name: manifest}`` for every tool of the pack, in folder order.
    Raises PackToolError listing every problem."""
    out: dict[str, dict] = {}
    problems: list[str] = []
    root = tools_dir()
    for folder in sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
        f = folder / "tool.yaml"
        if not f.is_file():
            continue
        m = yaml.safe_load(f.read_text(encoding="utf-8"))
        problems += _check_manifest(folder, m)
        out[folder.name] = m
    if problems:
        raise PackToolError("\n".join(problems))
    return out


def manifest(name: str) -> dict:
    try:
        return manifests()[name]
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


def setting_specs(name: str) -> list[dict]:
    """Every setting of the tool: its switch (``enabled``), its declared
    settings, and one ``view_<view>`` per image it produces."""
    m = manifest(name)
    specs: list[dict] = []
    if m.get("switch") is not None:
        sw = m["switch"]
        specs.append({"name": "enabled", "type": "bool", "default": sw["default"],
                      "label": sw.get("label", "Enabled"),
                      "description": sw.get("description", "")})
    specs += [dict(s) for s in m.get("settings") or []]
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
        if tool not in tools:
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


def read_overrides() -> dict[str, dict]:
    """The values changed in Workflow Settings."""
    try:
        raw = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
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


def image_outputs() -> list[dict]:
    """Every image the tools produce, in their declared order:
    ``{view, file, order, tool, setting}`` (``setting``: its on/off switch)."""
    rows = []
    for name, m in manifests().items():
        for img in (m.get("outputs") or {}).get("images") or []:
            rows.append({"view": img["view"], "file": img["file"],
                         "order": img["order"], "tool": name,
                         "setting": f"view_{img['view']}"})
    return sorted(rows, key=lambda r: r["order"])


def view_enabled(view: str) -> bool:
    for r in image_outputs():
        if r["view"] == view:
            return bool(settings(r["tool"])[r["setting"]])
    return False


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
            f"Error: no parameters.json at {params_file}.  An attempt's mesh "
            f"is built FROM its parameter record, so the record must exist "
            f"first — point this call at an attempt that has one."
        )
    try:
        raw_record = json.loads(params_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, (
            f"Error: could not read {params_file}: {exc}.  The file must be "
            f"a JSON object mapping each parameter name to a number."
        )
    if not isinstance(raw_record, dict):
        return None, (
            f"Error: {params_file} is not a JSON object.  It must map each "
            f"parameter name to a number."
        )
    values, missing, non_numeric = {}, [], []
    for name in _parameters.names():
        if name not in raw_record:
            missing.append(name)
            continue
        v = raw_record[name]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            non_numeric.append(name)
            continue
        values[name] = v
    if missing or non_numeric:
        parts = [f"Error: {params_file} is not a complete parameter record."]
        if missing:
            parts.append(f"Missing keys: {sorted(missing)}")
        if non_numeric:
            parts.append(f"Non-numeric values: {sorted(non_numeric)}")
        parts.append(
            "No mesh was built.  Fix the record on a NEW attempt rather than "
            "editing this one — attempt folders are append-only."
        )
        return None, "  ".join(parts)
    return values, None


def _model_word() -> str:
    """The pack's word for the model file ("mesh"): ``$output_model``."""
    return _pack.read("output_model", _pack.REFERENCE_TOPOLOGY)


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
    return GeneratorInput(params=values, attempt_dir=out_dir,
                          model_path=model_path, settings=settings(name)), None


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
