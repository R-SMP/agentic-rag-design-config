"""Assemble every agent's system prompt under a matrix of workflow settings x
topologies, and compare two such snapshots.

Why a matrix
------------
``topology_prompt_snapshot.py`` assembles the prompts under the settings that
are on disk.  Most prompt text is conditional, though: ``<<RAG_ON>>``,
``<<HAS_DBA>>``, the pack's ``<<IF:tool:…>>`` / ``<<IF:setting:…>>``, ``<<DCII_ONLY>>``,
``<<PF_ON>>``, the per-agent parameter-access regions, the per-agent
database-tool slots, and the runtime blocks chosen by ``RENDER_LIBRARY``,
``DCOI_COMPARISON_MODE``, ``KEEP_IMAGES_IN_CONTEXT`` and ``CHAIN_ACCESS``.  A
change that is byte-identical under one setting can still move a prompt under
another.  The 17 combinations below switch each of those at least once; times
three topologies that is 357 prompts.  They are the combinations that
verified ``MAS-generalized-v2`` (2026-10-13/14).

Usage
-----
    py -3.13 extra_utilities/scripts/prompt_matrix.py save     <outdir> [--repo DIR] [--jobs N]
    py -3.13 extra_utilities/scripts/prompt_matrix.py diff     <A> <B>
    py -3.13 extra_utilities/scripts/prompt_matrix.py wsdiff   <A> <B>
    py -3.13 extra_utilities/scripts/prompt_matrix.py classify <A> <B> [--json FILE]

``save``      writes ``<outdir>/<combination>/<N>agent/<agent>.txt`` (each
              prompt byte for byte) and ``<outdir>/manifest.json`` (SHA-256
              and length of every prompt, plus the commit it was taken on).
``diff``      compares the SHA-256 fingerprints, so either side may be a
              snapshot folder or a bare ``manifest.json`` -- the committed
              baseline is a manifest alone.
``wsdiff``    compares the texts with every run of whitespace collapsed to one
              space: a prompt that moved only by line breaks or indentation
              passes.  Needs the prompt files on both sides.
``classify``  cuts every difference into hunks, merges identical hunks found
              in several combinations / topologies / agents, and labels each:
              TEXT (words changed), reflow (same words, other line breaks),
              blank-line (a blank line added or removed), indent/space (only
              spaces inside lines changed).  Needs the prompt files.

Exit status is 0 when nothing differs (for ``classify``: no TEXT hunk), else 1.

Isolation
---------
One child process per (combination, topology): ``prompts.py`` captures
``PLANNER_FIRST`` and ``DC_INSPECTOR_ENABLED`` at import, so two assemblies in
one process would share those flags.  The children compile into a fresh,
temporary bytecode cache (``PYTHONPYCACHEPREFIX``), so a stale ``.pyc`` in the
tree can never serve old code (a size-preserving edit once served the wrong
``SYSTEM_TOPOLOGY``; see extra_utilities/tests/README.md).

A combination may only set settings that exist: ``setattr`` on a missing name
would silently create it, and the combination would go on "passing" while
testing nothing -- the failure mode if a setting is ever moved out of
``workflow_settings/settings.py``.  The effective values are recorded in the
manifest under ``settings``.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# ``_ALL_DB_TOOLS`` is not a setting: it replaces
# ``database_access.is_enabled_for`` with "every agent holds every database
# tool", the widest prompt surface the RAG layer can produce.
CONFIGS: dict[str, dict] = {
    "base":            {},
    "rag_on":          {"RAG_ENABLED": True},
    "rag_all":         {"RAG_ENABLED": True, "_ALL_DB_TOOLS": True},
    "bsv_off":         {"BLADE_SECTIONS_VISUALIZER_ENABLED": False},
    "mesh_on":         {"MESH_CHECKS": True},
    "mesh_on_pyvista": {"MESH_CHECKS": True, "RENDER_LIBRARY": "pyvista"},
    "pf_on":           {"PLANNER_FIRST": True},
    "dcii_off":        {"DC_INSPECTOR_ENABLED": False},
    "pf_on_dcii_off":  {"PLANNER_FIRST": True, "DC_INSPECTOR_ENABLED": False},
    "uii_params_on":   {"UII_PARAMETER_LIST_ENABLED": True},
    "dcoi_ranges_on":  {"DCOI_KNOWS_PARAMS_RANGES": True},
    "cmp_mode_1":      {"DCOI_COMPARISON_MODE": 1},
    "cmp_mode_2":      {"DCOI_COMPARISON_MODE": 2},
    "keep_imgs_noch":  {"KEEP_IMAGES_IN_CONTEXT": True, "CHAIN_ACCESS": False},
    "all_on":          {"RAG_ENABLED": True, "_ALL_DB_TOOLS": True,
                        "MESH_CHECKS": True, "UII_PARAMETER_LIST_ENABLED": True,
                        "DCOI_KNOWS_PARAMS_RANGES": True, "PLANNER_FIRST": True},
    "all_off":         {"RAG_ENABLED": False,
                        "BLADE_SECTIONS_VISUALIZER_ENABLED": False,
                        "MESH_CHECKS": False, "DC_INSPECTOR_ENABLED": False,
                        "UII_PARAMETER_LIST_ENABLED": False,
                        "DCOI_KNOWS_PARAMS_RANGES": False},
    "rag_all_bsv_off_dcii_off_mesh_on": {
                        "RAG_ENABLED": True, "_ALL_DB_TOOLS": True,
                        "BLADE_SECTIONS_VISUALIZER_ENABLED": False,
                        "DC_INSPECTOR_ENABLED": False, "MESH_CHECKS": True},
}
TOPOLOGIES = (7, 5, 3)

# Every setting some combination changes; recorded for every combination, so
# "base" documents the on-disk defaults the others are relative to.
_WATCHED = sorted({k for ov in CONFIGS.values() for k in ov
                   if not k.startswith("_")})


# ---------------------------------------------------------------------------
# Assembly (child process, one per combination x topology)
# ---------------------------------------------------------------------------

# The two settings the parameter-access table replaced (MAS-blueprint P3a),
# as the table cells they meant: True -> these cells, False -> the cells'
# old "off" state.  The combinations keep their names and meaning, so the
# baseline taken before the table existed still compares like for like.
_ACCESS_FROM_SETTING = {
    "UII_PARAMETER_LIST_ENABLED": (
        {"user_input_inspector": {7: "full", 5: "full"}},
        {"user_input_inspector": {7: "none", 5: "none"}}),
    "DCOI_KNOWS_PARAMS_RANGES": (
        {"dc_output_inspector": {7: "full", 5: "full"},
         "requirements_analyst": {3: "full"}},
        {"dc_output_inspector": {7: "names", 5: "names"},
         "requirements_analyst": {3: "names"}}),
}


def apply_config(config: str):
    """Apply combination *config* to this (child) process and return the
    settings module.  Shared with ``tool_matrix.py``."""
    import workflow_settings.settings as S
    overrides = dict(CONFIGS[config])
    all_db_tools = overrides.pop("_ALL_DB_TOOLS", False)
    try:
        from engine import parameter_access as PA
    except ImportError:                       # before the table existed
        PA = None
    if PA is not None:
        cells: dict = {}
        for name, (on, off) in _ACCESS_FROM_SETTING.items():
            if name in overrides:
                for agent, row in (on if overrides.pop(name) else off).items():
                    cells.setdefault(agent, {}).update(row)
        PA.read_overrides = lambda: {a: dict(r) for a, r in cells.items()}
    missing = [k for k in overrides if not hasattr(S, k)]
    if missing:
        raise SystemExit(f"{config}: not in workflow_settings.settings: "
                         f"{', '.join(missing)}")
    for k, v in overrides.items():
        setattr(S, k, v)
    if all_db_tools:
        from workflow_settings import database_access as D
        if not hasattr(D, "is_enabled_for"):
            raise SystemExit(f"{config}: database_access.is_enabled_for is gone")
        D.is_enabled_for = lambda agent, tool=None: True
    return S


def _child_main(repo: str, config: str, topology: int) -> int:
    repo_p = Path(repo)
    for p in ("extra_utilities/scripts", "extra_utilities/prompt_pdf", "."):
        sys.path.insert(0, str(repo_p / p))
    sys.modules["simplejson"] = None          # type: ignore[assignment]
    sys.modules["chardet"] = None             # type: ignore[assignment]
    import bootstrap                          # noqa: E402
    bootstrap.install()

    S = apply_config(config)

    import topology_prompt_snapshot as T      # noqa: E402
    payload = T._assemble(topology)
    payload.pop("templates", None)
    payload["settings"] = {k: getattr(S, k, None) for k in _WATCHED}
    sys.stdout.buffer.write(json.dumps(payload).encode("utf-8"))
    return 0


def _run_child(repo: Path, config: str, topology: int, cache: str) -> dict:
    env = dict(os.environ, PYTHONPYCACHEPREFIX=cache, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()),
         "_child", str(repo), config, str(topology)],
        capture_output=True, cwd=str(repo), env=env,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[-3000:])
    data = json.loads(proc.stdout.decode("utf-8"))
    if "fatal" in data:
        raise RuntimeError(data["fatal"])
    return data


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)
    return proc.stdout.strip()


def cmd_save(outdir: Path, repo: Path, jobs: int) -> int:
    jobs_list = [(c, n) for c in CONFIGS for n in TOPOLOGIES]
    results: dict[tuple[str, int], dict] = {}
    failures: dict[tuple[str, int], str] = {}
    with tempfile.TemporaryDirectory(prefix="prompt_matrix_pyc_") as cache:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {pool.submit(_run_child, repo, c, n, cache): (c, n)
                       for c, n in jobs_list}
            for fut in concurrent.futures.as_completed(futures):
                key = futures[fut]
                try:
                    results[key] = fut.result()
                except Exception as exc:              # noqa: BLE001
                    failures[key] = str(exc)
    if failures:
        for (c, n), err in sorted(failures.items()):
            print(f"FAIL {c} / topology {n}\n{err}\n")
        print(f"{len(failures)} of {len(jobs_list)} assemblies failed; "
              f"nothing written.")
        return 1

    manifest: dict = {"_meta": {
        "branch": _git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "commit": _git(repo, "rev-parse", "HEAD"),
        "uncommitted_changes": bool(_git(repo, "status", "--porcelain")),
        "taken": datetime.datetime.now(datetime.timezone.utc)
                 .isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "combinations": CONFIGS,
    }}
    total = 0
    for c, n in jobs_list:
        data = results[(c, n)]
        sub = outdir / c / f"{n}agent"
        sub.mkdir(parents=True, exist_ok=True)
        shas, chars = {}, {}
        for agent, text in sorted(data["prompts"].items()):
            # newline="" writes the assembled text byte for byte.
            (sub / f"{agent}.txt").write_text(text, encoding="utf-8",
                                              newline="")
            shas[agent] = hashlib.sha256(text.encode("utf-8")).hexdigest()
            chars[agent] = len(text)
        total += len(shas)
        manifest[f"{c}/{n}"] = {
            "prompts": shas,
            "chars": chars,
            "unavailable": data.get("unavailable", {}),
            "unformatted": data.get("unformatted", {}),
            "pf": data.get("planner_first"),
            "dcii": data.get("dcii_enabled"),
            "settings": data.get("settings", {}),
        }
        bad = sorted(data.get("unformatted", {}))
        print(f"{c:<34} {n}  agents={len(shas)}  pf={data.get('planner_first')!s:<5}"
              f" dcii={data.get('dcii_enabled')!s:<5}"
              + (f"  !! NOT FORMATTED: {bad}" if bad else ""))
    (outdir / "manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=False) + "\n",
        encoding="utf-8", newline="\n")
    meta = manifest["_meta"]
    print(f"\n{total} prompts from {len(jobs_list)} assemblies -> {outdir}")
    print(f"commit {meta['commit'][:12]} on {meta['branch']}"
          + ("  (WITH uncommitted changes)" if meta["uncommitted_changes"]
             else ""))
    return 0


# ---------------------------------------------------------------------------
# diff (fingerprints)
# ---------------------------------------------------------------------------

def _load_manifest(p: Path) -> dict:
    f = p / "manifest.json" if p.is_dir() else p
    return json.loads(f.read_text(encoding="utf-8"))


def cmd_diff(a: Path, b: Path) -> int:
    ma, mb = _load_manifest(a), _load_manifest(b)
    keys = sorted(k for k in set(ma) | set(mb) if not k.startswith("_"))
    same = differ = 0
    for key in keys:
        ra, rb = ma.get(key), mb.get(key)
        if ra is None or rb is None:
            print(f"ONLY IN {'B' if ra is None else 'A'}  {key}")
            differ += 1
            continue
        pa, pb = ra["prompts"], rb["prompts"]
        for agent in sorted(set(pa) | set(pb)):
            if pa.get(agent) == pb.get(agent):
                same += 1
                continue
            differ += 1
            if agent not in pa or agent not in pb:
                print(f"{'APPEARED' if agent not in pa else 'DISAPPEARED':<11} "
                      f"{key} {agent}")
            else:
                ca, cb = ra.get("chars", {}).get(agent), rb.get("chars", {}).get(agent)
                size = f"  {ca} -> {cb} chars" if ca is not None and cb is not None else ""
                print(f"DIFF        {key} {agent}{size}")
        for fld in ("unavailable", "unformatted", "pf", "dcii"):
            if ra.get(fld) != rb.get(fld):
                differ += 1
                print(f"DIFF        {key} {fld}: {ra.get(fld)!r} -> {rb.get(fld)!r}")
    print(f"\n{same} prompts byte-identical, {differ} difference(s).")
    return 1 if differ else 0


# ---------------------------------------------------------------------------
# wsdiff / classify (prompt texts)
# ---------------------------------------------------------------------------

def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", newline="")


def _prompt_files(a: Path, b: Path) -> list[Path]:
    if not a.is_dir() or not b.is_dir():
        raise SystemExit("wsdiff / classify need two snapshot FOLDERS "
                         "(the prompt files), not a manifest.")
    rels = {p.relative_to(a) for p in a.rglob("*.txt")}
    rels |= {p.relative_to(b) for p in b.rglob("*.txt")}
    return sorted(rels)


def cmd_wsdiff(a: Path, b: Path) -> int:
    same = ws_only = text = 0
    for rel in _prompt_files(a, b):
        fa, fb = a / rel, b / rel
        if not fa.exists() or not fb.exists():
            text += 1
            print(f"ONLY IN {'B' if not fa.exists() else 'A'}  {rel.as_posix()}")
            continue
        ta, tb = _read(fa), _read(fb)
        if ta == tb:
            same += 1
        elif _ws(ta) == _ws(tb):
            ws_only += 1
        else:
            text += 1
            print(f"TEXT DIFF  {rel.as_posix()}")
    print(f"\n{same} byte-identical, {ws_only} whitespace-only, "
          f"{text} TEXT different.")
    return 1 if text else 0


def _classify(bl: tuple[str, ...], al: tuple[str, ...]) -> str:
    before, after = "\n".join(bl), "\n".join(al)
    if _ws(before) != _ws(after):
        return "TEXT"
    if before.strip() == "" or after.strip() == "":
        return "blank-line"
    if len(bl) != len(al) or any(x.strip() != y.strip()
                                 for x, y in zip(bl, al)):
        return "reflow"
    return "indent/space"


def cmd_classify(a: Path, b: Path, json_out: Path | None) -> int:
    # Keyed by the LINES on each side, not their join: an empty side (a pure
    # insertion) and a side holding one blank line must stay distinguishable.
    hunks: dict[tuple[tuple[str, ...], tuple[str, ...]], set[str]] = \
        defaultdict(set)
    one_sided: list[str] = []
    for rel in _prompt_files(a, b):
        fa, fb = a / rel, b / rel
        where = rel.with_suffix("").as_posix()      # combination/Nagent/agent
        if not fa.exists() or not fb.exists():
            one_sided.append(f"ONLY IN {'B' if not fa.exists() else 'A'}  {where}")
            continue
        ta, tb = _read(fa).split("\n"), _read(fb).split("\n")
        if ta == tb:
            continue
        sm = difflib.SequenceMatcher(a=ta, b=tb, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                hunks[(tuple(ta[i1:i2]), tuple(tb[j1:j2]))].add(where)

    cats: dict[str, list] = defaultdict(list)
    for (before, after), where in hunks.items():
        cats[_classify(before, after)].append(
            {"before": list(before), "after": list(after),
             "where": sorted(where)})

    order = ("TEXT", "reflow", "blank-line", "indent/space")
    for line in one_sided:
        print(line)
    print("distinct hunks: " + ", ".join(
        f"{c} {len(cats.get(c, []))}" for c in order))
    for cat in order:
        for i, h in enumerate(cats.get(cat, []), 1):
            print(f"\n=== {cat} #{i} -- in {len(h['where'])} prompt(s), "
                  f"e.g. {', '.join(h['where'][:3])}")
            for sign, lines in (("-", h["before"]), ("+", h["after"])):
                if not lines:
                    print(f"  {sign} (no lines)")
                for line in lines:
                    print(f"  {sign} {line}")
    if json_out is not None:
        json_out.write_text(json.dumps({"only_one_side": one_sided, **cats},
                                       ensure_ascii=False, indent=1),
                            encoding="utf-8")
    return 1 if cats.get("TEXT") or one_sided else 0


# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    # Windows consoles default to cp1252; prompt text is not.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):        # pragma: no cover
        pass

    if argv[:1] == ["_child"]:
        return _child_main(argv[1], argv[2], int(argv[3]))

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save", help="assemble all 357 prompts")
    s.add_argument("outdir", type=Path)
    s.add_argument("--repo", type=Path, default=REPO,
                   help="checkout to assemble (default: this script's repo)")
    s.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 2))
    for name, text in (("diff", "compare fingerprints"),
                       ("wsdiff", "compare texts, whitespace ignored"),
                       ("classify", "label every differing hunk")):
        d = sub.add_parser(name, help=text)
        d.add_argument("a", type=Path)
        d.add_argument("b", type=Path)
        if name == "classify":
            d.add_argument("--json", type=Path, default=None)

    args = ap.parse_args(argv)
    if args.cmd == "save":
        return cmd_save(args.outdir.resolve(), args.repo.resolve(), args.jobs)
    if args.cmd == "diff":
        return cmd_diff(args.a, args.b)
    if args.cmd == "wsdiff":
        return cmd_wsdiff(args.a, args.b)
    return cmd_classify(args.a, args.b, args.json)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
