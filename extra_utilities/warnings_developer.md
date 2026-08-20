# Developer / AI-assistant warnings

This file is **NOT a TODO list**.  It is a list of subtle behaviours,
architectural assumptions, and easy-to-break invariants that any
future developer (human or AI) MUST keep in mind when modifying the
codebase.  Each entry describes something that is not a bug — it is
either intentional, or load-bearing in a way that is not obvious from
casual reading — and explains why touching it would cause regressions.

For things that ARE bugs to be fixed, see
`extra_utilities/TODO_known_issues.md`.

---

## W1. NEVER move session artefacts into `previous_sessions/` until ALL post-session tasks are finished.

**Where.** `agents/loader.py:_end_session`, ordering of operations.

**Why.** Several artefacts that may be needed by post-session
processing live at well-known paths during a session and only get
relocated by `_archive_previous_session()` at the very end:

  * `inputs/user_query.txt`
  * `inputs/extracted_inputs.txt`
  * `inputs/input_images/<name>.{png,jpg,jpeg}` and `<name>_note.txt`
  * `attempts/<TS>_<NNN>_<slug>/parameters.json`
  * `attempts/<TS>_<NNN>_<slug>/render_*.png`
  * `attempts/<TS>_<NNN>_<slug>/propeller_mesh.obj`
  * `logs/agent_histories/history_<agent>.txt`
  * `logs/session_<TS>.log`
  * `logs/agent_flow_<TS>.txt`
  * `logs/database_handler_<TS>.log` and `logs/dh_flow_<TS>.txt`

Any future post-session task that wants to read user inputs, the
generated parameters, the renders, the per-agent histories, the
session log, or the DH log MUST run BEFORE
`_archive_previous_session()`.  Once archival fires, those paths
are gone and the task will silently fail to find anything.

If you add a NEW post-session task (analytics, RAG indexing, an
extra LLM pass over the renders, a follow-up Q&A round, …),
**place it BEFORE the archival call in `_end_session` and give it a
clear log line** so an empty result is debuggable.

The Database Handler is the first such post-session task; it must
also run BEFORE archival.  The order in `_end_session` today is:

  1. resolve session name (so DH and archive agree)
  2. **dump agent histories** (frozen snapshot of session state)
  3. run the **Database Handler** (uses the same frozen state)
  4. close the trace + main session logger
  5. archive everything into `previous_sessions/<ID>/`

Do NOT change this order without re-reading every step.

## W2. Logger names are global singletons; do not reuse them.

**Where.** `agents/database_handler/dh_trace.py` uses
`logging.getLogger("database_handler")`.

**Why.** Python's `logging` module returns the same logger object for
the same name across the entire process.  Any other module that calls
`logging.getLogger("database_handler")` inherits the DH's
`propagate = False` flag and any FileHandler the DH attached.  If you
need a logger inside a different feature, pick a different name —
do not piggyback on the DH's logger or you will both swallow events
that should reach the main session log AND get duplicated DH-flow
events written into your own file.

## W3. Module-level captures of `config.LOGS_DIR` (and friends) defeat monkey-patching.

**Where.** `agents/database_handler/database_handler.py` does
`from config import LOGS_DIR` at module import time.  Same pattern in
many other modules.

**Why.** Importing the NAME (`LOGS_DIR`) binds the local module
attribute to whatever the path was when the module first loaded.
Subsequent monkey-patching of `config.LOGS_DIR` (e.g. by a smoke
test) does NOT propagate to the module that already imported the
name.  Tests that need to redirect `LOGS_DIR` must also overwrite the
attribute on every consuming module (e.g. `dh_mod.LOGS_DIR =
fake_path`).  Production code is unaffected — the path never changes
mid-session — but anyone writing tests against the loader / DH must
know this.

## W4. `print()` calls inside post-session tasks are unconditional.

**Where.** `agents/database_handler/database_handler.py` prints
`DH log file:` and `DH trace file:` at the start of
`populate_database`.

**Why.** The DH was designed to be invoked from the interactive
loader, where stdout reaches the user.  If you ever invoke
`populate_database` from a script, batch job, or a test harness, the
unconditional `print()`s will leak into stdout.  Either route them
through the logger only, or guard with a `verbose=` flag — but be
aware the calls exist.

## W5. The DH's per-agent fallback `agent.base_llm or agent.llm` is a foot-gun.

**Where.** `_run_one_conversation` in
`agents/database_handler/database_handler.py`:

```python
base_llm = getattr(agent, "base_llm", None) or agent.llm
```

**Why.** Every chain agent today stores `self.base_llm` in `__init__`
(the bare provider client) and then re-binds `self.llm` with tools.
The DH wants the BARE client so its question doesn't accidentally
invoke a tool.  The fallback to `agent.llm` exists for safety, but
`agent.llm` IS bound to tools — if any agent in the future stops
storing `base_llm` (e.g. someone refactors and renames it), the DH
will silently fall through to the tool-bound LLM and the agent's
"interview answer" may include surprise tool calls (which then
fail validation because no `ToolMessage` is appended).

When you add new chain agents, ALWAYS expose `self.base_llm`.

## W6. ~~`_freeze_histories` deep-copies messages but NOT other agent state.~~ **OBSOLETE since v3 Phase 1 commit 6.**

The `_freeze_histories` mechanism this warning was about is gone.
The DH now reads `session.agent_states[agent_key].messages` into a
local `convo_buffer` and never mutates any live agent attribute,
so `_pending_hop` / `cycle_start_ts` / `_pending_image_blocks`
drift is structurally impossible.  See TODO_known_issues.md R3
for the full resolution.

This warning is kept (rather than deleted) so a reader following an
older code-review or commit message that references W6 still finds
the explanation of what the original concern was.

## W7. ~~The DH deepcopy of message objects has a shallow-copy fallback.~~ **OBSOLETE since v3 Phase 1 commit 6.**

The `_freeze_histories` deepcopy fallback this warning was about is
gone — the method itself was removed in v3 Phase 1 commit 6.  No
deepcopy of message objects happens during the DH interview anymore
(the local `convo_buffer` is built with `list(agent_state.messages)`
which shares message OBJECTS with the AgentState, but the DH never
mutates message objects in place — it only ever appends new
HumanMessage / AIMessage instances to its own buffer, so the share
is safe).

Kept for reference like W6 above.

## W8. The save-to-database prompt is OPT-IN by default.

**THIS IS VERY IMPORTANT — keep it in mind.**

**Where.** `agents/loader.py:run`, the user-quit branch:

```python
save_database = _ask_yes_no(
    "Save this session to the database (for later RAG)?",
    default_yes=False,
)
```

**Why.** Pressing Enter at the end-of-session prompt means **NO
SAVE**.  This is deliberate for v1: saving runs the Database Handler
which incurs LLM calls and time, and we don't want every quick test
session to accumulate spurious database entries.  But it is a
double-edged sword: if a user is rushing through a long debugging
session and presses Enter to "just exit", they have IRRECOVERABLY
lost the chance to record anything from that session — once
archival has run, the agent histories are FROZEN INSIDE
`previous_sessions/<ID>/agent_histories/` as static text dumps.
The DH cannot run against a static text file; it needs the live
in-memory agent objects with their `messages` lists intact.

Implications:

  * **NEVER change the default to `True` casually.**  If you do,
    every session — including failures — populates the database
    and the database fills with garbage.  If you DO want to flip
    the default, flip it via `workflow_settings.py`, not via
    hand-editing the loader.
  * **NEVER auto-confirm on KeyboardInterrupt or unhandled
    exception paths.**  Both currently leave `save_database=False`.
    The user is no longer at the keyboard to make a real choice;
    do not save without an explicit "yes".
  * If you ever introduce an unattended / scripted mode, plumb the
    "save?" choice through `workflow_settings.py` rather than
    relying on the prompt.

## W9. Ctrl-C during the DH phase leaves partial files behind.

**Where.** Interaction between `agents/loader.py:run`'s
`KeyboardInterrupt` handler and `_end_session(save_database=True)`.

**Why.** The user already typed "yes" to save, so `save_database` is
True when the `KeyboardInterrupt` fires.  Inside `_end_session`,
`populate_database` is called inside a try/except — if it raises
mid-conversation, control returns to `_end_session` which logs the
exception and proceeds to archival.  The partial outputs that
already landed on disk:

  * the per-question .txt files for the agents the DH already
    finished interviewing,
  * a partial `database_handler_<TS>.log` (open file → close +
    truncate semantics may leave it half-written on Windows),
  * a partial `dh_flow_<TS>.txt`.

These all survive archival into `previous_sessions/<ID>/`, so a
future RAG pipeline reading the database may encounter
half-populated session folders.  Defensive code SHOULD therefore
treat any per-session database folder as potentially incomplete —
do not assume "if the folder exists, all 8 entries are there".

## W10. `print()` inside the DH does not interleave well with the loader's `Goodbye!` line.

**Where.** `agents/loader.py:run` user-quit branch + DH prints.

**Why** (historical).  An earlier version printed `Goodbye!` BEFORE
`_end_session` ran, so the DH log paths and "entries written" line
appeared AFTER the goodbye.  The current code prints `Goodbye!`
AFTER `_end_session`, which fixes the order.  If you ever move the
goodbye print again, ensure it stays last so the user does not see
stdout activity after the program has visibly bid them farewell.

## W11. The DH's session-time timestamp is NOT `datetime.now()` at DH start.

**Where.** `agents/database_handler/dh_trace.py:init_dh_logging` accepts
a `session_timestamp` argument supplied by the loader.

**Why.** All session-related files (the main log, the agent flow
trace, archived attempts, archived input images) share a single
timestamp computed at session START in `agents/loader.py:_setup_logger`.
The DH log + trace files MUST use the same timestamp so they sort
together visually and so the previous_sessions/ folder name
(``ID{N:03d}_{date_time}``) cleanly groups them.  Do NOT switch the
DH back to `datetime.now()` at DH start — when the user spent a
long session before saving, the DH timestamp would diverge from the
session timestamp and the archive folder name would no longer match
either.

## W12. Logger name "database_handler" must NOT propagate.

**Where.** `agents/database_handler/dh_trace.py:init_dh_logging`,
`dh_logger.propagate = False`.

**Why.** Without this flag, every DH log line would also be emitted
by the root logger and end up in the main session log, defeating
the entire reason for having a dedicated DH log.  If you ever copy
this pattern to add another dedicated logger, do NOT forget to set
`propagate = False`.

## W13. Stage A is single-user-at-a-time on disk.

