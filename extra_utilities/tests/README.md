# Offline checks

Six hand-run scripts that need no network, no database and no API spend.
There is no CI and no pytest: run each one directly from the **repository
root**.

```bash
py -3.13 extra_utilities/tests/dry_run_topology.py
```

Use Python 3.13 — the default 3.8 cannot parse the agent code's type hints.
Where `trimesh` / `langchain_*` are not installed, the scripts that import the
agent tree stub them through `extra_utilities/prompt_pdf/bootstrap.py`; set
`OPENAI_API_KEY=sk-dummy` (a key must exist to construct agents; nothing is
sent) and `PYTHONIOENCODING=utf-8` if you pipe the output.

These six were kept when the other ~50 test scripts were removed on
2026-10-10.  `extra_utilities/extra_info.md` §13 lists every removed script,
what it guarded and how to restore it from git.

## The six checks

| Script | Run it after… | What it proves |
|---|---|---|
| `dry_run_topology.py` | any change to routing, a hub, an agent's run loop or the dispatcher | Drives ONE complete turn per topology (7, 5 and 3) against a scripted fake LLM.  Everything except the LLM call is the production path: the real `dispatch_turn`, the real Receptionist, every agent's run loop, the real routing tools and hub dispatch.  It asserts the exact sequence of hops, so a mis-route fails naming who was called and who should have been, and an unbound tool name stalls the turn.  `--topology N` runs one topology; each runs in its own subprocess.  This is the only check that catches the defects both early 5-agent live runs hit (a blank user reply, a discarded start target, a hub calling an agent it never built). |
| `smoke_test_topology_fragments.py` | any prompt or fragment edit | Builds every prompt for topologies 7, 5 and 3 and checks that no topology reads another's files, no `$slot` is left unsubstituted, the hub routing resolves correctly, and topologies 5 and 3 read **nothing** from the shared prompt trees (the MIRROR invariant).  Findings awaiting an owner-approved prompt edit are printed as KNOWN-PENDING rather than passed silently.  Needs Python ≥ 3.10.  **Writes probe fragments into the real tree and removes them** — check `git status` afterwards. |
| `smoke_test_hub_attributes.py` | any change to a hub class | Pure AST, imports nothing.  For every hub: every `self.<attr>.<method>()` refers to an attribute the class actually has (the defect that left an old hub calling three agents its topology never built), and the wired routing edges match the expected edge set read from the source. |
| `smoke_test_slot_splices.py` | any fragment edit | Scans every prompt and fragment and fails when a `$slot` that expands to several lines does not stand alone on its own line.  Pure standard library. |
| `smoke_test_prompt_format.py` | any prompt edit | Formats every agent template of topologies 7, 5 and 3 (one subprocess per topology) with a stub mapping, under RAG off, RAG on, and RAG on with every database tool forced on, catching a literal `{` / `}` or an unmatched brace before it reaches agent construction (see `warnings_developer.md` W45; TODO F101). |
| `smoke_test_agent_roles.py` | any change to `agents/shared/agent_roles.py`, a hub's roster, `database_search`'s ACL or the DH question loader | The agent role map across topologies: `ROSTER` matches what each hub builds and `DISPLAY` matches `routing_tools.AGENT_DISPLAY`; who may read which past answers per topology (both directions, the hub taking the Orchestrator's role, the `RAG_DCIC_READS_DCII` toggle); that the question table maps "Agent from" downward only and drops a skipped row's sub-rows; and that a real assembled `database_search` response carries the `<agent_roles>` legend once, right after `<search_meta>`, listing only the agents found.  Offline (stubbed imports). |
| `smoke_test_ring_height.py` | any change to `web/feg/` or `tools/generate_mesh/ring_height.py` | The Python port of the outer-ring height fit must match the real `web/feg` JavaScript (run under Node) to within 1e-9 mm over 552 parameter sets.  **It is the only guard for that port — never remove it.**  Needs Node and `node_modules/three` (`npm install` in the repo root); without them it prints SKIP. |

## Things worth knowing before you trust a result

- **`smoke_test_slot_splices.py` false-fails when run from the main
  checkout** if `.claude/worktrees/` holds other checkouts: it walks the
  whole tree and scans them too.  If a failure names a path under
  `.claude/worktrees/`, it is not about this checkout.  The same trap applies
  to any repo-wide grep run from the main checkout.
- **A stale `.pyc` can serve the wrong `SYSTEM_TOPOLOGY`** (switching 7 → 5 → 3
  is a size-preserving edit).  If a check contradicts an earlier green run,
  delete every `__pycache__` folder and run it again.
- **For any prompt edit, also snapshot the assembled prompts** before and
  after: `py -3.13 extra_utilities/scripts/topology_prompt_snapshot.py save <dir>`,
  then `diff <dirA> <dirB>`.  State which agents moved and which are
  byte-identical; a topology-5 or topology-3 edit must leave topology 7's
  prompts untouched.
