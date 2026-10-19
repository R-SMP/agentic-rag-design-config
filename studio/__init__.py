"""The MAS Studio: set up a multi-agent system for a design configurator.

    python -m studio [--pack <folder>] [--port 8770]

MAS-blueprint P5 shows the setup; P6a edits its text fields, P6b its
parameters and agent access, P6c its tools.  ``engine_view.py`` computes
what the screens show (with the engine itself, in child processes),
``server.py`` serves the page in ``web/`` and keeps engine processes waiting
for the prompt viewer, ``editing.py`` writes a text field's files,
``params_edit.py`` the parameter file, the agents' parameter lists and the
access grid, ``tools_edit.py`` a tool's files (``yaml_patch.py``: a manifest
changed in its own layout).
"""
