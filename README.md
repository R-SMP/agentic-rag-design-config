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
├── web/                          # hand-written JS frontend (index.html, app.js, viewer.js, style.css)
├── Dockerfile  docker-compose.yml  # container build + local stack (matches Railway)
├── config.py                     # paths + RhinoCompute env vars
├── requirements.txt
├── requirements-web.txt          # FastAPI + uvicorn stack (web_app.py only)
├── workflow_settings/settings.py # 11 runtime flags (see Configuration)
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

The left rail switches between five views:

| View | Purpose |
|---|---|
| **Chat** | Conversational interface + inline 3D viewer for generated meshes |
| **Image Inputs** | Upload reference images, attach a `_note.txt` description per image |
| **Parameters Inputs** | (placeholder) future direct-edit form for the 17 design params |
| **LOG and Status** | Live multi-agent flowchart + tailing of the current session log |
| **Workflow Settings** | Live editor over `workflow_settings/settings.py` (takes effect next session) |

### Stop button

A red **Stop** button appears in the header while a turn is running. Clicking it flags the pipeline for **cooperative cancellation**: the currently-running step (LLM call, tool execution) completes normally, then the Orchestrator polls the shared stop flag (`agents/shared/stop_signal.py`) between hops and returns an interrupted message instead of continuing. The system then waits for the next user input. The flag auto-clears at the start of each new turn.

### LOG and Status view

A split pane: SVG flowchart on the left, live session log on the right (Server-Sent Events from `/api/log/stream`, dumps the full current-session log on open then tails new bytes).

