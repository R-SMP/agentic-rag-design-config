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
├── main.py                       # entrypoint → agents.loader.run()
├── config.py                     # paths + RhinoCompute env vars
├── requirements.txt
├── workflow_settings/settings.py # 11 runtime flags (see Configuration)
├── agents/
│   ├── loader.py                 # session lifecycle, REPL, archival, DH invocation
│   ├── step_caps.py              # single source of truth for every MAX_*
│   ├── shared/                   # prompt assembly, routing, retry, rate-limit, tools
│   ├── orchestrator/  receptionist/  planner/  user_input_inspector/
│   ├── dc_input_creator/  dc_input_inspector/  tool_caller/  dc_output_inspector/
│   └── database_handler/         # post-session interviewer (opt-in)
├── DC_prompt_fragments/          # DC-specific prompt fragments (propeller today)
│   ├── dc_config/                # parameters, structure, capabilities, constraints
│   └── tools_config/             # tool inventory, render-check library
├── tools/
│   ├── generate_mesh/            # RhinoCompute + Grasshopper definition
│   ├── render_mesh/              # trimesh + pyvista backends
│   └── calculate/
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

This repo (test11) is the v5 starting point. Near-term direction:

- Move heavy compute (RhinoCompute, mesh gen, rendering) off the local driver onto a server.
- Build a web interface as the user-facing front-end.
- Wire `RAG_ENABLED` to consume the database the Database Handler is now producing.
