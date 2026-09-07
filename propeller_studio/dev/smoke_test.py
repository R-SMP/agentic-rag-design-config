"""End-to-end smoke test for propeller_studio.

    .venv-studio/Scripts/python -m propeller_studio.dev.smoke_test
    .venv-studio/Scripts/python -m propeller_studio.dev.smoke_test --rhino

Covers the paths that break silently rather than loudly: the airfoil maths
against values that can be checked by hand, the settings merge, both geometry
backends, the render pipeline, and a full sheet in all three formats.  The
RhinoCompute case is opt-in because it needs a running server.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from propeller_studio import params as P
from propeller_studio import pipeline
from propeller_studio import settings as S
from propeller_studio.geometry import airfoil, backends

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  %s %s%s" % ("PASS" if cond else "FAIL", name,
                         ("  -- " + detail) if detail else ""))
    return cond


def test_airfoil():
    print("\n== airfoil maths ==")
    p = dict(P.DEFAULT_PARAMS)
    m = airfoil.section_metrics("inner", p)

    # innerThickness is a PERCENTAGE of the inner chord, so 12 % of a 10 mm
    # chord is nominally 1.2 mm.  The measured peak is 1.00029x that: the NACA
    # 4-digit thickness polynomial's fitted coefficients peak slightly above
    # t/2, which is a property of the aerofoil family and not an error.  The
    # drawing dimensions the ACTUAL geometry, so the tolerance allows for it --
    # but only 0.1 %, so a real scaling bug would still fail here.
    check("inner t max == 12% of 10 mm chord (within NACA polynomial peak)",
          abs(m["max_thickness_mm"] - 1.2) < 1.2 * 1e-3,
          "%.6f mm (%.5fx nominal)" % (m["max_thickness_mm"], m["max_thickness_mm"] / 1.2))

    # The thickness peak is fixed near 30 % chord and does NOT move with
    # innerMaxPos -- that parameter moves the CAMBER crest only.
    check("thickness peak near 30% chord",
          0.29 < m["thickness_station_frac"] < 0.31,
          "%.4f" % m["thickness_station_frac"])
    moved = airfoil.section_metrics("inner", dict(p, innerMaxPos=7))
    check("innerMaxPos does not move the thickness peak",
          abs(moved["thickness_station_frac"] - m["thickness_station_frac"]) < 1e-6)
    check("innerMaxPos DOES move the camber crest",
          abs(moved["camber_station_frac"] - 0.7) < 1e-9,
          "%.3f" % moved["camber_station_frac"])

    # The blade root is at r = 4 mm, not at the centre.
    mid = airfoil.section_metrics("middle", dict(p, middlePos=0.5, impellerRadius=70))
    check("middle radius = 4 + 0.5*(70-4) = 37", abs(mid["radius_mm"] - 37.0) < 1e-9,
          "%.4f mm" % mid["radius_mm"])

    # A zero-camber section has nothing to dimension.
    sym = airfoil.section_metrics("inner", dict(p, innerCamber=0))
    check("zero camber reports has_camber False", not sym["has_camber"])

    # The 2D drawing frame IS the (Y, Z) projection of the placed 3D section.
    p2 = airfoil.build_section_2d("outer", p)
    p3 = airfoil.build_section_3d("outer", p)
    check("2D section == (Y,Z) of the 3D section",
          abs(p2[:, 1] - p3[:, 2]).max() < 1e-9)


def test_settings():
    print("\n== settings ==")
    s = S.resolve({"render": {"width": 999}})
    check("partial merge keeps untouched defaults",
          s["render"]["width"] == 999 and s["render"]["height"] == 1200)
    check("lists replace rather than append",
          S.resolve({"render": {"views": ["top"]}})["render"]["views"] == ["top"])
    try:
        S.resolve({"render": {"lighting": {"preset": "nope"}}})
        check("bad lighting preset rejected", False)
    except S.SettingsError:
        check("bad lighting preset rejected", True)
    try:
        S.resolve({"drawing": {"views": ["sideways"]}})
        check("unknown view name rejected", False)
    except S.SettingsError:
        check("unknown view name rejected", True)
    name, az, el = S.resolve_view({"az": 30, "el": 20})
    check("custom view resolves", (az, el) == (30.0, 20.0))


def test_params():
    print("\n== parameters ==")
    try:
        P.validate(dict(P.DEFAULT_PARAMS, innerChord=99))
        check("out-of-range rejected by default", False)
    except P.ParamError:
        check("out-of-range rejected by default", True)
    ok = P.validate(dict(P.DEFAULT_PARAMS, innerChord=99), strict_range=False)
    check("out-of-range allowed when asked", ok["innerChord"] == 99)
    check("out_of_range() reports it",
          any("innerChord" in n for n in P.out_of_range(ok)))
    missing = dict(P.DEFAULT_PARAMS)
    missing.pop("middleChord")
    try:
        P.validate(missing)
        check("missing key rejected", False)
    except P.ParamError:
        check("missing key rejected", True)


def test_backends(with_rhino):
    print("\n== geometry backends ==")
    g = backends.build(P.DEFAULT_PARAMS, "feg")
    check("feg returns blade/ring/hub",
          {"blade", "ring", "hub"} <= set(g.parts), ", ".join(sorted(g.parts)))
    check("feg blade has bladeCount instances baked",
          g.meta.get("bladeCount") == P.DEFAULT_PARAMS["bladeCount"])
    check("feg sections agree with the Python port",
          g.meta["section_agreement_mm"] < 1e-4,
          "%.2e mm" % g.meta["section_agreement_mm"])
    try:
        backends.build(P.DEFAULT_PARAMS, "nonsense")
        check("unknown backend rejected", False)
    except backends.GeometryError:
        check("unknown backend rejected", True)

    if with_rhino:
        gr = backends.build(P.DEFAULT_PARAMS, "rhino")
        check("rhino returns tagged parts", len(gr.parts) >= 2,
              ", ".join(sorted(gr.parts)))
        lo1, hi1 = g.bounds()
        lo2, hi2 = gr.bounds()
        span = float(max(hi1 - lo1))
        check("rhino and feg agree on overall size to 2%",
              abs(float(max(hi2 - lo2)) - span) / span < 0.02,
              "feg %.2f mm vs rhino %.2f mm" % (span, float(max(hi2 - lo2))))
    else:
        print("  (rhino backend skipped -- pass --rhino with a server running)")


def test_pipeline():
    print("\n== pipeline + sheet ==")
    tmp = Path(tempfile.mkdtemp(prefix="propstudio_"))
    try:
        m = pipeline.run(
            P.DEFAULT_PARAMS,
            {"render": {"views": ["iso"], "width": 480, "height": 360},
             "drawing": {"dpi": 80, "formats": {"png": True, "pdf": True, "svg": True}}},
            out_root=tmp, slug="smoke", title="Smoke test", progress=None,
        )
        out = Path(m["out_dir"])
        check("run folder created", out.is_dir())
        check("render written", (out / "renders" / "iso.png").is_file())
        for fmt in ("png", "pdf", "svg"):
            check("drawing.%s written" % fmt, (out / ("drawing.%s" % fmt)).is_file())
        check("parameters.json written", (out / "parameters.json").is_file())
        check("settings.json written", (out / "settings.json").is_file())
        check("manifest records the backend", m["backend"] == "feg")
        check("sheet states a view scale", bool(m["drawing"]["view_scale"]),
              str(m["drawing"]["view_scale"]))
        check("sheet states a section scale", bool(m["drawing"]["section_scale"]),
              str(m["drawing"]["section_scale"]))

        # Turntable expansion.
        s = S.resolve({"render": {"views": ["top"],
                                  "turntable": {"enabled": True, "count": 4}}})
        check("turntable expands to 1 + 4 views",
              len(pipeline.expand_views(s["render"])) == 5)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    argv = argv or []
    with_rhino = "--rhino" in argv
    test_airfoil()
    test_params()
    test_settings()
    test_backends(with_rhino)
    test_pipeline()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
