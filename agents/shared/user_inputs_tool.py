"""Generic user-input file/image tools shared across agents.

Every agent that needs on-demand access to the user's input files
(text + images under ``inputs/`` and ``inputs/input_images/``) binds
the four LangChain ``@tool`` stubs defined here:

  * ``list_input_files``      — categorised filesystem listing
  * ``read_input_text``       — read any text file under ``inputs/``
  * ``read_image_notes``      — read every ``<name>_note.txt`` at once
  * ``view_images``           — the unified image tool: view any images
    (user sketches under ``inputs/`` AND tool renders under ``attempts/``),
    optionally cropped to a coarse region and/or merged side-by-side into
    one comparison image.  Replaces the former ``load_input_images`` +
    ``load_render_images``.

The actual handlers live in this module too — each one mutates the
calling agent's ``messages`` list (appending a ToolMessage with a
text summary, plus, for ``view_images``, a separate HumanMessage
carrying the paired path-text + image content blocks).
The single ``dispatch_user_inputs_tool(agent, tc, agent_key)``
helper is the one-liner each agent's run loop adds to route a tool
call to its correct handler.

Image-loading uses the agent's own ``provider`` attribute so the
content block format matches the bound LLM.  When the
``keep_images_in_context`` toggle is OFF, the existing
``on_operation_end`` strip hook (called by the dispatcher) drops
image bytes at the next operation boundary while preserving the
paired ``Loaded image (path: …):`` text blocks — exactly the same
mechanism DCOI / UII / Receptionist already use for their other
image loads.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from pathlib import Path

from PIL import Image
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool

from agents.shared.agent_activity import generic_tool
from agents.shared.file_utils import (
    append_pending_images,
    list_files,
    load_text_file,
    load_user_inputs_bundle,
    pair_input_images,
)
from agents.shared.image_stitch import crop_to_region, stitch, to_rgb
from agents.shared.llm_provider import (
    encode_image,
    encode_image_bytes,
    make_image_block,
)
from agents.shared.routing_tools import log_tool_call
from agents.shared.ocr import ocr_regions_reread, ocr_summary_if_enabled
from config import (
    ATTEMPTS_DIR,
    INPUT_IMAGES_DIR,
    INPUT_IMAGES_SUBDIR,
    USER_INPUTS_DIR,
)
from workflow_settings import ocr_access
from workflow_settings import ocr_region_crops_access
from workflow_settings import settings as workflow_settings

logger = logging.getLogger("propeller_agent")

ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
NOTE_SUFFIX = "_note.txt"


# ---------------------------------------------------------------------------
# Tool stubs (LangChain bindings; real work happens in the handlers below)
# ---------------------------------------------------------------------------


@tool
def list_input_files() -> str:
    """List every file under ``inputs/``, including the ``input_images/``
    subfolder.  Reports root text/JSON files (e.g. ``user_query.txt``,
    ``extracted_inputs.txt``), every paired image+note in
    ``input_images/``, and any orphan image / note (a
    ``<name>.png/.jpg/.jpeg`` with no matching ``<name>_note.txt`` or
    vice-versa).  Takes NO arguments — the inputs root is fixed by
    the system."""
    return ""  # handled by dispatch_user_inputs_tool


@tool
def read_input_text(path: str) -> str:
    """Read any text file located under the inputs directory.

    ``path`` MUST be the absolute path of a file inside ``inputs/``
    (or its ``input_images/`` subfolder); paths outside the inputs
    tree are refused.  Use this to read a ``_note.txt`` describing
    a specific image, or to re-read ``user_query.txt`` /
    ``extracted_inputs.txt`` on demand."""
    return ""  # handled by dispatch_user_inputs_tool


@tool
def read_image_notes() -> str:
    """Read every ``<name>_note.txt`` file in ``inputs/input_images/``
    and return the contents grouped by image name.  Convenience
    helper so you do not have to call ``read_input_text`` once per
    note.  Takes NO arguments."""
    return ""  # handled by dispatch_user_inputs_tool


_VIEW_IMAGES_BASE_DOC = (
    "View one or more images so you can see them — user sketches (under "
    "``inputs/``) and/or tool-generated renders (under ``attempts/``), "
    "interchangeably.\n\n"
    "``paths``: a LIST of absolute image paths (``.png`` / ``.jpg`` / "
    "``.jpeg``) obtained from ``list_input_files`` or relayed in the hand-off. "
    "Do NOT guess or fabricate paths.  By default each image is shown "
    "full-size as its own block; the images are attached in the next user "
    "message, each preceded by its absolute path.\n\n"
    "``side_by_side`` (default False): when True, up to THREE images are "
    "merged into ONE labelled composite image so you can compare them "
    "directly in a single frame — best for judging shape/detail.  Pass more "
    "than 3 paths only with ``side_by_side=False``.\n\n"
    "``layout`` (``'match_height'`` default | ``'native'``): only affects "
    "``side_by_side`` — ``'match_height'`` scales every panel to the same "
    "height (best for comparing shapes at a matched scale); ``'native'`` "
    "keeps native pixels.\n\n"
    "``crop_regions`` (OPTIONAL): a list aligned by index with ``paths``; "
    "each entry is a COARSE crop box ``[x0, y0, x1, y1]`` as fractions in "
    "0..1 (or ``null`` for no crop), so a large sketch is cropped to its "
    "relevant part before viewing or comparing.  These are picture crops, "
    "unrelated to the numbered TEXT regions OCR reports.  The User Input "
    "Inspector identifies them from the raw images and records them in the "
    "extraction's ``USEFUL INPUT IMAGES`` section; other agents (e.g. the "
    "DC Output Inspector comparing blade sections) REUSE a recorded crop "
    "region when it helps.  Prefer a recorded or handed-off crop region "
    "over one you derive yourself."
)

_VIEW_IMAGES_OCR_DOC = _VIEW_IMAGES_BASE_DOC + (
    "\n\nIf OCR is enabled, each USER image (under ``inputs/``) is also passed "
    "through an OCR engine that recognises any text written on it — dimension "
    "callouts, labels, annotations — returned here as one numbered "
    "``[text region N]`` entry per detected block of text (when a crop "
    "region is given, only that crop is OCR'd).  Those numbers are the ids "
    "you pass to ``reread_text_regions``; they are TEXT blocks, not crop "
    "regions.  It is "
    "machine-recognised, so check it against the image before relying on a "
    "value.  Renders are never OCR'd.  Pass ``extract_text=False`` to skip OCR."
)


def _build_view_images(ocr_on: bool):
    """Build the unified ``view_images`` tool (replaces the old
    ``load_input_images`` + ``load_render_images``).

    The ``extract_text`` OCR flag is present ONLY when *ocr_on* is True.  The
    real work happens in ``_handle_view_images`` via the dispatcher; this stub
    just defines the LLM-facing schema + doc.
    """
    if ocr_on:
        def _impl(paths: list[str], side_by_side: bool = False,
                  layout: str = "match_height", crop_regions: list = None,
                  extract_text: bool = True) -> str:
            return ""  # handled by dispatch_user_inputs_tool
        _impl.__doc__ = _VIEW_IMAGES_OCR_DOC
    else:
        def _impl(paths: list[str], side_by_side: bool = False,
                  layout: str = "match_height",
                  crop_regions: list = None) -> str:
            return ""  # handled by dispatch_user_inputs_tool
        _impl.__doc__ = _VIEW_IMAGES_BASE_DOC
    return tool("view_images")(_impl)


_REREAD_TEXT_REGIONS_DOC = (
    "Re-read one or more blocks of TEXT written on a user image, at "
    "higher resolution — in a single call.  This is a SECOND pass, never "
    "a first read: it works only on text blocks an earlier whole-image "
    "OCR already found and numbered.  Use it when that OCR (from "
    "``view_images`` / ``read_user_inputs``) shows callouts you want to "
    "read more confidently — small, faint, or garbled dimensions.  "
    "``image_path`` is the absolute path of that user image (under "
    "``inputs/input_images/``); ``text_region_ids`` is a LIST of the "
    "numbers shown for THAT image in its OCR output (e.g. ``[2, 5, 7]`` "
    "for ``[text region 2]`` etc.).  These are TEXT blocks the OCR engine "
    "found — NOT the picture crops you pass to ``view_images`` as "
    "``crop_regions``.  When several callouts look worth a closer read, "
    "pass them all in ONE call rather than one call each — the tool "
    "re-reads them together (one shared detection pass) and returns every "
    "result at once.  For each one it crops, zooms in, and re-runs OCR, "
    "returning the re-read text — machine-recognised, so check it.  "
    "Depending on this agent's settings the tool may also attach the "
    "zoomed crop image of each text region so you can verify against it."
)


def _build_reread_text_regions():
    """Build the ``reread_text_regions`` tool (bound only when OCR is
    enabled)."""
    def _impl(image_path: str, text_region_ids: list[int]) -> str:
        return ""  # handled by dispatch_user_inputs_tool
    _impl.__doc__ = _REREAD_TEXT_REGIONS_DOC
    return tool("reread_text_regions")(_impl)


USER_INPUTS_TOOL_NAMES = {
    "list_input_files",
    "read_input_text",
    "read_image_notes",
    "view_images",
    "reread_text_regions",
}


def build_user_inputs_tools(
    agent_key: str,
    include_image_tools: bool = True,
    include_text_tools: bool = True,
) -> list:
    """Return the user-inputs tool objects to bind to *agent_key*.

    Built fresh (not a static list) so the OCR-dependent tools/flags
    appear ONLY when OCR is enabled **for this agent** — when OCR is off
    (globally OR for this agent via the per-agent toggle) the agent
    never sees the ``extract_text`` flag NOR the
    ``reread_text_regions`` tool.
    The gate is ``ocr_access.is_enabled_for(agent_key)`` (master
    ``OCR_ENABLED`` AND the per-agent flag), read as of that session's
    build.  ``list_input_files`` / ``read_input_text`` /
    ``read_image_notes`` are static (OCR does not touch them).

    When *include_image_tools* is False the agent gets ONLY the text-file
    tools (``list_input_files`` / ``read_input_text``); the image-viewing
    tools (``read_image_notes`` / ``view_images`` /
    ``reread_text_regions``)
    are withheld.  The DC Input Creator uses this — it works from
    ``extracted_inputs.txt`` and does not view raw images.

    When *include_text_tools* is False the three text-file tools
    (``list_input_files`` / ``read_input_text`` / ``read_image_notes``)
    are withheld and only the image tools are returned.  The UII uses
    this — its ``read_user_inputs`` already reads every text file at
    once, image notes included, and lists the image paths.
    """
    tools = [list_input_files, read_input_text] if include_text_tools else []
    if include_image_tools:
        on = ocr_access.is_enabled_for(agent_key)
        if include_text_tools:
            tools.append(read_image_notes)
        tools.append(_build_view_images(on))
        if on:
            # The text-region zoom-in tool exists only when OCR is on.
            tools.append(_build_reread_text_regions())
    return tools


# ---------------------------------------------------------------------------
# ``read_user_inputs`` — the whole-directory reader (UII + Planner)
#
# Historically defined inside the UII's module; hoisted here (2026-08-22)
# because the Planner now binds it too (it replaced the Planner's
# ``read_user_queries``).  The UII keeps its stub + in-agent handler
# (which routes through ``read_user_inputs_summary`` below); the Planner
# binds a directly-invokable tool built by ``build_read_user_inputs``
# with ``direct=True``.
# ---------------------------------------------------------------------------

# The UII's wording — unchanged from when this tool lived in its module.
READ_INPUTS_DOC_UII = (
    "Read a user-inputs directory: TEXT plus a LIST of its images (it does "
    "NOT load the images themselves).\n\n"
    "Pass the absolute path of the inputs directory supplied in your hand-off "
    "under the ``Input directory:`` label (do NOT guess).  The output is a "
    "summary plus the concatenated contents of all text/JSON files — "
    "including every image's ``_note.txt`` — followed by a list of the "
    "reference images present with their paths.  To actually SEE an image "
    "(and get its OCR-recognised text: dimension callouts, labels), call "
    "``view_images`` with the path(s) you need."
)

# The DC Input Inspector's wording — it receives an ``Extracted inputs
# file:`` label, never an ``Input directory:`` one, and it DOES hold
# ``view_images``.
READ_INPUTS_DOC_DCII = (
    "Read the user-inputs directory: TEXT plus a LIST of its images (it does "
    "NOT load the images themselves.\n\n"
    "Pass the absolute path of the user-inputs directory — the folder holding "
    "``user_query.txt`` and ``extracted_inputs.txt``, i.e. the parent "
    "directory of the ``Extracted inputs file:`` path your hand-off carries "
    "(do NOT guess a path).  The output is a summary plus the concatenated "
    "contents of all text/JSON files — including every image's "
    "``_note.txt`` — followed by a list of the reference images present with "
    "their paths.  To actually SEE an image, call ``view_images`` with the "
    "path(s) you need."
)

# The Planner's wording — no ``Input directory:`` label reaches it and it
# holds no image tools, so the pointers differ.
READ_INPUTS_DOC_PLANNER = (
    "Read the user-inputs directory: TEXT plus a LIST of its images (it "
    "does NOT load the images themselves).\n\n"
    "Pass the absolute path of the user-inputs directory — the folder "
    "holding ``user_query.txt`` and ``extracted_inputs.txt``; when your "
    "hand-off names an ``Extracted inputs file:``, it is that file's parent "
    "directory (do NOT guess a path).  The output is a summary plus the "
    "concatenated contents of all text/JSON files — the user's queries, the "
    "current extraction and every image's ``_note.txt`` — followed by a "
    "list of the reference images present with their paths."
)


_TURN_HEADER_RE = re.compile(
    r"^--- \[[^\]]{1,40}\](?:[ \t]+([A-Z]+))?[ \t]*---[ \t]*$",
    re.MULTILINE,
)


def strip_turn_timestamps(text: str) -> str:
    """Rewrite conversation headers without their date-and-time stamp.

    ``user_query.txt`` records each turn as ``--- [YYYY-MM-DD HH:MM:SS]
    USER ---`` / ``--- [...] RECEPTIONIST ---``.  The exact clock time is
    of no use to the UII — it needs the ORDER and the SPEAKER — so the
    header collapses to ``--- USER ---`` / ``--- RECEPTIONIST ---``.

    Entries written before the role tag existed carry no role; they were
    all user turns, so they render as ``--- USER ---``.

    The file itself is never rewritten: timestamps stay on disk as
    provenance for the Database Handler's archive, and
    ``_parse_user_query_entries`` (the 5-agent Conductor / 3-agent
    Architect) still splits on the original header.  This is a
    presentation-time transform for one reader.
    """
    return _TURN_HEADER_RE.sub(
        lambda m: f"--- {m.group(1) or 'USER'} ---", text,
    )


def read_user_inputs_summary(
    raw_path,
    provider: str = "openai",
    exclude_root_files: tuple[str, ...] = (),
    can_view_images: bool = False,
    strip_timestamps: bool = False,
) -> str:
    """The ``read_user_inputs`` result text for *raw_path*.

    Shared by the UII's in-agent handler and the Planner's directly-
    invokable binding, so the two agents read exactly the same view of
    the inputs directory.  *can_view_images* adds the "call view_images
    to SEE an image" pointer — only for an agent that actually binds
    ``view_images`` (the UII; the Planner has no image tools).
    *strip_timestamps* collapses each conversation turn header to its
    speaker — see :func:`strip_turn_timestamps`.
    """
    if not raw_path or not isinstance(raw_path, str):
        return (
            "Error: no directory path provided.  Call this tool with "
            "the absolute path of the user-inputs directory."
        )
    directory = Path(raw_path)
    if not directory.is_dir():
        return (
            f"Error: '{raw_path}' is not an existing directory.  "
            f"Do not retry with a guessed path."
        )
    # Images are NOT loaded here — the caller loads the specific
    # image(s) it needs on demand via view_images (where bound).
    # read_user_inputs stays cheap: text + notes + a list of the
    # images present.
    loaded = load_user_inputs_bundle(
        directory,
        provider,
        include_image_bytes=False,
        exclude_root_files=exclude_root_files,
    )
    image_paths = loaded["image_paths"]
    pairing = loaded["pairing"]
    summary_parts = [
        f"Loaded inputs from {directory.resolve()}.",
        f"Files: {loaded['summary']}",
    ]
    if not pairing["ok"]:
        summary_parts.append(
            "WARNING: image+note pairing is INVALID.  "
            "The Receptionist should have caught this — "
            "ESCALATE so the user can be asked to fix the "
            "uploads.  Pairing report:\n" + pairing["report"]
        )
    if loaded["text_content"]:
        body = loaded["text_content"]
        if strip_timestamps:
            body = strip_turn_timestamps(body)
        summary_parts.append("--- File contents ---\n" + body)
    else:
        summary_parts.append("(no text or JSON files found)")
    if image_paths:
        listing = "\n".join(
            f"  - {Path(p).name}   (path: {p})"
            for p in image_paths
        )
        hint = (
            "  To SEE an image and get its OCR text, call "
            "view_images with the path(s) you need:"
            if can_view_images else
            "  Their paths, for relaying to an agent that can view them:"
        )
        summary_parts.append(
            f"{len(image_paths)} reference image(s) are available "
            f"but NOT loaded here (their notes are in the file "
            f"contents above).{hint}\n" + listing
        )
    return "\n\n".join(summary_parts)


def build_read_user_inputs(
    doc: str = READ_INPUTS_DOC_UII,
    direct_provider: str | None = None,
):
    """Build a ``read_user_inputs`` tool object.

    With *direct_provider* None the tool is a SCHEMA-ONLY stub (returns
    ``""``) for an agent whose run loop handles the call itself — the
    UII.  With a provider string it is directly invokable and returns
    :func:`read_user_inputs_summary` — the Planner's binding, whose run
    loop invokes unknown tools generically.
    """
    if direct_provider is None:
        def _impl(path: str) -> str:
            return ""  # handled by the binding agent's own handler
    else:
        def _impl(path: str) -> str:
            return read_user_inputs_summary(path, direct_provider)
    _impl.__doc__ = doc
    return tool("read_user_inputs")(_impl)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_inside_inputs(path: Path) -> bool:
    """True iff *path* resolves inside the configured inputs root."""
    try:
        p = path.resolve()
        root = USER_INPUTS_DIR.resolve()
    except OSError:
        return False
    return p == root or root in p.parents


def _attempt_params_blocks(loaded) -> list:
    """For any viewed image that lives in an attempt folder, append the
    parameter values that attempt was built from — so whoever is looking at a
    render always sees the numbers behind the picture, without depending on an
    upstream agent to relay them.  One block per attempt folder; silently
    skipped when the folder has no readable/complete ``parameters.json``.
    """
    # Imported lazily: reaching tools.render_blade_sections executes
    # tools/__init__, which pulls the heavy 3D render stack (trimesh / pyrender
    # / pyvista).  This module is a light shared image utility, so we only pay
    # that when a render is actually viewed.
    from tools.render_blade_sections.sections_geom import rendered_params_block

    out, seen = [], set()
    for raw in loaded:
        folder = Path(raw).parent
        if folder in seen or not _is_inside_attempts(folder):
            continue
        pj = folder / "parameters.json"
        if not pj.is_file():
            continue
        seen.add(folder)
        try:
            params = json.loads(pj.read_text(encoding="utf-8"))
            if isinstance(params, dict):
                out.append(f"{folder.name}:\n" + rendered_params_block(params))
        except Exception:  # unreadable / partial params — not worth failing a view
            continue
    return out


def _is_inside_attempts(path: Path) -> bool:
    """True iff *path* resolves inside the configured attempts root (a render)."""
    try:
        p = path.resolve()
        root = ATTEMPTS_DIR.resolve()
    except OSError:
        return False
    return p == root or root in p.parents


_COMPARISONS_SUBDIR = "_comparisons"


def _save_composite(png_bytes: bytes):
    """Save a side-by-side composite under ``attempts/_comparisons/`` so it
    auto-displays in the chat (the turn artefact-diff globs ``render_*.png``
    under ATTEMPTS_DIR).  Best-effort: returns the saved ``Path`` or ``None``
    on any write error.  Named ``render_comparison_<n>.png``."""
    try:
        out_dir = ATTEMPTS_DIR / _COMPARISONS_SUBDIR
        out_dir.mkdir(parents=True, exist_ok=True)
        n = sum(1 for _ in out_dir.glob("render_comparison_*.png")) + 1
        out_path = out_dir / f"render_comparison_{n}.png"
        while out_path.exists():   # skip past any gap so we never clobber
            n += 1
            out_path = out_dir / f"render_comparison_{n}.png"
        out_path.write_bytes(png_bytes)
        return out_path
    except OSError as exc:
        logger.warning("[view_images] could not save composite: %s", exc)
        return None


def _format_input_files_listing() -> str:
    """Return a categorised listing of every file under ``inputs/``."""
    if not USER_INPUTS_DIR.is_dir():
        return f"No inputs directory found at {USER_INPUTS_DIR.resolve()}."

    root_entries = list_files(USER_INPUTS_DIR)
    pairing = pair_input_images(INPUT_IMAGES_DIR)

    lines: list[str] = [f"Inputs directory: {USER_INPUTS_DIR.resolve()}"]
    if root_entries:
        lines.append("")
        lines.append("Root files:")
        for f in root_entries:
            lines.append(
                f"  - {f['name']}  ({f['category']})  "
                f"path: {f['path']}"
            )
    else:
        lines.append("(no files in the inputs root)")

    lines.append("")
    if not INPUT_IMAGES_DIR.is_dir():
        lines.append(
            f"{INPUT_IMAGES_SUBDIR}/ subfolder: not present (no images "
            f"have been uploaded)."
        )
    else:
        lines.append(f"{INPUT_IMAGES_SUBDIR}/ subfolder:")
        if not pairing["pairs"] and not pairing["orphan_images"] and not pairing["orphan_notes"]:
            lines.append("  (empty)")
        else:
            for img, note in pairing["pairs"]:
                lines.append(
                    f"  - PAIR  image: {img.name}   note: {note.name}"
                )
                lines.append(f"          image path: {img.resolve()}")
                lines.append(f"          note path : {note.resolve()}")
            for img in pairing["orphan_images"]:
                lines.append(
                    f"  - ORPHAN image (no matching {img.stem}_note.txt): "
                    f"{img.name}"
                )
                lines.append(f"          image path: {img.resolve()}")
            for note in pairing["orphan_notes"]:
                stem = note.name[: -len(NOTE_SUFFIX)]
                lines.append(
                    f"  - ORPHAN note (no matching {stem}.png/.jpg/.jpeg): "
                    f"{note.name}"
                )
                lines.append(f"          note path : {note.resolve()}")
            for stem, paths in pairing.get("duplicate_stems", []):
                names = ", ".join(p.name for p in paths)
                lines.append(
                    f"  - DUPLICATE-STEM image set (keep only one): "
                    f"{names}"
                )
        if not pairing["ok"]:
            lines.append("")
            lines.append(
                "PAIRING INVALID — every <name>.png/.jpg/.jpeg must be "
                "paired with <name>_note.txt and vice-versa, and each "
                "stem may use only one image format.  The Receptionist "
                "will not forward the user's request until this is fixed."
            )
    return "\n".join(lines)


def _format_image_notes() -> str:
    """Return the contents of every ``<name>_note.txt`` in the images folder."""
    if not INPUT_IMAGES_DIR.is_dir():
        return (
            f"{INPUT_IMAGES_SUBDIR}/ subfolder is not present at "
            f"{INPUT_IMAGES_DIR.resolve()} — there are no notes to read."
        )
    pairing = pair_input_images(INPUT_IMAGES_DIR)
    if not pairing["pairs"] and not pairing["orphan_notes"]:
        return f"{INPUT_IMAGES_SUBDIR}/ has no _note.txt files."

    lines: list[str] = []
    for img, note in pairing["pairs"]:
        try:
            text = load_text_file(note)
        except Exception as exc:
            text = f"(failed to read: {exc})"
        lines.append(
            f"--- {note.name} (describes image {img.name}) ---\n{text}"
        )
    for note in pairing["orphan_notes"]:
        try:
            text = load_text_file(note)
        except Exception as exc:
            text = f"(failed to read: {exc})"
        lines.append(
            f"--- {note.name} (ORPHAN — no matching "
            f".png/.jpg/.jpeg image) ---\n{text}"
        )
    if pairing["orphan_images"]:
        names = ", ".join(p.name for p in pairing["orphan_images"])
        lines.append(
            f"NOTE: the following image(s) have no matching _note.txt: "
            f"{names}"
        )
    if pairing.get("duplicate_stems"):
        for stem, paths in pairing["duplicate_stems"]:
            names = ", ".join(p.name for p in paths)
            lines.append(
                f"NOTE: stem '{stem}' is used by more than one image "
                f"format ({names}) — keep only one per stem."
            )
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Tool-call handlers
# ---------------------------------------------------------------------------


@generic_tool("List input files")
def _handle_list_input_files(agent, tc: dict, agent_key: str) -> None:
    summary = _format_input_files_listing()
    log_tool_call(agent_key, tc["name"], tc.get("args"), summary)
    agent.messages.append(ToolMessage(
        content=summary,
        tool_call_id=tc["id"],
        name=tc["name"],
    ))


@generic_tool("Read input text")
def _handle_read_input_text(agent, tc: dict, agent_key: str) -> None:
    raw_path = (tc.get("args", {}) or {}).get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        summary = (
            "Error: missing or non-string 'path' argument.  Pass the "
            "absolute path of a text file under the inputs/ directory."
        )
    else:
        path = Path(raw_path)
        if not _is_inside_inputs(path):
            summary = (
                f"Error: '{raw_path}' is not under the inputs/ directory.  "
                f"This tool only reads files inside "
                f"{USER_INPUTS_DIR.resolve()}."
            )
        elif not path.is_file():
            summary = (
                f"Error: '{raw_path}' is not an existing file.  Use "
                f"list_input_files to discover valid paths."
            )
        else:
            try:
                content = load_text_file(path)
            except Exception as exc:
                summary = f"Error reading '{raw_path}': {exc}"
            else:
                if not content.strip():
                    summary = f"'{path.name}' exists but is empty."
                else:
                    summary = (
                        f"--- {path.name} (path: {path.resolve()}) ---\n"
                        f"{content}"
                    )
    log_tool_call(agent_key, tc["name"], tc.get("args"), summary)
    agent.messages.append(ToolMessage(
        content=summary,
        tool_call_id=tc["id"],
        name=tc["name"],
    ))


@generic_tool("Read image notes")
def _handle_read_image_notes(agent, tc: dict, agent_key: str) -> None:
    summary = _format_image_notes()
    log_tool_call(agent_key, tc["name"], tc.get("args"), summary)
    agent.messages.append(ToolMessage(
        content=summary,
        tool_call_id=tc["id"],
        name=tc["name"],
    ))


def _load_cropped(path: Path, region):
    """Return (rgb_pil, png_bytes) for a possibly-cropped, white-flattened copy
    of the image at *path*.  The on-disk original is never modified."""
    im = to_rgb(Image.open(path))
    cropped = crop_to_region(im, region)
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return cropped, buf.getvalue()


@generic_tool("View images")
def _handle_view_images(agent, tc: dict, agent_key: str) -> None:
    args = tc.get("args", {}) or {}
    raw_paths = args.get("paths")
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    if not isinstance(raw_paths, list) or not raw_paths:
        summary = (
            "Error: 'paths' must be a non-empty list of absolute image paths "
            "(user images under inputs/ or renders under attempts/).  Discover "
            "valid paths via list_input_files or the hand-off."
        )
        log_tool_call(agent_key, tc["name"], tc.get("args"), summary)
        agent.messages.append(ToolMessage(
            content=summary, tool_call_id=tc["id"], name=tc["name"],
        ))
        return

    side_by_side = bool(args.get("side_by_side", False))
    layout = args.get("layout") or "match_height"
    if layout not in ("match_height", "native"):
        layout = "match_height"
    regions = args.get("crop_regions")
    if not isinstance(regions, list):
        regions = []
    # Per-agent OCR gate: the schema hides ``extract_text`` when THIS agent's
    # OCR is off, but the runtime pass must also honour the per-agent flag —
    # ``ocr_summary_if_enabled`` only checks the GLOBAL switch, so without this
    # a per-agent-disabled agent would still get OCR text on the default.
    ocr_on = ocr_access.is_enabled_for(agent_key)
    extract_text = ocr_on and bool(args.get(
        "extract_text",
        getattr(workflow_settings, "OCR_WHOLE_IMAGE_DEFAULT", True),
    ))
    provider = getattr(agent, "provider", "openai")

    # Resolve + validate each path; classify user-image (inputs/) vs render
    # (attempts/); attach the aligned crop region.
    resolved = []          # {path, is_render, region}
    missing: list[str] = []
    for i, raw in enumerate(raw_paths):
        if not isinstance(raw, str):
            missing.append(str(raw)); continue
        path = Path(raw)
        in_inputs = _is_inside_inputs(path)
        in_attempts = _is_inside_attempts(path)
        if not (in_inputs or in_attempts):
            missing.append(f"{raw} (not under inputs/ or attempts/)"); continue
        if not path.is_file() or path.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
            missing.append(f"{raw} (missing or unsupported suffix)"); continue
        region = regions[i] if i < len(regions) else None
        resolved.append({"path": path, "is_render": in_attempts, "region": region})

    image_blocks: list[dict] = []
    image_paths: list[str] = []
    ocr_items = []         # (label, source) — user images only; source = bytes/path
    loaded: list[str] = []
    body_parts: list[str] = []

    if side_by_side and resolved:
        # Merge up to 3 (cropped) panels into ONE labelled composite image.
        pil_panels, labels = [], []
        for j, r in enumerate(resolved[:3]):
            try:
                cropped, cbytes = _load_cropped(r["path"], r["region"])
            except (OSError, ValueError) as exc:
                missing.append(f"{r['path']} (read error: {exc})"); continue
            pil_panels.append(cropped)
            labels.append(f"{j + 1}: {r['path'].name}")
            loaded.append(str(r["path"].resolve()))
            if (not r["is_render"]) and extract_text:
                ocr_items.append((r["path"].name, cbytes))
        if pil_panels:
            try:
                comp = stitch(pil_panels, labels, layout)
                cbuf = io.BytesIO(); comp.save(cbuf, format="PNG")
                comp_bytes = cbuf.getvalue()
                saved = _save_composite(comp_bytes)   # auto-shows in chat
                # degree_pct=0: the composite is already sized to the vision cap.
                b64 = encode_image_bytes(comp_bytes, degree_pct=0)
                image_blocks.append(make_image_block(b64, provider))
                image_paths.append(str(saved) if saved else "composite")
                body_parts.append(
                    f"Composed {len(pil_panels)} image(s) side-by-side "
                    f"(layout={layout}) into one comparison image"
                    + (f", saved to {saved}." if saved else ".")
                )
            except Exception as exc:   # noqa: BLE001 — a compose error must not crash the tool
                body_parts.append(f"Could not compose the side-by-side image: {exc}")
    else:
        # Separate full-size blocks (today's behaviour; >3 allowed).
        for r in resolved:
            try:
                if r["region"]:
                    _cropped, cbytes = _load_cropped(r["path"], r["region"])
                    if r["is_render"]:
                        b64 = encode_image_bytes(cbytes, is_render=True,
                                                 name=r["path"].name)
                    else:
                        b64 = encode_image_bytes(cbytes, degree_pct=None,
                                                 is_render=False)
                    ocr_src = cbytes
                else:
                    b64 = encode_image(r["path"], is_render=r["is_render"])
                    ocr_src = r["path"]
            except (OSError, ValueError) as exc:
                missing.append(f"{r['path']} (read error: {exc})"); continue
            image_blocks.append(make_image_block(b64, provider))
            image_paths.append(str(r["path"].resolve()))
            loaded.append(str(r["path"].resolve()))
            if (not r["is_render"]) and extract_text:
                ocr_items.append((r["path"].name, ocr_src))

    # Build the ToolMessage summary.
    head = [
        f"Viewed {len(loaded)} image(s)"
        + (" as a side-by-side comparison." if side_by_side else ".")
    ]
    if loaded:
        head.append("Paths:\n  " + "\n  ".join(loaded))
    if missing:
        head.append("Missing / invalid paths:\n  " + "\n  ".join(missing))
    if image_blocks:
        head.append(
            "The image(s) are attached in the next user message, each preceded "
            "by its path so it stays in history even if bytes are later stripped."
        )
    else:
        head.append("No images were shown.  Do not retry with guessed paths.")

    # OCR (gated) — user images only, on the cropped region when one was given.
    parts = head + body_parts + _attempt_params_blocks(loaded) + list(
        ocr_summary_if_enabled(ocr_items, extract_text)
    )
    summary = "\n".join(parts)

    log_tool_call(agent_key, tc["name"], tc.get("args"), summary)
    agent.messages.append(ToolMessage(
        content=summary, tool_call_id=tc["id"], name=tc["name"],
    ))
    if image_blocks:
        # Buffer instead of appending a HumanMessage immediately so that a
        # batched sibling tool_call still satisfies the tool_use→tool_result
        # contiguity rule; the run loop flushes the buffer after all
        # ToolMessages are appended.
        append_pending_images(agent, image_blocks, image_paths)


@generic_tool("Read text regions (OCR)")
def _handle_reread_text_regions(agent, tc: dict, agent_key: str) -> None:
    """Re-OCR one or more TEXT regions of a user image at higher
    resolution in a single call.  Validates the path + text_region_ids,
    delegates the shared (single) detection + per-region crop/re-read to
    the engine, and attaches one zoomed crop per text region ONLY when
    crop-attachment is enabled for this agent (else returns the
    higher-res re-read text only).  Non-fatal throughout — invalid ids
    are reported inline without aborting the valid ones."""
    args = tc.get("args", {}) or {}
    raw_path = args.get("image_path")
    raw_regions = args.get("text_region_ids")

    def _err(msg: str) -> None:
        log_tool_call(agent_key, tc["name"], tc.get("args"), msg)
        agent.messages.append(ToolMessage(
            content=msg, tool_call_id=tc["id"], name=tc["name"],
        ))

    if not isinstance(raw_path, str) or not raw_path.strip():
        _err(
            "Error: 'image_path' must be the absolute path of a user "
            "image under inputs/input_images/."
        )
        return
    path = Path(raw_path)
    if not _is_inside_inputs(path):
        _err(f"Error: '{raw_path}' is not under the inputs/ directory.")
        return
    if not path.is_file() or path.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
        _err(
            f"Error: '{raw_path}' is not an existing .png/.jpg/.jpeg "
            f"image.  Discover valid paths via list_input_files."
        )
        return

    # Accept a list of text-region numbers; coerce a bare int/str.
    if isinstance(raw_regions, (int, str)):
        raw_regions = [raw_regions]
    if not isinstance(raw_regions, (list, tuple)) or not raw_regions:
        _err(
            "Error: 'text_region_ids' must be a non-empty list of "
            "integer text-region numbers from the image's OCR output "
            "(e.g. [2, 5, 7])."
        )
        return
    region_ids: list[int] = []
    bad_ids: list[str] = []
    for raw in raw_regions:
        try:
            region_ids.append(int(raw))
        except (TypeError, ValueError):
            bad_ids.append(repr(raw))
    if not region_ids:
        _err(
            f"Error: 'text_region_ids' had no valid integer text-region "
            f"numbers (got {raw_regions!r})."
        )
        return

    result = ocr_regions_reread(str(path.resolve()), region_ids)

    # Whole-call failure (engine/PIL import, bad image, detection): stop.
    if not result.get("ok"):
        _err(
            f"Could not re-read text regions on {path.name}: "
            f"{result.get('error')}."
        )
        return

    crops_on = ocr_region_crops_access.is_enabled_for(agent_key)
    results = result.get("results") or []
    invalid = result.get("invalid") or []
    n_ok = sum(1 for r in results if r.get("ok"))

    # Denominator = the de-duplicated, VALID text regions attempted
    # (``results``), not the raw request list — duplicates are silently
    # collapsed and out-of-range ids are listed separately below.
    parts: list[str] = [
        f"Re-read {n_ok} of {len(results)} text region(s) on "
        f"{path.name} at higher resolution — machine-read, so check "
        f"each value:"
    ]
    crop_blocks: list[dict] = []
    crop_labels: list[str] = []
    for r in results:
        rid = r.get("region_id")
        if r.get("ok"):
            reread = (r.get("reread_text") or "").strip()
            line = f"  [text region {rid}] {reread or '(no text detected)'}"
            if r.get("original_text"):
                line += f"   (whole-image OCR: {r['original_text']!r})"
            parts.append(line)
            if crops_on and r.get("crop_png"):
                b64 = base64.b64encode(r["crop_png"]).decode()
                crop_blocks.append(make_image_block(
                    b64, getattr(agent, "provider", "openai")
                ))
                crop_labels.append(
                    f"{path.resolve()} (text region {rid} zoom)")
        else:
            parts.append(
                f"  [text region {rid}] could not re-read: "
                f"{r.get('error')}"
            )
    for inv in invalid:
        parts.append(
            f"  Invalid: text region {inv.get('region_id')} — "
            f"{inv.get('error')}"
        )
    if bad_ids:
        parts.append(
            "  Ignored non-integer text-region id(s): "
            + ", ".join(bad_ids)
        )
    if crop_blocks:
        parts.append(
            f"The {len(crop_blocks)} zoomed crop(s) are attached in the "
            f"next user message, one per text region (labelled by text "
            f"region) — verify each value against its crop."
        )
    summary = "\n".join(parts)

    log_tool_call(agent_key, tc["name"], tc.get("args"), summary)
    agent.messages.append(ToolMessage(
        content=summary, tool_call_id=tc["id"], name=tc["name"],
    ))
    if crop_blocks:
        append_pending_images(agent, crop_blocks, crop_labels)


_HANDLERS = {
    "list_input_files":  _handle_list_input_files,
    "read_input_text":   _handle_read_input_text,
    "read_image_notes":  _handle_read_image_notes,
    "view_images":       _handle_view_images,
    "reread_text_regions": _handle_reread_text_regions,
}


def dispatch_user_inputs_tool(agent, tc: dict, agent_key: str) -> bool:
    """If ``tc`` calls one of the user-inputs tools, handle it and return True.

    Each handler appends the appropriate messages onto ``agent.messages``
    and writes a ``log_tool_call`` line tagged with *agent_key*.  Returns
    False (no side effects) if the tool name is not one of the
    user-inputs tools, so the agent's run loop can fall through to its
    other branches.
    """
    name = tc.get("name")
    handler = _HANDLERS.get(name)
    if handler is None:
        return False
    handler(agent, tc, agent_key)
    return True
