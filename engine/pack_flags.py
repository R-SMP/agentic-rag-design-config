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
the prompts as it does when the tool is switched off.  One whose name is
close to a tool that IS in the pack is more likely a misspelling
(:func:`near_tool`): the checks report it as an error.
"""

from __future__ import annotations

import difflib

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


def near_tool(flag: str) -> str | None:
    """For a flag naming a tool that is not in the pack: the pack's tool
    whose name is close to it (a likely misspelling), else None."""
    m = _pack_tools._FLAG_TOOL_RE.match(flag)
    if not m or not absent(flag):
        return None
    close = difflib.get_close_matches(m.group(1) or m.group(2),
                                      list(_pack_tools.manifests()), n=1, cutoff=0.8)
    return close[0] if close else None
