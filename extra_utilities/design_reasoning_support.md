# Reasoning / extended thinking — design and build plan

**Status:** PLAN ONLY. No code written. Authored 2026-08-08 against branch
`claude/interesting-herschel-1de64d` at `7a9426d`.

**Goal.** Make the models' reasoning visible and controllable: enable thinking
on Anthropic and OpenRouter models, capture the reasoning text, write it to the
session log, keep it correctly in the message history, and expose an ON/OFF
toggle plus a depth control in the Workflow Settings UI.

**Non-goal (deliberate).** OpenAI stays on Chat Completions and stays the
DEFAULT. Today's behaviour must be unchanged when the feature is off. The
Responses API migration that would unlock OpenAI reasoning *content* is
deferred — see §10.

---

## 1. Decisions taken

Each was an explicit choice, recorded so a future session does not re-litigate.

| # | Decision | Why |
|---|---|---|
| D1 | **OpenAI stays on Chat Completions, and it stays the default.** Anthropic + OpenRouter first. | Owner requirement: "the default system behaviour must be as it is today". The Responses migration changes every OpenAI agent call including tool loops. |
| D2 | **Global toggle + per-agent override.** | Mirrors the existing LLM-routing pattern. Lets the Planner reason while the Receptionist stays cheap. See §5.3 for the caveat that makes this partly a lie. |
| D3 | **Keep thinking blocks in the message history.** | Anthropic *requires* verbatim echo inside a tool-use turn; dropping them is a 400. Also preserves the prompt cache. |
| D4 | **ON/OFF plus one shared `REASONING_DEPTH` dropdown**, translated per provider by an adapter. | One knob a human can reason about; per-provider divergence hidden in a table (§4). |
| D5 | **Full reasoning text in the log**, under a distinct prefix. | Owner: reasoning "can be very important". Truncation defeats the purpose. The classifier-skew worry that argued for truncation turned out to be false (§2.4). |

**Verification status.** Every file:line anchor below came from research agents;
the load-bearing ones (L1 prefill loop, L3 pruner blindness, L5 raw-content
return, the client-cache key, the Haiku preset) were **re-read by hand and
confirmed** on 2026-08-08. Anchors not marked as verified should be re-checked
before the code that depends on them is written.
| D6 | **Capability table first, fail-open latch as backstop.** | The table prevents known-bad combinations; the latch catches new models the table has not learned. |
| D7 | **Construction-time injection, with the client-cache key widened.** | langchain-anthropic's forced-tool_choice auto-drop only fires for construction-time thinking. See §6. |
| D8 | **ONE toggle covering both the session and the DH save phase.** | Reversal of an earlier choice. The save *replays* session history, so the two phases are not independent for thinking the way they were for cache TTL (§2.5). |
| D9 | **Adopt the first-party `langchain-openrouter` package.** | `ChatOpenAI` discards OpenRouter's reasoning by design (§3.3). |
| D10 | **Phase 0 first: fix five pre-existing landmines before any thinking ships.** | Each detonates only once thinking is on, and each is defensible on its own merits (§7). |

---

## 2. What is true today (verified, with evidence)

### 2.1 Nothing reasoning-aware exists

A grep for `thinking|reasoning` across `agents/`, `workflow_settings/` and
`web_app.py` returns only prose in prompts plus a read-only token counter at
`token_usage.py:186-188` and `:276-277`. `build_llm` passes exactly
`model`, `api_key`, `rate_limiter`, `timeout` to every provider
(`llm_provider.py:264-297`). No `.bind()`, `model_kwargs`, `extra_body` or
`with_config` anywhere in `agents/`.

### 2.2 On Anthropic, thinking is currently OFF

`claude-opus-4-8` requires an explicit `thinking` parameter to think at all.
This is model-specific and **will change silently if the model changes** —
`claude-sonnet-5` and `claude-opus-5` think by default.

### 2.3 On OpenAI, thinking is probably ON and invisible

GPT-5-family models default to reasoning at `medium`. The counts are already
read and printed (`reasoning N` on the `[TOKENS]` line); the content is not
returned by Chat Completions at all.

### 2.4 The Sessions-Queue classifier does NOT read session logs

