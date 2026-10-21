"""The pack's tools, offline: manifests, settings, role binding and what the
two propeller tools answer.

Since MAS-blueprint P3c the generator and the blade-sections tool live in
``setups/<setup>/tools/<tool>/`` (a ``tool.yaml`` + plain Python) and the engine
(``engine/pack_tools.py``) loads them, builds their LLM tools, binds them by
role and owns their settings.  Four groups of checks:

1. MANIFESTS.  Every ``tool.yaml`` is valid; each tool builds its LLM tool
   under its own name; the views come in their declared order.
2. SETTINGS.  Defaults come from the manifests; a value the manifest does
   not allow, an unknown setting or an unknown tool is refused; saving
   stores only changes and resetting removes the file (a temporary path,
   never the real one); the prompt flags and view switches follow.
3. BINDING.  The tool runner -- the Tool Caller in topologies 7 and 5, the
   Design Engineer in 3 -- gets the generator and, while its switch is on,
   blade sections; no other agent gets either.
4. GOLDEN.  23 cases -- the generator with stand-in geometry and render
   back-ends (new mesh, reuse, fallback, both back-ends failing, bad or
   missing records, a folder outside ``attempts/``, a render failure) and
   the blade-sections tool for real -- must answer exactly what the tools
   answered BEFORE the move (``fixtures/pack_tools_golden.json``, recorded
   on the pre-P3c code): the text, the files written, the back-end calls.
   Image bytes and pixel sizes are left out (they depend on the fonts).

Since MAS-blueprint P3d each tool also owns the prompt text about it
(``prompts/`` in its folder, listed under ``prompt_slots``), and the tool
runner's numbered tool list is built from each tool's entry:

5. TOOL TEXTS.  Every tool-text slot of the registry is claimed by exactly
   one tool and has its files in that tool's ``prompts/``; and each rule is
   enforced -- a copy of the pack broken in one way (a slot claimed twice, a
   listed slot with no file, a stray file, tool text left in ``fragments/``,
   a non-tool slot listed, a missing ``list_order`` or list entry) is
   refused, naming the problem.
6. TOOL LIST.  The engine-built list equals, byte for byte, the six
   hand-numbered lists the prompts carried before P3d
   (``fixtures/tool_lists.json``: topologies 7 / 5 / 3, blade sections on
   and off); no other agent gets one.
7. REMOVAL.  A copy of the pack WITHOUT the blade-sections folder (and a
   Workflow Settings value still saved for it) builds every prompt of the
   three topologies; none names the tool or its "visualizer" note, its
   slots read empty, its view and its list entry are gone, and the tool
   runner is given the generator only.

Since MAS-blueprint P4b the engine names none of the tools' files or
settings -- the manifests declare them (the picture contract):

8. CONTRACT.  A copy of the pack breaking the picture contract in one way
   (a picture not named render_<view>.png, a missing or unknown
   ``compression``, no ``fill_on_save``, a malformed ``image_note``, a
   runtime block reading a slot the tool does not own or naming a bool
   setting) is refused, naming the problem.
9. SAVE STEP.  With stand-in tools, the save step makes a missing picture
   with the tool that declares it -- the helper first, then the generator
   (building the model when absent, rendering only when present) -- and
   does not use a tool whose ``fill_on_save`` is false.
10. COMPRESSION.  Each picture's shrink strength, now declared, is the one
   today's file-name rule picked.
11. BLOCK.  The generator's runtime block picks, for every setting, the
   render-check slot the engine used to pick by name.

Since MAS-blueprint P4c the geometry is made by geometry tools of their
own (``kind: geometry``: ``feg_geometry``, ``rhino_geometry``), which the
generator's ``geometry_tool`` / ``fallback_geometry_tool`` settings and
the Download buttons' choice pick (``engine/pack_tools.make_model``):

12. GEOMETRY.  Both load as geometry tools no agent is given, making the
   generator's model format; the generator's two settings list them
   (with "none" for the fallback) and the Downloads choice lists them
   and "the saved file", with its default from ``pack.yaml``; a value
   still saved for the removed ``geometry_backend`` setting is skipped;
   ``make_model`` with stand-in geometry tools uses the first, falls back
   to the second, raises one tool's own error or -- when both fail -- the
   two by display name, and passes the files a tool adds; and five
   broken copies of the pack (a geometry tool with roles, without
   entrypoint or with another format, a setting naming a geometry tool
   the pack lacks, a tool folder called ``downloads``) are refused.
13. IMAGE RUN.  ``engine/image_run.run`` (the generic Preview, the
   render-compression samples) with stand-in tools: the helpers first,
   called with the parameter file, then the generator; only switched-on
   views; the run's own attempts root (the session's restored after);
   errors reported per tool; the samples keep, per compression kind, the
   first picture of that kind for each of ``pack.yaml``'s sample sets,
   and a sample set missing a parameter is refused.

Since MAS-blueprint P5 (G1) what is read from the tools' files is kept while
they are unchanged (``engine/pack.py``: stamps of size and modification
time):

14. KEPT.  On a copy of the pack, a second call reads no ``tool.yaml``
   again; each caller gets a copy of its own; and the next call sees a
   ``tool.yaml`` edited without changing its size, one edited in the same
   instant as the read before it (same stamp), a tool folder removed or
   added, a file added to a tool's ``prompts/`` folder or tool text put in
   ``fragments/`` (the ownership checks run again), and a changed claim.
   Since P5b the same holds for a text's files: an agent copy or a
   per-topology file added, removed or renamed is seen on the next read
   (also when the folder's stamp did not move), and a text edited in place
   always is; a process that holds its stamps (the Studio's short-lived
   processes) does not see a file added after its first read, while a
   process that does not hold them does.

Run from the repo root:  py -3.13 extra_utilities/tests/smoke_test_pack_tools.py

Since MAS-blueprint P6c a tool declares the environment variables it reads:

15. SECRETS.  ``rhino_geometry`` declares RHINO_COMPUTE_URL and
   RHINO_COMPUTE_API_KEY; a copy of the pack whose declaration is broken in
   one way (a name not in capitals, no description, a name twice, an
   unknown field, ``required`` not true / false) is refused, naming the
   problem.
16. OUTPUTS.  Each picture view, and each generator's model file, is one
   tool's: a copy of the pack where a second tool declares the same view,
   or a second generator the same model file, is refused.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "extra_utilities" / "prompt_pdf"))
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
sys.modules["simplejson"] = None          # type: ignore[assignment]
sys.modules["chardet"] = None             # type: ignore[assignment]
import bootstrap                          # noqa: E402

bootstrap.install()

import agents                             # noqa: E402,F401
import config                             # noqa: E402
from engine import pack_tools as T        # noqa: E402

from engine import pack as PK            # noqa: E402

FAILURES: list[str] = []
FIXTURE = ROOT / "extra_utilities" / "tests" / "fixtures" / "pack_tools_golden.json"
LISTS = ROOT / "extra_utilities" / "tests" / "fixtures" / "tool_lists.json"
GEN, SEC = "generate_and_render_propeller", "render_blade_sections"


def check(ok: bool, what: str) -> None:
    if not ok:
        FAILURES.append(what)


# ---------------------------------------------------------------------------
# 1-3
# ---------------------------------------------------------------------------

def check_manifests() -> None:
    try:
        m = T.manifests()
    except T.PackToolError as exc:
        check(False, f"[MANIFEST] {exc}")
        return
    check(set(m) >= {GEN, SEC}, f"[MANIFEST] tools found: {sorted(m)}")
    check(T.generators() == [GEN], f"[MANIFEST] generators: {T.generators()}")
    for name in (n for n in m if m[n]["kind"] in T.KINDS):
        t = T.llm_tool(name)
        check(t.name == name and t.description.strip(),
              f"[MANIFEST] {name}: LLM tool name {t.name!r} / empty description")
    views = [r["view"] for r in T.image_outputs()]
    check(views == ["isometric", "top", "blade_sections", "side"],
          f"[MANIFEST] view order {views}")


def check_settings() -> None:
    check(T.settings(GEN) == {"geometry_tool": "feg_geometry",
                              "fallback_geometry_tool": "rhino_geometry",
                              "render_library": "trimesh",
                              "mesh_checks": False, "view_isometric": True,
                              "view_top": True, "view_side": False},
          f"[SETTINGS] generator defaults {T.settings(GEN)}")
    check(T.settings(SEC) == {"enabled": True, "view_blade_sections": True},
          f"[SETTINGS] blade-sections defaults {T.settings(SEC)}")
    real = T.OVERRIDES_PATH
    with tempfile.TemporaryDirectory() as tmp:
        T.OVERRIDES_PATH = Path(tmp) / "tool_settings.json"
        try:
            stored = T.save_overrides({GEN: dict(T.defaults(GEN), mesh_checks=True),
                                       SEC: T.defaults(SEC)})
            check(stored == {GEN: {"mesh_checks": True}},
                  f"[SETTINGS] stored {stored}, expected only the changed value")
            check(T.settings(GEN)["mesh_checks"] is True
                  and T.flag_values()[f"setting:{GEN}.mesh_checks"] is True,
                  "[SETTINGS] a saved value does not reach settings / flags")
            for bad in ({GEN: {"render_library": "blender"}}, {GEN: {"nope": 1}},
                        {"ghost": {"enabled": True}}, {SEC: {"enabled": "yes"}}):
                try:
                    T.save_overrides(bad)
                    check(False, f"[SETTINGS] {bad} was accepted")
                except T.PackToolError:
                    pass
            T.save_overrides({SEC: {"enabled": False, "view_blade_sections": False}})
            check(not T.is_enabled(SEC) and not T.flag_values()[f"tool:{SEC}"]
                  and not T.view_enabled("blade_sections"),
                  "[SETTINGS] switching blade sections off does not reach the flags / views")
            T.reset_overrides()
            check(not T.OVERRIDES_PATH.exists() and T.is_enabled(SEC),
                  "[SETTINGS] reset did not go back to the defaults")
        finally:
            T.OVERRIDES_PATH = real


def check_binding() -> None:
    from agents.shared import agent_roles
    from workflow_settings import settings as S
    runner = {7: "tool_caller", 5: "tool_caller", 3: "design_engineer"}
    saved = S.SYSTEM_TOPOLOGY
    try:
        for topo in runner:
            S.SYSTEM_TOPOLOGY = topo
            keys = agent_roles.roster(topo)
            check(runner[topo] in keys, f"[BINDING] topology {topo}: roster {keys}")
            for key in keys:
                gens = [t.name for t in T.agent_tools(key, ("generator",))]
                helpers = [t.name for t in T.agent_tools(key, ("helper",))]
                want = ([GEN], [SEC]) if key == runner[topo] else ([], [])
                check((gens, helpers) == want,
                      f"[BINDING] topology {topo} {key}: {gens} + {helpers}, want {want}")
            T.settings_override_for_tests({SEC: {"enabled": False}})
            check([t.name for t in T.agent_tools(runner[topo], ("helper",))] == [],
                  f"[BINDING] topology {topo}: blade sections bound while switched off")
            T.settings_override_for_tests(None)
    finally:
        S.SYSTEM_TOPOLOGY = saved
        T.settings_override_for_tests(None)


# ---------------------------------------------------------------------------
# 5-7. The text each tool owns, the tool list, removing a tool
# ---------------------------------------------------------------------------

def _pack_copy() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="pack_copy_"))
    shutil.copytree(PK.pack_dir(), tmp / "dc_pack",
                    ignore=shutil.ignore_patterns("__pycache__"))
    return tmp / "dc_pack"


def _append(path: Path, text: str) -> None:
    path.write_bytes(path.read_bytes() + text.encode("utf-8"))


def check_tool_texts() -> int:
    tool_text = {s for s, sp in PK.registry().items() if sp.get("filled_by") == "tool"}
    claims = PK.tool_claims()
    check(set(claims) == tool_text,
          f"[TEXTS] tool-text slots no tool claims: {sorted(tool_text - set(claims))}; "
          f"claimed but not tool text: {sorted(set(claims) - tool_text)}")
    for slot, tool in sorted(claims.items()):
        files = [p for p in PK.fragment_files() if PK.slot_of_file(p.name) == slot]
        check(bool(files) and all(p.parent == PK.tool_prompts_dir(tool) for p in files),
              f"[TEXTS] ${slot} ({tool}): files {[p.as_posix() for p in files]}")

    tools = lambda d: d / "tools"                                   # noqa: E731
    cases = [
        ("a slot claimed by both tools",
         lambda d: _append(tools(d) / SEC / "tool.yaml", "  - geometry_tool_name\r\n"),
         "claimed by both"),
        ("a listed slot with no file",
         lambda d: (tools(d) / GEN / "prompts" / "geometry_editing_ban.md").unlink(),
         "no file for $geometry_editing_ban"),
        ("a file no listed slot owns",
         lambda d: shutil.copy(tools(d) / GEN / "prompts" / "geometry_editing_ban.md",
                               tools(d) / SEC / "prompts" / "geometry_editing_ban.md"),
         "is not in the tool's prompt_slots"),
        ("tool text left in fragments/",
         lambda d: shutil.copy(tools(d) / GEN / "prompts" / "geometry_editing_ban.md",
                               d / "fragments" / "tools" / "geometry_editing_ban.md"),
         "is tool text"),
        ("a non-tool slot listed",
         lambda d: _append(tools(d) / GEN / "tool.yaml", "  - dc_name\r\n"),
         "is not a tool-text slot"),
        ("no list_order",
         lambda d: (tools(d) / SEC / "tool.yaml").write_bytes(re.sub(
             rb"(?m)^list_order: \d+\r?\n", b"", (tools(d) / SEC / "tool.yaml").read_bytes())),
         "needs list_order"),
        ("no tool-list entry",
         lambda d: (tools(d) / SEC / "prompts" / "tool_list_entry.md").unlink(),
         "tool_list_entry.md"),
    ]
    return _refused(cases, "[TEXTS]")


def _refused(cases, tag: str) -> int:
    """Each (what, break-the-copy, expected words) must make the manifests
    refuse a copy of the pack, naming the problem."""
    real = config.DC_PACK_DIR
    for what, breakit, needle in cases:
        copy = _pack_copy()
        try:
            breakit(copy)
            config.DC_PACK_DIR = copy
            try:
                T.manifests()
                check(False, f"{tag} {what}: the broken pack was accepted")
            except T.PackToolError as exc:
                check(needle in str(exc), f"{tag} {what}: refused, but not for "
                                          f"that reason: {str(exc)[:200]}")
        finally:
            config.DC_PACK_DIR = real
            shutil.rmtree(copy.parent, ignore_errors=True)
    return len(cases)


def _rewrite(path: Path, old: str, new: str) -> None:
    text = path.read_bytes().decode("utf-8")
    assert text.count(old) == 1, (path, old)
    path.write_bytes(text.replace(old, new).encode("utf-8"))


# ---------------------------------------------------------------------------
# 8-11. The picture contract, the save step, the shrink strength, the
# runtime block (MAS-blueprint P4b)
# ---------------------------------------------------------------------------

def check_contract() -> int:
    gen = lambda d: d / "tools" / GEN / "tool.yaml"                  # noqa: E731
    sec = lambda d: d / "tools" / SEC / "tool.yaml"                  # noqa: E731
    cases = [
        ("a picture named against the rule",
         lambda d: _rewrite(gen(d), "file: render_top.png", "file: top.png"),
         "must be the file 'render_top.png'"),
        ("a picture without its compression",
         lambda d: _rewrite(gen(d), "default_enabled: true, compression: 3d_render, "
                                    "label: \"Render view: isometric\"",
                            "default_enabled: true, label: \"Render view: isometric\""),
         "needs view, file, order, default_enabled, compression"),
        ("an unknown compression",
         lambda d: _rewrite(sec(d), "compression: cross_sections", "compression: heavy"),
         "compression is one of"),
        ("a picture-making tool that does not say fill_on_save",
         lambda d: _rewrite(sec(d), "fill_on_save: true", ""),
         "fill_on_save"),
        ("an image_note that is not module.py:function",
         lambda d: _rewrite(sec(d), "image_note: sections_geom.py:rendered_params_block",
                            "image_note: rendered_params_block"),
         "image_note must be"),
        ("a runtime block reading a slot the tool does not own",
         lambda d: _rewrite(gen(d), "off_slot: render_check_library_off",
                            "off_slot: tool_caller_instructions"),
         "not in the tool's prompt_slots"),
        ("a runtime block whose slot names a bool setting",
         lambda d: _rewrite(gen(d), "slot: render_check_library_${render_library}",
                            "slot: render_check_library_${mesh_checks}"),
         "may only name enum settings"),
    ]
    return _refused(cases, "[CONTRACT]")


def check_save_step() -> int:
    """The save step (agents/shared/attempt_renders.py) asks the tool that
    declares a missing picture to make it: helpers first, then the
    generator; a tool whose fill_on_save is false is not used."""
    from agents.shared import attempt_renders as AR
    folder = Path(tempfile.mkdtemp(prefix="save_step_")) / "20260101_000000_001_x"
    folder.mkdir()
    params = {p["name"]: p["default"] for p in json.loads(
        (ROOT / "setups" / "propeller" / "parameters.json").read_text(encoding="utf-8"))["parameters"]}
    (folder / "parameters.json").write_text(json.dumps(params), encoding="utf-8")
    calls: list = []
    real = (T.Plugin.function, T.run_generator, T.render_existing, config.DC_PACK_DIR)

    def fake_function(self, ref):
        def fn(parameters_path, *a, **k):
            calls.append(("helper", self.name))
            (Path(parameters_path).parent / "render_blade_sections.png").write_bytes(b"p")
            return "drawn"
        return fn

    def draw_generator_pictures(where: Path) -> None:
        for name in ("render_isometric.png", "render_top.png"):
            (where / name).write_bytes(b"p")

    def fake_run(name, parameters_path):
        calls.append(("build", name))
        (Path(parameters_path).parent / T.model_file()).write_text("v 0 0 0\n")
        draw_generator_pictures(Path(parameters_path).parent)
        return "built"

    def fake_render(name, attempt_dir):
        calls.append(("render", name))
        draw_generator_pictures(Path(attempt_dir))
        return "rendered"

    cases = 0
    try:
        T.Plugin.function, T.run_generator, T.render_existing = fake_function, fake_run, fake_render
        report = AR.ensure_renders(folder)
        cases += 1
        check(calls == [("helper", SEC), ("build", GEN)],
              f"[SAVE STEP] calls {calls}: want the blade-sections tool, then the generator's build")
        check(sorted(report["generated"]) == ["blade_sections", "isometric", "top"]
              and not report["failed"], f"[SAVE STEP] report {report}")
        # The model is there now: a missing picture is rendered, not rebuilt.
        (folder / "render_top.png").unlink()
        calls.clear()
        report = AR.ensure_renders(folder)
        cases += 1
        check(calls == [("render", GEN)] and report["generated"] == ["top"],
              f"[SAVE STEP] with the model present: calls {calls}, report {report}")
        # A tool that may not fill pictures at save time is not used.
        copy = _pack_copy()
        _rewrite(copy / "tools" / SEC / "tool.yaml", "fill_on_save: true", "fill_on_save: false")
        config.DC_PACK_DIR = copy
        (folder / "render_blade_sections.png").unlink()
        calls.clear()
        report = AR.ensure_renders(folder)
        cases += 1
        check(calls == [] and report["failed"] == [
            ("blade_sections", "its tool does not add pictures at save time")],
              f"[SAVE STEP] fill_on_save false: calls {calls}, report {report}")
        shutil.rmtree(copy.parent, ignore_errors=True)
    except Exception as exc:                                        # noqa: BLE001
        check(False, f"[SAVE STEP] {type(exc).__name__}: {str(exc)[:200]}")
    finally:
        T.Plugin.function, T.run_generator, T.render_existing, config.DC_PACK_DIR = real
        shutil.rmtree(folder.parent, ignore_errors=True)
    return cases


def check_compression() -> None:
    """The shrink strength of each picture, now declared in the manifests,
    is the one today's file-name rule picked."""
    from agents.shared import image_compression as IC
    want = {"render_blade_sections.png": "cross", "render_blade_sections_grid.png": "cross",
            "render_isometric.png": "3d", "render_top.png": "3d", "render_side.png": "3d",
            "render_comparison_1.png": None, "render_unknown.png": None, "sketch.png": None}
    for name, kind in want.items():
        check(IC.render_kind(name) == kind,
              f"[COMPRESSION] {name}: {IC.render_kind(name)!r}, want {kind!r}")


