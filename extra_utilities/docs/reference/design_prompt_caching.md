# Prompt Caching — how it works, and what it means for this system

Reference + design notes for Anthropic prompt caching in the multi-agent
propeller configurator. Written 2026-08-04 while scoping **conversation-history
caching (CHC)**.

> **Status.** Today the system caches **only the system prompt**, and **only for
> Anthropic** (`make_system_message` in `agents/shared/llm_provider.py`). The
> growing conversation history is re-sent and re-billed at full price on every
> call. This document is the basis for changing that.
>
> All API facts below were verified against Anthropic's official prompt-caching
> documentation on 2026-08-04. All timing/behaviour numbers were measured from
> four real production logs (see §6).

---

## 1. The principle — what a cache entry actually is

A cache entry is **not** "this conversation is cached". It is:

```
hash(exact token sequence from position 0 → N)  →  the model's precomputed state
```

Processing input tokens is the expensive half of a request: the model must run
over every input token before generating anything. Caching stores that
precomputed work, **keyed by a hash of the exact tokens that produced it**.

So the cache is a **content-addressed hash map**, not a session object. It is
memoisation: `f(prefix) → work already done`.

Three consequences follow directly, and they explain nearly every caching
behaviour worth knowing:

| Consequence | Why |
|---|---|
| **One changed byte anywhere in the prefix loses the hit** | Different bytes → different hash → the key simply does not exist. Nothing is "invalidated"; the lookup misses. |
| **Different agents never evict each other** | Different system prompts → different hashes → different keys. They coexist like two keys in a dict. |
| **A miss costs the *whole* prefix, never a fraction** | A hash lookup either finds precomputed state for that exact prefix or it does not. There is no partial hit. |

### The API is stateless

Request #2 does not know it is "the same conversation" as request #1. There is
no session handle. The only thing linking them is that request #2's tokens
*start with* request #1's tokens. Every request must re-find its match by
hashing.

---

## 2. Breakpoints

A breakpoint is a `cache_control` marker on a content block. **Maximum 4 per
request.** It does two jobs:

1. **On this request:** write one cache entry — a hash of the prefix ending at
   that block.
2. **On the next request:** serve as the starting point of the backward search.

The prefix is assembled in the order `tools` → `system` → `messages`, and a
marker caches **everything from position 0 up to and including its block**.

> **A marker on the last system block already covers the bound tools**, because
> tools render first. Spending a separate breakpoint on tools caches the same
> bytes twice and buys nothing.

Extra breakpoints are **nearly free**: entries are nested prefixes and writes
bill per token, so marking three positions does not write the history three
times — each delta is written once. The only cost of more breakpoints is code
complexity.

---

## 3. The 20-block lookback

**The 20 is not a size limit.** A single cache entry can cover 100+ blocks;
there is no documented maximum entry size. The 20 is a limit on the *backward
search distance*.

How a read works:

1. Hash the prefix at your current breakpoint. If an entry exists, hit.
2. Otherwise step backward one block at a time, hashing each earlier position,
   **for at most 20 positions** (the breakpoint itself counts as position 1).
3. It is looking for entries **previous requests wrote at their own
   breakpoints** — not for "stable content".
4. If nothing is found in that window, the search stops (or resumes at the next
   explicit breakpoint, if there is one).

The window counts **all** blocks cumulatively — tools, system, and messages.

### Why a search is needed at all

Because your marker moves. On turn 2 the conversation has grown, so your marker
sits at a new absolute position with brand-new content; the entry written on
turn 1 is a few blocks behind it. The walk is the system probing nearby keys to
find the one the previous request left behind.

```
Turn 1   [system][briefing][A][B]■              ■ = cache_control
          block 1    2      3  4                → writes entry for hash(1-4)

Turn 2   [system][briefing][A][B][C][D]■
          block 1    2      3  4  5  6
         probe 6 → miss, probe 5 → miss, probe 4 → HIT (turn-1 entry)
         → loads state, processes only 5-6 fresh
```

### The only number that matters

Not the session length, not the total block count — just **how many blocks were
added since the last write**. Mark every call and that distance is ~2. Mark once
per agent turn and it can be 24.

### Cost of a lookback failure

The **entire prefix** up to the breakpoint is re-processed and billed as
`cache_creation_input_tokens` — *not* just the blocks beyond the window. Roughly
a **12× swing** on that request (1.25× instead of ~0.1×).

---

## 4. TTL and pricing

