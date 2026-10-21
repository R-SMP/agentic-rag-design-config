"""The Studio's Primer page: the primer's picture and who gets it.

The primer (``engine/primer.py``) is one picture and its text, sent to the
agents the setup names with every call.  Its text is a text field like any
other (``studio/editing.py``); this module writes the rest, in the setup's
own files:

* ``pack.yaml``'s ``primer`` section -- ``image`` and, per topology, the
  ``agents`` that get it.  Only that block is rewritten, in one layout; a
  setup made before the section existed gets it appended, with its comment.
* the picture in ``assets/``: a PNG, JPEG or WebP is stored as a PNG (a PNG
  as it came).

Undo puts the agents, or the picture, back as the Studio opened them: the
block and the file byte for byte when everything is back.  Like
``studio/params_edit.py`` this process never imports the engine: the
agents a topology has come from the page's data (``data["roles"]``).
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import re
import threading
from pathlib import Path

import yaml

from studio.editing import Conflict, EditError
from studio.params_edit import eol_of, sha

TOPOLOGIES = (7, 5, 3)
NO_PRIMER_AGENTS = ("database_handler",)
DEFAULT_IMAGE = "dc_params_primer.png"
# A setup made before the section existed: what engine/primer.py reads then.
DEFAULT = {"image": DEFAULT_IMAGE, "agents": {
    7: ["user_input_inspector", "dc_input_creator", "dc_input_inspector", "dc_output_inspector"],
    5: ["user_input_inspector", "dc_input_creator", "dc_output_inspector"],
    3: ["design_engineer", "requirements_analyst"]}}
PICTURE_MAX = 10 * 1024 * 1024          # the file as it comes
PIXELS_MAX = 40_000_000                 # width x height, before it is opened
FORMATS = {"PNG": "PNG", "JPEG": "JPEG", "WEBP": "WebP"}
# The size a model provider takes a picture at as it is: Anthropic shrinks a
# longer side over 1568 px, or more than about 1.15 million pixels.
PROVIDER_EDGE, PROVIDER_PIXELS = 1568, 1_150_000

COMMENT = """# The primer: one picture and its text ($dc_params_primer_text -- an agent
# may have its own copy), sent to the agents below with every call, between
# their system prompt and the conversation (agents/shared/dc_primer.py).
#
#   image   a PNG in assets/; empty: the text alone
#   agents  per topology, the agents that get it (any but the Database
#           Handler); an empty list: none
#
# Workflow Settings > DC_PARAMS_PRIMER_ENABLED switches it off for every
# agent (a text-only model cannot take the picture).  See engine/primer.py.
"""

_HEAD_RE = re.compile(r"^primer:\s*(#.*)?$")


def _span(lines: list[str]) -> tuple[int, int] | None:
    """(first, end) of the ``primer`` block's own lines: its header and its
    indented lines, not the blank lines after them."""
    for i, ln in enumerate(lines):
        if _HEAD_RE.match(ln):
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j][:1].isspace()):
                j += 1
            while j > i + 1 and not lines[j - 1].strip():
                j -= 1
            return i, j
    return None


def section_of(text: str | None) -> dict | None:
    """The ``primer`` section of pack.yaml *text*, as ``{"image", "agents"}``
    with every topology; None when the setup has none."""
    data = yaml.safe_load(text or "") or {}
    if not isinstance(data, dict) or "primer" not in data:
        return None
    raw = data["primer"] if isinstance(data["primer"], dict) else {}
    agents = raw.get("agents") if isinstance(raw.get("agents"), dict) else {}
    return {"image": raw.get("image") or None,
            "agents": {t: list(agents.get(t) or []) for t in TOPOLOGIES}}


def effective(text: str | None) -> dict:
    """What the engine reads: the section, or :data:`DEFAULT`."""
    sec = section_of(text)
    return sec if sec is not None else {"image": DEFAULT["image"],
                                        "agents": {t: list(a) for t, a in DEFAULT["agents"].items()}}


def block(sec: dict) -> list[str]:
    """The ``primer`` block's lines, in its one layout."""
    out = ["primer:", "  image:" + (" " + sec["image"] if sec["image"] else ""), "  agents:"]
    out += [f"    {t}: [{', '.join(sec['agents'][t])}]" for t in TOPOLOGIES]
    return out


