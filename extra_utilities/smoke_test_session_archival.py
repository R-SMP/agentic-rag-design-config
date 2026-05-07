"""Smoke-test for the end-of-session archival behaviour.

Verifies that ``_archive_previous_session()`` correctly moves:
1. session_*.log + agent_flow_*.txt out of logs/
2. logs/agent_histories/ files into previous_sessions/<id>/agent_histories/
   AND removes the now-empty logs/agent_histories/ directory.
3. attempts/ subfolders into previous_sessions/<id>/attempts/
4. inputs/input_images/<files> into previous_sessions/<id>/input_images/
5. EVERY file at inputs/ root (user_query.txt, extracted_inputs.txt,
   current_plan.txt, AND orphan images/notes the user dropped there
   instead of in input_images/) into previous_sessions/<id>/.

Run from the project root:
    .venv/Scripts/python.exe extra_utilities/smoke_test_session_archival.py
"""

import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import loader as loader_mod


def _setup_fake_workspace(root: Path) -> dict[str, Path]:
    """Lay out a fake workspace mirroring the project's layout."""
    inputs = root / "inputs"
    input_images = inputs / "input_images"
    logs = root / "logs"
    histories = logs / "agent_histories"
    attempts = root / "attempts"
    previous = root / "previous_sessions"

    for d in (inputs, input_images, logs, histories, attempts, previous):
        d.mkdir(parents=True, exist_ok=True)

    # Files at inputs/ root — both the conventional ones AND orphan
    # files the user mistakenly dropped here instead of in input_images/.
    (inputs / "user_query.txt").write_text("user query text\n", encoding="utf-8")
    (inputs / "extracted_inputs.txt").write_text("extraction text\n", encoding="utf-8")
    (inputs / "test2v3.jpg").write_bytes(b"\xff\xd8\xff\xe0")  # fake JPEG header
    (inputs / "test2v3_note.txt").write_text("orphan note\n", encoding="utf-8")

    # File inside inputs/input_images/ (the conventional location)
    (input_images / "ref.png").write_bytes(b"\x89PNG\r\n")  # fake PNG header
    (input_images / "ref_note.txt").write_text("ref note\n", encoding="utf-8")

    # logs/ contents
    (logs / "session_20260501_120000.log").write_text("log content\n", encoding="utf-8")
    (logs / "agent_flow_20260501_120000.txt").write_text("trace\n", encoding="utf-8")
    (logs / "current_plan.txt").write_text("plan\n", encoding="utf-8")

    # logs/agent_histories/ files
    (histories / "orchestrator.txt").write_text("hist\n", encoding="utf-8")
    (histories / "planner.txt").write_text("hist\n", encoding="utf-8")

    # attempts/ subfolder
    attempt_folder = attempts / "20260501_120000_001_test"
    attempt_folder.mkdir()
    (attempt_folder / "parameters.json").write_text("{}\n", encoding="utf-8")

    return {
        "inputs": inputs,
        "input_images": input_images,
        "logs": logs,
        "histories": histories,
        "attempts": attempts,
        "previous": previous,
        "attempt_folder": attempt_folder,
    }


