"""Swappable OCR engine package.

v1 engine: **Google Cloud Vision** (``google_vision.py``).

This package is the seam described in
``extra_utilities/OCR_technology_notes.md`` §5: the OCR engine is
chosen via a workflow setting, and a different engine (Azure / AWS /
a future self-hosted model) can slot in behind the same
``detect_text`` contract without touching the tool or agent layer.

Public contract
---------------
``detect_text(image) -> {"full_text": str, "regions": [...],
"words": [...], "raw": ...}`` where each **region** is callout-level
``{"id": int, "text": str, "box": {x0,y0,x1,y1}, "word_ids": [int]}``
(the ``ocr_region`` menu) and each **word** is the raw per-word box it
was grouped from.  All coordinates are source-image pixels.
"""
from agents.shared.ocr.google_vision import (
    OCRConfigError,
    OCRRequestError,
    detect_text,
    group_words_into_regions,
)

__all__ = [
    "detect_text",
    "group_words_into_regions",
    "OCRConfigError",
    "OCRRequestError",
]
