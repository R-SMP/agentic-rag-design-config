"""The two downloads (MAS-blueprint P7-2): the setup file and the full package.

* **The setup file** -- ``<name>_setup.zip``: the setup's files under
  ``dc_pack/`` and ``setup_info.json`` (the Studio that made it, when, the
  engine's version, the setup's format, Validate's last result).  It holds
  no secret: the Studio has none.  Open setup file reads it back
  (:func:`read_setup_file`) and the Studio's setup is replaced by it.
* **The full package** -- ``<name>_package.zip``, one folder: the engine
  (:func:`engine_files`), the Studio with the checks Validate runs, this
  setup as ``dc_pack/``, and files written for it: ``README.md`` and
  ``DEPLOY.md`` (from ``package_files/``), ``.env.example`` with the
  variables its tools declare, a tool's own ``requirements.txt`` /
  ``apt.txt`` merged into ``requirements.txt`` and the ``Dockerfile``
  (:func:`merge_requirements`, :func:`merge_apt`), ``setup_info.json``.
  Not in it: the repository's notes, docs, benchmarks and the checks that
  hold for the propeller only; logs, attempts, past sessions; ``.env`` and
  the Workflow Settings saved on this computer.
* **The key scan** (:func:`scan`) -- every text file of a download, for what
  looks like an API key or a private key: a warning with the value masked
  (owner, 2026-10-19: the download is still possible).
"""

from __future__ import annotations

import fnmatch
import io
import json
import re
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
FILES = Path(__file__).resolve().parent / "package_files"
SETUP_DIR = "dc_pack"
INFO = "setup_info.json"
# The engine: these folders and files of the repository.
ENGINE_DIRS = ("agents", "engine", "tools", "web", "workflow_settings", "studio")
ENGINE_FILES = (
    "web_app.py", "main.py", "config.py", "requirements.txt", "requirements-web.txt",
    "package.json", "Dockerfile", "docker-compose.yml", ".dockerignore", ".gitignore",
    # what the Studio assembles prompts with
    "extra_utilities/scripts/prompt_matrix.py", "extra_utilities/scripts/topology_prompt_snapshot.py",
    "extra_utilities/scripts/tool_matrix.py", "extra_utilities/scripts/hub_registry.py",
    "extra_utilities/prompt_pdf/bootstrap.py",
    # the database's tables (DEPLOY.md: a database)
    "extra_utilities/db_design/apply_schema.py",
    "extra_utilities/db_design/database_PostgreSQL_schema_v9.sql",
    # the checks Validate runs (studio/validate.py)
    "extra_utilities/tests/dry_run_topology.py",
    "extra_utilities/tests/smoke_test_prompt_format.py",
    "extra_utilities/tests/smoke_test_slot_splices.py",
    "extra_utilities/tests/smoke_test_topology_fragments.py",
    "extra_utilities/tests/smoke_test_parameters.py",
    "extra_utilities/tests/smoke_test_parameter_access.py",
    "extra_utilities/tests/smoke_test_agent_roles.py",
    "extra_utilities/tests/smoke_test_hub_attributes.py",
)
SKIP_DIRS = {"__pycache__", "node_modules", ".git", "logs", "attempts", "database",
             "previous_sessions", "render_samples"}
# What the app writes on this computer: the Workflow Settings saved here.
STATE_FILES = {"workflow_settings/tool_settings.json", "workflow_settings/parameter_access.json",
               "workflow_settings/ocr_region_crops_access.json",
               "workflow_settings/dh_schedule.json", "workflow_settings/dh_schedule_5agents.json",
               "workflow_settings/dh_schedule_3agents.json"}
MAX_ZIP = 50 * 1024 * 1024
MAX_UNPACKED = 200 * 1024 * 1024
MAX_ENTRIES = 5000

