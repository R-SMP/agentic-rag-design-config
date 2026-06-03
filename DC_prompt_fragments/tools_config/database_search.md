### Searching past saved sessions — ``database_search``

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

**Text-only.**  ``database_search`` returns no images, no mesh
files.  After reading the text response, if a specific anchor's
images would actually help, a future artefact-fetch tool will let
you request that one anchor's user-input images / attempt renders.
