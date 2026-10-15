**generate_and_render_propeller** — build
   ``propeller_mesh.obj`` into an attempt folder from that attempt's own
   ``parameters.json`` (pass ONLY that file's path — the tool reads the
   values and writes beside them) AND, as its built-in final step, render
   the three views (isometric / top / side).  Returns the mesh path
   followed by the render+check report (the three render paths + any
   warnings).
