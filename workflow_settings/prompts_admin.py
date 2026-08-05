"""System Prompts UI — admin backer.

Endpoint backer for the System Prompts side-window:

  GET  /api/prompts/tree   → :func:`build_tree`
  GET  /api/prompts/file   → :func:`read_file`
  POST /api/prompts/save   → :func:`save_files`

Source of truth for what each fragment file feeds lives in
``agents.shared.prompts.FRAGMENT_TO_SLOT`` (for $-slot fragments)
and ``PROMPT_MD_RUNTIME_SLOTS`` (per-agent {…} allow-list).
WIRING-time fragments (routing_*.md, render_check_library/*.md,
database_search_<agent>.md) are NOT in those maps because they are
loaded at agent-construction time, not via the $-slot pipeline;
their usage mapping is hardcoded below in :data:`_WIRING_TIME_USAGE`.

Path safety: every file the UI can read or write must resolve under
one of :data:`_SOURCE_ROOTS`.  Anything outside is rejected.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from agents.shared.prompts import (
    FRAGMENT_TO_SLOT,
    PROMPT_MD_RUNTIME_SLOTS,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Source roots — the only directories that the UI may read or write
# ---------------------------------------------------------------------------

_SOURCE_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "agents",                                      # per-agent prompt.md
    REPO_ROOT / "agents" / "shared" / "prompt_fragments",      # generic + routing
    REPO_ROOT / "DC_prompt_fragments" / "dc_config",           # DC-config fragments
    REPO_ROOT / "DC_prompt_fragments" / "tools_config",        # tools-config fragments
)


# The 4 named groups (round 2 Q5) that appear in the UI tree.
_GROUPS: tuple[dict, ...] = (
    {"id": "per_agent",      "label": "Per-agent prompts",
     "subtitle": "agents/<agent>/prompt.md"},
    {"id": "routing_shared", "label": "Routing & shared fragments",
     "subtitle": "agents/shared/prompt_fragments/"},
    {"id": "dc_config",      "label": "DC configuration",
     "subtitle": "DC_prompt_fragments/dc_config/"},
    {"id": "tools_config",   "label": "Tools configuration",
     "subtitle": "DC_prompt_fragments/tools_config/"},
    # Topology overrides.  Only the files that DIFFER from the 7-agent
    # originals live here; everything else is shared and appears in the
    # groups above.  Empty (and hidden) when no topology directory
    # exists, so a 7-agent-only checkout sees the original four groups.
    {"id": "topology",       "label": "Topology overrides",
     "subtitle": "agents/<N>agent/"},
)


# ---------------------------------------------------------------------------
# Hardcoded wiring-time usage (mirror of routing_*.md, render_check, overlays)
# ---------------------------------------------------------------------------

_AGENT_DIRS: tuple[str, ...] = (
    "receptionist", "orchestrator", "planner", "user_input_inspector",
    "dc_input_creator", "dc_input_inspector", "tool_caller",
    "dc_output_inspector", "database_handler",
)


_WIRING_TIME_USAGE: dict[str, list[str]] = {
    # Routing fragments — one per chain agent (some have both
    # planner_first + uii_first variants).
    "agents/shared/prompt_fragments/routing_planner_planner_first.md":              ["planner"],
    "agents/shared/prompt_fragments/routing_planner_uii_first.md":                  ["planner"],
    "agents/shared/prompt_fragments/routing_user_input_inspector_planner_first.md": ["user_input_inspector"],
    "agents/shared/prompt_fragments/routing_user_input_inspector_uii_first.md":     ["user_input_inspector"],
    "agents/shared/prompt_fragments/routing_dc_input_creator_planner_first.md":     ["dc_input_creator"],
    "agents/shared/prompt_fragments/routing_dc_input_creator_uii_first.md":         ["dc_input_creator"],
    "agents/shared/prompt_fragments/routing_dc_input_inspector.md":                 ["dc_input_inspector"],
    "agents/shared/prompt_fragments/routing_dc_output_inspector.md":                ["dc_output_inspector"],
    "agents/shared/prompt_fragments/routing_tool_caller.md":                        ["tool_caller"],
    # Render-check library backends — Tool Caller picks one per session.
    "DC_prompt_fragments/tools_config/render_check_library/trimesh.md": ["tool_caller"],
    "DC_prompt_fragments/tools_config/render_check_library/pyvista.md": ["tool_caller"],
    # Per-agent database_search overlays (the $database_search_per_agent slot).
    "DC_prompt_fragments/tools_config/database_search_receptionist.md":         ["receptionist"],
    "DC_prompt_fragments/tools_config/database_search_orchestrator.md":         ["orchestrator"],
    "DC_prompt_fragments/tools_config/database_search_planner.md":              ["planner"],
    "DC_prompt_fragments/tools_config/database_search_user_input_inspector.md": ["user_input_inspector"],
    "DC_prompt_fragments/tools_config/database_search_dc_input_creator.md":     ["dc_input_creator"],
    "DC_prompt_fragments/tools_config/database_search_dc_input_inspector.md":   ["dc_input_inspector"],
    "DC_prompt_fragments/tools_config/database_search_tool_caller.md":          ["tool_caller"],
    "DC_prompt_fragments/tools_config/database_search_dc_output_inspector.md":  ["dc_output_inspector"],
}


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

class PromptsAdminError(ValueError):
    """Raised when the caller passes a path outside the allowed roots,
    asks for a file we won't serve, or sends malformed save payload."""


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _resolve_safe(rel_path: str) -> Path:
    """Resolve ``rel_path`` against REPO_ROOT and verify it sits under
    one of the allowed source roots.  Rejects ``..`` escapes and any
    extension other than .md / .txt."""
    if not rel_path or "\x00" in rel_path:
        raise PromptsAdminError("Empty or null-byte path.")
    p = (REPO_ROOT / rel_path).resolve()
    if not any(_is_within(p, root.resolve()) for root in _SOURCE_ROOTS):
        raise PromptsAdminError(
            f"Path {rel_path!r} is not under an allowed source root."
        )
    if p.suffix.lower() not in (".md", ".txt"):
        raise PromptsAdminError(
            f"Only .md / .txt files are accessible (got {p.suffix!r})."
        )
    return p


