"""Architect agent (3-agent topology) - the brain: perceives, plans,
routes and approves.

Merges the 7-agent User Input Inspector, Planner and Orchestrator into one
agent.  It reads the user's inputs INCLUDING their images, writes the
structured extraction, forms the plan, dispatches, and gives the final
verdict.  Like the Conductor it is a regular agent exposing
``run(message) -> AgentHop`` AND owning :meth:`dispatch`, the top-level
horizontal driver.

Perception is what distinguishes it from the Conductor.  The Conductor has
no vision at all (neither did the Planner it merged); the Architect binds
the UII's image tools, runs OCR through them, and owns
``write_extraction``.  ``extracted_inputs.txt`` is still written to disk:
perceive is PRESERVED in this topology - it is validate that is dropped -
and the Designer reads that file while the Critic compares against it in
DCOI_COMPARISON_MODE 3.

THE REFINE LOOP DOES NOT PASS THROUGH THIS AGENT (owner's decision).  The
Critic refines directly with the Designer, round after round, and the
Architect is called for exactly three things:

  * an ESCALATION that the pair cannot resolve;
  * a PHASE CHANGE - the Critic judges the current goal met, so the
    Architect can advance the job (e.g. "the sections match; now build
    the full 3D geometry");
  * a periodic CHECKPOINT, so several rounds of refinement can be
    reviewed as a whole.

The checkpoint is enforced here, not merely requested in a prompt: the
dispatch loop counts consecutive Designer <-> Critic rounds and forces the
next hop to the Architect at
``MAX_ROUNDS_BEFORE_ARCHITECT_CHECKPOINT``.  The Critic's prompt also asks
for a checkpoint when one is worthwhile, so the counter is a backstop for
when a model keeps deciding to iterate once more.

This is a REPORTING CADENCE, not a stopping condition.
``MAX_SECTIONS_REFINE_ROUNDS`` is unchanged and still bounds how many
refine rounds a phase may consume, exactly as in the other topologies.

Because the brain is outside the loop, standing directives must survive it:
the Architect stamps one at phase start and ``_DIRECTIVE_CARRIERS`` makes
the Designer and the Critic copy it verbatim through every round.

It does NOT hold ``new_attempt``: the Designer is the sole owner of attempt
creation in this topology, as the Creator is in the 5-agent one.

Deliberately a STANDALONE class rather than a subclass of Conductor.  The
5-agent hub is now a working, live-verified agent and a shared base would
put it at risk on every 3-agent change - the same reasoning that kept the
Conductor separate from the Orchestrator, one level down.
"""

import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

from agents.designer import Designer
from agents.database_handler import DatabaseHandler
from agents.dc_output_inspector import DCOutputInspector
from agents.receptionist import Receptionist
from agents.shared.agent_activity import generic_tool
from agents.shared.attempts_tool import list_attempts, read_attempt
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.context_pruner import ContextPruner
from agents.shared.file_utils import (
    ai_text,
    load_user_inputs_bundle,
    strip_image_blocks_from_messages,
)
from agents.shared.history_tool import build_read_agent_history_tool
from agents.shared.user_inputs_tool import (
    build_user_inputs_tools,
    dispatch_user_inputs_tool,
)
from agents.shared.llm_provider import (
    history_cache_control,
    make_system_message,
)
from agents.shared.llm_retry import invoke_with_retry
from agents.shared import token_usage
from agents.shared.prompts import _build_template
from agents.shared.retrieve_tool_dispatcher import dispatch_retrieve_tool
from agents.shared.routing_tools import (
    AGENT_DISPLAY,
    AgentHop,
    DONE,
    ROUTING_TOOL_NAMES,
    build_routing_tool,
    log_tool_call,
)
from agents.shared.session import AgentState, Session
from agents.shared import standing_directives
from agents.shared.stop_signal import check_stop_or_raise, is_stop_requested
from agents.shared.trace import trace as _trace
from agents.step_caps import (
    MAX_ROUNDS_BEFORE_ARCHITECT_CHECKPOINT,
    MAX_ARCHITECT_STEPS,
    MAX_ARCHITECT_VISITS,
    MAX_DISPATCH_HOPS,
    MAX_SECTIONS_REFINE_ROUNDS,
)
from config import INPUT_IMAGES_SUBDIR, USER_INPUTS_DIR
from tools.calculate.calculate import calculate
from tools.database_search.database_search import make_database_search_tool
from tools.retrieve_attempt.retrieve_attempt import make_retrieve_attempt_tool
from tools.retrieve_user_inputs.retrieve_user_inputs import (
    make_retrieve_user_inputs_tool,
)
from workflow_settings import database_access
from workflow_settings import settings as workflow_settings

# Pure formatting helpers, IMPORTED rather than duplicated.  They carry
# no topology knowledge, and copying them is exactly the duplication
# that lets two copies drift apart.
from agents.orchestrator.orchestrator import (
    _first_line,
    _format_agent_history,
    _last_text_message,
    _truncate,
)

# The two read tools the Architect inherits from the Planner third of its
# merge.  Both are SELF-CONTAINED — they do their own file I/O rather than
# being stubs backed by a handler — so binding them is all that is
# required; there is no dispatch code to port.  Imported for the same
# reason as the helpers above: a second copy would drift.
from agents.planner.planner import (
    read_extracted_inputs,
    read_user_queries,
)

logger = logging.getLogger("propeller_agent")


# ---------------------------------------------------------------------------
# The PERCEIVE half, lifted from the User Input Inspector.  Definitions are
# copied rather than imported so the Architect does not depend on an agent
# class this topology never constructs.
# ---------------------------------------------------------------------------

