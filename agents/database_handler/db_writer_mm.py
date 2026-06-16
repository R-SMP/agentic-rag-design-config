"""Multimodal mirror writer for the `chunks_mm` table (architecture doc §6.3).

ONE routine — :func:`mirror_session_to_mm` — produces, for a single
session, the full `chunks_mm` payload and writes it.  It is reused by:

  * the BACKFILL (web-UI button) — looped over every session, and
  * the LIVE dual-write — called best-effort after a session's normal
    save completes.

What it writes for one session
------------------------------
1. TEXT rows — read every row of the original `chunks` table for the
   session.  Semantic rows that carry a stitched `embedding_input` are
   re-embedded with voyage-multimodal-3.5 (text path); Quantitative /
   is_empty rows are copied verbatim (no vector).  Feedback rows ride
   along automatically (they are ordinary Semantic chunks).
2. IMAGE rows — fetched from R2 and fused image+text (see F37):
     * user images  -> agent_from='User',        field='User Image Input',
                       fused with the image's <name>_note.txt
     * renders      -> agent_from='tool_caller',  field='Attempt Visual Render',
                       fused with the attempt's description.txt;
                       ONE row per render_*.png view found in the folder.
   When the associated text is missing, falls back to image-only.

Metadata is REUSED: session_id / attempt_id FK straight to the existing
`sessions` / `dc_attempts` tables.

Idempotency / resume
--------------------
Per-session delete-then-insert.  A session that already has `chunks_mm`
rows is SKIPPED unless (a) ``force=True`` or (b) the embedding model on
its existing rows differs from the currently-configured model
(``current_model_string``).  This makes a long backfill safe to
restart and makes a model change trigger an automatic re-embed.

Embedding parameters are LOCKED in code — see warnings_developer.md W38
and ``agents/shared/voyage_mm.py``.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional

from agents.shared import postgres_pool, r2_uploader, voyage_mm
from agents.database_handler.db_writer import DEFAULT_AGENTS_TO_ACL

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Row-shape constants for image rows (architecture doc §6.3 / W38)
# --------------------------------------------------------------------------
FIELD_USER_IMAGE = "User Image Input"
FIELD_RENDER = "Attempt Visual Render"
AGENT_USER_IMAGE = "User"
AGENT_RENDER = "tool_caller"

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")
_RENDER_RE = re.compile(r"render_.*\.png$", re.IGNORECASE)
# attempts/<NNN>__<global_id>/  — global_id IS dc_attempts.attempt_id
_ATTEMPT_FOLDER_RE = re.compile(r"^(\d+)__(\d+)$")

LogFn = Callable[[str], None]


# --------------------------------------------------------------------------
# SQL
# --------------------------------------------------------------------------
_SELECT_SOURCE_CHUNKS = """
SELECT attempt_id, agent_from, agents_to, field, field_type, question,
       body, item_index, embedding_model, embedding_input, is_error, is_empty
FROM chunks
WHERE session_id = %s
ORDER BY id
"""

_SELECT_EXISTING_MM = """
SELECT COUNT(*),
       array_agg(DISTINCT embedding_model)
           FILTER (WHERE embedding_model IS NOT NULL)
FROM chunks_mm
WHERE session_id = %s
"""

_DELETE_MM_FOR_SESSION = "DELETE FROM chunks_mm WHERE session_id = %s"

_SELECT_ALL_SESSIONS = "SELECT session_id FROM sessions ORDER BY session_ts"

_INSERT_MM = """
INSERT INTO chunks_mm
    (session_id, attempt_id, agent_from, agents_to, field, field_type,
     question, body, item_index, embedding, embedding_model,
     embedding_input, is_error, is_empty)
VALUES
    (%(session_id)s, %(attempt_id)s, %(agent_from)s, %(agents_to)s,
     %(field)s, %(field_type)s, %(question)s, %(body)s, %(item_index)s,
     %(embedding)s, %(embedding_model)s, %(embedding_input)s,
     %(is_error)s, %(is_empty)s)
ON CONFLICT (session_id, agent_from, field, attempt_id, item_index,
             embedding_model) DO NOTHING
