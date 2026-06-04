"""Cooperative stop signal for the multi-agent pipeline.

The web UI exposes a "Stop" button that asks the in-flight pipeline
to halt as soon as the currently-acting step finishes — without
killing the LLM call mid-flight (which the API can't undo) and
without leaking partial state.

The implementation is intentionally minimal: a single module-level
boolean.  The web layer flips it on via ``request_stop()`` when the
user clicks Stop; the Orchestrator's hop loop polls it via
``is_stop_requested()`` at each hop boundary and returns a
user-facing "session interrupted" message if it's set.
``clear_stop()`` resets the flag at the start of every new
``dispatch_turn`` so a stale stop from a previous turn doesn't
silently cancel the next one.

No threading primitives needed — Python's GIL makes single-variable
reads / writes atomic, and the flag is only ever read at safe
boundaries (between agent hops, never inside a hop).  The web
process is single-worker by design (W17), so there is no cross-
process state to worry about.
"""

from __future__ import annotations


_stop_requested: bool = False


def request_stop() -> None:
    """Mark the current turn for cooperative cancellation.

    Safe to call at any time, including when no turn is running —
    the flag is auto-cleared at the start of the next dispatch_turn.
    """
    global _stop_requested
    _stop_requested = True


def clear_stop() -> None:
    """Clear the stop flag.  Called at the start of every
    ``dispatch_turn`` so a leftover request_stop() from before
    a turn started does not cancel the new turn."""
    global _stop_requested
    _stop_requested = False


def is_stop_requested() -> bool:
    """Return True if request_stop() has been called and the flag
    has not yet been cleared.  The Orchestrator polls this between
    hops and bails when it returns True."""
    return _stop_requested


class StopRequestedError(RuntimeError):
    """Raised by chain agents (and the dispatcher) when the user
    clicks Stop mid-pipeline.  ``dispatch_turn`` catches this and
    surfaces the user-facing "(Session interrupted...)" reply.

    Chain agents call :func:`check_stop_or_raise` at the top of
    each iteration of their outer ``for _ in range(MAX_<X>_STEPS)``
    loop AND the inner ``for i, tc in enumerate(response.tool_calls)``
    loop, so a Stop click is honoured within ~one inner step
    rather than ~one full hop boundary.  See W36 (and the upcoming
    W-entry for the L1+L2 stop fix) for the no-regression rules.
    """


def check_stop_or_raise() -> None:
    """Poll the stop signal and raise :class:`StopRequestedError`
    if set.

    Cheap (a single global-bool read); safe to call in tight
    loops.  Equivalent in effect to the Orchestrator's existing
    hop-boundary check at ``orchestrator.dispatch`` but at a much
    finer granularity, so a stop click during a slow LLM call or
    a slow tool (e.g. generate_propeller_mesh) is honoured BEFORE
    the next step starts rather than after the current full hop
    completes.
    """
    if _stop_requested:
        raise StopRequestedError(
            "User clicked Stop; pipeline halted at next checkpoint."
        )
