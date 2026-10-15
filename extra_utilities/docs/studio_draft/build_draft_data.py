"""Build ``draft_data.js`` for the Studio draft from the REAL propeller pack.

    py -3.13 extra_utilities/docs/studio_draft/build_draft_data.py

The draft pages are ``file://`` pages (the studio UI kit's rule: no fetch(),
no modules), so the data is written as one script, ``window.DRAFT_DATA``.

What it reads
-------------
* the parameter set from ``dc_pack/parameters.json`` (``engine/parameters.py``),
  with the units and descriptions of the agents' ``$parameter_list`` text;
* every pack fragment (``dc_pack/fragments/``) with its per-topology and
  per-agent files, and each slot's kind, section and description from the
  slot registry (``engine/slot_registry.yaml``);
* the assembled prompts of every agent, topologies 7 / 5 / 3, under two
  setting combinations of ``prompt_matrix.py`` (``base`` and ``all_on``).

"Where it lands" without guessing
---------------------------------
Each topology is assembled TWICE in a child process: once as is, once with
every pack slot's text wrapped in invisible private-use markers (and the
runtime blocks too).  The markers are stripped again and the result must
equal the real prompt -- byte for byte, or, where a marker lengthened a line
enough to change a re-wrap, after whitespace normalisation.  The marker
positions are then exact spans in the REAL prompt.  An agent whose prompts
do not line up gets no spans and is reported, never approximated.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = HERE / "draft_data.js"
COMBOS = ("base", "all_on")
TOPOLOGIES = (7, 5, 3)

START, END, ID0 = "", "", 0xF0000

VOCAB = ("output_model", "output_model_label", "output_image", "output_images",
         "output_image_caps", "output_images_long", "output_image_files",
         "output_images_label", "output_produced", "output_action",
         "output_reaction", "output_reactions", "output_action_noun")
WORDS = VOCAB + ("dc_name", "domain_description", "parameter_count")

# Studio section of every pack slot (brief §6.1).  A DRAFT proposal: the
# registry's ``section`` field, to be approved with the registry in P1/P5.
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


def _bootstrap():
    for p in ("extra_utilities/scripts", "extra_utilities/prompt_pdf", "."):
        sys.path.insert(0, str(REPO / p))
    sys.modules["simplejson"] = None          # type: ignore[assignment]
    sys.modules["chardet"] = None             # type: ignore[assignment]
    import bootstrap
    bootstrap.install()


def _pack_slots(P) -> dict[str, str]:
    """slot -> 'dc' | 'tool', for every $slot whose text lives in the pack
    (from the slot registry; runtime fragments are not $slots)."""
    return {name: ("dc" if spec["folder"] == "dc" else "tool")
            for name, spec in P._pack.slots(source="pack", use="prompt").items()}


# ---------------------------------------------------------------------------
# child: assemble one (combination, topology) twice, return spans
# ---------------------------------------------------------------------------

def _strip(marked: str, names: list[str]):
    text, spans, stack = [], [], []
    n = 0
    i = 0
    while i < len(marked):
        c = marked[i]
        if c == START and i + 1 < len(marked):
            stack.append((ord(marked[i + 1]) - ID0, n))
            i += 2
            continue
        if c == END:
            if stack:
                idx, s = stack.pop()
                if n > s:
                    spans.append([s, n, names[idx], len(stack)])
            i += 1
            continue
        text.append(c)
        n += 1
        i += 1
    while stack:
        idx, s = stack.pop()
        if n > s:
            spans.append([s, n, names[idx], len(stack)])
    return "".join(text), spans


def _norm(t: str):
    """Collapse whitespace runs; return (normalised, n_of[i] for i in t, idx)."""
    out, idx, n_of = [], [], []
    prev_ws = False
    for i, c in enumerate(t):
        ws = c.isspace()
        if ws and prev_ws:
            n_of.append(len(out) - 1)
            continue
        n_of.append(len(out))
        out.append(" " if ws else c)
        idx.append(i)
        prev_ws = ws
    n_of.append(len(out))
    return "".join(out), n_of, idx


def _child(combo: str, topology: int) -> int:
    _bootstrap()
    import prompt_matrix as PM
    # The same combination set-up as the prompt matrix, including the
    # parameter-access cells its old setting names stand for.
    PM.apply_config(combo)
    import topology_prompt_snapshot as T
    from agents.shared import prompts as P

    real = T._assemble(topology)["prompts"]
    pack = _pack_slots(P)
    names = sorted(pack) + ["routing_instructions", "render_check_library_block",
                            "image_persistence_block", "comparison_mode_block",
                            "chain_access_block", "user_inputs_dir",
                            "input_images_subdir", "extraction_output_file"]
    ids = {nm: i for i, nm in enumerate(names)}

    orig_mark = P.mark_inline_slots

    def marked_slots(slots):
        return orig_mark({k: (START + chr(ID0 + ids[k]) + v + END
                              if k in pack and v else v)
                          for k, v in slots.items()})
    P.mark_inline_slots = marked_slots

    orig_rt = T._runtime_slots

    def marked_runtime(agent, P_, S_):
        d = orig_rt(agent, P_, S_)
        if d is None:
            return None
        return {k: (START + chr(ID0 + ids[k]) + v + END if k in ids and v else v)
                for k, v in d.items()}
    T._runtime_slots = marked_runtime

    marked = T._assemble(topology)["prompts"]
    result = {"prompts": real, "spans": {}, "align": {}}
    for agent, text in real.items():
        stripped, spans = _strip(marked.get(agent, ""), names)
        if stripped == text:
            result["align"][agent] = "exact"
            result["spans"][agent] = spans
            continue
        ns, n_of_s, _ = _norm(stripped)
        nr, _, idx_r = _norm(text)
        if ns != nr:
            result["align"][agent] = "FAILED"
            result["spans"][agent] = []
            continue
        mapped = []
        for s, e, nm, depth in spans:
            a, b = n_of_s[s], n_of_s[e]
            if b <= a:
                continue
            mapped.append([idx_r[a], idx_r[b - 1] + 1, nm, depth])
        result["align"][agent] = "normalized"
        result["spans"][agent] = mapped
    sys.stdout.buffer.write(json.dumps(result).encode("utf-8"))
    return 0


def _run_children() -> dict:
    out = {}
    for combo in COMBOS:
        for n in TOPOLOGIES:
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "_child", combo, str(n)],
                capture_output=True, cwd=str(REPO))
            if proc.returncode != 0:
                raise SystemExit(proc.stderr.decode("utf-8", "replace")[-3000:])
            out[(combo, n)] = json.loads(proc.stdout.decode("utf-8"))
            bad = [a for a, s in out[(combo, n)]["align"].items() if s == "FAILED"]
            print(f"  {combo:<7} topology {n}: "
                  + ", ".join(f"{a}={s}" for a, s in sorted(out[(combo, n)]["align"].items()))
                  + (f"   !! no spans for {bad}" if bad else ""))
    return out


# ---------------------------------------------------------------------------
# parent: static pack data
# ---------------------------------------------------------------------------

def _read(p: Path, strip_both=False):
    if not p.is_file():
        return None
    t = p.read_text(encoding="utf-8")
    return t.strip() if strip_both else t.rstrip()


def _parameters(pack) -> dict:
    """The parameter set from its single source, ``dc_pack/parameters.json``
    (``engine/parameters.py``), plus each parameter's unit and description
    as the agents' hand-written ``$parameter_list`` text words them.
    ``copies_agree``: that text gives the same range as the file."""
    from engine import parameters as ep
    spec = ep.load()
    md = {}
    for line in pack.shared_path("parameter_list", pack.REFERENCE_TOPOLOGY).read_text(
            encoding="utf-8").splitlines():
        m = re.match(r"\s*\d+\.\s+(\w+)\s+\((.*?)\)\s+—\s+(.*?)\s*\[([\d.]+);\s*([\d.]+)\]\s*$", line)
        if m:
            md[m.group(1)] = {"unit_prompt": m.group(2), "description": m.group(3),
                              "min": float(m.group(4)), "max": float(m.group(5))}
    params = []
    for p in spec["parameters"]:
        a = md.get(p["name"], {})
        params.append({
            "name": p["name"], "type": p["type"], "group": p["group"],
            "label": p["label"], "unit": p["unit"],
            "unit_prompt": a.get("unit_prompt", ""), "description": a.get("description", ""),
            "min": p["min"], "max": p["max"], "step": p["step"], "default": p["default"],
            "copies_agree": (a.get("min"), a.get("max")) == (float(p["min"]), float(p["max"])),
        })
    groups = [{"id": g["id"], "label": g["label"]} for g in spec["groups"]]
    return {"groups": groups, "parameters": params}


def _topology_texts(pack, folder: Path, base: str, spec: dict) -> dict:
    """{"7"|"5"|"3": text or None} as stored on disk: the linked file for all
    three, else each topology's own ``.t<N>.md`` (None where there is none)."""
    linked = folder / f"{base}.md"
    if linked.is_file():
        t = pack._clean(spec, linked.read_text(encoding="utf-8"))
        return {"7": t, "5": t, "3": t}
    out = {}
    for n in ("7", "5", "3"):
        p = folder / f"{base}.t{n}.md"
        out[n] = pack._clean(spec, p.read_text(encoding="utf-8")) if p.is_file() else None
    return out


