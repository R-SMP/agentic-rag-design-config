"""Smoke test for database_search MULTIMODAL read-routing (chunks_mm).

Exercises the single-vector-multimodal path of `database_search`
against the LIVE Railway Postgres `chunks_mm` table + the Voyage API:

  1. Multimodal routing — a query in single-vector-multimodal mode hits
     `chunks_mm`, embeds with voyage-multimodal-3.5, and the
     <search_meta> reports db="chunks_mm" + the Voyage model + mode.
  2. Image references — a session-level query surfaces <image_ref>
     elements (chunks_mm holds user-image + render rows).
  3. Graceful LOGGED fallback — with VOYAGE_API_KEY unavailable, the
     multimodal path falls back to text-only `chunks`, reports
     db="chunks" + a fallback note, and logs an ERROR.

Run with the conda interpreter (voyageai + DB deps) + a populated .env::

    "C:/Users/vince/miniconda3/python.exe" extra_utilities/db_design/smoke_test_database_search_mm.py

Read-only against the DB (database_search never writes chunks).  Makes
a few live Voyage + OpenAI calls (free-tier sized).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass

try:
    from dotenv import load_dotenv as _load_dotenv  # type: ignore
    _load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

from agents.shared import postgres_pool, voyage_mm
from workflow_settings import db_options_config
from tools.database_search import database_search as ds

_PASS = 0
_FAIL = 0


def _check(cond: bool, label: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"[assert] OK    - {label}")
    else:
        _FAIL += 1
        print(f"[assert] FAIL  - {label}")


def main() -> int:
    if not postgres_pool.is_enabled():
        print("FAIL - postgres not enabled (set DATABASE_PUBLIC_URL in .env)")
        return 1

    # ---- 1. Multimodal routing ------------------------------------
    print("\n--- 1. Multimodal routing (single-vector-multimodal) ---")
    xml = ds._database_search_impl(
        caller_agent="planner",
        query="hand-drawn propeller blade sketch with ring",
        n=5,
        attempt_specific_flag=False,
        metafilters=None,
        db_mode=db_options_config.MODE_SINGLE_VECTOR,
    )
    print(xml[:400].replace("\n", " ") + (" ..." if len(xml) > 400 else ""))
    _check('db="chunks_mm"' in xml, "routed to chunks_mm")
    _check("voyage/voyage-multimodal-3.5/2048" in xml, "embedded with the Voyage model")
    _check('mode="single-vector-multimodal"' in xml, "search_meta reports the selected mode")
    _check('error=' not in xml.split("\n", 1)[0], "no error in the multimodal path")

    # ---- 2. Image references -------------------------------------
    print("\n--- 2. Image references (<image_ref>) ---")
    n_img = xml.count("<image_ref ")
    print(f"  <image_ref> elements in the response: {n_img}")
    _check(n_img >= 1, "at least one <image_ref> surfaced (user images / renders)")
    if n_img:
        _check("<caption>" in xml, "image refs carry a <caption>")
        _check('r2_key=' in xml, "image refs carry an r2_key")

    # ---- 3. Graceful LOGGED fallback -----------------------------
    print("\n--- 3. Graceful LOGGED fallback (no VOYAGE_API_KEY) ---")
    saved_key = os.environ.pop("VOYAGE_API_KEY", None)
    voyage_mm._client = None  # noqa: SLF001 — force a fresh (keyless) client build
    # Capture ERROR logs to confirm the fallback is logged.
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    cap = _Capture(level=logging.ERROR)
    logging.getLogger("propeller_agent").addHandler(cap)
    try:
        xml_fb = ds._database_search_impl(
            caller_agent="planner",
            query="hand-drawn propeller blade sketch with ring",
            n=5,
            attempt_specific_flag=False,
            metafilters=None,
            db_mode=db_options_config.MODE_SINGLE_VECTOR,
        )
    finally:
        logging.getLogger("propeller_agent").removeHandler(cap)
        if saved_key is not None:
            os.environ["VOYAGE_API_KEY"] = saved_key
        voyage_mm._client = None  # noqa: SLF001 — reset so later runs re-auth

    print(xml_fb[:300].replace("\n", " ") + (" ..." if len(xml_fb) > 300 else ""))
    _check('db="chunks"' in xml_fb, "fell back to the text-only chunks table")
    _check("openai/text-embedding-3-large" in xml_fb, "re-embedded with OpenAI on fallback")
    _check("fallback=" in xml_fb, "search_meta carries a fallback note")
    _check(
        any("multimodal embed FAILED" in (r.getMessage()) for r in records),
        "fallback logged a propeller_agent ERROR",
    )

    try:
        postgres_pool.close_pool()
    except Exception:
        pass

    print(f"\n--- Summary ---\n  passed: {_PASS}\n  failed: {_FAIL}")
    if _FAIL:
        print("FAIL - database_search multimodal smoke test had failures.")
        return 1
    print("PASS - database_search multimodal smoke test green.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
