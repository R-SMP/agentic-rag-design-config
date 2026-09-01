Configurator-specific patterns the operator has observed in how users
sketch propellers for THIS DC — how a sketch is typically drawn vs. how
the configurator actually renders the same design.

### Common drawing artifacts in propeller sketches

  * **Blade tips drawn inside or outside the ring.** The configurator
    always renders blades structurally connected to the ring — do NOT
    replicate a drawn gap or overshoot.

  * **Hub drawn as a rough or off-centre oval.** The configurator renders
    a clean cylindrical hub at the geometric centre — do NOT reproduce the
    drawn wobble or off-centre placement.

  * **Blade curvature varies between blades.** Drawing imprecision, not
    intent — the configurator produces identical blades by construction;
    pick a single curvature / sweep / chord matching the sketch's average
    character.

  * **Outer-ring thickness drawn unevenly.** The configurator renders a
    uniform-thickness ring — pick a single ``impellerThickness``
    representative of the sketch's average appearance.

  * **Number of blades — COUNT IT, and trust the count.** The blade count
    is a deliberate, discrete attribute the user means exactly. Even when
    the rest of the sketch is rough, carefully count the blades in the
    top-down view and treat that count as authoritative — it is one of the
    most reliable things a propeller sketch tells you.

  * *Small exception:* an explicitly stated count overrides the drawn
    shapes. If the user conveys the number by other means instead of
    drawing each blade — e.g. a "×6" label beside a single blade, or "6
    blades" written in text — follow that stated count, not the number of
    blades actually drawn.
