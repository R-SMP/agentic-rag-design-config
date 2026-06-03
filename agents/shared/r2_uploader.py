"""Cloudflare R2 mirror for the post-session database.

The Database Handler writes per-field ``.txt`` files (plus sidecar
``.meta.json`` files) under ``database/<session_id>/<agent>/<field>.txt``
inside the container.  Without an R2 mirror those files live only in
the container's writable layer and disappear on the next image
rebuild.  This module pushes them to a Cloudflare R2 bucket whose
key layout mirrors the local filesystem one-for-one.

R2 is S3-compatible: the standard boto3 S3 client works once the
``endpoint_url`` is pointed at
``https://<account_id>.r2.cloudflarestorage.com``.

Required environment
--------------------
* ``R2_ACCOUNT_ID``         — your Cloudflare account ID (e.g.
                              ``a1b2c3d4e5f6...``).  The endpoint
                              URL is derived from this.
* ``R2_ACCESS_KEY_ID``      — the R2 API token's access key.
* ``R2_SECRET_ACCESS_KEY``  — the R2 API token's secret.
* ``R2_BUCKET_NAME``        — the destination bucket name.

When ANY of the four is missing or empty, :func:`is_enabled` returns
``False`` and every uploader call becomes a no-op (with a one-line
log warning).  This is intentional: the DH save path must continue
to work locally without R2 configured.

Optional environment
--------------------
* ``R2_KEY_PREFIX``     — string prepended to every key written to the
                          bucket (no trailing slash needed; one is added
                          between the prefix and the per-session prefix).
                          Useful when several environments share a single
                          bucket — e.g. ``staging`` vs ``prod``.
* ``R2_JURISDICTION``   — Cloudflare jurisdiction for the bucket.
                          Empty / unset → standard endpoint
                          (``<account>.r2.cloudflarestorage.com``).
                          ``"eu"`` → EU endpoint
                          (``<account>.eu.r2.cloudflarestorage.com``).
                          ``"fedramp"`` → FedRAMP endpoint.  Mismatching
                          the bucket's actual jurisdiction returns
                          ``AccessDenied`` on every call — visible in the
                          R2 dashboard's "Applied to" column for the
                          token (e.g. ``my-bucket | EU``).
"""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("propeller_agent")

_REQUIRED_ENV_VARS = (
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_NAME",
)


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def is_enabled() -> bool:
    """Return True when every required env var is set and non-empty."""
    return all(_env(v) for v in _REQUIRED_ENV_VARS)


_VALID_JURISDICTIONS = ("", "eu", "fedramp")


def _endpoint_url() -> str:
    """Build the R2 S3 endpoint URL, honouring an optional jurisdiction.

    Cloudflare R2 buckets created in a jurisdiction (EU, FedRAMP) are
    NOT reachable through the standard endpoint — they require the
    jurisdiction-specific URL.  The R2 dashboard shows the bucket's
    jurisdiction next to the token's "Applied to" column
    (e.g. ``my-bucket | EU``).
    """
    account = _env("R2_ACCOUNT_ID")
    jur = _env("R2_JURISDICTION").lower()
    if jur and jur not in _VALID_JURISDICTIONS:
        logger.warning(
            f"[R2]  R2_JURISDICTION={jur!r} is not one of "
            f"{_VALID_JURISDICTIONS}; falling back to the standard "
            f"endpoint."
        )
        jur = ""
    middle = f".{jur}" if jur else ""
    return f"https://{account}{middle}.r2.cloudflarestorage.com"


def _key_prefix() -> str:
    """Optional ``R2_KEY_PREFIX``, normalised to ``"prefix/"`` or ``""``."""
    raw = _env("R2_KEY_PREFIX")
    if not raw:
        return ""
    raw = raw.strip("/")
    return f"{raw}/" if raw else ""


def _client():
    """Build a fresh boto3 S3 client pointed at the R2 endpoint.

    Returns ``None`` (and logs once) when boto3 is not importable or
    when the env vars are incomplete.  Built on demand so a Stage A
    deployment without R2 configured does not pay for the client at
    every startup.
    """
    if not is_enabled():
        return None
    try:
        import boto3  # type: ignore
        from botocore.config import Config  # type: ignore
    except Exception as exc:  # pragma: no cover - boto3 is a hard dep
        logger.warning(
            f"[R2]  boto3 import failed: {exc}; uploads disabled."
        )
        return None

    return boto3.client(
        "s3",
        endpoint_url=_endpoint_url(),
        aws_access_key_id=_env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_env("R2_SECRET_ACCESS_KEY"),
        region_name="auto",   # R2 ignores region but boto3 requires one
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 4, "mode": "standard"},
        ),
    )


