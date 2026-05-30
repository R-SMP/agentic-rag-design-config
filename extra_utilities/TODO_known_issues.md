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

## ⇒ IMMEDIATE NEXT ACTION (do this before anything else)

### NEXT1. Deploy Stage A to Railway + stand up Rhino Compute on Azure

**Status.** NOT STARTED.  This is the single highest-priority task
— Stage A code is complete and validated locally (native venv +
Docker, both with renders working); the only thing between "works
on my machine" and "invited-only cloud URL" is this deploy.

**Two coupled sub-tasks:**

**(a) Shift all code to Railway.**
  * Deploy is via the **Railway CLI (`railway up`)**, NOT GitHub
    auto-deploy: the Railway GitHub App is not authorised on the
    `R-SMP` org and that needs an org-owner approval we do not
    control.  No push-to-deploy; each deploy is a manual
    `railway up` from the `stage-a-web-deploy` worktree.
  * Follow `extra_utilities/cloud_deploy_runbook.md` end to end:
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

**What.** Stage A's Streamlit app isolates per-browser-session UI
state via `st.session_state`, but the agents underneath still
write to the global on-disk paths.  Two users hitting the same
pod simultaneously will collide — they will share `inputs/user_
query.txt`, they will see each other's renders under `attempts/`,
and their per-agent log files in `logs/agent_histories/` will
overwrite each other.

**Required behaviour.** Each Streamlit user-session needs its own
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

**Where.** Stage A Streamlit UI (`streamlit_app.py` once it lands
in Phase 3).

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

### F3. HNSW / IVFFlat upgrade for `chunks.embedding`

**Resolved by going HNSW from day one** in the v2 schema (see
`database_design_notes.md` D2). This item — historically tracked as
"add HNSW once corpus reaches ~30k vectors" — is **closed before
opening**. Do not re-add it.

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

**Status.** Open, deliberately deferred.  Post-Stage-C /
productionisation work.  Triggered by the "two or more C2
limitations bite" condition above, or by a public-audience
requirement.  Paired warning: `warnings_developer.md` W17.

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
