"""The parameter-access table, offline: who sees the parameter list.

``engine/parameter_access.py`` gives every agent, in every topology, one of
four states -- full list in its prompt, names only (ranges removed), through
the ``dc_params_list`` tool, or nothing.  The default lives in
``dc_pack/pack.yaml``; Workflow Settings stores changed cells in
``workflow_settings/parameter_access.json``.  Four groups of checks:

1. THE GRID.  ``pack.yaml`` has exactly one cell per agent the topology
   builds (``agents/shared/agent_roles.ROSTER``), plus the Database Handler
   in every topology -- no missing agent, no agent that does not exist.
2. THE PROMPTS.  Every one of those agents' prompt files holds exactly one
   ``<<IF:param_list>>`` region, around its ``$parameter_list`` -- the
   condition for every agent to be able to take every state.
3. EACH STATE.  For every agent, topology and allowed state, the assembled
   prompt shows the list with its ranges (full), without them (names), or not
   at all (tool, none); ``dc_params_list`` is bound for ``tool`` only; no
   ``<<IF`` marker survives.  The Database Handler cannot take ``tool``.
4. THE SETTINGS FILE.  Saving stores only the cells that differ from the
   default, rejects a cell the grid does not have, and resetting removes it.
   Written to a temporary path, never the real one.

Run from the repo root:
    py -3.13 extra_utilities/tests/smoke_test_parameter_access.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "extra_utilities" / "prompt_pdf"))
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
sys.modules["simplejson"] = None          # type: ignore[assignment]
sys.modules["chardet"] = None             # type: ignore[assignment]
import bootstrap                          # noqa: E402

bootstrap.install()

from agents.shared import agent_roles     # noqa: E402
from agents.shared import prompts as P    # noqa: E402
from agents.shared.dc_params_tool import param_tools_for  # noqa: E402
from engine import pack                   # noqa: E402
from engine import parameter_access as PA  # noqa: E402

FAILURES: list[str] = []
_IF_PARAM_LIST_RE = re.compile(r"<<IF:param_list>>(.*?)<</IF:param_list>>", re.DOTALL)


def check(ok: bool, what: str) -> None:
    if not ok:
        FAILURES.append(what)


def _agents(topology: int) -> list[str]:
    return list(agent_roles.roster(topology)) + ["database_handler"]


def check_grid(default: dict) -> None:
    for t in PA.TOPOLOGIES:
        have = {a for a, row in default.items() if t in row}
        want = set(_agents(t))
        check(have == want, f"[GRID] topology {t}: pack.yaml has cells for "
              f"{sorted(have - want)} that the topology does not build, and "
              f"none for {sorted(want - have)}")


def check_prompt_files() -> int:
    n = 0
    for t in PA.TOPOLOGIES:
        P._workflow_settings.SYSTEM_TOPOLOGY = t
        for agent in _agents(t):
            path = P._prompt_path(agent)
            regions = _IF_PARAM_LIST_RE.findall(path.read_text(encoding="utf-8"))
            n += 1
            check(len(regions) == 1 and "$parameter_list" in regions[0],
                  f"[PROMPT] {path.relative_to(ROOT).as_posix()}: needs exactly one "
                  f"<<IF:param_list>> region around $parameter_list "
                  f"(found {len(regions)})")
    return n


def check_states(default: dict) -> int:
    n = 0
    real_read = PA.read_overrides
    try:
        for t in PA.TOPOLOGIES:
            P._workflow_settings.SYSTEM_TOPOLOGY = t
            for agent in _agents(t):
                if t not in default.get(agent, {}):
                    continue          # reported by check_grid
                listing = pack.read("parameter_list", t, agent)
                bare = PA.strip_ranges(listing)
                for st in PA.STATES:
                    where = f"[STATE] topology {t} {agent} = {st}"
                    if st == "tool" and agent in PA.NO_TOOL_AGENTS:
                        continue          # refused: see check_settings_file
                    PA.read_overrides = lambda a=agent, s=st: {a: {t: s}}
                    text = P._build_template(agent)
                    n += 1
                    check("<<IF" not in text and "<</IF" not in text,
                          f"{where}: an <<IF marker survived")
                    if st == "full":
                        check(listing in text, f"{where}: the list is missing")
                    elif st == "names":
                        check(bare in text and (bare == listing or listing not in text),
                              f"{where}: the list without ranges is missing, "
                              f"or the ranges are still there")
                    else:
                        first = bare.strip().splitlines()[0]
                        check(first not in text, f"{where}: the list is still there")
                    tools = [x.name for x in param_tools_for(agent)]
                    check(tools == (["dc_params_list"] if st == "tool" else []),
                          f"{where}: dc_params_list bound = {tools}")
    finally:
        PA.read_overrides = real_read
    return n


def check_settings_file(default: dict) -> None:
    real_path = PA.OVERRIDES_PATH
    with tempfile.TemporaryDirectory() as tmp:
        PA.OVERRIDES_PATH = Path(tmp) / "parameter_access.json"
        try:
            grid = {a: {str(t): s for t, s in row.items()} for a, row in default.items()}
            check(PA.save_overrides(grid) == {} and not PA.OVERRIDES_PATH.exists(),
                  "[FILE] saving the default grid stored something")
            grid["user_input_inspector"]["7"] = "full"
            stored = PA.save_overrides(grid)
            check(stored == {"user_input_inspector": {7: "full"}},
                  f"[FILE] saved {stored}, expected only the changed cell")
            check(PA.table()["user_input_inspector"][7] == "full"
                  and PA.table()["user_input_inspector"][5] == default["user_input_inspector"][5],
                  "[FILE] the changed cell is not laid over the default")
            for bad in ({"user_input_inspector": {"3": "full"}},
                        {"tool_caller": {"7": "everything"}},
                        {"ghost_agent": {"7": "full"}},
                        {"database_handler": {"7": "tool"}}):
                try:
                    PA.save_overrides(bad)
                    check(False, f"[FILE] {bad} was accepted")
                except PA.ParameterAccessError:
                    pass
            PA.reset_overrides()
            check(not PA.OVERRIDES_PATH.exists() and PA.table() == default,
                  "[FILE] reset did not go back to the default")
        finally:
            PA.OVERRIDES_PATH = real_path


def main() -> int:
    default = PA.default_table()
    check_grid(default)
    n_files = check_prompt_files()
    n_builds = check_states(default)
    check_settings_file(default)
    print(f"{sum(len(r) for r in default.values())} cells; {n_files} prompt files; "
          f"{n_builds} prompts assembled across the four states")
    if FAILURES:
        print(f"\nFAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("\nPASS - the grid matches the agents, every prompt can take every "
          "state, each state shows what it should, and the settings file "
          "stores only changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
