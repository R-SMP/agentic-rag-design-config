"""The design-configurator pack and the slot registry.

Everything specific to one design configurator lives in ONE folder, the
pack: ``dc_pack/`` unless ``DC_PACK_DIR`` names another (``config.py``).  The
engine reads it on every session build and never writes into it.

    dc_pack/
      parameters.json        the parameters: names, types, ranges, groups
                             (engine/parameters.py)
      assets/                images (the parameter primer)
      fragments/dc/          text about the configurator
      fragments/tools/       text about its tools that no one tool owns
      tools/<tool>/prompts/  the text a tool owns (its tool.yaml lists the
                             slots under ``prompt_slots``), plus its entry
                             in the tool runner's numbered tool list
                             (``tool_list_entry.md``)

The slot registry, ``engine/slot_registry.yaml``, lists every ``$slot`` the
engine offers and how to read it.  It belongs to the engine; a pack only
supplies the text.  A slot marked ``filled_by: tool`` is text about one of
the pack's tools: the tool that claims it holds its files, and with no tool
claiming it -- the tool was removed -- it reads as empty.

Fragment files in ``dc_pack/fragments/<folder>/`` (or a tool's ``prompts/``).
Which of them exist IS the link state -- the Studio's link icon -- and is
stored nowhere else:

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

import os
import re
import time
from functools import lru_cache
from pathlib import Path

import yaml

import config

ENGINE_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = ENGINE_DIR / "slot_registry.yaml"
REFERENCE_TOPOLOGY = 7
FOLDERS = ("dc", "tools")
TOOL_PROMPTS = "prompts"            # dc_pack/tools/<tool>/prompts/
TOOL_LIST_ENTRY = "tool_list_entry"  # its entry in the tool runner's list

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


def tools_dir() -> Path:
    return pack_dir() / "tools"


def tool_prompts_dir(tool: str) -> Path:
    return tools_dir() / tool / TOOL_PROMPTS


# ---------------------------------------------------------------------------
# Kept while unchanged
# ---------------------------------------------------------------------------
# A prompt build asks for the tools' manifests and for "which tool owns this
# text" hundreds of times.  What is read from the tools' files is therefore
# kept, together with the STAMP of those files -- each one's size and
# modification time (a folder's moves when a file in it is added, removed
# or renamed) -- and read again as soon as a stamp differs.  File times are
# coarse (a few milliseconds), so an edit made in the same instant as a
# read could leave its stamp unchanged: a value read while one of its
# stamps was younger than SETTLE_NS is used but not kept (git's rule for
# "racy" files).

SETTLE_NS = 2_000_000_000


def stamp(path: Path) -> tuple[int, int] | None:
    """(size, modification time in ns) of a file or folder; None if absent."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns)


def settled(key: tuple) -> bool:
    """True when every stamp in *key* is old enough that a change made
    since would have moved it (see SETTLE_NS)."""
    limit = time.time_ns() - SETTLE_NS
    return all(part[1] < limit for part in key
               if isinstance(part, tuple) and len(part) == 2
               and all(isinstance(x, int) for x in part))


_folders_cache: dict[tuple, list[str]] = {}


def tool_folders() -> list[str]:
    """The names of the folders in ``tools/``, sorted.  Listed again when
    the tools folder changes (a folder added, removed or renamed)."""
    root = tools_dir()
    key = (str(root), stamp(root))
    names = _folders_cache.get(key)
    if names is None:
        # Sorted as paths, as the folders were before (case-insensitive on
        # Windows).
        names = ([p.name for p in sorted(Path(e.path) for e in os.scandir(root) if e.is_dir())]
                 if root.is_dir() else [])
        _folders_cache.clear()
        if settled(key):
            _folders_cache[key] = names
    return list(names)


def tools_stamp(prompts: bool = True) -> tuple:
    """The stamp of what the tools' manifests are read from: the tools
    folder, each tool's ``tool.yaml`` and -- unless *prompts* is False --
    its ``prompts/`` folder.  It changes when a tool is added, removed or
    renamed, a ``tool.yaml`` is edited, or a file comes or goes in a
    ``prompts/`` folder."""
    root = tools_dir()
    parts: list = [str(root), stamp(root)]
    for name in tool_folders():
        parts += [name, stamp(root / name / "tool.yaml")]
        if prompts:
            parts.append(stamp(root / name / TOOL_PROMPTS))
    return tuple(parts)


