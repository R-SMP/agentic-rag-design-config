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
- On the RIGHT: All the design parameters, one after the other, in
  order.  Before the first parameters, show the first image
  (general profile).  Before Inner section parameters, show the
  image of the inner section.  Before Middle section parameters,
  show the image of the middle section.  Before Outer section
  parameters, show the image of the outer section.
- **There should not be a "Next" button.**  All parameters visible
  at once; user scrolls to see them all.

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

Once the open questions in §3 get answers, capture them here in
order so the implementation plan in §4 can be re-numbered with
confidence.

*(empty — waiting for the discussion to start)*
