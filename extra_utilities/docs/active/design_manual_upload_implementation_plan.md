# Manual upload to the database — implementation plan

**Companion to** the owner's handover `design_manual_upload_to_database.md`
(2026-09-15). That document specifies WHAT to build. This one records what
survived verification against the actual codebase, the four design decisions
taken afterwards, and the order to build it in.

**Status:** planned, not built. Every claim below carries a file:line and was
verified on 2026-09-15 by an 8-agent parallel audit of the repository, not
inherited from the handover.

---

## 0. Two corrections that change the build

### 0.1 `upload_directory` has NO whitelist — REFUTES handover §3.4

The handover states `.json` "**is** in the `upload_directory` whitelist
`(".txt", ".png", ".jpg", ".jpeg", ".json")`". There is no whitelist in the
uploader. The extension set is a caller-supplied argument:

```python
def upload_directory(local_dir, remote_prefix, *,
                     suffixes: Iterable[str] = (".txt",)):   # r2_uploader.py:375
```

The 5-tuple lives at the single production call site,
`database_handler.py:2214-2220`. **A new caller that follows the handover's
step 6 literally uploads only `.txt`** — no images, no `.compression.json`
sidecars — silently, behind a success message. `retrieve_user_inputs` would
then return an empty `<images>` block for an upload that appeared to work.

> **MUST:** pass `suffixes=(".txt", ".png", ".jpg", ".jpeg", ".json")`
> explicitly at the manual-upload call site.

### 0.2 `user_provided_images` is not an absolute gate — REFUTES handover §3.1's implication

It gates the R2 listing **only when Postgres is reachable**. Two bypasses:

* Postgres down → `has_images` is forced `True`
  (`retrieve_user_inputs.py:535-544`).
* The local-cache replay path never consults it
  (`retrieve_user_inputs.py:564-572`).

Setting the column `false` therefore hides images from the *first* fetch, not
from a folder that has already been populated. Fine for this feature — we set
it `true` exactly when images are user-input images — but do not rely on it as
a security boundary.

---

## 1. Four corrections to keep (claims confirmed, details wrong)

| # | What the handover says | What is actually true |
|---|---|---|
| 1 | `_METAFILTER_SPECS` | It is `_METAFILTER_SPEC`, singular (`database_search.py:581`). The claim itself holds — `field` is a metafilter KEY, and no whitelist of field VALUES exists. Stronger than stated: the LLM-facing tool pins `metafilters=None` (`database_search.py:1633`), so no agent can filter on `field` at all. The real gate is `field_type='Semantic' AND NOT is_error AND NOT is_empty` plus `agents_to` and `embedding_model`. |
| 2 | "adding a `skip_stitch` parameter is the smallest correct change" | True, but it is **two edits**, and there is a trap: the `dc_name` guard at `db_writer.py:886-890` raises **before** the retry loop. A manual caller passing `skip_stitch=True` must still supply a non-empty `dc_name` or it fails outside the safety path. |
| 3 | `upsert_attempt(... )` | Signature confirmed (`db_writer.py:519-527`), keyword-only, returns the BIGSERIAL id. **But `attempt_label` carries a standalone global `UNIQUE`** (`schema_v8.sql:277`) while `ON CONFLICT` targets only `(session_id, attempt_label)` (`db_writer.py:554`). A label colliding across sessions raises an **unhandled** `UniqueViolation` — `upsert_attempt` has no handler. Timestamp-prefixed labels avoid it. |
| 4 | busy guards | All four confirmed. Two meanings are broader than stated: `_TURN_IN_FLIGHT` also covers Sessions-Queue turns (`web_app.py:2121`), and `_require_no_queue()` also rejects while an orphaned pipeline drains (`web_app.py:581-601`). Both broaden the refusal, which is what we want. |

