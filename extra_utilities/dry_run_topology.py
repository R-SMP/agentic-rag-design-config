"""Drive ONE COMPLETE TURN with every LLM replaced by a scripted fake.

The point is to exercise the parts of a session that cost nothing to run
and everything to get wrong: agent construction, prompt assembly off
disk, tool binding, the routing graph, and the dispatch loop.  No network
call, no token spend, no model judgement.

    py -3.13 extra_utilities/dry_run_topology.py              # topology 5
    py -3.13 extra_utilities/dry_run_topology.py --topology 7

What it CAN catch: a missing prompt fragment, an unfilled ``{slot}``, an
agent that fails to construct, a routing tool bound to an agent the
topology does not build, a hop to an unknown agent key, a dispatch loop
that never terminates.

What it CANNOT catch: whether the agents ROUTE SENSIBLY.  Every routing
decision here is scripted by the table below, so this proves the pipeline
runs -- never that the prompts are any good.  Only a real run does that.

Design notes, each one a trap that cost a debugging cycle to find:

* ``build_hub(session, llm_cache=...)`` reaches the HUB ONLY.  Planner5
  constructs its five sub-agents without forwarding the cache, so they
  fall back to the module.  The patch therefore has to be on
  ``agents.shared.llm_client_cache.get_for_agent`` itself.
* The Context Pruner bypasses the cache entirely and calls
  ``llm_provider.build_llm`` directly, so that needs its own patch.  It
  fails open, so leaving it would silently build a real client.
* ``self.llm`` is what the run loops invoke, and it is the object
  ``bind_tools`` returned -- so the fake needs both methods.
* A chain agent that returns prose does not end its turn: it triggers the
  one-shot routing retry and is invoked AGAIN.  Only the Receptionist
  treats prose as the answer.  Scripted routes avoid the retry entirely.
* Scripted tool calls are EXECUTED for real, so this scripts routing
  calls only.  ``new_attempt_parameters`` would create attempt folders
  and ``generate_and_render_propeller`` needs trimesh, which is not
  installed here.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# trimesh is not installed in this environment, and importing anything
# under ``agents.`` pulls the whole agent tree; the prompt_pdf bootstrap
# is the repo's existing way round that.
sys.path.insert(0, str(HERE / "prompt_pdf"))
sys.modules.setdefault("simplejson", None)          # type: ignore[arg-type]
sys.modules.setdefault("chardet", None)             # type: ignore[arg-type]
import bootstrap                                    # noqa: E402

bootstrap.install()
sys.path.insert(0, str(REPO))

from langchain_core.messages import AIMessage       # noqa: E402


# ---------------------------------------------------------------------------
# The scripted routes
# ---------------------------------------------------------------------------
#
# agent key -> the target it routes to on its 1st, 2nd, ... invoke.
# ``None`` means "answer in prose", which ends the turn for the
# Receptionist and triggers the routing retry for anyone else.
#
# These follow each topology's real edge set; a target outside the
# calling agent's bound set comes back as ``Error: unknown tool`` instead
# of a hop, which is itself a finding worth surfacing.

ROUTES = {
    5: {
        "receptionist":         ["planner", None],
        "planner":              ["user_input_inspector",
                                 "dc_input_creator",
                                 "receptionist"],
        "user_input_inspector": ["planner"],
        "dc_input_creator":     ["tool_caller"],
        "tool_caller":          ["dc_output_inspector"],
        "dc_output_inspector":  ["planner"],
    },
    7: {
        "receptionist":         ["orchestrator", None],
        "orchestrator":         ["user_input_inspector",
                                 "planner",
                                 "dc_input_creator",
                                 "receptionist"],
        "user_input_inspector": ["orchestrator"],
        "planner":              ["orchestrator"],
        "dc_input_creator":     ["dc_input_inspector"],
        "dc_input_inspector":   ["tool_caller"],
        "tool_caller":          ["dc_output_inspector"],
        "dc_output_inspector":  ["orchestrator"],
    },
}

TRACE: list[str] = []
UNSCRIPTED: list[str] = []


class FakeLLM:
    """One scripted model, standing in for a single agent's client."""

    def __init__(self, agent_key: str, route: list):
        self.agent_key = agent_key
        self.route = list(route)
        self.n = 0

    # bind_tools is called once per agent at wiring time, and the object
    # it returns is stored as self.llm and invoked by the run loop.
    # tool_choice= is passed on the feedback-round path, hence **kwargs.
    def bind_tools(self, tools, **kwargs):
        self.tool_names = [getattr(t, "name", str(t)) for t in tools]
        return self

    # cache_control= is passed for anthropic providers, hence **kwargs.
    def invoke(self, messages, **kwargs):
        i = self.n
        self.n += 1
        if i >= len(self.route):
            UNSCRIPTED.append(f"{self.agent_key} (invoke #{i})")
            # Do NOT loop: an unscripted agent would otherwise be invoked
            # up to its step cap before the dispatcher gave up.
            raise AssertionError(
                f"unscripted invoke: {self.agent_key} #{i} -- the route "
                f"table has {len(self.route)} entry/entries for it"
            )
        target = self.route[i]
        if target is None:
            TRACE.append(f"{self.agent_key} -> (prose, ends turn)")
            return AIMessage(content=f"[dry run] final reply from "
                                     f"{self.agent_key}.", tool_calls=[])
        TRACE.append(f"{self.agent_key} -> call_{target}")
        return AIMessage(
            content="",
            tool_calls=[{
                "name": f"call_{target}",
                "args": {"message": f"[dry run] {self.agent_key} hands off "
                                    f"to {target}."},
                "id": f"{self.agent_key}-{i}",
            }],
        )


