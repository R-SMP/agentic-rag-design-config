<<IF:tool:render_blade_sections>>1. **render_blade_sections** — render JUST the blade cross-sections
   (Inner, Middle, Outer) as one flat PNG, from an attempt's own
   ``parameters.json`` (pass ONLY that file's path).  No mesh and no 3D
   renders are produced.  Returns the PNG path.
2. **generate_and_render_propeller**<</IF:tool:render_blade_sections>><<IFNOT:tool:render_blade_sections>>1. **generate_and_render_propeller**<</IFNOT:tool:render_blade_sections>> — build
   ``propeller_mesh.obj`` into an attempt folder from that attempt's own
   ``parameters.json`` (pass ONLY that file's path — the tool reads the
   values and writes beside them) AND, as its built-in final step, render
   the three views (isometric / top / side).  Returns the mesh path
   followed by the render+check report (the three render paths + any
   warnings).
<<IF:tool:render_blade_sections>>3.<</IF:tool:render_blade_sections>><<IFNOT:tool:render_blade_sections>>2.<</IFNOT:tool:render_blade_sections>> **calculate** — evaluate arithmetic / boolean expressions.
<<IF:tool:render_blade_sections>>4.<</IF:tool:render_blade_sections>><<IFNOT:tool:render_blade_sections>>3.<</IFNOT:tool:render_blade_sections>> **read_attempts(local_attempt_numbers=None)** — with no argument, a
   numbered summary of every attempt folder: which roles (parameters /
   mesh / renders / description) each holds, plus its ``description.txt``.
   Given attempt numbers, the same for just those, each with its full
   ``parameters.json``.  Either way every render and mesh file is listed
   as an absolute path to hand on to whoever can load it.
