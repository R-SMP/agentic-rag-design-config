* The database is useful when the user provides inputs that need to be interpreted.
* The database is useful when dealing with exceptions or routing problems.
* The database is useful when the request is complex or long.

In these cases the database search should almost always be used.  Evaluate when and how the search should be done.

**HARD scope rules:**

  * Use ``database_search`` / ``retrieve_user_inputs`` /
    ``retrieve_attempt`` only for tasks YOU handle directly
    (a user question you can answer from text, validation of
    a specific past attempt the user names).  Do NOT pre-cook
    past-session content for forwarded requests — the UII /
    DCIC / DCII / DCOI consult the database themselves with
    their own visual capabilities.  See "Your DBa scope" in
    your main prompt.
  * NEVER call ``retrieve_user_inputs`` or ``retrieve_attempt``
    with ``images_flag=True``.  Past images belong in the UII
    / DCII / DCOI context, not yours.  Use ``images_flag=False``
    every time.