def install_fakes(routes: dict) -> None:
    """Patch BOTH places an agent's model can come from."""
    import agents.shared.llm_client_cache as cache
    import agents.shared.llm_provider as provider

    made: dict[str, FakeLLM] = {}

    def get_for_agent(agent_key: str):
        if agent_key not in made:
            made[agent_key] = FakeLLM(agent_key, routes.get(agent_key, []))
        # provider "openai" keeps history_cache_control() at None, so
        # invoke() is called with no extra kwargs.
        return made[agent_key], "openai", "dry-run-model"

    def build_llm(agent_name: str, *a, **k):
        return get_for_agent(agent_name)

    cache.get_for_agent = get_for_agent          # every agent
    provider.build_llm = build_llm               # the Context Pruner


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--topology", type=int, default=5, choices=sorted(ROUTES))
    ap.add_argument("--query", default="Design a 3-blade propeller, 40 mm "
                                       "radius, for quiet operation.")
    args = ap.parse_args(argv)

    import workflow_settings.settings as S
    S.SYSTEM_TOPOLOGY = args.topology

    routes = ROUTES[args.topology]
    install_fakes(routes)

    from agents.shared.session import Session
    from agents.shared.topology import hub_display, hub_key
    from agents.hub import build_hub
    from agents.dispatch import dispatch_turn

    print(f"=== dry run: topology {args.topology} "
          f"(hub = {hub_display()} / {hub_key()}) ===\n")

    tmp = Path(tempfile.mkdtemp(prefix=f"dryrun{args.topology}_"))
    session = Session(session_id=f"dryrun{args.topology}",
                      session_ts=datetime.now(timezone.utc))

    print("-- constructing the agent set (real prompt assembly) ----------")
    hub = build_hub(session)
    built = sorted(hub._agents_by_key)
    print(f"   hub class      : {type(hub).__name__}")
    print(f"   agents built   : {len(built)}  {built}")
    # Every $slot and {brace} is substituted in a healthy assembled
    # prompt -- verified across both topologies, so a survivor here is a
    # real defect (a fragment that never got spliced), not a false alarm.
    slot_re = re.compile(r"\$[a-z_][a-z0-9_]*|\{[a-z_][a-z0-9_]*\}")
    prompt_problems = []
    for key in built:
        agent = hub._agents_by_key[key]
        sp = getattr(agent, "system_prompt", "") or ""
        left = sorted(set(slot_re.findall(sp)))
        flag = f"  !! UNFILLED {left}" if left else ""
        print(f"     {key:<22} prompt {len(sp):>6} chars{flag}")
        if not sp:
            prompt_problems.append(f"{key} assembled an EMPTY system prompt")
        if left:
            prompt_problems.append(f"{key} has unfilled slots {left}")

    print("\n-- driving one turn -------------------------------------------")
    result = dispatch_turn(session, args.query, inputs_dir=tmp / "inputs",
                           attempts_dir=tmp / "attempts", hub=hub)

    print("\n-- agent path actually taken ----------------------------------")
    for i, step in enumerate(TRACE, 1):
        print(f"   {i:>2}. {step}")

    print("\n-- result ------------------------------------------------------")
    print(f"   forwarded      : {result.forwarded}")
    print(f"   reply          : {result.reply_text[:120]!r}")
    print(f"   new artefacts  : {len(result.new_artefacts_paths)}")

    problems = list(prompt_problems)
    if not result.forwarded:
        problems.append("the Receptionist did not forward the query")
    if not (result.reply_text or "").strip():
        problems.append("the turn produced an EMPTY reply")
    low = (result.reply_text or "").lower()
    for bad in ("dispatch error", "unknown agent key", "max dispatch hops",
                "unknown tool", "detected a stuck loop",
                "produced a response with no routing tool call"):
        if bad in low:
            problems.append(f"the reply carries a failure marker: {bad!r}")
    if UNSCRIPTED:
        problems.append(f"unscripted invokes: {UNSCRIPTED}")
    expected_hops = sum(len(v) for v in routes.values())
    if len(TRACE) != expected_hops:
        problems.append(f"expected {expected_hops} invokes, saw {len(TRACE)}")

    print()
    if problems:
        print("FAILURES:")
        for p in problems:
            print("  -", p)
        return 1
    print("PASS - the topology-%d pipeline ran end to end with no real "
          "model call." % args.topology)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
