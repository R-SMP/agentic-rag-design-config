"""Which agent holds which role, per topology.

The one table behind three things that must agree:

* **Retrieval** -- ``database_search`` (text, multimodal and parameter
  search) lets an agent read an answer whose ``agents_to`` names any agent
  whose role it holds in the running topology: :func:`readable_keys`.
* **The ``<agent_roles>`` legend** -- printed once at the top of a
  ``database_search`` response when a result names an agent the running
  topology does not build: :func:`legend`.
* **The Database Handler's question table** -- a row whose ``Agent from``
  is a seven-agent role the running topology merged away is asked to the
  agent holding that role: :func:`question_answerer`.

The seven-agent roster is the reference.  Topology 5 drops the Orchestrator
(the Planner hubs instead) and the DC Input Inspector (the DC Input Creator
validates its own parameters).  Topology 3 also merges the DC Input Creator,
DC Input Inspector and Tool Caller into the Design Engineer, and the User
Input Inspector and DC Output Inspector into the Requirements Analyst.

Retrieval maps BOTH ways (a 7-agent DC Input Creator reads what was
addressed to a 3-agent Design Engineer).  The question table maps DOWNWARD
only: the tables are written in seven-agent names, and a Design Engineer or
Requirements Analyst row run under topology 7 or 5 is skipped rather than
guessed at.

Dependency-free on purpose (``workflow_settings`` + ``topology`` only):
``dh_schedule.py`` and ``param_rank.py`` import it and must stay importable
without ``langchain_core``.  Every value is read FRESH on each call -- the
Sessions Queue switches topology between runs inside one process.

The user-customizable version of this table is TODO F102; once it exists,
``RAG_DCIC_READS_DCII`` is redundant (TODO F103).
"""

from __future__ import annotations

import re

from agents.shared import topology as _topology
from workflow_settings import settings as _workflow_settings

# The agents each topology builds (the hub included).  Asserted against
# every hub's real ``_agents_by_key`` by smoke_test_agent_roles.py.
ROSTER: dict[int, tuple[str, ...]] = {
    7: ("receptionist", "orchestrator", "user_input_inspector", "planner",
        "dc_input_creator", "dc_input_inspector", "tool_caller",
        "dc_output_inspector"),
    5: ("receptionist", "planner", "user_input_inspector", "dc_input_creator",
        "tool_caller", "dc_output_inspector"),
    3: ("receptionist", "planner", "design_engineer", "requirements_analyst"),
}

# The seven-agent roles a merged agent carries.  Every other key carries
# exactly one role: itself.
ROLES_OF: dict[str, tuple[str, ...]] = {
    "design_engineer":      ("dc_input_creator", "dc_input_inspector",
                             "tool_caller"),
    "requirements_analyst": ("user_input_inspector", "dc_output_inspector"),
}

# Seven-agent role -> the agent that holds it, where that is not the role
# itself.  A role neither here nor in the roster has no holder.
_HOLDER_BY_TOPOLOGY: dict[int, dict[str, str]] = {
    7: {},
    5: {
        "orchestrator":       "planner",
        # Gated by RAG_DCIC_READS_DCII (see holder()).
        "dc_input_inspector": "dc_input_creator",
    },
    3: {
        "orchestrator":         "planner",
        "user_input_inspector": "requirements_analyst",
        "dc_output_inspector":  "requirements_analyst",
        "dc_input_creator":     "design_engineer",
        "dc_input_inspector":   "design_engineer",
        "tool_caller":          "design_engineer",
    },
}

# Agent-facing display names.  Must agree with routing_tools.AGENT_DISPLAY
# (duplicated because that module imports langchain_core; the smoke test
# asserts the two agree).
DISPLAY: dict[str, str] = {
    "receptionist":         "Receptionist",
    "orchestrator":         "Orchestrator",
    "user_input_inspector": "User Input Inspector",
    "planner":              "Planner",
    "dc_input_creator":     "DC Input Creator",
    "dc_input_inspector":   "DC Input Inspector",
    "tool_caller":          "Tool Caller",
    "dc_output_inspector":  "DC Output Inspector",
    "design_engineer":      "Design Engineer",
    "requirements_analyst": "Requirements Analyst",
}

# Abbreviations the question names and answers use ("Problem - DCII").
ABBREVIATION: dict[str, str] = {
    "user_input_inspector": "UII",
    "dc_input_creator":     "DCIC",
    "dc_input_inspector":   "DCII",
    "dc_output_inspector":  "DCOI",
}

_SEVEN = ROSTER[7]


def _topo(topo: int | None) -> int:
    t = _topology.topology() if topo is None else int(topo)
    return t if t in ROSTER else 7


def dcic_reads_dcii() -> bool:
    """The topology-5 toggle: does the DC Input Creator hold the DC Input
    Inspector's role (read its answers, answer its questions)?"""
    return bool(getattr(_workflow_settings, "RAG_DCIC_READS_DCII", True))


