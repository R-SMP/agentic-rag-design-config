# Topology 5 — a briefing for whoever edits its system prompts

You are about to turn the owner's wishes into concrete edits to the **5-agent
system's** prompts.  This is everything you need to know to place those edits
correctly.  Read it once, end to end; it is short on purpose.

---

## 1. What topology 5 IS

**Topology 5 is the 7-agent system with two agents removed and one promoted.**

* The **Orchestrator is gone.**  Its dispatch job moved to the **Planner**,
  which is now the hub: it starts every cycle, every agent returns to it, and
  it is the final approver.
* The **DC Input Inspector is gone.**  Nothing validates the parameter set
  between authoring and generation; the Tool Caller's own range check before
  generating is what compensates.

Everything else is the same agent doing the same job as in the 7-agent system.

| Agent key | Role | In the "5"? |
|---|---|---|
| `planner` | **HUB.** Plans, dispatches, approves. Absorbs the Orchestrator. | yes |
| `user_input_inspector` | Reads the user's raw inputs, writes `extracted_inputs.txt` | yes |
| `dc_input_creator` | Authors the parameter set, opens the attempt folder | yes |
| `tool_caller` | Generates the mesh and renders it | yes |
| `dc_output_inspector` | Looks at the renders and gives the verdict | yes |
| `receptionist` | The only agent that talks to the user | extra |
| `database_handler` | Post-session only, never in the dispatch loop | extra |

Not built here at all: `orchestrator`, `dc_input_inspector`.  The old 5-agent
`conductor` and `creator` were **deleted from the repo** — if you see them
mentioned anywhere, that text is stale.

## 2. The routing graph — the thing most prompt text describes

```
Receptionist ──► Planner ──► Receptionist
                    │
       ┌────────────┼────────────┐
       ▼            ▼            ▼
      UII      Input Creator  Output Inspector
       │            │  ▲            │  ▲
       └──► Planner │  │            │  │
                    ▼  │            │  │
                Tool Caller ────────┘  │
                    │  ▲               │
                    └──┴───────────────┘
```

The 13 edges, exactly:

| From | Can call |
|---|---|
| Receptionist | Planner |
| **Planner (hub)** | UII · Input Creator · Output Inspector · Receptionist |
| UII | Planner |
| Input Creator | Tool Caller · Planner |
| Tool Caller | Output Inspector · Input Creator |
| Output Inspector | Tool Caller · Input Creator · Planner |

**Three consequences that shape the prose:**

1. **The Planner has NO edge to the Tool Caller**, and **the Tool Caller has
   NO edge to the Planner.**  The Tool Caller is the one agent that cannot
   escalate.  Work enters the DC loop through the Input Creator.
2. **FORWARD and ESCALATE are the same tool call** for the UII and the Input
   Creator — the agent they forward to and the hub they escalate to are now
   one agent (`call_planner`).  There is no separate escalation path.
3. **The Output Inspector talks to the Input Creator directly.**  In the
   7-agent system precision feedback went DCOI → Orchestrator → DCIC; with no
   Orchestrator the DCOI addresses the DCIC itself.

## 3. Where the prompts live, and the one rule that matters

### THE RULE

> **Never edit a file outside `agents/5agent/` for a topology-5 change.**
> Every shared file is topology 7's live prompt.

Topology 5 owns a **complete mirror** of the prompt tree — 100 files, currently
byte-identical to their 7-agent originals.  A verification check
(`smoke_test_topology_fragments`, the `MIRROR` case) asserts that topology 5
reads **nothing** from the shared trees; it currently reads 86 files, all of
them from `agents/5agent/`.  So the file you need is already there — find it
and edit it in place.

### Where each file is

| What | Shared original (topology 7 — do not touch) | Topology-5 file to edit |
|---|---|---|
| An agent's prompt | `agents/<agent>/prompt.md` | `agents/5agent/<agent>/prompt_5agents.md` |
| Generic fragment | `agents/shared/prompt_fragments/X.md` | `agents/5agent/prompt_fragments/X_5agents.md` |
| DC config fragment | `DC_prompt_fragments/dc_config/X.md` | `agents/5agent/dc_config/X_5agents.md` |
| Tools config fragment | `DC_prompt_fragments/tools_config/X.md` | `agents/5agent/tools_config/X_5agents.md` |

Sub-folders mirror too (`dc_config/user_input_types/`,
`tools_config/render_check_library/`).  The rule is always: **same relative
path, basename gains `_5agents` before the extension.**

The seven prompt files:

```
agents/5agent/planner/prompt_5agents.md              <- the HUB
agents/5agent/receptionist/prompt_5agents.md
agents/5agent/user_input_inspector/prompt_5agents.md
agents/5agent/dc_input_creator/prompt_5agents.md
agents/5agent/tool_caller/prompt_5agents.md
agents/5agent/dc_output_inspector/prompt_5agents.md
agents/5agent/database_handler/prompt_5agents.md
```

### Two naming rules you will hit

**Per-agent ("scoped") fragments.**  Some fragments have a per-agent variant.
The name is `<stem>_<agent_key>_5agents.md` — the agent key goes BEFORE the
topology suffix.  Example:
`agents/5agent/prompt_fragments/generic_constraints_planner_5agents.md`.
A scoped file whose slot is not registered in `prompts.SCOPED_FRAGMENTS` is
**silently inert** — no error, no log line.  Check that table before inventing
a new scoped name.

