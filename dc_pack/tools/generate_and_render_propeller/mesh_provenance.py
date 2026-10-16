"""The generator's provenance record: which parameters built an attempt's
model (``mesh_params.json``, written by ``tool.build``), and the comparisons
that keep a folder's model, record and parameters coherent (F75 / F75b).

The geometry itself is made by the geometry tools (``feg_geometry``,
``rhino_geometry``; ``engine/pack_tools.make_model``).
"""

import json
import logging
import math
from pathlib import Path

logger = logging.getLogger("mas_agent")

# Canonical 16-parameter INPUT set (the ring height is derived, not an
# input: rhino_geometry/ring_height.py).
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

# F75: attempt-folder coherence.
# DORMANT since the tool began reading parameters.json itself: the values it
# builds from now COME from the record, so they cannot disagree with it and
# this comparison is unreachable via the agent path.  Kept deliberately — it
# still guards any future caller that reintroduces value-passing, and deleting
# a working guard in the same change that removes its trigger is how a safety
# net gets lost twice.  ``mesh_provenance_mismatches`` below is likewise quiet
# now that a mesh cannot precede its record.
# --- F75: attempt-folder coherence -----------------------------------------
# A folder's mesh must come from that folder's own parameters.json.  The
# tolerance below only absorbs float repr / round-trip noise: parameters.json
# is written from the same LLM-authored numbers the tool call carries, so any
# REAL difference is orders of magnitude larger.
_PARAM_REL_TOL = 1e-9
_PARAM_ABS_TOL = 1e-12

# The three integer-typed parameters (declared ``Annotated[int, ...]`` on the
# tool) — compared exactly.  The other 13 are floats.
_INT_PARAM_NAMES = frozenset({"bladeCount", "innerMaxPos", "outerMaxPos"})


# F75b: the mesh-first order.  A mesh may legitimately be built into a folder
# that has no parameters.json yet (the Orchestrator's fallback folder, the
# 3-agent Designer's call ordering).  This sidecar records exactly what
# produced that mesh, so a LATER parameter write cannot label it with numbers
# it did not come from — the same corruption F75 blocks in the params-first
# order, arriving by the other door.
MESH_PROVENANCE_FILE = "mesh_params.json"

def _param_mismatches(out_dir, param_values, record_name="parameters.json"):
    """Compare *param_values* against ``<out_dir>/<record_name>``.

    Returns ``None`` when there is NOTHING TO COMPARE — no parameters.json,
    unreadable, not a JSON object, a non-numeric value, or one of the
    canonical 16 keys missing.  An absent or incomplete record is NOT a
    mismatch: legitimate callers reach this tool before any parameters.json
    exists (e.g. the Orchestrator's fallback folder, or a script that
    generates directly), and F75 is about a folder whose
    record DISAGREES with its mesh — which presupposes a complete record.

    Returns ``[]`` when all 16 agree, else a list of readable differences.

    A legacy ``impellerHeight`` key is ignored: pre-dda1560 folders still
    carry the 17th key.
    """
    params_path = out_dir / record_name
    if not params_path.is_file():
        return None
    try:
        on_disk = json.loads(params_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(
            "generate_mesh: %s unreadable or not valid JSON (%s) — "
            "parameter coherence NOT checked.", params_path, exc,
        )
        return None
    if not isinstance(on_disk, dict):
        return None

    mismatches = []
    for name in sorted(_CANONICAL_PARAM_NAMES):
        recorded = on_disk.get(name)
        if isinstance(recorded, bool) or not isinstance(recorded, (int, float)):
            logger.warning(
                "generate_mesh: %s has no usable '%s' value — parameter "
                "coherence NOT checked.", params_path, name,
            )
            return None
        passed = param_values[name]
        if isinstance(passed, bool) or not isinstance(passed, (int, float)):
            # Defensive: args_schema should have coerced this already.  If it
            # did not, degrade to "proceed" — today's behaviour — never to a
            # false refusal.
            logger.warning(
                "generate_mesh: passed '%s' is %r, not a number — parameter "
                "coherence NOT checked.", name, passed,
            )
            return None
        if name in _INT_PARAM_NAMES:
            same = passed == recorded
        else:
            same = math.isclose(
                float(passed), float(recorded),
                rel_tol=_PARAM_REL_TOL, abs_tol=_PARAM_ABS_TOL,
            )
        if not same:
            mismatches.append(
                f"{name}: you passed {passed}, the folder holds {recorded}"
            )
    return mismatches


def mesh_provenance_mismatches(attempt_dir, param_values):
    """Compare *param_values* against the mesh provenance sidecar.

    Public because the parameter-writing handlers call it before
    writing a record into a folder that may already hold a mesh.

    Returns ``None`` when there is NOTHING TO COMPARE — no sidecar, which is
    every attempt folder built before F75b — so this can never refuse a
    legacy folder.  ``[]`` when the mesh was built from these very values,
    else a list of readable differences.
    """
    return _param_mismatches(Path(attempt_dir), param_values,
                             record_name=MESH_PROVENANCE_FILE)
