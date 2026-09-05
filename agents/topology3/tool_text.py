"""Topology-3 copies of every per-agent TOOL table.

Each name here shadows the identically-named table in the shared tool module,
via :func:`agents.shared.topology.overlay_value`.  Shadowing REPLACES rather
than merges: these tables are the whole truth for topology 3, which is what
makes the topologies independent.  Editing a description in the shared module
can no longer reach topology 3, and editing one here can never reach 5 or 7.

**Every value below is either copied VERBATIM from ``agents/topology5``, or
derived from topology 3's roster.**  Nothing here is newly authored prose:
``smoke_test_topology3_tool_text.py`` asserts the verbatim half really is
byte-identical to its topology-5 source, so a transcription slip fails loudly
instead of quietly becoming a different instruction.

The three shapes a value can take, and why:

* **carried over unchanged** — the Planner and the Receptionist do the same
  job here as in topology 5, so their entries are exact copies;
* **superset wins** — where the two merged parents both had an entry and one
  strictly CONTAINS the other, the containing one is the union.  That is a
  copy, not a rewrite;
* **roster-derived** — a description that ENUMERATES agents or tool names is a
  statement of fact about the topology, so it is regenerated from topology 3's
  roster.  Leaving these alone is what makes a model burn a step calling an
  agent that does not exist.

Not here, and why:

* the DC-params PRIMER text — that is a FILE, so it forks through the prompt
  tree (``agents/3agent/dc_config/dc_params_primer_text*_3agents.txt``) and
  ``dc_primer._text_path`` resolves it with ``_topology_override``;
* the step budgets — UI-tunable, so ``workflow_settings/settings.py`` §28;
* the per-agent model defaults — ``workflow_settings/llm_defaults.py``, whose
  ``model_for()`` is the single funnel every consumer already goes through.

⚠ **ONE GENUINE MERGE IS DELIBERATELY ABSENT** — see
``READ_INPUTS_DOC_BY_AGENT`` below.
"""

# ---------------------------------------------------------------------------
# dc_params_tool — the "when to call me" clause of ``dc_params_list``
#
# Both entries carried over unchanged: topology 3 builds the same Planner and
# the same Receptionist, doing the same jobs.
# ---------------------------------------------------------------------------

USE_DEFAULT = (
    "Call this when you need to see which parameters exist and what they "
    "represent (e.g. before judging a directive that names one, or when "
    "wording a parameter-level plan).  Takes NO arguments."
)

USE_BY_AGENT = {
    "planner": (
        "Reference only: which parameters exist and what each one means.  You "
        "rarely need it — describe the change you want in plain words and let "
        "the DC Input Creator pick the parameter and the value.  Takes NO "
        "arguments."
    ),
    "receptionist": (
        "Call this to answer a user question about what the system accepts "
        "as input — which parameters exist, what they mean, what values are "
        "allowed — or to clarify a value the user gave.  Takes NO arguments."
    ),
}


# ---------------------------------------------------------------------------
# user_inputs_tool — where ``view_images`` says absolute paths come from
#
# SUPERSET WINS.  Topology 5 gave the UII "from the image listing
# ``read_user_inputs`` returns" and the DCOI a longer clause that ENDS with
# that same phrase.  The Requirements Analyst merges both agents, so the
# DCOI's text is already the union of the two and is copied verbatim rather
# than rewritten.
#
# The Design Engineer has no entry because it binds no image tool at all --
# neither of its parents did.
# ---------------------------------------------------------------------------

VIEW_IMAGES_PATHS_DEFAULT = (
    "from ``list_input_files``, or relayed in the hand-off"
)

VIEW_IMAGES_PATHS_BY_AGENT = {
    "requirements_analyst":
        "from the hand-off's ``Render images:`` line, from ``read_attempts`` "
        "for a PRIOR attempt's renders, or from the image listing "
        "``read_user_inputs`` returns",
}