**Routing fragments have NO `_uii_first` / `_planner_first` suffix here.**
That axis is 7-agent-only.  Topology 5 ships one file per agent:

```
agents/5agent/prompt_fragments/routing_planner_5agents.md          <- the hub's
agents/5agent/prompt_fragments/routing_user_input_inspector_5agents.md
agents/5agent/prompt_fragments/routing_dc_input_creator_5agents.md
agents/5agent/prompt_fragments/routing_tool_caller_5agents.md
agents/5agent/prompt_fragments/routing_dc_output_inspector_5agents.md
agents/5agent/prompt_fragments/routing_receptionist_5agents.md
```

These files are where each agent's `call_<agent>` tool list and its
FORWARD / CLARIFY semantics live.  Most routing-related edits belong here, not
in the agent's `prompt_5agents.md`.

## 4. What the CODE already handles — do not re-do it in prose

| Handled automatically | So do not… |
|---|---|
| `<<DCII_ONLY>>` blocks are stripped and `<<DCII_OFF>>` blocks unwrapped | …hand-delete DCII text; leave the markers alone |
| `<<PF_ON>>` blocks are stripped, `<<PF_OFF>>` unwrapped | …strip PLANNER_FIRST branches by hand |
| Routing boilerplate is the REDUCED set (fragment + the don't-announce mandate only); the `## Routing` header, decide/loop/permission sections are suppressed | …expect a "natural flow" line or a permission section to appear |
| Tool descriptions have their own topology-5 overlay in `agents/topology5/tool_text.py` | …edit a tool description in `agents/shared/` |
| Step budgets are separate (`MAX_PLANNER5_STEPS` / `MAX_PLANNER5_VISITS`) | …touch `MAX_PLANNER_STEPS` |

**Brace warning.** Every prompt except the Database Handler's is `.format()`ed
at construction, so a literal `{` or `}` anywhere in a prompt or in any
fragment spliced into it crashes startup. Double them: `{{` / `}}`.
The runtime slots each agent is formatted with:

* `planner` — `{routing_instructions}` `{user_inputs_dir}`
  `{input_images_subdir}` `{extraction_output_file}`
* `receptionist` — `{user_inputs_dir}` `{extraction_output_file}`
* `user_input_inspector`, `dc_input_creator` — `{routing_instructions}`
* `tool_caller` — `{routing_instructions}` `{render_check_library_block}`
* `dc_output_inspector` — `{routing_instructions}` `{image_persistence_block}`
  `{comparison_mode_block}`
* `database_handler` — none (never formatted)

## 5. What is still 7-agent text — the actual worklist

The topology-5 tree was forked byte-identical **on purpose**, so it currently
says 7-agent things.  The verification suites already name each of these and
stay green only because they are listed as known-pending.  These are the edits
to make:

1. **`call_orchestrator` appears in 7 prompts.**  Every agent's routing
   fragment still offers it.  It must become `call_planner`, and the semantics
   must fold FORWARD and ESCALATE into that one tool (§2.2).
2. **Routing sections name the wrong hub.**  The Tool Caller's and the Output
   Inspector's say "the Orchestrator" where topology 5 means "the Planner".
3. **Nobody states the UII's two required paths.**  In the 7-agent system the
   `Input directory:` and `Extraction output file:` lines are emitted by the
   **Orchestrator alone**; the Planner carries them only inside a `<<PF_ON>>`
   block, which is stripped here.  Topology 5 has no Orchestrator and the
   Planner kicks off the UII, so those lines appear nowhere — and
   `write_extraction` / `read_user_inputs` both take a **required** `path`
   with no default.  The Planner's prompt needs to emit them unconditionally.
4. **The hub still carries the chain-agent rules.**  `<<CHAIN_ONLY>>` regions
   are kept for the topology-5 Planner (the filter has no topology dimension,
   so excluding it would also change topology 7's Planner).  The fix is a
   scoped copy — `generic_constraints_planner_5agents.md` — with the region
   removed.  It currently tells the hub "never address the user yourself —
   route your content to the Orchestrator".
5. **The hub receives an inter-agent chain-access block its prompt never
   explains.**  The Orchestrator's prompt had a section for it; the Planner's
   does not, but the dispatcher still prepends the block.

Also worth knowing, from the 7-agent Orchestrator's prompt, which no longer
exists here — these responsibilities now live nowhere and may need re-homing
into the Planner's prompt: when to re-run the UII; the extraction-only stop
rule; the `Current attempt <N>:` propagation matrix (including the rule that a
NEW generation carries no attempt number); the precision-refine relay decision;
and the `Attempts this cycle:` / `Show to user:` emission template that the
Receptionist's reporting section consumes.

## 6. Verifying an edit

```bash
py -3.13 extra_utilities/smoke_test_topology_fragments.py
```
```bash
py -3.13 extra_utilities/smoke_test_prompt_tool_audit.py
```

The first checks fragment resolution, cross-topology leakage, unsubstituted
`$slots`, brace safety and the mirror invariant.  The second fails if a prompt
names a tool that nothing in that topology binds — the repo's most expensive
recurring defect.

To see the assembled result of an edit:

```bash
py -3.13 extra_utilities/topology_prompt_snapshot.py save /tmp/after
```

It writes every agent's full prompt per topology plus hashes; `diff` compares
two snapshots. **Take a snapshot before you start**, so you can show exactly
which agents moved and which are byte-identical.

**The non-negotiable check:** topology 7's nine prompts must stay byte-identical.
If a topology-5 edit moves them, the edit went into a shared file.
