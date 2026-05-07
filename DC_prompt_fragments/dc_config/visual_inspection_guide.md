A propeller with correct geometry should show:
- A continuous circular outer ring.
- The requested number of evenly spaced blades connecting the centre hub
  to the outer ring.
- Smooth blade surfaces without holes, spikes, or self-intersections.
- Proportions consistent with the input parameters (impellerRadius, impellerHeight, etc.).

### What you can typically check visually for this DC

  * Blade count (count blades in the top-down view).
  * Outer ring presence and continuity (visible in all three
    views).
  * Hub presence and approximate proportion.
  * Broad vs. narrow blade planform; rounded vs. squared tips.
  * Blade-to-ring connection vs. detached blade tips.

### What is typically NOT resolvable at render resolution

  * Sub-millimetre thicknesses (ring or blade section).
  * Exact twist angles in degrees.
  * Exact chord lengths within ~1 mm.
  * Camber / highpoint percentages.

When a claim falls in the "not resolvable" bucket, mark it as
such and trust falls on the DCIC's parameter choice<<DCII_ONLY>> and the
DCII's authorisation check<</DCII_ONLY>>.
