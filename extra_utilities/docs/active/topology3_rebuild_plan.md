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

- [x] 3.1 `workflow_settings/dh_schedule_3agents.default.json` — 33 rows,
      18 316 bytes.  `from_agent` and every `to_agents` entry remapped
      (`uii`/`dcoi` → RA, `dcic`/`tc` → DE) with an order-preserving dedupe
      WITHIN each row's target list; exactly two rows shrink, both having
      listed the UII and the DCOI separately.  Row `id`s, `name`s,
      `description`s, `scope`, `type`, `parent_id` and `sub_index` are
      untouched, so provenance back to the 5-agent source is exact.
      Resulting tallies — from: RA 17, planner 8, DE 5, receptionist 3.
- [x] 3.2 `dh_schedule._SCHEDULE_BY_TOPOLOGY[3] = "_3agents"`, landed AFTER
      the data file, with the ordering trap written into the comment above it.
- [x] 3.3 `smoke_test_dh_batching` gains a topology-3 row in `_HUBS`, and
      **mutation-tested both ways**: a row naming `tool_caller` fails it, and a
      30-row file fails it.  File restored and hash-checked afterwards.
- [x] 3.4 **VERIFIED.**  Snapshot diff 0 differences.  Cold-seed test — runtime
      file deleted first, because that is the case that actually matters —
      seeds **33 rows** under topology 3, i.e. the new default and NOT the
      29-row topology-blind hardcoded `SCHEDULE`; every `agent_key` and every
      `to_agents` entry is on the topology-3 roster; topologies 7 and 5 still
      seed their own files at 36 and 33 rows; and `_validate` still rejects a
      row naming the retired `architect`.  Eight suites pass, `pyflakes` still
      20.

**The writer was proved before it was trusted.**  The generator round-trips
`dh_schedule_5agents.default.json` **byte-for-byte** (2-space indent,
`ensure_ascii=False`, CRLF, trailing newline) before authoring anything, so the
new file is in house format rather than merely valid JSON.

**`.gitignore` was missing the topology-3 runtime file.**  It listed
`dh_schedule.json` and `dh_schedule_5agents.json` but not
`dh_schedule_3agents.json`, which is written on first use — so the per-deploy
file would have shown up as untracked and could have been committed over the
tracked default.  Added.

**The six stale question NAMES were left verbatim, on the owner's word:** the
schedule is a SEED, and the Workflow Settings UI lets him author a different
question set per topology, so `Problem - UII` / `Problem - DCIC` / `Tool Caller
problem` are his to adapt if he runs the DH under topology 3.  Recorded because
the name is not cosmetic — `database_handler._slugify` turns it into the stored
filename and the DB field label, and those come back at RAG retrieval time.

**The F19d roster check degrades honestly rather than being skipped.**  Its
strict form derives "which agents does the hub build" from the hub class's own
`_agents_by_key` literal, and `agents/planner3/planner3.py` does not exist until
Stage 6.  Until it does, the check falls back to the DECLARED queue roster and
prints a `PENDING` line naming what it substituted; it upgrades itself
automatically the moment the hub module lands.  Every other assertion in the
topology-3 case runs at full strength.

> **⚠ Order is load-bearing.**  The DATA file must land BEFORE the resolver
> entry.  Reversed, `_seed_default` falls through to the 29-row
> topology-blind hardcoded `SCHEDULE` and writes it to disk permanently.

### Stage 4 — Prompt tree fork  (D5, D13)

- [x] 4.1 **Forked 97 → 82 files** into `agents/3agent/`: 40 shared + 3
      unchanged agent prompts + 24 renamed scoped + 13 merged scoped + 2 merged
      prompts.  Done in BYTES throughout — the source tree is CRLF and both
      parents of every merge already are, so appending them verbatim cannot
      produce the `\r\r\n` that makes git stop normalising a file.  Verified:
      0 files with `\r\r\n`, 0 with a bare LF.
- [x] 4.2 The 15 merge targets carry a **`SCAFFOLD - NOT THE FINAL TEXT`
      banner** naming both parents, plus a `SCAFFOLD JOIN` line at the seam.
      Both strings are greppable, so Stage 9 can enumerate what is still
      provisional rather than relying on memory.
