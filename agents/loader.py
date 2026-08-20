"""Entry point for the multi-agent design configurator system.

Sets up logging, prompts the user for configuration (mesh checks, RAG,
optional DC Input Inspector, chain-access toggle), builds the
Orchestrator (which builds every sub-agent and resolves each
agent's LLM via ``agents/<name>/.env`` → ``agents/.env``), and runs
the interactive REPL.
"""

import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from agents.dispatch import dispatch_turn
from agents.hub import build_hub
from agents.shared.llm_provider import list_agent_configs
from agents.shared.routing_tools import AGENT_DISPLAY
from agents.shared.session import Session
from agents.shared.trace import close_trace, init_trace
from config import (
    ATTEMPTS_DIR,
    DATABASE_DIR,
    INPUT_IMAGES_DIR,
    LOGS_DIR,
    PREVIOUS_SESSIONS_DIR,
    USER_INPUTS_DIR,
)
from tools import set_mesh_checks, set_render_library, set_geometry_backend
from workflow_settings import settings as workflow_settings


# ---------------------------------------------------------------------------
# Session archival
# ---------------------------------------------------------------------------


# Module-level handle to the project's logger.  Resolves to the
# same singleton ``_setup_logger`` later configures with file
# handlers — Python's logging.getLogger() caches by name, so the
# reference here stays valid AND uses whatever handlers the
# session-time setup attaches.  Needed by _resolve_session_name's
# Postgres-down fallback (Phase 3E).
logger = logging.getLogger("propeller_agent")

_ID_RE = re.compile(r"^ID(\d+)_")
_LOG_TS_RE = re.compile(r"session_(\d{8}_\d{6})\.log$")


def _session_datetime_slug(log_files: list[Path]) -> str:
    """Prefer the timestamp embedded in an existing session_*.log filename;
    fall back to the current time."""
    for f in log_files:
        m = _LOG_TS_RE.search(f.name)
        if m:
            return m.group(1)
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _resolve_session_name() -> str:
    """Return the session folder name + DB session_id slug.

    Phase 3E (2026-06-02): the counter source moved from a
    filesystem scan of ``previous_sessions/`` (the old
    ``_next_session_id`` helper, since removed per Q-3E-1 = α) to
    the Postgres ``session_counter`` SEQUENCE.  This decouples
    slug generation from the local volume (which is being retired)
    and guarantees globally-unique counters across deploys,
    container rebuilds, and restarts.

    Two output shapes:

    * **Happy path** — Postgres reachable, ``nextval`` succeeds::

          ID{nnn:03d}_{YYYYMMDD_HHMMSS}    e.g. ID042_20260602_193015

      The 3-digit padding holds for nnn < 1000; beyond that the
      slug naturally extends to 4+ digits.  See architecture doc
      §9.10 + the chunks-table NOTE in
      ``database_PostgreSQL_schema_v6.sql``.

    * **Fallback** — Postgres disabled OR ``nextval`` raised
      (per Q-SID-2 = ii — keep the DH save flow alive even when
      the DB is unreachable)::

          ID_{YYYYMMDD_HHMMSS}_{microseconds:06d}
                                    e.g. ID_20260602_193015_524873

      A WARNING is logged so the operator sees the slug isn't in
      canonical form.  See warnings_developer.md W31.

    Same naming convention is used by ``_archive_previous_session``
    for its destination folder under ``previous_sessions/`` —
    that helper just reads the cached
    ``Session.resolved_session_name`` and never re-resolves.
    """
    log_files = list(LOGS_DIR.glob("*.log")) if LOGS_DIR.exists() else []
    slug = _session_datetime_slug(log_files)

    # Happy path — try Postgres first.
    try:
        from agents.shared import postgres_pool
        if postgres_pool.is_enabled():
            with postgres_pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT nextval('session_counter')")
                    row = cur.fetchone()
                    if row is None or row[0] is None:
                        raise RuntimeError(
                            "nextval('session_counter') returned no row"
                        )
                    nnn = int(row[0])
            return f"ID{nnn:03d}_{slug}"
    except Exception as exc:
        logger.warning(
            f"[loader] session_counter nextval failed "
            f"({type(exc).__name__}: {exc}); "
            f"falling back to timestamp-with-microseconds slug "
            f"per Q-SID-2 = ii (W31)."
        )

    # Fallback path — Postgres not configured OR sequence call raised.
    ts = datetime.now()
    return f"ID_{ts:%Y%m%d_%H%M%S}_{ts.microsecond:06d}"


