"""Centralised step / hop caps for every agent and the dispatcher.

Single source of truth for every ``MAX_*`` constant that previously
lived inside individual agent modules.  Tuning any of these values
only requires editing this one file.

Each cap controls how many LLM turns (or, for the dispatcher,
inter-agent hops) the corresponding loop is allowed before it bails
out with an error / escalation.  Raising a cap costs more tokens
and (sometimes) money but reduces premature step-limit
escalations; lowering it cuts cost but increases the chance that
genuine multi-step reasoning is cut short.

When tuning, remember that EVERY tool call inside an agent's
``run()`` consumes one LLM turn — including the routing tool that
terminates the run.  So an agent that needs to call N utility tools
plus one routing tool needs at least N+1 steps in its budget, and
in practice 1–2 more for the LLM's intermediate "thinking" turns
where it produces text without a tool call.
"""

# ---------------------------------------------------------------------------
# Per-agent caps — number of LLM turns inside one ``agent.run(message)``
# call.  When the cap is hit the agent returns an error AgentHop to the
# Orchestrator instead of looping forever.
# ---------------------------------------------------------------------------

MAX_RECEPTIONIST_STEPS = 10
"""Receptionist's ``_run_llm_loop``.  The Receptionist typically does
zero or one utility-tool call (``read_agent_history``) and then either
replies as text or invokes ``call_orchestrator``.  Ten turns is
already comfortable for that pattern."""

MAX_PLANNER_STEPS = 20
"""Planner's ``run()``.  Used both for Role 1 (kickoff) and Role 2
(recovery planning).  Recovery turns may call ``read_user_queries``
and ``read_agent_history`` before producing the routing call, so the
budget needs ~3-4 utility calls plus the routing tool."""

MAX_UII_STEPS = 10
"""User Input Inspector's ``run()``.  Standard flow is
``read_user_inputs`` → ``write_extraction`` → routing call (3 turns).
Extra slack covers the post-image-loading user-input tools
(``list_input_files`` / ``read_image_notes`` / ``read_input_text`` /
``view_images``) and the occasional ``calculate``."""

MAX_DCIC_STEPS = 50
"""DC Input Creator's ``run()``.  Standard flow is
``read_extracted_inputs`` → ``new_attempt`` (for a new generation) →
``write_parameters`` → routing call (3-4 turns).  Reference-matching
runs may additionally invoke ``list_input_files`` /
``read_image_notes`` / ``view_images``, which can push the
turn count up materially when the LLM also needs intermediate
``calculate`` calls."""

MAX_DCII_STEPS = 50
"""DC Input Inspector's ``run()``.  Standard flow is
``read_parameters`` (often parallel-called with
``read_extracted_inputs``) → ``calculate`` → routing call (3 turns).
Extra slack covers cycles where DCII consults user reference images
to judge appropriateness."""

MAX_TC_STEPS = 15
"""Tool Caller's ``run()``.  Higher than the others because the
generation pipeline is sequential: ``read_parameters`` →
``generate_and_render_propeller`` (builds the mesh AND renders it in one
call) → routing call, with potential ``calculate`` calls between, plus
the LLM sometimes inserts intermediate text turns."""

MAX_DCOI_STEPS = 15
"""DC Output Inspector's ``run()``.  Standard flow is
``view_images`` → routing call (2 turns).  Extra slack
covers reference-image comparison cycles
(``list_input_files`` / ``read_image_notes`` /
``view_images``) and looking up prior attempts via
``list_attempts`` / ``read_attempt``."""

MAX_DH_STEPS = 10
"""Database Handler's per-question turn budget.  The DH runs once per
saved session, post-mortem.  For each (agent, question) pair it
formulates a question (one LLM turn), sends it to the target agent,
receives the answer, then writes the result to disk.  No tools are
bound to the DH for now, so the cap mostly guards against runaway
loops if a future revision adds tools."""

MAX_DH_TURNS_PER_FIELD = 6
"""Cap on consecutive question/answer rounds the DH may have inside a
single conversation about ONE database field with one agent.  Each
round is one DH question and one agent answer; the cap therefore
bounds at most ``MAX_DH_TURNS_PER_FIELD`` LLM calls to the agent's
base_llm + the same number of decision turns on the DH side.  When the
cap is reached the DH stops asking and writes whatever it has."""


