"""F4 JavaScript web interface — FastAPI backend (local, experimental).

The Stage A "shift Streamlit -> JavaScript" prototype (F4 / W17).
This is a **thin shim** over ``agents/dispatch.py:dispatch_turn`` —
the exact same pipeline wiring as ``streamlit_app.py``; only the I/O
surface differs (JSON/HTTP for a browser JS frontend instead of
Streamlit widgets).  Per W17 NO agent or pipeline logic lives here.

Local only.  NOT wired into Railway / the Stage A container (still
Streamlit per cloud_architecture_notes.md C2).  Run:

    pip install -r requirements.txt -r requirements-web.txt
    uvicorn web_app:app --reload --port 8000

Then open http://localhost:8000 .

Single user at a time (same W13/O9 constraint as Stage A): one
in-process Session, global on-disk paths.  Auth is OPTIONAL locally —
the invite-code gate is enforced only when ``INVITE_CODE`` is set in
the environment; unset means "open" (local-dev convenience).
"""

from __future__ import annotations

import asyncio
import functools
import hmac
import json
import logging
import os
import queue
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import importlib

from agents.dispatch import dispatch_turn
from agents.loader import _archive_previous_session
from agents.shared.attempts_tool import attempt_label_for_path
from agents.shared.file_utils import pair_input_images
from agents.shared.session import Session
from agents.shared.stop_signal import (
    clear_stop as stop_signal_clear,
    request_stop as stop_signal_request,
)
from agents.shared.trace import close_trace, init_trace
from agents.shared.viz_bus import (
    publish as viz_publish,
    subscribe as viz_subscribe,
    unsubscribe as viz_unsubscribe,
    get_last_visualized_attempt_dir as viz_get_last_attempt_dir,
    set_last_visualized_attempt_dir as viz_set_last_attempt_dir,
)
from config import ATTEMPTS_DIR, INPUT_IMAGES_DIR, LOGS_DIR, USER_INPUTS_DIR
from tools import set_mesh_checks, set_render_library
from tools.generate_mesh.generate_mesh import (
    MeshGenerationError,
    render_mesh_obj_text,
)
from workflow_settings import dh_schedule as settings_dh_schedule
from workflow_settings import editor as settings_editor
from workflow_settings import llm_routing as settings_llm_routing
from workflow_settings import settings as workflow_settings

logger = logging.getLogger("propeller_agent")

WEB_DIR = Path(__file__).parent / "web"
INVITE_CODE_ENV = "INVITE_CODE"

# Image Inputs interface — same conventions the pipeline enforces
# (config.py / agents.shared.file_utils.pair_input_images): images live
# in inputs/input_images/, the note for ``foo.png`` is ``foo_note.txt``.
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
NOTE_SUFFIX = "_note.txt"
MAX_IMAGE_BYTES = 25 * 1024 * 1024  # 25 MB per uploaded image


# --------------------------------------------------------------------------
# Auth — only enforced when INVITE_CODE is set (local-dev convenience)
# --------------------------------------------------------------------------

def _configured_invite_code() -> str:
    return os.environ.get(INVITE_CODE_ENV, "").strip()


def _auth_required() -> bool:
    return bool(_configured_invite_code())


def _check_invite_code(submitted: str) -> bool:
    configured = _configured_invite_code()
    if not configured:
        return False
    return hmac.compare_digest(submitted.encode("utf-8"),
                               configured.encode("utf-8"))


# --------------------------------------------------------------------------
# Database admin view — separate password gate for destructive actions
# --------------------------------------------------------------------------
# Drives the "Database" side-menu view.  The password is read from
# the PASSWORD_DATABASE_WEB_UI environment variable on every check;
# when unset, the view is hard-disabled (every auth attempt is
# rejected) so a forgotten env var can never leave the destructive
# endpoint exposed.

DB_PASSWORD_ENV            = "PASSWORD_DATABASE_WEB_UI"
RESET_PHRASE               = "reset_database"
CLEAR_PREV_SESSIONS_PHRASE = "clear_previous_sessions"
# Order is intentional only for the SELECT COUNT(*) snapshot; the
# TRUNCATE ... CASCADE doesn't care about order.  dc_parameter_schemas
# is deliberately ABSENT — it holds the 17-parameter schema seed and
# must be preserved.
RESET_TABLES = [
    "chunks",
    "dc_attempt_parameters",
    "dc_attempts",
    "rag_queries",
    "sessions",
]


def _configured_db_password() -> str:
    return os.environ.get(DB_PASSWORD_ENV, "").strip()


def _check_db_password(submitted: str) -> bool:
    configured = _configured_db_password()
    if not configured or not submitted:
        return False
    return hmac.compare_digest(submitted.encode("utf-8"),
                               configured.encode("utf-8"))


# --------------------------------------------------------------------------
# In-process single session (mirrors streamlit_app._ensure_session)
# --------------------------------------------------------------------------

@dataclass
class _Box:
    session: Session | None = None
    log_path: Path | None = None
    authed: bool = False


_BOX = _Box()


# Module-level singleton guard for the End Session lifecycle.  The DH
# save inside ``/api/end`` can take 5–15 minutes; in the 2026-05-30
# deployment the Railway/Cloudflare edge severed the HTTP connection
# at ~5 min and the browser / proxy retried, spawning a SECOND
# ``populate_database`` thread that raced the first one's archive
# sweep (see extra_utilities/TODO_known_issues.md F22 + the project's
# auto-memory ``v9_duplicate_save_bug``).
#
# ``api_end`` now returns HTTP 202 immediately and runs the actual
# save in a background task, so the proxy can't time-out-and-retry
# in the first place — but a plain bool flag still guards against
# concurrent ``/api/end`` POSTs that arrive before the background
# task finishes.  A bool is the right primitive here (not an
# ``asyncio.Lock``): the lock acquisition would have to span the
# HTTP handler → background task boundary, and asyncio.Lock's
# task-owns-the-lock contract makes that awkward.  A bool is atomic
# in a single-worker async event loop (W13/O9 — no preemption
# between sync statements), set in the HTTP handler BEFORE the
# background task is scheduled and cleared by the background task
# in its ``finally``.
_END_IN_FLIGHT: bool = False


# Module-level singleton guard for the chat-turn lifecycle.  Same
# rationale as ``_END_IN_FLIGHT`` above (W13/O9 single-user): the
# first complex turn — image inputs flowing through all 8 chain
# agents — can take well over 5 minutes, hitting the Railway/
# Cloudflare edge timeout in the same way the 2026-05-30 DH save
# did.  In that state the proxy serves a plain-text ``upstream
# error`` body and the browser's ``res.json()`` crashes with
# ``SyntaxError: Unexpected token 'u', "upstream error" is not
# valid JSON`` even though the backend is still happily finishing
# the turn.  ``/api/turn`` therefore returns HTTP 202 + a
# ``turn_id`` immediately and publishes the final reply as a
# ``turn_done`` event on /api/events.  This bool guards against a
# second /api/turn POST arriving while the background task is
# still running.
_TURN_IN_FLIGHT: bool = False


# Reference to the currently-in-flight ``_run_turn_in_background``
# asyncio Task.  Set by ``api_turn`` immediately after scheduling
# the background task; cleared by the task's ``finally`` (success,
# exception, or cancellation).  ``api_stop`` consults this to call
# ``.cancel()`` on the task so the UI's pending bubble unblocks
# IMMEDIATELY rather than waiting for the chain agents' L1 stop
# polls to bubble up through the orchestrator.  The orphan thread
# inside ``run_in_threadpool`` keeps running until its next L1
# poll catches the stop signal (typically <10 s) but its return
# value is discarded since nothing is awaiting it.  See W36 for
# the no-regression rules.
_current_turn_task: asyncio.Task | None = None


def _new_session_id() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"web_{ts}_{uuid.uuid4().hex[:8]}"


def _setup_session_logger(session_id: str) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    # The session_id minted by ``_new_session_id`` already starts with
    # ``web_`` (e.g. ``web_20260531_104043_06f39a67``), so the file
    # name is just ``<session_id>.log``.  Earlier the path prepended
    # ``web_`` a second time, producing ugly ``web_web_...log``
    # filenames that propagated into the R2 mirror.
    log_path = LOGS_DIR / f"{session_id}.log"
    for h in logger.handlers:
        if (isinstance(h, logging.FileHandler)
                and Path(h.baseFilename).resolve() == log_path.resolve()):
            return log_path
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
    logger.setLevel(logging.DEBUG)
    logger.addHandler(fh)

    # Emit the session-config banner FIRST so every saved log starts
    # with the full settings + LLM routing + DBa snapshot.  Sensitive
    # values are filtered server-side by session_banner._is_sensitive_name.
    from workflow_settings.session_banner import write_to_logger as _write_banner
    _write_banner(logger)
    return log_path


def _detach_log_handler(log_path: Path | None) -> None:
    if not log_path:
        return
    target = Path(log_path).resolve()
    for h in list(logger.handlers):
        if (isinstance(h, logging.FileHandler)
                and Path(h.baseFilename).resolve() == target):
            try:
                h.flush()
                h.close()
            except Exception:
                pass
            logger.removeHandler(h)


