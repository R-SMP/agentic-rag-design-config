"""Dump a topology's assembled system prompts + bound tools.

Runs the REAL assembler (agents.shared.prompts) and the REAL langchain tool
objects, with every workflow setting left at its committed default.  Each
agent is produced twice -- RAG_ENABLED False and True -- so the caller can
mark exactly which text and which tools RAG adds.

    py -3.13 dump.py                 # topology 7 -> dump.json  (the default)
    py -3.13 dump.py --topology 5    # topology 5 -> dump5.json

The default is unchanged in every respect, output filename included, so the
PDF builder and anything else reading dump.json keeps working untouched.
"""
import io
import json
import sys

import bootstrap

REPO = bootstrap.install()

TOPOLOGY = 7
if "--topology" in sys.argv:
    TOPOLOGY = int(sys.argv[sys.argv.index("--topology") + 1])

import workflow_settings.settings as S
S.SYSTEM_TOPOLOGY = TOPOLOGY

from workflow_settings import database_access, ocr_access, blade_sections_access

# Production (Railway/Docker) paths.  The Dockerfile's WORKDIR is /app and
# config.py derives every path from PROJECT_ROOT = the repo root, so these
# are what the deployed agents read.
USER_INPUTS_DIR = "/app/inputs"
EXTRACTION_FILE = "/app/inputs/extracted_inputs.txt"
USER_QUERY_FILE = "/app/inputs/user_query.txt"
INPUT_IMAGES_SUBDIR = "input_images"

from agents.shared import prompts as P
from agents.shared.dba_tools import dba_tools_for
from agents.shared.attempts_tool import read_attempts
from agents.shared.dc_params_tool import build_dc_params_list, dc_params_list
from agents.shared.user_inputs_tool import (
    READ_INPUTS_DOC_DCOI, READ_INPUTS_DOC_PLANNER, build_read_user_inputs,
    build_user_inputs_tools,
)
from agents.shared.history_tool import build_read_agent_history_tool
from agents.shared.routing_tools import build_routing_tool
from agents.receptionist.propose_attempt_tool import propose_attempt
from tools.calculate.calculate import calculate
from tools.visualize_model.visualize_model import visualize_3d_model
from tools import get_tools
from tools.render_blade_sections.render_blade_sections import render_blade_sections

import agents.orchestrator.orchestrator as ORCH
import agents.planner.planner as PLAN
import agents.user_input_inspector.user_input_inspector as UII_M
import agents.dc_input_creator.dc_input_creator as DCIC_M
import agents.dc_input_inspector.dc_input_inspector as DCII_M
import agents.dc_output_inspector.dc_output_inspector as DCOI_M
from agents.database_handler import dh_tools, batch_tools

# Both axes exist only where the hub is the Orchestrator; prompts.py forces
# them off elsewhere, so read the EFFECTIVE values rather than the raw flags.
DCII_ON = P._dcii_effective()
PF = P._planner_first_effective()
if TOPOLOGY == 7:
    assert not PF, "this dump assumes the committed default PLANNER_FIRST=False"
    assert DCII_ON, ("this dump assumes the committed default "
                     "DC_INSPECTOR_ENABLED=True")


class _FakeSession:
    """build_routing_tool only needs .chain_log_exchanges."""
    chain_log_exchanges: list = []


class _FakeAgent:
    _pending_hop = None


_SESS = _FakeSession()


def rt(caller, target):
    return build_routing_tool(caller, target, _FakeAgent(), _SESS)


