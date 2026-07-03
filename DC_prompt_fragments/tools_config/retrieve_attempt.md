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
``database_search`` first); for the user's original inputs (that is
``retrieve_user_inputs``'s job — raw inputs are session-scoped, not
attempt-scoped); or in a loop (one call with all relevant ids).

**Reading the response.**  The meta header's ``render_views_in_scope``
lists which of isometric / top / side the deployed policy admits; with
``images_flag=True`` only those views' PNG bytes attach (as content
blocks on the next message, each preceded by its R2 key), and an attempt
with no renders yields no ``<renders>`` block.  An id missing from
``dc_attempts`` renders as ``status="not_found"``; a failed R2 fetch
leaves ``<missing path="..."/>`` markers; over the token cap, whole
attempts drop from the END with a ``<truncated omitted_attempts="K"/>``
footer (image bytes are not counted toward the cap).
