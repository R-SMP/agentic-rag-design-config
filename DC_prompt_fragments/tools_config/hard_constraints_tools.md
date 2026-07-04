### Tool-use hard rules (every agent)
- DON'T invent or guess a path for a read tool: read tools take only the
  paths a hand-off label gives (``Input directory:`` / ``Extracted inputs
  file:`` / ``Parameters file:`` / ``Render images:`` / ``Current
  attempt:``) or an upstream tool's return value.
- DO route EVERY arithmetic operation — sums, ratios, conversions, range
  comparisons — through the ``calculate`` tool (never mental arithmetic;
  LLM sums are unreliable even for trivial cases).  Batch every expression
  you need this turn into ONE ``calculate`` call; issue a second only when
  later expressions genuinely depend on earlier results.
- Attempt folders are append-only and COHERENT: never rewrite / edit /
  delete a file already in one, write only into the ``Current attempt:``
  folder, and a folder's mesh + ``render_*.png`` must have come from its
  own ``parameters.json``.  To reuse an old parameter set, COPY its values
  into a NEW attempt (Planner / Orchestrator / DCIC open it) — never edit
  the old folder.
