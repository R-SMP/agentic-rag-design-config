### Searching past saved sessions — ``database_search``

``database_search`` runs a semantic vector search over Q+A from past
saved sessions (the Database Handler's corpus).  Its arguments
(``query``, ``n``, ``attempt_specific_flag``, and ``metafilters`` —
including the metafilter syntax and supported keys) and its XML return
shape are documented on the tool itself; this section is about WHEN to
call it and HOW to use what comes back.

**How to use what you retrieve — IMPORTANT.**  Treat any past-session
content (here or via ``retrieve_user_inputs`` / ``retrieve_attempt``) as
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

**Same words, different case.**  A past session's language can read as if
it applies to you while its underlying context (template, conventions,
reference values) does not — the same phrase can be silently wrong under
your context.  Treat past claims as transferable LITERALLY only after you
have visual proof the contexts match: when the past session involved
images, pull them (``retrieve_user_inputs(session_ids=[<sid>],
images_flag=True)``), compare, and confirm the layout / labelled fields /
conventions are the same.  When the contexts differ at all, keep only the
PRINCIPLE — what the past agent checked, what defects they watched for,
why — and drop the literal values.

**Use the images.**  For any visual or geometric judgement — comparing a
past sketch to the current one, checking how a past blade actually
rendered, confirming that parameters you are considering produced the
expected shape last time — fetch the pixels with ``retrieve_user_inputs``
(past user images) or ``retrieve_attempt`` (attempt renders), both with
``images_flag=True``.  ``database_search`` itself returns TEXT ONLY: each
matched ``<session>`` carries an ``<available_attempts>`` list of
``global_id`` values you can feed to ``retrieve_attempt`` (including
attempts that did not directly match your query).  In the multimodal
Database-options mode a match may also carry ``<image_ref>`` elements (a
past user image or render whose visual content matched) — fetch the
actual pixels the same way.  Text-only is cheaper but loses the visual
evidence; for visual calls the fetch is usually worth it.

**When to call it** — when a question or doubt could plausibly be
answered by prior sessions: an obstacle you have hit, background on what
has been tried in similar situations, a request resembling a past one, or
a choice you are uncertain about.

**When NOT to call it** — for trivial questions answerable from the
current session's messages (it round-trips to Postgres + an embedding
call and consumes context tokens); iteratively as a search engine (call
it ONCE per question with a focused query, not in a loop); for arithmetic
(use ``calculate``).
