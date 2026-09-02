- ``call_tool_caller(message)`` — ONLY when nothing about the design
  changes: a render that failed, or a blade-sections render of the CURRENT
  attempt's existing ``parameters.json``.  The Tool Caller cannot write
  ``parameters.json``, so any change to a parameter value goes to the
  DC Input Creator instead.
- Also route to the Tool Caller with a clear clarification request (CLARIFY)
  if you cannot do your job because the incoming hand-off is ambiguous,
  missing data, or contains an error it can fix.
- ``call_dc_input_creator(message)`` — call it when you request a
  PARAMETER/design change through a REVISE message, and to hand back a
  PRECISION REFINE gap description while the refine loop is still turning.
- ``call_planner(message)`` — call it when you APPROVE a design, when you
  recommend REVISE because the upstream INTERPRETATION diverged even though
  every parameter is in range, or when a tool failure, a missing
  authorisation, or a problem you cannot solve yourself stops you: hand it
  back to the Planner and say plainly what blocked you.
