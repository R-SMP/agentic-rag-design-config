"""Build ``draft_data.js`` for the Studio draft from the REAL propeller pack.

    py -3.13 extra_utilities/docs/studio_draft/build_draft_data.py

The draft pages are ``file://`` pages (the studio UI kit's rule: no fetch(),
no modules), so the data is written as one script, ``window.DRAFT_DATA``.

What it reads
-------------
The data the real Studio shows, through the same functions
(``studio/engine_view.py``, MAS-blueprint P5a): the parameter set, every
pack fragment with its per-topology and per-agent files, the role map, the
tools and their settings, the parameter-access grid, and the assembled
prompts of every agent, topologies 7 / 5 / 3, under the ``base`` and
``all_on`` combinations of ``prompt_matrix.py`` -- with the exact place of
every field's text in them ("where it lands", explained there).

Plus the draft's own, for screens the Studio gets later: the hosted
Validate's static checks, the prompt-matrix summary, the setup's size, and a
local-mode test run of ``render_blade_sections``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = HERE / "draft_data.js"
sys.path.insert(0, str(REPO))

from studio import engine_view as V  # noqa: E402

VOCAB = ("output_model", "output_model_label", "output_image", "output_images",
         "output_image_caps", "output_images_long", "output_image_files",
         "output_images_label", "output_produced", "output_action",
         "output_reaction", "output_reactions", "output_action_noun")

# The order of the fields in each section, as the draft's pictures show it
# (the slot registry's ``section`` field files each slot; the real Studio
# orders them by the registry, the same order).
SECTION_OF = {
    "identity": ["dc_name", "domain_description"],
    "parameters": ["parameter_count", "parameter_list"],
    "description": [
        "dc_structure", "modelling_notes", "lever_map", "qualitative_examples",
        "invalid_parameter_examples", "capabilities_can", "capabilities_cannot",
        "hard_constraints_dc", "geometry_modification_rule",
        "output_file_locations", "ratio_vs_absolute_feedback"],
    "outputs": list(VOCAB) + [
        "render_view_list", "geometry_model_filename", "visual_inspection_guide",
        "precision_match_subject", "precision_gap_description",
        "precision_match_targets", "values_only_excluded_outputs"],
    "tools": [
        "tool_inventory", "tool_caller_instructions", "tool_caller_capabilities",
        "agent_tools_overview", "agent_tools_overview_brief",
        "hard_constraints_tools", "geometry_tool_name", "geometry_tools_loading_rule",
        "render_type_choice", "roster_sections_tool_sentence", "roster_tools_clause",
        "routing_sections_alternative", "sections_rerun_case",
        "directive_output_choice", "precision_multi_phase_rule",
        "precision_continue_directive_example", "sections_tool_block_full",
        "sections_tool_block_overlay", "blade_sections_visualizer",
        "blade_sections_visualizer_off", "blade_sections_visualizer_per_agent",
        "geometry_editing_ban", "mesh_editing_operations_actions",
        "recommendation_exclusions", "quality_check_numbers",
        "quality_check_report", "mesh_check_role_item", "qc_numerics_verdict_rule",
        "no_render_fallback_qc", "visualize_3d_model_tool", "propose_attempt_tool",
        "database_search_tool", "database_search_per_agent",
        "retrieve_user_inputs_tool", "retrieve_attempt_tool"],
    "examples": [
        "past_run_lookup_examples", "extraction_only_examples_user",
        "extraction_only_examples", "observable_fact_questions",
        "tool_run_history_contents", "non_consumable_input_examples",
        "quantitative_input_example", "countable_feature_example",
        "stated_count_example", "soft_target_example", "soft_target_marker_example",
        "parameter_level_entry_example", "non_applicable_input_examples",
        "visual_claim_examples", "shape_gap_example", "unlocked_lever_examples",
        "sub_resolution_examples", "prior_finding_citation_example",
        "feature_feedback_examples", "relative_magnitude_examples",
        "dh_artefact_reference_examples", "dh_parameter_dump_example",
        "dh_concrete_noun_examples", "dh_parameter_name_example",
        "dh_numeric_fact_example", "dh_structural_marker_examples"],
    "inputs": ["sketch_handling", "sketch_notes", "sketch_precision_examples",
               "sketch_crop_example", "useful_input_images_example"],
}


def _validate(slots: list, engine_slots: set) -> dict:
    """The hosted Validate's STATIC checks, run for real on today's files."""
    from engine import pack
    files = pack.fragment_files()
    braces = [p.relative_to(REPO).as_posix() for p in files
              if re.search(r"[{}]", p.read_text(encoding="utf-8"))]
    known = {s["slot"] for s in slots} | engine_slots
    unknown = sorted({m for p in files for m in re.findall(
        r"\$([a-z_][a-z0-9_]*)", p.read_text(encoding="utf-8")) if m not in known})
    multi = [s["slot"] for s in slots if s["kind"] == "phrase" and any(
        v and "\n" in v for v in s["values"].values())]
    empties = sorted(s["slot"] for s in slots if s["kind"] != "block" and
                     s["values"].get("7") == "")
    return {"fragment_files": len(files), "brace_files": braces,
            "unknown_dollar": unknown, "multiline_phrases": multi,
            "empty_in_topology7": empties}


def _test_child(out_png: str, params_json: str) -> int:
    """What local mode's "Test tool" does for render_blade_sections: run the
    tool's own drawing function on the parameter defaults, in a subprocess."""
    import time
    V.load_engine()
    from engine import pack_tools
    render_png = pack_tools.plugin("render_blade_sections").submodule("draw").render_png
    t0 = time.perf_counter()
    w, h = render_png(json.loads(params_json), False, Path(out_png))
    secs = time.perf_counter() - t0
    sys.stdout.write(json.dumps({"w": w, "h": h, "seconds": round(secs, 2),
                                 "bytes": Path(out_png).stat().st_size}))
    return 0