def _build_session() -> Session:
    # Reload settings.py so any edits saved via /api/settings or
    # /api/llm-routing since this process started take effect on the
    # next session build (the README explicitly promises this).
    # The on-disk file is rewritten by the editor's atomic
    # tempfile-rename path; this re-import picks up the new values
    # without a uvicorn restart.
    importlib.reload(workflow_settings)
    set_mesh_checks(workflow_settings.MESH_CHECKS)
    set_render_library(workflow_settings.RENDER_LIBRARY)

    session_id = _new_session_id()
    log_path = _setup_session_logger(session_id)
    try:
        init_trace(LOGS_DIR)
    except Exception:
        # Trace file is best-effort (same stance as streamlit_app).
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
    _BOX.session = session
    _BOX.log_path = log_path
    logger.info(f"[WEB] new session id={session_id}")
    return session


def _ensure_session() -> Session:
    if _BOX.session is None:
        return _build_session()
    return _BOX.session


def _run_dh_save() -> dict:
    """Run the Database Handler against the active session.

    Returns ``{"written": <int>, "session_dir": <str>}`` on success,
    or ``{"error": <str>}`` when the DH could not be invoked.  Called
    only when the user explicitly confirms "save to database" at End
    Session; matches the v4 REPL loader's post-session save path
    (W1 — dump histories before DH, since the DH mutates each agent's
    live messages).
    """
    from agents.loader import (
        _dump_agent_histories,
        _resolve_session_name,
        _resolve_session_timestamp,
    )
    from agents.orchestrator import Orchestrator
    from config import DATABASE_DIR

    session = _BOX.session
    if session is None:
        return {"error": "No active session to save."}

    # Resolve session name + timestamp ONCE per session lifecycle and
    # cache them on the Session.  Any subsequent caller (the archive
    # sweep in ``_end_session``, a race-induced second ``/api/end``)
    # reads the same value instead of computing a fresh
    # ``datetime.now()``-based slug.  Belt-and-suspenders against the
    # duplicate-save race; the backend lock in ``api_end`` is the
    # primary defence.
    try:
        if session.resolved_session_name is None:
            session.resolved_session_name = _resolve_session_name()
        session_name = session.resolved_session_name
    except Exception as exc:
        logger.exception("[WEB] DH save: resolving session name failed")
        return {"error": f"Could not resolve session name: {exc}"}

    try:
        if session.resolved_session_timestamp is None:
            session.resolved_session_timestamp = _resolve_session_timestamp()
        session_timestamp = session.resolved_session_timestamp
    except Exception as exc:
        logger.exception("[WEB] DH save: resolving session timestamp failed")
        return {"error": f"Could not resolve session timestamp: {exc}"}

    try:
        orchestrator = Orchestrator(session=session)
    except Exception as exc:
        logger.exception("[WEB] DH save: orchestrator build failed")
        return {"error": f"Could not build orchestrator: {exc}"}

    # W1 — dump histories BEFORE the DH so the per-agent history files
    # reflect the actual session (the DH's interview phase mutates each
    # agent's live messages).
    try:
        _dump_agent_histories(orchestrator, logger)
    except Exception as exc:
        logger.warning(f"[WEB] DH save: history dump failed: {exc}")

    try:
        session_db_dir = DATABASE_DIR / session_name
        logger.info(f"[WEB] DH save: populating {session_db_dir.resolve()}")
        written = orchestrator.database_handler.populate_database(
            session_db_dir,
            session_timestamp=session_timestamp,
            orchestrator=orchestrator,
        )
        logger.info(f"[WEB] DH save: wrote {written} entries")
        return {"written": int(written), "session_dir": str(session_db_dir)}
    except Exception as exc:
        logger.exception("[WEB] DH save: populate_database failed")
        return {"error": f"{type(exc).__name__}: {exc}"}


def _end_session(was_saved: bool = False) -> None:
    # Close the trace + detach the per-session log handler FIRST so
    # those files are unlocked (Windows holds open files), THEN sweep
    # everything session-specific (attempts/, logs, trace, inputs)
    # into previous_sessions/<id>/ — the SAME end-of-session archival
    # the v4 REPL loader runs, so attempts stop piling up shared
    # across web sessions.
    #
    # ``was_saved`` is threaded through to ``_archive_previous_session``
    # so the R2 mirror block there can honour
    # ``workflow_settings.SAVE_LOGS_FOR_UNSAVED_SESSIONS`` (settings
    # block #23).  Default ``False`` — a caller that does not know
    # the save state is treated as "not saved" (safer default; the
    # R2 upload then runs only when the setting allows it).
    logger.info("[WEB] end_session — archiving session, clearing state")
    try:
        close_trace()
    except Exception:
        pass
    _detach_log_handler(_BOX.log_path)
    # Re-use whatever name the DH save (if any) already resolved and
    # cached on the Session — so the archive folder under
    # ``previous_sessions/`` is named the SAME slug the DH wrote to
    # under ``database/`` and pushed to R2.  Falls back to a fresh
    # ``_resolve_session_name()`` (inside ``_archive_previous_session``)
    # when no save ran.
    cached_name: str | None = None
    if _BOX.session is not None:
        cached_name = _BOX.session.resolved_session_name
    try:
        _archive_previous_session(
            session_name=cached_name, was_saved=was_saved,
        )
    except Exception as exc:
        # Best-effort: a failed archive must not break the End Session
        # reset (worst case the old attempts remain for next session).
        logger.exception("[WEB] session archival failed: %s", exc)
    _BOX.session = None
    _BOX.log_path = None


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------

app = FastAPI(title="Propeller Design Configurator — JS web UI (local)")


@app.on_event("startup")
def _startup() -> None:
    # Same global side-effects the v4 loader / streamlit_app apply at
    # start so the render & mesh tools see the right configuration.
    set_mesh_checks(workflow_settings.MESH_CHECKS)
    set_render_library(workflow_settings.RENDER_LIBRARY)
    logger.info("[WEB] startup; auth_required=%s", _auth_required())


class TurnIn(BaseModel):
    message: str
    # Optional dict of FIXED parameter values from the Parameters Inputs
    # view (Step 8 of the redesign — see
    # extra_utilities/web_interface_notes.md §6.D).  Values are
    # pre-formatted display strings with units (e.g. "72 mm",
    # "5 % of chord") computed by the frontend so the backend has no
    # unit table to maintain.  Frontend sends this only when the FIXED
    # list has CHANGED since the last send (§6.D.B1); on unchanged
    # turns it sends None so save_user_input writes no FIXED block.
    fixed_params: dict[str, str] | None = None
    # Optional list of parameter names the user has just RELEASED back
    # to VARY since the previous send (Step 8 follow-up after
    # 2026-06-01 test feedback).  When present, save_user_input
    # appends a second block AFTER the FIXED block telling the LLM
    # the listed parameters are no longer user-constrained.
    released_params: list[str] | None = None


class AuthIn(BaseModel):
    code: str


class SettingsIn(BaseModel):
    values: dict[str, object]


class LlmRoutingIn(BaseModel):
    mode: str
    shared: dict[str, object]
    agents: list[dict[str, object]]


class ImageNoteIn(BaseModel):
    name: str
    description: str


class ImageNameIn(BaseModel):
    name: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/config")
def api_config() -> dict:
    return {
        "auth_required": _auth_required(),
        "authed": _BOX.authed or not _auth_required(),
        "session_active": _BOX.session is not None,
    }


@app.post("/api/auth")
def api_auth(body: AuthIn) -> dict:
    if not _auth_required():
        _BOX.authed = True
        return {"ok": True}
    if _check_invite_code(body.code):
        _BOX.authed = True
        logger.info("[WEB] invite-code accepted")
        return {"ok": True}
    logger.warning("[WEB] invite-code rejected")
    raise HTTPException(status_code=401, detail="Invite code did not match.")


def _require_auth() -> None:
    if _auth_required() and not _BOX.authed:
        raise HTTPException(status_code=401, detail="Not authenticated.")


def _require_no_session() -> None:
    """Reject settings writes while a session is active (HTTP 409).

    Pairs with the frontend's locked-view UX: every settings write
    surface (the flag list + the LLM routing chart) is disabled in the
    browser while ``session_active`` is true; this is the backend
    safety net.
    """
    if _BOX.session is not None:
        raise HTTPException(
            status_code=409,
            detail="Settings are locked while a session is active. "
                   "End the session to edit them.",
        )


def _artefact_url(p: Path) -> str:
    return f"/api/artefact?path={quote(str(p))}"


