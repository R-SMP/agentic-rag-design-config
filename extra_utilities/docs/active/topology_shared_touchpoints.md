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

## §A2 — PROMPT_VARIANT: a second, orthogonal dimension

`SYSTEM_TOPOLOGY` is the agent COUNT.  `PROMPT_VARIANT` is which set of
PROMPTS that same agent set runs on.  They are deliberately independent: a
"7-agent reduced" system is the SAME seven agents with the same hub, edges,
step caps and identity rows — only the text differs — so **no agent-count
logic should ever branch on the variant.**  Only `_topology_override` and
`_prompt_path` know it exists.

Resolution is two layers, most specific first, then the shared original:

```
agents/<N>agent_<variant>/…/<name>_<N>agents_<variant>.md
agents/<N>agent/…/<name>_<N>agents.md
<the shared original>
```

**Remark — this is what makes a half-finished variant safe to select.**  An
override that has not been written yet falls through, so the prompt is
byte-identical to the standard one.  Verified: with an empty
`agents/7agent_reduced/`, all nine topology-7 prompts and all seven
topology-5 prompts hash identically to `standard`.  It also means the
proposal's 349 cuts can be applied **one at a time**, each independently
reviewable and revertible by deleting one file.

**⚠ Warning 7 — NEVER DELETE A SHARED FRAGMENT to build a variant.**  The
shrink proposal removes fragments as well as shrinking them, and says so in
its own §3 mechanics note: deleting one means stripping its
`FRAGMENT_TO_SLOT` row and every `$slot` reference *in the same commit*, and
it explicitly warns that `agents/5agent/` overrides six of the files it
touches.  A deletion therefore breaks the 5- and 3-agent topologies, which
read the same files.  In a variant, a "deleted" fragment is simply **no
longer referenced** by that variant's prompts — the file stays for everyone
else.  New fragments are added **additively** to `_build_slots()` and
`FRAGMENT_TO_SLOT` for the same reason.  `_build_slots()` is a superset by
design; the cost is a few unused file reads per session, which is nothing
next to breaking a working topology.

**Remark — the two 7-agent buttons share per-agent LLM models.**  Overrides
live in `agents/<key>/.env` keyed by agent name, and standard and reduced
have identical agent keys, so they share automatically.  That is also the
right experiment: a full-vs-reduced prompt comparison is only clean if the
model is held constant.

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
  **Check EVERY `self.X.Y()`, not just the sub-agents you expect.**  Written
  the narrow way for the Architect it reported "problems: none" while the
  class still called `self.tool_caller`, `self.creator` and
  `self.user_input_inspector` — agents that topology never builds, so every
  one was an `AttributeError` waiting for `reset()`, the step-limit summary
  or the end-of-session history dump.  The check only looked at the four
  attributes it had been *told* about, so the three it had not been told
  about were invisible.  Enumerate `self.<attr>.<method>()` for ALL attrs
  and flag any attr that is not assigned in `__init__`.
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

---

## §G — Selector design + obstacle ledger

*Folded in 2026-08-21 from the former
`extra_utilities/design_topology_selector.md` (removed in the same commit --
the path no longer exists),*
reproduced in full with heading levels shifted down one.  No prose changed.
The two files were the design half and the runbook half of one subject and
were always read together; this is the runbook, so it is the surviving name.*

**Why the merge direction is this way round:** this file is larger (19 KB vs
8 KB), is cited as the operational spine of the reduced-agent work, and its
§F failure log is the most reusable content in the cluster.  The selector doc
is the WHY behind the rows above.

**Status caveat carried across:** the T1-T4 decisions in §G.1 all shipped
(`3dbde09`, `01173b8`, `ae727d9`, `dec7279`).  Several of the O-items in
"Structural obstacles that remain real" have since been resolved and are
annotated inline where known; `O9` (the nine eager `*_TEMPLATE` builds) is
still genuinely open and is now also tracked as **F90** in
`extra_utilities/TODO_known_issues.md` — fix it in one place, close both.

## Topology selector — design

**Status:** DESIGN AGREED 2026-08-01.  Build approach chosen: **additive steps
only, then stop for a real run.**  Nothing risky is applied until the additive
layer is deployed and sanity-checked.

### Decisions (owner)

