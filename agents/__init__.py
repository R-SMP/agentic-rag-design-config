"""Multi-agent design configurator system.

Public entry points:
    from agents import Orchestrator
    from agents.loader import run

Each agent lives under ``agents/<agent_name>/`` (its Python script,
``prompt.md`` template, and an optional ``.env`` for per-agent LLM
override).  Generic, DC- and tool-agnostic utilities live under
``agents/shared/``.
"""

from agents.orchestrator import Orchestrator

__all__ = ["Orchestrator"]
