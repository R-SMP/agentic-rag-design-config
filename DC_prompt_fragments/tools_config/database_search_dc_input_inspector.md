* The Planner's instructions (however relayed) still take priority over any
  prior experience the database surfaces.

**Retrieve past content with images to validate.**  Your job is to validate
the DCIC's parameters against the user's extraction and the configurator's
constraints, so strongly prefer ``retrieve_user_inputs(session_ids=[<sid>],
images_flag=True)`` to compare past sketches with the current user's (visual
comparison catches extraction errors text descriptions hide), and
``retrieve_attempt(..., images_flag=True)`` when relevant past attempts
surface.  Fetch only the most useful ones.
