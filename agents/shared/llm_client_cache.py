"""Process-wide LLM client cache.

Memoises ``build_llm`` results by ``(provider, model, api_key)`` so that
repeatedly constructing agents (e.g. on every Streamlit turn in v3 mode
when the live agent objects are rebuilt from ``Session.agent_states``)
does not pay the LLM-construction cost more than once per unique
provider/model/key triple.

The cache is a module-level dict, populated lazily on first
``get_for_agent(agent_key)`` call.  Idempotent: repeated calls for the
same agent_key return the same client instance.

Thread-safe via a module-level ``Lock`` — Streamlit runs each user
session in its own script-thread, and concurrent first-look-ups for the
same triple must not both build a client and race the cache write.
The double-checked-locking pattern keeps the fast path lock-free once
the entry is populated.

The underlying ``llm_provider.build_llm`` already attaches the shared
``InMemoryRateLimiter`` and applies per-provider construction quirks
(see ``llm_provider.py``).  Cached clients carry that configuration
intact — callers cannot tell whether they got a fresh build or a
cached hit.

The api_key participates in the cache key so two agents with the same
provider + model but different keys do not accidentally share a
client.  In practice all agents on one provider use one shared key, so
the triple collapses to a single cache entry per provider in the
common case.

This module is purely additive in v3-Phase-1: existing call sites of
``build_llm`` (every chain agent's ``__init__``) are unchanged and
still construct fresh clients.  Later Phase-1 commits convert those
sites to ``get_for_agent`` so reconstructing agents on every Streamlit
turn becomes free.
"""

from __future__ import annotations

from threading import Lock
from typing import Any

from agents.shared import llm_provider as _llm_provider

_CACHE: dict[tuple[str, str, str], Any] = {}
_LOCK = Lock()


def get_for_agent(agent_key: str) -> tuple[Any, str, str]:
    """Return ``(llm, provider, model)`` for ``agent_key``, building once.

    Resolves the agent's ``(provider, model, api_key)`` via
    ``llm_provider._resolve_config`` so per-agent ``.env`` overrides
    behave identically to the v4 REPL.  The first call for a given
    triple delegates to ``llm_provider.build_llm`` to construct the
    client; subsequent calls return the cached instance.
    """
    provider, model, api_key = _llm_provider._resolve_config(agent_key)
    cache_key = (provider, model, api_key)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached, provider, model
    with _LOCK:
        cached = _CACHE.get(cache_key)
        if cached is not None:
            return cached, provider, model
        llm, _, _ = _llm_provider.build_llm(agent_key)
        _CACHE[cache_key] = llm
        return llm, provider, model


def reset_for_tests() -> None:
    """Drop all cached clients.  Test-only helper.

    Streamlit's hot-reload swaps modules wholesale, so production runs
    never need this.  Smoke tests that call ``get_for_agent`` with
    stubbed providers should call ``reset_for_tests`` between cases to
    avoid cross-test cache pollution.
    """
    with _LOCK:
        _CACHE.clear()
