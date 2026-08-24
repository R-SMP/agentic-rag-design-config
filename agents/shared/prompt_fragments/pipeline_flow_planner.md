The pipeline is a horizontal chain where each agent hands off
directly to the next.  The full flow is:

  user → Receptionist → Orchestrator → User Input Inspector (UII) → Planner →
  DC Input Creator (DCIC) → <<DCII_ONLY>>DC Input Inspector (DCII) → <</DCII_ONLY>>Tool Caller (TC) →
  DC Output Inspector (DCOI) → Orchestrator → Planner → Orchestrator → Receptionist → user

Each agent forwards to the next in line by default.  When something
goes wrong, any agent can escalate back to the Orchestrator, which
then calls you for a recovery plan.
