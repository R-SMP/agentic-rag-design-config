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
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents.dispatch import dispatch_turn
from agents.loader import _archive_previous_session
from agents.shared.file_utils import pair_input_images
from agents.shared.session import Session
from agents.shared.trace import close_trace, init_trace
from agents.shared.viz_bus import (
    subscribe as viz_subscribe,
    unsubscribe as viz_unsubscribe,
)
from config import ATTEMPTS_DIR, INPUT_IMAGES_DIR, LOGS_DIR, USER_INPUTS_DIR
from tools import set_mesh_checks, set_render_library
from workflow_settings import editor as settings_editor
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
# In-process single session (mirrors streamlit_app._ensure_session)
# --------------------------------------------------------------------------

@dataclass
class _Box:
    session: Session | None = None
    log_path: Path | None = None
    authed: bool = False


_BOX = _Box()


def _new_session_id() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"web_{ts}_{uuid.uuid4().hex[:8]}"


def _setup_session_logger(session_id: str) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"web_{session_id}.log"
    for h in logger.handlers:
        if (isinstance(h, logging.FileHandler)
                and Path(h.baseFilename).resolve() == log_path.resolve()):
            return log_path
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
    logger.setLevel(logging.DEBUG)
    logger.addHandler(fh)
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


def _end_session() -> None:
    # Close the trace + detach the per-session log handler FIRST so
    # those files are unlocked (Windows holds open files), THEN sweep
    # everything session-specific (attempts/, logs, trace, inputs)
    # into previous_sessions/<id>/ — the SAME end-of-session archival
    # the v4 REPL loader runs, so attempts stop piling up shared
    # across web sessions.
    logger.info("[WEB] end_session — archiving session, clearing state")
    try:
        close_trace()
    except Exception:
        pass
    _detach_log_handler(_BOX.log_path)
    try:
        _archive_previous_session()
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


class AuthIn(BaseModel):
    code: str


class SettingsIn(BaseModel):
    values: dict[str, object]


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


def _artefact_url(p: Path) -> str:
    return f"/api/artefact?path={quote(str(p))}"


@app.post("/api/turn")
async def api_turn(body: TurnIn) -> dict:
    _require_auth()
    text = (body.message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty message.")
    session = _ensure_session()
    try:
        # dispatch_turn is synchronous and slow (the whole multi-agent
        # LLM pipeline). Run it off the event loop so the server stays
        # responsive.
        result = await run_in_threadpool(
            functools.partial(
                dispatch_turn,
                session=session,
                user_input=text,
                inputs_dir=USER_INPUTS_DIR,
            )
        )
        artefacts = []
        for p in result.new_artefacts_paths:
            sfx = p.suffix.lower()
            kind = "image" if sfx == ".png" else ("mesh" if sfx == ".obj"
                                                  else "file")
            artefacts.append({"name": p.name, "kind": kind,
                               "url": _artefact_url(p)})
        return {
            "reply": result.reply_text,
            "forwarded": result.forwarded,
            "artefacts": artefacts,
        }
    except Exception as exc:  # surface as a chat bubble, never 500 the UI
        logger.exception("[WEB] dispatch_turn raised: %s", exc)
        return {
            "reply": (f"(internal error during this turn — "
                      f"{type(exc).__name__}: {exc}. Check the session log "
                      f"for the full traceback.)"),
            "forwarded": False,
            "artefacts": [],
        }


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


@app.post("/api/end")
def api_end() -> dict:
    _end_session()
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
    session build); the rate-limit constants need a server restart."""
    _require_auth()
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
                        "type": "visualize",
                        "url": _artefact_url(p),
                        "name": evt.get("name") or p.name,
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
        finally:
            viz_unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


# Mounted last so it does not shadow the explicit routes above.
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
