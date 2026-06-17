# OCR for text recognition in user images — design notes

**Status.** Implementation in progress (as of 2026-06-17).

- **Engine + grouping — SHIPPED.**  `agents/shared/ocr/` + smoke tests,
  committed `9e00d19` on `stage-a-web-deploy`.
- **Settings gate + 3-tool integration (Decision 2) — BUILT, gated
  OFF.**  `settings.py` block 24 (`OCR_ENABLED` / `OCR_ENGINE` /
  `OCR_WHOLE_IMAGE_DEFAULT` / `OCR_MAX_TEXT_CHARS`).  A single shared
  entry point — `agents/shared/ocr/feature.py:ocr_summary_if_enabled`
  — is called by **all three** image tools: `load_input_images`,
  `read_user_inputs` (UII), and `retrieve_user_inputs`.  Each appends
  an OCR section to its result when enabled.  The agent-facing
  `extract_text` flag is built **dynamically per session** (via
  `build_user_inputs_tools()` / the `read_user_inputs` +
  `retrieve_user_inputs` factories) and is **invisible when
  `OCR_ENABLED=False`**.  Default of the flag: **ON** for
  `load_input_images` / `read_user_inputs`, **OFF** for
  `retrieve_user_inputs` (past-session images were usually already
  captured).  `OCR_ENABLED=False` by default pending validation in the
  deployed app (flip to True to test).
- **Remaining:** the `ocr_region` escalation tool (Decision 3 / §4) and
  per-agent UI gating (deferred to coordinate with the parallel
  settings-UI session).

This file is the running source of truth for the OCR feature decisions.

---

## 1. Purpose / why OCR

Users attach hand-drawn engineering sketches and annotated renders to
describe the propeller they want.  Many of these images carry **text
callouts that map directly onto the 17 design parameters** — e.g.
`renderwinfo_test1_image.png` reads *"3.5 mm thick"*, *"Diameter 136
mm"*, *"Chord 8mm"* on red arrows pointing at the ring / blade.  Today
the chain can only *see* those callouts as pixels (the agent reads them
itself, imperfectly); there is no mechanism to extract them as a clean,
quotable, verifiable string.

OCR's job here is to **read the text written on a user image and hand
that text to the agent alongside the image**, so the chain can use
explicit numbers instead of estimating dimensions from visual
proportions.  This relates to **F32** (UII should estimate parameters
from visual proportions) — OCR is the complementary path for when the
user *did* write the number down.

**Current state:** no OCR exists anywhere in the repo (grep for
`ocr|tesseract|text recognition` → nothing).  This is greenfield.

---

## 2. Architecture facts that shape the design

These are the real integration points (read 2026-06-15); the design
leans on them rather than inventing new plumbing.

