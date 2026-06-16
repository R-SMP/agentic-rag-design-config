"""Smoke test for agents/shared/voyage_mm.py against the LIVE Voyage API.

Confirms the installed ``voyageai`` SDK knows ``voyage-multimodal-3.5``
and honours ``output_dimension=2048``, and that text / image / fused
embedding all return 2048-float vectors in the same space.

Run from repo root with an interpreter that has ``voyageai`` + a valid
``VOYAGE_API_KEY`` in .env::

    python extra_utilities/db_design/smoke_test_voyage_mm.py

Exits 0 on success, non-zero on any failure.  Makes a handful of live
Voyage calls (well within the free-token tier at this size).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass

try:
    from dotenv import load_dotenv as _load_dotenv  # type: ignore
    _load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

from PIL import Image, ImageDraw

from agents.shared import voyage_mm


def _make_test_image() -> Image.Image:
    """A tiny synthetic 'sketch': white canvas with a few black strokes."""
    im = Image.new("RGB", (256, 256), "white")
    d = ImageDraw.Draw(im)
    d.ellipse((40, 40, 216, 216), outline="black", width=3)
    d.line((128, 40, 128, 216), fill="black", width=2)
    d.line((40, 128, 216, 128), fill="black", width=2)
    d.text((60, 120), "blade", fill="black")
    return im


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def main() -> int:
    print(f"[voyage_mm-smoke]  model string = {voyage_mm.embedding_model_string()}")
    print(f"[voyage_mm-smoke]  expected dims = {voyage_mm.VOYAGE_MM_DIMS}, "
          f"max image side = {voyage_mm.MAX_IMAGE_SIDE}")

    img = _make_test_image()

    print("[voyage_mm-smoke]  embedding text ...")
    v_text = voyage_mm.embed_text("A propeller blade cross-section sketch.")
    print(f"[voyage_mm-smoke]    text vector dims    = {len(v_text)}")

    print("[voyage_mm-smoke]  embedding image-only ...")
    v_img = voyage_mm.embed_image(img)
    print(f"[voyage_mm-smoke]    image vector dims   = {len(v_img)}")

    print("[voyage_mm-smoke]  embedding fused image+text ...")
    v_fused = voyage_mm.embed_fused("Hand-drawn propeller blade with ring.", img)
    print(f"[voyage_mm-smoke]    fused vector dims   = {len(v_fused)}")

    # Assertions
    ok = True
    for name, vec in (("text", v_text), ("image", v_img), ("fused", v_fused)):
        if len(vec) != voyage_mm.VOYAGE_MM_DIMS:
            print(f"[voyage_mm-smoke]  FAIL: {name} vector has {len(vec)} dims, "
                  f"expected {voyage_mm.VOYAGE_MM_DIMS}")
            ok = False

    # Sanity: fused should sit between text-only and image-only (all in
    # one space; cosine just needs to be finite and in [-1, 1]).
    cos_if = _cosine(v_img, v_fused)
    cos_tf = _cosine(v_text, v_fused)
    print(f"[voyage_mm-smoke]  cos(image, fused) = {cos_if:.3f}   "
          f"cos(text, fused) = {cos_tf:.3f}")
    if not (-1.01 <= cos_if <= 1.01 and -1.01 <= cos_tf <= 1.01):
        print("[voyage_mm-smoke]  FAIL: cosine out of range — vectors look wrong")
        ok = False

    print()
    if ok:
        print("PASS - voyage_mm smoke test green.")
        return 0
    print("FAIL - voyage_mm smoke test had failures (see above).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