**Layout.** The Orchestrator sits in the centre of the chart with open space around it. Each chain agent (UII, Planner, Input Creator, Input inspector, Tool Caller, Output inspector) lives in a fixed column; the two DC tool boxes (`Propeller Configurator`, `Visual Renderings generator`) sit on the right, next to the Tool Caller. The **EXTRA AGENTS** panel holds the **Database Handler** (lights up at End Session → Save while it interviews each agent for the post-session database) and the **Context Pruner** (lights up alongside whichever agent's history just exceeded the token threshold; see [Context Pruner](#context-pruner) below).

**Static black arrows** connect User ↔ Receptionist ↔ Orchestrator (the always-present top of the pipeline), UII → Planner → Input Creator → Input inspector → Tool Caller, and Tool Caller ↔ Output inspector / Propeller Configurator / Visual Renderings generator. These never change.

**Two dynamic gray arrows** around the Orchestrator visualise its most recent transition:

- `orch-caller-link` — from whichever non-Receptionist agent most recently called the Orchestrator, into Orch.
- `orch-callee-link` — from Orch out to whichever non-Receptionist agent it most recently handed off to.

Receptionist ↔ Orchestrator always uses the static black arrow, so the dynamic arrows stay hidden whenever Receptionist is the other side. At most one of the two dynamic arrows is visible at a time — the rules are summarised in `web/app.js:applyAgentActive`. *(See TODO F10 — the arrows are wired but the deployed build still needs a debug pass; they may not appear yet end-to-end.)*

**Live highlighting.** Every agent box lights up yellow ("strict transitions") between the moment another agent hands off to it and the moment it hands off to someone else. Utility tool calls do NOT change which agent is lit — the calling agent stays highlighted while it runs `calculate`, `read_extracted_inputs`, etc. The two DC tools (Propeller Configurator, Visual Renderings generator) are the exception: their boxes light up alongside Tool Caller while Tool Caller is waiting on them, because they represent real cross-process work.

**Generic helpers** — `read_user_inputs`, `write_extraction`, `read_extracted_inputs`, `new_attempt`, `write_parameters`, `read_parameters`, `load_render_images`, `calculate`, `visualize_3d_model`, etc. — complete in milliseconds and are too fast to flash. Each agent box therefore also carries a small **gray-italic caption below the box recording the most recent generic tool that agent invoked**. The caption persists across handoffs so the chart shows each agent's history at a glance; it wipes on End Session.

**Session log.** The right-hand pane streams `/api/log/stream` and now shows tool calls from **every** agent, including the Receptionist (`[TOOL CALL] Receptionist -> calculate ...`). The `[RECEPTIONIST] forward=...` line no longer echoes the message body — the full message is logged exactly once, by the routing tool, as `[AGENT MSG] Receptionist -> Orchestrator <message>`.

**End Session** wipes the chat, the LOG view, all agent highlights, all dynamic gray arrows, and all "last tool used" captions, and reopens a fresh session.

### Chat viewer footer

Below the 3D viewer in the Chat view sit two small buttons:

| Button | Behaviour |
|---|---|
| **Download geometry** | Disabled until a propeller mesh is loaded. Saves the currently displayed `.obj` via a programmatic `<a download>` click against the `/api/artefact` URL the viewer is already using. |
| **Copy parameters list** | Fetches `/api/parameters` and writes the response to `navigator.clipboard`. Falls back to a hidden-textarea + `document.execCommand("copy")` path for plain-HTTP contexts so it works on the local Docker URL too. Brief "Copied!" / "Copy failed" feedback. |

The `/api/parameters` endpoint currently serves the canonical 17-parameter reference list (`DC_prompt_fragments/dc_config/parameters.md`) as `{"text": "..."}`. *(See TODO F9 — once a mesh is on screen the endpoint should ideally return that attempt's actual `parameters.json` values instead of the generic reference list.)*

## Architecture: how live activity reaches the browser

The LOG and Status view, the live 3D viewer, and the per-agent "last tool used" captions are all driven by a single in-process pub-sub channel, with two SSE endpoints flushing events out to the browser. No agent code ever reaches into the web layer (per `warnings_developer.md` W17).

### The publish/subscribe seam (`agents/shared/viz_bus.py`)

Framework-agnostic by design — agent code calls `publish(event)`, the web layer calls `subscribe()` to get a per-connection event queue. When no subscriber is listening (REPL / Streamlit / tests), `publish` is a no-op. The bus accepts arbitrary dicts; the convention is a `type` field that the web layer routes on.

Three event types are in use today:

- `{type: "visualize", path, name}` — published by `tools/visualize_model/visualize_model.py:visualize_3d_model`. Tells the viewer to load a new mesh inline as soon as the agent invokes the tool, without waiting for end-of-turn.
- `{type: "agent_active", from, to, note}` — published from `agents/shared/trace.py:trace()` on every agent-to-agent handoff and (via the `@tool_active` decorator) on DC-tool entry / exit. Drives the highlight class on the flowchart.
- `{type: "generic_tool", name, state}` — published from `agents/shared/agent_activity.py:generic_tool` on entry/exit. Drives the "last tool used" caption only; never affects which agent is highlighted.

### The decorators (`agents/shared/agent_activity.py`)

Two wrappers, applied beside each tool's existing `@tool` decorator:

- `@tool_active("Display Name")` — for the two DC-specific tools that have their own boxes (Propeller Configurator, Visual Renderings generator). Calls `trace()` on entry **and** exit, so the tool's box stays lit alongside the Tool Caller while the tool runs and unlights cleanly when it returns.
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

### Frontend dispatch (`web/app.js`)

A single SSE handler in `startEventStream()` routes incoming events to either the viewer (`visualize`), the flowchart (`agent_active` → `applyAgentActive`), or the per-agent caption (`generic_tool` → `recordToolUsedByActiveAgent`). The strict-transitions highlighting policy lives entirely in `applyAgentActive`: at most one agent box is lit at a time, except during a DC-tool call where both the agent and the tool box are highlighted together.

## Context Pruner

Long multi-attempt sessions accumulate messages and (with `KEEP_IMAGES_IN_CONTEXT=True`) image content blocks across every agent's history. Once a single agent's history crosses the configured token threshold its next LLM invoke would either be wasteful or, in the worst case, exceed the provider's context window. The **Context Pruner** is a stateless agent (`agents/shared/context_pruner.py`) that condenses the older portion of any chain agent's history into a single SystemMessage block before the next invoke, keeping only the most recent N messages verbatim.

### How it fires

Every chain agent (Receptionist, Orchestrator, UII, Planner, DCIC, DCII, DCOI, Tool Caller) calls `self.prune_history_if_needed()` at the top of its invoke loop, in `agents/shared/base_chain_agent.py`. The check:

1. **Gated by** `CONTEXT_PRUNER_ENABLED` (default `True`).
2. **Triggered** when `count_tokens(self.messages) > CONTEXT_PRUNER_THRESHOLD_TOKENS` (cl100k_base, default 80,000). Below the threshold nothing happens.
3. **Cut point** is computed as `len(self.messages) - CONTEXT_PRUNER_KEEP_LAST_MESSAGES` (default 6), then advanced forward via `_safe_cut_point` so a `ToolMessage` is never separated from its matching `AIMessage(tool_calls=...)` — tool-call pairs are always pruned or kept as a unit.
4. **Prefix is serialised** to plain text (`USER:`/`ASSISTANT:`/`TOOL_RESULT:` lines; image content blocks become `[image: redacted for pruning]` placeholders so they don't waste pruner tokens) and handed to the Pruner's `run()`. The Pruner's system prompt is in `agents/shared/context_pruner.py`; it tells the model what to REMOVE (old render descriptions, superseded user requests, verbose tool outputs), KEEP (current design requirements, decisions, latest assessment, unresolved issues), and SUMMARISE (multi-attempt fix loops, long tool outputs).
5. **Result replaces** `self.messages` as `[SystemMessage("SUMMARY OF EARLIER CONVERSATION (pruned by the Context Pruner; N older messages condensed into this block): ...")] + tail`. The Database Handler is intentionally NOT pruned — it iterates ~28 schedule entries per save and relies on accumulated state.

### What stays untouched

Each agent's **original system prompt** lives in `self.system_prompt`, NOT in `self.messages`. The invoke pattern is:

```python
response = invoke_with_retry(
    self.llm,
    [make_system_message(self.system_prompt, self.provider)] + self.messages,
    "Receptionist",
)
```

The system prompt is rebuilt fresh at every invoke from the untouched `self.system_prompt` attribute, so pruning has no effect on it. The LLM sees the original system prompt, then the pruner's summary `SystemMessage` (now in `self.messages[0]`), then the kept tail messages. Anthropic / Google concatenate adjacent `SystemMessage` blocks into the single top-level system field of their respective APIs; OpenAI keeps them as separate `role: "system"` messages — all three handle this shape cleanly.

### Live feedback

While the Pruner runs, the LOG-and-Status chart highlights the **Context Pruner** box in the EXTRA AGENTS panel alongside the calling agent's box (same multi-active pattern as the two DC tools — see `applyAgentActive` and `TOOL_NAMES` in `web/app.js`). The matching exit handoff clears the CP box and leaves the caller solo-lit. Every prune logs a `[CP] <agent_key>: pruned history N -> M messages, ~X -> ~Y tokens` line in the session log.

## DH schedule: three kinds of questions

The DH schedule (edited via the **Questions for Saved Sessions** view, persisted as `workflow_settings/dh_schedule.json`) supports three kinds of rows:

| Kind | How it's flagged | Example | What the DH does |
|---|---|---|---|
| **Session-related** | `scope = session` (top-level row) | "What was the user's request?", "Did any agent flag an error?" | Interview Agent A, save Q+A to `.txt`. No attempt context. |
| **Identifying attempt-specific** | `scope = attempt` + `parent_id = null` (top-level) | "Which attempt best satisfied the user?", "Which attempt led to problems?" | Interview Agent A, **then forced to call `save_attempt_artefacts`** to pin down which attempt. On success, save Q+A AND upload the attempt's artefacts. On failure, drop the whole block (this row + every Q(N).x sub-row). |
| **Attempt-specific sub-row** | `scope = attempt` + `parent_id = <identifying row's id>` | "Why was that attempt successful?", "What numerical parameters were used?" | Description is auto-prefixed with `"For attempt NNN: "` before the interview, so Agent A knows which attempt to answer about. Saved like any session row. |

The Q-number scheme reflects the structure: `Q1, Q2, Q2.1, Q2.2, Q3` means Q1 and Q3 are session-related, Q2 is identifying, Q2.1 / Q2.2 are sub-rows under Q2.

## Identifying attempt-specific questions — force-tool flow

When the DH reaches an identifying attempt-specific row, the system runs a 5-step protocol that's distinct from the normal ASK/SAVE loop:

1. **DH formulates** the question (e.g. "Which attempt best satisfied the user's request?") and the system delivers it to Agent A.
2. **Agent A replies** in plain prose.
3. **Force-tool turn**: the DH's LLM is bound with `tool_choice="save_attempt_artefacts"` for this single turn. The DH MUST call the tool. Allowed inputs:
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

## Cloudflare R2 layout — how the two upload paths combine

The DH save flow writes to R2 via **two distinct upload paths** that run at different points and target **disjoint** parts of the per-session key space. Understanding which is which makes it easy to reason about what shows up in the bucket and why.

### Path 1 — Per-attempt artefacts (during the force-tool turn)

Site: `agents/database_handler/database_handler.py:_run_force_tool_phase`. Fires once per resolved attempt id, **immediately** when the force-tool's `save_attempt_artefacts` tool call succeeds — long before the DH emits its SAVE: body.

Calls `r2_uploader.upload_attempt_artefacts(folder, session_id=…, attempt_id=NNN)` per resolved NNN. Whitelisted files (from `agents/shared/r2_uploader.py:ATTEMPT_ARTEFACT_WHITELIST`): `parameters.json`, `propeller_mesh.obj`, `render_isometric.png`, `render_top.png`, `render_side.png`, `description.txt`. `propeller_mesh_components.obj` is intentionally excluded.

Keys written:

```
<R2_KEY_PREFIX>/<session_id>/attempts/<NNN>/<session_id>__<NNN>__<original_filename>
```

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

### Why the two paths can't double-upload

The local `database/<session_id>/` folder **does NOT contain an `attempts/` subtree** — `_collect_user_inputs` only writes `user_inputs/`, and `populate_database` only writes `<agent>/`. So Path 2's `upload_directory` walk cannot accidentally re-walk the artefact files; the two paths target disjoint key prefixes (`<sid>/attempts/<NNN>/…` vs `<sid>/<agent>/…` and `<sid>/user_inputs/…`). This is a load-bearing invariant — see `extra_utilities/warnings_developer.md` W19.

### What is NOT in R2

* **Sidecar `.meta.json` files** next to every `.txt`. The suffix whitelist is `.txt` / `.png` / `.jpg` / `.jpeg` — `.json` is excluded deliberately so the per-question access-control metadata (`to_agents` etc.) doesn't pollute the embedding stream. The sidecars remain local under `database/<session_id>/<agent>/<field>.meta.json` and travel into the End Session archive as part of the rest of the save tree.
* **Local `attempts/<slug>/` working folder.** The attempt artefacts upload through Path 1 with the rename pattern; the original folder names (`20260530_142312_002_descriptor`) only exist in the local filesystem and the End Session archive.
* **Per-session logs.** `logs/web_<id>.log`, `logs/agent_flow_*.txt`, `logs/dh_flow_*.txt` are local-only today. F13 in TODO_known_issues calls out the path to mirroring them when the Railway volume removal lands.

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
| `RAG_ENABLED` | `False` | reserved (logged but unwired) |
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
| `LLM_ROUTING_MODE` | `"individual"` | `"individual"` honours per-agent `.env` overrides; `"openai"` / `"anthropic"` / `"google"` forces every agent onto that provider. Edit only via the LLM-routing chart at the top of Workflow Settings. |
| `CONTEXT_PRUNER_ENABLED` | `True` | run the Context Pruner pre-invoke check on each chain agent |
| `CONTEXT_PRUNER_THRESHOLD_TOKENS` | `80000` | cl100k_base token count above which a chain agent's history is pruned before its next invoke |
| `CONTEXT_PRUNER_KEEP_LAST_MESSAGES` | `6` | how many recent messages of the calling agent survive the prune verbatim (cut point is extended forward to never split an `AIMessage(tool_calls)` from its `ToolMessage`) |

## Status & known issues

- [`extra_utilities/TODO_known_issues.md`](extra_utilities/TODO_known_issues.md) — open issues (O1–O10) and future-work entries (F1–F11), including the LOG-and-Status open items called out in this README:
  - **F5 / F6** — colorising the log pane and showing tool-call payloads on the flowchart.
  - **F9** — make Copy parameters list return the selected attempt's actual `parameters.json` instead of the canonical reference list.
  - **F10** — the dynamic gray arrows around the Orchestrator are wired but need a deployed-build debug pass.
  - **F11** — tighten the Stop button to cancel at the next tool call / message / LLM call boundary instead of only at Orchestrator hop boundaries; tool calls issued after Stop is pressed should not execute.
- [`extra_utilities/warnings_developer.md`](extra_utilities/warnings_developer.md) — load-bearing invariants (W1–W17) that must not regress.

## Roadmap

Near-term direction:

- Wire `RAG_ENABLED` to consume the database the Database Handler produces.
- Stage B: persist sessions and embeddings to Postgres, push binary artefacts to R2.
- Reorganise tools — split generic helpers from DC-specific tools and consolidate under `tools/` (see TODO F8) — so the `@generic_tool` decorator only needs to live at the `@tool` site instead of being duplicated on each agent's `_handle_*` handler method.
- Close out the LOG and Status open items above (F5, F6, F9, F10, F11).

**Done since v7:**

- Move heavy compute off the local driver — RhinoCompute now runs on an Azure VM, the Stage A FastAPI app runs on Railway.
- Build a web interface as the user-facing front-end — FastAPI + plain JS, see [Web UI](#web-ui) above.
- LOG and Status view live, with strict-transitions highlighting, dynamic Orchestrator caller/callee arrows, per-agent "last tool used" captions, and live session log tailing.
- Stop button with cooperative pipeline cancellation between hops.
- Chat viewer footer (Download geometry + Copy parameters list).
- Receptionist tool calls now appear in the session log alongside every other agent; `[RECEPTIONIST]` no longer duplicates the forwarded message body.
- **Context Pruner** wired into every chain agent's pre-invoke hook (see [Context Pruner](#context-pruner) below). F7 closed.
