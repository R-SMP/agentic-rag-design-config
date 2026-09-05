# Topology 3 — handover for the session that builds it

Written 2026-09-04 at `stage-a-web-deploy` = `280d477`, right after the
topology-5 rebuild shipped.  Every code fact below was verified against that
commit, not recalled from documentation.

---

## 1. The owner's brief — read this first, it governs everything

> The current 3-agent system was built based on an old system.  The 7-agent and
> 5-agent systems have been strongly edited and revised, and many
> functionalities work differently.
>
> At first, I want my 3-agent system to be **almost identical to the current
> 5-agent system**.  This means you can start by making the 3-agent system
> identical to the 5-agent system, and then we can ablate what is not
> necessary, add the correct topology-specific tool calls, and then finally
> edit the prompt fragments, tool descriptions etc.

**This is a fork from topology 5, NOT from topology 7.**  That is the single
most important instruction here.  Topology 5 already carries a large amount of
work that topology 7 does not, and starting from 7 would silently re-import
problems that have already been fixed.

### Differences from the 7-agent system (inherited via topology 5)

* the Orchestrator and the DC Input Inspector (DCII) are removed;
* no more proper "Escalation";
* during PRECISION jobs the DC Output Inspector sends back to the DC Input
  Creator, not to the Orchestrator (there is no Orchestrator).

### Differences from the 5-agent system (the new work)

* **Tool Caller is merged with the DCIC**: whoever creates the attempt folder
  and the `parameters.json` also calls the tool that generates the 3D geometry
  or the blade-section renders.
* **UII is merged with the DCOI**: one agent that can see the input images (if
  present), write the extraction file based on all inputs, and compare inputs
  against output renders and give feedback to the input creator or the Planner.
* The Planner stays approximately as it is now.  **The routing tools change
  significantly.**

### The agent graph (owner's words)

```
Receptionist        → Planner only
Planner             → Receptionist, [DCIC+TC], [UII+DCOI]
[DCIC+TC]           → Planner or [UII+DCOI]
[UII+DCOI]          → Planner or [DCIC+TC]
```

* During refinement rounds where the Planner can be skipped, [UII+DCOI] and
  [DCIC+TC] just route back and forth — like what the DCOI does in the 5-agent
  system when it calls the DCIC with an idea of what to do.
* When new useful user inputs are supplied, the Planner first routes to
  [UII+DCOI], which gives the extraction result back to the Planner, exactly as
  in the 5-agent system.  The Planner then chooses what to do.

### Non-negotiable constraints

* **Any edit to the 3-agent system must have NO effect on the 7-agent or the
  5-agent system.**  Use topology-specific AND agent-specific copies —
  including topology-specific and agent-specific **tool descriptions**, the way
  topologies 5 and 7 already do.
* The owner will supply **specific system-prompt edits and tool-description
  edits for each system** once that point of the process is reached.  Do not
  invent prompt wording ahead of that.
* Build a **TODO list** for the process and keep it current.  The owner's
  words: this is VERY important, so that no info, instruction or detail of the
  implementation is lost.  (`extra_utilities/docs/active/topology5_rebuild_plan.md`
  is the model — decisions, open items, stages, content inventories.)

---

## 2. Naming — NOT decided, and to be settled with the owner FIRST

The two merged agents need names.  **This is an open decision the owner will
make together with you; it is one of the first tasks.**  No candidate is
recorded here on purpose — the owner does not want the next session anchored on
names he has not chosen.

Two constraints on whatever is chosen, both from him:

* **The [UII+DCOI] agent must not be named for vision.**  His words: it "could
  also just read input text and transform it into a list of requirements
  without ever looking at renders".  Seeing images is one input modality, not
  the agent's identity — the agent owns the REQUIREMENTS at both ends: it
  derives them from whatever the user supplied, then judges the output against
  them.
* The names may differ from whatever the abandoned 3-agent attempt used (§3).
  They are not bound by it.

One factual hazard worth weighing when the choice is made: names close to
"DC Input Inspector" (DCII) risk a near-miss in prose and in abbreviations —
DCII and DCOI both still exist in topology 7, and these strings appear in
hundreds of lines of agent-facing routing text, where a near-miss is exactly
what produces a mis-route.

Whatever is chosen must be declared consistently across every registry in §5,
including `AGENT_DISPLAY` in `agents/shared/routing_tools.py` — `architect` and
`designer` are missing from it today, which is part of why topology 3 does not
import.

Until the names exist, this document refers to the two agents as **[DCIC+TC]**
and **[UII+DCOI]**.

---

## 3. ⚠ The existing topology-3 scaffolding is a DIFFERENT design

`SYSTEM_TOPOLOGY = 3` is already registered and `agents/architect/`,
`agents/designer/`, `LR_BOXES_3`/`LR_ARROWS_3` (`web/app.js:2014`, `:2104`) all
exist — from the Conductor era, encoding a different decomposition:

