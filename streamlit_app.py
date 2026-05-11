"""Stage A Streamlit entry point — Phase 3 chat UI.

This file is the sole entry point of the deployed web app (no
FastAPI front-door — see ``extra_utilities/cloud_architecture_notes.md``
C2).  Streamlit's ``streamlit run streamlit_app.py`` launches the
HTTP server, renders the page on every interaction, and re-runs
this script top-to-bottom each time.

Stage A scope:
  * One ``Session`` (``agents/shared/session.py``) per browser tab,
    held in ``st.session_state.session`` and rebuilt on first run.
  * Chat history in ``st.session_state.chat_history`` as a list of
    ``{role, text}`` dicts so script reruns can replay the
    transcript without re-invoking any agent.
  * Per turn: ``agents/dispatch.py:dispatch_turn`` runs the entire
    multi-agent pipeline (Receptionist → Orchestrator → … →
    Receptionist) end-to-end and returns the user-facing reply.
    The Orchestrator is rebuilt from ``session.agent_states`` on
    every turn (cheap because every chain agent's LLM is served
    from ``llm_client_cache``).
  * No DB writes anywhere — Stage A is ephemeral.

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
line of the file is guarded by ``if __name__ == "__main__"``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from agents.dispatch import dispatch_turn
from agents.shared.trace import close_trace, init_trace
from agents.shared.session import Session
from config import LOGS_DIR, USER_INPUTS_DIR
from tools import set_mesh_checks, set_render_library
from workflow_settings import settings as workflow_settings


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

PAGE_TITLE = "Propeller Design Configurator"
PAGE_ICON = ":gear:"


def configure_page() -> None:
    """Apply ``st.set_page_config`` exactly once per script run.

    Must be the first ``st.*`` call inside ``main()``.  Wrapped in a
    function so importing the module from a test harness does not
    invoke it.
    """
    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon=PAGE_ICON,
        layout="centered",
        initial_sidebar_state="auto",
    )


# ---------------------------------------------------------------------------
# Session bootstrap (runs once per browser tab)
# ---------------------------------------------------------------------------


def _new_session_id() -> str:
    """Return a unique session id for the current browser tab.

    Format: ``streamlit_<YYYYMMDD_HHMMSS>_<8-hex>``.  The timestamp
    keeps log files chronologically sortable; the random suffix
    disambiguates two tabs that would otherwise share the same
    second-resolution timestamp.  Per `warnings_developer.md` W13,
    Stage A is single-user-at-a-time — collisions on the same
    second are unlikely AND would only matter on disk-path level
    (which Stage A already accepts).
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"streamlit_{ts}_{suffix}"


