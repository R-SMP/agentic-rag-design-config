"""retrieve_attempt — DC-specific R2-backed attempt-scoped retrieval tool.

When a chain agent calls ``retrieve_attempt(attempts_ID_list,
images_flag)``, the tool:

1. Resolves each global attempt_id (BIGSERIAL ``dc_attempts.attempt_id``)
   against Postgres to recover ``(session_id, attempt_label, has_renders)``.
   The ``attempt_label`` is the ``<TS>_<NNN>_<slug>`` folder name; the
   tool extracts the 3-digit ``NNN`` to assemble the Phase 5A R2 key.
2. For each resolved attempt, fetches from R2 (key prefix
   ``<session_id>/attempts/<NNN>__<global_id>/``):
     * ``description.txt`` — per-attempt narrative.
     * ``parameters.json`` — JSON parameter snapshot.
     * ``render_isometric.png`` / ``render_top.png`` / ``render_side.png``
       — filtered by the three workflow flags
       (``RETRIEVE_ATTEMPT_INCLUDE_{ISO,TOP,SIDE}_VIEW``) AND gated by
       ``has_renders=TRUE`` AND gated by ``images_flag=TRUE``.
3. Assembles an XML response (``<retrieve_attempt_meta/>`` + per-attempt
   blocks); trims attempts from the end of the input list when the
   response exceeds ``RETRIEVE_MAX_RESPONSE_TOKENS``.
4. Logs the call to ``rag_queries`` with
   ``tool_name='retrieve_attempt'`` (schema v7).
5. Returns ``(xml, image_blocks, image_paths)`` to the dispatcher.

The ``@tool``-decorated public stub returns ``""`` — the dispatcher in
``agents/shared/retrieve_tool_dispatcher.py`` intercepts and runs the
real ``_run_retrieve_attempt`` function below.  Same load_input_images
pattern as ``retrieve_user_inputs``.

Architecture references
-----------------------
* Architecture doc §4 (retrieval contract) + Phase 5A/5C design lock.
* W30 — R2 path layout: Phase 5A key shape
  ``<sid>/attempts/<NNN>__<global_id>/<original_filename>``.
* W33 — DBa per-agent gating + RAG_ENABLED master switch (same gates
  as database_search and retrieve_user_inputs).
"""

from __future__ import annotations

import base64
import logging
import re
import time
from typing import Any
from xml.sax.saxutils import escape, quoteattr

import tiktoken
from langchain_core.tools import tool
from psycopg.types.json import Json

from agents.shared import postgres_pool, r2_uploader
from agents.shared.agent_activity import generic_tool
from agents.shared.llm_provider import make_image_block
from workflow_settings import settings as workflow_settings

logger = logging.getLogger("propeller_agent")


# ============================================================
# Module-level settings refs
# ============================================================
_MAX_RESPONSE_TOKENS = int(workflow_settings.RETRIEVE_MAX_RESPONSE_TOKENS)

# Render-view inclusion policy, ordered.  Isometric first since it
# is the single most informative single-view render for propeller
# geometry; top and side follow.  The render_views_in_scope meta
# attribute joins the enabled names in this order.
_RENDER_VIEWS = (
    ("isometric", "RETRIEVE_ATTEMPT_INCLUDE_ISOMETRIC_VIEW"),
    ("top",       "RETRIEVE_ATTEMPT_INCLUDE_TOP_VIEW"),
    ("side",      "RETRIEVE_ATTEMPT_INCLUDE_SIDE_VIEW"),
)

# Maps view name → R2 filename (matches ATTEMPT_ARTEFACT_WHITELIST in
# r2_uploader.py).  Filenames stay as the originals in Phase 5A
# (no <sid>__<NNN>__ rename).
_RENDER_FILES = {
    "isometric": "render_isometric.png",
    "top":       "render_top.png",
    "side":      "render_side.png",
}

# cl100k_base matches database_search and retrieve_user_inputs for
# consistency in observability data.
_TOKENIZER = tiktoken.get_encoding("cl100k_base")