def _resolve_session_timestamp() -> str:
    """Return the timestamp slug computed at session START.

    Reads it back from the existing ``session_<TS>.log`` file the
    loader created in ``_setup_logger``, so post-session tasks (the
    DH in particular) can name THEIR files with the SAME timestamp
    instead of using ``datetime.now()`` at task-start.  See
    ``extra_utilities/warnings_developer.md`` (W11).
    """
    log_files = list(LOGS_DIR.glob("session_*.log")) if LOGS_DIR.exists() else []
    return _session_datetime_slug(log_files)


def _archive_previous_session(
    session_name: str | None = None,
    was_saved: bool = False,
) -> None:
    """Move the previous session's artefacts into
    ``previous_sessions/{session_name}/``.

    *session_name* defaults to the result of ``_resolve_session_name``
    when not supplied.  The Database Handler resolves it once at end
    of session so DH and archival agree on the folder name.

    *was_saved* tells the function whether the user clicked "Save"
    or "No save" at End Session.  Local archival to
    ``previous_sessions/`` runs regardless; the R2 mirror at the
    bottom is gated on ``was_saved=True OR
    workflow_settings.SAVE_LOGS_FOR_UNSAVED_SESSIONS`` (see the
    "Session saving" section of settings.py, formerly block #23).
    Default ``False`` means: a caller that does not
    know save state is treated as "not saved", and the R2 upload
    only happens when the setting allows it.

    Anything the user dropped at ``inputs/`` root (images, notes,
    user_query.txt, extracted_inputs.txt, …) is archived as one
    bundle.  Previously only ``user_query.txt`` and
    ``extracted_inputs.txt`` were moved by name — orphan images or
    notes the user placed at ``inputs/`` root instead of inside
    ``inputs/input_images/`` were left behind across sessions.

    The empty ``logs/agent_histories/`` directory left after the
    history files are moved out is also removed (it gets recreated by
    ``_dump_agent_histories`` at the next session's end), so ``logs/``
    isn't cluttered with a stale empty folder between sessions.
    """
    log_files = list(LOGS_DIR.glob("*.log")) if LOGS_DIR.exists() else []
    trace_files = (
        list(LOGS_DIR.glob("agent_flow_*.txt")) if LOGS_DIR.exists() else []
    )
    # The DH writes its own flow-trace under a different prefix
    # (``dh_flow_<ts>.txt``) so it is visually grouped with the DH
    # log instead of with the main session trace.  Its dedicated
    # ``database_handler_<ts>.log`` is already picked up by the
    # ``*.log`` glob above.
    dh_trace_files = (
        list(LOGS_DIR.glob("dh_flow_*.txt")) if LOGS_DIR.exists() else []
    )
    histories_dir = LOGS_DIR / "agent_histories"
    attempts_dir = ATTEMPTS_DIR
    input_images_dir = INPUT_IMAGES_DIR
    current_plan = LOGS_DIR / "current_plan.txt"

    # Collect every FILE sitting at inputs/ root (the input_images/
    # subfolder is handled separately below).  Materialising the list
    # before any renames matters: iterating ``iterdir()`` while
    # mutating the directory has platform-dependent behaviour.
    inputs_root_files: list[Path] = []
    if USER_INPUTS_DIR.exists():
        for f in USER_INPUTS_DIR.iterdir():
            if f.is_file():
                inputs_root_files.append(f)

    has_content = bool(
        log_files
        or trace_files
        or dh_trace_files
        or (histories_dir.exists() and any(histories_dir.iterdir()))
        or (attempts_dir.exists() and any(attempts_dir.iterdir()))
        or (input_images_dir.exists() and any(input_images_dir.iterdir()))
        or inputs_root_files
        or current_plan.exists()
    )
    if not has_content:
        return

    if session_name is None:
        # Phase 3E: ``_next_session_id`` was removed (W31).  Use the
        # same ``_resolve_session_name()`` the DH save uses so the
        # discard path produces a name in the same shape as a saved
        # session.  This fix closes the regression where End Session
        # → No raised NameError inside this function, caught silently
        # by ``_end_session``'s try/except, leaving inputs/ +
        # input_images/ + attempts/ NOT archived — so the next session
        # inherited the previous user's leftovers.
        session_name = _resolve_session_name()
    dest = PREVIOUS_SESSIONS_DIR / session_name
    dest.mkdir(parents=True, exist_ok=True)

    # shutil.move instead of Path.rename: on Railway, PREVIOUS_SESSIONS_DIR
    # is a mounted volume on a separate filesystem from logs/attempts/inputs,
    # and os.rename across filesystems fails with EXDEV.  shutil.move
    # falls back to copy+delete in that case.
    for f in log_files:
        shutil.move(f, dest / f.name)
    for f in trace_files:
        shutil.move(f, dest / f.name)
    for f in dh_trace_files:
        shutil.move(f, dest / f.name)

    if histories_dir.exists() and any(histories_dir.iterdir()):
        dest_hist = dest / "agent_histories"
        dest_hist.mkdir(exist_ok=True)
        for f in list(histories_dir.iterdir()):
            shutil.move(f, dest_hist / f.name)
        # Remove the now-empty source dir so logs/ doesn't carry a
        # stale empty folder between sessions.  ``_dump_agent_histories``
        # re-creates it at the next session's end.
        try:
            histories_dir.rmdir()
        except OSError:
            # Non-empty (something snuck in) or locked — leave it.
            pass

    # The retrieval cache is DELETED, not archived: every file in it is a
    # copy of an artefact already stored in R2 under its own session, so
    # archiving it would duplicate the archive against itself.  Removing it
    # here is also what clears it between sessions.
    for _root in (attempts_dir, USER_INPUTS_DIR):
        _cache = _root / "_retrieved"
        if _cache.is_dir():
            shutil.rmtree(_cache, ignore_errors=True)

    if attempts_dir.exists() and any(attempts_dir.iterdir()):
        dest_attempts = dest / "attempts"
        dest_attempts.mkdir(exist_ok=True)
        for f in list(attempts_dir.iterdir()):
            shutil.move(f, dest_attempts / f.name)

    if input_images_dir.exists() and any(input_images_dir.iterdir()):
        dest_images = dest / input_images_dir.name
        dest_images.mkdir(exist_ok=True)
        for f in list(input_images_dir.iterdir()):
            shutil.move(f, dest_images / f.name)

    # Archive every file at inputs/ root in one sweep.  This covers
    # user_query.txt, extracted_inputs.txt, current_plan.txt-style
    # entries, AND any orphan images / notes the user placed at
    # inputs/ root instead of inside inputs/input_images/.
    for f in inputs_root_files:
        shutil.move(f, dest / f.name)

    if current_plan.exists():
        shutil.move(current_plan, dest / current_plan.name)

    # ------------------------------------------------------------------
    # R2 mirror — Path 3 (session-generic logs + traces + histories).
    # ------------------------------------------------------------------
    # Path 1 (upload_attempt_artefacts) covers per-attempt artefacts
    # under ``<sid>/attempts/<NNN>/...``; Path 2 (upload_directory in
    # the DH's populate_database) covers the DH's per-agent .txt tree
    # under ``<sid>/<agent>/...`` and the user inputs under
    # ``<sid>/user_inputs/...``.  This is the third disjoint path
    # (see W19 in extra_utilities/warnings_developer.md): it walks the
    # local logs / traces / agent_histories the move loops above just
    # archived under ``dest/`` and pushes them to R2 under
    # ``<sid>/logs/...``.  ``<sid>/logs/`` is disjoint from both
    # other paths' namespaces, so no key collision is possible.
    #
    # Gated by SAVE_LOGS_FOR_UNSAVED_SESSIONS (settings.py, the
    # "Session saving" section — formerly block #23)
    # for the not-saved path: when the user clicked "No save" AND
    # the setting is False, this block is skipped entirely and the
    # session lives only in ``previous_sessions/<sid>/`` locally.
    # Saved sessions (was_saved=True) always upload regardless of
    # the setting.
    #
    # Wrapped in try/except so a transient R2 failure cannot break
    # the archive sweep — same best-effort stance as the DH save's
    # ``upload_directory`` call.  Logging via ``propeller_agent`` so
    # the operator sees what landed in R2.
    if not was_saved:
        try:
            from workflow_settings import settings as _ws
        except Exception:
            _ws = None
        _allow = bool(
            _ws is not None
            and getattr(_ws, "SAVE_LOGS_FOR_UNSAVED_SESSIONS", False)
        )
        if not _allow:
            try:
                logging.getLogger("propeller_agent").info(
                    f"[R2]  skipped session-log mirror for "
                    f"{session_name} (was_saved=False AND "
                    f"SAVE_LOGS_FOR_UNSAVED_SESSIONS=False)"
                )
            except Exception:
                pass
            return
    try:
        from agents.shared import r2_uploader as _r2
        if _r2.is_enabled():
            _r2_log = logging.getLogger("propeller_agent")
            _uploaded = 0
            _skipped  = 0
            # The three flat-at-root families: log_files (which
            # already includes database_handler_*.log via the *.log
            # glob), trace_files (agent_flow_*.txt), dh_trace_files
            # (dh_flow_*.txt).  ``current_plan.txt`` is intentionally
            # NOT uploaded here — it is the Planner's working scratch,
            # not a log artefact.
            _flat: list[Path] = []
            _flat.extend(dest / f.name for f in log_files)
            _flat.extend(dest / f.name for f in trace_files)
            _flat.extend(dest / f.name for f in dh_trace_files)
            for p in _flat:
                if not p.is_file():
                    _skipped += 1
                    continue
                # Phase 5A: rename the main session log on upload only
                # to drop the session_id duplication.  Local filename
                # stays ``<session_name>.log`` (many parts of the system
                # know that name); the R2 key becomes
                # ``<session_name>/logs/session.log``.  The three other
                # log/trace files use timestamp-based filenames so they
                # pass through unchanged.
                if p.stem == session_name and p.suffix == ".log":
                    key_filename = "session.log"
                else:
                    key_filename = p.name
                key = f"{session_name}/logs/{key_filename}"
                if _r2.upload_file(p, key):
                    _uploaded += 1
                else:
                    _skipped += 1
            # agent_histories/*.json — nested one folder deeper to
            # mirror the local layout (matches what the move loop
            # above produced under ``dest / "agent_histories"``).
            dest_hist = dest / "agent_histories"
            if dest_hist.is_dir():
                for p in sorted(dest_hist.iterdir()):
                    if not p.is_file():
                        continue
                    key = f"{session_name}/logs/agent_histories/{p.name}"
                    if _r2.upload_file(p, key):
                        _uploaded += 1
                    else:
                        _skipped += 1
            _r2_log.info(
                f"[R2]  session-log mirror: {_uploaded} uploaded, "
                f"{_skipped} skipped → "
                f"<prefix>/{session_name}/logs/"
            )
    except Exception as _exc:
        # Best-effort: never let an R2 problem fail the archive sweep.
        try:
            logging.getLogger("propeller_agent").warning(
                f"[R2]  session-log mirror failed: "
                f"{type(_exc).__name__}: {_exc}"
            )
        except Exception:
            pass


