"""The pack's prompt flags: ``<<IF:tool:…>>`` and ``<<IF:setting:…>>``.

A fragment of the pack can carry text that only applies while one of the
configurator's tools is enabled, or while one of its boolean settings is on:

    <<IF:tool:render_blade_sections>> … <</IF:tool:render_blade_sections>>
    <<IFNOT:setting:generate_and_render_propeller.mesh_checks>> … <</IFNOT:…>>

``IF`` keeps its text when the flag is true, ``IFNOT`` when it is false; the
other one is removed, and a line that the removal leaves empty disappears
with it (``agents/shared/prompts.apply_if_flags``).

Which Workflow Settings value sets each flag is declared by the pack, in
``dc_pack/pack.yaml``:

    tool_switches:  {<tool>: <SETTING>}            -> flag  tool:<tool>
    tool_settings:  {<tool>.<name>: <SETTING>}     -> flag  setting:<tool>.<name>

A stopgap: when the tools get their own files (MAS-blueprint P3c), each
tool's file declares its switch and settings instead.  Values are read fresh
from ``workflow_settings.settings`` on every call (the web app reloads that
module before a session is built), like every other setting.
"""

from __future__ import annotations

import yaml

from engine import pack as _pack


class PackFlagError(ValueError):
    """pack.yaml names a flag source that does not exist."""


def declared() -> dict[str, str]:
    """``{flag: SETTING}`` as declared in ``dc_pack/pack.yaml``."""
    path = _pack.pack_dir() / "pack.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, str] = {}
    for key, prefix in (("tool_switches", "tool:"), ("tool_settings", "setting:")):
        table = data.get(key) or {}
        if not isinstance(table, dict):
            raise PackFlagError(f"{path.name}: {key} must be a mapping")
        for name, setting in table.items():
            out[f"{prefix}{name}"] = str(setting)
    return out


def values() -> dict[str, bool]:
    """Every pack flag with its value for the session being built."""
    from workflow_settings import settings as _settings

    out: dict[str, bool] = {}
    for flag, setting in declared().items():
        if not hasattr(_settings, setting):
            raise PackFlagError(
                f"dc_pack/pack.yaml: flag {flag} reads {setting}, which is not "
                f"in workflow_settings/settings.py")
        out[flag] = bool(getattr(_settings, setting))
    return out
