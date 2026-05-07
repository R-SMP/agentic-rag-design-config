### Available routing tools
<<DCII_ONLY>>- ``call_dc_input_inspector(message)`` — FORWARD to the DC Input
  Inspector (the next step in the natural pipeline).
<</DCII_ONLY>><<DCII_OFF>>- ``call_tool_caller(message)`` — FORWARD to the Tool Caller (the
  next step in the natural pipeline).
<</DCII_OFF>>
- ``call_planner(message)`` — CLARIFY back to the Planner if its
  hand-off was ambiguous, or if the qualitative directive it gave
  cannot be expressed in concrete parameter values.

- ``call_orchestrator(message)`` — ESCALATE when stuck (locked-value
  collision, qualitative directive with no quantitative expression,
  or a budgeted attempt cap reached).
