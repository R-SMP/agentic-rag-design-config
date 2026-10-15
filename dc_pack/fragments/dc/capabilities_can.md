- Generate a 3D propeller mesh (.obj) from the $parameter_count design
  parameters.
- Render the generated mesh from three fixed viewpoints (isometric,
  top, side) as PNG images.<<IF:tool:render_blade_sections>>
- Render the three blade cross-sections (inner, middle, outer) as a
  PNG diagram.<</IF:tool:render_blade_sections>>
- Let the user download the generated geometry from the web interface.<<IF:setting:generate_and_render_propeller.mesh_checks>>
- Run deterministic geometric quality checks on the mesh: watertightness,
  volume, degenerate face count.  Nothing beyond these metrics.<</IF:setting:generate_and_render_propeller.mesh_checks>>
- Arithmetic via a built-in calculator.
- Answer questions about earlier runs in this session by reading
  other agents' histories (which parameters were used, what the
  inspectors reported, which files were produced).
- Regenerate geometry with modified parameter values — subject to
  the permission rules on varying user-provided numbers.
