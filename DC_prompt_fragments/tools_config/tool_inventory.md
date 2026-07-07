1. **generate_propeller_mesh** — write ``propeller_mesh.obj`` into the
   attempt folder from the 16 parameters (pass them plus ``output_dir``);
   returns the saved mesh path.
2. **render_and_check_mesh** — render the three views (isometric / top /
   side) and, when mesh checks are enabled, the quality metrics; pass it the
   mesh path ``generate_propeller_mesh`` returned plus ``output_dir``.
3. **calculate** — evaluate arithmetic / boolean expressions; batch every
   expression you need this turn into ONE call.
4. **list_attempts** — numbered summary of every attempt folder and which
   roles (parameters / mesh / renders / description) each holds.
5. **read_attempt(n, file)** — read one file from the n-th attempt (text
   inline; an image or mesh returns a path to hand on, e.g. to
   ``load_render_images``).
