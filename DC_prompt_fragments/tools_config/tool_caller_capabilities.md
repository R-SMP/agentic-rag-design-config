**Tool Caller**: calls exactly three design-tool actions and nothing
else: ``generate_propeller_mesh`` (17 parameters + an attempt-folder
path → mesh out, written into that folder; returns the mesh path),
``render_and_check_mesh`` (mesh path + attempt-folder path → three
PNGs in the same folder, plus QC numbers), ``calculate`` (arithmetic
only).  Both ``generate_propeller_mesh`` and
``render_and_check_mesh`` write into the attempt folder named in the
hand-off's ``Current attempt:`` line — they refuse to overwrite an
existing mesh or render in that folder.  The Tool Caller CANNOT
edit, repair, remesh, boolean-union, weld, reorient, prune, or
otherwise post-process a mesh, and CANNOT choose custom output
filenames or output directories — only the attempt folder it was
given.
