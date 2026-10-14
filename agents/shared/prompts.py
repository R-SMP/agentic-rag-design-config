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

Each agent assembles its own prompt when it is constructed, with
``_build_template(<agent_dir>)``, so every build is topology-correct and
reads the fragments fresh from disk.  The module deliberately exposes no
pre-built templates or fragment copies (removed 2026-10-10, TODO F90): a
constant built at import would be frozen to whatever topology was on disk
then.  ``DC_NAME`` and ``PARAMETER_NAMES`` are data, not prompt text.
"""

import re
import textwrap
from pathlib import Path
from string import Template

# ``routing_instructions`` is re-exported: every agent imports it from THIS
# module, so this stays the one import site that reaches all eight.
from agents.shared.routing import natural_pipeline, routing_instructions

# Topology facts live in their own dependency-free module so that
# ``routing_tools`` (a leaf) can read them too.  Aliased to the private
# names this module has always used, so call sites below are unchanged.
from agents.shared.topology import (
    hub_key as _hub_agent,
    topology as _topology,
)
from workflow_settings import settings as _workflow_settings

AGENTS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = AGENTS_DIR.parent
DC_FRAGMENTS_DIR = REPO_ROOT / "DC_prompt_fragments"
TOOLS_CONFIG_DIR = DC_FRAGMENTS_DIR / "tools_config"
GENERIC_FRAGMENTS_DIR = Path(__file__).resolve().parent / "prompt_fragments"


# ---------------------------------------------------------------------------
# Agent topology
#
# A topology owns ``agents/<N>agent/``, holding ONLY the files that differ
# from the 7-agent originals.  Each is named with an ``_<N>agents`` suffix
# and filed under a sub-folder mirroring its SOURCE root:
#
#   agents/5agent/prompt_fragments/generic_constraints_5agents.md
#        overrides  agents/shared/prompt_fragments/generic_constraints.md
#   agents/5agent/dc_config/hard_constraints_dc_5agents.md
#        overrides  DC_prompt_fragments/dc_config/hard_constraints_dc.md
#   agents/5agent/tools_config/database_search_creator_5agents.md
#        overrides  DC_prompt_fragments/tools_config/database_search_creator.md
#   agents/5agent/receptionist/prompt_5agents.md
#        overrides  agents/receptionist/prompt.md
#
# Anything WITHOUT an override is shared: read from the original path, one
# copy, cannot drift.  The suffix makes each file self-identifying — an
# editor tab or a log line reading ``generic_constraints_5agents.md`` names
# its topology; a bare ``generic_constraints.md`` in a sibling folder does
# not.
#
# There is no ``agents/7agent/``, so under topology 7 every lookup below
# misses and falls through to the path it used before this indirection
# existed.
# ---------------------------------------------------------------------------

def _topology_override(rel_path: str) -> Path | None:
    """This topology's override of ``rel_path``, or None for the shared file.

    ``rel_path`` is relative to the topology directory and keeps its source
    sub-folder (``dc_config/x.md``, ``prompt_fragments/y.md``,
    ``<agent>/prompt.md``); only the basename gains the suffix.  Returning
    None is every caller's signal to read the shared original, which is what
    makes topology 7 — with no topology directory at all — behave exactly as
    it did before.
    """
    topo = _topology()
    rel = Path(rel_path)

    # Two layers, most specific first:
    #
    #   agents/<N>agent/…/<name>_<N>agents.md
    #
    # then the shared original.  A topology with no folder, or one that has
    # not written an override for this file, falls through to the shared
    # file — which is why a half-finished topology is safe to select: every
    # unwritten override is simply the shared text.
    candidates = [(
        AGENTS_DIR / f"{topo}agent",
        f"{rel.stem}_{topo}agents{rel.suffix}",
    )]

    for topo_dir, name in candidates:
        if not topo_dir.is_dir():
            continue
        cand = (topo_dir / rel).with_name(name)
        if cand.is_file():
            return cand
    return None


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


# Both constants above are IMPORT-time snapshots, and both describe axes
# that exist ONLY in the 7-agent system:
#
#   * topology 5 has no DC Input Inspector at all -- it was merged away --
#     so <<DCII_ONLY>> text there names an agent that is never built;
#   * topology 5's hub IS the Planner, so there is no Planner/UII ordering
#     to choose and <<PF_ON>>/<<PF_OFF>> has nothing to select between.
#
# The two helpers below force both axes off for every topology that does not
# have the agents they describe, and read the topology fresh on each call
# because the Sessions Queue switches it between runs inside one process (see
# topology.py).
#
# They key on the resolved HUB, not on ``topology() == 7``.  Any topology
# whose hub is the Orchestrator IS the 7-agent agent set -- including an
# UNREGISTERED topology number, which ``_HUB_BY_TOPOLOGY`` deliberately falls
# back to the Orchestrator for.  Keying on the number instead made that
# fallback build DIFFERENT prompts from topology 7, which is exactly what the
# fallback exists to avoid; smoke_test_topology_fragments' DEGRADE case
# caught it.


def _dcii_effective() -> bool:
    """Is the DC Input Inspector present in the ACTIVE topology?"""
    return DCII_ENABLED if _hub_agent() == "orchestrator" else False


def dcii_effective() -> bool:
    """Public alias of :func:`_dcii_effective`.

    The Database Handler needs the same answer this module already
    computes.  Without it the two layers disagree: the prompt layer
    strips every DCII reference under topology 5, while the DH's gate
    reads ``session.dc_inspector_enabled`` -- seeded from a setting whose
    default is True and which has NO topology dimension -- so the three
    DCII schedule rows fall through to the unknown-agent branch and are
    persisted as ``ERROR:`` chunks.
    """
    return _dcii_effective()


def _planner_first_effective() -> bool:
    """Does the ACTIVE topology have a Planner/UII ordering to choose?"""
    return PLANNER_FIRST if _hub_agent() == "orchestrator" else False

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
# Finer than <<HAS_DBA>>, which asks "holds ANY database tool".  The
# ``$retrieve_user_inputs_tool`` fragment is shown to holders of EITHER
# retrieve tool (see _DBA_TOOL_SLOTS), so text about a retrieved
# USER-INPUTS folder needs its own region, or it reaches attempt-only
# holders -- the DC Input Creator, the DC Output Inspector, the topology-3
# Design Engineer -- as a capability they do not have.
_HAS_USER_INPUTS_RE = re.compile(
    r"<<HAS_USER_INPUTS>>(.*?)<</HAS_USER_INPUTS>>", re.DOTALL)
# Two VERSIONS of a passage, not a show/hide: whichever does not apply is
# stripped, so exactly one survives.  Same shape as <<BSV_ON>>/<<BSV_OFF>>.
#
# The alternative -- one passage with "if you hold an image tool ..." in it --
# was rejected deliberately.  It asks the model to introspect about its own
# toolset, which the assembler already knows at build time, and it hands an
# agent that CAN look an explicit branch for handing the work off instead.
# Resolving capability here is the same principle _build_template already
# applies to the DBa slots: a tool an agent does not hold is not described
# to it.
_CAN_SEE_RE = re.compile(r"<<CAN_SEE>>(.*?)<</CAN_SEE>>", re.DOTALL)
_CANNOT_SEE_RE = re.compile(r"<<CANNOT_SEE>>(.*?)<</CANNOT_SEE>>", re.DOTALL)

# Agents that bind an image-viewing tool.  The source of truth is each
# agent's own ``can_view_images=`` argument where it calls
# ``read_user_inputs_summary``; this mirrors it so prompt assembly can branch
# without importing the agent modules (which drags in the 3D render stack).
# ``smoke_test_prompt_image_regions.py`` (removed 2026-10-10; restore it from
# git, see extra_utilities/extra_info.md §13) asserted the two agree.  Without
# that check this set rots silently the first time an agent gains or loses an
# image tool, and the wrong version of the passage ships.
_AGENTS_WITH_IMAGE_TOOLS = frozenset({
    "user_input_inspector",
    "dc_input_inspector",
    "dc_output_inspector",
    "requirements_analyst",
})


# Which database tool(s) each DBa slot describes.  A slot is blanked only
# when the agent holds NONE of its tools -- ``$retrieve_user_inputs_tool``
# is the "Retrieving past saved content" fragment, which covers BOTH
# retrieve tools, so an agent holding either one still needs it.
_DBA_TOOL_SLOTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("database_search_tool",       ("search",)),
    ("database_search_per_agent",  ("search",)),
    ("retrieve_user_inputs_tool",  ("user_inputs", "attempt")),
    ("retrieve_attempt_tool",      ("attempt",)),
)
# Global Blade-sections-visualizer filter — mirrors the DCII_ONLY pattern,
# gated by the ``BLADE_SECTIONS_VISUALIZER_ENABLED`` master switch (read fresh
# via ``workflow_settings.blade_sections_access`` so a Workflow-Settings edit
# takes effect next session).  See ``apply_bsv_filter``.
_BSV_ON_RE = re.compile(r"<<BSV_ON>>(.*?)<</BSV_ON>>", re.DOTALL)
_BSV_OFF_RE = re.compile(r"<<BSV_OFF>>(.*?)<</BSV_OFF>>", re.DOTALL)
# Global mesh-quality-checks filter — mirrors the BSV pattern, gated by the
# ``MESH_CHECKS`` workflow setting.  With the checks off the pipeline never
# produces watertightness / volume / degenerate-face numbers, so prose
# describing them is dead text in every prompt that carries it.  Read fresh,
# not captured at import, because ``web_app._build_session`` reloads
# ``workflow_settings`` in place and the Sessions Queue switches settings
# between runs inside one process.  See ``apply_mesh_checks_filter``.
_MESH_ON_RE = re.compile(r"<<MESH_ON>>(.*?)<</MESH_ON>>", re.DOTALL)
_MESH_OFF_RE = re.compile(r"<<MESH_OFF>>(.*?)<</MESH_OFF>>", re.DOTALL)
# A <<MESH_ON>> region that is a whole line on its own (e.g. an inspector
# role-list item spliced from tools_config) goes together with its line
# when mesh checks are off, so the list keeps no empty line.
_MESH_ON_LINE_RE = re.compile(
    r"^<<MESH_ON>>(?:(?!<</MESH_ON>>)[^\n])*<</MESH_ON>>\n", re.MULTILINE)
# Global UII-parameter-list filter, gated by ``UII_PARAMETER_LIST_ENABLED``.
# The markers appear only in the UII's own prompt and its scoped
# ``parameters_user_input_inspector.md``, so a global filter is safe: no other
# agent's template carries them.  See ``apply_uii_params_filter``.
_UII_PARAMS_ON_RE = re.compile(r"<<UII_PARAMS_ON>>(.*?)<</UII_PARAMS_ON>>",
                               re.DOTALL)
_UII_PARAMS_OFF_RE = re.compile(r"<<UII_PARAMS_OFF>>(.*?)<</UII_PARAMS_OFF>>",
                                re.DOTALL)
# Global DCOI-ranges filter, gated by ``DCOI_KNOWS_PARAMS_RANGES``.  Same
# reasoning: the markers live only in the DCOI's prompt and its scoped
# ``parameters_dc_output_inspector.md``.  See ``apply_dcoi_ranges_filter``.
_DCOI_RANGES_ON_RE = re.compile(r"<<DCOI_RANGES_ON>>(.*?)<</DCOI_RANGES_ON>>",
                                re.DOTALL)
_DCOI_RANGES_OFF_RE = re.compile(
    r"<<DCOI_RANGES_OFF>>(.*?)<</DCOI_RANGES_OFF>>", re.DOTALL)
# Global RAG switch.  Unlike ``<<HAS_DBA>>``, which asks whether THIS agent
# holds a database tool, ``<<RAG_ON>>`` asks only whether the RAG layer is on
# at all.  The distinction is load-bearing: the Tool Caller holds no database
# tool, so every ``<<HAS_DBA>>`` region is stripped from its prompt — yet it
# is the hop that relays past-session ids on to the DC Output Inspector, and
# so needs text that appears exactly when RAG is enabled.
_RAG_ON_RE = re.compile(r"<<RAG_ON>>(.*?)<</RAG_ON>>", re.DOTALL)

# Per-agent chain-only filter — strips ``<<CHAIN_ONLY>>`` regions from the
# agents that are NOT links in the forward chain, and unwraps them for the
# ones that are.  See ``apply_chain_only_filter``.
_CHAIN_ONLY_RE = re.compile(r"<<CHAIN_ONLY>>(.*?)<</CHAIN_ONLY>>", re.DOTALL)

# The non-chain agents: the Receptionist, which composes the user's wording
# rather than passing work along, and each topology's HUB — the Orchestrator
# in the 7-agent system — which dispatches and receives rather than
# forwarding to a "next" agent.
#
# ⚠ Topology 5's hub is the PLANNER, and it is deliberately NOT listed: this
# frozenset is keyed by agent name with no topology dimension, so adding
# "planner" would strip the <<CHAIN_ONLY>> regions from the 7-agent Planner
# too — a live behaviour change.  Topology 5 therefore keeps those regions,
# which is also what "identical to topology 7 first" requires.  Topology 3's
# hub is the Planner too, so the same reasoning applies there; the fix for
# both is a topology-scoped ``generic_constraints_planner`` override, never
# a row here.
#
# EVERY hub is listed unconditionally.  This is a delete-list keyed by agent
# name; it is never rendered into any prompt, and each hub is only ever
# built in its own topology, so the entries for the absent hubs are simply
# never consulted.  Miss a hub here and it KEEPS the ``<<CHAIN_ONLY>>``
# rules — i.e. it is told to escalate to itself.
_NON_CHAIN_AGENTS = frozenset({
    "receptionist", "orchestrator",
})


def apply_dcii_filter(text: str) -> str:
    """Resolve <<DCII_ONLY>> / <<DCII_OFF>> conditional regions.

    On = strip the OFF blocks, unwrap the ONLY blocks.
    Off = strip the ONLY blocks, unwrap the OFF blocks.
    """
    if _dcii_effective():
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
    if _planner_first_effective():
        text = _PF_OFF_RE.sub("", text)
        text = _PF_ON_RE.sub(lambda m: m.group(1), text)
    else:
        text = _PF_ON_RE.sub("", text)
        text = _PF_OFF_RE.sub(lambda m: m.group(1), text)
    return text


def apply_bsv_filter(text: str) -> str:
    """Resolve ``<<BSV_ON>>`` / ``<<BSV_OFF>>`` regions for the Blade-sections
    visualizer tool.

    Gated by the global ``BLADE_SECTIONS_VISUALIZER_ENABLED`` switch, read
    fresh (``web_app._build_session`` reloads ``workflow_settings`` before
    building the agents) so a toggle saved in the Workflow Settings editor
    takes effect on the next session — the same contract as the DBa / OCR
    toggles.

    On  = strip the OFF blocks, unwrap the ON blocks (full / brief fragments).
    Off = strip the ON blocks, unwrap the OFF blocks (the minimal
          "exists but currently OFF" note).
    """
    from workflow_settings import blade_sections_access

    if blade_sections_access.is_enabled():
        text = _BSV_OFF_RE.sub("", text)
        text = _BSV_ON_RE.sub(lambda m: m.group(1), text)
    else:
        text = _BSV_ON_RE.sub("", text)
        text = _BSV_OFF_RE.sub(lambda m: m.group(1), text)
    return text


def apply_mesh_checks_filter(text: str) -> str:
    """Resolve ``<<MESH_ON>>`` / ``<<MESH_OFF>>`` regions.

    Gated by the ``MESH_CHECKS`` workflow setting, read fresh so a toggle
    saved in the Workflow Settings editor takes effect on the next session —
    the same contract as the BSV / DBa / OCR toggles.

    On  = strip the OFF blocks, unwrap the ON blocks.
    Off = strip the ON blocks, unwrap the OFF blocks.
    """
    if bool(_workflow_settings.MESH_CHECKS):
        text = _MESH_OFF_RE.sub("", text)
        text = _MESH_ON_RE.sub(lambda m: m.group(1), text)
    else:
        text = _MESH_ON_LINE_RE.sub("", text)
        text = _MESH_ON_RE.sub("", text)
        text = _MESH_OFF_RE.sub(lambda m: m.group(1), text)
    return text


def apply_uii_params_filter(text: str) -> str:
    """Resolve ``<<UII_PARAMS_ON>>`` / ``<<UII_PARAMS_OFF>>`` regions.

    Gated by ``UII_PARAMETER_LIST_ENABLED``, read fresh so a toggle saved in
    the Workflow Settings editor takes effect on the next session — the same
    contract as the BSV / MESH / DBa toggles.
    """
    if bool(getattr(_workflow_settings, "UII_PARAMETER_LIST_ENABLED", False)):
        text = _UII_PARAMS_OFF_RE.sub("", text)
        text = _UII_PARAMS_ON_RE.sub(lambda m: m.group(1), text)
    else:
        text = _UII_PARAMS_ON_RE.sub("", text)
        text = _UII_PARAMS_OFF_RE.sub(lambda m: m.group(1), text)
    return text


def apply_dcoi_ranges_filter(text: str) -> str:
    """Resolve ``<<DCOI_RANGES_ON>>`` / ``<<DCOI_RANGES_OFF>>`` regions.

    Gated by ``DCOI_KNOWS_PARAMS_RANGES``, read fresh, same contract as above.
    """
    if bool(getattr(_workflow_settings, "DCOI_KNOWS_PARAMS_RANGES", False)):
        text = _DCOI_RANGES_OFF_RE.sub("", text)
        text = _DCOI_RANGES_ON_RE.sub(lambda m: m.group(1), text)
    else:
        text = _DCOI_RANGES_ON_RE.sub("", text)
        text = _DCOI_RANGES_OFF_RE.sub(lambda m: m.group(1), text)
    return text


def apply_rag_on_filter(text: str) -> str:
    """Resolve ``<<RAG_ON>>`` regions against the global RAG master switch.

    Deliberately NOT per-agent.  ``apply_dba_filter`` asks "does this agent
    hold a database tool?" and strips the region when it does not; this asks
    only "is the RAG layer on?".  The Tool Caller needs the second question:
    it holds no database tool, so a ``<<HAS_DBA>>`` region could never survive
    in its prompt, but it is the hop that must carry past-session ids forward
    to the DC Output Inspector.  Read fresh, same contract as the filters
    above.
    """
    if bool(getattr(_workflow_settings, "RAG_ENABLED", False)):
        return _RAG_ON_RE.sub(lambda m: m.group(1), text)
    return _RAG_ON_RE.sub("", text)


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
        ``## Database tools`` heading +
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
    if _database_access.is_enabled_for(agent_dir_name, "user_inputs"):
        text = _HAS_USER_INPUTS_RE.sub(lambda m: m.group(1), text)
    else:
        text = _HAS_USER_INPUTS_RE.sub("", text)
    return text


def apply_image_tools_filter(text: str, agent_dir_name: str) -> str:
    """Resolve ``<<CAN_SEE>>`` / ``<<CANNOT_SEE>>`` for one agent.

    Some shared fragments describe what to do with a retrieved IMAGE.  That
    instruction is only true for an agent that binds an image tool; for the
    others -- the DC Input Creator in topologies 7 and 5, the topology-3
    Design Engineer -- it used to read as an instruction to do something
    impossible, and it contradicted the ``database_search`` text telling them
    to hand a visual question on.  See ``F100``.

    Exactly one of the two regions survives: the version that does not apply
    is stripped whole.
    """
    can_see = agent_dir_name in _AGENTS_WITH_IMAGE_TOOLS
    if can_see:
        text = _CAN_SEE_RE.sub(lambda m: m.group(1), text)
        text = _CANNOT_SEE_RE.sub("", text)
    else:
        text = _CAN_SEE_RE.sub("", text)
        text = _CANNOT_SEE_RE.sub(lambda m: m.group(1), text)
    return text


def apply_chain_only_filter(text: str, agent_dir_name: str) -> str:
    """Resolve ``<<CHAIN_ONLY>>...<</CHAIN_ONLY>>`` conditional regions.

    The chain-only constraints — FORWARD-to-your-next-agent,
    escalate-to-the-hub, don't-bounce-permission-questions-backward,
    don't-retry-blindly, don't-script-the-user-facing-reply — only make
    sense for an agent that is a LINK in the forward chain.  Given to the
    hub itself they are self-referential ("escalate to the Conductor",
    addressed to the Conductor), so they are stripped for every agent in
    ``_NON_CHAIN_AGENTS`` and unwrapped for the rest.  The Database
    Handler has no such regions, so unwrapping is a no-op there.

    Like :func:`apply_dba_filter`, this is per-agent and therefore runs in
    :func:`_build_template` rather than in :func:`apply_flag_filters`.
    """
    if agent_dir_name in _NON_CHAIN_AGENTS:
        return _CHAIN_ONLY_RE.sub("", text)
    return _CHAIN_ONLY_RE.sub(lambda m: m.group(1), text)


def apply_flag_filters(text: str) -> str:
    """Apply the DCII, PLANNER_FIRST, BSV, MESH_CHECKS, UII-parameter-list,
    DCOI-ranges and RAG_ON filters in sequence.

    The last two are global even though their markers appear in only one
    agent's files each: the marker names are unique, so a template that does
    not carry them is untouched.

    NOTE: per-agent filters (:func:`apply_dba_filter`,
    :func:`apply_chain_only_filter`) are applied separately in
    :func:`_build_template` because they need to know which agent's
    template is being assembled.
    """
    return apply_rag_on_filter(
        apply_dcoi_ranges_filter(
            apply_uii_params_filter(
                apply_mesh_checks_filter(
                    apply_bsv_filter(
                        apply_planner_first_filter(apply_dcii_filter(text))
                    )
                )
            )
        )
    )


def _read_dc_fragment(rel_path: str) -> str:
    """Read a DC- or tool-specific fragment under ``DC_prompt_fragments/``,
    preferring the active topology's override when one exists."""
    path = _topology_override(rel_path) or (DC_FRAGMENTS_DIR / rel_path)
    return path.read_text(encoding="utf-8").rstrip()


