"""Database Handler write helpers — Phase 3B.

Owns the stitch → embed → upsert / INSERT pipeline that turns a
Database Handler Q+A into a row on the Postgres ``chunks`` table,
plus the End-Session feedback path that lands ``sessions.feedback``
and the corresponding ``chunks`` mirror rows.

Behaviour locked by
extra_utilities/db_design/database_and_RAG_architecture.md:
  - Single source of truth for ``DEFAULT_AGENTS_TO_ACL`` (the 9
    primary chain agents — invariant 14).
  - Stitching prompt at agents/database_handler/stitching_prompt.md
    is load-bearing; bump its frontmatter ``version:`` on edit
    (see §6.1).
  - DH retries failed chunks INSERTs up to
    ``DATABASE_ENTRY_MAX_RETRIES`` times with a fixed
    ``DATABASE_ENTRY_RETRY_BACKOFF_SECONDS`` delay between attempts
    (invariant 9).
  - On exhaustion the Q+A is uploaded to the R2 safety folder for
    the session — no local copy, no Railway volume use
    (invariant 12).  When R2 itself is unreachable, the FULL Q+A
    body is logged at ERROR level so it survives in the session
    log file.
  - UNIQUE violations are NOT retried — they mean "already saved";
    :func:`insert_chunk` returns ``InsertOutcome.SKIPPED_UNIQUE``
    in that case.
  - Stitching is OpenAI-only in v9 (T16, T17 deferred); the
    workflow-settings editor locks ``STITCHING_PROVIDER`` to
    "OpenAI".

This module is imported by:
  - agents/database_handler/database_handler.py (Phase 3C) — calls
    upsert_session, upsert_attempt, upsert_attempt_parameters, and
    insert_chunk inline with the existing per-agent .txt save flow.
  - web_app.py's End Session handler (Phase 3C) — calls
    save_session_feedback after the modal payload is received.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from psycopg import errors as pg_errors
from psycopg.types.json import Json

from agents.shared import postgres_pool, r2_uploader
from workflow_settings import settings as workflow_settings
from workflow_settings.fixed_feedback_questions import (
    FIXED_FEEDBACK_QUESTIONS,
)

logger = logging.getLogger("propeller_agent")


# ============================================================
# Section 1.  Constants
# ============================================================

DEFAULT_AGENTS_TO_ACL: tuple[str, ...] = (
    "receptionist",
    "database_handler",
    "dc_input_inspector",
    "dc_output_inspector",
    "planner",
    "orchestrator",
    "user_input_inspector",
    "dc_input_creator",
    "tool_caller",
    # 5-agent topology (superset across topologies)
    "conductor",
    "creator",
)
"""The canonical primary chain-agent identifiers, used as the
default value for ``chunks.agents_to`` when a DH-schedule entry's
``to_agents`` is empty.  See architecture doc §3.6 + invariant 14.