def _to_rel(abs_path: Path) -> str:
    """Repo-root-relative POSIX path."""
    return abs_path.relative_to(REPO_ROOT).as_posix()


# ---------------------------------------------------------------------------
# Forward index — slot name → set of agent_dir whose prompt.md uses it
# ---------------------------------------------------------------------------

_DOLLAR_SLOT_RE = re.compile(r"\$([a-z_][a-z0-9_]*)")


def _prompt_md_slot_usage() -> dict[str, set[str]]:
    """Scan every agent's prompt.md for ``$slot`` references and
    return ``{slot_name: {agent_dir, ...}}``.  Cheap (~9 small file
    reads).  Called once per :func:`build_tree` invocation."""
    usage: dict[str, set[str]] = {}
    for agent_dir in _AGENT_DIRS:
        prompt_md = REPO_ROOT / "agents" / agent_dir / "prompt.md"
        if not prompt_md.exists():
            continue
        body = prompt_md.read_text(encoding="utf-8")
        for slot in _DOLLAR_SLOT_RE.findall(body):
            usage.setdefault(slot, set()).add(agent_dir)
    return usage


def _used_by(rel_path: str, slot_usage: dict[str, set[str]]) -> list[str]:
    """List of agent_dir names whose template includes content from
    this file.  Empty for READMEs / unknown files."""
    # Per-agent prompt.md — direct mapping
    if rel_path.startswith("agents/") and rel_path.endswith("/prompt.md"):
        parts = rel_path.split("/")
        if len(parts) >= 3:
            return [parts[1]]
    # Hardcoded WIRING-time fragments
    if rel_path in _WIRING_TIME_USAGE:
        return list(_WIRING_TIME_USAGE[rel_path])
    # $-slot fragments
    slot = FRAGMENT_TO_SLOT.get(rel_path)
    if slot:
        return sorted(slot_usage.get(slot, set()))
    # README / unknown → nothing
    return []


