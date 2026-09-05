- Generate a 3D propeller mesh (.obj) from the $parameter_count design
  parameters.
- Render the generated mesh from three fixed viewpoints (isometric,
  top, side) as PNG images.<<BSV_ON>>
- Render the three blade cross-sections (inner, middle, outer) as a
  PNG diagram.<</BSV_ON>>
- Let the user download the generated geometry from the web interface.<<MESH_ON>>
- Run deterministic geometric quality checks on the mesh: watertightness,
  volume, degenerate face count.  Nothing beyond these metrics.<</MESH_ON>>
- Arithmetic via a built-in calculator.
- Answer questions about earlier runs in this session by reading
  other agents' histories (which parameters were used, what the
  inspectors reported, which files were produced).
- Regenerate geometry with modified parameter values — subject to
  the permission rules on varying user-provided numbers.
