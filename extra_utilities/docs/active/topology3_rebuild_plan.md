# Topology-3 rebuild — build plan and TODO

**Started 2026-09-05.  Branch `claude/rebuild-3-agent-topology-6ca792`, worktree
`rebuild-3-agent-topology-6ca792`, branched from `stage-a-web-deploy` at
`f24f038`.  Nothing is pushed anywhere.  The eventual push target is
`stage-a-web-deploy`, on the owner's word and not before.**

**What this replaces.**  The dormant 3-agent scaffolding (Receptionist,
Architect, Designer, DC Output Inspector) was registered in 2026-08 against the
Conductor-era system.  It encodes a DIFFERENT decomposition, it has never run,
and selecting `SYSTEM_TOPOLOGY = 3` today raises before any agent is built.  It
is being replaced, not repaired.

**The one rule above all others:** *no edit made for topology 3 may change
topology 7 or topology 5.*  Every claim of "unchanged" in this document must be
backed by an assembled-and-hashed before/after, never by reasoning.

Companion reading, in order:
`extra_utilities/docs/active/topology3_handover.md` (the brief this plan
implements), `extra_utilities/docs/active/topology5_rebuild_plan.md` (the model
for this work), `extra_utilities/docs/active/topology_shared_touchpoints.md`
(§A–§F — the runbook and its failure log),
`extra_utilities/docs/active/topology5_for_prompt_editors.md`.

---

## 1. Target definition

### 1.1 Agent set

Topology 3 is a fork of **topology 5**, with two merges:

* the DC Input Creator and the Tool Caller become the **Design Engineer**;
* the User Input Inspector and the DC Output Inspector become the
  **Requirements Analyst**.

| Agent key | Display | Role in topology 3 |
|---|---|---|
| `planner` | Planner | **HUB** — plans, dispatches, approves.  Same role it has in topology 5. |
| `design_engineer` | Design Engineer | **NEW (merge)** — authors the full parameter set, opens the attempt folder, AND runs the generation / render tools itself. |
| `requirements_analyst` | Requirements Analyst | **NEW (merge)** — derives the requirements from whatever the user supplied, writes `extracted_inputs.txt`, and judges the output renders against those requirements. |
| `receptionist` | Receptionist | **EXTRA** — always present, not one of the "3" |
| `database_handler` | Database Handler | **EXTRA** — post-session only, never in `_agents_by_key` |

Retired entirely: `architect` and `designer` (deleted from the repo — see D5);
`orchestrator`, `dc_input_inspector`, `user_input_inspector`,
`dc_input_creator`, `tool_caller` and `dc_output_inspector` are simply not
built under topology 3 (they remain live in topologies 7 and/or 5 and are not
touched).

**On the name of the Requirements Analyst.**  It is deliberately NOT named for
vision.  Seeing images is one input modality, not the agent's identity: it
could equally read plain text and turn it into a list of requirements without
ever looking at a render.  What it owns is the REQUIREMENTS, at both ends — it
derives them, then it judges against them.

**On the pairing.**  *Requirements Analyst* and *Design Engineer* share no
token.  This was chosen over `Design Analyst` (shares "Design") and
`Requirements Engineer` (shares "Engineer") because the two agents are named
side by side in hundreds of lines of agent-facing routing text, where a shared
token is what produces "the Engineer" / "the Design one" ambiguity and, from
there, a mis-route.  Neither abbreviation (RA, DEng) collides with the existing
DCIC / DCII / DCOI / TC / UII family.

### 1.2 Edge list — CONFIRMED BY OWNER 2026-09-05

| FROM | TO | Notes |
|---|---|---|
| Receptionist | Planner | the only door in |
| Planner | Receptionist | the only door out |
| Planner | Requirements Analyst | new user inputs → extraction, returned to the Planner |
| Planner | Design Engineer | starts the design cycle |
| Design Engineer | Requirements Analyst | FORWARD — generated, now judge it |
| Design Engineer | Planner | CLARIFY and ESCALATE collapse into ONE tool |
| Requirements Analyst | Design Engineer | the refine loop, Planner not involved |
| Requirements Analyst | Planner | return / approve / escalate |

Eight edges, four agents.  **The Planner is not in the refine loop**: during
refinement rounds the Design Engineer and the Requirements Analyst route back
and forth directly, exactly as the topology-5 DCOI does when it calls the DCIC
with an idea of what to do.

**Collapse consequence.**  For both merged agents, "forward to the Planner" and
"escalate to the Planner" are the *same tool call*.  Every routing fragment
must say so explicitly.

**A capability the merge GRANTS.**  In topology 5 the Tool Caller is the one
agent with no edge to the hub — it cannot escalate.  Merged into the Design
Engineer, which does have that edge, the execute half gains escalation it did
not previously have.  This is a consequence of the owner's edge list, accepted
knowingly, and it is the one behaviour the merge adds rather than removes.

### 1.3 `natural_pipeline()` for topology 3

```
Receptionist → Planner → Requirements Analyst → Planner → Design Engineer →
Requirements Analyst → Planner → Receptionist
```

**This diverges in SHAPE from both other topologies**, whose strings omit the
Receptionist entirely (7: `Orchestrator → … → Orchestrator`; 5:
`Planner → … → Planner`).  Deliberate, on the owner's instruction: with only
three working agents the Receptionist genuinely is the sole door in and the
composer out, and hiding it understates the flow.  Recorded here so it is never
later "corrected" as an inconsistency.

### 1.4 What is NOT changing

* **No dispatcher-forced checkpoint.**  The abandoned design had the dispatcher
  rewrite the next hop to the hub every N consecutive refine rounds.  Dropped:
  topology 5 has no such mechanism, and a mechanism that exists in only one
  topology is a confound in any 3-vs-5 comparison.  The real backstops stay —
  `MAX_SECTIONS_REFINE_ROUNDS` (clears the standing directive and forces an
  honest finalize) and `MAX_DISPATCH_HOPS`.
