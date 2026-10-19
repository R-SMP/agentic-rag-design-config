"""__DISPLAY__ -- a helper tool (made from the Studio's helper template).

A plain function: the engine builds the agents' tool from its signature and
the manifest's description (engine/pack_tools.py).  It is given the path of
an attempt's ``parameters.json`` and returns the text the agent reads.
"""

from __future__ import annotations

import json
from pathlib import Path


def __NAME__(parameters_path: str) -> str:
    """Read the attempt's parameter values and summarise them."""
    path = Path(parameters_path)
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"Error: could not read {path}: {exc}"
    shown = ", ".join(f"{k}={v}" for k, v in list(values.items())[:8])
    more = f" (and {len(values) - 8} more)" if len(values) > 8 else ""
    return f"Read {len(values)} parameter values from {path.name}: {shown}{more}."