def check_runtime_block() -> None:
    """The generator's runtime block picks, for every setting, the slot the
    engine used to pick by name."""
    snap = T.settings_snapshot()
    for mesh, lib, want in ((False, "trimesh", "render_check_library_off"),
                            (False, "pyvista", "render_check_library_off"),
                            (True, "trimesh", "render_check_library_trimesh"),
                            (True, "pyvista", "render_check_library_pyvista")):
        s = {**snap, GEN: {**snap[GEN], "mesh_checks": mesh, "render_library": lib}}
        got = T.runtime_block_slot("render_check_library_block", s)
        check(got == want, f"[BLOCK] mesh_checks={mesh} render_library={lib}: {got}, want {want}")
    check(T.runtime_block_slot("no_such_block", snap) is None,
          "[BLOCK] a placeholder no tool declares gave a slot")


def check_geometry() -> int:
    """The geometry tools, the settings that pick them, make_model, and
    the manifests it refuses."""
    from engine.tooling import GeometryResult, ToolError
    FEG, RH = "feg_geometry", "rhino_geometry"
    try:
        check(T.geometry_tools() == [FEG, RH], f"[GEOMETRY] geometry tools {T.geometry_tools()}")
        check(all(T.manifest(n)["outputs"]["model_format"] == "obj" for n in (FEG, RH))
              and T.model_info() == {"file": "propeller_mesh.obj", "ext": ".obj",
                                     "format": "obj", "media_type": "model/obj",
                                     "up_axis": "z"},
              f"[GEOMETRY] model info {T.model_info()}")
        for n in (FEG, RH):
            try:
                T.llm_tool(n)
                check(False, f"[GEOMETRY] {n} became an LLM tool")
            except T.PackToolError:
                pass
        specs = {s["name"]: s for s in T.setting_specs(GEN)}
        check(specs["geometry_tool"]["values"] == [FEG, RH]
              and specs["fallback_geometry_tool"]["values"] == [FEG, RH, "none"]
              and specs["geometry_tool"]["labels"] == {FEG: "FEG", RH: "RhinoCompute"},
              f"[GEOMETRY] the generator's geometry settings: {specs['geometry_tool']} "
              f"{specs['fallback_geometry_tool']}")
        dl = T.setting_specs(T.DOWNLOADS)[0]
        check(dl["values"] == [FEG, RH, "saved"] and dl["default"] == RH
              and T.download_tool() == RH and dl["labels"]["saved"] == "the saved file",
              f"[GEOMETRY] the Downloads choice: {dl}")
        check(T.geometry_order(T.settings(GEN)) == [FEG, RH]
              and T.geometry_order({"geometry_tool": RH, "fallback_geometry_tool": "none"}) == [RH]
              and T.geometry_order({"geometry_tool": FEG, "fallback_geometry_tool": FEG}) == [FEG],
              "[GEOMETRY] geometry_order")
        # A value saved for the removed geometry_backend setting is skipped.
        real = T.OVERRIDES_PATH
        with tempfile.TemporaryDirectory() as tmp:
            T.OVERRIDES_PATH = Path(tmp) / "tool_settings.json"
            try:
                T.OVERRIDES_PATH.write_text(json.dumps(
                    {GEN: {"geometry_backend": "rhino", "mesh_checks": True},
                     "downloads": {"geometry_tool": FEG}}), encoding="utf-8")
                check(T.settings(GEN)["mesh_checks"] is True
                      and "geometry_backend" not in T.settings(GEN)
                      and T.download_tool() == FEG,
                      f"[GEOMETRY] stale saved settings: {T.settings(GEN)}")
                for bad in ({"downloads": {"geometry_tool": "blender"}},
                            {GEN: {"geometry_tool": "none"}}):
                    try:
                        T.save_overrides(bad)
                        check(False, f"[GEOMETRY] {bad} was accepted")
                    except T.PackToolError:
                        pass
            finally:
                T.OVERRIDES_PATH = real
        # make_model with stand-in geometry tools.
        made: list = []
        behaviour = {}
        real_fn = T.Plugin.function

        def fake_function(self, ref):
            if self.name not in (FEG, RH):
                return real_fn(self, ref)

            def fn(params):
                made.append(self.name)
                if behaviour[self.name]:
                    raise ToolError(behaviour[self.name])
                return GeometryResult(f"v {self.name}", 1,
                                      {"extra.txt": "x"} if self.name == RH else {})
            return fn
        T.Plugin.function = fake_function
        try:
            p = {"a": 1}
            behaviour.update({FEG: None, RH: None})
            r = T.make_model(p, [FEG, RH])
            check(made == [FEG] and (r.made_by, r.chosen) == ("FEG", "FEG")
                  and r.result.model == f"v {FEG}", f"[GEOMETRY] first tool: {made} {r}")
            made.clear()
            behaviour.update({FEG: "FEG error: no node"})
            r = T.make_model(p, [FEG, RH])
            check(made == [FEG, RH] and (r.made_by, r.chosen) == ("RhinoCompute", "FEG")
                  and r.result.extra_files == {"extra.txt": "x"},
                  f"[GEOMETRY] fallback: {made} {r}")
            behaviour.update({RH: "RhinoCompute error: refused"})
            for order, want in (([FEG, RH], "All geometry backends failed — FEG: FEG error: "
                                             "no node | RhinoCompute: RhinoCompute error: refused"),
                                 ([FEG], "FEG error: no node")):
                try:
                    T.make_model(p, order)
                    check(False, f"[GEOMETRY] {order}: both failing gave a model")
                except ToolError as exc:
                    check(str(exc) == want, f"[GEOMETRY] {order}: {exc!s} != {want!r}")
        finally:
            T.Plugin.function = real_fn
    except Exception as exc:                                        # noqa: BLE001
        check(False, f"[GEOMETRY] {type(exc).__name__}: {str(exc)[:200]}")
    tools = lambda d: d / "tools"                                   # noqa: E731
    cases = [
        ("a geometry tool with roles",
         lambda d: _append(tools(d) / FEG / "tool.yaml", "roles: [tool_runner]\r\n"),
         "a geometry tool has no roles"),
        ("a geometry tool without entrypoint",
         lambda d: _rewrite(tools(d) / RH / "tool.yaml",
                            "entrypoint: rhino_geometry.py:make_model", ""),
         "entrypoint must be"),
        ("a geometry tool making another format",
         lambda d: _rewrite(tools(d) / FEG / "tool.yaml", "model_format: obj",
                            "model_format: glb"),
         "a geometry tool's outputs are exactly model_format"),
        ("a setting naming a geometry tool the pack lacks",
         lambda d: shutil.rmtree(tools(d) / FEG),
         "is not one of the pack's geometry tools"),
        ("a tool folder called downloads",
         lambda d: (shutil.copytree(tools(d) / FEG, tools(d) / "downloads"),
                    _rewrite(tools(d) / "downloads" / "tool.yaml", "name: feg_geometry",
                             "name: downloads")),
         "is reserved"),
    ]
    return _refused(cases, "[GEOMETRY]")