async def _run_turn_in_background(
    turn_id:         str,
    text:            str,
    fixed_params:    dict | None,
    released_params: list[str] | None,
) -> None:
    """Background task: run the multi-agent pipeline for a chat turn,
    then publish exactly one ``turn_done`` viz_bus event with the
    reply + artefacts.

    Clears ``_TURN_IN_FLIGHT`` in ``finally`` so the next /api/turn
    POST is accepted.  Always publishes EXACTLY ONE ``turn_done``
    event (success OR exception) so the frontend's chat bubble is
    never stuck in a pending state.
    """
    global _TURN_IN_FLIGHT, _current_turn_task
    reply:      str  = ""
    forwarded:  bool = False
    artefacts:  list = []
    error_str:  str | None = None
    cancelled:  bool = False
    try:
        session = _ensure_session()
        result = await run_in_threadpool(
            functools.partial(
                dispatch_turn,
                session=session,
                user_input=text,
                inputs_dir=USER_INPUTS_DIR,
                fixed_params=fixed_params,
                released_params=released_params,
            )
        )
        reply     = result.reply_text
        forwarded = result.forwarded
        for p in result.new_artefacts_paths:
            sfx = p.suffix.lower()
            kind = "image" if sfx == ".png" else ("mesh" if sfx == ".obj"
                                                  else "file")
            # Annotate the artefact with the attempt number when the
            # path sits inside a canonical ``YYYYMMDD_HHMMSS_NNN_<slug>``
            # attempt folder.  The frontend uses ``attempt_label`` to
            # caption image bubbles and to badge the 3D viewer.  Returns
            # None for artefacts outside an attempt folder (e.g. an
            # input image) — addBubble silently skips the label then.
            label = attempt_label_for_path(p)
            entry: dict = {
                "name": p.name,
                "kind": kind,
                "url":  _artefact_url(p),
            }
            if label is not None:
                entry["attempt_label"] = label
            artefacts.append(entry)
    except asyncio.CancelledError:
        # L2 — ``api_stop`` called ``.cancel()`` on this task.  The
        # threadpool thread running ``dispatch_turn`` keeps running
        # until its next L1 poll catches the stop signal; its return
        # value is discarded (no one is awaiting it).  We publish a
        # ``turn_done`` immediately so the UI's pending bubble
        # unblocks within ~1 s instead of waiting for the orphan
        # thread to bail.
        cancelled = True
        reply = (
            "(Session interrupted by Stop button — UI freed "
            "immediately; the background pipeline is halting at "
            "its next checkpoint.)"
        )
        forwarded = False
        artefacts = []
        error_str = None  # user-initiated, not a backend error
    except Exception as exc:
        logger.exception("[WEB] background turn task raised: %s", exc)
        reply = (
            f"(internal error during this turn — "
            f"{type(exc).__name__}: {exc}. Check the session log "
            f"for the full traceback.)"
        )
        forwarded = False
        artefacts = []
        error_str = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            viz_publish({
                "type":      "turn_done",
                "turn_id":   turn_id,
                "ok":        error_str is None,
                "reply":     reply,
                "forwarded": forwarded,
                "artefacts": artefacts,
                "error":     error_str,
            })
        except Exception:
            logger.exception("[WEB] failed to publish turn_done")
        _TURN_IN_FLIGHT = False
        _current_turn_task = None
        if cancelled:
            # Re-raise so the asyncio Task is marked CANCELLED
            # (cosmetic — nothing awaits this Task, but a Task that
            # swallows CancelledError logs a warning at gc time).
            raise asyncio.CancelledError()


@app.post("/api/turn", status_code=202)
async def api_turn(body: TurnIn) -> dict:
    """Schedule a chat turn and return HTTP 202 immediately.

    The real work (the full multi-agent pipeline inside
    ``dispatch_turn``) runs in a background asyncio task; the reply
    + artefacts are published as a single ``turn_done`` event on
    the already-open ``/api/events`` SSE stream, keyed by
    ``turn_id``.

    Mirrors the ``/api/end`` 202+SSE design (see the comment above
    ``_END_IN_FLIGHT``) and fixes the Railway/Cloudflare edge
    timeout that produced the 2026-06-04 ``"upstream error"`` chat
    bubble for the first image-heavy turn.
    """
    global _TURN_IN_FLIGHT, _current_turn_task
    _require_auth()
    text = (body.message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty message.")
    # Check-and-set is atomic: no ``await`` between the read and
    # the write, so no other coroutine can race on the
    # single-worker uvicorn event loop (W13/O9).
    if _TURN_IN_FLIGHT:
        raise HTTPException(
            status_code=409,
            detail=(
                "A previous turn is still in flight.  This request "
                "was ignored; the in-flight turn will complete on "
                "its own and emit a turn_done event on /api/events."
            ),
        )
    _TURN_IN_FLIGHT = True
    # Clear any stop flag left over from the previous turn — a
    # fresh /api/turn call always starts un-cancelled.
    stop_signal_clear()
    turn_id = uuid.uuid4().hex[:12]
    _current_turn_task = asyncio.create_task(
        _run_turn_in_background(
            turn_id,
            text,
            body.fixed_params,
            body.released_params,
        )
    )
    return {"ok": True, "status": "started", "turn_id": turn_id}


_PARAMETERS_MD = (
    Path(__file__).parent
    / "DC_prompt_fragments"
    / "dc_config"
    / "parameters.md"
)


@app.get("/api/parameters")
def api_parameters() -> dict:
    """Return parameters for the Copy parameters list button.

    When a mesh is currently shown in the chat-view 3D viewer (i.e.
    ``visualize_3d_model`` has been called by the Receptionist this
    process), serve the matching attempt's ``parameters.json`` so
    the user gets the ACTUAL design values they are looking at.

    When no mesh has been visualised yet (cold start, or after End
    Session resets the cache), fall back to the canonical
    17-parameter REFERENCE list at
    ``DC_prompt_fragments/dc_config/parameters.md``.

    The "currently-visualised attempt" is tracked server-side via the
    viz_bus cache that ``visualize_3d_model`` writes every time it
    accepts an obj_path.  Cleared on End Session in
    ``_run_end_in_background``.
    """
    _require_auth()
    folder = viz_get_last_attempt_dir()
    if folder is not None:
        params_path = folder / "parameters.json"
        try:
            text = params_path.read_text(encoding="utf-8")
            return {"text": text, "attempt": str(folder)}
        except OSError:
            # Fall through to the canonical list when parameters.json
            # is missing for any reason (folder pruned, write error,
            # etc.).
            pass
    try:
        text = _PARAMETERS_MD.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Cannot read parameters.md: {exc}",
        )
    return {"text": text}


# ---------------------------------------------------------------------------
# /api/preview_mesh  (Step 6 of the Parameters Inputs redesign)
# ---------------------------------------------------------------------------

# Range + type spec for each of the 17 canonical parameters.  Used by
# /api/preview_mesh to validate the request body BEFORE the RhinoCompute
# round-trip.  Mirrors DC_prompt_fragments/dc_config/parameters.md;
# hardcoded rather than parsed from the .md so this validator is robust
# against future formatting edits in that file.
#
# Keep in sync with PROPELLER_DC_PARAMETERS_V1 in
# extra_utilities/db_design/populate_dc_parameter_schemas.py — both
# represent the same v1 parameter set, just for different consumers.
_PREVIEW_PARAM_SPEC: dict[str, dict] = {
    # General / ring
    "bladeCount":        {"type": "int",   "min": 3,    "max": 6},
    "impellerRadius":    {"type": "float", "min": 60,   "max": 80},
    "impellerHeight":    {"type": "float", "min": 4,    "max": 10},
    "impellerThickness": {"type": "float", "min": 1,    "max": 5},
    # Inner blade section
    "innerThickness":    {"type": "float", "min": 3,    "max": 24},
    "innerMaxPos":       {"type": "int",   "min": 2,    "max": 8},
    "innerCamber":       {"type": "float", "min": 0,    "max": 9},
    "innerChord":        {"type": "float", "min": 3,    "max": 11},
    "innerAngle":        {"type": "float", "min": 2,    "max": 25},
    # Middle blade section
    "middlePos":         {"type": "float", "min": 0.3,  "max": 0.7},
    "middleChord":       {"type": "float", "min": 10,   "max": 30},
    "middleAngle":       {"type": "float", "min": 2,    "max": 25},
    # Outer blade section
    "outerThickness":    {"type": "float", "min": 3,    "max": 24},
    "outerMaxPos":       {"type": "int",   "min": 2,    "max": 8},
    "outerCamber":       {"type": "float", "min": 0,    "max": 9},
    "outerChord":        {"type": "float", "min": 10,   "max": 30},
    "outerAngle":        {"type": "float", "min": 2,    "max": 25},
}


class PreviewMeshIn(BaseModel):
    """POST body for /api/preview_mesh.

    Wrapped in a ``params`` dict so future fields (e.g. an explicit
    GH-definition selector, or a "skip cache" flag) can be added
    without breaking the body shape.
    """
    params: dict[str, float]


