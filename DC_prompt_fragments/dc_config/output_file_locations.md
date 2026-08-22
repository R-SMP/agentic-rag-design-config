All artifacts produced for a single design generation live INSIDE a
per-attempt folder under ``attempts/<TS>_<NNN>_<slug>/``.

Inside an attempt folder the canonical filenames are:
- **DC inputs** — ``parameters.json``.
- **DC output / mesh** — ``propeller_mesh.obj``.
- **Render images** — ``render_isometric.png``, ``render_top.png``,
  ``render_side.png``; plus ``render_blade_sections.png`` (or
  ``render_blade_sections_grid.png`` in grid mode), written by the
  ``render_blade_sections`` tool.
- **Description** — optional ``description.txt``.

There is no shared "current parameters.json" or "current mesh
output" location elsewhere in the project — every read/write goes
through an attempt folder.
