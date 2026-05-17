"""Prompt assembly.

Each agent's per-agent template lives at ``agents/<agent>/prompt.md``.

DC-specific and tool-specific fragments (parameter list, structure,
modelling notes, capabilities, tool inventory, …) live in the
top-level ``DC_prompt_fragments/`` folder, split into ``dc_config/``
and ``tools_config/``.  Edit those when retargeting the system at a
different design configurator or swapping the bound tools.

The single generic-constraints fragment (DOs / DON'Ts every agent
inherits) lives at ``agents/shared/prompt_fragments/generic_constraints.md``.

Two placeholder syntaxes are used and they do NOT collide:

- ``$slot`` (Python ``string.Template``) — DC + tool fragments,
  filled at IMPORT TIME by ``_build_template()``.
- ``{slot}`` (Python ``.format()``) — per-agent runtime values
  (``{routing_instructions}``, ``{natural_pipeline}``,
  ``{chain_access_block}``, ``{user_inputs_dir}``,
  ``{dc_inspector_block}``, …), filled at WIRING TIME when each
  agent's ``set_routing_tools`` runs.

``string.Template.safe_substitute`` ignores ``{name}`` and ``.format``
ignores ``$name``, so the two stages stay independent.

The package's public constants are the assembled per-agent templates:
``RECEPTIONIST_TEMPLATE``, ``ORCHESTRATOR_TEMPLATE``, ``PLANNER_TEMPLATE``,
``UII_TEMPLATE``, ``DCIC_TEMPLATE``, ``DCII_TEMPLATE``,
``TOOL_CALLER_TEMPLATE``, ``DCOI_TEMPLATE``, ``DH_TEMPLATE``.

The DC + tool fragment constants (``DC_NAME``, ``PARAMETER_LIST``,
``MODELLING_NOTES``, …) are also exposed so agents can import them
directly when they need a single fragment.
"""

import re
from pathlib import Path
from string import Template

from agents.shared.routing import NATURAL_PIPELINE, routing_instructions
from workflow_settings import settings as _workflow_settings

AGENTS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = AGENTS_DIR.parent
DC_FRAGMENTS_DIR = REPO_ROOT / "DC_prompt_fragments"
DC_CONFIG_DIR = DC_FRAGMENTS_DIR / "dc_config"
TOOLS_CONFIG_DIR = DC_FRAGMENTS_DIR / "tools_config"
GENERIC_FRAGMENTS_DIR = Path(__file__).resolve().parent / "prompt_fragments"


# ---------------------------------------------------------------------------
# DC-Input-Inspector conditional filter
#
# When DC_INSPECTOR_ENABLED is False, every DCII reference must be
# stripped from every assembled system prompt — weaker models get
# confused by "the DCII is disabled this session" disclaimers and
# treat the agent as still present.  Authors mark conditional regions
# inline:
#
#   <<DCII_ONLY>>...<</DCII_ONLY>>   text shown only when DCII is ON
#   <<DCII_OFF>>...<</DCII_OFF>>     text shown only when DCII is OFF
#
# ``apply_dcii_filter`` runs AFTER all $-slot substitution so markers
# inside fragments and inside per-agent prompts are handled uniformly.
# ---------------------------------------------------------------------------

DCII_ENABLED = bool(_workflow_settings.DC_INSPECTOR_ENABLED)
PLANNER_FIRST = bool(_workflow_settings.PLANNER_FIRST)

_DCII_ONLY_RE = re.compile(r"<<DCII_ONLY>>(.*?)<</DCII_ONLY>>", re.DOTALL)
_DCII_OFF_RE = re.compile(r"<<DCII_OFF>>(.*?)<</DCII_OFF>>", re.DOTALL)
_PF_ON_RE = re.compile(r"<<PF_ON>>(.*?)<</PF_ON>>", re.DOTALL)
_PF_OFF_RE = re.compile(r"<<PF_OFF>>(.*?)<</PF_OFF>>", re.DOTALL)


