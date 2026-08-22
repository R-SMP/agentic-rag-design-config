"""Tools for inspecting and creating per-attempt folders.

An "attempt" folder is the canonical home for ONE design-generation
process: it may carry the DC inputs (``parameters.json``), the DC
output (``propeller_mesh.obj``), the analysis renders
(``render_*.png``), an optional ``description.txt``, and any further
metrics produced for the same set of inputs.  Folders are created
explicitly by the DC Input Creator (the default owner of attempt
creation; the Orchestrator may open one only as a fallback) — nothing
creates them implicitly.

Two tools are defined here:

- ``read_attempts(attempt_numbers=None)`` — the one attempts-inspection
  tool (it replaced the former ``list_attempts`` / ``read_attempt``
  pair, 2026-08-22).  With no argument it summarises every attempt
  folder (files present + ``description.txt`` content); given attempt
  numbers it adds each named attempt's full ``parameters.json``.  In
  both modes it lists each attempt's ``render_*.png`` and
  ``propeller_mesh.obj`` as absolute paths — mesh contents and image
  bytes are never returned inline.
- ``new_attempt(slug, description)`` — create a new, empty attempt
  folder and return its absolute path.

``parameters.json`` is append-only: its write tool refuses to overwrite
an existing file.  The merged geometry+renders tool
(``generate_and_render_propeller``) reuses an existing
``propeller_mesh.obj`` in place (never overwritten) and reuses the three
``render_*.png`` files when they already exist rather than refusing.
"""

import re
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool

from agents.shared.agent_activity import generic_tool
from config import ATTEMPTS_DIR

# Folder names produced by ``new_attempt`` have the form
# ``YYYYMMDD_HHMMSS_NNN_<slug>`` — the third group is the 1-based
# attempt number.
_ATTEMPT_RE = re.compile(r"^(\d{8})_(\d{6})_(\d+)_(.+)$")

# Mesh files and images are NEVER returned inline.  Even a moderate
# propeller mesh is ~1 MB of plain-text vertex / face data — ~300 k
# tokens — which blows past every chain agent's context window AND the
# Context Pruner's own per-call LLM input cap (see the 2026-05-31
# incident where a Receptionist read of ``propeller_mesh.obj`` made the
# Pruner's tier-2 LLM call 429 with a "Request too large" error).
# ``read_attempts`` therefore lists the render / mesh files as absolute
# PATHS only, for the caller to hand to a path-taking tool
# (``visualize_3d_model``, ``view_images``, …).

_SLUG_SAFE_RE = re.compile(r"[^A-Za-z0-9_.\-]+")


def _list_attempt_folders() -> list[tuple[int, Path]]:
    """Return ``[(attempt_number, folder_path), ...]`` sorted by number."""
    if not ATTEMPTS_DIR.exists():
        return []
    out: list[tuple[int, Path]] = []
    for p in ATTEMPTS_DIR.iterdir():
        if not p.is_dir():
            continue
        m = _ATTEMPT_RE.match(p.name)
        if m:
            out.append((int(m.group(3)), p))
    out.sort(key=lambda x: x[0])
    return out


def attempt_number_for_path(path: Path) -> int | None:
    """Parse the attempt number from any file inside an attempt folder.

    Attempt folders are named ``YYYYMMDD_HHMMSS_NNN_<slug>``; any
    file directly inside one (``propeller_mesh.obj`` /
    ``render_*.png`` / ``description.txt`` / ``parameters.json``)
    reveals its NNN via the parent folder's name.

    Returns the 1-based attempt number (integer) when the parent
    folder name matches the canonical pattern, otherwise ``None``.
    Callers use ``f"{n:03d}"`` to render the zero-padded label
    that matches the folder slug — see :func:`attempt_label_for_path`.
    """
    if path is None:
        return None
    try:
        parent_name = path.parent.name
    except Exception:
        return None
    m = _ATTEMPT_RE.match(parent_name)
    if not m:
        return None
    try:
        return int(m.group(3))
    except (TypeError, ValueError):
        return None


