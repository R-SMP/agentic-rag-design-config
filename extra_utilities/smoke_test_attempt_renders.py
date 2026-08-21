# -*- coding: utf-8 -*-
"""Offline smoke test for the attempt render-view registry and the
save-time render-completion pass.

No geometry backend, no R2, no LLM, no network.  The render/geometry tools
are stubbed into ``sys.modules`` -- ``attempt_renders`` imports them LAZILY
inside its functions precisely so this is possible, and so that importing it
costs nothing in production.

Covers:
  1. enabled_views / enabled_view_files track the settings flags
  2. the R2 attempt whitelist = base artefacts + ENABLED view files
  3. ensure_renders skips cleanly with no parameters.json
  4. ensure_renders skips when the master switch is off
  5. a complete attempt generates nothing
  6. a missing blade-sections render is generated from parameters.json
  7. a missing 3D view with the mesh present calls the render core ONCE
  8. a missing 3D view with NO mesh calls the geometry tool, with the
     PARAMETERS PATH (its real signature -- not output_dir + 16 kwargs)
  9. a raising tool is recorded as failed and NEVER propagates
 10. blade sections are attempted even when the geometry backend is dead
 11. retrieve_attempt's view map carries blade sections

Run:  py extra_utilities/smoke_test_attempt_renders.py
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

# agents/__init__ eagerly imports every agent class, which needs langchain.
# Stub the package so agents.shared.* is importable on its own.
for _n, _r in (("agents", "agents"), ("agents.shared", "agents/shared")):
    _m = types.ModuleType(_n)
    _m.__path__ = [str(ROOT / _r)]
    sys.modules.setdefault(_n, _m)

from agents.shared import attempt_views as av            # noqa: E402
from agents.shared import attempt_renders as ar          # noqa: E402
from workflow_settings import settings as st             # noqa: E402

_FAILS: list[str] = []


def check(name: str, cond: bool, detail: object = "") -> None:
    print(("  PASS  " if cond else "  FAIL  ") + name
          + ("" if cond else "\n          -> " + str(detail)[:300]))
    if not cond:
        _FAILS.append(name)


class _Flags:
    """Force the four view flags + the two completion settings."""

    def __init__(self, **kw):
        self.kw, self.old = kw, {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.old[k] = getattr(st, k, None)
            setattr(st, k, v)
        return self

    def __exit__(self, *e):
        for k, v in self.old.items():
            setattr(st, k, v)
        return False


ALL_ON = dict(ATTEMPT_VIEW_ISOMETRIC=True, ATTEMPT_VIEW_TOP=True,
              ATTEMPT_VIEW_BLADE_SECTIONS=True, ATTEMPT_VIEW_SIDE=True,
              ATTEMPT_RENDER_COMPLETION_ON_SAVE=True,
              ATTEMPT_RENDER_COMPLETION_TIMEOUT_S=120)
DEFAULTS = dict(ATTEMPT_VIEW_ISOMETRIC=True, ATTEMPT_VIEW_TOP=True,
                ATTEMPT_VIEW_BLADE_SECTIONS=True, ATTEMPT_VIEW_SIDE=False,
                ATTEMPT_RENDER_COMPLETION_ON_SAVE=True,
                ATTEMPT_RENDER_COMPLETION_TIMEOUT_S=120)

CALLS: dict = {}


def _install_stubs(*, sections_ok=True, core_ok=True, geom_ok=True,
                   sections_raises=False, core_raises=False,
                   geom_raises=False):
    """Fake the three tool entry points ensure_renders imports lazily."""
    CALLS.clear()
    CALLS.update(sections=[], core=[], geom=[])

    def _sections(parameters_path, grid=False):
        CALLS["sections"].append(parameters_path)
        if sections_raises:
            raise RuntimeError("stub blade-sections failure")
        if sections_ok:
            (Path(parameters_path).parent
             / "render_blade_sections.png").write_bytes(b"PNG")
        return "ok"

    def _core(mesh_path, output_dir):
        CALLS["core"].append((mesh_path, output_dir))
        if core_raises:
            raise RuntimeError("stub render-core failure")
        if core_ok:
            for f in ("render_isometric.png", "render_top.png",
                      "render_side.png"):
                (Path(output_dir) / f).write_bytes(b"PNG")
        return "ok"

    def _geom(parameters_path):
        CALLS["geom"].append(parameters_path)
        if geom_raises:
            raise RuntimeError("stub geometry failure")
        if geom_ok:
            d = Path(parameters_path).parent
            (d / "propeller_mesh.obj").write_text("o mesh\n", encoding="utf-8")
            for f in ("render_isometric.png", "render_top.png",
                      "render_side.png"):
                (d / f).write_bytes(b"PNG")
        return "ok"

    bs_pkg = types.ModuleType("tools.render_blade_sections")
    bs_mod = types.ModuleType("tools.render_blade_sections.render_blade_sections")
    bs_mod.render_blade_sections = _sections
    gm_pkg = types.ModuleType("tools.generate_mesh")
    gm_mod = types.ModuleType("tools.generate_mesh.generate_mesh")
    gm_mod.generate_and_render_propeller = _geom
    tools_mod = types.ModuleType("tools")
    tools_mod.__path__ = []
    tools_mod.get_render_core = lambda: _core

    sys.modules["tools"] = tools_mod
    sys.modules["tools.render_blade_sections"] = bs_pkg
    sys.modules["tools.render_blade_sections.render_blade_sections"] = bs_mod
    sys.modules["tools.generate_mesh"] = gm_pkg
    sys.modules["tools.generate_mesh.generate_mesh"] = gm_mod


def _attempt(tmp: Path, *, params=True, mesh=False, renders=()) -> Path:
    d = tmp / "20260821_120000_001_test"
    d.mkdir(parents=True)
    if params:
        (d / "parameters.json").write_text(json.dumps({"bladeCount": 5}),
                                           encoding="utf-8")
    if mesh:
        (d / "propeller_mesh.obj").write_text("o mesh\n", encoding="utf-8")
    for r in renders:
        (d / r).write_bytes(b"PNG")
    return d


print("=" * 66)
print("PART A - the view registry")
print("=" * 66)

print("case 1 - enabled_views tracks the flags")
with _Flags(**DEFAULTS):
    check("defaults are isometric, top, blade_sections (side OFF)",
          av.enabled_views() == ["isometric", "top", "blade_sections"],
          av.enabled_views())
    check("blade sections render from parameters alone",
          av.PARAMS_ONLY_VIEWS == frozenset({"blade_sections"}))
with _Flags(**ALL_ON):
    check("all four when all on",
          av.enabled_views() == ["isometric", "top", "blade_sections", "side"],
          av.enabled_views())
with _Flags(ATTEMPT_VIEW_ISOMETRIC=False, ATTEMPT_VIEW_TOP=False,
            ATTEMPT_VIEW_BLADE_SECTIONS=False, ATTEMPT_VIEW_SIDE=False):
    check("none when all off", av.enabled_views() == [], av.enabled_views())
check("unknown view is not enabled", av.is_enabled("nope") is False)

print("case 2 - the R2 whitelist follows the flags")
from agents.shared import r2_uploader as r2                # noqa: E402
with _Flags(**DEFAULTS):
    wl = r2.attempt_artefact_whitelist()
    check("base artefacts present",
          {"parameters.json", "propeller_mesh.obj", "description.txt"} <= set(wl),
          wl)
    check("blade sections IS archived now", "render_blade_sections.png" in wl, wl)
    check("side is NOT (flag off)", "render_side.png" not in wl, wl)
with _Flags(**ALL_ON):
    check("side appears when its flag goes on",
          "render_side.png" in r2.attempt_artefact_whitelist())

print()
print("=" * 66)
print("PART B - the save-time completion pass")
print("=" * 66)

print("case 3/4 - it skips cleanly")
with tempfile.TemporaryDirectory() as td, _Flags(**DEFAULTS):
    _install_stubs()
    d = _attempt(Path(td), params=False)
    r = ar.ensure_renders(d)
    check("no parameters.json -> skipped, nothing called",
          r["skipped"] == "no parameters.json" and not CALLS["sections"], r)
with tempfile.TemporaryDirectory() as td, _Flags(**dict(DEFAULTS,
                                                        ATTEMPT_RENDER_COMPLETION_ON_SAVE=False)):
    _install_stubs()
    d = _attempt(Path(td))
    r = ar.ensure_renders(d)
    check("master switch off -> skipped",
          "ON_SAVE is off" in (r["skipped"] or ""), r)

print("case 5 - a complete attempt generates nothing")
with tempfile.TemporaryDirectory() as td, _Flags(**DEFAULTS):
    _install_stubs()
    d = _attempt(Path(td), mesh=True,
                 renders=("render_isometric.png", "render_top.png",
                          "render_blade_sections.png"))
    r = ar.ensure_renders(d)
    check("all three found, none generated",
          sorted(r["found"]) == ["blade_sections", "isometric", "top"]
          and not r["generated"] and not r["failed"], r)
    check("no tool was invoked",
          not CALLS["sections"] and not CALLS["core"] and not CALLS["geom"])

print("case 6 - a missing blade-sections render is created")
with tempfile.TemporaryDirectory() as td, _Flags(**DEFAULTS):
    _install_stubs()
    d = _attempt(Path(td), mesh=True,
                 renders=("render_isometric.png", "render_top.png"))
    r = ar.ensure_renders(d)
    check("generated from parameters.json",
          r["generated"] == ["blade_sections"] and not r["failed"], r)
    check("the tool got the PARAMETERS path",
          CALLS["sections"] == [str((d / "parameters.json").resolve())],
          CALLS["sections"])
    check("the render core was NOT needed", not CALLS["core"])

print("case 7 - a missing 3D view, mesh present -> render core once")
with tempfile.TemporaryDirectory() as td, _Flags(**DEFAULTS):
    _install_stubs()
    d = _attempt(Path(td), mesh=True, renders=("render_blade_sections.png",))
    r = ar.ensure_renders(d)
    check("isometric + top generated",
          sorted(r["generated"]) == ["isometric", "top"], r)
    check("the core ran exactly ONCE for the whole set",
          len(CALLS["core"]) == 1, CALLS["core"])
    check("geometry generation was NOT triggered", not CALLS["geom"])

print("case 8 - a missing 3D view, NO mesh -> geometry tool")
with tempfile.TemporaryDirectory() as td, _Flags(**DEFAULTS):
    _install_stubs()
    d = _attempt(Path(td), mesh=False, renders=("render_blade_sections.png",))
    r = ar.ensure_renders(d)
    check("the geometry tool ran", len(CALLS["geom"]) == 1, CALLS["geom"])
    check("it was given the PARAMETERS path, not a folder or kwargs",
          CALLS["geom"] == [str((d / "parameters.json").resolve())],
          CALLS["geom"])
    check("isometric + top generated",
          sorted(r["generated"]) == ["isometric", "top"], r)
    check("a mesh now exists", (d / "propeller_mesh.obj").is_file())

print("case 9/10 - failures never propagate, and never block the cheap one")
with tempfile.TemporaryDirectory() as td, _Flags(**DEFAULTS):
    _install_stubs(core_raises=True)
    d = _attempt(Path(td), mesh=True, renders=("render_blade_sections.png",))
    try:
        r = ar.ensure_renders(d)
        raised = None
    except Exception as exc:            # noqa: BLE001
        r, raised = None, exc
    check("a raising render core does NOT propagate", raised is None, raised)
    check("both 3D views recorded as failed",
          r and sorted(v for v, _w in r["failed"]) == ["isometric", "top"], r)
with tempfile.TemporaryDirectory() as td, _Flags(**DEFAULTS):
    _install_stubs(geom_raises=True)
    d = _attempt(Path(td), mesh=False)
    r = ar.ensure_renders(d)
    check("blade sections still generated with the geometry backend dead",
          "blade_sections" in r["generated"], r)
    check("the 3D views are the only failures",
          sorted(v for v, _w in r["failed"]) == ["isometric", "top"], r)
    check("log_report does not raise on a mixed result",
          ar.log_report(d, r) is None)

print("case 11 - the retrieve tool sees blade sections")
import ast                                                  # noqa: E402
_ra_src = (ROOT / "tools" / "retrieve_attempt"
           / "retrieve_attempt.py").read_text(encoding="utf-8")
check("retrieve_attempt builds its view map from the shared registry",
      "attempt_views.VIEW_FILES" in _ra_src and "attempt_views.VIEWS" in _ra_src)
check("blade sections is in the registry's file map",
      av.VIEW_FILES.get("blade_sections") == "render_blade_sections.png")

print()
if _FAILS:
    print("FAIL - %d assertion(s): %s" % (len(_FAILS), _FAILS))
    sys.exit(1)
print("PASS - views resolve from one registry; the save-time pass completes "
      "what it can and never breaks the save.")
