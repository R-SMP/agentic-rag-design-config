"""Master-switch read for the Blade-sections visualizer tool.

A thin helper mirroring the read pattern in
``workflow_settings.database_access`` / ``workflow_settings.ocr_access``: the
value is read *fresh* from the (reloaded) ``settings`` module on every call, so
a toggle saved via the web Workflow Settings editor takes effect on the NEXT
session build — ``web_app._build_session`` reloads ``workflow_settings`` in
place before constructing the agents.

There is no per-agent granularity (this is a single global switch), so the
helper exposes just :func:`is_enabled`.  Defaults to ``True`` when the setting
is absent, matching the ``BLADE_SECTIONS_VISUALIZER_ENABLED = True`` default in
``settings.py``.
"""

from __future__ import annotations

from workflow_settings import settings as _workflow_settings


def is_enabled() -> bool:
    """True when the blade-sections visualizer tool is switched on."""
    return bool(
        getattr(_workflow_settings, "BLADE_SECTIONS_VISUALIZER_ENABLED", True)
    )
