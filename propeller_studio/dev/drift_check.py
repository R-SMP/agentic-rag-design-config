"""Drift guard for the vendored copies.

``propeller_studio`` is self-contained on purpose -- it carries its own copy of
``web/feg/*.js`` and its own port of the airfoil maths -- so that lifting it into
a standalone repository is a move rather than a rewrite.  The cost of a copy is
drift, and this script is what makes the copy honest:

1. **Byte-compare** the vendored ``geometry/feg_js/*.js`` against ``web/feg/``
   in the parent repository, when that repository is present.
2. **Numerically compare** the Python section maths against the JS the exporter
   actually runs, over random in-range parameter sets.

Run it after touching either copy:

    .venv-studio/Scripts/python -m propeller_studio.dev.drift_check
"""

from __future__ import annotations

import hashlib
import math
import random
import sys
from pathlib import Path

import numpy as np

from propeller_studio import params as P
from propeller_studio.geometry import airfoil, backends

HERE = Path(__file__).resolve().parent
VENDORED = HERE.parent / "geometry" / "feg_js"
UPSTREAM = HERE.parents[1] / "web" / "feg"

TOL_MM = 1e-4          # float32 in the three.js BufferAttribute dominates this

# The ring is a swept ELLIPSE sampled at M points, so the built mesh never quite
# reaches the analytic semi-axis: the extreme Z is hit only if a sample lands
# exactly at phi = 90 deg.  Comparing the analytic fitted height against the
# mesh's Z extent without this factor reports a ~0.03 mm "drift" that is pure
# discretisation -- which is how a correct port gets blamed for a rounding rule.
_RING_M = max(24, airfoil.COUNT_I * 2)
RING_SAMPLING_FACTOR = max(abs(math.sin(2 * math.pi * i / _RING_M)) for i in range(_RING_M))


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def check_vendored_js():
    """Byte-compare the vendored JS against the upstream tree."""
    print("== vendored web/feg copy ==")
    if not UPSTREAM.is_dir():
        print("  upstream %s not present -- standalone checkout, skipping." % UPSTREAM)
        return True
    ok = True
    for f in sorted(VENDORED.glob("*.js")):
        up = UPSTREAM / f.name
        if not up.is_file():
            print("  MISSING upstream: %s" % f.name)
            ok = False
            continue
        a, b = _sha(f), _sha(up)
        same = a == b
        ok = ok and same
        print("  %-14s %s  vendored %s  upstream %s"
              % (f.name, "OK  " if same else "DRIFT", a, b))
    extra = {p.name for p in UPSTREAM.glob("*.js")} - {p.name for p in VENDORED.glob("*.js")}
    if extra:
        print("  (upstream also has %s -- not part of the propeller.js dependency "
              "closure, deliberately not vendored)" % ", ".join(sorted(extra)))
    return ok


def random_params(rng):
    out = {}
    for spec in P.PARAM_SPECS:
        v = rng.uniform(spec.lo, spec.hi)
        out[spec.name] = int(round(v)) if spec.integer else round(v, 4)
    return out


def check_python_vs_js(n=25, seed=11):
    """Compare the Python section port against the JS the exporter runs."""
    print("\n== Python airfoil port vs web/feg via Node (%d random sets) ==" % n)
    rng = random.Random(seed)
    worst_sec = 0.0
    worst_bounds = 0.0
    failures = 0
    for i in range(n):
        p = random_params(rng)
        try:
            geom = backends.build(p, "feg")
        except backends.GeometryError as exc:
            print("  set %d: geometry FAILED: %s" % (i, exc))
            failures += 1
            continue
        worst_sec = max(worst_sec, float(geom.meta.get("section_agreement_mm", 0.0)))

        # The ring is fitted to the outer section, so the Python-derived height
        # must match the ring part the JS actually built.
        ring = geom.parts.get("ring")
        if ring is not None:
            z = ring.vertices[:, 2]
            js_h = float(z.max() - z.min())
            py_h = airfoil.fitted_ring_height(p) * RING_SAMPLING_FACTOR
            worst_bounds = max(worst_bounds, abs(js_h - py_h))

    print("  max section disagreement : %.3e mm" % worst_sec)
    print("  max ring-height disagreement: %.3e mm  (analytic height x %.6f "
          "sampling factor)" % (worst_bounds, RING_SAMPLING_FACTOR))
    ok = failures == 0 and worst_sec < TOL_MM and worst_bounds < TOL_MM
    print("  %s (tolerance %.0e mm; three.js stores positions as float32, so a "
          "few 1e-6 mm is expected and fine)" % ("OK" if ok else "DRIFT", TOL_MM))
    return ok


def main(argv=None):
    n = 25
    if argv:
        try:
            n = int(argv[0])
        except ValueError:
            pass
    ok = check_vendored_js()
    ok = check_python_vs_js(n) and ok
    print("\n%s" % ("All drift checks passed." if ok else "DRIFT DETECTED -- see above."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
