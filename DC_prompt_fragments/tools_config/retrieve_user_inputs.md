### Retrieving past saved content

- **Don't over-call.**  Never retrieve content the live session already
  holds, and never loop — make ONE call with all the relevant ids.
- **Reading a partial response.**  A row missing from Postgres renders
  ``status="not_found"``; a failed R2 fetch leaves a
  ``<missing path="..."/>`` marker with the rest of the response intact;
  and when the response would exceed the token cap, whole items drop from
  the END of your list under a ``<truncated omitted_.../>`` footer.
- **Retrieving is not looking.**  Retrieval DOWNLOADS to a local folder and
  lists what is in it; no image reaches your context until you pass a listed
  path to ``view_images``.  Re-retrieving something another agent already
  fetched is free — it is served from that folder, not fetched again.
- **See it before you trust it.**  For any visual or geometric judgement — a
  past sketch vs the current one, how a past blade rendered, whether a
  parameter set produced the expected shape — a past claim is literally
  transferable only once you have LOOKED and seen the contexts match.<<HAS_USER_INPUTS>>
- **The user's own words are on disk, not in the reply.**
  A retrieval prints each past session's structured extraction, never the
  raw conversation.  The latter is in the ``<folder path=...>`` it names:
  pass the folder to ``read_user_inputs``.  Trust the extraction and do
  this only when it is genuinely not enough — a phrase you need verbatim,
  or wording the extraction leaves ambiguous.<</HAS_USER_INPUTS>>