def _slots(P, pack_origin: dict, roles: dict) -> list:
    """Every pack $slot with its three topology texts and per-agent copies,
    read from dc_pack/ through the registry (engine/pack.py naming)."""
    pack = P._pack
    order = {s: i for lst in SECTION_OF.values() for i, s in enumerate(lst)}
    agents = sorted({a for t in roles["roster"].values() for a in t} | {"database_handler"})
    out = []
    for slot, spec in sorted(pack.slots(source="pack", use="prompt").items()):
        folder = pack.fragments_dir() / spec["folder"]
        overlay = spec.get("missing") == "empty"
        vals = ({"7": "", "5": "", "3": ""} if overlay
                else _topology_texts(pack, folder, slot, spec))
        variants = []
        for ag in agents:
            v = _topology_texts(pack, folder, f"{slot}@{ag}", spec)
            if any(x is not None for x in v.values()):
                variants.append({"agent": ag, "values": v})
        present = [x for x in vals.values() if x is not None]
        out.append({
            "slot": slot, "origin": pack_origin.get(slot, "dc"),
            "kind": spec["kind"],
            "section": spec.get("section", "other"), "order": order.get(slot, 999),
            "description": spec.get("description", "") or (
                "Per-agent overlay: each agent's own text for this tool; "
                "agents without a file get nothing." if overlay else ""),
            "values": vals,
            "linked": overlay or (len(present) == 3 and len(set(present)) == 1),
            "variants": variants,
        })
    return out