Also confirmed: `DEFAULT_AGENTS_TO_ACL` is a true superset across all three
topologies, 11 members (`db_writer.py:67-87`); partial parameter dicts are
accepted with no completeness check and a bare `float()` cast
(`db_writer.py:586-630`); `dc_attempts.parameters_json` is `NOT NULL`
(`schema_v8.sql:280`); deleting a `sessions` row cascades to `chunks`,
`chunks_mm`, `dc_attempts` and — via **two hops**, since it has no
`session_id` column — `dc_attempt_parameters` (`schema_v8.sql:374-380`).

One incidental: `_IMAGE_FIELD_KINDS` (`database_search.py:835-838`) **is** a
hard-coded field-VALUE whitelist, used only to render `<image_ref>` blocks.
The text row's `'User Uploaded Content'` is text-only so it is unaffected —
but any future image-bearing field name would render as a plain `<qa>` whose
body is a raw R2 key.

---

## 2. The blocking design hole, and the decisions taken

### 2.1 `retrieve_attempt` cannot see manual images

It never lists the attempt folder. It fetches renders by **fixed canonical
filename** from a closed set of four (`attempt_views.py:37-43`), each gated by
a settings flag:

```python
("isometric",      "ATTEMPT_VIEW_ISOMETRIC",      "render_isometric.png"),
("top",            "ATTEMPT_VIEW_TOP",            "render_top.png"),
("blade_sections", "ATTEMPT_VIEW_BLADE_SECTIONS", "render_blade_sections.png"),
("side",           "ATTEMPT_VIEW_SIDE",           "render_side.png"),
```

```python
for view in render_views_in_scope:                      # retrieve_attempt.py:523
    filename = _RENDER_FILES[view]
    data = _r2_get_bytes(client, bucket, _r2_key(base, filename))
    if data is None:
        fetch_failures.append(key)                      # -> <missing/>
```

So handover §3.5's *"All uploaded images become that attempt's renders"* does
not work: an image named `my_sketch.png` is invisible, and with
`has_renders=True` the response is actively noisy — a `<missing/>` marker for
every enabled canonical view that is not there.

The same root cause hits handover step 8: `db_writer_mm` filters attempt files
with `_RENDER_RE = r"render_.*\.png$"` (`db_writer_mm.py:60, 291`), so manual
images never reach `chunks_mm` either.

### 2.2 Decisions (owner, 2026-09-15)

| # | Decision |
|---|----------|
| **D1** | **Extend `retrieve_attempt` to list the attempt folder** and return non-canonical images as `<extra_image>`, alongside the canonical views. Widen `db_writer_mm._RENDER_RE` in the same change so those images also reach `chunks_mm`. |
| **D2** | **`origin="manual_upload"`** on `<session>` and `<attempt>`, derived from the `MANUAL_` prefix. Replace the extraction `<missing/>` note for these entries — as written it says "no extraction was archived", which reads as data loss. |
| **D3** | **`partial="true" keys="N/M"`** on the returned parameter set, so absence is machine-checkable rather than inferred. |
| **D4** | **`queries.txt` is bare prose** — no `--- [ts] USER ---` header. Do not fabricate a turn that never happened; D2 explains the difference. |

D1 is worth more than this feature: today a *new* render type is invisible to
retrieval until someone adds it to `attempt_views.VIEWS`. D1 removes that.

---

## 3. Build order

Deliberately **inverted** relative to the handover, which builds the UI first.
The retrieval-layer work (Phase A) is independently testable against a
synthetic `MANUAL_` session seeded by a smoke test, with no UI and no writer.
Building it first means Phase B has a working target to verify against.

### Phase A — retrieval layer (no UI, no writer)