When chain agents are added or removed, this tuple is the SINGLE
place to edit — every callsite reads from here.
"""

_STITCHING_PROMPT_PATH = (
    Path(__file__).resolve().parent / "stitching_prompt.md"
)


# ============================================================
# Section 2.  Exceptions + result enum
# ============================================================

class StitchError(RuntimeError):
    """Raised by :func:`stitch_for_embedding` on API failure or
    empty output.

    Treated by :func:`insert_chunk` as a DB-insert failure (consumes
    one retry attempt) per architecture doc §6.1.  No fallback
    concatenation is ever attempted.
    """


class EmbedError(RuntimeError):
    """Raised by :func:`embed_text` on API failure or dimension
    mismatch.

    Treated by :func:`insert_chunk` as a DB-insert failure (consumes
    one retry attempt).
    """


class InsertOutcome(str, Enum):
    """Return value of :func:`insert_chunk`.

    INSERTED         — row landed in the chunks table.
    SKIPPED_UNIQUE   — row already existed (UNIQUE constraint hit);
                       no retry was consumed; no safety-folder
                       write was triggered.  See architecture doc
                       §3.5.2 rule 2.
    SAFETY           — all DATABASE_ENTRY_MAX_RETRIES attempts
                       failed; the Q+A was uploaded to the R2
                       safety folder under <session_id>/safety/...
                       (or logged at ERROR level when R2 itself
                       was unreachable).
    """

    INSERTED       = "inserted"
    SKIPPED_UNIQUE = "skipped_unique"
    SAFETY         = "safety"


# ============================================================
# Section 3.  Stitching (LLM rewrite for embedding input)
# ============================================================

_stitching_prompt_cache: str | None = None
_stitching_prompt_cache_lock = threading.Lock()


def _load_stitching_prompt() -> str:
    """Read ``agents/database_handler/stitching_prompt.md`` and
    return the system-prompt body with the YAML frontmatter stripped.

    Cached after first read — the prompt is load-bearing and a
    server restart is the natural cache-invalidation point.
    """
    global _stitching_prompt_cache
    if _stitching_prompt_cache is not None:
        return _stitching_prompt_cache
    with _stitching_prompt_cache_lock:
        if _stitching_prompt_cache is not None:
            return _stitching_prompt_cache
        raw = _STITCHING_PROMPT_PATH.read_text(encoding="utf-8")
        # Strip YAML frontmatter delimited by lines that are exactly
        # ``---``.  Frontmatter must start at the very first line;
        # otherwise the whole file is treated as prompt body.
        if raw.startswith("---\n"):
            end = raw.find("\n---\n", 4)
            if end != -1:
                raw = raw[end + 5:]
        _stitching_prompt_cache = raw.strip()
        return _stitching_prompt_cache


# OpenAI client cache (module-level, lazy-init, thread-safe).
_openai_client: Any = None
_openai_client_lock = threading.Lock()


def _get_openai_client():
    """Lazy-init and return the singleton OpenAI SDK client.

    Reads ``OPENAI_API_KEY`` from the environment INDEPENDENTLY of
    ``workflow_settings.EMBEDDING_API_KEY`` — stitching and
    embedding are independent API calls per design Q-X1.

    Raises
    ------
    RuntimeError
        When the OpenAI SDK is not installed or
        ``OPENAI_API_KEY`` is not set.
    """
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    with _openai_client_lock:
        if _openai_client is not None:
            return _openai_client
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "openai SDK not installed; cannot stitch or embed."
            ) from exc
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set in the environment."
            )
        _openai_client = OpenAI(api_key=api_key)
        return _openai_client


def stitch_for_embedding(
    *,
    dc_name: str,
    field: str,
    question: str,
    answer: str,
    provider: str | None = None,
    model: str | None = None,
) -> str:
    """Call the cheap stitching LLM to rewrite (DC_NAME, FIELD,
    QUESTION, ANSWER) into a single coherent declarative paragraph
    optimised for sentence-embedding retrieval.

    The output is stored verbatim on ``chunks.embedding_input`` and
    fed to the embedding model.  See architecture doc §6.1 and the
    versioned system prompt at
    ``agents/database_handler/stitching_prompt.md``.

    Parameters
    ----------
    dc_name, field, question, answer:
        Plain strings interpolated into the user message verbatim.
    provider:
        Override for ``workflow_settings.STITCHING_PROVIDER``.
        Default reads from settings.  Phase 3B only supports
        "OpenAI"; other providers raise ``NotImplementedError`` per
        TODOs T16 (Anthropic) and T17 (Google).
    model:
        Override for ``workflow_settings.STITCHING_MODEL``.
        Default reads from settings (currently ``"gpt-4o-mini"``).

    Returns
    -------
    The stitched paragraph, stripped of surrounding whitespace.

    Raises
    ------
    StitchError
        On any OpenAI API failure or empty / whitespace-only output.
    NotImplementedError
        When ``provider`` is anything other than "OpenAI".
    """
    effective_provider = (provider or workflow_settings.STITCHING_PROVIDER).strip()
    effective_model    = (model    or workflow_settings.STITCHING_MODEL).strip()
    if effective_provider != "OpenAI":
        raise NotImplementedError(
            f"Stitching provider {effective_provider!r} is not yet "
            f"implemented (T16=Anthropic, T17=Google in the "
            f"architecture doc).  Only 'OpenAI' is supported."
        )

    try:
        client = _get_openai_client()
    except RuntimeError as exc:
        raise StitchError(f"OpenAI client unavailable: {exc}") from exc

    system_prompt = _load_stitching_prompt()
    user_message = (
        f"DC_NAME: {dc_name}\n"
        f"FIELD: {field}\n"
        f"QUESTION: {question}\n"
        f"ANSWER: {answer}"
    )

    try:
        resp = client.chat.completions.create(
            model=effective_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.0,
            max_tokens=workflow_settings.STITCHING_MAX_OUTPUT_TOKENS,
            seed=42,
        )
    except Exception as exc:  # broad: OpenAI exception hierarchy varies
        raise StitchError(
            f"OpenAI chat.completions.create failed: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    try:
        body = resp.choices[0].message.content or ""
    except (AttributeError, IndexError) as exc:
        raise StitchError(
            f"OpenAI stitching response had unexpected shape: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    body = body.strip()
    if not body:
        raise StitchError(
            "OpenAI stitching returned empty / whitespace-only output."
        )
    return body


# ============================================================
# Section 4.  Embedding (vector for chunks.embedding)
# ============================================================


def _embedding_model_string(provider: str, model: str, dims: int) -> str:
    """Format the ``chunks.embedding_model`` column value.

    Format is locked as ``"{provider.lower()}/{model}/{dims}"``
    (architecture doc §4.9, design Q3).  Example::

        "openai/text-embedding-3-large/1024"
    """
    return f"{provider.lower()}/{model}/{dims}"


def embed_text(
    text: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    dims: int | None = None,
) -> tuple[list[float], str]:
    """Call the embedding API and return
    ``(vector, embedding_model_string)``.

    Phase 3B supports only the OpenAI provider; other providers
    raise ``NotImplementedError``.

    The input is truncated to ``EMBEDDING_INPUT_MAX_CHARS``
    characters if longer — a WARNING is logged but the call still
    proceeds (lossy, but the row is still embedded).
    ``text-embedding-3-large`` has an 8192-token per-call limit; the
    default 30000-char cap stays comfortably under it.

    Parameters
    ----------
    text:
        The paragraph to embed.  Typically the output of
        :func:`stitch_for_embedding`.
    provider:
        Override for ``workflow_settings.EMBEDDING_PROVIDER``.
        Default reads from settings.
    model:
        Override for ``workflow_settings.EMBEDDING_MODEL``.
        Default reads from settings.
    dims:
        Override for ``workflow_settings.EMBEDDING_VECTOR_DIMS``.
        Default reads from settings.

    Returns
    -------
    ``(vector, embedding_model_string)`` where ``vector`` is a list
    of ``dims`` floats and ``embedding_model_string`` is the value
    that will be stored on ``chunks.embedding_model``.

    Raises
    ------
    EmbedError
        On any OpenAI API failure or if the returned vector length
        does not match ``dims``.
    NotImplementedError
        When ``provider`` is anything other than "OpenAI".
    """
    effective_provider = (provider or workflow_settings.EMBEDDING_PROVIDER).strip()
    effective_model    = (model    or workflow_settings.EMBEDDING_MODEL).strip()
    effective_dims     = int(dims  or workflow_settings.EMBEDDING_VECTOR_DIMS)
    if effective_provider != "OpenAI":
        raise NotImplementedError(
            f"Embedding provider {effective_provider!r} is not yet "
            f"implemented.  Only 'OpenAI' is supported."
        )

    # Defensive truncation: keep us under the 8192-token per-call
    # limit even when an upstream stitched paragraph is unusually
    # long.  Lossy but preserves the row (the alternative — raising
    # EmbedError and routing to the safety folder — would drop the
    # data from the corpus entirely).
    cap = int(workflow_settings.EMBEDDING_INPUT_MAX_CHARS)
    if len(text) > cap:
        logger.warning(
            f"[db_writer] embed_text input length {len(text)} exceeds "
            f"EMBEDDING_INPUT_MAX_CHARS={cap}; truncating to cap "
            f"(lossy)."
        )
        text = text[:cap]

    try:
        client = _get_openai_client()
    except RuntimeError as exc:
        raise EmbedError(f"OpenAI client unavailable: {exc}") from exc

    try:
        resp = client.embeddings.create(
            model=effective_model,
            input=text,
            dimensions=effective_dims,
        )
    except Exception as exc:
        raise EmbedError(
            f"OpenAI embeddings.create failed: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    try:
        vector = list(resp.data[0].embedding)
    except (AttributeError, IndexError) as exc:
        raise EmbedError(
            f"OpenAI embedding response had unexpected shape: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    if len(vector) != effective_dims:
        raise EmbedError(
            f"OpenAI embedding returned {len(vector)} dims, expected "
            f"{effective_dims}."
        )

    return vector, _embedding_model_string(
        effective_provider, effective_model, effective_dims,
    )


# ============================================================
# Section 5.  Parent-row upserts (FK targets for chunks)
# ============================================================


def upsert_session(
    *,
    session_id: str,
    session_ts: datetime,
    dc_name: str,
    schema_version: int,
    dc_inspector_enabled: bool,
    user_id: str | None = None,
    user_provided_images: bool = False,
    notes: str | None = None,
) -> None:
    """Insert (or update) one ``sessions`` row by ``session_id``.

    Idempotent — safe to call repeatedly with the same session_id
    during a Phase 3C save flow (the DH walks the schedule and may
    re-enter the upsert when re-running a partial save).

    Does NOT touch ``satisfaction`` / ``feedback`` — those columns
    are written by :func:`save_session_feedback` at End-Session
    time so the two write paths stay independent.

    Raises
    ------
    PostgresDisabledError
        When the connection pool has no configured URL.
    psycopg.errors.*
        On any DB error — caller decides whether to retry / abort.
    """
    sql = """
        INSERT INTO sessions (
            session_id, session_ts, user_id, dc_name,
            dc_inspector_enabled, schema_version, notes,
            user_provided_images
        )
        VALUES (
            %(session_id)s, %(session_ts)s, %(user_id)s, %(dc_name)s,
            %(dc_inspector_enabled)s, %(schema_version)s, %(notes)s,
            %(user_provided_images)s
        )
        ON CONFLICT (session_id) DO UPDATE SET
            session_ts           = EXCLUDED.session_ts,
            user_id              = EXCLUDED.user_id,
            dc_name              = EXCLUDED.dc_name,
            dc_inspector_enabled = EXCLUDED.dc_inspector_enabled,
            schema_version       = EXCLUDED.schema_version,
            notes                = EXCLUDED.notes,
            user_provided_images = EXCLUDED.user_provided_images
    """
    params = {
        "session_id":           session_id,
        "session_ts":           session_ts,
        "user_id":              user_id,
        "dc_name":              dc_name,
        "dc_inspector_enabled": dc_inspector_enabled,
        "schema_version":       schema_version,
        "notes":                notes,
        "user_provided_images": user_provided_images,
    }
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    # with-block exit commits on success / rolls back on exception
    # (psycopg-pool autocommit=False contract).
    logger.info(
        f"[db_writer] upsert_session OK session_id={session_id}"
    )


def upsert_attempt(
    *,
    session_id: str,
    attempt_label: str,
    schema_version: int,
    parameters_json: dict,
    has_geometry: bool = False,
    has_renders: bool = False,
) -> int:
    """Insert (or update) one ``dc_attempts`` row and return its
    ``attempt_id`` (BIGSERIAL PK).

    Phase 3C callers pass the returned id to
    :func:`upsert_attempt_parameters` and :func:`insert_chunk` so
    chunks FKs resolve.

    Idempotent — re-running for the same ``(session_id,
    attempt_label)`` pair returns the same ``attempt_id``.

    Raises
    ------
    PostgresDisabledError
        When the connection pool has no configured URL.
    psycopg.errors.*
        On any DB error.
    """
    sql = """
        INSERT INTO dc_attempts (
            session_id, attempt_label, schema_version,
            parameters_json, has_geometry, has_renders
        )
        VALUES (
            %(session_id)s, %(attempt_label)s, %(schema_version)s,
            %(parameters_json)s, %(has_geometry)s, %(has_renders)s
        )
        ON CONFLICT (session_id, attempt_label) DO UPDATE SET
            schema_version  = EXCLUDED.schema_version,
            parameters_json = EXCLUDED.parameters_json,
            has_geometry    = EXCLUDED.has_geometry,
            has_renders     = EXCLUDED.has_renders
        RETURNING attempt_id
    """
    params = {
        "session_id":       session_id,
        "attempt_label":    attempt_label,
        "schema_version":   schema_version,
        "parameters_json":  Json(parameters_json),  # JSONB-wrapped per Q-C4
        "has_geometry":     has_geometry,
        "has_renders":      has_renders,
    }
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(
                    f"upsert_attempt RETURNING attempt_id produced no "
                    f"row for ({session_id!r}, {attempt_label!r})."
                )
            attempt_id = int(row[0])
    logger.info(
        f"[db_writer] upsert_attempt OK session_id={session_id} "
        f"attempt_label={attempt_label} attempt_id={attempt_id}"
    )
    return attempt_id


def upsert_attempt_parameters(
    *,
    attempt_id: int,
    parameters: dict[str, float],
) -> None:
    """Bulk upsert into ``dc_attempt_parameters`` for one attempt.

    Each entry in ``parameters`` becomes one row keyed by
    ``(attempt_id, param_name)``.  Existing rows for the same key
    have their ``raw_value`` overwritten.

    Empty input is a no-op (no DB round-trip).

    Raises
    ------
    PostgresDisabledError
        When the connection pool has no configured URL.
    psycopg.errors.*
        On any DB error.
    """
    if not parameters:
        logger.info(
            f"[db_writer] upsert_attempt_parameters skipped "
            f"(empty parameters dict) attempt_id={attempt_id}"
        )
        return
    sql = """
        INSERT INTO dc_attempt_parameters (
            attempt_id, param_name, raw_value
        )
        VALUES (%s, %s, %s)
        ON CONFLICT (attempt_id, param_name) DO UPDATE SET
            raw_value = EXCLUDED.raw_value
    """
    rows = [
        (attempt_id, name, float(value))
        for name, value in parameters.items()
    ]
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
    logger.info(
        f"[db_writer] upsert_attempt_parameters OK "
        f"attempt_id={attempt_id} n_params={len(rows)}"
    )


# ============================================================
# Section 6.  Safety-folder write (R2 only — no local copy)
# ============================================================


def _format_safety_payload(
    *,
    field: str,
    question: str,
    answer: str,
    agents_to: list[str],
    field_type: str,
    attempt_id_label: str,
    retry_count: int,
    max_retries: int,
    last_db_error: str,
    cascade_source: str | None,
) -> str:
    """Build the §3.5.4-formatted safety-file body (diagnostic header
    + canonical ``--- Field/Question/Answer ---`` block).

    Returns a plain-text string ready to encode as UTF-8 and PUT to
    R2.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cascade_line = cascade_source or "(none)"
    agents_line = ", ".join(agents_to)
    return (
        "--- SAFETY-SAVE DIAGNOSTIC ---\n"
        f"Timestamp:                 {ts}\n"
        f"Retry count:               {retry_count} of {max_retries}\n"
        f"Last DB error:             {last_db_error}\n"
        f"Field type:                {field_type}\n"
        f"Attempt ID:                {attempt_id_label}\n"
        f"Cascade source:            {cascade_line}\n"
        f"Agents allowed to access this answer:  {agents_line}\n"
        "--- Field ---\n"
        f"{field}\n"
        "--- Question ---\n"
        f"{question}\n"
        "--- Answer ---\n"
        f"{answer}\n"
    )


