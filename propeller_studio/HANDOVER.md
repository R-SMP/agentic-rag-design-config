# Propeller Studio — handover

**For: a Claude Code session merging this tool with another local tool.**

You have not seen this code before. This document tells you what it is, what it
exposes, and what you must not break. `README.md` next to it is the user-facing
manual; this file is the integration brief.

The owner's description of how the two tools should be joined is at the **end**
of this document. Read to there before designing anything.

---

## 1. What this tool is

`propeller_studio` turns **one set of the 16 propeller-configurator parameters**
into pictures:

* **Standalone renders** — one PNG per view, from any camera angles, with
  per-part colour, PBR material, four lighting rigs and four background modes.
* **One technical drawing sheet** — an ISO sheet (A5…A1, either orientation)
  carrying the 3D geometry in orthographic views with its outline drawn on top,
  *and* the inner / middle / outer blade sections fully dimensioned, in a single
  image, to a stated scale, with a frame and a title block.

It is a **local** tool. It is deliberately *not* part of the deployed
multi-agent web app, and it imports nothing from `agents/`, `web_app.py` or
`config.py`. It has its own virtualenv, its own `requirements.txt`, its own
vendored copy of the geometry maths.

That isolation is a requirement, not an accident: the owner intends this package
to be lifted into its own repository by **moving the folder**. Any merge you do
must keep that true — see §6.

**Scope note:** this tool renders. It does not analyse, compare or score meshes,
and it knows nothing about sessions or logs. Those are the other tool's job.

---

## 2. Where it is, and how to run it

* Branch **`claude/propeller-render-tool-f442ab`** (pushed to `origin`).
  Four commits, `144b1c8` → `c3240d3`. 43 files, ~5,800 lines.
* **Never commit or push to `stage-a-web-deploy`** — that is the branch Railway
  deploys the live web app from. This is an absolute rule from the owner.

```powershell
cd "C:\Users\vince\MT Coding\tests\test11_v9_git"
.\propeller_studio\bootstrap.ps1          # creates .venv-studio, npm install
.\.venv-studio\Scripts\python -m propeller_studio gui
```

```bash
python -m propeller_studio render --params propeller_studio/examples/default.json
python -m propeller_studio render --attempt attempts/12 --backend rhino
python -m propeller_studio render --layout sections_right --section-scale 4:1
python -m propeller_studio defaults        # the entire settings schema
```

**Environment facts, already established — do not re-derive:**

* `.venv-studio` runs **Python 3.13**. The `python` first on PATH is 3.8 and
  cannot import this package. Always use `.venv-studio/Scripts/python`.
* **PyVista/VTK offscreen rendering works natively on Windows here.** No OSMesa,
  no Docker, no display. This was the main technical risk and it is retired.
* Node 18+ is needed for the `feg` backend; `three` is pinned in the repo-root
  `package.json` and installed into the repo-root `node_modules`.
* RhinoCompute is expected at `http://localhost:6500/` (override `--rhino-url`
  or `RHINO_COMPUTE_URL`). Both backends have been verified working end to end.

---

## 3. What a run produces

One self-describing folder per run under `propeller_studio/out/` (gitignored):

```
20260907_170402_rhino-check/
  renders/iso.png, top.png, turntable_00.png …
  drawing.png / drawing.pdf / drawing.svg     (whichever formats were enabled)
  parameters.json    the 16 values used
  settings.json      every setting, fully resolved
  manifest.json      backend, per-part vertex/face counts, scales, timings, warnings
```

`manifest.json` is the machine-readable result and the natural thing for another
tool to consume:

```jsonc
{
  "created": "...", "run": "...", "backend": "feg" | "rhino",
  "geometry": {
    "parts": {"blade": {"vertices": 8425, "faces": 16830}, "ring": {...}, "hub": {...}},
    "fitted_ring_height_mm": 7.552467,
    "section_agreement_mm": 3.7e-06,     // feg only: Python port vs the JS
    "build_seconds": 0.26
  },
  "parameters": { ...the 16... },
  "warnings": [...],
  "renders": [{"name": "iso", "az": 45, "el": 35.264, "file": "iso.png", "size": [1600,1200]}],
  "drawing": {"layout": "...", "sheet": "A3 landscape", "view_scale": "1 : 1.24",
              "section_scale": "3.94 : 1", "files": {"png": "...", "pdf": "..."}},
  "total_seconds": 8.1,
  "out_dir": "..."
}
```

---

## 4. The integration surface — call these

Everything is importable; nothing needs the CLI or the GUI.

```python
from propeller_studio import params as P, settings as S, pipeline
from propeller_studio.geometry import airfoil, backends
from propeller_studio.drawing import sheet
from propeller_studio.render import scene
```

### The whole job in one call