| A# | Change | File |
|----|--------|------|
| A1 | List the attempt folder; emit non-canonical images as `<extra_image name= path=/>`. Filter to `_IMAGE_SUFFIXES`, and exclude the canonical view files already emitted so real attempts gain nothing. Costs one extra R2 `LIST` per attempt. | `tools/retrieve_attempt/retrieve_attempt.py` |
| A2 | `origin="manual_upload"` attribute on `<attempt>`; same on `<session>`. Honest note text on the extraction `<missing/>` when the id has the `MANUAL_` prefix. | both retrieve tools |
| A3 | `partial="true" keys="N/M"` on the parameters element, N = keys present, M = the schema's parameter count. | `retrieve_attempt.py` |
| A4 | Widen `_RENDER_RE` so non-canonical attempt images reach `chunks_mm`. | `db_writer_mm.py` |
| A6 | For a `MANUAL_` session, skip the canonical-view fetch and the description `<missing/>`. Without it the response carried four phantom failure markers for artefacts a curated entry can never have, so it read as a BROKEN attempt. | `retrieve_attempt.py` |

**Guard for A1/A4:** real attempt folders also hold `parameters.json`,
`description.txt` and `propeller_mesh.obj`. Both changes must filter to image
suffixes, or `<extra_image>` will list a mesh and `chunks_mm` will try to embed
one.

**Phase A exit criterion:** a seeded `_smoke%` session with a non-canonical
image in its attempt folder retrieves with that image listed, an
`origin` attribute, and a `partial=` count — with every REAL attempt's response
byte-identical to before. Prove the second half with a before/after capture,
the same way the prompt-census diff was done for the `<<CAN_SEE>>` split.

### Phase B — writer path

Order matters; several steps read what the previous one wrote.

```
 1. Refuse if busy: _TURN_IN_FLIGHT / _END_IN_FLIGHT /
    _BOX.session is not None / _require_no_queue()   -> HTTP 409, naming which
 2. Validate the form
 3. Staging folder OUTSIDE inputs/ and attempts/, shaped like a session
 4. INSERT the sessions row  (user_provided_images = images AND user-input toggle)
 5. upsert_attempt + upsert_attempt_parameters       -> global_attempt_id
 6. R2 via the EXISTING helpers:
       upload_directory(<staging>/user_inputs, ...,
                        suffixes=(".txt",".png",".jpg",".jpeg",".json"))  <-- §0.1
       upload_attempt_artefacts(..., global_attempt_id=...)
 7. insert_chunk(..., skip_stitch=True, dc_name='propeller')              <-- §1.2
 8. OPTIONAL: db_writer_mm.mirror_session_to_mm(session_id)  — reads chunks
    AND R2, so it must run LAST.  Best-effort, gated on multimodal enabled.
 9. Delete the staging folder (also on failure)
```

| B# | Change | File |
|----|--------|------|
| B1 | `skip_stitch: bool = False` on `insert_chunk`; when set, `embedding_input = body`. Retry loop and `save_to_safety_folder` untouched — verified they do not read `embedding_input` (`db_writer.py:976-991`). | `db_writer.py` |
| B2 | `attempt_label` MUST be `<YYYYMMDD>_<HHMMSS>_<NNN>_<slug>` -- **two** numeric groups before the NNN. `_ATTEMPT_LABEL_RE` is `^\d+_\d+_(\d+)_` (`retrieve_attempt.py:96`) and a label that fails it is SKIPPED with only a log warning, so the row sits correctly in Postgres while the agent gets `status="not_found"`. Found by a Phase-A fixture that used `<epoch>_001_<slug>`. The timestamp shape also dodges the standalone global UNIQUE (§1.3); consider a `UniqueViolation` handler on `upsert_attempt` while here. | new module |
| B3 | Transactional enough that a half-written entry is never searchable: if the embed fails, either roll back the `sessions` row or let the safety folder catch it — never leave a `sessions` row with no `chunks`. | new module |

### Phase C — web layer