def check_image_run() -> int:
    """The image runner's order, views, attempts root, errors and samples,
    with stand-in tools."""
    from engine import image_run as IR
    cases = 0
    root = Path(tempfile.mkdtemp(prefix="image_run_")).resolve()
    calls: list = []
    real = (T.Plugin.function, T.run_generator, config.ATTEMPTS_DIR, IR.run_in_child)
    params = {p["name"]: p["default"] for p in json.loads(
        (ROOT / "setups" / "propeller" / "parameters.json").read_text(encoding="utf-8"))["parameters"]}

    def fake_function(self, ref):
        def fn(parameters_path, *a, **k):
            calls.append(("helper", self.name, str(config.ATTEMPTS_DIR) == str(root)))
            (Path(parameters_path).parent / "render_blade_sections.png").write_bytes(b"sec")
            return "drawn"
        return fn

    def fake_run(name, parameters_path):
        calls.append(("generator", name, str(config.ATTEMPTS_DIR) == str(root)))
        for f in ("render_isometric.png", "render_top.png", "render_side.png"):
            (Path(parameters_path).parent / f).write_bytes(f.encode())
        return "Mesh saved.\n\nreport"
    try:
        T.Plugin.function, T.run_generator = fake_function, fake_run
        res = IR.run(params, root, "preview")
        cases += 1
        check([c[:2] for c in calls] == [("helper", SEC), ("generator", GEN)]
              and all(c[2] for c in calls),
              f"[IMAGE RUN] calls {calls}: want the helper, then the generator, in the run's root")
        check(config.ATTEMPTS_DIR == real[2], "[IMAGE RUN] the attempts root was not restored")
        check([i["view"] for i in res["images"]] == ["isometric", "top", "blade_sections"]
              and not res["errors"],
              f"[IMAGE RUN] images {[i['view'] for i in res['images']]} errors {res['errors']} "
              f"(want the switched-on views in order; side is off)")
        T.run_generator = lambda name, path: "FEG error: no node"
        res = IR.run(params, root, "broken")
        cases += 1
        check(res["errors"] == [{"tool": GEN, "message": "FEG error: no node"}]
              and [i["view"] for i in res["images"]] == ["blade_sections"],
              f"[IMAGE RUN] a failing generator: {res}")
        # The samples: one picture per compression kind and set.
        T.run_generator = fake_run

        def fake_child(sets, timeout=0):
            out_root = Path(tempfile.mkdtemp(prefix="image_run_child_"))
            return {n: IR.run(p, out_root, n) for n, p in sets.items()}, out_root
        IR.run_in_child = fake_child
        out = Path(tempfile.mkdtemp(prefix="samples_"))
        res = IR.make_render_samples(out)
        cases += 1
        want = sorted(f"{k}_{s}.png" for k in ("cross", "geo")
                      for s in ("small", "medium", "large"))
        check(sorted(res["written"]) == want
              and (out / "geo_small.png").read_bytes() == b"render_isometric.png"
              and (out / "cross_large.png").read_bytes() == b"sec",
              f"[IMAGE RUN] samples written {res['written']}")
        shutil.rmtree(out, ignore_errors=True)
        sets = IR.render_sample_sets()
        check(list(sets) == ["small", "medium", "large"]
              and all(list(v) == list(params) for v in sets.values()),
              f"[IMAGE RUN] pack.yaml's sample sets: {list(sets)}")
        broken = Path(tempfile.mkdtemp(prefix="packyaml_")) / "pack.yaml"
        text = (ROOT / "setups" / "propeller" / "pack.yaml").read_text(encoding="utf-8")
        broken.write_text(text.replace("  small: {bladeCount: 3, ", "  small: {"),
                          encoding="utf-8")
        try:
            IR.render_sample_sets(broken)
            check(False, "[IMAGE RUN] a sample set without bladeCount was accepted")
        except T.PackToolError:
            pass
        shutil.rmtree(broken.parent, ignore_errors=True)
    except Exception as exc:                                        # noqa: BLE001
        check(False, f"[IMAGE RUN] {type(exc).__name__}: {str(exc)[:200]}")
    finally:
        T.Plugin.function, T.run_generator, config.ATTEMPTS_DIR, IR.run_in_child = real
        shutil.rmtree(root, ignore_errors=True)
    return cases


