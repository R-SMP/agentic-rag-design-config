# Known issues, temporary fixes, and TODOs

This file tracks open issues in the codebase and any **temporary** /
**stop-gap** patches that have been applied to work around them.
Each entry should record:

- **What** the bug is and how to reproduce / observe it.
- **Why** the fix is temporary (what the proper fix would look like).
- **Where** the temporary patch lives in the code (file paths +
  search strings) so reverting it is mechanical.
- A **status** field so future-you can scan the open list at a glance.

When a temporary fix is replaced by the proper fix, move the entry
to a "Resolved" section at the bottom (or delete it, with a brief
note in the commit message).

---

## Open issues

### O1. Database Handler: handle dangling tool_use in frozen snapshots

**Where.** `agents/database_handler/database_handler.py:_freeze_histories`.

**What.** When the DH freezes an agent's history at end of session,
the agent's last `AIMessage` may contain `tool_calls` whose matching
`ToolMessage` blocks were never appended.  Concretely this can
happen if the session crashed mid-tool-call, if step-limit
exhaustion fired before the inner loop appended the tool_result, or
if a routing-tool invocation interleaved with utility tool calls in
ways that left an open tool_use at the tail.  When the DH then
restores that snapshot and the LLM is invoked, the API may reject
the message list with a `tool_use ids were found without
tool_result blocks immediately after: …` 400 (Anthropic) or the
equivalent OpenAI 400.

**Mitigation.** Run a sanitisation pass over each snapshot at
freeze time: detect any trailing `AIMessage` with `tool_calls` and
either (a) call
`agents.shared.routing_tools.finalize_unanswered_tool_calls(snapshot,
ai_msg.tool_calls, len(snapshot))` to append placeholder
`ToolMessage` results IMMEDIATELY AFTER the dangling AIMessage —
the third argument is the START index inside `tool_calls` from
which to fabricate placeholder results, so passing
`len(ai_msg.tool_calls)` would skip them all; you want to pass `0`
**only** when you want to fabricate placeholders for every tool
call AND you want them inserted starting from the AIMessage's
position in the message list.  Re-read the helper's signature
before wiring it: the original draft of this TODO suggested
`finalize_unanswered_tool_calls(snapshot, ai_msg.tool_calls, 0)`,
which would prepend results to the message list rather than append
them after the dangling AIMessage — that is wrong.  Option (b),
simpler and safer for a v2: drop the trailing AIMessage entirely
when its tool_calls have no matching results.  Option (a)
preserves more context but requires the correct insertion index;
option (b) loses one turn of history but cannot leave the message
list malformed.

**Context for clarity.** This issue ships latent today because
every chain-agent run loop calls
`finalize_unanswered_tool_calls` defensively before exiting on a
routing-tool invocation, and step-limit termination is rare.  The
crash window is narrow (an unhandled exception inside the inner
tool-loop after a tool_call was emitted but before the ToolMessage
was appended).  Reproduce by raising mid-tool-execution in any
chain agent and then triggering the DH.

**Status.** v1 leaves snapshots unmodified.  Add the sanitisation
pass when the first crash is observed, OR proactively before
shipping the v2 that fills more than one field per agent (which
multiplies the exposure linearly).

### O2. Database Handler: rate-limiter coupling on `agent.base_llm`

**Where.** `agents/database_handler/database_handler.py:_run_one_conversation`,
specifically:

```python
base_llm = getattr(agent, "base_llm", None) or agent.llm
response = invoke_with_retry(base_llm, ...)
```

**What.** The DH invokes each interviewed agent's `base_llm`
(the bare provider client without tool bindings) so the agent
answers in plain prose without trying to invoke routing tools that
no longer make sense post-session.  The shared
`InMemoryRateLimiter` from `workflow_settings.RATE_LIMIT_*` is
attached to that `base_llm` at construction time inside
`agents/shared/llm_provider.py:build_llm`, so the rate limit IS
honoured today.

**Concern.** This is fragile.  If `build_llm` is ever refactored to
attach the limiter via `bind_tools(...)` (which would put it only
on the post-binding `agent.llm` instance), the DH would silently
bypass the limiter and could blow through Anthropic's 30k
input-tokens/min standard tier on a single save.  The DH issues
~16 calls per save (8 questions × 2: one for the DH to formulate
the question + one for the agent to answer it), and at cold start
each one carries a full system prompt, so the burst pattern
triggers the very rate-limit case the limiter was added to
prevent.

