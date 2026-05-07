### Available routing tools
<<DCII_ONLY>>- ``call_dc_input_inspector(message)`` — FORWARD to the DC Input
  Inspector (the next step in the natural pipeline).
<</DCII_ONLY>><<DCII_OFF>>- ``call_tool_caller(message)`` — FORWARD to the Tool Caller (the
  next step in the natural pipeline).
<</DCII_OFF>>
- ``call_user_input_inspector(message)`` — CLARIFY back to the User
  Input Inspector if ``extracted_inputs.txt`` is missing required
  information or contains an inconsistency only the UII can resolve.

- ``call_orchestrator(message)`` — ESCALATE when stuck (locked-value
  collision, qualitative directive with no quantitative expression,
  or a budgeted attempt cap reached).
