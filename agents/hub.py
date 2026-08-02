"""Construct the active topology's hub agent.

Every entry point that needs a wired agent set — ``dispatch.py``,
``loader.py``, ``web_app.py``, ``database_handler.py`` — calls
:func:`build_hub` instead of naming a hub class.  None of those modules
imports the others, so homing the factory here adds no coupling between
them, and ``dispatch.py`` stays about running a turn rather than about
choosing an agent set.

The two hubs are drop-in interchangeable.  Both expose the same seven
public methods — ``run``, ``dispatch``, ``reset``, ``reset_turn``,
``dump_histories``, ``get_agent_messages``, ``run_feedback_round`` — and
the three attributes callers reach for: ``receptionist``,
``database_handler`` and ``_agents_by_key``.  Callers therefore treat the
result opaquely and never branch on topology themselves.
"""

from agents.shared.topology import topology


def build_hub(session, *, llm_cache=None):
    """The active topology's hub, with every sub-agent constructed.

    Constructing a hub materialises the whole agent set: each sub-agent
    builds its own LLM and its own system prompt.  That is why there is
    exactly one of these per session rather than one per call site.

    The hub classes are imported lazily so that selecting one topology
    never imports the other's agent modules — the 5-agent Conductor pulls
    in the Creator, the 7-agent Orchestrator pulls in the Planner and the
    two DC inspectors, and neither should pay for the other.
    """
    if topology() == 5:
        from agents.conductor import Conductor
        return Conductor(session=session, llm_cache=llm_cache)
    from agents.orchestrator import Orchestrator
    return Orchestrator(session=session, llm_cache=llm_cache)
