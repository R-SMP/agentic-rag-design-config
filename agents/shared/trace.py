"""Lightweight agent-flow trace logger.

Writes a human-readable .txt file showing who contacted whom and when.
No message content -- just the flow, one line per exchange.

Example output::

    === Agent Flow Trace ===
    Started: 2026-04-16 19:05:10

    19:05:12  User --> Receptionist
    19:05:13  Receptionist --> Orchestrator
    19:05:14  Orchestrator --> Planner
    19:05:15  Planner --> User Input Inspector
    19:05:18  DC Input Inspector --> DC Input Creator
    19:05:28  Orchestrator --> User
"""

from datetime import datetime
from pathlib import Path

_trace_file = None

# ---------------------------------------------------------------------------
# Current-agent tracker (for generic-tool subtext attribution)
# ---------------------------------------------------------------------------
#
# The LOG-and-Status flowchart shows a "last used tool" subtext under
# each agent box.  It must be bound to the agent that ACTUALLY ran the
# tool — never to whatever box happens to be highlighted, which can go
# stale if a box-switch (``agent_active``) event was dropped by the viz
# bus.  We keep an authoritative, in-process record of which real agent
# is currently in flight here (updated synchronously on every handoff,
# not through the lossy event queue) and stamp it onto every
# ``generic_tool`` event; the frontend then targets that exact box.
#
# The set is ``AGENT_DISPLAY.values()`` from ``routing_tools.py`` (the
# 8 chain agents) PLUS "Database Handler" — a real flowchart agent box
# (``agent-database-handler`` in web/app.js) that runs post-session and
# is not in the routing table.  It is duplicated here (not imported)
# because ``routing_tools`` imports THIS module — importing it back
# would be a circular import.  Tool boxes (Propeller Configurator, Blade
# Sections, Context Pruner) are deliberately excluded: a generic
# helper's subtext belongs to the agent that ran it, never a tool box.
_AGENT_DISPLAY_NAMES = frozenset({
    "Receptionist", "Orchestrator", "User Input Inspector", "Planner",
    "DC Input Creator", "DC Input Inspector", "Tool Caller",
    "DC Output Inspector", "Database Handler",
    # 5-agent topology (superset — a topology that does not use them
    # simply never emits their events).
    "Conductor", "Creator",
})
_current_agent = None


def get_current_agent():
    """Return the display name of the real agent currently in flight
    (the most recent handoff target that was a known agent), or
    ``None`` before the first handoff.  Used to attribute generic-tool
    subtexts to the correct flowchart box even when the box-switch
    event was dropped downstream."""
    return _current_agent


def init_trace(log_dir: Path) -> Path:
    """Create a new trace file.  Returns the path."""
    global _trace_file, _current_agent
    _current_agent = None
    log_dir.mkdir(parents=True, exist_ok=True)
    start = datetime.now()
    timestamp = start.strftime("%Y%m%d_%H%M%S")
    trace_path = log_dir / f"agent_flow_{timestamp}.txt"
    _trace_file = open(trace_path, "w", encoding="utf-8")
    _trace_file.write("=== Agent Flow Trace ===\n")
    _trace_file.write(f"Started: {start.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    _trace_file.flush()
    return trace_path


def trace(from_agent: str, to_agent: str, note: str = "",
          *, publish: bool = True) -> None:
    """Append one line: ``HH:MM:SS  A --> B  (optional note)``.

    Side effect (when ``publish=True``, the default): publishes an
    ``agent_active`` event on ``agents.shared.viz_bus`` so the web
    UI's LOG and Status flowchart can highlight the currently-
    active agent box.  The publish is a no-op when nobody is
    subscribed (REPL / tests).

    Callers that record file-only trace lines for events the
    flowchart should NOT react to (e.g. utility-tool invocations
    logged by ``log_tool_call``, where ``to_agent`` is a tool
    function name rather than a real agent) MUST pass
    ``publish=False`` — otherwise the frontend receives a bogus
    ``agent_active`` whose ``to`` is an unknown id, clears every
    real agent's highlight, and fails to re-activate anything.
    """
    if _trace_file is not None:
        now = datetime.now().strftime("%H:%M:%S")
        line = f"{now}  {from_agent} --> {to_agent}"
        if note:
            line += f"  ({note})"
        _trace_file.write(line + "\n")
        _trace_file.flush()

    # Track which real agent is now in flight so generic-tool subtexts
    # can be bound to the correct box even if the box-switch event is
    # dropped downstream.  Only real agents update it — never tool
    # boxes or synthetic targets ("Error, Escalated to …").
    if to_agent in _AGENT_DISPLAY_NAMES:
        global _current_agent
        _current_agent = to_agent

    if not publish:
        return

    try:
        from agents.shared.viz_bus import publish as _publish
        _publish({
            "type": "agent_active",
            "from": from_agent,
            "to": to_agent,
            "note": note,
        })
    except Exception:
        pass


def close_trace() -> None:
    """Write footer and close the trace file."""
    global _trace_file
    if _trace_file is None:
        return
    end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _trace_file.write(f"\n=== Trace ended: {end} ===\n")
    _trace_file.close()
    _trace_file = None
