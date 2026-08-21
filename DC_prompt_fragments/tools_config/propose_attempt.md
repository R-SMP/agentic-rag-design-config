### Surfacing a proposed solution — ``propose_attempt``

``propose_attempt(parameters_path)``'s mechanics — that it pushes an
attempt's full 16-parameter record to the Parameters Inputs view as the
system's PROPOSED SATISFYING SOLUTION, what the user sees (non-FIXED rows
move to the proposed value and every row, FIXED included, gets a "PROPOSED
VALUE: X" label), and that FIXED rows are never overwritten — are documented
on the tool itself.  Pass the PATH to that attempt's ``parameters.json``,
never values: the tool reads the record itself, so what the user sees is
what the attempt holds.  Take the attempt-folder path from the hand-off that
named the attempt; the folder path alone works too.

**When to call it — spontaneous, driven by the Planner's verdict.**  You are
not obliged to call it every cycle.  Read the Part-2 "Show to user:" wording
of the hand-off you are answering: phrasings such as *"recommend attempt N
because it best matches the brief"*, *"the satisfying result of the cycle"*,
*"the best attempt so far"*, *"final pick"*, *"proposed solution"* endorse
the attempt as the system's CURRENT BEST — call ``propose_attempt`` with the
path to that attempt's ``parameters.json``.  A direct user request ("propose these as your
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
