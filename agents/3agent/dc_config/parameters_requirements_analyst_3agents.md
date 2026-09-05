<!-- SCAFFOLD - NOT THE FINAL TEXT ------------------------------------
     scoped fragment `parameters` for the Requirements Analyst, produced by
     MECHANICALLY CONCATENATING its two topology-5 parents:
       User Input Inspector + DC Output Inspector

     It exists so the 3-agent system assembles and its wiring can be
     verified BEFORE the prompts are authored.  It is a concatenation,
     NOT a union: it states some concepts twice, and it can carry rules
     that contradict each other or name agents topology 3 never builds.

     Replaced WHOLESALE at Stage 9 under the merge doctrine.  Do not
     hand-patch it here -- see
     extra_utilities/docs/active/topology3_rebuild_plan.md sections 4 and 5.
------------------------------------------------------------------- -->

### Global / ring
 1. bladeCount         (integer)                             — Number of blades [3; 6]
 2. impellerRadius     (mm)                                  — Outer radius of the impeller ring [60; 80]
 3. impellerThickness  (mm)                                  — Wall thickness of the outer ring [1; 5]

### Inner blade section
 4. innerThickness     (% of the INNER chord)                — Profile thickness [3; 24]
 5. innerMaxPos        (tenths of the INNER chord, integer)  — Chordwise position of max camber [2; 8]
 6. innerCamber        (% of the INNER chord)                — Profile camber [0; 9]
 7. innerChord         (mm)                                  — Chord length [3; 11]
 8. innerAngle         (degrees)                             — Angle of attack [2; 25]

### Middle blade section
 9. middlePos          (fraction of blade span, unitless)    — Middle-section position along the blade: 0 = root (INNER BLADE SECTION, r = 4 mm), 1 = tip [0.3; 0.7]
10. middleChord        (mm)                                  — Chord length [10; 30]
11. middleAngle        (degrees)                             — Angle of attack [2; 25]

### Outer blade section
12. outerThickness     (% of the OUTER chord)                — Profile thickness [3; 24]
13. outerMaxPos        (tenths of the OUTER chord, integer)  — Chordwise position of max camber [2; 8]
14. outerCamber        (% of the OUTER chord)                — Profile camber [0; 9]
15. outerChord         (mm)                                  — Chord length [10; 30]
16. outerAngle         (degrees)                             — Angle of attack [2; 25]

<!-- SCAFFOLD JOIN - everything below comes from the DC Output Inspector -->

### Global / ring
 1. bladeCount         (integer)                             <<DCOI_RANGES_ON>> [3; 6]<</DCOI_RANGES_ON>>
 2. impellerRadius     (mm)                                  <<DCOI_RANGES_ON>> [60; 80]<</DCOI_RANGES_ON>>
 3. impellerThickness  (mm)                                  <<DCOI_RANGES_ON>> [1; 5]<</DCOI_RANGES_ON>>

(The outer-ring HEIGHT is not a parameter — it is derived automatically to fit
the outer blade section.)

(The central hub is a FIXED cylinder of radius 8 mm — not a parameter.  It is
LARGER than the blade root at r = 4 mm, so the hub hides the innermost part of
each blade.)

### Inner blade section
 4. innerThickness     (% of the INNER chord)                <<DCOI_RANGES_ON>> [3; 24]<</DCOI_RANGES_ON>>
 5. innerMaxPos        (tenths of the INNER chord, integer)  <<DCOI_RANGES_ON>> [2; 8]<</DCOI_RANGES_ON>>
 6. innerCamber        (% of the INNER chord)                <<DCOI_RANGES_ON>> [0; 9]<</DCOI_RANGES_ON>>
 7. innerChord         (mm)                                  <<DCOI_RANGES_ON>> [3; 11]<</DCOI_RANGES_ON>>
 8. innerAngle         (degrees)                             <<DCOI_RANGES_ON>> [2; 25]<</DCOI_RANGES_ON>>

### Middle blade section
 9. middlePos      (fraction of blade span: 0 = root, the INNER BLADE SECTION,
                   at r = 4 mm; 1 = tip)<<DCOI_RANGES_ON>> [0.3; 0.7]<</DCOI_RANGES_ON>>
10. middleChord        (mm)                                  <<DCOI_RANGES_ON>> [10; 30]<</DCOI_RANGES_ON>>
11. middleAngle        (degrees)                             <<DCOI_RANGES_ON>> [2; 25]<</DCOI_RANGES_ON>>

(The middle section has NO thickness, camber or high-point of its own.)

### Outer blade section
12. outerThickness     (% of the OUTER chord)                <<DCOI_RANGES_ON>> [3; 24]<</DCOI_RANGES_ON>>
13. outerMaxPos        (tenths of the OUTER chord, integer)  <<DCOI_RANGES_ON>> [2; 8]<</DCOI_RANGES_ON>>
14. outerCamber        (% of the OUTER chord)                <<DCOI_RANGES_ON>> [0; 9]<</DCOI_RANGES_ON>>
15. outerChord         (mm)                                  <<DCOI_RANGES_ON>> [10; 30]<</DCOI_RANGES_ON>>
16. outerAngle         (degrees)                             <<DCOI_RANGES_ON>> [2; 25]<</DCOI_RANGES_ON>>