def attempt_label_for_path(path: Path) -> str | None:
    """Return ``"Attempt NNN"`` (zero-padded to 3 digits) for a file
    inside an attempt folder, or ``None`` when the path is not under
    a canonical ``YYYYMMDD_HHMMSS_NNN_<slug>`` folder.

    Used by the web layer to caption render bubbles and the 3D
    viewer toolbar with the attempt the artefact belongs to.
    """
    n = attempt_number_for_path(path)
    if n is None:
        return None
    return f"Attempt {n:03d}"


def _next_attempt_number() -> int:
    """Return the next 1-based attempt number for a new folder."""
    items = _list_attempt_folders()
    if not items:
        return 1
    return items[-1][0] + 1


def _sanitise_slug(slug: str) -> str:
    """Strip a slug to filename-safe characters, fall back to 'attempt'."""
    if not isinstance(slug, str):
        return "attempt"
    cleaned = _SLUG_SAFE_RE.sub("_", slug.strip()).strip("_")
    if not cleaned:
        return "attempt"
    return cleaned[:60]


def _classify_files(folder: Path) -> tuple[list[str], dict[str, bool]]:
    """Return ``(file_names, role_presence)`` for an attempt folder."""
    try:
        names = sorted(f.name for f in folder.iterdir() if f.is_file())
    except OSError:
        return [], {
            "parameters": False, "mesh": False,
            "renders": False, "description": False,
        }
    flags = {
        "parameters": "parameters.json" in names,
        "mesh": "propeller_mesh.obj" in names,
        "renders": any(
            n.startswith("render_") and n.lower().endswith(
                (".png", ".jpg", ".jpeg")
            )
            for n in names
        ),
        "description": "description.txt" in names,
    }
    return names, flags


