"""Resolution-based image compression for the model-facing image copies.

Agents are billed vision tokens by PIXEL COUNT (Anthropic ~ (w*h)/750, OpenAI/
Gemini by tiles), not by file bytes — so the ONLY lever that lightens an agent's
token window is downscaling an image's pixel dimensions.  This module is the
single server-side choke-point that does that, shared by every place that hands
an image to a model.

  * A per-image "compression degree" — 0-100, where 0 = original resolution and
    100 = a fixed floor on the LONG edge (``IMAGE_COMPRESSION_MIN_LONG_EDGE``).
    Linear on the long edge; NEVER upscales, so an image already <= the floor is
    untouched at any degree.
  * The compressed image is a COPY for the model only.  The full-resolution
    original is always what OCR + the embedding pipeline read; this module never
    mutates the source file.
  * The copy is DERIVED on demand from (original bytes, degree); never stored.
    The degree travels in a small ``<stem>.compression.json`` sidecar (local +
    R2), so a retrieved past-session image is re-compressed to its author's
    degree.  ``degree_pct=None`` (or an absent/garbage sidecar) means "untuned"
    -> use the size-based ``suggested_degree``; an explicit value (INCLUDING 0)
    overrides it.  That None-vs-0 distinction is load-bearing.
  * Format is preserved (PNG stays lossless PNG, JPEG stays JPEG at q90); only
    resolution changes.  Exotic decode modes (I;16 / F / CMYK / P …) are
    normalised to a writable mode before re-encoding so they compress instead of
    crashing.

Everything degrades gracefully: disabled, undecodable, encode failure, or
no-shrink-needed -> the ORIGINAL bytes are returned unchanged.  The whole
transform is guarded so a single odd image can never crash an image-load site.
Pure PIL + stdlib, unit-testable outside the app.
"""

from __future__ import annotations

import io
import json
import logging
import math
import os
import threading
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps

logger = logging.getLogger("propeller_agent")

try:  # Pillow >= 9.1
    _LANCZOS = Image.Resampling.LANCZOS
except AttributeError:  # pragma: no cover - older Pillow
    _LANCZOS = Image.LANCZOS

_DEFAULT_ENABLED = True
_DEFAULT_MIN_LONG_EDGE = 512   # long edge at 100% ("max compression")
_DEFAULT_RENDER_MIN_LONG_EDGE = 320   # lower 100% floor for software renders
_DEFAULT_CAP = 1024            # size-based auto-default target long edge
_DEFAULT_HARD_MAX = 1900       # absolute ceiling; Anthropic many-image cap is 2000
_JPEG_QUALITY = 90

SIDECAR_SUFFIX = ".compression.json"

# PNG can encode these modes directly; anything else is normalised to RGB.
_PNG_SAFE_MODES = frozenset({"1", "L", "LA", "RGB", "RGBA"})


def _get_setting(name: str, default):
    """Read a workflow setting fresh, falling back to *default* (defensive lazy
    import so this module imports + unit-tests without the full app env)."""
    try:
        from workflow_settings import settings as ws
        return getattr(ws, name, default)
    except Exception:
        return default


def _floor() -> int:
    try:
        return max(1, int(_get_setting("IMAGE_COMPRESSION_MIN_LONG_EDGE", _DEFAULT_MIN_LONG_EDGE)))
    except (TypeError, ValueError):
        return _DEFAULT_MIN_LONG_EDGE


def _cap() -> int:
    try:
        return max(1, int(_get_setting("IMAGE_COMPRESSION_DEFAULT_CAP", _DEFAULT_CAP)))
    except (TypeError, ValueError):
        return _DEFAULT_CAP


def _hard_max() -> int:
    """Absolute long-edge ceiling for a MODEL-FACING image; 0 disables it.

    An API constraint rather than a tuning knob, so it applies even when
    ``IMAGE_COMPRESSION_ENABLED`` is False and whatever the per-image degree
    says.  See ``IMAGE_COMPRESSION_HARD_MAX_LONG_EDGE`` in settings.py.
    """
    try:
        return max(0, int(_get_setting("IMAGE_COMPRESSION_HARD_MAX_LONG_EDGE",
                                       _DEFAULT_HARD_MAX)))
    except (TypeError, ValueError):
        return _DEFAULT_HARD_MAX


def _render_floor() -> int:
    """The (lower) long edge a RENDER reaches at 100% degree — separate from the
    user-image floor so schematic renders can compress further."""
    try:
        return max(1, int(_get_setting(
            "IMAGE_COMPRESSION_RENDER_MIN_LONG_EDGE", _DEFAULT_RENDER_MIN_LONG_EDGE)))
    except (TypeError, ValueError):
        return _DEFAULT_RENDER_MIN_LONG_EDGE