| | existing scaffolding | the design being built |
|---|---|---|
| hub | `architect` = **UII + Planner + Orchestrator** | Planner (+Orchestrator role); **UII is NOT in the hub** |
| pair agent | `designer` = DCIC + Tool Caller | DCIC + Tool Caller — **same merge** |
| third agent | `dc_output_inspector`, standalone | **UII + DCOI merged** |

`agents/designer/designer.py` is the same merge as the new [DCIC+TC] and is
worth reading for intent.  `agents/architect/architect.py` is NOT — it binds
the UII's image tools and owns `write_extraction`, because it swallowed the
UII; those belong in the [UII+DCOI] agent now.

Both are stale: `architect.py` names the deleted Conductor/Creator 26 times,
`designer.py` 8 times.  **Topology 3 does not import at all today** —
`hub_class()` under `SYSTEM_TOPOLOGY=3` dies on a missing
`agents/shared/prompt_fragments/routing_architect.md`, and there is no
`agents/architect/prompt.md`.  Nothing works, so nothing is lost by replacing it.

**The fork should come from `agents/5agent/` (97 files), not from these two
modules.**

---

## 4. How a topology resolves — the mechanism

**(a) The number.** `workflow_settings/settings.py:834` → `SYSTEM_TOPOLOGY`.
`agents/shared/topology.py:46` reads it **fresh on every call**, never captured
at import, because the Sessions Queue switches topology between runs inside one
process.  `hub_key()` / `hub_display()` map it through `_HUB_BY_TOPOLOGY`,
falling back to topology 7 for an unregistered number.

**(b) The hub class.** `agents/hub.py` — `hub_class()` returns the class without
constructing it (no API key needed); `build_hub(session)` constructs it.  This
is the ONLY place mapping a topology to a hub; keep it that way.

**(c) The prompt tree.** `agents/shared/prompts.py:89` `_topology_override(rel)`:

```
agents/<N>agent/<same sub-path>/<basename>_<N>agents.md   ← if it exists
otherwise the shared original
```

The sub-path is preserved; only the **basename** gains the suffix.  So:

```
agents/planner/prompt.md              → agents/3agent/planner/prompt_3agents.md
agents/shared/prompt_fragments/x.md   → agents/3agent/prompt_fragments/x_3agents.md
DC_prompt_fragments/dc_config/y.md    → agents/3agent/dc_config/y_3agents.md
DC_prompt_fragments/tools_config/z.md → agents/3agent/tools_config/z_3agents.md
```

A topology with no folder falls through to the shared file — which is why
topology 7 has no folder and behaves exactly as it always did, and why a
half-finished topology is safe to select.  Topology 5 is a **complete mirror**:
its smoke test asserts ZERO reads from the shared trees.  Topology 3 should aim
for the same invariant.

**(d) Agent-SCOPED copies compose with the topology layer.**
`scoped_fragment_path(slot, agent)` (`prompts.py:830`) resolves
`<slot>_<agent>_<N>agents.md`.  **A `$slot` does NOT necessarily resolve to the
fragment file of the same name** — the agent-scoped copy wins and can differ in
substance.  Never read a base fragment and assume that is what the agent
receives; assemble the prompt instead (§6).

**(e) Conditional markers**, resolved at assembly: `<<DCII_ONLY>>` /
`<<DCII_OFF>>`, `<<PF_ON>>` / `<<PF_OFF>>`, `<<CHAIN_ONLY>>`, `<<HAS_DBA>>`,
`<<BSV_ON>>`, `<<DCOI_RANGES_ON>>`.

`prompts._dcii_effective()` and `_planner_first_effective()` are keyed on
**`_hub_agent() == "orchestrator"`**, NOT on `topology() == 7` — deliberately,
because keying on the number broke the unregistered-topology fallback.  Any
topology whose hub is not the Orchestrator gets DCII and PLANNER_FIRST off for
free.

**(f) Code overlays.** Topology-specific runtime STRINGS (tool descriptions
etc.) live in `agents/topology5/tool_text.py` and are fetched via
`topology.overlay_value(name, shared)`, which returns the shared value when the
active topology has no overlay module.  Topology 3 will want
`agents/topology3/tool_text.py` on the same pattern — this is the mechanism the
owner means by "topology-specific tool descriptions".

---

## 5. Registry checklist — every place a topology must be declared

Missing one usually fails **silently**.

