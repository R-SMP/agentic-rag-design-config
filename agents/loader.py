"""Entry point for the multi-agent design configurator system.

Sets up logging, prompts the user for configuration (mesh checks, RAG,
optional DC Input Inspector, chain-access toggle), builds the
Orchestrator (which builds every sub-agent and resolves each
agent's LLM via ``agents/<name>/.env`` → ``agents/.env``), and runs
the interactive REPL.
"""

import logging
import re
from datetime import datetime
from pathlib import Path

from agents.orchestrator import Orchestrator
from agents.shared.llm_provider import list_agent_configs
from agents.shared.routing_tools import AGENT_DISPLAY
from agents.shared.trace import close_trace, init_trace, trace as _trace
from config import (
    ATTEMPTS_DIR,
    DATABASE_DIR,
    INPUT_IMAGES_DIR,
    LOGS_DIR,
    PREVIOUS_SESSIONS_DIR,
    USER_INPUTS_DIR,
)
from tools import set_mesh_checks, set_render_library
from workflow_settings import settings as workflow_settings


# ---------------------------------------------------------------------------
# Session archival
# ---------------------------------------------------------------------------


_ID_RE = re.compile(r"^ID(\d+)_")
_LOG_TS_RE = re.compile(r"session_(\d{8}_\d{6})\.log$")
_RECEPTIONIST_LABEL = "[Incoming from: Receptionist]"


def _next_session_id() -> int:
    """Return the next session ID by scanning existing previous_sessions/."""
    if not PREVIOUS_SESSIONS_DIR.exists():
        return 1
    highest = 0
    for child in PREVIOUS_SESSIONS_DIR.iterdir():
        if not child.is_dir():
            continue
        m = _ID_RE.match(child.name)
        if m:
            highest = max(highest, int(m.group(1)))
    return highest + 1


def _session_datetime_slug(log_files: list[Path]) -> str:
    """Prefer the timestamp embedded in an existing session_*.log filename;
    fall back to the current time."""
    for f in log_files:
        m = _LOG_TS_RE.search(f.name)
        if m:
            return m.group(1)
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _resolve_session_name() -> str:
    """Return the session folder name (``ID{N:03d}_{date_time}``).

    Same naming convention used by ``_archive_previous_session`` for
    its destination folder under ``previous_sessions/``.  Factored out
    so the Database Handler can save under the IDENTICAL name in
    ``database/`` before archival runs.
    """
    log_files = list(LOGS_DIR.glob("*.log")) if LOGS_DIR.exists() else []
    session_id = _next_session_id()
    slug = _session_datetime_slug(log_files)
    return f"ID{session_id:03d}_{slug}"


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


