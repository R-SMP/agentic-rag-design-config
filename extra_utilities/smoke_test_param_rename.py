"""Smoke-test for the generate_propeller_mesh parameter naming.

Verifies that:
1. ``generate_mesh.py`` imports cleanly.
2. The dict keys passed to RhinoCompute use the camelCase GH-internal
   names (bladeCount, impellerRadius, impellerHeight, ...) — i.e. they
   are an identity mapping with the @tool's keyword arguments, no
   translation layer.
3. Every key in ``parameter_keys.txt`` (PARAMETER_NAMES) matches what
   the dict sends, in both directions.
4. None of the OLD snake_case names (amount_of_blades, thickness_i, ...)
   leak into the dict the tool sends to RhinoCompute.

Run from the project root:
    .venv/Scripts/python.exe extra_utilities/smoke_test_param_rename.py
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Stub out the heavy / network deps so the module imports without
# hitting RhinoCompute or DracoPy at import time.
if "compute_rhino3d" not in sys.modules:
    fake = types.ModuleType("compute_rhino3d")
    fake_gh = types.ModuleType("compute_rhino3d.Grasshopper")
    fake_gh.EvaluateDefinition = lambda *a, **kw: {"values": []}
    fake_util = types.ModuleType("compute_rhino3d.Util")
    fake_util.url = ""
    fake_util.apiKey = ""
    fake.Util = fake_util
    fake.Grasshopper = fake_gh
    sys.modules["compute_rhino3d"] = fake
    sys.modules["compute_rhino3d.Grasshopper"] = fake_gh
    sys.modules["compute_rhino3d.Util"] = fake_util


from tools.generate_mesh import generate_mesh as gm
from agents.shared.prompts import PARAMETER_NAMES


# ---------------------------------------------------------------------
# Read the canonical parameter list from parameter_keys.txt
# ---------------------------------------------------------------------
canonical = PARAMETER_NAMES
print(f"Canonical parameter list ({len(canonical)} entries) — read from parameter_keys.txt:")
for k in canonical:
    print(f"  - {k}")
print()


# ---------------------------------------------------------------------
# Capture the dict that the tool builds by intercepting EvaluateDefinition
# ---------------------------------------------------------------------
captured_param_names: list[str] = []


def _fake_eval(gh_path, input_trees):
    for tree in input_trees:
        captured_param_names.append(tree.data["ParamName"])
    return {"values": []}


sample_args = dict(
    output_dir="C:\\does\\not\\exist\\so_we_short_circuit_validation",
    bladeCount=3,
    impellerRadius=68.0,
    impellerHeight=5.0,
    impellerThickness=3.5,
    innerThickness=11.0,
    innerMaxPos=3,
    innerCamber=3.0,
    innerChord=8.0,
    innerAngle=22.0,
    middlePos=0.55,
    middleChord=22.0,
    middleAngle=14.0,
    outerThickness=10.0,
    outerMaxPos=3,
    outerCamber=2.5,
    outerChord=24.0,
    outerAngle=8.0,
)

with patch.object(gm.gh_compute, "EvaluateDefinition", _fake_eval):
    with patch.object(
        gm,
        "_validate_output_dir",
        lambda raw: (Path(raw), None),
    ):
        result = gm.generate_propeller_mesh.invoke(sample_args)

print(f"Tool returned: {result}")
print()


# ---------------------------------------------------------------------
# Verify the dict keys match the canonical names exactly
# ---------------------------------------------------------------------
print(f"GH ParamNames intercepted ({len(captured_param_names)}):")
for n in captured_param_names:
    print(f"  - {n}")
print()

assert len(captured_param_names) == 17, (
    f"Expected 17 param names, got {len(captured_param_names)}"
)

set_canonical = set(canonical)
set_captured = set(captured_param_names)

missing = set_canonical - set_captured
extra = set_captured - set_canonical

assert not missing, f"BAD: canonical names not sent to GH: {sorted(missing)}"
assert not extra, f"BAD: extra names sent to GH: {sorted(extra)}"

print("PASS — every dict key sent to RhinoCompute is a canonical name,")
print("       and every canonical name appears exactly once.")
print()


# ---------------------------------------------------------------------
# Verify NONE of the OLD snake_case names appear anywhere
# ---------------------------------------------------------------------
old_names = {
    "amount_of_blades", "radius", "height", "thickness_ring",
    "thickness_i", "highpoint_i", "camber_i", "chord_i", "angle_i",
    "distance_middle", "chord_m", "angle_m",
    "thickness_o", "highpoint_o", "camber_o", "chord_o", "angle_o",
}
overlap = set_captured & old_names
assert not overlap, f"BAD: old snake_case names still present: {sorted(overlap)}"
print("PASS — no old snake_case names (amount_of_blades / thickness_i / ...) survive")
print()


# ---------------------------------------------------------------------
# Verify the camelCase names ARE present
# ---------------------------------------------------------------------
expected_camel = {
    "bladeCount", "impellerRadius", "impellerHeight", "impellerThickness",
    "innerThickness", "innerMaxPos", "innerCamber", "innerChord", "innerAngle",
    "middlePos", "middleChord", "middleAngle",
    "outerThickness", "outerMaxPos", "outerCamber", "outerChord", "outerAngle",
}
assert set_captured == expected_camel, (
    f"BAD: captured names {sorted(set_captured)} != expected camelCase set"
)
print("PASS — captured names match the camelCase GH-internal set exactly")
print()

print("Parameter-naming smoke test passed.")