# attempt_label format is ``<YYYYMMDD>_<HHMMSS>_<NNN>_<slug>``.  This
# regex captures the 3+ digit NNN.  Robust to slug content (slugs
# may themselves contain underscores or digits).
_ATTEMPT_LABEL_RE = re.compile(r"^\d+_\d+_(\d+)_")


# ============================================================
# Render-view policy
# ============================================================
def _views_in_scope() -> list[str]:
    """Return the ordered list of render-view names the workflow enables."""
    out: list[str] = []
    for view, attr in _RENDER_VIEWS:
        if bool(getattr(workflow_settings, attr, False)):
            out.append(view)
    return out


# ============================================================
# Postgres helper
# ============================================================
def _resolve_global_attempt_ids(
    global_ids: list[int],
) -> dict[int, dict[str, Any] | None]:
    """Look up each global_id's (session_id, NNN, has_renders).

    Returns a dict mapping each requested global_id to either
    ``{"session_id": ..., "nnn": ..., "has_renders": ...}`` (when the
    row exists in ``dc_attempts``) or ``None`` (when the row is
    missing).  NNN is extracted from ``attempt_label`` via the
    ``<TS>_<NNN>_<slug>`` regex; rows whose label does not match
    (defensive) also map to ``None``.
    """
    if not global_ids:
        return {}
    out: dict[int, dict[str, Any] | None] = {gid: None for gid in global_ids}
    if not postgres_pool.is_enabled():
        return out
    with postgres_pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT attempt_id, session_id, attempt_label, has_renders "
                "FROM dc_attempts "
                "WHERE attempt_id = ANY(%s)",
                (global_ids,),
            )
            for gid, session_id, attempt_label, has_renders in cur.fetchall():
                m = _ATTEMPT_LABEL_RE.match(attempt_label or "")
                if not m:
                    logger.warning(
                        f"[retrieve_attempt]  attempt_label "
                        f"{attempt_label!r} does not match the expected "
                        f"<TS>_<NNN>_<slug> pattern; skipping global_id "
                        f"{gid}."
                    )
                    continue
                out[gid] = {
                    "session_id": session_id,
                    "nnn": m.group(1),
                    "has_renders": bool(has_renders),
                }
    return out


# ============================================================
# R2 helpers (parallel to retrieve_user_inputs)
# ============================================================
def _r2_key(*parts: str) -> str:
    """Build a slash-joined R2 key (prefix-free; client adds prefix)."""
    return "/".join(p.strip("/") for p in parts if p)


def _r2_bucket_and_client() -> tuple[str | None, Any]:
    if not r2_uploader.is_enabled():
        return None, None
    client = r2_uploader._client()  # noqa: SLF001
    if client is None:
        return None, None
    return r2_uploader._env("R2_BUCKET_NAME"), client  # noqa: SLF001


def _r2_get_text(client, bucket: str, key: str) -> str | None:
    full_key = f"{r2_uploader._key_prefix()}{key.lstrip('/')}"  # noqa: SLF001
    try:
        resp = client.get_object(Bucket=bucket, Key=full_key)
        return resp["Body"].read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        logger.info(
            f"[retrieve_attempt]  R2 GET miss for {full_key}: "
            f"{type(exc).__name__}: {exc}"
        )
        return None


def _r2_get_bytes(client, bucket: str, key: str) -> bytes | None:
    full_key = f"{r2_uploader._key_prefix()}{key.lstrip('/')}"  # noqa: SLF001
    try:
        resp = client.get_object(Bucket=bucket, Key=full_key)
        return resp["Body"].read()
    except Exception as exc:  # noqa: BLE001
        logger.info(
            f"[retrieve_attempt]  R2 GET miss for {full_key}: "
            f"{type(exc).__name__}: {exc}"
        )
        return None


# ============================================================
# XML build + trim
# ============================================================
def _attr(value: Any) -> str:
    return quoteattr(str(value))


def _wrap_cdata(text: str) -> str:
    if "]]>" in text:
        text = text.replace("]]>", "]]]]><![CDATA[>")
    return f"<![CDATA[{text}]]>"