def save_to_safety_folder(
    *,
    session_id: str,
    scope: str,
    filename: str,
    field: str,
    question: str,
    answer: str,
    agents_to: list[str],
    field_type: str,
    attempt_id_label: str,
    retry_count: int,
    max_retries: int,
    last_db_error: str,
    cascade_source: str | None = None,
) -> bool:
    """Upload one safety file directly to R2 (no local copy).

    Layout::

        <session_id>/safety/<scope>/<filename>

    where ``scope`` is ``"session"`` for session-generic failures or
    ``f"attempt_{NNN}"`` for attempt-specific ones.  See architecture
    doc §3.5.3.

    Behaviour when R2 is unreachable (``is_enabled()`` False OR
    ``upload_bytes`` returned False):

    * Log a HARD ERROR carrying the FULL Q+A body so the data
      survives in the session log file.  See design decision Q5b.
    * Return False so the caller can decide whether to escalate.

    Returns True iff the R2 upload succeeded.
    """
    if scope != "session" and not scope.startswith("attempt_"):
        # Defensive — silently coerce to the safest default rather
        # than refusing to save, since the caller is already in the
        # error path.
        logger.warning(
            f"[db_writer] save_to_safety_folder got unexpected "
            f"scope={scope!r}; coercing to 'session'."
        )
        scope = "session"
    payload = _format_safety_payload(
        field=field,
        question=question,
        answer=answer,
        agents_to=list(agents_to),
        field_type=field_type,
        attempt_id_label=attempt_id_label,
        retry_count=retry_count,
        max_retries=max_retries,
        last_db_error=last_db_error,
        cascade_source=cascade_source,
    )
    remote_key = f"{session_id}/safety/{scope}/{filename}"
    if not r2_uploader.is_enabled():
        logger.error(
            "[db_writer] R2 disabled — safety file cannot be "
            "uploaded; logging full Q+A body so data survives in "
            "the session log.\n"
            f"  remote_key (would-be): {remote_key}\n"
            f"  payload:\n{payload}"
        )
        return False
    ok = r2_uploader.upload_bytes(
        payload.encode("utf-8"), remote_key,
        content_type="text/plain",
    )
    if not ok:
        logger.error(
            "[db_writer] R2 upload of safety file FAILED — logging "
            "full Q+A body so data survives in the session log.\n"
            f"  remote_key (attempted): {remote_key}\n"
            f"  payload:\n{payload}"
        )
        return False
    logger.info(
        f"[db_writer] safety file uploaded to R2: {remote_key} "
        f"(retry {retry_count}/{max_retries})"
    )
    return True


