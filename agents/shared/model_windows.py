"""Context-window lookup per model, for the Context Pruner's threshold.

The Pruner needs to know how much room a model actually has before deciding
that a history is too long.  That number varies by an order of magnitude
across the models this project uses (200k for Haiku 4.5, 1.05M for gpt-5.4),
and — importantly — it varies WITHIN a family by version: Claude Opus 4.5 is
200k while Opus 4.6 and later are 1M.  A family-level guess is therefore
unsafe, so the table below is keyed on version-level prefixes and matched
longest-first.

Two sources, in priority order:

  1. A live per-model value fetched once per process (see ``refresh_from_api``).
     ONLY Anthropic can serve this: its ``GET /v1/models`` returns
     ``max_input_tokens`` per model.  OpenAI's ``GET /v1/models`` returns only
     ``id`` / ``object`` / ``created`` / ``owned_by`` — no context window — so
     OpenAI models always resolve from the static table.

  2. The static table, verified against the providers' own documentation
     (July 2026).  Used when the fetch is disabled, fails, or the provider
     cannot answer.

Unknown models fall back to ``DEFAULT_CONTEXT_WINDOW``, deliberately the
SMALLEST window in current use rather than an average: a model we do not
recognise should prune early rather than silently overflow.

Pure stdlib — importable and unit-testable without the agent stack.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger("propeller_agent")

# --------------------------------------------------------------------------
# Static table — verified against provider documentation, July 2026.
#
# Keys are MODEL-NAME PREFIXES matched longest-first, so a specific version
# always wins over a shorter family key.  That matters: "claude-opus-4-5"
# (200k) must not be shadowed by a generic "claude-opus" entry, and the
# family-level fallbacks below are deliberately the CONSERVATIVE 200k so a
# newly-released model we have not listed prunes early instead of overflowing.
# --------------------------------------------------------------------------
CONTEXT_WINDOWS: dict[str, int] = {
    # ---- Anthropic (platform.claude.com/docs/en/docs/about-claude/models) --
    "claude-fable-5":    1_000_000,
    "claude-mythos-5":   1_000_000,
    "claude-mythos-preview": 1_000_000,
    "claude-opus-4-8":   1_000_000,
    "claude-opus-4-7":   1_000_000,
    "claude-opus-4-6":   1_000_000,
    "claude-opus-4-5":     200_000,
    "claude-opus-4-1":     200_000,
    "claude-sonnet-5":   1_000_000,
    "claude-sonnet-4-6": 1_000_000,
    "claude-sonnet-4-5":   200_000,
    "claude-haiku-4-5":    200_000,
    # Family fallbacks — conservative on purpose (see module docstring).
    "claude-opus":         200_000,
    "claude-sonnet":       200_000,
    "claude-haiku":        200_000,
    "claude":              200_000,

    # ---- OpenAI (developers.openai.com/api/docs/models) --------------------
    "gpt-5.6-sol":       1_050_000,
    "gpt-5.6-terra":     1_050_000,
    "gpt-5.6-luna":      1_050_000,
    "gpt-5.6":           1_050_000,
    "gpt-5.5-pro":       1_050_000,
    "gpt-5.5":           1_050_000,
    "gpt-5.4-mini":        400_000,   # NOTE: much smaller than gpt-5.4
    "gpt-5.4":           1_050_000,
    "gpt-5":               400_000,   # unknown gpt-5.x -> the smaller tier
    "gpt-4":               128_000,
    "o3":                  200_000,
    "o1":                  200_000,

    # ---- Google -----------------------------------------------------------
    "gemini-2.5":        1_048_576,
    "gemini":            1_000_000,
}

DEFAULT_CONTEXT_WINDOW = 200_000

# Editable copy of the table, managed from the Workflow Settings panel.  The
# dict above stays as the built-in fallback for a missing/corrupt file.
TABLE_PATH = Path(__file__).with_suffix(".json")

# Populated by refresh_from_api(); exact model id -> max_input_tokens.
_api_windows: dict[str, int] = {}
_api_fetched = False

# Loaded from TABLE_PATH on first use; None until then.
_file_windows: dict[str, int] | None = None
_file_default: int | None = None

# Models that resolved to the default because nothing matched — surfaced in the
# settings panel so an unlisted model is visible without reading the logs.
_unmatched: set[str] = set()


def _load_table() -> tuple[dict[str, int], int]:
    """Return (models, default) from the JSON file, or the built-ins.

    Fail-soft by design: a missing, unreadable or malformed file leaves the
    verified built-in table in place rather than breaking session startup.
    """
    global _file_windows, _file_default
    if _file_windows is not None and _file_default is not None:
        return _file_windows, _file_default
    models, default = dict(CONTEXT_WINDOWS), DEFAULT_CONTEXT_WINDOW
    try:
        if TABLE_PATH.is_file():
            data = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
            raw = data.get("models")
            if isinstance(raw, dict) and raw:
                cleaned = {}
                for k, v in raw.items():
                    key = str(k).strip().lower()
                    try:
                        val = int(v)
                    except (TypeError, ValueError):
                        continue
                    if key and val > 0:
                        cleaned[key] = val
                if cleaned:
                    models = cleaned
            try:
                d = int(data.get("default", default))
                if d > 0:
                    default = d
            except (TypeError, ValueError):
                pass
    except Exception as exc:  # pragma: no cover - never block startup
        logger.warning(f"[CP]  model-window table unreadable ({exc}); "
                       f"using the built-in table.")
    _file_windows, _file_default = models, default
    return models, default


def reload_table() -> None:
    """Drop the cached file table so the next lookup re-reads TABLE_PATH."""
    global _file_windows, _file_default
    _file_windows = _file_default = None
    _unmatched.clear()


def read_table() -> dict:
    """The current editable table, for the settings panel."""
    models, default = _load_table()
    return {
        "models": dict(sorted(models.items(), key=lambda kv: (-len(kv[0]), kv[0]))),
        "default": default,
        "api_overrides": dict(_api_windows),
        "unmatched": sorted(_unmatched),
        "path": str(TABLE_PATH),
    }


def write_table(models: dict, default: int) -> None:
    """Persist the table and drop the cache.  Raises ValueError on bad input."""
    cleaned: dict[str, int] = {}
    for k, v in (models or {}).items():
        key = str(k).strip().lower()
        if not key:
            continue
        try:
            val = int(v)
        except (TypeError, ValueError):
            raise ValueError(f"'{k}' has a non-numeric window: {v!r}")
        if val <= 0:
            raise ValueError(f"'{k}' must have a positive window, got {val}")
        cleaned[key] = val
    if not cleaned:
        raise ValueError("the table must contain at least one model")
    try:
        dflt = int(default)
    except (TypeError, ValueError):
        raise ValueError(f"default must be an integer, got {default!r}")
    if dflt <= 0:
        raise ValueError("default must be positive")

    existing = {}
    if TABLE_PATH.is_file():
        try:
            existing = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    payload = {
        "_comment": existing.get("_comment", "Editable context-window table."),
        "default": dflt,
        "models": cleaned,
    }
    tmp = TABLE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(TABLE_PATH)          # atomic on the same filesystem
    reload_table()


def context_window_for(model: str) -> int:
    """Best-known context window (tokens) for *model*.

    Priority: a value fetched live from the provider API, then the longest
    matching prefix in the editable table, then the table's default.
    """
    name = (model or "").strip().lower()
    models, default = _load_table()
    if not name:
        return default

    live = _api_windows.get(name)
    if live and live > 0:
        return int(live)

    best, best_len = default, -1
    for prefix, window in models.items():
        if name.startswith(prefix) and len(prefix) > best_len:
            best, best_len = window, len(prefix)
    if best_len < 0:
        _unmatched.add(name)
    return best


def source_for(model: str) -> str:
    """Where ``context_window_for`` got its answer — for logging."""
    name = (model or "").strip().lower()
    models, _ = _load_table()
    if _api_windows.get(name):
        return "provider API"
    if any(name.startswith(p) for p in models):
        return "table"
    return "default (model not recognised)"


def refresh_from_api(force: bool = False) -> int:
    """Fetch per-model windows from the Anthropic Models API, once per process.

    Returns the number of models learned (0 on any failure).  Never raises:
    the pruning path must keep working without network access, so every error
    degrades to the static table.

    OpenAI is deliberately not attempted — its models endpoint does not expose
    a context window, so there is nothing to learn from it.
    """
    global _api_fetched
    if _api_fetched and not force:
        return len(_api_windows)
    _api_fetched = True

    try:
        from agents.shared.llm_provider import _read_shared_env
        import os
        shared = _read_shared_env()
        key = (shared.get("ANTHROPIC_API_KEY") or "").strip() \
            or os.getenv("ANTHROPIC_API_KEY", "").strip()
    except Exception:
        key = ""
    if not key:
        logger.info("[CP]  model-window refresh skipped: no ANTHROPIC_API_KEY "
                    "(static table in use)")
        return 0

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/models?limit=1000",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        logger.warning(f"[CP]  model-window refresh failed ({exc}); "
                       f"falling back to the static table.")
        return 0

    learned = 0
    for entry in (payload.get("data") or []):
        mid = str(entry.get("id", "")).strip().lower()
        win = entry.get("max_input_tokens")
        try:
            win = int(win)
        except (TypeError, ValueError):
            continue
        if mid and win > 0:
            _api_windows[mid] = win
            learned += 1
    if learned:
        logger.info(f"[CP]  model-window refresh: learned {learned} Anthropic "
                    f"model window(s) from the API.")
    return learned
