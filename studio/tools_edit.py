"""Editing a setup's tools (MAS-blueprint P6c): the server's side, without
the engine.

A tool is a folder ``tools/<name>/`` of the setup: its manifest ``tool.yaml``,
its code, and the texts it owns (``prompts/``, edited as text fields --
``studio/editing.py`` -- except its entry in the tool runner's numbered tool
list, ``prompts/tool_list_entry.md``, edited here with the same checks).
Here:

* **the manifest** -- changed from the form (:func:`studio.yaml_patch.patch`:
  only the changed values are rewritten, every comment stays) or as text;
* **the files** -- a text file saved as typed (its line endings kept), any
  file replaced or added by upload; nothing is run;
* **Undo** -- a file, or the whole tool, back as it was when the Studio
  opened (the OPENED copy of the setup, byte for byte);
* **Remove** -- the folder goes, once nothing names the tool any more.

Every change that could stop the engine loading the tools is checked first
by the engine's own check (``engine/pack_tools.py``), run on a throw-away
copy of the setup holding the change: the setup's own folder never holds a
manifest the engine refuses.  A Python file that does not compile is saved
with a warning (the engine imports a tool's code only when it is used).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import shutil
import tempfile
import threading
from pathlib import Path

import yaml

from studio import yaml_patch
from studio.editing import Conflict, EditError, check_text

TOOL_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PART_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")
SKIP = {"__pycache__", "node_modules"}
TEXT_MAX = 1024 * 1024
UPLOAD_MAX = 20 * 1024 * 1024
MANIFEST = "tool.yaml"
PROMPTS = "prompts"
# The tool's entry in the tool runner's list: tool text that is no $slot.
ENTRY_RE = re.compile(r"^prompts/tool_list_entry(\.t\d+)?\.md$")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def is_text(raw: bytes) -> bool:
    if len(raw) > TEXT_MAX or b"\x00" in raw:
        return False
    try:
        raw.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8").replace("\r\n", "\n")


def _eol(raw: bytes | None) -> str:
    return "\r\n" if raw and b"\r\n" in raw else "\n"


class ToolsEditor:
    """Changes to the tools of the setup in *pack_dir*; *opened_dir* is its
    copy as the Studio opened it; *check_tools(dir)* is the engine's check
    of the tools of a setup copy (``-> problems``).  One change at a time."""

    def __init__(self, pack_dir: Path, opened_dir: Path, check_tools, repo: Path | None = None):
        self.pack_dir, self.opened_dir, self.check_tools = pack_dir, opened_dir, check_tools
        self.repo = repo
        self._lock = threading.Lock()

    # -- files ---------------------------------------------------------------

    @staticmethod
    def tools(root: Path) -> list[str]:
        d = root / "tools"
        return sorted(p.name for p in d.iterdir() if (p / MANIFEST).is_file()) if d.is_dir() else []

    @staticmethod
    def files(folder: Path) -> dict[str, Path]:
        """The tool's files, by path inside its folder (no caches)."""
        if not folder.is_dir():
            return {}
        return {p.relative_to(folder).as_posix(): p for p in sorted(folder.rglob("*"))
                if p.is_file() and not (SKIP & set(p.relative_to(folder).parts))}

    def _tool(self, tool: str, opened_ok: bool = False) -> Path:
        if not isinstance(tool, str) or not TOOL_RE.match(tool):
            raise EditError(f"{tool!r} is not a tool name.")
        folder = self.pack_dir / "tools" / tool
        if not (folder / MANIFEST).is_file() and not (
                opened_ok and (self.opened_dir / "tools" / tool / MANIFEST).is_file()):
            raise EditError(f"The setup has no tool {tool!r}.")
        return folder

    @staticmethod
    def _rel(rel: str) -> str:
        parts = str(rel).replace("\\", "/").split("/")
        if not rel or any(not PART_RE.match(p) for p in parts) or (SKIP & set(parts)):
            raise EditError(f"{rel!r} is not a file name the Studio can write "
                            "(letters, digits, . _ -, folders with /).")
        return "/".join(parts)

    def _manifest_of(self, root: Path, tool: str):
        f = root / "tools" / tool / MANIFEST
        if not f.is_file():
            return None, None
        try:
            return yaml.safe_load(_decode(f.read_bytes())), None
        except yaml.YAMLError as exc:
            return None, str(exc)

    # -- what the page reads -------------------------------------------------

    def state(self, data: dict) -> dict:
        out = {}
        now, then = self.tools(self.pack_dir), self.tools(self.opened_dir)
        for tool in now:
            folder, ofolder = self.pack_dir / "tools" / tool, self.opened_dir / "tools" / tool
            files, ofiles = self.files(folder), self.files(ofolder)
            listing = []
            for rel, p in files.items():
                raw = p.read_bytes()
                o = ofiles.get(rel)
                listing.append({"path": rel, "size": len(raw), "text": is_text(raw), "sha": sha(raw),
                                "prompts": rel.split("/")[0] == PROMPTS and not ENTRY_RE.match(rel),
                                "entry": bool(ENTRY_RE.match(rel)),
                                "added": o is None, "changed": o is None or o.read_bytes() != raw})
            manifest, error = self._manifest_of(self.pack_dir, tool)
            omanifest, _ = self._manifest_of(self.opened_dir, tool)
            out[tool] = {
                "manifest": manifest, "manifest_error": error, "opened_manifest": omanifest,
                "sha": sha((folder / MANIFEST).read_bytes()), "files": listing,
                "gone_files": sorted(set(ofiles) - set(files)),
                "opened": tool in then,
                "changed": tool not in then or any(f["changed"] for f in listing)
                           or bool(set(ofiles) - set(files)),
            }
        return {"tools": out, "removed": [t for t in then if t not in now]}

    def changed(self) -> list[str]:
        """The tools' files (not their texts: those are text fields) that
        differ from the setup as opened."""
        out = []
        for tool in sorted(set(self.tools(self.pack_dir)) | set(self.tools(self.opened_dir))):
            a = self.files(self.pack_dir / "tools" / tool)
            b = self.files(self.opened_dir / "tools" / tool)
            for rel in sorted(set(a) | set(b)):
                if rel.split("/")[0] == PROMPTS and not ENTRY_RE.match(rel):
                    continue
                if rel not in a or rel not in b or a[rel].read_bytes() != b[rel].read_bytes():
                    out.append(f"tools/{tool}/{rel}")
        return out

    def read_file(self, data: dict, tool: str, rel: str) -> dict:
        folder = self._tool(tool)
        rel = self._rel(rel)
        p = folder / rel
        if not p.is_file():
            raise EditError(f"{tool}/{rel} does not exist.")
        raw = p.read_bytes()
        if not is_text(raw):
            return {"text": None, "sha": sha(raw), "size": len(raw), "warnings": []}
        return {"text": _decode(raw), "sha": sha(raw), "size": len(raw),
                "eol": "CRLF" if b"\r\n" in raw else "LF", "warnings": []}

    # -- checks --------------------------------------------------------------

    def _check(self, change) -> list[str]:
        """The engine's check of the tools of a throw-away copy of the setup
        with *change(copy_dir)* applied."""
        tmp = Path(tempfile.mkdtemp(prefix="studio_toolcheck_"))
        try:
            copy = tmp / self.pack_dir.name
            shutil.copytree(self.pack_dir, copy,
                            ignore=shutil.ignore_patterns("__pycache__", "node_modules", "assets"))
            change(copy)
            return list(self.check_tools(copy))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _write(self, path: Path, opened: Path | None, text: str | None = None,
               raw: bytes | None = None) -> None:
        """*text* (LF, written in the file's line endings -- the opened bytes
        when it is the opened text) or *raw* bytes."""
        if text is not None:
            if opened is not None and opened.is_file() and is_text(opened.read_bytes()) \
                    and _decode(opened.read_bytes()) == text:
                raw = opened.read_bytes()
            else:
                old = path.read_bytes() if path.is_file() else (
                    opened.read_bytes() if opened is not None and opened.is_file() else None)
                raw = text.replace("\n", _eol(old)).encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_bytes() != raw:
            path.write_bytes(raw)

    @staticmethod
    def _compile_warning(rel: str, text: str) -> list[str]:
        if not rel.endswith(".py"):
            return []
        try:
            compile(text, rel, "exec")
            return []
        except SyntaxError as exc:
            return [f"{rel} does not compile (line {exc.lineno}: {exc.msg}): the engine cannot "
                    "load this tool until it does."]

    # -- the manifest --------------------------------------------------------

    def save_manifest(self, data: dict, tool: str, desired, base: str) -> dict:
        """The manifest with the form's values (*desired*: the whole
        manifest), written into the file's own layout."""
        folder = self._tool(tool)
        with self._lock:
            path = folder / MANIFEST
            raw = path.read_bytes()
            if base != sha(raw):
                raise Conflict(f"{tool}/tool.yaml changed on disk since the page read it.  "
                               "Reload the page.")
            if not isinstance(desired, dict):
                raise EditError("The page sent no manifest.")
            opened = self.opened_dir / "tools" / tool / MANIFEST
            otext = _decode(opened.read_bytes()) if opened.is_file() else None
            try:
                text = yaml_patch.patch(_decode(raw), desired, otext)
            except yaml_patch.PatchError as exc:
                raise EditError(f"This change does not fit the manifest's layout ({exc}).  "
                                "Make it in the tool.yaml tab.") from None
            if text == _decode(raw):
                return {"sha": base, "warnings": []}
            problems = self._check(lambda d: self._write(d / "tools" / tool / MANIFEST, None, text))
            if problems:
                raise EditError("The manifest cannot be saved.", problems)
            self._write(path, opened, text)
            return {"sha": sha(path.read_bytes()), "warnings": []}

    # -- files ---------------------------------------------------------------

    def save_file(self, data: dict, tool: str, rel: str, text, base: str) -> dict:
        """A text file of the tool, as typed (``tool.yaml`` checked first)."""
        folder = self._tool(tool)
        rel = self._rel(rel)
        if rel.split("/")[0] == PROMPTS and not ENTRY_RE.match(rel):
            raise EditError("The tool's texts are edited as text fields (its Prompt texts tab).")
        text = str(text).replace("\r\n", "\n")
        if ENTRY_RE.match(rel):
            # prompt text: the text fields' own checks
            problems = check_text("block", text.rstrip(), set(data.get("text_names") or []),
                                  set(data.get("text_flags") or []), set(data.get("pack_tools") or []))
            if problems:
                raise EditError("The text cannot be saved.", problems)
        with self._lock:
            path = folder / rel
            if not path.is_file():
                raise EditError(f"{tool}/{rel} does not exist: add it by upload.")
            raw = path.read_bytes()
            if base != sha(raw):
                raise Conflict(f"{tool}/{rel} changed on disk since the page read it.  "
                               "Reload the page.")
            if not is_text(raw):
                raise EditError(f"{tool}/{rel} is not a text file: replace it by upload.")
            opened = self.opened_dir / "tools" / tool / rel
            if rel == MANIFEST:
                problems = self._check(lambda d: self._write(d / "tools" / tool / rel, None, text))
                if problems:
                    raise EditError("The manifest cannot be saved.", problems)
            self._write(path, opened, text)
            return {"sha": sha(path.read_bytes()), "warnings": self._compile_warning(rel, text)}

    def upload_file(self, data: dict, tool: str, rel: str, b64: str, base=None) -> dict:
        """A file of the tool replaced (*base*: the sha the page read) or
        added (*base* None)."""
        folder = self._tool(tool)
        rel = self._rel(rel)
        if rel.split("/")[0] == PROMPTS:
            raise EditError("The tool's texts are edited as text fields (its Prompt texts tab).")
        try:
            raw = base64.b64decode(str(b64), validate=True)
        except (binascii.Error, ValueError):
            raise EditError("The file did not arrive whole.") from None
        if len(raw) > UPLOAD_MAX:
            raise EditError(f"The file is {len(raw) / 1048576:.1f} MB; the limit is 20 MB.")
        with self._lock:
            path = folder / rel
            if path.is_file():
                if base != sha(path.read_bytes()):
                    raise Conflict(f"{tool}/{rel} exists or changed since the page read it: "
                                   "reload the page.")
            elif base is not None:
                raise Conflict(f"{tool}/{rel} is gone since the page read it: reload the page.")
            if rel == MANIFEST:
                problems = self._check(lambda d: self._write(d / "tools" / tool / rel, None, raw=raw))
                if problems:
                    raise EditError("The manifest cannot be saved.", problems)
            self._write(path, None, raw=raw)
            warnings = self._compile_warning(rel, raw.decode("utf-8")) if is_text(raw) else []
            return {"sha": sha(raw), "warnings": warnings}

    def undo_file(self, data: dict, tool: str, rel: str) -> dict:
        """A file back as it was when the Studio opened (an added one goes)."""
        folder = self._tool(tool, opened_ok=True)
        rel = self._rel(rel)
        opened = self.opened_dir / "tools" / tool / rel
        with self._lock:
            path = folder / rel
            if rel == MANIFEST:
                problems = self._check(lambda d: self._restore_file(d / "tools" / tool / rel, opened))
                if problems:
                    raise EditError("The opened manifest does not fit the tools as they are now: "
                                    "undo the other tools first, or use the tool's Undo.", problems)
            self._restore_file(path, opened)
            return {"warnings": []}

    @staticmethod
    def _restore_file(path: Path, opened: Path) -> None:
        if opened.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = opened.read_bytes()
            if not path.is_file() or path.read_bytes() != raw:
                path.write_bytes(raw)
        elif path.is_file():
            path.unlink()
            for parent in path.parents:
                if parent.name == "tools" or any(parent.iterdir()):
                    break
                parent.rmdir()

    # -- the whole tool ------------------------------------------------------

    def _restore_tool(self, root: Path, tool: str) -> None:
        """*root*'s folder of *tool* made as it was when the Studio opened
        (gone, when the tool did not exist then)."""
        folder, ofolder = root / "tools" / tool, self.opened_dir / "tools" / tool
        if not ofolder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)
            return
        now, then = self.files(folder), self.files(ofolder)
        for rel in now:
            if rel not in then:
                self._restore_file(folder / rel, ofolder / rel)
        for rel, p in then.items():
            self._restore_file(folder / rel, p)

    def undo_tool(self, data: dict, tool: str) -> dict:
        """The whole tool back as it was when the Studio opened -- its
        manifest, code and texts; a removed tool comes back, an added one
        goes."""
        if not isinstance(tool, str) or not TOOL_RE.match(tool) or not (
                (self.pack_dir / "tools" / tool).is_dir() or (self.opened_dir / "tools" / tool).is_dir()):
            raise EditError(f"The setup has no tool {tool!r}, now or as opened.")
        with self._lock:
            problems = self._check(lambda d: self._restore_tool(d, tool))
            if problems:
                raise EditError("The tool as opened does not fit the other tools as they are now: "
                                "undo them first.", problems)
            self._restore_tool(self.pack_dir, tool)
            return {"warnings": []}

    def remove_preview(self, data: dict, tool: str) -> dict:
        """What removing *tool* would leave: what still names it (blockers),
        the texts that leave with it, the engine's check without it."""
        self._tool(tool)
        blockers, warnings = [], []
        for other in self.tools(self.pack_dir):
            if other == tool:
                continue
            m, _ = self._manifest_of(self.pack_dir, other)
            for s in (m or {}).get("settings") or []:
                if isinstance(s, dict) and s.get("type") == "tool" and s.get("default") == tool:
                    blockers.append(f"{other}: its setting “{s.get('label') or s.get('name')}” "
                                    f"chooses it (the default) — choose another tool there first.")
        try:
            pack = yaml.safe_load((self.pack_dir / "pack.yaml").read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            pack = {}
        if ((pack.get("downloads") or {}).get("geometry_tool")) == tool:
            blockers.append("pack.yaml: the Download buttons use it (downloads › geometry_tool) — "
                            "change that first.")
        if self.repo is not None:
            f = self.repo / "workflow_settings" / "tool_settings.json"
            try:
                overrides = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
            except (OSError, ValueError):
                overrides = {}
            named = sorted(f"{t}.{k}" for t, vals in overrides.items() if isinstance(vals, dict)
                           for k, v in vals.items() if v == tool)
            if named or tool in overrides:
                warnings.append("Workflow Settings on this computer still mention it ("
                                + ", ".join(named or [tool]) + "): change them there after removing it.")
        m, _ = self._manifest_of(self.pack_dir, tool)
        owned = list((m or {}).get("prompt_slots") or [])
        texts = [f"${s}" for s in owned]
        if (self.pack_dir / "tools" / tool / PROMPTS).is_dir() and \
                list((self.pack_dir / "tools" / tool / PROMPTS).glob("tool_list_entry*.md")):
            texts.append("its entry in the tool runner's tool list")
        flag = re.compile(rf"<<IF(?:NOT)?:tool:{re.escape(tool)}>>")
        marked = sorted({p.relative_to(self.pack_dir).as_posix() for p in self.pack_dir.rglob("*.md")
                         if "tools/" + tool + "/" not in p.relative_to(self.pack_dir).as_posix()
                         and flag.search(p.read_text(encoding="utf-8", errors="replace"))})
        if (m or {}).get("kind") == "generator" and not any(
                (self._manifest_of(self.pack_dir, o)[0] or {}).get("kind") == "generator"
                for o in self.tools(self.pack_dir) if o != tool):
            warnings.append("It is the setup's only generator: without one the agents cannot "
                            "build a design.")
        problems = [] if blockers else self._check(
            lambda d: shutil.rmtree(d / "tools" / tool, ignore_errors=True))
        return {"blockers": blockers, "warnings": warnings, "texts": texts, "marked": marked,
                "problems": problems}

    def remove_tool(self, data: dict, tool: str) -> dict:
        with self._lock:
            pv = self.remove_preview(data, tool)
            if pv["blockers"] or pv["problems"]:
                raise EditError(f"{tool} cannot be removed yet.", pv["blockers"] + pv["problems"])
            shutil.rmtree(self.pack_dir / "tools" / tool)
            return {"warnings": pv["warnings"]}
