# setups/ — the design configurators

One folder per design configurator, all stored the same way: each one is a
*setup* — `pack.yaml`, `parameters.json`, `fragments/`, `tools/`, `assets/`,
`preview/` (`engine/pack.py`; each setup's own `README.md` says what is
where).  The engine and the agents are the same for all of them.

* `propeller/` — the propeller impeller configurator, the one the app loads
  the first time it starts.  It uses the database and its file store
  (`database: true` in its `pack.yaml`); its sessions are in the database's
  `propeller` section (each configurator has its own, named after its
  folder: `engine/db_sections.py`).
* `vacuum_hose_adapter/` — a configurator around an OpenSCAD model, built in
  the MAS Studio (MAS-blueprint P8).  Its tools run OpenSCAD, which the
  image installs (the `Dockerfile`'s OpenSCAD block, the one a package of it
  gets: `studio/package.py`).  It uses the database too: its sessions are
  in the `vacuum_hose_adapter` section.  The model's script asks not
  to be hosted or uploaded; it is here by the owner's decision, in a private
  repository whose deploy asks for an access code (TODO F125).

A configurator can also stay on one computer: a line in `.gitignore` and
`.dockerignore` leaves its folder out (a downloaded package drops such
lines).  None is left out now.

The app's main menu (`/`) loads any of them in place, with no restart, and
the app starts with the one loaded last (`engine/setups.py`);
`DC_PACK_DIR=setups/<name>` makes it start with another.  For the Studio:
`python -m studio --pack setups/<name>`.
