"""Tools for inspecting and creating per-attempt folders.

An "attempt" folder is the canonical home for ONE design-generation
process: it may carry the DC inputs (``parameters.json``), the DC
output (``propeller_mesh.obj``), the analysis renders
(``render_*.png``), an optional ``description.txt``, and any further
metrics produced for the same set of inputs.  Folders are created
explicitly by the agents that own the next design generation
(Planner / Orchestrator / DCIC) — nothing creates them implicitly.

Three tools are defined here:

- ``list_attempts()`` — enumerate every attempt folder so far this
  session, with attempt number and the files present so an agent can
  see what each attempt actually contains.
- ``read_attempt(n, file)`` — read one specific file from the n-th
  attempt.  Text/JSON content is returned inline; for images the
  absolute path is returned so the caller can hand it to
  ``load_render_images``.
- ``new_attempt(slug, description)`` — create a new, empty attempt
  folder and return its absolute path.

Files inside an attempt folder are append-only: every write tool that
targets an attempt refuses to overwrite an existing file.
"""

import re
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool

from config import ATTEMPTS_DIR

# Folder names produced by ``new_attempt`` have the form
# ``YYYYMMDD_HHMMSS_NNN_<slug>`` — the third group is the 1-based
# attempt number.
_ATTEMPT_RE = re.compile(r"^(\d{8})_(\d{6})_(\d+)_(.+)$")

_TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv", ".log", ".obj"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}

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


@tool
def list_attempts() -> str:
    """List every attempt folder created so far this session.

    An attempt folder is the canonical container for one design-
    generation process: it may hold the DC inputs (``parameters.json``),
    the generated mesh (``propeller_mesh.obj``), the rendered analysis
    images (``render_*.png``), and an optional ``description.txt``.
    Folders may be partial — e.g. a folder with only parameters.json
    means no mesh was generated yet for that input set.

    Returns a numbered summary so you can refer to past attempts by
    their attempt number when calling ``read_attempt(n, file)``, plus
    an explicit ``Has:`` line per attempt naming which roles
    (parameters / mesh / renders / description) are present.  Returns
    ``'No attempts created yet.'`` when no folder exists.
    """
    items = _list_attempt_folders()
    if not items:
        return "No attempts created yet."
    lines = [
        f"{len(items)} attempt(s) under {ATTEMPTS_DIR.resolve()}:"
    ]
    for n, folder in items:
        names, flags = _classify_files(folder)
        present_roles = [
            label for label, ok in (
                ("parameters", flags["parameters"]),
                ("mesh", flags["mesh"]),
                ("renders", flags["renders"]),
                ("description", flags["description"]),
            ) if ok
        ]
        lines.append(f"  Attempt {n}: {folder.name}")
        lines.append(
            f"    Has: {', '.join(present_roles) if present_roles else '(empty)'}"
        )
        lines.append(
            f"    Files: {', '.join(names) if names else '(empty)'}"
        )
    return "\n".join(lines)


@tool
def read_attempt(n: int, file: str) -> str:
    """Read a specific file from the n-th attempt folder.

    Args:
      n:    1-based attempt number, as shown by ``list_attempts``.
      file: a bare filename inside the attempt folder
            (e.g. ``'parameters.json'``, ``'render_isometric.png'``,
            ``'propeller_mesh.obj'``, ``'description.txt'``).  Path
            separators and ``..`` are rejected.

    For text / JSON files the content is returned inline.  For image
    files the resolved absolute path is returned so the caller can
    hand it to a tool that loads images (e.g.
    ``load_render_images``).  Returns an explicit error string if
    the attempt or file is missing.
    """
    try:
        n_int = int(n)
    except (TypeError, ValueError):
        return "Error: 'n' must be an integer >= 1."
    if n_int < 1:
        return "Error: 'n' must be >= 1."

    if not isinstance(file, str) or not file.strip():
        return "Error: 'file' must be a non-empty filename string."
    file_clean = file.strip()
    if "/" in file_clean or "\\" in file_clean or ".." in file_clean:
        return (
            f"Error: 'file' must be a bare filename inside the attempt "
            f"folder — no path separators or '..' allowed.  "
            f"Got: {file!r}."
        )

    items = _list_attempt_folders()
    if not items:
        return "Error: no attempts created yet."

    folder = next((f for num, f in items if num == n_int), None)
    if folder is None:
        available = sorted({num for num, _ in items})
        return (
            f"Error: no attempt numbered {n_int} found.  "
            f"Available attempt numbers: {available}."
        )

    target = folder / file_clean
    if not target.is_file():
        try:
            present = sorted(p.name for p in folder.iterdir() if p.is_file())
        except OSError:
            present = []
        return (
            f"Error: '{file_clean}' not found in attempt {n_int} "
            f"({folder.name}).  Files present: {present}."
        )

    suffix = target.suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return (
            f"Image file at: {target.resolve()}\n"
            f"(read_attempt does not return image bytes inline — "
            f"hand this absolute path to a tool that loads images, "
            f"e.g. ``load_render_images``.)"
        )
    if suffix in _TEXT_SUFFIXES or suffix == "":
        try:
            content = target.read_text(encoding="utf-8")
        except OSError as exc:
            return f"Error reading '{target}': {exc}"
        return (
            f"Loaded {target.name} from attempt {n_int} "
            f"({folder.name}, {len(content)} chars).\n\n"
            f"--- {file_clean} ---\n{content}"
        )
    return (
        f"File at: {target.resolve()} (extension '{suffix}' is "
        f"neither a recognised text nor image format; absolute path "
        f"returned)."
    )


@tool
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
