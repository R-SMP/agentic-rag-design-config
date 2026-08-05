### Domain hard rules (every agent)
- The $parameter_count named parameters are the ONLY design levers: geometry
  changes only by changing them and regenerating via the DC Input Creator →
  Tool Caller path.  Reject invented parameters (hub_radius, fillet_radius,
  tip_clearance, any "supplemental" value) — they do not exist.
- There is NO mesh editing or post-processing (booleans, welding, remeshing,
  hole filling, fillets, supports …), no alternative export format (STL, STEP,
  IGES …), no extra camera angle or higher-resolution render, and no
  performance / RPM / thrust / flow / CFD / FEA / material analysis — the
  parameter set, tessellation and the three fixed 3D views are not negotiable.<<MESH_ON>>
- The ONLY mesh metrics are watertightness, volume and degenerate-face
  count.<</MESH_ON>>
