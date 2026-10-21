"""The primer: one picture and its text, sent to the agents the setup names.

``agents/shared/dc_primer.py`` sends it with every call of those agents,
between their system prompt and the conversation.  What it is made of and
who gets it is the setup's, in ``dc_pack/pack.yaml``::

    primer:
      image: dc_params_primer.png      # a PNG in assets/; empty: the text alone
      agents:                          # per topology, the agents that get it
        7: [user_input_inspector, dc_input_creator, dc_input_inspector, dc_output_inspector]
        5: [user_input_inspector, dc_input_creator, dc_output_inspector]
        3: [design_engineer, requirements_analyst]

The text is the text field ``$dc_params_primer_text`` (an agent with its own
copy gets its copy).  Any agent of a topology may get it but the Database
Handler, which only saves the session.  A setup made before the section
existed reads as :data:`DEFAULT` -- the six design agents and
``assets/dc_params_primer.png`` -- so it behaves as it did.  Workflow
Settings' ``DC_PARAMS_PRIMER_ENABLED`` switches it off for every agent.

Read fresh on every call, like the parameter-access grid
(``engine/parameter_access.py``): an edit takes effect on the next call.
Imports nothing from the agents' code but the roster
(``agents/shared/agent_roles.py``), and that only to check a setup.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from engine import pack as _pack

TOPOLOGIES = (7, 5, 3)
TEXT_SLOT = "dc_params_primer_text"
# The Database Handler only saves the session: it never designs.
NO_PRIMER_AGENTS = frozenset({"database_handler"})
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# A picture of assets/, by its file name.
_IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.png$")
_KEYS = ("image", "agents")

DEFAULT = {
    "image": "dc_params_primer.png",
    "agents": {
        7: ["user_input_inspector", "dc_input_creator", "dc_input_inspector",
            "dc_output_inspector"],
        5: ["user_input_inspector", "dc_input_creator", "dc_output_inspector"],
        3: ["design_engineer", "requirements_analyst"],
    },
}


class PrimerError(ValueError):
    """The ``primer`` section of pack.yaml is invalid."""


def _roster() -> dict[int, tuple[str, ...]]:
    from agents.shared.agent_roles import ROSTER
    return ROSTER


def problems_of(raw, roster: dict | None = None) -> list[str]:
    """Why *raw* -- the ``primer`` value of pack.yaml -- is not a primer."""
    roster = _roster() if roster is None else roster
    where = "pack.yaml primer"
    if not isinstance(raw, dict):
        return [f"{where}: must be a mapping with image and agents"]
    out = [f"{where}: {k!r} is not one of {', '.join(_KEYS)}" for k in raw if k not in _KEYS]
    image = raw.get("image")
    if image not in (None, "") and not (isinstance(image, str) and _IMAGE_RE.match(image)):
        out.append(f"{where}: image must be the name of a PNG file in assets/ (or empty), "
                   f"not {image!r}")
    agents = raw.get("agents")
    if agents is None:
        return out
    if not isinstance(agents, dict):
        return out + [f"{where}: agents must map each topology to a list of agents"]
    for topo, names in agents.items():
        if topo not in TOPOLOGIES:
            out.append(f"{where}: {topo!r} is not a topology ({', '.join(map(str, TOPOLOGIES))})")
            continue
        if names is None:
            continue
        if not isinstance(names, list):
            out.append(f"{where}: agents {topo} must be a list")
            continue
        seen = set()
        for name in names:
            if name in NO_PRIMER_AGENTS:
                out.append(f"{where}: agents {topo}: the {name} cannot get the primer "
                           "(it only saves the session)")
            elif name not in roster.get(topo, ()):
                out.append(f"{where}: agents {topo}: {name!r} is not an agent of the "
                           f"{topo}-agent topology")
            elif name in seen:
                out.append(f"{where}: agents {topo}: {name} is listed twice")
            seen.add(name)
    return out


def read(root: Path | None = None) -> dict:
    """``{"image": <file name in assets/> | None, "agents": {7: [...], 5:
    [...], 3: [...]}, "declared": <the setup has the section>}`` for the
    setup in *root* (default: the active one).  Raises PrimerError."""
    path = (root or _pack.pack_dir()) / "pack.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or "primer" not in data:
        return {"image": DEFAULT["image"],
                "agents": {t: list(a) for t, a in DEFAULT["agents"].items()}, "declared": False}
    raw = data["primer"]
    problems = problems_of(raw)
    if problems:
        raise PrimerError("\n".join(problems))
    agents = raw.get("agents") or {}
    return {"image": raw.get("image") or None,
            "agents": {t: list(agents.get(t) or []) for t in TOPOLOGIES},
            "declared": True}


def agents_for(topology: int, root: Path | None = None) -> list[str]:
    """The agents that get the primer in *topology* (an unregistered
    topology reads the 7-agent list, as the pack's text does)."""
    t = int(topology) if int(topology) in TOPOLOGIES else 7
    return read(root)["agents"][t]


def gets(agent: str, topology: int, root: Path | None = None) -> bool:
    return agent in agents_for(topology, root)


def image_path(root: Path | None = None) -> Path | None:
    """The primer's picture, or None: none named, the file missing, or not
    a PNG (Validate says which)."""
    name = read(root)["image"]
    if not name:
        return None
    path = (root or _pack.pack_dir()) / "assets" / name
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return None
    return path if head == PNG_SIGNATURE else None


def png_size(path: Path) -> tuple[int, int]:
    """(width, height) from the PNG's IHDR -- no imaging library needed."""
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != PNG_SIGNATURE or head[12:16] != b"IHDR":
        raise ValueError(f"{path} is not a PNG")
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def image_tokens(width: int, height: int) -> int:
    """A picture's tokens as Anthropic counts them (width x height / 750),
    the estimate the Context Pruner uses."""
    return (width * height + 749) // 750
