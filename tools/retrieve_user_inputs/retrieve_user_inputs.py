"""retrieve_user_inputs — DC-specific R2-backed retrieval tool.

When a chain agent calls ``retrieve_user_inputs(sessions_ID_list,
images_flag)``, the tool:

1. Validates each session_id against the Postgres ``sessions`` table
   (and fetches each existing session's ``user_provided_images`` bool).
2. For each existing session, fetches from R2:
     * ``<sid>/user_inputs/queries.txt`` (user's chronological text inputs).
     * ``<sid>/user_inputs/images/<name>_note.txt`` (image notes), when
       ``user_provided_images=True``.
     * ``<sid>/user_inputs/images/<name>.{png,jpg,jpeg}`` (image bytes),
       when ``images_flag=True`` AND ``user_provided_images=True``.
3. Assembles an XML response (``<retrieve_user_inputs_meta/>`` +
   per-session blocks); trims sessions from the end of the input list
   when the response exceeds ``RETRIEVE_MAX_RESPONSE_TOKENS``.
4. Logs the call to ``rag_queries`` with
   ``tool_name='retrieve_user_inputs'`` (schema v7).
5. Returns ``(xml, image_blocks, image_paths)`` to the caller.

The ``@tool``-decorated public stub returns ``""`` — the dispatcher
in ``agents/shared/retrieve_tool_dispatcher.py`` intercepts and runs
the real ``_run_retrieve_user_inputs`` function below.  This split
mirrors the existing ``view_images`` pattern: one LLM-side
tool call produces both XML evidence (appended as a ``ToolMessage``)
and image content blocks (buffered for the next ``HumanMessage``).

Architecture references
-----------------------
* Architecture doc §4 (retrieval contract) + Phase 5B design lock.
* W30 — R2 path layout (Path 1 ``upload_directory``: keys under
  ``<sid>/user_inputs/...``).
* W33 — DBa per-agent gating + RAG_ENABLED master switch (same
  gates as database_search).
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any
from xml.sax.saxutils import escape, quoteattr

import tiktoken
from langchain_core.tools import tool
from psycopg.types.json import Json

from agents.shared import postgres_pool
from agents.shared.agent_activity import generic_tool
from agents.shared.image_compression import degree_from_json_text
from agents.shared.llm_provider import encode_image_bytes, make_image_block
from agents.shared.ocr import ocr_summary_if_enabled
from agents.shared import r2_uploader
from workflow_settings import ocr_access
from workflow_settings import settings as workflow_settings

logger = logging.getLogger("propeller_agent")


# ============================================================
# Module-level settings refs
# ============================================================
_MAX_RESPONSE_TOKENS = int(workflow_settings.RETRIEVE_MAX_RESPONSE_TOKENS)

# cl100k_base is the tokenizer used by the GPT-4 family and
# text-embedding-3-large; matches database_search's token-cap
# accounting for consistency in observability data.
_TOKENIZER = tiktoken.get_encoding("cl100k_base")

# Whitelist of image suffixes considered for retrieval.  Mirrors the
# pairing convention enforced by the Receptionist (case-insensitive).
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")


# ============================================================
# Postgres helper
# ============================================================
def _validate_sessions_in_postgres(
    session_ids: list[str],
) -> dict[str, bool | None]:
    """Look up which of *session_ids* exist in the sessions table.

    Returns a dict mapping every requested session_id to:
      * ``True``  — the session exists AND user_provided_images=TRUE
      * ``False`` — the session exists AND user_provided_images=FALSE
      * ``None``  — the session does NOT exist in Postgres
    """
    if not session_ids:
        return {}
    out: dict[str, bool | None] = {sid: None for sid in session_ids}
    if not postgres_pool.is_enabled():
        # No Postgres → no way to validate.  Mark all as "unknown"
        # (None) and let the caller decide whether to attempt R2
        # fetches anyway.
        return out
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT session_id, user_provided_images "
                "FROM sessions "
                "WHERE session_id = ANY(%s)",
                (session_ids,),
            )
            for sid, has_images in cur.fetchall():
                out[sid] = bool(has_images)
    return out


# ============================================================
# R2 helpers
# ============================================================
def _r2_key(*parts: str) -> str:
    """Build a slash-joined R2 key (prefix-free; client adds prefix)."""
    return "/".join(p.strip("/") for p in parts if p)


def _r2_bucket_and_client() -> tuple[str | None, Any]:
    """Return ``(bucket_name, boto3_client)`` or ``(None, None)`` when
    R2 is not configured.  The client is per-call (matches the
    pattern used by ``r2_uploader``).
    """
    if not r2_uploader.is_enabled():
        return None, None
    client = r2_uploader._client()  # noqa: SLF001 — single source of truth
    if client is None:
        return None, None
    return r2_uploader._env("R2_BUCKET_NAME"), client  # noqa: SLF001


def _r2_get_text(client, bucket: str, key: str) -> str | None:
    """GET *key* from R2 and decode as UTF-8.  Returns None on miss / error."""
    full_key = f"{r2_uploader._key_prefix()}{key.lstrip('/')}"  # noqa: SLF001
    try:
        resp = client.get_object(Bucket=bucket, Key=full_key)
        return resp["Body"].read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 — R2 surfaces many error classes
        logger.info(
            f"[retrieve_user_inputs]  R2 GET miss for {full_key}: "
            f"{type(exc).__name__}: {exc}"
        )
        return None


def _r2_get_bytes(client, bucket: str, key: str) -> bytes | None:
    """GET *key* from R2 and return the raw bytes.  Returns None on miss / error."""
    full_key = f"{r2_uploader._key_prefix()}{key.lstrip('/')}"  # noqa: SLF001
    try:
        resp = client.get_object(Bucket=bucket, Key=full_key)
        return resp["Body"].read()
    except Exception as exc:  # noqa: BLE001
        logger.info(
            f"[retrieve_user_inputs]  R2 GET miss for {full_key}: "
            f"{type(exc).__name__}: {exc}"
        )
        return None


def _r2_list_user_images(
    client, bucket: str, session_id: str,
) -> list[str]:
    """List ``<sid>/user_inputs/images/`` and return basenames.

    Returns every key's filename portion (without the path prefix).
    The caller splits this into image files vs. note files by suffix.
    """
    prefix = (
        f"{r2_uploader._key_prefix()}"  # noqa: SLF001
        f"{session_id}/user_inputs/images/"
    )
    out: list[str] = []
    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                key = obj.get("Key", "")
                if key.startswith(prefix):
                    name = key[len(prefix):]
                    if name and "/" not in name:
                        out.append(name)
    except Exception as exc:  # noqa: BLE001
        logger.info(
            f"[retrieve_user_inputs]  R2 LIST failed for {prefix}: "
            f"{type(exc).__name__}: {exc}"
        )
    return out


# ============================================================
# Image pairing
# ============================================================
def _split_image_and_note_names(
    listed: list[str],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Partition R2 listing into (image_files, note_files).

    Each list entry is ``(stem, filename)``.  ``stem`` is the name
    without suffix (and without ``_note`` for notes), used to pair
    each image with its matching note.
    """
    images: list[tuple[str, str]] = []
    notes: list[tuple[str, str]] = []
    for name in listed:
        lower = name.lower()
        if lower.endswith("_note.txt"):
            stem = name[: -len("_note.txt")]
            notes.append((stem, name))
            continue
        for suf in _IMAGE_SUFFIXES:
            if lower.endswith(suf):
                stem = name[: -len(suf)]
                images.append((stem, name))
                break
    return images, notes


