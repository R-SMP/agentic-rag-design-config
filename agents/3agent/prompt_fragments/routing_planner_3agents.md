- ``call_dc_input_creator(message)`` — FORWARD to the DC Input
  Creator.  This is the natural next step in the pipeline whenever
  Part 1 (planning) yields an actionable plan that the chain should
  execute.
- ``call_user_input_inspector(message)`` — (re-)extract user inputs
  into ``extracted_inputs.txt``.  Route here whenever the user added
  meaningful new content that downstream agents must see; and CLARIFY
  back to the User Input Inspector if its ``extracted_inputs.txt`` is
  missing required information or contains an inconsistency that only
  the UII can resolve.
- ``call_receptionist(message)`` — hand the result to the Receptionist,
  which composes the exact user-facing wording.  Use this for Part 2
  (the summary the user must hear), for normal completion when no
  pipeline run is required, and to ask the user a question.
- ``call_dc_output_inspector(message)`` — CLARIFY back to the DC Output
  Inspector when its verdict is unclear or you need it to look again, and
  ask it to analyse or compare specific attempts — against each other, or
  against the user's inputs.  It judges renders that already exist and
  generates nothing, so name the attempt number(s) you want examined.
