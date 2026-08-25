- Blade profiles are NACA-style airfoils parameterised by thickness, camber,
  and high-point.
- "High-point" is the camber crest: ``innerMaxPos`` / ``outerMaxPos``, in
  tenths of chord (3 = crest at 30% chord from the leading edge).
- ``middlePos`` (the middle section's radial position) is a fraction of the BLADE
  SPAN measured from the blade root: 0 = root (the INNER BLADE SECTION, radius 4 mm), 1 = tip
  (impellerRadius), 0.5 = the blade's exact midpoint.  The middle section's actual
  radius = ``4 + middlePos·(impellerRadius − 4)`` mm — NOT ``middlePos × impellerRadius``.
  Its range [0.3, 0.7] means the middle section sits 30–70% of the way along the blade.
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
  * Camber-crest position along the chord (mm or % of chord) ↔ tenths of
    chord (``innerMaxPos`` / ``outerMaxPos``: value = 10 × crest-position /
    chord, rounded to an integer in [2; 8]).
  * Distance along the blade ↔ ``middlePos`` (a fraction of the blade SPAN, root→tip,
    NOT of ``impellerRadius``): ``middlePos = (r − 4) / (impellerRadius − 4)``, with
    ``r`` the desired middle-section radius in mm and 4 mm the INNER BLADE SECTION's
    radius — NOT the hub radius, which is 8 mm.
  * Diameter ↔ radius (the configurator parameterises only ``impellerRadius``;
    user-stated diameters convert via ``impellerRadius = diameter / 2``).

These are the typical patterns; the user may state quantities in
other ways too.  When you encounter an unfamiliar unit, derive the
conversion from the parameter list itself plus standard unit
algebra, OR fall back to engineering judgement with a stated
rationale.
