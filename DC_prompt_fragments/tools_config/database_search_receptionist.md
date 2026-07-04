* Use the database only for a task YOU handle directly (a user question you
  can answer from past text, or confirming a specific past attempt the user
  names).  Do NOT pre-cook past-session content for a forwarded request, and
  NEVER call ``retrieve_user_inputs`` / ``retrieve_attempt`` with
  ``images_flag=True`` — past images belong in the UII / DCII / DCOI context.
  (Full rule: "Your DBa scope" in your main prompt.)
