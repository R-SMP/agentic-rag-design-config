"""Coarse cropping + side-by-side compositing for the ``view_images`` tool.

Pure PIL — no app dependencies, unit-testable standalone.  Produces the
approved "example-A" comparison layout: up to three panels placed next to each
other, each scaled to a common height (or left native), with a light label
bar, a thin border, and white gaps.  Used by the DC agents' unified image tool
so a vision model can compare images (renders and/or cropped user-sketch
regions) within a single frame.

The on-disk originals are never touched — callers pass already-loaded PIL
images / bytes; the crop + composite are model-facing copies only.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

# Layout constants (match the approved prototype).
_MATCH_HEIGHT_TARGET = 640   # common panel height for layout="match_height"
_NATIVE_CAP = 900            # per-image long-edge cap for layout="native"
_GAP = 26                    # white gap between panels (px)
_LABEL_H = 46                # label-bar height (px)
_BG = (255, 255, 255)
_LABEL_BG = (238, 238, 242)
_BORDER = (200, 200, 200)
_TEXT = (20, 20, 20)

MAX_PANELS = 3

try:  # Pillow >= 9.1
    _LANCZOS = Image.Resampling.LANCZOS
except AttributeError:  # pragma: no cover - older Pillow
    _LANCZOS = Image.LANCZOS


def to_rgb(im: "Image.Image") -> "Image.Image":
    """Return an RGB copy of *im*, compositing any alpha over WHITE (so a
    transparent-background render/sketch doesn't turn black on ``convert('RGB')``)."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return im.convert("RGB")


def _font(size: int):
    for cand in ("arial.ttf", "DejaVuSans.ttf",
                 r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf"):
        try:
            return ImageFont.truetype(cand, size)
        except Exception:
            continue
    return ImageFont.load_default()


def crop_to_region(im: "Image.Image", region) -> "Image.Image":
    """Crop *im* to a COARSE normalized box ``[x0, y0, x1, y1]`` (fractions in
    0..1).  Coordinates are clamped to [0, 1] and ordered, so a loose box from a
    vision model still yields a sensible crop.  Returns *im* unchanged on a
    missing / malformed / degenerate box (never raises)."""
    if not region:
        return im
    try:
        x0, y0, x1, y1 = (float(v) for v in list(region)[:4])
    except (TypeError, ValueError):
        return im
    x0, x1 = sorted((max(0.0, min(1.0, x0)), max(0.0, min(1.0, x1))))
    y0, y1 = sorted((max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))))
    w, h = im.size
    box = (int(x0 * w), int(y0 * h), int(round(x1 * w)), int(round(y1 * h)))
    if box[2] - box[0] < 2 or box[3] - box[1] < 2:
        return im   # degenerate crop -> keep the whole image
    return im.crop(box)


# Final composite long-edge cap.  Sized to the vision-API ceiling (Anthropic
# ~1568 px long edge) so the composite is downscaled ONCE here, cleanly, rather
# than again by the API — this is the legibility control for §B6.
_MAX_LONG_EDGE = 1560


def stitch(images, labels=None, layout: str = "match_height",
           max_long_edge: int = _MAX_LONG_EDGE) -> "Image.Image":
    """Compose up to :data:`MAX_PANELS` PIL images side-by-side into ONE image.

    ``layout="match_height"``: scale each panel to a common height — best for
    shape comparison, since two same-scale renders line up.  ``layout="native"``:
    keep native pixels (each capped), padded to a common height.  Every panel
    gets a label bar (its ``labels`` entry), a thin border, and white gaps.  The
    finished composite's long edge is capped at ``max_long_edge`` so it reaches
    the model at the vision-API size without a second downscale."""
    ims = [to_rgb(im) for im in list(images)[:MAX_PANELS]]
    if not ims:
        raise ValueError("stitch() needs at least one image")
    labels = list(labels or [])[:len(ims)]
    labels += [str(i + 1) for i in range(len(labels), len(ims))]

    if layout == "native":
        capped = []
        for im in ims:
            L = max(im.width, im.height)
            if L > _NATIVE_CAP:
                s = _NATIVE_CAP / L
                im = im.resize((round(im.width * s), round(im.height * s)), _LANCZOS)
            capped.append(im)
        ims = capped
    else:  # match_height (default)
        h = _MATCH_HEIGHT_TARGET
        ims = [im.resize((max(1, round(im.width * h / im.height)), h), _LANCZOS)
               for im in ims]

    panel_h = max(im.height for im in ims)
    total_w = sum(im.width for im in ims) + _GAP * (len(ims) - 1)
    canvas = Image.new("RGB", (total_w, panel_h + _LABEL_H), _BG)
    draw = ImageDraw.Draw(canvas)
    font = _font(30)
    x = 0
    for im, lab in zip(ims, labels):
        draw.rectangle([x, 0, x + im.width, _LABEL_H - 1], fill=_LABEL_BG)
        draw.text((x + 8, 8), str(lab), fill=_TEXT, font=font)
        y = _LABEL_H + (panel_h - im.height) // 2
        canvas.paste(im, (x, y))
        draw.rectangle([x, _LABEL_H, x + im.width - 1, _LABEL_H + panel_h - 1],
                       outline=_BORDER)
        x += im.width + _GAP

    L = max(canvas.width, canvas.height)
    if max_long_edge and L > max_long_edge:
        s = max_long_edge / L
        canvas = canvas.resize(
            (max(1, round(canvas.width * s)), max(1, round(canvas.height * s))),
            _LANCZOS,
        )
    return canvas


def stitch_to_png_bytes(images, labels=None, layout: str = "match_height",
                        max_long_edge: int = _MAX_LONG_EDGE) -> bytes:
    """:func:`stitch` then encode the composite to PNG bytes."""
    buf = io.BytesIO()
    stitch(images, labels, layout, max_long_edge).save(buf, format="PNG")
    return buf.getvalue()
