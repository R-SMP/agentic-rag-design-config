The pipeline is a horizontal chain where each agent hands off
directly to the next.  The full flow is:

  user → Receptionist → Orchestrator → User Input Inspector (UII) → Planner →
  DC Input Creator (DCIC) → <<DCII_ONLY>>DC Input Inspector (DCII) → <</DCII_ONLY>>Tool Caller (TC) →
  DC Output Inspector (DCOI) → Orchestrator → Planner → Orchestrator → Receptionist → user

Each agent forwards to the next in line by default.  When something
goes wrong, any agent can escalate back to the Orchestrator, which
then calls the Planner for a recovery plan.  The Planner's recovery
Sequence picks out a subset of these agents in the order they should
be called; the Orchestrator starts that sequence.  Each agent still
forwards to the next by default, so say in the hand-off where the
sequence should stop or hand back.

The User Input Inspector runs FIRST: it
extracts the user's intent and writes ``extracted_inputs.txt``
before the Planner sees the request.  The Planner then reads the
structured extraction and may consult the raw user inputs (texts +
notes) if it needs more context, before forwarding the actionable
plan to the DC Input Creator.
