"""Command line for propeller_studio.

    python -m propeller_studio render --params my_prop.json
    python -m propeller_studio render --attempt attempts/12 --backend rhino
    python -m propeller_studio render --preset technical --views top,front,iso
    python -m propeller_studio gui

Every setting is reachable two ways: through a preset file (a partial copy of
the settings tree) and through a flag.  Flags win, so a preset is a starting
point rather than a straitjacket.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from propeller_studio import params as P
from propeller_studio import settings as S
from propeller_studio.geometry.backends import GeometryError


def _csv(text):
    return [t.strip() for t in str(text).split(",") if t.strip()]


def _views(text):
    """Parse ``top,iso,az30el20`` or ``top,{"az":30,"el":20}``."""
    out = []
    for tok in _csv(text):
        if tok.startswith("{"):
            out.append(json.loads(tok))
        else:
            out.append(tok)
    return out


def _set(tree, path, value):
    node = tree
    keys = path.split(".")
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value


def build_parser():
    p = argparse.ArgumentParser(
        prog="propeller_studio",
        description="Renders and technical drawings of a parametric propeller.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("render", help="render one parameter set")
    src = r.add_argument_group("parameters")
    src.add_argument("--params", help="JSON file with the 16 parameters")
    src.add_argument("--attempt", help="an attempts/<n> folder to read parameters.json from")
    src.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                     help="override one parameter (repeatable)")
    src.add_argument("--allow-out-of-range", action="store_true",
                     help="draw values outside the documented band, noting them on the sheet")

    cfg = r.add_argument_group("settings")
    cfg.add_argument("--preset", action="append", default=[],
                     help="preset name or path (repeatable; later ones win)")
    cfg.add_argument("--backend", choices=("feg", "rhino"),
                     help="geometry engine; never falls back to the other")
    cfg.add_argument("--views", type=_views, help="render views, comma separated")
    cfg.add_argument("--drawing-views", type=_views, help="views on the drawing sheet")
    cfg.add_argument("--sections", type=_csv, help="inner,middle,outer (empty to omit)")
    cfg.add_argument("--turntable", type=int, metavar="N",
                     help="also render N orbit frames")
    cfg.add_argument("--color", help="propeller colour, e.g. '#b87333'")
    cfg.add_argument("--part-color", action="append", default=[], metavar="PART=#HEX",
                     help="per-part colour, e.g. ring=#8a8f98 (repeatable)")
    cfg.add_argument("--metallic", type=float)
    cfg.add_argument("--roughness", type=float)
    cfg.add_argument("--lighting", choices=S.LIGHTING_PRESETS)
    cfg.add_argument("--intensity", type=float, help="light gain, 1.0 = preset default")
    cfg.add_argument("--background", choices=S.BACKGROUND_MODES)
    cfg.add_argument("--bg-color")
    cfg.add_argument("--size", help="render size WxH, e.g. 2000x1500")
    cfg.add_argument("--projection", choices=S.PROJECTIONS)
    cfg.add_argument("--layout", choices=S.DRAWING_LAYOUTS,
                     help="stacked (bands) or sections_right/left (column)")
    cfg.add_argument("--sections-width", type=float, metavar="FRACTION",
                     help="width of the sections column, 0.15-0.7 (column layouts)")
    cfg.add_argument("--sheet", choices=sorted(S.SHEET_SIZES))
    cfg.add_argument("--portrait", action="store_true")
    cfg.add_argument("--formats", type=_csv, help="png,pdf,svg")
    cfg.add_argument("--dpi", type=int)
    cfg.add_argument("--no-renders", action="store_true")
    cfg.add_argument("--no-drawing", action="store_true")
    cfg.add_argument("--param-table", action="store_true",
                     help="print the full parameter table on the sheet")
    cfg.add_argument("--settings-json", help="raw settings JSON file merged last")

    out = r.add_argument_group("output")
    out.add_argument("--out", help="output root (default propeller_studio/out)")
    out.add_argument("--slug", help="name for the run folder")
    out.add_argument("--title", help="drawing title")
    out.add_argument("--drawn-by")
    out.add_argument("--quiet", action="store_true")

    rh = r.add_argument_group("rhino backend")
    rh.add_argument("--rhino-url", help="default http://localhost:6500/")
    rh.add_argument("--rhino-key")
    rh.add_argument("--gh-path", help="path to Propeller_Raul_V1.2.gh")
    rh.add_argument("--node-bin", help="path to node.exe for the feg backend")

    g = sub.add_parser("gui", help="start the local browser interface")
    g.add_argument("--port", type=int, default=8765)
    g.add_argument("--host", default="127.0.0.1")
    g.add_argument("--no-browser", action="store_true")
    g.add_argument("--out", help="output root")

    sub.add_parser("presets", help="list the available presets")

    d = sub.add_parser("defaults", help="print the full settings tree")
    d.add_argument("--out", help="write it to this file instead of stdout")

    return p


def collect_params(args):
    warnings = []
    if args.params and args.attempt:
        raise SystemExit("Give --params or --attempt, not both.")
    if args.params or args.attempt:
        raw, warnings = P.load(args.params or args.attempt,
                               strict_range=not args.allow_out_of_range)
    else:
        raw = dict(P.DEFAULT_PARAMS)
        warnings.append("No --params given; rendering the built-in default design.")
    for item in args.set:
        if "=" not in item:
            raise SystemExit("--set expects NAME=VALUE, got %r" % item)
        k, v = item.split("=", 1)
        k = k.strip()
        if k not in P.PARAM_NAMES:
            raise SystemExit("Unknown parameter %r.  Known: %s"
                             % (k, ", ".join(P.PARAM_NAMES)))
        try:
            raw[k] = float(v)
        except ValueError:
            raise SystemExit("--set %s expects a number, got %r" % (k, v))
    clean = P.validate(raw, strict_range=not args.allow_out_of_range)
    clean.pop("__unknown__", None)
    return clean, warnings


def collect_overrides(args):
    """Flag overrides as a settings dict layered over any --preset."""
    o = {}
    if args.backend:
        o["backend"] = args.backend
    if args.views is not None:
        _set(o, "render.views", args.views)
    if args.drawing_views is not None:
        _set(o, "drawing.views", args.drawing_views)
    if args.sections is not None:
        _set(o, "drawing.sections.which", args.sections)
        _set(o, "drawing.sections.enabled", bool(args.sections))
    if args.turntable:
        _set(o, "render.turntable.enabled", True)
        _set(o, "render.turntable.count", args.turntable)
    if args.color:
        _set(o, "render.material.uniform.color", args.color)
        _set(o, "render.material.mode", "uniform")
    for item in args.part_color:
        if "=" not in item:
            raise SystemExit("--part-color expects PART=#HEX, got %r" % item)
        part, col = item.split("=", 1)
        _set(o, "render.material.mode", "per_part")
        o.setdefault("render", {}).setdefault("material", {}).setdefault(
            "parts", {}).setdefault(part.strip(), {})["color"] = col.strip()
    if args.metallic is not None:
        _set(o, "render.material.uniform.metallic", args.metallic)
    if args.roughness is not None:
        _set(o, "render.material.uniform.roughness", args.roughness)
    if args.lighting:
        _set(o, "render.lighting.preset", args.lighting)
    if args.intensity is not None:
        _set(o, "render.lighting.intensity", args.intensity)
    if args.background:
        _set(o, "render.background.mode", args.background)
    if args.bg_color:
        _set(o, "render.background.color", args.bg_color)
    if args.size:
        try:
            w, h = str(args.size).lower().split("x")
            _set(o, "render.width", int(w))
            _set(o, "render.height", int(h))
        except Exception:
            raise SystemExit("--size expects WxH, e.g. 2000x1500")
    if args.projection:
        _set(o, "render.projection", args.projection)
    if args.layout:
        _set(o, "drawing.layout", args.layout)
    if args.sections_width:
        _set(o, "drawing.sections_column_fraction", args.sections_width)
    if args.sheet:
        _set(o, "drawing.sheet.size", args.sheet)
    if args.portrait:
        _set(o, "drawing.sheet.orientation", "portrait")
    if args.formats is not None:
        _set(o, "drawing.formats",
             {f: (f in args.formats) for f in ("png", "pdf", "svg")})
    if args.dpi:
        _set(o, "drawing.dpi", args.dpi)
    if args.no_renders:
        _set(o, "render.enabled", False)
    if args.no_drawing:
        _set(o, "drawing.enabled", False)
    if args.param_table:
        _set(o, "drawing.param_table", True)
    if args.drawn_by:
        _set(o, "drawing.drawn_by", args.drawn_by)

    layers = list(args.preset)
    if args.settings_json:
        layers.append(json.loads(Path(args.settings_json).read_text(encoding="utf-8")))
    layers.append(o)
    return layers


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.command == "presets":
        names = sorted(f.stem for f in S.PRESET_DIR.glob("*.json"))
        print("\n".join(names) if names else "(no presets)")
        return 0

    if args.command == "defaults":
        text = json.dumps(S.defaults(), indent=2)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print("Wrote %s" % args.out)
        else:
            print(text)
        return 0

    if args.command == "gui":
        from propeller_studio.gui.server import serve
        return serve(host=args.host, port=args.port,
                     open_browser=not args.no_browser, out_root=args.out)

    # ---- render ----------------------------------------------------------
    from propeller_studio import pipeline

    params, warnings = collect_params(args)
    for w in warnings:
        print("note: %s" % w, file=sys.stderr)

    def progress(msg):
        if not args.quiet:
            print(msg, flush=True)

    try:
        manifest = pipeline.run(
            params, collect_overrides(args),
            out_root=args.out, slug=args.slug, title=args.title,
            strict_range=not args.allow_out_of_range, progress=progress,
            rhino={"url": args.rhino_url, "api_key": args.rhino_key,
                   "gh_path": args.gh_path, "node_bin": args.node_bin},
        )
    except (GeometryError, S.SettingsError, P.ParamError) as exc:
        print("\n%s" % exc, file=sys.stderr)
        return 2

    if not args.quiet:
        print("\n%d render(s) + %s" % (
            len(manifest["renders"]),
            ", ".join(manifest["drawing"]["files"]) if manifest["drawing"] else "no drawing"))
    return 0
