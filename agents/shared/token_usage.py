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

Prompt-cache cost
-----------------
Raw token counts stopped being a cost proxy once prompt caching landed:
the same 8,500 input tokens cost wildly different amounts depending on
whether they were read from cache (0.1x), written to it (1.25x at a
5-minute ttl, 2x at an hour) or sent fresh (1x).  So each line also
carries a ``billed=`` figure in **input-token equivalents** — 1.0
equivalent being one full-price input token::

    [DCIC]  tokens  in=8,564  out=142  (cached 8,513 · wrote 49 5m)
                    billed=915 in-eq (saves 89%)

The unit is deliberately equivalents rather than currency: it is
model-agnostic, so it stays correct across Opus / Sonnet / Haiku and
needs no price table to drift out of date.  Output tokens are billed
separately and are NOT folded in.

Two things it is careful about:

* **A cold call shows a write PREMIUM, not a saving** — writing 8,435
  tokens at 1.25x bills 10,575 equivalents against 8,466 raw.  That is
  real, and caching only pays back from the second call on; the wording
  says ``write premium +25%`` so it can never be read as a win.
* **Silence on providers that do not report caching.**  OpenAI and
  Google expose no cache fields, so no ``billed=`` is printed for them.
  Printing "billed = in, saves 0%" would assert something this module
  cannot see — OpenAI caches automatically and simply does not say so.
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
_SESSION: dict[str, dict] = {}

# The turn currently open, if any.
_TURN_AGENT: str | None = None
_TURN: dict = {"in": 0, "out": 0, "calls": 0, "billed": 0.0, "cache_seen": 0}

# Calls whose provider reported no usage at all, session-wide.
_UNAVAILABLE = 0


def _blank() -> dict:
    # ``billed`` is a float — input-token EQUIVALENTS after cache pricing
    # (see billed_input).  Every other value is a raw count.
    return {"in": 0, "out": 0, "calls": 0, "billed": 0.0, "cache_seen": 0}


# ---------------------------------------------------------------------------
# Reading usage off a provider response
# ---------------------------------------------------------------------------

# The post-session Database Handler reads its own ttl setting (§30), so
# pricing an unsplit write by the SESSION ttl would be wrong the moment
# the two diverge.  Every DH call site labels itself with a name
# starting "DH" — "DH-decide", "DH-formulate", "DH-compress",
# "DH-force-tool-<n>", "DH<-<agent_key>" — and no in-session agent name
# does, so the label is a reliable phase marker.  Keep that true: a new
# DH call site must keep the prefix, and no agent may be named "DH*".
_SAVE_LABEL_PREFIX = "DH"


def _phase_for(agent_name: str) -> str:
    """Which caching phase the call labelled *agent_name* belongs to."""
    return "save" if str(agent_name).startswith(_SAVE_LABEL_PREFIX) else "session"


def _configured_ttl(phase: str = "session") -> str:
    """The ttl this run asked for in *phase* — ``"5m"`` or ``"1h"``.

    Read at call time (not import time) so a Workflow-Settings change is
    picked up on the next session, matching how llm_provider reads it.
    Only consulted when the provider does NOT report the per-ttl split;
    when it does, the reported buckets win, because what was actually
    written beats what was requested.
    """
    name = "PROMPT_CACHE_TTL_SAVE" if phase == "save" else "PROMPT_CACHE_TTL"
    try:
        from workflow_settings import settings as _s
        ttl = str(getattr(_s, name, "5m")).strip()
        return ttl if ttl in ("5m", "1h") else "5m"
    except Exception:
        return "5m"


def _is_anthropic(response: Any) -> bool:
    """True when *response* came from Anthropic.

    Both bindings stamp ``response_metadata["model_provider"]`` themselves
    (``langchain_anthropic`` sets ``"anthropic"``, ``langchain_openai``
    ``"openai"``), so this reads a provider-supplied label rather than
    pattern-matching a model name.  Used for ONE decision: whether a
    reported ``cache_creation`` count carries Anthropic's write premium.
    Unknown / missing metadata answers False — the conservative side,
    since it just leaves the tokens priced at the plain input rate.
    """
    meta = getattr(response, "response_metadata", None) or {}
    return str(meta.get("model_provider", "")).strip().lower() == "anthropic"