`web_app.py:2327` passes `result.reply_text` (the Receptionist's `ai_text()`
output); `sessions_queue.py:313` reads only `block["text"]`. Reasoning in the
log therefore cannot skew it. **An earlier assumption to the contrary was
wrong.** One residual risk remains — see L6 in §7.

### 2.5 `ai_text` is ALREADY thinking-safe

`file_utils.py:37-39` appends only blocks whose `type == "text"`. Anthropic
`thinking` / `redacted_thinking` blocks are already skipped. The Database
Handler's `ASK:`/`SAVE:` protocol (`_parse_dh_decision`, `database_handler.py:531-543`,
called from `:2836`, `:2904`, `:3017`) is therefore **not** at risk.

> **Standing rule: never widen `ai_text` to include reasoning text.** It is a
> one-line change with 15 call sites, three of which feed a parser whose
> contract is that the prefix must *start* the response. Reasoning gets a
> sibling extractor (§8.1), never a branch inside `ai_text`.

---

## 3. Provider reality

### 3.0 Haiku 4.5 is already on three agents — the blast radius is live

`workflow_settings/llm_defaults.py` ships `claude-haiku-4-5` as the Anthropic
preset for the **Orchestrator, Tool Caller and Database Handler** (alongside
`claude-opus-4-8` and `claude-sonnet-4-6` elsewhere). Haiku rejects `adaptive`
outright, so a naive global "thinking on" breaks those three agents **today**,
with no global override involved. `LLM_ROUTING_MODE=anthropic` +
`MODEL_NAME=claude-haiku-4-5` escalates it to total system failure, and the
Sessions Queue does exactly that per queued run via `single_model_payload()`
(`sessions_queue.py:122-133`). This is the single strongest argument for the
capability table (§4). *(Verified by reading the preset, 2026-08-08.)*

### 3.1 Anthropic — no single config works across models

| Model | Mode | Default when `thinking` omitted | Rejects | `effort` |
|---|---|---|---|---|
| `claude-opus-4-8` | Adaptive only | **OFF** | `enabled` → 400 | supported |
| `claude-sonnet-5` | Adaptive only | **ON** | `enabled` → 400 | supported |
| `claude-opus-5` | Adaptive only | **ON** | `enabled` → 400; `disabled` only at effort ≤ `high` | supported |
| `claude-haiku-4-5` | **Extended only** | OFF | **`adaptive` → 400** | **NOT supported** |

Key mechanics:

- **`effort` is `output_config.effort`, not part of the `thinking` object.**
  Passing `adaptive` as an effort value is an error — it is a mode, not a level.
- `display` accepts `"summarized"` or `"omitted"`, and works in both modes.
  It defaults to **`"omitted"`** on opus-4-8 / opus-5 / sonnet-5 / opus-4-7,
  and to `"summarized"` on opus-4-6 / sonnet-4-6 and earlier — **including
  haiku-4-5**. With `"omitted"` the block still arrives, carrying
  `thinking: ""` and only a signature.
- Returned shape: `{"type":"thinking","thinking":"…","signature":"…"}`.
  The raw chain of thought is never returned under any setting.
- `budget_tokens` (haiku only): minimum **1024**, and must be `< max_tokens`.
  The documented interleaved-thinking exception does not apply — haiku-4-5
  does not support interleaved thinking.
- Blocks **must be echoed back verbatim inside a tool-use turn**; a modified
  block returns 400 `…cannot be modified`.
- Any thinking-or-effort change **invalidates the message-tier prompt cache**
  (tools and system tiers survive).
- Thinking tokens bill as **output** tokens; breakdown at
  `usage.output_tokens_details.thinking_tokens`.

LangChain specifics:

- `thinking` is a **first-class top-level `ChatAnthropic` field**, passed
  straight into the payload. Thinking blocks land in `AIMessage.content` as
  **raw dicts**, not in `additional_kwargs`.
- langchain-anthropic **auto-drops a forced `tool_choice` when thinking is on
  — but only when thinking was set at construction** (`chat_models.py:2089-2103`,
  gated on `self.thinking`). This is the whole reason for D7.