```python
manifest = pipeline.run(
    params_dict,                  # the 16 parameters
    overrides,                    # a settings dict, a preset name, or a list of either
    out_root=Path(...),           # default propeller_studio/out
    slug="...", title="...",
    backend="feg" | "rhino",
    strict_range=True,            # False draws out-of-range values and notes them
    progress=lambda msg: ...,     # called per step; the GUI streams this
    rhino={"url": ..., "api_key": ..., "gh_path": ..., "node_bin": ...},
)
```

### Geometry only — most likely the seam for a mesh-analysis tool

```python
geom = backends.build(params_dict, "feg")      # or "rhino"
geom.backend                                   # "feg" | "rhino"
geom.parts                                     # {"blade": Part, "ring": Part, "hub": Part, ...}
part.vertices                                  # numpy (N, 3) float, millimetres
part.faces                                     # numpy (M, 3) int
geom.sections                                  # {"inner"|"middle"|"outer": (N, 3) closed loop}
geom.bounds()                                  # (min_xyz, max_xyz)
geom.ordered_parts()                           # [(name, Part), ...] in a stable order
geom.meta                                      # ring dims, timings, drift figure
```

**Parts are tagged and separable** (`blade`, `ring`, `hub`, and from Rhino also
`launcher`), and come as plain numpy arrays. If your other tool currently reads a
merged OBJ, this is a strictly better input: you can compare like-for-like parts
between two parameter sets instead of one anonymous soup.

The blade part has all `bladeCount` instances baked into world space.

### Derived engineering quantities, without building any mesh

```python
m = airfoil.section_metrics("middle", params_dict)
# chord_mm, angle_deg, radius_mm, span_fraction, thickness_pct, camber_pct,
# crest_tenths, max_thickness_mm, thickness_station_frac, max_camber_mm,
# camber_station_frac, outline_xy (N,2), camber_line_xy, le_xy, te_xy, …
airfoil.fitted_ring_height(params_dict)        # the derived ring height, mm
airfoil.build_section_3d(kind, params_dict)    # (N,3) placed section
```

Cheap and pure — no Node, no RhinoCompute, no rendering. Good for a comparison
table between two parameter sets.

### Individual pictures

```python
img = scene.render_view(geom, settings, "iso")            # (H, W, 3|4) uint8
sheet.render_sheet(geom, settings, out_paths={"png": Path(...)}, title=..., warnings=[...])
```

### Parameters and settings

```python
clean = P.validate(raw_dict, strict_range=True)     # raises P.ParamError
clean, warns = P.load("path.json" | "attempts/12")  # a file OR a folder with parameters.json
P.PARAM_SPECS                                       # name, unit, lo, hi, integer, label, group
P.DEFAULT_PARAMS

settings = S.resolve(preset_name_or_dict, another_dict, ...)   # deep-merged over defaults
S.defaults()                                        # the complete schema — no hidden state
```

`S.DEFAULTS` **is** the schema. A preset is a partial copy of it, deep-merged, so
adding a setting never breaks an existing preset.

### Errors worth catching

`backends.GeometryError`, `S.SettingsError`, `P.ParamError`. All carry messages
written for the person who asked for the render, not for a log.

---

## 5. Architecture map

```
params.py        the 16 parameters: specs, ranges, validation, loading
settings.py      DEFAULTS (the whole schema), deep-merge, validation, presets,
                 named views, scale parsing
pipeline.py      one run: geometry -> renders -> sheet -> manifest -> folder
cli.py           argparse over pipeline.run; every setting has a flag
__main__.py      python -m propeller_studio

geometry/
  airfoil.py           NACA + placement maths, pure Python (vendored port)
  backends.py          the two backends behind one contract; Part/PropellerGeometry
  feg_export_parts.mjs headless Node exporter: TAGGED parts + section curves
  feg_js/              vendored copy of web/feg/*.js (8-file dependency closure)

render/
  scene.py       PyVista: materials, camera-attached lights, camera, overlays

drawing/
  sheet.py       the sheet: paper, frame, title block, layout, scales
  sections.py    the dimensioned blade sections
  dimensions.py  linear/angular dimension primitives, grid
  placement.py   collision-aware label placement

gui/             Flask on localhost + one static page; a thin client over pipeline.run
dev/
  drift_check.py guards the vendored copies
  smoke_test.py  45 end-to-end checks
```

---

## 6. Design invariants — breaking these is a regression

1. **No imports from the parent repo.** Not `agents/`, not `web_app.py`, not
   `config.py`. Extraction must stay a folder move. If your merge needs shared
   code, vendor it and add a drift check, as `geometry/feg_js/` does.

