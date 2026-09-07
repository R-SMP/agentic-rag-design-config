# Propeller Studio

A **local** tool for making presentation renders and engineering-style technical
drawings of the parametric propeller. It is deliberately **not** part of the
deployed web app: it has its own virtualenv, its own dependencies, its own copy
of the geometry maths, and it imports nothing from `agents/`, `web_app.py` or
`config.py`.

That isolation is the point — the package is designed to be lifted into a
standalone repository by moving the folder, not by untangling imports.

You give it the 16 configurator parameters. It gives you:

* **Standalone renders** — one PNG per view, from any angles you name, with your
  choice of colour, material and lighting.
* **One technical drawing sheet** — the 3D geometry in 1–4 orthographic views
  with its outline drawn on top, *and* the inner / middle / outer blade sections
  fully dimensioned, all in a single image, to a stated scale.

---

## Setup

```powershell
cd "C:\Users\vince\MT Coding\tests\test11_v9_git"
.\propeller_studio\bootstrap.ps1
```

This creates `.venv-studio` (gitignored) and installs PyVista, matplotlib and
Flask into it, then runs `npm install` for the FEG backend's `three`. Your
global Python is untouched.

`sh propeller_studio/bootstrap.sh` does the same on macOS / Linux / Git Bash.

---

## The two geometry backends

| `--backend feg` | `--backend rhino` |
|---|---|
| Headless Node running the vendored copy of `web/feg/*.js` | RhinoCompute evaluating `Propeller_Raul_V1.2.gh` |
| The same geometry the browser 3D preview shows | The source of truth for the manufacturable part |
| Local, ~0.3 s, needs Node + `three` | Needs a running RhinoCompute server, ~6 s |

**They never substitute for each other.** If you ask for `rhino` and the server
is unreachable, the run fails with an explanation. This is on purpose: the two
produce visibly different blades, so a silent fallback would put FEG geometry
under a sheet whose title block says RhinoCompute — and a mislabelled drawing is
worse than a failed one.

RhinoCompute defaults to `http://localhost:6500/`; override with `--rhino-url`
or the `RHINO_COMPUTE_URL` environment variable.

---

## Using it

### The GUI

```powershell
.\.venv-studio\Scripts\python -m propeller_studio gui
```

Opens `http://127.0.0.1:8765` — all 16 parameters with their ranges, every
toggle, colour pickers, lighting rigs, view chips, and a Render button with a
live progress log and an inline gallery. Save any configuration as a preset.
The GUI is a thin client over the same `pipeline.run` the CLI calls; deleting it
would not affect the tool.

### The CLI

```bash
python -m propeller_studio render --params propeller_studio/examples/default.json
python -m propeller_studio render --attempt attempts/12 --backend rhino
python -m propeller_studio render --preset technical --views iso,top,front --turntable 12
python -m propeller_studio render --color '#b87333' --metallic 0.8 --lighting dramatic
python -m propeller_studio presets      # list presets
python -m propeller_studio defaults     # print the whole settings tree
```

Parameters come from a JSON file (`--params`), an existing attempt folder
(`--attempt`, reads its `parameters.json`), or the GUI form. `--set NAME=VALUE`
overrides individual values. Out-of-range values are refused unless you pass
`--allow-out-of-range`, which draws them and notes them on the sheet.

### Output

Every run writes one self-describing folder under `propeller_studio/out/`:

```
20260907_170402_rhino-check/
  renders/iso.png, top.png, turntable_00.png …
  drawing.png / drawing.pdf / drawing.svg      (whichever you enabled)
  parameters.json     the 16 values used
  settings.json       every setting, fully resolved
  manifest.json       backend, part vertex counts, scales, timings, warnings
```

A folder of PNGs whose settings you have forgotten is a folder you cannot trust
six months later, so each run carries everything needed to explain or repeat it.

---

## Settings

`settings.py:DEFAULTS` is the entire schema — there is no hidden state. A preset
is a **partial** copy of that tree, deep-merged over the defaults, so a preset
written today keeps working when a new toggle is added tomorrow.

Four presets ship: `technical`, `studio_copper`, `line_art`, `dramatic`.

Notable options:

* `render.views` — any of `top, bottom, front, back, left, right, iso, iso_low,
  iso_rear, three_quarter`, or `{"name": …, "az": 30, "el": 20}`.
* `render.turntable` — N evenly-spaced orbit frames, each its own PNG.
* `render.material.mode` — `uniform` (one colour) or `per_part` (blade / ring /
  hub / launcher separately), each with metallic, roughness and opacity.
* `render.lighting.preset` — `studio`, `soft`, `dramatic`, `technical`. Lights
  are attached to the **camera**, so every angle gets the same modelling; a
  world-fixed rig would make the top view bright and the bottom view black.
* `render.background.mode` — `solid`, `gradient`, `transparent`, `floor`
  (with a contact shadow).
* `render.overlays` — silhouette, feature edges, section curves, wireframe.
* `drawing.sections.annotations` — each dimension is its own switch.

---

## About the drawing

**It is genuinely to scale.** Both bands pick a scale from the standard series
(…10:1, 5:1, 4:1, 2.5:1, 2:1, 1:1, 1:2…) and the title block states it.
Auto-framing each panel to fill its box would look tidier and would be a lie.

**The 2D sections are true projections of the 3D geometry.** A section's placed
points all share one X (its radius), so the drawing frame is exactly the (Y, Z)
plane of the 3D section — the sections and the renders cannot disagree about
shape. The smoke test asserts this.

**Max thickness is measured, not assumed.** `innerMaxPos` / `outerMaxPos` move
the *camber crest*; the thickness peak sits near 30 % chord and no parameter
moves it. The two are computed separately, because reporting the crest station
as the thickness station is the easiest way to mislabel one of these drawings.

**Section curves are composited from a second pass.** The inner section sits at
r = 4 mm, *inside* the 8.28 mm hub, so in a single pass the hub swallows it and
the drawing silently loses a third of its subject. Set
`render.overlays.section_curves_on_top: false` for honest occlusion instead.

---

## Keeping the copies honest

This package carries a vendored copy of `web/feg/*.js` and its own port of the
airfoil maths. The cost of a copy is drift, so:

```powershell
.\.venv-studio\Scripts\python -m propeller_studio.dev.drift_check
```

byte-compares the vendored JS against `web/feg/` (skipped in a standalone
checkout) and numerically compares the Python section maths against the JS the
exporter actually runs, over random in-range parameter sets. Typical agreement
is ~4e-06 mm — three.js stores positions as float32, which dominates.

```powershell
.\.venv-studio\Scripts\python -m propeller_studio.dev.smoke_test --rhino
```

runs 33 end-to-end checks. Drop `--rhino` if no server is running.

---

## Extracting this into its own repository

1. Move the `propeller_studio/` folder.
2. Copy `package.json` (it pins `three`) and run `npm install`.
3. Point `PROPELLER_STUDIO_GH` at `Propeller_Raul_V1.2.gh` if you want the Rhino
   backend; otherwise drop `compute-rhino3d` / `DracoPy` from the requirements.
4. `drift_check` will report the upstream tree as absent and skip that half.

Nothing else needs changing — there are no imports from the parent repository.
