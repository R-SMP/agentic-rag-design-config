Configurator-specific patterns the operator has observed in how users
sketch propellers for THIS DC — how a sketch is typically drawn vs. how
the configurator actually renders the same design.

### Common drawing artifacts in propeller sketches

  * **Blade tips drawn slightly inside or outside the ring.** Hand-drawn
    blades often don't quite reach the ring's inner wall, or overshoot
    it, because the user's hand wandered. The configurator always renders
    blades as structurally connected to the ring — do NOT treat the drawn
    gap or overshoot as a feature to replicate.

  * **Hub drawn as a rough cylinder / wobbly oval.** Sketches typically
    show the hub as a hand-drawn ellipse, sometimes off-centre. The
    configurator renders a clean cylindrical hub at the geometric centre
    — do NOT reproduce the drawn wobble or off-centre placement.

  * **Blade curvature varies between blades.** Individual sketched blades
    often have slightly different curvature, sweep, or chord — drawing
    imprecision, not design intent. The configurator produces identical
    blades by construction; pick a single curvature / sweep / chord that
    matches the sketch's average character.

  * **Outer-ring thickness drawn unevenly.** The drawn ring may be
    thicker in one place than another. The configurator renders a
    uniform-thickness ring — pick a single ``impellerThickness``
    representative of the sketch's average appearance.

  * **Number of blades is RELIABLE.** Even when the rest of the sketch is
    rough, the blade count in the top-down view is deliberate. Count it
    carefully and treat it as authoritative.
