"""The text the engine itself writes for the agents, offline: unchanged.

MAS-blueprint P4a moved the propeller words in this text into the pack (its
vocabulary -- ``$output_model``, ``$output_images_label`` ... -- and a few
small slots), so the engine's own sentences are generic and the words come
from ``dc_pack/``.  The prompts and the chain agents' tools are proven
identical by the prompt and tool matrices; this check covers the rest of
what an agent reads, which neither matrix sees:

* TOOLS.  Name, description and argument schema of the tools whose text
  carries pack words -- ``read_attempts``, ``visualize_3d_model``,
  ``propose_attempt``, ``retrieve_attempt``, ``new_attempt_parameters``
  (both copies), ``view_images``, ``database_search``, the Database
  Handler's ``save_attempt_data`` and the hubs' ``submit_feedback_dispatch``
  -- in topologies 7, 5 and 3.
* ANSWERS.  What ``read_attempts``, ``visualize_3d_model`` and
  ``view_images`` return, on a fixture attempts folder.
* TEXTS.  The Context Pruner's three prompts, the Database Handler's reply
  reminder and stitching prompt, the hubs' end-of-session instructions, the
  hubs' refine-cap message and the Receptionist's "this cycle's images"
  block (the last two evaluated straight from the source line that builds
  them).

All of it must equal ``fixtures/engine_texts.json``, recorded on the code
before P4a (``27797dc``).  Paths are written as ``<ATT>``.

PACK WORDS.  Then the same texts are rebuilt from a temporary copy of the
pack whose words are swapped for stand-ins ("mesh" -> "widget", "renders"
-> "drawings", "propeller" -> "turbine" ...): each must now say the
stand-in and no longer the propeller word -- the proof that the words come
from the pack.  Module constants filled once at import (the Context
Pruner's prompts, the inspectors' runtime blocks, the reply reminder,
``database_search``'s argument texts) are not rebuilt; the golden covers
them.

Run from the repo root:  py -3.13 extra_utilities/tests/smoke_test_engine_texts.py
(``--record`` rewrites the fixture -- only on purpose).
"""
from __future__ import annotations

import ast
import importlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "extra_utilities" / "prompt_pdf"))
sys.path.insert(0, str(ROOT / "extra_utilities" / "scripts"))
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
sys.modules["simplejson"] = None          # type: ignore[assignment]
sys.modules["chardet"] = None             # type: ignore[assignment]
import bootstrap                          # noqa: E402

bootstrap.install()

import agents                             # noqa: E402,F401
from tool_matrix import _describe         # noqa: E402
from workflow_settings import settings as S  # noqa: E402

FIXTURE = ROOT / "extra_utilities" / "tests" / "fixtures" / "engine_texts.json"
FAILURES: list[str] = []


def _tools() -> dict:
    """name -> the tool, for the agents and topology being built."""
    from agents.design_engineer import design_engineer as de
    from agents.dc_input_creator import dc_input_creator as dcic
    from agents.database_handler import dh_tools
    from agents.orchestrator.feedback_tool import build_submit_feedback_dispatch
    from agents.receptionist.propose_attempt_tool import propose_attempt
    from agents.shared import attempts_tool
    from agents.shared.user_inputs_tool import build_user_inputs_tools
    from tools.database_search.database_search import make_database_search_tool
    from tools.retrieve_attempt.retrieve_attempt import make_retrieve_attempt_tool
    from tools.visualize_model.visualize_model import visualize_3d_model
    refresh = getattr(importlib.import_module("agents.shared.pack_text"), "refresh_tools", None) \
        if importlib.util.find_spec("agents.shared.pack_text") else None
    if refresh:
        refresh()
    out = {"read_attempts": attempts_tool.read_attempts,
           "visualize_3d_model": visualize_3d_model,
           "propose_attempt": propose_attempt,
           "retrieve_attempt": make_retrieve_attempt_tool("planner"),
           "new_attempt_parameters@dc_input_creator": dcic.new_attempt_parameters,
           "new_attempt_parameters@design_engineer": de.new_attempt_parameters,
           "save_attempt_data": dh_tools.save_attempt_data,
           "submit_feedback_dispatch": build_submit_feedback_dispatch()}
    for agent in ("user_input_inspector", "dc_input_inspector", "dc_output_inspector",
                  "requirements_analyst", "design_engineer"):
        out[f"view_images@{agent}"] = build_user_inputs_tools(agent)[0]
    for agent in ("planner", "dc_input_creator", "receptionist"):
        out[f"database_search@{agent}"] = make_database_search_tool(agent)
    return out


