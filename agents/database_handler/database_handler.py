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

_SAVE_Q_RE = re.compile(
    r"^\s*QUESTION\s*:\s*(.*?)(?=^\s*ANSWER\s*:|\Z)",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)
_SAVE_A_RE = re.compile(
    r"^\s*ANSWER\s*:\s*(.*)\Z",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)


def _parse_save_body_semantic(text: str) -> tuple[str | None, str | None]:
    """Split a SEMANTIC SAVE body into ``(saved_question, saved_answer)``.

    Returns ``(None, None)`` when the expected headers are missing —
    the caller treats that as a protocol slip and falls back gracefully.
    """
    if not text:
        return None, None
    q_match = _SAVE_Q_RE.search(text)
    a_match = _SAVE_A_RE.search(text)
    if not q_match or not a_match:
        return None, None
    return q_match.group(1).strip(), a_match.group(1).strip()


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

            # Maps an identifying Q(N)'s ``id`` to the textual attempt
            # identifier extracted from its raw reply.  ``None`` means
            # the parent ran but no identifier could be parsed (even
            # after the re-ask) — children of that parent are skipped
            # with empty-placeholder writes.
            attempt_id_by_parent: dict[str, str | None] = {}

            written = 0
            for entry in schedule_entries:
                # Publish the field's short label so the flowchart's
                # caption under the DH box updates to the question
                # currently being asked.  Uses the same ``generic_tool``
                # convention every other agent uses; the frontend
                # ignores the ``end`` state, so the label PERSISTS
                # until the next field overwrites it.
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
                to_agents = entry.get("to_agents") or []

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
                        self._write_sidecar_meta(
                            path, entry=entry, attempt_id=None,
                        )
                        written += 1
                    except OSError as exc:
                        logger.warning(
                            f"[DH]  failed to write empty placeholder "
                            f"for {agent_key}/{field}: {exc}"
                        )
                    continue

                # Attempt-specific sub-row (Q(N).x) whose parent had no
                # parseable attempt id → empty placeholder + skip.
                if parent_id is not None and attempt_id_by_parent.get(parent_id) is None and parent_id in attempt_id_by_parent:
                    logger.info(
                        f"[DH]  parent Q row {parent_id!r} did not "
                        f"resolve an attempt id; writing empty "
                        f"placeholder for sub-field '{field}'"
                    )
                    try:
                        path = self._write_empty_entry(
                            session_dir=session_dir,
                            agent_key=agent_key,
                            field=field,
                        )
                        self._write_sidecar_meta(
                            path, entry=entry, attempt_id=None,
                        )
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
                    err_path = self._write_error_entry(
                        session_dir=session_dir,
                        agent_key=agent_key,
                        field=field,
                        error_message=(
                            f"agent key '{agent_key}' is not present in "
                            f"the orchestrator's registry / session.agent_"
                            f"states; the DH could not interview it."
                        ),
                    )
                    self._write_sidecar_meta(
                        err_path, entry=entry, attempt_id=None,
                    )
                    continue

                # Prefix the description with the attempt anchor for
                # sub-rows whose parent resolved an id.  The DH's
                # _formulate_question reads ``description`` verbatim, so
                # the anchor flows naturally into both the asked and the
                # saved (embedded) question.
                effective_description = entry.get("description", "")
                resolved_for_parent = (
                    attempt_id_by_parent.get(parent_id)
                    if parent_id is not None
                    else None
                )
                if parent_id is not None and resolved_for_parent:
                    effective_description = (
                        f"For {resolved_for_parent}: "
                        f"{effective_description}"
                    )

                logger.info(
                    f"[DH]  starting conversation with {agent_key} "
                    f"(field='{field}', type={entry.get('type', 'Semantic')}, "
                    f"scope={scope}, parent_id={parent_id})"
                )
                try:
                    question, answer, raw_answer = self._run_one_conversation(
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
                    )
                    self._write_sidecar_meta(
                        err_path, entry=entry, attempt_id=None,
                    )
                    if scope == "attempt" and parent_id is None:
                        # Identifying Q failed entirely — mark as
                        # "unresolved" so its children skip cleanly.
                        attempt_id_by_parent[entry["id"]] = None
                    continue

                # Attempt-binding for identifying Q(N) rows: parse the
                # raw reply.  On miss, re-ask the same agent ONCE with
                # an explicit naming instruction.
                if scope == "attempt" and parent_id is None:
                    attempt_id = _extract_attempt_id(raw_answer)
                    if attempt_id is None:
                        logger.info(
                            f"[DH]  no attempt id parsed from "
                            f"{agent_key}/{field}; re-asking with "
                            f"explicit instruction."
                        )
                        explicit = (
                            f"{effective_description}\n\n(IMPORTANT: in "
                            f"your answer, please name the exact attempt "
                            f"you refer to by its identifier — an "
                            f"attempt folder slug like "
                            f"'YYYYMMDD_HHMMSS_NNN_<descriptor>' or an "
                            f"'attempt NNN' / 'attempt #NNN' phrase — so "
                            f"the system can bind follow-up questions to "
                            f"the same attempt.)"
                        )
                        try:
                            (
                                question_retry,
                                answer_retry,
                                raw_answer_retry,
                            ) = self._run_one_conversation(
                                agent_key=agent_key,
                                agent_system_prompt=getattr(agent, "system_prompt", "") or "",
                                agent_provider=getattr(agent, "provider", self.provider),
                                agent_base_llm=getattr(agent, "base_llm", None) or agent.llm,
                                agent_messages=list(agent_state.messages),
                                field=field,
                                description=explicit,
                                field_type=entry.get("type", "Semantic"),
                            )
                            attempt_id = _extract_attempt_id(raw_answer_retry)
                            if attempt_id is not None:
                                question, answer, raw_answer = (
                                    question_retry,
                                    answer_retry,
                                    raw_answer_retry,
                                )
                        except Exception as exc:  # pragma: no cover
                            logger.warning(
                                f"[DH]  attempt-id re-ask failed for "
                                f"{agent_key}/{field}: {exc}"
                            )
                    attempt_id_by_parent[entry["id"]] = attempt_id
                    if attempt_id is None:
                        logger.warning(
                            f"[DH]  could not bind attempt id for "
                            f"{agent_key}/{field}; children of this row "
                            f"will be skipped with empty placeholders."
                        )

                try:
                    path = self._write_entry(
                        session_dir=session_dir,
                        agent_key=agent_key,
                        field=field,
                        question=question,
                        answer=answer,
                    )
                    bound_attempt = (
                        attempt_id_by_parent.get(entry["id"])
                        if (scope == "attempt" and parent_id is None)
                        else resolved_for_parent
                    )
                    self._write_sidecar_meta(
                        path, entry=entry, attempt_id=bound_attempt,
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
    ) -> tuple[str, str, str]:
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

        if is_semantic:
            # New SEMANTIC SAVE shape: the body itself carries
            # QUESTION: and ANSWER: headers.  Defensive: when the DH
            # forgets the headers, treat the whole body as the answer
            # and reuse the asked question as the saved question
            # (cleaned through the same safety net).
            saved_q, saved_a = _parse_save_body_semantic(final_body)
            if saved_q is None or saved_a is None:
                logger.warning(
                    f"[DH]  SAVE body for {agent_key}/{field} did not "
                    f"contain QUESTION:/ANSWER: headers; using asked "
                    f"question + whole body as fallback."
                )
                saved_q = first_question
                saved_a = final_body

            # Safety-net cleanup BEFORE the cap check so the cap
            # measures what will actually be written.
            saved_q = _clean_semantic_body(saved_q) or saved_q
            saved_a = _clean_semantic_body(saved_a) or saved_a

            saved_q, saved_a = self._enforce_semantic_cap_pair(
                agent_key=agent_key,
                field=field,
                description=description,
                saved_question=saved_q,
                saved_answer=saved_a,
            )
            # Third return value is the RAW last agent answer (before
            # any cleanup).  populate_database needs it for attempt-id
            # extraction — the cleaned saved_a has paths and slugs
            # stripped, which would defeat _extract_attempt_id.
            return saved_q, saved_a, last_answer

        # QUANTITATIVE — legacy single-body path, untouched.
        return first_question, final_body, last_answer

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

    def _enforce_semantic_cap_pair(
        self,
        agent_key: str,
        field: str,
        description: str,
        saved_question: str,
        saved_answer: str,
    ) -> tuple[str, str]:
        """Ensure ``QUESTION + ANSWER`` fits within the SEMANTIC token cap.

        Counts ``cl100k_base`` tokens on the combined pair (mirrors how
        the embedding model sees the .txt file at index time).  When
        over cap, asks the DH ONCE for a shorter version of EITHER or
        BOTH components and accepts whatever comes back (subject to
        the same QUESTION:/ANSWER: parse).  If the second attempt is
        still over the cap, saves the shorter of the two pairs — the
        goal is best-effort compliance, not infinite-loop perfection.

        The defensive cleanup (:func:`_clean_semantic_body`) is applied
        to every replacement body returned by the DH so artefacts the
        DH adds during shortening are still stripped.
        """
        n_q = count_tokens(saved_question)
        n_a = count_tokens(saved_answer)
        n = n_q + n_a
        if n <= self.max_response_tokens:
            logger.info(
                f"[DH]  semantic Q+A within cap for "
                f"{agent_key}/{field}: {n_q}+{n_a}={n} <= "
                f"{self.max_response_tokens} tokens"
            )
            return saved_question, saved_answer

        logger.warning(
            f"[DH]  semantic Q+A OVER cap for {agent_key}/{field}: "
            f"{n_q}+{n_a}={n} > {self.max_response_tokens} tokens; "
            f"asking for shorter pair."
        )
        instruction = (
            "TOKEN-CAP COMPRESSION TURN.\n\n"
            f"Field: {field}\n"
            f"Field description: {description}\n\n"
            f"Your last SAVE: body for this field used "
            f"{n_q} QUESTION tokens + {n_a} ANSWER tokens = {n} total "
            f"under cl100k_base, but the combined cap is "
            f"{self.max_response_tokens}.  Rewrite the pair to fit "
            "comfortably below the cap (prefer <600 combined) WITHOUT "
            "losing the field's meaning.  Shorten QUESTION, ANSWER, or "
            "both — your choice.  Apply the embedding-friendly rules "
            "from your system prompt: strip paths, parameter dumps and "
            "routing-tool wrappers; self-contained declarative prose; "
            "domain-faithful; one topic per file; no filler.\n\n"
            "Reply with EXACTLY:\n"
            "  SAVE:\n"
            "  QUESTION: <shorter question>\n"
            "  ANSWER: <shorter answer>\n"
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
            payload = payload if kind in ("ASK", "SAVE") else text
            q2, a2 = _parse_save_body_semantic(payload)
            if q2 is None or a2 is None:
                # DH forgot the headers during compression too — fall
                # back to treating the whole payload as the shorter
                # answer and keep the existing question.
                q2 = saved_question
                a2 = payload
            q2 = _clean_semantic_body(q2) or q2
            a2 = _clean_semantic_body(a2) or a2
            n2_q = count_tokens(q2)
            n2_a = count_tokens(a2)
            n2 = n2_q + n2_a
            logger.info(
                f"[DH]  compressed Q+A for {agent_key}/{field}: "
                f"{n_q}+{n_a}={n} -> {n2_q}+{n2_a}={n2} tokens"
            )
            if n2 <= self.max_response_tokens:
                return q2, a2
            logger.warning(
                f"[DH]  compression did not reach cap for "
                f"{agent_key}/{field} ({n2} > "
                f"{self.max_response_tokens}); saving the shorter pair."
            )
            return (q2, a2) if n2 < n else (saved_question, saved_answer)

        logger.warning(
            f"[DH]  compression turn produced no output for "
            f"{agent_key}/{field}; saving original over-cap pair."
        )
        return saved_question, saved_answer

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
        """Write one ``(question, answer)`` pair to disk and return path.

        For SEMANTIC fields, ``question`` and ``answer`` are the DH's
        EMBEDDING-FRIENDLY rewrites (combined under the token cap);
        the original verbose question the DH put to the agent lives
        only in the DH log file.  For QUANTITATIVE fields, ``question``
        is the DH's asked question and ``answer`` is Agent A's
        verbatim reply.
        """
        path = self._entry_path(session_dir, agent_key, field)
        path.write_text(
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

