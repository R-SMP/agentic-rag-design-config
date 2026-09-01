The pipeline is a horizontal chain where each agent hands off
directly to the next.  The full flow is:

  user → Receptionist → Orchestrator → User Input Inspector →
  Planner → DC Input Creator → <<DCII_ONLY>>DC Input Inspector → <</DCII_ONLY>>Tool Caller →
  DC Output Inspector → Orchestrator → Receptionist → user

Each agent forwards to the next in line by default.  When something
goes wrong, any agent can escalate back to the Orchestrator, which
then calls the Planner for a recovery plan.  The Planner's recovery
Sequence picks out a subset of these agents in the order they should
be called; the Orchestrator executes that sequence one agent at a
time — the standard forward chain is NOT re-entered.

In this configuration the User Input Inspector runs FIRST: it
extracts the user's intent and writes ``extracted_inputs.txt``
before the Planner sees the request.  The Planner then reads the
structured extraction and may consult the raw user inputs (texts +
notes) if it needs more context, before forwarding the actionable
plan to the DC Input Creator.
