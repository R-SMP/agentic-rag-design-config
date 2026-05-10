"""Stage A Streamlit entry point — Phase 3 chat UI.

This file is the sole entry point of the deployed web app (no
FastAPI front-door — see ``extra_utilities/cloud_architecture_notes.md``
C2).  Streamlit's ``streamlit run streamlit_app.py`` launches the
HTTP server, renders the page on every interaction, and re-runs
this script top-to-bottom each time.

Stage A scope (this commit, the skeleton):
  * Imports cleanly with no side effects beyond ``st.set_page_config``
    and a placeholder page render.
  * No agent code is wired in yet — the chat handler that calls
    ``agents/dispatch.py:dispatch_turn`` lands in the next commit.
  * Layout choices (single column, chat-style) are decided here so
    later commits only have to populate the message history and
    handle the input box, not redesign the page.

Out of scope for Stage A in general (see the four reference docs):
  * Multi-user concurrency on disk paths — Stage A is one user at
    a time (warnings_developer.md W13, TODO_known_issues.md O9).
  * Save / database persistence — Stage A has no DB; the only
    end-of-conversation control is "End Session", landing in a
    later Phase 3 commit (warnings_developer.md W14, TODO_known_
    issues.md O10, cloud_architecture_notes.md C6).
  * Invite-code auth — lands in Phase 4.

Invariant: this module must import cleanly from a plain
``import streamlit_app`` (e.g. from a smoke test) without
triggering Streamlit-only behaviour.  The ``main()`` function
holds every ``st.*`` call so importing the module does nothing
visible.  Streamlit invokes ``main()`` because the very last
line of the file is ``main()``.
"""

from __future__ import annotations

import streamlit as st


# ---------------------------------------------------------------------------
# Page configuration — must be the first Streamlit call inside main().
# ---------------------------------------------------------------------------

PAGE_TITLE = "Propeller Design Configurator"
PAGE_ICON = ":gear:"


def configure_page() -> None:
    """Apply ``st.set_page_config`` exactly once per run.

    Streamlit re-executes the entire script on every interaction; the
    set_page_config call is fine to repeat as long as it's the first
    Streamlit call of the run.  Wrapped in a function so importing
    the module from a test harness does not invoke it.
    """
    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon=PAGE_ICON,
        layout="centered",
        initial_sidebar_state="auto",
    )


def render_header() -> None:
    """Top-of-page header.  Stable across reruns; no state involved."""
    st.title(PAGE_TITLE)
    st.caption(
        "Multi-agent propeller design assistant — Stage A web UI."
    )


def render_placeholder_body() -> None:
    """Stage-A-skeleton body.  Replaced by the chat surface in the
    next commit.  Lives in its own function so the diff in commit 2
    is concentrated."""
    st.info(
        "**Stage A skeleton.**  The chat interface will be wired in "
        "the next commit (Phase 3 commit 2).  This page currently "
        "verifies that ``streamlit run streamlit_app.py`` boots, "
        "applies the page config, and renders a header without "
        "touching any agent code."
    )


def main() -> None:
    """Entry point invoked once per Streamlit script run.

    Streamlit executes the WHOLE module on every user interaction,
    so anything stateful must live behind ``st.session_state`` —
    not in module-level variables.  Phase 3 commit 2 will introduce
    a ``Session`` (from ``agents.shared.session``) keyed under
    ``st.session_state.session`` exactly for this reason.
    """
    configure_page()
    render_header()
    render_placeholder_body()


# Streamlit invokes the module by re-executing it; calling main()
# at module bottom is the standard pattern.  Guarded by ``__name__``
# so ``import streamlit_app`` from a smoke test stays a no-op.
if __name__ == "__main__":
    main()