# ============================================================
# XML build + trim
# ============================================================
def _attr(value: Any) -> str:
    """Render *value* as an XML attribute (already quoted)."""
    return quoteattr(str(value))


def _wrap_cdata(text: str) -> str:
    """Wrap *text* in a CDATA section, splitting if it contains ``]]>``."""
    # CDATA cannot contain the literal "]]>" — split into multiple
    # sections if it does (rare for user prose).
    if "]]>" in text:
        text = text.replace("]]>", "]]]]><![CDATA[>")
    return f"<![CDATA[{text}]]>"


def _build_session_block(
    session_id: str,
    queries_text: str | None,
    image_notes: list[tuple[str, str | None]],
    image_refs: list[tuple[str, str]],  # (name, r2_key)
    fetch_failures: list[str],
) -> str:
    """Render one <session> block."""
    parts: list[str] = []
    parts.append(f"<session id={_attr(session_id)}>")
    if queries_text is None:
        # queries.txt missing in R2.  Emit a <missing> marker.
        parts.append(
            f"  <missing path={_attr(f'{session_id}/user_inputs/queries.txt')}/>"
        )
    else:
        parts.append("  <user_query>")
        parts.append("    " + _wrap_cdata(queries_text))
        parts.append("  </user_query>")
    if image_notes:
        parts.append("  <image_notes>")
        for name, note_text in image_notes:
            if note_text is None:
                parts.append(
                    f"    <missing path={_attr(f'{session_id}/user_inputs/images/{name}_note.txt')}/>"
                )
                continue
            parts.append(f"    <note name={_attr(name)}>")
            parts.append("      " + _wrap_cdata(note_text))
            parts.append("    </note>")
        parts.append("  </image_notes>")
    if image_refs:
        parts.append("  <images>")
        for name, key in image_refs:
            parts.append(
                f"    <image name={_attr(name)} key={_attr(key)}/>"
            )
        parts.append("  </images>")
    for failure_key in fetch_failures:
        # Catch-all marker for any other unexpected fetch miss
        # (kept separate from queries/notes-specific markers above
        # so an operator can distinguish the failure mode).
        parts.append(f"  <missing path={_attr(failure_key)}/>")
    parts.append("</session>")
    return "\n".join(parts)


