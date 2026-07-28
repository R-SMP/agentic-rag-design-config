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
3. **Creator prompt** (merge DCIC + DCII).
4. **Survivor 5-agent prompts** (UII, Tool Caller, DCOI, Receptionist),
   cross-references re-pointed.
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

## Final completeness pass (planned)
Once the whole Conductor draft is assembled, run an adversarial,
line-by-line completeness audit of the draft against BOTH originals
(`agents/planner/prompt.md`, `agents/orchestrator/prompt.md`) to catch any
dropped/weakened instruction — BEFORE moving to the fragment bodies.

---

## Value-states shared fragment — three-state model redesign (2026-07-27)

The LOCKED / SOFT TARGET / FREE explanation is being **restructured for
clarity** (model-first, fluid prose — NOT a rigid table) and pulled into a
**single topology-agnostic shared fragment `$value_states`** (draft:
`extra_utilities/draft_shared_fragments/value_states.md`; eventual home
`agents/shared/prompt_fragments/value_states.md`). It states the model +
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
