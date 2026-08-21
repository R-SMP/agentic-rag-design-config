# Known issues, temporary fixes, and TODOs

This file tracks open issues in the codebase and any **temporary** /
**stop-gap** patches that have been applied to work around them.
Each entry should record:

- **What** the bug is and how to reproduce / observe it.
- **Why** the fix is temporary (what the proper fix would look like).
- **Where** the temporary patch lives in the code (file paths +
  search strings) so reverting it is mechanical.
- A **status** field so future-you can scan the open list at a glance.

**Filing convention (rewritten 2026-08-21).**  APPEND new entries at the end
and give them the next free id.  Status is carried by the `**Status.**` line
and by the index below — **never by position in the file**.  Do not try to keep
closed entries at the bottom: that convention was in force here for months and
had already collapsed (entries F29-F89 sat under a `## Resolved issues` heading
while most of them were open).  When an entry is fully closed, move it to
`TODO_archive.md` verbatim.  If it is only partly closed, leave it here.

**Ids are never reused and never renumbered.**  ~19 F/O ids and 24 W ids are
cited from live source, and the counter is a single space reserved across git
branches (F36 is taken on a sibling branch).  Next free id: **F94**.

**Do not `cat` this file.**  Read the index, then pull the one entry you need:
`grep -n "^### F58" -A 40 extra_utilities/TODO_known_issues.md`.

---

## Index — every open entry

One row per entry in this file, in file order.  Closed entries live in
`TODO_archive.md`.  Pull one entry with
`grep -n "^### <id>" -A 40 extra_utilities/TODO_known_issues.md`.

| id | status | title |
|---|---|---|
| `O1` | OPEN | Database Handler: handle dangling tool_use in frozen snapshots |
| `O2` | OPEN | Database Handler: rate-limiter coupling on `agent.base_llm` |
| `O3` | OPEN | Database Handler: context-window pressure on multi-agent interviews |
| `O6` | OPEN | Database Handler: file-as-is database fields are skipped |
| `O7` | OPEN | Database Handler: 2D model files row is "Not yet implemented" |
| `O8` | OPEN | Database Handler: DCII-disabled rows write empty placeholders |
| `O9` | OPEN | Stage A: single-user-at-a-time on disk paths |
| `O10` | OPEN | Stage A: "End Session" only — no Save button until Stage B |
| `O5` | OPEN | Database Handler: end-of-session save-prompt UX |
| `OPS1` | OPEN | Set hard monthly spend caps on every LLM provider dashboard |
| `OPS2` | OPEN | Validate the Database Handler on the cloud deployment |
| `F1` | OPEN | `dc_parameter_schemas` auto-loader from Grasshopper-side declarations |
| `F2` | OPEN | Per-parameter weights for masked-RMSE |
| `F5` | OPEN | LOG and Status view: colorise the log and refine its look |
| `F6` | OPEN | LOG and Status view: show tool-call payloads on the flowchart |
| `F8` | OPEN | Split tools into generic vs DC-specific and consolidate under `tools/` |
| `F12` | OPEN | Verify the Context Pruner works as intended |
| `F13` | OPEN | Remove the Railway persistent volume once R2 mirror is verified |
| `F14` | OPEN | Verify the new identifying-attempt force-tool flow on Railway |
| `F15` | OPEN | Tighten DH response handling — safety net + slightly stricter prompt |
| `F16` | OPEN | Verify the multi-answer split + multi-attempt identifying-Q flow |
| `F17` | ADDRESSED | Scrap empty / "nothing to specify" DH answers instead of saving canonical negation sentences |
| `F18` | OPEN | UII / Receptionist: don't treat session-level numeric requests as design parameters |
| `F19` | OPEN | De-duplicate attempt uploads within a session |
| `F20` | OPEN | Compensate orphan artefacts when the identifying conversation raises after a successful force-tool u |
| `F21` | OPEN | Cache the boto3 client at module level |
| `F9` | OPEN | "Copy parameters list" should return the SELECTED attempt's parameters |
| `F10` | OPEN | LOG and Status view: fix the dynamic gray Orch arrows |
| `F11` | OPEN | Stop button: tighten the cancellation granularity |
| `F22` | OPEN | Support multiple simultaneous users (multi-tenant Stage A) |
| `F23` | OPEN | Replace the Context Pruner's pre-scan + tier-2 input cap with something less crude |
| `F25` | OPEN | Pre-compute the active FIXED parameter set in Python instead of asking the UII to walk user_query.tx |
| `F26` | OPEN | Verify the Planner's behaviour in problematic / non-happy-path cases |
| `F27` | OPEN | Live-preview ON / OFF toggle in the Parameters Inputs view |
| `F28` | OPEN | ``sessionStorage`` persistence of Parameters Inputs panel state across page reload |
| `F29` | OPEN | Improve the DCII's extraction-fidelity verification step |
| `F30` | OPEN | Render-view selection for retrieve_attempt is currently a developer-time choice |
| `F31` | OPEN | SSE disconnect-recovery cache for /api/turn + /api/end completion events |
| `F32` | OPEN | Estimate parameters from visual proportions in user-supplied images |
| `F34` | OPEN | Compress user-input images before save / retrieval / LLM-pass |
| `F35` | OPEN | Re-audit the Context Pruner — does it act on the Database Handler or not? |
| `F37` | OPEN | Evaluate VLM-enriched text for user-image multimodal embeddings |
| `F38` | OPEN | OCR region re-read relies on the detector spotting every text region |
| `F42` | PARTIALLY ADDRESSED | Make the Planner and DCOI processes faster / more focused |
| `F44` | NOT STARTED | Check whether the Context Pruner and Database Handler have / need blade-sections-tool info |
| `F45` | PARTIALLY ADDRESSED | Refine blade-section parameters in place (no new attempt per tweak) |
| `F46` | DEFERRED | Cross-schema-version session search — DEFERRED, blocked on T1 |
| `F52` | NOT STARTED | Sessions Queue overnight runner: SOLID token / rate / context-limit resilience |
| `F53` | PARTLY DONE | Prompt caching: port conversation-history caching to the 3-agent system |
| `F54` | OPEN | Verify save-phase prompt caching on a REAL session save |
| `F55` | OPEN | The briefing anchor: cache the DH's re-seeded base history ACROSS fields |
| `F56` | OPEN | `SYSTEM_TOPOLOGY` is read fresh mid-turn, so a run in flight is not pinned |
| `F57` | OPEN | The two hubs differ in chain access, which confounds a 7-vs-5 comparison |
| `F58` | OPEN | A 5-agent save loses 17 of the 36 default schedule rows, three different ways |
| `F59` | OPEN | Six verified defects in the DH save path (from the 2026-08-04 audit) |
| `F83` | OPEN | The UII's categorisation rule says "two buckets" but there are three sections |
| `F84` | OPEN | The generic CLARIFY bullet needs a per-agent patch paragraph in every first-agent fragment |
| `F89` | OPEN | The STANDARD hub prompt names retrieval tools outside the <<HAS_DBA>> gate |
| `F88` | OPEN | Giving the 5-agent / 3-agent / any future reduced system its own DBa distribution is a DATA change,  |
| `F85` | OPEN | The prompt sections describing the RAG tools are stale after the retrieval rework |
| `F60` | OPEN | Duplications in the assembled prompts that the shrink proposal does not target |
| `F61` | OPEN | `_authorisation_sources()` is topology-gated — a trap for any replacement that names the Planner |
| `F62` | OPEN | The UII prompt teaches "never invent a parameter" using an invented parameter |
| `F63` | PARTIAL | `middlePos` schema said the opposite of the prompts — fixed in the tool, NOT in the DB seeder |
| `F64` | PARTIAL | Six agents hard-code the sender of their incoming hand-off; only the Tool Caller gets it right |
| `F65` | OPEN | SUGGESTED SECTION SHAPES has no producer in the REDUCED prompt variants |
| `F66` | OPEN | Is the DCOI's "don't dictate exact params" bullet a repetition? — check when the DCOI is reduced |
| `F68` | OPEN | The DCIC is told the UII both is and is not an authorisation source |
| `F73` | OPEN | The DCII is told `parameters.json` is "overwritten".  It never is. |
| `F86` | OPEN | The reduced tree dropped the per-agent TRIGGERS for the user-input reading tools |
| `F87` | OPEN | C3 cannot be tested by the current variant switch, and its original evidence was a counting artefact |
| `F90` | OPEN | The eager `*_TEMPLATE` block in `prompts.py` — nine import-time, topology-frozen constants |
| `F91` | OPEN | Per-agent STATEFUL / STATELESS toggle in the Workflow-Settings agent flow chart |
| `F92` | PARTIALLY CLOSED | Four defects the 5-agent merge inherited from the 7-agent system — status re-checked 2026-08-21 |
| `F93` | OPEN | Pending actions embedded inside `warnings_developer.md` — index |

---

## ⇒ IMMEDIATE NEXT ACTION

**This slot is currently EMPTY** (2026-08-21).

`NEXT1` (deploy Stage A to Railway + stand up RhinoCompute on Azure) is **DONE**
and has moved to `TODO_archive.md`.  Nothing has been nominated to replace it —
that is a deliberate owner decision, not an oversight.

When something is nominated, put it here as `NEXT2` and say why it outranks
everything else.  Until then, pick work from the index below.  The
highest-signal open candidates today, by the file's own status lines, are
`F52` (Sessions-Queue overnight resilience — "relatively HIGH importance"),
`F34` (image compression — "High priority"), `F58` / `F59` (verified DH
save-path defects) and `F85` (prompt sections stale after the retrieval rework).

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

### O9. Stage A: single-user-at-a-time on disk paths

**Where.** Every agent and tool that reads or writes the global
paths in `config.py` (`USER_INPUTS_DIR`, `ATTEMPTS_DIR`, `LOGS_DIR`,
`INPUT_IMAGES_DIR`).  Same surface as `warnings_developer.md` W13.

**What.** Stage A's web app isolates per-browser-session UI
state client-side, but the agents underneath still
write to the global on-disk paths.  Two users hitting the same
pod simultaneously will collide — they will share `inputs/user_
query.txt`, they will see each other's renders under `attempts/`,
and their per-agent log files in `logs/agent_histories/` will
overwrite each other.

**Required behaviour.** Each web user-session needs its own
namespaced directory tree under `inputs/<session_id>/`,
`attempts/<session_id>/`, and `logs/<session_id>/`.  The
`Session.create_for_v3(...)` factory in `agents/shared/session.py`
already constructs the right Path objects, but the agents and
tools currently bypass `session.inputs_dir` / `attempts_dir` /
`logs_dir` and read straight from `config.*`.  The fix is to
plumb the per-session paths through:

- every agent that opens a file under one of those paths
  (Receptionist, UII, Planner, DCIC, DCOI, Tool Caller, DH),
- every helper in `agents/shared/file_utils.py` and the
  per-agent `*_tool.py` modules,
- the `Orchestrator`, which already receives the Session — pass
  it to each chain agent at construction time and resolve paths
  from `session.<x>_dir or config.<X>_DIR` (the `or` keeps the v4
  REPL working when the path fields are None).

**Why deferred to Stage B.** Stage B is when sessions persist to
Postgres, which means real `user_id` / `session_id` identity flows
through the system anyway.  Plumbing per-session disk paths is a
free side-effect of that work.  Doing it in Stage A would touch
~every agent for an MVP that explicitly accepts single-user
operation.

**Mitigation in Stage A.** Document the limit on the invite-code
login screen if user-visible wording is needed, and operationally:
share the URL with one user at a time during the thesis demos.

**Status.** Open.  Resolved when Stage B's per-session path
plumbing lands; remove this entry and W13 together at that point.

### O10. Stage A: "End Session" only — no Save button until Stage B

**Where.** The Stage A web UI (`web_app.py` + `web/app.js`).

> **Partly superseded (2026-08-21).**  This entry says *"Nothing is persisted
> (no DB in Stage A)"*.  That is no longer true: `/api/end` calls
> `hub.database_handler.populate_database(...)`, so ending a session DOES run
> the DH save flow (opt-in by default — see `warnings_developer.md` W8).  What
> remains genuinely open is the UX question below: whether an explicit
> **Save** / **Discard** pair should replace or join the single "End Session"
> control.  Re-scope or close this entry when that is decided.

**What.** The Stage A app exposes exactly one end-of-conversation
control, labelled **"End Session"**, which clears
`st.session_state` and reloads with a fresh Session.  Nothing is
persisted (no DB in Stage A).

**Required behaviour for Stage B.** Add a true **"Save"** button
that triggers the Database Handler save flow and persists the
Session into Postgres.  Open UX questions for that future button:

- Should "End Session" remain alongside "Save" as the explicit
  "discard, don't save" path, or be replaced by a Save / Discard
  pair?
- Should Save show a pre-save preview (number of attempts, agent
  step counts, expected DH LLM cost) before confirming?  This is
  the same UX question O5 raises for the v4 REPL's save prompt —
  resolve once for both surfaces.
- On the unhandled-exception / browser-close paths, should
  anything be written?  Stage A says no (consistent with W8 in
  the v4 REPL).  Stage B should keep that default unless the user
  explicitly opts in.
- Per-agent skip ("save UII + Planner only") — same shape as O5,
  defer until the basic Save button is shipped.

**Status.** Open, blocked on Stage B (DB save flow).  Until Stage
B lands, the Stage A label discipline in `warnings_developer.md`
W14 applies: do NOT add a "Save" button to the Stage A UI even
as a placeholder.

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

### OPS2. Validate the Database Handler on the cloud deployment

**What.** The Database Handler (`agents/database_handler/`) was
built and locally validated as part of the v5-era work but has
never been exercised end-to-end against the Railway-deployed
Stage A. Now that the cloud workflow is live (volume mount,
Rhino Compute on Azure, GitHub auto-deploy), the DH save flow
needs to be run on the cloud URL to confirm:

- The per-session `database/<session>/` tree is created on the
  Railway volume (`/app/previous_sessions/...`) and survives
  redeploys.
- The DH's ~16 LLM calls per save complete within the cloud
  request timeout window without tripping the
  `InMemoryRateLimiter` or provider 429s differently than
  locally.
- The `_run_one_conversation` flow handles the cloud-side agent
  state shapes correctly (no path assumptions baked against
  `LOGS_DIR` that only resolve locally).
- The dangling-tool_use sanitisation gap (O1) does not actually
  fire on a normal cloud session; if it does, escalate O1.

**Where.** Trigger an End Session save on
`https://stage-a-production.up.railway.app` after a real
multi-attempt design request, then inspect the Railway volume
contents via the runbook §4 commands.

**Status.** Open. Operational validation; no code change
expected unless a cloud-only failure shows up.

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

### F5. LOG and Status view: colorise the log and refine its look

**Where.** `web/app.js`, `web/style.css` (LOG and Status view, log
pane — the `<pre>` / line container that tails the per-session
log file via the `/api/log/stream` SSE endpoint).

**What.** v1 of the LOG and Status view renders the live log
tail as plain monospace text — every line the same colour, no
visual grouping. Hard to skim for errors, agent boundaries, or
tool-call markers.

**What to build.**
- Colour-code by log level: ERROR / WARNING / INFO / DEBUG with
  distinct foreground colours (and maybe a red left-border for
  ERROR lines).
- Colour-code by agent name when the line is prefixed with one
  (`[Orchestrator]`, `[Planner]`, etc.) — pick a stable hue per
  agent so the eye groups them.
- Bold or background-tint lines that start a new turn / tool
  call / agent handoff, so the pane reads as a sequence of
  "blocks" rather than a wall of text.
- Refine spacing, font-size, and the empty-state placeholder so
  the pane looks at home next to the flowchart rather than like
  a debug dump.

**Why deferred.** v1 prioritises the structural pieces (SSE
endpoint, live tail, flowchart highlighting). Visual polish is
worth doing once the data flow is proven and the user has lived
with the unfiltered stream long enough to know which line types
matter most.

**Status.** Open. Pick up after the LOG and Status view has had
real use.

### F6. LOG and Status view: show tool-call payloads on the flowchart

**Where.** `web/app.js` (the LOG and Status view's SVG
flowchart) and the backend agent-activity events published via
`agents/shared/viz_bus.py`.

**What.** v1 of the flowchart only highlights the active agent
box with a yellow frame. The viewer cannot tell, from the chart
alone, WHAT the active agent is doing — only that it is busy.

**What to build.**
- Extend the `agent_active` SSE event to carry an optional
  payload summary: the inbound prompt (first ~100 chars), the
  tool being called (for Tool Caller), the tool's arguments
  (truncated), and on completion the outcome / error / result
  shape.
- In the SVG view, attach a small floating panel or tooltip
  next to each box that, when the user hovers (or always for
  the currently-active box), shows the most recent payload
  associated with that agent.
- For Tool Caller specifically: show which TOOL box is active
  (`Propeller Configurator` vs `Visual Renderings generator`)
  by highlighting the right downstream orange box AND surfacing
  the call arguments inline.

**Why deferred.** Payload routing adds non-trivial schema
considerations (truncation, secrets, multi-line formatting) and
the SVG layout work for the panels is non-trivial. The yellow
frame is enough for "what's the system doing right now?" until
the user wants to debug WHY without leaving the LOG and Status
view.

**Status.** Open. Pairs with F5 — both are LOG and Status view
polish that should be sequenced after first real use.

### F8. Split tools into generic vs DC-specific and consolidate under `tools/`

**Where.** Across the codebase:
- `tools/` currently mixes DC-specific tools
  (`generate_mesh/`, `render_mesh/`) with generic helpers
  (`calculate/`, `visualize_model/`).
- Generic helpers are also scattered under `agents/shared/`
  (`attempts_tool.py`, `user_inputs_tool.py`, `history_tool.py`) and
  inside each agent's own file as `@tool` stubs whose actual logic
  lives in `_handle_*` class methods (UII, DCIC, DCII, Tool Caller,
  DCOI all do this).

**What.** Reorganise so the distinction between **DC tools**
(designer-of-this-DC business logic — Propeller Configurator,
Visual Renderings Generator) and **generic helpers** (read files,
list attempts, calculate, visualise model, read agent history) is
explicit in the directory layout.  Suggested target:

```
tools/
  dc/
    generate_mesh/
    render_mesh/                 # both backends
  generic/
    attempts_tool.py
    user_inputs_tool.py
    history_tool.py
    calculate/
    visualize_model/
    read_extracted_inputs.py     # moved out of planner / DCIC / DCII
    read_user_queries.py         # moved out of planner
    read_parameters.py           # moved out of DCII / Tool Caller
    write_extraction.py          # moved out of UII
    write_parameters.py          # moved out of DCIC
    load_render_images.py        # moved out of DCOI
```

**Why deferred.** Touches every agent's imports and would conflict
with active feature work.  Best done as one focused commit when
no other tool-related changes are in flight.

**Why this matters.** The LOG and Status flowchart's generic-tool
labelling (the `@generic_tool("…")` decorator from
`agents/shared/agent_activity.py`) currently has to instrument both
stub `@tool` decorators AND the per-agent `_handle_*` methods that
do the real work, because the stubs return ``""`` and the agent
loops call the handlers directly, bypassing langchain's tool
dispatch.  Once generic helpers live under `tools/generic/` with
the real logic in the tool function body, the decorator can be
applied once at the `@tool` site instead of duplicated on each
agent's handler method — far less surface area to maintain.

**Status.** Open.  Pairs with F5 / F6 (LOG and Status view
polish) — sequence after these settle.

### F12. Verify the Context Pruner works as intended

**Where.**
- Pre-invoke hook: ``agents/shared/base_chain_agent.py``
  (``prune_history_if_needed``, ``_safe_cut_point``,
  ``_serialise_messages``).
- Pruner agent: ``agents/shared/context_pruner.py``.
- Per-agent call sites: one line at the top of each
  ``for _ in range(MAX_X_STEPS):`` loop in the 8 chain agents
  (Receptionist, Orchestrator, UII, Planner, DCIC, DCII, DCOI,
  Tool Caller).
- Settings: ``workflow_settings/settings.py``
  (``CONTEXT_PRUNER_ENABLED``,
  ``CONTEXT_PRUNER_THRESHOLD_TOKENS``,
  ``CONTEXT_PRUNER_KEEP_LAST_MESSAGES``).
- Live observability: the ``Context Pruner`` entry in
  ``TOOL_NAMES`` in ``web/app.js`` and the EXTRA AGENTS panel
  box in ``web/index.html``.

**What.**  The CP machinery landed end-to-end but has not yet been
validated against a real, long, multi-attempt session.  Need a
proper verification pass — both unit tests on the pure helpers
and an integration smoke that pushes a real chain agent past
the threshold and confirms the prune fires, succeeds, and leaves
the agent in a usable state.

**What "works properly" means — concrete checklist.**

1. *Token count accuracy.*  ``count_tokens`` over
   ``_serialise_messages(self.messages)`` is a reasonable proxy
   for what the provider sees.  Drift between this estimate and
   the real provider-side count should be small enough that the
   ``CONTEXT_PRUNER_THRESHOLD_TOKENS`` default (80k) still leaves
   ~30-50k headroom for the next-hop reply on any of the three
   providers we wire.
2. *No-op when under threshold.*  Sessions that never exceed the
   threshold behave identically to the pre-v9 baseline — same
   message order, no extra LLM calls, no log lines, no flowchart
   events.  Verify by running a single-turn / single-attempt
   session and diffing the log against a pre-v9 reference.
3. *Cut point preserves tool-call pairing.*  ``_safe_cut_point``
   must never leave an ``AIMessage(tool_calls=...)`` in the
   prefix while its matching ``ToolMessage`` (same
   ``tool_call_id``) stays in the kept tail.  Unit-test against
   hand-crafted histories that intentionally place a tool-call /
   tool-message boundary at the ``len - KEEP_LAST_MESSAGES``
   index, with one, two, and three tool calls per AIMessage.
4. *Image content blocks survive the prune in summary form.*
   Image bytes are replaced by ``[image: redacted for pruning]``
   in the prefix so they don't waste tokens on encoded data, but
   the Pruner's system prompt should still surface
   "what the agent saw" in the summary — verify by running a
   3-attempt session with reference images and reading the
   resulting summary SystemMessage at the next invoke.
5. *Summary SystemMessage shape is provider-compatible.*  The
   resulting ``[SystemMessage(summary), ...tail]`` pattern works
   on all three providers we wire — Anthropic concatenates
   adjacent SystemMessages into a single system field; OpenAI
   keeps them separate; Google concatenates.  Smoke-test once
   per provider with ``LLM_ROUTING_MODE`` set to each.
6. *Settings re-read at next session.*  Edits to the three
   ``CONTEXT_PRUNER_*`` settings via Workflow Settings take
   effect on End Session → next session (the same reload path
   the rest of ``workflow_settings/settings.py`` uses).  Verify
   by flipping ``CONTEXT_PRUNER_ENABLED`` mid-process.
7. *Failure modes are non-fatal.*  Token count error, pruner
   LLM error, empty pruner output, viz_bus publish error — each
   logs a warning and leaves ``self.messages`` untouched.
   Verify by monkey-patching ``count_tokens`` / ``pruner.run``
   to raise.
8. *Observability events fire correctly.*  Each successful prune
   publishes ``agent_active(<agent>, "Context Pruner")`` on entry
   and ``agent_active("Context Pruner", <agent>)`` on exit; the
   exit event fires even on the error paths so the chart never
   leaves CP highlighted forever.
