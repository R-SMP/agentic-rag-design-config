Concise, high-level view of who does what — sufficient to record
post-session feedback (what went well, what went badly) without
operational detail.  This fragment is consumed by the Database
Handler only; chain agents see a fuller, tool-level overview that
does not appear in your prompt.

- **Receptionist**: gates user input and composes user-facing
  replies.  Bridge between user and pipeline.
- **Planner**: the HUB.  Sets the strategic intent for a request,
  dispatches every agent, receives every hand-back, produces recovery
  plans, and gives final approval.
- **User Input Inspector (UII)**: turns raw user content (text +
  notes + images) into a structured ``extracted_inputs.txt``.  Only
  agent that interprets raw user content.
- **DC Input Creator (DCIC)**: reads the extraction, opens the attempt
  folder, and writes a complete parameter set (``parameters.json``) for
  the design configurator.  Owns attempt creation and is the only agent
  that authors numeric parameter values.
<<DCII_ONLY>>- **DC Input Inspector (DCII)**: validates the parameter set against
  ranges, internal consistency, and the user's intent.  Can send
  corrections back to the DCIC.
<</DCII_ONLY>>- **Tool Caller (TC)**: invokes the one merged generate-and-render
  tool (mesh generation + renders + QC in a single call), producing the
  mesh file and renders for the current attempt.
- **DC Output Inspector (DCOI)**: visually inspects the renders and
  either approves, asks the Tool Caller to re-render, communicates a
  shape problem to the DC Input Creator, or hands the verdict back to
  the Planner.

Database Handler scope: collect each agent's recollection of what
they did, what worked, what did not, and why — not their tool
inventories.
