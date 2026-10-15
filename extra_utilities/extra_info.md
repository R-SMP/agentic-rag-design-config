# Extra information — what the removed development records knew

On 2026-10-10 the repository was cleaned up at the end of development.  The
build plans, hand-over notes, prompt-edit worklists, prompt-review specs, most
test scripts and the old database migrations were removed.  This file keeps
everything those records explained that is **not** explained anywhere else —
not in the README, the TODO list, `warnings_developer.md`, the docs in
`docs/` or the code's own docstrings.

It is written for both people and AI assistants.  Sections are independent;
read the one you need.

**Nothing was lost from history.**  Every removed file is still in git.
`f173e2d` is the last commit before the cleanup (it is also what
`MT-web-deploy` deployed on 2026-10-10):

```bash
git show f173e2d:extra_utilities/docs/active/topology3_rebuild_plan.md
```
```bash
git checkout f173e2d -- extra_utilities/smoke_test_dh_batching.py
```

§13 lists every removed group and its old path.

---

## Contents

1. [Topology 3 — the 3-agent system](#1-topology-3--the-3-agent-system)
2. [Topology 5 — the 5-agent system](#2-topology-5--the-5-agent-system)
3. [Why three topologies exist](#3-why-three-topologies-exist)
4. [How a topology's prompts and tools are resolved](#4-how-a-topologys-prompts-and-tools-are-resolved)
5. [Editing a topology's prompts safely](#5-editing-a-topologys-prompts-safely)
6. [Traps that cost real time](#6-traps-that-cost-real-time)
7. [7-agent behaviour decisions recorded nowhere else](#7-7-agent-behaviour-decisions-recorded-nowhere-else)
8. [Tool-surface decisions](#8-tool-surface-decisions)
9. [RAG retrieval and saved-attempt renders](#9-rag-retrieval-and-saved-attempt-renders)
10. [Manual upload to the database](#10-manual-upload-to-the-database)
11. [Database schema history](#11-database-schema-history)
12. [Lessons for anyone editing prompts](#12-lessons-for-anyone-editing-prompts)
13. [What was removed, and where it was](#13-what-was-removed-and-where-it-was)

---

## 1. Topology 3 — the 3-agent system

`SYSTEM_TOPOLOGY = 3`.  Built 2026-09-05 → 2026-09-12 as a **fork of
topology 5, never of topology 7** (the owner's brief: start "almost identical
to the current 5-agent system", then ablate).  Topology 5 had already diverged
from 7 (its Planner template was ~3 000 characters longer), so forking from 7
would have re-imported problems 5 had fixed.

### 1.1 Roster

| Key | Display | Role |
|---|---|---|
| `planner` | Planner | **Hub** — plans, dispatches, approves.  Class `Planner3` in `agents/planner3/`, keeping `AGENT_KEY = "planner"`, so it needs no new row in any identity registry (the same move `Planner5` made). |
| `design_engineer` | Design Engineer | **Merge of the DC Input Creator + the Tool Caller.**  Authors the full parameter set, opens the attempt folder (`new_attempt_parameters`), and runs the geometry / render tools itself. |
| `requirements_analyst` | Requirements Analyst | **Merge of the User Input Inspector + the DC Output Inspector.**  Derives the requirements from whatever the user supplied, and judges the renders against them. |
| `receptionist` | Receptionist | Extra — always present, not one of the "3". |
| `database_handler` | Database Handler | Extra — post-session only, never in `_agents_by_key`. |

Each merged agent's class docstring lists exactly which tools it took from
which parent.

**Why these names.**  The Requirements Analyst is deliberately *not* named
for vision: seeing images is one input modality, not its identity — it owns
the requirements at both ends (derives them, then judges against them).  The
two names share no token, so prompts never say "the Engineer" or "the Design
one" ambiguously; neither abbreviation (RA, DE) collides with DCIC / DCII /
DCOI / TC / UII.  New keys got new routing tools (`call_design_engineer`,
`call_requirements_analyst`) because a `call_<key>` name that does not match
the display name is the near-miss that produces mis-routes.

### 1.2 Edges and flow

Eight edges, owner-confirmed 2026-09-05:

```
Receptionist          → Planner
Planner               → Receptionist, Design Engineer, Requirements Analyst
Design Engineer       → Requirements Analyst   (forward: generated, now judge it)
Design Engineer       → Planner                (clarify AND escalate: one tool)
Requirements Analyst  → Design Engineer        (refine loop, Planner not involved)
Requirements Analyst  → Planner                (return / approve / escalate)
```

* **The Planner is not in the refine loop.**  During refinement the two merged
  agents go back and forth directly, as topology 5's DCOI does with the DCIC.
* **The merge grants one capability.**  In topology 5 the Tool Caller cannot
  escalate (no hub edge).  Merged into the Design Engineer, which has that
  edge, the execute half can.  Accepted knowingly.
* **Natural flow is DESIGN-ENGINEER-FIRST:**
  `User → Receptionist → Planner → Design Engineer → Requirements Analyst →
  Planner → Receptionist → User`.  It is the only pipeline string that names
  the user and the Receptionist; that shape difference from 7 and 5 is
  deliberate (with three working agents the Receptionist really is the only
  door in and out).  Do not "correct" it.
* **RA-first is the exception**, chosen by the Planner through a standing
  directive when images must be read before any number can be chosen.

The owner's three worked cases, which the Planner's flow text follows:

1. *Extract inputs from TEXT* → the Design Engineer reads the text and the user
   inputs, writes the parameters, hands back to the Planner.  The RA is never
   called.
2. *Read the blade count / extract from IMAGES* → the Planner issues a
   standing directive telling the RA to analyse the images; if calculations
   are needed the RA calls the DE.
3. *Follow a specific directive with its inputs* → a standing directive
   addressed to both; the RA goes first if inputs must be analysed, otherwise
   the DE; then they go back and forth until the request is met.

### 1.3 Architecture decisions (owner, 2026-09-05 / 09-06)

| | Decision |
|---|---|
| **No extraction file** | `extracted_inputs.txt` does not exist in topology 3.  The RA has no `write_extraction`; nothing writes or reads the file. |
| **Verbal hand-off** | The RA states everything it extracts in its hand-off message — quantitative values, qualitative descriptions, design intent — as free-form prose, not a structured block standing in for the old file. |
| **No crop regions** | The RA never passes image crop regions to anyone: it is the only agent that can see images, so nobody could use them. |
| **DE reads inputs itself** | The Design Engineer binds a `read_user_inputs` variant that shows image **names but not paths** (`include_image_paths=False`): a path is only useful to an agent that can open or relay an image, and the DE can do neither. |
| **Sketch vocabulary kept** | The RA keeps the ROUGH SKETCH / PRECISE SKETCH vocabulary and still issues that verdict — it states it instead of writing it to a file.  It is the only thing that starts a precision job from a drawing. |
| **`DCOI_COMPARISON_MODE` inert** | Under topology 3 the setting is shown greyed out and writes are refused; the RA always uses comparison mode 1 (modes 2 and 3 name the extraction file). |
| **RA built on the DCOI's spine** | The RA's standing job is CRITIC; reading the user's material is a capability it uses when directed.  Its prompt starts from the DCOI's text with the UII's folded in. |
| **No dispatcher checkpoint** | The abandoned first 3-agent design forced the hub back in every N refine rounds.  Dropped: topology 5 has no such mechanism, and a mechanism in only one topology confounds a 3-vs-5 comparison.  The backstops are `MAX_SECTIONS_REFINE_ROUNDS` and `MAX_DISPATCH_HOPS`. |
| **"Escalate" is a word, not an edge** | As in topology 5, prompts say "hand back" / "communicate the problem to the Planner" instead of ESCALATE, but every edge stays — `routing_tools.stuck_escalation` and every error fall-through target the hub. |
| **Step caps** | `MAX_REQUIREMENTS_ANALYST_STEPS = 40` is the **max** of its parents (UII 40, DCOI 40): its two jobs happen in separate invocations.  `MAX_DESIGN_ENGINEER_STEPS = 120` is the **sum** (DCIC 80 + TC 40): its two jobs happen in the same invocation.  Hub `MAX_PLANNER3_STEPS = 40` / `MAX_PLANNER3_VISITS = 150`, like Planner5.  The asymmetry is deliberate; do not tidy it into one rule. |
| **Models** | Inherited through the merge map: Receptionist `gpt-5.4`, Planner `gpt-5.4-mini`, RA `gpt-5.4`, DE `gpt-5.4-mini`, DH `gpt-5-mini`, Context Pruner `gpt-5.4` — `DEFAULT_PER_AGENT_MODELS_BY_TOPOLOGY[3]`, written in full.  The two new keys also have base `DEFAULT_PER_AGENT_MODELS` rows; that is not a leak (the keys exist only in topology 3) and without them any consumer iterating all keys falls back to `FALLBACK_MODEL`. |
| **DH schedule** | `dh_schedule_3agents.default.json` is a mechanical remap of the 33 five-agent rows (UII/DCOI → RA, DCIC/TC → DE, de-duplicated within each row).  Nothing dropped.  Six question NAMES still mention retired agents (`Problem - UII`, `Problem/Invalid solution/Valid solution - DCIC`, `Tool Caller problem`, `Tool Caller problem solution`) — left on the owner's word, to adapt in the UI if the DH is used under topology 3.  The name is not cosmetic: `_slugify` turns it into the stored filename and DB field label, which come back at retrieval time. |
| **OCR** | `ocr_access` lists the RA (both its parents bound image tools) and not the DE (neither did). |
| **Old scaffolding deleted** | The first 3-agent build (`architect`, `designer`) was deleted; both keys are in `session.RETIRED_AGENT_KEYS` so archived sessions and R2 snapshots still load. |
| **Complete prompt mirror** | `agents/3agent/` is a full mirror: topology 3 reads zero files from the shared prompt trees (`tests/smoke_test_topology_fragments.py`, MIRROR case). |

### 1.4 Implementation details that are easy to break

* **Precision counter key.**  `Planner3` counts a refine round on arrival at
  `"requirements_analyst"`.  Ported unchanged from `planner5.py` (which keys on
  `"dc_output_inspector"`) it would never match: the precision loop would run
  to `MAX_DISPATCH_HOPS` with no cap, no error and no log line.
* **Directive carriers.**  `_DIRECTIVE_CARRIERS = {design_engineer,
  requirements_analyst}`; the dispatcher re-stamps the standing directive on
  every hop to a carrier, including RA↔DE hops the hub never sees.
* **Aliases.**  `_AGENT_KEY_ALIASES` maps merged-away names to their new home
  (`uii`/`dcoi` → RA, `dcic`/`tool caller` → DE, `orchestrator` → planner), so
  `read_agent_history("DCIC")` answers instead of burning a step.
* **Local `@tool` stubs.**  The RA and DE carry their own copies of shared
  tool stubs.  A docstring IS the tool description the model reads; importing
  a parent's stub would let a topology-3 wording edit move topologies 5 and 7.
* **`render_check_block` is read at wiring time**, not from module-level
  constants: those resolve at import under whatever `SYSTEM_TOPOLOGY` was on
  disk, and the Sessions Queue switches topology between runs in one process.
* **`mandatory_tail` asymmetry.**  The DE's routing gets
  `("fragment", "mandatory_tail")`, the RA's `("fragment",)` only — the RA's
  routing fragment already contains "Routing is a tool call — MANDATORY".
  Stating that mandate two or three times is what the ID252-262 analysis
  traced three routing failures to.
* **`SOFT TARGET (goal: …; keep near … if free)` is a literal string** the RA
  writes and the DE matches.  Renaming it means changing the RA, DE and
  Planner fragments in the same commit.
* **Tool overlay** `agents/topology3/tool_text.py` (registered in
  `_OVERLAY_MODULE_BY_TOPOLOGY[3]`) shadows topology 5's.  Every value is
  either copied byte-for-byte from topology 5, the superset of two parents
  (`VIEW_IMAGES_PATHS_BY_AGENT`: the DCOI's text already contains the UII's),
  or regenerated from the roster (`READ_AGENT_HISTORY_DESCRIPTION`,
  `SUBMIT_FEEDBACK_DISPATCH_DOC`) so it never advertises agents this topology
  does not build.

### 1.5 State at the end of the build (2026-09-12)

Prompt rounds 1–3 were applied (round 1: removals + co-location; round 2:
Planner and DE; round 3: RA); topologies 7 and 5 stayed byte-identical at
every commit and the dry run drove a full turn in all three topologies.
Items the build left open, **not re-verified since**:

* No live topology-3 run had been recorded as the closing check ("static
  checks cannot see behaviour" — both 5-agent live runs found defects the
  static suite missed).
* The Planner's `read_attempts` section was kept "for now — revisit after a
  live 3-agent run".
* Owner questions: a replacement pre-route self-check for the RA (its old one
  was "did `write_extraction` succeed?"); whether the Receptionist's
  description of the flow still fits DE-first; whether
  `MAX_SECTIONS_REFINE_ROUNDS` needs retuning (a round is still one
  render-and-judge cycle); the DH question names above.
* ~24 uses of the words "extract" / "the extraction" were kept on purpose:
  the decision abolished the file, not the word.
* Held for the owner: the Planner says new user content must reach the RA
  first, while DE-first makes that the exception.
* The RA's `TODO F96` (two output labels nobody is told to read) is in
  `TODO_known_issues.md`.

---

## 2. Topology 5 — the 5-agent system

`SYSTEM_TOPOLOGY = 5`.  Rebuilt 2026-08-31 from the **current** 7-agent
system (an earlier 5-agent build — Conductor + Creator — had been written
against an older 7-agent system and was deleted; `conductor` / `creator` are
in `RETIRED_AGENT_KEYS`).

**Topology 5 = topology 7 minus the Orchestrator, minus the DC Input
Inspector.**  The Planner becomes the hub (`Planner5`, `agents/planner5/`,
`AGENT_KEY = "planner"`; it started as a copy of the current
`orchestrator.py` with the Planner's `current_plan.txt` persistence grafted
on).  Nothing independently validates the parameters between authoring and
generation — the DCIC's own pre-write check and the Tool Caller's range check
are what remain.

### 2.1 The 13 edges

| From | Can call |
|---|---|
| Receptionist | Planner |
| Planner (hub) | UII · DC Input Creator · DC Output Inspector · Receptionist |
| UII | Planner |
| DC Input Creator | Tool Caller · Planner |
| Tool Caller | DC Output Inspector · DC Input Creator |
| DC Output Inspector | Tool Caller · DC Input Creator · Planner |

* The Planner has **no edge to the Tool Caller**, and the Tool Caller has
  **no edge to the Planner** — it is the one agent that cannot escalate.  Work
  enters the DC loop through the Input Creator.
* For the UII and the DCIC, forward and escalate are the **same tool**
  (`call_planner`).
* The DCOI talks to the DCIC directly (in topology 7 precision feedback went
  DCOI → Orchestrator → DCIC).
* "No more proper escalation" is prompt wording only; the edges, the twelve
  error fall-throughs (`topology.hub_key()`), `MAX_DISPATCH_HOPS`,
  `MAX_SECTIONS_REFINE_ROUNDS` and `_surface_limit_to_user` all stay.
* The chain-access feed (the hub reading the inter-agent log) was removed for
  topology 5 — it was the Orchestrator's power and left with it.

### 2.2 Build decisions (owner, 2026-08-31)

* **Full fork.**  `agents/5agent/` is a complete, separate copy of every
  prompt file topology 5 can read — every `.md`/`.txt` under the shared
  fragment trees except READMEs, files scoped to a retired agent and the
  `_planner_first` halves, plus each surviving agent's `prompt.md`.  The fork
  was made complete *by construction*, not by recording which files were read:
  a read-trace misses module-level constants and fragments read at agent
  construction.  Owner: from that moment "any edit on one will not apply to
  the other and vice versa".
* **Inert settings.**  Under topologies 5 and 3, `PLANNER_FIRST` is ignored
  and `DC_INSPECTOR_ENABLED` is forced off.  Both stay visible in Workflow
  Settings with their real value, greyed out; `editor._do_write` refuses a
  change (`_INERT_UNDER_TOPOLOGY`, keyed on the topology the write would
  produce).
* **Overlays, not edits.**  Topology-specific tool text lives in
  `agents/topology5/tool_text.py`, read through `topology.overlay_value()`,
  which **replaces** the shared table rather than merging into it.
  UI-tunable numbers (step caps) live in `settings.py` §28; non-tunable text
  lives in `agents/topologyN/`.
* **Reduced routing sections.**  `routing._sections_for` gives topology 5 the
  same reduced section set as topology 7 (fragment + mandatory tail; the
  header / loop / permission sections are suppressed).  Otherwise each agent
  carried ~3 700 extra characters.
* **Step caps** `MAX_PLANNER5_STEPS = 40`, `MAX_PLANNER5_VISITS = 150`;
  `MAX_PLANNER_STEPS` stays topology 7's.  Models via
  `DEFAULT_PER_AGENT_MODELS_BY_TOPOLOGY[5]` (the hub Planner runs
  `gpt-5.4-mini`).
* **The owner supplied every prompt edit**; structural files (pass-throughs,
  byte-identical copies) were created freely, content never.

### 2.3 Responsibilities that lived only in the Orchestrator / DCII prompts

Any topology that drops these agents must re-home these responsibilities or
lose them silently.  From the 7-agent **Orchestrator** prompt:

1. the two mandatory UII path lines (`Input directory:` and the extraction
   file path) plus the rule for deriving them;
2. when to re-run the UII;
3. the extraction-only stop rule;
4. the `Current attempt <N>:` propagation matrix, including the negative rule
   that a NEW generation carries no attempt number;
5. the precision-refine relay decision (DCOI gap → DCIC, or finalize → Planner
   as final approver);
6. the `Attempts this cycle:` / `Show to user:` block — the Receptionist's
   whole attempt-reporting procedure consumes it, and the hub must emit it on
   APPROVE or the Receptionist reports no parameter values or paths at all.

From the 7-agent **DC Input Inspector** prompt: the precedence order
*system directive > extraction > DCIC discretion*; "a locked value that is
itself out of range is not restored — escalate"; cross-checking the
extraction against the RAW inputs (the only audit of extraction fidelity);
verifying the DCIC's real-world-quantity routes; the advisory
engineering-appropriateness critique; and the physical-impossibility gate
before generation.

In the reduced topologies the hub is the sole issuer of the STANDING
DIRECTIVE and issues one on every run, written for that request.

---

## 3. Why three topologies exist

The reduced topologies exist for **benchmark Test 2** (`docs/benchmark_suite.md`):
how much of the agent structure earns its keep, and where the value of
decomposition lives.  This section keeps the rationale from the 2026-07-26
design study.

**Method.**

* Start from eight **functions**, not agents: Interface, Perceive (vision),
  Plan, Route, Create, Validate, Execute, Critique (vision).
* **Merge** (keep every function, fewer agents) measures specialisation at
  constant capability.  **Prune** (drop a function) measures whether a stage
  is worth having.
* **Nesting** 7 ⊃ 5 ⊃ 3: each smaller system is a collapse of the larger one,
  so each step changes a small, named set of things.
* **The Receptionist is always present and unchanged.**  It does no design
  work and is the experiment's control surface; "7 / 5 / 3" count design-chain
  agents only.
* **The critic is never merged with the agent whose output it judges**
  (self-grading bias).  It is what the precision benchmarks depend on.
* **The hub in the reduced systems is the Planner** with the Orchestrator's
  routing folded in (the owner's steer).

**As built (differs from the original plan).**  The study planned a 5-agent
"Conductor + self-validating Creator (DCIC + DCII)" and a 3-agent
"Interpreter-Conductor (UII + Planner + Orchestrator) + Designer + Critic".
Both first builds were replaced (§1, §2).  As built:

| | Validation before generation | Critic |
|---|---|---|
| 7 | independent DC Input Inspector | DC Output Inspector |
| 5 | DCIC's own pre-write check + Tool Caller range check | DC Output Inspector |
| 3 | Design Engineer's pre-write check | Requirements Analyst (separate from the DE) |

**Warnings for reading the benchmark results.**

* **Cognitive load.**  A merged agent juggles more; if a smaller topology
  scores worse, that may be "one overloaded agent", not "fewer agents".
  Control for it (model choice, per-function quality).
* **Self-validation has correlated blind spots.**  When topology 5 or 3
  misses something topology 7's independent inspector caught, that is the
  measured effect, not a bug.
* **No independent gate means more render-time errors and reactive
  recovery** — the character of the reduced systems, not a defect.
* **Authority concentrates in the hub.**  Watch for it approving its own
  routing and planning without real scrutiny.
* **Merged agents inherit the model tier of their hardest job**, so "fewer
  agents" is not automatically cheaper or faster.  Measure it.
* **Keep the comparison fair.**  Hold models, temperatures, tools and settings
  constant except the topology, and keep merged prompts from adding or
  dropping capability.

---

## 4. How a topology's prompts and tools are resolved

* **The topology number is read fresh on every call**
  (`agents/shared/topology.py`), never captured at import — the Sessions Queue
  switches topology between runs in one process.  `hub_key()` /
  `hub_display()` map it through `_HUB_BY_TOPOLOGY`, falling back to 7 for an
  unknown number.
* **`agents/hub.py`** is the only place that maps a topology to a hub class:
  `hub_class()` (no construction, no API key) and `build_hub(session)`.
* **Engine prompt files** — `prompts._topology_override(rel)` looks for
  `agents/<N>agent/<same sub-path>/<basename>_<N>agents.md` and falls back to
  the shared file.  Only the basename gains the suffix:

  ```
  agents/planner/prompt.md              → agents/3agent/planner/prompt_3agents.md
  agents/shared/prompt_fragments/x.md   → agents/3agent/prompt_fragments/x_3agents.md
  ```

  Topology 7 has no folder, so it always reads the shared files.
* **Pack fragments** (`dc_pack/fragments/{dc,tools}/`, `engine/pack.py`) —
  `<slot>.md` is one text for every topology, `<slot>.t<N>.md` topology N's
  own; the lookup tries `.t<N>`, then the linked file, then `.t7`.
* **Agent-scoped fragments** — `scoped_fragment_path(slot, agent)`.  Any pack
  slot can have one: `<slot>@<agent>.md` / `.t<N>.md`.  An engine slot can
  only if it is marked `scoped: true` in `engine/slot_registry.yaml` (listed
  in `prompts.SCOPED_FRAGMENTS`): `<file stem>_<agent>_<N>agents.md` (agent
  key BEFORE the topology suffix).  The scoped copy wins and can differ in
  substance from the base fragment.
* **Two substitution layers** — `$slot` fragments are spliced when the
  template is built (`_build_slots` / `_build_template`); `{slot}` runtime
  values are filled at agent construction (`set_routing_tools` etc.).
* **Conditional regions** resolved at assembly: `<<DCII_ONLY>>` /
  `<<DCII_OFF>>`, `<<PF_ON>>` / `<<PF_OFF>>`, `<<CHAIN_ONLY>>` (stripped for the
  user-facing agents), `<<HAS_DBA>>`, `<<BSV_ON>>`, `<<DCOI_RANGES_ON>>`,
  `<<UII_PARAMS_ON>>`, `<<CAN_SEE>>` / `<<CANNOT_SEE>>`.
  `_dcii_effective()` / `_planner_first_effective()` key on "is the hub the
  Orchestrator", not on the topology number — keying on the number broke the
  unknown-topology fallback.
* **Routing fragments** — topology 7 has `_uii_first` / `_planner_first`
  variants; 5 and 3 have one `routing_<agent>_<N>agents.md` per agent.  The
  Receptionist and the topology-7 Orchestrator use the static
  `$routing_receptionist` / `$routing_hub` fragments instead of a generated
  routing block.
* **Code overlays** — topology-specific runtime strings (tool descriptions,
  roster lists) live in `agents/topologyN/tool_text.py`, fetched with
  `topology.overlay_value(name, shared)`.
* **The DC-parameter primer** (image + text, `agents/shared/dc_primer.py`) is
  injected at INVOKE time and bypasses every prompt-level filter.  Its text
  resolves through `_topology_override`; the image is shared deliberately (a
  ~1k-token binary, identical everywhere).
* **Who a hub really builds** is its class's `_agents_by_key` literal, read
  by `extra_utilities/scripts/hub_registry.py`.  Two other roster tables exist
  (`sessions_queue.AGENTS_BY_TOPOLOGY` and the one in
  `tests/smoke_test_topology_fragments.py`); do not add a third.
* **The registries a new agent must be added to** are listed in
  `docs/topology_shared_touchpoints.md`.  Missing one usually fails silently.

---

## 5. Editing a topology's prompts safely

* **A topology-N change only touches files under `agents/<N>agent/`** (and
  `agents/topologyN/` for tool text) **and the pack's `.t<N>.md` files**.
  Every shared engine file is topology 7's live prompt, and a linked pack file
  (`dc_pack/fragments/<folder>/<slot>.md`) is every topology's: editing it
  moves all of them — unlink it first to change one topology only.
* **Always assemble and compare.**  Snapshot before and after with
  `extra_utilities/scripts/topology_prompt_snapshot.py save <dir>` /
  `diff <dirA> <dirB>`, and state which agents moved and which are
  byte-identical.  Topology 7's nine prompts must not move for a 5- or 3-only
  change.
* **Never read a base fragment and assume that is what an agent receives** —
  the agent-scoped copy may differ.  Read the assembled prompt.
* **A bound tool's docstring is model-facing and is not part of the assembled
  prompt.**  A sweep for a removed concept must also cover
  `agents/topologyN/tool_text.py`, every `@tool` docstring and the shared
  `*_tool.py` doc builders.
* **Check the ASSEMBLED text for repeats**, not the source file: a `$slot` is
  one line, its expansion can be thousands of characters (merging two prompts
  once spliced the same fragments twice — ~29 % of each merged prompt).
* **Never put a literal `{` or `}` in a prompt fragment** (`warnings_developer.md`
  W45).
* **Empty a fragment rather than deleting it** — a missing scoped override
  falls back to the longer shared file (`warnings_developer.md` W42).

---

## 6. Traps that cost real time

1. **A stale `.pyc` can serve the wrong `SYSTEM_TOPOLOGY`.**  Python checks
   bytecode by (mtime, size), and flipping 7 → 5 → 3 is size-preserving.
   Symptom: the file reads `3`, `git diff` is clean, the import says otherwise.
   Delete every `__pycache__` folder.
2. **`build_hub(session, llm_cache=…)` reaches the hub only** — sub-agents do
   not get the cache.  Patch `agents.shared.llm_client_cache.get_for_agent`.
   The Context Pruner bypasses the cache (`llm_provider.build_llm`) and fails
   open, so an unpatched pruner silently builds a real client.
3. **A scoped file whose slot is not in `SCOPED_FRAGMENTS` is silently inert.**
4. **A scoped fragment added to the SHARED tree leaks into other topologies**
   whenever the agent folder name matches (`planner`, `receptionist`, … are
   shared).  Assemble and diff instead of asking "is it scoped?".
5. **Prompt files are CRLF in the working tree** (`core.autocrlf = true`; git
   stores LF).  Building `"a" + nl + "b"` and then `.replace("\n", nl)`
   produces `\r\r\n`, git stops normalising the file and the diff explodes.
   Read and write with `newline=""`, convert once at the boundary, and check
   `git diff --stat` after a scripted edit (`d.count(b"\r\r\n")` is the direct
   test).
6. **A prose-only turn from a chain agent does not end it** — it fires the
   one-shot routing retry and the agent runs again.  Only the Receptionist
   treats prose as its answer.
7. **A DH schedule row naming an agent the hub does not build** makes the DH
   write `ERROR:` rows into R2 and the Postgres `chunks` table, where they come
   back at retrieval time.
8. **Data before resolver.**  `dh_schedule_<N>agents.default.json` must exist
   before `_SCHEDULE_BY_TOPOLOGY` names it, or `_seed_default` writes the
   topology-blind hardcoded schedule to disk permanently.  The same rule holds
   for `dc_primer._TEXT_NAME_BY_AGENT`, which gates a file read.
9. **The standing-directive re-stamp is invisible in logs** — `[AGENT MSG]` is
   written before the dispatcher re-stamps, so a block shown once in the log
   was not lost.
10. **Never use `DC_INSPECTOR_ENABLED` as a topology lever** — it is global.
11. **A refine ROUND is a full cycle, not a hop.**  The counter increments once
    per arrival at the inspector/critic, so `MAX_SECTIONS_REFINE_ROUNDS = 12`
    means 12 render-and-judge cycles in every topology.
12. **`prompts.py` captures two flags at import.**  `PLANNER_FIRST` and
    `DC_INSPECTOR_ENABLED` are read once, when `agents.shared.prompts` is first
    imported, while `SYSTEM_TOPOLOGY` is read fresh on every call.  That is why
    the snapshot and dry-run scripts use one subprocess per topology.  (Until
    2026-10-10 the import also built every agent template under the on-disk
    topology — TODO F90, now archived.)
13. **`_load_routing_fragment`'s shared fallback uses the original branched
    name**, so a missing collapsed override silently falls through to the
    Orchestrator-naming shared file.
14. **`agents/loader.py` (the terminal REPL) logs the 7-agent roster
    literally** under every topology.  Cosmetic, but wrong in 5 and 3 logs.
15. **Local environment.**  Use `py -3.13` (3.8 cannot parse the PEP-604
    hints).  Where `trimesh` / `langchain_*` are not installed,
    `extra_utilities/prompt_pdf/bootstrap.py` stubs them so the agent tree
    imports; set `OPENAI_API_KEY=sk-dummy` to construct agents (no network
    call is made) and `PYTHONIOENCODING=utf-8` when piping output.

---

## 7. 7-agent behaviour decisions recorded nowhere else

### 7.1 The prompt-reduction programme (August 2026)

The 7-agent prompts were cut roughly in half over five rounds.  The owner
reviewed a PDF of the assembled prompts (`prompt_pdf/` builds it), marking
RED = delete, YELLOW = modify, with typed comments; `prompt_pdf/extract_annotations.py`
turned the mark-up back into file + line edits (typed comments are flattened
page text, found by their font and matched to the nearest highlight).
Round 1 (Receptionist / Orchestrator / Planner / UII, `afc33fa`), round 2
(DCIC / DCII / Tool Caller + changes to all nine agents), round 3 (DCOI),
round 4 (audit-driven repairs), round 5 (2026-08-26).

Decisions that shaped today's prompts:

* **Cuts inside shared fragments go into per-agent scoped copies**, because
  agents were cut differently.  A scoped copy in the shared tree also reaches
  topology 5 when the agent folder name matches, so each needed a topology-5
  pass-through while topology 5 was kept frozen.
* **One `## Hard constraints` section** (DOs, DON'Ts, Domain hard rules,
  Tool-use hard rules) in every agent.
* **One `## ROUTING` section**: the four decision rules (forward to the next
  agent / report back to the hub / clarify with the previous agent / escalate
  to the hub) were folded into the bullets of the tools they apply to
  (topology 7).
* **`Current attempt N: <path>`** — the attempt number sits on the same line
  as its path, because `read_attempts` takes numbers and hand-offs carry paths.
* **The DCOI** runs one precision mechanism whose target (blade sections, 3D
  views, or both) is set by the standing directive; budget ~2–3 refine
  rounds; when it finalizes it names the best attempt so far; feature-level
  feedback is an equal option to parameter-level feedback.
* **Round 5 — the UII stops speaking the configurator's language.**  Its
  extraction uses descriptive labels (`Radius of propeller: 70 mm`), not
  parameter names (owner: "it just sees whatever it sees").  Its OUT OF RANGE
  rule was removed, so the range gates are the DCII and the Tool Caller and an
  impossible value surfaces one hop later.  The DCIC and DCII keep their
  Verbatim vs Real-world-quantity split, so a user who types a parameter name
  still works.  `UII_PARAMETER_LIST_ENABLED` (default False) gates the UII's
  own parameter list.
* **The Receptionist** lost its static parameter list (it calls
  `dc_params_list` when the user asks about capabilities) and its
  parameter-name check.

### 7.2 Earlier owner-driven fixes (2026-07-28)

* **The DCIC checks its own parameters before writing** (`## Validate before
  you write (HARD)`): per-parameter ranges, hard-blocker inequalities via
  `calculate`, and every user value it moved must have some authorisation.
  The attempt folder is opened only once the draft passes, so a failed check
  leaves no empty folder.  Reason: the DCIC skips the DCII on most precision
  refine rounds, and no code-level range check existed.  **The DCII must not
  relax because of it** (owner: "the DCII is an additional check for
  EVERYTHING" — the redundancy is deliberate).
* **SOFT TARGET — "the goal governs".**  The goal sets the value from the
  first attempt; the user's number is only a tiebreak when the goal does not
  bear on that parameter.  (An earlier compression had made "stay near the
  number" the default.  Lesson: when compressing a two-sided rule, check
  which side becomes the default.)  Full model in
  `docs/value_states_and_out_of_range.md`.
* **The Receptionist no longer blocks out-of-range values** — the gate was
  silently failing the text-only parameter-extraction benchmarks.
  Out-of-range handling is **authority-based**: escalate only when nothing
  authorises the move (a SOFT TARGET marker, a hand-off permission, a design-
  intent permission, or a directive).

---

## 8. Tool-surface decisions

* **The three RAG tools stay separate** (`database_search`,
  `retrieve_user_inputs`, `retrieve_attempt`).  A merge was costed and
  rejected: a signature-generated schema cannot express "query + n XOR ids"
  (a hand-written discriminated union only moves the check to runtime); the
  merged schema would cost tokens rather than save them; and the three are a
  typed pipeline — `database_search` emits the `<available_attempts>` ids and
  `<image_ref>`s the other two consume, and `rag_queries.tool_name` records
  which tool produced each row.  The plumbing is not the obstacle: every agent
  routes retrieve calls through `dispatch_retrieve_tool` before its by-name
  lookup.
* **`read_attempts(local_attempt_numbers=None)`** replaced `list_attempts` +
  `read_attempt` (owner's call in round 1, overriding an analysis that said
  keep both).  With no argument it summarises every attempt; with numbers it
  also prints `description.txt` and the full `parameters.json`; both modes list
  the render and mesh paths (the Receptionist needs them for
  `visualize_3d_model`).
* **`new_attempt_parameters(parameters, slug, description)`** replaced
  `new_attempt` + `write_parameters`.  It has no path argument: the folder it
  creates is the folder it writes into, so the two can never disagree.
* **`dc_params_list()`** returns the parameter list on demand instead of every
  prompt carrying it (owner: retrieved "if it explicitly CALLS FOR IT").  It
  reads the shared `$parameter_list` text (`dc_pack/fragments/dc/parameter_list.md`),
  so an agent's own copy of that fragment is not what it returns.
* **One `read_user_inputs`** replaced three text-file readers
  (`list_input_files`, `read_input_text`, `read_image_notes`) wherever they
  were bound; the Planner has no image tools.
* **Not yet audited:** the token cost of what tools *return* (only schemas and
  prompts were measured).

---

## 9. RAG retrieval and saved-attempt renders

Design settled 2026-08-20 / 08-21; not described in
`db_design/database_and_RAG_architecture.md`.

* **Retrieval fetches to disk and describes; it never attaches.**  Both
  retrieve tools resolve ids, download every artefact into a local folder and
  return a text listing (plus the printed text).  Looking at an image is
  `view_images`' job alone (`side_by_side` up to three panels, `layout`,
  per-image `regions`, its own OCR).
* **Caches** live in `attempts/_retrieved/<global_id>/` and
  `inputs/_retrieved/<session_id>/`.  The turn's auto-display scan skips
  `_retrieved`; the caches are deleted (not archived) at end of session.
  Re-retrieving within a session is detected and returns the same reply — the
  agent must never reason about cache state.  Every `inputs/` walker uses the
  non-recursive `file_utils.list_files`, so `_retrieved/` is invisible to them;
  a future recursive walker must skip it.
* **What is printed:** `retrieve_user_inputs` prints each session's
  `extracted_inputs.txt` (uploaded to R2 only for sessions saved after
  `5c6154b`) and every image note with the local path of its image;
  `retrieve_attempt` prints the parameters and the attempt's description.
* **One registry of render views** — `agents/shared/attempt_views.py`
  (isometric, top, blade sections, side) feeds the R2 upload whitelist, the
  retrieve tool and the save-time completion pass, so they cannot drift (that
  drift is how blade-section renders were once written and never archived).
* **Saved attempts are complete by construction.**
  `agents/shared/attempt_renders.ensure_renders()` runs in the DH loop just
  before upload: blade sections first (they need only `parameters.json`), then
  the 3D set.  It never raises: it saves what exists and logs what was
  generated, found or failed, per view (End Session must not fail).
* **One flag per view governs generate + save + retrieve**:
  `ATTEMPT_VIEW_ISOMETRIC`, `_TOP`, `_BLADE_SECTIONS` (on) and `_SIDE` (off),
  plus `ATTEMPT_RENDER_COMPLETION_ON_SAVE` / `_TIMEOUT_S`.  **Saving is
  irreversible:** an attempt saved while a view is off never gets that render
  archived, and turning the flag on later cannot reach back.
* A new setting needs no front-end code: `/api/settings` parses
  `workflow_settings/settings.py`.
* **Which session made each RAG call** (schema v9, 2026-10-10).  Every
  `database_search` / `retrieve_*` call is one `rag_queries` row with the
  agent (`caller_agent`), the tool, the query (`query_text`, or the ids in
  `query_params`) and what came back (`returned_anchor_ids`).
  `run_session_id` holds the calling session's `IDNNN_<date>_<time>` id for
  every session; `session_id` (foreign key) is filled only for saved
  sessions.  The row is inserted during the call and gets its id whenever
  the session is named — a log snapshot, the end of a Sessions Queue run, a
  Database Handler save, or End Session — see
  `agents/shared/rag_queries_link.py`.  The 881 rows logged before v9 were
  backfilled by matching each one to the same `[TOOL CALL]` line in the
  session logs in R2 (all 881 matched; 202 sessions, ID1940–ID2146).
  Example: `SELECT run_session_id, caller_agent, tool_name, query_text,
  returned_anchor_ids FROM rag_queries ORDER BY run_session_id, ts;`

---

## 10. Manual upload to the database

The **Upload to database** view writes one hand-curated entry into the RAG
database.  `agents/database_handler/manual_entry.py` documents the write path
and its three traps; the decisions behind it (owner, 2026-09-15):

* A manual entry is stored like a saved session so the search and retrieve
  tools need no special case.  Its session id starts with `MANUAL_`
  (`retrieval_common.MANUAL_SESSION_PREFIX`); list and delete are scoped to
  that prefix **in the SQL**, not only in the UI.
* `retrieve_attempt` **lists the attempt folder** and returns non-canonical
  images as `<extra_image>` (filtered to image files, canonical views
  excluded), and `db_writer_mm`'s render filter was widened so those images
  reach `chunks_mm`.  Side benefit: a new render type is no longer invisible
  to retrieval until someone registers it.
* Both retrieve tools mark these entries `origin="manual_upload"` and replace
  the "no extraction archived" note with an honest one; the parameter set
  carries `partial="true" keys="N/M"`; `queries.txt` is bare prose (no invented
  turn header).
* Submitting is blocked when an image is attached but both "use as user input"
  and "use as render" are off (it would be stored but unreachable).
* Facts worth knowing: `user_provided_images` is **not** a security boundary
  (when Postgres is down the image listing is attempted anyway); up to schema v8
  `attempt_label` also carried a global UNIQUE while the upsert's ON CONFLICT is
  per session (v9 dropped it), and labels must be timestamp-shaped
  (`<YYYYMMDD>_<HHMMSS>_<NNN>_<slug>`) for the retrieve tools to parse them;
  `r2_uploader._key_prefix()` is `test11/` locally while live data sits under
  `web-v1/`.
* Open when built: nothing ranks a manual entry differently from a real
  session in search; the `retrieve_user_inputs` prompt text still says it
  "prints each past session's structured extraction", which manual entries do
  not have; re-running the multimodal mirror for a manual entry has not been
  exercised.

---

## 11. Database schema history

Only the current schema is kept: `db_design/database_PostgreSQL_schema_v9.sql`,
with `apply_schema.py`, `populate_dc_parameter_schemas.py` and
`drop_all_tables.sql`.  That is enough to build a fresh database.  A v8
database is upgraded with `db_design/migrations/migrate_v8_to_v9.sql`
(idempotent, one transaction, removes no data; 2026-10-10).

Removed: schemas v1–v7 and the older ordered, idempotent migration ledger
(`db_design/migrations/migrate_v5_to_v6.py`, `_v6_to_v7.py`, `_v7_to_v8.py`).
**To upgrade a database older than v8**, restore that ledger from `f173e2d`
and run the scripts in order, then the v8→v9 file; they are idempotent,
and `migrate_v7_to_v8.py` creates `chunks_mm` (with its HNSW index built in a
separate transaction behind a pgvector-version guard).

---

## 12. Lessons for anyone editing prompts

Harvested from the prompt-defect notes, the shrink proposal and its verifier
runs.  Every one of these shipped at least once.

* **A prompt naming a tool the agent does not hold** is the most expensive
  recurring defect — the agent burns steps on "unknown tool" or silently skips
  a rule it cannot satisfy.  (The Orchestrator was once told four times,
  including inside a HARD rule, to call a tool it was never bound.)
* **Calls that can never succeed** — e.g. a glob passed to a tool that does a
  plain path join.
* **Gated text outside its gate** — a RAG section sitting outside
  `<<HAS_DBA>>` handed agents rules for tools they did not have.
* **Enumerations drift from the code they describe** (rosters, tool lists,
  file names).  Derive them from the code where possible.
* **"Another section already says this" must be counted in the assembled
  prompt.**  Claims failed three ways: the other copy did not exist, it
  pointed the other way (a rule about your own blocked action is not a rule
  about a question put to you), or the agent never received the other section
  (the Receptionist and the Orchestrator have no generated routing block).
* **Advisory sentences are obeyed unevenly** — `gpt-5.4` followed them,
  `haiku` ignored them.  To stop a behaviour, unbind the tool rather than
  discourage its use.
* **Deleting a highlighted span strands punctuation** — re-read every cut site.
* **A cluttered, self-contradicting context makes the system decide worse
  without anyone noticing.**  That, more than token cost, was the reason for
  the reduction programme.

---

## 13. What was removed, and where it was

All paths are as they were at `f173e2d`.

| Group | Old location |
|---|---|
| Hand-over notes | `docs/active/topology3_handover.md`, `docs/active/topology5_for_prompt_editors.md` |
| Topology build plans and worklists | `docs/active/topology3_rebuild_plan.md`, `topology5_rebuild_plan.md`, `topology3_stage9_prompt_edits.md`, `topology3_stage9_round2_prompt_edits.md`, `topology3_stage9_round3_ra_prompt_edits.md`; `docs/archive/agent_count_variants_build_tracker.md` (+ `docs/archive/scripts/build_agent_table_v5.py`) |
| Superseded designs | `docs/active/design_3agent_architecture.md` (the abandoned Architect/Designer build), `docs/reference/design_agent_count_variants.md` (§3 above), `docs/reference/design_tool_merges.md` (§8), `docs/active/design_rag_customization_sequence.md` (§9), `docs/active/design_manual_upload_implementation_plan.md` (§10) |
| Prompt-review records | `prompt_reduction_4agents_changes.md`, `_3agents_`, `_dcoi_`, `_round5_changes.md`; `round2/3/5_annotations.json`; `prompt_defects_found.md`; `prompt_efficiency/PROMPT_SHRINK_PROPOSAL_7agent.md`, `UII_CUT_VERDICTS.md`, `prompt_shrink_cuts.json`, `verify_prompt_shrink.cjs`; `draft_5agent_fragments/routing_boilerplate.md` |
| Embedding comparison harness | `embedding_tests/` and the "Embedding tests" side-menu view (8 routes in `web_app.py`, its section in `web/index.html`, its code in `web/app.js` and styles in `web/style.css`).  It compared three ways of searching 35 test sketches: Voyage `voyage-multimodal-3` image embeddings (1024 dims), and OpenAI `text-embedding-3-large` embeddings of a VLM-written visual caption and of a semantic caption.  It had its own Voyage client; the live multimodal layer (`agents/shared/voyage_mm.py`, `voyage-multimodal-3.5` at 2048 dims) is a separate client and was never coupled to it.  It was self-contained, so restoring the folder and those four files brings it back. |
| Database history | schemas v1–v7, `db_design/migrations/` (§11) |
| Test scripts | 39 `smoke_test_*.py` from the folder root and all 11 from `db_design/` — see below |

**Removed test scripts and what each one guarded.**  Six offline checks were
kept in `tests/`.  If you change one of the areas below, restore the matching
script from `f173e2d` and run it (some need Postgres, R2 or API keys, and
`smoke_test_prompt_cache.py` costs a few cents).

| Script | Guarded |
|---|---|
| `smoke_test_all_chain_agents.py` | the Orchestrator builds all seven chain agents with the right keys and state slots |
| `smoke_test_async_turn.py` | the `/api/turn` 202 + SSE `turn_done` contract (400 blank, 409 concurrent) |
| `smoke_test_attempt_coherence.py` | geometry is built only from an attempt's own `parameters.json`; bad records fail cleanly |
| `smoke_test_attempt_renders.py` | the attempt-view registry and the save-time render-completion pass |
| `smoke_test_base_chain_agent.py` | the `BaseChainAgent` contract (snapshot / restore round-trip) |
| `smoke_test_database_access.py` | per-(profile, agent, tool) RAG-access store |
| `smoke_test_database_handler.py` | DH registration; **its case 4 was the only check that `populate_database` never replaces or mutates `session.agent_states[k].messages`** (a prompt-cache byte-stability precondition).  Known broken at removal. |
| `smoke_test_dc_primer.py` | primer assets (the approved 930×309 PNG) and the text block quoting `parameters.md` verbatim |
| `smoke_test_dh_batching.py` | DH batching (grouping, plan validation, repair) and that every schedule row names an agent the hub builds |
| `smoke_test_dh_force_tool_buffer.py` | every forced DH tool call is answered by a `ToolMessage` (an orphan breaks `/v1/responses`) |
| `smoke_test_dispatch_turn.py` | `dispatch_turn`'s five branches |
| `smoke_test_generate_mesh.py` | live end-to-end geometry + render against the configured backend |
| `smoke_test_google_vision.py` | live Google Cloud Vision connectivity and callout recall |
| `smoke_test_image_buffer.py` | the image buffer-and-flush contiguity mechanism |
| `smoke_test_image_compression.py` | `image_compression` downscale / passthrough / exotic modes |
| `smoke_test_llm_client_cache.py` | LLM clients are memoised per (provider, model, api_key) |
| `smoke_test_llm_routing.py` | LLM-routing read/write (per-agent overrides, global mode) |
| `smoke_test_manual_entry_offline.py` | the `MANUAL_` retrieval contract (§10) |
| `smoke_test_manual_upload_compression.py` | a manual upload keeps the compression degree its uploader chose |
| `smoke_test_no_parallel_kwarg.py` | no `bind_tools()` call passes kwargs (`parallel_tool_calls=False` stays off) |
| `smoke_test_ocr_descriptions.py` | no model-facing text mentions OCR when OCR is off |
| `smoke_test_ocr_grouping.py` | `group_words_into_regions` on synthetic word boxes |
| `smoke_test_orchestrator.py` | Orchestrator state slot, exchange log shape |
| `smoke_test_param_rename.py` | exactly the canonical parameter names reach RhinoCompute |
| `smoke_test_parameter_search.py` | the masked-RMSE parameter search (T1), schema and SQL |
| `smoke_test_prompt_cache.py` | real Anthropic calls prove the system + history cache breakpoints (costs money) |
| `smoke_test_prompt_image_regions.py` | the `<<CAN_SEE>>` / `<<CANNOT_SEE>>` split matches which agents can view images |
| `smoke_test_prompt_toggles.py` | `UII_PARAMETER_LIST_ENABLED` / `DCOI_KNOWS_PARAMS_RANGES` in both positions |
| `smoke_test_prompt_tool_audit.py` | no assembled prompt names a tool that nothing in its topology binds |
| `smoke_test_prompts_hot_reload.py` | fragments are re-read from disk on every agent construction |
| `smoke_test_queue_tiers.py` | Sessions Queue topology + tiers; `ALL_AGENT_KEYS == llm_routing.AGENT_KEYS` |
| `smoke_test_r2_upload.py` | live Cloudflare R2 mirror probe |
| `smoke_test_render_blade_sections.py` | blade-sections geometry and PNG rendering |
| `smoke_test_retrieve_attempt_offline.py` | `retrieve_attempt` falls back to Postgres parameters when R2 lacks them |
| `smoke_test_session_archival.py` | end-of-session archival sweeps everything into `previous_sessions/<id>/` |
| `smoke_test_session_roundtrip.py` | live two-turn dispatch + session snapshot round-trip |
| `smoke_test_session_to_from_dict.py` | `Session.to_dict` / `from_dict` round-trip |
| `smoke_test_topology3_tool_text.py` | topology 3's tool overlay is byte-identical / superset / roster-derived as it claims |
| `smoke_test_web_lazy_imports.py` | every lazily imported module in `web_app.py` is imported where it is used |
| `db_design/smoke_test_database_search.py` | live `database_search` (dedup, ACL, token cap, logging) |
| `db_design/smoke_test_database_search_mm.py` | `database_search` over `chunks_mm`, with text fallback |
| `db_design/smoke_test_db_writer.py` | the DH's Postgres writer end to end |
| `db_design/smoke_test_db_writer_mm.py` | the `chunks_mm` mirror for one session |
| `db_design/smoke_test_dh_kwarg_propagation.py` | no `NameError`-class kwargs in nine DH methods (pure AST) |
| `db_design/smoke_test_phase_3c.py` | session- vs attempt-scoped chunk rows |
| `db_design/smoke_test_postgres_pool.py` | Postgres connectivity, pgvector, schema seed |
| `db_design/smoke_test_resolve_session_name.py` | `IDNNN_` session ids from the `session_counter` sequence |
| `db_design/smoke_test_retrieve_attempt.py` | live `retrieve_attempt` (broken at removal: removed `images_flag`) |
| `db_design/smoke_test_retrieve_user_inputs.py` | live `retrieve_user_inputs` (broken at removal, same cause) |
| `db_design/smoke_test_voyage_mm.py` | live Voyage multimodal embeddings |
