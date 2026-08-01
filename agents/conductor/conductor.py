"""Conductor agent (5-agent topology) — the hub that plans, routes and
approves.

Merges the 7-agent Planner and Orchestrator into one agent.  Like the
Orchestrator it is a regular agent that exposes ``run(message) ->
AgentHop`` AND owns :meth:`dispatch`, the top-level horizontal driver.
Unlike the Orchestrator it also plans: strategy, recovery sequences and
final approval are its work, not a separate agent's.

Deliberately a STANDALONE class rather than a subclass of, or refactor
of, ``Orchestrator``.  The 7-agent hub is the most central agent in a
working system and cannot be verified in this environment, so it is left
untouched.  The cost is duplicated hub machinery; the pure formatting
helpers ARE imported from it rather than copied, so those cannot drift.

Three differences from a mechanical port, each deliberate:

* **Standing directives key on this agent, not "planner".**  The
  Orchestrator captures a directive with ``if current == "planner"``.
  Ported unchanged that test never fires here, ``session.standing_
  directives`` stays empty forever, the refine-round counter never arms
  and the whole precision section-matching loop silently disappears —
  no error, no log line.  It keys on ``"conductor"``.
* **No chain-access block.**  Chain access was dropped from the
  Conductor's prompt, so ``dispatch`` does not prepend the
  "messages recorded while you were waiting" block.
* **The step-limit escape hatch reads its own plan.**  The Orchestrator
  does ``getattr(self.planner, "current_plan", "")`` — the ``getattr``
  guards the ATTRIBUTE, not the agent, so with no ``self.planner`` it
  would raise inside the escape hatch, i.e. exactly when the system is
  already failing.  The Conductor holds the plan itself.

It does NOT hold ``new_attempt``: the Creator is the sole owner of
attempt creation in this topology, so the Orchestrator's
pre-open-a-folder fallback has no counterpart here.

NOT YET WIRED.  Nothing constructs this class — ``SYSTEM_TOPOLOGY``
defaults to 7 and no entry point builds the 5-agent set.  Two
resolution steps also remain outstanding, so a prompt built today would
splice the 7-agent fragments and leave ``$routing_conductor``
unresolved: ``prompts._build_slots`` is not topology-aware, and
``routing._load_routing_fragment`` only looks in the shared fragment
directory.
"""

import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage

from agents.creator import Creator
from agents.database_handler import DatabaseHandler
from agents.dc_output_inspector import DCOutputInspector
from agents.receptionist import Receptionist
from agents.shared.attempts_tool import list_attempts, read_attempt
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.context_pruner import ContextPruner
from agents.shared.file_utils import ai_text
from agents.shared.history_tool import build_read_agent_history_tool
from agents.shared.llm_provider import make_system_message
from agents.shared.llm_retry import invoke_with_retry
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
    MAX_CONDUCTOR_STEPS,
    MAX_CONDUCTOR_VISITS,
    MAX_DISPATCH_HOPS,
    MAX_SECTIONS_REFINE_ROUNDS,
)
from agents.tool_caller import ToolCaller
from agents.user_input_inspector import UserInputInspector
from config import INPUT_IMAGES_SUBDIR, USER_INPUTS_DIR
from tools.calculate.calculate import calculate
from tools.database_search.database_search import make_database_search_tool
from tools.retrieve_attempt.retrieve_attempt import make_retrieve_attempt_tool
from tools.retrieve_user_inputs.retrieve_user_inputs import (
    make_retrieve_user_inputs_tool,
)
from workflow_settings import database_access

# Pure formatting helpers, IMPORTED rather than duplicated.  They carry
# no topology knowledge, and copying them is exactly the duplication
# that lets two copies drift apart.
from agents.orchestrator.orchestrator import (
    _first_line,
    _format_agent_history,
    _last_text_message,
    _truncate,
)

logger = logging.getLogger("propeller_agent")


# The chain agents that must carry a standing directive forward —
# everyone a Conductor directive is meant to reach.  Excludes the
# Conductor itself and the Receptionist (hub / user-facing): the
# Conductor re-stamps on its OUTGOING hop, so a block dropped on the way
# INTO it is not lost.
_DIRECTIVE_CARRIERS = frozenset({
    "user_input_inspector", "creator", "tool_caller", "dc_output_inspector",
})


_ROLE4_INSTRUCTIONS_PATH = Path(__file__).parent / "role4_feedback_instructions.md"


