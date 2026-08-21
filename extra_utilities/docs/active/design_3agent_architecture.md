# The 3-agent system — architecture, decisions and build plan

**Status 2026-08-04:** Stage A (registration) and Stage B (agent classes)
are BUILT and committed.  Stage C (prompts) is NOT started, so the system
cannot run yet: selecting `SYSTEM_TOPOLOGY = 3` today raises, because
`$routing_hub` resolves to `routing_architect.md` and that file does not
exist.  **That failure is deliberate** — see Warning 1.

**Read alongside:**
`design_agent_count_variants.md` (why the variants exist at all),
`topology_shared_touchpoints.md` (HOW to add a topology — the runbook and
its §F failure log), `agent_count_variants_build_tracker.md` (the running
work log).

---

## 1. Roster

`Receptionist · Architect · Designer · Critic`

| Agent | key | merges | role |
|---|---|---|---|
| Receptionist | `receptionist` | — | user-facing wording |
| **Architect** | `architect` | UII + Planner + Orchestrator | perceive · plan · route · approve |
| **Designer** | `designer` | DC Input Creator + Tool Caller | create · execute — **no validation** |
| **Critic** | `dc_output_inspector` | — (the DCOI unchanged) | critique · drive refinement |

The Critic **keeps the `dc_output_inspector` key**.  It follows the 5-agent
precedent exactly: merged agents get new names (Conductor, Creator,
Architect, Designer), unmerged survivors keep theirs (UII, Tool Caller,
DCOI).  A rename would have cost seven identity-table rows, a new
`call_critic` routing tool, and cross-topology log comparability — for a
label.  "Critic" survives as descriptive prose only.

## 2. Role assignment across all three topologies

| # | Role | 7-agent | 5-agent | 3-agent |
|---|---|---|---|---|
| 1 | interface | Receptionist | Receptionist | Receptionist |
| 2 | perceive | UII | UII | ┐ **Architect** |
| 3 | plan | Planner | ┐ Conductor | │ |
| 4 | route | Orchestrator | │ | │ |
| 5 | approve | Planner / Orch | ┘ | ┘ |
| 6 | create | DCIC | ┐ Creator | ┐ **Designer** |
| 7 | **validate** | DCII | ┘ *(self-check)* | **✕ DROPPED** │ |
| 8 | execute | Tool Caller | Tool Caller | ┘ |
| 9 | critique | DCOI | DCOI | DCOI |
| 10 | drive-refine | Orchestrator | Conductor | **Critic** *(see §4)* |

Row 7 is the whole point: the validation gradient runs
**independent (7) → self-check (5) → none (3)**, and it is the cleanest
single result the benchmark is built to produce.

## 3. The edge set

```
Receptionist  ->  architect
Architect     ->  receptionist, designer, dc_output_inspector
Designer      ->  dc_output_inspector (forward), architect (clarify/escalate)
Critic        ->  designer (refine), architect (escalate/checkpoint/phase-done)
```

`natural_pipeline()` for topology 3:
`Architect → Designer → DC Output Inspector → Architect`

**Remark.** The string excludes the Receptionist, unlike the 5-agent's.
That is not an inconsistency: in the 5-agent the Receptionist routes into
the *chain* (to the UII), so it belongs; here — as in the 7-agent — it
hands to the *hub*, so the string starts and ends at the hub.

## 4. The refine loop — the defining decision

**The Critic refines DIRECTLY with the Designer.  The Architect is not in
the loop.**  It is called for exactly three things:

