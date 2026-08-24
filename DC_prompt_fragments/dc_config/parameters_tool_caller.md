### Global / ring
 1. bladeCount         (integer)              — Number of blades [3; 6]
 2. impellerRadius     (mm)                   — Outer radius of the impeller ring [60; 80]
 3. impellerThickness  (mm)                   — Wall thickness of the outer ring [1; 5]

(The central hub is a FIXED cylinder of radius 8 mm — not a parameter.  It is
LARGER than the blade root at r = 4 mm, so the hub hides the innermost part of
each blade; do not confuse the two radii.)

### Inner blade section
 4. innerThickness  (% of chord)              — Profile thickness [3; 24]
 5. innerMaxPos     (integer, tenths of chord) — Chordwise position of max camber [2; 8]
 6. innerCamber     (% of chord)              — Profile camber [0; 9]
 7. innerChord      (mm)                      — Chord length [3; 11]
 8. innerAngle      (degrees)                 — Angle of attack [2; 25]

``

### Middle blade section
 9. middlePos      (fraction of blade span, unitless)  — Middle-section position along the blade: 0 = root (INNER BLADE SECTION, r = 4 mm), 1 = tip;  [0.3; 0.7]
10. middleChord    (mm)                          — Chord length [10; 30]
11. middleAngle    (degrees)                     — Angle of attack [2; 25]

### Outer blade section
12. outerThickness (% of chord)               — Profile thickness [3; 24]
13. outerMaxPos    (integer, tenths of chord)  — Chordwise position of max camber [2; 8]
14. outerCamber    (% of chord)               — Profile camber [0; 9]
15. outerChord     (mm)                        — Chord length [10; 30]
16. outerAngle     (degrees)                   — Angle of attack [2; 25]
