# -*- coding: utf-8 -*-
"""Smoke-test Anthropic prompt caching end to end, through the REAL code path.

Runs a handful of live calls against the Anthropic API and prints the
``usage`` counters for each, so you can see caching actually working (or
not) before committing an overnight benchmark run to it.

It deliberately uses the production helpers — ``make_system_message``,
``history_cache_control`` and ``invoke_with_retry`` — rather than a
parallel implementation, so a pass here means *the shipped path* works.

What it proves
--------------
1. The explicit system-prompt breakpoint and Anthropic's top-level
   automatic breakpoint COEXIST in one request (the API 400s on a
   mismatched-ttl combination, so a clean run rules that out).
2. A second call with the same prefix produces a real cache READ.
3. ``scope="system+history"`` reads back MORE than ``scope="system"``,
   which is the whole point of the change.

Usage
-----
    ANTHROPIC_API_KEY=sk-ant-...  python extra_utilities/smoke_test_prompt_cache.py

Needs the app's environment (langchain-anthropic installed) — run it
where the app runs, not in a bare py3.8 checkout.  Costs a few cents:
four short calls with a ~2k-token system prompt.
"""
from __future__ import annotations

import os
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)


def _stub_agents_package() -> None:
    """Let ``agents.shared.*`` import without running ``agents/__init__.py``.

    That file does ``from agents.orchestrator import Orchestrator``, which
    transitively pulls in the Database Handler (psycopg, pgvector, boto3) and
    the render backends (trimesh, pyvista, pyrender, compute_rhino3d,
    DracoPy).  None of it is reachable from the LLM path this test exercises,
    and installing that stack just to make three API calls is slow and, on
    Windows, prone to failing outright.

    Registering a stub module whose ``__path__`` points at the real directory
    makes submodule imports resolve normally against the filesystem while the
    real package ``__init__`` never executes.  ``agents/shared/__init__.py``
    is a bare docstring, so it is left to load for real.

    Import-shape only — the modules under test are the genuine ones, so this
    does not weaken what the test proves.
    """
    if "agents" in sys.modules:
        return
    pkg = types.ModuleType("agents")
    pkg.__path__ = [os.path.join(_ROOT, "agents")]
    sys.modules["agents"] = pkg


_stub_agents_package()

from langchain_core.messages import HumanMessage  # noqa: E402

from workflow_settings import settings as _settings  # noqa: E402
from agents.shared import llm_provider as lp  # noqa: E402
from agents.shared import llm_retry as _retry  # noqa: E402
from agents.shared.llm_retry import invoke_with_retry  # noqa: E402

# Must comfortably exceed the model's minimum cacheable prefix or caching is
# SILENTLY skipped (Opus 4.8 = 1024 tokens, but Haiku 4.5 / Opus 4.6 = 4096).
# 200 repeats ~= 28k chars ~= 7k tokens, well clear of the 4096 floor so a
# "no cache read" verdict can never be an artefact of an undersized prefix.
BIG_SYSTEM = (
    "You are a meticulous propeller-design assistant. Answer with a single "
    "short sentence and no preamble.\n"
) + "\n".join(
    "Reference note %03d: blade sections are defined by thickness, camber "
    "and high-point, expressed as percentages of that section's own chord." % i
    for i in range(200)
)


def _usage(resp) -> dict:
    """Token counters for one response.

    ``cache_creation`` alone is NOT the write count.  When Anthropic returns
    the per-ttl breakdown, ``langchain_anthropic._create_usage_metadata``
    moves the tokens into ``ephemeral_5m_input_tokens`` /
    ``ephemeral_1h_input_tokens`` and sets ``cache_creation`` to 0 — so
    reading only that key reports "0 writes" on a run that plainly wrote
    (a later call cannot read tokens nobody wrote).  Sum all three.

    The per-ttl split is also the only cheap evidence of whether the ttl
    was HONOURED on the write: a 1h request whose tokens land in the 5m
    bucket means the ttl was ignored, and that is visible immediately
    instead of needing a >5 min gap.
    """
    u = getattr(resp, "usage_metadata", None) or {}
    details = u.get("input_token_details", {}) if isinstance(u, dict) else {}
    w5 = details.get("ephemeral_5m_input_tokens") or 0
    w1h = details.get("ephemeral_1h_input_tokens") or 0
    generic = details.get("cache_creation") or 0
    return {
        "input": u.get("input_tokens", 0) if isinstance(u, dict) else 0,
        "cache_write": generic + w5 + w1h,
        "write_5m": w5,
        "write_1h": w1h,
        "cache_read": details.get("cache_read") or 0,
    }


