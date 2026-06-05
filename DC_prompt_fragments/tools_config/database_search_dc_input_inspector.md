* The database is useful when the user asks for specific qualitative requirements (e.g. *make the design light*) or functional requirements (e.g. *I want the propeller to fly high*).
* The database is useful when the request is complex or long.
* The database is especially useful when problems or exceptions arise.
* The Planner's instructions (delivered directly or indirectly by another agent) still take priority over any prior experience the database surfaces.

In these cases the database search should almost always be used.  Evaluate when and how the search should be done.

**Retrieve past content with images when it helps you
validate.**  Your job is to validate the DCIC's parameter
choices against the user's extraction and the configurator's
constraints.  ``database_search`` surfaces past sessions in
scope; strongly prefer calling
``retrieve_user_inputs(session_ids=[<sid>], images_flag=True)``
on relevant past sessions to compare their sketches with the
current user's — visual comparison catches extraction errors
the text descriptions alone hide.  Same for
``retrieve_attempt(attempts_ID_list=[<global_id>, ...],
images_flag=True)`` when relevant past attempts surface: past
renders + parameters show how comparable parameter sets
actually played out.

Apply judgement on quantity (~1-1.5 k tokens per image).  At
least one fetch is a good measure when relevant past content
surfaces; fetch more sessions / attempts only for the MOST
useful ones.
