The propeller consists of:
1. A central hub (the rotating shaft), of FIXED radius 4 mm — this is the blade root.
2. An outer ring characterised by its radius (`impellerRadius` — the propeller's overall outer radius), its wall thickness
   (`impellerThickness`), and its height (derived automatically, not a parameter).
3. Blades, each divided into three radial sections spanning the hub (r = 4 mm) to the ring:
   - Inner section: the blade root, where the blade meets the central hub (radius 4 mm).
   - Middle section: between inner and outer; its radial position along the blade is set
     by `middlePos` — a fraction of the blade span (0 = root, 0.5 = the blade's exact
     midpoint, 1 = tip); it is positioned at radius 4 + middlePos·(impellerRadius − 4) mm. It need
     not be the geometric midpoint.
   - Outer section: the blade tip, at the outer radius (impellerRadius), furthest from the centre.