def _extract(response: Any, phase: str = "session") -> dict[str, int] | None:
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
            # Cache WRITES, split by ttl so each can be priced correctly
            # (a 5-minute write costs 1.25x base input, a 1-hour one 2x).
            #
            # ``cache_creation`` alone is NOT the write count: when
            # Anthropic returns the per-ttl breakdown, langchain-anthropic
            # moves the tokens into the two ``ephemeral_*`` keys and sets
            # ``cache_creation`` to 0.  Reading only that key reports "no
            # writes" on a call that plainly wrote — read all three.
            w5 = int(detail_in.get("ephemeral_5m_input_tokens") or 0)
            w1h = int(detail_in.get("ephemeral_1h_input_tokens") or 0)
            if not (w5 or w1h) and _is_anthropic(response):
                # ANTHROPIC ONLY.  Since 2026-08-27 the OpenAI Responses
                # API also reports ``cache_creation`` (measured: 4,383 on
                # a cold gpt-5.6-luna call) — but OpenAI's caching is
                # AUTOMATIC and carries no write premium: those tokens
                # are billed at the plain input rate.  Attributing them
                # here would price them at 1.25x (or 2x, chosen by
                # PROMPT_CACHE_TTL — an Anthropic-only setting that has
                # no business moving a reported OpenAI cost) and print
                # "write premium +25%" on a call that paid none.  For
                # non-Anthropic the tokens are simply left in the
                # uncached remainder, which is what they cost.
                generic = int(detail_in.get("cache_creation") or 0)
                if generic:
                    # No per-ttl split reported.  Attribute by the ttl THIS
                    # run asked for rather than assuming the 5-minute
                    # default: pricing a 1-hour write at the 5m rate
                    # under-states it by 37.5% and would OVERSTATE the
                    # saving — the one direction of error that matters for
                    # a number used to justify the feature.
                    if _configured_ttl(phase) == "1h":
                        w1h = generic
                    else:
                        w5 = generic
            if w5:
                out["write_5m"] = w5
            if w1h:
                out["write_1h"] = w1h
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


# Anthropic prompt-cache multipliers, relative to the base input-token
# price.  See extra_utilities/docs/reference/design_prompt_caching.md §4.
_PRICE_CACHE_READ = 0.1
_PRICE_WRITE_5M = 1.25
_PRICE_WRITE_1H = 2.0


def billed_input(counts: dict) -> float:
    """Input cost of one call in *input-token equivalents*.

    1.0 equivalent = one full-price input token, so the unit is
    model-agnostic: it stays meaningful across Opus / Sonnet / Haiku and
    needs no price table to maintain.  Compare it against the raw ``in``
    count to see what caching saved.

        billed = uncached + 0.1·read + 1.25·write_5m + 2.0·write_1h

    ``in`` is the TOTAL input (langchain sums cached, written and fresh
    tokens into it), so the uncached remainder is what is left after
    subtracting the two cached kinds.
    """
    read = counts.get("cached", 0)
    w5 = counts.get("write_5m", 0)
    w1h = counts.get("write_1h", 0)
    uncached = max(0, counts.get("in", 0) - read - w5 - w1h)
    return (uncached
            + _PRICE_CACHE_READ * read
            + _PRICE_WRITE_5M * w5
            + _PRICE_WRITE_1H * w1h)


def _has_cache_activity(counts: dict) -> bool:
    return bool(counts.get("cached") or counts.get("write_5m")
                or counts.get("write_1h"))


def _verdict(raw: int, billed: float) -> str:
    """``saves 89%`` / ``write premium +25%`` / ``no change``.

    Spelled out in words rather than a signed percentage on purpose: a
    bare ``+89%`` reads as "89% MORE" when it means "89% LESS", and the
    write-premium case (a cold call, where billed EXCEEDS raw because a
    write costs 1.25-2x) would then look like a saving.  That is the one
    misreading that would make this indicator worse than useless.
    """
    if not raw:
        return "no input"
    delta = (billed - raw) / raw * 100.0
    if delta < -0.5:
        return f"saves {-delta:.0f}%"
    if delta > 0.5:
        return f"write premium +{delta:.0f}%"
    return "no change"


