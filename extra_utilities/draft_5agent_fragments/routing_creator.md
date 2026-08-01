<!-- DRAFT — 5-agent system · routing_creator.md.
     From routing_dc_input_creator_uii_first.md (PF_OFF + DCII_OFF branches).
     The DCII hop is gone (the Creator self-validates), so FORWARD goes
     straight to the Tool Caller; call_planner and call_orchestrator collapse
     into the single call_conductor. -->

### Available routing tools
- ``call_tool_caller(message)`` — FORWARD to the Tool Caller once
  ``parameters.json`` is written and self-validated.  This is the natural
  next step in the pipeline.
- ``call_conductor(message)`` — CLARIFY back to the Conductor if its
  hand-off was ambiguous, or if the qualitative directive it gave cannot be
  expressed in concrete parameter values; and ESCALATE when stuck (a
  locked-value collision, or a budgeted attempt cap reached).  Both use this
  tool; what differs is the intent you state.
