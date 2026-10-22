Configurator-specific patterns the operator has observed in how users
sketch adapters for THIS DC — how a sketch is typically drawn vs. how
the configurator actually renders the same design.

### Common drawing artifacts in adapter sketches

  * **Ends drawn as ovals.** A round end seen at an angle — the
    configurator's ends are always round; do NOT read an oval as a
    requirement.

  * **Walls drawn unevenly.** The configurator renders a uniform wall per
    end — pick one ``End<N>_Wall_Thickness`` representative of the sketch.

  * **A bend drawn as a sharp kink.** Hand-drawn bends often look sharper
    than meant; read the angle from the directions of the two ends, and the
    radius only when it is drawn or stated.

  * **Magnets or screws — COUNT them, and trust the count.** A count is a
    deliberate, discrete attribute the user means exactly.  An explicitly
    stated count ("8 magnets") overrides the drawn shapes.