def _read_generic_fragment(rel_path: str) -> str:
    """Read a generic fragment under ``agents/shared/prompt_fragments/``,
    preferring the active topology's override when one exists."""
    path = (
        _topology_override(f"prompt_fragments/{rel_path}")
        or GENERIC_FRAGMENTS_DIR / rel_path
    )
    return path.read_text(encoding="utf-8").rstrip()


# ---------------------------------------------------------------------------
# DC-specific content (loaded once at import time)
#
# "Once at import time" is a REAL constraint, not a note about cost: these
# constants are resolved against whatever SYSTEM_TOPOLOGY was on disk when
# this module was first imported, and the Sessions Queue switches topology
# between runs inside one process (agents/shared/topology.py:11-15).  They
# are safe only because they are OFF the prompt-assembly path -- see the
# note above _build_slots(), which re-reads every fragment from disk on
# every call.  Do NOT consume these constants at agent-construction time:
# call _read_dc_fragment() / _read_generic_fragment() there instead.
# ---------------------------------------------------------------------------

DC_NAME = _read_dc_fragment("dc_config/name.txt").strip()


def _parse_parameter_keys(rel_path: str) -> tuple[tuple[str, ...], dict[str, type]]:
    """Parse ``parameter_keys.txt`` into an ordered name tuple + type map."""
    # The ONE reader here that deliberately does NOT go through
    # _topology_override.  The design configurator's parameters do not
    # depend on the topology: this file is DATA (the canonical key list
    # used by the runtime validator and for JSON ordering), not prompt
    # text, and it is not a $slot.  So there is nothing to fork, and a
    # per-topology copy would be a second source of truth for one fact.
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


