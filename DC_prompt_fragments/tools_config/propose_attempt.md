### Surfacing a proposed solution — ``propose_attempt``

``propose_attempt(values)``'s mechanics — that it pushes the full
17-parameter dict to the Parameters Inputs view as the system's PROPOSED
SATISFYING SOLUTION, what the user sees (non-FIXED rows move to the proposed
value and every row, FIXED included, gets a "PROPOSED VALUE: X" label), and
that FIXED rows are never overwritten — are documented on the tool itself.
Take the values from a ``read_attempt(n, "parameters.json")`` result and
NEVER invent them: the user is shown the dict literally, so a value you did
not confirm for a specific named attempt is forbidden.

**When to call it — spontaneous, driven by the Planner's verdict.**  You are
not obliged to call it every cycle.  Read the Part-2 "Show to user:" wording
of the hand-off you are answering: phrasings such as *"recommend attempt N
because it best matches the brief"*, *"the satisfying result of the cycle"*,
*"the best attempt so far"*, *"final pick"*, *"proposed solution"* endorse
the attempt as the system's CURRENT BEST — call ``propose_attempt`` with that
attempt's full 17-param dict.  A direct user request ("propose these as your
recommendation", "make this the proposed solution") is an unambiguous trigger
too.

**When NOT to call it.**  When the Planner's wording is non-committal or
hedging (*"showing attempt N for context"*, *"intermediate result while we
keep iterating"*, *"not satisfying yet"*), or the user only wants an
informational look at a non-proposed attempt ("show me the worst one"),
visualize the attempt but do NOT touch the panel — the mechanism is STICKY:
it must keep showing the last endorsed proposal until a new one arrives.

**Pair it, and never judge from it.**  ``propose_attempt`` only updates the
sliders — it does not render the model, create an attempt, or trigger any
agent.  When the user should both see the model AND have the sliders update,
call ``visualize_3d_model`` first, then ``propose_attempt`` in the same turn.
Its return value says nothing about design quality: the no-fabrication rule
holds — never describe or judge an attempt from it.