**Where.** Any code path that writes to or reads from
`config.USER_INPUTS_DIR`, `config.ATTEMPTS_DIR`, `config.LOGS_DIR`,
or `config.INPUT_IMAGES_DIR` — i.e. essentially every agent and
tool that touches user inputs, attempts, or logs.

**Why.** Stage A ships a Streamlit app whose `st.session_state`
isolates per-browser-session UI state, BUT the agents and tools
still write to the global on-disk paths from `config.py`.  Two
users hitting the same Streamlit pod simultaneously will collide:
both will append to the same `inputs/user_query.txt`, both will
write attempts into the same `attempts/<TS>_<NNN>_<slug>/`, both
will see each other's renders.  The `Session.create_for_v3` factory
already exists to namespace per-session paths, but plumbing those
paths through every agent + tool is a Stage B refactor (it pairs
naturally with introducing real per-user identity from Postgres).

**Implications for Stage A.**
  * Treat Stage A as **one-user-at-a-time**.  Document it on the
    invite-code login screen if user-visible wording is needed.
  * Do NOT silently rely on `Session.inputs_dir` etc. being set —
    they are None in v4 REPL and will also be None in Stage A's
    Streamlit dispatcher.  The caller passes `config.USER_INPUTS_DIR`
    to `dispatch_turn` directly, same as v4.
  * If you find yourself reaching for "let's just namespace one
    path", stop — partial namespacing is worse than none (some
    users see each other's files, some don't, hard to debug).
    Either do the whole refactor (Stage B) or accept the single-user
    invariant.

**Removal trigger.** This warning becomes obsolete the moment Stage
B lands per-session path namespacing through every agent and tool.
At that point, replace this entry with a short "obsolete" note
pointing at the commit that did the threading, like W6/W7 above.

## W14. UI button labels in Stage A must not promise persistence.

**Where.** Any Streamlit-side widget that ends or interrupts a
conversation in the Stage A web app.

**Why.** Stage A runs without a database.  There is no save flow
yet — the Database Handler exists in code but is wired only into
the v4 REPL's end-of-session prompt, not into the Streamlit UI.
Labelling a Stage A button "Save", "Save & Quit", "Submit",
"Archive", or anything similar promises persistence the system
cannot deliver and was a real source of confusion in earlier
v2 mockups.

**Stage A label.** The single available end-of-conversation
control is **"End Session"**.  It clears `st.session_state` and
reloads the page with a fresh empty Session.  Nothing is written
anywhere.

**Future stages.** Stage B introduces a true **"Save"** button
(persists Session into Postgres via the DH save flow).  When
Stage B lands, a Stage A-style "End Session" button MAY remain
alongside Save (as the explicit "discard, don't save" path) or
be replaced by a Save / Discard pair — this is a Stage B UX
decision, not a Stage A one.  Until then, do NOT add a "Save"
button anywhere in the Stage A UI even as a placeholder.

## W15. The project Python is a SHARED interpreter, NOT a venv in the worktree.

