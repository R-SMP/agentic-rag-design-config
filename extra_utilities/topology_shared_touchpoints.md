# Topology registry — every SHARED file a new agent must be added to

**Why this exists.**  The 5-agent topology's *prompts* are separated into
`agents/5agent/`, but its *code* cannot be: a folder whose name starts with a
digit is not a valid Python package, and several tables are single global
registries that every topology must share.  So each new agent adds an entry to
a fixed set of shared files.

**The failure mode is silence.**  The wiring map found that a missed entry does
not usually raise — it degrades.  `AGENT_DISPLAY` is the exception and the
reason it is listed first: miss it and everything else raises immediately,
which is the good case.

**Adding the 3-agent variant (or any new agent) = working this list top to
bottom.**  Verified 2026-08-01 by grep, not from memory.

> **⚠ 2026-08-04 — this file is now a RUNBOOK, not just a registry.**  The
> original 13 rows below were written BEFORE the topology resolver
> (`prompts._topology_override`), the topology module
> (`agents/shared/topology.py`), and the hub factory (`agents/hub.py`)
> existed.  Following the 13 alone would today miss six touch-points and the
> entire file-layout convention.  **Read §A–§F after the table** — they cover
> the layout, the resolution machinery, the build order, verification, and
> every defect the two live 5-agent runs exposed.  Everything below §A was
> learned by BUILDING the 5-agent and then RUNNING it twice; none of it is
> speculative.

---

## The 13 shared touch-points

| # | file | table / symbol | what a MISS causes |
|---|---|---|---|
| 1 | `agents/shared/routing_tools.py` | `AGENT_DISPLAY` | **Everything breaks loudly.** `ROUTING_TOOL_NAMES` and `session.KNOWN_AGENT_KEYS` both derive from it, so `call_<agent>` is not a recognised terminal routing tool and `AgentState(agent_key=...)` raises. **Do this one first.** |
| 2 | `agents/shared/routing_tools.py` | `_TOOL_DESCRIPTIONS` | Silent: a generic fallback description is used, so the LLM gets a weaker tool doc with no error. |
| 3 | `agents/shared/trace.py` | `_AGENT_DISPLAY_NAMES` | Silent: the agent's activity never lights up the LOG/Status flow chart. Duplicated deliberately (not imported) to avoid a circular import. |
| 4 | `agents/shared/base_chain_agent.py` | `_PRUNE_DISPLAY_NAMES` | Silent: `agent_active` events carry no display label. |
| 5 | `agents/shared/prompts.py` | `PROMPT_MD_RUNTIME_SLOTS` | The unescaped-brace / unknown-runtime-slot validator cannot check that agent's prompt. |
| 6 | `agents/step_caps.py` | per-agent caps | No budget for the new agent's run loop. |
| 7 | `agents/orchestrator/orchestrator.py` | `_AGENT_KEY_ALIASES` | `read_agent_history` cannot resolve the agent by name. |
| 8 | `workflow_settings/database_access.py` | `DEFAULT_AGENTS` | No DBa toggle; database tools never bind. Its own comment requires editing #9 in the same commit. |
| 9 | `agents/database_handler/db_writer.py` | `DEFAULT_AGENTS_TO_ACL` | The agent is missing from `chunks.agents_to` defaults. |
| 10 | `workflow_settings/ocr_access.py` | `DEFAULT_AGENTS` | Silent and easy to miss: the agent's `view_images` calls lose their OCR text. **Only for agents that bind image tools** — the wiring map got this wrong for the Conductor, which does bind `view_images` (inherited from the Planner). |
| 11 | `workflow_settings/llm_defaults.py` | `DEFAULT_PER_AGENT_MODELS` | No default model for the agent. |
| 12 | `workflow_settings/llm_routing.py` | `AGENT_SPEC` | Absent from LLM routing. Note the third field, `wired_into_dispatcher` — set it `False` until the agent is actually constructed, as `context_pruner` does. |
| 13 | `workflow_settings/settings.py` + `editor.py` | `SYSTEM_TOPOLOGY` + `ENUM_OPTIONS` | The topology cannot be selected from the UI. |

