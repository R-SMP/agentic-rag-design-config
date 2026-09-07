"""One run: parameters + settings -> a self-describing output folder.

A run folder holds everything needed to understand or reproduce it: the
renders, the drawing sheet, the exact parameters, the exact settings, which
backend actually built the geometry, and a manifest tying them together.  That
completeness is the point -- a folder of PNGs whose settings you have forgotten
is a folder you cannot trust six months later.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import time
from pathlib import Path

from PIL import Image

from propeller_studio import params as P
from propeller_studio import settings as S
from propeller_studio.drawing import sheet as SHEET
from propeller_studio.geometry import backends
from propeller_studio.render import scene

DEFAULT_OUT_ROOT = Path(__file__).resolve().parent / "out"

_SLUG_OK = re.compile(r"[^a-zA-Z0-9_.-]+")


def slugify(text, fallback="run"):
    s = _SLUG_OK.sub("-", str(text or "")).strip("-")
    return s[:60] or fallback


def expand_views(render_settings):
    """The full list of view specs, named/custom plus any turntable frames."""
    views = list(render_settings["views"])
    tt = render_settings.get("turntable") or {}
    if tt.get("enabled"):
        count = max(1, int(tt.get("count", 12)))
        el = float(tt.get("elevation", 20.0))
        for i in range(count):
            az = 360.0 * i / count
            views.append({"name": "turntable_%02d" % i, "az": az, "el": el})
    return views


def run(raw_params, overrides=None, *, out_root=None, slug=None, title=None,
        backend=None, strict_range=True, progress=None, rhino=None):
    """Build geometry, write the renders and the sheet, return the manifest.

    ``raw_params``  the 16 parameters as a dict.
    ``overrides``   a settings dict and/or preset name (or a list of them).
    ``rhino``       optional ``{"url":..., "api_key":..., "gh_path":...}``.
    """
    def say(msg):
        if progress:
            progress(msg)

    t0 = time.time()
    if isinstance(overrides, (str, Path, dict)) or overrides is None:
        overrides = [overrides]
    s = S.resolve(*overrides)
    if backend:
        s["backend"] = backend
        S.validate(s)

    clean = P.validate(raw_params, strict_range=strict_range)
    clean.pop("__unknown__", None)
    warnings = []
    if not strict_range:
        warnings.extend(P.out_of_range(clean))

    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    name = "%s_%s" % (stamp, slugify(slug or title or s["backend"]))
    out_dir = Path(out_root or DEFAULT_OUT_ROOT) / name
    (out_dir / "renders").mkdir(parents=True, exist_ok=True)

    say("Building geometry with the '%s' backend..." % s["backend"])
    rhino = rhino or {}
    geom = backends.build(
        clean, s["backend"],
        gh_path=rhino.get("gh_path"),
        rhino_url=rhino.get("url"),
        rhino_api_key=rhino.get("api_key"),
        node_bin=rhino.get("node_bin"),
    )
    say(geom.summary())

    manifest = {
        "created": _dt.datetime.now().isoformat(timespec="seconds"),
        "run": name,
        "backend": geom.backend,
        "geometry": {
            "parts": {n: {"vertices": p.n_vertices, "faces": p.n_faces}
                      for n, p in geom.ordered_parts()},
            "fitted_ring_height_mm": round(geom.meta["ring"]["fittedHeight"], 6),
            "build_seconds": geom.meta.get("build_seconds"),
        },
        "parameters": clean,
        "warnings": warnings,
        "renders": [],
        "drawing": None,
    }
    if "section_agreement_mm" in geom.meta:
        manifest["geometry"]["section_agreement_mm"] = geom.meta["section_agreement_mm"]

    # ---- standalone renders, one PNG each --------------------------------
    if s["render"]["enabled"]:
        views = expand_views(s["render"])
        for i, v in enumerate(views, 1):
            vname, az, el = S.resolve_view(v)
            say("Render %d/%d: %s" % (i, len(views), vname))
            img = scene.render_view(geom, s, v)
            path = out_dir / "renders" / ("%s.png" % slugify(vname, "view"))
            Image.fromarray(img).save(str(path))
            manifest["renders"].append({
                "name": vname, "az": az, "el": el, "file": path.name,
                "size": [int(img.shape[1]), int(img.shape[0])],
            })

    # ---- technical drawing ----------------------------------------------
    if s["drawing"]["enabled"]:
        fmts = {f for f, on in s["drawing"]["formats"].items() if on}
        if fmts:
            say("Composing the drawing sheet (%s)..." % ", ".join(sorted(fmts)))
            out_paths = {f: out_dir / ("drawing.%s" % f) for f in sorted(fmts)}
            manifest["drawing"] = SHEET.render_sheet(
                geom, s, out_paths=out_paths, title=title, warnings=warnings)

    (out_dir / "parameters.json").write_text(
        json.dumps(clean, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "settings.json").write_text(
        json.dumps(s, indent=2, sort_keys=True), encoding="utf-8")
    manifest["total_seconds"] = round(time.time() - t0, 2)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")

    manifest["out_dir"] = str(out_dir)
    say("Done in %.1fs -> %s" % (manifest["total_seconds"], out_dir))
    return manifest
