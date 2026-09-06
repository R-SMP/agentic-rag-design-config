<!-- SCAFFOLD - NOT THE FINAL TEXT ------------------------------------
     scoped fragment `database_search` for the Design Engineer, produced by
     MECHANICALLY CONCATENATING its two topology-5 parents:
       Design Engineer + Design Engineer

     It exists so the 3-agent system assembles and its wiring can be
     verified BEFORE the prompts are authored.  It is a concatenation,
     NOT a union: it states some concepts twice, and it can carry rules
     that contradict each other or name agents topology 3 never builds.

     Replaced WHOLESALE at Stage 9 under the merge doctrine.  Do not
     hand-patch it here -- see
     extra_utilities/docs/active/topology3_rebuild_plan.md sections 4 and 5.
------------------------------------------------------------------- -->

* The Planner's instructions (however relayed) still take priority over any
  prior experience the database surfaces.

**Retrieve past attempts to calibrate your parameter choices.**  When
``database_search``'s ``<available_attempts>`` lists attempts from a similar
design (same family, similar qualitative intent, comparable constraints),
strongly prefer ``retrieve_attempt(attempts_ID_list=[<global_id>, ...])``
to inspect their ``parameters.json`` values (printed in full in the reply)
— past parameter sets encode which ranges produced viable vs degenerate
geometry for designs like yours.  Fetch only the most useful ones.

<!-- SCAFFOLD JOIN - everything below comes from the Tool Caller -->

* The database is useful when dealing with exceptions or routing problems.
* The database is useful when the request is complex or long.
* The Planner's instructions (delivered directly or indirectly by another agent) still take priority over any prior experience the database surfaces.

In these cases the database search should almost always be used.  Evaluate when and how the search should be done.