| file | what |
|---|---|
| `agents/shared/topology.py` | `_HUB_BY_TOPOLOGY[3]` (currently `("architect", "Architect")`) |
| `agents/hub.py` | `hub_class()` branch |
| `agents/shared/routing_tools.py` | `AGENT_DISPLAY` — needs a row per new agent key |
| `workflow_settings/llm_routing.py` | `AGENT_SPEC` (has `architect`, `designer` rows) |
| `workflow_settings/dh_schedule.py` | `AGENT_KEYS`, `AGENT_SHORT_LABELS`, and `_SCHEDULE_BY_TOPOLOGY` if topology 3 needs its own schedule file |
| `workflow_settings/dh_schedule_3agents.default.json` | only if the row set changes — **land the DATA file before the resolver**, or `_seed_default` falls through to the 29-row topology-blind hardcoded `SCHEDULE` and writes it to disk permanently |
| `agents/shared/sessions_queue.py` | `AGENTS_BY_TOPOLOGY[3]` (names architect/designer today) |
| `agents/shared/routing.py` | `_PIPELINE_BY_TOPOLOGY`, `_sections_for` |
| `agents/shared/session.py` | `RETIRED_AGENT_KEYS` if a key is dropped |
| `agents/step_caps.py` | per-agent `MAX_*_STEPS` for the new agents |
| `workflow_settings/editor.py` | `ENUM_OPTIONS["SYSTEM_TOPOLOGY"]` already `[7,5,3]`; `_INERT_UNDER_TOPOLOGY` already covers `DC_INSPECTOR_ENABLED`, `PLANNER_FIRST`, `CHAIN_ACCESS` for `{5,3}` |
| `web/app.js` | `LR_BOXES_3` / `LR_ARROWS_3` — **exist, keyed to the old roster; rework, do not add** |
| `extra_utilities/dry_run_topology.py` | add a `ROUTES[3]` entry |
| `extra_utilities/prompt_pdf/*` | already take `--topology N` |

**Do NOT add a third `AGENTS_BY_TOPOLOGY`.**  Two exist with different shapes
(`sessions_queue.py`: `dict[int, list[tuple]]`, keys 7/5/3;
`smoke_test_topology_fragments.py`: `dict[int, list[str]]`, keys 7/5) and both
are supersets listing `context_pruner`/`database_handler`, which no hub
registers.  The authoritative source is the hub class's own `_agents_by_key`
literal, read by `extra_utilities/hub_registry.py`.

---

## 6. Verification — the standard the 5-agent rebuild worked to

```bash
# assemble every agent's REAL prompt per topology, and diff two snapshots
py -3.13 extra_utilities/topology_prompt_snapshot.py save <dir>
py -3.13 extra_utilities/topology_prompt_snapshot.py diff <dirA> <dirB>

# drive ONE COMPLETE TURN with a scripted fake LLM — no network, no tokens
py -3.13 extra_utilities/dry_run_topology.py --topology 5

py -3.13 extra_utilities/smoke_test_topology_fragments.py   # mirror invariant
py -3.13 extra_utilities/smoke_test_prompt_tool_audit.py    # prompts vs bound tools
py -3.13 extra_utilities/smoke_test_dh_batching.py          # + F19d hub-registry guard
py -3.13 extra_utilities/smoke_test_hub_attributes.py
py -3.13 extra_utilities/smoke_test_prompts_hot_reload.py
```

**The rule: after every change, prove topologies 7 AND 5 are byte-identical
with the snapshot diff.  Never assert "unchanged" without it.**  That is what
made the 5-agent rebuild safe, and the owner's isolation constraint (§1) makes
it mandatory here.

Environment: `py -3.13`.  `trimesh`, `langchain_openai`, `langchain_anthropic`
are NOT installed — use `extra_utilities/prompt_pdf/bootstrap.py` to import the
agent tree, and `OPENAI_API_KEY=sk-dummy` to construct agents (a key must be
present; no network call is made).  Use `PYTHONIOENCODING=utf-8` when piping
tool output or a `→` in a diff kills the run on cp1252.

---

## 7. Traps that cost real time in the 5-agent rebuild

1. **A stale `.pyc` can serve the wrong `SYSTEM_TOPOLOGY`.**  Python invalidates
   bytecode on (mtime, size) and flipping `7`→`5`→`3` is **size-preserving**.
   Symptom: the file plainly reads `3`, `git diff` is clean, the import yields
   something else.  Fix:
   `find . -name __pycache__ -type d -not -path './.git/*' -exec rm -rf {} +`.
   Suspect it whenever a red test contradicts a green one from earlier.
2. **`build_hub(session, llm_cache=…)` reaches the HUB ONLY** — Planner5 does
   not forward the cache to its sub-agents.  Patch
   `agents.shared.llm_client_cache.get_for_agent`.  The Context Pruner bypasses
   the cache (`llm_provider.build_llm`) and fails open, so an unpatched pruner
   silently builds a real client.
3. **A `$slot` resolves to the agent-SCOPED copy**, which can differ in
   substance.  Assemble the prompt; never read the base fragment and assume.
   (This one produced wrong advice to the owner during the 5-agent work.)