def _show(tag: str, resp) -> dict:
    u = _usage(resp)
    print("    %-20s input=%-7d write=%-7d (5m=%-6d 1h=%-6d) read=%-7d"
          % (tag, u["input"], u["cache_write"], u["write_5m"], u["write_1h"],
             u["cache_read"]))
    return u


def run_scope(scope: str, ttl: str, n_calls: int = 3) -> list:
    """Drive n_calls with a GROWING history under the given scope/ttl.

    Clears ``invoke_with_retry``'s fail-open latch first.  That latch exists
    to keep a live session alive when the API rejects the top-level kwarg —
    it swallows the rejection, drops the kwarg and retries — which is exactly
    right in production and exactly WRONG here: it would silently disable the
    feature this test exists to prove and every check below would still pass.
    ``latch_tripped()`` is what actually decides the verdict.
    """
    _retry._CACHE_KWARG_DISABLED = False
    _settings.PROMPT_CACHE_SCOPE = scope
    _settings.PROMPT_CACHE_TTL = ttl
    print("\n--- scope=%s ttl=%s ---" % (scope, ttl))
    print("    system_cache_control  -> %s" % (lp.system_cache_control("anthropic"),))
    print("    history_cache_control -> %s" % (lp.history_cache_control("anthropic"),))

    llm, provider, model = lp.build_llm("planner")
    # Print what ACTUALLY resolved — never a constant.  Which model ran is
    # the fact needed to read a "no cache read" verdict (the 4096-token
    # floor on Haiku 4.5 / Opus 4.6 vs 1024 on Opus 4.8), and a banner that
    # names the wrong model has already misled a real run analysis in this
    # project (see the LLM_ROUTING_MODE global-override case).
    print("    resolved routing      -> provider=%s model=%s" % (provider, model))
    if provider != "anthropic":
        print("    SKIP: routing resolves to %r, not anthropic" % provider)
        return []

    history: list = []
    out = []
    for i in range(1, n_calls + 1):
        history.append(HumanMessage(content=(
            "Question %d. Restate in one short sentence what a blade "
            "section's camber is measured against." % i
        )))
        resp = invoke_with_retry(
            llm,
            [lp.make_system_message(BIG_SYSTEM, provider)] + history,
            "smoke",
            cache_control=lp.history_cache_control(provider),
        )
        history.append(resp)
        out.append(_show("call %d" % i, resp))
    return out


def _check_key() -> "str | None":
    """Validate the API key's SHAPE before spending a call on a 401.

    Accepts it from either source the app itself accepts — the process
    environment or ``agents/.env`` — so the key does not have to be re-exported
    into every new shell.  Never prints the key: only its source, length and
    prefix, which is enough to tell "unset" from "placeholder" from "truncated"
    without putting a secret in the terminal scrollback or a pasted log.

    Returns an error string, or None when the key looks usable.
    """
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    source = "environment"
    if not key:
        try:
            from dotenv import dotenv_values
            key = (dotenv_values(
                os.path.join(_ROOT, "agents", ".env")
            ).get("ANTHROPIC_API_KEY") or "").strip()
            source = "agents/.env"
        except Exception:
            key = ""
    if not key:
        return ("no API key found. Set $env:ANTHROPIC_API_KEY, or add "
                "ANTHROPIC_API_KEY=... to agents/.env (gitignored).")
    if "REPLACE_ME" in key or key.lower() in ("sk-ant-...", "your-key"):
        return ("the key is still the PLACEHOLDER (%r) — substitute your real "
                "key." % key[:16])
    if not key.startswith("sk-ant-"):
        return ("key from %s does not start with 'sk-ant-' (starts %r, len %d) "
                "— likely mangled by shell quoting." % (source, key[:7], len(key)))
    if len(key) < 40:
        return ("key from %s is only %d chars — looks truncated."
                % (source, len(key)))
    # Make it visible to _resolve_config, which reads os.getenv as its
    # fallback; a key that came from agents/.env is otherwise invisible to it.
    os.environ["ANTHROPIC_API_KEY"] = key
    print("api key: source=%s len=%d prefix=%s…" % (source, len(key), key[:10]))
    return None


