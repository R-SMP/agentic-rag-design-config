"""Validate (MAS-blueprint P7): every check of a setup, in one report.

    python -m studio validate [--pack <folder>] [--json <report.json>]
    python -m studio.validate part load | part prompts <combination> <topology>

What it checks (owner, 2026-10-19):

* **A. The setup loads** -- what the engine reads, with the engine's own
  checks: the setup's format; ``parameters.json``; ``pack.yaml`` (the
  agents' access to the parameter list, the Download buttons, the picture
  samples); every ``tool.yaml`` (with the texts each tool owns, the
  geometry tools, the outputs); every text, in each topology.  Two
  warnings: a text condition about a tool the setup does not have (it
  reads as switched off), and a secret a tool needs that this computer
  does not set.
* **B. The prompts** -- every agent of topologies 3 / 5 / 7, with the
  setup's defaults and with every feature on: built, and nothing left of a
  ``$name`` or a ``<<IF:...>>`` marker; the tokens of each.
* **C. The parameter lists** -- each agent's hand-written list names the
  parameters of ``parameters.json``, in order, with their ranges (a choice
  or on/off parameter: its values, and when it is used).
* **D. The tools** -- each run once on the parameters' defaults, as Test
  tool runs it (``studio/tools_edit.run_tool_test``): it answers and makes
  what its manifest declares.  A run that fails because this computer lacks
  a package, a program or a service is a warning, not a failure.
* **E. A scripted turn** -- one per topology, a fake model, no API cost
  (``extra_utilities/tests/dry_run_topology.py``).
* **Developer checks** that hold for any setup (:data:`DEV_CHECKS`, in
  ``extra_utilities/tests/``).

Each check runs in a process of its own, several at a time, on a COPY of
the setup taken when Validate starts (a check may write a probe file into
its copy) -- except the tools, which run on the setup itself, as Test tool
does, writing only into a throw-away folder.  The report keeps the setup's
fingerprint at the start: the Studio shows it as out of date once the
setup changes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "extra_utilities" / "tests"
TOPOLOGIES = (3, 5, 7)          # the order the report shows them in
COMBOS = (("base", "with the setup's defaults"), ("all_on", "with every feature on"))
PASS, WARN, FAIL = "pass", "warn", "fail"
PARTS = {
    "A": "The setup loads",
    "B": "The prompts",
    "C": "The parameter lists",
    "D": "The tools",
    "E": "A scripted turn",
    "X": "Developer checks",
}
# The checks of extra_utilities/tests/ that hold for any setup: (script,
# title, what it proves).  The others check the propeller's own answers.
DEV_CHECKS = (
    ("smoke_test_prompt_format", "Prompt format",
     "every prompt template formats with RAG off, on, and on with every database tool"),
    ("smoke_test_slot_splices", "Slot splices",
     "a text of several lines stands alone on its line"),
    ("smoke_test_topology_fragments", "Topology texts",
     "each topology reads only its own texts, and an agent's own copy wins for it alone"),
    ("smoke_test_parameters", "Parameters",
     "the parameter file, the lists, what the pages and the database get from it"),
    ("smoke_test_parameter_access", "Parameter access",
     "the access grid, its four states, every text condition"),
    ("smoke_test_agent_roles", "Agent roles",
     "the agents of each topology and whose past answers each may read"),
    ("smoke_test_hub_attributes", "Hub attributes",
     "each hub calls only the agents it has"),
)
# Checks that write into their copy of the setup get one of their own.
WRITES = {"smoke_test_topology_fragments"}
TIMEOUT = 600
TOOL_TIMEOUT = 180

_NAME_LEFT_RE = re.compile(r"(?<![\w$\\])\$([A-Za-z_][A-Za-z0-9_]*)")
_MARKER_LEFT_RE = re.compile(r"<</?(?:IF|IFNOT):[^<>\n]*>>")
_FLAG_RE = re.compile(r"<<(IF|IFNOT):([^<>]+)>>")
# What a tool run that failed for want of something on this computer says.
_LACKS = (
    (re.compile(r"OpenSCAD was not found"), "the program OpenSCAD"),
    (re.compile(r"No module named '([A-Za-z0-9_]+)"), "the Python package {}"),
    (re.compile(r"Cannot find (?:module|package) '([^']+)'"), "the Node package {}"),
    (re.compile(r"ERR_MODULE_NOT_FOUND"), "a Node package (node_modules)"),
    (re.compile(r"No such file or directory: '([A-Za-z0-9_.-]+)'"), "the program {}"),
    (re.compile(r"\[WinError 2\]"), "a program it starts"),
    (re.compile(r"Connection refused|Failed to establish a new connection|"
                r"Max retries exceeded|ConnectionRefusedError"),
     "a service it calls (it did not answer)"),
)


def item(part: str, title: str, status: str, lines=(), **extra) -> dict:
    return dict(part=part, title=title, status=status, lines=list(lines), **extra)


# ---------------------------------------------------------------------------
# A + C: one engine process (python -m studio.validate part load)
# ---------------------------------------------------------------------------

def _rel(path: Path, root: Path) -> str:
    try:
        return f"{root.name}/{path.relative_to(root).as_posix()}"
    except ValueError:
        return path.as_posix()


def _raise(problem: str | None) -> None:
    if problem:
        raise ValueError(problem)


def part_load() -> list[dict]:
    """A and C, in this process, for the setup in ``DC_PACK_DIR``."""
    from studio import engine_view
    engine_view.load_engine()
    import yaml

    from engine import image_run, pack, pack_flags, pack_tools
    from engine import parameter_access as pa
    from engine import parameters as ep
    from studio import params_edit
    pack_tools.read_overrides = lambda: {}      # the setup's own values, not this computer's
    root = pack.pack_dir()
    out: list[dict] = []

    def attempt(fn) -> list[str]:
        try:
            fn()
            return []
        except FileNotFoundError as exc:
            return [f"a file is missing: {exc.filename or exc}"]
        except yaml.YAMLError as exc:
            return [f"not valid YAML: {exc}"]
        except Exception as exc:                            # noqa: BLE001
            return [ln for ln in str(exc).split("\n") if ln.strip()] or [type(exc).__name__]

    # A. the setup's format (pack.yaml: pack_format)
    lines = attempt(lambda: _raise(pack.format_problem()))
    out.append(item("A", "The setup's format (pack.yaml)", FAIL if lines else PASS, lines))
    # A. parameters.json
    spec, lines = None, []
    try:
        spec = json.loads((root / "parameters.json").read_text(encoding="utf-8"))
        lines = ep.validate(spec)
    except FileNotFoundError:
        lines = ["parameters.json is missing"]
    except ValueError as exc:
        lines = [f"parameters.json is not valid JSON: {exc}"]
    spec_ok = not lines
    out.append(item("A", "parameters.json", FAIL if lines else PASS, lines,
                    link={"section": "parameters"}))
    # A. pack.yaml: the agents' access to the parameter list
    lines = attempt(pa.default_table)
    out.append(item("A", "Agent access (pack.yaml)", FAIL if lines else PASS, lines,
                    link={"section": "access"}))
    # A. the tools
    lines = attempt(pack_tools._read_manifests)
    tools_ok = not lines
    out.append(item("A", "The tools' manifests", FAIL if lines else PASS, lines,
                    link={"section": "tools"}))
    if tools_ok:
        lines = attempt(pack_tools.download_specs)
        out.append(item("A", "The Download buttons (pack.yaml)", FAIL if lines else PASS, lines,
                        link={"section": "settings"}))
    if spec_ok:
        lines = attempt(image_run.render_sample_sets)
        out.append(item("A", "The picture samples (pack.yaml)", FAIL if lines else PASS, lines,
                        link={"section": "settings"}))
    # A. every text, in each topology
    lines = []
    if tools_ok:
        for slot in sorted(pack.slots(source="pack", use="prompt")):
            for n in TOPOLOGIES:
                for problem in attempt(lambda: pack.read(slot, n)):
                    lines.append(f"${slot} (topology {n}): {problem}")
    out.append(item("A", "The texts", FAIL if lines else PASS, lines))
    # A. conditions about a tool the setup does not have (read as switched off)
    if tools_ok:
        dead: dict[str, list[str]] = {}
        for folder in pack.text_dirs():
            for f in sorted(folder.rglob("*.md")):
                for kind, name in _FLAG_RE.findall(f.read_text(encoding="utf-8", errors="replace")):
                    if pack_flags.absent(name) and pack_flags.near_tool(name) is None:
                        marks = dead.setdefault(_rel(f, root), [])
                        if f"<<{kind}:{name}>>" not in marks:
                            marks.append(f"<<{kind}:{name}>>")
        lines = [f"{f}: {', '.join(marks)}" for f, marks in sorted(dead.items())]
        out.append(item("A", "Text about a tool the setup does not have", WARN if lines else PASS,
                        lines, note=("These parts read as switched off; remove them, or bring "
                                     "the tool back." if lines else "")))
        # A. the secrets the tools need
        lines = []
        for name, m in pack_tools.manifests().items():
            for s in m.get("secrets") or []:
                if s.get("required") and not os.environ.get(s["env"]):
                    lines.append(f"{name} needs {s['env']} ({s.get('description', '')}): "
                                 f"this computer does not set it")
        out.append(item("A", "Secrets the tools need", WARN if lines else PASS, lines,
                        link={"section": "settings"}))
    # C. the parameter lists
    lines, files = [], 0
    if spec_ok:
        # a choice or on/off parameter has no range (MAS-blueprint P6d)
        want = [(p["name"], float(p["min"]), float(p["max"])) if "min" in p else (p["name"], None, None)
                for p in spec["parameters"]]
        folder = pack.fragments_dir() / pack.slot_spec(params_edit.LIST_SLOT)["folder"]
        for f in sorted(folder.glob(f"{params_edit.LIST_SLOT}*.md")):
            files += 1
            text = f.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
            entries = params_edit.parse_entries(text)
            got = [params_edit._entry_state(text[a:b]) for a, b, _ in entries]
            numbers = [int(params_edit.ENTRY_RE.match(text[a]).group(2)) for a, _b, _ in entries]
            where = _rel(f, root)
            if numbers != list(range(1, len(numbers) + 1)):
                lines.append(f"{where}: numbered {numbers}, not 1 to {len(numbers)}")
            if [g[0] for g in got] != [w[0] for w in want]:
                lines.append(f"{where}: names {[g[0] for g in got]}, but parameters.json has "
                             f"{[w[0] for w in want]}")
                continue
            for (name, lo, hi), (_n, wlo, whi) in zip(got, want):
                if lo is not None and wlo is not None and (lo, hi) != (wlo, whi):
                    lines.append(f"{where}: {name} [{lo:g}; {hi:g}], but parameters.json says "
                                 f"[{wlo:g}; {whi:g}]")
            for (a, b, _), p in zip(entries, spec["parameters"]):
                why = ep.entry_problem(p, " ".join(text[a:b]))
                if why:
                    lines.append(f"{where}: {p['name']} {why}")
        if not files:
            lines.append("no parameter list found")
    else:
        lines.append("parameters.json cannot be read (see A)")
    out.append(item("C", f"{files} parameter list(s)", FAIL if lines else PASS, lines,
                    link={"section": "parameters"}))
    return out


# ---------------------------------------------------------------------------
# B: one engine process per (combination, topology)
# ---------------------------------------------------------------------------

def part_prompts(combo: str, topology: int) -> dict:
    """Every agent's prompt of *topology* under the prompt matrix's
    *combo*, as the Studio assembles it (``studio/engine_view.py``), and the
    agents whose prompt could not be filled in."""
    from studio import engine_view
    engine_view.load_engine()
    engine_view.setup_defaults(combo)
    import topology_prompt_snapshot as T
    built = T._assemble(topology)
    return {"prompts": built["prompts"], "unformatted": built.get("unformatted") or {}}


def _prompt_items(results: dict, names: dict) -> list[dict]:
    """B: one item per topology, from ``{(combo, n): part_prompts or
    {"fatal": ...}}`` (the combinations and topologies given)."""
    from studio.server import count_tokens
    out = []
    for n in TOPOLOGIES:
        if not any((combo, n) in results for combo, _ in COMBOS):
            continue
        lines, tokens = [], {}
        for combo, label in COMBOS:
            r = results.get((combo, n))
            if r is None:
                continue
            if "fatal" in r:
                lines.append(f"{label}: the prompts could not be assembled: {r['fatal']}")
                continue
            for agent, text in sorted(r["prompts"].items()):
                who = names.get(agent, agent)
                if agent in r["unformatted"]:
                    lines.append(f"{label} · {who}: its prompt could not be filled in: "
                                 f"{r['unformatted'][agent]}")
                left = sorted(set(_NAME_LEFT_RE.findall(text)))
                if left:
                    lines.append(f"{label} · {who}: " + ", ".join(f"${x}" for x in left)
                                 + " left unfilled")
                marks = sorted(set(_MARKER_LEFT_RE.findall(text)))
                if marks:
                    lines.append(f"{label} · {who}: markers left: " + ", ".join(marks))
                if combo == "base":
                    tokens[agent] = count_tokens(text)
        out.append(item("B", f"Topology {n}", FAIL if lines else PASS, lines,
                        tokens={names.get(a, a): t for a, t in tokens.items()},
                        link={"section": "prompts", "topology": n}))
    return out


# ---------------------------------------------------------------------------
# D: the tools
# ---------------------------------------------------------------------------

def _lacks(text: str) -> str | None:
    for rx, what in _LACKS:
        m = rx.search(text)
        if m:
            return what.format(*(g for g in m.groups() if g)) if m.groups() else what
    return None


def tool_item(name: str, report: dict) -> dict:
    """D: one tool's run (a Test tool report) as an item."""
    text = "\n".join([str(report.get("error") or ""), str(report.get("answer") or "")]
                     + list(report.get("output") or []))
    mism = report.get("mismatches") or []
    secs = report.get("seconds")
    first = str(report.get("answer") or "").strip().split("\n")[0][:300]
    link = {"section": "tools", "tool": name}
    if report.get("failed"):
        err = [ln for ln in str(report.get("error") or report.get("answer") or "").strip()
               .split("\n") if ln.strip()][-3:]
        lacks = _lacks(text)
        if lacks:
            return item("D", name, WARN, [f"It could not run on this computer: it needs {lacks}."]
                        + err, link=link, seconds=secs)
        return item("D", name, FAIL, ["The run failed:"] + err, link=link, seconds=secs)
    bad = [m for m in mism if "does not declare" not in m]
    extra = [m for m in mism if "does not declare" in m]
    lines = bad + extra + ([f"It answered: {first}"] if first else [])
    return item("D", name, FAIL if bad else WARN if extra else PASS, lines, link=link,
                seconds=secs)


