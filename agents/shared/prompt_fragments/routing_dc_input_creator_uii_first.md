<<DCII_ONLY>>- ``call_dc_input_inspector(message)`` — If the Orchestrator's instruction in
  your incoming message told you to continue the pipeline (explicitly or by
  default), and your own work succeeded, route FORWARD to the DC Input
  Inspector.
- ``call_tool_caller(message)`` — the precision tight-loop edge: FORWARD
  straight to render, skipping the DC Input Inspector.  Use it only on a
  precision refine round.
<</DCII_ONLY>><<DCII_OFF>>- ``call_tool_caller(message)`` — If the Orchestrator's instruction in
  your incoming message told you to continue the pipeline (explicitly or by
  default), and your own work succeeded, route FORWARD to the Tool Caller.
<</DCII_OFF>>
- ``call_planner(message)`` — If you cannot do your job because the incoming
  hand-off is ambiguous, missing data, or contains an error the sender can fix,
  route back to the Planner with a clear clarification request (CLARIFY).

- ``call_orchestrator(message)`` — If the Orchestrator's instruction told you to
  report back or to do X and return, route to the Orchestrator once your work is
  done.  If something is fundamentally wrong and you cannot fix it, route to the
  Orchestrator (ESCALATE).
