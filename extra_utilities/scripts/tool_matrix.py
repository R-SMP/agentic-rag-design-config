"""Record which tools every agent is given, under the prompt matrix's setting
combinations x topologies, and compare two such records.

Why
---
``prompt_matrix.py`` proves the SYSTEM PROMPTS did not move.  An agent's tools
are the other half of what the model sees: each tool's name, description and
argument schema.  The MAS-blueprint phase P3 moves tool bindings out of the
agent classes (the parameter-access table, then tool plugins); this is the
check that the tools every agent receives stay the same.

Usage
-----
    py -3.13 extra_utilities/scripts/tool_matrix.py save <out.json> [--full] [--jobs N]
    py -3.13 extra_utilities/scripts/tool_matrix.py diff <A.json> <B.json>

``save`` builds each topology's real hub -- every agent constructed, exactly
as a session does -- with a stand-in model that records every
``bind_tools`` call made while the agents are built.  It writes, per
(combination, topology, agent), each call's tools in order: the name and a
SHA-256 of the description and argument schema.  ``--full`` also writes the
texts themselves (large; for looking at a difference, not for committing).
``diff`` compares two records and names every agent whose tools changed.
Exit status 0 when nothing differs.

Only the tools bound while an agent is BUILT are recorded.  Tools an agent
binds for one turn later (the Database Handler's forced tools, the hub's
feedback round) are not.

The committed baseline is ``extra_utilities/prompt_matrix/tool_baseline.json``.
Children run like ``prompt_matrix.py``'s: one process per (combination,
topology), compiling into a fresh bytecode cache.  Nothing is sent anywhere.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from prompt_matrix import CONFIGS, TOPOLOGIES  # noqa: E402


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


def _describe(tool) -> dict:
    """Name, description and argument schema of one bound tool."""
    if isinstance(tool, dict):                       # an OpenAI-format dict
        fn = tool.get("function", tool)
        return {"name": fn.get("name"), "description": fn.get("description", ""),
                "args": fn.get("parameters")}
    name = getattr(tool, "name", None) or getattr(tool, "__name__", repr(tool))
    try:
        args = tool.tool_call_schema.model_json_schema()
    except Exception:                                # noqa: BLE001
        args = getattr(tool, "args", None)
    return {"name": name, "description": getattr(tool, "description", "") or "",
            "args": args}


# ---------------------------------------------------------------------------
# Child: build one topology's hub under one combination
# ---------------------------------------------------------------------------

def _child_main(repo: str, config: str, topology: int, full: bool) -> int:
    repo_p = Path(repo)
    for p in ("extra_utilities/scripts", "extra_utilities/prompt_pdf", "."):
        sys.path.insert(0, str(repo_p / p))
    sys.modules["simplejson"] = None          # type: ignore[assignment]
    sys.modules["chardet"] = None             # type: ignore[assignment]
    import bootstrap                          # noqa: E402
    bootstrap.install()

    import prompt_matrix                      # noqa: E402
    S = prompt_matrix.apply_config(config)
    S.SYSTEM_TOPOLOGY = topology

    from unittest.mock import MagicMock       # noqa: E402

    from agents.hub import build_hub          # noqa: E402
    from agents.shared import llm_provider    # noqa: E402
    from agents.shared.session import Session  # noqa: E402

    calls: dict[str, list] = {}

    class _RecordingCache:
        """Hands every agent its own stand-in model, which records the
        tools it is bound to."""

        def get_for_agent(self, agent_key):
            provider, model, _ = llm_provider._resolve_config(agent_key)
            llm = MagicMock(name=f"llm:{agent_key}")

            def bind_tools(tools, **kwargs):
                entry = {"kwargs": {k: repr(v) for k, v in sorted(kwargs.items())},
                         "tools": []}
                for t in tools:
                    d = _describe(t)
                    row = {"name": d["name"], "sha": _sha(d)}
                    if full:
                        row.update(description=d["description"], args=d["args"])
                    entry["tools"].append(row)
                calls.setdefault(agent_key, []).append(entry)
                return MagicMock(name=f"bound:{agent_key}")

            llm.bind_tools.side_effect = bind_tools
            return llm, provider, model

    # The hub passes its cache on to nobody: every sub-agent takes the
    # module-level default.  Replace both.
    from agents.shared import base_chain_agent  # noqa: E402
    recorder = _RecordingCache()
    base_chain_agent._default_llm_cache = recorder
    session = Session(session_id=f"tool_matrix_{config}_{topology}",
                      session_ts=datetime.datetime.now(datetime.timezone.utc))
    build_hub(session, llm_cache=recorder)
    sys.stdout.buffer.write(json.dumps({"calls": calls}).encode("utf-8"))
    return 0


def _run_child(repo: Path, config: str, topology: int, cache: str,
               full: bool) -> dict:
    env = dict(os.environ, PYTHONPYCACHEPREFIX=cache, PYTHONIOENCODING="utf-8")
    env.setdefault("OPENAI_API_KEY", "sk-dummy")
    # Never reach a database while building agents.
    env["DATABASE_URL"] = env["DATABASE_PUBLIC_URL"] = ""
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "_child", str(repo),
         config, str(topology), "1" if full else "0"],
        capture_output=True, cwd=str(repo), env=env)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[-3000:])
    return json.loads(proc.stdout.decode("utf-8"))


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True).stdout.strip()


def cmd_save(out: Path, repo: Path, jobs: int, full: bool) -> int:
    jobs_list = [(c, n) for c in CONFIGS for n in TOPOLOGIES]
    results, failures = {}, {}
    with tempfile.TemporaryDirectory(prefix="tool_matrix_pyc_") as cache:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {pool.submit(_run_child, repo, c, n, cache, full): (c, n)
                       for c, n in jobs_list}
            for fut in concurrent.futures.as_completed(futures):
                try:
                    results[futures[fut]] = fut.result()
                except Exception as exc:              # noqa: BLE001
                    failures[futures[fut]] = str(exc)
    if failures:
        for (c, n), err in sorted(failures.items()):
            print(f"FAIL {c} / topology {n}\n{err}\n")
        print(f"{len(failures)} of {len(jobs_list)} builds failed; nothing written.")
        return 1
    record: dict = {"_meta": {
        "branch": _git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "commit": _git(repo, "rev-parse", "HEAD"),
        "uncommitted_changes": bool(_git(repo, "status", "--porcelain")),
        "taken": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "full": full,
    }}
    n_tools = 0
    for c, n in jobs_list:
        calls = results[(c, n)]["calls"]
        record[f"{c}/{n}"] = {a: calls[a] for a in sorted(calls)}
        n_tools += sum(len(e["tools"]) for es in calls.values() for e in es)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    meta = record["_meta"]
    print(f"{n_tools} tool bindings from {len(jobs_list)} hub builds -> {out}")
    print(f"commit {meta['commit'][:12]} on {meta['branch']}"
          + ("  (WITH uncommitted changes)" if meta["uncommitted_changes"] else ""))
    return 0


def cmd_diff(a: Path, b: Path) -> int:
    ra = json.loads(a.read_text(encoding="utf-8"))
    rb = json.loads(b.read_text(encoding="utf-8"))
    keys = sorted(k for k in set(ra) | set(rb) if not k.startswith("_"))
    same = differ = 0
    for key in keys:
        ka, kb = ra.get(key), rb.get(key)
        if ka is None or kb is None:
            print(f"ONLY IN {'B' if ka is None else 'A'}  {key}")
            differ += 1
            continue
        for agent in sorted(set(ka) | set(kb)):
            ca, cb = ka.get(agent), kb.get(agent)

            def strip(cs):
                return [{"kwargs": e["kwargs"],
                         "tools": [(t["name"], t["sha"]) for t in e["tools"]]}
                        for e in cs or []]
            if strip(ca) == strip(cb):
                same += 1
                continue
            differ += 1
            na = [t["name"] for e in ca or [] for t in e["tools"]]
            nb = [t["name"] for e in cb or [] for t in e["tools"]]
            if na != nb:
                print(f"DIFF  {key} {agent}: tools {na} -> {nb}")
            else:
                changed = sorted({t1["name"] for e1, e2 in zip(ca, cb)
                                  for t1, t2 in zip(e1["tools"], e2["tools"])
                                  if t1["sha"] != t2["sha"]})
                print(f"DIFF  {key} {agent}: text of {changed or 'binding options'}")
    print(f"\n{same} agent tool sets identical, {differ} difference(s).")
    return 1 if differ else 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["_child"]:
        return _child_main(argv[1], argv[2], int(argv[3]), argv[4] == "1")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save")
    s.add_argument("out", type=Path)
    s.add_argument("--repo", type=Path, default=REPO)
    s.add_argument("--jobs", type=int, default=6)
    s.add_argument("--full", action="store_true")
    d = sub.add_parser("diff")
    d.add_argument("a", type=Path)
    d.add_argument("b", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "save":
        return cmd_save(args.out, args.repo.resolve(), args.jobs, args.full)
    return cmd_diff(args.a, args.b)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