def check_tool_list() -> None:
    from agents.shared import agent_roles
    from workflow_settings import settings as S
    lists = json.loads(LISTS.read_text(encoding="utf-8"))["lists"]
    saved = S.SYSTEM_TOPOLOGY
    try:
        for topo, want in lists.items():
            S.SYSTEM_TOPOLOGY = int(topo)
            for state in ("on", "off"):
                T.settings_override_for_tests({SEC: {"enabled": state == "on"}})
                got = T.tool_list(want["agent"])
                check(got == want[state],
                      f"[LIST] topology {topo} {want['agent']}, blade sections {state}: "
                      f"the engine-built list differs from the old one\n"
                      f"      want {json.dumps(want[state])[:300]}\n"
                      f"      got  {json.dumps(got)[:300]}")
            T.settings_override_for_tests(None)
            others = [a for a in agent_roles.roster(int(topo)) if a != want["agent"]]
            check(all(T.tool_list(a) == "" for a in others),
                  f"[LIST] topology {topo}: an agent other than {want['agent']} got a list")
    finally:
        S.SYSTEM_TOPOLOGY = saved
        T.settings_override_for_tests(None)


def check_removal() -> int:
    from agents.shared import agent_roles
    from agents.shared import prompts as P
    from workflow_settings import settings as S
    sec_slots = list(T.manifest(SEC)["prompt_slots"])
    copy = _pack_copy()
    shutil.rmtree(copy / "tools" / SEC)
    real_pack, real_topo, real_path = config.DC_PACK_DIR, S.SYSTEM_TOPOLOGY, T.OVERRIDES_PATH
    T.OVERRIDES_PATH = copy.parent / "tool_settings.json"
    # A value saved in Workflow Settings before the folder was removed.
    T.OVERRIDES_PATH.write_text(json.dumps({SEC: {"enabled": False}}), encoding="utf-8")
    config.DC_PACK_DIR = copy
    built = 0
    try:
        agent_kinds = [n for n, m in T.manifests().items() if m["kind"] in T.KINDS]
        check(agent_kinds == [GEN], f"[REMOVAL] tools: {list(T.manifests())}")
        check(all(PK.read(s, 7) == "" for s in sec_slots),
              "[REMOVAL] a slot of the removed tool still has text")
        check([r["view"] for r in T.image_outputs()] == ["isometric", "top", "side"],
              f"[REMOVAL] views: {[r['view'] for r in T.image_outputs()]}")
        for topo in (7, 5, 3):
            S.SYSTEM_TOPOLOGY = topo
            for agent in list(agent_roles.roster(topo)) + ["database_handler"]:
                try:
                    text = P._build_template(agent)
                except Exception as exc:                            # noqa: BLE001
                    check(False, f"[REMOVAL] topology {topo} {agent}: "
                                 f"{type(exc).__name__}: {str(exc)[:200]}")
                    continue
                built += 1
                for needle in ("render_blade_sections", "blade-sections visualizer", "<<IF"):
                    check(needle not in text,
                          f"[REMOVAL] topology {topo} {agent}: the prompt still has {needle!r}")
            runner = agent_roles.holder("tool_caller", topo)
            names = re.findall(r"(?m)^\d+\. \*\*([a-z_]+)", T.tool_list(runner))
            want = (["new_attempt_parameters"] if topo == 3 else []) + [GEN, "calculate", "read_attempts"]
            check(names == want, f"[REMOVAL] topology {topo} tool list: {names}")
            check([t.name for t in T.agent_tools(runner)] == [GEN],
                  f"[REMOVAL] topology {topo}: {runner} is given "
                  f"{[t.name for t in T.agent_tools(runner)]}")
    except Exception as exc:                                        # noqa: BLE001
        check(False, f"[REMOVAL] the pack without {SEC}: "
                     f"{type(exc).__name__}: {str(exc)[:200]}")
    finally:
        config.DC_PACK_DIR, S.SYSTEM_TOPOLOGY, T.OVERRIDES_PATH = real_pack, real_topo, real_path
        shutil.rmtree(copy.parent, ignore_errors=True)
    return built


