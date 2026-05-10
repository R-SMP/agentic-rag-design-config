"""BaseChainAgent — shared lifecycle plumbing for the 7 chain agents.

Subclasses (Receptionist, Planner, UII, DCIC, DCII, ToolCaller, DCOI)
inherit:

  * LLM lookup via ``llm_client_cache`` (replaces the per-agent
    ``build_llm(AGENT_KEY)`` call in each subclass's ``__init__``).
  * Common state restore: ``messages``, ``_pending_hop``, image
    buffers, plus the optional Receptionist (``cycle_start_ts``) and
    Planner (``current_plan``) fields are restored uniformly.
  * Symmetric ``snapshot_state()`` that captures everything back into
    a fresh ``AgentState`` ready for storage.
  * Session-config flag forwarding (``keep_images_in_context``).

Subclasses MUST set the class attribute ``AGENT_KEY`` and provide
their own:
  * ``system_prompt`` assembly (each agent's prompt template differs
    and may include session-config-derived blocks).
  * ``set_routing_tools()`` / ``set_tools()`` (signatures differ per
    agent — some take a ``next_agent`` arg, some ``prev_agent``,
    Receptionist takes neither).
  * ``_run_llm_loop()`` (tool dispatch logic is agent-specific —
    Planner has image loaders, Tool Caller has mesh tools, DCOI has
    render loaders, ...).

This module does NOT touch the dispatch / routing pipeline.  Which
agent calls which is determined by the routing tools each agent gets
bound to and by the Orchestrator's ``dispatch`` loop, neither of
which this base class affects.
"""

from __future__ import annotations

from typing import ClassVar

from agents.shared import llm_client_cache as _default_llm_cache
from agents.shared.routing_tools import AgentHop
from agents.shared.session import AgentState, Session


class BaseChainAgent:
    """Common scaffolding for chain agents — see module docstring."""

    AGENT_KEY: ClassVar[str]  # subclasses must set

    def __init__(
        self,
        state: AgentState,
        session: Session,
        llm_cache=None,
    ):
        if not getattr(self, "AGENT_KEY", None):
            raise TypeError(
                f"{type(self).__name__} must define class attribute "
                f"AGENT_KEY before subclassing BaseChainAgent."
            )
        if state.agent_key != self.AGENT_KEY:
            raise ValueError(
                f"AgentState.agent_key={state.agent_key!r} does not "
                f"match this class's AGENT_KEY={self.AGENT_KEY!r}."
            )

        cache = llm_cache if llm_cache is not None else _default_llm_cache
        self.base_llm, self.provider, self.model = cache.get_for_agent(
            self.AGENT_KEY
        )
        # Most subclasses re-bind ``self.llm`` in ``set_routing_tools``
        # / ``set_tools`` to the tool-bound version.
        self.llm = self.base_llm

        self.session = session
        # Session-config flags forwarded onto self for backwards
        # compatibility with v4 code that reads ``self.keep_images_in_
        # context`` directly.  Other flags (rag_enabled, etc.) are
        # subclass-specific and stay in subclass __init__.
        self.keep_images_in_context = session.keep_images_in_context

        # Restore plain-data state.  Lists are shallow-copied so
        # mutating this agent's fields does not retroactively edit
        # the snapshot the agent was built from.
        self.messages = list(state.messages)
        self._pending_hop = (
            None if state.pending_hop is None
            else AgentHop(**state.pending_hop)
        )
        self._pending_image_blocks = list(state.pending_image_blocks)
        self._pending_image_paths = list(state.pending_image_paths)

        # Optional agent-specific fields, restored uniformly so every
        # subclass has a well-defined attribute.  ``cycle_start_ts``
        # is only meaningful for Receptionist; ``current_plan`` only
        # for Planner.  Other agents carry the defaults harmlessly.
        self.cycle_start_ts = state.cycle_start_ts
        self.current_plan = state.current_plan

    def snapshot_state(self) -> AgentState:
        """Return a fresh ``AgentState`` with this agent's current state.

        All optional fields are captured uniformly via getattr-with-
        default so subclasses do not need to override.  Receptionist
        will have ``cycle_start_ts`` populated; Planner will have
        ``current_plan``; other agents will have both at the default
        (None / "").
        """
        hop_dict = None
        if self._pending_hop is not None:
            hop_dict = {
                "target":  self._pending_hop.target,
                "message": self._pending_hop.message,
            }
        return AgentState(
            agent_key=self.AGENT_KEY,
            messages=list(self.messages),
            pending_hop=hop_dict,
            pending_image_blocks=list(
                getattr(self, "_pending_image_blocks", [])
            ),
            pending_image_paths=list(
                getattr(self, "_pending_image_paths", [])
            ),
            cycle_start_ts=getattr(self, "cycle_start_ts", None),
            current_plan=getattr(self, "current_plan", ""),
        )

    def reset(self) -> None:
        """Clear conversation history.  Subclasses may override."""
        self.messages.clear()