| | Multiplier on base input price |
|---|---|
| Cache **read** (hit) | **0.1×** |
| Cache **write**, 5-minute TTL | **1.25×** |
| Cache **write**, 1-hour TTL | **2×** |
| Uncached input | 1× |

- Default TTL is **5 minutes**; `{"type": "ephemeral", "ttl": "1h"}` gives 1 hour.
- **The TTL refreshes for free on every hit.** A continuously-used entry stays
  alive indefinitely.
- On a hit, only the **delta** since the last entry is written — not the whole
  prefix.

### Minimum cacheable prefix (model-dependent, and NOT monotonic)

| Model | Minimum |
|---|---|
| Opus 5 / Fable 5 | 512 |
| **Opus 4.8**, Sonnet 5 / 4.6 / 4.5 | **1024** |
| Opus 4.7, Haiku 3.5 | 2048 |
| Opus 4.6, Opus 4.5, **Haiku 4.5** | **4096** |

Below the minimum, caching is **silently skipped** — no error, just
`cache_creation_input_tokens: 0`.

> Note: with `LLM_ROUTING_MODE` set to a provider name (global override) every
> agent runs the shared model, so a Haiku-per-agent mix in the settings chart is
> not what actually executes. See [[v9_llm_routing_global_override]].

### Verifying

```
total_input = cache_read_input_tokens + cache_creation_input_tokens + input_tokens
```

`input_tokens` counts only tokens **after** the last breakpoint, so a small
number there is expected, not a bug. If `cache_read_input_tokens` is 0 across
repeated requests, something in the prefix is non-deterministic.

---

## 5. Cache scope and isolation

- Entries are isolated **per workspace** on the Claude API.
- **Multiple distinct prefixes coexist simultaneously.** There is no eviction —
  entries disappear only by TTL expiry, never by being displaced.
- **Therefore the "hot potato" handoff is safe:** when agent A hands to agent B,
  A's entry is untouched. When control returns to A, A re-sends its prefix, the
  hash matches, and it is a hit — provided the TTL has not expired.
- The 4-breakpoint limit is **per request**. It is *not* a limit on how many
  agents or conversations can be cached. Nine agents → nine independent entries.
- Caches are **model-scoped**: switching an agent's model produces a different
  key.

---

## 6. Measured behaviour of this system

From four production logs (`ID178`, `ID185`, `ID186`, `ID193`; all
`LLM_ROUTING_MODE: anthropic` → every agent on `claude-opus-4-8`; Context Pruner
present but **never fired**; 1 user turn each; 10–15 min wall clock).

### Revisit gaps (an agent's last call → its next call), 70 measured

| | |
|---|---|
| median | **118 s** |
| p90 | **422 s** |
| max | **878 s** |
| **> 5 min** | **8 / 70 = 11.4 %** |

The misses are **structural**:

| Agent | Sessions with a >5 min gap | Cause |
|---|---|---|
| **Receptionist** | **4 of 4** (606–878 s) | Bookends the session: forwards at the start, replies at the end |
| **Planner** | **3 of 4** (422–583 s) | Plans early, reviews late |
| Orchestrator | 1 of 4 (306 s; also 267 s, 284 s) | Sits on the 300 s boundary |
| Tool Caller, DCOI, DCIC, DCII, UII | 0 | Tight refinement loop, 70–160 s |

### Blocks per activation (≈ 2 blocks per tool round-trip)

| Agent | max blocks in one activation |
|---|---|
| **User Input Inspector** | **24** ← only one over 20 |
| Receptionist | 16 |
| DC Output Inspector | 12 |
| DC Input Creator | 10 |
| Tool Caller | 6 |

Cumulative per agent per session reaches **26–32 blocks** (DCIC, DCOI) — far
over 20, which is **fine**, since entry size is unbounded.

### Conclusion on TTL

For one agent with N calls, prefix P and M expiries, 5-minute TTL beats 1-hour
only while `M < ~0.65` — i.e. **a single expiry per agent per session already
makes 1 hour cheaper**, because an expiry re-writes the whole accumulated prefix
while the 1-hour premium applies only to deltas.

The Receptionist expires in 100 % of sessions and the Planner in 75 %, and
sessions are 10–15 min — well inside one hour. **1 hour is the data-supported
default.** It is also robust to slower models (open-weight/reasoning models will
stretch the 267–306 s Orchestrator gaps past the boundary).

---

## 7. Interaction: image stripping (`KEEP_IMAGES_IN_CONTEXT = False`)

### Confirmed behaviour