def roster(topo: int | None = None) -> tuple[str, ...]:
    """The agents the topology builds."""
    return ROSTER[_topo(topo)]


def holder(role: str, topo: int | None = None) -> str | None:
    """The agent holding seven-agent *role* in the topology, or None."""
    t = _topo(topo)
    if role in ROSTER[t]:
        return role
    if t == 5 and role == "dc_input_inspector" and not dcic_reads_dcii():
        return None
    return _HOLDER_BY_TOPOLOGY[t].get(role)


def roles_of(key: str) -> tuple[str, ...]:
    """The seven-agent roles *key* carries (itself, for an unmerged agent)."""
    return ROLES_OF.get(key, (key,))


def holders(key: str, topo: int | None = None) -> list[str]:
    """Every agent in the topology holding one of *key*'s roles, in roster
    order.  Empty when none does."""
    t = _topo(topo)
    held = {holder(r, t) for r in roles_of(key)} - {None}
    return [a for a in ROSTER[t] if a in held]


def readable_keys(caller: str, topo: int | None = None) -> list[str]:
    """Every ``agents_to`` key whose answers *caller* may read: itself plus
    each key (any topology) one of whose roles *caller* holds here.

    Sorted, so the SQL parameter is stable.  ``database_handler`` and other
    keys outside the role table only ever match themselves."""
    t = _topo(topo)
    keys = {caller}
    for k in (*_SEVEN, *ROLES_OF):
        if caller in holders(k, t):
            keys.add(k)
    return sorted(keys)


def question_answerer(from_agent: str, topo: int | None = None) -> str | None:
    """Who answers a question-table row whose ``Agent from`` is *from_agent*.

    DOWNWARD only: an agent the topology builds answers its own rows; a
    seven-agent role it merged away goes to that role's holder; anything
    else (a Design Engineer / Requirements Analyst row under topology 7 or
    5, a DC Input Inspector row under topology 5 with the toggle off)
    returns None and the row is skipped.
    """
    t = _topo(topo)
    if from_agent in ROSTER[t]:
        return from_agent
    if from_agent in _SEVEN:
        return holder(from_agent, t)
    return None


# ---------------------------------------------------------------------------
# The <agent_roles> legend
# ---------------------------------------------------------------------------

def _patterns(key: str) -> list[re.Pattern]:
    pats = [re.compile(r"(?<![\w])" + re.escape(DISPLAY[key]) + r"(?![\w])", re.I),
            re.compile(r"(?<![\w])" + re.escape(key) + r"(?![\w])")]
    if key in ABBREVIATION:
        pats.append(re.compile(r"(?<![\w])" + ABBREVIATION[key] + r"(?![\w])"))
    return pats


_PATTERNS = {k: _patterns(k) for k in DISPLAY}


def foreign_agents(texts, topo: int | None = None) -> list[str]:
    """Agents named anywhere in *texts* (author keys, question names, answer
    text) that the topology does not build, in DISPLAY order."""
    t = _topo(topo)
    blob = "\n".join(x for x in texts if x)
    return [k for k in DISPLAY
            if k not in ROSTER[t] and any(p.search(blob) for p in _PATTERNS[k])]


def _name(key: str) -> str:
    return (f"{DISPLAY[key]} ({ABBREVIATION[key]})" if key in ABBREVIATION
            else DISPLAY[key])


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def legend(texts, topo: int | None = None) -> str:
    """The ``<agent_roles>`` line for a response whose results contain
    *texts*, or "" when every agent they name exists in the topology.

    Only the agents actually found are listed.  Agents sharing a holder
    are grouped ("DC Input Inspector (DCII), Tool Caller -> Design
    Engineer"); a role split across several agents here says so."""
    t = _topo(topo)
    found = foreign_agents(texts, t)
    if not found:
        return ""
    groups: dict[tuple[str, ...], list[str]] = {}
    for k in found:
        groups.setdefault(tuple(holders(k, t)), []).append(k)
    parts = []
    for hs, ks in groups.items():
        lhs = ", ".join(_name(k) for k in ks)
        if not hs:
            parts.append(f"{lhs} → no agent here holds this role")
        elif len(hs) == 1:
            parts.append(f"{lhs} → {DISPLAY[hs[0]]}")
        else:
            parts.append(f"{lhs} → {_join([DISPLAY[h] for h in hs])} "
                         f"(the role is split across them here)")
    return ("<agent_roles>Some results come from sessions run with a different "
            "set of agents. Where a result names an agent this system does not "
            "have, read it as the agent here that holds that role: "
            + "; ".join(parts) + ".</agent_roles>")


def role_map_rows() -> list[dict]:
    """The table shown read-only in Workflow Settings: one row per
    seven-agent role, with its holder in each topology."""
    order = ("receptionist", "orchestrator", "planner", "user_input_inspector",
             "dc_input_creator", "dc_input_inspector", "tool_caller",
             "dc_output_inspector")
    return [{"role": r, "display": DISPLAY[r],
             "holders": {t: holder(r, t) for t in (7, 5, 3)}}
            for r in order]