* **Escalation semantics.**  As in topology 5: "ESCALATE" is banned in the
  prompts in favour of "hand back" / "communicate the problem to the Planner",
  but the EDGES stay — `routing_tools.stuck_escalation` and every error
  fall-through target the hub.

---

## 2. Decisions LOCKED by the owner (2026-09-05)

| # | Decision |
|---|---|
| **D1** | **Fork from topology 5, never from topology 7.**  Verified necessary rather than assumed: the two have already diverged.  The 5-agent Planner template is 23 765 chars against the 7-agent's 20 786, and the DCIC 22 466 against 23 208.  Forking from the shared tree would silently re-import problems topology 5 has already fixed. |
| **D2** | The hub is a **new class `Planner3`** in `agents/planner3/`, keeping `AGENT_KEY = "planner"`.  `_HUB_BY_TOPOLOGY[3]` becomes `("planner", "Planner")`.  Because the key is unchanged, the hub needs **no new row in any identity registry** — the exact move `Planner5` made.  It also gets DCII-off and `PLANNER_FIRST`-off for free: `prompts._dcii_effective()` and `_planner_first_effective()` key on `_hub_agent() == "orchestrator"`, not on the topology number. |
| **D3** | The two merged agents get **new keys matching their names** — `design_engineer`, `requirements_analyst` — and therefore new `call_design_engineer` / `call_requirements_analyst` routing tools.  Rejected: reusing `designer` / `dc_output_inspector`.  The `call_<key>` string is agent-facing text, so a key that does not match the display name is exactly the near-miss the handover §2 warns produces mis-routes. |
| **D4** | The abandoned scaffolding is **deleted entirely** — `agents/architect/`, `agents/designer/`, every identity row, the four settings caps, and the topology-3 LLM-routing chart — with both keys added to `session.RETIRED_AGENT_KEYS` so archived sessions and R2 snapshots still load.  Same treatment topology 5 gave the Conductor and the Creator. |
| **D5** | `agents/3agent/` is a **complete mirror**, like `agents/5agent/`.  The smoke test's MIRROR invariant must show topology 3 reading ZERO files from the shared prompt trees. |
| **D6** | **Step caps: `max()` for the Requirements Analyst, `sum()` for the Design Engineer.**  The RA's two jobs — write the extraction, judge the render — happen in SEPARATE invocations, so it never needs both budgets at once: 40, the max of UII 40 and DCOI 40.  The DE's two jobs happen in the SAME invocation — author the parameters, then generate and render — so the budgets genuinely add: 120, the sum of DCIC 80 and TC 40.  Hub: 40 inner / 150 visits, identical to `Planner5`. |
| **D7** | **Models inherit through the merge map.**  Receptionist `gpt-5.4`, Planner `gpt-5.4-mini`, Requirements Analyst `gpt-5.4`, Design Engineer `gpt-5.4-mini`, Database Handler `gpt-5-mini`, Context Pruner `gpt-5.4`.  There is no conflict to resolve: each merged agent's two parents already carry the same model in topology 5.  Shipped as a `DEFAULT_PER_AGENT_MODELS_BY_TOPOLOGY[3]` overlay, never as an edit to the shared dict. |
| **D8** | **DH schedule: mechanical remap of the 33 five-agent rows, near-duplicates kept.**  `from_agent` and every `to_agents` entry rewritten through the merge map, then deduped WITHIN each row's target list.  Nothing is dropped.  Two questions that used to go to the UII and the DCOI separately now both go to the RA, which is honest — they are one agent now.  Pruning is deferred until a real topology-3 session has been saved and the interviews read. |
| **D9** | **`extra_utilities/dry_run_topology.py` is built, covering topologies 7, 5 AND 3.**  It does not exist today — the handover cites it, but it has never existed in this repo's history.  It drives ONE complete turn per topology against a scripted fake LLM: no network, no tokens.  It is the only lever that catches the §F class of defect (the blank user reply, the discarded start target, the `AttributeError` on a sub-agent the hub does not build), every one of which was invisible to the full static suite. |
| **D10** | **Prompt merges follow the owner's four-phase procedure** (§5).  Structural files may be created freely; merged CONTENT follows the procedure and nothing else. |
| **D11** | **NO ATTRIBUTION OF ANY KIND.**  No `Co-Authored-By`, no "Generated with", no collaborator, assistant or AI attribution line — not in commit messages, not in PR descriptions, not in this or any other documentation file, not in code comments or docstrings.  This is a hard rule for the whole build and it overrides any tooling default that asks for a trailer. |
| **D12** | **Build order is wiring first, prompts second** (§C of the runbook).  The 5-agent was built prompts-first and drifted silently; the drift was invisible to every static check and surfaced only on a live run. |
| **D13** | Scaffold prompts: the merge targets land at Stage 4 as a **mechanical concatenation of their two parents under a loud banner header**, so the skeleton assembles and Stages 5–8 can be verified at all.  They are replaced WHOLESALE at Stage 9 and never ship. |

---

## 3. OPEN items

