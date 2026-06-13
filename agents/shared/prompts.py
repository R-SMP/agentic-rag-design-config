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
# Per-agent DBa filter — mirrors the DCII_ONLY pattern but the
# enabling flag is per-agent (workflow_settings/database_access.py +
# global RAG_ENABLED master switch).  Stripped at template-build
# time when the agent does NOT have database access; otherwise
# unwrapped to expose the inner content.  See ``apply_dba_filter``.
_HAS_DBA_RE = re.compile(r"<<HAS_DBA>>(.*?)<</HAS_DBA>>", re.DOTALL)


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


def apply_dba_filter(text: str, agent_dir_name: str) -> str:
    """Resolve ``<<HAS_DBA>>...<</HAS_DBA>>`` conditional regions
    for one agent's template.

    The enabling condition is per-agent and consults BOTH the
    global ``RAG_ENABLED`` master switch AND the per-agent flag in
    ``workflow_settings/database_access.json``.  See
    :func:`workflow_settings.database_access.is_enabled_for`.

    On (the agent has database access)
        unwrap the region — keep its inner content verbatim.
    Off (the agent does NOT have access)
        strip the region entirely.  Used to remove the
        ``## Searching past saved sessions`` heading +
        ``$database_search_tool`` fragment from agents that lack
        access, so the LLM never sees stale references to a tool
        it can't call.

    Agents whose ``agent_dir_name`` is not in
    ``database_access.DEFAULT_AGENTS`` (currently just
    ``database_handler``) are treated as "no access" — any
    ``<<HAS_DBA>>`` region in their prompt is stripped.
    """
    # Local import to avoid an unconditional dependency in this
    # module — database_access itself imports workflow_settings,
    # which is already imported here, so the actual import chain
    # is fine, but keeping the import inside the function makes
    # the dependency direction obvious in `import` statements.
    from workflow_settings import database_access as _database_access

    if _database_access.is_enabled_for(agent_dir_name):
        text = _HAS_DBA_RE.sub(lambda m: m.group(1), text)
    else:
        text = _HAS_DBA_RE.sub("", text)
    return text


