"""LLM construction with per-agent ``.env`` resolution.

Two layers of configuration are supported:

1. ``agents/.env`` — the SHARED default for every agent.  Filling it with
   ``LLM_PROVIDER`` + the matching ``*_API_KEY`` + ``MODEL_NAME`` makes
   every agent use the same LLM (the original one-key-fits-all behaviour).
2. ``agents/<agent_name>/.env`` — a PER-AGENT override.  When this file
   exists AND defines a usable ``LLM_PROVIDER`` + matching API key, the
   named agent uses that provider instead of the shared default.  Other
   agents are unaffected.

Usage::

    from agents.shared.llm_provider import build_llm
    llm, provider, model = build_llm("orchestrator")

The shared ``agents/.env`` is read once at import time; per-agent files
are read lazily on the first ``build_llm(agent)`` call so a missing or
empty per-agent file simply falls back to the shared default.

Provider-aware image blocks live here too because the block format
differs by provider (Anthropic uses ``{type: image, source: ...}``;
OpenAI / Google use ``{type: image_url, image_url: {url: ...}}``).
``make_image_block(b64, provider)`` and the b64-encoder ``encode_image``
are the only image helpers.
"""

import base64
import os
from pathlib import Path
from typing import Tuple

from dotenv import dotenv_values
from langchain_core.messages import SystemMessage
from langchain_core.rate_limiters import InMemoryRateLimiter

from agents.shared.image_compression import (
    compress_for_model,
    read_degree,
    render_degree_and_floor,
    sniff_media_type,
)
from workflow_settings import settings as _workflow_settings
from workflow_settings.llm_defaults import model_for as _default_model_for

# Resolve the agents directory relative to this file (agents/shared/llm_provider.py).
AGENTS_DIR = Path(__file__).resolve().parent.parent

# ----------------------------------------------------------------------
# Shared rate limiter (optional)
# ----------------------------------------------------------------------
# When ``workflow_settings.RATE_LIMIT_ENABLED`` is True, build ONE
# token-bucket limiter at import time and hand the same instance to
# every provider constructor.  Because all 8 agents share this single
# bucket, the limiter enforces a GLOBAL request-rate ceiling across
# the whole multi-agent system — exactly what's needed against
# org-level provider limits like Anthropic's 30k input-tokens/min.
#
# When disabled, the constant is ``None`` and ``rate_limiter=None`` is
# the langchain default no-op, so existing runs see zero behavioural
# change.
#
# ``check_every_n_seconds`` is the polling interval used by the
# limiter while a call is waiting for a token; 0.1 is fine-grained
# enough to be invisible to humans without being a busy-loop.
# ``max_bucket_size`` controls how many "saved-up" requests can fire
# back-to-back when the system has been idle — set to ~4 seconds'
# worth of capacity (with a floor of 1) so a fresh session can issue
# a small burst before throttling kicks in.
# ----------------------------------------------------------------------
_RATE_LIMITER: InMemoryRateLimiter | None = (
    InMemoryRateLimiter(
        requests_per_second=_workflow_settings.RATE_LIMIT_REQUESTS_PER_SECOND,
        check_every_n_seconds=0.1,
        max_bucket_size=max(
            1,
            int(_workflow_settings.RATE_LIMIT_REQUESTS_PER_SECOND * 4),
        ),
    )
    if _workflow_settings.RATE_LIMIT_ENABLED
    else None
)

# Shared agent .env path.  The file itself is RE-READ at every
# ``_resolve_config`` call so that mid-process edits made by the web
# UI's Workflow Settings → LLM-routing chart take effect on the next
# session build (without a uvicorn restart).
_SHARED_ENV_PATH = AGENTS_DIR / ".env"

