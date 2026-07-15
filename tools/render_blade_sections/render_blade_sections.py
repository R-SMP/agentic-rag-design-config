"""``render_blade_sections`` — a Tool-Caller tool that renders the three
blade cross-sections (Inner / Middle / Outer) stacked vertically as a PNG.

Takes the path to a parameters JSON file (the standard 17-param attempt
file) and draws the SAME airfoils the in-browser "Blade sections" view shows
(see ``tools/render_blade_sections/draw.py``): each section rotated by its
angle of attack, colour-coded (Inner blue, Middle green, Outer red), labelled,
with a bottom-right 0-25 deg protractor whose three rays mark the sections'
angles of attack.

A ``grid`` flag (default False) draws a light 1 mm x 1 mm grid behind the
sections.  Use it ONLY when a real-millimetre reference genuinely helps and
will not mislead — e.g. NOT when matching a user's drawing whose own grid is
not 1 mm per square (the scales would not correspond).

The PNG is written under the parameters file's attempt folder (so it
auto-displays in the chat and can be read back by ``view_images``) and
the canvas is sized tightly to the content to keep the image small.

No web imports here; like the other tools this is pure agent-layer code.
"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.tools import tool

from agents.shared.agent_activity import tool_active
from config import ATTEMPTS_DIR
from tools.render_blade_sections.draw import render_png

# Keys the render needs (the blade-section + middle-position params).  The
# ring params (bladeCount / impeller*) are not used here, so a valid 17-param
# file naturally satisfies this and extra keys are ignored.
_REQUIRED_KEYS = (
    "innerThickness", "innerMaxPos", "innerCamber", "innerChord", "innerAngle",
    "middlePos", "middleChord", "middleAngle",
    "outerThickness", "outerMaxPos", "outerCamber", "outerChord", "outerAngle",
)


@tool
@tool_active("Blade Sections")
def render_blade_sections(parameters_path: str, grid: bool = False) -> str:
    """Render the three blade cross-sections (Inner / Middle / Outer) stacked
    vertically into a PNG image.

    Pass the absolute path to a parameters JSON file (an attempt's
    ``parameters.json``).  The image shows each section's airfoil rotated by
    its angle of attack, colour-coded with a name label, plus a small angle
    protractor.  The PNG is written into that attempt's folder and will be
    shown to the user in the chat; any agent with an image-reading tool (e.g.
    the DC Output Inspector via ``view_images``) can view it by passing
    the returned path.

    Args:
        parameters_path: Absolute path to the parameters ``.json`` file
            (must sit inside the attempts directory).
        grid: When True, draw a light 1 mm x 1 mm reference grid behind the
            sections.  Default False.  Only enable it when a true-millimetre
            grid genuinely helps and will not mislead — e.g. do NOT enable it
            when matching a user's drawing whose own grid squares are not
            1 mm, because the scales would not correspond.  When in doubt,
            leave it off.

    Returns:
        A short message stating the written PNG path (and its size), or
        precisely why the render could not be produced.
    """
    raw = (parameters_path or "").strip()
    if not raw:
        return ("render_blade_sections: FAILED — no parameters_path given. "
                "Pass the absolute path to an attempt's parameters.json.")
    try:
        src = Path(raw).resolve()
    except Exception as exc:
        return f"render_blade_sections: FAILED — invalid path {raw!r}: {exc}"
    if not src.is_file():
        return (f"render_blade_sections: FAILED — no file at {src}. "
                f"Pass the path the previous agent reported.")

    # Keep outputs inside the attempts directory so the render auto-displays
    # in chat and can be re-read by view_images / served by /api/artefact.
    try:
        root = ATTEMPTS_DIR.resolve()
    except OSError:
        root = ATTEMPTS_DIR
    if root != src.parent and root not in src.parents:
        return (f"render_blade_sections: FAILED — {src} is outside the "
                f"attempts directory ({root}); point the tool at an "
                f"attempt's parameters.json.")

    try:
        params = json.loads(src.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"render_blade_sections: FAILED — could not read JSON {src}: {exc}"
    if not isinstance(params, dict):
        return (f"render_blade_sections: FAILED — {src} is not a JSON object "
                f"of parameters.")
    missing = [k for k in _REQUIRED_KEYS if k not in params]
    if missing:
        return (f"render_blade_sections: FAILED — parameters file is missing "
                f"required keys: {missing}.")
    bad = [k for k in _REQUIRED_KEYS
           if not isinstance(params[k], (int, float)) or isinstance(params[k], bool)]
    if bad:
        return (f"render_blade_sections: FAILED — these parameters are not "
                f"numbers: {bad}.")

    out_name = "render_blade_sections_grid.png" if grid else "render_blade_sections.png"
    out_path = src.parent / out_name
    try:
        w, h = render_png(params, bool(grid), out_path)
    except Exception as exc:
        return f"render_blade_sections: FAILED — render error: {exc}"

    return (f"render_blade_sections: OK — wrote {out_name} ({w}x{h}px, "
            f"grid={'on' if grid else 'off'}) to {out_path.parent}. The image "
            f"will be shown in the chat; read it by passing this path to "
            f"view_images: {out_path}")
