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

Make the render type explicit when you route — the chain should tell the Tool
Caller to render just the blade sections, or just the full 3D geometry, or
both.  It depends on the current request's needs.
