"""Smoke test: Google Cloud Vision OCR connectivity + detection recall.

Runs ``TEXT_DETECTION`` on an annotated test image and prints what
Vision detected (full text + per-word boxes), to confirm two things:

  1. **Setup is correct** — ``GOOGLE_CLOUD_VISION_API_KEY`` + billing +
     API-enablement.  A 403 / error here means one of those is wrong
     (NOT a code bug).
  2. **Detection recall on real imagery** — does Vision catch every
     callout on a hand-annotated render?  Misses here are the F37 risk
     (a region with no detection has no id to escalate to), surfaced
     early on actual data rather than discovered later.
  3. **The feature-layer batch re-read** (``ocr_regions_reread``) against
     the real engine — detect-once + per-region crop + re-OCR — and the
     per-agent crop-attachment gate (``ocr_region_crops_access``) loading
     with its default-OFF flags.

Usage (run from anywhere in the repo / worktree)::

    python extra_utilities/smoke_test_google_vision.py [path-to-image]

The key is loaded from the nearest ``.env`` (walking up from the cwd),
so this works inside a git worktree whose ``.env`` lives in the main
repo root.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Load the nearest .env (walk up from cwd → finds the main-repo .env
# even when running inside a worktree that has none of its own).
load_dotenv(find_dotenv(usecwd=True))

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Import the engine DIRECTLY from its file, bypassing the ``agents``
# package __init__ chain (which eagerly imports the full agent stack +
# langchain).  The engine itself needs only stdlib + ``requests``, so
# this connectivity smoke test runs in a minimal environment without
# the whole app installed.
_ENGINE_PATH = _REPO_ROOT / "agents" / "shared" / "ocr" / "google_vision.py"
_spec = importlib.util.spec_from_file_location("ocr_google_vision", _ENGINE_PATH)
_engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_engine)  # type: ignore[union-attr]
detect_text = _engine.detect_text
OCRConfigError = _engine.OCRConfigError
OCRRequestError = _engine.OCRRequestError

DEFAULT_IMAGE = (
    _REPO_ROOT
    / "extra_utilities"
    / "embedding_tests"
    / "sketches"
    / "renderwinfo_test1_image.png"
)

# Known callouts on renderwinfo_test1_image.png — used for an eyeball
# recall check when that image is the target.
EXPECTED_CALLOUTS = ["3.5", "thick", "Diameter", "136", "Chord", "8mm"]


def main() -> int:
    img = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IMAGE
    if not img.is_file():
        print(f"FAIL: image not found: {img}")
        return 2

    print(f"Image: {img}")
    try:
        result = detect_text(img, language_hints=["en"])
    except OCRConfigError as exc:
        print(f"\nCONFIG ERROR: {exc}")
        return 2
    except OCRRequestError as exc:
        print(
            "\nREQUEST ERROR (check: Vision API enabled? billing active? "
            "key restricted to Vision?):\n  "
            f"{exc}"
        )
        return 1

    full_text = result["full_text"]
    regions = result["regions"]
    words = result.get("words", [])

    print("\n--- FULL TEXT ---")
    print(full_text if full_text.strip() else "(none detected)")

    print(f"\n--- CALLOUT REGIONS ({len(regions)})  [the ocr_regions menu] ---")
    for r in regions:
        b = r["box"]
        print(
            f"  [{r['id']:>2}] {r['text']!r:<28} "
            f"box=({b['x0']},{b['y0']})-({b['x1']},{b['y1']})  "
            f"words={r['word_ids']}"
        )

    print(f"\n--- RAW WORD BOXES ({len(words)}) ---")
    for w in words:
        b = w["box"]
        print(
            f"  [{w['id']:>2}] {w['text']!r:<18} "
            f"box=({b['x0']},{b['y0']})-({b['x1']},{b['y1']})"
        )

    exit_code = 0
    if img.name == DEFAULT_IMAGE.name:
        joined = full_text.lower()
        print("\n--- RECALL CHECK (renderwinfo_test1 known callouts) ---")
        missed = []
        for tok in EXPECTED_CALLOUTS:
            hit = tok.lower() in joined
            print(f"  {'OK  ' if hit else 'MISS'}  {tok}")
            if not hit:
                missed.append(tok)
        if missed:
            print(
                f"\nNOTE: {len(missed)} expected token(s) not detected: "
                f"{missed}"
            )
            print(
                "  This is a detection-recall gap (the F37 risk), NOT a "
                "key/setup failure — connectivity still succeeded."
            )
        else:
            print("\nAll known callouts detected. Connectivity + recall good.")

    # Exercise the NEW feature-layer batch re-read (against the same real
    # engine) + the per-agent crop-attachment gate.  Both are non-fatal:
    # a failure here prints but does not fail the connectivity check.
    if regions:
        _smoke_batch_reread(img, [r["id"] for r in regions[:3]])
    _smoke_crop_gate()

    print("\nConnectivity OK (HTTP 200 from Vision).")
    return exit_code


def _smoke_batch_reread(img: Path, region_ids: list) -> None:
    """Exercise ``ocr_regions_reread`` on real regions.  Loads feature.py
    by file path and points its internal ``from agents...google_vision
    import detect_text`` at the already-loaded REAL engine, so no agents /
    langchain stack is needed (mirrors the engine import above)."""
    print(f"\n--- BATCH RE-READ (ocr_regions_reread {region_ids}) ---")
    import types as _types
    try:
        for name in ("agents", "agents.shared", "agents.shared.ocr"):
            if name not in sys.modules:
                mod = _types.ModuleType(name)
                mod.__path__ = []  # mark as a package
                sys.modules[name] = mod
        sys.modules["agents.shared.ocr.google_vision"] = _engine
        feat_path = _REPO_ROOT / "agents" / "shared" / "ocr" / "feature.py"
        spec = importlib.util.spec_from_file_location(
            "agents.shared.ocr.feature", feat_path)
        feat = importlib.util.module_from_spec(spec)
        sys.modules["agents.shared.ocr.feature"] = feat
        spec.loader.exec_module(feat)  # type: ignore[union-attr]
        batch = feat.ocr_regions_reread(str(img), region_ids)
    except Exception as exc:  # noqa: BLE001 — non-fatal for the smoke test
        print(f"  (skipped — {type(exc).__name__}: {exc})")
        return
    if not batch.get("ok"):
        print(f"  batch FAILED (whole-call): {batch.get('error')}")
        return
    print(
        f"  detect-once on {batch['n_regions']} region(s); re-read "
        f"{len(batch['results'])}, invalid {len(batch['invalid'])}"
    )
    for r in batch["results"]:
        status = "ok" if r["ok"] else f"ERR {r['error']}"
        print(
            f"    [region {r['region_id']}] {status}: {r['reread_text']!r} "
            f"(was {r['original_text']!r})  "
            f"crop_png={'yes' if r['crop_png'] else 'no'}"
        )
    for inv in batch["invalid"]:
        print(f"    [region {inv['region_id']}] INVALID: {inv['error']}")


def _smoke_crop_gate() -> None:
    """Sanity-check the per-agent crop-attachment gate (pure settings; no
    network).  Confirms the module loads and every eligible agent defaults
    to crops OFF."""
    print("\n--- CROP GATE (ocr_region_crops_access) ---")
    try:
        from workflow_settings import ocr_region_crops_access as crops
    except Exception as exc:  # noqa: BLE001
        print(f"  (skipped — could not import: {type(exc).__name__}: {exc})")
        return
    flags = crops.get_all()
    all_off = not any(flags.values())
    print(f"  eligible agents: {list(crops.DEFAULT_AGENTS)}")
    print(f"  per-agent crop flags: {flags}")
    print(f"  all default OFF: {'OK' if all_off else 'UNEXPECTED (should be OFF)'}")


if __name__ == "__main__":
    raise SystemExit(main())