# ---------------------------------------------------------------------------
# Tree builder
# ---------------------------------------------------------------------------

def build_tree() -> dict:
    """Return the tree shape the System Prompts UI consumes:

      {
        "groups": [{"id", "label", "path_subtitle", "children": [...]}, ...]
      }
    """
    slot_usage = _prompt_md_slot_usage()
    groups_out: list[dict] = []
    for g in _GROUPS:
        if g["id"] == "per_agent":
            children = _per_agent_children()
        elif g["id"] == "topology":
            children = _topology_children(slot_usage)
            if not children:
                continue          # no topology dir -> hide the group
        else:
            root = _group_root(g["id"])
            children = _walk_dir(root, slot_usage)
        groups_out.append({
            "id":            g["id"],
            "label":         g["label"],
            "path_subtitle": g["subtitle"],
            "children":      children,
        })
    return {"groups": groups_out}


def _group_root(group_id: str) -> Path:
    return {
        "routing_shared": REPO_ROOT / "agents" / "shared" / "prompt_fragments",
        "dc_config":      REPO_ROOT / "DC_prompt_fragments" / "dc_config",
        "tools_config":   REPO_ROOT / "DC_prompt_fragments" / "tools_config",
    }[group_id]


def _topology_children(slot_usage: dict[str, set[str]]) -> list[dict]:
    """One folder per ``agents/<N>agent/`` directory found on disk.

    Discovered rather than hard-coded, so the 3-agent variant appears
    the moment its directory exists.
    """
    out: list[dict] = []
    agents_root = REPO_ROOT / "agents"
    if not agents_root.is_dir():
        return out
    for d in sorted(agents_root.iterdir(), key=lambda p: p.name.lower()):
        if d.is_dir() and _TOPOLOGY_DIR_RE.fullmatch(d.name):
            inner = _walk_dir(d, slot_usage)
            if inner:
                out.append({"kind": "folder", "display": d.name,
                            "children": inner})
    return out


def _per_agent_children() -> list[dict]:
    """Every agent prompt that lives in its own package.

    Covers the nine 7-agent prompts AND agents that exist only in a
    reduced topology (Conductor, Creator), whose file is
    ``prompt_<N>agents.md`` — those have no plain ``prompt.md``, so
    iterating a fixed list against that one name hid them completely.
    """
    children: list[dict] = []
    agents_root = REPO_ROOT / "agents"
    for d in sorted(agents_root.iterdir(), key=lambda p: p.name.lower()):
        if not d.is_dir() or _TOPOLOGY_DIR_RE.fullmatch(d.name):
            continue
        for f in sorted(d.iterdir(), key=lambda p: p.name.lower()):
            if f.is_file() and _PROMPT_FILE_RE.match(f.name):
                children.append({
                    "kind":    "file",
                    "path":    _to_rel(f),
                    "display": (d.name if f.name == "prompt.md"
                                else f"{d.name}  ({f.stem.split(chr(95))[-1]})"),
                    "used_by": [d.name],
                })
    return children


def _walk_dir(root: Path, slot_usage: dict[str, set[str]]) -> list[dict]:
    """Mirror disk subfolders exactly (round 3 Q10).  Returns a tree
    of ``{kind:'folder', display, children}`` and ``{kind:'file',
    path, display, used_by}`` nodes, sorted alphabetically with
    folders before files at each level.  Only .md files are surfaced
    as leaves (round 1 Q4)."""
    if not root.exists():
        return []
    folders: list[dict] = []
    files:   list[dict] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_dir():
            inner = _walk_dir(entry, slot_usage)
            if inner:
                folders.append({
                    "kind":     "folder",
                    "display":  entry.name,
                    "children": inner,
                })
        elif entry.is_file() and entry.suffix.lower() == ".md":
            rel = _to_rel(entry)
            files.append({
                "kind":    "file",
                "path":    rel,
                "display": entry.name,
                "used_by": _used_by(rel, slot_usage),
            })
    return folders + files


