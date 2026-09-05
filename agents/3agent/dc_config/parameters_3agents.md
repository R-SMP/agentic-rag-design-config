### Global / ring
 1. bladeCount         (integer)                             — Number of blades [3; 6]
 2. impellerRadius     (mm)                                  — Outer radius of the impeller ring [60; 80]
 3. impellerThickness  (mm)                                  — Wall thickness of the outer ring [1; 5]

(The outer-ring HEIGHT is not a parameter — it is derived automatically to fit the outer blade section.)

(The central hub is a FIXED cylinder of radius 8 mm — not a parameter.  It is
LARGER than the blade root at r = 4 mm, so the hub hides the innermost part of
each blade; do not confuse the two radii.)

### Inner blade section
 4. innerThickness     (% of the INNER chord)                — Profile thickness [3; 24]
 5. innerMaxPos        (tenths of the INNER chord, integer)  — Chordwise position of max camber [2; 8]
 6. innerCamber        (% of the INNER chord)                — Profile camber [0; 9]
 7. innerChord         (mm)                                  — Chord length [3; 11]
 8. innerAngle         (degrees)                             — Angle of attack [2; 25]

### Middle blade section
 9. middlePos          (fraction of blade span, unitless)    — Middle-section position along the blade: 0 = root (INNER BLADE SECTION, r = 4 mm), 1 = tip; radius = 4 + middlePos·(impellerRadius − 4) mm [0.3; 0.7]
10. middleChord        (mm)                                  — Chord length [10; 30]
11. middleAngle        (degrees)                             — Angle of attack [2; 25]

### Outer blade section
12. outerThickness     (% of the OUTER chord)                — Profile thickness [3; 24]
13. outerMaxPos        (tenths of the OUTER chord, integer)  — Chordwise position of max camber [2; 8]
14. outerCamber        (% of the OUTER chord)                — Profile camber [0; 9]
15. outerChord         (mm)                                  — Chord length [10; 30]
16. outerAngle         (degrees)                             — Angle of attack [2; 25]

``innerMaxPos`` / ``outerMaxPos`` move the CAMBER crest only, and do nothing
at zero camber.

``innerThickness`` / ``outerThickness`` set HOW THICK a section is, as a
percentage of its own chord.  They do not move WHERE it is thickest: the
chordwise position of maximum thickness is fixed at ~30% of chord and no
parameter changes it.