| # | Question | Needed by |
|---|---|---|
| **O1** | Does the Design Engineer keep the DCIC's `new_attempt_parameters` (one call: validate → create folder → write `parameters.json`), or the abandoned Designer's split `new_attempt` + `write_parameters`?  The fork rule (D1) says the former; recorded because the deleted `designer.py` is the only prior art for this merge and it used the latter. | Stage 5 |
| **O2** | `DCOI_COMPARISON_MODE` under topology 3: in mode 2 the Requirements Analyst compares the render against `extracted_inputs.txt` — a file it WROTE itself.  Self-grading against one's own extraction is a different act from grading against another agent's, and the mode's prompt block says "if the extraction is wrong, that is an upstream UII problem to surface" — which now has no upstream.  Needs an owner decision or a prompt edit. | Stage 9 |
| **O3** | Whether the Design Engineer keeps the DCIC's `USEFUL INPUT IMAGES` strip on `read_extracted_inputs`.  It binds no image tools, so the section is still noise it cannot act on — the strip should stay — but it is worth confirming rather than inheriting silently. | Stage 5 |
| **O4** | A `"3"` profile in `database_access.json` mirroring `"7"`.  Moot while `RAG_ENABLED=False`, but without it every topology-3 agent gets all three RAG tools the moment the flag flips.  Same open item topology 5 carries as its O5. | Stage 8 |
| **O5** | `history_tool.py` hard-codes an 8-agent roster in its description and `feedback_tool.py` a 7-agent allow-list.  Topology 5 fixed both with overlay entries (`READ_AGENT_HISTORY_DESCRIPTION`, `SUBMIT_FEEDBACK_DISPATCH_DOC`).  Topology 3 needs its own. | Stage 8 |
| **O6** | End-of-session feedback distribution (Role 4) for topology 3.  Deferred, as it was in the 5-agent rebuild; not needed for the owner's current tests. | Deferred |
| ~~O7~~ | **PARTIALLY CLOSED in Stage 2.**  Every residual reference in a file Stage 1 or 2 already opened has been swept, including both user-visible strings (`editor.py`'s `CHAIN_ACCESS` inert-reason, and `settings.py` §27's topology help text, which still described the DELETED Conductor/Creator 5-agent system).  What is left sits only in files no stage has needed yet — `feedback_tool.py`, `receptionist.py`, `hub_format.py`, `user_inputs_tool.py` ×2, `user_queries_tool.py`, `hub_registry.py`, two smoke tests, `generate_mesh.py` ×2 — and each is folded into the stage that next touches its file. | folded |

---

## 4. Content inventory — what actually gets merged

`agents/5agent/` holds **97 files**.  Grouping every scoped copy by the LONGEST
matching agent key (a naive check drops nine DC Input Creator fragments,
because `generic_constraints_dc_input_creator` also ends with `_creator`):

| | count | becomes |
|---|---|---|
| Shared fragments — straight copy, suffix retargeted `_5agents` → `_3agents` | 40 | 40 |
| Agent prompts: `receptionist`, `planner`, `database_handler` — straight copy | 3 | 3 |
| **Agent prompts needing a 2→1 union** | 4 | **2** |
| Scoped fragments that are a pure rename | 24 | 24 |
| **Scoped fragments needing a 2→1 union** | 26 | **13** |
| **TOTAL** | **97** | **82** |

**Fifteen documents get merged, not two.**  This is the single most
under-estimated part of the job and the reason it is written down here.

### 4.1 The two prompt merges

```
agents/5agent/dc_input_creator/prompt_5agents.md   ┐
agents/5agent/tool_caller/prompt_5agents.md        ┘ →  design_engineer

agents/5agent/user_input_inspector/prompt_5agents.md  ┐
agents/5agent/dc_output_inspector/prompt_5agents.md   ┘ →  requirements_analyst
```

### 4.2 The thirteen scoped-fragment merges

| slot | → Design Engineer (dcic + tc) | → Requirements Analyst (dcoi + uii) |
|---|:---:|:---:|
| `dc_config/hard_constraints_dc` | ✔ | ✔ |
| `dc_config/parameters` | ✔ | ✔ |
| `dc_config/user_input_types/sketch_handling` | — | ✔ |
| `prompt_fragments/generic_constraints` | ✔ | — |
| `prompt_fragments/routing` | ✔ | ✔ |
| `tools_config/blade_sections_visualizer` | ✔ | ✔ |
| `tools_config/database_search` | ✔ | ✔ |
| `tools_config/hard_constraints_tools` | — | ✔ |

### 4.3 The twenty-four pure renames

Design Engineer, from the DCIC alone: `modelling_notes`,
`qualitative_examples`, `value_states`, `hard_constraints_tools`.
From the Tool Caller alone: `tool_inventory`.

Requirements Analyst, from the UII alone: `dc_structure`,
`generic_constraints`, `dc_params_primer_text`.
From the DCOI alone: `visual_inspection_guide`, `value_states`,
`user_input_types/sketch_notes`.

Unchanged agents (`planner` ×6, `receptionist` ×5): straight rename.

### 4.4 Merge doctrine (owner's, binding)

1. Lose **no** information, instruction or detail.
2. Break nothing in the 7- or 5-agent systems.
3. A **union, not a concatenation** — never state the same concept twice.
4. Different roles → the merged agent has **both**.
5. **Conflicting** roles must be resolved, not carried: any "you ONLY do X", or
   "do NOT do X because agent Y handles it", where Y no longer exists or is now
   the same agent, must be removed or retailored — never left standing.
6. Prefer **verbatim wording** from the source over rewriting.

Two conflicts are already known and will need a ruling at Stage 9:

* the Tool Caller is told it cannot escalate; the DCIC is told it escalates to
  the Planner.  Merged, the Design Engineer can (§1.2).
* the DCOI's comparison-source block tells it that a wrong extraction is "an
  upstream UII problem to surface"; merged, there is no upstream (O2).

### 4.5 What the deleted `agents/designer/designer.py` was worth

It was the only prior art for the DCIC + Tool Caller merge.  Read in full
before deletion (Stage 1.1); five things survive it, for Stage 5.

1. **`mesh_provenance_mismatches` (F75b) becomes moot.**  The Designer's
   `write_parameters` had to refuse a write that would contradict a mesh
   already sitting in the attempt folder — possible because `new_attempt` and
   `write_parameters` were two calls with a gap between them.  The DCIC's
   `new_attempt_parameters` creates the folder and writes into it in ONE call,
   so no pre-existing mesh can be there.  The guard disappears by
   construction.  This is the argument for O1's "keep the DCIC's tool".
