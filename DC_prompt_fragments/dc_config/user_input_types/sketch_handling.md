A "sketch" here is a USER-SUPPLIED reference image that conveys design
intent.  Its PRECISION varies — do NOT assume it is rough.  Judge where
each reference image falls on the spectrum from a rough freehand doodle to
a precise, measured drawing, and match it accordingly.

### Filled-in templates and forms
Some reference images are a PRE-PRINTED FORM the user drew on, not a
freehand sketch.  The form's own printed content — faint/typeset guide
lines, reference circles, min/max callouts, measurement scales (e.g. an
angle protractor), grids, and fixed labels (part names, section titles) —
is SCAFFOLDING: it shows WHAT to specify and the guides/ranges/units to
draw against; it is NOT a user choice.  The user's actual inputs are ONLY
the marks added on top — darker handwritten numbers and hand-drawn
shapes/lines.  Read the answer from those marks; treat the printed content
as context only — never read a printed guide value or a printed min/max as
the user's value, and do not enforce a printed range as a limit.  E.g. a
form prints "Ø160 / Ø120" guide circles and "5 mm max / 1 mm min", but the
user drew an outline labelled "Ø140" and a ring reading ~3 mm → diameter
140, ring 3, never 160/120 or 5/1.

If you have a BLANK copy of the same form (the user supplied one, or with
RAG on you retrieved a match from a past session), compare filled against
blank — what matches the blank is scaffolding, only what was added is
input.  Otherwise separate them by character: printed elements are faint,
uniform and typeset in fixed guide positions; the user's marks are darker,
handwritten and irregular.

### Judging a sketch's precision
Weigh, per image:
  * **What the user says** — "rough" / "approximate" / "just an idea" points
    to a qualitative sketch; "to scale" / "precise" / "match exactly" points
    to a precise one.
  * **Line quality** — wobbly, uneven, freehand lines mean rougher; crisp,
    controlled lines mean more precise.
  * **Image character** — dimensions, a scale bar, gridlines, or clean
    CAD-like geometry point to precise; no dimensioning, freehand wobble,
    and asymmetry between elements meant to be identical point to rough.
  * **View type** — a whole-propeller doodle is usually rough; a dedicated
    blade top-view or a blade-section (airfoil) profile often carries
    precise proportions (chord, camber, thickness, angle) meant to be
    reproduced.

A single input can be MIXED — e.g. a precise blade-section profile
alongside a rough overall-layout doodle.  Assess each image, and each
feature within it, on its own.

### Matching a ROUGH sketch — qualitative
  * Imperfections are drawing artifacts, not design intent: asymmetry
    between elements that should match, line wobble, off-centre features,
    rendered curvature differing from a freehand line, a more-cylindrical
    hub or a more-circular ring — all NOISE.  "Matches the sketch" means
    same layout, structural elements, and broad proportions and shape
    character, NOT identical line positions; do not revise for these.
  * Recovery loops must NOT chase sketch imperfections.  If the only
    remaining "mismatch" is sketch-quality (irregular curvature, slight
    asymmetry, hand-drawn imprecision), the design is CONVERGED — do not
    order another cycle.

### Matching a PRECISE sketch — faithful within the parameters
  * Read the drawn proportions and reproduce them as closely as the
    $parameter_count parameters allow — e.g. a measured blade-section's
    thickness, camber, high-point, chord, and angle, or the middle
    section's radial position.
  * A real deviation from a deliberately-precise proportion IS a defect
    worth a revision — unlike hand-drawn wobble, it is not noise.
  * You remain bounded by the $parameter_count parameters: reproduce what
    they can express; when the drawing implies geometry outside their
    reach, match as closely as possible and say what could not be captured.
  * If the user SUBORDINATES the drawn dimensions to the overall shape —
    "fit the sketched shape; the exact dimensions matter less" — record
    those dimensions as **SOFT TARGETS** subordinate to the shape goal, not
    as locked values.  The shape is the objective; the dimensions are
    references the system may vary freely to achieve it.

### Always true, regardless of precision
  * Honor the INTENDED geometry, never literal pixels — even a precise
    drawing has some hand tremor; reproduce the proportions it specifies,
    not the tremor.
  * Communicate honestly: say whether you matched qualitatively or
    reproduced precise proportions, name the features that agree, and when a
    feature cannot be brought closer (parameter limits, or a rough source)
    say so plainly — don't imply more iterations would close the gap.

### UII responsibility — record the sketch's precision in the extraction
The User Input Inspector decides whether a reference image is a sketch and
how precise it is, and states that in the DESIGN INTENT section of
``extracted_inputs.txt`` so downstream agents (DCOI comparison modes that
don't load the image, and the DC Input Creator that authors the parameters)
match with the right strictness — for example:

    Reference image is a ROUGH SKETCH — match qualitatively; treat
    asymmetry / wobble / imperfections as drawing artifacts, not
    requirements.

    Reference image is a PRECISE SKETCH (measured blade sections) —
    reproduce the drawn proportions (thickness / camber / high-point /
    chord / angle) as closely as the parameters allow; ignore only genuine
    hand tremor.

Without this, downstream agents default to one strictness and either chase
unmeetable proportions on a rough sketch or discard real proportions on a
precise one.

### UII — for a PRECISE blade-section drawing, add a warm-start estimate + crop regions
The DC Input Creator authors the parameters but CANNOT see the images; you can.
So when a reference image contains a precise blade-section (airfoil) drawing, two
extra records make the downstream section-matching far more efficient:

1. **A rough shape estimate (warm start).**  Read the drawn airfoil proportions
   into a ROUGH numeric estimate of the section-shape parameters, for the INNER
   and OUTER sections only: profile **thickness** (% of chord), **camber**
   (% of chord), and the chordwise **camber-crest position** (high-point,
   tenths of chord).
   The middle section has no profile-shape parameters of its own — its shape is
   interpolated from inner and outer; only its chord, angle and radial position
   are settable.
   Record it in QUALITATIVE DESCRIPTIONS under a clear label so the DC Input
   Creator seeds its first attempt close to the drawing instead of from defaults:

       SUGGESTED SECTION SHAPES (rough estimate read from the precise drawing — a
       STARTING POINT for the DC Input Creator, NOT a user-locked value; refine
       within ranges):
         inner  ≈ 8% thick, 3% camber, camber crest at ~3/10 chord
         outer  ≈ 10% thick, 3% camber, camber crest at ~4/10 chord

   This is your READING of the user's own drawing (they DID draw the shape), not
   an invented number — a rough eyeball is enough; mark it clearly as an estimate
   and unlocked, distinct from any explicit user numbers in QUANTITATIVE INPUTS.
   The downstream loop refines it against the drawing, so do not over-invest.

2. **Crop regions, recorded in §4 of the extraction.**  When the section
   drawings occupy only part of a larger multi-part sketch (e.g. the bottom
   strip of a full technical page), the UII records a COARSE normalized crop
   box ``[x0, y0, x1, y1]`` (fractions in 0..1) for that part in the
   extraction's ``USEFUL INPUT IMAGES`` section, labelled by what it shows.
   A whole-propeller top / side / perspective view — one the 3D geometry, not
   just the sections, should match — gets its own labelled box there too, so
   the later 3D precision check knows which sketch view to compare against
   which render view.

   Downstream, pass the box straight to ``view_images`` as that image's
   ``crop_regions`` entry: the sections box for the cheap sections match, the
   whole-propeller box for the expensive 3D check.  Coarse is fine — a box
   only has to isolate the right part of the page.
