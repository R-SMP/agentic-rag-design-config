The pipeline is a chain built around the Conductor, its hub.  The full
flow is:

  user → Receptionist → User Input Inspector → Conductor → Creator →
  Tool Caller → DC Output Inspector → Conductor → Receptionist → user

A new user message enters through the Receptionist, which routes it to the
User Input Inspector whenever it carries design content — the usual case, and
the UII then runs first.  A message with no new design content (an answer to a
system question, a control instruction about a run in progress) goes straight
to the Conductor instead.  The
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