KEY_PATTERNS = (
    ("an OpenAI, Anthropic or OpenRouter key",
     re.compile(r"\bsk-(?:ant-|proj-|or-v1-)?[A-Za-z0-9_-]{20,}")),
    ("a Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("an AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("a GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})")),
    ("a Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("a Voyage key", re.compile(r"\bpa-[A-Za-z0-9_-]{40,}")),
    ("a private key", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    ("a secret written into a file",
     re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password|passwd)\b[\"']?\s*[:=]\s*[\"']"
                r"([^\"'\s]{16,})[\"']")),
)


class PackageError(ValueError):
    """A setup file that cannot be opened, with every reason."""

    def __init__(self, message: str, problems: list[str] | None = None):
        super().__init__(message)
        self.problems = problems or []


# ---------------------------------------------------------------------------
# what goes in
# ---------------------------------------------------------------------------

def _skipped(rel: str) -> bool:
    parts = rel.split("/")
    name = parts[-1]
    return (bool(SKIP_DIRS & set(parts[:-1])) or rel in STATE_FILES
            or name.endswith((".pyc", ".pyo")) or name == ".DS_Store"
            or (name.endswith(".env") or name == ".env") and not name.endswith(".env.example"))


def _git_files(repo: Path) -> list[str] | None:
    try:
        # tracked, and new files git does not ignore
        out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z", "--cached", "--others",
                              "--exclude-standard"], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]


def engine_files(repo: Path = REPO, use_git: bool = True) -> list[str]:
    """The engine's files that go into a package (paths from the repository
    root): what git has or would take in :data:`ENGINE_DIRS` and
    :data:`ENGINE_FILES` (not what it ignores) -- or, outside a git checkout,
    what is there -- less what the app wrote on this computer
    (:func:`_skipped`)."""
    def wanted(rel: str) -> bool:
        return rel in ENGINE_FILES or rel.split("/", 1)[0] in ENGINE_DIRS
    tracked = _git_files(repo) if use_git else None
    if tracked is not None:
        rels = [r for r in tracked if wanted(r) and (repo / r).is_file()]
    else:
        rels = [p.relative_to(repo).as_posix() for d in ENGINE_DIRS if (repo / d).is_dir()
                for p in (repo / d).rglob("*") if p.is_file()]
        rels += [r for r in ENGINE_FILES if (repo / r).is_file()]
    return sorted(r for r in set(rels) if not _skipped(r))


def setup_files(pack_dir: Path) -> dict[str, Path]:
    """The setup's files, by path inside it (no caches)."""
    return {p.relative_to(pack_dir).as_posix(): p for p in sorted(pack_dir.rglob("*"))
            if p.is_file() and not ({"__pycache__", "node_modules"} & set(p.relative_to(pack_dir).parts))}


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return s[:48].rstrip("_") or "setup"


