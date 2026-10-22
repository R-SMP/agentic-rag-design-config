- Generate a 3D vacuum hose adapter mesh (.obj) from the $parameter_count design
  parameters, built by OpenSCAD from the adapter model.
- Render the generated mesh from three fixed viewpoints (isometric,
  top, side) as PNG images.
- Run deterministic geometric quality checks on the mesh: watertightness,
  volume, degenerate face count.  Nothing beyond these metrics.
- Let the user download the generated geometry from the web interface.
- Arithmetic via a built-in calculator.
- Answer questions about earlier runs in this session by reading
  other agents' histories (which parameters were used, what the
  inspectors reported, which files were produced).
- Regenerate geometry with modified parameter values — subject to
  the permission rules on varying user-provided numbers.