# ---------------------------------------------------------------------------
# Orchestrator + dispatcher caps
# ---------------------------------------------------------------------------

MAX_ORCHESTRATOR_STEPS = 60
"""Maximum number of times the dispatcher is allowed to RE-ENTER
the Orchestrator's ``run()`` during a single user turn.  Each
re-entry corresponds to one routing decision the Orchestrator has
to make (kickoff, every escalation hand-back, every Planner reply,
etc.).  When this cap is hit the dispatcher calls
``_surface_limit_to_user("max Orchestrator visits")`` and the
Receptionist composes a polite "the workflow stopped" message."""

MAX_ORCH_INNER_STEPS = 6
"""Maximum number of LLM turns inside ONE ``Orchestrator.run()``
invocation.  Lets the Orchestrator chain a couple of utility calls
(e.g. ``new_attempt`` to mint an attempt path) before invoking its
final routing tool.  Kept tight because the Orchestrator should
relay, not deliberate."""


# ---------------------------------------------------------------------------
# Conductor + Creator caps (5-agent topology)
#
# Unlike every cap above, these are USER-TUNABLE from the Workflow
# Settings UI (section 27 of ``workflow_settings/settings.py``) rather
# than fixed here.  Neither merged agent can inherit a parent's budget
# — each does strictly MORE per turn than either agent it replaces —
# and the right figure is only really learnable from real runs, so the
# values live where they can be adjusted without a code change.
#
# Read at import, like the rest of this module.  Changing them in the
# UI takes effect on the next process start.
# ---------------------------------------------------------------------------

from workflow_settings import settings as _ws

MAX_CONDUCTOR_STEPS = _ws.MAX_CONDUCTOR_STEPS
"""LLM turns allowed inside ONE ``Conductor.run()`` invocation.
Defaults to the Planner's 20, NOT the Orchestrator's 6: the latter was
deliberately tight because the Orchestrator should "relay, not
deliberate", but the Conductor does both and its deliberating half is
what needs the room.  Tunable — see settings.py §27."""

MAX_CONDUCTOR_VISITS = _ws.MAX_CONDUCTOR_VISITS
"""How many times the dispatcher may RE-ENTER the Conductor during a
single user turn — the ``MAX_ORCHESTRATOR_STEPS`` analogue.  Defaults
above the Orchestrator's 60 because the Conductor absorbs the Planner:
a planning turn used to happen INSIDE the Planner and cost the hub
nothing, whereas here every plan, re-plan and approval is itself a
re-entry.  Tunable — see settings.py §27."""

MAX_CREATOR_STEPS = _ws.MAX_CREATOR_STEPS
"""LLM turns allowed inside ONE ``Creator.run()`` invocation.  Defaults
above either parent (DCIC 50 to author, DCII 50 to inspect) but far
below their sum: the merged agent runs both passes in one loop and
shares most of their tool calls.  Tunable — see settings.py §27."""

MAX_DISPATCH_HOPS = 200
"""Hard ceiling on the total number of agent hops the dispatcher
will execute in a single user turn before bailing out via
``_surface_limit_to_user("max dispatch hops")``.  Catches runaway
ping-pong loops that slip past the per-agent caps (e.g. agents
escalating back-and-forth indefinitely)."""

MAX_SECTIONS_REFINE_ROUNDS = 8
"""Hard cap on how many blade-section REFINE ROUNDS a precision job may
run before the dispatcher forces an honest finalize.  A "round" is one
hop into the DC Output Inspector while a Planner-issued standing
directive is active (each round = render → DCOI shape-comparison →
optional DCIC shape adjustment).  This is the CODE backstop behind the
DCOI's own prose-level stop judgments (Satisfied / Plateau): even if the
DCOI never says "converged", the loop can never run forever.  On hitting
the cap the dispatcher CLEARS the standing directive (so the DCOI is no
longer bound to keep iterating) and appends a "finalize + report the
residual honestly" note to the hand-off — a graceful stop, not an error.
Generous because the airfoil model usually plateaus well before 8."""
