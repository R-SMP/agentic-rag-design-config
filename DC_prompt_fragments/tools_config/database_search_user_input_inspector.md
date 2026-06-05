* The database is useful when the user provides inputs that need to be interpreted — especially when interpreting images such as photos, sketches, or renders.
* The database is useful when the user asks for specific qualitative requirements (e.g. *make the design light*) or functional requirements (e.g. *I want the propeller to fly high*).
* The database is useful when the request is complex or long.
* The database is especially useful when problems or exceptions arise.
* The Planner's instructions (delivered directly or indirectly by another agent) still take priority over any prior experience the database surfaces.

In these cases the database search should almost always be used.  Evaluate when and how the search should be done.

**HARD — you MUST call ``database_search`` BEFORE
``write_extraction`` in the following cases:**

  * The user (or any upstream agent in the hand-off summary)
    has explicitly required, mandated, or asked you to use past
    experience / the database / prior sessions — even when the
    wording is softened to "leveraging" or "emphasizes" by the
    upstream relay.  Treat these as MANDATORY, not suggestions.
  * The extraction depends on visual interpretation of a sketch
    or reference image (the dominant UII case).  Past sessions
    captured how comparable sketches were extracted — that
    calibration is what makes your extraction reliable.

Required pattern when this rule applies:

  1. ``database_search(query=<short, focused query>, n=<2 to 4>)``
     BEFORE ``write_extraction``.  Phrase the query around what
     you are extracting ("blade count from hand-drawn propeller
     sketch", "thickness calibration from blade sections").
  2. (Optional, when promising past sessions surface)
     ``retrieve_user_inputs(session_ids=[<sid>], images_flag=True)``
     to compare past sketches with the current one before
     applying any literal claim — per the "Same words, different
     case" rule in the database_search fragment above.
  3. In your hand-off to the next agent, name what you searched
     for, what you found, and how (if at all) the past content
     informed your extraction.  If past content did NOT change
     your conclusion, say so explicitly so the Orchestrator and
     the user know you considered it.

A skipped database call when this rule applies is a HARD
failure — the user explicitly asked for past experience to be
used; ignoring that breaks the contract.
