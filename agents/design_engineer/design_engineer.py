"""Design Engineer — authors the parameter set AND generates from it.

Merges the topology-5 **DC Input Creator** and **Tool Caller** into one agent.
Where topology 5 runs ``DCIC -> Tool Caller -> DC Output Inspector``, the
Design Engineer does both halves inside ONE invocation and forwards straight
to the Requirements Analyst.

That "inside one invocation" is why its step budget is the SUM of its parents'
(``MAX_DESIGN_ENGINEER_STEPS``, 120 = DCIC 80 + TC 40) rather than the max: a
single turn reads the extraction, authors the full parameter set, opens the
attempt, writes it, and only then generates and renders.

**Built from the CURRENT parents, not from the retired 3-agent Designer.**
``agents/designer/designer.py`` was the same merge but was written against a
system that has since moved: it predated the one-shot routing retry entirely,
hard-coded ``AgentHop("architect", ...)`` where every live agent now resolves
``topology.hub_key()``, and still logged ``[CREATOR]``.  The run loop below is
taken from ``dc_input_creator.py`` and ``tool_caller.py`` as they stand.

Tool set — the union of both parents, with two deliberate notes:

* it reads the USER INPUTS DIRECTLY.  Topology 3 has no
  ``extracted_inputs.txt`` — nothing writes one — so there is no extraction
  to read.  The Requirements Analyst STATES what it found in its hand-off,
  and for anything it did not cover this agent reads the inputs itself.
  Its view lists the reference images by NAME but NOT by path: a path is
  worth having only to an agent that can open an image or relay it to one
  that can, and this agent is neither.  The names still matter, because the
  user refers to them.
* ``new_attempt_parameters`` (from the DCIC), NOT the retired Designer's split
  ``new_attempt`` + ``write_parameters``.  One call validates, creates the
  folder and writes into it, so the folder it creates is the folder it writes
  to and the two can never disagree.  It also makes the Designer's
  ``mesh_provenance_mismatches`` guard unnecessary BY CONSTRUCTION: that guard
  existed because a gap between the two calls let a mesh appear in the folder
  first, and there is no gap here.
* **NO image tools.**  Neither parent binds one, so the union has none.  Vision
  in topology 3 lives entirely in the Requirements Analyst — which is also
  why this agent is given image names rather than paths.

The ``@tool`` stub below is a LOCAL copy of the DC Input Creator's
rather than imports of them.  Their docstrings ARE the descriptions the model
reads, so importing would mean a topology-3 wording edit silently moving
topologies 5 and 7 — the isolation rule this rebuild is bound by.
"""

import json
import logging

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

from agents.shared.agent_activity import generic_tool
from agents.shared.attempts_tool import create_attempt, read_attempts
from agents.shared.base_chain_agent import BaseChainAgent
from agents.shared.dba_tools import dba_tools_for
from agents.shared.dc_primer import dc_primer_messages
from agents.shared.file_utils import (
    ai_text,
    flush_pending_image_blocks,
    strip_image_blocks_from_messages,
)
from agents.shared.llm_provider import (
    history_cache_control,
    make_system_message,
)
from agents.shared.llm_retry import invoke_with_retry
from agents.shared.prompts import (
    PARAMETER_NAMES,
    _build_template,
    _read_dc_fragment,
    routing_instructions,
)
from agents.shared.retrieve_tool_dispatcher import dispatch_retrieve_tool
from agents.shared.routing_tools import (
    AgentHop,
    ROUTING_TOOL_NAMES,
    begin_routing_retry,
    finalize_unanswered_tool_calls,
    finish_routing_retry,
    log_tool_call,
    stuck_escalation,
    tool_call_signature,
)
from agents.shared.session import AgentState, Session
from agents.shared.stop_signal import check_stop_or_raise
from agents.shared.topology import hub_key as _hub_key
from agents.shared.user_inputs_tool import (
    build_read_user_inputs,
    read_inputs_doc,
    read_user_inputs_summary,
)
from agents.shared import token_usage
from agents.step_caps import MAX_DESIGN_ENGINEER_STEPS
from tools import get_render_library, get_tools
from tools.render_blade_sections.render_blade_sections import render_blade_sections
from workflow_settings import blade_sections_access

logger = logging.getLogger("propeller_agent")


# ---------------------------------------------------------------------------
# Utility tool schemas (actual I/O handled by DesignEngineer)
# ---------------------------------------------------------------------------