def _load_role4_instructions() -> str:
    """Role-4 (end-of-session feedback distribution) instructions.

    Held in a sibling ``.md`` and injected into the feedback-round
    trigger message ONLY when that pass runs, so the block does not ship
    in the live-pipeline system prompt on every turn.
    """
    return _ROLE4_INSTRUCTIONS_PATH.read_text(encoding="utf-8")


class Conductor(BaseChainAgent):
    """Hub of the 5-agent topology: plans, routes and approves."""

    AGENT_KEY = "conductor"

    def __init__(
        self,
        state: AgentState | None = None,
        session: Session | None = None,
        *,
        llm_cache=None,
    ):
        if session is None:
            raise TypeError(
                "Conductor requires a Session.  Construct one via "
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
        self.user_input_inspector = UserInputInspector(
            state=_state_for("user_input_inspector"), session=session,
        )
        self.creator = Creator(
            state=_state_for("creator"), session=session,
        )
        self.tool_caller = ToolCaller(
            state=_state_for("tool_caller"), session=session,
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
                           f"sharing the Conductor's LLM instead.")
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
        self.system_prompt = _build_template("conductor").format(
            user_inputs_dir=str(USER_INPUTS_DIR.resolve()),
            input_images_subdir=INPUT_IMAGES_SUBDIR,
            extraction_output_file=str(
                (USER_INPUTS_DIR / "extracted_inputs.txt").resolve()
            ),
        )

        # Registry for the dispatch driver
        self._agents_by_key: dict = {
            "conductor":            self,
            "user_input_inspector": self.user_input_inspector,
            "creator":              self.creator,
            "tool_caller":          self.tool_caller,
            "dc_output_inspector":  self.dc_output_inspector,
            "receptionist":         self.receptionist,
        }

        self._wire_routing()

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def _wire_routing(self) -> None:
        """Build per-agent tool sets and bind them.

        Each agent gets ONLY the routing tools it is allowed to use.
        ``build_routing_tool`` binds each tool to its CALLER: invoking it
        records an ``AgentHop`` on the caller's ``_pending_hop``, which
        the dispatcher reads once that caller's run loop exits.

        The 5-agent edge set is fixed — there is no PLANNER_FIRST or
        DC_INSPECTOR_ENABLED axis here.  The flow is:

            Receptionist -> UII -> Conductor -> Creator -> Tool Caller
            -> DC Output Inspector -> Conductor -> Receptionist
        """
        cl = self.session

        history_tool = build_read_agent_history_tool(self.get_agent_messages)

        # Receptionist — TWO forward doors.  It dispatches INTO the
        # pipeline (a message carrying design content goes to the UII)
        # and to the hub for everything else (an answer to a system
        # question, a control instruction, a restatement).
        self.receptionist.set_tools([
            history_tool,
            build_routing_tool(
                "receptionist", "user_input_inspector", self.receptionist, cl,
            ),
            build_routing_tool(
                "receptionist", "conductor", self.receptionist, cl,
            ),
        ])

        # UII — FORWARD/ESCALATE to the Conductor, and it may ask the
        # user a clarification DIRECTLY through the Receptionist.
        self.user_input_inspector.set_routing_tools(
            tools=[
                build_routing_tool("user_input_inspector", "conductor",
                                   self.user_input_inspector, cl),
                build_routing_tool("user_input_inspector", "receptionist",
                                   self.user_input_inspector, cl),
            ],
            next_agent="Conductor",
        )

        # Creator — FORWARD to the Tool Caller; CLARIFY and ESCALATE both
        # go to the Conductor via the same tool, differing only in the
        # intent it states.
        self.creator.set_routing_tools([
            build_routing_tool("creator", "tool_caller", self.creator, cl),
            build_routing_tool("creator", "conductor", self.creator, cl),
        ])

        # Tool Caller — FORWARD to the DCOI, CLARIFY back to the Creator
        # (whose values caused a tool failure, or whose set failed the
        # Tool Caller's own pre-generation range check), ESCALATE to the
        # Conductor.
        self.tool_caller.set_routing_tools(
            tools=[
                build_routing_tool("tool_caller", "dc_output_inspector",
                                   self.tool_caller, cl),
                build_routing_tool("tool_caller", "creator",
                                   self.tool_caller, cl),
                build_routing_tool("tool_caller", "conductor",
                                   self.tool_caller, cl),
            ],
            prev_agent="Creator",
        )

        # DC Output Inspector — re-render on the SAME attempt goes back
        # to the Tool Caller; everything else returns to the Conductor.
        self.dc_output_inspector.set_routing_tools([
            build_routing_tool("dc_output_inspector", "tool_caller",
                               self.dc_output_inspector, cl),
            build_routing_tool("dc_output_inspector", "conductor",
                               self.dc_output_inspector, cl),
        ])

        # Conductor — can dispatch to every agent.  Note it does NOT get
        # ``new_attempt``: the Creator is the sole owner of attempt
        # creation in this topology.
        cond_tools = [
            build_routing_tool("conductor", "receptionist", self, cl),
            build_routing_tool("conductor", "user_input_inspector", self, cl),
            build_routing_tool("conductor", "creator", self, cl),
            build_routing_tool("conductor", "tool_caller", self, cl),
            build_routing_tool("conductor", "dc_output_inspector", self, cl),
            calculate,
            list_attempts,
            read_attempt,
        ]
        if database_access.is_enabled_for(self.AGENT_KEY):
            cond_tools.append(make_database_search_tool(self.AGENT_KEY))
            cond_tools.append(make_retrieve_user_inputs_tool(self.AGENT_KEY))
            cond_tools.append(make_retrieve_attempt_tool(self.AGENT_KEY))
        self._tools_by_name = {t.name: t for t in cond_tools}
        self.llm = self.base_llm.bind_tools(cond_tools)

    # ------------------------------------------------------------------
    # Run loop — terminal on every routing tool (horizontal dispatch)
    # ------------------------------------------------------------------

    def run(self, message: str) -> AgentHop:
        """Process one incoming message and return the chosen hop."""
        self._pending_hop = None
        self.messages.append(HumanMessage(content=message))

        for _ in range(MAX_CONDUCTOR_STEPS):
            check_stop_or_raise()
            self.prune_history_if_needed()
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + self.messages,
                "Conductor",
            )
            self.messages.append(response)

            rendered_content = ai_text(response.content)
            if rendered_content:
                logger.info(f"[CONDUCTOR]  {rendered_content}")

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
                        logger.error(f"[CONDUCTOR TOOL ERROR] {name}: {exc}")

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
                 start_agent_key: str = "conductor") -> str:
        """Run the horizontal dispatch loop and return the user-facing text."""
        current = start_agent_key
        message = kickoff_message
        # A standing directive is issued fresh each user turn (the
        # Conductor re-derives it from the extraction when still
        # relevant), so a stale directive from a prior turn is never
        # forced onto — or leaked by — an unrelated later turn.
        self.session.standing_directives = ""
        conductor_visits = 0
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
                conductor_visits += 1
                if conductor_visits > MAX_CONDUCTOR_VISITS:
                    logger.warning("[DISPATCH] Max Conductor visits reached")
                    return self._surface_limit_to_user("max Conductor visits")

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
                _trace(source_display, "Error, Escalated to Conductor")

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

        tc_msg = _last_text_message(self.tool_caller)
        if tc_msg:
            summary_lines.append("Last Tool Caller report:")
            summary_lines.append(_truncate(tc_msg, 800))
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

    def reset(self) -> None:
        """Clear all agent histories for a fresh start."""
        self.messages.clear()
        self.session.chain_log_exchanges.clear()
        self.session.standing_directives = ""
        self.receptionist.reset()
        self.user_input_inspector.reset()
        self.creator.reset()
        self.tool_caller.reset()
        self.dc_output_inspector.reset()

    # ------------------------------------------------------------------
    # Live agent-history access (used by the read_agent_history tool)
    # ------------------------------------------------------------------

    _AGENT_KEY_ALIASES: dict = {
        "conductor": "conductor",
        "user input inspector": "user_input_inspector",
        "user_input_inspector": "user_input_inspector",
        "uii": "user_input_inspector",
        "creator": "creator",
        "dc output inspector": "dc_output_inspector",
        "dc_output_inspector": "dc_output_inspector",
        "dcoi": "dc_output_inspector",
        "tool caller": "tool_caller",
        "tool_caller": "tool_caller",
        "tc": "tool_caller",
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
        appends a ``HumanMessage(content=message, name="conductor")`` to
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
                    HumanMessage(content=msg, name="conductor")
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
            ("conductor",            self,                       self.system_prompt),
            ("receptionist",         self.receptionist,          getattr(self.receptionist, "system_prompt", None)),
            ("user_input_inspector", self.user_input_inspector,  getattr(self.user_input_inspector, "system_prompt", None)),
            ("creator",              self.creator,               getattr(self.creator, "system_prompt", None)),
            ("dc_output_inspector",  self.dc_output_inspector,   getattr(self.dc_output_inspector, "system_prompt", None)),
            ("tool_caller",          self.tool_caller,           getattr(self.tool_caller, "system_prompt", None)),
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
