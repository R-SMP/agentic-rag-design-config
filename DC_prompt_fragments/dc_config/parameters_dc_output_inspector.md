### Global / ring
 1. bladeCount         (integer)
 2. impellerRadius     (mm)
 3. impellerThickness  (mm)

(The outer-ring HEIGHT is not a parameter — it is derived automatically to fit
the outer blade section.)

### Inner blade section
 4. innerThickness  (% of chord)
 5. innerMaxPos     (integer, tenths of chord)
 6. innerCamber     (% of chord)
 7. innerChord      (mm)
 8. innerAngle      (degrees)

### Middle blade section
 9. middlePos      (fraction of blade span: 0 = root at r = 4 mm, 1 = tip)
10. middleChord    (mm)
11. middleAngle    (degrees)

(The middle section has NO thickness, camber or high-point of its own — its
profile is interpolated between the inner and outer sections.)

### Outer blade section
12. outerThickness (% of chord)
13. outerMaxPos    (integer, tenths of chord)
14. outerCamber    (% of chord)
15. outerChord     (mm)
16. outerAngle     (degrees)