def write_section(text: str, sec: dict | None, opened_text: str | None) -> str:
    """pack.yaml *text* (LF) with its ``primer`` section *sec* (None: none).
    A section as it was when the Studio opened goes back with its opened
    lines; a section the setup did not have when it opened goes away with
    the comment this module wrote above it."""
    lines = text.split("\n")
    span = _span(lines)
    olines = (opened_text or "").split("\n")
    ospan = _span(olines) if opened_text is not None else None
    if sec is None:
        if span is None:
            return text
        first, end = span
        comment = COMMENT.rstrip("\n").split("\n")
        if lines[first - len(comment):first] == comment:
            first -= len(comment)
        while first > 0 and not lines[first - 1].strip() and (end >= len(lines) or not lines[end].strip()):
            first -= 1
        return "\n".join(lines[:first] + lines[end:])
    if ospan is not None and section_of(opened_text) == sec:
        new = olines[ospan[0]:ospan[1]]
    else:
        new = block(sec)
    if span is not None:
        lines[span[0]:span[1]] = new
        return "\n".join(lines)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines + [""] + COMMENT.rstrip("\n").split("\n") + new + [""])


def picture_info(path: Path) -> dict | None:
    """``{file, width, height, bytes, sha, tokens, large}`` of a PNG in
    assets/, ``{file, error}`` when it is not one, None when it is not
    there."""
    if not path.is_file():
        return None
    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        return {"file": path.name, "error": "not a PNG"}
    w, h = int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")
    return {"file": path.name, "width": w, "height": h, "bytes": len(raw), "sha": sha(raw),
            "tokens": (w * h + 749) // 750,
            "large": max(w, h) > PROVIDER_EDGE or w * h > PROVIDER_PIXELS}


def to_png(raw: bytes) -> tuple[bytes, str]:
    """A PNG, JPEG or WebP picture as PNG bytes (a PNG as it came), and the
    format it came in."""
    from PIL import Image
    if len(raw) > PICTURE_MAX:
        raise EditError(f"The picture is {len(raw) / 1048576:.1f} MB; the limit is "
                        f"{PICTURE_MAX // 1048576} MB.")
    try:
        with Image.open(io.BytesIO(raw)) as im:
            fmt = im.format
            if fmt not in FORMATS:
                raise EditError(f"A {fmt or 'file of this kind'} cannot be the primer's picture: "
                                "use a PNG, JPEG or WebP.")
            if im.width * im.height > PIXELS_MAX:
                raise EditError(f"The picture is {im.width} x {im.height} pixels: make it smaller "
                                "first (a model sees at most about 1568 px a side).")
            if fmt == "PNG":
                return raw, fmt
            im.load()
            keep = "RGBA" if ("A" in im.getbands() or "transparency" in im.info) else "RGB"
            buf = io.BytesIO()
            im.convert(keep).save(buf, "PNG", optimize=True)
            return buf.getvalue(), fmt
    except EditError:
        raise
    except Exception:  # noqa: BLE001 -- PIL's many ways of saying "not a picture"
        raise EditError("This file is not a picture the Studio can read: use a PNG, JPEG or "
                        "WebP.") from None


