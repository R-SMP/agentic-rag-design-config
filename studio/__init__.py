"""The MAS Studio: set up a multi-agent system for a design configurator.

    python -m studio [--pack <folder>] [--port 8770]

MAS-blueprint P5 shows the setup; P6a edits its text fields.
``engine_view.py`` computes what the screens show (with the engine itself, in
child processes), ``server.py`` serves the page in ``web/`` and keeps engine
processes waiting for the prompt viewer, ``editing.py`` writes a field's
files.
"""
