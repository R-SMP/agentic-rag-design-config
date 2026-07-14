1. **generate_and_render_propeller** — build ``propeller_mesh.obj`` into the
   attempt folder from the 16 parameters (pass them plus ``output_dir``) AND,
   as its built-in final step, render the three views (isometric / top / side)
   and — when mesh checks are enabled — the quality metrics.  ONE call does
   both; there is no separate render tool to call.  Returns the mesh path
   followed by the render+check report (the three render paths + any warnings).
2. **calculate** — evaluate arithmetic / boolean expressions; batch every
   expression you need this turn into ONE call.
3. **list_attempts** — numbered summary of every attempt folder and which
   roles (parameters / mesh / renders / description) each holds.
4. **read_attempt(n, file)** — read one file from the n-th attempt (text
   inline; an image or mesh returns a path to hand on, e.g. to
   ``load_render_images``).