_API_KEY_ENV_VARS: dict = {
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

# OpenRouter is OpenAI-API-compatible — the SAME ChatOpenAI client with a
# different base_url — which is how open-weight models (DeepSeek, Qwen-VL,
# Llama, …) are reached.  Model names are OpenRouter-style, e.g.
# "deepseek/deepseek-chat"; vision models use the OpenAI-style image block
# ``make_image_block`` already emits for non-Anthropic providers.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_DEFAULT_MODEL = "gpt-5-mini"


# HTTP timeout (in seconds) passed to every provider client at
# construction time.  Without this, the underlying SDKs fall back
# to long read timeouts — Anthropic's SDK defaults to 600 s
# (10 min) per request, so a single stuck connection can hang the
# dispatcher for up to ~50 min once ``invoke_with_retry`` cycles
# through MAX_ATTEMPTS=5 attempts (one observed 2026-06-05 DH save
# stalled mid-interview for ~10 min before the SDK timed out and
# the retry path recovered).
#
# 180 s is long enough for vision-heavy generations and Context
# Pruner summarisation passes (Anthropic Opus with 4 images
# typically responds in 30-60 s; outliers up to ~90 s observed)
# and short enough that a true hang surfaces in ~15 min worst
# case (5 retries × 180 s) instead of ~50 min.  Bump only if you
# observe spurious connection-error retry log lines on legitimate
# slow generations.
_LLM_REQUEST_TIMEOUT_S: float = 180.0


def _read_shared_env() -> dict:
    """Read ``agents/.env`` fresh; empty dict when missing."""
    if not _SHARED_ENV_PATH.exists():
        return {}
    try:
        return dotenv_values(_SHARED_ENV_PATH)
    except OSError:
        return {}


def _read_env_file(agent_name: str) -> dict:
    """Read ``agents/<agent_name>/.env`` if it exists; else empty dict."""
    path = AGENTS_DIR / agent_name / ".env"
    if not path.exists():
        return {}
    try:
        return dotenv_values(path)
    except OSError:
        return {}


def _current_routing_mode() -> str:
    """Return the live LLM_ROUTING_MODE.

    Read directly off the (already-imported) ``workflow_settings``
    module so this picks up reloads done by callers such as
    ``web_app._build_session``.  Defaults to ``"individual"`` if the
    setting is missing or unrecognised.
    """
    mode = (getattr(_workflow_settings, "LLM_ROUTING_MODE", "individual") or "").strip().lower()
    if mode not in {"individual", "openai", "anthropic", "google", "openrouter"}:
        return "individual"
    return mode


def _require_explicit_openrouter_model(provider: str, explicit_model: str,
                                       where: str) -> None:
    """OpenRouter model ids are vendor-prefixed (e.g. ``deepseek/deepseek-chat``);
    the generic OpenAI-style fallback default would be rejected with a 400.
    Fail early with a clear message instead of an opaque provider error."""
    if provider == "openrouter" and not explicit_model:
        raise ValueError(
            f"{where} selects provider 'openrouter' but no MODEL_NAME is set. "
            f"OpenRouter needs an explicit vendor-prefixed model, "
            f"e.g. 'deepseek/deepseek-chat'."
        )


def _resolve_config(agent_name: str) -> Tuple[str, str, str]:
    """Pick (provider, model, api_key) for ``agent_name``.

    Resolution order:
      0. If ``LLM_ROUTING_MODE`` names a specific provider, force that
         provider+model from shared ``agents/.env`` (and ignore any
         per-agent override — the files stay on disk untouched).
      1. The per-agent .env file, if it sets ``LLM_PROVIDER`` and the
         matching API key.
      2. The shared ``agents/.env``.

    Raises ValueError if no source supplies a usable provider / key
    combination.
    """
    shared = _read_shared_env()

    def _from(layer: dict, key: str) -> str:
        return (layer.get(key) or "").strip()

    mode = _current_routing_mode()
    if mode in {"openai", "anthropic", "google", "openrouter"}:
        # Global override active — shared file's MODEL_NAME applies to
        # every agent, per-agent files are deliberately not consulted.
        provider = mode
        env_var = _API_KEY_ENV_VARS[provider]
        api_key = _from(shared, env_var) or os.getenv(env_var, "")
        if not api_key:
            raise ValueError(
                f"LLM_ROUTING_MODE={mode!r} but {env_var} is not set "
                f"in agents/.env or the process environment."
            )
        explicit = _from(shared, "MODEL_NAME")
        _require_explicit_openrouter_model(
            provider, explicit, "LLM_ROUTING_MODE=openrouter")
        model = explicit or _DEFAULT_MODEL
        return provider, model, api_key

    per_agent = _read_env_file(agent_name)

    # Prefer a complete per-agent override.
    provider = _from(per_agent, "LLM_PROVIDER").lower()
    if provider:
        env_var = _API_KEY_ENV_VARS.get(provider)
        if env_var is None:
            raise ValueError(
                f"Per-agent .env for '{agent_name}' has unknown "
                f"LLM_PROVIDER '{provider}'.  Supported: "
                f"{', '.join(_API_KEY_ENV_VARS)}."
            )
        api_key = _from(per_agent, env_var) or os.getenv(env_var, "")
        if api_key:
            explicit = _from(per_agent, "MODEL_NAME")
            _require_explicit_openrouter_model(
                provider, explicit, f"agents/{agent_name}/.env")
            model = explicit or _default_model_for(agent_name)
            return provider, model, api_key

    # Fall through to the shared default.
    provider = _from(shared, "LLM_PROVIDER").lower() or "openai"
    env_var = _API_KEY_ENV_VARS.get(provider)
    if env_var is None:
        raise ValueError(
            f"Shared agents/.env has unknown LLM_PROVIDER "
            f"'{provider}'.  Supported: {', '.join(_API_KEY_ENV_VARS)}."
        )
    api_key = _from(shared, env_var) or os.getenv(env_var, "")
    if not api_key:
        raise ValueError(
            f"No API key found for agent '{agent_name}'.  Either set "
            f"{env_var} in agents/.env or fill "
            f"agents/{agent_name}/.env with a complete LLM_PROVIDER + "
            f"key + MODEL_NAME triple."
        )
    explicit = _from(shared, "MODEL_NAME")
    _require_explicit_openrouter_model(provider, explicit, "agents/.env")
    model = explicit or _default_model_for(agent_name)
    return provider, model, api_key


def build_llm(agent_name: str) -> Tuple[object, str, str]:
    """Build the LLM for ``agent_name`` and return ``(llm, provider, model)``.

    The provider tag is returned alongside the LLM so callers can pass
    it to ``make_image_block`` (image content blocks differ by
    provider).  Provider names are lowercased, e.g. ``"openai"``,
    ``"anthropic"``, ``"google"``.
    """
    provider, model, api_key = _resolve_config(agent_name)
    return _construct_llm(provider, model, api_key), provider, model


def build_llm_for(provider: str, model: str) -> Tuple[object, str, str]:
    """Build an LLM from an EXPLICIT ``(provider, model)`` pair.

    For callers that choose the model themselves rather than reading it
    off an agent's ``.env`` — today the Database Handler's interview
    model (``DH_INTERVIEW_PROVIDER`` / ``DH_INTERVIEW_MODEL`` in the
    "Session saving" section of settings.py), which deliberately
    overrides whatever each interviewed agent runs on live.

    Everything else matches :func:`build_llm`: the API key is resolved
    from ``agents/.env`` then the process environment, and the client
    gets the same shared rate limiter and request timeout.  Raises
    ``ValueError`` on an unknown provider or a missing key, so a
    mis-typed setting fails with a clear message instead of a provider
    401 mid-way through a save.
    """
    provider = (provider or "").strip().lower()
    env_var = _API_KEY_ENV_VARS.get(provider)
    if env_var is None:
        raise ValueError(
            f"Unknown provider {provider!r}.  Supported: "
            f"{', '.join(_API_KEY_ENV_VARS)}."
        )
    shared = _read_shared_env()
    api_key = (shared.get(env_var) or "").strip() or os.getenv(env_var, "")
    if not api_key:
        raise ValueError(
            f"Provider {provider!r} selected but {env_var} is not set in "
            f"agents/.env or the process environment."
        )
    model = (model or "").strip()
    _require_explicit_openrouter_model(
        provider, model, "An explicit provider/model selection",
    )
    if not model:
        model = _DEFAULT_MODEL
    return _construct_llm(provider, model, api_key), provider, model


def _construct_llm(provider: str, model: str, api_key: str):
    """Instantiate the provider client.  Shared by both builders above so
    the rate limiter, timeout and OpenRouter base-url handling cannot
    drift between the per-agent path and the explicit-pair path."""
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            rate_limiter=_RATE_LIMITER,
            timeout=_LLM_REQUEST_TIMEOUT_S,
        )
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            rate_limiter=_RATE_LIMITER,
            timeout=_LLM_REQUEST_TIMEOUT_S,
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(
            model=model,
            api_key=api_key,
            rate_limiter=_RATE_LIMITER,
            timeout=_LLM_REQUEST_TIMEOUT_S,
        )
    elif provider == "openrouter":
        # OpenAI-compatible endpoint — same client, base_url override.
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            rate_limiter=_RATE_LIMITER,
            timeout=_LLM_REQUEST_TIMEOUT_S,
        )
    else:
        # Defensive — _resolve_config already validated, but keep this
        # path so a future provider key omitted from the dispatch table
        # surfaces as a clear error rather than a silent miss.
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")

    return llm


