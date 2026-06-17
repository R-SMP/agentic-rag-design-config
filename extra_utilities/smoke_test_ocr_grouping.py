"""Unit test for OCR callout grouping (``group_words_into_regions``).

Pure-Python, **no API call** — exercises the SPATIAL grouping logic
with synthetic word boxes, including the paths the live render images
do not cover:

  * two callouts on the **same horizontal band but far apart** (the
    gap-split path),
  * **order independence** — grouping is by image-space proximity, not
    by the order words arrive in (the direct proof that this is
    spatial, not sequence-based), and
  * **diagonal** and **vertically-stacked** callouts — which the 2D
    proximity model handles but a horizontal-line model would not.

Run (works in a minimal env — only needs ``requests`` importable, which
the engine module imports at module load)::

    python extra_utilities/smoke_test_ocr_grouping.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Load the engine module directly from its file — avoids the ``agents``
# package __init__ chain (langchain), same as the connectivity smoke
# test.  ``group_words_into_regions`` is pure geometry, no network.
_ENGINE_PATH = _REPO_ROOT / "agents" / "shared" / "ocr" / "google_vision.py"
_spec = importlib.util.spec_from_file_location("ocr_google_vision", _ENGINE_PATH)
_engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_engine)  # type: ignore[union-attr]
group = _engine.group_words_into_regions


def w(wid: int, text: str, x0: int, y0: int, x1: int, y1: int) -> dict:
    """Build a word record like the engine produces."""
    return {"id": wid, "text": text,
            "box": {"x0": x0, "y0": y0, "x1": x1, "y1": y1}}


def texts(regions: list[dict]) -> list[str]:
    return [r["text"] for r in regions]


_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f"   -- {detail}" if (detail and not cond) else ""))
    if not cond:
        _failures.append(name)


def main() -> int:
    print("group_words_into_regions - spatial grouping unit test\n")

    # A) close words on one line merge into a single callout.
    a = group([
        w(1, "Diameter", 0, 0, 80, 20),
        w(2, "136", 90, 0, 130, 20),
        w(3, "mm", 140, 0, 170, 20),
    ])
    check("A  close words on a line merge",
          len(a) == 1 and texts(a) == ["Diameter 136 mm"],
          f"got {texts(a)}")

    # B) same horizontal band, far apart -> two regions (the gap-split
    #    path the real images never exercise).
    b = group([
        w(1, "3.5", 0, 0, 30, 20), w(2, "mm", 40, 0, 70, 20),
        w(3, "thick", 80, 0, 130, 20),
        w(4, "Chord", 500, 0, 560, 20), w(5, "8mm", 570, 0, 610, 20),
    ])
    check("B  same band but far apart splits in two",
          len(b) == 2 and set(texts(b)) == {"3.5 mm thick", "Chord 8mm"},
          f"got {texts(b)}")

    # C) different vertical bands stay separate, ordered top-to-bottom.
    c = group([
        w(1, "3.5", 0, 0, 30, 20), w(2, "mm", 40, 0, 70, 20),
        w(3, "thick", 80, 0, 130, 20),
        w(4, "Diameter", 0, 100, 80, 120), w(5, "136", 90, 100, 130, 120),
        w(6, "mm", 140, 100, 170, 120),
    ])
    check("C  different lines stay separate",
          len(c) == 2, f"got {len(c)}: {texts(c)}")
    check("C  ordered + ids top-to-bottom",
          texts(c) == ["3.5 mm thick", "Diameter 136 mm"]
          and [r["id"] for r in c] == [1, 2],
          f"got {texts(c)} ids {[r['id'] for r in c]}")

    # D) ORDER INDEPENDENCE — scrambled input yields identical grouping.
    #    This is the proof that grouping is spatial, not sequence-based.
    d = group([
        w(3, "mm", 140, 0, 170, 20),
        w(1, "Diameter", 0, 0, 80, 20),
        w(2, "136", 90, 0, 130, 20),
    ])
    check("D  order-independent (spatial, not sequence)",
          len(d) == 1 and texts(d) == ["Diameter 136 mm"],
          f"got {texts(d)}")

    # E) empty input.
    check("E  empty input -> no regions", group([]) == [])

    # F) single word -> one region, carrying its word id.
    f = group([w(7, "136", 0, 0, 40, 20)])
    check("F  single word -> one region",
          len(f) == 1 and texts(f) == ["136"] and f[0]["word_ids"] == [7],
          f"got {f}")

    # G) union box spans all members.
    g = group([
        w(1, "Diameter", 10, 100, 80, 120),
        w(2, "136", 90, 101, 130, 119),
        w(3, "mm", 140, 100, 180, 120),
    ])
    check("G  union box spans all members",
          g[0]["box"] == {"x0": 10, "y0": 100, "x1": 180, "y1": 120},
          f"got {g[0]['box']}")

    # H) DIAGONAL callout — words step in both x and y (text along an
    #    arrow).  The old line-based grouping would split this (no
    #    vertical overlap end-to-end); 2D proximity keeps it as one.
    h = group([
        w(1, "3.5", 0, 0, 30, 20),
        w(2, "mm", 35, 15, 65, 35),
        w(3, "thick", 70, 30, 120, 50),
    ])
    check("H  diagonal callout stays one region (2D win)",
          len(h) == 1 and texts(h) == ["3.5 mm thick"],
          f"got {texts(h)}")

    # I) STACKED callout — a second line directly under the first.  The
    #    old line-based grouping would make two regions; 2D merges them.
    i = group([
        w(1, "Thickness", 0, 0, 100, 20),
        w(2, "2.28", 0, 24, 40, 44),
        w(3, "mm", 45, 24, 75, 44),
    ])
    check("I  stacked callout merges into one region (2D win)",
          len(i) == 1 and texts(i) == ["Thickness 2.28 mm"],
          f"got {texts(i)}")

    print()
    if _failures:
        print(f"FAILED: {len(_failures)} check(s): {_failures}")
        return 1
    print("All grouping checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
