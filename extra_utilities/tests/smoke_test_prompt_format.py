"""Prompt-format smoke test — catches str.format crash class at template
wiring time.

For every agent each topology (7, 5 and 3) builds -- all of them wire
their TEMPLATE through ``str.format(...)`` at construction -- pull the
assembled TEMPLATE from ``agents.shared.prompts`` and call
``.format_map()`` with a stub mapping that returns ``<stub:KEY>`` for any
requested key.  Each topology runs in its own subprocess, under RAG off,
RAG on, and RAG on with every database tool forced on.

The Database Handler is NOT covered: it assigns its TEMPLATE directly to
``self.system_prompt`` with no ``.format()`` call, so literal ``{}``
patterns in its prompt (e.g. JSON tool-result examples) are harmless at
runtime.

Caught bug classes:

  * Literal ``{}`` in fragment content (positional placeholder when none
    is expected) — ``IndexError``.
  * Literal unmatched ``{`` or ``}`` — ``ValueError``.
  * Genuinely malformed ``{slot}`` syntax — ``KeyError`` / ``ValueError``.

NOT caught:

  * Missing-slot regressions (an agent's ``set_routing_tools`` drops a
    kwarg the template still expects).  ``.format_map`` with a stub
    mapping silently provides a value for every key.

Both Phase 4 production crashes (the literal ``{}`` in one fragment and
the unescaped ``{`` / ``}`` in another) would have been caught here at
PR time.

Run with:

    python extra_utilities/tests/smoke_test_prompt_format.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap so the package import works when this file is run directly.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# ``import agents`` pulls the whole chain, and with it trimesh, pyrender,
# DracoPy and compute_rhino3d.  On any machine without the 3D stack this
# file died at IMPORT and was therefore silently never run -- which is how
# the W45 brace bug reached four prompts with a dedicated guard for it
# sitting right here.  prompt_pdf/bootstrap.py stubs exactly those
# packages and nothing that shapes a prompt.
sys.path.insert(0, str(REPO_ROOT / "extra_utilities" / "prompt_pdf"))
import bootstrap  # noqa: E402
bootstrap.install()

from agents.shared import prompts  # noqa: E402
from workflow_settings import settings as workflow_settings  # noqa: E402

# Every agent that wires its TEMPLATE through ``.format(...)``.  The Database
# Handler is the only genuine exclusion — database_handler.py:1022 assigns the
# template directly to ``self.system_prompt``, so literal ``{}`` patterns in its
# prompt body (e.g. JSON tool-result examples) are harmless at runtime.  If it is
# ever rewired through ``.format()``, add it here.
#
# THE RECEPTIONIST WAS EXCLUDED ON A FALSE PREMISE until F70.  This comment used
# to claim it "assigns the TEMPLATE directly ... with no ``.format()`` call".
# receptionist.py:99-104 DOES call ``.format(user_inputs_dir=...,
# extraction_output_file=...)``.  The comment above that call concedes the
# 7-agent prompt references neither slot so the call is "a no-op there" — but a
# no-op ``.format()`` still raises KeyError on a literal ``{name}`` and
# ValueError on a bare ``{``.  It was the one ``.format()``ed agent with zero
# brace coverage, in the exact place everyone assumed was safe.
# The agents checked are every agent each topology builds
# (``agent_roles.ROSTER``), assembled with _build_template() exactly as the
# agents do.  (prompts.py once also built module-level *_TEMPLATE copies at
# import; those were removed on 2026-10-10.)


class StubKwargs(dict):
    """``.format_map()`` mapping that returns a stub for any missing key.

    Subclassing ``dict`` and overriding ``__missing__`` is the lightest
    way to make ``str.format_map`` swallow any ``{name}`` slot without
    pre-populating the keys — we are testing the format machinery, not
    the values.
    """

    def __missing__(self, key: str) -> str:
        return f"<stub:{key}>"


# Every topology, every agent it builds (TODO F101, closed 2026-10-13).  The
# reduced topologies assemble from their own ``agents/<N>agent/`` overlays,
# which the 7-agent loop never touched: of the four prompts the W45 brace bug
# broke, the topology-5 DC Input Creator and the topology-3 Design Engineer
# were invisible to this test.
#
# One SUBPROCESS per topology, never a loop in one process: ``prompts.py``
# captures DC_INSPECTOR_ENABLED at IMPORT, so a second topology would
# inherit the first one's flag -- the same reason
# extra_utilities/scripts/topology_prompt_snapshot.py spawns one per topology.
#
# Three states per agent, because each ships different text:
#   RAG off       the default; every database fragment is blanked
#   RAG on        the per-agent tools in workflow_settings/database_access.json
#   RAG on, all   every database tool forced on, so no fragment is blanked --
#                 a fragment for a tool the CURRENT profile withholds is still
#                 one toggle away from shipping, and must be checked too.
TOPOLOGIES = (7, 5, 3)
STATES = (("RAG off     ", False, False),
          ("RAG on     ", True, False),
          ("RAG on, all", True, True))


def _child(topology: int) -> int:
    """Brace-check one topology; print one ``FAIL`` line per failure."""
    workflow_settings.SYSTEM_TOPOLOGY = topology
    from agents.shared import agent_roles
    from workflow_settings import database_access
    real_enabled = database_access.is_enabled_for
    stubs = StubKwargs()
    agents = agent_roles.ROSTER[topology]
    failures = 0
    for state, rag, force_all in STATES:
        workflow_settings.RAG_ENABLED = rag
        database_access.is_enabled_for = (
            (lambda *a, **k: True) if force_all else real_enabled)
        for agent in agents:
            label = agent_roles.DISPLAY[agent]
            try:
                tpl = prompts._build_template(agent)
            except Exception as exc:              # noqa: BLE001
                print(f"FAIL [t{topology} {state}] {label}: assembly failed: "
                      f"{type(exc).__name__}: {exc}")
                failures += 1
                continue
            try:
                tpl.format_map(stubs)
            except (IndexError, ValueError, KeyError) as exc:
                print(f"FAIL [t{topology} {state}] {label}: "
                      f"{type(exc).__name__}: {exc}")
                failures += 1
    print(f"@@checked {len(agents) * len(STATES)} failures {failures}")
    return 1 if failures else 0


def main() -> int:
    """Run every topology in its own process and summarise."""
    import subprocess

    total, failed = 0, 0
    for topology in TOPOLOGIES:
        proc = subprocess.run(
            [sys.executable, __file__, "--child", str(topology)],
            capture_output=True, text=True, encoding="utf-8",
        )
        lines = proc.stdout.splitlines()
        for ln in lines:
            if ln.startswith("FAIL"):
                print(ln)
        summary = [ln for ln in lines if ln.startswith("@@checked")]
        if not summary:
            print(f"FAIL [t{topology}] the child crashed:\n"
                  f"{proc.stderr[-2000:]}")
            failed += 1
            continue
        _, n, _, f = summary[-1].split()
        total, failed = total + int(n), failed + int(f)

    if failed:
        return 1
    print(f"OK prompt-format smoke test ({total} templates: topologies 7/5/3 "
          f"x RAG off / on / on-with-every-tool)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        raise SystemExit(_child(int(sys.argv[2])))
    raise SystemExit(main())
