## Active render / mesh-check backend: trimesh + pyrender

For this session the bound ``render_and_check_mesh`` tool runs on the
**trimesh + pyrender** backend.  The contract is identical regardless
of backend (same arguments, same three render filenames, same
metrics), but a few specifics are worth keeping in mind so you read
the tool's return text correctly:

- The mesh is loaded with ``trimesh.load``.  When the .obj contains
  multiple geometry groups, trimesh returns a Scene which is
  concatenated into a single mesh before any check runs.
- Watertightness is reported via trimesh's ``mesh.is_watertight``,
  which checks that every edge is shared by exactly two faces (no
  holes, no non-manifold edges, consistent winding).
- Volume is computed only when the mesh is watertight.  Volume is
  signed: a non-positive value means the surface normals are
  inverted, and the tool surfaces this as a WARNING line.
- Degenerate-face count uses trimesh's per-face area array with the
  same ``< 1e-10`` mm² threshold the PyVista backend uses; the
  numbers from the two backends should match closely on the same
  mesh.
- Renders are produced by an off-screen pyrender pipeline (white
  background, smooth shading, three directional lights).  All three
  PNGs are 800×600.
