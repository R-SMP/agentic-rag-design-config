"""Database Handler agent — post-session interviewer.

The Database Handler (DH) runs ONCE per saved session, after the
user has typed ``quit`` and confirmed they want to save.  It is NOT
part of the dispatch loop, has no routing tools, and never speaks to
the user.

Its job is to interview each in-session agent (UII, Planner, DCIC,
DCII if enabled, TC, DCOI, Orchestrator, Receptionist — in that
order) about a list of database fields drawn from the
``forClaude`` schema, and to write each (question, answer) pair to
disk under ``database/<session_name>/<agent>/<field>.txt``.

Per-field interview protocol
----------------------------
For every field:

* The DH formulates a question and the system delivers it to the
  target agent (in this module called *Agent A*).
* Agent A replies in plain text.
* The DH decides what to do next by emitting ONE of two prefixes:

      ASK: <follow-up question for Agent A>
      SAVE: <final body to be written to the .txt file>

  ``ASK:`` runs another round of the conversation; ``SAVE:`` ends
  the loop and the system writes the body to disk.  The cap is
  ``MAX_DH_TURNS_PER_FIELD`` rounds.

* For SEMANTIC fields the DH must keep the saved body within
  ``EMBEDDING_MAX_RESPONSE_TOKENS`` tokens (counted with
  ``cl100k_base``).  When the body exceeds the cap, the DH is asked
  for a shorter version — once.  Quantitative fields are saved
  verbatim with no cap.

Memory model
------------
* The DH is stateful — its ``self.messages`` accumulates across every
  field's interview so it can remember what it already learned.
* Every interviewed agent's session-time history is *frozen* at the
  start of the interview phase (deep-copied before any DH
  conversation begins) and re-loaded at the start of every new
  conversation about a new field.  Whatever was said in a previous
  conversation between the DH and the agent (including earlier
  fields filled for the SAME agent) is therefore invisible to the
  agent in the next conversation.
"""

import logging
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from agents.database_handler.dh_trace import (
    close_dh_logging,
    dh_trace,
    init_dh_logging,
)
from agents.database_handler.token_utils import count_tokens
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.file_utils import ai_text
from agents.shared.llm_provider import make_system_message
from agents.shared.llm_retry import invoke_with_retry
from agents.shared.prompts import DH_TEMPLATE
from agents.shared.session import AgentState, Session
from agents.step_caps import MAX_DH_STEPS, MAX_DH_TURNS_PER_FIELD
from config import LOGS_DIR
from workflow_settings import settings as workflow_settings

# DH events go to a DEDICATED logger that writes to
# ``logs/database_handler_<ts>.log`` and does NOT propagate to the
# main session log.  See ``dh_trace.py``.
logger = logging.getLogger("database_handler")


# ---------------------------------------------------------------------------
# Per-agent question schedule
# ---------------------------------------------------------------------------
#
# Sequence is fixed: UII, Planner, DCIC, DCII (if enabled), TC, DCOI,
# Orchestrator, Receptionist.  Each entry corresponds to one row of
# the ``forClaude`` sheet of ``Agent-Database_v5.xlsx`` — one database
# field that the named agent is responsible for filling.
#
# Per the May-3 spec:
#   * Orchestrator has no rows in the sheet, so we ask it a single
#     generic "what did you do this session?" question.
#   * Rows whose ``Type`` is "File as-is" / "as-is" (User images,
#     User input 2D model files, Design Output file, Design Output
#     renders) are SKIPPED for now — they require copying the actual
#     files into the database folder.  Tracked as TODO entries.
#   * The two ``(Not yet implemented) User input 2D model files``
#     rows are SKIPPED for now.

