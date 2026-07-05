"""Measure the vision-token savings from image compression (Phase 5).

``measure_prompts.py`` covers only static prompt-text assembly and CANNOT see
image token costs.  This companion measures the image side: it synthesises
representative images (a mesh render, a tall blade-section diagram, a phone
photo, a scanned sketch), runs each through ``compress_for_model`` at the
size-based auto-default, and reports the vision-token cost before/after for
each provider (Anthropic / OpenAI / Gemini), plus a typical-session total.

Token estimates depend only on pixel dimensions, so synthesised images with
realistic dimensions give accurate token numbers (content only affects file
bytes, reported as a secondary column).

Run:  python extra_utilities/prompt_efficiency/measure_image_tokens.py
"""

import importlib.util
import io
from pathlib import Path

from PIL import Image, ImageDraw

_MOD = Path(__file__).resolve().parents[2] / "agents" / "shared" / "image_compression.py"
_spec = importlib.util.spec_from_file_location("image_compression", _MOD)
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)

PROVIDERS = ("anthropic", "openai", "google")


def _lineart(w, h, fmt):
    """A light line-art image (renders / diagrams / sketches)."""
    im = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(im)
    for i in range(0, w, max(1, w // 40)):
        d.line([(i, 0), (w - i, h)], fill=(40, 40, 40), width=2)
    d.ellipse([w * 0.2, h * 0.2, w * 0.8, h * 0.8], outline=(10, 10, 10), width=3)
    b = io.BytesIO(); im.save(b, format=fmt); return b.getvalue()


def _photo(w, h, fmt):
    """A photographic gradient (phone-camera-like)."""
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            px[x, y] = ((x * 255) // w, (y * 255) // h, ((x + y) * 127) // (w + h))
    b = io.BytesIO(); im.save(b, format=fmt, quality=90); return b.getvalue()


# (label, width, height, format, generator, is_render)
SAMPLES = [
    ("mesh render (render_mesh)",   800, 600, "PNG", _lineart, True),
    ("blade-section diagram",       900, 1300, "PNG", _lineart, True),
    ("scanned sketch",             2000, 1500, "PNG", _lineart, False),
    ("phone photo",                3024, 4032, "JPEG", _photo, False),
]


def _dims(raw):
    return Image.open(io.BytesIO(raw)).size


def _fmt_tokens(w, h):
    return {p: ic.estimate_image_tokens(w, h, p) for p in PROVIDERS}


def main():
    print(f"Image compression: floor={ic._floor()}px  cap={ic._cap()}px  "
          f"enabled={ic._get_setting('IMAGE_COMPRESSION_ENABLED', True)}\n")
    header = f"{'image':<28}{'dims':>12}{'->':^4}{'dims':>12}   " + \
             "  ".join(f"{p[:4]:>10}" for p in PROVIDERS) + f"{'KB':>10}"
    print(header)
    print("-" * len(header))

    totals_before = {p: 0 for p in PROVIDERS}
    totals_after = {p: 0 for p in PROVIDERS}
    for label, w, h, fmt, gen, is_render in SAMPLES:
        raw = gen(w, h, fmt)
        out = ic.compress_for_model(raw, None, is_render=is_render)
        ow, oh = _dims(out)
        tb, ta = _fmt_tokens(w, h), _fmt_tokens(ow, oh)
        for p in PROVIDERS:
            totals_before[p] += tb[p]; totals_after[p] += ta[p]
        deltas = "  ".join(
            f"{(str(tb[p])+'->'+str(ta[p])):>10}" for p in PROVIDERS
        )
        kb = f"{len(raw)//1024}->{len(out)//1024}"
        print(f"{label:<28}{f'{w}x{h}':>12}{'->':^4}{f'{ow}x{oh}':>12}   {deltas}{kb:>10}")

    print("-" * len(header))
    print("\nPer-provider vision tokens for the 4-image set:")
    for p in PROVIDERS:
        b, a = totals_before[p], totals_after[p]
        pct = 100 * (b - a) // max(b, 1)
        print(f"  {p:<10} {b:>7} -> {a:>7}   ({pct}% saved, -{b - a} tok)")

    # A plausible design session's model-facing image mix.
    print("\nTypical-session estimate (Anthropic):")
    mix = [("2 uploaded sketches", 2, 2000, 1500, "PNG", _lineart, False),
           ("1 uploaded photo",    1, 3024, 4032, "JPEG", _photo, False),
           ("6 live mesh renders", 6, 800, 600, "PNG", _lineart, True),
           ("3 blade sections",    3, 900, 1300, "PNG", _lineart, True),
           ("4 retrieved renders", 4, 800, 600, "PNG", _lineart, True)]
    sb = sa = 0
    for label, n, w, h, fmt, gen, is_render in mix:
        out = ic.compress_for_model(gen(w, h, fmt), None, is_render=is_render)
        ow, oh = _dims(out)
        b = ic.estimate_image_tokens(w, h, "anthropic") * n
        a = ic.estimate_image_tokens(ow, oh, "anthropic") * n
        sb += b; sa += a
        print(f"  {label:<22} {b:>6} -> {a:>6} tok")
    print(f"  {'TOTAL':<22} {sb:>6} -> {sa:>6} tok   "
          f"({100 * (sb - sa) // max(sb, 1)}% saved, -{sb - sa} tok/session)")


if __name__ == "__main__":
    main()
