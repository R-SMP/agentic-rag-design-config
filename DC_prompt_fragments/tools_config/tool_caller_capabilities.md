**Tool Caller**: calls exactly two design-tool actions and nothing
else: ``generate_and_render_propeller`` (the path of an attempt's
``parameters.json`` → it reads the values, builds the mesh AND, as its
built-in final step, renders the three views + runs the QC checks, all written
into that file's own folder; returns the mesh path and the three render paths)
and ``calculate`` (arithmetic only).  It REUSES an existing
``propeller_mesh.obj`` in place (mesh + parameters are append-only — never
overwritten) and REUSES the three render PNGs when they already exist
(identical parameters give identical geometry), so re-running it on an
already-built attempt needs no new attempt.  The Tool Caller CANNOT
edit, repair, remesh, boolean-union, weld, reorient, prune, or
otherwise post-process a mesh, and CANNOT choose custom output
filenames or output directories — only the attempt folder it was
given.