SCHEDULE: list[dict] = [
    # ------------------------------------------------------------------
    # UII
    # ------------------------------------------------------------------
    {
        "agent_key": "user_input_inspector",
        "field": "User query description",
        "type": "Semantic",
        "description": (
            "Description of how the user requests something."
        ),
    },
    {
        "agent_key": "user_input_inspector",
        "field": "Design intent formulation",
        "type": "Semantic",
        "description": (
            "Formulation of the user needs, in terms of what the "
            "design needs to do / what is the application."
        ),
    },
    {
        "agent_key": "user_input_inspector",
        "field": "Functional Requirements",
        "type": "Semantic",
        "description": (
            "Formulation of the user needs, in terms of practical "
            "design features that have to be respected."
        ),
    },
    {
        "agent_key": "user_input_inspector",
        "field": "Problem - UII",
        "type": "Semantic",
        "description": (
            "Description of a problem encountered in the analysis "
            "of user inputs.  If no problem occurred this session, "
            "say so explicitly."
        ),
    },
    {
        "agent_key": "user_input_inspector",
        "field": "User clarification request",
        "type": "Semantic",
        "description": (
            "Any clarification you wanted to request from the user "
            "(e.g. ambiguous inputs, missing information).  If none "
            "was needed this session, say so explicitly."
        ),
    },
    {
        "agent_key": "user_input_inspector",
        "field": "User-defined quantitative inputs",
        "type": "Quantitative",
        "description": (
            "The quantitative inputs the user provided this session "
            "(numbers, units, locked values, etc.), as you "
            "extracted them."
        ),
    },
    {
        "agent_key": "user_input_inspector",
        "field": "User-defined qualitative inputs",
        "type": "Semantic",
        "description": (
            "The qualitative inputs the user provided this session "
            "(adjectives, target use case, stylistic constraints, "
            "etc.), as you extracted them."
        ),
    },
    {
        "agent_key": "user_input_inspector",
        "field": "User images descriptions",
        "type": "Semantic",
        "description": (
            "Your description of any images the user provided this "
            "session (what they show, what they imply for the "
            "design).  If no images were provided, say so "
            "explicitly."
        ),
    },
    # NOTE: The "User images" row (Type=File as-is) is intentionally
    # skipped here.  See TODO O6 in extra_utilities/TODO_known_issues.md.
    # NOTE: Both "(Not yet implemented) User input 2D model files"
    # rows are intentionally skipped here.  See TODO O7.

    # ------------------------------------------------------------------
    # Planner
    # ------------------------------------------------------------------
    {
        "agent_key": "planner",
        "field": "Problem - Planner",
        "type": "Semantic",
        "description": (
            "Description of a problem encountered in the workflow "
            "during this session.  If no problem occurred, say so "
            "explicitly."
        ),
    },
    {
        "agent_key": "planner",
        "field": "Plan",
        "type": "Semantic",
        "description": (
            "The plan you followed to solve the problem(s) "
            "encountered during this session.  If no plan beyond "
            "the natural pipeline was needed, say so explicitly."
        ),
    },
    {
        "agent_key": "planner",
        "field": "Problem solution - Planner",
        "type": "Semantic",
        "description": (
            "Description of how the problem(s) you faced were "
            "solved this session.  If none were solved (e.g. the "
            "session ended unresolved, or none arose), say so "
            "explicitly."
        ),
    },
    {
        "agent_key": "planner",
        "field": "Successful parameters",
        "type": "Quantitative",
        "description": (
            "The set(s) of input parameters for the Design "
            "Configurator that solved the problem this session "
            "(i.e. were eventually APPROVED).  If none, say so "
            "explicitly."
        ),
    },
    {
        "agent_key": "planner",
        "field": "Unsuccessful parameters",
        "type": "Quantitative",
        "description": (
            "Exemplary set(s) of input parameters for the Design "
            "Configurator that did NOT solve the problem this "
            "session (e.g. were REVISED, or otherwise failed).  If "
            "none, say so explicitly."
        ),
    },
    {
        "agent_key": "planner",
        "field": "Useful learning - Input parameters",
        "type": "Semantic",
        "description": (
            "Useful learning gathered this session about the input "
            "parameters of the Design Configurator (what worked, "
            "what did not, what to avoid next time)."
        ),
    },
    # NOTE: The "Design Output file" row (Type=as-is) is intentionally
    # skipped here.  See TODO O6.

    # ------------------------------------------------------------------
    # DCIC
    # ------------------------------------------------------------------
    {
        "agent_key": "dc_input_creator",
        "field": "Problem - DCIC",
        "type": "Semantic",
        "description": (
            "Problem(s) encountered when creating the input "
            "parameters for the Design Configurator this session.  "
            "If none, say so explicitly."
        ),
    },
    {
        "agent_key": "dc_input_creator",
        "field": "Invalid solution - DCIC",
        "type": "Semantic",
        "description": (
            "Explanation of any invalid change(s) you applied when "
            "trying to solve a problem this session.  If none, say "
            "so explicitly."
        ),
    },
    {
        "agent_key": "dc_input_creator",
        "field": "Valid solution - DCIC",
        "type": "Semantic",
        "description": (
            "Explanation of any valid change(s) you applied to "
            "solve the problem(s) this session.  If none, say so "
            "explicitly."
        ),
    },

    # ------------------------------------------------------------------
    # DCII (only interviewed when DC_INSPECTOR_ENABLED; otherwise
    # empty placeholder files are written — see populate_database)
    # ------------------------------------------------------------------
    {
        "agent_key": "dc_input_inspector",
        "field": "Problem - DCII",
        "type": "Semantic",
        "description": (
            "Problem(s) encountered when analyzing the input "
            "parameters created for the Design Configurator this "
            "session.  If none, say so explicitly."
        ),
        "requires_dcii_enabled": True,
    },
    {
        "agent_key": "dc_input_inspector",
        "field": "Validation of inputs - DCII",
        "type": "Semantic",
        "description": (
            "Reason(s) why a set of parameters was VALIDATED this "
            "session.  If no set was validated, say so explicitly."
        ),
        "requires_dcii_enabled": True,
    },
    {
        "agent_key": "dc_input_inspector",
        "field": "Rejection of inputs - DCII",
        "type": "Semantic",
        "description": (
            "Reason(s) why a set of parameters was REJECTED this "
            "session.  If no set was rejected, say so explicitly."
        ),
        "requires_dcii_enabled": True,
    },

    # ------------------------------------------------------------------
    # Tool Caller
    # ------------------------------------------------------------------
    {
        "agent_key": "tool_caller",
        "field": "Tool Caller problem",
        "type": "Semantic",
        "description": (
            "Description of any problem you encountered this "
            "session (e.g. a tool error, a missing input, a "
            "geometry-generation failure).  If none, say so "
            "explicitly."
        ),
    },
    {
        "agent_key": "tool_caller",
        "field": "Tool Caller problem solution",
        "type": "Semantic",
        "description": (
            "Description of what was done to solve the problem(s) "
            "you encountered this session.  If none arose, say so "
            "explicitly."
        ),
    },

    # ------------------------------------------------------------------
    # DCOI
    # ------------------------------------------------------------------
    # NOTE: The "Design Output renders" row (Type=as-is) is
    # intentionally skipped here.  See TODO O6.
    {
        "agent_key": "dc_output_inspector",
        "field": "Design Output Description",
        "type": "Semantic",
        "description": (
            "A general description of the design output produced "
            "this session — not the feedback, not whether it is "
            "correct, just describe the design in general."
        ),
    },
    {
        "agent_key": "dc_output_inspector",
        "field": "Design Output Correctness",
        "type": "Semantic",
        "description": (
            "Where the design did well: how it satisfied the "
            "design intent and the functional requirements, and "
            "the absence of problems."
        ),
    },
    {
        "agent_key": "dc_output_inspector",
        "field": "Design Output Problems",
        "type": "Semantic",
        "description": (
            "The main problems of the design: visible failures, "
            "and/or design intent / functional requirements that "
            "were not respected."
        ),
    },

    # ------------------------------------------------------------------
    # Orchestrator (no row in the sheet — generic summary, per spec)
    # ------------------------------------------------------------------
    {
        "agent_key": "orchestrator",
        "field": "Session summary",
        "type": "Semantic",
        "description": (
            "A brief description of what you did this session — "
            "how you coordinated the chain, what hand-offs you "
            "made, any escalations you handled."
        ),
    },

    # ------------------------------------------------------------------
    # Receptionist
    # ------------------------------------------------------------------
    {
        "agent_key": "receptionist",
        "field": "User query problem",
        "type": "Semantic",
        "description": (
            "Description of any problem you detected in the user's "
            "request(s) this session (ambiguity, conflict, "
            "infeasible numbers, missing information, etc.).  If "
            "none, say so explicitly."
        ),
    },
    {
        "agent_key": "receptionist",
        "field": "Receptionist Response problem",
        "type": "Semantic",
        "description": (
            "Description of any problem in your answer(s) to the "
            "user — most often, feedback the user gave you asking "
            "to clarify, add, remove, or change something.  If "
            "none, say so explicitly."
        ),
    },
    {
        "agent_key": "receptionist",
        "field": "Receptionist Response solution",
        "type": "Semantic",
        "description": (
            "Description of how you answered the user to "
            "successfully resolve the problem (do NOT consider it "
            "a good solution unless the user explicitly said so).  "
            "If no problem arose, say so explicitly."
        ),
    },
]


