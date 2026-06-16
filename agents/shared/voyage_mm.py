"""Voyage multimodal embedding client for the multimodal `chunks_mm` table.

This is the DEDICATED client for the database layer.  It is SEPARATE
from the embedding-tests harness client
(``extra_utilities/embedding_tests/voyage_client.py``), which is
hardcoded to ``voyage-multimodal-3`` @ 1024 dims and single-modality,
and whose 35 stored vectors depend on those defaults.  Do NOT merge
the two — changing the harness client would invalidate its cached
vectors.

What this client does
---------------------
Embeds TEXT, IMAGES, or FUSED image+text into a single
voyage-multimodal-3.5 vector.  All three live in the same embedding
space, so cosine similarity is meaningful across them (CLIP-style
cross-modal retrieval).

Locked parameters (architecture doc §6.3; currently non-modifiable in
the UI — see the Database options panel):

  * model            = ``voyage-multimodal-3.5``
  * output_dimension = 2048  (Voyage's max; stored as ``vector(2048)``)
  * input_type       = ``document`` for stored corpus rows
                       (``query`` reserved for read time, not wired yet)
  * max image side   = 1536 px (resize-before-send; preserves fine
                       sketch annotations better than the harness's
                       1024 while bounding pixel-token cost)
  * call mode        = single-item (one input per request) — per-item
                       error isolation for the one-time backfill
  * embedding_model string = ``voyage/voyage-multimodal-3.5/2048``

Image+text fusion is the primary path for image rows: a user image is
fused with its ``_note.txt``; a render is fused with the attempt's
``description.txt``.  When the associated text is missing the caller
falls back to image-only (``embed_image``).  See TODO_known_issues.md
F37 for the rationale on NOT adding a VLM-generated caption.

Requires ``VOYAGE_API_KEY`` in the environment.  ``voyageai`` is a
``requirements-web.txt`` dependency (present on Railway; install it
into the local interpreter for local testing).
"""

from __future__ import annotations

import io
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Union

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

ImageSource = Union[Image.Image, bytes, bytearray, str, Path]


def embedding_model_string() -> str:
    """The value written to ``chunks_mm.embedding_model``."""
    return f"voyage/{VOYAGE_MM_MODEL}/{VOYAGE_MM_DIMS}"


# --------------------------------------------------------------------------
# Lazy singleton client
# --------------------------------------------------------------------------
_client: Any = None
_client_lock = threading.Lock()


def _get_client() -> Any:
    """Return a process-wide singleton ``voyageai.Client``.

    ``voyageai`` is imported lazily so merely importing this module does
    not hard-require the package in environments that never embed.
    """
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            api_key = os.environ.get("VOYAGE_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "VOYAGE_API_KEY is not set — cannot embed with "
                    "voyage-multimodal-3.5.  Set it locally in .env or "
                    "in the Railway dashboard Variables."
                )
            import voyageai  # lazy — keeps the import optional

            _client = voyageai.Client(api_key=api_key)
    return _client


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


# --------------------------------------------------------------------------
# Core embed call (single-item, with retry/backoff)
# --------------------------------------------------------------------------
def _embed_one(inputs: list[list[Any]], *, input_type: str) -> list[float]:
    """Embed ONE document (`inputs` must hold exactly one inner list).

    Retries transient failures with exponential backoff.  Validates the
    returned vector length against ``VOYAGE_MM_DIMS`` so an SDK/model
    mismatch fails loudly rather than silently storing a wrong-dim
    vector.
    """
    client = _get_client()
    last_exc: Exception | None = None
    for attempt in range(_DEFAULT_RETRIES):
        try:
            result = client.multimodal_embed(
                inputs=inputs,
                model=VOYAGE_MM_MODEL,
                input_type=input_type,
                output_dimension=VOYAGE_MM_DIMS,
            )
            vector = list(result.embeddings[0])
            if len(vector) != VOYAGE_MM_DIMS:
                raise ValueError(
                    f"voyage-multimodal-3.5 returned {len(vector)} dims, "
                    f"expected {VOYAGE_MM_DIMS}.  Check the installed "
                    f"voyageai SDK supports output_dimension for this model."
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
    return _embed_one([[text]], input_type=input_type)


def embed_image(image: ImageSource, *, as_query: bool = False) -> list[float]:
    """Embed an image alone → 2048-float vector.

    The image-only fallback used when an image has no associated text.
    """
    im = _open_image(image)
    input_type = _INPUT_TYPE_QUERY if as_query else _INPUT_TYPE_DOCUMENT
    return _embed_one([[im]], input_type=input_type)


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
    return _embed_one([[text, im]], input_type=input_type)
