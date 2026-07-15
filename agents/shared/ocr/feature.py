"""OCR feature-integration layer — the single entry point chain tools call.

`view_images`, `read_user_inputs` and `retrieve_user_inputs` all
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


def ocr_regions_reread(
    image_source: "bytes | str",
    region_ids: "list[int]",
    *,
    pad_frac: float = 0.2,
    upscale: float = 3.0,
) -> dict:
    """Re-OCR one or more detected regions of an image at higher resolution.

    **Stateless** (the boxes were computed in an earlier tool call): runs
    whole-image detection **once** — grouping is deterministic, so the
    region ids match the earlier pass — then, for each requested id
    (deduplicated, input order preserved), crops its box (padded by
    *pad_frac* on each side, clamped to the image), upscales the crop by
    *upscale*, and re-runs the engine on the crop.  The single whole-image
    detection (the expensive call) is shared across all regions, so N
    regions cost 1 detection + N small crop re-OCRs — not N detections.

    **Non-fatal**: whole-call problems (engine/PIL import, bad image,
    detection failure) return ``ok=False`` + ``error``.  A per-region
    problem never aborts the call — an out-of-range id (the F38 case)
    lands in ``invalid``; a per-region crop/re-OCR failure lands in that
    region's own result with ``ok=False`` + ``error``.

    Returns dict with keys:
      * ``ok`` (bool), ``error`` (str | None) — whole-call status
      * ``n_regions`` (int) — regions detected on the full image
      * ``results`` (list) — one entry per VALID requested id, each a dict
        ``{region_id, ok, error, original_text, reread_text, crop_png, box}``
        in the same order the ids were requested
      * ``invalid`` (list) — ``{region_id, error}`` for ids not detected

    *image_source* is a file path or raw image bytes.
    """
    fail = {
        "ok": False, "error": None, "n_regions": 0,
        "results": [], "invalid": [],
    }

    try:
        import io

        from PIL import Image

        from agents.shared.ocr.google_vision import detect_text
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        return {**fail, "error": f"OCR/PIL import failed: {exc}"}

    # Deduplicate ids, preserving first-seen order.
    seen: set = set()
    ordered_ids: list = []
    for rid in region_ids:
        if rid not in seen:
            seen.add(rid)
            ordered_ids.append(rid)

    # 1) Detect on the full image ONCE to recover every region's box.
    try:
        full = detect_text(image_source, language_hints=["en"])
    except Exception as exc:  # noqa: BLE001
        return {**fail, "error": f"detection failed: {exc}"}
    regions = full.get("regions") or []
    n = len(regions)
    by_id = {r.get("id"): r for r in regions}

    # 2) Open the image ONCE (shared across all crops).
    try:
        if isinstance(image_source, (bytes, bytearray)):
            im = Image.open(io.BytesIO(bytes(image_source)))
        else:
            im = Image.open(image_source)
        im = im.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        return {**fail, "n_regions": n, "error": f"could not open image: {exc}"}

    # 3) Crop + upscale + re-OCR each requested region.
    results: list = []
    invalid: list = []
    for region_id in ordered_ids:
        match = by_id.get(region_id)
        if match is None:
            invalid.append({
                "region_id": region_id,
                "error": (
                    f"region {region_id} not found — {n} region(s) detected "
                    f"(valid ids 1..{n})" if n else "no text regions detected"
                ),
            })
            continue
        results.append(_reread_one_region(
            im, match, region_id, detect_text,
            pad_frac=pad_frac, upscale=upscale,
        ))

    return {
        "ok": True, "error": None, "n_regions": n,
        "results": results, "invalid": invalid,
    }


def _reread_one_region(im, match, region_id, detect_text, *, pad_frac, upscale):
    """Crop + upscale + re-OCR a single already-located region on an open
    image.  **Non-fatal**: returns a per-region result dict (never raises).
    Keys: ``region_id, ok, error, original_text, reread_text, crop_png, box``.
    """
    import io

    base = {
        "region_id": region_id, "ok": False, "error": None,
        "original_text": match.get("text", ""),
        "reread_text": "", "crop_png": None, "box": None,
    }

    # Padded, clamped crop box.
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
        return {**base, "error": "degenerate crop box"}
    padded_box = {"x0": x0, "y0": y0, "x1": x1, "y1": y1}

    # Crop + upscale + encode.
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
        return {**base, "box": padded_box,
                "error": f"crop/upscale failed: {exc}"}

    # Re-OCR the upscaled crop.
    try:
        reread = detect_text(crop_png, language_hints=["en"])
    except Exception as exc:  # noqa: BLE001
        return {**base, "box": padded_box, "crop_png": crop_png,
                "error": f"re-OCR failed: {exc}"}

    return {**base, "ok": True, "box": padded_box, "crop_png": crop_png,
            "reread_text": reread.get("full_text", "")}


def ocr_region_reread(
    image_source: "bytes | str",
    region_id: int,
    *,
    pad_frac: float = 0.2,
    upscale: float = 3.0,
) -> dict:
    """Single-region convenience wrapper over :func:`ocr_regions_reread`.

    Returns the legacy flat dict (``ok`` / ``error`` / ``n_regions`` /
    ``original_text`` / ``reread_text`` / ``crop_png`` / ``box``) for the
    one region, so existing callers + the smoke test keep working.
    """
    batch = ocr_regions_reread(
        image_source, [region_id], pad_frac=pad_frac, upscale=upscale,
    )
    legacy = {
        "ok": False, "error": batch.get("error"),
        "n_regions": batch.get("n_regions", 0),
        "original_text": "", "reread_text": "", "crop_png": None, "box": None,
    }
    if not batch.get("ok"):
        return legacy
    if batch["results"]:
        r = batch["results"][0]
        return {
            "ok": r["ok"], "error": r["error"],
            "n_regions": batch["n_regions"],
            "original_text": r["original_text"],
            "reread_text": r["reread_text"],
            "crop_png": r["crop_png"], "box": r["box"],
        }
    if batch["invalid"]:
        return {**legacy, "error": batch["invalid"][0]["error"]}
    return legacy