4. **Empty a fragment, do not delete it.**  A missing scoped override falls back
   to the longer shared file — the opposite of removing text.  A zero-byte file
   still overrides.
5. **All prompt files are CRLF**, `core.autocrlf=true`.  Building a string as
   `"a" + nl + "b"` then `.replace("\n", nl)` yields `\r\r\n`, which makes git
   stop normalising and explodes the diff to the whole file.  Convert once, at
   the boundary.
6. **A prose-only turn from a chain agent does not end it** — it fires the
   one-shot routing retry and the agent is invoked AGAIN.  Only the Receptionist
   treats prose as the answer.
7. **A schedule row naming an agent the hub does not build is not a warning** —
   the DH writes `ERROR:` rows into the R2 mirror and the Postgres `chunks`
   table, where they come back at retrieval time.
8. **The DC-parameter primer injects at INVOKE time** and bypasses every
   prompt-level filter (`agents/shared/dc_primer.py`, gated by
   `DC_PARAMS_PRIMER_ENABLED`).  It resolves through `_topology_override`, so
   the 3-agent tree needs its own primer files or it silently serves the shared
   ones.

---

## 8. Topology 5 as it stands — what is being forked

| | topology 7 | topology 5 |
|---|---|---|
| hub | Orchestrator | `Planner5` (`agents/planner5/`), `AGENT_KEY = "planner"` |
| agents built | 8 + DH | 6 + DH |
| prompt tree | shared | `agents/5agent/` — complete mirror, 97 files, zero shared reads |
| DCII | present | absent |
| chain-access feed | hub is fed the inter-agent log | **removed** (`83ae01a`) — that was the Orchestrator's power and left with it |
| DH schedule | `dh_schedule.json`, 36 rows | `dh_schedule_5agents.json`, 33 rows |
| code overlays | — | `agents/topology5/tool_text.py` |

**Topology-5 edge set** (read off the built hub, not from docs):

```
Receptionist → Planner
Planner      → UII, DCIC, DCOI, Receptionist
UII          → Planner
DCIC         → Tool Caller, Planner
Tool Caller  → DCOI, DCIC          (no edge to the hub — cannot escalate)
DCOI         → Tool Caller, DCIC, Planner
```

**Conventions to carry into topology 3:** "ESCALATE" is banned in favour of
"hand back" / "communicate the problem to the Planner"; the hub is the SOLE
issuer of the STANDING DIRECTIVE and issues one on every run, written for THIS
request rather than generically; and the hub must emit the
`Attempts this cycle:` / `Show to user:` block on APPROVE or the Receptionist
reports no parameter values or paths at all (it treats the disk as stale).

---

## 9. Working agreements (the owner's, standing)

* **Propose then apply, ONE edit at a time.**  Show BEFORE and AFTER, the
  reasoning and the risks.  Apply only on an explicit approval; on feedback,
  re-propose rather than applying a guess.
* **Never commit or push unless told.**  Check for conflicts first
  (`git fetch`, then `git log HEAD..origin/stage-a-web-deploy`).  Push target is
  `stage-a-web-deploy`.
* **No AI attribution in any commit or PR** — no `Co-Authored-By`, no
  "Generated with", nothing.
* Every PowerShell/bash block touching the repo starts with
  `cd "<worktree path>"`.
* Prefer guidelines over closed rule-sets in prompts; keep agent judgement and
  free-form inter-agent messages.
* Verify against the code before asserting — docs go stale.
* Faithful-merge rule: when merging two agents, lose NO instruction or detail
  except conflicts agreed with the owner; prefer verbatim wording.

---

## 10. Orientation reading, in order

1. `extra_utilities/docs/active/topology5_rebuild_plan.md` — the model for this
   work: decisions, open items, stages, content inventories.
2. `extra_utilities/docs/active/topology5_for_prompt_editors.md` — how to edit a
   topology's prompts safely.
3. `agents/planner5/planner5.py` — the hub to copy, especially `_wire_routing`
   and `dispatch`.
4. `agents/5agent/` — the tree being forked.
5. `agents/designer/designer.py` — the old DCIC+TC merge, for intent only.
6. `README.md` §Topologies; `extra_utilities/TODO_known_issues.md` (F57 and F61
   are topology-gated traps).
7. The assembled 5-agent prompts, exactly as the model receives them:
   `C:/Users/vince/OneDrive/Desktop/MT/Meetings/08.28/5-agent system/v2/system_prompts5_v2.pdf`
   (7-agent equivalent: `.../08.28/7agent_reduced_system_prompts_v2.pdf`).
   Regenerate with `dump.py` → `provenance.py` → `build_html.py --topology N`,
   then headless Chrome; see `extra_utilities/prompt_pdf/README.md`, and check
   the shrink-to-fit trap it documents.
