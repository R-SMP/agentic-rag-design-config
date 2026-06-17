"""OCR feature-integration layer — the single entry point chain tools call.

`load_input_images`, `read_user_inputs` and `retrieve_user_inputs` all
call :func:`ocr_summary_if_enabled` so they behave identically: the gate
(``OCR_ENABLED`` + the agent's per-call flag) and the per-image
formatting live in ONE place.

The pure engine (``google_vision.py``) stays free of workflow settings;
this module is where the OCR feature meets the settings layer (so the
engine remains swappable and unit-testable in isolation).
"""
from __future__ import annotations

from pathlib import Path


def ocr_enabled() -> bool:
    """True iff the operator master switch ``OCR_ENABLED`` is on.

    Read fresh on each call (e.g. at agent set-up) so a settings change
    is picked up without code edits here.  Import-guarded so a settings
    import problem can never break a tool call.
    """
    try:
        from workflow_settings import settings as workflow_settings
        return bool(getattr(workflow_settings, "OCR_ENABLED", False))
    except Exception:  # noqa: BLE001 — never break a tool over settings
        return False


def ocr_summary_if_enabled(
    items: list[tuple[str, "bytes | str"]],
    requested: bool,
) -> list[str]:
    """Return per-image OCR summary lines for *items*, or ``[]``.

    Returns ``[]`` immediately when OCR is globally disabled
    (``OCR_ENABLED=False``), when the caller's per-call flag *requested*
    is False, or when *items* is empty — so callers can unconditionally
    do ``parts.extend(ocr_summary_if_enabled(items, flag))``.

    Otherwise runs the configured OCR engine on each item and returns
    formatted lines (one block per image) ready to append to a tool's
    text result.  **Non-fatal**: a config / request / import error
    yields a single explanatory line instead of raising, so OCR can
    never break a tool call.

    Each item is ``(label, source)`` where *label* is a human-readable
    name (filename or R2 key) and *source* is an image file path or raw
    image bytes — both accepted by the engine's ``detect_text``.
    """
    if not items or not requested or not ocr_enabled():
        return []

    try:
        from workflow_settings import settings as workflow_settings
        cap = int(getattr(workflow_settings, "OCR_MAX_TEXT_CHARS", 2000))
    except Exception:  # noqa: BLE001
        cap = 2000

    try:
        from agents.shared.ocr.google_vision import (
            OCRConfigError,
            OCRRequestError,
            detect_text,
        )
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        return [f"OCR unavailable (engine import failed: {exc})."]

    out: list[str] = []
    for label, source in items:
        name = Path(label).name if isinstance(label, str) and label else str(label)
        try:
            result = detect_text(source, language_hints=["en"])
        except OCRConfigError as exc:
            out.append(f"OCR for {name}: unavailable ({exc}).")
            continue
        except OCRRequestError as exc:
            out.append(f"OCR for {name}: failed ({exc}).")
            continue
        except Exception as exc:  # noqa: BLE001 — never break a tool call
            out.append(f"OCR for {name}: error ({type(exc).__name__}: {exc}).")
            continue
        regions = result.get("regions") or []
        if not regions:
            out.append(f"OCR for {name}: no text detected.")
            continue
        lines = [
            f"OCR text detected on {name} "
            f"(machine-read — verify against the image):"
        ]
        for r in regions:
            lines.append(f"  [region {r['id']}] {r['text']}")
        block = "\n".join(lines)
        if len(block) > cap:
            block = block[:cap] + "\n  ...(OCR text truncated)"
        out.append(block)
    return out


def ocr_region_reread(
    image_source: "bytes | str",
    region_id: int,
    *,
    pad_frac: float = 0.2,
    upscale: float = 3.0,
) -> dict:
    """Re-OCR a single detected region of an image at higher resolution.

    **Stateless** (the box was computed in an earlier tool call): re-runs
    whole-image detection — grouping is deterministic, so the region ids
    match the earlier pass — locates *region_id*, crops its box (padded
    by *pad_frac* on each side, clamped to the image), upscales the crop
    by *upscale*, and re-runs the engine on the crop.

    **Non-fatal**: returns a dict with ``ok=False`` + ``error`` on any
    problem (engine/PIL import, bad image, region id out of range — the
    F38 case) rather than raising.

    Returns dict with keys:
      * ``ok`` (bool), ``error`` (str | None)
      * ``n_regions`` (int) — regions detected on the full image
      * ``original_text`` (str) — the region's text from the full pass
      * ``reread_text`` (str) — text read from the upscaled crop
      * ``crop_png`` (bytes | None) — the zoomed crop, PNG, for attaching
      * ``box`` (dict | None) — the padded crop box (source-image pixels)

    *image_source* is a file path or raw image bytes.
    """
    fail = {
        "ok": False, "error": None, "n_regions": 0,
        "original_text": "", "reread_text": "", "crop_png": None, "box": None,
    }

    try:
        import io

        from PIL import Image

        from agents.shared.ocr.google_vision import detect_text
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        return {**fail, "error": f"OCR/PIL import failed: {exc}"}

    # 1) Detect on the full image to recover region *region_id*'s box.
    try:
        full = detect_text(image_source, language_hints=["en"])
    except Exception as exc:  # noqa: BLE001
        return {**fail, "error": f"detection failed: {exc}"}
    regions = full.get("regions") or []
    n = len(regions)
    match = next((r for r in regions if r.get("id") == region_id), None)
    if match is None:
        return {
            **fail,
            "n_regions": n,
            "error": (
                f"region {region_id} not found — {n} region(s) detected "
                f"(valid ids 1..{n})" if n else "no text regions detected"
            ),
        }

    # 2) Open image + compute the padded, clamped crop box.
    try:
        if isinstance(image_source, (bytes, bytearray)):
            im = Image.open(io.BytesIO(bytes(image_source)))
        else:
            im = Image.open(image_source)
        im = im.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        return {**fail, "n_regions": n, "error": f"could not open image: {exc}"}

    w, h = im.size
    b = match["box"]
    bw = max(0, b["x1"] - b["x0"])
    bh = max(0, b["y1"] - b["y0"])
    px = int(bw * pad_frac)
    py = int(bh * pad_frac)
    x0 = max(0, b["x0"] - px)
    y0 = max(0, b["y0"] - py)
    x1 = min(w, b["x1"] + px)
    y1 = min(h, b["y1"] + py)
    if x1 <= x0 or y1 <= y0:
        return {**fail, "n_regions": n, "error": "degenerate crop box"}
    padded_box = {"x0": x0, "y0": y0, "x1": x1, "y1": y1}

    # 3) Crop + upscale + encode.
    try:
        crop = im.crop((x0, y0, x1, y1))
        if upscale and upscale != 1.0:
            crop = crop.resize(
                (max(1, int(crop.width * upscale)),
                 max(1, int(crop.height * upscale)))
            )
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        crop_png = buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        return {**fail, "n_regions": n, "error": f"crop/upscale failed: {exc}"}

    # 4) Re-OCR the upscaled crop.
    try:
        reread = detect_text(crop_png, language_hints=["en"])
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False, "error": f"re-OCR failed: {exc}", "n_regions": n,
            "original_text": match.get("text", ""), "reread_text": "",
            "crop_png": crop_png, "box": padded_box,
        }

    return {
        "ok": True, "error": None, "n_regions": n,
        "original_text": match.get("text", ""),
        "reread_text": reread.get("full_text", ""),
        "crop_png": crop_png, "box": padded_box,
    }