"""


# --------------------------------------------------------------------------
# R2 read helpers (reuse the shared r2_uploader client + the retrieve_*
# tools' GET/LIST pattern; keys are session-rooted, env prefix added here)
# --------------------------------------------------------------------------
def _r2_client() -> tuple[Optional[str], Any]:
    if not r2_uploader.is_enabled():
        return None, None
    client = r2_uploader._client()  # noqa: SLF001 — shared single source
    if client is None:
        return None, None
    return r2_uploader._env("R2_BUCKET_NAME"), client  # noqa: SLF001


def _full_key(session_rooted_key: str) -> str:
    return f"{r2_uploader._key_prefix()}{session_rooted_key.lstrip('/')}"  # noqa: SLF001


def _r2_get_bytes(client, bucket: str, session_rooted_key: str) -> Optional[bytes]:
    try:
        resp = client.get_object(Bucket=bucket, Key=_full_key(session_rooted_key))
        return resp["Body"].read()
    except Exception as exc:  # noqa: BLE001
        logger.info("[db_writer_mm]  R2 GET miss %s: %s", session_rooted_key, exc)
        return None


def _r2_get_text(client, bucket: str, session_rooted_key: str) -> Optional[str]:
    data = _r2_get_bytes(client, bucket, session_rooted_key)
    if data is None:
        return None
    return data.decode("utf-8", errors="replace")


def _r2_list(client, bucket: str, session_rooted_prefix: str) -> list[str]:
    """List keys under a session-rooted prefix; return SESSION-ROOTED keys.

    (The optional env ``R2_KEY_PREFIX`` is added for the request and
    stripped from the results, so callers always work in session-rooted
    space, e.g. ``ID097_.../attempts/003__42/render_top.png``.)
    """
    env_prefix = r2_uploader._key_prefix()  # noqa: SLF001
    full_prefix = f"{env_prefix}{session_rooted_prefix.lstrip('/')}"
    out: list[str] = []
    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []) or []:
                key = obj.get("Key", "")
                if env_prefix and key.startswith(env_prefix):
                    key = key[len(env_prefix):]
                if key:
                    out.append(key)
    except Exception as exc:  # noqa: BLE001
        logger.info("[db_writer_mm]  R2 LIST failed %s: %s", session_rooted_prefix, exc)
    return out


# --------------------------------------------------------------------------
# Row builders (return INSERT-ready param dicts; embedding done here)
# --------------------------------------------------------------------------
def _acl_list() -> list[str]:
    return list(DEFAULT_AGENTS_TO_ACL)


def _build_text_rows(
    session_id: str, source_rows: list[tuple], model_str: str, log: LogFn,
) -> tuple[list[dict], int, int, int]:
    """Re-embed Semantic text rows; copy Quantitative/empty rows verbatim."""
    rows: list[dict] = []
    embedded = copied = errors = 0
    for (attempt_id, agent_from, agents_to, field, field_type, question,
         body, item_index, _src_model, embedding_input, is_error,
         is_empty) in source_rows:
        is_embeddable = (
            field_type == "Semantic"
            and not is_empty
            and embedding_input is not None
            and embedding_input.strip() != ""
        )
        if is_embeddable:
            try:
                vec = voyage_mm.embed_text(embedding_input)
            except Exception as exc:  # noqa: BLE001 — best-effort per row
                errors += 1
                log(f"    ! text embed FAILED ({field}): {type(exc).__name__}: {exc}")
                continue
            rows.append({
                "session_id": session_id, "attempt_id": attempt_id,
                "agent_from": agent_from, "agents_to": list(agents_to),
                "field": field, "field_type": field_type,
                "question": question, "body": body, "item_index": item_index,
                "embedding": vec, "embedding_model": model_str,
                "embedding_input": embedding_input,
                "is_error": is_error, "is_empty": is_empty,
            })
            embedded += 1
        else:
            # Quantitative or is_empty Semantic — copy verbatim, no vector.
            rows.append({
                "session_id": session_id, "attempt_id": attempt_id,
                "agent_from": agent_from, "agents_to": list(agents_to),
                "field": field, "field_type": field_type,
                "question": question, "body": body, "item_index": item_index,
                "embedding": None, "embedding_model": None,
                "embedding_input": embedding_input,
                "is_error": is_error, "is_empty": is_empty,
            })
            copied += 1
    log(f"    text rows: {embedded} re-embedded, {copied} copied, {errors} errors")
    return rows, embedded, copied, errors


def _build_user_image_rows(
    session_id: str, client, bucket: str, model_str: str, log: LogFn,
) -> tuple[list[dict], int, int]:
    """One fused (image + <name>_note.txt) row per user image; image-only fallback."""
    rows: list[dict] = []
    embedded = errors = 0
    listed = _r2_list(client, bucket, f"{session_id}/user_inputs/images/")
    basenames = [k.rsplit("/", 1)[-1] for k in listed]
    image_names = sorted(
        n for n in basenames if n.lower().endswith(_IMAGE_SUFFIXES)
    )
    note_set = {n for n in basenames if n.lower().endswith("_note.txt")}
    for idx, name in enumerate(image_names, start=1):
        key = f"{session_id}/user_inputs/images/{name}"
        img_bytes = _r2_get_bytes(client, bucket, key)
        if img_bytes is None:
            errors += 1
            log(f"    ! user image GET miss: {name}")
            continue
        stem = name
        for suf in _IMAGE_SUFFIXES:
            if name.lower().endswith(suf):
                stem = name[: -len(suf)]
                break
        note_name = f"{stem}_note.txt"
        note_text = None
        if note_name in note_set:
            note_text = _r2_get_text(
                client, bucket, f"{session_id}/user_inputs/images/{note_name}")
        try:
            if note_text and note_text.strip():
                vec = voyage_mm.embed_fused(note_text, img_bytes)
                emb_input = note_text
            else:
                vec = voyage_mm.embed_image(img_bytes)
                emb_input = None
        except Exception as exc:  # noqa: BLE001
            errors += 1
            log(f"    ! user image embed FAILED ({name}): {type(exc).__name__}: {exc}")
            continue
        rows.append({
            "session_id": session_id, "attempt_id": None,
            "agent_from": AGENT_USER_IMAGE, "agents_to": _acl_list(),
            "field": FIELD_USER_IMAGE, "field_type": "Semantic",
            "question": None, "body": f"user_inputs/images/{name}",
            "item_index": idx, "embedding": vec,
            "embedding_model": model_str, "embedding_input": emb_input,
            "is_error": False, "is_empty": False,
        })
        embedded += 1
    log(f"    user images: {embedded} embedded, {errors} errors")
    return rows, embedded, errors


def _build_render_rows(
    session_id: str, client, bucket: str, model_str: str, log: LogFn,
) -> tuple[list[dict], int, int]:
    """One fused (render + attempt description.txt) row per render_*.png view."""
    rows: list[dict] = []
    embedded = errors = 0
    listed = _r2_list(client, bucket, f"{session_id}/attempts/")
    # Group keys by attempt folder segment "<NNN>__<gid>".
    folders: dict[str, list[str]] = {}
    for key in listed:
        parts = key.split("/")
        # <session_id>/attempts/<NNN>__<gid>/<filename>
        if len(parts) >= 4 and parts[1] == "attempts":
            folders.setdefault(parts[2], []).append(parts[-1])
    for folder, filenames in sorted(folders.items()):
        m = _ATTEMPT_FOLDER_RE.match(folder)
        if not m:
            log(f"    ! skip unrecognised attempt folder: {folder}")
            continue
        nnn, gid = m.group(1), int(m.group(2))
        renders = sorted(f for f in filenames if _RENDER_RE.search(f))
        if not renders:
            continue
        desc = _r2_get_text(
            client, bucket, f"{session_id}/attempts/{folder}/description.txt")
        for idx, fname in enumerate(renders, start=1):
            img_bytes = _r2_get_bytes(
                client, bucket, f"{session_id}/attempts/{folder}/{fname}")
            if img_bytes is None:
                errors += 1
                log(f"    ! render GET miss: {folder}/{fname}")
                continue
            try:
                if desc and desc.strip():
                    vec = voyage_mm.embed_fused(desc, img_bytes)
                    emb_input = desc
                else:
                    vec = voyage_mm.embed_image(img_bytes)
                    emb_input = None
            except Exception as exc:  # noqa: BLE001
                errors += 1
                log(f"    ! render embed FAILED ({folder}/{fname}): "
                    f"{type(exc).__name__}: {exc}")
                continue
            rows.append({
                "session_id": session_id, "attempt_id": gid,
                "agent_from": AGENT_RENDER, "agents_to": _acl_list(),
                "field": FIELD_RENDER, "field_type": "Semantic",
                "question": None, "body": f"attempts/{folder}/{fname}",
                "item_index": idx, "embedding": vec,
                "embedding_model": model_str, "embedding_input": emb_input,
                "is_error": False, "is_empty": False,
            })
            embedded += 1
    log(f"    renders: {embedded} embedded, {errors} errors")
    return rows, embedded, errors


# --------------------------------------------------------------------------
# Public entrypoint
# --------------------------------------------------------------------------
def mirror_session_to_mm(
    session_id: str,
    *,
    force: bool = False,
    current_model_string: Optional[str] = None,
    log: Optional[LogFn] = None,
) -> dict:
    """Mirror one session's text + images into `chunks_mm`.

    Returns a summary dict.  Best-effort: per-row embed/GET failures are
    logged and counted, never raised.  Postgres/connection failures DO
    raise so the caller (backfill loop / live hook) can decide.
    """
    log = log or (lambda m: logger.info("[db_writer_mm] %s", m))
    model_str = current_model_string or voyage_mm.embedding_model_string()

    if not postgres_pool.is_enabled():
        log(f"  {session_id}: SKIP — postgres not enabled")
        return {"session_id": session_id, "status": "postgres_disabled"}

    # 1. Skip / resume decision.
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_EXISTING_MM, (session_id,))
            existing_count, existing_models = cur.fetchone()
    existing_models = list(existing_models or [])
    if existing_count and not force:
        # Skip only if every embedded row already uses the current model
        # (or there are no embedded rows at all).
        if not existing_models or set(existing_models) == {model_str}:
            log(f"  {session_id}: SKIP — {existing_count} rows already at "
                f"current model")
            return {"session_id": session_id, "status": "skipped",
                    "existing_rows": existing_count}
        log(f"  {session_id}: re-embedding — existing model(s) "
            f"{existing_models} != current {model_str!r}")

    # 2. Read source chunks.
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_SOURCE_CHUNKS, (session_id,))
            source_rows = cur.fetchall()
    log(f"  {session_id}: {len(source_rows)} source chunks")

    # 3. Build all rows (Voyage calls happen here — outside any DB txn).
    text_rows, t_emb, t_copy, t_err = _build_text_rows(
        session_id, source_rows, model_str, log)

    bucket, client = _r2_client()
    img_rows: list[dict] = []
    rnd_rows: list[dict] = []
    i_emb = i_err = r_emb = r_err = 0
    if client is None:
        log("    R2 not configured — skipping image + render rows")
    else:
        img_rows, i_emb, i_err = _build_user_image_rows(
            session_id, client, bucket, model_str, log)
        rnd_rows, r_emb, r_err = _build_render_rows(
            session_id, client, bucket, model_str, log)

    all_rows = text_rows + img_rows + rnd_rows

    # 4. One transaction (DELETE + all INSERTs commit together).  Each
    #    insert runs in its own SAVEPOINT (nested ``conn.transaction()``)
    #    so a single bad row — e.g. a render folder whose <gid> is not a
    #    real dc_attempts FK — is skipped without rolling back the DELETE
    #    or the other inserts.
    inserted = 0
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            with conn.transaction():  # outer transaction
                if existing_count:
                    cur.execute(_DELETE_MM_FOR_SESSION, (session_id,))
                for row in all_rows:
                    try:
                        with conn.transaction():  # per-row savepoint
                            cur.execute(_INSERT_MM, row)
                            inserted += cur.rowcount
                    except Exception as exc:  # noqa: BLE001 — e.g. FK orphan
                        log(f"    ! INSERT failed ({row['field']} "
                            f"item={row['item_index']}): "
                            f"{type(exc).__name__}: {exc}")

    summary = {
        "session_id": session_id, "status": "done",
        "text_embedded": t_emb, "text_copied": t_copy, "text_errors": t_err,
        "user_images_embedded": i_emb, "user_image_errors": i_err,
        "renders_embedded": r_emb, "render_errors": r_err,
        "rows_inserted": inserted, "model": model_str,
    }
    log(f"  {session_id}: DONE — {inserted} rows inserted "
        f"(text {t_emb}+{t_copy}, user-img {i_emb}, renders {r_emb}; "
        f"errors text {t_err}/img {i_err}/render {r_err})")
    return summary


def backfill_all_sessions(
    *,
    force: bool = False,
    current_model_string: Optional[str] = None,
    log: Optional[LogFn] = None,
) -> dict:
    """Mirror EVERY session in `sessions` into `chunks_mm`.

    Reused by both the one-time backfill (web-UI button) and any manual
    re-run.  Processes sessions oldest-first.  Per-session failures are
    caught and recorded so one bad session never aborts the whole run
    (each session is independently resumable).  Returns an aggregate
    summary plus the per-session result list.
    """
    log = log or (lambda m: logger.info("[db_writer_mm] %s", m))
    model_str = current_model_string or voyage_mm.embedding_model_string()

    if not postgres_pool.is_enabled():
        log("Backfill ABORTED — postgres not enabled")
        return {"status": "postgres_disabled", "sessions": 0}

    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_ALL_SESSIONS)
            session_ids = [r[0] for r in cur.fetchall()]

    n = len(session_ids)
    log(f"Backfill starting: {n} sessions, model={model_str}, force={force}")
    results: list[dict] = []
    for i, sid in enumerate(session_ids, start=1):
        log(f"[{i}/{n}] {sid}")
        try:
            results.append(mirror_session_to_mm(
                sid, force=force, current_model_string=model_str, log=log))
        except Exception as exc:  # noqa: BLE001 — isolate per-session failures
            log(f"  {sid}: ERROR {type(exc).__name__}: {exc}")
            results.append({"session_id": sid, "status": "error",
                            "error": f"{type(exc).__name__}: {exc}"})

    done = sum(1 for r in results if r.get("status") == "done")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    errors = sum(1 for r in results if r.get("status") == "error")
    rows = sum(r.get("rows_inserted", 0) for r in results)
    log(f"Backfill complete: {done} done, {skipped} skipped, {errors} errors, "
        f"{rows} rows inserted across {n} sessions")
    return {
        "status": "complete", "sessions": n, "done": done,
        "skipped": skipped, "errors": errors, "rows_inserted": rows,
        "model": model_str, "results": results,
    }