def _setup_session_logger(session_id: str) -> Path:
    """Attach a per-session FileHandler to the ``propeller_agent`` logger.

    Idempotent: re-calling for the same session_id (which happens on
    every script rerun) does not stack handlers — we check for an
    existing one writing to the same path first.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"streamlit_{session_id}.log"
    logger = logging.getLogger("propeller_agent")
    for h in logger.handlers:
        if (
            isinstance(h, logging.FileHandler)
            and Path(h.baseFilename).resolve() == log_path.resolve()
        ):
            return log_path
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
    logger.setLevel(logging.DEBUG)
    logger.addHandler(fh)
    return log_path


def _ensure_session() -> Session:
    """Return the per-tab ``Session``, building it on first run.

    Creates ``st.session_state.session`` and ``st.session_state.
    chat_history`` once.  Subsequent script reruns within the same
    browser tab return the existing Session unchanged — that's the
    whole reason for stashing it in ``st.session_state`` rather than
    rebuilding per rerun.

    Note: The Session's ``inputs_dir`` / ``attempts_dir`` /
    ``logs_dir`` fields are deliberately left as None (not the
    ``Session.create_for_v3`` factory), because Stage A's agents
    still write to the global ``config.*`` paths.  See W13 / O9.
    """
    if "session" in st.session_state:
        return st.session_state.session

    # First run for this browser tab.  Apply the same global
    # side-effects the v4 loader applies at startup so render / mesh
    # tools see the right configuration.
    set_mesh_checks(workflow_settings.MESH_CHECKS)
    set_render_library(workflow_settings.RENDER_LIBRARY)

    session_id = _new_session_id()
    log_path = _setup_session_logger(session_id)
    try:
        init_trace(LOGS_DIR)
    except Exception:
        # Trace file is best-effort — a missing trace file does
        # not break the chat surface.  The propeller_agent logger
        # still records the same flow.
        pass

    session = Session(
        session_id=session_id,
        session_ts=datetime.now(timezone.utc),
        mesh_checks=workflow_settings.MESH_CHECKS,
        rag_enabled=workflow_settings.RAG_ENABLED,
        dc_inspector_enabled=workflow_settings.DC_INSPECTOR_ENABLED,
        chain_access=workflow_settings.CHAIN_ACCESS,
        keep_images_in_context=workflow_settings.KEEP_IMAGES_IN_CONTEXT,
        dcoi_comparison_mode=workflow_settings.DCOI_COMPARISON_MODE,
        planner_first=workflow_settings.PLANNER_FIRST,
        render_library=workflow_settings.RENDER_LIBRARY,
    )
    st.session_state.session = session
    st.session_state.chat_history: list[dict] = []
    st.session_state.session_log_path = str(log_path)
    logging.getLogger("propeller_agent").info(
        f"[STREAMLIT] new session id={session_id}"
    )
    return session


# ---------------------------------------------------------------------------
# End-session teardown
# ---------------------------------------------------------------------------


def _detach_session_log_handler(session_log_path: str | None) -> None:
    """Remove the FileHandler the just-ended session attached to the
    ``propeller_agent`` logger.

    Idempotent: a missing path or a logger without a matching handler
    is a no-op.  Leaving the handler attached would leak file handles
    across sessions AND cause the next session's log lines to ALSO
    end up in the previous session's log file because the handler
    is still listening on the same shared logger.
    """
    if not session_log_path:
        return
    target = Path(session_log_path).resolve()
    logger = logging.getLogger("propeller_agent")
    for h in list(logger.handlers):
        if (
            isinstance(h, logging.FileHandler)
            and Path(h.baseFilename).resolve() == target
        ):
            try:
                h.flush()
                h.close()
            except Exception:
                pass
            logger.removeHandler(h)


def end_session() -> None:
    """Clear the Stage A in-memory session and reload the page.

    Stage A is database-less (warnings_developer.md W14 / cloud_
    architecture_notes.md C6), so "End Session" has no save flow.
    The semantics are:
      1. Close the agent flow trace (module-level global; otherwise
         the next session's ``init_trace`` would orphan the file
         handle).
      2. Detach the per-session FileHandler from the
         ``propeller_agent`` logger so the file is released and the
         next session does not double-log into the old file.
      3. Clear every key from ``st.session_state``.  ``_ensure_
         session`` will rebuild a fresh ``Session`` on the next
         script run.
      4. ``st.rerun()`` so the cleared state is reflected
         immediately rather than waiting for the next user
         interaction.

    Stage B will replace this teardown with a Save flow that runs
    the Database Handler before clearing.  Do NOT pre-empt that
    plumbing in Stage A — see warnings_developer.md W14.
    """
    log_path = st.session_state.get("session_log_path")
    try:
        close_trace()
    except Exception:
        # close_trace is best-effort; a failure should not block the
        # session reset.
        pass
    _detach_session_log_handler(log_path)
    logging.getLogger("propeller_agent").info(
        "[STREAMLIT] end_session — clearing state"
    )
    # Iterate over a copy of the keys because clearing mutates the
    # dict while we iterate.
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_sidebar(session: Session) -> None:
    """Sidebar with session metadata + the End Session button.

    The button label is mandated by warnings_developer.md W14 and
    cloud_architecture_notes.md C6: Stage A may NOT use any label
    that promises persistence ("Save", "Save & Quit", etc.) because
    the database is not wired in until Stage B.  The future "Save"
    button arrives in Stage B alongside the DH save flow — at that
    point the sidebar grows a second button; see
    TODO_known_issues.md O10 for the open Stage B UX questions.
    """
    with st.sidebar:
        st.subheader("Session")
        st.caption(f"ID: `{session.session_id}`")
        st.caption(
            f"Started: {session.session_ts.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        st.caption(
            "Stage A — single user at a time, no save (sessions are "
            "ephemeral)."
        )
        st.divider()
        if st.button(
            "End Session",
            type="primary",
            help=(
                "Clear this conversation and start a fresh session.  "
                "Nothing is saved — Stage A has no database yet.  "
                "The future 'Save' button arrives in Stage B."
            ),
            width="stretch",
        ):
            end_session()


def render_header() -> None:
    """Top-of-page header.  Stable across reruns; no state involved."""
    st.title(PAGE_TITLE)
    st.caption(
        "Multi-agent propeller design assistant — Stage A web UI."
    )


def _render_artefacts(artefact_paths: list[str]) -> None:
    """Display each fresh artefact path inline in the current chat
    bubble.  PNGs render as ``st.image``; OBJ files get a small
    text line with the path (Streamlit cannot preview meshes
    inline).  Missing files (deleted between turn-end and rerun)
    are skipped silently with a caption.

    ``st.image`` is wrapped in a try/except because a corrupt or
    unreadable PNG would otherwise propagate up to ``main()`` and
    nuke the entire chat replay — every subsequent rerun would
    re-fire the same exception because the bad path lives in
    ``chat_history``.  We fall back to a small caption with the
    error so the rest of the transcript still renders.
    """
    for raw in artefact_paths:
        path = Path(raw)
        if not path.exists():
            st.caption(f"_missing artefact: {path.name}_")
            continue
        suffix = path.suffix.lower()
        if suffix == ".png":
            try:
                rel = path.relative_to(Path.cwd())
                caption = str(rel)
            except ValueError:
                caption = path.name
            try:
                # ``width="stretch"`` replaces the deprecated
                # ``use_container_width=True`` (removed after
                # 2025-12-31; we are past that date).
                st.image(str(path), caption=caption, width="stretch")
            except Exception as exc:
                logging.getLogger("propeller_agent").warning(
                    f"[STREAMLIT] could not render {path}: {exc}"
                )
                st.caption(
                    f"_failed to render `{path.name}`: "
                    f"{type(exc).__name__}_"
                )
        elif suffix == ".obj":
            st.caption(f"Generated mesh: `{path.name}` ({path})")
        else:
            st.caption(f"Artefact: `{path.name}`")


def render_chat_history() -> None:
    """Replay every prior turn's chat bubbles from ``st.session_state.
    chat_history``.  Streamlit reruns the whole script on every
    interaction, so this loop runs every time and the transcript
    appears intact even after the LLM call from the most recent
    turn has long since returned.  Artefact paths stored alongside
    each assistant message get re-rendered on every replay."""
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["text"])
            if msg.get("artefacts"):
                _render_artefacts(msg["artefacts"])


def handle_user_message(session: Session, user_text: str) -> None:
    """Run one user turn end-to-end against ``dispatch_turn``.

    Appends the user message to history, renders it, dispatches the
    full multi-agent pipeline under a spinner, renders the assistant
    reply (plus any fresh renders / OBJ files produced during the
    turn), and appends the reply with its artefact paths to history.
    Exceptions raised by ``dispatch_turn`` are caught and surfaced as
    an in-chat error bubble so a single failed turn does not nuke
    the whole UI.
    """
    st.session_state.chat_history.append({"role": "user", "text": user_text})
    with st.chat_message("user"):
        st.write(user_text)

    artefact_paths: list[str] = []
    with st.chat_message("assistant"):
        with st.spinner("Thinking — running the multi-agent pipeline..."):
            try:
                result = dispatch_turn(
                    session=session,
                    user_input=user_text,
                    inputs_dir=USER_INPUTS_DIR,
                )
                reply = result.reply_text
                # Store as strings so the chat_history stays plain-
                # data — matches the v3 invariant on Session state.
                artefact_paths = [str(p) for p in result.new_artefacts_paths]
            except Exception as exc:
                logging.getLogger("propeller_agent").exception(
                    f"[STREAMLIT] dispatch_turn raised: {exc}"
                )
                reply = (
                    f"(internal error during this turn — "
                    f"{type(exc).__name__}: {exc}.  Check the session log "
                    f"for the full traceback.)"
                )
        st.write(reply)
        if artefact_paths:
            _render_artefacts(artefact_paths)

    st.session_state.chat_history.append({
        "role": "assistant",
        "text": reply,
        "artefacts": artefact_paths,
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point invoked once per Streamlit script run.

    Streamlit executes the WHOLE module on every user interaction,
    so anything stateful must live behind ``st.session_state`` —
    not in module-level variables.  ``_ensure_session`` is the
    single place where per-tab state is created.
    """
    configure_page()
    session = _ensure_session()
    render_sidebar(session)
    render_header()
    render_chat_history()

    user_text = st.chat_input(
        "Describe the propeller you want to design."
    )
    if user_text:
        handle_user_message(session, user_text)


# Streamlit invokes the module by re-executing it; calling main()
# at module bottom is the standard pattern.  Guarded by ``__name__``
# so ``import streamlit_app`` from a smoke test stays a no-op.
if __name__ == "__main__":
    main()