# --------------------------------------------------------------------------
# Runtime {slot} values -- transcribed from each agent's set_routing_tools /
# __init__, with the committed default settings.
# --------------------------------------------------------------------------
def runtime_slots():
    return {
        "receptionist": dict(
            user_inputs_dir=USER_INPUTS_DIR,
            extraction_output_file=EXTRACTION_FILE,
        ),
        "orchestrator": dict(
            chain_access_block=(
                ORCH._CHAIN_ACCESS_ON if S.CHAIN_ACCESS
                else ORCH._CHAIN_ACCESS_OFF
            ),
        ),
        "planner": dict(
            routing_instructions=P.routing_instructions(
                agent_name="Planner", next_agent="DC Input Creator",
                prev_agent="User Input Inspector",
                fragment_name="routing_planner_uii_first.md",
            ),
            user_inputs_dir=USER_INPUTS_DIR,
            input_images_subdir=INPUT_IMAGES_SUBDIR,
            extraction_output_file=EXTRACTION_FILE,
        ),
        "user_input_inspector": dict(
            routing_instructions=P.routing_instructions(
                agent_name="User Input Inspector", next_agent="Planner",
                prev_agent=None,
                fragment_name="routing_user_input_inspector_uii_first.md",
            ),
        ),
        "dc_input_creator": dict(
            routing_instructions=P.routing_instructions(
                agent_name="DC Input Creator",
                next_agent="DC Input Inspector" if DCII_ON else "Tool Caller",
                prev_agent="Planner",
                fragment_name="routing_dc_input_creator_uii_first.md",
            ),
        ),
        "dc_input_inspector": dict(
            routing_instructions=P.routing_instructions(
                agent_name="DC Input Inspector", next_agent="Tool Caller",
                prev_agent="DC Input Creator",
                fragment_name="routing_dc_input_inspector.md",
            ),
        ),
        "tool_caller": dict(
            routing_instructions=P.routing_instructions(
                agent_name="Tool Caller", next_agent="DC Output Inspector",
                prev_agent="DC Input Inspector" if DCII_ON else "DC Input Creator",
                fragment_name="routing_tool_caller.md",
            ),
            render_check_library_block=(
                (
                    P.RENDER_CHECK_LIBRARY_PYVISTA
                    if S.RENDER_LIBRARY == "pyvista"
                    else P.RENDER_CHECK_LIBRARY_TRIMESH
                )
                if S.MESH_CHECKS else P.RENDER_CHECK_LIBRARY_OFF
            ),
        ),
        "dc_output_inspector": dict(
            routing_instructions=P.routing_instructions(
                agent_name="DC Output Inspector", next_agent=None,
                prev_agent="Tool Caller",
                fragment_name="routing_dc_output_inspector.md",
            ),
            image_persistence_block=(
                DCOI_M._IMAGE_PERSISTENCE_ON if S.KEEP_IMAGES_IN_CONTEXT
                else DCOI_M._IMAGE_PERSISTENCE_OFF
            ),
            comparison_mode_block=DCOI_M._build_comparison_mode_block(
                S.DCOI_COMPARISON_MODE, EXTRACTION_FILE, USER_QUERY_FILE,
            ),
        ),
        "database_handler": {},
    }


