- **Receptionist**: the user-facing agent.  Validates incoming requests
  before the pipeline ever starts and composes every outgoing message
  to the user.  You never call the Receptionist directly — if the user
  needs to be asked something, route to the Orchestrator and state
  what question is needed; the Orchestrator hands off to the
  Receptionist, which composes the exact wording.
- **User Input Inspector (UII)**: reads user_query.txt and any other
  input files in the inputs directory (text, sketches/images),
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
<</DCII_ONLY>>- **Tool Caller (TC)**: works from an attempt's ``parameters.json`` —
  the record of the $parameter_count parameter values the DCIC
  authored.<<BSV_ON>>  It can be asked for ``render_blade_sections`` —
  the three blade cross-sections alone, with no 3D mesh.<</BSV_ON>>  Or it
  points ``generate_and_render_propeller`` at that ``parameters.json``
  and calls it once — the tool reads the record itself and produces the
  mesh file AND, as its built-in final step, the renders and (if
  enabled) the quality-check numbers.  Also has a ``calculate`` tool
  for arithmetic.  Reports the produced file paths for the DC Output
  Inspector.
- **DC Output Inspector (DCOI)**: loads the rendered PNGs using the
  paths supplied by the Tool Caller and performs a qualitative visual
  analysis.  Approves the design (FORWARD to Orchestrator) or flags
  defects and escalates.  Cannot measure precise dimensions; comments
  on overall shape, proportions, and feature count.