def _norm(text: str, att: Path) -> str:
    for form in (str(att), str(att).replace("\\", "/")):
        text = text.replace(form, "<ATT>")
    return text.replace("\\", "/")


def _answers() -> dict:
    """What three tools return, on a fixture attempts folder."""
    from agents.shared import attempts_tool
    from agents.shared.user_inputs_tool import build_user_inputs_tools
    from tools.visualize_model import visualize_model
    att = Path(tempfile.mkdtemp(prefix="engine_texts_")).resolve()
    a1 = att / "20260101_000000_001_first"
    a2 = att / "20260101_000100_002_second"
    a1.mkdir()
    a2.mkdir()
    (a1 / "parameters.json").write_text('{"bladeCount": 5}', encoding="utf-8")
    (a1 / "propeller_mesh.obj").write_text("v 0 0 0\n", encoding="utf-8")
    for n in ("render_isometric.png", "render_top.png", "render_blade_sections.png"):
        (a1 / n).write_bytes(b"png")
    (a1 / "description.txt").write_text("five thin blades", encoding="utf-8")
    (a2 / "parameters.json").write_text('{"bladeCount": 3}', encoding="utf-8")
    (a2 / "description.txt").write_text("three blades\nwide ring", encoding="utf-8")
    real = attempts_tool.ATTEMPTS_DIR
    attempts_tool.ATTEMPTS_DIR = att
    out = {}
    try:
        ra = attempts_tool.read_attempts
        for key, args in (("all", {}), ("detail_1_2", {"local_attempt_numbers": [1, 2]}),
                          ("missing", {"local_attempt_numbers": [9]})):
            out[f"read_attempts/{key}"] = _norm(ra.invoke(args), att)
        # The schema refuses a non-integer before the function sees it.
        out["read_attempts/bad_number"] = _norm(ra.func(local_attempt_numbers=["x", 1]), att)
        attempts_tool.ATTEMPTS_DIR = att / "none"
        out["read_attempts/no_attempts"] = _norm(ra.invoke({}), att)
        attempts_tool.ATTEMPTS_DIR = att
        viz = visualize_model.visualize_3d_model
        outside = att / "elsewhere"
        outside.mkdir()
        (outside / "x.obj").write_text("v 0 0 0\n", encoding="utf-8")
        visualize_model.ATTEMPTS_DIR, real_viz = a1, visualize_model.ATTEMPTS_DIR
        for key, path in (("empty", ""), ("not_obj", str(a1 / "description.txt")),
                          ("outside", str(outside / "x.obj")),
                          ("missing", str(a1 / "nope.obj"))):
            out[f"visualize_3d_model/{key}"] = _norm(viz.invoke({"obj_path": path}), att)
        visualize_model.ATTEMPTS_DIR = real_viz
        # view_images' answer comes from the dispatcher's handler.
        from agents.shared.user_inputs_tool import _handle_view_images

        class _Agent:
            messages: list = []
        for agent in ("dc_output_inspector", "dc_input_inspector", "user_input_inspector"):
            _Agent.messages = []
            _handle_view_images(_Agent, {"name": "view_images", "id": "t1",
                                         "args": {"paths": []}}, agent)
            out[f"view_images/no_paths@{agent}"] = _Agent.messages[-1].content
    finally:
        attempts_tool.ATTEMPTS_DIR = real
        shutil.rmtree(att, ignore_errors=True)
    return out


class _Folder:
    """A stand-in attempt folder for the evaluated source expressions."""
    def resolve(self):
        return "<ATT>/20260101_000000_001_first"


def _expr_after(module, marker: str, target: str):
    """The right-hand side of the ``<target> += (...)`` statement in
    *module*'s source whose text contains *marker*."""
    src = Path(module.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.AugAssign) and ast.unparse(node.target) == target:
            seg = ast.get_source_segment(src, node.value)
            if marker in seg:
                return compile(ast.Expression(node.value), module.__file__, "eval")
    raise LookupError(f"{module.__name__}: no '{target} += ...' containing {marker!r}")


