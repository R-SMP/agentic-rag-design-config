### Searching past saved sessions — ``database_search``

**How to use what you retrieve — IMPORTANT.**

Treat any past-session content (here or via ``retrieve_user_inputs``
/ ``retrieve_attempt``) as a **blueprint for HOW to act**, NOT as
values to copy.  Past sessions answered DIFFERENT user requests
with DIFFERENT constraints; their concrete numerical choices were
correct for that session, not automatically for this one.

TAKE: reasoning patterns, pitfalls and how they were resolved,
extraction / interpretation conventions, calibration evidence
(which parameter ranges produced sound geometries vs degenerate
ones).

LEAVE BEHIND: specific parameter values (impellerRadius, chords,
angles, ...), specific user-input numbers (the past user's
diameter is not the current user's diameter), specific final
outcomes.  Copy them ONLY when it is obvious from the current
user's request that the practical solution should be the same
(e.g. user explicitly references the same design, or imposes the
same constraints).

When in doubt, derive your own values from the CURRENT user's
inputs.  Use past content to inform your method, not to short-cut
your judgement.

**Same words, different case.**  A past session's language can
read like it applies to your situation, yet the underlying
context (template, conventions, reference values) may not
match — the same phrase that was exact under that context can
be silently wrong under yours.  Example: the past user
sketched on a template with dimension circles and fill-in
fields specific to it ("the inner dashed circle marks 120 mm
diameter"); the current user is using a DIFFERENT template
with similar layout but different conventions.

Treat past claims as transferable LITERALLY only after you have
visual proof the contexts are the same.  When the past session
involved images, pull them via
``retrieve_user_inputs(session_ids=[<sid>], images_flag=True)``,
compare them to the current user's images, and confirm
concretely: same template layout, same labelled fields, same
conventions.  When the contexts differ at all, drop the literal
content and keep only the PRINCIPLE — what the past agent
checked, what defects they watched for, why they made each
verification.  The essence of past reasoning (what to look for
and why) usually transfers; specific tokens pinned to a
different context do not.

**Don't forget the images.**  Both ``retrieve_user_inputs`` and
``retrieve_attempt`` accept ``images_flag=True``, attaching the
past session's user-uploaded images (or the past attempt's
render PNGs) as image content blocks on the next message.  Use
it whenever a visual or geometric judgement would benefit —
comparing a past sketch to the current one, checking how a past
blade geometry actually rendered, sanity-checking that
parameters you are considering produced the expected shape last
time.  Text-only is cheaper but loses the visual evidence; for
visual calls the images are usually worth the fetch.

---

You have access to the ``database_search`` tool, which performs a
semantic vector search over Q+A from past saved sessions that were
captured by the Database Handler.

Signature:

  * ``database_search(query, n, attempt_specific_flag=False,
    metafilters=None)``

**Returns text-only XML.**  A ``<search_meta/>`` header, then up to
``n`` ``<session>`` blocks each carrying a similarity ``score`` and
one or more ``<qa>`` elements.  The best-matching ``<qa>`` per
anchor is marked ``best_match="true"``.  Empty results return
``<no_results>...</no_results>`` with a hint about metafilter
relaxation when filters were applied.  When the response would
exceed the token cap, lowest-ranked anchors are dropped and a
``<truncated omitted_anchors="K"/>`` footer is appended.

**Every returned ``<session>`` carries an ``<available_attempts>``
child block** (always emitted; self-closing when the session has
no saved attempts) listing every attempt saved for that session in
the database.  Each entry is
``<attempt global_id="42" nnn="001"/>``.  Use the ``global_id``
values as input to the ``retrieve_attempt`` tool when you want to
read a specific attempt's description, parameters, or renders —
including attempts that did not directly match your search.

**Matched ``<attempt>`` elements ALSO carry a ``global_id`` attribute**
(in addition to the per-session NNN ``id`` and the similarity
``score``).  That's the canonical handle to feed into
``retrieve_attempt`` for the attempt the search actually matched.

**Image references (multimodal database).**  When the workflow's
Database-options mode is the single-vector multimodal database, a
matched anchor may ALSO include ``<image_ref>`` elements — a past
USER IMAGE or attempt RENDER whose visual content matched your query.
Each carries ``kind`` (``user_input`` or ``render``), an ``r2_key``,
the ``field``, a similarity ``score``, and a ``<caption>`` (the
image's note / description).  An ``<image_ref>`` means that image's
session/attempt is relevant — to SEE the actual pixels, call
``retrieve_user_inputs(session_ids=[<sid>], images_flag=True)`` for a
``user_input`` hit, or
``retrieve_attempt(attempt_ids=[<global_id>], images_flag=True)`` for
a ``render`` hit.  The ``<search_meta db="..."/>`` attribute tells you
which table answered (``chunks`` text-only vs ``chunks_mm``
multimodal); a ``fallback="..."`` attribute means a multimodal query
degraded to text-only (the images would not appear in that response).

**Reasons to call it** — when you have a question or doubt that
prior sessions could plausibly answer:

  * **Problem-related**: you face an obstacle in the current
    session and want to know whether past sessions ran into the
    same one and how they resolved it.
  * **Context-related**: you need background on what has been
    tried before in similar situations.
  * **Request-related**: the user's request resembles something a
    past session worked on; you want to ground your response in
    that prior outcome.
  * **Doubt-related**: you are uncertain about a choice and want
    to see what comparable past decisions led to.

**When NOT to call it.**

  * For trivial in-turn questions answerable from the current
    session's messages — the tool round-trips to Postgres + an
    embedding API call and consumes tokens in your context.
  * Iteratively as a search engine — call it ONCE per question
    with a focused query, not in a loop.
  * For arithmetic — use ``calculate``.

**``n`` is the number of past sessions or attempts to retrieve.**
The tool returns up to ``n`` distinct past sessions (or attempts
when ``attempt_specific_flag=True``) whose content best matches
your query.

**``attempt_specific_flag`` scope.**

  * ``False`` (default): retrieves SESSIONS.  Each returned
    ``<session>`` includes both session-wide context AND every
    attempt within it.  Use for broad context.
  * ``True``: retrieves ATTEMPTS only.  Session-wide content is
    excluded.  Use for narrow per-iteration context (e.g.
    *"parameters used for the best attempt in similar past
    sessions"*).

<!--
NOTE for fragment editors: the curly braces appearing below are
DOUBLED on purpose.  This fragment is substituted into each
agent's prompt.md via the ``$database_search_tool`` slot; the
assembled template is later passed through Python's str.format
method at agent wiring time so that other named slots (the
chain-access block, the routing instructions, etc.) get filled.
str.format interprets single curly braces as placeholders and
crashes on any literal lone or non-matching pair.  Doubling each
opening and closing curly survives both stages and reaches the
LLM as a single brace.  See v9_gotchas.md "brace-escape rule for
.format-templated prompts".  This comment intentionally contains
NO literal curly braces and NO slot-shaped tokens so it cannot
itself trigger the very bug it documents.
-->

**Metafilter syntax — hybrid string-prefix.**  Pass ``None`` or
``{{}}`` to skip filtering.

  * Equality:    ``{{"dc_name": "propeller"}}``
  * Comparison:  ``{{"satisfaction": ">=7"}}``
    (ops: ``=``, ``>=``, ``<=``, ``>``, ``<``)
  * IN-list:     ``{{"agent_from": ["DH", "DCII"]}}``
  * Combine:     ``{{"has_renders": true, "satisfaction": ">=7"}}``

Supported keys (v1):

  * **sessions.\***: ``dc_name``, ``satisfaction`` (0-10),
    ``session_ts`` (ISO 8601 string), ``schema_version``,
    ``dc_inspector_enabled``, ``user_id``, ``user_provided_images``
  * **dc_attempts.\***: ``has_geometry``, ``has_renders``
  * **chunks.\***: ``agent_from``, ``field``

Parameter-value filters (e.g. ``bladeCount>=5``) are NOT in v1.

**No bytes inline.**  ``database_search`` returns text + image
REFERENCES (see "Image references" above), never image bytes or mesh
files.  After reading the response, fetch a specific anchor's actual
images with ``retrieve_user_inputs`` (past user images) or
``retrieve_attempt`` (attempt renders, via the ``global_id``), both
with ``images_flag=True``.