**Mitigation.** Future analysis: either (a) always attach the
limiter at constructor time and never as part of `bind_tools(...)`
(documented invariant), or (b) have the DH explicitly construct
its OWN bare LLM via `build_llm` per agent invocation rather than
reaching into `agent.base_llm` — this gives the DH explicit
control over rate-limiting and provider settings.

**Status.** Open.  Low priority while no refactor of `build_llm`
is planned.

### O3. Database Handler: context-window pressure on multi-agent interviews

**Where.** `agents/database_handler/database_handler.py:_formulate_question`,
which appends every prior Q/A summary to `self.messages`.

**What.** The DH is stateful across the entire interview phase —
every question it formulates and every answer it receives is
recorded in `self.messages`.  v1 asks one question per agent (8
total in the worst case with DCII enabled), so the buffer stays
small.  But the design supports filling many database fields per
agent in future versions.  At, say, 5 fields × 8 agents = 40
turns, plus the included answer text, the DH's own context window
will start to bite.

**Required behaviour.** If the DH is about to fill its context
window (define a threshold — e.g. 75% of the model's published
context length), erase the previous messages leaving ONLY the
conversation from the latest agent with which the DH talked to.
Reasoning: the DH does not need to remember every prior
interview to formulate the next question; the per-agent
conversation is the only thing relevant to the IMMEDIATE
clarification logic.  Earlier interviews are preserved on disk
under `database/<session_name>/<agent>/`, so the information is
not lost.

**Mitigation sketch.** Inside `_formulate_question`, before
invoking the LLM, estimate token count of `self.messages` (a
rough char-count proxy is fine; 4 chars ≈ 1 token).  When the
estimate crosses the threshold, walk backwards through
`self.messages` and find the boundary at which the most recent
"Agent: <agent_key>" entry started; truncate everything before
that boundary.

**Status.** Open.  v1 ships with no eviction; the architecture
supports the rephrased "remember everything" behaviour for now.
Implement before the v2 that fills > 2 fields per agent.

### O6. Database Handler: file-as-is database fields are skipped

**Where.** `agents/database_handler/database_handler.py:SCHEDULE`.

**What.** Four rows of the ``forClaude`` schema have ``Type =
File as-is`` (or just ``as-is``) rather than ``Semantic`` /
``Quantitative``:

| Field | Provider |
|---|---|
| User images | UII |
| Design Output file | Planner |
| Design Output renders | DCOI |