`on_operation_end()` fires **only when `agent.run()` returns** — i.e. when the
LLM invokes a routing tool and hands off. Utility tool calls inside `run()` do
**not** trigger it (`agents/orchestrator/orchestrator.py`, dispatch loop).
`strip_image_blocks_from_messages` then removes every `image` / `image_url`
block from that agent's `self.messages` **in place**, leaving the paired
`Loaded image (path: …):` text blocks as a path-only record.

So within one agent run, an image loaded on the first LLM call stays available
for every subsequent LLM call and tool call until the routing tool fires.

Empirically confirmed: UII logged *"stripped 9 image block(s)"* as a single
event at the exact millisecond of its handoff — not nine separate strips.

### Cache consequence

The strip **mutates history after the handoff**, so the agent's prefix on its
*next* activation differs from the prefix it presented during the previous one.
Every cache entry written during an activation that contained image bytes is
therefore unreachable on re-activation — the hash no longer matches.

Cost: **one re-write of the post-anchor history per re-activation of an
image-loading agent.**

Blast radius is small and known: only **UII and DCOI** actually strip (measured
across all four logs). DCOI strips on *every* activation (1–4 images each),
UII on its first. The other six agents' histories are stable and cache
perfectly.

This is the main argument for keeping a breakpoint anchored **after the task
briefing**: when the strip invalidates the post-briefing history, the fallback
is the briefing anchor rather than the system prompt.

### Why `KEEP_IMAGES_IN_CONTEXT` stays `False` — the reason is ATTENTION, not cost

**This is a deliberate model-quality decision, not a token-saving one.** An agent
that carries every image it has ever loaded gets *worse at using them*: attention
is spread across a large pile of images, most of them stale. The DCOI is the
clearest case — with persistence ON it would hold renders from every previous
attempt, and its own prompt then has to warn it that *"those images describe PAST
designs, not the current one"*. Stripping at hand-off keeps each agent's
attention on a **small, current, relevant set** of images, which is what we
actually want it to reason about.

The cost analysis independently agrees, but it is the secondary argument:

- `KEEP=True` would avoid **~zero** image loads. Measured: the UII loads
  *different crops* of the same file, and the DCOI builds a *new composite*
  against a new render each attempt — nothing is a redundant re-fetch of
  identical bytes.
- What it removes is small and flat (one cheap text re-write per re-activation,
  ~$0.05/session at Opus rates, and the 20-block lookback often still finds the
  pre-image entry a few blocks back anyway).
- What it adds **grows with session length**: on a 5-attempt run the DCOI would
  carry ~6 stale composites, on a 10-attempt run ~15 (~17k tokens) on *every*
  call.

**Decision: leave `KEEP_IMAGES_IN_CONTEXT = False`, globally, and do not make it
a per-run setting** — it is a behavioural switch, so varying it inside a
benchmark set would make runs non-comparable.

> Note: images do **not** propagate to downstream agents. `AgentHop.message` is a
> plain `str` and no agent's history is ever seeded from another's, so the flag
> only affects the loading agent's own history. (The `settings.py` comment's
> "downstream agents inherit them too" does not match the code.)

---

## 8. Design rules for this codebase

1. **Never mark the tools block** — the system-prompt marker already covers it.
2. **Keep a stable anchor on the system prompt.** It is assembled once at wiring
   time and never mutated, so it is a clean permanent prefix.
3. **Keep the gap between consecutive writes under 20 blocks.** Marking the last
   block of every request makes the gap ~2 by construction; caching only at turn
   boundaries breaks on UII's 24-block activation.
4. **Nothing non-deterministic before a breakpoint** — no timestamps, no UUIDs,
   no unsorted `json.dumps`.
5. **A Context-Pruner run is a cache reset** (accepted design decision): the
   prune rewrites history, the next call pays one full write, caching resumes.

---

## 9. What was built (Step 1)

Two orthogonal settings — scope decides **what** is cached, ttl decides **how
long** — because a system-only cache still has a lifetime:

| Setting | Values | Default |
|---|---|---|
| `PROMPT_CACHE_SCOPE` | `off` / `system` / `system+history` | `system+history` |
| `PROMPT_CACHE_TTL` | `5m` / `1h` | `5m` |

`system` alone reproduces the pre-change behaviour exactly, which is what makes
an A/B (`system·5m` → `system+history·1h`) isolate what history caching adds.

**Two breakpoints, one ttl.** The explicit marker on the system prompt plus
Anthropic's **top-level automatic** breakpoint, which the API advances along the
growing conversation itself. Officially compatible — *"use an explicit
breakpoint to cache your system prompt, while automatic caching handles the
conversation"* — and together they use 2 of the 4 slots.

