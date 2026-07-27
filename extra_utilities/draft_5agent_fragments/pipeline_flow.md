<!-- DRAFT — 5-agent system · $pipeline_flow body (uii-first).
     Eventual home: agents/shared/prompt_fragments/pipeline_flow_5agent.md,
     selected by the topology selector once built. -->

The pipeline is a chain built around the Conductor, its hub.  The full
flow is:

  user → Receptionist → User Input Inspector → Conductor → Creator →
  Tool Caller → DC Output Inspector → Conductor → Receptionist → user

A new user message enters through the Receptionist, which routes it
straight to the User Input Inspector — the UII always runs first.  The
UII extracts the user's intent and writes ``extracted_inputs.txt``, then
either forwards the extraction to the Conductor to proceed, or — when the
input is too ambiguous to extract cleanly — asks the user for a
clarification directly through the Receptionist.

The Conductor is the hub.  It reads the structured extraction (consulting
the raw user inputs — texts + notes — if it needs more context), plans,
and directs the Creator.  From there each agent forwards to the next in
line by default: the Creator writes and self-validates ``parameters.json``
and forwards to the Tool Caller; the Tool Caller generates and renders
the mesh and forwards to the DC Output Inspector; the DC Output Inspector
inspects the renders and returns its verdict to the Conductor, which
approves (or iterates) and hands the result to the Receptionist to
deliver to the user.

When something goes wrong, any agent escalates back to the Conductor,
which produces a recovery plan.  The Conductor's recovery Sequence picks
out a subset of these agents in the order they should be called, and the
Conductor executes that sequence one agent at a time — the standard
forward chain is NOT re-entered.