def list_agent_configs(agent_names: list[str]) -> list[dict]:
    """Resolve provider/model for each agent without constructing the LLM.

    Used by the loader to print a per-agent config summary at startup.
    Returns a list of ``{agent, provider, model, source}`` dicts.

    ``source`` is one of:
      * ``'global'``   — ``LLM_ROUTING_MODE`` forces a provider
      * ``'per-agent'``— the per-agent .env supplied a full override
      * ``'shared'``   — falls back to ``agents/.env``
    """
    shared = _read_shared_env()
    mode = _current_routing_mode()
    if mode in {"openai", "anthropic", "google", "openrouter"}:
        shared_model = (shared.get("MODEL_NAME") or _DEFAULT_MODEL).strip()
        return [
            {"agent": name, "provider": mode,
             "model": shared_model, "source": "global"}
            for name in agent_names
        ]

    out: list[dict] = []
    for name in agent_names:
        per_agent = _read_env_file(name)
        per_provider = (per_agent.get("LLM_PROVIDER") or "").strip().lower()
        per_key_var = _API_KEY_ENV_VARS.get(per_provider)
        per_has_key = bool(
            per_key_var
            and (
                (per_agent.get(per_key_var) or "").strip()
                or os.getenv(per_key_var, "").strip()
            )
        )
        if per_provider and per_key_var and per_has_key:
            provider = per_provider
            model = (per_agent.get("MODEL_NAME") or "").strip() or _default_model_for(name)
            source = "per-agent"
        else:
            provider = (
                shared.get("LLM_PROVIDER") or "openai"
            ).strip().lower()
            model = (
                shared.get("MODEL_NAME") or _default_model_for(name)
            ).strip()
            source = "shared"
        out.append(
            {
                "agent": name,
                "provider": provider,
                "model": model,
                "source": source,
            }
        )
    return out