def _texts() -> dict:
    from agents.database_handler import database_handler as dh
    from agents.database_handler import db_writer
    from agents.receptionist import receptionist
    from agents.shared import context_pruner as cp
    out = {}
    for name in ("COARSE_SUMMARY_PROMPT", "FINE_SUMMARY_PROMPT", "ULTRA_COMPACT_SUMMARY_PROMPT"):
        out[f"context_pruner/{name}"] = getattr(cp, name)
    tail = getattr(dh, "agent_facing_tail", None)
    out["database_handler/reply_reminder"] = tail() if tail else dh.DatabaseHandler._AGENT_FACING_TAIL
    out["database_handler/stitching_prompt"] = db_writer._load_stitching_prompt()
    for hub in ("orchestrator.orchestrator", "planner5.planner5", "planner3.planner3"):
        mod = importlib.import_module(f"agents.{hub}")
        out[f"{hub}/role4_instructions"] = mod._load_role4_instructions()
        code = _expr_after(mod, "PRECISION REFINE CAP", "hop.message")
        out[f"{hub}/refine_cap_message"] = eval(code, vars(mod))
    code = _expr_after(receptionist, "files produced this cycle", "text")
    out["receptionist/this_cycle_images"] = eval(code, {
        **vars(receptionist), "latest_attempt": _Folder(),
        "render_files": ["<ATT>/20260101_000000_001_first/render_isometric.png",
                         "<ATT>/20260101_000000_001_first/render_top.png"]})
    return out


# Stand-in words for the PACK WORDS check: slot -> text.
_STAND_INS = {
    "dc_pack/fragments/tools/output_model.md": "widget",
    "dc_pack/fragments/tools/output_models.md": "widgets",
    "dc_pack/fragments/tools/output_image.md": "drawing",
    "dc_pack/fragments/tools/output_images.md": "drawings",
    "dc_pack/fragments/tools/output_images_label.md": "Drawing images",
    "dc_pack/fragments/tools/output_produced.md": "drawn",
    "dc_pack/fragments/dc/dc_name.md": "turbine",
    "dc_pack/tools/generate_and_render_propeller/prompts/geometry_model_filename.md": "``turbine.step``",
    "dc_pack/fragments/dc/crop_reuse_example.md": "the inspector comparing vanes",
    "dc_pack/fragments/dc/attempt_slug_example.md": "``'3vanes'``",
    "dc_pack/fragments/tools/refine_cap_limits.md": "the vane-model ceiling",
    "dc_pack/fragments/dc/dh_stitching_example_answer.md": "Every vane matched.",
    "dc_pack/fragments/dc/dh_stitching_example_paragraph.md":
        "Regarding the turbine, every vane matched.",
}


