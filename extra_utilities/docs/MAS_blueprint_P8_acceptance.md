# MAS-blueprint P8 — acceptance: a second configurator built only through the Studio

**Date:** 2026-10-21.  **Result:** passed — the throw-away configurator ran a full
real session.

The plan's P8 acceptance (`MAS_blueprint_proposal.md` §10): a throw-away second
design configurator, not shipped, built only through the Studio, runs a full
session.  The owner chose the vacuum hose adapter (an OpenSCAD model), one real
LLM session in topology 7 with gpt-5.4-mini for every agent, run on the
developer's computer with no database; Railway later (TODO F125).

The setup and the model stay outside this repository (the model's author asks
that the script not be hosted): `C:\Users\vince\MT Coding\DCs\hose_dc\`.

## 1. Built through the Studio

On a copy of the propeller example, with the Studio (`python -m studio --pack ...`):

1. **Import** — `combined/vacuum-hose-adapter.scad` dropped on the Tools page,
   *Start a new configurator*: 187 parameters in 21 groups (146 with a proposed
   range, 98 used only when a choice has a value); the generator
   `vacuum_hose_adapter` and the geometry tool `vacuum_hose_adapter_geometry`
   replaced the propeller's three tools.
2. **Tools** — the propeller's helper `render_blade_sections` removed (Tools ›
   Remove).
3. **Ranges** — 39 ranges set in one *Paste CSV* (each end's diameter 10–200 mm,
   length 5–150 mm, wall 0.8–6 mm, taper −5–5, the bend 0–180°, ...); the 107
   other proposed ranges kept with *Keep all … in this group*.
4. **Texts** — 37 prompt fields (53 saves: shared texts, per-topology texts and
   agents' own copies) rewritten for the hose adapter, approved by the owner as
   one list; then 10 of the texts the app's code reads (the web app's title,
   examples in tool descriptions, the database examples), once the Studio could
   edit them (§2).  `$dc_params_primer_text` stayed as it was: the primer was
   switched off for the session (TODO F127).
5. **Validate** — 23 checks pass, no warning, no failure (both OpenSCAD tools
   run on the defaults; a scripted turn per topology).
6. **Download full package** — `vacuum_hose_adapter_design_configurator`.

## 2. What P8 changed in the Studio

* **The texts the app's code reads** (`use: runtime` in the slot registry — the
  web app's title, examples in tool descriptions, the tool runner's list
  entries, the primer's text, the database examples) were not shown by the
  Studio at all, so a configurator built only through it could not stop
  calling itself a propeller.  They are now shown in their sections, marked
  *read by the app*, and edited like every field (`studio/engine_view.py`
  `text_fields`).
* **The downloads read the setup as it is now** (`studio/server.py`): they took
  the last data built, and the title — a text field now — names the files.
* **User docs** — `studio/web/write-a-tool.html` and
  `studio/web/openscad-models.html`, linked from the guide and the Tools page.

## 3. The session

The downloaded package's web app, on the developer's computer: its own
Workflow Settings set every agent to gpt-5.4-mini (LLM routing: OpenAI) and the
primer off; the database addresses were empty; OpenSCAD 2026.10.18.  Installed
for it (owner-approved): trimesh 5.1.1, pyrender 0.1.45, pyglet 1.5.31 (below 2,
as pyrender 0.1.45 targets pyglet 1.x; 2.x was not tried), PyOpenGL 3.1.10,
freetype-py, imageio, networkx, scipy; langchain 1.4.6, langchain-core,
langchain-openai, langgraph (+checkpoint, prebuilt, sdk), langsmith, ormsgpack,
websockets.

**Request** (typed in the chat): *I need an adapter from my shop vac's 58 mm hose
to the 100 mm dust port on my table saw, with a 45° bend so the hose clears the
fence rail.*

**The turn**, 85 s: Receptionist → Orchestrator → User Input Inspector
(extraction) → Planner → DC Input Creator (attempt 001) → DC Input Inspector
(revise) → DC Input Creator (attempt 002) → DC Input Inspector (approve) → Tool
Caller → the OpenSCAD generator (11 s: model + three pictures) → DC Output
Inspector (looked at the pictures: approve) → Orchestrator → Planner → Receptionist
(3D viewer, proposed solution) → the user.  *End Session › No — just archive*
ended it cleanly.

**What was built:** end 1 58 mm, end 2 100 mm (both measured as the end's
inside), a 45° bend of radius 120 mm over an 80 mm transition, three barbs per
end, connector 3 off.  The reply said so, and noted that the 100 mm end uses the
model's hose end because the model has no plain port end.

**Cost:** 36 model calls; 429,190 input tokens (292,096 read from the cache),
8,081 output tokens.

## 4. Findings

* **F126** — `$propose_attempt_tool` says "16-parameter" (the propeller's count).
* **F127** — the parameter primer stays the propeller's in a new configurator.
* **F125** — the Railway run, after F123.
* With 187 parameters the DC Input Creator writes every value, and moved many
  settings that were inactive for this design (magnets, flanges, the alignment
  ring) to their range minimums — harmless here, as the hose style ignores
  them; the texts say to leave such settings at their defaults.
* The DC Input Inspector's one revision asked for a "device-facing / open end",
  which the model does not have; the second attempt was the first one with a
  new description.