# ---------------------------------------------------------------------------
# Tools-specific content
# ---------------------------------------------------------------------------

# Paired render / mesh-check backend fragments — exactly one is
# spliced into the Tool Caller's prompt per session via the runtime
# ``{render_check_library_block}`` placeholder.  See
# DC_prompt_fragments/tools_config/render_check_library/README.md.
# The agents read the fragment fresh at wiring time; these three
# constants are read only by the prompt snapshot and PDF tools
# (extra_utilities/scripts/topology_prompt_snapshot.py, prompt_pdf/dump.py).
RENDER_CHECK_LIBRARY_TRIMESH = _read_dc_fragment(
    "tools_config/render_check_library/trimesh.md"
)
RENDER_CHECK_LIBRARY_PYVISTA = _read_dc_fragment(
    "tools_config/render_check_library/pyvista.md"
)
# Substituted for the backend block when the session has mesh checks OFF —
# the metrics those fragments describe are then never produced.
RENDER_CHECK_LIBRARY_OFF = _read_dc_fragment(
    "tools_config/render_check_library/off.md"
)


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

def _pipeline_flow_fragment_name() -> str:
    """Which pipeline-flow fragment this topology + flag combination wants.

    ``PLANNER_FIRST`` picks the Planner/UII ordering, but that choice only
    exists in the 7-agent system — in the 5-agent one the Conductor IS the
    planner, so there is no ordering to pick and a single flow file covers
    both settings of the flag.  A topology shipping its own
    ``pipeline_flow_<N>agents.md`` therefore uses it unconditionally; one
    that does not falls through to the historic two-file choice.
    """
    if _topology_override("prompt_fragments/pipeline_flow.md") is not None:
        return "pipeline_flow.md"
    return (
        "pipeline_flow_planner_first.md" if _planner_first_effective()
        else "pipeline_flow_uii_first.md"
    )


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
# Reverse index: fragment FILE -> the $slot it feeds
#
# Lives HERE, next to _build_slots below, so a new $slot and its
# reverse-index entry are one screen apart — if you add a $slot, add the FRAGMENT_TO_SLOT entry in the
# same commit.
# ---------------------------------------------------------------------------

