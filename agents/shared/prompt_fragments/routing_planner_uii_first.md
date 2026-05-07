### Available routing tools
- ``call_dc_input_creator(message)`` — FORWARD to the DC Input
  Creator.  This is the natural next step in the pipeline whenever
  Part 1 (planning) yields an actionable plan that the chain should
  execute.
- ``call_user_input_inspector(message)`` — CLARIFY back to the User
  Input Inspector if its ``extracted_inputs.txt`` is missing
  required information or contains an inconsistency that only the
  UII can resolve.
- ``call_orchestrator(message)`` — return control to the Orchestrator.
  Use this for Part 2 (the user-facing summary the Orchestrator will
  relay through the Receptionist), for normal completion when no
  pipeline run is required, and for ESCALATE.