def _build_xml(
    session_records: list[dict],
    images_included: bool,
    truncated_count: int,
) -> str:
    """Render the full response XML from per-session records."""
    n_requested = sum(1 for r in session_records if r.get("present_in_meta", True))
    n_returned = sum(
        1 for r in session_records
        if r.get("present_in_meta", True)
        and not r.get("not_found", False)
        and not r.get("trimmed", False)
    )
    parts: list[str] = [
        f"<retrieve_user_inputs_meta "
        f"sessions_requested={_attr(n_requested)} "
        f"sessions_returned={_attr(n_returned)} "
        f"images_included={_attr(str(images_included).lower())} "
        f"truncated={_attr(str(truncated_count > 0).lower())}/>"
    ]
    for r in session_records:
        if r.get("trimmed"):
            continue
        if r.get("not_found"):
            parts.append(
                f"<session id={_attr(r['session_id'])} status=\"not_found\"/>"
            )
            continue
        if r.get("ignored"):
            # Session on the system-managed ignore list — see the
            # Database admin view.  Self-closing marker, no R2 /
            # Postgres fetch was performed.
            parts.append(
                f"<session id={_attr(r['session_id'])} status=\"ignored\"/>"
            )
            continue
        parts.append(_build_session_block(
            r["session_id"],
            r["queries_text"],
            r["image_notes"],
            r["image_refs"],
            r["fetch_failures"],
        ))
    if truncated_count > 0:
        parts.append(
            f"<truncated omitted_sessions={_attr(truncated_count)}/>"
        )
    return "\n".join(parts)


def _count_tokens(text: str) -> int:
    return len(_TOKENIZER.encode(text, disallowed_special=()))


def _trim_to_cap(
    session_records: list[dict],
    images_included: bool,
    cap_tokens: int,
) -> tuple[str, int]:
    """Render XML and drop sessions from the END until under *cap_tokens*.

    Returns ``(xml, n_trimmed)``.  Per the locked design Q4 the
    trim drops whole sessions starting from the end of the input
    list, never partial sessions.
    """
    # Start with all sessions present (none trimmed yet).
    for r in session_records:
        r["trimmed"] = False
    xml = _build_xml(session_records, images_included, truncated_count=0)
    if cap_tokens <= 0 or _count_tokens(xml) <= cap_tokens:
        return xml, 0
    # Walk backwards through session_records, marking each as
    # trimmed until we fit.
    trimmed = 0
    for r in reversed(session_records):
        if r.get("not_found") or r.get("ignored"):
            # not_found / ignored markers are single self-closing
            # tags; trimming them yields negligible savings.  Skip.
            continue
        r["trimmed"] = True
        trimmed += 1
        xml = _build_xml(session_records, images_included, truncated_count=trimmed)
        if _count_tokens(xml) <= cap_tokens:
            return xml, trimmed
    # Even after trimming all session blocks we are over cap.
    # Return the minimal XML (just meta + footer) and accept the
    # over-cap state.  Realistically this is unreachable with
    # default settings; defensive.
    return xml, trimmed