- [x] 4.3 `routing._sections_for` opened to topology 3 — **and the table it
      guards needed two new rows, which the plan had missed.**  Opening the
      gate alone would not have worked: `_ROUTING_SECTIONS_BY_AGENT` is keyed
      by DISPLAY name, and "Design Engineer" / "Requirements Analyst" are not
      in it, so both merged agents would have fallen through to
      `_ROUTING_SECTIONS_DEFAULT` — the full historic set, ~3 700 characters
      each — exactly the outcome the step exists to prevent.
- [x] 4.4 `dc_primer._TEXT_NAME_BY_AGENT` gained its `requirements_analyst`
      row, deferred from Stage 2 until the file it points at existed.
- [x] 4.5 **VERIFIED.**  Snapshot diff 0 differences.  All five topology-3
      agents assemble, and **every one reads ZERO files from either shared
      prompt tree** — the MIRROR invariant, checked by instrumenting
      `Path.read_text` around each `_build_template` call in a subprocess per
      topology.  The three carried-over agents are **byte-identical to
      topology 5's**: planner `d8c14a62a81f` 23 765, receptionist
      `370c1cc62d5b` 15 978, database_handler `54c27087079d` 22 338.  Eight
      suites pass; `pyflakes` still 20.

**The `mandatory_tail` asymmetry is deliberate and load-bearing.**  The Design
Engineer gets `("fragment", "mandatory_tail")`; the Requirements Analyst gets
`("fragment",)` alone.  The reason is a fact about the source fragments, not a
preference: `routing_user_input_inspector_5agents.md` carries the whole
`### Routing is a tool call — MANDATORY` section INSIDE itself — which is why
the UII's own row is `("fragment",)` — so the merged RA fragment already states
the mandate once, and adding the tail would state it twice.  Neither the DC
Input Creator's fragment nor the Tool Caller's carries it, so the DE needs it.
Saying the same routing rule twice is not harmless: the ID252-262 analysis
traced all three routing failures to agents carrying the mandate three times.

**A scaffold is ~40 % larger than the union will be, by construction.**  Design
Engineer 43 722 chars, Requirements Analyst 41 771 — against parents of
22 466 + 8 268 and 12 571 + 17 241.  The excess is not content: concatenating
two `prompt.md` files makes `_build_template` splice every shared `$slot`
TWICE.  Stage 9 collapsing the duplicates is most of where that goes.

**Known-pending, and expected:** the topology-3 scaffolds name tools nothing in
topology 3 binds — `call_tool_caller`, `call_dc_input_creator`,
`call_planner`'s neighbours — because the fragments are verbatim topology-5
text.  `smoke_test_prompt_tool_audit` does not see this yet (it covers only the
topologies with a `dump*.json`); topology 3 joins it at Stage 7.3, where these
become named known-pending entries exactly as topology 5's
`call_orchestrator` ones did.

### Stage 5 — The two agent classes

- [x] 5.1 `agents/requirements_analyst/` — union of `UserInputInspector` and
      `DCOutputInspector`.  **9 tools measured, not assumed:** `calculate`,
      `call_design_engineer`, `call_planner`, `read_attempts`,
      `read_extracted_inputs`, `read_user_inputs`, `reread_text_regions`,
      `view_images`, `write_extraction`.
- [x] 5.2 `agents/design_engineer/` — union of `DCInputCreator` and
      `ToolCaller`.  **8 tools measured:** `calculate`, `call_planner`,
      `call_requirements_analyst`, `generate_and_render_propeller`,
      `new_attempt_parameters`, `read_attempts`, `read_extracted_inputs`,
      `render_blade_sections`.  No image tool, because neither parent binds
      one.
- [x] 5.3 `PROMPT_MD_RUNTIME_SLOTS` — done in Stage 2; both prompts
      `.format()` cleanly, which is the proof (an unlisted `{x}` raises
      `KeyError` at construction).
- [x] 5.4 **VERIFIED.**  Both classes construct, wire and assemble — Design
      Engineer 48 336 chars, Requirements Analyst 50 530.  Snapshot diff 0
      differences; `pyflakes` clean on both new packages and still 20
      repo-wide.

