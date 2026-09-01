**Tool Caller**: calls the design tools: ``generate_and_render_propeller``
(the path of an attempt's ``parameters.json`` → it reads the values, builds
the mesh AND, as its built-in final step, renders the views + runs the
QC checks when they are enabled, all written into that file's own folder)<<BSV_ON>>,
``render_blade_sections`` (the three blade cross-sections alone, as a flat
image — no 3D mesh)<</BSV_ON>> and ``calculate``.  The Tool Caller CANNOT
edit, repair, remesh, boolean-union, weld, reorient, prune, or
otherwise post-process a mesh, and CANNOT choose custom output
filenames or output directories.
