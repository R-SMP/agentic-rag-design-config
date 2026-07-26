# Propeller Design Configurator — Benchmark & Experiments

Reproducible documentation of the evaluation work for the multi-agent propeller
design configurator. There are two layers:

- **The benchmark** — a fixed set of **7 case studies** scored by **7 metrics**.
  This is the shared *measuring instrument*.
- **Three experiments (tests)** — each **re-runs the entire benchmark** while
  varying one factor: the **LLMs used** (Test 1), the **number of agents**
  (Test 2), or **RAG on vs off** (Test 3).

So a "run" is one (experiment condition × case study × sample/case × iteration),
producing one session log that the analysis scripts score.

> **Sources.** This document is reconstructed from
> `…/28.07 Benchmark2 Setup/20260728_Benchmark2_SetUps.pptx` (the plan — case
> studies, metrics, Test 1 conditions), `extra_utilities/design_agent_count_variants.md`
> (Test 2 architectures), and the as-run data in `…/21.07/testResults/`.
> Where the **plan** and what is **built/run** differ, the gap is flagged
> explicitly — see the "As-built" notes and §A.8.

> **Where things live.** Runs, ground-truth files and analysis scripts sit
> **outside the app repo**, in the results folder `…/21.07/testResults/`
> (`TESTS/` below), synced via OneDrive. Only this document lives in the repo
> (`extra_utilities/`).

---

# Part A — The Benchmark (the measuring instrument)

## A.1 The 7 case studies

From the setup deck (slide 4). "Agents involved" is the subset the case is meant
to exercise; `(w)` = the DC Input Creator *writes* parameters. "Tests ×
Iterations" = (number of case instances) × (3 repeat iterations, to measure
variance).

| # | Case study | Metric(s) | Tests × Iter | Agents involved |
|---|---|---|---|---|
| 1 | **Text · Fully Quantitative · Simple** — geometry in text, all dimensions explicit | M1 | 2 × 3 | R, O, UII, Planner, DCIC (w), DCII |
| 2 | **Text · Fully Quantitative · Complex** — as #1 but some dimensions implicit (chained arithmetic, units, conditionals) | M1 | 5 × 3 | R, O, UII, Planner, DCIC (w), DCII |
| 3 | **Text · Fully Qualitative** — qualitative descriptions; correct if the guess lands in the target range | M2 | 5 × 3 | R, O, UII, Planner, DCIC, DCII, Tool Caller, DCOI |
| 4 | **Count blades + orientation — fine sketches (Task 2)** | M3, M4 | 20 × 3 | R, O, UII, Planner |
| 5 | **Count blades + orientation — rough sketches (Task 1)** — as #4 on noisier freehand sketches | M3, M4 | 20 × 3 | R, O, UII, Planner |
| 6 | **Extract dimensions from sketches** — scan + empty template (no text); recover written dims | M5, M6 | 20 × 3 | R, O, UII, Planner, DCIC (w), DCII, Tool Caller, DCOI |
| 7 | **Sketch interpretation → generate geometry** — full pipeline: Task 2 + Task 3 + text together; replicate sketches, noting they may differ from written dims | M6, M7 | 20 × 3 | Full system + Context Pruner |

The seven case-study numbers correspond to the `benchmark<N>/` folders on disk.

## A.2 The 7 metrics

| # | Metric | Measures | Score type |
|---|---|---|---|
| **M1** | Extract explicit dimensions from text | numeric dimensions written in the prose | **Binary** (right/wrong per parameter) |
| **M2** | Extract qualitative parameters from text | qualitative cues; correct if inside the target range | **Binary** (in-range per parameter) |
| **M3** | Count discrete features in images | number of blades read from a sketch | **Absolute error** |
| **M4** | Distinguish object orientation | recognise the orientation of a freely-drawn sketch | **Binary** |
| **M5** | Extract explicit dimensions from sketches | arrows, circles, written dims on the student's sketches | **Binary** |
| **M6** | Infer dimensions from relative size relations | estimate thickness, camber, max-thickness position | **Relative error** |
| **M7** | 3D model geometry correctness | volume + point-cloud difference after 3D normalization | **Relative error** |