| C# | Change | File |
|----|--------|------|
| C1 | Nav button + `<section class="view" data-view="upload_db">`. Reuse the *shape* of Image Inputs (`web/index.html:123`) scaled down; sliders may follow Input Parameters (`web/index.html:241`). | `web/index.html`, `web/style.css` |
| C2 | Form state, validation, submit. **Block submit when an image is present and both toggles are off** — such an image is stored but unreachable. Disable Send and say why when the system is busy. | `web/app.js` |
| C3 | Endpoints: submit, list, delete. **Hard-scope list and delete server-side** to `session_id LIKE 'MANUAL\_%'` in the SQL, not only in the UI. | `web_app.py` |

Delete removes the `sessions` row (everything cascades, §1) then the R2
objects under `<sid>/`.

---

## 4. Verification

Model on `extra_utilities/db_design/smoke_test_retrieve_user_inputs.py`: it
seeds its own `_smoke%` session in Postgres + R2 and cleans up completely,
**including local disk**. Copy that structure; do not test against real data.

1. `database_search` from an agent context returns the uploaded text.
2. `retrieve_user_inputs` returns `<user_query>` with the text, the
   extraction `<missing/>` carrying the **new** note, `origin="manual_upload"`,
   and `<images>` listing each image — only when the user-input toggle was ON.
3. `retrieve_attempt` returns the parameters with `partial=` and each image as
   `<extra_image>` — only when the render toggle was ON.
4. R2 keys match `<sid>/user_inputs/images/...` and
   `<sid>/attempts/001__<gid>/...` exactly.
5. Image present + both toggles off → **rejected**.
6. No images, no parameters → **succeeds** (text only).
7. Delete → `sessions`, `chunks`, `chunks_mm`, `dc_attempts`,
   `dc_attempt_parameters` and the R2 objects are all gone.
8. **Regression:** every real attempt and real session retrieves
   byte-identically to before Phase A.

> **Before running anything live:** census real Postgres + R2 content and
> re-take it afterwards. The system is in ACTIVE USE — on 2026-09-15 the chunk
> count moved mid-run because another session was saving. Scope every census
> query so external activity is distinguishable from your own writes, and
> remember `r2_uploader._key_prefix()` returns `test11/` while live data is
> under `web-v1/` — a census of the configured prefix alone says nothing about
> production content.

---

## 4b. Phase A status — DONE 2026-09-15

Applied, and verified two ways: 21 offline assertions through the real
builders (including regression cases proving a real attempt and a real
pre-extraction session are unchanged), and a live end-to-end that seeds a
`MANUAL_` entry in Postgres + R2, retrieves it with both tools and removes
every trace.  Census identical either side; the chunk count moved twice
during the work because other sessions were saving, which is why the census
must be scoped rather than compared as a raw total.

Two defects were found by those tests rather than by reading:

* The first A6 gated the description marker with `and not manual`, which sent
  a manual entry down the `else` branch into `_wrap_cdata(None)`.  Fixed by
  testing on PRESENCE first.  The offline suite had missed it because every
  manual fixture supplied a description; it now covers the absent case.
* `smoke_test_retrieve_attempt_offline.py` asserted the literal
  `"<parameters>"`, which stopped matching once the element gained
  attributes — its fixture is a 3-key set, so `partial` fires.  The
  assertions now match the opening tag and additionally check the partial
  count.  **Not a production regression:** all 86 real attempts carry
  exactly 16 keys, so `partial` never fires for them.

## 5. Open questions not yet decided

* **Does a manual entry outrank a real session in search?** Curated content is
  arguably higher-quality evidence, but nothing ranks it differently today and
  D2's `origin` attribute is the only signal an agent gets.
* **Should `retrieve_user_inputs`'s prompt fragment mention manual entries?**
  The shipped bullet says a retrieval "prints each past session's structured
  extraction" — for a manual entry there is none, by design. The wording is now
  slightly wrong for this case.
* **Nothing prevents a manual entry from being mirrored into `chunks_mm`
  twice** if `mirror_session_to_mm` is re-run; it is per-session
  delete-then-insert, so it is idempotent, but that has not been exercised for
  a session whose images are non-canonical.
