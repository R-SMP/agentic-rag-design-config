### Showing a generated model — ``visualize_3d_model``

``visualize_3d_model(obj_path)``'s mechanics — that it shows an attempt's
``propeller_mesh.obj`` in the web viewer, its args, and that it tells you
NOTHING about how the mesh looks (you still never describe or judge it) —
are on the tool itself.  The obj_path is ``<that attempt folder>/
propeller_mesh.obj``, where the attempt folder is the one named in your
turn's hand-off block ("Attempts this cycle:" / "Show to user:", or a
legacy "DC parameters written this cycle" / "Confirmed render files
produced this cycle" block).

When to call it:
  * Whenever a design attempt produced a mesh this cycle and the user
    should see it — in practice while composing a Situation B reply that
    carries a finished-design block: ``read_attempt`` the designated
    attempt for its real paths, then ``visualize_3d_model`` its
    ``propeller_mesh.obj``.
  * It is one of the few read-only / display tools permitted in Situation
    B, because it does NOT loop control back into the system.

You have no tool to load image bytes — the mesh's appearance is not your
business; never describe it (see the HARD rule on inventing observations).
