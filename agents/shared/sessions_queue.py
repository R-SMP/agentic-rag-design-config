"""Sessions Queue — overnight benchmark runner support (pure helpers).

This module holds the framework-agnostic pieces of the "Sessions
Queue" feature: the **LLM-condition registry** (maps a queue entry's
``condition`` id onto a ``workflow_settings.llm_routing.write_updates``
payload), the **intermediate-vs-final classifier** (a cheap LLM that
decides whether a reply is the final deliverable or the system paused
mid-way waiting for a "Continue"), and **manifest / queue-progress
persistence** on the one Railway-persistent volume.

It imports NOTHING from ``web_app`` — the runner loop lives in
``web_app.py`` (it needs the module-level session globals), but every
piece that can be written and reasoned about in isolation lives here so
it stays testable and web-framework-free (same spirit as
``agents/shared/viz_bus.py``).

Persistence path.  ``previous_sessions/_sessions_queue/`` is chosen on
purpose: ``previous_sessions/`` is the only directory Railway keeps
across a container restart, and the ``_sessions_queue`` name has a
leading underscore so it never collides with a session-named archive
folder (the End-Session archive only ever writes into
``previous_sessions/<session_name>/``).  A restart therefore loses at
most the single in-flight run and can resume from the manifest.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import PREVIOUS_SESSIONS_DIR

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

QUEUE_DIR = PREVIOUS_SESSIONS_DIR / "_sessions_queue"
MANIFEST_PATH = QUEUE_DIR / "manifest.json"
PROGRESS_PATH = QUEUE_DIR / "queue-progress.json"

# Terminal run states — a run in one of these is never re-driven on a
# resume, and the queue skips straight past it.
TERMINAL_STATES = {"done", "needs_review", "failed"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# LLM-condition registry
# ---------------------------------------------------------------------------
# A queue entry names a ``condition`` id; the runner translates it into a
# ``write_updates`` payload (identical shape to what POST /api/llm-routing
# accepts) and applies it BEFORE building that run's session.  ``current``
# (and any unknown id) maps to ``None`` — leave whatever routing is
# already configured, change nothing.
#
# Representative models for the global-override conditions are the ones
# Test 1's OpenAI / Anthropic runs use; add rows here (or a full per-agent
# editor later) when more conditions are needed.  The two Subj-5 presets
# are built from ``workflow_settings.llm_defaults.PROPOSED_WORKFLOWS`` so
# they never drift from the Workflow-Settings preset buttons.

_GLOBAL_OVERRIDE_MODELS = {
    "openai":    "gpt-5.4",
    "anthropic": "claude-sonnet-4-6",
}


def _subj5_payload(preset: dict) -> dict:
    """Per-agent (mode=individual) payload from a PROPOSED_WORKFLOWS entry."""
    provider = preset["provider"]
    models: dict[str, str] = preset["models"]
    agents = [
        {"key": key, "override_provider": provider, "override_model": model}
        for key, model in models.items()
    ]
    # ``shared`` must be a valid, non-empty provider+model even though the
    # per-agent overrides govern under mode=individual — use any model
    # from the preset as the harmless fallback.
    shared_model = models.get("receptionist") or next(iter(models.values()))
    return {
        "mode":   "individual",
        "shared": {"provider": provider, "model": shared_model},
        "agents": agents,
    }


def _global_payload(provider: str, model: str) -> dict:
    """Global-override payload — force ``provider`` + ``model`` on every agent."""
    return {
        "mode":   provider,
        "shared": {"provider": provider, "model": model},
        "agents": [],
    }


def _conditions() -> "list[dict[str, Any]]":
    """Build the ordered condition list (id, label, payload).

    Built lazily so a broken/absent ``llm_defaults`` never stops the
    module importing — the runner degrades to just ``current``.
    """
    out: list[dict[str, Any]] = [
        {"id": "current", "label": "Current settings (no change)", "payload": None},
    ]
    try:
        from workflow_settings.llm_defaults import PROPOSED_WORKFLOWS
        by_id = {p.get("id"): p for p in PROPOSED_WORKFLOWS}
        if "openai" in by_id:
            out.append({
                "id": "subj5-openai",
                "label": "Subj 5 · per-agent mix (OpenAI)",
                "payload": _subj5_payload(by_id["openai"]),
            })
        if "anthropic" in by_id:
            out.append({
                "id": "subj5-anthropic",
                "label": "Subj 5 · per-agent mix (Anthropic)",
                "payload": _subj5_payload(by_id["anthropic"]),
            })
    except Exception:
        # Fall through with just the global overrides + current.
        pass
    for provider, model in _GLOBAL_OVERRIDE_MODELS.items():
        out.append({
            "id":      f"all-{provider}",
            "label":   f"Global override · All {provider.capitalize()} ({model})",
            "payload": _global_payload(provider, model),
        })
    return out


def list_conditions() -> "list[dict[str, str]]":
    """UI-facing condition list: ``[{id, label}]`` (no payloads)."""
    return [{"id": c["id"], "label": c["label"]} for c in _conditions()]


def routing_payload_for(condition_id: str) -> "dict | None":
    """The ``write_updates`` payload for ``condition_id``, or ``None`` to
    leave the routing untouched (``current`` / unknown id)."""
    cid = (condition_id or "").strip()
    for c in _conditions():
        if c["id"] == cid:
            return c["payload"]
    return None


def condition_label(condition_id: str) -> str:
    cid = (condition_id or "").strip()
    for c in _conditions():
        if c["id"] == cid:
            return c["label"]
    return cid or "current"


def known_condition_ids() -> "set[str]":
    return {c["id"] for c in _conditions()}


_CLASSIFIER_KEY_ENV = {
    "openai":    "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google":    "GOOGLE_API_KEY",
}


def classifier_key_present(provider: str) -> bool:
    """True when the API key for the classifier ``provider`` is in the env.

    Used to fail-fast at queue start: a classifier whose key is absent
    would error on the FIRST reply of EVERY run (→ needs_review), wasting
    the whole night.
    """
    env = _CLASSIFIER_KEY_ENV.get((provider or "").strip().lower())
    return bool(env and os.getenv(env, "").strip())


# ---------------------------------------------------------------------------
# Intermediate-vs-final classifier
# ---------------------------------------------------------------------------

_CLASSIFIER_SYSTEM = (
    "You are a strict classifier for a multi-agent propeller-design "
    "assistant. Given the user's request and the assistant's reply, "
    "decide whether the reply is the FINAL deliverable the user asked "
    "for, or an INTERMEDIATE result where the assistant has paused and "
    "is waiting for the user to tell it to proceed / continue to the "
    "next stage (for example: it produced the blade cross-sections and "
    "is asking whether to go on to the 3D geometry, or it is otherwise "
    "checking in before finishing).\n"
    "Answer with exactly ONE word — either FINAL or INTERMEDIATE — and "
    "nothing else."
)

_CLASSIFIER_USER = (
    "USER REQUEST:\n{query}\n\n"
    "ASSISTANT REPLY:\n{reply}\n\n"
    "Is the assistant's reply FINAL or INTERMEDIATE?"
)


def _build_classifier_llm(provider: str, model: str):
    """Construct a cheap chat model for classification.

    Reads the API key from the process environment (the same fallback
    ``llm_provider._resolve_config`` uses on Railway).  Lazy provider
    imports so this module imports cleanly where langchain is absent
    (e.g. the py3.8 worktree).  Temperature is left at the provider
    default — several current reasoning models reject an explicit
    ``temperature`` and 400 on it.
    """
    provider = (provider or "openai").strip().lower()
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, api_key=os.getenv("OPENAI_API_KEY", ""),
                          timeout=60)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model,
                             api_key=os.getenv("ANTHROPIC_API_KEY", ""),
                             timeout=60)
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model,
                                      google_api_key=os.getenv("GOOGLE_API_KEY", ""),
                                      timeout=60)
    raise ValueError(f"Unsupported classifier provider {provider!r}.")


def _content_text(resp: Any) -> str:
    """Flatten a langchain message ``content`` (str OR list of blocks)."""
    content = getattr(resp, "content", resp)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(getattr(block, "text", block)))
        return " ".join(parts)
    return str(content)


def classify_reply(query: str, reply: str, *,
                   provider: str = "openai",
                   model: str = "gpt-5.4-mini") -> dict:
    """Classify ``reply`` as ``"final"`` or ``"intermediate"``.

    Returns ``{"verdict", "reason", "error"}``.  ``error`` is True when
    the classifier call itself failed — the runner treats that as
    "stop and flag for review" rather than looping, so a broken
    classifier never spins the queue.
    """
    result = {"verdict": "final", "reason": "", "error": False}
    try:
        llm = _build_classifier_llm(provider, model)
        from langchain_core.messages import HumanMessage, SystemMessage
        messages = [
            SystemMessage(content=_CLASSIFIER_SYSTEM),
            HumanMessage(content=_CLASSIFIER_USER.format(
                query=(query or "")[:6000],
                reply=(reply or "")[:8000],
            )),
        ]
        text = _content_text(llm.invoke(messages)).strip()
        up = text.upper()
        i_int = up.find("INTERMEDIATE")
        i_fin = up.find("FINAL")
        if i_int == -1 and i_fin == -1:
            # No decisive word — default to final (never discard, never
            # loop on an unparseable reply).
            result["verdict"] = "final"
        elif i_fin == -1:
            result["verdict"] = "intermediate"
        elif i_int == -1:
            result["verdict"] = "final"
        else:
            # Both words present — the earlier one wins.
            result["verdict"] = "intermediate" if i_int < i_fin else "final"
        result["reason"] = text[:300]
    except Exception as exc:  # noqa: BLE001 — surface, never raise into the loop
        result["error"] = True
        result["reason"] = f"{type(exc).__name__}: {exc}"
    return result


# ---------------------------------------------------------------------------
# Manifest / queue-progress persistence
# ---------------------------------------------------------------------------

def ensure_dir() -> None:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, obj: Any) -> None:
    ensure_dir()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def write_manifest(manifest: dict) -> None:
    _atomic_write(MANIFEST_PATH, manifest)


def read_manifest() -> "dict | None":
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_progress(progress: dict) -> None:
    _atomic_write(PROGRESS_PATH, progress)


def read_progress() -> "dict | None":
    try:
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_manifest(*, runs: "list[dict]", defaults: dict) -> dict:
    """Assemble a fresh manifest from a start payload.

    Raises ``ValueError`` when a run has no query — the runner has
    nothing to send otherwise.
    """
    out_runs: list[dict] = []
    known = known_condition_ids()
    for i, r in enumerate(runs):
        query = (r.get("query") or "").strip()
        if not query:
            raise ValueError(f"Run #{i + 1} has an empty query.")
        cond = (r.get("condition") or "current").strip()
        if cond not in known:
            raise ValueError(
                f"Run #{i + 1} has unknown condition {cond!r}. "
                f"Valid conditions: {sorted(known)}.")
        rid = (r.get("run_id") or "").strip() or f"run-{i + 1:02d}"
        out_runs.append({
            "run_id":           rid,
            "condition":        cond,
            "query":            query,
            "continue_message": (r.get("continue_message") or "").strip() or None,
            "timeout_min":      _pos_int_or_none(r.get("timeout_min")),
            "max_continues":    _nonneg_int_or_none(r.get("max_continues")),
            "status":           "pending",
            "session_id":       None,
            "r2_key":           None,
            "continues":        0,
            "started_at":       None,
            "finished_at":      None,
            "note":             None,
        })
    if not out_runs:
        raise ValueError("The queue is empty — add at least one run.")
    return {"created_at": _now_iso(), "defaults": defaults, "runs": out_runs}


def _pos_int_or_none(v: Any) -> "int | None":
    try:
        n = int(v)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _nonneg_int_or_none(v: Any) -> "int | None":
    try:
        n = int(v)
        return n if n >= 0 else None
    except (TypeError, ValueError):
        return None


def has_resumable(manifest: "dict | None") -> bool:
    """True when ``manifest`` has at least one non-terminal run to drive."""
    if not manifest:
        return False
    return any(r.get("status") not in TERMINAL_STATES
               for r in manifest.get("runs", []))