# ---------------------------------------------------------------------------
# E and the developer checks: scripts of extra_utilities/tests/
# ---------------------------------------------------------------------------

def _script_item(part: str, title: str, script: str, pack_copy: Path, about: str = "") -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", DC_PACK_DIR=str(pack_copy),
               DATABASE_URL="", DATABASE_PUBLIC_URL="")
    env.setdefault("OPENAI_API_KEY", "sk-dummy")
    t0 = time.perf_counter()
    try:
        proc = subprocess.run([sys.executable, str(TESTS / f"{script}.py")], cwd=str(REPO),
                              env=env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=TIMEOUT)
        output, code = (proc.stdout or "") + (proc.stderr or ""), proc.returncode
    except subprocess.TimeoutExpired:
        output, code = f"It took longer than {TIMEOUT} s and was stopped.", None
    secs = round(time.perf_counter() - t0, 1)
    lines = [ln.rstrip() for ln in output.splitlines() if ln.strip()]
    notes = [ln.strip() for ln in lines if ln.strip().startswith("[ABSENT]")]
    if code == 0:
        return item(part, title, PASS, [], about=about, seconds=secs, script=script,
                    notes=notes)
    # The problem lines: from the first failure report on, else the end.
    start = next((i for i, ln in enumerate(lines)
                  if re.match(r"\s*(FAIL|FATAL|problems:|Traceback)", ln)), max(0, len(lines) - 30))
    return item(part, title, FAIL, lines[start:start + 60], about=about, seconds=secs,
                script=script)


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def _child(args: list[str], pack_dir: Path) -> object:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", DC_PACK_DIR=str(pack_dir),
               DATABASE_URL="", DATABASE_PUBLIC_URL="")
    env.setdefault("OPENAI_API_KEY", "sk-dummy")
    proc = subprocess.run([sys.executable, "-m", "studio.validate", "part", *args],
                          cwd=str(REPO), env=env, capture_output=True, timeout=TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip()[-2000:] or "no output")
    return json.loads(proc.stdout.decode("utf-8"))