# ============================================================
# rag_queries log
# ============================================================
def _log_to_rag_queries(
    *,
    caller_agent: str,
    session_ids: list[str],
    images_flag: bool,
    n_returned: int,
    returned_session_ids: list[str],
    skipped_count: int,
    truncated_anchors: int,
    latency_ms: int,
    error_message: str | None,
) -> None:
    """Best-effort INSERT into rag_queries.  Never raises."""
    if not postgres_pool.is_enabled():
        return
    try:
        with postgres_pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO rag_queries ("
                    "  caller_agent, tool_name, query_params, "
                    "  n_requested, images_flag, "
                    "  n_returned, returned_anchor_ids, skipped_count, "
                    "  truncated_anchors, latency_ms, error_message"
                    ") VALUES ("
                    "  %s, %s, %s, "
                    "  %s, %s, "
                    "  %s, %s, %s, "
                    "  %s, %s, %s"
                    ")",
                    (
                        caller_agent,
                        "retrieve_user_inputs",
                        Json({"sessions_ID_list": session_ids}),
                        len(session_ids),
                        images_flag,
                        n_returned,
                        Json([{"session_id": sid} for sid in returned_session_ids]),
                        skipped_count,
                        truncated_anchors,
                        latency_ms,
                        error_message,
                    ),
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"[retrieve_user_inputs]  rag_queries log failed: "
            f"{type(exc).__name__}: {exc}"
        )


