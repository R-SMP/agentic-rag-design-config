- Generate a 3D propeller mesh (.obj) from the 17 design parameters
  using Grasshopper / RhinoCompute.
- Render the generated mesh from three fixed viewpoints (isometric,
  top, side) as PNG images.
- Run deterministic geometric quality checks on the mesh when the
  user enabled them at startup: watertightness, volume, degenerate
  face count.  Nothing beyond these metrics.
- Arithmetic via a built-in calculator.
- Answer questions about earlier runs in this session by reading
  other agents' histories (which parameters were used, what the
  inspectors reported, which files were produced).
- Regenerate geometry with modified parameter values — subject to
  the permission rules on varying user-provided numbers.
