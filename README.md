# Agentic RAG Design Configurator

A multi-agent system that turns natural-language design requests (plus optional reference images) into a parametric **propeller mesh + 3 renders + a quality-check report**, with optional post-session persistence of each agent's reflections into an embedding-ready database for later RAG.

Built on **LangChain** with swappable LLM backends (OpenAI / Anthropic / Google). The prompt and tool architecture is **DC-agnostic** by design — propeller-specific knowledge lives in `DC_prompt_fragments/` and can be swapped for another design configurator.

## How it works

Nine stateful sub-agents collaborate via a flat horizontal dispatcher (eight in-session, one post-session).

**Default flow (`PLANNER_FIRST=False`, UII-first):**

```
user → Receptionist → Orchestrator → User Input Inspector
                   → Planner → DC Input Creator → [DC Input Inspector]
                   → Tool Caller (mesh + renders)
                   → DC Output Inspector → Orchestrator → Receptionist → user
```

Any agent can ESCALATE to the Orchestrator, which calls the Planner for a Problem/Solution/Sequence plan and re-routes one step at a time. On REVISE, a new attempt folder is opened.

**Post-session save (opt-in):** when the user types `quit`, the system asks whether to save the session to the database. If yes, the **Database Handler** interviews each in-session agent through a per-field `ASK:`/`SAVE:` protocol and writes one `.txt` file per scheduled field, shaped to be embedding-ready (self-contained, declarative, one topic per file, ≤700 `cl100k_base` tokens for Semantic fields).

## Project layout

```
.
├── main.py                       # entrypoint → agents.loader.run()  (REPL)
├── web_app.py                    # FastAPI server backing the JS web UI (Stage A)
├── streamlit_app.py              # legacy Streamlit UI (pre-Stage-A, kept for reference)
├── web/                          # hand-written JS frontend (index.html, app.js, viewer.js, style.css, images/)
├── Dockerfile  docker-compose.yml  # container build + local stack (matches Railway)
├── config.py                     # paths + RhinoCompute env vars
├── requirements.txt
├── requirements-web.txt          # FastAPI + uvicorn stack (web_app.py only)
├── workflow_settings/settings.py # 18 runtime flags (see Configuration)
├── agents/
│   ├── loader.py                 # session lifecycle, REPL, archival, DH invocation
│   ├── step_caps.py              # single source of truth for every MAX_*
│   ├── shared/                   # prompt assembly, routing, retry, rate-limit, tools,
│   │                             # trace/viz_bus, stop_signal, agent_activity
│   ├── orchestrator/  receptionist/  planner/  user_input_inspector/
│   ├── dc_input_creator/  dc_input_inspector/  tool_caller/  dc_output_inspector/
│   └── database_handler/         # post-session interviewer (opt-in)
├── DC_prompt_fragments/          # DC-specific prompt fragments (propeller today)
│   ├── dc_config/                # parameters, structure, capabilities, constraints
│   └── tools_config/             # tool inventory, render-check library
├── tools/
│   ├── generate_mesh/            # RhinoCompute + Grasshopper definition (DC tool)
│   ├── render_mesh/              # trimesh + pyvista backends (DC tool)
│   ├── calculate/  visualize_model/
└── extra_utilities/              # TODO_known_issues.md, warnings_developer.md, smoke tests
```

Generated at runtime (gitignored): `attempts/`, `logs/`, `previous_sessions/`, `database/`, `inputs/`.

## Setup

Requires Python 3.13 and a running [RhinoCompute](https://www.rhino3d.com/compute/) instance for mesh generation.

```powershell
git clone https://github.com/R-SMP/agentic-rag-design-config.git
cd agentic-rag-design-config

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Environment variables

Copy each `.env.example` to `.env` and fill in the values:

```powershell
copy .env.example .env
copy agents\.env.example agents\.env
```

| File | Purpose |
|---|---|
| `.env` (root) | `RHINO_COMPUTE_URL`, `RHINO_COMPUTE_API_KEY` |
| `agents/.env` | Default `LLM_PROVIDER`, `MODEL_NAME`, and the matching API key (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`) |
| `agents/<agent>/.env` | Optional per-agent override (falls back to `agents/.env`, then root `.env`) |

⚠️ Real `.env` files are gitignored — never commit API keys.

## Running

```powershell
python main.py
```

A REPL opens. Type a design request (and optionally drop reference images into `inputs/input_images/` paired with `<name>_note.txt` files). Type `quit` to end the session; the system will ask whether to save to the database.

## Web UI

Alongside the REPL, a FastAPI + plain-JS web frontend ships as `web_app.py` + `web/`. The same dispatcher (`agents/dispatch.py:dispatch_turn`) drives both surfaces — no agent logic lives in the web layer (per `extra_utilities/warnings_developer.md` W17).

Run locally with uvicorn:

```powershell
pip install -r requirements.txt -r requirements-web.txt
uvicorn web_app:app --reload --port 8000
```

Or production-faithfully via docker-compose (matches the Railway build):

```powershell
docker compose up -d --build app
```

Then open `http://localhost:8000` (uvicorn) or `http://localhost:8501` (compose).

### Side-menu interfaces

The left rail switches between seven views:

| View | Purpose |
|---|---|
| **Chat** | Conversational interface + inline 3D viewer for generated meshes.  Image-render bubbles carry an "Attempt NNN" heading and the viewer toolbar shows a matching "Attempt NNN" badge so it's always clear which design is on screen. |
| **Image Inputs** | Upload reference images, attach a `_note.txt` description per image |
| **Parameters Inputs** | Direct-edit form for the 17 design params with live 3D preview. Split-pane like Chat: independent 3D viewer LEFT, 4-tab parameter column RIGHT (General / Inner / Middle / Outer profile).  Per-slider VARY ↔ FIXED ↔ PROPOSED state machine — moving a slider FIXES it (green); the system can spontaneously PROPOSE values (orange) when the Planner endorses an attempt.  FIXED values auto-append to the next chat message so downstream agents see them.  See **"Parameters Inputs view"** section below + `extra_utilities/web_interface_notes.md` for the full design. |
| **LOG and Status** | Live multi-agent flowchart + tailing of the current session log |
| **Questions for Saved Sessions** | Editable Database Handler schedule (see "DH schedule: three kinds of questions" below). Locked while a session is active. |
| **Workflow Settings** | Live editor over `workflow_settings/settings.py` (takes effect next session) + LLM-routing chart on top.  The LLM-routing chart hosts a per-agent **DBa** (Database access) toggle button — see `extra_utilities/warnings_developer.md` W33 for the per-agent flag + `RAG_ENABLED` master-switch semantics. |
| **Database** | Password-gated developer console (`PASSWORD_DATABASE_WEB_UI` env var).  Currently exposes a single destructive action: typing `reset_database` truncates every data table EXCEPT `dc_parameter_schemas`.  See W34. |

### Stop button

A red **Stop** button appears in the header while a turn is running. Clicking it flags the pipeline for **cooperative cancellation**: the currently-running step (LLM call, tool execution) completes normally, then the Orchestrator polls the shared stop flag (`agents/shared/stop_signal.py`) between hops and returns an interrupted message instead of continuing. The system then waits for the next user input. The flag auto-clears at the start of each new turn.

### LOG and Status view

A split pane: SVG flowchart on the left, live session log on the right (Server-Sent Events from `/api/log/stream`, dumps the full current-session log on open then tails new bytes).

