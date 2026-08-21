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

Interview protocol
------------------
Rows are asked in BATCHES: neighbouring rows going to the same agent
can share one call, which is what makes a save affordable (roughly
half the LLM calls on the shipped schedule).  Which rows travel
together is the DH's decision, taken once per save; code only fixes
the boundaries a batch may not cross (see
``batch_tools.candidate_runs``).

Every DH decision is a FORCED TOOL CALL — never prose:

* ``submit_batch_plan`` — once per save; which rows are asked together.
* ``submit_questions`` — once per batch; one question per row.
* ``submit_batch``     — after each reply; per row, what to save, what
  to ask again (``followups``), what to drop (``skips``).
* ``save_attempt_data`` — binds which design attempt(s) an
  attempt-identifying row is about, before anything attempt-scoped
  is written.

Each tool is bound for ONE turn and discarded, so the DH's LLM never
sees more than one tool schema at a time (the W18 / W20 invariant).

Answers map back to rows by short per-call LABELS (``A``, ``B``, …),
checked for full coverage before anything is written.  This replaced a
text protocol (``ASK:`` / ``SAVE:`` with ``QUESTION:`` / ``ANSWER:`` /
``ATTEMPT:`` headers) whose failures were silent: a header carrying
markdown became answer text, and an untagged block inherited the
previous block's attempt id, so one attempt's answer could be written
into another's file and database row with nothing marking it wrong.

Follow-up rounds are capped at ``MAX_DH_TURNS_PER_FIELD`` per batch;
on exhaustion one final forced turn must save or skip.  For SEMANTIC
rows each saved question+answer pair must fit
``EMBEDDING_MAX_RESPONSE_TOKENS`` (``cl100k_base``) on its own, since
each becomes its own file and its own embedding; over-cap pairs are
re-emitted once, keyed by label.  Quantitative rows are saved verbatim
and uncapped.

A row with nothing worth storing is SKIPPED: its ``.txt`` is written
with a ``SKIPPED`` marker and no database row, rather than saving a
"no problem occurred this session" sentence that would be embedded and
would then compete with real content at search time.

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

from agents.database_handler import db_writer
from agents.database_handler.dh_trace import (
    close_dh_logging,
    dh_trace,
    init_dh_logging,
)
from agents.database_handler.token_utils import count_tokens
from agents.shared import postgres_pool
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.file_utils import ai_text
from agents.shared.llm_provider import history_cache_control, make_system_message
from agents.shared.llm_retry import invoke_with_retry
from agents.shared.prompts import PARAMETER_NAMES, _build_template
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


_IMAGE_BLOCK_TYPES = frozenset({"image", "image_url"})


def _without_image_blocks(messages: list) -> tuple[list, int]:
    """Copy *messages*, dropping every image content block.

    Returns ``(messages, n_removed)``.  Messages carrying no image block
    are passed through by reference; only the ones that change are
    copied, so the common case allocates nothing.

    NON-MUTATING on purpose.  ``shared/file_utils.strip_image_blocks_
    from_messages`` does the same job in place, but the DH seeds its
    conversation from ``list(session.agent_states[k].messages)`` — a
    SHALLOW copy, whose elements are the very objects the session holds.
    Stripping those in place would permanently delete image blocks from
    the saved session state as a side effect of a save.

    Why strip at all: the interview asks an agent to recall and explain
    its own reasoning, never to look at a picture again, and the paired
    ``Loaded image (path: …):`` text blocks survive as a record of what
    it had seen.  Removing the bytes lets the interview run on a small
    text-only model and drops a large share of its input tokens.
    """
    out: list = []
    removed = 0
    for m in messages:
        content = getattr(m, "content", None)
        if not isinstance(content, list):
            out.append(m)
            continue
        kept = [
            b for b in content
            if not (isinstance(b, dict) and b.get("type") in _IMAGE_BLOCK_TYPES)
        ]
        if len(kept) == len(content):
            out.append(m)
            continue
        removed += len(content) - len(kept)
        try:
            out.append(m.model_copy(update={"content": kept}))
        except Exception:
            # Not a pydantic message (or a frozen one) — keep the
            # original rather than lose the turn.  Worst case the
            # interview model sees the images it would have seen before.
            out.append(m)
    return out, removed


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

