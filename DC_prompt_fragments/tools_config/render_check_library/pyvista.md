## Active mesh-check backend: PyVista / VTK (renders via pyrender)

For this session the bound ``render_and_check_mesh`` tool runs the
deterministic mesh checks on the **PyVista (VTK)** backend.  The
three visual renders go through the SAME pyrender pipeline used by
the trimesh-metrics backend, so the PNGs are visually identical to
what the trimesh backend would produce.  The tool's contract
(arguments, three render filenames, append-only attempt-folder
rules, ``set_mesh_checks`` toggle) is unchanged.

A few specifics worth keeping in mind so you read the tool's return
text correctly:

- The mesh is loaded with ``pyvista.read`` for the metric checks.
  When the .obj contains multiple geometry groups, the resulting
  MultiBlock is merged into a single PolyData before any check runs.
  The merged mesh is triangulated so per-cell area arrays have
  well-defined semantics.
- Watertightness is the conjunction of ``n_open_edges == 0`` (no
  boundary edges) AND ``is_manifold`` (no edges shared by 3+ faces).
  This matches trimesh's "every edge shared by exactly two faces"
  semantics; the ``Watertight: yes/no`` line in the report has the
  same meaning under both backends.
- Volume is computed only when the mesh is watertight, via a direct
  divergence-theorem sum over triangles (PyVista's built-in
  ``volume`` property is unsigned, so the tool computes the signed
  value itself).  A non-positive value means the surface normals
  are inverted, and the tool surfaces this as a WARNING line.
- Degenerate-face count uses VTK's ``compute_cell_sizes`` ``Area``
  array with the same ``< 1e-10`` mm² threshold the trimesh backend
  uses; the numbers from the two backends should match closely on
  the same mesh.
- Renders are produced by the shared pyrender off-screen pipeline
  (white background, smooth shading, three directional lights).
  All three PNGs are 800×600 — identical pipeline to the trimesh
  backend.
