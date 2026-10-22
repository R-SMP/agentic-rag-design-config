- The adapter is built by OpenSCAD from a parametric model: two ends
  (connectors) joined by a transition.  Each parameter goes to the model's
  setting of the same name.  ``End<N>_Diameter_mm`` and ``End<N>_Length_mm``
  are the model's millimetre values; ``Transition_Offset_x`` / ``_y`` and a
  nozzle's ``_x`` / ``_y`` / ``_z`` are the parts of one setting each.
- A choice parameter takes one of its listed values exactly (e.g.
  ``End1_Style = hose``); an on/off parameter takes true or false.
- A parameter marked "(only when …)" has no effect unless that condition
  holds — leave it at its default otherwise.
- Many settings use 0 for "none" or "automatic": an extension length of 0
  adds no extension, a barb count of 0 adds no barbs, an end-cap thickness of
  0 adds no cap.
- The ranges are the configurator's limits; the model's own defaults sit
  inside them.

### Common unit-conversion patterns for this configurator

When QUANTITATIVE INPUTS contains a real-world-quantity entry in a
non-matching unit / frame, the patterns most often encountered with
this hose adapter DC are:

  * Inches ↔ millimetres: 1 in = 25.4 mm.
  * A hose's or port's size ↔ an end's diameter and measurement.  An end
    that goes INTO a hose or port takes that hose's or port's INNER diameter,
    with ``Measurement = outer``; an end that goes OVER a pipe or port takes
    its OUTER diameter, with ``Measurement = inner``.  When the request does
    not say which, choose, and state the reading in one clause.
  * Radius ↔ diameter: diameter = 2 × radius.

These are the typical patterns; the user may state quantities in
other ways too.  When you encounter an unfamiliar unit, derive the
conversion from the parameter list itself plus standard unit
algebra, OR fall back to engineering judgement with a stated
rationale.

### Hard engineering blockers (parameter combinations that break the geometry)

These combinations make the geometry physically impossible —
flag them as hard blockers wherever you check parameter consistency:

  * ``End<N>_Wall_Thickness ≤ 0`` or ``End<N>_Diameter_mm ≤ 0`` → no end.

These are physics-derived blockers, not style preferences;
treat any violation as a non-negotiable fail.
