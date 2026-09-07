"""The 16 canonical propeller parameters: ranges, validation, and loading.

Self-contained by design.  ``propeller_studio`` is meant to be lifted out of
this repository into a standalone tool, so nothing here imports from the
multi-agent app -- the parameter table below is a deliberate copy of
``DC_prompt_fragments/dc_config/parameters.md``, guarded by
``propeller_studio/dev/drift_check.py``.

The outer-ring HEIGHT is NOT a parameter: it is derived to fit the outer blade
section (see ``geometry/airfoil.py:fitted_ring_height``).  Older parameter
files may still carry a 17th ``impellerHeight`` key; it is ignored on load.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParamSpec:
    name: str
    unit: str
    lo: float
    hi: float
    integer: bool
    label: str
    group: str


# Order matters: it is the display order in the GUI form and in the sheet's
# parameter table.
PARAM_SPECS: tuple[ParamSpec, ...] = (
    ParamSpec("bladeCount", "", 3, 6, True, "Blade count", "Global / ring"),
    ParamSpec("impellerRadius", "mm", 60, 80, False, "Impeller radius", "Global / ring"),
    ParamSpec("impellerThickness", "mm", 1, 5, False, "Ring wall thickness", "Global / ring"),

    ParamSpec("innerThickness", "% chord", 3, 24, False, "Thickness", "Inner section"),
    ParamSpec("innerMaxPos", "/10 chord", 2, 8, True, "Camber crest position", "Inner section"),
    ParamSpec("innerCamber", "% chord", 0, 9, False, "Camber", "Inner section"),
    ParamSpec("innerChord", "mm", 3, 11, False, "Chord", "Inner section"),
    ParamSpec("innerAngle", "deg", 2, 25, False, "Angle of attack", "Inner section"),

    ParamSpec("middlePos", "span fraction", 0.3, 0.7, False, "Span position", "Middle section"),
    ParamSpec("middleChord", "mm", 10, 30, False, "Chord", "Middle section"),
    ParamSpec("middleAngle", "deg", 2, 25, False, "Angle of attack", "Middle section"),

    ParamSpec("outerThickness", "% chord", 3, 24, False, "Thickness", "Outer section"),
    ParamSpec("outerMaxPos", "/10 chord", 2, 8, True, "Camber crest position", "Outer section"),
    ParamSpec("outerCamber", "% chord", 0, 9, False, "Camber", "Outer section"),
    ParamSpec("outerChord", "mm", 10, 30, False, "Chord", "Outer section"),
    ParamSpec("outerAngle", "deg", 2, 25, False, "Angle of attack", "Outer section"),
)

PARAM_NAMES: tuple[str, ...] = tuple(s.name for s in PARAM_SPECS)
SPEC_BY_NAME: dict[str, ParamSpec] = {s.name: s for s in PARAM_SPECS}

# Fixed geometry constants that are NOT parameters (mirrors web/feg/constants.js
# and the hub note in parameters.md).  The hub is LARGER than the blade root, so
# it hides the innermost part of each blade -- do not confuse the two radii.
INNER_RADIUS_FIXED = 4.0     # blade root radius, mm
HUB_RADIUS = 8.28            # mm
RING_CLEARANCE = 1.0         # mm, ring fit either side of the outer section

# A representative in-range design, used as the GUI's initial form state and as
# the CLI default when no parameter file is given.
DEFAULT_PARAMS: dict[str, float] = {
    "bladeCount": 5,
    "impellerRadius": 70.0,
    "impellerThickness": 3.0,
    "innerThickness": 12.0,
    "innerMaxPos": 4,
    "innerCamber": 4.0,
    "innerChord": 10.0,
    "innerAngle": 23.0,
    "middlePos": 0.5,
    "middleChord": 30.0,
    "middleAngle": 22.0,
    "outerThickness": 8.0,
    "outerMaxPos": 4,
    "outerCamber": 3.0,
    "outerChord": 20.0,
    "outerAngle": 15.0,
}


class ParamError(ValueError):
    """A parameter set is missing keys, non-numeric, or out of range."""


def validate(raw: dict, *, strict_range: bool = True) -> dict:
    """Return a clean 16-key parameter dict, or raise :class:`ParamError`.

    ``strict_range=False`` still requires every key to be present and numeric
    but permits values outside the documented band.  Out-of-range values are a
    legitimate thing to WANT to draw -- you may be exploring what a chord of
    40 mm looks like -- so the CLI exposes this as ``--allow-out-of-range``
    rather than making it unreachable.
    """
    if not isinstance(raw, dict):
        raise ParamError("Parameters must be a JSON object mapping name -> number.")

    missing, bad_type, out_of_range = [], [], []
    clean: dict[str, float] = {}

    for spec in PARAM_SPECS:
        if spec.name not in raw:
            missing.append(spec.name)
            continue
        v = raw[spec.name]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            bad_type.append(f"{spec.name}={v!r}")
            continue
        v = int(round(v)) if spec.integer else float(v)
        if strict_range and not (spec.lo <= v <= spec.hi):
            out_of_range.append(
                f"{spec.name}={v:g} (allowed {spec.lo:g}..{spec.hi:g} {spec.unit})".rstrip()
            )
        clean[spec.name] = v

    problems = []
    if missing:
        problems.append("missing: " + ", ".join(sorted(missing)))
    if bad_type:
        problems.append("not a number: " + ", ".join(sorted(bad_type)))
    if out_of_range:
        problems.append("out of range: " + "; ".join(out_of_range))
    if problems:
        raise ParamError(
            "Invalid parameter set -- " + " | ".join(problems)
            + (".  Pass --allow-out-of-range to draw it anyway."
               if out_of_range and not missing and not bad_type else ".")
        )

    unknown = sorted(set(raw) - set(PARAM_NAMES) - {"impellerHeight"})
    if unknown:
        # Not fatal: preset files and attempt records carry extra bookkeeping
        # keys.  Report them so a typo'd parameter name cannot pass silently.
        clean["__unknown__"] = unknown  # type: ignore[assignment]
    return clean


def load(source: str | Path, *, strict_range: bool = True) -> tuple[dict, list[str]]:
    """Load parameters from a JSON file OR an attempt folder.

    Accepts either a path to a ``.json`` file holding the 16 keys, or a
    directory containing ``parameters.json``.  Returns ``(params, warnings)``.
    """
    path = Path(source)
    if path.is_dir():
        path = path / "parameters.json"
    if not path.is_file():
        raise ParamError(f"No parameter file at {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ParamError(f"Could not read {path}: {exc}") from exc

    clean = validate(raw, strict_range=strict_range)
    warnings: list[str] = []
    unknown = clean.pop("__unknown__", None)
    if unknown:
        warnings.append(
            f"{path.name} carries keys that are not parameters and were "
            f"ignored: {', '.join(unknown)}"
        )
    return clean, warnings


def out_of_range(params: dict) -> list[str]:
    """Human-readable list of values outside the documented band (may be empty).

    Used to stamp a warning on the sheet rather than to refuse the render.
    """
    notes = []
    for spec in PARAM_SPECS:
        v = params.get(spec.name)
        if isinstance(v, (int, float)) and not (spec.lo <= v <= spec.hi):
            notes.append(f"{spec.name}={v:g} outside {spec.lo:g}..{spec.hi:g}")
    return notes
