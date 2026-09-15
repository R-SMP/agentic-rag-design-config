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
# (label, agent_dir_name).  The dir name is new: main() now ASSEMBLES each
# template with _build_template() instead of reading the module-level
# *_TEMPLATE constants, because those are built at import time
# (prompts.py:1190-1198) and so are frozen at whatever RAG_ENABLED was.
TEMPLATES = (
    ("RECEPTIONIST", "receptionist"),
    ("ORCHESTRATOR", "orchestrator"),
    ("PLANNER",      "planner"),
    ("UII",          "user_input_inspector"),
    ("DCIC",         "dc_input_creator"),
    ("DCII",         "dc_input_inspector"),
    ("TOOL_CALLER",  "tool_caller"),
    ("DCOI",         "dc_output_inspector"),
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
    """Brace-check every ``.format()``ed template under RAG OFF **and** ON.

    Both states ship, and they assemble DIFFERENT text: with RAG off,
    ``_DBA_TOOL_SLOTS`` blanks every ``database_search`` / ``retrieve_*``
    fragment, so checking only the shipped default leaves that whole
    fragment tree unverified -- which is exactly what let the W45 brace
    through.  Verified: with the brace re-introduced this returns 1 and
    names ``[RAG on ] DCIC``; under RAG off alone it returns 0.
    """
    stubs = StubKwargs()
    failures: list[tuple[str, str, str, str]] = []
    original_rag = getattr(workflow_settings, "RAG_ENABLED", False)
    try:
        for rag in (False, True):
            workflow_settings.RAG_ENABLED = rag
            state = "RAG on " if rag else "RAG off"
            for label, agent_dir in TEMPLATES:
                try:
                    tpl = prompts._build_template(agent_dir)
                except Exception as exc:              # noqa: BLE001
                    failures.append((state, label, type(exc).__name__,
                                     f"assembly failed: {exc}"))
                    continue
                try:
                    tpl.format_map(stubs)
                except (IndexError, ValueError, KeyError) as exc:
                    failures.append((state, label, type(exc).__name__,
                                     str(exc)))
    finally:
        workflow_settings.RAG_ENABLED = original_rag

    for state, label, etype, msg in failures:
        print(f"FAIL [{state}] {label}: {etype}: {msg}")

    if failures:
        return 1
    print(f"OK prompt-format smoke test "
          f"({len(TEMPLATES)} templates x RAG off/on)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
