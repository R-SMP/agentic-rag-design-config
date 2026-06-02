"""Smoke test for agents/loader.py::_resolve_session_name (Phase 3E).

Exercises BOTH output shapes:

  1. Happy path — Postgres reachable, ``session_counter`` SEQUENCE
     exists.  Slug = ``ID{nnn:03d}_{YYYYMMDD_HHMMSS}``.  Counter
     advances by exactly 1 between two consecutive calls.
  2. Fallback path — postgres_pool.is_enabled() forced to False
     (monkey-patched in this test).  Slug =
     ``ID_{YYYYMMDD_HHMMSS}_{microseconds:06d}``.

Cleanup: this test does NOT write any rows or change SEQUENCE
state in unexpected ways.  The happy-path calls advance
``session_counter`` by 2 (one per call); that's expected and
fine — the sequence is monotonic and the next real DH save will
just see the bumped value.

Run from repo root::

    python extra_utilities/db_design/smoke_test_resolve_session_name.py

Exits 0 on full pass; non-zero on any failure with a clear
message at the failure point.
"""

from __future__ import annotations

import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Force stdout/stderr to UTF-8 with replace-on-error so the test
# runs cleanly on Windows consoles (cp1252 default).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass

try:
    from dotenv import load_dotenv as _load_dotenv  # type: ignore
    _load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

from agents.shared import postgres_pool  # noqa: E402
from agents import loader as _loader  # noqa: E402


_HAPPY_RE = re.compile(r"^ID(\d{3,})_(\d{8}_\d{6})$")
_FALLBACK_RE = re.compile(r"^ID_(\d{8}_\d{6})_(\d{6})$")


def _run_happy_path() -> int:
    print("[happy]    calling _resolve_session_name() x2 (expecting "
          "Postgres SEQUENCE)")
    s1 = _loader._resolve_session_name()
    s2 = _loader._resolve_session_name()
    print(f"[happy]    s1 = {s1}")
    print(f"[happy]    s2 = {s2}")

    m1 = _HAPPY_RE.match(s1)
    m2 = _HAPPY_RE.match(s2)
    if not m1:
        print(
            f"FAIL - s1 doesn't match happy-path regex "
            f"{_HAPPY_RE.pattern!r}: {s1!r}"
        )
        return 1
    if not m2:
        print(
            f"FAIL - s2 doesn't match happy-path regex "
            f"{_HAPPY_RE.pattern!r}: {s2!r}"
        )
        return 1
    n1, n2 = int(m1.group(1)), int(m2.group(1))
    if n2 != n1 + 1:
        print(
            f"FAIL - SEQUENCE did not advance by 1: "
            f"s1 nnn={n1}, s2 nnn={n2}"
        )
        return 1
    print(
        f"[happy]    PASS — slug matches ID{{nnn:03d}}_{{ts}}, "
        f"SEQUENCE advanced {n1} → {n2}"
    )
    return 0


def _run_fallback_path() -> int:
    print()
    print("[fallback] forcing postgres_pool.is_enabled() = False")
    original_is_enabled = postgres_pool.is_enabled

    def _fake_is_enabled() -> bool:
        return False

    postgres_pool.is_enabled = _fake_is_enabled
    try:
        slug = _loader._resolve_session_name()
    finally:
        postgres_pool.is_enabled = original_is_enabled

    print(f"[fallback] slug = {slug}")
    m = _FALLBACK_RE.match(slug)
    if not m:
        print(
            f"FAIL - fallback slug doesn't match "
            f"{_FALLBACK_RE.pattern!r}: {slug!r}"
        )
        return 1
    # Sanity-check the microsecond field
    micros = int(m.group(2))
    if not (0 <= micros <= 999999):
        print(
            f"FAIL - fallback microseconds out of range: {micros}"
        )
        return 1
    print(
        "[fallback] PASS — slug matches "
        "ID_{ts}_{microseconds:06d}, micros in [0, 999999]"
    )
    return 0


def main() -> int:
    if not postgres_pool.is_enabled():
        print(
            "FAIL - postgres_pool not enabled.  Cannot exercise "
            "happy path; set DATABASE_PUBLIC_URL in .env."
        )
        return 1

    rc = 1
    try:
        # Happy path first (needs the SEQUENCE to exist; if the
        # migration hasn't run, this fails — that's diagnostic).
        rc = _run_happy_path()
        if rc != 0:
            return rc
        # Fallback path.
        rc = _run_fallback_path()
        if rc != 0:
            return rc
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        try:
            postgres_pool.close_pool()
        except Exception:
            pass

    print()
    print("PASS - both _resolve_session_name code paths verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