## Rows 14–19 — touch-points added AFTER the original list (2026-08-04)

These did not exist on 2026-08-01.  All were created while wiring the
5-agent; every one needs a topology-3 entry.

| # | file | table / symbol | what a MISS causes |
|---|---|---|---|
| 14 | `agents/shared/topology.py` | `_HUB_BY_TOPOLOGY` | The topology falls back to the 7-agent hub, so `hub_key()` / `hub_display()` name the **Orchestrator** in a topology that has none. Silent: prompts and traces quietly address a non-existent agent. Holds `(key, display)` — the display MUST equal `AGENT_DISPLAY`'s, and the smoke test asserts it. |
| 15 | `agents/hub.py` | `build_hub` branch | **Nothing constructs the new hub.** `build_hub` returns the Orchestrator, so selecting the topology silently runs the 7-agent set. |
| 16 | `agents/shared/routing.py` | `_PIPELINE_BY_TOPOLOGY` | Every chain agent's `## Routing` section shows the 7-agent flow string, naming agents that do not exist. |
| 17 | `agents/shared/prompts.py` | `_NON_CHAIN_AGENTS` | The new hub KEEPS the `<<CHAIN_ONLY>>` rules and is told to "ESCALATE to the &lt;hub&gt;" — i.e. to itself. Add every hub here; it is a delete-list key, never rendered, so listing all hubs unconditionally is correct. |
| 18 | `workflow_settings/dh_schedule.py` | `AGENT_KEYS` **and** `AGENT_SHORT_LABELS` | **Found the hard way.** `AGENT_KEYS` *validates* schedule entries (`dh_schedule.py:370,382`), so a DH schedule naming the new agent is **rejected outright** — the DH can never interview the agents that do all the work. Missing labels make the UI popover show raw underscored keys. |
| 19 | `extra_utilities/smoke_test_topology_fragments.py` | seven per-topology tables | The suite silently stops covering the new topology. Needs a row in each of `AGENTS_BY_TOPOLOGY`, `ROUTING_FRAGMENTS_BY_TOPOLOGY`, `HUB_BY_TOPOLOGY`, `HUB_MARKERS`, `CHAIN_BY_TOPOLOGY`, `UII_KICKOFF_AGENT` (skip if the topology has no UII), and `NEVER_FORMATTED` if the new agent is never `.format()`ed. |

---

## §A — File layout (DECIDED; applies to every topology)

A topology owns `agents/<N>agent/`, holding **only files that DIFFER** from
the 7-agent originals.  Anything without an override is SHARED — read from
the original path, one copy, cannot drift.  For the 5-agent that was 20
overrides against ~36 shared.

Each override is suffixed `_<N>agents` and filed under a sub-folder
**mirroring its source root**:

```
agents/5agent/prompt_fragments/generic_constraints_5agents.md
     overrides  agents/shared/prompt_fragments/generic_constraints.md
agents/5agent/dc_config/hard_constraints_dc_5agents.md
     overrides  DC_prompt_fragments/dc_config/hard_constraints_dc.md
agents/5agent/tools_config/database_search_creator_5agents.md
     overrides  DC_prompt_fragments/tools_config/database_search_creator.md
agents/5agent/receptionist/prompt_5agents.md
     overrides  agents/receptionist/prompt.md
```

Two rules that make this safe:

* **There is deliberately no `agents/7agent/`.**  Every override lookup
  misses under topology 7, so it takes the byte-identical historic path.
  The 7-agent is safe *by construction*, not by care.
* **An agent existing ONLY in a topology** (Conductor, Creator — and for the
  3-agent, Architect and Designer) keeps a NORMAL Python package,
  `agents/<name>/`, with its prompt as `prompt_<N>agents.md`.  It has no
  7-agent original to shadow.  A folder starting with a digit is not a valid
  package name, which is the whole reason code cannot live under
  `agents/<N>agent/`.