# ---------------------------------------------------------------------------
# Read / save
# ---------------------------------------------------------------------------

_MARKER_PAIRS: tuple[tuple[str, str], ...] = (
    ("<<DCII_ONLY>>", "<</DCII_ONLY>>"),
    ("<<DCII_OFF>>",  "<</DCII_OFF>>"),
    ("<<PF_ON>>",     "<</PF_ON>>"),
    ("<<PF_OFF>>",    "<</PF_OFF>>"),
    ("<<HAS_DBA>>",   "<</HAS_DBA>>"),
)


def _has_conditional_regions(content: str) -> bool:
    return any(
        open_ in content or close_ in content
        for open_, close_ in _MARKER_PAIRS
    )


def read_file(rel_path: str) -> dict:
    """Return ``{ok, path, content, has_conditional_regions}``."""
    p = _resolve_safe(rel_path)
    if not p.exists():
        raise PromptsAdminError(f"File not found: {rel_path}")
    content = p.read_text(encoding="utf-8")
    return {
        "ok":                       True,
        "path":                     rel_path,
        "content":                  content,
        "has_conditional_regions":  _has_conditional_regions(content),
    }


def save_files(files: list[dict]) -> dict:
    """Atomic-write each ``{path, content}`` to disk, then return
    ``{ok, files_written: [...], warnings: [...]}``.

    Atomicity: each file is written to ``<path>.tmp.<uuid>`` via
    ``tempfile.mkstemp`` and then ``os.replace``'d into place — a
    crash mid-write leaves either the previous content or the new
    content, never a partial file.

    Cross-file atomicity is NOT provided (a partial batch can land if
    Python crashes between two writes).  The frontend's pre-save
    validator + the backend's same validator below catch the same
    warnings, so this hasn't been worth the journal complexity.
    """
    if not isinstance(files, list) or not files:
        raise PromptsAdminError("No files supplied.")
    # Resolve all paths up-front so we fail fast on the first bad one.
    resolved: list[tuple[str, Path, str]] = []
    for entry in files:
        if not isinstance(entry, dict):
            raise PromptsAdminError("Each file entry must be an object.")
        rel = entry.get("path")
        body = entry.get("content")
        if not isinstance(rel, str) or not isinstance(body, str):
            raise PromptsAdminError(
                "Each entry needs string 'path' and 'content'."
            )
        resolved.append((rel, _resolve_safe(rel), body))

    # Per-file validation BEFORE any write so the response surfaces
    # warnings even when the caller chose to save through them.
    warnings: list[dict] = []
    for rel, _, body in resolved:
        warnings.extend(validate_one(rel, body))

    # Tree usage info, used to populate affected_agents per file.
    slot_usage = _prompt_md_slot_usage()

    files_written: list[dict] = []
    for rel, abs_path, body in resolved:
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        # ``tempfile.mkstemp`` with ``delete=False`` in the SAME
        # directory so os.replace is atomic on Windows + POSIX.
        fd, tmp = tempfile.mkstemp(
            prefix=abs_path.name + ".tmp.",
            dir=str(abs_path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(body)
            os.replace(tmp, abs_path)
        except Exception:
            try:
                Path(tmp).unlink(missing_ok=True)
            except Exception:
                pass
            raise
        files_written.append({
            "path":             rel,
            "affected_agents":  _used_by(rel, slot_usage),
        })

    return {
        "ok":             True,
        "files_written":  files_written,
        "warnings":       warnings,
    }


# ---------------------------------------------------------------------------
# Validation — 3 rules (round 5 Q18) + the empty-file warning (round 6 Q23)
# ---------------------------------------------------------------------------

_KNOWN_SLOTS_NOTE = (
    "Unknown $-slot.  Known slots: see _build_slots in "
    "agents/shared/prompts.py."
)

# `{x}` that isn't part of `{{x}}` / `}}` escape pairs.
_BRACE_RE = re.compile(
    r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})"
)