# Path → $-slot name.  Paths are RELATIVE to the repo root.  Every
# fragment that _build_slots reads is listed here, .md or .txt.  The
# tree-builder filters by .md extension; the .txt entries exist so
# any caller (including future validation) can reverse-resolve them.
FRAGMENT_TO_SLOT: dict[str, str] = {
    # DC-config fragments
    "DC_prompt_fragments/dc_config/name.txt":                      "dc_name",
    "DC_prompt_fragments/dc_config/domain_description.txt":        "domain_description",
    "DC_prompt_fragments/dc_config/parameter_count.txt":           "parameter_count",
    "DC_prompt_fragments/dc_config/structure.md":                  "dc_structure",
    "DC_prompt_fragments/dc_config/parameters.md":                 "parameter_list",
    "DC_prompt_fragments/dc_config/modelling_notes.md":            "modelling_notes",
    "DC_prompt_fragments/dc_config/qualitative_examples.md":       "qualitative_examples",
    "DC_prompt_fragments/dc_config/visual_inspection_guide.md":    "visual_inspection_guide",
    "DC_prompt_fragments/dc_config/capabilities_can.md":           "capabilities_can",
    "DC_prompt_fragments/dc_config/capabilities_cannot.md":        "capabilities_cannot",
    "DC_prompt_fragments/dc_config/output_file_locations.md":      "output_file_locations",
    "DC_prompt_fragments/dc_config/geometry_modification_rule.md": "geometry_modification_rule",
    "DC_prompt_fragments/dc_config/invalid_parameter_examples.md": "invalid_parameter_examples",
    "DC_prompt_fragments/dc_config/hard_constraints_dc.md":        "hard_constraints_dc",
    # User-input-type fragments
    "DC_prompt_fragments/dc_config/user_input_types/sketch_handling.md": "sketch_handling",
    "DC_prompt_fragments/dc_config/user_input_types/sketch_notes.md":    "sketch_notes",
    # DC-SPECIFIC EXAMPLES split out of sketch_handling so the surrounding
    # guidance can stay configurator-agnostic: the verdict wording a sketch
    # precision statement uses, and a worked crop-box example.  Referenced
    # today only by the 7-agent reduced variant's scoped sketch_handling; the
    # shared originals exist so the slots always resolve.
    "DC_prompt_fragments/dc_config/user_input_types/sketch_precision_examples.md": "sketch_precision_examples",
    "DC_prompt_fragments/dc_config/user_input_types/sketch_crop_example.md":       "sketch_crop_example",
    # Tools-config fragments
    "DC_prompt_fragments/tools_config/tool_inventory.md":             "tool_inventory",
    "DC_prompt_fragments/tools_config/tool_caller_instructions.md":   "tool_caller_instructions",
    "DC_prompt_fragments/tools_config/tool_caller_capabilities.md":   "tool_caller_capabilities",
    "DC_prompt_fragments/tools_config/agent_tools_overview.md":       "agent_tools_overview",
    "DC_prompt_fragments/tools_config/agent_tools_overview_brief.md": "agent_tools_overview_brief",
    "DC_prompt_fragments/tools_config/hard_constraints_tools.md":     "hard_constraints_tools",
    "DC_prompt_fragments/tools_config/visualize_3d_model.md":         "visualize_3d_model_tool",
    "DC_prompt_fragments/tools_config/propose_attempt.md":            "propose_attempt_tool",
    "DC_prompt_fragments/tools_config/database_search.md":            "database_search_tool",
    "DC_prompt_fragments/tools_config/retrieve_user_inputs.md":       "retrieve_user_inputs_tool",
    "DC_prompt_fragments/tools_config/retrieve_attempt.md":           "retrieve_attempt_tool",
    # Relocated DC- / tool-specific text (generic-fragments audit, 2026-10)
    "DC_prompt_fragments/tools_config/geometry_tool_name.md":                   "geometry_tool_name",
    "DC_prompt_fragments/tools_config/quality_check_numbers.md":                "quality_check_numbers",
    "DC_prompt_fragments/tools_config/quality_check_report.md":                 "quality_check_report",
    "DC_prompt_fragments/tools_config/mesh_check_role_item.md":                 "mesh_check_role_item",
    "DC_prompt_fragments/tools_config/qc_numerics_verdict_rule.md":             "qc_numerics_verdict_rule",
    "DC_prompt_fragments/tools_config/no_render_fallback_qc.md":                "no_render_fallback_qc",
    "DC_prompt_fragments/tools_config/geometry_model_filename.md":              "geometry_model_filename",
    "DC_prompt_fragments/tools_config/render_view_list.md":                     "render_view_list",
    "DC_prompt_fragments/tools_config/roster_sections_tool_sentence.md":        "roster_sections_tool_sentence",
    "DC_prompt_fragments/tools_config/roster_tools_clause.md":                  "roster_tools_clause",
    "DC_prompt_fragments/tools_config/routing_sections_alternative.md":         "routing_sections_alternative",
    "DC_prompt_fragments/tools_config/sections_rerun_case.md":                  "sections_rerun_case",
    "DC_prompt_fragments/tools_config/directive_output_choice.md":              "directive_output_choice",
    "DC_prompt_fragments/tools_config/precision_multi_phase_rule.md":           "precision_multi_phase_rule",
    "DC_prompt_fragments/tools_config/geometry_tools_loading_rule.md":          "geometry_tools_loading_rule",
    "DC_prompt_fragments/tools_config/sections_tool_block_full.md":             "sections_tool_block_full",
    "DC_prompt_fragments/tools_config/sections_tool_block_overlay.md":          "sections_tool_block_overlay",
    "DC_prompt_fragments/tools_config/precision_match_subject.md":              "precision_match_subject",
    "DC_prompt_fragments/tools_config/precision_gap_description.md":            "precision_gap_description",
    "DC_prompt_fragments/tools_config/precision_match_targets.md":              "precision_match_targets",
    "DC_prompt_fragments/tools_config/values_only_excluded_outputs.md":         "values_only_excluded_outputs",
    "DC_prompt_fragments/tools_config/precision_continue_directive_example.md": "precision_continue_directive_example",
    "DC_prompt_fragments/tools_config/render_type_choice.md":                   "render_type_choice",
    "DC_prompt_fragments/tools_config/geometry_editing_ban.md":                 "geometry_editing_ban",
    "DC_prompt_fragments/tools_config/mesh_editing_operations_actions.md":      "mesh_editing_operations_actions",
    "DC_prompt_fragments/tools_config/recommendation_exclusions.md":            "recommendation_exclusions",
    "DC_prompt_fragments/dc_config/past_run_lookup_examples.md":                "past_run_lookup_examples",
    "DC_prompt_fragments/dc_config/extraction_only_examples_user.md":           "extraction_only_examples_user",
    "DC_prompt_fragments/dc_config/extraction_only_examples.md":                "extraction_only_examples",
    "DC_prompt_fragments/tools_config/observable_fact_questions.md":            "observable_fact_questions",
    "DC_prompt_fragments/tools_config/tool_run_history_contents.md":            "tool_run_history_contents",
    "DC_prompt_fragments/dc_config/non_consumable_input_examples.md":           "non_consumable_input_examples",
    "DC_prompt_fragments/dc_config/quantitative_input_example.md":              "quantitative_input_example",
    "DC_prompt_fragments/dc_config/countable_feature_example.md":               "countable_feature_example",
    "DC_prompt_fragments/dc_config/stated_count_example.md":                    "stated_count_example",
    "DC_prompt_fragments/dc_config/soft_target_example.md":                     "soft_target_example",
    "DC_prompt_fragments/dc_config/soft_target_marker_example.md":              "soft_target_marker_example",
    "DC_prompt_fragments/dc_config/useful_input_images_example.md":             "useful_input_images_example",
    "DC_prompt_fragments/dc_config/lever_map.md":                               "lever_map",
    "DC_prompt_fragments/dc_config/parameter_level_entry_example.md":           "parameter_level_entry_example",
    "DC_prompt_fragments/dc_config/non_applicable_input_examples.md":           "non_applicable_input_examples",
    "DC_prompt_fragments/tools_config/visual_claim_examples.md":                "visual_claim_examples",
    "DC_prompt_fragments/dc_config/shape_gap_example.md":                       "shape_gap_example",
    "DC_prompt_fragments/dc_config/unlocked_lever_examples.md":                 "unlocked_lever_examples",
    "DC_prompt_fragments/dc_config/sub_resolution_examples.md":                 "sub_resolution_examples",
    "DC_prompt_fragments/dc_config/prior_finding_citation_example.md":          "prior_finding_citation_example",
    "DC_prompt_fragments/dc_config/feature_feedback_examples.md":               "feature_feedback_examples",
    "DC_prompt_fragments/dc_config/relative_magnitude_examples.md":             "relative_magnitude_examples",
    "DC_prompt_fragments/dc_config/ratio_vs_absolute_feedback.md":              "ratio_vs_absolute_feedback",
    "DC_prompt_fragments/tools_config/dh_artefact_reference_examples.md":       "dh_artefact_reference_examples",
    "DC_prompt_fragments/dc_config/dh_parameter_dump_example.md":               "dh_parameter_dump_example",
    "DC_prompt_fragments/dc_config/dh_concrete_noun_examples.md":               "dh_concrete_noun_examples",
    "DC_prompt_fragments/dc_config/dh_parameter_name_example.md":               "dh_parameter_name_example",
    "DC_prompt_fragments/dc_config/dh_numeric_fact_example.md":                 "dh_numeric_fact_example",
    "DC_prompt_fragments/dc_config/dh_structural_marker_examples.md":           "dh_structural_marker_examples",
    "DC_prompt_fragments/tools_config/output_images_label.md":                  "output_images_label",
    "DC_prompt_fragments/tools_config/output_model_label.md":                   "output_model_label",
    "DC_prompt_fragments/tools_config/output_images_long.md":                   "output_images_long",
    "DC_prompt_fragments/tools_config/output_image_files.md":                   "output_image_files",
    "DC_prompt_fragments/tools_config/output_reactions.md":                     "output_reactions",
    "DC_prompt_fragments/tools_config/output_reaction.md":                      "output_reaction",
    "DC_prompt_fragments/tools_config/output_action_noun.md":                   "output_action_noun",
    "DC_prompt_fragments/tools_config/output_produced.md":                      "output_produced",
    "DC_prompt_fragments/tools_config/output_image_caps.md":                    "output_image_caps",
    "DC_prompt_fragments/tools_config/output_action.md":                        "output_action",
    "DC_prompt_fragments/tools_config/output_images.md":                        "output_images",
    "DC_prompt_fragments/tools_config/output_image.md":                         "output_image",
    "DC_prompt_fragments/tools_config/output_model.md":                         "output_model",
    # Generic fragments
    "agents/shared/prompt_fragments/generic_constraints.md":  "hard_constraints_generic",
    "agents/shared/prompt_fragments/value_states.md":         "value_states",
    "agents/shared/prompt_fragments/routing_receptionist.md": "routing_receptionist",
    # $routing_hub has one source file PER TOPOLOGY; only the active
    # topology's is ever read.  Same many-to-one shape as $pipeline_flow.
    # (The other 5-agent override paths are not in this index yet — that is
    # part of the System-Prompts-UI surface step.)
    "agents/shared/prompt_fragments/routing_orchestrator.md": "routing_hub",
    "agents/5agent/prompt_fragments/routing_planner_5agents.md": "routing_hub",
    "agents/shared/prompt_fragments/available_agents.md":     "available_agents",
    # $pipeline_flow has TWO source files; only the file matching the
    # current PLANNER_FIRST flag is read by _build_slots.  Both are
    # listed so this map stays complete whichever way the flag is set --
    # a reader (or a tool) walking it must find both contributors, not
    # just the one the current flag happens to select.
    "agents/shared/prompt_fragments/pipeline_flow_planner_first.md": "pipeline_flow",
    "agents/shared/prompt_fragments/pipeline_flow_uii_first.md":     "pipeline_flow",
}


