On a blade-sections render the three sections are drawn in their OWN
colours — **Inner BLUE, Middle GREEN, Outer RED** — and each section's
name label, in the left gutter, carries that same colour.  The
bottom-right "Angle of attack" protractor draws one ray per section in
those colours and carries NO names, so colour is the only thing that
tells its three rays apart.

On a blade-sections render each section also carries two construction lines:
a THIN BLACK straight line from leading to trailing edge — the chord — and a
MAGENTA DASHED curve — the camber (mean) line.  A section with zero camber
shows the chord alone, because its mean line would lie exactly on it.

The camber line's high point can be moved along the chord.  The section's
THICKEST point cannot: it sits at ~30% of the chord from the leading edge on
every section, and no parameter changes it.  If a request or a gap
description asks to move where the blade is thickest, say it cannot be done.
