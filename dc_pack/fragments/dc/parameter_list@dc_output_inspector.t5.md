### Global / ring
 1. bladeCount         (integer)                              [3; 6]
 2. impellerRadius     (mm)                                   [60; 80]
 3. impellerThickness  (mm)                                   [1; 5]

(The outer-ring HEIGHT is not a parameter — it is derived automatically to fit
the outer blade section.)

(The central hub is a FIXED cylinder of radius 8 mm — not a parameter.  It is
LARGER than the blade root at r = 4 mm, so the hub hides the innermost part of
each blade.)

### Inner blade section
 4. innerThickness     (% of the INNER chord)                 [3; 24]
 5. innerMaxPos        (tenths of the INNER chord, integer)   [2; 8]
 6. innerCamber        (% of the INNER chord)                 [0; 9]
 7. innerChord         (mm)                                   [3; 11]
 8. innerAngle         (degrees)                              [2; 25]

### Middle blade section
 9. middlePos      (fraction of blade span: 0 = root, the INNER BLADE SECTION,
                   at r = 4 mm; 1 = tip) [0.3; 0.7]
10. middleChord        (mm)                                   [10; 30]
11. middleAngle        (degrees)                              [2; 25]

(The middle section has NO thickness, camber or high-point of its own.)

### Outer blade section
12. outerThickness     (% of the OUTER chord)                 [3; 24]
13. outerMaxPos        (tenths of the OUTER chord, integer)   [2; 8]
14. outerCamber        (% of the OUTER chord)                 [0; 9]
15. outerChord         (mm)                                   [10; 30]
16. outerAngle         (degrees)                              [2; 25]