def apply_dcii_filter(text: str) -> str:
    """Resolve <<DCII_ONLY>> / <<DCII_OFF>> conditional regions.

    On = strip the OFF blocks, unwrap the ONLY blocks.
    Off = strip the ONLY blocks, unwrap the OFF blocks.
    """
    if DCII_ENABLED:
        text = _DCII_OFF_RE.sub("", text)
        text = _DCII_ONLY_RE.sub(lambda m: m.group(1), text)
    else:
        text = _DCII_ONLY_RE.sub("", text)
        text = _DCII_OFF_RE.sub(lambda m: m.group(1), text)
    return text


def apply_planner_first_filter(text: str) -> str:
    """Resolve <<PF_ON>> / <<PF_OFF>> conditional regions.

    PF_ON  = Planner runs BEFORE the UII (v5 standard flow).
    PF_OFF = UII runs BEFORE the Planner.
    """
    if PLANNER_FIRST:
        text = _PF_OFF_RE.sub("", text)
        text = _PF_ON_RE.sub(lambda m: m.group(1), text)
    else:
        text = _PF_ON_RE.sub("", text)
        text = _PF_OFF_RE.sub(lambda m: m.group(1), text)
    return text


def apply_flag_filters(text: str) -> str:
    """Apply both DCII and PLANNER_FIRST filters in sequence."""
    return apply_planner_first_filter(apply_dcii_filter(text))


def _read_dc_fragment(rel_path: str) -> str:
    """Read a DC- or tool-specific fragment under ``DC_prompt_fragments/``."""
    return (DC_FRAGMENTS_DIR / rel_path).read_text(encoding="utf-8").rstrip()


def _read_generic_fragment(rel_path: str) -> str:
    """Read a generic fragment under ``agents/shared/prompt_fragments/``."""
    return (GENERIC_FRAGMENTS_DIR / rel_path).read_text(encoding="utf-8").rstrip()


# ---------------------------------------------------------------------------
# DC-specific content (loaded once at import time)
# ---------------------------------------------------------------------------

DC_NAME = _read_dc_fragment("dc_config/name.txt").strip()
DOMAIN_DESCRIPTION = _read_dc_fragment("dc_config/domain_description.txt").strip()
PARAMETER_COUNT = _read_dc_fragment("dc_config/parameter_count.txt").strip()
DC_STRUCTURE = _read_dc_fragment("dc_config/structure.md")
PARAMETER_LIST = _read_dc_fragment("dc_config/parameters.md")


def _parse_parameter_keys(rel_path: str) -> tuple[tuple[str, ...], dict[str, type]]:
    """Parse ``parameter_keys.txt`` into an ordered name tuple + type map."""
    raw = (DC_FRAGMENTS_DIR / rel_path).read_text(encoding="utf-8")
    names: list[str] = []
    types: dict[str, type] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, type_str = line.partition(":")
            key = key.strip()
            type_str = type_str.strip().lower()
            if type_str == "int":
                t = int
            elif type_str in ("float", ""):
                t = float
            else:
                raise ValueError(
                    f"Unknown type '{type_str}' for parameter '{key}' "
                    f"in {rel_path}.  Use 'int' or 'float'."
                )
        else:
            key = line
            t = float
        if key in types:
            raise ValueError(
                f"Duplicate parameter key '{key}' in {rel_path}."
            )
        names.append(key)
        types[key] = t
    return tuple(names), types


PARAMETER_NAMES, PARAMETER_TYPES = _parse_parameter_keys(
    "dc_config/parameter_keys.txt"
)
MODELLING_NOTES = _read_dc_fragment("dc_config/modelling_notes.md")
QUALITATIVE_TRANSLATION_EXAMPLES = _read_dc_fragment("dc_config/qualitative_examples.md")
VISUAL_INSPECTION_GUIDE = _read_dc_fragment("dc_config/visual_inspection_guide.md")
CAPABILITIES_CAN = _read_dc_fragment("dc_config/capabilities_can.md")
CAPABILITIES_CANNOT = _read_dc_fragment("dc_config/capabilities_cannot.md")
OUTPUT_FILE_LOCATIONS = _read_dc_fragment("dc_config/output_file_locations.md")
GEOMETRY_MODIFICATION_RULE = _read_dc_fragment("dc_config/geometry_modification_rule.md")
INVALID_PARAMETER_EXAMPLES = _read_dc_fragment("dc_config/invalid_parameter_examples.md")
HARD_CONSTRAINTS_DC = _read_dc_fragment("dc_config/hard_constraints_dc.md")

