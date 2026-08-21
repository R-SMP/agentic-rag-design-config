"""Visualization event bus — decoupled link from agent tools to the
web viewer.

An agent tool (``visualize_3d_model``) publishes a small event; the
web layer (``web_app.py`` SSE endpoint) subscribes and pushes it to
the browser, so the 3D model appears the moment the tool is used —
not only at end-of-turn.

Framework-agnostic on purpose: the agents layer must not import the
web layer (and vice versa).  Both sides depend only on this module
(same spirit as ``agents/shared/trace.py``).  When nobody is
subscribed (e.g. the CLI REPL), :func:`publish` is a harmless no-op.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path

_subscribers: list[queue.Queue] = []
_lock = threading.Lock()
# Generous per-subscriber buffer: box-switch (``agent_active``) and
# ``generic_tool`` events arrive in bursts during a busy turn, and a
# dropped box-switch is what mis-attributes a tool subtext to the wrong
# agent box.  Kept bounded so a dead/slow SSE client can never grow it
# without limit; on overflow ``publish`` evicts the OLDEST event so the
# freshest state wins (see below).
_MAX_QUEUED = 256


def subscribe() -> queue.Queue:
    """Register a new subscriber and return its event queue."""
    q: queue.Queue = queue.Queue(maxsize=_MAX_QUEUED)
    with _lock:
        _subscribers.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    """Drop a subscriber (called when an SSE client disconnects)."""
    with _lock:
        if q in _subscribers:
            _subscribers.remove(q)


def publish(event: dict) -> int:
    """Push ``event`` to every current subscriber.

    Returns the number of subscribers reached (0 = no web UI
    listening; still a successful publish, just nobody home).  Never
    blocks: a full subscriber queue drops the event for that
    subscriber rather than stalling the agent pipeline.
    """
    with _lock:
        subs = list(_subscribers)
    delivered = 0
    for q in subs:
        try:
            q.put_nowait(event)
            delivered += 1
        except queue.Full:
            # Evict the OLDEST queued event and retry: for a "current
            # state" display the newest box-switch matters more than a
            # stale one.  Still non-blocking — never stalls the agent
            # pipeline.
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(event)
                delivered += 1
            except queue.Full:
                pass
    return delivered


# Last-visualised attempt folder — Stage A single-tenant cache.
# Written by tools/visualize_model/visualize_model.py when it accepts
# an obj_path; read by web_app.py's /api/parameters endpoint so the
# Copy parameters list button can serve the actual attempt's
# parameters.json instead of the canonical reference list.  W13/O9
# lock Stage A to single-user-at-a-time on disk, so a single
# module-level Path is sufficient.  None when no mesh has been
# visualised yet this process.
_last_visualized_attempt_dir: "Path | None" = None
_last_lock = threading.Lock()


def set_last_visualized_attempt_dir(folder: "Path | None") -> None:
    """Record the attempt folder of the most recently visualised mesh
    (or ``None`` to clear).  See module-level comment above."""
    global _last_visualized_attempt_dir
    with _last_lock:
        _last_visualized_attempt_dir = folder


def get_last_visualized_attempt_dir() -> "Path | None":
    """Return the attempt folder of the most recently visualised mesh,
    or ``None`` if nothing has been visualised yet."""
    with _last_lock:
        return _last_visualized_attempt_dir