**`calculate` is bound exactly once, and that needed care.**  `get_tools()`
returns `[generate_and_render_propeller, calculate]`, and the DC Input Creator
half binds `calculate` explicitly — so a naive union would have bound it twice.
The tool map is keyed by NAME, which collapses it; asserted rather than
assumed.

**Both `@tool` stubs are LOCAL copies, not imports of the parents'.**  Their
docstrings ARE the descriptions the model reads, so importing
`read_extracted_inputs` from `dc_input_creator` would mean a topology-3 wording
edit silently moving topologies 5 and 7 — the isolation rule this rebuild is
bound by.  Same reason the retired Designer kept its own copies.

**The run loops come from the CURRENT parents, per §4.5.**  Both carry the
one-shot routing retry (`begin_routing_retry` / `finish_routing_retry`), the
stuck-loop signature check, `finalize_unanswered_tool_calls`, and
`topology.hub_key()` on every error fall-through — none of which the retired
`designer.py` had.

**Two verification mistakes worth recording, because both produced a
confident-looking wrong answer.**  The first binding probe read
`llm.kwargs["tools"]` and reported **0 tools bound** for both agents: under
`bootstrap.install()` the LLM is a `MagicMock`, so nothing is readable off the
bound object.  The second attempt patched `base_llm.bind_tools` to record its
argument — and recursed to the stack limit, because the two agents SHARE one
`base_llm`, so the second agent's spy wrapped the first.  The working form
records the argument and restores the original in a `finally`.  Until that was
fixed the check also reported `view_images` as unbound by the Requirements
Analyst, which was false — the tool comes from `build_user_inputs_tools`, which
is passed straight into `all_tools` and never touches
`_extra_utility_tools_by_name`.

**Known-pending, measured:** the assembled prompts still NAME
`call_tool_caller`, `call_dc_input_creator` and `call_dc_output_inspector` —
tools nothing in topology 3 binds — because the routing fragments are verbatim
topology-5 scaffolds.  This is the same class topology 5 carried as
`call_orchestrator`, and it clears at Stage 9.

### Stage 6 — The hub class  (D2)

- [x] 6.1 `agents/planner3/planner3.py`, **25 scripted anchor replacements**
      over a byte-for-byte copy of `planner5.py`.  Every replacement asserts
      its anchor matches exactly once, so a drifted source fails loudly rather
      than silently skipping an edit — which it did, three times, on anchors
      transcribed from memory instead of from the file.  Plus its own
      `role4_feedback_instructions.md` (`Path(__file__).parent`-relative).
- [x] 6.2 `_agents_by_key` = FOUR entries.
- [x] 6.3 `_wire_routing` for the §1.2 edge set.  No branches.  **8 edges
      wired**, read back out of the source with `ast`.
- [x] 6.4 `_DIRECTIVE_CARRIERS` = `{design_engineer, requirements_analyst}`.
- [x] 6.5 **Precision counter re-keyed to `"requirements_analyst"`** —
      the item most likely to have been missed, and silent if it had been.
- [x] 6.6 `_AGENT_KEY_ALIASES`, `reset()`, `dump_histories()` (4-tuple) and
      `_surface_limit_to_user()` re-pointed.
- [x] 6.7 `agents/hub.py` topology-3 branch → `Planner3` (the Stage-1
      `NotImplementedError` removed); `llm_routing` `wired_into_dispatcher`
      → `True` for both merged agents.
- [x] 6.8 **VERIFIED.**  Topology 3 assembles for the first time in this
      rebuild: `built=5 unavailable=0`.  Topologies 7 and 5: **16 agents
      byte-identical, 0 moved.**  Eight suites pass; `pyflakes` still 20.

**What 6.5 actually prevents.**  `planner5.py` counts a refine round with
`if hop.target == "dc_output_inspector" and self.session.standing_directives`.
That key does not exist in topology 3.  Ported unchanged the guard never
matches, `precision_rounds` stays 0 for the whole session,
`MAX_SECTIONS_REFINE_ROUNDS` never fires, and the precision section-matching
loop runs to `MAX_DISPATCH_HOPS` with no cap, no error and no log line — a
happy-path run would look fine.  It is the same failure that hit standing
directives during the 5-agent build, where the test was keyed on `"planner"`
and the issuer was the Conductor.  Both halves now carry a comment saying why
the key is what it is.