@app.post("/api/preview_mesh")
def api_preview_mesh(body: PreviewMeshIn) -> Response:
    """Generate a propeller mesh from a 17-parameter dict and return
    it as OBJ bytes.  Used by the Parameters Inputs view's live-
    preview pipeline (Step 7 of the redesign).

    This route does NOT go through the agent pipeline — it calls
    :func:`tools.generate_mesh.generate_mesh.render_mesh_obj_text`
    directly, bypassing attempts/ folders, agent-activity
    heartbeats, and tool-caller routing.  Slider tweaks in the
    Parameters Inputs view do NOT create attempt rows or trigger
    Receptionist / UII / DCIC / DCII / DCOI.

    The underlying helper is memoised via ``lru_cache(maxsize=64)``
    (keyed on a sorted params tuple + the GH file's mtime_ns), so
    repeated identical requests — e.g. the user dragging a slider
    back and forth — are served from cache without re-running
    RhinoCompute.

    Auth: same ``_require_auth()`` gate as ``/api/turn``.

    Body shape::
        {"params": {"bladeCount": 4, "impellerRadius": 71, …}}

    Responses:
      - **200 OK** — Content-Type ``model/obj``, body is the OBJ
        text (UTF-8).  Custom header ``X-Vertex-Count`` carries the
        decoded vertex count (diagnostic).
      - **400 Bad Request** — params dict missing keys, has unknown
        keys, out-of-range values, or non-integer values for
        integer-typed params (bladeCount / innerMaxPos / outerMaxPos).
        Detail message names the failing param(s).
      - **502 Bad Gateway** — RhinoCompute failed or returned no
        usable mesh.  Detail message includes the upstream error.
    """
    _require_auth()

    raw_params = body.params

    # ----- Validate keys --------------------------------------------
    expected_keys = set(_PREVIEW_PARAM_SPEC.keys())
    received_keys = set(raw_params.keys())
    missing = expected_keys - received_keys
    extra = received_keys - expected_keys
    if missing or extra:
        problems: list[str] = []
        if missing:
            problems.append(f"missing: {sorted(missing)}")
        if extra:
            problems.append(f"unknown: {sorted(extra)}")
        raise HTTPException(
            status_code=400,
            detail="Invalid params dict — " + "; ".join(problems),
        )

    # ----- Validate ranges + coerce integer-typed params ------------
    coerced: dict[str, int | float] = {}
    problems = []
    for name, spec in _PREVIEW_PARAM_SPEC.items():
        v = raw_params[name]
        if not (spec["min"] <= v <= spec["max"]):
            problems.append(
                f"{name}={v} (allowed: [{spec['min']}, {spec['max']}])"
            )
            continue
        if spec["type"] == "int":
            # JSON delivers 4 or 4.0 indistinguishably; render_mesh_obj_text
            # uses ``isinstance(v, int)`` to choose System.Int32 vs Double
            # for RhinoCompute, so coerce explicitly.  Reject non-integer
            # floats (e.g. bladeCount=3.5) — those are silent-rounding
            # foot-guns.
            if v != int(v):
                problems.append(f"{name}={v} (must be an integer)")
                continue
            coerced[name] = int(v)
        else:
            coerced[name] = float(v)
    if problems:
        raise HTTPException(
            status_code=400,
            detail="Out of range: " + ", ".join(problems),
        )

    # ----- Delegate to the pure helper (Step 5) ---------------------
    try:
        obj_text, vertex_count, _components = render_mesh_obj_text(coerced)
    except MeshGenerationError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Mesh generation failed: {exc}",
        )

    # ----- Return OBJ bytes ----------------------------------------
    # The frontend (Step 7) fetches this with OBJLoader.load(blobUrl);
    # the Content-Type is mostly informational (Three.js parses the
    # body regardless).  X-Vertex-Count exposed for diagnostics —
    # the frontend can log it but doesn't need it for rendering.
    return Response(
        content=obj_text,
        media_type="model/obj",
        headers={"X-Vertex-Count": str(vertex_count)},
    )


@app.get("/api/artefact")
def api_artefact(path: str) -> FileResponse:
    _require_auth()
    root = ATTEMPTS_DIR.resolve()
    target = Path(path).resolve()
    if root != target and root not in target.parents:
        raise HTTPException(status_code=403, detail="Path outside attempts dir.")
    if target.suffix.lower() not in {".png", ".obj"}:
        raise HTTPException(status_code=403, detail="Unsupported artefact type.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Artefact not found.")
    return FileResponse(target)


class FeedbackIn(BaseModel):
    # The three fields the End Session modal collects when the user
    # confirms "save".  Only ``satisfaction`` is required by the
    # frontend (a y/p/n toggle); the two free-text fields may be
    # empty strings — the Orchestrator handles "no elaboration"
    # gracefully (most agents end up with send=false).
    satisfaction:    str = ""
    what_went_well:  str = ""
    what_went_wrong: str = ""


class EndIn(BaseModel):
    # Optional — when ``True`` the Database Handler interviews each
    # agent (via the same path the v4 REPL loader uses) BEFORE the
    # session is archived.  Default is ``False`` so old clients posting
    # an empty body keep the v8 behaviour (archive only).
    save: bool = False
    # Optional — when present AND save=True, an Orchestrator-led
    # feedback distribution round runs BEFORE the DH save so the DH's
    # per-agent interview sees the user's feedback in each target
    # agent's history.  See agents/orchestrator/feedback_tool.py and
    # the Orchestrator's Role-4 prompt section.
    feedback: FeedbackIn | None = None


def _run_feedback_round_sync(feedback: "FeedbackIn") -> dict:
    """Run the Orchestrator's end-of-session feedback distribution.

    Mirrors the build-from-session pattern in :func:`_run_dh_save`
    (so the DH save can run immediately afterwards on the same
    in-memory Session — message appends to the live agents persist
    via ``snapshot_state()`` into ``session.agent_states``).

    Best-effort: any error is logged and surfaces in the returned
    dict; it never breaks the End Session pipeline (the user's
    saved data is the core promise, the feedback round is an
    enhancement).
    """
    from agents.orchestrator import Orchestrator

    session = _BOX.session
    if session is None:
        return {"ok": False, "error": "No active session for feedback."}

    try:
        orchestrator = Orchestrator(session=session)
    except Exception as exc:
        logger.exception("[WEB] feedback round: orchestrator build failed")
        return {"ok": False, "error": f"orch build: {exc}"}

    try:
        return orchestrator.run_feedback_round(
            satisfaction    = (feedback.satisfaction    or "").strip(),
            what_went_well  = (feedback.what_went_well  or "").strip(),
            what_went_wrong = (feedback.what_went_wrong or "").strip(),
        )
    except Exception as exc:
        logger.exception("[WEB] feedback round raised")
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _run_save_session_feedback_sync(feedback: "FeedbackIn") -> dict:
    """Phase 3C: persist the End Session feedback to Postgres.

    Direct call to ``db_writer.save_session_feedback`` — no LLM in
    the loop (Q-3C-6 = A).  Maps the modal payload to the
    ``FIXED_FEEDBACK_QUESTIONS`` ids and translates the satisfaction
    enum to the SMALLINT 0..10 scale per the
    ``database_PostgreSQL_schema_v5.sql`` ``sessions.satisfaction``
    column comment (10=yes, 5=partially, 0=no, NULL=no feedback).

    Best-effort: when Postgres is disabled OR an error occurs, log
    and return — the rest of ``/api/end`` (archive sweep, SSE
    event) proceeds.  The R2 mirror still carries the per-Q+A files
    written by ``populate_database`` earlier.

    MUST be called AFTER ``_run_dh_save`` so the sessions row
    exists (``save_session_feedback`` UPDATEs an existing row and
    raises if absent — see N18 guard in db_writer).
    """
    session = _BOX.session
    if session is None:
        return {"ok": False, "error": "session cleared before feedback persist"}

    try:
        from agents.shared import postgres_pool as _pp
    except Exception as exc:
        return {"ok": False, "error": f"postgres_pool import: {exc}"}

    if not _pp.is_enabled():
        logger.info(
            "[WEB] Phase 3C save_session_feedback SKIPPED "
            "(postgres_pool.is_enabled() == False)"
        )
        return {"ok": True, "skipped": True, "reason": "postgres disabled"}

    try:
        from agents.database_handler import db_writer as _dbw
    except Exception as exc:
        return {"ok": False, "error": f"db_writer import: {exc}"}

    # Map modal satisfaction enum → SMALLINT 0..10
    sat_str = (feedback.satisfaction or "").strip().lower()
    if sat_str == "yes":
        sat_int: int | None = 10
    elif sat_str in ("partially", "partial"):
        sat_int = 5
    elif sat_str == "no":
        sat_int = 0
    else:
        sat_int = None

    # Map modal field names → FIXED_FEEDBACK_QUESTIONS ids.  Empty
    # strings become None (treated as unanswered by
    # save_session_feedback → is_empty=TRUE safety-net row).
    pos = (feedback.what_went_well  or "").strip() or None
    neg = (feedback.what_went_wrong or "").strip() or None

    session_id = session.resolved_session_name or session.session_id

    try:
        outcomes = _dbw.save_session_feedback(
            session_id=session_id,
            dc_name=session.dc_name,
            satisfaction=sat_int,
            answers={
                "fixed_positive": pos,
                "fixed_negative": neg,
            },
        )
        outcomes_str = ", ".join(
            f"{k}={v.value}" for k, v in outcomes.items()
        )
        logger.info(
            f"[WEB] Phase 3C save_session_feedback OK "
            f"session_id={session_id} satisfaction={sat_int} "
            f"outcomes={{{outcomes_str}}}"
        )
        return {
            "ok": True,
            "session_id": session_id,
            "satisfaction": sat_int,
            "outcomes": {k: v.value for k, v in outcomes.items()},
        }
    except Exception as exc:
        logger.error(
            f"[WEB] Phase 3C save_session_feedback FAILED "
            f"session_id={session_id}: "
            f"{type(exc).__name__}: {exc}.  Sessions row "
            "satisfaction/feedback NOT updated; chunks mirror "
            "rows NOT inserted.  Session is otherwise saved."
        )
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


