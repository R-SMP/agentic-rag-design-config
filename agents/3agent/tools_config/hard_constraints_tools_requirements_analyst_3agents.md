<!-- SCAFFOLD - NOT THE FINAL TEXT ------------------------------------
     scoped fragment `hard_constraints_tools` for the Requirements Analyst, produced by
     MECHANICALLY CONCATENATING its two topology-5 parents:
       User Input Inspector + DC Output Inspector

     It exists so the 3-agent system assembles and its wiring can be
     verified BEFORE the prompts are authored.  It is a concatenation,
     NOT a union: it states some concepts twice, and it can carry rules
     that contradict each other or name agents topology 3 never builds.

     Replaced WHOLESALE at Stage 9 under the merge doctrine.  Do not
     hand-patch it here -- see
     extra_utilities/docs/active/topology3_rebuild_plan.md sections 4 and 5.
------------------------------------------------------------------- -->

### Tool-use hard rules
- DON'T invent or guess a path.  Every path you hand a tool must trace to
  your incoming message or to a tool result.

<!-- SCAFFOLD JOIN - everything below comes from the DC Output Inspector -->

### Tool-use hard rules
- DON'T invent or guess a path.  Every path you hand a tool must trace to
  your incoming message or to a tool result.
- DO route EVERY arithmetic operation through the ``calculate`` tool —
  never mental arithmetic, even for trivial sums.