# --------------------------------------------------------------------------
# Per-agent bound-tool lists, in bind order (replicating each agent's
# set_routing_tools / set_tools exactly).
# --------------------------------------------------------------------------
def tools_for(agent):
    if agent == "receptionist":
        routing = [build_read_agent_history_tool(lambda *a, **k: []),
                   rt("receptionist", "orchestrator")]
        return (list(routing) + [read_attempts,
                                 visualize_3d_model,
                                 build_dc_params_list("receptionist"),
                                 propose_attempt]
                + dba_tools_for("receptionist"))

    if agent == "orchestrator":
        t = [rt("orchestrator", "planner"),
             rt("orchestrator", "user_input_inspector"),
             rt("orchestrator", "dc_input_creator"),
             rt("orchestrator", "tool_caller"),
             rt("orchestrator", "dc_output_inspector"),
             rt("orchestrator", "receptionist"),
             read_attempts, dc_params_list,
             build_read_agent_history_tool(lambda *a, **k: [])]
        t.extend(dba_tools_for("orchestrator"))
        if DCII_ON:
            t.insert(4, rt("orchestrator", "dc_input_inspector"))
        return t

    if agent == "planner":
        routing = ([rt("planner", "dc_input_creator"),
                    rt("planner", "user_input_inspector"),
                    rt("planner", "orchestrator")] if not PF else
                   [rt("planner", "user_input_inspector"),
                    rt("planner", "orchestrator")])
        t = ([build_read_user_inputs(doc=READ_INPUTS_DOC_PLANNER,
                                     direct_provider="openai"),
              PLAN.read_extracted_inputs]
             + [build_read_agent_history_tool(lambda *a, **k: [])]
             + [read_attempts, dc_params_list]
             + routing)
        t.extend(dba_tools_for("planner"))
        return t

    if agent == "user_input_inspector":
        extra = list(dba_tools_for("user_input_inspector"))
        routing = ([rt("user_input_inspector", "planner"),
                    rt("user_input_inspector", "orchestrator")] if not PF else
                   [rt("user_input_inspector", "dc_input_creator"),
                    rt("user_input_inspector", "planner"),
                    rt("user_input_inspector", "orchestrator")])
        return ([UII_M._build_read_user_inputs("user_input_inspector"),
                 UII_M.write_extraction]
                + extra
                + build_user_inputs_tools("user_input_inspector",
                                          include_text_tools=False)
                + routing)

    if agent == "dc_input_creator":
        extra = [read_attempts, calculate]
        extra += dba_tools_for("dc_input_creator")
        routing = [rt("dc_input_creator",
                      "dc_input_inspector" if DCII_ON else "tool_caller"),
                   rt("dc_input_creator",
                      "user_input_inspector" if PF else "planner"),
                   rt("dc_input_creator", "orchestrator")]
        if DCII_ON:
            routing.append(rt("dc_input_creator", "tool_caller"))
        return ([DCIC_M.read_extracted_inputs, DCIC_M.new_attempt_parameters]
                + extra
                + routing)

    if agent == "dc_input_inspector":
        extra = [calculate, read_attempts]
        extra += dba_tools_for("dc_input_inspector")
        routing = [rt("dc_input_inspector", "tool_caller"),
                   rt("dc_input_inspector", "dc_input_creator"),
                   rt("dc_input_inspector", "orchestrator")]
        return ([build_read_user_inputs(), DCII_M.read_extracted_inputs]
                + extra
                + build_user_inputs_tools("dc_input_inspector",
                                          include_text_tools=False)
                + routing)

    if agent == "tool_caller":
        utility = list(get_tools()) + [read_attempts]
        utility += dba_tools_for("tool_caller")
        if blade_sections_access.is_enabled():
            utility.append(render_blade_sections)
        routing = [rt("tool_caller", "dc_output_inspector"),
                   rt("tool_caller",
                      "dc_input_inspector" if DCII_ON else "dc_input_creator"),
                   rt("tool_caller", "orchestrator")]
        return utility + routing

    if agent == "dc_output_inspector":
        extra = [read_attempts, calculate]
        extra += dba_tools_for("dc_output_inspector")
        routing = [rt("dc_output_inspector", "tool_caller"),
                   rt("dc_output_inspector", "orchestrator")]
        return ([DCOI_M.read_extracted_inputs,
                 build_read_user_inputs(doc=READ_INPUTS_DOC_DCOI)]
                + extra
                + build_user_inputs_tools("dc_output_inspector",
                                          include_text_tools=False)
                + routing)

    if agent == "database_handler":
        # Never simultaneously bound: the DH binds ONE of these per turn with
        # tool_choice forcing it, then unbinds (W18/W20 invariant).
        return [batch_tools.submit_batch_plan, batch_tools.submit_questions,
                batch_tools.submit_batch, dh_tools.save_attempt_data]

    raise KeyError(agent)


def tool_record(t):
    try:
        args = t.args
    except Exception:
        args = {}
    required = []
    try:
        required = list(t.tool_call_schema.model_json_schema().get("required", []))
    except Exception:
        pass
    return {"name": t.name, "description": t.description,
            "args": args, "required": required}


AGENTS_BY_TOPOLOGY = {
    7: ["receptionist", "orchestrator", "planner", "user_input_inspector",
        "dc_input_creator", "dc_input_inspector", "tool_caller",
        "dc_output_inspector", "database_handler"],
    # Topology 5: the 7-agent set minus the Orchestrator and the DC Input
    # Inspector, with the Planner as hub.
    5: ["receptionist", "planner", "user_input_inspector",
        "dc_input_creator", "tool_caller", "dc_output_inspector",
        "database_handler"],
}
AGENTS = AGENTS_BY_TOPOLOGY[TOPOLOGY]

