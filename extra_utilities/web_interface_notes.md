# Web Interface — Parameters Inputs view: full re-design notes

**Status.** Design discussion in progress.  Captured 2026-06-01 from
the user.  Implementation will follow step-by-step once every
question below is locked.  **Do not delete or rewrite the
"User requirements" section** — it is the verbatim source of truth
for the discussion.  Append clarifications below in dedicated
sections.

---

## 1. User requirements (verbatim source of truth)

The current Parameters Inputs view (`web/index.html` data-view="params",
shipped in commit `bf59c4d`) is a tabbed slider configurator inspired
by the standalone `propeller_V3` reference.  The user has now asked
for a substantially different design.  Quoting the user (lightly
edited for formatting only):

### Layout

- Interface split into two, just like in the Chat interface.
- On the LEFT: 3D rendering viewer same as the one of the chat.
- On the RIGHT: All the design parameters, organised into 4 TABS
  along the top: **General Parameters / Inner Profile / Middle
  Profile / Outer Profile**.  Clicking a tab shows only that
  section's contents — no scrolling needed for typical viewport
  sizes.  Each pane shows the matching profile image at the top
  followed by that section's slider rows.
- **There should not be a "Next" button.**  Tab navigation only.

> **Revision note (2026-06-01):** an earlier version of this design
> said *"all parameters visible at once; user scrolls to see them
> all"*.  The user revised this after seeing Step 2's first
> implementation — tabs are preferred to a single long scrolling
> column.  All other design observations are unchanged.