- Setting `reasoning_effort` *alone* implicitly turns thinking on
  (`chat_models.py:1466-1476` injects `{"type":"adaptive","display":"summarized"}`),
  but only when the model profile supports `xhigh` — so the same setting
  produces two different request shapes across model generations. **Never set
  `reasoning_effort` alone; always set `thinking` explicitly.**
- Invalid model/thinking combinations raise a **`ValueError` at payload-build
  time** (`chat_models.py:1304-1347`) — before any HTTP call. See L2.

### 3.2 OpenAI — counts only on the current path

- Chat Completions returns **no** reasoning field on the assistant message.
  `reasoning_content` is a third-party (DeepSeek/vLLM/Grok/OpenRouter)
  extension that `langchain_openai` **deliberately refuses to extract**.
- Reasoning defaults **ON at `medium`** for gpt-5, gpt-5.5 and gpt-5.6;
  **OFF (`none`)** for gpt-5.1.
- **Hard blocker for the GPT-5.6 tiers.** On `gpt-5.6-sol/terra/luna`, sending
  function tools to Chat Completions with *any* active reasoning effort
  returns **HTTP 400** — and since those models default to `medium`, it fires
  even when no `reasoning_effort` is sent. Because this system is entirely
  tool-driven, adopting any GPT-5.6 tier on the current path would break every
  agent until either `reasoning_effort="none"` or the Responses API is used.
  **Record this in the model-selection docs.**
- `token_usage.py:186` reads `output_token_details["reasoning"]`, but LangChain
  renames that key to `priority_reasoning` / `flex_reasoning` under the
  priority and flex service tiers — so the counter silently reads zero there.

### 3.3 OpenRouter — the richest source, and the one LangChain drops

- Unified request object: `reasoning: {effort | max_tokens, exclude, enabled}`
  (plus newer `context` and `mode`).
- Returned on the assistant message as **`reasoning`** (plaintext; alias
  `reasoning_content`) and/or **`reasoning_details`** (structured array of
  `reasoning.summary` / `reasoning.encrypted` / `reasoning.text`).
- Broad open-weight support: DeepSeek R1 / V3.1+ / V4, Qwen3 `-thinking`
  variants (incl. Qwen3-VL-thinking), GLM, Kimi, Nemotron, gpt-oss.
  **DeepSeek R1 returns the RAW chain of thought as plaintext** — the only
  provider here that does.
- OpenRouter *does* implement `/v1/responses`, but statelessly: `store: true`
  or a non-null `previous_response_id` return 400.
- **THE CRUX:** `langchain_openai.ChatOpenAI` discards it.
  `_convert_dict_to_message` copies only `function_call`, `tool_calls` and
  `audio` into `additional_kwargs`; `_create_chat_result`'s `llm_output`
  carries only usage / model / fingerprint / id / service_tier. The reasoning
  text appears in **neither** `additional_kwargs` **nor** `response_metadata`.
  Filed as langchain issue #32981, closed by PR #35211, which shipped a
  separate first-party **`langchain-openrouter` (`ChatOpenRouter`)** precisely
  because `ChatOpenAI` "intentionally does not handle" these fields. Hence D9.

---

## 4. The capability adapter (the heart of the design)

One shared depth setting, translated per (provider, model) into the native
request shape. Lives in a new `agents/shared/reasoning_config.py`.

```
resolve_reasoning(provider, model, depth) -> dict of constructor kwargs
```

| Provider / model | Emitted constructor kwargs |
|---|---|
| anthropic, adaptive-capable (opus-4-8/4-7/4-6, opus-5, sonnet-5, sonnet-4-6) | `thinking={"type":"adaptive","display":"summarized"}` + `output_config={"effort": <mapped>}` |
| anthropic, `claude-haiku-4-5` | `thinking={"type":"enabled","budget_tokens":<mapped>,"display":"summarized"}` — **no `output_config`** |
| openai (Chat Completions) | `reasoning_effort=<mapped>` — counts only, no content |
| openrouter | `reasoning={"effort": <mapped>}` via `ChatOpenRouter` |
| google | `{}` — unsupported, documented as inert |

Depth mapping:

