"""Receptionist tool: ``propose_attempt`` — signal the Parameters
Inputs view that a set of 16 parameter values represents the system's
PROPOSED SATISFYING SOLUTION.

Step 9 of the Parameters Inputs redesign — see
``extra_utilities/docs/reference/web_interface_notes.md`` §§3-6 (design rationale)
and §7 step 9 (implementation plan).

What this tool does
-------------------
- Takes the PATH to an attempt's ``parameters.json`` and reads the
  16 values out of that record itself.
- Validates the 16 keys.
- Publishes a ``{type: "params_proposed", values: ...}`` event on
  ``agents.shared.viz_bus``.
- Returns a short status string for the Receptionist's LLM.

WHY A PATH AND NOT VALUES.  The panel shows the user these numbers
literally, so they must be the attempt's OWN recorded numbers.  When the
caller passed a dict, it had to retype 16 values read from
``parameters.json`` a turn earlier, and the only defence against a
transcription slip was a prompt rule forbidding it.  Reading the record
removes the step instead of policing it -- the same move
``generate_and_render_propeller`` already made (see the note at
``tools/generate_mesh/generate_mesh.py:181``).

What this tool does NOT do
--------------------------
- Generate a mesh (use the agent path's ``generate_and_render_propeller``
  for that, OR the live preview's ``/api/preview_mesh`` route).
- Create an attempt folder.
- Modify any agent state or trigger downstream agents.

This is purely a UI-update side-effect.  The web frontend's
``/api/events`` SSE handler picks up the published event and
updates the Parameters Inputs view: non-FIXED sliders turn ORANGE
(PROPOSED state) and move to the proposed value; every row
(including FIXED ones) gets a "PROPOSED VALUE: X" text label so the
user always sees the system's most recent proposal even after
later over-riding it (locked decision §6.F.C2 + §6.F.C3).

When to call vs. NOT call
-------------------------
The Receptionist must ONLY call ``propose_attempt`` when surfacing
an attempt as the SYSTEM'S PROPOSED SATISFYING SOLUTION — i.e. when
the Planner or DCOI has indicated the attempt meets the user's
requirements.  Pair with ``visualize_3d_model`` in the same turn.

NOT to be called when:
- Showing an attempt for INFORMATIONAL reasons only (e.g. the user
  asked "show me the worst one") — the panel must continue showing
  the most recent ACTUAL proposed solution.  Use
  ``visualize_3d_model`` only.
- The system has produced an attempt that does NOT yet satisfy the
  user's requirements (Planner / DCOI still iterating).  Visualize
  is OK; updating the panel is not.

The exact wording for the Receptionist's prompt is in
``agents/receptionist/prompt.md`` (Step 11 of the redesign updates
that file with the new rules).
"""

import json
from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool

from agents.shared.attempts_tool import attempt_label_for_path
from agents.shared.viz_bus import publish
from config import ATTEMPTS_DIR


# Canonical 16-parameter INPUT set (impellerHeight removed — the ring
# height is derived, not proposed).  Duplicated from
# ``tools/generate_mesh/generate_mesh.py::_CANONICAL_PARAM_NAMES``
# rather than imported to keep this tool module independent of the
# mesh-tool's import chain (this tool only signals the UI; it does
# not call RhinoCompute).
_CANONICAL_PARAM_NAMES = frozenset({
    "bladeCount",
    "impellerRadius",
    "impellerThickness",
    "innerThickness",
    "innerMaxPos",
    "innerCamber",
    "innerChord",
    "innerAngle",
    "middlePos",
    "middleChord",
    "middleAngle",
    "outerThickness",
    "outerMaxPos",
    "outerCamber",
    "outerChord",
    "outerAngle",
})


