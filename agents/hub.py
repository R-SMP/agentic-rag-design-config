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


def hub_class():
    """The active topology's hub CLASS, without constructing it.

    Split out so a diagnostic tool can ask which hub a topology uses —
    and read its ``_agents_by_key`` — without materialising the agent
    set, which needs real API keys.  Keeping the branch here rather than
    duplicating it in the tool means exactly one place still maps a
    topology to a hub.

    The hub classes are imported lazily so that selecting one topology
    never imports the other's agent modules — the 7-agent Orchestrator
    pulls in the Planner and both DC inspectors, while the 5-agent Planner5
    pulls in neither of those two, and neither topology should pay for the
    other.
    """
    if topology() == 5:
        from agents.planner5 import Planner5
        return Planner5
    if topology() == 3:
        from agents.architect import Architect
        return Architect
    from agents.orchestrator import Orchestrator
    return Orchestrator


def build_hub(session, *, llm_cache=None):
    """The active topology's hub, with every sub-agent constructed.

    Constructing a hub materialises the whole agent set: each sub-agent
    builds its own LLM and its own system prompt.  That is why there is
    exactly one of these per session rather than one per call site.
    """
    return hub_class()(session=session, llm_cache=llm_cache)
