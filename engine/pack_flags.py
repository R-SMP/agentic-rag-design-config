"""The pack's prompt flags: ``<<IF:tool:…>>`` and ``<<IF:setting:…>>``.

A fragment of the pack can carry text that only applies while one of the
configurator's tools is enabled, or while one of its boolean settings is on:

    <<IF:tool:render_blade_sections>> … <</IF:tool:render_blade_sections>>
    <<IFNOT:setting:generate_and_render_propeller.mesh_checks>> … <</IFNOT:…>>

``IF`` keeps its text when the flag is true, ``IFNOT`` when it is false; the
other one is removed, and a line that the removal leaves empty disappears
with it (``agents/shared/prompts.apply_if_flags``).

The flags come from the tools themselves (``dc_pack/tools/<tool>/tool.yaml``,
``engine/pack_tools.py``): ``tool:<name>`` is the tool's on/off switch (true
for a tool without one), ``setting:<name>.<setting>`` each boolean tool
setting.  Values are read fresh on every call, with the Workflow Settings
changes laid over the defaults.

A flag naming a tool that is not in the pack -- its folder was removed --
reads as switched off (:func:`absent`), so text marked for that tool leaves
the prompts as it does when the tool is switched off.
"""

from __future__ import annotations

from engine import pack_tools as _pack_tools

PackFlagError = _pack_tools.PackToolError


def declared() -> list[str]:
    """Every flag the pack's tools offer."""
    return list(_pack_tools.flag_values())


def values() -> dict[str, bool]:
    """Every pack flag with its value for the session being built."""
    return _pack_tools.flag_values()


def absent(flag: str) -> bool:
    """True when *flag* names a tool that is not in the pack."""
    return _pack_tools.names_absent_tool(flag)