@tool
def new_attempt_parameters(parameters: dict,
                           slug: str = "attempt",
                           description: str = "") -> str:
    """Open a NEW attempt folder and write the complete parameter set into it.

    One call does both, in this order: the parameter set is validated,
    then the attempt folder is created (timestamp + sequence number +
    ``slug``), then ``description.txt`` is recorded when a description is
    given, and finally the values are written to ``parameters.json``
    inside that same folder.

    There is no path argument — the folder this tool creates is the folder
    it writes into, so the two can never disagree.  Because validation
    happens first, a rejected call creates nothing and leaves no empty
    attempt behind.

    Args:
      parameters:  dict carrying ALL the design parameters listed in your
                   prompt, each mapped to a number.
      slug:        short, filename-safe label that appears in the folder
                   name after the timestamp + sequence number (e.g.
                   ``'4blades_thick_ring'``).  Optional.
      description: optional one-paragraph note explaining what this
                   attempt is for; written to ``description.txt``.

    Returns the new attempt's NUMBER and absolute folder path on success —
    put both on the ``Current attempt <N>:`` line of your hand-off — or an
    error naming the missing / unexpected / non-numeric fields, in which
    case nothing was created and nothing was written."""
    return ""  # Actual work is performed by _handle_write_tool.


class DesignEngineer(BaseChainAgent):
    """Stateful agent that authors the DC parameter set AND generates it."""

    AGENT_KEY = "design_engineer"

    def __init__(
        self,
        state: AgentState | None = None,
        session: Session | None = None,
        *,
        llm_cache=None,
    ):
        if session is None:
            raise TypeError(
                "DesignEngineer requires a Session.  Construct one via "
                "Session(...) or Session.create_for_v3(...) and pass it in."
            )
        if state is None:
            state = AgentState(agent_key=self.AGENT_KEY)
        super().__init__(state=state, session=session, llm_cache=llm_cache)
        # Schema-only stub: this agent's run loop handles the call itself.
        self._read_tool = build_read_user_inputs(
            doc=read_inputs_doc(self.AGENT_KEY))
        self._write_tool = new_attempt_parameters
        # From the Tool Caller half.  The render backend is chosen by
        # ``set_render_library`` before this agent is built.
        self.mesh_checks = session.mesh_checks
        self.render_library = get_render_library()
        self._routing_tools_by_name: dict = {}
        self._extra_utility_tools_by_name: dict = {}
        self.system_prompt: str = ""

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def set_routing_tools(self, tools: list) -> None:
        """Bind the Design Engineer's utility + routing tools.

        One positional argument, unlike the DC Input Creator's
        ``(tools, next_agent)`` and the Tool Caller's ``(tools, prev_agent)``:
        this class exists only under topology 3, whose edge set is fixed, so
        the neighbours are stated here rather than threaded in from the hub.
        """
        # Keyed by NAME, which also de-duplicates: ``get_tools()`` already
        # returns ``calculate``, and the DC Input Creator half binds it too.
        self._extra_utility_tools_by_name = {
            read_attempts.name: read_attempts,
        }
        for _t in get_tools():
            self._extra_utility_tools_by_name[_t.name] = _t
        # Blade-sections visualizer (global toggle).  Read fresh so a
        # Workflow-Settings edit takes effect on the next session.
        if blade_sections_access.is_enabled():
            self._extra_utility_tools_by_name[
                render_blade_sections.name] = render_blade_sections
        # Which of the three database tools this agent holds is a
        # per-(profile, agent, tool) decision; dba_tools_for owns it.
        for _dba_tool in dba_tools_for(self.AGENT_KEY):
            self._extra_utility_tools_by_name[_dba_tool.name] = _dba_tool

        all_tools = (
            # NO image tools: neither parent binds one, so the union has none.
            [self._read_tool, self._write_tool]
            + list(self._extra_utility_tools_by_name.values())
            + list(tools)
        )
        self.llm = self.base_llm.bind_tools(all_tools)
        self._routing_tools_by_name = {t.name: t for t in tools}

        routing_block = routing_instructions(
            agent_name="Design Engineer",
            next_agent="Requirements Analyst",
            prev_agent="Planner",
            fragment_name="routing_design_engineer.md",
        )
        # Mesh checks OFF => the render step emits no metrics at all, so a
        # backend's metric semantics would describe a report this agent never
        # receives.  Gated HERE rather than with markers because ``.format()``
        # runs AFTER apply_flag_filters — a marker inside the injected
        # fragment would never be filtered.
        #
        # Read HERE, not from the module-level RENDER_CHECK_LIBRARY_*
        # constants: those resolve at prompts-import time and would pin the
        # fragment to whatever SYSTEM_TOPOLOGY was on disk when the process
        # started, and the Sessions Queue switches topology between runs
        # inside one process.
        render_check_block = _read_dc_fragment(
            "tools_config/render_check_library/"
            + (
                ("pyvista" if self.render_library == "pyvista" else "trimesh")
                if self.mesh_checks
                else "off"
            )
            + ".md"
        )
        # Built fresh at construction time so live edits to .md fragments on
        # disk take effect on the NEXT session without a Python restart.
        self.system_prompt = _build_template(self.AGENT_KEY).format(
            routing_instructions=routing_block,
            render_check_library_block=render_check_block,
        )

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    def run(self, message: str) -> AgentHop:
        """Process one hand-off message and return the chosen hop."""
        token_usage.begin_turn("DEng")
        self._pending_hop = None
        self._routing_retry_used = False
        # Agnostic wording: this agent is called by the Planner AND by the
        # Requirements Analyst, so naming a sender here could only contradict
        # the "[Incoming from: ...]" label the routing tool already prepends.
        text = f"Hand-off from previous agent:\n{message}"
        self.messages.append(HumanMessage(content=text))

        seen_sigs: set[tuple[str, str]] = set()

        for _ in range(MAX_DESIGN_ENGINEER_STEPS):
            check_stop_or_raise()
            self.prune_history_if_needed()
            response = invoke_with_retry(
                self.llm,
                [make_system_message(self.system_prompt, self.provider)]
                + dc_primer_messages(self.provider, self.AGENT_KEY)
                + self.messages,
                "DEng",
                cache_control=history_cache_control(self.provider),
            )
            self.messages.append(response)

            if not response.tool_calls:
                raw = ai_text(response.content)
                if begin_routing_retry(self, raw, "DEng"):
                    continue
                bound = " / ".join(sorted(self._routing_tools_by_name)) \
                    or "any routing tool"
                return AgentHop(
                    _hub_key(),
                    "Error: Design Engineer produced a response with no "
                    "routing tool call — it wrote prose but did not invoke "
                    f"{bound}, so the pipeline would otherwise halt "
                    f"silently.  Its raw text was:\n\n{raw}",
                )

            routed = False
            for i, tc in enumerate(response.tool_calls):
                check_stop_or_raise()
                name = tc["name"]
                if name not in self._routing_tools_by_name:
                    sig = tool_call_signature(tc)
                    if sig in seen_sigs:
                        finalize_unanswered_tool_calls(
                            self.messages, response.tool_calls, i,
                        )
                        return stuck_escalation("Design Engineer", name)
                    seen_sigs.add(sig)
                if name == "read_user_inputs":
                    self._handle_read_tool(tc)
                    continue
                if name == "new_attempt_parameters":
                    self._handle_write_tool(tc)
                    continue
                # retrieve_* tools are dispatcher-handled (their @tool stubs
                # return "" — the dispatcher does the real R2 work and appends
                # the ToolMessage + any image content blocks).  Caught before
                # the utility lookup so the stub never runs.
                if dispatch_retrieve_tool(self, tc, self.AGENT_KEY):
                    continue
                if name in self._extra_utility_tools_by_name:
                    tool_fn = self._extra_utility_tools_by_name[name]
                    try:
                        result = tool_fn.invoke(tc["args"])
                    except Exception as exc:
                        result = f"Error calling {name}: {exc}"
                        logger.error(f"[DEng TOOL ERROR] {name}: {exc}")
                    log_tool_call(
                        self.AGENT_KEY, name, tc.get("args"), result,
                    )
                    self.messages.append(ToolMessage(
                        content=str(result),
                        tool_call_id=tc["id"],
                        name=name,
                    ))
                    continue
                if name in self._routing_tools_by_name:
                    tool_fn = self._routing_tools_by_name[name]
                    try:
                        result = tool_fn.invoke(tc["args"])
                    except Exception as exc:
                        result = f"Error calling {name}: {exc}"
                        logger.error(f"[DEng TOOL ERROR] {name}: {exc}")
                    self.messages.append(ToolMessage(
                        content=str(result),
                        tool_call_id=tc["id"],
                        name=name,
                    ))
                    if name in ROUTING_TOOL_NAMES and self._pending_hop is not None:
                        routed = True
                        finalize_unanswered_tool_calls(
                            self.messages, response.tool_calls, i + 1,
                        )
                        break
                else:
                    self.messages.append(ToolMessage(
                        content=f"Error: unknown tool '{name}'",
                        tool_call_id=tc["id"],
                        name=name,
                    ))

            # Flush any pending image content blocks as a single trailing
            # HumanMessage AFTER all ToolMessages for this AIMessage are
            # appended, preserving the tool_use -> tool_result contiguity rule
            # on Anthropic / OpenAI.  This agent binds no image tools, but the
            # retrieve_* dispatcher can still attach retrieved renders.
            flush_pending_image_blocks(self)

            if routed:
                finish_routing_retry(self)
                return self._pending_hop

        return AgentHop(
            _hub_key(),
            "Error: Design Engineer reached step limit without routing.",
        )

    # ------------------------------------------------------------------
    # read_user_inputs handler
    # ------------------------------------------------------------------

    @generic_tool("Read user inputs")
    def _handle_read_tool(self, tc: dict) -> None:
        """Read the user-inputs directory: text, notes, and image NAMES.

        ``include_image_paths=False`` is the whole point of this override.
        This agent binds no image tool and has nobody to relay one to, so a
        path would be an instruction it cannot act on; the NAMES stay,
        because the user refers to the images by name in their request.
        """
        summary = read_user_inputs_summary(
            tc.get("args", {}).get("path"),
            getattr(self, "provider", "openai"),
            can_view_images=False,
            include_image_paths=False,
            strip_timestamps=True,
            agent_key=self.AGENT_KEY,
        )
        log_tool_call(self.AGENT_KEY, tc["name"], tc.get("args"), summary)
        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    # ------------------------------------------------------------------
    # new_attempt_parameters handler
    # ------------------------------------------------------------------

    @generic_tool("Open attempt + write parameters")
    def _handle_write_tool(self, tc: dict) -> None:
        """Validate the parameter set, then create the attempt folder and
        write ``parameters.json`` into it.

        Validation runs FIRST so a rejected call never leaves an empty attempt
        folder behind.  There is no target-folder argument: this tool always
        writes into the folder it just created, so the append-only guarantee
        holds by construction.
        """
        args = tc.get("args", {}) or {}
        params = args.get("parameters")
        slug = args.get("slug") or "attempt"
        description = args.get("description") or ""
        # Names the LLM actually passed in this call — quoted back in error
        # messages so it cannot mistake a missing-argument error for a
        # tool-schema mismatch and externalise blame.
        provided_arg_names = sorted(args.keys())

        if not isinstance(params, dict):
            summary = (
                f"Error: YOUR call to new_attempt_parameters omitted the "
                f"'parameters' argument (you passed only "
                f"{provided_arg_names}).  This is NOT a tool-schema "
                f"problem - 'parameters' is REQUIRED; 'slug' and "
                f"'description' are optional.  RE-ISSUE the call with "
                f"'parameters' set to a dict containing exactly these "
                f"{len(PARAMETER_NAMES)} keys, each mapped to a "
                f"numeric value: {list(PARAMETER_NAMES)}.  Do NOT "
                f"report this as a tool-interface bug; the omission "
                f"is in your previous call's arguments."
            )
        elif not isinstance(slug, str) or not isinstance(description, str):
            summary = (
                "Error: 'slug' and 'description' must be strings when "
                "given.  Nothing was created."
            )
        else:
            provided = set(params.keys())
            expected = set(PARAMETER_NAMES)
            missing = sorted(expected - provided)
            extra = sorted(provided - expected)
            non_numeric = [
                k for k in PARAMETER_NAMES
                if k in params and not isinstance(params[k], (int, float))
                or isinstance(params.get(k), bool)
            ]
            if missing or extra or non_numeric:
                parts = [
                    "Error: no attempt was created and no parameters.json "
                    "was written."
                ]
                if missing:
                    parts.append(f"Missing keys: {missing}")
                if extra:
                    parts.append(f"Unexpected keys (remove them): {extra}")
                if non_numeric:
                    parts.append(
                        f"Non-numeric values (must be int or float): "
                        f"{non_numeric}"
                    )
                summary = "  ".join(parts)
            else:
                ordered = {k: params[k] for k in PARAMETER_NAMES}
                try:
                    attempt_n, dest = create_attempt(slug, description)
                except OSError as exc:
                    summary = f"Error creating attempt folder: {exc}"
                    logger.warning(f"[DEng] {summary}")
                else:
                    path = dest / "parameters.json"
                    try:
                        path.write_text(
                            json.dumps(ordered, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        summary = (
                            f"Created attempt {attempt_n} at "
                            f"{dest.resolve()} and wrote parameters.json "
                            f"({len(ordered)} fields) into it.  Hand this "
                            f"on as: Current attempt {attempt_n}: "
                            f"{dest.resolve()}"
                        )
                        logger.info(f"[DEng] {summary}")
                    except OSError as exc:
                        summary = (
                            f"Attempt {attempt_n} was created at "
                            f"{dest.resolve()} but parameters.json could "
                            f"not be written: {exc}"
                        )
                        logger.warning(f"[DEng] {summary}")

        log_tool_call(self.AGENT_KEY, tc["name"], tc.get("args"), summary)

        self.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))

    def on_operation_end(self) -> None:
        """End-of-operation hook called by the dispatcher.

        A no-op in practice: this agent binds no image tools, so its history
        normally holds no image blocks to strip.  Kept rather than dropped so
        the dispatcher's per-hop hook contract holds for every agent, and
        because the retrieve_* dispatcher CAN attach retrieved renders.
        """
        if self.keep_images_in_context:
            return
        removed = strip_image_blocks_from_messages(self.messages)
        if removed:
            logger.info(
                f"[DEng]  on_operation_end stripped {removed} image "
                f"block(s); paired path-text blocks retained."
            )

    def reset(self) -> None:
        self.messages.clear()
