# Merge or don't: the three RAG tools and the two attempt tools

Two questions are on the table, both raised by the owner against a prior recommendation that said no to each. **B1:** why is merging `database_search` / `retrieve_user_inputs` / `retrieve_attempt` hard, and what about merging just two of them? **B2:** should `list_attempts` and `read_attempt` change — merge, rewrite, unbind, or something else entirely? This document re-derives both from the code rather than assuming the earlier verdict, prices every shape the owner named plus the non-merge shapes that compete with them, and corrects six figures the prior passes got wrong — including one epistemic claim that was flatly backwards. The merge verdicts survive. Almost nothing else about the earlier write-up does.

**Measurement basis, stated once.** Two numbers appear throughout and they are not interchangeable.

- **DOC** = raw docstring characters ÷ 4. This is `approx_tokens` at `extra_utilities/prompt_efficiency/measure_prompts.py:77-78`, and it is the basis every figure in `PROMPT_SHRINK_PROPOSAL_7agent.md` uses. Comparisons against the census must use it.
- **SCHEMA** = the cleandoc'd description + any `Annotated` argument descriptions + roughly 35–50 tokens of JSON envelope, ÷ 4. This is what is actually re-sent on every turn.

Neither is tiktoken. This worktree is Python 3.8.2 with no `tiktoken` and no `langchain` installed, so no figure here is a token count — all are the estimator the programme already uses. Where a claim depends on the difference between the two bases, that is called out; one of the prior pass's "corrections" is entirely an artefact of mixing them (Part 3, item 5).

---

## Part 1 — B1: the three RAG tools

### Current state

**Signatures, verified by reading all three modules.**

| tool | factory | `@tool` at | arguments | required today |
|---|---|---|---|---|
| `database_search` | `tools/database_search/database_search.py:1536` | `:1587` | `query`, `n`, `attempt_specific_flag=False`, `metafilters=None` | **`query`, `n`** |
| `retrieve_user_inputs` (OCR on) | `tools/retrieve_user_inputs/retrieve_user_inputs.py:641` | `:669` | `sessions_ID_list`, `images_flag=False`, `extract_text=False` | **`sessions_ID_list`** |
| `retrieve_user_inputs` (OCR off) | same factory | `:706` | `sessions_ID_list`, `images_flag=False` | **`sessions_ID_list`** |
| `retrieve_attempt` | `tools/retrieve_attempt/retrieve_attempt.py:575` | `:593` | `attempts_ID_list`, `images_flag=False` | **`attempts_ID_list`** |

The prior pass's claim that all four primary arguments are required is **CONFIRMED** by AST inspection (no defaults on any of them). Its line numbers were off by one on three of the four — it cited `:1589`, `:1597`, `:671`; the actual argument lines are `:1588`, `:1596`, `:670`.

**Return shapes and execution model — and they are not the same.** `database_search` returns a real string directly from the `@tool` (impl `_database_search_impl` at `:1432`), text only, capped at `DATABASE_SEARCH_MAX_RESPONSE_TOKENS = 30_000` (`workflow_settings/settings.py:613`). The other two are **stubs that `return ""`** (`retrieve_user_inputs.py:702`/`:743`, `retrieve_attempt.py:625`); the real work happens in `agents/shared/retrieve_tool_dispatcher.py`, which appends the ToolMessage *and* buffers image content blocks onto the next HumanMessage via `append_pending_images`. Their cap is shared: `RETRIEVE_MAX_RESPONSE_TOKENS = 30_000` at `settings.py:682`.

**Schema cost per agent per turn**, SCHEMA basis:

| | description chars | arg-description chars | ≈ tok/agent/turn |
|---|---:|---:|---:|
| `database_search` | 837 | 1,396 (query 281 / n 218 / flag 389 / metafilters 508) | **≈ 610** |
| `retrieve_user_inputs` (OCR off / on) | 797 / 1,139 | 0 | **≈ 235 / 325** |
| `retrieve_attempt` | 1,118 | 0 | **≈ 315** |
| **trio** | | | **≈ 1,160 – 1,250** |

