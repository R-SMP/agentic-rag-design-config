"""Helpers shared by the two R2-backed retrieval tools.

``retrieve_user_inputs`` and ``retrieve_attempt`` are near-twins: both
resolve ids, fetch artefacts from R2, materialise them into a local
``_retrieved`` folder, list that folder, and print text.  Twelve helpers
were defined identically (or near-identically) in both files.  They live
here now, so the next fix to one is a fix to both.

That mattered concretely: the ``dest``-unbound bug fixed in
``retrieve_attempt`` on 2026-08-20 existed because the pattern was written
once and then copied into the second tool by hand.

WHAT IS DELIBERATELY *NOT* SHARED
---------------------------------
Two helpers stay duplicated on purpose; this is a decision, not an
oversight:

* ``_build_xml`` renders genuinely different documents -- ``<session>``
  blocks with user queries and images, versus ``<attempt>`` blocks with
  parameters and renders.  There is no shared shape to factor out.
* ``_trim_to_cap`` runs the SAME loop in both tools, but differs only in
  which ``_build_xml`` it calls.  Sharing it means injecting a render
  callback, which trades ~30 duplicated-but-obvious lines for indirection
  in the one function whose whole job is "keep shrinking until it fits".
  It should stay readable top-to-bottom.

THE ``tag`` ARGUMENT
--------------------
Several helpers log.  The two tools are told apart in the session log by
their prefix -- ``[retrieve_user_inputs]`` / ``[retrieve_attempt]`` -- and
that distinction is worth keeping even when the code is not duplicated, so
the callers pass their own tag.

CALL SITES ARE UNCHANGED
------------------------
Each tool keeps a thin private wrapper under the original name and
signature (``_r2_get_text(client, bucket, key)`` and friends).  That keeps
every call site untouched, and keeps the offline behavioural harnesses
working: they ast-extract functions BY NAME and stub at the I/O boundary.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from xml.sax.saxutils import quoteattr

import tiktoken
from psycopg.types.json import Json

from agents.shared import postgres_pool
from agents.shared import r2_uploader

logger = logging.getLogger("propeller_agent")


# ============================================================
# Local retrieval cache
# ============================================================
RETRIEVED_SUBDIR = "_retrieved"


def retrieved_dir(root: Path, key: Any) -> Path:
    """``<root>/_retrieved/<key>`` — one retrieved item's local folder.

    The two callers pass different roots and key types, and each keeps its
    own wrapper with its own rationale, because the reasons differ and both
    are worth reading at the call site.
    """
    return root / RETRIEVED_SUBDIR / str(key)


def folder_listing(dest: Path) -> list[tuple[str, int]]:
    """``(name, size)`` for every file in *dest*, name-sorted."""
    if not dest.is_dir():
        return []
    return sorted(
        (f.name, f.stat().st_size) for f in dest.iterdir() if f.is_file()
    )


def write_artefact(dest: Path, name: str, data: bytes, *, tag: str) -> None:
    """Write one fetched artefact into the cache folder.  Best-effort."""
    try:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / name).write_bytes(data)
    except OSError as exc:
        logger.warning("[%s]  could not write %s: %s", tag, dest / name, exc)


def read_local(dest: Path, name: str) -> str | None:
    """Read a cached text artefact back, or None when absent/unreadable."""
    f = dest / name
    if not f.is_file():
        return None
    try:
        return f.read_text(encoding="utf-8")
    except OSError:
        return None


# ============================================================
# R2 access
# ============================================================
def r2_key(*parts: str) -> str:
    """Build a slash-joined R2 key (prefix-free; client adds prefix)."""
    return "/".join(p.strip("/") for p in parts if p)


def r2_bucket_and_client() -> tuple[str | None, Any]:
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


def _full_key(key: str) -> str:
    return f"{r2_uploader._key_prefix()}{key.lstrip('/')}"  # noqa: SLF001


def r2_get_text(client, bucket: str, key: str, *, tag: str) -> str | None:
    """GET *key* from R2 and decode as UTF-8.  None on miss / error."""
    full_key = _full_key(key)
    try:
        resp = client.get_object(Bucket=bucket, Key=full_key)
        return resp["Body"].read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 — R2 surfaces many error classes
        logger.info(
            f"[{tag}]  R2 GET miss for {full_key}: "
            f"{type(exc).__name__}: {exc}"
        )
        return None


def r2_get_bytes(client, bucket: str, key: str, *, tag: str) -> bytes | None:
    """GET *key* from R2 and return the raw bytes.  None on miss / error."""
    full_key = _full_key(key)
    try:
        resp = client.get_object(Bucket=bucket, Key=full_key)
        return resp["Body"].read()
    except Exception as exc:  # noqa: BLE001
        logger.info(
            f"[{tag}]  R2 GET miss for {full_key}: "
            f"{type(exc).__name__}: {exc}"
        )
        return None


# ============================================================
# XML escaping + token accounting
# ============================================================
# cl100k_base is the tokenizer used by the GPT-4 family and
# text-embedding-3-large; matches database_search's token-cap accounting
# so the observability data is comparable across all three tools.
_TOKENIZER = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_TOKENIZER.encode(text, disallowed_special=()))


def attr(value: Any) -> str:
    """Render *value* as an XML attribute (already quoted)."""
    return quoteattr(str(value))


def wrap_cdata(text: str) -> str:
    """Wrap *text* in a CDATA section, splitting if it contains ``]]>``."""
    # CDATA cannot contain the literal "]]>" — split into multiple
    # sections if it does (rare for user prose).
    if "]]>" in text:
        text = text.replace("]]>", "]]]]><![CDATA[>")
    return f"<![CDATA[{text}]]>"


# ============================================================
# rag_queries observability log
# ============================================================
def log_to_rag_queries(
    *,
    caller_agent: str,
    tool_name: str,
    params_key: str,
    requested_ids: list,
    returned_ids: list,
    returned_id_key: str,
    images_flag: bool,
    n_returned: int,
    skipped_count: int,
    truncated_anchors: int,
    latency_ms: int,
    error_message: str | None,
    tag: str,
) -> None:
    """Best-effort INSERT into ``rag_queries``.  Never raises.

    The four values that differ between the two tools are arguments:
    *tool_name*, the *params_key* naming the tool's id argument, the
    *returned_id_key* used inside ``returned_anchor_ids``, and the log
    *tag*.  Everything else is one shared statement.
    """
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
                        tool_name,
                        Json({params_key: requested_ids}),
                        len(requested_ids),
                        images_flag,
                        n_returned,
                        Json([{returned_id_key: i} for i in returned_ids]),
                        skipped_count,
                        truncated_anchors,
                        latency_ms,
                        error_message,
                    ),
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"[{tag}]  rag_queries log failed: "
            f"{type(exc).__name__}: {exc}"
        )