async def _run_end_in_background(
    save_requested: bool,
    session_present: bool,
    feedback: "FeedbackIn | None" = None,
) -> None:
    """Background task: run the feedback round (if any) + DH save (if
    requested) + archive sweep, then publish a ``session_save_done``
    viz_bus event.

    Clears ``_END_IN_FLIGHT`` in ``finally`` so the next ``/api/end``
    POST is accepted (the previous session is gone by the time this
    finishes, so a follow-up "no active session to save" path is
    coherent).

    Always publishes EXACTLY ONE ``session_save_done`` event, even
    on exception, so the frontend's End Session UI is never stuck
    in a "waiting" state.

    ORDERING INVARIANT: the feedback round MUST run before
    ``_run_dh_save`` so the per-agent ``HumanMessage(name="orchestrator")``
    entries it appends are visible to the DH when it interviews each
    agent.  ``_run_dh_save`` reads ``session.agent_states[<key>].messages``;
    ``run_feedback_round`` mirrors its appends there via
    ``snapshot_state()``.
    """
    global _END_IN_FLIGHT
    dh_result: dict | None = None
    feedback_result: dict | None = None
    error_str: str | None = None
    try:
        if save_requested and session_present:
            if feedback is not None:
                logger.info(
                    "[WEB] end_session — running Orchestrator feedback "
                    "round (background task) BEFORE DH save"
                )
                feedback_result = await run_in_threadpool(
                    _run_feedback_round_sync, feedback
                )
            logger.info(
                "[WEB] end_session — save=True, running DH (background task)"
            )
            dh_result = await run_in_threadpool(_run_dh_save)
            # Phase 3C — persist End Session feedback to Postgres
            # AFTER the DH save has created the sessions row via
            # upsert_session.  Skipped when no feedback was
            # supplied (legacy clients, or "Save without feedback").
            # Best-effort: errors logged inside the helper; no
            # change to the session_save_done SSE payload (Q-3C-G3 = A).
            if feedback is not None:
                await run_in_threadpool(
                    _run_save_session_feedback_sync, feedback
                )
        elif save_requested:
            # User requested save but no session is active — treat as
            # a plain End Session.  Surface the fact in the SSE event
            # so the UI can confirm.
            dh_result = {"error": "No active session to save."}
        _end_session(was_saved=save_requested)
    except Exception as exc:
        logger.exception(
            "[WEB] background end-session task failed: %s", exc
        )
        error_str = f"{type(exc).__name__}: {exc}"
    finally:
        # Publish exactly ONE completion event, success OR error.
        try:
            viz_publish({
                "type":     "session_save_done",
                "ok":       error_str is None,
                "saved":    bool(save_requested),
                "dh":       dh_result,
                "feedback": feedback_result,
                "error":    error_str,
            })
        except Exception:
            logger.exception("[WEB] failed to publish session_save_done")
        # Clear the "currently-visualised attempt" cache so the next
        # session's Copy parameters list button falls back to the
        # canonical reference list until a new mesh is visualised.
        try:
            viz_set_last_attempt_dir(None)
        except Exception:
            logger.exception("[WEB] failed to clear viz_bus attempt cache")
        _END_IN_FLIGHT = False


@app.post("/api/end", status_code=202)
async def api_end(body: EndIn | None = None) -> dict:
    """End the active session, optionally running the Database Handler
    first.

    **Returns HTTP 202 Accepted immediately**, then runs the actual
    work in a background asyncio task.  This eliminates the
    Railway/Cloudflare edge-timeout that caused the 2026-05-30
    duplicate-save bug (5–15 min DH save → proxy timeout at ~5 min →
    browser retry → second ``populate_database`` thread).  See
    extra_utilities/TODO_known_issues.md F22 and the project's
    auto-memory ``v9_duplicate_save_bug``.

    **Completion event.**  The background task publishes a single
    ``session_save_done`` event on the viz_bus when it finishes
    (success or error).  The frontend's already-open ``/api/events``
    EventSource forwards it; ``web/app.js`` runs the post-save UI
    cleanup (clear chat / viewer / images / log view) on receipt.
    Until then the End Session button stays disabled and the UI
    holds its "Saving…" state.

    **Singleton.**  A concurrent ``/api/end`` POST while another save
    is already in flight is rejected with HTTP 409 — guarded by the
    ``_END_IN_FLIGHT`` flag.  The flag is set synchronously in this
    handler BEFORE the background task is scheduled and cleared by
    the background task in its ``finally``, so the check-and-set is
    atomic in the single-worker uvicorn event loop (W13/O9).
    """
    global _END_IN_FLIGHT
    # Check-and-set is atomic: no ``await`` between the read and the
    # write, so no other coroutine can race on the same event loop.
    if _END_IN_FLIGHT:
        logger.info(
            "[WEB] /api/end rejected — save already in progress; "
            "returning HTTP 409 (duplicate-save guard)."
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "A previous End Session is still saving.  This "
                "request was ignored to avoid spawning a duplicate "
                "save; the in-flight save will complete on its own "
                "and emit a session_save_done event on /api/events."
            ),
        )
    _END_IN_FLIGHT = True

    save_requested  = bool(body and body.save)
    session_present = _BOX.session is not None
    # End-of-session feedback distribution runs ONLY when the user
    # chose to save AND supplied feedback in the modal.  Absent/null
    # feedback (legacy clients, or "Save without feedback" path) →
    # the feedback round is skipped, DH save runs as before.
    feedback        = body.feedback if (body and save_requested) else None

    # Schedule the actual work on the running event loop and return.
    # The task runs INDEPENDENTLY of this HTTP request's lifecycle,
    # so a proxy / browser disconnect cannot interrupt the DH save.
    asyncio.create_task(
        _run_end_in_background(save_requested, session_present, feedback)
    )

    return {
        "ok":     True,
        "status": "started",
        "saved":  save_requested,
    }