def _test_run(params: list) -> dict:
    defaults = {p["name"]: (int(p["default"]) if p["type"] == "int" else p["default"])
                for p in params}
    out = HERE / "assets" / "test_render_blade_sections.png"
    out.parent.mkdir(exist_ok=True)
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "_test",
                           str(out), json.dumps(defaults)],
                          capture_output=True, cwd=str(REPO))
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr.decode("utf-8", "replace")[-600:]}
    r = json.loads(proc.stdout.decode("utf-8"))
    r.update(ok=True, image="assets/test_render_blade_sections.png", params=defaults)
    return r


def _matrix_summary() -> dict:
    m = json.loads((REPO / "extra_utilities/prompt_matrix/baseline_manifest.json")
                   .read_text(encoding="utf-8"))
    rows = [(k, a, n) for k, e in m.items() if not k.startswith("_")
            for a, n in e["chars"].items()]
    k, a, n = max(rows, key=lambda r: r[2])
    return {"prompts": len(rows), "combinations": len(m["_meta"]["combinations"]),
            "unformatted": sum(len(e["unformatted"]) for kk, e in m.items()
                               if not kk.startswith("_")),
            "largest": {"where": k, "agent": a, "chars": n},
            "commit": m["_meta"]["commit"][:7]}


def _pack_bytes() -> int:
    from engine import pack
    roots = [pack.pack_dir(), REPO / "web/images"]
    return sum(p.stat().st_size for r in roots for p in r.rglob("*")
               if p.is_file() and "__pycache__" not in p.parts)


def main() -> int:
    if sys.argv[1:2] == ["_test"]:
        return _test_child(sys.argv[2], sys.argv[3])
    print("assembling (2 combinations x 3 topologies, twice each) ...")
    prompts = V.run_children(V.ASSEMBLY_JOBS)
    for (combo, n), res in prompts.items():
        bad = [a for a, s in res["align"].items() if s == "FAILED"]
        print(f"  {combo:<7} topology {n}: "
              + ", ".join(f"{a}={s}" for a, s in sorted(res["align"].items()))
              + (f"   !! no spans for {bad}" if bad else ""))
    V.load_engine()
    from agents.shared import prompts as P
    pack = V.pack_slots(P)
    roles = V.roles()
    order = {s: i for lst in SECTION_OF.values() for i, s in enumerate(lst)}
    slots = V.slots(P, pack, roles, order=order)
    data = {
        "pack": {"name": P._pack.read("dc_name", 7),
                 "domain": P._pack.read("domain_description", 7),
                 "parameter_count": P._GENERATED_SLOTS["parameter_count"]()},
        "parameters": V.parameters(P._pack),
        "slots": slots,
        "roles": roles,
        "where": V.where(prompts),
        "prompts": V.base_prompts(prompts),
        "align": V.alignment(prompts),
        "tools": V.tools(),
        "tool_settings": V.tool_settings(),
        "settings": V.settings_values({"DC_PARAMS_PRIMER_ENABLED"}),
        "parameter_access": V.parameter_access(),
        "validate": _validate(slots, set(P._build_slots())),
        # TODO F104 is closed (MAS-blueprint P3b): every field about the
        # blade-sections tool or the mesh checks carries its <<IF:...>> marker.
        "f104": {"blade_sections": [], "mesh_checks": []},
        "matrix": _matrix_summary(),
        "pack_bytes": _pack_bytes(),
        "env_vars": V.env_names(),
    }
    data["test_run"] = _test_run(data["parameters"]["parameters"])
    print(f"  test run of render_blade_sections: {data['test_run']}")
    js = "/* generated by build_draft_data.py -- do not edit */\nwindow.DRAFT_DATA = " + \
        json.dumps(data, ensure_ascii=False) + ";\n"
    OUT.write_text(js, encoding="utf-8", newline="\n")
    nspans = sum(len(v) for d in prompts.values() for v in d["spans"].values())
    print(f"wrote {OUT.name}: {len(js) // 1024} KB, {len(slots)} slots, "
          f"{len(data['parameters']['parameters'])} parameters, {nspans} spans, "
          f"where-it-lands for {len(data['where'])} slots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
