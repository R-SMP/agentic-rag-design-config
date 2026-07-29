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
import re
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
DRAFT_PATH = QUEUE_DIR / "draft.json"
# Per-run staged images (one subfolder per run's stage_id), each holding
# the image files + their `_note.txt` descriptions + `.compression.json`
# sidecars.  The runner copies a run's folder into inputs/input_images/
# before that run's turn.
IMAGES_ROOT = QUEUE_DIR / "images"

# Terminal run states — a run in one of these is never re-driven on a
# resume, and the queue skips straight past it.
TERMINAL_STATES = {"done", "needs_review", "failed"}

# A stage_id keys a run's staged-image folder.  Client-generated
# (crypto.randomUUID); validated here before it ever touches the filesystem.
_STAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def sanitize_stage_id(stage_id: str) -> str:
    sid = (stage_id or "").strip()
    if not _STAGE_ID_RE.match(sid):
        raise ValueError(f"Invalid stage_id {stage_id!r}.")
    return sid


def stage_dir(stage_id: str) -> Path:
    """Absolute staging folder for ``stage_id`` (validated, inside IMAGES_ROOT)."""
    sid = sanitize_stage_id(stage_id)
    d = (IMAGES_ROOT / sid)
    root = IMAGES_ROOT.resolve()
    if d.resolve().parent != root:
        raise ValueError(f"stage_id {stage_id!r} escapes the images root.")
    return d


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

_VALID_PROVIDERS = {"openai", "anthropic", "google", "openrouter"}


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


def single_model_payload(provider: str, model: str) -> dict:
    """Global-override payload — force one ``provider`` + ``model`` on EVERY
    agent (the runner's ``single`` condition).  Validates: provider must be
    known and the model non-empty.  Raises ``ValueError`` otherwise."""
    p = (provider or "").strip().lower()
    m = (model or "").strip()
    if p not in _VALID_PROVIDERS:
        raise ValueError(
            f"single-model provider must be one of {sorted(_VALID_PROVIDERS)}, "
            f"got {provider!r}.")
    if not m:
        raise ValueError("single-model run needs a model name.")
    return {"mode": p, "shared": {"provider": p, "model": m}, "agents": []}


