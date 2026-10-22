"""Prepare for GitHub (MAS-blueprint P7-3): a package made ready to commit.

    python -m studio prepare [--report <validate.json>]

Run in a folder made by **Download full package** (it has
``setup_info.json``).  It never runs git (owner, 2026-10-19: committing and
pushing are the user's): it checks and fixes the folder, then prints the
commands to run.

1. **Validate** (``studio/validate.py``) on ``setups/<setup>/`` as it is now -- or
   the report of ``python -m studio validate --json`` given with
   ``--report``, when the setup has not changed since; a failure stops it.
2. **``.gitignore`` and ``.dockerignore``**: what must stay out of git
   (``.env``, logs, attempts, past sessions, the Workflow Settings saved on
   this computer, ...) and out of the image is added where it is missing; a
   line that would leave the package's own configurator out is removed.
3. **The tools' dependencies**: merged again into ``requirements.txt`` and
   the ``Dockerfile`` (``studio/package.py``; a part merged before is
   replaced).
4. **``DEPLOY.md`` and ``setup_info.json``** written again for the setup
   as it is now (``README.md`` is kept once it exists).
5. **The key scan** of every file ``git add .`` would take: what looks like
   an API key or a private key, and every value set in this folder's
   ``.env``.  Listed (masked) to be removed before committing.
6. **The commands**: a first commit and a private GitHub repository, or --
   once ``.git/config`` names a remote -- a commit and a push.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from engine import setups as _setups
from studio import package as K

# (a path, is it a folder, the line that keeps it out) -- what git must not take
GIT_OUT = (
    (".env", False, ".env"), ("agents/.env", False, "*.env"),
    ("logs", True, "logs/"), ("attempts", True, "attempts/"), ("database", True, "database/"),
    ("previous_sessions", True, "previous_sessions/"), ("node_modules", True, "node_modules/"),
    ("__pycache__", True, "__pycache__/"), ("web/render_samples", True, "web/render_samples/"),
    ("inputs/input_images/a.png", False, "inputs/input_images/*"),
    ("inputs/user_query.txt", False, "inputs/user_query.txt"),
    ("inputs/extracted_inputs.txt", False, "inputs/extracted_inputs.txt"),
    ("workspace", True, "workspace/"),
    *((rel, False, rel) for rel in sorted(K.STATE_FILES)),
    *((rel.rstrip("/"), True, rel) for rel in K.STATE_DIRS),
)
GIT_IN = ((".env.example", "!.env.example"),)
DOCKER_OUT = (".env", ".git/", "logs/", "attempts/", "previous_sessions/", "database/",
              "node_modules/", "workspace/")
MARK = "# added by python -m studio prepare"


class PrepareError(ValueError):
    pass


def setup_dir(folder: Path) -> Path | None:
    """The package's one configurator, ``setups/<setup>/``, or None."""
    found = _setups.all_setups(folder)
    return found[0] if len(found) == 1 else None


def check_folder(folder: Path, pack_dir: Path | None = None) -> str | None:
    """Why prepare cannot run here, or None: it works in a folder made by
    Download full package, on that folder's one ``setups/<setup>/`` -- never
    in the MAS blueprint's own repository (it has ``extra_utilities/docs/``,
    which no package holds)."""
    if (folder / "extra_utilities" / "docs").is_dir():
        return ("This is the MAS blueprint's own repository: prepare works in a folder made by "
                "Download full package.")
    if not (folder / K.INFO).is_file() or not (folder / "studio").is_dir():
        return ("Prepare works in a folder made by Download full package (it has setup_info.json); "
                "this one was not.")
    found = _setups.all_setups(folder)
    if not found:
        return "This folder has no setups/<name>/ with a pack.yaml."
    if len(found) > 1:
        return (f"A package holds one configurator; this folder has {len(found)} in setups/ ("
                + ", ".join(p.name for p in found) + ").")
    if pack_dir is not None and pack_dir.resolve() != found[0].resolve():
        return f"Prepare works on the package's own setups/{found[0].name}/, not on {pack_dir}."
    return None


def _write_if(path: Path, text: str) -> bool:
    raw = text.encode("utf-8")
    if path.is_file() and path.read_bytes() == raw:
        return False
    path.write_bytes(raw)
    return True


def _add_lines(path: Path, lines: list[str]) -> bool:
    if not lines:
        return False
    old = path.read_bytes().decode("utf-8") if path.is_file() else ""
    eol = "\r\n" if "\r\n" in old else "\n"
    body = old if not old or old.endswith(("\n", "\r\n")) else old + eol
    path.write_text(body + eol.join(["", MARK] + lines) + eol, encoding="utf-8", newline="")
    return True