_READ_INPUTS_DOC = (
    "Read a user-inputs directory: TEXT plus a LIST of its images (it does "
    "NOT load the images themselves).\n\n"
    "Pass the absolute path of the inputs directory given on the ``Input "
    "file directory:`` line of your incoming message (do NOT guess).  The "
    "output is a "
    "summary plus the concatenated contents of all text/JSON files — "
    "including every image's ``_note.txt`` — followed by a list of the "
    "reference images present with their paths.  To actually SEE an image "
    "(and get its OCR-recognised text: dimension callouts, labels), call "
    "``view_images`` with the path(s) you need."
)


def _build_read_user_inputs():
    """Build the ``read_user_inputs`` tool.

    Returns text + an image LIST only; the real work happens in
    ``_handle_read_inputs_tool``.  Images (and their OCR) are loaded on
    demand via ``view_images``.
    """
    def _impl(path: str) -> str:
        return ""  # handled by _handle_read_inputs_tool
    _impl.__doc__ = _READ_INPUTS_DOC
    return tool("read_user_inputs")(_impl)


@tool
def write_extraction(
    path: str, quantitative: str, qualitative: str, intent: str,
) -> str:
    """Persist the structured user-input extraction to a file.

    Pass the absolute path to write to — the inputs directory from your
    incoming message with ``extracted_inputs.txt`` as the filename —
    plus three strings (one per section).  The file is a DESTINATION and
    need not already exist; this tool creates it.  Use "None specified." for any section with no content.
    The tool formats the file with canonical section headers and writes
    it to disk."""
    return ""  # Actual write is performed by _handle_write_extraction_tool.


# The chain agents that must carry a standing directive forward —
# everyone a Conductor directive is meant to reach.  Excludes the
# Conductor itself and the Receptionist (hub / user-facing): the
# Conductor re-stamps on its OUTGOING hop, so a block dropped on the way
# INTO it is not lost.
# The Designer and the Critic must carry a standing directive forward.
# This matters MORE here than in the 5-agent: the refine loop does not
# pass through the Architect, so a directive dropped between rounds is
# never re-stamped by the hub and the precision instructions are simply
# lost mid-phase.
_DIRECTIVE_CARRIERS = frozenset({
    "designer", "dc_output_inspector",
})


_ROLE4_INSTRUCTIONS_PATH = (
    Path(__file__).parent / "role4_feedback_instructions_3agents.md"
)


def _load_role4_instructions() -> str:
    """Role-4 (end-of-session feedback distribution) instructions.

    Held in a sibling ``.md`` and injected into the feedback-round
    trigger message ONLY when that pass runs, so the block does not ship
    in the live-pipeline system prompt on every turn.
    """
    return _ROLE4_INSTRUCTIONS_PATH.read_text(encoding="utf-8")


