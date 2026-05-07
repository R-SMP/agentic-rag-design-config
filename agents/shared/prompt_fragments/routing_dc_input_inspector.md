### Available routing tools
- ``call_tool_caller(message)`` — FORWARD when ``parameters.json``
  passes every check.  This is the natural next step in the pipeline.
- ``call_dc_input_creator(message)`` — CLARIFY back to the DC Input
  Creator when the bad value originated with the DCIC and the DCIC
  can fix it on its own.
- ``call_orchestrator(message)`` — ESCALATE when the bad value
  originated with the user (the DCIC cannot unilaterally correct a
  user-locked value), or when something else blocks the inspection
  that no chain agent can fix.
