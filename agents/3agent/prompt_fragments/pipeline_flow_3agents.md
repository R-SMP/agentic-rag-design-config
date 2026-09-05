The pipeline is a horizontal chain where each agent hands off
directly to the next.  The full flow is:

  user → Receptionist → Planner → User Input Inspector (UII) → Planner →
  DC Input Creator (DCIC) → Tool Caller (TC) →
  DC Output Inspector (DCOI) → Planner → Receptionist → user

Each agent forwards to the next in line by default.  When something
goes wrong, any agent can call back to the previous agent in line, or
to the Planner, which is the hub.