def make_image_block(b64_data: str, provider: str, media_type: str = None) -> dict:
    """Build a provider-appropriate image content block.

    ``provider`` is the lowercase tag returned by ``build_llm``.  Any
    non-Anthropic provider gets the OpenAI-style ``image_url`` block,
    which both OpenAI and Google accept.  ``media_type`` is auto-detected
    from the image bytes when not given, so JPEG (and other formats) are
    labelled correctly rather than always as ``image/png``.
    """
    if media_type is None:
        try:
            media_type = sniff_media_type(base64.b64decode(b64_data[:16]))
        except Exception:
            media_type = "image/png"
    if provider == "anthropic":
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": b64_data,
            },
        }
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{b64_data}"},
    }


def encode_image(image_path: Path, is_render: bool = False) -> str:
    """Read an image and return the base64 of its MODEL-facing copy.

    The copy is downscaled per the image's stored compression degree
    (size-based auto-default when untuned); the on-disk original is never
    modified — OCR / embeddings read it directly.  ``is_render`` marks a
    software-generated render so the renders toggle applies.
    """
    p = Path(image_path)
    if is_render:
        # Renders use the per-type degree + lower floor from settings (chosen by
        # the render's canonical filename), NOT a per-image sidecar.
        deg, floor = render_degree_and_floor(p)
        raw = compress_for_model(p.read_bytes(), deg, is_render=True, floor=floor)
    else:
        raw = compress_for_model(p.read_bytes(), read_degree(p), is_render=False)
    return base64.b64encode(raw).decode()