# ---------------------------------------------------------------------------
# user_inputs_tool — the per-agent ``read_user_inputs`` documentation
#
# ⚠ THE REQUIREMENTS ANALYST IS DELIBERATELY ABSENT FROM THIS TABLE, and that
# absence is a decision rather than an oversight.
#
# Its two parents' docs differ in the one thing that matters -- HOW to find the
# directory.  The UII is told to take the path "supplied in your hand-off under
# the ``Input directory:`` label"; the DCOI is told it is "the folder holding
# ``user_query.txt`` and ``extracted_inputs.txt``, i.e. the parent directory of
# the extraction path named in your comparison-source instructions".  Neither
# is a superset of the other, and the merged agent genuinely needs BOTH routes:
# it gets an ``Input directory:`` label when the Planner sends it new user
# material, and comparison-source instructions when it is judging a render.
#
# Writing the union is authoring new instruction text, which is the owner's
# call, so it is left to the prompt stage.  Omitting the key makes
# ``read_inputs_doc`` fall through to ``READ_INPUTS_DOC_DEFAULT`` -- the UII's
# wording, which is EXACTLY what topology 3 serves today with no overlay at
# all.  So this file changes nothing here, on purpose, rather than guessing.
# ---------------------------------------------------------------------------

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
    "planner": READ_INPUTS_DOC_PLANNER,
}


# ---------------------------------------------------------------------------
# history_tool — the ``read_agent_history`` description
#
# ROSTER-DERIVED.  The shared string advertises eight valid agents and the
# topology-5 one six; topology 3 builds four.  Asking for an agent this
# topology does not build can only return "Error: unknown agent" -- a burned
# step.  Byte-identical to topology 5's except the valid-agents list.
#
# The merged-away names still RESOLVE (``Planner3._AGENT_KEY_ALIASES`` maps
# ``dcic`` / ``tool caller`` onto the Design Engineer and ``uii`` / ``dcoi``
# onto the Requirements Analyst), so a carried-over habit still gets an answer
# -- they are simply not advertised here.
# ---------------------------------------------------------------------------

READ_AGENT_HISTORY_DESCRIPTION = (
    "Read another agent's message history to answer questions from "
    "prior pipeline runs without re-running anything.\n\n"
    "Parameters:\n"
    "  agent_name (str): Which agent's history to read.  Accepts "
    "human-readable names ('Design Engineer', 'Requirements Analyst') or "
    "snake_case keys ('design_engineer', 'requirements_analyst').  Valid "
    "agents: planner, design_engineer, requirements_analyst, "
    "receptionist.\n"
    "  last_n (int, optional): Return only the last N messages.  Omit "
    "for the full history.\n\n"
    "Returns a formatted transcript (tool calls, tool results, message "
    "content) or an error string if the name is unknown / no history "
    "has been recorded yet."
)


# ---------------------------------------------------------------------------
# routing_tools — the ``call_<agent>`` descriptions
#
# SHADOWS the shared table rather than merging into it, per the contract in
# topology.py: an overlay is the whole truth for its topology.  Only the four
# tools topology 3 actually builds are listed; ``build_routing_tool`` falls
# back to a generic description for anything else, which nothing here can
# reach.
#
# ``call_planner`` and ``call_receptionist`` are byte-identical to topology
# 5's -- the hub is the same agent doing the same job, and the Receptionist is
# unchanged.  The two merged agents' descriptions are the ones already written
# into the shared table when their keys were registered, moved here so a later
# edit to either cannot cross topologies.
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
    "call_design_engineer": (
        "Call the Design Engineer.  The ``message`` argument IS the "
        "hand-off text it will see — write it as free-form prose.  It "
        "authors the complete parameter set AND runs the generation / "
        "render tools itself, so state the qualitative direction you "
        "want rather than concrete numbers."
    ),
    "call_requirements_analyst": (
        "Call the Requirements Analyst.  The ``message`` argument IS "
        "the hand-off text it will see — write it as free-form prose.  "
        "It owns the requirements at both ends: it derives them from "
        "the user's material and judges the output against them, so "
        "include the full paths of any rendered images it should "
        "analyse, under a 'Render images:' label."
    ),
    "call_receptionist": (
        "Hand a user-facing result to the Receptionist, which composes "
        "and delivers the final message to the user.  Pass a technical "
        "summary — the Receptionist composes the actual wording."
    ),
}


# ---------------------------------------------------------------------------
# feedback_tool — the ``submit_feedback_dispatch`` description
#
# ROSTER-DERIVED, same as the history tool.  The hub is excluded from its own
# target set (``planner3.py``), so ``"planner"`` is not a legal key here
# either; what remains is the Receptionist and the two merged agents.
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
    ``"receptionist"``, ``"design_engineer"``,
    ``"requirements_analyst"``.
* ``send`` (bool) — ``true`` when the user's feedback contains
    material relevant to THIS agent's scope (e.g. the Receptionist
    owns presentation; the Design Engineer owns parameter choices
    and generation; the Requirements Analyst owns what the request
    asked for and whether the render met it); ``false`` when nothing
    applies.
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