def _setup_logger() -> logging.Logger:
    """Create a logger that writes to a timestamped log file.

    Archival of the previous session's artifacts happens at session END
    (in ``run``'s ``finally``), NOT here.  Doing it on session start
    would clobber any input images / notes the user uploaded into
    ``inputs/input_images/`` BEFORE launching the session.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"session_{timestamp}.log"

    logger = logging.getLogger("propeller_agent")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
    logger.addHandler(fh)

    # Emit the session-config banner FIRST so every saved log starts
    # with the full settings + LLM routing + DBa snapshot (REPL path —
    # matches the web entry point's behaviour).
    from workflow_settings.session_banner import write_to_logger as _write_banner
    _write_banner(logger)

    print(f"Log file: {log_path.resolve()}")
    return logger


def _close_logger(logger: logging.Logger) -> None:
    """Flush and close every handler on *logger*, then detach them.

    Required on Windows so the freshly-written ``session_*.log`` can
    be moved by ``_archive_previous_session`` (Windows holds open
    files exclusively).
    """
    for h in list(logger.handlers):
        try:
            h.flush()
            h.close()
        except Exception:
            pass
        logger.removeHandler(h)


def _end_session(
    logger: logging.Logger,
    hub,
    save_database: bool = False,
) -> None:
    """End-of-session shutdown: optionally populate the database via
    the Database Handler, dump histories, close trace + log, then
    archive everything session-specific into
    ``previous_sessions/ID{N:03d}_{date_time}/``.

    *save_database* is set to True only when the user explicitly
    confirmed at the end-of-session prompt; the KeyboardInterrupt
    and unhandled-exception paths leave it False (the user is no
    longer at the keyboard).

    Idempotent and exception-safe — designed to run in a ``finally``
    so it fires regardless of whether the session ended normally
    (user typed ``quit``), via Ctrl-C, or via an unhandled exception.
    """
    # Resolve the session folder name ONCE up-front so the DH and
    # the archive logic agree on the name.  The DH writes under
    # ``database/<name>/`` and the archive writes under
    # ``previous_sessions/<name>/``.
    try:
        session_name = _resolve_session_name()
    except Exception as exc:
        try:
            logger.warning(
                f"[SESSION END]  resolving session name failed: {exc}"
            )
        except Exception:
            pass
        session_name = None

    # IMPORTANT (see extra_utilities/warnings_developer.md, W1):
    # dump agent histories BEFORE any post-session task runs (the
    # Database Handler in particular).  The DH's interview phase
    # mutates each agent's live ``self.messages`` (it restores from
    # snapshot, then appends the question + answer) so by the time
    # the DH returns, ``agent.messages`` no longer represents the
    # session-time history.  Dumping first guarantees the per-agent
    # history files in ``logs/agent_histories/`` reflect the actual
    # session.
    try:
        if hub is not None:
            _dump_agent_histories(hub, logger)
    except Exception as exc:
        try:
            logger.warning(f"[SESSION END]  history dump failed: {exc}")
        except Exception:
            pass

    if save_database and hub is not None and session_name is not None:
        try:
            dh = getattr(hub, "database_handler", None)
            if dh is None:
                logger.warning(
                    "[SESSION END]  Database Handler not available; "
                    "save was requested but skipped."
                )
            else:
                session_db_dir = DATABASE_DIR / session_name
                logger.info(
                    f"[DH]  populating database under {session_db_dir.resolve()}"
                )
                written = dh.populate_database(
                    session_db_dir,
                    session_timestamp=_resolve_session_timestamp(),
                    orchestrator=hub,
                )
                logger.info(f"[DH]  wrote {written} entries")
                print(f"Database entries written: {written} -> {session_db_dir.resolve()}")
        except Exception as exc:
            try:
                logger.exception(
                    f"[SESSION END]  database population failed: {exc}"
                )
            except Exception:
                pass
    try:
        close_trace()
    except Exception:
        pass
    # Logger handlers must be closed BEFORE archive, otherwise the
    # session_*.log file is held open and Windows refuses the move.
    _close_logger(logger)
    try:
        _archive_previous_session(
            session_name=session_name, was_saved=save_database,
        )
    except Exception:
        # Logger is already closed — nothing left to record this on.
        pass


# ---------------------------------------------------------------------------
# Agent history dump
# ---------------------------------------------------------------------------


def _dump_agent_histories(hub, logger) -> None:
    """Write per-agent message histories to logs/agent_histories/."""
    try:
        dest = LOGS_DIR / "agent_histories"
        paths = hub.dump_histories(dest)
        if paths:
            logger.info(
                f"[AGENT HISTORIES]  wrote {len(paths)} files to "
                f"{dest.resolve()}"
            )
            print(f"Agent histories: {dest.resolve()}")
    except Exception as exc:  # pragma: no cover
        logger.warning(f"[AGENT HISTORIES]  dump failed: {exc}")


# ---------------------------------------------------------------------------
# Startup prompts
# ---------------------------------------------------------------------------


def _ask_yes_no(prompt: str, default_yes: bool = True) -> bool:
    hint = "[Y/n]" if default_yes else "[y/N]"
    while True:
        answer = input(f"{prompt} {hint}: ").strip().lower()
        if answer in {"", "y", "yes"}:
            return True if default_yes else (answer in {"y", "yes"})
        if answer in {"n", "no"}:
            return False
        print("  Please enter Y or N.")


def _ask_choice(prompt: str, options: list[str], default: int = 1) -> int:
    """Ask the user to pick one of *options* by 1-based index.

    Prints the prompt followed by each option on its own indented line
    (numbered).  Returns the 1-based index of the chosen option.  Empty
    input picks *default*.
    """
    print(prompt)
    for i, opt in enumerate(options, start=1):
        marker = " (default)" if i == default else ""
        print(f"  {i}. {opt}{marker}")
    valid = {str(i) for i in range(1, len(options) + 1)}
    while True:
        answer = input(f"Choose 1-{len(options)} [default {default}]: ").strip()
        if answer == "":
            return default
        if answer in valid:
            return int(answer)
        print(f"  Please enter a number between 1 and {len(options)}.")


def _print_agent_llm_summary(logger: logging.Logger) -> None:
    """Resolve and print the per-agent LLM config (provider + model + source).

    Calling ``list_agent_configs`` does NOT construct any LLMs — it
    only reads the ``.env`` files.  The actual LLM build happens
    inside each agent's ``__init__``.
    """
    agent_keys = list(AGENT_DISPLAY.keys())
    configs = list_agent_configs(agent_keys)

    # Detect the common case where every agent ends up using the same
    # shared default — collapse into one summary line.  Otherwise list
    # per-agent overrides.
    distinct = {(c["provider"], c["model"]) for c in configs}
    if len(distinct) == 1 and all(c["source"] == "shared" for c in configs):
        provider, model = next(iter(distinct))
        line = (
            f"  LLMs: shared default ({provider.upper()} / {model}) "
            f"used by all {len(configs)} agents."
        )
        print(line)
        logger.info(f"[CONFIG] {line.strip()}")
        return

    print("  Per-agent LLM configuration:")
    logger.info("[CONFIG] Per-agent LLM configuration:")
    for c in configs:
        display = AGENT_DISPLAY.get(c["agent"], c["agent"])
        marker = "[per-agent]" if c["source"] == "per-agent" else "[shared]"
        line = (
            f"    {display:<22} {c['provider'].upper():<10} {c['model']:<20}"
            f" {marker}"
        )
        print(line)
        logger.info(f"[CONFIG] {line.strip()}")


# ---------------------------------------------------------------------------
# Interactive loop
# ---------------------------------------------------------------------------


def run() -> None:
    """Main entry point for the multi-agent workflow.

    Archival of every session-specific artifact happens in the
    ``finally`` block at the bottom, so it fires no matter how the
    session ends — normal ``quit``, Ctrl-C / KeyboardInterrupt, or
    any unhandled exception bubbling out of the dispatcher.  This is
    why the user can drop images into ``inputs/input_images/`` BEFORE
    launching: nothing gets archived until shutdown.
    """
    logger = _setup_logger()
    hub = None
    save_database = False
    try:
        print("=== Multi-Agent Design Configurator ===\n")

        # Settings come from workflow_settings/settings.py — edit that
        # file to change the system's startup behaviour without
        # re-typing the same answers every session.
        mesh_checks = workflow_settings.MESH_CHECKS
        render_library = workflow_settings.RENDER_LIBRARY
        geometry_backend = workflow_settings.GEOMETRY_BACKEND
        rag_enabled = workflow_settings.RAG_ENABLED
        dc_inspector_enabled = workflow_settings.DC_INSPECTOR_ENABLED
        chain_access = workflow_settings.CHAIN_ACCESS
        keep_images_in_context = workflow_settings.KEEP_IMAGES_IN_CONTEXT
        dcoi_comparison_mode = workflow_settings.DCOI_COMPARISON_MODE
        rate_limit_enabled = workflow_settings.RATE_LIMIT_ENABLED
        rate_limit_rps = workflow_settings.RATE_LIMIT_REQUESTS_PER_SECOND

        # Validate the two non-boolean settings up front; a typo here
        # should fail loudly before agents are built rather than
        # silently keeping a default.
        if render_library not in ("trimesh", "pyvista"):
            raise ValueError(
                f"workflow_settings.RENDER_LIBRARY must be 'trimesh' or "
                f"'pyvista', got {render_library!r}.  Edit "
                f"workflow_settings/settings.py."
            )
        if geometry_backend not in ("feg", "rhino"):
            raise ValueError(
                f"workflow_settings.GEOMETRY_BACKEND must be 'feg' or "
                f"'rhino', got {geometry_backend!r}.  Edit "
                f"workflow_settings/settings.py."
            )
        if dcoi_comparison_mode not in (1, 2, 3):
            raise ValueError(
                f"workflow_settings.DCOI_COMPARISON_MODE must be 1, 2, "
                f"or 3, got {dcoi_comparison_mode!r}.  Edit "
                f"workflow_settings/settings.py."
            )
        if rate_limit_enabled and rate_limit_rps <= 0:
            raise ValueError(
                f"workflow_settings.RATE_LIMIT_REQUESTS_PER_SECOND must be "
                f"> 0 when RATE_LIMIT_ENABLED is True, got "
                f"{rate_limit_rps!r}.  Edit workflow_settings/settings.py."
            )

        set_mesh_checks(mesh_checks)
        set_render_library(render_library)
        set_geometry_backend(geometry_backend)

        settings_path = (
            Path(workflow_settings.__file__).resolve()
        )
        print()
        print(f"Settings loaded from: {settings_path}")
        print("(edit that file to change any of the values below)")
        print()
        _print_agent_llm_summary(logger)
        print(f"  Mesh quality checks: {'ON' if mesh_checks else 'OFF'}")
        print(f"  Render/check library: {render_library}")
        print(f"  RAG retrieval:       {'ON (not yet implemented)' if rag_enabled else 'OFF'}")
        print(f"  DC Input Inspector:  {'ON' if dc_inspector_enabled else 'OFF (skipped)'}")
        print(f"  Orchestrator chain access: {'ON' if chain_access else 'OFF'}")
        print(f"  Keep images in agent context: {'ON' if keep_images_in_context else 'OFF (stripped at every operation end)'}")
        if rate_limit_enabled:
            print(
                f"  Rate limiter:        ON ({rate_limit_rps} req/s shared "
                f"across all 8 agents)"
            )
        else:
            print("  Rate limiter:        OFF")
        print(f"  DCOI comparison mode: {dcoi_comparison_mode}")
        print()

        logger.info("=== Multi-Agent Design Configurator ===")
        logger.info(
            f"[CONFIG]  mesh_checks={mesh_checks}  "
            f"render_library={render_library}  rag={rag_enabled}  "
            f"dc_inspector={dc_inspector_enabled}  chain_access={chain_access}  "
            f"keep_images_in_context={keep_images_in_context}  "
            f"rate_limit={'on@' + str(rate_limit_rps) + 'rps' if rate_limit_enabled else 'off'}  "
            f"dcoi_comparison_mode={dcoi_comparison_mode}"
        )

        # Initialise the lightweight flow-trace log
        trace_path = init_trace(LOGS_DIR)
        print(f"Trace file: {trace_path.resolve()}")

        # Build the per-conversation Session (v3 Phase 1 commit 3).
        # In v4-REPL mode the session_id is the same one
        # ``_resolve_session_name`` will use at archive time, so logs,
        # archive, and (later) DH save all agree on the identifier.
        # Path fields stay None — v4 keeps using the global config.*
        # paths, no Streamlit-style namespacing.
        session = Session(
            session_id=_resolve_session_name(),
            session_ts=datetime.now(timezone.utc),
            mesh_checks=mesh_checks,
            rag_enabled=rag_enabled,
            dc_inspector_enabled=dc_inspector_enabled,
            chain_access=chain_access,
            keep_images_in_context=keep_images_in_context,
            dcoi_comparison_mode=dcoi_comparison_mode,
        )

        # Build the topology's hub (which constructs every sub-agent,
        # each of which builds its own LLM via build_llm(<key>))
        print("Initialising agents...")
        hub = build_hub(session)
        print("Agents ready.\n")

        logger.info("[AGENTS]  hub and all sub-agents initialised")
        logger.info(
            "[AGENTS]  Receptionist, Planner, User Input Inspector, "
            "DC Input Creator, DC Input Inspector, DC Output Inspector, "
            "Tool Caller"
        )

        print("Describe the propeller you want to design.  Type 'quit' to exit.\n")

        while True:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in {"quit", "exit", "q"}:
                logger.info("[SESSION END]  user quit")
                # Ask the user whether to save this session into the
                # database (used for RAG by future sessions).  Default
                # is "no" — saving runs the Database Handler and
                # incurs LLM calls.  TODO (refinement): this is a
                # minimal v1 prompt; the wording, default, and
                # branching may need polish (e.g. show what will be
                # saved, allow per-agent skip, etc.).
                save_database = _ask_yes_no(
                    "Save this session to the database (for later RAG)?",
                    default_yes=False,
                )
                if save_database:
                    print(
                        "Saving — Database Handler will interview each "
                        "agent before shutdown."
                    )
                # ``Goodbye!`` is printed AFTER ``_end_session``
                # finishes so the user does not see DH log paths /
                # progress prints AFTER the program has visibly bid
                # them farewell.  See warnings_developer.md (W10).
                break

            logger.info(f"[USER]  {user_input}")

            # The per-turn body lives in agents/dispatch.py so the v3
            # Streamlit handler can reuse it (Phase 3).  Loader's role
            # here is the I/O surface: read user input, print the
            # reply.  All agent orchestration is inside dispatch_turn.
            result = dispatch_turn(
                session=session,
                user_input=user_input,
                inputs_dir=USER_INPUTS_DIR,
                hub=hub,
            )
            print(f"\nAssistant: {result.reply_text}\n")
    except KeyboardInterrupt:
        try:
            logger.info("[SESSION END]  KeyboardInterrupt")
        except Exception:
            pass
        print("\nInterrupted.")
    except Exception as exc:
        try:
            logger.exception(f"[SESSION END]  unhandled exception: {exc}")
        except Exception:
            pass
        # Re-raise after the finally archives so main.py / the user
        # still see the traceback.
        raise
    finally:
        _end_session(logger, hub, save_database=save_database)
        # Printed AFTER all post-session work is complete so it is
        # the last thing the user sees on stdout.  See
        # warnings_developer.md (W10).
        print("Goodbye!")
