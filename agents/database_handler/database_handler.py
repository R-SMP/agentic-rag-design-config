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

import json
import logging
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

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
from config import ATTEMPTS_DIR, INPUT_IMAGES_DIR, LOGS_DIR, USER_INPUTS_DIR
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

# Max length of the short label shown under the Database Handler's
# flowchart box while the DH is interviewing.  Beyond this the
# derived label is ellipsised.  Each SCHEDULE entry may also carry an
# explicit ``"short_label"`` override; absent that, ``_short_label_for``
# derives one from ``field``.
_SHORT_LABEL_MAX = 26

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


# Compiled trim patterns for ``_short_label_for``.  Built once at
# import to keep the per-field hot path cheap.
_AGENT_SUFFIX_RE = re.compile(r"\s*-\s*(UII|DCIC|DCII|Planner)\s*$")
_USER_DEFINED_PREFIX_RE = re.compile(r"^User-defined\s+", re.IGNORECASE)
_RECEPTIONIST_PREFIX_RE = re.compile(r"^Receptionist\s+", re.IGNORECASE)
_TC_PREFIX_RE = re.compile(r"^Tool Caller\s+")


def _short_label_for(entry: dict) -> str:
    """Return a short caption for the flowchart's per-agent label.

    Used by ``populate_database`` to publish a ``generic_tool`` event
    while the DH is interviewing — the frontend writes the value into
    the gray-italic caption under the Database Handler's box, the same
    UI slot that records the most recent generic tool any other agent
    called.  Output is capped at :data:`_SHORT_LABEL_MAX` characters;
    longer derived labels are ellipsised.

    Resolution order: explicit ``entry["short_label"]`` first, then
    auto-derivation from ``entry["field"]``.
    """
    explicit = entry.get("short_label")
    if explicit:
        s = str(explicit).strip()
        return (s[:_SHORT_LABEL_MAX].rstrip() + "…") if len(s) > _SHORT_LABEL_MAX else s

    s = (entry.get("field") or "").strip()
    s = _LEADING_PAREN_RE.sub("", s)
    s = _AGENT_SUFFIX_RE.sub("", s)
    s = _USER_DEFINED_PREFIX_RE.sub("", s)
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    s = _RECEPTIONIST_PREFIX_RE.sub("", s)
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    s = _TC_PREFIX_RE.sub("TC ", s)
    if len(s) > _SHORT_LABEL_MAX:
        s = s[:_SHORT_LABEL_MAX].rstrip() + "…"
    return s or (entry.get("field", "field")[:_SHORT_LABEL_MAX])


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


# ---------------------------------------------------------------------------
# SEMANTIC SAVE body: QUESTION: / ANSWER: headers
# ---------------------------------------------------------------------------
#
# For SEMANTIC fields the DH's SAVE body must itself carry two
# headers:
#
#   QUESTION: <short embedding-friendly question>
#   ANSWER:   <embedding-friendly final answer>
#
# Both blocks may span multiple lines.  The headers are case-
# insensitive and tolerate whitespace before the colon.  When either
# header is missing the parser returns ``(None, None)`` and the caller
# falls back to a defensive behaviour (treat the whole body as the
# answer; reuse the asked question as the saved question).
# ---------------------------------------------------------------------------

# Multi-pair SAVE-body parser.  A SEMANTIC SAVE body may contain N
# pairs (multi-answer split) and/or ``ATTEMPT: <NNN>`` headers
# preceding each pair (multi-attempt identifying-Q case).  We walk
# the body line-by-line and accumulate ``(attempt_id_or_None, Q, A)``
# triples in order.  Each Q/A pair becomes one ``.txt`` file at
# write time, with naming controlled by the caller (single-pair vs
# multi-pair vs multi-attempt — see :meth:`_write_entry`).
_SAVE_LINE_RE = re.compile(
    r"^\s*(ATTEMPT|QUESTION|ANSWER)\s*:\s*(.*)$",
    re.IGNORECASE,
)


def _parse_save_body_semantic(
    text: str,
) -> list[tuple[str | None, str, str]]:
    """Split a SEMANTIC SAVE body into a list of ``(attempt_id, Q, A)``
    triples in order.

    Supported shapes:

    * Single Q/A pair (legacy single-answer)::

          QUESTION: ...
          ANSWER: ...

      → returns ``[(None, q, a)]``.

    * N Q/A pairs back-to-back (multi-answer split, Extension A)::

          QUESTION: q1
          ANSWER: a1
          QUESTION: q2
          ANSWER: a2

      → returns ``[(None, q1, a1), (None, q2, a2)]``.

    * N attempt-tagged blocks (multi-attempt identifying-Q,
      Extension B)::

          ATTEMPT: 002
          QUESTION: q1
          ANSWER: a1
          ATTEMPT: 005
          QUESTION: q2
          ANSWER: a2

      → returns ``[("002", q1, a1), ("005", q2, a2)]``.  The attempt
      id is normalised through ``_normalise_attempt_input`` so a
      slug or "attempt NNN" prefix is also accepted.

    * Mixed (illegal — some pairs have ATTEMPT, others don't) — the
      parser preserves the per-pair attempt_id (``None`` for pairs
      lacking the header), letting the caller decide how to handle
      the inconsistency.

    Returns an empty list when the body has no recognisable QUESTION /
    ANSWER headers — the caller treats that as a protocol slip and
    falls back to a single-pair best-effort.
    """
    if not text:
        return []

    triples: list[tuple[str | None, str, str]] = []
    current_attempt: str | None = None
    current_q: str | None = None
    current_a_buf: list[str] | None = None
    in_answer = False

    def _flush() -> None:
        nonlocal current_q, current_a_buf, current_attempt, in_answer
        if current_q is not None and current_a_buf is not None:
            ans = "\n".join(current_a_buf).strip()
            q = current_q.strip()
            if q or ans:
                triples.append((current_attempt, q, ans))
        current_q = None
        current_a_buf = None
        in_answer = False

    for line in text.splitlines():
        m = _SAVE_LINE_RE.match(line)
        if m:
            tag = m.group(1).upper()
            body = m.group(2).strip()
            if tag == "ATTEMPT":
                _flush()
                # Normalise inline so the caller doesn't have to.
                norm = _normalise_attempt_input(body)
                current_attempt = norm if norm is not None else body
                continue
            if tag == "QUESTION":
                _flush()
                current_q = body
                in_answer = False
                continue
            if tag == "ANSWER":
                current_a_buf = [body] if body else []
                in_answer = True
                continue
        # Continuation line — append to whichever buffer is active.
        if in_answer and current_a_buf is not None:
            current_a_buf.append(line)
        elif current_q is not None and not in_answer:
            # multi-line question continuation
            current_q = (current_q + "\n" + line).rstrip()
    _flush()
    return triples


# ---------------------------------------------------------------------------
# Safety-net cleanup for SEMANTIC bodies
# ---------------------------------------------------------------------------
#
# The DH's prompt instructs it to strip these artefacts itself; the
# helpers below are a defensive backstop for the cases where it slips
# (which is most of them, in practice — LLMs reliably echo the
# routing-tool wrapper they see in the agent's reply).  Only SEMANTIC
# fields are subject to cleanup; QUANTITATIVE bodies pass through
# verbatim per the user direction.
# ---------------------------------------------------------------------------

# Routing-tool wrapper extraction.  When an agent ends its turn with
# call_orchestrator / call_receptionist, langchain renders the
# ``content`` of the AI message as a JSON-stringified payload that
# starts with ``{"call_orchestrator":`` (or similar).  We extract the
# inner string value and use it as the substantive body.
_ROUTING_TOOL_NAMES = (
    "call_orchestrator",
    "call_receptionist",
    "call_planner",
    "call_user_input_inspector",
    "call_dc_input_creator",
    "call_dc_input_inspector",
    "call_dc_output_inspector",
    "call_tool_caller",
)

# Match a routing-tool JSON literal embedded anywhere in the body —
# even with text before/after.  Captures the INNER string (group 1)
# WITHOUT the outer quotes.  The inner may contain real newlines (which
# is invalid JSON, but is what the LLM actually emits in practice when
# it mirrors a tool-call shape from its history), so we decode escapes
# manually instead of round-tripping through ``json.loads``.
_ROUTING_TOOL_JSON_RE = re.compile(
    r'\{\s*"(?:' + "|".join(_ROUTING_TOOL_NAMES) + r')"\s*:\s*'
    r'"((?:[^"\\]|\\.)*)"\s*\}',
)

_JSON_ESCAPE_MAP = {
    "n":  "\n",
    "t":  "\t",
    "r":  "\r",
    '"':  '"',
    "\\": "\\",
    "/":  "/",
    "b":  "\b",
    "f":  "\f",
}


