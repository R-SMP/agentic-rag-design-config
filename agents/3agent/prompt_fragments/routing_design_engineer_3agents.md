<!-- SCAFFOLD - NOT THE FINAL TEXT ------------------------------------
     scoped fragment `routing` for the Design Engineer, produced by
     MECHANICALLY CONCATENATING its two topology-5 parents:
       DC Input Creator + Tool Caller

     It exists so the 3-agent system assembles and its wiring can be
     verified BEFORE the prompts are authored.  It is a concatenation,
     NOT a union: it states some concepts twice, and it can carry rules
     that contradict each other or name agents topology 3 never builds.

     Replaced WHOLESALE at Stage 9 under the merge doctrine.  Do not
     hand-patch it here -- see
     extra_utilities/docs/active/topology3_rebuild_plan.md sections 4 and 5.
------------------------------------------------------------------- -->

- ``call_tool_caller(message)`` — If the current request / directive requires
  geometry generation, route to the Tool Caller.  You can route back to it
  also if you can answer/resolve a clarification coming from the Tool Caller
  itself.

- ``call_planner(message)`` — If the directive asked you to hand back after you
  are finished, or if it asked you for VALUES ONLY (no geometry), hand back to
  the Planner once your work is done.  Use the same tool if you cannot do your
  job because the incoming hand-off is ambiguous, missing data, or contains an
  error the sender can fix: hand back with a clear clarification request
  (CLARIFY) or a description of the problem.

<!-- SCAFFOLD JOIN - everything below comes from the Tool Caller -->

- ``call_dc_output_inspector(message)`` — If the instruction in your incoming
  hand-off told you to continue the pipeline (explicitly or by default), and
  your own work succeeded, route FORWARD to the DC Output Inspector.

<<DCII_ONLY>>- ``call_dc_input_inspector(message)`` — If you cannot do your job because the
  incoming hand-off is ambiguous, missing data, or contains an error the sender
  can fix, route back to the DC Input Inspector with a clear clarification
  request (CLARIFY).
<</DCII_ONLY>><<DCII_OFF>>- ``call_dc_input_creator(message)`` — If you cannot do your job because the
  incoming hand-off is ambiguous, missing data, or contains an error the sender
  can fix, route back to the DC Input Creator with a clear clarification request
  (CLARIFY).
<</DCII_OFF>>
