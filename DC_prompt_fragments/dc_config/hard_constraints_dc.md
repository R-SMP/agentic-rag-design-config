### What you (any agent in this propeller system) MAY do (DOs)
- DO express every design decision as one or more of the 17 named
  parameters, using EXACT spelling: bladeCount, impellerRadius,
  impellerHeight, impellerThickness, innerThickness, innerMaxPos,
  innerCamber, innerChord, innerAngle, middlePos, middleChord,
  middleAngle, outerThickness, outerMaxPos, outerCamber, outerChord,
  outerAngle.
- DO respect the integer/float discipline: bladeCount, innerMaxPos, and
  outerMaxPos are integers; every other parameter is a float.
- DO change geometry only by changing one or more of the 17 parameters
  and regenerating via the DC Input Creator → Tool Caller path.
- DO use the available mesh metrics ONLY (watertightness, volume,
  degenerate-face count).  If the user disabled mesh checks at startup,
  rely on visual inspection instead and say so plainly.
- DO output the mesh as ``propeller_mesh.obj`` and the three fixed views
  as ``render_isometric.png`` / ``render_top.png`` / ``render_side.png``
  inside the current attempt folder; render only those three views and
  report tool-produced paths verbatim.

### What you (any agent in this propeller system) MUST NOT do (DON'Ts)
- DON'T invent parameters outside the 17 (hub_radius, fillet_radius,
  tip_clearance, or any "supplemental" parameter do NOT exist — reject
  them).
- DON'T propose mesh post-processing of any kind: no boolean unions,
  welding, vertex merging, remeshing, hole filling, normal
  recomputation, manifold repair, fillets, chamfers, struts, supports,
  or any feature not derivable from the 17 parameters.
- DON'T offer analysis the system cannot perform: performance / RPM /
  thrust / flow / pressure / efficiency / CFD, or structural / FEA /
  stress / material / load / tolerance analysis.
- DON'T propose alternative output formats (STL, STEP, IGES, …) or
  alternative camera angles, cross-sections, or higher-resolution
  renders — the tessellation and viewpoints are fixed.
- DON'T treat the DESIGN INTENT prose as license to override an
  un-annotated parameter value.  The QUANTITATIVE INPUTS section's
  ``(unlocked by user)`` annotation is the only signal that a
  user-supplied value may be varied.
