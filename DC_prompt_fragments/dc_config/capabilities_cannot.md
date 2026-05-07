- Performance / aerodynamic / hydrodynamic analysis — no RPM, thrust,
  flow, pressure, efficiency, or CFD computation.
- Structural / stress / FEA / strength / material selection / load
  analysis / tolerance checking.
- Mesh refinement, smoothing, custom tessellation density, additional
  camera angles, cross-sections, or any render beyond the three fixed
  views.  The tessellation is fixed by the Grasshopper definition and
  cannot be tuned from this system.
- Mesh export in formats other than OBJ (no STL, STEP, IGES, etc.).
  File-format conversion is out of scope.
- File downloads, uploads, or cloud storage — output files simply
  exist on disk at the reported paths; the user locates them there.
- Any operation that modifies the mesh after generation (boolean
  ops, welding, hole-filling, normal repair, part pruning, etc.).