- **`load_input_images(paths)`** — `agents/shared/user_inputs_tool.py`
  (`_handle_load_input_images`, ~L312).  This is the tool agents call to
  "see" the *current* user images.  It does two things in **one** call:
  1. appends a **text `ToolMessage`** ("Loaded N images… Loaded
     paths: …"), and
  2. buffers the image **bytes** as content blocks for the next message
     via `append_pending_images`.
- The retrieval tools (`retrieve_user_inputs`, `retrieve_attempt`) use
  the **same split**: XML/text in the `ToolMessage`, image bytes
  buffered separately.  See `agents/shared/retrieve_tool_dispatcher.py`.
- **Image-strip behaviour:** when `KEEP_IMAGES_IN_CONTEXT` is OFF, the
  `on_operation_end` strip hook drops image *bytes* at the next
  operation boundary **but preserves the text `ToolMessage`**.  So any
  text returned by the tool outlives the picture.
- **Settings idiom (two layers already in the codebase):** a master
  switch + per-agent gating (e.g. `RAG_ENABLED` + per-agent DBa
  gating), separate from an **agent-controlled per-call flag** (e.g.
  `images_flag` on `retrieve_user_inputs`).  Precedence: the settings
  gate always wins; the per-call flag is a preference *within* what the
  operator allowed, never an escape hatch around it.

The whole framework's principle — **freedom to each singular agent** —
is preserved by keeping the per-call flag agent-controlled.

---

## 3. Decisions locked so far

### Decision 1 — Two-layer control: settings gate **+** per-call flag  *(DECIDED)*

Mirror the existing `RAG_ENABLED` / `images_flag` idiom; do **not**
duplicate one control in two places.

- **Settings layer = operator policy.**  Decides whether OCR exists at
  all and for which agents, plus operator-only choices:
  - master `OCR_ENABLED` switch,
  - per-agent enablement (mirror the per-agent DBa gating pattern),
  - **which OCR engine** is used (see §5 — still open),
  - the **default value** of the per-call flag.
- **Tool-call flag layer = per-invocation agent intent.**  On *this*
  call, does the agent want OCR text back?  Preserves agent autonomy.
- **Precedence:** settings gate wins.  If OCR is off (globally or for
  that agent), the per-call flag is a silent no-op — exactly like
  `RAG_ENABLED=False` neutering `database_search`.
- **Sub-decision — flag default: ON.**  When the operator has enabled
  OCR for an agent, the agent receives OCR text automatically unless it
  opts out on a given call.  (Chosen because of the strip-survival
  advantage in Decision 2 — the read text is durable and cheap.)

### Decision 2 — Bundle OCR text into the visualization tool's existing text return  *(DECIDED)*

OCR output rides the `ToolMessage` that `load_input_images` **already**
returns.  No new content-block type, no new message plumbing — per
loaded path, append an `OCR text detected:` subsection to the existing
summary text.

Advantages this buys:
- **Nearly free plumbing** — reuses the existing text-in-ToolMessage /
  bytes-buffered split.
- **OCR text outlives the image bytes** — with `KEEP_IMAGES_IN_CONTEXT`
  OFF, the picture is stripped at the next operation boundary but the
  ToolMessage text is preserved.  The agent keeps *"Diameter 136 mm …"*
  even after the image is gone — arguably more durable and more useful
  for numeric reasoning than the pixels.
- **One call, two pieces of evidence** — same pattern the retrieve
  tools already establish, so it feels native to the agents.

Design care required:
- Delimit and attribute OCR text **per image**.
- Label it explicitly as **machine-read** so the agent treats it as
  evidence to **verify against the picture**, not ground truth (OCR on
  hand-drawn callouts is fallible).
- **Cap its length** so a dense image cannot blow up context.

### Decision 3 — Whole-image by default **+** optional region re-OCR escalation  *(SHAPE DECIDED; region mechanism OPEN — see §4)*

Not either/or.  Two tiers:
- **Whole-image OCR is the default** (bundled per Decision 2).  These
  sketches have *sparse* text, so one full pass is cheap and catches
  everything.  The agent also cannot pin-point regions on first contact
  — it doesn't know where text is until it has seen the image — so
  region-targeting is inherently a *second* step and cannot be the only
  path.
- **A region re-OCR escalation** for the cases that need precision:
  dense/overlapping text the whole-image pass garbles, or a tiny callout
  it missed/misread.  The agent visualizes → notices text → asks for a
  higher-res re-read.  This is the agent-autonomy precision lever.

---

## 4. Region / crop re-OCR mechanism

Decision 3's *escalation* tier.  The hard constraint that shapes it:
an LLM is **bad at precise pixel/fraction coordinates** and at the
spatial reasoning of *where to crop*, and the image it saw may have
been resized server-side — so the design must never depend on an
agent-supplied bounding box.

### Targeting — region IDs, not free crops  *(DECIDED)*

The agent does **not** free-crop.  The whole-image OCR pass also runs
text **detection** and returns a list of detected text regions, each
with an **ID**.  When the agent wants a higher-quality re-read, it
calls the escalation tool with a **region ID** — it picks from a menu
of detector-found regions rather than producing coordinates.  Chosen
because VLMs are poor at spatial reasoning, so a menu is far more
reliable than trusting agent coordinates.

**Assumption this rests on (logged as a known issue):** the mechanism
only works if the text detector spots *every* region containing text
— a missed region has no ID and is therefore unreachable by the
precision path, silently.  See **F38** in `TODO_known_issues.md` for
the recall risk + validation/mitigation plan.  Especially fragile on
faint / rotated / arrow-attached callouts, which is exactly the input
the feature serves.

### Return shape — text + zoomed crop image  *(DECIDED)*

The escalation tool returns the high-res re-read **text** for the
chosen region ID **and** the **zoomed crop image** of that region, so
the agent can visually confirm the read against the text.  The crop is
subject to the same image-strip rules as other loaded images (it is
*not* pinned in context past the strip) — the durable artefact is the
text, the crop is a transient confirm.

### Engine strategy — same engine, higher-res crop  *(DECIDED)*

The region pass re-runs the **same engine used for the whole-image
pass**, on the upscaled crop of the chosen region.  The resolution
bump alone is expected to fix callouts that were garbled at
whole-image scale.  (A second-engine cross-check was considered and
deferred — revisit only if same-engine-higher-res proves insufficient
in the §5 bake-off.)

### Tool shape — a separate `ocr_region` tool  *(DECIDED)*

Region re-OCR is its **own** escalation tool (working name
`ocr_region`), distinct from `load_input_images`.  The agent calls it
with a region ID *after* the whole-image pass has produced the region
menu.  Clean semantics, its own log line, and independent per-agent
gating — and it keeps the `load_input_images` buffered-image plumbing
unchanged.

### Region mechanism — summary of the locked flow

1. Agent calls `load_input_images` → whole-image OCR + text
   **detection** runs → the ToolMessage carries the OCR text **and** a
   menu of detected text regions, each with an **ID**.
2. Agent reviews; if a callout is garbled / suspect, it calls
   `ocr_region(<region_id>)`.
3. `ocr_region` crops that region, upscales, re-runs the **same
   engine** at higher res, and returns the re-read **text + the zoomed
   crop**.
4. Gated by the same settings as the rest of OCR (§3 Decision 1);
   recall assumption tracked in **F38**.

---

## 5. Engine — Google Cloud Vision  *(DECIDED; swappable)*

**Decision:** the OCR engine is **Google Cloud Vision**
(`vision.googleapis.com`).

**Why it fits the two hard filters** (see §2 + the region design in §4):
- **Returns bounding boxes.**  Vision's `TEXT_DETECTION` /
  `DOCUMENT_TEXT_DETECTION` returns the full text **plus** per-word /
  per-block `boundingPoly` coordinates — exactly what the region-ID
  menu (§4) needs, and the crop coordinates for `ocr_region`.  For
  sparse sketch callouts use **`TEXT_DETECTION`**;
  `DOCUMENT_TEXT_DETECTION` is for dense documents.
- **No GPU.**  It is an API call, so it runs fine from the CPU Railway
  container — unlike the self-hosted VLM-OCR tier.
- Strong printed accuracy (~98–99%) and competitive handwriting (50+
  languages), which covers both the printed render-overlay callouts we
  have today and future hand-annotated sketches.

**Why a dedicated engine over "just let the VLM read it":** a separate
OCR pass adds (a) full-resolution, box-anchored reading that resists
the VLM digit-hallucination failure mode (`136` → `138`, catastrophic
for dimensions), and (b) a clean quotable string that survives the
image strip (Decision 2).

**Swappable by design (operator flagged the method may change).**  The
recognition method is **not** assumed permanent.  Keep Vision behind a
thin engine interface (one module exposing e.g. `detect_regions(img)`
+ `ocr_region(img, region_id)`), selected via the §3 Decision-1
settings layer (`which OCR engine`), so swapping to a cloud
alternative (Azure / AWS) or a future self-hosted GPU model touches
only that module + the setting — never the tool or agent layer.

**Auth / keys:** see §7.

### Verification (2026-06-15) — connectivity + recall confirmed

A standalone smoke test
(`extra_utilities/smoke_test_google_vision.py`) ran against the live
API on both annotated renders:

- **Setup confirmed** — HTTP 200; the `GOOGLE_CLOUD_VISION_API_KEY` +
  billing + API-enablement are all correct.
- **Perfect recall + exact digits** on the printed render-overlay
  callouts:
  - `renderwinfo_test1` → *"3.5 mm thick / Chord 8mm / Diameter 136 mm"*
  - `renderwinfo_test2` → *"3.5 mm thick / Thickness 2.28 mm / Diameter 136 mm"*

  Every dimension — including the decimals `3.5` / `2.28` and the
  digits `136` / `8` — read **exactly**.  The digit-hallucination risk
  that motivated a dedicated engine does **not** appear (Vision reads,
  it doesn't guess).
- **Per-word boxes returned** — the raw material for the region menu.

**Caveat — handwriting still untested.**  Both verified images use
*printed* overlay text.  True hand-written callouts (the harder case,
and the core F38 recall risk) are untested — there is no hand-annotated
test image carrying text yet.  Treat **printed-callout recall as
proven, handwriting recall as the open unknown**.

**Engine module (landed):** `agents/shared/ocr/` —
`google_vision.py` (the Vision REST wrapper, the `detect_text()`
contract, and `group_words_into_regions()` the callout grouper) and
`__init__.py` (the swappable seam).  Depends on `requests`; confirm it
is a declared dependency before the production wire-up.

**Region grouping (landed 2026-06-15) — 2D proximity clustering.**
`detect_text` returns **callout-level** `regions` (the `ocr_region`
menu) alongside the raw per-word `words`.  Grouping
(`group_words_into_regions()`) builds a proximity graph whose
connected components are the regions: two words link when the
edge-to-edge gap between their boxes is small in **both** axes
(horizontal <= 1.5x, vertical <= 0.6x the median word height).  This
is true region-similarity in image space — order-independent, and it
handles **rotated / diagonal / vertically-stacked** callouts, not only
horizontal lines.  Chosen over a line-based heuristic (too narrow) and
over Vision's native paragraph grouping (would couple grouping to one
engine, against the §5 swappability goal).
Verified live on both renders (3 clean regions each, e.g.
*"Diameter 136 mm"* = box `(14,375)-(222,394)`) and unit-tested in
`extra_utilities/smoke_test_ocr_grouping.py` (10 deterministic checks,
incl. the gap-split, order-independence, diagonal, and stacked paths).

---

## 6. Coordination note

A parallel session is currently editing the **settings UI window** and
the **database**.  The settings *backend block* (`workflow_settings/
settings.py`) is safe to add to, but the operator-facing OCR toggle in
the settings **UI** overlaps that session's work — stage the UI slice to
avoid a collision, or hand it to the other session.

OCR itself touches no chain *logic*: the integration is confined to the
shared image tool (`user_inputs_tool.py`) + a new OCR module + the
settings gate.  No agent reasoning code changes.

---

## 7. Keys / setup (Google Cloud Vision)

**Important — this is NOT the existing `GOOGLE_API_KEY`.**  That key is
the **Gemini** LLM key (`langchain_google_genai` →
`generativelanguage.googleapis.com`).  Cloud Vision
(`vision.googleapis.com`) is a separate Google Cloud product; an
AI-Studio Gemini key is normally scoped to the Generative Language API
and will **not** authenticate Vision.  Give Vision its own credential.

**One-time Google Cloud setup:**
1. A **Google Cloud project** (reuse the one behind the Gemini key, or
   make a new dedicated one).
2. **Enable billing** on it (Vision requires billing; first ~1,000
   units/month are free).
3. **Enable the Cloud Vision API** (`vision.googleapis.com`).
4. **Set a budget / spend cap** on the project — consistent with OPS1
   in `TODO_known_issues.md`.

**Credential — two paths:**

- **Option A — API key (recommended for v1 / the harness).**  Create a
  key (Console → APIs & Services → Credentials), **restrict it to the
  Cloud Vision API**, and call
  `POST https://vision.googleapis.com/v1/images:annotate?key=...`.
  One env var, e.g. **`GOOGLE_CLOUD_VISION_API_KEY`** — matches the
  existing one-var pattern (`VOYAGE_API_KEY`, `OPENAI_API_KEY`).  Keep
  it **separate** from the Gemini `GOOGLE_API_KEY` so each is
  independently restrictable + spend-capped.

- **Option B — service account JSON (Google's recommended for servers;
  required if using the `google-cloud-vision` Python client).**  Create
  a service account → download its JSON key.  `GOOGLE_APPLICATION_
  CREDENTIALS` expects a file **path**, which is awkward on Railway —
  the usual pattern is to put the **whole JSON** in an env var
  (e.g. `GOOGLE_APPLICATION_CREDENTIALS_JSON`) and load it via
  `service_account.Credentials.from_service_account_info(json.loads(...))`.

**Railway gotcha (same as `VOYAGE_API_KEY`):** the key must be set in
the **Railway dashboard Variables**, not just local `.env` — `.env` is
`.dockerignore`d and never reaches the container.  Also set it in local
`.env` for dev.

**Recommendation:** Option A — a dedicated, Vision-restricted API key
in `GOOGLE_CLOUD_VISION_API_KEY`.  One variable, self-contained, fits
the module-isolation principle.  Move to a service account only if
tighter IAM is wanted later.
