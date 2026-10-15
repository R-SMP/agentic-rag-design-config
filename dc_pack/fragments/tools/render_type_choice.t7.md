<<IF:tool:render_blade_sections>>**Render type — the directive decides, not you.**  The standing
directive names which ONE output type this phase renders, and the hand-off may
name it too.  For the sections, call ``render_blade_sections`` with the
``Parameters file:`` path and generate no mesh and no 3D renders this cycle,
reporting the PNG path it returns under ``Render images:`` exactly as you would
a 3D render; for the full 3D, call ``generate_and_render_propeller``.  Never
both in one cycle.  If nothing names a type, route back and ask rather than
choosing.<</IF:tool:render_blade_sections>>
