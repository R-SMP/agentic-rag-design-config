"""Claude Sonnet VLM caption generator for the embedding-tests harness.

Calls the Anthropic API directly with an image attached, returning a
visual-style description OR a semantic-content description.  Both
flavours are used:

* At rebuild time (``rebuild_index``): per sketch, generate both
  descriptions; bake into ``embeddings.json``.
* At query time on the image-to-images path: caption the uploaded
  image with BOTH prompts, embed each via OpenAI, search the matching
  caption column.

This module is self-contained (does not import from ``agents/``) — the
harness is sandboxed per the user's scoping rule.

Requires
--------
* ``ANTHROPIC_API_KEY`` in the environment
* ``anthropic`` SDK (already a transitive dep via ``langchain-anthropic``)
"""
from __future__ import annotations

import base64
import io
import os
import threading
from pathlib import Path

CAPTION_MODEL     = "claude-sonnet-4-6"
MAX_OUTPUT_TOKENS = 900
# Resize to the same envelope as the Voyage path so the VLM sees an
# image close in size/quality to what gets stored.  Avoids the
# pathological 7.5 MB sketch dragging the API call out.
MAX_IMAGE_SIDE = 1024


VISUAL_PROMPT = (
    "Describe ONLY the VISUAL STYLE of this engineering sketch — NOT what "
    "it depicts.\n\n"
    "Cover: drawing medium (hand-drawn ink, pencil, marker, technical pen, "
    "digital, etc.); background (plain white, grid paper, gradient, dark); "
    "viewpoint (top-down, side elevation, isometric, 3D perspective, "
    "exploded); line style (solid, dashed, double-line, thin vs thick, "
    "freehand vs ruled); annotation style (typed labels, hand-written, "
    "dimension arrows, callout leaders, balloons); color palette "
    "(monochrome, two-tone, multi-color, sepia); composition (single panel, "
    "multi-panel with insets, grid of sub-views, full-bleed vs framed); "
    "grid or template (none, faint grid, prominent grid, dot-paper).\n\n"
    "DO NOT describe what the design is — no parameters, no geometry "
    "interpretation, no blade counts.  Be specific to THIS sketch's "
    "observable visual details.  Roughly 300-500 tokens.\n\n"
    "Return only the description text, no preamble or headings."
)


SEMANTIC_PROMPT = (
    "Describe ONLY WHAT THE DESIGN DEPICTS — NOT how it is drawn.\n\n"
    "Cover: blade count, blade arrangement (radial, axial, twisted), "
    "visible numerical dimensions and parameter values WITH UNITS "
    "(chord lengths in mm, pitch angles in degrees, diameters, ring "
    "thicknesses, ring heights); inner/middle/outer ring geometry; "
    "blade profile shape if discernible (airfoil, flat plate, twisted); "
    "presence of central hub or shaft; any text labels that name parts "
    "(e.g., 'Mid', 'Inner Ring', 'Outer Ring', 'Blade Center Line').\n\n"
    "Stay close to what is actually visible — if a number is unreadable "
    "or a feature absent, say so explicitly.  Roughly 300-500 tokens.\n\n"
    "Return only the description text, no preamble or headings."
)


_client_lock = threading.Lock()
_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        try:
            from anthropic import Anthropic  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "anthropic SDK not installed."
            ) from exc
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set in the environment."
            )
        # 180 s timeout mirrors agents/shared/llm_provider — the default
        # 600 s is too long for an interactive UI button.
        _client = Anthropic(api_key=api_key, timeout=180.0)
        return _client


def _image_to_base64(path: Path) -> tuple[str, str]:
    """Read an image, resize to ``MAX_IMAGE_SIDE``, return
    (media_type, base64-encoded PNG bytes).
    """
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        data = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    return ("image/png", data)


def _caption(image_path: Path, prompt: str) -> str:
    client = _get_client()
    media_type, b64 = _image_to_base64(Path(image_path))
    msg = client.messages.create(
        model=CAPTION_MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type":   "image",
                    "source": {
                        "type":       "base64",
                        "media_type": media_type,
                        "data":       b64,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )
    if not msg.content:
        return ""
    parts: list[str] = []
    for block in msg.content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts).strip()


def caption_visual(image_path: Path) -> str:
    """Generate the visual-style description for ``image_path``."""
    return _caption(image_path, VISUAL_PROMPT)


def caption_semantic(image_path: Path) -> str:
    """Generate the semantic-content description for ``image_path``."""
    return _caption(image_path, SEMANTIC_PROMPT)