# ---------------------------------------------------------------------------
# Upload helpers
# ---------------------------------------------------------------------------

def _content_type_for(path: Path) -> str:
    """Best-guess MIME type for *path*; falls back to ``text/plain``."""
    ctype, _ = mimetypes.guess_type(path.name)
    return ctype or "text/plain"


def upload_file(
    local_path: Path,
    remote_key: str,
    *,
    content_type: str | None = None,
) -> bool:
    """Upload one local file to R2.  Returns True on success.

    Best-effort: any error logs a warning and returns False so the
    caller's loop can keep going.
    """
    client = _client()
    if client is None:
        return False
    bucket = _env("R2_BUCKET_NAME")
    key = f"{_key_prefix()}{remote_key.lstrip('/')}"
    ct = content_type or _content_type_for(local_path)
    try:
        with local_path.open("rb") as fh:
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=fh.read(),
                ContentType=ct,
            )
        logger.info(f"[R2]  uploaded {key} ({local_path.name})")
        return True
    except Exception as exc:
        logger.warning(
            f"[R2]  upload failed for {local_path.name} → {key}: "
            f"{type(exc).__name__}: {exc}"
        )
        return False


def upload_bytes(
    content: bytes,
    remote_key: str,
    *,
    content_type: str = "text/plain",
) -> bool:
    """Upload an in-memory bytes payload to R2.  Returns True on success.

    Used by the Database Handler's safety-folder write path
    (``agents/database_handler/db_writer.py``), where the safety file
    has NO local representation — it is written directly to
    ``<session_id>/safety/...`` on R2 and never touches the local
    filesystem.  See architecture doc §3.5 and invariant 12.

    Best-effort: any error logs a warning and returns False so the
    caller can route to its own escalation path (e.g. log the full
    Q+A body at ERROR level so the data survives in the session log
    file).  When R2 is not configured (``is_enabled() == False``)
    this function returns False immediately with a single warning —
    no boto3 client is built.

    Parameters
    ----------
    content:
        The exact byte payload to PUT.  No transformation is applied.
    remote_key:
        Path under the bucket (and the optional ``R2_KEY_PREFIX``).
        Leading slashes are stripped.  Example::
            "ID042_20260602_140000/safety/attempt_001/BadAttempt__001.txt"
    content_type:
        S3 ``ContentType`` header.  Defaults to ``"text/plain"``
        (matches the safety-file format which is plain text).
    """
    client = _client()
    if client is None:
        return False
    bucket = _env("R2_BUCKET_NAME")
    key = f"{_key_prefix()}{remote_key.lstrip('/')}"
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        logger.info(f"[R2]  uploaded {key} ({len(content)} bytes, bytes payload)")
        return True
    except Exception as exc:
        logger.warning(
            f"[R2]  upload_bytes failed for {key}: "
            f"{type(exc).__name__}: {exc}"
        )
        return False


# Whitelist of artefact filenames inside an attempt folder that the DH
# uploads when the user identifies a specific attempt via the
# ``save_attempt_data`` tool.  ``propeller_mesh_components.obj``
# is intentionally NOT on the list (the user spec explicitly excludes
# it).  Files outside this set are ignored even if they exist.
ATTEMPT_ARTEFACT_WHITELIST: tuple[str, ...] = (
    "parameters.json",
    "propeller_mesh.obj",
    "render_isometric.png",
    "render_top.png",
    "render_side.png",
    "description.txt",
)


