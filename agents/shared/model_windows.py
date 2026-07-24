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

# Populated by refresh_from_api(); exact model id -> max_input_tokens.
_api_windows: dict[str, int] = {}
_api_fetched = False


def context_window_for(model: str) -> int:
    """Best-known context window (tokens) for *model*.

    Prefers a value fetched from the provider API, then the longest matching
    static prefix, then ``DEFAULT_CONTEXT_WINDOW``.
    """
    name = (model or "").strip().lower()
    if not name:
        return DEFAULT_CONTEXT_WINDOW

    live = _api_windows.get(name)
    if live and live > 0:
        return int(live)

    best, best_len = DEFAULT_CONTEXT_WINDOW, -1
    for prefix, window in CONTEXT_WINDOWS.items():
        if name.startswith(prefix) and len(prefix) > best_len:
            best, best_len = window, len(prefix)
    return best


def source_for(model: str) -> str:
    """Where ``context_window_for`` got its answer — for logging."""
    name = (model or "").strip().lower()
    if _api_windows.get(name):
        return "provider API"
    for prefix in CONTEXT_WINDOWS:
        if name.startswith(prefix):
            return "static table"
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
