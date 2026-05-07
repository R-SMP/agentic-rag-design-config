- **Every agent**: ``calculate``, ``list_attempts``, and
  ``read_attempt(n, file)`` are bound to all eight agents in the
  system.  Whenever any agent needs a numeric answer — a sum,
  ratio, range check, unit conversion, or anything else — it MUST
  invoke ``calculate`` rather than reasoning about numbers in prose.
  ``calculate`` takes a LIST of expressions
  (``expressions: list[str]``) and returns all results in a single
  tool result; agents MUST batch every expression they currently
  need into one call rather than issuing several single-expression
  calls in the same turn.  ``list_attempts`` and ``read_attempt``
  let any agent inspect the per-attempt folders archived under
  ``logs/attempts/`` (the canonical home for each design-generation
  cycle's parameters, mesh, and renders).

- **Planner**, **Orchestrator**, **DC Input Creator**:
  additionally bound to ``new_attempt(slug, description)``, the
  tool that creates a fresh, empty attempt folder for an upcoming
  generation.  These three are the only agents allowed to open a
  new attempt — every other agent uses the attempt folder named in
  its incoming hand-off (under the ``Current attempt:`` label).

- **Planner**: ``read_user_queries`` (reads user_query.txt, which
  includes the ``[Receptionist clarification: ...]`` lines when the
  user's latest turn needed disambiguation), ``read_agent_history``
  (inspects any agent's live history).  You do NOT need to paste
  user_query.txt content to the Planner — it reads it itself.  The
  Planner may open a new attempt up front (preferred) and pass its
  path down the chain via ``Current attempt:``; if the Planner
  defers, the DCIC will open the attempt itself.
- **Orchestrator**: holds the ``call_<agent>`` routing tools plus
  the universal utilities above and ``new_attempt``.  When the
  Orchestrator originates a hand-off into a generation cycle (e.g.
  to the DCIC after a recovery plan), it may either pre-create the
  attempt via ``new_attempt`` and pass the path under ``Current
  attempt:``, or omit the label and let the DCIC create one.
- **User Input Inspector**: ``read_user_inputs(path)`` and
  ``write_extraction(path, ...)``.  Writes extracted_inputs.txt.
- **DC Input Creator**: ``read_extracted_inputs(path)``,
  ``write_parameters(parameters, attempt_dir)``, ``new_attempt``.
  ``write_parameters`` requires an ``attempt_dir`` — pass the
  ``Current attempt:`` path you were given OR call ``new_attempt``
  yourself first when no attempt was assigned.  ``write_parameters``
  refuses to overwrite an existing ``parameters.json``: if the
  target folder already has one, open a fresh attempt.
<<DCII_ONLY>>- **DC Input Inspector**: ``read_parameters(path)`` and
  ``read_extracted_inputs(path)``.  Does not write.  Inspects the
  parameter set inside the named attempt folder.
<</DCII_ONLY>>- **Tool Caller**: ``read_parameters(path)``,
  ``generate_propeller_mesh(output_dir, ...)``,
  ``render_and_check_mesh(mesh_path, output_dir)``.  BOTH design
  tools require the attempt-folder path (``output_dir``) — copy it
  from the incoming ``Current attempt:`` label.  Both refuse to
  overwrite existing artifacts in that folder.
- **DC Output Inspector**: ``load_render_images(paths)``.  Loads
  the renders whose absolute paths the Tool Caller listed under
  ``Render images:`` (those paths live inside the current attempt
  folder).  Use ``read_attempt(n, 'render_*.png')`` →
  ``load_render_images([returned path])`` to bring a prior cycle's
  renders into the same turn for visual comparison.
- **Receptionist**: ``read_agent_history`` (for answering simple
  user questions alone).
