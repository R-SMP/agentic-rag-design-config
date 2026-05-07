DC-specific clarifications about how sketches of THIS particular
design configurator are typically drawn vs. how the configurator
actually renders the same design.  The companion
``sketch_handling.md`` (slot ``$sketch_handling``) defines what a
sketch is and the rules every reasoning agent must follow when
working with one; this fragment (slot ``$sketch_notes``) captures
DC-specific nuance — patterns the operator has observed when
users sketch designs for THIS DC — that those rules cannot capture
on their own.

The operator should fill this in with patterns specific to the
configurator at hand.  Examples below are starter content for
the propeller DC — adapt, delete, or replace as the operator
sees fit.

### Common drawing artifacts in propeller sketches (operator-curated)

  * **Blade tips drawn slightly inside or outside the ring.**
    Hand-drawn blades often don't quite reach the ring's inner
    wall, or overshoot it, simply because the user's hand
    wandered.  The configurator always renders blades as
    structurally connected to the ring — do NOT treat the
    drawn gap or overshoot as a feature to replicate.

  * **Hub drawn as a rough cylinder / wobbly oval.**  Sketches
    typically show the hub as a hand-drawn ellipse, sometimes
    off-centre.  The configurator renders a clean cylindrical
    hub at the geometric centre — do NOT try to reproduce the
    drawn wobble or off-centre placement.

  * **Blade curvature varies between blades in a sketch.**  In a
    sketched propeller, individual blades often have slightly
    different curvature, sweep, or chord — drawing imprecision,
    not design intent.  The configurator produces identical
    blades by construction.  Do NOT attempt to encode the
    per-blade variation; pick a single curvature / sweep /
    chord that matches the sketch's average character.

  * **Outer-ring thickness drawn unevenly.**  The drawn ring
    may be thicker in one place than another.  The configurator
    renders a uniform-thickness ring — pick a single
    ``impellerThickness`` representative of the sketch's average
    appearance.

  * **Number of blades is RELIABLE.**  Even when the rest of
    the sketch is rough, the count of blades visible in the
    top-down view is something the user drew deliberately.
    Count carefully (typically in the top render and in the
    sketch) and treat the count as authoritative.

When the operator extends this list with new patterns, keep them
short and specific to the propeller DC.  General sketch handling
lives in ``sketch_handling.md`` (slot ``$sketch_handling``);
THIS fragment is for the configurator-specific patterns.