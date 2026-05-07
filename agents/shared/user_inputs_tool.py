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

import logging
from pathlib import Path

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool

from agents.shared.file_utils import (
    append_pending_images,
    list_files,
    load_text_file,
    pair_input_images,
)
from agents.shared.llm_provider import encode_image, make_image_block
from agents.shared.routing_tools import log_tool_call
from config import INPUT_IMAGES_DIR, INPUT_IMAGES_SUBDIR, USER_INPUTS_DIR

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


@tool
def load_input_images(paths: list[str]) -> str:
    """Load one or more user-supplied images so you can see them.

    ``paths`` MUST be a list of absolute paths obtained from
    ``list_input_files`` (or relayed in the hand-off message).  Each
    path must point at a ``.png``, ``.jpg``, or ``.jpeg`` inside
    ``inputs/input_images/``.  Loaded images are attached in the next
    user message, each preceded by its absolute path so the path
    remains in your history even if image bytes are later stripped.
    Do NOT call this tool with guessed or fabricated paths."""
    return ""  # handled by dispatch_user_inputs_tool


USER_INPUTS_TOOLS = [
    list_input_files,
    read_input_text,
    read_image_notes,
    load_input_images,
]
USER_INPUTS_TOOL_NAMES = {t.name for t in USER_INPUTS_TOOLS}


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


def _handle_list_input_files(agent, tc: dict, agent_key: str) -> None:
    summary = _format_input_files_listing()
    log_tool_call(agent_key, tc["name"], tc.get("args"), summary)
    agent.messages.append(ToolMessage(
        content=summary,
        tool_call_id=tc["id"],
        name=tc["name"],
    ))


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


def _handle_read_image_notes(agent, tc: dict, agent_key: str) -> None:
    summary = _format_image_notes()
    log_tool_call(agent_key, tc["name"], tc.get("args"), summary)
    agent.messages.append(ToolMessage(
        content=summary,
        tool_call_id=tc["id"],
        name=tc["name"],
    ))


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


_HANDLERS = {
    "list_input_files":  _handle_list_input_files,
    "read_input_text":   _handle_read_input_text,
    "read_image_notes":  _handle_read_image_notes,
    "load_input_images": _handle_load_input_images,
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