def _build_attempt_block(
    global_id: int,
    nnn: str,
    session_id: str,
    description_text: str | None,
    parameters_text: str | None,
    render_refs: list[tuple[str, str]],  # (view_name, r2_key)
    fetch_failures: list[str],
) -> str:
    """Render one <attempt> block."""
    parts: list[str] = []
    parts.append(
        f"<attempt id={_attr(global_id)} nnn={_attr(nnn)} "
        f"session_id={_attr(session_id)}>"
    )
    if description_text is None:
        parts.append(
            f"  <missing path={_attr(f'{session_id}/attempts/{nnn}__{global_id}/description.txt')}/>"
        )
    else:
        parts.append("  <description>")
        parts.append("    " + _wrap_cdata(description_text))
        parts.append("  </description>")
    if parameters_text is None:
        parts.append(
            f"  <missing path={_attr(f'{session_id}/attempts/{nnn}__{global_id}/parameters.json')}/>"
        )
    else:
        parts.append("  <parameters>")
        parts.append("    " + _wrap_cdata(parameters_text))
        parts.append("  </parameters>")
    if render_refs:
        parts.append("  <renders>")
        for view, key in render_refs:
            parts.append(
                f"    <render name={_attr(view)} key={_attr(key)}/>"
            )
        parts.append("  </renders>")
    for failure_key in fetch_failures:
        parts.append(f"  <missing path={_attr(failure_key)}/>")
    parts.append("</attempt>")
    return "\n".join(parts)


def _build_xml(
    attempt_records: list[dict],
    images_included: bool,
    render_views_in_scope: list[str],
    truncated_count: int,
) -> str:
    n_requested = sum(
        1 for r in attempt_records if r.get("present_in_meta", True)
    )
    n_returned = sum(
        1 for r in attempt_records
        if r.get("present_in_meta", True)
        and not r.get("not_found", False)
        and not r.get("trimmed", False)
    )
    parts: list[str] = [
        f"<retrieve_attempt_meta "
        f"attempts_requested={_attr(n_requested)} "
        f"attempts_returned={_attr(n_returned)} "
        f"images_included={_attr(str(images_included).lower())} "
        f"render_views_in_scope={_attr(','.join(render_views_in_scope))} "
        f"truncated={_attr(str(truncated_count > 0).lower())}/>"
    ]
    for r in attempt_records:
        if r.get("trimmed"):
            continue
        if r.get("not_found"):
            parts.append(
                f"<attempt id={_attr(r['global_id'])} status=\"not_found\"/>"
            )
            continue
        if r.get("ignored"):
            # Session on the system-managed ignore list — see the
            # Database admin view.  Self-closing marker, no R2 /
            # Postgres fetch was performed.
            parts.append(
                f"<attempt id={_attr(r['global_id'])} status=\"ignored\"/>"
            )
            continue
        parts.append(_build_attempt_block(
            r["global_id"],
            r["nnn"],
            r["session_id"],
            r["description_text"],
            r["parameters_text"],
            r["render_refs"],
            r["fetch_failures"],
        ))
    if truncated_count > 0:
        parts.append(
            f"<truncated omitted_attempts={_attr(truncated_count)}/>"
        )
    return "\n".join(parts)


def _count_tokens(text: str) -> int:
    return len(_TOKENIZER.encode(text, disallowed_special=()))


def _trim_to_cap(
    attempt_records: list[dict],
    images_included: bool,
    render_views_in_scope: list[str],
    cap_tokens: int,
) -> tuple[str, int]:
    """Render XML and drop attempts from the END until under *cap_tokens*."""
    for r in attempt_records:
        r["trimmed"] = False
    xml = _build_xml(
        attempt_records, images_included, render_views_in_scope, 0,
    )
    if cap_tokens <= 0 or _count_tokens(xml) <= cap_tokens:
        return xml, 0
    trimmed = 0
    for r in reversed(attempt_records):
        if r.get("not_found") or r.get("ignored"):
            # Self-closing markers — trimming them yields negligible
            # savings.  Skip.
            continue
        r["trimmed"] = True
        trimmed += 1
        xml = _build_xml(
            attempt_records, images_included, render_views_in_scope, trimmed,
        )
        if _count_tokens(xml) <= cap_tokens:
            return xml, trimmed
    return xml, trimmed


