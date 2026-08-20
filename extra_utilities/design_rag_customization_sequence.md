# RAG tool customization — agreed sequence

Working document for the RAG / database-search tool customization.  Each step is
proposed with exact before/after and applied ONLY on explicit approval, one at a
time (see the tool-merge rule: a schema change hits every bound agent at once).

Status legend: **TODO** · **IN PROGRESS** · **DONE (commit)** · **BLOCKED**

---

## The settled design

**Retrieval becomes fetch-to-disk + describe, never attach.**

Both retrieve tools: resolve IDs → fetch every artefact → write into a local
folder → return a text listing of the folder's contents → plus printed text.
Nothing is attached to the model's context.  Viewing is exclusively
`view_images`' job — it already provides `side_by_side` (up to 3 panels merged
into one labelled composite via `stitch()`), `layout` (`match_height` /
`native`), per-image `regions` cropping, and its own OCR flag.  **`view_images`
needs no changes at all.**

Decisions taken (owner, this session):

| Decision | Choice |
|---|---|
| Retrieval response | Fetch all to disk, LIST contents, attach NOTHING |
| `images_flag` | Removed from both retrieve tools entirely — nothing to flag |
| Attempt cache | `attempts/_retrieved/<attempt_id>/` |
| User-input cache | `inputs/_retrieved/<session_id>/`, EXCLUDED from `list_input_files` |
| Auto-display | Suppressed — filenames must not match the `render_*.png` glob that the turn artefact-diff surfaces in chat |
| Cache lifetime | Cleared at session start (so idempotency is within-session, which is the stated use case) |
| Re-retrieval | Detected and skipped; the agent gets the SAME message either way — it must never reason about cache state |
| Printed text | Always full, no cap (the 30,000-token response cap backstops it) |
| Saved render views | top + blade sections + isometric.  **Side view dropped.** |
| DCOI scope | `retrieve_attempt` only — NOT `retrieve_user_inputs` |

Distribution (decided earlier, unchanged):

| Agent | search | user_inputs | attempt |
|---|:--:|:--:|:--:|
| Planner | YES | — | — |
| UII | YES | YES | — |
| DCIC | YES | — | YES |
| DCII | YES | YES | YES |
| DCOI | YES | — | YES |
| Receptionist / Orchestrator / Tool Caller | — | — | — |

---

## The sequence

### Step 1 — remove `extract_text` from `retrieve_user_inputs`  **PROPOSED**
Smallest, independent.  DECIDED: remove the flag and let `view_images` do the
OCR — retrieval fetches, viewing reads.  No capability is lost, because
`view_images`' own `extract_text` already defaults to **True** for OCR-eligible
agents, and (after step 2) retrieved user images live under `inputs/`, which is
the only tree `view_images` will OCR.

Note the target code ALREADY EXISTS: the factory's `else:` branch (OCR-off) has
exactly the signature we want, so this is mostly a deletion of the `if` branch.

### Step 2 — retrieval writes folders and stops attaching images  **TODO**
The core change.  Removes `images_flag` from both tools, adds the folder write,
the content listing, and the printed text.  Delivers most of the design above.

### Step 3 — shared implementation module for the two retrieve tools  **TODO**
Pure refactor, no behaviour change.  After step 2 the two tools are near-twins —
both resolve IDs, fetch, write a folder, list it, print text; they differ only
in ID space (`list[str]` vs `list[int]`), folder root, and printed text.  ~90–140
lines of genuine duplication (R2 access, escaping, token counting,
`rag_queries` logging).  NOT a merge — the UII and DCIC must hold different
tools, so the two names and their typed ID lists stay.

### Step 4 — exclude `inputs/_retrieved/` from `list_input_files`  **TODO**
Small guard; belongs with step 2.  Without it the UII would be told a past
session's sketch is part of the CURRENT request.

### Step 4b — add `extracted_inputs.txt` to the R2 save pipeline  **TODO**
NEW, and a PREREQUISITE for step 2's response contract.  The owner wants the
UII's structured extraction (QUANTITATIVE INPUTS / QUALITATIVE DESCRIPTIONS /
DESIGN INTENT) printed per retrieved session — it is more useful to a reasoning
agent than the raw `queries.txt`, because it is already interpreted.  But it is
**not uploaded to R2 at all** today, so it must be added to the artefact
whitelist first.  Consequence to accept: only sessions saved AFTER this change
will have it; already-archived sessions never will.

### Step 5 — save-side work  **TODO — needs its own scoping pass**
The three-render policy (top / blade sections / isometric), the missing
blade-sections setting, and generating absent renders from the attempt's
`parameters.json` at save time.  Touches the DH save pipeline, the R2 artefact
whitelist, the settings UI, AND requires invoking render/geometry code at save
time — a failure or slow call there affects the End-Session flow.  Deliberately
separate: one approval should not cover two subsystems plus a render path.

### Independent of all of the above
**Delete `metafilters` and `attempt_specific_flag` from `database_search`** —
~10 lines in one file, ~224 tok/agent/turn saved, covers all twelve binding
agents automatically because it changes the tool rather than the wiring.  Both
smoke tests call `_database_search_impl` directly, so the tool signature change
does not break them.  Highest return per line in the whole surface.

---

## Resolved questions

1. **`extract_text`** — it is an OCR flag, not the extraction file.  RESOLVED:
   remove it; `view_images` does the OCR when the agent actually looks.
2. **"The printed extracted inputs txt"** — RESOLVED: it means
   `extracted_inputs.txt`, the UII's structured extraction, NOT `queries.txt`.
   It is not in R2 today, hence the new step 4b.

## Response contract (owner's clarification)

- **`retrieve_user_inputs`** — for EVERY requested session, print the
  `extracted_inputs.txt` in full, plus the note for every image that has one,
  each naming the LOCAL path of the saved image it refers to.
- **`retrieve_attempt`** — for EVERY requested attempt, print the full 16
  parameters and the attempt's text description.

---

## Known defects to fix along the way

| | |
|---|---|
| `retrieve_user_inputs` docstrings (`:678`, `:714`) say the tool returns `user_query.txt`; it fetches `queries.txt` (`:511`).  A wrong filename **in the schema**, re-sent every turn. | 2-word fix |
| Four prompts teach `session_ids=`; the required argument is `sessions_ID_list`, which appears in **zero** prompts.  Dispatcher-fatal if copied verbatim. | 4 one-word fixes |
| `dispatch_retrieve_tool` routes on tool name with **no enablement check**, and every agent calls it BEFORE the bound-tool lookup — so unbinding is advisory, not enforcing. | ~12 lines |
