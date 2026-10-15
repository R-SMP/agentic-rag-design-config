"""Who sees the parameter list: one state per agent and topology.

    full   the list in the agent's system prompt, ranges included
    names  the list in the prompt with every ``[min; max]`` range removed
    tool   not in the prompt; the agent can call ``dc_params_list``
    none   neither

The setup's DEFAULT is ``parameter_access`` in ``dc_pack/pack.yaml`` (the
Studio edits it).  Workflow Settings > "Parameter list access" changes cells
for the next session; only the cells changed there are stored, in
``workflow_settings/parameter_access.json``, and every other cell keeps the
pack default.  Read fresh on every call, like every other setting: a change
takes effect when the next session's agents are built.

The table is a grid: one row per agent, one cell per topology the agent
exists in (``7``, ``5``, ``3``).  It replaces the settings
``UII_PARAMETER_LIST_ENABLED`` and ``DCOI_KNOWS_PARAMS_RANGES`` and the
``dc_params_list`` bindings that were written into the agent classes.  Where
it lands: ``agents/shared/prompts.py`` (the ``<<IF:param_list>>`` /
``<<IF:param_ranges>>`` regions and the range removal) and
``agents/shared/dc_params_tool.py`` (``param_tools_for``).

Imports nothing from ``agents`` -- the engine stays importable on its own;
the caller passes the topology.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path

import yaml

from engine import pack as _pack

STATES = ("full", "names", "tool", "none")
LABELS = {"full": "Full list", "names": "Names only",
          "tool": "Through the tool", "none": "Nothing"}
TOPOLOGIES = (7, 5, 3)
# The Database Handler only binds one forced tool per turn and has no free
# tool loop, so it cannot be given dc_params_list.
NO_TOOL_AGENTS = frozenset({"database_handler"})

OVERRIDES_PATH = (Path(__file__).resolve().parents[1]
                  / "workflow_settings" / "parameter_access.json")
_LOCK = threading.Lock()
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
# A range as the parameter lists write it: "[3; 6]", "[0.3; 0.7]".  The same
# shape extra_utilities/tests/smoke_test_parameters.py reads.
_RANGE_RE = re.compile(r" ?\[\s*-?\d+(?:\.\d+)?\s*;\s*-?\d+(?:\.\d+)?\s*\]")


class ParameterAccessError(ValueError):
    """The table in pack.yaml or the settings file is invalid."""


def pack_yaml_path() -> Path:
    return _pack.pack_dir() / "pack.yaml"


def _normalise(raw, where: str, problems: list[str]) -> dict[str, dict[int, str]]:
    table: dict[str, dict[int, str]] = {}
    if not isinstance(raw, dict):
        problems.append(f"{where}: must be a mapping of agent -> {{topology: state}}")
        return table
    for agent, cells in raw.items():
        if not isinstance(agent, str) or not _NAME_RE.match(agent):
            problems.append(f"{where}: {agent!r} is not an agent name")
            continue
        if not isinstance(cells, dict):
            problems.append(f"{where}: {agent} must map topologies to states")
            continue
        row: dict[int, str] = {}
        for topo, st in cells.items():
            try:
                t = int(topo)
            except (TypeError, ValueError):
                t = None
            if t not in TOPOLOGIES:
                problems.append(f"{where}: {agent}: {topo!r} is not a topology "
                                f"({', '.join(map(str, TOPOLOGIES))})")
                continue
            if st not in STATES:
                problems.append(f"{where}: {agent} / {t}: {st!r} is not one of "
                                f"{', '.join(STATES)}")
                continue
            if st == "tool" and agent in NO_TOOL_AGENTS:
                problems.append(f"{where}: {agent} / {t}: 'tool' is not possible "
                                f"for this agent (no free tool loop)")
                continue
            row[t] = st
        table[agent] = row
    return table


def default_table(path: Path | None = None) -> dict[str, dict[int, str]]:
    """``parameter_access`` from ``dc_pack/pack.yaml``.  Raises
    ParameterAccessError."""
    path = path or pack_yaml_path()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        raise ParameterAccessError(f"{path} does not exist") from None
    problems: list[str] = []
    table = _normalise(data.get("parameter_access"),
                       f"{path.name} parameter_access", problems)
    if problems:
        raise ParameterAccessError("\n".join(problems))
    return table


def read_overrides() -> dict[str, dict[int, str]]:
    """The cells changed in Workflow Settings.  Invalid entries raise: a
    silently ignored setting reads as "the setting did nothing"."""
    try:
        raw = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    problems: list[str] = []
    table = _normalise(raw, OVERRIDES_PATH.name, problems)
    if problems:
        raise ParameterAccessError("\n".join(problems))
    return table


def table() -> dict[str, dict[int, str]]:
    """The effective table: the pack default with the Workflow Settings
    changes laid over it.  A changed cell the default does not have (an
    agent that does not exist in that topology) is an error."""
    base = default_table()
    over = read_overrides()
    out = {a: dict(row) for a, row in base.items()}
    for agent, row in over.items():
        for t, st in row.items():
            if t not in base.get(agent, {}):
                raise ParameterAccessError(
                    f"{OVERRIDES_PATH.name}: {agent} has no cell in topology {t} "
                    f"(dc_pack/pack.yaml)")
            out[agent][t] = st
    return out


def state(agent: str, topology: int) -> str:
    """*agent*'s state in *topology*.  An unregistered topology reads the
    7-agent column, as the pack's text does (engine/pack.py).  An agent with
    no cell is an error: a missing row must not quietly become "none"."""
    t = int(topology) if int(topology) in TOPOLOGIES else 7
    row = table().get(agent)
    if row is None or t not in row:
        raise ParameterAccessError(
            f"dc_pack/pack.yaml parameter_access has no cell for {agent} in "
            f"topology {t}")
    return row[t]


def save_overrides(cells: dict) -> dict[str, dict[int, str]]:
    """Store the Workflow Settings choice.  *cells* is the whole grid as the
    page sends it; only the cells that differ from the pack default are
    written (none -> the file is removed).  Returns what was stored."""
    problems: list[str] = []
    wanted = _normalise(cells, "request", problems)
    base = default_table()
    for agent, row in wanted.items():
        for t in row:
            if t not in base.get(agent, {}):
                problems.append(f"request: {agent} has no cell in topology {t}")
    if problems:
        raise ParameterAccessError("\n".join(problems))
    diff = {a: {t: st for t, st in row.items() if base[a][t] != st}
            for a, row in wanted.items()}
    diff = {a: row for a, row in diff.items() if row}
    with _LOCK:
        if not diff:
            OVERRIDES_PATH.unlink(missing_ok=True)
            return {}
        payload = {a: {str(t): st for t, st in sorted(row.items(), reverse=True)}
                   for a, row in sorted(diff.items())}
        fd, tmp = tempfile.mkstemp(dir=OVERRIDES_PATH.parent,
                                   prefix=".parameter_access.", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
        os.replace(tmp, OVERRIDES_PATH)
    return diff


def reset_overrides() -> None:
    """Back to the pack default."""
    with _LOCK:
        OVERRIDES_PATH.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# What a state means for the prompt
# ---------------------------------------------------------------------------

def prompt_flags(st: str) -> dict[str, bool]:
    """The ``<<IF:…>>`` flags a state sets: ``param_list`` keeps the list
    section, ``param_ranges`` the sentences that say the ranges are given."""
    return {"param_list": st in ("full", "names"), "param_ranges": st == "full"}


def strip_ranges(text: str) -> str:
    """The parameter list without its ``[min; max]`` ranges (state names)."""
    return _RANGE_RE.sub("", text)
