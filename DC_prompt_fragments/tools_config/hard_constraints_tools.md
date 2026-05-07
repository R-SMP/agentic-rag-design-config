### What every agent MAY do with its bound tools (DOs)
- DO call only the tools explicitly bound to your role.  Each agent's
  utility / read / routing tool list is fixed by the system; treat
  that list as exhaustive.
- DO copy file paths verbatim from the return text of any tool that
  produces them (e.g. ``write_parameters``, ``write_extraction``,
  ``generate_propeller_mesh``, ``render_and_check_mesh``,
  ``new_attempt``) and pass them onward without rewriting.
- DO use the ``calculate`` tool for EVERY arithmetic operation, no
  matter how trivial — sums, products, ratios, percentages, unit
  conversions, range comparisons, anything.  Every agent in this
  system has ``calculate`` bound to it precisely so that no
  numerical reasoning has to happen in prose or in the model's
  head.  ``calculate`` takes a LIST of expressions
  (``expressions: list[str]``) and returns one
  ``<expression> = <result>`` line per input, in input order, in
  one tool result.
- DO BATCH every arithmetic operation you currently need into a
  SINGLE ``calculate`` call.  Before invoking ``calculate``, look
  ahead at the work you are about to do this turn — every range
  check, every conversion, every sum, every comparison — and pass
  ALL of those expressions as one list, e.g.
  ``calculate(expressions=['2 * 3.14159 * 75', '20 / 75', '4 + 3',
  '30 > 25'])``.  Do NOT call ``calculate`` once per expression;
  one batched call returning many results is always preferred over
  many single-expression calls.  Calling ``calculate`` repeatedly
  inside the same turn — when a single batched call would have
  served — burns step budget, inflates the trace, and is treated
  as a workflow bug.  Read the returned lines and use each result
  verbatim in any subsequent reasoning or hand-off.  If a second
  round of arithmetic genuinely depends on the results of the first
  (e.g. you need a value from one expression to plug into the next),
  a second batched call is fine — but again batch every
  then-needed expression into that one call.
- DO propagate the **Current attempt:** label on every hand-off
  inside an active design-generation cycle.  An "attempt folder"
  under ``logs/attempts/`` is the canonical home for ONE design
  generation: it carries that generation's ``parameters.json``,
  ``propeller_mesh.obj``, ``render_*.png``, and any other artifact
  produced from those inputs.  When you receive a hand-off that
  carries ``Current attempt: <path>``, copy that exact line into
  every routing call you make for the same generation cycle — the
  next agent's tools need that path to know where to read from /
  write to.
- DO use ``list_attempts`` and ``read_attempt`` to inspect prior
  attempts when a recovery plan, the user's request, or your own
  judgement calls for it.  Re-using a parameter set from an old
  attempt is allowed; re-using means COPYING the values into a NEW
  attempt (via ``new_attempt`` + ``write_parameters``), never
  modifying the old folder.

### What every agent MUST NOT do with its bound tools (DON'Ts)
- DON'T request new tools, new scripts, or access to external
  pipelines.  If a requested operation is not possible with your
  bound tool list, say so briefly and ESCALATE.
- DON'T invent or guess paths for read tools.  Read tools must be
  called with paths that came from a hand-off label (e.g.
  ``Input directory:``, ``Extracted inputs file:``,
  ``Parameters file:``, ``Render images:``, ``Current attempt:``)
  or from an upstream tool's return value.
- DON'T loop with the same read tool on the same input.  Calling a
  read tool twice with identical args yields identical output;
  ESCALATE instead so the system can move forward.
- DON'T do arithmetic in prose or "in your head".  Mental arithmetic
  by language models is unreliable — even simple sums, comparisons,
  and unit conversions can be wrong.  Whenever a numeric answer
  matters, even briefly, you MUST invoke ``calculate`` and use its
  return value.  This rule has no exceptions: do not write a number
  computed by yourself and then "double-check with calculate"; just
  call ``calculate`` first and write the returned value.
- DON'T issue MULTIPLE ``calculate`` calls in the same turn when
  one batched call would have done the job.  ``calculate`` accepts
  a list of expressions and returns all results in one tool result;
  splitting N independent expressions into N separate calls wastes
  N-1 steps of your budget for no benefit.  Plan the arithmetic you
  need ahead of the call, batch every expression into one
  ``calculate(expressions=[...])`` invocation, and only issue a
  second batched call when later expressions genuinely depend on
  the results of the first.  Repeated single-expression calls in
  one turn (the pattern that previously starved the DCIC of step
  budget) are forbidden.
- DON'T wrap a single bare value in ``calculate`` (e.g.
  ``calculate(expressions=['4'])``,
  ``calculate(expressions=['75.0'])``,
  ``calculate(expressions=['8.0'])``).
  The tool is for OPERATIONS — sums (``'4 + 3'``), products
  (``'4 * 75.0'``), ratios (``'20 / 75'``), comparisons
  (``'30 > 25'``), and conversions (``'9 / 100 * 11'``).  Echoing a
  value you already have is a no-op that wastes a turn and burns
  your step budget.  If you have nothing to compute — you are just
  recording, quoting, or handing off a value — use the value
  directly.  This DON'T does NOT relax the universal "always use
  calculate for arithmetic" rule above: anything that involves an
  operation between two or more numbers still goes through
  ``calculate`` (and goes through it BATCHED with any other
  expressions you need this turn).

### Attempt-folder integrity (HARD — applies to every agent)
- DON'T rewrite, edit, or delete a file already present in any
  attempt folder under ``logs/attempts/``.  Each file inside an
  attempt folder is final — once ``parameters.json``,
  ``propeller_mesh.obj``, or a ``render_*.png`` has been written
  for an attempt, it stays as-is.  The write tools enforce this
  (they refuse to overwrite); do NOT attempt to circumvent the
  enforcement.
- DON'T mix artifacts across attempts.  An attempt folder must be
  COHERENT: the ``propeller_mesh.obj`` it contains must have been
  generated from the ``parameters.json`` it contains; the
  ``render_*.png`` it contains must show that same mesh.  Never
  write a mesh into an attempt whose ``parameters.json`` was
  authored for a different parameter set, and never render into an
  attempt whose mesh was generated for different parameters.
- DON'T write into an attempt that is not the current one.  The
  ``Current attempt:`` line in your hand-off names the active
  attempt for this cycle.  If your work needs to target a folder
  other than that one (for instance: re-using an older parameter
  set), open a NEW attempt via ``new_attempt`` (only Planner /
  Orchestrator / DCIC can do this) and write into the new folder.
- DO fill in missing pieces of a previously-created attempt only
  when the user / Planner has explicitly asked you to use that
  attempt's existing inputs (e.g. "regenerate the mesh for
  attempt 3 using its current parameters.json"): in that case the
  attempt is the current attempt for this cycle, and writes are
  permitted only for files that the folder is still missing
  (mesh into a parameters-only folder; renders into a folder that
  has parameters + mesh but no renders).  The write tools' refuse-
  on-overwrite behaviour automatically protects existing files —
  do not try to work around it.