2. **The Design Engineer needs no `read_parameters`.**  The Designer carried a
   local copy because round 2 of the prompt reduction removed it from the
   7-agent Tool Caller.  The DE writes `parameters.json` itself, in the same
   invocation it then generates from, so reading it back is a round-trip to
   learn what it just did.
3. **`render_check_block` must be read at WIRING time.**  Not from the
   module-level `RENDER_CHECK_LIBRARY_*` constants: those resolve at
   prompts-import and would pin the fragment to whatever `SYSTEM_TOPOLOGY` was
   on disk when the process started — and the Sessions Queue switches topology
   between runs inside one process.
4. **Keep `on_operation_end` even though it is a no-op.**  The DE binds no
   image tools, so there is never an image block to strip; the hook stays so
   the dispatcher's per-hop contract holds for every agent, and so it behaves
   correctly if image tools are ever added.
5. **The file was STALE, which is why the run loop is not copied from it.**  It
   predates the one-shot routing retry entirely (no `begin_routing_retry` /
   `finish_routing_retry`), it hard-codes `AgentHop("architect", …)` where
   every live agent now calls `topology.hub_key()`, and it still logged
   `[CREATOR]` in two places — the copy-paste failure mode this build has to
   avoid.  The DE's run loop comes from the CURRENT `dc_input_creator.py` and
   `tool_caller.py`, per D1.

---

## 5. The prompt-merge procedure (owner's, verbatim)

> First, I give you a series of paragraphs to keep and where I imagine the
> problems to arise.  That will be already a long list.  Then, You will author
> a faithful union using mostly the pieces I used and i review section by
> section, as your recommended step.  You will also propose WHERE these
> portions will be put, where they will be joined, and so fourth, proposing
> every concatenation / union.  Then, you check every system prompt from the
> 5-agent system and check what I missed/what I didn't signal to put, and we
> discuss how relevant each neglected section is.  Finally, we take care of
> useless repetitions that may have arose.

Restated as four phases, in order, for the two prompts AND the thirteen scoped
fragments of §4.2:

* **P1 — the owner's keep-list.**  Paragraphs to carry, plus where he expects
  trouble.
* **P2 — the authored union.**  Built mostly from his pieces, reviewed section
  by section.  Every placement, join and concatenation is PROPOSED, not
  applied: where each portion goes, what it is joined to, and why.
* **P3 — the neglect sweep.**  Every 5-agent system prompt is re-read against
  the result and everything not signalled in P1 is surfaced, with a relevance
  judgement per item, for discussion.
* **P4 — de-duplication.**  Repetitions that arose from the union are removed.

Nothing is written to a merged prompt outside this procedure.

---

## 6. Build stages — in this order

Each stage is separately reviewable and separately committable, and each ends
with the snapshot diff of §7 proving topologies 7 and 5 have not moved.

### Stage 0 — Plan + baseline  *(docs only)*  — **DONE 2026-09-05**

- [x] 0.1 This document.
- [x] 0.2 Baseline captured with `topology_prompt_snapshot.py save` — see §8.
- [x] 0.3 Pre-work state of the smoke suite recorded — see §8.2.  Two suites
      fail on `ModuleNotFoundError: No module named 'trimesh'`, which is
      environmental and pre-existing; recorded so neither can later be blamed
      on this work.
- [x] 0.4 `git status` clean before the stage.

### Stage 1 — Retire the abandoned scaffolding  (D4)  — **DONE 2026-09-05**

33 scripted edits across 20 files plus 2 package deletions; 24 files changed,
+50 / −2 035.

- [x] 1.1 Deleted `agents/architect/` (2 files, 1 193 lines) and
      `agents/designer/` (2 files, 634 lines).  `designer.py` was read in full
      first and the five things worth carrying are recorded in §4.5.
- [x] 1.2 Stripped the `architect` / `designer` rows from every registry:
      `routing_tools.AGENT_DISPLAY` + `_TOOL_DESCRIPTIONS` (both
      `call_architect` and `call_designer`), `trace._AGENT_DISPLAY_NAMES`,
      `base_chain_agent._PRUNE_DISPLAY_NAMES`,
      `prompts._NON_CHAIN_AGENTS` + `PROMPT_MD_RUNTIME_SLOTS`,
      `dc_primer.PRIMER_AGENT_KEYS`, `database_access.DEFAULT_AGENTS`,
      `db_writer.DEFAULT_AGENTS_TO_ACL`, `ocr_access.DEFAULT_AGENTS`,
      `llm_defaults.DEFAULT_PER_AGENT_MODELS`, `llm_routing.AGENT_SPEC`,
      `dh_schedule.AGENT_KEYS` + `AGENT_SHORT_LABELS`,
      `sessions_queue.AGENTS_BY_TOPOLOGY[3]`,
      `orchestrator._AGENT_KEY_ALIASES`, and the
      `smoke_test_topology_fragments` FACTORY sentinel.
- [x] 1.3 Deleted `MAX_ARCHITECT_STEPS` (60), `MAX_ARCHITECT_VISITS` (150),
      `MAX_DESIGNER_STEPS` (85) and `MAX_ROUNDS_BEFORE_ARCHITECT_CHECKPOINT`
      (3) from `settings.py` §28 (−61) and `agents/step_caps.py` (−30).  This
      also cleared a pre-existing defect: `step_caps.py` held an ORPHANED
      docstring — the string written for `MAX_DESIGNER_STEPS` sat after
      `MAX_ROUNDS_BEFORE_ARCHITECT_CHECKPOINT`'s own docstring, documenting
      nothing.
- [x] 1.4 `session.RETIRED_AGENT_KEYS` += `architect`, `designer`, with the
      retirement recorded beside the Conductor / Creator one.
