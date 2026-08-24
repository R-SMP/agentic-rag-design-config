The propeller consists of:
1. A central hub (the rotating shaft), of FIXED radius 8 mm.  It is not a design
   parameter, and it is NOT where the blade starts — see the inner section below.
2. An outer ring characterised by its radius (`impellerRadius` — the propeller's overall outer radius), its wall thickness
   (`impellerThickness`), and its height (derived automatically, not a parameter).
3. Blades, each divided into three radial sections spanning r = 4 mm to the ring:
   - Inner section: the blade root, FIXED at radius 4 mm.  That is SMALLER than the
     hub radius, so the blade root is buried inside the hub and the hub hides the
     innermost part of each blade — do not confuse the two radii.
   - Middle section: between inner and outer; its radial position along the blade is set
     by `middlePos` — a fraction of the blade span (0 = root, 0.5 = the blade's exact
     midpoint, 1 = tip); its radius follows from middlePos and the ring radius, and is
     not necessarily the blade's midpoint.
   - Outer section: the blade tip, at the outer radius (impellerRadius), furthest from the centre.
