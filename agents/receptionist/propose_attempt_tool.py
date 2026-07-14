"""Receptionist tool: ``propose_attempt`` — signal the Parameters
Inputs view that a set of 16 parameter values represents the system's
PROPOSED SATISFYING SOLUTION.

Step 9 of the Parameters Inputs redesign — see
``extra_utilities/web_interface_notes.md`` §§3-6 (design rationale)
and §7 step 9 (implementation plan).

What this tool does
-------------------
- Validates the 16-key parameter dict.
- Publishes a ``{type: "params_proposed", values: ...}`` event on
  ``agents.shared.viz_bus``.
- Returns a short status string for the Receptionist's LLM.

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

from typing import Annotated

from langchain_core.tools import tool

from agents.shared.viz_bus import publish


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
    values: Annotated[
        dict[str, float],
        "Dict mapping ALL 16 canonical propeller parameter names "
        "(bladeCount / impellerRadius / impellerThickness / "
        "innerThickness / innerMaxPos / innerCamber / innerChord / "
        "innerAngle / middlePos / middleChord / middleAngle / "
        "outerThickness / outerMaxPos / outerCamber / outerChord / "
        "outerAngle) to their proposed numeric values.  All 16 keys "
        "MUST be present.  The outer-ring height is DERIVED, not an "
        "input — do not include it.",
    ],
) -> str:
    """Surface a set of 16 propeller parameter values in the
    Parameters Inputs view as the system's PROPOSED SATISFYING
    SOLUTION.

    Call this AFTER ``visualize_3d_model`` when you have decided
    (or have been told by Planner / DCOI) that a given attempt
    satisfies the user's requirements.  Pass the FULL 16-parameter
    dict — the frontend marks ``PROPOSED`` on every parameter the
    user has not user-FIXED, and shows "PROPOSED VALUE: X" text on
    every row (including FIXED rows) so the user always sees the
    system's most recent proposal.

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
    if not isinstance(values, dict):
        return (
            f"Error: propose_attempt received non-dict values "
            f"({type(values).__name__}); expected a 16-key dict."
        )

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
            "Error: propose_attempt rejected — " + "; ".join(problems)
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

    return (
        f"Surfaced {len(sanitized)} proposed parameter values to the "
        f"Parameters Inputs view."
    )
