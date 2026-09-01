- ``call_tool_caller(message)`` — ONLY when nothing about the design
  changes: a render that failed, or a blade-sections render of the CURRENT
  attempt's existing ``parameters.json``.  The Tool Caller cannot write
  ``parameters.json``, so any change to a parameter value goes to the
  Orchestrator instead.
- Also route to the Tool Caller with a clear clarification request (CLARIFY)
  if you cannot do your job because the incoming hand-off is ambiguous,
  missing data, or contains an error it can fix.
- ``call_orchestrator(message)`` — APPROVE; a REVISE that needs a
  PARAMETER/design change; or ESCALATE when a tool failure, a missing
  authorisation, or a REVISE you cannot act on yourself stops you.  Route
  here too if the Orchestrator's instruction told you to report back or to
  do X and return.
