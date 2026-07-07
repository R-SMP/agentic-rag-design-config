"""Smoke test for the ``generate_propeller_mesh`` tool.

Runs the tool end-to-end against whatever RhinoCompute server
``RHINO_COMPUTE_URL`` points at (per the loaded .env), with a
hard-coded sample parameter set.  Creates a fresh timestamped attempt
folder under ``ATTEMPTS_DIR`` and writes ``propeller_mesh.obj`` there.

How to run
----------

From inside the docker container (preferred — uses the container's
view of ``RHINO_COMPUTE_URL`` / ``RHINO_COMPUTE_API_KEY``, matching the
deployed config)::

    docker compose exec app python extra_utilities/smoke_test_generate_mesh.py

From your host (uses the host's .env / venv; mostly useful when
RhinoCompute is reachable from the laptop but you don't want to
exercise the container path)::

    python extra_utilities/smoke_test_generate_mesh.py

Outcomes
--------

Success prints something like::

    Mesh saved to /app/attempts/smoke_20260520_153000/propeller_mesh.obj
    (12345 bytes, 678 vertices). Parts: MeshFinal.

A reachability problem prints ``RhinoCompute error: ...``.  An
invalid / missing API key surfaces as a 401 inside that error string.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Make the repo importable when run as a plain script.
_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Importing config.py triggers ``load_dotenv``; this is what populates
# RHINO_COMPUTE_URL / RHINO_COMPUTE_API_KEY from the .env file.
from config import ATTEMPTS_DIR, RHINO_COMPUTE_URL, RHINO_COMPUTE_API_KEY
from tools.generate_mesh.generate_mesh import generate_propeller_mesh


# Sample parameter set — sensible defaults for a 4-bladed propeller.
# Edit any value here to test a different design before re-running.
SAMPLE_PARAMS: dict[str, int | float] = {
    "bladeCount":         3,
    "impellerRadius":     60.0,
    "impellerThickness":  1.0,
    "innerThickness":     6.0,
    "innerMaxPos":        4,
    "innerCamber":        4.0,
    "innerChord":         11.0,
    "innerAngle":         2.0,
    "middlePos":          0.3,
    "middleChord":        20.0,
    "middleAngle":        15.0,
    "outerThickness":     24.0,
    "outerMaxPos":        4,
    "outerCamber":        4.0,
    "outerChord":         15.0,
    "outerAngle":         10.0,
}


def _print_env_summary() -> None:
    key_present = bool(RHINO_COMPUTE_API_KEY)
    print("=== RhinoCompute configuration ===")
    print(f"  RHINO_COMPUTE_URL     : {RHINO_COMPUTE_URL!r}")
    key_label = "<set>" if key_present else "<NOT SET>"
    suffix = f" ({len(RHINO_COMPUTE_API_KEY)} chars)" if key_present else ""
    print(f"  RHINO_COMPUTE_API_KEY : {key_label}{suffix}")
    print(f"  ATTEMPTS_DIR          : {ATTEMPTS_DIR}")
    print()


def _make_attempt_dir() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = ATTEMPTS_DIR / f"smoke_{ts}"
    # If two runs land in the same second, suffix _2, _3, ... so we
    # never reuse a folder that already has a propeller_mesh.obj
    # (the tool refuses to overwrite).
    n = 1
    candidate = folder
    while candidate.exists():
        n += 1
        candidate = folder.with_name(f"{folder.name}_{n}")
    candidate.mkdir(parents=True, exist_ok=False)
    print(f"Created attempt folder: {candidate}")
    return candidate


def main() -> int:
    _print_env_summary()
    folder = _make_attempt_dir()

    print("Calling generate_propeller_mesh ...")
    args = {"output_dir": str(folder.resolve()), **SAMPLE_PARAMS}
    try:
        # The @tool decorator's ``.invoke({...})`` is the standard call
        # path; it forwards the dict as keyword arguments to the
        # wrapped function.
        result = generate_propeller_mesh.invoke(args)
    except Exception as exc:
        print(f"\nUNEXPECTED EXCEPTION: {type(exc).__name__}: {exc}")
        return 2

    print()
    print("=== Result ===")
    print(result)

    # The tool returns a string starting with "Mesh saved to" on
    # success and "Error:" / "RhinoCompute error:" on failure.
    if result.startswith("Mesh saved to"):
        obj_path = folder / "propeller_mesh.obj"
        print()
        print(f"Output file: {obj_path}")
        print(f"Size: {obj_path.stat().st_size} bytes")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
