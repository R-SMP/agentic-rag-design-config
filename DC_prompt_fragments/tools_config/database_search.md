### Searching past saved sessions — ``database_search``

``database_search`` runs a semantic vector search over Q+A from past
saved sessions (the Database Handler's corpus).  Its arguments and
its XML return shape are documented on the tool itself; this section is
about WHEN to call it and HOW to use what comes back.

**How to use what you retrieve — IMPORTANT.**  Treat any past-session
content — from here, or from whichever retrieval tools you hold — as
a **blueprint for HOW to act, NOT as values to copy**.  Past sessions
answered DIFFERENT requests under DIFFERENT constraints.

  * TAKE: reasoning patterns, pitfalls and how they were resolved,
    extraction / interpretation conventions, calibration evidence
    (which parameter ranges produced sound vs degenerate geometries).
  * BE CAREFUL WITH: specific parameter values, specific user-input numbers
    (the past user's diameter is not this user's diameter), specific
    outcomes.  Reuse them when the past design is of the same nature and
    its values fit the current design intent; derive your own when it is
    not, or when you cannot tell.  Past content should inform your
    method, not short-cut your judgement.

**Verify context before trusting past content.**  A past session's language
can read as if it applies to you while its underlying context (template,
conventions, reference values) differs — the same phrase can be silently
wrong.  Treat a past claim as literally transferable only once you have
checked that the contexts match; when they differ at all, or when you have
no way to check, keep only the PRINCIPLE (what the past agent checked, which
defects they watched for, why), drop the literal values, and say in your
hand-off that it still needs a look.
``database_search`` itself returns TEXT ONLY — each ``<session>`` lists
``<available_attempts>`` global_ids for attempt retrieval.  Answers refer
to attempts by the PAST session's own local numbering ("attempt 002", or
"the second attempt"); read that number's ``global_id`` off
``<available_attempts>`` and never reuse the local number itself.

**Pass on what you found.**  Name in your hand-off only the retrievals that
proved USEFUL — never everything you retrieved — with the id in a fixed form
(``attempt global_id 418``, ``session ID217_20260602_140000``), the local
folder it went to if you fetched it yourself, and one line on why.

When a hand-off names one and you hold the tool for it, strongly prefer to
open it before you finish your step, and say in one line what came of it —
including when it changed nothing.  When you hold no tool for it, carry the
id and the sender's note forward instead.

**When to call it** — when a question or doubt could plausibly be
answered by prior sessions: an obstacle you have hit, background on what
has been tried in similar situations, a request resembling a past one, or
a choice you are uncertain about.  A standing directive or hand-off saying
past experience is required counts as one of those: search once before you
commit, and say in one line what came of it.

**When NOT to call it** — for trivial questions answerable from the
current session's messages (it round-trips to Postgres + an embedding
call and consumes context tokens); iteratively as a search engine (call
it ONCE per question with a focused query, not in a loop); for arithmetic
(use ``calculate``).
