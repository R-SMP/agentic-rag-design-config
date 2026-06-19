### Blade-sections visualizer

The system can render JUST the blade cross-sections — a flat image showing the
three blade sections (Inner, Middle, Outer) stacked vertically, each drawn at
its true angle of attack — without building the full 3D propeller.  The Tool
Caller generates it (the `render_blade_sections` tool) from an attempt's
parameters file; the resulting image is shown to the user in the chat and can
be read by any agent that can load images.  An optional 1 mm grid can be drawn
behind the sections as a measurement reference.

Reach for this when only the cross-section shapes matter — inspecting or
comparing the airfoils, or showing the user the sections — rather than the
whole propeller.

Because it skips the (slow) full 3D mesh generation, rendering the sections is
**much faster** than producing the whole propeller.  So when a request centres
on the blade sections — e.g. the user gives drawings of sections or specific
section details — the system can render the sections first, check them, and
refine cheaply, then decide whether the full 3D propeller is needed at all; the
sections image can even be the final result when that is all the user asked
for.
