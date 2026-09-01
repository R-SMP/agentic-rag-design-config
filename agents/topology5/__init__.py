"""Topology-5 code overrides.

The prompt layer's topology dimension is a FOLDER — ``agents/5agent/`` — whose
files shadow the shared originals through ``prompts._topology_override``.  Code
cannot live there: a package name may not start with a digit, which is the
whole reason the prompt tree and the code tree are separate.  This package is
the code half of the same idea.

What belongs here: per-agent tables and text that the tool layer keys on
``agent_key`` alone, and that therefore leak between topologies if left shared.
Consumers reach them through :func:`agents.shared.topology.overlay_value`,
which returns the shared value unchanged under any topology that ships no
overlay module — so topology 7 is untouched by construction.

What does NOT belong here: anything the operator should be able to retune from
the Workflow Settings UI.  The settings editor only parses
``workflow_settings/settings.py``, so the topology-5 step budgets
(``MAX_PLANNER5_STEPS`` / ``MAX_PLANNER5_VISITS``) live there, in section 28,
beside every other cap.
"""
