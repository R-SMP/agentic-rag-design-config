# setups/ — the design configurators

One folder per design configurator, all stored the same way: each one is a
*setup* — `pack.yaml`, `parameters.json`, `fragments/`, `tools/`, `assets/`,
`preview/` (`engine/pack.py`; each setup's own `README.md` says what is
where).  The engine and the agents are the same for all of them.

* `propeller/` — the propeller impeller configurator, the one the engine runs
  unless `DC_PACK_DIR` names another (`config.py`, `engine/setups.py`).

A configurator can sit here on one computer without reaching the repository
or an image: `.gitignore` and `.dockerignore` leave it out.  So far:

* `vacuum_hose_adapter/` — its OpenSCAD model's author asks that the script
  not be hosted or uploaded anywhere; it stays out until they agree
  (TODO F125).

To run another one: `DC_PACK_DIR=setups/<name>` for the app,
`python -m studio --pack setups/<name>` for the Studio.