| `REASONING_DEPTH` | Anthropic `effort` | Haiku `budget_tokens` | OpenAI `reasoning_effort` | OpenRouter `effort` |
|---|---|---|---|---|
| `low` | `low` | 1024 (the documented minimum) | `low` | `low` |
| `medium` | `medium` | 4096 | `medium` | `medium` |
| `high` | `high` | 8192 | `high` | `high` |

**Rules the adapter must enforce:**

1. Never send `adaptive` to a model in the extended-only set.
2. Never send `output_config.effort` to a model absent from the effort
   compatibility list (currently: haiku-4-5).
3. `budget_tokens` must be `>= 1024` **and** `< max_tokens`; assert this.
4. Always set `display` explicitly — never rely on the per-model default,
   which differs across generations and is the cause of L1.
5. Return `{}` (feature off) for any provider/model the table does not know,
   and **log once at INFO** that reasoning was skipped for that model. Silence
   here is how a "reasoning on" run quietly produces no reasoning.
6. The table is a hardcoded fact set. **It must carry a review-on-model-release
   note**, and the per-model facts must never be inferred from a model name —
   see `warnings_developer.md` W-series on the context-window guessing incident.

---

## 5. Settings and UI

### 5.1 The UI is fully schema-driven — no frontend work

`workflow_settings/editor.py:read_schema()` AST-parses `settings.py`, derives
the control from the type annotation (`bool` → toggle) or from membership in
`ENUM_OPTIONS` (→ dropdown), lifts the `# ====` fenced header into a group
title and the surrounding comment block into the collapsible help text.
`web/app.js:buildControl` already renders both control kinds. **A new bool or
enum setting requires zero frontend changes.**

### 5.2 New settings — a new §31 in `settings.py`

```python
REASONING_ENABLED: bool = False      # default OFF — today's behaviour preserved
REASONING_DEPTH: str = "medium"      # ENUM_OPTIONS: low | medium | high
REASONING_LOG: bool = True           # write captured reasoning to the session log
```

`editor.py` gains `"REASONING_DEPTH": ["low", "medium", "high"]` in
`ENUM_OPTIONS`. Nothing else.

**Default OFF is load-bearing**, per D1: an untouched deployment must behave
exactly as it does today.

### 5.3 Live pickup, and the one thing that needs a restart

`web_app._build_session` calls `importlib.reload(workflow_settings)`
(`web_app.py:301`) on the same module object every consumer holds. So the
established call-time pattern —

```python
getattr(_workflow_settings, "REASONING_ENABLED", False)
```

— picks up a saved change on the **next session**, no restart. This is exactly
what `llm_provider._cache_settings` already does. Module-level constants copied
at import time (`prompts.py:119`, `step_caps.py:132`) would need a restart, so
**reasoning settings must be read at call time, never captured at import.**

### 5.4 Per-agent override — and the caveat that must be documented

Per-agent reasoning follows the LLM-routing tiering in
`llm_provider._resolve_config` (`:175-251`). Three pieces of work:

1. `workflow_settings/llm_routing.py:410-438` currently writes/unsets only
   `LLM_PROVIDER` and `MODEL_NAME`, and `write_updates` rejects a partial
   override (`:393-397`). A `REASONING_*` line added by hand would be orphaned
   — never cleared by a "clear override" click. The writer must learn the new
   keys.
2. `list_agent_configs()` (`llm_provider.py:307-360`) mirrors `_resolve_config`
   and feeds both the startup banner and the routing chart. It needs a
   reasoning column, or the chart under-reports what actually runs — the exact
   class of bug recorded in `v9_llm_routing_global_override.md`.
3. **The caveat:** `LLM_ROUTING_MODE` naming a provider makes `_resolve_config`
   ignore per-agent `.env` files entirely (`:194-210`). A per-agent reasoning
   setting is therefore **silently inert under a global override** — including
   every Sessions-Queue run using `single_model_payload()`
   (`sessions_queue.py:122-133`). This must be stated in the settings help text
   and in `warnings_developer.md`, not just in code comments.

---

## 6. Injection point: construction-time, with a widened cache key

Reasoning kwargs are applied in `build_llm`'s four provider branches
(`llm_provider.py:264-297`), **not** as an invoke-time kwarg.