class PrimerEditor:
    """Changes to the primer's picture and agents in the setup in
    *pack_dir*; *opened_dir* is its copy as the Studio opened it.  One
    change at a time."""

    def __init__(self, pack_dir: Path, opened_dir: Path):
        self.pack_dir, self.opened_dir = pack_dir, opened_dir
        self._lock = threading.Lock()

    @staticmethod
    def _text(path: Path) -> str | None:
        return path.read_bytes().decode("utf-8").replace("\r\n", "\n") if path.is_file() else None

    def _yaml(self) -> tuple[bytes, str, str | None]:
        raw = (self.pack_dir / "pack.yaml").read_bytes()
        return raw, raw.decode("utf-8").replace("\r\n", "\n"), self._text(self.opened_dir / "pack.yaml")

    def _write_yaml(self, raw: bytes, text: str, otext: str | None) -> None:
        """*text* (LF) to pack.yaml: the opened bytes when it is the opened
        text, else in the file's own line endings."""
        opath = self.opened_dir / "pack.yaml"
        out = (opath.read_bytes() if otext is not None and text == otext
               else text.replace("\n", eol_of(raw)).encode("utf-8"))
        if out != raw:
            (self.pack_dir / "pack.yaml").write_bytes(out)

    def _check(self, base) -> tuple[bytes, str, str | None]:
        raw, text, otext = self._yaml()
        if base != sha(raw):
            raise Conflict("pack.yaml changed on disk since the page read it.  Reload the page.")
        return raw, text, otext

    def _save(self, raw: bytes, text: str, otext: str | None, sec: dict | None) -> None:
        # back to no section at all when the setup had none and this is
        # what the engine read then
        if (sec is not None and otext is not None and section_of(otext) is None
                and sec == effective(otext)):
            sec = None
        out = write_section(text, sec, otext)
        back = yaml.safe_load(out) or {}
        if (sec is None and "primer" in back) or (sec is not None and section_of(out) != sec):
            raise EditError("pack.yaml's primer section is not in a layout the Studio can change: "
                            "edit it by hand.")
        self._write_yaml(raw, out, otext)

    # -- what the page reads -------------------------------------------------

    def state(self, data: dict) -> dict:
        """The primer as the Studio opened it, pack.yaml's hash, and the
        picture's (the page's address for it changes with it)."""
        raw, text, otext = self._yaml()
        cur, then = effective(text), effective(otext)
        pic = picture_info(self.pack_dir / "assets" / cur["image"]) if cur["image"] else None
        opic = picture_info(self.opened_dir / "assets" / then["image"]) if then["image"] else None
        return {"pack_yaml_sha": sha(raw),
                "opened": {"image": then["image"], "agents": {str(t): a for t, a in then["agents"].items()},
                           "picture_sha": (opic or {}).get("sha")},
                "picture": pic}

    def changed(self) -> list[str]:
        """The primer's picture when it is in the setup and as opened, under
        the same name, with other bytes (a picture added or removed is the
        parameter editor's ``assets/`` list)."""
        _raw, text, _otext = self._yaml()
        name = effective(text)["image"]
        if not name:
            return []
        a, b = self.pack_dir / "assets" / name, self.opened_dir / "assets" / name
        return [f"assets/{name}"] if a.is_file() and b.is_file() and a.read_bytes() != b.read_bytes() else []

    # -- the agents ----------------------------------------------------------

    def set_agent(self, data: dict, agent: str, topology, on, base: str) -> dict:
        """Give *agent* the primer in *topology*, or not (*on*)."""
        try:
            t = int(topology)
        except (TypeError, ValueError):
            t = None
        roster = [a for a in (data.get("roles") or {}).get("roster", {}).get(str(t), [])]
        if agent in NO_PRIMER_AGENTS:
            raise EditError(f"The {agent} cannot get the primer: it only saves the session.")
        if t not in TOPOLOGIES or agent not in roster:
            raise EditError(f"{agent} is not an agent of the {topology}-agent topology.")
        if not isinstance(on, bool):
            raise EditError("Say true or false.")
        with self._lock:
            raw, text, otext = self._check(base)
            sec = effective(text)
            has = set(sec["agents"][t]) | {agent} if on else set(sec["agents"][t]) - {agent}
            # in the roster's order, so a list reads the same however it was ticked
            sec["agents"][t] = [a for a in roster if a in has] + sorted(has - set(roster))
            self._save(raw, text, otext, sec)
            return {"pack_yaml_sha": sha((self.pack_dir / "pack.yaml").read_bytes()), "warnings": []}

    # -- the picture ---------------------------------------------------------

    def set_picture(self, data: dict, b64, filename=None, base: str = "") -> dict:
        """The primer's picture becomes the file sent (base64), as a PNG.  It
        replaces the picture the setup names, or -- when it names none --
        becomes ``assets/dc_params_primer.png``."""
        try:
            raw_pic = base64.b64decode(str(b64), validate=True)
        except (binascii.Error, ValueError):
            raise EditError("The picture did not arrive whole.") from None
        png, fmt = to_png(raw_pic)
        with self._lock:
            raw, text, otext = self._check(base)
            sec = effective(text)
            name = sec["image"] or DEFAULT_IMAGE
            path = self.pack_dir / "assets" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            # the opened bytes when it is the opened picture again
            opath = self.opened_dir / "assets" / name
            if opath.is_file() and opath.read_bytes() == png:
                png = opath.read_bytes()
            if not path.is_file() or path.read_bytes() != png:
                path.write_bytes(png)
            if sec["image"] != name:
                sec["image"] = name
                self._save(raw, text, otext, sec)
            info = picture_info(path)
            warnings = []
            if fmt != "PNG":
                warnings.append(f"Stored as a PNG ({fmt} sent).")
            if info and info.get("large"):
                warnings.append(f"It is {info['width']} x {info['height']} px: a model provider "
                                "shrinks it before the model sees it, and small labels may blur.  "
                                f"At most {PROVIDER_EDGE} px a side and about 1.15 million pixels "
                                "go through as they are.")
            return {"picture": info, "file": filename,
                    "pack_yaml_sha": sha((self.pack_dir / "pack.yaml").read_bytes()),
                    "warnings": warnings}

    def remove_picture(self, data: dict, base: str) -> dict:
        """The primer has no picture: its text alone.  The file goes, unless a
        group of the Parameters page shows it."""
        with self._lock:
            raw, text, otext = self._check(base)
            sec = effective(text)
            name = sec["image"]
            if not name:
                raise EditError("The primer has no picture.")
            sec["image"] = None
            self._save(raw, text, otext, sec)
            if name not in self._group_pictures():
                (self.pack_dir / "assets" / name).unlink(missing_ok=True)
            return {"pack_yaml_sha": sha((self.pack_dir / "pack.yaml").read_bytes()), "warnings": []}

    def _group_pictures(self) -> set[str]:
        try:
            spec = json.loads((self.pack_dir / "parameters.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return set()
        return {str(g.get("image", "")).rsplit("/", 1)[-1]
                for g in (spec or {}).get("groups", []) if isinstance(g, dict)}

    # -- Undo ----------------------------------------------------------------

    def undo(self, data: dict, part: str) -> dict:
        """The agents (*part* ``agents``) or the picture (``picture``) back as
        the Studio opened them."""
        if part not in ("agents", "picture"):
            raise EditError("Undo the agents or the picture.")
        with self._lock:
            raw, text, otext = self._yaml()
            cur, then = effective(text), effective(otext)
            if part == "agents":
                cur["agents"] = then["agents"]
            else:
                if cur["image"] and cur["image"] != then["image"] and \
                        cur["image"] not in self._group_pictures() and \
                        not (self.opened_dir / "assets" / cur["image"]).is_file():
                    (self.pack_dir / "assets" / cur["image"]).unlink(missing_ok=True)
                if then["image"]:
                    src = self.opened_dir / "assets" / then["image"]
                    dst = self.pack_dir / "assets" / then["image"]
                    if src.is_file():
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        if not dst.is_file() or dst.read_bytes() != src.read_bytes():
                            dst.write_bytes(src.read_bytes())
                cur["image"] = then["image"]
            self._save(raw, text, otext, cur)
            return {"pack_yaml_sha": sha((self.pack_dir / "pack.yaml").read_bytes()), "warnings": []}