# Filename slug rule: lowercase, strip leading parenthesised qualifier
# (e.g. "(Not yet implemented) "), replace any non-alphanumeric run
# with a single underscore, trim leading / trailing underscores.
_LEADING_PAREN_RE = re.compile(r"^\s*\([^)]*\)\s*")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str, max_len: int = 80) -> str:
    """Make ``text`` safe for use as a filename component.

    Examples
    --------
    >>> _slugify("User query description")
    'user_query_description'
    >>> _slugify("Problem - UII")
    'problem_uii'
    >>> _slugify("(Not yet implemented) User input 2D model files")
    'user_input_2d_model_files'
    """
    s = _LEADING_PAREN_RE.sub("", text or "").strip().lower()
    s = _NON_ALNUM_RE.sub("_", s).strip("_")
    if len(s) > max_len:
        s = s[:max_len].rstrip("_")
    return s or "entry"


# Indented blank-line-tolerant block formatter for the .log file.  The
# DH log is a debugging artefact — preserve message bodies exactly,
# never truncate, but indent every line so lines stay attributable to
# the surrounding logger record.
_LOG_INDENT = "    "


def _format_block(label: str, body: str) -> str:
    """Format a multi-line message body for the DH log, no truncation."""
    body = body if body is not None else ""
    indented = "\n".join(_LOG_INDENT + line for line in body.split("\n"))
    return f"{label}\n{indented}"


