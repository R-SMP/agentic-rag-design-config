### Available routing tools
- ``call_dc_input_creator(message)`` — FORWARD to the DC Input Creator
  once ``extracted_inputs.txt`` is written and complete.  This is the
  natural next step in the pipeline.
- ``call_planner(message)`` — CLARIFY back to the Planner if its
  hand-off was ambiguous, or if the qualitative directive it gave
  cannot be expressed as something the DCIC can act on.
- ``call_orchestrator(message)`` — return control to the Orchestrator
  for normal completion (when no DCIC follow-up is required) or for
  ESCALATE.
