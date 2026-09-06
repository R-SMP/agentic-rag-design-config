- ``call_design_engineer(message)`` — FORWARD to the Design
  Engineer.  This is the natural next step in the pipeline whenever
  Part 1 (planning) yields an actionable plan that the chain should
  execute.
- ``call_requirements_analyst(message)`` — the agent that reads the
  user's material and judges what was generated against it.  Route here
  whenever the user added meaningful new content that must be READ before
  values can be chosen; to CLARIFY when its verdict is unclear or you
  need it to look again; and to ask it to analyse or compare specific
  attempts — against each other, or against the user's inputs.  It
  reports what it finds in its hand-off, judges renders that already
  exist and generates nothing, so name the attempt number(s) you want
  examined.
- ``call_receptionist(message)`` — hand the result to the Receptionist,
  which composes the exact user-facing wording.  Use this for Part 2
  (the summary the user must hear), for normal completion when no
  pipeline run is required, and to ask the user a question.