# --------------------------------------------------------------------------
# Degree <-> resolution
# --------------------------------------------------------------------------
def degree_to_long_edge(degree_pct, orig_long_edge: int, floor: int = None) -> int:
    """Map a 0-100 degree to a target long-edge (px).  0 -> original,
    100 -> *floor* (defaults to the user-image floor); linear between.  Never
    upscales."""
    floor = _floor() if floor is None else max(1, int(floor))
    L = int(orig_long_edge)
    if L <= floor:
        return L
    p = min(100.0, max(0.0, float(degree_pct)))
    return int(min(L, max(floor, round(L - (p / 100.0) * (L - floor)))))


def suggested_degree(width: int, height: int) -> int:
    """Auto-default degree for an untuned image (size-based): shrink anything
    whose long edge exceeds the cap down to <= the cap; else 0.  Rounds the
    integer degree UP so the cap is a true ceiling (the compressed long edge is
    never above the cap, only up to ~1 degree-step below it)."""
    L = max(int(width), int(height))
    cap, floor = _cap(), _floor()
    if L <= cap or L <= floor:
        return 0
    if cap <= floor:
        return 100
    return int(math.ceil(100.0 * (L - cap) / (L - floor)))


# --------------------------------------------------------------------------
# Sidecar (per-image degree)
# --------------------------------------------------------------------------
def _coerce_degree(val) -> Optional[int]:
    """Clamp *val* to an int in [0, 100]; None for None/non-numeric input."""
    try:
        return min(100, max(0, int(val)))
    except (TypeError, ValueError):
        return None


def sidecar_path(image_path) -> Path:
    p = Path(image_path)
    return p.with_name(p.stem + SIDECAR_SUFFIX)


def degree_from_json_text(text: str) -> Optional[int]:
    """Parse a degree out of sidecar JSON text (used for R2-fetched sidecars).
    A missing/null/garbage value round-trips to None (= untuned)."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return _coerce_degree(data.get("degree_pct")) if isinstance(data, dict) else None


def degree_json(degree_pct) -> str:
    """Serialise a degree for a sidecar.  None (untuned) is stored as JSON
    ``null`` so it round-trips back to None instead of collapsing to 0."""
    return json.dumps({"degree_pct": _coerce_degree(degree_pct), "version": 1})


def read_degree(image_path) -> Optional[int]:
    """Stored degree for *image_path*, or None (=> caller uses suggested_degree).
    Absence of a sidecar also means 'untuned' -> size-based auto-default."""
    sc = sidecar_path(image_path)
    try:
        if not sc.is_file():
            return None
        return degree_from_json_text(sc.read_text(encoding="utf-8"))
    except OSError:
        return None


def write_degree(image_path, degree_pct) -> None:
    """Persist the degree beside *image_path* (atomic best-effort).  An explicit
    0 is a real choice ('no compression'); None is stored as null (= untuned).
    The temp name is unique per writer so two threads never share it."""
    sc = sidecar_path(image_path)
    tmp = sc.with_name(f"{sc.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(degree_json(degree_pct), encoding="utf-8")
        os.replace(str(tmp), str(sc))
    except OSError as exc:
        logger.warning("[img-compress] failed to write sidecar %s: %s", sc, exc)
        try:
            tmp.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------
# Format sniff (so the image content block carries the true media_type)
# --------------------------------------------------------------------------
def sniff_media_type(raw: bytes) -> str:
    """Best-effort image media type from magic bytes; defaults to image/png."""
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw[:2] == b"BM":
        return "image/bmp"
    if raw[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    return "image/png"


# --------------------------------------------------------------------------
# The choke-point
# --------------------------------------------------------------------------
def _normalize_mode(im: "Image.Image", out_format: str) -> "Image.Image":
    """Coerce *im* to a mode the target format can encode + LANCZOS can resize.
    JPEG needs RGB (no alpha).  PNG keeps 1/L/LA/RGB/RGBA and promotes P to
    RGB(A); exotic modes (I;16 / I / F / CMYK / YCbCr) are converted to RGB."""
    if out_format == "JPEG":
        return _flatten_to_rgb(im)
    if im.mode == "P":
        return im.convert("RGBA" if "transparency" in im.info else "RGB")
    if im.mode in _PNG_SAFE_MODES:
        return im
    return im.convert("RGB")


_CROSS_SECTION_PREFIX = "render_blade_sections"
_3D_RENDER_NAMES = frozenset(
    ("render_isometric.png", "render_top.png", "render_side.png"))


def render_kind(image_path) -> Optional[str]:
    """"cross" for a blade-sections diagram, "3d" for a 3D mesh view, else None
    — decided by the render's canonical filename."""
    name = Path(image_path).name
    if name.startswith(_CROSS_SECTION_PREFIX):
        return "cross"
    if name in _3D_RENDER_NAMES:
        return "3d"
    return None