def _roles() -> dict:
    from agents.shared import agent_roles as AR
    from agents.shared.routing_tools import AGENT_DISPLAY
    disp = {k: (v if isinstance(v, str) else str(v)) for k, v in AGENT_DISPLAY.items()}
    disp.setdefault("database_handler", "Database Handler")
    return {"roster": {str(k): list(v) for k, v in AR.ROSTER.items()},
            "roles_of": {k: list(v) for k, v in AR.ROLES_OF.items()},
            "holder": {str(k): v for k, v in AR._HOLDER_BY_TOPOLOGY.items()},
            "display": disp}


def _parameter_access() -> dict:
    """The pack's parameter-access grid (engine/parameter_access.py), for the
    Agent access screen: one row per agent, its cell per topology."""
    from agents.shared import agent_roles
    from engine import parameter_access as pa
    names = dict(agent_roles.DISPLAY, database_handler="Database Handler")
    return {
        "states": [{"id": s, "short": s, "label": pa.LABELS[s]} for s in pa.STATES],
        "no_tool": sorted(pa.NO_TOOL_AGENTS),
        "rows": [{"agent": a, "name": names.get(a, a),
                  "cells": {str(t): s for t, s in row.items()}}
                 for a, row in pa.default_table().items()],
    }


def _settings_values(names) -> dict:
    tree = ast.parse((REPO / "workflow_settings/settings.py").read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in names and node.value is not None:
                try:
                    out[node.target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
    return out


def _docstring(path: str, func: str) -> str:
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func:
            return ast.get_docstring(node) or ""
    return ""


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


def _where(prompts: dict) -> dict:
    """slot -> list of landing sentences, grouped across agents/topologies."""
    groups = defaultdict(lambda: defaultdict(list))
    for (combo, topo), data in prompts.items():
        for agent, text in data["prompts"].items():
            for s, e, nm, _depth in data["spans"].get(agent, []):
                head = ""
                for line in reversed(text[:s].split("\n")):
                    if line.startswith("#"):
                        head = line.lstrip("#").strip()
                        break
                a = max(text.rfind(". ", 0, s) + 2, text.rfind("\n\n", 0, s) + 2, s - 220, 0)
                b_candidates = [x for x in (text.find(". ", e), text.find("\n\n", e)) if x != -1]
                b = min(b_candidates + [e + 220, len(text)])
                before = " ".join(text[a:s].split())
                value = " ".join(text[s:e].split())
                after = " ".join(text[e:b + 1].split())
                if len(value) > 260:
                    value = value[:240] + " …"
                key = (head, before, value, after)
                groups[nm][key].append((combo, topo, agent))
    out = {}
    for nm, g in groups.items():
        rows = []
        for (head, before, value, after), where in g.items():
            agents = defaultdict(set)
            combos = set()
            for combo, topo, agent in where:
                agents[agent].add(topo)
                combos.add(combo)
            rows.append({"heading": head, "before": before, "value": value,
                         "after": after,
                         "agents": {a: sorted(t, reverse=True) for a, t in agents.items()},
                         "only_with_features": combos == {"all_on"}})
        rows.sort(key=lambda r: (r["only_with_features"], -sum(len(t) for t in r["agents"].values())))
        out[nm] = rows
    return out


def _test_child(out_png: str, params_json: str) -> int:
    """What local mode's "Test tool" does for render_blade_sections: run the
    tool's own drawing function on the parameter defaults, in a subprocess."""
    import time
    _bootstrap()
    from tools.render_blade_sections.draw import render_png
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
    roots = [pack.pack_dir(), REPO / "web/images",
             REPO / "tools/generate_mesh", REPO / "tools/render_blade_sections"]
    return sum(p.stat().st_size for r in roots for p in r.rglob("*")
               if p.is_file() and "__pycache__" not in p.parts)


def _env_names() -> list:
    return sorted({ln.split("=", 1)[0].strip() for ln in
                   (REPO / ".env.example").read_text(encoding="utf-8").splitlines()
                   if re.match(r"^[A-Z][A-Z0-9_]*=", ln)})


def main() -> int:
    if sys.argv[1:2] == ["_child"]:
        return _child(sys.argv[2], int(sys.argv[3]))
    if sys.argv[1:2] == ["_test"]:
        return _test_child(sys.argv[2], sys.argv[3])
    print("assembling (2 combinations x 3 topologies, twice each) ...")
    prompts = _run_children()
    _bootstrap()
    from agents.shared import prompts as P
    pack = _pack_slots(P)
    roles = _roles()
    slots = _slots(P, pack, roles)
    data = {
        "pack": {"name": P._pack.read("dc_name", 7),
                 "domain": P._pack.read("domain_description", 7),
                 "parameter_count": P._GENERATED_SLOTS["parameter_count"]()},
        "parameters": _parameters(P._pack),
        "slots": slots,
        "roles": roles,
        "where": _where(prompts),
        "prompts": {f"{n}": {"prompts": prompts[("base", n)]["prompts"],
                             "spans": prompts[("base", n)]["spans"]}
                    for n in TOPOLOGIES},
        "align": {f"{c}/{n}": prompts[(c, n)]["align"] for c, n in prompts},
        "tools": [
            {"name": "generate_and_render_propeller", "display": "Propeller Configurator",
             "kind": "generator", "file": "tools/generate_mesh/generate_mesh.py",
             "description": _docstring("tools/generate_mesh/generate_mesh.py",
                                       "generate_and_render_propeller")},
            {"name": "render_blade_sections", "display": "Blade Sections",
             "kind": "alt_generator", "file": "tools/render_blade_sections/render_blade_sections.py",
             "description": _docstring("tools/render_blade_sections/render_blade_sections.py",
                                       "render_blade_sections")},
        ],
        "settings": _settings_values({
            "MESH_CHECKS", "RENDER_LIBRARY", "GEOMETRY_BACKEND", "ATTEMPT_VIEW_ISOMETRIC",
            "ATTEMPT_VIEW_TOP", "ATTEMPT_VIEW_SIDE", "ATTEMPT_VIEW_BLADE_SECTIONS",
            "BLADE_SECTIONS_VISUALIZER_ENABLED", "DC_PARAMS_PRIMER_ENABLED"}),
        "parameter_access": _parameter_access(),
        "validate": _validate(slots, set(P._build_slots())),
        # TODO F104 (extra_utilities/TODO_known_issues.md): fragments about the
        # blade-sections tool / the mesh checks that carry no feature marker.
        "f104": {"blade_sections": [
                     "directive_output_choice", "precision_multi_phase_rule",
                     "precision_continue_directive_example", "precision_match_subject",
                     "precision_match_targets", "sections_rerun_case",
                     "values_only_excluded_outputs", "geometry_tools_loading_rule"],
                 "mesh_checks": [
                     "quality_check_numbers", "quality_check_report",
                     "observable_fact_questions", "tool_run_history_contents"]},
        "matrix": _matrix_summary(),
        "pack_bytes": _pack_bytes(),
        "env_vars": _env_names(),
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
