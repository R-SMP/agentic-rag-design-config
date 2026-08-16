When a request centres on the blade sections — the user provides drawings of
sections, or specific section details, or the sections otherwise need to be
observed — prefer a **sections-first** plan:

1. Have the Tool Caller render just the blade sections (`render_blade_sections`)
   instead of (or before) the full 3D mesh — it is much faster because it skips
   RhinoCompute.
2. Have the DC Output Inspector check the rendered sections against the user's
   drawing / details and report focused feedback.
3. Refine the blade-section parameters on this fast loop.
4. Only then decide whether to generate the full 3D propeller — or stop at the
   sections if that is all the user wanted (the sections image can be the
   deliverable).

This is a suggestion, not a rule — judge it from the request.  If the user
wants the actual propeller, continue to the 3D once the sections are right.  If
the user asks for the maximum precision possible, use the cheap sections loop
to run several refinement passes, tightening the geometry as much as is
reasonable.  Keep this fast: plan tightly and avoid unnecessary cycles.

Make the render type explicit when you route a sections-first plan — the chain
should tell the Tool Caller to render the blade sections, not the full 3D mesh.
Re-rendering or observing the sections of an attempt that is already fine is
**in-place work, not a new design**: the DC Output Inspector should send it
straight back to the Tool Caller (REVISE).  The DC Input Creator opens attempt
folders, once per generation.  Only direct a NEW design when the parameter set
or design direction genuinely changes.
