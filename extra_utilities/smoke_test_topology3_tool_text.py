"""The topology-3 tool overlay says what it claims to say.

``agents/topology3/tool_text.py`` asserts of itself that nothing in it is
newly authored: every value is either copied VERBATIM from
``agents/topology5/tool_text.py`` or derived from topology 3's roster.  That
claim is only worth something if something checks it — a transcription slip
in a tool description does not raise, it just quietly hands the model a
different instruction.

So this suite proves each claim in the shape the claim is made:

* **verbatim** — byte-identical to the topology-5 value it names;
* **superset wins** — the copied value CONTAINS the other parent's, so the
  copy really is the union rather than a choice between them;
* **roster-derived** — names every agent this topology builds and no agent it
  does not, checked against the hub's own ``_agents_by_key`` literal;
* **deliberately absent** — the one genuine merge is still absent, and the
  resolver therefore still returns exactly what it returned with no overlay
  at all.

It also checks the overlay is REACHED: an overlay module that is written but
never registered in ``_OVERLAY_MODULE_BY_TOPOLOGY`` is silently inert, which
is the same class of defect as an unregistered scoped fragment.

    py -3.13 extra_utilities/smoke_test_topology3_tool_text.py
"""

import sys
from pathlib import Path

sys.modules["simplejson"] = None
sys.modules["chardet"] = None
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "extra_utilities" / "prompt_pdf"))
import bootstrap                                      # noqa: E402
bootstrap.install()

from workflow_settings import settings as S           # noqa: E402
from agents.topology3 import tool_text as T3          # noqa: E402
from agents.topology5 import tool_text as T5          # noqa: E402
from agents.shared import topology as TOPO            # noqa: E402

sys.path.insert(0, str(ROOT / "extra_utilities"))
from hub_registry import registry_keys_from_source    # noqa: E402

FAILS: list[str] = []


def check(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label
          + (f"   {extra}" if extra and not cond else ""))
    if not cond:
        FAILS.append(label)


BUILT = registry_keys_from_source(ROOT / "agents" / "planner3" / "planner3.py")

print("-- VERBATIM: copied from topology 5, byte for byte --")
check("USE_DEFAULT", T3.USE_DEFAULT == T5.USE_DEFAULT)
for k in ("planner", "receptionist"):
    check(f"USE_BY_AGENT[{k!r}]",
          T3.USE_BY_AGENT.get(k) == T5.USE_BY_AGENT.get(k))
check("VIEW_IMAGES_PATHS_DEFAULT",
      T3.VIEW_IMAGES_PATHS_DEFAULT == T5.VIEW_IMAGES_PATHS_DEFAULT)
check("READ_INPUTS_DOC_PLANNER",
      T3.READ_INPUTS_DOC_PLANNER == T5.READ_INPUTS_DOC_PLANNER)
for k in ("call_planner", "call_receptionist"):
    check(f"TOOL_DESCRIPTIONS[{k!r}]",
          T3.TOOL_DESCRIPTIONS.get(k) == T5.TOOL_DESCRIPTIONS.get(k))

print()
print("-- SUPERSET WINS: the copy is the union, not a choice --")
ra = T3.VIEW_IMAGES_PATHS_BY_AGENT["requirements_analyst"]
check("view_images paths == the DCOI's wording verbatim",
      ra == T5.VIEW_IMAGES_PATHS_BY_AGENT["dc_output_inspector"])
check("...and it CONTAINS the UII's, so nothing was dropped",
      T5.VIEW_IMAGES_PATHS_BY_AGENT["user_input_inspector"] in ra,
      T5.VIEW_IMAGES_PATHS_BY_AGENT["user_input_inspector"])

print()
print("-- ROSTER-DERIVED: names what this topology builds, and nothing else --")
GONE = ("orchestrator", "dc_input_inspector", "user_input_inspector",
        "dc_input_creator", "tool_caller", "dc_output_inspector")
hist = T3.READ_AGENT_HISTORY_DESCRIPTION
valid = hist.split("Valid agents:", 1)[1].split(".", 1)[0]
for k in sorted(BUILT):
    check(f"read_agent_history advertises {k!r}", k in valid, valid)
for k in GONE:
    check(f"read_agent_history does NOT advertise the retired {k!r}",
          k not in valid, valid)

fb = T3.SUBMIT_FEEDBACK_DISPATCH_DOC
for k in ("receptionist", "design_engineer", "requirements_analyst"):
    check(f"submit_feedback_dispatch offers {k!r}", f'``"{k}"``' in fb)
check("submit_feedback_dispatch does NOT offer the hub (it is the splitter)",
      '``"planner"``' not in fb)
for k in GONE:
    check(f"submit_feedback_dispatch does NOT offer the retired {k!r}",
          f'``"{k}"``' not in fb)

check("TOOL_DESCRIPTIONS covers exactly the four call_* tools of this roster",
      set(T3.TOOL_DESCRIPTIONS) == {f"call_{k}" for k in BUILT},
      sorted(T3.TOOL_DESCRIPTIONS))

print()
print("-- BOTH merged agents now have a read_user_inputs doc --")
# Stage 8 deliberately left the Requirements Analyst out, because its two
# parents disagreed about how to FIND the directory.  Round 1 of Stage 9
# settled that: there is no extraction, so both routes name the same folder.
S.SYSTEM_TOPOLOGY = 3
from agents.shared.user_inputs_tool import (          # noqa: E402
    READ_INPUTS_DOC_DEFAULT, read_inputs_doc)
for _k in ("requirements_analyst", "design_engineer", "planner"):
    check(f"{_k} has its own doc, not the shared default",
          _k in T3.READ_INPUTS_DOC_BY_AGENT
          and read_inputs_doc(_k) != READ_INPUTS_DOC_DEFAULT)
# The one difference between the two merged agents, and it is the point:
# only the agent that can OPEN an image is offered paths.
check("the Requirements Analyst is offered image PATHS",
      "with their paths" in read_inputs_doc("requirements_analyst"))
check("the Design Engineer is offered image NAMES and told it cannot see",
      "the NAMES of the reference images" in read_inputs_doc("design_engineer")
      and "you cannot see them" in read_inputs_doc("design_engineer"))
check("...and is NOT handed paths it could not use",
      "with their paths" not in read_inputs_doc("design_engineer"))

print()
print("-- REACHED: a written-but-unregistered overlay is silently inert --")
S.SYSTEM_TOPOLOGY = 3
check("overlay_value resolves the topology-3 table",
      TOPO.overlay_value("TOOL_DESCRIPTIONS", {}) is T3.TOOL_DESCRIPTIONS)
S.SYSTEM_TOPOLOGY = 5
check("topology 5 still resolves ITS own table",
      TOPO.overlay_value("TOOL_DESCRIPTIONS", {}) is T5.TOOL_DESCRIPTIONS)
S.SYSTEM_TOPOLOGY = 7
_sentinel: dict = {}
check("topology 7 still takes the shared value, unchanged",
      TOPO.overlay_value("TOOL_DESCRIPTIONS", _sentinel) is _sentinel)

print()
if FAILS:
    print(f"{len(FAILS)} FAILURE(S): {FAILS}")
    sys.exit(1)
print("ALL PASS — the overlay is verbatim where it claims to be, correct "
      "where it is derived, and actually reached.")
sys.exit(0)
