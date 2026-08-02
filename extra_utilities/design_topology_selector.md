# Topology selector — design

**Status:** DESIGN AGREED 2026-08-01.  Build approach chosen: **additive steps
only, then stop for a real run.**  Nothing risky is applied until the additive
layer is deployed and sanity-checked.

## Decisions (owner)

| # | decision |
|---|---|
| T1 | Topology is chosen from a **drop-down in the workflow-settings UI** — and takes effect on the **NEXT session**, exactly like the other workflow settings. |
| T2 | Topology is ALSO a **per-run condition in the Sessions Queue**, like the existing per-run single-model setting, so **one overnight queue can mix 7 / 5 / 3** rather than needing three deploys. |
| T3 | The mechanism is **generic over N topologies**, not special-cased for two — adding the 3-agent later is a folder plus a drop-down entry, no further code change. |
| T4 | Layout: **separate folder per topology, shared files stay shared**; the 7-agent stays at `agents/<agent>/prompt.md`. |

## ⚠ The wiring map's O1 was OVERSTATED — corrected here

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

## Structural obstacles that remain real

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
- **O12 — ALREADY LIVE:** `prompts_admin._agent_for_prompt_md` has a
  `len(parts) == 3` gate, so it returns `None` for
  `agents/5agent/<agent>/prompt.md`.  **The unescaped-brace validator therefore
  never runs on any nested survivor prompt** — and the 5-agent Receptionist now
  contains `{user_inputs_dir}` / `{extraction_output_file}`.  Fix early.

## Build order — ADDITIVE FIRST (owner's choice)

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

## Verification reality — VERIFIED, not assumed

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