2. **The two geometry backends never substitute for each other.** They produce
   *visibly different* blades (Rhino's tips are wider). An unreachable
   RhinoCompute is a hard `GeometryError`, never a silent fall back to `feg`. A
   sheet whose title block says RhinoCompute must *be* RhinoCompute.

3. **A stated scale is the scale drawn.** The title block prints the scale; the
   drawing is at it. A scale the user chose explicitly is honoured even when it
   overflows the panel — the sheet says so and names the largest that fits,
   rather than quietly shrinking. Do not "fix" the overflow by clamping.

4. **Max thickness is measured, never assumed.** `innerMaxPos` / `outerMaxPos`
   move the **camber crest**; the thickness peak is pinned near 30 % chord and no
   parameter moves it. They are computed separately on purpose.

5. **Span is measured from the 4 mm blade root, not the centre.**
   `middle radius = 4 + middlePos × (impellerRadius − 4)`. The sheet says
   "(from 4 mm root)" and that note is the last thing dropped when space runs out.

6. **No dimension value overlaps other text, a box, or a dimension line, and
   none leaves its panel.** Enforced by `drawing/placement.py` and asserted by
   the smoke test against the real renderer. If you add an annotation, route it
   through the placer; do not position it at a fixed offset.

7. **Every run folder is self-describing.** Parameters, settings, backend and
   manifest travel with the images.

---

## 7. Traps that already cost time

* **The ring mesh never reaches its analytic height.** The swept ellipse is
  sampled at M = 50, so the built Z extent is `fittedHeight × 0.998027`.
  Comparing analytic-to-mesh without that factor reports a fake ~0.03 mm drift.
  **Relevant to a mesh-comparison tool**: the same applies to any dimension you
  measure off the tessellation rather than the parameters.
* **The NACA 4-digit polynomial peaks at 1.00029 × t**, not exactly `t`. A real
  property of the aerofoil family, not a bug. Don't "fix" it.
* **The inner section is inside the hub.** It sits at r = 4 mm; the hub is
  r = 8.28 mm. Anything drawn there needs an always-on-top pass or it vanishes.
* **three.js emits the hub cylinder unwelded**, so on the raw mesh every triangle
  edge counts as a boundary edge. `poly.clean(tolerance=1e-6)` before extracting
  feature edges. **Relevant to mesh analysis**: watertightness and edge counts on
  the FEG mesh are meaningless without welding first.
* **`tools/generate_mesh/feg_export.mjs` (the agent pipeline's exporter) is not
  reusable here** — it flattens everything into one untagged OBJ and discards the
  section curves. `geometry/feg_export_parts.mjs` replaces it and classifies
  parts by *intrinsic* properties, never by traversal order.
* **PBR needs an environment texture** or metals render near-black. A procedural
  cubemap is built in `render/scene.py`.
* **The Bash tool collapses a backslash-n escape inside a quoted heredoc.** A
  Python string written that way receives a real newline and raises
  SyntaxError. Use the Write/Edit tools for content containing backslash escapes.
  This cost three separate debugging rounds.

---

## 8. How to verify you have not broken anything

```powershell
.\.venv-studio\Scripts\python -m propeller_studio.dev.smoke_test --rhino
.\.venv-studio\Scripts\python -m propeller_studio.dev.drift_check
```

* **45 checks** (43 without `--rhino`, which needs a running server). Current
  state: **all passing**.
* Drift check byte-compares the vendored `feg_js/*.js` against `web/feg/` and
  numerically compares the Python airfoil port against the JS the exporter runs.
  Typical agreement **3.8e-06 mm** (three.js stores positions as float32).
* The label-placement check renders real sheets — every annotation on, both
  layouts, A3 landscape and A4 portrait — and measures every label box against
  the real matplotlib renderer. It has caught every layout regression so far;
  trust it over eyeballing a thumbnail.

Both backends were verified end to end with RhinoCompute running. The FEG and
Rhino geometries agree on overall size to 143.00 mm vs 143.00 mm.

---

## 9. Things worth knowing before you design the merge

* **`--attempt <folder>` already exists.** The tool reads `parameters.json` out
  of any attempt folder. If the other tool also speaks "a folder with a
  `parameters.json`", that is a ready-made common currency.
* **Comparing two parameter sets** needs no new geometry code: call
  `backends.build()` twice and diff the `Part` arrays. Everything is already in
  millimetres in one world frame.
* **The GUI is disposable.** `gui/server.py` is ~160 lines and holds no logic —
  it posts to `pipeline.run` and polls a job. If the merged tool wants one
  interface, take the CLI/`pipeline.run` as the engine and rebuild the front end;
  do not try to graft two servers together.
* **The settings tree is the extension point.** Add a key to `S.DEFAULTS`, give
  it validation, and it is automatically reachable from presets, the CLI (add a
  flag) and the GUI (which builds its form from `/api/schema`).
* The other tool is **not in this repository** — I searched. Its mesh-analysis
  and session-log-download code lives elsewhere, so nothing here is coupled to
  it, and you are free to choose the direction of the dependency.

---

## 10. How the owner wants the two tools joined

<!-- The owner's explanation follows. Everything above is descriptive; this
     section is the actual instruction. Where the two conflict, this wins —
     except for the invariants in §6, which should be raised with the owner
     rather than quietly broken. -->

*(to be filled in by the owner)*
