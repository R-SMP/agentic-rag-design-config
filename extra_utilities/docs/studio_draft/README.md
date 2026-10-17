# MAS Studio — interface draft (proof of concept)

A clickable draft of the Studio described in `../MAS_blueprint_proposal.md`
(revision 1: a hosted web app with a local mode).  It is **not** the Studio:
there is no server and no engine wiring.  Every screen shows the **real
propeller pack** of this branch, and a mock bridge answers the page's calls
the way the hosted server will (`POST /api/<name>` → `{ok: true, …}`).

Open `index.html` in a browser (double-click).  The look is the studio UI
kit's (`base.css`, copied unchanged; `studio.css` adds the Studio's pieces).

The real Studio is `studio/` (`python -m studio`, MAS-blueprint P5a): these
screens made real, read-only for now, with the screens that come later
marked.  This draft stays as the picture of those later screens (the landing
page, import, New tool, Validate, the downloads, local Test tool).

## The process, in pictures

`images/00_overview.png` strings the 15 steps together; one PNG per step:

| # | Image | Screen |
|---|---|---|
| 1 | `01_landing.png` | the three buttons: use the propeller example / create your own / import a setup |
| 2 | `02_create.png` | create your own: start from the propeller example or blank |
| 3 | `03_import.png` | import a setup file: what is inside, tools flagged as code, never run |
| 4 | `04_parameters.png` | the one parameter list (catches the real `middlePos` unit disagreement) |
| 5 | `05_examples_grid.png` | the 3 / 5 / 7 grid with link icons + "where it lands" |
| 6 | `06_description_unlinked.png` | per-topology (unlinked) texts and per-agent copies |
| 7 | `07_outputs_vocabulary.png` | the output vocabulary, each form in a real sentence |
| 8 | `08_blank_start.png` | starting blank: the propeller value as grey reference |
| 9 | `09_tools_new_tool.png` | tool list + "New tool"; Test tool disabled on the website |
| 10 | `10_agent_access.png` | which agent sees the parameter list, per role and topology |
| 11 | `11_settings_secrets.png` | tool settings + the secrets to set later (names only) |
| 12 | `12_prompt_viewer.png` | every assembled prompt, coloured by origin |
| 13 | `13_validate.png` | hosted Validate: static checks + every prompt assembled |
| 14 | `14_download.png` | setup file vs full package |
| 15 | `15_local_test_tool.png` | the same Tools screen on your own computer: Test tool runs |

## What is real and what is not

Real (read from this branch by `build_draft_data.py`, through the Studio's own
functions in `studio/engine_view.py`): the 16 parameters, the 99 text fields
and their three topology copies, every "where it lands" sentence and every
prompt colour (marker-assembled and checked against the real prompts), the
role map, the settings, the environment-variable names, the Validate
findings, the 357-prompt matrix summary, and the local-mode test run
(`render_blade_sections` really run on the default parameters).

Not real yet: the downloads, saving, and the New-tool form's example values
(a made-up turbine wheel).  The setup's files (`pack.yaml`, `tool.yaml`, the
`dc_pack/` layout) and the section each field is filed under (the slot
registry's `section`) are real since P1-P4.

## Rebuild

```
py -3.13 extra_utilities/docs/studio_draft/build_draft_data.py   # draft_data.js (~1 min)
py -3.13 extra_utilities/docs/studio_draft/shoot.py              # images/ (headless Edge)
```
