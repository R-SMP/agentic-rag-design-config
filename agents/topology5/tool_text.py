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
    "holding ``user_query.txt`` and ``extracted_inputs.txt``; when your "
    "hand-off names an ``Extracted inputs file:``, it is that file's parent "
    "directory (do NOT guess a path).  The output is a summary plus the "
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
