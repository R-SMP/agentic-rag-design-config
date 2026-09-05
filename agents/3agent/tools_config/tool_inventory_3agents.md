1. **generate_and_render_propeller** — build ``propeller_mesh.obj`` into an
   attempt folder from that attempt's own ``parameters.json`` (pass ONLY that
   file's path — the tool reads the values and writes beside them) AND,
   as its built-in final step, render the three views (isometric / top / side)
   and — when mesh checks are enabled — the quality metrics.  ONE call does
   both; there is no separate render tool to call.  Returns the mesh path
   followed by the render+check report (the three render paths + any warnings).
2. **calculate** — evaluate arithmetic / boolean expressions.
3. **read_attempts(attempt_numbers=None)** — with no argument, a numbered
   summary of every attempt folder: which roles (parameters / mesh /
   renders / description) each holds, plus its ``description.txt``.  Given
   attempt numbers, the same for just those, each with its full
   ``parameters.json``.  Either way every render and mesh file is listed as
   an absolute path to hand on to whoever can load it.