> **Revision note 2 (2026-06-01):**  Two additions made before
> Step 3 implementation:
> 1. The **"Use these parameters"** button is now a PERMANENT
>    feature (previously planned for removal in Step 8 in favour
>    of pure auto-append).  When pressed, it (a) transforms ALL
>    parameter rows to FIXED state — even sliders the user never
>    touched — and then (b) sends the formatted parameter message
>    to the chat as today.  The transformation makes the user's
>    intent explicit ("I am committing to ALL of these values,
>    not just the ones I tweaked"), and the resulting state lines
>    up cleanly with the FIXED-block auto-append landing in
>    Step 8.
> 2. A **"Download geometry"** button is added below the
>    Parameters Inputs view's 3D viewer (mirroring the chat
>    view's button).  Downloads the geometry currently shown in
>    the params-view viewer.  Disabled until the live preview
>    (Step 7) puts a mesh there.

### Tristate VARY / FIXED / PROPOSED button per slider

- To the LEFT of every parameter slider, a button.  Label changes
  based on state:
  - **VARY (gray, unpressed)** — default.  Parameter name and
    slider also gray.  Meaning: not user-imposed; the system can
    vary this parameter freely.
  - **FIXED (green, pressed)** — set when the user modifies the
    slider.  Parameter name and slider also turn green.  Meaning:
    user-imposed value.  The agent pipeline must respect this.
  - **PROPOSED (orange, not pressed)** — set when the system's
    `propose_attempt` tool fires with a value for this parameter
    (see "propose_attempt" below).  Parameter name and slider also
    turn orange.  A text line appears alongside the parameter name
    reading `PROPOSED VALUE: <value>`.  This text persists even if
    the user later changes the slider — the user always sees the
    most recent system-proposed value.

### Chat ↔ Parameters interaction

- When the user sends a chat message, the system appends the
  FIXED parameters to the message AND to the `user_query.txt`
  file.  Format:
  > `The user has fixed the following values through the
  > parameters Input interface: …` followed by parameter names
  > with their current values.
- The system is informed about parameter changes ONLY when the
  user sends a new chat message.  No background sync.
- The "fixed list" appended on each chat message uses the CURRENT
  fixed set at send time.  If the user changes a FIXED parameter
  between two chat messages, the next message will carry the
  updated FIXED list.
- This append only happens if any modification has been made to
  the LIST OF USER-INPUT-PARAMETERS-FIXED since the last send.
  (Open question: does this mean "any change in which params are
  fixed" or "any change in their values"? See §3 below.)

### `propose_attempt` tool (new, DC-specific, on the Receptionist)

- When the system sends an attempt back to the user AND visualizes
  it in the 3D viewer, the Parameters Inputs view also updates.
- The Receptionist gets a new tool called `propose_attempt`.  It
  is DC-specific (propeller for now).  It takes the same parameter
  json the DC tool already consumes.
- Effect of `propose_attempt`:
  - Params the user had FIXED stay FIXED (green).  Their slider
    value is NOT touched.
  - Params the user had not fixed turn ORANGE, button reads
    PROPOSED, slider value moves to the proposed value, and the
    `PROPOSED VALUE: <value>` text appears alongside the name.
  - The proposed-value text persists even after the user later
    moves that slider (so the user always sees the system's latest
    proposal as a reference point).
- The Receptionist system prompt must be updated to remind it to
  always show such proposed values to the user after the 3D
  rendering has been shown.

### Two separate 3D viewers (NOT shared)

- The 3D viewer in the Chat view and the 3D viewer in the
  Parameters Inputs view are SEPARATE.  They look similar, but
  they are independent.
- The attempt shown in the chat's viewer MAY differ in parameter
  values from the params shown in the Parameters Inputs view.
  Worked example the user gave:
  1. User receives the "best attempt" 3D render in the chat
     viewer.  Receptionist also calls `propose_attempt` with those
     parameters → Parameters Inputs UI shows those values as
     PROPOSED.
  2. User asks via chat: "show me the worst attempt".
  3. Receptionist shows the worst attempt's 3D render in the
     chat viewer AND tells the user the worst attempt's
     parameters in the chat reply.  BUT the PROPOSED parameters
     in the Parameters Inputs UI **stay the same** (the best
     attempt's values) — because those are still what "matches"
     the user requirements.
  4. User asks "Propose to me the more conservative attempt that
     weights more".  Receptionist selects a different attempt,
     shows its 3D render in the chat viewer, AND calls
     `propose_attempt` with that attempt's parameters →
     Parameters Inputs UI now updates the PROPOSED values.

### Live 3D preview in the Parameters Inputs view only

- When the user finishes changing a slider, a request to
  regenerate the geometry is sent to RhinoCompute.  The result
  loads into the Parameters Inputs viewer (the LEFT pane).
- This live preview uses the SAME `.gh` file as the tool caller's
  mesh tool, but does NOT call that tool.  It is its own separate
  path.
- Attempts made by the user moving sliders in the Parameters
  Inputs UI **do NOT count as attempts in the system workflow**
  (they don't create attempt rows, don't trigger the
  Receptionist → UII → DCIC chain, etc.).  They are visual-only.

---

## 2. State machine for one parameter slider

For clarity, the explicit state machine the user described:

```
                +--------+
        start → |  VARY  | (gray, unpressed, slider value = default)
                +--------+
                    |
                    | user moves the slider
                    v
                +--------+
                | FIXED  | (green, pressed, slider value = user choice)
                +--------+
                    |
                    | user presses the button to release
                    v
                +--------+
                |  VARY  | (gray again, slider value = ???)
                +--------+

(separately, at any time the system can fire propose_attempt:)
                                    |
                                    v
            if this param was NOT FIXED:
                +-----------+
                | PROPOSED  | (orange, not pressed, slider value = proposed)
                +-----------+
                    +  "PROPOSED VALUE: <value>" text shown alongside name
                    |
                    | user moves the slider
                    v
                +--------+
                | FIXED  | (green, pressed, slider value = user choice)
                +--------+
                    +  "PROPOSED VALUE: <value>" text REMAINS
                       (user always sees the most recent proposal
                       even after over-riding it)
```

Several states / transitions need clarification — see Open Questions
in §3.

---

## 3. Open questions to lock before implementation

### A. State machine fine print

1. **From FIXED → VARY transition.**  The user described pressing
   the button releases FIXED, but did not say what the slider
   value should reset to.  Options:
   a. Slider snaps back to the original default (loses user's
      tweak).
   b. Slider keeps its current value but the colour reverts to
      gray (system can now move it, but the visible position is
      the last user-set one).
   c. Slider snaps to the most recent PROPOSED value, if any;
      otherwise to the default.

2. **Initial slider values.**  Today the sliders use mid-of-range
   defaults from the standalone reference's `SLIDER_CONFIG`.
   Should those stay as the initial gray-VARY values?  Or initial
   = empty / undefined until either user FIXes or system PROPOSES?

3. **"PROPOSED value persists in text even if user changes."**
   Confirmed.  But what if the system fires `propose_attempt`
   AGAIN with a different value for the same parameter (user did
   NOT fix in between)?  Does the orange slider move to the new
   value AND the text update to the new value?  (Probably yes,
   but worth confirming.)

4. **Three modifier sources on one slider** — user, propose_attempt,
   live preview.  What if the user is dragging the slider AND a
   `propose_attempt` arrives at the same moment?  Probably user's
   action wins until they release; then we apply the propose.  Or
   we queue the propose to fire after the drag.

### B. "Fixed list" send semantics

5. **"Only append if the list has been modified since last
   send."**  The user's wording is "modified to the LIST OF
   USER-INPUT-PARAMETERS-FIXED".  Does "modified" mean:
   a. Set of FIXED parameter NAMES has changed (one added or
      removed)?
   b. Set of names AND their values?  E.g. user keeps the same
      params FIXED but moves a slider from 70 → 72 — does the
      next chat message re-append?
   c. Always append on every chat message (simpler — no diffing
      bug surface).

6. **"User fixed nothing" case.**  If the FIXED list is empty
   when the user sends a chat message, do we append a header
   line saying so ("No parameters were fixed by the user"), or
   nothing at all?

7. **Format of the appended block.**  Proposed:
   ```
   The user has fixed the following values through the Parameters
   Inputs interface:
     - bladeCount: 4
     - impellerRadius: 72 mm
     - innerCamber: 5
   ```
   Or JSON-like?  Or whatever the Receptionist prompt is best at
   parsing?

### C. `propose_attempt` tool design

8. **Tool registration.**  The Receptionist currently routes via
   `call_<agent>` tools (call_orchestrator, etc).  This new tool
   is different — it triggers a UI update only.  Should it be:
   a. A LangChain tool the Receptionist's LLM can invoke
      alongside `call_orchestrator` in the same turn.  Pro: the
      Receptionist decides freely when to propose.  Con: the
      Receptionist's prompt complexity grows.
   b. An automatic emission whenever the system surfaces a
      specific attempt in the chat viewer (i.e. wired at the
      Orchestrator/loader level, not in the Receptionist's LLM).
      Pro: cannot be forgotten by the LLM.  Con: less expressive.

9. **Tool signature.**  Take a JSON dict of `{param_name: value}`
   only?  Or also a free-text rationale ("Proposing a thinner
   blade because you asked for less weight") that gets shown to
   the user?

10. **When the user is fresh-in-session.**  Before any
    `propose_attempt` has fired, the Parameters Inputs UI just
    shows all-gray VARY sliders at the reference defaults.  Is
    that the desired empty-state?

11. **Multiple `propose_attempt` per session.**  Each new fire
    overwrites the previous PROPOSED set?  Or accumulates a
    history?  (User said the text persists for the most recent
    one — implies overwrite.)

### D. Two-viewer interaction

12. **Live preview ON / OFF toggle.**  Each slider movement
    triggers a RhinoCompute round-trip (~1-2 s).  Should there be
    a switch the user can toggle if they want to quickly drag
    multiple sliders without each one regenerating?

13. **Debounce duration.**  Slider movement fires a continuous
    stream of events; we need to debounce.  300 ms? 500 ms?
    Or only on `change` (slider release), not `input`?

14. **What does the Parameters viewer show on first load?**  Empty
    placeholder?  An auto-preview of the gray-VARY defaults?

15. **Sharing Three.js infrastructure.**  Currently
    `web/viewer.js` runs a single viewer in the chat-view's
    `<aside>`.  Two options:
    a. Refactor viewer.js to support multiple instances (one in
       chat, one in params).
    b. Instantiate a second viewer module duplicated for the
       params view.
    Option (a) is cleaner; option (b) is faster to ship.

### E. Backend integration

16. **Live preview endpoint.**  New route `/api/preview_mesh`
    (POST a parameter dict, get back a mesh).  Auth: same as
    `/api/turn`?  Rate-limit: yes/no?  Caching: should identical
    parameter sets return cached mesh bytes?

17. **`.gh` file alignment.**  Confirmed v9 uses
    `Propeller_Raul_V1.2.gh`.  The preview endpoint uses the same
    `.gh` so what the user sees in preview matches what the agent
    pipeline generates.  Confirmed.

18. **Where in `dispatch.py` do FIXED parameters get appended.**
    The current entry point is `dispatch_turn(session, user_input,
    inputs_dir, ...)`.  Plan: the frontend includes the FIXED
    dict in the `/api/turn` body; `web_app.py` formats the
    "The user has fixed the following values…" block; the formed
    text becomes the new `user_input` BEFORE `save_user_input()`
    and the Receptionist call.

19. **State persistence across page reloads.**  If the user
    reloads the browser tab mid-session, does the Parameters
    Inputs view restore FIXED / PROPOSED state?  Or reset?
    Persistence could live in:
    a. `sessionStorage` (per-tab).
    b. Server-side per-session state.
    c. Discarded (simplest; relies on the agent pipeline's own
       memory).

### F. Receptionist prompt updates

20. **Reminder for proposed values.**  User said the Receptionist
    prompt must remind it to "always show such proposed values to
    the user after the 3D rendering has been shown".  What exact
    wording?  Need a draft of the prompt fragment.

21. **Reading the user's FIXED block.**  Does the Receptionist
    prompt need explicit instruction on how to read the
    auto-appended "The user has fixed the following values…"
    block?

### G. Scope / cut points

22. **Reference's images vs new images.**  Current
    `web/images/{general,inner,middle,outer}-profile.png` are the
    reference's images.  Keep these or get new ones from you?

23. **Browser support.**  The reference uses ES modules + import
    map, plus rhino3dm CDN.  v9's web/ uses the same general
    pattern.  Both target evergreen browsers.  Lock: Chrome /
    Edge / Firefox latest is fine?

---

## 4. Implementation plan (DRAFT — to be refined after questions are answered)

These steps will be re-numbered and re-scoped once the open
questions are locked.  Each step is meant to be small enough that
the user can test it on Railway before moving to the next.

1. **Restructure the markup**: split-pane (viewer LEFT, scrolling
   parameter column RIGHT), single column with all 17 parameters
   in order, 4 inline section images.  No tabs.  No Back/Next.
2. **VARY/FIXED button + colour states** (no PROPOSED yet, no
   propose_attempt yet, no live preview).  Just gray ↔ green on
   slider modification.  Verify the visual works.
3. **Append FIXED block to chat messages**: frontend sends
   FIXED dict alongside the message; backend
   `web_app.api_turn` formats the block; `dispatch.py` passes it
   through to the Receptionist + `user_query.txt`.
4. **Second 3D viewer in the Parameters view**: refactor
   `web/viewer.js` to instantiate two independent viewers (or
   duplicate as a thin wrapper), wire the params-view viewer
   into a `<div>` on the left side.
5. **Live preview endpoint** `/api/preview_mesh` + frontend
   debounced fetch on slider change.  The new viewer renders the
   returned mesh.
6. **`propose_attempt` tool**: backend (Receptionist tool
   definition, system-prompt update) + frontend (UI updates the
   sliders / labels / button to PROPOSED state + adds the
   "PROPOSED VALUE: X" text).
7. **Cross-viewer scenarios**: the "user asks for worst attempt
   but proposed stays the same" behaviour (verifies that the
   chat-viewer mesh load is decoupled from the parameters-viewer
   PROPOSED state).

---

## 5. Files that will change (rough)

This is provisional — the workflow's code-exploration pass below
will refine it.

- `web/index.html` — replace the current Parameters Inputs
  section (added in commit `bf59c4d`) with the split-pane layout.
- `web/style.css` — restyle from tabbed-pane to scrolling
  column; add VARY / FIXED / PROPOSED colour states; second viewer
  layout.
- `web/app.js` — rewrite the Parameters Inputs JS module added
  in commit `bf59c4d`: replace tab logic with scrolling + per-row
  state machines; add FIXED-on-send append; add `propose_attempt`
  receiver; add live-preview fetch on slider change.
- `web/viewer.js` — refactor to support a second viewer
  instance, OR add a sibling module for the second viewer.
- `web_app.py` — new route `/api/preview_mesh`; modify
  `/api/turn` handler to accept + forward the FIXED dict.
- `agents/dispatch.py` — accept the FIXED dict, format the
  appended block, save to `user_query.txt` AND pass to Receptionist.
- `agents/receptionist/receptionist.py` — register the new
  `propose_attempt` tool; emit the UI update event on tool call.
- `agents/receptionist/prompt.md` — instructions for when to
  call `propose_attempt`; reminder to surface PROPOSED values.
- `tools/generate_mesh/generate_mesh.py` — possibly a re-usable
  helper that the new `/api/preview_mesh` can call (without going
  through the tool-caller path).
- `extra_utilities/TODO_known_issues.md` — F24 may be marked
  resolved (its scope IS this redesign's Step 5); add any new
  follow-ups discovered along the way.

---

## 6. Append-only log (post-discussion decisions)

All 8 critical pivots + 12 detail-level questions locked
**2026-06-01**.  Captured here in the order the discussion settled
them.  This is now the source of truth for implementation;
§3's open-question text is preserved above for context only.

### 6.A. Four critical architecture pivots (locked)

| Pivot | Decision |
|---|---|
| Mesh format pipeline for `/api/preview_mesh` | **Server-side OBJ + URL load.** Endpoint returns OBJ bytes; params-view viewer uses `OBJLoader` (same code path as chat viewer).  No rhino3dm in the browser.  Cheaper diff, no `MeshFinal` ParamName assumption. |
| `viewer.js` refactor strategy | **Class wrapper** (`new Viewer(containerEl, {...})`).  Chat does `window.modelViewer = new Viewer(...)` as a one-line compat shim — existing app.js call sites unchanged.  Params view does its own `new Viewer(...)`. |
| `propose_attempt` mechanism | **LLM-callable tool** modelled on `visualize_3d_model`.  Receptionist invokes it explicitly when proposing a satisfying solution (see 6.E1 below for the precise rule).  Not auto-fired at the loader level. |
| FIXED block injection point | **Extend `save_user_input(text, inputs_dir, *, fixed_params=None)`** in `agents/dispatch.py`.  Receptionist re-reads `user_query.txt`, so this is the single injection point.  Planner's `read_user_queries` tool and UII parse the same file — they get the FIXED block for free. |

### 6.B. State machine fine print

- **A1.**  Initial slider values on first load = mid-of-range from the reference's `SLIDER_CONFIG` (same as currently shipped in `bf59c4d`).
- **A2.**  If `propose_attempt` fires again for a parameter the user has NOT fixed in between, BOTH the orange slider position AND the "PROPOSED VALUE: X" text update to the new proposal.  Latest proposal always shown.
- **A3.**  Race: user is mid-drag on slider S and `propose_attempt` arrives with a value for S → user's drag wins (the proposal's value for S is silently dropped on the slider position), **BUT the "PROPOSED VALUE: X" text alongside S still updates to the proposed value** so no information is lost.  Other params in the same proposal apply normally.

### 6.C. FIXED → VARY transition + "Use these parameters" semantics

- **(from the 4-question batch)**  When the user releases a green FIXED button → slider **keeps its current visible value**, only the colour reverts to gray.  Nothing jumps; the system gains permission to vary but the visible position is informative as a hint.

- **"Use these parameters" button — permanent (revised 2026-06-01).**
  On click:
  1. ALL 17 parameter rows transition to FIXED state regardless of
     prior state (VARY rows become FIXED at their current slider
     position; FIXED rows stay FIXED; PROPOSED rows become FIXED at
     their current slider position — the user is taking ownership).
     The transition is visual + state, identical to what
     `paramsSetState(key, "fixed")` does row by row.
  2. The view switches to Chat and `sendMessage()` is called with
     the formatted parameter message.
  3. Once Step 8's FIXED-block auto-append lands, the Use-these-
     parameters message format will be SIMPLIFIED (e.g. a short
     "Please consider these parameters" message) so the agents
     don't see the full parameter list twice (once in the message,
     once in the auto-appended FIXED block).  Until then, the
     current full-list message stays.

### 6.D. FIXED-block send semantics

- **B1.**  "Modified since last send" = **names AND values changed.**  Moving a FIXED slider from 70 → 72 will cause the next chat message to re-send the FIXED block (the agents must see the updated value).
- **B2.**  Empty FIXED list on chat send → **append nothing extra** (no "no parameters fixed" header).
- **B3.**  Format = prose list **with units** (units from `DC_prompt_fragments/dc_config/parameters.md` — `mm`, `% of chord`, `degrees`, `tenths of chord`, `× impellerRadius`, or empty for `bladeCount`).  Example:
  ```
  The user has fixed the following values through the Parameters Inputs interface:
    - bladeCount: 4
    - impellerRadius: 72 mm
    - innerCamber: 5 % of chord
    - middleAngle: 18 degrees
    - middlePos: 0.5 × impellerRadius
  ```
  This means `PARAM_GROUPS` in `web/app.js` needs a `unit` field per parameter (extracted from the existing label text or added explicitly).

### 6.E. `propose_attempt` rules — REVISED per user clarification

**E1 — DO NOT auto-fire on every attempt visualization.**  The
Receptionist is NOT forced to call `propose_attempt` whenever it
calls `visualize_3d_model`.  The tool is reserved for the case
where the system has decided the attempt is a **satisfying
proposed solution** to the user's requirements — that judgment
comes from the **Planner or DCOI** and is communicated to the
Receptionist via the agent chain.

Concrete rules for the Receptionist prompt:

- **DO call** `propose_attempt(values=<attempt's full 17 params>)`
  when the Planner or DCOI has indicated the attempt satisfies the
  user's requirements (i.e. this is the system's actual
  recommendation to the user).  Pair it with `visualize_3d_model`
  in the same turn.
- **DO NOT call** `propose_attempt` when:
  - The user asks about an attempt for INFORMATIONAL reasons only
    (e.g. *"show me the worst one"*) — the Parameters Inputs
    panel must continue showing the most recently proposed
    satisfying solution.  Call `visualize_3d_model` for the 3D
    render but not `propose_attempt`.
  - The system has produced an attempt that does NOT yet satisfy
    the user's requirements (Planner/DCOI still iterating).
    Visualizing is OK; updating the panel is not.

Cascade implication: the Planner / DCOI prompts may eventually
need a small addition so they communicate their "satisfying / not
satisfying" verdict to the Receptionist in a way the Receptionist's
LLM can act on.  For v1 of this work, assume the chain already
carries enough context (the Planner's existing role-3 hand-off
covers this in many cases); if not, treat it as a follow-up.

### 6.F. Tool payload + UI behaviour

- **C2.**  Tool body payload = **full 17 params** (Receptionist prompt instructs).  UI behaviour:
  - For each param NOT user-FIXED → mark PROPOSED (orange slider + button + name; slider value moves to proposed; `PROPOSED VALUE: X` text shown alongside name).
  - For each param the user HAS FIXED → keep slider GREEN at the user's value (the user's FIX wins on the slider position) BUT also show the `PROPOSED VALUE: X` text alongside the name — so the user is reminded of what the system would have proposed even after overriding it.
- **C3.**  (Same effect as C2's FIXED-overridden case.)  Silently keep the FIXED slider value; still surface the proposed value in the alongside-name text.

### 6.G. Live preview tuning

- **D-debounce.**  300 ms trailing-edge debounce on `input` event (clear/restart `setTimeout` per movement, fire 300 ms after the last input).
- **D1.**  No ON/OFF toggle in v1 — **added to TODO list** (`extra_utilities/TODO_known_issues.md`).
- **D2.**  Empty-state placeholder in the params-view viewer reads *"Move any slider to generate a live preview"*.  Removed on the first successful preview load.
- **D3.**  `functools.lru_cache(maxsize=64)` on the new `render_mesh_obj_text(params)` helper.  Cache key is a sorted tuple of `params.items()`.  Cache invalidated when `Propeller_Raul_V1.2.gh`'s mtime changes (so editing the GH file doesn't serve stale meshes).

### 6.H. `propose_attempt` tool signature

- **C-rationale.**  Tool signature is `values: dict[str, float|int]` ONLY.  No `rationale` arg.  The Receptionist's chat reply already carries the rationale; a separate field would risk fabrication (Receptionist has a "no fabricated observations" hard rule).

### 6.I. State persistence

- **(state-persist).**  FIXED / PROPOSED state persisted via `sessionStorage` (per-tab).  Survives an accidental reload; lost on tab close.  No backend changes.  Format: a single key like `params:fixed_state` holding `{<paramKey>: {state: "VARY"|"FIXED"|"PROPOSED", value: number, proposedValue: number | null}}`.

### 6.J. Scope items

- **F1.**  Keep the 4 reference images at `web/images/{general,inner,middle,outer}-profile.png`.  Same files; just shown inline in the scrolling column rather than per-tab.
- **F2.**  `tool_caller`'s mesh tool stays exactly as-is.  `render_mesh_obj_text` is factored OUT of `generate_propeller_mesh` as a pure helper; `generate_propeller_mesh` then internally calls the helper.  External behaviour (writes to `attempts/`, agent-activity heartbeats, return-string shape) preserved.

---

## 7. Locked implementation plan (12 steps)

Re-numbered after §6.  Each step ships in its own commit and is
testable on Railway in isolation.  We pause after each step for the
user to verify before continuing.

| Step | Scope | Risk | Touches |
|---|---|---|---|
| 1 | Refactor `viewer.js` into a `Viewer` class.  Chat keeps working via `window.modelViewer = new Viewer(...)` compat shim.  **No behaviour change.**  Test: chat 3D render still works exactly as before. | Low | `web/viewer.js`, `web/app.js` (shim only) |
| 2 | Rebuild Parameters Inputs markup as split-pane: `viewer-panel` LEFT (currently empty), scrolling `params-column` RIGHT with all 17 sliders in order + 4 inline section images.  No tabs, no Next/Back.  Test: visual parity vs the user's mock; chat still unaffected. | Low | `web/index.html`, `web/style.css` |
| 3 | VARY ↔ FIXED button + colour states (gray ↔ green) per slider.  Moving any slider transitions that row to FIXED; clicking a green FIXED button releases back to VARY keeping the value (§6.C).  **"Use these parameters"** click also sets ALL rows to FIXED before sending (§6.C revision 2).  Add the **Download geometry** button below the Parameters Inputs view's 3D viewer — markup only, disabled until Step 7 wires a mesh into the params-view viewer (no handler yet).  No PROPOSED yet, no propose_attempt yet, no live preview yet. | Low | `web/app.js`, `web/style.css`, `web/index.html` |
| 4 | Instantiate a second `Viewer` in the params view (`new Viewer(paramViewerDiv, ...)`).  Empty placeholder reads "Move any slider to generate a live preview."  Test: two viewers can coexist; chat viewer unaffected. | Low | `web/app.js`, possibly `web/style.css` |
| 5 | Factor `render_mesh_obj_text(params: dict) -> (str, int)` out of `tools/generate_mesh/generate_mesh.py`'s `generate_propeller_mesh`.  Wrap with `functools.lru_cache(maxsize=64)` + GH-mtime guard.  Test: agent pipeline still generates meshes correctly (existing smoke test passes). | Medium | `tools/generate_mesh/generate_mesh.py` |
| 6 | New `/api/preview_mesh` route in `web_app.py`.  Validates params against `parameters.md` ranges, calls `render_mesh_obj_text`, returns OBJ bytes.  Auth = same as `/api/turn`.  Test: curl/Postman → 200 OK + valid OBJ. | Low | `web_app.py` |
| 7 | Wire debounced (300 ms) slider-change → POST `/api/preview_mesh` → `paramsViewer.load(blobUrl)`.  Test: dragging a slider regenerates the mesh in the params-view viewer; chat viewer unaffected. | Medium | `web/app.js` |
| 8 | Extend `save_user_input(text, inputs_dir, *, fixed_params=None)` to append the FIXED block (with units) under each turn's timestamp header.  Extend `TurnIn` to carry `fixed_params: dict | None`.  Extend `dispatch_turn` to pass through.  Frontend sends FIXED dict on every `/api/turn` (when changed since last send).  **Also: simplify the "Use these parameters" message format** — instead of inlining the full parameter list in the message body, send a short "Please consider these parameters" so the agents don't see the parameter list twice (once in the message, once in the auto-appended FIXED block).  Test: send a chat with some FIXED params; verify `user_query.txt` contains the block; Receptionist+UII+Planner see it; "Use these parameters" no longer produces a duplicate parameter listing. | Medium | `web_app.py`, `agents/dispatch.py`, `web/app.js` |
| 9 | New `propose_attempt(values: dict)` Receptionist tool.  Body validates `values` keys against the canonical param list; publishes `viz_bus` event `{type: "params_proposed", values: ...}`.  Add SSE handler branch in `/api/events`.  Test: invoke from a Python REPL → SSE delivers the event to a connected browser. | Medium | `agents/receptionist/`, `agents/shared/viz_bus.py` (no change needed — just consume), `web_app.py` (SSE branch) |
| 10 | Frontend SSE handler for `params_proposed`: turn non-FIXED sliders ORANGE, set them to proposed values, add `PROPOSED VALUE: X` text alongside every param name (FIXED ones too).  Persist `PROPOSED VALUE` text even after user re-overrides.  Test: trigger from step 9; verify UI matches §6.F. | Medium | `web/app.js`, `web/style.css` |
| 11 | Update `agents/receptionist/prompt.md`: add `propose_attempt` to Situation B's allow-list (`prompt.md:319-344`).  Insert it as the third item in the "Reporting attempts" procedure (`prompt.md:431-465`).  Templatize via a new `$propose_attempt_tool` placeholder.  Use the EXACT rules from §6.E1 (DO call when satisfying solution; DO NOT call for informational visualization or unsatisfying attempts). | Low | `agents/receptionist/prompt.md`, `agents/shared/prompts.py` (template wiring) |
| 12 | Mark F24 resolved in `extra_utilities/TODO_known_issues.md` (its scope IS Steps 5–7).  Add a new TODO for the live-preview ON/OFF toggle (D1) and possibly any other follow-ups discovered during implementation. | Trivial | `extra_utilities/TODO_known_issues.md` |

**Pause points:** after every step, I push, summarise what to test on Railway, wait for user verification.  No bundling.

---

## 8. Notes carried forward to implementation

- The current `web/app.js`'s `PARAM_GROUPS` (added in commit `bf59c4d`) will be rewritten in Step 2 — change its shape to include a `unit` field per parameter:
  ```js
  { key: "impellerRadius", label: "Propeller Radius", unit: "mm",
    min: 60, max: 80, step: 1, value: 71 }
  ```
  Use the unit when (a) rendering the slider's min/max/current values in the UI and (b) when formatting the FIXED block in Step 8.
- The compat shim in Step 1 must export `window.modelViewer` BEFORE any other code reads it — `web/viewer.js` is loaded as a module before `web/app.js`, so the shim runs at module-eval time.  Watch for race conditions where `app.js` reads `window.modelViewer` synchronously at top-level.
- The `params_proposed` SSE event in Step 9 needs frontend de-dup if the SSE connection reconnects mid-session (so the user doesn't see the panel update twice).  Use a small monotonic `event_id` carried in the publish payload.
- For Step 11 (Receptionist prompt update), there's a follow-up to consider: do the Planner / DCOI prompts also need an addition so they reliably communicate the "satisfying / not satisfying" verdict to the Receptionist?  If the existing chain already covers this implicitly, we're fine.  Worth verifying when we get to Step 11.
