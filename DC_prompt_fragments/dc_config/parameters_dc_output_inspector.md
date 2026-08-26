### Global / ring
 1. bladeCount         (integer)<<DCOI_RANGES_ON>>              [3; 6]<</DCOI_RANGES_ON>>
 2. impellerRadius     (mm)<<DCOI_RANGES_ON>>                   [60; 80]<</DCOI_RANGES_ON>>
 3. impellerThickness  (mm)<<DCOI_RANGES_ON>>                   [1; 5]<</DCOI_RANGES_ON>>

(The outer-ring HEIGHT is not a parameter — it is derived automatically to fit
the outer blade section.)

(The central hub is a FIXED cylinder of radius 8 mm — not a parameter.  It is
LARGER than the blade root at r = 4 mm, so the hub hides the innermost part of
each blade.)

### Inner blade section
 4. innerThickness  (% of chord)<<DCOI_RANGES_ON>>              [3; 24]<</DCOI_RANGES_ON>>
 5. innerMaxPos     (integer, tenths of chord)<<DCOI_RANGES_ON>> [2; 8]<</DCOI_RANGES_ON>>
 6. innerCamber     (% of chord)<<DCOI_RANGES_ON>>              [0; 9]<</DCOI_RANGES_ON>>
 7. innerChord      (mm)<<DCOI_RANGES_ON>>                      [3; 11]<</DCOI_RANGES_ON>>
 8. innerAngle      (degrees)<<DCOI_RANGES_ON>>                 [2; 25]<</DCOI_RANGES_ON>>

### Middle blade section
 9. middlePos      (fraction of blade span: 0 = root, the INNER BLADE SECTION,
                   at r = 4 mm; 1 = tip)<<DCOI_RANGES_ON>>      [0.3; 0.7]<</DCOI_RANGES_ON>>
10. middleChord    (mm)<<DCOI_RANGES_ON>>                       [10; 30]<</DCOI_RANGES_ON>>
11. middleAngle    (degrees)<<DCOI_RANGES_ON>>                  [2; 25]<</DCOI_RANGES_ON>>

(The middle section has NO thickness, camber or high-point of its own.)

### Outer blade section
12. outerThickness (% of chord)<<DCOI_RANGES_ON>>               [3; 24]<</DCOI_RANGES_ON>>
13. outerMaxPos    (integer, tenths of chord)<<DCOI_RANGES_ON>>  [2; 8]<</DCOI_RANGES_ON>>
14. outerCamber    (% of chord)<<DCOI_RANGES_ON>>               [0; 9]<</DCOI_RANGES_ON>>
15. outerChord     (mm)<<DCOI_RANGES_ON>>                       [10; 30]<</DCOI_RANGES_ON>>
16. outerAngle     (degrees)<<DCOI_RANGES_ON>>                  [2; 25]<</DCOI_RANGES_ON>>
