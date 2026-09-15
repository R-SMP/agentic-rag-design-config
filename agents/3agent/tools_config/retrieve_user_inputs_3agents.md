### Retrieving past saved content

- **Don't over-call.**  Never retrieve content the live session already
  holds, and never loop — make ONE call with all the relevant ids.
- **Reading a partial response.**  A row missing from Postgres renders
  ``status="not_found"``; a failed R2 fetch leaves a
  ``<missing path="..."/>`` marker with the rest of the response intact;
  and when the response would exceed the token cap, whole items drop from
  the END of your list under a ``<truncated omitted_.../>`` footer.<<CAN_SEE>>
- **Retrieving is not looking.**  Retrieval DOWNLOADS to a local folder and
  lists what is in it; no image reaches your context until you pass a listed
  path to ``view_images``.  Re-retrieving something another agent already
  fetched is free — it is served from that folder, not fetched again.
- **See it before you trust it.**  For any visual or geometric judgement — a
  past sketch vs the current one, how a past blade rendered, whether a
  parameter set produced the expected shape — a past claim is literally
  transferable only once you have LOOKED and seen the contexts match.<</CAN_SEE>><<CANNOT_SEE>>
- **Retrieving is not looking, and you cannot look.**  Retrieval DOWNLOADS to
  a local folder and lists what is in it.  Nothing you hold opens an image, so
  retrieve for the TEXT — parameter values, notes, the extraction — and treat
  a listed image path as something to pass on, never to read.  Re-retrieving
  what another agent already fetched is free.
- **Never settle a visual question yourself.**  For any visual or geometric
  judgement — a past sketch vs the current one, how a past blade rendered,
  whether a parameter set produced the expected shape — you cannot confirm the
  contexts match.  Keep the PRINCIPLE, drop the literal values, and say in
  your hand-off that the point needs a look, with the path.<</CANNOT_SEE>><<HAS_USER_INPUTS>>
- **The user's own words are on disk, not in the reply.**
  A retrieval prints an ``<extracted_inputs>`` block per past session: a
  short, complete list of what that user asked for, written when the session
  ran.  This system keeps no such file of its own, so read it as a trusted
  summary.  The raw conversation behind it is in the ``<folder path=...>``
  the response names — pass that folder to ``read_user_inputs`` only if the
  summary is genuinely not enough.<</HAS_USER_INPUTS>>