# Under topology 5 the routing EDGES differ (agents/planner5/planner5.py) and
# the hub is the Planner running the Planner's prompt.  Rather than fork
# tools_for(), post-process it: strip every routing tool the 7-agent wiring
# produced and re-add this topology's, which keeps the UTILITY half -- the
# part that is genuinely shared, because the classes are the same objects.
_EDGES_5 = {
    "receptionist":         ["planner"],
    "planner":              ["user_input_inspector", "dc_input_creator",
                             "dc_output_inspector", "receptionist"],
    "user_input_inspector": ["planner"],
    "dc_input_creator":     ["tool_caller", "planner"],
    "tool_caller":          ["dc_output_inspector", "dc_input_creator"],
    "dc_output_inspector":  ["tool_caller", "dc_input_creator", "planner"],
    "database_handler":     [],
}

_tools_for_7 = tools_for


def tools_for(agent):                     # noqa: F811 - deliberate wrapper
    t = _tools_for_7(agent)
    if TOPOLOGY == 7:
        return t
    utility = [x for x in t if not getattr(x, "name", "").startswith("call_")]
    return utility + [rt(agent, tgt) for tgt in _EDGES_5.get(agent, [])]

out = {
    "config": {
        "SYSTEM_TOPOLOGY": S.SYSTEM_TOPOLOGY,
        "dba_profile": database_access.profile_key(),
        "DC_INSPECTOR_ENABLED": bool(S.DC_INSPECTOR_ENABLED),
        "PLANNER_FIRST": bool(S.PLANNER_FIRST),
        "MESH_CHECKS": bool(S.MESH_CHECKS),
        "RENDER_LIBRARY": S.RENDER_LIBRARY,
        "GEOMETRY_BACKEND": S.GEOMETRY_BACKEND,
        "BLADE_SECTIONS_VISUALIZER_ENABLED": bool(S.BLADE_SECTIONS_VISUALIZER_ENABLED),
        "OCR_ENABLED": bool(S.OCR_ENABLED),
        "CHAIN_ACCESS": bool(S.CHAIN_ACCESS),
        "KEEP_IMAGES_IN_CONTEXT": bool(S.KEEP_IMAGES_IN_CONTEXT),
        "DCOI_COMPARISON_MODE": S.DCOI_COMPARISON_MODE,
        "RAG_ENABLED_default": bool(S.RAG_ENABLED),
        "ocr_per_agent": {a: ocr_access.is_enabled_for(a) for a in AGENTS},
        "user_inputs_dir": USER_INPUTS_DIR,
    },
    "dba_grid": database_access.get_all_tools("7-reduced"),
    "agents": {},
}

for a in AGENTS:
    rec = {}
    for flag, key in ((False, "rag_off"), (True, "rag_on")):
        S.RAG_ENABLED = flag
        slots = runtime_slots()[a]
        text = P._build_template(a)
        if slots:
            text = text.format(**slots)
        rec[key] = {
            "prompt": text,
            "tools": [tool_record(t) for t in tools_for(a)],
        }
    rec["prompt_path"] = str(P._prompt_path(a).relative_to(REPO)).replace("\\", "/")
    out["agents"][a] = rec

S.RAG_ENABLED = False

_name = "dump.json" if TOPOLOGY == 7 else f"dump{TOPOLOGY}.json"
with io.open(REPO / "extra_utilities" / "prompt_pdf" / _name,
             "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(f"wrote {_name}  (topology {TOPOLOGY}, {len(AGENTS)} agents)")
for a in AGENTS:
    r = out["agents"][a]
    print("{:22s} off={:6d} on={:6d} tools off={:2d} on={:2d}  [{}]".format(
        a, len(r["rag_off"]["prompt"]), len(r["rag_on"]["prompt"]),
        len(r["rag_off"]["tools"]), len(r["rag_on"]["tools"]),
        r["prompt_path"]))
