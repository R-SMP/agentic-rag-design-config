"""Dedicated log + flow-trace for the Database Handler phase.

Two files are produced under ``logs/`` whenever the DH actually
runs (i.e. when the user accepted ``Save this session to the
database?`` at the end of the session):

  ``logs/database_handler_<TS>.log``
      Detailed per-line log of the DH's internal events: which
      agent it interviewed, which field it filled, when each
      conversation started / finished, file write paths, and any
      warnings or errors.  Written via the ``database_handler``
      logger; does NOT propagate to the main ``propeller_agent``
      session logger, so the main session log stays focused on the
      session itself.

  ``logs/dh_flow_<TS>.txt``
      Lightweight flow trace, one line per inter-agent message
      during the DH phase.  Same shape as the regular session
      ``agent_flow_*.txt`` file.

Both files share the same timestamp so they pair up at archive
time.  ``_archive_previous_session`` in ``agents/loader.py``
sweeps both ``*.log`` and ``dh_flow_*.txt`` from ``logs/``, so
they end up in the corresponding ``previous_sessions/<ID>/``
folder alongside the rest.
"""

import logging
from datetime import datetime
from pathlib import Path

_DH_LOGGER_NAME = "database_handler"

# Module-level state — only one DH phase runs per session, so a
# single global pair of file handles is fine.
_dh_file_handler: logging.FileHandler | None = None
_dh_trace_file = None


def init_dh_logging(
    log_dir: Path,
    session_timestamp: str | None = None,
) -> tuple[Path, Path]:
    """Open the DH log and DH flow-trace files; return their paths.

    Idempotent: calling this twice in the same process tears down
    any previously-open handles, AND scrubs every ``FileHandler``
    still attached to the ``database_handler`` logger before adding
    a new one.  This catches the edge case where a previous run
    crashed before ``close_dh_logging`` could fire and left the
    logger holding an orphan handler the module never tracked.

    *session_timestamp* is the ``YYYYMMDD_HHMMSS`` slug from the
    main session log filename.  When supplied, the DH files share
    that exact timestamp so they sort with the rest of the session
    artefacts.  When ``None``, the DH falls back to the current
    time at DH start (older behaviour).
    """
    global _dh_file_handler, _dh_trace_file

    # Defensive: tear down any handles WE remember to track first.
    close_dh_logging()

    # Stronger safety net: even if a previous DH run crashed before
    # ``close_dh_logging`` could record its handler, the
    # ``database_handler`` logger object is a process-wide singleton
    # and may still hold orphan ``FileHandler``s that would cause
    # duplicate log lines.  Sweep them all out before installing
    # the new one.
    dh_logger = logging.getLogger(_DH_LOGGER_NAME)
    for orphan in list(dh_logger.handlers):
        if isinstance(orphan, logging.FileHandler):
            try:
                orphan.flush()
                orphan.close()
            except Exception:
                pass
            try:
                dh_logger.removeHandler(orphan)
            except Exception:
                pass

    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (
        session_timestamp
        if session_timestamp
        else datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    log_path = log_dir / f"database_handler_{timestamp}.log"
    trace_path = log_dir / f"dh_flow_{timestamp}.txt"

    # ---- DH-dedicated logger -----------------------------------
    dh_logger.setLevel(logging.DEBUG)
    # The DH log is a SEPARATE concern from the main session log;
    # turn off propagation so DH events do not also appear in
    # ``session_<ts>.log``.
    dh_logger.propagate = False

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
    dh_logger.addHandler(fh)
    _dh_file_handler = fh

    # ---- DH flow trace -----------------------------------------
    _dh_trace_file = open(trace_path, "w", encoding="utf-8")
    start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _dh_trace_file.write("=== Database Handler Flow Trace ===\n")
    _dh_trace_file.write(f"Started: {start}\n\n")
    _dh_trace_file.flush()

    return log_path, trace_path


def dh_trace(from_agent: str, to_agent: str, note: str = "") -> None:
    """Append one line to the DH flow trace.  No-op if not initialised."""
    if _dh_trace_file is None:
        return
    now = datetime.now().strftime("%H:%M:%S")
    line = f"{now}  {from_agent} --> {to_agent}"
    if note:
        line += f"  ({note})"
    _dh_trace_file.write(line + "\n")
    _dh_trace_file.flush()


def close_dh_logging() -> None:
    """Flush + close the DH log handler and trace file.

    Required on Windows so the freshly-written files can be moved
    by ``_archive_previous_session`` (Windows holds open files
    exclusively).
    """
    global _dh_file_handler, _dh_trace_file

    if _dh_trace_file is not None:
        try:
            end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _dh_trace_file.write(f"\n=== DH Trace ended: {end} ===\n")
            _dh_trace_file.close()
        except Exception:
            pass
        _dh_trace_file = None

    if _dh_file_handler is not None:
        dh_logger = logging.getLogger(_DH_LOGGER_NAME)
        try:
            _dh_file_handler.flush()
            _dh_file_handler.close()
        except Exception:
            pass
        try:
            dh_logger.removeHandler(_dh_file_handler)
        except Exception:
            pass
        _dh_file_handler = None