1. an **escalation** the pair cannot resolve;
2. a **phase change** — the Critic judges the current goal met, so the
   Architect can advance the job ("the sections match; now build the full
   3D geometry");
3. a periodic **checkpoint**, so several rounds can be reviewed together.

### 4.1 This overrides BOTH readings in the design doc

`design_agent_count_variants.md` contradicts itself here, and neither
branch is what was built:

| source | says | status |
|---|---|---|
| §7.4 mermaid | `Cri -->|refine| Des` — always direct | superseded |
| W3 | *"the relay becomes Critic → Interpreter-Conductor → Designer"* — always through the brain | superseded |
| **this document** | direct by default, brain at escalation / phase change / checkpoint | **authoritative** |

Owner's decision, 2026-08-04, after both were put to him: *"I DO want the
system to do a back-and-forth between refining and re-checking without the
architect always in the way."*  The Architect does **phase-level**
orchestration, not per-round micromanagement.

**Remark.** This matches how real work actually divided in live 5-agent run
ID237: a sections phase (3 rounds) and a 3D phase (2 rounds) with a clear
decision point between them.  The 5-agent put its hub in every round; the
3-agent puts it at the boundaries.

### 4.2 The checkpoint — prompt guidance PLUS a hard backstop

Both, by decision — judgement in the normal case, determinism as a floor.

* **Prompt half (Stage C):** the Critic is told when a checkpoint is
  worthwhile.
* **Code half (built):** `Architect.dispatch` counts consecutive
  `Designer ↔ Critic` rounds and, at
  `MAX_ROUNDS_BEFORE_ARCHITECT_CHECKPOINT` (settings §28, default **3**),
  rewrites the next hop to the Architect and prefixes the message with a
  `[CHECKPOINT — forced by the dispatcher …]` preamble so it knows why it
  was called.  The counter resets on any hop that reaches the Architect.

**⚠ Warning 1 — do not conflate this with `MAX_SECTIONS_REFINE_ROUNDS`.**
They do different jobs and must stay separate:

| | governs | if you change it |
|---|---|---|
| `MAX_ROUNDS_BEFORE_ARCHITECT_CHECKPOINT` | **reporting cadence** — how often the brain sees the work | 3-agent only; does not change when the system stops |
| `MAX_SECTIONS_REFINE_ROUNDS` | **stopping ceiling** — how many refine rounds a phase may consume | ALL topologies; changes what the system does, so runs at different values are **not comparable** |

### 4.3 Standing directives must survive a loop the hub is not in

Because the Architect is outside the refine loop it cannot re-stamp a
directive each round, as the Conductor does.  It stamps once at phase
start and `_DIRECTIVE_CARRIERS = {designer, dc_output_inspector}` makes both
agents copy the block **verbatim** through every round.

**⚠ Warning 2.** If either agent's Stage C prompt loses the
"copy STANDING DIRECTIVES verbatim" rule, precision instructions are lost
mid-phase with **no error and no log line** — the same silent-failure class
that would have killed the 5-agent precision loop had directives been keyed
on `"planner"` instead of `"conductor"`.

## 5. Settled decisions, with rationale

| # | decision | why |
|---|---|---|
| D1 | Brain is named **Architect** | tracker's Settled decisions; the design doc's "Interpreter-Conductor" is descriptive prose only |
| D2 | Critic keeps `dc_output_inspector` | 5-agent survivor precedent; preserves cross-topology log comparability |
| D3 | Build order **wiring → prompts** | inverts the 5-agent, where prompts written weeks before wiring drifted and produced the `read_extracted_inputs` bug |
| D4 | Architect **writes `extracted_inputs.txt`** | perceive is preserved (validate is what's dropped); the Designer reads it and the Critic compares against it in `DCOI_COMPARISON_MODE 3` |
| D5 | Designer binds **NO image tools** | the Creator got them from its DCII half — i.e. from validation.  Drop validation, drop the justification.  Keeps vision in the Architect + Critic, per design-doc R6 |
| D6 | Architect gets the **strongest** parent model | deliberate control for design-doc **W1**, the cognitive-load confound |
| D7 | Both new classes **standalone**, not subclasses | Conductor and Creator are live-verified; a shared base would risk them on every 3-agent change |
| D8 | Designer is **sole owner of `new_attempt`** | mirrors the Creator in the 5-agent |
| D9 | Refine loop per §4 | owner, 2026-08-04 |

## 6. Build stages

### Stage A — registration ✅ `fd5bef9`

All 19 shared touch-points from `topology_shared_touchpoints.md`, plus
`MAX_ARCHITECT_STEPS` (60), `MAX_ARCHITECT_VISITS` (150),
`MAX_DESIGNER_STEPS` (85).  Purely additive; `llm_routing` marked both
agents `wired_into_dispatcher=False`.

**Remark.** Working the runbook top to bottom caught four touch-points
absent from the plan written from memory — `_PRUNE_DISPLAY_NAMES`,
`_AGENT_KEY_ALIASES`, `_NON_CHAIN_AGENTS`, `db_writer.DEFAULT_AGENTS_TO_ACL`
— **all four fail silently**.

### Stage B — agent classes ✅ `3db84ae` (Designer) + this commit (Architect)

`agents/designer/` and `agents/architect/`, the `build_hub` topology-3
branch, `wired` flipped to `True`, and
`MAX_ROUNDS_BEFORE_ARCHITECT_CHECKPOINT`.

**⚠ Warning 3 — what a copied hub silently keeps.**  Porting the Conductor
left the Architect calling `self.tool_caller`, `self.creator` and
`self.user_input_inspector` — agents this topology never builds — in
`reset()`, the step-limit summary and the history dump.  Every one was an
`AttributeError` waiting.  `pyflakes` passed (it checks names, not method
existence) and the §E AST pre-flight **also passed**, because it only
examined the sub-agents it had been told about.  Widened; see §E.
Also stale: `_AGENT_KEY_ALIASES` (7-agent names), the `dispatch` default
`start_agent_key`, and `HumanMessage(name=...)`.

### Stage C — prompts ⬜ NOT STARTED

Four files needed:

| file | built from |
|---|---|
| `agents/architect/prompt_3agents.md` | Conductor + UII prompts merged |
| `agents/designer/prompt_3agents.md` | DCIC + Tool Caller merged, validation removed |
| `agents/3agent/dc_output_inspector/prompt_3agents.md` | DCOI, re-pointed + refine/checkpoint rules |
| `agents/3agent/receptionist/prompt_3agents.md` | Receptionist, single forward door |

Plus fragment overrides under `agents/3agent/{prompt_fragments,dc_config,tools_config}/`
— at minimum `routing_architect_3agents.md`, `routing_designer_3agents.md`,
`routing_dc_output_inspector_3agents.md`, `routing_receptionist_3agents.md`,
`generic_constraints_3agents.md`, `pipeline_flow_3agents.md`,
`available_agents_3agents.md`, and `role4_feedback_instructions_3agents.md`
in `agents/architect/`.

**The merge doctrine (owner, binding):**
1. Lose **no** information, instruction or detail.
2. Break nothing in the 7- or 5-agent systems.
3. A **union, not a concatenation** — never state the same concept twice.
4. Different roles → the merged agent has **both**.
5. **Conflicting** roles must be resolved, not carried: any "you ONLY do
   X", or "do NOT do X because agent Y handles it", where Y no longer
   exists or is now the same agent, must be removed or retailored.

**⚠ Warning 4 — a prompt can promise a tool the code never binds.**  The
Conductor's prompt documented `read_extracted_inputs` and
`read_user_queries`, including a full `## Utility tool:` section, while the
class bound neither.  Live cost: a failed `read_attempt`, then a hop to the
Tool Caller purely to have a file read back, every design turn.  Nothing in
the test suite can see this.  **As each Stage C prompt is written, check
every tool it names against what the class actually binds.**

**⚠ Warning 5 — the Designer's write tool.**  `write_parameters`' docstring
is **shown to the model**.  The Creator's version says *"Call this ONLY
after your self-validation has passed"*; that sentence was removed for the
Designer.  Do not let it back in via the prompt — it would instruct the
Designer to perform the stage this topology exists to remove, silently
collapsing the validation gradient.

## 7. Projections for Stage C

Merge ratios measured from the real 5-agent: Conductor = **76 %** of
Planner + Orchestrator; Creator = **75 %** of DCIC + DCII.

| agent | assembled prompt | ≈ tokens | tools |
|---|---|---|---|
| Receptionist | ~38,500 *(measured)* | ~9,600 | ~11 |
| **Architect** | **~85,000** *(projected)* | **~21,400** | ~18 |
| Designer | ~50,000 *(projected)* | ~12,500 | ~15 |
| Critic | ~44,100 *(measured)* | ~11,000 | ~11 |

**⚠ Warning 6 — the Architect's prompt is projected at roughly DOUBLE the
largest 7-agent prompt** (Planner, 12,004 tok) and 24 % above the Conductor,
the biggest thing currently in production.  It also carries ~18 tools and
perceives, plans, routes and approves in one turn.  This is design-doc
**W1** arriving concretely: if the 3-agent scores badly, you cannot
attribute it to "fewer agents" versus "one overloaded agent" without the
model control in D6.  Treat any Stage C opportunity to *shorten* the
Architect as a first-class goal, not a nicety.

## 8. Expected behaviour — not defects

* **More render-time errors and more reactive recovery than the 5-agent.**
  There is no validation gate; the generator's range guards and the
  critique loop are the entire safety net.  Design-doc **W5**.  Do not
  "fix" this — it is the variant's character and the gradient's third
  point.
* **Vision concentrated in two agents** (Architect, Critic).  Design-doc
  **R6**.
