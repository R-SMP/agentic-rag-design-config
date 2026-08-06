"""Fork drift — has any origin moved since its fork was taken?

The 7-agent reduced variant forks files from the shared tree.  A fork that
falls behind its origin does not raise: it produces a plausible prompt built
from stale text, which is the failure mode this whole project exists to remove.
Nothing else catches it — smoke_test_prompt_variant proves a fork is REACHED
and that its blast radius is right, not that its content is still current.

So this reads extra_utilities/fork_manifest.json and, for each entry, compares
the recorded commit against the origin's actual last-touched commit.

    py extra_utilities/smoke_test_fork_drift.py

FAILS (not warns) on drift, deliberately — see topology_shared_touchpoints.md
section D: a check that degrades quietly is one nobody acts on.  The fix is
never to bump the SHA on its own: read what changed, decide whether the fork
needs it, port it if so, and record the new commit as part of that change.

Skips cleanly when git is unavailable or the tree is not a repository, since
the manifest is then unverifiable rather than wrong.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "extra_utilities" / "fork_manifest.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

failures: list[str] = []
notes: list[str] = []


def _git(*args: str) -> str | None:
    """Run git in the repo root; None when git is unusable."""
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, ValueError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def main() -> int:
    if not MANIFEST.is_file():
        print(f"FAIL — manifest missing: {MANIFEST.relative_to(ROOT)}")
        return 1
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    forks = data.get("forks", [])
    if not forks:
        print("no forks recorded — nothing to check")
        return 0

    if _git("rev-parse", "--git-dir") is None:
        print(f"SKIP — git unavailable or not a repository; {len(forks)} fork(s) "
              "left unverified")
        return 0

    # Every fork on disk must be IN the manifest, or provenance is silently
    # incomplete — the failure mode where someone adds a fork and forgets.
    recorded = {f["fork"] for f in forks}
    on_disk: set[str] = set()
    for tree, pattern in (("agents/7agent_reduced", "*.md"),
                          ("reduced7", "*.py")):
        d = ROOT / tree
        if not d.is_dir():
            continue
        for p in d.rglob(pattern):
            if p.name == "__init__.py":
                continue
            on_disk.add(p.relative_to(ROOT).as_posix())
    for missing in sorted(on_disk - recorded):
        failures.append(
            f"[UNRECORDED] {missing} is a fork on disk with no manifest entry — "
            "add it, or its drift will never be noticed"
        )

    for entry in forks:
        fork_rel, origin_rel = entry["fork"], entry.get("origin")
        recorded_sha = entry.get("origin_commit")
        relation = entry.get("relation", "copy")
        fork_p = ROOT / fork_rel

        # relation "new": a variant file with no shared original — nothing
        # upstream to drift FROM.  Still recorded, so the UNRECORDED check
        # above stays meaningful and a reader can see it was a deliberate
        # addition rather than an unfiled fork.
        if relation == "new" or origin_rel is None:
            if not fork_p.is_file():
                failures.append(
                    f"[STALE ENTRY] {fork_rel} is in the manifest but not on "
                    "disk — if it was removed, delete its entry"
                )
            else:
                notes.append(f"{fork_rel.split('/')[-1]:52s} <- (new; no origin)")
            continue

        origin_p = ROOT / origin_rel

        if not fork_p.is_file():
            failures.append(
                f"[STALE ENTRY] {fork_rel} is in the manifest but not on disk — "
                "if the fork was reverted, delete its entry"
            )
            continue
        if not origin_p.is_file():
            failures.append(
                f"[ORIGIN GONE] {origin_rel} no longer exists, but "
                f"{fork_rel} forks it"
            )
            continue

        current = _git("log", "-1", "--format=%H", "--", origin_rel)
        if not current:
            notes.append(f"{origin_rel}: no commit history found, skipped")
            continue
        if current != recorded_sha:
            failures.append(
                f"[DRIFT] {origin_rel} has moved since {fork_rel} was forked.\n"
                f"           forked at : {recorded_sha[:9]}\n"
                f"           origin now: {current[:9]}  ({relation})\n"
                f"           inspect   : git log {recorded_sha[:9]}..{current[:9]} "
                f"-p -- {origin_rel}\n"
                f"           then port what the fork needs and update "
                f"extra_utilities/fork_manifest.json"
            )
        else:
            notes.append(
                f"{fork_rel.split('/')[-1]:52s} <- {origin_rel} @ "
                f"{recorded_sha[:9]} ({relation})"
            )

    print(f"Fork drift — {len(forks)} fork(s) recorded, {len(on_disk)} on disk")
    for n in notes:
        print(f"  {n}")
    print()
    if failures:
        print(f"FAIL — {len(failures)} problem(s):\n")
        for f in failures:
            print(f"  {f}")
        return 1
    print("PASS — every fork is recorded, and every origin is unchanged since "
          "its fork was taken.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
