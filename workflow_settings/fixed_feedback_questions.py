"""Fixed feedback questions asked to the user at End Session.

These are NOT user-editable through the "Questions for Saved
Sessions" web view.  They are rendered there as a read-only,
greyed-out table at the BOTTOM of the page, beneath the user-
editable schedule, so the developer sees them in context but
cannot mutate them through the UI.

The two questions are mirrored to ``chunks`` rows at End Session
time (architecture doc §3.3):

    - "Which parts of the process satisfied your request?"
        → field='Positive User Comments', agent_from='User',
          agents_to=DEFAULT_AGENTS_TO_ACL (the 9 primary chain agents)
    - "Which parts of the process did NOT satisfy your request?"
        → field='Negative User Comments', same agent_from / agents_to

Plus a single labelled-block concatenation lands in
``sessions.feedback`` (TEXT column, schema v5).  The labelled-block
format mirrors the DH's per-Q+A file delimiter convention so a
human reading the column sees the structure immediately::

    --- Positive ---
    <answer to "Which parts of the process satisfied your request?">

    --- Negative ---
    <answer to "Which parts of the process did NOT satisfy your request?">

Unanswered questions are skipped (no empty block, no empty chunks
row).  Future expansion of the list just appends another labelled
block — no schema change required.

To ADD a third feedback question:
    1. Append a new dict to FIXED_FEEDBACK_QUESTIONS below.
    2. Update web/app.js's End Session modal in the same commit so
       the user is actually asked the new question.
    3. (Optional) Update the architecture doc §3.3 worked example
       if the new question is notable.

No database migration is needed:
    - The chunks mirror is open-ended (each question = one
      potential row; the field column carries the distinction).
    - sessions.feedback is just appended labelled-block text.

To CHANGE the wording of an existing question:
    1. Edit the "question" string here AND in web/app.js's modal
       in the same commit so the question shown to the user and the
       question saved to chunks.question stay in lockstep.
    2. Past sessions' chunks rows keep the OLD wording frozen in
       their chunks.question column — that is the desired
       audit-trail behaviour.

This file is the SINGLE source of truth for the constant; the
architecture doc, dh_schedule.py, db_writer.py, the workflow-
settings editor UI, and the End Session modal all read from here
(directly or transitively).
"""

from __future__ import annotations

# Each entry carries:
#   id            — stable identifier (used as the row key when the
#                   constant is rendered in the read-only UI table).
#   field         — chunks.field value when the row lands in the DB.
#                   Architecture doc §3.3 locks these strings.
#   question      — exact wording shown to the user AND stored on
#                   chunks.question.  Must match web/app.js's modal.
#   block_label   — used by db_writer.save_session_feedback() to build
#                   the "--- <block_label> ---" header in the
#                   sessions.feedback labelled-block concatenation.
FIXED_FEEDBACK_QUESTIONS: tuple[dict[str, str], ...] = (
    {
        "id":          "fixed_positive",
        "field":       "Positive User Comments",
        "question":    "Which parts of the process satisfied your request?",
        "block_label": "Positive",
    },
    {
        "id":          "fixed_negative",
        "field":       "Negative User Comments",
        "question":    "Which parts of the process did NOT satisfy your request?",
        "block_label": "Negative",
    },
)
