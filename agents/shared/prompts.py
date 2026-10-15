"""Prompt assembly.

Each agent's per-agent template lives at ``agents/<agent>/prompt.md``.

DC-specific and tool-specific fragments (parameter list, structure,
modelling notes, capabilities, tool inventory, …) live in the design-
configurator pack, ``dc_pack/fragments/`` (``dc/`` and ``tools/``), read
through ``engine/pack.py``.  Every ``$slot`` -- pack, engine or setting --
is listed in ``engine/slot_registry.yaml``; ``_build_slots``,
``INLINE_FRAGMENT_SLOTS``, ``SCOPED_FRAGMENTS`` and ``FRAGMENT_TO_SLOT``
are all derived from it.

The engine's own fragments (the DOs / DON'Ts every agent inherits, the
routing text, the pipeline flow) live in ``agents/shared/prompt_fragments/``.

Two placeholder syntaxes are used and they do NOT collide:

- ``$slot`` (Python ``string.Template``) — pack + engine fragments,
  filled when each agent is built by ``_build_template()``.
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
from engine import pack as _pack
from engine import pack_flags as _pack_flags
from engine import pack_tools as _pack_tools
from engine import parameter_access as _parameter_access
from engine import parameters as _parameters
from workflow_settings import settings as _workflow_settings

AGENTS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = AGENTS_DIR.parent
GENERIC_FRAGMENTS_DIR = Path(__file__).resolve().parent / "prompt_fragments"


# ---------------------------------------------------------------------------
# Agent topology
#
# A topology owns ``agents/<N>agent/``, holding its copies of the ENGINE's
# files (the pack's per-topology texts are ``<slot>.t<N>.md`` files in
# ``dc_pack/``, see ``engine/pack.py``).  Each is named with an
# ``_<N>agents`` suffix and filed under a sub-folder mirroring its SOURCE
# root:
#
#   agents/5agent/prompt_fragments/generic_constraints_5agents.md
#        overrides  agents/shared/prompt_fragments/generic_constraints.md
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
    sub-folder (``prompt_fragments/y.md``, ``<agent>/prompt.md``); only the
    basename gains the suffix.  Returning
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
# stripped, so exactly one survives.  Same shape as an <<IF:…>> / <<IFNOT:…>> pair.
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
# ``<<IF:flag>>…<</IF:flag>>`` / ``<<IFNOT:flag>>…<</IFNOT:flag>>`` regions:
# kept when the flag is true (IF) or false (IFNOT), else removed -- and a line
# the removal leaves empty disappears with it.  Two families of flags:
#
#   * the pack's, global: ``tool:<tool>`` (the tool is enabled) and
#     ``setting:<tool>.<name>`` (a boolean tool setting), declared in
#     dc_pack/pack.yaml (engine/pack_flags.py) and resolved in
#     apply_flag_filters, so routing fragments get them too;
#   * per agent, from the parameter-access table
#     (engine/parameter_access.py): ``param_list`` -- the agent sees the list
#     in its prompt (full or names); ``param_ranges`` -- with the ranges.
#
# See apply_if_flags.
_IF_RE = re.compile(
    r"<<(IF|IFNOT):([a-z][a-z0-9_]*(?::[a-z0-9_.]+)?)>>(.*?)<</\1:\2>>",
    re.DOTALL)
# Where a region was removed, until the emptied lines are dropped.
_REMOVED = "\x04"
# A line holding nothing but removed regions, blanks and the inline-slot
# delimiters: it goes, newline included, so no empty line is left behind.
_EMPTIED_LINE_RE = re.compile(
    r"^[ \t\x02\x03]*\x04[ \t\x02\x03\x04]*(?:\n|\Z)", re.MULTILINE)
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
    """Apply the DCII and PLANNER_FIRST filters, the pack's ``<<IF:tool:…>>``
    / ``<<IF:setting:…>>`` flags, and the RAG_ON filter, in sequence.

    NOTE: per-agent filters (:func:`apply_dba_filter`,
    :func:`apply_chain_only_filter`, :func:`apply_if_flags` for the
    parameter-access regions) are applied separately in
    :func:`_build_template` because they need to know which agent's
    template is being assembled.
    """
    return apply_rag_on_filter(
        apply_if_flags(
            apply_planner_first_filter(apply_dcii_filter(text)),
            _pack_flags.values(), per_agent_later=True,
        )
    )


def apply_if_flags(text: str, flags: dict[str, bool], *,
                   per_agent_later: bool = False) -> str:
    """Resolve every ``<<IF:flag>>`` / ``<<IFNOT:flag>>`` region (see
    ``_IF_RE``), then drop each line the removals left empty.

    A flag not in *flags* is an error, so a misspelt marker fails the build
    instead of reaching a model -- except a ``tool:`` / ``setting:`` flag
    naming a tool that is not in the pack (removed), which reads as switched
    off.  With *per_agent_later* (the global pass in
    :func:`apply_flag_filters`), a region whose flag has no ``tool:`` /
    ``setting:`` prefix is left for the per-agent pass in
    :func:`_build_template`.
    """
    def keep(m: re.Match) -> str:
        kind, name, body = m.groups()
        if name not in flags:
            if per_agent_later and ":" not in name:
                return m.group(0)
            if _pack_flags.absent(name):
                return body if kind == "IFNOT" else _REMOVED
            raise ValueError(f"unknown prompt flag <<{kind}:{name}>> "
                             f"(known: {', '.join(sorted(flags))})")
        return body if flags[name] == (kind == "IF") else _REMOVED

    prev = None
    while prev != text:              # nested regions resolve outside-in
        prev, text = text, _IF_RE.sub(keep, text)
    return _EMPTIED_LINE_RE.sub("", text).replace(_REMOVED, "")


def read_pack_fragment(slot: str, agent_dir_name: str | None = None) -> str:
    """The pack text of *slot* for the active topology -- *agent_dir_name*'s
    own copy when it has one.  Resolution rules: ``engine/pack.py``."""
    return _pack.read(slot, _topology(), agent_dir_name)


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
# call read_pack_fragment() / _read_generic_fragment() there instead.
# ---------------------------------------------------------------------------

DC_NAME = read_pack_fragment("dc_name")


# The design configurator's parameters, from dc_pack/parameters.json
# (engine/parameters.py): the canonical names in JSON order and their types,
# used by the runtime validator.  DATA, not prompt text, and with no topology
# dimension: the parameters do not depend on the topology, so there is
# nothing to fork, and a per-topology copy would be a second source of truth
# for one fact.
_PARAMETER_SPEC = _parameters.load()
PARAMETER_NAMES = _parameters.names(_PARAMETER_SPEC)
PARAMETER_TYPES = _parameters.types(_PARAMETER_SPEC)


# ---------------------------------------------------------------------------
# Tools-specific content
# ---------------------------------------------------------------------------

# Paired render / mesh-check backend fragments — exactly one is
# spliced into the Tool Caller's prompt per session via the runtime
# ``{render_check_library_block}`` placeholder (registry: ``use: runtime``).
# The agents read the fragment fresh at wiring time; these three
# constants are read only by the prompt snapshot and PDF tools
# (extra_utilities/scripts/topology_prompt_snapshot.py, prompt_pdf/dump.py).
RENDER_CHECK_LIBRARY_TRIMESH = read_pack_fragment("render_check_library_trimesh")
RENDER_CHECK_LIBRARY_PYVISTA = read_pack_fragment("render_check_library_pyvista")
# Substituted for the backend block when the session has mesh checks OFF —
# the metrics those fragments describe are then never produced.
RENDER_CHECK_LIBRARY_OFF = read_pack_fragment("render_check_library_off")


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
# references ``$parameter_count``, so
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

# The registry's ``source: setting`` slots, captured at import like the
# constants above (today: the four embedding settings).
_SETTING_SLOT_VALUES: dict[str, str] = {
    name: str(getattr(_workflow_settings, spec["setting"]))
    for name, spec in _pack.slots(source="setting").items()
}


# ---------------------------------------------------------------------------
# Reverse index: fragment FILE -> the $slot it feeds
#
# Derived, not hand-kept: a pack file is named after its slot
# (engine/pack.py) and an engine file is named in the registry.  Paths are
# relative to the repo root (absolute for a pack outside it).
# ---------------------------------------------------------------------------

def _repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _fragment_to_slot() -> dict[str, str]:
    out = {_repo_rel(p): _pack.slot_of_file(p.name) for p in _pack.fragment_files()}
    for name, spec in _pack.slots(source="engine").items():
        for f in ([spec["file"]] if "file" in spec else spec.get("files", [])):
            out[_repo_rel(GENERIC_FRAGMENTS_DIR / f)] = name
    return out


FRAGMENT_TO_SLOT: dict[str, str] = _fragment_to_slot()


# ---------------------------------------------------------------------------
# Per-agent SCOPED COPIES of shared fragments
#
# An agent may own a copy of a fragment.  The copy replaces the shared text
# under the SAME $slot name, so no prompt.md changes anywhere: an agent with
# no copy assembles exactly what it assembled before, an agent with one gets
# its own text under the $slot its prompt already references.
#
#   * Pack slots: ANY of them, as ``<slot>@<agent>.md`` (or ``.t<N>.md``) in
#     ``dc_pack/fragments/`` -- see engine/pack.py.
#   * Engine slots: those marked ``scoped: true`` in the registry, as
#     ``<file stem>_<agent>.md`` beside the shared file in
#     ``agents/shared/prompt_fragments/`` (or the topology's copy of it).
#     SCOPED_FRAGMENTS lists them, as (root, file) for that lookup.
#
# NOTE this can TAILOR but not REMOVE: every prompt.md puts a heading directly
# above the slot (``## Hard constraints — DC-specific``), so an empty scoped
# file leaves a bare heading.  Dropping a fragment from an agent entirely means
# deleting the ``$slot`` line AND its heading from that agent's prompt.md.
# ---------------------------------------------------------------------------

SCOPED_FRAGMENTS: dict[str, tuple[str, str]] = {
    name: ("generic", spec.get("scoped_file") or spec["file"])
    for name, spec in _pack.slots(source="engine").items()
    if spec.get("scoped")
}


def scoped_fragment_path(slot: str, agent_dir_name: str) -> Path | None:
    """Path of *agent_dir_name*'s own copy of *slot*, or None if it has none.

    Honours the active topology exactly as the shared lookup does.  Public
    because ``extra_utilities/tests/smoke_test_topology_fragments.py``
    resolves the same question; a second copy of this naming rule there is
    exactly the drift 13e0bab had to consolidate away.
    """
    if slot in SCOPED_FRAGMENTS:
        _root, rel = SCOPED_FRAGMENTS[slot]
        p = Path(rel)
        # as_posix(), never str(): _topology_override re-parses this string, and a
        # Windows backslash would not survive the Linux container.
        scoped_rel = (p.parent / f"{p.stem}_{agent_dir_name}{p.suffix}").as_posix()
        path = (
            _topology_override(f"prompt_fragments/{scoped_rel}")
            or GENERIC_FRAGMENTS_DIR / scoped_rel
        )
        return path if path.is_file() else None
    if _pack.registry().get(slot, {}).get("source") == "pack":
        return _pack.agent_copy_path(slot, _topology(), agent_dir_name)
    return None


def _scoped_fragments_for(agent_dir_name: str) -> dict[str, str]:
    """Slot → text, for every fragment this agent has its own copy of.

    Only slots with an existing copy are returned, so the caller can splat
    the result over the shared slot map and leave the rest alone.  Runtime
    fragments (``use: runtime``) are not $slots and are left out.
    """
    out: dict[str, str] = {}
    for slot in SCOPED_FRAGMENTS:
        path = scoped_fragment_path(slot, agent_dir_name)
        if path is not None:
            out[slot] = path.read_text(encoding="utf-8").rstrip()
    for slot, text in _pack.agent_copies(agent_dir_name, _topology()).items():
        if _pack.slot_spec(slot).get("use", "prompt") == "prompt":
            out[slot] = text
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
# A per-agent-only slot (``missing: empty`` in the registry --
# ``$database_search_per_agent``, ``$blade_sections_visualizer_per_agent``)
# is "" in this dict; :func:`_build_template` lays each agent's own copy
# over it, because which text applies depends on the agent being assembled.
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
# A phrase slot is one with ``kind: phrase`` in engine/slot_registry.yaml.
# The output vocabulary ($output_images = "renders", ...) is ``kind: word``,
# not phrase: a vocabulary slot puts the author's own word back in its own
# place, so it never makes a line longer than the author wrote it.
# ---------------------------------------------------------------------------

INLINE_FRAGMENT_SLOTS: frozenset[str] = frozenset(
    name for name, spec in _pack.registry().items()
    if spec.get("kind") == "phrase"
)
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


def _engine_fragment_file(spec: dict) -> str:
    """The file an engine slot reads in the active topology."""
    which = spec.get("file_from")
    if which == "hub":
        # The hub's fragment is named per topology — routing_orchestrator.md
        # in the 7-agent system, routing_planner_5agents.md in the 5-agent
        # one, whose hub IS the Planner — but BOTH hub prompts reference the
        # single topology-neutral slot $routing_hub.  Only the active
        # topology's file is ever asked for, so there is no "might be
        # missing" case to tolerate: a genuine typo still raises
        # FileNotFoundError, loudly, as it should.
        return f"routing_{_hub_agent()}.md"
    if which == "pipeline_flow":
        return _pipeline_flow_fragment_name()
    return spec["file"]


# The registry's ``source: generated`` slots: computed from the pack's data on
# every build, never written by hand.  Keyed by the entry's ``from``.
_GENERATED_SLOTS = {
    # $parameter_count: how many parameters dc_pack/parameters.json lists.
    "parameter_count": lambda: str(_parameters.count()),
}

# Generated slots that differ per agent: "" in the shared map, filled for the
# agent being assembled in _build_template.
_GENERATED_PER_AGENT = {
    # $tool_inventory: the tool runner's numbered tool list, built from each
    # tool's own entry (engine/pack_tools.tool_list).
    "tool_list": _pack_tools.tool_list,
}


def _build_slots() -> dict[str, str]:
    """Re-read every fragment from disk and assemble the $-slot map.

    One entry per registry slot: pack slots from ``dc_pack/`` for the active
    topology (a per-agent-only slot is "" here), engine slots from
    ``agents/shared/prompt_fragments/``, setting slots from the values
    captured at import, generated slots computed from the pack's data
    (``_GENERATED_SLOTS``).  Runtime fragments (``use: runtime``) are read by
    Python where they are used and are not $slots.
    """
    topo = _topology()
    slots: dict[str, str] = {}
    for name, spec in _pack.slots(use="prompt").items():
        source = spec["source"]
        if source == "pack":
            slots[name] = _pack.read(name, topo)
        elif source == "engine":
            slots[name] = _read_generic_fragment(_engine_fragment_file(spec))
        elif source == "generated":
            slots[name] = ("" if spec["from"] in _GENERATED_PER_AGENT
                           else _GENERATED_SLOTS[spec["from"]]())
        else:
            slots[name] = _SETTING_SLOT_VALUES[name]
    return slots


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
    ``$parameter_count``).  One level of
    nesting is enough for current usage; deeper nesting would require
    more passes or a fixed-point loop.

    The slot map is rebuilt fresh on every call (via
    :func:`_build_slots`) so live edits to .md fragments on disk take
    effect on the next session's agent construction without a Python
    restart.
    """
    raw = _prompt_path(agent_dir_name).read_text(encoding="utf-8")
    # The agent's own copies go LAST, so they win over the shared text.  The
    # per-agent-only slots ($database_search_per_agent,
    # $blade_sections_visualizer_per_agent) are "" in the shared map and get
    # their text here, for the agents that have a file.
    slots = {
        **_build_slots(),
        **_scoped_fragments_for(agent_dir_name),
    }
    for _name, _spec in _pack.slots(source="generated").items():
        if _spec["from"] in _GENERATED_PER_AGENT:
            slots[_name] = _GENERATED_PER_AGENT[_spec["from"]](agent_dir_name)
    # Who sees the parameter list (engine/parameter_access.py): "names"
    # removes the ranges from this agent's list; the <<IF:param_list>> /
    # <<IF:param_ranges>> regions are resolved after the substitution.
    access = _parameter_access.state(agent_dir_name, _topology())
    if access == "names":
        slots["parameter_list"] = _parameter_access.strip_ranges(
            slots["parameter_list"])
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
    filtered = apply_if_flags(
        apply_flag_filters(twice),
        {**_pack_flags.values(), **_parameter_access.prompt_flags(access)})
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
    "read_pack_fragment",
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