def _tools_and_defaults(pack_dir: Path) -> tuple[list[str], dict | None]:
    tools = sorted(p.parent.name for p in (pack_dir / "tools").glob("*/tool.yaml"))
    try:
        spec = json.loads((pack_dir / "parameters.json").read_text(encoding="utf-8"))
        return tools, {p["name"]: p["default"] for p in spec["parameters"]}
    except Exception:                                       # noqa: BLE001
        return tools, None


def run(pack_dir: Path, progress=None, workers: int | None = None) -> dict:
    """Validate the setup in *pack_dir*.  *progress(done, total, items)* is
    called as each check ends.  Returns the report: ``status`` (pass / warn /
    fail), ``items`` (A, B, C, D, E, then the developer checks), the
    ``fingerprint`` of the setup when it started, ``started``, ``seconds``."""
    from studio.server import fingerprint
    from studio.editing import copy_setup
    pack_dir = Path(pack_dir).resolve()
    t0 = time.perf_counter()
    report = {"pack_dir": str(pack_dir), "fingerprint": fingerprint(pack_dir),
              "started": datetime.now().isoformat(timespec="seconds")}
    tmp = Path(tempfile.mkdtemp(prefix="studio_validate_"))
    try:
        copy = copy_setup(pack_dir, tmp / "shared" / pack_dir.name)
        own = {s: copy_setup(pack_dir, tmp / s / pack_dir.name) for s in WRITES}
        tools, defaults = _tools_and_defaults(copy)
        jobs: list[tuple[str, object]] = [("load", lambda: _child(["load"], copy))]
        jobs += [(("prompts", c, n), (lambda c=c, n=n: _child(["prompts", c, str(n)], copy)))
                 for c, _ in COMBOS for n in TOPOLOGIES]
        if defaults is not None:
            from studio.tools_edit import run_tool_test
            jobs += [(("tool", t), (lambda t=t: tool_item(t, run_tool_test(
                REPO, pack_dir, t, defaults, None, TOOL_TIMEOUT)))) for t in tools]
        jobs.append(("E", lambda: _script_item("E", "One turn per topology, a fake model",
                                               "dry_run_topology", copy)))
        jobs += [(("X", s), (lambda s=s, t=t, a=a: _script_item("X", t, s, own.get(s, copy), a)))
                 for s, t, a in DEV_CHECKS]
        results: dict = {}
        done = [0]
        lock = threading.Lock()

        def one(key, fn):
            try:
                results[key] = fn()
            except Exception as exc:                        # noqa: BLE001
                results[key] = {"fatal": f"{type(exc).__name__}: {exc}"}
            with lock:
                done[0] += 1
                if progress:
                    progress(done[0], len(jobs), _items(results, tools, defaults))

        with ThreadPoolExecutor(max_workers=workers or max(2, min(8, (os.cpu_count() or 4)))) as pool:
            for f in [pool.submit(one, k, fn) for k, fn in jobs]:
                f.result()
        report["items"] = _items(results, tools, defaults)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    statuses = {i["status"] for i in report["items"]}
    report["status"] = FAIL if FAIL in statuses else WARN if WARN in statuses else PASS
    report["seconds"] = round(time.perf_counter() - t0, 1)
    report["counts"] = {s: sum(1 for i in report["items"] if i["status"] == s)
                        for s in (PASS, WARN, FAIL)}
    return report


