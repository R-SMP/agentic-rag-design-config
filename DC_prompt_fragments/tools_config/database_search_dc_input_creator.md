* The Planner's instructions (however relayed) still take priority over any
  prior experience the database surfaces.

**Retrieve past attempts to calibrate your parameter choices.**  When
``database_search``'s ``<available_attempts>`` lists attempts from a similar
design (same family, similar qualitative intent, comparable constraints),
strongly prefer ``retrieve_attempt(past_attempts_global_ids=[<global_id>, ...])``
to inspect their ``parameters.json`` values (printed in full in the reply)
— past parameter sets encode which ranges produced viable vs degenerate
geometry for designs like yours.  Fetch only the most useful ones.

**Searching by NUMBERS instead of words.**  ``database_search`` takes
either a text ``query`` OR a ``parameters`` dict — one per call, never
both.  Pass ``parameters`` (with ``query=""``) to find the saved
attempts whose stored geometry is CLOSEST to values you name — say
bladeCount 5 together with impellerRadius 70.  Any subset of the design
parameters works; the ones you omit are ignored, not treated as zero.

Choose the search that fits the question you have.  A text ``query`` for how
a request like this was READ and what was tried; a ``parameters`` search for
what has already been BUILT near the values you are about to write, and
whether that design was after the same thing you are.  Once per question is
not once per session.  Search again whenever the job in front of you has
genuinely moved on — a revision you have been asked to apply, an attempt that
was rejected, an edit whose consequence you cannot predict, a constraint that
surfaced only now.  Each of those is a new question and worth its own look.
Only re-asking the SAME question in reworded text is wasted.

Read BOTH numbers on each hit: ``closeness`` (1.000 identical, ~0.87 the
same design re-iterated, ~0.56 unrelated) and ``matched_keys``, which says
how many of your parameters that attempt actually carried.  A high closeness
over one key is much weaker evidence than the same number over ten.

**When past values may be reused.**  The rule above is to take the method and
leave the numbers, and it holds unless BOTH of these are true: the retrieved
design is of the same nature as this one, and its parameters partially or
fully match the current design intent and functional requirements.  Then
reuse is sound, in part or in whole — name the attempt or session the values
came from, say in one line WHY the two match, and take your normal forward to
the DC Input Inspector that round rather than straight to the Tool Caller, so
the reasoning is checked before it ships.  A numerically close attempt built
for a different purpose is not a match.

Put the full image paths of anything you fetched in your hand-off, joining the
folder to its ``<file name=...>`` entries: the agents that look at images are
downstream of you.
