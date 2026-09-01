# Topology-5 rebuild — build plan and TODO

**Started 2026-08-31.  Branch `claude/topology-5-rebuild-7a0f07`, worktree
`modest-leakey-2099f8`.  Stages 0-4 are COMMITTED on that branch, which
branched from `stage-a-web-deploy` at `2a6d98f` and has not diverged from it.
Nothing is pushed anywhere yet; the eventual push target is
`stage-a-web-deploy`, on the owner's word.**

**What this replaces.**  The dormant 5-agent system (Receptionist, UII,
Conductor, Creator, Tool Caller, DCOI, DH) was built in 2026-08 against a
7-agent system that has since been heavily revised.  It is being rebuilt from
the CURRENT 7-agent system instead.

**The one rule above all others:** *no edit made for topology 5 may change
topology 7.*  Every claim of "unchanged" in this document must be backed by an
assembled-and-hashed before/after, not by reasoning.

Companion reading, in order: `extra_utilities/working_agreements.md`,
`extra_utilities/docs/active/topology_shared_touchpoints.md` (§A–§F),
`extra_utilities/docs/reference/design_agent_count_variants.md`.

---

## 1. Target definition

### 1.1 Agent set

Topology 5 = topology 7 **minus the Orchestrator, minus the DC Input
Inspector**.

| Agent key | Display | Role in topology 5 |
|---|---|---|
| `planner` | Planner | **HUB** — plans, dispatches, approves.  Absorbs the Orchestrator. |
| `user_input_inspector` | User Input Inspector | unchanged |
| `dc_input_creator` | DC Input Creator | unchanged; sole attempt creator |
| `tool_caller` | Tool Caller | unchanged |
| `dc_output_inspector` | DC Output Inspector | unchanged |
| `receptionist` | Receptionist | **EXTRA** — always present, not one of the "5" |
| `database_handler` | Database Handler | **EXTRA** — post-session only, never in `_agents_by_key` |

Retired entirely: `orchestrator` (not built under topology 5),
`dc_input_inspector` (not built under topology 5), `conductor` and `creator`
(deleted from the repo — see D10).

### 1.2 Edge list — CONFIRMED BY OWNER 2026-08-31

| FROM | TO | Notes |
|---|---|---|
| Receptionist | Planner | the only door; replaces `call_orchestrator` |
| Planner | Receptionist | replaces the Orchestrator's `call_receptionist` |
| Planner | User Input Inspector | |
| Planner | DC Input Creator | starts the design cycle |
| Planner | DC Output Inspector | **CONFIRMED 2026-08-31 (O3).** |
| User Input Inspector | Planner | FORWARD and ESCALATE collapse into ONE tool |
| DC Input Creator | Tool Caller | the only forward (the DCII-off branch in topology 7) |
| DC Input Creator | Planner | CLARIFY and ESCALATE collapse into ONE tool |
| Tool Caller | DC Output Inspector | |
| Tool Caller | DC Input Creator | `prev_agent = "DC Input Creator"` |
| DC Output Inspector | Tool Caller | re-render the same attempt |
| DC Output Inspector | DC Input Creator | **precision-job shape feedback** |
| DC Output Inspector | Planner | return / approve |

**The Planner has NO edge to the Tool Caller.**  **The Tool Caller has NO edge
to the Planner** — it is the one agent that cannot escalate.

**Collapse consequence.**  With the Planner as hub, "forward to the Planner"
and "escalate to the Planner" are the *same tool call* for the UII and the
DCIC.  Every routing fragment must say so explicitly.

### 1.3 What "no more proper escalation" means

Escalation is not a tool, a flag or a field — it is prompt semantics laid over
the ordinary `call_<hub>` tool.  Removing it is therefore a PROMPT change
(owner-supplied), not a code change.  **The edges must not be removed:**
`routing_tools.stuck_escalation` and the twelve error fall-throughs (D9) all
target the hub, and the code backstops (`MAX_DISPATCH_HOPS`,
`MAX_SECTIONS_REFINE_ROUNDS`, `_surface_limit_to_user`) stay regardless.

---

## 2. Decisions LOCKED by the owner (2026-08-31)

| # | Decision |
|---|---|
| **D1** | Topology 5 = topology 7 minus Orchestrator minus DCII (§1.1). |
| **D2** | The **Planner is the hub**.  `topology._HUB_BY_TOPOLOGY[5]` becomes `("planner", "Planner")`.  The hub keeps `AGENT_KEY = "planner"`, so **no new rows are needed in any of the 19 identity registries**. |
| **D3** | The hub class lives in a **new package `agents/planner5/`** (peer of `agents/orchestrator/`).  `agents/planner/planner.py` is never touched. |
| **D4** | The hub class **starts as a copy of the CURRENT `agents/orchestrator/orchestrator.py`**, with the Planner's `_persist_plan` / `_save_plan_to_file` grafted on so `current_plan.txt` keeps being written.  NOT a copy of `conductor.py` — that file was written against an older 7-agent system and would silently re-import stale behaviour (§C of the touchpoints doc). |
| **D5** | **Wipe `agents/5agent/` (37 files)**, then **FULL FORK**: copy every shared prompt file topology 5 can read into `agents/5agent/`, byte-identical, in the same commit.  From that moment the two topologies are fully separate trees -- an edit to one can never reach the other.  (Owner, 2026-08-31: *"the copy is made NOW ... FROM NOW ON, the 5-agent system will be separate, and any edit on one will not apply to the other and viceversa"*.)  This SUPERSEDES the earlier "fall through to the shared original" reading. |
| **D17** | The fork is **complete by construction, not by instrumentation**.  An instrumented read-set misses module-level constants (`prompts.py:551` render_check_library) and every fragment read at agent-CONSTRUCTION time (`routing_*` via `set_routing_tools`), so it is not a safe basis.  The rule instead: mirror every `.md`/`.txt` under `agents/shared/prompt_fragments/` and `DC_prompt_fragments/`, **except** READMEs, files scoped to a retired agent, and the `_planner_first` half of each PF pair; plus each surviving agent's `prompt.md`.  Scope matching uses the LONGEST agent key that fits -- `generic_constraints_dc_input_creator` ends with both `_dc_input_creator` (survivor) and `_creator` (retired). |
| **D6** | Under topology 5, `PLANNER_FIRST` is **ignored** (always the UII-first / branch-collapsed fragments) and `DC_INSPECTOR_ENABLED` is **forced False**.  Both stay VISIBLE in the workflow-settings UI showing their real value, but are **greyed out**; an attempt to change either snaps back to the forced value. |
| **D7** | The tool layer gains a topology dimension via **per-table overlay dicts** consulted first, mirroring `_topology_override`'s override-then-fallback.  Topology 7 takes the identical existing path by construction. |
| **D8** | `routing._sections_for()` is **opened to topology 5**, so its agents get the same REDUCED routing sections as topology 7.  Verified by assembling with the gate open and closed and diffing. |
| **D9** | All twelve `AgentHop("orchestrator", …)` fall-throughs in the six shared chain agents become `topology.hub_key()`.  Provably identical under topology 7. |
| **D10** | **Conductor and Creator are deleted entirely**, including their identity rows in every registry.  Because that shrinks `session.KNOWN_AGENT_KEYS` and `AgentState.__post_init__` raises on an unknown key, the deletion must ship **with** a guard/migration so archived sessions and R2 snapshots still load, and `smoke_test_llm_routing`'s equality assertion relaxed to a subset check. |
| **D11** | Step caps are **topology-specific and live in a topology-5-specific file**, not in the shared table.  New: `MAX_PLANNER_VISITS` (hub re-entry cap) and a hub inner-steps cap.  `MAX_PLANNER_STEPS = 40` stays shared and untouched. |
| **D18** | Topology-5 Python overrides split by whether the UI needs them: **UI-tunable numbers go in `workflow_settings/settings.py`**, non-tunable text/table overlays go in a new **`agents/topology5/`** package.  (Owner's O1 answer.)  Correction to an earlier note in this file: the step caps live in **section 28 "Step budgets"**, not section 27 — 27 is `SYSTEM_TOPOLOGY` itself.  `agents/step_caps.py`'s own docstring still says §27 and is stale. |
| **D12** | `llm_defaults` gains a **per-topology overlay** (`DEFAULT_PER_AGENT_MODELS_5AGENTS`) rather than editing the shared dict. |
| **D13** | `prompts._NON_CHAIN_AGENTS` is **NOT touched** — `"planner"` is not added.  The topology-5 Planner therefore keeps the `<<CHAIN_ONLY>>` regions and its prompt content stays IDENTICAL to topology 7's, which is what the owner asked for.  (Consequence, accepted knowingly: until the owner's prompt edits land, the topology-5 Planner is told "Route your content to the Orchestrator".)  Where there is any doubt about a shared fragment drifting, ship a **byte-identical pass-through** under `agents/5agent/`. |
| **D14** | Verification: `dump.py --topology`, a both-topology assemble+diff script, a rewritten `smoke_test_topology_fragments.py`, and a new **prompt-names-a-tool ⇄ class-binds-a-tool audit** run separately under `SYSTEM_TOPOLOGY` 7 and 5. |
| **D15** | **No prompt-content edits by Claude.**  The owner supplies the exact edits for every system prompt and tool description.  Claude may create *structural* files (pass-throughs, byte-identical copies, empty overrides) and must propose any content before writing it. |
| **D16** | End-of-session feedback distribution is **deferred to LAST, and is a MAYBE** — not needed for the owner's current tests. |