def encode_image_bytes(raw: bytes, degree_pct=None, is_render: bool = False,
                       name: str = None) -> str:
    """Base64 of the MODEL-facing (downscaled) copy of in-memory image bytes.

    For images fetched from R2; the caller keeps the untouched original bytes
    for OCR.  ``degree_pct`` None => size-based auto-default.  When ``is_render``
    and ``name`` is the render's filename/key, the per-render-type degree + the
    lower render floor from settings are used (matching the live
    ``encode_image`` path).
    """
    floor = None
    if is_render and name is not None:
        rdeg, rfloor = render_degree_and_floor(name)
        if rdeg is not None:
            degree_pct, floor = rdeg, rfloor
    return base64.b64encode(
        compress_for_model(raw, degree_pct, is_render=is_render, floor=floor)
    ).decode()


# ----------------------------------------------------------------------
# Prompt caching (Anthropic only) — see workflow_settings/settings.py §29
# and extra_utilities/docs/reference/design_prompt_caching.md
# ----------------------------------------------------------------------
# Both breakpoints are built from ONE ttl value here.  Anthropic returns
# a 400 when the automatic breakpoint lands on a block that already
# carries an explicit ``cache_control`` with a DIFFERENT ttl, so routing
# every marker through this module makes that divergence impossible
# rather than merely unlikely.

_CACHE_SCOPES = ("off", "system", "system+history")

# Which pair of settings a call reads.  The MACHINERY is identical for
# both phases — same breakpoints, same markers, same request shape; the
# phase only selects WHICH two settings are consulted, so the save can
# be tuned or measured without disturbing the session.  Anything that
# does not name a phase gets "session", which is why every pre-existing
# call site keeps its exact previous behaviour.
_CACHE_SETTING_NAMES = {
    "session": ("PROMPT_CACHE_SCOPE", "PROMPT_CACHE_TTL"),
    "save": ("PROMPT_CACHE_SCOPE_SAVE", "PROMPT_CACHE_TTL_SAVE"),
}


def _cache_settings(phase: str = "session") -> "tuple[str, str]":
    """Live (scope, ttl) for *phase*, read off the imported settings module.

    Read at call time (not import time) so a Workflow-Settings save that
    triggers ``web_app._build_session``'s reload is picked up on the next
    session build, matching how every other live setting behaves here.
    Unrecognised values fall back to the safe defaults rather than raise
    — including an unrecognised *phase*, which falls back to "session".
    """
    scope_name, ttl_name = _CACHE_SETTING_NAMES.get(
        phase, _CACHE_SETTING_NAMES["session"]
    )
    scope = str(getattr(_workflow_settings, scope_name, "system")).strip()
    if scope not in _CACHE_SCOPES:
        scope = "system"
    ttl = str(getattr(_workflow_settings, ttl_name, "5m")).strip()
    if ttl not in ("5m", "1h"):
        ttl = "5m"
    return scope, ttl


