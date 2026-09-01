All artifacts produced for a single design generation live INSIDE a
per-attempt folder under ``attempts/<TS>_<NNN>_<slug>/``.

It holds ``parameters.json``, ``propeller_mesh.obj``, the ``render_*.png``
files and an optional ``description.txt``.

There is no shared "current parameters.json" or "current mesh
output" location elsewhere in the project — every read/write goes
through an attempt folder.