@app.post("/api/save_log")
async def api_save_log() -> dict:
    """Snapshot the current session log to R2 without ending the session.

    Writes the live ``_BOX.log_path`` file to
    ``<resolved_session_name>/logs/snapshot_<UTC-YYYYMMDDTHHMMSSZ>.log``
    on R2.  Does NOT touch the SQL database, the in-flight session
    state, the DH save flow, or any other R2 namespace.  Safe to call
    repeatedly mid-session — each call creates a new timestamped key
    so concurrent / repeated snapshots never collide with each other
    or with the end-of-session ``session.log`` archive that
    ``_archive_previous_session`` writes.

    Returns ``{ok: bool, key?, session?, error?}``.
    """
    _require_auth()

    # Need both a session AND a log file path to snapshot.
    if _BOX.session is None or _BOX.log_path is None:
        return {"ok": False, "error": "No active session to snapshot."}

    log_path = _BOX.log_path
    if not log_path.exists():
        return {
            "ok":    False,
            "error": f"Log file not found at {log_path}.",
        }

    # R2 must be configured for this to do anything useful.
    from agents.shared import r2_uploader as _r2
    if not _r2.is_enabled():
        return {
            "ok": False,
            "error": (
                "R2 is not configured on this deploy "
                "(R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / "
                "R2_BUCKET_NAME missing)."
            ),
        }

    # Force-resolve the canonical session_name so the snapshot lands in
    # the same R2 namespace the end-of-session archive will use.  The
    # caching contract (Session.resolved_session_name set once, reused
    # by every subsequent caller) matches what _run_dh_save already
    # does for the regular save flow.
    if _BOX.session.resolved_session_name is None:
        try:
            from agents.loader import _resolve_session_name
            _BOX.session.resolved_session_name = _resolve_session_name()
        except Exception as exc:
            logger.exception("[WEB] /api/save_log could not resolve session name")
            return {
                "ok":    False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    session_name = _BOX.session.resolved_session_name
    if not session_name:
        return {
            "ok":    False,
            "error": "No canonical session name available after resolve.",
        }

    # UTC ISO-style timestamp with Zulu suffix.  Lexicographically
    # sortable, matches Session.session_ts (also UTC), and avoids
    # local-time ambiguity when reading the bucket months later.
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    remote_key = f"{session_name}/logs/snapshot_{ts}.log"

    try:
        ok = _r2.upload_file(log_path, remote_key)
    except Exception as exc:
        logger.exception("[WEB] /api/save_log upload failed")
        return {
            "ok":    False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    if not ok:
        return {
            "ok":    False,
            "error": (
                "R2 upload returned False (see server log for the "
                "underlying error)."
            ),
        }

    # Best-effort: log the snapshot key INTO the same log that was just
    # shipped, so a subsequent snapshot from the same session captures
    # this trail too.
    logger.info(f"[WEB] /api/save_log uploaded snapshot -> {remote_key}")
    return {
        "ok":      True,
        "key":     remote_key,
        "session": session_name,
    }


@app.post("/api/stop")
def api_stop() -> dict:
    """User clicked the Stop button — flag the in-flight pipeline
    for cooperative cancellation AND cancel its asyncio task.

    Two-layer stop (see W36 / the L1+L2 lesson):

    L1 (the cooperative side).  ``stop_signal_request()`` sets the
    shared bool that every chain agent's run loop polls — once at
    the top of the outer ``for _ in range(MAX_<X>_STEPS)`` loop
    and once at the top of the inner ``for tc in
    response.tool_calls`` loop.  This actually stops the work:
    the next agent step raises ``StopRequestedError``, which
    propagates to ``dispatch_turn`` and turns into the
    "(Session interrupted...)" reply.  Typical latency 3-10 s,
    worst case 30 s if mid-vision-LLM-call.

    L2 (the UI-responsiveness side).  We also cancel the asyncio
    Task running ``_run_turn_in_background``.  The
    ``await run_in_threadpool(dispatch_turn)`` raises
    CancelledError; the task's ``except`` publishes a ``turn_done``
    SSE event immediately, the frontend renders it and unblocks
    the composer within ~1 s.  The threadpool thread keeps
    running but its return value is discarded — it bails on its
    next L1 poll and exits naturally.

    Idempotent: clicking Stop again while already stopping is a
    no-op (cancel on an already-cancelled task is harmless;
    setting the flag twice is a no-op).
    """
    _require_auth()
    stop_signal_request()
    task = _current_turn_task
    if task is not None and not task.done():
        task.cancel()
        logger.info(
            "[WEB] /api/stop — stop requested AND in-flight turn "
            "task cancelled (UI will unblock on the turn_done SSE "
            "event the cancel handler publishes)"
        )
    else:
        logger.info(
            "[WEB] /api/stop — stop requested by user (no "
            "in-flight turn task to cancel)"
        )
    return {"ok": True}


@app.get("/api/settings")
def api_settings_get() -> dict:
    """Current workflow_settings/settings.py values + metadata for the
    Workflow Settings editor.  Thin delegate — no agent/pipeline logic
    here (W17); the parsing lives in workflow_settings.editor."""
    _require_auth()
    return {"settings": settings_editor.read_schema()}


@app.post("/api/settings")
def api_settings_post(body: SettingsIn) -> dict:
    """Validate + rewrite the touched assignment lines in settings.py.
    Edits take effect for the NEXT session (settings are read at
    session build); the rate-limit constants need a server restart.

    Rejected with HTTP 409 while a session is active.
    """
    _require_auth()
    _require_no_session()
    try:
        settings_editor.write_updates(dict(body.values))
    except settings_editor.SettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # never 500 the editor
        logger.exception("[WEB] settings write failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=f"Could not write settings ({type(exc).__name__}: {exc}).",
        )
    logger.info("[WEB] settings updated: %s", sorted(body.values))
    return {"ok": True, "settings": settings_editor.read_schema()}


@app.get("/api/llm-routing")
def api_llm_routing_get() -> dict:
    """Current LLM routing state (mode + per-provider key presence +
    shared default + per-agent overrides).  Thin delegate — parsing
    lives in workflow_settings.llm_routing."""
    _require_auth()
    return settings_llm_routing.read_state()


@app.post("/api/llm-routing")
def api_llm_routing_post(body: LlmRoutingIn) -> dict:
    """Validate + write the LLM routing payload.  Updates
    workflow_settings/settings.py:LLM_ROUTING_MODE plus the shared
    agents/.env and per-agent agents/<agent>/.env files.  Edits take
    effect for the NEXT session (settings + .env are re-read on
    session build).

    Rejected with HTTP 409 while a session is active.
    """
    _require_auth()
    _require_no_session()
    try:
        settings_llm_routing.write_updates(body.model_dump())
    except settings_llm_routing.RoutingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # never 500 the editor
        logger.exception("[WEB] llm-routing write failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=f"Could not write LLM routing "
                   f"({type(exc).__name__}: {exc}).",
        )
    logger.info("[WEB] llm-routing updated: mode=%s", body.mode)
    return {"ok": True, "state": settings_llm_routing.read_state()}


# --------------------------------------------------------------------------
# Per-agent DBa (database access) toggle — backs the LLM-routing chart's
# DBa buttons.  Two endpoints:
#
#   GET /api/database-access
#     Returns {flags: {agent: bool, ...}, rag_enabled: bool}.  The
#     frontend uses ``rag_enabled`` to show / hide the "master switch
#     is OFF" banner, and ``flags`` to render each agent's button
#     pressed-state.
#
#   POST /api/database-access  body: {agent, enabled}
#     Updates ONE agent's flag via
#     ``workflow_settings.database_access.set_one(...)``.  Rejected
#     with HTTP 409 while a session is active (same lock as the
#     other settings writes).  Returns {ok, flags, rag_enabled}.
#
# Both endpoints take effect on the NEXT session — the per-agent
# prompt templates and tool bindings are built once at session
# construction time and read the JSON file then.

from workflow_settings import database_access as _db_access


class _DbAccessBody(BaseModel):
    agent:   str
    enabled: bool


@app.get("/api/database-access")
def api_database_access_get() -> dict:
    """Current per-agent DBa state + the global RAG_ENABLED master
    switch.  Read-only."""
    _require_auth()
    # Re-read RAG_ENABLED off disk so the editor can't cache a
    # stale value from process startup — same idiom as
    # ``workflow_settings.llm_routing`` uses for LLM_ROUTING_MODE.
    importlib.reload(workflow_settings)
    return {
        "flags":       _db_access.get_all(),
        "rag_enabled": bool(workflow_settings.RAG_ENABLED),
    }


@app.post("/api/database-access")
def api_database_access_post(body: _DbAccessBody) -> dict:
    """Update one agent's DBa flag in
    ``workflow_settings/database_access.json``.  Edits take effect
    for the NEXT session.

    Rejected with HTTP 409 while a session is active.
    """
    _require_auth()
    _require_no_session()
    try:
        flags_after = _db_access.set_one(body.agent, body.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # never 500 the editor
        logger.exception("[WEB] database-access write failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=f"Could not write database-access "
                   f"({type(exc).__name__}: {exc}).",
        )
    logger.info(
        "[WEB] database-access updated: %s -> %s",
        body.agent, body.enabled,
    )
    importlib.reload(workflow_settings)
    return {
        "ok":          True,
        "flags":       flags_after,
        "rag_enabled": bool(workflow_settings.RAG_ENABLED),
    }


class DhScheduleIn(BaseModel):
    # The editor sends the FULL replacement schedule on every Save.
    version: int = 1
    questions: list[dict[str, object]]


@app.get("/api/fixed-feedback-questions")
def api_fixed_feedback_questions_get() -> dict:
    """Read-only — the two fixed feedback questions asked to the
    user at End Session.  Source of truth is the
    ``FIXED_FEEDBACK_QUESTIONS`` constant in
    ``workflow_settings/fixed_feedback_questions.py`` (see
    architecture doc §3.3 + §3.7, warnings_developer.md W24).

    Rendered as a read-only table at the bottom of the
    "Questions for Saved Sessions" web view, beneath the
    user-editable DH schedule.
    """
    _require_auth()
    from workflow_settings.fixed_feedback_questions import (
        FIXED_FEEDBACK_QUESTIONS,
    )
    return {"questions": [dict(q) for q in FIXED_FEEDBACK_QUESTIONS]}


@app.get("/api/dh-schedule")
def api_dh_schedule_get() -> dict:
    """Current DH question schedule + agent / scope / type metadata
    for the 'Questions for Saved Sessions' editor.  Seeded from the
    hardcoded SCHEDULE on first call (file is created lazily)."""
    _require_auth()
    return settings_dh_schedule.read_state()


@app.post("/api/dh-schedule")
def api_dh_schedule_post(body: DhScheduleIn) -> dict:
    """Validate + write the DH question schedule.  Edits take effect
    for the NEXT End Session → save (the DH reads the file at save
    time).

    Rejected with HTTP 409 while a session is active.
    """
    _require_auth()
    _require_no_session()
    try:
        settings_dh_schedule.write_updates(body.model_dump())
    except settings_dh_schedule.ScheduleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # never 500 the editor
        logger.exception("[WEB] dh-schedule write failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=f"Could not write DH schedule "
                   f"({type(exc).__name__}: {exc}).",
        )
    logger.info(
        "[WEB] dh-schedule updated: %d questions",
        len(body.questions),
    )
    return {"ok": True, "state": settings_dh_schedule.read_state()}


@app.get("/api/dh-schedule/download")
def api_dh_schedule_download() -> Response:
    """Stream the current schedule JSON as a downloadable attachment."""
    _require_auth()
    payload = settings_dh_schedule.download_payload()
    return Response(
        content=payload,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                'attachment; filename="dh_schedule.json"'
            ),
        },
    )


@app.post("/api/dh-schedule/upload")
async def api_dh_schedule_upload(file: UploadFile = File(...)) -> dict:
    """Accept an uploaded JSON, parse + validate, and return the
    canonical payload for the UI to load into its in-memory table.

    Does NOT write to disk — the user must click Save to persist.
    Rejected with HTTP 409 while a session is active.
    """
    _require_auth()
    _require_no_session()
    try:
        raw = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not read uploaded file: {exc}",
        )
    try:
        payload = settings_dh_schedule.parse_uploaded(raw)
    except settings_dh_schedule.ScheduleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    logger.info(
        "[WEB] dh-schedule upload parsed: %d questions",
        len(payload.get("questions") or []),
    )
    return {"ok": True, "payload": payload}


# --------------------------------------------------------------------------
# Database admin view — password-gated reset endpoint
# --------------------------------------------------------------------------
# Backs the side-menu "Database" view.  Two endpoints:
#
#   POST /api/db_admin/auth    body: {password}
#       Validates the password ONLY (so the UI can unlock its form
#       with immediate feedback before the operator types the
#       destructive phrase).  Always returns HTTP 200 with
#       {ok: bool, error?: str}.
#
#   POST /api/db_admin/reset   body: {password, phrase}
#       Re-validates the password AND the phrase, then TRUNCATEs
#       the 5 data tables (chunks, dc_attempt_parameters,
#       dc_attempts, rag_queries, sessions) in one transaction.
#       dc_parameter_schemas is preserved (intentionally not in
#       RESET_TABLES) and the session_counter SEQUENCE is left
#       alone.  Returns row counts that were deleted on success.


