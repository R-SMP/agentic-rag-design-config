"""Blade-sections visualizer tool package.

Exposes :func:`render_blade_sections` — a Tool-Caller tool that renders the
three blade cross-sections (Inner / Middle / Outer) stacked vertically as a
PNG, optionally on a 1 mm grid.  Gated by the
``BLADE_SECTIONS_VISUALIZER_ENABLED`` workflow setting (see
``workflow_settings/blade_sections_access.py``).
"""

from tools.render_blade_sections.render_blade_sections import render_blade_sections

__all__ = ["render_blade_sections"]
