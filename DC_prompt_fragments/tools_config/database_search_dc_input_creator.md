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

Reach for it when your question is about VALUES — "has anything near
this been built?", "what came of this blade count at this radius?" —
and for the text query when it is about REASONING.  Read BOTH numbers
on each hit: ``closeness`` (1.000 identical, ~0.87 the same design
re-iterated, ~0.56 unrelated) and ``matched_keys``, which says how many
of your parameters that attempt actually carried.  A high closeness
over one key is much weaker evidence than the same number over ten.
