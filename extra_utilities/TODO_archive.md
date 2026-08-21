# Known issues — ARCHIVE (closed entries)

Entries from `TODO_known_issues.md` that are FIXED, DONE, RESOLVED, BUILT or
otherwise settled.  Split out 2026-08-21; **the text is verbatim**, only the
file it lives in changed.

**Ids are never reused.**  The F / O / R counter is a single manually-reserved
space shared across git branches, and ~19 F/O ids are cited from live source.
An id appearing here is retired, not free.  New items start at **F94**.

**Why entries are here and not deleted.**  Several record a decision plus its
reasoning (why a thing was kept, why a fix was narrowed, why something was
"closed before opening").  That reasoning is the part worth keeping.

Anything still open lives in `TODO_known_issues.md`.  Where an entry was
partially closed it stayed THERE, not here.

---

### F3. HNSW / IVFFlat upgrade for `chunks.embedding`

**Resolved by going HNSW from day one** in the v2 schema (see
`database_design_notes.md` D2). This item — historically tracked as
"add HNSW once corpus reaches ~30k vectors" — is **closed before
opening**. Do not re-add it.

---

### F7. Implement the Context Pruner agent

**Where.** New agent (slot reserved in the LOG and Status
flowchart's `EXTRA AGENTS` box alongside the Database Handler).
Will hook into the dispatch / orchestrator path.

**What.** The Context Pruner is one of the two "extra agents"
displayed in the LOG and Status flowchart as a placeholder.
It does not exist in code today (no `agents/context_pruner/`
directory) — only the conceptual slot.

**Why it matters.** Carry-over open item from v7 (project memory
`project_v8_scope.md` → Open issues #1): the DCOI accumulates
messages + vision tokens across attempts, and a 3-attempt design
request with an attached image has hit 894k tokens vs the model's
272k cap (`OpenAIContextOverflowError` raised in
`agents/dc_output_inspector/dc_output_inspector.py:306`). The
current workaround is the `KEEP_IMAGES_IN_CONTEXT=False`
workflow setting, which is coarse — it drops ALL images
regardless of whether they were still relevant.

**What to build.** An agent that watches each agent's message
list as the session progresses and decides what to prune /
summarise / drop before context becomes a problem. Likely
candidates: collapse old image blocks into textual summaries,
fold prior tool-call outputs into the agent's running plan,
drop superseded attempts' DCOI history once a new attempt has
landed. Triggered by token-count thresholds (per-agent),
similar to O3's sketch for the DH's own context pruning.

**Why deferred.** A real design needs more data on which kinds
of context actually waste tokens in real sessions. The cheap
workaround (`KEEP_IMAGES_IN_CONTEXT=False`) covers the only
overflow seen so far. Implement once a non-image-driven
overflow shows up, or when the multi-attempt flow becomes the
common case rather than the exception.

**Status.** **Implemented (v9).**  The Context Pruner is now wired
into every chain agent's pre-invoke hook via
``BaseChainAgent.prune_history_if_needed`` (see the dedicated
"Context Pruner" section in ``README.md``).  Gated by the new
``CONTEXT_PRUNER_ENABLED`` / ``CONTEXT_PRUNER_THRESHOLD_TOKENS`` /
``CONTEXT_PRUNER_KEEP_LAST_MESSAGES`` settings.  The CP box in the
LOG-and-Status chart lights up alongside whichever agent's history
is being pruned (multi-active, same pattern as the DC tools).  The
Database Handler is intentionally NOT pruned — it iterates ~28
schedule entries in one save and relies on accumulated state.

---

### F24. Live 3D preview in the Parameters Inputs view (P3-C)

**Where.**  `web/index.html` Parameters Inputs section (`data-view="params"`) and `web/app.js` PARAM_GROUPS / paramsInit().  Both currently ship the sliders + Use-these-parameters submit but no live preview.  The standalone reference at `C:\Users\vince\MT Coding\web_interface_tests\propeller_V3` shows the target behaviour: the right-hand viewport regenerates a propeller mesh on every slider change (debounced).

**What to build.**  Three coordinated pieces:

1. **Backend preview endpoint** — new `/api/preview_mesh` route in `web_app.py` that takes a JSON body of the 17 parameter values, calls the existing mesh tool (`tools/generate_mesh/generate_mesh.py`) directly (bypassing the agent pipeline), and returns the mesh bytes (`.obj` is fine; `.3dm` if we want to match the reference exactly).  This is the same RhinoCompute round-trip the agent path already does, just exposed without the chain in front of it.  Authentication: same `_require_auth()` gate as `/api/turn`; no session lock required since this is a preview, not a session action.

2. **Frontend slider listener** — add a debounced (~300–500 ms) `input` handler to every slider in PARAM_GROUPS that POSTs the current `paramState` to `/api/preview_mesh` and loads the returned mesh into a Three.js viewport.  Reuse `web/viewer.js` if possible, or instantiate a second viewer scoped to a new `<div>` in the Parameters view (the existing chat-view viewer needs to keep showing the agent-generated propellers, so sharing one DOM node is fragile).

3. **`.gh` file alignment decision** — the reference uses `propeller_V3.3.gh`; the v9 mesh tool uses `Propeller_Raul_V1.2.gh` (`config.GH_DEFINITION_PATH`).  Decide whether (a) the preview uses Raul V1.2 like the rest of v9 (visual continuity between preview and final mesh, but the preview won't look identical to the standalone reference), or (b) we add a second registered `.gh` definition for preview-only and switch on `definition` arg in the request body.  Option (a) is simpler and means "what you preview is what the agents generate" — recommended unless there's a reason to keep the propeller_V3.3.gh visuals.

**Why deferred.**  The Parameters Inputs view ships as sliders + submit in the current commit so the user can pick values and route them through the agent pipeline today.  The live preview is a separable, larger piece of work that needs (a) the backend bridge, (b) the viewport infrastructure, and (c) the .gh decision.  Not blocking the submit path; can land in its own commit when there is time.

**Status.**  **RESOLVED** 2026-06-XX (commits ``14bdfa1`` factor ``render_mesh_obj_text`` helper, ``dfc66e5`` ``/api/preview_mesh`` route, ``03ad83b`` debounced slider → preview pipeline + Download geometry handler).  ``.gh`` decision: went with option (a) — preview uses ``Propeller_Raul_V1.2.gh`` so what the user previews is what the agent pipeline produces.

---

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

---

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

---

### F33. Reduce DH LLM cost by batching multiple questions per agent into one call

**Where.**  `agents/database_handler/database_handler.py` — the
DH's interview loop that walks `dh_schedule.json` entries one
at a time and issues one `llm.invoke(messages)` per schedule
entry against the target chain agent.

**What.**  The DH currently asks each schedule question as a
SEPARATE LLM call to the target agent.  The DH iterates ~28
schedule entries per save (per the architecture doc), which
means ~28 LLM calls per session save.  Many of those entries
ask the SAME agent multiple distinct questions about different
facets of its session work (e.g. the UII gets asked about its
extraction, its image-handling, its database use, its hand-off
prose).  Each call re-sends the agent's full context (system
prompt + history) and pays the per-call overhead.

A natural optimisation is to GROUP schedule entries by target
agent and send all questions for that agent in a single LLM
call — the agent answers each question in a structured response
(one labelled section per question); the DH parses the response
back into per-question chunks and runs the same `insert_chunk`
flow per chunk as today.

Estimated saving: if the average grouping factor is ~3 (28
entries / 9 agents ≈ 3 questions per agent on average), the DH
save's LLM cost drops by roughly 60-65 %.  Savings come from
(a) fewer system-prompt resends, (b) fewer round-trip
latencies, (c) better prompt-cache utilisation since the
agent's context is loaded once per batched call.

**Why deferred.**  Several real risks need handling:

  1. **Output-token quality.**  A single response with many
     answers may produce shorter or less thoughtful per-
     question content than separate calls.  Needs empirical
     calibration per agent.
  2. **Schedule-order semantics.**  Some entries depend on
     prior answers from the same agent (rare but exists).  The
     batched prompt must preserve that ordering OR identify
     the sequential entries and keep them separate.
  3. **Parsing brittleness.**  Structured-response parsing
     needs either strict JSON / XML output with format
     validation, or per-question stop-marker delimiters with
     a graceful fallback.
  4. **Per-agent context size.**  Some agents accumulate a lot
     of history (Tool Caller, DCOI with images) and a batched
     call could exceed the agent's effective working budget.
     The DH already integrates with the Context Pruner (W7);
     would need to verify batching doesn't push pruning
     thresholds.

**Proper fix.**  Three components:

  1. Group `dh_schedule.json` entries by target agent at DH
     startup; preserve original order WITHIN each group and
     identify any explicit ordering constraints across groups.
  2. Build a single batched prompt per group: agent-specific
     framing + N numbered questions + a strict structured-
     response template (JSON or XML with one entry per
     question, plus a field for any "I can't answer" notes
     so a single bad question doesn't poison the whole batch).
  3. Parse the batched response back into per-question chunks;
     run `insert_chunk` on each chunk individually (same
     downstream path as today, so retry / safety folder /
     embedding flow are unchanged).

**Status.**  **DONE 2026-08-04.**  Built in three steps.  The shape
differs from the sketch above in one important way: the grouping is NOT
computed from the schedule by code, it is DECIDED BY THE DH in one
planning call per save (`submit_batch_plan`), because "would these two
questions be answered well together?" is a judgement — the owner's
example being that a best-case and a worst-case question must never
share a reply.  Code only fixes the boundaries a group may not cross
(same `agent_key`, `scope` and `parent_id`; identifying rows always
alone).

The four listed risks were handled as follows:

1. *Output-token quality* — per-entry token cap unchanged and still
   enforced, now re-emitted BY LABEL rather than by position.
2. *Schedule-order semantics* — groups may only form inside a candidate
   run, and sub-rows still run per resolved attempt in schedule order.
3. *Parsing brittleness* — solved by construction: the whole text
   protocol is gone.  Every decision is a forced tool call with a
   schema, and coverage (every row in exactly one of
   `saves`/`followups`/`skips`) is validated before anything is
   written, with one retry then a per-row fallback.
4. *Per-agent context size* — a batch sends ONE copy of the agent's
   frozen history for N rows instead of N copies, so batching REDUCES
   this pressure rather than adding to it.

Measured on the shipped 36-row schedule: 36 rows → 15 batches, 42 fewer
LLM calls per pass, before the per-attempt multiplier on sub-rows.  The
real per-save cost is still unmeasured — that needs one live save.

Documented in the README ("Database Handler: the batched interview").
Covered by `extra_utilities/smoke_test_dh_batching.py` (80 checks).

---

### F39. database_search read-routing to chunks_mm (multimodal) — SCOPED, build in progress

> **F36/F37/F38 are taken.**  F36 = embedding-tests mini-eval
> (`silly-black` branch); F37 = VLM-enriched user-image embeddings;
> F38 = OCR region re-read (above).  This entry is therefore **F39**.

**Where.**  `tools/database_search/database_search.py` (the
`make_database_search_tool` factory + the search impl) +
`DC_prompt_fragments/tools_config/database_search*.md`.  Reuses
`agents/shared/voyage_mm.py` + `workflow_settings/db_options_config.py`
(no new deps; no schema change — `chunks_mm` already exists + is
populated).

**What.**  Route `database_search` to query the multimodal `chunks_mm`
table (Voyage voyage-multimodal-3.5, 2048-dim, halfvec HNSW) instead of
`chunks` when the Database-options mode is `single-vector-multimodal`.
Mode is FROZEN at session build (read in the tool factory).  Image rows
rank like any chunk and surface as `<image_ref>` REFERENCES (the agent
fetches bytes via `retrieve_*`); user images appear in session-level
searches only.  Graceful + LOGGED fallback to the text-only `chunks`
path if Voyage is unavailable (`logger.error` + `<search_meta>` note +
`rag_queries.error_message`).  `rag_queries` logging is otherwise
unchanged (`embedding_model` records the Voyage model).

**Full design + build steps:** architecture doc §4.11 (locked design)
+ §9.15 (the 7 build steps).  This entry is the durable SCOPE marker —
mark DONE / remove when the read-routing ships.

**Status.**  BUILT + verified 2026-06-16 — `_resolve_search_backend`
routing + mode-aware embed-with-fallback + `<image_ref>` emission +
generic `<search_meta>` `mode`/`db`/`fallback` attrs, all in
`database_search.py`; the single extension point for future backends is
documented in **W39**.  Smoke test
`smoke_test_database_search_mm.py` (11/11).  NOT yet committed/deployed
— mark this entry DONE once it ships.

---

### F40. Planner: use the blade-sections creator tool when sections must be observed

**Status.** ADDRESSED (prompt-first, 2026-06-18) — the Planner blade-sections
overlay (`DC_prompt_fragments/tools_config/blade_sections_visualizer_planner.md`)
tells it to prefer a sections-first plan when sections must be observed.  Part
of the BSV fast-path fragments alongside `render_blade_sections`
(`tools/render_blade_sections/`).

> Let the Planner know that, if there are sections to be observed as well, to use the blade sections creator tool

---

### F41. Planner: "maximum precision possible" means multiple refinement attempts

**Status.** ADDRESSED (2026-07-15) by the precision sections-matching feature
(**F51**) — a "match precisely / many attempts" demand now becomes a FORCED refine
loop: the Planner issues a standing directive, the DCOI won't approve the first render
or on proportions alone, and the loop iterates (sections, then — if a whole-propeller
sketch exists — the 3D) until a close match or a code-capped plateau, reporting the
residual honestly. Generalises beyond the 2026-06-18 sections-only overlay. Pending a
prod end-to-end run (see F51).

Earlier (2026-06-18): PARTIALLY ADDRESSED — the Planner blade-sections overlay covered
the sections-context case (max precision ⇒ several cheap section-refinement passes).

> Let the planner know that it is very important that if the user specifies they want maximum precision possible, it means performing multiple attempts trying to refine the geometry as much as possible (within a reasonable error)

---

### F43. Treat the Blade-sections renderer as a full new capability (sections-first fast path)

**Status.** ADDRESSED (prompt-first, BSV fragments, 2026-06-18) — the
sections-first fast path is now in the Planner / Tool-Caller / DCOI / UII
blade-sections overlays + the shared brief; the system can render + check
sections first and may stop at the sections (chat image as the deliverable; no
downstream code change this pass).  Deeper workflow / logic optimization
remains a later step.

> Let the system understand that, if the Blade section rendering tool is ON, that is a FULL NEW CAPABILITY that the system can use. If the user provides drawings of blade sections, or specific details about the blade sections, the system can first run the blade section renderer, check this, and then decide whether to generate a 3D geometry or not, because generating the blade sections only is much faster. This is just a suggestion, but still it can be done depending on the circumstance. This is to be optimized in the funcitoning, logic, and prompt wording for the soon future (very soon)

---

### F47. Attempt-creation ownership: DCIC is the sole default creator

**Status.** FIXED (2026-07-13, commit `cf4b900` → stage-a) — pending a prod
(py3.13) validation run.

**Bug (from `LOG_problem_2.txt`).** Both the Planner and the DCIC held
`new_attempt`, so on one generation the Planner opened attempt 1 and the DCIC
opened attempt 2 and wrote params there — attempt 1 was orphaned
(`description.txt` only, no `parameters.json`).

**Fix.** Removed `new_attempt` from the Planner entirely — its tool binding
(`agents/planner/planner.py`) AND every system-prompt/doc reference
(planner/prompt.md incl. the hot-path Role-1 FORWARD move; orchestrator/prompt.md
incl. the "MUST carry Current attempt" rule; dc_input_creator prompt +
`write_parameters` docstring; routing_orchestrator.md; agent_tools_overview{,_brief}.md;
output_file_locations.md; attempts_tool.py docstring; step_caps.py).  The DCIC is
now the sole default creator (opens exactly ONE attempt per generation and ALWAYS
writes `parameters.json` into it); the Planner DIRECTS it via a slug + intent.  The
Orchestrator KEEPS `new_attempt` but ONLY as a special-case fallback for when the
DCIC cannot create the folder.  Prompt-driven (no hard code guardrail) — the prod
validation should confirm a fresh design yields ONE populated attempt, no empty
folder.  Adversarial review caught 12 stale-prompt leftovers (all fixed).

---

### F48. render_and_check_mesh reuses existing renders (no new attempt to re-render)

**Status.** FIXED (2026-07-13, commit `cf4b900` → stage-a) — pending a prod
validation run.  Completes the render-reuse half of F45.

**Bug (from `LOG_problem_2.txt`).** `render_and_check_mesh` was append-only on
renders: if the three `render_*.png` existed it ERRORED ("Attempt folders are
append-only … Create a NEW attempt").  So a QC re-run on an already-rendered
attempt spawned a whole new attempt with the SAME params + a full mesh
REGENERATION + re-render (byte-identical output) — pure waste.

**Fix.** Both backends (`tools/render_mesh/render_mesh.py` +
`render_mesh_pyvista.py`): `_validate_output_dir` no longer errors on existing
renders; the render step REUSES all three PNGs in place when they exist (still
runs QC on the mesh), else renders.  Scoped to **renders/QC only** —
`parameters.json` + the mesh stay append-only (`generate_propeller_mesh` still
refuses to overwrite a mesh).  All "append-only renders" prompt text reconciled.
This does NOT relax the append-only `parameters.json`, so a parameter TWEAK still
opens a new attempt — that remaining piece is F45's deferred scope.

**Update (2026-07-14, `d5de05c`).** `render_and_check_mesh` no longer exists as a
standalone tool — it was merged into `generate_and_render_propeller` (F50).  The
render-reuse behaviour described here now lives in that tool's built-in render step
(a plain `render_and_check` / `render_and_check_pv` core, wired via
`set_render_and_check_fn`), which reuses the three PNGs in place exactly as before.

---

### F49. LOG/Status flowchart: "last used tool" caption bound to the wrong agent box (+ label renames + Blade Sections box)

**Status.** FIXED (2026-07-14, commit `d5de05c` → stage-a) — pending a live (py3.13)
look at the running flowchart; NOT visually verified in-sandbox (the py3.8 worktree
can't import the app and the screenshot subsystem is broken, so the wiring was checked
structurally + the pure-Python attribution path was runtime-tested).

**Bug.** The gray "last used tool" caption under each agent box (published by the
`@generic_tool` decorator) was attached to whichever box currently had `.active` in
the DOM, with NO tool→owner check.  When a box-switch (`agent_active`) event was
dropped by the lossy viz bus (`viz_bus._MAX_QUEUED=32`, silent drop-on-full), the
caption landed on the previously-lit box — e.g. the DCIC's "Write parameters" showed
under the **Planner** (the reported symptom).

**Fix.** The event now carries its owner.  `agents/shared/trace.py` keeps an
in-process `_current_agent` (updated inside `trace()` ONLY when `to_agent` is a real
agent — the 8 `AGENT_DISPLAY.values()` + "Database Handler"; reset in `init_trace()`;
read via `get_current_agent()`).  `@generic_tool` (`agent_activity.py`) stamps
`{"agent": get_current_agent()}` onto its event.  The frontend
`recordToolUsedByActiveAgent(name, agentName)` (`web/app.js`) targets
`FLOW_BOX_BY_NAME[agentName]` (falls back to the old `.active` query only if the field
is absent).  `viz_bus._MAX_QUEUED` 32→256 + **drop-oldest** on overflow so box-switch
bursts rarely lose an event and, when they do, the freshest state wins (still
non-blocking).

**Also in this pass.** (a) Renamed 4 captions for accuracy/consistency: "Write
extraction"→"Write extracted inputs", "Generate new design attempt"→"Open new
attempt", "OCR regions"→"Read text regions (OCR)", "Database Search"→"Database
search".  (b) `render_blade_sections` now gets its OWN light-green "Blade Sections"
flow box (`@generic_tool("Render blade sections")`→`@tool_active("Blade Sections")`;
wired in `web/index.html` + `style.css` + `app.js` `FLOW_BOX_BY_NAME`/`TOOL_NAMES`/
`DYNAMIC_ARROW_BY_EDGE` + the LLM-routing chart) instead of a transient caption —
delivers the box side of F43.  Adversarial review (4 dimensions × verify) → 0
confirmed defects.

---

### F50. Merge generate_propeller_mesh + render_and_check_mesh into one tool

**Status.** FIXED (2026-07-14, commit `d5de05c` → stage-a) — pending a prod (py3.13)
run to exercise the merged tool's render step (needs the real trimesh/pyrender stack,
unavailable in the py3.8 worktree).

**Context.** The Tool Caller called two design tools in sequence —
`generate_propeller_mesh` (geometry) then `render_and_check_mesh` (3D renders + QC) —
hand-copying the mesh path from the first into the second.  Rendering is always the
logical next step after a good geometry build, so the split added a round-trip and a
chance for the LLM to skip or mis-path the second call.

**Fix.** ONE tool `generate_and_render_propeller`
(`tools/generate_mesh/generate_mesh.py`, `@tool @tool_active("Propeller Configurator")`):
builds the geometry (selected backend + bidirectional fallback) then, as its built-in
final step, renders the three views + runs QC — no path round-trip.  It **reuses an
existing `propeller_mesh.obj` in place** (append-only preserved — never overwritten;
relaxed `_validate_output_dir` from refuse-if-exists to reuse) so a re-run is
idempotent and a render retry needs no new attempt (folds in F48's reuse).  It **skips
the render step only if the geometry generation fails** (both backends).  The two
render tools were de-decorated into plain cores `render_and_check` /
`render_and_check_pv`; `tools/__init__` injects the active one via
`set_render_and_check_fn()` (`get_render_tool`→`get_render_core`), so the merge adds NO
import of trimesh/pyrender/pyvista to the pure `render_mesh_obj_text` live-preview
path.  `get_tools()`→`[generate_and_render_propeller, calculate]`.  The "Visual
Renderings Generator" flow box is removed (one combined "Propeller Configurator" box —
see F49).  Prompts/fragments rewritten two-step→one tool ("calls exactly three
design-tool actions"→"exactly two"); Tool-Caller freshness signalling now reads the
return's "Mesh saved"/"Reused existing mesh" + "Renders saved:"/"Renders already
present" markers.  Adversarial review (4 dimensions × verify) → 0 confirmed defects.

**Caveat.** The external `propeller-dc` MCP server still exposes
`generate_propeller_mesh` / `render_and_check_mesh` by those names — a different layer,
untouched by this rename.

---

### F51. Precision sections-matching — iterate to match a user's precise blade-section drawings

**Status.** BUILT — all 5 phases (2026-07-15) → stage-a (commits `6cdfa3c` P1,
`97b6d21` P2, `f0b8763` P3, `cce0276` P4, `6a37974` P5; plus `9ed7c2a` for the
`middlePos` correction). Pending a prod (py3.13) END-TO-END run with a real precision
sketch — the py3.8 worktree can't import the app, so verification so far is
`py_compile` + pure-Python unit tests + structural / fragment-marker checks + per-phase
adversarial reviews only.

**Context.** Per `LOG_systemNotCheckingCrossSections.txt`: on a run where the user
mandated "recreate as precisely as possible / as many attempts as needed", the
sections-first loop ran ONCE — the DCOI approved the first blade-sections render on
ordering + proportions (explicitly declining shape) and went straight to 3D. Root
causes: DCOI bar too low (A), section-shape params never extracted from the drawing (B),
"many attempts" recorded as permission not mandate (D); compounded by a small /
compressed comparison render (C) and the NACA airfoil ceiling (E). Full design:
`extra_utilities/docs/archive/design_precision_sections_match.md` (31 decisions; 3 components).

**Fix (3 components, 5 phases).**
  * **C — standing directives (P1).** A verbose Planner-issued instruction survives the
    whole agent chain in a `=== STANDING DIRECTIVES ===` block, re-stamped by the
    dispatcher on loss, cleared per turn. NOT a flag.
    (`agents/shared/standing_directives.py` + `orchestrator.dispatch`.)
  * **B — unified `view_images` tool (P2).** One tool with coarse crop + side-by-side
    stitch replaces `load_input_images` / `load_render_images` across the 4 image agents;
    the composite saves to `attempts/_comparisons/` and auto-shows in chat.
    (`agents/shared/image_stitch.py` + `agents/shared/user_inputs_tool.py`.)
  * **A — the precision loop (P3–P5).**
    - P3: the UII writes a rough `SUGGESTED SECTION SHAPES` warm-start estimate + a coarse
      `SKETCH CROP REGION`; the DCIC seeds shape params from it; `draw.py` scaled ×18/11 so
      the comparison render stays legible when stitched.
    - P4: the Planner decides a precision job + issues the directive; the DCOI stitches
      render + sketch-crop, judges SHAPE fidelity, won't approve the first render /
      proportions-only, describes the visual gap in prose; the Orchestrator relays it
      STRAIGHT to the DCIC (no re-plan); the DCIC does shape-param-only moves; a code
      backstop in `dispatch` caps the loop at `MAX_SECTIONS_REFINE_ROUNDS = 8`
      (`agents/step_caps.py`) and forces an honest finalize.
    - P5: after sections converge, the Planner issues a FRESH 3D directive & the DCOI
      precision-checks the 3D top/side renders vs the sketch view (iterate an unlocked
      lever else report); per-phase ~8 budget via a counter reset; the Receptionist
      relays the achieved fidelity + ceiling residual honestly (wired producer-side
      through the Planner APPROVE move).

**Review.** Every phase went through find→verify adversarial review before commit; 6
confirmed defects fixed total (P3 protractor title overflow, P4 COMPARISON MODE 2
contradiction, P5 misattributed cap note + A7 producer-side wiring gap).

**Relation to F41 / F45.** CLOSES F41 (see its updated status). It deliberately does NOT
do F45's "refine in place" — each refine round opens a NEW attempt (`parameters.json`
stays append-only), consistent with F45's 2026-06-18 decision to keep per-attempt
history; the accumulating attempts also give the DCOI a prior render to measure progress
against for plateau detection.

---

### F82. The DC Output Inspector is told to name parameters it is never shown

**Status.** FIXED 2026-08-20 — the DCOI now holds the parameter NAMES in all
three trees, delivered as a per-agent scoped copy.  The ranges-or-not question
this entry left open is CLOSED against ranges; see "Decided: names, not ranges"
below.  Found while scoping which agents need `$hard_constraints_dc`.  Was
present in the 7-agent standard AND reduced trees and in the 5-agent tree.  Not
in the shrink proposal; it surfaced from the fragment-audience map, not from a
cut.

**The gap.** Every agent that handles parameters splices `$parameter_list` — the
canonical 16 names with their ranges — **except the DC Output Inspector**:

| agent | `$parameter_list` |
|---|---|
| Receptionist, Orchestrator, Planner, UII, DCIC, DCII, Tool Caller | yes |
| **DC Output Inspector** | **no** (7-agent AND 5-agent: `grep -c parameter_list` = 0 in both) |

Yet the DCOI is instructed twice to name them:

* `agents/dc_output_inspector/prompt.md:34` — "diagnose WHY a failure occurred and
  name which parameters likely need changing"
* `agents/dc_output_inspector/prompt.md:307` — "name which of the
  `$parameter_count` parameters *seem* to need adjustment and in which direction
  (`"<param X> looks too small / large"`)"

(Both line numbers are POST-fix.  The first was written as `:35` here and was
already off by one; the second was `:301` before the six-line reference block
went in above it.)

It splices `$parameter_count` (the number, "16") but never the names.  The only
literal parameter name anywhere in its prompt is `middlePos`, in an unrelated
passage.  So the agent whose entire output is "name the parameter that looks
wrong" has been given the count and one example.

**Why it matters.** The DCOI's verdict feeds the refine loop: the Orchestrator
relays its diagnosis to the Planner, which turns it into a parameter directive.
A hallucinated name (`filletRadius`, `bladePitch`) propagates one hop before
anything can reject it, and the DCOI is exactly the agent with the least
information to avoid inventing one.  This is also why `$hard_constraints_dc`'s
"reject invented parameters" clause should NOT be scoped away from the DCOI
before this is fixed — today it is one of the few signals it has that made-up
names are forbidden.

**Partial mitigations that exist today** (none of them designed for this):

* It binds `list_attempts` + `read_attempt`, so it CAN read `parameters.json`
  and see the real keys — but nothing in its prompt tells it to do so for this
  purpose, and it costs a tool round-trip.
* Incoming hand-offs usually quote parameter names in prose.

Both are incidental.  Neither is a substitute for the agent holding the list.

**The fix — DECIDED by the owner 2026-08-05: the DCOI is to be given the list of
parameters.**  Shipped 2026-08-20 as the names-only variant this entry held in
reserve, in all three trees.

**Decided: names, not ranges** (2026-08-20, on evidence from an adversarial
review).  This entry left ranges-or-not open.  Three findings closed it:

* The 5-agent DCOI's STATED ground for deferring to the value-owner is that the
  OTHER agent holds the ranges — `agents/5agent/dc_output_inspector/`
  `prompt_5agents.md:313-316`, "the Creator owns the final numbers and may
  choose differently using its range and consistency knowledge".  Handing it a
  bounds table falsifies its own reason to defer: it would close one
  contradiction by opening another.  (Both 7-agent trees phrase that sentence
  without the range clause, so this bites the 5-agent tree hardest.)
* Bounds are unusable without CURRENT values, and for `bladeCount`,
  `impellerRadius` and `impellerThickness` no tool result the DCOI receives
  ever states one.  "Read the ranges for headroom" would invite exactly the
  invention this entry exists to prevent.
* 222 tok against 386.

**How it was delivered — no new slot, no python.**  `parameter_list` was
ALREADY registered in `SCOPED_FRAGMENTS` (`agents/shared/prompts.py:721`),
whose table is deliberately a superset of what has a scoped copy today, and
`_build_template` splats `_scoped_fragments_for()` LAST so a scoped file wins
over the shared fragment.  `_build_template` is called with the constant
`"dc_output_inspector"` in every topology, so ONE file serves all three trees:
`DC_prompt_fragments/dc_config/parameters_dc_output_inspector.md`.

The scoped fragment also states the two structural facts most likely to be
invented from a render: the outer-ring HEIGHT is derived rather than a
parameter, and the middle section has no thickness, camber or high-point of its
own (only `middlePos` / `middleChord` / `middleAngle` exist).

**Verified.** The DCOI template was assembled under topology 7/reduced,
7/standard, 5/standard and 5/reduced: `$parameter_list` resolves in all four,
the names are present, no range bracket leaks, and `scoped_fragment_path`
returns the scoped copy for `dc_output_inspector` ALONE while the other eight
agents keep the full-ranges fragment.  `smoke_test_prompt_variant`,
`_prompts_hot_reload`, `_slot_splices`, `_topology_fragments`, `_fork_drift`,
`_prompts_admin` and `_attempt_coherence` all pass.

**Where.** `agents/dc_output_inspector/prompt.md:296`;
`agents/7agent_reduced/dc_output_inspector/prompt_7agents_reduced.md:246`;
`agents/5agent/dc_output_inspector/prompt_5agents.md:297`;
the shared full-ranges fragment is `DC_prompt_fragments/dc_config/parameters.md`
and the DCOI's scoped copy is `.../dc_config/parameters_dc_output_inspector.md`
-> slot `$parameter_list` (`agents/shared/prompts.py` FRAGMENT_TO_SLOT +
SCOPED_FRAGMENTS).
Related: F81 (also a silent-gap defect found the same way).

---

---

### F67. The Orchestrator has a soft "should" for turn-ending, and NO anti-loop rule at all

**Status.** FIXED 2026-08-11 in the Orchestrator fork, `56fab8b` (batch 1) —
7-agent REDUCED variant only; the shared prompt still carries both gaps for the
standard build.

**Part 1 turned out to be worse than "weak wording".**  The plan was to promote
"should" to MUST so it matched the delivered hard rule.  Reading the dispatcher
first showed the hard rule is FALSE for this reader:
`agents/orchestrator/orchestrator.py:502-511` — when the hub emits no tool call,
`final = rendered_content` and it returns `AgentHop(DONE, final)`.  The text is
DELIVERED TO THE USER as the final answer.  Nothing is discarded and no pipeline
halts.  So `generic_constraints_7agents_reduced.md` was telling the hub a
consequence that does not apply to it, while its own carve-out names "the
Orchestrator's final user-facing wrap-up" and defines it nowhere.

The same section also instructed an UNREACHABLE state — "when the cycle is
complete (after ``call_receptionist``), produce no further tool call".
`agents/receptionist/receptionist.py:437-440` returns `AgentHop(DONE, ...)` and
`orchestrator.py:690-691` returns `hop.message` immediately, so the hub is never
re-entered after that call.

The fork rewrites `## Output format` to state the true mechanism, define the
wrap-up the carve-out names, and drop the unreachable instruction.

**Part 2 was narrower than recorded here.**  The hub is not remedy-less on every
axis: `prompt.md:474-487` covers failure-retry and `:399-409` covers Planner
ping-pong.  What was genuinely absent is the SAME-READ-TWICE case, and the hub
holds four repeatable read tools (`orchestrator.py:447-461`).  The new bullet
lives in `## Escalation Hierarchy`, which already owns both exits, and its
discriminator is **"has any agent RUN since"** — NOT "the answer will not
change", which is false across a chain excursion: F71 bound `read_agent_history`
precisely so `prompt.md:386` could re-verify after one.

Original finding follows.

1. **"should" vs MUST.**  `agents/orchestrator/prompt.md:530` says "Every response
   *should* end with your next tool call", under a `## Output format` heading.
   The fragment it also receives (`generic_constraints.md:46-55` — outside both
   `<<CHAIN_ONLY>>` regions, so it DOES reach the hub) states the hard version
   plus the consequence.  The only dispatching agent in the system gets the
   weaker wording in its own prompt.

2. **No anti-loop remedy anywhere.**  A grep of `agents/orchestrator/prompt.md`
   for "do not loop" / "same tool with the same" / "same arguments you already" /
   "stuck" returns ZERO hits.  The operational long form lives in
   `agents/shared/routing.py:222-231` and the Orchestrator never calls
   `routing_instructions()` (verified: 0 occurrences in `orchestrator.py`).
   `generic_constraints.md:34-36` gives it the prohibition but no remedy.

Owner's decision 2026-08-10: the routing MUST, the halt consequence and the
anti-loop rule STAY unconditional in the shared core rather than move down.  The
missing remedy is a separate, deliberate fix.

---

### F69. `smoke_test_prompt_variant.py` cannot classify a routing-fragment override

**Status.** FIXED (this commit).  Was OPEN — it blocked a whole class of
variant override.  REPRODUCED 2026-08-10 (probe written, gate run, probe
removed, tree verified clean).

Dropping any `routing_*_7agents_reduced.md` into
`agents/7agent_reduced/prompt_fragments/` turns the gate RED:

    FAIL — 1 problem(s):
      [UNKNOWN] ...routing_user_input_inspector_uii_first_7agents_reduced.md
      shadows agents/shared/prompt_fragments/routing_user_input_inspector_uii_first.md,
      which is neither a prompt.md, a FRAGMENT_TO_SLOT entry, nor a recognised
      per-agent scoped copy

Cause: the six chain routing fragments are deliberately ABSENT from
`FRAGMENT_TO_SLOT` (`prompts.py:544-549`) because they load at WIRING time via
`_load_routing_fragment`, not at template-build time.  The test's classifier only
knows the three build-time categories.

Consequence already felt: the two conflicts that wanted a routing-fragment
override (the DCIC's missing `call_tool_caller`, the UII's CLARIFY collision) had
to be fixed elsewhere — in the shared fragment and in the existing `reduced7/`
fork respectively.  Any future routing override needs the classifier taught first.

**RESOLVED.**  `_ROUTING_FRAGMENT_AGENTS` maps the nine chain routing
fragments to their owning agent — the owner being fixed by which agent passes
that `fragment_name` at its `routing_instructions()` call site.  The three HUB
fragments (`routing_orchestrator`, `routing_receptionist`,
`routing_conductor_5agents`) are deliberately NOT in the table: they are real
slots and the `FRAGMENT_TO_SLOT` branch already classifies them.  A routing
override shadows a real shared file, so it falls THROUGH to the CONSUMED probe
rather than short-circuiting — a dead one is still caught.

`_check_routing_table()` keeps the table honest: every `routing_*.md` in the
shared dir must be classifiable by one branch or the other, or the gate fails
naming F69.  That matters because this sweep found NINE wrong or incomplete
enumerations, and each fix was itself a hand-maintained list that can drift
the same way.  This one polices itself.

Mutation-tested both halves: dropping a real
`routing_tool_caller_7agents_reduced.md` into the variant dir now turns the
gate GREEN and attributes it to `['tool_caller']` (it previously went RED with
[UNKNOWN] — the exact reproduction above); and deleting one table entry makes
`_check_routing_table` fire.  Probe removed, tree verified clean after both.

---

### F70. `smoke_test_prompt_format.py` skips the Receptionist on a false premise — a possible brace hole

**Status.** CONFIRMED and FIXED 2026-08-11.  `"RECEPTIONIST"` added to
`TEMPLATE_NAMES`; the comment that justified the exclusion rewritten.

**The premise really was false.**  `agents/receptionist/receptionist.py:99-104`
calls `.format(user_inputs_dir=..., extraction_output_file=...)`.  The comment
immediately above that call even concedes it — "the 7-agent prompt references
neither, so ``.format()`` is a no-op there — but it is still called" — and a
no-op `.format()` still raises on a malformed brace.  The Database Handler
exclusion IS correct: `database_handler.py:1022` assigns the template directly.

**Verified without running the harness** (it imports the agent packages, which
pull `langchain_core`, absent here).  Its check is just
`TEMPLATE.format_map(StubKwargs())` per name, and `prompts.py` imports fine with
the stubs used elsewhere in this session.  All 8 templates format clean under
both variants.  Mutation-tested: a bare `{` and a bare `}` are both caught, and
both crash `receptionist.py:99` at runtime if shipped.

**RESIDUAL GAP, pre-existing and NOT closed — applies to all 8 agents, not just
the Receptionist.**  `StubKwargs.__missing__` returns a stub for any key, so a
well-formed but unknown slot — `{bogus}` — passes the harness while raising
`KeyError` at agent construction.  That leniency is deliberate and cannot simply
be removed: legitimate runtime slots exist (the Orchestrator's
`{chain_access_block}`).  Closing it properly means giving the harness each
agent's ALLOWED slot set and rejecting anything else.  Worth doing if a
`{word}`-shaped accident ever ships; the malformed-brace case fixed here is the
one an author actually makes writing prose.

Original finding follows.

Its docstring (`:10-13`) and comment (`:54-58`) state that the Receptionist
"assign[s] their TEMPLATE directly to `self.system_prompt` with no `.format()`
call", and exclude it from brace coverage on that basis.  The audit reports that
`agents/receptionist/receptionist.py:99-104` DOES call `.format()`.

If that holds, the Receptionist is the one `.format()`ed agent with ZERO brace
coverage — a literal `{` or `}` in any fragment it receives would raise
`KeyError` at agent construction, in the exact place the harness assumes is safe.
That is the ⚠3 failure mode the harness exists to prevent.

VERIFY BY EXECUTION in an environment that has the dependencies before acting.

---

---

### F71. The Orchestrator is ordered THREE TIMES to call a tool it does not hold

**Status.** FIXED 2026-08-11 in `ed8569a` (shared tree, topology 7 — the 5-
and 3-agent hubs use `cond_tools` / `arch_tools` and are unaffected).

**Correction to the finding below: it was TWO sites, not three.**  `:119` is
correct as written — in context the Orchestrator is quoting an instruction to
HAND TO the Planner ("point the Planner at the source"), and the Planner does
hold the tool.  Only `:348` and `:386` were real, and they needed different
fixes:

  * `:386` — BOUND the tool.  Nothing else could serve it: the chain-access
    block (default ON, `session.py:41`) injects hand-off PROSE
    (`[FROM x, TO y]: <message>`), never tool results, and
    `list_attempts` / `read_attempt` read attempt FOLDERS, not message history.
    Precedent, not judgement, decided this: the same bug class was already
    found and fixed by BINDING in the 5-agent Conductor, whose comment at
    `conductor.py:350-357` records the live consequence of a hub prompt naming
    unbound tools — a wrong call, an error, then a wasted routing hop.
  * `:348` — DELETED, along with the bullet after it.  Its three clauses were
    (a) mechanics the tool schema owns, (b) "never guess a path", already owned
    fleet-wide by `hard_constraints_tools` bullet 1, and (c) a numbered pointer
    to a list 160 lines below in the same prompt, plus an inline restatement of
    the rule it pointed at.  The one non-redundant clause — "never omit an
    attempt", the completeness lower bound to rule 4's upper bound — survives
    with the tension resolved inside the sentence instead of by footnote.

Original finding follows.

`agents/orchestrator/orchestrator.py:439-452` builds `orch_tools` as: six
routing tools, `calculate`, `list_attempts`, `read_attempt`, `new_attempt`
(plus three DBa tools when RAG is on).  **`read_agent_history` is not in it.**
It is built once at `:287` and handed only to the Planner (`:310`) and the
Receptionist (`:318`).

The Orchestrator's prompt orders it anyway:

| line | text |
|---|---|
| `:119` | "``read_agent_history('dc_output_inspector')``" |
| `:348` | "confirm it via ``read_agent_history`` (the Tool Caller / DCIC / …)" |
| `:386` | "``read_agent_history(<the escalating agent>)`` and read the failing tool's …" |

`:348` is inside a rule that says to confirm something BEFORE calling the
Planner or Receptionist — so the hub is told to gate a routing decision on a
tool call it cannot make.  Worse than a duplicate: the model either invents the
call and fails, or silently skips the confirmation step.

**Fix is a choice, not a wording change:** either add `read_agent_history` to
`orch_tools`, or reword all three sites to `list_attempts` / `read_attempt`,
which the Orchestrator does hold.  Decide when the Orchestrator's prompt comes
up in the reduction (it is also F67's file).

---

### F72. Receptionist Situation B forbids `calculate` while a hard rule orders it

**Status.** FIXED 2026-08-11 (shared tree, all topologies read this prompt).
CON-25 is closed — but its stated risk was OVERSTATED, and the fix that
shipped is not the one it proposed.

**CON-25 said "Situation B is exactly where arithmetic shows up", citing two
sections.  Both of them FORBID the Receptionist from computing:**
`prompt.md:316` — "this must come FROM the hand-off — do not work it out
yourself"; `:324` — "the fidelity / ceiling wording must come from the
hand-off".  Situation B is relay-only by design, so the clash fires only on
arithmetic the Receptionist performs incidentally.  Still a real conflict —
two absolutes, and any incidental sum forces a violation — but rarer than
the finding implied.

**The deeper defect was the whitelist's own incoherence.**  It claimed its
criterion was "the read-only / display ones that do not loop control back",
then banned `read_agent_history` two lines earlier — which is read-only and
does not loop.  The criterion did not produce the list, so a model applying
it as written would conclude `read_agent_history` was allowed.

The real criterion, visible once the relay-only design is seen, is: tools
that DISPLAY what the hand-off designates, or COMPUTE on numbers it already
carries — not tools that gather new material.  That explains every entry,
gives the `read_agent_history` ban an actual reason (tying it to the
never-invent rule the rest of Situation B rests on), and places `calculate`
on the permitted side.  Shipped as a restatement rather than CON-25's
one-word insertion, +85 chars.  Also rewrapped a 108-column line.

Original finding follows.

`DC_prompt_fragments/tools_config/hard_constraints_tools.md` (and its reduced
override) says "route EVERY arithmetic operation through the ``calculate``
tool".  `agents/receptionist/prompt.md:216-219` says "The **ONLY** tools
permitted here are the read-only / display ones that do not loop control back:
``read_attempt``, ``list_attempts``, ``visualize_3d_model`` and
``propose_attempt``".  `calculate` IS bound (`receptionist.py:126`, bound at
`:145`) but excluded from that whitelist.  Both statements are absolutes.

Situation B is where a number reaches the user unreviewed ("70 mm -> 65 mm"),
so this is the worst possible place for the arithmetic rule to be voided.

**Fix: add ``calculate`` to the Situation B list.**  It does not loop control
back, so it belongs there on the whitelist's own stated criterion.

---

### F74. The "only these five" path-label list is incomplete — FIXED

**Status.** FIXED (this commit).  Was CUT in the 7-agent reduced variant
2026-08-10 and OPEN everywhere else.

`DC_prompt_fragments/tools_config/hard_constraints_tools.md:2-5` states that
read tools take "only" the paths given by five named labels.  At least these
live labels are missing:

  * ``Extraction output file:``  — the UII's own WRITE target
    (`user_input_inspector.py:107-108`)
  * ``Input file directory:``    — the Orchestrator's incoming label
  * ``Attempts this cycle:`` / ``Show to user:`` — Receptionist

An exhaustive list that omits four live labels, one of them an agent's own
write destination, is worse than no list.  The reduced variant deletes it (each
label lives in its consuming tool's schema).  The standard and 5-agent trees
still carry it and must either complete it or drop it the same way.

Related: it is ALSO wrong for the Receptionist, which receives NONE of the five
— see the hard_constraints_tools fork note.

**RESOLVED** by DROPPING the list at source rather than completing it, which
follows the precedent the reduced override already set.  The bullet now reads
"DON'T invent or guess a path.  Every path you hand a tool must trace to a
label in your incoming message or to an upstream tool's return value." —
wording deliberately close to the reduced override so the trees do not diverge
in meaning.  Completing it would have meant nine-plus labels and a list free to
go stale on the next one.

Re-verified before the cut.  The five listed labels are all real (9-21 prompt
files each).  So are all four omissions — and `Extraction output file:` appears
in ELEVEN files, as widespread as `Extracted inputs file:`, which IS listed.
The standard Receptionist receives none of the five and uses two of the
omissions (`Attempts this cycle:`, `Show to user:`), so the list was wrong in
both directions at once.

Blast radius: 14 prompts (8 standard, 6 five-agent).  The 8 reduced forks were
already on their own override.  Bullets 2 and 3 untouched — bullet 3's
coherence invariant is F75's subject.

---

### F75. Attempt-folder coherence is an invariant nothing enforces

**Status.** FIXED-NARROWED in the params-first order; the mesh-first order
was closed separately as **F75b** below.  **DORMANT since 2026-08-20**:
`generate_and_render_propeller` now takes the attempt's `parameters.json` PATH
instead of 16 values, so the numbers it builds from COME from the record and
cannot disagree with it.  This comparison is unreachable through the agent path.
KEPT, not deleted — it still guards any future caller that reintroduces
value-passing, and `smoke_test_attempt_coherence` now exercises it directly
instead of through the tool.

The removed clause said a folder's mesh and ``render_*.png`` must have come
from that folder's own ``parameters.json``.  Nothing checks it:

  * `tools/generate_mesh/generate_mesh.py:177-213` (`_validate_output_dir`)
    checks only that `output_dir` exists under the attempts root — never that
    the parameters passed in match the folder's `parameters.json`.
  * `generate_and_render_propeller` REUSES any pre-existing
    `propeller_mesh.obj` without comparing it to the 16 values in the same
    call.
  * `render_blade_sections.py:112-113` writes into `src.parent`, guarded only
    by "somewhere under the attempts tree".

Prose was removed because the actionable core is stated more strongly in
`agents/tool_caller/prompt.md:11-13` ("that path is the only folder you may
write into this cycle"), in the prompt of the only agent that can violate it.
What remains is a system invariant no agent acts on — which belongs in code.

**Fix: have `_validate_output_dir` compare the passed parameters against the
target folder's `parameters.json` and refuse on mismatch.**

**THAT WORDING IS SUPERSEDED — do not implement it as written.**  Putting the
comparison in `_validate_output_dir` and refusing on mismatch would, on day
one: refuse `smoke_test_generate_mesh.py` on 100% of runs (it never writes a
`parameters.json` — verified, zero occurrences); `TypeError`
`smoke_test_param_rename.py:92-96`, which patches that function with a
ONE-ARGUMENT lambda; block the Orchestrator's documented DCIC-failure recovery
folder (`new_attempt` writes no parameters.json); block the 3-agent Designer
structurally (it can emit the geometry call before `write_parameters` in one
response); and wall off the highest-traffic geometry path.

**WHAT SHIPPED INSTEAD.**  A `_param_mismatches` helper called from the tool
body; `_validate_output_dir` keeps its one-argument signature (asserted
offline by the new smoke test, since the test that would catch it needs
langchain and cannot run in a bare worktree).  The BUILD branch REFUSES on a
mismatch — that is the case that permanently writes a mesh contradicting the
folder's record, and `/api/download_geometry` regenerates the USER'S
DELIVERABLE from `parameters.json`, so the file they receive would not be the
propeller they approved.  The REUSE branch WARNS and proceeds: it never reads
the passed parameters, usually writes nothing, and is the path every DCOI
re-render takes, so refusing there would block work on grounds that cannot
change the outcome.  A missing / empty / unparseable / incomplete
`parameters.json` always proceeds.  Comparison is numeric only —
`math.isclose` for the 13 floats, exact `==` for the three ints — and a legacy
`impellerHeight` key is ignored.  The error quotes the on-disk values so the
corrective retry carries different arguments and does not trip the identical-
signature `stuck_escalation` at `tool_caller.py:213-218`.

Covered by `extra_utilities/smoke_test_attempt_coherence.py` (18 assertions,
fully offline), which proves it fires AND does not over-fire.

---

### F75b. The mesh-first order is still unguarded

**Status.** FIXED 2026-08-20 — the build branch writes a `mesh_params.json`
provenance sidecar recording exactly what produced the mesh, and the three
`write_parameters` handlers refuse a record that contradicts it.  Fails open:
no sidecar means nothing to compare, so every folder that predates the fix
stays writable.

**DORMANT the same day**, for the same reason as F75: the tool now READS the
parameter record, so it cannot run before one exists and a mesh can no longer
precede its parameters.  The guard should never fire again.  Kept for the same
reason — see F75's note.

Split out of F75 so that row could ship on its own.

F75's guard catches "folder has a record, mesh built from different values".
Swap the two calls and the identical corruption goes through unseen: build a
mesh into a folder with no `parameters.json` (the guard correctly proceeds —
no record to compare), then call `write_parameters`, which SUCCEEDS because
the append-only check tests only for `parameters.json` and never looks for a
`propeller_mesh.obj` (`dc_input_creator.py:416`, `creator.py:443`,
`designer.py:510`).  Reachable via the Orchestrator fallback folder, and
inside a SINGLE model response in the 3-agent tree.

**Fix sketch:** have the build branch write a provenance sidecar
(`mesh_params.json`) recording exactly the kwargs that produced the mesh, and
have the three `write_parameters` handlers refuse when that sidecar exists and
disagrees.  Four files plus a new artefact in every attempt folder — its own
approval, not a rider on F75.

**Also still unguarded, smaller:** `render_blade_sections` writes to
`src.parent` and accepts any JSON under `attempts/` carrying its 13 required
keys; nothing binds `output_dir` to the CURRENT attempt; and the root cause is
untouched — `read_parameters` returns raw text and the model retypes 16
numbers every cycle, so the guard alarms on drift rather than removing it.

---

---

### F76. `logs/attempts/` does not exist — 15 stale sites, fleet-wide

**Status.** FIXED 2026-08-11.  All 15 sites rewritten to `attempts/`.

**The fact.** `config.py:38` is the SOLE assignment in the repo:
`ATTEMPTS_DIR = PROJECT_ROOT / "attempts"`.  `LOGS_DIR` is a separate
constant at `config.py:33`, and nothing anywhere creates a `logs/attempts`
directory.  `docker-compose.yml:101` mounts `./attempts:/app/attempts`.

**Why it mattered more than prose.** Three of the fifteen were TOOL SCHEMAS —
`generate_mesh.py:184`, `render_mesh.py:37`, `render_mesh_pyvista.py:45` —
which ship to the Tool Caller every turn on the tool-definition channel.  An
agent sanity-checking or reconstructing a path against that text would have
built one `_validate_output_dir` (`generate_mesh.py:177-213`) then rejects.
The hand-off-label discipline normally prevents construction, which is why
this never surfaced as a visible failure.

**Sites fixed:** `agents/orchestrator/prompt.md:136`,
`agents/planner/prompt.md:529`, `agents/dc_input_creator/prompt.md:222`,
`agents/tool_caller/prompt.md:11,120`,
`DC_prompt_fragments/dc_config/output_file_locations.md:2`,
`DC_prompt_fragments/tools_config/agent_tools_overview.md:4`, the three tool
schemas above, plus the 5-agent tree —
`agents/conductor/prompt_5agents.md:428,871`,
`agents/creator/prompt_5agents.md:444`,
`agents/5agent/tool_caller/prompt_5agents.md:11,120`.

**Deliberately NOT changed:** `agents/loader.py:227`.  Its
`"logs/attempts/inputs"` is a prose list of THREE directories inside an EXDEV
comment, not a path.

Found while auditing `agent_tools_overview.md`, which carried one of the
fifteen.  Cutting that fragment would have fixed nothing on its own — the
copy the hub actually quotes into hand-offs is `orchestrator/prompt.md:136`.

---

---

### F77 — FIXED (`3677f78`)
**`{render_check_library_block}` was dead under the shipped default — code fix,
not a prompt fix.**  `agents/tool_caller/tool_caller.py:148-152` picks
`RENDER_CHECK_LIBRARY_PYVISTA` / `_TRIMESH` by render library alone; there is no
mesh-checks gate (`self.mesh_checks` is stored at `:119` and never consulted
here).  The block is 1,306 chars (`trimesh.md`) / 1,988 (`pyvista.md`) and is
almost entirely metric semantics — how watertightness, signed volume and the
`< 1e-10` mm² degenerate-face threshold are computed — introduced as "a few
specifics worth keeping in mind so you read the tool's return text correctly".

But `workflow_settings/settings.py:33` ships `MESH_CHECKS: bool = False`, and
with it off the backend emits none of it: `tools/render_mesh/render_mesh.py:281`
guards the Watertight / Volume / WARNING findings and `:329` guards the summary,
mirrored at `render_mesh_pyvista.py:209`.  So by default the Tool Caller is told
how to read a report it never receives — 14-21% of its 9,321-char prompt again.

**Why the reduced fork could not fix it.**  `.format()` runs AFTER
`_build_template`, so `apply_flag_filters` has already run and `<<MESH_ON>>`
markers placed inside the injected fragment would NOT be filtered.  Dropping the
placeholder from the prompt is the WRONG fix — it removes the block even when
mesh checks ARE on, and it would not error, because `.format()` tolerates the
now-unused kwarg.  The gate belongs in `tool_caller.py`: pass `""` when
`session.mesh_checks` is False.

**RESOLVED** in `3677f78`, and slightly differently from the sketch above.
The OFF state is a new fragment
`DC_prompt_fragments/tools_config/render_check_library/off.md` rather than an
empty string: with checks off nothing else told the agent the metrics were
absent (`hard_constraints_dc`'s metrics bullet is `<<MESH_ON>>`-gated and
therefore stripped) while the prompt still asked it to report "the numbers
from THIS cycle's return".  `off.md` says what the render step DOES return —
the three views and the bounding box, which `render_mesh.py` appends before
the gate.  BOTH call sites were fixed: `tool_caller.py` (live) and
`designer.py:213-218` (latent — `agents/designer/` has no `prompt.md` yet, so
the path cannot run, but the defect was identical).  Measured: Tool Caller
full system prompt 15,297 -> 14,220 (trimesh), 15,965 -> 14,220 (pyvista).

---

### F78
**The `Mesh file:` label has no reader.**  `agents/tool_caller/prompt.md:105`
makes it one of three labels that MUST appear on every routing call, but the
string occurs repo-wide only there and at
`agents/5agent/tool_caller/prompt_5agents.md:105`.  The DC Output Inspector
binds no mesh-consuming tool (`dc_output_inspector.py:240-251`), the
Orchestrator's hand-off block asks for attempt number + folder path, the
Receptionist derives `<attempt>/propeller_mesh.obj` itself, and no Python parses
it.  ~60 chars.

**KEPT deliberately** in the reduced fork (owner's call): it is the hand-off's
only human-readable proof the mesh reached disk, and cutting a label with no
reader is only safe if nothing downstream ever starts reading one.  Recorded
rather than removed.

---

### F79 — FIXED (this commit)
**`tool_inventory.md:11-13` pointed the Tool Caller at a tool it does not hold.**
`read_attempt`'s entry ends "an image or mesh returns a path to hand on, e.g. to
``view_images``" — but `agents/tool_caller/tool_caller.py` never calls
`build_user_inputs_tools`, so this agent has no `view_images`.

**CORRECTION to this entry's own first reading, and the reason it was worth
fixing rather than filing:** `$tool_inventory` is NOT shared across agent
types.  It is spliced into TOOL CALLER prompts only — `agents/tool_caller`,
`agents/5agent/tool_caller`, `agents/7agent_reduced/tool_caller` — and none of
them bind `view_images`.  So the pointer was wrong for EVERY consumer of the
fragment, not correct-elsewhere-and-wrong-here.  "Shared fragment" was read as
"many agent types read it"; here it means three files that are all the same
agent.

**FIXED** at source, which repairs all three variants at once: the example now
reads "a path to hand on to whoever can load it", which for the Tool Caller is
the DC Output Inspector — exactly what its `Render images:` contract already
does.  The SCHEMA needed no change: `attempts_tool.py:215-217` says "hand it to
a tool that loads images (e.g. `view_images`)", which is generic with an
example and ships to the four agents that genuinely bind it.

---

### F80 — FIXED (this commit)
**The UII did not signal how hard the extraction was.**  The DC Input
Inspector fork now tells the DCII to re-check the raw user inputs when "the
extraction or an incoming hand-off reports that the user's inputs were hard to
interpret" (E7, DCII batch 2) — but nothing currently produces that signal.
The User Input Inspector writes no interpretation-difficulty marker into
`extracted_inputs.txt`, and no hand-off carries one.

**To do, inside this prompt-reduction task:** have the UII state, in the
extraction, whether interpreting the user's inputs was straightforward or
genuinely ambiguous — and on WHAT (a unit, a sketch callout, a qualitative
phrase that could map several ways).  Until then E7's fourth trigger fires only
when an agent volunteers the difficulty in prose.

Owner's instruction when approving DCII batch 2.

**RESOLVED.**  §3 DESIGN INTENT of
`agents/7agent_reduced/user_input_inspector/prompt_7agents_reduced.md` now
ends with `**INTERPRETATION: straightforward**` or
`**INTERPRETATION: ambiguous, <what was open to reading>**`.  The owner chose
the ALWAYS-STATE form over a when-present note, so silence is meaningful
rather than ambiguous between "clean read" and "never considered" — the same
failure mode as the Tool Caller's freshness signal, where a reused render and
a fresh one produced byte-identical hand-offs.

Placed OUTSIDE the "Also state here, when present:" bullet list, since an
always-stated line under a when-present heading contradicts itself and the two
sibling bullets (PRECISION DEMAND, SOFT TARGET goal) are genuinely conditional.

Producer and consumer are BOTH reduced-fork-only and stay symmetric: the
standard DC Input Inspector has no such trigger (`grep` returns 0).  The DC
Input Creator was deliberately NOT given a consumer — it binds no image tools,
so its realistic response to an ambiguity note is a CLARIFY it can already
send for other reasons.

---

---

### NEXT1. Deploy Stage A to Railway + stand up Rhino Compute on Azure

**Status.**  **DONE.**  Re-statused 2026-08-21: both halves shipped.
`README.md:548` records it — "RhinoCompute now runs on an Azure VM, the Stage A
FastAPI app runs on Railway."  The entry had read "NOT STARTED … the single
highest-priority task" for months after the work landed, which made the file's
own top section actively misleading.

**Kept in full below** rather than trimmed: the sub-tasks record the deploy
decisions that were actually taken (Railway CLI rather than the GitHub App,
because the Railway GitHub App is not authorised on the `R-SMP` org), and that
constraint still governs every redeploy.

**Two coupled sub-tasks:**

**(a) Shift all code to Railway.**
  * Deploy is via the **Railway CLI (`railway up`)**, NOT GitHub
    auto-deploy: the Railway GitHub App is not authorised on the
    `R-SMP` org and that needs an org-owner approval we do not
    control.  No push-to-deploy; each deploy is a manual
    `railway up` from the `stage-a-web-deploy` worktree.
  * Follow `extra_utilities/docs/reference/cloud_deploy_runbook.md` end to end:
    §1 open the existing empty (Pro-workspace) Railway project
    `agentic-rag-design-config`
    (id `644e017b-b027-455a-b1f8-5a86952feae5`), create the
    `stage-a` empty service, set its EU-West region, install +
    `railway login` + `railway link`,
    §2 set service env vars (`INVITE_CODE`, `OPENAI_API_KEY`,
    `ANTHROPIC_API_KEY`; NOT R2 — Stage B), §3 `railway up` +
    the five smoke checks, §4 operational notes.
  * Decision still open at deploy time: whether `main` gets the
    Stage A merge before or after the first green Railway deploy.
    Recommended: deploy `stage-a-web-deploy` directly (Railway can
    track any branch), validate the cloud URL, THEN merge to
    `main`.
  * Pre-flight gate: OPS1 spend caps must be confirmed set
    (user reported done — re-verify in the dashboards before the
    URL is shared).

**(b) Set up and use Rhino Compute on the Azure server.**
  * Stage A's local validation pointed `RHINO_COMPUTE_URL` at the
    developer's local Rhino Compute (`localhost:6500` native /
    `host.docker.internal:6500` in Docker).  Neither is reachable
    from Railway.
  * Provision Rhino Compute on the Azure Windows VM (region was
    still TBD as of the last project-memory note — confirm /
    finalise the region now).  Expose it on a URL Railway can
    reach over the network, secured by `RHINO_COMPUTE_API_KEY`.
  * Set `RHINO_COMPUTE_URL` (and `RHINO_COMPUTE_API_KEY`) as
    Railway service env vars to that Azure endpoint.
  * Until (b) is done, the cloud app will boot, gate, and chat,
    but any propeller-design request fails the moment it reaches
    Tool Caller → `generate_propeller_mesh` (connection refused).
    Deploying (a) first and accepting "no mesh tools until (b)"
    is a valid intermediate state for verifying the deploy path —
    it is explicitly NOT the Stage A end state.

**Definition of done.** An invited-only `*.up.railway.app` URL
where a fresh visitor enters the invite code, describes a
propeller, and gets renders inline — i.e. the Stage A end state
from the re-staging plan, running in the cloud rather than on the
developer's laptop.

**Where the detail lives.** `extra_utilities/cloud_deploy_
runbook.md` (the step-by-step), project memory
`project_test11_v3.md` (current state + decisions), and
`cloud_architecture_notes.md` C1/C5 (Railway + domain rationale).

---

---

### F4. Shift from Streamlit to a JavaScript-based web interface

**Where.** Today: `streamlit_app.py` is the entire web layer
(Stage A, Phase 3).  Target: a JavaScript-based frontend (SPA or
HTMX-driven) talking to a thin API that calls the existing
`agents/dispatch.py:dispatch_turn`.

**What to build.** Replace the Streamlit surface with a real web
frontend.  The agent layer does not change — `dispatch_turn` +
the `Session` plain-data contract are already the seam.  The work
is: (1) a small HTTP API (FastAPI) exposing "start session",
"submit turn", "end session", "fetch artefacts"; (2) a JS
frontend (framework TBD — plain HTMX over server-rendered
fragments is the lowest-effort option per
`cloud_architecture_notes.md` C2's "Future migration" subsection;
a React/SPA is the heavier option) that consumes it; (3) porting
the invite-code gate, the chat transcript, inline render display,
and the "End Session" / future "Save" controls.

**Why deferred.** Streamlit got Stage A to a deployed, gated,
working chat UI fast and with zero JS.  A JS frontend is only
worth the 4–7+ days once Streamlit's limitations start to bite on
real usage — see the eight enumerated limitations in
`cloud_architecture_notes.md` C2 (whole-script rerun, multi-user
concurrency, layout rigidity, no real progress streaming for the
minutes-long pipeline, "Made with Streamlit" branding, awkward
auth integration, etc.).  Migrate when **two or more** of those
bite in practice, or when the app needs to face a non-invited
audience.

**Hard constraint when this is done.** Do not let the migration
leak agent logic into the frontend.  `warnings_developer.md` W17
spells out the rule: the web layer stays a thin I/O surface over
`dispatch_turn`; the JS frontend should be a drop-in replacement
for `streamlit_app.py`, not a rewrite of the pipeline.  Settle
the multi-user-concurrency story (Stage B path-namespacing, O9 /
W13) before or together with this — a real frontend invites real
concurrent users.

**Status.** **DONE 2026-08-21.**  Delivered, then the old surface was removed.

`web_app.py` (FastAPI) + `web/` (plain JS) are the production frontend --
`Dockerfile` ends with `CMD ... uvicorn web_app:app`, so this is what Railway
runs.  `streamlit_app.py` was deleted and `streamlit>=1.39.0` dropped from
`requirements.txt` (it had been shipping into the Railway image for a process
that never started).  `warnings_developer.md` W17, whose own closing line said
to retire it "once F4 lands", was rewritten from "Streamlit is an INTERIM web
interface" to the durable thin-shim rule.  `cloud_architecture_notes.md` C2,
which made Streamlit the sole entry point, now carries a SUPERSEDED banner.

The original entry follows, unchanged, as the record of what was planned.

**Superseded status line.** Open, deliberately deferred.  Post-Stage-C /
productionisation work.  Triggered by the "two or more C2
limitations bite" condition above, or by a public-audience
requirement.  Paired warning: `warnings_developer.md` W17.

---
