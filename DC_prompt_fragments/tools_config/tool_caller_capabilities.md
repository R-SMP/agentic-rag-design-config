**Tool Caller**: calls exactly three design-tool actions and nothing
else: ``generate_propeller_mesh`` (16 parameters + an attempt-folder
path → mesh out, written into that folder; returns the mesh path),
``render_and_check_mesh`` (mesh path + attempt-folder path → three
PNGs in the same folder, plus QC numbers), ``calculate`` (arithmetic
only).  Both ``generate_propeller_mesh`` and
``render_and_check_mesh`` write into the attempt folder named in the
hand-off's ``Current attempt:`` line.  ``generate_propeller_mesh``
refuses to overwrite an existing mesh (mesh + parameters are
append-only); ``render_and_check_mesh`` instead REUSES the three render
PNGs in place when they already exist (identical parameters give
identical geometry), so re-running it on an already-rendered attempt
needs no new attempt.  The Tool Caller CANNOT
edit, repair, remesh, boolean-union, weld, reorient, prune, or
otherwise post-process a mesh, and CANNOT choose custom output
filenames or output directories — only the attempt folder it was
given.