Both markers are built by `llm_provider.system_cache_control()` /
`history_cache_control()` from the **same** ttl value. That is deliberate: a
mismatched ttl on the block the automatic breakpoint lands on is a **400**, so
routing every marker through those helpers makes divergence impossible rather
than merely unlikely (see `warnings_developer.md` W40).

**Why the top-level kwarg rather than hand-placed markers.** `cache_control` is
a field on a *block*, so marking a string-content message means coercing it to
block form. Doing that only for the message that currently holds the rolling
marker would make a message's bytes differ between calls as the marker moves —
changing the prefix hash and producing a **100 % miss rate**. Since
`ChatAnthropic._llm_type == "anthropic-chat"`, the kwarg is passed straight
through as the API's top-level parameter and the **server** places the
breakpoint, so no message content is ever rewritten and nothing can drift.

**Wiring.** `invoke_with_retry(..., cache_control=...)` is pure plumbing holding
no policy; each in-session agent passes `history_cache_control(self.provider)` at
its call site, so "who caches" is a grep — no exclusion list to rot.

**Fail-open latch.** `invoke_with_retry` catches a rejection that NAMES
`cache_control` (a binding that does not accept the kwarg, or an API 400 —
including the mismatched-ttl one), latches caching off process-wide, and
retries without it. Caching degrades to off rather than taking a session down.
The latch is deliberately narrow (the message must name the kwarg) so an
unrelated 400 never silently disables it, and it resets on process restart.

> **The latch inverts what a green test means.** Because a rejection is
> swallowed, "no exception reached us" proves nothing — every check can pass
> with the feature entirely disabled. `smoke_test_prompt_cache.py` therefore
> reads `_CACHE_KWARG_DISABLED` directly and FAILS on it; never re-derive
> "it worked" from the absence of an exception.

### Which call sites cache, and which deliberately do not

**The rule: only call sites whose message list persists across turns — or repeats
across calls — get the history breakpoint.** Fifteen do: the 8-agent topology, the
5-agent one (Conductor, Creator), and the Database Handler's 5 post-session sites.
Two are excluded on purpose:

| Excluded | Why |
|---|---|
| **Context Pruner** | Rare one-off summarisation, no persistent history |
| **Orchestrator** feedback-dispatch | Sends a freshly-built `[system] + [instruction]` list |
| **Conductor** feedback-dispatch | Same shape, same reason |

For the two feedback-dispatch sites, `instruction` is rebuilt every call, so an
automatic breakpoint there could only ever write an entry nothing can match — a
pure cache WRITE premium with no offsetting read. Their system prompt is still
cached by the explicit marker, which IS stable across those calls.

### The session-save phase (Database Handler)

Added 2026-08-04. **Same machinery, separate knobs.** The DH reuses the identical
helpers, breakpoints and request shape; `phase="save"` only selects a second pair
of settings (`PROMPT_CACHE_SCOPE_SAVE` / `PROMPT_CACHE_TTL_SAVE`, §30) so the save
can be tuned or measured without disturbing the session. Everything else defaults
to `phase="session"`, which is why the 13 in-session call sites were untouched.

**Why it is the largest single opportunity.** `SCHEDULE` holds **29 fields**, and
`_ask_agent` does `convo_buffer = list(agent_messages)` — re-seeded from the
agent's **full in-session history** — once per field:

| Agent | Fields | Agent | Fields |
|---|---|---|---|
| User Input Inspector | 8 | Receptionist | 3 |
| Planner | 6 | DC Output Inspector | 3 |
| DC Input Creator | 3 | Tool Caller | 2 |
| DC Input Inspector | 3 | Orchestrator | 1 |

Each field runs up to `MAX_DH_TURNS_PER_FIELD = 6` rounds, each round costing one
DH call plus one agent call. So without caching the UII's whole history is re-billed
at full price **at least 8 times** and the Planner's 6.

**Why the repeated prefix is stable.** Nothing mutates `agent_state.messages`
during the save: `list()` copies it and `_ask_agent`'s appends land on the copy.
That byte-stability is a property of *this code*, not of the API — so it is what
`smoke_test_prompt_cache.py`'s `run_save_phase()` exists to test, by re-seeding the
buffer exactly the way the DH does. A growing-history test cannot detect a drifting
re-seed.

#### Two shapes — only one of them is fully cached today

Measured 2026-08-04, `claude-opus-4-8`, and the two shapes behave very differently.