def _names() -> dict:
    """agent key -> display name (``agents/shared/agent_roles.py``), read as
    source: this process does not load the engine."""
    try:
        text = (REPO / "agents/shared/agent_roles.py").read_text(encoding="utf-8")
    except OSError:
        return {}
    block = text.split("DISPLAY: dict[str, str] = {", 1)[-1].split("}", 1)[0]
    return dict(re.findall(r'"([a-z_]+)":\s*"([^"]+)"', block),
                database_handler="Database Handler")


def _items(results: dict, tools: list[str], defaults) -> list[dict]:
    """The report's items, in order, from the checks ended so far."""
    out: list[dict] = []
    load = results.get("load")
    if isinstance(load, list):
        out += [i for i in load if i["part"] == "A"]
    elif isinstance(load, dict):
        out.append(item("A", "The setup loads", FAIL, [load.get("fatal", "")]))
    if any(k[0] == "prompts" for k in results if isinstance(k, tuple)):
        got = {(k[1], k[2]): v for k, v in results.items()
               if isinstance(k, tuple) and k[0] == "prompts"}
        if len(got) == len(COMBOS) * len(TOPOLOGIES):
            out += _prompt_items(got, _names())
    if isinstance(load, list):
        out += [i for i in load if i["part"] == "C"]
    if defaults is None:
        out.append(item("D", "The tools", FAIL, ["parameters.json cannot be read (see A): "
                                                 "the tools are not run"]))
    for t in tools:
        r = results.get(("tool", t))
        if isinstance(r, dict) and "part" in r:
            out.append(r)
        elif isinstance(r, dict):
            out.append(item("D", t, FAIL, [r.get("fatal", "")]))
    if "E" in results:
        r = results["E"]
        out.append(r if "part" in r else item("E", "One turn per topology", FAIL,
                                              [r.get("fatal", "")]))
    for s, t, _a in DEV_CHECKS:
        r = results.get(("X", s))
        if r is not None:
            out.append(r if "part" in r else item("X", t, FAIL, [r.get("fatal", "")]))
    return out


