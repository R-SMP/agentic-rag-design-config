"""The design-configurator pack and the slot registry.

Everything specific to one design configurator lives in ONE folder, its
setup -- the pack: one folder per configurator in ``setups/``
(``engine/setups.py``), ``setups/propeller/`` unless ``DC_PACK_DIR`` names
another (``config.py``).  The engine reads it on every session build and
never writes into it.

    setups/<setup>/
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

Fragment files in ``setups/<setup>/fragments/<folder>/`` (or a tool's ``prompts/``).
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

import fnmatch
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
TOOL_PROMPTS = "prompts"            # setups/<setup>/tools/<tool>/prompts/
TOOL_LIST_ENTRY = "tool_list_entry"  # its entry in the tool runner's list

_TOPOLOGY_SUFFIX_RE = re.compile(r"\.t\d+$")

# The setup's format: ``pack_format`` in its pack.yaml.  An engine change
# that a setup must follow raises it; a setup in a newer format than this
# engine reads is refused (:func:`format_problem`).
PACK_FORMAT = 1


# ---------------------------------------------------------------------------
# Where things are
# ---------------------------------------------------------------------------

def pack_dir() -> Path:
    """The active pack.  Read per call, so a changed ``config.DC_PACK_DIR``
    takes effect on the next lookup."""
    return Path(config.DC_PACK_DIR)


def pack_format(root: Path | None = None) -> int | None:
    """``pack_format`` of the setup in *root* (default: the active one): 1
    for a setup made before the key existed, None when it is not a whole
    number from 1 up."""
    data = yaml.safe_load(((root or pack_dir()) / "pack.yaml").read_text(encoding="utf-8")) or {}
    v = data.get("pack_format", 1) if isinstance(data, dict) else None
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 1 else None


def format_problem(root: Path | None = None) -> str | None:
    """Why this engine cannot read the setup in *root*, or None."""
    v = pack_format(root)
    if v is None:
        return "pack.yaml: pack_format must be a whole number from 1 up"
    if v > PACK_FORMAT:
        return (f"pack.yaml: this setup is in format {v}, made by a newer engine; this engine "
                f"reads formats up to {PACK_FORMAT}: update the engine first")
    return None


def uses_database(root: Path | None = None) -> bool:
    """Whether the setup in *root* (default: the active one) may use the
    database and its file store (R2): ``database: true`` in its
    ``pack.yaml``.  A configurator without it runs with neither, whatever
    the deployment's ``DATABASE_URL`` and ``R2_*`` say -- the database's
    tables are one configurator's (MAS-blueprint setups)."""
    try:
        data = yaml.safe_load(((root or pack_dir()) / "pack.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return False
    return isinstance(data, dict) and data.get("database") is True


def read_in(root: Path, slot: str) -> str:
    """The shared text of the ``dc`` word *slot* (``app_title``,
    ``dc_name`` ...) in the setup at *root*, loaded or not -- the main
    menu's list of configurators; "" when it has none."""
    spec = slot_spec(slot)
    folder = root / "fragments" / spec["folder"]
    for name in _candidates(slot, REFERENCE_TOPOLOGY):
        if (folder / name).is_file():
            return _clean(spec, (folder / name).read_text(encoding="utf-8"))
    return ""


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
#
# A process that lives a few seconds and is answered for one state of the
# pack (the Studio's workers and build children) may call hold_stamps():
# from then on each stamp is read once and held for the life of the
# process.  The web app never does.

SETTLE_NS = 2_000_000_000
_held: dict[str, tuple[int, int] | None] | None = None


def hold_stamps() -> None:
    """Take the pack's files as unchanging for the rest of this process:
    each stamp is read once, then held.  For short-lived processes only
    (the Studio's): the files' TEXT is still read fresh, but a file added,
    removed or edited meanwhile is not noticed."""
    global _held
    if _held is None:
        _held = {}


def stamp(path: Path) -> tuple[int, int] | None:
    """(size, modification time in ns) of a file or folder; None if absent."""
    if _held is not None and str(path) in _held:
        return _held[str(path)]
    try:
        st = os.stat(path)
        out = (st.st_size, st.st_mtime_ns)
    except OSError:
        out = None
    if _held is not None:
        _held[str(path)] = out
    return out


def settled(key: tuple) -> bool:
    """True when every stamp in *key* is old enough that a change made
    since would have moved it (see SETTLE_NS) -- always, in a process that
    holds its stamps."""
    if _held is not None:
        return True
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


_names_cache: dict[str, tuple] = {}


def file_names(folder: Path) -> frozenset[str]:
    """The names of the files in *folder* (none if it does not exist).
    Kept while the folder's stamp is unchanged: adding, removing or
    renaming a file moves it; editing a file's text needs no new list."""
    st = stamp(folder)
    hit = _names_cache.get(str(folder))
    if hit is not None and hit[0] == st:
        return hit[1]
    names = (frozenset(e.name for e in os.scandir(folder) if e.is_file())
             if st is not None and os.path.isdir(folder) else frozenset())
    if settled((st,)):
        _names_cache[str(folder)] = (st, names)
    else:
        _names_cache.pop(str(folder), None)
    return names


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
    present = file_names(folder)
    for name in names:
        if name in present:
            return folder / name
    return None


def _folder(slot: str) -> Path:
    # Only tool text can live in a tool's folder: engine/pack_tools.py
    # refuses a pack whose tool lists any other slot.
    if slot_spec(slot).get("filled_by") == "tool":
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
            found.update(slot_of_file(n) for n in file_names(d)
                         if fnmatch.fnmatch(n, pattern))
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