**The `_AGENT_KEY_ALIASES` table keeps the merged-away names**, mapped onto
whichever agent absorbed them — `uii`/`dcoi` → `requirements_analyst`,
`dcic`/`tool caller` → `design_engineer`, `orchestrator` → `planner`.  A
prompt, a log line or a user carried over from topology 5 or 7 asking
`read_agent_history("DCIC")` gets an answer instead of "unknown agent", which
costs a burned step.

**`smoke_test_hub_attributes` gained a Planner3 row and both halves were
mutation-tested.**  Deleting the Requirements Analyst → Design Engineer edge
fails the edge check; adding a `self.tool_caller.reset()` call fails the
attribute check with `! self.tool_caller -> reset`, reproducing exactly the
defect that shipped in the retired Architect — it called three agents its
topology never built, and `pyflakes` and the narrow version of this check both
passed it.  File restored and hash-checked afterwards.

**The DH check upgraded itself.**  `smoke_test_dh_batching`'s F19d roster test
fell back to the DECLARED queue roster at Stage 3 while `planner3.py` did not
exist, printing a `PENDING` line.  Now that `hub_registry.built_here()` parses
the class's own `_agents_by_key` literal, the topology-3 case runs at full
strength with no code change: `['design_engineer', 'planner', 'receptionist',
'requirements_analyst']`.

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
| `planner` | 21 901 | `3b9ca3a8ea4f` | *(re-baselined, see below)* |
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
| `planner` | 25 415 | `c191528578b7` | *(re-baselined, see below)* |
| `receptionist` | 15 978 | `370c1cc62d5b` |
| `tool_caller` | 9 040 | `df6a4b436e92` |
| `user_input_inspector` | 14 400 | `0ecf3a4bf846` |

> **RE-BASELINED 2026-09-05, mid-Stage-6.**  The owner reworded the Planner's
> PRECISION INPUT-MATCH lead-in on `stage-a-web-deploy` (`4e15726`) so the
> standing-directive block reads as an EXAMPLE rather than a template, and
> applied it to the 7-agent and 5-agent Planners.  That commit was merged into
> this branch — merged rather than rebased, so the topology-3 commit SHAs
> already reported stay valid — and the same text imported into
> `agents/3agent/planner/prompt_3agents.md` by re-copying from the 5-agent
> source, which was byte-identical to it beforehand and therefore imports his
> edit exactly and nothing else.
>
> **The two `planner` rows above are the ONLY figures that changed.**  Proved,
> not assumed: the snapshot diff from the original baseline reports both
> Planners `MOVED +118 chars` with the expected four-line hunk, and every other
> topology-7 and topology-5 prompt `byte-identical`.  From here on, "0
> differences" means against THESE numbers.

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
| `smoke_test_database_handler` | **FAIL — environmental.**  Same missing module.  *(Added 2026-09-05: not run at Stage 0.)* |
| `smoke_test_base_chain_agent` | **FAIL — environmental.**  Same missing module.  *(Added 2026-09-05.)* |
| `smoke_test_all_chain_agents` | **FAIL — environmental.**  Same missing module.  *(Added 2026-09-05.)* |
| `smoke_test_prompt_toggles` | **FAIL — pre-existing, and NOT environmental.**  *(Added 2026-09-05: not run at Stage 0.)*  See below. |

> **Correction to this baseline.**  The Stage-0 sweep did not run every suite in
> `extra_utilities/`, so two failures surfaced later and had to be attributed
> after the fact rather than being on record from the start.  Both were proved
> pre-existing by re-running them in a throwaway worktree checked out at the
> commit BEFORE the stage that found them, with `agents/3agent/` absent —
> which is the only honest way to settle "was this mine?", and is cheaper than
> the argument.
>
> `smoke_test_prompt_toggles` is the interesting one: it fails on *"neither
> position adds a blank-line run"*, and the run it finds is a 4-newline
> sequence in the **topology-7** User Input Inspector prompt that is present in
> BOTH toggle positions.  So the check's label mis-attributes it — the residue
> exists independently of the toggle it is blaming, in the SHARED tree, in the
> live 7-agent system.  Out of scope for this rebuild; recorded because it is a
> real defect in production text and nothing else is tracking it.
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