def text_report(report: dict) -> str:
    """The report as text (the command line)."""
    mark = {PASS: "ok  ", WARN: "WARN", FAIL: "FAIL"}
    lines, part = [], None
    for i in report["items"]:
        if i["part"] != part:
            part = i["part"]
            lines.append(f"\n{part}. {PARTS[part]}")
        lines.append(f"  {mark[i['status']]}  {i['title']}")
        lines += [f"          {ln}" for ln in i["lines"][:40]]
    c = report["counts"]
    lines.append(f"\n{report['status'].upper()}: {c[PASS]} passed, {c[WARN]} warning(s), "
                 f"{c[FAIL]} failed, in {report['seconds']} s.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """``python -m studio validate`` (``studio/__main__.py``): 0 when nothing
    failed, 1 otherwise."""
    import argparse
    ap = argparse.ArgumentParser(prog="python -m studio validate")
    ap.add_argument("--pack", default=os.getenv("DC_PACK_DIR") or "dc_pack")
    ap.add_argument("--json", help="also write the report here")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):        # a console's code page may lack a character
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    pack = Path(args.pack)
    if not pack.is_absolute():
        pack = REPO / pack
    if not (pack / "pack.yaml").is_file():
        print(f"{pack} is not a setup (it has no pack.yaml).", file=sys.stderr)
        return 2
    report = run(pack, progress=lambda d, n, _i: print(f"\r{d}/{n} checks done", end="",
                                                       file=sys.stderr, flush=True))
    print(file=sys.stderr)
    print(text_report(report))
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 1 if report["status"] == FAIL else 0


def _part_main(argv: list[str]) -> int:
    try:
        if argv[:1] == ["load"]:
            payload = part_load()
        elif argv[:1] == ["prompts"] and len(argv) == 3:
            payload = part_prompts(argv[1], int(argv[2]))
        else:
            sys.stderr.write(__doc__.split("\n\n")[1] + "\n")
            return 2
    except Exception as exc:                                # noqa: BLE001
        payload = {"fatal": f"{type(exc).__name__}: {exc}",
                   "trace": traceback.format_exc()[-2000:]}
    sys.stdout.buffer.write(json.dumps(payload, default=str).encode("utf-8"))
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["part"]:
        raise SystemExit(_part_main(sys.argv[2:]))
    raise SystemExit(main(sys.argv[1:]))