def render_degree_and_floor(image_path):
    """(degree_pct, floor) for a render path per its kind + the workflow
    settings, or (None, None) when the path is not a recognised render (the
    caller then falls back to the size-based default)."""
    kind = render_kind(image_path)
    if kind is None:
        return None, None
    setting = ("IMAGE_COMPRESSION_CROSS_SECTIONS_DEGREE" if kind == "cross"
               else "IMAGE_COMPRESSION_3D_RENDER_DEGREE")
    deg = _coerce_degree(_get_setting(setting, 0))
    return (0 if deg is None else deg), _render_floor()


def compress_for_model(raw: bytes, degree_pct=None, is_render: bool = False,
                       floor: int = None) -> bytes:
    """Resolution-reduced copy of *raw* for MODEL viewing.  *degree_pct* None (or
    non-numeric) => size-based ``suggested_degree``; an explicit int (incl. 0,
    which means "no downscale") overrides.  *floor* overrides the long edge the
    100% degree reaches (renders pass a lower floor than user images).
    *is_render* is informational only — the per-render-type degree + floor are
    chosen by the caller (see ``render_degree_and_floor``).  Format preserved;
    the long edge is downscaled per the degree curve.  Returns the ORIGINAL
    bytes unchanged when compression is disabled, no downscale is needed, or
    ANYTHING fails — never raises, never upscales.  OCR / embeddings must NOT
    call this; they read the full original.

    ``IMAGE_COMPRESSION_HARD_MAX_LONG_EDGE`` is an absolute ceiling and applies
    even with compression disabled and even at degree 0 — it exists to keep a
    request under Anthropic's 2000 px many-image limit, which a long agent turn
    reaches by accumulating images."""
    enabled = bool(_get_setting("IMAGE_COMPRESSION_ENABLED", _DEFAULT_ENABLED))
    hard = _hard_max()
    if not enabled and not hard:
        return raw
    try:
        im = Image.open(io.BytesIO(raw))
        w, h = im.size  # header only — passthrough never pays a full decode
        L = max(w, h)
        if enabled:
            chosen = _coerce_degree(degree_pct)
            pct = suggested_degree(w, h) if chosen is None else chosen
            target_L = degree_to_long_edge(pct, L, floor=floor)
        else:
            target_L = L          # ceiling only
        if hard:
            target_L = min(target_L, hard)
        if target_L >= L:
            return raw  # no shrink -> keep the original bytes (and true format)

        out_format = "JPEG" if (im.format or "").upper() in ("JPEG", "JPG") else "PNG"
        if out_format == "JPEG":
            # libjpeg scaled decode (1/2, 1/4, 1/8) — cheaper decode + memory.
            im.draft("RGB", (target_L, target_L))
        im = ImageOps.exif_transpose(im) or im  # bake orientation before resize
        im = _normalize_mode(im, out_format)
        im.thumbnail((target_L, target_L), _LANCZOS)  # caps long edge, keeps aspect

        buf = io.BytesIO()
        if out_format == "JPEG":
            im.save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
        else:
            im.save(buf, format="PNG")  # no optimize: bytes don't affect tokens
        return buf.getvalue()
    except Exception:
        return raw  # decode / resize / encode failure -> safe passthrough


def _flatten_to_rgb(im: "Image.Image") -> "Image.Image":
    """RGB copy compositing any alpha over white (JPEG can't carry alpha)."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return im.convert("RGB")


# --------------------------------------------------------------------------
# Token estimation (live preview + measurement; not used at load time)
# --------------------------------------------------------------------------
def estimate_image_tokens(width: int, height: int, provider: str = "anthropic") -> int:
    """Rough vision-token estimate for *width* x *height* on *provider*.  For UI
    preview + measurement only, never billing."""
    w, h = int(width), int(height)
    if w <= 0 or h <= 0:
        return 0
    p = (provider or "").lower()
    if p == "openai":
        if max(w, h) > 2048:
            s = 2048 / max(w, h); w, h = round(w * s), round(h * s)
        if min(w, h) > 768:
            s = 768 / min(w, h); w, h = round(w * s), round(h * s)
        return 85 + 170 * (math.ceil(w / 512) * math.ceil(h / 512))
    if p in ("google", "gemini"):
        if max(w, h) <= 384:
            return 258
        return 258 * (math.ceil(w / 768) * math.ceil(h / 768))
    # anthropic / default: pixel-count model with its 1568 long-edge + 1.15MP caps
    if max(w, h) > 1568:
        s = 1568 / max(w, h); w, h = round(w * s), round(h * s)
    if w * h > 1_150_000:
        s = (1_150_000 / (w * h)) ** 0.5; w, h = round(w * s), round(h * s)
    return int((w * h) / 750)
