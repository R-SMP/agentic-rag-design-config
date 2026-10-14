- **Planner**: the HUB.  Starts every cycle, dispatches the UII, the
  DC Input Creator and the DC Output Inspector, receives every
  hand-back, owns the qualitative directives, and gives final approval
  before anything reaches the user.
- **Receptionist**: the user-facing agent.  Validates incoming requests
  before the pipeline ever starts and composes every outgoing message
  to the user.
- **User Input Inspector (UII)**: reads user_query.txt and any other
  input files in the inputs directory (text, JSON, sketches/images),
  extracts design values, intent, and constraints, and writes
  extracted_inputs.txt.  This is the only agent that interprets raw
  user content into structured design data.
- **DC Input Creator (DCIC)**: reads extracted_inputs.txt and writes
  the complete $parameter_count-parameter set to parameters.json.  This is the only
  agent that authors concrete numeric parameter values.  Translates
  qualitative guidance (a directive of the form "increase <param X>")
  into numbers.
<<DCII_ONLY>>- **DC Input Inspector (DCII)**: reads parameters.json and
  extracted_inputs.txt from disk and validates that the parameter
  values are in range, internally consistent, and match the user's
  intent.  Can send corrections back to the DC Input Creator.
<</DCII_ONLY>>- **Tool Caller (TC)**: points $geometry_tool_name
  at an attempt's ``parameters.json`` and calls it once — the tool reads
  that record itself and produces the $output_model file
  AND, as its built-in final step, the $output_images and (if enabled) $quality_check_numbers.$roster_sections_tool_sentence  Also has a ``calculate`` tool for
  arithmetic.  Reports the produced file paths for the DC Output
  Inspector.
- **DC Output Inspector (DCOI)**: loads the $output_image_files using the
  paths supplied by the Tool Caller and performs a qualitative visual
  analysis.  It calls the Planner to approve the design or to flag
  defects and problems.  Cannot measure precise dimensions; comments
  on overall shape, proportions, and feature count.
