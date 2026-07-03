### Retrieving user inputs from past saved sessions — ``retrieve_user_inputs``

``retrieve_user_inputs`` pulls a past saved session's user-supplied
content (chronological text + reference images + image notes) from R2.
Its arguments (``sessions_ID_list``, ``images_flag``) and XML return
shape are documented on the tool itself; this section is about WHEN to
use it and how to read the edge cases.

**When to use it** — after a ``database_search`` hit whose session looks
worth a deeper read: to see what the user actually said or showed, to
ground your response in their raw inputs (not just the saved Q+A), or
when you suspect the outcome hinged on something in their images.

**When NOT to call it** — without a concrete session_id (use
``database_search`` first to discover them); for anything the live
session already contains; or in a loop (one call with all relevant
session_ids).

**Reading the response.**  Image notes are always included when a
session had images (they are text, and free); image BYTES attach as
separate content blocks on the next message only when
``images_flag=True``, each preceded by its R2 key.  A session missing
from Postgres renders as ``status="not_found"``; a failed R2 fetch
leaves ``<missing path="..."/>`` markers (the rest still renders); over
the token cap, whole sessions drop from the END of your list with a
``<truncated omitted_sessions="K"/>`` footer (image bytes are not
counted toward the cap).
