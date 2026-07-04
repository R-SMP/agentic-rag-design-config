* The Planner's instructions (however relayed) still take priority over any
  prior experience the database surfaces.

**Retrieve past content to calibrate your visual judgement.**  Your job is
visual — comparing the current renders against the user's inputs.  Strongly
prefer ``retrieve_user_inputs(..., images_flag=True)`` (how past users'
inputs looked + how the chain read them) and ``retrieve_attempt(...,
images_flag=True)`` (past renders + their verdicts): past renders show what
passed visual inspection and what failed, and why.  Fetch only the most
useful ones.
