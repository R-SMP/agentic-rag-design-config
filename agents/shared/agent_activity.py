"""Helpers for the LOG and Status flowchart's live highlighting.

The flowchart's ``agent_active`` events are published from
``agents.shared.trace.trace`` for agent→agent handoffs (which were
already instrumented for the on-disk agent-flow trace).  Tools need
the same lifecycle treatment but with two differences:

  1. While a tool is running, the CALLING agent (typically the Tool
     Caller) is still semantically "in flight" — it is waiting on the
     tool to return.  The frontend should keep the caller's box lit
     alongside the tool's box, not swap one for the other.
  2. When the tool returns, the caller should be the only box lit;
     the tool box turns off.  This requires an explicit exit event —
     trace() at function entry only is not enough.

The :func:`tool_active` decorator handles both: emits an
``agent_active`` (caller -> tool_name) on entry, and an
``agent_active`` (tool_name -> caller) on exit, regardless of how
the wrapped function returns (success, validation early-return, or
exception).

Usage::

    from agents.shared.agent_activity import tool_active
    from langchain_core.tools import tool

    @tool
    @tool_active("Propeller Configurator")
    def generate_and_render_propeller(...) -> str:
        ...

``@tool_active`` MUST sit BELOW ``@tool`` so it wraps the plain
function before LangChain converts it to a ``BaseTool`` object.
"""

from __future__ import annotations

import functools
from typing import Callable


def generic_tool(name: str) -> Callable[[Callable], Callable]:
    """Decorator for "generic" tools — every tool that is NOT one of
    the tools that have their own box on the flowchart (Propeller
    Configurator, Blade Sections).

    A generic tool call does NOT swap which agent is active — the
    calling agent stays "in flight" while the helper runs (reading
    a file, listing attempts, writing parameters, etc.).  So the
    frontend keeps the agent's box highlighted and merely shows a
    small floating text label next to it carrying ``name`` while
    the call is in progress.  The label disappears when the call
    returns (or raises).

    The display ``name`` you pass here is what shows up next to the
    agent's box on the flowchart — keep it short and human-readable
    (e.g. "Read user inputs", "New attempt", "Calculate").

    These events are intentionally NOT routed through ``_trace`` —
    the on-disk agent-flow file is meant to record agent-level
    handoffs, not every internal helper call.  Generic-tool entries
    would drown it.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Stamp the running agent onto the event so the frontend can
            # bind the subtext to the box of the agent that ACTUALLY ran
            # this helper, rather than whatever box is currently lit
            # (which can be stale if the box-switch event was dropped).
            try:
                from agents.shared.viz_bus import publish as _publish
                from agents.shared.trace import get_current_agent
                _publish({"type": "generic_tool", "name": name,
                          "state": "start", "agent": get_current_agent()})
            except Exception:
                pass
            try:
                return fn(*args, **kwargs)
            finally:
                try:
                    from agents.shared.viz_bus import publish as _publish
                    from agents.shared.trace import get_current_agent
                    _publish({"type": "generic_tool", "name": name,
                              "state": "end", "agent": get_current_agent()})
                except Exception:
                    pass
        return wrapper
    return decorator


def tool_active(
    tool_name: str,
    *,
    caller: str = "Tool Caller",
) -> Callable[[Callable], Callable]:
    """Return a decorator that publishes entry / exit activity events
    for a tool, so the LOG and Status flowchart can light up the
    tool's box while the call is in flight and turn it off when the
    call returns.

    The wrapped function is otherwise untouched.  Side effects use
    a best-effort try/except — instrumentation MUST NOT break a
    real tool invocation.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Entry: real handoff, log it via trace() so the agent-
            # flow trace file gets the line AND the viz_bus event
            # gets published.
            try:
                from agents.shared.trace import trace as _trace
                _trace(caller, tool_name)
            except Exception:
                pass
            try:
                return fn(*args, **kwargs)
            finally:
                # Exit: also a real handoff (the tool returned
                # control to its caller), so trace() again — the
                # flow file then records the round trip.
                try:
                    from agents.shared.trace import trace as _trace
                    _trace(tool_name, caller, "tool returned")
                except Exception:
                    pass
        return wrapper
    return decorator
