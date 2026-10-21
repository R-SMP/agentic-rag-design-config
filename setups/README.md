# setups/ — the design configurators

One folder per design configurator, all stored the same way: each one is a
*setup* — `pack.yaml`, `parameters.json`, `fragments/`, `tools/`, `assets/`,
`preview/` (`engine/pack.py`; each setup's own `README.md` says what is
where).  The engine and the agents are the same for all of them.

* `propeller/` — the propeller impeller configurator, the one the app loads
  the first time it starts.  It is the only one that uses the database and
  its file store (`database: true` in its `pack.yaml`).

A configurator can sit here on one computer without reaching the repository
or an image: `.gitignore` and `.dockerignore` leave it out.  So far:

* `vacuum_hose_adapter/` — its OpenSCAD model's author asks that the script
  not be hosted or uploaded anywhere; it stays out until they agree
  (TODO F125).

The app's main menu (`/`) loads any of them in place, with no restart, and
the app starts with the one loaded last (`engine/setups.py`);
`DC_PACK_DIR=setups/<name>` makes it start with another.  For the Studio:
`python -m studio --pack setups/<name>`.