# ============================================================
# Section 7.  insert_chunk — the full stitch → embed → INSERT chain
# ============================================================


def _attempt_id_label_from_scope(scope: str) -> str:
    """Derive the diagnostic ``Attempt ID:`` line value for the
    safety file header from the ``safety_scope`` argument.
    """
    if scope.startswith("attempt_"):
        return scope[len("attempt_"):]
    return "session-generic"


_CHUNK_INSERT_SQL = """
    INSERT INTO chunks (
        session_id, attempt_id, agent_from, agents_to,
        field, field_type, question, body, item_index,
        embedding, embedding_model, embedding_input,
        is_error, is_empty
    )
    VALUES (
        %(session_id)s, %(attempt_id)s, %(agent_from)s, %(agents_to)s,
        %(field)s, %(field_type)s, %(question)s, %(body)s,
        %(item_index)s,
        %(embedding)s, %(embedding_model)s, %(embedding_input)s,
        %(is_error)s, %(is_empty)s
    )
"""


def insert_chunk(
    *,
    # Identity / FK
    session_id: str,
    attempt_id: int | None,
    # ACL + classification
    agent_from: str,
    agents_to: list[str],
    field: str,
    field_type: str,
    # Payload
    question: str | None,
    body: str,
    item_index: int | None = None,
    is_error: bool = False,
    is_empty: bool = False,
    # Stitching context (Semantic non-empty only — passed verbatim
    # to the stitching LLM as the DC_NAME line)
    dc_name: str | None = None,
    # Safety-fallback context (required because R2-only on exhaust)
    safety_scope: str,
    safety_filename: str,
    cascade_source: str | None = None,
) -> InsertOutcome:
    """Run the full stitch → embed → INSERT chain for one ``chunks``
    row, with retry and R2 safety-folder fallback.

    See architecture doc §3.5 / §6.1.2 for the locked behaviour.

    Behaviour summary
    -----------------
    - Empty ``agents_to`` → :data:`DEFAULT_AGENTS_TO_ACL`
      (invariant 14).
    - ``field_type='Quantitative'`` OR ``is_empty=True``:
      skip stitch + embed; INSERT directly with
      ``embedding=NULL``, ``embedding_model=NULL``,
      ``embedding_input=NULL``.
    - ``field_type='Semantic'`` AND NOT ``is_empty``:
        for attempt in 1..DATABASE_ENTRY_MAX_RETRIES:
            stitch (cheap LLM)
            embed (text-embedding-3-large)
            INSERT
            return INSERTED on success
        if a UniqueViolation occurs at any point: return
        SKIPPED_UNIQUE (no retry consumed).
        On exhaustion: write safety file to R2, return SAFETY.
    - All other exceptions consume a retry attempt with a fixed
      ``DATABASE_ENTRY_RETRY_BACKOFF_SECONDS`` delay between
      attempts.

    Parameters
    ----------
    session_id, attempt_id:
        FK targets.  ``attempt_id=None`` for session-scoped rows.
    agent_from:
        Originating agent identifier.  Required.
    agents_to:
        ACL list (architecture doc §3.6 + invariant 14).  Empty list
        → :data:`DEFAULT_AGENTS_TO_ACL`.
    field, field_type, question, body, item_index, is_error,
    is_empty:
        Verbatim ``chunks`` column values.
    dc_name:
        Required for Semantic non-empty rows (passed to the
        stitching LLM as ``DC_NAME``).  Unused otherwise.
    safety_scope:
        ``"session"`` or ``f"attempt_{NNN}"`` — drives the R2 key
        prefix on safety-folder writes.
    safety_filename:
        DH source filename (e.g. ``"Plan__001.txt"``).  Used as the
        R2 object name under ``<session_id>/safety/<scope>/``.
    cascade_source:
        Optional ``"Cascade source:"`` line value for the safety
        file (architecture doc §3.5.4) — set by the DH integration
        when this row's parent identifying-Q failed.

    Returns
    -------
    InsertOutcome.INSERTED | SKIPPED_UNIQUE | SAFETY.
    """
    # ----- input normalisation -------------------------------------
    if field_type not in ("Semantic", "Quantitative"):
        raise ValueError(
            f"field_type must be 'Semantic' or 'Quantitative', "
            f"got {field_type!r}."
        )
    effective_agents_to = list(agents_to) if agents_to else list(
        DEFAULT_AGENTS_TO_ACL
    )

    skip_stitch_embed = (field_type == "Quantitative") or is_empty

    if field_type == "Semantic" and not is_empty and not dc_name:
        raise ValueError(
            "insert_chunk requires dc_name for Semantic, non-empty "
            "rows (the stitching prompt needs the DC_NAME line)."
        )

    max_retries = int(workflow_settings.DATABASE_ENTRY_MAX_RETRIES)
    backoff = float(workflow_settings.DATABASE_ENTRY_RETRY_BACKOFF_SECONDS)
    attempt_id_label = _attempt_id_label_from_scope(safety_scope)

    last_db_error_repr = "(no error recorded)"
    attempt = 1
    while attempt <= max_retries:
        try:
            # ----- stitch + embed (Semantic non-empty only) --------
            if skip_stitch_embed:
                embedding_input: str | None = None
                vector: list[float] | None = None
                model_str: str | None = None
            else:
                embedding_input = stitch_for_embedding(
                    dc_name=dc_name or "",   # guard above ensures non-empty
                    field=field,
                    question=question or "",
                    answer=body,
                )
                vector, model_str = embed_text(embedding_input)

            # ----- INSERT ------------------------------------------
            params = {
                "session_id":      session_id,
                "attempt_id":      attempt_id,
                "agent_from":      agent_from,
                "agents_to":       effective_agents_to,
                "field":           field,
                "field_type":      field_type,
                "question":        question,
                "body":            body,
                "item_index":      item_index,
                "embedding":       vector,
                "embedding_model": model_str,
                "embedding_input": embedding_input,
                "is_error":        is_error,
                "is_empty":        is_empty,
            }
            with postgres_pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(_CHUNK_INSERT_SQL, params)
            # with-block exit committed cleanly.
            logger.info(
                f"[db_writer] insert_chunk OK "
                f"session_id={session_id} "
                f"attempt_id={attempt_id} "
                f"agent_from={agent_from} field={field!r} "
                f"item_index={item_index} field_type={field_type} "
                f"is_empty={is_empty} attempt={attempt}/{max_retries}"
            )
            return InsertOutcome.INSERTED

        except pg_errors.UniqueViolation as exc:
            # Already saved — exit immediately, do NOT consume retry,
            # do NOT write safety.  Architecture doc §3.5.2 rule 2.
            logger.info(
                f"[db_writer] insert_chunk SKIPPED_UNIQUE "
                f"session_id={session_id} field={field!r} "
                f"attempt_id={attempt_id} item_index={item_index} "
                f"({exc})"
            )
            return InsertOutcome.SKIPPED_UNIQUE

        except Exception as exc:
            last_db_error_repr = f"{type(exc).__name__}: {exc}"
            logger.warning(
                f"[db_writer] insert_chunk attempt "
                f"{attempt}/{max_retries} FAILED "
                f"session_id={session_id} field={field!r}: "
                f"{last_db_error_repr}"
            )
            if attempt < max_retries:
                time.sleep(backoff)
            attempt += 1
            continue

    # ----- retries exhausted → safety folder ------------------------
    logger.warning(
        f"[db_writer] insert_chunk EXHAUSTED retries "
        f"({max_retries}/{max_retries}) "
        f"session_id={session_id} field={field!r}; routing to R2 "
        f"safety folder."
    )
    save_to_safety_folder(
        session_id=session_id,
        scope=safety_scope,
        filename=safety_filename,
        field=field,
        question=question or "",
        answer=body,
        agents_to=effective_agents_to,
        field_type=field_type,
        attempt_id_label=attempt_id_label,
        retry_count=max_retries,
        max_retries=max_retries,
        last_db_error=last_db_error_repr,
        cascade_source=cascade_source,
    )
    return InsertOutcome.SAFETY