def upload_attempt_artefacts(
    attempt_folder: Path,
    *,
    session_id: str,
    attempt_id: str,
    global_attempt_id: int | None = None,
    whitelist: Iterable[str] = ATTEMPT_ARTEFACT_WHITELIST,
) -> tuple[list[str], list[str]]:
    """Upload the whitelisted files from one *attempt_folder* to R2.

    Key layout (Phase 5A, *global_attempt_id* provided)::

        <R2_KEY_PREFIX>/<session_id>/attempts/<NNN>__<global_id>/<original_filename>

    The ``attempts/`` subfolder encodes BOTH the per-session ``NNN``
    (first, for chronological sort within a session) and the global
    Postgres ``dc_attempts.attempt_id`` (after the ``__`` separator).
    Filenames stay as the originals (``parameters.json``,
    ``propeller_mesh.obj``, ``render_isometric.png``, …) — no
    ``<sid>__<NNN>__`` rename, because the folder already disambiguates.

    Legacy key layout (pre-Phase 5A, *global_attempt_id* omitted)::

        <R2_KEY_PREFIX>/<session_id>/attempts/<NNN>/<session_id>__<NNN>__<original_filename>

    This fallback exists only for direct test callers that have not
    been updated.  Production callers (the Database Handler) always
    pass ``global_attempt_id``.  When *global_attempt_id* is omitted
    a warning is logged.

    Returns ``(uploaded_names, missing_names)`` — both as lists of the
    *original* filenames so the caller's ToolMessage to the DH can
    distinguish "uploaded" from "absent on disk".  When R2 is not
    configured both lists are empty (with a single log warning) so the
    DH still sees an unambiguous "nothing was saved" signal and the
    cascade-drop branch fires.
    """
    if not is_enabled():
        logger.warning(
            "[R2]  not configured; skipping attempt-artefact upload "
            "for " + str(attempt_folder.resolve())
        )
        return [], list(whitelist)

    if not attempt_folder.exists() or not attempt_folder.is_dir():
        logger.warning(
            f"[R2]  attempt folder {attempt_folder.resolve()} is "
            f"missing or not a directory; nothing uploaded."
        )
        return [], list(whitelist)

    bucket = _env("R2_BUCKET_NAME")
    # NOTE: `base` is PREFIX-FREE.  ``upload_file`` is the single owner
    # of ``_key_prefix()`` — passing an already-prefixed key here would
    # double the prefix (e.g. ``web-v1/web-v1/<sid>/attempts/...``).
    #
    # Phase 5A: when ``global_attempt_id`` is provided the folder
    # encodes both NNN and the global id, and filenames stay clean.
    # Otherwise fall back to the pre-5A layout for any unupdated
    # direct caller.
    if global_attempt_id is not None:
        base = f"{session_id}/attempts/{attempt_id}__{global_attempt_id}/"
    else:
        logger.warning(
            "[R2]  upload_attempt_artefacts called without "
            "global_attempt_id — falling back to pre-5A key shape.  "
            "Production callers should always pass global_attempt_id."
        )
        base = f"{session_id}/attempts/{attempt_id}/"

    uploaded: list[str] = []
    missing: list[str] = []
    for name in whitelist:
        local = attempt_folder / name
        if not local.is_file():
            missing.append(name)
            continue
        if global_attempt_id is not None:
            key = base + name  # clean filename — folder disambiguates
        else:
            key = base + f"{session_id}__{attempt_id}__{name}"  # legacy
        if upload_file(local, key):
            uploaded.append(name)
        else:
            # The upload error path already logs; mark as missing so
            # the DH sees a coherent ToolMessage payload.
            missing.append(name)

    logger.info(
        f"[R2]  attempt-artefact upload: {len(uploaded)} uploaded, "
        f"{len(missing)} missing → "
        f"s3://{bucket}/{_key_prefix()}{base}"
    )
    return uploaded, missing


def upload_directory(
    local_dir: Path,
    remote_prefix: str,
    *,
    suffixes: Iterable[str] = (".txt",),
) -> int:
    """Upload every file under *local_dir* matching *suffixes* to R2.

    The local relative path is preserved under *remote_prefix* — so
    ``upload_directory(Path("database/ID007_..."), "ID007_.../")``
    with suffixes ``(".txt",)`` mirrors the per-agent / per-field
    layout one-for-one.

    Returns the number of files uploaded.  When R2 is not configured
    (or boto3 is missing) returns 0 immediately after one warning,
    without touching the filesystem.
    """
    if not is_enabled():
        logger.warning(
            "[R2]  not configured (missing one of R2_ACCOUNT_ID / "
            "R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET_NAME); "
            "skipping upload of " + str(local_dir.resolve())
        )
        return 0

    if not local_dir.exists() or not local_dir.is_dir():
        logger.warning(
            f"[R2]  source directory {local_dir.resolve()} is "
            f"missing or not a directory; nothing to upload."
        )
        return 0

    suffixes_lc = tuple(s.lower() for s in suffixes)
    prefix = remote_prefix.strip("/")
    if prefix:
        prefix += "/"

    uploaded = 0
    for path in sorted(local_dir.rglob("*")):
        if not path.is_file():
            continue
        if suffixes_lc and path.suffix.lower() not in suffixes_lc:
            continue
        rel = path.relative_to(local_dir).as_posix()
        key = f"{prefix}{rel}"
        if upload_file(path, key):
            uploaded += 1

    logger.info(
        f"[R2]  uploaded {uploaded} file(s) from "
        f"{local_dir.resolve()} → "
        f"s3://{_env('R2_BUCKET_NAME')}/{_key_prefix()}{prefix}"
    )
    return uploaded
