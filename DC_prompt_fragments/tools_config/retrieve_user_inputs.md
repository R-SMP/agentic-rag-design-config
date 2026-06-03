### Retrieving user inputs from past saved sessions — ``retrieve_user_inputs``

You have access to ``retrieve_user_inputs``, which pulls the
user-supplied content (text + reference images) for one or more
past saved sessions from R2 storage.

Signature:

  * ``retrieve_user_inputs(sessions_ID_list, images_flag=False)``

**Returns text-only XML.**  A ``<retrieve_user_inputs_meta/>`` header,
then one ``<session id="..."/>`` block per requested session_id.
Each existing session block carries the user's full chronological
text in ``<user_query>`` and, when that session had reference
images, an ``<image_notes>`` block (always included) plus an
``<images>`` block listing the R2 keys (whose bytes are attached
separately when ``images_flag=True``).

**Reasons to call it.**

  * You just received a ``database_search`` result and one of the
    returned sessions looks worth a deeper read — you want to see
    what the user actually said or showed in that session.
  * You need the user's original raw inputs (not just the saved
    Q+A from the Database Handler) to ground your own response.
  * You suspect the past session's outcome was driven by something
    in the user's images that the extracted Q+A might have missed.

**When NOT to call it.**

  * Without a concrete session_id to retrieve — use
    ``database_search`` first to discover plausible sessions.
  * For information the current live session already contains —
    re-fetching past inputs costs an R2 round-trip and tokens.
  * In a tight loop — call it once with the relevant session_ids,
    not iteratively per session.

**Arguments.**

  * ``sessions_ID_list`` — a list of session_id strings (e.g.
    ``"ID042_20260602_140000"``).  Get these from a
    ``database_search`` response's ``<session id="..."/>`` elements.
  * ``images_flag`` — ``True`` to attach the user's reference image
    bytes on the next message; ``False`` (default) to skip image
    bytes.  **Image notes are always included** when the session
    had images, regardless of this flag — they are text and free.

**Image delivery.**  When ``images_flag=True`` and a session had
reference images, the image bytes attach as separate content blocks
on the next message you see (same convention as
``load_input_images``).  Each block is preceded by its R2 key as
text so the key remains in your history even if image bytes are
later stripped.

**Missing files.**  If an expected R2 file fetch fails (e.g. R2 was
unavailable during the original save), the session's block carries
``<missing path="..."/>`` markers identifying which files were
unreachable.  The rest of the session block is still rendered with
whatever did fetch.

**Unknown session_ids.**  When a requested session_id is not in
Postgres, the block is rendered as
``<session id="..." status="not_found"/>`` so you know the request
was acknowledged without ambiguity.

**Token cap.**  When the assembled XML would exceed the configured
cap, whole sessions are dropped from the END of your input list
(lowest priority first) and a ``<truncated omitted_sessions="K"/>``
footer is appended.  Image bytes are NOT counted toward the text
cap — they ship as requested via ``images_flag``.