# User-input-type fragments — one pair per accepted input type.  See
# DC_prompt_fragments/dc_config/user_input_types/README.md for the
# convention.  When a DC does not accept a particular type, simply
# delete the corresponding files and the matching slot lines below.
SKETCH_HANDLING = _read_dc_fragment(
    "dc_config/user_input_types/sketch_handling.md"
)
SKETCH_NOTES = _read_dc_fragment(
    "dc_config/user_input_types/sketch_notes.md"
)


# ---------------------------------------------------------------------------
# Tools-specific content
# ---------------------------------------------------------------------------

TOOL_INVENTORY = _read_dc_fragment("tools_config/tool_inventory.md")
TOOL_CALLER_INSTRUCTIONS = _read_dc_fragment("tools_config/tool_caller_instructions.md")
TOOL_CALLER_CAPABILITIES = _read_dc_fragment("tools_config/tool_caller_capabilities.md")
AGENT_TOOLS_OVERVIEW = _read_dc_fragment("tools_config/agent_tools_overview.md")
# Shorter, role-focused overview consumed only by the Database Handler.
# Strips the detailed tool listings — the DH is interested in WHAT
# each agent does, not in every bound tool.
AGENT_TOOLS_OVERVIEW_BRIEF = _read_dc_fragment(
    "tools_config/agent_tools_overview_brief.md"
)
HARD_CONSTRAINTS_TOOLS = _read_dc_fragment("tools_config/hard_constraints_tools.md")
# Web-interface-only display tool.  Bound to the Receptionist alone and
# meaningful only when the DC is driven through the web UI, so its
# agent-facing description + usage rules live in a tool fragment
# instead of being hardcoded in the Receptionist prompt body.
VISUALIZE_3D_MODEL_TOOL = _read_dc_fragment(
    "tools_config/visualize_3d_model.md"
)

# Paired render / mesh-check backend fragments — exactly one is
# spliced into the Tool Caller's prompt per session via the runtime
# ``{render_check_library_block}`` placeholder.  See
# DC_prompt_fragments/tools_config/render_check_library/README.md.
RENDER_CHECK_LIBRARY_TRIMESH = _read_dc_fragment(
    "tools_config/render_check_library/trimesh.md"
)
RENDER_CHECK_LIBRARY_PYVISTA = _read_dc_fragment(
    "tools_config/render_check_library/pyvista.md"
)


# ---------------------------------------------------------------------------
# Generic constraints (applies to every agent)
# ---------------------------------------------------------------------------

HARD_CONSTRAINTS_GENERIC = _read_generic_fragment("generic_constraints.md")


# ---------------------------------------------------------------------------
# Per-agent routing fragments — "which agents can you call" sections.
#
# The Receptionist and Orchestrator splice their fragments at IMPORT
# time via the $-slot mechanism (their roster is static).  The six
# chain agents (Planner, UII, DCIC, DCII, TC, DCOI) load their
# fragments at WIRING time via routing_instructions(...) instead, so
# they are NOT exposed as $-slots here.
# ---------------------------------------------------------------------------

ROUTING_RECEPTIONIST = _read_generic_fragment("routing_receptionist.md")
ROUTING_ORCHESTRATOR = _read_generic_fragment("routing_orchestrator.md")


# ---------------------------------------------------------------------------
# Cross-agent organisational fragments
#
# Both the Planner and the Orchestrator describe the canonical pipeline
# flow for the design workflow.  Authored once in ``pipeline_flow.md``
# and spliced into both prompts via ``$pipeline_flow``.
#
# The Planner additionally needs a directory of every agent in the
# system (with role descriptions); authored in ``available_agents.md``
# and spliced via ``$available_agents``.  This fragment itself
# references ``$parameter_count`` and ``$tool_inventory``, so
# ``_build_template`` runs a second substitution pass to resolve the
# nested $-placeholders.
# ---------------------------------------------------------------------------

