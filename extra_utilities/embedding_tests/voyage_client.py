"""Voyage AI multimodal-3 wrapper for the embedding-tests harness.

Thin layer over the ``voyageai`` SDK.  Provides two functions:

* :func:`embed_image` — image → 1024-dim vector
* :func:`embed_text`  — text  → 1024-dim vector

Both vectors live in the same Voyage multimodal embedding space, so
cosine similarity is meaningful across them (text query → image
vector retrieval is the canonical CLIP-style cross-modal search).

Requires
--------
* ``VOYAGE_API_KEY`` in the environment
* ``pip install voyageai``  (added to requirements-web.txt)
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

VOYAGE_MODEL = "voyage-multimodal-3"
VOYAGE_DIMS  = 1024
# Voyage's per-request payload limit is generous (multi-MB), but
# resizing to a consistent max-side keeps the embedding stable across
# the wildly different file sizes in our test set (30 KB → 7.5 MB).
MAX_IMAGE_SIDE = 1024

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
            import voyageai  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "voyageai SDK not installed; "
                "run `pip install voyageai`."
            ) from exc
        api_key = os.environ.get("VOYAGE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "VOYAGE_API_KEY is not set in the environment."
            )
        _client = voyageai.Client(api_key=api_key)
        return _client


def _open_image_resized(path: Path):
    """Open an image as RGB, resized so the longest side is at most
    ``MAX_IMAGE_SIDE`` pixels.  Returns a PIL.Image.Image."""
    from PIL import Image
    im = Image.open(path)
    im = im.convert("RGB")
    im.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    return im


def embed_image(path: Path, *, as_query: bool = False) -> list[float]:
    """Embed an image file (PNG/JPG) via Voyage multimodal-3.

    Parameters
    ----------
    path:
        Absolute path to the image file.
    as_query:
        ``False`` (default) tags the call ``input_type="document"`` —
        the right mode for the stored sketches.  ``True`` tags it
        ``input_type="query"`` — the right mode for user-supplied
        images at search time.

    Returns
    -------
    A 1024-dim list of floats (Voyage embeddings are already
    L2-normalised, so cosine = dot).
    """
    client = _get_client()
    input_type = "query" if as_query else "document"
    im = _open_image_resized(Path(path))
    try:
        result = client.multimodal_embed(
            inputs=[[im]],
            model=VOYAGE_MODEL,
            input_type=input_type,
        )
    finally:
        try:
            im.close()
        except Exception:
            pass
    return list(result.embeddings[0])


def embed_text(text: str, *, as_query: bool = True) -> list[float]:
    """Embed a text string via Voyage multimodal-3 (same vector space
    as :func:`embed_image`).

    Defaults to ``input_type="query"`` since text-against-our-store is
    the user/agent search direction.  Pass ``as_query=False`` if you
    ever want to embed text as a document for some reason.
    """
    client = _get_client()
    input_type = "query" if as_query else "document"
    result = client.multimodal_embed(
        inputs=[[text]],
        model=VOYAGE_MODEL,
        input_type=input_type,
    )
    return list(result.embeddings[0])
