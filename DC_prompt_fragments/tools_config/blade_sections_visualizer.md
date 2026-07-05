### Blade-sections visualizer

The system can render JUST the blade cross-sections — a flat image showing the
three blade sections (Inner, Middle, Outer) stacked vertically, each at its
true angle of attack — without building the full 3D propeller.  The Tool Caller
generates it (the `render_blade_sections` tool) from an attempt's parameters
file; the image is shown to the user and can be read by any agent that can load
images.  Because it skips the slow full-3D mesh generation, it is **much
faster** than producing the whole propeller — so when a request centres on the
blade sections (section drawings or specific section details), the sections can
be rendered and refined cheaply on their own, and can even be the final
deliverable.
