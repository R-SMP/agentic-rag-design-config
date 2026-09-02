"""Topology-5 copies of every per-agent TOOL table.

Each name here shadows the identically-named table in the shared tool module,
via :func:`agents.shared.topology.overlay_value`.  Shadowing REPLACES rather
than merges: these tables are the whole truth for topology 5, which is what
makes the two topologies independent.  Editing a description in the shared
module can no longer reach topology 5, and editing one here can never reach
topology 7.

**Every value below started as a byte-identical copy of its 7-agent
original.**  That is deliberate — the rebuild's first milestone was "topology 5
is identical to topology 7", and divergence is applied one reviewed edit at a
time afterwards.  Entries for agents topology 5 does not build (the
Orchestrator, the DC Input Inspector) are dropped, since nothing can ever look
them up.

Not here, and why:

* the DC-params PRIMER text — that is a FILE, so it forks through the prompt
  tree instead (``agents/5agent/dc_config/dc_params_primer_text*_5agents.txt``)
  and ``dc_primer._text_path`` resolves it with ``_topology_override``.  The
  primer IMAGE is deliberately still shared: it is a binary asset, identical
  in both topologies, and duplicating it would double a ~1k-token payload for
  no editorial gain.
* the step budgets — UI-tunable, so ``workflow_settings/settings.py`` §28.
* the per-agent model defaults — ``workflow_settings/llm_defaults.py``, whose
  ``model_for()`` is the single funnel every consumer already goes through.
"""

# ---------------------------------------------------------------------------
# dc_params_tool — the "when to call me" clause of ``dc_params_list``
# ---------------------------------------------------------------------------

USE_DEFAULT = (
    "Call this when you need to see which parameters exist and what they "
    "represent (e.g. before judging a directive that names one, or when "
    "wording a parameter-level plan).  Takes NO arguments."
)

USE_BY_AGENT = {
    # The Planner directs in words and never picks values, so it rarely needs
    # this at all — and the printed ranges are exactly what tempted it to pick
    # from them (runs ID278 / ID279).
    #
    # ⚠ In topology 7 this entry is DEAD CODE: planner.py binds the module
    # default rather than build_dc_params_list("planner").  Under topology 5
    # the Planner is the hub, and whether it should hold the tailored wording
    # at all is an open question (plan O10).  Copied verbatim so the two
    # topologies start identical either way.
    "planner": (
        "Reference only: which parameters exist and what each one means.  You "
        "rarely need it — describe the change you want in plain words and let "
        "the DC Input Creator pick the parameter and the value.  Takes NO "
        "arguments."
    ),
    # The Receptionist never validates numbers; it answers and clarifies.
    "receptionist": (
        "Call this to answer a user question about what the system accepts "
        "as input — which parameters exist, what they mean, what values are "
        "allowed — or to clarify a value the user gave.  Takes NO arguments."
    ),
}


# ---------------------------------------------------------------------------
# user_inputs_tool — where ``view_images`` says absolute paths come from
# ---------------------------------------------------------------------------

VIEW_IMAGES_PATHS_DEFAULT = (
    "from ``list_input_files``, or relayed in the hand-off"
)

VIEW_IMAGES_PATHS_BY_AGENT = {
    # Runs before any render exists and binds no ``read_attempts``.
    "user_input_inspector":
        "from the image listing ``read_user_inputs`` returns",
    # The ``dc_input_inspector`` entry of the 7-agent table is NOT copied:
    # topology 5 never builds that agent.
    #
    # Its usual case is this cycle's renders, named in the Tool Caller's
    # hand-off; the extraction's ``USEFUL INPUT IMAGES`` section is NOT a
    # path source -- it names images by filename and gives crop boxes.
    "dc_output_inspector":
        "from the hand-off's ``Render images:`` line, from ``read_attempts`` "
        "for a PRIOR attempt's renders, or from the image listing "
        "``read_user_inputs`` returns",
}

