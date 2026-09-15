"""Offline guard for the MANUAL_ (curated content) retrieval contract.

A manual entry is written to look like a saved session so the retrieval
tools work unmodified, but it is NOT a design run: it has no extraction, no
canonical renders, no description, and its parameter set may be partial.
Phase A taught all three modules to say so.  This test pins what they say.

Twelve assertions, in four groups:

  M1  retrieve_attempt  -- origin="manual_upload" on <attempt>
  M2                    -- a partial parameter set is flagged, with its count
  M3                    -- a COMPLETE set keeps the old <parameters> tag,
                           byte-for-byte (no attribute creep for real runs)
  M4                    -- non-canonical images surface as <extra_image>
  M5                    -- no phantom <missing/> for a description a curated
                           entry never had ... and a REAL attempt still
                           reports its absent description
  M6  retrieve_user_inputs -- origin + the short "manually-written data
                           point" note, and NOT the archive wording
  M7                    -- a real pre-extraction session keeps the archive
                           wording and gains no origin attribute
  M8  db_writer_mm      -- any image in an attempt folder is mirrored ...
  M9                    -- but never propeller_mesh.obj / .json / .txt
  M10 web/app.js        -- its hardcoded parameter list still matches
                           parameter_keys.txt, in the canonical order

M3, M5's second half, M7 and M9 are REGRESSION assertions: they are the
reason a real session's retrieval is unchanged by any of this, and they are
what will fail first if the MANUAL_ branches ever leak.

Why the modules are loaded through a stub loader rather than imported
normally: ``import agents`` pulls the whole agent package, which imports
``trimesh`` via ``tools.render_mesh`` -- a heavy dependency this test has no
use for and which is absent on a plain checkout.  Stubbing keeps the test
runnable anywhere and honest about what it covers: the three modules' own
logic, nothing else.  No Postgres, no R2, no network.

Run from the repo root::

    python extra_utilities/smoke_test_manual_entry_offline.py
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
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

MANUAL_SID = "MANUAL_20260915_143022"
REAL_SID = "ID1899_20260915_124819"
PARTIAL = json.dumps({"bladeCount": 5, "ringThickness": 1.6,
                      "impellerRadius": 70.0}, indent=2)

_failures: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    if ok:
        print(f"OK {name}")
    else:
        _failures.append(f"{name}: {detail}")
        print(f"FAIL {name} - {detail}")


# ---------------------------------------------------------------------------
# Stub loading
# ---------------------------------------------------------------------------
def _stub(name: str, path: Path | None = None) -> types.ModuleType:
    mod = types.ModuleType(name)
    if path is not None:
        mod.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[name] = mod
    return mod


def _load(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:      # pragma: no cover
        raise ImportError(f"cannot load {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_modules() -> tuple[types.ModuleType, types.ModuleType,
                             types.ModuleType]:
    _stub("agents", _REPO_ROOT / "agents")
    _stub("agents.shared", _REPO_ROOT / "agents" / "shared")
    _stub("agents.database_handler", _REPO_ROOT / "agents" / "database_handler")

    pool = _stub("agents.shared.postgres_pool")
    pool.is_enabled = lambda: False              # type: ignore[attr-defined]
    _stub("agents.shared.r2_uploader")
    _stub("agents.shared.voyage_mm")

    writer = _stub("agents.database_handler.db_writer")
    writer.DEFAULT_AGENTS_TO_ACL = ()            # type: ignore[attr-defined]

    activity = _stub("agents.shared.agent_activity")
    activity.generic_tool = lambda *a, **k: (lambda f: f)  # type: ignore[attr-defined]

    _load("agents.shared.attempt_views",
          _REPO_ROOT / "agents" / "shared" / "attempt_views.py")

    tools_pkg = _stub("tools", _REPO_ROOT / "tools")
    common = _load("tools.retrieval_common",
                   _REPO_ROOT / "tools" / "retrieval_common.py")
    tools_pkg.retrieval_common = common          # type: ignore[attr-defined]

    ra = _load("retrieve_attempt_under_test",
               _REPO_ROOT / "tools" / "retrieve_attempt"
               / "retrieve_attempt.py")
    rui = _load("retrieve_user_inputs_under_test",
                _REPO_ROOT / "tools" / "retrieve_user_inputs"
                / "retrieve_user_inputs.py")
    mm = _load("db_writer_mm_under_test",
               _REPO_ROOT / "agents" / "database_handler" / "db_writer_mm.py")
    return ra, rui, mm


def main() -> int:
    ra, rui, mm = _load_modules()

    total = ra._schema_parameter_count()
    if not total:
        print("FAIL - parameter_count.txt unreadable; the partial-set "
              "assertions cannot run")
        return 1
    complete = json.dumps({f"p{i}": i for i in range(total)}, indent=2)

    # ---------------- retrieve_attempt ----------------
    manual = ra._build_attempt_block(
        global_id=114, nnn="001", session_id=MANUAL_SID,
        description_text=None,          # a curated entry has none
        parameters_text=PARTIAL,
        render_refs=[], fetch_failures=[],
        folder="/tmp/114", listing=[("ring_photo.png", 84213)],
        extra_images=[("ring_photo.png", "/tmp/114/ring_photo.png")],
    )
    check("M1_attempt_origin", 'origin="manual_upload"' in manual,
          "a MANUAL_ attempt must announce itself")
    check("M2_partial_flagged",
          'partial="true"' in manual and f'keys="3/{total}"' in manual,
          f'a 3-key set must render partial="true" keys="3/{total}"')
    check("M4_extra_image_surfaced",
          "<extra_images>" in manual and "ring_photo.png" in manual,
          "a non-canonical image must surface as <extra_image>")
    check("M5a_no_phantom_description",
          "description.txt" not in manual,
          "a curated entry never had a description; no <missing/> for it")

    real = ra._build_attempt_block(
        global_id=113, nnn="012", session_id=REAL_SID,
        description_text=None, parameters_text=complete,
        render_refs=[("isometric", "/tmp/113/render_isometric.png")],
        fetch_failures=[], folder="/tmp/113",
        listing=[("render_isometric.png", 40201)], extra_images=[],
    )
    check("M3_complete_set_tag_unchanged",
          "<parameters>" in real and "partial=" not in real,
          "a COMPLETE set must keep the attribute-free <parameters> tag")
    check("M5b_real_attempt_keeps_marker", "description.txt" in real,
          "a real attempt with no description must still report it")
    check("M3b_no_origin_on_real", "origin=" not in real,
          "a real attempt must gain no origin attribute")

    # ---------------- retrieve_user_inputs ----------------
    sess = rui._build_session_block(
        session_id=MANUAL_SID, extraction_text=None,
        queries_text="A five-blade ring propeller with a thin ring.",
        images=[], orphan_notes=[], fetch_failures=[],
        folder=None, listing=None,
    )
    check("M6_session_origin_and_note",
          'origin="manual_upload"' in sess
          and "manually-written data point" in sess
          and "no extraction was archived" not in sess
          and "<user_query>" in sess,
          "a MANUAL_ session needs origin, the short note, no archive "
          "wording, and the raw text still in <user_query>")

    legacy = rui._build_session_block(
        session_id="ID0042_20260101_000000", extraction_text=None,
        queries_text="legacy text", images=[], orphan_notes=[],
        fetch_failures=[], folder=None, listing=None,
    )
    check("M7_real_session_unchanged",
          "no extraction was archived" in legacy and "origin=" not in legacy,
          "a pre-extraction archive keeps its wording and gains no origin")

    # ---------------- db_writer_mm ----------------
    real_folder = ["description.txt", "parameters.json", "propeller_mesh.obj",
                   "render_isometric.png", "render_top.png",
                   "render_blade_sections.png"]
    manual_folder = ["parameters.json", "ring_photo.png", "sketch_2.JPG",
                     "notes.txt"]
    got_real = [f for f in real_folder if mm._RENDER_RE.search(f)]
    got_manual = [f for f in manual_folder if mm._RENDER_RE.search(f)]
    check("M8_manual_images_mirrored",
          got_manual == ["ring_photo.png", "sketch_2.JPG"],
          f"both manual images must be mirrored; got {got_manual}")
    check("M9_real_folder_unchanged_and_no_mesh",
          got_real == ["render_isometric.png", "render_top.png",
                       "render_blade_sections.png"],
          f"a real folder must yield exactly its canonical renders and "
          f"never the mesh; got {got_real}")

    # ---------------- the web form's parameter list ----------------
    # web/app.js hardcodes the 16 names (a static asset cannot read the
    # fragment).  parameter_keys.txt declares BOTH the set and the order
    # canonical, so a copy that drifts would offer the owner a box for a
    # parameter that no longer exists -- or silently omit one.
    keys_file = _REPO_ROOT / "DC_prompt_fragments" / "dc_config" /         "parameter_keys.txt"
    canon = [ln.split()[0].rstrip(":,")
             for ln in keys_file.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    app_js = (_REPO_ROOT / "web" / "app.js").read_text(encoding="utf-8")
    m = re.search(r"const UDB_PARAMS = \[(.*?)\];", app_js, re.S)
    ui = re.findall(r'"([A-Za-z]+)"', m.group(1)) if m else []
    check("M10_web_form_parameters_match", ui == canon,
          f"web/app.js UDB_PARAMS is {ui}, parameter_keys.txt is {canon}")

    print()
    if _failures:
        print(f"FAIL - {len(_failures)} of 12 assertions failed")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("PASS - manual-entry retrieval contract (12 assertions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