# ============================================================
# Section 8.  save_session_feedback — End-Session helper
# ============================================================


def _slugify_field_for_filename(field: str) -> str:
    """Convert a field name like ``"Positive User Comments"`` to a
    safe filename slug like ``"Positive_User_Comments.txt"`` for the
    R2 safety folder.

    Inline helper (db_writer is the only consumer); intentionally
    NOT shared with the DH's existing slug helper in
    ``database_handler.py`` to avoid a circular import.  See the
    developer-notes entry on this duplication.
    """
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", field).strip("_")
    return f"{safe or 'field'}.txt"


_SESSION_FEEDBACK_UPDATE_SQL = """
    UPDATE sessions
    SET satisfaction = %(satisfaction)s,
        feedback     = %(feedback)s
    WHERE session_id = %(session_id)s
"""


def save_session_feedback(
    *,
    session_id: str,
    dc_name: str,
    satisfaction: int | None,
    answers: dict[str, str | None],
) -> dict[str, InsertOutcome]:
    """Persist the End-Session feedback for one session.

    Writes:

    1. UPDATE on ``sessions``:
       - ``satisfaction`` ← the 0..10 quick-score (or NULL)
       - ``feedback``     ← labelled-block concatenation of all
                            answered fixed feedback questions, in
                            ``FIXED_FEEDBACK_QUESTIONS`` order, with
                            blocks separated by a blank line.
                            NULL when no question was answered.
    2. One ``chunks`` row per question in
       :data:`workflow_settings.fixed_feedback_questions.FIXED_FEEDBACK_QUESTIONS`:
       - **Answered question:** Semantic row with the user's text
         in ``body``, stitched + embedded normally.
       - **Unanswered question:** Semantic row with
         ``body=""``, ``is_empty=True``, ``embedding=NULL``
         (allowed by the v5 relaxed CHECK constraint — see
         architecture doc §3.1 v5 addendum + §3.3 + §3.7).  Acts
         as a safety-net marker that the question WAS asked.

    Architecture doc §3.3 locks this behaviour.

    Parameters
    ----------
    session_id:
        Target sessions row.  Must already exist
        (:func:`upsert_session` is expected to have run earlier in
        the End-Session flow).
    dc_name:
        DC name for the stitching LLM's DC_NAME line.
    satisfaction:
        0..10 numeric quick-score, or None for "user did not
        answer the slider".
    answers:
        Map ``{fixed_id: answer_text_or_None_or_empty}`` keyed by
        :data:`FIXED_FEEDBACK_QUESTIONS` entry ``id``.  A missing
        key is treated as unanswered.

    Returns
    -------
    Mapping ``{fixed_id: InsertOutcome}`` so the caller can log
    per-question outcomes.

    Raises
    ------
    PostgresDisabledError
        When the connection pool has no configured URL.
    RuntimeError
        When the UPDATE matched zero rows (no sessions row for
        ``session_id`` — caller forgot to upsert the session).
    psycopg.errors.*
        On UPDATE failure (the chunks inserts handle their own
        retries via :func:`insert_chunk`).
    """
    # ----- 1. Build sessions.feedback labelled-block text -----------
    blocks: list[str] = []
    for q in FIXED_FEEDBACK_QUESTIONS:
        ans = (answers.get(q["id"]) or "").strip()
        if not ans:
            continue
        blocks.append(f"--- {q['block_label']} ---\n{ans}")
    feedback_text: str | None = "\n\n".join(blocks) if blocks else None

    # ----- 2. UPDATE sessions (with row-presence guard, N18) --------
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                _SESSION_FEEDBACK_UPDATE_SQL,
                {
                    "session_id":   session_id,
                    "satisfaction": satisfaction,
                    "feedback":     feedback_text,
                },
            )
            if cur.rowcount == 0:
                raise RuntimeError(
                    f"save_session_feedback: no sessions row for "
                    f"{session_id!r} — call upsert_session first."
                )
    logger.info(
        f"[db_writer] save_session_feedback UPDATE OK "
        f"session_id={session_id} satisfaction={satisfaction} "
        f"feedback_len={(len(feedback_text) if feedback_text else 0)}"
    )

    # ----- 3. One chunks row per fixed feedback question -----------
    outcomes: dict[str, InsertOutcome] = {}
    for q in FIXED_FEEDBACK_QUESTIONS:
        ans_raw = answers.get(q["id"])
        answered = bool(ans_raw and ans_raw.strip())
        body = ans_raw.strip() if answered else ""
        outcome = insert_chunk(
            session_id=session_id,
            attempt_id=None,
            agent_from="User",
            agents_to=[],  # → DEFAULT_AGENTS_TO_ACL via invariant 14
            field=q["field"],
            field_type="Semantic",
            question=q["question"],
            body=body,
            item_index=None,
            is_error=False,
            is_empty=not answered,
            dc_name=dc_name,
            safety_scope="session",
            safety_filename=_slugify_field_for_filename(q["field"]),
            cascade_source=None,
        )
        outcomes[q["id"]] = outcome

    logger.info(
        f"[db_writer] save_session_feedback chunks results "
        f"session_id={session_id} outcomes="
        + ", ".join(f"{k}={v.value}" for k, v in outcomes.items())
    )
    return outcomes
