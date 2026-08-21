"""Tool bound to the Orchestrator ONLY during the end-of-session feedback round.

The Orchestrator is otherwise purely a router (its permanent tool set is
the ``call_<agent>`` routing tools plus ``calculate`` / ``list_attempts``
/ ``read_attempt`` / ``new_attempt`` / ``read_agent_history``).  At end-of-session-with-save the
user supplies a satisfaction marker plus two free-text fields; the
Orchestrator is given THIS tool in a single per-turn binding (mirroring
the DH's force-tool W18 pattern) and must use it ONCE to return a list
of per-agent decisions.

The tool's argument is a JSON list of dispatch dicts, one per CHAIN
agent the Orchestrator considered.  For every dispatch with ``send=true``
the system appends a ``HumanMessage(content=message, name="orchestrator")``
to that agent's history — so when the Database Handler interviews each
agent post-session, the relevant user feedback is part of the agent's
own conversation context.

Like ``save_attempt_data`` in ``agents/database_handler/dh_tools.py``,
the body of this tool is a no-op stub — the real logic lives in the
Orchestrator's feedback-round helper, where it has live access to
``session.agent_states`` and the per-agent registry.
"""

from __future__ import annotations

from langchain_core.tools import tool


# Public name used in:
#   * the per-turn force-tool path
#     (``tool_choice="submit_feedback_dispatch"``)
#   * the Role-4 prompt rule (so the Orchestrator knows what to call)
#   * the ToolMessage round-trip back to the Orchestrator
SUBMIT_FEEDBACK_DISPATCH_TOOL_NAME = "submit_feedback_dispatch"


def feedback_envelope() -> str:
    """Text prepended to a forwarded feedback message — or "" for most systems.

    In the 7-agent REDUCED variant the "## End-of-session feedback message
    (read-only)" section is deleted from the chain agents' prompts, because the
    message it describes exists ONLY when the user ends a session WITH SAVE:
    in every session that does not save — most of them — that explanation is
    dead text carried by eight prompts for a message that never arrives.  The
    instruction travels with the message instead, so it costs nothing until
    there is something to explain and it arrives attached to the thing it
    explains.

    Systems that KEEP the prompt section must not also get the envelope, or
    they are told the same thing twice.  So the text is a variant fragment and
    this returns "" whenever the active topology + variant has not written one
    — which is every topology today except 7-agent reduced.

    Resolved through ``prompts._topology_override`` rather than an explicit
    ``PROMPT_VARIANT`` test: that machinery already exists, is already covered
    by smoke_test_prompt_variant, and keeps this module free of a second place
    in the codebase that branches on the variant.  There is deliberately NO
    shared original — an absent override is the correct signal for "no
    envelope", exactly as an absent prompt override means "use the standard
    text".

    Read fresh per call, never cached: the Sessions Queue switches settings
    between runs inside one process.

    Defined here because all three hubs (Orchestrator, Conductor, Architect)
    already import this module for the dispatch tool, and three copies of one
    sentence is how they drift apart.
    """
    from agents.shared.prompts import (
        GENERIC_FRAGMENTS_DIR,
        _topology_override,
    )

    # Fall back to the SHARED fragment, exactly as every other reader does
    # (``_read_generic_fragment`` is ``_topology_override(...) or SHARED``).
    # Without that fallback this returned "" whenever no topology override
    # existed -- which became the NORMAL case the moment the reduced variant
    # was promoted and its directory removed, silently emptying the envelope.
    rel = "feedback_envelope.md"
    path = (_topology_override("prompt_fragments/" + rel)
            or GENERIC_FRAGMENTS_DIR / rel)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").rstrip() + "\n\n"


@tool(SUBMIT_FEEDBACK_DISPATCH_TOOL_NAME)
def submit_feedback_dispatch(dispatches: list[dict]) -> str:
    """Distribute the user's end-of-session feedback to the chain agents.

    Call this tool EXACTLY ONCE with a JSON list of dispatch objects —
    one per chain agent you considered (Receptionist, Planner, UII,
    DCIC, DCII, Tool Caller, DCOI; DCII is skipped automatically when
    the DC Input Inspector is disabled).

    Each dispatch object MUST have these three keys:

    * ``agent_key`` (string) — one of:
        ``"receptionist"``, ``"planner"``, ``"user_input_inspector"``,
        ``"dc_input_creator"``, ``"dc_input_inspector"``,
        ``"tool_caller"``, ``"dc_output_inspector"``.
    * ``send`` (bool) — ``true`` when the user's feedback contains
        material relevant to THIS agent's scope (e.g. the Receptionist
        owns presentation; the DCIC owns parameter choices; the DCOI
        owns visual / QC verdicts); ``false`` when nothing applies.
    * ``message`` (string) — when ``send=true``, the EXACT text to
        forward to that agent.  It must contain ONLY the parts of the
        user's feedback that pertain to this agent's responsibilities;
        leave out the parts that belong to OTHER agents.  When
        ``send=false`` the field is ignored; pass an empty string.

    Hard rules:

    1. Do NOT paraphrase or invent commentary.  Use the user's own
       words; you may quote, condense, or omit, but never rewrite the
       sentiment.
    2. Do NOT duplicate the same line of feedback to multiple agents.
       Split: every distinct concern belongs to ONE agent — whichever
       owns the part of the process the concern is about.
    3. Most agents on most sessions will receive ``send=false`` — that
       is the correct default when the user gave no specific feedback
       in your area.
    4. You MUST emit one dispatch per agent in scope.  Do not skip
       agents from the list — surface them with ``send=false`` instead.

    Return value (this stub) is ignored by the caller — the real
    persistence happens in the Orchestrator's helper which intercepts
    the tool call.
    """
    # No-op body — the system intercepts the call and runs the real
    # logic (per-agent message append + session_states mirror).
    return (
        f"(no-op stub — the system handles submit_feedback_dispatch; "
        f"caller passed {len(dispatches)} dispatch(es))"
    )