**Why construction-time.** langchain-anthropic drops a forced `tool_choice`
automatically when thinking is on, but the guard reads `self.thinking` — i.e.
construction-time config only. Three sites force a tool:

- `orchestrator.py:962-965` (Role-4 feedback dispatch to 9 agents)
- `conductor.py:755-757`
- `database_handler.py:2359-2362` (attempt-scoped save)

All three **swallow the exception** and return an empty result with only a
`logger.warning` (`orchestrator.py:1013-1018`, `conductor.py:759-765`,
`database_handler.py:2415`). With invoke-time injection the guard never fires,
the API rejects the combination, and **Role-4 feedback distribution silently
stops happening**. Construction-time gets the guard for free.

**The cost, and its one-line fix.** `llm_client_cache.py:59` keys the memoised
client on `(provider, model, api_key)` only. Under a global override all 12
agents collapse to one entry, so a per-agent construction-time reasoning config
would be a fiction — first agent to build wins, silently. **The cache key must
be widened to include the resolved reasoning config.** Without this, D2 does
not actually work.

---

## 7. Phase 0 — five landmines to fix before any thinking ships

Each detonates only once thinking is on. Each is independently testable and
defensible on its own merits.

### L1 — The Database Handler prefill trap `CRITICAL`

**Where:** `database_handler.py:2822-2838` (`_decide_next`), `:2891-2906`
(`_formulate_question`), `:3004-3019` (`_enforce_semantic…`).

**Mechanism:** each loop does `invoke → self.messages.append(response) →
if not text: continue`. On the retry the appended `AIMessage` is still last —
an **assistant prefill**, which Anthropic forbids while thinking is on.

**Why thinking triggers it:** `display` defaults to `"omitted"` on
opus-4-8 / opus-5 / sonnet-5, so a thinking-only turn yields `ai_text("")` —
which is exactly the condition that fires the empty-text retry branch.

**Blast radius:** none of the three has a try/except around the invoke. The
only guard is `web_app.py:399-408`, which catches at the top of
`populate_database`. **A single 400 anywhere in the ~28-entry schedule aborts
the whole save with zero entries written.**

**Fix:** pop the empty `AIMessage` before retrying (or append a corrective
`HumanMessage`), so the request never ends on an assistant turn. Setting
`display="summarized"` in the adapter (§4 rule 4) makes the branch far rarer
but does **not** remove the trap — fix the loop.

### L2 — The feature fails CLOSED `CRITICAL`

**Where:** `llm_retry.py:117` (`if "cache_control" not in str(exc).lower(): return False`)
and the retryable set at `:64-69`.

**Mechanism:** the `_CACHE_KWARG_DISABLED` latch only trips on exceptions
naming `cache_control`. A thinking 400 will not trip it. Worse,
langchain-anthropic raises a **`ValueError` at payload-build time** for a bad
model/thinking combination — not an API error at all, and not in the retryable
set, so it propagates and kills the turn.

**Fix:** generalise the latch from one hardcoded kwarg into a small registry
(`cache_control`, `thinking`, `output_config`, `reasoning_effort`, `reasoning`),
each with its own module-level disable flag, and extend the classifier to
recognise `ValueError` when the message names one of those keys. Keep the
existing narrowness — the message must still name the kwarg.

> Same inversion as prompt caching: a green test proves nothing once the latch
> exists. The smoke test must read the latch directly (§9).

### L3 — The Context Pruner is BLIND to thinking tokens `HIGH`

**Where:** `_body_text_of` at `base_chain_agent.py:564`; the generic `else`
that swallows thinking is `:584-585`. Consumed by the threshold check at
`:239-241`.

**Mechanism:** `_body_text_of` branches on `text`, `image`/`image_url` and
`tool_use`, then falls through to `else: parts.append(f"[{btype}: ...]")`.
A thinking block therefore renders as the literal string `"[thinking: ...]"`
— about **6 tokens**. A 4,000-token thinking block counts as 6.
*(Verified by reading the function, 2026-08-08.)*

**Consequence:** on keep-all models the real request grows monotonically while
the pruner's estimate stays flat, so **the pruner never fires and the run dies
on a hard provider context limit instead**. The same blindness disarms
`_truncate_oversized_messages` (`:619-624`), so an oversized-because-of-thinking
message never trips `CONTEXT_PRUNER_MAX_INDIVIDUAL_MESSAGE_TOKENS`.

