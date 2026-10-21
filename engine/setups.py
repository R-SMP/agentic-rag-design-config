"""The configurators a repository holds: ``setups/<name>/``, one folder per
configurator, all stored the same way -- each a setup (``pack.yaml``,
``parameters.json``, ``fragments/``, ``tools/``, ``assets/``, ``preview/``;
``engine/pack.py``).  ``setups/README.md`` says which ones git leaves out.

Standard library only: ``config.py`` and the Studio's start read it, the
Studio without loading ``.env``.
"""

from __future__ import annotations

from pathlib import Path

SETUPS = "setups"
DEFAULT = "propeller"
# A package in the layout from before setups/: its one setup in dc_pack/.
OLD_LAYOUT = "dc_pack"


def all_setups(root: Path) -> list[Path]:
    """Every setup in ``<root>/setups/``, by folder name."""
    folder = root / SETUPS
    return sorted(p.parent for p in folder.glob("*/pack.yaml")) if folder.is_dir() else []


def default_setup(root: Path) -> Path:
    """The setup run when ``DC_PACK_DIR`` names none: ``setups/propeller``,
    else the first one in ``setups/`` (a package holds one), else
    ``dc_pack/``."""
    own = root / SETUPS / DEFAULT
    if (own / "pack.yaml").is_file():
        return own
    found = all_setups(root)
    return found[0] if found else root / OLD_LAYOUT


def resolve(root: Path, value: str | None) -> Path:
    """``DC_PACK_DIR`` as the engine takes it: relative to *root*, and
    :func:`default_setup` when empty."""
    if not value:
        return default_setup(root)
    p = Path(value)
    return p if p.is_absolute() else root / p