class _DbAuthBody(BaseModel):
    password: str


class _DbResetBody(BaseModel):
    password: str
    phrase:   str


@app.post("/api/db_admin/auth")
async def api_db_admin_auth(body: _DbAuthBody) -> dict:
    """Validate the Database-view password.  Used by the frontend to
    unlock the reset form before the operator types the destructive
    phrase.  Always returns 200; ``ok`` discriminates."""
    if not _configured_db_password():
        return {
            "ok": False,
            "error": f"{DB_PASSWORD_ENV} is not set in the environment.",
        }
    return {"ok": _check_db_password(body.password)}


@app.post("/api/db_admin/reset")
async def api_db_admin_reset(body: _DbResetBody) -> dict:
    """Destructive: TRUNCATE the 5 data tables (preserves
    ``dc_parameter_schemas`` and the ``session_counter`` SEQUENCE).

    Re-validates the password AND the literal reset phrase
    server-side so the endpoint cannot be invoked by anyone who
    skipped the UI's unlock step.
    """
    if not _check_db_password(body.password):
        return {"ok": False, "error": "Password rejected."}
    if body.phrase != RESET_PHRASE:
        return {
            "ok": False,
            "error": f"Phrase must be exactly {RESET_PHRASE!r}.",
        }

    # Local import — only loaded when the destructive endpoint
    # actually fires, so a Railway deploy without DATABASE_URL set
    # never tries to open the pool just to serve other views.
    from agents.shared import postgres_pool

    if not postgres_pool.is_enabled():
        return {
            "ok": False,
            "error": ("Postgres pool is not enabled "
                      "(DATABASE_URL / DATABASE_PUBLIC_URL not set)."),
        }

    before: dict[str, int] = {}
    try:
        with postgres_pool.connection() as conn:
            with conn.cursor() as cur:
                for tbl in RESET_TABLES:
                    cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                    before[tbl] = int(cur.fetchone()[0])
                cur.execute(
                    "TRUNCATE TABLE "
                    + ", ".join(RESET_TABLES)
                    + " RESTART IDENTITY CASCADE"
                )
                conn.commit()
    except Exception as exc:
        logger.exception("[db_admin] reset failed")
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    logger.warning(
        "[db_admin] DATABASE RESET via /api/db_admin/reset — "
        "deleted rows: %s",
        before,
    )
    return {
        "ok":            True,
        "before_counts": before,
        "tables_wiped":  RESET_TABLES,
    }


# --------------------------------------------------------------------------
# Database admin — clear PREVIOUS_SESSIONS_DIR (Railway-mounted volume)
# --------------------------------------------------------------------------
# Mirrors the reset endpoint pattern (same password + literal phrase
# confirmation).  Designed for one-shot wipes before detaching the
# Railway-mounted volume; the DH save itself does NOT read from
# previous_sessions/ (see warnings_developer.md W1 + W30 — the archive
# sweep happens AFTER the DH save, and R2 mirror runs against the moved
# files), so wiping is safe between sessions even with the volume
# attached.

class _DbClearPrevSessionsBody(BaseModel):
    password: str
    phrase:   str


@app.post("/api/db_admin/clear_previous_sessions")
async def api_db_admin_clear_previous_sessions(
    body: _DbClearPrevSessionsBody,
) -> dict:
    """Destructive: remove every entry under PREVIOUS_SESSIONS_DIR and
    leave the folder itself intact so the volume mount target survives.

    Same password+phrase gate as :func:`api_db_admin_reset`.  Returns
    ``entries_removed`` + ``bytes_freed`` for verification.
    """
    if not _check_db_password(body.password):
        return {"ok": False, "error": "Password rejected."}
    if body.phrase != CLEAR_PREV_SESSIONS_PHRASE:
        return {
            "ok": False,
            "error": f"Phrase must be exactly {CLEAR_PREV_SESSIONS_PHRASE!r}.",
        }

    import shutil
    from config import PREVIOUS_SESSIONS_DIR

    if not PREVIOUS_SESSIONS_DIR.exists():
        return {
            "ok":              True,
            "entries_removed": 0,
            "bytes_freed":     0,
            "note":            "Directory did not exist; nothing to do.",
        }

    # Snapshot count + total bytes BEFORE deletion so the response
    # tells the operator exactly how much was freed.
    entries     = list(PREVIOUS_SESSIONS_DIR.iterdir())
    n_entries   = len(entries)
    total_bytes = 0
    for entry in entries:
        if entry.is_file():
            try:
                total_bytes += entry.stat().st_size
            except OSError:
                pass
        elif entry.is_dir():
            for f in entry.rglob("*"):
                if f.is_file():
                    try:
                        total_bytes += f.stat().st_size
                    except OSError:
                        pass

    try:
        for entry in entries:
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
    except Exception as exc:
        logger.exception("[db_admin] clear_previous_sessions failed")
        return {
            "ok":    False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    logger.warning(
        "[db_admin] PREVIOUS_SESSIONS_DIR WIPED via "
        "/api/db_admin/clear_previous_sessions — removed %d entries, "
        "%d bytes",
        n_entries, total_bytes,
    )
    return {
        "ok":              True,
        "entries_removed": n_entries,
        "bytes_freed":     total_bytes,
    }


# --------------------------------------------------------------------------
# Database admin — session ignore list (database_search +
# retrieve_user_inputs + retrieve_attempt all skip listed sessions).
# Persistent storage in workflow_settings/db_search_ignore_list.json;
# read fresh by the tools on every call so a UI write takes effect
# immediately, no session restart needed.  Strict server-side
# validation of each session_id against the canonical regex
# ``^ID\d+_\d{8}_\d{6}$`` (W31 happy-path shape).
# --------------------------------------------------------------------------


class _DbIgnoreReadBody(BaseModel):
    password: str


class _DbIgnoreWriteBody(BaseModel):
    password: str
    sessions: list[str]


@app.post("/api/db_admin/ignore_list/read")
def api_db_admin_ignore_read(body: _DbIgnoreReadBody) -> dict:
    """Return the current session ignore list.  Password-gated via
    the same DB-admin password as the reset endpoint."""
    if not _check_db_password(body.password):
        return {"ok": False, "error": "Password rejected."}
    from workflow_settings import db_search_ignore_list as _il
    return {"ok": True, "sessions": _il.get_ignore_list()}


@app.post("/api/db_admin/ignore_list/write")
def api_db_admin_ignore_write(body: _DbIgnoreWriteBody) -> dict:
    """Replace the session ignore list.  Validates each session_id
    against ``^ID\\d+_\\d{8}_\\d{6}$``; rejects the whole payload
    when any element is malformed (no partial writes)."""
    if not _check_db_password(body.password):
        return {"ok": False, "error": "Password rejected."}
    from workflow_settings import db_search_ignore_list as _il
    cleaned = [(s or "").strip() for s in body.sessions]
    invalid = [s for s in cleaned if s and not _il.SESSION_ID_PATTERN.match(s)]
    if invalid:
        return {
            "ok": False,
            "error": (
                f"{len(invalid)} session_id(s) do not match the "
                f"expected shape ^ID\\d+_\\d{{8}}_\\d{{6}}$: "
                f"{invalid!r}"
            ),
        }
    stored = _il.set_ignore_list(cleaned)
    logger.info(
        "[db_admin] ignore list updated: %d session(s)", len(stored)
    )
    return {"ok": True, "sessions": stored}


# --------------------------------------------------------------------------
# Image Inputs — manage inputs/input_images/ from the browser
# --------------------------------------------------------------------------

def _images_dir() -> Path:
    INPUT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return INPUT_IMAGES_DIR


def _sanitize_stem(stem: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", stem).strip("._-")
    return cleaned or "image"


def _note_path_for(image: Path) -> Path:
    return image.parent / f"{image.stem}{NOTE_SUFFIX}"


def _safe_image_path(name: str) -> Path:
    """Resolve *name* to a file directly inside INPUT_IMAGES_DIR.

    Rejects path traversal, nested paths and disallowed suffixes — the
    same defensive stance as the /api/artefact guard.
    """
    raw = (name or "").strip()
    if not raw or raw != Path(raw).name:
        raise HTTPException(status_code=400, detail="Invalid image name.")
    suffix = Path(raw).suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="Unsupported image type.")
    root = _images_dir().resolve()
    target = (root / raw).resolve()
    if target.parent != root:
        raise HTTPException(status_code=403, detail="Path outside images dir.")
    return target


def _unique_target(stem: str, suffix: str) -> Path:
    """A free ``<stem><suffix>`` in the images dir.

    Auto-suffixes ``-1``, ``-2`` … on a same-suffix collision.  Rejects
    a same-stem-different-format collision (the pipeline allows only one
    image format per name).
    """
    root = _images_dir()
    existing = {
        p.stem.lower(): p
        for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in ALLOWED_IMAGE_SUFFIXES
    }
    candidate = stem
    n = 0
    while True:
        clash = existing.get(candidate.lower())
        if clash is None:
            return root / f"{candidate}{suffix}"
        if clash.suffix.lower() != suffix:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"An image named '{clash.name}' already exists; the "
                    f"pipeline allows only one format per name. Rename or "
                    f"delete it first."
                ),
            )
        n += 1
        candidate = f"{stem}-{n}"


