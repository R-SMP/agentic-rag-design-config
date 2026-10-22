### Searching past saved sessions — ``database_search``

``database_search`` runs a semantic vector search over Q+A from past
saved sessions (the Database Handler's corpus).

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

**Contexts differ silently.**  A past claim can read as if it applies to
you while its template, conventions or reference values differ.  Treat it as
literally transferable only once you have checked the contexts match; when
they do not match in what matters, or when you cannot tell, keep the
PRINCIPLE, drop the literal values, and say in your hand-off that it still
needs a look.

**Ids come off ``<available_attempts>``, not off the answer text.**  The
answers name attempts by the past session's own local numbering ("attempt
002"); the ``global_id`` beside that number in ``<available_attempts>`` is
the one to pass on or retrieve, never the local number.

**Pass on what you found.**  Name in your hand-off only the retrievals that
proved USEFUL — never everything you retrieved — with the id in a fixed form
(``attempt global_id 418``, ``session ID217_20260602_140000``), the local
folder it went to if you fetched it yourself, and one line on why.

When a hand-off names an id and you hold the tool for it, strongly prefer to
open it before you finish your step, and say in one line what came of it —
including when it changed nothing.  When you hold no tool for it, carry the
id and the sender's note forward instead.

**When to call it.**  When a question or doubt could plausibly be
answered by prior sessions: an obstacle you have hit, background on what
has been tried in similar situations, a request resembling a past one, or
a choice you are uncertain about.  A standing directive or hand-off saying
past experience is required counts as one of those: search once before you
commit, and say in one line what came of it.

**When NOT to call it.**  For trivial questions answerable from the
current session's messages (it costs a round-trip and context tokens);
iteratively as a search engine (call it ONCE per question with a focused
query, not in a loop); for arithmetic.
