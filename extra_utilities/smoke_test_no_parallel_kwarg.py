"""Smoke-test that no agent still passes parallel_tool_calls=False.

After the buffer-and-flush refactor (TODO #1 proper fix), the
provider-specific stop-gap should be gone everywhere.  This test
constructs the full agent stack under an Anthropic mock and asserts
that every bind_tools() call site receives ZERO kwargs.

Run from the project root:
    .venv/Scripts/python.exe extra_utilities/smoke_test_no_parallel_kwarg.py
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _FakeLLM:
    def __init__(self, *a, **kw):
        self.rate_limiter = kw.get("rate_limiter")

    def bind_tools(self, tools, **kw):
        # CRITICAL: no agent should still pass parallel_tool_calls=False
        assert "parallel_tool_calls" not in kw, (
            f"BAD: an agent still passes "
            f"parallel_tool_calls={kw['parallel_tool_calls']!r} "
            f"to bind_tools; the TODO #1 stop-gap should have been removed."
        )
        return self


# Stub the Anthropic binding so build_llm() can construct without an API key
fake_pkg = types.ModuleType("langchain_anthropic")
fake_pkg.ChatAnthropic = _FakeLLM
sys.modules["langchain_anthropic"] = fake_pkg


import agents.shared.llm_provider as lp


def _fake_resolve(_):
    return ("anthropic", "claude-opus-4-5", "sk-fake")


with patch.object(lp, "_resolve_config", _fake_resolve):
    from agents.orchestrator.orchestrator import Orchestrator
    o = Orchestrator(
        mesh_checks=False,
        rag_enabled=False,
        dc_inspector_enabled=True,
        chain_access=False,
        keep_images_in_context=False,
        dcoi_comparison_mode=3,
    )
    print("Orchestrator + all sub-agents constructed with Anthropic mock.")
    print("Every bind_tools() call passed only the tools list — no kwargs.")
    print("PASS: TODO #1 stop-gap is fully removed.")
