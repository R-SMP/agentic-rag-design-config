"""Drift guard: cross-check tools/generate_mesh/ring_height.fitted_ring_height
against the REAL web/feg modules (via Node), proving the server-side derived
ring height is bit-identical to the in-browser FEG 3D preview.

The Python port and the FEG JS are two implementations of the same geometry;
this test is what keeps them from drifting.  It builds hundreds of param sets
(random across the outer-param ranges + all-min/all-max corners + integer
samples), runs the real web/feg via Node to get each fittedHeight, and asserts
the Python port matches within 1e-9 mm.

Dev/local only: needs Node + ``npm install three`` (node_modules/three).  If
either is missing it SKIPS (exit 0) with a message — the port itself is pure
Python and never needs Node on the server.

Usage:  python extra_utilities/smoke_test_ring_height.py
"""
import importlib.util
import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FEG_DIR = REPO_ROOT / "web" / "feg"
TOL = 1e-9

# Load the port BY FILE PATH so we don't trigger tools/__init__'s eager import
# of the whole agents stack (which needs langchain, absent in a bare env).
_spec = importlib.util.spec_from_file_location(
    "ring_height", REPO_ROOT / "tools" / "generate_mesh" / "ring_height.py")
_rh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rh)  # type: ignore[union-attr]
fitted_ring_height = _rh.fitted_ring_height

# Node reference: the REAL web/feg outer-section + ring computation.  %FEG% is
# replaced with a JSON-quoted absolute path to web/feg.
_NODE_REF = r'''
import { pathToFileURL } from 'node:url';
import { readFileSync } from 'node:fs';
const FEG = %FEG%;
const { buildPlacedSection } = await import(pathToFileURL(`${FEG}/blade.js`).href);
const { computeRingDimensions } = await import(pathToFileURL(`${FEG}/ring.js`).href);
const { CONSTANTS } = await import(pathToFileURL(`${FEG}/constants.js`).href);
const sets = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const out = sets.map((p) => {
  const outerSection = buildPlacedSection({
    thickness: p.outerThickness, highPt: p.outerMaxPos, camber: p.outerCamber,
    chord: p.outerChord, angle: p.outerAngle, radius: p.impellerRadius,
    countI: CONSTANTS.countI, project: true, projectionRadius: p.impellerRadius,
  });
  return computeRingDimensions(outerSection, CONSTANTS.clearance).fittedHeight;
});
process.stdout.write(JSON.stringify(out));
'''

RANGES = {
    "outerThickness": (3, 24), "outerMaxPos": (2, 8), "outerCamber": (0, 9),
    "outerChord": (10, 30), "outerAngle": (2, 25),
    "impellerRadius": (60, 80),  # only used by the Node outer-section build
}


def _build_param_sets():
    random.seed(1234)

    def rnd(a, b):
        return a + random.random() * (b - a)

    sets = [{k: rnd(a, b) for k, (a, b) in RANGES.items()} for _ in range(500)]
    sets.append({k: a for k, (a, b) in RANGES.items()})   # all-min corner
    sets.append({k: b for k, (a, b) in RANGES.items()})   # all-max corner
    for _ in range(50):                                   # integer samples
        sets.append({k: float(random.randint(a, b)) for k, (a, b) in RANGES.items()})
    return sets


def main() -> int:
    if shutil.which("node") is None:
        print("SKIP: node not found — dev-only drift guard (the port is pure Python).")
        return 0
    if not (REPO_ROOT / "node_modules" / "three").is_dir():
        print("SKIP: node_modules/three missing — run `npm install three` to enable this guard.")
        return 0

    sets = _build_param_sets()
    node_src = _NODE_REF.replace(
        "%FEG%", json.dumps(str(FEG_DIR).replace("\\", "/")))
    with tempfile.TemporaryDirectory() as td:
        ref = Path(td) / "ref.mjs"
        ref.write_text(node_src, encoding="utf-8")
        pf = Path(td) / "params.json"
        pf.write_text(json.dumps(sets), encoding="utf-8")
        proc = subprocess.run(
            ["node", str(ref), str(pf)],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
    if proc.returncode != 0:
        print("SKIP: could not run the FEG reference via Node "
              "(three not resolvable?):\n  " + proc.stderr.strip()[:400])
        return 0

    feg = json.loads(proc.stdout)
    port = [fitted_ring_height(p) for p in sets]
    diffs = [abs(a - b) for a, b in zip(feg, port)]
    maxdiff = max(diffs)
    print(f"compared {len(sets)} param sets; max |FEG - port| = {maxdiff:.3e} mm")

    if maxdiff >= TOL:
        i = diffs.index(maxdiff)
        print(f"FAIL: port drifted from the FEG preview.\n"
              f"  worst set: {sets[i]}\n"
              f"  FEG {feg[i]!r} vs port {port[i]!r}")
        return 1
    print(f"PASS: ring_height port == FEG preview within {TOL:g} mm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
