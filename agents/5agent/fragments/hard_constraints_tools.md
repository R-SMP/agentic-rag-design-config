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
- Attempt folders are COHERENT and append-only for their inputs: never
  rewrite / edit / delete a ``parameters.json`` or mesh already in one,
  write only into the ``Current attempt:`` folder, and a folder's mesh +
  ``render_*.png`` must have come from its own ``parameters.json``.
  Re-running the render/QC tool on an attempt that already has renders
  REUSES them in place — no new attempt is needed just to re-render.  To
  build on an old parameter set, COPY its values into a NEW attempt (the
  Creator opens it) — never edit the old folder's parameters.
