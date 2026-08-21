"""Google Cloud Vision OCR engine (text detection).

Thin REST layer over the Cloud Vision ``images:annotate`` endpoint,
authenticated with an **API key** (``GOOGLE_CLOUD_VISION_API_KEY``).
No SDK / service-account machinery — a single HTTPS POST, so it runs
identically on the CPU Railway container and locally.

This is the first concrete implementation behind the swappable OCR
engine interface in ``extra_utilities/docs/reference/OCR_technology_notes.md`` §5.
Other engines (Azure, AWS, a future self-hosted model) can implement
the same :func:`detect_text` contract and be selected via the OCR
engine workflow setting.

Mode
----
Uses **``TEXT_DETECTION``** (sparse-scene OCR) rather than
``DOCUMENT_TEXT_DETECTION`` (dense documents) — the right mode for the
scattered callouts on engineering sketches / annotated renders.

Requires
--------
* ``GOOGLE_CLOUD_VISION_API_KEY`` in the environment (Railway dashboard
  Variables; local ``.env`` for dev).  The Cloud Vision API must be
  enabled and billing active on the owning GCP project.  See
  ``OCR_technology_notes.md`` §7.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

import requests

_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
# One annotate call; generous enough for a large image upload, short
# enough not to hang an agent's turn if Vision is unreachable.
_HTTP_TIMEOUT = 30


class OCRConfigError(RuntimeError):
    """Engine is not configured (e.g. missing API key)."""


class OCRRequestError(RuntimeError):
    """The Vision API call failed or returned an error payload."""


def _api_key() -> str:
    key = os.environ.get("GOOGLE_CLOUD_VISION_API_KEY", "").strip()
    if not key:
        raise OCRConfigError(
            "GOOGLE_CLOUD_VISION_API_KEY is not set in the environment. "
            "Set it in the Railway dashboard Variables (and local .env "
            "for dev). See extra_utilities/docs/reference/OCR_technology_notes.md §7."
        )
    return key


def _load_image_bytes(image: bytes | bytearray | str | Path) -> bytes:
    if isinstance(image, (bytes, bytearray)):
        return bytes(image)
    return Path(image).read_bytes()


def _box_from_vertices(bounding_poly: dict | None) -> dict:
    """Reduce Vision's 4-vertex boundingPoly to an axis-aligned rect."""
    verts = (bounding_poly or {}).get("vertices") or []
    xs = [v.get("x", 0) for v in verts]
    ys = [v.get("y", 0) for v in verts]
    return {
        "x0": min(xs) if xs else 0,
        "y0": min(ys) if ys else 0,
        "x1": max(xs) if xs else 0,
        "y1": max(ys) if ys else 0,
    }


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2:
        return float(s[mid])
    return (s[mid - 1] + s[mid]) / 2.0


def _box_gap(a: dict, b: dict) -> tuple[int, int]:
    """Edge-to-edge gap between two boxes along x and y.

    Returns ``(gap_x, gap_y)``; either is ``0`` when the boxes overlap
    on that axis.
    """
    gap_x = max(b["x0"] - a["x1"], a["x0"] - b["x1"], 0)
    gap_y = max(b["y0"] - a["y1"], a["y0"] - b["y1"], 0)
    return gap_x, gap_y


