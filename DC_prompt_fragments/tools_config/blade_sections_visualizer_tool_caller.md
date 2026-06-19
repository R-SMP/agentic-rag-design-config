**You hold the `render_blade_sections` tool.**  Inputs:

- `parameters_path` — absolute path to an attempt's `parameters.json`.
- `grid` (default `false`) — set `true` to draw a 1 mm × 1 mm reference grid
  behind the sections.

It writes a PNG of the three stacked cross-sections into that attempt's folder
and returns its path; the image is shown to the user automatically.

Enabling the grid: only turn it on when a true-millimetre reference genuinely
helps AND cannot mislead.  In particular, do NOT enable the grid when the goal
is to match a user's drawing whose own grid squares are not 1 mm each — the two
scales would not correspond, so the grid would confuse rather than help.  When
in doubt, leave the grid off.

Sections-first fast path: your incoming hand-off may ask you to render the
blade sections instead of the full 3D propeller (a section-centric request, or
the DC Output Inspector asking for the sections of the current attempt).  When
it does, call `render_blade_sections` with the `Parameters file:` path and the
`Current attempt:` folder — and do NOT call the mesh-generation tool this
cycle.  This skips RhinoCompute, so it is much faster.  Only generate the full
mesh once the hand-off asks for the actual 3D propeller.  Re-rendering the
sections of an attempt you have already built reuses that same attempt — you do
not need a new one.