9. *Database Handler is NOT pruned.*  Confirm the DH does not
   call ``self.prune_history_if_needed()`` — its
   ``populate_database`` loop sees the full accumulated
   conversation per field.
10. *System prompt is untouched.*  After a prune,
    ``self.system_prompt`` is bit-for-bit identical to the
    construction-time value, and the next invoke prepends
    ``make_system_message(self.system_prompt, self.provider)``
    fresh — confirm with a simple before/after equality check.

**Suggested test layout.**

- ``extra_utilities/smoke_test_context_pruner.py`` (new) — exercises
  the pure helpers (``_safe_cut_point`` boundary cases,
  ``_serialise_messages`` round-trip including image blocks,
  ``prune_history_if_needed`` no-op paths, and the failure
  modes) without standing up a Session or invoking a real LLM.
  Mocks ``pruner.run`` to return a fixed summary string.  Should
  be runnable inside the Docker container the same way
  ``smoke_test_llm_routing.py`` is.
- A manual run: take the v7 case that hit 894k tokens (3-attempt
  design request with one reference image attached) and confirm
  (a) it no longer raises ``OpenAIContextOverflowError`` and
  (b) the CP box lights up in the LOG-and-Status view at the
  right moments.

**Why deferred.**  The machinery landed in v9.  Verification is
specifically called out as a follow-up so we get systematic
coverage (every chain agent, every failure mode) instead of
finding bugs only when a real session crashes.

**Status.** Open.  Pairs with F7 (implementation).

### F13. Remove the Railway persistent volume once R2 mirror is verified

**Where.**
- Railway dashboard → `stage-a` service → **Settings** → **Volumes**
  (currently has one volume mounted at ``/app/previous_sessions/``,
  set up in v7 / v8).
- ``agents/loader.py:_archive_previous_session`` — the local sweep
  that moves ``logs/`` / ``attempts/`` / ``inputs/`` /
  ``database/`` into ``previous_sessions/<session_id>/`` at End
  Session.
- ``agents/shared/r2_uploader.py`` — the R2 path the DH save now
  takes; currently uploads ONLY ``.txt`` files under
  ``database/<session_id>/`` (sidecar ``.meta.json`` excluded by
  the suffix filter, plus everything under ``logs/`` /
  ``attempts/`` / ``inputs/``).
- ``docker-compose.yml`` (local dev) — already has the volume
  block.  Same decision applies locally if the developer wants
  to retire the host-side ``previous_sessions/`` directory.

**What.**  As of v9 the DH database (the post-session ``.txt``
files the future RAG layer cares about) is mirrored to a
Cloudflare R2 bucket.  The Railway-mounted volume at
``/app/previous_sessions/`` is therefore **redundant for the
database side** and can be deleted once R2 is verified to be
working in production for a few real sessions.

**Why it matters.**  The Railway volume isn't free — every GB-
month is billed by Railway, and ``previous_sessions/`` only
grows.  R2 storage is materially cheaper per GB and has zero
egress fees, so the same data costs less to keep there.

**Prerequisite: decide on the NON-database artefacts.**
``previous_sessions/<session_id>/`` carries FOUR things:

1. ``database/<agent>/<field>.txt`` — DH-saved answers.
   **Already mirrored to R2** as of v9 ⇒ safe.
2. ``logs/web_<session_id>.log`` — full session log (every
   ``[AGENT MSG]``, every tool call, the full DH transcript).
   Critical for debugging.  **NOT yet mirrored to R2.**
3. ``attempts/<attempt_id>/`` — ``parameters.json``,
   ``propeller_mesh.obj``, render PNGs.  Used by the
   Receptionist's attempt-selection logic AND by the future
   "Copy parameters list" backend (F9).  **NOT yet mirrored.**
4. ``inputs/`` — user-query text + reference images.  Useful
   for replaying a session.  **NOT yet mirrored.**

If the volume is removed without first mirroring (2)/(3)/(4),
the system LOSES those artefacts on End Session.  Three
acceptable paths:

* **(a) Mirror everything to R2 before removing.**  Extend
  ``r2_uploader.upload_directory`` calls in the End Session
  path (``web_app.py:_end_session`` / ``agents/loader.py:_end_
  session``) to push the whole ``previous_sessions/<id>/``
  tree, not just the DH database.  Drop the suffix filter.
* **(b) Accept losing the non-database artefacts.**  Only the
  DH database survives; sessions become un-replayable.  Smallest
  code change, biggest information loss.
* **(c) Keep the volume but shrink it to only ``logs/`` /
  ``attempts/`` / ``inputs/``.**  Move the local
  ``database/<id>/`` write target out of the volume so the
  cost-savings come from the DH database (the bulk of the
  growth).  Compromise.

Recommendation: **(a)**, scoped to extending the existing
``upload_directory`` call.  It's a few lines and removes the
ongoing Railway cost entirely.

**Verification gate before doing this.**

1. Run at least 5 real End Session → Save flows on Railway.
2. For each, confirm every expected ``.txt`` lands in R2
   under ``prod/<session_id>/<agent>/<field>.txt`` (Cloudflare
   dashboard or ``aws s3 ls`` against the R2 endpoint).
3. Confirm no ``[R2]`` warnings in any Railway log.
4. Smoke-test reading at least one ``.txt`` back from R2 (so
   we know the upload truly succeeded and the file is readable,
   not just present-but-corrupt).
5. Only after the above passes consistently: implement (a) (or
   accept (b)/(c)), then detach + delete the Railway volume in
   the dashboard.

**Cost-saving rough order.**  Railway volume cost dominates
for sessions with mesh artefacts (one ``.3dm`` mesh + three
PNGs per attempt ≈ several MB; multiplied across attempts and
sessions, the volume grows fast).  R2 with zero egress and
~$0.015 / GB-month materially undercuts Railway volume pricing
for the same data.

**Status.** Open.  Blocked on F13's own prerequisites — do
NOT delete the volume until (a)/(b)/(c) is chosen and the
five-session verification above is clean.

### F14. Verify the new identifying-attempt force-tool flow on Railway

**Where.**
- ``agents/database_handler/database_handler.py`` —
  ``_run_identifying_conversation`` + ``_run_force_tool_phase``.
- ``agents/database_handler/dh_tools.py`` — the
  ``save_attempt_data`` langchain tool.
- ``agents/shared/r2_uploader.py`` —
  ``upload_attempt_artefacts``.
- Railway service ``stage-a`` — Variables tab + live container.