# ---------------------------------------------------------------------------
# user_inputs_tool — the per-agent ``read_user_inputs`` documentation
#
# In the 7-agent tree these are four module constants, each imported by name
# and passed as ``doc=`` at the agent's own call site — not a table, so
# ``overlay_value`` could not reach them.  ``user_inputs_tool`` now also
# exposes ``READ_INPUTS_DOC_BY_AGENT`` + ``read_inputs_doc(agent_key)``, and
# the four call sites go through it; the constants stay exported so nothing
# else breaks.
#
# The DC Input Inspector's wording is NOT copied — topology 5 never builds
# that agent.
# ---------------------------------------------------------------------------

READ_INPUTS_DOC_UII = (
    "Read a user-inputs directory: TEXT plus a LIST of its images (it does "
    "NOT load the images themselves).\n\n"
    "Pass the absolute path of the inputs directory supplied in your hand-off "
    "under the ``Input directory:`` label (do NOT guess).  The output is a "
    "summary plus the concatenated contents of all text/JSON files — "
    "including every image's ``_note.txt`` — followed by a list of the "
    "reference images present with their paths.  To actually SEE an image "
    "(and get its OCR-recognised text: dimension callouts, labels), call "
    "``view_images`` with the path(s) you need."
)

READ_INPUTS_DOC_DCOI = (
    "Read the user-inputs directory: TEXT plus a LIST of its images (it does "
    "NOT load the images themselves).\n\n"
    "Pass the absolute path of the user-inputs directory — the folder holding "
    "``user_query.txt`` and ``extracted_inputs.txt``, i.e. the parent "
    "directory of the extraction path named in your comparison-source "
    "instructions (do NOT guess a path).  The output is a summary plus the "
    "concatenated contents of all text/JSON files — the user's queries and "
    "every image's ``_note.txt`` — followed by a list of the reference images "
    "present with their paths.  To actually SEE an image, call "
    "``view_images`` with the path(s) you need."
)

READ_INPUTS_DOC_PLANNER = (
    "Read the user-inputs directory: TEXT plus a LIST of its images (it "
    "does NOT load the images themselves).\n\n"
    "Pass the absolute path of the user-inputs directory — the folder "
    "holding ``user_query.txt`` and ``extracted_inputs.txt``.  Your own "
    "prompt states it; if a hand-off instead names an ``Extracted inputs "
    "file:``, it is that file's parent directory (do NOT guess a path).  "
    "The output is a summary plus the "
    "concatenated contents of all text/JSON files — the user's queries, the "
    "current extraction and every image's ``_note.txt`` — followed by a "
    "list of the reference images present with their paths."
)

READ_INPUTS_DOC_BY_AGENT = {
    "user_input_inspector": READ_INPUTS_DOC_UII,
    "dc_output_inspector":  READ_INPUTS_DOC_DCOI,
    "planner":              READ_INPUTS_DOC_PLANNER,
}

# Historic default for any agent without an entry — the UII's wording, which
# is what ``build_read_user_inputs``'s default argument has always been.
READ_INPUTS_DOC_DEFAULT = READ_INPUTS_DOC_UII

# ---------------------------------------------------------------------------
# history_tool — the ``read_agent_history`` description                  (X-01)
#
# The shared string advertises eight valid agents, two of which topology 5
# never builds.  Asking for ``dc_input_inspector`` can only return "Error:
# unknown agent" — a burned step — and ``orchestrator`` resolves only because
# Planner5._AGENT_KEY_ALIASES maps it onto the hub.  Both the Receptionist and
# the Planner hold this tool here.
#
# Byte-identical to the shared text except the valid-agents list.
# ---------------------------------------------------------------------------

READ_AGENT_HISTORY_DESCRIPTION = (
    "Read another agent's message history to answer questions from "
    "prior pipeline runs without re-running anything.\n\n"
    "Parameters:\n"
    "  agent_name (str): Which agent's history to read.  Accepts "
    "human-readable names ('DC Output Inspector', 'Tool Caller') or "
    "snake_case keys ('dc_output_inspector', 'tool_caller').  Valid "
    "agents: planner, user_input_inspector, dc_input_creator, "
    "dc_output_inspector, tool_caller, receptionist.\n"
    "  last_n (int, optional): Return only the last N messages.  Omit "
    "for the full history.\n\n"
    "Returns a formatted transcript (tool calls, tool results, message "
    "content) or an error string if the name is unknown / no history "
    "has been recorded yet."
)


