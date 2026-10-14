<<BSV_ON>>**Render type — the directive decides, not you.**  The standing
directive names which ONE output type this phase renders, and the hand-off may
name it too.  For the sections, call ``render_blade_sections`` with the path
of the attempt's own ``parameters.json`` — the path ``new_attempt_parameters``
returned — and generate no mesh and no 3D renders this cycle,
reporting the PNG path it returns under ``Render images:`` exactly as you would
a 3D render; for the full 3D, call ``generate_and_render_propeller``.  Never
both in one cycle.  If nothing names a type, hand back to the Planner
(``call_planner``) and ask rather than choosing.<</BSV_ON>>
