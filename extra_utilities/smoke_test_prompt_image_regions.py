"""Offline guard for the ``<<CAN_SEE>>`` / ``<<CANNOT_SEE>>`` prompt split.

``agents/shared/prompts.py`` carries ``_AGENTS_WITH_IMAGE_TOOLS``, a mirror
of which agents bind an image-viewing tool.  The real source of truth is each
agent's own ``can_view_images=`` argument where it calls
``read_user_inputs_summary``.  Prompt assembly cannot read that directly --
importing an agent module drags in the 3D render stack -- so the two are kept
in step by this check instead of by hope.

Without it the mirror rots the first time an agent gains or loses an image
tool, and the WRONG version of the retrieval passage ships: an agent that
cannot see images gets told to open one (which is how F100 arose), or an
agent that can gets told it cannot and hands the work off instead.

Pure text analysis: no imports of the project, no Postgres, no R2, no
network, and no dependency on the Python version the prompts themselves
need.  Run from the repo root::

    python extra_utilities/smoke_test_prompt_image_regions.py
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

PROMPTS = _REPO_ROOT / "agents" / "shared" / "prompts.py"
FRAGMENTS = (
    _REPO_ROOT / "DC_prompt_fragments/tools_config/retrieve_user_inputs.md",
    _REPO_ROOT / "agents/5agent/tools_config/retrieve_user_inputs_5agents.md",
    _REPO_ROOT / "agents/3agent/tools_config/retrieve_user_inputs_3agents.md",
)

_FROZENSET_RE = re.compile(
    r"_AGENTS_WITH_IMAGE_TOOLS\s*=\s*frozenset\(\{(.*?)\}\)", re.DOTALL)
_NAME_RE = re.compile(r'"([a-z_0-9]+)"')
_CAN_SEE_RE = re.compile(r"<<CAN_SEE>>(.*?)<</CAN_SEE>>", re.DOTALL)
_CANNOT_SEE_RE = re.compile(r"<<CANNOT_SEE>>(.*?)<</CANNOT_SEE>>", re.DOTALL)

_failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        _failures.append(msg)


def _read(path: Path) -> str:
    return io.open(path, encoding="utf-8").read()


def _declared_mirror() -> set[str]:
    """The set prompt assembly branches on."""
    m = _FROZENSET_RE.search(_read(PROMPTS))
    if m is None:
        _failures.append(
            "could not find _AGENTS_WITH_IMAGE_TOOLS in prompts.py -- it was "
            "renamed or removed; this guard needs updating with it")
        return set()
    return set(_NAME_RE.findall(m.group(1)))


# Subdirectories of ``agents/`` that are NOT agents: shared infrastructure
# (``shared`` is where ``can_view_images`` is DEFINED, so scanning it always
# produces a false positive), the two topology overlay trees, and the two
# per-topology prompt forks.
_NOT_AGENTS = frozenset({
    "shared", "topology3", "topology5", "3agent", "5agent",
})


def _actual_from_call_sites() -> set[str]:
    """Agents whose own code says they can view images.

    An agent that never calls ``read_user_inputs_summary`` binds no image
    tool either, so absence counts as False.
    """
    seers: set[str] = set()
    for agent_dir in sorted((_REPO_ROOT / "agents").iterdir()):
        if not agent_dir.is_dir() or agent_dir.name.startswith("__"):
            continue
        if agent_dir.name in _NOT_AGENTS:
            continue
        for py in agent_dir.glob("*.py"):
            if py.name == "__init__.py":
                continue
            body = _read(py)
            if "can_view_images=True" in body:
                seers.add(agent_dir.name)
            elif ("can_view_images=" in body
                    and "can_view_images=False" not in body):
                _failures.append(
                    f"{py.relative_to(_REPO_ROOT)}: can_view_images is passed "
                    f"a non-literal; this guard can only read True/False")
    return seers


def main() -> int:
    print("[smoke-prompt-image-regions]  checking the CAN_SEE split...")

    declared = _declared_mirror()
    actual = _actual_from_call_sites()
    check(declared == actual,
          f"_AGENTS_WITH_IMAGE_TOOLS is {sorted(declared)} but the agent "
          f"modules say {sorted(actual)}.  Update the frozenset in "
          f"prompts.py to match, or the wrong version of the retrieval "
          f"passage will ship for the agents that differ.")
    if declared == actual:
        print(f"  roster agrees: {', '.join(sorted(actual))}")

    for frag in FRAGMENTS:
        rel = frag.relative_to(_REPO_ROOT)
        check(frag.is_file(), f"{rel}: missing")
        if not frag.is_file():
            continue
        body = _read(frag)
        can = _CAN_SEE_RE.findall(body)
        cannot = _CANNOT_SEE_RE.findall(body)
        check(len(can) == 1, f"{rel}: expected 1 <<CAN_SEE>> region, "
                             f"found {len(can)}")
        check(len(cannot) == 1, f"{rel}: expected 1 <<CANNOT_SEE>> region, "
                                f"found {len(cannot)}")
        if len(can) == 1 and len(cannot) == 1:
            check(can[0].strip() != "", f"{rel}: <<CAN_SEE>> region is empty")
            check(cannot[0].strip() != "",
                  f"{rel}: <<CANNOT_SEE>> region is empty")
            # The defect F100 recorded, asserted directly: the version for
            # agents with no image tool must not name one, or tell them to
            # look.
            check("view_images" not in cannot[0],
                  f"{rel}: the <<CANNOT_SEE>> version names an image tool")
            check("you have LOOKED" not in cannot[0],
                  f"{rel}: the <<CANNOT_SEE>> version tells an agent with no "
                  f"image tool that it must have looked")
            # Markers must not nest or interleave.
            check("<<CAN_SEE>>" not in cannot[0]
                  and "<<CANNOT_SEE>>" not in can[0],
                  f"{rel}: the two regions overlap")
        print(f"  {rel.as_posix()}: both regions present and well-formed")

    print()
    if _failures:
        print(f"FAIL - {len(_failures)} problem(s):")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("PASS - prompt image-region split is consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
