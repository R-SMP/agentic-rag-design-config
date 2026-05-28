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


def init_trace(log_dir: Path) -> Path:
    """Create a new trace file.  Returns the path."""
    global _trace_file
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
