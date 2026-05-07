- Blade profiles are NACA-style airfoils parameterised by thickness, camber,
  and high-point.
- "High-point" is the chordwise location of maximum thickness, given in
  tenths of chord (e.g. a value of 3 means 30% chord from the leading edge).
- "Distance to middle NACA" is dimensionless: multiply it by the propeller
  radius to obtain the actual radial distance from the centre.
- bladeCount, innerMaxPos, and outerMaxPos must be integers; all
  other parameters are floating-point numbers.

### Common unit-conversion patterns for this configurator

When QUANTITATIVE INPUTS contains a real-world-quantity entry in a
non-matching unit / frame, the patterns most often encountered with
this propeller DC are:

  * Blade-section thickness in mm ↔ percent of chord
    (``innerThickness`` / ``outerThickness`` are stored as % of the
    corresponding chord).
  * Camber in mm ↔ percent of chord
    (``innerCamber`` / ``outerCamber``).
  * Highpoint in mm ↔ integer percent of chord
    (``innerMaxPos`` / ``outerMaxPos`` — round after conversion).
  * Distance from hub in mm ↔ fraction of radius
    (``middlePos`` is stored as a fraction of ``impellerRadius``).
  * Diameter ↔ radius (the configurator parameterises only ``impellerRadius``;
    user-stated diameters convert via ``impellerRadius = diameter / 2``).
  * Absolute mm ↔ fraction / percent of an overall scale parameter
    (when the user expresses a chord, height, or similar absolute-
    unit value as a fraction of diameter or radius, multiply by the
    corresponding scale).

These are the typical patterns; the user may state quantities in
other ways too.  When you encounter an unfamiliar unit, derive the
conversion from the parameter list itself plus standard unit
algebra, OR fall back to engineering judgement with a stated
rationale.

### Hard engineering blockers (parameter combinations that break the geometry)

These combinations make the geometry physically impossible or
self-intersecting — flag them as hard blockers wherever you check
parameter consistency:

  * ``innerThickness ≤ 0`` or ``outerThickness ≤ 0``  → degenerate
    blade section.

These are physics-derived blockers, not style preferences;
treat any violation as a non-negotiable fail.