def _cache_control_dict(ttl: str) -> dict:
    """``cache_control`` payload for *ttl*.  5m is the API default and is
    expressed by OMITTING the field — do not send ``"ttl": "5m"``."""
    return {"type": "ephemeral"} if ttl == "5m" else {"type": "ephemeral", "ttl": ttl}


def system_cache_control(provider: str, phase: str = "session") -> "dict | None":
    """Marker for the EXPLICIT breakpoint on an agent's system prompt.

    Returns ``None`` when caching is off or the provider is not Anthropic
    (no other provider accepts the field).  *phase* selects which pair of
    settings governs the decision — see ``_CACHE_SETTING_NAMES``.
    """
    if provider != "anthropic":
        return None
    scope, ttl = _cache_settings(phase)
    if scope == "off":
        return None
    return _cache_control_dict(ttl)


def history_cache_control(provider: str, phase: str = "session") -> "dict | None":
    """Value for the TOP-LEVEL ``cache_control`` request parameter — the
    AUTOMATIC breakpoint that advances with the growing conversation.

    Returned only for scope ``"system+history"``; ``None`` otherwise, so
    the kwarg is simply not passed and the request is byte-identical to
    the pre-caching shape.  ``ChatAnthropic._llm_type == "anthropic-chat"``
    means ``langchain_anthropic`` leaves this in ``kwargs`` and it reaches
    the Messages API as the top-level parameter; the API then places the
    breakpoint on the last cacheable block itself, so nothing here has to
    rewrite message content (and nothing can drift between calls).

    *phase* selects which pair of settings governs the decision — see
    ``_CACHE_SETTING_NAMES``.
    """
    if provider != "anthropic":
        return None
    scope, ttl = _cache_settings(phase)
    if scope != "system+history":
        return None
    return _cache_control_dict(ttl)


def make_system_message(
    prompt: str, provider: str, phase: str = "session"
) -> SystemMessage:
    """Build a provider-appropriate ``SystemMessage`` for the agent's prompt.

    Anthropic supports explicit prompt caching via a ``cache_control``
    block on the last system content block to be cached.  Each agent's
    system prompt is fixed for the lifetime of the session (it is
    assembled at wiring time and never mutated per-turn), so it is a
    clean cache prefix — every subsequent ``llm.invoke()`` within ~5
    minutes hits the cache and is billed at ~10% of the normal input-
    token rate.  Without caching, a multi-agent dispatcher loop re-
    transmits and re-bills the full system prompt on every turn, which
    blows through Anthropic's per-minute input-token rate limits and
    significantly inflates cost on OpenAI as well.

    For Anthropic the prompt is wrapped in a single text content block
    tagged with a ``cache_control`` marker whose ttl comes from
    ``PROMPT_CACHE_TTL``.  ``langchain_anthropic`` preserves the field
    (``_format_text_block`` keeps ``cache_control`` in its allow-list),
    so the marker reaches the API intact.  When ``PROMPT_CACHE_SCOPE``
    is ``"off"`` no marker is emitted and the plain-string form is used
    instead, which is what makes a true no-caching baseline measurable.

    For OpenAI the prompt is returned as a plain-string ``SystemMessage``
    — OpenAI applies prompt caching automatically (50% discount on
    matching prefixes ≥1024 tokens) with no API surface, so an
    explicit marker would just be ignored.

    Other providers (Google etc.) get the plain-string form because the
    langchain bindings for those providers do not currently surface a
    cache-control mechanism through ``SystemMessage`` content blocks.

    *phase* selects which settings pair governs the marker.  It defaults
    to ``"session"``, so the 13 in-session call sites are unaffected; the
    post-session Database Handler passes ``"save"`` so its system marker
    obeys the same switch as its history marker rather than splitting
    across the two settings pairs.
    """
    cc = system_cache_control(provider, phase)
    if cc is not None:
        return SystemMessage(
            content=[{"type": "text", "text": prompt, "cache_control": cc}]
        )
    return SystemMessage(content=prompt)