_claims_cache: dict[tuple, dict[str, str]] = {}


def tool_claims() -> dict[str, str]:
    """slot -> the tool whose folder holds its text (each ``tool.yaml``'s
    ``prompt_slots``).  Kept while the tools folder and every
    ``tool.yaml`` are unchanged (:func:`tools_stamp`); a slot two tools
    claim goes to the first here and is reported by
    ``engine/pack_tools.manifests()``."""
    key = tools_stamp(prompts=False)
    claims = _claims_cache.get(key)
    if claims is None:
        claims = {}
        root = tools_dir()
        for name in tool_folders():
            f = root / name / "tool.yaml"
            if not f.is_file():
                continue
            m = yaml.safe_load(f.read_text(encoding="utf-8"))
            listed = m.get("prompt_slots") if isinstance(m, dict) else None
            for slot in listed if isinstance(listed, list) else []:
                claims.setdefault(str(slot), name)
        _claims_cache.clear()
        if settled(key):
            _claims_cache[key] = claims
    return claims


def text_dirs() -> list[Path]:
    """Every folder that holds slot text: ``fragments/<folder>/`` and each
    tool's ``prompts/``."""
    dirs = [fragments_dir() / f for f in FOLDERS]
    dirs += [tools_dir() / name / TOOL_PROMPTS for name in tool_folders()]
    return [d for d in dirs if d.is_dir()]


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
    tool = tool_claims().get(slot)
    if tool is not None:
        return tool_prompts_dir(tool)
    return fragments_dir() / slot_spec(slot)["folder"]


def unclaimed_tool_slot(slot: str) -> bool:
    """True for a ``filled_by: tool`` slot no tool of the pack fills: it
    reads as empty."""
    return (slot_spec(slot).get("filled_by") == "tool"
            and slot not in tool_claims())


def agent_copy_path(slot: str, topology: int, agent: str) -> Path | None:
    """*agent*'s own copy of *slot* in *topology*, or None if it has none."""
    if unclaimed_tool_slot(slot):
        return None
    return _first(_folder(slot), _candidates(f"{slot}@{agent}", topology))


def shared_path(slot: str, topology: int) -> Path | None:
    """The text of *slot* every agent without its own copy gets."""
    if unclaimed_tool_slot(slot):
        return None
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
        if spec.get("missing") == "empty" or unclaimed_tool_slot(slot):
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
    for d in text_dirs():
        for pattern in (f"*@{agent}.md", f"*@{agent}.t*.md"):
            found.update(slot_of_file(p.name) for p in d.glob(pattern))
    out: dict[str, str] = {}
    for slot in sorted(found):
        path = agent_copy_path(slot, topology, agent)
        if path is not None:
            out[slot] = _clean(slot_spec(slot), path.read_text(encoding="utf-8"))
    return out


def fragment_files() -> list[Path]:
    """Every slot file in the pack: ``fragments/<folder>/`` and each tool's
    ``prompts/`` (its tool-list entry is not a slot: see
    :func:`tool_list_entry_files`)."""
    out: list[Path] = []
    for d in text_dirs():
        out.extend(p for p in sorted(d.glob("*.md"))
                   if slot_of_file(p.name) != TOOL_LIST_ENTRY)
    return out


def tool_list_entry_path(tool: str, topology: int) -> Path | None:
    """*tool*'s entry in the tool runner's numbered tool list, for
    *topology* (same lookup as a slot's shared text)."""
    return _first(tool_prompts_dir(tool), _candidates(TOOL_LIST_ENTRY, topology))


def tool_list_entry_files() -> list[Path]:
    """Every tool's ``tool_list_entry*.md``."""
    root = tools_dir()
    return sorted(root.glob(f"*/{TOOL_PROMPTS}/{TOOL_LIST_ENTRY}*.md")) if root.is_dir() else []