# Protocol prefixes the DH must use after each Agent-A reply.
_ASK_PREFIX = "ASK:"
_SAVE_PREFIX = "SAVE:"


def _parse_dh_decision(text: str) -> tuple[str, str]:
    """Parse a DH decision into ``(kind, payload)``.

    *kind* is one of ``"ASK"``, ``"SAVE"``, or ``"PROTOCOL_ERROR"``.
    *payload* is the trimmed text after the prefix (or the raw text on
    a protocol error, for fallback handling).
    """
    stripped = (text or "").lstrip()
    if stripped.upper().startswith(_ASK_PREFIX):
        return "ASK", stripped[len(_ASK_PREFIX):].lstrip()
    if stripped.upper().startswith(_SAVE_PREFIX):
        return "SAVE", stripped[len(_SAVE_PREFIX):].lstrip()
    return "PROTOCOL_ERROR", stripped


class DatabaseHandler(BaseChainAgent):
    """Stateful post-session interviewer."""

    AGENT_KEY = "database_handler"

    def __init__(
        self,
        state: AgentState | None = None,
        session: Session | None = None,
        *,
        llm_cache=None,
    ):
        if session is None:
            raise TypeError(
                "DatabaseHandler now requires a Session.  Construct "
                "one via Session(...) or Session.create_for_v3(...) "
                "and pass it in."
            )
        if state is None:
            state = session.agent_states.setdefault(
                "database_handler", AgentState(agent_key="database_handler"),
            )
        super().__init__(state=state, session=session, llm_cache=llm_cache)
        # The DH binds no tools — it only emits plain text.
        self.system_prompt: str = DH_TEMPLATE

        # Cached for SEMANTIC token-cap enforcement.
        self.max_response_tokens: int = int(
            workflow_settings.EMBEDDING_MAX_RESPONSE_TOKENS
        )

    # ------------------------------------------------------------------
    # Public API — called once by loader after user confirms "save"
    # ------------------------------------------------------------------

    def populate_database(
        self,
        session_dir: Path,
        *,
        session_timestamp: str | None = None,
        orchestrator=None,
    ) -> int:
        """Walk the schedule and write one .txt per (agent, field).

        Returns the number of entries written.  When a conversation
        with a specific agent fails, that agent's entry is written
        with an ``ERROR`` body instead of being silently dropped —
        the per-session folder structure stays consistent and the
        failure is visible to the future RAG pipeline.

        v3 Phase 1 commit 6 changes how the DH talks to each agent:

        * It reads each agent's session-time messages from
          ``self.session.agent_states[agent_key].messages`` (read-
          only — never mutated).  No more freeze/restore pump.
        * It needs each agent's wired ``system_prompt`` + ``base_llm``
          to invoke the conversation.  When ``orchestrator`` is
          supplied (the v4 loader passes its already-built one), the
          DH reads them from there; otherwise it constructs a fresh
          one from ``self.session`` and uses that.  The Orchestrator
          construction is idempotent against the Session — it just
          re-runs routing wiring to assemble each agent's prompt.

        ``dc_inspector_enabled`` is read from ``self.session``, not a
        parameter — the Session is the source of truth for session-
        config.

        Opens (and at the end, closes) a dedicated DH log + flow-trace
        pair under ``logs/``.  Both files are picked up by the
        regular session-archive sweep so they end up alongside the
        main session log in ``previous_sessions/<ID>/``.

        *session_timestamp* is the ``YYYYMMDD_HHMMSS`` slug computed at
        SESSION START (same one used by the main session log
        filename).  When supplied, the DH log + flow-trace files
        share that timestamp so they sort together with the rest of
        the session artefacts.  When ``None`` (e.g. the DH is invoked
        outside of the loader), fall back to ``datetime.now()``.
        See ``extra_utilities/warnings_developer.md`` (W11).
        """
        session_dir.mkdir(parents=True, exist_ok=True)

        # Build a wired Orchestrator from self.session if the caller
        # didn't supply one.  Used only to read each agent's
        # ``system_prompt`` and ``base_llm`` — never mutated, never
        # invoked.
        if orchestrator is None:
            from agents.orchestrator import Orchestrator
            orchestrator = Orchestrator(session=self.session)

        dc_inspector_enabled = self.session.dc_inspector_enabled

        try:
            log_path, trace_path = init_dh_logging(
                LOGS_DIR,
                session_timestamp=session_timestamp,
            )
            print(f"DH log file: {log_path.resolve()}")
            print(f"DH trace file: {trace_path.resolve()}")
        except Exception as exc:  # pragma: no cover
            log_path = trace_path = None
            print(f"(warning) could not open DH log files: {exc}")

        try:
            logger.info(
                f"[DH]  populate_database start; session_dir={session_dir.resolve()}; "
                f"dc_inspector_enabled={dc_inspector_enabled}; "
                f"max_response_tokens={self.max_response_tokens}; "
                f"embedding={workflow_settings.EMBEDDING_PROVIDER}/"
                f"{workflow_settings.EMBEDDING_MODEL}@"
                f"{workflow_settings.EMBEDDING_VECTOR_DIMS}d"
            )

            written = 0
            for entry in SCHEDULE:
                agent_key = entry["agent_key"]
                field = entry["field"]

                # DCII gating.  When the DCII is disabled this session
                # we still create the agent folder and write an EMPTY
                # placeholder file for every DCII-bound field, so the
                # per-session folder layout stays uniform across runs
                # regardless of the toggle.
                if (
                    entry.get("requires_dcii_enabled")
                    and not dc_inspector_enabled
                ):
                    logger.info(
                        f"[DH]  DCII disabled; writing empty "
                        f"placeholder for field '{field}'"
                    )
                    try:
                        path = self._write_empty_entry(
                            session_dir=session_dir,
                            agent_key=agent_key,
                            field=field,
                        )
                        logger.info(f"[DH]  wrote (empty) {path}")
                        written += 1
                    except OSError as exc:
                        logger.warning(
                            f"[DH]  failed to write empty placeholder "
                            f"for {agent_key}/{field}: {exc}"
                        )
                    continue

                agent = orchestrator._agents_by_key.get(agent_key)
                agent_state = self.session.agent_states.get(agent_key)
                if agent is None or agent_state is None:
                    logger.warning(
                        f"[DH]  unknown agent '{agent_key}' in schedule; "
                        f"skipped"
                    )
                    self._write_error_entry(
                        session_dir=session_dir,
                        agent_key=agent_key,
                        field=field,
                        error_message=(
                            f"agent key '{agent_key}' is not present in "
                            f"the orchestrator's registry / session.agent_"
                            f"states; the DH could not interview it."
                        ),
                    )
                    continue

                logger.info(
                    f"[DH]  starting conversation with {agent_key} "
                    f"(field='{field}', type={entry.get('type', 'Semantic')})"
                )
                try:
                    question, answer = self._run_one_conversation(
                        agent_key=agent_key,
                        agent_system_prompt=getattr(agent, "system_prompt", "") or "",
                        agent_provider=getattr(agent, "provider", self.provider),
                        agent_base_llm=getattr(agent, "base_llm", None) or agent.llm,
                        agent_messages=list(agent_state.messages),
                        field=field,
                        description=entry.get("description", ""),
                        field_type=entry.get("type", "Semantic"),
                    )
                except Exception as exc:  # pragma: no cover — defensive
                    logger.warning(
                        f"[DH]  conversation with {agent_key} failed: {exc}"
                    )
                    self._write_error_entry(
                        session_dir=session_dir,
                        agent_key=agent_key,
                        field=field,
                        error_message=(
                            f"the DH conversation with {agent_key} "
                            f"raised an exception: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                    )
                    continue

                try:
                    path = self._write_entry(
                        session_dir=session_dir,
                        agent_key=agent_key,
                        field=field,
                        question=question,
                        answer=answer,
                    )
                    logger.info(
                        f"[DH]  wrote {path}\n"
                        f"{_format_block('FINAL saved body:', answer)}"
                    )
                    written += 1
                except OSError as exc:
                    logger.warning(
                        f"[DH]  failed to write entry for {agent_key}: {exc}"
                    )

            logger.info(
                f"[DH]  populate_database end; entries written={written}"
            )
            return written
        finally:
            close_dh_logging()

    # ------------------------------------------------------------------
    # Conversation primitives
    # ------------------------------------------------------------------

    def _run_one_conversation(
        self,
        agent_key: str,
        agent_system_prompt: str,
        agent_provider: str,
        agent_base_llm,
        agent_messages: list,
        field: str,
        description: str,
        field_type: str,
    ) -> tuple[str, str]:
        """Run one DH-driven conversation about *field* with the named agent.

        Loop:
          1. DH formulates an initial question and the system delivers
             it to Agent A.
          2. Agent A replies.
          3. DH emits ``ASK: ...`` (loop) or ``SAVE: ...`` (terminate).
          4. For SEMANTIC fields, the saved body is checked against the
             token cap; if over, the DH is asked once for a shorter
             version.

        v3 Phase 1 commit 6: the conversation runs entirely in a local
        ``convo_buffer`` list seeded from *agent_messages* (a copy of
        ``session.agent_states[agent_key].messages``).  Neither the
        live agent (if one even exists at this point) nor the
        AgentState is mutated.  Each call to this method starts from
        a fresh seed of session-time messages, so a per-field
        deepcopy/restore pump is no longer needed — the W6 / O4
        invariants hold by construction.
        """
        # Local conversation buffer.  The DH appends its question and
        # the agent's reply here; nothing is written back to the
        # AgentState or to any live agent instance.
        convo_buffer: list = list(agent_messages)

        is_semantic = (field_type or "Semantic").strip().lower() == "semantic"

        # Step 1: DH formulates the initial question.
        first_question = self._formulate_question(
            agent_key=agent_key,
            field=field,
            description=description,
            field_type=field_type,
        )
        logger.info(
            f"[DH]  initial question for {agent_key}/{field}\n"
            f"{_format_block('DH -> ' + agent_key + ':', first_question)}"
        )

        # Step 2+: alternate Agent A reply / DH decision until the DH
        # emits SAVE or the per-field cap is hit.
        last_question = first_question
        last_answer = ""
        final_body: str | None = None

        for round_idx in range(MAX_DH_TURNS_PER_FIELD):
            # ---- Agent A turn -----------------------------------------
            answer = self._ask_agent(
                agent_key=agent_key,
                agent_system_prompt=agent_system_prompt,
                agent_provider=agent_provider,
                agent_base_llm=agent_base_llm,
                convo_buffer=convo_buffer,
                field=field,
                question=last_question,
            )
            last_answer = answer

            # Record the round in the DH's own running history so
            # subsequent fields can reference what was just said.
            self.messages.append(
                HumanMessage(
                    content=(
                        f"Agent: {agent_key}\nField: {field}\n"
                        f"Field type: {field_type}\n"
                        f"My question to {agent_key}: {last_question}\n"
                        f"{agent_key}'s reply: {answer}"
                    )
                )
            )

            # ---- DH decision turn -------------------------------------
            decision_kind, decision_payload = self._decide_next(
                agent_key=agent_key,
                field=field,
                field_type=field_type,
                description=description,
                last_question=last_question,
                last_answer=answer,
                round_idx=round_idx,
            )

            if decision_kind == "SAVE":
                final_body = decision_payload
                break
            if decision_kind == "ASK":
                last_question = decision_payload
                logger.info(
                    f"[DH]  follow-up #{round_idx + 1} for "
                    f"{agent_key}/{field}\n"
                    f"{_format_block('DH -> ' + agent_key + ':', last_question)}"
                )
                continue
            # PROTOCOL_ERROR — log and bail with the agent's last
            # answer as the body.  Better to save something than
            # nothing.
            logger.warning(
                f"[DH]  protocol error from DH for "
                f"{agent_key}/{field} (no ASK:/SAVE: prefix); "
                f"using agent's last answer as body."
            )
            final_body = answer
            break

        # If the per-field cap was reached without a SAVE, fall back
        # to the agent's last answer.
        if final_body is None:
            logger.warning(
                f"[DH]  per-field turn cap "
                f"({MAX_DH_TURNS_PER_FIELD}) reached for "
                f"{agent_key}/{field} without SAVE; using last answer."
            )
            final_body = last_answer

        if not (final_body or "").strip():
            final_body = "(no usable content was produced for this field this session)"

        # Token-cap enforcement applies ONLY to SEMANTIC fields.
        if is_semantic:
            final_body = self._enforce_semantic_cap(
                agent_key=agent_key,
                field=field,
                description=description,
                body=final_body,
            )

        return first_question, final_body

    def _ask_agent(
        self,
        agent_key: str,
        agent_system_prompt: str,
        agent_provider: str,
        agent_base_llm,
        convo_buffer: list,
        field: str,
        question: str,
    ) -> str:
        """Send ONE question to Agent A and return their plain-text reply.

        The conversation lives in *convo_buffer* (a local list, not on
        any agent instance).  The function appends the question + the
        agent's response to that buffer in place, mirroring the shape
        the v4 code maintained on ``agent.messages`` — but without
        touching session.agent_states or any live agent.
        """
        dh_trace("DH", agent_key, note=f"asks ({field})")
        convo_buffer.append(HumanMessage(content=question))

        # Use the agent's BASE llm (no tool bindings) so the model is
        # free to reply in plain prose without trying to invoke
        # routing tools that no longer make sense post-session.
        response = invoke_with_retry(
            agent_base_llm,
            [make_system_message(agent_system_prompt, agent_provider)]
            + convo_buffer,
            f"DH<-{agent_key}",
        )
        convo_buffer.append(response)
        answer = ai_text(getattr(response, "content", "")).strip()
        if not answer:
            answer = "(agent produced no text in response)"

        dh_trace(agent_key, "DH", note="answers")
        logger.info(
            f"[DH]  reply received from {agent_key} ({field})\n"
            f"{_format_block(agent_key + ' -> DH:', answer)}"
        )
        return answer

    def _decide_next(
        self,
        agent_key: str,
        field: str,
        field_type: str,
        description: str,
        last_question: str,
        last_answer: str,
        round_idx: int,
    ) -> tuple[str, str]:
        """Ask the DH whether to ASK a follow-up or SAVE the final body.

        Returns ``(kind, payload)`` where *kind* is ``"ASK"``,
        ``"SAVE"``, or ``"PROTOCOL_ERROR"``.
        """
        rounds_left = max(0, MAX_DH_TURNS_PER_FIELD - (round_idx + 1))
        is_semantic = (field_type or "Semantic").strip().lower() == "semantic"
        cap_line = (
            f"This is a SEMANTIC field — your SAVE: body MUST stay "
            f"under {self.max_response_tokens} tokens (cl100k_base; "
            f"prefer <600).  Apply the embedding-friendly rules from "
            f"your system prompt."
            if is_semantic
            else "This is a QUANTITATIVE field — save the data verbatim, "
            "no token cap, do not paraphrase numbers or units."
        )
        instruction = (
            "DECISION TURN.\n\n"
            f"Target agent: {agent_key}\n"
            f"Field: {field}\n"
            f"Field type: {field_type}\n"
            f"Field description: {description}\n\n"
            f"You just asked: {last_question}\n"
            f"{agent_key} replied: {last_answer}\n\n"
            f"{cap_line}\n"
            f"Follow-up rounds remaining: {rounds_left}.\n\n"
            "Reply with EXACTLY ONE of:\n"
            "  ASK: <a follow-up question for the agent>\n"
            "  SAVE: <the final body to write to the .txt file>\n"
            "The very first non-whitespace characters of your reply "
            "must be either 'ASK:' or 'SAVE:'."
        )
        self.messages.append(HumanMessage(content=instruction))

        for _ in range(MAX_DH_STEPS):
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + self.messages,
                "DH-decide",
            )
            self.messages.append(response)
            text = ai_text(getattr(response, "content", "")).strip()
            if not text:
                continue
            kind, payload = _parse_dh_decision(text)
            logger.info(
                f"[DH]  decision for {agent_key}/{field} (round "
                f"{round_idx + 1}): kind={kind}\n"
                f"{_format_block('DH decision raw:', text)}"
            )
            return kind, payload

        # All MAX_DH_STEPS attempts came back empty — treat as protocol
        # error so the caller falls back to the agent's last answer.
        logger.warning(
            f"[DH]  decide_next produced no usable output for "
            f"{agent_key}/{field} after {MAX_DH_STEPS} attempts."
        )
        return "PROTOCOL_ERROR", ""

    def _formulate_question(
        self,
        agent_key: str,
        field: str,
        description: str,
        field_type: str,
    ) -> str:
        """Ask the DH's own LLM to produce the FIRST question for *agent_key*.

        The DH is shown the field name, the field's "Type" tag, and
        the schema description.  It is told to STAY FAITHFUL to the
        original intent of the field.
        """
        instruction = (
            "FIRST QUESTION TURN.\n\n"
            f"Target agent: {agent_key}\n"
            f"Database field to fill: {field}\n"
            f"Field type: {field_type}\n"
            f"Field description (from the database schema): "
            f"{description}\n\n"
            "Write ONE clear, specific question for this agent that "
            "asks them to fill the named field for this session.  "
            "Stay faithful to the original intent of the field; do "
            "not invent details that have no solid grounds.  You "
            "MAY adapt the wording slightly based on the design "
            "configurator's goal and on what earlier agents have "
            "already told you in this same save, IF such adaptation "
            "is genuinely useful and does not drift the question "
            "away from the original intent.\n\n"
            "Reply with the question only — no preamble, no labels, "
            "no markdown, NO 'ASK:' or 'SAVE:' prefix.  The protocol "
            "prefixes are only for decision turns AFTER the agent "
            "has replied."
        )
        self.messages.append(HumanMessage(content=instruction))

        for _ in range(MAX_DH_STEPS):
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + self.messages,
                "DH-formulate",
            )
            self.messages.append(response)
            text = ai_text(getattr(response, "content", "")).strip()
            if text:
                # If the model accidentally prefixed ASK:/SAVE: on the
                # FIRST turn, strip it — the protocol only applies to
                # decision turns.
                kind, payload = _parse_dh_decision(text)
                if kind in ("ASK", "SAVE"):
                    return payload or text
                return text

        # Fallback when the model produces nothing usable.  Better to
        # ask a generic question than to skip the entry entirely.
        fallback = (
            f"Please describe, for this session, the database "
            f"field '{field}' — {description}"
        ).strip()
        logger.warning(
            f"[DH]  formulate_question yielded no text for "
            f"{agent_key}/{field}; using fallback question."
        )
        return fallback

    # ------------------------------------------------------------------
    # SEMANTIC token-cap enforcement
    # ------------------------------------------------------------------

    def _enforce_semantic_cap(
        self,
        agent_key: str,
        field: str,
        description: str,
        body: str,
    ) -> str:
        """Ensure *body* fits within the SEMANTIC token cap.

        When *body* is over the cap, asks the DH ONCE for a shorter
        version and accepts whatever comes back.  If the second
        attempt is still over the cap, logs a warning but saves the
        shorter of the two — the goal is best-effort compliance, not
        infinite-loop perfection.
        """
        n = count_tokens(body)
        if n <= self.max_response_tokens:
            logger.info(
                f"[DH]  semantic body within cap for "
                f"{agent_key}/{field}: {n} <= "
                f"{self.max_response_tokens} tokens"
            )
            return body

        logger.warning(
            f"[DH]  semantic body OVER cap for {agent_key}/{field}: "
            f"{n} > {self.max_response_tokens} tokens; asking for "
            f"shorter version."
        )
        instruction = (
            "TOKEN-CAP COMPRESSION TURN.\n\n"
            f"Field: {field}\n"
            f"Field description: {description}\n\n"
            f"Your last SAVE: body for this field is "
            f"{n} tokens long under cl100k_base, but the cap is "
            f"{self.max_response_tokens}.  Rewrite it to fit comfortably "
            "below the cap (prefer <600) WITHOUT losing the field's "
            "meaning.  Apply the embedding-friendly rules from your "
            "system prompt: self-contained, declarative prose, "
            "domain-faithful, one topic per file, no filler.\n\n"
            "Reply with EXACTLY:\n"
            "  SAVE: <the shorter body>\n"
            "Do not use ASK: this turn — the system will save whatever "
            "you produce."
        )
        self.messages.append(HumanMessage(content=instruction))

        for _ in range(MAX_DH_STEPS):
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + self.messages,
                "DH-compress",
            )
            self.messages.append(response)
            text = ai_text(getattr(response, "content", "")).strip()
            if not text:
                continue
            kind, payload = _parse_dh_decision(text)
            shorter = payload if kind in ("ASK", "SAVE") else text
            n2 = count_tokens(shorter)
            logger.info(
                f"[DH]  compressed body for {agent_key}/{field}: "
                f"{n} -> {n2} tokens\n"
                f"{_format_block('DH compressed body:', shorter)}"
            )
            if n2 <= self.max_response_tokens:
                return shorter
            # Compression didn't reach the cap — keep the shorter of
            # the two and move on.
            logger.warning(
                f"[DH]  compression did not reach cap for "
                f"{agent_key}/{field} ({n2} > "
                f"{self.max_response_tokens}); saving the shorter body."
            )
            return shorter if n2 < n else body

        logger.warning(
            f"[DH]  compression turn produced no output for "
            f"{agent_key}/{field}; saving original over-cap body."
        )
        return body

    # ------------------------------------------------------------------
    # Disk I/O
    # ------------------------------------------------------------------

    def _entry_path(
        self,
        session_dir: Path,
        agent_key: str,
        field: str,
    ) -> Path:
        """Return the path for ``<session>/<agent>/<slugified field>.txt``."""
        agent_dir = session_dir / agent_key
        agent_dir.mkdir(parents=True, exist_ok=True)
        return agent_dir / f"{_slugify(field)}.txt"

    def _write_entry(
        self,
        session_dir: Path,
        agent_key: str,
        field: str,
        question: str,
        answer: str,
    ) -> Path:
        """Write one (question, answer) pair to disk and return path."""
        path = self._entry_path(session_dir, agent_key, field)
        path.write_text(
            f"--- Field ---\n{field}\n\n"
            "--- Question (asked by Database Handler) ---\n"
            f"{question}\n\n"
            "--- Answer (from agent) ---\n"
            f"{answer}\n",
            encoding="utf-8",
        )
        return path

    def _write_error_entry(
        self,
        session_dir: Path,
        agent_key: str,
        field: str,
        error_message: str,
    ) -> Path:
        """Write a sentinel ``ERROR:`` entry when the conversation failed."""
        path = self._entry_path(session_dir, agent_key, field)
        path.write_text(
            f"ERROR: {error_message}\n",
            encoding="utf-8",
        )
        return path

    def _write_empty_entry(
        self,
        session_dir: Path,
        agent_key: str,
        field: str,
    ) -> Path:
        """Write an EMPTY placeholder file for a skipped entry.

        Used today only when a DCII row is reached and
        ``DC_INSPECTOR_ENABLED`` is False.
        """
        path = self._entry_path(session_dir, agent_key, field)
        path.write_text("", encoding="utf-8")
        return path

