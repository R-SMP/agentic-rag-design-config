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