@tool
def propose_attempt(
    parameters_path: Annotated[
        str,
        "ABSOLUTE path to the attempt's ``parameters.json`` — the record "
        "written when the attempt was created, e.g. "
        "``<attempt folder>/parameters.json``.  Take the attempt-folder "
        "path from the hand-off that named the attempt and append the "
        "filename; passing the folder itself also works.  Do NOT pass "
        "parameter VALUES: this tool reads them from the record, so what "
        "the user is shown is always what the attempt actually holds.",
    ],
) -> str:
    """Surface a set of 16 propeller parameter values in the
    Parameters Inputs view as the system's PROPOSED SATISFYING
    SOLUTION.

    Call this AFTER ``visualize_3d_model`` when you have decided
    (or have been told by Planner / DCOI) that a given attempt
    satisfies the user's requirements.  Pass the PATH to that
    attempt's ``parameters.json`` — the tool reads all 16 values out
    of the record, so the panel can only ever show what the attempt
    actually holds.  The frontend marks ``PROPOSED`` on every
    parameter the user has not user-FIXED, and shows "PROPOSED
    VALUE: X" text on every row (including FIXED rows) so the user
    always sees the system's most recent proposal.

    Do NOT call this when showing an attempt for INFORMATIONAL
    reasons only ("show me the worst attempt"), or when the system
    has produced an attempt that does NOT yet satisfy the user's
    requirements.  Use ``visualize_3d_model`` alone in those cases —
    the Parameters Inputs panel must keep showing the most recent
    actual proposed solution.

    Returns a short status string.  Side effect: publishes a
    ``viz_bus`` event ``{type: "params_proposed", values: ...}``
    that the web frontend's SSE handler consumes.
    """
    raw = (parameters_path or "").strip()
    if not raw:
        return ("Error: propose_attempt received no parameters_path.  Pass "
                "the absolute path to the attempt's parameters.json.")
    try:
        target = Path(raw).resolve()
    except Exception as exc:                                  # noqa: BLE001
        return f"Error: propose_attempt — invalid path {raw!r}: {exc}"

    # An attempt FOLDER is what travels in hand-offs, so accept one and
    # append the canonical filename rather than making the caller do it.
    # A path that does not exist AND is not a .json is treated as a folder
    # too, so a wrong folder reports "no parameters.json at <folder>" --
    # naming the real problem -- instead of "<folder> is not
    # parameters.json", which would send the caller to fix the filename.
    if target.is_dir() or (not target.exists()
                           and target.suffix.lower() != ".json"):
        target = target / "parameters.json"
    if target.name != "parameters.json":
        return (f"Error: propose_attempt — {target.name} is not "
                f"parameters.json.  Only an attempt's parameter record can "
                f"be proposed.")
    if not target.is_file():
        return (f"Error: propose_attempt — no parameters.json at {target}.  "
                f"Check the attempt folder path.")

    # Same sandbox rule as visualize_3d_model: only records under
    # attempts/ can reach the user's panel.
    try:
        root = ATTEMPTS_DIR.resolve()
    except OSError:
        root = ATTEMPTS_DIR
    if root != target and root not in target.parents:
        return (f"Error: propose_attempt — {target} is outside the attempts "
                f"directory ({root}).")

    try:
        values = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"Error: propose_attempt — could not read {target}: {exc}"
    if not isinstance(values, dict):
        return (f"Error: propose_attempt — {target} does not contain a JSON "
                f"object (got {type(values).__name__}).")

    # Lenient read: impellerHeight was removed as an input (ring height is
    # derived).  Drop a stray one rather than rejecting the proposal.
    if "impellerHeight" in values:
        values = {k: v for k, v in values.items() if k != "impellerHeight"}

    received = set(values.keys())
    missing = _CANONICAL_PARAM_NAMES - received
    extra = received - _CANONICAL_PARAM_NAMES
    if missing or extra:
        problems: list[str] = []
        if missing:
            problems.append(f"missing: {sorted(missing)}")
        if extra:
            problems.append(f"unknown: {sorted(extra)}")
        return (
            f"Error: propose_attempt rejected {target} — "
            + "; ".join(problems)
        )

    # Coerce all values to float for consistent JSON serialisation.
    # The frontend renders them with the same per-spec precision the
    # sliders use (so 0.05-step middlePos shows as "0.30", not
    # "0.30000000000004"); coercing here keeps the wire payload clean.
    try:
        sanitized = {k: float(v) for k, v in values.items()}
    except (TypeError, ValueError) as exc:
        return (
            f"Error: propose_attempt could not coerce values to "
            f"float — {exc}"
        )

    publish({
        "type":   "params_proposed",
        "values": sanitized,
    })

    label = attempt_label_for_path(target)
    where = f" from {label}" if label else ""
    return (
        f"Surfaced {len(sanitized)} proposed parameter values{where} "
        f"({target}) to the Parameters Inputs view."
    )
