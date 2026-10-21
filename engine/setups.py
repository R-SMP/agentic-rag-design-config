"""The configurators a repository holds: ``setups/<name>/``, one folder per
configurator, all stored the same way -- each a setup (``pack.yaml``,
``parameters.json``, ``fragments/``, ``tools/``, ``assets/``, ``preview/``;
``engine/pack.py``).  ``setups/README.md`` says which ones git leaves out.

Which one the engine runs: ``DC_PACK_DIR`` when set, else the one loaded
last on this computer (the web app's main menu remembers it,
``workflow_settings/active_setup.json``), else ``setups/propeller``.  Each
keeps its own Workflow Settings choices for its tools and agents in
``workflow_settings/setups/<name>/`` (:func:`settings_file`).

Standard library only: ``config.py`` and the Studio's start read it, the
Studio without loading ``.env``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SETUPS = "setups"
DEFAULT = "propeller"
# A package in the layout from before setups/: its one setup in dc_pack/.
OLD_LAYOUT = "dc_pack"
# The configurator loaded last on this computer; ACTIVE_SETUP_FILE names
# another file (the tests).
ACTIVE_FILE = Path("workflow_settings") / "active_setup.json"
ACTIVE_ENV = "ACTIVE_SETUP_FILE"
SETTINGS_DIR = Path("workflow_settings") / SETUPS


def all_setups(root: Path) -> list[Path]:
    """Every setup in ``<root>/setups/``, by folder name."""
    folder = root / SETUPS
    return sorted(p.parent for p in folder.glob("*/pack.yaml")) if folder.is_dir() else []


def default_setup(root: Path) -> Path:
    """The setup run when nothing else names one: ``setups/propeller``,
    else the first one in ``setups/`` (a package holds one), else
    ``dc_pack/``."""
    own = root / SETUPS / DEFAULT
    if (own / "pack.yaml").is_file():
        return own
    found = all_setups(root)
    return found[0] if found else root / OLD_LAYOUT


def _active_file(root: Path) -> Path:
    named = os.environ.get(ACTIVE_ENV)
    return Path(named) if named else root / ACTIVE_FILE


def remembered(root: Path) -> Path | None:
    """The setup loaded last on this computer, while it is still one of
    ``setups/``."""
    try:
        name = json.loads(_active_file(root).read_text(encoding="utf-8")).get("setup")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(name, str) or not name or Path(name).name != name:
        return None
    path = root / SETUPS / name
    return path if (path / "pack.yaml").is_file() else None


def remember(root: Path, setup: Path) -> None:
    """Remember *setup* -- one of ``setups/`` -- as the one to run at the
    next start; another folder is not remembered."""
    if setup.resolve().parent != (root / SETUPS).resolve():
        return
    path = _active_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"setup": setup.name}) + "\n", encoding="utf-8")


def resolve(root: Path, value: str | None) -> Path:
    """``DC_PACK_DIR`` as the engine takes it: relative to *root*; when
    empty, :func:`remembered`, else :func:`default_setup`."""
    if not value:
        return remembered(root) or default_setup(root)
    p = Path(value)
    return p if p.is_absolute() else root / p


def settings_file(root: Path, setup: Path, name: str) -> Path:
    """This computer's Workflow Settings file *name* for *setup*:
    ``workflow_settings/setups/<setup>/<name>``.  Before setups/ existed the
    one setup -- ``setups/propeller``, or a package's ``dc_pack/`` -- kept
    its own in ``workflow_settings/`` itself: it is moved here the first
    time."""
    target = root / SETTINGS_DIR / setup.name / name
    first = {(root / SETUPS / DEFAULT).resolve(), (root / OLD_LAYOUT).resolve()}
    if not target.exists() and setup.resolve() in first:
        old = root / "workflow_settings" / name
        if old.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            old.replace(target)
    return target
