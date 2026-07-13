All artifacts produced for a single design generation live INSIDE a
per-attempt folder under ``logs/attempts/<TS>_<NNN>_<slug>/``.  The
folder is created via ``new_attempt`` by the DC Input Creator (or, only
as a special-case fallback, the Orchestrator); downstream agents target
the same folder by reading the ``Current attempt:`` label in their hand-
off.

Inside an attempt folder the canonical filenames are:
- **DC inputs** — ``parameters.json`` (written by the DC Input
  Creator's ``write_parameters`` tool).
- **DC output / mesh** — ``propeller_mesh.obj`` (written by the
  Tool Caller's ``generate_propeller_mesh`` tool).
- **Render images** — ``render_isometric.png``, ``render_top.png``,
  ``render_side.png`` (written by the Tool Caller's
  ``render_and_check_mesh`` tool).
- **Description** — optional ``description.txt`` written at folder
  creation time by whichever agent invoked ``new_attempt``.

An attempt folder MAY be partial: it might carry only
``parameters.json`` (a parameter set was authored but no mesh ever
generated), only parameters + mesh (renders never produced), or any
other combination.  ``parameters.json`` and the mesh are append-only —
their write tools refuse to overwrite an existing one in any attempt
folder.  The render/QC tool instead REUSES existing renders in place
(identical parameters give identical geometry), so re-running it on an
attempt that already has renders needs no new attempt.

There is no shared "current parameters.json" or "current mesh
output" location elsewhere in the project — every read/write goes
through an attempt folder.