def _read_small_text(path: Path) -> str | None:
    """Content of a small text file, or None when absent/unreadable."""
    try:
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _indent_block(text: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _attempt_summary(n: int, folder: Path, detailed: bool) -> list[str]:
    """The per-attempt lines shared by both ``read_attempts`` modes."""
    names, flags = _classify_files(folder)
    present_roles = [
        label for label, ok in (
            ("parameters", flags["parameters"]),
            ("mesh", flags["mesh"]),
            ("renders", flags["renders"]),
            ("description", flags["description"]),
        ) if ok
    ]
    lines = [
        f"  Attempt {n}: {folder.name}",
        f"    Has: {', '.join(present_roles) if present_roles else '(empty)'}",
        f"    Files: {', '.join(names) if names else '(empty)'}",
    ]
    desc = _read_small_text(folder / "description.txt")
    if desc:
        if "\n" in desc:
            lines.append("    Description:")
            lines.append(_indent_block(desc, "      "))
        else:
            lines.append(f"    Description: {desc}")
    render_paths = sorted(
        p.resolve() for p in folder.iterdir()
        if p.is_file() and p.name.startswith("render_")
        and p.suffix.lower() in (".png", ".jpg", ".jpeg")
    ) if names else []
    if render_paths:
        lines.append("    Render paths:")
        lines += [f"      {p}" for p in render_paths]
    mesh = folder / "propeller_mesh.obj"
    if mesh.is_file():
        lines.append(f"    Mesh path: {mesh.resolve()}")
    if detailed:
        params = _read_small_text(folder / "parameters.json")
        if params is not None:
            lines.append("    parameters.json:")
            lines.append(_indent_block(params, "      "))
    return lines


@tool
@generic_tool("Read attempts")
def read_attempts(attempt_numbers: list[int] | None = None) -> str:
    """Inspect this session's attempt folders — contents and file paths.

    An attempt folder is the canonical container for one design-
    generation process: it may hold the DC inputs (``parameters.json``),
    the generated mesh (``propeller_mesh.obj``), the rendered analysis
    images (``render_*.png``), and an optional ``description.txt``.
    Folders may be partial — e.g. a folder with only parameters.json
    means no mesh was generated yet for that input set.

    Args:
      attempt_numbers: OPTIONAL list of 1-based attempt numbers.  Omit
        it to get a numbered summary of EVERY attempt — files present
        (``Has:`` line) plus each attempt's ``description.txt`` content.
        Pass numbers (e.g. ``[2, 5]``) to get the same summary for only
        those attempts, each with its full ``parameters.json`` content
        as well.  Attempt numbers only — never paths.

    In both modes each attempt's ``render_*.png`` (including
    ``render_blade_sections.png``) and ``propeller_mesh.obj`` are listed
    as ABSOLUTE PATHS, ready to hand to a tool that takes a path — mesh
    contents and image bytes are never returned inline.  Returns
    ``'No attempts created yet.'`` when no folder exists.
    """
    items = _list_attempt_folders()
    if not items:
        return "No attempts created yet."

    if attempt_numbers is None or attempt_numbers == []:
        selected = items
        detailed = False
        invalid: list[str] = []
    else:
        if isinstance(attempt_numbers, (int, str)):
            attempt_numbers = [attempt_numbers]
        if not isinstance(attempt_numbers, (list, tuple)):
            return (
                "Error: 'attempt_numbers' must be a list of integer "
                "attempt numbers (or omitted to list every attempt)."
            )
        wanted: list[int] = []
        invalid = []
        for raw in attempt_numbers:
            try:
                wanted.append(int(raw))
            except (TypeError, ValueError):
                invalid.append(f"{raw!r} is not an integer")
        by_n = dict(items)
        selected = []
        for n in wanted:
            if n in by_n:
                if (n, by_n[n]) not in selected:
                    selected.append((n, by_n[n]))
            else:
                invalid.append(f"no attempt numbered {n}")
        detailed = True
        if not selected:
            available = sorted({num for num, _ in items})
            return (
                f"Error: none of the requested attempt numbers exist "
                f"({'; '.join(invalid)}).  "
                f"Available attempt numbers: {available}."
            )

    lines = [
        f"{len(items)} attempt(s) under {ATTEMPTS_DIR.resolve()}"
        + ("" if not detailed else f"; showing {len(selected)}")
        + ":"
    ]
    for n, folder in selected:
        lines += _attempt_summary(n, folder, detailed)
    for msg in invalid:
        lines.append(f"  Ignored: {msg}.")
    return "\n".join(lines)


@tool
@generic_tool("Open new attempt")
def new_attempt(slug: str = "attempt", description: str = "") -> str:
    """Create a new, empty attempt folder for an upcoming design generation.

    An attempt folder is the canonical home for ONE design-generation
    process — it will hold parameters.json, propeller_mesh.obj, the
    render PNGs, and any other artifact produced for the same set of
    DC inputs.  Whoever creates the folder decides what (if anything)
    to record in the description.

    Args:
      slug:        short, filename-safe label that will appear in the
                   folder name after the timestamp + sequence number
                   (e.g. ``'4blades_thick_ring'``).  Falls back to
                   ``'attempt'`` when omitted or made of unsafe
                   characters.
      description: optional one-paragraph note explaining what this
                   attempt is for.  When non-empty it is written to
                   ``description.txt`` inside the new folder.

    Returns a confirmation that includes the folder's absolute path
    on success — copy that path verbatim into your hand-offs as
    ``Current attempt:`` so downstream agents target the same folder.
    """
    if not isinstance(slug, (str, type(None))):
        return "Error: 'slug' must be a string or omitted."
    if not isinstance(description, (str, type(None))):
        return "Error: 'description' must be a string or omitted."

    safe_slug = _sanitise_slug(slug or "attempt")

    try:
        ATTEMPTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        attempt_n = _next_attempt_number()
        dest = ATTEMPTS_DIR / f"{timestamp}_{attempt_n:03d}_{safe_slug}"
        dest.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        return f"Error creating attempt folder: {exc}"

    desc_text = (description or "").strip()
    if desc_text:
        try:
            (dest / "description.txt").write_text(
                desc_text + "\n", encoding="utf-8",
            )
        except OSError as exc:
            return (
                f"Attempt folder created at {dest.resolve()} but "
                f"description.txt could not be written: {exc}"
            )

    return (
        f"Created attempt {attempt_n} at {dest.resolve()}."
        + (f"  description.txt written ({len(desc_text)} chars)."
           if desc_text else "")
    )