def _conditions() -> "list[dict[str, Any]]":
    """Build the ordered condition list (id, label, payload).

    Built lazily so a broken/absent ``llm_defaults`` never stops the
    module importing — the runner degrades to just ``current`` + ``single``.
    ``single`` carries no static payload: the runner builds it per run from
    that run's ``single_provider`` / ``single_model`` fields.
    """
    out: list[dict[str, Any]] = [
        {"id": "current", "label": "Current settings (no change)", "payload": None},
        {"id": "single",
         "label": "Single model — all agents (pick provider + model below)",
         "payload": None},
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
        # Fall through with just current + single.
        pass
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


_PROVIDER_KEY_ENV = {
    "openai":     "OPENAI_API_KEY",
    "anthropic":  "ANTHROPIC_API_KEY",
    "google":     "GOOGLE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def provider_key_present(provider: str) -> bool:
    """True when the API key for ``provider`` is set in the process env.

    Used to fail-fast at queue start: a classifier (or a single-model run's
    condition) whose provider key is absent would error every run — better
    caught before the night starts.
    """
    env = _PROVIDER_KEY_ENV.get((provider or "").strip().lower())
    return bool(env and os.getenv(env, "").strip())


def classifier_key_present(provider: str) -> bool:
    """Back-compat alias — the classifier's key check is a provider check."""
    return provider_key_present(provider)


# ---------------------------------------------------------------------------
# Intermediate-vs-final classifier
# ---------------------------------------------------------------------------

_CLASSIFIER_SYSTEM = (
    "You are a strict classifier for an automated benchmark runner driving a "
    "multi-agent propeller-design assistant. Your ONLY job: decide whether the "
    "assistant's latest reply has DELIVERED what the user asked for in THIS "
    "run, or whether the assistant is still working — i.e. it paused, is asking "
    "a clarifying question, gave only a partial / intermediate result, or is "
    "waiting to be told to continue.\n"
    "\n"
    "Judge STRICTLY against what the user actually requested in their query "
    "(and the explicit acceptance criterion, if one is given) — NOT against any "
    "assumption about what a 'complete' propeller job normally involves. In "
    "particular: if the user asked only for extracted parameter values, a "
    "specific number, or any text answer, then a reply that contains exactly "
    "that IS final — even if no 3D geometry, mesh, blade-section drawings, or "
    "renders were produced. Absent geometry means 'not done' ONLY when the user "
    "asked for geometry. Do not invent extra steps the user did not request.\n"
    "\n"
    "Refine that with three rules:\n"
    "\n"
    "- VALUES/ANSWER REQUESTS. When the request is for the values or the answer "
    "themselves, a reply that presents them is FINAL even if it also shows the "
    "arithmetic, conditional branches, and provenance behind each value: that "
    "worked-out reasoning IS the deliverable, not a sign the assistant is still "
    "calculating.\n"
    "\n"
    "- PRODUCE-A-RESULT REQUESTS. That leniency applies ONLY to value/answer "
    "requests. When the request asks the assistant to actually PRODUCE a result "
    "from the values (a generated 3D model, a built or rendered geometry), a "
    "parameter list or a described plan is NOT yet final — finality needs the "
    "produced result to actually exist (the files-produced line should name a "
    "real mesh/render). If unsure, prefer INTERMEDIATE.\n"
    "\n"
    "- OPTIONAL/WELCOMED WORK. Steps the user only permits or welcomes but does "
    "not require do not by themselves gate finality: a complete required answer "
    "is FINAL whether or not that optional step was taken — UNLESS the reply "
    "itself signals the assistant still intends to do more, which is "
    "INTERMEDIATE.\n"
    "\n"
    "Answer with exactly ONE word — either FINAL or INTERMEDIATE — and nothing "
    "else."
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
    if provider == "openrouter":
        # OpenAI-compatible endpoint — same client, base_url override.
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model,
                          api_key=os.getenv("OPENROUTER_API_KEY", ""),
                          base_url="https://openrouter.ai/api/v1",
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
                   expected_output: str = "",
                   artefacts: str = "",
                   provider: str = "openai",
                   model: str = "gpt-5.4-mini") -> dict:
    """Classify ``reply`` as ``"final"`` or ``"intermediate"`` for THIS run.

    ``expected_output`` is an optional per-run acceptance criterion (a
    classifier-only grading hint — never sent to the agents); blank means
    "grade against the query".  ``artefacts`` is a short summary of the
    files the assistant produced this turn (e.g. ``"propeller_mesh.obj,
    render_isometric.png"`` or ``"none"``), so an expectation of geometry
    can be graded on the actual artefact rather than the reply's claim.

    Returns ``{"verdict", "reason", "error"}``.  ``error`` is True when the
    classifier call itself failed — the runner treats that as "stop and
    flag for review" rather than looping, so a broken classifier never
    spins the queue.
    """
    result = {"verdict": "final", "reason": "", "error": False}
    try:
        llm = _build_classifier_llm(provider, model)
        from langchain_core.messages import HumanMessage, SystemMessage
        # Built by concatenation (NOT str.format) so a query / reply / note
        # containing "{" or "}" can never raise.
        expected_block = ""
        if (expected_output or "").strip():
            expected_block = (
                "EXPLICIT ACCEPTANCE CRITERION for this run — what a FINISHED "
                "answer must contain; treat as authoritative:\n"
                + expected_output.strip()[:2000] + "\n\n")
        artefact_block = (
            "FILES THE ASSISTANT PRODUCED THIS TURN: "
            + ((artefacts or "").strip() or "none")[:500] + "\n\n")
        user_msg = (
            "USER REQUEST (what this run asked for):\n"
            + (query or "")[:6000] + "\n\n"
            + expected_block
            + artefact_block
            + "ASSISTANT REPLY:\n" + (reply or "")[:8000] + "\n\n"
            + "Has the assistant delivered what the user asked for (FINAL), or "
              "is it still working / paused / asking a question (INTERMEDIATE)? "
              "Answer FINAL or INTERMEDIATE."
        )
        messages = [
            SystemMessage(content=_CLASSIFIER_SYSTEM),
            HumanMessage(content=user_msg),
        ]
        text = _content_text(llm.invoke(messages)).strip()
        up = text.upper()
        # WHOLE-WORD matches only, so "FINALIZE" / "FINALLY" do not count as
        # a FINAL verdict.  The prompt demands exactly one word; anything
        # ambiguous (both words, or neither) means the model did not comply.
        has_fin = re.search(r"\bFINAL\b", up) is not None
        has_int = re.search(r"\bINTERMEDIATE\b", up) is not None
        if has_fin and not has_int:
            result["verdict"] = "final"
            result["reason"] = text[:300]
        elif has_int and not has_fin:
            result["verdict"] = "intermediate"
            result["reason"] = text[:300]
        else:
            # Ambiguous / non-compliant output — do NOT guess.  Flag as an
            # error so the runner STOPS and marks the run needs_review
            # (never silently finalises, never loops).
            result["error"] = True
            result["reason"] = "unparseable classifier verdict: " + text[:200]
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


def write_draft(draft: dict) -> None:
    _atomic_write(DRAFT_PATH, draft)


def read_draft() -> "dict | None":
    try:
        return json.loads(DRAFT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def prune_staging(keep_stage_ids: "set[str] | list[str]") -> None:
    """Remove staged-image folders whose stage_id is not in ``keep_stage_ids``
    (best-effort GC of runs the user deleted / old queues)."""
    keep = {str(s) for s in (keep_stage_ids or [])}
    if not IMAGES_ROOT.exists():
        return
    import shutil
    for d in IMAGES_ROOT.iterdir():
        try:
            if d.is_dir() and d.name not in keep:
                shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


ITERATIONS_MAX = 100


def build_manifest(*, runs: "list[dict]", defaults: dict) -> dict:
    """Assemble a fresh manifest from a start payload.

    Each editor run is EXPANDED into its ``iterations`` count (per-run field,
    else the queue-wide default, else 1) — each iteration is an independent
    manifest run (its own session / log / R2 key), tagged with ``base_run_id``
    / ``iteration`` / ``iterations_total`` so the morning scoring can group
    the repeats.  Raises ``ValueError`` on an empty query, unknown condition,
    or an invalid single-model spec.
    """
    default_iter = _pos_int_or_none(defaults.get("iterations")) or 1
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
        single_provider = (r.get("single_provider") or "").strip().lower()
        single_model = (r.get("single_model") or "").strip()
        if cond == "single":
            # Validate now (raises on bad provider / empty model).
            try:
                single_model_payload(single_provider, single_model)
            except ValueError as exc:
                raise ValueError(f"Run #{i + 1}: {exc}")
        rid = (r.get("run_id") or "").strip() or f"run-{i + 1:02d}"
        stage_id = (r.get("stage_id") or "").strip() or None

        n_iter = _pos_int_or_none(r.get("iterations")) or default_iter
        n_iter = max(1, min(ITERATIONS_MAX, n_iter))

        base = {
            "condition":        cond,
            "query":            query,
            "stage_id":         stage_id,
            "single_provider":  single_provider or None,
            "single_model":     single_model or None,
            "expected_output":  (r.get("expected_output") or "").strip() or None,
            "continue_message": (r.get("continue_message") or "").strip() or None,
            "timeout_min":      _pos_int_or_none(r.get("timeout_min")),
            "max_continues":    _nonneg_int_or_none(r.get("max_continues")),
        }
        for it in range(1, n_iter + 1):
            run_dict = dict(base)
            run_dict.update({
                "run_id":          rid if n_iter == 1 else f"{rid}·{it}",
                "base_run_id":     rid,
                "iteration":       it,
                "iterations_total": n_iter,
                "status":          "pending",
                "session_id":      None,
                "r2_key":          None,
                "continues":       0,
                "started_at":      None,
                "finished_at":     None,
                "note":            None,
            })
            out_runs.append(run_dict)
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
