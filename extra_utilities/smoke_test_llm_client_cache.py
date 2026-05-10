"""Smoke test for agents/shared/llm_client_cache.py.

Verifies:
1. Two calls to ``get_for_agent`` for the same agent_key return the
   same LLM object (cache hit).
2. Two different agent_keys that resolve to the same
   ``(provider, model, api_key)`` triple share a single cached LLM
   (cache key collapses across agents on the same provider/model/key).
3. Two agent_keys that resolve to different triples get distinct LLMs.
4. The api_key participates in the cache key — same provider + model
   but different api_key yields a different cached LLM.
5. ``reset_for_tests`` clears the cache so a subsequent call rebuilds.

The underlying ``build_llm`` and ``_resolve_config`` are mocked so the
test never touches a real provider SDK or environment file — running
this script does not require any LLM credentials.

Run from the project root:
    .venv/Scripts/python.exe extra_utilities/smoke_test_llm_client_cache.py
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.shared import llm_client_cache, llm_provider


FAKE_CONFIGS = {
    "agent_a": ("openai",    "gpt-fake",  "key-x"),
    "agent_b": ("openai",    "gpt-fake",  "key-x"),  # same triple as agent_a
    "agent_c": ("anthropic", "claude-fk", "key-y"),  # different provider+model+key
    "agent_d": ("openai",    "gpt-fake",  "key-z"),  # same provider+model, different key
}


def _fake_resolve_config(agent_name: str):
    return FAKE_CONFIGS[agent_name]


_BUILD_CALL_COUNT = {"n": 0}


def _fake_build_llm(agent_name: str):
    """Return a unique sentinel object per call so identity comparisons mean something."""
    _BUILD_CALL_COUNT["n"] += 1
    provider, model, _ = FAKE_CONFIGS[agent_name]
    return object(), provider, model


with patch.object(llm_provider, "_resolve_config", _fake_resolve_config), \
     patch.object(llm_provider, "build_llm", _fake_build_llm):

    llm_client_cache.reset_for_tests()
    _BUILD_CALL_COUNT["n"] = 0

    # Case 1: same agent twice -> same instance, build called once.
    a1, prov1, mdl1 = llm_client_cache.get_for_agent("agent_a")
    a2, prov2, mdl2 = llm_client_cache.get_for_agent("agent_a")
    assert a1 is a2, "same agent_key must return the same cached LLM object"
    assert prov1 == prov2 == "openai"
    assert mdl1 == mdl2 == "gpt-fake"
    assert _BUILD_CALL_COUNT["n"] == 1, (
        f"build_llm should fire once for first agent, got {_BUILD_CALL_COUNT['n']}"
    )
    print("PASS case 1 — repeat call for same agent_key returns cached LLM")

    # Case 2: different agent_key, same triple -> cache hit, no extra build.
    b1, _, _ = llm_client_cache.get_for_agent("agent_b")
    assert b1 is a1, (
        "agent_a and agent_b resolve to the same triple; must share the cached LLM"
    )
    assert _BUILD_CALL_COUNT["n"] == 1, (
        "agent_b must hit the cache; build_llm should NOT have fired again"
    )
    print("PASS case 2 — distinct agent_keys with same triple share one cached LLM")

    # Case 3: different triple -> different cached LLM.
    c1, prov_c, mdl_c = llm_client_cache.get_for_agent("agent_c")
    assert c1 is not a1, "different (provider, model, api_key) must yield different LLMs"
    assert prov_c == "anthropic"
    assert _BUILD_CALL_COUNT["n"] == 2, "build_llm should fire for the new triple"
    print("PASS case 3 — different (provider, model, api_key) yields different LLM")

    # Case 4: same provider + model but different api_key -> different cached LLM.
    d1, _, _ = llm_client_cache.get_for_agent("agent_d")
    assert d1 is not a1, (
        "different api_key with same provider+model must yield a different LLM"
    )
    assert _BUILD_CALL_COUNT["n"] == 3, "build_llm should fire for the new api_key triple"
    print("PASS case 4 — api_key participates in the cache key")

    # Case 5: reset clears the cache.
    llm_client_cache.reset_for_tests()
    a3, _, _ = llm_client_cache.get_for_agent("agent_a")
    assert a3 is not a1, "reset_for_tests must drop the cache so a new LLM is built"
    assert _BUILD_CALL_COUNT["n"] == 4, "build_llm should fire after a reset"
    print("PASS case 5 — reset_for_tests clears the cache")

print()
print("LLM client cache smoke test passed.")
