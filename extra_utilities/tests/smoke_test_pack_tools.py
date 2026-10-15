"""The pack's tools, offline: manifests, settings, role binding and what the
two propeller tools answer.

Since MAS-blueprint P3c the generator and the blade-sections tool live in
``dc_pack/tools/<tool>/`` (a ``tool.yaml`` + plain Python) and the engine
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

Run from the repo root:  py -3.13 extra_utilities/tests/smoke_test_pack_tools.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
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

FAILURES: list[str] = []
FIXTURE = ROOT / "extra_utilities" / "tests" / "fixtures" / "pack_tools_golden.json"
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
    for name in m:
        t = T.llm_tool(name)
        check(t.name == name and t.description.strip(),
              f"[MANIFEST] {name}: LLM tool name {t.name!r} / empty description")
    views = [r["view"] for r in T.image_outputs()]
    check(views == ["isometric", "top", "blade_sections", "side"],
          f"[MANIFEST] view order {views}")


def check_settings() -> None:
    check(T.settings(GEN) == {"geometry_backend": "feg", "render_library": "trimesh",
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
# 4. Golden
# ---------------------------------------------------------------------------

def check_golden() -> int:
    att = Path(tempfile.mkdtemp(prefix="golden_att_")).resolve()
    outside = Path(tempfile.mkdtemp(prefix="golden_out_")).resolve()
    real_att = config.ATTEMPTS_DIR
    config.ATTEMPTS_DIR = att
    gen = T.plugin(GEN).module
    real_dispatch, real_render = gen.render_agent_mesh_obj_text, gen.render_and_check
    params = {p["name"]: p["default"] for p in json.loads(
        (ROOT / "dc_pack" / "parameters.json").read_text(encoding="utf-8"))["parameters"]}
    calls: list = []

    def norm(s):
        if not isinstance(s, str):
            return s
        for root, tag in ((att, "<ATT>"), (outside, "<OUT>")):
            for form in (str(root), str(root).replace("\\", "/")):
                s = s.replace(form, tag)
        return s.replace("\\", "/")

    def backend_ok(comps="g Comp1\nv 9 9 9\n", used="feg"):
        def f(p):
            calls.append(["backend", sorted(p.items())])
            return ("g Blade\nv 0 0 0\ng Ring\nv 1 1 1\ng Blade\n", 1234, comps, used)
        return f

    def backend_raises(msg):
        def f(p):
            calls.append(["backend", sorted(p.items())])
            raise gen.MeshGenerationError(msg)
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
        gen.render_agent_mesh_obj_text = backend or backend_ok()
        gen.render_and_check = lambda mesh, out, settings: render(mesh, out)
        T.settings_override_for_tests({GEN: {"geometry_backend": selected}})
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
        gen.render_agent_mesh_obj_text, gen.render_and_check = real_dispatch, real_render
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


def main() -> int:
    check_manifests()
    check_settings()
    check_binding()
    n = check_golden()
    print(f"{len(T.manifests())} tools; {n} golden cases compared with "
          f"{FIXTURE.relative_to(ROOT).as_posix()}")
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - the manifests load, the settings and their checks behave, the "
          "tool runner of each topology gets the tools, and both tools answer "
          "exactly what they answered before the move.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
