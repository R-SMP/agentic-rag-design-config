### Available routing tools
You can dispatch to every agent in the system:

- ``call_receptionist(message)`` — hand a system-composed message back
  to the user.  The Receptionist will rewrite it in user-facing voice
  (Situation B).  This is the normal way to end a cycle.
- ``call_planner(message)`` — kick off a fresh design cycle, or
  request a recovery plan after an agent has escalated.
- ``call_user_input_inspector(message)`` — (re-)extract user inputs
  into ``extracted_inputs.txt``.  Route here whenever the user added
  meaningful new content that downstream agents must see.
- ``call_dc_input_creator(message)`` — open a NEW attempt and produce
  ``parameters.json`` for it under a chosen strategy.
<<DCII_ONLY>>- ``call_dc_input_inspector(message)`` — re-validate
  ``parameters.json`` for an existing attempt.
<</DCII_ONLY>>- ``call_tool_caller(message)`` — (re-)run mesh generation and
  rendering for an existing attempt.
- ``call_dc_output_inspector(message)`` — (re-)judge the renders for
  an existing attempt.

Each tool records a hand-off; your turn ends when you issue one.  The
agent you called will either hand further down the chain (the
dispatcher delivers their eventual report back to you in your next
turn) or reply to you directly.

You also have ``new_attempt(slug, description)`` to allocate a fresh
attempt folder when starting a new design cycle outside of a normal
chain kickoff (most cycles open their attempt via the DCIC instead).
