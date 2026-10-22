"""TEAM_SIZE -- how many agents the design workflow runs with (3, 5 or 7).

The setting was called ``SYSTEM_TOPOLOGY`` until 2026-10-22.  A
``settings.py`` that still says ``SYSTEM_TOPOLOGY`` (a copy edited before
the rename, an older downloaded setup) is read the same way, and a save
under either name lands on whichever of the two the file holds
(``editor._do_write``).

Read FRESH on every call, never captured at import:
``web_app._build_session`` reloads the settings module in place, and the
Sessions Queue switches the team size between runs inside one process.
"""

from __future__ import annotations

from typing import Any

NAME = "TEAM_SIZE"
OLD_NAME = "SYSTEM_TOPOLOGY"
NAMES = (NAME, OLD_NAME)
DEFAULT = 7


def read(settings_module: Any) -> int:
    """The team size *settings_module* holds, under either name."""
    for name in NAMES:
        if hasattr(settings_module, name):
            return int(getattr(settings_module, name))
    return DEFAULT


def in_file(names: "set[str] | dict") -> str:
    """The name the settings file uses: the new one unless only the old one
    is there."""
    return OLD_NAME if OLD_NAME in names and NAME not in names else NAME
