A propeller with correct geometry should show:
- A continuous circular outer ring.
- The requested number of evenly spaced blades connecting the centre hub
  to the outer ring.
- Smooth blade surfaces without holes, spikes, or self-intersections.
- Proportions consistent with the input parameters (impellerRadius, impellerThickness, etc.).  The outer-ring HEIGHT auto-fits the outer blade section (derived, not an input).

### What you can typically check visually for this DC

  * Blade count (count blades in the top-down view).
  * Outer ring presence and continuity (visible in all three
    views).
  * Hub presence and approximate proportion.
  * Broad vs. narrow blade planform; rounded vs. squared tips.
  * Blade-to-ring connection vs. detached blade tips.

### The three shape levers, and what each one actually moves

  * ``*Thickness`` (% of chord) — how thick the section is.  Its THICKEST
    POINT is FIXED at ~30% chord and no parameter can move it.
  * ``*Camber`` (% of chord) — how curved the mean line is; 0 = a symmetric
    section with no crest at all.
  * ``*MaxPos`` (tenths of chord) — where the CAMBER CREST sits along the
    chord.  It does not move the thickest point, and does nothing when
    camber is 0.

So "the high point is too far forward" is a statement about the CAMBER
crest.  If a section instead looks thickest in the wrong place, NO parameter
can fix it — say so plainly rather than asking for a ``*MaxPos`` change.

### What is typically NOT resolvable at render resolution

  * Sub-millimetre thicknesses (ring or blade section).
  * Exact twist angles in degrees.
  * Exact chord lengths within ~1 mm.
  * Camber percentages and the high-point (camber-crest) position.

When a claim falls in the "not resolvable" bucket, mark it as
such and trust falls on the DCIC's parameter choice<<DCII_ONLY>> and the
DCII's authorisation check<</DCII_ONLY>>.
