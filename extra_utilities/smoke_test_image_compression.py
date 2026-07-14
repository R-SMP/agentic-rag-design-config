"""Smoke test for agents/shared/image_compression.py.

Standalone (loads the module by path, so it runs under the worktree's Python
without importing the full agent stack).  Covers the correctness + robustness
fixes: exotic decode modes (I;16/F/CMYK) compress instead of crashing, EXIF
orientation is baked, the None-vs-0 degree sentinel round-trips, honest
media-type sniffing, passthrough on disabled/undecodable/small, and sane token
estimates.  Run:  python extra_utilities/smoke_test_image_compression.py
"""

import importlib.util
import io
import sys
import tempfile
from pathlib import Path

from PIL import Image

_MOD = Path(__file__).resolve().parents[1] / "agents" / "shared" / "image_compression.py"
_spec = importlib.util.spec_from_file_location("image_compression", _MOD)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

_fails = []


def ok(cond, msg):
    print(("PASS" if cond else "FAIL"), msg)
    if not cond:
        _fails.append(msg)


def _enc(im, fmt, **kw):
    b = io.BytesIO()
    im.save(b, format=fmt, **kw)
    return b.getvalue()


def _dims(raw):
    return Image.open(io.BytesIO(raw)).size


def _fmt(raw):
    return Image.open(io.BytesIO(raw)).format


CAP = 1024  # matches IMAGE_COMPRESSION_DEFAULT_CAP default