# ============================================================
# Public surface
# ============================================================
def _run_retrieve_user_inputs(
    *,
    caller_agent: str,
    session_ids: list[str],
    images_flag: bool,
    provider: str = "openai",
    extract_text: bool = False,
) -> tuple[str, list[dict], list[str]]:
    """Real retrieval logic.  Called by the dispatcher.

    Returns ``(xml_str, image_blocks, image_paths)``.  ``image_blocks``
    is a list of provider-shaped image content-block dicts ready to
    attach via ``append_pending_images``.  ``image_paths`` is the
    parallel list of R2 keys used as text labels in the next
    ``HumanMessage`` so the path stays in history even after image
    bytes are stripped.
    """
    start = time.monotonic()
    error_message: str | None = None
    image_blocks: list[dict] = []
    image_paths: list[str] = []
    ocr_items: list[tuple[str, bytes]] = []
    session_records: list[dict] = []
    try:
        existence = _validate_sessions_in_postgres(session_ids)
        bucket, client = _r2_bucket_and_client()

        # System-managed session ignore list — read fresh on every
        # tool call so a Database admin UI edit takes effect
        # immediately.  Sessions on the list are skipped without
        # hitting Postgres or R2 — they emit a self-closing
        # <session id="..." status="ignored"/> marker.
        try:
            from workflow_settings.db_search_ignore_list import (
                get_ignore_list as _get_il,
            )
            _ignored_set = set(_get_il())
        except Exception:
            _ignored_set = set()

        for sid in session_ids:
            if sid in _ignored_set:
                session_records.append({
                    "session_id": sid,
                    "ignored": True,
                })
                continue
            has_images = existence.get(sid, None)
            if has_images is None and not postgres_pool.is_enabled():
                # Postgres is down; we cannot validate.  Best-effort:
                # attempt R2 fetches anyway, treat session as "exists,
                # may have images".  An R2 miss on queries.txt will
                # surface as a <missing/> marker.
                logger.info(
                    f"[retrieve_user_inputs]  Postgres disabled — "
                    f"attempting R2 fetches for {sid} blindly."
                )
                has_images = True
            if has_images is None:
                # Session not in Postgres → not_found marker.
                session_records.append({
                    "session_id": sid,
                    "not_found": True,
                })
                continue

            queries_text: str | None = None
            image_notes: list[tuple[str, str | None]] = []
            image_refs: list[tuple[str, str]] = []
            fetch_failures: list[str] = []

            if bucket is None or client is None:
                # R2 not configured: emit <missing/> markers and
                # move on.  Won't return any content.
                fetch_failures.append(
                    f"{sid}/user_inputs/ (R2 not configured)"
                )
            else:
                # queries.txt
                queries_text = _r2_get_text(
                    client, bucket,
                    _r2_key(sid, "user_inputs", "queries.txt"),
                )
                # Images + notes
                if has_images:
                    listed = _r2_list_user_images(client, bucket, sid)
                    images_listed, notes_listed = (
                        _split_image_and_note_names(listed)
                    )
                    # Notes — always fetched if any images exist
                    for stem, note_name in notes_listed:
                        note_text = _r2_get_text(
                            client, bucket,
                            _r2_key(sid, "user_inputs", "images", note_name),
                        )
                        image_notes.append((stem, note_text))
                    # Images (only when flag set)
                    if images_flag:
                        for stem, img_name in images_listed:
                            key = _r2_key(
                                sid, "user_inputs", "images", img_name,
                            )
                            full_key = (
                                f"{r2_uploader._key_prefix()}"  # noqa: SLF001
                                f"{key.lstrip('/')}"
                            )
                            data = _r2_get_bytes(client, bucket, key)
                            if data is None:
                                fetch_failures.append(key)
                                continue
                            # Re-apply the degree its author saved (auto-default
                            # if no sidecar); the model sees the downscaled copy
                            # while OCR (below) still reads full-res ``data``.
                            _istem = img_name.rsplit(".", 1)[0]
                            _sc = _r2_get_text(
                                client, bucket,
                                _r2_key(sid, "user_inputs", "images",
                                        _istem + ".compression.json"),
                            )
                            _deg = degree_from_json_text(_sc) if _sc else None
                            b64 = encode_image_bytes(data, _deg)
                            image_blocks.append(
                                make_image_block(b64, provider)
                            )
                            image_paths.append(full_key)
                            image_refs.append((stem, full_key))
                            if extract_text:
                                ocr_items.append((full_key, data))

            session_records.append({
                "session_id": sid,
                "not_found": False,
                "queries_text": queries_text,
                "image_notes": image_notes,
                "image_refs": image_refs,
                "fetch_failures": fetch_failures,
            })

        # Render + trim
        xml, n_trimmed = _trim_to_cap(
            session_records,
            images_included=images_flag,
            cap_tokens=_MAX_RESPONSE_TOKENS,
        )

        # OCR (gated, opt-in for this tool): read the text on the fetched
        # past-session images via the shared OCR entry point and append it
        # as a trailing <ocr_text> element.  Returns [] (no-op) when OCR
        # is disabled or extract_text is False; non-fatal on engine error.
        ocr_lines = ocr_summary_if_enabled(ocr_items, extract_text)
        if ocr_lines:
            xml = (
                xml
                + "\n<ocr_text>\n"
                + _wrap_cdata("\n\n".join(ocr_lines))
                + "\n</ocr_text>"
            )

        # rag_queries log
        returned_sids = [
            r["session_id"] for r in session_records
            if not r.get("not_found") and not r.get("trimmed")
        ]
        not_found_count = sum(
            1 for r in session_records if r.get("not_found")
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        _log_to_rag_queries(
            caller_agent=caller_agent,
            session_ids=session_ids,
            images_flag=images_flag,
            n_returned=len(returned_sids),
            returned_session_ids=returned_sids,
            skipped_count=not_found_count,
            truncated_anchors=n_trimmed,
            latency_ms=latency_ms,
            error_message=None,
        )
        return xml, image_blocks, image_paths
    except Exception as exc:  # noqa: BLE001
        # Hard error before / during retrieval.  Build a minimal
        # error envelope; rag_queries logs the failure.
        error_message = f"{type(exc).__name__}: {exc}"
        logger.warning(
            f"[retrieve_user_inputs]  unhandled error: {error_message}",
            exc_info=True,
        )
        xml = (
            f"<retrieve_user_inputs_meta "
            f"sessions_requested={_attr(len(session_ids))} "
            f"sessions_returned=\"0\" "
            f"images_included={_attr(str(images_flag).lower())} "
            f"truncated=\"false\" "
            f"error={_attr(error_message)}/>\n"
            f"<error>{escape(error_message)}</error>"
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        _log_to_rag_queries(
            caller_agent=caller_agent,
            session_ids=session_ids,
            images_flag=images_flag,
            n_returned=0,
            returned_session_ids=[],
            skipped_count=len(session_ids),
            truncated_anchors=0,
            latency_ms=latency_ms,
            error_message=error_message,
        )
        return xml, [], []


def make_retrieve_user_inputs_tool(caller_agent: str):
    """Factory: returns a fresh ``@tool``-decorated stub for *caller_agent*.

    The LLM-facing schema has NO ``caller_agent`` parameter — the
    caller is baked into a closure variable at bind time so the LLM
    cannot spoof its identity.  Phase 5E binds this per-agent in
    each chain agent's ``set_tools()``/``set_routing_tools()``.

    The returned stub returns ``""`` and relies on the dispatcher
    in ``agents/shared/retrieve_tool_dispatcher.py`` to do the real
    work (so the same tool call can also attach image content
    blocks to the next ``HumanMessage`` via
    ``append_pending_images``).
    """
    # ``caller_agent`` is captured but currently used only at
    # dispatcher time (the dispatcher reads ``agent_key`` from the
    # caller).  The closure is kept anyway so future per-agent
    # behaviour (e.g. caller-specific docstring tweaks, an ACL
    # layer) can hook in here.
    _caller = caller_agent

    # The ``extract_text`` OCR flag is present ONLY when OCR is enabled,
    # so the agent never sees it when OCR is off.  For this tool it
    # defaults to False (past-session image text was usually already
    # captured when that session ran).
    if ocr_access.is_enabled_for(caller_agent):
        @tool
        @generic_tool("Retrieve user inputs")
        def retrieve_user_inputs(
            sessions_ID_list: list[str],
            images_flag: bool = False,
            extract_text: bool = False,
        ) -> str:
            """Retrieve text and (optionally) image artefacts for past saved sessions.

            Use AFTER ``database_search`` has surfaced a session_id that
            looks worth a deeper read.  Returns the session's user-supplied
            text (``user_query.txt``) and per-image notes.  When
            ``images_flag=True`` it also attaches the user-provided image
            bytes as content blocks on the next message.

            Args:
                sessions_ID_list: list of session_id strings to retrieve
                    (e.g. from a database_search response's
                    ``<session id="..."/>`` elements).
                images_flag: when True, attach image bytes; when False,
                    only the text content (image notes are always
                    included if any images exist for that session).
                extract_text: when True (and images_flag=True), the text
                    written on the fetched past-session images is ALSO
                    read for you by OCR and returned in the response —
                    machine-recognised, so verify against the image.
                    Defaults to False: opt in only when you specifically
                    need to re-read a past image's text.

            Returns text-only XML.  Image bytes, when requested, attach
            separately as content blocks on the next message.
            """
            # Real work happens in the dispatcher (it has access to the
            # agent's messages buffer + provider info).  This stub just
            # satisfies langchain's @tool contract.
            return ""
    else:
        @tool
        @generic_tool("Retrieve user inputs")
        def retrieve_user_inputs(
            sessions_ID_list: list[str],
            images_flag: bool = False,
        ) -> str:
            """Retrieve text and (optionally) image artefacts for past saved sessions.

            Use AFTER ``database_search`` has surfaced a session_id that
            looks worth a deeper read.  Returns the session's user-supplied
            text (``user_query.txt``) and per-image notes.  When
            ``images_flag=True`` it also attaches the user-provided image
            bytes as content blocks on the next message.

            Args:
                sessions_ID_list: list of session_id strings to retrieve
                    (e.g. from a database_search response's
                    ``<session id="..."/>`` elements).
                images_flag: when True, attach image bytes; when False,
                    only the text content (image notes are always
                    included if any images exist for that session).

            Returns text-only XML.  Image bytes, when requested, attach
            separately as content blocks on the next message.
            """
            # Real work happens in the dispatcher (it has access to the
            # agent's messages buffer + provider info).  This stub just
            # satisfies langchain's @tool contract.
            return ""

    return retrieve_user_inputs
