### Global / ring
 1. bladeCount         (integer)                             — Number of blades<<DCOI_RANGES_ON>> [3; 6]<</DCOI_RANGES_ON>>
 2. impellerRadius     (mm)                                  — Ring MID-WALL radius (outer face = +impellerThickness/2)<<DCOI_RANGES_ON>> [60; 80]<</DCOI_RANGES_ON>>
 3. impellerThickness  (mm)                                  — Wall thickness of the outer ring<<DCOI_RANGES_ON>> [1; 5]<</DCOI_RANGES_ON>>

(The outer-ring HEIGHT is not a parameter — it is derived automatically to fit
the outer blade section.)

(The central hub — a FIXED cylinder of radius 8 mm — is not a parameter either.)

### Inner blade section
 4. innerThickness     (% of the INNER chord)                — Profile thickness<<DCOI_RANGES_ON>> [3; 24]<</DCOI_RANGES_ON>>
 5. innerMaxPos        (tenths of the INNER chord, integer)  — Chordwise position of max camber<<DCOI_RANGES_ON>> [2; 8]<</DCOI_RANGES_ON>>
 6. innerCamber        (% of the INNER chord)                — Profile camber<<DCOI_RANGES_ON>> [0; 9]<</DCOI_RANGES_ON>>
 7. innerChord         (mm)                                  — Chord length<<DCOI_RANGES_ON>> [3; 11]<</DCOI_RANGES_ON>>
 8. innerAngle         (degrees)                             — Angle of attack<<DCOI_RANGES_ON>> [2; 25]<</DCOI_RANGES_ON>>

### Middle blade section
 9. middlePos          (fraction of blade span, unitless)    — Middle-section position along the blade: 0 = root (INNER BLADE SECTION, r = 4 mm), 1 = tip<<DCOI_RANGES_ON>> [0.3; 0.7]<</DCOI_RANGES_ON>>
10. middleChord        (mm)                                  — Chord length<<DCOI_RANGES_ON>> [10; 30]<</DCOI_RANGES_ON>>
11. middleAngle        (degrees)                             — Angle of attack<<DCOI_RANGES_ON>> [2; 25]<</DCOI_RANGES_ON>>

(The middle section has NO thickness, camber or high-point of its own.)

### Outer blade section
12. outerThickness     (% of the OUTER chord)                — Profile thickness<<DCOI_RANGES_ON>> [3; 24]<</DCOI_RANGES_ON>>
13. outerMaxPos        (tenths of the OUTER chord, integer)  — Chordwise position of max camber<<DCOI_RANGES_ON>> [2; 8]<</DCOI_RANGES_ON>>
14. outerCamber        (% of the OUTER chord)                — Profile camber<<DCOI_RANGES_ON>> [0; 9]<</DCOI_RANGES_ON>>
15. outerChord         (mm)                                  — Chord length<<DCOI_RANGES_ON>> [10; 30]<</DCOI_RANGES_ON>>
16. outerAngle         (degrees)                             — Angle of attack<<DCOI_RANGES_ON>> [2; 25]<</DCOI_RANGES_ON>>
