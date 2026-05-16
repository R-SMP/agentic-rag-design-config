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
