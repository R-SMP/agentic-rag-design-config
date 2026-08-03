# Agent-count variants — 5-agent & 3-agent build tracker

Working file for the multi-stage task of building the reduced-agent system
prompts (5-agent and 3-agent) by **merging + tailoring** the current
7-agent prompts and their shared fragments. Companion to the design
rationale in `design_agent_count_variants.md`. **Focus: the 5-agent
system first.** Keep this file updated as stages complete.

---

## Golden rules for this whole task (from the user — always valid)
1. **Faithful-merge rule.** The merged/tailored prompt must contain
   EVERY instruction, detail, and nuance from the source(s). The ONLY
   permitted changes: (a) agent names / topology references re-pointed;
   (b) the specific agreed conflicts removed or tailored; (c) a concept
   that appears in BOTH sources collapsed to one copy. Otherwise keep the
   original wording, structure, and logic. When in doubt, preserve
   verbatim.
2. **Propose-then-apply, per change.** Show the exact change; the user has
   final say on EACH change; ask (via the multiple-choice tool) on any
   fork or slight uncertainty; apply nothing without showing it first.
3. **No Claude coauthor / attribution** in commits or PRs.
4. **PowerShell/bash blocks touching the repo start with `cd "<worktree>"`.**
5. **Step by step.** Do not run ahead on design / architecture decisions.
6. **Every fragment gets a per-system copy** tailored to that structure.
   The **Receptionist is an EXTRA agent** — always present, not one of the
   "5" or the "3".

---

## Settled decisions
- **5-agent roster** (+ Receptionist): **Conductor** (Planner+Orchestrator),
  **User Input Inspector (UII)**, **Creator** (DCIC+DCII), **Tool Caller**,
  **DC Output Inspector (DCOI)**. The three survivors keep their names.
- **3-agent brain name: `Architect`** (perceive+plan+route+approve).
  [3-agent build is LATER.]
- **Conductor structure:** restructured around "you are the hub"
  (plan / route / approve).
- **Topology toggles resolved to clean prose** — Creator self-validates
  (no DCII hop). The `<<PF_ON/OFF>>` and `<<DCII_ONLY>>` markers are NOT
  kept in the 5-agent prose. Feature toggles ARE kept: `<<BSV_ON/OFF>>`
  (blade-sections visualizer), `<<HAS_DBA>>` (database search).
