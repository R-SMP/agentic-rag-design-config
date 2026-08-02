"""Per-operation token accounting, printed into the session LOG.

Every LLM call in this system goes through
:func:`agents.shared.llm_retry.invoke_with_retry`, so recording usage
there covers every agent — chain agents, the Database Handler and the
Context Pruner alike — from ONE place.

Three levels of granularity end up in the log:

* **per call** — one line for each ``invoke``: every reasoning step,
  every tool round-trip, every image read.  This is what shows WHICH
  operation was expensive.
* **per turn** — a total when an agent finishes the turn it began with
  :func:`begin_turn`, so a log can be scanned without adding lines up.
* **per session** — :func:`log_session_totals` prints each agent's
  total and a grand total.  This is the number that makes a
  topology-vs-topology comparison (7-agent vs 5-agent vs 3-agent)
  measurable rather than anecdotal.

Turn boundaries are EXPLICIT: each agent calls :func:`begin_turn` at
the top of its ``run()``.  Inferring them from a change of agent name
would be free, but two back-to-back invocations of the same agent would
silently merge into one line — and a merged total looks plausible,
which is the worst kind of wrong number.

**Never estimated.**  When a provider reports no usage the line says
``unavailable``.  A fabricated token count is worse than a missing one:
it would silently corrupt exactly the comparison this module exists to
support.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger("propeller_agent")

# ---------------------------------------------------------------------------
# State
#
# The app runs ONE global session at a time, but a lock costs nothing
# and keeps the counters honest if that ever changes.
# ---------------------------------------------------------------------------

_LOCK = threading.RLock()

# agent display name -> {"in": int, "out": int, "calls": int}
_SESSION: dict[str, dict[str, int]] = {}

# The turn currently open, if any.
_TURN_AGENT: str | None = None
_TURN: dict[str, int] = {"in": 0, "out": 0, "calls": 0}

# Calls whose provider reported no usage at all, session-wide.
_UNAVAILABLE = 0


def _blank() -> dict[str, int]:
    return {"in": 0, "out": 0, "calls": 0}


# ---------------------------------------------------------------------------
# Reading usage off a provider response
# ---------------------------------------------------------------------------

def _extract(response: Any) -> dict[str, int] | None:
    """Pull token counts off an ``AIMessage``-like response.

    Prefers LangChain's standardised ``usage_metadata`` (populated by
    langchain-openai, -anthropic and -google-genai alike, and by
    OpenRouter through the OpenAI client).  Falls back to the older
    ``response_metadata["token_usage"]`` shape.

    Returns ``None`` when the provider reported nothing — the caller
    logs that as ``unavailable`` rather than guessing.
    """
    usage = getattr(response, "usage_metadata", None)
    if isinstance(usage, dict) and (
        usage.get("input_tokens") is not None
        or usage.get("output_tokens") is not None
    ):
        out: dict[str, int] = {
            "in": int(usage.get("input_tokens") or 0),
            "out": int(usage.get("output_tokens") or 0),
        }
        # Optional detail — only present on providers that report it.
        detail_in = usage.get("input_token_details") or {}
        detail_out = usage.get("output_token_details") or {}
        if isinstance(detail_in, dict):
            cached = detail_in.get("cache_read")
            if cached:
                out["cached"] = int(cached)
        if isinstance(detail_out, dict):
            reasoning = detail_out.get("reasoning")
            if reasoning:
                out["reasoning"] = int(reasoning)
        return out

    meta = getattr(response, "response_metadata", None) or {}
    legacy = meta.get("token_usage") or meta.get("usage") or {}
    if isinstance(legacy, dict):
        prompt = legacy.get("prompt_tokens", legacy.get("input_tokens"))
        completion = legacy.get(
            "completion_tokens", legacy.get("output_tokens")
        )
        if prompt is not None or completion is not None:
            return {"in": int(prompt or 0), "out": int(completion or 0)}

    return None


def _fmt(counts: dict[str, int]) -> str:
    """``in=12,345  out=678  (cached 8,192 · reasoning 512)``"""
    line = f"in={counts['in']:,}  out={counts['out']:,}"
    extras = []
    if counts.get("cached"):
        extras.append(f"cached {counts['cached']:,}")
    if counts.get("reasoning"):
        extras.append(f"reasoning {counts['reasoning']:,}")
    if extras:
        line += "  (" + " · ".join(extras) + ")"
    return line


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def begin_turn(agent_name: str) -> None:
    """Open a turn for ``agent_name``, flushing any turn still open.

    Called at the top of every agent's ``run()``.  Safe to call when no
    turn is open, and safe to call twice.
    """
    global _TURN_AGENT, _TURN
    with _LOCK:
        _flush_turn_locked()
        _TURN_AGENT = agent_name
        _TURN = _blank()


def record(agent_name: str, response: Any) -> None:
    """Log one LLM call's usage and fold it into the running totals."""
    global _UNAVAILABLE
    counts = _extract(response)

    with _LOCK:
        if counts is None:
            _UNAVAILABLE += 1
            logger.info(f"[{agent_name}]  tokens  unavailable (provider reported none)")
            return

        logger.info(f"[{agent_name}]  tokens  {_fmt(counts)}")

        if _TURN_AGENT == agent_name:
            _TURN["in"] += counts["in"]
            _TURN["out"] += counts["out"]
            _TURN["calls"] += 1

        agg = _SESSION.setdefault(agent_name, _blank())
        agg["in"] += counts["in"]
        agg["out"] += counts["out"]
        agg["calls"] += 1


