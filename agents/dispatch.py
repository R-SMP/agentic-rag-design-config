"""Per-turn dispatch driver — pure-function entry point shared by
both the v4 REPL loader and the v3 Streamlit handler.

``dispatch_turn(session, user_input, ...) -> TurnResult`` runs one
user turn end-to-end:

  1. Saves the user's text to ``user_query.txt`` under the supplied
     ``inputs_dir``.
  2. Constructs (or reuses) an Orchestrator from the Session.
  3. Runs ``Receptionist.validate_input`` against the inputs dir.
  4. If the Receptionist forwards into the pipeline, builds a kickoff
     message and runs ``Orchestrator.dispatch``.
  5. Returns the user-facing reply text alongside whether the pipeline
     was actually invoked.

The function does NOT print to stdout, NOT prompt the user, NOT manage
the REPL loop, and NOT run any post-session work (DH save, archival).
Callers wrap it with their own I/O surface — the v4 loader prints to
the terminal and reads ``input()``; the v3 Streamlit dispatcher feeds
chat-message bubbles in and out.

Caller responsibility
---------------------
* The caller manages the Orchestrator's lifetime.  The v4 loader holds
  one for the entire REPL session and reuses it across turns; the v3
  Streamlit dispatcher may rebuild one per turn (cheap with the LLM
  cache) — chain agents are reconstructed from session.agent_states
  in either case so behaviour is identical.
* The caller chooses ``inputs_dir``.  v4 passes the global
  ``config.USER_INPUTS_DIR``; v3 will pass the namespaced
  ``session.inputs_dir`` so concurrent users do not collide on the
  same on-disk paths.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from agents.orchestrator import Orchestrator
from agents.shared.session import Session
from agents.shared.trace import trace as _trace
from config import ATTEMPTS_DIR as _CONFIG_ATTEMPTS_DIR

logger = logging.getLogger("propeller_agent")

# The Receptionist's call_orchestrator routing tool prepends this label
# to every forward message; the kickoff already carries its own
# top-level "[Incoming from: Receptionist]" label, so the inner
# duplicate is stripped before embedding under the
# "--- Receptionist's summary to you ---" header.
_RECEPTIONIST_LABEL = "[Incoming from: Receptionist]"


@dataclass
class TurnResult:
    """The outcome of one ``dispatch_turn`` call.

    ``reply_text`` is what the caller surfaces to the user this turn.
    ``forwarded`` distinguishes a Receptionist-only direct reply
    (``False``) from a full pipeline run (``True``).
    ``new_artefacts_paths`` carries the absolute paths of any
    ``render_*.png`` files (and other ``.png`` / ``.obj`` artefacts)
    that appeared under ``attempts_dir`` between the start and end
    of this turn, sorted by mtime ascending so the order reflects
    creation order.  Empty when no new artefacts landed (Receptionist
    direct reply, or pipeline that did not call ``new_attempt``).
    The v3 Streamlit handler renders these inline as chat-bubble
    images; the v4 REPL caller is free to ignore the field (it does
    — terminal output has no concept of inline images).
    """
    reply_text: str
    forwarded: bool
    new_artefacts_paths: list[Path] = field(default_factory=list)


def save_user_input(text: str, inputs_dir: Path) -> Path:
    """Append the user's text to ``{inputs_dir}/user_query.txt``.

    Creates ``inputs_dir`` if it does not exist, prefixes the entry
    with a ``--- [YYYY-MM-DD HH:MM:SS] ---`` header, and returns the
    inputs directory unchanged so callers can chain.
    """
    inputs_dir.mkdir(parents=True, exist_ok=True)
    query_path = inputs_dir / "user_query.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(query_path, "a", encoding="utf-8") as f:
        f.write(f"\n--- [{timestamp}] ---\n{text}\n")
    return inputs_dir


_ARTEFACT_PATTERNS: tuple[str, ...] = ("render_*.png", "*.obj")


def _snapshot_artefact_paths(attempts_dir: Path) -> set[Path]:
    """Return the absolute paths of every artefact currently under
    ``attempts_dir`` matching ``_ARTEFACT_PATTERNS``.

    Used to diff before vs. after one ``Orchestrator.dispatch`` so the
    Streamlit handler can display only the artefacts that were created
    during the just-completed turn.  Returns an empty set when
    ``attempts_dir`` does not yet exist (first turn before any
    ``new_attempt`` call).
    """
    if not attempts_dir.exists():
        return set()
    found: set[Path] = set()
    for pattern in _ARTEFACT_PATTERNS:
        for p in attempts_dir.rglob(pattern):
            if p.is_file():
                found.add(p.resolve())
    return found


def dispatch_turn(
    session: Session,
    user_input: str,
    *,
    inputs_dir: Path,
    attempts_dir: Path | None = None,
    orchestrator: Orchestrator | None = None,
    llm_cache=None,
) -> TurnResult:
    """Run one user turn against ``session`` and return the reply.

    See module docstring for the contract.  ``attempts_dir`` defaults
    to ``config.ATTEMPTS_DIR`` when omitted — both the v4 REPL caller
    (which uses the global paths) and the Stage A Streamlit handler
    (which also uses the global paths per W13/O9) can rely on the
    default.  Stage B's per-session path threading is the moment to
    start passing ``session.attempts_dir`` explicitly.
    """
    if orchestrator is None:
        orchestrator = Orchestrator(session=session, llm_cache=llm_cache)

    if attempts_dir is None:
        attempts_dir = _CONFIG_ATTEMPTS_DIR

    # Snapshot the artefact set BEFORE dispatch so we can compute the
    # set of newly-created paths after the pipeline finishes.  Done
    # ahead of the try/finally because if the snapshot itself fails we
    # would rather raise loudly than swallow the underlying I/O error.
    pre_artefacts = _snapshot_artefact_paths(attempts_dir)

    try:
        # 1. Save the user's text to user_query.txt.
        save_user_input(user_input, inputs_dir)
        logger.info(f"[INPUT FILES]  saved to {inputs_dir.resolve()}")

        # 2. Receptionist reads the input files and decides whether to
        #    forward into the pipeline or reply directly.
        _trace("User", "Receptionist")
        validation = orchestrator.receptionist.validate_input(inputs_dir)
        logger.info(
            f"[RECEPTIONIST]  forward={validation['forward']}  "
            f"message={validation['message']}"
        )

        if not validation["forward"]:
            _trace("Receptionist", "User", "direct")
            reply = validation["message"]
            logger.info(f"[RECEPTIONIST -> USER]  {reply}")
            return TurnResult(
                reply_text=reply,
                forwarded=False,
                new_artefacts_paths=_compute_new_artefacts(
                    pre_artefacts, attempts_dir,
                ),
            )

        # 3. Receptionist forwarded — Orchestrator drives the dispatch loop.
        _trace("Receptionist", "Orchestrator", "forwarded")
        orchestrator.reset_turn()
        receptionist_summary = (validation.get("message") or "").strip()
        if receptionist_summary.startswith(_RECEPTIONIST_LABEL):
            receptionist_summary = receptionist_summary[
                len(_RECEPTIONIST_LABEL):
            ].lstrip()

        ft_str = (
            ", ".join(validation["file_types"])
            if validation["file_types"] else "text"
        )
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
            logger.error(
                "[DISPATCH]  empty user-facing message; substituted fallback"
            )
        _trace("Receptionist", "User", "delivered")
        logger.info(f"[RECEPTIONIST -> USER]  {outgoing}")
        return TurnResult(
            reply_text=outgoing,
            forwarded=True,
            new_artefacts_paths=_compute_new_artefacts(
                pre_artefacts, attempts_dir,
            ),
        )
    finally:
        # Snapshot every live agent's state back into session.agent_
        # states so that (a) v3 callers who rebuild Orchestrator per
        # turn pick up where this turn left off, and (b) the DH's
        # populate_database (which reads session.agent_states) sees
        # the actual session-time messages — not the empty placeholder
        # AgentStates created at Orchestrator-construction time.
        # Runs in a finally so a mid-dispatch crash still persists
        # whatever progress the agents made before the failure.
        _snapshot_agents_to_session(orchestrator, session)


def _compute_new_artefacts(
    pre_artefacts: set[Path], attempts_dir: Path,
) -> list[Path]:
    """Return artefacts under ``attempts_dir`` that did NOT exist when
    ``pre_artefacts`` was captured, sorted by mtime ascending.

    mtime ordering reflects creation order during this turn, which
    matches how the chat surface wants to display the renders
    (the first render generated appears first in the conversation).
    Failures to stat a path (e.g. it was moved between glob and stat)
    sort to the end so the chat surface still gets a stable list.
    """
    post = _snapshot_artefact_paths(attempts_dir)
    fresh = post - pre_artefacts

    def _mtime_key(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return float("inf")

    return sorted(fresh, key=_mtime_key)


def _snapshot_agents_to_session(
    orchestrator: Orchestrator, session: Session,
) -> None:
    """Write every live agent's snapshot_state into session.agent_states.

    Covers the seven chain agents + Orchestrator (all of which live in
    ``orchestrator._agents_by_key``) and the DatabaseHandler (held
    separately on the Orchestrator).  Each call replaces the existing
    ``session.agent_states[<key>]`` entry with a fresh AgentState.
    """
    for agent_key, agent in orchestrator._agents_by_key.items():
        session.agent_states[agent_key] = agent.snapshot_state()
    session.agent_states["database_handler"] = (
        orchestrator.database_handler.snapshot_state()
    )
