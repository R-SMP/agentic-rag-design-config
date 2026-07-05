### Retrieving past saved content

``retrieve_user_inputs`` and ``retrieve_attempt`` document their purpose,
arguments, and return shape on the tools themselves.  Two things they do
NOT cover:

- **Don't over-call.**  Never retrieve content the live session already
  holds, and never loop — make ONE call with all the relevant ids.
- **Reading a partial response.**  A row missing from Postgres renders
  ``status="not_found"``; a failed R2 image fetch leaves a
  ``<missing path="..."/>`` marker with the rest of the response intact;
  and when the response would exceed the token cap, whole items drop from
  the END of your list under a ``<truncated omitted_.../>`` footer (image /
  render bytes never count toward that cap).