- [x] 1.5 **`agents/hub.py` RAISES for topology 3** rather than losing the
      branch.  Deleting it would have made `build_hub` return the
      Orchestrator, i.e. silently run the 7-agent set under a 3-agent label —
      runbook row 15, and the exact thing the DEGRADE test's own comment
      forbids.  The raise is removed at Stage 6.
- [x] 1.6 **`topology._HUB_BY_TOPOLOGY[3]` → `("planner", "Planner")` moved
      into this stage** (it was filed as 2.4).  It cannot wait: the suite's
      TABLES check asserts every `_HUB_BY_TOPOLOGY` display name equals its
      `AGENT_DISPLAY` entry, so deleting the `architect` row from one and not
      the other turns the suite red.  Net effect on topology 3 is nil — it
      still raises `FileNotFoundError`, now on `routing_planner.md` instead of
      `routing_architect.md`.
- [x] 1.7 Two suites that named the deleted agents, fixed in the same commit:
      `smoke_test_dc_primer`'s case-5 tuple (it READS
      `agents/designer/designer.py` from disk, so the deletion would have
      crashed it) and `smoke_test_topology_fragments`'s `_SentinelArchitect`,
      its `agents.architect` stub module and its `(3, "architect")` FACTORY
      row.
- [x] 1.8 **VERIFIED.**  Snapshot diff: **0 differences** — all nine
      topology-7 and all seven topology-5 full prompts byte-identical to the
      §8.1 baseline.  All eight runnable suites pass, unchanged from §8.2.
      `pyflakes`: 20 warnings, the same set as the baseline, every one in a
      file this stage did not touch.  No `\r\r\n` in any edited file.
      Behavioural checks the offline suite cannot cover, run through
      `bootstrap.install()`: `llm_routing.AGENT_KEYS` and
      `sessions_queue._all_agent_keys()` both shrank 12 → 10 and remain equal
      (`smoke_test_llm_routing`'s assertion, which cannot run here for want of
      `trimesh`); all four retired keys still load as inert `AgentState`s while
      an unknown key is still rejected; and `hub_class()` returns
      `Orchestrator` under 7, `Planner5` under 5, and raises under 3.

**Deliberately left standing, and why.**  `routing._PIPELINE_BY_TOPOLOGY[3]`
still reads `Architect → Designer → DC Output Inspector → Architect`, and
`web/app.js`'s `LR_BOXES_3` / `LR_ARROWS_3` still draw an Architect and a
Designer.  Both are rewritten wholesale at Stage 2 (2.6 and 2.7) rather than
deleted here and re-added there — `LR_ARROWS_3` in particular is hand-derived
coordinate pairs, and touching that block twice invites an error.  Both are
inert: topology 3 cannot be constructed at all until Stage 6.

**Comment residue — a separate sweep.**  Fourteen prose references to the
Architect / Designer survive in files this stage had no reason to edit
(`feedback_tool.py`, `receptionist.py`, `dc_primer.py` module docstring,
`hub_format.py`, `user_inputs_tool.py` ×2, `user_queries_tool.py`,
`editor.py`, `settings.py` §21, `hub_registry.py`, `smoke_test_hub_attributes`,
`smoke_test_orchestrator`, `generate_mesh.py` ×2, `web/app.js:2443`), plus
`topology.topology()`'s docstring still saying "(7 or 5)".  None affects
behaviour; one — `editor.py`'s CHAIN_ACCESS inert-reason string — is
user-visible in the Workflow Settings UI.  Tracked as **O7**.

### Stage 2 — Register the new roster  (runbook Stage A: additive)  — **DONE 2026-09-05**

26 scripted edits across 18 files; +245 / −43.

- [x] 2.1 `AGENT_DISPLAY` += `design_engineer`, `requirements_analyst`, done
      FIRST — `ROUTING_TOOL_NAMES` and `session.KNOWN_AGENT_KEYS` both derive
      from it, and a miss there raises immediately, which is the good case.
- [x] 2.2 `_TOOL_DESCRIPTIONS` += `call_design_engineer`,
      `call_requirements_analyst`, generic shared wording; the topology-3
      wording lands in the overlay at Stage 8.
