<!-- SCAFFOLD - NOT THE FINAL TEXT ------------------------------------
     scoped fragment `sketch_handling` for the Requirements Analyst, produced by
     MECHANICALLY CONCATENATING its two topology-5 parents:
       Requirements Analyst + Requirements Analyst

     It exists so the 3-agent system assembles and its wiring can be
     verified BEFORE the prompts are authored.  It is a concatenation,
     NOT a union: it states some concepts twice, and it can carry rules
     that contradict each other or name agents topology 3 never builds.

     Replaced WHOLESALE at Stage 9 under the merge doctrine.  Do not
     hand-patch it here -- see
     extra_utilities/docs/active/topology3_rebuild_plan.md sections 4 and 5.
------------------------------------------------------------------- -->

A "sketch" is any USER-SUPPLIED drawing containing design details.
Its PRECISION varies — do NOT assume it is rough.

### Filled-in templates and forms
When the image is a PRE-PRINTED FORM the user drew on, its printed content —
guide lines, callouts, scales, grids, fixed labels — is SCAFFOLDING, not a
user choice; only the marks added on top (darker, handwritten, irregular) are
input.  A printed range beside a feature states the span it may take, never a
chosen value: if the template prints "1 to 10 mm" and the user wrote "2 mm",
the input is 2 — not 1, and not 10.  When unsure which is which, ask what a
BLANK copy of the same template would already show; that part is scaffolding.

### Judging a sketch's precision
Judge each image, and each feature within it, on its own — one input can be
MIXED.  Weigh what the user says ("rough" / "just an idea" vs "to scale" /
"match exactly"), line quality (wobbly freehand vs crisp and controlled),
and image character (dimensions, a scale bar, gridlines
point to precise; asymmetry between elements meant to
be identical points to rough).

### Always true, regardless of precision
Honor the INTENDED geometry, never literal pixels — even a precise drawing
has some hand tremor; read the proportions it specifies, not the tremor.

### Record the sketch's precision in DESIGN INTENT
State each reference image's precision, using this vocabulary:

$sketch_precision_examples



<!-- SCAFFOLD JOIN - everything below comes from the DC Output Inspector -->

### Matching a ROUGH sketch
Imperfections are drawing artifacts, not design intent: asymmetry between
elements that should match, line wobble, off-centre features — all NOISE.
"Matches the sketch" means the same layout, structural elements and broad
proportions, NOT identical line positions.  A refine loop must NOT chase
sketch imperfections: if the only remaining mismatch is sketch-quality, the
design is CONVERGED — do not order another cycle.

### Matching a PRECISE sketch
A real deviation from a deliberately-drawn proportion IS a defect worth a
revision — unlike hand-drawn wobble, it is not noise.  You remain bounded by
the $parameter_count parameters: judge what they can express, and say what the drawing
implies that they cannot reach.

### Filled-in templates and forms
When the image is a PRE-PRINTED FORM the user drew on, its printed content —
guide lines, callouts, scales, grids, fixed labels — is SCAFFOLDING, not a
user choice; only the marks added on top are input.  A printed range beside a
feature states the span it may take, never a chosen value: if the template
prints "1 to 10 mm" and the user wrote "2 mm", the input is 2 — not 1, and
not 10.  When unsure which is which, ask what a BLANK copy of the same
template would already show; that part is scaffolding.
