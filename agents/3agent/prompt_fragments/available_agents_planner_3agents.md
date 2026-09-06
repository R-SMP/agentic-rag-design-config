- **Receptionist**: the user-facing agent.  Validates incoming requests
  before the pipeline ever starts and composes every outgoing message
  to the user.  If the user needs to be asked something, route to the
  Receptionist and state what question is needed; it composes the
  exact wording.
- **Requirements Analyst (RA)**: reads user_query.txt and any other
  input files in the inputs directory (text, sketches/images),
  extracts design values, intent, and constraints, and writes
  extracted_inputs.txt.  This is the only agent that interprets raw
  user content into structured design data.
- **Design Engineer (DE)**: reads extracted_inputs.txt and writes
  the complete $parameter_count-parameter set to parameters.json.  This is the only
  agent that authors concrete numeric parameter values.  Translates
  qualitative guidance (a directive of the form "increase <param X>")
  into numbers.
<<DCII_ONLY>>- **DC Input Inspector (DCII)**: reads parameters.json and
  extracted_inputs.txt from disk and validates that the parameter
  values are in range, internally consistent, and match the user's
  intent.  Can send corrections back to the Design Engineer.
<</DCII_ONLY>>- **Design Engineer (TC)**: works from an attempt's ``parameters.json`` —
  the record of the $parameter_count parameter values the DE
  authored.<<BSV_ON>>  It can be asked for ``render_blade_sections`` —
  the three blade cross-sections alone, with no 3D mesh.<</BSV_ON>>  Or it
  points ``generate_and_render_propeller`` at that ``parameters.json``
  and calls it once — the tool reads the record itself and produces the
  mesh file AND, as its built-in final step, the renders and (if
  enabled) the quality-check numbers.  Also has a ``calculate`` tool
  for arithmetic.  Reports the produced file paths for the Requirements
  Analyst.
- **Requirements Analyst (RA)**: loads the rendered PNGs using the
  paths supplied by the Design Engineer and performs a qualitative visual
  analysis.  It calls you to approve the design or to flag defects and
  problems.  Cannot measure precise dimensions; comments
  on overall shape, proportions, and feature count.