def _known_slot_names() -> frozenset[str]:
    """Slot names that ``Template.safe_substitute`` will resolve.

    Derived from the LIVE slot map rather than the ``FRAGMENT_TO_SLOT``
    reverse index, because the two drift: the index only lists slots that
    come from an editable file, so slots built from settings values
    (``$embedding_*``) or from more than one file were reported as
    "unknown" even though they resolve perfectly.  Both per-agent overlays
    are added by hand — they are merged in by ``_build_template`` rather
    than living in the slot map.
    """
    from agents.shared.prompts import _build_slots

    return frozenset(_build_slots()) | {
        "database_search_per_agent",
        "blade_sections_visualizer_per_agent",
    }


# Roots whose ``.md`` files are spliced into prompts via ``$slot``.  Used by
# rule (c) to decide whether a non-prompt file is a fragment.  READMEs sit in
# these trees but are never spliced, so they are excluded.
_FRAGMENT_ROOT_PREFIXES: tuple[str, ...] = (
    "agents/shared/prompt_fragments/",
    "DC_prompt_fragments/",
)


def _is_spliced_fragment(rel_path: str) -> bool:
    """True when ``rel_path`` is a fragment whose text lands in a prompt."""
    if not rel_path.endswith(".md"):
        return False
    if Path(rel_path).name.upper().startswith("README"):
        return False
    if any(rel_path.startswith(p) for p in _FRAGMENT_ROOT_PREFIXES):
        return True
    # A topology's overrides mirror those same roots under agents/<N>agent/.
    parts = rel_path.split("/")
    return (
        len(parts) >= 4
        and parts[0] == "agents"
        and _TOPOLOGY_DIR_RE.fullmatch(parts[1]) is not None
        and parts[2] in ("prompt_fragments", "dc_config", "tools_config")
    )


# The three shapes an agent prompt can take.  The topology work added the
# latter two, and the old ``len(parts) == 3 and parts[2] == "prompt.md"``
# test matched neither — so rule (c) silently skipped every 5-agent prompt.
#
#   agents/<X>/prompt.md                         7-agent, and any survivor
#   agents/<X>/prompt_<N>agents.md               agent existing ONLY in <N>
#   agents/<N>agent/<X>/prompt_<N>agents.md      <N>'s copy of a survivor
#
# In all three the agent directory is the SECOND-TO-LAST path segment.
_PROMPT_FILE_RE = re.compile(r"^prompt(?:_\d+agents(?:_[a-z0-9]+)?)?\.md$")

# A topology directory: agents/<N>agent/, or a PROMPT_VARIANT of one,
# agents/<N>agent_<variant>/.  Defined once because three call sites need
# it -- the tree walker, the per-agent lister and the fragment test -- and
# a fourth pattern drifting from the others is how the variant folder was
# invisible to the editor in the first place.
_TOPOLOGY_DIR_RE = re.compile(r"\d+agent(?:_[a-z0-9]+)?")


def _agent_for_prompt_md(rel_path: str) -> str | None:
    """Agent directory name if ``rel_path`` is an agent prompt, else None."""
    parts = rel_path.split("/")
    if (
        len(parts) >= 3
        and parts[0] == "agents"
        and _PROMPT_FILE_RE.match(parts[-1])
    ):
        return parts[-2]
    return None