These fields are meant to capture the actual binary artefacts (PNG
images, OBJ meshes), not a textual description of them.  The DH as
shipped only writes plain-text Q/A files via
``_run_one_conversation`` + ``_write_entry``, so on the May-3 cut
these rows are deliberately omitted from ``SCHEDULE`` entirely (the
``# NOTE:`` comments in ``SCHEDULE`` flag where each was dropped).

**Required behaviour.** The DH should copy the actual files into
the per-session database folder, e.g.

```
database/<session>/dc_output_inspector/design_output_renders/render_isometric.png
database/<session>/dc_output_inspector/design_output_renders/render_top.png
database/<session>/dc_output_inspector/design_output_renders/render_side.png
database/<session>/planner/design_output_file/propeller_mesh.obj
database/<session>/user_input_inspector/user_images/<image>.{png,jpg,jpeg}
```

and write a small ``.txt`` next to (or alongside) each copy that
records the source path and any session-time provenance (which
attempt the renders came from, which was the APPROVED attempt for
``Design Output file``, etc.).

**Mitigation sketch.** Add a `"copy_files": True` (or similar)
flag to the affected ``SCHEDULE`` entries and a corresponding
``_write_file_entry`` branch in ``populate_database`` that locates
the canonical source on disk (e.g. for ``Design Output renders``,
the three PNGs in the most recent APPROVED attempt; for
``Design Output file``, that attempt's ``propeller_mesh.obj``; for
``User images``, the contents of ``inputs/input_images/``) and
copies them.  The same field's ``description`` from the schema can
go into a sidecar ``README.txt`` next to the copy so the layout
stays self-documenting.

**Status.** Open.  v1 explicitly skips these rows; the four
``# NOTE:`` markers in ``SCHEDULE`` document where each was
dropped.

### O7. Database Handler: 2D model files row is "Not yet implemented"

**Where.** `agents/database_handler/database_handler.py:SCHEDULE`.

**What.** The ``forClaude`` sheet has two duplicate rows labelled
``(Not yet implemented) User input 2D model files`` (Type = ``File
as-is``).  The system has no concept of 2D model file inputs today
(the ``inputs/`` directory only accepts the user query text, image
files, and image notes), so these rows are intentionally absent
from ``SCHEDULE`` for now.

**Required behaviour.** Once 2D model file inputs are wired into
``inputs/`` (in some yet-to-be-defined sub-folder convention),
add a single ``SCHEDULE`` entry for the field, with the same
``copy_files`` mechanism as O6.  The duplicate row in the sheet
should be reconciled with the schema author (likely a
copy-paste artefact in v5) before re-introducing here.

**Status.** Open, blocked on the 2D-input feature being designed
and shipped first.

### O8. Database Handler: DCII-disabled rows write empty placeholders

**Where.** `agents/database_handler/database_handler.py:populate_database`,
the ``if entry.get("requires_dcii_enabled") and not
dc_inspector_enabled:`` branch.

**What.** Per the May-3 spec, when the DC Input Inspector is
disabled this session (``DC_INSPECTOR_ENABLED = False``), every
DCII-bound row in ``SCHEDULE`` (today: ``Problem - DCII``,
``Validation of inputs - DCII``, ``Rejection of inputs - DCII``)
still produces a file at
``database/<session>/dc_input_inspector/<slug>.txt`` — but the file
is EMPTY.  This is a temporary fix so the per-session database
folder layout stays uniform regardless of the DCII toggle, without
the DH having to fabricate "the DCII did not run" answers.

**Why temporary.** An empty file is ambiguous: a future RAG
pipeline cannot tell whether the DCII was simply disabled, or
whether the DCII ran but produced no relevant content for that
field, or whether something failed.  The proper behaviour should
either:

- (a) write a tiny structured sentinel (e.g. ``DCII_DISABLED`` on
  its own line, or a YAML front-matter block) so consumers can
  programmatically distinguish the disabled case from a real
  empty answer, OR
- (b) drop the DCII rows entirely from ``SCHEDULE`` when DCII is
  disabled, and have the future RAG pipeline tolerate "missing
  field" the same way it tolerates "ERROR:" entries.

**Status.** Open, low priority while DCII is on by default.

### O5. Database Handler: end-of-session save-prompt UX

**Where.** `agents/loader.py:run` — the `_ask_yes_no("Save this
session to the database (for later RAG)?", default_yes=False)` call
inside the user-quit branch.

**What.** v1 ships a minimal yes/no prompt with `default_yes=False`.
There are several open questions about the intended UX:

- Default value: should it be `False` (current — opt-in saving) or
  `True` (opt-out)?
- Per-agent control: should the user be able to skip individual
  agents (e.g. "save UII + Planner only")?
- Pre-save preview: should the loader show what's about to be
  recorded (number of attempts, duration, agent step counts) before
  the user confirms?
- Follow-up flow: if the DH is asked to fill more fields per agent
  in the future, should the user be told how many LLM calls saving
  will incur?
- The KeyboardInterrupt and unhandled-exception paths currently
  default to "no save".  This is correct (the user is no longer at
  the keyboard to answer), but the behaviour should be documented
  in the user-facing help once written.

**Status.** Refine when the database-population flow stabilises.

---

## Operational checklist (pre-deploy)

Items here are not codebase bugs — they are external admin actions that must
be done before the cloud deploy goes live. Tracked here so they don't fall
off the radar between phases.

### OPS1. Set hard monthly spend caps on every LLM provider dashboard

**What.** Configure a hard monthly spend cap on each LLM provider used by the
v3 stack so that runaway usage (whether from a leaked invite code, a bug, or
a rogue session) cannot bill more than the cap before the API starts
returning 429s.

**Where to set them.**
- OpenAI → platform.openai.com → Settings → Billing → Limits → set a hard
  monthly budget that returns a 429 when exceeded.
- Anthropic → console.anthropic.com → Settings → Plans & Billing → Spend
  limits.
- Google → at the time `GOOGLE_API_KEY` is generated, set a budget on the
  linked GCP project.

**Why this is the floor.** v3 ships with invite-code-only auth (per
`cloud_architecture_notes.md` C3, with the slowapi rate limit dropped per
OQ1). If the invite code leaks, the spend cap is the only defence between
"free LLM trial for the internet" and the user's credit card.

**Recommended starting cap.** €50/month per provider for thesis-stage
usage. Adjust upward only when telemetry shows sustained legitimate burn
against the cap.

**Status.** Open. Must be done before Phase 7 (first Railway deploy);
should be done much earlier so that even local dev mistakes can't run away.
Independent of all code changes.

---

## Future work / planned enhancements

These are not bugs — they are design items deliberately deferred to keep
v2 scope tight. Cross-referenced from `database_design_notes.md` where
relevant.

### F1. `dc_parameter_schemas` auto-loader from Grasshopper-side declarations

**Where.** Today: manual `INSERT INTO dc_parameter_schemas` rows whenever
the propeller (or future DC) parameter inventory changes.

**What to build.** Keep
`DC_prompt_fragments/dc_config/parameter_keys.txt` and
`DC_prompt_fragments/dc_config/parameters.md` as the source of truth (or
add a parallel machine-readable `parameters.json`). Write a small Python
loader that diffs the file against the current contents of
`dc_parameter_schemas` and, if anything changed, INSERTs a new
`schema_version` row-set with the updated `(param_name, min, max, unit,
description)`. Old `schema_version` rows stay in place so historical
attempts remain queryable under their own normalisation.

**Why deferred.** Manual INSERTs are fine while there is one DC and
schema bumps are infrequent. The auto-loader becomes worthwhile when
either (a) parameter inventories change often, or (b) a second DC is
added and the surface area doubles.

**Status.** Open. Triggered by either condition above.

### F2. Per-parameter weights for masked-RMSE

**Where.** Today: masked L2 = √(masked SSD), all dims weighted equally.

**What to build.** Run a sensitivity analysis on the propeller DC's 17
parameters to determine which ones drive design outcome the most, then
expose per-parameter weights as an optional argument to
`query_database_quantitative`. Default remains all-equal weights;
callers can pass `weights={"numBlades": 2.0, "hubDiameter": 0.5, ...}`
when they want to bias the search.

**Why deferred.** No data on which parameters are dominant yet. Premature
weighting would inject bias rather than remove it.

**Status.** Open. Blocks on running the sensitivity analysis itself.

### F3. HNSW / IVFFlat upgrade for `chunks.embedding`

**Resolved by going HNSW from day one** in the v2 schema (see
`database_design_notes.md` D2). This item — historically tracked as
"add HNSW once corpus reaches ~30k vectors" — is **closed before
opening**. Do not re-add it.

---

## Resolved issues

### R3. Database Handler: `_pending_hop` and other per-instance state not snapshotted

**Resolved:** 2026-05-10. Originally tracked as Open issue O4
(`_freeze_histories` only deepcopied `agent.messages`, leaving
`_pending_hop` / `_pending_image_blocks` / `_pending_image_paths`
/ `cycle_start_ts` unsnapshotted; safe today only because the DH
called `agent.base_llm` directly and never invoked `agent.run()`,
so the run-loop branches that read those attributes never fired —
an implicit contract that any future DH change touching `run()`
would silently violate).

**Resolved by construction in v3 Phase 1 commit 6.** The DH no
longer freezes / restores anything onto live agent instances.
`_run_one_conversation` reads `session.agent_states[agent_key].
messages` (a copy) into a local `convo_buffer` list and runs the
DH-vs-agent conversation entirely in that buffer.  No live agent
attribute is ever read or mutated by the DH conversation loop, so
the unsnapshotted attributes simply do not enter the picture.

The `_freeze_histories` method is removed; the `agent.messages =
copy.deepcopy(snapshot)` mutation is removed; the W6 invariant
this issue depended on is also resolved (see warnings_developer.md
W6 — annotated as obsolete).

### R2. Parallel image-loading tool calls produce a malformed message history

**Resolved:** 2026-04-30. Originally tracked as Open issue #1
("Parallel image-loading tool calls produce a malformed message
history (OpenAI 400)") — first observed on OpenAI in session
`session_20260426_231337.log`, then re-surfaced on Anthropic on
2026-04-30 (DCOI crashed with `messages.2: tool_use ids were found
without tool_result blocks immediately after: toolu_01Vn9tCH...`)
because the OpenAI-only stop-gap could not be applied to Anthropic
(no equivalent `parallel_tool_calls` flag).

**Symptom (historical).** When an agent that has at least one
image-loading tool bound (concretely Planner, UII, DCIC, DCII, and
DCOI; DCOI also has `load_render_images`) lets its LLM emit two or
more tool_calls in a SINGLE `AIMessage` and at least one of them
loads images, the agent's `messages` list ended up shaped:

```
AIMessage(tool_calls=[A, B])
ToolMessage(A)
HumanMessage(image bytes for A)   <-- breaks contiguity
ToolMessage(B)                    <-- now "lost" — tool_use B has no tool_result
```

Both Anthropic and OpenAI reject this on the next `.invoke()`:

- OpenAI 400: `An assistant message with 'tool_calls' must be
  followed by tool messages responding to each 'tool_call_id'. The
  following tool_call_ids did not have response messages: …`
- Anthropic 400: `tool_use ids were found without tool_result
  blocks immediately after: …`

**Why the previous stop-gap was insufficient.** The original 2026-
04-26 stop-gap passed `parallel_tool_calls=False` to `bind_tools()`
on the 5 affected agents — but only on OpenAI, because the flag is
OpenAI-specific. As soon as Anthropic Opus reached the DCOI on
2026-04-30, the latent bug fired immediately (Opus batches tool
calls aggressively). Provider-aware suppression only papered over
the symptom on one provider; the message-shape bug was always
present.

**Fix shipped (proper fix from the original Open #1 spec).** New
buffer-and-flush mechanism in `agents/shared/file_utils.py`:

- `append_pending_images(agent, image_blocks, image_paths)` —
  image-loading tool handlers append to a per-agent buffer
  (`agent._pending_image_blocks` / `_pending_image_paths`) instead
  of appending a `HumanMessage` immediately after the `ToolMessage`.
- `flush_pending_image_blocks(agent)` — called by each affected
  agent's `_run_llm_loop` AFTER the inner `for tc in
  response.tool_calls:` loop has appended every `ToolMessage` for
  the current `AIMessage`. Flushes the buffered image blocks as a
  single trailing `HumanMessage` and clears the buffer.

The result is a uniform message shape regardless of how many
parallel tool calls were batched:

```
AIMessage(tool_calls=[A, B, C])
ToolMessage(A)
ToolMessage(B)
ToolMessage(C)
HumanMessage(image bytes for any of A/B/C that loaded images)
```

Both Anthropic and OpenAI accept this shape.

**Files touched.**

Image-loading handlers refactored to buffer instead of
immediate-append:
- `agents/shared/user_inputs_tool.py:_handle_load_input_images`
- `agents/dc_output_inspector/dc_output_inspector.py:_handle_load_tool`
- `agents/user_input_inspector/user_input_inspector.py:_handle_read_inputs_tool`

Flush call wired into the `_run_llm_loop` of each affected agent,
right after the inner `for tc in response.tool_calls:` loop:
- `agents/planner/planner.py`
- `agents/user_input_inspector/user_input_inspector.py`
- `agents/dc_input_creator/dc_input_creator.py`
- `agents/dc_input_inspector/dc_input_inspector.py`
- `agents/dc_output_inspector/dc_output_inspector.py`

**Stop-gap removed.** Every `parallel_tool_calls=False` site is
gone; `bind_tools(all_tools)` is now called bare in each of the 5
agents. The five `TEMPORARY (see extra_utilities/TODO_known_
issues.md, item #1)` comment markers are deleted.

**Verified by 4 unit-style smoke tests.** See
`extra_utilities/smoke_test_image_buffer.py`:

1. Dual parallel tool call (`load_input_images` + `read_input_text`)
   → final shape `[AIMessage, ToolMessage, ToolMessage, HumanMessage]`,
   paired path-text + image block intact.
2. Empty-flush is a no-op.
3. Three parallel tool calls (two image-loading + one utility) →
   final HumanMessage carries 6 content blocks (3 images × 2 = path
   text + image alternating).
4. The exact failure mode from 2026-04-30 (`load_render_images` +
   `load_input_images` in one AIMessage) → both paths in path-text
   labels, two image blocks, contiguity preserved.

A second smoke test (`extra_utilities/smoke_test_no_parallel_kwarg.py`)
asserts that NO agent still passes `parallel_tool_calls=` to
`bind_tools(...)`.

---

### R1. No retry / back-off on `RateLimitError` or transient connection errors

**Resolved:** 2026-04-30. Carried forward from the v4 handoff doc as
known issue #6 ("No retry/back-off on `openai.RateLimitError`") and
the related run-2 / run-3 / run-4 connection-error / 429 session
deaths in v5.

**Symptom (historical).** A single 429 from Anthropic's
`claude-opus-4-x` 30k input-tokens/min standard tier, or a single
transient `RemoteProtocolError` / `APIConnectionError`, killed the
entire dispatch loop. Sessions terminated with the `[SESSION END]
unhandled exception:` marker mid-pipeline, even after substantial
prior work — the `agents/loader.py` archive logic ran cleanly so
artifacts and histories were preserved, but the user-facing failure
message they should have received was never produced.

Reproducible historically by running on the Anthropic standard tier
(30,000 input tokens / minute) — by the time the 4th cold-start
agent invoke fired, cache writes had already exhausted the rolling
per-minute budget, the call 429'd, and the dispatcher propagated
the exception up through `Orchestrator.dispatch()` and out of
`agents/loader.py:run()`'s outer try.

**Fix shipped.** New helper `agents/shared/llm_retry.py` exposing
`invoke_with_retry(llm, messages, agent_name)`:

- Catches `RateLimitError` (anthropic + openai by class-name match).
  On 429, sleeps for the response's `Retry-After` header if the
  server sent one, otherwise sleeps a default 60s (one full
  per-minute window so cache writes age out before retry). Up to 5
  attempts.
- Catches `APIConnectionError` / `APITimeoutError` /
  `RemoteProtocolError`. Exponential back-off with 25% jitter (2s,
  4s, 8s, 16s, capped at 30s). Up to 5 attempts.
- Logs every retry decision with the calling agent's name, e.g.
  `[Planner] 429 rate limit on attempt 2/5; sleeping 60.0s before
  retry` — so post-hoc log inspection can attribute every retry to
  the agent that triggered it.
- Re-raises non-retryable exceptions immediately (no silent
  swallowing).
- Re-raises after exhausting retries on a retryable exception, with
  a `[<agent>] retries exhausted` warning written first.

Class-name matching (rather than `isinstance`) is deliberate — the
helper is loaded by every agent regardless of which provider is
configured, and shouldn't fail if only one of the provider SDKs is
installed.

**Wired into all 8 agents.** Each agent's `_run_llm_loop` now calls
`invoke_with_retry(self.llm, [...], "<AgentName>")` instead of
`self.llm.invoke([...])` directly. Agent labels: `Receptionist`,
`Orchestrator`, `Planner`, `UII`, `DCIC`, `DCII`, `DCOI`,
`Tool Caller`.

**Companion mitigations shipped in the same window** (defence in
depth against the 30k/min Anthropic tier):

- **Prompt caching for Anthropic.** New `make_system_message(prompt,
  provider)` helper in `agents/shared/llm_provider.py` wraps each
  agent's static system prompt in a `cache_control: ephemeral`
  block on Anthropic. Plain-string `SystemMessage` on OpenAI /
  Google. Cuts steady-state per-call input cost ~10× on cache hits.
- **Optional shared rate limiter.** New
  `RATE_LIMIT_ENABLED` / `RATE_LIMIT_REQUESTS_PER_SECOND` constants
  in `workflow_settings/settings.py` build a single
  `langchain_core.rate_limiters.InMemoryRateLimiter` shared across
  all 8 agents and pass it to every provider constructor. Off by
  default; flip on for tight per-minute budgets.

The three together form the full Anthropic-rate-limit defence:
limiter **prevents** by smoothing call rate; cache markers
**reduce** per-call cost; retry/back-off **recovers** when a 429
slips through anyway.

**Verified by 6 unit-style smoke tests** in the helper's smoke run
(success path, single 429 with `Retry-After`, single 429 without
header, persistent 429 exhausting retries, two-shot connection
error with exponential back-off, non-retryable `ValueError`
propagating immediately).
