The Planner's instructions (however relayed) still take priority over any
prior experience the database surfaces.

**Retrieve past attempts to calibrate your parameter choices.**  When
``database_search``'s ``<available_attempts>`` lists attempts from a similar
design (same family, similar qualitative intent, comparable constraints),
strongly prefer
``retrieve_attempt(past_attempts_global_ids=[<global_id>, ...])`` to inspect
their ``parameters.json`` values (printed in full in the reply)
— past parameter sets encode which ranges produced viable vs degenerate
geometry for designs like yours.  Fetch only the most useful ones.

**Words or NUMBERS — choose the search that fits the question.**  A text
``query`` for how a request like this was READ and what was tried; a
``parameters`` search (with ``query=""``) for what has already been BUILT
near the values you are about to write, and whether that design was after
the same thing you are — a ``parameters`` hit gives you that attempt's
ranking numbers and its archived Q+A, not its stored values.  Once per
question is not once per session: a revision you have been asked to apply,
an attempt that was rejected, an edit whose consequence you cannot predict,
or a constraint that surfaced only now is a new question.

**If you reuse past values.**  Name the attempt or session they came from
and say in one line WHY that design matches this one — same nature, same
job, comparable constraints.  A numerically close attempt built for a
different purpose is not a match.

Put the full image paths of anything you fetched in your hand-off, joining the
folder to its ``<file name=...>`` entries: the agents that look at images are
downstream of you.