**Fix:** add a thinking branch to `_body_text_of` that returns the block's real
text. This is a latent bug today for any non-text block type, independent of
this feature.

### L4 — The truncator destroys signed blocks but keeps `tool_calls` `HIGH`

**Where:** `base_chain_agent.py:646-654`.

**Mechanism:** `_truncate_oversized_messages` rebuilds an oversized `AIMessage`
as `content=<placeholder string>` while **preserving `tool_calls`**. That is
precisely the shape Anthropic's contract forbids: the `tool_use` survives, the
signed thinking block does not.

**Fix:** when truncating an `AIMessage` that carries `tool_calls`, either
preserve the thinking blocks verbatim alongside the placeholder text, or skip
truncation for that message. Never emit tool_calls without their thinking.

### L5 — The pruner returns a raw block list into `.strip()` `HIGH`

**Where:** `context_pruner.py:182` (`return response.content`) →
`base_chain_agent.py:294-300` / `:308`.

**Mechanism:** tier-1's `.strip()` sits **outside** the try/except that wraps
`pruner.run`. With thinking on the pruner's own model, `content` is a list of
blocks → `AttributeError: 'list' object has no attribute 'strip'` → the
exception escapes and kills the turn.

**Reachability:** the pruner has its own routing row with a `gpt-5.4` default
(`llm_defaults.py:39`) but is built via `build_llm` directly
(`orchestrator.py:205-213`, `conductor.py:196-204`), so
`LLM_ROUTING_MODE=anthropic` silently makes it an Anthropic model **without
anyone opting it in**.

**Fix:** `context_pruner.py:182` returns `ai_text(response.content)`. A summary
is text by definition. Also move the `.strip()` inside the guarded block.

### L6 — Residual: a thinking classifier breaks the Sessions Queue `MEDIUM`

**Where:** `sessions_queue.py:388-399` → `web_app.py:2347-2356`.

**Mechanism:** the classifier bypasses `llm_provider` entirely and reads keys
from `os.environ` (`sessions_queue.py:270-302`). If its model is a thinking
model that returns only a thinking block, `_content_text` yields `""`, neither
verdict word matches, `classify_reply` sets `error: True`, and the runner marks
the run `needs_review`.

**Fix:** apply the adapter to the classifier's client too, or pin it to
non-reasoning. Same for the Context Pruner and the `db_writer` stitching call
(§8.4) — **all three bypass `invoke_with_retry`.**

---

## 8. Phases 1-5 — building the feature

### 8.1 Capture: `ai_thinking()`, a sibling of `ai_text`

New in `agents/shared/file_utils.py`. Extracts `type == "thinking"` blocks and
returns their text; skips `redacted_thinking` (encrypted, no readable text);
returns `""` when there is none. **`ai_text` is not modified** (§2.5).

For OpenRouter the reasoning arrives on `additional_kwargs` rather than in
`content`, so the helper takes the whole message, not just `content`, and
checks both locations.

### 8.2 Logging

Log in `invoke_with_retry` beside `token_usage.record(...)` — the one choke
point that sees all **17** call sites across 11 agent classes, with the agent
label already in hand. Format `[THINKING][<agent>] …`, full text, gated on
`REASONING_LOG`.

**Two calls bypass this choke point** and need their own handling:
`ContextPruner.run` (`context_pruner.py:165`) and the Sessions-Queue classifier
(`sessions_queue.py:369`).

### 8.3 History

Nothing to build. Every agent already does `self.messages.append(response)`
with the whole `AIMessage`, and nothing strips non-text blocks —
`strip_image_blocks_from_messages` touches images only. D3 is satisfied by the
existing code, **provided L4 is fixed**.

### 8.4 OpenRouter via `langchain-openrouter`

Add the dependency; add a `ChatOpenRouter` branch in `build_llm` replacing the
current `ChatOpenAI` + `base_url` construction for `provider == "openrouter"`.
Pin a floor in `requirements.txt`.

