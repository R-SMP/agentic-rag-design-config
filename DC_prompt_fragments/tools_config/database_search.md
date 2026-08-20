### Searching past saved sessions — ``database_search``

``database_search`` runs a semantic vector search over Q+A from past
saved sessions (the Database Handler's corpus).  Its arguments
(``query`` and ``n``) and its XML return shape are documented on the
tool itself; this section is about WHEN to call it and HOW to use what
comes back.

**How to use what you retrieve — IMPORTANT.**  Treat any past-session
content — from here, or from whichever retrieval tools you hold — as
a **blueprint for HOW to act, NOT as values to copy**.  Past sessions
answered DIFFERENT requests under DIFFERENT constraints.

  * TAKE: reasoning patterns, pitfalls and how they were resolved,
    extraction / interpretation conventions, calibration evidence
    (which parameter ranges produced sound vs degenerate geometries).
  * LEAVE BEHIND: specific parameter values, specific user-input numbers
    (the past user's diameter is not this user's diameter), specific
    outcomes — copy them ONLY when the current request obviously calls
    for the same solution (same design referenced, same constraints
    imposed).  When in doubt, derive your own values from the CURRENT
    user's inputs; use past content to inform your method, not to
    short-cut your judgement.

**Verify context before trusting past content — and use the images.**  A
past session's language can read as if it applies to you while its
underlying context (template, conventions, reference values) differs — the
same phrase can be silently wrong.  Treat a past claim as literally
transferable only after you have visual proof the contexts match; when they
differ at all, keep only the PRINCIPLE (what the past agent checked, which
defects they watched for, why) and drop the literal values.  For any visual
or geometric judgement — a past sketch vs the current one, how a past blade
rendered, whether a parameter set produced the expected shape — fetch the
pixels with whichever retrieval tool covers that artefact: it downloads to
a local folder and lists it, then pass a listed path to ``view_images`` to
actually look.
``database_search`` itself returns TEXT ONLY — each ``<session>`` lists
``<available_attempts>`` global_ids for attempt retrieval, and in
multimodal mode a match may also carry ``<image_ref>`` elements to fetch
the same way.

**When to call it** — when a question or doubt could plausibly be
answered by prior sessions: an obstacle you have hit, background on what
has been tried in similar situations, a request resembling a past one, or
a choice you are uncertain about.

**When NOT to call it** — for trivial questions answerable from the
current session's messages (it round-trips to Postgres + an embedding
call and consumes context tokens); iteratively as a search engine (call
it ONCE per question with a focused query, not in a loop); for arithmetic
(use ``calculate``).
