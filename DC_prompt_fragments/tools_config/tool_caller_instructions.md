- The hand-off carries TWO load-bearing labels that you MUST copy
  verbatim into your tool calls — do NOT guess, rename, or shorten
  them:
    - ``Current attempt:`` — the absolute path of the attempt
      folder for this generation cycle.  Pass it as the
      ``output_dir`` argument to BOTH ``generate_propeller_mesh``
      and ``render_and_check_mesh``.  All artifacts produced this
      cycle live inside this folder; the tools refuse to overwrite
      anything already there.
    - ``Parameters file:`` — the absolute path of
      ``parameters.json``.  This file lives inside the attempt
      folder named above; the path will be of the form
      ``<Current attempt>/parameters.json``.
- Call ``read_parameters`` first using the ``Parameters file:`` path.
- When you receive approved parameters, call ``generate_propeller_mesh``
  with all 17 values AND the ``Current attempt:`` path as
  ``output_dir``.  Capture the absolute mesh path from its return
  message and pass that exact path as the ``mesh_path`` argument to
  ``render_and_check_mesh`` — together with the same ``Current
  attempt:`` path as ``output_dir``.  Never call either tool with a
  guessed path.
- Call ``calculate`` for any arithmetic you actually need (chord
  totals, blade-spacing checks, etc.) instead of doing the math in
  prose.  ``calculate`` takes a LIST of expressions and returns all
  results in one tool result — batch every expression you need this
  turn into a single call (e.g.
  ``calculate(expressions=['innerChord + outerChord', '2 * 3.14159 * impellerRadius',
  'impellerRadius / middleChord'])``); do not issue one call per expression.
- After the utility tools return, invoke the appropriate routing tool.
  Its ``message`` argument carries the hand-off to the next agent and
  MUST include the same ``Current attempt:`` line you received, plus
  a ``Render images:`` block listing the absolute paths of the three
  render PNGs (verbatim from ``render_and_check_mesh``'s return
  text).  Without ``Current attempt:`` the DC Output Inspector
  cannot locate the artifacts it is meant to analyse.
- Do NOT call your utility tools to "fix" a mesh — there are no
  edit / repair / remesh / boolean-union / weld / prune /
  custom-filename tools.  When the geometry is wrong, ESCALATE so
  the Planner can direct a parameter change and the Orchestrator /
  DCIC opens a new attempt for the next try.
- If the hand-off is missing ``Current attempt:``, ESCALATE — do
  NOT call ``new_attempt`` yourself (you are not bound to it) and
  do NOT proceed by writing into a guessed path.