def _flush_turn_locked() -> None:
    """Emit the open turn's total.  Caller must hold ``_LOCK``."""
    global _TURN_AGENT
    if _TURN_AGENT is not None and _TURN["calls"]:
        logger.info(
            f"[{_TURN_AGENT}]  turn total  "
            f"in={_TURN['in']:,}  out={_TURN['out']:,}  "
            f"· {_TURN['calls']} call{'s' if _TURN['calls'] != 1 else ''}"
        )
    _TURN_AGENT = None


def log_session_totals() -> None:
    """Print the per-agent breakdown and the session grand total.

    Called at session end.  Flushes any turn still open first, so the
    last agent's turn is never lost.
    """
    with _LOCK:
        _flush_turn_locked()
        if not _SESSION:
            logger.info("[TOKENS] session total  no LLM calls recorded")
            return

        total_in = sum(a["in"] for a in _SESSION.values())
        total_out = sum(a["out"] for a in _SESSION.values())
        total_calls = sum(a["calls"] for a in _SESSION.values())

        logger.info(
            f"[TOKENS] session total  in={total_in:,}  out={total_out:,}  "
            f"· {total_calls} call{'s' if total_calls != 1 else ''}"
        )
        # Heaviest first — the interesting end of the list.
        for name, agg in sorted(
            _SESSION.items(), key=lambda kv: -(kv[1]["in"] + kv[1]["out"])
        ):
            logger.info(
                f"[TOKENS]   {name:<22} in={agg['in']:,}  "
                f"out={agg['out']:,}  · {agg['calls']} "
                f"call{'s' if agg['calls'] != 1 else ''}"
            )
        if _UNAVAILABLE:
            logger.info(
                f"[TOKENS]   ({_UNAVAILABLE} call"
                f"{'s' if _UNAVAILABLE != 1 else ''} reported no usage and "
                f"are NOT counted above)"
            )


def reset() -> None:
    """Clear all counters.  Called when a session ends or restarts."""
    global _SESSION, _TURN_AGENT, _TURN, _UNAVAILABLE
    with _LOCK:
        _SESSION = {}
        _TURN_AGENT = None
        _TURN = _blank()
        _UNAVAILABLE = 0


def session_totals() -> dict[str, dict[str, int]]:
    """Snapshot of the per-agent totals, for callers that want the
    numbers rather than the log lines (e.g. a benchmark harness)."""
    with _LOCK:
        return {k: dict(v) for k, v in _SESSION.items()}