**Related version hazard:** `requirements.txt:3` floors `langchain-anthropic`
at `>=0.3.0` with no ceiling, while this worktree has `1.5.3`. The
`thinking` / `output_config` fields **do not exist in 0.3.x**, so a
constructor kwarg would raise `TypeError` on a Railway container that resolved
an older wheel. **Raise the floor to a version known to carry the fields.**

### 8.5 Token accounting and the cost signal

Reasoning tokens are read (`token_usage.py:185-188`) and printed (`:276-277`)
but appear in **no aggregate** (`:82`, `:88-91`, `:321-332`) and in **no
`billed=` figure** (`:211-232`). Turning thinking on inflates `out=` with no
cost indicator, so a Sessions-Queue topology/model matrix would **silently
mis-rank models by cost**. Three fixes:

1. Fold reasoning tokens into the turn and session aggregates.
2. Include them in a cost figure (they bill as output).
3. Read the `priority_reasoning` / `flex_reasoning` key variants (§3.2), and
   note that the legacy `response_metadata["token_usage"]` fallback path
   (`:191-199`) drops reasoning entirely.

---

## 9. Testing

**Offline (no API key, runs in CI):**
- Capability-adapter table tests: every (provider, model) row emits the
  expected kwargs; haiku never receives `adaptive` or `output_config`;
  unknown models return `{}`.
- Settings isolation: `REASONING_ENABLED=False` produces byte-identical
  constructor kwargs to today.
- `ai_thinking()` unit tests over both block shapes (Anthropic content blocks,
  OpenRouter `additional_kwargs`), and an assertion that `ai_text()` output is
  **unchanged** by the presence of thinking blocks.
- Latch registry: a simulated thinking 400 and a simulated `ValueError` both
  trip the thinking latch and not the cache latch.

**Live, per provider** (a new `extra_utilities/smoke_test_reasoning.py`
following the prompt-cache smoke test's shape, including reading the latch
directly so a green run cannot hide a disabled feature):
- Anthropic adaptive model: thinking blocks present, `display` honoured,
  signature present, blocks survive a tool round-trip.
- Anthropic haiku-4-5: extended mode with `budget_tokens` works; adaptive is
  correctly never sent.
- OpenRouter DeepSeek R1: raw reasoning captured through `ChatOpenRouter`.
- A forced-`tool_choice` call with thinking on, to prove the auto-drop fires.

**Regression:** re-run `smoke_test_prompt_cache.py` — thinking changes
invalidate the message-tier cache, so its numbers must be re-baselined with
reasoning on and off.

---

## 10. Deferred

- **OpenAI Responses API.** The only route to OpenAI reasoning *content*.
  Deferred per D1; Chat Completions remains the default and must remain a
  supported option even after any migration. Structure the OpenAI branch so
  the endpoint becomes a setting rather than a rewrite.
- **GPT-5.6 tiers (Sol/Terra/Luna) are currently unusable here** — tools +
  active reasoning on Chat Completions is a 400, and they default to `medium`.
  Adopting them requires `reasoning_effort="none"` or the Responses migration.
- **`db_writer` stitching** (`db_writer.py:275-283`): the one raw-SDK call,
  with `temperature=0.0`, `max_tokens=800` and a free-text UI-editable model.
  Point it at a reasoning model and it either 400s on `temperature` or returns
  empty content and raises a misleading `StitchError`. Out of scope; document
  the constraint next to the setting.

---

## 11. Build order

| Phase | Content | Gate |
|---|---|---|
| **0** | L1-L5 fixes | Each independently reviewed; existing smoke tests green |
| **1** | Settings §31 + `ENUM_OPTIONS`; UI verified | Toggle visible, default OFF, behaviour unchanged |
| **2** | `reasoning_config.py` adapter + offline table tests | All table tests pass |
| **3** | `build_llm` injection + widened client-cache key | Per-agent config provably not shared |
| **4** | `ai_thinking()` + `[THINKING]` logging + L6 bypass paths | Live Anthropic smoke test |
| **5** | `langchain-openrouter` + raised langchain-anthropic floor | Live DeepSeek R1 smoke test |
| **6** | Token accounting + cost signal | Matrix ranks models correctly |

Nothing in Phase 1-6 may ship before Phase 0 is complete (D10).