def validate_one(rel_path: str, content: str) -> list[dict]:
    """Run the 3 validation rules + the empty-file check on one file.

    Returns ``[{path, line, kind, detail}, ...]``.  Empty when clean.

    READMEs are documentation ABOUT the fragment system and are never
    spliced into a prompt, so rules (a) and (b) are skipped for them: they
    deliberately contain example slot names (``$slot_name``) and prose
    mentions of region markers, none of which can cause a runtime failure,
    and reporting them buried the real findings under five permanent false
    positives.  Rule (c) already skips them via ``_is_spliced_fragment``.
    The empty-file check still applies — a blanked README is a real edit
    accident whatever the file is for.
    """
    warnings: list[dict] = []
    lines = content.splitlines()
    is_readme = Path(rel_path).name.upper().startswith("README")

    # Rule (a) — unknown $slot
    if not is_readme:
        known = _known_slot_names()
        for i, line in enumerate(lines, start=1):
            for m in _DOLLAR_SLOT_RE.finditer(line):
                name = m.group(1)
                if name not in known:
                    warnings.append({
                        "path":   rel_path,
                        "line":   i,
                        "kind":   "unknown_slot",
                        "detail": f"${name} — {_KNOWN_SLOTS_NOTE}",
                    })

    # Rule (b) — unbalanced <<…>> conditional markers
    if not is_readme:
        for open_, close_ in _MARKER_PAIRS:
            n_open  = content.count(open_)
            n_close = content.count(close_)
            if n_open != n_close:
                row = 1
                for i, line in enumerate(lines, start=1):
                    if open_ in line or close_ in line:
                        row = i
                        break
                warnings.append({
                    "path":   rel_path,
                    "line":   row,
                    "kind":   "unbalanced_marker",
                    "detail": (
                        f"{open_} opens={n_open}, closes={n_close} "
                        "— region marker mismatch will swallow content "
                        "via the greedy regex."
                    ),
                })

    # Rule (c) — unescaped { that runtime .format() would choke on.
    #
    # Applies to agent prompts AND to spliced fragments.  Fragments matter
    # just as much: they are substituted INTO a prompt before that prompt is
    # .format()ed, so a literal brace in a fragment reaches .format() exactly
    # as if it had been typed in the prompt.  Rule (c) used to skip them
    # entirely, which left the codebase's top recorded gotcha unguarded in
    # the one place it is easiest to hit by accident (pasting JSON or code
    # into a shared fragment).
    #
    # Fragments allow NO unescaped single brace at all.  None currently
    # carries one, and a fragment can be spliced into several agents with
    # different allow-lists, so "none" is both the status quo and the only
    # rule that is correct for every consumer.  Warnings are advisory, so a
    # deliberate exception can still be saved through.
    agent = _agent_for_prompt_md(rel_path)
    is_fragment = agent is None and _is_spliced_fragment(rel_path)
    if agent is not None or is_fragment:
        allowed = (
            PROMPT_MD_RUNTIME_SLOTS.get(agent, frozenset())
            if agent is not None else frozenset()
        )
        for i, line in enumerate(lines, start=1):
            for m in _BRACE_RE.finditer(line):
                name = m.group(1)
                if name not in allowed:
                    if agent is not None:
                        where = (
                            f"Allowed for {agent}: "
                            f"{', '.join(sorted(allowed)) or '(none)'}."
                        )
                    else:
                        where = (
                            "Fragments take no runtime slots — this text is "
                            "spliced into a prompt that is then .format()ed."
                        )
                    warnings.append({
                        "path":   rel_path,
                        "line":   i,
                        "kind":   "brace_escape",
                        "detail": (
                            f"{{{name}}} — runtime .format() will raise "
                            f"KeyError.  {where}  "
                            "To embed a literal brace, double it: "
                            "`{{` / `}}`."
                        ),
                    })

    # Empty-file warning (round 6 Q23) — applies to any saved file.
    if not content.strip():
        warnings.append({
            "path":   rel_path,
            "line":   1,
            "kind":   "empty_file",
            "detail": "File is empty after edits.",
        })

    return warnings
