### Available routing tools
- ``call_dc_output_inspector(message)`` — FORWARD when mesh + renders
  + report all exist.  This is the natural next step in the pipeline.

<<DCII_ONLY>>- ``call_dc_input_inspector(message)`` — CLARIFY back to the DC Input
  Inspector when its parameter audit caused a tool failure that the
  inspector might catch on a second pass.
<</DCII_ONLY>><<DCII_OFF>>- ``call_dc_input_creator(message)`` — CLARIFY back to the DC Input
  Creator when its parameter values caused a tool failure.
<</DCII_OFF>>
- ``call_orchestrator(message)`` — ESCALATE on tool failure or any
  other blocker the upstream chain agent cannot fix.
