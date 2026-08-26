### Available routing tools
- ``call_orchestrator(message)`` — return control to the Orchestrator.
  Use this to **forward** a validated user message into the pipeline
  (Situation A, path 1) or to relay a forwarded answer to a system-
  posed question.

You CANNOT call any other agent in the pipeline directly.  All onward
dispatch goes through the Orchestrator.