class Architect(BaseChainAgent):
    """Brain of the 3-agent topology: perceives, plans, routes and
    approves."""

    AGENT_KEY = "architect"

    def __init__(
        self,
        state: AgentState | None = None,
        session: Session | None = None,
        *,
        llm_cache=None,
    ):
        if session is None:
            raise TypeError(
                "Architect requires a Session.  Construct one via "
                "Session(...) or Session.create_for_v3(...) and pass "
                "it in."
            )
        if state is None:
            state = session.agent_states.setdefault(
                self.AGENT_KEY, AgentState(agent_key=self.AGENT_KEY),
            )
        super().__init__(state=state, session=session, llm_cache=llm_cache)

        # Config flags read from session, held on self so call sites can
        # read self.* without touching session.* directly.  There is no
        # dc_inspector_enabled here: the Creator self-validates, so that
        # axis does not exist in this topology.  There is no
        # chain_access either — it was dropped from the Conductor's
        # prompt, so nothing consumes it.
        # The perceive half's read tool is built per instance because the
        # UII's factory closes over the loader.
        self._read_inputs_tool = _build_read_user_inputs()
        self.rag_enabled = session.rag_enabled
        self.mesh_checks = session.mesh_checks
        self.dcoi_comparison_mode = session.dcoi_comparison_mode

        def _state_for(agent_key: str) -> AgentState:
            return session.agent_states.setdefault(
                agent_key, AgentState(agent_key=agent_key),
            )

        self.receptionist = Receptionist(
            state=_state_for("receptionist"), session=session,
        )
        # No User Input Inspector: this agent IS the perceiver.
        # No Tool Caller: the Designer absorbed it.
        self.designer = Designer(
            state=_state_for("designer"), session=session,
        )
        self.dc_output_inspector = DCOutputInspector(
            state=_state_for("dc_output_inspector"), session=session,
        )

        # Context Pruner gets its OWN LLM from its per-agent model
        # assignment rather than sharing the hub's, so tiering it
        # independently takes effect on the (rare) summarisation call.
        # Falls back to the hub's LLM on any resolution error, so a
        # missing per-agent entry can never block startup.
        try:
            from agents.shared.llm_provider import build_llm as _build_pruner
            _pruner_llm, _, _pruner_model = _build_pruner("context_pruner")
            logger.info(f"[CP]  pruner LLM built: {_pruner_model}")
        except Exception as exc:
            logger.warning(f"[CP]  pruner LLM build failed ({exc}); "
                           f"sharing the Architect's LLM instead.")
            _pruner_llm = self.base_llm
        self.context_pruner = ContextPruner(_pruner_llm)
        setattr(session, "context_pruner", self.context_pruner)
        try:
            from agents.shared.model_windows import refresh_from_api
            refresh_from_api()
        except Exception as exc:  # pragma: no cover - never block startup
            logger.warning(f"[CP]  model-window refresh skipped: {exc}")

        # Database Handler — runs ONLY post-session.  Not part of the
        # dispatch loop, has no routing tools, never speaks to the user.
        self.database_handler = DatabaseHandler(
            state=_state_for("database_handler"), session=session,
        )

        self._tools_by_name: dict = {}
        # The Conductor's prompt carries the Planner's three path slots
        # (it hands the UII its input directory and extraction output
        # path).  It does NOT take routing_instructions: as the hub it
        # uses the static $routing_conductor fragment, the way the
        # Orchestrator uses $routing_orchestrator.
        #
        # Built fresh at construction time so live edits to .md
        # fragments via the System Prompts UI take effect on the NEXT
        # session without a Python restart.
        self.system_prompt = _build_template("architect").format(
            user_inputs_dir=str(USER_INPUTS_DIR.resolve()),
            input_images_subdir=INPUT_IMAGES_SUBDIR,
            extraction_output_file=str(
                (USER_INPUTS_DIR / "extracted_inputs.txt").resolve()
            ),
        )

        # Registry for the dispatch driver
        self._agents_by_key: dict = {
            "architect":            self,
            "designer":             self.designer,
            "dc_output_inspector":  self.dc_output_inspector,
            "receptionist":         self.receptionist,
        }

        self._wire_routing()

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def _wire_routing(self) -> None:
        """Bind every agent's routing tools and build their prompts.

        Each agent gets ONLY the routing tools it is allowed to use.
        ``build_routing_tool`` binds each tool to its CALLER: invoking it
        records an ``AgentHop`` on the caller's ``_pending_hop``, which
        the dispatcher reads once that caller's run loop exits.

        The 3-agent edge set is fixed.  The flow is:

            Receptionist -> Architect -> Designer -> Critic -> Designer
            -> ... -> Architect -> Receptionist

        Note the loop: the Critic refines DIRECTLY with the Designer and
        the Architect is not in it.  The Critic returns to the Architect
        only to escalate, to report a phase complete, or when the
        dispatcher forces a checkpoint.
        """
        cl = self.session

        history_tool = build_read_agent_history_tool(self.get_agent_messages)

        # Receptionist — ONE forward door.  Unlike the 5-agent, where it
        # chose between the UII and the hub, there is no separate
        # perceiver here: the Architect reads the inputs itself, so every
        # forward goes to it.
        self.receptionist.set_tools([
            history_tool,
            build_routing_tool(
                "receptionist", "architect", self.receptionist, cl,
            ),
        ])

        # Designer — FORWARD to the Critic; CLARIFY and ESCALATE both go
        # to the Architect via the same tool, differing only in the intent
        # it states.
        self.designer.set_routing_tools([
            build_routing_tool("designer", "dc_output_inspector",
                               self.designer, cl),
            build_routing_tool("designer", "architect", self.designer, cl),
        ])

        # Critic (DC Output Inspector) — the refine partner.  It sends
        # work straight BACK to the Designer round after round; the
        # Architect is called to escalate, to report the current phase's
        # goal met so the job can advance, or when the dispatcher forces
        # a checkpoint.  This is the one edge that differs from the
        # 5-agent, where the DCOI could only return to the hub.
        self.dc_output_inspector.set_routing_tools([
            build_routing_tool("dc_output_inspector", "designer",
                               self.dc_output_inspector, cl),
            build_routing_tool("dc_output_inspector", "architect",
                               self.dc_output_inspector, cl),
        ])

        # Architect — can dispatch to every agent.  It does NOT get
        # ``new_attempt``: the Designer is the sole owner of attempt
        # creation in this topology, as the Creator is in the 5-agent.
        arch_tools = [
            build_routing_tool("architect", "receptionist", self, cl),
            build_routing_tool("architect", "designer", self, cl),
            build_routing_tool("architect", "dc_output_inspector", self, cl),
            calculate,
            list_attempts,
            read_attempt,
            # Planner half: read the extraction and the user's own words
            # before planning.  Bound explicitly because the Conductor
            # shipped without them and paid two wasted hops per turn.
            read_extracted_inputs,
            read_user_queries,
            # UII half: this agent PERCEIVES.  read_user_inputs loads the
            # text bundle, write_extraction persists the structured
            # extraction, and build_user_inputs_tools supplies the image /
            # OCR tools.  None of this exists on the Conductor, which has
            # no vision at all.
            self._read_inputs_tool,
            write_extraction,
        ] + build_user_inputs_tools(self.AGENT_KEY)
        if database_access.is_enabled_for(self.AGENT_KEY):
            arch_tools.append(make_database_search_tool(self.AGENT_KEY))
            arch_tools.append(make_retrieve_user_inputs_tool(self.AGENT_KEY))
            arch_tools.append(make_retrieve_attempt_tool(self.AGENT_KEY))
        self._tools_by_name = {t.name: t for t in arch_tools}
        self.llm = self.base_llm.bind_tools(arch_tools)

    # ------------------------------------------------------------------
    # Run loop — terminal on every routing tool (horizontal dispatch)
    # ------------------------------------------------------------------

    def run(self, message: str) -> AgentHop:
        """Process one incoming message and return the chosen hop."""
        token_usage.begin_turn("Architect")
        self._pending_hop = None
        self.messages.append(HumanMessage(content=message))

        for _ in range(MAX_ARCHITECT_STEPS):
            check_stop_or_raise()
            self.prune_history_if_needed()
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + self.messages,
                "Conductor",
                cache_control=history_cache_control(self.provider),
            )
            self.messages.append(response)

            rendered_content = ai_text(response.content)
            if rendered_content:
                logger.info(f"[ARCHITECT]  {rendered_content}")

            if not response.tool_calls:
                final = rendered_content
                if not final or not final.strip():
                    final = (
                        "The Conductor produced no user-facing text this "
                        "turn (empty response from the model).  This is "
                        "likely a coordination bug; please re-send your "
                        "last request."
                    )
                return AgentHop(DONE, final)

            routed = False
            for tc in response.tool_calls:
                check_stop_or_raise()
                name = tc["name"]
                # retrieve_* tools are dispatcher-handled (their @tool
                # stubs return "") — catch them before the
                # _tools_by_name lookup so the stub never runs.
                if name == self._read_inputs_tool.name:
                    self._handle_read_inputs_tool(tc)
                    continue
                if name == "write_extraction":
                    self._handle_write_extraction_tool(tc)
                    continue
                if dispatch_user_inputs_tool(self, tc, self.AGENT_KEY):
                    continue
                if dispatch_retrieve_tool(self, tc, self.AGENT_KEY):
                    continue
                tool_fn = self._tools_by_name.get(name)
                if tool_fn is None:
                    result = f"Error: unknown tool '{name}'"
                else:
                    try:
                        result = tool_fn.invoke(tc["args"])
                    except Exception as exc:
                        result = f"Error calling {name}: {exc}"
                        logger.error(f"[ARCHITECT TOOL ERROR] {name}: {exc}")

                if name not in ROUTING_TOOL_NAMES:
                    log_tool_call(
                        self.AGENT_KEY, name, tc.get("args"), result,
                    )

                self.messages.append(ToolMessage(
                    content=str(result),
                    tool_call_id=tc["id"],
                    name=name,
                ))
                if name in ROUTING_TOOL_NAMES and self._pending_hop is not None:
                    routed = True
                    break

            if routed:
                return self._pending_hop

        # The inner loop exhausted its budget without routing or
        # producing plain text.  Bail out as DONE so the dispatcher does
        # not loop indefinitely.
        return AgentHop(
            DONE,
            "Conductor produced no routing decision this turn.",
        )

    # ------------------------------------------------------------------
    # Dispatcher — the top-level horizontal driver
    # ------------------------------------------------------------------

    def dispatch(self, kickoff_message: str,
                 start_agent_key: str = "architect") -> str:
        """Run the horizontal dispatch loop and return the user-facing text."""
        current = start_agent_key
        message = kickoff_message
        # A standing directive is issued fresh each user turn (the
        # Conductor re-derives it from the extraction when still
        # relevant), so a stale directive from a prior turn is never
        # forced onto — or leaked by — an unrelated later turn.
        self.session.standing_directives = ""
        architect_visits = 0
        # Consecutive Designer <-> Critic rounds that have not passed
        # through this agent.  Drives the checkpoint backstop below.
        rounds_since_checkpoint = 0
        # A refine ROUND is one hop into the DCOI while a precision
        # standing directive is active.  A local (not on the session)
        # because a precision loop lives entirely within ONE dispatch
        # call (one user turn).
        precision_rounds = 0

        for _ in range(MAX_DISPATCH_HOPS):
            # Cooperative-stop check honoured at each hop boundary: the
            # currently-running step has already finished by the time we
            # get back here.
            if is_stop_requested():
                logger.warning(
                    "[DISPATCH] Stop requested by user — halting pipeline "
                    f"at hop into '{current}'"
                )
                _trace(current, "User", "stopped by user")
                return (
                    "(Session interrupted by Stop button — the pipeline "
                    "halted after the last completed step.  Send a new "
                    "message to continue.)"
                )

            agent = self._agents_by_key.get(current)
            if agent is None:
                return f"Dispatch error: unknown agent key '{current}'."

            if current == self.AGENT_KEY:
                # No chain-access block: chain access was dropped from
                # the Conductor's prompt, so there is nothing to prepend.
                architect_visits += 1
                if architect_visits > MAX_ARCHITECT_VISITS:
                    logger.warning("[DISPATCH] Max Architect visits reached")
                    return self._surface_limit_to_user("max Architect visits")

            hop = agent.run(message)

            # Operation-end hook.  An "operation" ends when an agent's
            # run() returns — i.e. the LLM invoked a routing tool.
            # Image-consuming agents use this to strip image bytes from
            # history when KEEP IMAGES IN CONTEXT is OFF.
            on_op_end = getattr(agent, "on_operation_end", None)
            if callable(on_op_end):
                try:
                    on_op_end()
                except Exception as exc:  # pragma: no cover
                    logger.warning(
                        f"[DISPATCH] on_operation_end failed for "
                        f"{current}: {exc}"
                    )

            if not isinstance(hop, AgentHop):
                # Defensive guard — every agent must return AgentHop.
                return str(hop)

            # [AGENT MSG] is normally emitted by the routing tool when
            # the LLM invokes it.  When an agent's run loop returns a
            # hub-bound hop WITHOUT having invoked the tool (error
            # fall-through, step-limit exhaustion, empty tool_calls) the
            # routing-tool logger never fires, so emit it here.
            if (
                hop.target == self.AGENT_KEY
                and current != self.AGENT_KEY
                and getattr(agent, "_pending_hop", None) is None
            ):
                source_display = AGENT_DISPLAY.get(current, current)
                logger.info(
                    f"[AGENT MSG]  {source_display} -> Conductor\n"
                    f"{hop.message}"
                )
                _trace(source_display, "Error, Escalated to Architect")

            if hop.target == DONE:
                return hop.message

            # Precision sections: when the refine loop exceeds its hard
            # cap, DROP the directive (so the DCOI is no longer bound to
            # keep iterating) and tell it to finalize with the best
            # attempt and report the residual honestly.  This is the
            # graceful code backstop behind the DCOI's own
            # Satisfied/Plateau prose judgements, so a stuck loop can
            # never run forever regardless of prose.  Runs BEFORE the
            # re-stamp block below, so clearing the field here makes
            # that block's ensure_present a no-op.
            if hop.target == "dc_output_inspector" and self.session.standing_directives:
                precision_rounds += 1
                if precision_rounds > MAX_SECTIONS_REFINE_ROUNDS:
                    logger.warning(
                        "[DISPATCH] Sections refine cap "
                        f"({MAX_SECTIONS_REFINE_ROUNDS}) reached — forcing an "
                        "honest finalize"
                    )
                    self.session.standing_directives = ""
                    hop.message += (
                        "\n\n=== PRECISION REFINE CAP REACHED ===\n"
                        f"The precision refine loop hit its "
                        f"{MAX_SECTIONS_REFINE_ROUNDS}-round cap.  STOP iterating: "
                        "finalize with the best attempt so far and report honestly "
                        "how closely it matched the sketch, naming any remaining gap "
                        "as the configurator's limit (the airfoil-model ceiling for a "
                        "sections match, or the geometry / locked-parameter limit for "
                        "a 3D match) rather than ordering another cycle."
                    )

            # Capture a Conductor-issued standing directive, then
            # re-stamp it onto any forward hand-off that dropped it (the
            # loss backstop).  The directive is verbose text carried IN
            # the messages, not a flag; only the Conductor may set one.
            #
            # NOTE: this keys on the CONDUCTOR.  The 7-agent original
            # keys on "planner"; ported unchanged the test would never
            # fire here and the entire precision refine loop would
            # vanish silently.
            if current == self.AGENT_KEY:
                _issued = standing_directives.extract_directive(hop.message)
                if _issued:
                    # A FRESH / changed directive begins a NEW precision
                    # PHASE (e.g. sections converged -> the 3D check), so
                    # reset the per-phase refine-round budget, giving
                    # each phase its own allowance.
                    if _issued != self.session.standing_directives:
                        precision_rounds = 0
                    self.session.standing_directives = _issued
            if hop.target in _DIRECTIVE_CARRIERS:
                hop.message = standing_directives.ensure_present(
                    hop.message, self.session.standing_directives
                )

            # CHECKPOINT BACKSTOP.  The Critic refines DIRECTLY with the
            # Designer, so the Architect is not in the refine loop and a
            # model that keeps deciding to iterate once more could shut it
            # out indefinitely.  Count consecutive rounds that bypass this
            # agent and, at the cap, redirect the next hop here instead.
            #
            # The Critic's prompt ALSO asks for a checkpoint when one is
            # worthwhile; this is only the floor for when it does not.  A
            # reporting CADENCE, not a stopping condition —
            # MAX_SECTIONS_REFINE_ROUNDS remains the per-phase ceiling.
            if hop.target == self.AGENT_KEY:
                rounds_since_checkpoint = 0
            elif current == "dc_output_inspector" and hop.target == "designer":
                rounds_since_checkpoint += 1
                if (rounds_since_checkpoint
                        >= MAX_ROUNDS_BEFORE_ARCHITECT_CHECKPOINT):
                    logger.info(
                        f"[DISPATCH]  checkpoint: {rounds_since_checkpoint} "
                        f"Designer<->Critic rounds without the Architect; "
                        f"routing to it before continuing."
                    )
                    hop.message = (
                        "[CHECKPOINT — forced by the dispatcher after "
                        f"{rounds_since_checkpoint} refine rounds that did "
                        "not pass through you.]\n\nThe Critic was about to "
                        "send the following back to the Designer for another "
                        "round.  Review what these rounds have achieved, then "
                        "either let the loop continue, redirect it, or move "
                        "the job to its next phase.\n\n" + hop.message
                    )
                    hop.target = self.AGENT_KEY
                    rounds_since_checkpoint = 0

            current = hop.target
            message = hop.message

        logger.warning("[DISPATCH] Max dispatch hops reached")
        return self._surface_limit_to_user("max dispatch hops")

    # ------------------------------------------------------------------
    # Surfacing step-limit termination to the user
    # ------------------------------------------------------------------

    def _surface_limit_to_user(self, reason_label: str) -> str:
        """Build a technical summary and let the Receptionist relay it."""
        summary_lines: list[str] = [
            "The design workflow was halted before completion.",
            f"Reason: {reason_label} reached.",
            "",
        ]

        exchanges = self.session.chain_log_exchanges
        if exchanges:
            summary_lines.append("Route taken (compact):")
            for ex in exchanges[-20:]:
                snippet = _first_line(ex["message"], limit=180)
                summary_lines.append(
                    f"  - {ex['from_agent']} -> {ex['to_agent']}: {snippet}"
                )
            summary_lines.append("")

        dcoi_msg = _last_text_message(self.dc_output_inspector)
        if dcoi_msg:
            summary_lines.append("Last DC Output Inspector verdict:")
            summary_lines.append(_truncate(dcoi_msg, 800))
            summary_lines.append("")

        des_msg = _last_text_message(self.designer)
        if des_msg:
            summary_lines.append("Last Designer report:")
            summary_lines.append(_truncate(des_msg, 800))
            summary_lines.append("")

        # The Conductor holds the plan itself — there is no separate
        # Planner to read it from.  The 7-agent equivalent reads
        # ``self.planner.current_plan``, whose getattr guards the
        # attribute rather than the agent and would raise here.
        plan = getattr(self, "current_plan", "")
        if plan:
            summary_lines.append("Latest plan:")
            summary_lines.append(_truncate(plan, 600))
            summary_lines.append("")

        summary = "\n".join(summary_lines).rstrip()
        last_attempted = ""
        if exchanges:
            fa, ta, msg = exchanges[-1]
            last_attempted = f"{fa} -> {ta}: {_first_line(msg, limit=160)}"

        fallback = (
            f"The Conductor could not settle a plan within its step "
            f"budget ({reason_label}); this is likely a coordination bug."
        )
        if last_attempted:
            fallback += f"  Last attempted action: {last_attempted}"

        try:
            composed = self.receptionist.run(summary).message
        except Exception as exc:
            logger.error(f"[DISPATCH SURFACE ERROR] {exc}")
            composed = ""

        if not composed or not composed.strip():
            return fallback
        return composed

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def reset_turn(self) -> None:
        """Reset per-turn state (call at the start of each user turn).

        Vestigial: the chain log is session-scoped and the per-turn view
        is reconstructed via a cursor inside ``dispatch`` rather than by
        clearing anything.  Kept as a no-op so the loader's call site
        stays stable.
        """
        return None

    def _handle_read_inputs_tool(self, tc: dict) -> None:
        """Load everything in the requested directory and feed it to the LLM."""
        raw_path = tc.get("args", {}).get("path")
        summary_parts: list[str] = []
        image_paths: list[str] = []

        if not raw_path or not isinstance(raw_path, str):
            summary = (
                "Error: no directory path provided.  Call this tool with "
                "the absolute path supplied in your hand-off."
            )
        else:
            directory = Path(raw_path)
            if not directory.is_dir():
                summary = (
                    f"Error: '{raw_path}' is not an existing directory.  "
                    f"Do not retry with a guessed path."
                )
            else:
                # Workflow setting (block #18) lets the developer
                # filter the prior extracted_inputs.txt out of the
                # bundle when they suspect the UII is carrying stale
                # state forward despite the prompt's "do not copy
                # forward" rule.  Read disk-fresh per the standard
                # workflow_settings pattern.
                exclude_root: tuple[str, ...] = ()
                if not workflow_settings.UII_MAY_READ_PREVIOUS_EXTRACTION:
                    exclude_root = ("extracted_inputs.txt",)
                # Images are NOT loaded here — the UII loads the specific
                # image(s) it needs on demand via view_images (which
                # also runs OCR per image).  read_user_inputs stays cheap:
                # text + notes + a list of the images present.
                loaded = load_user_inputs_bundle(
                    directory,
                    self.provider,
                    include_image_bytes=False,
                    exclude_root_files=exclude_root,
                )
                image_paths = loaded["image_paths"]
                pairing = loaded["pairing"]
                summary_parts.append(
                    f"Loaded inputs from {directory.resolve()}."
                )
                summary_parts.append(f"Files: {loaded['summary']}")
                if not pairing["ok"]:
                    summary_parts.append(
                        "WARNING: image+note pairing is INVALID.  "
                        "The Receptionist should have caught this — "
                        "ESCALATE so the user can be asked to fix the "
                        "uploads.  Pairing report:\n" + pairing["report"]
                    )
                if loaded["text_content"]:
                    summary_parts.append(
                        "--- File contents ---\n" + loaded["text_content"]
                    )
                else:
                    summary_parts.append("(no text or JSON files found)")
                if image_paths:
                    listing = "\n".join(
                        f"  - {Path(p).name}   (path: {p})"
                        for p in image_paths
                    )
                    summary_parts.append(
                        f"{len(image_paths)} reference image(s) are available "
                        f"but NOT loaded here (their notes are in the file "
                        f"contents above).  To SEE an image and get its OCR "
                        f"text, call view_images with the path(s) you "
                        f"need:\n" + listing
                    )
                summary = "\n\n".join(summary_parts)

        log_tool_call(
            self.AGENT_KEY, tc["name"], tc.get("args"), summary,
        )

        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    # ------------------------------------------------------------------
    # write_extraction handler
    # ------------------------------------------------------------------

    @generic_tool("Write extracted inputs")

    def _handle_write_extraction_tool(self, tc: dict) -> None:
        """Write the three-section extraction to the path the LLM supplied."""
        args = tc.get("args", {}) or {}
        raw_path = args.get("path")
        quantitative = args.get("quantitative")
        qualitative = args.get("qualitative")
        intent = args.get("intent")

        if not isinstance(raw_path, str) or not raw_path.strip():
            summary = (
                "Error: missing or non-string 'path' argument.  Call this "
                "tool with the absolute path supplied in your hand-off under "
                "the 'Extraction output file:' label."
            )
        else:
            missing = [
                name for name, val in (
                    ("quantitative", quantitative),
                    ("qualitative", qualitative),
                    ("intent", intent),
                ) if not isinstance(val, str)
            ]
            if missing:
                summary = (
                    f"Error: the following arguments are missing or not "
                    f"strings: {missing}.  File not written."
                )
            else:
                q, ql, it = (
                    quantitative.strip(),
                    qualitative.strip(),
                    intent.strip(),
                )
                if not (q or ql or it):
                    summary = (
                        "Error: all three sections are empty.  Provide "
                        "at least one non-empty section (use 'None "
                        "specified.' only for truly empty sections when "
                        "at least one other section has content).  File "
                        "not written."
                    )
                else:
                    extraction = (
                        f"QUANTITATIVE INPUTS:\n{q or 'None specified.'}\n\n"
                        f"QUALITATIVE DESCRIPTIONS:\n{ql or 'None specified.'}\n\n"
                        f"DESIGN INTENT AND FUNCTIONAL REQUIREMENTS:\n"
                        f"{it or 'None specified.'}"
                    )
                    out_path = Path(raw_path)
                    try:
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_text(extraction, encoding="utf-8")
                        summary = (
                            f"Wrote {out_path.name} ({len(extraction)} chars) "
                            f"to {out_path.resolve()}."
                        )
                        logger.info(f"[ARCHITECT] {summary}")
                    except OSError as exc:
                        summary = (
                            f"Error writing to '{raw_path}': {exc}"
                        )
                        logger.warning(f"[ARCHITECT] {summary}")

        log_tool_call(
            self.AGENT_KEY, tc["name"], tc.get("args"), summary,
        )

        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    def on_operation_end(self) -> None:
        """End-of-operation hook called by the dispatcher.

        With ``keep_images_in_context=False`` strip every image
        content block from this agent's history, leaving the paired
        ``Loaded image (path: …):`` text blocks behind.  No-op when
        ``keep_images_in_context=True``.
        """
        if self.keep_images_in_context:
            return
        removed = strip_image_blocks_from_messages(self.messages)
        if removed:
            logger.info(
                f"[ARCHITECT]  on_operation_end stripped {removed} image "
                f"block(s); paired path-text blocks retained."
            )

    def reset(self) -> None:
        """Clear all agent histories for a fresh start."""
        self.messages.clear()
        self.session.chain_log_exchanges.clear()
        self.session.standing_directives = ""
        self.receptionist.reset()
        self.designer.reset()
        self.dc_output_inspector.reset()

    # ------------------------------------------------------------------
    # Live agent-history access (used by the read_agent_history tool)
    # ------------------------------------------------------------------

    _AGENT_KEY_ALIASES: dict = {
        # Only the agents THIS topology constructs.  Carrying the
        # 7-agent aliases would let read_agent_history resolve a name
        # to an agent that does not exist and then fail on lookup.
        "architect": "architect",
        "designer": "designer",
        "dc output inspector": "dc_output_inspector",
        "dc_output_inspector": "dc_output_inspector",
        "dcoi": "dc_output_inspector",
        "critic": "dc_output_inspector",
        "receptionist": "receptionist",
    }

    def get_agent_messages(
        self,
        agent_name: str,
        last_n: int | None = None,
    ) -> str:
        """Return a formatted dump of *agent_name*'s message history."""
        if not isinstance(agent_name, str):
            return "Error: 'agent_name' must be a string."
        key = self._AGENT_KEY_ALIASES.get(agent_name.strip().lower())
        if key is None:
            valid = sorted(self._agents_by_key)
            return (
                f"Error: unknown agent '{agent_name}'.  Valid names: "
                f"{', '.join(valid)}."
            )
        agent = self._agents_by_key.get(key)
        messages = getattr(agent, "messages", None)
        if not messages:
            return f"No history recorded for agent '{key}' yet."
        if isinstance(last_n, int) and last_n > 0:
            messages = messages[-last_n:]
        return _format_agent_history(key, messages, sys_prompt=None)

    # ------------------------------------------------------------------
    # End-of-session feedback distribution (Role 4)
    # ------------------------------------------------------------------

    def run_feedback_round(
        self,
        *,
        satisfaction: str,
        what_went_well: str,
        what_went_wrong: str,
    ) -> dict:
        """Drive ONE forced ``submit_feedback_dispatch`` tool call that
        decides, per agent, whether the user's end-of-session feedback
        contains material worth forwarding to that agent.

        Side effect on success: for every dispatch with ``send=True``,
        appends a ``HumanMessage(content=message, name="architect")`` to
        the target's LIVE ``self.messages`` AND mirrors the agent's new
        ``snapshot_state()`` into ``self.session.agent_states[<key>]``.
        The Database Handler reads from the session's ``agent_states``
        when interviewing each agent post-session.

        This method DOES NOT mutate the Conductor's live pipeline
        history: the tool is bound for ONE turn only and discarded
        immediately afterwards, leaving the permanent binding installed
        by ``_wire_routing`` untouched.
        """
        from agents.orchestrator.feedback_tool import (
            feedback_envelope,
            submit_feedback_dispatch,
            SUBMIT_FEEDBACK_DISPATCH_TOOL_NAME,
        )

        # Target set: every agent in the registry INCLUDING the
        # Conductor itself.  This is a deliberate departure from the
        # 7-agent hub, which is excluded because it only relays.  The
        # Conductor also PLANS — strategy, recovery, approval timing,
        # retry budget — and that is exactly what users comment on, so
        # excluding it would leave the Planner's entire feedback scope
        # with no recipient at all.
        target_keys: list[str] = list(self._agents_by_key.keys())

        # Per-turn forced-tool binding.  LOCAL — it does NOT mutate
        # self.llm, which stays the permanently-bound pipeline LLM.
        try:
            feedback_llm = self.base_llm.bind_tools(
                [submit_feedback_dispatch],
                tool_choice=SUBMIT_FEEDBACK_DISPATCH_TOOL_NAME,
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                f"[CONDUCTOR-FEEDBACK]  could not bind "
                f"submit_feedback_dispatch: {type(exc).__name__}: "
                f"{exc}; treating as empty dispatch list."
            )
            return {"ok": False, "decisions": [], "error": str(exc)}

        # TRANSIENT message list (we do NOT append to self.messages) so
        # the pipeline history stays clean.  The Role-4 instructions are
        # injected by CONCATENATION — not str.format — so their literal
        # JSON braces survive.
        ww = (what_went_well or "").strip() or "(no text supplied)"
        ww_wrong = (what_went_wrong or "").strip() or "(no text supplied)"
        targets_md = ", ".join(target_keys)

        live_data = (
            "--- THIS SESSION'S FEEDBACK ---\n\n"
            f"Satisfaction (y/partial/n): {(satisfaction or '').strip() or '(unset)'}\n"
            f"What worked well: {ww}\n"
            f"What did NOT work: {ww_wrong}\n\n"
            "Target agents (emit exactly one dispatch each, any order): "
            f"{targets_md}\n\n"
            "Emit the submit_feedback_dispatch call now."
        )
        instruction = HumanMessage(
            content=_load_role4_instructions() + "\n\n" + live_data
        )

        try:
            response = invoke_with_retry(
                feedback_llm,
                [make_system_message(self.system_prompt, self.provider)]
                + [instruction],
                "Conductor-feedback-dispatch",
                # NO history breakpoint here on purpose — same reasoning as
                # the Orchestrator's feedback dispatch: this sends a
                # freshly-built one-off list ([system] + [instruction]), so
                # ``instruction`` differs every time and a breakpoint on it
                # would write an entry no later request can ever match — a
                # pure cache WRITE premium with no offsetting read.  The
                # system prompt is still cached by make_system_message.
            )
        except Exception as exc:
            logger.warning(
                f"[CONDUCTOR-FEEDBACK]  LLM call raised "
                f"{type(exc).__name__}: {exc}; treating as empty "
                f"dispatch list."
            )
            return {"ok": False, "decisions": [], "error": str(exc)}

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            logger.warning(
                "[CONDUCTOR-FEEDBACK]  response carried no tool_calls "
                "despite tool_choice=submit_feedback_dispatch; "
                "treating as empty dispatch list."
            )
            return {"ok": False, "decisions": [], "error": "no_tool_call"}

        tc = tool_calls[0]
        args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
        dispatches = (args or {}).get("dispatches") or []
        if not isinstance(dispatches, list):
            logger.warning(
                f"[CONDUCTOR-FEEDBACK]  expected `dispatches` to be a "
                f"list; got {type(dispatches).__name__!r}."
            )
            dispatches = []

        applied: list[dict] = []
        seen_keys: set[str] = set()
        for d in dispatches:
            if not isinstance(d, dict):
                continue
            ak  = str(d.get("agent_key") or "").strip()
            snd = bool(d.get("send", False))
            msg = str(d.get("message") or "").strip()
            if ak not in target_keys:
                logger.warning(
                    f"[CONDUCTOR-FEEDBACK]  dispatch agent_key {ak!r} "
                    f"not in target set; skipping."
                )
                continue
            if ak in seen_keys:
                logger.warning(
                    f"[CONDUCTOR-FEEDBACK]  duplicate dispatch for "
                    f"{ak!r}; keeping the first one."
                )
                continue
            seen_keys.add(ak)
            if not snd or not msg:
                applied.append({"agent_key": ak, "send": False, "message": ""})
                continue

            # Append to the LIVE agent so dump_histories sees it, then
            # mirror via snapshot_state() into session.agent_states so
            # the DH's per-agent interview sees it too (the DH reads
            # session.agent_states[<key>].messages, NOT the live agent
            # instances).
            target = self._agents_by_key.get(ak)
            if target is None:  # pragma: no cover — defensive
                continue
            try:
                target.messages.append(
                    HumanMessage(content=feedback_envelope() + msg,
                                  name="architect")
                )
                self.session.agent_states[ak] = target.snapshot_state()
            except Exception as exc:
                logger.warning(
                    f"[CONDUCTOR-FEEDBACK]  could not append feedback "
                    f"to {ak!r}: {type(exc).__name__}: {exc}"
                )
                applied.append({"agent_key": ak, "send": False, "message": ""})
                continue
            applied.append({"agent_key": ak, "send": True, "message": msg})

        sent = [d["agent_key"] for d in applied if d.get("send")]
        skipped = [d["agent_key"] for d in applied if not d.get("send")]
        logger.info(
            f"[CONDUCTOR-FEEDBACK]  round complete — "
            f"sent={sent or '[]'}  skipped={skipped or '[]'}"
        )
        return {"ok": True, "decisions": applied, "error": None}

    # ------------------------------------------------------------------
    # Per-agent history dump
    # ------------------------------------------------------------------

    def dump_histories(self, output_dir) -> list:
        """Write each agent's message history to its own text file."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        agents = [
            ("architect",           self,                      self.system_prompt),
            ("receptionist",        self.receptionist,         getattr(self.receptionist, "system_prompt", None)),
            ("designer",            self.designer,             getattr(self.designer, "system_prompt", None)),
            ("dc_output_inspector", self.dc_output_inspector,  getattr(self.dc_output_inspector, "system_prompt", None)),
        ]

        written: list = []
        for name, agent, sys_prompt in agents:
            messages = getattr(agent, "messages", None)
            if messages is None:
                continue
            path = output_dir / f"history_{name}.txt"
            path.write_text(
                _format_agent_history(name, messages, sys_prompt),
                encoding="utf-8",
            )
            written.append(path)
        return written
