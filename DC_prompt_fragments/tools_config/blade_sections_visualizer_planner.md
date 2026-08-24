### Generating geometry — the full 3D propeller, or the blade sections alone

The standard product of a design cycle is the full 3D propeller: the Tool
Caller points ``generate_and_render_propeller`` at an attempt's
``parameters.json`` and the tool builds the complete 3D geometry and, as its
built-in final step, renders the three views into that attempt's folder for
the DC Output Inspector to judge.

The system can also render JUST the blade cross-sections — a flat image
showing the three blade sections (Inner, Middle, Outer) — without building
the full 3D propeller.  The Tool Caller generates it from an attempt's
parameters file; the image can be read by any agent that can load images.
Because it skips the full-3D geometry generation, it is **much faster** than
producing the whole propeller — so when a request centres on the blade
sections (section drawings or specific section details), the sections can be
rendered and refined cheaply on their own, and can even be the final
deliverable.

When a request centres on the blade sections — the user provides drawings of
sections, or specific section details, or the sections otherwise need to be
observed — prefer a **sections-first** plan:

1. Have the Tool Caller render just the blade sections (`render_blade_sections`)
   instead of (or before) the full 3D geometry.
2. Have the DC Output Inspector check the rendered sections against the user's
   inputs / details and report focused feedback.
3. Refine the blade-section parameters on this fast loop.
4. Only then decide whether to generate the full 3D propeller — or stop at the
   sections if that is all the user wanted (the sections image can be the
   deliverable).

This is a suggestion, not a rule — judge it from the request.  If the user
wants the actual propeller, continue to the 3D once the sections are right.

Make the render type explicit when you route a sections-first plan — the chain
should tell the Tool Caller to render the blade sections, not the full 3D
geometry.
