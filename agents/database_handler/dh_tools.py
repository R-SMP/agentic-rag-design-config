"""Tools bound to the Database Handler.

The DH is otherwise tool-less (its prompt explicitly says so).  The one
exception is the post-identification save: when the DH is interviewing
an *identifying attempt-specific* row of the schedule, the system forces
the DH to call :func:`save_attempt_data` with the list of attempt
numbers Agent A named — or an empty list (or ``["none"]``) if no
specific attempt could be identified.

(Renamed in Phase 3C from ``save_attempt_artefacts``.  See architecture
doc §9.5 and warnings_developer.md W18.  The function still uploads the
6 whitelisted attempt-folder artefacts to R2; Phase 3C extended it to
ALSO persist per-attempt data to Postgres — ``dc_attempts`` +
``dc_attempt_parameters``.)

Multi-attempt support
---------------------
The tool accepts a LIST of attempt ids so an identifying question that
pins down more than one attempt (e.g. "describe non-satisfactory
attempts that provided useful insights") can fan out cleanly.  When
multiple attempt ids are passed, every Q(N).x sub-row of this parent
runs N times — once per resolved attempt, in the order the DH
provided.  Each attempt's folder content lives at its own R2 prefix
``<R2_KEY_PREFIX>/<session_id>/attempts/<NNN>/`` and the sub-row
``.txt`` files acquire the ``__<NNN>`` suffix so they don't collide
across attempts.

The langchain ``@tool`` decorator below produces the schema the LLM
uses to format its tool call.  The body intentionally just records the
call and returns a placeholder string — the real work (resolve each
local attempt folder, validate the input list, ``upsert_attempt`` +
``upsert_attempt_parameters`` into Postgres, upload the whitelisted
files to R2 with the rename pattern, push a ``ToolMessage`` back to
the DH carrying success / failure + retry counter) all happens inside
``database_handler.populate_database``'s tool-call handler, where it
has live access to ``session_dir`` / ``session_id`` / the in-progress
``attempt_ids_by_parent`` map / the R2 uploader / the Postgres pool
via ``db_writer``.
"""

from __future__ import annotations

from langchain_core.tools import tool


# Public name used in:
#   * the force-tool path (``tool_choice="save_attempt_data"``)
#   * the prompt rules (so the DH knows what to call)
#   * the ToolMessage round-trip back to the DH
SAVE_ATTEMPT_DATA_TOOL_NAME = "save_attempt_data"


@tool(SAVE_ATTEMPT_DATA_TOOL_NAME)
def save_attempt_data(attempt_ids: list[str]) -> str:
    """Save the data of one OR MORE design attempts to the database
    mirror (Postgres ``dc_attempts`` + ``dc_attempt_parameters``) and
    the artefact mirror (R2).

    Call this tool IMMEDIATELY after Agent A answers an identifying
    attempt-specific question, before producing any SAVE: body.

    Pass a JSON list of attempt identifiers.  Each element may be:

    * The attempt's identifier as Agent A named it — a number like
      ``"002"`` (or ``"2"``, ``"attempt 002"``, an ordinal like
      ``"second"``, or a full slug like
      ``"20260530_142312_002_..."``).  The system extracts the
      3-digit number from each element, locates the matching folder
      inside this session's ``attempts/`` tree, then:
        - reads ``parameters.json`` and upserts the attempt into
          Postgres (``dc_attempts`` + ``dc_attempt_parameters``);
        - uploads ``parameters.json``, ``propeller_mesh.obj``,
          ``render_*.png``, and ``description.txt`` (whichever
          exist) per attempt to the R2 mirror — renamed with the
          session and attempt ids — under the path
          ``<prefix>/<session_id>/attempts/<NNN>/...``.

    * The literal string ``"none"`` (case-insensitive) — anywhere in
      the list — when Agent A did NOT identify any specific attempt
      (e.g. the answer was "no attempt fully satisfied the user", or
      the session generated no attempts at all).  No artefacts are
      uploaded; no Postgres rows are written; the entire question
      block (this question and any sub-questions) is then dropped
      from the saved database.

    An empty list ``[]`` is also treated as "no attempt".

    The system tells you via a ToolMessage whether each call element
    succeeded, failed validation, or resolved zero / multiple attempt
    folders.  You are given up to three attempts to land a valid call
    (the full list must validate as a whole); after that the system
    synthesises an empty list and moves on.
    """
    # No-op body — the system intercepts the call and runs the real
    # logic.  Returning a sentinel string makes debugging
    # straightforward if a malformed binding ever lets the call reach
    # this function.
    return (
        f"(no-op stub — the system handles save_attempt_data; "
        f"caller passed attempt_ids={attempt_ids!r})"
    )
