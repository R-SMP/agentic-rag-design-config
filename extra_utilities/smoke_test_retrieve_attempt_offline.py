"""Offline smoke test for ``retrieve_attempt``'s Postgres parameters fallback.

NO database, NO R2, NO network.  Where
``extra_utilities/db_design/smoke_test_retrieve_attempt.py`` exercises the
whole tool against live Railway Postgres + Cloudflare R2, this one isolates
the one behaviour that has no infrastructure of its own: when the R2
artefact is gone, the parameters must still come back, out of
``dc_attempts.parameters_json``.

Run from repo root::

    python extra_utilities/smoke_test_retrieve_attempt_offline.py

7 named assertions:

  A1  <parameters> is emitted even with R2 unreachable.
  A2  the emitted values are the ones the database held.
  A3  no <missing .../parameters.json> marker for the recovered attempt.
  A4  a NULL parameters_json still yields <missing/> (nothing is invented).
  A5  an unknown global id still reports status="not_found".
  A6  the fallback writes NOTHING into attempts/_retrieved/<gid>/.
  A7  the CDATA round-trips to the original dict (no double-encoding).

A6 and A7 are the two traps.  A6: the cache branch fires on "folder exists
and is non-empty", so persisting the fallback's parameters.json when nothing
else was fetched would make every later call take the cache path and stop
re-trying R2 for the description and the renders.  A7: psycopg returns JSONB
as a dict; if it ever handed back a ``str`` instead, ``json.dumps`` would
wrap the already-serialised text in quotes and the agent would read a quoted
blob instead of a parameter set.

Why the module is loaded through a stub loader rather than imported
normally: ``import agents`` pulls in the whole agent package, which imports
``trimesh`` via ``tools.render_mesh``.  That is a heavy runtime dependency
this test has no use for, and it is absent on a plain developer checkout.
Stubbing keeps the test runnable anywhere and keeps it honest about what it
covers -- ``retrieve_attempt``'s own logic, nothing else.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import types
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass


SESSION = "IDOFFLINE_20260914_000000"
PARAMS = {"bladeCount": 5, "impellerRadius": 26.0, "ringThickness": 1.7}
GID_OK = 501        # dc_attempts row WITH parameters_json, nothing in R2
GID_NULL = 502      # defensive: a row whose parameters_json came back None
GID_ABSENT = 999    # no dc_attempts row at all


def _stub_package(name: str, path: Path | None = None) -> types.ModuleType:
    """Register an empty module under *name* so imports of it succeed."""
    mod = types.ModuleType(name)
    if path is not None:
        mod.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[name] = mod
    return mod


def _load_from_path(name: str, path: Path) -> types.ModuleType:
    """Import one module file directly, bypassing its package's __init__."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:      # pragma: no cover - defensive
        raise ImportError(f"cannot load {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_retrieve_attempt() -> types.ModuleType:
    """Load ``tools.retrieve_attempt.retrieve_attempt`` in isolation."""
    _stub_package("agents", _REPO_ROOT / "agents")
    _stub_package("agents.shared", _REPO_ROOT / "agents" / "shared")
    _stub_package("agents.database_handler",
                  _REPO_ROOT / "agents" / "database_handler")
    _stub_package("agents.database_handler.db_writer")

    pool = _stub_package("agents.shared.postgres_pool")
    pool.is_enabled = lambda: False           # type: ignore[attr-defined]

    activity = _stub_package("agents.shared.agent_activity")
    activity.generic_tool = lambda *a, **k: (lambda f: f)  # type: ignore[attr-defined]

    # attempt_views is pure settings-reading, so load the real thing: the
    # render-view scope in the response should be the product's, not a fake.
    _load_from_path("agents.shared.attempt_views",
                    _REPO_ROOT / "agents" / "shared" / "attempt_views.py")

    tools_pkg = _stub_package("tools", _REPO_ROOT / "tools")
    common = _load_from_path("tools.retrieval_common",
                             _REPO_ROOT / "tools" / "retrieval_common.py")
    tools_pkg.retrieval_common = common       # type: ignore[attr-defined]

    return _load_from_path(
        "retrieve_attempt_under_test",
        _REPO_ROOT / "tools" / "retrieve_attempt" / "retrieve_attempt.py",
    )


def main() -> int:
    mod = _load_retrieve_attempt()

    tmp_root = Path(tempfile.mkdtemp(prefix="smoke_retrieve_attempt_offline_"))
    failures: list[str] = []
    try:
        # Isolate the retrieval cache, cut R2 off entirely, silence the
        # rag_queries write, and answer the resolver from a fixture.
        mod.ATTEMPTS_DIR = tmp_root
        mod._r2_bucket_and_client = lambda: (None, None)
        mod._log_to_rag_queries = lambda **kwargs: None
        mod._resolve_global_attempt_ids = lambda ids: {
            GID_OK: {"session_id": SESSION, "nnn": "003",
                     "has_renders": True, "parameters_json": PARAMS},
            GID_NULL: {"session_id": SESSION, "nnn": "004",
                       "has_renders": False, "parameters_json": None},
            GID_ABSENT: None,
        }

        xml = mod._run_retrieve_attempt(
            caller_agent="dc_input_creator",
            global_attempt_ids=[GID_OK, GID_NULL, GID_ABSENT],
        )

        def check(name: str, ok: bool, detail: str = "") -> None:
            if ok:
                print(f"OK {name}")
            else:
                failures.append(f"{name}: {detail}")
                print(f"FAIL {name} - {detail}")

        check("A1_parameters_present", "<parameters>" in xml,
              "no <parameters> despite the database holding the snapshot")
        check("A2_values_are_the_db_values", '"bladeCount": 5' in xml,
              "the seeded parameter values are not in the response")
        check(
            "A3_no_missing_marker_for_recovered_attempt",
            f"attempts/003__{GID_OK}/parameters.json" not in xml,
            "parameters.json is still reported missing",
        )
        check(
            "A4_null_params_still_missing",
            f"attempts/004__{GID_NULL}/parameters.json" in xml,
            "a NULL parameters_json must still yield <missing/>",
        )
        check(
            "A5_unknown_id_not_found",
            f'<attempt id="{GID_ABSENT}" status="not_found"/>' in xml,
            "unknown global id no longer reports not_found",
        )
        check(
            "A6_fallback_does_not_touch_the_cache",
            not list(mod._retrieved_dir(GID_OK).glob("*")),
            f"the fallback wrote into {mod._retrieved_dir(GID_OK)}, which "
            "would make later calls take the cache path and stop "
            "re-trying R2",
        )

        round_tripped = None
        detail = ""
        try:
            body = xml.split("<parameters>")[1].split("</parameters>")[0]
            round_tripped = json.loads(body.split("CDATA[")[1].split("]]")[0])
        except Exception as exc:
            detail = f"CDATA is not valid JSON (double-encoded?): {exc}"
        check("A7_cdata_round_trips", round_tripped == PARAMS,
              detail or f"decoded {round_tripped!r}, expected {PARAMS!r}")

        print()
        if failures:
            print(f"FAIL - {len(failures)} of 7 assertions failed")
            return 1
        print("PASS - retrieve_attempt offline fallback test (7 assertions)")
        return 0
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
