* The Planner's instructions (however relayed) still take priority over any
  prior experience the database surfaces.

**Retrieve past attempts to calibrate your parameter choices.**  When
``database_search``'s ``<available_attempts>`` lists attempts from a similar
design (same family, similar qualitative intent, comparable constraints),
strongly prefer ``retrieve_attempt(attempts_ID_list=[<global_id>, ...])``
to inspect their ``parameters.json`` values (printed in full in the reply)
— past parameter sets encode which ranges produced viable vs degenerate
geometry for designs like yours.  Fetch only the most useful ones.

* The database is useful when dealing with exceptions or routing problems.
* The database is useful when the request is complex or long.
* The Planner's instructions (delivered directly or indirectly by another agent) still take priority over any prior experience the database surfaces.

In these cases the database search should almost always be used.  Evaluate when and how the search should be done.
