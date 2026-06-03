### Retrieving past attempts — ``retrieve_attempt``

You have access to ``retrieve_attempt``, which pulls the
system-generated artefacts (description, parameter snapshot, render
PNGs) for one or more past saved attempts from R2 storage.

Signature:

  * ``retrieve_attempt(attempts_ID_list, images_flag=False)``

**Returns text-only XML.**  A ``<retrieve_attempt_meta/>`` header
(carrying the active render-view policy) followed by one
``<attempt id="..."/>`` block per requested global attempt id.  Each
existing attempt's block carries ``<description>``, ``<parameters>``,
and (when applicable) ``<renders>`` listing R2 keys whose bytes
attach separately on the next message.

**Reasons to call it.**

  * You just received a ``database_search`` result and one of the
    returned attempts looks worth a deeper read — you want to see
    the attempt's full description and parameter values.
  * You need the rendered geometry of a specific past attempt to
    inform a visual judgement on the current design.
  * You want to compare the current attempt's parameters against
    those of a similar past attempt.

**When NOT to call it.**

  * Without a concrete global attempt id — use ``database_search``
    first to discover plausible attempts (their global ids appear in
    the response's ``<available_attempts>`` block).
  * For information about the user's original inputs — that is
    ``retrieve_user_inputs``'s job (raw user inputs are session-
    scoped, not attempt-scoped).
  * In a tight loop — call it once with the relevant global ids,
    not iteratively per attempt.

**Arguments.**

  * ``attempts_ID_list`` — a list of **global** attempt id integers
    (PostgreSQL ``BIGSERIAL dc_attempts.attempt_id`` values).  The
    per-session NNN (``001``, ``002``, …) is for human readability
    only; this tool resolves the global id against Postgres to find
    the matching R2 location.
  * ``images_flag`` — ``True`` to attach render PNG bytes on the
    next message; ``False`` (default) for a text-only response.

**Render-view policy.**  The deployed system controls which of the
three views (``isometric``, ``top``, ``side``) get attached.  The
meta header's ``render_views_in_scope`` attribute lists the
admitted views as a comma-joined string (e.g.
``render_views_in_scope="isometric"``).  When ``images_flag=True``
and the attempt's ``has_renders=TRUE``, only the views in scope are
fetched; the rest are silently omitted from the ``<renders>``
block.  An attempt with ``has_renders=FALSE`` produces no
``<renders>`` block at all.

**Image delivery.**  When ``images_flag=True`` and render PNGs are
in scope, the bytes attach as separate content blocks on the next
message (same convention as ``load_input_images`` and
``retrieve_user_inputs``).  Each block is preceded by its R2 key as
text so the key remains in your history even if image bytes are
later stripped.

**Missing files.**  If an expected R2 file fetch fails (e.g.
attempt was uploaded before the Phase 5A key change, or R2 was
unavailable during the original save), the attempt's block carries
``<missing path="..."/>`` markers identifying which files were
unreachable.  The rest of the block is still rendered with whatever
did fetch.

**Unknown global ids.**  When a requested global id is not in the
``dc_attempts`` table, the block is rendered as
``<attempt id="..." status="not_found"/>``.

**Token cap.**  When the assembled XML would exceed the configured
cap, whole attempts are dropped from the END of your input list
(lowest priority first) and a ``<truncated omitted_attempts="K"/>``
footer is appended.  Image bytes are NOT counted toward the text
cap — they ship as requested via ``images_flag``.