def engine_version(repo: Path = REPO) -> str:
    """The engine's git commit (with ``+changes`` when its files differ from
    it), or ``unknown`` outside a git checkout."""
    try:
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=30)
        if head.returncode != 0:
            return "unknown"
        dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--",
                                *ENGINE_DIRS], capture_output=True, text=True, timeout=60)
        return head.stdout.strip() + ("+changes" if dirty.stdout.strip() else "")
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def pack_format(pack_dir: Path) -> int | None:
    try:
        data = yaml.safe_load((pack_dir / "pack.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    return data.get("pack_format", 1) if isinstance(data, dict) else None


def setup_info(pack_dir: Path, name: str, validation: dict | None, engine: str | None = None) -> dict:
    """What ``setup_info.json`` says: the setup, the Studio and engine that
    wrote it (*engine*, else :func:`engine_version`), and Validate's last
    result for the setup as it is now."""
    rep = (validation or {}).get("report")
    if rep and (validation or {}).get("current"):
        checked = {"status": rep["status"], "counts": rep["counts"], "when": rep["started"]}
    elif rep:
        checked = {"status": "out of date", "when": rep["started"],
                   "note": "the setup changed after the last Validate"}
    else:
        checked = {"status": "not run"}
    return {"configurator": name, "made_by": "MAS Studio", "made": datetime.now().isoformat(timespec="seconds"),
            "engine": engine or engine_version(), "pack_format": pack_format(pack_dir), "validate": checked}


# ---------------------------------------------------------------------------
# the key scan
# ---------------------------------------------------------------------------

def _mask(value: str) -> str:
    return f"{value[:4]}… ({len(value)} characters)"


def scan(files: dict[str, bytes]) -> list[dict]:
    """``[{file, line, what, shown}]``: what in the text files looks like an
    API key or a private key, the value masked."""
    found = []
    for rel, raw in sorted(files.items()):
        if b"\x00" in raw[:4096] or len(raw) > 5 * 1024 * 1024:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for what, rx in KEY_PATTERNS:
                for m in rx.finditer(line):
                    value = m.group(1) if m.groups() else m.group(0)
                    found.append({"file": rel, "line": n, "what": what, "shown": _mask(value)})
    return found


# ---------------------------------------------------------------------------
# the tools' own dependencies
# ---------------------------------------------------------------------------

_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
# Where the merged part starts: a merge again replaces it (python -m studio
# prepare runs it on a package whose tools may have changed).
REQ_MARK = "# ---- this setup's tools ----"
APT_MARK = "        # ---- this setup's tools (dc_pack/tools/<tool>/apt.txt) ----"


def _req_name(line: str) -> str | None:
    m = _REQ_NAME_RE.match(line)
    return m.group(1).lower().replace("_", "-") if m else None


def _lines(raw: bytes) -> list[str]:
    return [ln.strip() for ln in raw.decode("utf-8", "replace").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def merge_requirements(engine_text: str, setup: dict[str, Path]) -> tuple[str, list[str]]:
    """The engine's ``requirements.txt`` with each tool's own
    ``tools/<tool>/requirements.txt`` added after :data:`REQ_MARK` (a part
    merged before is replaced); a package the engine already names is kept
    as the engine has it (a different version is noted)."""
    eol = "\r\n" if "\r\n" in engine_text else "\n"
    at = engine_text.find(eol + REQ_MARK)
    if at >= 0:
        engine_text = engine_text[:at]
    have = {}
    for ln in engine_text.splitlines():
        n = _req_name(ln) if ln.strip() and not ln.strip().startswith("#") else None
        if n:
            have[n] = ln.strip()
    added, notes = [], []
    for rel, path in sorted(setup.items()):
        parts = rel.split("/")
        if len(parts) != 3 or parts[0] != "tools" or parts[2] != "requirements.txt":
            continue
        tool = parts[1]
        new = []
        for ln in _lines(path.read_bytes()):
            n = _req_name(ln)
            if n is None or ln.startswith("-"):
                notes.append(f"{tool}: the line {ln!r} of its requirements.txt was left out")
            elif n in have:
                if have[n].replace(" ", "") != ln.replace(" ", ""):
                    notes.append(f"{tool} asks for {ln}; the engine's {have[n]} is kept")
            else:
                have[n] = ln
                new.append(ln)
        if new:
            added.append(f"# for the tool {tool} (dc_pack/tools/{tool}/requirements.txt)")
            added += new
    if not added:
        return engine_text, notes
    body = engine_text if engine_text.endswith(("\n", "\r\n")) else engine_text + eol
    return body + eol + REQ_MARK + eol + eol.join(added) + eol, notes


def merge_apt(dockerfile: str, setup: dict[str, Path]) -> tuple[str, list[str]]:
    """The ``Dockerfile`` with each tool's own ``tools/<tool>/apt.txt``
    packages added to its apt-get line, after :data:`APT_MARK` (a part merged
    before is replaced)."""
    eol = "\r\n" if "\r\n" in dockerfile else "\n"
    lines = dockerfile.split(eol)
    if APT_MARK in lines:
        i = lines.index(APT_MARK)
        j = next((k for k in range(i, len(lines)) if "rm -rf /var/lib/apt/lists/*" in lines[k]), len(lines))
        dockerfile = eol.join(lines[:i] + lines[j:])
    want, notes = [], []
    for rel, path in sorted(setup.items()):
        parts = rel.split("/")
        if len(parts) != 3 or parts[0] != "tools" or parts[2] != "apt.txt":
            continue
        for ln in _lines(path.read_bytes()):
            if re.fullmatch(r"[a-z0-9][a-z0-9.+-]*", ln):
                if ln not in want and not re.search(rf"^\s+{re.escape(ln)} \\$", dockerfile, re.M):
                    want.append(ln)
            else:
                notes.append(f"{parts[1]}: {ln!r} in its apt.txt is not a package name: left out")
    if not want:
        return dockerfile, notes
    lines = dockerfile.split(eol)
    at = next((i for i, ln in enumerate(lines) if "rm -rf /var/lib/apt/lists/*" in ln), None)
    if at is None:
        return dockerfile, notes + ["the Dockerfile has no apt-get line: the tools' apt.txt "
                                    "packages were not added (" + ", ".join(want) + ")"]
    lines[at:at] = [APT_MARK] + [f"        {p} \\" for p in want]
    return eol.join(lines), notes


# ---------------------------------------------------------------------------
# the files written for a package
# ---------------------------------------------------------------------------

def _secrets(setup: dict[str, Path]) -> list[dict]:
    out = []
    for rel, path in sorted(setup.items()):
        parts = rel.split("/")
        if len(parts) != 3 or parts[0] != "tools" or parts[2] != "tool.yaml":
            continue
        try:
            m = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        for s in m.get("secrets") or []:
            if isinstance(s, dict) and s.get("env"):
                out.append({"tool": parts[1], "env": s["env"], "required": bool(s.get("required")),
                            "description": str(s.get("description") or "")})
    return out


def env_example(engine_text: str, secrets: list[dict]) -> str:
    """The engine's ``.env.example`` with the variables this setup's tools
    declare that it does not already name."""
    eol = "\r\n" if "\r\n" in engine_text else "\n"
    named = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", engine_text, re.M))
    new = [s for s in secrets if s["env"] not in named]
    if not new:
        return engine_text
    rule = "# " + "-" * 70
    lines = ["", rule, "# The tools of this setup", rule]
    for s in new:
        lines.append(f"# {s['tool']}: {s['description']} ({'required' if s['required'] else 'optional'})")
        lines.append(f"{s['env']}=")
    body = engine_text if engine_text.endswith(("\n", "\r\n")) else engine_text + eol
    return body + eol.join(lines) + eol


def _fill(template: str, values: dict[str, str]) -> str:
    for k, v in values.items():
        template = template.replace("{{" + k + "}}", v)
    return template


def deploy_md(title: str, dc: str, name: str, secrets: list[dict], info: dict) -> str:
    """``DEPLOY.md`` for this setup, from ``package_files/DEPLOY.md``."""
    if secrets:
        rows = ["| Variable | Tool | Needed | What it is |", "|---|---|---|---|"]
        rows += [f"| `{s['env']}` | {s['tool']} | {'yes' if s['required'] else 'if you use it'} | "
                 f"{s['description']} |" for s in secrets]
        tools = "\n".join(rows)
    else:
        tools = "No tool of this setup needs a variable of its own."
    v = info["validate"]
    checked = (f"Validate: {v['status']}" + (f" ({v['counts']['fail']} failed, {v['counts']['warn']} "
                                             f"warnings, {v['counts']['pass']} passed)" if "counts" in v else "")
               + (f", {v['when'].replace('T', ' ')}" if v.get("when") else ""))
    return _fill((FILES / "DEPLOY.md").read_text(encoding="utf-8"),
                 {"TITLE": title, "DC": dc, "NAME": name, "MADE": info["made"].replace("T", " "),
                  "ENGINE": info["engine"], "VALIDATE": checked, "TOOL_VARIABLES": tools})


def readme_md(title: str, dc: str) -> str:
    return _fill((FILES / "README.md").read_text(encoding="utf-8"), {"TITLE": title, "DC": dc})


# ---------------------------------------------------------------------------
# the zips
# ---------------------------------------------------------------------------

def names(pack_dir: Path, dc_name: str | None) -> tuple[str, str, str]:
    """(file-name stem, title, the name in a sentence) from the
    configurator's title (``$app_title``, else ``$dc_name``)."""
    base = " ".join((dc_name or "").split()) or pack_dir.name
    return slug(base), base[:1].upper() + base[1:], base


def setup_contents(pack_dir: Path, info: dict) -> dict[str, bytes]:
    out = {f"{SETUP_DIR}/{rel}": p.read_bytes() for rel, p in setup_files(pack_dir).items()}
    out[INFO] = (json.dumps(info, indent=2) + "\n").encode("utf-8")
    return out


def package_contents(pack_dir: Path, name: str, title: str, dc: str, info: dict,
                     repo: Path = REPO) -> tuple[dict[str, bytes], list[str]]:
    """The full package's files (paths inside its folder) and the notes of
    the dependency merge."""
    setup = setup_files(pack_dir)
    out = {rel: (repo / rel).read_bytes() for rel in engine_files(repo)}
    for rel, p in setup.items():
        out[f"{SETUP_DIR}/{rel}"] = p.read_bytes()
    notes = []
    req, n1 = merge_requirements(out["requirements.txt"].decode("utf-8"), setup)
    dock, n2 = merge_apt(out["Dockerfile"].decode("utf-8"), setup)
    notes += n1 + n2
    out["requirements.txt"], out["Dockerfile"] = req.encode("utf-8"), dock.encode("utf-8")
    secrets = _secrets(setup)
    out[".env.example"] = env_example((repo / ".env.example").read_bytes().decode("utf-8"),
                                      secrets).encode("utf-8")
    out["README.md"] = readme_md(title, dc).encode("utf-8")
    out["DEPLOY.md"] = deploy_md(title, dc, name, secrets, info).encode("utf-8")
    out[INFO] = (json.dumps(info, indent=2) + "\n").encode("utf-8")
    return out, notes


def write_zip(contents: dict[str, bytes], to: Path, folder: str | None = None) -> Path:
    with zipfile.ZipFile(to, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, raw in sorted(contents.items()):
            z.writestr(f"{folder}/{rel}" if folder else rel, raw)
    return to


# ---------------------------------------------------------------------------
# Open setup file
# ---------------------------------------------------------------------------

_SAFE_PART_RE = re.compile(r"^[^<>:\"|?*\x00-\x1f]+$")


def read_setup_file(raw: bytes) -> tuple[dict[str, bytes], dict | None]:
    """The setup's files (paths inside the setup) and its ``setup_info.json``
    from a setup file -- or a full package: its ``dc_pack/`` is taken.
    Raises :class:`PackageError` with every reason it cannot be opened."""
    if len(raw) > MAX_ZIP:
        raise PackageError(f"The file is {len(raw) / 1048576:.1f} MB; the limit is "
                           f"{MAX_ZIP // 1048576} MB.")
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise PackageError("This is not a setup file: it is not a zip file.") from None
    entries = [i for i in z.infolist() if not i.is_dir()]
    if len(entries) > MAX_ENTRIES:
        raise PackageError(f"The file holds {len(entries)} files; the limit is {MAX_ENTRIES}.")
    if sum(i.file_size for i in entries) > MAX_UNPACKED:
        raise PackageError(f"Unpacked, the file is larger than {MAX_UNPACKED // 1048576} MB.")
    problems, prefix = [], None
    for i in entries:
        parts = i.filename.split("/")
        if SETUP_DIR in parts[:2]:
            p = "/".join(parts[:parts.index(SETUP_DIR) + 1]) + "/"
            prefix = prefix or p
            if p != prefix:
                problems.append(f"two setups in one file: {prefix} and {p}")
    if prefix is None:
        raise PackageError("This is not a setup file: it has no dc_pack/ folder.")
    files, info = {}, None
    for i in entries:
        name = i.filename
        if name in (INFO, prefix[:-len(SETUP_DIR) - 1] + INFO):
            try:
                info = json.loads(z.read(i).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                problems.append(f"{INFO} is not valid JSON")
            continue
        if not name.startswith(prefix):
            continue
        rel = name[len(prefix):]
        parts = rel.split("/")
        if ("\\" in name or name.startswith("/") or any(p in ("", ".", "..") for p in parts)
                or not all(_SAFE_PART_RE.match(p) for p in parts)):
            problems.append(f"{name}: not a path the Studio writes")
            continue
        if (i.external_attr >> 16) & 0o170000 == 0o120000:
            problems.append(f"{name}: a link, not a file")
            continue
        if {"__pycache__", "node_modules"} & set(parts):
            continue
        files[rel] = z.read(i)
    if "pack.yaml" not in files:
        problems.append("dc_pack/pack.yaml is missing")
    if problems:
        raise PackageError("This setup file cannot be opened.", problems)
    return files, info


def replace_setup(pack_dir: Path, files: dict[str, bytes]) -> None:
    """Make the folder *pack_dir* hold exactly *files* (paths inside it): a
    file that differs is written, one that is not in *files* removed, with
    the folders left empty."""
    pack_dir.mkdir(parents=True, exist_ok=True)
    for rel, path in setup_files(pack_dir).items():
        if rel not in files:
            path.unlink()
    for rel, raw in files.items():
        target = pack_dir / rel
        if target.is_file() and target.read_bytes() == raw:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    for d in sorted((p for p in pack_dir.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        if d.name != "__pycache__" and not any(d.iterdir()):
            d.rmdir()


# ---------------------------------------------------------------------------
# what git would take (python -m studio prepare; no git is run)
# ---------------------------------------------------------------------------

class IgnoreRules:
    """A folder's ``.gitignore`` read the way git reads it, closely enough
    for prepare: ``#`` comments, ``!`` to take a path back, a trailing ``/``
    for folders only, a pattern with a ``/`` matched from the folder's root,
    one without matched against each name; the last rule that matches wins."""

    def __init__(self, text: str):
        self.rules = []
        for raw in text.splitlines():
            ln = raw.rstrip()
            if not ln or ln.startswith("#"):
                continue
            neg = ln.startswith("!")
            ln = ln[1:] if neg else ln
            dir_only = ln.endswith("/")
            ln = ln.rstrip("/")
            anchored = "/" in ln
            self.rules.append((ln.lstrip("/"), neg, dir_only, anchored))

    def ignored(self, rel: str, is_dir: bool = False) -> bool:
        out = False
        for pat, neg, dir_only, anchored in self.rules:
            if dir_only and not is_dir:
                continue
            if fnmatch.fnmatchcase(rel if anchored else rel.rsplit("/", 1)[-1], pat):
                out = not neg
        return out


def files_git_takes(folder: Path) -> list[str]:
    """The files ``git add .`` would take in *folder*, by its ``.gitignore``
    files (each folder's own one too; a folder they ignore is not entered)."""
    out = []

    def ignored(chain, r: str, is_dir: bool) -> bool:
        hit = False
        for base, rules in chain:                 # the deeper .gitignore decides last
            sub = r[len(base):]
            for pat, neg, dir_only, anchored in rules.rules:
                if dir_only and not is_dir:
                    continue
                if fnmatch.fnmatchcase(sub if anchored else sub.rsplit("/", 1)[-1], pat):
                    hit = not neg
        return hit

    def walk(d: Path, rel: str, chain: list) -> None:
        gi = d / ".gitignore"
        if gi.is_file():
            chain = chain + [(rel, IgnoreRules(gi.read_text(encoding="utf-8", errors="replace")))]
        for p in sorted(d.iterdir()):
            r = f"{rel}{p.name}"
            if p.name == ".git":                      # a folder, or a worktree's pointer file
                continue
            if p.is_dir():
                if not ignored(chain, r, True):
                    walk(p, r + "/", chain)
            elif p.is_file() and not ignored(chain, r, False):
                out.append(r)
    walk(folder, "", [])
    return out


def env_values(folder: Path) -> dict[str, str]:
    """The values set in *folder*'s ``.env`` (8 characters or more): what
    must not be in a file that is committed."""
    f = folder / ".env"
    out = {}
    if f.is_file():
        for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", ln)
            if m:
                v = m.group(2).strip().strip("\"'")
                if len(v) >= 8:
                    out[m.group(1)] = v
    return out


def scan_values(files: dict[str, bytes], values: dict[str, str]) -> list[dict]:
    """``[{file, line, what, shown}]``: where a value of *values* (a name ->
    its value) appears in the text files."""
    found = []
    for rel, raw in sorted(files.items()):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for name, value in values.items():
                if value in line:
                    found.append({"file": rel, "line": n, "what": f"the value of {name} in .env",
                                  "shown": _mask(value)})
    return found
