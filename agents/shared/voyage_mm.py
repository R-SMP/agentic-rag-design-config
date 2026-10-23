"""Voyage multimodal embedding client for the multimodal `chunks_mm` table.

This is the DEDICATED client for the database layer.  The Embedding-tests
harness (removed 2026-10-10, see ``extra_utilities/extra_info.md`` §13)
had its own client, hardcoded to ``voyage-multimodal-3`` @ 1024 dims and
single-modality; the two were deliberately never merged.

What this client does
---------------------
Embeds TEXT, IMAGES, or FUSED image+text into a single
voyage-multimodal-3.5 vector.  All three live in the same embedding
space, so cosine similarity is meaningful across them (CLIP-style
cross-modal retrieval).

The model is reached through OpenRouter's embeddings endpoint (since
2026-10-23; before that, Voyage's own ``voyageai`` SDK).  Checked side
by side on 2026-10-23: text, image and image+text, as document and as
query, give the same vectors as Voyage directly (cosine >= 0.9996), so
the rows already stored stay searchable and keep their
``embedding_model`` string.

Locked parameters (architecture doc §6.3; currently non-modifiable in
the UI — see the Database options panel):

  * model            = ``voyage-multimodal-3.5`` (OpenRouter's
                       ``voyageai/voyage-multimodal-3.5``)
  * output_dimension = 2048  (Voyage's max; stored as ``vector(2048)``)
  * input_type       = ``document`` for stored corpus rows, and
                       ``query`` for a search's query vector -- wired
                       via ``as_query=True`` in database_search.py
  * max image side   = 1536 px (resize-before-send; preserves fine
                       sketch annotations better than the harness's
                       1024 while bounding pixel-token cost)
  * image encoding   = lossless WebP data URI (what the ``voyageai``
                       SDK sent, so the vectors match the stored ones)
  * call mode        = single-item (one input per request) — per-item
                       error isolation for the one-time backfill
  * embedding_model string = ``voyage/voyage-multimodal-3.5/2048``

Image+text fusion is the primary path for image rows: a user image is
fused with its ``_note.txt``; a render is fused with the attempt's
``description.txt``.  When the associated text is missing the caller
falls back to image-only (``embed_image``).  See TODO_known_issues.md
F37 for the rationale on NOT adding a VLM-generated caption.

Requires ``OPENROUTER_API_KEY`` in the environment (the same key the
OpenRouter LLM provider uses).
"""

from __future__ import annotations

import base64
import io
import logging
import os
import time
from pathlib import Path
from typing import Any, Union

import requests
from PIL import Image

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Locked parameters
# --------------------------------------------------------------------------
VOYAGE_MM_MODEL: str = "voyage-multimodal-3.5"
VOYAGE_MM_DIMS: int = 2048
MAX_IMAGE_SIDE: int = 1536

_INPUT_TYPE_DOCUMENT: str = "document"
_INPUT_TYPE_QUERY: str = "query"

_DEFAULT_RETRIES: int = 3
_BACKOFF_BASE_SECONDS: float = 2.0

_OPENROUTER_URL: str = "https://openrouter.ai/api/v1/embeddings"
_OPENROUTER_MODEL: str = f"voyageai/{VOYAGE_MM_MODEL}"
_TIMEOUT_SECONDS: float = 60.0

ImageSource = Union[Image.Image, bytes, bytearray, str, Path]


def embedding_model_string() -> str:
    """The value written to ``chunks_mm.embedding_model``."""
    return f"voyage/{VOYAGE_MM_MODEL}/{VOYAGE_MM_DIMS}"


def _api_key() -> str:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set — cannot embed with "
            "voyage-multimodal-3.5 (reached through OpenRouter).  Set it "
            "locally in .env or in the Railway dashboard Variables."
        )
    return api_key


# --------------------------------------------------------------------------
# Image preprocessing
# --------------------------------------------------------------------------
def _open_image(src: ImageSource) -> Image.Image:
    """Load `src` (PIL image / bytes / path) → RGB, resized to MAX_IMAGE_SIDE.

    ``thumbnail`` preserves aspect ratio and only ever shrinks, so small
    sketches are left untouched while large phone photos are bounded.
    """
    if isinstance(src, Image.Image):
        im = src
    elif isinstance(src, (bytes, bytearray)):
        im = Image.open(io.BytesIO(bytes(src)))
    elif isinstance(src, (str, Path)):
        im = Image.open(Path(src))
    else:  # pragma: no cover - defensive
        raise TypeError(f"Unsupported image source type: {type(src)!r}")

    im = im.convert("RGB")
    im.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    return im


