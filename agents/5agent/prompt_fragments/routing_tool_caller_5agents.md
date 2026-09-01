- ``call_dc_output_inspector(message)`` — If the Orchestrator's instruction in
  your incoming message told you to continue the pipeline (explicitly or by
  default), and your own work succeeded, route FORWARD to the DC Output
  Inspector.

<<DCII_ONLY>>- ``call_dc_input_inspector(message)`` — If you cannot do your job because the
  incoming hand-off is ambiguous, missing data, or contains an error the sender
  can fix, route back to the DC Input Inspector with a clear clarification
  request (CLARIFY).
<</DCII_ONLY>><<DCII_OFF>>- ``call_dc_input_creator(message)`` — If you cannot do your job because the
  incoming hand-off is ambiguous, missing data, or contains an error the sender
  can fix, route back to the DC Input Creator with a clear clarification request
  (CLARIFY).
<</DCII_OFF>>
- ``call_orchestrator(message)`` — If the Orchestrator's instruction told you to
  report back or to do X and return, route to the Orchestrator once your work is
  done.  If something is fundamentally wrong and you cannot fix it, route to the
  Orchestrator (ESCALATE).