_PIPELINE_FLOW_FRAGMENT_NAME = (
    "pipeline_flow_planner_first.md" if PLANNER_FIRST
    else "pipeline_flow_uii_first.md"
)
PIPELINE_FLOW = _read_generic_fragment(_PIPELINE_FLOW_FRAGMENT_NAME)
AVAILABLE_AGENTS = _read_generic_fragment("available_agents.md")


# Embedding-related settings consumed by the Database Handler's
# system prompt.  The DH uses these to shape SEMANTIC answers so they
# fit the embedding model's tokenizer (``cl100k_base`` for
# ``text-embedding-3-large``).
EMBEDDING_PROVIDER = str(_workflow_settings.EMBEDDING_PROVIDER)
EMBEDDING_MODEL = str(_workflow_settings.EMBEDDING_MODEL)
EMBEDDING_VECTOR_DIMS = str(_workflow_settings.EMBEDDING_VECTOR_DIMS)
EMBEDDING_MAX_RESPONSE_TOKENS = str(
    _workflow_settings.EMBEDDING_MAX_RESPONSE_TOKENS
)


# Common slot map fed into ``string.Template.safe_substitute``.  Every
# per-agent template has access to every slot; templates that don't
# need a slot simply don't reference it.
_SLOTS: dict[str, str] = {
    # DC-specific
    "dc_name": DC_NAME,
    "domain_description": DOMAIN_DESCRIPTION,
    "parameter_count": PARAMETER_COUNT,
    "dc_structure": DC_STRUCTURE,
    "parameter_list": PARAMETER_LIST,
    "modelling_notes": MODELLING_NOTES,
    "qualitative_examples": QUALITATIVE_TRANSLATION_EXAMPLES,
    "visual_inspection_guide": VISUAL_INSPECTION_GUIDE,
    "capabilities_can": CAPABILITIES_CAN,
    "capabilities_cannot": CAPABILITIES_CANNOT,
    "output_file_locations": OUTPUT_FILE_LOCATIONS,
    "geometry_modification_rule": GEOMETRY_MODIFICATION_RULE,
    "invalid_parameter_examples": INVALID_PARAMETER_EXAMPLES,
    "hard_constraints_dc": HARD_CONSTRAINTS_DC,
    # User-input-type fragments (one pair per accepted type)
    "sketch_handling": SKETCH_HANDLING,
    "sketch_notes": SKETCH_NOTES,
    # Tool-specific
    "tool_inventory": TOOL_INVENTORY,
    "tool_caller_instructions": TOOL_CALLER_INSTRUCTIONS,
    "tool_caller_capabilities": TOOL_CALLER_CAPABILITIES,
    "agent_tools_overview": AGENT_TOOLS_OVERVIEW,
    "agent_tools_overview_brief": AGENT_TOOLS_OVERVIEW_BRIEF,
    "hard_constraints_tools": HARD_CONSTRAINTS_TOOLS,
    "visualize_3d_model_tool": VISUALIZE_3D_MODEL_TOOL,
    # Generic
    "hard_constraints_generic": HARD_CONSTRAINTS_GENERIC,
    # Per-agent routing fragments (Receptionist + Orchestrator only;
    # the six chain agents load theirs via routing_instructions())
    "routing_receptionist": ROUTING_RECEPTIONIST,
    "routing_orchestrator": ROUTING_ORCHESTRATOR,
    # Cross-agent organisational fragments (Planner + Orchestrator)
    "pipeline_flow": PIPELINE_FLOW,
    "available_agents": AVAILABLE_AGENTS,
    # Embedding (DH only) — see workflow_settings/settings.py
    "embedding_provider": EMBEDDING_PROVIDER,
    "embedding_model": EMBEDDING_MODEL,
    "embedding_vector_dims": EMBEDDING_VECTOR_DIMS,
    "embedding_max_response_tokens": EMBEDDING_MAX_RESPONSE_TOKENS,
}


