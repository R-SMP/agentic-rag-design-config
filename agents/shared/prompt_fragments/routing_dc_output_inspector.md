- ``call_tool_caller(message)`` — REVISE that needs only a (re-)render
  of the SAME design on the CURRENT attempt (e.g. render/re-render the
  blade sections, or a render that failed): ask the Tool Caller to
  render, reusing the attempt.  Do NOT use it for a parameter/design
  change.
  Also route back here, with a clear clarification request (CLARIFY), if you
  cannot do your job because the incoming hand-off is ambiguous, missing data,
  or contains an error the Tool Caller can fix.
- ``call_orchestrator(message)`` — APPROVE; a REVISE that needs a
  PARAMETER/design change; or ESCALATE when a tool failure, a missing
  authorisation, or a REVISE you cannot act on yourself stops you.  Route
  here too if the Orchestrator's instruction told you to report back or to
  do X and return.