# ---------------------------------------------------------------------------
# 4. Golden
# ---------------------------------------------------------------------------

def check_golden() -> int:
    att = Path(tempfile.mkdtemp(prefix="golden_att_")).resolve()
    outside = Path(tempfile.mkdtemp(prefix="golden_out_")).resolve()
    real_att = config.ATTEMPTS_DIR
    config.ATTEMPTS_DIR = att
    gen = T.plugin(GEN).module
    real_dispatch, real_render = T.make_model, gen.render_and_check
    from engine.tooling import GeometryResult, MadeModel, ToolError
    shown = {"feg": "FEG", "rhino": "RhinoCompute"}
    params = {p["name"]: p["default"] for p in json.loads(
        (ROOT / "setups" / "propeller" / "parameters.json").read_text(encoding="utf-8"))["parameters"]}
    calls: list = []

    def norm(s):
        if not isinstance(s, str):
            return s
        for root, tag in ((att, "<ATT>"), (outside, "<OUT>")):
            for form in (str(root), str(root).replace("\\", "/")):
                s = s.replace(form, tag)
        return s.replace("\\", "/")

    # The stand-in for the engine's make_model: the geometry tool *used*
    # made the model; the settings chose order[0].
    def backend_ok(comps="g Comp1\nv 9 9 9\n", used="feg"):
        def f(p, order):
            calls.append(["backend", sorted(p.items())])
            extra = {"propeller_mesh_components.obj": comps} if comps is not None else {}
            return MadeModel(GeometryResult("g Blade\nv 0 0 0\ng Ring\nv 1 1 1\ng Blade\n",
                                            1234, extra),
                             made_by=shown[used],
                             chosen=T.manifest(order[0])["display_name"])
        return f

    def backend_raises(msg):
        def f(p, order):
            calls.append(["backend", sorted(p.items())])
            raise ToolError(msg)
        return f

    def render_ok(mesh, out):
        calls.append(["render", norm(str(mesh)), norm(str(out))])
        return f"RENDER REPORT for {Path(mesh).name} in {out}"

    def render_raises(mesh, out):
        calls.append(["render", norm(str(mesh)), norm(str(out))])
        raise RuntimeError("GL context lost")

    def folder(name, record=None, raw=None):
        d = att / name
        d.mkdir(parents=True, exist_ok=True)
        if record is not None:
            (d / "parameters.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        if raw is not None:
            (d / "parameters.json").write_text(raw, encoding="utf-8")
        return d

    def snapshot(d):
        out = {}
        for p in sorted(d.iterdir()):
            if p.suffix == ".png":
                out[p.name] = "<png>"
            elif p.suffix == ".json":
                raw = p.read_text(encoding="utf-8")
                try:
                    out[p.name] = json.loads(raw)
                except ValueError:
                    out[p.name] = "raw:" + raw
            else:
                out[p.name] = norm(p.read_text(encoding="utf-8"))
        return out

    got: dict = {}

    def gen_case(name, path, *, backend=None, render=render_ok, selected="feg", look=None):
        calls.clear()
        T.make_model = backend or backend_ok()
        gen.render_and_check = lambda mesh, out, settings: render(mesh, out)
        T.settings_override_for_tests({GEN: {"geometry_tool": f"{selected}_geometry"}})
        text = T.llm_tool(GEN).invoke({"parameters_path": str(path)})
        got[name] = {"text": norm(text), "calls": json.loads(json.dumps(calls)),
                     "files": snapshot(look) if look else None}

    def sec_case(name, args, look=None):
        text = T.llm_tool(SEC).invoke(args)
        got[name] = {"text": re.sub(r"\(\d+x\d+px", "(<W>x<H>px", norm(text)),
                     "files": snapshot(look) if look else None}

    try:
        d = folder("001_new", params)
        gen_case("new_mesh_feg", d / "parameters.json", look=d)
        gen_case("reuse_existing", d / "parameters.json", look=d)
        d = folder("002_fallback", params)
        gen_case("fallback_rhino_selected", d / "parameters.json",
                 backend=backend_ok(comps=None, used="feg"), selected="rhino", look=d)
        d = folder("003_rhino", params)
        gen_case("rhino_selected_rhino_used", d / "parameters.json",
                 backend=backend_ok(used="rhino"), selected="rhino", look=d)
        d = folder("004_err_prefixed", params)
        gen_case("backend_error_prefixed", d / "parameters.json",
                 backend=backend_raises("FEG error: node is not installed"), look=d)
        d = folder("005_err_generic", params)
        gen_case("backend_error_generic", d / "parameters.json",
                 backend=backend_raises("All geometry backends failed — feg: x | rhino: y"),
                 look=d)
        d = folder("006_no_record")
        gen_case("no_record", d / "parameters.json", look=d)
        bad = dict(params)
        bad.pop("innerChord")
        bad["outerAngle"] = "ten"
        d = folder("007_bad_record", bad)
        gen_case("incomplete_record", d / "parameters.json", look=d)
        d = folder("008_not_object", raw="[1, 2, 3]")
        gen_case("record_not_object", d / "parameters.json", look=d)
        d = folder("009_bad_json", raw="{not json")
        gen_case("record_bad_json", d / "parameters.json", look=d)
        d = folder("010_legacy_key", dict(params, impellerHeight=7))
        gen_case("legacy_impeller_height", d / "parameters.json", look=d)
        d = folder("011_render_fails", params)
        gen_case("render_raises", d / "parameters.json", render=render_raises, look=d)
        (outside / "parameters.json").write_text(json.dumps(params), encoding="utf-8")
        gen_case("outside_attempts", outside / "parameters.json")
        gen_case("missing_folder", att / "nope" / "parameters.json")

        d = folder("101_sections", params)
        sec_case("sections_ok", {"parameters_path": str(d / "parameters.json")}, look=d)
        sec_case("sections_grid", {"parameters_path": str(d / "parameters.json"), "grid": True},
                 look=d)
        sec_case("sections_empty_path", {"parameters_path": "  "})
        sec_case("sections_no_file", {"parameters_path": str(att / "nope" / "parameters.json")})
        sec_case("sections_outside", {"parameters_path": str(outside / "parameters.json")})
        d = folder("102_sections_bad_json", raw="{nope")
        sec_case("sections_bad_json", {"parameters_path": str(d / "parameters.json")})
        d = folder("103_sections_list", raw="[1]")
        sec_case("sections_not_object", {"parameters_path": str(d / "parameters.json")})
        d = folder("104_sections_missing",
                   {k: v for k, v in params.items() if not k.startswith("outer")})
        sec_case("sections_missing_keys", {"parameters_path": str(d / "parameters.json")})
        d = folder("105_sections_nonnum", dict(params, innerAngle="x"))
        sec_case("sections_non_numeric", {"parameters_path": str(d / "parameters.json")})
    finally:
        T.make_model, gen.render_and_check = real_dispatch, real_render
        T.settings_override_for_tests(None)
        config.ATTEMPTS_DIR = real_att
        shutil.rmtree(att, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)

    want = json.loads(FIXTURE.read_text(encoding="utf-8"))
    check(sorted(got) == sorted(want), f"[GOLDEN] cases {sorted(set(got) ^ set(want))}")
    for name in sorted(want):
        g, w = got.get(name, {}), want[name]
        for field in ("text", "calls", "files"):
            if g.get(field) != w.get(field):
                FAILURES.append(f"[GOLDEN] {name}: {field} differs\n"
                                f"      want {json.dumps(w.get(field))[:300]}\n"
                                f"      got  {json.dumps(g.get(field))[:300]}")
    return len(got)


# ---------------------------------------------------------------------------
# 14. Kept while unchanged (MAS-blueprint P5, G1)
# ---------------------------------------------------------------------------

def _reads(fn):
    """(fn(), how many YAML files it parsed)."""
    import yaml
    real, n = yaml.safe_load, [0]

    def counting(*a, **k):
        n[0] += 1
        return real(*a, **k)
    yaml.safe_load = counting
    try:
        return fn(), n[0]
    finally:
        yaml.safe_load = real


def _age(path: Path, seconds: int = 120) -> None:
    """Give *path* a modification time *seconds* in the past (as if the
    edit had been made then), so what is read from it may be kept."""
    t = time.time_ns() - seconds * 1_000_000_000
    os.utime(path, ns=(t, t))


def check_kept() -> int:
    real = config.DC_PACK_DIR
    copy = _pack_copy()
    n = 0
    try:
        config.DC_PACK_DIR = copy
        tools = copy / "tools"
        sec_yaml = tools / SEC / "tool.yaml"
        n_tools = len([d for d in tools.iterdir() if (d / "tool.yaml").is_file()])

        # Kept: the second call reads nothing again.
        _, first = _reads(T.manifests)
        _, second = _reads(T.manifests)
        _, c_first = _reads(PK.tool_claims)
        _, c_second = _reads(PK.tool_claims)
        check(first == n_tools and second == 0 and c_first == n_tools and c_second == 0,
              f"[KEPT] tool.yaml files parsed by two calls: manifests {first} then {second}, "
              f"claims {c_first} then {c_second} (want {n_tools} then 0)")
        n += 1

        # A copy of its own for each caller.
        m = T.manifests()
        m[SEC]["display_name"] = "changed"
        m[SEC]["outputs"]["images"].append({"view": "x"})
        T.manifest(GEN)["settings"].clear()
        again = T.manifests()
        check(again[SEC]["display_name"] == "Blade Sections"
              and len(again[SEC]["outputs"]["images"]) == 1 and again[GEN]["settings"],
              "[KEPT] a caller changing its manifests changed what the next caller gets")
        n += 1

        # A tool.yaml edited without changing its size, then left to settle.
        _rewrite(sec_yaml, "display_name: Blade Sections", "display_name: Blade Sectionz")
        _age(sec_yaml)
        got = T.manifests()[SEC]["display_name"]
        _, later = _reads(T.manifests)
        check(got == "Blade Sectionz" and later == 0,
              f"[KEPT] a same-size tool.yaml edit: read {got!r}, then {later} files parsed again")
        n += 1

        # An edit in the same instant as the read before it: same size, same
        # stamp.  A value read while its file was that young is not kept.
        _rewrite(sec_yaml, "display_name: Blade Sectionz", "display_name: Blade Sectiony")
        st = os.stat(sec_yaml)
        got_y = T.manifests()[SEC]["display_name"]
        _rewrite(sec_yaml, "display_name: Blade Sectiony", "display_name: Blade Sectionx")
        os.utime(sec_yaml, ns=(st.st_atime_ns, st.st_mtime_ns))
        got_x = T.manifests()[SEC]["display_name"]
        check((got_y, got_x) == ("Blade Sectiony", "Blade Sectionx"),
              f"[KEPT] an edit with the same stamp as the read before it: read {got_y!r} "
              f"then {got_x!r}")
        n += 1

        # A changed claim (pack.tool_claims, read without the checks).
        _rewrite(sec_yaml, "  - render_type_choice", "  - render_type_choicX")
        _age(sec_yaml, 90)
        claims = PK.tool_claims()
        check(claims.get("render_type_choicX") == SEC and "render_type_choice" not in claims,
              "[KEPT] a changed prompt_slots entry is not seen by tool_claims()")
        _rewrite(sec_yaml, "render_type_choicX", "render_type_choice")
        _rewrite(sec_yaml, "display_name: Blade Sectionx", "display_name: Blade Sections")
        _age(sec_yaml, 80)
        n += 1

        # A tool folder removed, then put back.
        away = copy.parent / "away"
        shutil.move(str(tools / SEC), str(away))
        _age(tools, 70)
        gone = T.manifests()
        gone_claims = PK.tool_claims()
        shutil.move(str(away), str(tools / SEC))
        _age(tools, 60)
        back = T.manifests()
        check(SEC not in gone and "render_type_choice" not in gone_claims and SEC in back
              and PK.tool_claims().get("render_type_choice") == SEC,
              f"[KEPT] a tool folder removed then put back: {sorted(gone)} -> {sorted(back)}")
        n += 1

        def refused(what, needle):
            try:
                T.manifests()
                check(False, f"[KEPT] {what}: not seen (the manifests were not checked again)")
            except T.PackToolError as exc:
                check(needle in str(exc), f"[KEPT] {what}: refused for another reason: "
                                          f"{str(exc)[:200]}")

        # A tool folder added (a second copy of blade sections claims its texts).
        shutil.copytree(tools / SEC, tools / "zz_twin")
        _age(tools, 50)
        refused("a tool folder added", "claimed by both")
        shutil.rmtree(tools / "zz_twin")
        _age(tools, 40)
        check(sorted(T.manifests()) == sorted(back), "[KEPT] the added folder, removed, is still seen")
        n += 1

        # A file added to a tool's prompts/: the ownership checks run again.
        stray = tools / SEC / "prompts" / "geometry_editing_ban.md"
        shutil.copy(tools / GEN / "prompts" / "geometry_editing_ban.md", stray)
        _age(stray.parent, 30)
        refused("a file added to a prompts/ folder", "is not in the tool's prompt_slots")
        stray.unlink()
        _age(stray.parent, 20)
        T.manifests()               # read and kept: the next change is the only one
        n += 1

        # Tool text put in fragments/.
        moved = copy / "fragments" / "tools" / "geometry_editing_ban.md"
        shutil.copy(tools / GEN / "prompts" / "geometry_editing_ban.md", moved)
        _age(moved.parent, 10)
        refused("tool text put in fragments/", "is tool text")
        moved.unlink()
        try:
            T.manifests()
        except T.PackToolError as exc:
            check(False, f"[KEPT] the pack put right is still refused: {str(exc)[:200]}")
        n += 1

        # A text's files: an agent copy or a per-topology file added,
        # removed or renamed is seen on the next read (the folder's file
        # list is kept by its stamp), and a text edit always is.
        dc = copy / "fragments" / "dc"
        slot, agent = "capabilities_can", "planner"
        shared = PK.read(slot, 7)
        _age(dc, 300)
        PK.read(slot, 7, agent)                      # the list, kept
        own = dc / f"{slot}@{agent}.t7.md"
        own.write_text("The Planner's own copy.\n", encoding="utf-8")
        _age(own, 290)
        _age(dc, 280)
        got_own = (PK.read(slot, 7, agent), PK.agent_copies(agent, 7).get(slot))
        own.unlink()
        _age(dc, 270)
        got_gone = (PK.read(slot, 7, agent), slot in PK.agent_copies(agent, 7))
        check(got_own == ("The Planner's own copy.", "The Planner's own copy.")
              and got_gone == (shared, False),
              f"[KEPT] an agent copy added then removed: read {got_own!r}, then {got_gone!r}")
        t5 = dc / f"{slot}.t5.md"
        t5.write_text("Topology 5's own text.\n", encoding="utf-8")
        _age(t5, 260)
        _age(dc, 250)
        got5 = (PK.read(slot, 5), PK.read(slot, 7))
        t5.rename(dc / f"{slot}.t3.md")
        _age(dc, 240)
        got_renamed = (PK.read(slot, 5), PK.read(slot, 3))
        (dc / f"{slot}.t3.md").unlink()
        _age(dc, 230)
        check(got5 == ("Topology 5's own text.", shared)
              and got_renamed == (shared, "Topology 5's own text."),
              f"[KEPT] a per-topology file added then renamed: {got5!r}, then {got_renamed!r}")
        # A file added in the same instant as the read before it: the
        # folder keeps its stamp, but a list read while the folder was that
        # young is not kept.
        young = dc / f"{slot}.t5.md"
        young.write_text("Young.\n", encoding="utf-8")
        st = os.stat(dc)
        got_young = PK.read(slot, 5)
        young.unlink()
        os.utime(dc, ns=(st.st_atime_ns, st.st_mtime_ns))
        try:
            got_after = PK.read(slot, 5)
        except OSError as exc:              # a kept list naming the removed file
            got_after = f"{type(exc).__name__}: {exc}"
        _age(dc, 225)
        check((got_young, got_after) == ("Young.", shared),
              f"[KEPT] a file removed with the folder's stamp unchanged: read {got_young!r}, "
              f"then {got_after!r}")
        linked = dc / f"{slot}.md"
        raw = linked.read_bytes()
        linked.write_bytes((b"#" if raw[:1] != b"#" else b"*") + raw[1:])
        _age(linked, 220)
        check(PK.read(slot, 7)[1:] == shared[1:] and PK.read(slot, 7) != shared,
              "[KEPT] a text edited in place is not read fresh")
        n += 4

        # The hold switch (the Studio's short-lived processes): a process
        # that holds its stamps does not see a copy added after its first
        # read; this process, which does not hold, does.
        probe = (
            "import json, os, sys, time\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import config\n"
            "from engine import pack as PK\n"
            "PK.hold_stamps()\n"
            "first = PK.read(sys.argv[2], 7, sys.argv[3])\n"
            "f = os.path.join(sys.argv[4], sys.argv[2] + '@' + sys.argv[3] + '.t7.md')\n"
            "open(f, 'w', encoding='utf-8').write('Added while held.\\n')\n"
            "t = time.time_ns() - 200 * 10**9\n"
            "os.utime(f, ns=(t, t)); os.utime(sys.argv[4], ns=(t, t))\n"
            "print(json.dumps([first, PK.read(sys.argv[2], 7, sys.argv[3])]))\n")
        import subprocess
        p = subprocess.run([sys.executable, "-c", probe, str(ROOT), slot, agent, str(dc)],
                           capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT),
                           env=dict(os.environ, DC_PACK_DIR=str(copy)))
        held = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else p.stderr[-300:]
        here = PK.read(slot, 7, agent)
        check(held == [PK.read(slot, 7), PK.read(slot, 7)] and here == "Added while held.",
              f"[KEPT] the hold switch: the holding process read {held!r}; this one {here!r}")
        n += 1
    finally:
        config.DC_PACK_DIR = real
        shutil.rmtree(copy.parent, ignore_errors=True)
    return n


