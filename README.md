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

**Live highlighting.** Every agent box lights up yellow ("strict transitions") between the moment another agent hands off to it and the moment it hands off to someone else. The two DC tools (`Propeller Configurator` for mesh generation, `Visual Renderings generator` for the three renders) have their own boxes next to the Tool Caller and light up alongside Tool Caller while in use (Tool Caller is semantically waiting for the tool).

**Generic helpers** — `read_user_inputs`, `write_extraction`, `read_extracted_inputs`, `new_attempt`, `write_parameters`, `read_parameters`, `load_render_images`, `calculate`, `visualize_3d_model`, etc. — complete in milliseconds and are too fast to flash. Each agent box therefore also carries a small **gray-italic line below the agent's name recording the most recent generic tool that agent invoked**. The line persists across handoffs so the chart shows each agent's history at a glance; it wipes on End Session.

**Instrumentation seams.** Activity events flow through `agents/shared/viz_bus.py` (a framework-agnostic pub-sub channel) and reach the browser via `/api/events` SSE:

- `agents/shared/trace.py:trace(from, to)` publishes an `agent_active` event on every routing-tool handoff. Pass `publish=False` for file-only trace lines that should NOT light up the chart (e.g. utility-tool log entries whose `to` is a tool function name, not a real agent).
- `agents/shared/agent_activity.py` exposes two decorators:
  - `@tool_active("Display Name")` — for the DC tools that have their own boxes; publishes `agent_active` events on entry/exit so the box stays lit alongside the caller while the tool runs.
  - `@generic_tool("Display Name")` — for fast generic helpers; publishes a separate `generic_tool` event consumed only by the LOG and Status view's "last tool used" labels, and never affects which agent is highlighted.

**End Session** wipes the chat, the LOG view, all agent highlights and all "last tool used" labels, and reopens a fresh session.

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

- [`extra_utilities/TODO_known_issues.md`](extra_utilities/TODO_known_issues.md) — open issues (O1–O8) and carry-forward bugs.
- [`extra_utilities/warnings_developer.md`](extra_utilities/warnings_developer.md) — load-bearing invariants (W1–W12) that must not regress.

## Roadmap

Near-term direction:

- Wire `RAG_ENABLED` to consume the database the Database Handler produces.
- Stage B: persist sessions and embeddings to Postgres, push binary artefacts to R2.
- Implement the **Context Pruner** agent (slot reserved in the LOG and Status flowchart — see TODO F7).
- Reorganise tools — split generic helpers from DC-specific tools and consolidate under `tools/` (see TODO F8) — so the `@generic_tool` decorator only needs to live at the `@tool` site instead of being duplicated on each agent's `_handle_*` handler method.

**Done since v7:**

- Move heavy compute off the local driver — RhinoCompute now runs on an Azure VM, the Stage A FastAPI app runs on Railway.
- Build a web interface as the user-facing front-end — FastAPI + plain JS, see [Web UI](#web-ui) above.