def apply_flag_filters(text: str) -> str:
    """Apply both DCII and PLANNER_FIRST filters in sequence.

    NOTE: per-agent filters (currently :func:`apply_dba_filter`)
    are applied separately in :func:`_build_template` because they
    need to know which agent's template is being assembled.
    """
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
# Web-interface-only UI-update tool.  Bound to the Receptionist alone
# (Step 9 of the Parameters Inputs redesign — see
# extra_utilities/web_interface_notes.md §§3-7).  Fires the
# params_proposed SSE event that updates the Parameters Inputs view's
# slider colours / labels.  Same templating idiom as
# VISUALIZE_3D_MODEL_TOOL above.
PROPOSE_ATTEMPT_TOOL = _read_dc_fragment(
    "tools_config/propose_attempt.md"
)
# Semantic vector search over past saved sessions' Q+A.  Bound (via
# the closure factory ``make_database_search_tool``) to the 8 live-
# session chain agents — Receptionist, Orchestrator, Planner, UII,
# DCIC, DCII, DCOI, Tool Caller — see Q-4A-13 in
# extra_utilities/db_design/database_and_RAG_architecture.md §9.11.
# Skipped for the Database Handler (write-only, post-session).
DATABASE_SEARCH_TOOL = _read_dc_fragment(
    "tools_config/database_search.md"
)
# R2-backed retrieval of past saved sessions' user inputs (Phase 5B).
# Bound to the same 8 live-session chain agents (closure factory
# ``make_retrieve_user_inputs_tool``).  The dispatcher in
# ``agents/shared/retrieve_tool_dispatcher.py`` intercepts the
# tool call and attaches both the XML response (ToolMessage) and
# any image bytes (HumanMessage content blocks) for the next turn.
RETRIEVE_USER_INPUTS_TOOL = _read_dc_fragment(
    "tools_config/retrieve_user_inputs.md"
)
# R2-backed retrieval of past saved attempts' description / parameters /
# renders (Phase 5C).  Same binding + dispatcher pattern as
# RETRIEVE_USER_INPUTS_TOOL.  Render-view selection is governed by
# the three workflow flags in settings.py block #21.
RETRIEVE_ATTEMPT_TOOL = _read_dc_fragment(
    "tools_config/retrieve_attempt.md"
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


# ---------------------------------------------------------------------------
# Slot-map builder
#
# Hoisted from the former module-level ``_SLOTS`` dict so the System
# Prompts UI's save endpoint can take effect on the NEXT session's
# agent construction without a Python restart.  Every call re-reads
# the ~30 fragment files from disk; cost is negligible relative to a
# single LLM round-trip.
#
# Module-level constants above (DC_NAME, PARAMETER_LIST, ...) stay
# captured at import time for back-compat with any caller that does
# ``from agents.shared.prompts import DC_NAME`` — they are NOT used by
# ``_build_template`` any more.
#
# Per-agent overlays (``database_search_<agent_dir>.md``) are NOT in
# this dict — they are merged in by :func:`_build_template` because
# the choice of overlay depends on which agent is being assembled.
# ---------------------------------------------------------------------------


def _build_slots() -> dict[str, str]:
    """Re-read every fragment from disk and assemble the $-slot map."""
    return {
        # DC-specific
        "dc_name": _read_dc_fragment("dc_config/name.txt").strip(),
        "domain_description": _read_dc_fragment("dc_config/domain_description.txt").strip(),
        "parameter_count": _read_dc_fragment("dc_config/parameter_count.txt").strip(),
        "dc_structure": _read_dc_fragment("dc_config/structure.md"),
        "parameter_list": _read_dc_fragment("dc_config/parameters.md"),
        "modelling_notes": _read_dc_fragment("dc_config/modelling_notes.md"),
        "qualitative_examples": _read_dc_fragment("dc_config/qualitative_examples.md"),
        "visual_inspection_guide": _read_dc_fragment("dc_config/visual_inspection_guide.md"),
        "capabilities_can": _read_dc_fragment("dc_config/capabilities_can.md"),
        "capabilities_cannot": _read_dc_fragment("dc_config/capabilities_cannot.md"),
        "output_file_locations": _read_dc_fragment("dc_config/output_file_locations.md"),
        "geometry_modification_rule": _read_dc_fragment("dc_config/geometry_modification_rule.md"),
        "invalid_parameter_examples": _read_dc_fragment("dc_config/invalid_parameter_examples.md"),
        "hard_constraints_dc": _read_dc_fragment("dc_config/hard_constraints_dc.md"),
        # User-input-type fragments (one pair per accepted type)
        "sketch_handling": _read_dc_fragment("dc_config/user_input_types/sketch_handling.md"),
        "sketch_notes": _read_dc_fragment("dc_config/user_input_types/sketch_notes.md"),
        # Tool-specific
        "tool_inventory": _read_dc_fragment("tools_config/tool_inventory.md"),
        "tool_caller_instructions": _read_dc_fragment("tools_config/tool_caller_instructions.md"),
        "tool_caller_capabilities": _read_dc_fragment("tools_config/tool_caller_capabilities.md"),
        "agent_tools_overview": _read_dc_fragment("tools_config/agent_tools_overview.md"),
        "agent_tools_overview_brief": _read_dc_fragment("tools_config/agent_tools_overview_brief.md"),
        "hard_constraints_tools": _read_dc_fragment("tools_config/hard_constraints_tools.md"),
        "visualize_3d_model_tool": _read_dc_fragment("tools_config/visualize_3d_model.md"),
        "propose_attempt_tool": _read_dc_fragment("tools_config/propose_attempt.md"),
        "database_search_tool": _read_dc_fragment("tools_config/database_search.md"),
        "retrieve_user_inputs_tool": _read_dc_fragment("tools_config/retrieve_user_inputs.md"),
        "retrieve_attempt_tool": _read_dc_fragment("tools_config/retrieve_attempt.md"),
        # Generic
        "hard_constraints_generic": _read_generic_fragment("generic_constraints.md"),
        # Per-agent routing fragments (Receptionist + Orchestrator only;
        # the six chain agents load theirs via routing_instructions())
        "routing_receptionist": _read_generic_fragment("routing_receptionist.md"),
        "routing_orchestrator": _read_generic_fragment("routing_orchestrator.md"),
        # Cross-agent organisational fragments (Planner + Orchestrator)
        "pipeline_flow": _read_generic_fragment(_PIPELINE_FLOW_FRAGMENT_NAME),
        "available_agents": _read_generic_fragment("available_agents.md"),
        # Embedding (DH only) — settings.py values, captured at import time
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

    The slot map is rebuilt fresh on every call (via
    :func:`_build_slots`) so live edits to .md fragments via the
    System Prompts UI take effect on the next session's agent
    construction without a Python restart.
    """
    raw = (AGENTS_DIR / agent_dir_name / "prompt.md").read_text(encoding="utf-8")
    # Per-agent overlay onto the global slot map: load this agent's
    # ``database_search_<agent_dir_name>.md`` fragment if present and
    # expose it as ``$database_search_per_agent``.  Agents without a
    # matching fragment (currently just the Database Handler, which is
    # write-only post-session and has no <<HAS_DBA>> block in its
    # prompt) get an empty string — harmless because their prompt.md
    # does not reference the slot.
    per_agent_dbs_file = TOOLS_CONFIG_DIR / f"database_search_{agent_dir_name}.md"
    per_agent_dbs = (
        per_agent_dbs_file.read_text(encoding="utf-8").rstrip()
        if per_agent_dbs_file.exists()
        else ""
    )
    slots = {**_build_slots(), "database_search_per_agent": per_agent_dbs}
    once = Template(raw).safe_substitute(slots)
    twice = Template(once).safe_substitute(slots)
    filtered = apply_flag_filters(twice)
    # apply_dba_filter is per-agent (consults the per-agent flag in
    # database_access.json + the RAG_ENABLED master switch), so it
    # runs separately from the global apply_flag_filters chain.
    return apply_dba_filter(filtered, agent_dir_name)


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
    "RETRIEVE_USER_INPUTS_TOOL",
    "RETRIEVE_ATTEMPT_TOOL",
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
