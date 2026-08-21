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

### Step 2a — `retrieve_attempt` writes folders, stops attaching  **DONE**
`retrieve_attempt(attempts_ID_list)` — one required argument, nothing optional.
Artefacts materialise under `attempts/_retrieved/<global_id>/`; the reply adds a
`<folder>` listing every downloaded file with its size, beside the existing
`<description>` and `<parameters>`.  Re-retrieval within a session is detected
and skipped, returning the SAME reply — the agent never learns it was cached.

Also: the artefact auto-display scan skips `_retrieved` (but NOT `_comparisons`,
whose composites are deliberately surfaced); the cache is DELETED rather than
archived during end-of-session archival, which is also what clears it between
sessions; and six prompt fragments that taught
`retrieve_attempt(..., images_flag=True)` were corrected — a prompt teaching a
removed argument is a defect, and this is the `d5de05c` failure mode.

### Step 2b — `retrieve_user_inputs` writes folders, stops attaching  **TODO**
Same shape, after step 4b so it can print `extracted_inputs.txt`.  Note the
`retrieve_user_inputs(..., images_flag=True)` mentions still standing in ~6
prompt fragments must be corrected in that step.

### Step 3 — shared implementation module for the two retrieve tools  **TODO — approved to run after the System-Prompts-UI removal (2026-08-21)**
Pure refactor, no behaviour change.  After step 2 the two tools are near-twins —
both resolve IDs, fetch, write a folder, list it, print text; they differ only
in ID space (`list[str]` vs `list[int]`), folder root, and printed text.  ~90–140
lines of genuine duplication (R2 access, escaping, token counting,
`rag_queries` logging).  NOT a merge — the UII and DCIC must hold different
tools, so the two names and their typed ID lists stay.

### Step 4 — exclude `inputs/_retrieved/` from `list_input_files`  **CLOSED — NO CODE NEEDED**
The worry was that the UII would be told a past session's sketch is part of
the CURRENT request.  It cannot happen: EVERY `inputs/` walker in the system
goes through `file_utils.list_files`, which is non-recursive AND files-only
(`if p.is_file()`), so the `inputs/_retrieved/<sid>/` SUBDIRECTORY is
invisible to all of them by construction.  `load_all_inputs` uses the same
function; `pair_input_images` only ever looks at `inputs/input_images/`.
Verified 2026-08-20 — no guard written, and none needed.  If a future walker
is added that DOES recurse, it must skip `_retrieved`.

### Step 4b — add `extracted_inputs.txt` to the R2 save pipeline  **DONE (`5c6154b`)**
NEW, and a PREREQUISITE for step 2's response contract.  The owner wants the
UII's structured extraction (QUANTITATIVE INPUTS / QUALITATIVE DESCRIPTIONS /
DESIGN INTENT) printed per retrieved session — it is more useful to a reasoning
agent than the raw `queries.txt`, because it is already interpreted.  But it is
**not uploaded to R2 at all** today, so it must be added to the artefact
whitelist first.  Consequence to accept: only sessions saved AFTER this change
will have it; already-archived sessions never will.

### Step 5 — save-side work  **TODO — decisions below are SETTLED (2026-08-21)**

#### The mismatch, measured

|                                          | isometric | top | side | blade sections |
|------------------------------------------|:---------:|:---:|:----:|:--------------:|
| saved to R2 (`ATTEMPT_ARTEFACT_WHITELIST`) | yes | yes | yes | **NEVER** |
| retrieval can request (`_RENDER_FILES`)    | yes | yes | yes | **no entry** |
| setting exists (`RETRIEVE_ATTEMPT_INCLUDE_*`) | yes, `True` | yes, `False` | yes, `False` | **none** |

`render_blade_sections` writes `render_blade_sections.png` (or
`..._grid.png`) into the attempt folder correctly — it is simply absent from
the upload whitelist, so no archived attempt anywhere has one.

#### Owner's decisions — SETTLED

1. **The blade-sections render MUST be uploaded** to R2 with each attempt.
2. **It MUST be retrieved** when an attempt is retrieved.
3. **A corresponding setting MUST exist in the workflow UI**, default **True**
   for both saving and retrieving.
4. **RENDER COMPLETENESS AT SAVE TIME.**  For any attempt about to be saved,
   if a `parameters.json` is present, then ALL renders the save policy
   requires MUST be created — using the SAME tools the live workflow uses —
   when they are not already there.  This explicitly includes 3D-geometry
   renders for **every view set to TRUE**, not only the blade sections.

   So a saved attempt is COMPLETE by construction: parameters plus the full
   set of enabled renders.  An attempt whose Tool Caller never happened to
   call the blade-sections tool no longer archives as a partial record.

#### What that costs, and why it is still its own step

Decision 4 means invoking render / geometry code INSIDE the End-Session save.
That is the risk to respect: a slow or failing render there delays or breaks
the save, which is the one path that must not fail (see W1 — never move
artefacts to `previous_sessions/` until every post-session task is done).  Any
implementation needs a per-render timeout, a best-effort failure mode that
saves what exists rather than aborting, and a log line naming what it
generated versus what it found.

#### The per-view flags — SETTLED 2026-08-21

**ONE flag per view, governing generate + save + retrieve.**  Four flags:
isometric, top, blade sections, side.  A flag ON means that view is
generated at save time when missing, uploaded to R2, AND fetched on
retrieval.  Defaults follow the decided policy:

| view           | default |
|----------------|---------|
| isometric      | **ON**  |
| top            | **ON**  |
| blade sections | **ON**  |
| side           | **OFF** |

Chosen over two-flags-per-view (save / retrieve separately) because one flag
cannot disagree with itself, it halves the settings surface, and it matches
the decision's own wording — "renders of 3D geometry (from the views that
were set to TRUE)" already scopes GENERATION by the flag.

**The accepted cost, stated so nobody rediscovers it as a bug:** saving is
IRREVERSIBLE, retrieval is not.  A view left OFF is unrecoverable for every
attempt archived while it was off — flipping it ON later cannot reach back.
Turning a view OFF is therefore a decision about the permanent record, not a
display preference.  Turning one ON only affects attempts saved afterwards.

**Renaming needed.**  The settings are currently
`RETRIEVE_ATTEMPT_INCLUDE_<VIEW>_VIEW`.  That name becomes actively
misleading once they govern saving too — someone reading
`RETRIEVE_ATTEMPT_INCLUDE_TOP_VIEW=False` would not guess it stops the top
render being archived.  Rename as part of the implementation; the exact name
is an implementation detail, but it must not say "retrieve".

#### Failure at save time — SETTLED 2026-08-21

**Best-effort: save what exists, log what failed.**  Upload every render that
is present or was successfully generated, emit a warning naming each one that
could not be made, and let the save COMPLETE.

Chosen over aborting the attempt's upload because End Session must not fail
(W1): one bad render must not cost the whole attempt, and a systematic render
failure must not silently archive nothing.  An incomplete archive beats a lost
one.  Chosen over retry-once because a retry doubles the worst-case save time
exactly when the backend is down — which is when the save most needs to
finish.

The log line must name generated vs found vs failed, per view, so a thin
archive is diagnosable after the fact rather than mysterious.

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