# ---------------------------------------------------------------------------
# routing_tools — the ``call_<agent>`` descriptions                      (X-02)
#
# SHADOWS the shared table rather than merging into it, per the contract in
# topology.py: an overlay is the whole truth for its topology.  Every entry is
# byte-identical to the shared one EXCEPT ``call_planner``.
#
# ``call_planner`` is the one that had to change.  In topology 7 it is the
# Orchestrator's FORWARD edge to a chain agent, and the shared wording says so.
# Here it is the RETURN edge for four different agents, and the retired
# ``call_orchestrator`` entry — which carried the "when to use me" clause —
# went with the Orchestrator.  The clause is not restored verbatim: its
# "when the incoming instruction told you to report back" half is text the
# owner struck in O-09.
#
# Keyed by tool NAME, not by (caller, target), so this wording reaches all
# four callers.  Only the six tools topology 5 actually builds are listed;
# build_routing_tool falls back to a generic description for anything else,
# which nothing here can reach.
# ---------------------------------------------------------------------------

TOOL_DESCRIPTIONS: dict = {
    "call_planner": (
        "Hand control to the Planner — the hub that plans, routes and "
        "approves.  The ``message`` argument IS the hand-off text it will "
        "see — write it as free-form prose.  Use this when your step is "
        "complete, to CLARIFY when its directive was ambiguous, or to hand "
        "back a problem you cannot resolve yourself; it is the single point "
        "the chain returns to."
    ),
    "call_user_input_inspector": (
        "Call the User Input Inspector.  The ``message`` argument IS "
        "the hand-off text the UII will see — write it as free-form "
        "prose."
    ),
    "call_dc_input_creator": (
        "Call the DC Input Creator.  The ``message`` argument IS the "
        "hand-off text the DCIC will see — write it as free-form prose."
    ),
    "call_tool_caller": (
        "Call the Tool Caller.  The ``message`` argument IS the hand-"
        "off text the Tool Caller will see — write it as free-form "
        "prose."
    ),
    "call_dc_output_inspector": (
        "Call the DC Output Inspector.  The ``message`` argument IS "
        "the hand-off text the DC Output Inspector will see.  Include "
        "the full paths of any rendered images that the Inspector "
        "should analyse, under a 'Render images:' label."
    ),
    "call_receptionist": (
        "Hand a user-facing result to the Receptionist, which composes "
        "and delivers the final message to the user.  Pass a technical "
        "summary — the Receptionist composes the actual wording."
    ),
}


# ---------------------------------------------------------------------------
# feedback_tool — the ``submit_feedback_dispatch`` description           (F18)
#
# Topology 5 builds neither the Orchestrator nor the DC Input Inspector, so the
# shared roster names two agents that are not here and offers
# ``"dc_input_inspector"`` as a legal agent_key.  The hub is also excluded from
# its own target set (planner5.py), so ``"planner"`` is not a key either.
#
# langchain DEDENTS a docstring when it becomes a description, so this string
# carries no leading indentation either — the two must match in shape.
# ---------------------------------------------------------------------------

SUBMIT_FEEDBACK_DISPATCH_DOC = """\
Distribute the user's end-of-session feedback to the chain agents.

Call this tool EXACTLY ONCE with a JSON list of dispatch objects — one
per agent in the target list supplied in your instructions.

Each dispatch object MUST have these three keys:

* ``agent_key`` (string) — one of:
    ``"receptionist"``, ``"user_input_inspector"``,
    ``"dc_input_creator"``, ``"tool_caller"``,
    ``"dc_output_inspector"``.
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
4. You MUST emit one dispatch per agent in the target list.  Do not
   skip agents — surface them with ``send=false`` instead.
5. You are the splitter, never a recipient: you are not in the target
   list, so feedback about planning, recovery or final approval has no
   inbox this session.  Leave it out rather than routing it elsewhere.

Return value (this stub) is ignored by the caller — the real
persistence happens in the hub's helper which intercepts the tool call."""