def _summarise(d: Path, prefix: str = "") -> list[str]:
    """Return a sorted list of every file path under d, relative to d."""
    if not d.exists():
        return []
    out = []
    for p in d.rglob("*"):
        if p.is_file():
            out.append(str(p.relative_to(d)).replace("\\", "/"))
    return sorted(out)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ws = _setup_fake_workspace(root)

        print("Pre-archive state:")
        print(f"  inputs/        = {sorted(p.name for p in ws['inputs'].iterdir())}")
        print(f"  inputs/input_images/ = {sorted(p.name for p in ws['input_images'].iterdir())}")
        print(f"  logs/          = {sorted(p.name for p in ws['logs'].iterdir())}")
        print(f"  logs/agent_histories/ = {sorted(p.name for p in ws['histories'].iterdir())}")
        print(f"  attempts/      = {sorted(p.name for p in ws['attempts'].iterdir())}")
        print(f"  previous_sessions/ = {sorted(p.name for p in ws['previous'].iterdir())}")
        print()

        # Patch the loader's module-level constants to point at our temp workspace
        with patch.object(loader_mod, "USER_INPUTS_DIR", ws["inputs"]), \
             patch.object(loader_mod, "INPUT_IMAGES_DIR", ws["input_images"]), \
             patch.object(loader_mod, "LOGS_DIR", ws["logs"]), \
             patch.object(loader_mod, "ATTEMPTS_DIR", ws["attempts"]), \
             patch.object(loader_mod, "PREVIOUS_SESSIONS_DIR", ws["previous"]):
            loader_mod._archive_previous_session()

        # Find the new previous_sessions/IDXXX_*/ folder
        archived = sorted(p for p in ws["previous"].iterdir() if p.is_dir())
        assert len(archived) == 1, f"expected 1 archived session, got {archived}"
        dest = archived[0]
        print(f"Archived to: {dest.name}")
        print()

        # ------ Assertions ------

        # Issue 2: logs/agent_histories/ should be GONE
        assert not ws["histories"].exists(), (
            f"BAD: {ws['histories']} should have been removed after iter-empty"
        )
        print("PASS — logs/agent_histories/ removed (Issue 2 fixed)")

        # Issue 1: every orphan file at inputs/ root should be archived
        archived_files = _summarise(dest)
        print(f"  Files in archived session:")
        for f in archived_files:
            print(f"    {f}")
        print()

        expected_at_dest_root = {
            "session_20260501_120000.log",
            "agent_flow_20260501_120000.txt",
            "user_query.txt",
            "extracted_inputs.txt",
            "test2v3.jpg",          # the orphan image
            "test2v3_note.txt",     # the orphan note
            "current_plan.txt",
        }
        actual_at_dest_root = {
            p.name for p in dest.iterdir() if p.is_file()
        }
        missing = expected_at_dest_root - actual_at_dest_root
        assert not missing, f"BAD: these files were NOT archived: {sorted(missing)}"
        print(f"PASS — every file at inputs/ root archived (Issue 1 fixed):")
        for f in sorted(expected_at_dest_root):
            print(f"    {f}")
        print()

        # input_images/ subfolder contents should also be archived
        assert (dest / "input_images" / "ref.png").exists()
        assert (dest / "input_images" / "ref_note.txt").exists()
        print("PASS — inputs/input_images/ contents archived to previous_sessions/<id>/input_images/")

        # agent_histories/ contents should be in archived session
        assert (dest / "agent_histories" / "orchestrator.txt").exists()
        assert (dest / "agent_histories" / "planner.txt").exists()
        print("PASS — logs/agent_histories/ contents archived to previous_sessions/<id>/agent_histories/")

        # attempts/<folder>/ contents should be in archived session
        assert (dest / "attempts" / "20260501_120000_001_test" / "parameters.json").exists()
        print("PASS — attempts/<folder>/ archived to previous_sessions/<id>/attempts/")
        print()

        # Sanity: nothing left behind at inputs/ root
        leftover_files = [p.name for p in ws["inputs"].iterdir() if p.is_file()]
        assert leftover_files == [], (
            f"BAD: files left behind at inputs/ root: {leftover_files}"
        )
        print("PASS — inputs/ root is clean after archival")

        # input_images/ subfolder still exists (for next session's uploads)
        # but is empty
        assert ws["input_images"].exists(), "input_images/ subfolder should remain"
        assert not any(ws["input_images"].iterdir()), (
            f"input_images/ should be empty: {list(ws['input_images'].iterdir())}"
        )
        print("PASS — inputs/input_images/ kept as empty subfolder for next session")

        # attempts/ should still exist (no files left in it)
        assert ws["attempts"].exists(), "attempts/ should remain"
        assert not any(ws["attempts"].iterdir()), (
            f"attempts/ should be empty: {list(ws['attempts'].iterdir())}"
        )
        print("PASS — attempts/ kept as empty folder for next session")

        print()
        print("Session-archival smoke test passed.")


if __name__ == "__main__":
    main()