def _decode_json_string_escapes(inner: str) -> str:
    """Replace ``\\n`` / ``\\t`` / ``\\"`` / ``\\\\`` (etc.) with the
    real characters.  Unknown escape sequences are passed through
    untouched so we never silently lose data."""
    out: list[str] = []
    i = 0
    n = len(inner)
    while i < n:
        ch = inner[i]
        if ch == "\\" and i + 1 < n:
            nxt = inner[i + 1]
            mapped = _JSON_ESCAPE_MAP.get(nxt)
            if mapped is not None:
                out.append(mapped)
                i += 2
                continue
            # Unknown escape — keep literal so we don't lose info.
            out.append(ch + nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _unwrap_routing_tool_json(body: str) -> str:
    """Replace every routing-tool JSON wrapper in *body* with its inner
    string.

    Handles both the "whole body is one JSON object" case AND the
    common "narration line + JSON tool-call object on a later line"
    case langchain agents emit when their LLM mirrors its session-time
    pattern.  Escape sequences inside the captured string are decoded
    via :func:`_decode_json_string_escapes` (NOT via ``json.loads``,
    which rejects the real newlines the LLM frequently inserts inside
    the value).
    """
    if not body:
        return body
    return _ROUTING_TOOL_JSON_RE.sub(
        lambda m: _decode_json_string_escapes(m.group(1)),
        body,
    )


# Strip absolute paths the DH should never embed.  Matches typical
# Docker / Linux paths under /app/... and the timestamped attempt
# folder slugs that show up bare in some agent replies.
_ABS_PATH_RE = re.compile(
    r"(?:/app/)[\w./\\\-]+",
)
_ATTEMPT_SLUG_RE = re.compile(
    r"\b\d{8}_\d{6}_\d{3}_[\w\-]+\b",
)

# Common chain-narration leads.  Removed line-wise.
_CHAIN_NARRATION_RES = [
    re.compile(r"^\s*I(?:'ll| will) (?:send|forward|hand[\s\-]?off|relay).*$",
               re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*Handing (?:this )?off to.*$",
               re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*Forwarding to (?:the )?[A-Z][\w ]+.*$",
               re.MULTILINE),
]


# ---------------------------------------------------------------------------
# Attempt identification (parse Q(N)'s raw answer for an attempt id)
# ---------------------------------------------------------------------------
#
# When the user marks a Q(N) row as "attempt"-scoped, the system needs
# to bind every Q(N).x child to the SAME attempt the parent's reply
# named.  ``_extract_attempt_id`` tries (in order):
#
#   1. A full attempt-folder slug          (e.g. 20260529_091434_001_...)
#   2. An "attempt NNN" / "attempt #NNN"   (zero-padded integer)
#   3. An ordinal ("first / second / ..." up to tenth, mapped to 001..010)
#
# Returns ``None`` when no candidate is found — the caller then re-asks
# Q(N) once with an explicit instruction to name the attempt; if that
# also fails, the children are skipped with an empty-placeholder write.
# ---------------------------------------------------------------------------

_ATTEMPT_SLUG_FULL_RE = re.compile(
    r"\b(\d{8}_\d{6}_\d{3}_[\w\-]+)\b",
)
_ATTEMPT_NUMBER_RE = re.compile(
    r"\battempt\s*#?\s*(\d{1,4})\b",
    re.IGNORECASE,
)
_ORDINAL_TO_NUM: dict[str, int] = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}
_ATTEMPT_ORDINAL_RE = re.compile(
    r"\b(" + "|".join(_ORDINAL_TO_NUM) + r")\s+(?:attempt|iteration)\b",
    re.IGNORECASE,
)


def _extract_attempt_id(raw_text: str) -> str | None:
    """Return a textual attempt identifier from *raw_text*, or ``None``.

    The returned string is suitable for embedding into a follow-up
    question's framing — either a full slug, ``attempt NNN`` (zero-
    padded to 3 digits when possible), or ``None`` when nothing
    matched.
    """
    if not raw_text:
        return None
    m = _ATTEMPT_SLUG_FULL_RE.search(raw_text)
    if m:
        return m.group(1)
    m = _ATTEMPT_NUMBER_RE.search(raw_text)
    if m:
        return f"attempt {int(m.group(1)):03d}"
    m = _ATTEMPT_ORDINAL_RE.search(raw_text)
    if m:
        idx = _ORDINAL_TO_NUM.get(m.group(1).lower())
        if idx is not None:
            return f"attempt {idx:03d}"
    return None


# Used by the force-tool path's input validator.  Accepts:
#   * "002" / "2" / "  3  "
#   * "attempt 002" / "attempt #2"
#   * a full slug like "20260530_142312_002_descriptor"
# Returns the zero-padded 3-digit number, or ``None`` when the input
# looks like none of the above.
_BARE_NUMBER_RE = re.compile(r"^\s*#?\s*(\d{1,4})\s*$")


def _normalise_attempt_input(raw: str) -> str | None:
    """Pick the 3-digit attempt number out of *raw*.

    Returns ``"NNN"`` (zero-padded) or ``None`` when nothing matched.
    The literal string ``"none"`` (case-insensitive) is a separate
    sentinel handled by the caller — this helper does NOT recognise
    it (so a number is unambiguously distinguishable from "no
    attempt").
    """
    if not raw:
        return None
    s = raw.strip()
    m = _BARE_NUMBER_RE.match(s)
    if m:
        return f"{int(m.group(1)):03d}"
    m = _ATTEMPT_NUMBER_RE.search(s)
    if m:
        return f"{int(m.group(1)):03d}"
    m = _ATTEMPT_SLUG_FULL_RE.search(s)
    if m:
        slug = m.group(1)
        # The slug has the shape YYYYMMDD_HHMMSS_NNN_descriptor; the
        # 3-digit segment is the 3rd underscore-delimited field.
        parts = slug.split("_")
        if len(parts) >= 3 and parts[2].isdigit():
            return f"{int(parts[2]):03d}"
    m = _ATTEMPT_ORDINAL_RE.search(s)
    if m:
        idx = _ORDINAL_TO_NUM.get(m.group(1).lower())
        if idx is not None:
            return f"{idx:03d}"
    return None


