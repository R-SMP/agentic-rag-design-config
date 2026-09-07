"""Studio settings: every toggle, colour and layout choice in one JSON tree.

The whole tool is driven by this one structure.  ``DEFAULTS`` below is the
complete schema -- there is no hidden state -- so a preset file is just a
partial copy of it, deep-merged over the defaults by :func:`resolve`.

That partial-merge rule is what makes presets survive upgrades: a preset
written today keeps working when a new toggle is added tomorrow, because the
new key falls back to its default instead of being missing.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

PRESET_DIR = Path(__file__).resolve().parent / "presets"

# Named view directions as (azimuth_deg, elevation_deg).
#   azimuth   -- angle in the XY plane, measured from +X toward +Y
#   elevation -- angle above the XY plane; +90 looks straight down the axis
# Z is the propeller's rotation axis, so `top` is the planform view.
NAMED_VIEWS = {
    "top": (0.0, 90.0),
    "bottom": (0.0, -90.0),
    "front": (0.0, 0.0),
    "back": (180.0, 0.0),
    "right": (90.0, 0.0),
    "left": (270.0, 0.0),
    "iso": (45.0, 35.264),          # true isometric
    "iso_low": (45.0, 20.0),
    "iso_rear": (225.0, 35.264),
    "three_quarter": (30.0, 55.0),
}

LIGHTING_PRESETS = ("studio", "soft", "dramatic", "technical")
BACKGROUND_MODES = ("solid", "gradient", "transparent", "floor")
PROJECTIONS = ("perspective", "orthographic")
DRAWING_LAYOUTS = ("stacked", "sections_right", "sections_left")
SCALE_MODES = ("fill", "standard")
SHEET_SIZES = {                      # width x height in mm, portrait
    "A5": (148, 210), "A4": (210, 297), "A3": (297, 420),
    "A2": (420, 594), "A1": (594, 841),
}

DEFAULTS = {
    # Which geometry engine builds the mesh.  No fallback between them.
    "backend": "feg",

    "render": {
        "enabled": True,
        "views": ["iso", "top", "front"],
        "turntable": {"enabled": False, "count": 12, "elevation": 20.0},
        "width": 1600,
        "height": 1200,
        "projection": "perspective",
        "zoom": 1.4,
        "anti_aliasing": True,
        "background": {
            "mode": "gradient",
            "color": "#f2f4f7",
            "color2": "#c9d4e4",
            "floor_color": "#e8e8e8",
            "shadow": True,
        },
        "material": {
            "mode": "uniform",              # "uniform" | "per_part"
            "uniform": {
                "color": "#b87333",
                "metallic": 0.55,
                "roughness": 0.35,
                "opacity": 1.0,
            },
            "parts": {
                "blade": {"color": "#b87333", "metallic": 0.55, "roughness": 0.30, "opacity": 1.0},
                "ring": {"color": "#8a8f98", "metallic": 0.70, "roughness": 0.28, "opacity": 1.0},
                "hub": {"color": "#4a5058", "metallic": 0.60, "roughness": 0.40, "opacity": 1.0},
                "launcher": {"color": "#6f7681", "metallic": 0.60, "roughness": 0.40, "opacity": 1.0},
                "body": {"color": "#b87333", "metallic": 0.55, "roughness": 0.35, "opacity": 1.0},
            },
        },
        "lighting": {
            "preset": "studio",
            "intensity": 1.0,
            "custom": [],                   # non-empty overrides the preset
        },
        "overlays": {
            "silhouette": False,
            "feature_edges": False,
            "feature_angle": 45.0,
            "section_curves": False,
            "section_curves_on_top": True,
            "wireframe": False,
        },
    },

    "drawing": {
        "enabled": True,
        # "stacked"        views across the top, sections in a band below
        # "sections_right" views fill the left, sections run down the right
        # "sections_left"  the mirror of sections_right
        "layout": "stacked",
        "sections_column_fraction": 0.38,   # column layouts only
        # "fill"     draw as large as the panel allows, stating the true ratio
        # "standard" round DOWN to a preferred-series scale (2:1, 1:1, 1:2 ...)
        # The series has nothing between 1:1 and 1:2, so on A3 with three views
        # "standard" costs about 40 % of the image size.  Either way the title
        # block states the scale actually used.
        "scale_mode": "fill",
        "font_scale": 1.0,                  # multiplies every annotation size
        "sheet": {
            "size": "A3",
            "orientation": "landscape",
            "margin_mm": 10.0,
            "frame": True,
            "title_block": True,
        },
        "views": ["top", "front", "iso"],
        "view_style": {
            "shaded": True,
            "silhouette": True,
            "feature_edges": True,
            "section_curves": True,
            "planform_outline": False,
            "wireframe": False,
            "labels": True,
            "shading_strength": 0.55,       # 0 = white body, 1 = full render
        },
        "sections": {
            "enabled": True,
            "which": ["inner", "middle", "outer"],
            "common_scale": True,
            "grid": True,
            "annotations": {
                "chord": True,
                "angle": True,
                "thickness": True,
                "camber": True,
                "radial_station": True,
                "span_position": True,
                "chord_line": True,
                "camber_line": True,
                "le_te": False,
                "le_radius": False,
                "bbox": False,
                "value_table": True,
            },
        },
        "param_table": False,
        "title": "",
        "drawn_by": "",
        "notes": "",
        "formats": {"png": True, "pdf": True, "svg": False},
        "dpi": 200,
    },
}


class SettingsError(ValueError):
    """A settings tree contains a value the renderer cannot honour."""


def deep_merge(base, override):
    """Recursively merge *override* into a copy of *base*.

    Lists REPLACE rather than concatenate -- ``views: ["top"]`` in a preset
    means exactly one view, not "top appended to the defaults".
    """
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def defaults():
    return copy.deepcopy(DEFAULTS)


def load_preset(name_or_path):
    """Load a preset by bare name (from ``presets/``) or by explicit path."""
    p = Path(name_or_path)
    if not p.suffix:
        p = PRESET_DIR / (str(name_or_path) + ".json")
    if not p.is_file():
        available = sorted(f.stem for f in PRESET_DIR.glob("*.json"))
        raise SettingsError(
            "No preset %r.  Available: %s" % (name_or_path, ", ".join(available) or "(none)")
        )
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SettingsError("Preset %s is not valid JSON: %s" % (p, exc)) from exc


def resolve(*overrides):
    """Merge *overrides* (dicts or preset names) over the defaults, validate."""
    out = defaults()
    for ov in overrides:
        if ov is None:
            continue
        if isinstance(ov, (str, Path)):
            ov = load_preset(ov)
        out = deep_merge(out, ov)
    validate(out)
    return out


def _check(cond, msg):
    if not cond:
        raise SettingsError(msg)


def validate(s):
    """Fail loudly on a value that cannot be honoured, naming the fix."""
    _check(s["backend"] in ("feg", "rhino"),
           "backend must be 'feg' or 'rhino', got %r" % s["backend"])

    r = s["render"]
    _check(r["projection"] in PROJECTIONS,
           "render.projection must be one of %s" % (PROJECTIONS,))
    _check(r["background"]["mode"] in BACKGROUND_MODES,
           "render.background.mode must be one of %s" % (BACKGROUND_MODES,))
    _check(r["lighting"]["preset"] in LIGHTING_PRESETS,
           "render.lighting.preset must be one of %s" % (LIGHTING_PRESETS,))
    _check(r["material"]["mode"] in ("uniform", "per_part"),
           "render.material.mode must be 'uniform' or 'per_part'")
    _check(int(r["width"]) > 0 and int(r["height"]) > 0,
           "render width/height must be positive")
    for v in r["views"]:
        resolve_view(v)
    tt = r["turntable"]
    if tt["enabled"]:
        _check(int(tt["count"]) >= 1, "render.turntable.count must be >= 1")

    d = s["drawing"]
    _check(d.get("layout", "stacked") in DRAWING_LAYOUTS,
           "drawing.layout must be one of %s" % (DRAWING_LAYOUTS,))
    _check(d.get("scale_mode", "fill") in SCALE_MODES,
           "drawing.scale_mode must be one of %s" % (SCALE_MODES,))
    _check(float(d.get("font_scale", 1.0)) > 0,
           "drawing.font_scale must be positive")
    _check(d["sheet"]["size"] in SHEET_SIZES,
           "drawing.sheet.size must be one of %s" % (sorted(SHEET_SIZES),))
    _check(d["sheet"]["orientation"] in ("landscape", "portrait"),
           "drawing.sheet.orientation must be 'landscape' or 'portrait'")
    for v in d["views"]:
        resolve_view(v)
    for k in d["sections"]["which"]:
        _check(k in ("inner", "middle", "outer"),
               "drawing.sections.which may only contain inner/middle/outer, got %r" % k)
    _check(any(d["formats"].values()) or not d["enabled"],
           "drawing.formats: enable at least one of png / pdf / svg, or set "
           "drawing.enabled = false")
    _check(int(d["dpi"]) > 0, "drawing.dpi must be positive")
    return s


def resolve_view(v):
    """Normalise one view spec to ``(name, azimuth_deg, elevation_deg)``.

    Accepts a named view (``"iso"``), or a dict with ``az``/``el`` and an
    optional ``name``.
    """
    if isinstance(v, str):
        if v not in NAMED_VIEWS:
            raise SettingsError(
                "Unknown view %r.  Named views: %s.  Or give "
                '{"name": "...", "az": 30, "el": 20}.' % (v, ", ".join(sorted(NAMED_VIEWS)))
            )
        az, el = NAMED_VIEWS[v]
        return (v, float(az), float(el))
    if isinstance(v, dict):
        if "az" not in v or "el" not in v:
            raise SettingsError('Custom view needs both "az" and "el": %r' % (v,))
        az, el = float(v["az"]), float(v["el"])
        name = v.get("name") or ("az%g_el%g" % (az, el))
        return (str(name), az, el)
    raise SettingsError("A view must be a name or {az, el} dict, got %r" % (v,))


def sheet_size_mm(sheet):
    w, h = SHEET_SIZES[sheet["size"]]
    return (h, w) if sheet["orientation"] == "landscape" else (w, h)


def part_material(s, part_name):
    """The material dict to use for *part_name*, honouring uniform vs per-part."""
    mat = s["render"]["material"]
    if mat["mode"] == "uniform":
        return mat["uniform"]
    return mat["parts"].get(part_name, mat["uniform"])