# ---------------------------------------------------------------------------
# Per-agent SCOPED COPIES of shared fragments
#
# Same file-naming idiom as the ``$blade_sections_visualizer_per_agent`` /
# ``$database_search_per_agent`` overlays: a file whose basename carries the
# agent's directory name wins over the shared one.  ONE difference, and it is
# the whole point — an overlay falls back to "" under its own ``_per_agent``
# slot; a SCOPED COPY replaces the value of the SHARED slot and falls back to
# the SHARED FILE.
#
# Consequence: no prompt.md changes anywhere.  An agent with no scoped file
# assembles byte-for-byte what it assembles today; an agent with one gets its
# own text under the same $slot name its prompt already references.  There is
# no "registered but not referenced" or "referenced but not registered" state
# to get wrong, because no new slot name is introduced.
#
# NOTE this can TAILOR but not REMOVE: every prompt.md puts a heading directly
# above the slot (``## Hard constraints — DC-specific``), so an empty scoped
# file leaves a bare heading.  Dropping a fragment from an agent entirely means
# deleting the ``$slot`` line AND its heading from that agent's prompt.md.
#
# Keys are $-slot names.  Values are (root, path-relative-to-that-root), where
# "dc" means DC_prompt_fragments/ and "generic" means
# agents/shared/prompt_fragments/ — the two roots ``_read_dc_fragment`` and
# ``_read_generic_fragment`` already use.  Registering a slot costs one
# ``is_file()`` check per agent per template build and nothing else, so this
# table is deliberately a SUPERSET of what has a scoped copy today.
# ---------------------------------------------------------------------------