- **5-agent flow = UII-FIRST (PF_OFF).** [2026-07-26 revision of the
  earlier "Conductor-first" reading.] New user input:
  Receptionist → **UII** (always first) → **Conductor** (direct) →
  Creator → Tool Caller → DCOI → Conductor → Receptionist → user. The UII
  may ask the user a clarification **directly via the Receptionist**
  (a 2nd user-facing gateway, alongside the Conductor). The Conductor is
  entered AFTER the UII with the extraction ready (like the Planner); it
  does NOT call the UII on a fresh request, but may CLARIFY back to it for
  a defective extraction. **CONSEQUENCE — DONE (Conductor early sections
  revised to PF_OFF, 2026-07-26):** *The pipeline you run* rewritten
  (entered AFTER the UII; design-vs-direct decision is post-extraction);
  *Route through the UII on new content* REMOVED (now the Receptionist's
  job — residue folded into the pipeline section); FORWARD dropped its "to
  the UII" sub-forward (→ the CLARIFY move now carries the two UII path
  lines); Role 1 preamble → PF_OFF. Also **removed `{chain_access_block}`**
  (no chain-access for the Conductor — it uses `read_agent_history` on
  demand; the Planner's model). **Targeted re-check DONE** — early sections
  verified faithful to the Planner's `<<PF_OFF>>` branches; caught + fixed
  2 PF_ON remnants in the chunk-4D utility-tool tails (`read_agent_history`
  "only call the UII to run the workflow" → "run a generation via the
  Creator"; `read_user_queries` "forwarding to the UII" → "when you CLARIFY
  back to the UII"); chain-access cleanly removed. ⚠️ The "meaningful vs
  not-meaningful
  content → UII rewrite" judgment now belongs to the **Receptionist**
  prompt (stage 4) — capture it there so it isn't lost.
- **Draft location:** `extra_utilities/draft_prompt_conductor.md`
  (a template carrying the same `$fragment` / `{slot}` placeholders as the
  live prompts; promoted to `agents/conductor/prompt.md` when the topology
  is built).
- **Tool naming:** the Creator's routing tool = `call_creator`
  (assumption; confirm at the routing-fragment stage). Survivors keep
  their tool names (`call_user_input_inspector`, `call_tool_caller`,
  `call_dc_output_inspector`, `call_receptionist`).
- **`new_attempt` is NOT given to the Conductor.** Verified in code:
  Planner never bound it; DCIC (`dc_input_creator.py:148`) owns creation;
  Orchestrator (`orchestrator.py:447`) held it only as a fallback. Dropping
  it from the Conductor resolves the Planner-("must NOT open a folder
  yourself")-vs-Orchestrator-("you hold the fallback") conflict, keeps the
  Creator as sole creator (design principle, commit `cf4b900`), and lowers
  the Conductor's authority concentration. A Creator-creation failure is
  handled via the Conductor's Role-2 recovery path.

---

## The fragment machinery (how prompts assemble)
- `agents/shared/prompts.py` assembles each agent's
  `agents/<agent>/prompt.md`: `$slot` DC/tool fragments substituted at
  build time (`_build_slots` / `_build_template`), `{slot}` runtime values
  filled at wiring time (`set_routing_tools`, etc.).
- Fragment sources: `DC_prompt_fragments/{dc_config,tools_config}/` and
  `agents/shared/prompt_fragments/`. Routing lives in
  `agents/shared/routing.py` (`NATURAL_PIPELINE`, `routing_instructions()`).
- **Precedent to extend:** `$pipeline_flow` already selects between
  `pipeline_flow_planner_first.md` / `pipeline_flow_uii_first.md` by the
  `PLANNER_FIRST` flag (`prompts.py:403-407`). "Select a fragment body by
  topology" is therefore an established pattern the 5-/3-agent selection
  can reuse.
- Conditional-region filters in `prompts.py`: `apply_dcii_filter`
  (`<<DCII_ONLY/OFF>>`), `apply_planner_first_filter` (`<<PF_ON/OFF>>`),
  `apply_bsv_filter`, `apply_dba_filter`, `apply_chain_only_filter`
  (`<<CHAIN_ONLY>>`; stripped for user-facing agents = Receptionist +
  Orchestrator).

---

## Fragments needing a 5-agent-tailored copy (they reference agents / counts / names)
- `agents/shared/prompt_fragments/pipeline_flow_*.md` → 5-agent flow.
- `agents/shared/prompt_fragments/available_agents.md` → 5-agent roster.
- `DC_prompt_fragments/tools_config/agent_tools_overview.md` (+ `_brief`,
  used by the Database Handler) → per-agent tool listing, 5-agent.
- `DC_prompt_fragments/tools_config/tool_caller_capabilities.md` →
  mentions the DCII; audit + retarget.
- `agents/shared/prompt_fragments/routing_orchestrator.md` /
  `routing_receptionist.md` → Conductor / Receptionist routing rosters.
- `agents/shared/routing.py`: `NATURAL_PIPELINE` + `routing_instructions()`
  → the 5-agent routing-tool set (Conductor calls UII, Creator, Tool
  Caller, DCOI, Receptionist; Creator has no DCII hop).
- **Audit for DCII / agent references:** `eos_feedback_intro/outro`,
  `capabilities_can/cannot`, `hard_constraints_generic/dc/tools`.
- **Agent-agnostic — SHARE as-is:** `parameter_list`, `parameter_count`,
  `structure`, `modelling_notes`, `qualitative_examples`,
  `invalid_parameter_examples`, `geometry_modification_rule`,
  `domain_description`, `sketch_*`, `tool_inventory`, and the
  database/retrieve/BSV tool fragments (they don't name agent counts).

---

## Build order (5-agent)
1. **Conductor prose** (merge Planner + Orchestrator) — ✅ DONE (uii-first;
   full audit + targeted re-check both clean). Draft:
   `extra_utilities/draft_prompt_conductor.md`.
2. **5-agent fragment bodies** — IN PROGRESS. Done: `pipeline_flow` ✅,
   `available_agents` merged roster ✅, **`routing_conductor` ✅** (all in
   `extra_utilities/draft_5agent_fragments/`). Routing insight: the
   Conductor is the HUB → it uses a **static `$routing_conductor` fragment
   like the Orchestrator, NOT the chain `routing_instructions()` builder**;
   the prompt's `## Your tools` slot changed `{routing_instructions}` →
   `$routing_conductor`. That fragment confirms tool name **`call_creator`**,
   drops `call_planner` / `call_dc_input_inspector` / the `new_attempt`
   fallback, and re-points the UII tool to **CLARIFY-only** (uii-first).
   Fragment **audit DONE + 3 re-points DONE**: `capabilities_can/cannot` +
   `eos_feedback_outro` are topology-agnostic (SHARE as-is);
   `hard_constraints_dc` (DCIC→Creator), `hard_constraints_tools`
   (DCIC→Creator + drop the Orchestrator `new_attempt` fallback), and
   `eos_feedback_intro` (Orchestrator→Conductor) copied to
   `draft_5agent_fragments/`. `generic_constraints` DEFERRED to stage 4
   (chain-agent-centric + the `<<CHAIN_ONLY>>` filter). **Stage 2 done bar
   generic_constraints (a stage-4 concern).** **DEFERRED to stage 4 /
   topology-selector** (they belong to the SURVIVOR prompts, not the
   Conductor): the 5-agent `NATURAL_PIPELINE`, the `routing_instructions()`
   boilerplate re-pointed Orchestrator→Conductor, and the survivor
   `routing_<agent>.md` + `routing_receptionist.md`.

   **Soft targets VALIDATED LIVE (2026-07-27)** — two 7-agent OpenAI runs
   proved both halves of the contract (ID228 gpt-5.4 keep-close-if-free;
   ID229 gpt-5.5 vary-to-serve-goal + honest plateau). NO prompt tuning
   needed. Only external issue: precision runs exceed the Sessions-Queue
   3600 s per-run cap (raise runtime; F52). The 5-agent Creator / UII / DCOI
   (stages 3–4) must inherit the soft-target handling from the live 7-agent
   prompts + `design_soft_targets.md`. See [[v9_soft_targets]].
3. **Creator prompt** (merge DCIC + DCII) — ✅ **DONE** (C1–C4 in
   `extra_utilities/draft_prompt_creator.md`; 29-agent completeness audit =
   0 losses; 6 coherence contradictions found + fixed). Committed `1e1ecb9`.
4. **Survivor 5-agent prompts** (UII, Tool Caller, DCOI, Receptionist),
   cross-references re-pointed — **NEXT**. Plus the items deferred here from
   stage 2: the 5-agent `generic_constraints` (chain-agent-centric + the
   `<<CHAIN_ONLY>>` filter), `NATURAL_PIPELINE`, the `routing_instructions()`
   boilerplate re-pointed Orchestrator→Conductor, and the survivor
   `routing_<agent>.md` + `routing_receptionist.md`.
   Known re-points: DCIC/DCII→**Creator**, Planner/Orchestrator→**Conductor**.
   Known NEW content: the Receptionist gains the "does this message carry
   meaningful content for the UII" judgment, since in the 5-agent flow it
   calls the UII directly (Receptionist → UII → Conductor → …).
Then: 3-agent variant (all of the above, tailored to 3 agents).
Separately, after discussion: the topology selector.

---

## Conductor build — status

**DONE (in `draft_prompt_conductor.md`):**
- **Chunk 1:** identity (hub: plan/route/approve); "The situations you are
  called in" (defines Role 1/2/3 names + "other agents reference these
  names"); Output mechanics; The pipeline you run (incl. the "many turns
  need no pipeline → REPLY DIRECTLY" case); Route through the UII.
- **Chunk 2:** "Your common moves" — FORWARD (call-UII + call-Creator),
  Issue a STANDING DIRECTIVE (+ PRECISION SECTION-MATCH template), Relay a
  precision refine round, CLARIFY, Recovery PLAN, APPROVE (+ fidelity/
  ceiling residual), REPLY DIRECTLY, ESCALATE; then Role 1, Role 2
  (escalation target — any chain agent escalates to the Conductor), Role 3
  (+ CONTINUE-to-3D-precision-check).

**DRAFT COMPLETE — chunks 1–4 all written to `draft_prompt_conductor.md`.**
- Chunk 3 (hand-off mechanics) — DONE (3A calling/attempt/directive; 3B
  preserve-directives / letting-agents-decide / name-attempt-folders;
  3C do-not-seed / delivery / verify-diagnosis / escalation-hierarchy /
  observable-facts / mis-attribute).
- Chunk 4 (roster + tail) — DONE (4A merged roster; 4B HARD RULES 1–10;
  4C Anti-Hallucination A–G + params + eos + hard constraints, geometry
  FOLDED into HARD RULE 4; 4D reference / utility tools / attempt tools /
  database / BSV / routing / chain-access).
- **Completeness audit DONE — CLEAN (0 gaps).** Workflow
  `conductor-completeness-audit` (run `wf_84615e3f-bc2`): 4 slice-auditors
  each read the full draft + their original slice and reasoned
  instruction-by-instruction; all returned zero missing/weakened items
  (adjudicator not needed — no candidates). Spot-checked one transcript
  (235 KB, ~80k tokens): genuine instruction-level coverage reasoning with
  self-second-guessing, not a lazy empty. **Conductor draft = complete +
  faithful.** NEXT (on the user's go-ahead): build-order stage 2 = the
  5-agent fragment BODIES (`pipeline_flow`, the merged `available_agents`
  roster per the spec above, `agent_tools_overview` folded in, routing).

The disposition table + chunk-4 plan below remain as the build record.

### Chunk 3 — disposition table (CONFIRMED)
| Orchestrator section | Disposition | Notes |
|---|---|---|
| When calling an agent | Keep, tailor | Drop "never frame the plan" + "you never originate strategy" (conflicts). Keep "no invented numbers / no out-of-tool capabilities" + "another agent's suggestions are evidence". |
| Attempt folders & `Current attempt:` propagation | Keep, re-point | DCIC→Creator; DCII hop removed. **`new_attempt` fallback line DROPPED** — Conductor directs, never creates. |
| Hand-offs you originate MUST carry `Current attempt:` | Keep, re-point | DCII hop removed. |
| Preserving user directives in hand-offs (HARD) | Keep verbatim | — |
| Letting agents decide when to use their own tools | Keep, tailor | UII case kept; DCII-authority case → "Creator self-validates authority"; authorisation-relay kept ("no need to manufacture a *separate* directive on a direct user authorisation"). |
| Name the attempt folder(s) & which to show (HARD) | Keep, re-point | Full format for the APPROVE hand-off. "Show-to-user pick comes from the Planner" → "the pick is yours"; drop the "after the Planner-approval step" para. |
| Do NOT seed follow-ups the system cannot deliver | Keep verbatim | `$capabilities_can/cannot`. |
| Verify the diagnosis BEFORE you relay it (HARD) | Keep, re-cast | "verify before **acting**" (not "before relaying upstream"). All substance preserved. |
| User questions about observable facts | Keep, re-cast | "route to the Planner" → "answer it yourself via `read_agent_history`… never from memory". |
| Escalation Hierarchy (CRITICAL) + Rules | Keep, re-cast | Three authorities → **two** (You decide recovery AND execute; the User is final). Rules re-pointed. |
| You ORIGINATE nothing — RELAY and SHAPE | Split | Remove "originate nothing" (done in identity). Keep "you DO shape communication — choose what each agent sees, summarise upstream, name authorship when relaying a directive" (fold into "When calling an agent"). |
| ❌ Completing a cycle — the Planner is the FINAL APPROVER | Remove (mostly) | Obsolete relay protocol. **Preserve only** the tail: "call `call_receptionist` with the brief summary; it composes the wording — don't write the final message yourself; the dispatcher delivers it." |
| ❌ When the Planner returns a direct answer | Remove | Obsolete; behaviour is in REPLY DIRECTLY. |
| ❌ Recognise Planner actionable instructions | Remove | Obsolete — no Planner→Orchestrator relay. |
| ❌ Do NOT re-ask the Planner | Remove | Obsolete. ("Don't loop with no new evidence" lives in Planner HARD RULE 9, chunk 4.) |
| Never attribute a Planner directive to the user | Keep, tailor | → "Never attribute **your own** directives to the user; only sentences the user literally said are attributable to them." |
| Geometry Modification Rule (HARD) | → chunk 4 | `$geometry_modification_rule`; sits with the HARD constraints + params. |

### Chunk 4 — plan (roster + tail; mostly Planner tail + shared fragments)
- **Available Agents / roster** — DECIDED: **ONE merged roster** (not two
  sections). The Conductor uses a single `$available_agents` section whose
  stage-2 body merges roles (`$available_agents`) + capabilities (inline
  "Agent Capabilities" + `$tool_caller_capabilities`) + tools
  (`$agent_tools_overview`) into ONE entry per surviving agent. Drop the
  separate `$agent_tools_overview` section from the Conductor. **Stage-2
  roster body must:** list only UII, Creator, Tool Caller, DCOI,
  Receptionist (no Planner/Orchestrator self-entries — the Conductor's own
  tools live in the tail sections: Routing tools, Utility tools, Attempt
  tools); re-point **Receptionist = directly callable** (was "never call
  directly — route to the Orchestrator"); **DCIC→Creator absorbing the
  DCII** (validates its own parameters — range/consistency/intent/authority);
  **DCOI returns to the Conductor** (was "FORWARD to Orchestrator");
  **`new_attempt` on the Creator only** (Conductor has none). Keep the "DO
  NOT exceed these capabilities" boundary rule as the section framing.
- **HARD RULES (Planner 1–10)** — KEEP; re-point DCII refs (rule 8's "the
  DCIC can act on and the DCII can check" → "the Creator can act on and
  self-check"). Rules cover: no invented mechanisms; no mid-pipeline
  pauses; direct-don't-do-the-work; geometry only via params; plan only
  around real metrics; params are the only params; qualitative only;
  locked user values (scope + extent); retry budget; escalation framing.
- **Anti-Hallucination Rules** — merge Planner A–E + Orchestrator 1–6
  (dedup; drop Orchestrator #1 "don't seed the Planner with options" as
  obsolete).
- **The N Design Parameters** (`$parameter_list`) — shared.
- **End-of-session feedback** (`$eos_feedback_intro/outro`) — widen "your
  scope" to cover BOTH planning AND routing decisions.
- **Hard constraints** generic / dc / tools (shared fragments).
- **Geometry Modification Rule** — DECIDED: **FOLDED into HARD RULE 4**
  (the `$geometry_modification_rule` fragment duplicated it). No separate
  geometry section in the Conductor; rule 4 gained "a render defect is a
  PARAMETER change + regeneration; do NOT ask the Tool Caller to fix a
  mesh". The fragment's other content is already covered (HARD RULE 1 =
  custom filenames; Role 2 = propose a change). The shared fragment file
  stays for the other agents' prompts.
- **Reference — user input files** (Planner section) — KEEP (incl.
  `view_images`, filled-in-FORM handling).
- **Utility tools** `read_user_queries`, `read_agent_history` — KEEP
  (Conductor inherits the Planner's).
- **Attempt folders and the attempt tools** (`list_attempts` /
  `read_attempt`) — KEEP. The "you do NOT have a tool to create attempt
  folders and must NOT try to open one yourself" rule is now TRUE verbatim
  (see `new_attempt` decision). "The DCIC creates the folder" → "The
  Creator creates the folder".
- **Searching past saved sessions** (`$database_search_tool`,
  `$database_search_per_agent`, `$retrieve_*`) — shared, `<<HAS_DBA>>`.
- **BSV block** (`$blade_sections_visualizer*`) — shared, `<<BSV_ON/OFF>>`.
- **Routing tools** (`{routing_instructions}`) — Conductor's merged set:
  `call_user_input_inspector`, `call_creator`, `call_tool_caller`,
  `call_dc_output_inspector`, `call_receptionist`. (Bodies in stage 2.)
- **Chain access block** (`{chain_access_block}`) — KEEP (Conductor is the
  hub / chain-visible).

---

## Integration flags / open items (do NOT lose)
- **Soft targets (7-agent LIVE `70ded2f`; 5-agent Conductor DONE):** the
  first-class SOFT TARGET feature (a provided value subordinated to a goal —
  see `design_soft_targets.md`) is committed across the 7-agent prompts and
  added to the 5-agent **Conductor** draft (HARD RULE 8 third case + HARD
  RULE 9 exclusion + relay-authorisations bullet). When you author the
  5-agent **UII / Creator / DCOI** drafts (stages 3-4), carry the soft-target
  handling into them too: UII marker convention + UI-pin-softening; Creator
  not-locked/start-near + self-validate-no-violation (the DCII half); DCOI
  "not a claim to enforce".
- **`read_extracted_inputs` tool:** the Conductor reads the extraction
  (Role 1) → it needs this Planner tool. Confirm in wiring/routing (stage
  2/4).
- **APPROVE ↔ Name-attempt-format:** the Conductor's APPROVE hand-off to
  the Receptionist must itself carry the full "Name the attempt folder(s)"
  format (every attempt's number + absolute path + the `Show to user:`
  line) — no Orchestrator to add it. Cross-reference chunk 3 (Name the
  attempt folder(s)) ↔ chunk 2 APPROVE when assembling.
- **Forward vs recovery hop asymmetry:** forward hops auto-unroll unseen
  (Creator→Tool Caller→DCOI); recovery hops the Conductor drives manually
  (RECOVER move). Role 3 "what you do NOT see" is scoped to forward hops.
- **Role 1/2/3 names** are referenced by survivor prompts → when tailoring
  UII / DCOI / etc. (stage 4), update "the Planner's Role 3" →
  "the Conductor's Role 3".
- **Extraction-only** handling: the Orchestrator had a dedicated section;
  folded into Role 1's extraction-only bullet (dedup). Re-check no unique
  detail is lost when finalizing.
- **DCOI → Conductor:** the DCOI now returns directly to the Conductor
  (end-of-cycle + precision refine). The survivor DCOI prompt (stage 4)
  must re-point Planner/Orchestrator → Conductor.
- **Creator = DCIC + DCII:** the Creator self-validates (absorbs the DCII's
  authority/range checks). Its prompt (stage 3) merges DCIC + DCII,
  resolving "route to the DCII" → "self-check".
- **Standing directives machinery** (`agents/shared/standing_directives.py`
  + dispatcher re-stamp): the Conductor is the SOLE issuer (was the
  Planner). Wiring stage: point the issuer role at the Conductor.
- **`call_creator` tool name** is an assumption — confirm when writing the
  routing fragment (stage 2).

---

## ✅ STEP 4 DONE — topology-aware prompt/fragment resolution (2026-08-02)

**Layout.**  `agents/<N>agent/` holds only the files that DIFFER from the
7-agent originals — 20 of them for the 5-agent — each suffixed `_<N>agents`
and filed under a sub-folder mirroring its source root (`prompt_fragments/`,
`dc_config/`, `tools_config/`, `<agent>/`).  Everything else is shared: one
copy, cannot drift.  Agents existing ONLY in a topology (Conductor, Creator)
keep a normal package and take the suffix on the file
(`agents/conductor/prompt_5agents.md`).

**Resolution.**  `_topology()` reads `SYSTEM_TOPOLOGY` FRESH per call — never
captured at import, because the Sessions Queue switches topology between runs
inside one process and `web_app` reloads `settings` but not `prompts`.
`_topology_override(rel_path)` returns the override or `None`; every caller
is override-then-fallback, and there is no `agents/7agent/`, so **topology 7
takes the byte-identical historic path**.

Touched: `_read_dc_fragment`, `_read_generic_fragment`, `_prompt_path` (new,
3 candidates), the two per-agent overlays in `_build_template`,
`_pipeline_flow_fragment_name()` (was a constant), and
`routing._load_routing_fragment`.

**Three defects the test found and closed:**
1. `$routing_conductor` had no slot → the Conductor shipped that literal
   string and ZERO routing-tool docs.  Fixed by a single topology-neutral
   `$routing_hub` slot that BOTH hub prompts reference, filled from
   `routing_<hub>.md` for the active topology.  Chosen over an
   `optional=`/second-helper approach because it makes the missing-file case
   *not exist* rather than tolerating it — a real typo still raises.
   Also delivers `_HUB_BY_TOPOLOGY` / `_hub_agent()`, which step 6 needs.
2. The UII passes a PF-branched name (`routing_user_input_inspector_uii_first.md`)
   that its 5-agent override could never match → it silently loaded the
   **7-agent** fragment, i.e. was told to call `call_planner` /
   `call_orchestrator`, neither of which exists or is bound in a 5-agent run.
   Fixed by collapsing the `_planner_first` / `_uii_first` branch as a
   SECOND candidate in `_load_routing_fragment` (exact name still wins).
   Chosen over renaming the file so it cannot regress if `PLANNER_FIRST` is
   ever flipped.
3. `_USER_FACING_AGENTS` → `_NON_CHAIN_AGENTS`, now listing both hubs.  The
   name described the wrong property: the filter gates `<<CHAIN_ONLY>>`,
   which is about being a LINK IN THE CHAIN, not about talking to the user.
   Without the entry the Conductor kept "ESCALATE to the Conductor",
   "return to the Conductor", "route your content to the Conductor" —
   self-referential instructions to the hub.

**Verification** — `extra_utilities/smoke_test_topology_fragments.py`
(imports the REAL `prompts.py` / `routing.py`; only `agents/__init__.py` is
stubbed, as it drags in `langchain_core`).  Run with `py` (needs ≥3.10).
Seven checks over 4 combinations (topology 7/5 × `PLANNER_FIRST` False/True):
COVERAGE, NO-LEAK, ISOLATION, SHARING, SLOT, HUB-SLOT, CHAIN_ONLY, plus
DEGRADE and PRECEDENCE.  **All pass; 20/20 overrides reached.**  Separately
verified by sha256 that all nine assembled 7-agent prompts are **byte-identical**
before and after the whole step.

---

## ✅ CLOSED (step 7) — receptionist-hop trace, landed WITH the dispatch entry

Resolved by making `dispatch_turn` topology-neutral: the "5-agent dispatch
entry" this was waiting on turned out not to be a new function at all, but
`dispatch_turn` itself once it stopped naming a concrete hub class.  Both
halves landed together, as required — `dispatch.py` now emits
`_trace("Receptionist", hub_display(), "forwarded")`, and the suppression in
`routing_tools.py` is keyed on `target_key == hub_key()`.  Original analysis
kept below for the reasoning.

---

## 🔗 (was) COUPLED — receptionist-hop trace

`routing_tools.py` `build_routing_tool._invoke` suppresses its own
`_trace(caller, target)` for the Receptionist → hub hop:

```python
if not (caller_key == "receptionist" and target_key == "orchestrator"):
```

Step 6 made the sibling chain-log skip hub-aware but left THIS one literal,
deliberately.  The suppression is only correct where something else emits a
richer trace, and the sole emitter is `agents/dispatch.py:277`
(`_trace("Receptionist", "Orchestrator", "forwarded")`).  `Conductor.dispatch`
has no counterpart — its only `_trace` calls are "stopped by user" and
"Error, Escalated to Conductor".  So keying this on the active hub today would
SILENTLY DELETE the Receptionist → Conductor trace rather than de-duplicate
it.  Left literal, the 5-agent path emits exactly one trace, which is correct.

**When writing the 5-agent dispatch entry**, do both in the same change:
1. emit `_trace("Receptionist", "Conductor", "forwarded")` at the point the
   Receptionist hands off, mirroring `dispatch.py:277`; and
2. change the guard above to `target_key == hub_key()`.

Doing either alone is wrong: (1) without (2) double-traces the hop; (2)
without (1) loses it entirely.

---

## 🔶 OPEN — the LIVE 7-agent flow never emits the UII's two path lines

**Not a 5-agent problem.**  Surfaced while wiring the Receptionist's runtime
slots (2026-08-03) and deliberately left alone: it changes live, deployed,
working behaviour and deserves its own review.

### The finding, code-conclusive
The UII reads and writes files ONLY via paths given in its incoming hand-off
— `user_input_inspector.py:317` returns *"Error: no directory path
provided"* otherwise — and its prompt says so ("persist your extraction to
the ``Extraction output file:``").  But:

* the ONLY place those two labels are emitted is
  `agents/planner/prompt.md:38-39`;
* that block sits inside `<<PF_ON>>` (opened line 33, closed line 43);
* `PLANNER_FIRST` is `False` in `settings.py:270` — the live default — so
  the block is STRIPPED at assembly.

Verified by assembling all four candidate prompts under topology 7: the
string `Extraction output file:` survives in the **UII's** prompt only, and
the UII is the CONSUMER, not the emitter.  Nobody sends the line.

Real runs (ID228 / ID229) succeed, so the UII must be INFERRING the
conventional paths and happening to be right.  That is a latent fragility,
not a design: it breaks the moment a path convention changes, a session uses
a namespaced inputs dir, or a weaker model guesses differently.

### Why it is NOT fixed by the Receptionist change
In the 5-agent flow the Receptionist hands off to the UII, so giving it the
two slots closes the hole there.  In the 7-agent flow the UII's entry point
is the **Orchestrator**, a different agent — so the fix needs an Orchestrator
prompt edit, an entry in `PROMPT_MD_RUNTIME_SLOTS["orchestrator"]` (today
only `chain_access_block`), and a `.format()` change in `orchestrator.py`.

### Proposed fix when it is taken up
Add the two lines to the Orchestrator's FORWARD-to-UII hand-off, mirroring
`agents/5agent/receptionist/prompt_5agents.md:110-111`, and note that
`orchestrator.py` already imports what it needs.  Cost is two lines per UII
hand-off; benefit is that the path stops being a guess.

---

## 🔶 OPEN — the eager `*_TEMPLATE` block in `prompts.py` (raised 2026-08-02)

**Status:** deliberately NOT touched during the topology-resolution step, to
keep that step's blast radius small.  Not a live defect today; a latent trap.
Decide before the 3-agent variant.

### The condition
The tail of `agents/shared/prompts.py` builds nine module-level constants at
**import** time:

```python
RECEPTIONIST_TEMPLATE = _build_template("receptionist")
ORCHESTRATOR_TEMPLATE = _build_template("orchestrator")
PLANNER_TEMPLATE      = _build_template("planner")
UII_TEMPLATE          = _build_template("user_input_inspector")
DCIC_TEMPLATE         = _build_template("dc_input_creator")
DCII_TEMPLATE         = _build_template("dc_input_inspector")
TOOL_CALLER_TEMPLATE  = _build_template("tool_caller")
DCOI_TEMPLATE         = _build_template("dc_output_inspector")
DH_TEMPLATE           = _build_template("database_handler")
```

They are the **7-agent** set, and they run exactly once, when the module is
first imported.  All nine are listed in `__all__`.

### The problem (four parts, in ascending severity)

1. **Wasted startup work.**  Under topology 5 all nine still build — including
   Planner, Orchestrator, DCIC and DCII, which that topology never
   constructs.  Each `_build_template` call re-reads ~40 fragment files, so
   this is ~360 file reads done at import for ~4/9 no reason.  A cost, not a
   correctness issue.

1b. **What those four builds actually CONTAIN is incoherent** (this is the
   sharper form of 1, and the original O9 in `design_topology_selector.md`).
   Under topology 5, `_build_template("planner")` reads the 7-agent
   `agents/planner/prompt.md` but fills it from a topology-5 slot map — so
   `PLANNER_TEMPLATE` becomes the 7-agent Planner prompt with **5-agent
   fragments spliced into it**: `generic_constraints_5agents.md` telling it
   to escalate to a Conductor, `hard_constraints_dc_5agents.md`, and so on.
   A topology-MIXED prompt, not merely a wasted one.  Harmless only because
   nothing reads it — which is exactly the assumption problem 3 says will
   not hold forever.

2. **They are topology-frozen and hot-reload-stale.**  `_topology()` is read
   fresh per call precisely because the Sessions Queue switches topology
   between runs inside one process.  These nine capture whatever
   `SYSTEM_TOPOLOGY` was on disk when the module was FIRST imported, and
   never update — neither on a topology switch nor on a System-Prompts-UI
   edit.  They are the one place in this module that breaks the
   fresh-read contract.

3. **They look like the supported API.**  Being in `__all__`, a future caller
   doing `from agents.shared.prompts import DCOI_TEMPLATE` would silently get
   an import-time, topology-frozen, stale string, while every current agent
   correctly calls `_build_template(...)` fresh in its own `__init__`.  This
   is the same trap already documented for the module-level fragment
   constants at `prompts.py` ("captured at import time for back-compat …
   NOT used by `_build_template` any more").

4. **They become a hard startup failure the moment a topology deletes a
   prompt.**  Each line needs its `agents/<agent>/prompt.md` to resolve.  All
   nine 7-agent files exist today, so under topology 5 candidates 1–2 of
   `_prompt_path` miss and each falls through to its historic file — fine.
   But if the 3-agent variant ever REMOVES a 7-agent prompt file, this block
   raises `FileNotFoundError` **at module import**, i.e. the whole app fails
   to boot rather than failing at the one agent that needed it.

### Why it is safe right now
Grepped: no production code reads any of the nine.  The only consumer is
`extra_utilities/smoke_test_prompt_format.py:88`
(`getattr(prompts, f"{name}_TEMPLATE")`).  So today they are dead weight.

### Proposed solutions

- **Option A — make them lazy (recommended).**  Delete the nine assignments
  and add a PEP-562 module-level `__getattr__` that maps
  `<NAME>_TEMPLATE` → `_build_template(<agent_dir>)` on attribute access.
  Fixes 1, 2 and 4 at once: nothing is built until asked for, and what is
  built is topology-correct and disk-fresh.  `__all__` is unchanged and
  `smoke_test_prompt_format.py` needs no edit, so call-site churn is zero.
- **Option B — remove them.**  Delete the nine constants and their `__all__`
  entries; change the one harness to call `_build_template` directly.
  Cleanest end state and kills 3 outright, but it is a public-API removal.
- **Option C — guard only.**  Wrap the block in a topology check or a
  try/except.  Addresses 4 alone, leaves 1, 2 and 3 in place.  Not
  recommended — it hides the staleness rather than fixing it.

**Recommendation:** A now (zero call-site churn, fixes three of four), then B
later if the API surface is ever worth removing outright.

---

## Final completeness pass (planned)
Once the whole Conductor draft is assembled, run an adversarial,
line-by-line completeness audit of the draft against BOTH originals
(`agents/planner/prompt.md`, `agents/orchestrator/prompt.md`) to catch any
dropped/weakened instruction — BEFORE moving to the fragment bodies.

---

## Value-states shared fragment — three-state model redesign (2026-07-27)

The LOCKED / SOFT TARGET / FREE explanation is being **restructured for
clarity** (model-first, fluid prose — NOT a rigid table) and pulled into a
**single topology-agnostic shared fragment `$value_states`**, LIVE at
`agents/shared/prompt_fragments/value_states.md` and **SHARED by both
topologies** (the 5-agent draft copy was deleted 2026-07-31 — see F4). It
states the model +
recognition + the three authorisation sources (A hand-off / B DESIGN INTENT
/ **C `(unlocked by user)` inline annotation**) + the "as needed vs freely"
extent — ONCE. Each consumer keeps only its role-specific ACTION.
- **Rule:** presentation redesign only — **no semantics change**; re-validate.
- **Consumers to rewire = `$value_states` + action:** 7-agent **DCIC**
  (write), **DCII** (check), **Planner** HARD RULE 8/9 (what a plan may
  touch), **DCOI** (judge a soft target vs its goal); 5-agent **Creator**
  (write + check). User chose **whole-set + fix-7-agent-first**.
- **Content-loss catch:** source **(C) `(unlocked by user)` annotation** was
  in the DCIC "Verbatim entries" bullet + DCII §4a but missing from my first
  `$value_states` draft — restored.
- **Granularity decision (2026-07-28):** ONE full `$value_states` (core +
  authorisation, not split). The DCOI carries the full model and simply does
  not act on the authorisation part — accepted as harmless extra context.
- **LIVE fragment created + registered (2026-07-28):**
  `agents/shared/prompt_fragments/value_states.md` written (clean body, no
  draft header); registered in `prompts.py` — added to `_build_slots()`
  (`"value_states": _read_generic_fragment("value_states.md")`) and to
  `FRAGMENT_TO_SLOT`. No braces in the fragment → no `{}`-escaping / `.format()`
  risk. Not import-verified (py3.8 worktree can't load the app).
- **DCIC rewired LIVE (2026-07-28):** `agents/dc_input_creator/prompt.md` —
  (A) "Verbatim entries" bullet now points to the three-state section instead
  of restating locked-by-default; (B) the whole `## User-supplied … LOCKED by
  default` block (When-authorised / When-not / Soft-targets / free-values)
  replaced by `## The three states … $value_states` + a 5-sentence **write-
  action** (verbatim LOCKED / seed-near-and-move SOFT / discretion FREE /
  escalate-to-Orchestrator-not-UII, don't-invent). DCIC now inherits the
  extent clause (user approved — "it should have had it to begin with").
  Cross-ref "the LOCKED rule above" (line ~150) still resolves. **Wording
  generalization flagged:** the explicit sender list (Orchestrator / Planner-
  via-Orchestrator / UII / CLARIFY) → generic "incoming hand-off"; auth TYPES
  all preserved; offered to restore senders to the write-action if wanted.
- **DCII rewired LIVE (2026-07-28):** `agents/dc_input_inspector/prompt.md` —
  `## The three states … $value_states` inserted before `## What to Check`;
  §4a slimmed to the CHECK-action (precedence **Planner directive > extraction
  > DCIC discretion** kept verbatim; bullet 2 now reads "fall back to the
  extraction's **markers**" and keeps "do NOT flag a soft-target deviation").
  Everything from `Then check parameters.json:` onward unchanged.
- **Planner rewired LIVE (2026-07-28):** `agents/planner/prompt.md` —
  `## The three states … $value_states` inserted between the `<<DCII_ONLY>>`
  status block and `## HARD RULES` (the `<</DCII_ONLY>>` tag stays glued to the
  new heading, so the heading survives both DCII on/off builds); HARD RULE 8
  slimmed to the Planner's per-state actions + scope/how-far authorisation.
  HR9 / HR10 reviewed, NO change needed (they APPLY the model, not define it).
- **⚠ CONTRADICTION CAUGHT BY THE USER (2026-07-28) — keep this lesson:** my
  first HR8 rewrite said *"LOCKED covers any number the user gave directly,
  whether in user_query.txt or the extraction's QUANTITATIVE INPUTS"* — which
  **contradicts SOFT TARGET**, because a soft target IS a number the user gave
  directly in QUANTITATIVE INPUTS. **Rule: LOCKED is defined by the ABSENCE OF
  A MARKER, never by the SOURCE of the value.** The original avoided this with
  "LOCKED **by default** … SOFT TARGET is **the exception**"; my slimming
  dropped that framing. Fixed by removing the source clause entirely and
  letting `$value_states` define all three states. Also dropped: the
  `user_query.txt` mention — a raw query number carries NO marker, so state is
  only decidable from the extraction's QUANTITATIVE INPUTS.
- **Repo-wide contradiction sweep (2026-07-28):** adversarial multi-agent audit
  of all ~70 prompt-surface files (7 live prompts + shared fragments + DC
  fragments + 5-agent drafts + a Python-embedded-prompt critic) for the same
  "locked-by-source" defect class.
- **⚠ NEW FEATURE SPUN OUT (2026-07-28) — see
  `extra_utilities/design_no_ask_back_and_range_degrade.md`.** Benchmark 6
  (user states an OUT-OF-RANGE value, asks to keep it, asks the system NOT to
  ask back) exposed that the Receptionist hard-gates out-of-range values at the
  front door and no "don't ask back" support exists anywhere. Owner signed off
  8 decisions (global no-escalation, standing directive in DESIGN INTENT,
  extraction-only vs geometry 2×2, degrade-to-SOFT-TARGET reusing the existing
  marker, DCIC substitutes + DCII verifies, insistence = authorisation,
  mandatory disclosure, never override). **This SUPERSEDES the pending P2 edit**
  — do not apply the old P2 wording as-is. Requires amending the live UII rule
  "use a soft target ONLY when the user themselves subordinated the value".
- **DCOI rewired LIVE (2026-07-28) — 3 changes, one of them a REAL BUG FIX:**
  (1) `## The three states … $value_states` inserted before `## Per-claim
  verification …`; (2) **P1** — the 3D precision loop's "iterate only if an
  UNLOCKED lever helps" now says *"A value marked ``SOFT TARGET`` counts as an
  available lever here, NOT a locked number"* (without it the DCOI counts a soft
  target among "LOCKED user numbers" and **STOPS iterating**, reporting an
  unmatchable mismatch while a legitimate lever was free — mirrors Planner HR9);
  (3) the "A SOFT TARGET is not a claim to enforce" paragraph gained a clause for
  when the in-scope comparison source is the user's RAW INPUTS.
- **⚠ DCOI_COMPARISON_MODE — I OVERSTATED THIS ONCE, keep the facts:** it is a
  workflow setting 1/2/3, **DEFAULT = 3** (`workflow_settings/settings.py:242`,
  `agents/shared/session.py:43`). 1 = raw user inputs only (extraction OUT of
  scope — the "check the original, not the interpretation" mode); 2 = extraction
  only; **3 = extraction PRIMARY + raw inputs secondary when needed**. So the
  DCOI is NOT normally barred from `extracted_inputs.txt` — only in mode 1. I
  first claimed this made injecting `$value_states` into the DCOI wrong; it does
  not (coherent in 2 and 3, merely inapplicable in 1). Owner uses **mode 3
  always** for tests.
  **The real find:** SOFT TARGET markers exist ONLY in the extraction, but the
  subordination also appears in the user's OWN WORDS — so change (3) makes the
  carve-out fire on the user's language too. Live bug fix for mode 1, and it
  also helps **mode 3's secondary raw-input consultation**.
- **Static checks PASSED before commit:** `value_states.md` contains **0 braces**
  (no `.format()` escaping hazard — the codebase's top gotcha); 4 consumers wired
  (DCIC/DCII/DCOI/Planner); registered in BOTH `FRAGMENT_TO_SLOT` and
  `_build_slots()`. NOT import-verified (py3.8 worktree cannot load the app).
- **FAITHFULNESS REVIEW PASSED (2026-07-28, 11-agent adversarial):** **0
  confirmed losses** out of 6 claimed — every one refuted with evidence of where
  the content survives. **Build safety CLEAN**: the reviewer re-implemented the
  4 filters from `prompts.py:71-119` and rendered both edited prompts under ALL
  FOUR `DCII_ENABLED` × `PLANNER_FIRST` combinations — no unresolved markers, and
  the glued `<</DCII_ONLY>>## The three states …` tag at `planner/prompt.md:288`
  is correct in BOTH branches. Blanket locked-by-source assertion confirmed GONE
  from all four files.
- **Post-review fixes, ALL APPLIED (2026-07-28):**
  * **1f (HIGH) — the DCIC mirror of the DCOI's P1 bug.** P1 fixed only the DCOI;
    the DCIC — *the agent that actually moves values* — still read "the levers
    that would help are all locked → ESCALATE". So the DCOI would hand back a
    shape gap expecting a soft-target chord to move while the DCIC declared no
    lever available. **This is the failure already observed in production
    ("DCIC froze levers", precision-sections work)** — P1 alone would NOT have
    fixed it. Added the soft-target-is-a-lever carve-out to BOTH DCIC precision
    paragraphs (sections + full-3D).
  * **3 verbatim losses restored** (the #1 no-details-lost rule, missed by the
    category audit): the **`(HARD)`** force marker on the DCIC heading; the
    dropped verb **"adjust"** + the `re-scale` hyphenation; and **"read it once
    and act."** with the sender enumeration (Orchestrator / Planner-via-
    Orchestrator / UII / CLARIFY bounce).
  * **1a — source (C) was a DEAD marker.** `value_states.md` told 4 agents to
    look for `(unlocked by user)`, but `user_input_inspector/prompt.md:131-138`
    FORBIDS writing it (*"simply OMIT it from QUANTITATIVE INPUTS"*) — VERIFIED.
    It was stale in DCIC+DCII already; centralising SPREAD it to Planner+DCOI.
    Fixed by **correcting the FREE definition** (a value is FREE whether the user
    never specified it OR specified-then-released it — omission is the real
    unlock mechanism) and **demoting (C) to legacy** ("IF PRESENT — an older
    extraction may still carry this"), so archived DB extractions still parse.
  * **1b** — DCII §4a bullet 2 now accepts *"a user permission named in the
    hand-off (source (A) above)"*; without it an Orchestrator-relayed user
    permission fell through to LOCKED → VIOLATION → bounced a lawful DCIC change,
    contradicting `orchestrator/prompt.md:198-201`.
  * **1e** — Planner HR8 regained `user_query.txt` coverage: a number the user
    gave in chat that the extraction has not yet recorded (incl. a
    `[Receptionist clarification: …]` line) is LOCKED until the extraction says
    otherwise. Without it, a fresh clarification classified as FREE.
  * **4b** — `sketch_handling.md` cross-ref *"see 'Soft targets' in the
    extraction format"* made self-contained; it is injected into UII+DCII+DCOI
    but only the UII has that heading.
  * **3a SKIPPED deliberately** (owner agreed): HR8's inline restatement of the
    three states duplicates the fragment, BUT *"**no plan** may change a LOCKED
    value"* is Planner-specific force the generic fragment does not carry.
    Force > tidiness.
- **Done:** `$value_states` LIVE + registered; Creator C2a uses it; **DCIC + DCII
  + Planner + DCOI all rewired LIVE**; P1/P3/P5 + all post-review fixes applied;
  adversarially reviewed with 0 surviving losses. **Pending:** P2 (soft-target
  out-of-range → CLARIFY) and P4 (Receptionist permission block) proposed but NOT
  approved; the no-ask-back feature (own design doc); the Creator merge C2b/C3/C4;
  then commit + a re-validation run.

## ⚠ SOFT-TARGET FRICTION FIX — "the goal governs" (2026-07-28, owner-driven)

**Owner caught a bias I INTRODUCED and shipped in `ae39b9e`.** My compressed
write-action read *"Seed a SOFT TARGET **near** its stated value and move it
(within range) to serve its goal"* — which frames nearness as the default
posture and movement as the exception. The owner's objection, verbatim: *"this
friction … can prevent the system from finding the best solution … only stay
close to it if there are no other design goals that are important and related
to that parameter."* Benchmark 7 ("dimensions given, but fit the shape") is
exactly what it would have degraded.

**Note the pre-existing text was already RIGHT** — the old DCIC said "keep it
close while that does not fight the goal, and move it freely to serve the goal
when they conflict". The friction came from my compression, not from the
original. **Lesson: when compressing a two-sided rule, check which side the
compression makes the default.**

**Decisions (owner, 3 explicit sign-offs):**
1. **Goal first; the stated number is only a TIEBREAK.** Set the parameter to
   whatever the goal calls for, from the first attempt onward. Fall back to the
   user's number ONLY when the goal does not bear on that parameter.
2. **Reframe the shared `$value_states` SOFT TARGET bullet**, not just the
   write-action — it is the definition all 4 live agents read.
3. **The "keep near … if free" STRENGTH survives**, as the tiebreak calibration
   for the no-conflict case ("not as important" → free choice; "prefer X but
   the shape matters more" → use X).

**Applied (4 places):** `value_states.md` SOFT TARGET bullet (now leads with
"**The goal governs**" + "you never have to justify moving it"); the DCIC
write-action; `user_input_inspector/prompt.md:235` (its description of what
downstream agents do said "start near this value" — stale once downstream went
goal-first); and the Creator draft C2a. **Pending:** `sketch_handling.md:72`
"start-near references" — the last residual, proposed.

**⚠ RE-VALIDATION NEEDED:** logs ID228/ID229 validated soft targets under the
OLD wording, so they do NOT cover this. A fresh run is required before trusting it.

## Creator merge — C1/C2/C3 DONE (2026-07-28)

- **C1 revised to THREE phases** (owner's call — "the write is considerably
  different from the self-validate"): **DRAFT → SELF-VALIDATE → WRITE**.
  Originally WRITE-then-validate, which was **impossible**: `write_parameters`
  refuses a folder that already holds a `parameters.json` (append-only) and the
  DCIC opens *exactly one* attempt per generation, so a post-write correction
  had nowhere legal to go. Draft-first means the file on disk is **validated by
  construction**. Added guard: *"do not write a set you know to be wrong."*
- **C2a corrected + C2b written**: real-world-quantity (3 routes), filtering
  responsibility, acting-on-a-Conductor-directive, all 3 precision paragraphs.
  Re-points: Planner/Orchestrator→Conductor, `<<DCII_ONLY>>` audit clauses→
  "check it again in your self-validation", DCIC discretion→your discretion.
- **C3 written** — the DCII's 5 axes as the Creator's own pre-write check:
  images section (owner: "match what the dcii does" — inherits all 5 tools +
  the selectivity framing), `$sketch_handling`/`$sketch_notes` (union rule: the
  DCII has them, the DCIC does not), §1 strict per-parameter range check, §2
  consistency, §3 hard blockers via `calculate`, §4a changeability ladder, §4b
  real-world verification, §5 appropriateness (advisory framing KEPT and
  re-pointed — it is the only sentence stopping the value-author from
  overriding the plan). Verdict table: 3 destinations → **PASS** (write once →
  Tool Caller) / **SELF-CORRECT** (no hop) / **ESCALATE** (Conductor).
- Owner decisions: no mandatory `read_parameters` re-read (it authored the
  values; staleness cannot occur inside one turn).
- **Live bug found while copying:** the DCII said *"**Four** tools"* then listed
  **five** (`ocr_regions` added later without updating the count). Fixed live.

## ✅ 5-AGENT PROMPT LAYER COMPLETE (2026-08-01)

The four per-agent fragments for the merged agents are written, so **nothing
prompt-side remains**: 6 prompts + 17 fragments.
- `database_search_conductor.md` — merges the Planner's + Orchestrator's;
  "request is complex" appeared in both (one copy kept), and the two priority
  lines collapse into one once those agents are the same agent.
- `database_search_creator.md` — merges DCIC's (retrieve_attempt to calibrate
  parameter choices) + DCII's (retrieve_user_inputs with images to validate).
  Dropped the DCII's trailing retrieve_attempt clause — the DCIC half already
  mandates it.
- `blade_sections_visualizer_conductor.md` — the Planner's verbatim except the
  closing rule, which said *"**you** should NOT open a new attempt"*: the
  Conductor holds no `new_attempt`, so it is re-pointed to direct the Creator.
- `blade_sections_visualizer_creator.md` — the DCIC's, with "create the attempt
  and write" re-ordered to "open the attempt and write" per draft-first.

## ✅ TOPOLOGY LAYOUT DECIDED + DRAFTS PROMOTED (2026-08-01)

**Owner's decision: separate folder per topology, SHARED FILES STAY SHARED.**
The second half is what prevents another F4 (the stale `value_states` copy).
Also decided: **leave the 7-agent where it is** — it is the incumbent, working
system, and moving 8 live prompts buys symmetry while risking a system that
runs today. `SYSTEM_TOPOLOGY` will default to 7.

**Layout (grounded in the loader: `_build_template` reads
`AGENTS_DIR / <name> / "prompt.md"`, and `<name>` is a PATH string, so a
nested path needs NO loader change):**
```
agents/conductor/{conductor.py, prompt.md}   NEW — 5-agent only, no variant needed
agents/creator/{creator.py, prompt.md}       NEW — same
agents/<agent>/prompt.md                     7-agent, UNCHANGED
agents/5agent/<agent>/prompt.md              the FOUR survivor variants only
agents/5agent/fragments/*.md                 17 topology-specific fragments
agents/shared/prompt_fragments/              SHARED by both, never copied
```
Only the four survivors need a variant, because they share one Python class
but read different prompts. The Conductor and Creator exist only in the
5-agent, so their prompts sit with their code as ordinary agent packages.

**PROMOTED 2026-08-01:** all 22 draft files moved into place, `<!-- DRAFT -->`
headers stripped (authoring notes = real tokens every turn; the information
lives here instead), and the drafts DELETED so exactly one copy of each file
exists. `routing_boilerplate.md` deliberately stayed in `extra_utilities/` —
it is a port-notes document, not a prompt fragment; no agent reads it.
**Zero runtime risk: nothing reads these paths until `SYSTEM_TOPOLOGY` is
wired.**

**WHAT REMAINS IS CODE + THE TOPOLOGY SELECTOR** (no prompt work):
`agents/conductor/` and `agents/creator/` packages; `prompts.py` templates +
allow-lists (incl. the F1 Receptionist runtime slots); a `routing.py` variant
(strings already recorded in `routing_boilerplate.md`); dispatch registration
and `call_conductor` / `call_creator` tool bindings; then a validation run.
**The selector governs where all of it lives and is still undiscussed.**

**OWNER'S END-OF-5-AGENT REVIEW (requested 2026-08-01) — do this before
declaring done:** check for (1) anything missed, (2) useless repetitions,
(3) text that can be shrunk/simplified without losing effectiveness, (4) token
count reducible without impacting effectiveness, (5) inconsistencies or
conflicts between the 7-agent and 5-agent systems.

## Stage-4 AUDIT + fix set F1–F7 (2026-07-31) — CLOSED

**29-agent whole-set audit: 0 confirmed losses**, filters all correct
(including the Creator PF pair mis-resolved earlier — now right), no stale
agent names in any body. But the CROSS-FILE pass found what per-file review
structurally cannot — gaps that would break a run:

- **F1 — the UII would get NO paths.** It needs `Input directory:` /
  `Extraction output file:` "verbatim; don't guess"; its tool handlers ERROR
  without them. Fixed: the Receptionist now emits both.
  **⚠ LIVE FINDING (code-conclusive, own section in `routing_boilerplate.md`):
  the ONLY emitter is `planner/prompt.md:38-39`, inside `<<PF_ON>>` — and the
  live default is PF_OFF, so the block is STRIPPED and NO live agent emits
  them.** Runs succeed only because the UII infers the conventional paths.
  Latent live fragility; a 7-agent fix is NOT yet proposed.
- **F2 — the Receptionist's second door was invisible.** The Conductor said
  raw user input "never" reaches it (3 places + 2 fragments). Fixed across
  all 5, plus a Role-1 clause, plus a **light CLARIFY path in Role 2** (a
  chain agent asking what you meant gets a sharpened directive, NOT a full
  Recovery PLAN). This also resolved a contradiction that PREDATED the audit
  (conductor :194 "not to fetch new content" vs :480 "route through the UII").
- **F3 — the Receptionist's context died at the UII.** Owner corrected my
  first proposal: DESIGN INTENT is about the PIECE, not the system's modus
  operandi, and the 7-agent conveys this by **verbatim relay**
  (orchestrator:90/93, planner:158 — verified). My persistence argument was
  also wrong: agents are STATEFUL, so a relayed cap already persists.
  Landed as BOTH channels (owner's call): the DESIGN INTENT bullet broadened
  `Reporting preferences` → **`Process preferences`** (covers strategy caps
  and "run without asking back" — which is exactly what **no-ask-back D1**
  needs), plus a one-clause relay in the UII's forward. Also added "your
  incoming hand-off is a source too".
  *Checked:* the `Reporting preferences` bullet is NOT mine — it dates to the
  initial commit `e16d20e`.
- **F4 — deleted the stale `draft_shared_fragments/value_states.md`.** It
  predated the live `8ebfe5f` fix and would have REGRESSED "goal governs" on
  promotion. Root cause was copying a fragment that never needed copying (its
  only agent reference is the UII, which survives), so the fix kills the
  staleness CLASS: value_states is SHARED, like `capabilities_can/cannot`.
- **F5** — conductor "the Receptionist splices those from the extraction" →
  the Receptionist CANNOT read it; the Conductor can, so it includes the
  values itself. (The live Planner hedged "Orchestrator / Receptionist"; the
  merge kept the wrong one.)
- **F6** — dropped the "Conductor's final user-facing wrap-up" exception.
  **It was already wrong LIVE**: the Orchestrator's own prompt says "do NOT
  write the final user message yourself". Confirmed rule: every agent ends
  with a routing call; the ONLY exception is the Receptionist replying to the
  user. Worth fixing live separately.
- **F7** — `available_agents` said the Tool Caller does "exactly two
  design-tool actions", which literally BLOCKS the `render_blade_sections`
  the Conductor's own precision directive requires. Now split by
  `<<BSV_ON>>`/`<<BSV_OFF>>`: the ON variant (the DEFAULT) emphasises BOTH
  rendering actions and that the directive must say which; the OFF variant
  states plainly that sections cannot be rendered alone.

**Deferred, INHERITED from the 7-agent (not merge-introduced):** the DCOI
cannot supply the `Parameters file:` line it is told to carry; the Creator's
DCOI-directed context dies at the Tool Caller; no `conductor`/`creator`
variants of the per-agent database/BSV fragments; `user_input_inspector.py`
still says paths are "supplied by the Planner".

## Stage 4 — routing layer + survivor prompts (2026-07-28, IN PROGRESS)

**Routing layer DONE** (`extra_utilities/draft_5agent_fragments/`):
- `routing_boilerplate.md` — the 5-agent `NATURAL_PIPELINE`
  (`Receptionist → UII → Conductor → Creator → Tool Caller → DCOI →
  Conductor`; the Receptionist IS in the string, unlike the 7-agent one,
  because here it is genuinely the UII's previous), the per-agent
  prev/next table, every boilerplate re-point, and a recorded warning about
  the PF-branch trap. **The one substantive change, not a rename:** the
  authorisation source list collapses from three to two — "from the user
  (via Receptionist → Conductor), or from the Conductor itself".
- `routing_user_input_inspector.md` (gains `call_receptionist` — the UII asks
  the user directly through it), `routing_creator.md` (NEW; CLARIFY and
  ESCALATE share `call_conductor`, differing only in stated intent),
  `routing_tool_caller.md` (DCII_OFF branch, CLARIFY → `call_creator`),
  `routing_dc_output_inspector.md`, `routing_receptionist.md`.
- **`generic_constraints.md`** — the stage-2 deferral, now done.
  **`<<CHAIN_ONLY>>` markers are KEPT**: unlike `<<PF_*>>`/`<<DCII_ONLY>>`
  (topology flags resolved at authoring time), CHAIN_ONLY strips chain-only
  rules for the USER-FACING agents, which here are the Receptionist and the
  Conductor. It is still doing real work.
- **`agents/shared/routing.py` was NOT touched** — it is live and drives the
  7-agent system; the topology selector is still a pending discussion. The
  boilerplate doc records the exact strings so that port is mechanical.

**Receptionist's NEW judgement (owner decision):** it now dispatches into the
pipeline, so it inherits the "is this meaningful content" call the Orchestrator
makes today. Criterion: **new/changed design content → UII; an answer to a
system question, a control instruction about an in-flight run, or a restatement
of something already captured → Conductor.** A message that does both → UII.

**Survivor prompts:**
- **Tool Caller ✅** `draft_prompt_tool_caller.md` — remarkably clean, only
  THREE re-points (DCIC→Creator at the staleness note, Orchestrator→Conductor
  at "no menu of options", Planner→Conductor at "strategy decisions belong
  to"). No `<<PF_*>>`/`<<DCII_ONLY>>` markers exist in it at all.
- **DC Output Inspector ✅** `draft_prompt_dc_output_inspector.md` — made by
  COPYING the live file and applying targeted edits, so the untouched ~90% is
  byte-identical (verified: ~27 changed lines of 423). 12 mechanical re-points
  + `call_orchestrator`→`call_conductor` throughout. Two judgement calls:
  (1) "you do NOT re-check parameters (that's the DCII)" → "(that's the
  **Creator's self-validation**)" — the job moved, it did not vanish;
  (2) the two `<<DCII_ONLY>>` asides in "Override authority" — a LITERAL
  rename would have been **false**, since the original says "the DCII's check
  is parameters-vs-extraction only" but the Creator now consults raw inputs
  too (the A5 decision). Re-pointed to the surviving distinction instead:
  "the Creator validates PARAMETERS against the inputs; only you compare the
  rendered RESULT against them" / "overriding a **Creator PASS**".
- **User Input Inspector ✅** `draft_prompt_user_input_inspector.md` — copy +
  targeted edits. Contained MANY `<<PF_ON>>/<<PF_OFF>>` pairs, ALL resolved to
  **PF_OFF**. FORWARD target `call_planner` → **`call_conductor`**. One block
  rewritten beyond a rename: the live PF_OFF text says *"You are the first
  agent in the chain — there is no upstream agent to CLARIFY back to"*, which
  is FALSE in the 5-agent system — the Receptionist precedes the UII and the
  UII can call it. Replaced with the Receptionist-relays-not-decides paragraph
  + the new `call_receptionist` ask-the-user path.
- **Receptionist ✅** `draft_prompt_receptionist.md` — the biggest survivor
  change. **Path 1 now has TWO doors** (`call_user_input_inspector` /
  `call_conductor`) plus the "Which door" criterion; every `call_orchestrator`
  had to resolve to one of them or be generalised ("the act of invoking **a
  forward tool** IS the decision to forward"; "must NOT invoke **any routing
  tool**" in Situation B). Also re-pointed the `read_agent_history` roster
  (Planner→Conductor for reasoning, DCIC→Creator for parameter values) and the
  database/images agent lists. **Flagged + fixed consequence:** the
  extraction-only flag used to be addressed to the Orchestrator directly;
  the Receptionist now forwards to the UII, so it is re-pointed to "so the
  **Conductor** can route appropriately", noting the UII carries it on and
  independently recognises an extraction-only ask.

**All four survivor bodies verified to contain ZERO residual topology refs**
(the only grep hits are the drafts' own header comments). **Stage 4 COMPLETE**;
whole-set audit running (per-prompt faithfulness + adversarial verification +
a cross-artefact consistency pass over all 6 prompts and 13 fragments).

## Creator C4 + merge audit (2026-07-28) — DRAFT COMPLETE

**C4 written:** attempt folders (case (A) dropped — the Conductor has no
`new_attempt`), no-op-write ban folded into self-validation, read/write tool
policy, a merged Output Format carrying BOTH the choices and the validation
result, the 3-line Tool Caller hand-off, routing split into fix-yourself vs
escalate, and a merged end-of-session scope covering both halves of the job.

**29-agent completeness audit: 0 CONFIRMED LOSSES out of 22 claimed.** Stale
topology mechanically clean (0 hits for DCIC/DCII/Planner/Orchestrator);
filter markers balanced (only `<<HAS_DBA>>` / `<<BSV_*>>` survive — no
`<<DCII_ONLY>>` / `<<PF_*>>`, matching the settled 5-agent decision).

**But the coherence pass found 6 real self-contradictions — all fixed:**
- **A1 — I resolved a conditional filter to the WRONG branch.** DCIC:323 is
  `<<PF_ON>>the UII<</PF_ON>><<PF_OFF>>the Planner<</PF_OFF>>`; the 5-agent
  flow is **PF_OFF (uii-first)**, confirmed by
  `routing_dc_input_creator_uii_first.md:7` (`call_planner` = CLARIFY target).
  I had kept the PF_ON branch. Fixed → **the Conductor**, which also collapses
  the phantom 4th route: CLARIFY and ESCALATE share one tool, differing only
  in stated intent.
- **A2** — the MUST tool sequence omitted `new_attempt`; now
  `new_attempt` → `write_parameters` → `call_tool_caller` (2 places).
- **A3** — "never call `new_attempt` a second time" + "open ONE fresh
  `new_attempt` and write there" contradicted each other once case (A) was
  removed. **Owner's ruling: a post-write correction IS a NEW generation** —
  allowed, gets a fresh attempt, never an overwrite. Reuses the precision
  loop's existing principle ("every round is a fresh generation"). Bounded by
  the EXISTING guards (no-op-write ban + "corrected once and it persists →
  ESCALATE"), no new numeric cap. **Applied to the live DCIC too**, per
  "same goes for the DCIC".
- **A4** — a write the tool REJECTS is not a write; "exactly once" counts
  successful writes.
- **A5** — phase 2 let the AUTHORISATION check go "light on a nudge" while
  §4a said "check every cycle". **Owner's model, now implemented: everything
  the DCIC checks (ranges + blockers + authorisation) runs EVERY cycle; only
  the DCII-style deeper comparisons (raw inputs/images, appropriateness,
  real-world audit) scale.**
- **A6** — two overlapping fix-lists that disagreed (pre-write "fix the draft"
  vs post-write "re-call the tool"); collapsed, with the post-write cases
  named explicitly.
- **B1** — "axis 5" pointed at nothing (the draft has phases, not axes) and
  misdirected to §5 = *Appropriateness*; now names §4 explicitly.
  **B2** — "missing from your hand-off" → "the incoming hand-off" ("your
  hand-off" everywhere else means the one the Creator WRITES).

**Not changed (deliberate):** the real-world-quantity do-then-verify
duplication (doing and checking are genuinely different passes) and the
duplications inherited verbatim from the sources — trimming those would break
the faithful-merge rule rather than serve it.

## 🔴 DCIC NOW SELF-CHECKS BEFORE WRITING (2026-07-28, owner-driven — LIVE FIX)

**Owner's side-question during C4 exposed a live hole:** *"does the DCIC, in any
case, check its own parameters before writing the file, like the creator does?
The DCIC should. The DCII is more like an additional check."*

**Verified: the DCIC had NO self-check at all.** Its only "verify" was specific
to unit conversions; its only pre-write check was the no-op check (compares
against PREVIOUS writes, not ranges). Guideline 4 said *"ALL values MUST be
within their allowed ranges"* with no procedure. Combine that with:
  * the DCIC **skips the DCII on ~2 of 3 precision refine rounds** (tight loop);
  * `write_parameters` validates key-set + numeric-ness only — **no code-level
    range check exists anywhere**;
  * the DCII's own prompt records that range violations *"produced false
    APPROVEs in prior runs"*.
⟹ **On most precision refine rounds, parameters reached the geometry backend
with ZERO range validation.**

**Applied (3 edits):**
1. New `## Validate before you write (HARD)` in the DCIC — per-parameter range
   check, hard-blocker inequalities via `calculate`, and "every user value you
   moved must have SOME authorisation behind it" (owner reworded this from
   "is authorised", which read as an assertion rather than a check to perform).
2. Attempt folder is opened **only once the draft PASSES** — a check that
   escalates can no longer leave a dead empty folder.
3. **DCII guard against relaxing:** *"The DC Input Creator now runs its own
   range and feasibility check before writing. That is NOT a reason to relax
   yours: it can misjudge its own work… Re-check every parameter yourself,
   exactly as if no prior check had happened."*

**Owner's explicit constraint — the DCII loses NOTHING:** *"The DCII is an
additional check for EVERYTHING, not just the things the DCIC does not check on
itself. It can happen that the DCIC makes a mistake when reviewing itself,
that's why the DCII also has to check what may seem as a redundant check."*
The redundancy is deliberate. Net DCII change: +4 lines, −0.
**Tight precision loop KEPT** — it is now safe, since the skipped rounds are no
longer unvalidated.

## ⚠ RECEPTIONIST RANGE GATE REMOVED (2026-07-28, owner)

Owner: *"remove completely from the receptionist the function of blocking
out-of-range values, it's easier like this at this point."* The
`## Quantitative viability check` is now a `## Parameter-name check`: the
range comparison AND the blocking are deleted; **name-mapping survives**
(unrecognised parameter names still bounce), as does the no-clip half
(*"never silently clip, round, or redistribute a user's value"*).
**Why it mattered:** the gate was silently failing the owner's **text-only
parameter-extraction benchmark tests** — an out-of-range value stopped the
request at the door even though the Planner would never have sent it to the
DCIC. Fixed 2 dangling refs ("step 1 of the quantitative check", "the
quantitative viability check below"); grep confirmed no other agent depended
on it. **This also removes the front-door blocker the whole no-ask-back
feature was built around** — see the status update in
`design_no_ask_back_and_range_degrade.md`.

**Out-of-range routing is now AUTHORITY-BASED, not marker-based** (live DCII +
Creator draft). Owner's objection to my marker-based draft: it would make the
no-ask-back case depend on the UII having written a `SOFT TARGET` marker — and
per G5 the UII may never even detect a unit-mismatched breach. So: escalate
only when **nothing** authorises the move; any of a `SOFT TARGET` marker, a
hand-off permission, a DESIGN INTENT permission, or a directive is enough.

## Separate feature TODO (surfaced 2026-07-26 — NOT part of the reduced-agent build)

**Per-agent stateful/stateless toggle in the Workflow-Settings agent flow
chart.** For every PIPELINE agent shown in the flow chart, add a
button/tick:
- **ticked = STATEFUL (DEFAULT for every agent)** — the agent remembers
  its own previous messages (its message history persists across its
  invocations within the session, exactly as today).
- **un-ticked = STATELESS** — the agent's only context is its initial
  system prompt; it does NOT remember its previous conversations (fresh
  each invocation).
Scope: **pipeline agents ONLY.** Does NOT apply to the **Context Pruner**
or the **Database Handler**. (Today all agents are effectively stateful;
this makes it a per-agent choice.)

## 3-agent variant (LATER)
- Brain = **Architect** (perceive+plan+route+approve = UII + Conductor
  merged). Plus a Designer (Creator-like) and a Critic (DCOI-like); see
  `design_agent_count_variants.md` §7. Strip-down validation (none).
  Receptionist still extra. Own fragment copies tailored to 3 agents.

## Topology selector (SEPARATE — discuss first)
- A `SYSTEM_TOPOLOGY = 7 | 5 | 3` mechanism to select which prompt +
  fragment set assembles. **NOT to be built unilaterally** — discuss step
  by step. (An earlier unilateral build-plan draft was removed at the
  user's request.)
- **File placement DECIDED (2026-07-26): Option 2 — SEPARATE FOLDERS per
  topology.** Each topology gets a folder holding its COMPLETE set (agent
  prompts + tailored fragments); the selector points the loader at one root
  per topology. Truly topology-agnostic fragments (`parameter_list`,
  `structure`, `modelling_notes`, …) can stay shared. Exact folder names +
  loader plumbing to be locked WHEN the selector is designed. Drafts stay
  in `extra_utilities/draft_5agent_fragments/` until then.