---

## 3. OPEN decisions — must be answered before the stage that needs them

| # | Question | Needed by |
|---|---|---|
| ~~O1~~ | **RESOLVED 2026-08-31 — see D18.** | — |
| ~~O2~~ | **RESOLVED — `agents/planner5/`, class `Planner5`.** | — |
| ~~O3~~ | **RESOLVED 2026-08-31 — YES, the Planner gets `call_dc_output_inspector`.**  Hub edges are therefore: Receptionist, UII, DCIC, DCOI — four, i.e. the Orchestrator's six minus the retired DCII and minus the Tool Caller. | — |
| ~~O4~~ | **RESOLVED 2026-08-31 — full fork, done in Stage 1.**  See D5 / D17. | — |
| **O5** | Author a `"5"` profile in `database_access.json` mirroring `"7"`?  Zero blast radius (the store is keyed by profile first) and moot while `RAG_ENABLED=False`, but cheap insurance: without it every topology-5 agent gets all three RAG tools the moment the flag flips. | Stage 7 |
| **O6** | `natural_pipeline()` / `_PIPELINE_BY_TOPOLOGY[5]`: does the flow string start at the Receptionist (as the old 5-agent string did) or at the hub (as the 7-agent string does)? | Stage 5 |
| **O7** | `web/app.js` `LR_BOXES_5` — the LLM-routing chart.  Boxes are easy; `LR_ARROWS_5` is hard-coded coordinate pairs that must be re-derived by hand.  Do this now or defer? | Stage 6 |
| ~~O8~~ | **RESOLVED — no.  Verified in 3.14.**  Was: does the DCOI→DCIC direct edge break **standing-directive re-stamping**?  The hub re-stamps on its OUTGOING hop; a DCOI→DCIC hop bypasses the hub.  Topology 7 already has non-hub hops (DCIC→DCII→TC), so the mechanism probably covers it — **verify, do not assume.** | Stage 3 |
| ~~O9~~ | **RESOLVED — yes.  Verified in 3.14.**  Was: does the precision-refine cap still fire?  `orchestrator.py:699-717` counts hops into the DCOI while a directive is active and, on hitting `MAX_SECTIONS_REFINE_ROUNDS`, clears the directive and appends a finalize note to the hand-off.  Confirm it still lands when the loop is DCOI→DCIC→TC→DCOI rather than passing through the hub. | Stage 3 |
| **O10** | `dc_params_list` wording for the hub: `_USE_BY_AGENT["planner"]` exists but is **dead code** (`planner.py:140` binds the module default).  Bind the scoped variant, keep the default, or write a topology-5 third entry? | Stage 7 / prompt phase |
| **O11** | `history_tool.py:27-29` hard-codes a static 8-agent roster in its description, and `feedback_tool.py:84-93` hard-codes the 7-agent allow-list.  Neither takes an agent-key or topology parameter.  Fix under D7's overlay, or leave? | Stage 7 |
| ~~O13~~ | **RESOLVED 2026-08-31 — pre-populate now, full separation.  Done in 2.2.** | — |
| ~~O14~~ | **RESOLVED — forked, done in 2.5b.**  Was: `READ_INPUTS_DOC_UII / _DCII / _DCOI / _PLANNER` (`user_inputs_tool.py:326-390`) are the one tool-layer surface still shared. They are NOT an agent-keyed table — each agent imports its own constant by name and passes `doc=` at the call site — so `overlay_value` cannot reach them. Forking them needs an agent-keyed table plus a resolver, and edits to the four call sites (`planner.py:134`, `dc_input_inspector.py:110`, `dc_output_inspector.py:208`, and the UII's default arg). Behaviour-identical, but it touches shared agent files. Now, or at Stage 7 with the tool-description edits? | Stage 2.2 / 7 |
| ~~O15~~ | **RESOLVED — fixed + mutation-tested in 2.5c.**  Was: **Pre-existing bug, unrelated to this rebuild but in the blast path.** `editor._do_write` reads `settings.py` with universal newlines and writes the temp file with `newline="
"` (`editor.py:402-409`), while `settings.py` on disk is CRLF. **The first save through the Workflow Settings UI rewrites the whole file to LF**, turning a one-toggle change into a whole-file diff. Fix it (one line: preserve the file's own line ending) or leave it? | any |
| ~~O16~~ | **RESOLVED — disabled control + explanatory note.  Done in 2.5.** | — | the topology-5 tables with byte-identical copies of every entry now — mirroring D5's full fork of the prompt tree, so the two topologies are fully separate at the tool layer too — or leave them EMPTY and add an entry only when it diverges (override-then-fallback per entry, so an untouched entry still tracks topology 7)?  The prompt-tree answer was "copy now"; the tool layer is code rather than data, so it is worth confirming separately. | Stage 2.2 |
| **O12** | Feedback envelope double-statement: topology 5 currently gets **both** `feedback_envelope.md` and the `## End-of-session feedback message` prompt section — the exact duplication `feedback_tool.py:48-52` warns against.  Resolve with the EOS work (D16). | Deferred |

---

## 4. Build stages — in this order

§C of the touchpoints doc: **wiring skeleton first, prompts second.**  The old
5-agent was built prompts-first and drifted silently.  Do not invert this.

### Stage 0 — Baseline capture  *(read-only)*  — **DONE 2026-08-31**

Harness: `extra_utilities/topology_prompt_snapshot.py` (new).
`save <dir> [--topology N]` assembles and SHA-256-hashes every agent that
builds under a topology; `diff <a> <b>` reports per-agent identical / moved /
appeared / disappeared with unified diffs.  One SUBPROCESS per topology,
because `prompts.py` captures `PLANNER_FIRST` and `DC_INSPECTOR_ENABLED` at
IMPORT while reading `SYSTEM_TOPOLOGY` fresh.  The agent list is DERIVED from
`AGENT_DISPLAY`, so it never needs editing as the rebuild proceeds.

- [x] 0.1 Script that assembles and SHA-256-hashes all 9 topology-7 prompts and
      all topology-5 prompts, writing a JSON baseline.  Uses the working
      recipe (verified 2026-08-31):
      `sys.modules["simplejson"]=None; sys.modules["chardet"]=None;`
      `import bootstrap; bootstrap.install()` from `extra_utilities/prompt_pdf`,
      then `S.SYSTEM_TOPOLOGY = 5`, then `prompts._build_template(agent)`.
- [x] 0.2 Record the topology-7 baseline.  **Verified 2026-08-31, `py -3.13`:**
      receptionist 16 036 · user_input_inspector 12 907 · planner 20 396 ·
      dc_input_creator 23 020 · dc_input_inspector 17 728 · tool_caller 8 255 ·
      dc_output_inspector 17 300 · orchestrator 16 434 · database_handler 22 780.
- [x] 0.3 Record the topology-5 baseline (matches the handoff exactly):
      receptionist 35 129 · user_input_inspector 38 550 · conductor 68 359 ·
      creator 58 597 · tool_caller 18 613 · dc_output_inspector 37 607 ·
      database_handler 24 748.
- [x] 0.4 `git status` clean check before each stage; every stage is separately
      reviewable and separately committable.

### Stage 1 — Wipe + full fork  (D5, D17)  — **DONE 2026-08-31**

- [x] 1.1 Deleted all 37 files under `agents/5agent/`.
- [x] 1.2 `topology._HUB_BY_TOPOLOGY[5]` -> `("planner", "Planner")` (D2), plus
      the two stale comments above it.
- [x] 1.3 Forked **100 files** into `agents/5agent/` (dc_config 28,
      dc_config/user_input_types 7, prompt_fragments 21, tools_config 33,
      tools_config/render_check_library 3, + 7 agent `prompt_5agents.md`).
      25 shared files deliberately NOT forked: 6 READMEs, 5 `_planner_first`
      PF halves, 14 scoped to the retired Orchestrator / DC Input Inspector.
- [x] 1.4 **VERIFIED — topology 7 unchanged.**  All nine templates hash
      identically to the Stage-0 baseline
      (`receptionist d7bd2399fa4d`, `orchestrator 355969cadbb2`,
      `planner 1ef0a64b32c3`, `user_input_inspector ac5d5bacc7f6`,
      `dc_input_creator 1779a462628d`, `dc_input_inspector 4acb048494f9`,
      `tool_caller 5b5fc9f0d21f`, `dc_output_inspector a98ed0cef6f0`,
      `database_handler fb7b6b2c33ed`).
- [x] 1.5 **VERIFIED — all seven topology-5 templates are byte-identical to
      their topology-7 twins.**  Before the wipe they were 1.7x-3.0x larger
      (e.g. receptionist 35 129 -> 16 036, user_input_inspector 38 550 ->
      12 907, dc_output_inspector 37 607 -> 17 300, tool_caller 18 613 ->
      8 255).
- [x] 1.6 **Blocker B1 confirmed by execution, then closed.**  With the hub
      set to `planner`, `_build_slots():953` raised
      `FileNotFoundError … routing_planner.md`.  Closed by
      `agents/5agent/prompt_fragments/routing_planner_5agents.md`, a
      byte-identical copy of `routing_planner_uii_first.md`.

**Identity is proven at the TEMPLATE level only.**  `{routing_instructions}`
is `.format()`ed in at agent-construction time and is NOT part of the
template.  Measured directly (`routing.routing_instructions` under each
topology, same arguments): topology 5's routing block is **~3 700 characters
LONGER per agent** — Planner 1 019 -> 4 704, UII 1 829 -> 5 864, DCIC
1 258 -> 4 921, Tool Caller 1 112 -> 4 796, DCOI 1 157 -> 4 891; **+18 800
characters across the five**.  Cause: `_sections_for` (`routing.py:266`)
returns the FULL historic section set for any topology that is not 7.  This
is exactly **D8**, and it must land for "identical" to be true.

#### Stage 1b — harness extended, then D8 applied  — **DONE 2026-08-31**

`topology_prompt_snapshot.py` now captures the FULL prompt, not just the
template: it fills the runtime `{slots}` the way `prompt_pdf/dump.py` does
(`_ROUTING_SHAPE` + `_runtime_slots`).  **Cross-validated: it reproduces
`dump.py`'s topology-7 output byte-for-byte for all nine agents.**

> ⚠ `_ROUTING_SHAPE`'s topology-5 rows are deliberately IDENTICAL to
> topology 7's, so any difference the harness reports is caused by
> topology-aware CODE, not by a routing shape nobody has approved yet.
> **They must be updated when the hub class lands (Stage 3 / O2 / O3)**, or
> the harness will describe a hub that does not exist.

D8 applied to `routing._sections_for`: `topology() != 7` became
`topo not in (7, 5)`, and the PF gate was narrowed to `topo == 7`.

- [x] **Topology 7: all nine FULL prompts byte-identical before and after.**
      Provably a no-op, as designed.
- [x] **Topology 5: all seven agents' FULL prompts are now byte-identical to
      their topology-7 twins.**  −18 762 characters removed across five
      agents (DCIC −3 670, DCOI −3 734, Planner −3 685, Tool Caller −3 688,
      UII −4 035; Receptionist and DH have no routing slot and never moved).
- [x] `pyflakes` clean on `routing.py`, `topology.py`,
      `topology_prompt_snapshot.py`.

**Why byte-identity is achievable at all despite `hub_display()` differing:**
the REDUCED section set emits only `fragment` + `mandatory_tail`, and the
three sections that interpolate the hub name (`header`, `loop`, `permission`)
are suppressed.  So no `hub_display()` value reaches the prompt.  The
consequence is the honest one: **the topology-5 prompts currently say
`call_orchestrator` literally**, because that is what the forked fragments
say.  That is the identical baseline, and it is what the owner's Stage-8
edits change.

**Known breakage, expected and tracked:**
`extra_utilities/smoke_test_topology_fragments.py` now dies with
`FileNotFoundError … routing_creator.md` — its `ROUTING_FRAGMENTS_BY_TOPOLOGY[5]`
still names the retired Creator.  That is Stage 6.3.

**Trap.** `routing_creator.md` and `routing_designer.md` have **no shared
original**; `creator.py:209` resolves only through `routing_creator_5agents.md`.
Deleting that override before deleting `creator.py` is a `FileNotFoundError`.
Sequence Stage 1 and Stage 4.1 together, or delete the creator override last.

### Stage 2 — Topology-5 override infrastructure (Python)  (D7, D11, D12, D18)

- [x] 2.1 **DONE** — D18.
- [x] 2.2 **DONE** — `topology.overlay_value(name, shared)` added
      (override-then-**replace**, not merge: a topology that ships an overlay
      owns the table outright).  New package `agents/topology5/` with
      `tool_text.py`, pre-populated per **O13** with byte-identical copies of
      `USE_BY_AGENT` / `USE_DEFAULT` (dc_params_tool) and
      `VIEW_IMAGES_PATHS_BY_AGENT` / `VIEW_IMAGES_PATHS_DEFAULT`
      (user_inputs_tool), minus the entries for retired agents.
      `dc_params_tool._use_clause` and
      `user_inputs_tool._view_images_paths_clause` now consult it.
- [x] 2.2b **DONE — a silently-inert fork, caught and closed.**  The 100-file
      fork copied `dc_params_primer_text.txt` and
      `dc_params_primer_text_user_input_inspector.txt` into
      `agents/5agent/dc_config/`, but `dc_primer.py` built those paths
      ABSOLUTE from `_DC_CONFIG_DIR` and never consulted `_topology_override`,
      so both copies were dead files.  This is the primer's known trap — it is
      injected at INVOKE time and bypasses every prompt-level filter.
      `_TEXT_PATH_BY_AGENT` (paths) became `_TEXT_NAME_BY_AGENT` (filenames)
      and `_text_path()` now resolves through `_topology_override`, with a
      lazy import to avoid the circular one.  **Verified:** topology 7 still
      reads `DC_prompt_fragments/dc_config/…`, topology 5 now reads
      `agents/5agent/dc_config/…_5agents.txt`, and the two files are
      byte-identical today.  The primer IMAGE stays shared deliberately — a
      binary asset, identical in both, and duplicating it doubles a ~1k-token
      payload for no editorial gain.
- [x] 2.3 **DONE** — `MAX_PLANNER5_STEPS = 40` and `MAX_PLANNER5_VISITS = 150`
      added to `settings.py` §28 and forwarded through `agents/step_caps.py`.
      Both are NEW names: `MAX_PLANNER_STEPS = 40` stays shared with topology
      7's chain Planner and was not touched.  Nothing reads them yet — the hub
      class is Stage 3.  `pyflakes` clean.
- [x] 2.4 **DONE** — `DEFAULT_PER_AGENT_MODELS_BY_TOPOLOGY` added to
      `llm_defaults.py`, consulted inside `model_for()` — the single funnel all
      five consumers already go through, so no caller changed.
      `SYSTEM_TOPOLOGY` is read off `workflow_settings.settings` directly
      (not via `agents.shared.topology`) to avoid inverting the package
      dependency direction, and FRESH per call.
      **Verified by resolution table:** topologies 7 and 3 unchanged for all
      12 agent keys; topology 5 differs in exactly one — `planner`
      `gpt-5-mini` → `gpt-5.4-mini`, the figure the retired Conductor used for
      the same merged hub role.  Change it with one line if you disagree.
- [x] 2.5 **DONE.**  There was no precedent — of 85 settings only
      `EMBEDDING_API_KEY` is read-only, and unconditionally — so the mechanic
      is new, in four places:
      `editor._INERT_UNDER_TOPOLOGY` + `_inert_reason()` (the rule, in ONE
      place); `read_schema` emits `disabled` + `disabled_note`, computed from
      the file's own `SYSTEM_TOPOLOGY` literal rather than the imported
      module, so it agrees with what a save would write; `_do_write` REFUSES a
      change to an inert setting (without this the grey-out is cosmetic —
      `SettingsIn.values` is an untyped dict, `web_app.py:505`);
      `app.js` paints the value then disables every control in the row and
      skips it in `collectChanges`; `style.css` gains `.setting-control.inert`,
      `.toggle button[disabled]` (which did NOT exist — a disabled toggle
      would otherwise still look live), `select[disabled]` and
      `.setting-inert-note`.
      **Mutation-tested, all four directions:** topology 7 → not disabled,
      write accepted; topology 5 → disabled with the value still shown, write
      REFUSED for both flags; an unrelated setting (`MESH_CHECKS`) untouched;
      and a combined `SYSTEM_TOPOLOGY=7 + PLANNER_FIRST` save still accepted,
      because the check uses the topology the write PRODUCES.  `settings.py`
      byte-identical afterwards.
      **Visually verified** by rendering the exact DOM against the real
      `style.css`: both inert toggles dim but still show their state (V lit
      green = True, X lit red = False), clearly distinct from a live toggle.
- [x] 2.5b **DONE — O14, the last shared tool-layer surface.**
      `READ_INPUTS_DOC_UII/_DCII/_DCOI/_PLANNER` were module constants chosen
      at each agent's call site, which no overlay could reach.
      `user_inputs_tool` gained `READ_INPUTS_DOC_BY_AGENT` +
      `read_inputs_doc(agent_key)` (the constants stay exported), and the four
      call sites now go through it —
      `planner.py:134`, `dc_output_inspector.py:208`,
      `dc_input_inspector.py:111`, `user_input_inspector.py:85` (whose
      module-level builder now takes the key as an argument).
      `agents/topology5/tool_text.py` carries the three surviving docs, copied
      by lifting their SOURCE SPANS with `ast` rather than by re-typing them.
      **Verified:** under topology 7 the resolver returns the original
      constant for all five keys tested; under topology 5 it returns identical
      text for every agent that topology builds, and the retired DCII falls
      back to the default.
- [x] 2.5c **DONE — O15, the pre-existing CRLF handling.**  `editor._do_write` now
      detects the file's own line ending instead of hard-coding `newline="
"`.
      **I triggered this bug on the real file while testing** (a patch anchor
      failed to match, so the fix was not applied and my verification save
      converted `settings.py` to LF); restored by re-applying CRLF — 77 566 +
      1 623 = 79 189 bytes, and `git diff --stat` confirmed only the 30
      intended insertions remained.  **Mutation-tested both ways:** a CRLF file
      survives a no-op save byte-identically, and an LF copy stays LF.
- [x] 2.6 **DONE** — `prompts._dcii_effective()` / `_planner_first_effective()`
      added; `apply_dcii_filter`, `apply_planner_first_filter` and
      `_pipeline_flow_fragment_name()` now call them.  Both return the
      IMPORT-time constant unchanged when `topology() == 7` and `False`
      otherwise, so topology 7 takes byte-for-byte the path it always took
      while the topology is re-read fresh on every call.

**Measured effect of 2.6** (full prompts, `topology_prompt_snapshot.py`):

- Topology 7 — all nine byte-identical.
- Topology 5 — DCII text removed from five agents: DC Input Creator
  −1 018, Database Handler −420, Planner −326, DC Output Inspector −69,
  Tool Caller −4.  Receptionist and UII did not move.

The Receptionist looked like a miss (its forked prompt carries a
`<<DCII_ONLY>>` region at line 232) but is correct: that region sits inside a
`<<HAS_DBA>>` block, which `RAG_ENABLED = False` strips first.  It will start
mattering the moment RAG is switched on.

**Residual DCII mentions in the assembled topology-5 prompts — exactly two,
both UNGATED, both content for Stage 8:**

1. `agents/5agent/planner/prompt_5agents.md:224` — *"…is the DC Input
   Creator's job and the DC Input Inspector checks it"*.  This is the
   pre-existing topology-7 defect recorded in §5.3; it is simply now visible
   in topology 5 as well.
2. `agents/5agent/database_handler/prompt_5agents.md` — a bare `DCII` inside
   the `UII/DCIC/DCII/DCOI/TC/Receptionist` abbreviation list.

Orchestrator mentions still standing in the assembled topology-5 prompts (all
Stage 8): Receptionist 12, Planner 21, UII 3, DCIC 12, Tool Caller 6, DCOI 8,
DH 7 — **69 in total**.

**Regression check after all Stage 1 + Stage 2 work:** all nine topology-7
templates are byte-identical to the ORIGINAL pre-work baseline.  Drift: 0.

### Stage 3 - The hub class  (D2, D3, D4)  - **DONE 2026-08-31**

`agents/planner5/planner5.py`, 1 147 lines, started as a byte-for-byte copy of
`agents/orchestrator/orchestrator.py` and was re-pointed in five scripted
passes.  `class Planner5(BaseChainAgent)`, `AGENT_KEY = "planner"`.

- [x] 3.1 Package + class: `agents/planner5/{__init__,planner5}.py`, plus a
      copy of `role4_feedback_instructions.md` (its path is
      `Path(__file__).parent`-relative, so the hub needs its own).
- [x] 3.2 `_agents_by_key` = 6 keys, `self.AGENT_KEY -> self`.  No
      `orchestrator`, no `dc_input_inspector`; neither a `Planner` nor a
      `DCInputInspector` is constructed and both imports are gone.
- [x] 3.3 `_wire_routing` rewritten for the owner's edge set, with NO branches
      - no `PLANNER_FIRST`, no `dc_inspector_enabled`.
- [x] 3.4 `dispatch()`: `start_agent_key` defaults to `""` and resolves to
      `self.AGENT_KEY`; both `current == "orchestrator"` tests and the
      escalation-log test compare against `self.AGENT_KEY`; the log strings use
      `AGENT_DISPLAY[self.AGENT_KEY]`.
- [x] 3.5 **Standing-directive capture keyed on `self.AGENT_KEY`.**  The silent
      trap: ported unchanged as `if current == "planner"` it would still have
      worked here - but only BY ACCIDENT, because the hub happens to be the
      planner.  Written explicitly so it cannot rot.
- [x] 3.6 `_DIRECTIVE_CARRIERS` = UII, DCIC, Tool Caller, DCOI.  `planner` is
      dropped: the hub is the directive's AUTHOR.
- [x] 3.7 `_persist_plan` / `_save_plan_to_file` grafted from `planner.py`,
      lifted by AST source span rather than re-typed, and called from the run
      loop at both of the chain Planner's call sites.  `current_plan.txt` keeps
      being written under topology 5.
- [x] 3.8 `_AGENT_KEY_ALIASES` trimmed (DCII rows gone; `"orchestrator"` and
      `"hub"` now RESOLVE TO `"planner"`, so a prompt or a user carried over
      from the 7-agent system still gets an answer).  `reset()`,
      `dump_histories()` (6-tuple), `run_feedback_round()` and
      `_surface_limit_to_user()` re-pointed; the last now reads
      `self.current_plan`, not `self.planner.current_plan`.
- [x] 3.9 **Module helpers MOVED, not forked.**  `_first_line`, `_truncate`,
      `_last_text_message`, `_format_message_content`, `_format_agent_history`
      now live in `agents/shared/hub_format.py`.  `orchestrator.py` re-exports
      them by explicit assignment, so `agents/architect/architect.py` (and the
      Conductor, until Stage 4 deletes it) keep importing them from the old
      path unchanged.
- [x] 3.10 `agents/hub.py` - the `topology() == 5` branch returns `Planner5`.
- [x] 3.11 `_HUB_BY_TOPOLOGY[5]` - done in Stage 1.
- [x] 3.12 **D9 applied: all twelve `AgentHop("orchestrator", ...)` sites**
      across the six chain agents now use `topology.hub_key()`, which returns
      `"orchestrator"` under topology 7.  Exactly 2 per file, asserted by the
      patch script rather than assumed.
- [x] 3.13 **The §E structural pre-flight, built and mutation-tested** -
      `extra_utilities/smoke_test_hub_attributes.py`.  Written the WIDE way: it
      enumerates EVERY `self.<attr>.<method>()` in a hub class and flags any
      attr the class never provides.  It also asserts each hub's WIRED EDGE SET
      against an expected list, extracted from the source with `ast` - so it
      tests what the code does, not what a comment claims.  Orchestrator 28
      edges, Planner5 13, both matching.  **Mutation-tested twice**:
      re-introducing `self.planner.reset()` makes it fail, and deleting the
      DCOI->DCIC edge makes it fail.  Neither half is vacuous.
- [x] 3.14 **O8 and O9 resolved by READING the dispatch loop, not assumed.**
      The directive re-stamp (`if hop.target in _DIRECTIVE_CARRIERS`) and the
      precision-round counter (`if hop.target == "dc_output_inspector"`) both
      live in the dispatcher and fire on EVERY hop, whoever made it - so the
      new DCOI->DCIC edge is re-stamped like any other and still counts towards
      `MAX_SECTIONS_REFINE_ROUNDS`.  No change needed.
- [x] 3.15 The two hard-coded incoming hand-off labels are now topology-gated.
      Topology 7 keeps its exact wording - changing it would alter text the live
      system shows those agents on every turn, which is not a topology-5 change
      to make.  Topology 5 uses "previous agent", the agnostic wording the UII
      and Tool Caller already use.

**Tool set - a deliberate starting point, to re-read at Stage 8.**  The hub
binds the PLANNER's utility tools (`read_user_inputs`, `read_extracted_inputs`,
`read_agent_history`, `read_attempts`, `dc_params_list`, plus `dba_tools_for`),
NOT the Orchestrator's smaller set.  It has to: it runs the Planner's PROMPT,
which documents the first two.  A prompt naming a tool the class does not bind
is the §F.4 defect that cost the first live 5-agent run two wasted hops, ~60k
tokens and its only tool error.  The owner has said tool sets are settled
alongside the prompt edits; this is where they start.

**Dropped: `_CHAIN_ACCESS_ON` / `_CHAIN_ACCESS_OFF`.**  The Planner's prompt has
no `chain_access_block` slot, so both constants had no consumer.  The
dispatch-time PREPEND is kept (it is gated on the `CHAIN_ACCESS` setting, not on
the prompt), so under topology 5 the hub receives the inter-agent block without
its prompt explaining it.  **Stage-8 item:** either add that section to the
topology-5 Planner prompt, or turn the setting off for this topology.

**Verified after Stage 3:** topology-7 templates 0 drift from the ORIGINAL
baseline; 0 full prompts moved in EITHER topology; `pyflakes` clean on every
file touched; `agents.planner5` imports under `SYSTEM_TOPOLOGY = 5` and exposes
all seven hub-contract methods; `build_hub` returns `Planner5`.

### Stage 4 - Retire Conductor + Creator  (D10)  - **DONE 2026-08-31**

- [x] 4.1 Deleted `agents/conductor/` (4 files) and `agents/creator/` (3), the
      `build_hub` branch (Stage 3), and the step budgets
      `MAX_CONDUCTOR_STEPS` / `MAX_CONDUCTOR_VISITS` / `MAX_CREATOR_STEPS`
      from both `settings.py` §28 (-1 730 chars) and `agents/step_caps.py`
      (-1 575 chars + the stray `MAX_CREATOR_STEPS` further down the file).
      Three topology-3 comments that CITED those constants were reworded so
      nothing dangles, and `step_caps.py`'s stale "section 27" reference was
      corrected to 28.
- [x] 4.2 Identity rows removed from all fourteen registries:
      `routing_tools.AGENT_DISPLAY` and `_TOOL_DESCRIPTIONS` (both
      `call_conductor` and `call_creator`), `base_chain_agent`
      `_PRUNE_DISPLAY_NAMES`, `db_writer.DEFAULT_AGENTS_TO_ACL`,
      `orchestrator._AGENT_KEY_ALIASES` (which declared each key TWICE -- both
      copies gone), `dc_primer.PRIMER_AGENT_KEYS`,
      `prompts._NON_CHAIN_AGENTS` + `PROMPT_MD_RUNTIME_SLOTS`,
      `sessions_queue.AGENTS_BY_TOPOLOGY[5]` (rewritten to the real roster:
      Receptionist, Planner (hub), UII, Input Creator, Tool Caller, Output
      Inspector, Context Pruner, Database Handler),
      `database_access.DEFAULT_AGENTS`, `dh_schedule.AGENT_KEYS` +
      `AGENT_SHORT_LABELS`, `ocr_access.DEFAULT_AGENTS`,
      `llm_defaults.DEFAULT_PER_AGENT_MODELS`, `llm_routing.AGENT_SPEC`, and
      `web/app.js` `LR_BOXES_5`.
- [x] 4.2b **`web/app.js` chart rebuilt, not just de-referenced.**  The
      topology-5 boxes are now the 7-agent layout minus the Orchestrator and
      the Input Inspector, with the Planner in the hub slot; `LR_ARROWS_5` was
      re-derived by hand (they are hard-coded coordinate pairs) and the result
      **rendered and inspected**, not assumed: 12 boxes, 10 arrows, including
      the Output Inspector -> Input Creator diagonal that is the precision
      loop, and the two Tool Caller -> tool diagonals the old 5-agent chart
      was missing entirely.  `node --check web/app.js` passes.
- [x] 4.3 **`AgentState` guard shipped** - `agents/shared/session.py` gains
      `RETIRED_AGENT_KEYS = {"conductor", "creator"}`, checked BEFORE
      `KNOWN_AGENT_KEYS`.  An archived snapshot naming a retired agent loads
      with a warning; the state is inert because nothing looks the key up in
      `_agents_by_key`.  Kept deliberately SEPARATE from `KNOWN_AGENT_KEYS`
      so a retired key can never become a routing target or a settings row.
      **Verified:** `conductor` and `creator` states load, `planner` loads,
      an unknown key is still rejected, and `KNOWN_AGENT_KEYS` is down to 11.
- [x] 4.4 **Turned out to be unnecessary - verified, not assumed.**  The
      concern was that removing the two keys would drop
      `sessions_queue.ALL_AGENT_KEYS` below `llm_routing.AGENT_SPEC` and break
      `smoke_test_llm_routing`'s equality assertion.  Both shrank together, so
      the assertion still holds: the suite reports **ALL CASES PASSED** with
      no change to it.
- [x] 4.5 The doubled `conductor`/`creator` rows in `_AGENT_KEY_ALIASES` -
      removed with the rest in 4.2.

**Content preserved rather than dropped** (working-agreement rule 1).  The
retired `call_conductor` description is the only return-to-hub tool wording
the repo had, and topology 5's `call_planner` will want something like it at
Stage 8, since the live `call_planner` text is a FORWARD description:

> Return control to the Conductor - the hub that plans, routes and approves.
> The ``message`` argument IS the hand-off text it will see - write it as
> free-form prose.  Use this when the natural pipeline has completed, to
> CLARIFY when its directive was ambiguous or could not be expressed in
> concrete parameter values, or to ESCALATE when you are stuck; the Conductor
> is the single point the chain returns to on any failure.

**Verified after Stage 4:**

- topology-7 templates: **0 drift** from the original pre-work baseline;
- topology 5: `conductor` and `creator` DISAPPEARED and **nothing else moved**
  in either topology;
- `pyflakes agents/ workflow_settings/ web_app.py`: only the pre-existing
  warnings in files this work never touched;
- `smoke_test_hub_attributes` (attributes + both edge sets): problems none;
- `smoke_test_queue_tiers`: ALL CHECKS PASSED;
- `smoke_test_llm_routing`: ALL CASES PASSED;
- `smoke_test_dc_primer`: 2 failures, **proven pre-existing** by re-running it
  against `git show HEAD:agents/shared/dc_primer.py` - identical failures;
- `smoke_test_topology_fragments`: **still broken**, now on
  `agents/conductor/prompt.md`.  This is Stage 6.3 and is the one guard left
  dead.

### Stage 5 — Minimum prompt overrides to make topology 5 assemble and dispatch

Structural only — **no content editorialising** (D15).

- [ ] 5.1 **HARD BLOCKER (verified by execution 2026-08-31):**
      `prompts._build_slots():953` reads `routing_{hub_key()}.md`.  With
      hub = `planner` this raises
      `FileNotFoundError … agents/shared/prompt_fragments/routing_planner.md`.
      Ship `agents/5agent/prompt_fragments/routing_planner_5agents.md`.  The
      same file satisfies BOTH the `$routing_hub` slot and the
      branch-collapsed `{routing_instructions}` fragment lookup.
      **Content must be proposed to the owner before writing.**
- [ ] 5.2 `routing_dc_input_creator_5agents.md` (collapsed name covers both PF
      branches).
- [ ] 5.3 Rewrites of `routing_{user_input_inspector,tool_caller,
      dc_output_inspector,receptionist}_5agents.md`.
- [ ] 5.4 `_PIPELINE_BY_TOPOLOGY[5]` (O6).
- [ ] 5.5 `_authorisation_sources`: gates on `topology() == 7`; the collapsed
      2-source branch reads correctly for a Planner-hub **by accident** —
      read the emitted sentence and confirm.
- [x] 5.6 D8 — **DONE in Stage 1b.**  `_ROUTING_SECTIONS_BY_AGENT` did NOT
      need a topology key: topology 5 reuses the same display names and now
      loads the same (forked, byte-identical) fragments, so sharing the table
      is correct rather than merely convenient.
- [ ] 5.7 Scoped-fragment pass-throughs (O4).

### Stage 6 - Verification harness  (D14)  - **DONE 2026-08-31**

- [x] 6.1 `dump.py --topology N` (default 7 -> `dump.json`, unchanged in every
      respect; 5 -> `dump5.json`).  `tools_for()` is WRAPPED rather than
      forked: the wrapper strips the routing tools the 7-agent wiring produced
      and re-adds topology 5's, keeping the utility half, which is genuinely
      shared because the classes are the same objects.  The two committed-
      default asserts now read the EFFECTIVE flags and only apply to topology
      7.  **This also fixed a break I had introduced in 2.5b and not caught:**
      changing `UII._build_read_user_inputs` to take an `agent_key` left
      `dump.py` raising `TypeError`.  It had been broken since; the
      cross-validation I reported at Stage 2 was true when run and stale
      afterwards.
- [x] 6.2 `topology_prompt_snapshot.py` - built in Stage 1b.
- [x] 6.3 `smoke_test_topology_fragments.py` rewritten for the new agent set.
      Rosters, routing-fragment lists, `HUB_BY_TOPOLOGY`, `UII_KICKOFF_AGENT`,
      `CHAIN_BY_TOPOLOGY` and the FACTORY sentinels all re-pointed.  Three
      deeper changes:
      * **"the other hub" stopped being a usable idea.**  It worked while the
        Conductor existed only in topology 5 and the Orchestrator only in 7.
        Now topology 5's hub is the PLANNER, which is a perfectly real agent
        in topology 7 - forbidding its name there would reject correct text.
        Replaced by `ABSENT_DISPLAYS`: no routing section may name an agent
        the ACTIVE topology does not build.  Narrower and actually true.
      * **`MIRROR`, a new and much stronger check.**  The old COVERAGE
        invariant ("every override is read") does not fit a complete mirror -
        the mirror deliberately contains flag-gated variants nothing reads
        under one setting.  For a mirrored topology the invariant is instead
        that NOTHING is read from the shared prompt trees at all.  **Topology
        5 reads 86 files, every one from `agents/5agent/`, zero shared.**
      * `HUB_MARKERS` -> `HUB_SLOT_TOPOLOGIES`.  A marker word only proves
        SOME file was read; the check now compares the assembled hub prompt
        against the text `routing_<hub>.md` actually resolves to.  Topology 5
        is not listed because its hub prompt carries `{routing_instructions}`
        rather than `$routing_hub`, and is covered by the HUB section.
- [x] 6.4 `smoke_test_prompt_tool_audit.py` - NEW.  Fails when an assembled
      prompt names a tool that NO agent in that topology binds.  Both sides
      derived, never transcribed: prompts from `topology_prompt_snapshot`,
      bound tools from `dump*.json` plus the routing edges read out of
      `planner5.py` with `ast`.
      The invariant is deliberately topology-wide rather than per-agent: a
      prompt may legitimately NAME a neighbour's tool (the hub's roster does,
      the DH's prompt describes the whole system), but naming one nothing
      binds cannot be explained that way - and that is the shape of all three
      drifts on record.
- [x] 6.5 **Every new check mutation-tested**, per the "a check that has never
      failed has not been shown to work" rule:
      * hub attributes - re-introducing `self.planner.reset()` fails it;
      * hub edges - deleting the DCOI->DCIC edge fails it;
      * MIRROR - deleting one mirrored file fails it, naming the shared file
        that stood in;
      * RETIRED - adding `list_input_files` to a topology-5 prompt fails it.
      Every mutated file restored and hash-checked afterwards.
- [x] 6.6 `pyflakes agents/ workflow_settings/ web_app.py extra_utilities/*.py`
      - every warning is in a file this work never touched.
- [x] 6.7 Other scripts naming the retired agents: `measure_prompts.py`,
      `build_html.py` and `provenance.py` turned out to match only on
      `dc_input_creator`.  `smoke_test_dc_primer.py` was fixed in Stage 4.
      `smoke_test_db_writer.py` fails on a missing Postgres URL, which is
      environmental.  `prompt_shrink_cuts.json`, `round2_annotations.json` and
      `baseline_tokens.json` are records of past analysis rounds and are
      deliberately left as they are.
- [x] 6.8 `web/app.js` - done in Stage 4.
- [x] 6.9 `SMOKE_TESTS.md` gains rows for the two new checks; the stale
      description of the rewritten suite and the stale side-effects note (it
      named a probe file the wipe removed) are corrected.
      `prompt_pdf/.gitignore` gains `dump5.json` / `dump3.json`.

**Two-way cross-validation, the strongest statement in the harness:** every
prompt in `dump.json` (9 agents) and `dump5.json` (7 agents) hashes identically
to the same agent's prompt from `topology_prompt_snapshot`.  Two independently
written assemblers agree byte-for-byte on both topologies.

**The suite, after Stage 6** - all green:
`smoke_test_topology_fragments` PASS (18 known-pending),
`smoke_test_hub_attributes` problems none,
`smoke_test_prompt_tool_audit` PASS (7 known-pending),
`smoke_test_queue_tiers`, `smoke_test_slot_splices`, `smoke_test_llm_routing`
all pass.  Topology-7 templates: 0 drift from the original baseline.

### The KNOWN-PENDING list IS the Stage-8 worklist

Everything below is a real finding, deliberately left standing because the
fix is a prompt edit the owner owns.  Nothing here is silently swallowed - the
suites print each one and stay green only because it is named.

1. **Topology 5 still routes to `call_orchestrator`** - 7 prompts.  The forked
   tree is byte-identical to topology 7's, so every routing fragment still
   names an agent topology 5 does not build.
2. **Topology 5's routing sections never name their own hub** - the Tool
   Caller's and the DCOI's say "the Orchestrator" where they should say "the
   Planner".
3. **Nobody states the UII's two required paths.**  In topology 7 the
   `Input directory:` / `Extraction output file:` lines are emitted by the
   ORCHESTRATOR alone; the Planner carries them only inside a `<<PF_ON>>`
   block, which is stripped whenever PLANNER_FIRST is False.  Topology 5 has
   no Orchestrator and its hub IS the Planner, so the lines are emitted
   nowhere - and `write_extraction` / `read_user_inputs` both take a REQUIRED
   `path` with no default.  This is item 1 of the fifteen responsibilities
   that lived only in the Orchestrator's prompt (§5.1), now confirmed to bite.
4. **The topology-5 hub keeps the `<<CHAIN_ONLY>>` rules**, so it is told
   "never address the user yourself - route your content to the Orchestrator".
   Deliberate: `_NON_CHAIN_AGENTS` has no topology dimension, so adding
   `planner` would strip that block from the 7-agent Planner too.  The fix is
   a topology-5 scoped copy of `generic_constraints_planner`.
5. **The hub receives the chain-access block its prompt never explains** -
   `_CHAIN_ACCESS_ON/OFF` were dropped with the Orchestrator's prompt, but the
   dispatch-time prepend is still gated on the `CHAIN_ACCESS` setting.

### Stage 7 — Tool-layer topology overlays  (D7)

Tool descriptions and bindings are discussed **together with the prompt edits**
(owner's instruction).  Tables needing an overlay when that happens:
`_VIEW_IMAGES_PATHS_BY_AGENT`, `READ_INPUTS_DOC_{UII,DCII,DCOI,PLANNER}`,
`_USE_BY_AGENT` (`dc_params_list`), `_TEXT_PATH_BY_AGENT` (DC-params primer),
plus O5, O10, O11.

`tools/` itself needs **zero** changes — confirmed by exhaustive grep.

### Stage 8 — Owner-supplied prompt edits

The owner provides the exact edits.  Each one lands as a file under
`agents/5agent/`, never as an edit to a shared file.

### Stage 9 — Live run

Static checks cannot see behaviour.  Both previous 5-agent live runs found
defects the full static suite could not (§F).

---

## 5. Content that MUST NOT be silently lost

Retiring the Orchestrator and the DCII deletes two prompts.  These inventories
exist so the owner can decide, item by item, where each responsibility lands —
**Claude will not re-home any of them unilaterally (D15).**

### 5.1 Lives ONLY in `agents/orchestrator/prompt.md`

Mechanism-critical (something else breaks if dropped):

1. The two mandatory UII path lines + "take the directory VERBATIM from your
   own `Input file directory:` line" + "the extraction file is a DESTINATION"
   (`:29-40`).  The Planner has the two-line block only inside `<<PF_ON>>` and
   lacks the derivation rule entirely.
2. When to re-run the UII (`:22-47`) — decided nowhere else.
3. The extraction-only stop rule (`:49-62`) — boundary exists nowhere else.
4. The complete `Current attempt <N>:` propagation matrix, including the
   **negative** rule that a new-generation `call_dc_input_creator` hand-off
   carries **no** attempt number (`:87-98`).
5. The precision-refine RELAY decision: DCOI gap → DCIC with no attempt number,
   vs finalizing → Planner as final approver (`:136-151`).
6. The `Attempts this cycle:` / `Show to user:` emission template
   (`:166-179`) — **the Receptionist's entire attempt-reporting procedure
   consumes this block and nobody else emits it.**

Also unique, less load-bearing: the Agent Capabilities roster (`:195-215`); the
three-level Escalation Hierarchy (`:216-226`); the self-exonerating-diagnosis
exception (`:228-233`); the anti-loop rules (`:181-186`, `:236-241`); "relay
context only — never frame the plan" (`:72-81`); "you ORIGINATE nothing"
(`:245-252`); the no-tool-call terminal semantics (`:264-269`); the two
"Planner not needed" exemptions (`:162-164`); relaying a new mid-session user
authorisation through the UII (`:126-134`).

Items 11 and 14 above become **self-referential** once the Planner is the hub
and should probably be dropped rather than reworded.

### 5.2 Lives ONLY in `agents/dc_input_inspector/prompt.md`

Already redundant elsewhere (safe to lose): range validation (the Tool Caller
does it independently), the VALUES-ONLY exception, the authorisation check.

Genuinely lost:

1. The precedence ORDER **system directive > extraction > DCIC discretion**
   (`:114-123`).  The DCIC's list (`:183`) is an unordered OR.
2. "The locked value is itself out of range → do NOT restore it, ESCALATE"
   (`:129-131`).
3. **Cross-checking `extracted_inputs.txt` against the RAW user inputs, text
   AND images** (`:12-16`, `:79-102`) — **the only audit of UII extraction
   fidelity anywhere in the system.**  The DCIC provably cannot do it (it binds
   no image tools by design); the DCOI compares the render, not the extraction.
4. Verification of the DCIC's three real-world-quantity routes, including the
   silent-default catch (`:133-154`).
5. The engineering-appropriateness critique with its ADVISORY ceiling
   (`:156-167`).
6. The physical-impossibility / self-intersection gate **before** generation
   (`:72-77`).  Moves from before the render to after it, or is lost.
7. Mandatory double-read + "the extraction is OVERWRITTEN in place, so a copy
   read earlier can be silently stale" (`:29-44`).
8. `read_user_inputs` as a second-opinion tool (`:95`).
9. The verdict-scoping anti-overreach clause (`:182-186`).
10. The obedience-to-instruction APPROVE branch (`:189-192`).
11. The "who asked for this change and were they allowed to" output line
    (`:169-180`).
12. The DCOI's override authority is framed *relative to the DCII*
    (`dc_output_inspector/prompt.md:136-140`).  Already `<<DCII_ONLY>>`-gated,
    so it degrades cleanly — but becomes an override of nothing.

### 5.3 A broken reference already present in a surviving prompt

`agents/planner/prompt.md:224` — *"Deriving parameter values … is the DC Input
Creator's job **and the DC Input Inspector checks it**"* — is **not** wrapped
in `<<DCII_ONLY>>`.  Every other DCII reference in the six survivors is gated.
This is a topology-7 defect today and a topology-5 defect tomorrow.

---

## 6. Verification protocol — applies to EVERY change from here on

1. Assemble both topologies BEFORE the change; hash every agent.
2. Make the change.
3. Assemble both topologies AFTER; hash every agent.
4. State explicitly **which agents moved and which are byte-identical**, and
   show the diff for every one that moved.
5. Never claim a check passed without showing its output.

Environment: **`py -3.13`** (the default 3.8 cannot parse `prompts.py`'s
PEP-604 hints).  `trimesh` is not installed, so `import agents` fails —
use the `bootstrap.install()` recipe from `extra_utilities/prompt_pdf`.

---

## 6a. Stage 2 close-out — what was verified

- **Topology 7 templates: 0 drift from the original pre-work baseline**,
  re-checked after every sub-step.
- **Topology 5 and 7 full prompts: 0 movement from 2.2 / 2.4 / 2.5** — as
  expected, those are tool-layer, model-layer and UI changes, not prompt
  ones.  The only prompt movement in Stage 2 was 2.6's DCII strip.
- `pyflakes agents/ web_app.py workflow_settings/` reports 8 warnings, all
  in files this work did not touch (`database_handler.py`,
  `db_writer_mm.py`, `orchestrator.py`'s unused `timezone`, `web_app.py`)
  — confirmed by `git diff --quiet` per file.  Pre-existing.
- `settings.py` still CRLF, 79 189 bytes, 1 623 line endings; its diff is
  the 30 intended insertions and nothing else.
- 16 files changed, +378 / -31.

---

## 6b. Facts established while doing Stage 0-1 (2026-08-31)

- **The eager `*_TEMPLATE` block is live, not theoretical.**  Importing
  `agents.shared.prompts` builds ALL NINE templates immediately
  (`prompts.py:1077+`), under whatever `SYSTEM_TOPOLOGY` is set at import.
  Proof: instrumenting `Path.read_text` BEFORE the import recorded 105 files;
  instrumenting AFTER it recorded 87.  The 18-file difference is the eager
  block plus the module-level constants.  This is touchpoints-doc `O9` /
  TODO `F90`, and it is the reason the snapshot harness uses one subprocess
  per topology.
- **Topology 3 was ALREADY broken before this work started.**  Assembling it
  raises `FileNotFoundError … agents/shared/prompt_fragments/routing_architect.md`.
  Recorded in the Stage-0 baseline, so it cannot later be blamed on the
  topology-5 rebuild.  The Architect needs the same `$routing_hub` fix
  the Planner just got (a `routing_architect*.md` must exist).
- **`agents/orchestrator/prompt.md` still assembles under topology 5** and now
  measures 15 884 chars instead of 16 434, because `$routing_hub` resolves to
  the forked `routing_planner_5agents.md`.  Harmless — the Orchestrator is
  never constructed under topology 5 — but it is noise in any snapshot, and
  the same is true of `dc_input_inspector`.  Consider filtering retired agents
  out of the topology-5 snapshot once Stage 3/4 land.
- **`conductor` and `creator` still assemble** (60 915 / 54 915 chars, down
  from 68 359 / 58 597 because they now read the forked fragments).  Stage 4
  deletes them.
- **A scoped-suffix filter must match the LONGEST agent key.**
  `generic_constraints_dc_input_creator` ends with `_creator`, so a naive
  retired-key check silently dropped nine surviving DC Input Creator
  fragments from the fork.  Caught by reading the skip list, not by any test.

---
---

## 6c. Line endings — a correction, and a bug I hit twice

**Correction to what §2.5c originally claimed.**  I described `editor._do_write`'s
hard-coded `newline="\n"` as turning "a one-toggle change into a whole-file
diff".  That overstated it.  This clone has **`core.autocrlf = true`**, and
`workflow_settings/settings.py` is stored in git as **LF** (0 CRLF in the blob)
while being checked out as CRLF.  Git therefore normalises the working tree on
every diff, so a CRLF-vs-LF working file produces NO diff at all.  The fix
(preserve whatever line ending the file already has) is still the right
behaviour — it stops the editor silently rewriting a file's physical form — but
the harm it prevents is smaller than first stated.

**The bug that actually did produce a whole-file diff, twice, was mine.**
Building a replacement string as `"a" + nl + "b"` and THEN calling
`.replace("\n", nl)` on it rewrites the `\n` inside the `\r\n` that is
already there, producing `\r\r\n`.  One such sequence anywhere in a file is
enough to make git stop normalising it, and the diff explodes to every line
(1 583 lines, in the case that caught this).

Rules for any script that edits a CRLF file in this repo:

1. Read and write with `newline=""` so nothing is translated.
2. Write literal `\n` in the patch strings and convert ONCE, at the boundary:
   `old.replace("\n", nl)`.  Never pre-splice `nl` into a string that will be
   converted again.
3. After a scripted edit, `git diff --stat` the file.  A line count far larger
   than the edit means a line-ending problem, not a content one.
4. `d.count(b"\r\r\n")` is the direct test.

## 7. Traps carried forward

- **A scoped fragment added to the SHARED tree leaks into topology 5**, because
  `scoped_fragment_path` keys on `agent_dir_name`, which both topologies share
  for `receptionist`, `user_input_inspector`, `tool_caller`,
  `dc_output_inspector` — and now `planner` and `dc_input_creator` too.  Asking
  "is it scoped?" is the wrong question; **assemble both topologies and diff.**
- **A scoped file whose slot is not registered in `SCOPED_FRAGMENTS` is
  silently inert** — no error, no log line.  15 slots are registered today.
- **Never use `DC_INSPECTOR_ENABLED` as the topology-5 lever.**  It is global:
  turning it off to clean topology 5 strips the DCII from topology 7's prompts
  while `orchestrator.py:389-397` still wires the agent.
- **The standing-directive re-stamp is invisible in logs.**  `[AGENT MSG]` is
  written by the routing tool *before* the dispatcher re-stamps, so a log
  showing the block once does not mean it was lost.
- **Prompt fragments are CRLF.**  Read/write with `newline=""` or you produce a
  whole-file diff.
- **`_load_routing_fragment`'s shared fallback always uses the ORIGINAL branched
  name.**  A missing collapsed override silently falls through to the shared,
  Orchestrator-naming file — no error.
- **`agents/loader.py:784-788` logs the 7-agent roster literally under every
  topology.**  Cosmetic, but it will lie in every topology-5 log.
- `O9` in the touchpoints doc (the nine eager `*_TEMPLATE` builds at
  `prompts.py:1077+`) is still open and is an active hazard here: they build at
  IMPORT time under whatever topology is on disk.
