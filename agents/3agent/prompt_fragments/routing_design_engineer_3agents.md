- ``call_planner(message)`` — If the directive asked you to hand back after you
  are finished, or if it asked you for VALUES ONLY (no geometry), hand back to
  the Planner once your work is done.  Use the same tool if you cannot do your
  job because the incoming hand-off is ambiguous, missing data, or contains an
  error the sender can fix: hand back with a clear clarification request
  (CLARIFY) or a description of the problem.

- ``call_requirements_analyst(message)`` — If the instruction in your incoming
  hand-off told you to continue the pipeline (explicitly or by default), and
  your own work succeeded, route FORWARD to the Requirements Analyst.