def check_pack_words() -> int:
    """With the pack's words swapped for stand-ins, the text built per call or
    per session uses the stand-ins -- the words come from the pack, not the
    engine.  (Module constants are filled once at import, so they are not
    part of this; see agents/shared/pack_text.py.)"""
    import config
    from agents.database_handler import db_writer
    from agents.orchestrator.feedback_tool import build_submit_feedback_dispatch
    from agents.planner5 import planner5
    from agents.receptionist import receptionist
    from agents.receptionist.propose_attempt_tool import propose_attempt
    from agents.dc_input_creator import dc_input_creator as dcic
    from agents.shared import attempts_tool
    from agents.shared.pack_text import refresh_tools
    from agents.shared.user_inputs_tool import build_user_inputs_tools
    from tools.visualize_model.visualize_model import visualize_3d_model

    tmp = Path(tempfile.mkdtemp(prefix="pack_words_"))
    shutil.copytree(ROOT / "dc_pack", tmp / "dc_pack",
                    ignore=shutil.ignore_patterns("__pycache__"))
    for rel, text in _STAND_INS.items():
        (tmp / rel).write_text(text + "\n", encoding="utf-8")
    real_pack, saved = config.DC_PACK_DIR, S.SYSTEM_TOPOLOGY
    checks = 0

    def expect(text: str, present: list[str], absent: list[str], where: str) -> None:
        nonlocal checks
        checks += 1
        for word in present:
            if word not in text:
                FAILURES.append(f"[PACK WORDS] {where}: {word!r} missing")
        for word in absent:
            if word in text:
                FAILURES.append(f"[PACK WORDS] {where}: still says {word!r}")

    try:
        config.DC_PACK_DIR = tmp / "dc_pack"
        S.SYSTEM_TOPOLOGY = 7
        refresh_tools()
        expect(attempts_tool.read_attempts.description,
               ["the generated widget (``turbine.step``)", "no widget was generated",
                "and ``turbine.step`` are listed"], ["mesh", "propeller"], "read_attempts")
        answers = _answers()
        # (The model's FILE name is still the generator's propeller_mesh.obj:
        # file names come from the manifests in P4b.)
        expect(answers["read_attempts/all"], ["Has: parameters, widget, drawings",
                                              "Drawing paths:", "Widget path:"],
               ["Has: parameters, mesh", "Mesh path", "Render paths", "renders"],
               "read_attempts' answer")
        expect(answers["visualize_3d_model/outside"], ["only generated widgets"], ["meshes"],
               "visualize_3d_model's answer")
        expect(visualize_3d_model.description, ["a turbine widget", "``turbine.step``"],
               ["mesh", "propeller"], "visualize_3d_model")
        expect(propose_attempt.description, ["turbine parameter values"], ["propeller"],
               "propose_attempt")
        expect(dcic.new_attempt_parameters.description, ["``'3vanes'``"], ["4blades"],
               "new_attempt_parameters")
        expect(build_user_inputs_tools("dc_output_inspector")[0].description,
               ["tool-generated drawings", "``Drawing images:`` line",
                "e.g. the inspector comparing vanes"],
               ["renders", "Render images", "blade sections"], "view_images")
        code = _expr_after(receptionist, "files produced this cycle", "text")
        block = eval(code, {**vars(receptionist), "latest_attempt": _Folder(),
                            "render_files": []})
        expect(block, ["Confirmed drawing files produced this cycle"], ["render"],
               "the Receptionist's block")
        code = _expr_after(planner5, "PRECISION REFINE CAP", "hop.message")
        expect(eval(code, vars(planner5)), ["(the vane-model ceiling)"], ["airfoil"],
               "the refine-cap message")
        db_writer._stitching_prompt_cache = None
        expect(db_writer._load_stitching_prompt(),
               ['"what worked for a thin turbine?"', "DC_NAME: turbine"], ["propeller"],
               "the stitching prompt")
        S.SYSTEM_TOPOLOGY = 3
        expect(build_submit_feedback_dispatch().description, ["whether the drawing met it"],
               ["the render met"], "submit_feedback_dispatch (topology 3)")
    finally:
        config.DC_PACK_DIR, S.SYSTEM_TOPOLOGY = real_pack, saved
        refresh_tools()
        db_writer._stitching_prompt_cache = None
        shutil.rmtree(tmp, ignore_errors=True)
    return checks


def collect() -> dict:
    got: dict = {}
    saved = S.SYSTEM_TOPOLOGY
    try:
        for topo in (7, 5, 3):
            S.SYSTEM_TOPOLOGY = topo
            for name, t in _tools().items():
                got[f"tools/{topo}/{name}"] = _describe(t)
        S.SYSTEM_TOPOLOGY = 7
        got.update({f"answers/{k}": v for k, v in _answers().items()})
        got.update({f"texts/{k}": v for k, v in _texts().items()})
    finally:
        S.SYSTEM_TOPOLOGY = saved
    return got


def main() -> int:
    got = collect()
    if "--record" in sys.argv:
        FIXTURE.write_text(json.dumps(got, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                           encoding="utf-8")
        print(f"recorded {len(got)} texts -> {FIXTURE.relative_to(ROOT).as_posix()}")
        return 0
    want = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for key in sorted(set(want) | set(got)):
        if want.get(key) != got.get(key):
            w, g = json.dumps(want.get(key)), json.dumps(got.get(key))
            i = next((n for n, (a, b) in enumerate(zip(w, g)) if a != b), min(len(w), len(g)))
            FAILURES.append(f"[TEXT] {key} differs at character {i}:\n"
                            f"      want ...{w[max(0, i - 80):i + 80]}\n"
                            f"      got  ...{g[max(0, i - 80):i + 80]}")
    n_words = check_pack_words()
    print(f"{len(got)} texts compared with {FIXTURE.relative_to(ROOT).as_posix()}; "
          f"{n_words} texts rebuilt from a pack with stand-in words")
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - the tools, answers and texts the engine writes for the agents are "
          "exactly what they were before their propeller words moved into the pack, "
          "and they follow the pack's words when those change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