| # | decision |
|---|---|
| T1 | Topology is chosen from a **drop-down in the workflow-settings UI** — and takes effect on the **NEXT session**, exactly like the other workflow settings. |
| T2 | Topology is ALSO a **per-run condition in the Sessions Queue**, like the existing per-run single-model setting, so **one overnight queue can mix 7 / 5 / 3** rather than needing three deploys. |
| T3 | The mechanism is **generic over N topologies**, not special-cased for two — adding the 3-agent later is a folder plus a drop-down entry, no further code change. |
| T4 | Layout: **separate folder per topology, shared files stay shared**; the 7-agent stays at `agents/<agent>/prompt.md`. |

### ⚠ The wiring map's O1 was OVERSTATED — corrected here

The map concluded *"topology must be an import-time constant … the Sessions
Queue cannot alternate topologies in one process; a restart is required."*
**That is wrong, and the code's own design says so.**

- `_build_slots()` is called INSIDE `_build_template`, **per call**.  Its
  docstring states the reason: *"rebuilt fresh on every call … so live edits to
  .md fragments via the System Prompts UI take effect on the next session's
  agent construction **without a Python restart**."*
- Every agent calls `_build_template(...)` **at construction time**, not import
  time (`planner.py:223`, `orchestrator.py:240`, `receptionist.py:88`,
  `dc_input_creator.py:185`, `dc_output_inspector.py:280`, …).

So **prompt assembly is already per-session by design** — built that way for
live prompt editing.  Topology rides the same path.

What is genuinely import-time is only:
`_USER_FACING_AGENTS` (`prompts.py:92`), `_PIPELINE_FLOW_FRAGMENT_NAME`
(`:403`), `NATURAL_PIPELINE` (`routing.py:31-39`), and the nine eager
`*_TEMPLATE` builds (`:660-668`) — which the map independently confirmed are
**DEAD CODE** (every agent rebuilds its own).  These are *parameters written as
constants*, not an architectural constraint.

**⟹ The work is to thread a topology argument down to `_build_template` /
`_build_slots`, which already run at the right moment.**

### Structural obstacles that remain real

Full detail in the wiring map; the ones that survive the O1 correction:

- **O4 — the quietest failure.**  `if current == "planner":`
  (`orchestrator.py:718`) is the ONLY place `standing_directives.extract_directive`
  runs.  Under another topology the issuer is the Conductor, so
  `session.standing_directives` stays empty, the DCOI refine counter never
  arms, and **the whole precision section-matching loop silently disappears —
  no error, no log line, and a happy-path run looks fine.**
- **O5 — three fragment basenames are IDENTICAL across roots**
  (`routing_receptionist.md` 1588B vs 830B, `routing_tool_caller.md` 411B vs
  669B, `routing_dc_output_inspector.md` 873B vs 889B).  A bare filename no
  longer identifies a fragment; the failure mode is **loading the WRONG
  content**, not `FileNotFoundError`.  Resolution must be
  **override-then-fallback**, never override-only.
  > **CLOSED (2026-08-02).**  Every topology file now carries an
  > `_<N>agents` suffix and sits in a sub-folder mirroring its source root,
  > so no two are alike.  Resolution is override-then-fallback throughout.
  > `smoke_test_topology_fragments.py` asserts all 20 overrides are reached
  > and that no shared original of an overridden fragment is ever read.
- **O2 — `_wire_routing` is a topology expressed as control flow**
  (~30 literal `build_routing_tool` calls, 7 different consumer signatures).
  Each topology's hub needs its own; not a shared table to extend.
- **O3 — "orchestrator" is a string literal in ~10 places** meaning *the hub*,
  including inside `routing_tools.py:238/249`.
