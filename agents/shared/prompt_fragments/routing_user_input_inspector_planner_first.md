- ``call_dc_input_creator(message)`` — FORWARD to the DC Input Creator
  once ``extracted_inputs.txt`` is written and complete.  This is the
  natural next step in the pipeline.

  **Pre-route self-check (mandatory).**  Before you invoke a forward route,
  look back at this turn: did ``write_extraction`` return success?  If not,
  call it first — routing now delivers an empty file to the next agent.
- ``call_planner(message)`` — CLARIFY back to the Planner if its
  hand-off was ambiguous, or if the qualitative directive it gave
  cannot be expressed as something the DCIC can act on.
- ``call_orchestrator(message)`` — return control to the Orchestrator
  for normal completion (when no DCIC follow-up is required) or for
  ESCALATE.