SCOPED_FRAGMENTS: dict[str, tuple[str, str]] = {
    "hard_constraints_generic": ("generic", "generic_constraints.md"),
    "available_agents":         ("generic", "available_agents.md"),
    "hard_constraints_dc":      ("dc", "dc_config/hard_constraints_dc.md"),
    "hard_constraints_tools":   ("dc", "tools_config/hard_constraints_tools.md"),
    "sketch_handling":          ("dc", "dc_config/user_input_types/sketch_handling.md"),
    "sketch_notes":             ("dc", "dc_config/user_input_types/sketch_notes.md"),
    "parameter_list":           ("dc", "dc_config/parameters.md"),
    # ``pipeline_flow`` is registered under the flag-free name even though
    # the shared file is ``pipeline_flow_uii_first.md`` /
    # ``pipeline_flow_planner_first.md`` — the registered name is only used
    # to BUILD the scoped filename (``pipeline_flow_orchestrator.md``),
    # never to read the shared file, so it cannot collide with the
    # flag-suffixed shared pair.
    "pipeline_flow":            ("generic", "pipeline_flow.md"),
    "value_states":             ("generic", "value_states.md"),
    "dc_structure":             ("dc", "dc_config/structure.md"),
    # Round 2 of the prompt reduction (extra_utilities/extra_info.md §7.1).
    "modelling_notes":          ("dc", "dc_config/modelling_notes.md"),
    "qualitative_examples":     ("dc", "dc_config/qualitative_examples.md"),
    "tool_inventory":           ("dc", "tools_config/tool_inventory.md"),
    # Round 3 of the prompt reduction -- the DC Output
    # Inspector cuts 9 spans from the visual-inspection guide; the
    # 5-agent DCOI reads the shared file and must not move.
    "visual_inspection_guide":  ("dc", "dc_config/visual_inspection_guide.md"),
    # Do NOT register ``blade_sections_visualizer``: its scoped name for the
    # Planner would collide with the existing per-agent OVERLAY file
    # ``blade_sections_visualizer_planner.md``, which feeds the different
    # ``$blade_sections_visualizer_per_agent`` slot.
}


def scoped_fragment_path(slot: str, agent_dir_name: str) -> Path | None:
    """Path of *agent_dir_name*'s own copy of *slot*, or None if it has none.

    Honours the active topology + variant exactly as ``_read_dc_fragment`` and
    ``_read_generic_fragment`` do, so the 7-agent reduced variant can ship
    ``agents/7agent_reduced/dc_config/hard_constraints_dc_<agent>_7agents_reduced.md``
    and a 5-agent Creator could ship its own twin.

    Public because ``extra_utilities/tests/smoke_test_topology_fragments.py``
    resolves the same question; a second copy of this naming rule there is
    exactly the drift 13e0bab had to consolidate away.  (It was also read by
    the System Prompts UI's "used by" badge, removed 2026-08-21 -- the smoke
    test is now the only caller.)
    """
    try:
        root, rel = SCOPED_FRAGMENTS[slot]
    except KeyError:
        return None
    p = Path(rel)
    # as_posix(), never str(): _topology_override re-parses this string, and a
    # Windows backslash would not survive the Linux container.
    scoped_rel = (p.parent / f"{p.stem}_{agent_dir_name}{p.suffix}").as_posix()
    if root == "generic":
        path = (
            _topology_override(f"prompt_fragments/{scoped_rel}")
            or GENERIC_FRAGMENTS_DIR / scoped_rel
        )
    else:
        path = _topology_override(scoped_rel) or DC_FRAGMENTS_DIR / scoped_rel
    return path if path.is_file() else None


def _scoped_fragments_for(agent_dir_name: str) -> dict[str, str]:
    """Slot → text, for every shared fragment this agent has its own copy of.

    Only slots with an existing scoped file are returned, so the caller can
    splat the result over the shared slot map and leave the rest alone.
    """
    out: dict[str, str] = {}
    for slot in SCOPED_FRAGMENTS:
        path = scoped_fragment_path(slot, agent_dir_name)
        if path is not None:
            out[slot] = path.read_text(encoding="utf-8").rstrip()
    return out


# Per-agent allow-list of runtime ``{slot}`` names that may appear
# inside ``agents/<agent>/prompt.md``.  MUST mirror the kwargs passed
# to ``_build_template(<agent>).format(...)`` in each agent's
# ``__init__``.
#
# ⚠ NOTHING ENFORCES THIS ANY MORE.  It was checked by the System Prompts
# UI's validator (rule "c"), which flagged any ``{x}`` in a prompt.md whose
# ``x`` is not allowed for that agent.  That UI was removed 2026-08-21, so
# the check is gone while the failure mode is not: an unlisted ``{x}`` makes
# ``str.format`` raise KeyError at agent construction, i.e. at RUNTIME.
#
# So the discipline matters MORE than it did, not less: if you add a new
# format kwarg in an agent's ``__init__``, ADD the same name to this set in
# the same commit.
PROMPT_MD_RUNTIME_SLOTS: dict[str, frozenset[str]] = {
    "orchestrator":         frozenset({"chain_access_block"}),
    "planner":              frozenset({
        "routing_instructions", "user_inputs_dir",
        "input_images_subdir", "extraction_output_file",
    }),
    "user_input_inspector": frozenset({"routing_instructions"}),
    "dc_input_creator":     frozenset({"routing_instructions"}),
    "dc_input_inspector":   frozenset({"routing_instructions"}),
    # Topology 5 needs no extra rows: its hub is the PLANNER, running the
    # Planner's prompt with the Planner's four slots (already above), and
    # every other agent it builds is a 7-agent agent under its own key.
    # 3-agent topology.  Each merged agent takes the UNION of its two
    # parents' slots: the Design Engineer gets the DC Input Creator's
    # routing slot plus the Tool Caller's render-backend block, and the
    # Requirements Analyst gets the UII's routing slot plus the DC Output
    # Inspector's two runtime blocks.  The hub is the Planner and uses
    # ``$routing_hub``, so it needs no row.
    "design_engineer":      frozenset({
        "routing_instructions", "render_check_library_block",
    }),
    "requirements_analyst": frozenset({
        "routing_instructions", "image_persistence_block",
        "comparison_mode_block",
    }),
    "tool_caller":          frozenset({
        "routing_instructions", "render_check_library_block",
    }),
    "dc_output_inspector":  frozenset({
        "routing_instructions", "image_persistence_block", "comparison_mode_block",
    }),
    "database_handler":     frozenset(),
}


# ---------------------------------------------------------------------------
# Slot-map builder
#
# Hoisted from the former module-level ``_SLOTS`` dict so the System
# Prompts UI's save endpoint can take effect on the NEXT session's
# agent construction without a Python restart.  Every call re-reads
# the ~30 fragment files from disk; cost is negligible relative to a
# single LLM round-trip.
#
# The few module-level constants above (DC_NAME, PARAMETER_NAMES) are
# data captured at import time; ``_build_template`` does not use them.
#
# Per-agent overlays (``database_search_<agent_dir>.md``) are NOT in
# this dict — they are merged in by :func:`_build_template` because
# the choice of overlay depends on which agent is being assembled.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Inline phrase slots
#
# A DC- or tool-specific PHRASE (a tool name, an example list, ...) kept
# in its own one-line fragment and spliced INSIDE a sentence of a generic
# fragment or an agent body.  Splicing one can make its line much longer
# than the text around it, so after assembly every line that one of
# these lengthened past _INLINE_WRAP_WIDTH is re-wrapped at word
# boundaries.  Lines without one are never touched.
#
# A new phrase slot is listed here as well as in _build_slots.  The output
# vocabulary ($output_images = "renders", ...) is NOT: a vocabulary slot puts
# the author's own word back in its own place, so it never makes a line
# longer than the author wrote it.
# ---------------------------------------------------------------------------

INLINE_FRAGMENT_SLOTS: frozenset[str] = frozenset({
    "geometry_tool_name",
    "quality_check_numbers",
    "quality_check_report",
    "qc_numerics_verdict_rule",
    "no_render_fallback_qc",
    "geometry_model_filename",
    "render_view_list",
    "roster_sections_tool_sentence",
    "roster_tools_clause",
    "routing_sections_alternative",
    "sections_rerun_case",
    "directive_output_choice",
    "precision_multi_phase_rule",
    "geometry_tools_loading_rule",
    "precision_match_subject",
    "precision_gap_description",
    "precision_match_targets",
    "values_only_excluded_outputs",
    "geometry_editing_ban",
    "mesh_editing_operations_actions",
    "recommendation_exclusions",
    "past_run_lookup_examples",
    "extraction_only_examples_user",
    "extraction_only_examples",
    "observable_fact_questions",
    "tool_run_history_contents",
    "non_consumable_input_examples",
    "countable_feature_example",
    "stated_count_example",
    "soft_target_example",
    "soft_target_marker_example",
    "parameter_level_entry_example",
    "non_applicable_input_examples",
    "visual_claim_examples",
    "shape_gap_example",
    "unlocked_lever_examples",
    "sub_resolution_examples",
    "prior_finding_citation_example",
    "feature_feedback_examples",
    "relative_magnitude_examples",
    "dh_artefact_reference_examples",
    "dh_parameter_dump_example",
    "dh_concrete_noun_examples",
    "dh_parameter_name_example",
    "dh_numeric_fact_example",
    "dh_structural_marker_examples",
})
_INLINE_WRAP_WIDTH = 80
# Invisible delimiters around an inline slot's text, so the lines it lands
# on can be found after the substitution passes and the flag filters.
_INLINE_OPEN, _INLINE_CLOSE = "\x02", "\x03"
_LIST_MARKER_RE = re.compile(r"(?:[-*]|\d+\.) ")