def repair_ignores(folder: Path) -> list[str]:
    """What must stay out of git and out of the image, added where the
    folder's ``.gitignore`` / ``.dockerignore`` miss it, and a line that
    would leave the package's own configurator out removed: the changes
    made."""
    changes = []
    own = f"{K.SETUPS}/{setup_dir(folder).name}"

    def leaves_it_out(line: str) -> bool:
        rules = K.IgnoreRules(line)
        return rules.ignored(own, True) or rules.ignored(K.SETUPS, True)

    for rel in (".gitignore", ".dockerignore"):
        f = folder / rel
        if f.is_file():
            text, gone = K.drop_ignore_lines(f.read_bytes().decode("utf-8"), leaves_it_out)
            if gone:
                f.write_bytes(text.encode("utf-8"))
                changes.append(f"{rel}: removed " + ", ".join(gone) + f" (it left {own}/ out)")
    gi = folder / ".gitignore"
    rules = K.IgnoreRules(gi.read_text(encoding="utf-8") if gi.is_file() else "")
    add = [line for rel, is_dir, line in GIT_OUT if not rules.ignored(rel, is_dir)]
    rules = K.IgnoreRules((gi.read_text(encoding="utf-8") if gi.is_file() else "") + "\n" + "\n".join(add))
    add += [line for rel, line in GIT_IN if rules.ignored(rel)]
    if _add_lines(gi, add):
        changes.append(".gitignore: added " + ", ".join(add))
    di = folder / ".dockerignore"
    have = {ln.strip().rstrip("/") for ln in (di.read_text(encoding="utf-8").splitlines() if di.is_file() else [])}
    add = [line for line in DOCKER_OUT if line.rstrip("/") not in have]
    if _add_lines(di, add):
        changes.append(".dockerignore: added " + ", ".join(add))
    return changes


def _title(folder: Path) -> str:
    """The configurator's title: its ``$app_title`` text, else ``$dc_name``,
    else what setup_info.json says."""
    for name in ("app_title", "dc_name"):
        f = setup_dir(folder) / "fragments" / "dc" / f"{name}.md"
        if f.is_file() and f.read_text(encoding="utf-8").strip():
            return " ".join(f.read_text(encoding="utf-8").split())
    try:
        return json.loads((folder / K.INFO).read_text(encoding="utf-8")).get("configurator") or folder.name
    except (OSError, ValueError):
        return folder.name


def _remote(folder: Path) -> str | None:
    """The remote ``.git/config`` names (read as a file: no git is run)."""
    cfg = folder / ".git" / "config"
    if not cfg.is_file():
        return None
    m = re.search(r'\[remote "([^"]+)"\]', cfg.read_text(encoding="utf-8", errors="replace"))
    return m.group(1) if m else None


def commands(folder: Path, name: str, title: str) -> dict:
    """``{"case", "steps": [[what, command]], "manual": [...]}``: the git
    commands for this folder, first time or later."""
    remote = _remote(folder)
    msg = title.replace('"', "'")
    if remote:
        return {"case": "update", "remote": remote, "steps": [
            ["Take every change", "git add ."],
            ["Commit it", f'git commit -m "{msg}: changes"'],
            ["Push it (Railway deploys it)", "git push"]], "manual": []}
    steps = [] if (folder / ".git").exists() else [["Start a git repository", "git init -b main"]]
    steps += [["Take every file", "git add ."],
              ["The first commit", f'git commit -m "{msg}"'],
              ["A private GitHub repository, pushed (GitHub CLI)", f"gh repo create {name} --private --source . --push"]]
    return {"case": "first", "remote": None, "steps": steps, "manual": [
        "Without the GitHub CLI: create an empty private repository on github.com, then",
        "git remote add origin <its address>",
        "git push -u origin main"]}


