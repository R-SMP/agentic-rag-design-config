"""Editing a setup's text fields (MAS-blueprint P6a): the server's side.

A FIELD is one ``$slot`` of the pack -- its shared text -- or one agent's own
copy of it (``<slot>@<agent>``).  Its files sit in one folder of the setup
(``fragments/<folder>/``, or the ``prompts/`` folder of the tool that owns
the slot), and their names ARE its link state (``engine/pack.py``)::

    <name>.md          one text for every topology   (linked)
    <name>.t<N>.md     topology N's own text         (unlinked)

where ``<name>`` is ``<slot>`` or ``<slot>@<agent>``.  A topology with no
file of its own reads the 7-agent one (then, for an own copy, the shared
text) -- the engine's rule, which the Studio shows rather than re-derives.

Every change is checked first (:func:`check_text`); a file is written so it
keeps its own line endings and final newline, and a text put back to what it
was when the Studio opened is written back BYTE FOR BYTE: the OPENED copy of
the setup, taken when the server starts, holds those bytes, and Undo
restores a field from it.  A file that changed on disk since the page read
it is never overwritten (:class:`Conflict`).

Nothing here imports the engine: the Studio's data (``engine_view.py``'s
``static_data``) says which folder holds each field, which names and flags
a text may use, and which agents each topology builds.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

TOPOLOGIES = ("7", "5", "3")
_NAME_RE = re.compile(r"\$([a-z_][a-z0-9_]*)")
_TAG_OPEN_RE = re.compile(r"<<(?!/)([A-Za-z][A-Za-z0-9_]*(?::[a-z0-9_.]+)?)>>")
_TAG_CLOSE_RE = re.compile(r"<</([A-Za-z][A-Za-z0-9_]*(?::[a-z0-9_.]+)?)>>")
_FLAG_TOOL_RE = re.compile(r"^(?:tool:([a-z][a-z0-9_]*)|setting:([a-z][a-z0-9_]*)\.[a-z0-9_]+)$")


class EditError(ValueError):
    """A change the Studio refuses, with the reasons."""

    def __init__(self, message: str, problems: list[str] | None = None):
        super().__init__(message)
        self.problems = problems or []


class Conflict(EditError):
    """A file changed on disk since the page read it."""


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------

def check_text(kind: str, text: str, names: set[str], flags: set[str],
               tools: set[str]) -> list[str]:
    """What stops *text* from being saved in a field of *kind*: braces (they
    silently remove an agent's routing section, warnings_developer.md W45),
    a line break in a one-line field, a ``$name`` the engine does not know,
    an ``<<IF:...>>`` flag it does not know (a flag of a tool the setup lacks
    reads as off, as in the engine), a marker that is not closed."""
    problems = []
    if "{" in text or "}" in text:
        problems.append("It contains { or }: the engine would silently drop an agent's "
                        "routing section (W45).  Write the text without braces.")
    if kind in ("phrase", "word") and "\n" in text:
        problems.append("It is a one-line field: remove the line breaks.")
    unknown = sorted({n for n in _NAME_RE.findall(text) if n not in names})
    if unknown:
        problems.append("Unknown $name: " + ", ".join("$" + n for n in unknown) + ".")
    opens, closes = _TAG_OPEN_RE.findall(text), _TAG_CLOSE_RE.findall(text)
    if sorted(opens) != sorted(closes):
        problems.append("A <<marker>> is not closed by its <</marker>> (or the other way "
                        "round).")
    for tag in sorted(set(opens)):
        if tag.startswith(("IF:", "IFNOT:")):
            flag = tag.split(":", 1)[1]
            m = _FLAG_TOOL_RE.match(flag)
            if flag not in flags and not (m and (m.group(1) or m.group(2)) not in tools):
                problems.append(f"<<{tag}>> names an unknown flag.")
    return problems


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------

def field_name(slot: str, agent: str | None) -> str:
    return f"{slot}@{agent}" if agent else slot


def clean(strip: str, text: str) -> str:
    """The text as the engine reads it (``engine/pack.py`` ``_clean``)."""
    text = text.rstrip()
    return text.strip() if strip == "both" else text


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8").replace("\r\n", "\n")


def _eol(raw: bytes | None) -> bytes | None:
    if not raw:
        return None
    return b"\r\n" if b"\r\n" in raw else (b"\n" if b"\n" in raw else None)


def field_files(folder: Path, name: str) -> dict[str, Path]:
    """The files of field *name* in *folder*: ``{"md": path}`` (linked)
    and/or ``{"<N>": path}`` (topology N's own)."""
    out: dict[str, Path] = {}
    if not folder.is_dir():
        return out
    pat = re.compile(rf"^{re.escape(name)}(?:\.t(\d+))?\.md$")
    for p in folder.iterdir():
        m = pat.match(p.name)
        if m and p.is_file():
            out[m.group(1) or "md"] = p
    return out


class Editor:
    """Changes to the setup in *pack_dir*; *opened_dir* is its copy as the
    Studio opened it.  One change at a time."""

    def __init__(self, pack_dir: Path, opened_dir: Path):
        self.pack_dir = pack_dir
        self.opened_dir = opened_dir
        self._lock = threading.Lock()

    # -- the field ----------------------------------------------------------

    def _field(self, data: dict, slot: str, agent: str | None):
        spec = (data.get("slot_specs") or {}).get(slot)
        if spec is None:
            raise EditError(f"The setup has no text field {slot!r}.")
        if not spec.get("dir"):
            raise EditError(f"${slot} is text about a tool the setup does not have.")
        if agent is not None and agent not in self._agents(data):
            raise EditError(f"There is no agent {agent!r}.")
        rel = Path(spec["dir"])
        folder = (self.pack_dir / rel).resolve()
        if self.pack_dir.resolve() not in folder.parents:
            raise EditError(f"${slot}: its folder is outside the setup.")
        return spec, rel, folder, field_name(slot, agent)

    @staticmethod
    def _agents(data: dict) -> set[str]:
        return {a for t in data["roles"]["roster"].values() for a in t} | {"database_handler"}

    @staticmethod
    def _topologies_of(data: dict, agent: str | None) -> list[str]:
        """The topologies a field's per-topology files exist for: all three
        for a shared text, the ones that build the agent for an own copy."""
        if agent is None or agent == "database_handler":
            return list(TOPOLOGIES)
        return [n for n in TOPOLOGIES if agent in data["roles"]["roster"].get(n, [])]

    def _opened(self, rel: Path, path: Path) -> bytes | None:
        p = self.opened_dir / rel / path.name
        return p.read_bytes() if p.is_file() else None

    def _folder_eol(self, folder: Path) -> bytes:
        crlf = lf = 0
        for p in folder.glob("*.md") if folder.is_dir() else []:
            e = _eol(p.read_bytes())
            crlf += e == b"\r\n"
            lf += e == b"\n"
        return b"\r\n" if crlf > lf else b"\n"

    def _write(self, rel: Path, path: Path, text: str, strip: str, eol: bytes) -> None:
        """Write *text* (as the engine will read it) to *path*: the opened
        bytes when the text is what it was at opening, else the text with
        *eol* line endings and a final line ending (none when empty)."""
        opened = self._opened(rel, path)
        if opened is not None and clean(strip, _decode(opened)) == text:
            raw = opened
        else:
            raw = text.encode("utf-8").replace(b"\n", eol) + eol if text else b""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def _check(self, data: dict, spec: dict, texts: list[str]) -> None:
        names, flags = set(data["text_names"]), set(data["text_flags"])
        tools = set(data["pack_tools"])
        problems = []
        for t in texts:
            problems += [p for p in check_text(spec["kind"], t, names, flags, tools)
                         if p not in problems]
        if problems:
            raise EditError("The text cannot be saved.", problems)

    # -- the changes --------------------------------------------------------

    def save(self, data: dict, slot: str, agent: str | None,
             values: dict, base: dict) -> list[str]:
        """Write the field's texts: ``values = {"all": text}`` for a linked
        field, ``{"<N>": text, ...}`` for topology N's own files (a topology
        without one gets it).  *base* holds the texts the page showed for
        the same keys (None: no file); a file that differs from them is a
        :class:`Conflict`.  Returns warnings."""
        with self._lock:
            spec, rel, folder, name = self._field(data, slot, agent)
            if agent is None and spec.get("missing") == "empty":
                raise EditError(f"${slot} has no shared text: give an agent its own copy.")
            files = field_files(folder, name)
            linked = "md" in files or (not files and "all" in values)
            if set(values) - ({"all"} if linked else set(self._topologies_of(data, agent))):
                raise Conflict("This field's files changed since the page read them "
                               "(linked / unlinked).  Reload the page.")
            targets = {k: (folder / f"{name}.md" if k == "all" else folder / f"{name}.t{k}.md")
                       for k in values}
            stale = [k for k, p in targets.items()
                     if (clean(spec["strip"], _decode(p.read_bytes())) if p.is_file() else None)
                     != base.get(k)]
            if stale:
                raise Conflict("The file changed on disk since the page read it: "
                               + ", ".join(targets[k].name for k in stale)
                               + ".  Reload the page to see the current text.")
            texts = {k: clean(spec["strip"], str(v).replace("\r\n", "\n")) for k, v in values.items()}
            self._check(data, spec, list(texts.values()))
            eol = (next((e for e in (_eol(p.read_bytes()) for p in files.values()) if e), None)
                   or self._folder_eol(folder))
            for k, path in targets.items():
                self._write(rel, path, texts[k], spec["strip"], eol)
            return ["The text is empty: the agents that read this field get nothing here."
                    for t in texts.values() if not t][:1]

    def unlink(self, data: dict, slot: str, agent: str | None) -> None:
        """Give each topology its own file, holding the linked text: the
        prompts do not change."""
        with self._lock:
            spec, rel, folder, name = self._field(data, slot, agent)
            files = field_files(folder, name)
            if set(files) != {"md"}:
                raise Conflict("The field is not linked any more.  Reload the page.")
            raw = files["md"].read_bytes()
            for n in self._topologies_of(data, agent):
                path = folder / f"{name}.t{n}.md"
                opened = self._opened(rel, path)
                path.write_bytes(opened if opened is not None
                                 and _decode(opened) == _decode(raw) else raw)
            files["md"].unlink()

    def link(self, data: dict, slot: str, agent: str | None, keep: str) -> None:
        """One text for every topology: topology *keep*'s."""
        with self._lock:
            spec, rel, folder, name = self._field(data, slot, agent)
            files = field_files(folder, name)
            if "md" in files or keep not in files:
                raise Conflict("The field changed since the page read it.  Reload the page.")
            kept = files[keep].read_bytes()
            self._write(rel, folder / f"{name}.md", clean(spec["strip"], _decode(kept)),
                        spec["strip"], _eol(kept) or self._folder_eol(folder))
            for k, path in files.items():
                path.unlink()

    def own_copy(self, data: dict, slot: str, agent: str) -> None:
        """Give *agent* its own copy of *slot*, starting from the text it
        reads now (so no prompt changes); empty for a per-agent-only field."""
        if not agent:
            raise EditError("Name the agent that gets its own copy.")
        with self._lock:
            spec, rel, folder, name = self._field(data, slot, agent)
            if field_files(folder, name):
                raise Conflict(f"{agent} already has its own copy.  Reload the page.")
            shared = field_files(folder, slot)
            if spec.get("missing") == "empty" or not shared:
                (folder / f"{name}.md").write_bytes(b"")
                return
            if "md" in shared:
                (folder / f"{name}.md").write_bytes(shared["md"].read_bytes())
                return
            for n in self._topologies_of(data, agent):
                src = shared.get(n) or shared.get("7")
                if src is not None:
                    (folder / f"{name}.t{n}.md").write_bytes(src.read_bytes())

    def remove_copy(self, data: dict, slot: str, agent: str) -> None:
        """Remove *agent*'s own copy: it reads the shared text again."""
        if not agent:
            raise EditError("Name the agent whose own copy goes.")
        with self._lock:
            spec, rel, folder, name = self._field(data, slot, agent)
            files = field_files(folder, name)
            if not files:
                raise Conflict(f"{agent} has no own copy any more.  Reload the page.")
            for path in files.values():
                path.unlink()

    def undo(self, data: dict, slot: str, agent: str | None) -> None:
        """Put the field's files back as they were when the Studio opened."""
        with self._lock:
            spec, rel, folder, name = self._field(data, slot, agent)
            now = field_files(folder, name)
            then = field_files(self.opened_dir / rel, name)
            for key, path in now.items():
                if key not in then:
                    path.unlink()
            for key, path in then.items():
                target = folder / path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())

    def changed(self, data: dict) -> list[str]:
        """The fields (``slot`` / ``slot@agent``) whose files differ from
        the opened copy."""
        out = set()
        for slot, spec in (data.get("slot_specs") or {}).items():
            if not spec.get("dir"):
                continue
            rel = Path(spec["dir"])
            for root in (self.pack_dir, self.opened_dir):
                folder = root / rel
                if not folder.is_dir():
                    continue
                for p in folder.iterdir():
                    m = re.match(rf"^{re.escape(slot)}(@[a-z0-9_]+)?(?:\.t\d+)?\.md$", p.name)
                    if not m:
                        continue
                    other = (self.opened_dir if root == self.pack_dir else self.pack_dir) / rel / p.name
                    if not other.is_file() or other.read_bytes() != p.read_bytes():
                        out.add(slot + (m.group(1) or ""))
        return sorted(out)


def copy_setup(pack_dir: Path, to: Path) -> Path:
    """The OPENED copy: the setup's files as they are now (no caches)."""
    import shutil
    shutil.copytree(pack_dir, to, ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
    return to