The prior pass quoted these components to four significant figures and got most of them wrong (it said `database_search`'s argument descriptions were 1,269 chars; they are 1,396). Its aggregate — "~1,205 tok/agent" — happens to land inside the range above, so nothing built on the aggregate moves.

**Who binds them.** Twelve agent classes bind all three when RAG is on: architect, conductor, creator, designer, dc_input_creator, dc_input_inspector, dc_output_inspector, orchestrator, planner, receptionist, tool_caller, user_input_inspector. Binding is by `tool.name` into a dict, so no agent hard-codes a tool name. The literal name strings live at `retrieve_tool_dispatcher.py:208-209`, plus `retrieve_user_inputs.py:408` / `retrieve_attempt.py:376` (the `rag_queries.tool_name` value), `extra_utilities/db_design/migrations/migrate_v6_to_v7.py:86-112` (DDL default + index), and two smoke tests. The prior pass's "only three hard-coded sites" is an undercount, though not a material one.

**What ships today.** `workflow_settings/settings.py:104` is `RAG_ENABLED: bool = False`; `workflow_settings/database_access.py:142` ANDs the master switch with the per-agent flag and gates both the binding and the `<<HAS_DBA>>` prompt region. So today: nothing binds, nothing renders. **When RAG is switched on**, `workflow_settings/database_access.json` has `orchestrator: false` and `tool_caller: false`, so **six** of the eight seven-agent chain agents get the trio, not eight. Note also that `database_access.json` holds only those eight keys, while `database_access.py:70-84` lists twelve agents with `_DEFAULT_VALUE = True` at `:90` — so conductor, creator, architect and designer all default to **on** in their topologies, and the comment at `:65` still calls the tuple "the 8 chain agents".

**What is already converged at the prompt layer, without any merge.** `DC_prompt_fragments/tools_config/retrieve_attempt.md` is **0 bytes** — deliberately, per commit `251ff5b` ("retrieve_* fragments — lean fully on the tool schemas"). Its 17 `$retrieve_attempt_tool` slots render nothing. `DC_prompt_fragments/tools_config/retrieve_user_inputs.md` (731 chars, 183 tok) already covers **both** tools in one block, opening: "``retrieve_user_inputs`` and ``retrieve_attempt`` document their purpose, arguments, and return shape on the tools themselves." The 7-agent-reduced tree has already deleted the dead slot from 5 of its 8 prompts (it survives at `agents/7agent_reduced/orchestrator/…:506`, `planner/…:523`, `user_input_inspector/…:245`).

**Prompt-site census, re-counted.**

| | occurrences | files |
|---|---:|---:|
| `$database_search_tool` | 22 | 22 |
| `$retrieve_user_inputs_tool` | 22 | 22 |
| `$retrieve_attempt_tool` | 17 | 17 (all dead) |
| `$database_search_per_agent` | 22 | 22 |
| **slot total** | **83** | **22 unique** |
| prose lines naming any of the three | 37 | — |
| prose lines naming the retrieve pair | 27 | — |

The prior pass's "83 lines / 22 files" and "17 not 22" are **CONFIRMED exactly**. But 22 of the 83 are `$database_search_per_agent` lines no merge touches, and 17 are dead slots. On the basis of *lines that would actually have to be edited or deleted*: **≈98 for a three-way merge, 66 for the retrieve pair** (39 slot lines of which 17 are deletions, plus 27 prose lines).

**Fragment cost when RAG is on** (chars ÷ 4, LF, the same method the proposal used and reproducing its figures): `database_search.md` = 3,032 chars = **758 tok**; `retrieve_user_inputs.md` = 731 chars = **183 tok**; `retrieve_attempt.md` = **0**. The eight per-agent overlays total ~5,318 chars ≈ 1,317 tok, and `database_search_orchestrator.md` / `database_search_tool_caller.md` are **byte-identical** (408 bytes each) — and both belong to agents whose DBa flag is already `false`.

### Why a three-way merge is hard — the specific mechanism

The prior pass said the plumbing made it hard. **That is wrong, and the owner is right to have pushed on it.** I checked the run loop of all twelve binding agent classes: `dispatch_retrieve_tool` is called *before* the by-name utility lookup in every one — `user_input_inspector.py:256` vs `:258`, `tool_caller.py:228` vs `:233`, `orchestrator.py:522` vs `:524`, `planner.py:277` vs `:279`, `receptionist.py:182` vs `:184`, `architect.py:467`, `conductor.py:412`, `creator.py:279`, `designer.py:294`, `dc_input_creator.py:249`, `dc_input_inspector.py:215`, `dc_output_inspector.py:330`. A merged, dispatcher-routed tool would be intercepted correctly in all twelve today. Binding is name-agnostic. The plumbing objection is retired.

The real mechanism is three things, none of which is mechanical:

**1. A flat merged schema cannot express "query+n XOR ids".** The four required arguments are mutually exclusive across modes. Pydantic models generated from a Python signature — which is how every tool in this repo is declared — have no way to say "required when `kind='search'`". The escape hatch is a hand-written `args_schema` with a discriminated union. **Correction to the prior pass, which said this was impossible here:** it isn't. No `bind_tools` call in this repo passes `strict=True`, and `args_schema=` is used by exactly zero tools, so the Annotated-argument style is a house convention, not a hard constraint. The honest objection is weaker but still real: a Pydantic union validates at *runtime*, so a wrong-shaped call degrades to an error string, which is the same failure surface the flat merge has. A discriminated union relocates the check; it does not restore the schema-level guarantee.

**2. It costs tokens rather than saving them.** Merging removes two JSON envelopes (~35–50 tok each) and adds a `kind` discriminator description plus applicability clauses on six arguments. Net is somewhere between break-even and **+100 tok/agent/turn**, i.e. up to +600 across six DBa-on agents. A merge that makes the every-turn schema *larger* cannot be justified by "less clutter" — the model still reads all three contracts, now interleaved with mode-applicability prose it has to resolve itself.

**3. These are not three ways to do one thing — they are a typed pipeline.** `database_search` emits `<available_attempts>` global ids (`database_search.py:512`, `:891-922`) and, in multimodal mode, `<image_ref>` (`:841`). Those are the *inputs* to the other two. `retrieve_attempt`'s own docstring says so: "Get these from the ``<available_attempts>`` block of a ``database_search`` response." Under one name that hand-off stops being visible in the schema. It also collapses `rag_queries.tool_name`, added by `migrate_v6_to_v7.py:10-20` precisely "to identify which RAG tool produced the row" and indexed for per-tool analytics.

### Option-by-option

#### (i) Three-way merge

```
past_sessions(kind: Literal["search","user_inputs","attempt"],
              query: str|None = None, n: int|None = None,
              ids: list[str]|None = None,
              images_flag: bool = False, attempt_specific_flag: bool = False,
              metafilters: dict|None = None, extract_text: bool = False) -> str
```

**Required kept: 1 of 4.** Only `kind`. **Docstring** would have to state three purposes, three return contracts (search XML with `<search_meta>` + `<session>` blocks; session text + image notes; attempt description + parameters + renders filtered by the deployed view policy), and which arguments apply in which mode. **Prompt sites: ≈98 lines across up to 33 files, in three trees that have already diverged here.** **Token delta: 0 to +100/agent.**

*Pros:* one name instead of three in the choice space; one cap policy instead of two constants already set to the same 30,000. *Cons:* everything in the section above, plus it makes `database_search` dispatcher-routed, which turns the run-loop branch ordering into load-bearing state in twelve files — and silently kills its flowchart label, since the dispatcher never invokes the stub and so never publishes the `@generic_tool("Database search")` viz event that `database_search.py:1586` currently fires (the other two, `retrieve_user_inputs.py:668`/`:705` and `retrieve_attempt.py:592`, are already dead labels for that reason).

*Failure mode:* `past_sessions(kind="attempt", query="thin blades that worked")` — a search-shaped call in retrieve mode. Every argument is optional; nothing rejects it. Today `attempts_ID_list` is required and `query` does not exist on that tool.

**Verdict: REJECT.** Not for the reason previously given.

#### (ii) `retrieve_user_inputs` + `retrieve_attempt`

```
retrieve_past(kind: Literal["user_inputs","attempt"], ids: list[str],
              images_flag: bool = False [, extract_text: bool = False]) -> str
```

**Required kept: 2, up from 1 each.** This is the finding that matters, and it **overturns the prior pass's stated reason for rejecting this shape.** Each tool has exactly one required argument today; a Literal discriminator gives the merged tool two. The blanket claim "none can stay required in a flat merged schema" is **false for this pair**. It is true, and fatal, for (i), (iii) and (iv).

**Prompt sites: 66** — 22 `$retrieve_user_inputs_tool` renames, 17 dead-slot deletions, 27 prose lines. **Token delta: ≈ +30/agent** — one envelope saved, a discriminator and one applicability clause added.

*Pros:* the only shape that preserves requiredness. And the system already treats this pair as one unit everywhere except the schema: one shared cap (`settings.py:678-682` says verbatim that a single shared cap "is simpler than per-tool caps"), one shared fragment covering both by name, one dispatcher module, one `<<HAS_DBA>>` gate, one `rag_queries` table. There is also genuine implementation duplication to collapse.

*Cons:* the id spaces are different types — session ids are strings (`20260718_143201_ab12`), attempt ids are BIGSERIAL integers. `list[str]` vs `list[int]` is the schema telling the model which space it is in; one `ids` field stops telling it, and explaining "integers as strings when kind=attempt" in prose is exactly the mechanics-into-prose move the policy forbids. The two return contracts are different enough that a merged docstring must state both, so the description barely shrinks. `extract_text` applies to one mode only and only for OCR-eligible agents; **TODO F30** (`extra_utilities/TODO_known_issues.md:2276-2302`) plans a per-call `views` argument for attempt mode only — a second mode-conditional argument on a two-mode tool.

*Failure mode:* `retrieve_past(kind="user_inputs", ids=[412, 415])` — global attempt ids passed under the user_inputs kind, because both id spaces appear in the *same* `database_search` response. Result is a silent `status="not_found"` per id, not an error.

**Verdict: DEFENSIBLE, NOT WORTH DOING NOW.** This is the honest answer to "what about just merging two". It is the only viable pair, it was rejected for a reason that does not apply, and it still fails on value: roughly zero tokens, 66 lines across three trees, a real loss of id-type information, and F30 about to change the argument count. Its one concrete benefit is available from (N5) at zero prompt cost. If the owner still wants it, do it **after** F30 lands and **after** (N4), which turns it from a 39-slot job into a 22-slot job.

#### (ii-b) The retrieve pair as two OPTIONAL TYPED lists — my own proposal, costed against itself

```
retrieve_past(sessions_ID_list: list[str] | None = None,
              attempts_ID_list: list[int] | None = None,
              images_flag: bool = False [, extract_text: bool = False]) -> str
```

I proposed this shape before the analysis ran, on the grounds that it answers
(ii)'s strongest objection. It does — and it introduces a different one. Recorded
here because it is my suggestion and it should be held to the same standard as
the rest.

**What it fixes.** (ii)'s decisive con is that one `ids` field stops telling the
model which id space it is in, and that explaining "integers as strings when
kind=attempt" in prose is the mechanics-into-prose move the policy forbids. Here
the argument *name* is the discriminator and the *type* enforces it: session ids
stay `list[str]`, attempt ids stay `list[int]`. (ii)'s failure mode —
`retrieve_past(kind="user_inputs", ids=[412, 415])` silently returning
`status="not_found"` per id — becomes a type error at the boundary, not a silent
empty result. No discriminator exists to get wrong.

**What it breaks.** Requiredness, which was the entire reason (ii) survived
scrutiny. (ii) keeps two required arguments (`kind`, `ids`); (ii-b) has **zero**
required at schema level, because neither list can be individually mandatory. The
"at least one must be supplied" rule moves into the function body and degrades to
a runtime error string — precisely the relocation this document rejects when
arguing about discriminated unions in the three-way case. Judged by the standard
applied to (i), (iii) and (iv), (ii-b) fails it.

**The turn saving is weaker than I claimed.** I argued it collapses two calls into
one. It does — but the sequencing makes that rare: both fetch docstrings say "Use
AFTER `database_search` … has surfaced" something worth reading, and
`retrieve_attempt`'s ids come from the `<available_attempts>` block of a search
response. The pattern is sequential exploration, not a simultaneous fetch of both
kinds. The existing rule already forces batching *within* a kind
(`retrieve_user_inputs.md:8`, "never loop — make ONE call with all the relevant
ids"), so the saving is one turn in the uncommon case where an agent has already
decided it needs both kinds at once.

**Cost is otherwise identical to (ii):** same 66 model-facing lines, same
`extract_text` mode-conditionality, same exposure to F30 adding a third
mode-conditional argument. Token delta is marginally worse than (ii) — two
argument descriptions instead of one discriminator.

**Verdict: REJECT, and it does not rescue the pair.** It trades schema-level
requiredness (real, enforced before the call) for type distinctness (real, also
enforced) plus a turn saving that is speculative. That is a lateral move, not an
improvement, and it costs the same 66 lines. The pair's problem was never which
of the two shapes to pick — it is that both cost 66 lines across three trees to
save approximately nothing, while N1, N2 and N6 save real tokens for less work.

#### (iii) `database_search` + `retrieve_user_inputs`

```
sessions(query=None, n=None, session_ids=None, images_flag=False,
         attempt_specific_flag=False, metafilters=None[, extract_text=False]) -> str
```

**Required kept: 0 of 3.** A no-argument call becomes syntactically valid. **Prompt sites: ≈77.** **Token delta: ≈ +40/agent.**

*Pro:* puts the search and its documented follow-up under one name. *Cons:* zero requiredness survives; it merges the direct-return tool with a dispatcher stub; and it **orphans `retrieve_attempt`**, splitting the one pair that already shares a cap, a fragment, a dispatcher and a gate. *Failure mode:* `sessions(session_ids=[...], n=5)` — `n` is meaningless in retrieve mode, silently ignored, and the model believes it capped the response.

**Verdict: REJECT.** Strictly worse than (ii) on requiredness (0 vs 2) and worse than doing nothing on tokens.

#### (iv) `database_search` + `retrieve_attempt`

```
attempts(query=None, n=None, attempt_ids=None, images_flag=False,
         attempt_specific_flag=False, metafilters=None) -> str
```

**Required kept: 0 of 3.** **Prompt sites: ≈69.** **Token delta: ≈ +40/agent.**

*Pro:* `database_search` already has `attempt_specific_flag`, so an "attempts" surface has surface coherence. *Cons:* zero requiredness; it splits the genuinely-paired pair and leaves `retrieve_user_inputs` alone carrying the OCR variant; and `attempt_specific_flag` and `attempt_ids` now say overlapping things — one narrows a *search* to attempt anchors, the other *fetches* named attempts. *Failure mode:* `attempts(query="blade tip failures", attempt_ids=[412])` with the flag left `False` — three arguments implying three different operations, none contradicted by the schema.

**Verdict: REJECT.** The worst of the four.

#### (v) Non-merge shapes

**N1 — shrink `database_search.md`, already scoped by the owner.** `PROMPT_SHRINK_PROPOSAL_7agent.md:664`: cut 758 → ~180 tok, keeping the TAKE/LEAVE-BEHIND principle ("past sessions are a blueprint for HOW to act, never values to copy") and "fetch the pixels before trusting a visual claim", dropping the argument and return-shape prose the schema already carries. The proposal's 4,624 figure is **(758−180) × 8, and it reproduces exactly**. **Correction: that is eight-agent arithmetic.** At the shipped `database_access.json`, six chain agents carry the fragment, so the real figure the day RAG flips on is **3,468**. Either way it is 4–16× any merge, and every merge measures negative. One caveat: the proposal's second half — "merge the three identical per-agent variants into one" — saves **zero** assembled tokens (each agent still receives a copy) and the two truly identical variants belong to the two agents already switched off. Zero prompt-site churn, zero code, no stale-wording tail.

**N2 — gate the ungated RAG prose.** Four model-facing blocks name the three tools *outside* `<<HAS_DBA>>`, so they ship at `RAG_ENABLED=False`, next to `$hard_constraints_generic` telling the agent its tool list is exhaustive:

| site | size | gate is at |
|---|---:|---|
| `agents/receptionist/prompt.md:374-394` ("## Your DBa scope") | 1,291 ch ≈ 323 tok | `:417` / `:426` |
| `agents/5agent/receptionist/prompt_5agents.md:393-413` | 1,290 ch ≈ 322 tok | `:436` / `:445` |
| `agents/orchestrator/prompt.md:174-177` | 221 ch ≈ 55 tok | `:530` / `:539` |
| `agents/conductor/prompt_5agents.md:461-464` | 266 ch ≈ 66 tok | `:911` / `:920` |

Only `agents/7agent_reduced/receptionist/…:349-366` is correctly gated. **Correction to the prior pass, which reported this as "−748 tok saved today":** those are source copies across three topologies, and **only one topology runs per session**. Runtime saving is **≈378 tok/session on topology 7** (receptionist + orchestrator) and **≈388 on topology 5**. Half the headline — but still the only item in B1 that saves anything *today*, and the fork manifest already records this exact fix for the reduced tree (D-3, B6), so the standard and 5-agent trees are simply behind. Four files, eight marker lines. The Receptionist block must be wrapped as a unit; an orphan marker renders as literal prompt text.

**N3 — fix a required argument's name in four prompts.** Four model-facing files instruct `retrieve_user_inputs(session_ids=[...])`. The argument is `sessions_ID_list`, and `retrieve_tool_dispatcher.py:76-86` hard-fails without it ("Error: 'sessions_ID_list' must be a non-empty list of session_id strings"). Sites: `DC_prompt_fragments/tools_config/database_search.md:35`, `database_search_dc_input_inspector.md:6`, `database_search_user_input_inspector.md:21`, `agents/5agent/tools_config/database_search_creator_5agents.md:14`. **`sessions_ID_list` appears in zero prompts.** Four one-word edits, zero tokens.

**N3b — MISSED BY BOTH PRIOR PASSES, and by the stated policy this is worse than N3: the schema itself names a file that does not exist.** Both `retrieve_user_inputs` docstrings — `retrieve_user_inputs.py:678` and `:714` — tell the model the tool returns "the session's user-supplied text (``user_query.txt``)". The tool actually fetches `<sid>/user_inputs/queries.txt` (`_r2_key(sid, "user_inputs", "queries.txt")` at `:511`; module docstring `:9`) and emits `<missing path=".../queries.txt"/>` at `:248`. A wrong filename **in the schema** is re-sent every turn to every bound agent. Two-word fix; ships with N3.

**N4 — delete the 17 dead `$retrieve_attempt_tool` slots.** Zero tokens (the fragment is 0 bytes by design), but it removes 17 of the 39 lines that make a pair merge look expensive, and finishes a job the reduced tree has already done in 5 of 8 prompts.

**N5 — share the retrieve pair's *code*, not its schema.** The genuinely duplicated helpers between the two modules are `_r2_key`, `_r2_bucket_and_client`, `_r2_get_text`, `_r2_get_bytes`, `_attr`/`_wrap_cdata`, `_count_tokens` and `_log_to_rag_queries` — roughly 89 lines, or ~142 if `_build_xml` is included. Lift them into a shared module; both tools keep their own name, docstring and typed id list. Zero model tokens, zero prompt sites, zero schema change, and the id types stay distinct. **Note the prior pass's scope was wrong in two directions that cancelled:** it counted `_trim_to_cap` as duplicated (the two versions are barely similar — `retrieve_attempt`'s carries an extra `render_views_in_scope` parameter) and excluded `_build_xml` (which is highly similar). "~144 lines" was right by accident. Keep the shared module to R2 access, escaping, token counting and `rag_queries` logging; leave the XML builders per-tool.

**N6 — unbind instead of merge.** Dropping the trio from one agent removes **≈1,160–1,250 tok of schema *plus* the fragment layer** — `database_search.md` 758 + `retrieve_user_inputs.md` 183 + that agent's overlay (57–521 tok) = **≈2,150–2,700 tok/agent/turn**. The prior pass counted only the schema half, understating this by roughly 2×. It is an order of magnitude larger than any merge, in the right direction, with zero prompt edits (`is_enabled_for` strips binding and prompt region together) and full reversibility from the settings UI. Two of the eight are already off, and their overlays are byte-identical boilerplate — evidence the owner already reached this conclusion for them.

**N7 — MISSED: delete the dispatcher instead of merging around it.** `append_pending_images(agent, image_blocks, image_paths)` needs only the agent object, and every factory call site already has `self` in scope. Passing `self` into `make_retrieve_*_tool` would let each tool return real XML and buffer its own images, removing the dispatcher module, the two hard-coded names at `:208-209`, the load-bearing branch ordering in twelve run loops, and reviving both dead flowchart labels — zero prompt sites, zero schema change. This dissolves the third-largest objection to (i). It should be judged on its own merits, and the merge question re-asked afterwards against a cleaner baseline.

**N8 — the pair the census flagged and both passes dropped: `retrieve_attempt` vs `read_attempt`.** `PROMPT_SHRINK_PROPOSAL_7agent.md:1152` ends recommendation 6 with: "when RAG is on, `retrieve_attempt` overlaps `read_attempt` (past-session vs this-session) — re-check that pair before enabling `RAG_ENABLED`." This is the strongest confusion case anywhere in the brief and it is unpriced. `read_attempt(n, file)` takes a per-session attempt number plus a bare filename (`attempts_tool.py:205`, `:256`); `retrieve_attempt(attempts_ID_list)` takes global BIGSERIAL ids. Two attempt-numbering spaces, two similarly-named tools, both bound to the same agents when RAG is on, both returning description + parameters + renders. That is exactly the "two id spaces under one surface" hazard that correctly sinks option (ii) — except here it exists *across tools, today*. Neither prior pass named it. B1 cannot be closed without pricing it, and it sits on the B1/B2 seam.

### The prompt-only alternative, priced against every merge option

| shape | tok/agent/turn | fleet effect when RAG is on | model-facing lines to edit | requiredness |
|---|---:|---|---:|---|
| (i) three-way merge | 0 to **+100** | up to **+600** | ≈98 | 4 → 1 |
| (ii) retrieve pair | **+30** | **+180** | 66 | 2 → 2 ✓ |
| (ii-b) retrieve pair, typed lists | **+35** | **+210** | 66 | 2 → **0** ✗ |
| (iii) db + rui | **+40** | **+240** | ≈77 | 3 → 0 |
| (iv) db + ra | **+40** | **+240** | ≈69 | 3 → 0 |
| N1 fragment shrink | 0 | **−3,468** | 52 (one file) | unchanged |
| N2 gate the prose | 0 | **−378/session, today** | 8 (four files) | unchanged |
| N3 + N3b name fixes | 0 | 0 | 6 | unchanged |
| N6 unbind one agent | **−2,150 to −2,700** | −2,150 to −2,700 per agent | 0 | unchanged |

Every merge is negative-value. The comparison the owner asked for — merge versus the prompt-only edit he already scoped — is not close: **N1 alone is 4–16× the largest merge saving and points the other way**, and unbinding two agents beats N1 outright.

### Recommendation for B1

**Do not merge, in any of the four shapes** — but the prior reasoning was partly wrong and the pushback was justified. Findings, in order of what they change:

1. **The plumbing objection is retired.** All twelve run loops dispatch before the by-name lookup; binding is name-agnostic. A merged tool would work today.
2. **Requiredness is preserved by (ii) and only by (ii).** The blanket "no argument can stay required" is false for the retrieve pair, and that was the prior pass's main reason for rejecting it.
3. **(ii) still fails on value, not on mechanism**: ~zero tokens, 66 lines across three trees, loss of the `list[str]` / `list[int]` distinction between two id spaces that appear in the same search response, and F30 about to add a third mode-conditional argument.
4. **Order of work:** N3 + N3b (free, and N3b is a schema-level contradiction) → N2 (only live win, ~378/session) → N4 (hygiene, halves any future pair-merge bill) → N6 per agent when RAG goes live → N1 when RAG goes live → N5 → evaluate N7 → **price N8 before closing B1**.
5. **If the owner still wants a merge:** (ii), only (ii), after F30 and after N4.

---

## Part 2 — B2: the attempt tools

### Current state

`agents/shared/attempts_tool.py`, 365 lines, three tools:

| tool | line | signature | required |
|---|---:|---|---|
| `list_attempts` | `:161` | `() -> str` | none exist |
| `read_attempt` | `:205` | `(n: int, file: str) -> str` | **both** |
| `new_attempt` | `:310` | `(slug="attempt", description="") -> str` | **neither** |

**Returns.** `list_attempts` emits, per attempt, three lines: `Attempt n: <folder>` (`:194`), `Has: <roles>` (`:195`), `Files: <names>` (`:198`). `read_attempt` branches on suffix: text/`.json`/`.md`/`.csv`/`.log`/no-suffix inline with a header (`:291-300`); image suffixes return the absolute path only (`:268-274`); mesh suffixes `.obj`/`.stl`/`.ply` return path + size, never inline (`:275-290` — the 2026-05-31 incident defence). Path separators and `..` rejected at `:237-242`.

**Docstring sizes** (AST-measured): `list_attempts` raw 790 ch = **198 DOC**, clean 741; `read_attempt` raw 1,043 = **261 DOC**, clean 970; `new_attempt` raw 1,099 = **275 DOC**, clean 1,026. The census's 200 / 263 / 277 reproduce to within 1%.

**Per-turn cost.** SCHEMA basis: `list_attempts` ≈ 213, `read_attempt` ≈ 288, pair ≈ **500/agent**; `new_attempt` ≈ 304. Shipped 7-agent config (`settings.py:867` `SYSTEM_TOPOLOGY=7`, `:120` `DC_INSPECTOR_ENABLED=True`) → 8 holders of the pair, 2 of `new_attempt` = **≈4,600 tok/turn**, with RAG off.

**Bindings.** Twelve agent classes bind the pair: `architect.py:393-394`, `conductor.py:348-349`, `creator.py:187-188`, `dc_input_creator.py:150-151`, `dc_input_inspector.py:128-129`, `dc_output_inspector.py:241-242`, `designer.py:178-179`, `orchestrator.py:449-450`, `planner.py:196`, `receptionist.py:127-128`, `tool_caller.py:110`, `user_input_inspector.py:154-155`. `new_attempt` is bound by creator, dc_input_creator, designer, and the Orchestrator as a fallback. **The 5-agent and 3-agent hubs already withhold it deliberately** — `conductor.py:33`/`:339` and `architect.py:45`/`:386` both say so in comments.

**Prompt footprint**, re-counted: `list_attempts` 43 occurrences, `read_attempt` 66, `new_attempt` 28 = **137 across 27 files**; the pair alone = **109 across 25 files**. No overstatement here — these reproduce exactly.

**Two defects shipping today.**

- **The impossible glob.** `agents/receptionist/prompt.md:299` and `agents/5agent/receptionist/prompt_5agents.md:317` both order `read_attempt(n, "render_*.png")`. There is no glob expansion: `attempts_tool.py:256-265` does `target = folder / file_clean` and returns "Error: 'render_*.png' not found in attempt N. Files present: [...]". Exactly two sites. Already filed as **CON-26** at `PROMPT_SHRINK_PROPOSAL_7agent.md:15716-15750`.
- **A one-line self-contradiction in the Planner.** `agents/planner/prompt.md:552-553` says "or a render filename for its absolute path (you can't view images; only the DCOI can)". The Planner **does** bind `view_images` — `planner.py:201` calls `build_user_inputs_tools(self.AGENT_KEY)` — and `prompt.md:462` tells it to call `view_images(paths)`. The identical sentence is *correct* in `agents/conductor/prompt_5agents.md:893-894`, because `conductor.py` never calls `build_user_inputs_tools`. This is a copy-paste that went stale on the way into the Planner. Neither prior pass found it; it is free to fix.

**Where the attempt-folder object model is restated:** the module docstring (`attempts_tool.py:1-29`), `list_attempts`' own preamble (`:164-171`), `DC_prompt_fragments/dc_config/output_file_locations.md`, `DC_prompt_fragments/tools_config/agent_tools_overview.md:1-10`, `agents/planner/prompt.md:526-568`, `agents/conductor/prompt_5agents.md:868-910`, `agents/tool_caller/prompt.md:118-135` and its two twins. The census already priced the prompt half of this at **1,931 fleet tokens** (`PROMPT_SHRINK_PROPOSAL_7agent.md:103`, "Attempt-folder model + list_attempts/read_attempt narration | 419 | 7 | 1,931") with a fix specified at `:682-683` (create `dc_config/attempts_model.md` ~130 tok, absorbing and deleting `output_file_locations.md`).

### Options

#### (a) Merge into one tool with optional args

```
attempts(n: int | None = None, file: str | None = None) -> str
```

**Required kept: none.** `read_attempt`'s two required arguments both go optional; `list_attempts` had none to lose. **Prompt sites: 109 occurrences / 25 files, three trees, plus 12 `.py` binding sites, plus two shared fragments that assert the pair by name** (`agent_tools_overview.md:1-5` "bound to every agent"; `available_agents_5agents.md:72-76` "Every agent also holds…"), plus the out-of-repo `propeller-dc` MCP server, which exposes `list_attempts` and `read_attempt` under those names and desyncs silently.

**Token delta:** a merged, rewritten docstring lands ~35 tok/agent below the same two tools rewritten separately — **≈280 fleet tok/turn**, essentially one saved JSON envelope, partly eaten by the "which arguments when" prose the merge forces you to add.

*Failure mode:* `attempts(n=3)` is schema-valid and ambiguous — the model that means "read attempt 3's parameters" gets a directory listing and burns a turn. `attempts(file="parameters.json")` is schema-valid and must be rejected by a hand-written string. **Argument omission is a demonstrated, recurring failure class in this fleet:** three prompts carry a HARD rule about it verbatim (`agents/dc_input_creator/prompt.md:361`, `agents/creator/prompt_5agents.md:572`, `agents/7agent_reduced/dc_input_creator/…:334`) and **six** code sites hand-write the "YOUR call … omitted the" error (`creator.py:412`, `:453`; `dc_input_creator.py:383`, `:435`; `designer.py:479`, `:520`). That rule works *because* the schema made the argument mandatory and the error could name it.

**Precedent:** `d5de05c` (verified: **38 files changed, 547 insertions, 380 deletions**) merged generate+render for a tool bound to **one** agent and still left stale wording found months later. This pair is bound to twelve classes.

**Verdict: NO**, and specifically *worse than leaving the shape alone*. It is the most expensive item in B2 per token returned and the only one that costs requiredness.

#### (a2) Merge with a `Literal` discriminator

```
attempts(action: Literal['list','read'], n=None, file=None) -> str
```

**Required kept: 1.** `n` and `file` become *conditionally* required, which a signature-derived schema cannot express. **Token delta: worse than (a)** — the enum plus "REQUIRED when action=read" prose costs more than it saves, so ≈+220 fleet rather than +280 saved. Same 25-file fan-out, same loss of enforced requiredness, plus a per-call argument carrying no information the tool name already carried.

**Verdict: NO.** Strictly worse than (a), which is itself a bad trade.

#### (b) Leave the tools, rewrite the docstrings

Signatures unchanged; `n` and `file` stay required. **Prompt sites: 0** — no `prompt.md` quotes the docstring text.

**The census's 3,704 → 1,824 figure is VERIFIED and accurate — not conservative.** 3,704 = (263+200) × 8 on the census's raw basis; my independent measure of the same docstrings gives (261+198) × 8 = 3,672, within 1%. I then measured the census's own replacement text (`PROMPT_SHRINK_PROPOSAL_7agent.md:806-817`, `:825-832`) on the same raw basis: **130 + 94 = 224/agent against its estimate of 228** — accurate to under 2%. Consistent arithmetic: 3,672 → 1,792, saving **1,880**. Add the `new_attempt` row (277 → ~106, ×2 = **342**) and (b) is worth **≈2,222 tok/turn**.

**One correction the prior pass got backwards** — see Part 3, item 5 — and **one wording change it was right to demand, narrowed:**

- Keep the *fact* that a mesh returns a path (the 2026-05-31 narrative can go; the behaviour is enforced at `:275-290`), or an agent will request one expecting content.
- The image clause is **fine as written and has already been adjudicated**. `attempts_tool.py:215-218` says "hand it to a tool that loads images (e.g. ``view_images``)" — generic with an example. `extra_utilities/TODO_known_issues.md:4511-4514` states verbatim, in F79's own entry: "The SCHEMA needed no change: `attempts_tool.py:215-217` says 'hand it to a tool that loads images (e.g. `view_images`)', which is generic with an example and ships to the four agents that genuinely bind it."
- The **mesh** clause at `:222-224` is the one narrow spot: "Hand the returned path to ``visualize_3d_model``" names a tool bound to one agent (`receptionist.py:56`, the sole import) — though it offers "or to a downstream tool that operates on the mesh" in the same sentence, and the Receptionist is both the sole holder *and* the agent most likely to make that call. LOW severity; reword to match the image clause's shape.

*Pros:* one file; lands in all three topologies at once because every agent imports the same module — including the 3-agent tree, which has no prompts yet; removes the largest genuine duplication (the `list_attempts` preamble re-explaining the attempt-folder model that seven prompt files already carry); zero requiredness change; zero stale-prompt risk.

*Con:* does not reduce the tool count.

**Verdict: DO THIS FIRST.** It dominates both merge shapes: ~1,880 vs ~280 marginal, zero prompt churn vs 25 files, no requiredness loss. **Pair it with the prompt-side twin** at `PROMPT_SHRINK_PROPOSAL_7agent.md:103` / `:682-683` — the 1,931-token `attempts_model.md` consolidation. (b) alone leaves roughly two-thirds of the attempt-folder duplication in place, in the prompts. Sequencing consequence: doing (b) first roughly halves what (c) is worth.

#### (c) Selective unbinding

**The "~463 tok per agent" figure is VERIFIED** (463 = 263 + 200, census basis; my SCHEMA measure is ~500). **But it is only valid before (b).** After the rewrite the pair costs ~265 SCHEMA/agent, so unbinding is worth roughly **half**. Any plan that adds (b) and (c) together double-counts.

Evidence per candidate, from the prompts:

- **DC Input Inspector — strongest case.** `agents/dc_input_inspector/prompt.md` and `agents/7agent_reduced/dc_input_inspector/…` contain **zero** occurrences of `list_attempts` or `read_attempt`. (There is no 5-agent DCII; the Creator absorbs it.) It binds both tools with no instruction in any tree. *Caveat the prior pass missed:* it carries `$retrieve_attempt_tool` at `prompt.md:377`, so with RAG on it is expected to inspect *past-session* attempts while holding no instruction for *this-session* ones. That asymmetry is either the justification for unbinding or a defect in the DCII prompt; it should be resolved first.
- **Orchestrator — contested.** All mentions are Receptionist-directed (`prompt.md:314`, `:333`; reduced `:285`, `:290`). But `prompt.md:311-333` makes it a HARD requirement that the hub emit **every** attempt's number and absolute path to the Receptionist, and unbinding removes its only filesystem ground truth when a hand-off is garbled. More importantly, **the repo's two recorded resolutions of "hub prompt vs hub bindings" both went toward *more* binding**: F71 (`TODO_known_issues.md:4170`, **FIXED 2026-08-11 in `ed8569a`**) bound the missing tool, explicitly citing the 5-agent Conductor precedent, and it lists "reword all three sites to `list_attempts` / `read_attempt`, which the Orchestrator does hold" as the alternative it considered. The prior pass cited F71 as *live* support for unbinding; it is fixed, and it cuts the other way.
- **Tool Caller — genuine judgement call.** It has a 172-tok section at `agents/tool_caller/prompt.md:118-135`, which already calls the tools "diagnostic helpers, not part of the normal generate → render flow" — **so the reduced tree did not diverge**; both say the same thing. The prior pass claimed the reduced tree had demoted them and the standard tree had not.

**Sequencing trap, first-class:** the `.py` binding change and the prose deletions must land in **one commit**. `conductor.py:350-357` records what the reverse mistake cost: a hub prompt naming unbound tools produced "a wrong call, an error, then a wasted routing hop" on every design turn. Two shared fragments must change in the same commit (`agent_tools_overview.md:1-5`, `available_agents_5agents.md:72-76`) because both assert the pair is universal.

**Verdict: DCII yes, after resolving its RAG asymmetry. Orchestrator: put to the owner with F71's record in front of him — it is not the clean no-op the prior pass claimed. Tool Caller: separate decision.** Worth ~530 tok/turn (two agents, after (b)) or ~1,000 (before it).

#### (d1) Add glob matching to `read_attempt`'s `file` argument

Both arguments stay required; `fnmatch.filter` over the folder's filenames at `:256`, then the existing suffix branching per match. ~8 lines, one file.

**Token delta: NEGATIVE at the schema** — roughly **+17 tok/agent, +136/turn** across 8 agents, permanently.

**A prompt-only fix already exists and both prior passes missed it.** **CON-26**, `PROMPT_SHRINK_PROPOSAL_7agent.md:15716-15750`, diagnoses the same wildcard from the same evidence and prescribes a two-line prompt edit: "``read_attempt(n, "render_isometric.png")`` — one exact filename per call, no wildcards". Cost: two lines, two files (with the 5-agent twin), zero schema tokens, zero code, permanently.

**The turn-saving justification does not hold up.** The prior pass valued (d1) at "two saved Receptionist turns per attempt report ≈ 45k input tokens against a 22,618-token system prompt (`baseline_tokens.json`, verified) ≈ 150× the merge." Three problems: both wildcard sites mark the render read **"(optionally)"** (`receptionist/prompt.md:298`, `prompt_5agents.md:316`), so it is not a per-report call; `receptionist/prompt.md:291-293` says "THAT block — **not the filesystem** — tells you which attempts exist", making the filesystem tools the fallback path; and the reduced tree's `:281-284` lists three filenames as *alternatives* after "(optionally)", not three mandatory calls. The 45k figure is an unmeasured worst case presented as the decisive number.

**Verdict: fix the defect with CON-26's prompt edit, not with a glob.** Revisit a glob only if a real run shows the Receptionist actually making three render calls. It is the right *diagnosis* — "changing `read_attempt` beats merging it" — attached to the more expensive of two fixes.

#### (d2) Slim the `list_attempts` return

The proposal was to drop the `Files:` line as redundant with `Has:`. **Two problems, both disqualifying as stated.**

**First, the derivation runs the other way.** `attempts_tool.py:137-155`: `_classify_files` builds `flags` **from** `names`. `Has:` is derived from `Files:`; `Files:` carries strictly more information — which render views exist, and any non-canonical file. The proposal deletes the source and keeps the derivative. The suggested mitigation ("emit `Files:` only when the folder holds something outside the canonical four") is not computable from the existing code: `:145-149` matches renders by `render_` prefix with no fixed count, so "the canonical four" has no representation to test against.

**Second, it is not prompt-site-zero.** Four model-facing prompts describe the file list as part of the return: `agents/tool_caller/prompt.md:125`, `agents/5agent/tool_caller/prompt_5agents.md:125`, `agents/planner/prompt.md:550`, `agents/conductor/prompt_5agents.md:891`. Deleting either line makes all four stale — the exact failure `conductor.py:350-357` records.

**Third, there is a live consumer.** `agents/dc_output_inspector/prompt.md:138-140` tells the DCOI to "use ``list_attempts`` / ``read_attempt`` to pull a PRIOR round's render" during the precision loop; the filenames are how it does that.

**The defensible version is the reverse:** drop `Has:` (≈55 chars ≈ 14 tok per attempt), keep `Files:`. That saves less — ~14 tok/attempt, so ~280 on a 20-attempt precision job — and still touches the same four prompt sites. Worth doing only as part of (b)'s single-file pass, if at all.

**Verdict: NO as proposed; the reverse is marginal.** The honest observation underneath survives and is worth recording: **the census audited schemas and prompts but never tool *returns*.** `list_attempts` prints a derived line and the line it was derived from, and that lands permanently in the caller's context. That is a whole unexamined category, and it deserves its own pass rather than a one-line fix here.

#### (d3) Roles-based accessor

```
read_attempt(n: int, role: Literal['parameters','description','mesh','renders']) -> str
```

*Replacement form:* both arguments stay required and the wrong-filename error class disappears — but it forecloses reading anything outside four canonical roles, in a folder whose contents are explicitly allowed to grow (`extra_utilities/db_design/database_design_notes.md` enumerates it as a schema; the module docstring `:6-8` says "and any further metrics produced for the same set of inputs"). *Additive form* (`file=None, role=None`): both become optional — option (a)'s requiredness loss wearing a different hat. Same 25-file fan-out either way, because every prompt names `file` by example.

**Verdict: NO in both forms.**

#### (d4) Unbind `new_attempt` from the Orchestrator

**This is A5 in the owner's own proposal, and the prior pass priced it at roughly half.** `PROMPT_SHRINK_PROPOSAL_7agent.md:16168` and `:16177`: **"A5 · Unbind new_attempt from the Orchestrator … TOOL_UNBIND · 713 · low · 13 [files]"**, fully scoped at `:16177-16340`. The prior pass listed four sites and ~436 tokens — a **~3× understatement of the fan-out**, the specific error class the brief warned about, here in the opposite direction from the warned instance. A5's file list includes `orchestrator.py:33` and `:451`, `routing_orchestrator.md:26-29`, `orchestrator/prompt.md:134-146`, `dc_config/output_file_locations.md:3-6`, `hard_constraints_tools.md:11-19`, `dc_input_creator/prompt.md:234-243`, `dc_input_creator.py:96-101`, `step_caps.py:109-113`, `attempts_tool.py:6-10`, and `orchestrator/prompt.md:156-157`.

The case for it is strong and not primarily about tokens: three prompt blocks exist solely to explain that a bound tool must almost never be used, and the 5-agent Conductor (`conductor.py:33`, `:339`) and 3-agent Architect (`architect.py:45`, `:386`) already withhold it — the 7-agent hub is the outlier. A5 frames the risk the opposite way from the prior pass: "A hub that can mint folders produces empty attempts nobody writes into, and every prompt then has to spend prose saying 'but don't'" (`:16237-16239`).

**Verdict: PUT TO THE OWNER as a behaviour question, at A5's numbers (713 tok, 13 files).** It removes a documented recovery path for "the DCIC blocks, loops, or errors on creation". Neither pass established whether that fallback has ever fired — the session logs would say.

#### (e) Recommended combination

Signatures unchanged; both of `read_attempt`'s arguments stay required throughout; no argument anywhere becomes optional.

| step | files | prompts | tok/turn |
|---|---|---|---:|
| 1. **(b)** docstring rewrite, mesh clause reworded | 1 | 0 | **−1,880** (+342 for `new_attempt`) |
| 2. **(b′)** the prompt-side twin: `attempts_model.md` per proposal `:682-683` | ~8 | 7 | **−1,931 fleet** |
| 3. **CON-26** prompt fix for the wildcard | 2 | 2 | 0 |
| 4. **free** `agents/planner/prompt.md:552-553` contradiction | 1 | 1 | 0 |
| 5. **(c)** unbind DCII (Orchestrator: owner's call) | 1 `.py` + 6 prompt, one commit | 6 | **−265** |
| 6. **(d4)/A5** unbind `new_attempt` from the hub | 13 | 11 | **−713**, owner's call |
| **merge, layered on all of this** | 25+12 | 25 | **−280** |

Steps 1, 3 and 4 touch one file each and can land before any structural decision is taken. **Failure mode of the combination:** step 5's binding change and prose deletions must be one commit (`conductor.py:350-357`).

### Recommendation for B2

**Do not merge `list_attempts` and `read_attempt`, in either form — but the prior "leave them alone" verdict is also wrong, and the owner's instinct that they should change is right.**

The merge is worth ~280 fleet tokens per turn, essentially one JSON envelope, partly eaten by the disambiguation prose it forces. Against that: 109 occurrences across 25 prompt files in three trees, twelve binding classes, two shared fragments asserting the pair by name, an out-of-repo MCP server that desyncs silently, and the conversion of two required arguments into optional ones in a fleet where argument omission is a documented recurring failure with six hand-written error sites. `d5de05c` cost 38 files for a tool bound to one agent.

Instead: **(b) the docstring rewrite at the census's own number (~1,880), paired with the census's 1,931-token prompt-side twin; CON-26's two-line prompt fix rather than a glob; the free Planner contradiction fix; DCII unbinding after its RAG asymmetry is resolved; and A5 as a behaviour decision at 713 tokens across 13 files.** That is roughly 4,500 tokens across schema and prompts, against the merge's 280, and it keeps every argument required.

The census's own recommendation 6 (`PROMPT_SHRINK_PROPOSAL_7agent.md:1152`, "list_attempts vs read_attempt is the one pair I would KEEP") is **confirmed**, and now has arithmetic behind it rather than an assertion. Its rider — re-check `retrieve_attempt` vs `read_attempt` before enabling RAG — is **not** addressed by anything here and is the strongest remaining merge candidate in the whole brief (N8, Part 1).

---

## Part 3 — what this changes about the earlier verdicts

Both merge verdicts survive. Nine specific claims do not.

1. **"The three-way merge is hard because of the plumbing" — OVERTURNED.** All twelve run loops dispatch before the by-name lookup; binding is name-agnostic. The objection is semantic and token-based. The owner was right to push.
2. **"None of the four arguments can stay required in a merged schema" — HALF OVERTURNED.** True for (i), (iii), (iv). **False for (ii)**, which yields two required arguments from one each — and that was the prior pass's stated reason for rejecting the very pair the owner asked about.
3. **"RAG has never shipped True; there is zero empirical evidence" — OVERTURNED, and this is the most consequential correction.** `git show 905446d:workflow_settings/settings.py:81` is `RAG_ENABLED: bool = True`, committed **2026-06-03**; `77e34d5` flipped it to False on **2026-07-26**. That is a **53-day window**, and `git show 77e34d5^:workflow_settings/database_access.json` is byte-for-byte today's file, so six agents held the trio throughout. `git log -S` reports commits where the occurrence *count changed* — two hits for a string added then removed is proof it **was** committed; the command was run and read backwards. Every session record also carries its own `rag_enabled` flag (`agents/shared/session.py:133`, `:265`), and `rag_queries.tool_name` exists precisely to tell the three tools apart. The evidence is one query and one log-grep away, not a hypothetical future experiment.
4. **"−748 tok, saved today" for the ungated prose — HALVED.** Those are source copies across three topologies; one topology runs per session. Real runtime saving: **≈378 (topology 7) / ≈388 (topology 5)**. Still the only live win in B1.
5. **"The census's 3,704 → 1,824 is 9% conservative" — OVERTURNED as a basis error.** The prior pass measured the *current* docstrings raw (198/261, matching the census) but the *replacement* cleandoc'd (208), then compared 208 against the census's raw-basis 228. On a consistent raw basis the replacements measure **224 against an estimate of 228** — under 2% off. The census was right; the "correction" was noise.
6. **"read_attempt's docstring mis-points most of its holders" — LARGELY OVERTURNED.** The cited lines `:271-273` and `:287-288` are **return strings**, emitted once when the tool is called — not the schema, which is `:215-224`. The entire severity argument ("a second copy re-sent every turn") was attached to lines that are never re-sent. And the image clause was already adjudicated in F79's own entry at `TODO_known_issues.md:4511-4514` as needing no change. What survives is one clause: the mesh branch at `:222-224`, LOW.
7. **"F71 is live, and supports unbinding the Orchestrator" — OVERTURNED twice.** `TODO_known_issues.md:4170`: "FIXED 2026-08-11 in `ed8569a`." And the fix was to **bind** the missing tool, citing the 5-agent Conductor as precedent. Both recorded resolutions of this bug class went toward more binding, not less.
8. **"(d4) is ~436 tokens across 4 files" — UNDERSTATED ~3×.** It is A5 in the owner's own proposal: **713 tokens, 13 files** (`PROMPT_SHRINK_PROPOSAL_7agent.md:16168`, `:16177-16340`).
9. **"(d2) has zero prompt sites" — FALSE.** Four prompts describe the return: `tool_caller/prompt.md:125`, `5agent/tool_caller/…:125`, `planner/prompt.md:550`, `conductor/prompt_5agents.md:891`. And the derivation runs the opposite way from the claim — `Has:` is built *from* `Files:` at `attempts_tool.py:137-155`.

Three things neither prior pass found, all cheap:

- **`retrieve_user_inputs.py:678` and `:714` name `user_query.txt` in the schema; the tool fetches `queries.txt`** (`:511`, `:248`). A wrong filename in a schema outranks a wrong argument name in a prompt under "schema owns mechanics".
- **`agents/planner/prompt.md:552-553`** tells the Planner it cannot view images; `planner.py:201` binds `view_images` and `prompt.md:462` tells it to call it. One line.
- **CON-26 already scopes a two-line prompt fix for the wildcard** (`PROMPT_SHRINK_PROPOSAL_7agent.md:15716-15750`), which is cheaper than the glob the prior pass called "the highest-value change in B2".

One meta-point worth recording: both prior passes benchmarked schema savings against "the 87k prompt fleet". Those budgets are disjoint by construction — `PROMPT_SHRINK_PROPOSAL_7agent.md:91` says plainly that tool schemas are "sent separately from the prompt text" with 8,308 tokens recoverable. Against its own budget, (b) is ~22% of recoverable schema, not 2%. The *ordering* of the recommendations does not change; the dismissiveness does.

## Part 4 — Open questions for the owner

1. **Will you look at the 53-day RAG window before deciding B1?** `SELECT tool_name, caller_agent, count(*) FROM rag_queries WHERE ts BETWEEN '2026-06-03' AND '2026-07-26' GROUP BY 1,2`, plus the session logs whose `rag_enabled` is true. If the model never confused the three, the choice-space argument for merging evaporates; if it did, that is the first real evidence either way and it should drive the shape.
2. **N8 — do you want `retrieve_attempt` vs `read_attempt` priced before B1 closes?** Your own census flagged it at `:1152` and both analysis passes dropped it. Two attempt-numbering spaces, two similarly-named tools, same agents, overlapping returns. It is the strongest merge/confusion case in the brief and it straddles B1 and B2.
3. **N7 — should the retrieve dispatcher go away entirely?** Closing over `self` in the factory removes 229 lines, both hard-coded names, the load-bearing branch ordering in twelve run loops, and two dead flowchart labels, at zero prompt and zero schema cost. It also dissolves the third-largest objection to a three-way merge. Judge it on its own merits, then re-ask the merge question.
4. **N6 — which agents actually need the trio?** Unbinding one is worth ~2,150–2,700 tok/agent/turn, an order of magnitude more than any merge. Two are already off. I have deliberately not ranked the rest by role: that is your read of each prompt, and the `rag_queries` data is a better input than either of ours.
5. **(c) — the Orchestrator: unbind or keep?** F71's own record says the last two resolutions of this bug class went toward binding, and `prompt.md:311-333` makes the hub responsible for emitting every attempt's number and absolute path. Is `list_attempts` its ground-truth fallback when a hand-off is garbled, or dead weight?
6. **A5/(d4) — has the Orchestrator's `new_attempt` fallback ever actually fired?** That is a log question, not a token question, and it decides the item.
7. **(b)'s scope: schema only, or schema plus the 1,931-token prompt-side consolidation at `:682-683`?** Doing the docstrings alone leaves roughly two-thirds of the attempt-folder duplication in the prompts, and a reader of the diff will reasonably believe it was handled.
8. **The tool-return category.** `list_attempts` prints a derived line and its source; nothing in the census ever audited what tools *return*, only what they *declare*. Should that be its own pass?
9. **The 3-agent tree cuts against the no-merge verdict and I want to flag it rather than bury it.** `agents/architect/` and `agents/designer/` have **no prompt file at all**, yet both bind all three RAG tools (`architect.py:393`, `designer.py:178`) and both default to DBa-on (`database_access.py:70-84`, `_DEFAULT_VALUE = True` at `:90`). Every prompt-site bill in this document **grows** once those prompts are written — so a merge is cheaper now than it will ever be again. That is a real argument for acting sooner, and it does not change my verdict, but you should have it in front of you rather than discover it later.