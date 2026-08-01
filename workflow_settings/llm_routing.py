"""Read / write the LLM routing configuration for the Workflow
Settings web view.

Storage layout (unchanged from v8):

* ``agents/.env``                            — shared default
  (``LLM_PROVIDER``, ``MODEL_NAME``, ``*_API_KEY`` lines)
* ``agents/<agent_name>/.env``               — per-agent override
  (same three line types; honoured at session start when both
  ``LLM_PROVIDER`` and the matching API key are set)
* ``workflow_settings/settings.py``          — ``LLM_ROUTING_MODE``
  (gates whether ``llm_provider.py`` honours per-agent overrides;
  edited via :func:`workflow_settings.editor.write_internal`)

This module never touches API key lines.  The UI is explicitly
not a key-management surface — keys must be set in the env or in
the .env files by hand.  Key-present status surfaces in the read
payload so the UI can warn the user when a chosen provider has no
key reachable at session start.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from dotenv import dotenv_values, set_key, unset_key

from workflow_settings import editor as _editor
from workflow_settings.llm_defaults import (
    model_for as _default_model_for,
    PROPOSED_WORKFLOWS as _PROPOSED_WORKFLOWS,
)
# NOTE: do NOT import ``workflow_settings.settings`` at module level
# here.  ``read_state`` must read LLM_ROUTING_MODE freshly off disk
# (via ``_editor._parse_nodes``) so a save made during a live session
# is visible the next time the Workflow Settings view fetches state.
# Importing the module would bind a stale reference to the value
# frozen at process startup — the exact pattern that caused saved
# routing modes to silently revert to "individual" in v9.

# ---------------------------------------------------------------------------
# Topology — the agents that appear as boxes in the routing chart.
# Order matches the LOG-and-Status SVG so the duplicate-layout chart
# in Workflow Settings can iterate over this list directly.
# ---------------------------------------------------------------------------

PROVIDERS: list[dict[str, str]] = [
    {"key": "openai",     "label": "OpenAI",     "env_var": "OPENAI_API_KEY"},
    {"key": "anthropic",  "label": "Anthropic",  "env_var": "ANTHROPIC_API_KEY"},
    {"key": "google",     "label": "Google",     "env_var": "GOOGLE_API_KEY"},
    {"key": "openrouter", "label": "OpenRouter", "env_var": "OPENROUTER_API_KEY"},
]
_PROVIDER_KEYS = {p["key"] for p in PROVIDERS}
_PROVIDER_ENV_VARS = {p["key"]: p["env_var"] for p in PROVIDERS}

_MODES = {"individual", "openai", "anthropic", "google", "openrouter"}

# (agent_key, display label, wired_into_dispatcher)
AGENT_SPEC: list[tuple[str, str, bool]] = [
    ("receptionist",          "Receptionist",          True),
    ("orchestrator",          "Orchestrator",          True),
    ("user_input_inspector",  "User Input Inspector",  True),
    ("planner",               "Planner",               True),
    ("dc_input_creator",      "Input Creator",         True),
    ("dc_input_inspector",    "Input Inspector",       True),
    ("dc_output_inspector",   "Output Inspector",      True),
    ("tool_caller",           "Tool Caller",           True),
    ("database_handler",      "Database Handler",      True),
    ("context_pruner",        "Context Pruner",        False),
    # 5-agent topology.  ``wired_into_dispatcher=False`` until the
    # topology wiring lands — they exist as identities but are never
    # constructed yet.
    ("conductor",             "Conductor",             False),
    ("creator",               "Creator",               False),
]
AGENT_KEYS = [k for k, _, _ in AGENT_SPEC]

# Resolve paths once.  ``AGENTS_DIR`` mirrors what ``llm_provider.py``
# computes so the two modules can never disagree about where the .env
# files live.
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
AGENTS_DIR = _PROJECT_ROOT / "agents"
SHARED_ENV_PATH = AGENTS_DIR / ".env"

_DEFAULT_PROVIDER = "openai"
_DEFAULT_MODEL = "gpt-5-mini"

# Recommended placeholder model names per provider; the UI uses these
# as input ``placeholder`` text only — the field stays free-form.
PROVIDER_MODEL_PLACEHOLDERS = {
    "openai":     "gpt-5-mini",
    "anthropic":  "claude-sonnet-4-5",
    "google":     "gemini-2.5-pro",
    "openrouter": "deepseek/deepseek-chat",
}


class RoutingError(ValueError):
    """Raised on an invalid routing payload; surfaced to the UI as 400."""


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def _read_env(path: Path) -> dict[str, str]:
    """Return a ``{KEY: value}`` dict from ``path`` or ``{}``."""
    if not path.exists():
        return {}
    try:
        return {k: (v or "") for k, v in dotenv_values(path).items()}
    except OSError:
        return {}


def _agent_env_path(agent_key: str) -> Path:
    return AGENTS_DIR / agent_key / ".env"


def _provider_key_present(provider: str, per_agent_env: dict[str, str] | None) -> bool:
    """Check whether the API key for ``provider`` is reachable.

    The check mirrors ``llm_provider._resolve_config`` so the UI
    accurately predicts whether a session would start: per-agent .env
    first (when given), then shared ``agents/.env``, then ``os.environ``.
    """
    env_var = _PROVIDER_ENV_VARS.get(provider)
    if not env_var:
        return False
    if per_agent_env and (per_agent_env.get(env_var) or "").strip():
        return True
    shared = _read_env(SHARED_ENV_PATH)
    if (shared.get(env_var) or "").strip():
        return True
    return bool((os.getenv(env_var) or "").strip())


def _shared_provider_model() -> tuple[str, str]:
    shared = _read_env(SHARED_ENV_PATH)
    provider = (shared.get("LLM_PROVIDER") or "").strip().lower() or _DEFAULT_PROVIDER
    if provider not in _PROVIDER_KEYS:
        # Treat an unknown provider in the file as "default" so the UI
        # surfaces something selectable; the user can correct it.
        provider = _DEFAULT_PROVIDER
    model = (shared.get("MODEL_NAME") or "").strip() or _DEFAULT_MODEL
    return provider, model


def read_state() -> dict[str, Any]:
    """Return the full read payload consumed by the routing UI.

    Shape::

        {
          "mode": "individual" | "openai" | "anthropic" | "google",
          "providers": [
            {"key": "openai", "label": "OpenAI",
             "env_var": "OPENAI_API_KEY", "key_present": True,
             "model_placeholder": "gpt-5-mini"},
            ...
          ],
          "shared": {"provider": "openai", "model": "gpt-5-mini"},
          "agents": [
            {"key": "receptionist", "label": "Receptionist",
             "wired": True, "provider": "openai", "model": "gpt-5-mini",
             "source": "shared" | "per-agent" | "global",
             "override_provider": "" | "openai" | "anthropic" | "google",
             "override_model": ""},
            ...
          ]
        }

    ``provider`` / ``model`` show the EFFECTIVE values (what the session
    would resolve to right now); ``override_provider`` /
    ``override_model`` show the values literally written in the
    per-agent file (empty when there is no override).  The UI binds its
    inputs to the override fields so saving never accidentally promotes
    an inherited value into a per-agent override.
    """
    # Read LLM_ROUTING_MODE freshly off disk on every call.  Do NOT
    # use ``getattr(_settings, …)`` here: ``write_updates`` writes the
    # new value to settings.py via atomic rename, but nothing in this
    # process ever reloads the ``workflow_settings.settings`` module
    # outside of ``_build_session`` — and the Workflow Settings view
    # fetches /api/llm-routing WITHOUT building a session.  Reading the
    # cached module attribute therefore returns the value frozen at
    # process startup, which is why saved-mode reverts to the old
    # value the moment the POST response paints the dropdown.
    #
    # Same disk-parse pattern ``editor.read_schema`` uses for the
    # /api/settings flag list (the flag list does NOT have this bug).
    mode_raw = ""
    for _node in _editor._parse_nodes()[1]:
        if _node.target.id == "LLM_ROUTING_MODE":
            ok, val = _editor._literal(_node.value)
            if ok:
                mode_raw = str(val or "")
            break
    mode = mode_raw.strip().lower()
    if mode not in _MODES:
        # Fallback when the literal is missing / unrecognised — match
        # the on-disk default in workflow_settings/settings.py.
        mode = "openai"

    shared_provider, shared_model = _shared_provider_model()

    # Read the shared file once more, this time WITHOUT the
    # ``_DEFAULT_MODEL`` fallback, so the per-agent loop below can
    # distinguish "shared file explicitly set MODEL_NAME" (use that
    # for every agent) from "shared file has no MODEL_NAME at all"
    # (fall back to the per-agent baked-in default in
    # ``workflow_settings/llm_defaults.py``).
    shared_data = _read_env(SHARED_ENV_PATH)
    shared_model_in_file = (shared_data.get("MODEL_NAME") or "").strip()

    providers_out: list[dict[str, Any]] = []
    for p in PROVIDERS:
        providers_out.append({
            "key": p["key"],
            "label": p["label"],
            "env_var": p["env_var"],
            "key_present": _provider_key_present(p["key"], None),
            "model_placeholder": PROVIDER_MODEL_PLACEHOLDERS[p["key"]],
        })

    agents_out: list[dict[str, Any]] = []
    for key, label, wired in AGENT_SPEC:
        per_env = _read_env(_agent_env_path(key))
        override_provider = (per_env.get("LLM_PROVIDER") or "").strip().lower()
        override_model = (per_env.get("MODEL_NAME") or "").strip()
        if mode in _PROVIDER_KEYS:
            # GLOBAL OVERRIDE active.  ``llm_provider._resolve_config`` forces
            # this provider + the shared MODEL_NAME on every agent and does
            # NOT consult the per-agent files at all, so reporting a per-agent
            # value here would describe a model that will never be used (it
            # previously did, which made both the chart and the session-config
            # banner misreport what actually ran).  The override_* fields below
            # still carry the literal file values, so the UI keeps showing —
            # and can still save — per-agent entries for when the mode goes
            # back to "individual".
            effective_provider = mode
            effective_model = shared_model
            source = "global"
        elif override_provider in _PROVIDER_KEYS and override_model:
            effective_provider = override_provider
            effective_model = override_model
            source = "per-agent"
        else:
            # Provider falls back to shared file's value, else to
            # the generic default.  Model prefers the shared file's
            # value (explicit user choice in agents/.env) and falls
            # back to the per-agent baked-in default so a fresh
            # deploy with no .env files shows the configured
            # per-agent model in the chart.
            effective_provider = shared_provider
            effective_model = shared_model_in_file or _default_model_for(key)
            source = "shared"
            # Surface a partial override as "still inherits" but keep
            # the override fields populated so the UI can show what
            # was already typed.
        agents_out.append({
            "key": key,
            "label": label,
            "wired": wired,
            "provider": effective_provider,
            "model": effective_model,
            "source": source,
            "override_provider": override_provider if override_provider in _PROVIDER_KEYS else "",
            "override_model": override_model,
        })

    return {
        "mode": mode,
        "providers": providers_out,
        "shared": {"provider": shared_provider, "model": shared_model},
        "agents": agents_out,
        # Surfaced to the UI as buttons in the Global LLM row.  See
        # workflow_settings.llm_defaults.PROPOSED_WORKFLOWS for the
        # source of truth and the frontend ``renderLrPresets`` /
        # ``applyLrPreset`` in web/app.js for the consumer.
        "proposed_workflows": _PROPOSED_WORKFLOWS,
    }


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

_AGENT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _validate_provider(provider: str, *, allow_empty: bool, label: str) -> str:
    p = (provider or "").strip().lower()
    if not p:
        if allow_empty:
            return ""
        raise RoutingError(f"{label}: provider is required.")
    if p not in _PROVIDER_KEYS:
        raise RoutingError(
            f"{label}: provider must be one of "
            f"{sorted(_PROVIDER_KEYS)}, got {provider!r}."
        )
    return p


def _validate_model(model: str, *, allow_empty: bool, label: str) -> str:
    m = (model or "").strip()
    if not m and not allow_empty:
        raise RoutingError(f"{label}: model name is required.")
    if len(m) > 200:
        raise RoutingError(f"{label}: model name is unreasonably long.")
    return m


def write_updates(payload: dict[str, Any]) -> None:
    """Validate ``payload`` and update settings.py + .env files in place.

    ``payload`` shape mirrors the ``read_state`` response (minus the
    ``providers`` block, which is read-only):

        {
          "mode": "individual" | "openai" | "anthropic" | "google",
          "shared": {"provider": "openai", "model": "gpt-5-mini"},
          "agents": [
            {"key": "receptionist",
             "override_provider": "" | "openai" | "anthropic" | "google",
             "override_model": ""},
            ...
          ]
        }

    The save is intentionally NOT atomic across files: each .env file
    is written individually by ``dotenv.set_key`` (atomic per file),
    and ``LLM_ROUTING_MODE`` is rewritten via ``editor.write_internal``
    (atomic via tempfile).  Validation runs to completion before any
    file is touched, so a payload-level error never leaves the system
    half-saved.
    """
    if not isinstance(payload, dict):
        raise RoutingError("Expected a JSON object.")

    raw_mode = (payload.get("mode") or "").strip().lower()
    if raw_mode not in _MODES:
        raise RoutingError(
            f"mode must be one of {sorted(_MODES)}, got {payload.get('mode')!r}."
        )

    shared = payload.get("shared") or {}
    if not isinstance(shared, dict):
        raise RoutingError("'shared' must be an object.")
    shared_provider = _validate_provider(
        shared.get("provider", ""), allow_empty=False, label="shared",
    )
    shared_model = _validate_model(
        shared.get("model", ""), allow_empty=False, label="shared",
    )

    agents_payload = payload.get("agents") or []
    if not isinstance(agents_payload, list):
        raise RoutingError("'agents' must be a list.")

    known_keys = set(AGENT_KEYS)
    seen: set[str] = set()
    per_agent_clean: list[tuple[str, str, str]] = []  # (key, provider, model)
    for entry in agents_payload:
        if not isinstance(entry, dict):
            raise RoutingError("Each agent entry must be an object.")
        key = (entry.get("key") or "").strip().lower()
        if not _AGENT_KEY_RE.match(key):
            raise RoutingError(f"Agent key {entry.get('key')!r} is malformed.")
        if key not in known_keys:
            raise RoutingError(f"Unknown agent key {key!r}.")
        if key in seen:
            raise RoutingError(f"Duplicate agent entry for {key!r}.")
        seen.add(key)
        ov_provider = _validate_provider(
            entry.get("override_provider", ""),
            allow_empty=True,
            label=f"agent {key}",
        )
        ov_model = _validate_model(
            entry.get("override_model", ""),
            allow_empty=True,
            label=f"agent {key}",
        )
        # Reject partial overrides — either both fields are set or both
        # are empty.  A partial override silently inherits from shared
        # at session start, which would be a confusing UX.
        if bool(ov_provider) != bool(ov_model):
            raise RoutingError(
                f"agent {key}: set both provider and model, or clear "
                f"both to inherit from the shared default."
            )
        per_agent_clean.append((key, ov_provider, ov_model))

    # ----- validation done; start writing -----

    # 1. LLM_ROUTING_MODE via the editor's internal write path.
    _editor.write_internal({"LLM_ROUTING_MODE": raw_mode})

    # 2. Shared agents/.env.  Always rewrite LLM_PROVIDER + MODEL_NAME
    #    (other lines, including API keys, are preserved by set_key).
    SHARED_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SHARED_ENV_PATH.exists():
        SHARED_ENV_PATH.touch()
    set_key(str(SHARED_ENV_PATH), "LLM_PROVIDER", shared_provider,
            quote_mode="never")
    set_key(str(SHARED_ENV_PATH), "MODEL_NAME", shared_model,
            quote_mode="never")

    # 3. Per-agent agents/<agent>/.env.  When both override fields are
    #    set, write them; when both are empty, clear any existing
    #    override lines (other lines stay intact).
    for key, ov_provider, ov_model in per_agent_clean:
        path = _agent_env_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if ov_provider and ov_model:
            if not path.exists():
                path.touch()
            set_key(str(path), "LLM_PROVIDER", ov_provider,
                    quote_mode="never")
            set_key(str(path), "MODEL_NAME", ov_model,
                    quote_mode="never")
        else:
            # No override requested.  Only touch the file when it
            # exists AND actually carries one of the two lines.
            if path.exists():
                cur = _read_env(path)
                if "LLM_PROVIDER" in cur:
                    unset_key(str(path), "LLM_PROVIDER",
                              quote_mode="never")
                if "MODEL_NAME" in cur:
                    unset_key(str(path), "MODEL_NAME",
                              quote_mode="never")
