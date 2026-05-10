"""Session and AgentState — the v3 plain-data carriers.

These are the units that flow through the v3 storage layer.  The
``Session`` holds everything about one user's conversation (config
flags, server-local paths, the chain log of inter-agent exchanges,
and one ``AgentState`` per agent).  ``AgentState`` holds the data
that defines a single agent's current state — chiefly the message
list, the pending routing hop, and the buffered image blocks.

Why "plain data"?  In v3 the live agent objects are reconstructed
on every Streamlit turn from this state plus the LLM client cache
(``agents/shared/llm_client_cache.py``).  Sessions can also be
serialised to JSON for an eventual Redis-backed Option-B session
store (see ``cloud_architecture_notes.md`` C4).  Both flows require
that nothing in ``Session`` or ``AgentState`` holds a live object
(LLM client, file handle, agent reference, etc.).  ``assert_plain_
data`` enforces this invariant; smoke tests invoke it on the
``to_dict`` output.

This module is purely additive in v3-Phase-1: nothing imports
``Session`` yet.  Later commits in Phase 1 introduce a
``BaseChainAgent`` that builds itself ``from_state`` and snapshots
itself back, then convert each agent in turn.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from agents.shared.routing_tools import AGENT_DISPLAY


# Defaults baked from workflow_settings/settings.py (the v4-REPL
# convention).  Streamlit / v3 callers may override any of these per
# Session by passing keyword arguments to the constructor or factory.
_DEFAULT_RAG_ENABLED                = False
_DEFAULT_DC_INSPECTOR_ENABLED       = True
_DEFAULT_MESH_CHECKS                = False
_DEFAULT_CHAIN_ACCESS               = True
_DEFAULT_KEEP_IMAGES_IN_CONTEXT     = False
_DEFAULT_DCOI_COMPARISON_MODE       = 3
_DEFAULT_PLANNER_FIRST              = False
_DEFAULT_RENDER_LIBRARY             = "trimesh"


# Every chain agent + Orchestrator + DH gets one AgentState entry
# inside Session.agent_states.  These are the legal keys (matches
# AGENT_DISPLAY in routing_tools.py plus 'database_handler').
KNOWN_AGENT_KEYS: frozenset[str] = frozenset(
    list(AGENT_DISPLAY.keys()) + ["database_handler"]
)


@dataclass
class AgentState:
    """Per-agent state in plain-data form.

    Field choices:
      messages
        The agent's LangChain message list, serialised to dicts via
        ``BaseMessage.dict()`` / restored via ``message_from_dict``
        (wired in later Phase-1 commits).  At in-memory residency
        during a turn, may temporarily hold live ``BaseMessage``
        instances; at JSON-serialisation time, callers must convert
        to the dict form.
      pending_hop
        ``AgentHop.__dict__`` (i.e. ``{'target': str, 'message': str}``)
        when the agent's run loop just emitted a hand-off, else None.
      pending_image_blocks
        Image content blocks buffered by ``append_pending_images``
        (see ``shared/file_utils.py``), waiting for the next
        ``flush_pending_image_blocks`` call to merge them into a
        trailing HumanMessage.
      pending_image_paths
        The file-path text labels that pair with each block in
        ``pending_image_blocks`` — same length, same order.
      cycle_start_ts
        Receptionist-only.  Float UNIX timestamp of when the current
        user-cycle started; used to filter "fresh this cycle"
        artefacts in ``format_outgoing``.  None for every other agent.
      current_plan
        Planner-only.  The accumulated plan text built up across
        turns.  Empty string when no plan is active or for non-Planner
        agents.
    """
    agent_key: str
    messages: list = field(default_factory=list)
    pending_hop: dict | None = None
    pending_image_blocks: list[dict] = field(default_factory=list)
    pending_image_paths: list[str] = field(default_factory=list)
    cycle_start_ts: float | None = None
    current_plan: str = ""

    def __post_init__(self) -> None:
        if self.agent_key not in KNOWN_AGENT_KEYS:
            raise ValueError(
                f"Unknown agent_key {self.agent_key!r}.  Must be one of "
                f"{sorted(KNOWN_AGENT_KEYS)}."
            )


@dataclass
class Session:
    """One user's conversation, in plain-data form.

    Field choices align with ``cloud_architecture_notes.md`` C4
    (Option A in-memory session state, serialisation-ready) and
    ``database_design_notes.md`` (sessions row schema, including
    ``dc_name``, ``schema_version``, ``dc_inspector_enabled``).

    The ``inputs_dir`` / ``attempts_dir`` / ``logs_dir`` fields are
    server-local paths set ONLY by ``Session.create_for_v3`` — when
    the v4 REPL constructs a Session via the bare constructor they
    stay None, and the v4 file-handling code keeps using the global
    paths in ``config.py``.  Two modes, no path-convention crossover.
    """
    session_id: str
    session_ts: datetime
    user_id: str | None = None

    # DC-side identity (matches sessions table columns).
    dc_name: str = "propeller"
    schema_version: int = 1

    # Session-config flags (defaults baked from workflow_settings.py
    # so v4 Sessions match v4 behaviour with no overrides needed).
    dc_inspector_enabled:   bool = _DEFAULT_DC_INSPECTOR_ENABLED
    rag_enabled:            bool = _DEFAULT_RAG_ENABLED
    mesh_checks:            bool = _DEFAULT_MESH_CHECKS
    chain_access:           bool = _DEFAULT_CHAIN_ACCESS
    keep_images_in_context: bool = _DEFAULT_KEEP_IMAGES_IN_CONTEXT
    dcoi_comparison_mode:   int  = _DEFAULT_DCOI_COMPARISON_MODE
    planner_first:          bool = _DEFAULT_PLANNER_FIRST
    render_library:         str  = _DEFAULT_RENDER_LIBRARY

    # Inter-agent exchanges accumulated across the WHOLE session
    # (per Q1 of the Phase-1 design pass — ChainLog is session-scoped,
    # not per-turn).  Each exchange is a plain dict with keys
    # ``from_agent``, ``to_agent``, ``message``, ``ts`` (ISO-8601 with
    # TZ).  Populated by the routing tools (commit 5).
    chain_log_exchanges: list[dict] = field(default_factory=list)

    # Per-agent state, one entry per agent_key in KNOWN_AGENT_KEYS.
    # Empty dict at construction; populated as agents are
    # rebuilt-and-snapshot per turn (commits 3-6).
    agent_states: dict[str, AgentState] = field(default_factory=dict)

    # Server-local per-session paths; None in v4-REPL mode.
    inputs_dir:   Path | None = None
    attempts_dir: Path | None = None
    logs_dir:     Path | None = None

    @classmethod
    def create_for_v3(
        cls,
        session_id: str,
        base_inputs_dir: Path,
        base_attempts_dir: Path,
        base_logs_dir: Path,
        *,
        session_ts: datetime | None = None,
        user_id: str | None = None,
        **overrides,
    ) -> "Session":
        """Build a Session with v3-style namespaced paths.

        Used by the Streamlit dispatcher to give each user's session
        its own ``inputs/<session_id>/`` etc., so concurrent users do
        not collide on the same server-local files.  v4 REPL does NOT
        call this — it constructs a plain Session whose path fields
        stay None, and the existing v4 file-handling code keeps using
        the global ``config.INPUTS_DIR`` etc.
        """
        return cls(
            session_id=session_id,
            session_ts=session_ts or datetime.now(timezone.utc),
            user_id=user_id,
            inputs_dir=base_inputs_dir / session_id,
            attempts_dir=base_attempts_dir / session_id,
            logs_dir=base_logs_dir / session_id,
            **overrides,
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise to a plain-data dict suitable for ``json.dumps``.

        Datetimes become ISO-8601 strings; Paths become str;
        ``AgentState`` becomes its ``asdict`` form.  ``messages``
        entries are NOT recursively converted here — callers must
        ensure ``AgentState.messages`` already holds plain dicts (use
        ``BaseMessage.dict()`` upstream) before calling ``to_dict``.
        """
        return {
            "session_id":             self.session_id,
            "session_ts":             self.session_ts.isoformat(),
            "user_id":                self.user_id,
            "dc_name":                self.dc_name,
            "schema_version":         self.schema_version,
            "dc_inspector_enabled":   self.dc_inspector_enabled,
            "rag_enabled":            self.rag_enabled,
            "mesh_checks":            self.mesh_checks,
            "chain_access":           self.chain_access,
            "keep_images_in_context": self.keep_images_in_context,
            "dcoi_comparison_mode":   self.dcoi_comparison_mode,
            "planner_first":          self.planner_first,
            "render_library":         self.render_library,
            "chain_log_exchanges":    list(self.chain_log_exchanges),
            "agent_states": {
                k: asdict(v) for k, v in self.agent_states.items()
            },
            "inputs_dir":   None if self.inputs_dir   is None else str(self.inputs_dir),
            "attempts_dir": None if self.attempts_dir is None else str(self.attempts_dir),
            "logs_dir":     None if self.logs_dir     is None else str(self.logs_dir),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """Inverse of ``to_dict``.

        Doesn't reconstruct LLM clients (those come from the cache via
        the agent constructors).  Doesn't restore live BaseMessage
        instances (callers do that lazily via ``message_from_dict``
        when invoking the agent's LLM in later Phase-1 commits).
        """
        return cls(
            session_id=             data["session_id"],
            session_ts=             datetime.fromisoformat(data["session_ts"]),
            user_id=                data.get("user_id"),
            dc_name=                data.get("dc_name", "propeller"),
            schema_version=         data.get("schema_version", 1),
            dc_inspector_enabled=   data.get("dc_inspector_enabled", _DEFAULT_DC_INSPECTOR_ENABLED),
            rag_enabled=            data.get("rag_enabled", _DEFAULT_RAG_ENABLED),
            mesh_checks=            data.get("mesh_checks", _DEFAULT_MESH_CHECKS),
            chain_access=           data.get("chain_access", _DEFAULT_CHAIN_ACCESS),
            keep_images_in_context= data.get("keep_images_in_context", _DEFAULT_KEEP_IMAGES_IN_CONTEXT),
            dcoi_comparison_mode=   data.get("dcoi_comparison_mode", _DEFAULT_DCOI_COMPARISON_MODE),
            planner_first=          data.get("planner_first", _DEFAULT_PLANNER_FIRST),
            render_library=         data.get("render_library", _DEFAULT_RENDER_LIBRARY),
            chain_log_exchanges=    list(data.get("chain_log_exchanges", [])),
            agent_states={
                k: AgentState(**v) for k, v in data.get("agent_states", {}).items()
            },
            inputs_dir=   None if data.get("inputs_dir")   is None else Path(data["inputs_dir"]),
            attempts_dir= None if data.get("attempts_dir") is None else Path(data["attempts_dir"]),
            logs_dir=     None if data.get("logs_dir")     is None else Path(data["logs_dir"]),
        )


# ---------------------------------------------------------------------
# Plain-data invariant
# ---------------------------------------------------------------------

_PLAIN_TYPES = (str, int, float, bool, type(None))


def assert_plain_data(value, _path: str = "<root>") -> None:
    """Walk ``value`` and assert every leaf is JSON-serialisable.

    Raises ``TypeError`` with the dotted path to the offending leaf
    so the test message points at the exact AgentState or Session
    field that is leaking a non-plain object.

    Allowed leaf types: ``str``, ``int``, ``float``, ``bool``, ``None``.
    Allowed containers: ``dict`` (with ``str`` keys), ``list``,
    ``tuple``.  Anything else (Path, datetime, BaseMessage, live LLM
    client, ...) is a violation of the v3 plain-data invariant.

    Use on the output of ``Session.to_dict()`` rather than on the
    Session object itself — Session and AgentState are dataclasses,
    not dicts, and only the serialised form is the storage contract.
    """
    if isinstance(value, _PLAIN_TYPES):
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(
                    f"{_path}: dict key {k!r} is {type(k).__name__}, "
                    f"not str — JSON requires string keys"
                )
            assert_plain_data(v, f"{_path}.{k}")
        return
    if isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            assert_plain_data(v, f"{_path}[{i}]")
        return
    raise TypeError(
        f"{_path}: value of type {type(value).__name__} is not plain "
        f"data (allowed: str, int, float, bool, None, dict, list, "
        f"tuple).  This breaks the v3 plain-data invariant — if you "
        f"need to stash a live object here, put it in the LLM cache "
        f"or rebuild it from the cache during agent reconstruction."
    )