def main():
    # Large images compress, format preserved, long edge <= cap
    out = m.compress_for_model(_enc(Image.new("RGB", (3024, 2016), (120, 60, 30)), "PNG"))
    ok(max(_dims(out)) <= CAP and _fmt(out) == "PNG", f"RGB PNG 3024 -> {_dims(out)} {_fmt(out)}")
    out = m.compress_for_model(_enc(Image.new("RGB", (4032, 3024), (30, 90, 140)), "JPEG", quality=90))
    ok(max(_dims(out)) <= CAP and _fmt(out) == "JPEG", f"JPEG 4032 -> {_dims(out)} {_fmt(out)}")

    # Small image -> byte-identical passthrough
    raw = _enc(Image.new("RGB", (400, 300)), "PNG")
    ok(m.compress_for_model(raw) == raw, "small image passthrough")

    # Exotic modes used to CRASH (thumbnail/save outside guard) -> now compress
    for mode, fmt in [("I;16", "PNG"), ("F", "TIFF"), ("CMYK", "TIFF")]:
        raw = _enc(Image.new(mode, (3000, 2000)), fmt)
        try:
            out = m.compress_for_model(raw)
            ok(max(_dims(out)) <= CAP, f"exotic {mode} -> {_dims(out)} {_fmt(out)} (no crash)")
        except Exception as exc:  # noqa: BLE001
            ok(False, f"exotic {mode} CRASHED: {type(exc).__name__}: {exc}")

    # EXIF orientation baked in (portrait out, tag cleared)
    base = Image.new("RGB", (2000, 1000), (200, 120, 60))
    ex = base.getexif(); ex[274] = 6
    im = Image.open(io.BytesIO(m.compress_for_model(_enc(base, "JPEG", exif=ex, quality=90))))
    ok(im.size[1] > im.size[0] and im.getexif().get(274) in (None, 1), f"EXIF baked -> {im.size}")

    # Degree semantics: None=suggested, explicit 0=passthrough
    big = _enc(Image.new("RGB", (3000, 2000)), "PNG")
    ok(max(_dims(m.compress_for_model(big, None))) <= CAP, "degree None -> compressed")
    ok(m.compress_for_model(big, 0) == big, "degree 0 -> passthrough")
    # Non-numeric degree must not crash the choke-point
    for bad in ["abc", object(), [1, 2], ""]:
        try:
            ok(max(_dims(m.compress_for_model(big, bad))) <= CAP, f"degree {bad!r} -> no crash")
        except Exception as exc:  # noqa: BLE001
            ok(False, f"degree {bad!r} CRASHED: {type(exc).__name__}")

    # Sidecar round-trip preserves the None-vs-0 distinction
    ok(m.degree_from_json_text(m.degree_json(None)) is None, "sidecar None -> null -> None")
    ok(m.degree_from_json_text(m.degree_json(0)) == 0, "sidecar 0 -> 0")
    ok(m.degree_from_json_text(m.degree_json(50)) == 50, "sidecar 50 -> 50")
    ok(m.degree_from_json_text(m.degree_json("xyz")) is None, "sidecar garbage -> None")
    ok(m.degree_from_json_text(m.degree_json(150)) == 100, "sidecar clamp 150 -> 100")

    # Honest media-type sniffing
    for fmt, mt in {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif",
                    "WEBP": "image/webp", "BMP": "image/bmp", "TIFF": "image/tiff"}.items():
        got = m.sniff_media_type(_enc(Image.new("RGB", (50, 50), (1, 2, 3)), fmt))
        ok(got == mt, f"sniff {fmt} -> {got}")
    ok(m.sniff_media_type(b"") == "image/png", "sniff empty -> png (no crash)")

    # write/read sidecar + unique temp cleaned up
    with tempfile.TemporaryDirectory() as td:
        img = Path(td) / "foo.png"
        img.write_bytes(_enc(Image.new("RGB", (10, 10)), "PNG"))
        m.write_degree(img, 73)
        ok(m.read_degree(img) == 73, "sidecar write/read 73")
        ok(m.sidecar_path(img).name == "foo.compression.json", "sidecar name")
        m.write_degree(img, None)
        ok(m.read_degree(img) is None, "write None -> read None")
        ok(not [p for p in Path(td).iterdir() if p.name.endswith(".tmp")], "no leftover temp files")

    # Token estimates
    ok(m.estimate_image_tokens(800, 600, "anthropic") == 640, "anthropic 800x600 == 640")
    ok(m.estimate_image_tokens(1024, 768, "openai") == 765, "openai 1024x768 == 765")
    ok(m.estimate_image_tokens(300, 300, "google") == 258, "gemini small == 258")

    # Disabled / undecodable -> passthrough
    orig = m._get_setting
    m._get_setting = lambda n, d: False if n == "IMAGE_COMPRESSION_ENABLED" else orig(n, d)
    ok(m.compress_for_model(big) == big, "disabled -> passthrough")
    m._get_setting = orig
    ok(m.compress_for_model(b"not an image") == b"not an image", "undecodable -> passthrough")

    # Per-type render compression: explicit degree + a lower render floor.
    ok(max(_dims(m.compress_for_model(big, is_render=True))) <= CAP,
       "render with no explicit degree -> size-based default <= cap")
    ok(m.compress_for_model(big, degree_pct=0) == big, "degree 0 -> passthrough (no downscale)")
    ok(max(_dims(m.compress_for_model(big, degree_pct=100, floor=320))) == 320,
       "degree 100 + render floor -> long edge == 320")
    ok(m.render_kind("/x/render_blade_sections.png") == "cross", "cross-section render kind by name")
    ok(m.render_kind("/x/render_isometric.png") == "3d", "3d render kind by name")
    ok(m.render_kind("/x/user_photo.png") is None, "non-render name -> None kind")
    m._get_setting = lambda n, d: (60 if n == "IMAGE_COMPRESSION_3D_RENDER_DEGREE"
                                   else 320 if n == "IMAGE_COMPRESSION_RENDER_MIN_LONG_EDGE"
                                   else orig(n, d))
    ok(m.render_degree_and_floor("/x/render_isometric.png") == (60, 320),
       "3d degree+floor pulled from settings")
    ok(m.render_degree_and_floor("/x/user_photo.png") == (None, None),
       "non-render -> (None, None)")
    m._get_setting = orig

    # make_image_block's auto media-type detection reads the b64 head correctly
    import base64 as _b64
    for fmt, mt in {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.items():
        b = _b64.b64encode(_enc(Image.new("RGB", (60, 60), (9, 9, 9)), fmt)).decode()
        ok(m.sniff_media_type(_b64.b64decode(b[:16])) == mt, f"b64-head sniff {fmt} -> {mt}")

    # Headline: a phone photo really loses tokens
    photo = _enc(Image.new("RGB", (3024, 4032), (70, 70, 70)), "JPEG", quality=90)
    before = m.estimate_image_tokens(*_dims(photo), "anthropic")
    after = m.estimate_image_tokens(*_dims(m.compress_for_model(photo)), "anthropic")
    print(f"    phone photo anthropic tokens: {before} -> {after} ({100 * (before - after) // max(before, 1)}% saved)")
    ok(after < before, "phone photo tokens reduced")

    print("\n" + ("ALL PASS" if not _fails else f"{len(_fails)} FAILURES: " + "; ".join(_fails)))
    return 1 if _fails else 0


if __name__ == "__main__":
    sys.exit(main())
