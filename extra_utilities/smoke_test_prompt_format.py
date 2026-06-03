"""Prompt-format smoke test — catches str.format crash class at template
wiring time.

For each of the 7 chain agents that wire their TEMPLATE through
``str.format(...)`` at agent-construction time (Orchestrator, Planner,
UII, DCIC, DCII, Tool Caller, DCOI), pull the assembled TEMPLATE from
``agents.shared.prompts`` and call ``.format_map()`` with a stub mapping
that returns ``<stub:KEY>`` for any requested key.

The Receptionist and Database Handler are NOT covered — they assign
their TEMPLATE directly to ``self.system_prompt`` with no ``.format()``
call, so literal ``{}`` patterns in their prompts (e.g. JSON tool-result
examples in the DH prompt) are harmless at runtime.  See the comment
above ``TEMPLATE_NAMES`` below.

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

    python extra_utilities/smoke_test_prompt_format.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap so the package import works when this file is run directly.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Force ``agents`` to import before any ``tools`` reference — see the
# session bootstrap pattern in extra_utilities/db_design/smoke_test_*.
import agents  # noqa: F401, E402
from agents.shared import prompts  # noqa: E402

# The 7 chain agents that wire their TEMPLATE through ``.format(...)`` at
# agent-construction time (see ``set_routing_tools`` in each module).  The
# Receptionist and Database Handler are intentionally EXCLUDED — both
# assign the TEMPLATE directly to ``self.system_prompt`` with no
# ``.format()`` call, so literal ``{}`` patterns in their prompt bodies
# (e.g. JSON tool-result examples in the DH prompt) are harmless at
# runtime.  If you ever rewire either of these two through ``.format()``,
# re-add them here so the regression-catcher covers them.
TEMPLATE_NAMES = (
    "ORCHESTRATOR",
    "PLANNER",
    "UII",
    "DCIC",
    "DCII",
    "TOOL_CALLER",
    "DCOI",
)


class StubKwargs(dict):
    """``.format_map()`` mapping that returns a stub for any missing key.

    Subclassing ``dict`` and overriding ``__missing__`` is the lightest
    way to make ``str.format_map`` swallow any ``{name}`` slot without
    pre-populating the keys — we are testing the format machinery, not
    the values.
    """

    def __missing__(self, key: str) -> str:
        return f"<stub:{key}>"


def main() -> int:
    stubs = StubKwargs()
    failures: list[tuple[str, str, str]] = []
    for name in TEMPLATE_NAMES:
        tpl = getattr(prompts, f"{name}_TEMPLATE")
        try:
            tpl.format_map(stubs)
        except (IndexError, ValueError, KeyError) as exc:
            failures.append((name, type(exc).__name__, str(exc)))

    for name, etype, msg in failures:
        print(f"FAIL {name}: {etype}: {msg}")

    if failures:
        return 1
    print(f"OK prompt-format smoke test ({len(TEMPLATE_NAMES)} templates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
