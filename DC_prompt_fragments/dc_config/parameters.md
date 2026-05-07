### Global / ring
 1. bladeCount         (integer)              — Number of blades [3; 6]
 2. impellerRadius     (mm)                   — Outer radius of the impeller ring [60; 80]
 3. impellerHeight     (mm)                   — Height of the outer ring [4; 10]
 4. impellerThickness  (mm)                   — Wall thickness of the outer ring [1; 5]

### Inner blade section
 5. innerThickness  (% of chord)              — Profile thickness [3; 24]
 6. innerMaxPos     (integer, tenths of chord) — Chordwise position of max thickness [2; 8]
 7. innerCamber     (% of chord)              — Profile camber [0; 9]
 8. innerChord      (mm)                      — Chord length [3; 11]
 9. innerAngle      (degrees)                 — Angle of attack [2; 25]

### Middle blade section
10. middlePos      (x impellerRadius, unitless)  — Radial position as multiplier of propeller radius [0.3; 0.7]
11. middleChord    (mm)                          — Chord length [10; 30]
12. middleAngle    (degrees)                     — Angle of attack [2; 25]

### Outer blade section
13. outerThickness (% of chord)               — Profile thickness [3; 24]
14. outerMaxPos    (integer, tenths of chord)  — Chordwise position of max thickness [2; 8]
15. outerCamber    (% of chord)               — Profile camber [0; 9]
16. outerChord     (mm)                        — Chord length [10; 30]
17. outerAngle     (degrees)                   — Angle of attack [2; 25]
