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

**Status.** Open.  Pairs with F15 (DH response safety net) —
both reshape DH save behaviour around "what content actually
deserves to land in the database".

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

### F24. Live 3D preview in the Parameters Inputs view (P3-C)

**Where.**  `web/index.html` Parameters Inputs section (`data-view="params"`) and `web/app.js` PARAM_GROUPS / paramsInit().  Both currently ship the sliders + Use-these-parameters submit but no live preview.  The standalone reference at `C:\Users\vince\MT Coding\web_interface_tests\propeller_V3` shows the target behaviour: the right-hand viewport regenerates a propeller mesh on every slider change (debounced).

**What to build.**  Three coordinated pieces:

1. **Backend preview endpoint** — new `/api/preview_mesh` route in `web_app.py` that takes a JSON body of the 17 parameter values, calls the existing mesh tool (`tools/generate_mesh/generate_mesh.py`) directly (bypassing the agent pipeline), and returns the mesh bytes (`.obj` is fine; `.3dm` if we want to match the reference exactly).  This is the same RhinoCompute round-trip the agent path already does, just exposed without the chain in front of it.  Authentication: same `_require_auth()` gate as `/api/turn`; no session lock required since this is a preview, not a session action.

2. **Frontend slider listener** — add a debounced (~300–500 ms) `input` handler to every slider in PARAM_GROUPS that POSTs the current `paramState` to `/api/preview_mesh` and loads the returned mesh into a Three.js viewport.  Reuse `web/viewer.js` if possible, or instantiate a second viewer scoped to a new `<div>` in the Parameters view (the existing chat-view viewer needs to keep showing the agent-generated propellers, so sharing one DOM node is fragile).

3. **`.gh` file alignment decision** — the reference uses `propeller_V3.3.gh`; the v9 mesh tool uses `Propeller_Raul_V1.2.gh` (`config.GH_DEFINITION_PATH`).  Decide whether (a) the preview uses Raul V1.2 like the rest of v9 (visual continuity between preview and final mesh, but the preview won't look identical to the standalone reference), or (b) we add a second registered `.gh` definition for preview-only and switch on `definition` arg in the request body.  Option (a) is simpler and means "what you preview is what the agents generate" — recommended unless there's a reason to keep the propeller_V3.3.gh visuals.

**Why deferred.**  The Parameters Inputs view ships as sliders + submit in the current commit so the user can pick values and route them through the agent pipeline today.  The live preview is a separable, larger piece of work that needs (a) the backend bridge, (b) the viewport infrastructure, and (c) the .gh decision.  Not blocking the submit path; can land in its own commit when there is time.

**Status.**  **RESOLVED** 2026-06-XX (commits ``14bdfa1`` factor ``render_mesh_obj_text`` helper, ``dfc66e5`` ``/api/preview_mesh`` route, ``03ad83b`` debounced slider → preview pipeline + Download geometry handler).  ``.gh`` decision: went with option (a) — preview uses ``Propeller_Raul_V1.2.gh`` so what the user previews is what the agent pipeline produces.

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

**Status.**  Open.  Cost optimisation only — no behavioural
change visible to the user.  Best landed alongside any future
work on `dh_schedule.json` schema (so the batched-group
metadata can ride in on a coordinated schema bump).


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
`extra_utilities/OCR_technology_notes.md` (the region / crop re-OCR
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


### F40. Planner: use the blade-sections creator tool when sections must be observed

**Status.** ADDRESSED (prompt-first, 2026-06-18) — the Planner blade-sections
overlay (`DC_prompt_fragments/tools_config/blade_sections_visualizer_planner.md`)
tells it to prefer a sections-first plan when sections must be observed.  Part
of the BSV fast-path fragments alongside `render_blade_sections`
(`tools/render_blade_sections/`).

> Let the Planner know that, if there are sections to be observed as well, to use the blade sections creator tool


### F41. Planner: "maximum precision possible" means multiple refinement attempts

**Status.** PARTIALLY ADDRESSED (2026-06-18) — the Planner blade-sections
overlay covers the sections-context case (max precision ⇒ several cheap
section-refinement passes); the general directive (any geometry, not just
sections) is still open.

> Let the planner know that it is very important that if the user specifies they want maximum precision possible, it means performing multiple attempts trying to refine the geometry as much as possible (within a reasonable error)


### F42. Make the Planner and DCOI processes faster / more focused

**Status.** PARTIALLY ADDRESSED (2026-06-18) — the sections-context "clear,
precise, non-wasteful feedback" guidance is in the DCOI + Planner blade-sections
overlays; the general Planner/DCOI efficiency (beyond blade sections) is
deferred to a later step (user decision).

> Try to make the planner and the DCOI make their processes faster. e.g. when the DCOI observes the blade sections, many iterations may be required, so the feedback is to be given clearly and precisely and don't waste time on useless feedback. It all depends on the user request


### F43. Treat the Blade-sections renderer as a full new capability (sections-first fast path)

**Status.** ADDRESSED (prompt-first, BSV fragments, 2026-06-18) — the
sections-first fast path is now in the Planner / Tool-Caller / DCOI / UII
blade-sections overlays + the shared brief; the system can render + check
sections first and may stop at the sections (chat image as the deliverable; no
downstream code change this pass).  Deeper workflow / logic optimization
remains a later step.

> Let the system understand that, if the Blade section rendering tool is ON, that is a FULL NEW CAPABILITY that the system can use. If the user provides drawings of blade sections, or specific details about the blade sections, the system can first run the blade section renderer, check this, and then decide whether to generate a 3D geometry or not, because generating the blade sections only is much faster. This is just a suggestion, but still it can be done depending on the circumstance. This is to be optimized in the funcitoning, logic, and prompt wording for the soon future (very soon)


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