def _archive_previous_session(session_name: str | None = None) -> None:
    """Move the previous session's artefacts into
    ``previous_sessions/{session_name}/``.

    *session_name* defaults to the result of ``_resolve_session_name``
    when not supplied.  The Database Handler resolves it once at end
    of session so DH and archival agree on the folder name.

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
        session_id = _next_session_id()
        slug = _session_datetime_slug(log_files)
        session_name = f"ID{session_id:03d}_{slug}"
    dest = PREVIOUS_SESSIONS_DIR / session_name
    dest.mkdir(parents=True, exist_ok=True)

    for f in log_files:
        f.rename(dest / f.name)
    for f in trace_files:
        f.rename(dest / f.name)
    for f in dh_trace_files:
        f.rename(dest / f.name)

    if histories_dir.exists() and any(histories_dir.iterdir()):
        dest_hist = dest / "agent_histories"
        dest_hist.mkdir(exist_ok=True)
        for f in list(histories_dir.iterdir()):
            f.rename(dest_hist / f.name)
        # Remove the now-empty source dir so logs/ doesn't carry a
        # stale empty folder between sessions.  ``_dump_agent_histories``
        # re-creates it at the next session's end.
        try:
            histories_dir.rmdir()
        except OSError:
            # Non-empty (something snuck in) or locked — leave it.
            pass

    if attempts_dir.exists() and any(attempts_dir.iterdir()):
        dest_attempts = dest / "attempts"
        dest_attempts.mkdir(exist_ok=True)
        for f in list(attempts_dir.iterdir()):
            f.rename(dest_attempts / f.name)

    if input_images_dir.exists() and any(input_images_dir.iterdir()):
        dest_images = dest / input_images_dir.name
        dest_images.mkdir(exist_ok=True)
        for f in list(input_images_dir.iterdir()):
            f.rename(dest_images / f.name)

    # Archive every file at inputs/ root in one sweep.  This covers
    # user_query.txt, extracted_inputs.txt, current_plan.txt-style
    # entries, AND any orphan images / notes the user placed at
    # inputs/ root instead of inside inputs/input_images/.
    for f in inputs_root_files:
        f.rename(dest / f.name)

    if current_plan.exists():
        current_plan.rename(dest / current_plan.name)


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
    orchestrator,
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
        if orchestrator is not None:
            _dump_agent_histories(orchestrator, logger)
    except Exception as exc:
        try:
            logger.warning(f"[SESSION END]  history dump failed: {exc}")
        except Exception:
            pass

    if save_database and orchestrator is not None and session_name is not None:
        try:
            dh = getattr(orchestrator, "database_handler", None)
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
                    orchestrator,
                    session_db_dir,
                    dc_inspector_enabled=getattr(
                        orchestrator, "dc_inspector_enabled", False,
                    ),
                    session_timestamp=_resolve_session_timestamp(),
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
        _archive_previous_session(session_name=session_name)
    except Exception:
        # Logger is already closed — nothing left to record this on.
        pass


# ---------------------------------------------------------------------------
# Agent history dump
# ---------------------------------------------------------------------------


def _dump_agent_histories(orchestrator, logger) -> None:
    """Write per-agent message histories to logs/agent_histories/."""
    try:
        dest = LOGS_DIR / "agent_histories"
        paths = orchestrator.dump_histories(dest)
        if paths:
            logger.info(
                f"[AGENT HISTORIES]  wrote {len(paths)} files to "
                f"{dest.resolve()}"
            )
            print(f"Agent histories: {dest.resolve()}")
    except Exception as exc:  # pragma: no cover
        logger.warning(f"[AGENT HISTORIES]  dump failed: {exc}")


# ---------------------------------------------------------------------------
# Input-file helpers
# ---------------------------------------------------------------------------


def _save_user_input(text: str) -> Path:
    """Append the user's text input to inputs/user_query.txt with a
    timestamp.  Returns the inputs directory path."""
    USER_INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    query_path = USER_INPUTS_DIR / "user_query.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(query_path, "a", encoding="utf-8") as f:
        f.write(f"\n--- [{timestamp}] ---\n{text}\n")
    return USER_INPUTS_DIR


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
    orchestrator = None
    save_database = False
    try:
        print("=== Multi-Agent Design Configurator ===\n")

        # Settings come from workflow_settings/settings.py — edit that
        # file to change the system's startup behaviour without
        # re-typing the same answers every session.
        mesh_checks = workflow_settings.MESH_CHECKS
        render_library = workflow_settings.RENDER_LIBRARY
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

        # Build the Orchestrator (which constructs every sub-agent, each
        # of which builds its own LLM via build_llm(<key>))
        print("Initialising agents...")
        orchestrator = Orchestrator(
            mesh_checks, rag_enabled,
            dc_inspector_enabled=dc_inspector_enabled,
            chain_access=chain_access,
            keep_images_in_context=keep_images_in_context,
            dcoi_comparison_mode=dcoi_comparison_mode,
        )
        print("Agents ready.\n")

        logger.info("[AGENTS]  Orchestrator and all sub-agents initialised")
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

            # Step 1: Save user input to files
            input_dir = _save_user_input(user_input)
            logger.info(f"[INPUT FILES]  saved to {input_dir.resolve()}")

            # Step 2: Receptionist reads the input files and decides, via
            # its own reasoning, whether to forward into the pipeline
            # (``forward == True``) or to reply to the user directly.  The
            # decision is recorded purely by the tool the LLM chose to
            # invoke — no status codes, no code-words.
            _trace("User", "Receptionist")
            validation = orchestrator.receptionist.validate_input(input_dir)
            logger.info(
                f"[RECEPTIONIST]  forward={validation['forward']}  "
                f"message={validation['message']}"
            )

            if not validation["forward"]:
                _trace("Receptionist", "User", "direct")
                print(f"\nAssistant: {validation['message']}\n")
                logger.info(f"[RECEPTIONIST -> USER]  {validation['message']}")
                continue

            # Step 3: Orchestrator drives the horizontal dispatch loop.
            _trace("Receptionist", "Orchestrator", "forwarded")
            orchestrator.reset_turn()
            ft_str = ", ".join(validation["file_types"]) if validation["file_types"] else "text"
            receptionist_summary = (validation.get("message") or "").strip()
            # The routing tool prepends `[Incoming from: Receptionist]` to the
            # Receptionist's call_orchestrator message.  The kickoff below
            # already carries its own top-level `[Incoming from: Receptionist]`
            # label, so strip the inner duplicate before embedding the
            # summary under the "--- Receptionist's summary to you ---"
            # header.
            if receptionist_summary.startswith(_RECEPTIONIST_LABEL):
                receptionist_summary = receptionist_summary[
                    len(_RECEPTIONIST_LABEL):
                ].lstrip()
            kickoff_parts = [
                "[Incoming from: Receptionist]",
                "",
                "New user message forwarded by the Receptionist.",
                "",
                "--- Receptionist's summary to you ---",
                receptionist_summary or "(no summary supplied)",
                "",
                f"Input file directory: {validation['input_dir']}",
                f"Available file types: {ft_str}",
                "",
                "Decide freely how to proceed.  In most cases this means "
                "handing off to the Planner with whatever context from the "
                "Receptionist (goals, strategy caps, specific requirements, "
                "abstract reasoning, disambiguations) would help the Planner "
                "do its job well.  Lose no useful context.",
            ]
            kickoff = "\n".join(kickoff_parts)
            outgoing = orchestrator.dispatch(kickoff)
            if not outgoing or not outgoing.strip():
                outgoing = (
                    "(internal error — the system produced no user-facing "
                    "message; please re-send your last request)"
                )
                logger.error("[DISPATCH]  empty user-facing message; substituted fallback")
            _trace("Receptionist", "User", "delivered")
            print(f"\nAssistant: {outgoing}\n")
            logger.info(f"[RECEPTIONIST -> USER]  {outgoing}")
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
        _end_session(logger, orchestrator, save_database=save_database)
        # Printed AFTER all post-session work is complete so it is
        # the last thing the user sees on stdout.  See
        # warnings_developer.md (W10).
        print("Goodbye!")
