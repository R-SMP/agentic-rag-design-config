"""The topology-5 hub — the Planner, doing the Orchestrator's job too.

Topology 5 is the 7-agent system MINUS the Orchestrator and MINUS the DC
Input Inspector.  With the Orchestrator gone somebody has to own the
dispatch loop, and the owner's edge list makes that the Planner: every
chain agent returns to it and it starts every cycle.

**This file began as a byte-for-byte copy of
``agents/orchestrator/orchestrator.py``** and was then re-pointed.  That is
deliberate, and is the build order the reduced-agent runbook prescribes: the
previous 5-agent hub (the Conductor) was written against an older 7-agent
system and silently carried its drift forward.  Copying the LIVE hub means
every fix made to it since is inherited rather than re-derived.

It keeps ``AGENT_KEY = "planner"``, so it needs no new row in any identity
registry -- ``AGENT_DISPLAY``, ``trace``, ``llm_defaults``, ``llm_routing``,
``dh_schedule``, ``database_access``, ``ocr_access`` and ``LR_BOXES`` all
already have one.  This is a different IMPLEMENTATION of the same agent,
not a different agent.

Differences from the Orchestrator, every one a consequence of the two
removals:

* it constructs neither a Planner (it IS the Planner) nor a DC Input
  Inspector, so ``_agents_by_key`` holds six entries rather than eight;
* it uses the PLANNER's prompt, so it fills that prompt's four runtime
  slots instead of the Orchestrator's ``chain_access_block``;
* it carries the Planner's ``_persist_plan`` / ``_save_plan_to_file``, so
  ``current_plan.txt`` keeps being written under topology 5;
* no ``PLANNER_FIRST`` or ``DC_INSPECTOR_ENABLED`` branching -- neither axis
  exists here (``prompts._planner_first_effective`` forces both off).

The dispatch contract is unchanged, so both hubs stay drop-in
interchangeable for ``agents/hub.py``: same seven public methods, same three
attributes.
"""

import logging
from datetime import datetime
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage

from agents.database_handler import DatabaseHandler
from agents.dc_input_creator import DCInputCreator
from agents.dc_output_inspector import DCOutputInspector
from agents.receptionist import Receptionist
from agents.planner.planner import read_extracted_inputs
from agents.shared.attempts_tool import read_attempts
from agents.shared.dc_params_tool import dc_params_list
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.context_pruner import ContextPruner
from agents.shared.file_utils import ai_text
from agents.shared.history_tool import build_read_agent_history_tool
from agents.shared.llm_provider import (
    history_cache_control,
    make_system_message,
)
from agents.shared.llm_retry import invoke_with_retry
from agents.shared import token_usage
from agents.shared.prompts import _build_template, routing_instructions
from agents.shared.stop_signal import is_stop_requested
from agents.shared.routing_tools import (
    AGENT_DISPLAY,
    AgentHop,
    DONE,
    ROUTING_TOOL_NAMES,
    build_routing_tool,
    log_tool_call,
)
from agents.shared.session import AgentState, Session
from agents.shared.user_inputs_tool import (
    build_read_user_inputs,
    read_inputs_doc,
)
from agents.shared import standing_directives
from agents.shared.trace import trace as _trace
from agents.step_caps import (
    MAX_DISPATCH_HOPS,
    MAX_PLANNER5_STEPS,
    MAX_PLANNER5_VISITS,
    MAX_SECTIONS_REFINE_ROUNDS,
)
from agents.shared.retrieve_tool_dispatcher import dispatch_retrieve_tool
from agents.shared.stop_signal import check_stop_or_raise
from agents.tool_caller import ToolCaller
from agents.user_input_inspector import UserInputInspector
from agents.shared.dba_tools import dba_tools_for
from agents.shared.hub_format import (
    _first_line,
    _format_agent_history,
    _last_text_message,
    _truncate,
)
from config import INPUT_IMAGES_SUBDIR, LOGS_DIR, USER_INPUTS_DIR

logger = logging.getLogger("propeller_agent")


# Component C — the chain agents that must carry a standing directive forward
# (everyone a Planner directive is meant to reach).  Excludes the Receptionist
# (user-facing) and the PLANNER, which here is the hub AND the issuer: stamping
# a directive onto a hop back into its own author is pointless.  The DC Input
# Inspector is absent because topology 5 never builds it.
#
# NOTE the dispatcher applies this to EVERY hop, not only hub-outgoing ones, so
# the DCOI -> DCIC precision edge is re-stamped like any other.
_DIRECTIVE_CARRIERS = frozenset({
    "user_input_inspector", "dc_input_creator",
    "tool_caller", "dc_output_inspector",
})


