"""No model-facing text may mention OCR when OCR is switched off.

Why this exists
---------------
Turning OCR off already removes the ``reread_text_regions`` tool and the
``extract_text`` flag, but two pieces of TEXT survived the switch: the
``crop_regions`` clause of ``view_images`` ("unrelated to the numbered
TEXT regions OCR reports") and the ``read_user_inputs`` clause promising
"its OCR-recognised text".  A run with OCR off was still telling the
model about text recognition it could not perform.

Both fixes live in ``agents/shared/user_inputs_tool.py``, and one of
them is a ``str.replace`` of a sentence that must match byte-for-byte in
TWO places -- the shared ``READ_INPUTS_DOC_UII`` and the topology-5
overlay's own copy in ``agents/topology5/tool_text.py``.  If either copy
is reworded, the replace silently stops matching and the OCR text comes
back with nothing to flag it.  That is what this test is for.

It also pins the positive direction: with OCR ON the descriptions MUST
still mention it, so a fix that simply deleted the text everywhere would
fail here rather than pass quietly.

Run
---
    py -3.13 extra_utilities/smoke_test_ocr_descriptions.py

Needs no API key: it builds tool objects, never agents.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "extra_utilities" / "prompt_pdf"))
sys.modules["simplejson"] = None          # type: ignore[assignment]
sys.modules["chardet"] = None             # type: ignore[assignment]
import bootstrap                          # noqa: E402
bootstrap.install()
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "extra_utilities"))

import workflow_settings.settings as S    # noqa: E402
from hub_registry import built_here       # noqa: E402

FAILS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILS.append(label)


def descriptions(agents: list[str]) -> dict:
    """Every description the builders can produce, keyed by (agent, tool).

    Deliberately a SUPERSET of what is actually bound.  Only the UII, the
    DCII and the DCOI receive ``view_images`` / ``reread_text_regions``,
    and only the UII, DCII, DCOI and Planner receive
    ``read_user_inputs``; the Orchestrator, Receptionist, Tool Caller and
    DC Input Creator bind none of them.  Asking the builders for every
    agent is conservative -- it can only over-report, never miss a real
    leak -- and it needs no API key, unlike building a hub.  Do not read
    a row here as proof that the agent holds that tool.

    Reimported per call so the OCR gate is re-read: the tool builders
    resolve it at build time, but ``ocr_access`` caches the master switch
    at import.
    """
    for m in [m for m in sys.modules
              if m.startswith(("agents.shared.user_inputs_tool",
                               "workflow_settings.ocr_access"))]:
        del sys.modules[m]
    from agents.shared.user_inputs_tool import (   # noqa: E402
        build_user_inputs_tools, build_read_user_inputs, read_inputs_doc,
    )
    out = {}
    for a in agents:
        for t in build_user_inputs_tools(a):
            out[(a, getattr(t, "name", "?"))] = getattr(t, "description", "") or ""
        rd = build_read_user_inputs(doc=read_inputs_doc(a))
        out[(a, "read_user_inputs")] = getattr(rd, "description", "") or ""
    return out


OCR_WORDS = re.compile(r"OCR|text region", re.IGNORECASE)

for topo in (7, 5):
    S.SYSTEM_TOPOLOGY = topo
    # Every agent the hub builds -- see descriptions() on why this is a
    # superset of the agents that actually hold the image tools.
    agents = sorted(built_here())
    print(f"\n-- topology {topo}: {len(agents)} agents ------------------------")
    check(f"topology {topo}: the hub roster resolves", bool(agents),
          ", ".join(agents))

    S.OCR_ENABLED = False
    off = descriptions(agents)
    leaks = {k: v for k, v in off.items() if OCR_WORDS.search(v)}
    check(f"topology {topo}: no description mentions OCR when it is OFF",
          not leaks,
          "; ".join(f"{a}/{t}" for a, t in sorted(leaks)) or "clean")
    for (a, t), v in sorted(leaks.items()):
        for m in OCR_WORDS.finditer(v):
            frag = " ".join(v[max(0, m.start() - 70):m.end() + 70].split())
            print(f"        {a}/{t}: ...{frag}...")
            break

    # The reread tool must be gone, not merely quiet about itself.
    check(f"topology {topo}: reread_text_regions is unbound when OCR is OFF",
          not any(t == "reread_text_regions" for _, t in off))

    S.OCR_ENABLED = True
    on = descriptions(agents)
    # Positive direction: deleting the text outright would pass the check
    # above and quietly cost every normal run its OCR documentation.
    said = [k for k, v in on.items() if OCR_WORDS.search(v)]
    check(f"topology {topo}: OCR IS still documented when it is ON",
          bool(said), f"{len(said)} description(s) mention it")

    # And the swap must actually be doing something on the agents that
    # have OCR -- if both sides were identical the test would be vacuous.
    moved = [k for k in set(on) & set(off) if on[k] != off[k]]
    check(f"topology {topo}: turning OCR off actually changes text",
          bool(moved),
          ", ".join(f"{a}/{t}" for a, t in sorted(moved)))

S.OCR_ENABLED = True
S.SYSTEM_TOPOLOGY = 7

print()
if FAILS:
    print(f"{len(FAILS)} FAILURE(S): {FAILS}")
    sys.exit(1)
print("ALL PASS")
sys.exit(0)