def check_secrets() -> int:
    """15. The environment variables a tool reads: names, never values."""
    declared = [s["env"] for s in T.manifests()["rhino_geometry"].get("secrets", [])]
    check(declared == ["RHINO_COMPUTE_URL", "RHINO_COMPUTE_API_KEY"],
          f"[SECRETS] rhino_geometry declares {declared}")
    rhino = lambda d: d / "tools" / "rhino_geometry" / "tool.yaml"      # noqa: E731
    cases = [
        ("a name not in capitals",
         lambda d: _rewrite(rhino(d), "{env: RHINO_COMPUTE_URL,", "{env: rhino_compute_url,"),
         "secrets[0] is"),
        ("no description",
         lambda d: _rewrite(rhino(d), ', description: "Its API key, when the server asks for one."}', "}"),
         "secrets[1] is"),
        ("a name twice",
         lambda d: _rewrite(rhino(d), "{env: RHINO_COMPUTE_API_KEY,", "{env: RHINO_COMPUTE_URL,"),
         "names RHINO_COMPUTE_URL twice"),
        ("an unknown field",
         lambda d: _rewrite(rhino(d), "{env: RHINO_COMPUTE_URL, required: false,",
                            "{env: RHINO_COMPUTE_URL, required: false, value: x,"),
         "secrets[0] is"),
        ("required not true / false",
         lambda d: _rewrite(rhino(d), "{env: RHINO_COMPUTE_URL, required: false,",
                            "{env: RHINO_COMPUTE_URL, required: maybe,"),
         "secrets[0] is"),
    ]
    return _refused(cases, "[SECRETS]")


