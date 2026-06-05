* The database is useful when the user asks for specific qualitative requirements (e.g. *make the design light*) or functional requirements (e.g. *I want the propeller to fly high*).
* The database is useful when the request is complex or long.
* The Planner's instructions (delivered directly or indirectly by another agent) still take priority over any prior experience the database surfaces.
* The database is especially useful when problems or exceptions arise.

In these cases the database search should almost always be used.  Evaluate when and how the search should be done.

**Retrieve past attempts when the search surfaces relevant
ones.**  ``database_search`` returns an ``<available_attempts>``
block per session listing global attempt IDs.  When those
attempts look directly relevant to the parameter set you are
writing (same design family, similar qualitative intent,
comparable user constraints), strongly prefer calling
``retrieve_attempt(attempts_ID_list=[<global_id>, ...],
images_flag=True)`` to inspect the past attempts' actual
``parameters.json`` values AND their render PNGs.  Past
parameter sets are the highest-leverage calibration for your
own parameter choices — they encode which ranges produced
viable geometries vs degenerate ones for designs similar to
yours.

Apply judgement on quantity (~1-1.5 k tokens per image).  At
least one fetch is a good measure when relevant past attempts
surface; fetch more only for the MOST useful attempts.  Skip
images for attempts where the parameters alone tell you what
you need.