def _resolve_attempt_folder(
    attempt_number_nnn: str,
    attempts_root: Path,
    session_start_ts: float | None,
) -> tuple[Path | None, str]:
    """Locate the local attempt folder matching ``attempt_number_nnn``.

    *attempt_number_nnn* is the zero-padded 3-digit string returned by
    :func:`_normalise_attempt_input`.  *session_start_ts* (epoch
    seconds) is used to filter cross-session matches when the same
    NNN exists in earlier session folders that the End-Session sweep
    hasn't archived yet.

    Returns ``(folder, status)`` where ``status`` is one of:
        ``"ok"``           — exactly one match found, returned in folder
        ``"none-match"``   — zero folders match this NNN
        ``"multi-match"``  — more than one folder matches; the most
                              recent (by mtime) is returned, and the
                              caller may log a warning
    """
    if not attempts_root.exists() or not attempts_root.is_dir():
        return None, "none-match"
    pattern = f"*_{attempt_number_nnn}_*"
    candidates = sorted(
        (p for p in attempts_root.glob(pattern) if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,  # most-recent first
    )
    if session_start_ts is not None:
        candidates = [
            p for p in candidates
            if p.stat().st_mtime >= session_start_ts - 1.0  # 1s slack
        ]
    if not candidates:
        return None, "none-match"
    if len(candidates) == 1:
        return candidates[0], "ok"
    return candidates[0], "multi-match"


def _clean_semantic_body(body: str) -> str:
    """Apply the defensive cleanup rules to a SEMANTIC body.

    These rules MIRROR the strip-list in the DH prompt — when the DH
    obeys, they are no-ops; when the DH slips, they catch the most
    common leaks (routing-tool JSON, literal ``\\n`` escapes, ``/app/``
    paths, attempt-folder slugs, mid-chain narration).
    """
    if not body:
        return body

    # 1. Unwrap routing-tool JSON if the whole body is one.
    body = _unwrap_routing_tool_json(body)

    # 2. Unescape literal \n / \t / \" 2-character sequences left
    #    over from JSON-stringified content.  Done as a targeted
    #    replace (NOT json.loads on the whole body) so we don't break
    #    real backslashes in prose.
    body = body.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')

    # 3. Strip absolute paths and attempt-folder slugs.
    body = _ABS_PATH_RE.sub("", body)
    body = _ATTEMPT_SLUG_RE.sub("", body)

    # 4. Drop chain-narration lines wholesale.
    for pat in _CHAIN_NARRATION_RES:
        body = pat.sub("", body)

    # 5. Collapse the whitespace left behind by the substitutions —
    #    runs of blank lines and trailing spaces.
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


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

        # Light up the Database Handler box in the LOG-and-Status
        # flowchart for the duration of the interview.  ``trace`` writes
        # the line to the agent-flow file AND publishes an ``agent_
        # active`` event on the viz bus the web UI listens to.  Failures
        # to publish must not break the DH run (a tracefile error here
        # would otherwise abort the save).
        try:
            from agents.shared.trace import trace as _viz_trace
            _viz_trace("User", "Database Handler",
                       note="DH save started")
        except Exception:
            _viz_trace = None  # noqa: F841 — we'll still try later

        try:
            logger.info(
                f"[DH]  populate_database start; session_dir={session_dir.resolve()}; "
                f"dc_inspector_enabled={dc_inspector_enabled}; "
                f"max_response_tokens={self.max_response_tokens}; "
                f"embedding={workflow_settings.EMBEDDING_PROVIDER}/"
                f"{workflow_settings.EMBEDDING_MODEL}@"
                f"{workflow_settings.EMBEDDING_VECTOR_DIMS}d"
            )

            # Load the schedule the developer set via the "Questions
            # for Saved Sessions" web view.  Falls back to the
            # hardcoded SCHEDULE when the file is missing / malformed
            # so existing deployments without a dh_schedule.json keep
            # working.
            try:
                from workflow_settings import dh_schedule as _dh_schedule
                schedule_entries = _dh_schedule.read_for_dh()
                if not schedule_entries:
                    raise RuntimeError("empty schedule")
                logger.info(
                    f"[DH]  loaded {len(schedule_entries)} schedule "
                    f"entries from dh_schedule.json"
                )
            except Exception as exc:
                logger.warning(
                    f"[DH]  dh_schedule.json unavailable ({exc}); "
                    f"falling back to the hardcoded SCHEDULE."
                )
                schedule_entries = [
                    {
                        "id":          f"hardcoded_{i}",
                        "agent_key":   e["agent_key"],
                        "field":       e["field"],
                        "description": e.get("description", ""),
                        "type":        e.get("type", "Semantic"),
                        "scope":       "session",
                        "parent_id":   None,
                        "sub_index":   None,
                        "to_agents":   [],
                        "requires_dcii_enabled": bool(
                            e.get("requires_dcii_enabled", False)
                        ),
                    }
                    for i, e in enumerate(SCHEDULE)
                ]

            # Maps an identifying Q(N)'s ``id`` to the LIST of textual
            # attempt identifiers the force-tool resolved.  An empty
            # list means the parent ran but no identifier could be
            # bound (explicit "none" or 3-retry exhaustion) — children
            # of that parent are silently skipped (no .txt, no
            # placeholder).  Multi-attempt parents land here with
            # ``len(value) >= 2``.
            attempt_ids_by_parent: dict[str, list[str]] = {}

            # Session-id slug embedded in every saved .txt and used
            # as the per-session prefix for the R2 mirror.  Same value
            # the archive sweep uses under previous_sessions/.
            session_id = session_dir.name

            # Epoch seconds at the START of the live session.  Used
            # by the force-tool path's attempt-folder resolver to
            # filter out attempt folders left behind by earlier (un-
            # archived) sessions whose folder names happen to share
            # the same 3-digit NNN.  Session.session_ts is recorded
            # at session-build time, so any attempt generated during
            # this session has mtime >= session_start_ts.
            try:
                session_start_ts = self.session.session_ts.timestamp()
            except Exception:
                session_start_ts = None  # disables filtering

            written = 0
            n_entries = len(schedule_entries)
            i = 0
            while i < n_entries:
                entry = schedule_entries[i]
                # Publish the field's short label so the flowchart's
                # caption under the DH box updates to the question
                # currently being asked.
                try:
                    from agents.shared.viz_bus import publish as _viz_publish
                    _viz_publish({
                        "type": "generic_tool",
                        "name": _short_label_for(entry),
                        "state": "start",
                    })
                except Exception:
                    pass
                agent_key = entry["agent_key"]
                field = entry["field"]
                parent_id = entry.get("parent_id")
                scope = entry.get("scope", "session")

                # DCII gating.  When the DCII is disabled this session
                # we still create the agent folder and write an EMPTY
                # placeholder file, so the per-session folder layout
                # stays uniform across runs regardless of the toggle.
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
                        self._write_sidecar_meta(
                            path, entry=entry, attempt_id=None,
                        )
                        written += 1
                    except OSError as exc:
                        logger.warning(
                            f"[DH]  failed to write empty placeholder "
                            f"for {agent_key}/{field}: {exc}"
                        )
                    i += 1
                    continue

                # Sub-rows reached at the main level mean they survived
                # the inner attempt-major loop OR their parent failed.
                # Either way, drop them silently — the parent's block
                # is the single point of authority for sub-row writes
                # (whether N=1 or N>=2 attempts).
                if parent_id is not None:
                    logger.info(
                        f"[DH]  sub-row '{field}' reached the main "
                        f"loop without being handled by its parent's "
                        f"block (parent_id={parent_id!r}); skipping."
                    )
                    i += 1
                    continue

                agent = orchestrator._agents_by_key.get(agent_key)
                agent_state = self.session.agent_states.get(agent_key)
                if agent is None or agent_state is None:
                    logger.warning(
                        f"[DH]  unknown agent '{agent_key}' in schedule; "
                        f"skipped"
                    )
                    err_path = self._write_error_entry(
                        session_dir=session_dir,
                        agent_key=agent_key,
                        field=field,
                        error_message=(
                            f"agent key '{agent_key}' is not present in "
                            f"the orchestrator's registry / session.agent_"
                            f"states; the DH could not interview it."
                        ),
                        session_id=session_id,
                        attempt_id=None,
                    )
                    self._write_sidecar_meta(
                        err_path, entry=entry, attempt_id=None,
                    )
                    i += 1
                    continue

                is_identifying_attempt_q = (
                    scope == "attempt" and parent_id is None
                )
                effective_description = entry.get("description", "")

                logger.info(
                    f"[DH]  starting conversation with {agent_key} "
                    f"(field='{field}', type={entry.get('type', 'Semantic')}, "
                    f"scope={scope}, identifying={is_identifying_attempt_q})"
                )

                # ----- IDENTIFYING ATTEMPT-SPECIFIC ROW --------------
                if is_identifying_attempt_q:
                    try:
                        triples, raw_answer, resolved_attempt_ids = (
                            self._run_identifying_conversation(
                                agent_key=agent_key,
                                agent_system_prompt=getattr(agent, "system_prompt", "") or "",
                                agent_provider=getattr(agent, "provider", self.provider),
                                agent_base_llm=getattr(agent, "base_llm", None) or agent.llm,
                                agent_messages=list(agent_state.messages),
                                field=field,
                                description=effective_description,
                                field_type=entry.get("type", "Semantic"),
                                session_id=session_id,
                                session_start_ts=session_start_ts,
                            )
                        )
                    except Exception as exc:  # pragma: no cover
                        logger.warning(
                            f"[DH]  identifying conversation with "
                            f"{agent_key}/{field} raised "
                            f"{type(exc).__name__}: {exc}; treating as "
                            f"'no attempts' (cascade drop)."
                        )
                        triples, resolved_attempt_ids = [], []

                    attempt_ids_by_parent[entry["id"]] = list(resolved_attempt_ids)

                    # Locate the contiguous block of sub-rows whose
                    # parent_id matches this row's id.  The sub-rows
                    # come right after the parent in the schedule
                    # order (the validation in dh_schedule enforces
                    # contiguity).
                    sub_rows: list[dict] = []
                    j = i + 1
                    while j < n_entries and schedule_entries[j].get("parent_id") == entry["id"]:
                        sub_rows.append(schedule_entries[j])
                        j += 1

                    if not resolved_attempt_ids:
                        logger.warning(
                            f"[DH]  identifying Q '{field}' resolved "
                            f"NO attempts; DROPPING this row's .txt "
                            f"AND every Q(N).x sub-row "
                            f"({len(sub_rows)} children) entirely."
                        )
                        i = j
                        continue

                    n_attempts = len(resolved_attempt_ids)
                    # Write the identifying Q's .txt file(s).
                    if n_attempts == 1:
                        # Single attempt: one .txt for the row.
                        # Multi-answer split is allowed (rare for
                        # identifying Qs, but possible).
                        only_attempt = resolved_attempt_ids[0]
                        for idx, (_attempt_tag, q, a) in enumerate(triples):
                            item_index = (
                                idx + 1 if len(triples) > 1 else None
                            )
                            try:
                                path = self._write_entry(
                                    session_dir=session_dir,
                                    agent_key=agent_key,
                                    field=field,
                                    question=q,
                                    answer=a,
                                    session_id=session_id,
                                    attempt_id=only_attempt,
                                    attempt_suffix=None,
                                    item_index=item_index,
                                )
                                self._write_sidecar_meta(
                                    path, entry=entry,
                                    attempt_id=only_attempt,
                                )
                                logger.info(
                                    f"[DH]  wrote identifying-Q {path}"
                                )
                                written += 1
                            except OSError as exc:
                                logger.warning(
                                    f"[DH]  failed to write identifying-Q "
                                    f"item {idx} for {agent_key}: {exc}"
                                )
                    else:
                        # Multi-attempt: one .txt per resolved
                        # attempt.  Each pair in ``triples`` should
                        # carry an ATTEMPT tag the parser recovered
                        # from the SAVE body; we honour that order
                        # but cross-check against the resolved list.
                        by_attempt: dict[str, tuple[str, str]] = {}
                        for (attempt_tag, q, a) in triples:
                            norm = (
                                _normalise_attempt_input(attempt_tag)
                                if attempt_tag else None
                            )
                            if norm and norm not in by_attempt:
                                by_attempt[norm] = (q, a)
                        for attempt_str in resolved_attempt_ids:
                            norm = _normalise_attempt_input(attempt_str)
                            if not norm:
                                continue
                            q_a = by_attempt.get(norm)
                            if q_a is None and triples:
                                # DH didn't tag a pair for this attempt
                                # — fall back to the first untagged
                                # pair (best effort).
                                _t, fq, fa = triples[0]
                                q_a = (fq, fa)
                                logger.warning(
                                    f"[DH]  identifying multi-attempt "
                                    f"SAVE missing ATTEMPT: {norm}; "
                                    f"reusing first pair as fallback."
                                )
                            if q_a is None:
                                continue
                            q, a = q_a
                            try:
                                path = self._write_entry(
                                    session_dir=session_dir,
                                    agent_key=agent_key,
                                    field=field,
                                    question=q,
                                    answer=a,
                                    session_id=session_id,
                                    attempt_id=attempt_str,
                                    attempt_suffix=norm,
                                    item_index=None,
                                )
                                self._write_sidecar_meta(
                                    path, entry=entry,
                                    attempt_id=attempt_str,
                                )
                                logger.info(
                                    f"[DH]  wrote identifying-Q "
                                    f"{path.name} (attempt {norm})"
                                )
                                written += 1
                            except OSError as exc:
                                logger.warning(
                                    f"[DH]  failed to write identifying-Q "
                                    f"for attempt {norm}: {exc}"
                                )

                    # ATTEMPT-MAJOR sub-row loop.  For each resolved
                    # attempt, run every sub-row's interview about THAT
                    # specific attempt, in schedule order.  Per the v9
                    # spec, all sub-rows for attempt 1 complete before
                    # attempt 2's begin.
                    for attempt_str in resolved_attempt_ids:
                        norm = _normalise_attempt_input(attempt_str)
                        if not norm:
                            continue
                        for sub_entry in sub_rows:
                            sub_agent_key = sub_entry["agent_key"]
                            sub_field = sub_entry["field"]
                            sub_agent = orchestrator._agents_by_key.get(sub_agent_key)
                            sub_state = self.session.agent_states.get(sub_agent_key)
                            if sub_agent is None or sub_state is None:
                                logger.warning(
                                    f"[DH]  sub-row agent "
                                    f"{sub_agent_key!r} not in registry; "
                                    f"skipping for attempt {norm}."
                                )
                                continue
                            sub_desc = (
                                f"For {attempt_str}: "
                                f"{sub_entry.get('description', '')}"
                            )
                            try:
                                sub_triples, _sub_raw = (
                                    self._run_one_conversation(
                                        agent_key=sub_agent_key,
                                        agent_system_prompt=getattr(sub_agent, "system_prompt", "") or "",
                                        agent_provider=getattr(sub_agent, "provider", self.provider),
                                        agent_base_llm=getattr(sub_agent, "base_llm", None) or sub_agent.llm,
                                        agent_messages=list(sub_state.messages),
                                        field=sub_field,
                                        description=sub_desc,
                                        field_type=sub_entry.get("type", "Semantic"),
                                    )
                                )
                            except Exception as exc:  # pragma: no cover
                                logger.warning(
                                    f"[DH]  sub-row conversation for "
                                    f"{sub_agent_key}/{sub_field} "
                                    f"(attempt {norm}) raised "
                                    f"{type(exc).__name__}: {exc}; "
                                    f"skipping."
                                )
                                continue

                            # Multi-attempt → always use the __NNN
                            # suffix on sub-row files so they don't
                            # collide across attempts.
                            attempt_suffix = norm if n_attempts >= 2 else None
                            for idx, (_t, sq, sa) in enumerate(sub_triples):
                                item_index = (
                                    idx + 1 if len(sub_triples) > 1 else None
                                )
                                try:
                                    spath = self._write_entry(
                                        session_dir=session_dir,
                                        agent_key=sub_agent_key,
                                        field=sub_field,
                                        question=sq,
                                        answer=sa,
                                        session_id=session_id,
                                        attempt_id=attempt_str,
                                        attempt_suffix=attempt_suffix,
                                        item_index=item_index,
                                    )
                                    self._write_sidecar_meta(
                                        spath, entry=sub_entry,
                                        attempt_id=attempt_str,
                                    )
                                    logger.info(
                                        f"[DH]  wrote sub-row {spath.name} "
                                        f"(attempt {norm})"
                                    )
                                    written += 1
                                except OSError as exc:
                                    logger.warning(
                                        f"[DH]  failed to write sub-row "
                                        f"for {sub_agent_key}/{sub_field} "
                                        f"(attempt {norm}): {exc}"
                                    )

                    i = j  # skip past the sub-rows the inner loop just handled
                    continue

                # ----- SESSION-SCOPED ROW (or QUANT) -----------------
                try:
                    triples, raw_answer = self._run_one_conversation(
                        agent_key=agent_key,
                        agent_system_prompt=getattr(agent, "system_prompt", "") or "",
                        agent_provider=getattr(agent, "provider", self.provider),
                        agent_base_llm=getattr(agent, "base_llm", None) or agent.llm,
                        agent_messages=list(agent_state.messages),
                        field=field,
                        description=effective_description,
                        field_type=entry.get("type", "Semantic"),
                    )
                except Exception as exc:  # pragma: no cover — defensive
                    logger.warning(
                        f"[DH]  conversation with {agent_key} failed: {exc}"
                    )
                    err_path = self._write_error_entry(
                        session_dir=session_dir,
                        agent_key=agent_key,
                        field=field,
                        error_message=(
                            f"the DH conversation with {agent_key} "
                            f"raised an exception: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                        session_id=session_id,
                        attempt_id=None,
                    )
                    self._write_sidecar_meta(
                        err_path, entry=entry, attempt_id=None,
                    )
                    i += 1
                    continue

                for idx, (_t, q, a) in enumerate(triples):
                    item_index = idx + 1 if len(triples) > 1 else None
                    try:
                        path = self._write_entry(
                            session_dir=session_dir,
                            agent_key=agent_key,
                            field=field,
                            question=q,
                            answer=a,
                            session_id=session_id,
                            attempt_id=None,
                            attempt_suffix=None,
                            item_index=item_index,
                        )
                        self._write_sidecar_meta(
                            path, entry=entry, attempt_id=None,
                        )
                        logger.info(
                            f"[DH]  wrote {path.name}"
                            + (f" (item {item_index}/{len(triples)})"
                               if item_index else "")
                        )
                        written += 1
                    except OSError as exc:
                        logger.warning(
                            f"[DH]  failed to write entry for "
                            f"{agent_key}: {exc}"
                        )
                i += 1

            logger.info(
                f"[DH]  populate_database end; entries written={written}"
            )

            # Snapshot the user's text inputs + reference images +
            # image descriptions into the database tree, so the R2
            # mirror below picks them up alongside the per-agent
            # .txt files.  Best-effort: a copy failure logs a
            # warning but does NOT break the rest of the save.
            try:
                n_inputs = self._collect_user_inputs(session_dir)
                logger.info(
                    f"[DH]  collected {n_inputs} user-input file(s) "
                    f"into {session_dir / 'user_inputs'}"
                )
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning(
                    f"[DH]  user-input collection raised "
                    f"({type(exc).__name__}: {exc}); save kept locally."
                )

            # Mirror the local session_dir to Cloudflare R2 when
            # configured.  Suffix whitelist covers both the DH's .txt
            # bodies AND the user-input PNG/JPG images collected just
            # above.  Best-effort: a failure here logs a warning but
            # never breaks the local save the user just confirmed.
            try:
                from agents.shared import r2_uploader as _r2
                if _r2.is_enabled():
                    n_up = _r2.upload_directory(
                        session_dir,
                        remote_prefix=f"{session_id}/",
                        suffixes=(".txt", ".png", ".jpg", ".jpeg"),
                    )
                    logger.info(
                        f"[DH]  R2 mirror complete: {n_up} file(s) "
                        f"uploaded under prefix {session_id}/"
                    )
                else:
                    logger.info(
                        f"[DH]  R2 not configured; skipped mirror of "
                        f"{session_dir.resolve()} "
                        f"(set R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / "
                        f"R2_SECRET_ACCESS_KEY / R2_BUCKET_NAME to enable)."
                    )
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning(
                    f"[DH]  R2 mirror raised "
                    f"({type(exc).__name__}: {exc}); save kept locally."
                )

            return written
        finally:
            # Always emit the clearing handoff so the LOG-and-Status
            # chart stops highlighting the DH box, regardless of
            # whether the interview finished cleanly or threw.
            try:
                from agents.shared.trace import trace as _viz_trace_end
                _viz_trace_end("Database Handler", "User",
                               note="DH save done")
            except Exception:
                pass
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
    ) -> tuple[list[tuple[str | None, str, str]], str]:
        """Run one DH-driven conversation about *field* with the named agent.

        Returns ``(triples, raw_last_answer)`` where ``triples`` is a
        list of ``(attempt_id, question, answer)`` items in DH-emitted
        order.  For non-identifying conversations the attempt_id slot
        is ``None``; the multi-attempt SAVE format only fires from
        :meth:`_run_identifying_conversation`.  Multi-answer split
        (Extension A) is supported here: when the DH emits N
        QUESTION:/ANSWER: pairs, all N show up in the returned list.

        Loop:
          1. DH formulates an initial question and the system delivers
             it to Agent A.
          2. Agent A replies.
          3. DH emits ``ASK: ...`` (loop) or ``SAVE: ...`` (terminate).
          4. For SEMANTIC fields, EACH pair is checked against the
             per-pair token cap; pairs over cap get a one-shot retry.

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

        if is_semantic:
            # SEMANTIC SAVE shape (v9.1+): one or more QUESTION:/
            # ANSWER: pairs back-to-back (multi-answer split is
            # allowed when the agent's reply covers N distinct
            # items).  Defensive: when no pairs parse, fall back to
            # a single pair built from the asked question + the
            # whole body.
            triples = _parse_save_body_semantic(final_body)
            if not triples:
                logger.warning(
                    f"[DH]  SAVE body for {agent_key}/{field} did not "
                    f"contain QUESTION:/ANSWER: headers; using asked "
                    f"question + whole body as a single-pair fallback."
                )
                triples = [(None, first_question, final_body)]

            # Safety-net cleanup BEFORE the cap check so the cap
            # measures what will actually be written.  Strip the
            # ATTEMPT tag here — non-identifying conversations don't
            # honour it, but a stray one in the prose shouldn't break
            # the embedding either.
            cleaned: list[tuple[str | None, str, str]] = []
            for (_attempt, q, a) in triples:
                cq = _clean_semantic_body(q) or q
                ca = _clean_semantic_body(a) or a
                cleaned.append((None, cq, ca))

            cleaned = self._enforce_semantic_cap_pairs(
                agent_key=agent_key,
                field=field,
                description=description,
                triples=cleaned,
            )
            # Return shape: (triples, raw_last_answer).  The raw last
            # answer is preserved so any future extension that needs
            # the un-cleaned reply (none today; identifying-Q used to)
            # can still reach it.
            return cleaned, last_answer

        # QUANTITATIVE — single-body path.  Wrap as a one-element
        # list of triples with attempt_id=None so the caller has a
        # uniform interface.
        return [(None, first_question, final_body)], last_answer

    # Mechanical tail clause appended to every DH question sent to an
    # agent.  Reduces the cleanup burden by asking the agent up-front
    # NOT to surface artefacts the DH would otherwise have to strip.
    # Independent of the DH's own wording so it cannot be "forgotten":
    # Option 1 in the user's design notes, layered on top of Option 2
    # (the SEMANTIC safety net in _clean_semantic_body).
    _AGENT_FACING_TAIL = (
        "\n\n[Reminder for your reply, from the Database Handler:\n"
        "Do not include file paths, directory names, or absolute "
        "paths of any kind (no /app/... paths, no render PNG paths, "
        "no parameters.json references, no attempt-folder slugs).  "
        "Do not enumerate the 17 design parameters as a value list — "
        "instead, describe the REASONING you applied (which checks, "
        "which heuristics, which trade-offs).  Do not address any "
        "other agent or the user; the chain is over and your reply "
        "is consumed only by me.]"
    )

    # ------------------------------------------------------------------
    # Force-tool variant for IDENTIFYING attempt-specific questions
    # ------------------------------------------------------------------
    #
    # Identifying attempt-specific rows are top-level rows with
    # ``scope="attempt"`` and ``parent_id=None``.  They pin down WHICH
    # design attempt this block of questions is about.  The DH is
    # forced to call ``save_attempt_artefacts`` after Agent A's first
    # reply; the tool's argument is either the attempt number Agent A
    # named (e.g. ``"002"``, ``"attempt 002"``, a full slug) or the
    # literal string ``"none"`` when no attempt could be identified.
    #
    # Up to ``_MAX_FORCE_TOOL_RETRIES`` retries; after that, the
    # system synthesises a ``None`` outcome and drops the whole
    # block (this row's .txt + every Q(N).x sub-row).
    # ------------------------------------------------------------------

    _MAX_FORCE_TOOL_RETRIES = 3

    def _run_identifying_conversation(
        self,
        agent_key: str,
        agent_system_prompt: str,
        agent_provider: str,
        agent_base_llm,
        agent_messages: list,
        field: str,
        description: str,
        field_type: str,
        session_id: str,
        session_start_ts: float | None,
    ) -> tuple[
        list[tuple[str | None, str, str]],
        str,
        list[str],
    ]:
        """Identifying attempt-specific variant of :meth:`_run_one_conversation`.

        Returns ``(triples, raw_last_answer, resolved_attempt_ids)``.

        * ``resolved_attempt_ids`` — list of ``"attempt NNN"`` strings
          the force-tool resolved (may have multiple entries for the
          multi-attempt case; empty list on explicit-none / max-retries).
        * ``triples`` — for SEMANTIC: list of ``(attempt_id, Q, A)``
          pairs the DH emitted in SAVE: (multi-attempt → one per
          attempt with ATTEMPT: tag; single-attempt → may still be
          multi-pair if the DH split the answer).  Empty when the
          force-tool returned no attempts (cascade drop).
        * ``raw_last_answer`` — Agent A's final un-cleaned reply, kept
          for any future extension that needs it.
        """
        convo_buffer: list = list(agent_messages)
        is_semantic = (field_type or "Semantic").strip().lower() == "semantic"

        # Step 1 — DH formulates the question.
        first_question = self._formulate_question(
            agent_key=agent_key,
            field=field,
            description=description,
            field_type=field_type,
        )
        logger.info(
            f"[DH]  identifying-Q initial question for {agent_key}/{field}\n"
            f"{_format_block('DH -> ' + agent_key + ':', first_question)}"
        )

        # Step 2 — Agent A's first reply.
        first_answer = self._ask_agent(
            agent_key=agent_key,
            agent_system_prompt=agent_system_prompt,
            agent_provider=agent_provider,
            agent_base_llm=agent_base_llm,
            convo_buffer=convo_buffer,
            field=field,
            question=first_question,
        )
        self.messages.append(
            HumanMessage(
                content=(
                    f"Agent: {agent_key}\nField: {field}\n"
                    f"Field type: {field_type} (IDENTIFYING attempt-specific)\n"
                    f"My question to {agent_key}: {first_question}\n"
                    f"{agent_key}'s reply: {first_answer}"
                )
            )
        )

        # Step 3 — FORCE-TOOL PHASE.  Returns a LIST of resolved ids
        # (or an empty list on explicit-none / max-retries).
        resolved_attempt_ids, reason = self._run_force_tool_phase(
            agent_key=agent_key,
            field=field,
            agent_last_answer=first_answer,
            session_id=session_id,
            session_start_ts=session_start_ts,
        )
        if not resolved_attempt_ids:
            logger.info(
                f"[DH]  force-tool resolved 'no attempts' for "
                f"{agent_key}/{field} (reason={reason}); the whole "
                f"block will be dropped."
            )
            return [], first_answer, []

        # Step 4 — DH decide loop (ASK/SAVE).  The ToolMessages from
        # the force-tool phase are already in self.messages, so the
        # DH's SAVE: body naturally references the resolved attempts.
        last_question = first_question
        last_answer = first_answer
        final_body: str | None = None
        for round_idx in range(MAX_DH_TURNS_PER_FIELD):
            decision_kind, decision_payload = self._decide_next(
                agent_key=agent_key,
                field=field,
                field_type=field_type,
                description=description,
                last_question=last_question,
                last_answer=last_answer,
                round_idx=round_idx,
            )
            if decision_kind == "SAVE":
                final_body = decision_payload
                break
            if decision_kind == "ASK":
                last_question = decision_payload
                last_answer = self._ask_agent(
                    agent_key=agent_key,
                    agent_system_prompt=agent_system_prompt,
                    agent_provider=agent_provider,
                    agent_base_llm=agent_base_llm,
                    convo_buffer=convo_buffer,
                    field=field,
                    question=last_question,
                )
                self.messages.append(
                    HumanMessage(
                        content=(
                            f"Agent: {agent_key}\nField: {field}\n"
                            f"My follow-up to {agent_key}: {last_question}\n"
                            f"{agent_key}'s reply: {last_answer}"
                        )
                    )
                )
                continue
            logger.warning(
                f"[DH]  protocol error from DH for {agent_key}/{field} "
                f"after force-tool; falling back to last agent answer."
            )
            final_body = last_answer
            break

        if final_body is None:
            final_body = last_answer
        if not (final_body or "").strip():
            final_body = "(no usable content was produced for this field this session)"

        if is_semantic:
            triples = _parse_save_body_semantic(final_body)
            if not triples:
                logger.warning(
                    f"[DH]  identifying SAVE body for {agent_key}/{field} "
                    f"did not contain QUESTION:/ANSWER: headers; using "
                    f"asked question + whole body as single-pair fallback."
                )
                triples = [(None, first_question, final_body)]

            cleaned: list[tuple[str | None, str, str]] = []
            for (attempt_tag, q, a) in triples:
                cq = _clean_semantic_body(q) or q
                ca = _clean_semantic_body(a) or a
                cleaned.append((attempt_tag, cq, ca))

            cleaned = self._enforce_semantic_cap_pairs(
                agent_key=agent_key,
                field=field,
                description=description,
                triples=cleaned,
            )
            return cleaned, last_answer, resolved_attempt_ids

        # QUANTITATIVE identifying Q (uncommon; type is usually Semantic
        # for identifying questions, but we handle it cleanly anyway):
        # one pair, no attempt tag.
        return [(None, first_question, final_body)], last_answer, resolved_attempt_ids

    def _run_force_tool_phase(
        self,
        *,
        agent_key: str,
        field: str,
        agent_last_answer: str,
        session_id: str,
        session_start_ts: float | None,
    ) -> tuple[list[str], str]:
        """Force the DH to call save_attempt_artefacts; up to 3 retries.

        Returns ``(resolved_attempt_ids, reason)`` where
        ``resolved_attempt_ids`` is the list of normalised
        identifiers (each in ``"attempt NNN"`` form) the DH passed —
        possibly empty when the DH explicitly chose "no attempt".
        ``reason`` is one of ``"ok"`` / ``"explicit-none"`` /
        ``"max-retries"`` / ``"bind-failed"``.

        On a successful resolve for N>=1 attempts, every resolved
        folder's artefacts are uploaded to R2 BEFORE the ToolMessage
        is returned, so the DH's next turn sees the uploaded state in
        its conversation context.
        """
        import json as _json
        from agents.database_handler.dh_tools import (
            save_attempt_artefacts,
            SAVE_ATTEMPT_ARTEFACTS_TOOL_NAME,
        )

        try:
            dh_with_tool = self.llm.bind_tools(
                [save_attempt_artefacts],
                tool_choice=SAVE_ATTEMPT_ARTEFACTS_TOOL_NAME,
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                f"[DH]  could not bind save_attempt_artefacts to the "
                f"DH LLM: {type(exc).__name__}: {exc}; treating as "
                f"empty list."
            )
            return [], "bind-failed"

        attempts_root = ATTEMPTS_DIR

        instruction = HumanMessage(
            content=(
                "FORCE-TOOL TURN.\n\n"
                f"Field: {field} (identifying attempt-specific)\n"
                f"Agent: {agent_key}\n\n"
                f"{agent_key}'s last reply:\n{agent_last_answer}\n\n"
                "You MUST now call `save_attempt_artefacts` exactly "
                "ONCE.  Pass a JSON list of attempt identifiers:\n"
                "  * One element per attempt the agent identified — "
                "each element is a number/slug/ordinal (e.g. \"002\", "
                "\"attempt 002\", or a full slug).  Examples:\n"
                "      attempt_ids=[\"002\"]            (single attempt)\n"
                "      attempt_ids=[\"002\", \"005\"]   (two attempts)\n"
                "  * An empty list [] OR a list containing \"none\" "
                f"when {agent_key} did NOT identify any specific "
                "attempt.\n\n"
                "Do not emit ASK: or SAVE: this turn — the system is "
                "forcing the tool call and will give you up to "
                f"{self._MAX_FORCE_TOOL_RETRIES} attempts to land a "
                "valid call before defaulting to no attempt."
            )
        )
        self.messages.append(instruction)

        for attempt in range(1, self._MAX_FORCE_TOOL_RETRIES + 1):
            try:
                response = invoke_with_retry(
                    dh_with_tool,
                    [make_system_message(self.system_prompt, self.provider)]
                    + self.messages,
                    f"DH-force-tool-{attempt}",
                )
            except Exception as exc:
                logger.warning(
                    f"[DH]  force-tool attempt {attempt} LLM call "
                    f"raised {type(exc).__name__}: {exc}; treating as "
                    f"invalid and continuing."
                )
                continue
            self.messages.append(response)

            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                self.messages.append(
                    HumanMessage(
                        content=(
                            f"You did not emit a tool call.  Attempt "
                            f"{attempt} of {self._MAX_FORCE_TOOL_RETRIES}. "
                            "Call save_attempt_artefacts now."
                        )
                    )
                )
                logger.warning(
                    f"[DH]  force-tool attempt {attempt}: no tool_calls "
                    f"in DH response; reprompting."
                )
                continue

            tc = tool_calls[0]
            tool_call_id = (
                tc.get("id") if isinstance(tc, dict)
                else getattr(tc, "id", None)
            ) or ""
            args = (
                tc.get("args") if isinstance(tc, dict)
                else getattr(tc, "args", None)
            ) or {}
            raw_ids: list[str] = []
            if isinstance(args, dict):
                # New API: attempt_ids: list[str].  Tolerate single-
                # element scalars as well (some providers' JSON-mode
                # tool-call binding occasionally coerces a 1-element
                # list to a string).
                raw = args.get("attempt_ids")
                if isinstance(raw, list):
                    raw_ids = [str(x).strip() for x in raw if str(x).strip()]
                elif isinstance(raw, str) and raw.strip():
                    raw_ids = [raw.strip()]

            # Treat empty / all-"none" lists as the explicit-no-attempt
            # path.
            non_none_ids = [
                s for s in raw_ids if s.lower() != "none"
            ]
            if not non_none_ids:
                self.messages.append(ToolMessage(
                    content=_json.dumps({
                        "ok": True,
                        "attempt_ids": [],
                        "note": "no attempt identified; "
                                "the system will drop this block.",
                    }),
                    tool_call_id=tool_call_id,
                ))
                logger.info(
                    f"[DH]  force-tool attempt {attempt}: DH chose "
                    f"'no attempts' for {agent_key}/{field} "
                    f"(raw_ids={raw_ids})."
                )
                return [], "explicit-none"

            # Normalise each element + look up its folder.  The whole
            # list must validate cleanly; on any failure, return a
            # ToolMessage error and let the DH retry with a corrected
            # list (not a partial accept).
            normalised: list[str] = []
            invalid: list[tuple[str, str]] = []  # (raw, reason)
            for raw in non_none_ids:
                nnn = _normalise_attempt_input(raw)
                if nnn is None:
                    invalid.append((raw, "unparseable"))
                    continue
                folder, status = _resolve_attempt_folder(
                    nnn, attempts_root, session_start_ts,
                )
                if folder is None:
                    invalid.append((raw, f"no folder matched NNN={nnn}"))
                    continue
                normalised.append(nnn)
                if status == "multi-match":
                    logger.warning(
                        f"[DH]  force-tool: multiple folders matched "
                        f"NNN={nnn}; using most-recent {folder.name}."
                    )

            if invalid:
                err = _json.dumps({
                    "ok": False,
                    "error": (
                        "one or more attempt ids could not be parsed "
                        "or resolved; re-emit the FULL list with valid "
                        "ids only, or pass an empty list / \"none\"."
                    ),
                    "invalid": [
                        {"input": r, "reason": why} for r, why in invalid
                    ],
                    "valid_so_far": normalised,
                    "attempt": attempt,
                    "max_attempts": self._MAX_FORCE_TOOL_RETRIES,
                })
                self.messages.append(ToolMessage(
                    content=err, tool_call_id=tool_call_id,
                ))
                logger.warning(
                    f"[DH]  force-tool attempt {attempt}: invalid="
                    f"{invalid}; reprompting."
                )
                continue

            # All entries resolved → upload each attempt's artefacts.
            uploaded_per_attempt: dict[str, dict] = {}
            try:
                from agents.shared import r2_uploader as _r2
                for nnn in normalised:
                    folder, _ = _resolve_attempt_folder(
                        nnn, attempts_root, session_start_ts,
                    )
                    # folder is guaranteed non-None by the validation
                    # above; ``status`` ignored here (already logged).
                    uploaded, missing = _r2.upload_attempt_artefacts(
                        folder,
                        session_id=session_id,
                        attempt_id=nnn,
                    )
                    uploaded_per_attempt[nnn] = {
                        "folder": folder.name,
                        "uploaded": uploaded,
                        "missing": missing,
                    }
            except Exception as exc:
                err = _json.dumps({
                    "ok": False,
                    "error": (
                        f"R2 upload raised: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                    "attempt": attempt,
                    "max_attempts": self._MAX_FORCE_TOOL_RETRIES,
                })
                self.messages.append(ToolMessage(
                    content=err, tool_call_id=tool_call_id,
                ))
                logger.warning(
                    f"[DH]  force-tool attempt {attempt}: upload "
                    f"raised {type(exc).__name__}: {exc}; reprompting."
                )
                continue

            ok_payload = _json.dumps({
                "ok": True,
                "attempt_ids": [f"attempt {n}" for n in normalised],
                "uploads_per_attempt": uploaded_per_attempt,
            })
            self.messages.append(ToolMessage(
                content=ok_payload, tool_call_id=tool_call_id,
            ))
            logger.info(
                f"[DH]  force-tool attempt {attempt} SUCCEEDED for "
                f"{agent_key}/{field}: {len(normalised)} attempt(s) "
                f"resolved ({normalised}); per-attempt uploads="
                f"{uploaded_per_attempt}"
            )
            return [f"attempt {n}" for n in normalised], "ok"

        logger.warning(
            f"[DH]  force-tool exhausted {self._MAX_FORCE_TOOL_RETRIES} "
            f"retries for {agent_key}/{field}; treating as empty list."
        )
        return [], "max-retries"

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

        The agent-facing tail clause :attr:`_AGENT_FACING_TAIL` is
        appended to the question text before delivery; the DH's own
        running history records the question WITHOUT the tail so the
        DH's prompt does not see the boilerplate echoed back at every
        round.
        """
        dh_trace("DH", agent_key, note=f"asks ({field})")
        convo_buffer.append(
            HumanMessage(content=question + self._AGENT_FACING_TAIL)
        )

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
        if is_semantic:
            cap_line = (
                f"This is a SEMANTIC field.  Your SAVE: body MUST "
                f"contain a ``QUESTION:`` line and an ``ANSWER:`` line "
                f"(in that order).  Combined QUESTION + ANSWER token "
                f"count MUST stay under {self.max_response_tokens} "
                f"(cl100k_base; prefer <600).  Aim for the saved "
                f"QUESTION under ~80 tokens (roughly one sentence) so "
                f"most of the budget goes to the ANSWER.  Apply the "
                f"embedding-friendly rewrite rules from your system "
                f"prompt to BOTH the QUESTION and the ANSWER — strip "
                f"file paths, parameter-value dumps, routing-tool JSON "
                f"wrappers, literal \\n escapes, and mid-chain "
                f"narration."
            )
            shape_line = (
                "Reply with EXACTLY ONE of:\n"
                "  ASK: <a follow-up question for the agent>\n"
                "  SAVE:\n"
                "  QUESTION: <short embedding-friendly question>\n"
                "  ANSWER: <embedding-friendly final body>\n"
            )
        else:
            cap_line = (
                "This is a QUANTITATIVE field — save the data verbatim, "
                "no token cap, do not paraphrase numbers or units.  The "
                "SAVE body is a single prose block (no QUESTION:/"
                "ANSWER: headers)."
            )
            shape_line = (
                "Reply with EXACTLY ONE of:\n"
                "  ASK: <a follow-up question for the agent>\n"
                "  SAVE: <the final body to write to the .txt file>\n"
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
            f"{shape_line}"
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

    def _enforce_semantic_cap_pairs(
        self,
        agent_key: str,
        field: str,
        description: str,
        triples: list[tuple[str | None, str, str]],
    ) -> list[tuple[str | None, str, str]]:
        """Ensure each ``QUESTION + ANSWER`` pair fits the per-PAIR cap.

        Each pair becomes its own ``.txt`` file (one embedding vector
        per file), so the cap is enforced PER PAIR — not combined.
        Counts ``cl100k_base`` tokens on each pair; when one or more
        pairs are over cap, asks the DH ONCE for a shorter version
        of the FULL list (the DH may shorten only the offending pairs
        or all of them — its choice).  If the second attempt is still
        over the cap on some pair, keeps the shorter of the two
        versions for that pair.

        The defensive cleanup (:func:`_clean_semantic_body`) is applied
        to every replacement returned by the DH so artefacts the DH
        adds during shortening are still stripped.
        """
        per_pair_caps = [
            (count_tokens(q) + count_tokens(a), q, a)
            for (_aid, q, a) in triples
        ]
        cap = self.max_response_tokens
        over = [
            (i, total) for i, (total, _q, _a) in enumerate(per_pair_caps)
            if total > cap
        ]
        if not over:
            logger.info(
                f"[DH]  semantic pairs within per-pair cap for "
                f"{agent_key}/{field}: "
                f"{[t for (t, _q, _a) in per_pair_caps]} <= {cap} each"
            )
            return triples

        logger.warning(
            f"[DH]  {len(over)}/{len(triples)} semantic pair(s) OVER "
            f"the {cap}-token per-pair cap for {agent_key}/{field} "
            f"(sizes={[t for (t, _q, _a) in per_pair_caps]}); asking "
            f"for shorter version(s)."
        )
        over_summary = ", ".join(
            f"pair#{i + 1} = {t} tokens" for i, t in over
        )
        instruction = (
            "TOKEN-CAP COMPRESSION TURN.\n\n"
            f"Field: {field}\n"
            f"Field description: {description}\n\n"
            f"Your last SAVE: body for this field produced "
            f"{len(triples)} QUESTION/ANSWER pair(s).  Each pair "
            f"becomes its own .txt that the embedding model reads "
            f"INDEPENDENTLY, so each pair must stay under "
            f"{cap} cl100k_base tokens on its own (prefer <600).\n\n"
            f"Pairs over cap: {over_summary}.\n\n"
            "Re-emit ALL pairs in the same order, shortening the "
            "over-cap ones (and any others you want to tighten).  "
            "Apply the embedding-friendly rules from your system "
            "prompt.  If any pair carries an ATTEMPT: tag, preserve "
            "it on the corresponding pair in the same position.\n\n"
            "Reply with EXACTLY:\n"
            "  SAVE:\n"
            "  [ATTEMPT: <NNN>]\n"
            "  QUESTION: <shorter question>\n"
            "  ANSWER: <shorter answer>\n"
            "  ... (repeat the block for every pair)\n"
            "Do not use ASK: this turn — the system will save "
            "whatever you produce."
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
            payload = payload if kind in ("ASK", "SAVE") else text
            new_triples = _parse_save_body_semantic(payload)
            if not new_triples:
                # DH forgot the headers — fall back to keeping the
                # original triples (shorter pair beats no pair).
                logger.warning(
                    f"[DH]  compression for {agent_key}/{field} "
                    f"emitted no parseable pairs; keeping originals."
                )
                return triples
            # Pair-wise post-process: clean each, count again, keep
            # the shorter of (new, old) per index.
            merged: list[tuple[str | None, str, str]] = []
            for i in range(max(len(triples), len(new_triples))):
                old_attempt, old_q, old_a = (
                    triples[i] if i < len(triples) else (None, "", "")
                )
                if i < len(new_triples):
                    new_attempt, new_q, new_a = new_triples[i]
                    new_q = _clean_semantic_body(new_q) or new_q
                    new_a = _clean_semantic_body(new_a) or new_a
                else:
                    new_attempt, new_q, new_a = old_attempt, old_q, old_a
                # The DH may drop the ATTEMPT tag on a re-emit — keep
                # the original if the new one is None.
                attempt_to_use = (
                    new_attempt if new_attempt is not None else old_attempt
                )
                old_tokens = count_tokens(old_q) + count_tokens(old_a)
                new_tokens = count_tokens(new_q) + count_tokens(new_a)
                if new_tokens <= cap:
                    merged.append((attempt_to_use, new_q, new_a))
                elif new_tokens < old_tokens:
                    merged.append((attempt_to_use, new_q, new_a))
                    logger.warning(
                        f"[DH]  pair#{i + 1} for {agent_key}/{field} "
                        f"still over cap after compression ({new_tokens} "
                        f"> {cap}); keeping the shorter version."
                    )
                else:
                    merged.append((attempt_to_use, old_q, old_a))
                    logger.warning(
                        f"[DH]  pair#{i + 1} for {agent_key}/{field} "
                        f"compression made it longer; keeping original."
                    )
            return merged

        logger.warning(
            f"[DH]  compression turn produced no output for "
            f"{agent_key}/{field}; saving original over-cap pairs."
        )
        return triples

    # ------------------------------------------------------------------
    # Disk I/O
    # ------------------------------------------------------------------

    def _entry_path(
        self,
        session_dir: Path,
        agent_key: str,
        field: str,
        *,
        attempt_suffix: str | None = None,
        item_index: int | None = None,
    ) -> Path:
        """Return the path for one (agent, field) entry's ``.txt``.

        Filename rules (combine cleanly):

        * Base: ``<slugified field>``
        * Multi-attempt sub-row: append ``__<NNN>`` when *attempt_suffix*
          is supplied (the 3-digit attempt number — ``"002"``, etc.).
        * Multi-answer split: append ``_<idx>`` when *item_index* is
          supplied (1-based).

        Examples:

        =====================  ============================================
        Scenario               Filename
        =====================  ============================================
        single                 ``<field>.txt``
        N answer-split items   ``<field>_1.txt`` / ``<field>_2.txt`` / ...
        sub-row, attempt 002   ``<field>__002.txt``
        sub-row, 002 + split   ``<field>__002_1.txt`` / ``<field>__002_2.txt``
        =====================  ============================================
        """
        agent_dir = session_dir / agent_key
        agent_dir.mkdir(parents=True, exist_ok=True)
        base = _slugify(field)
        if attempt_suffix:
            base = f"{base}__{attempt_suffix}"
        if item_index is not None:
            base = f"{base}_{item_index}"
        return agent_dir / f"{base}.txt"

    def _write_entry(
        self,
        session_dir: Path,
        agent_key: str,
        field: str,
        question: str,
        answer: str,
        *,
        session_id: str,
        attempt_id: str | None,
        attempt_suffix: str | None = None,
        item_index: int | None = None,
    ) -> Path:
        """Write one ``(question, answer)`` pair to disk and return path.

        For SEMANTIC fields, ``question`` and ``answer`` are the DH's
        EMBEDDING-FRIENDLY rewrites (capped per-pair); the original
        verbose question the DH put to the agent lives only in the DH
        log file.  For QUANTITATIVE fields, ``question`` is the DH's
        asked question and ``answer`` is Agent A's verbatim reply.

        The header carries:

        * ``--- Session ID ---``   — the ``IDxxx_YYYYMMDD_HHMMSS`` slug
          shared with ``previous_sessions/`` and the R2 mirror's
          per-session prefix.
        * ``--- Attempt ID ---``   — set to ``attempt_id`` when known,
          ``"(session-scope)"`` for session-scoped rows, or
          ``"(unbound)"`` for attempt rows that errored.
        * ``--- Field ---``        — the schedule's human-readable
          field name (NOT the slug — the slug is the filename).

        *attempt_suffix* and *item_index* are filename-only controls;
        the body content is unchanged either way.  Callers decide
        which suffixes apply based on N attempts / N answer-split
        items.
        """
        path = self._entry_path(
            session_dir, agent_key, field,
            attempt_suffix=attempt_suffix,
            item_index=item_index,
        )
        attempt_line = attempt_id if attempt_id else "(session-scope)"
        path.write_text(
            f"--- Session ID ---\n{session_id}\n\n"
            f"--- Attempt ID ---\n{attempt_line}\n\n"
            f"--- Field ---\n{field}\n\n"
            "--- Question ---\n"
            f"{question}\n\n"
            "--- Answer ---\n"
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
        *,
        session_id: str = "",
        attempt_id: str | None = None,
    ) -> Path:
        """Write a sentinel ``ERROR:`` entry when the conversation failed.

        ``session_id`` / ``attempt_id`` mirror :meth:`_write_entry` so
        the future RAG layer can still bucket failures by session;
        both are optional with safe defaults to preserve backward
        compatibility with any external test caller.
        """
        path = self._entry_path(session_dir, agent_key, field)
        attempt_line = attempt_id if attempt_id else "(session-scope)"
        path.write_text(
            f"--- Session ID ---\n{session_id}\n\n"
            f"--- Attempt ID ---\n{attempt_line}\n\n"
            f"--- Field ---\n{field}\n\n"
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

    def _write_sidecar_meta(
        self,
        entry_path: Path,
        *,
        entry: dict,
        attempt_id: str | None,
    ) -> None:
        """Write the per-question metadata as a sidecar JSON next to *entry_path*.

        The sidecar carries fields used by the (future) RAG retrieval
        layer but kept OUT of the embedded ``.txt`` so the embedding
        vector is not polluted by access-control metadata:

          ``to_agents``  list of agent keys the future RAG layer may
                         expose this answer to.
          ``scope``      "session" | "attempt"
          ``type``       "Semantic" | "Quantitative"
          ``attempt_id`` resolved attempt identifier (None when not
                         attempt-bound or when binding failed)
          ``question_id`` stable id from the schedule (so the sidecar
                          can be cross-referenced back to the editor
                          row)

        Filename: ``<field_slug>.meta.json`` (parallel to the .txt).
        Best-effort: a failure to write the sidecar logs a warning but
        does not break the save.
        """
        try:
            import json as _json
            meta_path = entry_path.with_suffix(".meta.json")
            meta_path.write_text(
                _json.dumps(
                    {
                        "question_id": entry.get("id"),
                        "scope":       entry.get("scope") or "session",
                        "type":        entry.get("type") or "Semantic",
                        "to_agents":   list(entry.get("to_agents") or []),
                        "attempt_id":  attempt_id,
                    },
                    indent=2,
                    ensure_ascii=False,
                ) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(
                f"[DH]  failed to write sidecar meta for "
                f"{entry_path.name}: {exc}"
            )

    def _collect_user_inputs(self, session_dir: Path) -> int:
        """Snapshot the session's user inputs into the database tree.

        Copies into ``<session_dir>/user_inputs/``:

        * ``queries.txt`` — the full turn-by-turn collection of user
          text inputs.  Source is ``inputs/user_query.txt``, which the
          dispatcher APPENDS to on every ``/api/turn`` call
          (``agents/dispatch.py:save_user_input``), so it already
          carries every turn the user submitted this session with a
          ``--- [YYYY-MM-DD HH:MM:SS] ---`` header before each entry.
        * ``images/<original_name>`` — every reference image the user
          uploaded via the Image Inputs view, plus its matching
          ``<name>_note.txt`` description sidecar.  Original filenames
          are preserved so the image / note pairing is obvious.

        The local copies live alongside the per-agent ``.txt`` files
        the DH already writes; the subsequent R2 mirror picks them
        up via the suffix whitelist (``.txt`` / ``.png`` / ``.jpg`` /
        ``.jpeg``).  The original ``inputs/`` directory is left
        intact — End Session's archival sweep moves it under
        ``previous_sessions/<session_id>/inputs/`` afterwards.

        Returns the number of files written into
        ``<session_dir>/user_inputs/``.  Best-effort throughout: each
        copy is wrapped so a single I/O failure (a corrupt image, a
        permissions blip) doesn't abort the rest of the collection.
        """
        import shutil

        target = session_dir / "user_inputs"
        target.mkdir(parents=True, exist_ok=True)
        written = 0

        # 1. The cumulative text-input collection.
        src_query = USER_INPUTS_DIR / "user_query.txt"
        if src_query.is_file():
            try:
                shutil.copyfile(src_query, target / "queries.txt")
                written += 1
                logger.info(
                    f"[DH]  copied user_query.txt → "
                    f"{(target / 'queries.txt').name}"
                )
            except OSError as exc:
                logger.warning(
                    f"[DH]  failed to copy user_query.txt: {exc}"
                )
        else:
            logger.info(
                f"[DH]  no user_query.txt at {src_query.resolve()}; "
                f"the user issued no text turns this session."
            )

        # 2. Every reference image + its _note.txt sidecar.
        if INPUT_IMAGES_DIR.is_dir():
            images_target = target / "images"
            images_target.mkdir(parents=True, exist_ok=True)
            n_imgs = 0
            n_notes = 0
            for entry in sorted(INPUT_IMAGES_DIR.iterdir()):
                if not entry.is_file():
                    continue
                # Skip the .gitkeep marker if present.
                if entry.name in (".gitkeep",):
                    continue
                try:
                    shutil.copyfile(entry, images_target / entry.name)
                    written += 1
                    if entry.suffix.lower() == ".txt":
                        n_notes += 1
                    else:
                        n_imgs += 1
                except OSError as exc:
                    logger.warning(
                        f"[DH]  failed to copy {entry.name}: {exc}"
                    )
            logger.info(
                f"[DH]  copied {n_imgs} image(s) + {n_notes} note "
                f"file(s) from {INPUT_IMAGES_DIR.name}/ → "
                f"{(target / 'images').name}/"
            )
        else:
            logger.info(
                f"[DH]  no images directory at "
                f"{INPUT_IMAGES_DIR.resolve()}; no images to collect."
            )

        return written

