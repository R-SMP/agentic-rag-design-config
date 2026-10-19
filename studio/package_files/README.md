# {{TITLE}}

A multi-agent system for the {{DC}}: agents that turn a design request
into the configurator's parameters, build the design with its tools, check
it and explain it.  Made with the MAS Studio.

* **Deploy it**: `DEPLOY.md`.
* **Change it**: `python -m studio` opens the MAS Studio on `dc_pack/` (the
  configurator: its parameters, texts and tools); **Validate** checks it.
  `python -m studio validate` runs the same checks on the command line.
* **What is where**: `dc_pack/` is this configurator; everything else is the
  engine that runs it (`agents/`, `engine/`, `tools/`, `web/`,
  `workflow_settings/`, `web_app.py`) and the Studio (`studio/`).
  `setup_info.json` says when and from what this folder was made.
