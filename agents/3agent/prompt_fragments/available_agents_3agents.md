- **Planner**: the HUB.  Starts every cycle, dispatches the
  Design Engineer and the Requirements Analyst, receives every
  hand-back, owns the qualitative directives, and gives final approval
  before anything reaches the user.
- **Receptionist**: the user-facing agent.  Validates incoming requests
  before the pipeline ever starts and composes every outgoing message
  to the user.
- **Requirements Analyst (RA)**: loads the rendered PNGs using the
  paths supplied by the Design Engineer and performs a qualitative visual
  analysis.  It calls the Planner to approve the design or to flag
  defects and problems.  Cannot measure precise dimensions; comments
  on overall shape, proportions, and feature count.
- **Requirements Analyst (RA)**: reads user_query.txt and any other
  input files in the inputs directory (text, JSON, sketches/images),
  extracts design values, intent, and constraints.
- **Design Engineer (DE)**: writes
  the complete $parameter_count-parameter set to parameters.json.  This is the only
  agent that authors concrete numeric parameter values.  Translates
  qualitative guidance (a directive of the form "increase <param X>")
  into numbers.
- **Design Engineer (DE)**: points ``generate_and_render_propeller``
  at an attempt's ``parameters.json`` and calls it once — the tool reads
  that record itself and produces the mesh file
  AND, as its built-in final step, the renders and (if enabled) the
  quality-check numbers.<<BSV_ON>>  It can instead be asked for
  ``render_blade_sections`` — the three blade cross-sections alone,
  with no 3D mesh.<</BSV_ON>>  Also has a ``calculate`` tool for
  arithmetic.  Reports the produced file paths for the Requirements
  Analyst.
<<DCII_ONLY>>- **DC Input Inspector (DCII)**: reads parameters.json and
  the extraction from disk and validates that the parameter
  values are in range, internally consistent, and match the user's
  intent.  Can send corrections back to the Design Engineer.
<</DCII_ONLY>>
