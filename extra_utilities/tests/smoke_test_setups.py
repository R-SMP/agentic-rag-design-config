"""The configurators a repository holds: ``setups/<name>/``, all stored the
same way (``engine/setups.py``, ``setups/README.md``).

1. ENGINE -- a folder of ``setups/`` is a setup when it holds a
   ``pack.yaml``; the default is ``setups/propeller``, else the first setup,
   else ``dc_pack/`` (a package in the layout from before setups/);
   ``DC_PACK_DIR`` is taken from the root when relative, as it is when
   absolute.
2. THE REPOSITORY -- the propeller is committed in ``setups/propeller``, no
   ``dc_pack/`` is left; ``config.py`` and the Studio run it by default, and
   both take ``DC_PACK_DIR`` alike; the vacuum hose adapter is left out of
   git and of the images (its model's author asks that it not be uploaded).

    py -3.13 extra_utilities/tests/smoke_test_setups.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine import setups as S  # noqa: E402

FAILURES: list[str] = []


def check(ok: bool, what: str) -> None:
    if not ok:
        FAILURES.append(what)


def _run(group, tag: str):
    try:
        return group()
    except Exception as exc:                                        # noqa: BLE001
        check(False, f"{tag} {type(exc).__name__}: {str(exc)[:300]}")
        return None


def setup(root: Path, name: str, pack_yaml: bool = True) -> Path:
    d = root / "setups" / name
    d.mkdir(parents=True)
    if pack_yaml:
        (d / "pack.yaml").write_text("pack_format: 1\n", encoding="utf-8")
    return d


def check_engine() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="setups_smoke_"))
    try:
        check(S.all_setups(tmp) == [] and S.default_setup(tmp) == tmp / "dc_pack",
              f"[ENGINE] no setups/: {S.all_setups(tmp)} {S.default_setup(tmp)}")
        b = setup(tmp, "bravo")
        a = setup(tmp, "alpha")
        setup(tmp, "notes", pack_yaml=False)
        (tmp / "setups" / "README.md").write_text("x", encoding="utf-8")
        check(S.all_setups(tmp) == [a, b], f"[ENGINE] the setups: {S.all_setups(tmp)}")
        check(S.default_setup(tmp) == a, f"[ENGINE] without a propeller, the first: {S.default_setup(tmp)}")
        p = setup(tmp, "propeller")
        check(S.default_setup(tmp) == p, f"[ENGINE] the propeller first: {S.default_setup(tmp)}")
        check(S.resolve(tmp, None) == p and S.resolve(tmp, "") == p, "[ENGINE] an empty DC_PACK_DIR")
        check(S.resolve(tmp, "setups/bravo") == b, f"[ENGINE] a relative one: {S.resolve(tmp, 'setups/bravo')}")
        check(S.resolve(tmp, str(b)) == b, "[ENGINE] an absolute one")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _default_in_child(env_value: str | None) -> list[str]:
    env = {k: v for k, v in os.environ.items() if k != "DC_PACK_DIR"}
    if env_value is not None:
        env["DC_PACK_DIR"] = env_value
    env.update(PYTHONIOENCODING="utf-8", DATABASE_URL="", DATABASE_PUBLIC_URL="")
    code = ("import config; from studio.__main__ import default_pack; "
            "print(config.DC_PACK_DIR); print(default_pack())")
    out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env, capture_output=True,
                         text=True, encoding="utf-8", timeout=120)
    return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]


def check_repo() -> None:
    tracked = subprocess.run(["git", "ls-files", "setups", "dc_pack"], cwd=str(ROOT), capture_output=True,
                             text=True, check=True).stdout.split()
    check("setups/propeller/pack.yaml" in tracked and "setups/README.md" in tracked
          and not any(t.startswith("dc_pack/") for t in tracked),
          "[REPO] the propeller is not committed in setups/propeller, or dc_pack/ is left")
    check(not any(t.startswith("setups/vacuum_hose_adapter/") for t in tracked),
          "[REPO] the vacuum hose adapter is committed")
    ignored = subprocess.run(["git", "check-ignore", "-q", "setups/vacuum_hose_adapter/pack.yaml"],
                             cwd=str(ROOT)).returncode == 0
    check(ignored, "[REPO] git does not leave out setups/vacuum_hose_adapter/")
    docker = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    check("setups/vacuum_hose_adapter/" in docker, "[REPO] the images do not leave out the vacuum hose adapter")
    check(not (ROOT / "dc_pack").exists(), "[REPO] a dc_pack/ folder is left")
    want = str(ROOT / "setups" / "propeller")
    got = _default_in_child(None)
    check(got == [want, want], f"[REPO] the default for config.py and the Studio: {got}")
    other = str(ROOT / "setups" / "elsewhere")
    got = _default_in_child("setups/elsewhere")
    check(got == [other, other], f"[REPO] DC_PACK_DIR for config.py and the Studio: {got}")


def main() -> int:
    _run(check_engine, "[ENGINE]")
    _run(check_repo, "[REPO]")
    if FAILURES:
        print(f"FAIL - {len(FAILURES)} problem(s):")
        for f in FAILURES:
            print("  " + f)
        return 1
    print("PASS - every configurator is a folder of setups/, the propeller the default for the engine and "
          "the Studio alike, DC_PACK_DIR taken from the root, and the vacuum hose adapter left out of git "
          "and the images.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
