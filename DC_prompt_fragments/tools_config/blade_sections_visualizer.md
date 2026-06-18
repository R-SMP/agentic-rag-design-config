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
