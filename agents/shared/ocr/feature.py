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
