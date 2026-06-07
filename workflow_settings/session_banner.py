"""Session-start config banner.

Emitted into every new session's log as the very first content after the
``logging.FileHandler`` attaches (see ``web_app._setup_session_logger``
and ``agents.loader._setup_logger``).  The banner captures, at session
start, the full picture an operator would need months later to answer
"what was this session running with?":

  * Every public, non-callable, non-sensitive attribute of
    ``workflow_settings.settings`` (the 23 numbered flag blocks).
  * The effective per-agent LLM provider + model + source, via
    ``workflow_settings.llm_routing.read_state()``.
  * The 8 per-agent DBa flags from
    ``workflow_settings.database_access.get_all()``.
  * Presence-only (set / unset) for every sensitive env var.  We never
    log the value of API keys, passwords, secrets, tokens, invite
    codes, or any DB connection string.

A single ``__SESSION_CONFIG__={json}`` line is also emitted so
``grep '^__SESSION_CONFIG__' logs/*.log | jq`` becomes trivial for
cross-session analytics.

This module is the SINGLE source of truth for what goes into the
banner.  Both the web entry point and the REPL entry point call
:func:`write_to_logger` so a saved log from either path is comparable.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

# ----------------------------------------------------------------------
# Sensitive-data blacklist
# ----------------------------------------------------------------------
# Any settings-module attribute whose NAME contains one of these
# substrings is omitted from the banner.  This catches
# ``EMBEDDING_API_KEY`` (which silently holds the OpenAI key value at
# runtime — see ``workflow_settings.settings:271``) without needing a
# per-name allowlist.
_SENSITIVE_NAME_PATTERNS = (
    "API_KEY",
    "PASSWORD",
    "SECRET",
    "TOKEN",
    "INVITE_CODE",
)

# Env vars whose PRESENCE we want to report (never the value).
_SECRET_ENV_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "INVITE_CODE",
    "PASSWORD_DATABASE_WEB_UI",
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_NAME",
    "R2_KEY_PREFIX",
    "R2_JURISDICTION",
    "RHINO_COMPUTE_API_KEY",
    "DATABASE_URL",
    "DATABASE_PUBLIC_URL",
)


def _is_sensitive_name(name: str) -> bool:
    return any(pattern in name for pattern in _SENSITIVE_NAME_PATTERNS)


def _scan_settings_module() -> dict[str, Any]:
    """Return ``{name: value}`` for every public, non-callable,
    non-sensitive scalar attribute of ``workflow_settings.settings``.

    Filters out: leading-underscore names, callables, classes,
    submodules, and anything whose name matches the sensitive
    blacklist.  Only ``str | int | float | bool | None`` values are
    returned so the banner stays printable and the JSON tail stays
    serialisable without a custom encoder.

    Returns an empty dict when ``workflow_settings.settings`` cannot
    be imported (e.g. a syntax error landed there) so the other
    banner sections still render rather than the whole banner
    dropping to its outer-try fallback line.
    """
    try:
        from workflow_settings import settings as _S
    except Exception:
        return {}

    out: dict[str, Any] = {}
    for name in sorted(dir(_S)):
        if name.startswith("_"):
            continue
        if _is_sensitive_name(name):
            continue
        try:
            val = getattr(_S, name)
        except Exception:
            continue
        if callable(val):
            continue
        if isinstance(val, type):
            continue
        # Skip modules (submodule imports leak through dir()).
        if hasattr(val, "__file__"):
            continue
        if isinstance(val, (str, int, float, bool, type(None))):
            out[name] = val
    return out


def _scan_llm_routing() -> dict[str, Any] | None:
    """Return ``llm_routing.read_state()``'s output, or ``None`` on
    failure (so the banner survives a broken config rather than
    crashing the session)."""
    try:
        from workflow_settings.llm_routing import read_state
        return read_state()
    except Exception:
        return None


def _scan_database_access() -> dict[str, bool] | None:
    """Return the per-agent DBa flag dict from
    ``database_access.get_all()`` (pre-master-switch — pure per-agent
    state), or ``None`` on failure."""
    try:
        from workflow_settings.database_access import get_all
        return get_all()
    except Exception:
        return None


def _scan_secrets_present() -> dict[str, bool]:
    """Return ``{env_var_name: bool}`` based on os.environ presence.
    Never reads the value beyond truthiness."""
    return {
        name: bool((os.environ.get(name) or "").strip())
        for name in _SECRET_ENV_NAMES
    }


def build_banner_lines() -> list[str]:
    """Build the banner as a list of lines (no trailing newlines).
    Each line is intended to be passed to ``logger.info`` so the
    formatter's timestamp prefix lands at the start of every line.

    Order:
      1. Header marker.
      2. ``[settings.py]`` — every public, non-sensitive flag.
      3. ``[LLM routing]`` — global mode + per-agent effective config.
      4. ``[Database access]`` — per-agent DBa flag.
      5. ``[Secrets]`` — presence-only.
      6. ``[Machine-readable]`` — a single JSON line for grep + jq.
      7. End marker.
    """
    lines: list[str] = []

    settings_dict = _scan_settings_module()
    routing = _scan_llm_routing()
    dba = _scan_database_access()
    secrets = _scan_secrets_present()

    lines.append("=== SESSION CONFIG BANNER ===")
    lines.append("")

    # --- [settings.py] ---
    lines.append("[settings.py]")
    if settings_dict:
        for k in sorted(settings_dict):
            lines.append(f"  {k}: {settings_dict[k]}")
    else:
        lines.append("  (no public settings found)")
    lines.append("")

    # --- [LLM routing] ---
    lines.append("[LLM routing - effective per agent]")
    if routing:
        lines.append(f"  mode: {routing.get('mode', '?')}")
        shared = routing.get("shared", {}) or {}
        lines.append(
            f"  shared: {shared.get('provider', '?')}  "
            f"{shared.get('model', '?')}"
        )
        for agent in (routing.get("agents") or []):
            key       = str(agent.get("key", "?"))
            provider  = str(agent.get("provider", "?"))
            model     = str(agent.get("model", "?"))
            source    = str(agent.get("source", "?"))
            wired_tag = (
                "" if agent.get("wired", True) else "  (wired=False)"
            )
            lines.append(
                f"  {key:22}  {provider:10}  {model:24}  "
                f"(source: {source}){wired_tag}"
            )
    else:
        lines.append("  (could not read LLM routing)")
    lines.append("")

    # --- [Database access] ---
    lines.append("[Database access - per-agent DBa flag]")
    if dba is not None:
        for k in sorted(dba):
            lines.append(f"  {k:22}: {dba[k]}")
    else:
        lines.append("  (could not read database access flags)")
    lines.append("")

    # --- [Secrets] ---
    lines.append("[Secrets - presence only]")
    for name in _SECRET_ENV_NAMES:
        lines.append(f"  {name:26}: {'set' if secrets.get(name) else 'unset'}")
    lines.append("")

    # --- [Machine-readable] ---
    payload: dict[str, Any] = {
        "captured_at":     datetime.now(timezone.utc).isoformat(),
        "settings":        settings_dict,
        "llm_routing":     routing,
        "database_access": dba,
        "secrets_present": secrets,
    }
    lines.append("[Machine-readable]")
    lines.append(
        "__SESSION_CONFIG__="
        + json.dumps(payload, default=str, sort_keys=True)
    )

    lines.append("=== END SESSION CONFIG BANNER ===")
    return lines


def write_to_logger(logger: logging.Logger) -> None:
    """Emit the banner to ``logger`` via repeated ``logger.info`` calls.

    Best-effort: any exception here is caught and a single fallback
    line is logged instead, so a misconfigured banner can never
    prevent a session from starting.
    """
    try:
        for line in build_banner_lines():
            logger.info(line)
    except Exception as exc:
        logger.warning(
            "[banner] could not emit session config banner: "
            f"{type(exc).__name__}: {exc}"
        )
