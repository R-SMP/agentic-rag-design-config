A "sketch" — for the purposes of this system — is a USER-SUPPLIED
reference image whose value is QUALITATIVE: it conveys overall
intent (layout, structural elements, gross proportions, counts of
repeated features), NOT precise dimensions or exact geometry.
Sketches are deliberately imperfect — hand-drawn, freehand, often
asymmetric, often missing details — and they communicate what the
user broadly wants without dictating every measurement.

### When to treat a user image as a sketch

Treat a user-supplied reference image as a sketch when ANY of the
following is true:

  * The user (in ``user_query.txt`` or in the paired
    ``_note.txt``) calls it a sketch / drawing / doodle / rough
    draft / rough idea / approximate / freehand / "just an
    example" or any equivalent phrasing.
  * The visual character of the image is clearly hand-drawn:
    uneven line widths, freehand wobble, visible asymmetries
    between elements that ought to be identical (e.g. blades of
    different lengths in what is clearly meant to be a symmetric
    propeller), missing or rough hub / connection details, no
    dimensioning, no axes / rulers / scale.
  * The user's design intent prose explicitly asks the system to
    "match qualitatively", "replicate the look", "follow the
    rough shape", or similar non-literal phrasings.

When in doubt, DEFAULT TO sketch — slightly relaxed matching is a
much milder failure mode than chasing imperfections forever.

### Rules that apply when the user input is a sketch

  1. **Imperfections are drawing artifacts, NOT design intent.**
     Asymmetries between elements that should be identical, line
     wobble, off-centre features, missing details, and small
     distortions are NOISE — not requirements to replicate.  The
     configurator produces clean, symmetric geometry; THAT is the
     intended outcome.

  2. **DO NOT seek a 1-to-1 / pixel-perfect / proportion-perfect
     match.**  A sketch communicates intent, not specification.
     "Matches the sketch" means: same overall layout, same
     structural elements, same counts of repeated features, same
     broad proportions and shape character — NOT identical line
     positions, proportions to within sketch precision, or
     replicated imperfections.

  3. **Counts of repeated features ARE precise — count them
     carefully.**  Even though the sketch is qualitative overall,
     discrete counts (number of blades, struts, holes, arms, etc.)
     are a digital attribute the user clearly expressed.  Count
     them in the appropriate view and treat the count as
     authoritative, just like any other quantitative input.
     Imperfections in shape / curvature / spacing do NOT bleed
     into the count.

  4. **Comparison against a sketch is QUALITATIVE.**  Approve a
     design when the rendered geometry agrees with the sketch's
     STRUCTURAL intent — counts, presence/absence of major
     features, overall layout, broad proportions.  Do NOT trigger
     a revision because the rendered curvature differs from a
     freehand line, the rendered hub is more cylindrical than a
     wobbly drawn hub, or the rendered ring is more perfectly
     circular than the drawn one.  Those differences are EXPECTED
     — the configurator's output is supposed to be cleaner than
     the sketch.

  5. **Recovery loops must NOT chase sketch imperfections.**  If
     the only remaining "mismatch" between renders and sketch is
     sketch-quality (irregular curvature, slight asymmetry,
     hand-drawn imprecision, exact proportions slightly off),
     the design is CONVERGED — do not order another DCIC → ...
     → DCOI cycle.  Recovery cycles exist to resolve real
     geometry problems, not to re-roll random parameter changes
     hoping to coincidentally hand-draw the user's wobble.

  6. **Communicate the limit to the user honestly.**  When you
     report a finished design, do NOT claim "the design exactly
     matches your sketch".  Say it matches the sketch's
     QUALITATIVE intent, and name the structural features that
     specifically agree (counts, layout, presence of major
     features).  When a feature cannot be replicated more
     closely without violating the sketch's qualitative intent
     (or without exceeding parameter ranges), say so plainly —
     don't pretend further iterations would close the gap.

### UII responsibility — stamp sketch character into the extraction

The User Input Inspector is the agent that decides whether the
user supplied a sketch and that records that decision in
``extracted_inputs.txt``.  When the input qualifies as a sketch
under the criteria above, the UII MUST include in the extraction's
DESIGN INTENT section an explicit line of the form:

    Reference image is a SKETCH — match qualitatively only;
    treat asymmetries / wobble / imperfections as drawing
    artifacts, not design requirements; counts of repeated
    features are still precise.

That line is what propagates the sketch character to every
downstream agent — including DCOI comparison modes that don't
load the user image directly.  Without it, downstream agents
will default to literal matching and waste recovery cycles
chasing unmeetable proportions.