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
form prints "Ø100 / Ø50" guide circles and "5 mm max / 1 mm min", but the
user drew an end labelled "Ø58" and a wall reading ~2 mm → diameter 58,
wall 2, never 100/50 or 5/1.

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
  * **View type** — a quick perspective doodle is usually rough; a
    dimensioned side view or an end-on view of a connector often carries
    precise proportions (diameters, lengths, bend angle) meant to be
    reproduced.

A single input can be MIXED — e.g. a precise, dimensioned connector
alongside a rough overall-layout doodle.  Assess each image, and each
feature within it, on its own.

### Matching a ROUGH sketch — qualitative
  * Imperfections are drawing artifacts, not design intent: asymmetry
    between elements that should match, line wobble, off-centre features,
    rendered curvature differing from a freehand line, rounder ends or a
    smoother bend than drawn — all NOISE.  "Matches the sketch" means
    same layout, structural elements, and broad proportions and shape
    character, NOT identical line positions; do not revise for these.
  * Recovery loops must NOT chase sketch imperfections.  If the only
    remaining "mismatch" is sketch-quality (irregular curvature, slight
    asymmetry, hand-drawn imprecision), the design is CONVERGED — do not
    order another cycle.

### Matching a PRECISE sketch — faithful within the parameters
  * Read the drawn proportions and reproduce them as closely as the
    $parameter_count parameters allow — e.g. a measured end's
    diameter and length, or the bend's angle and radius.
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

    Reference image is a PRECISE SKETCH (measured diameters and bend) —
    reproduce the drawn proportions (diameters / lengths / bend angle /
    bend radius) as closely as the parameters allow; ignore only genuine
    hand tremor.

Without this, downstream agents default to one strictness and either chase
unmeetable proportions on a rough sketch or discard real proportions on a
precise one.

### UII — for a PRECISE drawing, add a warm-start estimate + crop regions
The DC Input Creator authors the parameters but CANNOT see the images; you can.
So when a reference image is a precise, measured drawing of the adapter, two
extra records make the downstream matching far more efficient:

1. **A rough reading of the drawn proportions (warm start).**  Read what the
   drawing shows but does not label — the ends' diameters and lengths, the bend
   angle and radius — into a ROUGH numeric estimate.  Record it in QUALITATIVE
   DESCRIPTIONS under a clear label so the DC Input Creator seeds its first
   attempt close to the drawing instead of from defaults:

       SUGGESTED PROPORTIONS (rough estimate read from the precise drawing — a
       STARTING POINT for the DC Input Creator, NOT a user-locked value; refine
       within ranges):
         end 1 ≈ 58 mm outside, 40 mm long; end 2 ≈ 100 mm inside, 50 mm long;
         bend ≈ 45°

   This is your READING of the user's own drawing (they DID draw the shape), not
   an invented number — a rough eyeball is enough; mark it clearly as an estimate
   and unlocked, distinct from any explicit user numbers in QUANTITATIVE INPUTS.
   The downstream loop refines it against the drawing, so do not over-invest.

2. **Crop regions, recorded in §4 of the extraction.**  When the useful part
   occupies only part of a larger multi-part sheet (e.g. one view of a full
   technical page), the UII records a COARSE normalized crop box
   ``[x0, y0, x1, y1]`` (fractions in 0..1) for that part in the extraction's
   ``USEFUL INPUT IMAGES`` section, labelled by what it shows — a side view, an
   end view, the detail of a flange.

   Downstream, pass the box straight to ``view_images`` as that image's
   ``crop_regions`` entry.  Coarse is fine — a box only has to isolate the
   right part of the page.
