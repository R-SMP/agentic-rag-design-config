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
