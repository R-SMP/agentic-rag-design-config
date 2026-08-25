### Domain hard rules
- The $parameter_count named parameters are the ONLY design levers:
  geometry changes only by changing them and regenerating.  Reject invented
  parameters (hub_radius, fillet_radius, tip_clearance, any "supplemental"
  value) — they do not exist.<<MESH_ON>>
- The ONLY mesh metrics are watertightness, volume and degenerate-face
  count.<</MESH_ON>>