def _text_part(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _image_part(im: Image.Image) -> dict[str, Any]:
    """An image as OpenRouter's ``image_url`` part: a lossless WebP data URI."""
    buf = io.BytesIO()
    im.save(buf, format="WEBP", lossless=True)
    uri = "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": uri}}


# --------------------------------------------------------------------------
# Core embed call (single-item, with retry/backoff)
# --------------------------------------------------------------------------
def _embed_one(parts: list[dict[str, Any]], *, input_type: str) -> list[float]:
    """Embed ONE document made of `parts` (text and image parts, in order).

    Retries transient failures with exponential backoff.  Validates the
    returned vector length against ``VOYAGE_MM_DIMS`` so a model or
    endpoint mismatch fails loudly rather than silently storing a
    wrong-dim vector.
    """
    api_key = _api_key()
    body = {
        "model": _OPENROUTER_MODEL,
        "input": [{"content": parts}],
        "dimensions": VOYAGE_MM_DIMS,
        "input_type": input_type,
        "encoding_format": "float",
    }
    last_exc: Exception | None = None
    for attempt in range(_DEFAULT_RETRIES):
        try:
            response = requests.post(
                _OPENROUTER_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
                timeout=_TIMEOUT_SECONDS,
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"OpenRouter embeddings answered HTTP "
                    f"{response.status_code}: {response.text[:300]}"
                )
            try:
                vector = list(response.json()["data"][0]["embedding"])
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                # not the dimension check's ValueError: this one is retried
                raise RuntimeError(
                    f"OpenRouter embeddings answered without a vector: "
                    f"{response.text[:300]}"
                ) from exc
            if len(vector) != VOYAGE_MM_DIMS:
                raise ValueError(
                    f"voyage-multimodal-3.5 returned {len(vector)} dims, "
                    f"expected {VOYAGE_MM_DIMS}.  Check that OpenRouter "
                    f"still passes `dimensions` on to this model."
                )
            return vector
        except ValueError:
            # Dimension mismatch is a hard error — do not retry.
            raise
        except Exception as exc:  # noqa: BLE001 — transient API/network errors
            last_exc = exc
            if attempt == _DEFAULT_RETRIES - 1:
                break
            backoff = _BACKOFF_BASE_SECONDS * (2 ** attempt)
            logger.warning(
                "[voyage_mm] embed attempt %d/%d failed (%s: %s); "
                "retrying in %.1fs",
                attempt + 1, _DEFAULT_RETRIES, type(exc).__name__, exc,
                backoff,
            )
            time.sleep(backoff)
    assert last_exc is not None
    raise last_exc


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def embed_text(text: str, *, as_query: bool = False) -> list[float]:
    """Embed a text string → 2048-float vector.

    Used to re-embed the stored stitched paragraph for text rows.
    """
    input_type = _INPUT_TYPE_QUERY if as_query else _INPUT_TYPE_DOCUMENT
    return _embed_one([_text_part(text)], input_type=input_type)


def embed_image(image: ImageSource, *, as_query: bool = False) -> list[float]:
    """Embed an image alone → 2048-float vector.

    The image-only fallback used when an image has no associated text.
    """
    im = _open_image(image)
    input_type = _INPUT_TYPE_QUERY if as_query else _INPUT_TYPE_DOCUMENT
    return _embed_one([_image_part(im)], input_type=input_type)


def embed_fused(
    text: str, image: ImageSource, *, as_query: bool = False
) -> list[float]:
    """Embed image + text fused into ONE 2048-float vector.

    The PRIMARY path for image rows: text first, then image (Voyage
    accepts interleaved content in a single input).  See F37 for why the
    fused text is the user's note / chain's description, not a VLM
    caption.
    """
    im = _open_image(image)
    input_type = _INPUT_TYPE_QUERY if as_query else _INPUT_TYPE_DOCUMENT
    return _embed_one([_text_part(text), _image_part(im)], input_type=input_type)