# Narrow strip for the sub-row "For attempt NNN:" lead-in.  Sub-row
# descriptions are auto-prefixed with ``"For attempt NNN: "`` (see
# the ``sub_desc = f"For {attempt_str}: {sub_entry.get('description','')}"``
# line in :meth:`populate_database`) so Agent A knows which attempt
# the question is scoped to.  Without intervention the DH model
# parrots the lead-in into the short SAVE: QUESTION (and sometimes
# the ANSWER), which is redundant — the attempt id is already in
# the filename suffix (``__NNN``) and in the file body's
# ``--- Attempt ID ---`` header that ``_write_entry`` writes.
#
# Surgically narrow: only the literal lead-in pattern, NOT bare
# "attempt NNN" elsewhere in the body, so cross-references like
# "unlike attempt 002, this one ..." survive.
_ATTEMPT_LEADIN_RE = re.compile(
    r"^\s*[Ff]or\s+attempt\s*#?\s*\d{1,4}\s*[:\-,]\s*",
    re.MULTILINE,
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

    # 3b. Strip the "For attempt NNN:" / "for attempt NNN -"
    #     scope-anchor lead-in that sub-row descriptions auto-prefix.
    #     The attempt id is already recorded in the file's filename
    #     suffix (``__NNN``) and in the ``--- Attempt ID ---`` header,
    #     so echoing it into the short SAVE: QUESTION/ANSWER wastes
    #     embedding-token budget.  Narrow on purpose: bare
    #     "attempt NNN" cross-references elsewhere in the body
    #     (e.g. "unlike attempt 002, this one was better") are
    #     legitimate and survive.
    body = _ATTEMPT_LEADIN_RE.sub("", body)

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
        # Built fresh at construction time so live edits to .md
        # fragments on disk take effect on the
        # NEXT session without a Python restart.
        self.system_prompt: str = _build_template("database_handler")

        # Cached for SEMANTIC token-cap enforcement.
        self.max_response_tokens: int = int(
            workflow_settings.EMBEDDING_MAX_RESPONSE_TOKENS
        )

        # Resolved once per save by :meth:`_interview_llm` and reused for
        # every interviewed agent.  ``None`` = not resolved yet; the
        # sentinel below = resolved to "each agent's own model".
        self._interview_llm_cache: tuple | None = None

    # ------------------------------------------------------------------
    # Which LLM answers the interview
    # ------------------------------------------------------------------

    # DH_INTERVIEW_PROVIDER value meaning "leave every agent on its own
    # live model" — the historic behaviour.  Compared case-insensitively
    # so a hand-edited settings.py cannot miss it on capitalisation.
    _ORIGINAL_AGENT = "original agent"

    def _interview_llm(self, agent) -> tuple:
        """The ``(llm, provider)`` pair that answers this agent's questions.

        By default (``DH_INTERVIEW_PROVIDER = "Original Agent"``) this is
        the agent's own bare LLM and its own provider tag — exactly what
        the DH used before the setting existed.  When the setting names a
        real provider, EVERY interviewed agent answers on that one model
        instead, which is where a save's cost mostly goes: ~36 answers,
        each re-sending a full session history, billed at the strongest
        models in the workflow.

        The provider tag travels WITH the llm on purpose.  ``_ask_agent``
        passes it to ``make_system_message``, which emits an Anthropic
        ``cache_control`` block for Anthropic and a plain string
        otherwise — swapping the model without the tag would send an
        Anthropic-shaped system block to OpenAI.

        Read fresh from settings at the first call of each save (the same
        contract as every other setting: an edit applies to the next
        session), then memoised for the rest of the save.

        Fail-open: any resolution error (unknown provider, missing API
        key, a model the client rejects at construction) logs a warning
        and falls back to the agent's own LLM.  A misconfigured setting
        must never cost a whole session's worth of answers.
        """
        agent_own = (
            getattr(agent, "base_llm", None) or agent.llm,
            getattr(agent, "provider", self.provider),
        )

        if self._interview_llm_cache is None:
            provider = str(
                getattr(workflow_settings, "DH_INTERVIEW_PROVIDER",
                        "Original Agent")
            ).strip()
            model = str(
                getattr(workflow_settings, "DH_INTERVIEW_MODEL", "")
            ).strip()
            if provider.lower() == self._ORIGINAL_AGENT or not provider:
                logger.info(
                    "[DH]  interview model: each agent's own "
                    "(DH_INTERVIEW_PROVIDER = 'Original Agent')"
                )
                self._interview_llm_cache = ()
            else:
                try:
                    from agents.shared.llm_provider import build_llm_for
                    llm, resolved_provider, resolved_model = build_llm_for(
                        provider, model,
                    )
                    self._interview_llm_cache = (llm, resolved_provider)
                    logger.info(
                        f"[DH]  interview model: {resolved_provider}/"
                        f"{resolved_model} for EVERY interviewed agent "
                        f"(overrides each agent's own model)"
                    )
                except Exception as exc:
                    logger.warning(
                        f"[DH]  could not build the configured interview "
                        f"model {provider}/{model or '(default)'}: "
                        f"{type(exc).__name__}: {exc}.  Falling back to "
                        f"each agent's own model for this save."
                    )
                    self._interview_llm_cache = ()

        return self._interview_llm_cache or agent_own

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

        # Build the active topology's wired hub from self.session if
        # the caller didn't supply one.  Used only to read each
        # agent's ``system_prompt`` and ``base_llm`` — never mutated,
        # never invoked.
        if orchestrator is None:
            from agents.hub import build_hub
            orchestrator = build_hub(self.session)

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
            # Decide, in ONE call, which rows are asked together.  Skipped
            # entirely when no run holds more than one row — there would be
            # nothing to decide, and the call is not free.  ``handled_ids``
            # then keeps the main loop from re-asking a row that an earlier
            # batch already settled.
            from agents.database_handler import batch_tools as _bt
            batch_group_of: dict[str, list[dict]] = {}
            handled_ids: set[str] = set()
            if any(len(r) > 1 for r in _bt.candidate_runs(schedule_entries)):
                try:
                    batch_group_of = self._plan_batches(schedule_entries)
                except Exception as exc:  # pragma: no cover — defensive
                    logger.warning(
                        f"[DH]  batch planning raised "
                        f"{type(exc).__name__}: {exc}; asking every row "
                        f"on its own."
                    )
            else:
                logger.info(
                    "[DH]  no run holds more than one row; nothing to "
                    "batch, skipping the planning call."
                )

            attempt_ids_by_parent: dict[str, list[str]] = {}

            # Session-id slug embedded in every saved .txt and used
            # as the per-session prefix for the R2 mirror.  Same value
            # the archive sweep uses under previous_sessions/.
            # Moved UP here (was below the schedule-loading block
            # before Phase 3C) because the Phase 3C upsert_session +
            # per-Q+A insert_chunk blocks below all need session_id
            # — leaving it below them would UnboundLocalError on the
            # first DB call.
            session_id = session_dir.name

            # Phase 3C caches — live for the duration of THIS
            # populate_database call.
            #   attempt_id_by_nnn: maps each DH-chosen attempt_label
            #     to the BIGSERIAL ``dc_attempts.attempt_id`` returned
            #     by db_writer.upsert_attempt.  Per-Q+A insert_chunk
            #     looks up the BIGSERIAL here when an attempt-scoped
            #     row is about to land.
            #   cascaded_attempt_nnns: attempt_labels whose
            #     identifying-Q INSERT returned SAFETY OR whose
            #     upsert_attempt itself failed.  Every subsequent
            #     attempt-scoped Q+A for these attempts SKIPS
            #     insert_chunk and goes straight to the R2 safety
            #     folder with cascade_source set.  See architecture
            #     doc §3.5.5 + §9.5.
            attempt_id_by_nnn: dict[str, int] = {}
            cascaded_attempt_nnns: set[str] = set()

            # Phase 3C — when Postgres is not configured (local dev
            # without a DATABASE_URL), the entire DB path is skipped.
            # No row marked as cascaded; no insert_chunk calls fired.
            # See Q-3C-B3 = (A).
            db_writer_available = postgres_pool.is_enabled()
            if not db_writer_available:
                logger.info(
                    "[DH]  Phase 3C: postgres_pool.is_enabled() is "
                    "False; SKIPPING all Postgres-side writes for "
                    "this save (R2 mirror unaffected)."
                )

            # Phase 3C — upsert the sessions row FIRST, before any
            # schedule processing.  Pre-creates the parent row that
            # every chunks FK (directly) and every dc_attempts FK
            # (transitively) needs.  See architecture doc §9.5 + Q-3C-3.
            #
            # On failure: log ERROR and DISABLE db_writer for the rest
            # of this populate_database call (R2 mirror unaffected).
            # Rationale: if the sessions row cannot land, every
            # subsequent chunks INSERT would FK-fail and route to
            # safety anyway; bailing here keeps the log clean.
            #
            # ``notes`` is passed as None (T21 — reserved column,
            # first use case TBD; see warnings_developer.md W26).
            # ``user_id`` is forwarded from self.session.user_id which
            # is currently always None (T22 / F22 — reserved column,
            # frontend wiring TBD; see warnings_developer.md W27).
            # ``user_provided_images`` is derived by globbing the
            # session inputs dir for common image suffixes — works
            # for v9's PNG/JPG/JPEG pipeline but won't catch HEIC /
            # WEBP / AVIF in the future (T20).
            if db_writer_available:
                user_provided_images = False
                if self.session.inputs_dir is not None:
                    try:
                        user_provided_images = any(
                            p.is_file()
                            for ext in ("*.png", "*.jpg", "*.jpeg")
                            for p in self.session.inputs_dir.glob(ext)
                        )
                    except OSError:
                        user_provided_images = False  # defensive
                try:
                    db_writer.upsert_session(
                        session_id=session_id,
                        session_ts=self.session.session_ts,
                        dc_name=self.session.dc_name,
                        schema_version=self.session.schema_version,
                        dc_inspector_enabled=self.session.dc_inspector_enabled,
                        user_id=self.session.user_id,
                        user_provided_images=user_provided_images,
                        notes=None,
                    )
                    logger.info(
                        f"[DH]  Phase 3C upsert_session OK "
                        f"session_id={session_id} "
                        f"user_provided_images={user_provided_images}"
                    )
                except Exception as exc:
                    logger.error(
                        f"[DH]  Phase 3C upsert_session FAILED "
                        f"session_id={session_id}: "
                        f"{type(exc).__name__}: {exc}.  DISABLING "
                        f"all Postgres writes for the remainder of "
                        f"this save (R2 mirror unaffected)."
                    )
                    db_writer_available = False

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
                    error_msg = (
                        f"agent key '{agent_key}' is not present in "
                        f"the orchestrator's registry / session.agent_"
                        f"states; the DH could not interview it."
                    )
                    err_path = self._write_error_entry(
                        session_dir=session_dir,
                        agent_key=agent_key,
                        field=field,
                        error_message=error_msg,
                        session_id=session_id,
                        attempt_id=None,
                    )
                    self._write_sidecar_meta(
                        err_path, entry=entry, attempt_id=None,
                    )
                    # Phase 3C — error rows also land in chunks
                    # (is_error=True).  The DH never resolved an
                    # attempt here (agent unknown), so this row is
                    # session-scoped (nnn=None).  See §9.5 + Q-3C-E1.
                    self._phase_3c_persist_chunk(
                        session_id=session_id,
                        nnn=None,
                        agent_key=agent_key,
                        agents_to=list(entry.get("to_agents") or []),
                        field=field,
                        field_type="Semantic",
                        question=None,
                        body=f"ERROR: {error_msg}",
                        item_index=None,
                        is_error=True,
                        is_identifying=False,
                        safety_filename=err_path.name,
                        attempt_id_by_nnn=attempt_id_by_nnn,
                        cascaded_attempt_nnns=cascaded_attempt_nnns,
                        db_writer_available=db_writer_available,
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
                                # (llm, provider) resolved together — see
                                # _interview_llm; the provider tag must
                                # match the model that receives it.
                                agent_provider=self._interview_llm(agent)[1],
                                agent_base_llm=self._interview_llm(agent)[0],
                                agent_messages=list(agent_state.messages),
                                field=field,
                                description=effective_description,
                                field_type=entry.get("type", "Semantic"),
                                session_id=session_id,
                                session_start_ts=session_start_ts,
                                # Phase 3C — forwarded to _run_force_tool_phase
                                # via _run_identifying_conversation (which now
                                # accepts them since the previous regression
                                # fix).
                                attempt_id_by_nnn=attempt_id_by_nnn,
                                cascaded_attempt_nnns=cascaded_attempt_nnns,
                                db_writer_available=db_writer_available,
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
                        only_nnn = _normalise_attempt_input(only_attempt)
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
                                # Phase 3C — identifying-Q row, attempt-scoped.
                                self._phase_3c_persist_chunk(
                                    session_id=session_id,
                                    nnn=only_nnn,
                                    agent_key=agent_key,
                                    agents_to=list(entry.get("to_agents") or []),
                                    field=field,
                                    field_type=entry.get("type", "Semantic"),
                                    question=q,
                                    body=a,
                                    item_index=item_index,
                                    is_error=False,
                                    is_identifying=True,
                                    safety_filename=path.name,
                                    attempt_id_by_nnn=attempt_id_by_nnn,
                                    cascaded_attempt_nnns=cascaded_attempt_nnns,
                                    db_writer_available=db_writer_available,
                                )
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
                                # Phase 3C — identifying-Q row in
                                # multi-attempt loop, attempt-scoped.
                                self._phase_3c_persist_chunk(
                                    session_id=session_id,
                                    nnn=norm,
                                    agent_key=agent_key,
                                    agents_to=list(entry.get("to_agents") or []),
                                    field=field,
                                    field_type=entry.get("type", "Semantic"),
                                    question=q,
                                    body=a,
                                    item_index=None,
                                    is_error=False,
                                    is_identifying=True,
                                    safety_filename=path.name,
                                    attempt_id_by_nnn=attempt_id_by_nnn,
                                    cascaded_attempt_nnns=cascaded_attempt_nnns,
                                    db_writer_available=db_writer_available,
                                )
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

                        # Multi-attempt → always use the __NNN suffix on
                        # sub-row files so they don't collide across
                        # attempts.
                        attempt_suffix = norm if n_attempts >= 2 else None

                        def _persist_sub(
                            sub_entry: dict, result,
                            _attempt_str=attempt_str, _norm=norm,
                            _suffix=attempt_suffix,
                        ) -> None:
                            """Write one settled sub-row for ONE attempt.

                            The attempt is bound through the default
                            arguments rather than read from the enclosing
                            scope: this closure outlives the loop
                            iteration that made it (``_run_batch`` calls
                            it later), and a late read would file every
                            attempt's answers under the last one.
                            """
                            nonlocal written
                            if result == "unsettled":
                                sub_unsettled.append(sub_entry)
                                return
                            if result is None:
                                try:
                                    spath = self._write_skipped_entry(
                                        session_dir=session_dir,
                                        agent_key=sub_entry["agent_key"],
                                        field=sub_entry["field"],
                                        session_id=session_id,
                                        attempt_id=_attempt_str,
                                        attempt_suffix=_suffix,
                                    )
                                    self._write_sidecar_meta(
                                        spath, entry=sub_entry,
                                        attempt_id=_attempt_str,
                                    )
                                    logger.info(
                                        f"[DH]  skipped sub-row "
                                        f"{spath.name} (attempt {_norm}, "
                                        f"no database row)"
                                    )
                                    written += 1
                                except OSError as exc:
                                    logger.warning(
                                        f"[DH]  failed to write sub-row "
                                        f"skip placeholder: {exc}"
                                    )
                                return
                            for idx, item in enumerate(result):
                                item_index = (
                                    idx + 1 if len(result) > 1 else None
                                )
                                try:
                                    spath = self._write_entry(
                                        session_dir=session_dir,
                                        agent_key=sub_entry["agent_key"],
                                        field=sub_entry["field"],
                                        question=item["question"],
                                        answer=item["answer"],
                                        session_id=session_id,
                                        attempt_id=_attempt_str,
                                        attempt_suffix=_suffix,
                                        item_index=item_index,
                                    )
                                    self._write_sidecar_meta(
                                        spath, entry=sub_entry,
                                        attempt_id=_attempt_str,
                                    )
                                    logger.info(
                                        f"[DH]  wrote sub-row {spath.name} "
                                        f"(attempt {_norm})"
                                    )
                                    written += 1
                                    # Phase 3C — sub-row, attempt-scoped.
                                    self._phase_3c_persist_chunk(
                                        session_id=session_id,
                                        nnn=_norm,
                                        agent_key=sub_entry["agent_key"],
                                        agents_to=list(sub_entry.get("to_agents") or []),
                                        field=sub_entry["field"],
                                        field_type=sub_entry.get("type", "Semantic"),
                                        question=item["question"],
                                        body=item["answer"],
                                        item_index=item_index,
                                        is_error=False,
                                        is_identifying=False,
                                        safety_filename=spath.name,
                                        attempt_id_by_nnn=attempt_id_by_nnn,
                                        cascaded_attempt_nnns=cascaded_attempt_nnns,
                                        db_writer_available=db_writer_available,
                                    )
                                except OSError as exc:
                                    logger.warning(
                                        f"[DH]  failed to write sub-row "
                                        f"for {sub_entry['agent_key']}/"
                                        f"{sub_entry['field']} "
                                        f"(attempt {_norm}): {exc}"
                                    )

                        # Sub-rows are batched per attempt, using the
                        # groups the planning call already decided; the
                        # same grouping is reused for every attempt.
                        # Rows whose agent this topology never built are
                        # dropped here rather than inside a batch.
                        sub_done: set[str] = set()
                        sub_unsettled: list[dict] = []
                        for sub_entry in sub_rows:
                            if sub_entry["id"] in sub_done:
                                continue
                            sub_agent_key = sub_entry["agent_key"]
                            sub_agent = orchestrator._agents_by_key.get(sub_agent_key)
                            sub_state = self.session.agent_states.get(sub_agent_key)
                            if sub_agent is None or sub_state is None:
                                logger.warning(
                                    f"[DH]  sub-row agent "
                                    f"{sub_agent_key!r} not in registry; "
                                    f"skipping for attempt {norm}."
                                )
                                sub_done.add(sub_entry["id"])
                                continue

                            sub_group = [
                                r for r in batch_group_of.get(
                                    sub_entry["id"], [sub_entry],
                                )
                                if r["id"] not in sub_done
                                and r.get("parent_id") == entry["id"]
                                and r["agent_key"] == sub_agent_key
                            ] or [sub_entry]

                            # The attempt is stated in the question the
                            # agent sees — its own reply is what pins the
                            # answer to the right design — while the
                            # FILING comes from the closure above, never
                            # from the model.
                            asked_rows = [
                                {**r, "description": (
                                    f"For {attempt_str}: "
                                    f"{r.get('description', '')}"
                                )}
                                for r in sub_group
                            ]
                            for r in sub_group:
                                sub_done.add(r["id"])

                            try:
                                self._run_batch(
                                    rows=asked_rows,
                                    agent_key=sub_agent_key,
                                    agent_system_prompt=getattr(sub_agent, "system_prompt", "") or "",
                                    agent_provider=self._interview_llm(sub_agent)[1],
                                    agent_base_llm=self._interview_llm(sub_agent)[0],
                                    agent_messages=list(sub_state.messages),
                                    on_resolved=_persist_sub,
                                )
                            except Exception as exc:  # pragma: no cover
                                logger.warning(
                                    f"[DH]  sub-row batch for "
                                    f"{sub_agent_key} (attempt {norm}) "
                                    f"raised {type(exc).__name__}: {exc}; "
                                    f"falling back to one row at a time."
                                )
                                sub_unsettled.extend(asked_rows)

                        # Per-row fallback, one attempt's worth at a time.
                        for sub_entry in sub_unsettled:
                            sub_agent = orchestrator._agents_by_key.get(
                                sub_entry["agent_key"])
                            sub_state = self.session.agent_states.get(
                                sub_entry["agent_key"])
                            if sub_agent is None or sub_state is None:
                                continue
                            logger.info(
                                f"[DH]  falling back to a single "
                                f"conversation for "
                                f"{sub_entry['agent_key']}/"
                                f"{sub_entry['field']} (attempt {norm})"
                            )
                            try:
                                self._run_batch(
                                    rows=[sub_entry],
                                    agent_key=sub_entry["agent_key"],
                                    agent_system_prompt=getattr(sub_agent, "system_prompt", "") or "",
                                    agent_provider=self._interview_llm(sub_agent)[1],
                                    agent_base_llm=self._interview_llm(sub_agent)[0],
                                    agent_messages=list(sub_state.messages),
                                    on_resolved=lambda r, res: (
                                        _persist_sub(r, None)
                                        if res == "unsettled"
                                        else _persist_sub(r, res)
                                    ),
                                )
                            except Exception as exc:  # pragma: no cover
                                logger.warning(
                                    f"[DH]  fallback sub-row conversation "
                                    f"failed: {type(exc).__name__}: {exc}"
                                )

                    i = j  # skip past the sub-rows the inner loop just handled
                    continue

                # ----- SESSION-SCOPED ROW (or QUANT) -----------------
                #
                # This row may be asked together with its neighbours.  The
                # batch is driven from whichever of its rows the loop
                # reaches FIRST; the rest are settled inside that call and
                # skipped when the loop walks over them.
                if entry["id"] in handled_ids:
                    i += 1
                    continue

                def _eligible(r: dict) -> bool:
                    """Rows this loop would itself reach and interview.

                    A planned group is computed over the WHOLE schedule,
                    so it can name rows that take another path entirely
                    (sub-rows, identifying rows) or that the loop has
                    already disposed of (a DCII row with the inspector
                    off gets an empty placeholder above).  Asking those
                    inside a batch would interview them twice.
                    """
                    return (
                        r["id"] not in handled_ids
                        and r.get("parent_id") is None
                        and r.get("scope") == "session"
                        and not (
                            r.get("requires_dcii_enabled")
                            and not dc_inspector_enabled
                        )
                    )

                group = [
                    r for r in batch_group_of.get(entry["id"], [entry])
                    if _eligible(r)
                ] or [entry]

                unsettled: list[dict] = []

                def _persist(row: dict, result) -> None:
                    """Write one settled row — entries, a skip, or neither.

                    Called the moment a row is settled rather than at the
                    end of the batch, so a crash costs the rows still
                    open, not the ones already answered.  That matches
                    the per-row path, which writes as each conversation
                    returns.
                    """
                    nonlocal written
                    if result == "unsettled":
                        unsettled.append(row)
                        return
                    handled_ids.add(row["id"])
                    r_field = row["field"]
                    r_agent = row["agent_key"]

                    if result is None:
                        # SKIPPED: keep the .txt so the session folder
                        # stays complete and auditable, write NO database
                        # row — a "nothing to report" sentence would be
                        # embedded and would then compete with real
                        # content at search time (F17).
                        try:
                            path = self._write_skipped_entry(
                                session_dir=session_dir,
                                agent_key=r_agent,
                                field=r_field,
                                session_id=session_id,
                            )
                            self._write_sidecar_meta(
                                path, entry=row, attempt_id=None,
                            )
                            logger.info(
                                f"[DH]  skipped {path.name} "
                                f"(no database row written)"
                            )
                            written += 1
                        except OSError as exc:
                            logger.warning(
                                f"[DH]  failed to write skip placeholder "
                                f"for {r_agent}/{r_field}: {exc}"
                            )
                        return

                    for idx, item in enumerate(result):
                        item_index = idx + 1 if len(result) > 1 else None
                        try:
                            path = self._write_entry(
                                session_dir=session_dir,
                                agent_key=r_agent,
                                field=r_field,
                                question=item["question"],
                                answer=item["answer"],
                                session_id=session_id,
                                attempt_id=None,
                                attempt_suffix=None,
                                item_index=item_index,
                            )
                            self._write_sidecar_meta(
                                path, entry=row, attempt_id=None,
                            )
                            logger.info(
                                f"[DH]  wrote {path.name}"
                                + (f" (item {item_index}/{len(result)})"
                                   if item_index else "")
                            )
                            written += 1
                            # Phase 3C — session-scoped row (or Quant).
                            # item_index stays as-is (None for
                            # single-pair): the schema's NULL-distinct
                            # semantics on session-scoped rows is
                            # intentional; no forcing to 1 (see W28 +
                            # chunks table NOTE).
                            self._phase_3c_persist_chunk(
                                session_id=session_id,
                                nnn=None,
                                agent_key=r_agent,
                                agents_to=list(row.get("to_agents") or []),
                                field=r_field,
                                field_type=row.get("type", "Semantic"),
                                question=item["question"],
                                body=item["answer"],
                                item_index=item_index,
                                is_error=False,
                                is_identifying=False,
                                safety_filename=path.name,
                                attempt_id_by_nnn=attempt_id_by_nnn,
                                cascaded_attempt_nnns=cascaded_attempt_nnns,
                                db_writer_available=db_writer_available,
                            )
                        except OSError as exc:
                            logger.warning(
                                f"[DH]  failed to write entry for "
                                f"{r_agent}: {exc}"
                            )

                def _write_row_error(row: dict, exc: Exception) -> None:
                    nonlocal written
                    handled_ids.add(row["id"])
                    error_msg = (
                        f"the DH conversation with {row['agent_key']} "
                        f"raised an exception: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    err_path = self._write_error_entry(
                        session_dir=session_dir,
                        agent_key=row["agent_key"],
                        field=row["field"],
                        error_message=error_msg,
                        session_id=session_id,
                        attempt_id=None,
                    )
                    self._write_sidecar_meta(
                        err_path, entry=row, attempt_id=None,
                    )
                    # Phase 3C — error rows also land in chunks
                    # (is_error=True), session-scoped.
                    self._phase_3c_persist_chunk(
                        session_id=session_id,
                        nnn=None,
                        agent_key=row["agent_key"],
                        agents_to=list(row.get("to_agents") or []),
                        field=row["field"],
                        field_type="Semantic",
                        question=None,
                        body=f"ERROR: {error_msg}",
                        item_index=None,
                        is_error=True,
                        is_identifying=False,
                        safety_filename=err_path.name,
                        attempt_id_by_nnn=attempt_id_by_nnn,
                        cascaded_attempt_nnns=cascaded_attempt_nnns,
                        db_writer_available=db_writer_available,
                    )

                if len(group) > 1:
                    logger.info(
                        f"[DH]  batch for {agent_key}: "
                        + ", ".join(r["field"] for r in group)
                    )
                try:
                    self._run_batch(
                        rows=group,
                        agent_key=agent_key,
                        agent_system_prompt=getattr(agent, "system_prompt", "") or "",
                        agent_provider=self._interview_llm(agent)[1],
                        agent_base_llm=self._interview_llm(agent)[0],
                        agent_messages=list(agent_state.messages),
                        on_resolved=_persist,
                    )
                except Exception as exc:  # pragma: no cover — defensive
                    logger.warning(
                        f"[DH]  batch with {agent_key} failed "
                        f"({type(exc).__name__}: {exc}); falling back to "
                        f"one conversation per unsettled row."
                    )
                    unsettled.extend(
                        r for r in group if r["id"] not in handled_ids
                    )

                # Per-row fallback.  A row the batch could not settle is
                # asked on its own, with its own fresh budget — the
                # pre-batching path, unchanged.  Only these rows pay for
                # it, so one difficult question cannot cost the batch.
                for row in unsettled:
                    if row["id"] in handled_ids:
                        continue
                    logger.info(
                        f"[DH]  falling back to a single conversation "
                        f"for {row['agent_key']}/{row['field']}"
                    )
                    try:
                        # A batch of ONE.  Coverage is trivial with a
                        # single label, so the mapping problem that sent
                        # the row here cannot recur; and a second failure
                        # resolves as a skip rather than recursing.
                        self._run_batch(
                            rows=[row],
                            agent_key=row["agent_key"],
                            agent_system_prompt=getattr(agent, "system_prompt", "") or "",
                            agent_provider=self._interview_llm(agent)[1],
                            agent_base_llm=self._interview_llm(agent)[0],
                            agent_messages=list(agent_state.messages),
                            on_resolved=lambda r, res: _persist(
                                r, None if res == "unsettled" else res,
                            ),
                        )
                    except Exception as exc:  # pragma: no cover — defensive
                        logger.warning(
                            f"[DH]  fallback conversation with "
                            f"{row['agent_key']} failed: {exc}"
                        )
                        _write_row_error(row, exc)
                        continue

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

            # Mirror <session_dir>/user_inputs/ to Cloudflare R2 when
            # configured.  Phase 3D (2026-06-02) dropped the ``.txt``
            # suffix from what used to be a WHOLE-session_dir scan
            # because per-agent Q+A bodies (under
            # ``<session_dir>/<agent>/<field>.txt``) live in Postgres
            # ``chunks`` only in the happy path (architecture doc
            # §3.5 + §9.6 + invariant 12).  Q+A text only reaches R2
            # via the safety folder when ``insert_chunk`` exhausts
            # its retries (handled inline by
            # ``db_writer.save_to_safety_folder``).
            #
            # BUT the user-input files written by
            # ``_collect_user_inputs`` just above — ``queries.txt``,
            # ``extracted_inputs.txt``,
            # ``images/<original>.png|.jpg|.jpeg``, and
            # ``images/<original>_note.txt`` — are NOT in Postgres
            # and DO need to reach R2.  Path-scope the mirror to the
            # ``user_inputs/`` subtree and put the full
            # ``.txt`` / ``.png`` / ``.jpg`` / ``.jpeg`` whitelist
            # back.  This both:
            #
            #   * keeps per-agent ``<agent>/<field>.txt`` bodies OUT
            #     of R2 (they live outside ``user_inputs/``); and
            #   * gets ``queries.txt``, ``extracted_inputs.txt`` and
            #     the ``_note.txt`` sidecars
            #     UP to R2 regardless of whether any images were
            #     uploaded this session or whether the DH wrote any
            #     attempts.
            #
            # Per-attempt artefacts (mesh, renders, description.txt)
            # land on R2 via the SEPARATE
            # ``upload_attempt_artefacts`` path inside
            # ``save_attempt_data``'s force-tool handler — see
            # warnings_developer.md W30 for the three R2 paths.
            #
            # Best-effort: a failure here logs a warning but never
            # breaks the local save the user just confirmed.
            try:
                from agents.shared import r2_uploader as _r2
                if _r2.is_enabled():
                    user_inputs_dir = session_dir / "user_inputs"
                    if user_inputs_dir.is_dir():
                        n_up = _r2.upload_directory(
                            user_inputs_dir,
                            remote_prefix=f"{session_id}/user_inputs/",
                            # .json = the per-image <stem>.compression.json
                            # degree sidecar (user_inputs/ holds no other json).
                            suffixes=(".txt", ".png", ".jpg", ".jpeg", ".json"),
                        )
                        logger.info(
                            f"[DH]  R2 mirror complete: {n_up} file(s) "
                            f"uploaded under prefix "
                            f"{session_id}/user_inputs/"
                        )
                    else:
                        logger.info(
                            f"[DH]  no user_inputs/ subdir at "
                            f"{user_inputs_dir.resolve()}; nothing to "
                            f"mirror this session."
                        )
                else:
                    logger.info(
                        f"[DH]  R2 not configured; skipped user_inputs/ "
                        f"mirror of {session_dir.resolve()} "
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

    # Mechanical tail clause appended to every DH question sent to an
    # agent.  Reduces the cleanup burden by asking the agent up-front
    # NOT to surface artefacts the DH would otherwise have to strip.
    # Independent of the DH's own wording so it cannot be "forgotten":
    # Option 1 in the user's design notes, layered on top of Option 2
    # (the SEMANTIC safety net in _clean_semantic_body).
    # The parameter COUNT is derived from the live parameter set rather
    # than written as a literal.  It read "17" for months after
    # impellerHeight was dropped and the set became 16 — in text
    # appended to every question the DH sends every agent.  Deriving it
    # means the same drift cannot recur the next time the DC's
    # parameter list changes.
    _AGENT_FACING_TAIL = (
        "\n\n[Reminder for your reply, from the Database Handler:\n"
        "Do not include file paths, directory names, or absolute "
        "paths of any kind (no /app/... paths, no render PNG paths, "
        "no parameters.json references, no attempt-folder slugs).  "
        f"Do not enumerate the {len(PARAMETER_NAMES)} design parameters "
        "as a value list — "
        "instead, describe the REASONING you applied (which checks, "
        "which heuristics, which trade-offs).  Do not address any "
        "other agent or the user; the chain is over and your reply "
        "is consumed only by me.]"
    )

    # ------------------------------------------------------------------
    # Batched interview
    # ------------------------------------------------------------------
    #
    # A BATCH is a group of schedule rows asked to one agent in ONE call.
    # Where the per-row path costs three LLM calls per row (write the
    # question, ask the agent, decide what to save), a batch of N costs
    # three for the whole group.
    #
    # Every DH decision here is a FORCED TOOL CALL, never prose.  The old
    # text protocol could fail invisibly — a header with markdown on it
    # became answer text, an untagged block inherited the previous
    # block's attempt — and with several rows riding on one reply those
    # failures stop being cosmetic: a mis-mapped answer is filed under
    # the wrong row, and the database will not catch it (a session-scoped
    # duplicate inserts twice, an attempt-scoped one is discarded at
    # INFO — see F59).  So the mapping is carried by short labels the
    # schema requires, and checked here before anything is written.
    # ------------------------------------------------------------------

    def _force_tool_args(
        self,
        tool_obj,
        tool_name: str,
        instruction: str,
        log_label: str,
        *,
        retries: int = 2,
    ) -> dict | None:
        """Bind ONE tool for ONE turn, force it, and return its arguments.

        Returns ``None`` when the binding fails, every attempt raises, or
        the model returns no tool call despite ``tool_choice``.  Callers
        must treat ``None`` as "fall back", never as "empty result" — the
        difference is a whole batch's worth of answers.

        The binding is LOCAL: ``self.llm`` keeps no tools, per the W18 /
        W20 invariant that a forced tool is never left bound.
        """
        try:
            bound = self.base_llm.bind_tools(
                [tool_obj], tool_choice=tool_name,
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                f"[DH]  could not bind {tool_name}: "
                f"{type(exc).__name__}: {exc}"
            )
            return None

        self.messages.append(HumanMessage(content=instruction))
        for attempt in range(1, retries + 1):
            try:
                response = invoke_with_retry(
                    bound,
                    [
                        make_system_message(
                            self.system_prompt, self.provider, phase="save",
                        )
                    ]
                    + self.messages,
                    f"{log_label}-{attempt}",
                    # Every batching tool call comes through here — the
                    # plan, each batch's questions, every save decision
                    # and its retry — so this is where most of the DH's
                    # own token spend now lives.  ``self.messages`` grows
                    # monotonically across the whole save and is never
                    # re-seeded, which makes it the ideal cached prefix:
                    # each call reads back everything the save has said
                    # so far instead of re-paying for it.  Retries within
                    # this loop re-send an identical prefix and so hit in
                    # full.
                    cache_control=history_cache_control(
                        self.provider, phase="save",
                    ),
                )
            except Exception as exc:
                logger.warning(
                    f"[DH]  {log_label} attempt {attempt} raised "
                    f"{type(exc).__name__}: {exc}"
                )
                continue
            self.messages.append(response)
            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                logger.warning(
                    f"[DH]  {log_label} attempt {attempt} returned no "
                    f"tool call despite tool_choice={tool_name}."
                )
                continue
            first = tool_calls[0]
            args = (
                first.get("args") if isinstance(first, dict)
                else getattr(first, "args", {})
            )
            return args or {}
        return None

    def _plan_batches(self, entries: list[dict]) -> dict[str, list[dict]]:
        """Decide which schedule rows are asked together.

        ONE LLM call for the whole save.  Returns ``{row_id: group}`` —
        every row maps to the group it belongs to, and a row asked alone
        maps to a group of one, so callers need no special case.

        Code decides only what is not a judgement: rows may be grouped
        solely within a CANDIDATE RUN (same agent, same scope, same
        parent — see ``batch_tools.candidate_runs``).  Everything else,
        including whether to batch at all, is the DH's call.

        Fails safe in both directions: a plan that does not validate is
        repaired by :func:`batch_tools.validate_plan` (cross-run groups
        split, omitted rows made singletons) after one retry, and a call
        that fails outright degrades to one row per group — which is
        exactly the pre-batching behaviour, so a broken planner costs
        money, never correctness.
        """
        from agents.database_handler import batch_tools as bt

        runs = bt.candidate_runs(entries)
        labels = bt.label_rows(entries, style="plan")
        label_of = {id(row): label for label, row in labels.items()}

        run_lines: list[str] = []
        for n, run in enumerate(runs, start=1):
            head = run[0]
            kind = (
                "attempt-identifying" if bt.is_identifying(head)
                else f"{head.get('scope', 'session')}-scoped"
            )
            if head.get("parent_id"):
                kind += ", sub-rows of an attempt block"
            run_lines.append(
                f"\nRUN {n} — agent: {head.get('agent_key')}, {kind}"
                + ("  [only one row; nothing to decide]" if len(run) == 1 else "")
            )
            for row in run:
                run_lines.append(
                    f"  {label_of[id(row)]}  {row.get('field')}"
                    f"\n        {(row.get('description') or '').strip()}"
                )

        instruction = (
            "BATCH PLANNING TURN.\n\n"
            "Below is this session's whole question schedule, split into "
            "runs.  Decide which rows are asked to their agent TOGETHER, "
            "in one call, and which are asked alone.\n"
            + "\n".join(run_lines)
            + "\n\nGroup only within a run — rows in different runs cannot "
            "share a call.  Batching a group of N saves 2 x (N-1) LLM "
            "calls, so group wherever one combined answer would be as "
            "good as separate ones, and leave apart only what genuinely "
            "would suffer.  Questions that pull in OPPOSITE directions "
            "(a best case and a worst case, a success and a failure) "
            "belong apart: one reply covering both tends to blur them.\n\n"
            "Call submit_batch_plan now.  Every label above must appear "
            "in exactly one group."
        )

        args = self._force_tool_args(
            bt.submit_batch_plan, bt.SUBMIT_BATCH_PLAN_TOOL_NAME,
            instruction, "DH-plan",
        )
        if args is None:
            logger.warning(
                "[DH]  batch planning failed; asking every row on its "
                "own (the pre-batching behaviour)."
            )
            groups = bt.no_batching_plan(runs)
        else:
            groups, problems = bt.validate_plan(
                args.get("batches") or [], runs, labels,
            )
            if problems:
                logger.warning(
                    "[DH]  batch plan needed fixing: "
                    + "  ".join(problems)
                )
                retry = self._force_tool_args(
                    bt.submit_batch_plan, bt.SUBMIT_BATCH_PLAN_TOOL_NAME,
                    "Your plan had problems:\n  - "
                    + "\n  - ".join(problems)
                    + "\n\nCall submit_batch_plan again, fixing them.  "
                    "Group only within a run; cover every label exactly "
                    "once.",
                    "DH-plan-retry", retries=1,
                )
                if retry is not None:
                    groups2, problems2 = bt.validate_plan(
                        retry.get("batches") or [], runs, labels,
                    )
                    if len(problems2) <= len(problems):
                        groups, problems = groups2, problems2
                if problems:
                    logger.warning(
                        "[DH]  proceeding with the repaired plan "
                        "(remaining: " + "  ".join(problems) + ")"
                    )

        batched = sum(1 for g in groups if len(g) > 1)
        logger.info(
            f"[DH]  batch plan: {len(entries)} row(s) -> {len(groups)} "
            f"group(s) ({batched} batched); "
            f"{sum(2 * (len(g) - 1) for g in groups)} fewer LLM calls "
            f"than asking each row alone"
        )
        return {
            row["id"]: group for group in groups for row in group
        }

    def _batch_questions(
        self, agent_key: str, labelled: dict[str, dict],
    ) -> dict[str, str]:
        """One question per row in the batch, keyed by label.

        Falls back to the row's own schedule description for any label
        the DH omits, so a partial response costs wording quality rather
        than a missing question.
        """
        from agents.database_handler import batch_tools as bt

        rows_block = "\n".join(
            f"  {label}  {row.get('field')} "
            f"[{row.get('type', 'Semantic')}]"
            f"\n        {(row.get('description') or '').strip()}"
            for label, row in labelled.items()
        )
        args = self._force_tool_args(
            bt.submit_questions, bt.SUBMIT_QUESTIONS_TOOL_NAME,
            "QUESTION-WRITING TURN.\n\n"
            f"Target agent: {agent_key}\n"
            f"You are about to ask it these {len(labelled)} database "
            f"field(s) in ONE message:\n\n{rows_block}\n\n"
            "Write one question per label.  Stay faithful to each "
            "field's original intent; you MAY adapt the wording using "
            "what earlier agents have told you this save, as long as "
            "that does not drift the question away from its field.  "
            "Each question is stored verbatim beside its answer, so "
            "write each one self-contained.\n\n"
            "Call submit_questions now — one entry per label, no extras.",
            "DH-questions",
        )

        out: dict[str, str] = {}
        for item in (args or {}).get("questions") or []:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            question = str(item.get("question") or "").strip()
            if label in labelled and question:
                out.setdefault(label, question)

        for label, row in labelled.items():
            if label not in out:
                logger.warning(
                    f"[DH]  no question written for {label} "
                    f"({row.get('field')}); using its schedule "
                    f"description."
                )
                out[label] = (
                    f"For this session, please describe: "
                    f"{row.get('field')} — "
                    f"{(row.get('description') or '').strip()}"
                )
        return out

    @staticmethod
    def _clean_saves(
        labelled: dict[str, dict], saves: dict[str, list[dict]],
    ) -> dict[str, list[dict]]:
        """Run the defensive cleanup over what the DH chose to save.

        The DH's prompt tells it to strip file paths, routing-tool JSON
        wrappers and literal ``\\n`` escapes itself.  In practice models
        reliably echo the wrapper they saw in the agent's reply, which is
        why this backstop exists on the per-row path — a structured tool
        call changes how the text is DELIVERED, not what the model puts
        inside the strings, so the same backstop is still needed here.

        Semantic rows only: Quantitative bodies are stored verbatim, and
        cleaning one could silently alter a number or a unit.
        """
        out: dict[str, list[dict]] = {}
        for label, entries in saves.items():
            row = labelled.get(label) or {}
            if (row.get("type") or "Semantic").strip().lower() != "semantic":
                out[label] = entries
                continue
            cleaned: list[dict] = []
            for e in entries:
                cleaned.append({
                    **e,
                    "question": _clean_semantic_body(e["question"]) or e["question"],
                    "answer": _clean_semantic_body(e["answer"]) or e["answer"],
                })
            out[label] = cleaned
        return out

    def _shorten_over_cap(
        self,
        agent_key: str,
        labelled: dict[str, dict],
        saves: dict[str, list[dict]],
    ) -> dict[str, list[dict]]:
        """Bring each saved pair under the per-pair token cap.

        Each pair becomes its own file and its own embedding vector, so
        the cap applies per pair, not per row and not per batch.

        Unlike the per-row path this re-emits by LABEL, not by position.
        The positional merge there is a live hazard: it pairs the
        rewritten list against the original index-by-index, so a count
        drift silently moves an answer onto another row (and its
        ``max(len, len)`` bound can append an empty pair that gets
        written as an empty file plus a database row).  Keyed
        re-emission cannot do either.

        Applies only to Semantic rows; Quantitative bodies are saved
        verbatim and uncapped.
        """
        from agents.database_handler import batch_tools as bt

        cap = self.max_response_tokens
        over: list[str] = []
        for label, entries in saves.items():
            if (labelled[label].get("type") or "Semantic").strip().lower() != "semantic":
                continue
            for e in entries:
                if count_tokens(e["question"]) + count_tokens(e["answer"]) > cap:
                    over.append(label)
                    break
        if not over:
            return saves

        logger.warning(
            f"[DH]  {len(over)} row(s) over the {cap}-token per-pair "
            f"cap for {agent_key}: {', '.join(over)}; asking for "
            f"shorter versions."
        )
        detail = "\n".join(
            f"  {label} ({labelled[label].get('field')}): "
            + ", ".join(
                str(count_tokens(e["question"]) + count_tokens(e["answer"]))
                + " tokens"
                for e in saves[label]
            )
            for label in over
        )
        args = self._force_tool_args(
            bt.submit_batch, bt.SUBMIT_BATCH_TOOL_NAME,
            "TOKEN-CAP COMPRESSION TURN.\n\n"
            "Each saved question+answer pair becomes its own database "
            f"entry, read independently by the embedding model, so each "
            f"must stay under {cap} cl100k_base tokens ON ITS OWN "
            f"(prefer under 600).  These are over:\n\n{detail}\n\n"
            "Call submit_batch again with ONLY those labels in 'saves', "
            "shortened, keeping the same number of entries per label "
            "and the same attempt tags.  Leave 'followups' and 'skips' "
            "empty.  Apply the embedding-friendly rules from your "
            "system prompt.",
            "DH-compress-batch", retries=1,
        )
        if args is None:
            logger.warning(
                f"[DH]  compression produced nothing for {agent_key}; "
                f"saving the over-cap pairs as they are."
            )
            return saves

        shorter, _f, _s, _p = bt.read_batch_result(args, set(over))
        out = dict(saves)
        for label, new_entries in shorter.items():
            old_entries = saves.get(label) or []
            if len(new_entries) != len(old_entries):
                logger.warning(
                    f"[DH]  compression for {label} returned "
                    f"{len(new_entries)} entr(ies) for {len(old_entries)}; "
                    f"keeping the originals rather than guessing which "
                    f"is which."
                )
                continue
            merged = []
            for old, new in zip(old_entries, new_entries):
                old_n = count_tokens(old["question"]) + count_tokens(old["answer"])
                new_n = count_tokens(new["question"]) + count_tokens(new["answer"])
                keep = new if new_n < old_n else old
                if new_n >= old_n:
                    logger.warning(
                        f"[DH]  compression made {label} longer; "
                        f"keeping the original."
                    )
                # A re-emit that drops the attempt tag keeps the original's.
                keep = dict(keep)
                keep["attempt"] = new.get("attempt") or old.get("attempt")
                merged.append(keep)
            out[label] = merged
        return out

    def _run_batch(
        self,
        *,
        rows: list[dict],
        agent_key: str,
        agent_system_prompt: str,
        agent_provider: str,
        agent_base_llm,
        agent_messages: list,
        on_resolved,
    ) -> None:
        """Interview one agent about a whole batch of rows.

        Calls ``on_resolved(row, entries)`` the moment a row is settled —
        ``entries`` is a list of ``{question, answer, attempt}`` to save,
        or ``None`` when the DH skipped the row.

        Resolving as we go rather than at the end is deliberate.  The
        per-row path writes each entry as soon as its conversation
        returns, so a crash costs one row; accumulating a whole batch
        would cost the batch.  A row is settled exactly once and never
        re-asked, so its pairs are final when the cap check runs on them.
        """
        from agents.database_handler import batch_tools as bt

        labelled = bt.label_rows(rows, style="batch")
        convo_buffer, n_img = _without_image_blocks(agent_messages)
        if n_img:
            logger.info(
                f"[DH]  stripped {n_img} image block(s) from the "
                f"{agent_key} interview buffer ({len(rows)} row(s))"
            )

        questions = self._batch_questions(agent_key, labelled)
        open_labels = set(labelled)
        pending = dict(questions)

        for round_idx in range(MAX_DH_TURNS_PER_FIELD):
            asked = "\n\n".join(
                f"[{label}] {pending[label]}"
                for label in labelled if label in pending
            )
            answer = self._ask_agent(
                agent_key=agent_key,
                agent_system_prompt=agent_system_prompt,
                agent_provider=agent_provider,
                agent_base_llm=agent_base_llm,
                convo_buffer=convo_buffer,
                field=", ".join(
                    labelled[label].get("field", "?") for label in pending
                ),
                question=(
                    "Please answer each of the following, labelled as "
                    "shown.  Address every one — they are separate "
                    "database fields.\n\n" + asked
                    if len(pending) > 1 else asked
                ),
            )
            self.messages.append(HumanMessage(content=(
                f"Agent: {agent_key}\n"
                f"Fields in this batch: "
                + ", ".join(
                    f"{label}={labelled[label].get('field')}"
                    for label in pending
                )
                + f"\nMy questions:\n{asked}\n\n"
                f"{agent_key}'s reply: {answer}"
            )))

            args = self._force_tool_args(
                bt.submit_batch, bt.SUBMIT_BATCH_TOOL_NAME,
                self._batch_decision_instruction(
                    agent_key, labelled, open_labels,
                    final_round=False,
                    rounds_left=MAX_DH_TURNS_PER_FIELD - round_idx - 1,
                ),
                "DH-batch",
            )
            if args is None:
                logger.warning(
                    f"[DH]  no batch decision for {agent_key}; falling "
                    f"back to one conversation per remaining row."
                )
                break

            saves, followups, skipped, problems = bt.read_batch_result(
                args, open_labels,
            )
            if problems:
                logger.warning(
                    "[DH]  batch decision problems: " + "  ".join(problems)
                )
                retry = self._force_tool_args(
                    bt.submit_batch, bt.SUBMIT_BATCH_TOOL_NAME,
                    "Your submit_batch call had problems:\n  - "
                    + "\n  - ".join(problems)
                    + "\n\nCall submit_batch again.  Every one of these "
                    "labels must appear in exactly one list: "
                    + ", ".join(sorted(open_labels)),
                    "DH-batch-retry", retries=1,
                )
                if retry is not None:
                    s2, f2, k2, p2 = bt.read_batch_result(retry, open_labels)
                    # Keep whichever attempt SETTLED more rows.  Counting
                    # problem strings instead would be wrong: a single
                    # "not covered at all" problem can name any number of
                    # labels, so a retry that rescued one row but still
                    # missed another scores equal to the original and
                    # would be thrown away along with the row it saved.
                    if len(set(s2) | set(f2) | k2) > len(
                        set(saves) | set(followups) | skipped
                    ):
                        saves, followups, skipped, problems = s2, f2, k2, p2

            saves = self._clean_saves(labelled, saves)
            saves = self._shorten_over_cap(agent_key, labelled, saves)

            for label in list(saves):
                on_resolved(labelled[label], saves[label])
                open_labels.discard(label)
            for label in sorted(skipped):
                on_resolved(labelled[label], None)
                open_labels.discard(label)

            if not open_labels:
                return
            pending = {
                label: q for label, q in followups.items()
                if label in open_labels
            }
            if not pending:
                # Nothing was saved, skipped OR followed up for these
                # rows — the coverage check could not be satisfied even
                # after its retry.  They fall to the caller's per-row
                # fallback below rather than being guessed at.
                break
        else:
            # The round cap ran out with rows still open, which means the
            # DH kept asking follow-ups.  ONE more decision turn — no
            # agent call, so it costs a single DH call — where saving or
            # skipping are the only options left.  Deliberately NOT the
            # per-row fallback: the cap was reached by the DH's own
            # choice to keep digging, and re-running each row with a
            # fresh budget would reward exactly that.
            if open_labels:
                logger.warning(
                    f"[DH]  round cap reached for {agent_key} with "
                    f"{len(open_labels)} row(s) open; forcing a final "
                    f"save-or-skip."
                )
                final_args = self._force_tool_args(
                    bt.submit_batch, bt.SUBMIT_BATCH_TOOL_NAME,
                    self._batch_decision_instruction(
                        agent_key, labelled, open_labels,
                        final_round=True, rounds_left=0,
                    ),
                    "DH-batch-final", retries=1,
                )
                saves, _f, skipped, _p = (
                    bt.read_batch_result(final_args, open_labels)
                    if final_args is not None else ({}, {}, set(), [])
                )
                saves = self._clean_saves(labelled, saves)
                saves = self._shorten_over_cap(agent_key, labelled, saves)
                for label in list(saves):
                    on_resolved(labelled[label], saves[label])
                    open_labels.discard(label)
                # Anything the DH still would not settle is skipped: it
                # had its rounds and its forced turn, and a skip leaves a
                # visible artefact rather than nothing at all.
                for label in sorted(open_labels):
                    logger.warning(
                        f"[DH]  {labelled[label].get('field')!r} was "
                        f"never settled; recording it as skipped."
                    )
                    on_resolved(labelled[label], None)
                open_labels.clear()
            return

        # Reached only via ``break`` — the DH's decision could not be
        # obtained or could not be made to cover these rows.  Report them
        # by name; the caller re-runs each on its own.
        for label in sorted(open_labels):
            logger.warning(
                f"[DH]  {labelled[label].get('field')!r} was not settled "
                f"in its batch; it will be asked on its own."
            )
            on_resolved(labelled[label], "unsettled")

    def _batch_decision_instruction(
        self,
        agent_key: str,
        labelled: dict[str, dict],
        open_labels: set[str],
        final_round: bool,
        rounds_left: int,
    ) -> str:
        """The prompt for one ``submit_batch`` turn."""
        rows_block = "\n".join(
            f"  {label}  {labelled[label].get('field')} "
            f"[{labelled[label].get('type', 'Semantic')}]"
            for label in sorted(open_labels)
        )
        cap_line = (
            f"Semantic entries: keep each question + answer together "
            f"under {self.max_response_tokens} cl100k_base tokens "
            f"(prefer under 600), with the question about one sentence.  "
            f"Quantitative entries: save the data verbatim, uncapped, "
            f"and do not paraphrase numbers or units."
        )
        if final_round:
            tail = (
                "This is the LAST round — 'followups' is not available.  "
                "Put every label in 'saves' or 'skips'."
            )
        else:
            tail = (
                f"Follow-up rounds remaining after this one: "
                f"{rounds_left}.  Use 'followups' only where another "
                f"question would genuinely change what you save."
            )
        return (
            "SAVE DECISION TURN.\n\n"
            f"Target agent: {agent_key}\n"
            f"Still open in this batch:\n{rows_block}\n\n"
            f"{cap_line}\n\n"
            "Skip a row rather than saving a 'nothing to report' "
            "sentence — an empty negation adds nothing to the database "
            "and competes with real content at search time.  Split one "
            "row into several 'saves' entries when the reply genuinely "
            "contains several distinct items worth finding separately.\n\n"
            f"{tail}\n\n"
            "Call submit_batch now.  Every label above must appear in "
            "exactly one of the three lists."
        )

    # ------------------------------------------------------------------
    # Force-tool variant for IDENTIFYING attempt-specific questions
    # ------------------------------------------------------------------
    #
    # Identifying attempt-specific rows are top-level rows with
    # ``scope="attempt"`` and ``parent_id=None``.  They pin down WHICH
    # design attempt this block of questions is about.  The DH is
    # forced to call ``save_attempt_data`` after Agent A's first
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
        *,
        # Phase 3C — caches propagated through to
        # _run_force_tool_phase.  Owned by populate_database; we
        # only forward them.  Without these in the signature, the
        # _run_force_tool_phase call below NameError'd because the
        # kwargs reference names not in this method's scope (see
        # fix commit after Phase 3C / 10E + 10F).
        attempt_id_by_nnn: dict[str, int],
        cascaded_attempt_nnns: set[str],
        db_writer_available: bool,
    ) -> tuple[
        list[tuple[str | None, str, str]],
        str,
        list[str],
    ]:
        """Interview an agent about an attempt-IDENTIFYING row.

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
        convo_buffer, _n_img = _without_image_blocks(agent_messages)
        if _n_img:
            logger.info(
                f"[DH]  stripped {_n_img} image block(s) from the "
                f"{agent_key} interview buffer ({field})"
            )
        # The identifying row is a batch of ONE, so it uses the same
        # tools as every other row — ``submit_questions`` to write the
        # question, ``submit_batch`` to decide what to store.  What makes
        # it different is step 3: the attempt ids must be BOUND before
        # anything attempt-scoped can be written, which is why it is
        # never grouped with other rows.
        from agents.database_handler import batch_tools as bt

        row = {
            "id": "identifying", "field": field, "agent_key": agent_key,
            "description": description, "type": field_type,
        }
        labelled = {"A": row}

        # Step 1 — DH writes the question.
        first_question = self._batch_questions(agent_key, labelled)["A"]
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
            attempt_id_by_nnn=attempt_id_by_nnn,
            cascaded_attempt_nnns=cascaded_attempt_nnns,
            db_writer_available=db_writer_available,
        )
        if not resolved_attempt_ids:
            logger.info(
                f"[DH]  force-tool resolved 'no attempts' for "
                f"{agent_key}/{field} (reason={reason}); the whole "
                f"block will be dropped."
            )
            return [], first_answer, []

        # Step 4 — the save decision, through ``submit_batch``.  The
        # force-tool ToolMessages are already in self.messages, so the DH
        # can see exactly which attempts were resolved.
        #
        # Each entry carries its attempt EXPLICITLY, in its own field.
        # The retired text protocol inferred it from an ``ATTEMPT:``
        # header, which was sticky across blocks and fragile to any
        # markdown on the tag line — so an untagged block silently
        # inherited the previous attempt's id, and attempt A's answer
        # could be written into attempt B's file, sidecar and database
        # row with nothing marking it wrong (F59).  A per-entry field
        # cannot leak between entries.
        attempts_line = ", ".join(resolved_attempt_ids)
        args = self._force_tool_args(
            bt.submit_batch, bt.SUBMIT_BATCH_TOOL_NAME,
            "SAVE DECISION TURN (attempt-identifying).\n\n"
            f"Target agent: {agent_key}\n"
            f"Field: {field}  [label A]\n"
            f"Attempt(s) just bound: {attempts_line}\n\n"
            + (
                "Emit ONE 'saves' entry per attempt, each with label A "
                "and its own 'attempt' set to that attempt — the entries "
                "are told apart by that field alone, so an entry without "
                "it cannot be filed.\n\n"
                if len(resolved_attempt_ids) > 1 else
                "Emit a 'saves' entry with label A and 'attempt' set to "
                f"{attempts_line}.\n\n"
            )
            + "Do not repeat the attempt id inside the question or the "
            "answer: the saved file already carries it in its name and "
            "in its header, so repeating it spends embedding budget on "
            "nothing.  Write as if the reader already knows which "
            "attempt is meant.\n\n"
            f"Keep each question + answer under {self.max_response_tokens} "
            "cl100k_base tokens (prefer under 600).  Leave 'followups' "
            "and 'skips' empty unless there is genuinely nothing to "
            "store for this row.",
            "DH-identifying-save",
        )

        if args is None:
            logger.warning(
                f"[DH]  no save decision for the identifying row "
                f"{agent_key}/{field}; the attempts are bound but this "
                f"row gets no entry of its own."
            )
            return [], first_answer, resolved_attempt_ids

        saves, _followups, skipped, problems = bt.read_batch_result(
            args, {"A"},
        )
        if problems:
            logger.warning(
                "[DH]  identifying save problems: " + "  ".join(problems)
            )
        if "A" in skipped:
            logger.info(
                f"[DH]  the DH skipped the identifying row "
                f"{agent_key}/{field} itself; its attempts stay bound "
                f"and its sub-rows still run."
            )
            return [], first_answer, resolved_attempt_ids

        saves = self._clean_saves(labelled, saves)
        saves = self._shorten_over_cap(agent_key, labelled, saves)

        triples = [
            (e.get("attempt"), e["question"], e["answer"])
            for e in saves.get("A", [])
        ]
        return triples, first_answer, resolved_attempt_ids

    def _run_force_tool_phase(
        self,
        *,
        agent_key: str,
        field: str,
        agent_last_answer: str,
        session_id: str,
        session_start_ts: float | None,
        attempt_id_by_nnn: dict[str, int],
        cascaded_attempt_nnns: set[str],
        db_writer_available: bool,
    ) -> tuple[list[str], str]:
        """Force the DH to call save_attempt_data; up to 3 retries.

        Returns ``(resolved_attempt_ids, reason)`` where
        ``resolved_attempt_ids`` is the list of normalised
        identifiers (each in ``"attempt NNN"`` form) the DH passed —
        possibly empty when the DH explicitly chose "no attempt".
        ``reason`` is one of ``"ok"`` / ``"explicit-none"`` /
        ``"max-retries"`` / ``"bind-failed"``.

        On a successful resolve for N>=1 attempts, for each resolved
        attempt the method:

          1. (Phase 3C) Calls ``db_writer.upsert_attempt`` +
             ``db_writer.upsert_attempt_parameters`` to persist the
             attempt's data to Postgres, caching the returned
             ``BIGSERIAL attempt_id`` in ``attempt_id_by_nnn``.
             Postgres-side failures log ERROR + add the
             attempt_label to ``cascaded_attempt_nnns`` (subsequent
             attempt-scoped Q+A then routes to the R2 safety folder
             with ``cascade_source`` set).  When
             ``db_writer_available`` is False, this step is skipped
             entirely.
          2. Uploads the 6 whitelisted artefact files to R2
             (existing behaviour, independent of step 1 per
             Q-3C-2 = A).

        The ToolMessage carrying both steps' outcomes is returned to
        the DH so its next turn sees the uploaded / persisted state
        in conversation context.
        """
        import json as _json
        from agents.database_handler.dh_tools import (
            save_attempt_data,
            SAVE_ATTEMPT_DATA_TOOL_NAME,
        )

        try:
            dh_with_tool = self.llm.bind_tools(
                [save_attempt_data],
                tool_choice=SAVE_ATTEMPT_DATA_TOOL_NAME,
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                f"[DH]  could not bind save_attempt_data to the "
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
                "You MUST now call `save_attempt_data` exactly "
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
                # Every retry re-sends the SAME prefix, so attempts 2+
                # read it back at cache price instead of re-paying for
                # the whole accumulated interview.
                response = invoke_with_retry(
                    dh_with_tool,
                    [
                        make_system_message(
                            self.system_prompt, self.provider, phase="save"
                        )
                    ]
                    + self.messages,
                    f"DH-force-tool-{attempt}",
                    cache_control=history_cache_control(
                        self.provider, phase="save"
                    ),
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
                            "Call save_attempt_data now."
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

            # ----- Phase 3C: Postgres-side per-attempt persistence ------
            # Best-effort: a Postgres failure (or any other exception
            # below) logs an ERROR and marks the attempt as cascaded —
            # but does NOT abort the R2 upload that follows.  See
            # architecture doc §9.5 + Q-3C-2 = A.
            # When db_writer_available is False (no DATABASE_URL set),
            # this whole block is a no-op — attempts are NOT marked
            # cascaded, just not persisted.  Q-3C-B3 = A.
            postgres_upsert_results: dict[str, dict] = {}
            if db_writer_available:
                for nnn in normalised:
                    folder, _ = _resolve_attempt_folder(
                        nnn, attempts_root, session_start_ts,
                    )
                    attempt_label = folder.name
                    try:
                        params_path = folder / "parameters.json"
                        parameters_json = _json.loads(
                            params_path.read_text(encoding="utf-8")
                        )
                        has_geometry = any(folder.glob("*.obj"))
                        has_renders  = any(folder.glob("render_*.png"))
                        # Long-format scalar mirror: numeric-only per
                        # v5 dc_attempt_parameters.raw_value DOUBLE
                        # PRECISION NOT NULL.  Non-numeric values are
                        # preserved verbatim on dc_attempts.
                        # parameters_json (JSONB).  T19 covers the
                        # future text-param mirror in schema v6.
                        long_params: dict[str, float] = {}
                        for k, v in parameters_json.items():
                            try:
                                long_params[k] = float(v)
                            except (TypeError, ValueError):
                                continue
                        bigserial_id = db_writer.upsert_attempt(
                            session_id=session_id,
                            attempt_label=attempt_label,
                            schema_version=self.session.schema_version,
                            parameters_json=parameters_json,
                            has_geometry=has_geometry,
                            has_renders=has_renders,
                        )
                        db_writer.upsert_attempt_parameters(
                            attempt_id=bigserial_id,
                            parameters=long_params,
                        )
                        # Cache keyed by NNN (e.g. "001"), NOT by
                        # folder name — per-Q+A integration sites in
                        # populate_database have `nnn` available via
                        # _normalise_attempt_input, not the folder.
                        attempt_id_by_nnn[nnn] = bigserial_id
                        postgres_upsert_results[nnn] = {
                            "ok": True,
                            "attempt_id": bigserial_id,
                            "has_geometry": has_geometry,
                            "has_renders": has_renders,
                            "n_scalar_params": len(long_params),
                        }
                        logger.info(
                            f"[DH]  Phase 3C upsert_attempt OK "
                            f"attempt_label={attempt_label} → "
                            f"attempt_id={bigserial_id}, "
                            f"has_geometry={has_geometry}, "
                            f"has_renders={has_renders}, "
                            f"{len(long_params)} scalar param rows."
                        )
                    except Exception as exc:  # broad: any FS/JSON/Postgres failure
                        logger.error(
                            f"[DH]  Phase 3C upsert_attempt FAILED "
                            f"for attempt_label={attempt_label}: "
                            f"{type(exc).__name__}: {exc}.  Marking "
                            f"attempt as cascaded — subsequent "
                            f"attempt-scoped Q+A will route to the "
                            f"R2 safety folder."
                        )
                        # NNN-keyed too (see attempt_id_by_nnn comment
                        # above).
                        cascaded_attempt_nnns.add(nnn)
                        postgres_upsert_results[nnn] = {
                            "ok": False,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
            else:
                logger.info(
                    "[DH]  Phase 3C upsert_attempt SKIPPED for all "
                    "attempts (postgres_pool.is_enabled() == False)."
                )
            # ----- End Phase 3C block; existing R2 upload follows -------

            # All entries resolved → upload each attempt's artefacts.
            uploaded_per_attempt: dict[str, dict] = {}
            try:
                from agents.shared import r2_uploader as _r2
                from agents.shared import attempt_renders as _renders
                for nnn in normalised:
                    folder, _ = _resolve_attempt_folder(
                        nnn, attempts_root, session_start_ts,
                    )
                    # folder is guaranteed non-None by the validation
                    # above; ``status`` ignored here (already logged).
                    # Phase 5A: pass the Postgres BIGSERIAL attempt_id
                    # so the R2 key encodes both NNN and the global id
                    # (folder shape becomes ``attempts/<NNN>__<global_id>/``).
                    # ``attempt_id_by_nnn.get(nnn)`` returns None for
                    # cascaded attempts where the upsert failed — the
                    # uploader falls back to the pre-5A key shape with
                    # a warning, which is acceptable for the rare
                    # cascade case.
                    # Complete the attempt's render set BEFORE archiving
                    # it.  Saving is irreversible: whatever is missing here
                    # is missing from that attempt for good.  Best-effort by
                    # construction -- ensure_renders never raises, so a dead
                    # geometry backend costs renders, never the save (W1).
                    _rep = _renders.ensure_renders(folder)
                    _renders.log_report(folder, _rep)
                    uploaded, missing = _r2.upload_attempt_artefacts(
                        folder,
                        session_id=session_id,
                        attempt_id=nnn,
                        global_attempt_id=attempt_id_by_nnn.get(nnn),
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
        # Caching matters MOST here.  convo_buffer is re-seeded from the
        # agent's full in-session history for every one of its SCHEDULE
        # fields (8 for the UII, 6 for the Planner), so without a cache
        # that whole history is re-billed at full price once per field.
        # Nothing mutates agent_state.messages during the save — list()
        # copies it and the appends below land on the copy — so the
        # repeated prefix is byte-stable and hits every time after the
        # first.  Both markers take the AGENT's provider, not the DH's:
        # this call invokes agent_base_llm, which may be a different
        # provider entirely.
        response = invoke_with_retry(
            agent_base_llm,
            [
                make_system_message(
                    agent_system_prompt, agent_provider, phase="save"
                )
            ]
            + convo_buffer,
            f"DH<-{agent_key}",
            cache_control=history_cache_control(agent_provider, phase="save"),
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

    def _write_skipped_entry(
        self,
        session_dir: Path,
        agent_key: str,
        field: str,
        *,
        session_id: str = "",
        attempt_id: str | None = None,
        attempt_suffix: str | None = None,
    ) -> Path:
        """Write the ``.txt`` for a row the DH deliberately SKIPPED.

        A skip means "this session produced nothing worth storing for
        this row" — the agent had no problem to report, no clarification
        to describe, nothing new.  Today such a row is still saved, as a
        canonical negation sentence ("no problem occurred this session"),
        which is then embedded and competes with real content at search
        time; F17 asks for exactly the opposite.

        So a skip keeps the FILE and drops the DATABASE ROW.  The file
        keeps the per-session folder complete and auditable — you can see
        the DH considered the row — while the corpus stays free of empty
        negations.  The caller is responsible for NOT calling
        ``_phase_3c_persist_chunk`` for a skipped row.

        Distinct from :meth:`_write_empty_entry`, which writes a
        zero-byte file for an agent that was not running at all (a DCII
        row with the inspector disabled).  Both would otherwise be
        indistinguishable on disk, and they mean different things:
        "nothing to say" versus "nobody was there to ask".
        """
        path = self._entry_path(
            session_dir, agent_key, field, attempt_suffix=attempt_suffix,
        )
        attempt_line = attempt_id if attempt_id else "(session-scope)"
        path.write_text(
            f"--- Session ID ---\n{session_id}\n\n"
            f"--- Attempt ID ---\n{attempt_line}\n\n"
            f"--- Field ---\n{field}\n\n"
            "SKIPPED: the Database Handler found nothing worth saving "
            "for this field this session.  No database row was written.\n",
            encoding="utf-8",
        )
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

    def _phase_3c_persist_chunk(
        self,
        *,
        session_id: str,
        nnn: str | None,
        agent_key: str,
        agents_to: list[str],
        field: str,
        field_type: str,
        question: str | None,
        body: str,
        item_index: int | None,
        is_error: bool,
        is_identifying: bool,
        safety_filename: str,
        attempt_id_by_nnn: dict[str, int],
        cascaded_attempt_nnns: set[str],
        db_writer_available: bool,
    ) -> None:
        """Phase 3C: persist one chunks row, with cascade fast-path.

        Called from every successful ``_write_entry`` /
        ``_write_error_entry`` call site in ``populate_database`` —
        IMMEDIATELY AFTER the local ``.txt`` was written.  See
        architecture doc §9.5.

        Behaviour summary
        -----------------
        - When ``db_writer_available`` is False → no-op (Postgres
          disabled for this session).
        - Session-scoped row (``nnn is None``) → straight
          ``insert_chunk`` with ``attempt_id=None``; ``item_index``
          passed through unchanged (the schema's NULL-distinct
          semantics on session-scoped single-pair rows is
          intentional — see chunks table NOTE).
        - Attempt-scoped row (``nnn`` given):
            * If ``nnn`` is cascaded OR not in ``attempt_id_by_nnn``
              → CASCADE FAST-PATH: skip ``insert_chunk`` and call
              ``db_writer.save_to_safety_folder`` directly with
              ``cascade_source`` set.  Architecture doc §3.5.5.
            * Otherwise → ``insert_chunk`` with the cached BIGSERIAL.
              When ``item_index`` is ``None``, it is PROMOTED to ``1``
              so the chunks UNIQUE constraint engages (architecture
              doc §9.5 + warnings_developer.md W28).
        - SAFETY outcome on an identifying-Q row → add ``nnn`` to
          ``cascaded_attempt_nnns`` so subsequent sub-rows fast-path
          (architecture doc §9.5 / §3.5.5).
        """
        if not db_writer_available:
            return

        # ----- Determine FK target + safety scope ---------------
        if nnn is None:
            attempt_id_pk: int | None = None
            safety_scope = "session"
            attempt_id_label_for_safety = "session-generic"
            effective_item_index = item_index  # no forcing for session-scoped
            is_cascaded = False
        else:
            safety_scope = f"attempt_{nnn}"
            attempt_id_label_for_safety = nnn
            attempt_id_pk = attempt_id_by_nnn.get(nnn)
            is_cascaded = (
                nnn in cascaded_attempt_nnns or attempt_id_pk is None
            )
            # Promote item_index=None → 1 for attempt-scoped rows so
            # the chunks UNIQUE constraint engages (W28).
            effective_item_index = 1 if item_index is None else item_index

        # ----- Cascade fast-path --------------------------------
        if is_cascaded:
            effective_agents_to = (
                list(agents_to) if agents_to
                else list(db_writer.DEFAULT_AGENTS_TO_ACL)
            )
            try:
                db_writer.save_to_safety_folder(
                    session_id=session_id,
                    scope=safety_scope,
                    filename=safety_filename,
                    field=field,
                    question=question or "",
                    answer=body,
                    agents_to=effective_agents_to,
                    field_type=field_type,
                    attempt_id_label=attempt_id_label_for_safety,
                    retry_count=0,
                    max_retries=0,
                    last_db_error=(
                        f"(cascade — identifying-Q or upsert_attempt "
                        f"for attempt_{nnn} failed earlier; this row "
                        f"routed straight to safety with no retries)"
                    ),
                    cascade_source=(
                        f"identifying-Q or upsert_attempt for "
                        f"attempt_{nnn} failed (see earlier logs in "
                        f"this populate_database run)"
                    ),
                )
                logger.warning(
                    f"[DH]  Phase 3C cascade fast-path: routed "
                    f"{agent_key}/{field!r} (attempt_{nnn}) to R2 "
                    f"safety folder."
                )
            except Exception as exc:  # pragma: no cover — defensive
                logger.error(
                    f"[DH]  Phase 3C cascade fast-path FAILED for "
                    f"{agent_key}/{field!r} (attempt_{nnn}): "
                    f"{type(exc).__name__}: {exc}.  Q+A may be lost."
                )
            return

        # ----- Normal insert_chunk ------------------------------
        try:
            outcome = db_writer.insert_chunk(
                session_id=session_id,
                attempt_id=attempt_id_pk,
                agent_from=agent_key,
                agents_to=list(agents_to),
                field=field,
                field_type=field_type,
                question=question,
                body=body,
                item_index=effective_item_index,
                is_error=is_error,
                is_empty=False,
                dc_name=self.session.dc_name,
                safety_scope=safety_scope,
                safety_filename=safety_filename,
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.error(
                f"[DH]  Phase 3C insert_chunk raised for "
                f"{agent_key}/{field!r}: "
                f"{type(exc).__name__}: {exc}.  Q+A NOT in Postgres."
            )
            return

        if outcome == db_writer.InsertOutcome.SAFETY:
            logger.warning(
                f"[DH]  Phase 3C insert_chunk returned SAFETY for "
                f"{agent_key}/{field!r}; data preserved in R2 safety "
                f"folder, not in Postgres."
            )
            if is_identifying and nnn is not None:
                cascaded_attempt_nnns.add(nnn)
                logger.warning(
                    f"[DH]  Phase 3C: identifying-Q for attempt_{nnn} "
                    f"went to SAFETY; cascading subsequent sub-rows."
                )
        # INSERTED / SKIPPED_UNIQUE: db_writer already logged INFO.

    def _collect_user_inputs(self, session_dir: Path) -> int:
        """Snapshot the session's user inputs into the database tree.

        Copies into ``<session_dir>/user_inputs/``:

        * ``queries.txt`` — the full turn-by-turn collection of user
          text inputs.  Source is ``inputs/user_query.txt``, which the
          dispatcher APPENDS to on every ``/api/turn`` call
          (``agents/dispatch.py:save_user_input``), so it already
          carries every turn the user submitted this session with a
          ``--- [YYYY-MM-DD HH:MM:SS] ---`` header before each entry.
        * ``extracted_inputs.txt`` — the User Input Inspector's
          structured extraction of those inputs (QUANTITATIVE INPUTS /
          QUALITATIVE DESCRIPTIONS / DESIGN INTENT).  Source is
          ``inputs/extracted_inputs.txt``, which the UII OVERWRITES on
          each re-extraction, so this copy is its final state as of
          save time.  Absent when the UII never ran.
        * ``images/<original_name>`` — every reference image the user
          uploaded via the Image Inputs view, plus its matching
          ``<name>_note.txt`` description sidecar.  Original filenames
          are preserved so the image / note pairing is obvious.

        The local copies live alongside the per-agent ``.txt`` files
        the DH already writes locally.  Per Phase 3D those per-agent
        files stay in Postgres only and are NOT mirrored to R2;
        the subsequent R2 mirror in :meth:`populate_database` is
        scoped narrowly to ``<session_dir>/user_inputs/`` and
        uploads its contents (``queries.txt``,
        ``extracted_inputs.txt``, reference images + ``_note.txt``
        sidecars) via the
        ``.txt`` / ``.png`` / ``.jpg`` / ``.jpeg`` whitelist.  The
        original ``inputs/`` directory is left intact — End
        Session's archival sweep moves it under
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

        # 2. The UII's structured extraction of those inputs.
        src_extraction = USER_INPUTS_DIR / "extracted_inputs.txt"
        if src_extraction.is_file():
            try:
                shutil.copyfile(
                    src_extraction, target / "extracted_inputs.txt"
                )
                written += 1
                logger.info(
                    f"[DH]  copied {src_extraction.name} → "
                    f"user_inputs/{src_extraction.name}"
                )
            except OSError as exc:
                logger.warning(
                    f"[DH]  failed to copy extracted_inputs.txt: {exc}"
                )
        else:
            logger.info(
                f"[DH]  no extracted_inputs.txt at "
                f"{src_extraction.resolve()}; the User Input Inspector "
                f"never wrote an extraction this session."
            )

        # 3. Every reference image + its _note.txt sidecar.
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