def main() -> int:
    problem = _check_key()
    if problem:
        print("ANTHROPIC_API_KEY problem — %s" % problem)
        return 2
    print("system prompt ~%d chars (~%d tokens)  — each scope prints the "
          "model it actually resolved" % (len(BIG_SYSTEM), len(BIG_SYSTEM) // 4))

    base = dict(scope=_settings.PROMPT_CACHE_SCOPE, ttl=_settings.PROMPT_CACHE_TTL)
    latched = {}
    try:
        sys_only = run_scope("system", "5m")
        latched["system·5m"] = _retry._CACHE_KWARG_DISABLED
        both = run_scope("system+history", "5m")
        latched["system+history·5m"] = _retry._CACHE_KWARG_DISABLED
        both_1h = run_scope("system+history", "1h", n_calls=2)
        latched["system+history·1h"] = _retry._CACHE_KWARG_DISABLED
    finally:
        _settings.PROMPT_CACHE_SCOPE = base["scope"]
        _settings.PROMPT_CACHE_TTL = base["ttl"]
        _retry._CACHE_KWARG_DISABLED = False

    print("\n================ VERDICT ================")
    ok = True

    if not both:
        print("INCONCLUSIVE: routing is not on Anthropic.")
        return 2

    # 1. Did the top-level kwarg survive?  This MUST be read off the latch,
    #    not inferred from "no exception reached us": invoke_with_retry fails
    #    OPEN on a cache_control rejection — it swallows the error, drops the
    #    kwarg and retries — so every other check below would still pass with
    #    the feature entirely disabled.  The latch is the only witness.
    tripped = [k for k, v in latched.items() if v]
    if tripped:
        ok = False
        print("FAIL  the top-level cache_control kwarg was REJECTED and "
              "silently disabled during: %s" % ", ".join(tripped))
        print("      => the two breakpoints do NOT coexist as assumed. See the")
        print("         'prompt-cache kwarg rejected' warning above for the")
        print("         API's reason. Fallback: drop the top-level kwarg and")
        print("         hand-place both markers (design doc §10).")
    else:
        print("PASS  explicit system breakpoint + top-level automatic "
              "breakpoint coexist (kwarg never rejected).")

    # 2. a cache read happened on a later call
    if any(c["cache_read"] > 0 for c in both[1:]):
        print("PASS  cache READ observed on a later call.")
    else:
        print("FAIL  no cache read on any later call — prefix may be unstable.")
        ok = False

    # 3. history caching reads back more than system-only
    if sys_only and both:
        s = max(c["cache_read"] for c in sys_only)
        b = max(c["cache_read"] for c in both)
        if b > s:
            print("PASS  system+history reads back MORE than system-only "
                  "(%d vs %d tokens)." % (b, s))
        else:
            print("WARN  system+history did not read back more than "
                  "system-only (%d vs %d) — check the growing history." % (b, s))

    # 4. Was the ttl honoured ON THE WRITE?  Read-back alone cannot tell a
    #    5-minute entry from a 1-hour one over back-to-back calls, but the
    #    per-ttl write buckets can: Anthropic reports which bucket the
    #    tokens landed in, so a 1h request whose writes appear under 5m
    #    means the ttl was silently ignored.  This still does NOT prove the
    #    LIFETIME is honoured — only a >5 min gap would — but it does catch
    #    the failure mode that would otherwise hide until an overnight run.
    if both_1h:
        w1h = sum(c["write_1h"] for c in both_1h)
        w5 = sum(c["write_5m"] for c in both_1h)
        if w1h > 0 and w5 == 0:
            print("PASS  ttl=1h honoured on the write (%d tokens in the 1h "
                  "bucket, 0 in the 5m bucket)." % w1h)
        elif w1h == 0 and w5 > 0:
            print("FAIL  ttl=1h was IGNORED — %d write tokens landed in the "
                  "5m bucket and 0 in the 1h bucket." % w5)
            ok = False
        elif w1h == 0 and w5 == 0:
            print("INFO  ttl=1h: no cache writes occurred in this scope "
                  "(everything was already cached), so the ttl bucket is "
                  "unobservable here.")
        else:
            print("WARN  ttl=1h: writes split across buckets (1h=%d, 5m=%d) "
                  "— inspect the per-call lines above." % (w1h, w5))
        print("      Bucket placement is a WRITE-side check; the 1h lifetime "
              "itself is only provable with a >5 min gap (design doc §10).")

    # Cross-check the instrument itself: a read is impossible without a
    # prior write, so all-zero writes beside non-zero reads means the
    # counters are being misread, not that caching is free.
    all_calls = (sys_only or []) + (both or []) + (both_1h or [])
    if any(c["cache_read"] > 0 for c in all_calls) and \
            not any(c["cache_write"] > 0 for c in all_calls):
        print("WARN  reads observed but zero writes reported across every "
              "call — the usage counters are being misread; treat the "
              "numbers above as unreliable.")

    print("=========================================")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