def group_words_into_regions(
    words: list[dict],
    *,
    x_gap_factor: float = 1.5,
    y_gap_factor: float = 0.6,
) -> list[dict]:
    """Group per-word boxes into callout regions by **2D spatial proximity**.

    Builds a proximity graph and takes its connected components: two
    words are linked when the edge-to-edge gap between their boxes is
    small in BOTH axes — horizontal gap <= ``x_gap_factor`` and vertical
    gap <= ``y_gap_factor``, each scaled by the median word height.
    Connected words form one region.

    Because the proximity test is purely geometric and symmetric,
    grouping is **independent of the order words arrive in**, and it
    handles rotated / diagonal / vertically-stacked callouts — not only
    horizontal lines.

    Each returned region is ``{"id", "text", "box", "word_ids"}`` with a
    1-based ``id`` assigned top-to-bottom, left-to-right.  Word text
    within a region is concatenated in reading order (banded
    top-to-bottom, then left-to-right).  These ids are the menu the
    agent picks from for ``ocr_regions`` (see F37).

    Complexity is O(n^2) in the word count — fine for sparse sketch
    callouts (TEXT_DETECTION on a drawing yields tens of words), which
    is the only use case here.
    """
    if not words:
        return []

    n = len(words)
    heights = [w["box"]["y1"] - w["box"]["y0"] for w in words]
    med_h = _median([h for h in heights if h > 0]) or 1
    x_thresh = x_gap_factor * med_h
    y_thresh = y_gap_factor * med_h

    # Union-find over the proximity graph.
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(n):
        for j in range(i + 1, n):
            gap_x, gap_y = _box_gap(words[i]["box"], words[j]["box"])
            if gap_x <= x_thresh and gap_y <= y_thresh:
                union(i, j)

    components: dict[int, list[dict]] = {}
    for i in range(n):
        components.setdefault(find(i), []).append(words[i])

    # Reading order: bucket y-centres into bands ~0.7x median height so
    # words on the same visual line sort left-to-right, bands ordered
    # top-to-bottom.  Robust for both single lines and stacked blocks.
    band = max(1, round(0.7 * med_h))

    def reading_key(w: dict) -> tuple[int, float]:
        y_center = (w["box"]["y0"] + w["box"]["y1"]) / 2
        return (round(y_center / band), w["box"]["x0"])

    regions: list[dict] = []
    for members in components.values():
        ordered = sorted(members, key=reading_key)
        regions.append(
            {
                "text": " ".join(m["text"] for m in ordered),
                "box": {
                    "x0": min(m["box"]["x0"] for m in members),
                    "y0": min(m["box"]["y0"] for m in members),
                    "x1": max(m["box"]["x1"] for m in members),
                    "y1": max(m["box"]["y1"] for m in members),
                },
                "word_ids": [m["id"] for m in ordered],
            }
        )

    regions.sort(key=lambda r: (r["box"]["y0"], r["box"]["x0"]))
    for idx, r in enumerate(regions, start=1):
        r["id"] = idx
    return regions


def detect_text(
    image: bytes | bytearray | str | Path,
    *,
    language_hints: list[str] | None = None,
) -> dict:
    """Run Google Cloud Vision ``TEXT_DETECTION`` on a single image.

    Parameters
    ----------
    image:
        Raw image bytes, or a path to a ``.png`` / ``.jpg`` / ``.jpeg``.
    language_hints:
        Optional list of BCP-47 language codes (e.g. ``["en"]``) passed
        to ``imageContext`` to bias recognition.

    Returns
    -------
    dict with:
      * ``full_text`` — the entire detected text block (newline-joined),
        ``""`` if nothing was found.
      * ``regions``   — **callout-level** regions (words grouped by line
        + horizontal proximity), each
        ``{"id": int, "text": str, "box": {x0,y0,x1,y1},
        "word_ids": [int]}`` in source-image pixel coordinates.  The
        1-based ``id`` is the menu the agent picks from for
        ``ocr_regions`` (see F37).
      * ``words``     — the raw **per-word** boxes the regions were built
        from: ``{"id": int, "text": str, "box": {x0,y0,x1,y1}}``.
      * ``raw``       — the raw first-response dict (for debugging).

    Raises
    ------
    OCRConfigError
        When ``GOOGLE_CLOUD_VISION_API_KEY`` is unset.
    OCRRequestError
        When the HTTP call fails or Vision returns an error (API not
        enabled, billing disabled, key restricted, etc.).
    """
    key = _api_key()
    content_b64 = base64.b64encode(_load_image_bytes(image)).decode("ascii")

    body: dict = {
        "requests": [
            {
                "image": {"content": content_b64},
                "features": [{"type": "TEXT_DETECTION"}],
            }
        ]
    }
    if language_hints:
        body["requests"][0]["imageContext"] = {
            "languageHints": list(language_hints)
        }

    try:
        resp = requests.post(
            _ENDPOINT,
            params={"key": key},
            json=body,
            timeout=_HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise OCRRequestError(f"Vision API request failed: {exc}") from exc

    if resp.status_code != 200:
        # The error body carries the actionable message (API not
        # enabled / billing disabled / key restricted / bad image).
        raise OCRRequestError(
            f"Vision API returned HTTP {resp.status_code}: "
            f"{resp.text[:500]}"
        )

    payload = resp.json()
    responses = payload.get("responses") or [{}]
    r0 = responses[0] or {}
    if "error" in r0:
        raise OCRRequestError(f"Vision API per-image error: {r0['error']}")

    annotations = r0.get("textAnnotations") or []
    full_text = annotations[0].get("description", "") if annotations else ""

    words: list[dict] = []
    for i, ann in enumerate(annotations[1:], start=1):
        words.append(
            {
                "id": i,
                "text": ann.get("description", ""),
                "box": _box_from_vertices(ann.get("boundingPoly")),
            }
        )

    regions = group_words_into_regions(words)

    return {
        "full_text": full_text,
        "regions": regions,
        "words": words,
        "raw": r0,
    }
