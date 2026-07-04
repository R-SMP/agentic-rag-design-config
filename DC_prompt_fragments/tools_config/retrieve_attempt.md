### Retrieving past attempts — ``retrieve_attempt``

``retrieve_attempt`` pulls a past saved attempt's system-generated
artefacts (description, parameter snapshot, render PNGs) from R2.  Its
arguments (``attempts_ID_list`` of GLOBAL attempt ids, ``images_flag``)
and XML return shape are documented on the tool itself; this section is
about WHEN to use it and how to read the edge cases.

**When to use it** — after a ``database_search`` hit (global ids appear
in its ``<available_attempts>`` block) or a ``retrieve_user_inputs``
read: to see an attempt's full description + parameter values, to view
its rendered geometry for a visual judgement, or to compare its
parameters against the current attempt's.

**When NOT to call it** — without a concrete GLOBAL attempt id (use
``database_search`` first; the global ids appear in its
``<available_attempts>`` block), for the user's original inputs (that is
``retrieve_user_inputs``'s job — raw inputs are session-scoped, not
attempt-scoped), or in a loop (one call with all relevant ids).

**Reading the response.**  The meta header's ``render_views_in_scope``
lists which of isometric / top / side the deployed policy admits; with
``images_flag=True`` only those views' PNG bytes attach (each preceded by
its R2 key), and an attempt with no renders yields no ``<renders>`` block.
The ``status="not_found"`` / ``<missing path="..."/>`` /
``<truncated omitted_attempts="K"/>`` conventions — and image bytes not
counting toward the token cap — are the same as ``retrieve_user_inputs``
above.