def mark_inline_slots(slots: dict[str, str]) -> dict[str, str]:
    """Delimit the text of every inline phrase slot (see above)."""
    return {
        k: (_INLINE_OPEN + v + _INLINE_CLOSE
            if k in INLINE_FRAGMENT_SLOTS and v else v)
        for k, v in slots.items()
    }


def wrap_inline_lines(text: str) -> str:
    """Remove the delimiters and re-wrap each delimited line that is now
    longer than ``_INLINE_WRAP_WIDTH``.

    The line keeps its indentation; the continuation lines of a list item
    (``- ``, ``* ``, ``3. ``) are indented past its marker.  Words and
    hyphenated words are never split.
    """
    out = []
    for line in text.split("\n"):
        if _INLINE_OPEN not in line:
            out.append(line)
            continue
        plain = line.replace(_INLINE_OPEN, "").replace(_INLINE_CLOSE, "")
        if len(plain) <= _INLINE_WRAP_WIDTH:
            out.append(plain)
            continue
        body = plain.lstrip(" ")
        indent = plain[: len(plain) - len(body)]
        marker = _LIST_MARKER_RE.match(body)
        hang = indent + " " * (marker.end() if marker else 0)
        out.append(textwrap.fill(
            body, width=_INLINE_WRAP_WIDTH, initial_indent=indent,
            subsequent_indent=hang, break_long_words=False,
            break_on_hyphens=False,
        ))
    return "\n".join(out)


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
        "sketch_precision_examples": _read_dc_fragment(
            "dc_config/user_input_types/sketch_precision_examples.md"),
        "sketch_crop_example": _read_dc_fragment(
            "dc_config/user_input_types/sketch_crop_example.md"),
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
        # Blade-sections visualizer — shared brief awareness (all agents) +
        # the minimal "OFF" note; gated by <<BSV_ON>>/<<BSV_OFF>> regions.  The
        # per-agent overlay ($blade_sections_visualizer_per_agent) is loaded in
        # _build_template, like $database_search_per_agent.
        "blade_sections_visualizer": _read_dc_fragment("tools_config/blade_sections_visualizer.md"),
        "blade_sections_visualizer_off": _read_dc_fragment("tools_config/blade_sections_visualizer_off.md"),
        # Relocated DC- / tool-specific text (generic-fragments audit,
        # 2026-10): phrases and blocks that were inline in a generic
        # fragment or an agent body.  Described in the dc_config /
        # tools_config READMEs.
        "geometry_tool_name": _read_dc_fragment("tools_config/geometry_tool_name.md"),
        "quality_check_numbers": _read_dc_fragment("tools_config/quality_check_numbers.md"),
        "quality_check_report": _read_dc_fragment("tools_config/quality_check_report.md"),
        "mesh_check_role_item": _read_dc_fragment("tools_config/mesh_check_role_item.md"),
        "qc_numerics_verdict_rule": _read_dc_fragment("tools_config/qc_numerics_verdict_rule.md"),
        "no_render_fallback_qc": _read_dc_fragment("tools_config/no_render_fallback_qc.md"),
        "geometry_model_filename": _read_dc_fragment("tools_config/geometry_model_filename.md"),
        "render_view_list": _read_dc_fragment("tools_config/render_view_list.md"),
        "roster_sections_tool_sentence": _read_dc_fragment("tools_config/roster_sections_tool_sentence.md"),
        "roster_tools_clause": _read_dc_fragment("tools_config/roster_tools_clause.md"),
        "routing_sections_alternative": _read_dc_fragment("tools_config/routing_sections_alternative.md"),
        "sections_rerun_case": _read_dc_fragment("tools_config/sections_rerun_case.md"),
        "directive_output_choice": _read_dc_fragment("tools_config/directive_output_choice.md"),
        "precision_multi_phase_rule": _read_dc_fragment("tools_config/precision_multi_phase_rule.md"),
        "geometry_tools_loading_rule": _read_dc_fragment("tools_config/geometry_tools_loading_rule.md"),
        "sections_tool_block_full": _read_dc_fragment("tools_config/sections_tool_block_full.md"),
        "sections_tool_block_overlay": _read_dc_fragment("tools_config/sections_tool_block_overlay.md"),
        "precision_match_subject": _read_dc_fragment("tools_config/precision_match_subject.md"),
        "precision_gap_description": _read_dc_fragment("tools_config/precision_gap_description.md"),
        "precision_match_targets": _read_dc_fragment("tools_config/precision_match_targets.md"),
        "values_only_excluded_outputs": _read_dc_fragment("tools_config/values_only_excluded_outputs.md"),
        "precision_continue_directive_example": _read_dc_fragment("tools_config/precision_continue_directive_example.md"),
        "render_type_choice": _read_dc_fragment("tools_config/render_type_choice.md"),
        "geometry_editing_ban": _read_dc_fragment("tools_config/geometry_editing_ban.md"),
        "mesh_editing_operations_actions": _read_dc_fragment("tools_config/mesh_editing_operations_actions.md"),
        "recommendation_exclusions": _read_dc_fragment("tools_config/recommendation_exclusions.md"),
        "past_run_lookup_examples": _read_dc_fragment("dc_config/past_run_lookup_examples.md"),
        "extraction_only_examples_user": _read_dc_fragment("dc_config/extraction_only_examples_user.md"),
        "extraction_only_examples": _read_dc_fragment("dc_config/extraction_only_examples.md"),
        "observable_fact_questions": _read_dc_fragment("tools_config/observable_fact_questions.md"),
        "tool_run_history_contents": _read_dc_fragment("tools_config/tool_run_history_contents.md"),
        "non_consumable_input_examples": _read_dc_fragment("dc_config/non_consumable_input_examples.md"),
        "quantitative_input_example": _read_dc_fragment("dc_config/quantitative_input_example.md"),
        "countable_feature_example": _read_dc_fragment("dc_config/countable_feature_example.md"),
        "stated_count_example": _read_dc_fragment("dc_config/stated_count_example.md"),
        "soft_target_example": _read_dc_fragment("dc_config/soft_target_example.md"),
        "soft_target_marker_example": _read_dc_fragment("dc_config/soft_target_marker_example.md"),
        "useful_input_images_example": _read_dc_fragment("dc_config/useful_input_images_example.md"),
        "lever_map": _read_dc_fragment("dc_config/lever_map.md"),
        "parameter_level_entry_example": _read_dc_fragment("dc_config/parameter_level_entry_example.md"),
        "non_applicable_input_examples": _read_dc_fragment("dc_config/non_applicable_input_examples.md"),
        "visual_claim_examples": _read_dc_fragment("tools_config/visual_claim_examples.md"),
        "shape_gap_example": _read_dc_fragment("dc_config/shape_gap_example.md"),
        "unlocked_lever_examples": _read_dc_fragment("dc_config/unlocked_lever_examples.md"),
        "sub_resolution_examples": _read_dc_fragment("dc_config/sub_resolution_examples.md"),
        "prior_finding_citation_example": _read_dc_fragment("dc_config/prior_finding_citation_example.md"),
        "feature_feedback_examples": _read_dc_fragment("dc_config/feature_feedback_examples.md"),
        "relative_magnitude_examples": _read_dc_fragment("dc_config/relative_magnitude_examples.md"),
        "ratio_vs_absolute_feedback": _read_dc_fragment("dc_config/ratio_vs_absolute_feedback.md"),
        "dh_artefact_reference_examples": _read_dc_fragment("tools_config/dh_artefact_reference_examples.md"),
        "dh_parameter_dump_example": _read_dc_fragment("dc_config/dh_parameter_dump_example.md"),
        "dh_concrete_noun_examples": _read_dc_fragment("dc_config/dh_concrete_noun_examples.md"),
        "dh_parameter_name_example": _read_dc_fragment("dc_config/dh_parameter_name_example.md"),
        "dh_numeric_fact_example": _read_dc_fragment("dc_config/dh_numeric_fact_example.md"),
        "dh_structural_marker_examples": _read_dc_fragment("dc_config/dh_structural_marker_examples.md"),
        "output_images_label": _read_dc_fragment("tools_config/output_images_label.md"),
        "output_model_label": _read_dc_fragment("tools_config/output_model_label.md"),
        "output_images_long": _read_dc_fragment("tools_config/output_images_long.md"),
        "output_image_files": _read_dc_fragment("tools_config/output_image_files.md"),
        "output_reactions": _read_dc_fragment("tools_config/output_reactions.md"),
        "output_reaction": _read_dc_fragment("tools_config/output_reaction.md"),
        "output_action_noun": _read_dc_fragment("tools_config/output_action_noun.md"),
        "output_produced": _read_dc_fragment("tools_config/output_produced.md"),
        "output_image_caps": _read_dc_fragment("tools_config/output_image_caps.md"),
        "output_action": _read_dc_fragment("tools_config/output_action.md"),
        "output_images": _read_dc_fragment("tools_config/output_images.md"),
        "output_image": _read_dc_fragment("tools_config/output_image.md"),
        "output_model": _read_dc_fragment("tools_config/output_model.md"),
        # Generic
        "hard_constraints_generic": _read_generic_fragment("generic_constraints.md"),
        "value_states": _read_generic_fragment("value_states.md"),
        # Per-agent routing fragments (Receptionist + the topology's hub;
        # the chain agents load theirs via routing_instructions()).
        #
        # The hub's fragment is named per topology — routing_orchestrator.md
        # in the 7-agent system, routing_planner_5agents.md in the 5-agent
        # one, whose hub IS the Planner —
        # but BOTH hub prompts reference the single topology-neutral slot
        # $routing_hub.  Only the active topology's file is ever asked for,
        # so there is no "might be missing" case to tolerate: a genuine typo
        # still raises FileNotFoundError, loudly, as it should.
        "routing_receptionist": _read_generic_fragment("routing_receptionist.md"),
        "routing_hub": _read_generic_fragment(f"routing_{_hub_agent()}.md"),
        # Cross-agent organisational fragments (Planner + Orchestrator)
        "pipeline_flow": _read_generic_fragment(_pipeline_flow_fragment_name()),
        "available_agents": _read_generic_fragment("available_agents.md"),
        # Embedding (DH only) — settings.py values, captured at import time
        "embedding_provider": EMBEDDING_PROVIDER,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_vector_dims": EMBEDDING_VECTOR_DIMS,
        "embedding_max_response_tokens": EMBEDDING_MAX_RESPONSE_TOKENS,
    }


