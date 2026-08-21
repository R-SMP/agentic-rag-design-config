"""retrieve_user_inputs — DC-specific R2-backed retrieval tool.

When a chain agent calls ``retrieve_user_inputs(sessions_ID_list)``,
the tool:

1. Validates each session_id against the Postgres ``sessions`` table
   (and fetches each existing session's ``user_provided_images`` bool).
2. Materialises that session's user inputs into
   ``inputs/_retrieved/<sid>/`` — the UII's ``extracted_inputs.txt``,
   the raw ``queries.txt``, every reference image at FULL resolution,
   each image's ``_note.txt`` description, and each image's
   ``.compression.json`` degree sidecar (so ``view_images`` applies the
   degree the image's own author chose).  A folder already populated is
   served straight from disk: the artefacts are immutable, so a
   re-retrieval by any agent costs nothing and reads identically.
3. Assembles an XML response (``<retrieve_user_inputs_meta/>`` +
   per-session blocks) naming every local path; trims sessions from the
   end of the input list when the response exceeds
   ``RETRIEVE_MAX_RESPONSE_TOKENS``.
4. Logs the call to ``rag_queries`` with
   ``tool_name='retrieve_user_inputs'`` (schema v7).
5. Returns the XML string.

NOTHING is attached to the caller's context — not one image byte.
The agent reads the paths and decides what is worth looking at;
``view_images`` does the looking, and can place a retrieved image side by
side with any other.  The ``@tool``-decorated public stub returns ``""``
— the dispatcher in ``agents/shared/retrieve_tool_dispatcher.py``
intercepts and runs the real ``_run_retrieve_user_inputs`` below.

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
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from langchain_core.tools import tool

from agents.shared import postgres_pool
from agents.shared.agent_activity import generic_tool
from agents.shared import r2_uploader
from tools import retrieval_common
from config import USER_INPUTS_DIR
from workflow_settings import settings as workflow_settings

logger = logging.getLogger("propeller_agent")

# Log prefix: the two retrieve tools are told apart in the session
# log by this, which is why the shared helpers take a ``tag``.
_TAG = "retrieve_user_inputs"


# ============================================================
# Module-level settings refs
# ============================================================
_MAX_RESPONSE_TOKENS = int(workflow_settings.RETRIEVE_MAX_RESPONSE_TOKENS)


# Whitelist of image suffixes considered for retrieval.  Mirrors the
# pairing convention enforced by the Receptionist (case-insensitive).
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")


# ============================================================
# Local retrieval cache
# ============================================================
_RETRIEVED_SUBDIR = "_retrieved"


def _retrieved_dir(session_id: str) -> Path:
    """Local folder holding one retrieved session's user inputs.

    Sits BESIDE ``input_images/`` rather than inside it, so nothing that
    walks the live inputs can mistake a retrieved file for one the user
    uploaded this session.  Every ``inputs/`` walker in the system goes
    through ``file_utils.list_files``, which is non-recursive and
    files-only, so a subdirectory here is invisible to all of them.
    """
    return retrieval_common.retrieved_dir(USER_INPUTS_DIR, session_id)


def _folder_listing(dest: Path) -> list[tuple[str, int]]:
    """``(name, size)`` for every file in *dest*, name-sorted."""
    return retrieval_common.folder_listing(dest)


def _write_artefact(dest: Path, name: str, data: bytes) -> None:
    """Write one fetched artefact into the cache folder.  Best-effort."""
    retrieval_common.write_artefact(dest, name, data, tag=_TAG)


def _read_local(dest: Path, name: str) -> str | None:
    """Read a cached text artefact back, or None when absent/unreadable."""
    return retrieval_common.read_local(dest, name)


def _local_images(
    dest: Path,
) -> tuple[list[tuple[str, str, str | None]], list[tuple[str, str]]]:
    """Re-read a cached folder into ``(images, orphan_notes)``.

    ``images`` is ``(stem, absolute path, note text or None)`` — the
    note is optional, the path never is.  ``orphan_notes`` is
    ``(stem, text)`` for any ``_note.txt`` whose image is not in the folder.
    """
    if not dest.is_dir():
        return [], []
    files = [f for f in sorted(dest.iterdir()) if f.is_file()]
    stems: set[str] = set()
    images: list[tuple[str, str, str | None]] = []
    for f in files:
        if f.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        stems.add(f.stem)
        images.append((f.stem, str(f.resolve()),
                       _read_local(dest, f"{f.stem}_note.txt")))
    orphans: list[tuple[str, str]] = []
    for f in files:
        if not f.name.lower().endswith("_note.txt"):
            continue
        stem = f.name[: -len("_note.txt")]
        if stem in stems:
            continue
        text = _read_local(dest, f.name)
        if text is not None:
            orphans.append((stem, text))
    return images, orphans


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
    return retrieval_common.r2_key(*parts)


def _r2_bucket_and_client() -> tuple[str | None, Any]:
    """``(bucket_name, boto3_client)``, or ``(None, None)`` when R2 is off."""
    return retrieval_common.r2_bucket_and_client()  # noqa: SLF001


def _r2_get_text(client, bucket: str, key: str) -> str | None:
    """GET *key* from R2 and decode as UTF-8.  None on miss / error."""
    return retrieval_common.r2_get_text(client, bucket, key, tag=_TAG)


def _r2_get_bytes(client, bucket: str, key: str) -> bytes | None:
    """GET *key* from R2 and return the raw bytes.  None on miss / error."""
    return retrieval_common.r2_get_bytes(client, bucket, key, tag=_TAG)


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
    return retrieval_common.attr(value)


def _wrap_cdata(text: str) -> str:
    """Wrap *text* in a CDATA section, splitting if it contains ``]]>``."""
    return retrieval_common.wrap_cdata(text)


def _build_session_block(
    session_id: str,
    extraction_text: str | None,
    queries_text: str | None,
    images: list[tuple[str, str, str | None]],   # (name, local path, note|None)
    orphan_notes: list[tuple[str, str]],
    fetch_failures: list[str],
    folder: str | None = None,
    listing: list[tuple[str, int]] | None = None,
) -> str:
    """Render one <session> block."""
    parts: list[str] = []
    parts.append(f"<session id={_attr(session_id)}>")
    if extraction_text is not None:
        # The UII's interpreted extraction is the primary text: already
        # structured, so a reading agent does not re-derive it from prose.
        # queries.txt stays on disk and is listed in <folder> below.
        parts.append("  <extracted_inputs>")
        parts.append("    " + _wrap_cdata(extraction_text))
        parts.append("  </extracted_inputs>")
    else:
        # Sessions archived before extractions were shipped to R2 have none.
        # Say so, then fall back to the raw text, so one call is still
        # useful for the whole pre-existing corpus.
        parts.append(
            "  <missing path={} note={}/>".format(
                _attr(f"{session_id}/user_inputs/extracted_inputs.txt"),
                _attr("no extraction was archived for this session; "
                      "the raw user text is given below instead"),
            )
        )
        if queries_text is None:
            parts.append(
                f"  <missing path={_attr(f'{session_id}/user_inputs/queries.txt')}/>"
            )
        else:
            parts.append("  <user_query>")
            parts.append("    " + _wrap_cdata(queries_text))
            parts.append("  </user_query>")
    if images or orphan_notes:
        parts.append("  <images>")
        for name, path, note_text in images:
            if note_text is None:
                # No note was written for this image.  The PATH is reported
                # regardless: it is what ``view_images`` needs, and an image
                # with no description is still worth looking at.
                parts.append(
                    f"    <image name={_attr(name)} path={_attr(path)}/>"
                )
                continue
            parts.append(f"    <image name={_attr(name)} path={_attr(path)}>")
            parts.append("      <note>")
            parts.append("        " + _wrap_cdata(note_text))
            parts.append("      </note>")
            parts.append("    </image>")
        for name, text in orphan_notes:
            # A note whose image is absent.  Rare (the Receptionist enforces
            # pairing) but reported rather than silently dropped.
            parts.append(f"    <note name={_attr(name)} orphan=\"true\">")
            parts.append("      " + _wrap_cdata(text))
            parts.append("    </note>")
        parts.append("  </images>")
    if folder:
        # The full set of user inputs, materialised locally.  Every file is
        # addressable by ``view_images``; the agent picks what to look at.
        parts.append(f"  <folder path={_attr(folder)}>")
        for name, size in (listing or []):
            parts.append(f"    <file name={_attr(name)} bytes={_attr(size)}/>")
        parts.append("  </folder>")
    for failure_key in fetch_failures:
        # Catch-all marker for any other unexpected fetch miss
        # (kept separate from the specific markers above so an operator
        # can distinguish the failure mode).
        parts.append(f"  <missing path={_attr(failure_key)}/>")
    parts.append("</session>")
    return "\n".join(parts)


def _build_xml(
    session_records: list[dict],
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
            r["extraction_text"],
            r["queries_text"],
            r["images"],
            r["orphan_notes"],
            r["fetch_failures"],
            r.get("folder"),
            r.get("listing"),
        ))
    if truncated_count > 0:
        parts.append(
            f"<truncated omitted_sessions={_attr(truncated_count)}/>"
        )
    return "\n".join(parts)


def _count_tokens(text: str) -> int:
    return retrieval_common.count_tokens(text)


def _trim_to_cap(
    session_records: list[dict],
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
    xml = _build_xml(session_records, truncated_count=0)
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
        xml = _build_xml(session_records, truncated_count=trimmed)
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
    retrieval_common.log_to_rag_queries(
        caller_agent=caller_agent,
        tool_name="retrieve_user_inputs",
        params_key="sessions_ID_list",
        requested_ids=session_ids,
        returned_ids=returned_session_ids,
        returned_id_key="session_id",
        images_flag=images_flag,
        n_returned=n_returned,
        skipped_count=skipped_count,
        truncated_anchors=truncated_anchors,
        latency_ms=latency_ms,
        error_message=error_message,
        tag=_TAG,
    )


# ============================================================
# Public surface
# ============================================================
def _run_retrieve_user_inputs(
    *,
    caller_agent: str,
    session_ids: list[str],
) -> str:
    """Real retrieval logic.  Called by the dispatcher.

    Returns the XML string.  Every artefact is materialised under
    ``inputs/_retrieved/<session_id>/`` and referenced there BY PATH;
    nothing is attached to the model's context.
    """
    start = time.monotonic()
    error_message: str | None = None
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

            extraction_text: str | None = None
            queries_text: str | None = None
            images: list[tuple[str, str, str | None]] = []
            orphan_notes: list[tuple[str, str]] = []
            fetch_failures: list[str] = []

            # Bound before any branching: the record below reads it
            # unconditionally.  Same rule as retrieve_attempt, where binding
            # it inside one branch cost an UnboundLocalError.
            dest = _retrieved_dir(sid)

            if dest.is_dir() and any(dest.iterdir()):
                # Already fetched this session — by THIS agent or any
                # other.  Immutable artefacts, so serve from disk whatever
                # R2's state is.  Nothing in the response says "cached": it
                # reads identically either way, deliberately, so an agent
                # never has to reason about cache state.
                extraction_text = _read_local(dest, "extracted_inputs.txt")
                queries_text = _read_local(dest, "queries.txt")
                images, orphan_notes = _local_images(dest)
            elif bucket is None or client is None:
                # R2 not configured and nothing cached: emit a <missing/>
                # marker and move on.  Won't return any content.
                fetch_failures.append(
                    f"{sid}/user_inputs/ (R2 not configured)"
                )
            else:
                extraction_text = _r2_get_text(
                    client, bucket,
                    _r2_key(sid, "user_inputs", "extracted_inputs.txt"),
                )
                queries_text = _r2_get_text(
                    client, bucket,
                    _r2_key(sid, "user_inputs", "queries.txt"),
                )
                if extraction_text is not None:
                    _write_artefact(dest, "extracted_inputs.txt",
                                    extraction_text.encode("utf-8"))
                if queries_text is not None:
                    _write_artefact(dest, "queries.txt",
                                    queries_text.encode("utf-8"))
                if has_images:
                    listed = _r2_list_user_images(client, bucket, sid)
                    images_listed, notes_listed = (
                        _split_image_and_note_names(listed)
                    )
                    paired: set[str] = set()
                    for stem, img_name in images_listed:
                        key = _r2_key(
                            sid, "user_inputs", "images", img_name,
                        )
                        data = _r2_get_bytes(client, bucket, key)
                        if data is None:
                            fetch_failures.append(key)
                            continue
                        # Full resolution on disk — no downscale here.
                        # The sidecar fetched just below lands BESIDE the
                        # image, which is exactly where
                        # ``image_compression.read_degree`` looks, so
                        # ``view_images`` applies the degree the image's own
                        # author chose.
                        _write_artefact(dest, img_name, data)
                        paired.add(stem)
                        note_name = f"{stem}_note.txt"
                        note_text = _r2_get_text(
                            client, bucket,
                            _r2_key(sid, "user_inputs", "images", note_name),
                        )
                        if note_text is not None:
                            _write_artefact(dest, note_name,
                                            note_text.encode("utf-8"))
                        _sc_name = (
                            f"{img_name.rsplit('.', 1)[0]}.compression.json"
                        )
                        _sc_text = _r2_get_text(
                            client, bucket,
                            _r2_key(sid, "user_inputs", "images", _sc_name),
                        )
                        if _sc_text is not None:
                            _write_artefact(dest, _sc_name,
                                            _sc_text.encode("utf-8"))
                        images.append(
                            (stem, str((dest / img_name).resolve()), note_text)
                        )
                    for stem, note_name in notes_listed:
                        # A note with no image of its own.  Fetched too, so
                        # nothing the user wrote is silently lost.
                        if stem in paired:
                            continue
                        text = _r2_get_text(
                            client, bucket,
                            _r2_key(sid, "user_inputs", "images", note_name),
                        )
                        if text is None:
                            continue
                        _write_artefact(dest, note_name, text.encode("utf-8"))
                        orphan_notes.append((stem, text))

            session_records.append({
                "session_id": sid,
                "not_found": False,
                "extraction_text": extraction_text,
                "queries_text": queries_text,
                "images": images,
                "orphan_notes": orphan_notes,
                "fetch_failures": fetch_failures,
                "folder": str(dest.resolve()) if dest.is_dir() else None,
                "listing": _folder_listing(dest),
            })

        # Render + trim
        xml, n_trimmed = _trim_to_cap(
            session_records,
            cap_tokens=_MAX_RESPONSE_TOKENS,
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
            # The column records whether image BYTES reached the caller's
            # context.  Nothing is attached any more, so it is always
            # false — same as retrieve_attempt since step 2a.
            images_flag=False,
            n_returned=len(returned_sids),
            returned_session_ids=returned_sids,
            skipped_count=not_found_count,
            truncated_anchors=n_trimmed,
            latency_ms=latency_ms,
            error_message=None,
        )
        return xml
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
            f"truncated=\"false\" "
            f"error={_attr(error_message)}/>\n"
            f"<error>{escape(error_message)}</error>"
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        _log_to_rag_queries(
            caller_agent=caller_agent,
            session_ids=session_ids,
            images_flag=False,
            n_returned=0,
            returned_session_ids=[],
            skipped_count=len(session_ids),
            truncated_anchors=0,
            latency_ms=latency_ms,
            error_message=error_message,
        )
        return xml


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

    # OCR is NOT performed here: retrieval fetches, ``view_images`` reads.
    # That tool's own OCR flag already defaults to True for eligible
    # agents, so nothing is lost — and nothing is read that no one views.
    @tool
    @generic_tool("Retrieve user inputs")
    def retrieve_user_inputs(sessions_ID_list: list[str]) -> str:
        """Fetch a past saved session's user inputs onto local disk.

        Use AFTER ``database_search`` has surfaced a session_id worth a
        deeper read.  Everything that session's user supplied is written
        to a local folder, and the response lists that folder's contents.

        The response prints, per session: the User Input Inspector's
        structured extraction of the inputs (or, for a session archived
        before extractions were kept, the raw user text instead), and
        every reference image as an absolute local path — with its
        description when one was written, and the path alone when none
        was.

        Nothing is shown to you as an image here.  Pass any of the listed
        paths to ``view_images`` to actually look at one, alongside
        images from anywhere else if you want them side by side.

        Args:
            sessions_ID_list: session_id strings to retrieve, e.g. from a
                ``database_search`` response's ``<session id="..."/>``
                elements.
        """
        # Real work happens in the dispatcher (it has access to the
        # agent's messages buffer + provider info).  This stub just
        # satisfies langchain's @tool contract.
        return ""

    return retrieve_user_inputs
