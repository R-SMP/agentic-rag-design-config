### Tool-use hard rules (every agent)
- DON'T invent or guess a path.  Every path you hand a tool must trace to
  your incoming message or to a tool result.
- DO route EVERY arithmetic operation through the ``calculate`` tool —
  including range comparisons — never mental arithmetic, even for trivial
  sums.  Batch into ONE call; a second only when a later expression needs
  an earlier result.