def _prompt_path(agent_dir_name: str) -> Path:
    """Locate an agent's prompt, honouring the active topology.  First hit:

    1. ``agents/<N>agent/<agent>/prompt_<N>agents.md`` — this topology's
       tailored copy of an agent that ALSO exists in the 7-agent system
       (Receptionist, UII, Tool Caller, DCOI).
    2. ``agents/<agent>/prompt_<N>agents.md`` — an agent existing ONLY in
       this topology (Conductor, Creator).  It has no 7-agent original to
       shadow, so it lives in a normal agent package rather than under the
       topology directory.
    3. ``agents/<agent>/prompt.md`` — the historic path.  Under topology 7
       candidates 1 and 2 always miss, so this is always the answer.
    """
    override = _topology_override(f"{agent_dir_name}/prompt.md")
    if override is not None:
        return override
    # An agent that exists ONLY in this topology keeps a normal package, so
    # its prompt sits beside its code.
    here = AGENTS_DIR / agent_dir_name
    own = here / f"prompt_{_topology()}agents.md"
    return own if own.is_file() else here / "prompt.md"


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
    :func:`_build_slots`) so live edits to .md fragments on disk take
    effect on the next session's agent construction without a Python
    restart.
    """
    raw = _prompt_path(agent_dir_name).read_text(encoding="utf-8")
    # Per-agent overlay onto the global slot map: load this agent's
    # ``database_search_<agent_dir_name>.md`` fragment if present and
    # expose it as ``$database_search_per_agent``.  Agents without a
    # matching fragment (currently just the Database Handler, which is
    # write-only post-session and has no <<HAS_DBA>> block in its
    # prompt) get an empty string — harmless because their prompt.md
    # does not reference the slot.
    per_agent_dbs_rel = f"tools_config/database_search_{agent_dir_name}.md"
    per_agent_dbs_file = (
        _topology_override(per_agent_dbs_rel)
        or TOOLS_CONFIG_DIR / f"database_search_{agent_dir_name}.md"
    )
    per_agent_dbs = (
        per_agent_dbs_file.read_text(encoding="utf-8").rstrip()
        if per_agent_dbs_file.exists()
        else ""
    )
    # Per-agent Blade-sections-visualizer overlay (Tool Caller = full tool
    # usage, DC Output Inspector = read-by-path; others have no file → empty,
    # so only the shared brief awareness shows).  Same idiom as the DBa overlay.
    per_agent_bsv_rel = (
        f"tools_config/blade_sections_visualizer_{agent_dir_name}.md"
    )
    per_agent_bsv_file = (
        _topology_override(per_agent_bsv_rel)
        or TOOLS_CONFIG_DIR / f"blade_sections_visualizer_{agent_dir_name}.md"
    )
    per_agent_bsv = (
        per_agent_bsv_file.read_text(encoding="utf-8").rstrip()
        if per_agent_bsv_file.exists()
        else ""
    )
    slots = {
        **_build_slots(),
        "database_search_per_agent": per_agent_dbs,
        "blade_sections_visualizer_per_agent": per_agent_bsv,
        # LAST, so a per-agent scoped copy wins over the shared fragment.
        **_scoped_fragments_for(agent_dir_name),
    }
    # A database tool this agent does NOT hold must not be described to it.
    # ``<<HAS_DBA>>`` is all-or-nothing (it asks "holds ANY database tool"),
    # so the per-TOOL decision lands here: each slot blanks itself when its
    # tool is off for this (profile, agent).  No prompt file has to change,
    # because the slots dict is already built per agent.
    #
    # Local import for the same reason ``apply_dba_filter`` uses one: it
    # makes the settings dependency obvious in the import statements.
    from workflow_settings import database_access as _dba
    for _slot, _tools in _DBA_TOOL_SLOTS:
        if not any(_dba.is_enabled_for(agent_dir_name, t) for t in _tools):
            slots[_slot] = ""
    slots = mark_inline_slots(slots)
    once = Template(raw).safe_substitute(slots)
    twice = Template(once).safe_substitute(slots)
    filtered = apply_flag_filters(twice)
    # apply_dba_filter and apply_chain_only_filter are per-agent — they
    # consult, respectively, the per-agent DBa flag in database_access.json
    # (+ the RAG_ENABLED master switch) and the user-facing-vs-chain agent
    # classification — so they run separately from the global
    # apply_flag_filters chain.
    filtered = apply_dba_filter(filtered, agent_dir_name)
    filtered = apply_image_tools_filter(filtered, agent_dir_name)
    return wrap_inline_lines(
        apply_chain_only_filter(filtered, agent_dir_name))


# Re-export routing helpers so agents can do ``from agents.shared.prompts
# import natural_pipeline, routing_instructions`` for one-stop access.
__all__ = [
    "natural_pipeline",
    "routing_instructions",
    "DC_NAME",
    "PARAMETER_NAMES",
    "PARAMETER_TYPES",
    "RENDER_CHECK_LIBRARY_TRIMESH",
    "RENDER_CHECK_LIBRARY_PYVISTA",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "EMBEDDING_VECTOR_DIMS",
    "EMBEDDING_MAX_RESPONSE_TOKENS",
    "FRAGMENT_TO_SLOT",
    "PROMPT_MD_RUNTIME_SLOTS",
]