The suffix exists so every file is self-identifying: an editor tab reading
`generic_constraints_5agents.md` names its topology; a bare
`generic_constraints.md` in a sibling folder does not.

## §B — The resolution machinery (already generic over N)

Built for the 5-agent, parameterised by the integer — **the 3-agent needs no
changes here**:

| function | what it does |
|---|---|
| `topology()` | reads `SYSTEM_TOPOLOGY` **fresh per call**, never at import |
| `_topology_override(rel)` | `agents/<N>agent/<rel-with-suffixed-basename>` or `None` |
| `_read_dc_fragment` / `_read_generic_fragment` | override-then-fallback |
| `_prompt_path(agent)` | 3 candidates: topology copy → topology-only agent → historic |
| `_load_routing_fragment` | override, then the branch-suffix-stripped name, then shared |
| `$routing_hub` | one topology-neutral slot filled from `routing_<hub>.md` |

**Why `topology()` is read per call and not captured at import:**
`web_app._build_session` reloads the settings module in place but does NOT
reload its importers, and the Sessions Queue switches topology between runs
inside one process.  A module constant would pin the topology to whatever
was on disk at process start.

**The PF-collapse rule.**  `PLANNER_FIRST` splits some routing fragments into
`*_planner_first.md` / `*_uii_first.md`.  That axis exists ONLY in the
7-agent system, so a reduced topology ships ONE fragment per agent and
`_load_routing_fragment` tries the branch-suffix-stripped name as a second
candidate.  Without it, the 5-agent UII silently loaded the **7-agent**
fragment and was told to call `call_planner` — an agent that does not exist
there.  The same trap applies to `pipeline_flow`, handled in
`_pipeline_flow_fragment_name()`.

## §C — Build ORDER (learned the hard way — do NOT invert)

**Wiring skeleton first, prompts second.**

The 5-agent was built prompts-first, and the prompts were written weeks
before the wiring.  They drifted, silently, and the drift was invisible to
every static check.  It surfaced only on a live run — see §F item 4.

Recommended staging, each stage independently reviewable and committable:

* **Stage A — identity + config skeleton.**  All 19 touch-points above.
  Purely additive; nothing constructs the new agents, so the other
  topologies cannot regress.  Set `llm_routing.AGENT_SPEC`'s third field
  (`wired_into_dispatcher`) to `False` here.
* **Stage B — the agent classes** + the `build_hub` branch.  Flip
  `wired_into_dispatcher` to `True`.  Copy the nearest existing class as a
  template but re-derive every hard-coded agent key.
* **Stage C — prompts + fragment overrides**, written against a skeleton
  that already assembles, so every tool a prompt names can be checked
  against what the class actually binds *as it is written*.

## §D — Verification (what to run, and what it does not cover)

```bash
py extra_utilities/smoke_test_topology_fragments.py
py extra_utilities/smoke_test_prompts_admin.py
py -m pyflakes agents/ web_app.py workflow_settings/
```

* **Use `py` (3.13), not `python`.**  The worktree default is 3.8.2 and
  cannot even import `prompts.py` (PEP-585/604 annotations).
* **`py_compile` is NOT evidence.**  Python resolves names at runtime, so a
  renamed variable that no longer exists compiles happily.  `pyflakes`
  catches it.  This bit twice — see §F.
* **Mutation-test any new check.**  Re-introduce the defect it is supposed
  to catch and confirm it fails.  A check that has never failed has not been
  shown to work; two of the suite's checks were silently vacuous until
  mutation-tested.
* **What none of this covers:** whether the merged prompts make the agents
  *behave* well, and whether the runtime dispatch path works. Only a live
  run tells you that. Both live 5-agent runs found defects the full static
  suite could not see.

## §E — Structural pre-flight for a new agent class

Cheap, and it caught real issues before the first run:

* AST-check that every `self.<subagent>.<method>()` the hub calls exists on
  that class with a compatible signature (11 calls checked for the Conductor).
* Confirm the hub wires **every** sub-agent (`set_tools` / `set_routing_tools`)
  — one missed agent has no routing tools and dead-ends.