- [x] 2.3 The remaining identity rows: `trace`, `_PRUNE_DISPLAY_NAMES`,
      `PROMPT_MD_RUNTIME_SLOTS` (each merged agent takes the UNION of its two
      parents' slots), `dc_primer.PRIMER_AGENT_KEYS`, `database_access`,
      `db_writer` ACL, `ocr_access` **(RA only)**, `llm_defaults` + the `[3]`
      overlay, `llm_routing.AGENT_SPEC` with `wired_into_dispatcher=False`,
      `dh_schedule` keys + labels ("DEng" / "RA"),
      `sessions_queue.AGENTS_BY_TOPOLOGY[3]`.
- [x] 2.4 **DONE in Stage 1** — it could not wait; see 1.6.
- [x] 2.5 Step caps (D6) in `settings.py` §28, forwarded through
      `step_caps.py`, each carrying its own reasoning so the `max()`-vs-`sum()`
      asymmetry cannot later be "tidied" into one rule.
- [x] 2.6 `routing._PIPELINE_BY_TOPOLOGY[3]` → the §1.3 string.
- [x] 2.7 `web/app.js` — `LR_BOXES_3` / `LR_ARROWS_3` rebuilt.  `node --check`
      passes.  **Rendered and inspected twice**; see the note below.
- [x] 2.8 **VERIFIED.**  Snapshot diff **0 differences** — all sixteen
      topology-7 and topology-5 prompts still byte-identical to the §8.1
      baseline.  Eight suites pass; `pyflakes` still 20, the same set.
      Behavioural checks through `bootstrap.install()`: `AGENT_SPEC` and the
      queue union both grew 10 → 12 and remain equal; both keys present in all
      eight registries that need them and in `ROUTING_TOOL_NAMES`; `AgentState`
      accepts both; the full model-resolution table for topologies 7 / 5 / 3
      printed and checked, with topology 7's Planner still `gpt-5-mini` and
      topology 5's still `gpt-5.4-mini`; the topology-3 pipeline string names
      the Receptionist at both ends and no retired agent; all four new caps
      resolve, `MAX_PLANNER5_*` unmoved, all three deleted caps confirmed gone.

**Two decisions inside 2.3 worth keeping.**

*The two new keys DO get base `DEFAULT_PER_AGENT_MODELS` entries*, which looks
like a violation of D7's "overlay, never the shared dict".  It is not: that rule
protects agents topologies 7 and 5 also build.  These keys exist ONLY under
topology 3, so a base entry cannot move anything — while its absence would drop
them to `FALLBACK_MODEL` in every consumer that iterates ALL agent keys
(`llm_routing`, the loader's startup banner).  The `[3]` overlay is still
written in FULL, like topology 5's, so the table is the whole truth for the
topology rather than a diff the reader must compute; exactly one entry differs
from base — `planner` `gpt-5-mini` → `gpt-5.4-mini`.

*`ocr_access` gets the Requirements Analyst and NOT the Design Engineer.*  The
RA merges the UII and the DCOI, both image-tool binders.  The DE merges the DC
Input Creator and the Tool Caller, neither of which binds one — so a flag for
it would be the same dead switch that tuple's own comments record dropping
twice before.

**`dc_primer._TEXT_NAME_BY_AGENT` deliberately did NOT get its row.**  Unlike
every other table here it gates a FILE READ, and the Requirements Analyst's
primer text does not exist until Stage 4.  Adding the row now would point at a
missing shared path.  Same "land the data before the resolver" rule as the DH
schedule; it moves to Stage 4.

**The chart was rendered twice, and the first render did not count.**  The
first mock wrapped long labels onto two lines.  The production renderer
(`app.js:2217-2226`) does no such thing — it emits a SINGLE unwrapped `<text>`
at `y + 22`, 12 px, white on `#2c6cb7`, and SVG text does not clip, so an
over-long label spills outside its box.  Re-rendered faithfully against the real
fill colours, font sizes and baselines, and every label measured: "Requirements
Analyst" is 116 px in a 140 px box — the longest in the chart, and exactly the
same character count as the "User Input Inspector" already shipping in a 140 px
box in topologies 5 and 7.  Nothing overflows; no line crosses a box.

**The Design Engineer sits on the RIGHT deliberately.**  It absorbed the Tool
Caller, so it is the box the two tool diagonals leave from; with it on the left
both lines would cross straight through the Requirements Analyst.  Those two
diagonals are also NEW — the old 3-agent chart drew none at all, the same
omission the topology-5 rebuild had to repair in `LR_ARROWS_5`.

**O7, partially closed.**  The residue in files this stage already opened was
swept: `editor.py`'s `CHAIN_ACCESS` inert-reason and `settings.py` §27's
topology help text (**both user-visible** — and §27 still described the DELETED
Conductor/Creator 5-agent system while offering topology 3 as a valid value),
`settings.py` §21's primer roster, `dc_primer.py`'s module docstring,
`web/app.js`'s per-agent `.env` note, and `topology.topology()`'s `"""(7 or
5)"""`.  What remains is only in files no stage has needed yet.

### Stage 3 — DH schedule  (D8)

- [ ] 3.1 `workflow_settings/dh_schedule_3agents.default.json` — the 33 rows
      remapped.
- [ ] 3.2 `dh_schedule._SCHEDULE_BY_TOPOLOGY[3] = "_3agents"`.
- [ ] 3.3 VERIFY: `smoke_test_dh_batching` (which today covers only topologies
      7 and 5 — it gains a topology-3 case here).

> **⚠ Order is load-bearing.**  The DATA file must land BEFORE the resolver
> entry.  Reversed, `_seed_default` falls through to the 29-row
> topology-blind hardcoded `SCHEDULE` and writes it to disk permanently.

### Stage 4 — Prompt tree fork  (D5, D13)

- [ ] 4.1 Fork 82 files into `agents/3agent/`: 40 shared + 3 unchanged agent
      prompts + 24 renamed scoped + 13 merged scoped + 2 merged prompts.
- [ ] 4.2 The 15 merge targets land as **banner-marked scaffolds** (D13).
- [ ] 4.3 `routing._sections_for` opened to topology 3 — currently
      `topo not in (7, 5)`, so topology 3 gets the FULL historic routing
      section set, roughly +3 700 characters per agent.  Without this,
      "identical to topology 5" is false by ~15 000 characters.
- [ ] 4.4 VERIFY: 7 and 5 byte-identical; the MIRROR invariant shows topology 3
      reading ZERO shared prompt files.

### Stage 5 — The two agent classes

- [ ] 5.1 `agents/requirements_analyst/` — union of `UserInputInspector` and
      `DCOutputInspector`.  Tools: `read_user_inputs`, `write_extraction`,
      `read_extracted_inputs`, `read_attempts`, `calculate`, `view_images`
      (+ `reread_text_regions` when OCR is on), the DBa set, routing.
- [ ] 5.2 `agents/design_engineer/` — union of `DCInputCreator` and
      `ToolCaller`.  Tools: `read_extracted_inputs`,
      `new_attempt_parameters` (O1), `read_attempts`, `calculate`,
      `get_tools()`, `render_blade_sections` when enabled, the DBa set,
      routing.  **No image tools** — neither parent binds any.
- [ ] 5.3 `PROMPT_MD_RUNTIME_SLOTS` rows for both.  An unlisted `{x}` makes
      `str.format` raise `KeyError` at agent construction, i.e. at runtime.
- [ ] 5.4 VERIFY: `smoke_test_hub_attributes`; `smoke_test_prompt_tool_audit`.

### Stage 6 — The hub class  (D2)

- [ ] 6.1 `agents/planner3/planner3.py` — starts as a byte-for-byte copy of
      `agents/planner5/planner5.py`, then re-pointed.  Plus its own
      `role4_feedback_instructions.md` (the path is `__file__`-relative).
- [ ] 6.2 `_agents_by_key` = FOUR entries: `self.AGENT_KEY -> self`,
      `design_engineer`, `requirements_analyst`, `receptionist`.
- [ ] 6.3 `_wire_routing` for the §1.2 edge set.  No branches.
- [ ] 6.4 `_DIRECTIVE_CARRIERS` = `{design_engineer, requirements_analyst}`.
      The hub is the directive's AUTHOR and is excluded.
- [ ] 6.5 **Re-key the precision-round counter.**  `planner5.py:724` reads
      `if hop.target == "dc_output_inspector" and …: precision_rounds += 1`.
      Under topology 3 that key is never built, so ported unchanged the guard
      never fires, `precision_rounds` stays 0 forever, and the entire precision
      section-matching loop vanishes with **no error and no log line**.  It
      must become `"requirements_analyst"`, and it gets a mutation test.
- [ ] 6.6 `_AGENT_KEY_ALIASES`, `reset()`, `dump_histories()` (4-tuple) and
      `_surface_limit_to_user()` re-pointed — the last reads
      `self.dc_output_inspector` and `self.tool_caller` today.
- [ ] 6.7 `agents/hub.py` topology-3 branch → `Planner3`;
      `llm_routing` `wired_into_dispatcher` → `True`.
- [ ] 6.8 VERIFY: `smoke_test_hub_attributes` (edge set asserted from source
      with `ast`, not from a comment); 7 and 5 byte-identical.

### Stage 7 — Verification harness  (D9)

- [ ] 7.1 `extra_utilities/dry_run_topology.py` — one complete turn per
      topology against a scripted fake LLM.  Asserts the full topology-3 hop
      sequence and locks 7 and 5 against regression at the same time.
- [ ] 7.2 `smoke_test_topology_fragments.py` — topology-3 rows in all seven
      per-topology tables.
- [ ] 7.3 `prompt_pdf/dump.py --topology 3` → `dump3.json`, feeding the
      prompt-names-a-tool ⇄ class-binds-a-tool audit.
- [ ] 7.4 **Every new check mutation-tested.**  A check that has never failed
      has not been shown to work; two of this suite's checks were silently
      vacuous until they were mutation-tested.
- [ ] 7.5 `SMOKE_TESTS.md` rows for the new checks;
      `prompt_pdf/.gitignore` already carries `dump3.json`.

### Stage 8 — Tool-layer overlay  (D3)

- [ ] 8.1 `agents/topology3/tool_text.py` — the same shape as
      `agents/topology5/tool_text.py`: every per-agent tool table, fully
      populated, SHADOWING rather than merging.  Entries for agents topology 3
      does not build are dropped.
- [ ] 8.2 `TOOL_DESCRIPTIONS` for `call_planner`, `call_design_engineer`,
      `call_requirements_analyst`, `call_receptionist`.
- [ ] 8.3 O4 and O5 resolved here.

### Stage 9 — The merged prompts  (D10, §5)

The real content work.  Four phases, owner-driven, for the 2 prompts and the
13 scoped fragments.  The Stage-4 scaffolds are replaced wholesale.

### Stage 10 — Live run

Static checks cannot see behaviour.  Both 5-agent live runs found defects the
full static suite could not.

---

## 7. Verification protocol — applies to EVERY change from here on

1. Assemble both defended topologies BEFORE the change; hash every agent.
2. Make the change.
3. Assemble AFTER; hash every agent.
4. State explicitly **which agents moved and which are byte-identical**, and
   show the diff for every one that moved.
5. Never claim a check passed without showing its output.

```bash
py -3.13 extra_utilities/topology_prompt_snapshot.py save <dir>
py -3.13 extra_utilities/topology_prompt_snapshot.py diff <dirA> <dirB>
py -3.13 extra_utilities/smoke_test_topology_fragments.py
py -3.13 extra_utilities/smoke_test_prompt_tool_audit.py
py -3.13 extra_utilities/smoke_test_hub_attributes.py
py -3.13 extra_utilities/smoke_test_dh_batching.py
py -3.13 extra_utilities/smoke_test_prompts_hot_reload.py
py -3.13 -m pyflakes agents/ workflow_settings/ web_app.py
```

Environment: **`py -3.13`** (the default 3.8 cannot parse `prompts.py`'s
PEP-604 hints).  `trimesh`, `langchain_openai` and `langchain_anthropic` are
NOT installed — use `extra_utilities/prompt_pdf/bootstrap.py` to import the
agent tree, and `OPENAI_API_KEY=sk-dummy` to construct agents (a key must be
present; no network call is made).  `PYTHONIOENCODING=utf-8` when piping tool
output or a `→` in a diff kills the run on cp1252.

---

## 8. Stage-0 baseline — the numbers every later claim is checked against

### 8.1 Assembled prompts, 2026-09-05 at `f24f038`

`chars` / `sha256[:12]` of the FULL prompt (runtime slots filled), from
`topology_prompt_snapshot.py`.

**Topology 7** — hub `orchestrator`, `PLANNER_FIRST=False`, `DCII=True`,
9 agents built, 0 unavailable:

| agent | chars | sha256[:12] |
|---|---:|---|
| `database_handler` | 22 780 | `fb7b6b2c33ed` |
| `dc_input_creator` | 24 444 | `6d8a5e70c981` |
| `dc_input_inspector` | 18 794 | `f8d84b85c795` |
| `dc_output_inspector` | 19 576 | `3525c8805e46` |
| `orchestrator` | 16 900 | `f681d36e0b53` |
| `planner` | 21 783 | `df166732af60` |
| `receptionist` | 16 036 | `d7bd2399fa4d` |
| `tool_caller` | 9 317 | `71835c0f1f05` |
| `user_input_inspector` | 14 393 | `53a39d746b8d` |

**Topology 5** — hub `planner`, `PLANNER_FIRST=False`, `DCII=False`,
7 agents built, 0 unavailable:

| agent | chars | sha256[:12] |
|---|---:|---|
| `database_handler` | 22 338 | `54c27087079d` |
| `dc_input_creator` | 23 465 | `8cb1578b61e1` |
| `dc_output_inspector` | 19 771 | `29e0fea6c7fd` |
| `planner` | 25 297 | `70514bdc6fc5` |
| `receptionist` | 15 978 | `370c1cc62d5b` |
| `tool_caller` | 9 040 | `df6a4b436e92` |
| `user_input_inspector` | 14 400 | `0ecf3a4bf846` |

**Topology 3** — `FATAL FileNotFoundError:
agents/shared/prompt_fragments/routing_architect.md`.

Nothing assembles.  This failure predates the rebuild and is recorded here so
it can never later be attributed to it.

> **Topology 5 has DIVERGED from topology 7.**  The 5-agent Planner template is
> 23 765 chars against the 7-agent's 20 786, the DCIC 22 466 against 23 208.
> This is the measurement behind D1: forking topology 3 from the shared tree
> would re-import text topology 5 has already moved past.

### 8.2 Smoke suite, same commit

| suite | result |
|---|---|
| `smoke_test_topology_fragments` | **PASS** — every override reached, no original leaked, no cross-topology read.  Topology 5 reads 91/97 overrides, 0 shared; the 6 unread are flag-gated variants. |
| `smoke_test_prompt_tool_audit` | **PASS**, 10 known-pending NOTEs |
| `smoke_test_hub_attributes` | **problems: none** — Planner5 13 routing edges |
| `smoke_test_dh_batching` | **ALL PASS** — topology 7 36 rows, topology 5 33 rows.  Covers only 7 and 5 today. |
| `smoke_test_prompts_hot_reload` | **OK** |
| `smoke_test_queue_tiers` | **ALL CHECKS PASSED** |
| `smoke_test_slot_splices` | **PASS** — 216 targets, 69 multi-line slot refs |
| `smoke_test_dc_primer` | **PASS** |
| `smoke_test_llm_routing` | **FAIL — environmental.**  `ModuleNotFoundError: No module named 'trimesh'` at import. |
| `smoke_test_prompt_format` | **FAIL — environmental.**  Same missing module. |
| `pyflakes agents/ workflow_settings/ web_app.py extra_utilities/*.py` | 20 warnings, every one in a file this work has not touched |

---

## 9. Traps carried forward

1. **A stale `.pyc` can serve the wrong `SYSTEM_TOPOLOGY`.**  Python invalidates
   bytecode on (mtime, size) and flipping `7`→`5`→`3` is **size-preserving**.
   Symptom: the file plainly reads `3`, `git diff` is clean, the import yields
   something else.  Fix:
   `find . -name __pycache__ -type d -not -path './.git/*' -exec rm -rf {} +`.
   Suspect it whenever a red test contradicts a green one from earlier.
2. **A `$slot` resolves to the agent-SCOPED copy**, which can differ in
   substance.  Never read a base fragment and assume that is what the agent
   receives — assemble the prompt.
3. **A scoped file whose slot is not registered in `SCOPED_FRAGMENTS` is
   silently inert** — no error, no log line.
4. **A scoped fragment added to the SHARED tree leaks across topologies**,
   because `scoped_fragment_path` keys on `agent_dir_name`.  Topology 3's two
   merged agents have brand-new dir names, so they are safe by construction —
   but `planner` and `receptionist` are shared with topologies 5 and 7 and are
   NOT.  Asking "is it scoped?" is the wrong question; assemble and diff.
5. **Empty a fragment, do not delete it.**  A missing scoped override falls back
   to the longer shared file — the opposite of removing text.  A zero-byte file
   still overrides.
6. **All prompt files are CRLF**, `core.autocrlf=true`.  Building a string as
   `"a" + nl + "b"` then `.replace("\n", nl)` yields `\r\r\n`, which makes git
   stop normalising and explodes the diff to the whole file.  Convert once, at
   the boundary; `d.count(b"\r\r\n")` is the direct test.
7. **A prose-only turn from a chain agent does not end it** — it fires the
   one-shot routing retry and the agent is invoked AGAIN.  Only the
   Receptionist treats prose as the answer.
8. **A schedule row naming an agent the hub does not build is not a warning** —
   the DH writes `ERROR:` rows into the R2 mirror and the Postgres `chunks`
   table, where they come back at retrieval time.
9. **The DC-parameter primer injects at INVOKE time** and bypasses every
   prompt-level filter.  It resolves through `_topology_override`, so the
   3-agent tree needs its own primer files or it silently serves the shared
   ones — and `_TEXT_NAME_BY_AGENT` must learn the new keys.
10. **The standing-directive re-stamp is invisible in logs.**  `[AGENT MSG]` is
    written by the routing tool *before* the dispatcher re-stamps, so a log
    showing the block once does not mean it was lost.
11. **Never use `DC_INSPECTOR_ENABLED` as a topology lever.**  It is global.
12. **`agents/loader.py` logs the 7-agent roster literally under every
    topology.**  Cosmetic, but it will lie in every topology-3 log.
13. **A refine ROUND is a full cycle, not a hop.**  `precision_rounds += 1`
    fires once per ARRIVAL at the inspector, so
    `DCOI → DCIC → TC → DCOI` counts as one.  `MAX_SECTIONS_REFINE_ROUNDS = 12`
    therefore means 12 render-and-judge cycles in every topology; the merge
    removes one hand-off per round, not a third of the round.
