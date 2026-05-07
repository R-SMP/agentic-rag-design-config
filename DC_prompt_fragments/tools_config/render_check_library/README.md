# Render / mesh-check library variants

Two interchangeable backends live behind the single LangChain tool
name ``render_and_check_mesh`` — exactly one is bound to the Tool
Caller per session, picked at startup by ``loader.py``.  Both
backends compute the same metrics (watertightness, volume,
degenerate-face count) on the same mesh and produce three PNG
renders (``render_isometric.png`` / ``render_top.png`` /
``render_side.png``) into the active attempt folder.

| Choice | Fragment | Backend |
|--------|----------|---------|
| 1      | ``trimesh.md`` | trimesh + pyrender |
| 2      | ``pyvista.md`` | PyVista (VTK)      |

Whichever fragment matches the user's startup pick is spliced into
the Tool Caller's system prompt at wiring time via the runtime
placeholder ``{render_check_library_block}``.  The other fragment
is loaded but unused for the session.

## Adding another backend

1. Implement the new tool under ``tools/render_mesh/`` so that it
   exports the SAME LangChain tool name (``render_and_check_mesh``)
   and matches the trimesh backend's argument signature, return-text
   shape, and append-only attempt-folder rules.
2. Register it in ``tools/__init__.py`` (extend ``RENDER_LIBRARIES``,
   add a branch in ``get_render_tool``, sync ``set_mesh_checks``).
3. Drop a new ``<library>.md`` fragment alongside ``trimesh.md`` /
   ``pyvista.md`` describing the backend's specifics.
4. Wire the fragment into ``agents/shared/prompts.py`` (read it as a
   module-level constant) and into ``agents/tool_caller/tool_caller.py``
   (extend the lookup that picks ``RENDER_CHECK_LIBRARY_*`` based on
   ``self.render_library``).
5. Extend the startup question in ``agents/loader.py`` so the user
   can pick the new option.
