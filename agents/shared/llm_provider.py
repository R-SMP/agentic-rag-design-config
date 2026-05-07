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

from workflow_settings import settings as _workflow_settings

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

# Shared agent .env (read once at import).  Falls back to empty dict if
# the file is missing.
_SHARED_ENV_PATH = AGENTS_DIR / ".env"
_SHARED_ENV: dict = (
    dotenv_values(_SHARED_ENV_PATH) if _SHARED_ENV_PATH.exists() else {}
)

_API_KEY_ENV_VARS: dict = {
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

_DEFAULT_MODEL = "gpt-5-mini"


def _read_env_file(agent_name: str) -> dict:
    """Read ``agents/<agent_name>/.env`` if it exists; else empty dict."""
    path = AGENTS_DIR / agent_name / ".env"
    if not path.exists():
        return {}
    try:
        return dotenv_values(path)
    except OSError:
        return {}


def _resolve_config(agent_name: str) -> Tuple[str, str, str]:
    """Pick (provider, model, api_key) for ``agent_name``.

    Resolution order:
      1. The per-agent .env file, if it sets ``LLM_PROVIDER`` and the
         matching API key.
      2. The shared ``agents/.env``.

    Raises ValueError if neither source supplies a usable provider /
    key combination.
    """
    per_agent = _read_env_file(agent_name)

    def _from(layer: dict, key: str) -> str:
        return (layer.get(key) or "").strip()

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
            model = _from(per_agent, "MODEL_NAME") or _DEFAULT_MODEL
            return provider, model, api_key

    # Fall through to the shared default.
    provider = _from(_SHARED_ENV, "LLM_PROVIDER").lower() or "openai"
    env_var = _API_KEY_ENV_VARS.get(provider)
    if env_var is None:
        raise ValueError(
            f"Shared agents/.env has unknown LLM_PROVIDER "
            f"'{provider}'.  Supported: {', '.join(_API_KEY_ENV_VARS)}."
        )
    api_key = _from(_SHARED_ENV, env_var) or os.getenv(env_var, "")
    if not api_key:
        raise ValueError(
            f"No API key found for agent '{agent_name}'.  Either set "
            f"{env_var} in agents/.env or fill "
            f"agents/{agent_name}/.env with a complete LLM_PROVIDER + "
            f"key + MODEL_NAME triple."
        )
    model = _from(_SHARED_ENV, "MODEL_NAME") or _DEFAULT_MODEL
    return provider, model, api_key


def build_llm(agent_name: str) -> Tuple[object, str, str]:
    """Build the LLM for ``agent_name`` and return ``(llm, provider, model)``.

    The provider tag is returned alongside the LLM so callers can pass
    it to ``make_image_block`` (image content blocks differ by
    provider).  Provider names are lowercased, e.g. ``"openai"``,
    ``"anthropic"``, ``"google"``.
    """
    provider, model, api_key = _resolve_config(agent_name)

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=model, api_key=api_key, rate_limiter=_RATE_LIMITER)
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model=model, google_api_key=api_key, rate_limiter=_RATE_LIMITER
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model=model, api_key=api_key, rate_limiter=_RATE_LIMITER)
    else:
        # Defensive — _resolve_config already validated, but keep this
        # path so a future provider key omitted from the dispatch table
        # surfaces as a clear error rather than a silent miss.
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")

    return llm, provider, model


def list_agent_configs(agent_names: list[str]) -> list[dict]:
    """Resolve provider/model for each agent without constructing the LLM.

    Used by the loader to print a per-agent config summary at startup.
    Returns a list of ``{agent, provider, model, source}`` dicts where
    ``source`` is ``'per-agent'`` if the per-agent .env supplied the
    provider+key, otherwise ``'shared'``.
    """
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
            model = (per_agent.get("MODEL_NAME") or "").strip() or _DEFAULT_MODEL
            source = "per-agent"
        else:
            provider = (
                _SHARED_ENV.get("LLM_PROVIDER") or "openai"
            ).strip().lower()
            model = (
                _SHARED_ENV.get("MODEL_NAME") or _DEFAULT_MODEL
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


def make_image_block(b64_data: str, provider: str) -> dict:
    """Build a provider-appropriate image content block.

    ``provider`` is the lowercase tag returned by ``build_llm``.  Any
    non-Anthropic provider gets the OpenAI-style ``image_url`` block,
    which both OpenAI and Google accept.
    """
    if provider == "anthropic":
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": b64_data,
            },
        }
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{b64_data}"},
    }


def encode_image(image_path: Path) -> str:
    """Read an image file and return its base64 encoding."""
    return base64.b64encode(Path(image_path).read_bytes()).decode()


def make_system_message(prompt: str, provider: str) -> SystemMessage:
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
    tagged with ``{"type": "ephemeral"}`` cache control.  ``langchain_
    anthropic`` forwards the typed-dict content list to the Anthropic
    API verbatim, preserving the cache marker.

    For OpenAI the prompt is returned as a plain-string ``SystemMessage``
    — OpenAI applies prompt caching automatically (50% discount on
    matching prefixes ≥1024 tokens) with no API surface, so an
    explicit marker would just be ignored.

    Other providers (Google etc.) get the plain-string form because the
    langchain bindings for those providers do not currently surface a
    cache-control mechanism through ``SystemMessage`` content blocks.
    """
    if provider == "anthropic":
        return SystemMessage(
            content=[
                {
                    "type": "text",
                    "text": prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        )
    return SystemMessage(content=prompt)
