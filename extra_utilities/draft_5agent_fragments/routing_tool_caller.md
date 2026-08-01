<!-- DRAFT — 5-agent system · routing_tool_caller.md.
     From routing_tool_caller.md, resolved to the <<DCII_OFF>> branch (there is
     no DC Input Inspector to CLARIFY back to) with DC Input Creator → Creator
     and Orchestrator → Conductor. -->

### Available routing tools
- ``call_dc_output_inspector(message)`` — FORWARD when mesh + renders
  + report all exist.  This is the natural next step in the pipeline.

- ``call_creator(message)`` — CLARIFY back to the Creator when its
  parameter values caused a tool failure.

- ``call_conductor(message)`` — ESCALATE on tool failure or any
  other blocker the upstream chain agent cannot fix.
