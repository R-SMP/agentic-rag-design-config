"""Generic user-input file/image tools shared across agents.

Every agent that needs on-demand access to the user's input files
(text + images under ``inputs/`` and ``inputs/input_images/``) binds
the four LangChain ``@tool`` stubs defined here:

  * ``list_input_files``      — categorised filesystem listing
  * ``read_input_text``       — read any text file under ``inputs/``
  * ``read_image_notes``      — read every ``<name>_note.txt`` at once
  * ``load_input_images``     — load one or more user-supplied images

The actual handlers live in this module too — each one mutates the
calling agent's ``messages`` list (appending a ToolMessage with a
text summary, plus, for ``load_input_images``, a separate
HumanMessage carrying the paired path-text + image content blocks).
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
import logging
from pathlib import Path

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool

from agents.shared.agent_activity import generic_tool
from agents.shared.file_utils import (
    append_pending_images,
    list_files,
    load_text_file,
    pair_input_images,
)
from agents.shared.llm_provider import encode_image, make_image_block
from agents.shared.routing_tools import log_tool_call
from agents.shared.ocr import ocr_regions_reread, ocr_summary_if_enabled
from config import INPUT_IMAGES_DIR, INPUT_IMAGES_SUBDIR, USER_INPUTS_DIR
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


_LOAD_IMAGES_BASE_DOC = (
    "Load one or more user-supplied images so you can see them.\n\n"
    "``paths`` MUST be a list of absolute paths obtained from "
    "``list_input_files`` (or relayed in the hand-off message).  Each "
    "path must point at a ``.png``, ``.jpg``, or ``.jpeg`` inside "
    "``inputs/input_images/``.  Loaded images are attached in the next "
    "user message, each preceded by its absolute path so the path "
    "remains in your history even if image bytes are later stripped.  "
    "Do NOT call this tool with guessed or fabricated paths."
)

_LOAD_IMAGES_OCR_DOC = _LOAD_IMAGES_BASE_DOC + (
    "\n\nIf OCR is enabled, each loaded image is also passed through an "
    "OCR engine that recognises any text written on the image — "
    "dimension callouts, labels, annotations — and that recognised text "
    "is returned to you here, one entry per detected text region.  Treat "
    "it as the image's text, read for you by OCR: it is machine-recognised, "
    "so check it against the image before you rely on a value.  Pass "
    "``extract_text=False`` to skip OCR for a given call."
)


def _build_load_input_images(ocr_on: bool):
    """Build the ``load_input_images`` tool.

    The ``extract_text`` OCR flag is present ONLY when *ocr_on* is True —
    so when OCR is globally disabled the agent never sees the flag.  The
    real work happens in ``_handle_load_input_images`` via the
    dispatcher; this stub just defines the LLM-facing schema + doc.
    """
    if ocr_on:
        def _impl(paths: list[str], extract_text: bool = True) -> str:
            return ""  # handled by dispatch_user_inputs_tool
        _impl.__doc__ = _LOAD_IMAGES_OCR_DOC
    else:
        def _impl(paths: list[str]) -> str:
            return ""  # handled by dispatch_user_inputs_tool
        _impl.__doc__ = _LOAD_IMAGES_BASE_DOC
    return tool("load_input_images")(_impl)


_OCR_REGIONS_DOC = (
    "Re-read one or more labelled text regions of a user image at higher "
    "resolution — in a single call.\n\n"
    "Use this when an image's whole-image OCR (from ``load_input_images`` "
    "/ ``read_user_inputs``) shows callouts you want to read more "
    "confidently — small, faint, or garbled dimensions.  ``image_path`` "
    "is the absolute path of that user image (under "
    "``inputs/input_images/``); ``region_ids`` is a LIST of the region "
    "numbers shown for THAT image in its OCR output (e.g. ``[2, 5, 7]`` "
    "for ``[region 2]`` etc.).  When several callouts look worth a closer "
    "read, pass them all in ONE call rather than one call each — the tool "
    "re-reads them together (one shared detection pass) and returns every "
    "result at once.  For each region it crops, zooms in, and re-runs OCR, "
    "returning the re-read text — machine-recognised, so check it.  "
    "Depending on this agent's settings the tool may also attach the "
    "zoomed crop image of each region so you can verify against it."
)


def _build_ocr_regions():
    """Build the ``ocr_regions`` tool (only bound when OCR is enabled)."""
    def _impl(image_path: str, region_ids: list[int]) -> str:
        return ""  # handled by dispatch_user_inputs_tool
    _impl.__doc__ = _OCR_REGIONS_DOC
    return tool("ocr_regions")(_impl)


USER_INPUTS_TOOL_NAMES = {
    "list_input_files",
    "read_input_text",
    "read_image_notes",
    "load_input_images",
    "ocr_regions",
}


def build_user_inputs_tools(
    agent_key: str, include_image_tools: bool = True
) -> list:
    """Return the user-inputs tool objects to bind to *agent_key*.

    Built fresh (not a static list) so the OCR-dependent tools/flags
    appear ONLY when OCR is enabled **for this agent** — when OCR is off
    (globally OR for this agent via the per-agent toggle) the agent
    never sees the ``extract_text`` flag NOR the ``ocr_regions`` tool.
    The gate is ``ocr_access.is_enabled_for(agent_key)`` (master
    ``OCR_ENABLED`` AND the per-agent flag), read as of that session's
    build.  ``list_input_files`` / ``read_input_text`` /
    ``read_image_notes`` are static (OCR does not touch them).

    When *include_image_tools* is False the agent gets ONLY the text-file
    tools (``list_input_files`` / ``read_input_text``); the image-viewing
    tools (``read_image_notes`` / ``load_input_images`` / ``ocr_regions``)
    are withheld.  The DC Input Creator uses this — it works from
    ``extracted_inputs.txt`` and does not view raw images.
    """
    tools = [list_input_files, read_input_text]
    if include_image_tools:
        on = ocr_access.is_enabled_for(agent_key)
        tools.append(read_image_notes)
        tools.append(_build_load_input_images(on))
        if on:
            # The region zoom-in tool exists only when OCR is enabled.
            tools.append(_build_ocr_regions())
    return tools


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


@generic_tool("Load input images")
def _handle_load_input_images(agent, tc: dict, agent_key: str) -> None:
    raw_paths = (tc.get("args", {}) or {}).get("paths")
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    if not isinstance(raw_paths, list) or not raw_paths:
        summary = (
            "Error: 'paths' must be a non-empty list of absolute image "
            "paths.  Discover valid paths via list_input_files."
        )
        log_tool_call(agent_key, tc["name"], tc.get("args"), summary)
        agent.messages.append(ToolMessage(
            content=summary,
            tool_call_id=tc["id"],
            name=tc["name"],
        ))
        return

    loaded: list[str] = []
    missing: list[str] = []
    image_blocks: list[dict] = []
    image_paths: list[str] = []
    provider = getattr(agent, "provider", "openai")

    for raw in raw_paths:
        if not isinstance(raw, str):
            missing.append(str(raw))
            continue
        path = Path(raw)
        if not _is_inside_inputs(path):
            missing.append(f"{raw} (not under inputs/)")
            continue
        if not path.is_file() or path.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
            missing.append(f"{raw} (missing or unsupported suffix)")
            continue
        try:
            b64 = encode_image(path)
            image_blocks.append(make_image_block(b64, provider))
            image_paths.append(str(path.resolve()))
            loaded.append(str(path.resolve()))
        except OSError as exc:
            missing.append(f"{raw} (read error: {exc})")

    parts = [f"Loaded {len(loaded)} user input image(s)."]
    if loaded:
        parts.append("Loaded paths:\n  " + "\n  ".join(loaded))
    if missing:
        parts.append(
            "Missing / invalid paths:\n  " + "\n  ".join(missing)
        )
    if image_blocks:
        parts.append(
            "The loaded images are attached in the next user message, "
            "each preceded by its absolute path so the path remains in "
            "history even if image bytes are later stripped."
        )
    else:
        parts.append("No images were loaded.  Do not retry with guessed paths.")

    # OCR pass (gated): read any text written on the loaded images and
    # append it to THIS ToolMessage via the shared OCR entry point.  The
    # shared function no-ops when OCR is disabled or not requested, and
    # is non-fatal on any engine error.  Default of the per-call
    # ``extract_text`` flag follows OCR_WHOLE_IMAGE_DEFAULT.  See
    # extra_utilities/OCR_technology_notes.md.
    args = tc.get("args", {}) or {}
    extract_text = bool(
        args.get(
            "extract_text",
            getattr(workflow_settings, "OCR_WHOLE_IMAGE_DEFAULT", True),
        )
    )
    parts.extend(ocr_summary_if_enabled([(p, p) for p in loaded], extract_text))

    summary = "\n".join(parts)

    log_tool_call(agent_key, tc["name"], tc.get("args"), summary)
    agent.messages.append(ToolMessage(
        content=summary,
        tool_call_id=tc["id"],
        name=tc["name"],
    ))
    if image_blocks:
        # Buffer instead of appending HumanMessage immediately, so that
        # if the LLM batched another tool_call alongside this one, the
        # contiguity rule (every tool_use → tool_result before any
        # other content) is preserved.  The agent's _run_llm_loop
        # flushes the buffer once all ToolMessages are appended.
        append_pending_images(agent, image_blocks, image_paths)


@generic_tool("Read text regions (OCR)")
def _handle_ocr_regions(agent, tc: dict, agent_key: str) -> None:
    """Re-OCR one or more regions of a user image at higher resolution in
    a single call.  Validates the path + region_ids, delegates the shared
    (single) detection + per-region crop/re-read to the engine, and
    attaches one zoomed crop per region ONLY when crop-attachment is
    enabled for this agent (else returns the higher-res re-read text
    only).  Non-fatal throughout — invalid region ids are reported inline
    without aborting the valid ones."""
    args = tc.get("args", {}) or {}
    raw_path = args.get("image_path")
    raw_regions = args.get("region_ids")

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

    # Accept a list of region numbers; forgivingly coerce a bare int/str.
    if isinstance(raw_regions, (int, str)):
        raw_regions = [raw_regions]
    if not isinstance(raw_regions, (list, tuple)) or not raw_regions:
        _err(
            "Error: 'region_ids' must be a non-empty list of integer "
            "region numbers from the image's OCR output (e.g. [2, 5, 7])."
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
            f"Error: 'region_ids' had no valid integer region numbers "
            f"(got {raw_regions!r})."
        )
        return

    result = ocr_regions_reread(str(path.resolve()), region_ids)

    # Whole-call failure (engine/PIL import, bad image, detection): stop.
    if not result.get("ok"):
        _err(
            f"Could not re-read regions on {path.name}: "
            f"{result.get('error')}."
        )
        return

    crops_on = ocr_region_crops_access.is_enabled_for(agent_key)
    results = result.get("results") or []
    invalid = result.get("invalid") or []
    n_ok = sum(1 for r in results if r.get("ok"))

    # Denominator = the de-duplicated, VALID regions actually attempted
    # (``results``), not the raw request list — duplicates are silently
    # collapsed and out-of-range ids are listed separately below.
    parts: list[str] = [
        f"Re-read {n_ok} of {len(results)} region(s) on {path.name} at "
        f"higher resolution — machine-read, so check each value:"
    ]
    crop_blocks: list[dict] = []
    crop_labels: list[str] = []
    for r in results:
        rid = r.get("region_id")
        if r.get("ok"):
            reread = (r.get("reread_text") or "").strip()
            line = f"  [region {rid}] {reread or '(no text detected)'}"
            if r.get("original_text"):
                line += f"   (whole-image OCR: {r['original_text']!r})"
            parts.append(line)
            if crops_on and r.get("crop_png"):
                b64 = base64.b64encode(r["crop_png"]).decode()
                crop_blocks.append(make_image_block(
                    b64, getattr(agent, "provider", "openai")
                ))
                crop_labels.append(f"{path.resolve()} (region {rid} zoom)")
        else:
            parts.append(
                f"  [region {rid}] could not re-read: {r.get('error')}"
            )
    for inv in invalid:
        parts.append(
            f"  Invalid: region {inv.get('region_id')} — {inv.get('error')}"
        )
    if bad_ids:
        parts.append(
            "  Ignored non-integer region id(s): " + ", ".join(bad_ids)
        )
    if crop_blocks:
        parts.append(
            f"The {len(crop_blocks)} zoomed crop(s) are attached in the next "
            f"user message, one per region (labelled by region) — verify "
            f"each value against its crop."
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
    "load_input_images": _handle_load_input_images,
    "ocr_regions":       _handle_ocr_regions,
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