def _build_template(agent_dir_name: str) -> str:
    """Assemble one per-agent template by substituting DC + tool slots.

    Each agent owns ``agents/<agent_dir_name>/prompt.md``.  This loader
    reads it and resolves every ``$slot`` via
    ``string.Template.safe_substitute`` (unrecognised slots are left
    as-is).  Per-agent runtime ``{name}`` placeholders survive
    untouched and are filled by the agent at wiring time.

    Two passes are run so a fragment may itself reference another
    ``$slot`` (e.g. ``available_agents.md`` references
    ``$parameter_count`` and ``$tool_inventory``).  One level of
    nesting is enough for current usage; deeper nesting would require
    more passes or a fixed-point loop.
    """
    raw = (AGENTS_DIR / agent_dir_name / "prompt.md").read_text(encoding="utf-8")
    once = Template(raw).safe_substitute(_SLOTS)
    twice = Template(once).safe_substitute(_SLOTS)
    return apply_flag_filters(twice)


# ---------------------------------------------------------------------------
# Per-agent assembled templates
# ---------------------------------------------------------------------------

RECEPTIONIST_TEMPLATE = _build_template("receptionist")
ORCHESTRATOR_TEMPLATE = _build_template("orchestrator")
PLANNER_TEMPLATE = _build_template("planner")
UII_TEMPLATE = _build_template("user_input_inspector")
DCIC_TEMPLATE = _build_template("dc_input_creator")
DCII_TEMPLATE = _build_template("dc_input_inspector")
TOOL_CALLER_TEMPLATE = _build_template("tool_caller")
DCOI_TEMPLATE = _build_template("dc_output_inspector")
DH_TEMPLATE = _build_template("database_handler")


# Re-export routing helpers so agents can do ``from agents.shared.prompts
# import NATURAL_PIPELINE, routing_instructions`` for one-stop access.
__all__ = [
    "NATURAL_PIPELINE",
    "routing_instructions",
    "DC_NAME",
    "DOMAIN_DESCRIPTION",
    "PARAMETER_COUNT",
    "DC_STRUCTURE",
    "PARAMETER_LIST",
    "PARAMETER_NAMES",
    "PARAMETER_TYPES",
    "MODELLING_NOTES",
    "QUALITATIVE_TRANSLATION_EXAMPLES",
    "VISUAL_INSPECTION_GUIDE",
    "CAPABILITIES_CAN",
    "CAPABILITIES_CANNOT",
    "OUTPUT_FILE_LOCATIONS",
    "GEOMETRY_MODIFICATION_RULE",
    "INVALID_PARAMETER_EXAMPLES",
    "HARD_CONSTRAINTS_DC",
    "SKETCH_HANDLING",
    "SKETCH_NOTES",
    "TOOL_INVENTORY",
    "TOOL_CALLER_INSTRUCTIONS",
    "TOOL_CALLER_CAPABILITIES",
    "AGENT_TOOLS_OVERVIEW",
    "AGENT_TOOLS_OVERVIEW_BRIEF",
    "HARD_CONSTRAINTS_TOOLS",
    "RENDER_CHECK_LIBRARY_TRIMESH",
    "RENDER_CHECK_LIBRARY_PYVISTA",
    "HARD_CONSTRAINTS_GENERIC",
    "ROUTING_RECEPTIONIST",
    "ROUTING_ORCHESTRATOR",
    "PIPELINE_FLOW",
    "AVAILABLE_AGENTS",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "EMBEDDING_VECTOR_DIMS",
    "EMBEDDING_MAX_RESPONSE_TOKENS",
    "RECEPTIONIST_TEMPLATE",
    "ORCHESTRATOR_TEMPLATE",
    "PLANNER_TEMPLATE",
    "UII_TEMPLATE",
    "DCIC_TEMPLATE",
    "DCII_TEMPLATE",
    "TOOL_CALLER_TEMPLATE",
    "DCOI_TEMPLATE",
    "DH_TEMPLATE",
]
