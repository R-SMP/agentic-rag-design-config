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

## W15. The project venv lives at the worktree's PARENT, not in the worktree.

**Where.** `C:\Users\vince\MT Coding\tests\test11_v4_git\.venv\`
holds the Python 3.13 environment with the project's actual
dependencies (langchain, langchain-openai, anthropic, trimesh, …)
installed.  Worktrees under
`C:\Users\vince\MT Coding\tests\test11_v4_git\.claude\worktrees\<name>\`
do NOT carry their own venv and inherit nothing automatically —
running `python` from inside a worktree picks up whatever the
shell's `PATH` resolves to, which on this machine is the system
Python 3.8 install that does NOT have the project dependencies.

**Why this matters.** Smoke tests that say "run `python -c ...`"
will silently use the wrong interpreter and either fail with
`ModuleNotFoundError: langchain_core` or, worse, succeed against
a Python 3.8 install whose other packages are different versions
than what the project was developed against (e.g. numpy 1.24.4
rather than the requirements-pinned numpy 2.x).

**How to run smoke tests reliably.** Either:
  * Use the venv's interpreter explicitly:
    `"<repo>/.venv/Scripts/python.exe" -c "..."` or
    `"<repo>/.venv/Scripts/python.exe" -m streamlit run ...`
    where `<repo>` is the worktree's parent (e.g. the literal
    `C:\Users\vince\MT Coding\tests\test11_v4_git`, not the
    worktree path).
  * Or `source` / activate the venv first in the shell:
    `"<repo>/.venv/Scripts/activate"` (Git Bash) or
    `"<repo>/.venv/Scripts/Activate.ps1"` (PowerShell).

**Pip installs in agent shells.**  If you `pip install <pkg>`
from inside a worktree using the bare `python` interpreter, the
install lands in whatever Python the shell resolves — typically
NOT the project venv.  Always prefix with the venv's full
interpreter path:
`"<repo>/.venv/Scripts/python.exe" -m pip install <pkg>` —
or activate the venv first.

**Update tracker.** When this convention changes (the user moves
to per-worktree venvs, or to a tool like `uv`/`hatch` that
provisions per-checkout environments automatically), update this
entry rather than letting it rot.

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


## W18. The DH's `save_attempt_data` tool is bound ONLY during the force-tool turn.

The Database Handler is otherwise tool-less, and its prompt says
so explicitly.  The single exception is the **force-tool turn**
that fires once per identifying attempt-specific schedule row
(``scope="attempt"`` AND ``parent_id is None``).  On that turn,
``_run_force_tool_phase`` calls
``self.llm.bind_tools([save_attempt_data],
tool_choice="save_attempt_data")`` to construct a
PER-TURN tool-bound LLM; the per-turn binding is then thrown away
and the next turn uses ``self.llm`` unbound.

### Why this matters

* The DH's prompt is calibrated against a tool-less default.  If
  ``save_attempt_data`` were bound to ``self.llm`` for every
  turn (rather than per-force-tool-turn), the model would emit
  spurious tool calls on session-scoped rows and sub-rows,
  breaking the ASK:/SAVE: protocol.
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

**Path 1 — `r2_uploader.upload_directory(session_dir, suffixes=...)`**
- Called ONCE at the end of
  `agents/database_handler/database_handler.py::populate_database`.
- Walks `<session_dir>` recursively and uploads any file whose
  suffix matches the whitelist.
- Phase 3D whitelist: `(".png", ".jpg", ".jpeg")`.
- What lands here: user-input reference images snapshotted by
  `_collect_user_inputs` into `<session_dir>/user_inputs/`.
- What USED TO land here (pre-3D): the DH's per-Q+A `.txt` files
  too.  Removed because Postgres `chunks` is the sole Q+A store
  in the happy path now (§3.5 / invariant 12).

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
- Unchanged by Phase 3D.

**Path 3 — `r2_uploader.upload_bytes(content, remote_key)`**
- Called by `agents/database_handler/db_writer.py::save_to_safety_folder`
  when `insert_chunk` exhausts retries.
- No whitelist — the safety file is built in-memory and PUT
  directly to R2 under
  `<session_id>/safety/<scope>/<filename>`.
- The failure-escape-hatch path for Q+A text that couldn't land
  in Postgres.  Architecture doc §3.5 + invariant 12.

Mental model: paths 1 + 2 are happy-path mirrors; path 3 is the
failure escape hatch.

**Status.** In force from Phase 3D (2026-06-02) onward.


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

**Status.** In force from Phase 3E (2026-06-02) onward.
