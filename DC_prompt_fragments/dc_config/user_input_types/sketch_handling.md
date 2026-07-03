A "sketch" here is a USER-SUPPLIED reference image that conveys design
intent.  Its PRECISION varies by case — do NOT assume it is rough.
Judge where each reference image falls on the spectrum from a rough,
freehand doodle to a precise, measured drawing, and match it
accordingly.

### Judging a sketch's precision
Weigh, per image:
  * **What the user says** — "rough" / "approximate" / "just an idea"
    points to a qualitative sketch; "to scale" / "precise" / "accurate" /
    "match exactly" points to a precise one.
  * **Line quality** — wobbly, uneven, freehand lines usually mean a
    rougher sketch; crisp, controlled lines mean a more precise one.
  * **Image character** — dimensions, a scale bar, gridlines, or clean
    CAD-like geometry point to precise; no dimensioning, freehand wobble,
    and asymmetry between elements meant to be identical point to rough.
  * **View type** — a whole-propeller doodle is usually rough; a
    dedicated blade top-view or a blade-section (airfoil) profile often
    carries precise proportions (chord, camber, thickness, angle) the
    user means for you to reproduce.

A single input can be MIXED — e.g. a precise blade-section profile
alongside a rough overall-layout doodle.  Assess each image, and each
feature within it, on its own.

### Matching a ROUGH sketch — qualitative
  * Imperfections are drawing artifacts, not design intent: asymmetry
    between elements that should match, line wobble, off-centre features,
    and small distortions are NOISE.  The configurator produces clean,
    symmetric geometry, and THAT is the intended outcome.
  * Do NOT seek a pixel- or proportion-perfect match.  "Matches the
    sketch" means same layout, same structural elements, same broad
    proportions and shape character — not identical line positions.
  * Do NOT revise merely because rendered curvature differs from a
    freehand line, the hub is more cylindrical than a wobbly drawing, or
    the ring is more perfectly circular.
  * Recovery loops must NOT chase sketch imperfections.  If the only
    remaining "mismatch" is sketch-quality (irregular curvature, slight
    asymmetry, hand-drawn imprecision), the design is CONVERGED — do not
    order another cycle.

### Matching a PRECISE sketch — faithful within the parameters
  * Read the drawn proportions and reproduce them as closely as the 17
    parameters allow — e.g. a measured blade-section's thickness, camber,
    high-point, chord, and angle, or the middle section's radial
    position.
  * A real deviation from a deliberately-precise proportion IS a defect
    worth a revision — unlike hand-drawn wobble, it is not noise.
  * You are still bounded by the 17 parameters: reproduce what they can
    express; when the drawing implies geometry outside their reach, match
    as closely as possible and say what could not be captured.

### Always true, regardless of precision
  * **Counts of repeated features are ALWAYS precise** — discrete counts
    (blades, struts, holes, arms) are a digital attribute the user
    clearly expressed; count them in the appropriate view and treat the
    count as authoritative.
  * Honor the user's INTENDED geometry, never literal pixels: even a
    precise drawing has some hand tremor — reproduce the proportions it
    specifies, not the tremor.
  * Communicate honestly: say whether you matched qualitatively or
    reproduced precise proportions, name the features that agree, and
    when a feature cannot be brought closer (parameter limits, or a rough
    source) say so plainly — don't imply more iterations would close the
    gap.

### UII responsibility — record the sketch's precision in the extraction
The User Input Inspector decides whether a reference image is a sketch
and how precise it is, and states that in the DESIGN INTENT section of
``extracted_inputs.txt`` so downstream agents (including DCOI comparison
modes that don't load the image, and the DC Input Creator that authors
the parameters) match with the right strictness.  Make the assessment
explicit — for example, for a rough image:

    Reference image is a ROUGH SKETCH — match qualitatively; treat
    asymmetry / wobble / imperfections as drawing artifacts, not
    requirements; counts of repeated features are still precise.

or, for a precise one:

    Reference image is a PRECISE SKETCH (measured blade sections) —
    reproduce the drawn section proportions (thickness / camber /
    high-point / chord / angle) as closely as the parameters allow;
    counts are precise; ignore only genuine hand tremor.

Without this, downstream agents default to a single strictness and
either chase unmeetable proportions on a rough sketch or discard real
proportions on a precise one.
