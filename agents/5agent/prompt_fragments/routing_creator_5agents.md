### Available routing tools
- ``call_tool_caller(message)`` — FORWARD to the Tool Caller once
  ``parameters.json`` is written and self-validated.  This is the natural
  next step in the pipeline.
- ``call_conductor(message)`` — CLARIFY back to the Conductor if its
  hand-off was ambiguous, or if the qualitative directive it gave cannot be
  expressed in concrete parameter values; and ESCALATE when stuck (a
  locked-value collision, or a budgeted attempt cap reached).  Both use this
  tool; what differs is the intent you state.