## A.3 The output space — 16 parameters

Every design output is these, in canonical order:

```
bladeCount, impellerRadius, impellerThickness,
innerThickness, innerMaxPos, innerCamber, innerChord, innerAngle,
middlePos, middleChord, middleAngle,
outerThickness, outerMaxPos, outerCamber, outerChord, outerAngle
```

`*Thickness` / `*Camber` are **percentages of that section's own chord**;
`*MaxPos` is the chordwise high-point in tenths of chord; `middlePos` is the
middle section's position along the blade span (0 = root at the 4 mm hub, 1 =
tip). The **middle section has no independent thickness/camber/max-position** —
they are interpolated between inner and outer at `middlePos`; only `middleChord`
and `middleAngle` are its own. (`impellerHeight`, in older GT decks, is removed —
ring height is derived — and excluded from scoring. Per the deck: the ring
height is **not** floored to 4 mm; the geometry preview's minimum is ~2.4 mm.)

## A.4 Shared setup

**Samples (scans), graded by level of detail** (deck slides 8–10):

| Sample `code` | Detail level |
|---|---|
| `0178` | Medium |
| `0273` | High |
| `0365` | Very high |

Currently **0178 and 0273** are used across the image benchmarks; more scan IDs
(incl. `0365`) will be added. The 20× in the deck's "Tests × Iterations" is the
planned scan count; only a subset is run so far.

**Iterations.** Each test is run **3 times** (the `× 3`) to measure run-to-run
variance; the analysis currently scores the runs present without yet averaging
across iterations.

**The template (all image cases).** Filled-sketch cases are given a **blank
dimensioning template** plus a text note describing it, so the test measures
interpretation, *not* whether the system can tell template scaffolding from the
user's marks (deck remark, slide 3). The note (`template_not_filled_note.txt`):

> Template for sketching the dimensions. On top, the diameter can be written; the
> inner dashed circle = 120 mm diameter, the outer = 160 mm. In the middle, the
> top view of one blade is drawn (the middle-section position can be specified
> there; the outer-ring thickness reported to the right, graphically and/or
> numerically). On the bottom, three boxes hold the inner / middle / outer blade
> sections, each with a reference angle example bottom-right.

Filled sketches per sample: `task1/task2/task3.png` — the roles are the
whole-propeller sketch, the filled template, and the section detail (Task 2 =
"fine", Task 1 = "rough").

**Folder layout.**

```
TESTS/
  benchmark<N>/                       # N = case-study number (1..7)
    <case-or-sample>/                 # complexQuant1 …, or 0178 / 0273
      <CONDITION>/                    # a Test-1 LLM condition, e.g. CLAUDE_OPUS_4_8
        web-v1_ID###_…_.log           # the scored artefact (all hand-offs + final answer)
        benchmark#_<sample>_<cond>.pdf  # chat PDF, optional
      <query>.txt                     # the prompt for that case
      <sample>_task*.png              # sketches (image cases)
      template_not_filled.png / _note.txt
      <sample>_compressions.txt       # per-image compression degree (cost, not scoring)
  gt_quantitative.json  gt_qualitative.json  blade_counts.json
  *.py  (analysis scripts)            _analysis*/  (generated outputs)
```

The **`<CONDITION>`** subfolder currently encodes the **Test-1 LLM condition**
(see Part B). Tests 2 and 3 will add their own condition dimension.

## A.5 Per-case detail

Each entry: the **query**, **ground-truth source**, **scoring**, the **script +
command**, and an **As-built** note where reality differs from the plan.

For **text** cases (1–3) the prompt is `<case design text> + <add-on>`. The
design text and the ground truth both live in the test deck
`20260721_FixingSystem_Testing_corrected_v2.pptx`.

---

### Case 1 · Text · Quantitative · Simple — `benchmark1`  ·  M1

**Query.** Case design text + the **quantitative add-on** (verbatim; shared with
Case 2):

```
That's everything I want in it.

This isn't a question for the Receptionist to answer on its own — forward it into
the workflow and have the values worked out there, by the agents whose job that
is; the Receptionist's part is only to pass the result back to me.

For this run I only need the parameter list — no geometry. Please don't bring in
the Tool Caller or the DC Output Inspector: I don't want a mesh, 3D renders or
blade-section drawings out of this. Every other agent is free to work as much as
it needs, and to iterate until the values are right. Since nothing is being
rendered, have the DC Input Inspector hand back to the Orchestrator rather than
passing things on to the Tool Caller, and let the Planner close the run by
replying to me directly with the final values. No render files will exist at the
end of this cycle — that's expected, not a failure.

Don't come back to me with clarifying questions. If something in my text is
ambiguous, commit to your best reading of it.

Give me the answer in two parts: first the complete parameter set as JSON, in the
canonical order. Then, underneath, one line per parameter telling me the value
and where it came from — the words of mine it came from, or the arithmetic you
used if you derived it (for example, a 120 mm diameter giving a radius of 60).
```

**GT.** Flat 16-value set on the case's deck slide → `gt_quantitative.json`.
**Scoring.** M1 binary (right/wrong per parameter), 0.5 % tolerance.
**Script.** `extract_gt_from_pptx.py` → `benchmark_text_compare.py --benchmarks 2`
(the quant scorer handles both simple and complex; point it at the right folder).
**As-built.** `benchmark1/` is empty — **not yet run**. 2 cases planned.

---

### Case 2 · Text · Quantitative · Complex — `benchmark2`  ·  M1

Same query add-on as Case 1. Design texts are chained-arithmetic puzzles with
unit traps and conditional branches, e.g. `complexQuant1`:

> *"…12.6 cm diameter. The impeller thickness is 18 times smaller than the outer
> radius. The inner blade section thickness should be 1/5th of the outer — but if
> the outer is smaller than 0.045 dm, cap the inner to 0.9 mm…"*

**GT.** Flat 16-value set per case (deck slides 2–4; `complexQuant1` → slide 2,
`complexQuant2` → slide 3). **Scoring.** M1 binary, 0.5 % tolerance.
**Script.**
```bash
python extract_gt_from_pptx.py
python benchmark_text_compare.py --benchmarks 2
```
→ `_analysis_text/benchmark2/<case>/<cond>/report.txt` + `summary.{txt,csv}`.
**As-built.** `complexQuant1`, `complexQuant2` run. **3 more planned** (deck
slide 4 = "Most complex attempt").

---

### Case 3 · Text · Qualitative — `benchmark3`  ·  M2

**Query.** Case design text + the **qualitative add-on** (verbatim). Note it
*allows* geometry (the system may render to check itself) and involves the full
chain incl. Tool Caller + DCOI:

```
That's the kind of propeller I'm after.

This isn't a question for the Receptionist to answer on its own — it should go
into the workflow and be worked out there, with the Receptionist only relaying
what comes back.

I haven't given you numbers, so I'm expecting you to translate what I've described
into concrete values. The parameter set is what I want back — how you get there is
entirely up to you. Rendering the sections or the 3D to see what your numbers
actually produce is available to you if you want it, and it may tell you more than
reasoning alone.

Don't come back to me with clarifying questions. Where my description doesn't pin
something down, use your engineering judgement and commit to a value.

Give me the answer in two parts: first the complete parameter set as JSON, in the
canonical order. Then, underneath, one line per parameter — all sixteen of them —
telling me the value you chose and why: which part of my description drove it, or,
where my description didn't reach, what reasoning made you settle on that number.
Finish with a couple of lines on what made you confident the set as a whole
matches what I asked for.
```

**GT.** An accepted band `{target, min, max}` per parameter on the case's deck
slide (slides 5–9; `complexQual1` → slide 5, `complexQual2` → slide 6) →
`gt_qualitative.json`. **Scoring.** M2 binary — IN / OUT of `[min, max]`, plus
how far outside on a miss. **Script.**
```bash
python extract_gt_from_pptx.py
python benchmark_text_compare.py --benchmarks 3
```
**As-built.** `complexQual1`, `complexQual2` run. **3 more planned** (deck slides
7–9). *To add: fill the deck slide, map `case → slide` in `SLIDE_FOR_CASE`
(`extract_gt_from_pptx.py`), create the folder.*

---

### Cases 4 & 5 · Count blades + orientation — `benchmark4` (fine, Task 2) · `benchmark5` (rough, Task 1)  ·  M3, M4

**Measures.** Perception (**M3** blade count, absolute error) **and** orientation
(**M4** binary) from a sketch — *and* routing discipline: a question must be
answered **without** a design generation (only R / O / UII / Planner may act).

**Query** (`BladeCountingQuery.txt`, verbatim):

```
I've uploaded a rough sketch of a propeller.

How many blades does it have? Count them from the drawing and tell me the number.

Please also say briefly how you read it — what made you settle on that count. If
any part of the drawing is unclear, still give me a single best answer, but tell
me where you were unsure.
```

Input image: Case 4 uses the *fine* sketch (Task 2), Case 5 the *rough* sketch
(Task 1).

**GT.** Hand-filled `blade_counts.json` — true count per sample + each condition's
reported answer (read by eye; prose varies too much for a safe regex).
**Scoring.** M3 = `|answer − truth|`; **plus a routing check** flagging any run
that touched DCIC / DCII / Tool Caller / DCOI.
**Script.** `python benchmark_text_compare.py --benchmarks 4`.
**As-built gaps.**
- **M4 orientation is not scored** — only the blade count (M3) and routing.
- `benchmark4` (0178/0273) run and clean; **`benchmark5` not yet documented as
  run** (folder reuses the same query; its Task-1 image set + scoring to be
  confirmed).

---

### Case 6 · Extract dimensions from sketches — `benchmark6`  ·  M5, M6

**Plan.** Read the dimensions off the filled template — some written as numbers,
some encoded by *how* the user drew relative to the printed dashed circles/boxes
— and report them. **M5** (explicit dims, binary) + **M6** (inferred dims,
relative error). No written text description.

**Query as run** (`query_benchmark6.txt`, verbatim — note it asks to *recreate
with 3D geometry*, i.e. it is closer to a no-text variant of Case 7 than to pure
extraction):

```
I've uploaded my drawings, together with the blank template and a note describing it.

Please recreate this propeller from the drawings, matching the blade sections as
closely as you can — make as many refinement attempts as you need until the
section shapes genuinely match, not just the ordering and rough proportions.

The dimensions I specified in the drawings are hard requirements and must be
reproduced exactly. Some I wrote as numbers; others I expressed through how I drew
relative to the template's printed features. Both are equally binding. Working out
which dimensions I specified is part of the task — I am not going to list them.

Everything I did not specify is yours to choose, and you may vary it as freely as
you need to make the rendered sections match my drawn ones as closely as possible.

If one of my specified dimensions cannot be reproduced exactly, do not silently
round it or design around it — say so.

At the end, report: every dimension you concluded I specified, its value, and how
you read it (a written number, or extrapolated — and against which printed
feature); which parameters you treated as free and why; how close the final
sections got, and anything you could not match, with the reason.
Report back to me once you have the final solution with 3D geometry.
```

**GT.** The submitted design the sketch was drawn from —
`…/step10results/20260526_Results_step10.json`, entries keyed by the 4-digit
`code` (= sample folder). Each entry's `params` = the 16-value GT.
**Scoring (as-built).** `benchmark_geometry_compare.py` scores per-parameter
error (both % of GT and % of allowed range) and renders a **geometry comparison
image** (GT beside every condition, common scale, with a blade-sections row).
**Script.** `python benchmark_geometry_compare.py --benchmarks 6`.
**As-built gaps.**
- The **query generates geometry** rather than only extracting dimensions, so
  as-run this overlaps Case 7 (minus the text). Pure M5 dimension-extraction
  scoring is not separately implemented.
- **M6 relative error** is approximated by the per-parameter error table.

---

### Case 7 · Sketch interpretation → generate geometry — `benchmark7`  ·  M6, M7

**Plan.** Full pipeline: Task 2 + Task 3 + **written text** fed together; replicate
the sketches, flagging where they may differ from written dimensions. **M6**
(inferred dims, relative error) + **M7** (3D geometry correctness — volume +
point-cloud difference after normalization).

**Query as run** (`query_benchmark7.txt`, verbatim; the `<paste …>` marker is
replaced per sample with that sample's `description`):

```
I've uploaded my drawings, together with the blank template and a note describing it.

Below is also the description I wrote about this propeller when I designed it.
The description and the drawings are two accounts of the same propeller.

--- MY DESCRIPTION ---
<paste the sample's description here>
--- END OF MY DESCRIPTION ---

Please recreate this propeller as precisely as you possibly can — precision is
what matters most to me here. I mean the finished propeller, not only its
cross-sections: match the blade sections in my sketches as closely as you can, and
make sure the propeller they build up into matches my drawings too. Make as many
refinement attempts as you need on both. I'll be judging the result on the
finished geometry, so keep refining until both genuinely match what I drew —
getting the ordering and the rough proportions right is not enough.

Important: matching what I actually described and drew matters more to me than any
single number in isolation. Every quantitative value I gave you — whether written
on the drawings or in the description above — is a starting estimate, not a fixed
requirement. You have my explicit authorisation to change any of them, including
the overall diameter, if changing it produces a closer match to what I described
and drew.

Where my description and my drawings seem to disagree, do not silently pick one
and move on: decide which is more trustworthy for that feature, and tell me which
you followed and why.

At the end, tell me explicitly: which of my original values you changed and why;
where each key value came from; anywhere the two disagreed and which you followed;
how close the final sections and finished propeller got, and anything you could
not match or represent, with the reason.
Report back to me once you have the solution.
```

**GT.** Same as Case 6 (`step10results/…json` by `code`). Benchmark 7 has no
separate GT file yet; it reuses Case 6's — see `GT_JSON_BY_BENCHMARK` in the
geometry script.
**Scoring (as-built).** Per-parameter error + the geometry comparison image, same
as Case 6.
**Script.** `python benchmark_geometry_compare.py --benchmarks 7` (or run 6 and 7
together).
**As-built gaps.**
- **M7 (volume + point-cloud difference after normalization) is NOT implemented.**
  The current geometry score is per-parameter error plus a *visual* isometric
  comparison. A true M7 would mesh both designs, normalize scale/orientation, and
  compute a volumetric + point-cloud distance. This is the biggest plan-vs-built
  gap.
**Finding so far.** Adding the description improved 6 of 8 runs; mean per-run
error dropped ~22.5 % → 16.2 % of range.

## A.6 Ground-truth sources

| Source | Feeds | Shape |
|---|---|---|
| `20260721_FixingSystem_Testing_corrected_v2.pptx` | Cases 1–3 | per-slide design text + GT (flat values / `{target,min,max}` bands) |
| `gt_quantitative.json` / `gt_qualitative.json` | Cases 1–3 | extracted from the deck by `extract_gt_from_pptx.py`, keyed by case |
| `blade_counts.json` | Cases 4–5 | hand-filled: true count + each condition's answer |
| `20260526_Results_step10.json` | Cases 6–7 | original submissions; entry keyed by 4-digit `code`, `params` = 16-value GT |

A `.pptx` is a zip of XML, so `extract_gt_from_pptx.py` reads it with the
standard library — no `python-pptx` needed. The slide↔case map is confirmed by
matching each case's own text against the slide body; `--list` re-verifies it.

## A.7 Analysis scripts

All in `TESTS/`; run with the system's default Python (`numpy` + `PIL`; the
geometry script also needs Node with `three` installed in the app checkout).

| Script | Purpose | Writes |
|---|---|---|
| `extract_gt_from_pptx.py` | pull GT out of the deck | `gt_quantitative.json`, `gt_qualitative.json` |
| `benchmark_text_compare.py` | score cases 1–5 (text + blade count) | `_analysis_text/` |
| `benchmark_geometry_compare.py` | score + render cases 6–7 | `_analysis/` |
| `benchmark_cost_estimate.py` | estimate tokens / time / cost | `_analysis_cost/` |
| `make_results_pptx.py` | build a results deck | `benchmark_results.pptx` |

**Dependency order:**
```bash
cd "…/21.07/testResults"
python extract_gt_from_pptx.py          # after any deck GT change
python benchmark_text_compare.py        # cases 1–5
python benchmark_geometry_compare.py    # cases 6–7  (--repo <app checkout> for FEG)
python benchmark_cost_estimate.py       # all
python make_results_pptx.py             # the deck
```
- **Geometry engine.** The geometry script shells out to the app's headless-Node
  FEG exporter and renders isometrics with a self-contained numpy/PIL rasteriser
  — no trimesh/pyrender install. Needs `three` installed once in the app checkout
  and its path via `--repo`.
- **Cost.** Tokens are **modelled** (logs record no usage); time and turns are
  measured. Costs assume prompt caching. Two load-bearing uncertainties: caching
  (~3× spread) and the ~4-chars/token approximation. It is an order-of-magnitude
  figure.

## A.8 As-built gaps (summary)

| Planned (deck) | Built / run today |
|---|---|
| M4 orientation (cases 4–5) | **not scored** — only M3 count + routing |
| Case 6 = dimension extraction (M5) | folder runs a *recreate-geometry* query; scored like Case 7 |
| M6 relative error | approximated by the per-parameter error table |
| M7 = volume + point-cloud after normalization | **not implemented** — per-parameter error + visual isometric compare instead |
| 3 iterations averaged | runs scored individually; no cross-iteration averaging yet |
| 20 scans per image case | 0178, 0273 run; more IDs (incl. 0365) planned |
| Cases 1 fully; 2,3 five each | Case 1 not run; 2 & 3 have 2 of 5 each |

---

# Part B — The three experiments

All three run the **same benchmark above**; each varies one factor. The
`<CONDITION>` subfolder in the layout is where an experiment's condition is
recorded.

## B.1 Test 1 — LLM comparison

**Question.** Expensive/smart vs cheap/fast LLMs — how much does model tier buy?

**Performance tiers** (deck slide 6):

| Provider | High-performance | Medium-performance | Low-performance |
|---|---|---|---|
| OpenAI | `gpt-5.5` (reasoning High) | `gpt-5.4` (High) | `gpt-5.4-mini` (Med/High) |
| Anthropic | `claude-opus-4-8` | `claude-sonnet-4-6` | `claude-haiku-4-5` |
| Google | Gemini 3.1 Pro | Gemini 3.5 Flash | Gemini 3 Flash |

**Experiment subjects** (the conditions):

| Subject | Configuration | Status |
|---|---|---|
| 1 | **All-high** performance agents (Anthropic → `claude-opus-4-8`) | run → `CLAUDE_OPUS_4_8/` |
| 2 | **All-medium** (OpenAI → `gpt-5.4`) | run → `GPT_5_4/` |
| 3 | **All-low** (Anthropic + OpenAI → `claude-haiku-4-5`, `gpt-5.4-mini`) | run → `CLAUDE_HAIKU_4_5/`, `GPT_5_4_mini/` |
| 4 | **High + medium** mix | **SKIPPED** (saving money) |
| 5 | **High + medium + low**, a **different LLM per agent** | **TO BE BUILT** (with the team) |

Subject 5's per-agent assignment will be set from the tier table above, using
each agent's reasoning and context-window needs. **Hypothesis:** Subject 1 first
in quality, Subject 4 second, Subject 5 third — but Subject 5 with the lowest
cost and time, making it the **best compromise**.

**Model → folder mapping (as run).** The `<CONDITION>` folders are Test-1
subjects: `CLAUDE_OPUS_4_8` = Subj 1, `GPT_5_4` = Subj 2, `CLAUDE_HAIKU_4_5` +
`GPT_5_4_mini` = Subj 3.

> **Open decision.** Whether Tests 2 & 3 use Subject 5 (the per-agent mix) is
> **not yet finalised** — the expectation is that Subject 5 is the best
> compromise, so Tests 2 & 3 would use it, but this is confirmed only after Test
> 1's results are in.

## B.2 Test 2 — Number of agents

**Question.** Does reducing the agent count hurt? The Receptionist is an
interface add-on kept in every configuration; the *chain* is what shrinks.

**Full rationale + diagrams:** `extra_utilities/design_agent_count_variants.md`.
The three architectures (its §7):

| Function | 7-agent (baseline) | 5-agent (merge-only) | 3-agent (strip-down) |
|---|---|---|---|
| interface | Receptionist | Receptionist | Receptionist |
| perceive | UII | UII | ┐ **Interpreter-Conductor** |
| plan | Planner | ┐ **Conductor** | │ (UII+Planner+Orchestrator) |
| route | Orchestrator | ┘ (Planner+Orchestrator) | ┘ |
| create | DCIC | ┐ **Creator** | ┐ **Designer** |
| validate | DCII | ┘ (DCIC+DCII self-check) | ✕ *dropped* │ (DCIC+Tool Caller) |
| execute | Tool Caller | Tool Caller | ┘ |
| critique | DCOI | DCOI | **Critic** (DCOI) |
| **chain count** | **7** | **5** | **3** |

- **7 → 5** removes the dedicated LLM router (into the Conductor) and the
  independent parameter auditor (into the Creator as self-validation).
- **5 → 3** fuses perception into planning, execution into creation, and **drops
  validation entirely** — the minimal brain/hands/eyes triad.

The cleanest result is the **validation gradient**: input-checking going
*independent (7) → self-check (5) → none (3)*. Each configuration runs the full
benchmark; per the open decision above, this test is expected to use Test 1's
Subject 5 LLM mix. *(This test is being built in a separate work stream; that
design doc is the source of truth for the architectures.)*

## B.3 Test 3 — RAG comparison

**Question.** Does giving the system *previous experience* (RAG on) beat running
without it (RAG off)?

Each condition (RAG on / RAG off) runs the full benchmark, expected on Test 1's
Subject 5 LLM mix. **Details deferred** — the RAG populating algorithm, the
retrieval process and the on/off harness are still being built (deck agenda). To
be documented when those land.

---

# Part C — Extending & open items

- **Add a model / LLM condition** → run the pipeline under that condition, save
  the log under `benchmark<N>/<case>/<CONDITION>/`; add the condition to each
  script's `MODELS` / `MODEL_LABEL` list.
- **Add a scan** (e.g. `0365`) → add its sketches under the image cases; ensure
  `step10…json` has a matching `code` (cases 6–7) or add it to `blade_counts.json`
  (cases 4–5).
- **Add a text case** → author its deck slide (text + GT), map `case → slide` in
  `extract_gt_from_pptx.py`, create the folder, re-run extraction + scorer.

**Open items:**
- `benchmark1` (Case 1) not run; Cases 2 & 3 have 2 of 5 each; Case 5 (rough
  sketches) run-status to confirm.
- **M4 orientation**, **M5 pure dimension-extraction**, and **M7 point-cloud
  geometry** metrics are not yet implemented (§A.8).
- **Test 1 Subject 5** (per-agent LLM mix) to be built.
- Whether **Tests 2 & 3 use Subject 5** — pending Test 1 results.
- **Test 3 (RAG)** harness + documentation — pending.
- **Cost precision** — real per-call token usage from the API responses would
  collapse the caching + chars/token uncertainties; not done.