**Layout.** The Orchestrator sits in the centre of the chart with open space around it. Each chain agent (UII, Planner, Input Creator, Input inspector, Tool Caller, Output inspector) lives in a fixed column; the two DC tool boxes (`Propeller Configurator` — the merged geometry+renders tool — and `Blade Sections`) sit on the right, next to the Tool Caller. The **EXTRA AGENTS** panel holds the **Database Handler** (lights up at End Session → Save while it interviews each agent for the post-session database) and the **Context Pruner** (lights up alongside whichever agent's history just exceeded the token threshold; see [Context Pruner](#context-pruner) below).

**Static black arrows** connect User ↔ Receptionist ↔ Orchestrator (the always-present top of the pipeline), UII → Planner → Input Creator → Input inspector → Tool Caller, and Tool Caller ↔ Output inspector / Propeller Configurator (the merged geometry+renders tool) / Blade Sections. These never change.

**Two dynamic gray arrows** around the Orchestrator visualise its most recent transition:

- `orch-caller-link` — from whichever non-Receptionist agent most recently called the Orchestrator, into Orch.
- `orch-callee-link` — from Orch out to whichever non-Receptionist agent it most recently handed off to.

Receptionist ↔ Orchestrator always uses the static black arrow, so the dynamic arrows stay hidden whenever Receptionist is the other side. At most one of the two dynamic arrows is visible at a time — the rules are summarised in `web/app.js:applyAgentActive`. *(See TODO F10 — the arrows are wired but the deployed build still needs a debug pass; they may not appear yet end-to-end.)*

**Live highlighting.** Every agent box lights up yellow ("strict transitions") between the moment another agent hands off to it and the moment it hands off to someone else. Utility tool calls do NOT change which agent is lit — the calling agent stays highlighted while it runs `calculate`, `read_extracted_inputs`, etc. The two DC tool boxes (Propeller Configurator, Blade Sections) are the exception: their boxes light up alongside Tool Caller while Tool Caller is waiting on them, because they represent real cross-process work.

**Generic helpers** — `read_user_inputs`, `write_extraction`, `read_extracted_inputs`, `new_attempt`, `write_parameters`, `read_parameters`, `view_images`, `calculate`, `visualize_3d_model`, etc. — complete in milliseconds and are too fast to flash. Each agent box therefore also carries a small **gray-italic caption below the box recording the most recent generic tool that agent invoked**. The caption persists across handoffs so the chart shows each agent's history at a glance; it wipes on End Session.

**Session log.** The right-hand pane streams `/api/log/stream` and now shows tool calls from **every** agent, including the Receptionist (`[TOOL CALL] Receptionist -> calculate ...`). The `[RECEPTIONIST] forward=...` line no longer echoes the message body — the full message is logged exactly once, by the routing tool, as `[AGENT MSG] Receptionist -> Orchestrator <message>`.

**End Session** wipes the chat, the LOG view, all agent highlights, all dynamic gray arrows, and all "last tool used" captions, and reopens a fresh session.

### Chat viewer footer

Below the 3D viewer in the Chat view sit two small buttons:

| Button | Behaviour |
|---|---|
| **Download geometry** | Disabled until a propeller mesh is loaded. Saves the currently displayed `.obj` via a programmatic `<a download>` click against the `/api/artefact` URL the viewer is already using. |
| **Copy parameters list** | Fetches `/api/parameters` and writes the response to `navigator.clipboard`. Falls back to a hidden-textarea + `document.execCommand("copy")` path for plain-HTTP contexts so it works on the local Docker URL too. Brief "Copied!" / "Copy failed" feedback. |

The `/api/parameters` endpoint currently serves the canonical 17-parameter reference list (`DC_prompt_fragments/dc_config/parameters.md`) as `{"text": "..."}`. *(See TODO F9 — once a mesh is on screen the endpoint should ideally return that attempt's actual `parameters.json` values instead of the generic reference list.)*

## Parameters Inputs view

Split-pane like the Chat view. **LEFT**: an independent 3D viewer instance (separate from the chat's — `viewer.js` refactored into a `Viewer` class in late v9 so two instances can coexist). **RIGHT**: a parameter column with 4 section tabs at the top — General Parameters / Inner Profile / Middle Profile / Outer Profile. Click a tab to show only that section's sliders + matching profile image; no scrolling through all 17.

**Per-slider state machine** — every slider row has a state button on its left:

| State | Visual | When |
|---|---|---|
| **VARY** | gray, "VARY" | default; the system can vary this parameter freely |
| **FIXED** | green, "FIXED" (pressed-in look) | the user has set it; the system MUST respect it |
| **PROPOSED** | orange, "PROPOSED" (not pressed) | the system has proposed a value via `propose_attempt`; the slider holds that value until the user accepts (clicks → FIXED) or over-rides (moves it → FIXED at new value) |

Moving any slider takes the row from VARY → FIXED at the slider's current visible value. Clicking a green FIXED button releases back to VARY but **keeps the visible value** as a hint. Every row that has ever received a PROPOSED value carries a small italic `PROPOSED VALUE: X` label on the right side of its name — this **persists even after the user takes ownership** so they always see the system's most recent suggestion as a reference point.

**Live 3D preview pipeline (front-end geometry / FEG).** The LEFT viewer's live preview is built **entirely in the browser** — no server round-trip. The propeller is generated in three.js from the current 17-param dict (`web/feg/*` — a faithful port of the standalone `propeller-browser` builder: NACA + camber morph per section, Lagrange-lofted blade `InstancedMesh`, swept-ellipse ring, placeholder hub) via `Viewer.loadFromParams(params)`. It auto-builds the moment the view opens and rebuilds live as you drag (coalesced with `requestAnimationFrame`, so a fast drag rebuilds at most once per frame). This is the **FEG** — a fast, disposable approximation; the viewer toolbar reads "3D preview (approximate)" to make that explicit. Below the LEFT viewer, the **Download geometry** button is the only path that touches the server: it POSTs the current params to `/api/preview_mesh` and downloads the precise **RhinoCompute geometry (RCG)** OBJ as `propeller.obj` (fetch-on-click with a brief "Generating…" status). The chat view's viewer is unaffected — it shows the RCG end-to-end as before.

**FIXED + RELEASED auto-append on chat.** Every `/api/turn` body carries an optional `fixed_params` dict (when the FIXED list has changed since the previous send) and an optional `released_params` list (when the user has just released previously-FIXED parameters). `save_user_input` appends two blocks under each turn's timestamp header in `user_query.txt`:

```
The user has fixed the following values through the Parameters Inputs interface:
  - bladeCount: 4
  - impellerRadius: 72 mm
  - innerCamber: 5 % of chord

The user is no longer constraining the following parameters (they can now be varied freely by the system):
  - outerThickness
```

All downstream agents (Receptionist, UII via `read_user_inputs`, Planner via `read_user_queries`) see both blocks for free — no per-agent code change. Dedup by full fingerprint (names AND values); an unchanged FIXED list does not re-append. Empty FIXED list appends nothing.

**Bottom-row action buttons** (visible regardless of active tab):

- **Copy parameters** — clipboard, long-form list with units, for paste elsewhere.
- **Use these parameters** — sets ALL rows to FIXED and posts a short chat message (the real parameter dict reaches the agents via the auto-append above).

**Spontaneous PROPOSED.** The Receptionist's `propose_attempt` tool fires automatically when the Planner's APPROVE-branch hand-off endorses the surfaced attempt in plain prose (no fixed marker required — see `extra_utilities/warnings_developer.md` W22 for the natural-language convention rule). Phrases like *"recommend attempt N as the satisfying solution"*, *"best attempt so far"*, *"final pick"* trigger the call; hedging phrases like *"showing for context"*, *"intermediate result"*, *"first cut, still revising"* suppress it. The panel is sticky on the most recent endorsed proposal — informational user requests like *"show me the worst"* update the chat 3D viewer but never touch the Parameters Inputs panel.

**End Session** wipes the Parameters Inputs panel state (`paramsResetAll()` in `web/app.js`) alongside the chat: all rows reset to gray VARY at mid-of-range defaults, PROPOSED text cleared, LEFT viewer unloads, Download geometry disabled, FIXED-dispatch dedup snapshot cleared so the next session's first chat send carries a fresh FIXED block if applicable.

Full design + decisions log: [`extra_utilities/web_interface_notes.md`](extra_utilities/web_interface_notes.md).

## Architecture: how live activity reaches the browser

The LOG and Status view, the live 3D viewer, and the per-agent "last tool used" captions are all driven by a single in-process pub-sub channel, with two SSE endpoints flushing events out to the browser. No agent code ever reaches into the web layer (per `warnings_developer.md` W17).

### The publish/subscribe seam (`agents/shared/viz_bus.py`)

Framework-agnostic by design — agent code calls `publish(event)`, the web layer calls `subscribe()` to get a per-connection event queue. When no subscriber is listening (REPL / Streamlit / tests), `publish` is a no-op. The bus accepts arbitrary dicts; the convention is a `type` field that the web layer routes on.

Five event types are in use today:

- `{type: "visualize", path, name}` — published by `tools/visualize_model/visualize_model.py:visualize_3d_model`. Tells the viewer to load a new mesh inline as soon as the agent invokes the tool, without waiting for end-of-turn.
- `{type: "agent_active", from, to, note}` — published from `agents/shared/trace.py:trace()` on every agent-to-agent handoff and (via the `@tool_active` decorator) on DC-tool entry / exit. Drives the highlight class on the flowchart.
- `{type: "generic_tool", name, state, agent}` — published from `agents/shared/agent_activity.py:generic_tool` on entry/exit. `agent` is the display name of the agent currently in flight (from `trace.get_current_agent()`); the frontend binds the "last tool used" caption to THAT box, so a dropped box-switch event can't mis-attribute it. Drives the caption only; never affects which agent is highlighted.
- `{type: "session_save_done", ok, saved, dh, feedback, error}` — published exactly once when the End Session background task finishes (success or failure). Frontend uses it to run the post-save UI cleanup (clear chat / viewer / images / log view) and re-enable the End Session button.
- `{type: "params_proposed", values}` — published by `agents/receptionist/propose_attempt_tool.py:propose_attempt` when the Receptionist decides the surfaced attempt is the system's current best / satisfying recommendation (interprets the Planner's APPROVE-branch wording — endorsement vs. hedging). Drives the Parameters Inputs view's PROPOSED state update: non-FIXED sliders turn orange + every row gets a `PROPOSED VALUE: X` text label. See `extra_utilities/warnings_developer.md` W22 for the natural-language convention.

### The decorators (`agents/shared/agent_activity.py`)

Two wrappers, applied beside each tool's existing `@tool` decorator:

- `@tool_active("Display Name")` — for the tools that have their own boxes: Propeller Configurator (`generate_and_render_propeller`, which builds the geometry AND its renders in one call) and Blade Sections (`render_blade_sections`). Calls `trace()` on entry **and** exit, so the tool's box stays lit alongside the Tool Caller while the tool runs and unlights cleanly when it returns.
- `@generic_tool("Display Name")` — for every other utility tool (read_user_inputs, list_attempts, calculate, etc.). Publishes only the lighter-weight `generic_tool` event. Intentionally NOT routed through `trace()` so it doesn't pollute the agent-flow trace file with every tiny internal helper call.

The two decorators between them cover ~17 tool functions across `tools/`, `agents/shared/`, and per-agent files. See TODO F8 for the planned consolidation of generic helpers under `tools/generic/`.

### Trace publish flag (`agents/shared/trace.py:trace`)

`trace(from_agent, to_agent, note="", *, publish=True)` writes one line to the agent-flow file AND publishes an `agent_active` event. Pass `publish=False` from callers that need the file line but NOT the SSE event — specifically `agents/shared/routing_tools.py:log_tool_call`, which logs `[TOOL CALL]` lines whose `to` is a tool function name (not a real agent); without the flag those events would inject bogus `agent_active` messages into the flowchart and wipe the live highlight on the actual calling agent.

### SSE endpoints (`web_app.py`)

Two endpoints flush viz_bus events to the browser:

- `GET /api/events` — long-lived stream that forwards `visualize`, `agent_active`, and `generic_tool` events as Server-Sent Events. The frontend's single EventSource subscribes once at app start and stays connected across view switches.
- `GET /api/log/stream` — long-lived stream that opens the current-session log file, dumps its full contents on connect, then tails new bytes as they're written. Hot-swaps to a fresh file when End Session triggers a new session.

A few one-shot endpoints round out the surface:

- `POST /api/stop` — sets the cooperative-cancellation flag in `agents/shared/stop_signal.py`. Polled today only at Orchestrator hop boundaries (see TODO F11 for the planned tighter cancellation).
- `GET /api/parameters` — serves the canonical parameter list for the Copy parameters list button (see above and TODO F9).
- `GET /api/artefact?path=...` — sandboxed read of any `.png` / `.obj` produced this session, scoped to `ATTEMPTS_DIR`. Used for both inline render display and the Download geometry button.
- `POST /api/preview_mesh` — generates a propeller mesh on demand from a 17-parameter dict and returns it as OBJ bytes (the **RCG**). Backs the Parameters Inputs view's **Download geometry** button (the live preview itself is now the in-browser FEG and does NOT call this route). Validates the dict's keys / ranges / integer-typed params; calls the pure `render_mesh_obj_text` helper that's also used internally by the agent path's `generate_and_render_propeller` tool. Bypasses the agent pipeline entirely — a download does NOT create attempt folders, does NOT trigger any chain agent, does NOT show up in the LOG view. Memoised via `lru_cache(maxsize=64)`; identical parameter dicts return cached OBJ bytes instantly.

### Frontend dispatch (`web/app.js`)

A single SSE handler in `startEventStream()` routes incoming events to either the viewer (`visualize`), the flowchart (`agent_active` → `applyAgentActive`), or the per-agent caption (`generic_tool` → `recordToolUsedByActiveAgent`). The strict-transitions highlighting policy lives entirely in `applyAgentActive`: at most one agent box is lit at a time, except during a DC-tool call where both the agent and the tool box are highlighted together.

## Context Pruner

Long multi-attempt sessions accumulate messages and (with `KEEP_IMAGES_IN_CONTEXT=True`) image content blocks across every agent's history. Once a single agent's history crosses the configured token threshold its next LLM invoke would either be wasteful or, in the worst case, exceed the provider's context window. The **Context Pruner** is a stateless agent (`agents/shared/context_pruner.py`) that condenses the older portion of any chain agent's history into a `SystemMessage` block before the next invoke. The Pruner uses a **three-tier escalation** so a single pruning pass that's not enough still gets the agent under threshold without losing essential information.

### How it fires

Every chain agent (Receptionist, Orchestrator, UII, Planner, DCIC, DCII, DCOI, Tool Caller) calls `self.prune_history_if_needed()` at the top of its invoke loop, in `agents/shared/base_chain_agent.py`. The check:

1. **Gated by** `CONTEXT_PRUNER_ENABLED` (default `True`).
2. **Triggered** when `count_tokens(self.messages) + count_tokens(self.system_prompt)` exceeds a per-agent threshold derived from the context window of the model *that agent* runs on: `max(MIN, min(WINDOW_FRACTION × window, MAX))` — defaults `0.60`, `150,000`, `20,000`. Counting the system prompt means the threshold is total context sent, not history alone. Windows come from `agents/shared/model_windows.py` (Anthropic Models API when reachable, else a verified static table; unknown models fall back to the smallest window in use). Below the threshold nothing happens.
3. **Cut point** is computed as `len(self.messages) - CONTEXT_PRUNER_KEEP_LAST_MESSAGES` (default 6), then advanced forward via `_safe_cut_point` so a `ToolMessage` is never separated from its matching `AIMessage(tool_calls=...)` — tool-call pairs are always pruned or kept as a unit.

The Database Handler is intentionally NOT pruned — it iterates ~28 schedule entries per save and relies on accumulated state.

### Three-tier escalation

After the cut is decided, the Pruner runs up to three passes. Each tier RE-CHECKS the token count and only escalates when the previous tier didn't get under threshold.

**Tier 1 — coarse summary** (`COARSE_SUMMARY_PROMPT`). The prefix (everything before the latest `keep_n` messages) is serialised to plain text (`USER:`/`ASSISTANT:`/`TOOL_RESULT:` lines; image content blocks become `[image: redacted for pruning]` placeholders so they don't waste pruner tokens) and handed to `ContextPruner.run(prefix_text, tier=1)`. The prompt tells the model what to REMOVE (old render descriptions, superseded user requests, verbose tool outputs), KEEP (current design requirements, decisions, latest assessment, unresolved issues), and SUMMARISE (multi-attempt fix loops, long tool outputs). Result replaces the prefix: `self.messages = [SystemMessage(summary1)] + tail`. The latest `keep_n` messages survive verbatim. *(If after this the history is under threshold, the Pruner stops here. Most cases stop here.)*

**Tier 2 — fine summary** (`FINE_SUMMARY_PROMPT`). When tier 1's replacement is not enough, the still-verbatim tail (the latest `keep_n` messages) is also summarised — through a SEPARATE, more PRECISE prompt that asks the LLM to retain specific values, attempt numbers, last decisions, and last errors verbatim (only condensing verbose framing). Result: `self.messages = [SystemMessage(summary1), SystemMessage(summary2)]`. No verbatim messages remain. Tool-call pairing is vacuous from here on because there are no `AIMessage` / `ToolMessage` instances left.

**Tier 3 — ultra-compact super-summary** (`ULTRA_COMPACT_SUMMARY_PROMPT`). When tiers 1+2 together still leave the history over threshold, the two summaries are concatenated and merged into ONE super-summary. The prompt strips everything except (1) the current design state, (2) the current task / pending question, (3) the single most-critical decision, (4) the single most-recent unresolved issue. Result: `self.messages = [SystemMessage(super_summary)]` — one terse `SystemMessage` total.

### Safety nets

Each tier independently validates its output before replacing `self.messages`:

- **Empty summary** → log a warning, stay at the previous tier's state.
- **Summary larger than the input it would replace** (the LLM expanded instead of condensed) → log a warning, REJECT the replacement, stay at the previous tier.
- **LLM exception** → log a warning, stay at the previous tier.
- **All three tiers exhausted and the history is still over threshold** → log a warning and proceed with the invoke anyway; the upstream LLM may rate-limit or context-overflow, but the agent doesn't lose its state.

### Pre-scan and tier-2 input cap (defences against giant single messages)

A specific failure mode that the three-tier escalation alone cannot recover from: ONE message in the history is so large that the Pruner's OWN LLM call would exceed the upstream provider's per-request token cap. For example, a `ToolMessage` containing a 1 MB inline `.obj` mesh dump is ~333k tokens — bigger than most providers' single-call input limit of 100k–200k. Sending that one message to the Pruner's LLM returns HTTP 429 ("Request too large for `<model>` in organisation ... TPM limit ...") before the LLM does any work. Tier 1 can't help because the giant message is in the tail (latest-N verbatim); tier 2 can't help because tier 2 IS the thing whose LLM call fails; tier 3 can't help because it merges tier-1 + tier-2 summaries and there's no tier-2 summary to merge. So two extra defences run AHEAD of the three-tier flow:

- **Pre-scan** (runs BEFORE the threshold check). Walks `self.messages` and, for every single message whose serialised content exceeds `CONTEXT_PRUNER_MAX_INDIVIDUAL_MESSAGE_TOKENS` (default 30 000), replaces it in-place with a placeholder of the same message type. `ToolMessage` placeholders preserve `tool_call_id` and `name`; `AIMessage` placeholders preserve `tool_calls`; the agent's protocol contract is not broken. The placeholder body is the first 2 000 characters of the original content with a `[content auto-truncated by Context Pruner pre-scan: original was N chars (~M tokens) ...]` marker. The lost bytes are gone from chat context, but the message structure remains and downstream tool-call pairing still closes.
- **Tier-2 input cap** (runs inside tier 2). Even after the pre-scan, the SUM of the latest-N tail messages could still exceed the upstream provider's per-call cap. So before invoking `pruner.run(tail_text, tier=2)`, if `count_tokens(tail_text) > CONTEXT_PRUNER_TIER2_INPUT_CAP_TOKENS` (default 60 000), the text is hard-truncated by character ratio with a `...[tail truncated to honour Context Pruner tier-2 LLM input cap]` marker. The summary won't see the dropped portion but the LLM call SUCCEEDS.

Tools also defend at the source: `read_attempt` no longer returns mesh files (`.obj` / `.stl` / `.ply`) as inline text — it returns the absolute path plus a hint to pass it to `visualize_3d_model`. That stops the most common path that fills chat history with hundreds of thousands of vertex-coordinate tokens.

### What stays untouched

Each agent's **original system prompt** lives in `self.system_prompt`, NOT in `self.messages`. The invoke pattern is:

```python
response = invoke_with_retry(
    self.llm,
    [make_system_message(self.system_prompt, self.provider)] + self.messages,
    "Receptionist",
)
```

The system prompt is rebuilt fresh at every invoke from the untouched `self.system_prompt` attribute, so pruning has no effect on it. The LLM sees the original system prompt, then ONE / TWO / or in tier 3 ONE summary `SystemMessage`(s), then any kept tail messages (tier 1 only). Anthropic / Google concatenate adjacent `SystemMessage` blocks into the single top-level system field of their respective APIs; OpenAI keeps them as separate `role: "system"` messages — all three handle this shape cleanly.

### Live feedback

While the Pruner runs, the LOG-and-Status chart highlights the **Context Pruner** box in the EXTRA AGENTS panel alongside the calling agent's box (same multi-active pattern as the two DC tools — see `applyAgentActive` and `TOOL_NAMES` in `web/app.js`). The matching exit handoff clears the CP box and leaves the caller solo-lit. The CP box stays lit through the whole escalation chain — entry / exit are published ONCE per `prune_history_if_needed` invocation, not per tier. Each tier emits its own `[CP] <agent_key> tier N: ...` line in the session log, e.g.:

```
[CP]  planner tier 1: pruned 42 -> 7 messages, ~95000 -> ~72000 tokens
[CP]  planner tier 2: tail summarised, ~72000 -> ~55000 tokens
```

…so an operator can watch which tier did the work.

## DH schedule: three kinds of questions

The DH schedule (edited via the **Questions for Saved Sessions** view, persisted as `workflow_settings/dh_schedule.json`) supports three kinds of rows:

| Kind | How it's flagged | Example | What the DH does |
|---|---|---|---|
| **Session-related** | `scope = session` (top-level row) | "What was the user's request?", "Did any agent flag an error?" | Interview Agent A, save Q+A to `.txt`. No attempt context. |
| **Identifying attempt-specific** | `scope = attempt` + `parent_id = null` (top-level) | "Which attempt best satisfied the user?", "Which attempt led to problems?" | Interview Agent A, **then forced to call `save_attempt_data`** to pin down which attempt. On success, save Q+A AND upload the attempt's artefacts. On failure, drop the whole block (this row + every Q(N).x sub-row). |
| **Attempt-specific sub-row** | `scope = attempt` + `parent_id = <identifying row's id>` | "Why was that attempt successful?", "What numerical parameters were used?" | Description is auto-prefixed with `"For attempt NNN: "` before the interview, so Agent A knows which attempt to answer about. Saved like any session row. |

The Q-number scheme reflects the structure: `Q1, Q2, Q2.1, Q2.2, Q3` means Q1 and Q3 are session-related, Q2 is identifying, Q2.1 / Q2.2 are sub-rows under Q2.

## Identifying attempt-specific questions — force-tool flow

When the DH reaches an identifying attempt-specific row, the system runs a 5-step protocol that's distinct from the normal ASK/SAVE loop:

1. **DH formulates** the question (e.g. "Which attempt best satisfied the user's request?") and the system delivers it to Agent A.
2. **Agent A replies** in plain prose.
3. **Force-tool turn**: the DH's LLM is bound with `tool_choice="save_attempt_data"` for this single turn. The DH MUST call the tool. Allowed inputs:
   - The attempt number Agent A named — `"002"`, `"2"`, `"attempt 002"`, an ordinal+`"attempt"`/`"iteration"`, or a full slug like `"20260530_142312_002_..."`. The system extracts the 3-digit number via `_normalise_attempt_input`.
   - The literal string `"none"` (case-insensitive) — when Agent A did NOT identify a specific attempt.
4. **System processes the tool call**:
   - On a valid number, `_resolve_attempt_folder` globs `attempts/*_NNN_*` filtered to folders created during this session (`mtime >= session_ts`). Multiple matches → most recent. Zero matches → ToolMessage with an error and the DH retries.
   - On a successful resolve, `r2_uploader.upload_attempt_artefacts` pushes `parameters.json` / `propeller_mesh.obj` / `render_*.png` / `description.txt` (whichever exist) to R2 under `<prefix>/<session_id>/attempts/<NNN>/<session_id>__<NNN>__<original_name>`. `propeller_mesh_components.obj` is **explicitly excluded**.
   - On `"none"`, the ToolMessage records `{ok: true, attempt_id: null}` and the system drops the whole block.
   - The DH gets up to **3 retries** to land a valid call (invalid input, or number that resolved to no folder). After 3, the system synthesises `"none"` and drops the block.
5. **DH continues normally**: if the tool succeeded with a real attempt, the DH emits SAVE: with QUESTION:/ANSWER: as for any SEMANTIC field; the ToolMessage payload is part of the DH's context so the answer naturally references the resolved attempt. If the tool resolved to "none" or 3-failures, the SAVE step is **skipped entirely** — no .txt is written for this row, no placeholders for its children.

The tool is bound **only** for the force-tool turn — not for the SAVE: emit, not for any other row. The DH's prompt says so explicitly.

### Live feedback for the force-tool flow

The Database Handler box in the LOG-and-Status chart is lit yellow for the entire interview (same as today). The force-tool round-trips don't add chart events — they're internal DH plumbing. The session log captures every step: `[DH] starting conversation … (identifying=True)`, then `[DH] force-tool attempt k SUCCEEDED for <agent>/<field>: attempt NNN; uploaded=[...] missing=[...]`, then `[R2] uploaded …` lines for each artefact.

### User inputs (text + reference images) also land in the database

Right before the R2 mirror runs, the DH copies the session's user-side artefacts into a new `<session_dir>/user_inputs/` branch:

* `queries.txt` — the **complete** turn-by-turn collection of user text inputs. Sourced from `inputs/user_query.txt`, which the dispatcher appends to on every `/api/turn` call with a `--- [YYYY-MM-DD HH:MM:SS] ---` timestamped header, so every user message issued during the session is preserved.
* `images/<original_name>` — every reference image the user uploaded via the Image Inputs view, plus its matching `<name>_note.txt` description sidecar (original filenames preserved so each image stays paired with its note).

The R2 upload step's suffix whitelist now covers `.txt`, `.png`, `.jpg`, and `.jpeg`, so the user-inputs branch flows through to the bucket alongside the per-agent answer files. Final R2 layout per session:

```
<R2_KEY_PREFIX>/<session_id>/
├── receptionist/
│   ├── user_query_problem.txt
│   └── ...
├── orchestrator/session_summary.txt
├── ... (one folder per agent)
├── attempts/
│   └── <NNN>/                              # only when an identifying-Q
│       ├── <session_id>__<NNN>__parameters.json
│       ├── <session_id>__<NNN>__propeller_mesh.obj
│       ├── <session_id>__<NNN>__render_isometric.png
│       └── <session_id>__<NNN>__description.txt
└── user_inputs/
    ├── queries.txt                          # all user turns, chronological
    └── images/
        ├── reference_blade.png
        ├── reference_blade_note.txt
        └── ...
```

The local `inputs/` folder is left untouched by this step — End Session's archival sweep moves it into `previous_sessions/<session_id>/inputs/` as before. The copy under `database/<session_id>/user_inputs/` is the database-layout duplicate, intended for the future RAG layer.

## Cloudflare R2 layout — how the three upload paths combine

The save flow writes to R2 via **three distinct upload paths** that run at different points and target **disjoint** parts of the per-session key space. Understanding which is which makes it easy to reason about what shows up in the bucket and why.

### Path 1 — Per-attempt artefacts (during the force-tool turn)

Site: `agents/database_handler/database_handler.py:_run_force_tool_phase`. Fires once per resolved attempt id, **immediately** when the force-tool's `save_attempt_data` tool call succeeds — long before the DH emits its SAVE: body.

Calls `r2_uploader.upload_attempt_artefacts(folder, session_id=…, attempt_id=NNN, global_attempt_id=<bigserial>)` per resolved NNN. Whitelisted files (from `agents/shared/r2_uploader.py:ATTEMPT_ARTEFACT_WHITELIST`): `parameters.json`, `propeller_mesh.obj`, `render_isometric.png`, `render_top.png`, `render_side.png`, `description.txt`. `propeller_mesh_components.obj` is intentionally excluded.

Keys written (Phase 5A shape, 2026-06-03 onward):

```
<R2_KEY_PREFIX>/<session_id>/attempts/<NNN>__<global_id>/<original_filename>
```

The `attempts/` subfolder encodes both the per-session `NNN` (first, for chronological sort within a session) and the Postgres `dc_attempts.attempt_id` (after the `__` separator). Filenames stay as the originals — no `<sid>__<NNN>__` rename, because the folder already disambiguates. Pre-Phase-5A R2 keys retain the old `attempts/<NNN>/<sid>__<NNN>__<original>` shape; no historical migration is run. See W30 + `retrieve_attempt` design in the architecture doc.

### Path 2 — End-of-save mirror of `database/<session_id>/`

Site: `populate_database` at the end of the per-row write loop, after `_collect_user_inputs` has copied user inputs into `database/<session_id>/user_inputs/`.

Calls `r2_uploader.upload_directory(session_dir, remote_prefix=f"{session_id}/", suffixes=(".txt", ".png", ".jpg", ".jpeg"))`. Walks `database/<session_id>/` and uploads every file whose suffix is in the whitelist.

Keys written:

```
<R2_KEY_PREFIX>/<session_id>/<agent>/<field>.txt                       (per-agent answer)
<R2_KEY_PREFIX>/<session_id>/<agent>/<field>__<NNN>.txt                (sub-row, multi-attempt)
<R2_KEY_PREFIX>/<session_id>/<agent>/<field>_<idx>.txt                 (multi-answer split)
<R2_KEY_PREFIX>/<session_id>/user_inputs/queries.txt
<R2_KEY_PREFIX>/<session_id>/user_inputs/images/<name>.png
<R2_KEY_PREFIX>/<session_id>/user_inputs/images/<name>_note.txt
```

### Path 3 — Session-generic logs (during archive sweep)

Site: `agents/loader.py:_archive_previous_session`, immediately after the three `shutil.move` loops that relocate `*.log`, `agent_flow_*.txt`, and `dh_flow_*.txt` into `previous_sessions/<sid>/`.

Iterates the moved-into-place files and the `agent_histories/<file>.json` siblings, calling `r2_uploader.upload_file(path, key)` for each. Best-effort — an R2 failure logs a warning but never breaks the archive sweep.

Keys written (Phase 5A shape, 2026-06-03 onward):

```
<R2_KEY_PREFIX>/<session_id>/logs/session.log
<R2_KEY_PREFIX>/<session_id>/logs/database_handler_<ts>.log
<R2_KEY_PREFIX>/<session_id>/logs/agent_flow_<ts>.txt
<R2_KEY_PREFIX>/<session_id>/logs/dh_flow_<ts>.txt
<R2_KEY_PREFIX>/<session_id>/logs/agent_histories/history_<agent>.txt
```

The main session log's local filename is `<session_id>.log` — the archive sweep renames it on upload only (to drop the duplicated `<session_id>` from the key) so the R2 key is `<session_id>/logs/session.log` instead of `<session_id>/logs/<session_id>.log`. The other three log/trace files use timestamp-based names and pass through unchanged. Pre-Phase-5A keys retain the duplicated shape. See W30.

### Why the three paths can't double-upload

The local `database/<session_id>/` folder **does NOT contain an `attempts/` subtree** — `_collect_user_inputs` only writes `user_inputs/`, and `populate_database` only writes `<agent>/`. Path 3's `<sid>/logs/` prefix is disjoint from both `<sid>/attempts/<NNN>/...` (Path 1) and `<sid>/<agent>/...` + `<sid>/user_inputs/...` (Path 2). So all three target disjoint key prefixes. This is a load-bearing invariant — see `extra_utilities/warnings_developer.md` W19.

### What is NOT in R2

* **Sidecar `.meta.json` files** next to every `.txt`. The suffix whitelist is `.txt` / `.png` / `.jpg` / `.jpeg` — `.json` is excluded deliberately so the per-question access-control metadata (`to_agents` etc.) doesn't pollute the embedding stream. The sidecars remain local under `database/<session_id>/<agent>/<field>.meta.json` and travel into the End Session archive as part of the rest of the save tree.
* **Local `attempts/<slug>/` working folder.** The attempt artefacts upload through Path 1 with the rename pattern; the original folder names (`20260530_142312_002_descriptor`) only exist in the local filesystem and the End Session archive.
* **`current_plan.txt`.** Not a log — the Planner's working scratch. Travels into the End Session archive but does NOT get mirrored to R2.

### Behaviour when R2 is not configured

Both paths gate on `r2_uploader.is_enabled()` (all four required env vars present: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`). When not configured, both paths log one warning and no-op cleanly. The DH save runs to completion locally; R2 stays untouched. Same shape on save=False (no DH run, no R2 fire either way).

### Known small inconsistencies

Three minor edges flagged for follow-up — none affect correctness in the happy path, but they're documented as TODO items so they don't drift:

* **F19** — Same attempt referenced by N identifying-Q rows triggers N R2 PUTs of identical bytes (idempotent overwrites; wasteful, not incorrect).
* **F20** — Orphan artefacts possible if `_run_identifying_conversation` raises **after** the force-tool upload but before the SAVE step. R2 would have the artefacts, local `database/<sid>/` would have no `.txt` referencing them.
* **F21** — `r2_uploader._client()` constructs a fresh `boto3.client("s3", …)` per file. Minor perf overhead (40–60 client constructions per typical save); not a correctness issue.

## Configuration

All runtime flags live in [`workflow_settings/settings.py`](workflow_settings/settings.py):

| Flag | Default | Notes |
|---|---|---|
| `MESH_CHECKS` | `False` | watertight / volume / degenerate-face checks |
| `RENDER_LIBRARY` | `"trimesh"` | `"trimesh"` or `"pyvista"` metric backend |
| `RAG_ENABLED` | `True` | Master switch for the `database_search` tool (Phase 4).  When `True`, the 8 chain agents get `database_search` bound at session start AND the `$database_search_tool` fragment in their system prompts — *subject to* the per-agent DBa flag in `workflow_settings/database_access.json` (AND semantics).  When `False`, no agent gets database access regardless of any per-agent flag.  Per-agent flags are edited via the **DBa** toggle button on each agent box in the LLM-routing chart.  See `warnings_developer.md` W33 for the full lifecycle + filter mechanism. |
| `DC_INSPECTOR_ENABLED` | `True` | run DCII before mesh generation |
| `CHAIN_ACCESS` | `True` | Orchestrator sees inter-agent chain messages |
| `KEEP_IMAGES_IN_CONTEXT` | `False` | image bytes persist across hand-offs |
| `RATE_LIMIT_ENABLED` | `True` | throttle every `llm.invoke()` |
| `RATE_LIMIT_REQUESTS_PER_SECOND` | `1.0` | steady-state call rate |
| `DCOI_COMPARISON_MODE` | `3` | 1=user inputs, 2=extraction, 3=both |
| `PLANNER_FIRST` | `False` | True = Planner runs before UII |
| `EMBEDDING_MODEL` | `"text-embedding-3-large"` | for DH-shaped Semantic bodies |
| `EMBEDDING_VECTOR_DIMS` | `1024` | MRL truncation dim at index time |
| `EMBEDDING_MAX_RESPONSE_TOKENS` | `700` | DH cap for Semantic bodies |
| `LLM_ROUTING_MODE` | `"openai"` | `"individual"` honours per-agent `.env` overrides; `"openai"` / `"anthropic"` / `"google"` forces every agent onto that provider. Edit only via the LLM-routing chart at the top of Workflow Settings. **The chart's read path parses `settings.py` freshly off disk** on every `/api/llm-routing` GET — do not reintroduce `getattr(_settings, "LLM_ROUTING_MODE", …)` in `workflow_settings/llm_routing.py`; that read the cached module attribute frozen at process startup and made saves silently revert in the UI. |
| `CONTEXT_PRUNER_ENABLED` | `True` | run the Context Pruner pre-invoke check on each chain agent |
| `CONTEXT_PRUNER_WINDOW_FRACTION` | `0.60` | share of the agent's model context window at which pruning fires (binds on small-window models, e.g. 200k × 0.60 = 120k) |
| `CONTEXT_PRUNER_MAX_THRESHOLD_TOKENS` | `150000` | absolute cap on that threshold — governs on 1M-window models, where a pure fraction would let ~600k of history accumulate |
| `CONTEXT_PRUNER_MIN_THRESHOLD_TOKENS` | `20000` | absolute floor, so a small/unknown window cannot produce a threshold that prunes constantly |
| `CONTEXT_PRUNER_THRESHOLD_TOKENS` | `80000` | **deprecated** — superseded by the three settings above; retained so saved profiles keep loading |
| `CONTEXT_PRUNER_KEEP_LAST_MESSAGES` | `6` | how many recent messages of the calling agent survive the tier-1 prune verbatim (cut point is extended forward to never split an `AIMessage(tool_calls)` from its `ToolMessage`).  Same N is used to define the tier-2 scope (the "latest window" the fine summary covers). |
| `CONTEXT_PRUNER_MAX_INDIVIDUAL_MESSAGE_TOKENS` | `30000` | per-message hard cap for the Context Pruner's pre-scan.  Any single message whose serialised content exceeds this many cl100k_base tokens is replaced in-place with a short placeholder of the same message type (`tool_call_id` / `tool_calls` / `name` fields preserved).  Runs BEFORE the threshold check so the rest of the prune pipeline never sees a giant message.  `0` disables the pre-scan. |
| `CONTEXT_PRUNER_TIER2_INPUT_CAP_TOKENS` | `60000` | hard cap for the tier-2 LLM input.  When tier 2 fires, if the serialised tail exceeds this many tokens it is hard-truncated by character ratio before being sent to the Pruner's LLM, so the call cannot exceed the upstream provider's per-request TPM limit.  `0` disables the cap. |
| `DATABASE_ENTRY_MAX_RETRIES` | `3` | maximum attempts the Database Handler makes to INSERT a Q+A row into the Postgres `chunks` table when the insert fails (CHECK constraint violation, embedding-pipeline error, transient DB error).  On exhaustion the Q+A is written to the R2 safety folder for the session and skipped from the database.  See `extra_utilities/db_design/database_and_RAG_architecture.md` §3.5 for the safety-folder layout.  (Postgres backend is currently on hold mid-Phase-3B; this knob ships but is not yet exercised end-to-end.) |
| `STITCHING_PROVIDER` | `"OpenAI"` | LLM provider for the Database Handler's Option B paragraph-rewrite step (which becomes the input to the embedding model).  Currently OpenAI only; the architecture allows swapping to `"Anthropic"` / `"Google"` when the matching API key is set.  See architecture doc §6.1. |
| `STITCHING_MODEL` | `"gpt-4o-mini"` | Cheap model name for the rewrite step.  See architecture doc §6.1. |
| `UII_MAY_READ_PREVIOUS_EXTRACTION` | `True` | Whether the User Input Inspector receives the prior turn's `extracted_inputs.txt` as part of the `read_user_inputs` bundle.  Default `True` preserves historical behaviour; flip to `False` when you suspect the UII is carrying stale state forward despite the prompt's "do not copy lines forward" rule.  Gated in `agents/shared/file_utils.py:load_user_inputs_bundle` via the new `exclude_root_files` kwarg.  See the UII's prompt section "Temporal scope and Parameters Inputs interface blocks" for the full extraction contract. |
| `BLADE_SECTIONS_VISUALIZER_ENABLED` | `True` | Master switch for the `render_blade_sections` tool (Tool Caller only).  When `True`, the tool is bound and the whole workflow's prompts carry the capability fragments (`<<BSV_ON>>` regions — a brief awareness for every agent, full call usage for the Tool Caller, a read-by-path note for the DC Output Inspector).  When `False`, the tool is not bound and the prompts carry only the minimal "exists but OFF" note (`<<BSV_OFF>>`), so the system behaves exactly as before.  Read fresh per session via `workflow_settings/blade_sections_access.py`.  The tool renders the three blade cross-sections (Inner / Middle / Outer) stacked vertically as a PNG into the attempt folder (auto-displayed in chat, readable via `view_images`); a `grid=True` arg draws a 1 mm reference grid behind. |

## Status & known issues

- [`extra_utilities/TODO_known_issues.md`](extra_utilities/TODO_known_issues.md) — open issues (O1–O10) and future-work entries (F1–F28), including:
  - **F5 / F6** — colorising the log pane and showing tool-call payloads on the flowchart.
  - **F9** — make Copy parameters list return the selected attempt's actual `parameters.json` instead of the canonical reference list.
  - **F10** — the dynamic gray arrows around the Orchestrator are wired but need a deployed-build debug pass.
  - **F11** — tighten the Stop button to cancel at the next tool call / message / LLM call boundary instead of only at Orchestrator hop boundaries; tool calls issued after Stop is pressed should not execute.
  - **F24** — RESOLVED.  Live 3D preview in the Parameters Inputs view (Phase 3 of the redesign — see "Parameters Inputs view" above).
  - **F25 / F26 / F27 / F28** — post-redesign polish items: pre-compute the active FIXED set in Python (instead of UII's in-prompt walk); verify Planner behaviour in non-happy-path cases; live-preview ON/OFF toggle; `sessionStorage` persistence of panel state across reload.  All open as low-priority exploration items, none committed to being implemented.
- [`extra_utilities/warnings_developer.md`](extra_utilities/warnings_developer.md) — load-bearing invariants (W1–W35) that must not regress.  W18 + W20 are the per-turn force-tool pattern (DH's `save_attempt_data`; Orchestrator's `submit_feedback_dispatch`).  W19 is the disjoint-R2-key-namespace invariant for the upload paths.  **W21** is the "empty `to_agents` in the DH schedule means all primary agents, NOT no agents" rule (Postgres ingest contract).  **W22** is the natural-language convention for the spontaneous `propose_attempt` mechanism — Receptionist's LLM interprets the Planner's APPROVE-branch wording; endorsement vocabulary in Receptionist / Planner / `DC_prompt_fragments/tools_config/propose_attempt.md` MUST stay consistent.  **W30 / W33 / W35** govern the RAG / retrieve_* stack — Phase-5A R2 attempt key shape, per-agent DBa gating, and the dispatcher pattern that lets retrieve_* tool calls deliver both XML and image content blocks.
- [`extra_utilities/web_interface_notes.md`](extra_utilities/web_interface_notes.md) — full design + locked-decisions log for the Parameters Inputs redesign (§§1–8) plus a closing wrap-up (§9) describing the delivered state as of 2026-06-02.

## Roadmap

Near-term direction:

- Stage B: persist sessions and embeddings to Postgres, push binary artefacts to R2.
- Reorganise tools — split generic helpers from DC-specific tools and consolidate under `tools/` (see TODO F8) — so the `@generic_tool` decorator only needs to live at the `@tool` site instead of being duplicated on each agent's `_handle_*` handler method.
- Close out the LOG and Status open items above (F5, F6, F9, F10, F11).
- F30 — extend `retrieve_attempt` so the calling agent can pick render views per call (today's view set is a developer-time choice via three workflow flags).  See `extra_utilities/TODO_known_issues.md` F30.

**Done since v7:**

- Move heavy compute off the local driver — RhinoCompute now runs on an Azure VM, the Stage A FastAPI app runs on Railway.
- Build a web interface as the user-facing front-end — FastAPI + plain JS, see [Web UI](#web-ui) above.
- LOG and Status view live, with strict-transitions highlighting, dynamic Orchestrator caller/callee arrows, per-agent "last tool used" captions, and live session log tailing.
- Stop button with cooperative pipeline cancellation between hops.
- Chat viewer footer (Download geometry + Copy parameters list).
- Receptionist tool calls now appear in the session log alongside every other agent; `[RECEPTIONIST]` no longer duplicates the forwarded message body.
- **Context Pruner** wired into every chain agent's pre-invoke hook (see [Context Pruner](#context-pruner) below). F7 closed.
- **Database Handler save flow + R2 mirror** (3 disjoint upload paths: per-attempt artefacts, per-agent .txt + user inputs, session-generic logs + agent_histories).
- **LLM routing chart** at the top of Workflow Settings, with default = `"openai"` (every agent uses OpenAI unless explicitly overridden per-agent).
- **End Session is async** — `/api/end` returns HTTP 202 immediately, work runs in a background asyncio task, completion fires `session_save_done` on `/api/events` SSE. Eliminates the proxy-timeout duplicate-save race.  Singleton-guarded by a module-level `_END_IN_FLIGHT` bool; second POST while one is in flight gets HTTP 409.
- **In-app End Session modal** (replaces `window.confirm`).  Step 1: Yes / No / Cancel.  Step 2 (on Yes): Y/Partial/N satisfaction toggle + two optional free-text fields.  Feedback submitted with the save.
- **Orchestrator Role 4 — end-of-session feedback distribution.**  When the user supplies feedback, the Orchestrator distributes per-agent slices via a forced `submit_feedback_dispatch` tool call.  Each chain agent receives a single `HumanMessage(name="orchestrator")` in its history with only the feedback parts relevant to its scope — visible to the Database Handler when it interviews each agent post-session.
- **Per-attempt UI labels** — image renders in chat carry an "Attempt NNN" heading; the 3D viewer toolbar shows a matching badge.
- **Parameters Inputs view redesign** (2026-06 multi-step rollout, commits `f378ba7` → `fcb9ab6`).  Replaces the previous "coming soon" placeholder with a working split-pane view: independent 3D viewer LEFT, tabbed parameter column RIGHT, per-slider VARY ↔ FIXED ↔ PROPOSED state machine, live preview via `/api/preview_mesh`, FIXED/RELEASED block auto-append on every chat send so downstream agents see user constraints without any per-agent code change, and a spontaneous `propose_attempt` mechanism driven by the Planner's natural-language endorsement (no fixed marker phrase required — see W22).  `viewer.js` refactored to a `Viewer` class so the params view can host its own 3D instance alongside the chat's.  UII prompt rewritten to handle the new auto-appended blocks correctly (no more stale `(unlocked by user)` annotations).  Planner and Receptionist prompts gain rules for when to consult prior attempts and when to fire `propose_attempt` spontaneously.  Full design + chronology + delivered-state walkthrough in [`extra_utilities/web_interface_notes.md`](extra_utilities/web_interface_notes.md).
- **Phase 4 — `database_search` tool** (2026-06-03).  Closure-factory `@tool` bound to the 8 chain agents (DH skipped — write-only post-session).  Window-function dedup over a `DATABASE_SEARCH_CANDIDATE_POOL_MAGNIFIER × N` candidate pool (default 10), invariant-8 prefix locked in a single helper (`tools/database_search/database_search.py::_invariant_8_where_fragment`), per-row ACL via `chunks.agents_to[]`, embedding-model mismatch skip, token-cap trim, structured error envelope, best-effort `rag_queries` logging.  26-assertion live smoke test at `extra_utilities/db_design/smoke_test_database_search.py` passes against Railway.  See architecture doc §4 + §9.7 + §9.11 + `warnings_developer.md` W32.
- **Per-agent DBa toggle + `RAG_ENABLED` master switch** (2026-06-03).  Each chain-agent box on the LLM-routing chart now has a small "DBa" pill that decides whether that agent has `database_search` bound AND the `$database_search_tool` fragment in its prompt.  Persistent in `workflow_settings/database_access.json`; combined with `RAG_ENABLED` (now also a real master switch, default `True`) via AND semantics.  Conditional inclusion in templates uses a `<<HAS_DBA>>...<</HAS_DBA>>` filter applied per-agent at `_build_template` time.  See W33.
- **Database admin view** (2026-06-03).  New seventh side-menu view, password-gated by `PASSWORD_DATABASE_WEB_UI`.  Currently exposes one action: `TRUNCATE` every data table EXCEPT `dc_parameter_schemas` (preserves the 17-parameter schema seed; leaves the `session_counter` SEQUENCE alone — manual `ALTER SEQUENCE` via psql if you want IDNNN to restart).  See W34.
- **User-inputs R2 mirror fix** (2026-06-03).  Phase 3D's whole-`session_dir` upload with `.png/.jpg/.jpeg` whitelist had inadvertently stopped mirroring `queries.txt` and `*_note.txt` files under `<session_dir>/user_inputs/`.  Mirror re-scoped to that subdirectory with the full `.txt/.png/.jpg/.jpeg` whitelist; user text + image notes now reach R2 regardless of whether images were uploaded or any DH attempts were saved.  W30 updated.
- **Phase 5 — `retrieve_user_inputs` + `retrieve_attempt` tools** (2026-06-03+).  Two new DC-specific R2-backed retrieval tools complement `database_search` by letting agents pull a specific session's user inputs or a specific attempt's artefacts (description, parameters, renders) after `database_search` discovers candidate IDs.  Both tools share the same per-agent DBa gate as `database_search` (W33); image bytes are attached via a dispatcher pattern (`agents/shared/retrieve_tool_dispatcher.py`) mirroring the existing `view_images` plumbing — see W35.  Phase 5 also: bumped Postgres schema to v7 (`rag_queries` gains `tool_name` / `images_flag` columns + idempotent migration), reshaped the R2 attempt key to `attempts/<NNN>__<global_id>/<original_filename>` (forward-only — W30), extended `database_search`'s XML response with per-session `<available_attempts>` blocks + `global_id` on matched `<attempt>` elements, and added two new live smoke tests (`smoke_test_retrieve_{user_inputs,attempt}.py`).  Full narrative in architecture doc §9.13.
