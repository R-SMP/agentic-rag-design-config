### Domain hard rules
- The $parameter_count named parameters are the ONLY design levers and there
  is no mesh-editing capability: geometry changes only by changing them and
  regenerating.  Reject invented parameters — they do not exist.<<IF:setting:generate_and_render_propeller.mesh_checks>>
- The ONLY mesh metrics are watertightness, volume and degenerate-face
  count.<</IF:setting:generate_and_render_propeller.mesh_checks>>