def run(folder: Path, report: dict | None = None, progress=None) -> dict:
    """Prepare *folder*; *report* is a Validate report of its setup as it is
    now (else Validate runs).  Returns ``{ok, validate, changes, notes,
    findings, commands}``; ``ok`` False when Validate found a failure (then
    nothing is changed)."""
    from studio import validate as V
    folder = folder.resolve()
    why = check_folder(folder)
    if why:
        raise PrepareError(why)
    pack_dir = setup_dir(folder)
    where = f"{K.SETUPS}/{pack_dir.name}"
    if report is None:
        report = V.run(pack_dir, progress=progress)
    out = {"ok": report["status"] != V.FAIL, "validate": {"status": report["status"],
           "counts": report["counts"], "when": report["started"]},
           "failed": [{"title": i["title"], "lines": i["lines"][:6]} for i in report["items"]
                      if i["status"] == V.FAIL],
           "changes": [], "notes": [], "findings": [], "commands": None}
    if not out["ok"]:
        return out
    out["changes"] += repair_ignores(folder)
    setup = K.setup_files(pack_dir)
    for rel, text_notes in (
            ("requirements.txt", lambda t: K.merge_requirements(t, setup, where)),
            ("Dockerfile", lambda t: K.merge_apt(t, setup))):
        text, notes = text_notes((folder / rel).read_bytes().decode("utf-8"))
        out["notes"] += notes
        if _write_if(folder / rel, text):
            out["changes"].append(f"{rel}: the tools' dependencies merged again")
    title = _title(folder)
    name = K.slug(title)
    try:
        before = json.loads((folder / K.INFO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        before = {}
    # what the download wrote (the engine it came from, when), with this run's setup and result
    new = K.setup_info(pack_dir, title, {"report": report, "current": True},
                       engine=before.get("engine") or "unknown")
    info = dict(new, made=before.get("made") or new["made"], prepared=new["made"])
    secrets = K._secrets(setup)
    env_ex = folder / ".env.example"
    if env_ex.is_file() and _write_if(env_ex, K.env_example(env_ex.read_bytes().decode("utf-8"), secrets)):
        out["changes"].append(".env.example: the tools' variables added")
    if _write_if(folder / "DEPLOY.md", K.deploy_md(title, title, name, secrets, info, where)):
        out["changes"].append("DEPLOY.md: written again for the setup as it is now")
    if not (folder / "README.md").is_file():
        (folder / "README.md").write_text(K.readme_md(title, title, where), encoding="utf-8")
        out["changes"].append("README.md: written")
    (folder / K.INFO).write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    files = {rel: (folder / rel).read_bytes() for rel in K.files_git_takes(folder)}
    out["findings"] = K.scan(files) + K.scan_values(files, K.env_values(folder))
    out["commands"] = commands(folder, name, title)
    return out


def text_report(out: dict) -> str:
    v = out["validate"]
    c = v["counts"]
    lines = [f"Validate: {c['fail']} failed, {c['warn']} warning(s), {c['pass']} passed."]
    if not out["ok"]:
        lines.append("\nValidate found failures: fix them first (python -m studio, Validate).")
        for f in out["failed"]:
            lines.append(f"  FAIL  {f['title']}")
            lines += [f"          {ln}" for ln in f["lines"]]
        return "\n".join(lines)
    lines.append("\nWhat prepare changed:" if out["changes"] else "\nNothing needed changing.")
    lines += [f"  {c}" for c in out["changes"]]
    if out["notes"]:
        lines.append("\nThe tools' dependencies:")
        lines += [f"  {n}" for n in out["notes"]]
    if out["findings"]:
        lines.append(f"\nSomething here looks like a key ({len(out['findings'])}): remove it before you "
                     f"commit -- keys belong in .env (which git ignores) or in the deployment's "
                     f"variables.")
        lines += [f"  {f['file']}:{f['line']}  {f['what']}: {f['shown']}" for f in out["findings"]]
    cmd = out["commands"]
    lines.append("\nNothing was committed: prepare never runs git.  To commit"
                 + (" and push (Railway then deploys it):" if cmd["case"] == "update"
                    else " and create the private GitHub repository:"))
    for what, command in cmd["steps"]:
        lines += [f"  # {what}", f"  {command}"]
    if cmd["manual"]:
        lines.append("")
        lines += [f"  {m}" for m in cmd["manual"]]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """``python -m studio prepare``: 0 when the folder is ready, 1 when
    Validate failed, 2 when this is no package folder."""
    import argparse
    from studio import validate as V
    from studio.server import fingerprint
    ap = argparse.ArgumentParser(prog="python -m studio prepare")
    ap.add_argument("--report", help="a report of python -m studio validate --json, used when "
                                     "the setup has not changed since")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    folder = Path.cwd()
    why = check_folder(folder)
    if why:
        print(why, file=sys.stderr)
        return 2
    report = None
    if args.report:
        try:
            r = json.loads(Path(args.report).read_text(encoding="utf-8"))
            if r.get("fingerprint") == fingerprint(setup_dir(folder)):
                report = r
                print("Using the Validate report given (the setup has not changed since).", file=sys.stderr)
            else:
                print("The setup changed since that report: Validate runs again.", file=sys.stderr)
        except (OSError, ValueError):
            print("That report cannot be read: Validate runs again.", file=sys.stderr)
    out = run(folder, report, progress=lambda d, n, _i: print(f"\rValidate: {d}/{n} checks done", end="",
                                                              file=sys.stderr, flush=True))
    print(file=sys.stderr)
    print(text_report(out))
    return 0 if out["ok"] else 1