_ROLE4_INSTRUCTIONS_PATH = Path(__file__).parent / "role4_feedback_instructions.md"


def _load_role4_instructions() -> str:
    """Role-4 (end-of-session feedback distribution) instructions.

    Held in a sibling ``.md`` and injected into the feedback-round trigger
    message ONLY when that pass runs (see ``run_feedback_round``) — so the
    ~100-line block no longer ships in the hub's live-pipeline system
    prompt on every turn.
    """
    return _ROLE4_INSTRUCTIONS_PATH.read_text(encoding="utf-8")


class Planner5(BaseChainAgent):
    """The topology-5 hub: plans, dispatches and approves.

    Subclasses ``BaseChainAgent`` so it shares the (state, session,
    *, llm_cache) construction signature, the snapshot/restore
    plumbing, and the LLM-cache lookup with every other chain agent.
    The dispatch loop (``dispatch``) and the agent registry
    (``_agents_by_key``) are hub-specific.
    """

    AGENT_KEY = "planner"

    def __init__(
        self,
        state: AgentState | None = None,
        session: Session | None = None,
        *,
        llm_cache=None,
    ):
        if session is None:
            raise TypeError(
                "Planner5 requires a Session.  Construct one via "
                "Session(...) or Session.create_for_v3(...) and pass "
                "it in."
            )
        if state is None:
            state = session.agent_states.setdefault(
                self.AGENT_KEY, AgentState(agent_key=self.AGENT_KEY),
            )
        super().__init__(state=state, session=session, llm_cache=llm_cache)

        # Hub config flags read from session.  Held on self so call sites
        # that read self.* keep working without touching session.* directly.
        # ``dc_inspector_enabled`` is deliberately absent: topology 5 has no
        # DC Input Inspector to enable.
        self.rag_enabled = session.rag_enabled
        self.mesh_checks = session.mesh_checks
        self.dcoi_comparison_mode = session.dcoi_comparison_mode
        self.chain_access = session.chain_access

        # The chain log lives on session.chain_log_exchanges (per
        # v3 Phase 1 Q1 — session-scoped, not per-turn).  Routing
        # tools and dispatch read/write it directly via self.session.

        # Build every chain agent via the (state, session) path.
        # Each one's per-agent state is materialised into
        # session.agent_states under its own agent_key so subsequent
        # turns can rebuild the live agent from the snapshot.
        def _state_for(agent_key: str) -> AgentState:
            return session.agent_states.setdefault(
                agent_key, AgentState(agent_key=agent_key),
            )

        # NO ``self.planner``: this agent IS the Planner.  NO
        # ``self.dc_input_inspector``: topology 5 does not have one.
        self.receptionist = Receptionist(
            state=_state_for("receptionist"), session=session,
        )
        self.user_input_inspector = UserInputInspector(
            state=_state_for("user_input_inspector"), session=session,
        )
        self.dc_input_creator = DCInputCreator(
            state=_state_for("dc_input_creator"), session=session,
        )
        self.dc_output_inspector = DCOutputInspector(
            state=_state_for("dc_output_inspector"), session=session,
        )
        self.tool_caller = ToolCaller(
            state=_state_for("tool_caller"), session=session,
        )
        # Context Pruner gets its OWN LLM, built from its per-agent model
        # assignment, rather than sharing this hub's — so tiering it
        # independently (e.g. Test-1 Subject 5's "context_pruner: HIGH") takes
        # effect on the (rare) summarisation call.  Falls back to the
        # this hub's LLM on any resolution error, so a missing per-agent
        # entry can never block startup.  Exposed on the Session so every chain
        # agent's ``BaseChainAgent.prune_history_if_needed`` reaches it via
        # ``self.session.context_pruner``.  Pruning is gated by
        # ``workflow_settings.CONTEXT_PRUNER_ENABLED``.
        try:
            from agents.shared.llm_provider import build_llm as _build_pruner
            _pruner_llm, _, _pruner_model = _build_pruner("context_pruner")
            logger.info(f"[CP]  pruner LLM built: {_pruner_model}")
        except Exception as exc:
            logger.warning(f"[CP]  pruner LLM build failed ({exc}); "
                           f"sharing the hub's LLM instead.")
            _pruner_llm = self.base_llm
        self.context_pruner = ContextPruner(_pruner_llm)
        setattr(session, "context_pruner", self.context_pruner)
        # Learn real per-model context windows once per process, so the
        # Pruner's threshold tracks the model each agent actually runs on.
        # Anthropic-only (its /v1/models returns max_input_tokens; OpenAI's
        # does not expose a window), cached, and fail-open: any error leaves
        # the verified static table in place.
        try:
            from agents.shared.model_windows import refresh_from_api
            refresh_from_api()
        except Exception as exc:  # pragma: no cover - never block startup
            logger.warning(f"[CP]  model-window refresh skipped: {exc}")
        # Database Handler — runs ONLY post-session, after the user
        # types ``quit`` and confirms saving.  Not part of the
        # dispatch loop, has no routing tools, never speaks to the
        # user.  Held here so the loader can reach it via the
        # hub instance.  As of v3 Phase 1 commit 6, the DH
        # is a BaseChainAgent like every other agent, takes
        # (state, session), and reads from session.agent_states.
        self.database_handler = DatabaseHandler(
            state=_state_for("database_handler"), session=session,
        )

        # Hub-specific extras (BaseChainAgent already set
        # self.messages / self._pending_hop / self.llm / self.base_llm).
        self._tools_by_name: dict = {}

        # Registry for the dispatch driver.  SIX entries, not the
        # Orchestrator's eight: this agent is its own ``planner`` row, and
        # there is no ``orchestrator`` or ``dc_input_inspector``.
        self._agents_by_key: dict = {
            self.AGENT_KEY:         self,
            "user_input_inspector": self.user_input_inspector,
            "dc_input_creator":     self.dc_input_creator,
            "tool_caller":          self.tool_caller,
            "dc_output_inspector":  self.dc_output_inspector,
            "receptionist":         self.receptionist,
        }

        # Wire every agent's routing tools (including this hub's own).  The
        # system prompt is built at the END of ``_wire_routing`` -- the way the
        # chain Planner builds it inside ``set_routing_tools`` -- because the
        # PLANNER's prompt carries a ``{routing_instructions}`` slot that the
        # Orchestrator's did not.
        self._wire_routing()

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def _wire_routing(self) -> None:
        """Build per-agent tool sets and bind them.

        ``build_routing_tool`` binds each tool to its CALLER: invoking the
        tool records an ``AgentHop`` on the caller's ``_pending_hop``
        attribute; the dispatcher reads that hop once the caller's run loop
        exits.

        Unlike the Orchestrator's version there are NO branches.  Topology 5
        has no ``PLANNER_FIRST`` ordering to choose (the hub IS the planner)
        and no DC Input Inspector to switch in or out, so the edge set is
        fixed::

            Receptionist        -> Planner
            Planner (this hub)  -> Receptionist, UII, DCIC, DCOI
            UII                 -> Planner
            DCIC                -> Tool Caller, Planner
            Tool Caller         -> DCOI, DCIC
            DCOI                -> Tool Caller, DCIC, Planner

        Two absences are deliberate rather than oversights: the Planner has
        NO edge to the Tool Caller (work enters the DC loop through the
        DCIC), and the Tool Caller has NO edge to the Planner -- it is the
        one agent that cannot escalate.

        For the UII and the DCIC, FORWARD and ESCALATE collapse into the SAME
        ``call_planner`` tool, because the agent they forward to and the hub
        they escalate to are now one agent.
        """
        cl = self.session

        # Shared history-reading tool, bound to this hub's live provider.
        history_tool = build_read_agent_history_tool(self.get_agent_messages)

        # Receptionist -- read_agent_history (to answer simple questions on
        # its own) plus the one door into the pipeline.
        self.receptionist.set_tools([
            history_tool,
            build_routing_tool(
                "receptionist", self.AGENT_KEY, self.receptionist, cl,
            ),
        ])

        # UII -- one edge back to the hub; it is both the forward target and
        # the escalation target.
        self.user_input_inspector.set_routing_tools(
            tools=[
                build_routing_tool("user_input_inspector", self.AGENT_KEY,
                                   self.user_input_inspector, cl),
            ],
            next_agent="Planner",
        )

        # DCIC -- FORWARD to the Tool Caller (no DCII to pass through),
        # CLARIFY / ESCALATE back to the hub.
        self.dc_input_creator.set_routing_tools(
            tools=[
                build_routing_tool("dc_input_creator", "tool_caller",
                                   self.dc_input_creator, cl),
                build_routing_tool("dc_input_creator", self.AGENT_KEY,
                                   self.dc_input_creator, cl),
            ],
            next_agent="Tool Caller",
        )

        # Tool Caller -- forward to the DCOI, back to the DCIC to clarify.
        # No edge to the hub: this is the agent that cannot escalate.
        self.tool_caller.set_routing_tools(
            tools=[
                build_routing_tool("tool_caller", "dc_output_inspector",
                                   self.tool_caller, cl),
                build_routing_tool("tool_caller", "dc_input_creator",
                                   self.tool_caller, cl),
            ],
            prev_agent="DC Input Creator",
        )

        # DCOI -- three edges.  The DCIC one replaces the 7-agent precision
        # relay: there the DCOI returned to the Orchestrator and the
        # Orchestrator passed the gap description on to the DCIC, so with no
        # Orchestrator the DCOI addresses the DCIC directly.
        self.dc_output_inspector.set_routing_tools([
            build_routing_tool("dc_output_inspector", "tool_caller",
                               self.dc_output_inspector, cl),
            build_routing_tool("dc_output_inspector", "dc_input_creator",
                               self.dc_output_inspector, cl),
            build_routing_tool("dc_output_inspector", self.AGENT_KEY,
                               self.dc_output_inspector, cl),
        ])

        # This hub -- the Orchestrator's reach minus the retired DCII and
        # minus the Tool Caller, plus the PLANNER's own utility tools.
        #
        # The utility set is the Planner's, not the Orchestrator's, and that
        # is load-bearing: this agent runs the PLANNER's prompt, which
        # documents ``read_user_inputs`` and ``read_extracted_inputs``.  A
        # prompt naming a tool the class does not bind is exactly the defect
        # the first 5-agent live run hit -- two wasted hops and the only tool
        # error in the run.
        read_user_inputs = build_read_user_inputs(
            doc=read_inputs_doc(self.AGENT_KEY),
            direct_provider=getattr(self, "provider", "openai"),
        )
        hub_tools = [
            read_user_inputs,
            read_extracted_inputs,
            history_tool,
            read_attempts,
            dc_params_list,
            build_routing_tool(self.AGENT_KEY, "user_input_inspector",
                               self, cl),
            build_routing_tool(self.AGENT_KEY, "dc_input_creator", self, cl),
            build_routing_tool(self.AGENT_KEY, "dc_output_inspector",
                               self, cl),
            build_routing_tool(self.AGENT_KEY, "receptionist", self, cl),
        ]
        # Which of the three database tools this agent holds is a
        # per-(profile, agent, tool) decision; dba_tools_for owns it.
        hub_tools.extend(dba_tools_for(self.AGENT_KEY))
        self._tools_by_name = {t.name: t for t in hub_tools}
        self.llm = self.base_llm.bind_tools(hub_tools)

        # The PLANNER's prompt, with the PLANNER's four runtime slots.  Built
        # here rather than in __init__ because ``{routing_instructions}`` is
        # only meaningful once the edge set above is settled -- the same
        # reason the chain Planner builds it inside ``set_routing_tools``.
        #
        # ``next_agent`` / ``prev_agent`` mirror the chain Planner's UII-first
        # values so the assembled prompt starts out identical to topology 7's.
        # Both are suppressed by the reduced routing-section set today (only
        # the fragment and the mandate survive), so they change nothing until
        # that set does.
        routing_block = routing_instructions(
            agent_name="Planner",
            next_agent="DC Input Creator",
            prev_agent="User Input Inspector",
            fragment_name="routing_planner_uii_first.md",
        )
        # Built fresh at construction time so live edits to .md fragments on
        # disk take effect on the NEXT session without a Python restart.
        self.system_prompt = _build_template(self.AGENT_KEY).format(
            routing_instructions=routing_block,
            user_inputs_dir=str(USER_INPUTS_DIR.resolve()),
            input_images_subdir=INPUT_IMAGES_SUBDIR,
            extraction_output_file=str(
                (USER_INPUTS_DIR / "extracted_inputs.txt").resolve()
            ),
        )

    # ------------------------------------------------------------------
    # Run loop — terminal on every routing tool (horizontal dispatch)
    # ------------------------------------------------------------------

    def run(self, message: str) -> AgentHop:
        """Process one incoming message and return the chosen hop."""
        token_usage.begin_turn("Planner")
        self._pending_hop = None
        self.messages.append(HumanMessage(content=message))

        for _ in range(MAX_PLANNER5_STEPS):
            check_stop_or_raise()
            self.prune_history_if_needed()
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + self.messages,
                "Planner",
                cache_control=history_cache_control(self.provider),
            )
            self.messages.append(response)

            rendered_content = ai_text(response.content)
            if rendered_content:
                logger.info(f"[PLANNER]  {rendered_content}")

            if not response.tool_calls:
                final = rendered_content
                if not final or not final.strip():
                    final = (
                        "The Planner produced no user-facing text this "
                        "turn (empty response from the model).  This is "
                        "likely a coordination bug; please re-send your "
                        "last request."
                    )
                self._persist_plan(response, pending_hop=None)
                return AgentHop(DONE, final)

            routed = False
            for tc in response.tool_calls:
                check_stop_or_raise()
                name = tc["name"]
                # Phase 5E: retrieve_* tools are dispatcher-handled
                # (their @tool stubs return "" — the dispatcher does
                # the real R2 work and appends the ToolMessage +
                # image content blocks).  Catch them before the
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
                        logger.error(f"[PLANNER TOOL ERROR] {name}: {exc}")

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

            # The Planner's plan artefact: capture this turn's long
            # (response content) and short (routing message) halves and write
            # them to current_plan.txt, exactly as the 7-agent Planner does.
            self._persist_plan(response, pending_hop=self._pending_hop)

            if routed:
                return self._pending_hop

        # The inner loop exhausted its budget without routing or
        # producing plain text.  Bail out as DONE so the dispatcher
        # does not loop indefinitely.
        return AgentHop(
            DONE,
            "The Planner produced no routing decision this turn.",
        )

    # ------------------------------------------------------------------
    # Plan persistence — lifted VERBATIM from agents/planner/planner.py
    #
    # The hub is the Planner, so it keeps writing current_plan.txt.  Copied
    # rather than imported because both are methods on a class, and copied
    # from the SOURCE SPANS with ast rather than re-typed, so the text is
    # exact.  If the 7-agent Planner's version changes, this one does not —
    # which is the intended topology separation, not drift.
    # ------------------------------------------------------------------

    def _persist_plan(self, response, pending_hop) -> None:
        """Capture the long and short parts of this turn's plan and
        write them to ``current_plan.txt``."""
        long_plan = ai_text(getattr(response, "content", "")).strip()
        short_plan = (
            pending_hop.message.strip()
            if pending_hop is not None
            and getattr(pending_hop, "message", "")
            else ""
        )
        if not long_plan and not short_plan:
            return

        sections: list[str] = []
        if long_plan:
            sections.append(
                "--- Full plan (Planner's reasoning; Part 1, response "
                "content) ---\n" + long_plan
            )
        else:
            sections.append(
                "--- Full plan (Planner's reasoning; Part 1, response "
                "content) ---\n"
                "(Not produced as natural-language content this turn — "
                "the LLM placed everything in the routing tool's "
                "message argument; see the short version below.)"
            )
        if short_plan:
            sections.append(
                "--- Short actionable message (Part 2, routing tool's "
                "message argument) ---\n" + short_plan
            )
        else:
            sections.append(
                "--- Short actionable message (Part 2, routing tool's "
                "message argument) ---\n"
                "(None recorded — the LLM did not invoke a routing "
                "tool this turn.)"
            )

        self.current_plan = "\n\n".join(sections)
        self._save_plan_to_file()

    def _save_plan_to_file(self) -> None:
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            plan_path = LOGS_DIR / "current_plan.txt"
            plan_path.write_text(
                f"Plan updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                f"\n\n{self.current_plan}\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Dispatcher — the top-level horizontal driver
    # ------------------------------------------------------------------

    def dispatch(self, kickoff_message: str,
                 start_agent_key: str = "") -> str:
        """Run the horizontal dispatch loop and return the user-facing text."""
        current = start_agent_key or self.AGENT_KEY
        message = kickoff_message
        # Component C: a standing directive is issued fresh each user turn
        # (the Planner re-derives it from the extraction when still relevant),
        # so a stale directive from a prior turn is never forced onto — or
        # leaked by — an unrelated later turn.  Within-turn persistence is
        # unaffected: capture happens later in THIS dispatch and the field is
        # session-scoped for the rest of the loop.
        self.session.standing_directives = ""
        # Cursor into the SESSION-scoped chain log.  Initialised to the
        # log's current length so the per-turn chain-access view shows
        # only exchanges produced during THIS dispatch call, not prior
        # turns' exchanges (per v3 Phase 1 Q1: chain_log is session-
        # scoped, but the hub's "what happened while I was
        # waiting" feature stays per-turn).
        orch_chain_log_cursor = len(self.session.chain_log_exchanges)
        orch_visits = 0
        first_orch_entry = True
        # A6 (precision sections): count refine ROUNDS while a standing
        # directive is active — one round per hop into the DCOI.  A local
        # here (not on the session) because a precision loop lives entirely
        # within ONE dispatch call (one user turn).
        precision_rounds = 0

        for _ in range(MAX_DISPATCH_HOPS):
            # Cooperative-stop check: the web UI's Stop button sets
            # the shared flag, and we honour it at each hop boundary
            # (the currently-running step has already finished by the
            # time we get back here).  We surface a clear message to
            # the user and return — the next /api/turn auto-clears
            # the flag so subsequent turns proceed normally.
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
                if self.chain_access and not first_orch_entry:
                    new_exchanges = self.session.chain_log_exchanges[
                        orch_chain_log_cursor:
                    ]
                    if new_exchanges:
                        block_lines = [
                            "--- Inter-agent messages recorded while you "
                            "were waiting ---"
                        ]
                        for ex in new_exchanges:
                            block_lines.append(
                                f"\n[FROM {ex['from_agent']}, "
                                f"TO {ex['to_agent']}]:\n{ex['message']}"
                            )
                        block_lines.append(
                            "\n--- End of inter-agent messages; hand-off "
                            "below ---"
                        )
                        message = (
                            "\n".join(block_lines) + "\n\n" + message
                        )
                first_orch_entry = False
                orch_visits += 1
                if orch_visits > MAX_PLANNER5_VISITS:
                    logger.warning("[DISPATCH] Max Planner visits reached")
                    return self._surface_limit_to_user(
                        "max Planner visits"
                    )

            hop = agent.run(message)

            # Operation-end hook (Change #2).  An "operation" ends when
            # an agent's run() returns — i.e. the LLM invoked a routing
            # tool (or otherwise handed off).  Utility tool calls
            # inside run() do NOT trigger this since run() doesn't
            # return until the LLM routes.  Image-consuming agents use
            # this to strip image bytes from history when KEEP IMAGES
            # IN CONTEXT is OFF, leaving paired path-text blocks
            # behind.  Non-image agents (and image agents in KEEP=ON
            # mode) just no-op.
            on_op_end = getattr(agent, "on_operation_end", None)
            if callable(on_op_end):
                try:
                    on_op_end()
                except Exception as exc:  # pragma: no cover
                    logger.warning(
                        f"[DISPATCH] on_operation_end failed for "
                        f"{current}: {exc}"
                    )

            if current == self.AGENT_KEY:
                orch_chain_log_cursor = len(self.session.chain_log_exchanges)

            if not isinstance(hop, AgentHop):
                # Defensive guard — every agent must return AgentHop.
                return str(hop)

            # [AGENT MSG] is normally emitted by the routing tool when the
            # LLM invokes it.  When an agent's run loop returns an
            # hub-bound hop WITHOUT having invoked the tool
            # (error fall-through, step-limit exhaustion, empty
            # tool_calls), the routing-tool logger never fires.  Emit the
            # log line here so mid-chain resumes are still visible in the
            # session log.
            if (
                hop.target == self.AGENT_KEY
                and current != self.AGENT_KEY
                and getattr(agent, "_pending_hop", None) is None
            ):
                source_display = AGENT_DISPLAY.get(current, current)
                hub_display = AGENT_DISPLAY.get(self.AGENT_KEY, self.AGENT_KEY)
                logger.info(
                    f"[AGENT MSG]  {source_display} -> {hub_display}\n"
                    f"{hop.message}"
                )
                _trace(source_display, f"Error, Escalated to {hub_display}")

            if hop.target == DONE:
                return hop.message

            # A6 (precision sections): a refine ROUND is one hop into the DCOI
            # while a precision standing directive is active.  When the loop
            # exceeds its hard cap, DROP the directive (so the DCOI is no longer
            # bound to keep iterating) and tell it to finalize with the best
            # attempt + report the residual honestly.  This is the graceful code
            # backstop behind the DCOI's own Satisfied/Plateau prose judgments,
            # so a stuck loop can never run forever regardless of prose.  Runs
            # BEFORE the re-stamp block below, so clearing the field here makes
            # that block's ensure_present a no-op (it won't re-add the directive).
            # Keyed on ANY active directive because precision section-matching is
            # the only directive TYPE today, and only its tight loop can reach 9
            # DCOI hops in one turn — an ordinary directive leaves the DCOI at
            # its usual 1-3 visits, far under the cap.  If a non-precision
            # directive type is ever added, gate this on it being a precision one
            # (the finalize note below is sections-specific).
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

            # Component C: capture a Planner-issued standing directive, then
            # re-stamp it onto any forward hand-off that dropped it (the loss
            # backstop).  The directive is verbose text carried IN the messages,
            # not a flag; only the Planner may set one.  ensure_present is a
            # no-op when nothing is active or the block is still intact — so it
            # re-stamps ONLY on detected loss.
            if current == self.AGENT_KEY:
                _issued = standing_directives.extract_directive(hop.message)
                if _issued:
                    # A6b: a FRESH / changed Planner directive begins a NEW
                    # precision PHASE (e.g. sections converged → the 3D check),
                    # so reset the per-phase refine-round budget.  Only the
                    # Planner issues directives + it is not re-invoked per round,
                    # so this fires just at phase boundaries, giving each phase
                    # its own ~MAX_SECTIONS_REFINE_ROUNDS (user choice: separate
                    # budget per phase).
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

        # This hub IS the Planner, so the plan lives on self (restored by
        # BaseChainAgent and written by _persist_plan).
        plan = getattr(self, "current_plan", "")
        if plan:
            summary_lines.append("Latest Planner plan:")
            summary_lines.append(_truncate(plan, 600))
            summary_lines.append("")

        summary = "\n".join(summary_lines).rstrip()
        last_attempted = ""
        if exchanges:
            ex = exchanges[-1]
            last_attempted = (
                f"{ex['from_agent']} -> {ex['to_agent']}: "
                f"{_first_line(ex['message'], limit=160)}"
            )

        fallback = (
            f"The Planner could not settle a plan within its step "
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

        Vestigial in v3: the chain log is session-scoped (per Phase 1
        Q1) and the per-turn "what happened while I was waiting" view
        is reconstructed via a cursor inside ``dispatch`` rather than
        by clearing anything.  Kept as a no-op so the loader's call
        site stays stable; remove together with the loader call when
        the v3 loader rewrite lands.
        """
        return None

    def reset(self) -> None:
        """Clear all agent histories for a fresh start."""
        self.messages.clear()
        self.session.chain_log_exchanges.clear()
        self.session.standing_directives = ""
        self.current_plan = ""
        self.receptionist.reset()
        self.user_input_inspector.reset()
        self.dc_input_creator.reset()
        self.dc_output_inspector.reset()
        self.tool_caller.reset()

    # ------------------------------------------------------------------
    # Live agent-history access (used by the read_agent_history tool)
    # ------------------------------------------------------------------

    _AGENT_KEY_ALIASES: dict = {
        "planner": "planner",
        "user input inspector": "user_input_inspector",
        "user_input_inspector": "user_input_inspector",
        "uii": "user_input_inspector",
        "dc input creator": "dc_input_creator",
        "dc_input_creator": "dc_input_creator",
        "dcic": "dc_input_creator",
        "dc output inspector": "dc_output_inspector",
        "dc_output_inspector": "dc_output_inspector",
        "dcoi": "dc_output_inspector",
        "tool caller": "tool_caller",
        "tool_caller": "tool_caller",
        "tc": "tool_caller",
        "receptionist": "receptionist",
        # The hub answers to its own name and to "orchestrator": prompts and
        # users carried over from the 7-agent system still say the latter, and
        # resolving it here costs nothing.
        "orchestrator": "planner",
        "hub": "planner",
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
        """Drive the hub through ONE forced ``submit_feedback_dispatch``
        tool call that decides, per chain agent, whether the user's
        end-of-session feedback contains material worth forwarding to
        that agent — and if so, what exact text to forward.

        Side effect on success: for every dispatch with ``send=True``,
        appends a ``HumanMessage(content=message, name=<hub key>)``
        to the target's LIVE ``self.messages`` AND mirrors the agent's
        new ``snapshot_state()`` into ``self.session.agent_states[<key>]``.
        The Database Handler reads from the session's ``agent_states``
        when interviewing each agent post-session, so the feedback
        becomes part of that interview's context.

        This method DOES NOT mutate the hub's own
        ``self.messages`` — the feedback round is a separate
        post-session pass, NOT part of the live design pipeline.  The
        tool is bound for ONE turn only (W18 / W20 force-tool pattern)
        and discarded immediately afterwards; the permanent ``orch_tools``
        binding installed by ``_wire_routing`` is untouched.

        Args:
            satisfaction:    "yes" / "partially" / "no" — the y/p/n
                             toggle the user picked in the End Session
                             modal.
            what_went_well:  Free-text field, may be empty when the
                             user didn't elaborate.
            what_went_wrong: Free-text field, may be empty.

        Returns:
            ``{"ok": bool, "decisions": [{"agent_key", "send", "message"}, ...],
               "error": str | None}``.  When the LLM call or tool-call
            parsing fails, ``ok`` is False and ``decisions`` is empty.
        """
        from agents.orchestrator.feedback_tool import (
            feedback_envelope,
            submit_feedback_dispatch,
            SUBMIT_FEEDBACK_DISPATCH_TOOL_NAME,
        )

        # Target set: every chain agent in the registry except the
        # hub itself (the hub collects/dispatches,
        # never receives feedback).  Adapts to ``dc_inspector_enabled``
        # automatically because DCII is only inserted into
        # ``_agents_by_key`` when enabled... actually DCII is ALWAYS in
        # the registry (orchestrator.py:188-197) but its routing tools
        # are only wired when enabled — so we explicitly drop it from
        # the feedback target set when disabled to avoid forwarding
        # feedback to a dormant agent.
        target_keys: list[str] = []
        for k in self._agents_by_key.keys():
            if k == self.AGENT_KEY:
                continue
            target_keys.append(k)

        # Build the per-turn forced-tool LLM binding.  This is a LOCAL
        # binding — it does NOT mutate self.llm (which is the
        # permanently-tool-bound design-pipeline LLM).  W20 mirrors
        # the DH's W18 invariant: this tool is never on self.llm.
        try:
            feedback_llm = self.base_llm.bind_tools(
                [submit_feedback_dispatch],
                tool_choice=SUBMIT_FEEDBACK_DISPATCH_TOOL_NAME,
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                f"[ORCHESTRATOR-FEEDBACK]  could not bind "
                f"submit_feedback_dispatch: {type(exc).__name__}: "
                f"{exc}; treating as empty dispatch list."
            )
            return {"ok": False, "decisions": [], "error": str(exc)}

        # Compose the instruction message.  This is a TRANSIENT message
        # list (we do NOT append to self.messages) so the design
        # pipeline's history stays clean.  The Role-4 instructions live in
        # a sibling .md (injected here by CONCATENATION — not str.format —
        # so its literal JSON braces survive) rather than in the live
        # system prompt; prepend them, then add the user's three fields
        # plus the live target list.
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
                "Orchestrator-feedback-dispatch",
                # NO history breakpoint here on purpose.  This call sends a
                # freshly-built one-off list ([system] + [instruction]) rather
                # than the persistent self.messages, so ``instruction`` differs
                # every time and an automatic breakpoint placed on it would
                # write an entry no later request can ever match — a pure cache
                # WRITE premium with no offsetting read.  The system prompt is
                # still cached: make_system_message applies its own explicit
                # breakpoint, and that prefix IS stable across these calls.
            )
        except Exception as exc:
            logger.warning(
                f"[ORCHESTRATOR-FEEDBACK]  LLM call raised "
                f"{type(exc).__name__}: {exc}; treating as empty "
                f"dispatch list."
            )
            return {"ok": False, "decisions": [], "error": str(exc)}

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            logger.warning(
                "[ORCHESTRATOR-FEEDBACK]  response carried no tool_calls "
                "despite tool_choice=submit_feedback_dispatch; "
                "treating as empty dispatch list."
            )
            return {"ok": False, "decisions": [], "error": "no_tool_call"}

        tc = tool_calls[0]
        args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
        dispatches = (args or {}).get("dispatches") or []
        if not isinstance(dispatches, list):
            logger.warning(
                f"[ORCHESTRATOR-FEEDBACK]  expected `dispatches` to be "
                f"a list; got {type(dispatches).__name__!r}."
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
                    f"[ORCHESTRATOR-FEEDBACK]  dispatch agent_key "
                    f"{ak!r} not in target set; skipping."
                )
                continue
            if ak in seen_keys:
                logger.warning(
                    f"[ORCHESTRATOR-FEEDBACK]  duplicate dispatch for "
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
                                  name=self.AGENT_KEY)
                )
                self.session.agent_states[ak] = target.snapshot_state()
            except Exception as exc:
                logger.warning(
                    f"[ORCHESTRATOR-FEEDBACK]  could not append "
                    f"feedback to {ak!r}: {type(exc).__name__}: {exc}"
                )
                applied.append({"agent_key": ak, "send": False, "message": ""})
                continue
            applied.append({"agent_key": ak, "send": True, "message": msg})

        # Surface a summary in the session log so the operator can see
        # which agents received feedback at a glance.
        sent = [d["agent_key"] for d in applied if d.get("send")]
        skipped = [d["agent_key"] for d in applied if not d.get("send")]
        logger.info(
            f"[ORCHESTRATOR-FEEDBACK]  round complete — "
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
            (self.AGENT_KEY,         self,                       self.system_prompt),
            ("receptionist",         self.receptionist,          getattr(self.receptionist, "system_prompt", None)),
            ("user_input_inspector", self.user_input_inspector,  getattr(self.user_input_inspector, "system_prompt", None)),
            ("dc_input_creator",     self.dc_input_creator,      getattr(self.dc_input_creator, "system_prompt", None)),
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