**Where (v9, updated 2026-06-15).**  This repo
(`C:\Users\vince\MT Coding\tests\test11_v9_git`) does NOT contain a
`.venv`, and neither do its worktrees under
`...\.claude\worktrees\<name>\`.  The interpreter that has the
project's dependencies (langchain, psycopg, pgvector, Pillow,
voyageai, …) is the **conda base env**:
`C:\Users\vince\miniconda3\python.exe`.  Running a bare `python`
from inside a worktree picks up whatever `PATH` resolves to — on
this machine the system Python 3.8, which does NOT have the project
dependencies.

(Historical note: earlier entries pointed at
`...\test11_v4_git\.venv` (Python 3.13).  That venv still exists but
belongs to the v4 checkout, is not v9-specific, and lacks
`voyageai`.  Use the conda interpreter for v9 work.)

**Why this matters.** Smoke tests / migration scripts that say
"run `python ...`" will silently use the wrong interpreter and
either fail with `ModuleNotFoundError` or, worse, succeed against a
Python whose package versions differ from what the project expects.

**How to run scripts reliably (v9).** Use the conda interpreter
explicitly:
  * `"C:\Users\vince\miniconda3\python.exe" <script.py>`

Each worktree also needs its OWN `.env` — worktrees do NOT inherit
the main checkout's untracked `.env`.  Copy it in once:
  * `Copy-Item "C:\Users\vince\MT Coding\tests\test11_v9_git\.env" ".env"`
    — `.env` is gitignored, so it cannot be committed from the
    worktree.

**Pip installs.** Always target the conda interpreter explicitly:
`"C:\Users\vince\miniconda3\python.exe" -m pip install <pkg>` —
a bare `pip` from a worktree lands in the wrong Python.

**Update tracker.** When this convention changes (per-worktree
venvs, or a tool like `uv`/`hatch` that provisions per-checkout
environments), update this entry rather than letting it rot.

## W16. requirements.txt pins newer numpy than some local Pythons can install.

**Where.** `requirements.txt` line `numpy>=2.0.0`.

**What.** numpy 2.x requires Python 3.9+.  The local Windows
machine has three Python installs — 3.8 (system), 3.9, and 3.13
(via py launcher).  Only 3.9+ can install numpy 2.x.  Installing
streamlit (or any other dep) via `pip install` while running on
Python 3.8 will downgrade numpy to 1.24.4 to satisfy compatibility
with 3.8 — and since `python` on this machine resolves to the
3.8 install (`C:\Program Files\Python38\python.exe`), this is
easy to do by accident.

**Why this is a footgun.** No runtime check enforces numpy >=
2.0.0; if the 1.x install ends up on `PYTHONPATH` (e.g. by being
imported from a 3.8 site-packages directory while the script
runs in another Python that falls back to it), the project may
silently behave differently than tested.  In practice this has
NOT bitten any Phase-1 work — the project venv (W15) uses
Python 3.13 with numpy 2.x — but the pinning vs. installed-env
gap is real and worth documenting before someone investigates a
"my smoke test failed but the venv works" puzzle.

**Status.** Documented, not fixed.  Resolving by either (a)
pinning a more specific numpy floor that matches what every
project Python can install, or (b) adding a runtime
`numpy.__version__` check at startup, or (c) tightening the
`python_requires` constraint to >= 3.9 in a future `pyproject.
toml` — is deliberately deferred.  See also W15 for the venv
convention that mostly papers over this in day-to-day use.

## W17. Streamlit is an INTERIM web interface — do not over-invest in it.

**THIS IS A WEB-INTERFACE DEVELOPER NOTE — read before adding
anything non-trivial to `streamlit_app.py`.**

**Where.** `streamlit_app.py` and anything that grows around it.

**What.** The Stage A web UI is Streamlit purely because it was
the fastest path to a deployed, invite-gated chat surface that
reuses `agents/dispatch.py:dispatch_turn` unchanged.  It is
explicitly a **stop-gap**, not the destination.  The planned
replacement is a **JavaScript-based web interface** (see
`TODO_known_issues.md` F4 for the tracked item, and
`cloud_architecture_notes.md` C2's "Future migration" subsection
for the architectural sketch — HTMX-or-SPA over a FastAPI/API
backend).

**Why this is a warning, not just a TODO.** Streamlit's
whole-script-rerun model tempts developers into Streamlit-specific
contortions: stuffing live objects into `st.session_state`,
threading background work around the rerun loop, fighting the
single-column layout with `st.columns`/`components.v1.html`
escapes, caching hacks, etc.  Every such hack is **throwaway work**
— it does not survive the migration to a JS frontend, and worse,
it entangles agent-level logic with Streamlit's execution model
and makes the migration harder.

**Rules for anyone extending the web layer:**
  * Keep all agent / pipeline logic behind `dispatch_turn` and the
    `Session` plain-data contract.  `streamlit_app.py` must stay a
    THIN I/O surface (read input, render output, manage the gate +
    session-state lifecycle) — the same role the v4 REPL loader
    plays.  A JS frontend should be able to replace
    `streamlit_app.py` by calling the same `dispatch_turn`.
  * Do NOT push business rules, parameter validation, artefact
    resolution, or persistence decisions into the Streamlit layer.
  * If a feature needs a Streamlit-specific hack to work, that is
    a signal the feature belongs behind `dispatch_turn` / in the
    agent layer, OR that it should wait for the JS frontend.
  * New user-facing controls (e.g. the Stage B "Save" button, see
    W14) should be specified in terms of *what dispatch/session
    operation they trigger*, so they port to the JS frontend as a
    button that hits the same operation.

**Status.** Streamlit is the Stage A + (likely) Stage B/C
frontend.  The JS migration is post-Stage-C / productionisation
work (F4).  This warning stays in force until F4 lands; at that
point replace it with an "obsolete" note like W6/W7.


## W18. Every DH tool is bound for ONE turn only, never left on `self.llm`.

The Database Handler's ``self.llm`` is tool-LESS, and its prompt says so
explicitly.  Each of its four tools is bound for a single turn with
``tool_choice`` and then discarded:

| tool | bound on |
|---|---|
| ``submit_batch_plan`` | the one planning turn per save |
| ``submit_questions`` | the question-writing turn of each batch |
| ``submit_batch`` | each save-decision turn (and the cap-compression turn) |
| ``save_attempt_data`` | the force-tool turn of an identifying row |

The three batching tools go through ``_force_tool_args``, which binds,
invokes, reads the arguments off ``tool_calls`` and drops the binding.
The original and still-canonical example is the **force-tool turn** that
fires once per identifying attempt-specific schedule row
(``scope="attempt"`` AND ``parent_id is None``).  On that turn,
``_run_force_tool_phase`` calls
``self.llm.bind_tools([save_attempt_data],
tool_choice="save_attempt_data")`` to construct a
PER-TURN tool-bound LLM; the per-turn binding is then thrown away
and the next turn uses ``self.llm`` unbound.

### Why this matters

* ``self.llm`` on the DH is deliberately tool-LESS, and every tool the
  DH has is bound the same way: for one turn, with ``tool_choice``,
  then discarded.  As of the batching work (F33) there are four —
  ``submit_batch_plan``, ``submit_questions``, ``submit_batch`` and
  ``save_attempt_data`` — and the invariant is what keeps them from
  interfering: the DH's LLM sees EXACTLY ONE tool schema per turn, so
  there is never a choice of which to call, and a turn cannot answer
  with the wrong tool.  Binding any of them permanently would put four
  schemas in front of the model on every turn and invite exactly that.
* In particular, binding ``save_attempt_data`` permanently would make
  the model emit spurious attempt-binding calls on session-scoped rows
  and sub-rows, where no attempt exists to bind.
* The force-tool's ``tool_choice="save_attempt_data"``
  *forces* the LLM to call the named tool on its next response.
  Using this binding outside the force-tool turn would also force
  unwanted tool calls.
* Tool-call IDs round-trip through ``ToolMessage(tool_call_id=...)``
  — the DH's per-save ``self.messages`` accumulates these
  ToolMessages, and a follow-up invoke that does NOT have the tool
  bound is fine with them in history (it sees them as already-
  closed tool calls).

### Where the binding lives

* ``_run_force_tool_phase`` (in
  ``agents/database_handler/database_handler.py``) — the only
  place ``bind_tools`` is called on the DH's LLM.
* The unbound ``self.llm`` is used by every OTHER DH LLM call:
  ``_formulate_question`` (first-question turn),
  ``_decide_next`` (ASK/SAVE), ``_enforce_semantic_cap_pair``
  (compression).

### If you add another DH tool later

Follow the same pattern:

1. Define the tool in ``agents/database_handler/dh_tools.py``.
2. Bind it via ``self.llm.bind_tools(...)`` on a per-turn basis
   from a focused helper method (like ``_run_force_tool_phase``).
3. Append the ``ToolMessage`` to ``self.messages`` and let later
   unbound invokes see them as closed.
4. Add a line in this warning to keep the "tools are
   per-turn-bound" invariant explicit.

Do NOT bind tools to ``self.llm`` permanently — the DH's prompt
assumes a tool-less default.

**Status.** In force from v9 onward.  The single tool
(``save_attempt_data``) is the only one wired today.


## W19. The two R2 upload paths MUST stay disjoint in key space.

The DH save flow writes to R2 via TWO distinct upload paths, each
operating at a different point in the save lifecycle:

* **Path 1** — ``r2_uploader.upload_attempt_artefacts`` called
  from ``_run_force_tool_phase`` immediately when the
  ``save_attempt_data`` tool resolves attempt ids.  Keys
  written: ``<R2_KEY_PREFIX>/<session_id>/attempts/<NNN>/...``.
* **Path 2** — ``r2_uploader.upload_directory`` called from
  ``populate_database`` at the end of the per-row write loop,
  walking the LOCAL ``database/<session_id>/`` tree.  Keys
  written: ``<R2_KEY_PREFIX>/<session_id>/<agent>/...`` and
  ``<R2_KEY_PREFIX>/<session_id>/user_inputs/...``.

These two paths target DISJOINT R2 key prefixes (``<sid>/attempts/``
vs ``<sid>/<agent>/`` and ``<sid>/user_inputs/``), and the system
relies on that disjointness to avoid double-uploads.  The
disjointness is NOT enforced by the upload layer — it is a
consequence of WHERE the local files live: ``populate_database``
never writes anything to ``database/<session_id>/attempts/``, so
Path 2's directory walk never finds the artefact files.

### What this means in practice

If you add a new local writer (e.g. a future ``_collect_attempts``
helper that mirrors ``attempts/<slug>/`` content into
``database/<session_id>/attempts/<slug>/`` for the End Session
archive), Path 2's ``upload_directory`` will pick those files up
and try to upload them ON TOP of Path 1's already-uploaded
artefacts.  The result depends on the key shape:

* If the new local files match Path 1's exact rename pattern
  (``<sid>__<NNN>__<original>``) under
  ``database/<session_id>/attempts/<NNN>/``, Path 2 would issue
  identical PUTs — wasteful but idempotent.
* If the new local files use a different shape (e.g. original
  filenames preserved under
  ``database/<session_id>/attempts/<slug>/parameters.json``),
  Path 2 would write to a DIFFERENT R2 key
  (``<sid>/attempts/<slug>/parameters.json``) — both
  representations would end up in the bucket and the future RAG
  layer would have to disambiguate.  This is the failure mode to
  avoid.

### How to add a new R2 upload path safely

1. Audit which R2 keys the new path writes.
2. Confirm those keys do not overlap with the existing two paths.
3. If overlap is unavoidable (e.g. you want to mirror the
   artefact files locally too), pick ONE path to own that key
   prefix and skip it from the other (e.g. add a glob exclusion
   to ``upload_directory``'s suffix walk).
4. Add the new path to the README's "Cloudflare R2 layout"
   section AND update this warning so the invariant stays current.

### Why this matters

R2 PUTs are idempotent at the byte level — overwriting an
identical-content key is harmless functionally.  But:

* They cost bandwidth and Cloudflare write-operations quota.
* They confuse the future RAG retrieval layer, which uses the
  key shape to bucket per-attempt vs per-agent content.
* They obscure failures: an orphan Path-2 write to an
  ``attempts/`` key could mask a real Path-1 upload failure
  (see TODO F20).

**Status.** In force from v9 onward.  Two paths today; any third
upload path must be checked against this invariant.


## W20. The Orchestrator's `submit_feedback_dispatch` tool is bound ONLY during the end-of-session feedback round.

Second consumer of the per-turn force-tool pattern (see W18 for the
first — the DH's ``save_attempt_data``).  The Orchestrator's
permanent ``self.llm`` is bound to its routing tools
(``call_<agent>``, ``calculate``, ``list_attempts`` etc.) at
``_wire_routing`` time and stays that way for the whole design
pipeline.

When the user clicks "End Session → Save" in the web UI and
supplies feedback in the modal, ``web_app._run_end_in_background``
calls ``Orchestrator.run_feedback_round(...)``, which:

1. Builds a LOCAL ``feedback_llm = self.base_llm.bind_tools(
   [submit_feedback_dispatch], tool_choice="submit_feedback_dispatch")``
   — note ``base_llm`` (the unbound LLM held on the agent), NOT
   ``self.llm`` (the routing-tool-bound LLM).
2. Invokes ``feedback_llm`` ONCE via ``invoke_with_retry`` against a
   TRANSIENT message list ``[make_system_message(...) + one
   HumanMessage]`` — the Orchestrator's ``self.messages`` is NOT
   touched, so the design-pipeline history is unaffected.
3. Discards ``feedback_llm`` immediately.  ``self.llm`` is unchanged.
4. Applies the returned dispatch list by appending
   ``HumanMessage(name="orchestrator")`` entries to the TARGET
   agents' message histories.

### Why this invariant matters

* The Orchestrator's Role-1 / Role-2 / Role-3 prompt sections do not
  describe ``submit_feedback_dispatch``; only the Role-4 section does.
  Permanently binding the feedback tool would let the Orchestrator
  accidentally call it during normal dispatch — meaningless and
  potentially destructive.
* Prompt-cache invariance: the static system prompt only describes
  Role 4 as a separate post-session pass.  The LLM should never see
  ``submit_feedback_dispatch`` listed in its tool schema during the
  design pipeline.

### Adding a third forced-tool consumer

Same checklist as W18:

1. Define the tool in the agent's own tools file (e.g.
   ``agents/<agent>/<feature>_tool.py``).  Do NOT pollute another
   agent's tools file.
2. Bind via ``self.base_llm.bind_tools([...], tool_choice="...")``
   on a per-turn basis from a focused helper method.
3. Append the ``ToolMessage`` to ``self.messages`` (or work entirely
   in a transient buffer, as ``run_feedback_round`` does).
4. Add a paired entry here so the per-turn-only invariant stays
   discoverable.

**Status.** In force from v9 onward.  Two consumers today
(``save_attempt_data`` on the DH; ``submit_feedback_dispatch``
on the Orchestrator).

## W21. Empty `to_agents` in the DH schedule means "all primary agents", NOT "no agents".

**Where.** Database Handler chunks-INSERT path (Phase 3B,
``agents/database_handler/db_writer.py``), the DH-schedule editor
UI (``web/app.js`` ``openQPopover`` + ``renderToCellChips``),
and the `chunks.agents_to TEXT[]` ACL column.

**Why.** The DH-schedule editor lets an operator pick which agents
can retrieve each Q+A from the RAG (the per-row "To" cell, backed
by ``to_agents`` in ``dh_schedule.default.json`` and the live
schedule JSON).  An operator who saves a row without ticking any
"To" boxes does **not** mean "no agents should see this Q+A".  The
DH treats that as the permissive default and inserts the chunks
row with
``agents_to = [Receptionist, DH, DCII, DCOI, Planner, Orchestrator,
UII, DCIC, TC]`` — every primary chain agent.

The intent is to avoid the silent-invisibility failure mode where
an operator forgets the ACL and the resulting chunks become
unreachable for the RAG without any warning.  See
``extra_utilities/db_design/database_and_RAG_architecture.md`` §3.6
for the full design rationale and §8 invariant 14 for the locked
contract.

**To restrict** visibility, populate ``to_agents`` explicitly per
row.  The popover in the UI now shows a help line stating the
empty-default rule, and the empty-state chip in the table cell
reads ``(all agents — click to restrict)`` rather than the
previous misleading ``(click to set)``.

**Single source of truth for "primary agents".**  The list of
agent keys that constitute "all primary agents" lives in ONE
place: the ``DEFAULT_AGENTS_TO_ACL`` constant in
``agents/database_handler/db_writer.py``.  Do NOT redefine it in
``dh_schedule.py``, in the UI's ``Q_AGENTS`` list, or anywhere
else — those are display-only catalogues, not the ACL default.
When chain agents are added or removed, edit
``DEFAULT_AGENTS_TO_ACL`` and that change automatically flows to
every chunks-INSERT call.

**Status.** In force from Phase 3B (DH-Postgres ingest) onward.

## W22. The spontaneous PROPOSED mechanism uses NATURAL-LANGUAGE detection, not a fixed marker.

**Where.** Receptionist's ``propose_attempt`` tool firing rule —
``agents/receptionist/prompt.md`` "Reporting attempts" step 4
(spontaneous PROPOSED branch) + the ``$propose_attempt_tool``
fragment at ``DC_prompt_fragments/tools_config/propose_attempt.md``.
The Planner emits its verdict in plain prose
(``agents/planner/prompt.md`` Role 3 APPROVE branch); the
Receptionist's LLM interprets that prose to decide whether to fire
``propose_attempt``.

**Why.** An earlier design draft (2026-06-01) proposed a literal
marker convention like ``BEST SO FAR: attempt N — <reason>`` so
the Receptionist could regex-match.  The user rejected this:
*"there is no need to have ALWAYS a 'BEST SO FAR'. But IF there
is, it should be specified, verbatim, not with a fixed form"*.
Natural-language phrasing keeps the Planner's voice free and lets
the system express the full spectrum of confidence (clear
satisfying pick / interim show-for-context / not satisfying yet)
without forcing the Planner into a binary tagged outcome.

**The trade-off.**  Pattern-matching prose is fuzzier than
pattern-matching a literal token.  The Receptionist might
occasionally misjudge an ambiguous hand-off — fire propose_attempt
when the Planner meant "still iterating", or skip it when the
Planner meant "this is the one".  We accept this on the user's
sign-off; if it becomes a real problem we revisit by either
(a) tightening the Receptionist's prompt with more examples,
(b) asking the Planner for stricter phrasing rules, or
(c) reintroducing an optional explicit marker (e.g. a literal
``ENDORSED: yes`` line the Planner MAY include for clarity but
isn't required to use).

**What this means for prompt-edit discipline.**

  * The endorsement / hedging example phrases in the Receptionist
    prompt (``propose_attempt`` step 4) and the matching example
    phrases in the Planner prompt (Role 3 APPROVE clarity
    paragraph) must STAY CONSISTENT.  If you change the
    "endorsement vocabulary" on one side you must mirror it on
    the other or the natural-language detection breaks silently.
  * The same applies to the
    ``DC_prompt_fragments/tools_config/propose_attempt.md`` tool
    fragment — it carries the same example phrases as the
    Receptionist prompt body for the LLM's reference.
  * NEVER replace this natural-language convention with a
    regex / literal-marker convention without a paired prompt
    update on the Planner side AND a user sign-off.  The marker
    convention was explicitly considered and rejected on
    2026-06-01; reintroducing it is a real design change, not a
    cleanup.

**Status.** In force from commit B of the Parameters Inputs
redesign (2026-06-XX) onward.


## W23. The Phase 3B smoke test lives at `extra_utilities/db_design/smoke_test_db_writer.py` and exercises the live OpenAI API + the live Railway Postgres.

The smoke test is the canonical end-to-end verifier for
`agents/database_handler/db_writer.py` (Phase 3B).  It runs 14
numbered checks that together prove:

- the OpenAI stitch + embed endpoints are reachable,
- `embedding_model` is formatted as the locked
  `"openai/text-embedding-3-large/1024"` string,
- the four insert-outcome branches (`INSERTED`, `SKIPPED_UNIQUE`,
  `SAFETY`, and the v5-relaxed `is_empty=TRUE` Semantic safety
  net) all behave per the architecture doc §3.5 / §3.1 v5
  addendum,
- `save_session_feedback` writes the labelled-block
  `sessions.feedback` and the per-question `chunks` mirror rows
  (answered → embedded; unanswered → `is_empty=TRUE`).

How to run::

    python extra_utilities/db_design/smoke_test_db_writer.py

Cost: roughly 8 OpenAI calls (gpt-4o-mini + text-embedding-3-large),
well under one cent.  Sub-second wall-clock excluding cold starts.

Cleanup: the test always wipes its own `_smoke_test_*` Postgres
session at exit (CASCADE removes child rows in chunks +
dc_attempts + dc_attempt_parameters).  Set `SMOKE_NO_CLEANUP=1`
to leave the synthetic data in place for manual inspection.

**R2 leftover.** The SAFETY-path check uploads exactly one R2
object (under `<SMOKE_SESSION_ID>/safety/session/_SmokeForceFail.txt`)
that the smoke test does NOT clean up — a deliberate scope cut
per design Q-T4.  Remove it via the Cloudflare dashboard if it
matters, or wait for the future R2-cleanup helper.

When to run: any time `db_writer.py`, `stitching_prompt.md`, the
`workflow_settings.STITCHING_*` knobs, the v5 schema, or the
`agents/shared/postgres_pool.py` connection logic change.

For the full per-check expected-output transcript and the
architecture-doc cross-references for each check, see the module
docstring at the top of
`extra_utilities/db_design/smoke_test_db_writer.py`.

**Status.** Introduced 2026-06-02 alongside Phase 3B.


## W24. End-Session feedback questions live in code, NOT in `dh_schedule.json`.

The two feedback questions asked to the user at End Session
("Which parts of the process satisfied your request?" and "Which
parts of the process did NOT satisfy your request?") are defined
in code at
`workflow_settings/fixed_feedback_questions.py` and rendered as
a **read-only** greyed-out table at the bottom of the "Questions
for Saved Sessions" web view (`workflow_settings/editor.py` +
`web/index.html`).  They are NOT part of the user-editable
`dh_schedule.json`.

Source of truth: `FIXED_FEEDBACK_QUESTIONS` in
`workflow_settings/fixed_feedback_questions.py`.  Every consumer
(`db_writer.py`, the editor UI, the End Session modal in
`web/app.js`, the architecture doc §3.3 / §3.7) reads from this
single constant.

**Why fixed in code, not the schedule?**  Changing the wording
through the UI would create a silent mismatch — the modal in
`web/app.js` shows hardcoded prompt text, while the schedule's
"question" field would drift.  Code is the single source of truth
so the modal and the schedule view stay in lockstep.

**Adding a third feedback question.**  Append a new dict to
`FIXED_FEEDBACK_QUESTIONS` with `id` / `field` / `question` /
`block_label`, then update the End Session modal in
`web/app.js` to actually ask the question.  No schema migration
is required — the `chunks` mirror is open-ended (each question
= one row distinguished by `field`) and `sessions.feedback`
just appends another labelled block.

**Editing the wording of an existing question.**  Edit the
`question` string in `fixed_feedback_questions.py` AND in
`web/app.js` in the SAME commit.  Past sessions' `chunks` rows
keep the OLD wording frozen in their `chunks.question` column —
that is the desired audit-trail behaviour.

**Status.** In force from Phase 3B (2026-06-02) onward.  See
architecture doc §3.3 + §3.7.


## W25. `_slugify_field_for_filename` is duplicated between `db_writer.py` and `database_handler.py`.

`agents/database_handler/db_writer.py` carries a small inline
`_slugify_field_for_filename(field)` helper used to derive R2
safety-folder filenames (e.g. `"Positive User Comments"` →
`"Positive_User_Comments.txt"`).  The Database Handler's
existing `_entry_path` helper in
`agents/database_handler/database_handler.py` does a similar
job for the local `.txt` per-Q+A files.

These are deliberately separate to avoid a circular import
(`db_writer` is imported by `database_handler.py`; the
reverse would create a cycle).

**Risk if the two slug conventions diverge.**  R2 safety-folder
filenames produced by `db_writer` would no longer match the
canonical DH filenames that a future recovery script (T12 in the
architecture doc §7) tries to pair them with.  The slug rule is
currently the same — `re.sub(r"[^A-Za-z0-9_-]+", "_", field)`
plus a `.txt` suffix — but is enforced ONLY by convention.

**Fix if the duplication becomes a problem.**  Factor the slug
helper into `agents/shared/file_utils.py` (a leaf module with
no agent dependencies) and import it from both `db_writer.py`
and `database_handler.py`.  Until then, any edit to the slug
convention must be applied to BOTH files in the same commit.

**Status.** In force from Phase 3B (2026-06-02) onward.


## W26. `sessions.notes` column is reserved for future use; currently always NULL.

The v5 schema reserves a `sessions.notes TEXT` column for free-text
session-level notes.  Phase 3C's `db_writer.upsert_session` call
always passes `notes=None`, so the column stays NULL for every
session today.

If the project ever needs to attach a final message to the saved
session — e.g.

  * an operator-side "session notes" textarea in the workflow-
    settings UI,
  * an automatic *"the DH save was partial because <reason>"*
    message generated by `populate_database` itself,
  * a wrap-up summary from the End Session flow,

the column is already in place.  Wiring is just one non-None
string passed to `db_writer.upsert_session(notes=...)`; no schema
change is needed.  See architecture doc §7 (T21).

**Status.** Reserved by schema v5 (2026-06-02); first use case TBD.


## W27. `sessions.user_id` column is reserved for multi-user identification; currently always NULL.

The v5 schema reserves a `sessions.user_id TEXT` column for a
per-user identifier so future multi-user deployments can filter
sessions by user.  Phase 3C's `db_writer.upsert_session` call
already forwards `self.session.user_id` to the column, but
`Session.user_id` defaults to `None` and is never set by the
dispatch layer.

If we want to identify different users, the column spot is already
in place — only the FRONTEND needs to change.  Concretely:

  1. Capture a user-ID value at session start (login flow,
     URL parameter, or a "who is using this?" header field).
  2. Forward it to the dispatch layer (e.g. `/api/turn` or
     `/api/start`).
  3. Store it on `Session.user_id`.

`populate_database`'s existing
`upsert_session(user_id=self.session.user_id, ...)` call then
automatically includes it — no further DH code change required.

See also architecture doc §7 (T22) and the deferred user-identifier
work tracked under F22.

**Status.** Reserved by schema v5 (2026-06-02); first use case TBD.


## W28. `insert_chunk` forces `item_index=1` for attempt-scoped single-pair rows.

The chunks UNIQUE constraint is on `(session_id, agent_from,
field, attempt_id, item_index, embedding_model)`.  PostgreSQL's
default treats NULLs as DISTINCT in UNIQUE constraints — so if any
of `attempt_id` / `item_index` is NULL, two otherwise-identical
rows can coexist (no UNIQUE violation, no `SKIPPED_UNIQUE`).

The DH writes single-pair rows with `item_index=None` to keep the
local `.txt` filename free of an `_1` suffix (the v9 filename
matrix uses `_M` only for multi-pair).  But for attempt-scoped
rows we DO want UNIQUE to engage so a re-run of
`populate_database` returns `SKIPPED_UNIQUE` rather than silently
duplicating the chunks row.

Resolution: at the per-Q+A integration site
(`agents/database_handler/database_handler.py::_phase_3c_persist_chunk`),
when an attempt-scoped row arrives with `item_index=None`, the
helper PROMOTES it to `item_index=1` before passing to
`db_writer.insert_chunk`.  Session-scoped single-pair rows
(`attempt_id=None`) keep `item_index=None` — the NULL-distinct
semantics are intentional for those.

Consequence: a local `.txt` named `<field>__001.txt` corresponds
to a chunks row with `item_index=1`, not `item_index=NULL`.
Recovery scripts that pair safety files with chunks rows by the
unique key need to be aware of this asymmetry.

**Status.** In force from Phase 3C (2026-06-02) onward.  See
architecture doc §9.5 + the chunks-table NOTE in
`database_PostgreSQL_schema_v5.sql`.


## W29. Local DH `.txt` files are transitional during Phase 3C; Postgres + R2 will be the only sources of truth.

Phase 3C wires `populate_database` to write each Q+A to BOTH the
local on-disk `.txt` and Postgres `chunks` (plus the R2 mirror).
The architecture's long-term direction is that **the local `.txt`
files will eventually NOT be looked at — only Postgres and R2
content will**.  The local writes are kept active during Phase 3C
as belt-and-braces while we verify the Postgres path end-to-end.

What this means for tools, scripts, and future maintainers:

- Treat the local `database/<session>/.../**.txt` tree as a
  **debug aid**, not a source of truth.  Code that reads it for
  retrieval (e.g. early RAG prototypes) should migrate to
  `database_search` (Phase 4) when that ships.
- Phase 3D (2026-06-02) DROPPED the `.txt` suffix from the
  end-of-`populate_database` R2 mirror suffix list.  R2 now only
  holds non-Q+A artefacts (mesh / renders / user-input images /
  per-attempt `description.txt`) plus the safety folder for
  failed Q+A inserts.  The local `.txt` tree still exists on the
  Railway container's writable layer but is no longer mirrored
  via the `upload_directory` whitelist.  See W30 for the three
  R2 upload paths and which file types each carries.
- The eventual end state (post-Phase 3D, post-Phase 4): Postgres
  `chunks` is the retrieval surface; R2 holds artefacts +
  safety-folder failures; the local `.txt` files exist only for
  ad-hoc debugging when SSHing into the container.

If you find yourself writing code that LOOKS UP a Q+A from the
local `.txt` tree (rather than via `database_search` or
`db_writer`), you are probably writing the wrong thing.

**Status.** Forward-looking note from Phase 3C (2026-06-02)
onward.  Phase 3D narrowed the R2 mirror on the same date.
Beyond that, the local `.txt` writes may be removed entirely.


## W30. Three R2 upload paths — know which one carries which file.

After Phase 3D (2026-06-02), Cloudflare R2 receives session files
via THREE distinct code paths, each with its own whitelist /
trigger.  Adding or removing a file type involves deciding which
path should carry it.

**Path 1 — `r2_uploader.upload_directory(user_inputs_dir, suffixes=...)`**
- Called ONCE at the end of
  `agents/database_handler/database_handler.py::populate_database`.
- Walks `<session_dir>/user_inputs/` (NOT the whole `<session_dir>`)
  recursively and uploads any file whose suffix matches the
  whitelist.
- Current whitelist: `(".txt", ".png", ".jpg", ".jpeg")`.
- What lands here: every file `_collect_user_inputs` snapshotted
  under `<session_dir>/user_inputs/`:
    * `queries.txt` — the user's full turn-by-turn text inputs;
    * `images/<original>.png|.jpg|.jpeg` — reference images;
    * `images/<original>_note.txt` — per-image notes.
- What USED TO be in scope (pre-3D): the WHOLE `<session_dir>`
  with `.txt` included — that picked up the DH's per-Q+A
  `<agent>/<field>.txt` files too.  Phase 3D dropped `.txt`
  from the whitelist (Postgres `chunks` is the sole Q+A store
  now per §3.5 / invariant 12) but inadvertently also dropped
  `queries.txt` and `_note.txt`.  The 2026-06-03 fix re-scoped
  the upload to `user_inputs/` only, restoring `queries.txt`
  and `_note.txt` mirroring while keeping per-agent Q+A bodies
  out of R2 (they live under `<agent>/`, outside the scope).
- The upload runs whether the DH wrote zero attempts or many —
  `_collect_user_inputs` + this mirror call BOTH execute
  unconditionally at the end of `populate_database`.

**Path 2 — `r2_uploader.upload_attempt_artefacts(folder, ...)`**
- Called PER RESOLVED ATTEMPT from
  `_run_force_tool_phase` inside `save_attempt_data`'s tool
  handler.
- Uploads a fixed hardcoded whitelist of artefact filenames
  found in `attempts/<NNN>/`:
  `parameters.json`, `propeller_mesh.obj`, `render_isometric.png`,
  `render_top.png`, `render_side.png`, `description.txt`.
- The `description.txt` here is a per-attempt narrative (e.g.
  generated alongside the mesh + renders), NOT a DH-saved Q+A.
  DH Q+A `.txt` files were always written under
  `<session_dir>/<agent>/<field>.txt`, NEVER under
  `<session_dir>/attempts/<NNN>/`.
- **Phase 5A key shape** (2026-06-03 onward): folder
  `attempts/<NNN>__<global_id>/` and clean filenames.  Example:
  `<sid>/attempts/001__42/parameters.json`.  The folder encodes
  both the per-session NNN (first, for chronological sort within
  a session) and the Postgres `dc_attempts.attempt_id` (after the
  `__` separator).  Filenames stay as the originals — no
  `<sid>__<NNN>__` prefix.  Pre-Phase-5A keys retain the old
  `attempts/<NNN>/<sid>__<NNN>__<original>` shape; no migration
  is run.  See `retrieve_attempt` design in architecture doc §4
  (locked) and the Phase 5A note in §9.
- Backward-safety hatch: if a direct test caller invokes
  `upload_attempt_artefacts` without `global_attempt_id`, the
  uploader logs a warning and falls back to the pre-5A key shape.
  Production callers (the Database Handler) always pass it.

**Path 3 — `r2_uploader.upload_bytes(content, remote_key)`**
- Called by `agents/database_handler/db_writer.py::save_to_safety_folder`
  when `insert_chunk` exhausts retries.
- No whitelist — the safety file is built in-memory and PUT
  directly to R2 under
  `<session_id>/safety/<scope>/<filename>`.
- The failure-escape-hatch path for Q+A text that couldn't land
  in Postgres.  Architecture doc §3.5 + invariant 12.

**Path 4 — `r2_uploader.upload_file(path, key)` from the archive sweep.**
- Called by `agents/loader.py:_archive_previous_session` for the
  four session log/trace files plus the per-agent histories.
- Keys written:
  - `<sid>/logs/session.log` (the main session log; renamed on
    upload from the local `<sid>.log` — see the Phase 5A rename
    rule below)
  - `<sid>/logs/agent_flow_<ts>.txt`
  - `<sid>/logs/database_handler_<ts>.log`
  - `<sid>/logs/dh_flow_<ts>.txt`
  - `<sid>/logs/agent_histories/history_<agent>.txt`
- **Phase 5A rename rule** (2026-06-03 onward): the main session
  log is the only one of these whose local filename
  (`<sid>.log`) duplicates the folder prefix.  The archive sweep
  rewrites that one filename to `session.log` on upload so the
  R2 key becomes `<sid>/logs/session.log` instead of the
  duplicated `<sid>/logs/<sid>.log`.  The other three log/trace
  files use timestamp-based names and pass through unchanged.
  Pre-Phase-5A keys retain the duplicated shape.

Mental model: paths 1, 2, 4 are happy-path mirrors; path 3 is the
failure escape hatch.

**Status.** In force from Phase 3D (2026-06-02) onward; Phase 5A
key-shape and filename-rename rules from 2026-06-03 onward.


## W31. `_resolve_session_name` slug format depends on whether Postgres is reachable.

Phase 3E (2026-06-02) moved the IDNNN counter source from a
filesystem scan of `previous_sessions/` to a Postgres `SEQUENCE`
named `session_counter`.  This decouples slug generation from the
local Railway volume (which is being retired) and guarantees
globally-unique counters across deploys / container rebuilds /
restarts.

**Happy path** (Postgres reachable, sequence exists):
```
ID{nnn:03d}_{YYYYMMDD_HHMMSS}    e.g. ID042_20260602_193015
```
- The 3-digit padding holds for `nnn < 1000`; beyond that the
  slug naturally extends to 4+ digits (`ID1000_...`).
  Lexicographic sort breaks at the boundary but numeric sort
  by counter remains correct.
- The SEQUENCE persists across pg_dump/pg_restore.

**Fallback path** (Postgres unreachable OR nextval raised — per
design Q-SID-2 = ii: keep DH save alive even with the DB down):
```
ID_{YYYYMMDD_HHMMSS}_{microseconds:06d}    e.g. ID_20260602_193015_524873
```
- No counter — no ordinal in the slug.
- Microsecond suffix gives 1-in-a-million uniqueness per
  second on a single machine.
- A WARNING is logged on every fallback so the operator sees
  the slug isn't in canonical form.

**Implications for tooling / log greps:**

- Scripts that filter by `^ID\d+_` (the historical happy-path
  shape) will MISS fallback-generated session_ids.  Use
  `^ID(\d+_|_)` to match both, or two separate regexes.
- Postgres FK queries don't care — the slug is just a TEXT
  primary key.
- R2 prefixes mix both shapes if Postgres was down during some
  saves; navigation by date works either way (timestamp is in
  both formats).

**Migration on existing v5 deployments.**  Run
`extra_utilities/db_design/migrations/migrate_v5_to_v6.py` to
add the SEQUENCE and seed its initial value from existing
`sessions.session_id` MAX(NNN).  Idempotent.  See architecture
doc §9.10 + the migration script's docstring.

**Regression risk — never roll your own session-name fallback.**
The removed `_next_session_id()` left behind a latent regression:
any code path that branched on "`session_name is None`" and
re-computed via the deleted helper raised `NameError` at runtime.
The archive sweep (`_archive_previous_session(session_name=None)`
in `agents/loader.py`) was one such site — fixed 2026-06-04 by
routing through `_resolve_session_name()` instead.  The bug hid
for ~2 days because the DH save (the common archive caller) always
pre-populates `_BOX.session.resolved_session_name` before archive
runs, so it only surfaced on the End Session "No" (don't-save)
path where DH is skipped.  **When adding code that needs a fresh
session name, ALWAYS use `_resolve_session_name()`.**  Don't
re-implement a name computation, even as a fallback — the
microsecond-timestamp fallback semantics live inside
`_resolve_session_name()` already.

**Status.** In force from Phase 3E (2026-06-02) onward.


## W32. Every vector query against `chunks` MUST use `_invariant_8_where_fragment()`.

The partial HNSW index on `chunks.embedding` (created in schema v4
and preserved through v6) is restricted to rows that retrieval
would actually return:

```sql
CREATE INDEX idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops)
  WHERE NOT is_error AND NOT is_empty AND field_type = 'Semantic';
```

Postgres only consults a partial index when the query's `WHERE`
clause logically implies the index's `WHERE`.  Every vector search
MUST include the literal three predicates:

```sql
WHERE NOT is_error
  AND NOT is_empty
  AND field_type = 'Semantic'
  AND ...   -- additional filters: ACL, embedding_model match, metafilters
```

Forgetting any one of them causes Postgres to fall back to a
sequential scan over the full `chunks` table — correct but ~1000×
slower on a non-trivial corpus, and with no warning emitted at
query time.

### The lock

The literal predicate prefix lives in exactly ONE place:

```python
# tools/database_search/database_search.py
def _invariant_8_where_fragment() -> str:
    return "NOT is_error AND NOT is_empty AND field_type = 'Semantic'"
```

Every vector query in `database_search.py` (the candidate
window-function query, the expansion query, and the
embedding-model-mismatch COUNT query) builds its `WHERE` clause by
interpolating the return value of this helper.  No other vector
query exists today.

### What this means in practice

- **Never** hand-roll a vector query against `chunks`.  Use the
  helper, even for one-off scripts or smoke tests.
- When adding a new query that touches `chunks.embedding <=> ...`,
  build the `WHERE` clause through `_invariant_8_where_fragment()`
  + your additional filters.  Grep for the helper to see live
  examples.
- If you find yourself writing the literal
  `WHERE NOT is_error AND NOT is_empty AND field_type = 'Semantic'`
  in a new file, stop and import the helper instead — the
  duplication is exactly what this invariant prevents.
- The `<=>` operator needs its right-hand-side parameter cast as
  `vector` for Postgres to resolve the operator type.  All live
  query sites do `%(query_vec)s::vector` — preserve that cast
  when reusing the helper.

### What this is NOT

This invariant covers vector queries only — queries against
`chunks` that do not use the `<=>` operator (pure COUNT,
non-vector SELECT, INSERT, etc.) do not need the helper.  The
mismatch COUNT query happens to use it for symmetry and to honour
invariant 8's filter scope, not because COUNT requires the partial
index.

### Status

In force from Phase 4B step 3 (2026-06-03) onward.  Captured as
architecture doc §8 invariant 8 (locked design) and §9.7 +
§9.11 (Phase 4 implementation).


## W33. Per-agent DBa toggle + `RAG_ENABLED` master switch — AND semantics, next-session lifecycle.

Whether a chain agent ends up with `database_search` bound at
session start AND the `$database_search_tool` fragment in its
system prompt is decided by TWO ANDed checks:

1. **Global master switch** `RAG_ENABLED` in
   `workflow_settings/settings.py` (bool, default `True`).
2. **Per-agent flag** in `workflow_settings/database_access.json`
   (one bool per chain agent, default `True` for all 8).  Edited
   via the small "DBa" pill button rendered in each agent box on
   the LLM-routing chart in the Workflow Settings view.

The combined predicate lives in ONE place:
```python
# workflow_settings/database_access.py
def is_enabled_for(agent: str) -> bool:
    if not bool(getattr(_workflow_settings, "RAG_ENABLED", False)):
        return False
    return get(agent)
```

If you add a new check or shortcut path that decides "does this
agent get RAG?", route it through `is_enabled_for` — do NOT read
the per-agent flag directly, because that bypasses the master
switch.

### Two places the flag affects behaviour

* **Tool binding.**  In each of the 8 chain agents'
  `set_tools` / `set_routing_tools`:
  ```python
  if database_access.is_enabled_for("<slug>"):
      _tool = make_database_search_tool("<slug>")
      ... add to the agent's bound tool surface ...
  ```
  When off, the `database_search` tool is NOT in `bind_tools(...)`
  and the LLM never sees it as an option.

* **System prompt.**  Each chain agent's `prompt.md` wraps the
  database section in `<<HAS_DBA>>...<</HAS_DBA>>` markers.  At
  template-build time, `agents/shared/prompts.py::apply_dba_filter`
  unwraps the region when `is_enabled_for(agent_dir_name)` returns
  `True`, strips it entirely otherwise.  No orphaned heading line.

* **Phase 5E extension.**  The two retrieve_* tools shipped in
  Phase 5B/5C (`retrieve_user_inputs`, `retrieve_attempt`) share
  the SAME `is_enabled_for(<slug>)` gate as `database_search`.
  Each chain agent's binding block conditionally appends BOTH
  retrieve tools alongside `make_database_search_tool(...)`; each
  `<<HAS_DBA>>...<</HAS_DBA>>` region carries the new
  `$retrieve_user_inputs_tool` and `$retrieve_attempt_tool` slot
  references after `$database_search_tool`.  Flipping a DBa flag
  off strips all three RAG tools from that agent as a unit.  See
  also W35 for the dispatcher pattern the two retrieve tools rely
  on for image content-block delivery.

### Lifecycle

Changes take effect on the NEXT session — same semantics as every
other workflow-settings edit.  Per-agent templates are built ONCE
at module-import time (`prompts.py::_build_template`) and tool
binding happens at agent construction.  Mid-session toggles do not
affect the currently-running agents.

### Editing surface

* **Master switch** — checkbox for `RAG_ENABLED` in the flag list
  under the LLM-routing chart; or `workflow_settings/settings.py`
  directly.
* **Per-agent** — DBa button in each agent box; or
  `workflow_settings/database_access.json` directly.  The JSON has
  one top-level key per chain agent slug (lowercase_snake,
  matching `database_access.DEFAULT_AGENTS`); missing keys default
  to `True`.
* **Endpoints** — `GET /api/database-access` returns
  `{flags, rag_enabled}`; `POST /api/database-access` body
  `{agent, enabled}` updates one agent.  Both endpoints reject
  mid-session writes with HTTP 409 (same lock as `/api/settings`
  and `/api/llm-routing`).

### UI behaviour the operator should know

* When the master switch is OFF, every DBa button visually dims
  (`opacity: 0.45`, dashed border) so the inert state is obvious,
  but the buttons remain clickable for staging the next master-on
  config.  A yellow banner above the chart explicitly states the
  master switch is off.
* When the global LLM override is active (provider dropdown set
  to anything other than "Use individual LLMs"), the provider +
  model controls inside each agent box are locked + dimmed, but
  the DBa button stays solid and clickable — DBa is orthogonal to
  LLM routing.  The CSS targets the `.lr-provider-select` and
  `.lr-model-input` directly, NOT the container, exactly so the
  DBa button isn't caught in the lock.

### Status

In force from 2026-06-03 onward.  Touches
`workflow_settings/{settings,database_access}.py`,
`workflow_settings/database_access.json`, `agents/shared/prompts.py`,
all 8 chain agent `prompt.md` + `<agent>.py` modules, `web_app.py`
(two new endpoints), and the web frontend (button + banner +
legend + dimming).


## W34. "Database" admin view — password-gated destructive endpoint.

The seventh side-menu view ("Database") is a developer-only
console gated by the `PASSWORD_DATABASE_WEB_UI` environment
variable.  When unset, every auth attempt is rejected so a
forgotten env var can never leave the destructive endpoint
exposed.

### Single action today: TRUNCATE every data table except
`dc_parameter_schemas`

Triggered by typing the literal phrase `reset_database` in the
view's text input and clicking Send (or pressing Enter), after
the password unlock step succeeds.  The action runs in a single
transaction:

```sql
TRUNCATE TABLE chunks, dc_attempt_parameters, dc_attempts,
               rag_queries, sessions
  RESTART IDENTITY CASCADE;
```

* `dc_parameter_schemas` is intentionally absent from the
  `RESET_TABLES` list in `web_app.py`.  Preserves the 17-parameter
  schema seed so the system stays usable without re-running
  `populate_dc_parameter_schemas.py`.
* The `session_counter` SEQUENCE is left alone.  Next session
  continues from the current count, not reset to 1.  Operator can
  manually `ALTER SEQUENCE session_counter RESTART WITH 1;` via
  psql if a fully-fresh IDNNN run is wanted.
* Pre-truncate row counts per table are captured and returned in
  the response so the operator sees what was deleted.

### Two endpoints, both gated

* `POST /api/db_admin/auth`  body `{password}`  →  `{ok, error?}`.
  Used by the UI for immediate "wrong password" feedback before
  the operator types the destructive phrase.  Always HTTP 200;
  `ok` discriminates.  Compares via `hmac.compare_digest`.
* `POST /api/db_admin/reset`  body `{password, phrase}`  →
  `{ok, before_counts?, tables_wiped?, error?}`.  Re-validates
  BOTH the password AND the literal `reset_database` phrase
  server-side, so the endpoint cannot be invoked by anyone who
  skipped the UI's unlock step.  Logs at WARNING level on success
  with the before-counts.

### UI lifecycle

* Locked view = password input.  Successful auth flips to the
  reset card.  Unsuccessful = inline error.
* After a successful reset, the view auto-re-locks 4 s later so a
  subsequent destructive action requires re-authentication.
* The password is held in a JS module-local variable ONLY.
  Refreshing the page requires re-entering it.  Never written to
  `localStorage` / `sessionStorage`.
* Switching to any other view and back also re-locks.

### Status

In force from 2026-06-03 onward.  See `web_app.py`'s
`api_db_admin_auth` / `api_db_admin_reset`, `web/index.html`'s
`<section class="view database-view">`, and the controllers at
the bottom of `web/app.js` (Database view section).


## W35. retrieve_* tools are dispatcher-handled; their @tool stubs must return "".

The two retrieve tools shipped in Phase 5B/5C
(`retrieve_user_inputs`, `retrieve_attempt`) are split into THREE
pieces, mirroring the existing `load_input_images` pattern:

1. A public `@tool`-decorated stub returned by the closure factory
   (`make_retrieve_user_inputs_tool(slug)` /
   `make_retrieve_attempt_tool(slug)`).  The stub's body returns
   `""` (empty string) and exists only to satisfy langchain's
   `bind_tools(...)` contract.  The LLM sees the docstring +
   argument schema; calling it directly via
   `tool_fn.invoke(args)` yields an empty ToolMessage.
2. A private `_run_retrieve_*` function in the same module that
   does the real work (Postgres lookup, R2 fetch, XML assembly,
   image content-block emission, `rag_queries` log).
3. A central dispatcher
   `dispatch_retrieve_tool(agent, tc, agent_key)` in
   `agents/shared/retrieve_tool_dispatcher.py`.  The dispatcher
   inspects the tool call's name, invokes `_run_retrieve_*` with
   the agent's provider, appends the XML as a `ToolMessage` to
   `agent.messages`, and (when image bytes are present) buffers
   them for the next `HumanMessage` via `append_pending_images`.

### Why the split

Image content blocks have to attach as a separate `HumanMessage`
(or buffered for it) so the tool_use → tool_result contiguity
invariant is preserved when the LLM batches the retrieve_* tool
call with other tool calls.  A plain `@tool` whose body returns
the XML string can ONLY append a ToolMessage — it cannot inject
image content blocks for the next message.  The dispatcher
pattern (mirroring `dispatch_user_inputs_tool` for
`load_input_images`) lets the same tool call produce two attached
pieces of evidence (XML text + images) in the agent's next view.

### Each chain agent's run loop calls the dispatcher

Phase 5E added one
`if dispatch_retrieve_tool(self, tc, "<slug>"): continue` line to
each of the 8 chain agents' run loops, placed BEFORE the agent's
normal tool dispatch (`_tools_by_name` /
`_extra_utility_tools_by_name` / etc.) so retrieve_* names are
caught first and never fall through to the stub.

If that dispatch line is removed, moved BELOW the stub-finding
branch, or fails to return early (`continue`), the stub fires and
the agent receives an empty ToolMessage.  The agent typically
retries the same call (assuming a transient error), wasting LLM
turns until step-cap exhaustion.

### Adding a third dispatcher-handled tool later

Same checklist as the existing two:

1. Define the tool in its own module under `tools/<tool>/`:
   closure factory + `@tool` stub returning `""` + private
   `_run_*` doing the work.
2. Add a new handler to
   `agents/shared/retrieve_tool_dispatcher.py` and register the
   tool name in `_HANDLERS` (with the matching name added to
   `RETRIEVE_TOOL_NAMES`).
3. The chain agents need NO change — the same
   `dispatch_retrieve_tool(...)` line already catches any name
   that `_HANDLERS` registers.

### Status

In force from Phase 5B/5C (2026-06-03+) onward.  Two consumers
today (`retrieve_user_inputs`, `retrieve_attempt`).

## W36. `/api/turn` is async (HTTP 202 + SSE `turn_done`) — do NOT regress it to sync.

**Where.**  `web_app.py:api_turn` + `web_app.py:_run_turn_in_background`
plus the `turn_done` branch in `api_events`; `web/app.js:sendMessage`,
`web/app.js:finalizeTurn`, and the `turn_done` branch in
`startEventStream`'s SSE handler.

**Why this is load-bearing.**  The first complex turn — multi-image
input flowing through all 8 chain agents — routinely takes 5+
minutes on the cloud deploy.  Railway's edge proxy (and Cloudflare
in front of it) gives up on the upstream long before then and
serves a plain-text `"upstream error"` body to the browser.  The
browser's `res.json()` then crashes with
`SyntaxError: Unexpected token 'u', "upstream error" is not valid
JSON` and the user sees a "(network error …)" chat bubble even
though the backend successfully finished the turn (2026-06-04
incident; the user saved the relevant LOG file outside the repo).

The fix mirrors the `/api/end` 202+SSE pattern (same root cause
that produced the 2026-05-30 duplicate-save bug — see the comment
above `_END_IN_FLIGHT`).  `/api/turn` now returns HTTP 202 +
`{turn_id}` immediately; the multi-agent pipeline runs in
`asyncio.create_task(_run_turn_in_background(...))` decoupled from
the HTTP request's lifecycle; the reply lands as a single
`turn_done` SSE event on the already-open `/api/events` stream
(which pings every 10 s and never trips a proxy idle timeout).

### Do NOT, when editing this code path:

1. **Re-synchronise `/api/turn`.**  Returning the reply on the
   POST body restores the original timeout bug.  Even a "fast"
   simple turn that takes 3 s today can grow to 6+ min later —
   the async shape should hold for any duration.
2. **Add an `await` between the `_TURN_IN_FLIGHT` check and the
   `_TURN_IN_FLIGHT = True` write.**  Same single-worker-event-
   loop atomicity argument as `_END_IN_FLIGHT` (W13/O9): no
   preemption between sync statements, but an `await` would
   create a race where two concurrent `/api/turn` POSTs both
   pass the check.
3. **Move `viz_publish` out of `_run_turn_in_background`'s
   `finally`.**  The publish runs in `finally` so EXACTLY ONE
   `turn_done` event fires per turn — success or exception.  If
   a future edit moves it into the `try`, the frontend's pending
   bubble will hang forever on any exception inside
   `dispatch_turn`.
4. **Forget to clear `_TURN_IN_FLIGHT` in `finally`.**  Same
   reasoning — if it's only cleared on the happy path, an
   exception inside `dispatch_turn` would lock the chat out
   until the server restarts.
5. **Change the `turn_done` payload shape without updating
   `finalizeTurn`.**  The frontend reads `turn_id`, `ok`,
   `reply`, `forwarded`, `artefacts`, `error` — drop or rename
   any and the chat bubble fails open (no render, hung pending
   state).
6. **Remove the `_pendingTurns.delete(turn_id)` cleanup.**
   Long-lived sessions would accumulate unbounded entries if
   `finalizeTurn` skipped that delete.  Today this is bounded by
   the `_TURN_IN_FLIGHT` singleton (at most one entry at a
   time), but if the singleton ever relaxes the cleanup becomes
   load-bearing.

### Regression-catcher

`extra_utilities/smoke_test_async_turn.py` covers the five
properties above (202 + `turn_id` shape, 400 on empty, 409 on
concurrent, end-to-end SSE round-trip, flag cleared after
completion).  Run it from your venv before any commit that
touches `api_turn`, `_run_turn_in_background`, or the
`turn_done` SSE branch.

### Status

In force from 2026-06-04 onward.  Sister entry to the (untitled)
`/api/end` async lesson encoded in `_END_IN_FLIGHT`'s comment
block in web_app.py.

## W37. The Stop button is two layers — L1 (in-loop polls) AND L2 (asyncio task cancel) — don't drop either.

**Where.**  `agents/shared/stop_signal.py` (the `StopRequestedError`
exception + `check_stop_or_raise()` helper); `agents/dispatch.py`
(the `except StopRequestedError` catch site in `dispatch_turn`);
each of the 7 chain agents' run loops plus the Orchestrator's
inner-step loop (one `check_stop_or_raise()` at the top of the
outer `for _ in range(MAX_<X>_STEPS)` loop AND one at the top of
the inner `for [i, ]tc in ... response.tool_calls` loop);
`web_app.py` (the `_current_turn_task` module-level ref, its
assignment in `api_turn`, its `.cancel()` in `api_stop`, and the
`except asyncio.CancelledError` handler in
`_run_turn_in_background`).

**Why this is load-bearing.**  Before the L1+L2 sprint the Stop
button polled `is_stop_requested()` only at the Orchestrator's
hop boundaries (`orchestrator.py:508`).  Worst-case latency was
~30-60 s: the currently-running LLM call AND the currently-
running tool call BOTH had to finish before the next hop check
caught the stop.  Image-heavy turns could keep the UI "busy" for
a full minute after the user clicked Stop.

Two complementary fixes ship together:

  * **L1 — fine-grained polls inside the chain agents' loops.**
    Each iteration of the outer + inner run-loop calls
    `check_stop_or_raise()` which raises `StopRequestedError` when
    the flag is set.  `dispatch_turn`'s catch site turns that
    into the existing "(Session interrupted by Stop button...)"
    reply.  This actually stops the work — the next agent step
    bails before another LLM call or tool call fires.  Typical
    latency drops to ~3-10 s, worst case ~30 s if mid-vision-LLM-
    call (the LLM call itself isn't interrupted).
  * **L2 — `/api/stop` also `.cancel()`s the asyncio Task.**
    `_run_turn_in_background`'s `await run_in_threadpool(...)`
    raises `CancelledError`; the new `except` handler publishes
    `turn_done` immediately with the interrupted reply; the
    frontend's `finalizeTurn` renders it and unblocks the
    composer within ~1 s.  The threadpool thread keeps running
    until its next L1 poll catches the stop, then bails
    naturally; its return value is discarded since nothing is
    awaiting it.

### Do NOT, when editing this code path:

1. **Remove `check_stop_or_raise()` from any chain agent's outer
   OR inner loop.**  Dropping the outer poll restores the old
   ~30-60 s latency.  Dropping the inner poll lets a stop click
   right before a 30 s `generate_and_render_propeller` call wait for
   the full mesh to render.
2. **Remove the `except StopRequestedError` catch in
   `dispatch_turn`.**  Without it, a stop mid-pipeline propagates
   as an unhandled exception out of `_run_turn_in_background`,
   which logs it as "background turn task raised" and surfaces
   it to the user as a confusing "(internal error...)" bubble.
3. **Move the `viz_publish` call OUT of
   `_run_turn_in_background`'s `finally`.**  The CancelledError
   path depends on the `finally` running to publish `turn_done`
   before the task is marked CANCELLED.  Moving the publish into
   the `try` would skip it on CancelledError and the UI would
   hang.
4. **Forget the `raise asyncio.CancelledError()` re-raise at the
   end of `_run_turn_in_background`'s `finally`.**  A coroutine
   that swallows CancelledError logs a warning at GC time
   ("coroutine raised StopIteration") and confuses asyncio's
   task-state machine.  Re-raise so the task is properly marked
   CANCELLED.
5. **Forget to set OR forget to clear `_current_turn_task`.**
   Set it in `api_turn` immediately after `asyncio.create_task`;
   clear it in `_run_turn_in_background`'s `finally`.  A stale
   non-None reference would let a Stop click cancel the NEXT
   turn's task.  A missing assignment in `api_turn` would make
   Stop a no-op for the UI (only L1 would fire).
6. **Add an `await` between the `_TURN_IN_FLIGHT = True` write
   and the `_current_turn_task = asyncio.create_task(...)`
   assignment in `api_turn`.**  Same atomicity argument as W36
   #2 — an `await` in between would create a race where Stop
   fires AFTER the singleton is reserved but BEFORE the task ref
   is set, so the cancel is a no-op and the UI hangs.

### Acknowledged caveats (documented, NOT bugs to fix)

  * The threadpool thread inside `run_in_threadpool` cannot be
    truly killed — Python threads have no preemptive abort.  It
    bails cooperatively on its next L1 poll, which is usually
    <10 s but can be ~30 s if mid-vision-LLM-call.  During that
    window it might still append a few lines to
    `session.chain_log_exchanges` (the only shared mutable state
    a bailing agent touches before unwinding); ordering may
    interleave with a new turn but no semantic corruption.  If
    you ever observe a real corruption, escalate to L4 (subprocess
    isolation — see TODO F-item the original /api/turn ticket
    flagged).
  * The Database Handler's run loops in
    `agents/database_handler/database_handler.py` are NOT
    polled.  DH runs only at End Session (`/api/end`), a separate
    flow that has its own background task and its own Stop story
    (today: none — End Session cannot be interrupted).  If End
    Session ever needs a Stop, it gets its own design pass.

### Regression-catcher

`extra_utilities/smoke_test_async_turn.py` (extended on the
L1+L2 ship) covers the stop path: open SSE, POST /api/turn, POST
/api/stop, assert the matching `turn_done` arrives carrying the
"(Session interrupted...)" reply within 2 s.  Run it from your
venv before any commit that touches `api_stop`,
`_run_turn_in_background`'s cancellation handler, or any chain
agent's run-loop poll.

### Status

In force from 2026-06-04 onward.  Companion entry to W36
(`/api/turn` async-by-design).

## W38. Multimodal `chunks_mm` embedding parameters are LOCKED in code (currently non-modifiable in the UI).

**Where.** `agents/shared/voyage_mm.py` (the dedicated Voyage client
for the DB layer) + `agents/database_handler/db_writer_mm.py` (the
mirror writer) + the `chunks_mm` table (schema v8).  Surfaced
READ-ONLY in the web UI's "Database options" panel (Single-vector
multimodal section).

**What.** The multimodal index uses ONE fixed parameter set, recorded
here so a future session does not have to re-derive it (and so the
UI's read-only display and the code stay in sync):

  * embedding model   = `voyage-multimodal-3.5`
  * output dimension  = `2048` (Voyage's max; stored `vector(2048)`,
    HNSW indexed via a `halfvec(2048)` cast — pgvector's float
    `vector` HNSW caps at 2000 dims)
  * max image side    = `1536` px (resize-before-send; preserves fine
    hand-drawn-sketch annotations better than the harness's 1024 px
    while bounding pixel-token cost)
  * input_type        = `document` for all stored rows (`query`
    reserved for read time — not wired yet)
  * call mode         = single-item (one input per request; per-item
    error isolation for the one-time backfill)
  * image+text fusion = ON.  User image fused with its `_note.txt`;
    render fused with the attempt's `description.txt`.  Image-only
    fallback when the associated text is missing.
  * embedding_model string = `voyage/voyage-multimodal-3.5/2048`

**Why "currently non-modifiable".** At this phase the Database
options panel DISPLAYS these values but does not let the operator
edit them (the boxes are not wired to change behaviour yet).  Making
them live tunables is a later phase.

**Cross-refs.** Architecture doc §6.3 (canonical design rationale,
incl. the no-VLM-caption decision), TODO_known_issues.md F37
(re-evaluate VLM-enriched user-image text), F36 (mini-eval harness).

**Update tracker.** If any value above changes, update this entry,
§6.3, and the UI panel's read-only display together.

## W39. Adding a new database_search backend (embedding model / chunks table) — the single extension point.

**Where.** `tools/database_search/database_search.py::_resolve_search_backend`.

**What.** `database_search` routes to a backend (table + cosine-distance
SQL expr + embed function) chosen by the Database-options mode
(`workflow_settings/db_options_config.py`).  Today: `text-only` ->
`chunks` (OpenAI, `::vector`); `single-vector-multimodal` -> `chunks_mm`
(Voyage voyage-multimodal-3.5, `::halfvec(2048)`); `late-interaction-
multimodal` -> text-only placeholder.

To add a NEW embedding model with its own chunks table (a new mode),
edit these FOUR places — nothing else:
  1. `_resolve_search_backend` — add a branch returning the table name,
     the cosine-distance SQL expr (with the right cast for that table's
     index), and `is_multimodal`.
  2. `db_options_config.VALID_MODES` (+ a `MODE_*` constant).
  3. The embed step in `_run_search_pipeline` — wire the new model's
     QUERY embedding (only if it is neither OpenAI nor the existing
     Voyage path).
  4. The web "Database options" panel (a new column) + its read-only
     param display.

`<search_meta>` reports `mode=` (the selected mode) and `db=` (the
resolved table) VERBATIM, so the emitter / meta code needs NO change
for a new backend.  The 3 SQL builders already take `table` +
`dist_expr` params, so they need no change either.

**Why this entry exists.** So a future model addition doesn't miss one
of the four spots (especially the embed step) or hand-edit the meta
emitter.  See architecture doc §4.11 + §9.15; the read-routing TODO is
F39.

**Status.** In force from 2026-06-16 (the read-routing build).

---

## W40. Prompt-cache breakpoints: one ttl feeds both, and the reduced-agent systems lack them

**Two Anthropic cache breakpoints are emitted per in-session request**: an EXPLICIT one on
the system prompt (`make_system_message`) and Anthropic's TOP-LEVEL automatic one (the
`cache_control` kwarg forwarded by `invoke_with_retry`). They are documented as compatible
and together consume 2 of the 4 available breakpoint slots.

**The trap.** Anthropic returns a **400** when the automatic breakpoint lands on a block
that already carries an explicit `cache_control` with a **different** ttl. Both markers are
therefore built from the single `PROMPT_CACHE_TTL` setting, via
`llm_provider.system_cache_control()` / `history_cache_control()`. **Never hand-write a
`cache_control` dict at a call site** — route it through those helpers, or a future edit can
reintroduce a ttl mismatch that only fails at runtime, on Anthropic, in production.

**Also:** `cache_control` is Anthropic-only. Both helpers return `None` for every other
provider, so the kwarg is omitted entirely and the request stays byte-identical to the
pre-caching shape. A Claude model served through **OpenRouter** runs as
`provider == "openrouter"` and therefore gets **no caching at all** — expected, not a bug.

**Scope gap.** The 8-agent topology, the 5-agent one (Conductor + Creator) and the
post-session **Database Handler** all pass the kwarg; the **3-agent topology does not**
(TODO F53). Two call sites are excluded ON PURPOSE and must stay that way: the **Context
Pruner** (rare one-off summarisation) and each hub's **feedback-dispatch** call, which
sends a freshly-built one-off message list so a breakpoint there could only ever write an
entry nothing can match. The rule: **only call sites whose message list persists across
turns, or repeats across calls, get the history breakpoint.**

**Two settings PAIRS, one mechanism.** The save phase uses the *same* helpers, markers and
request shape as the session — it differs only in which settings it reads. `phase="save"`
selects `PROMPT_CACHE_SCOPE_SAVE` / `PROMPT_CACHE_TTL_SAVE` (§30); everything else defaults
to `phase="session"` and reads §29. **Both markers on a given call must come from the same
phase** — mixing them re-opens exactly the ttl-mismatch 400 described above, which is why
`make_system_message` takes the phase too rather than always reading the session setting.

**The label is load-bearing.** `token_usage._phase_for()` decides how to price an unsplit
cache write by testing `agent_name.startswith("DH")`. Every DH call site is labelled
`DH-decide` / `DH-formulate` / `DH-compress` / `DH-force-tool-<n>` / `DH<-<agent_key>`, and
no in-session agent name starts with `DH` (`DCIC`/`DCII`/`DCOI` start with `DC`). **A new DH
call site must keep the prefix, and no agent may ever be named `DH*`** — otherwise its
writes get priced at the wrong phase's ttl the moment the two ttls diverge.

**Status.** In force from 2026-08-04 (the conversation-history-caching change; the
Database Handler joined the same day). See `extra_utilities/design_prompt_caching.md`
and `workflow_settings/settings.py` §29–§30.

**Unverified assumption (2026-08-04).** Whether the **top-level** `cache_control`
request parameter honours a `ttl` field is NOT confirmed — every documented example
of the top-level form is the bare `{"type": "ephemeral"}`, and `ttl` is documented
on *block-level* markers. If it is ignored, choosing `PROMPT_CACHE_TTL="1h"` yields
a 1-hour system anchor and a 5-minute history breakpoint. Verify with a deliberate
>5 minute gap before drawing conclusions from a `1h` A/B; the smoke test cannot
detect it (back-to-back calls hit under either ttl).

**Fail-open.** `invoke_with_retry` catches a rejection that NAMES `cache_control`,
latches `_CACHE_KWARG_DISABLED` process-wide, and retries without the kwarg — so a
binding/API that rejects it degrades caching to off instead of killing every
in-session Anthropic turn. If caching mysteriously stops, grep the session log for
"prompt-cache kwarg rejected".

## W41. `database_search` no longer exposes `metafilters` or `attempt_specific_flag` — the plumbing is still there

**Changed 2026-08-20** (owner's decision, during the RAG tool customization).
Both parameters were removed from the LLM-facing `@tool` signature in
`tools/database_search/database_search.py`.  The tool an agent sees is now
`database_search(query, n)`.

**The implementation was NOT ripped out.**  `_parse_metafilters`, the
`_METAFILTER_SPEC` key table, the WHERE-clause builder, the attempt-ranked
branch of `_database_search_impl`, and their error types are all still present
and still work.  The stub simply calls the impl with `attempt_specific_flag =
False` and `metafilters = None`, hard-coded.

**Why:** the two `Annotated` descriptions were the single largest thing the
tool ships, and a tool schema is re-sent to the model on EVERY turn, for every
agent that binds it.  Rough estimate ~180 tokens per agent per turn for the
description text alone, before the JSON-schema wrapper.

**What was actually given up.**  Be honest about this if you are reading it
back later:

* `attempt_specific_flag` — little real loss.  The replacement path is
  search sessions, read the `<available_attempts>` ids in the response, then
  call `retrieve_attempt`.  That is one extra call but returns MORE (the full
  parameter set and the attempt's description, not a ranked summary).
* `metafilters` — a REAL capability loss with no replacement anywhere in the
  system.  An agent can no longer restrict the candidate pool before ranking,
  e.g. `{"has_renders": true, "satisfaction": ">=7"}` to learn only from
  sessions the user was actually happy with.  The prompts still tell agents to
  seek calibration evidence from past sessions; they now do it without any
  hard filter.  If retrieval quality disappoints, THIS is the first thing to
  reconsider — re-exposing just `satisfaction` would recover most of it.

**To re-expose either one, undo exactly three things:**

1. the `Annotated[...]` parameter block in the `database_search` stub
   (`make_database_search_tool`, near the end of the module);
2. the two hard-coded arguments in the `_database_search_impl(...)` call
   directly below it;
3. the one prompt sentence naming the arguments, in
   `DC_prompt_fragments/tools_config/database_search.md` — the ONLY prompt
   file in any tree that mentions them.

**Two dead branches this leaves behind**, deliberately not deleted:

* `_emit_no_results(metafilters_applied)` can now only ever be called with
  `False`, so its "may be related to the metafilters" wording is unreachable.
* `<search_meta>` no longer emits a `metafilters` attribute (it could only
  ever have been `{}`).  `attempt_specific` is still emitted and is now
  likewise always `"false"` — left in place pending a separate decision.