* Confirm the hub binds its own tools, and that `_agents_by_key` lists every
  agent plus itself.
* Confirm the hub's `dispatch` loop tolerates `start_agent_key` naming a
  non-hub agent (generic `_agents_by_key.get(current)` lookup + unknown-key
  guard).

## §F — Defects the two live 5-agent runs exposed

Three of the four were invisible to every static check.  Expect the 3-agent
to hit the same *classes* in the same places.

1. **Shared dispatch plumbing carried a 7-agent assumption.**
   `receptionist.validate_input` decided "did it forward?" with
   `self._pending_hop.target == "orchestrator"`.  The 5-agent Receptionist
   routes to the UII, so the test failed, the turn was classified as a
   direct reply, and the reply text was empty (the turn had ended in a tool
   call).  **Symptom: the user got a blank response.**  Fix: any routing-tool
   invocation is a forward; return the target.
2. **`dispatch_turn` discarded the chosen target**, always starting the hub.
   Both hubs already accepted `start_agent_key`; it was simply never passed.
   When the target is not the hub, pass the Receptionist's own hand-off
   through unwrapped — it already IS the hand-off.
3. **The kickoff named a specific agent** ("handing off to the Planner").
   Wrong in the 5-agent, and *already* contradicting the Orchestrator's own
   prompt under the live `PLANNER_FIRST=False`.  Now names no agent.
4. **A prompt promised tools the code never bound.**  The Conductor's prompt
   documents `read_extracted_inputs` and `read_user_queries` — the latter
   with a whole `## Utility tool:` section — but the class bound neither.
   Live cost every design turn: it called `read_attempt` on a file not in an
   attempt folder (`Error: no attempts created yet`), then routed to the
   Tool Caller purely to have the file read back to it, which used
   `read_parameters` on a non-parameters file.  Two wasted hops, ~60k
   tokens, and the only tool error in the run.  **Whenever a merged prompt
   names a tool, check the class binds it.**

### What the runs CONFIRMED works

Worth knowing, so the 3-agent build does not re-litigate it:

* Standing directives must key on the **new hub's** agent key.  Ported
  unchanged from the Orchestrator's `if current == "planner"`, the test never
  fires, `session.standing_directives` stays empty forever, and the entire
  precision section-matching loop vanishes with **no error and no log line**.
  Keying it on `"conductor"` armed the loop correctly.
* The hub's APPROVE hand-off must itself carry the full "Name the attempt
  folder(s)" format — number, absolute path, `Show to user:` — because there
  is no Orchestrator downstream to add it.  It survived the merge.
* Prompt caching works in a reduced topology (savings climbed to 84–86%).
* A merged create+execute agent honoured its phase contract on all four
  cycles: self-validate → `new_attempt` → `write_parameters`.  **Note for the
  3-agent: the Designer has NO validation stage by design, so that first
  phase is deliberately absent — expect more render-time errors and reactive
  recovery, which is the intended character of the strip-down (design doc
  W5).**

## Not in this list, but also needed

- **The agent package itself** — `agents/<name>/<name>.py` + `__init__.py`, a
  peer of `agents/planner/` (owner's decision: keep the repo's one-folder-per-agent
  convention rather than a topology package).
- **The prompt** — `agents/<N>agent/<agent>/prompt.md` for a survivor whose
  prompt varies by topology, or `agents/<name>/prompt.md` for an agent that
  exists in only one topology.
- **The hub's `_wire_routing`** — each topology's hub owns its own edge set;
  there is no shared table to extend (wiring-map obstacle O2).
- **`web/app.js` `LR_BOXES`** — no coordinates means the agent is silently
  omitted from the LLM-routing chart (verified: `LR_AGENT_KEYS` is *derived*
  from `LR_BOXES`, so this omits rather than crashes).

## Known side-effects of a superset registry

`agents/loader.py` iterates `AGENT_DISPLAY.keys()` for the startup LLM banner,
so it lists agents that the active topology never constructs, and the "all N
agents share one default" collapse changes its count.  Accepted knowingly.