def _image_listing() -> list[dict]:
    pairing = pair_input_images(INPUT_IMAGES_DIR)
    out: list[dict] = []
    for img, note in pairing["pairs"]:
        try:
            empty = not note.read_text(encoding="utf-8").strip()
        except OSError:
            empty = True
        out.append({
            "name": img.name,
            "url": f"/api/images/file?name={quote(img.name)}",
            "has_note": True,
            "note_empty": empty,
        })
    for img in pairing["orphan_images"]:
        out.append({
            "name": img.name,
            "url": f"/api/images/file?name={quote(img.name)}",
            "has_note": False,
            "note_empty": True,
        })
    out.sort(key=lambda e: e["name"].lower())
    return out


@app.get("/api/images")
def api_images_list() -> dict:
    _require_auth()
    return {"images": _image_listing()}


@app.post("/api/images")
async def api_images_upload(files: list[UploadFile] = File(...)) -> dict:
    _require_auth()
    saved: list[str] = []
    errors: list[str] = []
    for f in files:
        suffix = Path(f.filename or "").suffix.lower()
        if suffix not in ALLOWED_IMAGE_SUFFIXES:
            errors.append(f"{f.filename}: unsupported type "
                          f"(allowed: .png .jpg .jpeg)")
            continue
        data = await f.read()
        if len(data) > MAX_IMAGE_BYTES:
            errors.append(f"{f.filename}: exceeds "
                          f"{MAX_IMAGE_BYTES // (1024 * 1024)} MB limit")
            continue
        stem = _sanitize_stem(Path(f.filename or "image").stem)
        try:
            target = _unique_target(stem, suffix)
        except HTTPException as exc:
            errors.append(f"{f.filename}: {exc.detail}")
            continue
        target.write_bytes(data)
        # Auto-create an empty paired note so pair_input_images stays
        # valid (an undescribed image would otherwise be an orphan and
        # the Receptionist would refuse to forward the request).
        note = _note_path_for(target)
        if not note.exists():
            note.write_text("", encoding="utf-8")
        saved.append(target.name)
    if saved:
        logger.info("[WEB] images uploaded: %s", saved)
    return {"ok": not errors, "saved": saved, "errors": errors,
            "images": _image_listing()}


@app.get("/api/images/file")
def api_images_file(name: str) -> FileResponse:
    _require_auth()
    target = _safe_image_path(name)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(target)


@app.get("/api/images/note")
def api_images_note_get(name: str) -> dict:
    _require_auth()
    image = _safe_image_path(name)
    note = _note_path_for(image)
    text = ""
    if note.is_file():
        try:
            text = note.read_text(encoding="utf-8")
        except OSError as exc:
            raise HTTPException(status_code=400,
                                detail=f"Could not read note: {exc}")
    return {"name": image.name, "description": text}


@app.post("/api/images/note")
def api_images_note_save(body: ImageNoteIn) -> dict:
    _require_auth()
    image = _safe_image_path(body.name)
    if not image.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    _note_path_for(image).write_text(body.description, encoding="utf-8")
    logger.info("[WEB] note saved for %s", image.name)
    return {"ok": True}


@app.post("/api/images/note/reset")
def api_images_note_reset(body: ImageNameIn) -> dict:
    _require_auth()
    image = _safe_image_path(body.name)
    # Keep the .txt alive (pairing requires it) but empty its content.
    _note_path_for(image).write_text("", encoding="utf-8")
    logger.info("[WEB] note reset for %s", image.name)
    return {"ok": True}


@app.delete("/api/images")
def api_images_delete(name: str) -> dict:
    _require_auth()
    image = _safe_image_path(name)
    note = _note_path_for(image)
    if image.exists():
        image.unlink()
    if note.exists():
        note.unlink()
    logger.info("[WEB] image deleted: %s", image.name)
    return {"ok": True, "images": _image_listing()}


@app.get("/api/events")
async def api_events() -> StreamingResponse:
    """Server-Sent Events stream. Pushes a "visualize" event the
    moment an agent tool (``visualize_3d_model``) publishes one, so
    the browser loads the model live — not only at end-of-turn."""
    q = viz_subscribe()

    async def gen():
        last_ping = time.monotonic()
        try:
            yield ": connected\n\n"
            while True:
                try:
                    evt = q.get_nowait()
                except queue.Empty:
                    evt = None
                if evt is None:
                    now = time.monotonic()
                    if now - last_ping > 10:
                        last_ping = now
                        yield ": ping\n\n"
                    await asyncio.sleep(0.4)
                    continue
                if evt.get("type") == "visualize":
                    p = Path(evt["path"])
                    payload = {
                        "type":          "visualize",
                        "url":           _artefact_url(p),
                        "name":          evt.get("name") or p.name,
                        "attempt_label": evt.get("attempt_label"),
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                elif evt.get("type") == "agent_active":
                    payload = {
                        "type": "agent_active",
                        "from": evt.get("from", ""),
                        "to": evt.get("to", ""),
                        "note": evt.get("note", ""),
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                elif evt.get("type") == "generic_tool":
                    payload = {
                        "type": "generic_tool",
                        "name": evt.get("name", ""),
                        "state": evt.get("state", ""),
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                elif evt.get("type") == "session_save_done":
                    # End Session completion signal — emitted by
                    # ``_run_end_in_background`` exactly once when
                    # the feedback round + DH save + archive sweep
                    # finish (success or failure).  The frontend
                    # uses this to run the post-save UI cleanup
                    # (clear chat / viewer / images / log view) and
                    # re-enable the End Session button.  The
                    # ``feedback`` field surfaces the
                    # Orchestrator's per-agent dispatch summary so
                    # the UI can display which agents received user
                    # feedback at end-of-session.
                    payload = {
                        "type":     "session_save_done",
                        "ok":       bool(evt.get("ok")),
                        "saved":    bool(evt.get("saved")),
                        "dh":       evt.get("dh"),
                        "feedback": evt.get("feedback"),
                        "error":    evt.get("error"),
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                elif evt.get("type") == "turn_done":
                    # /api/turn background-task completion signal —
                    # emitted by ``_run_turn_in_background`` exactly
                    # once per chat turn.  The frontend matches the
                    # ``turn_id`` against the pending bubble it
                    # captured at /api/turn 202 time, then renders
                    # the assistant reply, auto-loads any new mesh
                    # into the viewer, and runs the post-turn UI
                    # cleanup (clear busy / refocus input).
                    payload = {
                        "type":      "turn_done",
                        "turn_id":   evt.get("turn_id", ""),
                        "ok":        bool(evt.get("ok")),
                        "reply":     evt.get("reply", ""),
                        "forwarded": bool(evt.get("forwarded")),
                        "artefacts": evt.get("artefacts", []),
                        "error":     evt.get("error"),
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                elif evt.get("type") == "params_proposed":
                    # Step 9 of the Parameters Inputs redesign.
                    # Receptionist's propose_attempt tool publishes
                    # this when the system has decided a given attempt
                    # satisfies the user's requirements (per the rules
                    # in receptionist/prompt.md — Step 11).  The
                    # frontend SSE handler turns non-FIXED sliders
                    # ORANGE, moves them to the proposed value, and
                    # adds a "PROPOSED VALUE: X" text on every row
                    # (FIXED ones too, per locked §6.F.C2).
                    payload = {
                        "type":   "params_proposed",
                        "values": evt.get("values", {}),
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
        finally:
            viz_unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/log/stream")
async def api_log_stream() -> StreamingResponse:
    """SSE stream of the current session's log file.

    On connect: sends the file's current contents (capped at the
    last few MB for safety), then tails newly-appended bytes.  If
    the active session changes (End Session -> new session), the
    tail follows the new log file from byte 0.  Heartbeats every
    10 s keep proxies from closing the stream.
    """
    _require_auth()
    max_initial_bytes = 5 * 1024 * 1024  # cap initial dump at 5 MB

    async def gen():
        yield ": connected\n\n"
        tailed_path: Path | None = None
        offset: int = 0
        last_ping = time.monotonic()

        while True:
            current = _BOX.log_path
            try:
                if current is not None and current.exists():
                    # New / changed log file -> dump initial backlog.
                    if current != tailed_path:
                        tailed_path = current
                        size = current.stat().st_size
                        start = max(0, size - max_initial_bytes)
                        with open(current, "r", encoding="utf-8",
                                  errors="replace") as f:
                            f.seek(start)
                            initial = f.read()
                            offset = f.tell()
                        if initial:
                            yield (
                                "data: "
                                + json.dumps({"type": "log",
                                              "text": initial})
                                + "\n\n"
                            )
                    else:
                        size = current.stat().st_size
                        if size < offset:
                            # Truncated / rotated mid-session.
                            offset = 0
                        if size > offset:
                            with open(current, "r", encoding="utf-8",
                                      errors="replace") as f:
                                f.seek(offset)
                                new_text = f.read()
                                offset = f.tell()
                            if new_text:
                                yield (
                                    "data: "
                                    + json.dumps({"type": "log",
                                                  "text": new_text})
                                    + "\n\n"
                                )
            except OSError:
                # Transient FS error (file moved during archival, etc.) —
                # drop the tailed_path so the next iteration re-detects.
                tailed_path = None
                offset = 0

            now = time.monotonic()
            if now - last_ping > 10:
                last_ping = now
                yield ": ping\n\n"
            await asyncio.sleep(0.4)

    return StreamingResponse(gen(), media_type="text/event-stream")


# Mounted last so it does not shadow the explicit routes above.
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
