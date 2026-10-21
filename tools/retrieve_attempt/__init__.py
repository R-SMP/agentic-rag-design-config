"""DC-specific tool: retrieve_attempt.

Returns the description, parameters JSON, and (optionally) render
PNGs for one or more past saved attempts identified by their
PostgreSQL global ``dc_attempts.attempt_id`` integers.  See
``retrieve_attempt.py`` for the public API and
``setups/<setup>/fragments/tools/retrieve_attempt_tool.md`` for the
agent-facing description.
"""