def _fmt(counts: dict) -> str:
    """``in=12,345  out=678  (cached 8,192 · wrote 49 5m)  billed=1,024 in-eq (-88%)``

    The billed figure is shown ONLY when the provider actually reported
    cache activity, so a provider that reports nothing gets silence rather
    than a fabricated "billed = in, saved 0%".

    NOTE (corrected 2026-08-27): this used to say OpenAI "has no cache
    fields to read".  That is false and was already false on
    chat/completions — OpenAI caches automatically AND reports the read
    (measured: ``cache_read`` 3,712 of 4,475 input tokens on a warm
    gpt-5.4 call, on both endpoints).  So this line DOES print for OpenAI.
    The read is priced with ``_PRICE_CACHE_READ`` = 0.1, which is also
    Anthropic's multiplier -- that looked like an accidental cross-provider
    borrow, and it is not.  Verified 2026-08-08 against OpenAI's published
    pricing: cached input is 0.1x standard input on gpt-5.6-sol/terra/luna
    and gpt-5.4, on the long-context tier as well as the short one.  The
    "saves N%" figure is therefore correct for OpenAI as it stands.  This
    does NOT extend to openrouter, which proxies upstream providers with
    different cache economics -- see warnings_developer.md W43.
    """
    line = f"in={counts['in']:,}  out={counts['out']:,}"
    extras = []
    if counts.get("cached"):
        extras.append(f"cached {counts['cached']:,}")
    if counts.get("write_5m"):
        extras.append(f"wrote {counts['write_5m']:,} 5m")
    if counts.get("write_1h"):
        extras.append(f"wrote {counts['write_1h']:,} 1h")
    if counts.get("reasoning"):
        extras.append(f"reasoning {counts['reasoning']:,}")
    if extras:
        line += "  (" + " · ".join(extras) + ")"
    if _has_cache_activity(counts):
        billed = billed_input(counts)
        raw = counts.get("in", 0)
        line += f"  billed={billed:,.0f} in-eq ({_verdict(raw, billed)})"
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
    counts = _extract(response, _phase_for(agent_name))

    with _LOCK:
        if counts is None:
            _UNAVAILABLE += 1
            logger.info(f"[{agent_name}]  tokens  unavailable (provider reported none)")
            return

        logger.info(f"[{agent_name}]  tokens  {_fmt(counts)}")

        billed = billed_input(counts)
        seen = 1 if _has_cache_activity(counts) else 0

        if _TURN_AGENT == agent_name:
            _TURN["in"] += counts["in"]
            _TURN["out"] += counts["out"]
            _TURN["calls"] += 1
            _TURN["billed"] = _TURN.get("billed", 0.0) + billed
            _TURN["cache_seen"] = _TURN.get("cache_seen", 0) + seen

        agg = _SESSION.setdefault(agent_name, _blank())
        agg["in"] += counts["in"]
        agg["out"] += counts["out"]
        agg["calls"] += 1
        agg["billed"] += billed
        agg["cache_seen"] += seen


def _flush_turn_locked() -> None:
    """Emit the open turn's total.  Caller must hold ``_LOCK``."""
    global _TURN_AGENT
    if _TURN_AGENT is not None and _TURN["calls"]:
        line = (
            f"[{_TURN_AGENT}]  turn total  "
            f"in={_TURN['in']:,}  out={_TURN['out']:,}  "
            f"· {_TURN['calls']} call{'s' if _TURN['calls'] != 1 else ''}"
        )
        line += _billed_suffix(_TURN)
        logger.info(line)
    _TURN_AGENT = None


def _billed_suffix(agg: dict) -> str:
    """``  billed=9,412 in-eq (-72%)`` — empty when no cache was observed.

    Suppressed unless at least one call in the aggregate actually reported
    cache activity, so a provider that does not report caching never gets
    a misleading "0% saved" attached to its totals.
    """
    if not agg.get("cache_seen"):
        return ""
    billed = agg.get("billed", 0.0)
    raw = agg.get("in", 0)
    return f"  billed={billed:,.0f} in-eq ({_verdict(raw, billed)})"


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

        grand = {
            "in": sum(a["in"] for a in _SESSION.values()),
            "out": sum(a["out"] for a in _SESSION.values()),
            "calls": sum(a["calls"] for a in _SESSION.values()),
            "billed": sum(a.get("billed", 0.0) for a in _SESSION.values()),
            "cache_seen": sum(a.get("cache_seen", 0) for a in _SESSION.values()),
        }

        logger.info(
            f"[TOKENS] session total  in={grand['in']:,}  "
            f"out={grand['out']:,}  "
            f"· {grand['calls']} call{'s' if grand['calls'] != 1 else ''}"
            + _billed_suffix(grand)
        )
        # Heaviest first — the interesting end of the list.
        for name, agg in sorted(
            _SESSION.items(), key=lambda kv: -(kv[1]["in"] + kv[1]["out"])
        ):
            logger.info(
                f"[TOKENS]   {name:<22} in={agg['in']:,}  "
                f"out={agg['out']:,}  · {agg['calls']} "
                f"call{'s' if agg['calls'] != 1 else ''}"
                + _billed_suffix(agg)
            )
        if grand["cache_seen"]:
            logger.info(
                "[TOKENS]   billed = input-token EQUIVALENTS after prompt-cache "
                "pricing (read 0.1x, write 1.25x/5m or 2x/1h); output tokens "
                "are billed separately and are NOT in that figure."
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


def session_totals() -> dict[str, dict]:
    """Snapshot of the per-agent totals, for callers that want the
    numbers rather than the log lines (e.g. a benchmark harness)."""
    with _LOCK:
        return {k: dict(v) for k, v in _SESSION.items()}