**Shape A — the DH's own side (`self.messages`): fully cached.** It grows
monotonically across all 29 fields, since answers are appended "so subsequent fields
can reference what was just said". Every call's prefix strictly extends the previous
one, so it hits the end-of-messages breakpoint in full — exactly the measured
`system+history` pattern where each call reads back everything the last one wrote
(`read` 8435 → 8464 → 8522 against `write` 29 → 58 → 58).

**Shape B — the agent side (`_ask_agent`): only PARTLY cached.** Measured across
three re-seeded fields:

```
field 1  write=558  read=8435      <- 8435 is the SYSTEM PROMPT alone
field 2  write=558  read=8435      <- flat, not growing
field 3  write=558  read=8435
```

The read is flat at the system-prompt size and the ~520-token base history is
**re-written every field**. Cause: breakpoints exist only on (a) the system prompt
and (b) the end of the messages. Field 1 writes an entry for
`system + base + question-1`; field 2's prefix is `system + base + question-2`,
which diverges at that last block and therefore cannot match it — and **there is no
breakpoint at `system + base`** to fall back to.

**Net effect, worked through.** Within a field, round 1 writes the base at 1.25x and
rounds 2+ read it back at 0.1x (they extend round 1's prefix, so they DO hit). Only
the first round of each field re-pays. For an agent history `H`, `F` fields and `R`
rounds per field:

| | Cost |
|---|---|
| No caching | `F × R × H` |
| Today (shipped) | `F × (1.25H + (R-1) × 0.1H)` |
| With the briefing anchor | `1.25H + (F × R - 1) × 0.1H` |

Break-even against no caching is **R = 2**: a one-round field costs 25% more, a
two-round field 33% less, a three-round field 52% less. Worked for the UII
(`F = 8`, `R = 2`): no caching `16H`, today `10.8H` (**~32% saved**), with the
anchor `2.75H` (**~83% saved**).

So what shipped is a genuine win — roughly a third of what is available. The
remaining two thirds need a **third breakpoint anchored on the last message of the
re-seeded base** (marker ②, "the briefing anchor" — TODO F55).

**Why the anchor is not a one-liner.** Marking a message requires coercing its
content into block form, and `convo_buffer = list(agent_messages)` is a *shallow*
copy — mutating a message in place would corrupt live session state shared with the
agent. The anchor must therefore mark a COPY of the last base message, and must
survive whatever that message is (`AIMessage` with `tool_calls`, image blocks left
by the strip, etc.). It also consumes the 4th breakpoint slot: explicit system (1)
+ top-level automatic (2) + anchor (1) = 4, the documented maximum.

**`_ask_agent` uses the AGENT's provider**, not the DH's — it invokes
`agent_base_llm`, which may resolve to a different provider entirely. Passing
`self.provider` there would emit a marker for the wrong provider.

**TTL default is `5m` for the save.** `SCHEDULE` is grouped by agent, so one agent's
fields run back-to-back seconds apart and every hit refreshes the TTL for free — the
prefix stays warm through that agent's block however long the whole save takes.
Revisit after the live measurement (TODO).

**Not cacheable in the save path:** `db_writer.stitch_for_embedding` and
`embeddings.create` use a raw OpenAI client, not langchain — OpenAI caches
automatically with no API surface, so there is nothing to wire.

### Reading the cost in the log

Raw token counts stopped being a cost proxy the moment caching landed. Each
`[TOKENS]` line therefore carries a `billed=` figure in **input-token
equivalents** (`agents/shared/token_usage.py`):

```
billed = uncached + 0.1·cache_read + 1.25·write_5m + 2.0·write_1h
```

```
[DCIC]  tokens  in=8,564  out=142  (cached 8,513 · wrote 49 5m)
                billed=915 in-eq (saves 89%)
```

Equivalents rather than currency, so it stays valid across models with no price
table to drift. Output tokens are billed separately and are NOT included.

Two deliberate behaviours: a **cold call reports a write premium, not a saving**
(`billed=10,575 in-eq (write premium +25%)` — caching only pays back from the
second call), and **nothing is printed for providers that do not report cache
fields**, since OpenAI caches automatically without saying so and a "saves 0%"
there would be an assertion this module cannot support.

**Verify with** `extra_utilities/smoke_test_prompt_cache.py` (live calls, prints
the usage counters, checks the latch never tripped, and that a later call reads
from cache).

### Measured live, 2026-08-04 (`claude-opus-4-8`, ~6.9k-token system prompt)

All four checks passed. Two things this settled that the documentation could not:

1. **The two breakpoints DO coexist.** No rejection, latch never tripped.
2. **`ttl` IS honoured on the write.** Under `ttl=1h` the written tokens landed
   in `ephemeral_1h_input_tokens` with **0** in the 5m bucket — so the top-level
   parameter carries the ttl through, not just the explicit block marker.

The incremental shape is exactly right — write the delta, read the accumulated
prefix (scope `system+history`, ttl 5m):

| call | write | read |
|---|---|---|
| 1 | 0 | 8464 |
| 2 | 58 | 8464 |
| 3 | 58 | 8522 |

> **Do not read a headline saving out of these numbers.** The test's history is
> ~58 tokens per turn against a 6,925-token system prompt, so history caching
> adds only ~5 % here on top of the system-prompt caching that already existed.
> It demonstrates that the mechanism WORKS; it does not measure what it is
> worth. The benefit scales with history size, and production histories are far
> larger (§6: DCIC/DCOI accumulate 26–32 blocks of tool results, parameter
> dumps and renders per session). The real figure has to come from an A/B on a
> benchmark case — `system·5m` vs `system+history·1h` — not from this test.

**Counter-reading gotcha.** `input_token_details["cache_creation"]` is **not**
the write count. When Anthropic returns the per-ttl breakdown,
`langchain_anthropic._create_usage_metadata` moves the tokens into
`ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens` and sets
`cache_creation` to **0**. Reading only `cache_creation` reports "0 writes" on a
run that plainly wrote — sum all three.

**Fail-open.** The kwarg rides on a third-party passthrough
(`langchain-anthropic>=0.3.0`, no ceiling) and on a recent API parameter, while
`invoke_with_retry` re-raises anything that is not a rate-limit/connection
error — and the feature ships enabled. A rejection naming `cache_control` is
therefore caught once, latched process-wide, and the call retried WITHOUT the
kwarg, so caching degrades to off instead of taking every Anthropic turn down.

**Why the default ttl is `5m`, not the `1h` §6 argues for.** The agents that
actually exceed 5 minutes — Receptionist and Planner — carry *small* histories,
so their expiries are cheap; the expensive tight-loop agents revisit every
70–160 s and never expire, so they get the cheaper 1.25× write. `1h` remains the
right answer once a live A/B has measured it.

## 10. Still open

- **⚠ ASSUMPTION, not verified:** that the **top-level** `cache_control`
  parameter honours a `ttl` field. Every documented example of the top-level
  form is the bare `{"type": "ephemeral"}`; `ttl` is documented on *block-level*
  markers. `_cache_control_dict` emits `{"type":"ephemeral","ttl":"1h"}` for
  both. If the top-level form ignores `ttl`, selecting `1h` would give a 1-hour
  system anchor and a 5-minute history breakpoint — the expiries this change
  targets would persist and a cost analysis would wrongly read "1h didn't help".
  The smoke test cannot detect this (two back-to-back calls hit under either
  ttl); only a deliberate >5 min gap would. **Verify before trusting a `1h` A/B.**
- **⚠ The 3-agent (Architect) topology does NOT have this** — TODO **F53**. The
  5-agent topology (Conductor + Creator) does, as of this change.
- **Step 2 (not built):** the briefing anchor (marker ②). Only worth adding if
  measurement shows the post-strip / lookback misses matter; it is the one
  hand-placed marker and so the only place coercion risk returns.
- **OpenRouter gets no cache marker at all**, including for Anthropic models
  served through it (`provider == "openrouter"`, not `"anthropic"`). A Claude
  model routed via OpenRouter silently forfeits caching.
- **Per-run queue override** — the combined per-run dropdown in the Sessions
  Queue is not wired yet; the global Workflow Settings dropdowns are.
- **What history caching is actually WORTH here is still unmeasured.** The
  smoke test proves the mechanism, not the magnitude (see the caveat in §9).
  Measure it with an A/B on one benchmark case: `system·5m` (today's
  behaviour) vs `system+history·1h`, same case and model, comparing the
  session's total `cache_read` / `cache_creation` / uncached input.
- **The 1h LIFETIME is still unproven.** Only the write-side bucket was
  confirmed; that an entry actually survives >5 min needs a real session with
  a gap that long — which the measured Receptionist/Planner revisit gaps (§6)
  would exercise naturally.
- Whether `KEEP_IMAGES_IN_CONTEXT` should change is a **separate, measurable
  question** — deliberately not coupled to this change (§7).
