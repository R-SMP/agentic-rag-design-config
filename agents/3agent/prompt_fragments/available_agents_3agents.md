- **Planner**: the HUB.  Starts every cycle, dispatches the
  Design Engineer and the Requirements Analyst, receives every
  hand-back, owns the qualitative directives, and gives final approval
  before anything reaches the user.
- **Receptionist**: the user-facing agent.  Validates incoming requests
  before the pipeline ever starts and composes every outgoing message
  to the user.
- **Requirements Analyst (RA)**: reads user_query.txt and any other
  input files in the inputs directory (text, JSON, sketches/images),
  extracts design values, intent, and constraints.  It also loads the
  $output_image_files using the paths supplied by the Design Engineer and
  performs a qualitative visual analysis, calling the Planner to approve
  the design or to flag defects and problems.  Cannot measure precise
  dimensions; comments on overall shape, proportions, and feature count.
- **Design Engineer (DE)**: writes the complete $parameter_count-parameter
  set to parameters.json.  This is the only agent that authors concrete
  numeric parameter values.  Translates qualitative guidance (a directive
  of the form "increase <param X>") into numbers.  It then uses that
  attempt's ``parameters.json``$roster_tools_clause
  at that ``parameters.json`` and calls it once — the tool reads that
  record itself and produces the $output_model file and the image $output_images of the
  $output_model.  Also has a ``calculate`` tool for arithmetic.
  Reports the produced file paths for the Requirements Analyst.