**What.**  The v9 force-tool flow for identifying attempt-specific
questions (see README §"Identifying attempt-specific questions —
force-tool flow") was verified locally via Docker.  Run the same
flow on Railway to confirm:

1. The container can call ``self.llm.bind_tools(...,
   tool_choice="save_attempt_data")`` against whichever
   provider Railway is configured with.  Each provider has a
   slightly different tool_choice payload shape; langchain
   abstracts them but it's worth a live check per provider you
   intend to support in production.
2. The DH actually emits a tool call on the force-tool turn (the
   provider-side tool-choice forcing works as expected).
3. The retry loop fires correctly when the DH passes an
   unparseable input or a number that resolves to no folder.
4. ``upload_attempt_artefacts`` uploads the four whitelisted
   files (``parameters.json``, ``propeller_mesh.obj``,
   ``render_*.png``, ``description.txt``) to the live R2 bucket
   under ``<prefix>/<session_id>/attempts/<NNN>/<session_id>__<NNN>__<original>``.
5. ``propeller_mesh_components.obj`` is NOT uploaded (whitelist
   exclusion holds).
6. On ``"none"`` or 3-retry exhaustion, the parent row's
   ``.txt`` is NOT written AND every Q(N).x sub-row is silently
   skipped (no placeholders).
7. The .txt of a successful identifying row carries the
   ``--- Session ID ---`` and ``--- Attempt ID ---`` headers
   with the correct values.

**How.**  Author a schedule with at least one identifying
attempt-specific row + at least one Q(N).x sub-row, ideally
covering both the success and the explicit-``"none"`` paths.
Run an End Session → Save on the live deploy, then inspect:
* Cloudflare R2 dashboard: ``prod/<session_id>/attempts/<NNN>/``
  should contain the renamed files.
* Railway logs: ``[DH]  force-tool attempt k SUCCEEDED`` /
  ``[R2]  attempt-artefact upload: N uploaded, M missing``
  lines should appear.
* Local mount or ``docker compose exec``: ``previous_sessions/
  <session_id>/database/`` should match the R2 contents (modulo
  the file renames).

**Why deferred.**  The flow is functioning locally.  Railway-side
verification depends on the v9 push having reached the
``stage-a-web-deploy`` branch and at least one real save flowing
through the deployed container.

**Status.** Open.  Pairs with F13 (volume removal) — F13's
"5-session verification" gate should cover most of F14's
checklist if the identifying-Q rows are part of those test
sessions.

### F15. Tighten DH response handling — safety net + slightly stricter prompt

**Where.**
- ``agents/database_handler/database_handler.py`` —
  ``_decide_next`` (DH ASK/SAVE), ``_enforce_semantic_cap_pair``
  (compression), ``_run_force_tool_phase`` (tool-call parsing).
- ``agents/database_handler/prompt.md`` — system prompt.
- ``agents/database_handler/database_handler.py`` —
  ``_parse_dh_decision`` / ``_parse_save_body_semantic`` /
  ``_clean_semantic_body``.

**What.**  Add a defensive *response check* the system runs on
every DH reply before accepting it, AND tighten the prompt by a
small amount to make malformed replies less likely in the first
place.

The current DH path already does some checking:
* ``_parse_dh_decision`` rejects responses missing the
  ``ASK:`` / ``SAVE:`` prefix.
* ``_parse_save_body_semantic`` rejects SAVE bodies missing
  ``QUESTION:`` / ``ANSWER:`` headers.
* ``_clean_semantic_body`` strips routing-tool JSON wrappers,
  literal ``\n`` escapes, file paths, attempt-folder slugs,
  chain-narration leads.

What's missing — the "safety net" — is a tighter post-parse
audit that flags responses for re-prompting BEFORE they're
accepted, rather than passing through with a warning.  Concrete
checklist for what the audit should reject:

1. ``SAVE:`` body present but the saved ``ANSWER`` is suspiciously
   short (e.g. < N tokens) for a SEMANTIC field — usually means
   the DH echoed a fragment instead of the cleaned answer.
2. Saved ``QUESTION`` exceeds the recommended soft cap
   (~80 cl100k_base tokens) — re-prompt for a tighter version.
3. ``SAVE:`` body still contains any of the forbidden artefacts
   AFTER ``_clean_semantic_body`` ran (i.e. the regex helpers
   missed something) — usually a sign of a new failure mode
   worth surfacing.
4. The DH's response on a force-tool turn is anything other
   than a single tool call — currently logged as a warning, but
   should also bump the retry counter explicitly so the
   "3-retries-then-none" budget is enforced.
5. For QUANTITATIVE fields: confirm the saved body contains at
   least one number / parameter marker.  An all-prose answer is
   a sign of the DH wandering off.

The prompt update should be **slightly stricter, not longer**.
The goal is to remove ambiguity, not add new sections.  Examples
of "stricter without longer":
* Replace soft "should" / "prefer" with hard "MUST" / "MUST
  NOT" wherever the system-side check is actually enforced.
* Move format requirements (``ASK:``/``SAVE:`` prefix, the
  ``QUESTION:``/``ANSWER:`` headers, the per-Q token budget)
  closer to the per-turn instructions instead of one general
  section the model may skim past.
* Add a single sentence at the top of the prompt naming the
  consequence of a malformed response: "*The system will
  reject and re-prompt on any reply that does not exactly
  match the protocol below — burning retry budget.*"

**Why it matters.**  The DH is the most failure-tolerant agent
in the pipeline today (it gets several retries by design), but
the consequences of a silent acceptance are larger than for any
chain agent: a malformed SAVE: lands in the database as
embedding-noise that the future RAG layer can't filter.  An
audit step that re-prompts is much cheaper than the downstream
fix.

**Why deferred.**  v9 ships the force-tool path AND the existing
defensive helpers (``_clean_semantic_body`` etc.).  The audit
step is a follow-up; do it once real saves are flowing on
Railway (F14) so we have actual misbehaviour examples to write
the audit rules against, rather than guessing.

**Status.** Open.  Pairs with F12 (CP verification) and F14
(Railway identifying-Q verification) — all three are
"verify-the-DH-works" tasks.

### F16. Verify the multi-answer split + multi-attempt identifying-Q flow

**Where.**
- ``agents/database_handler/database_handler.py`` —
  ``_parse_save_body_semantic`` (multi-pair + ``ATTEMPT:`` header
  parser); ``_enforce_semantic_cap_pairs`` (per-pair cap with
  retry); ``_run_one_conversation`` /
  ``_run_identifying_conversation`` (both return triple-lists now);
  ``_run_force_tool_phase`` (``attempt_ids: list[str]`` API);
  ``populate_database`` (attempt-major sub-row loop).
- ``agents/database_handler/dh_tools.py`` — tool signature.
- ``agents/shared/r2_uploader.py`` —
  ``upload_attempt_artefacts`` (called per attempt).
- ``agents/database_handler/prompt.md`` — multi-pair + multi-
  attempt rules.

**What.**  The v9 force-tool flow grew two orthogonal extensions:

1. **Multi-answer split** (Extension A) — when one agent's reply
   covers N distinct items the DH may emit N
   ``QUESTION:``/``ANSWER:`` pairs in a single SAVE; each pair
   becomes its own ``.txt`` file (single-underscore + index
   suffix when N≥2).
2. **Multi-attempt identifying Q** (Extension B) — the
   ``save_attempt_data`` tool now accepts a LIST of attempt
   ids.  When the list has N≥2 entries, the identifying Q's
   answer is split per attempt (one ``ATTEMPT:``/``QUESTION:``/
   ``ANSWER:`` block per attempt → one ``__<NNN>.txt`` per
   attempt) AND the system runs every Q(N).x sub-row interview
   N times (attempt-major: all sub-rows for attempt 1 first,
   then for attempt 2, and so on).  Each attempt's artefacts
   land in its own ``<prefix>/<session_id>/attempts/<NNN>/``
   folder.

Both landed in v9.x and were unit-smoked locally (parser shape +
filename rules), but neither has been exercised against a real
multi-attempt session end-to-end.  Need a proper verification.

**What "works properly" means — concrete checklist.**

1. *Multi-answer parse robustness.*  The parser correctly
   splits N back-to-back ``QUESTION:``/``ANSWER:`` blocks in one
   SAVE body — at N=1, N=2, N=3, with multi-line answers, with
   stray blank lines between pairs, and with mixed casing
   (``Question:`` / ``ANSWER:``).
2. *ATTEMPT-tag parse robustness.*  ``ATTEMPT: 002`` /
   ``ATTEMPT: attempt 002`` / ``ATTEMPT: 20260530_142312_002_xxx``
   all yield the same 3-digit ``"002"`` after
   ``_normalise_attempt_input``.  Pairs missing an ATTEMPT tag
   are tolerated and surface as ``None`` in the triple, not
   dropped.
3. *Per-pair cap enforcement.*  Each pair's
   ``count_tokens(Q) + count_tokens(A)`` is checked against
   ``EMBEDDING_MAX_RESPONSE_TOKENS`` independently.  The
   one-shot retry asks the DH to shorten WHICHEVER pair(s) are
   over cap, and the merger keeps the shorter of (new, old)
   per index when the retry only partially worked.
4. *Filename matrix.*  Confirm at write time:
   - single → ``<field>.txt``
   - multi-answer (item 2) → ``<field>_2.txt``
   - sub-row attempt 002 → ``<field>__002.txt``
   - sub-row 002 + multi-answer (item 1) →
     ``<field>__002_1.txt``
5. *Force-tool list parsing.*  ``attempt_ids=["002"]`` /
   ``["002", "005", "007"]`` / ``[]`` / ``["none"]`` /
   ``["002", "garbage"]`` all behave per spec
   (single-success / multi-success / drop / drop / retry).
6. *R2 upload fan-out.*  ``upload_attempt_artefacts`` is called
   ONCE per resolved attempt; each call lands the whitelisted
   files under ``<prefix>/<session_id>/attempts/<NNN>/`` with
   the rename pattern.  No cross-attempt collisions.
7. *Attempt-major sub-row order.*  In a multi-attempt block
   ``[Q(N), Q(N).1, Q(N).2]`` with two resolved attempts (``002``
   and ``005``), the system writes in the order:
   ``Q(N)__002.txt``, ``Q(N)__005.txt``,
   then ``Q(N).1__002.txt``, ``Q(N).2__002.txt``,
   then ``Q(N).1__005.txt``, ``Q(N).2__005.txt``.
   Verify by inspecting the ``[DH]  wrote sub-row …`` log lines.
8. *Cascade drop on empty / max-retries.*  When the force-tool
   ends with no resolved attempts, NEITHER the parent's ``.txt``
   NOR any Q(N).x sub-row file is written.  No placeholders.
   No R2 keys.
9. *Cap on QUANT fields unchanged.*  QUANT rows still emit a
   single verbatim block (the multi-pair / ATTEMPT path is
   SEMANTIC-only).
10. *Provider compatibility for the list-based tool.*  Confirm
    every provider we wire (OpenAI / Anthropic / Google) accepts
    the ``attempt_ids: list[str]`` schema via langchain's
    ``bind_tools(tool_choice="save_attempt_data")``.  The
    list parameter shape is not exotic, but the per-provider
    json-mode handling sometimes coerces single-element lists
    to scalars — the parsing code already handles that, but the
    behaviour should be verified live per provider.

**Suggested test layout.**

- ``extra_utilities/smoke_test_dh_multi.py`` (new) — pure-helper
  tests for ``_parse_save_body_semantic`` (the 5 shapes above),
  ``_normalise_attempt_input`` edge cases, ``_safe_cut_point``
  if not already covered, and ``_resolve_attempt_folder`` with
  multi-match.  Runnable inside the container the same way the
  R2 + LLM-routing smokes are.
- A manual session: configure two identifying attempt-specific
  rows — one likely to resolve to N=1 (best attempt), one
  likely to resolve to N≥2 (non-satisfactory attempts).  Add
  two sub-rows under each.  Run a 3-attempt session.  Verify
  the per-attempt R2 subtree, the ``[DH]  wrote …`` ordering,
  and the cascade-drop case (force the DH to ``"none"`` by
  asking a question whose answer the agent can't anchor to a
  specific attempt).

**Why deferred.**  Both extensions landed in v9.x; verification
is a follow-up so we exercise the per-attempt fan-out and the
multi-answer split against real LLM behaviour rather than
synthetic SAVE bodies.

**Status.** Open.  Pairs with F14 (Railway identifying-Q
verification) and F15 (DH response safety net) — same
"verify-the-DH-works" cluster.

### F17. Scrap empty / "nothing to specify" DH answers instead of saving canonical negation sentences

**Where.**
- ``agents/database_handler/prompt.md`` — the "Negation-canonical"
  rewrite rule (rule 9 of the rewrite-rules section currently says
  to save a short canonical "No problem occurred this session"
  sentence; this needs reversing for empty content).
- ``agents/database_handler/database_handler.py`` — the SAVE
  protocol parser (``_parse_dh_decision`` /
  ``_parse_save_body_semantic``); ``populate_database``'s per-row
  write path (currently always writes a ``.txt`` for non-DCII-
  gated rows).
- Sidecar ``.meta.json`` writer.

**What.**  When the agent's answer to the DH is essentially
"nothing of this kind happened" / "there is nothing to specify"
(a negation-canonical or empty-content reply), the DH should
NOT save a ``.txt`` file for that (agent, field) at all.  Drop
the row entirely — same cascade as when an identifying
attempt-specific question fails to resolve an attempt id, just
scoped to one row instead of a whole block.

Currently the DH prompt RULE 9 instructs the opposite: "do not
leave the body empty, ambiguous, or filled with hedges — save a
canonical short sentence such as ``No problem occurred during
this session for the User Input Inspector.``".  That rule was
right when the goal was a uniform per-session folder layout; the
v9.x RAG layer benefits more from a sparse layout (every saved
``.txt`` actually carries information worth embedding).

**Proposal sketch.**

1. **New SAVE-body verb (or extend SAVE).**  Two options:

   * **(a) New prefix ``SKIP:``.**  The DH emits ``SKIP: <one-line
     rationale>`` instead of ``SAVE:`` when there's nothing
     embedding-worthy.  ``_parse_dh_decision`` learns the new
     verb; ``populate_database`` writes nothing for that row.
     The Part-2 message is logged for the DH trace; no ``.txt``
     or ``.meta.json`` lands on disk.
   * **(b) Reserved SAVE body sentinel.**  ``SAVE: <NO_CONTENT>``
     (or similar) tells the system to skip.  Simpler protocol
     (no new verb) but easier to misfire on a real answer that
     happens to start with the sentinel.

   I lean toward (a) — explicit verbs are easier for the model
   to remember and easier for the system to validate.

2. **Prompt updates.**  Replace rule 9 with: "When the agent's
   answer says nothing of the kind happened this session (no
   problem to describe, no clarification was needed, no decision
   was made), emit ``SKIP:`` instead of ``SAVE:``.  Do NOT
   fabricate a canonical sentence to fill the file.  The system
   will drop the row from the saved database."  Cross-reference
   the new rule from the per-field protocol section.

3. **Identifying attempt-specific Q interaction.**  ``SKIP:`` is
   ALSO the natural verb for "no attempt to identify" — today
   the force-tool's ``["none"]`` path achieves the same cascade
   drop for the whole block.  Leave the force-tool behaviour
   alone; ``SKIP:`` is only for the SAVE turn that follows a
   resolved cycle (session-scoped row, sub-row, or identifying
   Q where the cycle ran but the agent's content is empty).

4. **Sidecar layout.**  Today every ``.txt`` carries a sibling
   ``.meta.json``.  When ``SKIP:`` fires, neither is written —
   the future RAG layer detects "no entry" by file absence, the
   same way it would for a DCII-gated DCII row when DCII is off.

5. **Logging.**  The DH log records the ``SKIP:`` rationale so a
   reviewer can see WHY a row was dropped; only the disk write
   is suppressed.

**Why deferred.**  Touches the DH protocol shape (a new verb),
the parser, the per-row write path, and the prompt.  Worth
batching with F15 (DH response safety net) since both change the
DH's response handling and both benefit from real-session
examples to calibrate against.

**Status.** **LARGELY ADDRESSED 2026-08-04** by the batching work's
SKIP path.  `submit_batch` now has a `skips` list, and the DH's prompt
tells it to skip rather than save a negation ("nothing went wrong" is a
skip; "nothing went wrong BECAUSE the extraction pinned the ambiguity
early" is worth saving).  A skipped row writes its `.txt` with a
`SKIPPED` marker — so the per-session folder stays complete and
auditable — and writes **no `chunks` row**, which is the half that
matters: the negation never gets embedded and so never competes with
real content at search time.

What remains open is the RETROSPECTIVE half: sessions already saved
still carry canonical negation sentences in `chunks`, and nothing
sweeps them.  Also unaddressed: an agent that answers with a negation
where the DH nevertheless judges it worth saving is not second-guessed
— by design, but it means the corpus quality now depends on the DH's
judgement rather than on a filter.  Still pairs with F15.

### F18. UII / Receptionist: don't treat session-level numeric requests as design parameters

**Where.**
- ``agents/user_input_inspector/prompt.md`` — extraction logic;
  the rules that decide which user-stated numbers become
  ``QUANTITATIVE INPUTS`` entries vs ``DESIGN INTENT`` /
  session-level metadata.
- ``agents/receptionist/prompt.md`` — disambiguation logic when
  the Receptionist annotates the user's raw text before
  forwarding (the annotation lines starting with
  ``[Receptionist clarification: ...]``).
- Possibly ``agents/planner/prompt.md`` — the Planner reads the
  extraction and may also need to recognise a session-level cap
  vs a parameter value.

**What.**  When the user's prompt contains a number that is
OBVIOUSLY a session-level instruction — typically "give me 3
designs", "try 3 different attempts", "produce 5 variations" —
that number is NOT a design parameter (e.g. it is NOT
``bladeCount=3``).  It is a count of design CYCLES the user wants
the system to perform within this session.

The UII currently risks pattern-matching any user-stated integer
to one of the configurator's integer parameters
(``bladeCount``, ``innerMaxPos``, ``outerMaxPos`` — the only
integer-typed entries in the 17-param schema).  A user asking for
"3 attempts" should not silently end up with ``bladeCount=3`` in
``QUANTITATIVE INPUTS``.

**Proposal sketch.**

1. **UII prompt — explicit session-vs-parameter rule.**  Add a
   short paragraph to the extraction rules: "Numbers attached to
   phrases describing session structure — 'N designs', 'N
   attempts', 'N variations', 'N different versions', 'try N
   <something>' — are SESSION-LEVEL counts.  They belong in
   ``DESIGN INTENT`` (or a new ``SESSION CONSTRAINTS`` section
   if you keep the prompt strict), NEVER in ``QUANTITATIVE
   INPUTS`` as a parameter value.  When in doubt about whether a
   number is a parameter or a session count, prefer DESIGN
   INTENT and add a one-line note explaining the ambiguity."
2. **Receptionist annotation rule.**  When the Receptionist
   disambiguates the user's text (the ``[Receptionist
   clarification: ...]`` lines appended to ``user_query.txt``),
   it should call out session-level counts explicitly so the UII
   sees them tagged: e.g. ``[Receptionist clarification: 'three
   designs' is a session-level request for 3 design cycles, not
   a parameter value]``.
3. **Planner prompt — read the session count.**  The Planner
   already has visibility into the extraction; add a one-line
   rule that any ``SESSION CONSTRAINTS`` / count of cycles it
   sees there caps the number of recovery iterations it can
   plan without escalating to the user.
4. **Schema cross-reference.**  Add a short list at the top of
   the UII rules naming the legitimate integer-typed parameters
   (``bladeCount``, ``innerMaxPos``, ``outerMaxPos``) so the
   model has a quick reference for what an integer in the
   prompt could plausibly map to — anything else integer-shaped
   is most likely a session-level count.

**Why it matters.**  Misclassifying "3 designs" as
``bladeCount=3`` is a quietly destructive failure: the user
gets a 3-bladed propeller when they asked for three different
designs.  It is the kind of error the rest of the safety net
(DCII range checks, DCOI visual comparison) does not catch —
the parameter passes range checks, the mesh generates, the
visual matches the (misclassified) extraction.  The user only
notices when they look at the result.

**Why deferred.**  Prompt-only fix; needs careful wording so
the UII does not over-correct and ignore genuine parameter
numbers ("set ``bladeCount`` to 3").  Calibrate against a
small set of realistic user prompts before rolling out.

**Status.** Open.  Lightweight prompt change but worth a
focused test pass (a handful of user prompts that include
session-level integers + a handful that include legitimate
parameter integers) before landing.

### F19. De-duplicate attempt uploads within a session

**Where.**
- ``agents/database_handler/database_handler.py`` —
  ``populate_database`` (the parent ``while`` loop holding the
  ``attempt_ids_by_parent`` dict) and ``_run_force_tool_phase``
  (the upload site).
- ``agents/shared/r2_uploader.py`` —
  ``upload_attempt_artefacts``.

**What.**  When two identifying-Q rows in a single schedule
resolve to the SAME attempt id (e.g. "best attempt" → 002 and
"useful insights" → 002 because the same attempt was both
best AND informative), the force-tool's upload step runs once
per row.  Each run re-uploads the same artefact files to the
same R2 keys:

    PUT <prefix>/<sid>/attempts/002/<sid>__002__parameters.json     (row 1)
    PUT <prefix>/<sid>/attempts/002/<sid>__002__parameters.json     (row 2, identical bytes)
    ...

R2 PUTs are idempotent at the byte level (the second write
overwrites with identical content), so the bucket ends up in the
right state.  But each PUT consumes bandwidth and a Cloudflare
write-operations quota slot.  For a 3-attempt session with the
default schedule's three identifying-Q rows all pointing at
overlapping attempts, this can produce ~12 redundant PUTs per
save.

**Proposal sketch.**

1. Add a session-scoped ``set[str]`` of already-uploaded NNN's to
   ``populate_database``'s local state — e.g.
   ``uploaded_attempts: set[str] = set()``.
2. Pass it through to ``_run_force_tool_phase`` (new kwarg).
3. In the per-NNN upload loop, skip the upload when the NNN is
   already in the set; STILL push the same ``ok: true``
   ToolMessage to the DH so its conversation context is
   unchanged.
4. After a successful upload, ``add()`` the NNN to the set.

Net effect: per-attempt artefacts are uploaded AT MOST ONCE per
save, regardless of how many identifying-Q rows reference the
same attempt.

**Why deferred.**  Correctness is fine today (idempotent).  The
fix is a small contained change but introduces a piece of
session-scoped mutable state in ``populate_database`` and a new
kwarg-passing layer through ``_run_force_tool_phase``.  Worth
batching with any other DH save-path tightening (F15, F17, F20).

**Status.** Open.  Low priority unless R2 egress / quota
becomes a measurable cost.

### F20. Compensate orphan artefacts when the identifying conversation raises after a successful force-tool upload

**Where.**
- ``agents/database_handler/database_handler.py`` —
  ``_run_identifying_conversation`` (sequence: force-tool
  upload → DH decide loop → return); ``populate_database``'s
  ``try``/``except`` block around ``_run_identifying_conversation``.
- ``agents/shared/r2_uploader.py`` — possibly a new
  ``delete_attempt_artefacts(session_id, attempt_id)`` helper
  if path (a) below is chosen.

**What.**  Today's failure mode:

1. Force-tool resolves ``["002"]`` and uploads 002's artefacts
   to R2 successfully.
2. The DH's subsequent ASK/SAVE decide loop, or the SEMANTIC
   cleanup, or the cap-enforcement step raises.
3. ``populate_database``'s ``except`` clause sets
   ``resolved_attempt_ids = []`` and the cascade-drop branch
   fires — neither the parent ``.txt`` nor any sub-row file is
   written.

End state: R2 has ``<sid>/attempts/002/…`` files (5–6 of them) with
NO corresponding ``<sid>/<agent>/<field>.txt`` referencing them.
A future RAG retrieval layer that joins attempt artefacts
against the answer .txt files would see orphans.

Probability of this firing in a real session is LOW (the DH would
have to fail mid-conversation after the force-tool succeeded),
but the partial state is real and persistent (R2 doesn't garbage-
collect).

**Proposal sketch.**

Two acceptable compensations, pick one:

  * **(a) Delete on failure.**  When ``_run_identifying_conversation``
    raises after a successful force-tool, the system DELETES the
    just-uploaded artefacts.  Requires a new
    ``r2_uploader.delete_attempt_artefacts(session_id,
    attempt_id)`` helper that issues a ``DeleteObject`` call per
    whitelisted file under ``<sid>/attempts/<NNN>/``.  Most
    correct; restores the "all-or-nothing" cascade-drop invariant
    to the R2 side too.
  * **(b) Sentinel orphan marker.**  Same scenario, but instead of
    deleting, write a sentinel ``<sid>/attempts/<NNN>/_orphan.txt``
    file containing the failure reason and a timestamp.  The
    future RAG layer can detect & skip orphaned attempt folders.
    Safer (no delete on a possibly-still-useful file) but leaves
    junk in the bucket.

Recommendation: **(a)** — keep R2 clean.  The artefacts can
always be re-uploaded on a successful retry if the user runs the
same save again.

**Implementation sketch (option a).**

1. Track the per-row "what was uploaded" set inside the ``try``
   block.  ``populate_database`` already has
   ``attempt_ids_by_parent``; extend it (or a parallel dict) to
   hold a per-parent ``list[str]`` of NNN's that were uploaded
   during the force-tool phase.
2. On exception, before setting ``resolved_attempt_ids = []``,
   call ``r2_uploader.delete_attempt_artefacts(session_id, nnn)``
   for each NNN that was uploaded.
3. Log the cleanup so the orphan reason is auditable.

**Why deferred.**  Real but low-probability edge case.  Hard to
test without artificially injecting a failure into the DH's
decide loop — write a smoke test that monkey-patches
``_run_one_conversation`` to raise after the force-tool, then
asserts the R2 keys were deleted.

**Status.** Open.  Pairs with F19 (both reshape the per-session
R2 upload state-tracking).

### F21. Cache the boto3 client at module level

**Where.**  ``agents/shared/r2_uploader.py`` — the ``_client``
factory.

**What.**  Today ``_client()`` constructs a fresh
``boto3.client("s3", ...)`` on every call.  ``upload_file``
calls ``_client()`` per file; ``upload_directory`` iterates
files and calls ``upload_file`` per iteration.  A typical
DH save flow does 40–60 ``_client()`` calls (36 per-agent
.txt PUTs + ~4–12 attempt artefact PUTs + ~1–10 user-input
PUTs).

Each construction does some signing-config setup and endpoint
resolution — minor per-call cost (~milliseconds), but it also
prevents the underlying urllib3 connection pool from being
reused across PUTs, which DOES matter for many small writes.

**Proposal sketch.**

1. Add a module-level ``_CLIENT_CACHE: dict[tuple, BotoClient]``
   keyed by the four env-var values (account id / access key /
   secret hash / bucket).  Different env values → different
   client; same env → reuse.
2. ``_client()`` reads the cache and only constructs when the
   cache key is missing.
3. Invalidate the cache when env vars change between calls
   (rare in practice — Railway / Docker env is fixed for the
   process lifetime, but a unit test that swaps env vars mid-run
   would need this).

Net effect: ONE boto3 client across the entire save's worth of
PUTs, and the urllib3 connection pool is reused — fewer TCP
handshakes + TLS negotiations.

**Why deferred.**  Pure perf optimisation.  Correct today; just
not as fast as it could be.  Worth doing once R2 throughput
becomes a measurable bottleneck (or just folded in opportunistically
when next touching ``r2_uploader.py``).

**Status.** Open.  Low priority.

### F9. "Copy parameters list" should return the SELECTED attempt's parameters

**Where.** Backend endpoint `web_app.py:api_parameters()` (currently
serves `DC_prompt_fragments/dc_config/parameters.md`); frontend
handler in `web/app.js` (the `copy-parameters` button click).

**What.** Today the **Copy parameters list** button in the chat
viewer footer copies the canonical 17-parameter REFERENCE list
(names, units, ranges, descriptions) from `parameters.md`.  That
is the right content for "what parameters does this DC accept" —
a template / cheat-sheet — but it is NOT what the user almost
certainly wants once they have a generated propeller on screen:
they want the actual numerical values chosen for the propeller
currently being displayed in the viewer.

**Required behaviour.** When a mesh is shown in the 3D viewer,
`/api/parameters` should return the `parameters.json` from the
attempt folder that produced that mesh — specifically, the
attempt the Receptionist selected for visualisation this turn
(see `Receptionist.format_outgoing` in
`agents/receptionist/receptionist.py:271`, which already attaches
the chosen attempt's `parameters.json` to the user-facing
message).  Suggested shape: `{"text": "<json contents>", "attempt":
"<path>"}`.  When NO mesh is loaded yet, fall back to the
current behaviour (the canonical reference list) so the button
still produces something useful.

**Implementation sketch.**
- Track the currently-visualised attempt folder on the server.
  The Receptionist already knows it via `_latest_active_attempt()`
  / the per-cycle `cycle_start_ts` filtering; expose that via a
  small helper, e.g. `_currently_visualised_attempt()` on the
  Session, or just walk `ATTEMPTS_DIR` for the most recent folder
  containing a `parameters.json` AND `propeller_mesh.obj`.
- `api_parameters()` reads that attempt's `parameters.json` and
  returns it.  Frontend behaviour unchanged (still writes the
  returned text to the clipboard).
- Optional: rename the button on the fly to "Copy current
  parameters" when a mesh is loaded, "Copy parameter list" when
  not — clearer UX.

**Why deferred.** Wiring the "current attempt" state from the
agent layer through to a stateless API endpoint touches the
`Session` shape and the Receptionist's attempt-selection logic.
The current static-list behaviour is correct for the empty-
viewer case and is at worst confusing (never wrong) when a
mesh IS loaded, so this can wait for a focused refactor.

**Status.** Open.  Verify what's expected, then either rewire
the endpoint or document the current static behaviour as
intentional.

### F10. LOG and Status view: fix the dynamic gray Orch arrows

**Where.**
- HTML: the two `<line id="orch-caller-link">` and
  `<line id="orch-callee-link">` elements in
  `web/index.html`'s LOG and Status SVG.
- CSS: `.orch-dyn-link` + `.orch-dyn-link[hidden]` in
  `web/style.css`.
- JS: `showOrchCallerLink` / `showOrchCalleeLink` /
  `hideOrchCallerLink` / `hideOrchCalleeLink` /
  `_drawOrchDynLink` / `_edgePointOutward` in `web/app.js`,
  driven from `applyAgentActive` on every `agent_active` SSE
  event involving the Orchestrator.

**What.** When the Orchestrator hands off to a non-Receptionist
agent (UII / Planner / Input Creator / Input inspector / Tool
Caller / Output inspector), or when one of those agents
escalates back to the Orchestrator, a gray arrow in the
appropriate direction is supposed to appear in the flowchart
(`orch-callee-link` for outgoing, `orch-caller-link` for
incoming).  Receptionist ↔ Orch is handled by the static black
arrow and the dynamic ones should stay hidden in that case.

In practice the arrows do not appear reliably.  We have:
- Confirmed the backend publishes the right `agent_active`
  events (verified via `/api/events` EventStream in DevTools).
- Confirmed `applyAgentActive` is being called with the right
  `from` / `to` strings (e.g. `Orchestrator` → `User Input
  Inspector`).
- Switched `link.hidden = true/false` to explicit
  `setAttribute("hidden", "")` / `removeAttribute("hidden")`
  to dodge the SVG `hidden` IDL-property quirk.

Still not visible at last test.  Open hypotheses (try in order):
1. **Cache.** Browser caching of the old `app.js` / `index.html`
   / `style.css`.  Disable cache in DevTools, hard-refresh, and
   confirm `typeof showOrchCalleeLink === "function"` in the
   Console.
2. **Z-order / coverage.** The dynamic lines are drawn before
   the agent box `<g>` elements (so they sit behind, which is
   intentional).  Verify the computed endpoints fall in the
   GAP between Orch and the other agent — e.g. Orch (220, 265,
   120, 50) ↔ UII (40, 200, 120, 50) should yield endpoints
   around (210, 255) → (170, 260).  If the line is being drawn
   inside Orch / UII's rect bounds it will be hidden by the
   coloured fill.
3. **Off-screen / negative coords.** `_edgePointOutward`'s
   10px outward offset can produce negative `x` or `y` for an
   agent that sits flush against the viewBox edge.  Clamp.
4. **Marker reference.** `marker-end="url(#arrow-gray)"` needs
   the `<marker id="arrow-gray">` to be present in `<defs>`.
   That marker was added; confirm it survived later edits.
5. **CSS specificity.** `.orch-dyn-link[hidden] { display: none }`
   must NOT be overridden by any later rule that re-shows
   `<line>` elements indiscriminately.

**Reproduction.** Open the LOG and Status view, send a turn
that escalates from any chain agent back to the Orchestrator
(e.g. ask for a design and let the Planner finish).  Expected:
gray arrow from Planner → Orch while Orch is processing the
escalation, then arrow flips direction (Orch → next agent) when
Orch hands off.  Observed: no arrow.

**Status.** Open.  Debug with the DevTools-based steps under
"Open hypotheses" above; once the root cause is identified,
fix and add a smoke check (e.g. a `data-debug` attribute that
records the most-recent `applyAgentActive` event so we can
verify from the page directly).

### F11. Stop button: tighten the cancellation granularity

**Where.**
- Flag module: `agents/shared/stop_signal.py`
  (`request_stop` / `clear_stop` / `is_stop_requested`).
- Web endpoint that sets the flag: `web_app.py:api_stop`.
- Current single check site:
  `agents/orchestrator/orchestrator.py:dispatch` (top of the
  hop loop).
- Frontend Stop button: `web/index.html` (header) +
  `web/app.js` (`stopBtn` click handler).

**What today.** The Stop button sets a shared flag.  The
Orchestrator polls it **only** at the top of every hop — i.e.
once per agent hand-off.  An agent that's mid-run when Stop is
clicked will finish its ENTIRE turn (every LLM call AND every
tool execution AND its hand-off) before the Orchestrator
notices the flag.  That's the "as soon as the next agent
boundary" cancellation — coarser than what the button name
suggests to a user clicking it as an emergency stop.

**Required behaviour.** Stop should take effect at the EARLIEST
of these three checkpoints, regardless of which agent is
currently running:

1. The current tool call (utility OR routing) returns.
2. The currently-sent inter-agent message has been delivered
   (i.e. the routing tool finishes recording the hop).
3. The currently-running `invoke_with_retry` LLM call returns
   (the model has finished reasoning for the current step).

And, critically: **if an LLM emits a tool call after Stop has
been requested but the agent has not yet invoked the tool,
the tool MUST NOT be executed.**  Instead, the tool result
appended to the agent's `messages` is a sentinel string —
something explicit like `"aborted — process manually stopped
by the user"` — and the agent's loop bails to the Orchestrator
at the very next iteration with that sentinel as its outbound
message.  The Orchestrator in turn surfaces the existing
"(Session interrupted by Stop button…)" reply to the user.

**Implementation sketch.**
- Add `is_stop_requested()` polls inside every agent's
  `_run_llm_loop`:
  - Once at the top of each iteration (before
    `invoke_with_retry`).
  - Once after `invoke_with_retry` returns (catches "model
    reasoned and is about to act").
  - Once before each `tool_fn.invoke(tc["args"])` (the
    "tool not executed" branch — substitute the abort
    sentinel and skip the call).
  - Once after each tool execution (catches the "tool just
    returned, drop the next iteration" case).
- Each early exit appends a `ToolMessage` carrying the abort
  sentinel for any pending `tool_call_id`s (re-use
  `finalize_unanswered_tool_calls` to keep the
  tool_use/tool_result contract intact on both Anthropic and
  OpenAI), then returns an `AgentHop("orchestrator",
  "aborted — process manually stopped by the user")`.
- Routing-tool callsite (`agents/shared/routing_tools.py:245`)
  also needs a Stop check — same sentinel, same hop.
- Update `Orchestrator.dispatch`'s existing Stop check to
  preserve the "(Session interrupted by Stop button…)" reply
  it already returns; the tighter agent-level checks just
  cause it to hit that branch sooner.

**Edge cases to handle.**
- The Receptionist's `validate_input` runs BEFORE the
  Orchestrator's dispatch loop is entered.  A Stop click
  during validate_input must also short-circuit — wire the
  same `_run_llm_loop` polls in `agents/receptionist/
  receptionist.py:_run_llm_loop`.
- Database Handler runs at session end (opt-in save).  Stop
  there should abort the DH cleanly too — its
  `_run_one_conversation` loop is the relevant site.
- Tool-side instrumentation (`@tool_active`, `@generic_tool`)
  must still publish their exit event even when the wrapped
  function is short-circuited by the abort path, otherwise
  the flowchart label gets stuck.

**Why deferred.** Touching every agent's `_run_llm_loop` is
high-blast-radius and easy to break the tool_use/tool_result
contiguity invariants (see resolved issue R2).  Worth a
dedicated commit with the smoke tests in
`extra_utilities/smoke_test_image_buffer.py` re-run to make
sure the abort path doesn't malform message lists.

**Status.** Open.  Today's coarse hop-boundary check is "good
enough" for non-emergency cancellation; this entry tracks the
finer-grained behaviour the Stop button name implies.

### F22. Support multiple simultaneous users (multi-tenant Stage A)

**Where.**  Cross-cutting.  Touches every module that reads / writes
shared global state today:

- ``web_app.py`` — the ``_BOX`` singleton holds **one** Session per
  process.  ``/api/turn``, ``/api/end``, ``/api/images``, etc. all
  read and mutate it without any user identity scoping.  The viz_bus
  SSE stream (``/api/events``) is also process-global — every
  connected browser sees every agent_active event.
- ``agents/loader.py`` — ``_resolve_session_name`` /
  ``_resolve_session_timestamp`` mint a single ``IDxxx_<ts>`` per
  process lifecycle.  The ``IDxxx`` counter reads from
  ``previous_sessions/`` on disk, which is also a single shared
  path.
- ``config.py`` paths — ``LOGS_DIR``, ``ATTEMPTS_DIR``,
  ``USER_INPUTS_DIR``, ``INPUT_IMAGES_DIR``, ``DATABASE_DIR``,
  ``PREVIOUS_SESSIONS_DIR`` are all single global directories that
  every active session shares.
- ``agents/shared/viz_bus.py`` — the publish/subscribe queue is
  one global bus.
- ``agents/database_handler/database_handler.py`` — at End Session
  the archive sweep moves ``/app/attempts/`` and ``/app/inputs/``
  out of the live tree; with two concurrent users this would
  corrupt the other user's in-flight state (this is structurally
  the same race that produced the 2026-05-30 duplicate-save bug
  in single-user mode, where one user's two retried saves raced
  each other — and would be a hard requirement in multi-user mode).
- Auth: today ``POST /api/auth`` validates a shared invite code and
  stores no user identity.  Multi-tenancy needs a per-user identity
  (cookie / JWT) and authorisation on every API endpoint.
- R2 layout: today the key prefix is per-environment
  (``R2_KEY_PREFIX``).  Multi-tenant would need either a per-user
  prefix segment (``<env>/<user_id>/<session_id>/…``) or a
  per-user bucket.

**What.**  Today Stage A is **single-tenant by construction**.  The
Railway deployment serves one session at a time, archived under a
single ``previous_sessions/`` tree, mirrored to a single R2 key
prefix.  Trying to use it with two browsers simultaneously today
will:

1. Have both browsers share the same ``_BOX.session`` — turns from
   user B mutate user A's agent histories.
2. Have both End Session clicks race on the same shared filesystem
   (the same race documented in the 2026-05-30 bug, but now
   structural instead of accidental).
3. Have both saves write to the same R2 prefix
   (``<env>/IDxxx_<ts>/...``) — different timestamps, but the
   ``IDxxx`` counter is shared and the prefix has no user
   discriminator.
4. Have the SSE flowchart cross-pollinate: user A sees user B's
   agent activations and vice versa.

The goal of this work is to make N simultaneous users a supported
mode: each user gets their own isolated session, own attempts/
inputs/logs/database namespace, own SSE event stream, own End
Session lifecycle, and own R2 destination prefix.

**Sub-options for HOW (to be decided).**  This entry is intentionally
under-specified at the design level — pick one of these before
implementation work starts.

- **F22.a — In-process multi-tenancy via per-request session lookup.**
  Replace the ``_BOX`` singleton with a ``dict[user_id, Session]``.
  Every endpoint takes a cookie / JWT, resolves the user, fetches
  or creates that user's Session.  Filesystem paths become
  ``<base>/<user_id>/<session>/…`` (or ``<base>/<session>``
  where ``<session>`` includes a user-prefixed slug).  R2 key
  prefix gains a ``<user_id>`` segment.  SSE viz_bus becomes
  per-user (one queue per user).
  - Pros: smallest delta from current architecture; reuses the
    single-worker uvicorn invariant (W1) so the in-process state
    model still works; no infra changes.
  - Cons: still bounded by one process — concurrent saves still
    share CPU, memory, the same LLM rate-limit budget, the
    same boto3 connection pool.  Crash takes everyone down.
    A single 5-15 min DH save still blocks the threadpool slot;
    other users can keep using the app but slot contention is
    real.
  - Where: ``web_app.py`` rewrites ``_BOX`` → registry; every
    endpoint refactored to require ``user_id``; ``agents/loader.py``
    resolves session under user-scoped roots; ``viz_bus.py``
    becomes per-user.

- **F22.b — Container-per-user via spawn-on-demand.**
  Railway's deployment / Docker can run multiple replicas, but
  not one-per-user out of the box.  This option introduces a
  thin router that spawns a fresh container per user (or per
  N users), backed by a small orchestrator (k8s, Nomad, Docker
  Swarm, or a custom spawn-script).  Each user's container is
  effectively the current single-tenant build, isolated.
  - Pros: zero changes to the Stage A app code itself — each
    container thinks it's single-tenant.  Hard isolation.  Easy
    to reason about.
  - Cons: significant infra work; cold-start latency per user
    (~30s+); per-user cost is the whole container; auth /
    routing layer needs to be built and operated separately
    from the app.

- **F22.c — Move state to Postgres + Redis + R2; make Stage A stateless.**
  Largest rewrite.  Each request reconstitutes the Session
  from durable storage (Postgres for schedule / settings,
  Redis for live message histories + viz_bus pub/sub, R2 for
  artefacts).  No ``_BOX``; no in-memory session at all.  Then
  N uvicorn workers / replicas can serve any user.
  - Pros: cloud-native; scales horizontally; survives restarts
    mid-session (today every Railway redeploy kills any
    in-flight session); aligns with the Stage B database
    design notes (``database_design_notes.md``).
  - Cons: invasive — every agent's ``self.messages`` mutation
    path has to round-trip through a persistence layer; W1 (the
    single-worker invariant) goes away; Redis becomes a hard
    dependency.

- **F22.d — Hybrid: F22.a now, F22.c later.**
  Adopt F22.a for the first cut (per-user dict + per-user paths
  + per-user R2 prefix segment + per-user viz_bus), but design
  the user-id scoping at the data-model boundary so a later
  move to F22.c (state in Postgres + Redis) is a swap-out of
  the registry implementation rather than a re-plumb of every
  endpoint.

**Concrete acceptance criteria (any chosen option must satisfy).**

1. Two browsers can each start a session, run independent turns,
   click End Session, and produce TWO distinct ``previous_sessions/<sid>/``
   archives and TWO disjoint R2 prefixes.  Neither save's archive
   sweep can touch the other user's live ``/app/attempts/`` or
   ``/app/inputs/`` state.
2. Two simultaneous DH saves do not race on the schedule, the
   agent message histories, or the boto3 connection pool.
3. Each user's SSE ``/api/events`` stream only carries that user's
   agent activations.
4. The ``IDxxx`` counter is either per-user (``IDxxx_<user>_<ts>``)
   or globally monotonic across users; either way two concurrent
   ``populate_database`` calls do NOT both pick the same
   ``IDxxx``.
5. R2 keys for two users never collide on a single prefix —
   ``<env>/<user_id>/<session>/…`` or equivalent.
6. ``POST /api/auth`` returns a stable per-user identity (cookie
   or JWT), and every other endpoint authorises against it.
7. A crash / OOM in one user's session does NOT corrupt or stop
   the other user's session.  (F22.c is the only option that
   gives this for free; F22.a / F22.d need careful try/except
   discipline.)

**Why deferred.**  This is a fundamental architecture choice with
significant cost regardless of the option picked, and the current
single-user mode is sufficient for the v9 milestone.  The work
should NOT start until:

- The duplicate-save / HTTP-timeout fix (the lock on ``/api/end``,
  per the 2026-05-30 diagnosis) lands first — every option above
  depends on having a single well-defined save lifecycle per
  user.
- Auth strategy is decided (cookie vs JWT; per-user vs invite-code).
- A clear answer to: do we expect 2-3 simultaneous users (favor
  F22.a / F22.d) or 20+ (favor F22.b / F22.c)?

**Status.** Open.  Architecture choice pending.

### F23. Replace the Context Pruner's pre-scan + tier-2 input cap with something less crude

**Where.**
- ``agents/shared/base_chain_agent.py`` — ``_truncate_oversized_messages`` (the pre-scan helper) and the tier-2 input-cap block inside ``prune_history_if_needed``.
- ``workflow_settings/settings.py`` — ``CONTEXT_PRUNER_MAX_INDIVIDUAL_MESSAGE_TOKENS``, ``CONTEXT_PRUNER_TIER2_INPUT_CAP_TOKENS``.
- ``agents/shared/context_pruner.py`` — three-tier prompts.

**What.**  Both defences shipped on 2026-05-31 in response to the live incident where the Receptionist called ``read_attempt(file="propeller_mesh.obj")``, got a 1.3 MB inline mesh dump (~333k tokens) as a ToolMessage, and the Context Pruner's own tier-2 LLM call then 429-ed with "Request too large for gpt-5.4-mini in organization … TPM Limit 200000, Requested 333109".  They work, but both are **crude band-aids** rather than the right design:

- **Pre-scan** blindly truncates any single message above the cap (default 30 000 tokens) to the first 2 000 characters plus a marker.  Lossy by character count rather than by semantic relevance; cuts mid-sentence; doesn't distinguish "a 50 000-token tool output that was actually useful" from "a 50 000-token tool output that was a mistake".
- **Tier-2 input cap** truncates the serialised tail by **character ratio**, not by message boundaries.  Can chop the head off the most recent message, lose tool-call closures, or leave the LLM a partial JSON fragment.
- Both caps are **single global numbers** — they don't adapt to the actual upstream provider's per-request TPM limit (which differs per model/account).
- Neither defence is **needed in the happy path** — they only matter when a tool returns way too much content, which itself is the upstream bug.

**Proposal sketch** — one of, or a combination of:

1. **Per-tool output caps at the source.**  Extend the pattern already used by ``read_attempt`` (mesh suffixes → path only): every tool that can produce variable-length output declares its own cap and its own degradation strategy (path-only, head + tail with marker, structured stats, etc.).  This eliminates the failure mode at the cause rather than mopping it up downstream.  ``load_render_images``, ``read_extracted_inputs``, the ``read_attempt`` text branch, anything in the future agents add — all should honour a per-tool ``MAX_INLINE_CHARS`` (or per-suffix policy).
2. **Smarter pre-scan that preserves message tail rather than head.**  For oversized ToolMessages the LAST few lines (e.g. final tool error / final stat block) are usually more useful than the first 2 000 chars.  Head-AND-tail with the middle elided ("[... 320 000 chars elided ...]") would be more honest than head-only.
3. **Tier-2 should drop OLDEST tail messages first, not truncate by character ratio.**  If the tail is over cap, drop messages from the front of the tail until it fits, with a marker noting how many were dropped (and into a synthetic summary line "[N earlier tail messages dropped — see tier-1 summary for context]").  Preserves message-boundary semantics and keeps the most recent / most relevant turns intact.
4. **Provider-aware cap on tier-2 input.**  Read the agent's bound provider+model from ``self.provider`` / ``self.model``, look up the per-request input limit from a small ``PROVIDER_INPUT_LIMITS`` table (OpenAI 200k for gpt-4o-mini, Anthropic 200k for haiku, Google ~30k for flash, etc.), and use 0.7× that as the per-call cap.  The current 60 000 default is conservative-or-wasteful depending on the provider.
5. **Dedicated chunked-summarisation for very large tails.**  When the tail genuinely needs summarising but exceeds the LLM's per-call cap, split it into chunks of ``cap × 0.7`` tokens each, summarise each chunk independently, then summarise the chunk-summaries.  Map-reduce in spirit.  More LLM calls but never truncates the input.
6. **Telemetry first.**  Log every time the pre-scan / tier-2 cap fires (already done in the commit) and dashboard it.  See which tools actually trigger this in production before deciding which of 1-5 to ship.

**Why deferred.**  The current defences are correctness-safe (the system never gets *worse* than the un-defended state — a truncated ToolMessage is strictly better than a 429-ing prune chain) and they unblock the 2026-05-31 production failure.  The proper fix is a small per-tool design pass plus arguably a provider-aware cap; both want a calm refactor cycle, not the same-day deploy that landed the band-aid.

**Status.**  Open.  Triage suggestion: option 1 (per-tool source caps) is the highest-leverage move because it removes the failure mode entirely for known tools.  Combine with option 4 (provider-aware tier-2 cap) for a complete fix; options 2/3/5 become nice-to-have polish.

### F25. Pre-compute the active FIXED parameter set in Python instead of asking the UII to walk user_query.txt

**Where.**  The User Input Inspector's prompt now contains a "Temporal scope and Parameters Inputs interface blocks" section instructing the UII's LLM to walk ``user_query.txt`` forward in time, applying each ``FIXED block`` (full snapshot) and each ``RELEASED`` block (drop listed keys) to compute the active constraint set.  This is in-prompt logic relying on the LLM to do a deterministic file-merge correctly.

**What to explore.**  Replace the in-prompt walk with a Python pre-computation: have ``dispatch.py`` (or wherever the FIXED state is tracked) maintain the active-FIXED dict in memory, and pass it to the UII as a structured hand-off field (e.g. inside the Orchestrator's hand-off message body, or as a new attribute on the inputs bundle returned by ``load_user_inputs_bundle``).  The UII's prompt would then read the pre-computed set directly rather than reconstructing it.

**Why deferred.**  In-prompt walk is fine for now per the user's 2026-06-01 sign-off — the LLM is generally good at this kind of step-by-step merge over a small file, and we want to see if natural-language errors actually appear before adding pre-computation plumbing.  The Python pre-computation is a clean upgrade path if (a) we see UII regressions interpreting FIXED/RELEASED blocks, or (b) ``user_query.txt`` grows long enough that walking it in-prompt becomes wasteful tokens.

**Status.**  Open as a candidate for future exploration — NOT committed to being implemented.  Reassess after a few real sessions exercise the new flow.

### F26. Verify the Planner's behaviour in problematic / non-happy-path cases

**Where.**  Planner prompt updates landed across commits b7f4879 (initial "consult prior attempts on user reference" addition), 40c2951 (tightened to exceptional cases only), and be0de09 (Role 3 APPROVE clarity paragraph for natural-language endorsement vs. hedging — drives the Receptionist's spontaneous ``propose_attempt`` decision).  These changes have been tested only on the happy path so far.

**What to check.**  Exercise the Planner in scenarios that stress the new rules:

- **Multi-cycle defect recovery.**  Trigger a sequence where the DCOI flags the same defect across 2-3 consecutive cycles.  Verify the Planner correctly invokes ``list_attempts()`` / ``read_attempt(n, 'parameters.json')`` only in the recovery context (the "Typical recovery use" bullet in the unified exceptional-cases section), not on the routine user-reference case the UII handles upstream.
- **Error interpretation.**  Inject a tool failure or a confusing log entry tied to a specific attempt and observe whether the Planner reads that attempt's files to investigate (the "Error interpretation" bullet).
- **Ambiguous / hard-to-parse user request.**  Send something like *"do something different from before"* without context, or a request that contradicts the UII's extraction.  Verify the Planner reads prior attempts to clarify before planning (the "Ambiguous / hard-to-parse" bullet).
- **Additional supervision.**  When the UII's extraction or the DCIC's parameter choice looks suspicious, the Planner should be able to verify against on-disk parameters (the "Additional supervision" bullet).
- **APPROVE-branch endorsement vocabulary.**  Verify the Planner's "Show to user:" line phrases endorsement clearly enough for the Receptionist to decide whether to fire ``propose_attempt``.  Happy path was tested in commit be0de09; need to check:
  - Cases where the Planner approves an INTERMEDIATE attempt with hedging language ("first cut", "still revising"): the Receptionist should NOT fire ``propose_attempt`` and the Parameters Inputs panel should stay sticky on the last actually-endorsed pick.
  - Cases where the Planner's wording is ambiguous (neither clearly endorsement nor clearly hedging): does the Receptionist misjudge?  This is the natural-language fuzziness W22 calls out — worth a real-session check.
- **REVISE / REPLY-DIRECTLY branches.**  Confirm the Planner correctly produces a recovery plan (REVISE) or a user-facing summary (REPLY DIRECTLY) when those branches apply; the natural-language endorsement guidance in APPROVE shouldn't accidentally bleed into the other two.

**Why open.**  Manual end-to-end testing on a real session for the problematic paths hasn't been done yet (only the happy path verified for commit be0de09).  Without this verification we don't know whether the new prompt rules survive contact with real LLM behaviour under stress.

**Status.**  Open.  Test in a calm session before the next round of prompt edits to the Planner — easier to attribute regressions to specific commits than to debug after several more changes layer on top.

### F27. Live-preview ON / OFF toggle in the Parameters Inputs view

**Where.**  Parameters Inputs view's live-preview pipeline — ``web/app.js`` ``paramsRequestPreviewDebounced`` (currently fires on every slider input with a 300 ms trailing-edge debounce; no opt-out).

**What to build.**  A small toggle (checkbox or button) in the Parameters Inputs view's bottom row (next to Copy parameters / Use these parameters / Download geometry) that turns the live preview ON / OFF.  When OFF, slider input still updates ``paramState`` and the VARY → FIXED transition, but does NOT call ``/api/preview_mesh``; the params viewer holds whatever mesh was last loaded (or stays at the placeholder if none).  Probably want to persist the toggle's state via ``sessionStorage`` so it survives navigation between tabs in the side menu.

**Why deferred.**  Locked decision §6.G.D1 (web_interface_notes.md): *"no toggle in v1, added to TODO list"*.  300 ms debounce is enough headroom for normal slider use, but a power-user dragging many sliders in sequence might want to silence the preview to avoid RhinoCompute round-trips per change.

**Status.**  Open.  Pick up when there is feedback that the always-on preview is annoying; not a behavioural blocker.

### F28. ``sessionStorage`` persistence of Parameters Inputs panel state across page reload

**Where.**  Parameters Inputs view's runtime state — currently in-memory only (``paramState``, ``paramRowState``, ``_lastSentFixedDict``, ``_lastSentFixedFingerprint``, the per-row ``data-has-proposal`` / proposed-text DOM, the latest preview blob URL).  A page reload mid-session wipes all of this and the panel resets to all-gray VARY at defaults.

**What to build.**  Per locked decision §6.I: persist the relevant pieces to ``sessionStorage`` on every change; rehydrate in ``paramsInit()``.  Concrete shape — a single key like ``params:fixed_state`` holding a JSON dict ``{<paramKey>: {state: "vary"|"fixed"|"proposed", value: <number>, proposedValue: <number | null>}}``.  Restore the slider DOM positions + ``data-state`` + proposed-text + dedup-snapshot from the rehydrated dict on init.  No backend changes; per-tab scope (sessionStorage, not localStorage) so closing the tab clears it.

**Why deferred.**  Confirmed low priority on 2026-06-XX.  Mid-session page reload is uncommon and recoverable (the user re-fixes what they want; the live preview re-runs on the first slider change).  The redesign's behavioural goal is reached without persistence.

**Status.**  Open as a polish item — pick up if reload-during-session becomes a real workflow.

---

## Future work / planned enhancements (continued)

### F29. Improve the DCII's extraction-fidelity verification step

**Where.**  `agents/dc_input_inspector/prompt.md` — axis 5
("Faithfulness of the extraction") in "Your Role" and the
extraction-fidelity paragraph in "Optional reference: user input
images" introduce the DCII's responsibility to re-read user inputs
(text + images) and verify that ``extracted_inputs.txt`` faithfully
reflects them.  Paired with image-complexity signals authored by the
User Input Inspector (``agents/user_input_inspector/prompt.md``) and
the Planner (``agents/planner/prompt.md``) that let the DCII decide
when a re-read of the image is worthwhile.

**What.**  The current prompt-level instruction frames the
verification as reactive — fires when the DCII *suspects* an
extraction problem.  Worth exploring:

  * Trigger heuristics — when does the DCII proactively re-read vs.
    only react to suspicion?
  * Structured flag output — when the DCII detects an extraction
    error, give the message a fixed shape so the Orchestrator /
    Planner / UII can act on it without prose-parsing.
  * Cost discipline — cheap textual re-reads first, expensive
    image re-loads only when needed.
  * Image-complexity vocabulary — today the UII and Planner are
    asked to convey complexity in their own prose; the DCII parses
    it as natural language.  A fixed lexicon (e.g. SIMPLE /
    MODERATE / COMPLEX) would tighten the contract but lose the
    open-ended reasoning latitude.
  * Feedback loop to the UII — today nothing closes the loop so
    future runs improve.

**Why deferred.**  The prompt-level instructions added in the same
sprint are a workable starting point.  These refinements want a
calm design pass.

**Status.**  Open.

### F30. Render-view selection for retrieve_attempt is currently a developer-time choice

**Where.**  `workflow_settings/settings.py` block #21 (three bool
flags); `tools/retrieve_attempt/retrieve_attempt.py` (consumer,
Phase 5C).

**What.**  The three workflow flags
``RETRIEVE_ATTEMPT_INCLUDE_{TOP,SIDE,ISOMETRIC}_VIEW`` decide which
of the saved render PNGs to attach when an agent calls
``retrieve_attempt(..., images_flag=True)``.  Today the developer
flips the booleans before deploy; the calling agent has no say.

Two future improvements worth considering once the visual rendering
tool design firms up:

  * Per-call view selection — extend the tool signature with a
    ``views`` parameter (subset of {"top","side","isometric"}) so
    the agent picks per call.
  * Tool-level coupling — when the agent uses the visual rendering
    tool independently, retrieve_attempt's default could adapt to
    match whatever that tool's chosen render-view convention is.

**Why deferred.**  Locking the choice to the developer for now keeps
the v1 retrieve_attempt response shape predictable (every call from
the same deploy returns the same view set), and avoids designing the
per-call API before the broader visual-rendering tool's contract is
settled.

**Status.**  Open.

### F31. SSE disconnect-recovery cache for /api/turn + /api/end completion events

**Where.**  `web_app.py:_run_turn_in_background` (publish-side),
`web_app.py:_run_end_in_background` (publish-side), `web/app.js`
`_pendingTurns` + `finalizeTurn` (consume-side); same shape on
the End Session side via `endSessionState` / `finalizeEndSession`.

**What.**  Both `/api/turn` and `/api/end` return HTTP 202 with
fire-and-forget completion via the `/api/events` SSE stream
(`turn_done` and `session_save_done` events).  If the browser tab
is closed between the 202 response and the matching SSE event, or
the SSE connection drops between event publication and re-connect,
the completion event is **lost**.  The chat bubble (resp. the End
Session button) stays stuck in its pending state on next page
load even though the server-side work succeeded.

**Why deferred.**  The window is narrow in practice (turn = a few
seconds to ~10 min; End Session = ~5–15 min) and the single-user
W13/O9 constraint means a stuck UI is recoverable by reloading
and sending a "what was the result" follow-up message — the
Receptionist can answer from the live session state.  Shipping the
minimal 202+SSE fix without the cache keeps the diff small and
matches the existing `/api/end` behaviour exactly.

**Proper fix.**  A small server-side cache `{turn_id: turn_done
payload}` (bounded by N most-recent entries, evicted on session
end) plus a new GET `/api/turns/<turn_id>` endpoint.  Frontend on
SSE `onerror` or page reload reads any pending `turn_id` from
`sessionStorage` and polls that endpoint.  Same shape for End
Session if you want to fully close that loop too.

**Status.**  Open.  Pair this with any future work that broadens
the chat-turn UX (e.g. multi-turn history restore on reload —
[[F28]]).

### F32. Estimate parameters from visual proportions in user-supplied images

**Where.**  `agents/user_input_inspector/` (UII — the agent that
extracts user inputs from sketches / reference images) and its
prompt fragments under `DC_prompt_fragments/user_input_inspector/`.
Downstream interpretation may also need adjustment in the DCIC
(which writes parameters.json) and the Planner (which sets the
strategy).

**What.**  Today the UII extracts EXPLICIT numerical annotations
the user wrote on their sketch (chord mm, angle degrees, ring
thickness mm).  It does NOT estimate parameter values from the
VISUAL PROPORTIONS shown in the drawing when those values are
absent.  Several parameters could plausibly be estimated from
proportional reasoning over the image alone:

  * `innerThickness` / `outerThickness`: from the section
    views' thickness-to-chord ratio.
  * `innerCamber` / `outerCamber`: from the curvature of the
    section sketch's mean-line.
  * Relative chord widths across sections: from the planform
    view.
  * `innerMaxPos` / `outerMaxPos`: from where the maximum
    thickness sits along the chord in the section sketch.
  * `middlePos`: from where the broadest chord sits radially in
    the planform.
  * Ring proportions (`impellerThickness` vs `impellerRadius`) from
    a side or isometric view.  (Ring HEIGHT is derived — it auto-fits
    the outer section — so it is not read from the sketch.)

The 2026-06-04 propeller-from-sketches run is a clean example:
the user supplied a thin-small-thin geometry intent but no
numbers for inner/outer thickness or camber.  The UII
extracted only the explicit annotations and left section-shape
parameters to the DCIC's defaults; a proportional-estimation
pass would have lifted thickness/camber/max-pos estimates
directly from the section sketches.

**Why deferred.**  The current happy path works when the user
writes explicit numbers; the failure mode is silent when they
don't (downstream picks defaults that ignore the visual
evidence).  A proper fix needs:

  1. UII prompt-fragment guidance telling the agent to MEASURE
     proportionally (pixel-ratio style reasoning over the
     image) and to record an estimate + a confidence note.
  2. A per-parameter heuristic table mapping visual ratios to
     parameter ranges (e.g. "blade chord-to-thickness ratio
     ~8:1 → thickness ~12 % of chord → map to innerThickness
     within the configurator's allowed range").
  3. A way for DCIC / Planner to distinguish "explicit user
     value" from "proportional estimate" when weighing inputs
     against each other.

**Status.**  Open.  Logically pairs with [[F29]] (DCII
extraction-fidelity verification): F29 checks how faithful the
extraction is to the image; F32 makes the extraction more
capable in the first place.

### F34. Compress user-input images before save / retrieval / LLM-pass

**Where.**  Image flow touches multiple surfaces; the proper
fix instruments three of them:

  * `web_app.py` `_save_uploaded_image` (and any sibling on the
    upload endpoint) — INGEST path from the web UI's Image
    Inputs view into `inputs/input_images/`.
  * `agents/shared/llm_provider.py::make_image_block` —
    LLM-PASS encode site for outgoing image content blocks.
  * `tools/retrieve_user_inputs/retrieve_user_inputs.py::_run_retrieve_user_inputs`
    and `tools/retrieve_attempt/retrieve_attempt.py` —
    R2-side RETRIEVAL paths that re-attach image bytes to
    tool responses for past saved sessions.

Adjacent supporting sites (read for context, not necessarily
modified):

  * `agents/shared/file_utils.py::load_user_inputs_bundle` /
    `load_input_images` — agent-side load from disk.
  * `agents/database_handler/database_handler.py::_collect_user_inputs`
    — DH copy from `inputs/input_images/` into
    `database/<sid>/user_inputs/images/` ahead of the R2 mirror.
  * `agents/shared/r2_uploader.py::upload_directory` /
    `upload_attempt_artefacts` — R2 PUT site.

**What.**  User-uploaded reference images flow through the
system at their original resolution and encoding today.  A
modern phone-camera PNG or JPEG is easily 3–6 MB, which:

  1. **Fills the LLM context window.**  Providers count
     base64-encoded image bytes against the per-call input
     budget.  A 4 MB image consumes ~5.3 MB of token-equivalent
     space; multi-image turns push UII / DCII / DCOI close to
     or past per-call limits, contribute to Anthropic 429
     rate-limit hits during image-heavy turns (already a
     recurring operational gotcha — see the 2026-06-04 →
     2026-06-05 sprint notes), and cost real money on input
     tokens.
  2. **Bloats R2 storage and bandwidth.**  Each saved session
     mirrors its reference images to R2; later
     `retrieve_user_inputs(images_flag=True)` calls re-fetch
     them.  Both pay R2 bandwidth + storage and re-pay the
     context cost on the retrieving side.
  3. **Slows every image-touching pass.**  Encode / decode /
     network round-trip / LLM input parsing all scale with
     image size, and there are 3–5 LLM passes per session that
     touch the images (UII initial read, optional UII
     re-read with retrieve_*, DCII, DCOI per attempt).

A single Pillow-based compression pass (resize the longest
side to N pixels + re-encode as JPEG at quality Q) typically
delivers a 10–30× reduction with no human-visible loss for the
kind of sketches and references our users upload.

The compression can apply at any of THREE distinct points,
and the right design likely combines them:

  * **At INGEST** — compress once at upload time; everything
    downstream (LLM calls, DH save, R2 mirror, future
    retrievals) inherits the smaller bytes.  Cheapest if we
    trust the compression budget for the use case.
  * **At LLM-PASS** — keep the original on disk / R2;
    compress in-memory only when handing bytes to an LLM.
    Preserves the canonical asset but pays the compression
    cost on every LLM read.
  * **At RETRIEVAL** — keep originals everywhere; compress
    only when `retrieve_user_inputs` / `retrieve_attempt`
    packs bytes into a tool response.  Required for legacy
    images already on R2 from sessions saved before this
    feature shipped.

A typical configuration would be ingest-time by default plus
retrieval-time for legacy R2 content, with LLM-pass as a
safety-net guard against any path that bypassed both.

**Why deferred.**  Three real concerns to settle before
shipping:

  1. **Quality loss for image-as-blueprint use cases.**  When
     a user uploads a hand-drawn sketch annotated with
     numerical parameters (small text, thin lines), aggressive
     compression can destroy annotation legibility.  The UII
     relies on reading those annotations.  Compression budgets
     need empirical calibration per use case — likely two
     tiers (gentle for annotated sketches, aggressive for
     photo references) with a heuristic or a per-image
     metadata hint to pick.
  2. **In-place vs canonical-preservation.**  Compressing at
     ingest is destructive — the canonical original is lost.
     We may want the original archived to R2 under a separate
     key shape and only the compressed version flowing through
     the agent chain + retrieval surface.  Adds R2 key shape
     complexity.
  3. **EXIF / orientation handling.**  Phone images carry
     EXIF orientation metadata; a naive resize without
     honouring it produces sideways thumbnails.  The
     compression helper must rotate-bake before resize.

**Proper fix.**  Five components:

  1. **New helper** at `agents/shared/image_utils.py`:
     `compress_image_bytes(data, *, max_dim, quality, format='JPEG')`.
     Pillow-backed.  Honours EXIF orientation, preserves
     aspect ratio, returns `(compressed_bytes, mime_type)`.
     Handles PNG-with-transparency by detecting alpha and
     either keeping PNG with palette quantisation or
     flattening on white background.
  2. **New workflow-settings block** (next free number, likely
     #24) with four knobs:
       * `IMAGE_COMPRESSION_ENABLED` (bool, default `True`)
       * `IMAGE_COMPRESSION_MAX_DIMENSION_PX` (int, default
         `1280`)
       * `IMAGE_COMPRESSION_JPEG_QUALITY` (int 1–95, default
         `85`)
       * `IMAGE_COMPRESSION_APPLY_AT` (enum: `"ingest"`,
         `"llm-pass"`, `"retrieval"`, `"all"`; default
         `"ingest"`).
  3. **Call site 1 — INGEST.**  `web_app.py::_save_uploaded_image`
     runs the helper before writing to
     `inputs/input_images/`.  The on-disk file is the
     compressed form.  Gated on the settings block.
  4. **Call site 2 — LLM-PASS.**  `make_image_block` runs the
     helper on raw bytes when `APPLY_AT in {"llm-pass", "all"}`.
     Cheap insurance against any path that bypassed ingest
     (programmatic image adds, legacy on-disk content).
  5. **Call site 3 — RETRIEVAL.**  Both retrieve_* tools run
     the helper on R2-fetched bytes before building the image
     content blocks when `APPLY_AT in {"retrieval", "all"}`.
     This is the critical path for legacy R2 content that
     landed before ingest-time compression existed.

Pairs naturally with a small smoke test that verifies the
default compression budget preserves blade-count + annotation
visibility on a representative sketch corpus while delivering
the expected size reduction.

**Status.**  Open.  **High priority** — directly impacts
per-turn LLM input cost, the frequency of Anthropic 429
rate-limit hits on image-heavy turns, and the effective
context window the chain agents have to work against.  Best
landed as a focused multi-commit sprint (helper → settings →
ingest → LLM-pass → retrieval → smoke test).  Pairs with F32
(visual-proportion parameter estimation) — both improvements
make the UII's effective image budget go further.


### F35. Re-audit the Context Pruner — does it act on the Database Handler or not?

**Where.**

  * `agents/shared/base_chain_agent.py::prune_history_if_needed`
    — the pre-invoke hook every chain agent calls at the top
    of its run loop.
  * `agents/shared/context_pruner.py` — the three-tier
    escalation Pruner agent itself.
  * `agents/database_handler/database_handler.py` —
    `populate_database`, `_run_one_conversation`,
    `_formulate_question`, `_decide_next`,
    `_enforce_semantic_cap_pair`, `_run_force_tool_phase`.
    The DH's own LLM invokes (the ones formulating questions /
    parsing ASK / SAVE responses) AND the
    `invoke_with_retry(agent.base_llm, ...)` calls against
    each interviewed chain agent's bare LLM.
  * Workflow settings: `CONTEXT_PRUNER_ENABLED`,
    `CONTEXT_PRUNER_THRESHOLD_TOKENS` (default 80 000),
    `CONTEXT_PRUNER_KEEP_LAST_MESSAGES` (default 6),
    `CONTEXT_PRUNER_MAX_INDIVIDUAL_MESSAGE_TOKENS`,
    `CONTEXT_PRUNER_TIER2_INPUT_CAP_TOKENS`.
  * Cross-refs: README's "Context Pruner" section, F7 (status
    note), F12 (10-item verification checklist), O3 (DH
    context-window pressure, still open).

**What.**  The Context Pruner shipped in v9 and is documented
as **intentionally NOT applied to the Database Handler** (per
the README CP section + F12 item 9 + F7 status note).  The
stated rationale: the DH iterates ~28 schedule entries in one
save and relies on accumulated state — pruning would lose
context the DH needs to formulate later questions accurately.

But this design decision has never been validated end-to-end
against a real long DH save, and there are four specific
questions the audit should answer:

  1. **Is the design intent actually implemented?**  Walk the
     DH code paths and confirm no inherited / indirect call
     site triggers `prune_history_if_needed` on the DH's own
     `self.messages` buffer.  The DH does NOT subclass
     `BaseChainAgent` (it has its own base), but a subtle
     copy-paste or future refactor could introduce a hook
     accidentally.
  2. **What is the DH's real context size on long saves?**
     Sessions with 40+ chunks (e.g. ID057, ID059 from the
     2026-06-04 sprint) iterate dozens of Q+A interviews.
     Each appends ASK + SAVE turns to `self.messages`.  Need
     real measurements: at the END of a long DH save, how
     many tokens are in `self.messages`?  Is it close to the
     provider's per-call budget?  This is the empirical
     ground for whether O3 (still open) is a real risk or a
     theoretical one.
  3. **Are the interviewed chain agents pruned mid-interview?**
     When the DH calls
     `invoke_with_retry(agent.base_llm, [system_msg] + convo_buffer)`,
     it bypasses `BaseChainAgent`'s run loop entirely — so
     `prune_history_if_needed` is NOT called.  But the agent's
     OWN `self.messages` is still the source of `convo_buffer`.
     If the agent's history was already pruned during the live
     session, the DH sees the pruned form (likely fine).  If
     not, the DH sees the full history — possibly large.
     Confirm: does the DH ever construct a `convo_buffer`
     large enough to hit the upstream provider's per-call
     limit?  (Especially for DCOI with image-heavy attempts,
     before F34's compression lands.)
  4. **Is "DH NOT pruned" still the right design?**  Alternative
     designs worth weighing if the audit turns up real
     pressure:
       a. **Per-agent eviction** (O3's sketch) — at each
          `_formulate_question`, walk `self.messages` backwards
          and truncate to the boundary where the CURRENT
          agent's section began.  Earlier agents' interviews
          stay archived on disk under
          `database/<sid>/<agent>/`; the DH doesn't need them
          in live context.
       b. **Custom CP for the DH** with a more aggressive
          threshold and a tailored prompt that knows about
          the DH's ASK / SAVE protocol.
       c. **Keep "no pruning" but cap the schedule** — if the
          real bottleneck is too many entries per save, bound
          the per-save count and require multiple End Session
          rounds for very long sessions.
       d. **Status quo** — if the audit shows actual budgets
          comfortable, no change needed; close O3.

The F12 checklist already lists "DB Handler not pruned" as
item 9 but does not exercise the EMPIRICAL question 2 above.
F35 is the focused follow-up: a single empirical run plus a
code audit.

**Why deferred.**  F12 as a whole is open; F35 is the subset
that matters most for stability since the DH save is the
only place a single LLM call routinely processes a giant
accumulated state.  Lower than the live-session items but
worth scheduling before the corpus grows much larger (more
chunks per save → more DH context pressure).

**Proper fix.**  Three components:

  1. **Code audit.**  Read `database_handler.py` end-to-end,
     confirm no path calls `prune_history_if_needed` on the
     DH's own buffer.  Document the finding inline in the
     DH file as a comment so future refactors don't quietly
     re-introduce the hook.
  2. **Empirical run.**  Take the longest real saved session
     (ID057 or ID059, 40 chunks each).  Add instrumentation to
     log `count_tokens(self.messages)` at the start of every
     `_formulate_question` AND the size of every `convo_buffer`
     handed to an interviewed agent's `base_llm`.  Run a fresh
     DH save (or replay against the existing chunks if
     possible).  Capture the curve.
  3. **Decision.**  Based on (2):
       * Tokens stay <50 % of provider limit → close O3 as
         "no action needed", document in README.
       * Tokens hit 50–80 % → adopt per-agent eviction
         (option a) as a lightweight protective measure.
       * Tokens hit > 80 % → either custom DH CP (option b)
         or schedule capping (option c), based on which
         dominates.

**Status.**  Open.  Pairs with F12 (broader CP verification)
and O3 (DH context-window pressure, currently still labelled
"open, low priority while no refactor planned" — F35's
empirical step would either close O3 or escalate its
priority).

### F37. Evaluate VLM-enriched text for user-image multimodal embeddings

**Where.**  `agents/database_handler/db_writer_mm.py` (the
multimodal mirror writer — the image-embedding site, which fuses
each image with its associated text via voyage-multimodal-3.5)
and the `chunks_mm` table created by
`extra_utilities/db_design/migrations/migrate_v7_to_v8.py`.
Evaluation would lean on the F36 embedding-tests mini-eval
harness once that exists.

**What.**  In the multimodal `chunks_mm` table, each USER-INPUT
image is embedded with voyage-multimodal-3.5 fused with ONLY the
user-written `<name>_note.txt`.  We deliberately do NOT add a
VLM-generated description of the image to the fused text.

The bias argument: fusing a VLM caption would pull the vector
toward what the VLM *saw and chose to describe*, risking
(a) losing genuine visual similarity between sketches
("similar sketches retrieved"), and (b) suppressing retrieval of
details the VLM failed to notice ("details not spotted by the
VLM").  The user-written note is the lower-risk signal: it
reflects the user's own stated intent and is smaller / more
faithful.  The expected LOSS from joining the user-written note
is minimal; adding a VLM-generated description is the riskier
move.

**Scope note — RENDERS are handled differently and are NOT part
of this concern.**  Each attempt render is fused with the
chain-authored attempt `description.txt` (the design narrative
the chain already produced), NOT a VLM caption of the render
pixels.  The bias risk above does not apply to renders — their
fused text is an existing chain artefact, not a fresh
image-derived description.

**Why deferred / TODO.**  Once the multimodal index is populated
and the F36 mini-eval harness exists, empirically compare on the
eval query set, cut by image family (sketches / renders /
photos):

  * `image-only`,
  * `image + user-note` (current default),
  * `image + user-note + VLM-caption`,
  * `image + VLM-caption-only`.

Decide per-family whether a VLM caption helps or hurts.  Keep
**image + user-note** as the default until measured.

**Status.**  Open.  Deferred until the multimodal index is
populated + the eval harness exists (pairs with F36).  Design
rationale also recorded in
`extra_utilities/db_design/database_and_RAG_architecture.md`
§6.3.

### F38. OCR region re-read relies on the detector spotting every text region

> **F36 and F37 are taken on sibling branches.**  F36 is the
> embedding-tests mini-eval (the `eb24c7c` doc commit on the
> `silly-black` branch); F37 is "Evaluate VLM-enriched text for
> user-image multimodal embeddings" (the parallel DB session, already
> on `stage-a-web-deploy`).  This entry is therefore **F38**.

**Where.**  The not-yet-built OCR feature — see
`extra_utilities/docs/reference/OCR_technology_notes.md` (the region / crop re-OCR
escalation tier, §3 Decision 3 + §4).  No code exists yet; this
records a design assumption to validate before / during build.

**What.**  The region re-OCR escalation tool does **not** let the
agent free-crop the image.  Instead, the whole-image OCR pass runs
text **detection** and returns a list of detected text regions, each
with an **ID**; when the agent wants a higher-quality re-read it
specifies a **region ID**, not a bounding box.  This is deliberate:
VLMs are poor at the spatial reasoning needed to say *where* to crop,
so handing them a menu of detector-found regions to pick from is more
reliable than trusting agent-supplied coordinates.

**The assumption this rests on.**  The mechanism only works if the
text-detection pass spots **every** region that actually contains
text.  A region the detector misses has **no ID**, so the agent has
no way to escalate a high-quality re-OCR onto it — the missed text is
invisible to the precision path even if the agent can faintly see it
in the raw image.  In other words, the escalation tier inherits the
**recall** of the whole-image detector: low detection recall silently
caps what the agent can ever re-read, and the failure is silent (no
ID simply looks like "no text there").

**Why it matters here specifically.**  The target images are
hand-drawn engineering sketches and annotated renders where callouts
can be faint, rotated, overlapping the drawing, or in unusual places
(red arrow labels, tiny chord annotations).  These are exactly the
conditions where a detector's recall is weakest — so the assumption
is most fragile precisely on the inputs the feature exists to serve.

**What "validate / mitigate" looks like.**

  1. Measure detection **recall** on the few annotated test images we
     have (`renderwinfo_test1_image.png`,
     `renderwinfo_test2_image.png`) — does the detector find all
     callouts, including faint / rotated / arrow-attached ones?
  2. If recall is the bottleneck, consider escape hatches so a missed
     region is not permanently unreachable, e.g.: a coarse fallback
     where the agent can still name an approximate area (grid cell)
     when it sees text the detector didn't flag; or running detection
     at higher resolution / with rotation handling; or letting the
     whole-image OCR text itself (not just detected boxes) be the
     menu the agent re-reads from.
  3. Surface the detector's miss honestly — if the agent reports text
     it sees that has no matching region ID, log it rather than
     letting it vanish.

**Status.**  Open — the assumption still holds.  The escalation tool
shipped (2026-06-17) and became **multi-region + crop-gated** on
2026-07-06 as `ocr_regions(image_path, region_ids)` — but batching
region re-reads into one call does **not** change detector recall, so the
core F38 risk (a missed region has no ID to escalate) is unchanged.
Partial mitigation only: an **out-of-range** region id is now non-fatal
and reported inline (per-region), and the smoke test measures recall on
the annotated test images — but a genuine detector **miss** still yields
no id at all.  Resolve via the escape hatches above
(OCR_technology_notes.md §4).


### F42. Make the Planner and DCOI processes faster / more focused

**Status.** PARTIALLY ADDRESSED (2026-06-18) — the sections-context "clear,
precise, non-wasteful feedback" guidance is in the DCOI + Planner blade-sections
overlays; the general Planner/DCOI efficiency (beyond blade sections) is
deferred to a later step (user decision).

> Try to make the planner and the DCOI make their processes faster. e.g. when the DCOI observes the blade sections, many iterations may be required, so the feedback is to be given clearly and precisely and don't waste time on useless feedback. It all depends on the user request


### F44. Check whether the Context Pruner and Database Handler have / need blade-sections-tool info

**Status.** NOT STARTED.

> Check if the CP and DH have info about the blade sections tool, and if they need such info at all

Note (partly known already, 2026-06-18): the **DH does** carry the brief
blade-sections awareness fragment — it was one of the 9 agents given the
`<<BSV_ON>>/<<BSV_OFF>>` block (`agents/database_handler/prompt.md`).  The
**Context Pruner** is NOT one of the prompted chain agents
(`agents/shared/context_pruner.py`, no `prompt.md`), so it has no
blade-sections info today — open question whether it needs any.


### F45. Refine blade-section parameters in place (no new attempt per tweak)

**Status.** PARTIALLY ADDRESSED — the RENDER-reuse half is now done for BOTH
tools (`render_and_check_mesh` reuses existing renders in place as of
2026-07-13, commit `cf4b900` — see F48; the sections re-render already did via
F43).  The remaining DEFERRED part is only relaxing the append-only
`parameters.json` (a parameter tweak still opens a new attempt).  Deferred
follow-up from the F43 sections-first fast-path fix (2026-06-18).

The fast-path fix makes a **re-render** of an attempt's sections reuse that
attempt (DCOI → Tool Caller via `call_tool_caller`, no new attempt).  But a
**parameter change** still opens a new attempt, because `parameters.json` is
append-only (the DC Input Creator writes it once per attempt) — so a fast loop
that keeps *tweaking* the section parameters still spawns one attempt per tweak.

Decided (2026-06-18) to keep that for now — a parameter change is treated as a
"real design change".  The deferred option: relax the append-only
`parameters.json` model so an attempt can be refined IN PLACE across iterations
(overwrite + re-render in the same folder), so the cheap section-refinement
loop doesn't accumulate attempts.  Weigh against losing the per-attempt
parameter history.


### F46. Cross-schema-version session search — DEFERRED, blocked on T1

**Status.** DEFERRED — recorded 2026-07-07 at `impellerHeight` removal,
rescoped the same day after checking `database_search`.  NOT real work now;
becomes real only when **T1** (parameter-value filtering) is built.

**Finding (why deferred).** `database_search` does NOT search, filter, or
rank by any design parameter today.  It is pure semantic / vector-embedding
similarity (pgvector cosine distance over the RAG corpus); its filters are a
closed set of 11 metadata metafilters (`_METAFILTER_SPEC`, ~L581-596) on
sessions / dc_attempts / chunks columns — **none is a design parameter**.
Parameters are STORED (`dc_attempts.parameters_json` + the
`dc_attempt_parameters` table) but not embedded, not filtered, not ranked.
Parameter-value filters (e.g. `bladeCount>=5`) are the deferred **T1**
feature (`database_search.py` docstring ~L569: "the dc_attempt_parameters
JOIN is not built").

So the `impellerHeight` removal causes **no search problem today**: a V1
(17-param) vs V2 (16-param) attempt is invisible to the ranking path — no
code path throws or mis-ranks on the param-count difference.  The one
genuinely cross-version feature, the **`schema_version` metafilter**
(~L586, supports `=`/`>=`/… so an agent can scope a search to V1-only or
V2-only), already works for both versions with NO change.

**What to do WHEN T1 is built (not before).** Make parameter-value
filtering over `dc_attempt_parameters` schema_version-aware: (a) query old
attempts under their OWN schema's parameter set (design invariant 7,
per-attempt schema); (b) a filter on `impellerHeight` must gracefully
exclude / NULL-handle V2 attempts that lack it; (c) treat ring height as
DERIVED, NOT comparable across versions (V1 = user input in [4,10]; V2 =
auto-fit, can exceed 10) — never a match / ranking signal.

**Dependency.** Blocked on T1 (`database_search.py` ~L569).  Do not
schedule standalone.


### F52. Sessions Queue overnight runner: SOLID token / rate / context-limit resilience

**Status.** NOT STARTED — planned. **Relatively HIGH importance.** Do this AFTER the
current Sessions Queue milestones (M3 + the other night-time-running changes already
planned). The overnight runner is unattended, so an LLM token/rate/context limit MUST NOT
halt the night or silently waste runs — the handling has to be solid.

**Problem.** During an unattended overnight queue an agent's LLM call can hit a limit:
(a) **rate limit** (HTTP 429 — RPM or, more likely, per-minute TPM), (b) **context-length**
(HTTP 400 "context length exceeded" — a single request over the model's window), or
(c) an **account quota** (daily/monthly cap). Any of these can currently DISCARD a run (or,
worst case, stall it) instead of recovering.

**Current state (grounded — what already exists).**
  * `agents/shared/llm_retry.py::invoke_with_retry` (every agent's LLM call goes through it)
    retries **429 `RateLimitError`** up to `MAX_ATTEMPTS=5`, sleeping the `Retry-After` header
    or `DEFAULT_RATE_LIMIT_BACKOFF_S=60s`; and **connection/timeout** errors with exponential
    back-off (2→30 s). On exhaustion it **re-raises**. It does NOT catch context-length
    400s (correctly — they aren't transient) and does NOT catch account-quota errors.
  * The process-global `InMemoryRateLimiter` (`llm_provider.py`, `RATE_LIMIT_REQUESTS_PER_SECOND=1`)
    smooths **RPM only, not TPM** — a heavy queue can still overrun the token/min budget.
  * Context-length is handled ENTIRELY by the Context Pruner (three-tier + pre-scan; see
    `agents/shared/context_pruner.py`, F23, F35). Its "all tiers exhausted → proceed anyway"
    path can still send an over-window request → 400.
  * **The runner gap:** `web_app.py::_drive_one_turn` catches ANY turn exception and returns
    None → `_run_queue_in_background` marks the run `failed` (terminal) and moves on. So a
    *sustained* rate limit (past the 5 call-level retries) or a context-400 **DISCARDS the run**
    — it is treated identically to a genuine failure, never retried. An account-quota hit would
    burn the whole night marking every run failed.

**Ways to counter (ranked; the fix should combine several for solidity).**
  1. **Classify the failure in the runner.** Detect 429 / `RateLimitError` and context-length
     (400 / "context length") in the caught exception; treat them as RETRYABLE, distinct from a
     real failure. (Requires surfacing the exception type through `dispatch_turn` → `_drive_one_turn`,
     which today only returns a `TurnResult` or None.)
  2. **Run-level retry with long back-off / pause — do NOT discard.** When the call-level retries
     are exhausted on a limit error, retry the whole RUN after a longer sleep (TPM windows can need
     minutes; a daily quota needs hours). A "pause the queue and retry later" loop so the queue
     survives rather than losing the run.
  3. **Circuit breaker.** If N consecutive runs fail on limit errors (account-level quota), PAUSE the
     whole queue (long sleep + a cheap periodic probe call) instead of running through the night
     failing everything; resume when a probe succeeds. Surface a queue-level "paused (rate limit)"
     state in the runner log + manifest.
  4. **TPM-aware pacing.** Add a token-rate pace (or a conservative inter-turn/inter-run delay) on top
     of the RPM limiter, ideally self-throttling from the provider's `x-ratelimit-remaining-tokens`
     headers, so a heavy queue does not overrun TPM in the first place.
  5. **Context-length hardening (belt).** Guarantee no single request can 400 on length: audit the
     pruner's all-tiers-exhausted path (F23/F35), add a last-resort hard truncation, and/or a
     per-agent preflight (count tokens vs the model window before invoke; force-prune/truncate if over).
  6. **Per-run token budget guard.** Cap tokens a single run may consume so a runaway continue/refine
     loop is flagged `needs_review` rather than retry-storming.
  7. **Observability.** Record every limit event on the run (`note` = "rate-limited, paused Ns,
     retried" / "context-truncated") and in the runner log, so the morning review sees exactly what
     happened.

**Where the pieces live.** `agents/shared/llm_retry.py` (call-level retry), `llm_provider.py`
`_RATE_LIMITER` + `RATE_LIMIT_REQUESTS_PER_SECOND` (pace), `agents/shared/context_pruner.py` +
`model_windows.py` (window), `web_app.py::_drive_one_turn` / `_run_queue_in_background` (runner-level
classify + retry + pause + circuit-breaker), `agents/dispatch.py` (surface the exception type out of
`dispatch_turn`). Related: F23, F35, O2, O3; the Sessions Queue runner (`web_app.py`
`_run_queue_in_background`).

---

### F53. Prompt caching: port conversation-history caching to the 3-agent system

**Status.** PARTLY DONE. The 8-agent system and the **5-agent topology (Conductor +
Creator) now have it**; the **3-agent (Architect) topology does not** — it is not built
yet, so this is a reminder to wire it in at build time rather than retrofit it. Whoever builds or next touches those topologies must port it,
or they will silently run at full input-token price while the 8-agent system runs at ~0.1x
on its cached prefix — which would also make any Test-2 (agent-count) cost comparison
meaningless, since the configurations would differ in caching as well as in agent count.

**What has to be ported.** Each in-session agent of the reduced topology must:

1. import `history_cache_control` alongside `make_system_message` from
   `agents.shared.llm_provider`;
2. pass `cache_control=history_cache_control(self.provider)` to its
   `invoke_with_retry(...)` call(s).

Nothing else — `make_system_message` already applies the explicit system-prompt
breakpoint, and both markers derive their ttl from the single `PROMPT_CACHE_TTL`
setting, so they cannot diverge (a mismatched ttl is a 400 from Anthropic).

**The Database Handler now HAS it** (2026-08-04, all 5 sites) — it was previously excluded
by omission. It uses the same helpers with `phase="save"`, which reads the separate
`PROMPT_CACHE_SCOPE_SAVE` / `PROMPT_CACHE_TTL_SAVE` pair (§30). A reduced-topology agent
still passes no phase, i.e. the `"session"` default.

**Where.** `agents/<each reduced-topology agent>/*.py`. Reference implementation: the 8
in-session agents on the current topology. Mechanics + measured rationale:
`extra_utilities/docs/reference/design_prompt_caching.md`. Settings: `workflow_settings/settings.py` §29.
Related: the agent-count work in `extra_utilities/docs/reference/design_agent_count_variants.md` and
`agent_count_variants_build_tracker.md`.

---

### F54. Verify save-phase prompt caching on a REAL session save

**Status.** OPEN — code shipped 2026-08-04, offline + live smoke tests pass, but the
Database Handler has never run with caching enabled against a real saved session.

**Why it needs a live check.** `smoke_test_prompt_cache.py` proves the mechanism and
proves a re-seeded buffer keeps a stable prefix, but it builds a *synthetic* base
history. A real save differs in the ways that could break the win:

1. **Real agent histories** may contain content whose serialisation is not stable
   across the `list()` copy (tool-call blocks, image placeholders left by the strip,
   provider-specific metadata). Any instability shows up as a cache read that shrinks
   field over field.
2. **Prefix size.** An agent with a short history may fall under the model's minimum
   cacheable prefix (1024 tokens on Opus 4.8, **4096** on Haiku 4.5 / Opus 4.6), in
   which case caching is silently skipped for that agent — no error, no saving.
3. **The 5m TTL assumption** — that one agent's `SCHEDULE` block runs fast enough to
   stay warm — is reasoning, not measurement.

**How to check.** Run one ordinary session to completion and let it save (this is
**not** a Sessions Queue run — plain single-session save). Then in the session log:

- filter for `[DH-decide]`, `[DH-formulate]`, `[DH-compress]`, `[DH<-<agent>]`;
- confirm `billed=` on the `DH<-<agent>` lines drops sharply after each agent's first
  field, and that the cache-read figure is roughly CONSTANT across that agent's
  remaining fields (a shrinking read = prefix drift, the failure mode in point 1);
- confirm the UII (8 fields) and Planner (6 fields) show the largest savings, since
  they repeat the most;
- note any agent showing **zero** cache reads throughout — check its history size
  against the model's minimum cacheable prefix before assuming a bug.

**Then decide the TTL.** If any agent's block spans >5 minutes and shows a re-write of
its full prefix mid-block, flip `PROMPT_CACHE_TTL_SAVE` to `"1h"`. That setting is
independent of the session's, so it can be changed without re-measuring the session.

**Where.** `workflow_settings/settings.py` §30; `agents/database_handler/database_handler.py`
(5 call sites); `agents/shared/token_usage.py` (`_phase_for`, `_configured_ttl`).
Mechanics: `extra_utilities/docs/reference/design_prompt_caching.md` § "The session-save phase".

---

### F55. The briefing anchor: cache the DH's re-seeded base history ACROSS fields

**Status.** OPEN — this is the larger half of the save-phase saving, and it is NOT
captured by the 2026-08-04 change. **Measured**, not suspected.

**The gap.** `smoke_test_prompt_cache.py`'s `run_save_phase()` measured three re-seeded
fields on `claude-opus-4-8`:

```
field 1  write=558  read=8435      <- 8435 = the SYSTEM PROMPT alone
field 2  write=558  read=8435      <- flat, not growing
field 3  write=558  read=8435
```

The ~520-token base history is re-written on **every** field. Only two breakpoints
exist: the explicit one on the system prompt, and the top-level automatic one, which
lands at the END of the messages. Field 1 writes an entry for
`system + base + question-1`; field 2's prefix diverges at that final block, so it
cannot match — and there is no breakpoint at `system + base` to fall back to.

**Why it matters.** Within a field, round 1 writes the base at 1.25x and rounds 2+ read
it back; only each field's FIRST round re-pays. With `F` fields and `R` rounds per
field: no caching `F × R × H`; today `F × (1.25H + (R-1) × 0.1H)`; with the anchor
`1.25H + (F × R - 1) × 0.1H`. For the UII (`F = 8`, `R = 2`) that is `16H` → `10.8H`
today (~32% saved) → `2.75H` with the anchor (~83% saved). So the shipped change is a
real win and this item claims the remaining two thirds. Real histories are far larger
than the smoke test's 520 tokens, so the absolute gap is large.

**Break-even note.** A field resolved in a SINGLE round costs 25% more than no caching
(one 1.25x write, no offsetting read). If a real save turns out to be dominated by
one-round fields, measure before assuming the current state is net positive for the
agent side — F54 produces exactly that number.

**What is unaffected.** The DH's own `self.messages` grows monotonically and already
caches fully — the measured `system+history` pattern (`read` 8435 → 8464 → 8522). Do
not touch those 4 sites.

**The fix, and why it is not a one-liner.** Place a third breakpoint on the LAST message
of the re-seeded base, so `system + base` becomes a matchable entry. Constraints:

1. **Never mutate in place.** `convo_buffer = list(agent_messages)` is a SHALLOW copy —
   marking a message object would corrupt live session state shared with the agent.
   Mark a COPY of the last base message.
2. **Content coercion.** Marking requires block-form content. Must survive whatever
   the last base message actually is: an `AIMessage` carrying `tool_calls`, a message
   whose content is already a block list, or image placeholders left by the strip.
   Verify how `langchain_anthropic` serialises each of those forms BEFORE changing any.
3. **Breakpoint budget.** explicit system (1) + top-level automatic (2) + anchor (1)
   = **4**, the documented maximum. No slot is left for a fifth.
4. Consider whether dropping the top-level automatic on the agent side and hand-placing
   two explicit markers (system + anchor) is simpler — within-field Q/A tails are small,
   so little is lost, and it frees 2 slots.

**How to confirm the fix.** Re-run the smoke test: `run_save_phase()` currently WARNs
with a flat read. Success is field 2's read exceeding field 1's by roughly the base
size, with the per-field write collapsing to the question alone. The check is already
written — only the verdict changes.

**Where.** `agents/database_handler/database_handler.py` `_ask_agent` (~line 2733);
`agents/shared/llm_provider.py` (a new marker helper alongside `system_cache_control`).
Mechanics: `extra_utilities/docs/reference/design_prompt_caching.md` § "The session-save phase".
Related: F54 (live verification on a real save).

### F56. `SYSTEM_TOPOLOGY` is read fresh mid-turn, so a run in flight is not pinned



**Where.** `agents/shared/topology.py` (`topology()` / `hub_key()` /

`hub_display()`), consumed at `agents/dispatch.py:292` + `:298`,

`agents/shared/routing_tools.py:267` + `:284`, and

`agents/shared/routing.py` (`natural_pipeline`, `_authorisation_sources`,

`routing_instructions`).



**What.** `topology.py` reads `SYSTEM_TOPOLOGY` FRESH on every call and

deliberately never captures it at import — correct for prompt assembly,

because `web_app._build_session` reloads the settings module in place and

the Sessions Queue switches topology between runs inside one process.



But the same fresh read also happens DURING a live turn. `dispatch_turn`

resolves the start agent with `hub_key()` after the Receptionist has

already run; `build_routing_tool._invoke` calls `hub_key()` on every

hand-off. The hub object itself, and every agent's system prompt, were

built once at session start.



So if `SYSTEM_TOPOLOGY` changes on disk while a turn is in flight, that

turn's routing starts resolving against the NEW topology while the agents

it is driving belong to the OLD one: hops address an agent key the live

hub does not hold (`"Dispatch error: unknown agent key"`), and the

chain-log / trace suppression keyed on `target_key == hub_key()` silently

picks the wrong branch.



`workflow_settings/settings.py` §27 states the intended contract

explicitly — *"Changing this takes effect on the NEXT session; a run

already in flight keeps the topology it started with"* — and nothing

enforces it today.



**Why it has not bitten.** The only writer that switches topology between

runs is the Sessions Queue, which does so while no turn is running. The

window is real but narrow: a Workflow-Settings save during an active turn.



**Proper fix.** Carry the topology on `Session` the way

`dcoi_comparison_mode` is (set once in `web_app._build_session`, read by

the hub/routing helpers), so a live turn is pinned to the topology it

started with by construction rather than by timing. This is also decision

T1/T2 of `extra_utilities/docs/active/topology_shared_touchpoints.md` §G — the Sessions

Queue's per-run topology field needs a per-session carrier anyway, so the

two land naturally together.



**Status.** Open. Raised 2026-08-04 during an architecture read; not

observed in a run.





### F57. The two hubs differ in chain access, which confounds a 7-vs-5 comparison



**Where.** `workflow_settings/settings.py` §5 (`CHAIN_ACCESS`, default

`True`), `agents/orchestrator/orchestrator.py` (`_CHAIN_ACCESS_ON` /

`_CHAIN_ACCESS_OFF` + the block `dispatch` prepends), and

`agents/conductor/conductor.py:163` + `:470` (no such block, by design).



**What.** The 7-agent Orchestrator ships with chain access ON: every

inter-agent exchange that happened while it was waiting is prepended to

its next incoming message. The 5-agent Conductor has no chain-access block

at all — it was dropped from its prompt on purpose, so it pulls history on

demand via `read_agent_history` (the Planner's model) instead of being fed

it.



Both choices are defensible on their own. The problem is comparing them:

a 7-vs-5 benchmark run then differs in TWO variables at once — how many

agents there are, AND how much of the chain the hub sees — so a difference

in quality or token cost cannot be attributed to agent count alone, which

is the whole point of the Test-2 comparison.



**Options.** (a) Give the Conductor the chain-access block, so both hubs

see the same traffic. (b) Run the 7-agent with `CHAIN_ACCESS=False` for

comparison runs, so both hubs pull on demand — cheapest, no prompt change

to either topology. (c) Keep the asymmetry and treat "the hub pulls rather

than is pushed" as part of what the 5-agent variant IS — in which case say

so explicitly wherever the comparison is reported, so the result is not

read as a pure agent-count effect.



**Status.** Open. Raised 2026-08-04 during an architecture read. Decide

before the first 7-vs-5 comparison run, not after.




### F58. A 5-agent save loses 17 of the 36 default schedule rows, three different ways



**Where.** `agents/database_handler/database_handler.py` `populate_database`

(the agent-resolution guard, the sub-row collector and the `parent_id`

guard), `workflow_settings/dh_schedule.py` `AGENT_KEYS`, and the two hub

registries `agents/orchestrator/orchestrator.py` / `agents/conductor/conductor.py`.



**What.** `dh_schedule.AGENT_KEYS` is a deliberate SUPERSET across topologies —

it has to be, or a schedule naming the Conductor could not be saved at all. But

the DH resolves each row's agent against `hub._agents_by_key`, which holds only

the agents the ACTIVE topology actually built. Under `SYSTEM_TOPOLOGY = 5` the

default 36-row schedule names four agents that no longer exist (planner ×7,

dc_input_creator ×3, dc_input_inspector ×3, orchestrator ×1).



Verified breakdown for a 5-agent run on default settings — **17 rows yield

nothing, but only 12 leave any trace**:



* **12 rows** hit the agent-resolution guard and produce an ERROR `.txt` plus an

  `is_error=True` chunks row. Visible, if ugly.

* **2 rows** (`Bad attempt Suggested solution`, `Useful Attempt planner

  observations`) are Planner SUB-rows of DCOI parents. The DCOI exists in the

  5-agent topology, so their parent runs normally and consumes them inside the

  attempt-major loop, where an unresolvable sub-agent hits a bare `continue`

  with a log warning — **no error entry, no chunks row, nothing on disk.**

* **3 rows** are collateral. Row 20 (`Final Design Output`) is a PLANNER

  identifying row whose three children all name the DC Output Inspector — an

  agent the Conductor does have. But the parent errors out and does

  `i += 1; continue`, so the sub-row collector never runs, and those three

  perfectly-valid children fall through to the main loop where the

  `if parent_id is not None:` guard — which sits ABOVE agent resolution —

  drops them silently.



So one unresolvable PARENT silently costs every child under it, whatever agent

those children name.



**A topology-independent hole in the same area.** Neither hub registers

`database_handler` or `context_pruner`, yet `dh_schedule.py` offers both in the

editor's agent dropdown. A row naming either takes the error path in EVERY

topology, 7-agent included.



**Why it matters now.** This is not cosmetic: it silently halves the corpus a

5-agent session contributes, and the rows it drops are not a random sample —

they are every planning and parameter-authoring question. Any Test-2

(agent-count) comparison drawn from saved sessions would be comparing a full

7-agent corpus against a mutilated 5-agent one.



**Options, none chosen yet.**



1. **Map retired agents onto their merged successor** at save time —

   planner/orchestrator → conductor, dc_input_creator/dc_input_inspector →

   creator. One schedule keeps working across topologies. Needs a per-row

   judgement about whether the merged agent can answer that question

   meaningfully.

2. **Make the schedule topology-aware** — a per-topology file, or a per-row

   topology filter, so a run only asks what its agents can answer. Cleanest

   semantically, most work, two question sets to maintain.

3. **At minimum, make the failure uniform and loud**: the three dispositions

   above (error entry / silent continue / silent parent-cascade drop) should be

   one disposition, and a save whose schedule names agents the active topology

   does not build should say so up front rather than 12 times in the middle.



**Status.** Open, logged 2026-08-04 from a verified multi-agent audit of the DH

save path (run `wf_ae8569ed-087`). Owner's call: log now, decide later.


### F59. Six verified defects in the DH save path (from the 2026-08-04 audit)

Found by a 23-agent audit of the save path (run `wf_ae8569ed-087`), each
adversarially verified against the code.  Grouped into one entry because they
share a cause — the save path trusts its inputs and reports its failures at
INFO — not because they must be fixed together.  **None of these is fixed by
the DH-batching work**; the batching design fixes a different set (the
free-text SAVE parsing layer).  Ordered worst-first.

**1. Slug collisions silently overwrite a saved answer.**  `dh_schedule._validate`
guarantees `name` is globally unique, but compares RAW STRIPPED STRINGS, while
the DH derives the filename via `_slugify`, which lowercases, strips a leading
parenthetical, collapses punctuation runs to `_` and truncates at 80 chars.  So
`Bad Attempt` / `bad attempt`, and `(Not yet implemented) Plan` / `Plan`, both
pass validation and then write to the SAME `.txt`.  `_entry_path` has no
existence check and `_write_entry` writes unconditionally, so the second write
silently replaces the first, sidecar included.  A third divergent slug
implementation in the editor UI means the filename hint the user sees is not the
filename the DH writes, so the UI cannot warn either.  *Fix: validate on the
slug, not the name — or derive the filename from the row id.*

**2. The `chunks` UNIQUE constraint is not a backstop, and is asymmetric.**
`UNIQUE (session_id, agent_from, field, attempt_id, item_index, embedding_model)`
with Postgres' default NULLS-DISTINCT semantics.  Session-scoped rows always
carry `attempt_id = NULL`, so a duplicate **inserts twice**; Quantitative rows
also carry `embedding_model = NULL`, same result.  Attempt-scoped Semantic rows
DO collide — and are then discarded as `SKIPPED_UNIQUE` at **INFO** level with
no safety-folder write.  So the same mistake either doubles a row or deletes it
depending on scope, and neither is visible above INFO.  Recorded as intended
behaviour in W28, but it means the database cannot be relied on to catch a
mapping error upstream.

**3. A child interview that raises leaves NO artefact at all.**  In the
attempt-major sub-row loop an exception is caught with a log warning and a bare
`continue` — no error `.txt`, no `is_error` chunks row, no placeholder.  This
diverges from the session-scoped path, which writes both.  Hole probability
scales linearly with the number of resolved attempts.

**4. Grandchildren pass validation and are then silently dropped.**  A row whose
`parent_id` points at a row that ITSELF has a `parent_id` satisfies every rule in
`_validate` (its parent exists and is attempt-scoped).  The DH only ever collects
rows whose `parent_id` equals an IDENTIFYING row's id, so a grandchild is never
collected, and the `if parent_id is not None:` guard in the main loop drops it
without a file or a row.  *Fix: reject depth > 1 in `_validate` — the contiguity
pass added 2026-08-04 sits right beside where this check belongs.*

**5. Resolved attempts are uncapped and undeduped.**  `save_attempt_data` accepts
an arbitrary-length list and nothing dedupes it, so `["002", "2"]` normalises to
the same attempt twice and the entire child set runs twice for it, at full LLM
cost.  Nothing caps N either: with N=10 across the default schedule's three
identifying blocks that is 90 child interviews, ~270 LLM calls at the floor.

**6. The only smoke test for schedule iteration is dead.**  It patches the
in-code `SCHEDULE` constant, which `populate_database` no longer reads on the
happy path (it loads `dh_schedule.json` and only falls back to the constant when
that read fails).  The test therefore passes while exercising nothing the DH
actually runs.  Related: when that fallback DOES fire it silently flattens every
attempt-scoped row to session scope, replacing the user's edited structure with a
different 29-row question set.

**Fixed on 2026-08-04, listed here so the audit's record is complete:** sub-row
contiguity is now enforced in `_validate` and repaired in `read_for_dh`;
`read_for_dh` now validates at all (it never did, and it is the only path the DH
reads); the editor's `moveRow` no longer drops a row between a parent and its
first child; and `_AGENT_FACING_TAIL` derives the parameter count from
`PARAMETER_NAMES` instead of claiming "17" when the DC has 16.

**Also removed by the batching work (F33), since it deleted the layer they
lived in:** the sticky `ATTEMPT:` tag; the `by_attempt` fallback that wrote one
attempt's answer into another's file, sidecar and `chunks` row with
`is_error=False`; the markdown-fragile header regex; the positional
re-emit merge in the token-cap pass (now keyed by label, so a count drift
cannot re-assign an answer) and its `max(len, len)` bound that could append an
empty pair and write it as an empty `.txt` plus a database row.

**Item 3 is narrowed, not closed.**  A sub-row whose batch raises now falls
back to a single-row batch, and a row that still will not settle is written as
a SKIP — so the common paths leave an artefact.  The hole survives only if the
FALLBACK call itself raises, which is logged but still writes nothing.

**Status.** Open.

---

### F83. The UII's categorisation rule says "two buckets" but there are three sections

**Status.** OPEN — found 2026-08-05 while writing the UII-scoped DC hard rules.
Low severity, but it leaves one output section with no rule routing anything
into it.  Not in the shrink proposal.

**The gap.** `agents/user_input_inspector/prompt.md:20-31` — the categorisation
rule that governs the whole extraction:

> "Categorise every input you observe (text, paired image notes, image
> annotations) into **one of two buckets**, based purely on the NATURE of the
> data, NOT on whether it matches a configurator parameter:
>   * **QUANTITATIVE.** Anything numerical, OR anything that resolves to a
>     number / can be quantised in some way.
>   * **QUALITATIVE.** Anything that is NOT expressed as numerical data …"

But the output format further down has **three** sections:

* `### 1. QUANTITATIVE INPUTS`      (line 143)
* `### 2. QUALITATIVE DESCRIPTIONS` (line 270)
* `### 3. Design Intent and Functional Requirements` (line 287)

Section 3 is substantial — purpose, performance goals, constraints, aesthetic
preferences, stated **reporting preferences**, and the `PRECISION DEMAND:` line
that the whole precision sections-matching loop depends on (F51 / commit
`cce0276`).  None of it is numerical, so under the stated rule it all
categorises as QUALITATIVE, and nothing directs it to section 3.

**Why it matters.** The rule is emphatic and comes first ("Categorise EVERY
input … into one of two buckets"), so an agent following it literally has a
defensible reason to fold design intent into QUALITATIVE DESCRIPTIONS.  A
`PRECISION DEMAND:` buried in prose under the wrong heading is materially worse
than one on its own line under section 3 — `agents/shared/standing_directives.py`
and the Planner both look for it as a distinct entry.

**The fix.** Add the third bucket to the rule at line 21, e.g.:

```
Categorise every input you observe (text, paired image notes, image
annotations) into one of three buckets, based purely on the NATURE of the
data, NOT on whether it matches a configurator parameter:

  * QUANTITATIVE.  Anything numerical, OR anything that resolves to a
    number / can be quantised in some way.
  * QUALITATIVE.  Descriptive prose, adjectives, comparisons, aesthetic or
    stylistic cues.
  * DESIGN INTENT.  What the user is trying to ACHIEVE rather than what the
    artefact should be — purpose, performance goals, constraints, reporting
    preferences, and any precision / iteration demand.
```

Applies to `agents/5agent/user_input_inspector/prompt_5agents.md` as well if it
carries the same rule — check before editing.

**Why it is not fixed here.** It is a `prompt.md` change, and under the
one-file-at-a-time review model that belongs to the UII prompt's own turn.  It
is recorded now because the UII-scoped `hard_constraints_dc` deliberately does
NOT paper over it: an earlier draft of that fragment enumerated
"quantitative, qualitative or design intent" and would have masked the gap from
inside a hard-constraints fragment — the wrong layer for a routing rule.

**Where.** `agents/user_input_inspector/prompt.md:20-31` (rule), `:143`, `:270`,
`:287` (the three sections).  Related: F82 (also a UII/DCOI prompt gap found by
mapping rather than by a proposed cut).

---

### F84. The generic CLARIFY bullet needs a per-agent patch paragraph in every first-agent fragment

**Status.** OPEN in the shared tree; fixed in the 7-agent REDUCED variant only
(owner's call — section-8-class repairs land in the variant, not in standard).
Found 2026-08-05 while verifying the shrink proposal's routing-duplication claims.

**NOT a contradiction — read this before "fixing" it.**  An earlier analysis of
mine called it a live contradiction and that was wrong; the owner corrected it.
"Previous agent" legitimately means *whoever handed you this work*, and the UII
does have a caller (the Orchestrator) with `call_orchestrator` in its tool set.

**The actual shape.**  `agents/shared/routing.py::routing_instructions` guards
only the POSITION line on `prev_agent` (lines 190-196).  The
`### How to decide where to route` block below it is appended unconditionally,
including:

    - If you cannot do your job because the upstream message is ambiguous,
      missing data, or contains an error that the previous agent can fix,
      route to the previous agent with a clear clarification request (CLARIFY).

For an agent with `prev_agent=None` that bullet points at nobody — so the
per-agent fragment has to patch it afterwards.
`agents/shared/prompt_fragments/routing_user_input_inspector_uii_first.md`
closes with exactly that patch:

    You are the first agent in the natural flow; there is no "previous"
    agent in the chain for you to CLARIFY back to.  Anything that would
    otherwise be a "back" routes to the Orchestrator instead.

It works.  The cost is structural: EVERY first-agent fragment, in every
topology, must carry a paragraph correcting generated text — and the generator
already knows `prev_agent is None`, so it could say the right thing itself.
Under `PLANNER_FIRST=True` the Planner becomes first and needs the same patch;
the 5-agent UII needs it; a 3-agent first agent will need it.

**The fix (already applied in the reduced variant).**  Phrase the bullet from
the generator, defining "previous" as the sender rather than a pipeline
position:

* `prev_agent` set  — "route back to the agent that handed you this work —
  normally the **<prev_agent>** — with a clear clarification request (CLARIFY)."
* `prev_agent` None — "route back to the agent that handed you this work — for
  you that is the <hub> — with a clear clarification request (CLARIFY)."

The fragment's patch paragraph then becomes redundant and can be deleted, which
is what makes the proposal's `UII-44` cut safe rather than lossy.

**To port it to the shared tree** apply the same change to
`agents/shared/routing.py` and drop the closing paragraph from every
`routing_*_uii_first.md` / first-agent fragment.  Check each fragment
individually — some may carry other content in the same paragraph.

**Where.** `agents/shared/routing.py:198-215` (the unconditional block),
`:190-196` (the guard that exists);
`agents/shared/prompt_fragments/routing_user_input_inspector_uii_first.md:9-11`.
Reduced-variant fork: `reduced7/agents/shared/routing.py`.

---

### F89. The STANDARD hub prompt names retrieval tools outside the <<HAS_DBA>> gate

**Status.** OPEN in the standard tree; already fixed in the 7-agent REDUCED
fork (defect B6 in `extra_utilities/fork_manifest.json`).  Surfaced 2026-08-21
by the per-tool DBa invariant check, which the manual sweep had missed.

**Where.** `agents/orchestrator/prompt.md:176-177`, inside the worked example
for relaying a user mandate:

    Call ``database_search`` (and/or ``retrieve_user_inputs`` /
    ``retrieve_attempt``) before finalising your output.

**Why it is wrong.**  That sentence sits OUTSIDE the
`<<HAS_DBA>>...<</HAS_DBA>>` region, so it survives even when the hub holds
no database tool at all — which is its state in the shipped `"7"` profile
(`orchestrator` is `false` for all three tools) and under `RAG_ENABLED=False`.
It also scripts the hub to name specific tools in the mouths of DOWNSTREAM
agents, which may hold a different subset again now that distribution is
per (profile, agent, tool).

**The fix**, when the standard tree is next worked on: the reduced fork simply
DELETED the tool names from the example, leaving the mandate-relay principle
intact.  Porting that is a one-hunk change — but note
`agents/orchestrator/prompt.md` is a fork ORIGIN, so it needs the usual
`origin_commit` bump in `fork_manifest.json` afterwards.

**Why it is not fixed now.**  The owner has set the 7-agent standard and
5-agent systems aside; the reduced system is the one being built.
`smoke_test_database_access.py` case 13 therefore HARD-asserts the invariant
for `reduced` and, for `standard`, asserts only that no violation appears
BEYOND this known pair — so a NEW standard-tree violation still fails the
test, while this one does not mask it.

### F88. Giving the 5-agent / 3-agent / any future reduced system its own DBa distribution is a DATA change, not a code change

**Status.** OPEN by design — nothing is broken; this records where the work
goes when those systems are designed.  Written 2026-08-20 alongside the
per-tool DBa distribution.

**The shape.**  `workflow_settings/database_access.json` is keyed by SETTINGS
PROFILE, then agent, then tool:

    {
      "7":         { "planner": {"search": true, "user_inputs": true, "attempt": true}, ... },
      "7-reduced": { "planner": {"search": true, "user_inputs": false, "attempt": false}, ... }
    }

The profile key is `"<topology>"` for the standard prompts and
`"<topology>-<variant>"` otherwise — e.g. `"7"`, `"7-reduced"`.

**Only profiles someone actually DECIDED are in the file.**  `"5"` and `"3"`
are deliberately ABSENT.  A missing profile falls back to the in-code default
(every tool on for every agent), which is exactly how those systems behave
today, so nothing changes for them until somebody decides otherwise.  This was
a conscious choice: writing rows for them would have recorded an inherited
DEFAULT as though it were a DECISION, and six months later nobody could tell
the two apart.

**So when you design database access for the 5-agent system, the 3-agent
system, or a future reduced variant of either: ADD ITS ROW.  That is the whole
change.**  No migration, no code, no new smoke test — the resolver, the
binding helper, the prompt-slot blanking and the admin UI are all already
profile-agnostic.  A new key simply starts resolving.

**The one thing to get right** is the key itself: it must match what
`database_access.profile_key()` computes from `SYSTEM_TOPOLOGY` +
`PROMPT_VARIANT`.  A typo'd key does NOT error — it silently falls back to the
all-on default, which looks like "the setting did nothing".  If a distribution
seems to be ignored, check the key spelling FIRST.

### F85. The prompt sections describing the RAG tools are stale after the retrieval rework

**Status.** OPEN. Raised by the owner 2026-08-20, during the RAG tool
customization (steps 2a / 2b / 4b).

**Why it matters.** The tools changed shape; the prompts that teach them did
not.  A prompt that describes a parameter the schema no longer has, or a
behaviour the code no longer performs, is worse than no guidance: the agent
reasons from it and the contradiction is invisible at runtime.

**What actually changed underneath the prompts.**

* `retrieve_attempt` and `retrieve_user_inputs` no longer ATTACH anything.
  Both now materialise artefacts under `attempts/_retrieved/<id>/` and
  `inputs/_retrieved/<sid>/` respectively, print the local paths, and leave
  all viewing to `view_images`.
* `images_flag` is gone from BOTH tools' schemas.
* `extract_text` is gone from `retrieve_user_inputs`.
* `retrieve_user_inputs` now prints the UII's `extracted_inputs.txt`, falling
  back to raw `queries.txt` only for sessions archived before extractions
  were saved to R2.
* Every retrieved image is reported with its path whether or not it has a
  `_note.txt`.

**Known-stale sites found on 2026-08-20** (call forms, whitespace-normalised
so line wraps do not hide them):

    DC_prompt_fragments/tools_config/database_search.md
    DC_prompt_fragments/tools_config/database_search_dc_input_inspector.md
    DC_prompt_fragments/tools_config/database_search_dc_output_inspector.md
    DC_prompt_fragments/tools_config/database_search_receptionist.md
    DC_prompt_fragments/tools_config/database_search_user_input_inspector.md
    DC_prompt_fragments/tools_config/retrieve_user_inputs.md
    agents/5agent/tools_config/database_search_creator_5agents.md
    agents/5agent/receptionist/prompt_5agents.md

Five of those still spell a call as `retrieve_user_inputs(session_ids=[<sid>],
images_flag=True)`.  BOTH halves are wrong: the argument is `sessions_ID_list`
(the dispatcher reads exactly that key and errors out otherwise), and
`images_flag` no longer exists.  `retrieve_user_inputs.md` is the tool's own
fragment and still describes the attach behaviour end to end.

**Do not just delete the mentions.**  Per the shared-fragment rule, a variant
removes text by not referencing it or via an override file — never by deleting
a fragment the 5-/3-agent topologies also read.

**Also re-read, not just grep.**  The count above is of explicit CALL FORMS.
Prose describing these tools ("attaches the images", "the notes are returned
for every image") is spread across the 7-agent, 5-agent and reduced trees and
will not show up in a signature grep.

### F60. Duplications in the assembled prompts that the shrink proposal does not target

**Status.** OPEN — evidence-backed, no fix attempted.  Found 2026-08-05 by a
13-agent adversarial verification of the proposal's routing-duplication claims
(~968k tokens).  Recorded because re-deriving it is expensive; see
`extra_utilities/prompt_efficiency/UII_CUT_VERDICTS.md` for the per-cut detail.

Four duplications, none of which any of the 349 cuts touches:

1. **"natural next step" appears 3x, not 2.**  The generated position line
   ("- Your natural next in line is: **Planner**."), the per-agent fragment
   ("This is the natural next step in the pipeline."), and the agent's own
   `prompt.md` ("this is the natural\nnext step").  The third splits across a
   newline, which is why a flat substring search misses it — and it is the most
   cuttable text in the whole forwarding section.  `UII-44` targets only the
   fragment copy.

2. **The generated routing block duplicates ITSELF.**  The mandatory-routing
   rule is asserted twice inside `routing.py::routing_instructions`: "Every
   response that ends your turn MUST invoke exactly one of the routing tools
   listed above." and, three paragraphs later, "Do NOT substitute the tool call
   with free-form prose that says \"routing to X\".  In the same response where
   you finish your work, invoke the tool."  Fixing it in the generator removes a
   restatement from all SIX chain agents at once — the single highest-leverage
   edit found, and no cut proposes it.

3. **The per-agent fragment restates the generator by construction.**  See F84:
   the fragment's closing paragraph restates the position line the generator
   already emits whenever `prev_agent` is None.

4. **"ESCALATE to the <hub>" appears 4x** across the assembled UII prompt,
   outside any cut cluster.  `UII-40`'s rationale assumes the generic bullet is
   the only copy naming the target; it is not.

**Note on measuring these.** Count against the ASSEMBLED prompt (prompt.md +
spliced fragments + the runtime `{routing_instructions}` block), not against
`prompt.md` alone — the routing block is ~4,700 chars and sits 90% of the way
in, so anything measured without it misses roughly a tenth of the text and all
of the generated duplication.

---

### F61. `_authorisation_sources()` is topology-gated — a trap for any replacement that names the Planner

**Status.** OPEN as a documented trap; no defect in the current code.  Found
2026-08-05 while verifying the shrink proposal's `UII-40`.

**The trap.** `agents/shared/routing.py:53-70` builds the authorisation-grantor
list per topology:

* topology 7 — "authorisations come from the user (relayed by the Receptionist
  -> <hub>), from the **Planner** (relayed by the <hub>), or from the <hub>
  itself."
* topology 5 or 3 — the Planner clause is DROPPED, because the Conductor
  absorbs the Planner and no such agent exists.

Several proposed replacement texts inline the 7-agent wording as a literal
string.  Any prompt that hardcodes "the Planner" as an authorisation source will
name a nonexistent agent under topologies 5 and 3 — the same class of defect as
the `<<DCII_ONLY>>` guard losses that section 9 refuted eight Orchestrator cuts
for.

**Rule.** When a replacement needs to state who can authorise, either call
`_authorisation_sources(hub)` or omit the grantor list.  Never inline it.

**Where.** `agents/shared/routing.py:53-70`; the risk lands in any cut whose
replacement text quotes the permission paragraph, `UII-40` most directly.

---

### F62. The UII prompt teaches "never invent a parameter" using an invented parameter

**Status.** OPEN in the standard 7-agent and the 5-agent prompts.  FIXED in the
7-agent reduced variant (both instances).  Found 2026-08-06 while applying the
shrink proposal's UII cuts; not in the proposal, though one of its cuts happens
to correct one instance in passing.

**The defect.** `outerRadius` is NOT one of the 16 configurator parameters.  The
canonical list is `bladeCount, impellerRadius, impellerThickness,
innerThickness, innerMaxPos, innerCamber, innerChord, innerAngle, middlePos,
middleChord, middleAngle, outerThickness, outerMaxPos, outerCamber, outerChord,
outerAngle` — there is no `outerRadius`.  Yet the UII prompt uses it in BOTH of
its worked examples:

| file | line | text |
|---|---|---|
| `agents/user_input_inspector/prompt.md` | 212 | `- outerRadius: 160 mm — OUT OF RANGE (allowed [10; 140])` |
| `agents/user_input_inspector/prompt.md` | 247 | `- outerRadius: ~140 mm — SOFT TARGET (goal: match the sketched blade …)` |
| `agents/5agent/user_input_inspector/prompt_5agents.md` | 218 | same OUT OF RANGE line |
| `agents/5agent/user_input_inspector/prompt_5agents.md` | 253 | same SOFT TARGET line |

The RANGES are wrong too.  `[10; 140]` is not any parameter's range; the closest
real parameter, `impellerRadius`, is `[60; 80]` mm.  So the SOFT TARGET example's
`~140 mm` is also outside the range of the parameter it is presumably meant to
illustrate.

**Why it matters.** These examples sit a few lines below hard rules the same
prompt carries: "Reject invented parameters (hub_radius, fillet_radius,
tip_clearance, any 'supplemental' value) — they do not exist", and
"$parameter_list" itself.  The prompt demonstrates its output format with
exactly the kind of value it forbids, and an agent copying the shape of a worked
example is doing the reasonable thing.  The OUT OF RANGE example is the worse of
the two: it teaches the agent to compare a value against a range, using a range
that does not exist.

**The fix**, per instance:

```
- impellerRadius: 160 mm — OUT OF RANGE (allowed [60; 80])
- impellerRadius: ~75 mm — SOFT TARGET (goal: match the sketched blade
  shape; keep near 75 mm if free, but vary freely to fit the shape)
```

(160 is kept in the first: it is clearly outside [60; 80], and the number may
echo the Ø160-vs-Ø140 form incident this rule family came from.)

**Where the reduced variant already has it.**
`agents/7agent_reduced/user_input_inspector/prompt_7agents_reduced.md` — the
SOFT TARGET example was corrected as part of cut UII-05, the OUT OF RANGE one
as a standalone fix.  Not ported to the shared tree per the standing decision
that section-8-class repairs land in the variant only.

**Scope — SCANNED, and it is contained.**  Found by eye, so the obvious worry
was more of the same elsewhere.  Scanned every `agents/**/prompt*.md` and
`DC_prompt_fragments/**/*.md` for camelCase identifier-shaped tokens and
compared them against the 77 keys in
`DC_prompt_fragments/dc_config/parameter_keys.txt`.  Result: exactly two
non-canonical tokens in the whole tree —

* `outerRadius` x4 — the four instances tabulated above, and nothing else;
* `camelCase` x2 — the literal word, in `agents/database_handler/prompt.md`
  (false positive).

So no other prompt invents a parameter name.  Fixing the four lines closes it
entirely.

**Worth turning into a check?**  Probably not on its own — a one-off scan found
a bounded problem.  But if a `parameter_keys.txt`-versus-prompts assertion is
ever added to the smoke suite, note the two false-positive classes it must
tolerate: prose words that happen to be camelCase, and tool/field names
(`view_images`, `parameters.json`) that are not parameters.

Related: F82 (the DCOI is asked to name parameters it is never shown — same
family, opposite direction).

---

### F63. `middlePos` schema said the opposite of the prompts — fixed in the tool, NOT in the DB seeder

**Status.** Tool schema FIXED 2026-08-06 (shared tree, all topologies).  The DB
seeder and any already-seeded rows are DELIBERATELY LEFT ALONE — owner's call.

**What was wrong.** `tools/generate_mesh/generate_mesh.py` described the
parameter as:

    middlePos: Annotated[float, "Middle-section radial position
                                 (x impellerRadius, dimensionless)"]

That is the formula the prompts explicitly FORBID.  Three sources agree against
it:

* `DC_prompt_fragments/dc_config/modelling_notes.md:5-9` — "radius =
  ``4 + middlePos·(impellerRadius − 4)`` mm — **NOT** ``middlePos ×
  impellerRadius``"
* `DC_prompt_fragments/dc_config/parameters.md:16` — "(fraction of blade span,
  unitless)"
* `web/feg/profiles.js:19` — the code that actually runs:
  `radius: 4.0 + (impellerRadius - 4.0) * t`

The Annotated description is sent to the **Tool Caller on every turn**, and the
Tool Caller is the last agent before geometry generation.  This is the same
misunderstanding that corrupted a test deck once already (fixed in the prompts
and the deck; the tool schema and the DB seeder were missed).

**Why a schema and not a prompt.** A prompt can carry a conditional or be
corrected per agent; a docstring is a plain Python string.  This is the worst
instance of the general finding that in this codebase the SCHEMAS, not the
prompts, are where stale statements accumulate — see the tool-schema audit
summarised in the commit for this fix.

**LEFT ALONE, deliberately:**

* `extra_utilities/db_design/populate_dc_parameter_schemas.py:64` still reads
  `"unit": "x impellerRadius"` / `"...as multiplier of propeller radius"`, in
  the V1 list (V2 derives from V1 by comprehension, so it inherits it).
* Any already-seeded database therefore holds the wrong text for BOTH
  `schema_version` 1 and 2.

Two reasons this is acceptable rather than sloppy.  **Nothing reads
`dc_parameter_schemas` at runtime** — verified by grep; the only references are
the seeder, a row-count in `smoke_test_postgres_pool.py`, and TRUNCATE comments
in `web_app.py`.  No agent has ever seen it.  And the file's header states the
V1 list is immutable history, so correcting it in place would violate the
table's own append-only contract.

**If it ever needs correcting** (e.g. a future feature starts reading the
table), note that re-running the seeder will NOT help: it is
`INSERT ... ON CONFLICT (schema_version, param_name) DO NOTHING`, so it is a
no-op on existing rows.  It needs a manual statement, the same shape the file's
header prescribes for retirements:

```sql
UPDATE dc_parameter_schemas
   SET unit = 'fraction of blade span',
       description = 'Middle blade section position along the blade span from
                      the 4 mm root: radius = 4 + middlePos*(impellerRadius - 4)
                      mm, NOT a multiplier of impellerRadius'
 WHERE param_name = 'middlePos';   -- applies to schema_version 1 AND 2
```

Related: F62 (a prompt example naming a parameter that does not exist — same
family, and both were found by comparing a stated formula against the code).

---

### F64. Six agents hard-code the sender of their incoming hand-off; only the Tool Caller gets it right

**Status.** FIXED for the User Input Inspector 2026-08-06.  OPEN for five other
agents — to be fixed as each one's turn comes up in the prompt-reduction pass.

**The pattern.** Every chain agent's `run()` prepends a sender label to the
incoming message:

| file:line | current text | correct today? |
|---|---|---|
| `agents/tool_caller/tool_caller.py:168` | `"Hand-off from previous agent:"` | **yes — the model to copy** |
| `agents/user_input_inspector/user_input_inspector.py:203` | ~~`"Hand-off from Planner:"`~~ → `"previous agent"` | FIXED |
| `agents/dc_input_creator/dc_input_creator.py:201` | `"Hand-off from User Input Inspector:"` | **NO** — under `PLANNER_FIRST=False` the **Planner** hands to the DCIC |
| `agents/dc_input_inspector/dc_input_inspector.py:167` | `"Hand-off from DC Input Creator:"` | yes, but by luck |
| `agents/dc_output_inspector/dc_output_inspector.py:298` | `"Hand-off from Tool Caller:"` | yes, but by luck |
| `agents/creator/creator.py:231` | `"Hand-off from Conductor:"` | yes, but by luck (5-agent) |
| `agents/designer/designer.py:234` | `"Hand-off from Architect:"` | yes, but by luck (3-agent) |

**Why all six are wrong even when the name is right.**  `agents/shared/routing_tools.py:311`
already does this, for every hop, in one place:

```python
labeled_message = f"[Incoming from: {caller_display}]\n\n{message}"
```

with the comment *"Label the hand-off with its sender so the target agent can
never mis-attribute the content (e.g. mistake a Planner plan for a user
request)."*  So the `run()` prefix is redundant at best.  When it disagrees —
as the UII's did — the agent reads a self-contradicting header:

```
Hand-off from Planner:
[Incoming from: Orchestrator]

<the message>
```

which defeats the exact guard the routing prefix was added to provide.  The
four "correct by luck" cases are correct only because their upstream happens
not to vary with `PLANNER_FIRST`; none of them is correct *by construction*,
and any topology or routing change silently falsifies them.

**The fix**, per agent: replace the hard-coded name with `previous agent`, as
`tool_caller.py:168` already does.  Consider whether the prefix is worth
keeping at all, given `routing_tools.py` supplies a better one unconditionally
— deleting the line entirely may be the cleaner end state.

**Same root cause as F63.** A wrong statement that lives in Python rather than
in a prompt, because Python has no `<<PF_ON>>` mechanism to make it
conditional.  The fleet-wide policy that came out of the tool-schema audit
covers this: *a docstring — or any model-facing Python string — may not name an
agent, a flag, or a count.*

Related: F63 (`middlePos` schema), F62 (invented parameter in a prompt example).

---

### F65. SUGGESTED SECTION SHAPES has no producer in the REDUCED prompt variants

**Status.** OPEN by design — owner's decision 2026-08-07, taken knowingly and
reaffirmed.  Scope: the REDUCED prompts of the 7-, 5- and 3-agent systems.  The
ORIGINAL (standard) prompts of all three topologies KEEP the feature and are
unchanged.  Only the 7-agent reduced variant exists so far; the 5- and 3-agent
reduced equivalents are to come, and must make the same removal to stay
consistent.

**What happened.** The UII-scoped `sketch_handling` deletes the warm-start block
that told the UII to emit a `SUGGESTED SECTION SHAPES` estimate.  The owner's
reason: it over-prescribed how to report sketch inputs, and it was heavily
DC-specific.  The block was Phase 3 of the precision sections-matching work
(F51), but its production record is poor — the two live runs analysed in
`design_precision_sections_match.md` found the DCIC froze levers, and BOTH
competing rewrites in the shrink proposal still emitted `middleThickness` /
`middleCamber` / `middleMaxPos`, none of which exist (`parameter_keys.txt` gives
the middle section only `middlePos`, `middleChord`, `middleAngle`).

**The phantom middle row is FIXED in the shared tree** (2026-08-07), separately
from this decision: the block instructed the UII to estimate thickness / camber
/ max-thickness position "per section (inner / middle / outer)" and printed a
`middle ≈ 14% thick, 4% camber ...` example row, but `middleThickness`,
`middleCamber` and `middleMaxPos` do not exist — `parameter_keys.txt` gives the
middle only `middlePos`, `middleChord`, `middleAngle`, and
`web/feg/profiles.js::interpolateMiddleParams` interpolates its shape from
inner and outer.  That defect had shipped since the block was written and both
competing rewrites in the shrink proposal copied it faithfully.  The standard
prompts, which keep the feature, now ask only for inner and outer.

**Two prompts now reference a block that never arrives** — in the REDUCED
variants only:

* `agents/dc_input_creator/prompt.md:23-26` — Guidelines item 3: "pick a
  reasonable mid-range default — EXCEPT: if QUALITATIVE DESCRIPTIONS carries a
  ``SUGGESTED SECTION SHAPES`` block … SEED the section-shape parameters".  The
  EXCEPT branch simply never fires; the DCIC falls back to mid-range defaults.
  Also `:157`, "your FIRST attempt should already be seeded from it".
* `agents/planner/prompt.md:78` — one of THREE signals for detecting a precision
  job: "a ``PRECISION DEMAND`` line in DESIGN INTENT, a PRECISE SKETCH carrying a
  ``SUGGESTED SECTION SHAPES`` block, or wording like …".  The other two signals
  still work, so precision jobs are still detected.

Neither is a hard failure: one is a fallback, the other is one signal of three.
Both are DEGRADATIONS, and both leave dead text in a prompt.

**To resolve, when the DCIC and Planner get their own reduced prompts:** delete
the `SUGGESTED SECTION SHAPES` clauses from both, so no reduced prompt references
a marker no reduced agent produces.  Do NOT delete them from the shared prompts —
the 5-agent Creator and Conductor still consume the marker and the 5-agent UII
still produces it via the shared `sketch_handling`.

**If instead the warm-start is ever wanted back**, note what the deletion also
removed: the guard "record it in QUALITATIVE DESCRIPTIONS, never in QUANTITATIVE
INPUTS, where an unmarked value is read as user-locked".  `value_states.md:4-5`
defines LOCKED as "a value the user stated plainly there, with no marker", so a
warm start written to QUANTITATIVE INPUTS arrives locked and freezes the very
levers the refine loop moves.  Neither proposal candidate carried that guard;
it was added during this review and would need re-adding.

Related: F62 (a prompt example naming a parameter that does not exist — the
`middle*` rows are the same defect, caught before shipping this time).

---

### F66. Is the DCOI's "don't dictate exact params" bullet a repetition? — check when the DCOI is reduced

**Status.** OPEN — owner's note 2026-08-10, raised while approving the C2a
citation fix.

The citation error is FIXED: `agents/dc_output_inspector/prompt.md:129-131` no
longer cites "the HARD RULES below", a section which contained the OPPOSITE rule.
What was NOT decided is whether the bullet's *content* already reaches the DCOI
from elsewhere.  Candidate carriers, all of which the DCOI receives:

| where | text |
|---|---|
| `prompt.md:298-302` | "Setting the parameter VALUES is not your job — that is the DC Input Creator's.  Your feedback stays primarily QUALITATIVE" |
| `prompt.md:312-315` | "You MAY name a specific value when you are genuinely confident about it, but treat that as the exception" |
| `prompt.md:362-364` | the RECOMMENDATION template's "NO concrete numeric values" |

If it IS a repetition, `:129-131` is the copy to drop — the HARD RULES section is
the natural owner.  Decide it when the DCOI's prompt comes up in the reduction.

### F68. The DCIC is told the UII both is and is not an authorisation source

**Status.** OPEN — deferred 2026-08-10 to the DCIC's own fork turn.

`agents/dc_input_creator/prompt.md:63-64`: "An authorisation reaches you from the
Orchestrator, the Planner relayed through the Orchestrator, **the UII**, or a
CLARIFY bounce".  Six lines later, `:66-69`: "only it (relaying the user /
Planner) or the user can GRANT authorisation, **NOT the User Input Inspector**".

Reconcilable as relay-vs-grant, but stated as a flat contradiction.  The fix is
one sentence: an authorisation may REACH the DCIC via the UII, but only the
Orchestrator or the user can GRANT one.

### F73. The DCII is told `parameters.json` is "overwritten".  It never is.

**Status.** OPEN — one word.  Deferred to the DCII's fork turn.

`agents/dc_input_inspector/prompt.md:76`: "``parameters.json`` has just been
**overwritten**".  The byte-parallel paragraph in the Tool Caller's prompt gets
it right — `tool_caller/prompt.md:48`: "the parameter set has just been
**written** by the DCIC".

The code refuses an overwrite: `dc_input_creator.py:99-103`, "the write refuses
if it already contains a ``parameters.json`` (attempt folders are append-only)".

So the DCII is told the file was mutated in place when in fact a NEW attempt
folder was opened.  **Fix: `overwritten` -> `written`.**

### F86. The reduced tree dropped the per-agent TRIGGERS for the user-input reading tools

**Status.** OPEN — LOW, and a VERIFY item rather than a fix-now item.  Found
2026-08-20 while analysing the standard-vs-reduced A/B (ID245 / ID246).

**The measurement.** ASSEMBLED prompts, topology 7, RAG off, counting mentions
of the four on-demand user-input tools (standard -> reduced):

| agent | `ocr_regions` | `read_image_notes` | `list_input_files` | `read_input_text` |
|---|---|---|---|---|
| Receptionist | 0 -> 0 | 0 -> 0 | 0 -> 0 | 1 -> 0 |
| Planner | 0 -> 0 | 1 -> 0 | 1 -> 0 | 1 -> 0 |
| User Input Inspector | 1 -> 0 | 1 -> 0 | 1 -> 0 | 1 -> 0 |
| DC Input Inspector | 1 -> 0 | 2 -> 0 | 2 -> 0 | 2 -> 0 |
| DC Output Inspector | 1 -> 0 | 1 -> 0 | 1 -> 0 | 1 -> 0 |

Sixteen mentions across five agents.  Measured on the ASSEMBLED prompts, not
the source `.md`, so this is not a shared-fragment artefact.

**Why this is NOT the defect it first looks like.**  The removed text is almost
entirely a tool CATALOGUE — a name plus a one-line description — and the tools
stay BOUND, so their schemas ship every turn carrying exactly that.  The one
piece of real mechanics in the deleted block, the `ocr_regions` batching rule
("pass every region in ONE call, not one call each"), was confirmed to ship in
`_OCR_REGIONS_DOC` (`user_inputs_tool.py:173-189`) BEFORE the cut was made —
that verification is what authorised it.  This is the fleet policy working as
designed: schema owns mechanics, prompt owns judgement.

**What is genuinely gone** is the per-agent TRIGGER — the sentence saying when
THIS agent should reach for the tool, which a schema cannot carry:

* UII, standard: "``ocr_regions`` — to confirm small/faint/garbled OCR
  callouts, re-read them at higher resolution".
* DCII, standard: the five-tool block is introduced with "when you suspect the
  UII misread something".
* DCOI, standard: "use this to discover whether any reference images exist this
  cycle".

**Evidence it may not matter.**  In the A/B the STANDARD arm — which names
`ocr_regions` — never called it either: `grep ocr_regions` returns 0 hits in
BOTH ID245 and ID246.  On the one observation available, naming the tool did
not drive use of it.  The reduced arm meanwhile DID call `read_image_notes`
(ID246 line 185), a tool its prompt never names, i.e. it found the tool from
the schema alone.

**What to do.**  Not a rewrite.  Confirm ONCE, in a run where an image is
genuinely faint or ambiguous, that a reduced-tree agent still escalates to
`ocr_regions` / `read_image_notes`.  If it does, close this.  If it does not,
the fix is one trigger sentence per agent, not the catalogue back.

**Where.** `agents/7agent_reduced/{user_input_inspector,dc_input_inspector,`
`dc_output_inspector,planner,receptionist}/prompt_7agents_reduced.md`, against
`agents/<agent>/prompt.md`.
Related: F65 (also an "open by design" reduced-tree omission).

---

### F87. C3 cannot be tested by the current variant switch, and its original evidence was a counting artefact

**Status.** OPEN as a METHOD item.  The hypothesis as originally stated is
WITHDRAWN; what replaces it is the experimental design needed to ask the
question properly.  Logged 2026-08-20 after the ID245 / ID246 A/B.

**What C3 claimed.**  That the reduced User Input Inspector — cut hardest in
the fleet, assembled 44,476 -> 17,970 chars — had lost the ability to say how
BINDING each user-supplied value is, and would therefore corrupt
`extracted_inputs.txt`, the canonical record every downstream agent reads.

**Why the motivating evidence was wrong.**  It rested on case-SENSITIVE counts:
`LOCKED` 1 -> 0 and `FREE` 1 -> 0.  Those tokens appear exactly ONCE in the
standard prompt — incidental capitalisation, not reinforcement.  Counted
case-insensitively the families are lock 15 -> 4 and free 12 -> 5, and the
reduced prompt still TEACHES all three states, including a rule the standard
does not phrase at all: "otherwise a stated value stays locked, including a
UI-pinned (FIXED) one, unless a LATER message subordinates it"
(`prompt_7agents_reduced.md:113-119`), plus the whole SOFT TARGET block with
its worked example.  Nothing conceptual about the three states was removed.

**What the A/B actually showed.**  TIE on both scored dimensions.  On the
predicted failure the reduced arm was BETTER: 15/15 reported quantities carried
a bindingness label against the standard arm's 11.  The predicted failure mode
did not appear.

**Two design faults that make the run pair unable to settle it either way:**

1. **`PROMPT_VARIANT` is a FLEET-WIDE switch.**  The treatment is all eight
   prompts at once, not the UII.  Verified from the cold-call token floors:
   every agent's floor dropped (Receptionist -1,369 tok, Orchestrator -1,605,
   Planner -1,464, UII -6,232).  A UII-specific hypothesis cannot be isolated
   this way, and more runs would not fix it — it is a design confound.
2. **The stated outcome measure was never captured.**  `extracted_inputs.txt`
   is written via `write_extraction`, and the session log truncates the tool
   args (20,917 chars hidden in ID245, 19,867 in ID246), so roughly 91% of both
   canonical records is unobserved.  Everything scored was the Receptionist's
   final report — a proxy rewritten twice by agents whose prompts also changed.

**Also confounded, and worth remembering before quoting any efficiency number
from that pair:** arm B received a SECOND user turn (its classifier ran twice,
arm A's once), so the headline "+51% input tokens / +87% LLM calls" partly
measures a classifier verdict rather than a prompt set.  Only the deterministic
cold-call floors are clean.

**What a real test needs.**

* A PER-AGENT variant selector, so only the UII changes.  `PROMPT_VARIANT` is
  one global string today; this is the blocking prerequisite.
* `extracted_inputs.txt` captured as a FILE artefact per run, not read out of a
  truncated log line.
* k >= 5 runs per arm, for a noise floor.  At n=1 the two most quotable
  differences found — a fabricated middle-section position, and a middle angle
  read as 10 deg where the drawing shows 18 deg — have no variance estimate and
  no causal path to any deleted text.
* Counterbalanced run order (A-then-B was run once, unbalanced).

**Genuinely established by the pair, and worth keeping.**  Per-run
`prompt_variant` pinning WORKS: proven by token floors (arm B's UII floor of
8,032 tok is below what the standard prompt alone would cost), by a behavioural
fingerprint ("configurator stores" — 2x in the standard prompt, 2x in ID245, 0x
in ID246), and by re-running the repo's own assembler under both variants.
Both arms also correctly honoured an extraction-only task: no DCIC, Tool Caller
or DCOI ran in either.

**Where.** Runs `ID245` (standard) / `ID246` (reduced), 2026-08-20.
Related: F56 (`SYSTEM_TOPOLOGY` read fresh mid-turn — the same
settings-are-global problem, one axis over).

---

### F90. The eager `*_TEMPLATE` block in `prompts.py` — nine import-time, topology-frozen constants

**Status.** OPEN. Not a live defect today; a latent trap. Raised 2026-08-02
during the topology-resolution step and deliberately NOT touched then, to keep
that step's blast radius small. **Decide before the 3-agent variant.**
Re-verified live 2026-08-21: still eager at `agents/shared/prompts.py:1045-1053`.

**Where.** `agents/shared/prompts.py:1045-1053` builds nine module-level
constants at **import** time — `RECEPTIONIST_TEMPLATE`, `ORCHESTRATOR_TEMPLATE`,
`PLANNER_TEMPLATE`, `UII_TEMPLATE`, `DCIC_TEMPLATE`, `DCII_TEMPLATE`,
`TOOL_CALLER_TEMPLATE`, `DCOI_TEMPLATE`, `DH_TEMPLATE` — each a
`_build_template(...)` call. They are the **7-agent** set, they run exactly once
when the module is first imported, and all nine are listed in `__all__`.

**The problem, in ascending severity.**

1. **Wasted startup work.** Under topology 5 all nine still build, including
   Planner, Orchestrator, DCIC and DCII, which that topology never constructs.
   Each `_build_template` call re-reads ~40 fragment files, so this is ~360 file
   reads at import for ~4/9 no reason. A cost, not a correctness issue.

1b. **What those four builds CONTAIN is incoherent** — the sharper form of 1,
   and the same defect as `O9` in the topology-selector design notes. Under
   topology 5, `_build_template("planner")` reads the 7-agent
   `agents/planner/prompt.md` but fills it from a topology-5 slot map, so
   `PLANNER_TEMPLATE` becomes the 7-agent Planner prompt with **5-agent
   fragments spliced into it**: `generic_constraints_5agents.md` telling it to
   escalate to a Conductor, `hard_constraints_dc_5agents.md`, and so on. A
   topology-MIXED prompt, not merely a wasted one. Harmless only because nothing
   reads it — which is exactly the assumption problem 3 says will not hold.

2. **Topology-frozen and hot-reload-stale.** `_topology()` is read fresh per
   call precisely because the Sessions Queue switches topology between runs
   inside one process. These nine capture whatever `SYSTEM_TOPOLOGY` was on disk
   when the module was FIRST imported and never update — neither on a topology
   switch nor on a System-Prompts-UI edit. They are the one place in the module
   that breaks the fresh-read contract.

3. **They look like the supported API.** Being in `__all__`, a future caller
   doing `from agents.shared.prompts import DCOI_TEMPLATE` silently gets an
   import-time, topology-frozen, stale string, while every current agent
   correctly calls `_build_template(...)` fresh in its own `__init__`.

4. **They become a hard startup failure the moment a topology deletes a prompt.**
   Each line needs its `agents/<agent>/prompt.md` to resolve. All nine 7-agent
   files exist today, so under topology 5 the first two `_prompt_path` candidates
   miss and each falls through to its historic file — fine. But if the 3-agent
   variant ever REMOVES a 7-agent prompt file, this block raises
   `FileNotFoundError` **at module import**: the whole app fails to boot rather
   than failing at the one agent that needed it.

**Why it is safe right now.** No production code reads any of the nine.
Re-grepped 2026-08-21: the only consumer outside the module is
`extra_utilities/smoke_test_prompt_format.py:95`
(`getattr(prompts, f"{name}_TEMPLATE")`). (`dc_output_inspector.py:65` mentions
`DCOI_TEMPLATE` in a comment only.) So today they are dead weight.

**Proposed solutions.**

- **Option A — make them lazy (recommended).** Delete the nine assignments and
  add a PEP-562 module-level `__getattr__` mapping `<NAME>_TEMPLATE` →
  `_build_template(<agent_dir>)` on attribute access. Fixes 1, 2 and 4 at once:
  nothing is built until asked for, and what is built is topology-correct and
  disk-fresh. `__all__` is unchanged and `smoke_test_prompt_format.py` needs no
  edit, so call-site churn is zero.
- **Option B — remove them.** Delete the nine constants and their `__all__`
  entries; change the one harness to call `_build_template` directly. Cleanest
  end state and kills 3 outright, but it is a public-API removal.
- **Option C — guard only.** Wrap the block in a topology check or a
  try/except. Addresses 4 alone, leaves 1, 2 and 3 in place. Not recommended —
  it hides the staleness rather than fixing it.

**Recommendation:** A now (zero call-site churn, fixes three of four), then B
later if the API surface is ever worth removing outright.

**Provenance.** Lifted verbatim from
`extra_utilities/docs/archive/agent_count_variants_build_tracker.md` (section
"🔶 OPEN — the eager `*_TEMPLATE` block in `prompts.py`") when that file was
archived, so the item stays visible in the live tracker. Same subject as the
topology-selector `O9` obstacle, now folded into
`extra_utilities/docs/active/topology_shared_touchpoints.md` §G.

---

### F91. Per-agent STATEFUL / STATELESS toggle in the Workflow-Settings agent flow chart

**Status.** OPEN — a feature request, never started. Surfaced 2026-07-26. It was
recorded in the reduced-agent build tracker under a heading that explicitly said
"**NOT part of the reduced-agent build**", i.e. it has been sitting in the wrong
file since it was raised. Re-grepped 2026-08-21: it appears in no other tracker.

**What to build.** For every PIPELINE agent shown in the Workflow-Settings agent
flow chart, add a button/tick:

- **ticked = STATEFUL (DEFAULT for every agent)** — the agent remembers its own
  previous messages (its message history persists across its invocations within
  the session, exactly as today).
- **un-ticked = STATELESS** — the agent's only context is its initial system
  prompt; it does NOT remember its previous conversations (fresh each
  invocation).

**Scope: pipeline agents ONLY.** Does NOT apply to the **Context Pruner** or the
**Database Handler**. (Today all agents are effectively stateful; this makes it a
per-agent choice.)

**Provenance.** Lifted verbatim from
`extra_utilities/docs/archive/agent_count_variants_build_tracker.md`, section
"Separate feature TODO (surfaced 2026-07-26 — NOT part of the reduced-agent
build)".

---

### F92. Four defects the 5-agent merge inherited from the 7-agent system — status re-checked 2026-08-21

**Status.** PARTIALLY CLOSED. Two of the four were fixed after they were
recorded; two are unverified and still stand as claims.

**Why this entry exists.** The reduced-agent build tracker recorded four defects
as "Deferred, INHERITED from the 7-agent (not merge-introduced)". That file has
now been archived, and the claims were never re-checked against the code. They
are reproduced here with a verification status against HEAD so they are not
silently carried forward as live defects.

**(a) "The DCOI cannot supply the `Parameters file:` line it is told to carry."**
NOT VERIFIED. The line is referenced from several prompts
(`agents/5agent/dc_output_inspector/prompt_5agents.md:385`,
`agents/5agent/tool_caller/prompt_5agents.md:14,28,43,58`,
`agents/5agent/tools_config/hard_constraints_tools_5agents.md:4`) but the
producer/consumer chain was not traced. Treat as an open claim, not a
confirmed defect.

**(b) "The Creator's DCOI-directed context dies at the Tool Caller."**
NOT VERIFIED. Same caveat.

**(c) "No `conductor`/`creator` variants of the per-agent database / BSV
fragments."** **FIXED.** `agents/5agent/tools_config/` now holds all four:
`database_search_conductor_5agents.md`, `database_search_creator_5agents.md`,
`blade_sections_visualizer_conductor_5agents.md`,
`blade_sections_visualizer_creator_5agents.md`.

**(d) "`user_input_inspector.py` still says paths are 'supplied by the
Planner'."** **FIXED in substance.** `prev_agent="Planner"` at
`agents/user_input_inspector/user_input_inspector.py:168` is correctly gated
behind `if PLANNER_FIRST:`, so the live default (`PLANNER_FIRST=False`,
`workflow_settings/settings.py:270`) never takes it; `:194-200` carries an
explicit comment that the sender is the Orchestrator, not the Planner, and uses
the agnostic "Hand-off from previous agent:" form; and the tool-handler error at
`:318` is path-agnostic ("Error: no directory path provided"). **Residue:** the
module docstring at `:4` still reads "Receives a short hand-off message from the
Planner" — cosmetic, one line.

**Next step.** Trace (a) and (b), then either close this entry or split each
surviving half into its own F-id.

---

### F93. Pending actions embedded inside `warnings_developer.md` — index

**Status.** OPEN as an index. Written 2026-08-21 during the documentation
reorganisation.

**The problem.** `warnings_developer.md` is an **invariant registry** — its job
is "do not break this", and most entries are permanent by design. But a dozen
entries also carry *pending work* (a named fix, a removal trigger that has come
due, a capability deliberately given up pending a decision). That work is
invisible from the TODO tracker, so it never gets scheduled.

**Deliberately an index, not a copy.** Duplicating each warning as its own F-id
would create twelve near-identical entries that then drift apart from their W
originals. Instead this entry lists them; the authoritative text stays in
`warnings_developer.md`.

| W-id | Pending action |
|---|---|
| `W41` | `metafilters` is a REAL capability loss with no replacement — an agent can no longer restrict the candidate pool before ranking. The 3-step undo recipe is in the entry; re-exposing just `satisfaction` would recover most of it. **First thing to reconsider if retrieval quality disappoints.** |
| `W40` | The top-level `cache_control` `ttl` assumption is unverified — a `1h` A/B would silently misread. Also records the 3-agent scope gap. |
| `W38` | `chunks_mm` embedding parameters are LOCKED in code and not modifiable in the UI. |
| `W29` | Local DH `.txt` writes are transitional; their removal is tracked nowhere else. |
| `W26` / `W27` | `sessions.notes` and `sessions.user_id` are reserved-but-always-NULL columns. |
| `W25` | `_slugify_field_for_filename` is duplicated between `db_writer.py` and `database_handler.py`; the entry names the fix. |
| `W16` | `requirements.txt` pins a numpy newer than some local Pythons can install; three named resolutions, none chosen. |
| `W13` | Removal trigger (Stage B per-session path namespacing) still not met — stays in force. Pairs with `O9`. |
| ~~`W14`~~ / ~~`W17`~~ | **Done 2026-08-21.** W14 retired (its "no save flow" premise is false — `/api/end` saves). W17 rewritten from "Streamlit is interim" to the durable thin-shim rule. |
| `W5` | The `agent.base_llm or agent.llm` rule has no enforcing test. |

**How to use this.** When one of these is actually scheduled, give it its own
F-id and link back to the W. Do not delete the W entry — the invariant outlives
the fix.
