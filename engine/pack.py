"""The design-configurator pack and the slot registry.

Everything specific to one design configurator lives in ONE folder, the
pack: ``dc_pack/`` unless ``DC_PACK_DIR`` names another (``config.py``).  The
engine reads it on every session build and never writes into it.

    dc_pack/
      parameters.json        the parameters: names, types, ranges, groups
                             (engine/parameters.py)
      assets/                images (the parameter primer)
      fragments/dc/          text about the configurator
      fragments/tools/       text about its tools

The slot registry, ``engine/slot_registry.yaml``, lists every ``$slot`` the
engine offers and how to read it.  It belongs to the engine; a pack only
supplies the text.

Fragment files in ``dc_pack/fragments/<folder>/``.  Which of them exist IS
the link state -- the Studio's link icon -- and is stored nowhere else:

    <slot>.md                one text for every topology ("linked")
    <slot>.t<N>.md           topology N's own text ("unlinked")
    <slot>@<agent>.md        <agent>'s own copy, in every topology
    <slot>@<agent>.t<N>.md   <agent>'s own copy, in topology N

A lookup takes the most specific file that exists: the agent's own copy if
there is one (``.t<N>``, then the shared copy, then the 7-agent one), else
the slot's text (``.t<N>``, then the shared text, then the 7-agent text).
The 7-agent text is the reference the other topologies were forked from,
which is why a topology with no file of its own -- or an unregistered
topology -- reads it.

An EMPTY file is a decision, not an accident: it resolves to "" and ends the
search (``warnings_developer.md`` W42).  A slot with no file at all is an
error, except for a per-agent-only slot (``missing: empty``), which then
contributes nothing.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

import config

ENGINE_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = ENGINE_DIR / "slot_registry.yaml"
REFERENCE_TOPOLOGY = 7
FOLDERS = ("dc", "tools")

_TOPOLOGY_SUFFIX_RE = re.compile(r"\.t\d+$")


# ---------------------------------------------------------------------------
# Where things are
# ---------------------------------------------------------------------------

def pack_dir() -> Path:
    """The active pack.  Read per call, so a changed ``config.DC_PACK_DIR``
    takes effect on the next lookup."""
    return Path(config.DC_PACK_DIR)


def fragments_dir() -> Path:
    return pack_dir() / "fragments"


def asset_path(name: str) -> Path:
    return pack_dir() / "assets" / name


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def registry() -> dict:
    """slot -> spec, in file order.  Engine-owned and never edited at run
    time, so it is parsed once per process."""
    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return data["slots"]


def slot_spec(slot: str) -> dict:
    try:
        return registry()[slot]
    except KeyError:
        raise KeyError(f"${slot} is not in {REGISTRY_PATH.name}") from None


def slots(source: str | None = None, use: str | None = None) -> dict:
    """slot -> spec, filtered by ``source`` and by ``use`` (default prompt)."""
    return {
        name: spec for name, spec in registry().items()
        if (source is None or spec["source"] == source)
        and (use is None or spec.get("use", "prompt") == use)
    }


def slot_of_file(name: str) -> str:
    """``hard_constraints_dc@tool_caller.t5.md`` -> ``hard_constraints_dc``."""
    stem = name[:-3] if name.endswith(".md") else name
    return _TOPOLOGY_SUFFIX_RE.sub("", stem.split("@", 1)[0])


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _candidates(base: str, topology: int) -> list[str]:
    names = [f"{base}.t{topology}.md", f"{base}.md"]
    if topology != REFERENCE_TOPOLOGY:
        names.append(f"{base}.t{REFERENCE_TOPOLOGY}.md")
    return names


def _first(folder: Path, names: list[str]) -> Path | None:
    for name in names:
        path = folder / name
        if path.is_file():
            return path
    return None


def _folder(slot: str) -> Path:
    return fragments_dir() / slot_spec(slot)["folder"]


def agent_copy_path(slot: str, topology: int, agent: str) -> Path | None:
    """*agent*'s own copy of *slot* in *topology*, or None if it has none."""
    return _first(_folder(slot), _candidates(f"{slot}@{agent}", topology))


def shared_path(slot: str, topology: int) -> Path | None:
    """The text of *slot* every agent without its own copy gets."""
    return _first(_folder(slot), _candidates(slot, topology))


def fragment_path(slot: str, topology: int, agent: str | None = None) -> Path | None:
    """The file that fills *slot* for *agent* (or for everyone) in *topology*."""
    if agent:
        own = agent_copy_path(slot, topology, agent)
        if own is not None:
            return own
    return shared_path(slot, topology)


def _clean(spec: dict, text: str) -> str:
    text = text.rstrip()
    return text.strip() if spec.get("strip") == "both" else text


def read(slot: str, topology: int, agent: str | None = None) -> str:
    """The text that fills *slot*, trimmed the way its registry entry says."""
    spec = slot_spec(slot)
    path = fragment_path(slot, topology, agent)
    if path is None:
        if spec.get("missing") == "empty":
            return ""
        raise FileNotFoundError(
            f"no file for ${slot} (topology {topology}) in {_folder(slot)}")
    return _clean(spec, path.read_text(encoding="utf-8"))


def agent_copies(agent: str, topology: int) -> dict[str, str]:
    """slot -> text, for every pack slot *agent* owns a copy of in *topology*.

    Only the slots with a ``<slot>@<agent>...`` file are returned, so the
    caller can lay the result over the shared slot map.
    """
    found: set[str] = set()
    for folder in FOLDERS:
        d = fragments_dir() / folder
        if d.is_dir():
            for pattern in (f"*@{agent}.md", f"*@{agent}.t*.md"):
                found.update(slot_of_file(p.name) for p in d.glob(pattern))
    out: dict[str, str] = {}
    for slot in sorted(found):
        path = agent_copy_path(slot, topology, agent)
        if path is not None:
            out[slot] = _clean(slot_spec(slot), path.read_text(encoding="utf-8"))
    return out


def fragment_files() -> list[Path]:
    """Every fragment file in the pack."""
    out: list[Path] = []
    for folder in FOLDERS:
        d = fragments_dir() / folder
        if d.is_dir():
            out.extend(sorted(d.glob("*.md")))
    return out
