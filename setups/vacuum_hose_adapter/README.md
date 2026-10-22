# The vacuum hose adapter configurator

A design configurator around an OpenSCAD model, built in the MAS Studio
(MAS-blueprint P8): the model's Customizer settings became its 187
parameters in 21 groups.

* `tools/vacuum_hose_adapter/`: the generator the agents call; OpenSCAD
  builds the model from an attempt's parameters.
* `tools/vacuum_hose_adapter_geometry/`: the same model at the downloads'
  detail, for the Download buttons.
* `vacuum-hose-adapter.scad` (in both) is the model author's script
  (github.com/ostat/vacuum-hose-adapter-openscad).  Its header asks that it
  not be hosted or uploaded; it is in this private repository, and in its
  deploy behind an access code, by the owner's decision (TODO F125).
* The image installs the OpenSCAD the tools need (the repository's
  `Dockerfile`).  It uses the database (`database: true` in `pack.yaml`):
  its sessions go in the database's `vacuum_hose_adapter` section, its own
  (`engine/db_sections.py`).  The primer is off (its agent lists are empty;
  its picture and text are still the propeller's).
* No browser preview: the Parameters page's Preview button builds the model
  on the server.

How a setup folder is laid out: `setups/propeller/README.md`.
