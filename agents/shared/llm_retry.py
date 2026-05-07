"""Synchronous retry / back-off wrapper for LLM ``.invoke()`` calls.

Each agent's ``_run_llm_loop`` calls ``invoke_with_retry(self.llm,
messages, agent_name)`` instead of ``self.llm.invoke(messages)``
directly.  The helper intercepts two families of exception that have
killed multi-agent sessions in the past and is a no-op on success:

1. **Rate-limit (HTTP 429)** —
   ``anthropic.RateLimitError`` / ``openai.RateLimitError``.
   On Anthropic's standard tier the per-minute input-token budget can
   be exhausted by the cold-start cache writes of the first 3-4
   agents, even with the shared ``InMemoryRateLimiter`` smoothing the
   call rate.  The retry sleeps until the per-minute window is
   expected to roll over (``Retry-After`` header if the server sent
   one, else 60 s) and tries again — by which time prior cache writes
   have aged out of the rolling window and the call typically
   succeeds as a near-free cache hit.

2. **Transient connection / timeout** —
   ``APIConnectionError`` / ``APITimeoutError`` /
   ``RemoteProtocolError``.
   Network blips that previously killed entire sessions (run 2 of v5
   ended on ``httpx.RemoteProtocolError`` during the Receptionist's
   final outgoing format pass).  The retry uses exponential back-off
   with jitter (2 s, 4 s, 8 s, 16 s, capped at 30 s).

Why per-agent name as a parameter?  This is option 2 from the
implementation discussion: each call site passes its own short agent
label, so retry log lines read e.g. ``[Planner] 429 rate limit on
attempt 2/5; sleeping 60.0s before retry`` — letting post-hoc log
inspection attribute every retry to the agent that triggered it.

All other exceptions propagate unchanged — only the two retryable
families are caught.
"""

import logging
import random
import time
from typing import Any

logger = logging.getLogger("propeller_agent")

# ---------------------------------------------------------------------------
# Retry policy constants
# ---------------------------------------------------------------------------
MAX_ATTEMPTS: int = 5
DEFAULT_RATE_LIMIT_BACKOFF_S: float = 60.0  # one full per-minute window
CONNECTION_BASE_S: float = 2.0
CONNECTION_MAX_S: float = 30.0
JITTER_FRACTION: float = 0.25  # +0–25 % random jitter on connection back-off


# ---------------------------------------------------------------------------
# Exception classification
# ---------------------------------------------------------------------------
# Match by class NAME rather than ``isinstance`` so we don't have to
# import the provider SDKs at module-import time (this module is loaded
# by every agent regardless of which provider is configured).  Both
# anthropic and openai expose ``RateLimitError`` / ``APIConnectionError``
# / ``APITimeoutError`` with these exact names.

_RATE_LIMIT_EXC_NAMES = {"RateLimitError"}
_CONNECTION_EXC_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "RemoteProtocolError",
}


def _is_rate_limit(exc: BaseException) -> bool:
    return type(exc).__name__ in _RATE_LIMIT_EXC_NAMES


def _is_connection_error(exc: BaseException) -> bool:
    return type(exc).__name__ in _CONNECTION_EXC_NAMES


def _read_retry_after(exc: BaseException) -> float | None:
    """Read ``Retry-After`` (seconds) from the response headers, if any.

    The provider SDKs attach the underlying ``httpx.Response`` to the
    exception as ``.response`` (anthropic) or ``.response`` (openai).
    Either way, header lookup is case-insensitive in httpx.
    """
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def invoke_with_retry(llm: Any, messages: list, agent_name: str) -> Any:
    """Call ``llm.invoke(messages)`` with retry on rate-limit / connection
    errors, logging every retry decision under the calling agent's name.

    Parameters
    ----------
    llm
        A LangChain chat model (already bound to tools etc.).  Must
        expose ``.invoke(messages)``.
    messages
        The full message list to pass to ``invoke``.  Constructed by
        the caller exactly as before — this helper does not modify it.
    agent_name
        Short display label for the agent (e.g. ``"Planner"``,
        ``"DCIC"``).  Appears in retry log lines.

    Returns
    -------
    The provider's response object (``AIMessage``-like).  Identical
    return value to ``llm.invoke(messages)`` on success.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return llm.invoke(messages)
        except Exception as exc:
            if _is_rate_limit(exc):
                last_exc = exc
                if attempt == MAX_ATTEMPTS:
                    logger.warning(
                        f"[{agent_name}]  rate-limit retries exhausted "
                        f"after {attempt} attempts; re-raising"
                    )
                    break
                wait_s = (
                    _read_retry_after(exc) or DEFAULT_RATE_LIMIT_BACKOFF_S
                )
                logger.info(
                    f"[{agent_name}]  429 rate limit on attempt "
                    f"{attempt}/{MAX_ATTEMPTS}; sleeping {wait_s:.1f}s "
                    f"before retry"
                )
                time.sleep(wait_s)
                continue

            if _is_connection_error(exc):
                last_exc = exc
                if attempt == MAX_ATTEMPTS:
                    logger.warning(
                        f"[{agent_name}]  connection retries exhausted "
                        f"after {attempt} attempts; re-raising "
                        f"({type(exc).__name__})"
                    )
                    break
                base = min(
                    CONNECTION_BASE_S * (2 ** (attempt - 1)),
                    CONNECTION_MAX_S,
                )
                wait_s = base + random.uniform(0, base * JITTER_FRACTION)
                logger.info(
                    f"[{agent_name}]  {type(exc).__name__} on attempt "
                    f"{attempt}/{MAX_ATTEMPTS}; sleeping {wait_s:.1f}s "
                    f"before retry"
                )
                time.sleep(wait_s)
                continue

            # Non-retryable: re-raise immediately so the agent / dispatcher
            # sees the original exception with its full traceback.
            raise

    # Exhausted all attempts on a retryable exception.
    assert last_exc is not None
    raise last_exc
