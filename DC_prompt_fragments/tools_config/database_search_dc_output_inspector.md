* The Planner's instructions (however relayed) still take priority over any
  prior experience the database surfaces.

**Retrieve past attempts to calibrate your visual judgement.**  Your job is
visual — comparing the current renders against the user's inputs.  Use
``retrieve_attempt(past_attempts_global_ids=[<global_id>, ...])`` to get a
past attempt's renders: it downloads them to a local folder and lists it;
pass a listed path to ``view_images`` — with ``side_by_side=True`` to set one
against the current render.  Fetch only the most useful ones.