def check_outputs() -> int:
    """16. Two tools never write the same picture or model file."""
    sec = lambda d: d / "tools" / SEC / "tool.yaml"                    # noqa: E731

    def second_generator(d):
        shutil.copytree(d / "tools" / GEN, d / "tools" / "qzx_gen",
                        ignore=shutil.ignore_patterns("prompts", "__pycache__"))
        y = d / "tools" / "qzx_gen" / "tool.yaml"
        text = y.read_bytes().decode("utf-8")
        text = text.replace(f"name: {GEN}", "name: qzx_gen", 1)
        text = text[:text.index("list_order:")]       # its texts stay with the original
        for v in ("isometric", "top", "side"):
            text = text.replace(f"view: {v}, file: render_{v}.png", f"view: q{v}, file: render_q{v}.png")
        y.write_bytes(text.encode("utf-8"))
    cases = [
        ("a picture view declared twice",
         lambda d: _rewrite(sec(d), "view: blade_sections, file: render_blade_sections.png",
                            "view: top, file: render_top.png"),
         "is already"),
        ("a model file written by two generators", second_generator, "the model file"),
    ]
    return _refused(cases, "[OUTPUTS]")


def main() -> int:
    check_manifests()
    check_settings()
    check_binding()
    n = check_golden()
    n_broken = check_tool_texts()
    check_tool_list()
    n_built = check_removal()
    n_contract = check_contract()
    n_saves = check_save_step()
    check_compression()
    check_runtime_block()
    n_geometry = check_geometry()
    n_runs = check_image_run()
    n_kept = check_kept()
    n_secrets = check_secrets()
    n_outputs = check_outputs()
    print(f"{len(T.manifests())} tools; {n} golden cases compared with "
          f"{FIXTURE.relative_to(ROOT).as_posix()}; {len(PK.tool_claims())} tool-text "
          f"slots owned, {n_broken} broken packs refused; 6 tool lists compared with "
          f"{LISTS.relative_to(ROOT).as_posix()}; {n_built} prompts built without "
          f"the blade-sections tool; {n_contract} pictures-contract breaks refused; "
          f"{n_saves} save-step cases; {n_geometry} broken geometry packs refused; "
          f"{n_runs} image-run cases; {n_kept} kept-while-unchanged cases; "
          f"{n_secrets} broken secret declarations refused; {n_outputs} shared outputs refused")
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - the manifests load, the settings and their checks behave, the "
          "tool runner of each topology gets the tools, both tools answer exactly "
          "what they answered before the move, each owns its prompt text, the "
          "tool list is built exactly as it was written, a tool can be removed, "
          "the picture contract, the save step, the shrink strengths and the "
          "runtime block come from the manifests, the geometry tools are "
          "chosen and fall back as their settings say, the image runner "
          "makes the tools' pictures in a root of its own, what is read "
          "from the tools' files is kept only while they are unchanged, and the "
          "secrets a tool declares are checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
