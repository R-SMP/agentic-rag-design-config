# Topology registry — every SHARED file a new agent must be added to

**Why this exists.**  The 5-agent topology's *prompts* are separated into
`agents/5agent/`, but its *code* cannot be: a folder whose name starts with a
digit is not a valid Python package, and several tables are single global
registries that every topology must share.  So each new agent adds an entry to
a fixed set of shared files.

**The failure mode is silence.**  The wiring map found that a missed entry does
not usually raise — it degrades.  `AGENT_DISPLAY` is the exception and the
reason it is listed first: miss it and everything else raises immediately,
which is the good case.

**Adding the 3-agent variant (or any new agent) = working this list top to
bottom.**  Verified 2026-08-01 by grep, not from memory.

---

## The 13 shared touch-points

| # | file | table / symbol | what a MISS causes |
|---|---|---|---|
| 1 | `agents/shared/routing_tools.py` | `AGENT_DISPLAY` | **Everything breaks loudly.** `ROUTING_TOOL_NAMES` and `session.KNOWN_AGENT_KEYS` both derive from it, so `call_<agent>` is not a recognised terminal routing tool and `AgentState(agent_key=...)` raises. **Do this one first.** |
| 2 | `agents/shared/routing_tools.py` | `_TOOL_DESCRIPTIONS` | Silent: a generic fallback description is used, so the LLM gets a weaker tool doc with no error. |
| 3 | `agents/shared/trace.py` | `_AGENT_DISPLAY_NAMES` | Silent: the agent's activity never lights up the LOG/Status flow chart. Duplicated deliberately (not imported) to avoid a circular import. |
| 4 | `agents/shared/base_chain_agent.py` | `_PRUNE_DISPLAY_NAMES` | Silent: `agent_active` events carry no display label. |
| 5 | `agents/shared/prompts.py` | `PROMPT_MD_RUNTIME_SLOTS` | The unescaped-brace / unknown-runtime-slot validator cannot check that agent's prompt. |
| 6 | `agents/step_caps.py` | per-agent caps | No budget for the new agent's run loop. |
| 7 | `agents/orchestrator/orchestrator.py` | `_AGENT_KEY_ALIASES` | `read_agent_history` cannot resolve the agent by name. |
| 8 | `workflow_settings/database_access.py` | `DEFAULT_AGENTS` | No DBa toggle; database tools never bind. Its own comment requires editing #9 in the same commit. |
| 9 | `agents/database_handler/db_writer.py` | `DEFAULT_AGENTS_TO_ACL` | The agent is missing from `chunks.agents_to` defaults. |
| 10 | `workflow_settings/ocr_access.py` | `DEFAULT_AGENTS` | Silent and easy to miss: the agent's `view_images` calls lose their OCR text. **Only for agents that bind image tools** — the wiring map got this wrong for the Conductor, which does bind `view_images` (inherited from the Planner). |
| 11 | `workflow_settings/llm_defaults.py` | `DEFAULT_PER_AGENT_MODELS` | No default model for the agent. |
| 12 | `workflow_settings/llm_routing.py` | `AGENT_SPEC` | Absent from LLM routing. Note the third field, `wired_into_dispatcher` — set it `False` until the agent is actually constructed, as `context_pruner` does. |
| 13 | `workflow_settings/settings.py` + `editor.py` | `SYSTEM_TOPOLOGY` + `ENUM_OPTIONS` | The topology cannot be selected from the UI. |

## Not in this list, but also needed

- **The agent package itself** — `agents/<name>/<name>.py` + `__init__.py`, a
  peer of `agents/planner/` (owner's decision: keep the repo's one-folder-per-agent
  convention rather than a topology package).
- **The prompt** — `agents/<N>agent/<agent>/prompt.md` for a survivor whose
  prompt varies by topology, or `agents/<name>/prompt.md` for an agent that
  exists in only one topology.
- **The hub's `_wire_routing`** — each topology's hub owns its own edge set;
  there is no shared table to extend (wiring-map obstacle O2).
- **`web/app.js` `LR_BOXES`** — no coordinates means the agent is silently
  omitted from the LLM-routing chart (verified: `LR_AGENT_KEYS` is *derived*
  from `LR_BOXES`, so this omits rather than crashes).

## Known side-effects of a superset registry

`agents/loader.py` iterates `AGENT_DISPLAY.keys()` for the startup LLM banner,
so it lists agents that the active topology never constructs, and the "all N
agents share one default" collapse changes its count.  Accepted knowingly.
