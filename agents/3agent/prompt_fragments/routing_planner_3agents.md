- ``call_design_engineer(message)`` — FORWARD to the Design
  Engineer.  This is the natural next step in the pipeline whenever
  Part 1 (planning) yields an actionable plan that the chain should
  execute.
- ``call_requirements_analyst(message)`` — (re-)read the user inputs.
  Route here whenever the user added meaningful new content that
  downstream agents must see; and CLARIFY back to the Requirements
  Analyst if what it reported is missing required information or
  contains an inconsistency that only it can resolve.
- ``call_receptionist(message)`` — hand the result to the Receptionist,
  which composes the exact user-facing wording.  Use this for Part 2
  (the summary the user must hear), for normal completion when no
  pipeline run is required, and to ask the user a question.