# ============================================================
# rag_queries log
# ============================================================
def _log_to_rag_queries(
    *,
    caller_agent: str,
    global_attempt_ids: list[int],
    images_flag: bool,
    n_returned: int,
    returned_global_ids: list[int],
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
                        "retrieve_attempt",
                        Json({"attempts_ID_list": global_attempt_ids}),
                        len(global_attempt_ids),
                        images_flag,
                        n_returned,
                        Json([{"attempt_id": gid} for gid in returned_global_ids]),
                        skipped_count,
                        truncated_anchors,
                        latency_ms,
                        error_message,
                    ),
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"[retrieve_attempt]  rag_queries log failed: "
            f"{type(exc).__name__}: {exc}"
        )


# ============================================================
# Public surface
# ============================================================
def _run_retrieve_attempt(
    *,
    caller_agent: str,
    global_attempt_ids: list[int],
    images_flag: bool,
    provider: str = "openai",
) -> tuple[str, list[dict], list[str]]:
    """Real retrieval logic.  Called by the dispatcher.

    Returns ``(xml_str, image_blocks, image_paths)``.  ``image_blocks``
    is a list of provider-shaped image content-block dicts ready to
    attach via ``append_pending_images``.  ``image_paths`` is the
    parallel list of R2 keys used as text labels.
    """
    start = time.monotonic()
    error_message: str | None = None
    image_blocks: list[dict] = []
    image_paths: list[str] = []
    attempt_records: list[dict] = []
    render_views_in_scope = _views_in_scope()

    try:
        resolved = _resolve_global_attempt_ids(global_attempt_ids)
        bucket, client = _r2_bucket_and_client()

        # System-managed session ignore list — read fresh on every
        # tool call.  Attempts whose session_id is on the list are
        # skipped without hitting R2 — they emit a self-closing
        # <attempt id="..." status="ignored"/> marker.
        try:
            from workflow_settings.db_search_ignore_list import (
                get_ignore_list as _get_il,
            )
            _ignored_set = set(_get_il())
        except Exception:
            _ignored_set = set()

        for gid in global_attempt_ids:
            info = resolved.get(gid)
            if info is None:
                attempt_records.append({
                    "global_id": gid,
                    "not_found": True,
                })
                continue

            session_id = info["session_id"]
            nnn = info["nnn"]
            has_renders = info["has_renders"]

            if session_id in _ignored_set:
                # Session on the ignore list — skip R2 + parameter
                # fetch and emit a self-closing
                # <attempt id="..." status="ignored"/> marker.
                attempt_records.append({
                    "global_id": gid,
                    "not_found": False,
                    "ignored": True,
                    "nnn": nnn,
                    "session_id": session_id,
                })
                continue

            description_text: str | None = None
            parameters_text: str | None = None
            render_refs: list[tuple[str, str]] = []
            fetch_failures: list[str] = []

            if bucket is None or client is None:
                fetch_failures.append(
                    f"{session_id}/attempts/{nnn}__{gid}/ (R2 not configured)"
                )
            else:
                base = f"{session_id}/attempts/{nnn}__{gid}"
                description_text = _r2_get_text(
                    client, bucket, _r2_key(base, "description.txt"),
                )
                parameters_text = _r2_get_text(
                    client, bucket, _r2_key(base, "parameters.json"),
                )
                # Renders — gated by has_renders + images_flag + workflow flags
                if has_renders and images_flag and render_views_in_scope:
                    for view in render_views_in_scope:
                        filename = _RENDER_FILES[view]
                        key = _r2_key(base, filename)
                        full_key = (
                            f"{r2_uploader._key_prefix()}"  # noqa: SLF001
                            f"{key.lstrip('/')}"
                        )
                        data = _r2_get_bytes(client, bucket, key)
                        if data is None:
                            # render expected but not in R2 — emit a
                            # per-file <missing/> marker
                            fetch_failures.append(key)
                            continue
                        b64 = base64.b64encode(data).decode()
                        image_blocks.append(
                            make_image_block(b64, provider)
                        )
                        image_paths.append(full_key)
                        render_refs.append((view, full_key))

            attempt_records.append({
                "global_id": gid,
                "not_found": False,
                "nnn": nnn,
                "session_id": session_id,
                "description_text": description_text,
                "parameters_text": parameters_text,
                "render_refs": render_refs,
                "fetch_failures": fetch_failures,
            })

        # Render + trim
        xml, n_trimmed = _trim_to_cap(
            attempt_records,
            images_included=images_flag,
            render_views_in_scope=render_views_in_scope,
            cap_tokens=_MAX_RESPONSE_TOKENS,
        )

        # rag_queries log
        returned_gids = [
            r["global_id"] for r in attempt_records
            if not r.get("not_found") and not r.get("trimmed")
        ]
        not_found_count = sum(
            1 for r in attempt_records if r.get("not_found")
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        _log_to_rag_queries(
            caller_agent=caller_agent,
            global_attempt_ids=global_attempt_ids,
            images_flag=images_flag,
            n_returned=len(returned_gids),
            returned_global_ids=returned_gids,
            skipped_count=not_found_count,
            truncated_anchors=n_trimmed,
            latency_ms=latency_ms,
            error_message=None,
        )
        return xml, image_blocks, image_paths

    except Exception as exc:  # noqa: BLE001
        error_message = f"{type(exc).__name__}: {exc}"
        logger.warning(
            f"[retrieve_attempt]  unhandled error: {error_message}",
            exc_info=True,
        )
        xml = (
            f"<retrieve_attempt_meta "
            f"attempts_requested={_attr(len(global_attempt_ids))} "
            f"attempts_returned=\"0\" "
            f"images_included={_attr(str(images_flag).lower())} "
            f"render_views_in_scope={_attr(','.join(render_views_in_scope))} "
            f"truncated=\"false\" "
            f"error={_attr(error_message)}/>\n"
            f"<error>{escape(error_message)}</error>"
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        _log_to_rag_queries(
            caller_agent=caller_agent,
            global_attempt_ids=global_attempt_ids,
            images_flag=images_flag,
            n_returned=0,
            returned_global_ids=[],
            skipped_count=len(global_attempt_ids),
            truncated_anchors=0,
            latency_ms=latency_ms,
            error_message=error_message,
        )
        return xml, [], []


def make_retrieve_attempt_tool(caller_agent: str):
    """Factory: returns a fresh ``@tool``-decorated stub for *caller_agent*.

    The LLM-facing schema has NO ``caller_agent`` parameter — the
    caller is baked into a closure variable at bind time so the LLM
    cannot spoof its identity.  Phase 5E binds this per-agent in
    each chain agent's ``set_tools()``/``set_routing_tools()``.

    The returned stub returns ``""`` and relies on the dispatcher in
    ``agents/shared/retrieve_tool_dispatcher.py`` to do the real
    work (so the same tool call can also attach image content
    blocks to the next ``HumanMessage`` via
    ``append_pending_images``).
    """
    _caller = caller_agent

    @tool
    @generic_tool("Retrieve attempt")
    def retrieve_attempt(
        attempts_ID_list: list[int],
        images_flag: bool = False,
    ) -> str:
        """Retrieve description, parameters, and (optionally) renders for past attempts.

        Use AFTER ``database_search`` or ``retrieve_user_inputs`` has
        surfaced an attempt worth a deeper read.  Returns the
        attempt's description text, parameter JSON, and (when
        ``images_flag=True``) the render PNGs admitted by the
        deployed view-selection policy.

        Args:
            attempts_ID_list: list of GLOBAL attempt_id integers
                (BIGSERIAL ``dc_attempts.attempt_id`` values from
                Postgres).  Get these from the ``<available_attempts>``
                block of a ``database_search`` response — the per-session
                NNN is for human readability only; the global id is
                what this tool resolves.
            images_flag: when True, attach render PNG bytes; when
                False, the response is text-only.  The deployed
                view-selection policy (workflow settings) further
                filters which views are sent.

        Returns text-only XML.  The meta header's
        ``render_views_in_scope`` attribute lists which render views
        the deployed policy admits.  When ``images_flag=True``,
        image bytes attach separately as content blocks on the next
        message.
        """
        # Real work happens in the dispatcher; this stub satisfies
        # langchain's @tool contract.
        return ""

    return retrieve_attempt
