"""Shared file-loading utilities for agents.

Every agent can use these functions to load text, JSON, and image files
from anywhere in the project directory.

Image-loading is provider-aware: pass the agent's LLM provider tag
(``"openai"`` / ``"anthropic"`` / ``"google"``) so the resulting
content blocks match the bound model's expectations.
"""

import json
from pathlib import Path

from agents.shared.llm_provider import encode_image, make_image_block

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".log"}
JSON_EXTENSIONS = {".json"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


def ai_text(content) -> str:
    """Return the text portion of an AIMessage ``content`` field.

    Anthropic / some LangChain integrations set ``content`` to a list of
    content blocks when the model emits both text and structured
    tool_use in the same turn.  Naively calling ``str(content)`` on
    such a list produces a Python ``repr`` — garbage for downstream
    text parsing.  This helper returns the concatenated ``text`` of
    every text block (or the string itself when ``content`` is already
    a plain ``str``).
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def categorise_file(path: Path) -> str:
    """Return 'text', 'json', 'image', or 'unknown' for a file."""
    ext = path.suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return "text"
    if ext in JSON_EXTENSIONS:
        return "json"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return "unknown"


def list_files(directory: Path) -> list[dict]:
    """List and categorise every file in *directory* (non-recursive)."""
    if not directory.is_dir():
        return []
    result = []
    for p in sorted(directory.iterdir()):
        if p.is_file():
            result.append({
                "name": p.name,
                "path": str(p.resolve()),
                "category": categorise_file(p),
                "extension": p.suffix.lower(),
            })
    return result


def load_text_file(path: Path) -> str:
    """Read a text file and return its content."""
    return path.read_text(encoding="utf-8")


def load_json_file(path: Path) -> dict:
    """Read a JSON file and return its content as a dict."""
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------
# High-level loaders
# ------------------------------------------------------------------

def load_all_inputs(directory: Path, provider: str) -> dict:
    """Load all input files from a directory.

    ``provider`` is the LLM provider tag of the agent that will see
    the loaded blocks (used to build provider-correct image content
    blocks).

    Returns
    -------
    dict with keys:
        text_content  : str        -- all text files concatenated
        json_data     : list[dict] -- parsed JSON files
        image_blocks  : list[dict] -- LLM-ready image content blocks
        image_paths   : list[str]  -- absolute paths parallel to
                                      ``image_blocks`` (same length,
                                      same order); used by callers
                                      that pair each image with a
                                      path-text block in history
        file_list     : list[dict] -- metadata for every file
        summary       : str        -- human-readable one-liner
    """
    files = list_files(directory)
    text_parts: list[str] = []
    json_data: list[dict] = []
    image_blocks: list[dict] = []
    image_paths: list[str] = []

    for f in files:
        p = Path(f["path"])
        cat = f["category"]
        try:
            if cat == "text":
                content = load_text_file(p)
                text_parts.append(f"--- {f['name']} ---\n{content}")
            elif cat == "json":
                data = load_json_file(p)
                json_data.append({"file": f["name"], "data": data})
                text_parts.append(
                    f"--- {f['name']} ---\n{json.dumps(data, indent=2)}"
                )
            elif cat == "image":
                b64 = encode_image(p)
                image_blocks.append(make_image_block(b64, provider))
                image_paths.append(str(p.resolve()))
        except Exception:
            text_parts.append(f"--- {f['name']} --- (failed to load)")

    return {
        "text_content": "\n\n".join(text_parts) if text_parts else "",
        "json_data": json_data,
        "image_blocks": image_blocks,
        "image_paths": image_paths,
        "file_list": files,
        "summary": summarise_files(files),
    }


_NOTE_SUFFIX = "_note.txt"
USER_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")


def pair_input_images(images_dir: Path) -> dict:
    """Match every user-supplied image in *images_dir* with its ``<name>_note.txt``.

    Returns a dict with:
        pairs           : list[(image_path: Path, note_path: Path)]
        orphan_images   : list[Path] — images with no matching _note.txt
        orphan_notes    : list[Path] — _note.txt files with no matching image
        duplicate_stems : list[(stem, [Path, ...])] — same-stem images
                                                      across formats
        ok              : bool      — True iff there are no orphans or
                                      duplicate stems
        report          : str       — human-readable summary string,
                                      empty when there are no images
                                      and no notes (i.e. nothing to report)

    Image stem matching is case-insensitive (so ``Image1.png`` pairs
    with ``image1_note.txt``).  Image extensions accepted: ``.png``,
    ``.jpg``, and ``.jpeg``.  If two images share a stem across formats
    (e.g. ``image1.png`` AND ``image1.jpg``), they are reported as a
    duplicate-stem pairing failure rather than silently picking one.
    """
    if not images_dir.is_dir():
        return {
            "pairs": [],
            "orphan_images": [],
            "orphan_notes": [],
            "duplicate_stems": [],
            "ok": True,
            "report": "",
        }
    images: dict[str, Path] = {}
    duplicate_stems: dict[str, list[Path]] = {}
    notes: dict[str, Path] = {}
    for entry in sorted(images_dir.iterdir()):
        if not entry.is_file():
            continue
        lname = entry.name.lower()
        if lname.endswith(_NOTE_SUFFIX):
            stem = entry.name[: -len(_NOTE_SUFFIX)].lower()
            notes[stem] = entry
            continue
        if entry.suffix.lower() in USER_IMAGE_SUFFIXES:
            stem = entry.stem.lower()
            if stem in images:
                duplicate_stems.setdefault(stem, [images[stem]]).append(entry)
            else:
                images[stem] = entry

    # Remove duplicates from the primary dict so they aren't paired below.
    for stem in duplicate_stems:
        images.pop(stem, None)

    pairs: list[tuple[Path, Path]] = []
    orphan_images: list[Path] = []
    orphan_notes: list[Path] = []
    for stem, img in images.items():
        note = notes.get(stem)
        if note is None:
            orphan_images.append(img)
        else:
            pairs.append((img, note))
    for stem, note in notes.items():
        if stem not in images and stem not in duplicate_stems:
            orphan_notes.append(note)

    duplicate_list = [(stem, paths) for stem, paths in duplicate_stems.items()]
    ok = not orphan_images and not orphan_notes and not duplicate_list
    if not images and not notes and not duplicate_list:
        report = ""
    else:
        lines = []
        if pairs:
            lines.append(
                f"{len(pairs)} valid image+note pair(s):"
            )
            for img, note in pairs:
                lines.append(f"  - {img.name}  +  {note.name}")
        if orphan_images:
            lines.append(
                f"{len(orphan_images)} image(s) with NO matching "
                f"_note.txt (each <name>.png/.jpg/.jpeg MUST have "
                f"<name>_note.txt):"
            )
            for img in orphan_images:
                lines.append(
                    f"  - {img.name}  (expected {img.stem}_note.txt)"
                )
        if orphan_notes:
            lines.append(
                f"{len(orphan_notes)} _note.txt file(s) with NO matching "
                f"image (each <name>_note.txt MUST have a "
                f"<name>.png/.jpg/.jpeg image):"
            )
            for note in orphan_notes:
                stem = note.name[: -len(_NOTE_SUFFIX)]
                lines.append(
                    f"  - {note.name}  (expected {stem}.png, {stem}.jpg, "
                    f"or {stem}.jpeg)"
                )
        if duplicate_list:
            lines.append(
                f"{len(duplicate_list)} stem(s) used by more than one "
                f"image format (keep only one per stem):"
            )
            for stem, paths in duplicate_list:
                names = ", ".join(p.name for p in paths)
                lines.append(f"  - stem '{stem}': {names}")
        report = "\n".join(lines)
    return {
        "pairs": pairs,
        "orphan_images": orphan_images,
        "orphan_notes": orphan_notes,
        "duplicate_stems": duplicate_list,
        "ok": ok,
        "report": report,
    }


def load_user_inputs_bundle(
    inputs_dir: Path,
    provider: str,
    include_image_bytes: bool,
    images_subdir: str = "input_images",
) -> dict:
    """Load every user-supplied input under *inputs_dir* (text + images).

    Reads:
      * Every text / JSON file in the root of *inputs_dir* (e.g.
        ``user_query.txt``, ``extracted_inputs.txt``).
      * Every paired image + note in ``inputs_dir / images_subdir`` —
        both the note text and (when ``include_image_bytes`` is True)
        the image bytes as LLM-ready content blocks.
      * Records orphan images / notes into ``pairing`` so the
        Receptionist can refuse the cycle.

    Parameters
    ----------
    inputs_dir
        Root inputs folder (typically ``USER_INPUTS_DIR``).
    provider
        LLM provider tag of the agent that will see the loaded blocks
        (used to build provider-correct image content blocks).
    include_image_bytes
        When True, return paired images as LLM-ready ``image_blocks``
        + ``image_paths``.  When False, return image *paths* and *note
        text* only — used by agents that should know what was uploaded
        without ingesting the image bytes themselves (Receptionist).

    Returns a dict with:
        text_content    : str         -- root text/JSON + paired notes,
                                          each section labelled with
                                          its source filename
        image_blocks    : list[dict]  -- paired images (only when
                                          ``include_image_bytes``)
        image_paths     : list[str]   -- absolute paths parallel to
                                          ``image_blocks`` (or, when
                                          bytes are excluded, the paths
                                          of every paired image)
        note_pairs      : list[(image_name, note_name, note_text)]
                                       -- paired notes (loaded
                                          regardless of
                                          ``include_image_bytes``)
        pairing         : dict        -- result of ``pair_input_images``
                                          for the images subfolder
        root_files      : list[dict]  -- categorised root file list
        summary         : str         -- one-line human-readable summary
    """
    root_files = list_files(inputs_dir)
    text_parts: list[str] = []
    for f in root_files:
        p = Path(f["path"])
        cat = f["category"]
        try:
            if cat == "text":
                text_parts.append(
                    f"--- {f['name']} ---\n{load_text_file(p)}"
                )
            elif cat == "json":
                data = load_json_file(p)
                text_parts.append(
                    f"--- {f['name']} ---\n"
                    f"{json.dumps(data, indent=2)}"
                )
        except Exception:
            text_parts.append(f"--- {f['name']} --- (failed to load)")

    images_dir = inputs_dir / images_subdir
    pairing = pair_input_images(images_dir)
    note_pairs: list[tuple[str, str, str]] = []
    image_blocks: list[dict] = []
    image_paths: list[str] = []

    for img_path, note_path in pairing["pairs"]:
        try:
            note_text = load_text_file(note_path)
        except Exception as exc:
            note_text = f"(failed to read: {exc})"
        note_pairs.append((img_path.name, note_path.name, note_text))
        text_parts.append(
            f"--- {images_subdir}/{note_path.name} "
            f"(describes image {img_path.name}) ---\n{note_text}"
        )
        if include_image_bytes:
            try:
                b64 = encode_image(img_path)
                image_blocks.append(make_image_block(b64, provider))
                image_paths.append(str(img_path.resolve()))
            except Exception:
                text_parts.append(
                    f"--- {images_subdir}/{img_path.name} --- "
                    f"(failed to load image bytes)"
                )
        else:
            image_paths.append(str(img_path.resolve()))

    if pairing["report"]:
        text_parts.append(
            f"--- {images_subdir}/ pairing report ---\n"
            f"{pairing['report']}"
        )

    summary_bits: list[str] = []
    if root_files:
        cats: dict[str, list[str]] = {}
        for f in root_files:
            cats.setdefault(f["category"], []).append(f["name"])
        summary_bits.append(
            "; ".join(f"{cat}: {', '.join(names)}" for cat, names in cats.items())
        )
    n_pairs = len(pairing["pairs"])
    if n_pairs:
        summary_bits.append(
            f"{n_pairs} paired image+note in {images_subdir}/"
        )
    if pairing["orphan_images"] or pairing["orphan_notes"]:
        summary_bits.append(
            f"{len(pairing['orphan_images'])} orphan image(s), "
            f"{len(pairing['orphan_notes'])} orphan note(s) in "
            f"{images_subdir}/ (pairing INVALID)"
        )
    if not summary_bits:
        summary = "No input files found."
    else:
        summary = " | ".join(summary_bits)

    return {
        "text_content": "\n\n".join(text_parts) if text_parts else "",
        "image_blocks": image_blocks,
        "image_paths": image_paths,
        "note_pairs": note_pairs,
        "pairing": pairing,
        "root_files": root_files,
        "summary": summary,
    }


def summarise_files(files: list[dict]) -> str:
    """One-line summary of available file types and names."""
    if not files:
        return "No files found."
    cats: dict[str, list[str]] = {}
    for f in files:
        cats.setdefault(f["category"], []).append(f["name"])
    parts = []
    for cat, names in cats.items():
        parts.append(f"{cat}: {', '.join(names)}")
    return "; ".join(parts)


def build_multimodal_content(
    text: str,
    image_blocks: list[dict],
    image_paths: list[str] | None = None,
) -> list[dict] | str:
    """Build a LangChain-compatible content value.

    If there are images, returns a list of content blocks (text first,
    then for each image a ``Loaded image (path: …):`` text block
    immediately followed by the image block — provided ``image_paths``
    is supplied and parallel to ``image_blocks``).  When ``image_paths``
    is omitted or empty the images are appended unpaired (legacy
    behaviour).  When there are no images the plain text string is
    returned.

    Pairing matters because it keeps the image's source path visible
    to the LLM alongside the bytes — and because it's the record that
    survives image-block stripping when the "keep images in context"
    option is OFF.
    """
    if not image_blocks:
        return text
    blocks: list[dict] = [{"type": "text", "text": text}]
    if image_paths and len(image_paths) == len(image_blocks):
        for img, p in zip(image_blocks, image_paths):
            blocks.append({"type": "text", "text": f"Loaded image (path: {p}):"})
            blocks.append(img)
    else:
        blocks.extend(image_blocks)
    return blocks


def build_paired_image_blocks(
    image_blocks: list[dict],
    image_paths: list[str],
) -> list[dict]:
    """Return ``[path-text, image, path-text, image, …]`` for a HumanMessage.

    Use this when you want the image content blocks alone (no leading
    summary text) — e.g. DC Output Inspector and User Input Inspector
    each append a separate ``HumanMessage`` of just the loaded images
    after their tool-call summary.  Pairs each image with a preceding
    ``Loaded image (path: <p>):`` text block so the path remains in
    history even when the image bytes are later stripped (KEEP IMAGES
    OFF mode).

    ``image_paths`` MUST be the same length as ``image_blocks``.
    """
    if len(image_blocks) != len(image_paths):
        raise ValueError(
            f"image_blocks ({len(image_blocks)}) and image_paths "
            f"({len(image_paths)}) must be the same length"
        )
    out: list[dict] = []
    for img, p in zip(image_blocks, image_paths):
        out.append({"type": "text", "text": f"Loaded image (path: {p}):"})
        out.append(img)
    return out


# ---------------------------------------------------------------------------
# Per-turn image buffer — preserves Anthropic / OpenAI tool-call contiguity
# ---------------------------------------------------------------------------
# When an image-loading tool call returns, the natural shape is:
#
#     ToolMessage(tool_call_id=A, content="loaded N images")
#     HumanMessage(content=[image bytes...])
#
# That works fine when the LLM emitted a single tool_call.  But when
# the LLM batches multiple tool_calls in one ``AIMessage`` (e.g.
# ``load_render_images`` + ``read_input_text`` in the same response —
# Claude Opus does this routinely), appending the HumanMessage
# immediately after the first ToolMessage breaks the API's contiguity
# requirement: every ``tool_use`` block in an assistant message MUST
# be followed by a contiguous run of ``tool_result`` blocks before any
# other content can appear.  Anthropic returns HTTP 400 with
# ``tool_use ids were found without tool_result blocks immediately
# after``; OpenAI returns HTTP 400 with ``tool_calls must be followed
# by tool messages``.
#
# Solution: every image-loading handler appends its image content
# blocks to a per-agent BUFFER (``agent._pending_image_blocks`` /
# ``agent._pending_image_paths``) instead of appending a HumanMessage
# directly.  The agent's ``_run_llm_loop`` then calls
# ``flush_pending_image_blocks(self)`` AFTER its inner
# ``for tc in response.tool_calls:`` loop has appended every
# ToolMessage for the current AIMessage.  The result is a uniform
# message shape:
#
#     AIMessage(tool_calls=[A, B, C])
#     ToolMessage(A)
#     ToolMessage(B)
#     ToolMessage(C)
#     HumanMessage(image bytes for any of A/B/C that loaded images)
#
# Both Anthropic and OpenAI accept this shape regardless of how many
# tool_calls were batched together.

def append_pending_images(
    agent,
    image_blocks: list[dict],
    image_paths: list[str],
) -> None:
    """Append loaded image content blocks to the agent's per-turn buffer.

    Use this from inside an image-loading tool handler instead of
    appending a ``HumanMessage`` directly.  ``image_blocks`` and
    ``image_paths`` MUST be the same length and ordered correspondingly.

    The buffer is created lazily on first use, so agents do not have
    to declare it in their ``__init__`` — though declaring it there
    keeps the type clear at a glance.
    """
    if len(image_blocks) != len(image_paths):
        raise ValueError(
            f"image_blocks ({len(image_blocks)}) and image_paths "
            f"({len(image_paths)}) must be the same length"
        )
    if not hasattr(agent, "_pending_image_blocks"):
        agent._pending_image_blocks = []
        agent._pending_image_paths = []
    agent._pending_image_blocks.extend(image_blocks)
    agent._pending_image_paths.extend(image_paths)


def flush_pending_image_blocks(agent) -> int:
    """Flush the agent's pending image blocks as a single ``HumanMessage``.

    Call AFTER the full ``for tc in response.tool_calls:`` loop has
    completed (whether the loop broke early on a routing-tool match or
    ran to completion is irrelevant — flushing is always safe and
    keeps the message history valid for any subsequent re-entry of
    the same agent).

    No-op when the buffer is empty.  Returns the number of image
    blocks flushed (for logging / debugging — most callers ignore
    the return value).
    """
    blocks = getattr(agent, "_pending_image_blocks", None)
    paths = getattr(agent, "_pending_image_paths", None)
    if not blocks:
        return 0
    # Local import to avoid a circular dependency: file_utils is loaded
    # very early in the agents package and HumanMessage import here
    # would otherwise drag the entire langchain_core message stack into
    # this module's import-time graph.
    from langchain_core.messages import HumanMessage
    agent.messages.append(HumanMessage(
        content=build_paired_image_blocks(blocks, paths),
    ))
    n = len(blocks)
    agent._pending_image_blocks = []
    agent._pending_image_paths = []
    return n


_IMAGE_BLOCK_TYPES = {"image", "image_url"}


def strip_image_blocks_from_messages(messages: list) -> int:
    """Remove every image content block from every message's content.

    Walks ``messages`` (typically an agent's ``self.messages``) and,
    for each one whose ``content`` is a list of blocks, drops every
    block whose ``type`` is ``"image"`` or ``"image_url"``.  Paired
    ``Loaded image (path: …):`` text blocks are left in place — they
    remain as a path-only record of which images the agent had loaded.

    Returns the number of image blocks removed.
    """
    removed = 0
    for m in messages:
        content = getattr(m, "content", None)
        if not isinstance(content, list):
            continue
        new_blocks: list = []
        msg_removed = 0
        for blk in content:
            if (
                isinstance(blk, dict)
                and blk.get("type") in _IMAGE_BLOCK_TYPES
            ):
                msg_removed += 1
                continue
            new_blocks.append(blk)
        if msg_removed:
            try:
                m.content = new_blocks
            except (AttributeError, ValueError):
                # Defensive: if the message object is frozen for any
                # reason, skip it rather than crash the dispatcher.
                pass
            removed += msg_removed
    return removed