- **O6/O7/O8** — `_USER_FACING_AGENTS` must be `{receptionist, <hub>}` per
  topology; `_PIPELINE_FLOW_FRAGMENT_NAME` must be bypassed (the 5-agent
  `pipeline_flow.md` is a single file with no PF markers);
  `PROMPT_MD_RUNTIME_SLOTS` needs two different values for the key
  `"receptionist"` (7-agent has none, 5-agent has two).
  > **O6/O7 CLOSED (2026-08-02).**  `_USER_FACING_AGENTS` →
  > `_NON_CHAIN_AGENTS`, listing both hubs: it is a delete-list KEY, never
  > rendered, and each hub is only built in its own topology, so no
  > per-topology branch is needed (verified — the nine 7-agent prompts are
  > byte-identical by hash before/after).  `_PIPELINE_FLOW_FRAGMENT_NAME` is
  > now `_pipeline_flow_fragment_name()`, which returns the unbranched
  > `pipeline_flow.md` whenever the topology ships one.  The same
  > PF-collapse rule is applied in `routing._load_routing_fragment`, since
  > the UII passes a `*_uii_first.md` name its 5-agent override could never
  > match.  **O8 still open.**
- **O9 — the eager `*_TEMPLATE` block is an active hazard**: once `_build_slots`
  is topology-aware it would splice one topology's fragments into another's
  prompts.  Delete it (it is dead) or guard it.
  > **STILL OPEN (2026-08-02)** — deliberately untouched to keep the
  > resolution step's blast radius small.  Written up in full in the build
  > tracker (condition, five problems, three fix options; recommendation =
  > make them lazy via a module-level `__getattr__`).  Confirmed dead: no
  > production code reads any of the nine, only
  > `smoke_test_prompt_format.py:88`.
- **O12 — MOOT since 2026-08-21.**  This described a gate in
  `prompts_admin._agent_for_prompt_md` that stopped the unescaped-brace
  validator running on nested survivor prompts.  The System Prompts UI and
  `workflow_settings/prompts_admin.py` were **removed entirely** on stage-a
  (same commit that closed TODO `F81`), so there is no validator left to gate.
  Prompts are edited as files again.

  > **The underlying hazard did NOT go away — it lost its only detector.**  A
  > literal `{` or `}` in any `.format()`-spliced fragment still breaks prompt
  > assembly at import.  Nothing checks for it now.  If a prompt-editing UI is
  > ever reinstated, its validator must cover nested variant prompts, and its
  > marker list must cover all nine conditional markers (see the archived
  > `F81`).

### Build order — ADDITIVE FIRST (owner's choice)

**Now (all dead code while the topology stays 7; the 7-agent is provably
untouched):**
1. **Identity tables** — `AGENT_DISPLAY` (+`conductor`,`creator`) and the ~9
   other hard-coded agent lists that derive from or mirror it.
2. **Step caps** — `MAX_CONDUCTOR_STEPS` / `MAX_CONDUCTOR_VISITS` /
   `MAX_CREATOR_STEPS`.  ⚠ do NOT copy the Orchestrator's 6 or the DCIC's 50:
   a merged agent both relays and deliberates.
3. **The selector** — `SYSTEM_TOPOLOGY`, generic over N, defaulting to 7;
   carried on `Session` (per T1/T2) the way `dcoi_comparison_mode` is.
4. **The two agent classes** — `agents/conductor/conductor.py`,
   `agents/creator/creator.py`.  Nothing imports them yet.

**Then STOP for a real run / deploy check.**

**Later (modifies shared code; each written so topology 7 takes the
byte-identical existing path):** topology-aware fragment + prompt resolution;
the hub-string parameterisation; the Conductor's `_wire_routing`; dispatch
entry; the four construction sites; the Receptionist `.format()`; the
admin/UI surface (incl. O12); the queue's per-run topology field.

### Verification reality — VERIFIED, not assumed

- This worktree is **Python 3.8.2**, but `prompts.py` / `routing.py` /
  `routing_tools.py` use PEP-585 annotations WITHOUT
  `from __future__ import annotations`, so they need **≥3.9** regardless of
  dependencies.
- `langchain_core` is not installed, and a direct `importlib` file-load of
  `prompts.py` fails too — **there is no stub-import escape.**
- ⟹ Locally impossible: executing `_build_template`, constructing any agent,
  exercising `_wire_routing` / `dispatch()`, or running any smoke test that
  imports the app.
- The one lever that runs here is
  `extra_utilities/prompt_efficiency/measure_prompts.py` (stdlib-only) — but it
  is a **verbatim replica** of the assembly logic, so it verifies its own copy,
  **not production**.
- **The step-4 non-regression test that actually proves something:** hash all
  nine assembled 7-agent prompts on the target machine BEFORE the shared-code
  commit and compare after.  Nothing static proves it.
