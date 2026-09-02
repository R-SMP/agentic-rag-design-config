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
