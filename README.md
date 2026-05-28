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

**Layout.** The Orchestrator sits in the centre of the chart with open space around it. Each chain agent (UII, Planner, Input Creator, Input inspector, Tool Caller, Output inspector) lives in a fixed column; the two DC tool boxes (`Propeller Configurator`, `Visual Renderings generator`) sit on the right, next to the Tool Caller. Database Handler and Context Pruner live in the EXTRA AGENTS panel — placeholders that will light up once they're wired into the live flow.

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
- Implement the **Context Pruner** agent (slot reserved in the LOG and Status flowchart — see TODO F7).
- Reorganise tools — split generic helpers from DC-specific tools and consolidate under `tools/` (see TODO F8) — so the `@generic_tool` decorator only needs to live at the `@tool` site instead of being duplicated on each agent's `_handle_*` handler method.
- Close out the LOG and Status open items above (F5, F6, F9, F10, F11).

**Done since v7:**

- Move heavy compute off the local driver — RhinoCompute now runs on an Azure VM, the Stage A FastAPI app runs on Railway.
- Build a web interface as the user-facing front-end — FastAPI + plain JS, see [Web UI](#web-ui) above.
- LOG and Status view live, with strict-transitions highlighting, dynamic Orchestrator caller/callee arrows, per-agent "last tool used" captions, and live session log tailing.
- Stop button with cooperative pipeline cancellation between hops.
- Chat viewer footer (Download geometry + Copy parameters list).
- Receptionist tool calls now appear in the session log alongside every other agent; `[RECEPTIONIST]` no longer duplicates the forwarded message body.
