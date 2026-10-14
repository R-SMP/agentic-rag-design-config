## Which lever moves what

"Shape" means two different things here, and different levers move each.

**A section's PROFILE** — the airfoil outline of one blade section:
* Set by ``*Thickness`` (% of chord), ``*Camber`` (% of chord) and
  ``*MaxPos`` (tenths of chord — the camber crest), for the INNER and
  OUTER sections only.  Nothing else changes a section's profile.
* That section's ``*Chord`` (mm) SIZES it — scaling the profile, not
  reshaping it.
* **The MIDDLE section has no profile parameters.**  Its profile is
  interpolated from inner and outer, so you reshape it only by changing
  the inner and/or outer profile — either or both — and it also shifts with
  ``middlePos``, the radial position the interpolation is taken at.  Its
  own ``middleChord`` sizes it.
* **Angles** orient a section in space; they change neither its profile
  nor its size.

**The BLADE AS A WHOLE** — its 3D form and its top-view outline.  It
follows from the section profiles AND from how the sections are sized,
angled and placed, so more levers reach it:
* the three ``*Chord`` values set the blade OUTLINE from root to tip —
  changing them reshapes the blade even when every section profile is
  left untouched;
* ``middlePos`` moves where the middle section sits along the span, which
  changes that outline too;
* ``impellerRadius`` sets the blade SPAN (4 mm root → tip), so it changes
  the blade's proportions;
* the three ``*Angle`` values TWIST the blade — varying the angle of
  attack from one section to the next turns them by different amounts, so
  the blade as a whole twists along its span;
* the profile parameters above, since the blade is the surface through its
  sections.

``bladeCount`` changes only how many blades there are, and
``impellerThickness`` only the outer ring's wall.

``*Thickness`` and ``*Camber`` are RATIOS (percentages of that section's own
chord), so a request like "make it thicker" or "keep the thickness as it is"
can mean either the ratio or the resulting absolute size in mm — the two
diverge whenever the chord changes.  If the incoming request does not make
clear which it means, state in one clause which reading you used before
applying it.
